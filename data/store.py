"""data/store.py -- ListingStore, the drop-in replacement for the worksheet.

PLAIN ENGLISH
Everywhere the app currently says "read the sheet" or "write to the sheet", the
beta says "read the store" or "write to the store" instead. What comes back looks
identical, so nothing downstream notices the difference.

THE CONTRACT THAT MAKES THIS WORK
get_all_rows() returns dictionaries keyed by the SHEET's column names -- "Buy Box
Price (GBP)", not "buy_box_price" -- with string values. That is exactly what a
sheet read produced, so the ~300 places that read a row need no changes.

Break that contract and the failure is silent: g("Buy Box Price (GBP)") starts
returning "" instead of a price, no exception is raised anywhere, and every
margin on screen quietly reads zero.

THE WORKSHEET ADAPTER
Some code does not go through a nice interface -- it calls the worksheet object
directly: ws.row_values(1), ws.get_all_values(), ws.batch_update([...]). There
are 14 such calls in routes/listing_routes.py alone. SheetLikeStore below answers
those same method names on top of the database, so that code runs unmodified
rather than needing a rewrite.
"""
import json
import threading
import time

from data import db as _db
from data.column_map import (COL_TO_HEADER, HEADER_TO_COL, INTERNAL_COLS,
                             header_dict_to_row, row_to_header_dict)

# The sheet's column order. Used by anything that still thinks in grids --
# row_values(1), get_all_values(), and A1-notation batch updates.
ORDERED_HEADERS = list(HEADER_TO_COL.keys())

_WRITE_LOCK = threading.RLock()


