"""listing/run_status.py — the honest answer to "is it actually running?"

PLAIN ENGLISH
-------------
The dashboard used to infer whether a run was alive from the text scrolling in
the log panel. That is not evidence. Twice now the generator froze solid while
the panel simply stopped -- looking identical to "quietly working on a slow
row". You had no way to tell the difference without me reading a stack trace.

This module makes the run report its own pulse to a small file on disk, and
nothing else. That matters: the log panel travels down the same pipe that keeps
jamming, so it can never be trusted to report on its own health. A file write
does not go through the pipe, so a jammed pipe cannot fake it.

Two independent facts are then combined:

    1. WHEN did the run last do anything?   (from the heartbeat file)
    2. IS the process actually alive?       (asked of the operating system)

Those two give an honest verdict a frozen pipe cannot lie about:

    RUNNING  process alive, heartbeat recent
    STALLED  process alive, but silent far too long  <-- the freeze, named
    STOPPED  process is gone (finished, crashed, or killed)
    IDLE     no run

WHY IT IS ITS OWN FILE (CLAUDE.md §12): every producer and reader of run state
uses these functions. There is no second copy of the "is it alive" rule.
"""
import json
import os
import tempfile
import time

# A row takes roughly 30-60s and a Claude call alone can take 40s, so silence is
# normal in short bursts. Past this, silence is not normal -- it is the freeze.
STALL_AFTER_SECONDS = 180

# Never write more than once a second: beat() is called on every console line.
_MIN_WRITE_INTERVAL = 1.0

_last_write = [0.0]
_state = {}


def status_path(app_dir=None):
    """The heartbeat file. Sits next to config.json; safe to delete any time."""
    base = app_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "run_status.json")


def _write(path, force=False):
    now = time.time()
    if not force and (now - _last_write[0]) < _MIN_WRITE_INTERVAL:
        return
    _last_write[0] = now
    _state["ts"] = now
    try:
        # Write-then-rename so a reader never sees a half-written file.
        d = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".run_status.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_state, f)
        os.replace(tmp, path)
    except Exception:
        # A heartbeat must never be able to break the run it is reporting on.
        try:
            os.unlink(tmp)
        except Exception:
            pass


def start(total=0, mode="", app_dir=None):
    """Called once when a run begins."""
    _state.clear()
    _state.update({"state": "running", "pid": os.getpid(), "mode": mode,
                   "idx": 0, "total": total, "sku": "", "stage": "starting",
                   "started": time.time(), "exit_code": None})
    _write(status_path(app_dir), force=True)


def beat(idx=None, total=None, sku=None, stage=None, app_dir=None, force=False):
    """Called constantly -- every console line, plus every row/stage change.

    Records the moment work last happened. Cheap: throttled to one write/second
    unless something meaningful changed.
    """
    if not _state:
        return
    changed = False
    for key, val in (("idx", idx), ("total", total), ("sku", sku), ("stage", stage)):
        if val is not None and _state.get(key) != val:
            _state[key] = val
            changed = True
    _write(status_path(app_dir), force=force or changed)


def finish(exit_code=0, summary="", app_dir=None):
    """Called when the run ends normally, so the badge says finished, not died."""
    if not _state:
        return
    _state.update({"state": "finished", "exit_code": exit_code,
                   "summary": summary[:300], "stage": "finished"})
    _write(status_path(app_dir), force=True)


def install_console_heartbeat(console, app_dir=None):
    """Make every console line refresh the pulse -- one hook, no scattered calls.

    The beat is recorded BEFORE the print runs. That is deliberate: if the print
    itself blocks (exactly what the pipe freeze does), the last recorded time is
    the last moment the run was genuinely healthy, so the age keeps climbing and
    the state correctly flips to STALLED.
    """
    original = console.print

    def _print(*args, **kwargs):
        try:
            beat(app_dir=app_dir)
        except Exception:
            pass
        return original(*args, **kwargs)

    console.print = _print
    return original


# --------------------------------------------------------------------------
# Reading side (the dashboard)
# --------------------------------------------------------------------------

def pid_alive(pid):
    """Is this process still alive? Asked of the OS, not inferred from output."""
    if not pid:
        return False
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        pass
    try:
        os.kill(int(pid), 0)          # POSIX fallback
        return True
    except OSError:
        return False
    except Exception:
        return False


def read(app_dir=None):
    """The raw heartbeat file, or {} when there has never been a run."""
    try:
        with open(status_path(app_dir), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def classify(app_dir=None, stall_after=STALL_AFTER_SECONDS, proc_alive=None):
    """Combine 'when did it last act' with 'is it alive' into an honest verdict.

    proc_alive lets the caller pass what it already knows (the dashboard holds
    the real Popen handle, which is better evidence than a PID lookup, because a
    PID can be recycled).
    """
    st = read(app_dir)
    if not st:
        return {"state": "IDLE", "detail": "no run has been started yet",
                "idx": 0, "total": 0, "sku": "", "stage": "", "age": None,
                "pid": None, "exit_code": None}

    age = max(0.0, time.time() - float(st.get("ts") or 0))
    pid = st.get("pid")
    alive = pid_alive(pid) if proc_alive is None else bool(proc_alive)
    idx, total = st.get("idx", 0), st.get("total", 0)

    out = {"idx": idx, "total": total, "sku": st.get("sku", ""),
           "stage": st.get("stage", ""), "age": round(age, 1), "pid": pid,
           "exit_code": st.get("exit_code"), "started": st.get("started"),
           "mode": st.get("mode", "")}

    if st.get("state") == "finished":
        code = st.get("exit_code")
        out.update({"state": "STOPPED",
                    "detail": (f"finished normally ({idx} of {total})"
                               if not code else
                               f"finished with exit code {code} ({idx} of {total})")})
        return out

    if not alive:
        out.update({"state": "STOPPED",
                    "detail": f"process is gone -- stopped at item {idx} of {total}"})
        return out

    if age >= stall_after:
        out.update({"state": "STALLED",
                    "detail": (f"item {idx} of {total} -- alive but NO activity for "
                               f"{_pretty(age)}. It is very likely stuck.")})
        return out

    out.update({"state": "RUNNING",
                "detail": f"item {idx} of {total} -- last activity {_pretty(age)} ago"})
    return out


def _pretty(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
