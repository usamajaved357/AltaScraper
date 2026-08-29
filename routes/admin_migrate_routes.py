"""routes/admin_migrate_routes.py -- TEMPORARY. Run the one-off migrations from a URL.

    GET /admin/migrate?key=...            dry run, changes nothing
    GET /admin/migrate?key=...&apply=1    actually writes

WHY THIS EXISTS

The simplified-flow migrations are one-off scripts meant to be run from a shell
on the machine holding the database. Railway offers no shell on this plan and
`railway run` executes locally -- with a SQLite database on the container's
persistent volume, that reaches nothing. So the only way in is the app itself.

DELETE THIS FILE once the migration has run successfully. It is not a feature.
Removing it is: delete this file, and delete the four lines in dashboard.py that
import and register it. Nothing else refers to it.

HOW IT IS PROTECTED, and how well

  1. THE LOGIN. auth/guard.py's doorman runs before every request and this
     endpoint is not in PUBLIC_ENDPOINTS, so a signed-out visitor is redirected
     to the login page and never reaches this code. That is the real gate.
  2. THE PERMISSION. Registered in auth/guard.RULES as "approve_delete" -- the
     same permission /input/clear needs. A signed-in user without it is refused.
  3. THE KEY. A second factor, compared with hmac.compare_digest so the
     comparison is timing-safe.

BE CLEAR ABOUT THE KEY'S LIMITS. It travels in the URL, which means it lands in
server logs, any proxy in front of the app, and browser history. It is not a
secret after first use. It is here to stop an *accidental* hit on a URL that
rewrites a production database -- not to withstand anyone who has read a log.
That is why the login above it is the protection that matters, and why this file
should not outlive the migration.

WHAT IT RUNS, AND IN WHICH ORDER

  1. scripts/clear_sheet_queue.py    old source="sheet" rows out of the queue
  2. scripts/migrate_statuses.py     statuses -> the four, queue rows -> QUEUED
  3. scripts/recompute_warnings.py   every listing's warnings, every workspace

That order is load-bearing, twice over.

migrate_statuses MOVES leftover queue rows into the listings store as QUEUED, so
running it before the clear would turn stale sheet imports -- products generated
months ago -- into queued listings presented as things still to make.

And recompute_warnings must come LAST. It needs the statuses already folded into
the four and the warnings/ebay_item_id columns already added, both of which
migrate_statuses does. Run earlier it would either fail on a missing column or
compute duplicate warnings against statuses about to change underneath it.

Step 3 is also the only one that can find the duplicates at all: a duplicate
barcode, eBay item or competitor ASIN is a fact about how rows relate to EACH
OTHER, so it cannot be worked out while migrating one row. Existing listings
have no such warnings until this runs.

Both scripts are imported and their own main() is called, so this route runs
exactly the code that would run in a shell, with the same dry-run default and
the same backups (CLAUDE.md Rule 12). Nothing is reimplemented here.
"""
import hmac
import io
import os
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

from flask import request, Response

# The literal is the fallback; ADMIN_MIGRATE_KEY overrides it without a deploy.
DEFAULT_KEY = "run_migration_2026"

SCRIPTS = (
    ("clear_sheet_queue", "scripts/clear_sheet_queue.py"),
    ("migrate_statuses", "scripts/migrate_statuses.py"),
    ("recompute_warnings", "scripts/recompute_warnings.py"),
)


def _expected_key():
    return os.environ.get("ADMIN_MIGRATE_KEY") or DEFAULT_KEY


def _key_ok(given):
    # compare_digest, not ==, so the comparison does not leak the key's length
    # or its matching prefix through timing.
    return hmac.compare_digest(str(given or ""), _expected_key())


def _run_script(path, apply):
    """Import a migration script and call its own main(). Returns its output."""
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(root, path.replace("/", os.sep))
    if not os.path.exists(full):
        return "NOT FOUND: %s\n(has this branch been deployed?)\n" % path

    spec = importlib.util.spec_from_file_location("_mig_" + os.path.basename(path), full)
    mod = importlib.util.module_from_spec(spec)

    buf = io.StringIO()
    argv = [os.path.basename(path)] + (["--apply"] if apply else [])
    old_argv, old_cwd = sys.argv, os.getcwd()
    try:
        sys.argv = argv
        with redirect_stdout(buf), redirect_stderr(buf):
            spec.loader.exec_module(mod)     # module body: sets CONFIG_PATH, chdir
            mod.main()
    except SystemExit:
        pass                                  # argparse/sys.exit from main()
    except Exception:
        buf.write("\n!! THIS SCRIPT FAILED\n")
        buf.write(traceback.format_exc())
    finally:
        sys.argv = old_argv
        try:
            os.chdir(old_cwd)                 # the scripts chdir to the repo root
        except Exception:
            pass
    return buf.getvalue()


def register(app, *, CONFIG_PATH=None, _state=None):
    """Attach /admin/migrate. Delete this call when the migration is done."""

    @app.route("/admin/migrate")
    def admin_migrate():
        if not _key_ok(request.args.get("key")):
            # Deliberately terse and 404, not 403: a wrong key should not confirm
            # that there is something here to find the right key for.
            return Response("Not found\n", status=404, mimetype="text/plain")

        apply = str(request.args.get("apply") or "") in ("1", "true", "yes")

        out = io.StringIO()
        out.write("=" * 68 + "\n")
        out.write("ALTASCRAPER -- one-off migration\n")
        out.write("mode: %s\n" % ("APPLY -- writing to the database"
                                  if apply else "DRY RUN -- nothing is changed"))
        out.write("config: %s\n" % os.environ.get("CONFIG_PATH", "config.json"))
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
            from data import db as _db
            out.write("database: %s\n" % _db.db_path(
                os.environ.get("CONFIG_PATH", "config.json")))
        except Exception as e:
            out.write("database: could not resolve (%s)\n" % str(e)[:120])
        out.write("=" * 68 + "\n\n")

        # WHICH DATABASE, SAID BEFORE THE RESULTS. Every wrong-target incident in
        # this project looked like a clean success against the wrong data; the
        # path above is what makes that checkable from the output alone.
        for name, path in SCRIPTS:
            out.write("\n" + "-" * 68 + "\n")
            out.write("### %s\n" % name)
            out.write("-" * 68 + "\n")
            out.write(_run_script(path, apply))

        out.write("\n" + "=" * 68 + "\n")
        if apply:
            out.write("APPLIED. Backups are in _backups/ NEXT TO THE DATABASE\n"
                      "(on this host that is the persistent volume, not /app,\n"
                      "so they survive the next deploy).\n\n"
                      "Now tell Claude it ran, so this route can be removed --\n"
                      "it is temporary and should not outlive the migration.\n")
        else:
            out.write("DRY RUN -- nothing was changed.\n"
                      "Add &apply=1 to the URL to write.\n")
        out.write("=" * 68 + "\n")

        return Response(out.getvalue(), mimetype="text/plain; charset=utf-8")
