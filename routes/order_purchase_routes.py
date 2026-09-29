"""routes/order_purchase_routes.py -- "I bought this order from the supplier".

    POST /orders/purchase          record that one order was bought
    POST /orders/purchase/remove   forget one such record

A RECORD, NOT A PURCHASE. Nothing here contacts a supplier or spends money; the
person buys on the supplier's own site and says so here. The rules live in
domain/order_purchases.py.

THE ACCOUNT MUST BE NAMED. Unlike the older tracking routes, these never fall
back to the server's open account (domain/order_scope.py, shared with the
dispatch routes; CLAUDE.md Rule 14). The guard (auth/guard.py) has already
checked the signed-in person may use the account named.
"""
from flask import jsonify, request

from domain import order_scope as _osc
from domain import request_account as _req_acct


def register(app, *, CONFIG_PATH, _cfg):
    """Attach /orders/purchase* to the app."""

    def _scope(b, what):
        """(account_id, marketplace, order_id, None) or (.., refusal)."""
        try:
            acc, mkt, oid = _osc.resolve(_cfg, _req_acct.named_now(),
                                         b.get("marketplace"), b.get("order_id"), what)
        except _osc.ScopeError as e:
            return "", "", "", (jsonify({"ok": False, "error": str(e)}), e.status)
        return str(acc.get("id")), mkt, oid, None

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
