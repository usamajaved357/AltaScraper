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
        # The one copy, shared with the generate path -- see
        # data/input_import.import_for_workspace.
        added, updated, total, err = _ii.import_for_workspace(
            CONFIG_PATH, wsid, acc, _cfg() or {}, _client)
        if err:
            return jsonify({"ok": False, "error": err}), 502

        return jsonify({"ok": True, "workspace": wsid, "added": added,
                        "updated": updated, "read": total,
                        **_ii.summary(CONFIG_PATH, wsid)})

    # ---- adding products WITHOUT a spreadsheet ---------------------------
    # The queue is the same queue an import fills, so a workspace can be fed
    # from a sheet, by hand, or both, and the generator neither knows nor cares
    # which. This is what makes the spreadsheet optional rather than merely
    # imported: paste the links here and press Generate.

    def _product(b):
        """A posted row, reduced to the columns the queue actually has."""
        from data import input_import as _ii
        return {k: str((b or {}).get(k, "") or "").strip() for k in _ii.COLUMNS}

    @app.route("/input/add", methods=["POST"])
    def input_add():
        """Queue one product typed into the app."""
        from data import input_import as _ii
        b = request.get_json(silent=True) or {}
        p = _product(b)
        # SOMETHING has to identify the product. A row with neither a source
        # link nor an ASIN nor a name cannot be generated from and would sit in
        # the queue looking like work.
        if not (p["ebay_url"] or p["amazon_url"] or p["competitor_asin"]
                or p["item_name"]):
            return jsonify({"ok": False, "error": (
                "Give at least a source link, an Amazon link or ASIN, or a "
                "product name — otherwise there is nothing to generate from.")}), 400
        wsid = _wsid()
        rid = _ii.add_row(CONFIG_PATH, wsid, p)
        return jsonify({"ok": True, "id": rid, "workspace": wsid,
                        **_ii.summary(CONFIG_PATH, wsid)})

    @app.route("/input/update", methods=["POST"])
    def input_update():
        """Change one queued product in place."""
        from data import input_import as _ii
        b = request.get_json(silent=True) or {}
        rid = b.get("id")
        if not rid:
            return jsonify({"ok": False, "error": "no row id"}), 400
        fields = {k: v for k, v in (b or {}).items() if k in _ii.COLUMNS}
        n = _ii.update_row(CONFIG_PATH, _wsid(), rid, fields)
        if not n:
            return jsonify({"ok": False, "error": (
                "That row is not in this workspace's queue.")}), 404
        return jsonify({"ok": True, "updated": n})

    @app.route("/input/delete", methods=["POST"])
    def input_delete():
        """Remove one queued product."""
        from data import input_import as _ii
        b = request.get_json(silent=True) or {}
        rid = b.get("id")
        if not rid:
            return jsonify({"ok": False, "error": "no row id"}), 400
        n = _ii.delete_row(CONFIG_PATH, _wsid(), rid)
        return jsonify({"ok": bool(n), "removed": n,
                        **_ii.summary(CONFIG_PATH, _wsid())})

    @app.route("/input/clear", methods=["POST"])
    def input_clear():
        """Empty the queue for this workspace. Deliberately explicit -- an import
        never deletes, so this is the only way work leaves the queue."""
        from data import input_import as _ii
        wsid = _wsid()
        return jsonify({"ok": True, "workspace": wsid,
                        "removed": _ii.clear(CONFIG_PATH, wsid)})
