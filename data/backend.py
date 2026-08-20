"""data/backend.py -- swap the Google Sheet for the database, behind the same two
functions the whole app already uses.

WHY THIS IS SO SMALL
The app never touches a worksheet directly from most of its code. It goes through
two module-level helpers in dashboard.py:

    _ws()            -> the worksheet for the ACTIVE workspace
    _records(ws)     -> that worksheet's rows, as dicts keyed by column name

and those two are handed to every route module by injection
(register(app, *, _ws=..., _records=..., ...)). That is already the seam a
backend swap needs. So switching to SQLite is not a rewrite -- it is supplying a
different pair of functions with the same shapes.

get_all_records() on SheetLikeStore returns dicts keyed by the SHEET's column
names, which is exactly what _records() returned before, so nothing downstream
can tell the difference.
"""
from data.store import FIRST_DATA_ROW as _FIRST_DATA_ROW
from data.store import ListingStore, SheetLikeStore


def make(state, config_path=None):
    """Return (_ws, _records) backed by SQLite.

    `state` is dashboard.py's live _state dict -- the same object the sheets
    backend reads to find the active workspace, so switching backends cannot
    change WHICH workspace is being looked at, only where its rows come from.
    """

    def _ws():
        return SheetLikeStore(ListingStore(workspace_of(state), config_path=config_path))

    def _records(ws, _use_cache=True):
        # _use_cache is accepted and ignored: it existed to collapse bursts of
        # sheet reads under Google's per-minute quota. A local database has no
        # quota and no network, so the cache has nothing to protect against --
        # and dropping it means a row edited by a background job is visible
        # immediately rather than up to 12 seconds later.
        rows = ws.get_all_records()
        # "_row" IS PART OF THE SHAPE. dashboard._records() stamps the sheet row
        # number onto every record, and callers use it to address a row for
        # writing. This one did not, so on the database backend that key was
        # None -- and _apply_edits_batch, which is the ONLY way auto-fix writes
        # anything, passed it straight into update_cell:
        #
        #     TypeError: int() argument must be a string, a bytes-like object
        #                or a real number, not 'NoneType'
        #
        # Every field, every round, every SKU. Auto-fix asked the AI for values,
        # got good ones back -- item_package_dimensions.length.value = 50,
        # .unit = centimeters, size = 148cm -- and threw all of them away, then
        # reported "Nothing new to apply" and stopped. Measured on three real
        # Nestwell rows: 9 suggestions produced, 9 discarded, 2 of 3 SKUs stuck.
        #
        # The number is the inverse of SheetLikeStore._sku_for_row, so the two
        # cannot drift apart.
        for i, r in enumerate(rows):
            r["_row"] = i + _FIRST_DATA_ROW
        return rows

    return _ws, _records


def workspace_of(state):
    """Which workspace the app currently has open.

    Mirrors how the sheets backend resolves the active sheet: the selected
    account first, then the named view. "_no_account" is the explicit name for
    the built-in cross-account workspace, so its rows cannot collide with a real
    account's just because both resolved to an empty string.
    """
    return (state.get("active_account_id")
            or state.get("active_view")
            or "_no_account")
