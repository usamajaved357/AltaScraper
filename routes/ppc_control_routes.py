"""routes/ppc_control_routes.py -- campaign controls on the Campaign Analytics page.

    GET  /ppc/control/campaigns        Amazon's current campaign list (reads, keeps it)
    GET  /ppc/control/structure        one campaign's ad groups, keywords, targets, negatives
    POST /ppc/control/change           state and/or budget/bid of one campaign,
                                       ad group, keyword or product target
    POST /ppc/control/negative         add one negative keyword to an ad group

Owner, 30 Sep 2026: "i also want an option to turn on or off the campaigns and
change the budget, bids and rules ... i want it here". The writes need the
"publish" permission (auth/guard.py RULES: they change live advertising and
spend money), a confirmed flag, an account NAMED by the request (never the
server's open one, Rule 14), and the owner's own typed value (Rule 8,
domain/ppc_control). Every step lands in the Dr PPC ledger.
"""
from flask import jsonify, request

import domain.request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg, _state, _active_account):

    def _read_scope():
        from routes import scope as _scope_mod
        return _scope_mod.ads_account(request, state=_state, active_account=_active_account,
                                      cfg=_cfg, req_acct=_req_acct)

    def _write_scope(b):
        """The account and marketplace a WRITE names -> (aid, mkt, refusal).
        Named in the body, or refused: a write never lands on whichever account
        the server happens to have open."""
        aid = str(b.get("account") or b.get("id") or "").strip()
        if not aid:
            return "", "", (jsonify({"ok": False, "error": (
                "The request did not say which account -- nothing was changed.")}), 400)
        mkt = str(b.get("marketplace") or "").strip().upper()
        if not mkt or mkt == "__ALL__":
            cfg = _cfg() if callable(_cfg) else (_cfg or {})
            acc = next((a for a in (cfg.get("accounts") or []) if str(a.get("id")) == aid), None)
            if not acc:
                return "", "", (jsonify({"ok": False, "error": "no such account"}), 404)
            mkt = str(acc.get("default_marketplace") or "").upper()
        if not mkt:
            return "", "", (jsonify({"ok": False, "error": "no marketplace for this account"}), 400)
        return aid, mkt, None

    def _who():
        try:
            from domain import job_owner as _jo
            return _jo.label(CONFIG_PATH)
        except Exception:
            return ""

    @app.route("/ppc/control/campaigns")
    def ppc_control_campaigns():
        aid, mkt = _read_scope()
        if not (aid and mkt):
            return jsonify({"ok": False, "error": "Open an account first."}), 400
        from domain import ppc_control as _pc
        got = _pc.refresh_campaigns(CONFIG_PATH, aid, mkt)
        code = 200 if got.get("ok") else 502
        got.update({"account": aid, "marketplace": mkt})
        return jsonify(got), code

    @app.route("/ppc/control/structure")
    def ppc_control_structure():
        aid, mkt = _read_scope()
        cid = str(request.args.get("campaign_id") or "").strip()
        if not (aid and mkt and cid):
            return jsonify({"ok": False, "error": "need an account and a campaign"}), 400
        from domain import ppc_control as _pc
        got = _pc.structure(CONFIG_PATH, aid, mkt, cid)
        return jsonify(got), (200 if got.get("ok") else 502)

    @app.route("/ppc/control/change", methods=["POST"])
    def ppc_control_change():
        b = request.get_json(silent=True) or {}
        if b.get("confirmed") is not True:
            return jsonify({"ok": False, "error": "not confirmed -- nothing was changed"}), 400
        aid, mkt, bad = _write_scope(b)
        if bad:
            return bad
        from domain import ppc_control as _pc
        got = _pc.change(CONFIG_PATH, aid, mkt, str(b.get("kind") or ""),
                         b.get("id"), b.get("campaign_id"),
                         state=b.get("state"), amount=b.get("amount"), who=_who())
        got.update({"account": aid, "marketplace": mkt})
        return jsonify(got), (200 if got.get("ok") else 400)

    @app.route("/ppc/control/negative", methods=["POST"])
    def ppc_control_negative():
        b = request.get_json(silent=True) or {}
        if b.get("confirmed") is not True:
            return jsonify({"ok": False, "error": "not confirmed -- nothing was changed"}), 400
        aid, mkt, bad = _write_scope(b)
        if bad:
            return bad
        from domain import ppc_control as _pc
        got = _pc.add_negative(CONFIG_PATH, aid, mkt, b.get("campaign_id"), b.get("ad_group_id"),
                               b.get("text"), b.get("match_type"), who=_who())
        return jsonify(got), (200 if got.get("ok") else 400)
