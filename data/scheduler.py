"""data/scheduler.py -- background jobs, and an honest record of what they did.

PLAIN ENGLISH
Some work should happen on its own rather than when you click a button: pulling
live listing data from Amazon, checking tracked ASINs for new sellers, refreshing
FBA stock levels. This runs those on a timer and writes down what happened, so
the dashboard can tell you the truth about when each last ran.

WHY EVERY RUN IS RECORDED
A background job that silently fails is worse than no job at all: the screen
keeps showing old numbers and nothing says they are old. That is exactly the
class of bug that caused the 64-listings-becomes-16 problem. So every run writes
a row to sync_jobs -- start, finish, result or error -- and /jobs/status reads
back from that table rather than from anything held in memory.

APSCHEDULER IS OPTIONAL
It is not installed here yet, and an import error at startup would stop the beta
from booting at all. So the import is guarded: without APScheduler the jobs can
still be run by hand through /jobs/run/<job_type>, and /jobs/status reports that
scheduling is unavailable rather than pretending jobs are queued.
    pip install apscheduler
"""
import json
import threading
import time
import traceback

from data import db as _db

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    HAVE_APSCHEDULER = True
except Exception:
    BackgroundScheduler = None
    HAVE_APSCHEDULER = False

_scheduler = None
_JOBS = {}
_LOCK = threading.RLock()


def register_job(job_type, fn, hours=None, description=""):
    """Make a job runnable by name. Scheduling it is a separate step."""
    with _LOCK:
        _JOBS[job_type] = {"fn": fn, "hours": hours, "description": description}


def _record_start(job_type, workspace_id):
    conn = _db.get_db()
    cur = conn.execute(
        "INSERT INTO sync_jobs (job_type, workspace_id, status, last_run) "
        "VALUES (?,?,'running',?)",
        (job_type, workspace_id, _now()))
    return cur.lastrowid


def _record_end(row_id, status, result=None, error=None):
    _db.get_db().execute(
        "UPDATE sync_jobs SET status=?, result=?, error=? WHERE id=?",
        (status,
         json.dumps(result)[:4000] if result is not None else None,
         str(error)[:2000] if error else None,
         row_id))


def run_job(job_type, workspace_id=None):
    """Run one job now, recording the attempt whether it works or not.

    Never raises. A scheduled job that throws would otherwise kill its thread and
    stop running for ever, with nothing on screen to say so.
    """
    job = _JOBS.get(job_type)
    if not job:
        return {"ok": False, "error": "unknown job type: %s" % job_type}
    row_id = _record_start(job_type, workspace_id)
    started = time.time()
    try:
        result = job["fn"](workspace_id) if workspace_id else job["fn"]()
        _record_end(row_id, "ok", result=result)
        return {"ok": True, "job": job_type, "result": result,
                "seconds": round(time.time() - started, 2)}
    except Exception as e:
        _record_end(row_id, "error", error="%s\n%s" % (e, traceback.format_exc()[-1200:]))
        return {"ok": False, "job": job_type, "error": str(e)[:400],
                "seconds": round(time.time() - started, 2)}


def status():
    """Last run of every job type, straight from the database.

    Read from sync_jobs, not from the scheduler's memory: after a restart the
    scheduler knows nothing, while the table still holds the truth.
    """
    conn = _db.get_db()
    rows = conn.execute(
        "SELECT job_type, workspace_id, status, last_run, result, error "
        "FROM sync_jobs WHERE id IN ("
        "  SELECT MAX(id) FROM sync_jobs GROUP BY job_type, COALESCE(workspace_id,'')"
        ") ORDER BY job_type").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["age_seconds"] = _age(d.get("last_run"))
        out.append(d)
    known = {r["job_type"] for r in rows}
    for jt, j in _JOBS.items():
        if jt not in known:
            out.append({"job_type": jt, "workspace_id": None, "status": "never run",
                        "last_run": None, "result": None, "error": None,
                        "age_seconds": None})
    return {"jobs": out,
            "scheduler_running": bool(_scheduler and _scheduler.running),
            "apscheduler_installed": HAVE_APSCHEDULER,
            "registered": sorted(_JOBS.keys())}


