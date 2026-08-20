"""routes/leading_routes.py -- Leading Indicators.

    Orbit's screen: yesterday's figures against their own history, expressed in
    standard deviations, with an ON TRACK status.

    GET /leading   the whole screen for one account and marketplace

ONE ENDPOINT, because the screen is one answer. The arithmetic is in
domain/leading.py and takes rows rather than a database, so the sigma maths can
be tested exhaustively without one -- which is what makes it worth trusting.
This file only fetches the rows.

NOTHING IS FETCHED FROM AMAZON HERE. Every figure comes from sales_daily, which
the app already syncs. That is the point of the screen: it is a new READING of
data that has been sitting there all along, not a new thing to download.
"""
import datetime

from flask import jsonify, request

from domain import leading as _lead


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /leading to the app."""

    def _scope():
        aid = (request.args.get("id") or request.args.get("account_id") or "").strip()
        mkt = (request.args.get("marketplace") or "").strip().upper()
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

    @app.route("/leading", methods=["GET"])
    def leading_screen():
        wsid, mkt = _scope()
        day = (request.args.get("day") or "").strip() or _lead.yesterday()
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            return jsonify({"ok": False, "error": "Bad date: %s" % day}), 400
        try:
            window = int(request.args.get("window") or _lead.WINDOW_DAYS)
        except ValueError:
            window = _lead.WINDOW_DAYS
        window = max(_lead.MIN_DAYS + 1, min(window, 365))
        start = (datetime.date.fromisoformat(day)
                 - datetime.timedelta(days=window)).isoformat()
        try:
            # The query moved into domain/leading.rows_for so the weekly brief
            # reads the same rows by the same rule -- including the rollup-vs-
            # per-ASIN choice, which is the part that doubles the figures when
            # it is got wrong. See that function for the measurement.
            rows = _lead.rows_for(CONFIG_PATH, wsid, mkt, start, day)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the daily figures: %s"
                                     % str(e)[:180]}), 500
        # Rows come back per ASIN per day; domain/leading groups them by day and
        # combines them by each indicator's own rule (a rate is recomputed from
        # its parts, never averaged across products).
        out = _lead.build(rows, day=day, window_days=window)
        out["ok"] = True
        out["account"] = wsid
        out["marketplace"] = mkt
        out["rows_read"] = len(rows)
        # SAID OUT LOUD RATHER THAN LEFT TO BE NOTICED. A screen with no data
        # behind it and a screen where everything is genuinely normal look
        # identical unless one of them says so.
        if not rows:
            out["note"] = ("No daily sales or traffic has been stored for this "
                           "account and marketplace yet, so there is nothing to "
                           "compare yesterday against. Sync a sales report first.")
        return jsonify(out)
