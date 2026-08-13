"""domain/live_refresher.py -- keep EVERY account's live catalogue fresh, server-side.

WHY THIS IS ON THE SERVER
The browser timer could only ever refresh the ONE workspace and ONE marketplace
that happened to be open, and only while a tab was open. So every other account
stayed stale, and the first visit to it paid the full report-build wait.

This runs in the app, walks every connected account and every marketplace it
sells on, and keeps each one's saved catalogue current. By the time you open a
workspace the data is already there.

HOW IT PACES ITSELF
Amazon report generation is slow and quota'd, and there can be a dozen
account+marketplace pairs. So it refreshes ONE at a time, always picking the
stalest, and waits between each. That spreads the load instead of asking Amazon
for everything at once -- which is how you get throttled and end up with nothing.

A pair is only refreshed once its saved copy is older than REFRESH_AFTER. A pair
that was just synced by hand is left alone.

IT REUSES THE ROUTE, IT DOES NOT REIMPLEMENT IT
The refresh calls the /live/catalog view function directly, inside a request
context. That is deliberate (Rule 12): fetching a catalogue is one piece of
logic, and a background copy of it would drift from the one the button uses.
dashboard.py already passes the same view around this way.

NOTHING IT DOES CAN BREAK A PAGE
It is a daemon thread that swallows its own errors. A failed refresh leaves the
last good snapshot exactly where it was -- the app keeps serving that, labelled
with when it was really pulled.
"""
import threading
import time

_STATE = {
    "thread": None,
    "running": False,
    "last": {},          # "acct::MKT" -> epoch of the last attempt
    "results": {},       # "acct::MKT" -> short outcome string
    "current": None,     # what is being refreshed right now
    "started": 0.0,
}
_LOCK = threading.RLock()

# How stale a saved catalogue may get before it is refreshed.
REFRESH_AFTER = 10 * 60

# ...UNLESS the marketplace has no listings in it. This account set has 36
# account+marketplace pairs, because each account is registered across most of
# Europe -- but only a handful actually HAVE listings. Refreshing all 36 on the
# same 10-minute clock would take a 54-minute rotation, so the marketplaces you
# actually sell in would be refreshed HOURLY, not every ten minutes, and 36
# reports an hour would be spent mostly on empty ones.
#
# So an empty marketplace backs off hard. It is still checked -- a first listing
# in Poland must eventually show up on its own -- just not at the expense of the
# marketplaces carrying your catalogue.
REFRESH_AFTER_EMPTY = 6 * 3600

# Gap between two refreshes. One report at a time, spread out, so many
# marketplaces never hit Amazon together.
STAGGER = 45
# How often to look for something worth doing.
TICK = 30

# YOU ALWAYS COME FIRST.
#
# When you press Sync on an account -- because you just changed something on
# Amazon and want it in the app NOW -- the background rotation stands aside. It
# is refreshing marketplaces nobody is looking at; you are waiting at a screen.
#
# It keeps standing aside for a short while AFTER your sync finishes, because a
# manual sync is usually followed by more work on that account (edit, push,
# sync again) and a background report starting in the gap would compete with it
# for the same per-minute Amazon quota.
USER_PRIORITY_QUIET = 120

_USER = {"active": 0, "until": 0.0, "last_key": None}


def user_sync_started(key=None):
    """A user-initiated sync has begun. Called by /live/catalog on force."""
    with _LOCK:
        _USER["active"] += 1
        if key:
            _USER["last_key"] = key


def user_sync_finished():
    with _LOCK:
        _USER["active"] = max(0, _USER["active"] - 1)
        _USER["until"] = time.time() + USER_PRIORITY_QUIET


def user_busy():
    """True while a user sync is running, or just after one."""
    with _LOCK:
        return _USER["active"] > 0 or time.time() < _USER["until"]


def status():
    with _LOCK:
        return {
            "running": bool(_STATE["running"]),
            "current": _STATE["current"],
            "paused_for_user": user_busy(),
            "user_syncs_in_flight": _USER["active"],
            "uptime_seconds": int(time.time() - _STATE["started"]) if _STATE["started"] else 0,
            "refresh_after_seconds": REFRESH_AFTER,
            "stagger_seconds": STAGGER,
            "targets": [
                {"key": k, "last_attempt": v, "age_seconds": int(time.time() - v),
                 "result": _STATE["results"].get(k, "")}
                for k, v in sorted(_STATE["last"].items())
            ],
        }