def start(workspace_ids=None):
    """Start the timers. Safe to call when APScheduler is absent.

    Jobs are staggered rather than all firing at once on boot: three SP-API
    sweeps starting together is how you meet a rate limit on the first minute of
    every deploy.
    """
    global _scheduler
    if not HAVE_APSCHEDULER:
        return {"ok": False,
                "error": "APScheduler is not installed -- jobs can still be run "
                         "manually via /jobs/run/<job_type>. pip install apscheduler"}
    with _LOCK:
        if _scheduler and _scheduler.running:
            return {"ok": True, "already_running": True}
        _scheduler = BackgroundScheduler(daemon=True)
        delay = 0
        for jt, j in _JOBS.items():
            if not j.get("hours"):
                continue
            for ws in (workspace_ids or [None]):
                _scheduler.add_job(
                    run_job, "interval", hours=j["hours"],
                    args=[jt, ws], id="%s::%s" % (jt, ws or "all"),
                    replace_existing=True, max_instances=1, coalesce=True,
                    next_run_time=_soon(60 + delay))
                delay += 45
        _scheduler.start()
    return {"ok": True, "jobs": len(_scheduler.get_jobs())}


def shutdown():
    global _scheduler
    with _LOCK:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
        _scheduler = None


# ---- the jobs themselves ------------------------------------------------
# These were stubs that raised NotImplementedError, on the grounds that each
# needed "the beta's SP-API client". That reasoning has expired: dashboard_beta.py
# calls build_app(backend="db"), which is the SAME app with the SAME routes, so
# every one of these already exists and works. What was missing was not a client
# but a way to reach it from a timer.
#
# So none of them talks to Amazon. Each delegates to the code that already owns
# that job (Rule 12) -- a second implementation would drift from the one the
# buttons use, and the difference would show as "the scheduled sweep disagrees
# with the screen".
_APP = {"app": None, "config_path": None, "cfg": None}


def bind(app=None, config_path=None, cfg=None):
    """Give the jobs the app and config they need to reach the real code.

    Held in a module global because APScheduler calls these with no context at
    all. Set once by register_jobs().
    """
    if app is not None:
        _APP["app"] = app
    if config_path is not None:
        _APP["config_path"] = config_path
    if cfg is not None:
        _APP["cfg"] = cfg


def _need(*keys):
    missing = [k for k in keys if not _APP.get(k)]
    if missing:
        raise RuntimeError("scheduler is not bound to %s -- call bind() first"
                           % ", ".join(missing))
    return [_APP[k] for k in keys]


def catalog_sync(workspace_id=None):
    """Refresh live listing data, and the images that go with it.

    Delegates to domain/live_refresher.py, which already does this per account
    and does it BETTER than a fixed timer could: it ranks marketplaces by how far
    past their own deadline they are, backs off on empty ones, and stands aside
    while a person is syncing. A second six-hourly catalogue sweep next to it
    would not add freshness, it would add contention for the same Amazon quota.

    So this job's real work is to make sure that refresher is running, and to
    report what it is doing. Running it by hand forces one account's stalest
    marketplace immediately, which is the part a timer usefully adds.
    """
    import domain.live_refresher as _ref
    app, config_path, cfg = _need("app", "config_path", "cfg")
    st = _ref.status()
    if not st.get("running"):
        _ref.start(app, cfg, config_path)
        return {"started_refresher": True}
    target = _ref._stalest(cfg, config_path, only_account=workspace_id)
    if not target:
        return {"refreshed": None, "note": "every marketplace is current",
                "workers": st.get("workers")}
    note = _ref._refresh_one(app, target[0], target[1])
    enote = _ref._enrich_one(app, config_path, target[0], target[1])
    return {"refreshed": "%s::%s" % target, "catalogue": note, "images": enote}


def asin_monitor_check(workspace_id=None):
    """Check tracked ASINs for seller changes.

    monitor/checker.py already owns this, including the 24-hour throttle that
    exists so the monitor stops exhausting the Amazon quota. Calling check_all
    directly respects that throttle; reimplementing the sweep here would not,
    which is precisely the bug the throttle was added for.
    """
    from monitor import checker as _checker
    _, config_path, cfg = _need("app", "config_path", "cfg")
    res = _checker.check_all(cfg() if callable(cfg) else cfg, config_path,
                             log=lambda m: None)
    return res if isinstance(res, dict) else {"result": str(res)[:400]}


def inventory_sync(workspace_id=None):
    """Refresh FBA inventory levels.

    Calls the real /inventory/v2/run view inside a request context, the same way
    live_refresher calls /live/catalog. The inventory model -- reorder points,
    cover days, the alert thresholds -- lives in that route, and a copy of it
    here would quietly disagree with the numbers on the Inventory screen.
    """
    app, _config_path, _cfg = _need("app", "config_path", "cfg")
    fn = app.view_functions.get("inventory_v2_run")
    if not fn:
        raise RuntimeError("inventory_v2_run view is not registered")
    with app.test_request_context("/inventory/v2/run", method="POST",
                                  json={"id": workspace_id or ""}):
        resp = fn()
    body = resp[0] if isinstance(resp, tuple) else resp
    data = getattr(body, "json", None) or {}
    if not data.get("ok"):
        raise RuntimeError("inventory run failed: %s" % str(data.get("error"))[:200])
    return {"alerts": len(data.get("alerts") or []),
            "skus": data.get("count") or data.get("rows") or 0}


