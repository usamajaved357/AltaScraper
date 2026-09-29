"""routes/submit_routes.py — submit pre-flight endpoints, extracted from dashboard.py (Phase 3).

Same register(app, ...) injection pattern as drive_routes: shared helpers are
injected (they remain owned by dashboard.py during the transition) and the route
bodies are moved VERBATIM — no logic changes (CLAUDE.md §10).

Routes:
  GET /submit/precheck -> warn about APPROVED rows whose main image is a LOCAL path
  GET /submit/target   -> report which Amazon account/marketplace a submit will hit
"""
from flask import jsonify, request


def register(app, *, _records, _active_account, _state, _cfg, _ws=None, CONFIG_PATH=""):
    """Attach the /submit/* routes to the existing Flask app."""

    @app.route("/submit/precheck")
    def submit_precheck():
        """Scan APPROVED/API_READY rows for main images that are LOCAL paths
        (e.g. /media/... or 127.0.0.1) which Amazon cannot fetch. Returns the list
        of affected SKUs so the UI can warn BEFORE submitting."""
        # THIS NEVER FOUND ANYTHING. `_records()` was called without the sheet
        # it reads (a TypeError, swallowed into "no rows"), and each row was read
        # for `attributes`/`main_image`, keys a row never has -- they are TEXT in
        # "Attributes JSON". So the warning before a submit, "this main image is
        # a file on your PC and Amazon cannot fetch it", never appeared once
        # (found 28 Sep 2026). The rows are the requesting tab's account
        # (_ws follows it); the image is read by the one shared reader.
        #
        # WHAT IS A PROBLEM is the submit's own rule (image_urls.main_image_problem,
        # shared with the generator): an app image with a public address set is
        # fine; a borrowed photo or an unreachable one goes up with no picture;
        # a link to this machine fails. `?skus=a,b` limits it to what is being
        # submitted, so the warning never names listings you did not pick.
        from domain import row_image as _ri
        from domain import image_urls as _iu
        from listing.preview_scope import SUBMIT_ELIGIBLE as _SUBMITTABLE
        only = {s.strip() for s in (request.args.get("skus") or "").split(",") if s.strip()}
        try:
            records = _records(_ws()) if _ws else []
        except Exception:
            records = []
        bad = []
        for r in records or []:
            # The statuses a submit sends: the one list (listing/preview_scope).
            status = str(r.get("Status") or r.get("status") or "").strip().upper()
            if status not in _SUBMITTABLE:
                continue
            sku = str(r.get("SKU") or r.get("sku") or "")
            if only and sku not in only:
                continue
            img = str(_ri.main_image(r.get("Attributes JSON"), strict=True) or "")
            why = _iu.main_image_problem(CONFIG_PATH, img)
            if why:
                bad.append({"sku": sku or "?", "image": img[:120], "why": why})
        return jsonify({"ok": True, "local_image_rows": bad, "count": len(bad)})

    @app.route("/submit/target")
    def submit_target():
        """Report WHICH Amazon account a submit will hit. With the accounts model,
        this is the ACTIVE ACCOUNT directly -- not inferred from marketplace."""
        acc = _active_account()
        # The tab's marketplace and view, never another tab's (routes/scope).
        from routes import scope as _scope_mod
        from domain import request_account as _rqa
        mkt = (_scope_mod.marketplace(state=_state, account=acc or {},
                                      asked=request.args.get("marketplace")) or "").upper()
        _other_tab = bool(_rqa.named_now()) and _rqa.named_now() != str(
            _state.get("active_account_id", "") or "")
        if acc:
            rt = str(acc.get("refresh_token", ""))
            ready = bool(rt) and not rt.startswith(("PUT_", "ROTATE"))
            return jsonify({"ok": True, "marketplace": mkt or "(account default)",
                            "account_label": acc.get("label", acc.get("id", "account")),
                            "seller_id": acc.get("seller_id", ""),
                            "account_id": acc.get("id", ""),
                            "block": "account" if ready else "none",
                            "view": (acc.get("label", "") if _other_tab
                                     else (_state.get("active_view") or acc.get("label", ""))),
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
                            "view": _state.get("active_view") or "Default sheet", "ready": ready})
        return jsonify({"ok": True, "marketplace": mkt,
                        "account_label": cfg.get("uk_account_label") or "UK account",
                        "seller_id": cfg.get("seller_id", ""), "block": "main",
                        "view": _state.get("active_view") or "Default sheet", "ready": True})
