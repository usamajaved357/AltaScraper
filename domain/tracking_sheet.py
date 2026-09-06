"""domain/tracking_sheet.py -- the tracking numbers, in and out on one file.

    "i want the orders page to show tracking ids put in the account which have
     tracking ids uploaded and track them with the carrier and show me the
     status of the trackings"

WHY A SHEET AT ALL, WHEN AMAZON HAS THE NUMBERS

    "i have already uploaded the trackings of the fbm orders in seller central
     so dont ask me to provide the tracking of that order again in the app,
     check the tracking details from amazon"

IT WILL NOT GIVE THEM BACK. Asked again, properly, on an account that IS
authorised (nestwell_goods answered QuotaExceeded where the others answer
Unauthorized) across a window holding 54 real orders of which 49 were SHIPPED
merchant-fulfilled -- exactly the orders in question:

    getOrder                     OrderStatus and ship-by dates, no tracking
    getOrderItems                QuantityShipped, no tracking
    FLAT FILE All Orders         header read from Amazon: 33 columns, and not
                                 one names a carrier or a tracking number
    XML All Orders               the same report in XML DOES carry a
                                 <FulfillmentData> block -- and it holds only
                                 FulfillmentChannel, ShipServiceLevel and the
                                 delivery Address. The string "track" does not
                                 occur once in 73KB of it.
    MerchantFulfillment          get_shipment(id) reads back a label THIS app
                                 bought through the API. There is no call to
                                 LIST shipments, so a label bought anywhere else
                                 -- which is all of them -- cannot be found.

The XML report was the last real candidate and it is a definite no. Seller-
uploaded tracking is simply not exposed by SP-API.

SO THE FILE IS THE ROUTE -- AND IT IS THE SELLER'S EXISTING FILE, NOT A NEW ONE.
Confirming shipments in Seller Central leaves the seller holding Amazon's own
shipping-confirmation file, and this module accepts that file unedited:
`order-id`, `tracking-number` and the carrier all resolve straight out of it.
Answering "do not make me type it again" with "type it into our template
instead" would be the same request refused in a different hat.

So the numbers come from the seller, the same way the per-order costs do -- and
deliberately in the same SHAPE, because it is the same act: download a sheet with
the orders already listed, fill one column in, upload it back. Somebody who has
done the costs once already knows how to do this.

WHAT THIS FILE DOES AND DOES NOT DO
domain/source_bulk.read_table reads the file, domain/sheets.pick matches the
columns, domain/tracking.add does every write and owns the carrier mapping.
This file only decides what a row MEANS (Rule 12).

A BLANK TRACKING COLUMN IS NOT A DELETION.
The template hands out every order with the column empty, so blank is the normal
state of a row nobody has touched. Treating blank as "remove the tracking" would
wipe every number in the account on the first upload of an unedited file. Blank
rows are skipped and counted; removing a number is its own explicit act.

EVERY ROW IS REPORTED -- matched, blank, unknown order, or a number that is not
one. A bulk action that says "done" and silently drops a third of the file is
worse than one that refuses.
"""
from domain import tracking as _tr

# What an order-number column might be called. The same list the order-cost
# sheet accepts, borrowed rather than retyped, so one file can be renamed and
# reused instead of being subtly different from the other one.
from domain.order_cogs_sheet import ORDER_COLS

TRACKING_COLS = ("tracking", "tracking id", "tracking number", "tracking no",
                 "trackingid", "tracking-id", "tracking_number", "consignment",
                 "consignment number", "barcode", "parcel number")

CARRIER_COLS = ("carrier", "courier", "carrier name", "shipping carrier",
                "ship carrier", "carrier-name", "delivery company",
                # Amazon's own shipping-confirmation file, where this is the
                # column that is actually filled in.
                "carrier code", "carrier-code")


def _carrier_columns(headers):
    """Every column that could name a carrier, in the order to try them.

    Amazon's file has two and fills whichever suits the courier, so ONE index is
    not enough -- see the note in apply_sheet. Ordered so an explicit name beats
    a code, because when both are filled the name is the more specific of the
    two.
    """
    from domain import source_bulk as _sb

    norm = [_sb._norm(h) for h in (headers or [])]
    named, coded, loose = [], [], []
    for i, h in enumerate(norm):
        if not h:
            continue
        if h in ("carrier name", "carrier"):
            named.append(i)
        elif h in ("carrier code",):
            coded.append(i)
        elif any(w in h for w in ("carrier", "courier")):
            loose.append(i)
    return named + coded + loose

