"""domain/cogs.py -- what the stock cost, resolved in ONE place.

WHERE COST COMES FROM
These SKUs are built by the generator as {source_cost}_{N}Days_{COMPETITOR_ASIN}
-- see build_sku() in amazon_listing_generator.py, which formats the first field
from source_cost. So the cost of goods is already written on every SKU the
generator made, and does not need entering again.

Two things about that are easy to get wrong and both produce a confident wrong
number:

  * 0.00 MEANS UNKNOWN, NOT FREE. build_sku writes "0.00" when it had no cost to
    write. Treating that as a zero cost makes an item look infinitely
    profitable, which is precisely the item someone would then order more of.

  * THE ASIN IN THE SKU IS THE COMPETITOR'S, NOT OURS. CLAUDE.md Rule 1. It is a
    reference used at generation time. It must never be used to identify our own
    listing, and nothing here does -- only the leading cost is read.

NOT EVERY SKU IS ONE OF OURS
Hand-made SKUs exist ("46 pcs wrench", "cleaning brush_11GBP"). On the live
account 85 of 107 SKUs carry a readable cost and 22 do not. Those 22 have NO
cost, not a zero cost, and every figure derived from them has to say so rather
than quietly assuming.

WHY THIS FILE EXISTS AT ALL
_cogs_from_sku and _resolve_cogs already lived in dashboard.py and are used by
the listings screen. The sales dashboard needs the same answer. A second copy
would have drifted the first time either changed (CLAUDE.md Rule 12), so the
originals were MOVED here and dashboard.py now calls these. Behaviour is
unchanged -- same parse, same override precedence.
"""


def cost_from_sku(sku):
    """The source cost written into a generated SKU, or None.

    Deliberately the same permissive parse dashboard.py has always used: take
    everything before the first underscore and see if it is a number. Anything
    that is not -- a hand-typed SKU, a name -- has no cost, and 0.00 is treated
    as no cost rather than as free.
    """
    try:
        first = str(sku).split("_", 1)[0]
        v = float(first)
        if v > 0:
            return v
    except Exception:
        pass
    return None


def resolve(overrides, account_id, sku):
    """(cost, source) for one SKU. source is 'manual', 'sku', or ''.

    A manual override always wins: someone typed it because the SKU was wrong or
    absent, and a parsed number must never quietly overrule a person.
    """
    key = "%s::%s" % (account_id, sku)
    if overrides and key in overrides:
        try:
            return float(overrides[key]), "manual"
        except (TypeError, ValueError):
            pass
    c = cost_from_sku(sku)
    if c is not None:
        return c, "sku"
    return None, ""


def lookup(overrides, account_id):
    """A one-argument cost function for callers that only have a SKU.

    Returns f(sku) -> (cost_or_None, source), so the finance parser can price
    each shipment line without knowing anything about where costs come from.
    """
    def _f(sku):
        return resolve(overrides, account_id, sku)
    return _f


# The cost sheet's columns, and what a cost column might be called in a sheet
# that did not come from here. "cost" first, so the template's own empty column
# is preferred over its read-only "cost now" beside it.
TEMPLATE_HEADERS = ["sku", "asin", "product", "cost", "cost now", "where from"]
COST_COLS = ("cost", "cogs", "unit cost", "buy price", "source price",
             "source cost", "supplier price", "price paid")


def template_rows(config_path, account_id, marketplace, overrides=None,
                  catalogue=None):
    """The cost sheet to hand someone, already filled in with what we know.

    There was a COGS CSV UPLOAD and no template. So the columns had to be
    guessed, every SKU typed by hand, and a SKU typed by hand is one that
    silently matches nothing -- the upload's own error for that case is "No
    matchable rows (check sku/asin values match your listings)", which is the
    app telling you it cannot read what it asked you to write.

    THE COLUMN TO FILL IS `cost`, AND IT ARRIVES EMPTY -- even where a cost is
    already known. That is deliberate and it is the opposite of the supplier-link
    sheet, which arrives pre-filled:

        A supplier link is a fact about the world. Showing the current one and
        letting it come back unchanged is right, because unchanged means "still
        this supplier".

        A cost is a MANUAL OVERRIDE. Pre-filling it and reading it back would
        turn every cost the app had worked out from the SKU name into a typed-in
        override -- silently, for the whole catalogue, on one upload of a file
        nobody edited. Overrides win over everything, so that is unrecoverable
        without knowing which were which.

    So `cost now` and `where from` are there to READ -- what the app currently
    uses and whether it came from the SKU name or from a previous override --
    and `cost` is there to WRITE. A row left blank changes nothing.

    Rows with no known cost come first: those are the ones there is a job to do
    in, and burying them under two hundred that are already covered is how they
    get missed.
    """
    from domain import catalogue as _cat
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace) or {}
    except Exception:
        rec = {}
    idx = catalogue if catalogue is not None else {}
    out = []
    for it in (rec.get("items") or []):
        sku = str(it.get("sku") or "").strip()
        if not sku:
            continue
        cost, src = resolve(overrides, account_id, sku)
        got = _cat.look(idx, sku)
        out.append([sku,
                    got.get("asin") or str(it.get("asin") or ""),
                    got.get("title") or str(it.get("title") or ""),
                    "",                                  # the column to fill in
                    ("" if cost is None else "%.2f" % float(cost)),
                    {"manual": "you set it", "sku": "read from the SKU name"}
                        .get(src, "not known")])
    out.sort(key=lambda r: (bool(r[4]), (r[2] or "").lower(), r[0]))
    return out


