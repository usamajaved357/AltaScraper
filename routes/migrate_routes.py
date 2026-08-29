"""routes/migrate_routes.py -- move a workspace's listings out of Google Sheets.

    GET  /migrate/status   what each account has in each store (reads only)
    POST /migrate/import   copy one account's sheet into the database

WHY THIS EXISTS AT ALL, given the app was supposed to be off Sheets already.

Switching the app to the database was done in two halves and only one of them
finished. The CODE moved: the generator writes to the database, listings are
read from it, Finance and the repricer are built on it. The DATA did not. Every
account still has its output spreadsheet configured, and on a machine where the
one-time import was never run, that spreadsheet is where the history actually
is.

data/import_sheets.py has always been able to do the copy -- but only as a
command line run against a local database. It was run on the developer's
machine, which is why everything looked migrated there, and never on the
server, where the database was created fresh by a deploy. So the server kept
depending on Sheets, and every screen that stopped reading Sheets appeared to
lose data.

That is the honest reason the same problem keeps coming back, and it does not
stop until the rows are actually moved on the machine that serves them. Hence a
route: the import has to run where the database is, and that is not a laptop.

SAFETY. The sheet is only ever READ -- import_from_sheet never writes back, not
even to mark a row as imported, so the original stays as the fallback if the
import is wrong. Rows are upserted by SKU, so running it twice is not running it
twice: the second pass overwrites with the same values rather than duplicating.
A dry run reports exactly what a real one would do, and is the default.
"""
from flask import request, jsonify


def register(app, *, CONFIG_PATH, _cfg, _client, _state):
    """Attach /migrate/* to the app."""

    def _accounts():
        try:
            from domain import accounts as _acc
            return _acc.load_accounts(_cfg(), CONFIG_PATH) or []
        except Exception:
            return (_cfg() or {}).get("accounts") or []

    def _counts(aid):
        """(rows in the database, error) for one workspace."""
        try:
            from data.store import ListingStore
            return ListingStore(aid, config_path=CONFIG_PATH).row_count(), ""
        except Exception as e:
            return 0, str(e)[:160]

    @app.route("/migrate/status")
    def migrate_status():
        """What is where. Reads only -- nothing is copied or changed."""
        try:
            from data import choice as _choice
            backend = _choice.resolve(_cfg(), CONFIG_PATH)
        except Exception:
            backend = "sheets"
        out = []
        for a in _accounts():
            aid = str(a.get("id") or "").strip()
            if not aid:
                continue
            n_db, err = _counts(aid)
            out.append({
                "id": aid,
                "label": a.get("label") or aid,
                "in_database": n_db,
                "sheet_id": str(a.get("output_spreadsheet_id") or "").strip(),
                "tab": str(a.get("output_tab") or "").strip(),
                # The question worth answering on sight: is this account still
                # relying on the spreadsheet?
                "still_on_sheets": bool(str(a.get("output_spreadsheet_id") or "").strip())
                                   and n_db == 0,
                "error": err,
            })
        return jsonify({"ok": True, "backend": backend, "accounts": out})

    @app.route("/migrate/import", methods=["POST"])
    def migrate_import():
        """Copy ONE account's output sheet into the database.

        Defaults to a dry run. The caller has to ask for the real thing, because
        a button that silently writes several hundred rows on first click is a
        button nobody can safely explore.
        """
        b = request.get_json(force=True) or {}
        aid = str(b.get("id") or "").strip()
        dry = bool(b.get("dry_run", True))
        if not aid:
            return jsonify({"ok": False, "error": "no account given"}), 400

        acc = None
        for a in _accounts():
            if str(a.get("id") or "").strip() == aid:
                acc = a
                break
        if not acc:
            return jsonify({"ok": False, "error": "unknown account: %s" % aid}), 404

        # THE COPY ITSELF LIVES IN domain/sheet_migration.py, because the
        # listings read now does it too, on its own, when it finds rows that are
        # still only in the spreadsheet. Two copies of the tab rule would be two
        # ways to read the wrong account's listings.
        from domain import sheet_migration as _mig
        res = _mig.import_account(acc, client=_client(),
                                  config_path=CONFIG_PATH, dry_run=dry)
        return jsonify(res), 200