TEMPLATE_HEADERS = ["order id", "date", "sku", "product", "amazon says",
                    "carrier now", "tracking now", "carrier", "tracking"]


def template_rows(config_path, workspace_id, marketplace, start=None, end=None,
                  only_untracked=False):
    """One row per order, for the person to write the tracking against.

    `carrier` and `tracking` are LAST and EMPTY, with `carrier now` and
    `tracking now` beside them showing what the app already holds -- so the
    sheet is corrected rather than retyped, and a row that is already right can
    be left alone. That is what makes re-uploading an unedited file harmless.
    """
    from data import db as _db

    conn = _db.get_db(config_path)
    # ONE ROW PER ORDER, not per line. A parcel carries an order, not a line:
    # a two-line order posted in one box has one tracking number, and handing
    # out two rows for it invites the same number to be typed twice.
    sql = ("SELECT order_id, MIN(purchase_date) d, "
           "       GROUP_CONCAT(DISTINCT sku) skus, "
           "       MIN(title) title, SUM(units) units "
           "FROM order_lines WHERE workspace_id=? AND marketplace=?")
    args = [workspace_id, marketplace]
    if start:
        sql += " AND purchase_date>=?"
        args.append(start)
    if end:
        sql += " AND purchase_date<=?"
        args.append(end + "T23:59:59")
    sql += " GROUP BY order_id ORDER BY d DESC, order_id"

    orders = list(conn.execute(sql, args))
    have = _tr.for_orders(config_path, workspace_id, marketplace,
                          [r["order_id"] for r in orders])

    rows = []
    for r in orders:
        oid = r["order_id"] or ""
        got = have.get(oid) or []
        if only_untracked and got:
            continue
        rows.append([
            oid,
            str(r["d"] or "")[:10],
            r["skus"] or "",
            r["title"] or "",
            _amazon_says(r["units"]),
            # What the app already holds, so an unchanged row needs no typing.
            ", ".join(sorted({str(g.get("carrier") or "") for g in got
                              if g.get("carrier")})),
            ", ".join(g.get("tracking_number") or "" for g in got),
            "",                       # the carrier to fill in
            "",                       # the tracking number to fill in
        ])
    return TEMPLATE_HEADERS, rows


def _amazon_says(units):
    """Amazon's own shipment state for the sheet. Free, and already synced.

    Deliberately vague where the data is: order_lines records what was ordered,
    not what has left. The honest column says how many units the order is for,
    so the person filling the sheet in knows whether to expect one parcel or
    several -- rather than a shipped/unshipped claim this table cannot support.
    """
    try:
        n = int(units or 0)
    except (TypeError, ValueError):
        return ""
    return "%d unit%s ordered" % (n, "" if n == 1 else "s")


def looks_like_tracking(s):
    """Is this plausibly a tracking number, or has a column been misread?

    Not a validation of any carrier's format -- there are dozens and they change
    -- but a guard against the common upload accident: a date, a price or a
    product name landing in the tracking column because a sheet was rearranged.
    A number that is really only three characters long is a mistake, and letting
    it through means asking a carrier about nonsense and showing "not found"
    forever without ever saying why.
    """
    s = str(s or "").strip()
    if len(s) < 6:
        return False
    # A tracking number is letters and digits, allowing the separators carriers
    # actually print. Spaces are common in Royal Mail's own emails.
    core = s.replace(" ", "").replace("-", "").replace("_", "")
    if not core.isalnum():
        return False
    return any(c.isdigit() for c in core)


