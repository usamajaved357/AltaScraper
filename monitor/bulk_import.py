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
