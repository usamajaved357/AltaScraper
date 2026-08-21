"""monitor/bulk_import.py — tolerant bulk ASIN file import for the ASIN Monitor.

Accepts CSV / TXT / XLSX with NO rigid template. Auto-detects:
  - the ASIN column: the column whose values most look like ASINs (10-char alnum, usually B0…)
  - an optional label/title column (by header hint, else the first free-text column)
  - an optional marketplaces column (by header hint, else values that look like EU codes)
Returns clean rows [{asin, label, marketplaces}] + a per-row 'invalid' list (row #, value, why),
so a few bad rows never fail the whole file. No side effects -- the route decides new-vs-existing
and calls asin_monitor.add (which updates duplicates instead of creating them).
"""
import io
import re
import csv

_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
EU = ["UK", "DE", "FR", "IT", "ES", "NL", "PL", "SE", "BE", "IE"]


def _looks_asin(v):
    return bool(_ASIN_RE.match(str(v or "").strip().upper()))


def _parse_mkts(cell):
    parts = re.split(r"[,;/|\s]+", str(cell or "").upper())
    seen, out = set(), []
    for p in parts:
        p = "UK" if p == "GB" else p
        if p in EU and p not in seen:
            seen.add(p); out.append(p)
    return out


def _read_grid(data, filename):
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        return [[("" if c is None else str(c)) for c in row]
                for row in ws.iter_rows(values_only=True)]
    text = data.decode("utf-8-sig", "replace") if isinstance(data, (bytes, bytearray)) else str(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
        rdr = csv.reader(io.StringIO(text), dialect)
    except Exception:
        rdr = csv.reader(io.StringIO(text))       # falls back to comma; one-col TXT still works
    return [list(r) for r in rdr]


# ---- the OTHER list you can paste in: seller IDs and who they are -----------
#
#   "i have the names of the sellers which i can put in a csv file to tell the
#    asin monitor that this seller id's person name is this. whether it is
#    amazon, myself, or a third party."
#
# A seller ID is 13-14 characters, starts with an A, and is upper-case
# alphanumeric -- distinctive enough to find its own column without a template,
# the same way the ASIN importer already finds ASINs.
_SELLER_RE = re.compile(r"^A[0-9A-Z]{9,20}$")

# What the "who is this" column may say, and what it means to the app. Written
# generously because a person typing a spreadsheet writes "3rd party", "me",
# "mine", "Amazon Retail" -- not the app's four internal words.
_KIND_WORDS = {
    "me": "me", "mine": "me", "us": "me", "our": "me", "ours": "me",
    "myself": "me", "my account": "me", "own": "me", "self": "me",
    "amazon": "amazon", "amazon retail": "amazon", "amz": "amazon",
    "retail": "amazon",
    "authorised": "authorised", "authorized": "authorised",
    "approved": "authorised", "reseller": "authorised",
    "distributor": "authorised", "partner": "authorised", "trusted": "authorised",
    "third party": "name", "3rd party": "name", "thirdparty": "name",
    "3p": "name", "other": "name", "competitor": "name", "hijacker": "name",
    "name": "name", "named": "name", "unknown": "unknown", "": "name",
}


def _looks_seller(v):
    return bool(_SELLER_RE.match(str(v or "").strip().upper()))


def _kind_of(v):
    """A person's word for who a seller is -> the app's four. Unrecognised text
    is treated as a NAMED THIRD PARTY, which is the safe direction: it stays
    flagged and visible rather than being quietly trusted."""
    s = str(v or "").strip().lower()
    if s in _KIND_WORDS:
        return _KIND_WORDS[s]
    for word, kind in _KIND_WORDS.items():
        if word and word in s:
            return kind
    return "name"


def parse_sellers(data, filename=""):
    """A CSV/TXT/XLSX of seller IDs -> [{seller_id, name, kind, marketplace}].

    NO TEMPLATE NEEDED, same as the ASIN importer. The seller column is found by
    shape; the name is the column beside it with the most text in it; the
    "who is this" column is found by its header OR by its values.

    -> {"rows": [...], "invalid": [...], "columns": {...}}
    """
    grid = _read_grid(data, filename)
    if not grid:
        return {"rows": [], "invalid": [], "columns": {},
                "error": "That file has no rows in it."}

    ncols = max((len(r) for r in grid), default=0)
    hdr = [str(c or "").strip().lower() for c in (grid[0] if grid else [])]

    # IS ROW ONE A HEADER, OR THE FIRST SELLER?
    #
    # "any(hdr)" is not the test -- a headerless file's first row is full of
    # text too, and treating it as a header silently ate the first seller.
    # Measured: a two-line file with no header imported one row. A row that
    # CONTAINS a seller ID is data, whatever else is in it.
    has_header = not any(_looks_seller(c) for c in (grid[0] if grid else []))
    start = 1 if has_header else 0

    def find_header(*names):
        if not has_header:
            return None
        for i, h in enumerate(hdr):
            for n in names:
                if n in h:
                    return i
        return None

    # The seller column: by header first, then by what the values look like.
    sid_col = find_header("seller id", "seller_id", "sellerid", "merchant id",
                          "merchantid", "seller")
    if sid_col is None or not any(_looks_seller(r[sid_col])
                                 for r in grid[start:] if sid_col < len(r)):
        best, best_n = None, 0
        for ci in range(ncols):
            n = sum(1 for r in grid[start:] if ci < len(r) and _looks_seller(r[ci]))
            if n > best_n:
                best, best_n = ci, n
        sid_col = best
    if sid_col is None:
        return {"rows": [], "invalid": [], "columns": {},
                "error": ("No seller IDs found. A seller ID looks like "
                          "A3TSTGWB8M3T3Z — one column of them is all this "
                          "needs. Columns seen: "
                          + ", ".join(h for h in hdr if h)[:160])}

    kind_col = find_header("kind", "type", "who", "category", "class",
                           "relationship")
    name_col = find_header("name", "seller name", "label", "company", "business")
    if name_col is None or name_col == sid_col:
        # The wordiest OTHER column wins -- that is where a person puts a name.
        best, best_len = None, 0
        for ci in range(ncols):
            if ci in (sid_col, kind_col):
                continue
            tot = sum(len(str(r[ci]).strip()) for r in grid[start:]
                      if ci < len(r) and not _looks_seller(r[ci]))
            if tot > best_len:
                best, best_len = ci, tot
        name_col = best
    mkt_col = find_header("marketplace", "market", "country", "region")

    rows, invalid, seen = [], [], set()
    for n, r in enumerate(grid[start:], start=start + 1):
        sid = str(r[sid_col]).strip().upper() if sid_col < len(r) else ""
        if not sid:
            continue
        if not _looks_seller(sid):
            invalid.append({"row": n, "value": sid[:40],
                            "why": "does not look like a seller ID"})
            continue
        if sid in seen:
            invalid.append({"row": n, "value": sid,
                            "why": "already in this file"})
            continue
        seen.add(sid)
        name = (str(r[name_col]).strip()
                if name_col is not None and name_col < len(r) else "")
        kind = (_kind_of(r[kind_col])
                if kind_col is not None and kind_col < len(r) else "name")
        mkt = (str(r[mkt_col]).strip().upper()
               if mkt_col is not None and mkt_col < len(r) else "")
        rows.append({"seller_id": sid, "name": name, "kind": kind,
                     "marketplace": mkt})
    return {"rows": rows, "invalid": invalid,
            "columns": {"seller_id": sid_col, "name": name_col,
                        "kind": kind_col, "marketplace": mkt_col},
            "error": ""}


def _pick_asin_col(grid, start):
    best, best_n = None, 0
    ncols = max((len(r) for r in grid), default=0)
    for ci in range(ncols):
        n = sum(1 for r in grid[start:] if ci < len(r) and _looks_asin(r[ci]))
        if n > best_n:
            best, best_n = ci, n
    return best, best_n


def _find_col(header, hints, exclude=None):
    for ci, h in enumerate(header):
        if ci == exclude:
            continue
        if any(x in h for x in hints):
            return ci
    return None


def _find_mkt_by_values(grid, start, exclude):
    ncols = max((len(r) for r in grid), default=0)
    body = grid[start:] or []
    for ci in range(ncols):
        if ci == exclude:
            continue
        hits = sum(1 for r in body if ci < len(r) and _parse_mkts(r[ci]))
        if hits and hits >= max(1, len(body) // 3):
            return ci
    return None


def _first_text_col(grid, start, exclude=()):
    ncols = max((len(r) for r in grid), default=0)
    for ci in range(ncols):
        if ci in exclude:
            continue
        vals = [str(r[ci]).strip() for r in grid[start:] if ci < len(r) and str(r[ci]).strip()]
        if vals and not all(_looks_asin(v) for v in vals):
            return ci
    return None


def _exact_col(header, names):
    """Column whose (lower) header EXACTLY equals one of `names` (priority order)."""
    for want in names:
        for ci, h in enumerate(header):
            if h == want:
                return ci
    return None


def _norm_status(v):
    s = str(v or "").strip().lower()
    if s.startswith("active"):
        return "Active"
    if s.startswith("inactive"):
        return "Inactive"
    if s.startswith("incomplete"):
        return "Incomplete"
    return s.title() if s else ""


def parse(data, filename=""):
    grid = _read_grid(data, filename)
    if not grid:
        return {"rows": [], "invalid": [], "detected": {}, "status_counts": {}}
    row0_has_asin = any(_looks_asin(c) for c in grid[0])
    start = 0 if row0_has_asin else 1
    header = [] if row0_has_asin else [str(c).strip().lower() for c in grid[0]]

    # ASIN column: prefer the Amazon report's 'asin1' (or an exact 'asin' header) so asin2/asin3
    # are NEVER imported as separate ASINs; else fall back to the most-ASIN-looking column.
    asin_col = _exact_col(header, ("asin1", "asin"))
    if asin_col is None:
        asin_col = _find_col(header, ("asin",), exclude=None) if header else None
        # avoid grabbing asin2/asin3 by name
        if asin_col is not None and header and header[asin_col] in ("asin2", "asin3"):
            asin_col = None
    if asin_col is None:
        asin_col, n = _pick_asin_col(grid, start if len(grid) > 1 else 0)
        if not asin_col and n == 0:
            asin_col, n = _pick_asin_col(grid, 0); start = 0
    if asin_col is None:
        return {"rows": [], "invalid": [{"row": 0, "value": "", "reason": "no ASIN column found"}],
                "detected": {}, "status_counts": {}}

    label_col = _exact_col(header, ("item-name", "item name")) \
        or _find_col(header, ("label", "title", "name", "product"), exclude=asin_col)
    status_col = _exact_col(header, ("status",))
    sku_col = _exact_col(header, ("seller-sku", "seller sku", "sku"))
    mkt_col = _find_col(header, ("marketplace", "markets", "mkt", "country", "countries"), exclude=asin_col)
    if mkt_col is None:
        mkt_col = _find_mkt_by_values(grid, start, asin_col)
    if label_col is None:
        label_col = _first_text_col(grid, start, exclude=(asin_col, mkt_col, status_col, sku_col))

    def _cell(r, ci):
        return (str(r[ci]).strip() if (ci is not None and ci < len(r)) else "")

    rows, invalid, seen = [], [], set()
    status_counts = {}
    for ri, r in enumerate(grid[start:], start=start + 1):
        raw = _cell(r, asin_col)
        if not raw and not any(str(c).strip() for c in r):
            continue                               # wholly blank line
        asin = raw.upper()
        if not _looks_asin(asin):
            invalid.append({"row": ri, "value": raw, "reason": "not a 10-character ASIN"})
            continue
        if asin in seen:
            continue                               # duplicate within the file -> keep first
        seen.add(asin)
        st = _norm_status(_cell(r, status_col))
        if st:
            status_counts[st] = status_counts.get(st, 0) + 1
        mkts = _parse_mkts(_cell(r, mkt_col)) if mkt_col is not None else []
        rows.append({"asin": asin, "label": _cell(r, label_col),
                     "marketplaces": mkts or list(EU),
                     "sku": _cell(r, sku_col), "status": st})
    return {"rows": rows, "invalid": invalid, "status_counts": status_counts,
            "detected": {"asin_col": asin_col, "label_col": label_col, "mkt_col": mkt_col,
                         "status_col": status_col, "sku_col": sku_col, "had_header": bool(header)}}
