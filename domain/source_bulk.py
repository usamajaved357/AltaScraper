"""domain/source_bulk.py -- attach suppliers to many SKUs from one uploaded sheet.

"the repricer tool give me an option to upload a sheet containing the sku's or
 original asins of the item, to add their suppliers through a sheet upload, i
 will write, i can use whether the asin whether the sku to tell the app that
 this supplier or source belongs to this asin or sku"

So a row identifies its listing by EITHER a SKU or an ASIN, and carries the
supplier link. Everything else about the row is optional.

WHY EITHER KEY, AND WHY THAT IS NOT AMBIGUOUS
A SKU names exactly one listing. An ASIN can name several -- the same product
relisted, or one ASIN carrying two of your SKUs -- so an ASIN row attaches the
supplier to every SKU that sits on it, and says how many that was. Silently
picking one would attach a real supplier to a listing nobody meant, and the
repricer would then price a listing from a cost that is not its own.

CLAUDE.md Rule 1 applies to the column: the ASIN in a generated SKU is the
COMPETITOR's, used to identify which of OUR listings was built from it. It is
never treated as our own ASIN, and nothing here writes it to Amazon.

WHAT IT REFUSES, AND WHY IT SAYS SO PER ROW
A bulk import that reports only a total is how twelve silently-skipped rows
become "the repricer is not working". Every row comes back with what happened
to it: attached, already had one, no such listing, or a link nothing can read.
The link itself is judged by domain/source_link.classify -- the same rule that
refuses an Amazon page as a supplier, so a sheet cannot introduce something the
automatic path would reject.

Nothing here enrols anything into LIVE pricing. Tracking is not pricing (see
the Repricer screen): a SKU added by sheet is in dry run like any other.
"""
import csv
import io
import re

from domain import source_link as _link
from domain import source_repo as _repo

# What a column might be called. Matched loosely -- a person's sheet says
# "Seller SKU", "sku", "SKU " or "Item SKU", and refusing all but one spelling
# is a way of making a working file look broken.
_SKU_COLS = ("sku", "seller sku", "sellersku", "seller-sku", "item sku",
             "merchant sku", "our sku")
_ASIN_COLS = ("asin", "competitor asin", "original asin", "amazon asin",
              "parent asin", "competitor_asin")
_URL_COLS = ("url", "link", "source", "source url", "source link", "supplier",
             "supplier url", "supplier link", "ebay", "ebay url", "ebay link")

_ASIN_RE = re.compile(r"\b(B0[A-Z0-9]{8})\b", re.I)


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").strip().lower()).strip()


def _pick(headers, wanted):
    """The index of the first column whose name looks like one of `wanted`."""
    norm = [_norm(h) for h in headers]
    for w in wanted:
        if w in norm:
            return norm.index(w)
    # A looser pass, so "eBay Source Link" still finds the url column.
    for i, h in enumerate(norm):
        for w in wanted:
            if w and w in h:
                return i
    return -1


def read_table(data, filename=""):
    """(headers, rows) from an uploaded CSV or spreadsheet. Never raises."""
    name = str(filename or "").lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            ws = wb[wb.sheetnames[0]]
            rows = [[("" if c is None else str(c)) for c in r]
                    for r in ws.iter_rows(values_only=True)]
            wb.close()
        except Exception as e:
            return [], [], ("that spreadsheet could not be read (%s). Save it as "
                            "CSV and try again." % str(e)[:80])
    else:
        try:
            txt = data.decode("utf-8-sig", "replace")
        except Exception:
            txt = str(data)
        try:
            dialect = csv.Sniffer().sniff(txt[:4000], delimiters=",;\t")
        except Exception:
            dialect = csv.excel
        rows = [r for r in csv.reader(io.StringIO(txt), dialect)]
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return [], [], "that file has no rows in it"
    return rows[0], rows[1:], ""


def _sku_exists(config_path, workspace_id, marketplace, sku):
    """Does this account actually have that SKU -- as a listing, on Amazon, or
    already being tracked?

    Three places because a SKU can legitimately be in any of them: a draft this
    app made, something Amazon returned that has no draft here, or one already
    enrolled in the repricer (re-uploading a sheet must not orphan those).
    """
    from data import db as _db
    s = str(sku or "").strip()
    if not s:
        return False
    try:
        conn = _db.get_db(config_path)
        r = conn.execute("SELECT 1 FROM listings WHERE workspace_id=? AND "
                         "UPPER(sku)=UPPER(?) LIMIT 1", (workspace_id, s)).fetchone()
        if r:
            return True
    except Exception:
        pass
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, workspace_id, marketplace) or {}
        want = s.upper()
        for it in (rec.get("items") or []):
            if str(it.get("sku") or "").strip().upper() == want:
                return True
    except Exception:
        pass
    try:
        for row in _repo.enrolled(config_path, workspace_id, marketplace):
            if str(row.get("sku") or "").strip().upper() == s.upper():
                return True
    except Exception:
        pass
    return False


