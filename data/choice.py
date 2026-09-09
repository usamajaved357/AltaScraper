"""data/choice.py -- which store is in force, decided ONCE.

WHY THIS EXISTS
This was the most consequential setting in the app and it was decided in three
different ways that could disagree:

  dashboard.py            build_app(backend="sheets")   -- a function argument,
                          and docker-entrypoint.sh runs `python dashboard.py`,
                          so the deployed app was ALWAYS sheets whatever the
                          environment said
  amazon_listing_generator.py   read ALTA_DATA_BACKEND, then config.json
  users_routes / deploy_check   reported ALTA_DATA_BACKEND

So with ALTA_DATA_BACKEND=db the generator would write listings into SQLite
while the dashboard kept reading the Google Sheet -- you would generate listings
and they would simply never appear -- and /diag would confidently report "db"
for an app that was running on sheets. A diagnostic that lies is worse than no
diagnostic at all.

Every one of them now asks resolve(). Rule 12: one concept, one implementation.

THE DEFAULT IS STILL SHEETS. Nothing about a working deployment changes.
"""
import os

SHEETS = "sheets"
DB = "db"
VALID = (SHEETS, DB)

ENV_VAR = "ALTA_DATA_BACKEND"
CONFIG_KEY = "data_backend"


def _raw(config=None, config_path=None):
    """The requested value and where it came from, before any validation.

    WHEN NOBODY HAS SAID, THE DATABASE WINS -- IF THERE IS ONE.
    The default used to be the sheet unconditionally. That is how an account with
    a fully migrated database, 283 listings in it and the input sheet imported on
    demand still spent a whole session reading Google Sheets: nothing was wrong,
    nobody had said "db", and the default quietly sent it back to spreadsheets.
    Every screen then correctly said "your sheet", which looked like the
    migration had failed when it was the default that had.

    So: an existing database is now taken as the answer. It is not a guess -- a
    database file only exists because it was created and written to. Where there
    is none, the sheet is still the answer, and that is the case this cannot get
    wrong: a brand new install has no database and must not start empty.
    """
    env = str(os.environ.get(ENV_VAR) or "").strip().lower()
    if env:
        return env, "the %s environment variable" % ENV_VAR
    cfg = str((config or {}).get(CONFIG_KEY) or "").strip().lower()
    if cfg:
        return cfg, "%s in config.json" % CONFIG_KEY
    path = db_path(config_path)
    if path and os.path.exists(path):
        return DB, "the default (a database exists at %s)" % path
    return SHEETS, "the default (no database exists yet)"


def decide(config=None, config_path=None):
    """Which store to use, and the honest reason. Returns a dict:

        {"backend": "sheets"|"db", "requested": ..., "source": ..., "note": ...}

    Never raises. A caller that only wants the answer should use resolve().
    """
    requested, source = _raw(config, config_path)

    # THE STORE IS THE DATABASE. See the note under resolve(). The requested
    # value is still reported, so /diag can say "your config asks for sheets and
    # it is being ignored" rather than pretending nobody asked.
    if _SHEETS_UNLINKED:
        note = ""
        if requested == SHEETS:
            note = ("%s asks for the Google Sheet, which is ignored: the "
                    "spreadsheet is permanently unlinked and the database is "
                    "the only store." % (source[0].upper() + source[1:]))
        elif requested not in VALID:
            # A TYPO IS STILL REPORTED. This used to be caught below, by the
            # branch that sent an unrecognised value back to the sheet and named
            # the mistake -- "sqlite" instead of "db" was the case it was written
            # for. Returning early would have swallowed it: the app would do the
            # right thing and say nothing, so the misspelling stays in the config
            # for the next person to puzzle over. The ANSWER cannot change any
            # more; the fact that somebody asked for something that is not a
            # store still can, and should.
            note = ("%r is not a recognised store (expected 'sheets' or 'db'). "
                    "The database is being used either way -- the spreadsheet is "
                    "permanently unlinked -- but fix %s."
                    % (requested, source))
        return {"backend": DB, "requested": requested, "source": source,
                "note": note, "unlinked": True}

    out = {"backend": requested, "requested": requested, "source": source, "note": ""}

    if requested not in VALID:
        out["backend"] = SHEETS
        out["note"] = ("%r is not a recognised store (expected 'sheets' or 'db'), "
                       "so the app is using the Google Sheet. Fix %s."
                       % (requested, source))
        return out

    # REFUSING TO SWITCH TO A STORE THAT IS NOT THERE.
    # Setting the variable to "db" on a server whose database file was never
    # created -- or was wiped by a deploy -- would start an app that works
    # perfectly and shows nothing at all. That reads as "my listings are gone",
    # which is the most alarming and least informative failure available. An
    # empty store is not a valid answer to "where is my data", so say so and
    # keep reading the sheet.
    if out["backend"] == DB:
        path = db_path(config_path)
        if not path or not os.path.exists(path):
            out["backend"] = SHEETS
            out["note"] = ("%s asked for the database, but no database exists at "
                           "%s. Using the Google Sheet instead -- an empty app "
                           "would look like lost data. Run the import first."
                           % (source[0].upper() + source[1:], path or "(unknown)"))
    return out


