"""domain/order_cogs_sheet.py -- set the cost of MANY orders from one file.

    "i will upload a sheet containing amazon order numbers and the source price
     on which this order was fulfilled. so the profits to me are shown according
     to these order cogs. give me a bulk upload button in the app, from where i
     can download the template and then fill back to update the cogs per order"

WHY PER ORDER, AND NOT PER PRODUCT
domain/cogs.py already sets a cost against a PRODUCT, and that cost applies to
every order of it, past and future. This is the other question: the same product
bought at 7.00 in July and 9.50 in August. A per-product cost cannot hold both,
and re-costing July with August's price is exactly what domain/order_cogs.py
exists to prevent.

So this writes onto the ORDER LINE, through order_cogs.set_for_order, which
marks it `manual-order` -- the top of the trust order, the one thing nothing
later overwrites. It is the bulk form of a correction the app can already make
one order at a time.

IT DOES NOT PARSE, AND IT DOES NOT WRITE
domain/source_bulk.read_table reads the file (CSV quoting, delimiters, the
byte-order mark, and real spreadsheets), domain/sheets.pick matches the columns,
and order_cogs.set_for_order does every write. This file only decides what a row
MEANS. Three borrowed pieces and no fourth opinion (CLAUDE.md Rule 12).

A BLANK COST IS NOT A ZERO COST
The template is handed out with the cost column empty on every row, so blank is
the normal state of a row nobody has filled in. Writing 0.00 for those would set
every order's cost to nothing on the first upload of an unedited file -- and a
zero cost makes an order look infinitely profitable, which is exactly the order
somebody would then read a strategy off. Blank rows are skipped and counted.

EVERY ROW IS REPORTED
Matched, skipped, unknown order, bad number -- each row comes back with what
happened to it. A bulk action that says "done" and silently drops a third of the
file is worse than one that refuses.
"""
from domain import cogs as _cogs
from domain import order_cogs as _oc

# What an order-number column might be called. Amazon writes "amazon-order-id"
# in its reports and "Order ID" on screen; a seller typing their own sheet
# writes "order". All three, plus the ones Seller Central exports use.
ORDER_COLS = ("order id", "order-id", "amazon order id", "amazon-order-id",
              "order", "order number", "order no", "amazonorderid")

# The template's own columns. `cost` is the one to fill in; the rest are there
# so the person filling it in can see WHICH order they are pricing.
TEMPLATE_HEADERS = ["order id", "date", "sku", "product", "units",
                    "revenue", "cost now", "where from", "cost"]


def template_rows(config_path, workspace_id, marketplace, start=None, end=None,
                  only_uncosted=False):
    """One row per order line, for the person to fill the cost in against.

    `cost` is deliberately LAST and deliberately EMPTY, and `cost now` beside it
    shows what the app currently believes, so filling the sheet in is a matter
    of correcting what is wrong rather than retyping what is already right.
    """
    from data import db as _db

    conn = _db.get_db(config_path)
    sql = ("SELECT order_id, purchase_date, sku, title, units, revenue, "
           "cogs, cogs_source FROM order_lines "
           "WHERE workspace_id=? AND marketplace=?")
    args = [workspace_id, marketplace]
    if start:
        sql += " AND purchase_date>=?"
        args.append(start)
    if end:
        sql += " AND purchase_date<=?"
        args.append(end + "T23:59:59")
    if only_uncosted:
        sql += " AND cogs IS NULL"
    sql += " ORDER BY purchase_date DESC, order_id"

    rows = []
    for r in conn.execute(sql, args):
        rows.append([
            r["order_id"] or "",
            str(r["purchase_date"] or "")[:10],
            r["sku"] or "",
            r["title"] or "",
            r["units"] if r["units"] is not None else "",
            r["revenue"] if r["revenue"] is not None else "",
            # What the app believes today, so an unchanged row can be left alone.
            "" if r["cogs"] is None else round(float(r["cogs"]), 2),
            _where_from(r["cogs_source"]),
            "",                       # the column to fill in
        ])
    return TEMPLATE_HEADERS, rows


