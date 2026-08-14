"""data/input_import.py -- bring the input sheet in, once, on demand.

WHAT THIS CHANGES
The generator's INPUT -- the list of products waiting to be turned into listings
-- was the last thing read live from Google Sheets. Reading it live meant no
listing could be started unless Google was reachable, the service account still
had access, and the sheet had not been renamed or re-tabbed. Everything else in
the app had already stopped depending on Sheets; this was the last thread.

Now it is an IMPORT. You press a button, the rows land in the database, and
nothing reads Google again until you press it again. Your sheet stays exactly as
you use it today -- it just stops being a dependency, and can be abandoned
whenever you like without the app noticing.

WHY IT REUSES read_input_sheet()
The generator already knows how to read one of these sheets: which column names
mean what, which rows to skip, how to normalise the odd ones. That logic is not
copied here. Import calls the generator's own reader, so an input sheet imported
by this module and one read directly by the generator can never be understood
differently (Rule 12).

WHAT AN IMPORT DOES NOT DO
It does not delete. A row that disappears from the sheet stays in the database
until you clear it explicitly. Import is additive and idempotent per row, so
pressing the button twice is harmless -- and a sheet that fails to load halfway
through cannot empty your queue.
"""
import json
import time

from data import db as _db


COLUMNS = ("amazon_url", "competitor_asin", "ebay_url", "item_name",
           "source_cost", "selling_price", "handling_time", "upc")


def _asin_of(url):
    import re
    m = re.search(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", str(url or ""))
    return m.group(1) if m else ""


def import_rows(config_path, workspace_id, products, source="sheet"):
    """Store already-normalised product dicts. Returns (added, updated).

    Keyed on the row's position in the source AND on the source itself, so
    re-importing the same sheet updates its own rows in place instead of
    duplicating the queue.

    THE SOURCE IS PART OF THE KEY, and has to be. Position alone meant sheet row
    0 landed on whatever was at position 0 -- and once products could be typed
    into the app, that was somebody's first hand-added product. Pressing "Import
    from sheet" silently replaced work that had never been in a spreadsheet, with
    no error and nothing to undo it. A test caught it on the first run.
    """
    conn = _db.get_db(config_path)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    added = updated = 0
    for i, p in enumerate(products or []):
        if not isinstance(p, dict):
            continue
        vals = {k: str(p.get(k, "") or "") for k in COLUMNS}
        if not vals["competitor_asin"]:
            vals["competitor_asin"] = _asin_of(vals["amazon_url"])
        row = conn.execute(
            "SELECT id FROM input_products WHERE workspace_id=? AND row_index=? "
            "AND source=?", (workspace_id, i, source)).fetchone()
        if row:
            conn.execute(
                "UPDATE input_products SET %s, raw=?, imported_at=?, source=? "
                "WHERE id=?" % ", ".join("%s=?" % c for c in COLUMNS),
                tuple(vals[c] for c in COLUMNS)
                + (json.dumps(p)[:4000], now, source, row["id"]))
            updated += 1
        else:
            conn.execute(
                "INSERT INTO input_products (workspace_id, row_index, %s, raw, "
                "imported_at, source) VALUES (?,?,%s,?,?,?)"
                % (", ".join(COLUMNS), ",".join("?" * len(COLUMNS))),
                (workspace_id, _free_index(conn, workspace_id, i))
                + tuple(vals[c] for c in COLUMNS)
                + (json.dumps(p)[:4000], now, source))
            added += 1
    conn.commit()
    return added, updated


def import_from_worksheet(config_path, workspace_id, ws_in, source="sheet"):
    """Read a Google input sheet and store it. Returns (added, updated, total).

    Uses the GENERATOR'S OWN reader, so the column-name handling cannot drift
    between what gets imported and what the generator would have read itself.
    """
    from amazon_listing_generator import read_input_sheet
    products = read_input_sheet(ws_in) or []
    added, updated = import_rows(config_path, workspace_id, products, source=source)
    return added, updated, len(products)


# ---- typed straight into the app, instead of into a spreadsheet -------------
#
# import_rows keys on the row's POSITION in the source sheet, which is right for
# an import -- re-importing updates in place rather than duplicating -- and
# useless for adding one product by hand: every hand-added row would be index 0
# and would overwrite the last one. These three give the queue the operations a
# person needs when the spreadsheet is not in the picture at all: add one, change
# one, remove one.
#
# The queue is the SAME queue either way, so a workspace can be filled from a
# sheet, by hand, or both, and the generator neither knows nor cares which.

# Hand-added products live in their own range of row_index, above anything a
# spreadsheet will ever reach.
#
# row_index is UNIQUE per workspace, and a sheet import writes positions 0..n.
# Share the range and sheet row 0 lands on whatever is at position 0 -- which,
# once products can be typed into the app, is somebody's first hand-added
# product, silently replaced by an import with nothing to undo it. A test caught
# exactly that on the first run. Separate ranges make the collision impossible
# rather than merely unlikely: no spreadsheet has a million rows.
HAND_BASE = 1000000


def next_index(config_path, workspace_id):
    """The next free row_index for a HAND-ADDED row, clear of any sheet."""
    conn = _db.get_db(config_path)
    r = conn.execute("SELECT MAX(row_index) AS m FROM input_products "
                     "WHERE workspace_id=? AND row_index>=?",
                     (workspace_id, HAND_BASE)).fetchone()
    m = r["m"] if r and r["m"] is not None else None
    return HAND_BASE if m is None else m + 1


def _free_index(conn, workspace_id, wanted):
    """`wanted` if nothing holds it, otherwise the next free one above it.

    Only reachable on a queue built before the ranges were separated, where a
    hand-added row may sit at a low index. Moving the incoming sheet row is the
    right way round: the row already in the queue is the one somebody typed.
    """
    i = int(wanted)
    while conn.execute("SELECT 1 FROM input_products WHERE workspace_id=? "
                       "AND row_index=?", (workspace_id, i)).fetchone():
        i += 1
    return i


def add_row(config_path, workspace_id, product, source="app"):
    """Queue ONE product. Returns its id.

    source="app" rather than "sheet" so it is visible afterwards where a row came
    from -- and so a later sheet import, which writes by position, cannot land on
    top of something typed by hand.
    """
    conn = _db.get_db(config_path)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    vals = {k: str((product or {}).get(k, "") or "").strip() for k in COLUMNS}
    if not vals["competitor_asin"]:
        vals["competitor_asin"] = _asin_of(vals["amazon_url"])
    cur = conn.execute(
        "INSERT INTO input_products (workspace_id, row_index, %s, raw, "
        "imported_at, source) VALUES (?,?,%s,?,?,?)"
        % (", ".join(COLUMNS), ",".join("?" * len(COLUMNS))),
        (workspace_id, next_index(config_path, workspace_id))
        + tuple(vals[c] for c in COLUMNS)
        + (json.dumps(product or {})[:4000], now, source))
    conn.commit()
    return cur.lastrowid


def update_row(config_path, workspace_id, row_id, fields):
    """Change one queued product. Only the columns given, and only in this
    workspace -- an id from another workspace matches nothing rather than
    editing somebody else's queue."""
    cols = [c for c in COLUMNS if c in (fields or {})]
    if not cols:
        return 0
    conn = _db.get_db(config_path)
    vals = {c: str(fields.get(c, "") or "").strip() for c in cols}
    if "amazon_url" in vals and not vals.get("competitor_asin"):
        found = _asin_of(vals["amazon_url"])
        if found and "competitor_asin" not in cols:
            cols.append("competitor_asin")
            vals["competitor_asin"] = found
    n = conn.execute(
        "UPDATE input_products SET %s WHERE workspace_id=? AND id=?"
        % ", ".join("%s=?" % c for c in cols),
        tuple(vals[c] for c in cols) + (workspace_id, row_id)).rowcount
    conn.commit()
    return n


def delete_row(config_path, workspace_id, row_id):
    """Remove one queued product. Scoped to the workspace for the same reason."""
    conn = _db.get_db(config_path)
    n = conn.execute("DELETE FROM input_products WHERE workspace_id=? AND id=?",
                     (workspace_id, row_id)).rowcount
    conn.commit()
    return n


def rows(config_path, workspace_id):
    """Everything queued for this workspace, in the order it was imported."""
    conn = _db.get_db(config_path)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM input_products WHERE workspace_id=? ORDER BY row_index",
        (workspace_id,)).fetchall()]


