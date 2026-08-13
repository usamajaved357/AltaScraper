"""domain/sales_data.py -- the Sales dashboard's numbers.

WHERE THEY COME FROM
One SP-API report: GET_SALES_AND_TRAFFIC_REPORT, asked for with dateGranularity
DAY and asinGranularity CHILD. It returns sales AND traffic together -- units,
orders, revenue, sessions, page views, buy box, conversion -- per day and per
ASIN, in a single JSON document. Most of the dashboard is that one call.

WHAT IS NOT HERE
Ad spend, ACOS and ROAS. Those are the Amazon ADVERTISING API, which is a
different API with its own authorisation, and this app is not connected to it.
ads_daily exists and is read by the same code path; it is simply empty until
either a Sponsored Products report is uploaded or the API is connected. The
dashboard says "not connected" rather than showing a zero, because a zero is a
claim that there was no ad spend.

AMAZON'S LAG IS REAL
Sales for today never exist, and yesterday is often incomplete. Every reply
carries the range that genuinely has data, so the dashboard can draw "no data
yet" instead of a column of zeros that reads as "you sold nothing".
"""
import json
import time

from data import db as _db

REPORT_TYPE = "GET_SALES_AND_TRAFFIC_REPORT"

# The stored columns, and how to read them out of Amazon's JSON. Kept as one
# table rather than scattered through the parser so adding a metric is one line
# and cannot be half-added.
#   (column, salesByAsin/salesByDate key path, traffic key path)
_SALES_KEYS = [
    ("units",             ("unitsOrdered",)),
    ("units_b2b",         ("unitsOrderedB2B",)),
    ("order_items",       ("totalOrderItems",)),
    ("ordered_sales",     ("orderedProductSales", "amount")),
    ("ordered_sales_b2b", ("orderedProductSalesB2B", "amount")),
    ("avg_selling_price", ("averageSellingPrice", "amount")),
]
_TRAFFIC_KEYS = [
    ("sessions",         ("sessions",)),
    ("sessions_mobile",  ("mobileAppSessions",)),
    ("sessions_browser", ("browserSessions",)),
    ("page_views",       ("pageViews",)),
    ("buy_box_pct",      ("buyBoxPercentage",)),
    ("unit_session_pct", ("unitSessionPercentage",)),
]


def _dig(d, path):
    cur = d or {}
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def parse_report(doc):
    """Amazon's JSON -> rows ready for sales_daily.

    Handles both blocks the report contains: salesAndTrafficByDate (the account
    total for each day) and salesAndTrafficByAsin (the per-ASIN breakdown). The
    ASIN block has no date of its own when the report covers a range, so a
    single-day request is made per day -- see fetch_range.
    """
    rows = []
    if not isinstance(doc, dict):
        return rows

    currency = ""
    for block in (doc.get("salesAndTrafficByDate") or []):
        s = block.get("salesByDate") or {}
        t = block.get("trafficByDate") or {}
        currency = currency or (_dig(s, ("orderedProductSales", "currencyCode")) or "")
        row = {"date": str(block.get("date") or "")[:10], "asin": "*",
               "currency": currency}
        for col, path in _SALES_KEYS:
            row[col] = _dig(s, path)
        for col, path in _TRAFFIC_KEYS:
            row[col] = _dig(t, path)
        # Amazon reports order ITEMS by date; distinct orders are not in this
        # report. Recording items and naming the column honestly beats inventing
        # an "orders" number the report does not contain.
        row["orders"] = row.get("order_items")
        if row["date"]:
            rows.append(row)

    for block in (doc.get("salesAndTrafficByAsin") or []):
        s = block.get("salesByAsin") or {}
        t = block.get("trafficByAsin") or {}
        row = {"date": str(block.get("date") or doc.get("_date") or "")[:10],
               "asin": str(block.get("parentAsin") or block.get("childAsin") or "") or "?",
               "currency": currency}
        for col, path in _SALES_KEYS:
            row[col] = _dig(s, path)
        for col, path in _TRAFFIC_KEYS:
            row[col] = _dig(t, path)
        row["orders"] = row.get("order_items")
        if row["date"] and row["asin"] != "?":
            rows.append(row)
    return rows


_COLS = ["units", "units_b2b", "orders", "order_items", "ordered_sales",
         "ordered_sales_b2b", "sessions", "sessions_mobile", "sessions_browser",
         "page_views", "buy_box_pct", "unit_session_pct", "avg_selling_price",
         "currency"]


