"""domain/live_reconcile.py -- the Orders API is the truth for what sold.

WHY THIS EXISTS
Amazon publishes the same trade twice, and the two do not arrive together:

    Orders API              within minutes, dated by when the order was PLACED
    Sales & Traffic report  a day or more later, dated the same way

This app read the report and used the Orders API only to patch days the report
had sent nothing -- and then only in the browser, for the five cards. The stored
series that the charts, the P&L grid and the CSV export all read had nothing.

MEASURED on nestwell_goods, 2026-08-16:

    date         report        Orders API
    2026-08-13   nothing       89.97   3 units   2 orders
    2026-08-14   nothing       74.97   3 units   3 orders
    2026-08-15   nothing        8.49   1 unit    1 order
    -------------------------------------------------------
    TOTAL        149.95        323.38

The screen showed 149.95. The business had taken 323.38. Not a rounding
difference -- 54% of the money was missing, because the report is three days
behind and nothing wrote the live figures anywhere the screen could see them.

THE RULE, WHICH IS ORBIT'S: the Orders API wins for orders, units and sales.
    "Orders API wins for top-line because it's realtime order-date basis. If
     Business Report says orderedProductSales = $1,000 and Orders API sums to
     $1,050 for same day, dashboard shows Orders API figure for Sales."

The report is still fetched and still authoritative for everything it uniquely
has -- sessions, page views, buy box, conversion. Those cannot come from
anywhere else. This only takes over the three columns that describe what sold.

AND IT COUNTS ORDERS PROPERLY. The report has no distinct-order count at all, so
`orders` was filled with the count of order ITEMS -- a two-item order counted as
two. This counts distinct AmazonOrderIds, which is what a person means.

WHAT IT DOES NOT DO
Touch a day the Orders API cannot speak for. Amazon's Orders API only goes back
so far, and a window that reaches beyond it must keep the report's answer rather
than be overwritten with a zero. A day with no orders inside the live window IS
written as zero -- that is a real answer, and the difference between the two
cases is the whole reason `since` is respected.
"""
import datetime as _dt

from data import db as _db

SOURCE = "orders_api"


def figures_by_day(marketplace, marketplace_id, creds, days=14,
                   price_cache=None, include_shipping=True):
    """{date: {orders, units, ordered_sales, currency}} from the Orders API.

    Counted the way a person counts: one order is one order however many things
    were in it, units is what was actually bought, and sales is what the buyer
    paid for the goods plus the postage they paid to have them sent.
    """
    from domain import orders_live as _ol

    days = max(1, min(int(days or 1), 30))
    res = _ol.by_day(marketplace, marketplace_id, creds, days=days,
                     price_cache=price_cache, include_shipping=include_shipping)
    out = {}
    for date, v in (res.get("days") or {}).items():
        out[date] = {
            "orders": int(v.get("orders") or 0),
            "units": int(v.get("units") or 0),
            "ordered_sales": round(float(v.get("revenue") or 0.0), 2),
            "product_sales": round(float(v.get("product_sales") or 0.0), 2),
            "shipping": round(float(v.get("shipping") or 0.0), 2),
            "currency": res.get("currency") or "",
        }
    return out, res.get("since"), res


