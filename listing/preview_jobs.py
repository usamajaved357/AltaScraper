"""listing/preview_jobs.py — per-listing Preview/Submit as SERVER-SIDE background jobs.

Preview/Submit used to be a live browser connection: leaving the detail page cut the
stream and the progress vanished, and a second Preview was refused instead of queued.
This runs each Preview/Submit as a JOB in a registry that lives on the SERVER, so its
progress survives navigating away, closing the drawer, or a full page reload -- any
browser reads it by polling. Jobs run ONE AT A TIME through a FIFO queue, serialised
against every other run by the existing global run lock. Mirrors the auto-fix model.

configure(...) must be called once at startup to inject the run-lock handles.
"""
import threading
import subprocess
import time

_LOCK = threading.Lock()       # guards the registry/queue below
_JOBS = {}                     # id -> job dict
_QUEUE = []                    # ids waiting to run (FIFO)
_ORDER = []                    # every id in creation order (for listing / pruning)
_WORKER = {"n": 0}      # how many worker threads are alive right now
_SEQ = {"n": 0}
_DEPS = {}                     # injected run-lock handles (see configure)
_MAX_JOBS = 200                # bound the registry
_MAX_LOG = 2000                # bound each job's captured log


def configure(*, acquire_lock, run_lock, running, ansi_re):
    """Inject the existing global run-lock handles so preview jobs serialise against
    SSE runs / generate / auto-fix exactly like the live endpoint does.
      acquire_lock : callable() -> bool (the app's _acquire_run_lock)
      run_lock     : threading.Lock (the app's _run_lock)
      running      : the app's _running dict ({on, proc, started})
      ansi_re      : compiled regex that strips ANSI colour codes from child output
    """
    _DEPS["acquire_lock"] = acquire_lock
    _DEPS["run_lock"] = run_lock
    _DEPS["running"] = running
    _DEPS["ansi_re"] = ansi_re


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _public(j):
    """Job view without the internal argv."""
    return {k: v for k, v in j.items() if k != "_args"}


def enqueue(sku, mode, args, label="", account_id="", owner=""):
    """Create a job and add it to the FIFO queue. Returns the job id. Starts the worker
    thread if it isn't already running.

    account_id and owner are recorded so the run can be keyed per account and per
    SKU rather than against one global lock, and so Stop can tell whose run it is.
    """
    with _LOCK:
        _SEQ["n"] += 1
        jid = "pj%d" % _SEQ["n"]
        _JOBS[jid] = {"id": jid, "sku": sku, "mode": mode, "label": label or sku,
                      "status": "queued", "log": [], "summary": "", "exit_code": None,
                      "created": _now(), "started": "", "ended": "", "_args": list(args),
                      "account_id": str(account_id or ""), "owner": str(owner or "")}
        _QUEUE.append(jid)
        _ORDER.append(jid)
        _prune_locked()
    _ensure_workers()
    return jid


def _prune_locked():
    # drop oldest FINISHED jobs beyond the cap (never a queued/running one)
    while len(_ORDER) > _MAX_JOBS:
        old = _ORDER[0]
        if _JOBS.get(old, {}).get("status") in ("queued", "running"):
            break
        _ORDER.pop(0)
        _JOBS.pop(old, None)


def _ensure_workers():
    """Keep enough workers alive to fill the available run slots.

    There was exactly ONE worker thread, so even after the global lock was split
    per account and per SKU, jobs would still have come off the queue one at a
    time -- the queue itself was the bottleneck. The number of workers follows
    the slot limit, so the two cannot disagree.
    """
    try:
        from domain.run_slots import total_limit
        want = total_limit()
    except Exception:
        want = 1
    to_start = 0
    with _LOCK:
        # Never more workers than there is work for, and never more than the
        # slot limit -- a worker beyond that would only sit spinning on acquire().
        need = min(want, _WORKER["n"] + len(_QUEUE))
        while _WORKER["n"] < need:
            _WORKER["n"] += 1
            to_start += 1
    for _ in range(to_start):
        threading.Thread(target=_worker, daemon=True).start()


def _worker():
    while True:
        with _LOCK:
            jid = _QUEUE.pop(0) if _QUEUE else None
            if jid is None:
                _WORKER["n"] = max(0, _WORKER["n"] - 1)
                return
            job = _JOBS.get(jid)
        if not job or job.get("status") == "cancelled":
            continue
        _run_one(job)


