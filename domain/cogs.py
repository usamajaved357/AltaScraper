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

    # EVERY SKU THAT NEEDS A COST, not just the ones in the catalogue snapshot.
    #
    # This listed the snapshot and nothing else, and the snapshot is not the same
    # thing as "what this account sells". Measured on selvora_limited, 17 Aug 2026:
    # the snapshot holds 7 SKUs while the account has taken orders on 4, two of
    # which are NOT in it -- OO-96JX-Z7ND with 52 orders and 1,757.97 of revenue,
    # and one other. So the two products earning nearly all of that account's money
    # could not be given a cost AT ALL: they were not on the sheet, so there was no
    # row to type one into, so no profit could ever be shown for them. The person
    # fills in the sheet, uploads it, and the orders still say profit unknown --
    # which is exactly the report that led here.
    #
    # So three sources, unioned:
    #   the catalogue snapshot   what Amazon says is listed
    #   order_lines              what has actually SOLD -- the ones that matter
    #   the repricer enrolment   what is being tracked, so a cost can be set
    #                            before the first sale rather than after it
    #
    # `where from` says which, so a SKU appearing that the person does not
    # recognise explains itself instead of looking like a bug.
    seen, entries = {}, []
    # HOW MUCH MONEY EACH SKU HAS TAKEN, used only for ordering the sheet. The
    # biggest revenue with no cost is the biggest hole in the profit figures, so
    # it belongs on the first line rather than wherever the alphabet puts it.
    revenue = {}

    def add(sku, asin, title, origin, strong=False):
        """Add a SKU once. `strong` overwrites a weaker reason for it being here.

        A SKU is usually in the snapshot AND in the orders. The snapshot is added
        first, so without this the row for AltaboltaVoo Ceiling Fan -- 20 orders
        on nestwell_goods and no cost -- read "listed on Amazon" and sorted below
        products nobody has ever bought. Having SOLD is the fact that decides how
        urgent a missing cost is, so it wins.
        """
        s = str(sku or "").strip()
        if not s:
            return
        k = s.upper()
        if k in seen:
            if strong:
                i = seen[k]
                old = entries[i]
                entries[i] = (old[0], old[1] or str(asin or ""),
                              old[2] or str(title or ""), origin)
            return
        seen[k] = len(entries)
        entries.append((s, str(asin or ""), str(title or ""), origin))

    for it in (rec.get("items") or []):
        add(it.get("sku"), it.get("asin"), it.get("title"), "listed on Amazon")

    # SOLD. Ordered by how much money the SKU has taken, so the biggest hole in
    # the profit figures is the first row anyone sees.
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        for r in conn.execute(
                "SELECT sku, MAX(asin) asin, MAX(title) title, "
                "       COUNT(*) n, SUM(IFNULL(revenue,0)) rev "
                "FROM order_lines WHERE workspace_id=? AND IFNULL(sku,'')<>'' "
                "GROUP BY sku ORDER BY rev DESC", (account_id,)):
            add(r["sku"], r["asin"], r["title"],
                "SOLD %d time%s" % (r["n"], "" if r["n"] == 1 else "s"),
                strong=True)
            try:
                revenue[str(r["sku"]).strip().upper()] = float(r["rev"] or 0)
            except (TypeError, ValueError):
                pass
    except Exception:
        pass

    # TRACKED by the repricer but never sold and not in the snapshot.
    try:
        from domain import source_repo as _repo
        for row in _repo.enrolled(config_path, account_id, marketplace):
            add(row.get("sku"), "", "", "tracked by the repricer")
    except Exception:
        pass

    out = []
    for sku, asin, title, origin in entries:
        cost, src = resolve(overrides, account_id, sku)
        got = _cat.look(idx, sku)
        out.append([sku,
                    got.get("asin") or asin,
                    got.get("title") or title,
                    "",                                  # the column to fill in
                    ("" if cost is None else "%.2f" % float(cost)),
                    # WHERE THE COST COMES FROM, and where the ROW comes from.
                    # Both matter: "not known -- SOLD 52 times" is the line that
                    # tells someone which gap is costing them.
                    "%s%s" % ({"manual": "you set it",
                               "sku": "read from the SKU name"}
                              .get(src, "not known"),
                              " -- %s" % origin if origin else "")])
    # ROWS WITH NO COST FIRST -- they are the job. Within those, the ones that
    # have SOLD, biggest earner first, because an unknown cost on a product
    # nobody has bought costs nothing today and an unknown cost on the SKU that
    # took 1,757.97 is the reason the profit figures are wrong.
    out.sort(key=lambda r: (bool(r[4]),
                            "SOLD" not in (r[5] or ""),
                            -revenue.get(str(r[0]).strip().upper(), 0.0),
                            (r[2] or "").lower(), r[0]))
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

    out = {"ok": True, "set": 0, "skipped": 0, "unmatched": 0,
           "unknown_sku": 0, "rows": [],
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
    known_skus = set()
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace) or {}
        for it in (rec.get("items") or []):
            a = str(it.get("asin") or "").strip().upper()
            s = str(it.get("sku") or "").strip()
            if s:
                known_skus.add(s)
            if a and s:
                by_asin.setdefault(a, []).append(s)
    except Exception:
        by_asin = {}

    # ...AND THE SKUS THAT HAVE ACTUALLY SOLD. The catalogue snapshot leaves out
    # SKUs an account really sells -- an inactive listing, a marketplace whose
    # snapshot has not been pulled -- so judging a typed SKU on the snapshot
    # alone would call a real SKU a typo. Order lines are the second half of the
    # same question and they are already local.
    try:
        from data import db as _db
        for row in _db.get_db(config_path).execute(
                "SELECT DISTINCT sku FROM order_lines WHERE workspace_id=?",
                (str(account_id or ""),)):
            s = str(row[0] or "").strip()
            if s:
                known_skus.add(s)
    except Exception:
        pass

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
        # A TYPED SKU IS STILL SET, AND STILL NAMED. "a hand-typed SKU is one
        # that silently matches nothing" -- so a cost against a SKU this account
        # has never listed and never sold is stored (the snapshot is not the
        # whole truth, and refusing it would lose a real cost) but counted and
        # reported, so a file of typos does not look like a file of costs.
        strange = bool(sku) and known_skus and sku not in known_skus
        rec_row = {"row": n, "sku": ", ".join(targets),
                   "status": "set", "detail": "%.2f" % cost}
        if strange:
            out["unknown_sku"] = out.get("unknown_sku", 0) + 1
            rec_row["unknown_sku"] = True
            rec_row["detail"] += " — no listing or order on this account uses "\
                                 "that SKU"
        out["rows"].append(rec_row)
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
