"""routes/monitor_routes.py — ASIN Monitor endpoints.

Stage 2: CRUD over the tracked-ASIN list. Stage 3: alerts / status / check-now / history from
the hourly checker. No Slack anywhere — in-app only.

register(app, ...) injection pattern.
"""
from flask import request, jsonify


def register(app, *, CONFIG_PATH, _cfg=None):
    from monitor import asin_monitor as _mon
    from monitor import checker as _chk

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

    # ---- Stage 3: alerts / status / manual check / history ----
    @app.route("/monitor/alerts")
    def monitor_alerts():
        unread = request.args.get("unread") in ("1", "true", "yes")
        return jsonify({"ok": True,
                        "alerts": _chk.get_alerts(CONFIG_PATH, unread_only=unread, limit=200),
                        "unread": _chk.unread_count(CONFIG_PATH),
                        "status": _chk.status()})

    @app.route("/monitor/alerts/read", methods=["POST"])
    def monitor_alerts_read():
        b = request.get_json(force=True) or {}
        _chk.mark_alerts_read(CONFIG_PATH, ids=b.get("ids"))   # ids omitted -> mark all read
        return jsonify({"ok": True, "unread": _chk.unread_count(CONFIG_PATH)})

    @app.route("/monitor/status")
    def monitor_status():
        return jsonify({"ok": True, "status": _chk.status(),
                        "unread": _chk.unread_count(CONFIG_PATH)})

    @app.route("/monitor/check_now", methods=["POST"])
    def monitor_check_now():
        if _cfg is None:
            return jsonify({"ok": False, "error": "config unavailable"}), 500
        return jsonify(_chk.check_now_async(_cfg(), CONFIG_PATH))

    @app.route("/monitor/history")
    def monitor_history():
        asin = (request.args.get("asin") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip() or None
        if not asin:
            return jsonify({"ok": False, "error": "asin required"}), 400
        return jsonify({"ok": True, "history": _chk.get_history(CONFIG_PATH, asin, mkt)})
