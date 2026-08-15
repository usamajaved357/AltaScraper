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
    """Should the app still read Google Sheets alongside the database?

    Default TRUE, so nothing changes for anyone mid-migration. Meaningless on
    the sheets backend, where the sheet IS the store -- answered True there so
    no caller has to special-case it.
    """
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
