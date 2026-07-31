"""routes/monitor_routes.py — ASIN Monitor tracking-list endpoints (Stage 2).

CRUD over the tracked-ASIN list only. No SP-API here (Stage 3 adds the checker).

register(app, ...) injection pattern.
"""
from flask import request, jsonify


def register(app, *, CONFIG_PATH):
    from monitor import asin_monitor as _mon

    @app.route("/monitor/list")
    def monitor_list():
        return jsonify({"ok": True,
                        "asins": _mon.list_asins(CONFIG_PATH),
                        "eu_marketplaces": _mon.EU_MARKETPLACES})

    @app.route("/monitor/add", methods=["POST"])
    def monitor_add():
        b = request.get_json(force=True) or {}
        res = _mon.add(CONFIG_PATH,
                       b.get("asin", ""),
                       b.get("label", ""),
                       b.get("marketplaces"),
                       b.get("condition", "New"))
        return jsonify(res), (200 if res.get("ok") else 400)

    @app.route("/monitor/remove", methods=["POST"])
    def monitor_remove():
        b = request.get_json(force=True) or {}
        res = _mon.remove(CONFIG_PATH, asin=b.get("asin"), id=b.get("id"))
        return jsonify(res), (200 if res.get("ok") else 400)
