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


_FIN_COLS = ("referral_fees", "fba_fees", "other_fees", "refunds", "refund_units",
             "refund_fees_returned", "reimbursements", "promos", "principal",
             "tax", "refund_tax", "units_shipped", "cogs", "cogs_units")


# ---- VAT -------------------------------------------------------------------
# Two arrangements, and telling them apart decides whether every profit figure in
# the app is right or a fifth too high.
#
#   Amazon sent a Tax line ALONGSIDE principal
#       -> principal is the EX-VAT price. Revenue is already net; the tax was
#          collected on top and is owed onward. Nothing to subtract.
#   No tax line, and the account is VAT-registered
#       -> principal is what the buyer paid, VAT inside it. It must come out:
#          vat = gross * rate / (1 + rate).  NOT gross * rate, which is the
#          classic error and understates the VAT by a fifth of itself.
#   No tax line, no rate configured
#       -> we do not know. The figure is shown, and the screen says it may be
#          overstated, because silence here reads as "no VAT applies".

VAT_FROM_AMAZON = "amazon"      # Amazon itemised it; revenue already net
VAT_DERIVED     = "derived"     # we took it out of a gross principal
VAT_UNKNOWN     = "unknown"     # no tax line and no rate set
VAT_NONE        = "none"        # not VAT-registered; nothing to take out


def vat_for(row, vat_rate=None):
    """(vat, net_revenue, basis) for one row. Never invents a number."""
    gross = float((row or {}).get("principal") or 0.0)
    tax = (row or {}).get("tax")
    # `is not None`, NOT truthiness. A stored 0.00 means "we read Amazon's tax
    # lines and they came to zero"; NULL means "this row predates us capturing
    # tax at all". Treating a legitimate zero as absent falls through to the
    # derived branch and subtracts VAT from a principal that is ALREADY net of
    # it -- deducting it twice, on exactly the zero-rated days.
    #
    # Measured on the live UK account 14 Aug 2026 (probe_finance.py): Amazon
    # sends Tax as its own ChargeType, 80.47 against 402.39 of Principal, which
    # is 20.0% ON TOP. So Principal is the VAT-EXCLUSIVE price and there is
    # nothing to take out of it.
    if tax is not None:
        return round(float(tax), 2), round(gross, 2), VAT_FROM_AMAZON
    if vat_rate in (None, "", 0, 0.0):
        # A rate of 0 is a real answer -- not registered -- but None is not.
        return ((0.0, round(gross, 2), VAT_NONE) if vat_rate == 0
                else (None, round(gross, 2), VAT_UNKNOWN))
    try:
        r = float(vat_rate)
    except (TypeError, ValueError):
        return None, round(gross, 2), VAT_UNKNOWN
    if r <= 0 or r >= 1:
        return None, round(gross, 2), VAT_UNKNOWN
    vat = round(gross * r / (1.0 + r), 2)
    return vat, round(gross - vat, 2), VAT_DERIVED


def vat_rate_for(config, workspace_id):
    """The account's VAT rate, or None if nobody has said.

    Per ACCOUNT, not per marketplace: VAT registration is a fact about the
    business, and two accounts selling on the same marketplace can differ.
    """
    cfg = config() if callable(config) else (config or {})
    for a in (cfg.get("accounts") or []):
        if str(a.get("id")) == str(workspace_id):
            v = a.get("vat_rate", None)
            return None if v in (None, "") else float(v)
    return None