def sales_sync(workspace_id=None):
    """Pull yesterday's sales, and chip away at any backlog.

    Every connected account and every marketplace it sells on, paced. Amazon
    revises the last couple of days as returns settle, so recent days are
    re-fetched rather than trusted once -- domain/sales_fetch.py owns that rule
    and this job does not repeat it.
    """
    from domain import sales_fetch as _sf
    _app, config_path, cfg = _need("app", "config_path", "cfg")
    try:
        import accounts as _acc
    except Exception as e:
        raise RuntimeError("accounts module unavailable: %s" % e)

    conf = cfg() if callable(cfg) else cfg
    done, skipped = [], []
    for a in (_acc.load_accounts(conf, config_path) or []):
        aid = str(a.get("id") or "")
        if workspace_id and aid != workspace_id:
            continue
        # A borrowed token authenticates as the LENDER, so its sales would be
        # someone else's filed under this workspace's name.
        if not aid or not _acc.has_own_creds(a) or not _acc.seller_scope_allowed(a):
            skipped.append(aid or "(unnamed)")
            continue
        for mkt in (a.get("marketplaces") or []):
            mkt = str(mkt or "").strip().upper()
            if not mkt or mkt == "__ALL__":
                continue
            res = _sf.sync(config_path, aid, mkt,
                           _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else "",
                           _acc.account_creds(a))
            done.append({"workspace": aid, "marketplace": mkt,
                         "fetched": res.get("fetched"), "left": res.get("still_missing")})
    return {"accounts": len(done), "skipped": skipped, "detail": done[:20]}


def ads_sync(workspace_id=None):
    """Keep the advertising figures current, WITHOUT ever waiting for Amazon.

    An advertising report is commissioned, not fetched: you ask, Amazon builds
    it, and you come back. Measured on the first live pull, a daily report took
    between 9 and 14 minutes, and two attempts that waited 7 minutes both timed
    out with it still PENDING. A scheduled job cannot hold still for that.

    So each pass does two things and neither of them blocks:

        1. COLLECT what the previous pass asked for and Amazon has since built
        2. ASK for the next window

    Collect comes first so a pass always banks the previous pass's work before
    commissioning more, and the report ids live in ads_report_jobs, so a missed
    pass, a restart or a reboot loses nothing.

    Which ad products get pulled is per account and defaults to Sponsored
    Products alone -- domain/ads_sync.py owns that rule and this job does not
    repeat it.
    """
    from domain import ads_sync as _as
    _app, config_path, cfg = _need("app", "config_path", "cfg")
    try:
        import accounts as _acc
    except Exception as e:
        raise RuntimeError("accounts module unavailable: %s" % e)

    # BANK FIRST. Runs for every account at once -- a pending report knows which
    # workspace it belongs to, so there is nothing to iterate here.
    got = _as.collect_pending(config_path, workspace_id)

    conf = cfg() if callable(cfg) else cfg
    asked, skipped = [], []
    for a in (_acc.load_accounts(conf, config_path) or []):
        aid = str(a.get("id") or "")
        if not aid or (workspace_id and aid != workspace_id):
            continue
        # Not connected to the ADVERTISING API is the normal case, not an error:
        # it is a separate login from SP-API and only one account has one.
        creds, why = _as.creds_or_why(aid, config_path)
        if why:
            skipped.append(aid)
            continue
        for mkt in (a.get("marketplaces") or []):
            mkt = str(mkt or "").strip().upper()
            if not mkt or mkt == "__ALL__":
                continue
            res = _as.request_reports(aid, mkt, days=30, config_path=config_path)
            asked.append({"workspace": aid, "marketplace": mkt,
                          "requested": len(res.get("requested") or []),
                          "errors": res.get("errors") or []})
    return {"collected": len(got.get("collected") or []),
            "still_building": got.get("still_building"),
            "failed": got.get("failed") or [],
            "requested_for": asked, "not_connected": skipped}


