"""domain/sales_queries.py -- the Sales screen's direct questions to its tables.

Moved statement for statement out of routes/sales_routes.py (architecture batch
A6, 29 Sep 2026): the same SQL text and parameters, one get_db() call each as
the route made them. The route keeps every rule about what the answers mean --
ACOS/ROAS/CPC from summed figures, the totals, the currency rule -- and its own
error handling.
"""
from data import db as _db


def campaign_latest(config_path, wsid, mkt, end=None):
    """{campaign_id: {campaign_name, status, budget}} from each campaign's
    NEWEST stored day (on or before `end`).

    THE ONE ANSWER TO "WHAT IS THIS CAMPAIGN NOW". MAX() over a window compared
    them as text and numbers -- ENABLED -> PAUSED -> ENABLED read PAUSED, a
    budget cut from 20 to 5 still read 20 -- and it was written four times, in
    Campaign Analytics, the Sales campaigns table, Dr PPC and its console
    (review of the advertising pages, 30 Sep 2026; Rule 12)."""
    conn = _db.get_db(config_path)
    cond, args = "", [wsid, mkt]
    if end:
        cond = " AND date<=?"
        args.append(str(end)[:10])
    out = {}
    for r in conn.execute(
            "SELECT l.campaign_id, l.campaign_name, l.status, l.budget FROM "
            "ads_campaign_daily l JOIN (SELECT campaign_id, MAX(date) d FROM "
            "ads_campaign_daily WHERE workspace_id=? AND marketplace=?" + cond
            + " GROUP BY campaign_id) m ON l.campaign_id=m.campaign_id AND l.date=m.d "
            "WHERE l.workspace_id=? AND l.marketplace=?", args + [wsid, mkt]):
        out[str(r["campaign_id"])] = {"campaign_name": r["campaign_name"],
                                      "status": r["status"], "budget": r["budget"]}
    return out


def with_latest(rows, latest, name_key="campaign_name", status_key="status",
                budget_key="budget"):
    """Put campaign_latest's name / status / budget onto summed rows, in the
    caller's own key names. Rows it has nothing for are left as they were."""
    for d in rows:
        got = latest.get(str(d.get("campaign_id")))
        if not got:
            continue
        if got.get("campaign_name"):
            d[name_key] = got["campaign_name"]
        d[status_key] = got.get("status")
        d[budget_key] = got.get("budget")
    return rows


def campaign_rows(config_path, wsid, mkt, start, end):
    """Per-campaign sums over a date range, biggest spend first, as dicts.
    Name, status and budget are the newest day's (campaign_latest)."""
    conn = _db.get_db(config_path)
    return with_latest([dict(r) for r in conn.execute(
        "SELECT campaign_id, "
        "       MAX(campaign_name) AS campaign_name, "
        "       MAX(status)        AS status, "
        "       MAX(budget)        AS budget, "
        "       MAX(ad_product)    AS ad_product, "
        "       SUM(impressions)   AS impressions, "
        "       SUM(clicks)        AS clicks, "
        "       SUM(spend)         AS spend, "
        "       SUM(ad_orders)     AS ad_orders, "
        "       SUM(ad_sales)      AS ad_sales, "
        "       COUNT(DISTINCT date) AS days, "
        "       MAX(fetched_at)    AS fetched_at "
        "FROM ads_campaign_daily "
        "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
        "GROUP BY campaign_id ORDER BY spend DESC",
        (wsid, mkt, start, end))], campaign_latest(config_path, wsid, mkt, end))


def currency_rows(config_path, wsid, mkt):
    """At most one sales_daily row that names a currency, as dicts."""
    return [dict(r) for r in _db.get_db(config_path).execute(
        "SELECT currency FROM sales_daily WHERE workspace_id=? AND "
        "marketplace=? AND COALESCE(currency,'')<>'' LIMIT 1",
        (wsid, mkt))]