def series(config_path, workspace_id, marketplace, start, end, asin=None,
           vat_rate=None):
    """Daily rows for a range, sales joined with ads and finance.

    The dates come from the UNION of the three sources, not from sales alone. A
    refund posts on the day the money went back, which can easily be a day with
    no sales of its own -- keying off sales would drop that refund entirely and
    quietly overstate what you kept.
    """
    conn = _db.get_db(config_path)
    key = asin or "*"
    sales = {r["date"]: dict(r) for r in conn.execute(
        "SELECT * FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, key)).fetchall()}
    ads = {r["date"]: dict(r) for r in conn.execute(
        "SELECT * FROM ads_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=?",
        (workspace_id, marketplace, start, end, key)).fetchall()}
    from domain import finance_data as _fd
    fin = _fd.series(config_path, workspace_id, marketplace, start, end, key)

    out = []
    for d in sorted(set(sales) | set(ads) | set(fin)):
        row = dict(sales.get(d) or {"date": d, "asin": key, "currency": ""})
        row["date"] = d
        a = ads.get(d) or {}
        for k in ("impressions", "clicks", "spend", "ad_orders", "ad_sales"):
            row[k] = a.get(k)
        f = fin.get(d) or {}
        for k in _FIN_COLS:
            row[k] = f.get(k)
        # finance_daily.units is units SHIPPED (money basis); sales_daily.units is
        # units ORDERED (order-date basis). Same word, different measurements, and
        # letting one land on the other would silently replace one with the other.
        row["units_shipped"] = f.get("units")
        if not row.get("currency"):
            row["currency"] = f.get("currency") or ""
        # Derived per DAY as well as per bucket, because a bucket that sums
        # already-derived days would be summing ratios. These two are additive,
        # so summing them is safe; the rates below are recomputed instead.
        fees = [row.get(k) for k in ("referral_fees", "fba_fees", "other_fees")]
        fees = [float(x) for x in fees if x is not None]
        row["total_fees"] = round(sum(fees), 2) if fees else None
        if row["total_fees"] is not None or row.get("refunds") is not None:
            # PRINCIPAL, not ordered_sales. Both are revenue, but they are dated
            # differently -- ordered_sales by order date, principal by the date
            # the money moved, which is the same basis as the fees and refunds
            # below. Mixing the two produces a figure that is neither: on a live
            # UK account it read 246.53 when the money-basis answer was 281.52,
            # and nothing on screen could have shown which was meant.
            gross = float(row.get("principal") or 0.0)
            # VAT comes out FIRST. It was never yours -- you collected it and you
            # owe it onward -- so leaving it in overstates everything downstream.
            _v, _net_rev, _basis = vat_for(row, vat_rate)
            row["vat"] = _v
            row["vat_basis"] = _basis
            row["net_revenue"] = _net_rev
            row["net_proceeds"] = round(
                _net_rev - float(row.get("total_fees") or 0.0)
                         - float(row.get("refunds") or 0.0)
                         - float(row.get("promos") or 0.0)
                         + float(row.get("refund_fees_returned") or 0.0)
                         + float(row.get("reimbursements") or 0.0), 2)
        else:
            row["net_proceeds"] = None
            row["vat"] = None
            row["net_revenue"] = None
            row["vat_basis"] = ""

        # PROFIT -- only when the cost of every unit shipped that day is known.
        #
        # A partial cost is not a small error, it is a number in the wrong
        # direction: the units missing a cost contribute revenue and no cost, so
        # profit comes out HIGH, and it comes out high exactly on the products
        # nobody has costed. Better to say nothing for that day and show the
        # coverage than to publish a figure that flatters.
        u, cu = row.get("units_shipped"), row.get("cogs_units")
        if row["net_proceeds"] is not None and u and cu == u:
            row["profit"] = round(row["net_proceeds"] - float(row.get("cogs") or 0.0), 2)
            p = float(row.get("principal") or 0.0)
            row["margin_pct"] = round(row["profit"] / p * 100, 2) if p else None
        else:
            row["profit"] = None
            row["margin_pct"] = None
        out.append(row)
    return out


def breakdown(config_path, workspace_id, marketplace, start, end, group="asin"):
    """Sales per product for a range, optionally rolled up to the PARENT.

    group='asin'   -> one row per child ASIN, which is the thing that sells
    group='parent' -> variations grouped, so a parent with five children reads as
                      one product rather than five unrelated ones

    parent_asin has been stored on every row since the sales report was first
    parsed and has never been shown anywhere. A t-shirt in six sizes looked like
    six weak products instead of one strong one, which is the opposite of the
    conclusion the numbers support.
    """
    conn = _db.get_db(config_path)
    # COALESCE, not parent_asin alone: a product with no variations has an empty
    # parent, and grouping on that would collapse every standalone product in the
    # account into a single nameless row.
    key = ("CASE WHEN COALESCE(parent_asin,'')<>'' THEN parent_asin ELSE asin END"
           if group == "parent" else "asin")
    rows = conn.execute(
        "SELECT %s k, MAX(COALESCE(parent_asin,'')) parent_asin, "
        "  COUNT(DISTINCT asin) children, "
        "  SUM(COALESCE(units,0)) units, SUM(COALESCE(ordered_sales,0)) revenue, "
        "  SUM(COALESCE(sessions,0)) sessions, SUM(COALESCE(page_views,0)) page_views, "
        "  SUM(COALESCE(order_items,0)) orders, MAX(currency) currency "
        "FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "  AND date>=? AND date<=? AND asin<>'*' "
        "GROUP BY k ORDER BY revenue DESC, units DESC, k" % key,
        (workspace_id, marketplace, start, end)).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        u, s = d["units"] or 0, d["sessions"] or 0
        # Recomputed from the totals, never averaged from the daily rates: the
        # mean of seven daily conversion rates is not the week's conversion rate,
        # and the gap widens the more the daily traffic varies.
        d["conversion"] = round(u / s * 100, 2) if s else None
        d["avg_price"] = round((d["revenue"] or 0) / u, 2) if u else None
        out.append(d)
    return out


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
    # ---- from the Finances API: what Amazon took and what went back ---------
    ("referral_fees",     "Referral fees",         "money", "down", ("sum",)),
    ("fba_fees",          "FBA fees",              "money", "down", ("sum",)),
    ("other_fees",        "Other fees",            "money", "down", ("sum",)),
    ("total_fees",        "Amazon fees",           "money", "down", ("sum",)),
    # Over PRINCIPAL, not ordered_sales: fees are dated when the money moved and
    # ordered_sales when the order was placed, so dividing one by the other gives
    # a rate for no period at all. On live data that read 70% when the true share
    # of what buyers were charged was 18%.
    ("fee_rate",          "Fees as % of charged",  "pct",   "down", ("rate", "total_fees", "principal")),
    ("refunds",           "Refunds",               "money", "down", ("sum",)),
    ("refund_units",      "Units refunded",        "count", "down", ("sum",)),
    ("refund_rate",       "Refund rate",           "pct",   "down", ("rate", "refund_units", "units")),
    ("promos",            "Promotions funded",     "money", "down", ("sum",)),
    ("reimbursements",    "Reimbursements",        "money", "up",   ("sum",)),
    # What is left after Amazon's cut, refunds and funded discounts. NOT profit:
    # it is before cost of goods, and calling it profit would be a wrong number
    # dressed as a right one.
    ("principal",         "Charged to buyers",     "money", "up",   ("sum",)),
    # VAT out first: it was collected, not earned. net_revenue is what is left.
    ("vat",               "VAT",                   "money", "down", ("sum",)),
    ("net_revenue",       "Revenue after VAT",     "money", "up",   ("sum",)),
    ("net_proceeds",      "Net proceeds",          "money", "up",   ("sum",)),
    # ---- cost of goods, from the cost written into each generated SKU -------
    ("units_shipped",     "Units shipped",         "count", "up",   ("sum",)),
    ("cogs",              "Cost of goods",         "money", "down", ("sum",)),
    # Profit and margin are recomputed from the parts, and are None for any
    # bucket containing a unit whose cost is unknown -- see profit_for() below.
    ("profit",            "Profit",                "money", "up",   ("profit",)),
    ("margin_pct",        "Margin",                "pct",   "up",   ("margin",)),
]

_AGG = {m[0]: m[4] for m in METRICS}
METRIC_KEYS = [m[0] for m in METRICS]

# =============================================================================
# WHICH SECTION OF THE GRID EACH METRIC BELONGS TO.
#
# "the p&l heatmap has spacing in it to separate data and make it easy to
# understand visually". Measured on Orbit: its grid is not one long list of
# thirty-three rows. It is six SECTIONS, each introduced by a header row --
# 24px tall on rgb(45,50,66), against 29px transparent for a data row:
#
#     SALES & REVENUE   ORGANIC   PPC   COSTS & DEDUCTIONS   TRAFFIC   DERIVED
#
# That banding is the whole difference between a grid you can scan and a wall of
# numbers: "is my advertising working" is answered by four adjacent rows rather
# than by four rows scattered through thirty.
#
# Declared HERE, beside the metrics themselves, because a metric's section is a
# fact about the metric. Kept as a separate table rather than a seventh element
# of each tuple so that nothing already unpacking those five positions breaks.
#
# Order matters: the grid draws the sections in this order and the metrics
# within each section in METRICS order. Anything not listed falls into "Other",
# which is how a newly added metric appears at all rather than vanishing.
METRIC_SECTIONS = [
    ("Sales & revenue", [
        "ordered_sales", "net_revenue", "principal", "profit", "margin_pct",
        "orders", "units", "units_shipped", "avg_selling_price",
        "ordered_sales_b2b", "units_b2b",
    ]),
    ("PPC", [
        "ad_sales", "spend", "ad_orders", "acos", "tacos", "roas",
        "impressions", "clicks",
    ]),
    ("Costs & deductions", [
        "total_fees", "referral_fees", "fba_fees", "other_fees", "fee_rate",
        "cogs", "vat", "refunds", "refund_units", "refund_rate", "promos",
        "reimbursements", "net_proceeds",
    ]),
    ("Traffic", [
        "sessions", "sessions_mobile", "sessions_browser", "page_views",
        "unit_session_pct", "buy_box_pct",
    ]),
]

# key -> section name, for the renderer.
METRIC_SECTION_OF = {k: name for name, keys in METRIC_SECTIONS for k in keys}


def sections_for(keys):
    """[(section, [key, ...]), ...] for the keys actually present, in order.

    Empty sections are dropped: a heading over nothing is worse than no heading,
    and which metrics arrive depends on which Amazon feeds have answered.
    """
    have = set(keys or [])
    out = []
    for name, wanted in METRIC_SECTIONS:
        got = [k for k in wanted if k in have]
        if got:
            out.append((name, got))
    placed = {k for _, got in out for k in got}
    rest = [k for k in (keys or []) if k not in placed]
    if rest:
        out.append(("Other", rest))
    return out


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
    if how[0] == "profit":
        return profit_for(rows)
    if how[0] == "margin":
        p, charged = profit_for(rows), _sum(rows, "principal")
        return _pct(p, charged) if p is not None else None
    return _sum(rows, key)


def profit_for(rows):
    """Profit across rows, or None if ANY unit in them has no known cost.

    Not the sum of the daily profits: a week containing one uncosted day would
    then report the other six days' profit as the week's, which is a smaller
    number presented as a complete one. Recomputed from the parts, and withheld
    entirely unless every unit in the bucket is costed -- because a partial cost
    of goods only ever makes profit look BETTER than it is.
    """
    units = _sum(rows, "units_shipped")
    costed = _sum(rows, "cogs_units")
    if not units or costed != units:
        return None
    net = _sum(rows, "net_proceeds")
    if net is None:
        return None
    return round(net - float(_sum(rows, "cogs") or 0.0), 2)


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


def totals(config_path, workspace_id, marketplace, start, end, asin=None,
           vat_rate=None):
    """Every metric over a range, each by its own aggregation rule."""
    rows = series(config_path, workspace_id, marketplace, start, end, asin, vat_rate)
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