def reconcile(config_path, workspace_id, marketplace, marketplace_id, creds,
              days=14, price_cache=None, include_shipping=True):
    """Write the live truth into sales_daily for every day it can speak for.

    Only the account-wide row (asin='*') is written. Per-ASIN rows stay with the
    report: the Orders API can give them, but at one call per order, and the
    per-product screen is not the one being read wrong.
    """
    by_day, since, raw = figures_by_day(
        marketplace, marketplace_id, creds, days=days,
        price_cache=price_cache, include_shipping=include_shipping)

    # EVERY DAY INSIDE THE LIVE WINDOW, not only the days with orders. A quiet
    # day is a real zero and has to be written as one, or a day the report
    # wrongly shows as busy would never be corrected downwards.
    try:
        first = _dt.date.fromisoformat(str(since)[:10])
    except Exception:
        first = _dt.date.today() - _dt.timedelta(days=days - 1)
    today = _dt.date.today()

    conn = _db.get_db(config_path)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    written = changed = 0
    diffs = []

    d = first
    while d <= today:
        ds = d.isoformat()
        v = by_day.get(ds) or {"orders": 0, "units": 0, "ordered_sales": 0.0,
                               "currency": raw.get("currency") or ""}
        was = conn.execute(
            "SELECT orders, units, ordered_sales FROM sales_daily "
            "WHERE workspace_id=? AND marketplace=? AND date=? AND asin='*'",
            (workspace_id, marketplace, ds)).fetchone()

        if was is not None:
            before = (was["orders"], was["units"], was["ordered_sales"])
            after = (v["orders"], v["units"], v["ordered_sales"])
            if before != after:
                changed += 1
                diffs.append({"date": ds,
                              "was": {"orders": was["orders"], "units": was["units"],
                                      "ordered_sales": was["ordered_sales"]},
                              "now": {"orders": v["orders"], "units": v["units"],
                                      "ordered_sales": v["ordered_sales"]}})

        conn.execute(
            "INSERT INTO sales_daily (workspace_id, marketplace, date, asin,"
            " orders, units, ordered_sales, currency, orders_source, fetched_at) "
            "VALUES (?,?,?,'*',?,?,?,?,?,?) "
            "ON CONFLICT(workspace_id, marketplace, date, asin) DO UPDATE SET "
            "  orders=excluded.orders, units=excluded.units,"
            "  ordered_sales=excluded.ordered_sales,"
            "  currency=COALESCE(NULLIF(excluded.currency,''), sales_daily.currency),"
            "  orders_source=excluded.orders_source,"
            "  fetched_at=excluded.fetched_at",
            (workspace_id, marketplace, ds, v["orders"], v["units"],
             v["ordered_sales"], v.get("currency") or "", SOURCE, now))
        written += 1
        d += _dt.timedelta(days=1)

    conn.commit()
    try:
        from domain import sales_data as _sd
        _sd._refresh_availability(conn, workspace_id, marketplace, "sales")
    except Exception:
        pass

    return {"days_written": written, "days_changed": changed,
            "since": since, "changes": diffs[:30],
            "truncated": bool(raw.get("truncated"))}


# What from_lines() has already derived, so a read does not rewrite figures that
# cannot have changed. Keyed by account, marketplace and window; the value is
# (how many order lines there were, the newest fetched_at among them) -- both,
# because a re-fetch that corrects a line in place moves the second without
# moving the first, and a deletion moves the first without moving the second.
_DERIVED = {}


def forget_derived():
    """Drop that memory. For tests, and for anything that edits order_lines
    behind this module's back."""
    _DERIVED.clear()


