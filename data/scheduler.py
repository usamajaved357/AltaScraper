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
a row to sync_jobs -- start, finish, result or error -- and /sync/status reads
back from that table rather than from anything held in memory.

APSCHEDULER IS OPTIONAL
It is not installed here yet, and an import error at startup would stop the beta
from booting at all. So the import is guarded: without APScheduler the jobs can
still be run by hand through /sync/run/<job_type>, and /sync/status reports that
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
                         "manually via /sync/run/<job_type>. pip install apscheduler"}
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
# Left as explicit stubs. Each needs the beta's SP-API wiring, which does not
# exist until dashboard_beta.py is built, and a stub that returns "not
# implemented" is honest -- one that silently returns success would make
# /sync/status show green for work that never happened.

def catalog_sync(workspace_id=None):
    """Pull live listing data from SP-API. Buy box price, offers, status."""
    raise NotImplementedError(
        "catalog_sync needs the beta's SP-API client, wired in dashboard_beta.py")


def asin_monitor_check(workspace_id=None):
    """Check tracked ASINs for seller changes."""
    raise NotImplementedError(
        "asin_monitor_check needs the beta's SP-API client")


def inventory_sync(workspace_id=None):
    """Pull FBA inventory levels."""
    raise NotImplementedError(
        "inventory_sync needs the beta's SP-API client")


register_job("catalog_sync", catalog_sync, hours=6,
             description="Pull live listing data from Amazon")
register_job("asin_monitor", asin_monitor_check, hours=4,
             description="Check tracked ASINs for seller changes")
register_job("inventory_sync", inventory_sync, hours=24,
             description="Pull FBA inventory levels")


def register_jobs(app, workspace_ids=None):
    """Attach /sync/status and /sync/run/<job_type>, and start the timers."""
    from flask import jsonify

    @app.route("/sync/status")
    def sync_status():
        return jsonify({"ok": True, **status()})

    @app.route("/sync/run/<job_type>", methods=["POST"])
    def sync_run(job_type):
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
