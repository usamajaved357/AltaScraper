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
    import domain.request_account as _req_acct

    def _price_cache(wsid, mkt):
        """Remembered per-order product sales, or None if the store is not up.

        Pricing an order costs an Amazon call each; the hourly page is already
        storing exactly these numbers, so the Sales screen reads from the same
        table rather than paying for them twice. Never fatal: without a cache
        the figures are identical, only slower.
        """
        try:
            import domain.hourly_week as _hw
            return _hw.price_cache(CONFIG_PATH, wsid, mkt)
        except Exception:
            return None

    def _account_by_id(aid):
        """The account record for an id the PAGE named, or None."""
        try:
            import accounts as _acc_mod
            return _acc_mod.get_account(_cfg(), aid, CONFIG_PATH)
        except Exception:
            return None

    def _scope():
        """Which workspace and marketplace this request is about.

        THE ACCOUNT COMES FROM THE PAGE, not from the process-wide global.
        _state["active_account_id"] is one variable for the whole server, so an
        in-flight read could be answered after a workspace switch had moved it
        -- and it was: opening Nestwell Goods, switching away and back showed
        figures belonging to whichever account the global had drifted to. The
        marketplace on the line below has always been taken from the request
        first; the account now follows the same rule, and for the same reason.
        See domain/request_account.py.
        """
        aid, acc = _req_acct.for_read(request, _state, get_account=_account_by_id)
        if acc is None:
            # No account named by the page (an older screen, or a background job
            # with no page behind it) -- fall back to the global, as before.
            try:
                acc = _active_account()
            except Exception:
                acc = None
        wsid = str(aid or (acc or {}).get("id")
                   or _state.get("active_account_id", "") or "") or "dropshipping"
        mkt = (request.args.get("marketplace")
               or (request.get_json(silent=True) or {}).get("marketplace")
               or _state.get("active_marketplace") or "").upper()
        return acc, wsid, mkt

    def _cogs_overrides():
        """The manual COGS overrides dashboard.py holds, if it is loaded.

        Read through rather than copied: the overrides are one dict, owned in one
        place, and a second copy here would go stale the moment someone typed a
        cost on the listings screen.
        """
        try:
            import dashboard as _d
            return getattr(_d, "_COGS_OVERRIDE", None)
        except Exception:
            return None

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
            # PARSED, not sliced. A slice accepts "banana!!" and hands it to SQL,
            # where it silently matches nothing and the screen reads as "no sales"
            # rather than "that is not a date".
            try:
                s = _dt.datetime.strptime(a["start"][:10], "%Y-%m-%d").date()
                e = _dt.datetime.strptime(a["end"][:10], "%Y-%m-%d").date()
                if s > e:
                    s, e = e, s          # a backwards range is a slip, not a request
                return s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d"), "custom"
            except ValueError:
                pass                     # fall through to the preset below
        if preset == "ytd":
            return "%d-01-01" % end.year, end.strftime("%Y-%m-%d"), preset
        days = {"7d": 7, "14d": 14, "30d": 30, "60d": 60, "90d": 90}.get(preset, 30)
        start = end - _dt.timedelta(days=days - 1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), preset

    def _basis():
        """WHICH CALENDAR Amazon's money is reported on. Decided in ONE place.

        "order"  every fee and refund sits on the day its order was PLACED --
                 the same day its sale is on -- so a row reads across.
        "money"  the cash view: what landed in the account this week.

        Measured on jack_uk, Amazon settles 10 to 12 days after the order, so
        these are genuinely different reports and both are worth having.

        THE DEFAULT IS "order", and that is the fix for the P&L heatmap. It
        used to be "money", with the grid overriding it to "order" for itself
        and the cards left on the default -- so one screen ran two calendars
        and showed 18.32 of revenue on a day with no orders, and no orders on
        the day that took three. Orbit's own rule is the same: "Orders API
        wins for top-line because it's realtime order-date basis."

        Anything that genuinely wants the cash view asks for basis=money.
        """
        b = (request.args.get("basis") or "order").lower()
        return b if b in ("money", "order") else "order"

    def _basis_note(basis):
        """Said out loud, every time, wherever the basis is reported.

        A grid whose fees are on the order's day and a grid whose fees are on
        the payment day look identical and are different reports; leaving the
        reader to work it out is how the two-calendar problem stayed invisible.
        """
        return ("Amazon's fees and refunds are shown on the day the ORDER was "
                "placed, so every row describes the same trade."
                if basis == "order" else
                "Amazon's fees and refunds are shown on the day the MONEY MOVED, "
                "which is 10-12 days after the order on this account. Sales above "
                "them are dated by the order, so the two do not line up.")

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

        _vat = _sd.vat_rate_for(_cfg, wsid)
        # THE CARDS ARE ON THE SAME CALENDAR AS THE GRID BELOW THEM. They are
        # sums of the very rows it draws, so the basis has to be handed in here
        # too. It was not: the cards stayed on the money calendar while the grid
        # moved to the order one, and the same screen showed a period's sales
        # against a different period's fees.
        _meta = {}
        cur = _sd.totals(CONFIG_PATH, wsid, mkt, start, end, asin, _vat,
                         basis=_basis(), meta=_meta)
        span = (_dt.datetime.strptime(end, "%Y-%m-%d")
                - _dt.datetime.strptime(start, "%Y-%m-%d")).days + 1
        p_end = (_dt.datetime.strptime(start, "%Y-%m-%d") - _dt.timedelta(days=1))
        p_start = p_end - _dt.timedelta(days=span - 1)
        prev = _sd.totals(CONFIG_PATH, wsid, mkt, p_start.strftime("%Y-%m-%d"),
                          p_end.strftime("%Y-%m-%d"), asin, _vat,
                          basis=_basis())
        # "WAS £0" AND "THERE WAS NO BEFORE" ARE NOT THE SAME CLAIM.
        #
        # Summing a window with no rows in it gives zero, and the card then
        # printed "was : £0" -- stating that the previous month took nothing.
        # For an account that did not exist yet that is not a measurement, it is
        # an assertion about a period nobody has looked at. Reported as "the
        # prior period dotted lines are not accurate".
        #
        # The screen already knows how to say "no earlier period" -- see
        # _sDelta -- and shows it when the previous figures are absent rather
        # than zero. So when the whole comparison window falls before this
        # account's first data, the figures are withheld instead of invented.
        _avail = _sd.availability(CONFIG_PATH, wsid, mkt)
        _from = ((_avail.get("sales") or {}).get("first_date") or "")
        if _from and p_end.strftime("%Y-%m-%d") < _from:
            prev = {"days": 0, "currency": cur.get("currency"),
                    "_before_any_data": True}

        def delta(k):
            a, b = cur.get(k), prev.get(k)
            try:
                if a is None or not b:
                    return None          # no baseline is not "0% change"
                return round((float(a) - float(b)) / float(b) * 100, 1)
            except Exception:
                return None

        # PROFIT AND MARGIN ARE CARDS TOO.
        #
        # They were already being calculated -- totals carried profit 80.11,
        # margin_pct 20.0, cogs 215.78 -- and the cards showed only revenue,
        # orders, units and ad spend. So the screen computed the one number the
        # business actually runs on and then did not display it, and "I cannot
        # see the profit margin on the sales tab" was exactly right.
        #
        # Placed after revenue and before the volume counts, because that is the
        # order the question gets asked in: what came in, what was left, on what
        # margin, off how many units.
        cards = []
        for key, label, kind in (("ordered_sales", "Revenue", "money"),
                                 ("net_revenue", "Net of VAT", "money"),
                                 ("profit", "Profit", "money"),
                                 ("margin_pct", "Margin", "pct"),
                                 ("cogs", "Stock cost", "money"),
                                 ("total_fees", "Amazon fees", "money"),
                                 ("orders", "Orders", "count"),
                                 ("units", "Units", "count"),
                                 ("refunds", "Refunds", "money"),
                                 ("spend", "Ad Spend", "money")):
            cards.append({"key": key, "label": label, "kind": kind,
                          "value": cur.get(key), "previous": prev.get(key),
                          "delta_pct": delta(key)})
        avail = _sd.availability(CONFIG_PATH, wsid, mkt)

        # Why profit may be blank. Without this the screen can only show an
        # em-dash, and an em-dash where a profit should be reads as a fault
        # rather than as "three of these products have never been costed".
        from domain import cogs as _cogs
        cov = _cogs.coverage(CONFIG_PATH, (_acc or {}).get("id") or wsid, mkt,
                             _cogs_overrides())
        # "and it fills in" would NOT have been true. Cost is priced onto each day
        # when that day's finance data is pulled, so a cost typed today does not
        # reach days already stored -- pressing Sync re-fetches them and re-prices
        # them, and only then does profit appear. Saying so is the difference
        # between a screen that looks broken and one that tells you the next step.
        cov["note"] = ("" if cov["unknown"] == 0 else
                       "%d of %d SKUs have no cost, so profit is only shown for "
                       "periods where every unit shipped was costed. Set a cost on "
                       "the listings screen, or rebuild the SKU, then press Sync -- "
                       "costs are applied when each day is pulled, so already-pulled "
                       "days need re-pulling before profit appears."
                       % (cov["unknown"], cov["total"]))

        # PROFIT ON THE ORDERS PLACED IN THIS WINDOW, from the owner's own cost
        # prices. The `profit` card above is dated by when the MONEY MOVED, so on
        # a window whose orders have not settled it describes different trades
        # from the sales beside it -- which is how "Total Sales £0" came to sit
        # next to "Profit £80". Amazon cannot answer this one: it reports no
        # profit against an order until settlement. The owner can, because they
        # know what the stock cost. Asked for exactly that.
        #
        # Sent alongside rather than replacing the settled figure: they answer
        # different questions and both are worth having.
        try:
            from domain import order_profit as _op
            from domain import order_cogs as _oc
            # Freeze a cost onto any line that has not got one yet, at the price
            # that applied WHEN THAT ORDER ARRIVED. Done before reading, so a
            # newly-synced day is costed the first time it is looked at; lines
            # that already carry a cost are never touched, which is what stops
            # last month's profit moving when a supplier changes their price.
            _mode = _oc.mode_for(_cfg, wsid)
            try:
                _oc.freeze_range(CONFIG_PATH, wsid, mkt, start, end, _mode,
                                 _cogs_overrides())
            except Exception:
                pass          # costing is best-effort; the figures still come back
            # THE SAME REVENUE THE CARDS SHOW is handed in, so profit cannot be
            # worked out over a different set of trade. Deriving it twice, from
            # two stores filled by two passes over two windows, produced
            # "Total Sales 1,248, Profit 1,728" on a live account.
            est = _op.for_period(CONFIG_PATH, wsid, mkt, start, end,
                                 _cogs_overrides(),
                                 vat_rate=_vat,
                                 ads_connected=bool(avail["ads"]["connected"]),
                                 ad_spend=cur.get("spend") or 0.0,
                                 revenue=cur.get("ordered_sales"),
                                 units=cur.get("units"))
            est["cogs_mode"] = _mode
            # Profit is now built from the SAME revenue and unit count as the
            # cards, so there is no longer a period-coverage question to answer:
            # the two describe the same trade by construction. What can still be
            # incomplete is the COST side, and est["warning"] says so in units.
            est["period_units"] = cur.get("units")
            est["covers_all"] = True
        except Exception as e:
            est = {"profit": None, "error": str(e)[:200]}

        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "start": start, "end": end, "preset": preset,
                        "asin": asin, "currency": cur.get("currency"),
                        "basis": _meta.get("basis") or _basis(),
                        "basis_note": _basis_note(_meta.get("basis") or _basis()),
                        "cards": cards, "totals": cur, "previous": prev,
                        "compared_to": {"start": p_start.strftime("%Y-%m-%d"),
                                        "end": p_end.strftime("%Y-%m-%d")},
                        "ads_connected": avail["ads"]["connected"],
                        "ads_note": avail["ads"]["note"],
                        "order_profit": est,
                        "cogs_coverage": cov})

    @app.route("/sales/products")
    def sales_products():
        """The product filter's options: what actually sold in this window."""
        from domain import sales_data as _sd
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end, _preset = _range()
        items = _sd.products(CONFIG_PATH, wsid, mkt, start, end)
        return jsonify({"ok": True, "start": start, "end": end,
                        "count": len(items), "products": items})

    @app.route("/sales/breakdown")
    def sales_breakdown():
        """Sales per product, optionally rolled up to the parent."""
        from domain import sales_data as _sd
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end, _preset = _range()
        group = "parent" if (request.args.get("group") or "").lower() == "parent" else "asin"
        rows = _sd.breakdown(CONFIG_PATH, wsid, mkt, start, end, group)
        return jsonify({"ok": True, "start": start, "end": end, "group": group,
                        "rows": rows, "count": len(rows),
                        "currency": _sd.currency_of(rows),
                        "note": ("" if rows else
                                 "No per-product sales in this period yet — press "
                                 "Sync to pull them from Amazon.")})

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

        # The basis is chosen by _basis(), which is the only place that reads
        # the parameter -- see the note there on why the default is "order".
        _meta = {}
        rows = _sd.series(CONFIG_PATH, wsid, mkt, start, end, asin,
                          vat_rate=_sd.vat_rate_for(_cfg, wsid),
                          basis=_basis(), meta=_meta)
        # The basis USED, not the one asked for: a product filter cannot be
        # re-dated and falls back to money. Echoing the request instead would
        # label money-basis figures with the order-basis note.
        basis = _meta.get("basis") or _basis()
        buckets, order = _sd.bucket(rows, gran)

        metrics = []
        for key, label, kind, good, _how in _sd.METRICS:
            cells = [_sd.aggregate(buckets[b], key) for b in order]
            if any(c is not None for c in cells):
                metrics.append({"key": key, "label": label, "kind": kind,
                                "good": good, "cells": cells})
        return jsonify({"ok": True, "start": start, "end": end, "preset": preset,
                        "granularity": gran, "asin": asin,
                        "basis": basis, "basis_note": _basis_note(basis),
                        "basis_gap": _meta.get("basis_note") or "",
                        # Where Amazon's settled figures and its own order
                        # totals disagree -- stated, not silently reconciled.
                        "tie_out": _meta.get("tie_out") or None,
                        "currency": _sd.currency_of(rows),
                        "columns": order, "metrics": metrics,
                        # Which section each metric belongs in, so the grid can
                        # band itself the way Orbit's does -- Sales & revenue,
                        # PPC, Costs, Traffic -- instead of listing thirty-odd
                        # rows flat. Sent as a list of (section, keys) so the
                        # ORDER is the server's and not rebuilt in the browser.
                        "sections": [{"name": n, "keys": k} for n, k in
                                     _sd.sections_for([m["key"] for m in metrics])],
                        "empty": not rows})

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
        days = int(b.get("days") or 30)
        creds = _acc_mod.account_creds(acc)
        res = _sf.sync(CONFIG_PATH, wsid, mkt,
                       _acc_mod.marketplace_id(mkt) if hasattr(_acc_mod, "marketplace_id") else "",
                       creds, days_back=days,
                       budget=int(b.get("budget") or _sf.BACKFILL_PER_PASS))

        # THE LIVE FEED HAS THE LAST WORD ON WHAT SOLD, and it runs AFTER the
        # report so its answer is the one that survives. The report is the same
        # measurement arriving a day or more later, not a newer one -- measured
        # on nestwell_goods, three days where it had sent nothing while the
        # Orders API held 173.43 of real sales. See domain/live_reconcile.py.
        try:
            from domain import live_reconcile as _lr
            import domain.hourly_week as _hw
            res["live"] = _lr.reconcile(
                CONFIG_PATH, wsid, mkt,
                _acc_mod.marketplace_id(mkt) if hasattr(_acc_mod, "marketplace_id") else "",
                creds, days=int(b.get("live_days") or 14),
                price_cache=_price_cache(wsid, mkt))
        except Exception as e:
            # Never fatal: the report half already succeeded, and saying which
            # half failed beats losing both.
            res["live"] = {"error": str(e)[:200]}

        # Fees and refunds come from a DIFFERENT Amazon API, so it gets its own
        # result rather than being folded into the sales one. If Finances fails
        # and Sales succeeded, that is a partial success and the screen should be
        # able to say which half worked.
        if b.get("finance", True):
            from domain import finance_fetch as _ff
            res["finance"] = _ff.sync(CONFIG_PATH, wsid, mkt, creds,
                                      account_id=(acc or {}).get("id") or wsid,
                                      days_back=days,
                                      next_token=b.get("finance_token"),
                                      cogs_overrides=_cogs_overrides())
        return jsonify(res), (200 if res.get("ok") else 502)

    @app.route("/sales/hourly")
    def sales_hourly():
        """Today by the hour, with yesterday behind it -- Orbit's Live Sales card.

        Built from the SAME order fetch /sales/today already uses, so this adds
        a shape to data the app was pulling anyway rather than a second call to
        Amazon. Orders as PLACED, in the account's own timezone; a different
        measurement from the settled figures below it, and the card says so.
        """
        from domain import orders_live as _ol
        from domain import hourly_sales as _hs
        try:
            import accounts as _acc_mod
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        if not acc or not _acc_mod.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error":
                            "Live orders need this workspace's own Amazon "
                            "account."}), 400
        try:
            # From the START OF YESTERDAY, so both lines come from one fetch.
            start = _ol.day_start(mkt, 1)
            orders, truncated = _ol.fetch_since(
                mkt,
                _acc_mod.marketplace_id(mkt) if hasattr(_acc_mod, "marketplace_id") else "",
                _acc_mod.account_creds(acc), start)
            out = _hs.curve(orders, tz=str(_ol.marketplace_zone(mkt)))
            out["ok"] = True
            out["truncated"] = truncated
            if truncated:
                out["note"] = ("Amazon stopped returning orders part-way "
                               "through, so the curve is incomplete rather "
                               "than low.")
            return jsonify(out)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 502

    @app.route("/sales/today")
    def sales_today():
        """Today so far, from the Orders API -- the one thing the report cannot have.

        Deliberately NOT merged into the grid. Orders are counted here the moment
        they are placed and in the report only once Amazon has settled what the
        order finally was, so the two disagree by design. Shown beside the grid,
        labelled as live, rather than as a column pretending to be the same
        measurement.
        """
        from domain import orders_live as _ol
        try:
            import accounts as _acc_mod
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        if not acc or not _acc_mod.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error":
                            "Live orders need this workspace's own Amazon "
                            "account."}), 400
        try:
            return jsonify(_ol.today(
                mkt,
                _acc_mod.marketplace_id(mkt) if hasattr(_acc_mod, "marketplace_id") else "",
                _acc_mod.account_creds(acc),
                compare=(request.args.get("compare", "1") != "0"),
                price_cache=_price_cache(wsid, mkt)))
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 502

    @app.route("/sales/recent")
    def sales_recent():
        """The last few days of orders, from the ORDERS API.

        "but in amazn i am able to see the sales from yesterday accurately, why
        not here" -- because Seller Central reads this feed and the chart was
        reading the Sales & Traffic report, which runs a day or two behind.

        Both count an order on the day it was PLACED, so this fills the report's
        missing tail with the same measurement rather than a different one. It
        is a separate request on purpose: the chart draws from the report as
        soon as it arrives, and this only ever adds the days the report has not
        covered.
        """
        try:
            from domain import orders_live as _ol
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        try:
            from domain import accounts as _acc_mod
        except Exception:
            try:
                import accounts as _acc_mod
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500
        acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        if not acc or not _acc_mod.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error":
                            "Live orders need this workspace's own Amazon "
                            "account."}), 400
        try:
            days = int(request.args.get("days") or 5)
        except (TypeError, ValueError):
            days = 5
        try:
            out = _ol.by_day(
                mkt,
                _acc_mod.marketplace_id(mkt) if hasattr(_acc_mod, "marketplace_id") else "",
                _acc_mod.account_creds(acc),
                days=days,
                price_cache=_price_cache(wsid, mkt))
            out["ok"] = True
            return jsonify(out)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 502

    @app.route("/sales/finance-raw")
    def sales_finance_raw():
        """One page of financial events, EXACTLY as Amazon sends it.

        A diagnostic, not part of the dashboard. The finance parser is written to
        Amazon's documented shape, and documented is not observed -- CLAUDE.md
        Rule 4 says read the real response rather than assume it. Open this once
        against a live account, confirm the field names, then it has done its job.
        """
        from domain import finance_fetch as _ff
        try:
            import accounts as _acc_mod
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        acc, wsid, mkt = _scope()
        if not mkt or not acc:
            return jsonify({"ok": False, "error": "open an account workspace first"}), 400
        if not _acc_mod.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error":
                            "borrowed credentials cannot read another account's "
                            "finances"}), 400
        start, end, _p = _range()
        try:
            return jsonify({"ok": True, "start": start, "end": end,
                            "raw": _ff.raw_sample(mkt, _acc_mod.account_creds(acc),
                                                  start, end)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:400]}), 502
