"""routes/order_purchase_routes.py -- "I bought this order from the supplier".

    POST /orders/purchase          record that one order was bought
    POST /orders/purchase/remove   forget one such record

A RECORD, NOT A PURCHASE. Nothing here contacts a supplier or spends money; the
person buys on the supplier's own site and says so here. The rules live in
domain/order_purchases.py.

THE ACCOUNT MUST BE NAMED. Unlike the older tracking routes, these never fall
back to the server's open account -- that belongs to whichever browser tab
switched last, and a record filed there would sit on another company's order
(CLAUDE.md Rule 14). The guard (auth/guard.py) has already checked the signed-in
person may use the account named.
"""
from flask import jsonify, request

from domain import request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg):
    """Attach /orders/purchase* to the app."""

    def _account(aid):
        cfg = (_cfg() if callable(_cfg) else _cfg) or {}
        return next((a for a in (cfg.get("accounts") or [])
                     if str(a.get("id") or "") == aid), None)

    def _marketplace(acc, asked):
        """The marketplace the page named, else the account's own default --
        where its orders come from, never a guess -- and only one of the
        account's own marketplaces."""
        own = [str(m).strip().upper() for m in (acc.get("marketplaces") or [])
               if str(m).strip()]
        dflt = str(acc.get("default_marketplace") or "").strip().upper()
        if dflt and dflt not in own:
            own.append(dflt)
        asked = str(asked or "").strip().upper()
        if asked:
            return asked if asked in own else ""
        return dflt or (own[0] if own else "")

    def _scope(b, what):
        """(account_id, marketplace, order_id, None) or (.., refusal)."""
        aid = _req_acct.named_now()
        oid = str(b.get("order_id") or "").strip()
        if not aid:
            return "", "", "", (jsonify({"ok": False, "error": (
                "Which account? The request did not name one, so nothing was "
                "%s. Reload the Orders page and try again." % what)}), 400)
        acc = _account(aid)
        if acc is None:
            return "", "", "", (jsonify({"ok": False, "error": (
                "There is no account called %r in this app." % aid)}), 404)
        mkt = _marketplace(acc, b.get("marketplace"))
        if not mkt:
            return "", "", "", (jsonify({"ok": False, "error": (
                "That marketplace is not one of %s's, so nothing was %s."
                % (acc.get("label") or aid, what))}), 400)
        if not oid:
            return "", "", "", (jsonify({"ok": False, "error": (
                "No order number came with the request.")}), 400)
        return aid, mkt, oid, None

    @app.route("/orders/purchase", methods=["POST"])
    def orders_purchase():
        from domain import job_owner as _jo
        from domain import order_purchases as _op
        b = request.get_json(silent=True) or {}
        aid, mkt, oid, bad = _scope(b, "recorded")
        if bad:
            return bad
        pid = _op.record(CONFIG_PATH, aid, mkt, oid,
                         supplier=b.get("supplier"),
                         supplier_url=b.get("supplier_url"),
                         supplier_ref=b.get("supplier_ref"),
                         note=b.get("note"),
                         who=_jo.label(CONFIG_PATH))
        if not pid:
            return jsonify({"ok": False, "error": "That could not be recorded."}), 400
        return jsonify({"ok": True, "id": pid, "order_id": oid})

    @app.route("/orders/purchase/remove", methods=["POST"])
    def orders_purchase_remove():
        from domain import order_purchases as _op
        b = request.get_json(silent=True) or {}
        aid, mkt, oid, bad = _scope(b, "removed")
        if bad:
            return bad
        # `purchase_id`, never `id`: auth/guard reads a body `id` as an account.
        n = _op.remove(CONFIG_PATH, aid, mkt, oid, b.get("purchase_id"))
        if not n:
            return jsonify({"ok": False, "error": (
                "That record was not found on this order, so nothing was "
                "removed.")}), 404
        return jsonify({"ok": True, "removed": n})
