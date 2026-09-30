"""domain/finance_resync_job.py -- Finance > "Re-read 95 days" as a background job.

WHY A JOB (review, 30 Sep 2026)
The newer Finances list allows one call every two seconds, so a 95-day re-read
spends a minute or more just waiting between pages -- inside one web request,
long enough for the proxy in front of the app to give up on it while the pull
carries on unseen. The button now starts the pull and returns; the screen asks
for its progress until it finishes.

One job per account, in this process's memory: a second press while one runs
attaches to the running job instead of starting another. The last finished job
is kept so the screen can read its result.
"""
import threading
import time

_JOBS = {}  # arch-ok: module-mutable-global -- the running Re-read job per account, read by the status route; guarded by _GUARD
_GUARD = threading.Lock()


def get(account):
    """The account's current or last job, as a plain dict (a copy), or None."""
    with _GUARD:
        j = _JOBS.get(str(account or ""))
        return dict(j) if j else None


def start(account, run):
    """Start `run(log)` for the account unless one is running.

    -> (job, started). `run` receives a log(text) callback and returns the
    sync's result dict; it is called on a daemon thread and never raises out.
    """
    key = str(account or "")
    with _GUARD:
        cur = _JOBS.get(key)
        if cur and cur.get("status") == "running":
            return dict(cur), False
        job = {"account": key, "status": "running", "pages": 0, "last": "",
               "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "result": None}
        _JOBS[key] = job

    def log(text):
        with _GUARD:
            job["last"] = str(text)[:200]
            if str(text).startswith("finance page"):
                job["pages"] += 1

    def _go():
        try:
            res = run(log)
            status = "done" if (res or {}).get("ok") else "error"
        except Exception as ex:                      # never lose the thread silently
            res, status = {"ok": False, "error": str(ex)[:300]}, "error"
        with _GUARD:
            job.update({"status": status, "result": res,
                        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")})

    threading.Thread(target=_go, daemon=True, name="finance-resync-%s" % key).start()
    return dict(job), True