class ListingStore:
    """Listings for ONE workspace. Mirrors how the app treats one sheet tab."""

    def __init__(self, workspace_id, config_path=None):
        self.workspace_id = str(workspace_id or "")
        self.config_path = config_path

    # ---- reads ----------------------------------------------------------
    def _conn(self):
        return _db.get_db(self.config_path)

    def get_all_rows(self):
        """Every listing, oldest first, keyed by SHEET column names.

        Ordered by id so the row order is stable between reads. The sheet had an
        inherent order and parts of the app (row numbers shown to the user, "row
        N failed" messages) lean on rows not shuffling under them.
        """
        cur = self._conn().execute(
            "SELECT * FROM listings WHERE workspace_id=? ORDER BY id",
            (self.workspace_id,))
        return [row_to_header_dict(r) for r in cur.fetchall()]

    def get_row_by_sku(self, sku):
        r = self._conn().execute(
            "SELECT * FROM listings WHERE workspace_id=? AND sku=?",
            (self.workspace_id, str(sku or ""))).fetchone()
        return row_to_header_dict(r) if r else None

    def get_rows_by_status(self, status):
        cur = self._conn().execute(
            "SELECT * FROM listings WHERE workspace_id=? AND status=? ORDER BY id",
            (self.workspace_id, str(status or "")))
        return [row_to_header_dict(r) for r in cur.fetchall()]

    def count_by_status(self):
        cur = self._conn().execute(
            "SELECT COALESCE(status,'') AS s, COUNT(*) AS n FROM listings "
            "WHERE workspace_id=? GROUP BY COALESCE(status,'')",
            (self.workspace_id,))
        return {r["s"]: r["n"] for r in cur.fetchall()}

    def search(self, query):
        """Substring search over title, SKU, ASIN and notes.

        LIKE rather than FTS5: the tables are thousands of rows, not millions,
        so it is fast enough, and it avoids a second shadow table that has to be
        kept in step with every write.
        """
        q = "%%%s%%" % str(query or "").strip()
        cur = self._conn().execute(
            "SELECT * FROM listings WHERE workspace_id=? AND ("
            "  COALESCE(title,'')           LIKE ? COLLATE NOCASE"
            "  OR COALESCE(sku,'')          LIKE ? COLLATE NOCASE"
            "  OR COALESCE(competitor_asin,'') LIKE ? COLLATE NOCASE"
            "  OR COALESCE(notes,'')        LIKE ? COLLATE NOCASE"
            ") ORDER BY id", (self.workspace_id, q, q, q, q))
        return [row_to_header_dict(r) for r in cur.fetchall()]

    def row_count(self):
        return self._conn().execute(
            "SELECT COUNT(*) AS n FROM listings WHERE workspace_id=?",
            (self.workspace_id,)).fetchone()["n"]

    # ---- writes ---------------------------------------------------------
    def upsert_row(self, row):
        """Insert, or update the existing row with the same SKU.

        SKU is the identity of a listing, and (workspace_id, sku) is UNIQUE, so
        re-running a generation updates the row rather than duplicating it --
        which is what the sheet flow did by finding the row and overwriting it.
        """
        data = header_dict_to_row(row)
        sku = (data.get("sku") or "").strip()
        if not sku:
            raise ValueError("upsert_row needs a SKU -- it is the row's identity")
        data["workspace_id"] = self.workspace_id
        data["updated_at"] = _now()

        cols = [c for c in data if c in COL_TO_HEADER or c in
                ("workspace_id", "updated_at", "listing_marketplace")]
        with _WRITE_LOCK:
            placeholders = ",".join("?" for _ in cols)
            updates = ",".join("%s=excluded.%s" % (c, c) for c in cols
                               if c not in ("workspace_id", "sku"))
            sql = ("INSERT INTO listings (%s) VALUES (%s) "
                   "ON CONFLICT(workspace_id, sku) DO UPDATE SET %s"
                   % (",".join(cols), placeholders, updates))
            self._conn().execute(sql, [data[c] for c in cols])
        return sku

    def update_fields(self, sku, fields):
        """Change some columns on one row. Accepts SHEET column names."""
        data = header_dict_to_row(fields)
        data.pop("sku", None)                 # never rename a row's identity here
        if not data:
            return 0
        data["updated_at"] = _now()
        sets = ",".join("%s=?" % c for c in data)
        with _WRITE_LOCK:
            cur = self._conn().execute(
                "UPDATE listings SET %s WHERE workspace_id=? AND sku=?" % sets,
                list(data.values()) + [self.workspace_id, str(sku or "")])
        return cur.rowcount

    def bulk_update(self, updates):
        """[(sku, {field: value}), ...] in ONE transaction.

        All of it lands or none of it does. The sheet version wrote in batches of
        100 and could fail halfway, leaving rows half-updated with no record of
        where it stopped.
        """
        n = 0
        with _WRITE_LOCK:
            conn = self._conn()
            conn.execute("BEGIN")
            try:
                for sku, fields in (updates or []):
                    n += self.update_fields(sku, fields)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return n

    def delete_row(self, sku):
        with _WRITE_LOCK:
            cur = self._conn().execute(
                "DELETE FROM listings WHERE workspace_id=? AND sku=?",
                (self.workspace_id, str(sku or "")))
        return cur.rowcount

    def delete_empty_rows(self):
        """Rows with no SKU and no title -- the sheet's 'clear empty' action."""
        with _WRITE_LOCK:
            cur = self._conn().execute(
                "DELETE FROM listings WHERE workspace_id=? "
                "AND COALESCE(sku,'')='' AND COALESCE(title,'')=''",
                (self.workspace_id,))
        return cur.rowcount

    # ---- sheet interop --------------------------------------------------
    def import_from_sheet(self, gc, spreadsheet_id, tab=None, dry_run=False):
        """One-time copy of an existing sheet into the database.

        The sheet is only ever READ. Nothing here writes back to it -- if the
        import is wrong you still have the original untouched, which is the whole
        safety net for this migration.
        """
        book = gc.open_by_key(spreadsheet_id)
        ws = book.worksheet(tab) if tab else book.get_worksheet(0)
        grid = ws.get_all_values()
        if not grid:
            return {"imported": 0, "skipped": 0, "errors": ["sheet is empty"]}

        header = [str(h).strip() for h in grid[0]]
        unknown = [h for h in header if h and h not in HEADER_TO_COL]
        imported, skipped, errors = 0, 0, []

        for i, values in enumerate(grid[1:], start=2):
            row = {header[j]: values[j] for j in range(min(len(header), len(values)))}
            if not (row.get("SKU") or "").strip():
                skipped += 1                  # no SKU means no identity
                continue
            if dry_run:
                imported += 1
                continue
            try:
                self.upsert_row(row)
                imported += 1
            except Exception as e:
                errors.append("row %d: %s" % (i, str(e)[:160]))

        return {"imported": imported, "skipped": skipped, "errors": errors,
                "unknown_headers": unknown, "sheet_rows": len(grid) - 1,
                "dry_run": bool(dry_run)}

    def export_to_sheet(self, gc, spreadsheet_id, tab="listings"):
        """One-way push to a Google Sheet, as a backup you can eyeball.

        Rewrites the tab wholesale. Not a sync -- edits made in the sheet are NOT
        read back, and will be overwritten next time this runs.
        """
        from listing import repo as _repo       # shared open-or-create (Rule 12)
        book = gc.open_by_key(spreadsheet_id)
        # No headers passed: this method writes the whole grid INCLUDING its own
        # header row a few lines below, so letting ensure_tab write one too would
        # put the headers in twice.
        ws, _created = _repo.ensure_tab(book, tab, rows=1000,
                                        cols=len(ORDERED_HEADERS))
        rows = self.get_all_rows()
        grid = [ORDERED_HEADERS]
        for r in rows:
            grid.append([r.get(h, "") for h in ORDERED_HEADERS])
        ws.clear()
        ws.update(grid, "A1")
        return {"exported": len(rows), "tab": tab}


