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


def store_for(aid, cfg, config_path=None):
    """The listings store for ONE NAMED workspace. -> a store, or None.

        "no one account data should be shared with another"

    THE DIFFERENCE BETWEEN THIS AND _ws() IS THE WHOLE POINT. _ws() answers
    "the workspace the SERVER currently has open", which is one variable for the
    whole process, written when an account is chosen. This answers "the
    workspace the PAGE named". The owner routinely has several browser tabs
    open, so whichever tab last switched account owns that global -- and a write
    routed through _ws() lands on that account's rows regardless of which
    account the person was looking at when they typed.

    Measured consequence, 7 Sep 2026: the bulk handling-time endpoint pushed the
    new number to the right account on Amazon (it resolved the account from the
    request) and recorded it through _ws(). So the two halves of one action
    could go to two different companies, and the listing on screen kept showing
    the old number no matter how many times it was changed --

        "i did this multiple time in the past with days of break in between but
         still app shows 3, it is not changing to 2"

    On the database a workspace IS the unit of storage -- data/store.StoreBook
    says it plainly, "on the database a tab is a workspace" -- so a store can
    simply be opened for the account that was asked about. Verified before this
    was used: ListingStore("jack_uk") holds 87 SKUs,
    ListingStore("nestwell_goods") 86, and none is shared between them.

    Returns None when there is no account to open or the backend is not the
    database, so callers keep their existing behaviour rather than losing their
    rows to a helper that could not help.

    IT LIVES HERE because two route modules need it and a second copy of "which
    store belongs to which account" is exactly the duplication Rule 12 is about.
    `cfg` is passed rather than read, so this module still holds no opinion
    about where configuration comes from.
    """
    aid = str(aid or "").strip()
    if not aid:
        return None
    try:
        from data import choice as _ch
        if _ch.resolve(cfg, None) != "db":
            return None
        return SheetLikeStore(ListingStore(aid, config_path=config_path))
    except Exception:
        return None


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
