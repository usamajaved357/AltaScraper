"""domain/sales_queries.py -- the Sales screen's direct questions to its tables.

Moved statement for statement out of routes/sales_routes.py (architecture batch
A6, 29 Sep 2026): the same SQL text and parameters, one get_db() call each as
the route made them. The route keeps every rule about what the answers mean --
ACOS/ROAS/CPC from summed figures, the totals, the currency rule -- and its own
error handling.
"""
from data import db as _db


def campaign_rows(config_path, wsid, mkt, start, end):
    """Per-campaign sums over a date range, biggest spend first, as dicts."""
    conn = _db.get_db(config_path)
    return [dict(r) for r in conn.execute(
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
        (wsid, mkt, start, end))]


def currency_rows(config_path, wsid, mkt):
    """At most one sales_daily row that names a currency, as dicts."""
    return [dict(r) for r in _db.get_db(config_path).execute(
        "SELECT currency FROM sales_daily WHERE workspace_id=? AND "
        "marketplace=? AND COALESCE(currency,'')<>'' LIMIT 1",
        (wsid, mkt))]
