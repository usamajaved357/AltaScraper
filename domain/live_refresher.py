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
    "workers": {},       # account_id -> its worker thread
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

# PRIORITY IS PER ACCOUNT, NOT GLOBAL.
#
# Amazon's report quota is per SELLING PARTNER ACCOUNT. jack_uk and
# nestwell_goods have separate buckets, so a manual sync on one does not compete
# with a background refresh of the other -- and pausing everything because you
# synced one account would just make every OTHER account go stale for no reason.
#
# What genuinely competes is two reports for the SAME account. That is the only
# case worth standing aside for, and it is the case that matters: you press Sync
# on Nestwell precisely because you are about to work on Nestwell.
_USER = {"accounts": {}, "active": {}}


def _acct_of(key):
    return str(key or "").split("::", 1)[0]


def user_sync_started(key=None):
    """A user-initiated sync has begun. Called by /live/catalog on force."""
    aid = _acct_of(key)
    with _LOCK:
        _USER["active"][aid] = _USER["active"].get(aid, 0) + 1


def user_sync_finished(key=None):
    aid = _acct_of(key)
    with _LOCK:
        _USER["active"][aid] = max(0, _USER["active"].get(aid, 0) - 1)
        _USER["accounts"][aid] = time.time() + USER_PRIORITY_QUIET


def user_busy(account_id=None):
    """Is a user syncing THIS account (or just finished)?

    With no account named, answers for any account -- used only by status().
    """
    with _LOCK:
        if account_id is None:
            return (any(v > 0 for v in _USER["active"].values())
                    or any(t > time.time() for t in _USER["accounts"].values()))
        aid = str(account_id or "")
        return (_USER["active"].get(aid, 0) > 0
                or _USER["accounts"].get(aid, 0) > time.time())


