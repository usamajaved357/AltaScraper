"""routes/finance_routes.py -- the Finance screen: contribution per product.

Reads only. It holds no arithmetic of its own: the per-product figures come from
domain/contribution.py, which in turn defers to domain/sales_data.py for the one
rule about when a contribution may be shown at all.
"""
import datetime as _dt

from flask import request, jsonify

from domain import contribution as _contrib


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach the /finance/* routes to the existing Flask app."""

    def _scope():
        acc = _active_account() or {}
        wsid = (request.args.get("id") or acc.get("id")
                or _state.get("active_account_id") or "")
        mkt = (request.args.get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        return acc, wsid, mkt

    def _range():
        """The window, resolved to two dates. Defaults to the last 30 days.

        Deliberately the same shape the Sales screen uses, so a figure here and a
        figure there cover the same days and can be compared without arithmetic.
        """
        today = _dt.date.today()
        start = (request.args.get("start") or "").strip()
        end = (request.args.get("end") or "").strip()
        if not start or not end:
            end = today.strftime("%Y-%m-%d")
            start = (today - _dt.timedelta(days=29)).strftime("%Y-%m-%d")
        return start, end

    @app.route("/finance/contribution")
    def finance_contribution():
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end = _range()
        rows, totals = _contrib.by_product(CONFIG_PATH, wsid, mkt, start, end)
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "start": start, "end": end,
                        "rows": rows, "totals": totals,
                        "notes": _contrib.notes(rows, totals),
                        "ads_connected": totals.get("ad_spend") is not None,
                        "currency": totals.get("currency") or ""})