def skus_for_key(config_path, workspace_id, marketplace, sku="", asin=""):
    """Which of OUR SKUs a row is talking about.

    A SKU is taken as given. An ASIN is resolved to every SKU that sits on it --
    from the live catalogue Amazon returned, and from the competitor ASIN the
    generator wrote into the SKU itself.
    """
    from data import db as _db
    sku = str(sku or "").strip()
    if sku:
        # A TYPED SKU IS STILL CHECKED. Taking it on trust meant a typo -- or a
        # SKU from another account's sheet -- created an enrolment for a listing
        # that does not exist, which then sat in the repricer for ever reporting
        # that it could not be read. Caught by the upload test: a row keyed
        # "NO-SUCH-SKU-123" was attached without complaint.
        return [sku] if _sku_exists(config_path, workspace_id, marketplace, sku) else []
    a = str(asin or "").strip().upper()
    if not a:
        return []
    found, seen = [], set()

    # 1. Our own listings, by the competitor ASIN they were built from.
    try:
        conn = _db.get_db(config_path)
        for r in conn.execute(
                "SELECT sku FROM listings WHERE workspace_id=? AND "
                "UPPER(IFNULL(competitor_asin,''))=? AND IFNULL(sku,'')<>''",
                (workspace_id, a)):
            s = str(r["sku"]).strip()
            if s and s.upper() not in seen:
                seen.add(s.upper())
                found.append(s)
    except Exception:
        pass

    # 2. The live catalogue, where the ASIN is OURS on Amazon.
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, workspace_id, marketplace) or {}
        for it in (rec.get("items") or []):
            if str(it.get("asin") or "").strip().upper() != a:
                continue
            s = str(it.get("sku") or "").strip()
            if s and s.upper() not in seen:
                seen.add(s.upper())
                found.append(s)
    except Exception:
        pass
    return found


def apply_rows(config_path, workspace_id, marketplace, headers, rows):
    """Attach every row's supplier. Returns a report, per row.

    Never raises: one malformed line must not lose the rest of the file.
    """
    i_sku = _pick(headers, _SKU_COLS)
    i_asin = _pick(headers, _ASIN_COLS)
    i_url = _pick(headers, _URL_COLS)

    out = {"ok": True, "attached": 0, "already": 0, "skipped": 0,
           "tracked": 0, "rows": [],
           "columns": {"sku": (headers[i_sku] if i_sku >= 0 else ""),
                       "asin": (headers[i_asin] if i_asin >= 0 else ""),
                       "url": (headers[i_url] if i_url >= 0 else "")}}
    if i_url < 0:
        out["ok"] = False
        out["error"] = ("no supplier link column found. Name one of the columns "
                        "'url', 'link', 'source' or 'supplier'.")
        return out
    if i_sku < 0 and i_asin < 0:
        out["ok"] = False
        out["error"] = ("no SKU or ASIN column found. Name a column 'sku' or "
                        "'asin' so each link can be matched to a listing.")
        return out

    def cell(r, i):
        return str(r[i]).strip() if (0 <= i < len(r)) else ""

    for n, r in enumerate(rows, start=2):        # row 1 is the header
        sku = cell(r, i_sku)
        asin = cell(r, i_asin)
        url = cell(r, i_url)
        rep = {"line": n, "sku": sku, "asin": asin, "url": url,
               "status": "", "note": ""}
        if not url:
            # An ASIN typed into the url column is a common slip; say so rather
            # than "no link".
            rep["status"] = "skipped"
            rep["note"] = "no supplier link on this row"
            out["skipped"] += 1
            out["rows"].append(rep)
            continue
        # An ASIN can be pasted anywhere in an Amazon URL; pull it out.
        if not asin and not sku:
            m = _ASIN_RE.search(url)
            if m:
                asin = m.group(1)
        kind, why = _link.classify(url)
        if not kind:
            rep["status"] = "skipped"
            rep["note"] = why
            out["skipped"] += 1
            out["rows"].append(rep)
            continue

        targets = skus_for_key(config_path, workspace_id, marketplace,
                               sku=sku, asin=asin)
        if not targets:
            rep["status"] = "skipped"
            rep["note"] = ("no listing in this account matches %s"
                           % (("SKU " + sku) if sku else ("ASIN " + asin)))
            out["skipped"] += 1
            out["rows"].append(rep)
            continue

        done = []
        for s in targets:
            try:
                _repo.enrol(config_path, workspace_id, marketplace, s, mode="dry_run")
                out["tracked"] += 1
                _sid, created = _repo.ensure_source(
                    config_path, workspace_id, marketplace, s, url,
                    kind=kind, label=url)
                if created:
                    out["attached"] += 1
                    done.append(s + " ✓")
                else:
                    out["already"] += 1
                    done.append(s + " (already had it)")
            except Exception as e:
                out["skipped"] += 1
                done.append("%s failed: %s" % (s, str(e)[:60]))
        rep["status"] = "attached"
        rep["matched"] = targets
        # An ASIN carrying more than one SKU is worth saying out loud: the same
        # supplier now prices both, and that is only right if it really is the
        # same product.
        rep["note"] = ("; ".join(done)
                       + ("  — this ASIN carries %d of your SKUs" % len(targets)
                          if len(targets) > 1 else ""))
        out["rows"].append(rep)
    return out