def status():
    with _LOCK:
        return {
            "running": bool(_STATE["running"]),
            "current": _STATE["current"],
            "workers": sorted(_STATE["workers"].keys()),
            "paused_for_user": user_busy(),
            "user_syncs_in_flight": _USER["active"],
            "uptime_seconds": int(time.time() - _STATE["started"]) if _STATE["started"] else 0,
            "refresh_after_seconds": REFRESH_AFTER,
            "stagger_seconds": STAGGER,
            "enrich": {"batch": ENRICH_BATCH, "per_pass": ENRICH_PER_PASS,
                       "pause_seconds": ENRICH_PAUSE},
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


def _stalest(cfg_fn, config_path, only_account=None):
    """The pair most in need of a refresh, or None if everything is current.

    `only_account` restricts the search to one account, so each account's worker
    minds its own business and cannot pick up another's work.
    """
    import domain.live_snapshots as _snap
    best, best_score = None, -1.0
    now = time.time()
    for aid, mkt in _targets(cfg_fn, config_path):
        if only_account is not None and aid != only_account:
            continue
        # Only skip the account the user is actually syncing. Other accounts have
        # their own Amazon quota and carry on being refreshed.
        if user_busy(aid):
            continue
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


# --- images and A+ content, fetched the same way the catalogue is ------------
# WHY THIS IS HERE
# The catalogue report gives titles, prices and statuses but NOT images, and A+
# content lives behind a different API again. So opening a workspace meant
# waiting while the browser pulled images one SKU at a time, and pressing "pull
# live images" by hand. There is no reason a person should have to ask: it is the
# same background job that already keeps the catalogue fresh.
#
# PACED, BECAUSE IMAGES ARE EXPENSIVE
# Each image is one getListingsItem call and SP-API is rate limited per account.
# A catalogue of 500 listings is 500 calls, so a pass takes a BUDGET rather than
# doing all of them: it chips away, newest gaps first, and the next pass
# continues. Getting there in an hour without being throttled beats trying to
# get there in a minute and failing.
ENRICH_BATCH = 20          # SKUs per call to /live/images (its own cap is 40)
ENRICH_PER_PASS = 60       # SKUs per account per pass -- the budget
ENRICH_PAUSE = 3           # seconds between batches, to stay under the rate limit


def _needs_images(cfg_fn, config_path, account_id):
    """The account's marketplace with the most listings still missing an image.

    Most-missing first, so the biggest gap closes fastest instead of the worker
    nibbling at whichever marketplace happens to sort first.
    """
    import domain.live_snapshots as _snap
    if user_busy(account_id):
        return None
    best, most = None, 0
    for aid, mkt in _targets(cfg_fn, config_path):
        if aid != account_id:
            continue
        rec = _snap.get(config_path, aid, mkt)
        if not rec:
            continue
        missing = sum(1 for i in (rec.get("items") or [])
                      if i.get("sku") and not i.get("img"))
        if missing > most:
            best, most = (aid, mkt), missing
    return best


def _enrich_one(app, config_path, aid, mkt, log=None):
    """Fill in images (and warm A+ content) for a marketplace already refreshed.

    Calls the REAL /live/images and /live/aplus views, exactly as _refresh_one
    calls the real /live/catalog -- Rule 12. A background copy of the fetching
    logic would drift from the one the buttons use, and the difference would show
    up as "the images are wrong only when nobody clicked".
    """
    import domain.live_snapshots as _snap
    rec = _snap.get(config_path, aid, mkt)
    if not rec:
        return "no snapshot"
    items = rec.get("items") or []
    # Only listings with no image yet. A gap that Amazon genuinely has no image
    # for is retried on the next catalogue refresh, not on every pass.
    need = [str(i.get("sku") or "") for i in items
            if str(i.get("sku") or "") and not i.get("img")]
    if not need:
        return "images complete"

    todo = need[:ENRICH_PER_PASS]
    got = {}
    failed = 0
    fn = app.view_functions.get("live_images")
    if not fn:
        return "live_images view is not registered"
    for i in range(0, len(todo), ENRICH_BATCH):
        if user_busy(aid):
            break                      # a person is syncing this account; stand aside
        chunk = todo[i:i + ENRICH_BATCH]
        try:
            with app.test_request_context(
                    "/live/images", method="POST",
                    json={"id": aid, "marketplace": mkt, "skus": chunk}):
                resp = fn()
            body = resp[0] if isinstance(resp, tuple) else resp
            data = getattr(body, "json", None) or {}
            if not data.get("ok"):
                failed += len(chunk)
                continue
            imgs = data.get("images") or {}
            statuses = data.get("statuses") or {}
            meta = data.get("meta") or {}
            failed += len(data.get("failed") or [])
            for sku in chunk:
                fields = {}
                if imgs.get(sku):
                    fields["img"] = imgs[sku]
                if statuses.get(sku):
                    fields["status"] = statuses[sku]
                m = meta.get(sku) or {}
                if m.get("fulfillment"):
                    fields["fulfillment"] = m["fulfillment"]
                if m.get("handling") is not None:
                    fields["handling"] = m["handling"]
                if m.get("title"):
                    fields["title"] = m["title"]
                if fields:
                    got[sku] = fields
        except Exception as e:
            failed += len(chunk)
            if log:
                log("enrich %s::%s batch failed: %s" % (aid, mkt, str(e)[:80]))
        time.sleep(ENRICH_PAUSE)

    written = _snap.enrich(config_path, aid, mkt, got) if got else 0

    # A+ content: ONE call per marketplace, and it populates the same cache the
    # page reads, so the card is complete before anyone opens it.
    aplus_note = ""
    afn = app.view_functions.get("live_aplus")
    if afn and not user_busy(aid):
        try:
            with app.test_request_context("/live/aplus", method="POST",
                                          json={"id": aid, "marketplace": mkt}):
                aresp = afn()
            abody = aresp[0] if isinstance(aresp, tuple) else aresp
            adata = getattr(abody, "json", None) or {}
            if adata.get("ok"):
                aplus_note = ", A+ %d" % len(adata.get("by_asin") or {})
        except Exception:
            aplus_note = ", A+ failed"

    left = max(0, len(need) - len(todo))
    return ("images %d/%d saved%s%s%s"
            % (written, len(todo), aplus_note,
               (", %d refused" % failed) if failed else "",
               (", %d still to do" % left) if left else ""))


def _loop(app, cfg_fn, config_path, account_id, log=None):
    """One worker, responsible for ONE account.

    Accounts get their own worker because Amazon's report quota is per selling
    partner account -- jack_uk and nestwell_goods draw on separate buckets and
    genuinely do not compete. A single worker walking all of them in turn made
    four independent accounts queue behind each other for no reason: with 36
    pairs that was a rotation measured in tens of minutes, when four workers each
    handling their own account finish in a quarter of the time.

    Within an account the work IS still serialised, because that is where the
    shared quota actually is.
    """
    while True:
        try:
            # Skips this account only while ITS user sync is running.
            target = _stalest(cfg_fn, config_path, only_account=account_id)
            if target:
                note = _refresh_one(app, target[0], target[1])
                if log:
                    log("live refresh %s::%s -> %s" % (target[0], target[1], note))
                # Fill in the images for what was just refreshed. A catalogue
                # without them is only half a screen, and the person who opens
                # this workspace should not have to ask for the other half.
                try:
                    enote = _enrich_one(app, config_path, target[0], target[1], log)
                    if log:
                        log("live enrich %s::%s -> %s" % (target[0], target[1], enote))
                except Exception:
                    pass
                time.sleep(STAGGER)            # one report at a time FOR THIS ACCOUNT
                continue

            # Nothing needs a fresh REPORT, so spend the idle time finishing the
            # images on a catalogue that already exists. This is what makes a big
            # catalogue arrive complete: one pass is budgeted, and the passes keep
            # coming while there is nothing more urgent to do.
            gap = _needs_images(cfg_fn, config_path, account_id)
            if gap:
                enote = _enrich_one(app, config_path, gap[0], gap[1], log)
                if log:
                    log("live enrich %s::%s -> %s" % (gap[0], gap[1], enote))
                time.sleep(STAGGER)
                continue
        except Exception:
            pass                               # never let a worker die
        time.sleep(TICK)


def _supervisor(app, cfg_fn, config_path, log=None):
    """Start one worker per account, and pick up accounts added later.

    Runs as its own thread so that adding an account in the UI does not require
    an app restart before it starts being kept fresh.
    """
    while True:
        try:
            accounts = sorted({aid for aid, _ in _targets(cfg_fn, config_path)})
            with _LOCK:
                for aid in accounts:
                    if aid in _STATE["workers"]:
                        continue
                    t = threading.Thread(target=_loop,
                                         args=(app, cfg_fn, config_path, aid, log),
                                         name="live-refresher-%s" % aid, daemon=True)
                    _STATE["workers"][aid] = t
                    t.start()
                    if log:
                        log("worker started for %s" % aid)
        except Exception:
            pass
        time.sleep(300)                        # look for new accounts every 5 min


def start(app, cfg_fn, config_path, log=None):
    """Start the refresher. Safe to call twice; the second call does nothing."""
    with _LOCK:
        if _STATE["running"]:
            return {"ok": True, "already_running": True}
        t = threading.Thread(target=_supervisor, args=(app, cfg_fn, config_path, log),
                             name="live-refresher-supervisor", daemon=True)
        _STATE.update({"thread": t, "running": True, "started": time.time()})
        t.start()
    return {"ok": True, "started": True,
            "refresh_after_seconds": REFRESH_AFTER, "stagger_seconds": STAGGER,
            "model": "one worker per account (separate Amazon quotas)"}
