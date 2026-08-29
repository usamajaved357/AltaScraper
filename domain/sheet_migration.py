"""domain/sheet_migration.py -- moving a workspace's listings out of Google Sheets.

ONE PLACE ANSWERS "COPY THIS ACCOUNT'S SHEET INTO THE APP" (CLAUDE.md Rule 12).

This was routes/migrate_routes.py's private working, reachable only by pressing a
button. It is now called from two places -- that route, and the listings read
itself, which brings leftovers in on its own -- and two copies of the tab rule
below would be two ways to read the wrong account's listings.

WHY THE TAB RULE IS THE WHOLE JOB. Several accounts share ONE workbook, each
owning a different tab, identified by gid rather than by name. import_from_sheet
takes the FIRST tab when given no name, and on a dry run here that read a 3-row
scratch tab for five accounts of six. It would have "succeeded", reported three
rows, and left every real listing behind. So a gid that is not in the workbook is
refused rather than falling back -- the first tab belongs to somebody else.

SAFETY, unchanged from when this was a button:
  * The spreadsheet is only ever READ. import_from_sheet never writes back, not
    even to mark a row as imported, so the original stays as the fallback if the
    import turns out to be wrong.
  * Rows are upserted by SKU, so running it twice is not running it twice: the
    second pass overwrites with the same values rather than duplicating.
"""

# Accounts this process has already tried to bring in, so the listings screen
# does not re-attempt an import on every single load. An account that fails
# (unreachable sheet, unresolvable tab) is recorded here too -- retrying it on
# every read would put a Google round trip in front of a screen that has
# perfectly good rows to draw, which is the cost the banner used to avoid by
# making a person press the button.
#
# Process-scoped on purpose: a restart is the natural "try again", and the
# import is idempotent, so a second attempt costs nothing but time.
_ATTEMPTED = set()


def resolve_tab(client, sid, acc):
    """The account's OWN tab name in workbook `sid` -> (name, error).

    A name is only trusted if the workbook actually has it; a gid that is not in
    the workbook is refused rather than quietly falling back to the first tab.
    """
    gid = str(acc.get("output_tab_gid") or "").strip()
    name = str(acc.get("output_tab") or "").strip()
    try:
        book = client.open_by_key(sid)
        sheets = book.worksheets()
    except Exception as e:
        return None, "Could not open that spreadsheet: %s" % str(e)[:180]
    by_gid = {str(w.id): w.title for w in sheets}
    by_name = {w.title: w.title for w in sheets}
    if gid and gid in by_gid:
        return by_gid[gid], ""
    if name and name in by_name:
        return name, ""
    if gid or name:
        return None, ("This account's own tab (%s) is not in that spreadsheet, "
                      "so nothing was read. Set the output sheet and tab on the "
                      "account first -- importing the workbook's first tab would "
                      "copy in another account's listings." % (gid or name))
    # Only one listing-shaped tab and no gid recorded: unambiguous.
    if len(sheets) == 1:
        return sheets[0].title, ""
    return None, ("This account has no output tab recorded, and that spreadsheet "
                  "has %d tabs. Set the account's output tab first so the right "
                  "one is read." % len(sheets))


def import_account(acc, *, client, config_path, dry_run=True):
    """Copy ONE account's output sheet into its database. Returns a result dict.

    Always returns a dict with "ok"; it never raises, because both callers are
    mid-request and a spreadsheet that cannot be reached is not a reason to fail
    the thing the caller was actually doing.
    """
    aid = str(acc.get("id") or "").strip()
    label = acc.get("label") or aid
    if not aid:
        return {"ok": False, "error": "no account given"}

    sid = str(acc.get("output_spreadsheet_id") or "").strip()
    if not sid:
        return {"ok": False,
                "error": ("%s has no output spreadsheet configured, so there is "
                          "nothing to import from. If its listings are already in "
                          "the app, there is nothing to do." % label)}

    tab, tab_err = resolve_tab(client, sid, acc)
    if tab_err:
        return {"ok": False, "error": tab_err}

    try:
        from data.store import ListingStore
        store = ListingStore(aid, config_path=config_path)
        before = store.row_count()
        res = store.import_from_sheet(client, sid, tab=tab, dry_run=dry_run)
        after = store.row_count()
    except Exception as e:
        return {"ok": False,
                "error": "Could not read that sheet: %s" % str(e)[:200]}

    res = dict(res or {})
    res.update({"ok": True, "account": aid, "label": label, "tab": tab,
                "before": before, "after": after, "dry_run": dry_run,
                # Said every time, because the whole safety of this rests on it
                # and it should never be something the reader assumes.
                "note": "The spreadsheet was only read. Nothing was written to "
                        "it and nothing in it was changed."})
    return res


def auto_import_once(acc, *, client, config_path):
    """Bring an account's leftover sheet rows in, at most once per process.

    Called from the listings read when it finds rows that exist ONLY in the
    spreadsheet. Returns the result dict, or None if this account has already
    been attempted.

    This is the replacement for the notice that used to sit above the listings
    saying "N of these are still only in the Google Sheet" with a button. The
    button was the right mechanism and the wrong place to put the decision: the
    rows have to move for the app to be off Sheets, nobody was ever going to
    answer "no", and until somebody pressed it the same listings kept appearing
    and disappearing as the app changed where it read from.
    """
    aid = str(acc.get("id") or "").strip()
    if not aid or aid in _ATTEMPTED:
        return None
    _ATTEMPTED.add(aid)
    return import_account(acc, client=client, config_path=config_path,
                          dry_run=False)
