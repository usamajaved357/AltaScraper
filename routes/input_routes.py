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
        return str(_state.get("active_account_id", "") or "") or "_no_account"

    @app.route("/input/status")
    def input_status():
        """How many products are queued, and how old the queue is.

        Age is the whole point: a queue with no date on it is indistinguishable
        from a fresh one, which is how you end up generating last month's list.

        Counted from the LISTINGS STORE now -- rows with status=QUEUED -- rather
        than from the old input_products table.
        """
        from data import queued_store as _qs
        wsid = _wsid()
        return jsonify({"ok": True, "workspace": wsid,
                        **_qs.queued_count(CONFIG_PATH, wsid)})

    @app.route("/input/rows")
    def input_rows():
        """The queued products, from the listings store.

        Returned under the names the queue UI already uses, so the screen did
        not have to change with the storage: a listing's Source URL is the
        eBay link the person pasted, and its Title is the name they gave it.
        """
        from data import queued_store as _qs
        out = []
        for r in _qs.queued_rows(CONFIG_PATH, _wsid()):
            out.append({
                "id": r.get("sku"),          # the SKU is the row's identity now
                "sku": r.get("sku"),
                "ebay_url": r.get("source_url") or "",
                "amazon_url": "",
                "competitor_asin": r.get("competitor_asin") or "",
                "item_name": r.get("title") or "",
                "source_cost": "",
                "selling_price": r.get("our_price") or "",
                "handling_time": r.get("handling_time") or r.get("handling_days") or "",
                "upc": r.get("upc") or "",
                "source": "queued",
            })
        return jsonify({"ok": True, "rows": out})

    # ---- REPLACED BY /input/upload (CSV/Excel) ------------------------------
    #
    # Kept, commented, rather than deleted, so it can be put back by removing
    # the comment markers and nothing else.
    #
    # The INPUT no longer comes from Google. Products reach the queue two ways
    # now -- the "Add a product" form (/input/add, below) and a CSV or Excel
    # file (/input/upload, routes/input_upload_routes.py) -- and neither needs
    # a spreadsheet to be configured, reachable, or still named what it was.
    #
    # The queue itself is unchanged: data/input_import.py stays, add_row and
    # import_rows are still what everything writes through, and the Google
    # client stays too because the OUTPUT store still uses it. Only this way IN
    # is gone.
    #
    # Two things went with it, for the same reason: the "Import from sheet"
    # button on the Generate screen, and the auto-import inside /run/generate
    # (routes/listing_routes.py) that read the sheet whenever the queue was
    # empty. That second one is the important one -- leaving it would have kept
    # the sheet dependency alive with no button in sight to explain it.
    #
    # @app.route("/input/import", methods=["POST"])
    # def input_import():
    #     """Read the workspace's input sheet ONCE and store it.
    #
    #     Additive and idempotent per row: pressing this twice is harmless, and a
    #     sheet that fails to load halfway through cannot empty your queue. Rows
    #     deleted from the sheet stay here until cleared explicitly -- silently
    #     dropping work because a spreadsheet changed is not a behaviour worth
    #     having.
    #     """
    #     from data import input_import as _ii
    #     wsid = _wsid()
    #     acc = None
    #     try:
    #         acc = _active_account()
    #     except Exception:
    #         acc = None
    #     # The one copy, shared with the generate path -- see
    #     # data/input_import.import_for_workspace.
    #     added, updated, total, err = _ii.import_for_workspace(
    #         CONFIG_PATH, wsid, acc, _cfg() or {}, _client)
    #     if err:
    #         return jsonify({"ok": False, "error": err}), 502
    #
    #     return jsonify({"ok": True, "workspace": wsid, "added": added,
    #                     "updated": updated, "read": total,
    #                     **_ii.summary(CONFIG_PATH, wsid)})

    # ---- adding products WITHOUT a spreadsheet ---------------------------
    # The queue is the same queue an import fills, so a workspace can be fed
    # from a sheet, by hand, or both, and the generator neither knows nor cares
    # which. This is what makes the spreadsheet optional rather than merely
    # imported: paste the links here and press Generate.

    def _product(b):
        """A posted row, reduced to the columns the queue actually has."""
        from data import input_import as _ii
        return {k: str((b or {}).get(k, "") or "").strip() for k in _EDITABLE}

    @app.route("/input/add", methods=["POST"])
    def input_add():
        """Queue one product typed into the app."""
        from data import input_import as _ii
        from data import input_row as _ir
        b = request.get_json(silent=True) or {}
        p = _product(b)
        # SOMETHING has to identify the product. A row with neither a source
        # link nor an ASIN nor a name cannot be generated from and would sit in
        # the queue looking like work.
        #
        # THE TEST AND ITS WORDING BOTH LIVE IN data/input_row.py NOW, because
        # the file upload has to apply the same rule to every row of a
        # spreadsheet. Written out twice, the two would have drifted the first
        # time either was relaxed -- and the failure mode is silent: a row the
        # form accepts but an upload drops, or the reverse, with no message
        # anywhere saying the two disagree (CLAUDE.md Rule 12).
        if not _ir.is_generatable(p):
            return jsonify({"ok": False, "error": _ir.WHY_NOT}), 400
        wsid = _wsid()
        # Into the LISTINGS STORE as QUEUED, exactly as an upload does -- same
        # function, so a typed product and an uploaded one are the same row.
        from data import queued_store as _qs
        extras = _qs.add_queued(CONFIG_PATH, wsid, p)
        return jsonify({"ok": True, "id": extras["sku"], "sku": extras["sku"],
                        "workspace": wsid,
                        **_qs.queued_count(CONFIG_PATH, wsid)})

    # The queue's columns, kept so an edit can still be filtered to real fields.
    _EDITABLE = ("ebay_url", "amazon_url", "competitor_asin", "item_name",
                 "source_cost", "selling_price", "handling_time", "upc")

    # Queue field -> the listings column it is stored in. amazon_url and
    # source_cost are absent on purpose: neither has a column on `listings`
    # (the ASIN is what an Amazon link is kept for, and the cost lives in the
    # COGS store), so neither can be edited here.
    _EDIT_TO_HEADER = {
        "ebay_url": "Source URL",
        "competitor_asin": "Competitor ASIN",
        "item_name": "Title",
        "selling_price": "Our Price (GBP)",
        "handling_time": "Handling Time",
        "upc": "UPC",
    }

    @app.route("/input/update", methods=["POST"])
    def input_update():
        """Change one queued product in place. `id` is its SKU."""
        from data.store import ListingStore
        from data import queued_store as _qs
        b = request.get_json(silent=True) or {}
        sku = str(b.get("id") or b.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no row id"}), 400
        wsid = _wsid()
        # ONLY QUEUED ROWS. This endpoint could once only reach the queue table
        # and so could never touch a real listing; now that queued rows sit
        # beside live ones, that has to be enforced rather than assumed.
        if not any(r.get("sku") == sku for r in _qs.queued_rows(CONFIG_PATH, wsid)):
            return jsonify({"ok": False, "error": (
                "That row is not queued in this workspace.")}), 404
        fields = {_EDIT_TO_HEADER[k]: v for k, v in (b or {}).items()
                  if k in _EDIT_TO_HEADER}
        if not fields:
            return jsonify({"ok": False, "error": "nothing to change"}), 400
        n = ListingStore(wsid, config_path=CONFIG_PATH).update_fields(sku, fields)
        return jsonify({"ok": True, "updated": n})

    @app.route("/input/delete", methods=["POST"])
    def input_delete():
        """Remove one queued product. Refuses anything not QUEUED."""
        from data import queued_store as _qs
        b = request.get_json(silent=True) or {}
        sku = str(b.get("id") or b.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no row id"}), 400
        wsid = _wsid()
        n = _qs.delete_queued(CONFIG_PATH, wsid, sku)
        return jsonify({"ok": bool(n), "removed": n,
                        **_qs.queued_count(CONFIG_PATH, wsid)})

    @app.route("/input/clear", methods=["POST"])
    def input_clear():
        """Empty this workspace's QUEUED rows.

        QUEUED ONLY. Generated, submitted and live listings live in the same
        table now, and this must never be the thing that empties a catalogue.
        """
        from data import queued_store as _qs
        wsid = _wsid()
        return jsonify({"ok": True, "workspace": wsid,
                        "removed": _qs.clear_queued(CONFIG_PATH, wsid)})
