"""routes/cogs_routes.py — COGS (cost-of-goods) endpoints, extracted from dashboard.py (Phase 3).

Same register(app, ...) injection pattern. _COGS_OVERRIDE (a shared mutable dict),
_save_cogs_overrides and _estimate_profit are used across the app, so they are
injected (the same objects), and the route bodies move VERBATIM (CLAUDE.md §10).

Routes:
  POST /cogs/set    -> set/override COGS for one SKU
  POST /cogs/upload -> bulk COGS upload {rows:[{sku,cost}]}
"""
from flask import request, jsonify


def register(app, *, _state, _COGS_OVERRIDE, _save_cogs_overrides, _estimate_profit):
    """Attach the /cogs/* routes to the existing Flask app."""

    @app.route("/cogs/set", methods=["POST"])
    def cogs_set():
        """Manually set/override COGS for a SKU in the active account."""
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        sku = (b.get("sku", "") or "").strip()
        cost = b.get("cost", None)
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        key = f"{aid}::{sku}"
        if cost in (None, "", "null"):
            _COGS_OVERRIDE.pop(key, None)   # clear override
        else:
            try:
                _COGS_OVERRIDE[key] = float(cost)
            except Exception:
                return jsonify({"ok": False, "error": "cost must be a number"}), 400
        _save_cogs_overrides()
        # return the recomputed profit for immediate UI update
        prof = None
        if key in _COGS_OVERRIDE:
            prof = _estimate_profit(b.get("price", ""), _COGS_OVERRIDE[key])
        return jsonify({"ok": True, "profit": prof})

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
