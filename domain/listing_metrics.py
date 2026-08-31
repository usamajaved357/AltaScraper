"""domain/listing_metrics.py -- the numbers beside a listing, for one workspace.

ONE JOB: given some SKUs, answer "what has this listing done, what is in stock,
and what is it up against". The listings page's detailed view reads it; so can
the product page. Nothing here calls Amazon and nothing here decides anything.

WHY MOST OF IT NEEDS NO SP-API CALL AT ALL

The brief for this feature assumed every figure had to be fetched. Measured
against the real database first (CLAUDE.md Rule 4 -- read, do not guess), most
of it is already here and has been all along:

    sales_daily   units, ordered_sales, sessions, page_views, buy_box_pct
                  keyed by OUR asin, one row per asin per day
    stock_daily   qty, status, fulfillment per sku -- and our own asin
    order_lines   units and revenue per sku, per order

Fetching page views from SP-API when sales_daily already holds them would put a
second source behind the same number, and the Sales screen and this view would
eventually disagree about a figure they both call "views" (Rule 12). So this
reads what is here, and metrics_cache carries ONLY what genuinely is not:
sales rank, inbound and reserved stock, and a live lowest price.

THE ASIN TRAP, AND WHY stock_daily IS THE BRIDGE

A SKU is price_days_ASIN and that ASIN is the COMPETITOR's -- the product the
listing was researched from, never ours (CLAUDE.md Rule 1). sales_daily is keyed
by OUR asin, the one Amazon issued when it accepted the listing. Joining the two
by the SKU's embedded code therefore matches nothing, and measured on the real
database it matches exactly nothing:

    SELECT COUNT(*) FROM sales_daily s JOIN listings l
      ON s.asin = l.competitor_asin;          ->  0

stock_daily carries both, because it is written from the live catalogue sync:

    sku  10.06_3Days_B0081ZHHTS     <- B0081ZHHTS is the competitor's
    asin B0H8TPB5Y9                 <- ours

so it is the bridge. domain/catalogue.py also maps a SKU to an "asin", but it is
NOT usable here: for rows that are still drafts it fills that field from
listings.competitor_asin, deliberately, because it exists to answer "what does
this product look like" and either code finds a picture. Using it for a metrics
join would silently attribute a competitor's ASIN to our listing.

WHAT IT WILL NOT DO

An absent figure comes back as None, never 0. "Sold nothing" and "we have not
looked" are different facts, and the view draws them differently -- a dash for
one, a zero for the other. Collapsing them here would make that impossible.
"""
import datetime as _dt

from data import db as _db

# The window every "last 30 days" figure is measured over.
DEFAULT_DAYS = 30


def _iso_days_ago(days):
    return (_dt.date.today() - _dt.timedelta(days=int(days))).isoformat()