def resolve(config=None, config_path=None):
    """Just the answer: "sheets" or "db"."""
    return decide(config, config_path)["backend"]


# ===========================================================================
# GOOGLE SHEETS IS UNLINKED. THE ANSWER IS THE DATABASE, ALWAYS.
# ===========================================================================
#
#     "i thought the google sheets are permanently removed from the workflow,
#      unlink the google sheets permanently from my app wherever they are"
#
# It was not removed -- it was switched off in ONE config.json, the local one.
# The deployed app keeps its config on a Render disk (render.yaml: CONFIG_PATH
# =/data/config.json), that copy never had read_sheets_as_well in it, and the
# key defaults to ON. So production was running backend=db with the spreadsheet
# ALSO being read, which is the state that produced this:
#
#     "why the deleted listings from drafts are not permanently deleting from
#      the database ... when i try to delete them again they give the error
#      that they are not here, but i am still seeing them here"
#
# The delete was working. routes/listing_routes.py then read the sheet as well
# (line ~1564, `cards = db_cards + sheet_only`), showed the row the sheet still
# had -- appended AFTER the database rows, which is why they moved to the end --
# and auto_import_once copied it back into the database. Delete it again and the
# database genuinely does not have it, so the app says so while the sheet's copy
# is still on screen.
#
# A SETTING WAS THE WRONG PLACE FOR THIS. The two functions below used to answer
# from config.json and the environment, so "is this app on Sheets" had a
# different answer on every machine and could be turned back on by a file nobody
# can see from here. The decision is made in code now, once, and no config or
# environment variable can undo it.
#
# WHAT THIS DOES NOT TOUCH, deliberately:
#   * Google DRIVE -- product images live there and it is a different service.
#   * An explicit, user-pressed one-time import or backup. Those ask for a
#     spreadsheet by name; this only governs whether one is consulted BEHIND
#     the app's back, which is the thing that was resurrecting deleted rows.
#
# The sheets code paths are now unreachable rather than deleted. Deleting them
# is Phase 6 of the restructure and a change of a different size -- 111 files
# mention Sheets, most of them archives and backups -- and an unreachable path
# cannot resurrect a listing.
_SHEETS_UNLINKED = True


def sheets_unlinked():
    """Is the spreadsheet permanently out of the loop? Always True.

    A function rather than the bare constant so /diag and the settings screen
    can state it, and so the reason travels with the answer."""
    return _SHEETS_UNLINKED


# A SECOND, SEPARATE QUESTION: may the Google Sheet still be read as well?
#
# "Which store" and "is the old store still consulted" are different things,
# and conflating them is what made the migration drag. While this is on, the
# app reads BOTH and merges -- which is what stops a half-migrated account
# showing an empty screen, and is deliberately the default.
#
# Turning it OFF is the actual moment the app becomes independent of Sheets. It
# is a deliberate act, not a side effect of having a database, because it is the
# point after which a row that only exists in a spreadsheet is invisible. Check
# /backup/verify first: it reports, per account, whether the app holds every SKU
# the sheet does.
#
# Backups and the one-time import are NOT affected. Those ask for a sheet
# explicitly; this only governs whether one is consulted BEHIND the app's back.
FALLBACK_KEY = "read_sheets_as_well"
FALLBACK_ENV = "ALTA_READ_SHEETS"


def sheets_fallback(config=None, config_path=None):
    """Should the app still read Google Sheets alongside the database? NO.

    ALWAYS FALSE NOW. This is the switch that was resurrecting deleted drafts:
    while it was on, the listings read merged the spreadsheet's rows in and
    copied them back into the database, so a row the owner had deleted returned
    on the next page load. It defaulted to ON for anyone who had not explicitly
    set it, which is every deployment whose config.json was written before the
    key existed -- including the live one.

    The key and the environment variable below are still NAMED so an old config
    carrying them does not read as a mystery, but neither is consulted. See the
    note under resolve() for what is deliberately still allowed to touch a
    spreadsheet (an explicit backup or one-time import) and what is not.
    """
    if _SHEETS_UNLINKED:
        return False
    if resolve(config, config_path) != DB:
        return True
    env = str(os.environ.get(FALLBACK_ENV) or "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    val = (config or {}).get(FALLBACK_KEY)
    if val is None:
        return True                      # nobody has said: keep reading, safely
    if isinstance(val, str):
        return val.strip().lower() not in ("0", "false", "no", "off")
    return bool(val)


def db_path(config_path=None):
    """Where the SQLite file lives.

    Delegates to data/db.py, which already owned this and handles the
    ALTASCRAPER_DB override and the CONFIG_PATH fallback. Re-deriving it here
    would have been a second answer to the same question -- and a wrong one:
    this module would have said "no database exists" for anyone using
    ALTASCRAPER_DB, and refused to start on the store they had asked for.
    """
    try:
        from data.db import db_path as _p
        return _p(config_path)
    except Exception:
        return None


def label(backend):
    """How to name it to a human, in a sentence."""
    return "the Google Sheet" if backend == SHEETS else "the app's own database"
