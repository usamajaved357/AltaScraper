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
        # The CHILD asin is the key, not the parent. With asinGranularity CHILD
        # every block carries BOTH, and preferring the parent files every
        # variation of a product under one key -- which the unique index then
        # collapses, so a parent with five children keeps only the last one's
        # numbers and loses the other four silently. The parent is kept in its
        # own column so variations can still be grouped.
        row = {"date": str(block.get("date") or doc.get("_date") or "")[:10],
               "asin": str(block.get("childAsin") or block.get("parentAsin") or "") or "?",
               "parent_asin": str(block.get("parentAsin") or ""),
               "currency": currency}
        for col, path in _SALES_KEYS:
            row[col] = _dig(s, path)
        for col, path in _TRAFFIC_KEYS:
            row[col] = _dig(t, path)
        row["orders"] = row.get("order_items")
        if row["date"] and row["asin"] != "?":
            rows.append(row)
    return rows


_COLS = ["parent_asin", "units", "units_b2b", "orders", "order_items",
         "ordered_sales", "ordered_sales_b2b", "sessions", "sessions_mobile",
         "sessions_browser", "page_views", "buy_box_pct", "unit_session_pct",
         "avg_selling_price", "currency"]


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


def products(config_path, workspace_id, marketplace, start, end):
    """The ASINs that actually sold in a range, biggest first.

    Read from sales_daily rather than the live catalogue, because this list only
    has to contain what the filter can usefully select. An ASIN with no sales in
    the period filters to an empty screen, and a catalogue-driven list is also
    empty until someone has synced the catalogue -- which has nothing to do with
    looking at sales.
    """
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT asin, MAX(parent_asin) parent_asin, "
        "       SUM(COALESCE(units,0)) units, SUM(COALESCE(ordered_sales,0)) revenue "
        "FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "  AND date>=? AND date<=? AND asin<>'*' "
        "GROUP BY asin ORDER BY revenue DESC, units DESC, asin",
        (workspace_id, marketplace, start, end)).fetchall()
    return [dict(r) for r in rows]


# =============================================================================
# HOW EACH METRIC AGGREGATES -- the single definition, used by every caller.
#
# This table is the reason the grid, the stat cards and the CSV cannot disagree.
# It previously existed twice, once here and once in the route, and the two had
# already drifted: the route SUMMED average selling price, so a 30-day column
# read about thirty times the real price. A metric is defined once, here, or it
# will be defined twice and one of them will be wrong (CLAUDE.md Rule 12).
#
#   sum       -- add the values up (units, revenue, sessions)
#   ratio     -- divide one total by another (price = revenue / units)
#   rate      -- the same, as a percentage (conversion = units / sessions)
#   weighted  -- a share, weighted by the thing it is a share OF
#
#   (key, label, kind, good, how)
# `good` says which direction is an improvement, so a rise in ACOS or ad spend
# is never coloured as a win.
# =============================================================================
METRICS = [
    ("ordered_sales",     "Ordered product sales", "money", "up",   ("sum",)),
    ("units",             "Units ordered",         "count", "up",   ("sum",)),
    ("orders",            "Order items",           "count", "up",   ("sum",)),
    ("avg_selling_price", "Average selling price", "money", "up",   ("ratio", "ordered_sales", "units")),
    ("sessions",          "Sessions",              "count", "up",   ("sum",)),
    ("sessions_mobile",   "Sessions — mobile",     "count", "up",   ("sum",)),
    ("sessions_browser",  "Sessions — browser",    "count", "up",   ("sum",)),
    ("page_views",        "Page views",            "count", "up",   ("sum",)),
    ("unit_session_pct",  "Conversion rate",       "pct",   "up",   ("rate", "units", "sessions")),
    ("buy_box_pct",       "Buy box",               "pct",   "up",   ("weighted", "page_views")),
    ("units_b2b",         "Units — B2B",           "count", "up",   ("sum",)),
    ("ordered_sales_b2b", "Sales — B2B",           "money", "up",   ("sum",)),
    ("impressions",       "Ad impressions",        "count", "up",   ("sum",)),
    ("clicks",            "Ad clicks",             "count", "up",   ("sum",)),
    ("spend",             "Ad spend",              "money", "down", ("sum",)),
    ("ad_sales",          "Ad sales",              "money", "up",   ("sum",)),
    ("ad_orders",         "Ad orders",             "count", "up",   ("sum",)),
    ("acos",              "ACOS",                  "pct",   "down", ("rate", "spend", "ad_sales")),
    ("roas",              "ROAS",                  "count", "up",   ("ratio", "ad_sales", "spend")),
    ("tacos",             "TACOS",                 "pct",   "down", ("rate", "spend", "ordered_sales")),
]

_AGG = {m[0]: m[4] for m in METRICS}
METRIC_KEYS = [m[0] for m in METRICS]


def aggregate(rows, key):
    """One metric over many rows, by that metric's OWN rule.

    Rates and prices are recomputed from their parts, never averaged from the
    daily figures: the mean of thirty conversion rates is not the period's
    conversion rate, and the gap grows the more uneven the days are.
    """
    how = _AGG.get(key, ("sum",))
    if how[0] == "ratio":
        return _div(_sum(rows, how[1]), _sum(rows, how[2]))
    if how[0] == "rate":
        return _pct(_sum(rows, how[1]), _sum(rows, how[2]))
    if how[0] == "weighted":
        return _weighted(rows, key, how[1])
    return _sum(rows, key)


def bucket(rows, gran):
    """Group daily rows into day, week (Mon-start) or month. Returns (map, order)."""
    import datetime as _dt
    buckets, order = {}, []
    for r in rows:
        d = r["date"]
        if gran == "week":
            dt = _dt.datetime.strptime(d, "%Y-%m-%d").date()
            key = (dt - _dt.timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
        elif gran == "month":
            key = d[:7]
        else:
            key = d
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(r)
    return buckets, order


def totals(config_path, workspace_id, marketplace, start, end, asin=None):
    """Every metric over a range, each by its own aggregation rule."""
    rows = series(config_path, workspace_id, marketplace, start, end, asin)
    out = {"days": len(rows), "currency": (rows[0]["currency"] if rows else "")}
    for key in METRIC_KEYS:
        out[key] = aggregate(rows, key)
    out["order_items"] = aggregate(rows, "order_items")
    return out


def _sum(rows, key):
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    return round(sum(float(v) for v in vals), 2) if vals else None


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
