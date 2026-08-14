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

    def _resolve_tab(sid, acc):
        """The account's OWN tab name in that workbook -> (name, error).

        Accounts share a workbook and each owns one tab, identified by gid. A
        name is only trusted if the workbook actually has it; a gid that is not
        in the workbook is refused rather than quietly falling back to the first
        tab, because the first tab belongs to somebody else.
        """
        gid = str(acc.get("output_tab_gid") or "").strip()
        name = str(acc.get("output_tab") or "").strip()
        try:
            book = _client().open_by_key(sid)
            sheets = book.worksheets()
        except Exception as e:
            return None, "Could not open that spreadsheet: %s" % str(e)[:180]
        by_gid = {str(w.id): w.title for w in sheets}
        by_name = {w.title: w.title for w in sheets}
        if gid and gid in by_gid:
            return by_gid[gid], ""
        if name and name in by_name:
            return name, ""
        if gid or name:
            return None, ("This account's own tab (%s) is not in that "
                          "spreadsheet, so nothing was read. Set the output "
                          "sheet and tab on the account first -- importing the "
                          "workbook's first tab would copy in another account's "
                          "listings." % (gid or name))
        # Only one listing-shaped tab and no gid recorded: unambiguous.
        if len(sheets) == 1:
            return sheets[0].title, ""
        return None, ("This account has no output tab recorded, and that "
                      "spreadsheet has %d tabs. Set the account's output tab "
                      "first so the right one is read." % len(sheets))

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

        sid = str(acc.get("output_spreadsheet_id") or "").strip()
        if not sid:
            return jsonify({"ok": False,
                            "error": ("%s has no output spreadsheet configured, so "
                                      "there is nothing to import from. If its "
                                      "listings are already in the app, there is "
                                      "nothing to do." % (acc.get("label") or aid))}), 200

        # WHICH TAB. This is the whole ball game on a SHARED workbook: five of
        # these accounts live in ONE spreadsheet, each owning a different tab,
        # and the tab is identified by its gid rather than its name.
        #
        # Taking the first tab -- which is what import_from_sheet does when
        # given no name -- read a 3-row scratch tab for five of six accounts on
        # a dry run here. It would have "succeeded", reported three rows, and
        # left every real listing behind.
        tab, tab_err = _resolve_tab(sid, acc)
        if tab_err:
            return jsonify({"ok": False, "error": tab_err}), 200
        try:
            from data.store import ListingStore
            store = ListingStore(aid, config_path=CONFIG_PATH)
            before = store.row_count()
            res = store.import_from_sheet(_client(), sid, tab=tab, dry_run=dry)
            after = store.row_count()
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read that sheet: %s" % str(e)[:200]}), 200
        res["tab"] = tab

        res.update({"ok": True, "account": aid,
                    "label": acc.get("label") or aid,
                    "before": before, "after": after, "dry_run": dry,
                    # Said every time, because the whole safety of this rests on
                    # it and it should never be something the reader assumes.
                    "note": "The spreadsheet was only read. Nothing was written "
                            "to it and nothing in it was changed."})
        return jsonify(res)