def _run_one(job):
    acquire = _DEPS.get("acquire_lock")
    run_lock = _DEPS.get("run_lock")
    running = _DEPS.get("running")
    ansi = _DEPS.get("ansi_re")

    # Wait for a run slot. Keyed on THIS job's account and SKU, so a job only
    # waits for work that would genuinely collide with it -- the same listing, or
    # the same Amazon account already at its quota -- instead of for whatever
    # single run happened to be going anywhere in the app.
    waited = 0
    while acquire is not None and not acquire(job.get("account_id", ""),
                                              job.get("sku", "")):
        if job.get("status") == "cancelled":
            job["ended"] = _now()
            return
        time.sleep(1.0)
        waited += 1
        if waited > 600:   # 10 min ceiling waiting for another run to end
            job["status"] = "error"
            job["summary"] = "timed out waiting for another run to finish"
            job["ended"] = _now()
            return

    job["status"] = "running"
    job["started"] = _now()
    # Emit a [start] marker (mirrors the live SSE endpoint) so the log shows the command AND
    # the frontend knows the run actually launched -- without it the panel wrongly reported
    # "The run didn't start" even though the job ran to completion.
    job["log"].append("[start] " + " ".join(str(a) for a in job.get("_args", [])))
    p = None
    try:
        # Decode the child's stdout as UTF-8 explicitly. On Windows text=True defaults to
        # the ANSI code page (cp1252), which turns the generator's '…' (UTF-8 E2 80 A6)
        # into mojibake 'â€¦' in the log. errors="replace" keeps a stray byte from killing
        # the whole line.
        p = subprocess.Popen(job["_args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace", bufsize=1)
        if running is not None:
            running["proc"] = p
        try:
            p.stdin.close()   # api / api_submit need no stdin (only generate prompts for a brand)
        except Exception:
            pass
        for line in iter(p.stdout.readline, ""):
            clean = ansi.sub("", line.rstrip("\n")) if ansi is not None else line.rstrip("\n")
            if clean.strip():
                job["log"].append(clean)
                if len(job["log"]) > _MAX_LOG:
                    del job["log"][0:len(job["log"]) - _MAX_LOG]
            if job.get("status") == "cancelled":
                try:
                    p.terminate()
                except Exception:
                    pass
                break
        p.wait()
        job["exit_code"] = p.returncode
        summ = ""
        for ln in reversed(job["log"]):
            if "complete --" in ln.lower():
                summ = ln
                break
        if not summ and job["log"]:
            summ = job["log"][-1]
        job["summary"] = summ
        if job.get("status") != "cancelled":
            job["status"] = "done"
    except Exception as e:
        job["status"] = "error"
        job["summary"] = "job failed: " + str(e)[:200]
    finally:
        job["ended"] = _now()
        # release the global run lock (mirror the SSE endpoint's finally)
        if running is not None:
            if run_lock is not None:
                with run_lock:
                    running["proc"] = None
                    running["on"] = False
            else:
                running["proc"] = None
                running["on"] = False


# ---- read API (for the routes) ----
def get(jid):
    with _LOCK:
        j = _JOBS.get(jid)
        return _public(j) if j else None


def by_sku(sku):
    """Most recent job for a SKU (so reopening a drawer re-attaches to its run)."""
    with _LOCK:
        for jid in reversed(_ORDER):
            j = _JOBS.get(jid)
            if j and str(j.get("sku")) == str(sku):
                return _public(j)
    return None


def list_jobs(limit=100):
    """Metadata for every job (newest first), without the full log -- for the global panel."""
    with _LOCK:
        qpos = {jid: i for i, jid in enumerate(_QUEUE)}
        out = []
        for jid in reversed(_ORDER):
            j = _JOBS.get(jid)
            if not j:
                continue
            row = {k: v for k, v in j.items() if k not in ("_args", "log")}
            row["log_lines"] = len(j.get("log", []))
            row["queue_pos"] = qpos.get(jid)
            out.append(row)
            if len(out) >= limit:
                break
    return out


def counts():
    with _LOCK:
        running = sum(1 for j in _JOBS.values() if j.get("status") == "running")
        return {"running": running, "queued": len(_QUEUE), "total": len(_ORDER)}


def stop(jid):
    """Cancel a queued or running job. Returns True if it was cancellable."""
    with _LOCK:
        j = _JOBS.get(jid)
        if not j:
            return False
        if j.get("status") in ("queued", "running"):
            j["status"] = "cancelled"
            if jid in _QUEUE:
                _QUEUE.remove(jid)
            return True
    return False