def apply_sheet(config_path, account_id, marketplace, headers, rows):
    """Read an uploaded cost sheet. Returns a report, per row. Never raises.

    WHY THIS IS SERVER-SIDE. It was done in the browser by splitting each line on
    commas -- which is not what a CSV is. A product name like "Grill, Large" is
    quoted and contains a comma, so every column after it shifted by one and the
    cost column was read out of the wrong place. The cost sheet this app now
    hands out is FULL of product names with commas in them, so that would have
    been the normal case rather than an edge one.

    domain/source_bulk.read_table already parses CSV properly -- quoting,
    delimiters, the byte-order mark -- and spreadsheets as well, which the
    browser version could not do at all. One reader (Rule 12).

    A row with no cost is SKIPPED, not zeroed. The template is handed out with
    the cost column empty on every row, so "blank" is the normal state of a row
    nobody has touched, and writing 0.00 for those would set the entire
    catalogue's cost to nothing on the first upload of an unedited file.
    """
    from domain import sheets as _sheets
    from domain import source_bulk as _sb

    i_sku = _sheets.pick(headers, _sb._SKU_COLS)
    i_asin = _sheets.pick(headers, _sb._ASIN_COLS)
    i_cost = _sheets.pick(headers, COST_COLS)

    out = {"ok": True, "set": 0, "skipped": 0, "unmatched": 0, "rows": [],
           "columns": {"sku": (headers[i_sku] if i_sku >= 0 else ""),
                       "asin": (headers[i_asin] if i_asin >= 0 else ""),
                       "cost": (headers[i_cost] if i_cost >= 0 else "")}}
    if i_cost < 0:
        out["ok"] = False
        out["error"] = ("no cost column found. Name one of the columns 'cost' "
                        "or 'cogs'. Download the cost sheet and it is already "
                        "named correctly.")
        return out
    if i_sku < 0 and i_asin < 0:
        out["ok"] = False
        out["error"] = ("no SKU or ASIN column found. Name a column 'sku' or "
                        "'asin' so each cost can be matched to a listing.")
        return out

    # ASIN -> SKUs, from the catalogue, so an ASIN row can be used at all. Built
    # once rather than per row.
    by_asin = {}
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace) or {}
        for it in (rec.get("items") or []):
            a = str(it.get("asin") or "").strip().upper()
            s = str(it.get("sku") or "").strip()
            if a and s:
                by_asin.setdefault(a, []).append(s)
    except Exception:
        by_asin = {}

    def cell(r, i):
        return str(r[i]).strip() if (0 <= i < len(r)) else ""

    updates = {}
    for n, r in enumerate(rows, start=2):          # row 1 is the header
        sku = cell(r, i_sku)
        asin = cell(r, i_asin).upper()
        raw = cell(r, i_cost)
        if not raw:
            out["skipped"] += 1
            continue
        # A currency symbol, a thousands comma, a stray space -- all things a
        # person's sheet really contains. Refusing them would be refusing the
        # file for being written by a human.
        clean = raw.replace(",", "").strip()
        for sym in ("£", "$", "€", "GBP", "USD", "EUR"):
            clean = clean.replace(sym, "")
        try:
            cost = float(clean.strip())
        except (TypeError, ValueError):
            out["rows"].append({"row": n, "sku": sku or asin,
                                "status": "not a number",
                                "detail": "could not read %r as a cost" % raw})
            continue
        if cost < 0:
            out["rows"].append({"row": n, "sku": sku or asin,
                                "status": "refused",
                                "detail": "a cost cannot be negative"})
            continue
        targets = [sku] if sku else by_asin.get(asin, [])
        if not targets:
            out["unmatched"] += 1
            out["rows"].append({"row": n, "sku": sku or asin,
                                "status": "no such listing",
                                "detail": ("nothing on this account matches %s"
                                           % (sku or asin or "(blank)"))})
            continue
        for s in targets:
            updates[s] = cost
        out["rows"].append({"row": n, "sku": ", ".join(targets),
                            "status": "set", "detail": "%.2f" % cost})
        out["set"] += len(targets)
    out["updates"] = updates
    return out


def coverage(config_path, account_id, marketplace, overrides=None):
    """How much of this catalogue has a known cost. For telling the truth on screen.

    A profit figure covering four fifths of your SKUs is useful; the same figure
    presented as if it covered all of them is not. This is what lets the screen
    say which it is.
    """
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace) or {}
    except Exception:
        rec = {}
    known = unknown = 0
    missing = []
    for it in (rec.get("items") or []):
        sku = str(it.get("sku") or "").strip()
        if not sku:
            continue
        cost, _src = resolve(overrides, account_id, sku)
        if cost is None:
            unknown += 1
            if len(missing) < 50:
                missing.append(sku)
        else:
            known += 1
    total = known + unknown
    return {"known": known, "unknown": unknown, "total": total,
            "pct": (round(known / total * 100, 1) if total else None),
            "missing_skus": missing}
