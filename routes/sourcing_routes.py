"""routes/sourcing_routes.py -- the source repricer's screen.

Holds no decision logic of its own. Enrolment and sources come from
domain/source_repo.py, readings from domain/source_fetch.py, and every "what
would happen" answer from domain/source_run.py, which is the same code Phase D
will act on. That matters: the log this screen shows is not a preview built for
display, it is the actual decision, recorded.

Permissions are in auth/guard.py, not here. Reading the dry run is open to any
signed-in user because it is how you find out what the app is about to do;
everything that changes what it WILL do needs 'publish', which is the permission
for pushing changes to Amazon -- and that is precisely what enrolling a SKU
eventually causes.
"""
from flask import request, jsonify

from domain import source_fetch as _fetch
from domain import source_repo as _repo
from domain import source_run as _run
from domain import sourcing as _sourcing


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach the /sourcing/* routes to the existing Flask app."""

    def _where():
        """(account_id, marketplace) for the request, defaulting to the active one."""
        acc = _active_account() or {}
        wsid = (request.args.get("id") or (request.get_json(silent=True) or {}).get("id")
                or acc.get("id") or _state.get("active_account_id") or "")
        mkt = (request.args.get("marketplace")
               or (request.get_json(silent=True) or {}).get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        return wsid, mkt

    def _body():
        return request.get_json(force=True, silent=True) or {}

    # ---- what is enrolled, and what would happen to it -------------------
    @app.route("/sourcing/list")
    def sourcing_list():
        """Everything the screen draws: enrolment, sources, readings, decisions."""
        wsid, mkt = _where()
        run = _run.dry_run(CONFIG_PATH, wsid, mkt, record=False)
        rows = []
        for d in run["decisions"]:
            pairs = _repo.pairs_for(CONFIG_PATH, d["workspace_id"],
                                    d["marketplace"], d["sku"])
            rows.append({**d, "sources": [
                {**s, "check": c} for s, c in pairs]})
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "rows": rows, "counts": run["counts"],
                        "note": run["note"],
                        "rule": _sourcing.rule_with_defaults(
                            _repo.rule_for(CONFIG_PATH, wsid, mkt, "")),
                        "defaults": _sourcing.DEFAULT_RULE})

    @app.route("/sourcing/log")
    def sourcing_log():
        """The audit trail -- every decision, whether or not it was pushed."""
        wsid, mkt = _where()
        return jsonify({"ok": True, "actions": _repo.recent_actions(
            CONFIG_PATH, wsid, mkt, request.args.get("sku") or None,
            int(request.args.get("limit") or 200))})

    # ---- enrolment ------------------------------------------------------
    @app.route("/sourcing/enrol", methods=["POST"])
    def sourcing_enrol():
        b = _body()
        wsid, mkt = _where()
        sku = (b.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        if b.get("enrolled") is False:
            _repo.unenrol(CONFIG_PATH, wsid, mkt, sku)
        else:
            # 'live' is refused here on purpose. Phase D owns arming, and it will
            # require a min_price first -- the only guard that survives a
            # misread supplier cost.
            _repo.enrol(CONFIG_PATH, wsid, mkt, sku, mode="dry_run")
        return jsonify({"ok": True})

    # ---- sources --------------------------------------------------------
    @app.route("/sourcing/source/add", methods=["POST"])
    def sourcing_source_add():
        b = _body()
        wsid, mkt = _where()
        sku = (b.get("sku") or "").strip()
        url = (b.get("url") or "").strip()
        if not sku or not url:
            return jsonify({"ok": False, "error": "need a sku and a url"}), 400
        kind = (b.get("kind") or "").strip().lower()
        if not kind:
            kind = "ebay" if "ebay." in url.lower() else "html"
        if kind == "ebay":
            from api import ebay as _ebay
            if not _ebay.item_id_from_url(url):
                return jsonify({"ok": False, "error": (
                    "that does not look like an eBay item link -- it should "
                    "contain /itm/ and the item number")}), 400
        sid = _repo.add_source(CONFIG_PATH, wsid, mkt, sku, url, kind=kind,
                               label=(b.get("label") or "").strip(),
                               priority=int(b.get("priority") or 100),
                               shipping_override=b.get("shipping_override"))
        return jsonify({"ok": True, "id": sid})

    @app.route("/sourcing/source/update", methods=["POST"])
    def sourcing_source_update():
        b = _body()
        sid = b.get("source_id")
        if not sid:
            return jsonify({"ok": False, "error": "no source"}), 400
        if "enabled" in b:
            _repo.set_source_enabled(CONFIG_PATH, sid, bool(b["enabled"]))
        if "shipping_override" in b:
            v = b["shipping_override"]
            _repo.set_shipping_override(
                CONFIG_PATH, sid, None if v in ("", None) else float(v))
        return jsonify({"ok": True})

    @app.route("/sourcing/source/remove", methods=["POST"])
    def sourcing_source_remove():
        b = _body()
        if not b.get("source_id"):
            return jsonify({"ok": False, "error": "no source"}), 400
        _repo.remove_source(CONFIG_PATH, b["source_id"])
        return jsonify({"ok": True})

    # ---- rules ----------------------------------------------------------
    @app.route("/sourcing/rules", methods=["POST"])
    def sourcing_rules():
        b = _body()
        wsid, mkt = _where()
        vals = {k: v for k, v in (b.get("rule") or {}).items()
                if k in _sourcing.DEFAULT_RULE}
        _repo.save_rule(CONFIG_PATH, wsid, mkt, (b.get("sku") or "").strip(), vals)
        return jsonify({"ok": True, "rule": _sourcing.rule_with_defaults(
            _repo.rule_for(CONFIG_PATH, wsid, mkt, (b.get("sku") or "").strip()))})

    # ---- run it now -----------------------------------------------------
    @app.route("/sourcing/check", methods=["POST"])
    def sourcing_check_now():
        """Re-read every supplier now, then decide. The same two steps the timer
        runs, so pressing this cannot produce a different answer from waiting."""
        wsid, mkt = _where()
        got = _fetch.sweep(CONFIG_PATH, _cfg, workspace_id=wsid, marketplace=mkt,
                           pause=0.0)
        run = _run.dry_run(CONFIG_PATH, wsid, mkt)
        return jsonify({"ok": True, "fetch": got, "counts": run["counts"],
                        "skus": run["skus"]})
