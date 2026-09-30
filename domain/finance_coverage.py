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


def misfiled(config_path, wsid, mkt):
    """A note when this marketplace holds account-wide money it should not, else None.

    Amazon's Finances feed is for the whole account, and the app keeps it under
    the account's home marketplace (accounts.home_marketplace). Rows under any
    other marketplace are a copy filed there by mistake -- 28 Sep 2026:
    nestwell_goods' money under IT. REPORTED, NOT DELETED and not hidden: which
    rows go is the owner's call, and silently dropping them from one screen
    would leave the others disagreeing with it.
    """
    from domain import accounts as _accounts
    home, _why = _accounts.home_marketplace(config_path, wsid)
    if not home or str(mkt or "").strip().upper() == home:
        return None
    r = span(config_path, wsid, mkt)
    if not r or not r["n"]:
        return None
    return {"level": "bad", "text": (
        "These Amazon fees, refunds and ad invoices are the whole account's, not "
        "%s's. Amazon reports them for the account, and this app keeps them under "
        "%s; %d row(s) from %s to %s were filed under %s by an earlier sync. "
        "Read the account's money on %s (re-read its last 95 days there if it "
        "looks short). These rows have been left in place, not deleted."
        % (mkt, home, r["n"], r["a"], r["b"], mkt, home))}


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
