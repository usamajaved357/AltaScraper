"""routes/submit_routes.py — submit pre-flight endpoints, extracted from dashboard.py (Phase 3).

Same register(app, ...) injection pattern as drive_routes: shared helpers are
injected (they remain owned by dashboard.py during the transition) and the route
bodies are moved VERBATIM — no logic changes (CLAUDE.md §10).

Routes:
  GET /submit/precheck -> warn about APPROVED rows whose main image is a LOCAL path
  GET /submit/target   -> report which Amazon account/marketplace a submit will hit
"""
from flask import jsonify


def register(app, *, _records, _active_account, _state, _cfg):
    """Attach the /submit/* routes to the existing Flask app."""

    @app.route("/submit/precheck")
    def submit_precheck():
        """Scan APPROVED/API_READY rows for main images that are LOCAL paths
        (e.g. /media/... or 127.0.0.1) which Amazon cannot fetch. Returns the list
        of affected SKUs so the UI can warn BEFORE submitting."""
        try:
            records = _records()
        except Exception:
            records = []
        bad = []
        for r in records or []:
            status = (r.get("Status") or r.get("status") or "").upper()
            if status not in ("APPROVED", "API_READY"):
                continue
            attrs = r.get("attributes") or {}
            img = (r.get("main_image") or attrs.get("main_product_image_locator")
                   or attrs.get("media_location") or "")
            if isinstance(img, list) and img:
                img = (img[0] or {}).get("media_location", "") if isinstance(img[0], dict) else str(img[0])
            img = str(img or "")
            is_local = (img.startswith("/media/") or "127.0.0.1" in img
                        or "localhost" in img or img.startswith("/mnt/")
                        or (img and not img.lower().startswith("http")))
            if img and is_local:
                bad.append({"sku": r.get("SKU") or r.get("sku") or "?", "image": img[:120]})
        return jsonify({"ok": True, "local_image_rows": bad, "count": len(bad)})

    @app.route("/submit/target")
    def submit_target():
        """Report WHICH Amazon account a submit will hit. With the accounts model,
        this is the ACTIVE ACCOUNT directly -- not inferred from marketplace."""
        acc = _active_account()
        mkt = (_state.get("active_marketplace") or "").upper()
        if acc:
            rt = str(acc.get("refresh_token", ""))
            ready = bool(rt) and not rt.startswith(("PUT_", "ROTATE"))
            return jsonify({"ok": True, "marketplace": mkt or "(account default)",
                            "account_label": acc.get("label", acc.get("id", "account")),
                            "seller_id": acc.get("seller_id", ""),
                            "account_id": acc.get("id", ""),
                            "block": "account" if ready else "none",
                            "view": _state.get("active_view") or acc.get("label", ""),
                            "ready": ready})
        # legacy fallback
        cfg = _cfg()
        mkt = mkt or "UK"
        if mkt == "US":
            us = cfg.get("us_spapi") or {}
            ready = bool(us.get("refresh_token"))
            return jsonify({"ok": True, "marketplace": mkt,
                            "account_label": cfg.get("us_account_label") or "US account",
                            "seller_id": us.get("seller_id", ""), "block": "us_spapi" if ready else "none",
                            "view": _state.get("active_view") or "Dropshipping", "ready": ready})
        return jsonify({"ok": True, "marketplace": mkt,
                        "account_label": cfg.get("uk_account_label") or "UK account",
                        "seller_id": cfg.get("seller_id", ""), "block": "main",
                        "view": _state.get("active_view") or "Dropshipping", "ready": True})