def sourcing_check(workspace_id=None):
    """Re-read every supplier of every SKU enrolled in the repricer.

    domain/source_fetch.py owns the sweep, including the rule that enrolment
    bounds it: a SKU nobody opted in is never checked and its suppliers are never
    contacted. This job only supplies the config and gets out of the way.

    Four-hourly against a 24-hour staleness limit, so a reading has to fail six
    times running before the decision engine starts calling it stale -- which is
    the point at which it stops acting on it rather than acting on old numbers.
    """
    from domain import source_fetch as _sfetch
    _, config_path, cfg = _need("app", "config_path", "cfg")
    return _sfetch.sweep(config_path, cfg, workspace_id=workspace_id)


def sourcing_apply(workspace_id=None):
    """Push price/stock/handling changes for SKUs that have been ARMED.

    Does nothing at all unless the master switch is on AND a SKU has been moved
    out of dry run AND that SKU has a minimum price -- three separate deliberate
    acts. domain/source_apply.py owns every one of those gates; this job supplies
    the credentials and nothing else, so there is no path to Amazon that skips
    them by coming in through the timer.
    """
    from domain import source_apply as _sapply
    from domain import accounts as _acc
    app, config_path, cfg = _need("app", "config_path", "cfg")
    c = cfg() if callable(cfg) else cfg

    def creds_for(ws, mkt):
        for a in (c.get("accounts") or []):
            if str(a.get("id")) == str(ws):
                return (_acc.account_creds(a), _acc.marketplace_id(mkt),
                        str(a.get("seller_id") or ""))
        raise RuntimeError("no account called %s" % ws)

    return _sapply.run_live(config_path, cfg, creds_for, workspace_id=workspace_id)


def sourcing_listings(workspace_id=None):
    """Drop SKUs Amazon no longer has out of the repricer, by itself.

        "if the listing is deleted from my sellercentral i think the app knows
         it, so lets remove the deleted items from repricer automatically"

    It did know, and only ever when the button was pressed. Measured on jack_uk
    at the time the check was written: six of its 67 enrolled SKUs answered 404
    and the repricer was working out prices for all six.

    DAILY, AND ITS OWN JOB. One getListingsItem per enrolled SKU, which is the
    same order of cost as the fee refresh and far too much to put on the
    four-hourly pricing pass. A listing deleted this morning being noticed
    tonight is soon enough -- it is already unpriceable, and decide() refuses to
    price a SKU marked gone whether or not this has run yet.

    NOTHING IS DELETED. domain/source_run.check_listings unenrols a gone SKU and
    keeps its row, its suppliers, its history and its rule, so this is a
    reversible act taken on a 404 and nothing else. That is what makes it safe
    to do unattended -- see the note on that function.
    """
    from domain import accounts as _acc
    from domain import source_repo as _repo
    from domain import source_run as _run
    _app, config_path, cfg = _need("app", "config_path", "cfg")
    c = cfg() if callable(cfg) else cfg

    # One pass per account+marketplace that actually has enrolled SKUs, rather
    # than per account: a workspace can track SKUs on more than one marketplace
    # and each is a separate question to Amazon.
    pairs = {}
    for e in _repo.enrolled(config_path, workspace_id):
        pairs.setdefault((str(e.get("workspace_id") or ""),
                          str(e.get("marketplace") or "")), 0)
        pairs[(str(e.get("workspace_id") or ""),
               str(e.get("marketplace") or ""))] += 1

    checked = removed = unreadable = 0
    for (ws, mkt) in sorted(pairs):
        acc = _acc.get_account(c, ws)
        if not acc:
            continue
        got = _run.check_listings(config_path, acc, ws, mkt)
        if got.get("error"):
            continue          # an account that cannot be asked is not an error here
        checked += got["checked"]
        removed += len(got["removed"])
        unreadable += len(got["unreadable"])
        # SAID, NOT DONE SILENTLY. A row vanishing from the repricer with
        # nothing anywhere to explain it is a worse screen than the one that
        # showed a deleted SKU. The button says it in a toast to the person who
        # pressed it; this is the same sentence for the pass nobody watched.
        if got["removed"]:
            try:
                from domain import notify as _notify
                _notify.announce(
                    config_path, ws, _notify.LISTING_GONE,
                    "%d listing%s left the repricer"
                    % (len(got["removed"]),
                       "" if len(got["removed"]) == 1 else "s"),
                    lines=[got["note"]] + got["removed"][:20],
                    marketplace=mkt)
            except Exception:
                pass      # never let saying so undo the doing
    return {"checked": checked, "removed": removed, "unreadable": unreadable}


