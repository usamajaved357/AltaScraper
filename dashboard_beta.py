"""dashboard_beta.py -- the same app, on SQLite instead of Google Sheets.

    python dashboard_beta.py            -> http://127.0.0.1:5001

    localhost:5000  the live app, Google Sheets, untouched
    localhost:5001  this, the database beta

WHY THIS FILE IS FORTY LINES AND NOT THREE THOUSAND
The migration brief said to copy dashboard.py and edit the copy. That would have
forked about 3,950 lines between the two versions, and from the first bug fix
onward they would drift -- every change needing to be made twice, and silently
wrong if it were not.

It turned out not to be necessary. Route modules in this app are already handed
their dependencies (register(app, *, _ws=..., _records=...)), which is exactly
the seam a backend swap needs. The only thing standing in the way was that
dashboard.py did its wiring inside `if __name__ == "__main__":`, so importing it
gave you an app with no routes. Moving that wiring into build_app() -- a pure
move, verified line for line -- means this file can just call it.

So: one codebase, two backends. A fix to a route helps both.

WHAT IS SHARED, NOT COPIED
Everything. dashboard.py, all of routes/, amazon_listing_generator.py, listing/,
static/ and templates/. The ONLY difference between the two apps is which pair of
functions supplies the rows.
"""
import logging
import os
import sys
import time

_STARTED = time.time()

# Announce the backend BEFORE building, so a mistake is visible in the terminal
# rather than discovered later by wondering why the sheet is not updating.
print("\n  AltaScraper BETA -- data backend: SQLite")

import dashboard as _d                      # noqa: E402  (after the banner)
from data import db as _db                  # noqa: E402
from data import scheduler as _sched        # noqa: E402
from data.column_map import verify_column_map  # noqa: E402

PORT = int(os.environ.get("BETA_PORT", "5001"))
HOST = os.environ.get("BETA_HOST", _d.HOST)

# The mapping is what keeps every g('...') call site working. A gap in it does
# not raise -- it just makes one column of data silently vanish -- so it is
# checked at startup rather than trusted.
_ok, _problems = verify_column_map(_d.FIXED_HEADERS if hasattr(_d, "FIXED_HEADERS")
                                   else __import__("amazon_listing_generator").FIXED_HEADERS)
if not _ok:
    print("\n  REFUSING TO START -- the column map no longer matches FIXED_HEADERS:")
    for p in _problems:
        print("    " + p)
    print("  Fix data/column_map.py. Starting anyway would silently lose that "
          "column's data on every read.\n")
    sys.exit(2)

app = _d.build_app(backend="db")

# Standard logging instead of Rich console output, per the brief: a file you can
# tail and ship, rather than ANSI colour codes aimed at a terminal.
logging.basicConfig(
    filename=os.environ.get("BETA_LOG", "altascraper_beta.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("altascraper.beta")


@app.after_request
def _cache_static(resp):
    """Let the browser keep static files for an hour.

    Deliberately NOT applied to anything else: the app's data endpoints must
    stay uncached or the dashboard would show stale listings after an edit --
    which is the exact failure the live-sync work was fixing.
    """
    try:
        from flask import request
        if request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=3600"
    except Exception:
        pass
    return resp


@app.route("/health")
def _health():
    """Honest liveness: reports what is actually true, not a hardcoded ok."""
    from flask import jsonify
    up = int(time.time() - _STARTED)
    st = _sched.status()
    last = None
    for j in st.get("jobs", []):
        if j.get("last_run") and (last is None or str(j["last_run"]) > str(last)):
            last = j["last_run"]
    return jsonify({
        "status": "ok" if _db.healthy() else "degraded",
        "backend": "db",
        "db": _db.healthy(),
        "db_stats": _db.stats(),
        "uptime": "%dh %dm" % (up // 3600, (up % 3600) // 60),
        "last_sync": last,
        "scheduler_running": st.get("scheduler_running"),
        "apscheduler_installed": st.get("apscheduler_installed"),
    })


if __name__ == "__main__":
    print("  database  : %s" % _db.db_path(_d.CONFIG_PATH))
    print("  listening : http://%s:%s" % (HOST, PORT))
    print("  the live app on :5000 is untouched and still using Google Sheets")

    res = _sched.register_jobs(app)
    if not res.get("ok"):
        # Not fatal: the app is fully usable, only the timers are missing, and
        # every job can still be triggered by hand at /sync/run/<job_type>.
        print("  scheduler : %s" % res.get("error"))
    else:
        print("  scheduler : %d job(s) scheduled" % res.get("jobs", 0))
    print("  (Ctrl+C to stop)\n")

    log.info("beta starting on %s:%s db=%s", HOST, PORT, _db.db_path(_d.CONFIG_PATH))
    app.run(host=HOST, port=PORT, threaded=True)
