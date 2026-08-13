"""domain/deploy_check.py -- is this deployment actually configured correctly?

WHY THIS EXISTS
On a server you cannot open a terminal and poke at things. The symptoms of a
misconfigured deployment all look like application bugs -- listings vanish, users
get signed out, an API call returns a login page -- so time gets spent hunting in
the code for something that is really a missing environment variable or a
non-persistent directory.

This answers, from inside the running app, the handful of questions that actually
matter. It reads state; it changes nothing.

THE ONE THAT BITES HARDEST
On Railway and Render the filesystem is EPHEMERAL unless a volume is mounted.
config.json's directory is where users.json, altascraper.db and
live_snapshots.json all live -- so if CONFIG_PATH is not on a mounted volume,
every deploy silently destroys your accounts, your imported listings and every
saved catalogue. The app keeps working and simply looks empty, which is the worst
possible way for that to fail.
"""
import os
import time


def _writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.unlink(probe)
        return True
    except Exception:
        return False


def check(config_path):
    """Everything worth knowing, with a verdict per item."""
    cfg = os.path.abspath(str(config_path))
    data_dir = os.path.dirname(cfg)
    items = []

    def add(name, ok, detail, why=""):
        items.append({"name": name, "ok": bool(ok), "detail": detail, "why": why})

    # --- where state lives -------------------------------------------------
    add("Data directory", os.path.isdir(data_dir), data_dir,
        "config.json's folder also holds users.json, altascraper.db and "
        "live_snapshots.json.")
    add("Data directory is writable", _writable(data_dir), data_dir,
        "Without this the app cannot save users, listings or synced catalogues.")

    # Ephemeral filesystem is the big one. A mounted volume is normally NOT
    # inside the app's source directory.
    app_dir = os.path.dirname(os.path.abspath(__file__))
    app_root = os.path.dirname(app_dir)
    looks_ephemeral = os.path.normcase(data_dir).startswith(os.path.normcase(app_root))
    on_paas = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER")
                   or os.environ.get("DYNO"))
    add("State survives a deploy", not (looks_ephemeral and on_paas),
        ("state is inside the app folder (%s) -- this is WIPED on every deploy"
         % data_dir) if (looks_ephemeral and on_paas)
        else ("stored at %s" % data_dir),
        "Mount a volume and point CONFIG_PATH at it, e.g. /data/config.json.")

    # --- sessions ----------------------------------------------------------
    secret = os.environ.get("APP_SECRET_KEY")
    add("APP_SECRET_KEY is set", bool(secret),
        "set" if secret else "NOT SET -- a random key is generated on each boot",
        "Without it every deploy or restart signs EVERY user out, and their "
        "session cookie stops being valid.")

    # --- the login gate ----------------------------------------------------
    pw = os.environ.get("APP_PASSWORD")
    add("APP_PASSWORD is set", bool(pw),
        "set" if pw else "NOT SET -- the login gate is DISABLED",
        "With no password and no user accounts, anyone who reaches the URL has "
        "full access.")

    # --- files that should exist once in use -------------------------------
    for fname, what in (("config.json", "your credentials"),
                        ("users.json", "user accounts"),
                        ("live_snapshots.json", "saved Amazon catalogues"),
                        ("altascraper.db", "the SQLite database")):
        p = os.path.join(data_dir, fname)
        exists = os.path.exists(p)
        size = os.path.getsize(p) if exists else 0
        age = (time.time() - os.path.getmtime(p)) if exists else None
        items.append({
            "name": "File: %s" % fname,
            "ok": exists or fname in ("altascraper.db", "users.json",
                                      "live_snapshots.json"),
            "detail": ("%d bytes, updated %s ago" % (size, _ago(age))) if exists
                      else "not present yet (%s)" % what,
            "why": "" if exists else "Normal if the feature has not been used yet.",
        })

    # --- backend -----------------------------------------------------------
    backend = (os.environ.get("ALTA_DATA_BACKEND") or "sheets").strip().lower()
    add("Data backend", True, backend,
        "'sheets' reads and writes Google Sheets; 'db' uses altascraper.db.")

    failures = [i for i in items if not i["ok"]]
    return {"ok": not failures, "config_path": cfg, "data_dir": data_dir,
            "problems": len(failures), "checks": items}


def _ago(seconds):
    if seconds is None:
        return "never"
    s = int(seconds)
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % (s // 60)
    if s < 172800:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)
