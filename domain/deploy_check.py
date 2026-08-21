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


def check(config_path, in_use=None):
    """Everything worth knowing, with a verdict per item.

    `in_use` is the store the running app actually settled on (build_app records
    it). Passed in rather than looked up, so this module reports the truth about
    a specific app instead of guessing from the environment a second time.
    """
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
    #
    # THAT SHAPE TEST IS NOT ENOUGH, and the gap cost a folder of generated
    # images. CONFIG_PATH=/data/config.json passes it -- /data is outside the app
    # folder -- whether or not a volume is actually mounted there, because
    # docker-entrypoint.sh mkdir -p's the folder either way. So an unmounted
    # /data reported "state survives a deploy" while every deploy wiped it, and
    # the wipe was invisible because the entrypoint reseeds config.json from the
    # Secret File on boot. The real answer comes from the mount table and from a
    # marker this folder has been accumulating across boots; the shape test stays
    # as the first, cheapest way to be certain it is wrong.
    app_dir = os.path.dirname(os.path.abspath(__file__))
    app_root = os.path.dirname(app_dir)
    looks_ephemeral = os.path.normcase(data_dir).startswith(os.path.normcase(app_root))
    on_paas = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER")
                   or os.environ.get("DYNO"))
    if looks_ephemeral and on_paas:
        add("State survives a deploy", False,
            "state is inside the app folder (%s) -- this is WIPED on every deploy"
            % data_dir,
            "Mount a volume and point CONFIG_PATH at it, e.g. /data/config.json.")
    else:
        try:
            import domain.media_recover as _mrec
            ev = _mrec.disk_evidence(data_dir, on_paas=on_paas)
            add("State survives a deploy", ev["verdict"] != "EPHEMERAL", ev["detail"],
                "Mount a volume and point CONFIG_PATH at it, e.g. /data/config.json. "
                "This folder also holds every generated image (media/), so an "
                "unmounted path loses those on each deploy as well.")
        except Exception as e:
            add("State survives a deploy", True, "stored at %s" % data_dir,
                "Could not verify the mount (%s) -- the path is at least outside "
                "the app folder." % e)

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

    # --- which store is in force -------------------------------------------
    # Reported from the one resolver, never by re-reading the environment. The
    # environment says what was ASKED FOR; this says what the app is DOING, and
    # when those differ the difference is the whole story.
    try:
        from data import choice as _choice
        d = _choice.decide(None, cfg)
        if in_use:
            d = dict(d, backend=in_use)
        add("Data store", not d.get("note"),
            "%s (%s), chosen by %s" % (d["backend"], _choice.label(d["backend"]),
                                       d.get("source", "?")),
            d.get("note") or "'sheets' reads and writes Google Sheets; 'db' uses "
                             "altascraper.db in the folder above.")
        if d.get("requested") and d["requested"] != d["backend"]:
            add("Requested store is in use", False,
                "asked for %r, running on %r" % (d["requested"], d["backend"]),
                d.get("note") or "")
    except Exception as e:
        add("Data store", False, "could not be determined: %s" % e, "")

    # --- one Amazon seller, one workspace ----------------------------------
    # An account authorized through OAuth used to be created from the merchant
    # token alone, without asking whether some workspace already WAS that
    # seller. On the live app that produced "Nestwell Goods LTD" and "Amazon
    # seller ZAAYT4" side by side in the switcher -- both A8YN8LJZAAYT4.
    #
    # The cause is fixed (domain/accounts.by_seller_id), but a duplicate already
    # created stays until somebody decides which record survives -- and that
    # decision moves listings, costs and orders, so it is not made here. It is
    # named here, which is the part that was missing.
    try:
        import json as _json
        from domain import accounts as _acc_mod
        _cfg_data = _json.load(open(cfg, encoding="utf-8"))
        dupes = _acc_mod.duplicate_sellers(_cfg_data, cfg)
        add("One workspace per Amazon seller", not dupes,
            ("ok" if not dupes else "; ".join(
                "%s is in %d workspaces (%s)" % (sid, len(ids), ", ".join(ids))
                for sid, ids in dupes.items())),
            "Two workspaces for one seller split that seller's listings, costs "
            "and orders between them depending on which is open, and each "
            "carries its own sheet, VAT rate and marketplace list. Decide which "
            "record survives, move anything on the other to it, then delete the "
            "spare under Manage accounts.")
    except Exception as e:
        add("One workspace per Amazon seller", False,
            "could not be checked: %s" % str(e)[:120], "")

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