def sourcing_fees(workspace_id=None):
    """Ask Amazon what it charges on each enrolled product, and remember it.

    DAILY, NOT FOUR-HOURLY, and that is the whole reason this is a job of its
    own rather than a step inside sourcing_check. A referral fee is a percentage
    by CATEGORY: it does not move between one four-hour cycle and the next, and
    asking Amazon about sixty-seven products every four hours would be four
    hundred calls a day against a limit Amazon enforces -- to re-learn the same
    number. Once a day is sixty-seven.

    IT WAS WEEKLY, and a quote is now trusted for a day
    (amazon_fees.QUOTE_MAX_AGE_HOURS), so weekly would have left six days in
    seven where every product was due a refresh nothing was going to give it.
    The cadence and the age limit are the same decision and have to agree.

    rate_for_asin only re-asks where the stored answer is stale -- older than
    QUOTE_MAX_AGE_HOURS, or taken at a price the listing has since moved off --
    so a run that finds everything current costs nothing. A price change is
    therefore picked up here on its own, without anything having to tell this
    job that a price changed.

    Nothing here changes a price. It fills the cache that pricing reads, and
    pricing never calls Amazon itself -- see domain/source_run.decide_one.
    """
    from domain import amazon_fees as _fees
    from domain import source_repo as _repo
    _app, config_path, cfg = _need("app", "config_path", "cfg")

    quoted = asked = skipped = 0
    for e in _repo.enrolled(config_path, workspace_id):
        # quote_for_sku is the one place that knows how to ask about a SKU --
        # the account, our ASIN, the current price and the storing. The button
        # and the enrol route call the same function.
        _rate, basis, _detail, note = _fees.quote_for_sku(
            config_path, cfg, e.get("workspace_id"), e.get("marketplace"),
            e.get("sku"))
        if note:
            skipped += 1
            continue
        asked += 1
        if basis == _fees.QUOTED:
            quoted += 1
    return {"asked": asked, "quoted": quoted, "skipped": skipped}


register_job("sourcing_listings", sourcing_listings, hours=24,
             description="Drop SKUs Amazon no longer has out of the repricer "
                         "(daily)")
register_job("sourcing_check", sourcing_check, hours=4,
             description="Re-read supplier prices and stock for enrolled SKUs")
register_job("sourcing_fees", sourcing_fees, hours=24,
             description="Refresh Amazon's fee quote for each enrolled SKU (daily)")
register_job("sourcing_apply", sourcing_apply, hours=4,
             description="Push repricer changes for armed SKUs (off unless armed)")
register_job("sales_sync", sales_sync, hours=6,
             description="Pull daily sales and traffic from Amazon")
register_job("catalog_sync", catalog_sync, hours=6,
             description="Pull live listing data from Amazon")
register_job("asin_monitor", asin_monitor_check, hours=4,
             description="Check tracked ASINs for seller changes")
register_job("inventory_sync", inventory_sync, hours=24,
             description="Pull FBA inventory levels")
# EVERY 6 HOURS, NOT 24. The job is two non-blocking halves and the collect half
# is what makes yesterday's spend appear -- running it four times a day means a
# report commissioned at one pass is banked at the next rather than a day later.
# It costs two report requests per account per pass, which is well inside
# Amazon's reporting limits.
register_job("ads_sync", ads_sync, hours=6,
             description="Collect finished Amazon advertising reports and "
                         "commission the next ones (never waits)")


def register_jobs(app, workspace_ids=None, config_path=None, cfg=None):
    """Attach /jobs/status and /jobs/run/<job_type>, and start the timers.

    NOT /sync/*. The app already owns that prefix for AMAZON sync -- pulling a
    listing's live data back from Seller Central -- and it already has a
    /sync/status endpoint. These are background JOBS, a different thing, and
    naming them apart keeps both readable. Registering on /sync/status crashed
    the beta at startup with an endpoint collision, which is how this was found.
    """
    from flask import jsonify

    # The jobs reach the real code through these; APScheduler gives them no
    # context of its own.
    bind(app=app, config_path=config_path, cfg=cfg)

    @app.route("/jobs/status")
    def jobs_status():
        return jsonify({"ok": True, **status()})

    @app.route("/jobs/run/<job_type>", methods=["POST"])
    def jobs_run(job_type):
        from flask import request
        ws = (request.get_json(silent=True) or {}).get("workspace_id")
        res = run_job(job_type, ws)
        return jsonify(res), (200 if res.get("ok") else 500)

    return start(workspace_ids)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _soon(seconds):
    import datetime as _dt
    return _dt.datetime.now() + _dt.timedelta(seconds=seconds)


def _age(ts):
    if not ts:
        return None
    try:
        return max(0, int(time.time() - time.mktime(time.strptime(str(ts)[:19],
                                                    "%Y-%m-%d %H:%M:%S"))))
    except Exception:
        return None
