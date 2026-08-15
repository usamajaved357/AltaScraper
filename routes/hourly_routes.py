"""routes/hourly_routes.py -- the Hourly Sales screen.

Two endpoints, deliberately separate:

    /hourly/summary   reads what the app already holds. Fast, no Amazon call.
    /hourly/fetch     pulls orders it has not seen yet. Slow, rate limited.

Split because the fetch costs one Amazon call per order and the screen must draw
from what is already there rather than sitting blank while it runs. Opening the
page is free; filling it is a button.
"""

from flask import jsonify, request


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state, **_kw):
    from domain import hourly_week as _hw

    def _scope():
        acc = _active_account() or {}
        wsid = str(acc.get("id") or "")
        mkt = (request.args.get("marketplace") or "").strip()
        if not mkt or mkt == "__all__":
            mkt = str(acc.get("default_marketplace") or "")
        return acc, wsid, mkt

    def _days():
        try:
            d = int((request.args.get("days") or "30").rstrip("d"))
        except (TypeError, ValueError):
            d = 30
        return max(1, min(d, 90))

    @app.route("/hourly/summary")
    def hourly_summary():
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        metric = (request.args.get("metric") or "units").lower()
        try:
            out = _hw.summary(CONFIG_PATH, wsid, mkt, days=_days(), metric=metric)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 500
        out["ok"] = True
        if out.get("empty"):
            out["note"] = ("Nothing here yet. This screen is built from ORDER "
                           "TIMES, which Amazon publishes nowhere in a report — "
                           "the only source is the Orders API, one call per "
                           "order. Press Pull orders to fetch them; they are "
                           "kept, so it only ever fetches what it has not "
                           "already seen.")
        return jsonify(out)

    @app.route("/hourly/fetch", methods=["POST"])
    def hourly_fetch():
        """Pull orders in the window that the app has not stored yet."""
        try:
            from domain import accounts as _acc_mod
        except Exception:
            import accounts as _acc_mod
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        if not acc or not _acc_mod.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error":
                            "Order times need this workspace's own Amazon "
                            "account."}), 400
        try:
            days = int((request.args.get("days") or "30").rstrip("d"))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, 90))
        try:
            got = _hw.fetch(
                CONFIG_PATH, wsid, mkt,
                _acc_mod.marketplace_id(mkt) if hasattr(_acc_mod, "marketplace_id") else "",
                _acc_mod.account_creds(acc), days=days)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 502
        got["ok"] = True
        if got.get("capped"):
            got["note"] = ("More orders were waiting than one pass fetches. "
                           "Press it again to continue — everything already "
                           "pulled is kept, so nothing is fetched twice.")
        return jsonify(got)
