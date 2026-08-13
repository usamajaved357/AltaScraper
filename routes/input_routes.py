"""routes/input_routes.py -- bring the input sheet in, on demand.

The generator's INPUT was the last thing read live from Google Sheets. Reading it
live meant no listing could be started unless Google was reachable, the service
account still had access, and the sheet kept its name and tab. Everything else in
the app had already stopped depending on Sheets.

These three endpoints make it an import instead. Your sheet stays exactly as you
use it; it just stops being a dependency.
"""
from flask import request, jsonify


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state, _client=None):
    """Attach /input/* to the app."""

    def _wsid():
        return str(_state.get("active_account_id", "") or "") or "dropshipping"

    @app.route("/input/status")
    def input_status():
        """How many products are queued, and how old the queue is.

        Age is the whole point: a queue with no date on it is indistinguishable
        from a fresh one, which is how you end up generating last month's list.
        """
        from data import input_import as _ii
        wsid = _wsid()
        s = _ii.summary(CONFIG_PATH, wsid)
        return jsonify({"ok": True, "workspace": wsid, **s})

    @app.route("/input/rows")
    def input_rows():
        from data import input_import as _ii
        return jsonify({"ok": True, "rows": _ii.rows(CONFIG_PATH, _wsid())})

    @app.route("/input/import", methods=["POST"])
    def input_import():
        """Read the workspace's input sheet ONCE and store it.

        Additive and idempotent per row: pressing this twice is harmless, and a
        sheet that fails to load halfway through cannot empty your queue. Rows
        deleted from the sheet stay here until cleared explicitly -- silently
        dropping work because a spreadsheet changed is not a behaviour worth
        having.
        """
        from data import input_import as _ii
        wsid = _wsid()
        acc = None
        try:
            acc = _active_account()
        except Exception:
            acc = None
        cfg = _cfg() or {}
        # THREE places an input sheet can be configured, in priority order:
        #   the account's own            -- a real workspace
        #   dropshipping_*               -- the built-in Dropshipping workspace,
        #                                   which has no account object and keeps
        #                                   its sheets under its own config keys
        #   the app-wide default         -- what everything used before accounts
        # Missing the middle one would have made Import silently read the WRONG
        # sheet for Dropshipping, or refuse when a sheet was plainly configured.
        if acc:
            sid = str(acc.get("input_spreadsheet_id") or "").strip()
            gid = str(acc.get("input_tab_gid") or "").strip()
        else:
            sid = str(cfg.get("dropshipping_input_spreadsheet_id")
                      or cfg.get("input_spreadsheet_id") or "").strip()
            gid = str(cfg.get("dropshipping_input_tab_gid") or "").strip()
        if not sid:
            return jsonify({"ok": False, "error":
                            "This workspace has no input sheet configured. Open "
                            "Account & sheets and paste the input sheet link."}), 400

        try:
            if _client is None:
                raise RuntimeError("no Google client is configured")
            gc = _client()
            sh = gc.open_by_key(sid)
            ws = None
            if gid.isdigit():
                try:
                    ws = sh.get_worksheet_by_id(int(gid))
                except Exception:
                    ws = None
            if ws is None:
                ws = sh.get_worksheet(0)
            added, updated, total = _ii.import_from_worksheet(CONFIG_PATH, wsid, ws)
        except Exception as e:
            # Say which sheet failed. "Import failed" on an account with several
            # sheets configured sends you looking through all of them.
            return jsonify({"ok": False,
                            "error": "Could not read the input sheet (%s): %s"
                                     % (sid[:12] + "…", str(e)[:200])}), 502

        return jsonify({"ok": True, "workspace": wsid, "added": added,
                        "updated": updated, "read": total,
                        **_ii.summary(CONFIG_PATH, wsid)})

    @app.route("/input/clear", methods=["POST"])
    def input_clear():
        """Empty the queue for this workspace. Deliberately explicit -- an import
        never deletes, so this is the only way work leaves the queue."""
        from data import input_import as _ii
        wsid = _wsid()
        return jsonify({"ok": True, "workspace": wsid,
                        "removed": _ii.clear(CONFIG_PATH, wsid)})
