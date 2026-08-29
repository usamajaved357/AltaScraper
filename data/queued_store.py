"""data/queued_store.py -- putting QUEUED rows into the listings store.

ONE PLACE WRITES A QUEUED LISTING. The CSV upload and the "Add a product" form
both come through here, so a product typed in and a product uploaded arrive as
the same shape of row (CLAUDE.md Rule 12).

WHY THIS IS NOT JUST store.upsert_row
Three of the things a queued row carries have no column in the sheet header map
that upsert_row filters against:

  warnings           added by scripts/migrate_statuses.py; not a sheet column
  ebay_item_id       new, and only meaningful inside the app
  ebay_variation_id  ditto

data/column_map.verify_column_map checks the map BOTH ways -- every mapped
header must still be a real header -- so adding these to it would fail that
check and quietly change the sheet contract. They are written straight to their
columns instead, which leaves the header map describing exactly what it always
described.

The supplier cost has no column at all on `listings`; it belongs to the COGS
store, keyed by (account, sku), and is recorded there.
"""
import json

_EXTRA_COLUMNS = ("warnings", "ebay_item_id", "ebay_variation_id")


def ensure_columns(config_path):
    """Add the columns a queued row needs, if they are not there yet.

    ADD COLUMN only -- nothing is dropped, renamed or retyped, so this is safe
    to call on every write and on a database that already has them. Returns the
    list actually added.
    """
    from data import db as _db
    conn = _db.get_db(config_path)
    have = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    added = []
    for col in _EXTRA_COLUMNS:
        if col not in have:
            conn.execute("ALTER TABLE listings ADD COLUMN %s TEXT DEFAULT ''" % col)
            added.append(col)
    if added:
        conn.commit()
    return added


def taken_skus(config_path, workspace_id):
    """Every SKU already used in this workspace.

    Passed to build_sku so a second upload of the same product gets _2 rather
    than silently overwriting the first: (workspace, sku) is UNIQUE and
    upsert_row would treat a repeat as an update.

    THIS IS NOT DEDUPLICATION. The brief is explicit that no row is skipped or
    filtered on upload -- every row goes in, and telling the user that two of
    them look like the same product is the warning system's job. This only stops
    two rows from colliding on one identity.
    """
    from data import db as _db
    conn = _db.get_db(config_path)
    return {r[0] for r in conn.execute(
        "SELECT sku FROM listings WHERE workspace_id=? AND sku IS NOT NULL "
        "AND sku<>''", (workspace_id,))}


def add_queued(config_path, workspace_id, product, taken=None):
    """Queue ONE product as a QUEUED listing. Returns its extras dict (with sku).

    `taken` lets a caller queueing many rows keep one growing set across the
    batch, so two rows in the same file cannot land on the same SKU. Left out,
    it is read fresh for this row.
    """
    from data import input_row as _ir
    from data.store import ListingStore

    ensure_columns(config_path)
    owned = taken if taken is not None else taken_skus(config_path, workspace_id)

    row, extras = _ir.to_listing_row(product, owned)
    store = ListingStore(workspace_id, config_path=config_path)
    store.upsert_row(row)
    owned.add(extras["sku"])

    _write_extras(config_path, workspace_id, extras)
    _record_cost(config_path, workspace_id, extras)
    return extras


def _write_extras(config_path, workspace_id, extras):
    """The columns upsert_row's header map does not cover."""
    from data import db as _db
    conn = _db.get_db(config_path)
    conn.execute(
        "UPDATE listings SET ebay_item_id=?, ebay_variation_id=?, warnings=? "
        "WHERE workspace_id=? AND sku=?",
        (extras.get("ebay_item_id", ""), extras.get("ebay_variation_id", ""),
         json.dumps(extras.get("warnings") or [], ensure_ascii=False),
         workspace_id, extras["sku"]))
    conn.commit()


def _record_cost(config_path, workspace_id, extras):
    """The supplier cost, into the COGS store where cost actually lives.

    Never fatal: a queued row without a recorded cost is worth having, and a
    COGS store that will not open is not a reason to refuse the upload.
    """
    cost = extras.get("source_cost") or 0
    if not cost:
        return
    try:
        from domain import cogs_store as _cogs
        _cogs.set_cost(config_path, workspace_id, extras["sku"], cost)
    except Exception:
        pass


# ---- reading them back -----------------------------------------------------

def queued_rows(config_path, workspace_id):
    """The QUEUED rows for a workspace, as plain dicts, oldest first."""
    from data import db as _db
    conn = _db.get_db(config_path)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM listings WHERE workspace_id=? AND status='QUEUED' "
        "ORDER BY id", (workspace_id,))]


def queued_count(config_path, workspace_id):
    from data import db as _db
    conn = _db.get_db(config_path)
    r = conn.execute("SELECT COUNT(*) n, MAX(updated_at) last FROM listings "
                     "WHERE workspace_id=? AND status='QUEUED'",
                     (workspace_id,)).fetchone()
    return {"count": (r["n"] if r else 0) or 0,
            "imported_at": (r["last"] if r else None)}


def delete_queued(config_path, workspace_id, sku):
    """Remove ONE queued row. Refuses anything that is not QUEUED.

    The old /input/delete could only ever reach the queue table, so it could not
    delete a real listing. Now that queued rows live beside generated and live
    ones, the status test is the only thing keeping that true.
    """
    from data import db as _db
    conn = _db.get_db(config_path)
    n = conn.execute("DELETE FROM listings WHERE workspace_id=? AND sku=? "
                     "AND status='QUEUED'", (workspace_id, sku)).rowcount
    conn.commit()
    return n


def clear_queued(config_path, workspace_id):
    """Empty this workspace's QUEUED rows. Generated and live rows are untouched."""
    from data import db as _db
    conn = _db.get_db(config_path)
    n = conn.execute("DELETE FROM listings WHERE workspace_id=? AND "
                     "status='QUEUED'", (workspace_id,)).rowcount
    conn.commit()
    return n
