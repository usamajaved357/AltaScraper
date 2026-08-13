"""routes/sales_routes.py -- the Sales dashboard's endpoints.

FOUR ROUTES, AND THE ORDER MATTERS
/sales/availability is asked FIRST, before anything requests numbers. Amazon
delivers sales with a lag and never has today, so without asking what dates
genuinely exist the dashboard draws empty columns for days that were never going
to be there -- which reads as "you sold nothing" rather than "not in yet". The
Orbit audit calls this the single best idea in their API design and it is the
cheapest thing here to get right.

URL GRAMMAR
This follows the app's own /w/<workspace>/... shape rather than Orbit's
/brand/{brand}/{marketplace}. The app already has workspaces, a permission table
keyed to them, and History-API routing that understands them. A second URL
grammar would be the same class of mistake as a second copy of a function.
"""
import datetime as _dt

from flask import request, jsonify, Response


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /sales/* to the app."""

    def _scope():
        """Which workspace and marketplace this request is about."""
        acc = None
        try:
            acc = _active_account()
        except Exception:
            acc = None
        wsid = str((acc or {}).get("id") or _state.get("active_account_id", "") or "") \
            or "dropshipping"
        mkt = (request.args.get("marketplace")
               or (request.get_json(silent=True) or {}).get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        return acc, wsid, mkt

    def _range():
        """The requested window, resolved to two dates.

        Presets are resolved HERE, not in the browser: a preset computed from the
        viewer's clock means two people in different time zones asking for "7d"
        get different weeks, and neither matches the account's marketplace.
        """
        a = request.args
        end = _dt.date.today() - _dt.timedelta(days=1)     # Amazon never has today
        preset = (a.get("preset") or "30d").lower()
        if a.get("start") and a.get("end"):
            try:
                return a["start"][:10], a["end"][:10], "custom"
            except Exception:
                pass
        if preset == "ytd":
            return "%d-01-01" % end.year, end.strftime("%Y-%m-%d"), preset
        days = {"7d": 7, "14d": 14, "30d": 30, "60d": 60, "90d": 90}.get(preset, 30)
        start = end - _dt.timedelta(days=days - 1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), preset

    @app.route("/sales/availability")
    def sales_availability():
        """What dates actually have data. Asked before anything else."""
        from domain import sales_data as _sd
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        **_sd.availability(CONFIG_PATH, wsid, mkt)})

    @app.route("/sales/summary")
    def sales_summary():
        """The stat cards, each with the change against the PREVIOUS equal period.

        The comparison window is the same LENGTH immediately before, not the same
        dates last month: comparing a 31-day month against a 28-day one produces a
        double-digit "change" that is only the calendar.
        """
        from domain import sales_data as _sd
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end, preset = _range()
        asin = (request.args.get("asin") or "").strip() or None

        cur = _sd.totals(CONFIG_PATH, wsid, mkt, start, end, asin)
        span = (_dt.datetime.strptime(end, "%Y-%m-%d")
                - _dt.datetime.strptime(start, "%Y-%m-%d")).days + 1
        p_end = (_dt.datetime.strptime(start, "%Y-%m-%d") - _dt.timedelta(days=1))
        p_start = p_end - _dt.timedelta(days=span - 1)
        prev = _sd.totals(CONFIG_PATH, wsid, mkt, p_start.strftime("%Y-%m-%d"),
                          p_end.strftime("%Y-%m-%d"), asin)

        def delta(k):
            a, b = cur.get(k), prev.get(k)
            try:
                if a is None or not b:
                    return None          # no baseline is not "0% change"
                return round((float(a) - float(b)) / float(b) * 100, 1)
            except Exception:
                return None

        cards = []
        for key, label, kind in (("ordered_sales", "Revenue", "money"),
                                 ("orders", "Orders", "count"),
                                 ("units", "Units", "count"),
                                 ("spend", "Ad Spend", "money")):
            cards.append({"key": key, "label": label, "kind": kind,
                          "value": cur.get(key), "previous": prev.get(key),
                          "delta_pct": delta(key)})
        avail = _sd.availability(CONFIG_PATH, wsid, mkt)
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "start": start, "end": end, "preset": preset,
                        "asin": asin, "currency": cur.get("currency"),
                        "cards": cards, "totals": cur, "previous": prev,
                        "compared_to": {"start": p_start.strftime("%Y-%m-%d"),
                                        "end": p_end.strftime("%Y-%m-%d")},
                        "ads_connected": avail["ads"]["connected"],
                        "ads_note": avail["ads"]["note"]})

    # The metric rows, in the order the grid shows them. `good` says which
    # direction is an improvement, so a rise in ACOS is never coloured as a win.
    METRICS = [
        ("ordered_sales",     "Ordered product sales", "money",  "up"),
        ("units",             "Units ordered",         "count",  "up"),
        ("orders",            "Order items",           "count",  "up"),
        ("avg_selling_price", "Average selling price", "money",  "up"),
        ("sessions",          "Sessions",              "count",  "up"),
        ("sessions_mobile",   "Sessions — mobile",     "count",  "up"),
        ("sessions_browser",  "Sessions — browser",    "count",  "up"),
        ("page_views",        "Page views",            "count",  "up"),
        ("unit_session_pct",  "Conversion rate",       "pct",    "up"),
        ("buy_box_pct",       "Buy box",               "pct",    "up"),
        ("units_b2b",         "Units — B2B",           "count",  "up"),
        ("ordered_sales_b2b", "Sales — B2B",           "money",  "up"),
        ("impressions",       "Ad impressions",        "count",  "up"),
        ("clicks",            "Ad clicks",             "count",  "up"),
        ("spend",             "Ad spend",              "money",  "down"),
        ("ad_sales",          "Ad sales",              "money",  "up"),
    ]

    @app.route("/sales/series")
    def sales_series():
        """Metrics x dates, the shape the grid draws.

        Granularity is applied HERE. Rolling up in the browser would mean the
        export and the screen could disagree, and the export is the one people
        paste into a spreadsheet and trust.
        """
        from domain import sales_data as _sd
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end, preset = _range()
        asin = (request.args.get("asin") or "").strip() or None
        gran = (request.args.get("granularity") or "day").lower()

        rows = _sd.series(CONFIG_PATH, wsid, mkt, start, end, asin)
        buckets, order = _bucket(rows, gran)

        metrics = []
        for key, label, kind, good in METRICS:
            cells = []
            for b in order:
                cells.append(_agg(buckets[b], key, kind))
            if any(c is not None for c in cells):
                metrics.append({"key": key, "label": label, "kind": kind,
                                "good": good, "cells": cells})
        return jsonify({"ok": True, "start": start, "end": end, "preset": preset,
                        "granularity": gran, "asin": asin,
                        "currency": (rows[0]["currency"] if rows else ""),
                        "columns": order, "metrics": metrics,
                        "empty": not rows})

    def _bucket(rows, gran):
        buckets, order = {}, []
        for r in rows:
            d = r["date"]
            if gran == "week":
                dt = _dt.datetime.strptime(d, "%Y-%m-%d").date()
                key = (dt - _dt.timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
            elif gran == "month":
                key = d[:7]
            else:
                key = d
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(r)
        return buckets, order

    def _agg(rows, key, kind):
        """Sum counts and money; RECOMPUTE rates from their parts.

        Averaging seven daily conversion rates is not the week's conversion rate.
        The error is small on even days and large on uneven ones, which is exactly
        when someone is looking.
        """
        if kind == "pct":
            if key == "unit_session_pct":
                return _rate(rows, "units", "sessions")
            if key == "buy_box_pct":
                return _weighted(rows, "buy_box_pct", "page_views")
        vals = [r.get(key) for r in rows if r.get(key) is not None]
        if not vals:
            return None
        return round(sum(float(v) for v in vals), 2)

    def _rate(rows, a, b):
        num = sum(float(r.get(a) or 0) for r in rows)
        den = sum(float(r.get(b) or 0) for r in rows)
        return round(num / den * 100, 2) if den else None

    def _weighted(rows, field, weight):
        num = den = 0.0
        for r in rows:
            v, w = r.get(field), r.get(weight)
            if v is None or not w:
                continue
            num += float(v) * float(w)
            den += float(w)
        return round(num / den, 2) if den else None

    @app.route("/sales/export")
    def sales_export():
        """The grid as CSV -- the same numbers, produced by the same code.

        Built from /sales/series' own output rather than re-queried, so the file
        cannot disagree with the screen it was exported from.
        """
        from flask import current_app
        with app.test_request_context("/sales/series?" + request.query_string.decode()):
            data = app.view_functions["sales_series"]().get_json()
        if not data.get("ok"):
            return jsonify(data), 400
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Metric"] + data["columns"])
        for m in data["metrics"]:
            w.writerow([m["label"]] + ["" if c is None else c for c in m["cells"]])
        name = "sales_%s_%s_to_%s.csv" % (data.get("granularity", "day"),
                                          data["start"], data["end"])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="%s"' % name})

    @app.route("/sales/sync", methods=["POST"])
    def sales_sync_now():
        """Pull missing days from Amazon now. Paced; safe to press twice."""
        from domain import sales_fetch as _sf
        try:
            import accounts as _acc_mod
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        if not acc:
            return jsonify({"ok": False, "error":
                            "Sales data is per Amazon account -- open an account "
                            "workspace first."}), 400
        if not _acc_mod.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error":
                            "%s has no Amazon account of its own, so it cannot have "
                            "its own sales." % (acc.get("label") or wsid)}), 400
        b = request.get_json(silent=True) or {}
        res = _sf.sync(CONFIG_PATH, wsid, mkt,
                       _acc_mod.marketplace_id(mkt) if hasattr(_acc_mod, "marketplace_id") else "",
                       _acc_mod.account_creds(acc),
                       days_back=int(b.get("days") or 30),
                       budget=int(b.get("budget") or _sf.BACKFILL_PER_PASS))
        return jsonify(res), (200 if res.get("ok") else 502)
