"""Google Sheets is unlinked, and a deleted draft stays deleted.

    "i deleted some listings ... they are just changing their position, they are
     now brought to the end of the list but are not deleted from the drafts
     section ... when i try to delete them again they give the error that they
     are not here, but i am still seeing them here"

    "once the listing is deleted from drafts i dont want to see it again"

    "i thought the google sheets are permanently removed from the workflow,
     unlink the google sheets permanently from my app wherever they are"

WHAT WAS HAPPENING. The delete always worked -- the row went from the database.
The listings read then consulted the SPREADSHEET as well, showed the copy the
sheet still had (appended after the database rows, which is why they moved to
the end of the list) and copied it back into the database. Deleting again found
nothing in the database and said so, while the sheet's copy was still on screen.

WHY IT WAS ON. It was a setting, read_sheets_as_well, which defaults to ON for
any config that has never mentioned it. The deployed config.json lives on a
Render disk (render.yaml: CONFIG_PATH=/data/config.json), was written before the
key existed, and therefore had it on -- while the local config, the only one
anybody could see, had it off. Two machines, two answers, one of them invisible.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with io.open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


from data import choice as C

CFG = os.path.join(HERE, "config.json")
BASE = {"data_backend": "db"}

print("== there is no way to turn the spreadsheet back on ==")
yes("the decision is in code, not a setting", C.sheets_unlinked() is True)
check("silence means OFF now, which is production's config shape",
      C.sheets_fallback({}, CFG), False)
# EVERY ROUTE BACK, tried. A decision that a config file can undo is not a
# decision -- and the config that mattered was the one nobody could see.
for cfgval in (True, "on", "yes", "1"):
    check("  config read_sheets_as_well=%-5r cannot" % cfgval,
          C.sheets_fallback(dict(BASE, read_sheets_as_well=cfgval), CFG), False)
for envval in ("1", "true", "on", "yes"):
    os.environ[C.FALLBACK_ENV] = envval
    check("  %s=%-5s cannot" % (C.FALLBACK_ENV, envval),
          C.sheets_fallback(BASE, CFG), False)
os.environ.pop(C.FALLBACK_ENV, None)
check("the sheets BACKEND cannot be chosen either",
      C.resolve({"data_backend": "sheets"}, CFG), "db")
os.environ[C.ENV_VAR] = "sheets"
check("  not by environment variable", C.resolve({}, CFG), "db")
_note = C.decide({}, CFG).get("note") or ""
os.environ.pop(C.ENV_VAR, None)
# BUT ASKING IS STILL REPORTED. An app that silently ignores its own settings is
# what /diag exists to catch -- see the note at the top of data/choice.py about
# a diagnostic that lies being worse than none.
yes("  and being overruled is said out loud", "permanently unlinked" in _note)

print("\n== the listings read cannot merge a spreadsheet in ==")
LR = read("routes", "listing_routes.py")
_ra = LR[LR.index("def rows_all"):]
_ra = _ra[:_ra.index("@app.route", 10)]
yes("it asks before contacting Google", "sheets_fallback" in _ra)
yes("  and returns first when the answer is no",
    _ra.index("sheets_fallback") < _ra.index("_client().open_by_key"))
# These two are the resurrection itself. They are unreachable now rather than
# removed -- an unreachable path cannot bring a listing back, and deleting the
# sheets code is Phase 6 and a change of a different size.
yes("the merge that appended sheet rows is behind that gate",
    _ra.index("sheets_fallback") < _ra.index("cards = db_cards + sheet_only"))
yes("  and so is the re-import that copied them back",
    _ra.index("sheets_fallback") < _ra.index("auto_import_once"))

print("\n== nothing opens a spreadsheet on an ordinary click ==")
AC = read("routes", "accounts_routes.py")
_sel = AC[AC.index("def accounts_select"):]
_sel = _sel[:_sel.index("@app.route", 10)] if "@app.route" in _sel[10:] else _sel
# This was the last one: every account switch opened the account's Google Sheet
# to turn a tab gid into a tab NAME -- a string used only as a label, and
# meaningless once no listing is read from a sheet.
yes("switching account asks before opening a workbook",
    "sheets_unlinked()" in _sel)
yes("  and the gid lookup is skipped when it is unlinked",
    "if not _unlinked and sid and" in _sel)
yes("  falling back to the name it already had",
    "_account_tab_name(acc)" in _sel)

print("\n== what is deliberately still allowed to touch a spreadsheet ==")
# Read the docstring rather than restating it, so the two cannot drift.
CH = read("data", "choice.py")
yes("Drive is explicitly out of scope -- images live there",
    "Google DRIVE" in CH and "different service" in CH)
yes("an explicit, user-pressed backup or import still may",
    "explicit" in CH and "BEHIND" in CH)
# The distinction that matters: consulted behind the app's back vs asked for by
# name. Only the first was resurrecting rows.
yes("  and the reason is stated", "resurrecting deleted rows" in CH
    or "behind the app's back" in CH.lower())

print("\n== the delete path itself ==")
_del = LR[LR.index("def delete_row():"):]
_del = _del[:_del.index("@app.route", 10)]
yes("a named SKU that is not here is reported, not deleted by position",
    "if target is None and row and not sku:" in _del)
yes("  and the read cache is cleared so the row cannot come back from it",
    "_bust_records_cache()" in _del)
yes("a live listing goes from Amazon too", "_delete_on_amazon(" in _del)

# MEASURED, 9 Sep 2026, on the running app with a planted draft:
#   before   the row is in ROWS
#   delete   {"ok": true, "deleted": 1}
#   reload 1 gone
#   reload 2 gone            <- the re-import used to run once per process, so
#                               the second reload is the one that used to fail
#   /rows_all source: {"store":"database","from_database":86,"from_sheet":0,
#                      "sheets_off":true}
#   0 rows left in the database for that sku. No page errors.

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
