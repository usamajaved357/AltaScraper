"""routes/live_tracker_routes.py -- the Live Tracker.

    GET /ppc/live            everything the page draws, in one call
    GET /ppc/live/asin       one product's daily line, for an expanded card

Its own file because it is its own feature (CLAUDE.md Rule 7).

READ-ONLY. Nothing here touches a bid, a budget or a campaign state (Rule 8).
"""
from flask import jsonify, request

import domain.request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg, _state, _active_account):

    def _scope():
        # The one copy: routes/scope.ads_account (shared with ppc_analytics_routes).
        from routes import scope as _scope_mod
        return _scope_mod.ads_account(request, state=_state, active_account=_active_account,
                                      cfg=_cfg, req_acct=_req_acct)

    def _need(aid, mkt):
        if aid and mkt:
            return None
        return jsonify({"ok": False, "error": (
            "Open an account and pick a marketplace first — advertising belongs "
            "to one advertiser in one marketplace.")}), 400

    def _days():
        try:
            return max(1, min(90, int(request.args.get("days") or 7)))
        except (TypeError, ValueError):
            return 7

    @app.route("/ppc/live")
    def ppc_live():
        from domain import live_tracker as _lt

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        days = _days()
        cum = str(request.args.get("cumulative") or "").lower() in (
            "1", "true", "yes", "on")

        # Whether advertising is connected at all, from the single place that
        # answers it -- so this page cannot disagree with PPC Analytics about
        # the same account (Rule 12).
        acc = {}
        for a in ((_cfg() or {}).get("accounts") or []):
            if str(a.get("id") or "") == aid:
                acc = a
                break
        try:
            from api import amazon_ads as _ads
            conn_state = _ads.connection(_cfg, acc)
        except Exception as e:
            conn_state = {"ok": None, "why": str(e)[:120], "missing": []}

        return jsonify({
            "ok": True, "account": aid, "marketplace": mkt,
            "account_label": acc.get("label") or aid,
            "connection": conn_state,
            "kpis": _lt.kpis(CONFIG_PATH, aid, mkt, days),
            "series": _lt.series(CONFIG_PATH, aid, mkt, days, cum),
            "placements": _lt.placements(CONFIG_PATH, aid, mkt, days),
            "products": _lt.products(CONFIG_PATH, aid, mkt, days),
            "ranges": [{"key": k, "label": lab, "days": d}
                       for k, lab, d in _lt.RANGES],
            "days": days, "cumulative": cum,
            # THE PAGE'S CENTRAL LIMITATION, sent so the screen states it rather
            # than quietly offering day buttons where a mockup promised hours.
            #
            # ASKED, NOT ASSERTED. This was a hardcoded False. It now comes from
            # domain/live_tracker.hourly_state, which asks domain/ams -- the one
            # module that decides whether hourly data exists anywhere in the app
            # (Rule 12). The spec defers this whole page pending AWS: "Requires
            # AMS. Currently deferred because Talal doesn't have an AWS
            # account." If a queue is ever added and rows land, this flips on
            # its own, here and on PPC Analytics, without either screen changing.
            "hourly": _lt.hourly_state(CONFIG_PATH),
        })

    @app.route("/ppc/live/asin")
    def ppc_live_asin():
        from domain import live_tracker as _lt

        aid, mkt = _scope()
        bad = _need(aid, mkt)
        if bad:
            return bad
        asin = (request.args.get("asin") or "").strip()
        if not asin:
            return jsonify({"ok": False, "error": "no asin given"}), 400
        got = _lt.daily_for_asin(CONFIG_PATH, aid, mkt, asin, _days())
        got["ok"] = True
        return jsonify(got)