def _targets(cfg_fn, config_path):
    """Every (account_id, marketplace) worth keeping fresh.

    Skips accounts with no credentials of their own: a borrowed token
    authenticates as the LENDER, so a report would return the wrong seller's
    listings under this workspace's name. The route refuses those anyway; not
    asking is quieter and saves a pointless API call.
    """
    out = []
    try:
        import accounts as _acc
        for a in (_acc.load_accounts(cfg_fn(), config_path) or []):
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "").strip()
            if not aid or not _acc.has_own_creds(a):
                continue
            if not _acc.seller_scope_allowed(a):
                continue
            for mkt in (a.get("marketplaces") or []):
                mkt = str(mkt or "").strip().upper()
                if mkt and mkt != "__ALL__":
                    out.append((aid, mkt))
    except Exception:
        return []
    return out


def _stalest(cfg_fn, config_path):
    """The pair most in need of a refresh, or None if everything is current."""
    import domain.live_snapshots as _snap
    best, best_score = None, -1.0
    now = time.time()
    for aid, mkt in _targets(cfg_fn, config_path):
        key = "%s::%s" % (aid, mkt)
        rec = _snap.get(config_path, aid, mkt)
        age = _snap.age_seconds(rec)
        never = (rec is None or age is None)
        # A marketplace with no listings is refreshed on the slow clock. One that
        # holds your catalogue is refreshed on the fast one.
        empty = (not never) and int(rec.get("count") or 0) == 0
        due_after = REFRESH_AFTER_EMPTY if empty else REFRESH_AFTER

        # Do not retry the same pair immediately after an attempt, successful or
        # not -- otherwise one permanently failing account starves every other.
        with _LOCK:
            last_try = _STATE["last"].get(key, 0)
        if now - last_try < due_after:
            continue

        if never:
            age = 10 ** 9                      # never fetched -> highest priority
        elif age < due_after:
            continue

        # Rank by how far PAST its own deadline a pair is, not by raw age. An
        # empty marketplace 7 hours old is barely overdue; a live one 20 minutes
        # old is twice overdue and should go first. Ranking on raw age alone
        # would let the empty marketplaces -- which are allowed to be old --
        # crowd out the ones that matter.
        score = float(age) / float(due_after)
        if score > best_score:
            best, best_score = (aid, mkt), score
    return best


def _refresh_one(app, aid, mkt):
    """Refresh ONE account+marketplace by calling the real /live/catalog view."""
    key = "%s::%s" % (aid, mkt)
    with _LOCK:
        _STATE["current"] = key
        _STATE["last"][key] = time.time()
    try:
        with app.test_request_context(
                "/live/catalog", method="POST",
                # _bg marks this as the ROTATION, not a person. Without it the
                # refresher would register itself as a user sync and then stand
                # aside for itself -- pausing after every single refresh.
                json={"id": aid, "marketplace": mkt, "force": True, "_bg": True}):
            fn = app.view_functions.get("live_catalog")
            if not fn:
                raise RuntimeError("live_catalog view is not registered")
            resp = fn()
        body = resp[0] if isinstance(resp, tuple) else resp
        data = getattr(body, "json", None) or {}
        if data.get("ok"):
            note = "ok (%s listings)" % data.get("count", "?")
            if data.get("partial"):
                note += " partial"
        else:
            note = "failed: %s" % str(data.get("error", ""))[:80]
    except Exception as e:
        note = "error: %s" % str(e)[:80]
    with _LOCK:
        _STATE["results"][key] = note
        _STATE["current"] = None
    return note


def _loop(app, cfg_fn, config_path, log=None):
    while True:
        try:
            # Stand aside while the user is syncing. Their request is what
            # someone is actually waiting on; this rotation is not.
            if user_busy():
                time.sleep(TICK)
                continue
            target = _stalest(cfg_fn, config_path)
            if target:
                note = _refresh_one(app, target[0], target[1])
                if log:
                    log("live refresh %s::%s -> %s" % (target[0], target[1], note))
                time.sleep(STAGGER)            # one report at a time, spread out
                continue
        except Exception:
            pass                               # never let the loop die
        time.sleep(TICK)


def start(app, cfg_fn, config_path, log=None):
    """Start the refresher. Safe to call twice; the second call does nothing."""
    with _LOCK:
        if _STATE["running"]:
            return {"ok": True, "already_running": True}
        t = threading.Thread(target=_loop, args=(app, cfg_fn, config_path, log),
                             name="live-refresher", daemon=True)
        _STATE.update({"thread": t, "running": True, "started": time.time()})
        t.start()
    return {"ok": True, "started": True,
            "refresh_after_seconds": REFRESH_AFTER, "stagger_seconds": STAGGER}
