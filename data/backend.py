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
        return ws.get_all_records()

    return _ws, _records


def workspace_of(state):
    """Which workspace the app currently has open.

    Mirrors how the sheets backend resolves the active sheet: the selected
    account first, then the named view. "dropshipping" is the explicit name for
    the built-in cross-account workspace, so its rows cannot collide with a real
    account's just because both resolved to an empty string.
    """
    return (state.get("active_account_id")
            or state.get("active_view")
            or "dropshipping")
