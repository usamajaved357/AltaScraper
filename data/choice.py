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


def _raw(config=None):
    """The requested value and where it came from, before any validation."""
    env = str(os.environ.get(ENV_VAR) or "").strip().lower()
    if env:
        return env, "the %s environment variable" % ENV_VAR
    cfg = str((config or {}).get(CONFIG_KEY) or "").strip().lower()
    if cfg:
        return cfg, "%s in config.json" % CONFIG_KEY
    return SHEETS, "the default"


def decide(config=None, config_path=None):
    """Which store to use, and the honest reason. Returns a dict:

        {"backend": "sheets"|"db", "requested": ..., "source": ..., "note": ...}

    Never raises. A caller that only wants the answer should use resolve().
    """
    requested, source = _raw(config)
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
