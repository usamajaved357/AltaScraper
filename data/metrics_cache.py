"""data/metrics_cache.py -- the SP-API half of a listing's metrics, remembered.

Only the figures that COST a call are kept here. Everything the database already
holds -- units, sales, page views, buy-box share, on-hand stock -- is read
straight out of it by domain/listing_metrics.py on every request, because a
local read is cheaper than a cache lookup and a cached copy of a local table is
just a second copy that can go stale against the first.

So this stores exactly what api/amazon_metrics.py and inventory_module fetch:

    pricing    buy_box_price, offer_count        TTL  4 hours
    rank       rank, category                    TTL 24 hours
    fba        available, reserved, inbound      TTL  4 hours

TWO TTLs, BECAUSE THEY ARE TWO DIFFERENT QUESTIONS. A price and the stock behind
it move hour to hour and a stale one is actively misleading -- it is what a
repricing or a restock decision would be made against. A sales rank moves
slowly, is reported by Amazon on a lag anyway, and costs a catalogue call per
ASIN; refreshing it hourly would spend the rate limit to watch a number that has
not changed.

WHAT IT REFUSES TO DO

It never stores a FAILURE as an answer. If Amazon refuses the call -- and this
account's roles have been partial before -- nothing is written, so the next
request tries again and the screen goes on saying "we do not have this" rather
than "there is none". A cached empty is indistinguishable from a cached zero
once it is on screen, and that is the bug this whole feature exists to avoid.
"""
import json
import time

from data import db as _db

# group -> seconds. See the docstring for why these two numbers differ.
TTL = {"pricing": 4 * 3600, "fba": 4 * 3600, "rank": 24 * 3600}
DEFAULT_TTL = 4 * 3600

_READY = False


def _ensure(conn):
    """The table, made on first use.

    Keyed by (workspace, marketplace, sku, group): one row per kind of answer,
    so a fresh price does not have to wait for a stale rank to expire, and
    refreshing one never overwrites the other.
    """
    global _READY
    if _READY:
        return
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS listing_metrics_cache ("
            "  workspace_id TEXT NOT NULL,"
            "  marketplace  TEXT NOT NULL,"
            "  sku          TEXT NOT NULL,"
            "  grp          TEXT NOT NULL,"
            "  payload      TEXT NOT NULL,"
            "  fetched_at   REAL NOT NULL,"
            "  PRIMARY KEY (workspace_id, marketplace, sku, grp))")
    _READY = True


def get(config_path, workspace_id, marketplace, skus, groups=None, now=None):
    """{sku: {group: {"data": {...}, "fetched_at": float, "stale": bool}}}.

    STALE ROWS ARE RETURNED, marked. A four-hour-old price is worth showing with
    "last updated 5 hours ago" beside it; throwing it away would leave the
    screen blank whenever Amazon is slow or unreachable, which is exactly when
    somebody most wants to see the last known figure. The caller decides.
    """
    conn = _db.get_db(config_path)
    _ensure(conn)
    now = time.time() if now is None else now
    want = {str(s) for s in (skus or [])}
    if not want:
        return {}
    out = {}
    try:
        rows = conn.execute(
            "SELECT sku, grp, payload, fetched_at FROM listing_metrics_cache "
            "WHERE workspace_id=? AND marketplace=?",
            (workspace_id, marketplace))
        for r in rows:
            sku = str(r["sku"])
            if sku not in want:
                continue
            grp = str(r["grp"])
            if groups and grp not in groups:
                continue
            try:
                data = json.loads(r["payload"] or "{}")
            except Exception:
                continue
            age = now - float(r["fetched_at"] or 0)
            out.setdefault(sku, {})[grp] = {
                "data": data,
                "fetched_at": float(r["fetched_at"] or 0),
                "age": age,
                "stale": age > TTL.get(grp, DEFAULT_TTL),
            }
    except Exception:
        return {}
    return out


def put(config_path, workspace_id, marketplace, sku, group, data, now=None):
    """Remember one answer. Returns True if it was written.

    An empty or non-dict `data` is REFUSED, for the reason in the module
    docstring: a stored blank reads as "Amazon says there is none" forever after.
    """
    if not isinstance(data, dict) or not data:
        return False
    conn = _db.get_db(config_path)
    _ensure(conn)
    now = time.time() if now is None else now
    try:
        with conn:
            conn.execute(
                "INSERT INTO listing_metrics_cache "
                "  (workspace_id, marketplace, sku, grp, payload, fetched_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(workspace_id, marketplace, sku, grp) DO UPDATE SET "
                "  payload=excluded.payload, fetched_at=excluded.fetched_at",
                (workspace_id, marketplace, str(sku), str(group),
                 json.dumps(data), float(now)))
    except Exception:
        return False
    return True


def stale_skus(config_path, workspace_id, marketplace, skus, group, now=None):
    """Which of these SKUs need `group` fetching: never cached, or past its TTL.

    This is what keeps a page load from calling Amazon for 300 listings that
    were all refreshed twenty minutes ago.
    """
    now = time.time() if now is None else now
    have = get(config_path, workspace_id, marketplace, skus, [group], now)
    out = []
    for s in (skus or []):
        s = str(s)
        e = (have.get(s) or {}).get(group)
        if not e or e.get("stale"):
            out.append(s)
    return out


def newest(config_path, workspace_id, marketplace, skus, now=None):
    """The most recent fetch time across these SKUs, or 0.

    Drives the "last updated: 2 hours ago" line -- so that claim is read off
    what was actually stored, not off when the page happened to render.
    """
    have = get(config_path, workspace_id, marketplace, skus, None, now)
    best = 0.0
    for groups in have.values():
        for e in groups.values():
            if e.get("fetched_at", 0) > best:
                best = e["fetched_at"]
    return best


def forget(config_path, workspace_id, marketplace, skus=None):
    """Drop cached answers so the next request refetches. Returns rows removed."""
    conn = _db.get_db(config_path)
    _ensure(conn)
    try:
        with conn:
            if skus:
                n = 0
                for s in skus:
                    c = conn.execute(
                        "DELETE FROM listing_metrics_cache WHERE workspace_id=? "
                        "AND marketplace=? AND sku=?",
                        (workspace_id, marketplace, str(s)))
                    n += c.rowcount or 0
                return n
            c = conn.execute(
                "DELETE FROM listing_metrics_cache WHERE workspace_id=? AND marketplace=?",
                (workspace_id, marketplace))
            return c.rowcount or 0
    except Exception:
        return 0
