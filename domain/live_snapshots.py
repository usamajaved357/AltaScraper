"""domain/live_snapshots.py -- DURABLE storage for the live Amazon catalogue.

WHY THIS EXISTS
The live catalogue used to be held in exactly two volatile places: a module-level
dict in dashboard.py (`_LIVE_CACHE`, 30-minute TTL) and a JavaScript variable in
the browser (`LIVE_STORE`). A page reload emptied the browser copy; thirty
minutes, a container restart or a redeploy emptied the server copy. Nothing was
ever written to disk, so a Sync that fetched 64 listings could show 16 an hour
later with no error -- the app had simply forgotten, and then re-answered from a
stale Amazon report.

That hurts most on the live server. On Render the container restarts on every
deploy, on health-check failures and on instance recycling, and each restart
takes the whole cache with it.

WHERE IT WRITES
Beside config.json, i.e. the persistent disk on Render (CONFIG_PATH=/data/...),
matching what listing/sync.py already does for its own snapshots. Nothing is
written next to the code, so a redeploy never wipes it.

CONCURRENCY
dashboard.py serves with app.run(threaded=True): one process, many threads. So
in-process state is guarded by a lock, and every file write goes to a temporary
file in the same directory and is then os.replace()d over the target -- atomic on
both Windows and Linux, so a crash or a concurrent read can never observe a
half-written file.

This module stores and returns data. It makes no Amazon calls and holds no
opinion about freshness -- the caller decides what is too old, and every record
carries the timestamp needed to decide.
"""
import json
import os
import tempfile
import threading
import time

_FILE = "live_snapshots.json"
_LOCK = threading.RLock()
_MEM = {"path": None, "data": None}      # process-local mirror of the file


def _path(config_path):
    return os.path.join(os.path.dirname(os.path.abspath(str(config_path))), _FILE)


def _read_all(config_path):
    """Whole store, read through the process-local mirror."""
    p = _path(config_path)
    with _LOCK:
        if _MEM["path"] == p and isinstance(_MEM["data"], dict):
            return _MEM["data"]
        data = {}
        try:
            with open(p, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}          # missing or corrupt file is simply "no snapshots yet"
        _MEM["path"], _MEM["data"] = p, data
        return data


def _write_all(config_path, data):
    """Atomic whole-store write: temp file in the same dir, then os.replace()."""
    p = _path(config_path)
    d = os.path.dirname(p)
    try:
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".live_snapshots.", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, p)          # atomic on Windows and Linux
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        return True
    except Exception:
        return False                    # persistence is best-effort, never fatal


def key(account_id, marketplace):
    return f"{account_id}::{str(marketplace or '').upper()}"


def save(config_path, account_id, marketplace, items, report_source="",
         partial=False, warnings=None):
    """Store one account+marketplace catalogue. Returns the stored record.

    A PARTIAL result never overwrites a COMPLETE one that has more listings. That
    is the specific guard against the 64 -> 16 collapse: when the inactive-report
    half fails, the short list is not allowed to erase the full list already on
    disk -- it is kept as a fallback and reported as partial instead.
    """
    rec = {
        "items": list(items or []),
        "count": len(items or []),
        "ts": time.time(),
        "report_source": report_source or "",
        "partial": bool(partial),
        "warnings": list(warnings or []),
    }
    with _LOCK:
        data = dict(_read_all(config_path))
        k = key(account_id, marketplace)
        prev = data.get(k) or {}
        if (rec["partial"] and not prev.get("partial")
                and int(prev.get("count") or 0) > rec["count"]):
            prev = dict(prev)
            prev["superseded_by_partial_at"] = rec["ts"]
            prev["last_partial_count"] = rec["count"]
            data[k] = prev
            _MEM["data"] = data
            _write_all(config_path, data)
            return prev
        data[k] = rec
        _MEM["data"] = data
        _write_all(config_path, data)
    return rec


def get(config_path, account_id, marketplace):
    """The stored record for one account+marketplace, or None."""
    rec = _read_all(config_path).get(key(account_id, marketplace))
    return rec if isinstance(rec, dict) else None


def age_seconds(rec):
    """How old a record is, or None when there is no usable timestamp."""
    try:
        return max(0.0, time.time() - float((rec or {}).get("ts") or 0)) if rec else None
    except Exception:
        return None


def summary(config_path):
    """Every stored key with its count and age -- for diagnostics/health views."""
    out = []
    for k, rec in (_read_all(config_path) or {}).items():
        if not isinstance(rec, dict):
            continue
        out.append({"key": k, "count": rec.get("count", 0), "ts": rec.get("ts"),
                    "age_seconds": age_seconds(rec), "partial": rec.get("partial", False)})
    return sorted(out, key=lambda r: r["key"])