def apply_sheet(config_path, workspace_id, marketplace, headers, rows):
    """Read a filled-in tracking sheet and record every number. -> a report.

    Never raises. Every row is accounted for.
    """
    from domain import sheets as _sheets

    i_order = _sheets.pick(headers, ORDER_COLS)
    i_track = _sheets.pick(headers, TRACKING_COLS)
    i_sku = _sheets.pick(headers, ("sku", "seller sku", "merchant sku"))

    # AMAZON'S OWN FILE PUTS THE CARRIER IN TWO COLUMNS, AND USUALLY FILLS THE
    # OTHER ONE.
    #
    # The shipping-confirmation file Seller Central issues has BOTH
    # `carrier-code` and `carrier-name`. carrier-code holds the carrier for
    # every courier Amazon knows -- "Royal Mail", "Evri", "DPD" -- and
    # carrier-name is filled only when carrier-code is "Other". So a matcher
    # that finds carrier-name and stops reads an empty cell on nearly every row.
    #
    # Measured on Amazon's real header: the carrier came back blank for every
    # order, and a tracking number with no carrier can never be checked with the
    # courier -- which is the entire point of storing it. The status would sit
    # at "unknown" for ever and the screen would look broken.
    #
    # So every carrier-ish column is collected and the first NON-EMPTY one on
    # each row wins, per row rather than per file: one file can legitimately
    # carry "Royal Mail" in the code column on one line and "Other" plus a real
    # name on the next.
    i_carriers = _carrier_columns(headers)
    i_carrier = i_carriers[0] if i_carriers else -1

    out = {"ok": True, "set": 0, "blank": 0, "unknown_order": 0,
           "bad_number": 0, "rows": [], "carriers": {},
           "columns": {"order": (headers[i_order] if i_order >= 0 else ""),
                       "tracking": (headers[i_track] if i_track >= 0 else ""),
                       # ALL of them, not the first: the value can come from any
                       # one of these per row, and naming only the first would
                       # tell somebody the carrier came from a column that was
                       # empty on every line.
                       "carrier": ", ".join(headers[i] for i in i_carriers
                                            if i < len(headers)),
                       "carrier_columns": [headers[i] for i in i_carriers
                                           if i < len(headers)]}}
    if i_order < 0:
        out["ok"] = False
        out["error"] = ("no order-number column found. Name one of the columns "
                        "'order id'. Download the template and it is already "
                        "named correctly.")
        return out
    if i_track < 0:
        out["ok"] = False
        out["error"] = ("no tracking column found. Name one of the columns "
                        "'tracking'. Download the template and it is already "
                        "named correctly.")
        return out

    # WHICH ORDERS THIS ACCOUNT ACTUALLY HAS. A tracking number recorded against
    # an order that is not here would sit in the table for ever, never shown on
    # any screen and never explained -- so it is reported back instead.
    from data import db as _db
    conn = _db.get_db(config_path)
    known = {r[0] for r in conn.execute(
        "SELECT DISTINCT order_id FROM order_lines WHERE workspace_id=? "
        "AND marketplace=?", (workspace_id, marketplace))}

    cell = lambda r, i: (str(r[i]).strip()
                         if 0 <= i < len(r) and r[i] is not None else "")

    for r in rows or []:
        oid = cell(r, i_order)
        tn = cell(r, i_track)
        # The first carrier column with something in it, on THIS row.
        carrier = ""
        for ci in i_carriers:
            v = cell(r, ci)
            # "Other" is Amazon's placeholder meaning "look in the next column",
            # not the name of a courier. Taking it would file every parcel under
            # a carrier that does not exist.
            if v and v.strip().lower() != "other":
                carrier = v
                break
        sku = cell(r, i_sku) if i_sku >= 0 else ""
        if not oid:
            continue
        if not tn:
            out["blank"] += 1
            continue
        if not looks_like_tracking(tn):
            out["bad_number"] += 1
            out["rows"].append({"order_id": oid, "tracking": tn,
                                "result": "that does not look like a tracking "
                                          "number — check the column"})
            continue
        if known and oid not in known:
            out["unknown_order"] += 1
            out["rows"].append({"order_id": oid, "tracking": tn,
                                "result": "no order of that number is stored "
                                          "for this account and marketplace"})
            continue
        # THE ONE WRITER. tracking.add owns the carrier mapping and the upsert,
        # so re-uploading a corrected sheet updates rather than duplicates.
        n = _tr.add(config_path, workspace_id, marketplace, oid, tn,
                    carrier=carrier, sku=sku, source="upload")
        if not n:
            out["bad_number"] += 1
            out["rows"].append({"order_id": oid, "tracking": tn,
                                "result": "could not be recorded"})
            continue
        out["set"] += n
        code = _tr.carrier_code(carrier)
        out["carriers"][code or "not stated"] = \
            out["carriers"].get(code or "not stated", 0) + 1
        out["rows"].append({"order_id": oid, "tracking": tn,
                            "carrier": carrier, "carrier_code": code,
                            "result": "recorded"})
    return out