def store(config_path, workspace_id, marketplace, rows):
    """Upsert. Returns how many rows were written.

    Re-fetching a day REPLACES it: Amazon revises recent days as returns and
    cancellations settle, and keeping the first answer would freeze a number that
    Amazon itself no longer agrees with.
    """
    if not rows:
        return 0
    conn = _db.get_db(config_path)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for r in rows:
        vals = [r.get(c) for c in _COLS]
        conn.execute(
            "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, %s, fetched_at) "
            "VALUES (?,?,?,?,%s,?) "
            "ON CONFLICT(workspace_id, marketplace, date, asin) DO UPDATE SET %s, fetched_at=excluded.fetched_at"
            % (", ".join(_COLS), ",".join("?" * len(_COLS)),
               ", ".join("%s=excluded.%s" % (c, c) for c in _COLS)),
            [workspace_id, marketplace, r["date"], r.get("asin", "*")] + vals + [now])
        n += 1
    conn.commit()
    _refresh_availability(conn, workspace_id, marketplace, "sales")
    return n


def _refresh_availability(conn, workspace_id, marketplace, source):
    table = "sales_daily" if source == "sales" else "ads_daily"
    r = conn.execute(
        "SELECT MIN(date) a, MAX(date) b, COUNT(DISTINCT date) n FROM %s "
        "WHERE workspace_id=? AND marketplace=?" % table,
        (workspace_id, marketplace)).fetchone()
    conn.execute(
        "INSERT INTO data_availability (workspace_id, marketplace, source, first_date, "
        "last_date, days, fetched_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id, marketplace, source) DO UPDATE SET "
        "first_date=excluded.first_date, last_date=excluded.last_date, "
        "days=excluded.days, fetched_at=excluded.fetched_at",
        (workspace_id, marketplace, source, r["a"], r["b"], r["n"] or 0,
         time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()


def availability(config_path, workspace_id, marketplace):
    """What dates genuinely have data, asked BEFORE anything requests data."""
    conn = _db.get_db(config_path)
    out = {}
    for src in ("sales", "ads"):
        r = conn.execute(
            "SELECT first_date, last_date, days, fetched_at FROM data_availability "
            "WHERE workspace_id=? AND marketplace=? AND source=?",
            (workspace_id, marketplace, src)).fetchone()
        out[src] = (dict(r) if r else
                    {"first_date": None, "last_date": None, "days": 0, "fetched_at": None})
    out["ads"]["connected"] = bool(out["ads"]["days"])
    out["ads"]["note"] = ("" if out["ads"]["days"] else
                          "Ad data needs the Amazon Advertising API, which is not "
                          "connected. Upload a Sponsored Products report, or connect "
                          "the API, and these fill in.")
    return out


def series(config_path, workspace_id, marketplace, start, end, asin=None):
    """Daily rows for a range. asin=None means the account total ('*')."""
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT * FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=? ORDER BY date",
        (workspace_id, marketplace, start, end, asin or "*")).fetchall()
    sales = [dict(r) for r in rows]
    ads = {r["date"]: dict(r) for r in conn.execute(
        "SELECT * FROM ads_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, asin or "*")).fetchall()}
    for s in sales:
        a = ads.get(s["date"]) or {}
        for k in ("impressions", "clicks", "spend", "ad_orders", "ad_sales"):
            s[k] = a.get(k)
    return sales


def totals(config_path, workspace_id, marketplace, start, end, asin=None):
    """Summed metrics for a range, plus the derived ones.

    Rates are recomputed from the totals, never averaged from the daily rates:
    the mean of thirty conversion rates is not the period's conversion rate, and
    the difference grows with how uneven the days are.
    """
    rows = series(config_path, workspace_id, marketplace, start, end, asin)
    out = {"days": len(rows), "currency": (rows[0]["currency"] if rows else "")}
    for k in ("units", "orders", "order_items", "sessions", "page_views",
              "ordered_sales", "spend", "ad_sales", "clicks", "impressions"):
        vals = [r.get(k) for r in rows if r.get(k) is not None]
        out[k] = round(sum(vals), 2) if vals else None
    out["unit_session_pct"] = _pct(out["units"], out["sessions"])
    out["avg_selling_price"] = _div(out["ordered_sales"], out["units"])
    out["acos"] = _pct(out["spend"], out["ad_sales"])
    out["roas"] = _div(out["ad_sales"], out["spend"])
    out["tacos"] = _pct(out["spend"], out["ordered_sales"])
    # Buy box is a share of page views, so it is weighted by them -- a flat mean
    # would let a day with four views count as much as a day with four thousand.
    out["buy_box_pct"] = _weighted(rows, "buy_box_pct", "page_views")
    return out


def _div(a, b):
    try:
        return round(float(a) / float(b), 2) if a is not None and b else None
    except Exception:
        return None


def _pct(a, b):
    v = _div(a, b)
    return round(v * 100, 2) if v is not None else None


def _weighted(rows, field, weight):
    num = den = 0.0
    for r in rows:
        v, w = r.get(field), r.get(weight)
        if v is None or not w:
            continue
        num += float(v) * float(w)
        den += float(w)
    return round(num / den, 2) if den else None
