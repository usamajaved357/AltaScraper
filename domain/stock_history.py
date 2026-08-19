"""domain/stock_history.py -- how much stock there was, on each day.

WHY THIS HAS TO EXIST AT ALL

Amazon does not keep this for a merchant-fulfilled seller. It reports what stock
is there NOW; the history is gone the moment the number changes. Every account
here is merchant-fulfilled -- the live catalogue reports fulfillment DEFAULT,
and there are no FBA units -- so there is no ledger to read it out of either.

Without a history, "how fast does this sell" can only be answered by dividing
units by days. That counts every day the product was OUT OF STOCK as a day it
sold nothing, which understates real demand by exactly the amount that matters:
the days you could have sold and had nothing to sell.

    Steven, Orbit's inventory agent, on its own method:
    "OOS days are excluded from the OOS-adjusted pace calculation -- that is the
     adjustment. We do not count an out-of-stock day as a zero-sales day, so it
     does not understate true demand."

That is the right method and it needs a history. So the quantity is recorded
each time the live catalogue is refreshed, which already happens on a timer.

WHAT IT DOES NOT PRETEND

It starts empty, and it fills one day at a time. Nothing here back-fills a past
it cannot know, and the metrics built on it report how many days they actually
had -- a velocity computed over two days of history is not a velocity.
"""
import datetime as _dt

from data import db as _db


def _today():
    return _dt.date.today().isoformat()


def record(config_path, workspace_id, marketplace, items, when=None):
    """Write one row per SKU for today. Returns how many were written.

    The LAST reading of a day wins. What matters for "was this sellable today"
    is whether it ran out, and a later re-check is the better evidence of that.
    """
    if not items:
        return 0
    day = when or _today()
    now = _dt.datetime.now().isoformat(timespec="seconds")
    rows = []
    for it in items:
        sku = str((it or {}).get("sku") or "").strip()
        if not sku:
            continue
        q = (it or {}).get("qty")
        try:
            q = int(q) if q is not None and str(q).strip() != "" else None
        except (TypeError, ValueError):
            q = None
        rows.append((str(workspace_id or ""), str(marketplace or ""), day, sku,
                     str((it or {}).get("asin") or ""), q,
                     str((it or {}).get("status") or ""),
                     str((it or {}).get("fulfillment") or ""), now))
    if not rows:
        return 0
    conn = _db.get_db(config_path)
    with conn:
        conn.executemany(
            "INSERT INTO stock_daily (workspace_id, marketplace, date, sku, "
            "  asin, qty, status, fulfillment, recorded_at) "
            "VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(workspace_id, marketplace, date, sku) DO UPDATE SET "
            "  asin=excluded.asin, qty=excluded.qty, status=excluded.status, "
            "  fulfillment=excluded.fulfillment, recorded_at=excluded.recorded_at",
            rows)
    return len(rows)


def history(config_path, workspace_id, marketplace, start, end, sku=None):
    """{sku: {date: qty}} over the window. qty may be None for 'not said'."""
    conn = _db.get_db(config_path)
    sql = ("SELECT sku, date, qty FROM stock_daily "
           "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=?")
    args = [workspace_id, marketplace, start, end]
    if sku:
        sql += " AND sku=?"
        args.append(sku)
    out = {}
    try:
        for r in conn.execute(sql, args):
            out.setdefault(r["sku"], {})[r["date"]] = r["qty"]
    except Exception:
        return {}
    return out


def coverage(config_path, workspace_id, marketplace):
    """How much history there is: (days recorded, first day, last day, skus).

    Reported wherever a metric depends on it, because a number computed over
    three days should not look like one computed over ninety.
    """
    conn = _db.get_db(config_path)
    try:
        r = conn.execute(
            "SELECT COUNT(DISTINCT date) d, MIN(date) a, MAX(date) b, "
            "       COUNT(DISTINCT sku) s FROM stock_daily "
            "WHERE workspace_id=? AND marketplace=?",
            (workspace_id, marketplace)).fetchone()
    except Exception:
        return {"days": 0, "first": "", "last": "", "skus": 0}
    return {"days": int(r["d"] or 0), "first": r["a"] or "", "last": r["b"] or "",
            "skus": int(r["s"] or 0)}


def in_stock_days(qty_by_date, days):
    """Of `days` dates, how many was this SKU sellable on, and which.

    A day with no reading at all is NOT counted as in stock and NOT counted as
    out of stock -- it is simply unknown, and unknown days are excluded from
    both. Treating a gap in our own recording as a stockout would invent a
    stockout that never happened.
    """
    known = [d for d in days if qty_by_date.get(d) is not None]
    in_stock = [d for d in known if (qty_by_date.get(d) or 0) > 0]
    return {"known": known, "in_stock": in_stock,
            "oos": [d for d in known if (qty_by_date.get(d) or 0) <= 0]}
