"""domain/miles_runlog.py -- persistent Miles harvest/generate run logs.

Problem this solves: the old /miles/generate ran the CLI subprocess and read its stdout
INSIDE the request-bound SSE generator, and on browser disconnect it TERMINATED the process.
So reloading/navigating away aborted the run AND lost the log (nothing was saved).

Design: start() spawns the subprocess plus a DAEMON reader thread. The thread -- not the SSE
request -- owns the process I/O: it appends every line to a per-run .log file and updates a
.json status (uploaded source, counts, per-SKU outcome). Because the reader is detached, the
run KEEPS GOING and KEEPS LOGGING when the browser leaves. The SSE endpoint merely TAILS the
in-memory buffer, so any connect/reconnect replays the same persistent history.

Files live under <base_dir>/miles_runs/ (gitignored local data):
  <run_id>.log   -- full human-readable log (header names the uploaded file + time)
  <run_id>.json  -- {id, source, started, state, total, counts, skus:{sku:{status,detail}}}
  <run_id>.csv   -- one row per SKU (written on demand)
"""
import os
import re
import csv
import json
import threading
import subprocess
import datetime

_RUNS = {}                      # run_id -> entry dict (in-memory, this process)
_LOCK = threading.Lock()
_ACTIVE = {"id": None}

# ---- per-SKU status parsing from the CLI's log lines -------------------------
_RE_PROGRESS = re.compile(r"^\[(\d+)/(\d+)\]\s+([A-Za-z0-9._-]+)")          # [35/159] MSF1308003
_RE_GENPROG  = re.compile(r"^\[(\d+)/(\d+)\][^\n]*::\s*([A-Za-z0-9._-]+)")  # [34/106] BRAND ... :: MSF1532003
_RE_WROTE    = re.compile(r"WROTE draft for\s+([A-Za-z0-9._-]+)", re.I)     # generation wrote a listing
_RE_NOTFOUND = re.compile(r"\[([A-Za-z0-9._-]+)\][^\n]*?NOT[_ ]?FOUND", re.I)
_RE_REVIEW   = re.compile(r"\[([A-Za-z0-9._-]+)\][^\n]*?(NEEDS_REVIEW|need[s]? review|\d+\s+product matches|duplicate)", re.I)
_RE_FILE     = re.compile(r"\[([A-Za-z0-9._-]+)\]\s+(SDS|TDS|OTHER)\s*:", re.I)   # a doc was captured
_RE_WRITTEN  = re.compile(r"\b(OK)\b[^\n]*Written|listing written|\bwrote\b", re.I)
_RE_SKU_WROTE= re.compile(r"(?:SKU|sku)[=:\s]+([A-Za-z0-9._-]+)")


def _runs_dir(base_dir):
    d = os.path.join(str(base_dir), "miles_runs")
    os.makedirs(d, exist_ok=True)
    return d


def _new_id(source_name):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (source_name or "run")).strip("_")[:40] or "run"
    return f"{ts}_{safe}"