def _f(v):
    """A float, or None. Never 0 for a missing value."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def own_asins(config_path, workspace_id, marketplace, skus=None):
    """{sku: our own asin} from the most recent stock_daily row for each SKU.

    The latest row wins, because a listing's ASIN can change (a merge into an
    existing catalogue entry) and the newest reading is the true one.
    """
    conn = _db.get_db(config_path)
    sql = ("SELECT sku, asin, MAX(date) FROM stock_daily "
           "WHERE workspace_id=? AND marketplace=? AND IFNULL(asin,'')<>'' "
           "GROUP BY sku")
    out = {}
    try:
        for r in conn.execute(sql, (workspace_id, marketplace)):
            out[str(r["sku"])] = str(r["asin"])
    except Exception:
        return {}
    if skus is not None:
        want = {str(s) for s in skus}
        out = {k: v for k, v in out.items() if k in want}
    return out


def _stock(conn, workspace_id, marketplace, skus):
    """{sku: {on_hand, status, fulfillment, as_of}} from the latest reading."""
    out = {}
    try:
        rows = conn.execute(
            "SELECT s.sku, s.qty, s.status, s.fulfillment, s.date "
            "FROM stock_daily s "
            "JOIN (SELECT sku, MAX(date) d FROM stock_daily "
            "      WHERE workspace_id=? AND marketplace=? GROUP BY sku) m "
            "  ON m.sku=s.sku AND m.d=s.date "
            "WHERE s.workspace_id=? AND s.marketplace=?",
            (workspace_id, marketplace, workspace_id, marketplace))
        for r in rows:
            sku = str(r["sku"])
            if skus and sku not in skus:
                continue
            out[sku] = {"on_hand": _i(r["qty"]),
                        "stock_status": str(r["status"] or ""),
                        "fulfillment": str(r["fulfillment"] or ""),
                        "stock_as_of": str(r["date"] or "")}
    except Exception:
        return {}
    return out


def _sales_by_asin(conn, workspace_id, marketplace, since):
    """{asin: {units, sales, views, sessions, buybox_pct}} over the window.

    Amazon's own per-ASIN daily rows. The account-wide total is stored under the
    asin '*' and is skipped -- it is every product added together, and adding it
    to a product's own line would report the whole account's sales against one
    listing.

    sessions and page_views are NULL on the days Amazon did not return the
    traffic half of the report (359 of 1079 rows carry them, measured). SUM()
    over all-NULL is NULL, which is exactly right: it means "not reported", and
    the caller draws a dash rather than a zero.
    """
    out = {}
    try:
        rows = conn.execute(
            "SELECT asin, "
            "       SUM(units) units, SUM(ordered_sales) sales, "
            "       SUM(page_views) views, SUM(sessions) sessions, "
            "       AVG(buy_box_pct) bb "
            "FROM sales_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND asin<>'*' "
            "GROUP BY asin",
            (workspace_id, marketplace, since))
        for r in rows:
            out[str(r["asin"])] = {
                "units": _i(r["units"]), "sales": _f(r["sales"]),
                "views": _i(r["views"]), "sessions": _i(r["sessions"]),
                "buybox_pct": _f(r["bb"]),
            }
    except Exception:
        return {}
    return out


def _orders_by_sku(conn, workspace_id, marketplace, since, skus):
    """{sku: {units, revenue}} straight from the order lines.

    A SECOND READING OF THE SAME THING, and it is here on purpose. sales_daily
    is keyed by ASIN, so a listing with no own-ASIN yet -- submitted but not
    settled, or one the catalogue sync has not seen -- gets nothing from it,
    while its orders are recorded against the SKU regardless. This fills that
    gap only; where both exist the ASIN figures win, because they are Amazon's
    own report rather than our reconstruction from order lines.
    """
    out = {}
    try:
        rows = conn.execute(
            "SELECT sku, SUM(units) units, SUM(revenue) rev FROM order_lines "
            "WHERE workspace_id=? AND marketplace=? AND purchase_date>=? "
            "GROUP BY sku",
            (workspace_id, marketplace, since))
        for r in rows:
            sku = str(r["sku"])
            if skus and sku not in skus:
                continue
            out[sku] = {"units": _i(r["units"]), "sales": _f(r["rev"])}
    except Exception:
        return {}
    return out


def for_skus(config_path, workspace_id, marketplace, skus, days=DEFAULT_DAYS):
    """Everything known locally about these SKUs. Never raises.

    -> {sku: {asin, units, sales, views, sessions, buybox_pct, on_hand,
              available, stock_status, fulfillment, stock_as_of,
              units_source, days}}

    Fields that nothing can answer are absent rather than zero.
    """
    want = {str(s) for s in (skus or [])}
    if not want:
        return {}
    conn = _db.get_db(config_path)
    since = _iso_days_ago(days)

    asins = own_asins(config_path, workspace_id, marketplace, want)
    stock = _stock(conn, workspace_id, marketplace, want)
    sales = _sales_by_asin(conn, workspace_id, marketplace, since)
    orders = _orders_by_sku(conn, workspace_id, marketplace, since, want)

    out = {}
    for sku in want:
        m = {"days": int(days)}
        asin = asins.get(sku, "")
        if asin:
            m["asin"] = asin
        s = sales.get(asin) if asin else None
        if s:
            # Amazon's own per-ASIN report is the better answer where it exists.
            m.update({k: v for k, v in s.items() if v is not None})
            if s.get("units") is not None:
                m["units_source"] = "amazon_report"
        o = orders.get(sku)
        if o:
            # Only where the report said nothing -- see _orders_by_sku.
            if m.get("units") is None and o.get("units") is not None:
                m["units"] = o["units"]
                m["units_source"] = "order_lines"
            if m.get("sales") is None and o.get("sales") is not None:
                m["sales"] = o["sales"]
        st = stock.get(sku)
        if st:
            m.update({k: v for k, v in st.items() if v not in (None, "")})
            # AVAILABLE IS NOT ASSUMED. For a merchant-fulfilled listing the
            # quantity Amazon holds IS what is available, so the two are the
            # same number. For FBA they are not -- some of the on-hand stock is
            # reserved against orders already placed, and that figure only
            # comes from the FBA inventory API. So `available` is filled here
            # ONLY for the case where it is knowable, and left absent for FBA
            # until metrics_cache has the real split.
            ff = str(st.get("fulfillment") or "").upper()
            if st.get("on_hand") is not None and ff in ("DEFAULT", "MFN", ""):
                m["available"] = st["on_hand"]
        out[sku] = m
    return out


def coverage(config_path, workspace_id, marketplace, days=DEFAULT_DAYS):
    """How much the window above can actually speak for.

    Reported beside the figures, because a "last 30 days" total computed from
    four days of data is not one, and there is no way to tell by looking.
    """
    conn = _db.get_db(config_path)
    since = _iso_days_ago(days)
    out = {"sales_days": 0, "sales_last": "", "stock_last": "", "days": int(days)}
    try:
        r = conn.execute(
            "SELECT COUNT(DISTINCT date) d, MAX(date) b FROM sales_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=?",
            (workspace_id, marketplace, since)).fetchone()
        if r:
            out["sales_days"] = int(r["d"] or 0)
            out["sales_last"] = str(r["b"] or "")
        r2 = conn.execute(
            "SELECT MAX(date) b FROM stock_daily "
            "WHERE workspace_id=? AND marketplace=?",
            (workspace_id, marketplace)).fetchone()
        if r2:
            out["stock_last"] = str(r2["b"] or "")
    except Exception:
        pass
    return out