def from_lines(config_path, workspace_id, marketplace, start, end):
    """Write sales_daily's order-side figures from order_lines.

    WHY THIS EXISTS, when reconcile() above already writes them.

    reconcile() reads the Orders API for a recent window -- fourteen days -- and
    writes what it finds. order_lines holds far more: ninety days, because a fee
    settling today can belong to an order from seventy days ago and would
    otherwise have nowhere to be reported.

    So on any window longer than a fortnight the two disagreed, and the P&L had
    a money side covering more days than its sales side. Measured on
    selvora_limited over thirty days: 2861.33 charged against 1241.13 of sales,
    with fifteen days of settled money against eight days of sales. More than
    double, and it looks exactly like a data fault because it is one.

    Both now come from the SAME rows. order_lines is filled from the Orders API
    one order at a time, so it is the same measurement -- there is simply more
    of it, and this makes the sales side reach as far as the money side does.

    Days with no orders are written as real zeros, so a day the report wrongly
    shows as busy is corrected downwards rather than left alone.

    BUT ONLY WHERE THE ORDER HISTORY ACTUALLY REACHES.

    A zero here means "the Orders API says nothing happened". Before the first
    order this app ever fetched, it means "we were not looking", and those are
    opposite claims. Writing zeros across the gap turned a year-to-date request
    into an instruction to erase every month the order history does not cover:
    the Sales & Traffic report's own figures for those days were overwritten
    with zeros, and year-to-date then read exactly the same as ninety days
    because everything before it had been flattened.

    So the window is clamped to the first day order_lines has for this account
    and marketplace. Earlier days are left exactly as the report delivered them.
    """
    conn = _db.get_db(config_path)
    dead = ("canceled", "cancelled")
    # WHERE THE EVIDENCE BEGINS. No history at all means nothing here can be
    # said about any day, so nothing is written -- rather than every day in the
    # window being asserted as a zero on the strength of an empty table.
    edge = conn.execute(
        "SELECT MIN(substr(purchase_date,1,10)) AS lo, COUNT(*) AS n, "
        "       MAX(COALESCE(fetched_at,'')) AS seen FROM order_lines "
        "WHERE workspace_id=? AND marketplace=?",
        (workspace_id, marketplace)).fetchone()
    stamp = (edge["n"], edge["seen"]) if edge else (0, "")
    edge = edge["lo"] if edge else None
    if not edge:
        return {"days_written": 0, "days_with_orders": 0, "no_history": True}

    # NOT REWRITTEN WHEN NOTHING HAS CHANGED.
    #
    # This is called by sales_data.series(), which is a READ -- every load of
    # the Sales screen, and every click on a period pill. So a screen that only
    # looks at figures was rewriting a month of them each time, as a WRITER.
    #
    # The database is in WAL, so readers never block; two writers do. The
    # background refresher writes constantly just after start-up, and the first
    # Sales screen opened then had to queue behind it -- measured at 20 to 39
    # seconds against a busy_timeout of 30, whichever account was opened first.
    # Every account opened afterwards was under a second.
    #
    # Re-deriving from unchanged rows produces byte-identical figures, so if no
    # order line has arrived or been re-fetched since the last pass over this
    # same window there is nothing to write and no reason to become a writer.
    memo = "%s::%s::%s::%s" % (workspace_id, marketplace, start, end)
    if _DERIVED.get(memo) == stamp:
        return {"days_written": 0, "days_with_orders": 0, "unchanged": True,
                "history_starts": edge}
    rows = conn.execute(
        "SELECT substr(purchase_date,1,10) AS d, "
        "       COUNT(DISTINCT order_id) AS orders, "
        "       SUM(units) AS units, "
        "       SUM(revenue + COALESCE(shipping,0)) AS sales, "
        "       MAX(currency) AS cur "
        "FROM order_lines "
        "WHERE workspace_id=? AND marketplace=? "
        "  AND lower(COALESCE(status,'')) NOT IN (?,?) "
        "  AND substr(purchase_date,1,10) >= ? "
        "  AND substr(purchase_date,1,10) <= ? "
        "GROUP BY d",
        (workspace_id, marketplace, dead[0], dead[1], str(start), str(end))
    ).fetchall()
    have = {r["d"]: r for r in rows}

    first = _dt.date.fromisoformat(str(start)[:10])
    last = _dt.date.fromisoformat(str(end)[:10])
    # Clamped, per the note above: never claim a zero for a day this app has no
    # order history for.
    first = max(first, _dt.date.fromisoformat(edge))
    if first > last:
        return {"days_written": 0, "days_with_orders": 0,
                "before_history": True, "history_starts": edge}
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    written = 0
    d = first
    while d <= last:
        ds = d.isoformat()
        r = have.get(ds)
        conn.execute(
            "INSERT INTO sales_daily (workspace_id, marketplace, date, asin,"
            " orders, units, ordered_sales, currency, orders_source, fetched_at) "
            "VALUES (?,?,?,'*',?,?,?,?,?,?) "
            "ON CONFLICT(workspace_id, marketplace, date, asin) DO UPDATE SET "
            "  orders=excluded.orders, units=excluded.units,"
            "  ordered_sales=excluded.ordered_sales,"
            "  currency=COALESCE(NULLIF(excluded.currency,''), sales_daily.currency),"
            "  orders_source=excluded.orders_source,"
            "  fetched_at=excluded.fetched_at",
            (workspace_id, marketplace, ds,
             int(r["orders"]) if r else 0,
             int(r["units"] or 0) if r else 0,
             round(float(r["sales"] or 0), 2) if r else 0.0,
             (r["cur"] if r else "") or "", SOURCE, now))
        written += 1
        d += _dt.timedelta(days=1)
    conn.commit()
    # Recorded only AFTER the write succeeded, so a failure part-way through is
    # retried rather than remembered as done.
    _DERIVED[memo] = stamp
    try:
        from domain import sales_data as _sd
        _sd._refresh_availability(conn, workspace_id, marketplace, "sales")
    except Exception:
        pass
    return {"days_written": written, "days_with_orders": len(have),
            "history_starts": edge}


def owned_days(config_path, workspace_id, marketplace, start, end):
    """The dates in a range whose figures came from the Orders API.

    So the report's own writer can leave those three columns alone, and so a
    screen can say which days are live and which are the report's.
    """
    conn = _db.get_db(config_path)
    return {r["date"] for r in conn.execute(
        "SELECT date FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "AND asin='*' AND date>=? AND date<=? AND orders_source=?",
        (workspace_id, marketplace, str(start), str(end), SOURCE)).fetchall()}