class SheetLikeStore:
    """A worksheet-shaped face on ListingStore.

    Exists for code that talks to the gspread worksheet object directly rather
    than through a helper -- ws.row_values(1), ws.get_all_values(),
    ws.batch_update([...]). There are 14 such calls in routes/listing_routes.py.
    Answering those method names here means that code runs against the database
    unmodified, instead of each call site needing a rewrite.

    It is a compatibility shim, not a design. New code should use ListingStore
    directly; this exists so the beta can reach working sooner and with a much
    smaller diff to review.
    """

    def __init__(self, store):
        self.store = store
        self.title = "listings"

    # -- reads
    def row_values(self, n):
        if int(n) == 1:
            return list(ORDERED_HEADERS)
        rows = self.store.get_all_rows()
        idx = int(n) - 2
        if idx < 0 or idx >= len(rows):
            return []
        return [rows[idx].get(h, "") for h in ORDERED_HEADERS]

    def get_all_values(self):
        grid = [list(ORDERED_HEADERS)]
        for r in self.store.get_all_rows():
            grid.append([r.get(h, "") for h in ORDERED_HEADERS])
        return grid

    def get_all_records(self):
        return self.store.get_all_rows()

    # -- writes
    def batch_update(self, payload):
        """Accepts gspread's [{'range': 'C5', 'values': [[v]]}, ...].

        A1 ranges are resolved back to (row, column) -> (sku, header), which is
        why ORDERED_HEADERS has to match the sheet's column order exactly.
        """
        updates = {}
        for item in (payload or []):
            rng = item.get("range") or ""
            vals = item.get("values") or [[]]
            cell = _parse_a1(rng)
            if not cell:
                continue
            row_n, col_n = cell
            sku = self._sku_for_row(row_n)
            if not sku:
                continue
            for dr, line in enumerate(vals):
                for dc, v in enumerate(line):
                    h = _header_at(col_n + dc)
                    if h:
                        updates.setdefault(sku, {})[h] = v
        return self.store.bulk_update(list(updates.items()))

    def update(self, values, range_name=None, **kw):
        raise NotImplementedError(
            "SheetLikeStore.update() is deliberately not implemented. Whole-grid "
            "writes are how the sheet flow worked; on the database use "
            "ListingStore.upsert_row() so a write names the row it changes.")

    def _sku_for_row(self, row_n):
        rows = self.store.get_all_rows()
        idx = int(row_n) - 2
        if idx < 0 or idx >= len(rows):
            return None
        return rows[idx].get("SKU")


def _header_at(col_n):
    i = int(col_n) - 1
    return ORDERED_HEADERS[i] if 0 <= i < len(ORDERED_HEADERS) else None


def _parse_a1(ref):
    """'C5' or 'Sheet1!C5' or 'C5:E5' -> (row, col) of the first cell."""
    ref = str(ref or "").split("!")[-1].split(":")[0].strip()
    letters = "".join(c for c in ref if c.isalpha())
    digits = "".join(c for c in ref if c.isdigit())
    if not letters or not digits:
        return None
    col = 0
    for c in letters.upper():
        col = col * 26 + (ord(c) - 64)
    return int(digits), col


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")
