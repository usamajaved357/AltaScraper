"""routes/tracker_routes.py -- the four trackers and the one alert count.

    Orbit's menu: All Trackers, BSR Tracker, BuyBox Tracker, Price Tracker, Fee
    Tracker, and Alerts.

Six menu items, one set of endpoints, because the four trackers are one engine
pointed at different numbers (domain/trackers.py) and Alerts is that engine's
off-track rows. Six routes would be five copies of the same handler.

    GET  /trackers            every row, or one metric's rows with ?metric=bsr
    GET  /trackers/summary    counts per tracker -- the All Trackers screen
    GET  /trackers/alerts     the off-track rows and the badge count
    GET  /trackers/history    one ASIN + one metric, for the sparkline
    POST /trackers/watch      turn one on or off, set its target
    POST /trackers/refresh    go and read the numbers now

NOTHING HERE IS ON A TIMER. Reading costs an API call per ASIN, and the ASIN
Monitor already learned this lesson the hard way -- it was rebuilt to be off by
default with a chosen interval after "i dont want the asin monitor to be working
always". A refresh happens when the button is pressed. If a schedule is wanted
later it belongs in monitor/schedule.py, which already exists for exactly this
and would then cover both.
"""
from flask import jsonify, request

from domain import trackers as _t


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /trackers/* to the app."""

    def _scope():
        """(workspace_id, marketplace) for this request.

        Same resolution as the weekly and daily screens: an explicit id wins, and
        the active account fills in what was not sent. Kept identical so a
        screen cannot be looking at one account while its trackers look at
        another -- the exact fault that put another account's orders on the
        Orders tab.
        """
        aid = (request.args.get("id") or request.args.get("account_id") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip().upper()
        body = request.get_json(silent=True) or {}
        aid = aid or str(body.get("id") or body.get("account_id") or "").strip()
        mkt = mkt or str(body.get("marketplace") or "").strip().upper()
        if not aid or not mkt:
            acc = {}
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = aid or str(acc.get("id") or (_state or {}).get("active_account_id") or "")
            mkt = mkt or str(acc.get("default_marketplace")
                             or (_state or {}).get("active_marketplace") or "").upper()
        return aid, (mkt or "UK")

    def _names(wsid, mkt):
        """{asin: product name}, from the catalogue the rest of the app uses.

        Through domain/catalogue so there is ONE product-name lookup and this
        screen cannot show a different name from every other screen. A failure
        here costs the names and nothing else -- the numbers are the point.
        """
        try:
            from domain import catalogue as _cat
            idx = _cat.index(CONFIG_PATH, wsid, mkt) or {}
            out = {}
            for row in (idx.values() if isinstance(idx, dict) else idx):
                if not isinstance(row, dict):
                    continue
                a = str(row.get("asin") or "").strip().upper()
                if a and a not in out:
                    out[a] = row.get("title") or row.get("name") or ""
            return out
        except Exception:
            return {}

    @app.route("/trackers", methods=["GET"])
    def trackers_list():
        wsid, mkt = _scope()
        metric = (request.args.get("metric") or "").strip().lower() or None
        if metric and metric not in _t.METRICS:
            return jsonify({"ok": False, "error": "Unknown tracker: %s" % metric}), 400
        rows = _t.rows(CONFIG_PATH, wsid, metric, _names(wsid, mkt))
        return jsonify({"ok": True, "account": wsid, "marketplace": mkt,
                        "metric": metric or "", "rows": rows,
                        "metrics": _t.METRICS})

    @app.route("/trackers/summary", methods=["GET"])
    def trackers_summary():
        wsid, mkt = _scope()
        s = _t.summary(CONFIG_PATH, wsid, _names(wsid, mkt))
        return jsonify({"ok": True, "account": wsid, "marketplace": mkt,
                        "summary": s,
                        "alerts": _t.alerts(CONFIG_PATH, wsid)["count"]})

    @app.route("/trackers/alerts", methods=["GET"])
    def trackers_alerts():
        wsid, mkt = _scope()
        a = _t.alerts(CONFIG_PATH, wsid, _names(wsid, mkt))
        return jsonify({"ok": True, "account": wsid, "marketplace": mkt,
                        "count": a["count"], "rows": a["rows"]})

    @app.route("/trackers/history", methods=["GET"])
    def trackers_history():
        wsid, _mkt = _scope()
        asin = (request.args.get("asin") or "").strip().upper()
        metric = (request.args.get("metric") or "").strip().lower()
        if not asin or metric not in _t.METRICS:
            return jsonify({"ok": False, "error": "Need an asin and a known metric."}), 400
        try:
            limit = int(request.args.get("limit") or 60)
        except ValueError:
            limit = 60
        return jsonify({"ok": True, "asin": asin, "metric": metric,
                        "points": _t.history(CONFIG_PATH, wsid, asin, metric, limit)})

    @app.route("/trackers/watch", methods=["POST"])
    def trackers_watch():
        wsid, _mkt = _scope()
        b = request.get_json(silent=True) or {}
        asin = str(b.get("asin") or "").strip().upper()
        metric = str(b.get("metric") or "").strip().lower()
        if not asin:
            return jsonify({"ok": False, "error": "Which ASIN?"}), 400
        if metric not in _t.METRICS:
            return jsonify({"ok": False, "error": "Unknown tracker: %s" % metric}), 400
        # `on` and `target` are both optional, so a screen can flip the switch
        # without knowing the target and set the target without flipping the
        # switch. An absent key means "leave it alone"; an empty target string
        # means "clear it", which is a different thing and has to stay so.
        on = b.get("on", None)
        target = b.get("target", None)
        if target is None and "target" in b:
            target = ""
        return jsonify(_t.watch_set(CONFIG_PATH, wsid, asin, metric,
                                    on=on, target=target))

    @app.route("/trackers/refresh", methods=["POST"])
    def trackers_refresh():
        """Read every tracked number now.

        Synchronous on purpose. The list is what the user chose to watch, it is
        typically tens of ASINs rather than a whole catalogue, and the offers
        call takes twenty at a time -- so this is seconds, and a progress-polled
        background job would be more machinery than the job deserves.
        """
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        metrics = b.get("metrics") or None
        if metrics and not isinstance(metrics, list):
            metrics = [str(metrics)]
        try:
            import accounts as _acc
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
            acc = next((a for a in accts if str(a.get("id")) == str(wsid)), None)
            if not acc:
                return jsonify({"ok": False,
                                "error": "That account is not connected."}), 400
            creds = _acc.account_creds(acc)
            seller_id = str(acc.get("seller_id") or "")
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the account: %s" % str(e)[:160]}), 500
        try:
            from domain import tracker_fetch as _fetch
            res = _fetch.refresh(CONFIG_PATH, wsid, creds, mkt, seller_id,
                                 metrics=metrics)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "%s: %s" % (type(e).__name__, str(e)[:180])}), 502
        res["alerts"] = _t.alerts(CONFIG_PATH, wsid)["count"]
        return jsonify(res)
