"""domain/finance_coverage.py -- WHAT finance data an account has, for the Finance screen.

The Finance screen's own questions about the tables behind it: which marketplace
has rows, what the account has at all when a window is empty, how much of a
window has settled, and whether anything sold after the last settled day.

Moved statement for statement out of routes/finance_routes.py (architecture
batch A6, 29 Sep 2026): the SQL text, the parameters, and one get_db() call per
statement exactly as the route made them. The route keeps every rule about what
to SAY with these answers, and its own try/except around each, so a failure
here is handled exactly as before. Rows are returned as the database gave them.
"""
from data import db as _db


def marketplaces_with_data(config_path, wsid):
    """Up to two distinct marketplaces with finance rows for this account."""
    return _db.get_db(config_path).execute(
        "SELECT DISTINCT marketplace FROM finance_daily "
        "WHERE workspace_id=? LIMIT 2", (wsid,)).fetchall()


def span(config_path, wsid, mkt):
    """Row count and first/last date of finance rows for one marketplace."""
    return _db.get_db(config_path).execute(
        "SELECT COUNT(*) n, MIN(date) a, MAX(date) b FROM finance_daily "
        "WHERE workspace_id=? AND marketplace=?",
        (wsid, mkt)).fetchone()


def rows_per_marketplace(config_path, wsid):
    """Finance row count per marketplace for this account."""
    return _db.get_db(config_path).execute(
        "SELECT marketplace, COUNT(*) n FROM finance_daily "
        "WHERE workspace_id=? GROUP BY marketplace",
        (wsid,)).fetchall()


def settled_and_sold(config_path, wsid, mkt, start, end):
    """(settled row, sold row) for a window, on ONE connection as before:
    distinct products settled plus the last settled day, and distinct products
    that sold (per-product rows only -- asin '*' is the account total)."""
    _c = _db.get_db(config_path)
    _f = _c.execute(
        "SELECT COUNT(DISTINCT asin) a, MAX(date) last FROM finance_daily "
        "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=?",
        (wsid, mkt, start, end)).fetchone()
    _s = _c.execute(
        "SELECT COUNT(DISTINCT asin) a FROM sales_daily "
        "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
        "  AND asin<>'*'", (wsid, mkt, start, end)).fetchone()
    return _c, _f, _s


def sales_after(conn, wsid, mkt, last, end):
    """Account-total ordered sales after the last settled day, on the connection
    settled_and_sold() used."""
    return conn.execute(
        "SELECT COALESCE(SUM(ordered_sales),0) s FROM sales_daily "
        "WHERE workspace_id=? AND marketplace=? AND asin='*' "
        "  AND date>? AND date<=?",
        (wsid, mkt, last, end)).fetchone()
