"""domain/live_mirror_store.py -- Sync's copy of each live listing, kept on disk.

WHAT IT HOLDS
One row per (account, marketplace, SKU): what getListingsItem returned for a
live listing, shaped by routes/live_routes._build_mirror_entry -- title, brand,
bullets, description, images, variations, product type, status, condition --
and when that read happened.

WHY IT EXISTS
The mirror was a dict in server memory (_MIRROR_CACHE in live_routes). Every
restart and every deploy emptied it, so the PDP's "Actual on Amazon" panel and
the listings row's condition went blank until somebody pressed Sync again --
and nothing said the data had been there an hour ago. The owner's PDP redesign
(26 Sep 2026) asked for it to survive a reload, with the sync time shown.

WHAT IT DOES NOT DO
It never talks to Amazon. It stores what Sync already fetched and hands it
back; deciding when to fetch is still live_routes' job. A stored entry is a
record of a past read, and `synced_at` travels with it so no screen can present
it as current.

The one writer and the one reader (CLAUDE.md Rule 12). Never raises: a failed
write loses a cache entry, never a Sync.
"""
import json
import time

from data import db as _db


def save(config_path, workspace_id, marketplace, sku, entry, synced_at=None):
    """Store one listing's mirror entry. Returns True when it was written."""
    if not (workspace_id and marketplace and sku) or not isinstance(entry, dict):
        return False
    try:
        _db.get_db(config_path).execute(
            "INSERT INTO live_mirror (workspace_id, marketplace, sku, payload, synced_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(workspace_id, marketplace, sku) DO UPDATE SET "
            "payload=excluded.payload, synced_at=excluded.synced_at",
            (str(workspace_id), str(marketplace).upper(), str(sku),
             json.dumps(entry), float(synced_at or time.time())))
        return True
    except Exception:
        return False


def load(config_path, workspace_id, marketplace, skus):
    """{sku: entry} for the SKUs asked about that have a stored entry.

    Each entry carries `_synced_at` (epoch seconds) -- when Amazon was read --
    so a screen can say "synced 2h ago" rather than imply it is live.
    """
    out = {}
    skus = [str(s) for s in (skus or []) if str(s).strip()]
    if not (workspace_id and marketplace and skus):
        return out
    try:
        conn = _db.get_db(config_path)
        # In chunks: SQLite caps the number of ? in one statement.
        for i in range(0, len(skus), 400):
            part = skus[i:i + 400]
            rows = conn.execute(
                "SELECT sku, payload, synced_at FROM live_mirror "
                "WHERE workspace_id=? AND marketplace=? AND sku IN (%s)"
                % ",".join("?" for _ in part),
                [str(workspace_id), str(marketplace).upper()] + part).fetchall()
            for r in rows:
                try:
                    entry = json.loads(r["payload"] or "{}")
                except Exception:
                    continue
                if isinstance(entry, dict):
                    entry["_synced_at"] = float(r["synced_at"] or 0)
                    out[r["sku"]] = entry
    except Exception:
        return {}
    return out
