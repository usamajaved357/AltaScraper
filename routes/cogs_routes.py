"""routes/cogs_routes.py — COGS (cost-of-goods) endpoints, extracted from dashboard.py (Phase 3).

Same register(app, ...) injection pattern. _COGS_OVERRIDE (a shared mutable dict),
_save_cogs_overrides and _estimate_profit are used across the app, so they are
injected (the same objects), and the route bodies move VERBATIM (CLAUDE.md §10).

Routes:
  GET  /cogs/template.csv -> the cost sheet, listing this account's SKUs
  POST /cogs/set          -> set/override COGS for one SKU
  POST /cogs/upload       -> bulk COGS upload {rows:[{sku,cost}]}
"""
from flask import request, jsonify, Response


def register(app, *, _state, _COGS_OVERRIDE, _save_cogs_overrides, _estimate_profit,
             CONFIG_PATH=None, _active_account=None):
    """Attach the /cogs/* routes to the existing Flask app."""

    @app.route("/cogs/template.csv")
    def cogs_template():
        """The cost sheet to fill in, listing every SKU on the account.

        There was an upload and no template, so the columns had to be guessed and
        every SKU typed by hand -- and a hand-typed SKU is one that silently
        matches nothing. The upload's own error for that is "No matchable rows",
        which is the app telling you it cannot read what it asked you to write.

        The `cost` column arrives EMPTY on purpose, even where a cost is known.
        See domain/cogs.template_rows: a cost is a manual override, and
        pre-filling it would turn every SKU-derived cost into a typed-in one on
        a single upload of a file nobody edited. What the app uses now is in
        `cost now`, to read.
        """
        from domain import cogs as _cogs
        from domain import catalogue as _cat
        from domain import sheets as _sheets
        acc = (_active_account() or {}) if callable(_active_account) else {}
        aid = str(acc.get("id") or _state.get("active_account_id", "") or "")
        mkt = str(acc.get("default_marketplace")
                  or _state.get("active_marketplace") or "").upper()
        rows = _cogs.template_rows(CONFIG_PATH, aid, mkt,
                                   overrides=_COGS_OVERRIDE,
                                   catalogue=_cat.index(CONFIG_PATH, aid, mkt))
        body = _sheets.to_csv(_cogs.TEMPLATE_HEADERS, rows)
        name = "costs-%s-%s.csv" % (aid or "account", mkt or "")
        return Response(body, # Flask appends the charset itself; naming it here too produced
                        # "text/csv; charset=utf-8; charset=utf-8", which a strict parser
                        # is entitled to reject.
                        mimetype="text/csv",
                        headers={"Content-Disposition":
                                 'attachment; filename="%s"' % name})

    @app.route("/cogs/upload_sheet", methods=["POST"])
    def cogs_upload_sheet():
        """A cost sheet, parsed HERE rather than in the browser.

        The browser version split each line on commas, which is not what a CSV
        is: a product name like "Grill, Large" is quoted and contains one, so
        every column after it shifted and the cost was read from the wrong
        place. The sheet this app hands out is full of such names, so that was
        about to become the normal case. It also could not read a spreadsheet at
        all; this can.
        """
        from domain import cogs as _cogs
        from domain import source_bulk as _sb
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "no file"}), 400
        acc = (_active_account() or {}) if callable(_active_account) else {}
        aid = str(request.form.get("id") or acc.get("id")
                  or _state.get("active_account_id", "") or "")
        mkt = str(acc.get("default_marketplace")
                  or _state.get("active_marketplace") or "").upper()
        headers, rows, err = _sb.read_table(f.read(), f.filename or "")
        if err:
            return jsonify({"ok": False, "error": err}), 400
        rep = _cogs.apply_sheet(CONFIG_PATH, aid, mkt, headers, rows)
        if not rep.get("ok"):
            return jsonify(rep), 400
        # Written only after the whole file has been read without complaint, so
        # a sheet that fails halfway does not leave half the catalogue changed.
        # Through the store, same as /cogs/set -- one way in, so a cost set by
        # sheet and a cost typed on a row cannot end up in different dicts.
        from domain import cogs_store as _cs
        for sku, cost in (rep.pop("updates", None) or {}).items():
            _cs.set_cost(CONFIG_PATH, aid, sku, cost)
        rep["note"] = ("%d cost%s set. %d row%s had no cost filled in and were "
                       "left alone." % (rep["set"], "" if rep["set"] == 1 else "s",
                                        rep["skipped"],
                                        "" if rep["skipped"] == 1 else "s"))
        return jsonify(rep)

    @app.route("/cogs/set", methods=["POST"])
    def cogs_set():
        """Manually set/override COGS for a SKU in the active account."""
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        sku = (b.get("sku", "") or "").strip()
        cost = b.get("cost", None)
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        # THROUGH THE STORE, which owns the dict and the file together. Writing
        # the dict here and saving separately is how the two came apart before:
        # see domain/cogs_store.py for the module-identity bug that made a typed
        # cost invisible to the Sales and Orders screens.
        from domain import cogs_store as _cs
        stored, ok = _cs.set_cost(CONFIG_PATH, aid, sku, cost)
        if not ok and cost not in (None, "", "null"):
            return jsonify({"ok": False, "error": (
                "cost must be a number, and not a negative one")}), 400
        # return the recomputed profit for immediate UI update
        prof = (_estimate_profit(b.get("price", ""), stored)
                if stored is not None else None)
        return jsonify({"ok": True, "profit": prof, "cost": stored,
                        "cogs_source": ("manual" if stored is not None else "")})

    @app.route("/cogs/upload", methods=["POST"])
    def cogs_upload():
        """Bulk COGS upload: accepts {rows:[{sku,cost}]} (parsed client-side from CSV)."""
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        rows = b.get("rows", []) or []
        n = 0
        for r in rows:
            sku = (r.get("sku", "") or "").strip()
            cost = r.get("cost", None)
            if not sku or cost in (None, ""):
                continue
            try:
                _COGS_OVERRIDE[f"{aid}::{sku}"] = float(cost)
                n += 1
            except Exception:
                continue
        _save_cogs_overrides()
        return jsonify({"ok": True, "count": n})