def summary(config_path, workspace_id):
    """Enough to tell someone whether their queue is current, and how old it is."""
    conn = _db.get_db(config_path)
    r = conn.execute(
        "SELECT COUNT(*) AS n, MAX(imported_at) AS last FROM input_products "
        "WHERE workspace_id=?", (workspace_id,)).fetchone()
    return {"count": (r["n"] if r else 0) or 0,
            "imported_at": (r["last"] if r else None)}


def clear(config_path, workspace_id):
    conn = _db.get_db(config_path)
    n = conn.execute("DELETE FROM input_products WHERE workspace_id=?",
                     (workspace_id,)).rowcount
    conn.commit()
    return n


class InputGrid(object):
    """The stored queue, shaped like a worksheet.

    read_input_sheet() asks a worksheet for get_all_values() and nothing else, so
    presenting the database through that one method lets the generator read from
    either source with NO change to how it reads. That is the whole reason the
    generator reads through listing/repo.py: the day something replaced the sheet,
    the call site would not have to change. This is that day.
    """

    def __init__(self, config_path, workspace_id):
        self._rows = rows(config_path, workspace_id)

    def get_all_values(self):
        if not self._rows:
            return []
        # The header names must be ones read_input_sheet ACTUALLY recognises, not
        # our own column names. It maps ebay_price/ebay_cost -> source_cost and
        # amazon_price/selling_price -> selling_price, so emitting "source_cost"
        # would have arrived back empty and every product would have lost its
        # cost -- silently, because a blank cost is a legal value.
        # (header emitted, column stored)
        pairs = [("amazon_url", "amazon_url"), ("ebay_url", "ebay_url"),
                 ("item_name", "item_name"), ("ebay_cost", "source_cost"),
                 ("selling_price", "selling_price"),
                 ("handling_time", "handling_time"), ("upc", "upc")]
        out = [[h for h, _ in pairs]]
        for r in self._rows:
            out.append([str(r.get(col) or "") for _, col in pairs])
        return out

    def __len__(self):
        return len(self._rows)