def _where_from(src):
    """Plain English for a cogs_source, because the codes mean nothing on a sheet."""
    return {
        "manual-order": "you set it for this order",
        "manual": "you set it for this product",
        "tracked": "supplier price when it arrived",
        "sku": "read from the SKU",
    }.get(str(src or ""), "not costed")


def _num(v):
    """A cost, or None. Accepts what a spreadsheet actually produces.

    Currency symbols and thousands separators arrive because people paste from
    an invoice; a blank, a dash or the word "unknown" mean nobody filled it in.
    """
    s = str(v if v is not None else "").strip()
    if not s or s in ("-", "--", "?"):
        return None
    if s.lower() in ("unknown", "n/a", "na", "none"):
        return None
    s = s.replace(",", "")
    for sym in ("£", "$", "€", "¥", "GBP", "USD", "EUR"):
        s = s.replace(sym, "")
    s = s.strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def apply_sheet(config_path, workspace_id, marketplace, headers, rows):
    """Read a filled-in order-cost sheet and write the costs. -> a report.

    Never raises. Every row is accounted for.
    """
    from domain import sheets as _sheets

    i_order = _sheets.pick(headers, ORDER_COLS)
    # The same cost-column names the product sheet accepts, so one file can be
    # renamed and reused rather than being subtly different from the other one.
    i_cost = _sheets.pick(headers, _cogs.COST_COLS)
    i_sku = _sheets.pick(headers, ("sku", "seller sku", "merchant sku"))

    out = {"ok": True, "set": 0, "cleared": 0, "blank": 0, "unknown_order": 0,
           "bad_number": 0, "rows": [],
           "columns": {"order": (headers[i_order] if i_order >= 0 else ""),
                       "cost": (headers[i_cost] if i_cost >= 0 else ""),
                       "sku": (headers[i_sku] if i_sku >= 0 else "")}}
    if i_order < 0:
        out["ok"] = False
        out["error"] = ("no order-number column found. Name one of the columns "
                        "'order id'. Download the template and it is already "
                        "named correctly.")
        return out
    if i_cost < 0:
        out["ok"] = False
        out["error"] = ("no cost column found. Name one of the columns 'cost'. "
                        "Download the template and it is already named "
                        "correctly.")
        return out

    cell = lambda r, i: (str(r[i]).strip()
                         if 0 <= i < len(r) and r[i] is not None else "")

    for r in rows or []:
        oid = cell(r, i_order)
        raw = cell(r, i_cost)
        sku = cell(r, i_sku) if i_sku >= 0 else ""
        if not oid:
            continue
        if not raw:
            out["blank"] += 1
            continue
        cost = _num(raw)
        if cost is None:
            out["bad_number"] += 1
            out["rows"].append({"order_id": oid, "cost": raw,
                                "result": "not a number"})
            continue
        if cost < 0:
            out["bad_number"] += 1
            out["rows"].append({"order_id": oid, "cost": raw,
                                "result": "a cost cannot be negative"})
            continue
        # THE ONE WRITER. set_for_order marks it 'manual-order', which is the
        # top of the trust order in domain/order_cogs.resolve -- so a later
        # sync, a supplier price change or a re-freeze cannot overwrite it.
        n = _oc.set_for_order(config_path, workspace_id, marketplace, oid, cost,
                              sku or None)
        if not n:
            out["unknown_order"] += 1
            out["rows"].append({"order_id": oid, "cost": cost,
                                "result": ("no line in this account and "
                                           "marketplace matches that order"
                                           + (" and SKU" if sku else ""))})
            continue
        out["set"] += n
        out["rows"].append({"order_id": oid, "cost": cost, "lines": n,
                            "result": "set"})
    return out
