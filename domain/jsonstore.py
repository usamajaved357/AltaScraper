"""domain/jsonstore.py -- one place that reads and writes small JSON files safely.

WHY THIS EXISTS
Two things now need durable JSON beside config.json: the live-catalogue snapshots
(domain/live_snapshots.py) and the user accounts (auth/users.py). Both need the
same three properties, and getting any of them subtly different in two files is
exactly the kind of duplicated logic that rots:

  1. It must live BESIDE config.json, i.e. on Render's persistent disk
     (CONFIG_PATH=/data/...). Anything written next to the code is wiped by the
     next deploy.
  2. A write must be atomic. We write a temp file in the SAME directory and then
     os.replace() it over the target -- atomic on both Windows and Linux -- so a
     crash or a concurrent reader can never see half a file. Writing in place
     would mean a power cut could leave you with no user accounts at all.
  3. A missing or corrupt file must read as "nothing stored yet", never as a
     crash. The app has to start even if the file was hand-edited badly.

This module stores bytes. It holds no opinion about what is in them.
"""
import json
import os
import tempfile


def path_beside_config(config_path, filename):
    """Where `filename` lives: the same directory as config.json."""
    return os.path.join(os.path.dirname(os.path.abspath(str(config_path))), filename)


def read_json(path, default=None):
    """Parse `path`, or return `default` if it is missing, empty or unparseable."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def write_json_atomic(path, data, indent=None):
    """Write `data` to `path` atomically. Returns True on success, False otherwise.

    Never raises: callers treat persistence as best-effort and decide for
    themselves whether a failure is fatal.
    """
    try:
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".jsonstore.", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=indent)
            os.replace(tmp, path)          # atomic on Windows and Linux
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        return True
    except Exception:
        return False