def _save_meta(entry):
    try:
        with open(entry["metaf"], "w", encoding="utf-8") as f:
            json.dump(entry["meta"], f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def _bump(meta, key):
    meta["counts"][key] = meta["counts"].get(key, 0) + 1


def _set_sku(meta, sku, status, detail=""):
    """Set a SKU's status, but never downgrade a terminal outcome back to 'processing'."""
    cur = meta["skus"].get(sku, {})
    if cur.get("status") in ("not_found", "harvested", "generated", "review") and status == "processing":
        return
    meta["skus"][sku] = {"status": status, "detail": (detail or cur.get("detail", ""))[:160]}


# Bracketed STATUS markers the CLI emits ([done], [start], [check]...) are NOT SKUs.
# Real SKUs always contain a digit (MSF1308003, M00600205, MM2001203); markers don't --
# so "has a digit and isn't a known marker word" cleanly separates them.
_MARKERS = {"done", "start", "check", "limit", "busy", "error", "note", "items",
            "image", "ba", "warn", "info", "end", "ok", "drive-check", "stop"}

def _is_sku(tok):
    t = (tok or "").strip()
    return bool(t) and t.lower() not in _MARKERS and bool(re.search(r"\d", t))


def _parse(meta, line):
    # generation progress ("[i/N] BRAND ... :: SKU") -- check FIRST because it also matches
    # the plain [i/N] shape; the SKU is after the "::".
    mg = _RE_GENPROG.match(line)
    if mg and _is_sku(mg.group(3)):
        try: meta["total"] = int(mg.group(2))
        except Exception: pass
        _set_sku(meta, mg.group(3), "processing")
    else:
        m = _RE_PROGRESS.match(line)
        if m and _is_sku(m.group(3)):
            try: meta["total"] = int(m.group(2))
            except Exception: pass
            _set_sku(meta, m.group(3), "processing")
    m = _RE_WROTE.search(line)
    if m and _is_sku(m.group(1)):
        _set_sku(meta, m.group(1), "generated", line)
    m = _RE_NOTFOUND.search(line)
    if m and _is_sku(m.group(1)):
        _set_sku(meta, m.group(1), "not_found", line)
    m = _RE_REVIEW.search(line)
    if m and _is_sku(m.group(1)):
        _set_sku(meta, m.group(1), "review", line)
    m = _RE_FILE.search(line)
    if m and _is_sku(m.group(1)):
        # a doc was captured for this SKU -> it was found & harvested
        cur = meta["skus"].get(m.group(1), {})
        if cur.get("status") != "generated":
            _set_sku(meta, m.group(1), "harvested", line)


def _reader(entry):
    """Owns the subprocess stdout. Runs on a daemon thread, so it survives request
    disconnects and keeps writing the log + status until the process exits."""
    proc = entry["proc"]
    meta = entry["meta"]
    try:
        lf = open(entry["logf"], "w", encoding="utf-8")
        lf.write(f"# Miles run {meta['id']}\n# source: {meta['source']}\n"
                 f"# started: {meta['started']}\n# args: {' '.join(meta.get('args') or [])}\n\n")
        lf.flush()
        for raw in iter(proc.stdout.readline, ""):
            line = raw.rstrip("\n")
            if not line:
                continue
            with entry["lock"]:
                entry["lines"].append(line)
            try:
                lf.write(line + "\n"); lf.flush()
            except Exception:
                pass
            _parse(meta, line)
            # cheap throttled meta save (every line is fine -- files are small)
            _save_meta(entry)
        proc.wait()
        meta["state"] = "done"
        meta["exit"] = proc.returncode
    except Exception as e:
        meta["state"] = "error"
        meta["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    finally:
        # roll processing -> found-but-not-generated summary counts
        c = {"harvested": 0, "not_found": 0, "review": 0, "generated": 0, "processing": 0}
        for s in meta["skus"].values():
            c[s.get("status", "processing")] = c.get(s.get("status", "processing"), 0) + 1
        meta["counts"] = c
        meta["ended"] = datetime.datetime.now().isoformat(timespec="seconds")
        _save_meta(entry)
        try: entry["_lf"] = None; lf.close()
        except Exception: pass
        with _LOCK:
            if _ACTIVE["id"] == meta["id"]:
                _ACTIVE["id"] = None


def start(base_dir, source_name, args):
    """Spawn the CLI subprocess + detached reader thread. Returns run_id."""
    d = _runs_dir(base_dir)
    rid = _new_id(source_name)
    meta = {"id": rid, "source": source_name or "",
            "started": datetime.datetime.now().isoformat(timespec="seconds"),
            "args": list(args), "state": "running", "total": None,
            "counts": {}, "skus": {}}
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            cwd=str(base_dir))
    entry = {"proc": proc, "meta": meta, "lines": [], "lock": threading.Lock(),
             "logf": os.path.join(d, rid + ".log"),
             "metaf": os.path.join(d, rid + ".json")}
    with _LOCK:
        _RUNS[rid] = entry
        _ACTIVE["id"] = rid
    t = threading.Thread(target=_reader, args=(entry,), daemon=True, name=f"miles-run-{rid}")
    t.start()
    entry["thread"] = t
    return rid


def _lines_from_chunk(chunk):
    """Pull the human-readable text line(s) out of an SSE chunk ('data: <line>\\n\\n').
    'event:' control lines (e.g. the 'event: end' terminator) carry no log text."""
    out = []
    for raw in str(chunk).split("\n"):
        raw = raw.rstrip("\r")
        if raw.startswith("data:"):
            t = raw[5:].lstrip()
            if t and t != "end":
                out.append(t)
    return out


def run_stream(base_dir, source_name, gen_factory, args=None):
    """Run an SSE generator function (the route's existing stream()) on a DAEMON thread,
    teeing every yielded chunk to a persistent run log. Returns (run_id, tailer):
      - the background thread runs gen_factory() to completion EVEN IF the client
        disconnects, so the run never stops on reload and the log is always saved;
      - `tailer` is a generator that yields the SSE chunks for the Response and ends when
        the run is done (or the client goes away -- which does NOT stop the thread).
    """
    import time as _t
    d = _runs_dir(base_dir)
    rid = _new_id(source_name)
    meta = {"id": rid, "source": source_name or "",
            "started": datetime.datetime.now().isoformat(timespec="seconds"),
            "args": list(args or []), "state": "running", "total": None,
            "counts": {}, "skus": {}}
    entry = {"proc": None, "meta": meta, "lines": [], "chunks": [],
             "lock": threading.Lock(), "done": False,
             "logf": os.path.join(d, rid + ".log"), "metaf": os.path.join(d, rid + ".json")}
    with _LOCK:
        _RUNS[rid] = entry
        _ACTIVE["id"] = rid

    def _worker():
        lf = None
        try:
            lf = open(entry["logf"], "w", encoding="utf-8")
            lf.write(f"# Miles run {rid}\n# source: {meta['source']}\n"
                     f"# started: {meta['started']}\n\n"); lf.flush()
            for chunk in gen_factory():
                with entry["lock"]:
                    entry["chunks"].append(chunk)
                for ln in _lines_from_chunk(chunk):
                    with entry["lock"]:
                        entry["lines"].append(ln)
                    try: lf.write(ln + "\n"); lf.flush()
                    except Exception: pass
                    _parse(meta, ln)
                _save_meta(entry)
            if meta["state"] == "running":
                meta["state"] = "done"
        except Exception as e:
            meta["state"] = "error"
            meta["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        finally:
            c = {"harvested": 0, "not_found": 0, "review": 0, "generated": 0, "processing": 0}
            for s in meta["skus"].values():
                k = s.get("status", "processing"); c[k] = c.get(k, 0) + 1
            meta["counts"] = c
            meta["ended"] = datetime.datetime.now().isoformat(timespec="seconds")
            entry["done"] = True
            _save_meta(entry)
            try:
                if lf: lf.close()
            except Exception: pass
            with _LOCK:
                if _ACTIVE["id"] == rid:
                    _ACTIVE["id"] = None

    threading.Thread(target=_worker, daemon=True, name=f"miles-run-{rid}").start()

    def tailer():
        # first hand the client its run id so the page can re-attach after a reload
        yield f"data: [runid] {rid}\n\n"
        i = 0
        while True:
            with entry["lock"]:
                new = entry["chunks"][i:]; i = len(entry["chunks"])
            for c in new:
                yield c
            if entry["done"] and i >= len(entry["chunks"]):
                break
            _t.sleep(0.4)
        yield "event: end\ndata: end\n\n"

    return rid, tailer()


def active_id():
    return _ACTIVE.get("id")


def is_running(rid):
    e = _RUNS.get(rid)
    return bool(e and e["meta"].get("state") == "running")


def tail(rid, frm=0):
    """Return new log lines since index `frm` + current status. Powers SSE re-attach."""
    e = _RUNS.get(rid)
    if not e:
        return {"ok": False, "lines": [], "next": frm, "state": "unknown"}
    with e["lock"]:
        lines = e["lines"][frm:]
        nxt = len(e["lines"])
    m = e["meta"]
    return {"ok": True, "lines": lines, "next": nxt, "state": m.get("state"),
            "total": m.get("total"), "counts": m.get("counts", {}),
            "done": sum(1 for s in m["skus"].values() if s.get("status") in ("harvested","generated","not_found","review"))}


def status(rid):
    e = _RUNS.get(rid)
    if e:
        return e["meta"]
    return None


def stop(rid):
    """Explicit user stop -- terminate the subprocess (unlike a browser disconnect)."""
    e = _RUNS.get(rid)
    if not e:
        return False
    try:
        if e["proc"].poll() is None:
            e["proc"].terminate()
        e["meta"]["state"] = "stopped"
        _save_meta(e)
        return True
    except Exception:
        return False


def list_runs(base_dir, limit=30):
    """List past runs (newest first) from the metadata files on disk."""
    d = _runs_dir(base_dir)
    out = []
    try:
        for fn in sorted(os.listdir(d), reverse=True):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    m = json.load(f)
                out.append({"id": m.get("id"), "source": m.get("source"),
                            "started": m.get("started"), "ended": m.get("ended"),
                            "state": m.get("state"), "total": m.get("total"),
                            "counts": m.get("counts", {})})
            except Exception:
                continue
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out


def read_log(base_dir, rid):
    p = os.path.join(_runs_dir(base_dir), rid + ".log")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def write_csv(base_dir, rid):
    """Write/refresh a per-SKU CSV for a run; return its path (or '')."""
    d = _runs_dir(base_dir)
    meta = None
    e = _RUNS.get(rid)
    if e:
        meta = e["meta"]
    else:
        try:
            with open(os.path.join(d, rid + ".json"), encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            return ""
    path = os.path.join(d, rid + ".csv")
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sku", "status", "detail"])
            for sku, s in sorted((meta.get("skus") or {}).items()):
                w.writerow([sku, s.get("status", ""), s.get("detail", "")])
        return path
    except Exception:
        return ""
