"""routes/daily_routes.py -- the daily round.

    "i want to design a page where all of these metrics results are being shown
     and it highlights the things which are off track"

Assembles what each check needs and hands it to domain/daily_check.py, which
does the judging. The awkward part lives here on purpose: some of these are on
disk already and some need a live Amazon call, and keeping that out of the
domain module is what makes the judgements testable without a network.

NOTHING HERE FAILS THE WHOLE PAGE. Every source is fetched inside its own try,
and a source that cannot be read leaves its key ABSENT from the context — which
domain/daily_check.py reports as "could not look" rather than as "fine". A daily
round where one broken feed turns twelve checks green is worse than no round.
"""
import datetime as _dt

from flask import jsonify, request

from domain import daily_check as _dc


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /daily/* to the app."""

    def _scope():
        aid = (request.args.get("id") or request.args.get("account_id")
               or "").strip()
        mkt = (request.args.get("marketplace") or "").strip().upper()
        if not aid or not mkt:
            acc = {}
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = aid or str(acc.get("id")
                             or (_state or {}).get("active_account_id") or "")
            mkt = mkt or str(acc.get("default_marketplace")
                             or (_state or {}).get("active_marketplace")
                             or "").upper()
        return aid, mkt

    @app.route("/daily/check")
    def daily_check():
        """Run the whole round for the open account."""
        wsid, mkt = _scope()
        if not wsid or not mkt:
            return jsonify({"ok": False, "error": (
                "Open an account and pick a marketplace first.")}), 400

        ctx = {"now": _dt.datetime.now(_dt.timezone.utc)}
        notes = []

        # ---- orders: LIVE, because ship-by dates are not stored ------------
        # order_lines keeps a status but no LatestShipDate, and "late" is the
        # one hard line on this page. One call a day is what the person doing
        # this by hand was making anyway.
        try:
            fn = app.view_functions.get("orders_list")
            if fn:
                with app.test_request_context(
                        "/orders/list?days=2&account=" + wsid):
                    resp = fn()
                data = resp[0] if isinstance(resp, tuple) else resp
                j = data.get_json() if hasattr(data, "get_json") else data
                if j and j.get("ok"):
                    ctx["orders"] = j.get("orders") or j.get("rows") or []
        except Exception as e:
            notes.append("orders: %s" % str(e)[:120])

        # ---- the stored catalogue -----------------------------------------
        try:
            from domain import live_snapshots as _snap
            rec = _snap.get(CONFIG_PATH, wsid, mkt) or {}
            if rec.get("items") is not None:
                ctx["listings"] = rec.get("items") or []
            ts = rec.get("ts")
            if ts:
                ctx["data_age_hours"] = max(
                    0.0, (_dt.datetime.now().timestamp() - float(ts)) / 3600.0)
        except Exception as e:
            notes.append("catalogue: %s" % str(e)[:120])

        # ---- stock ---------------------------------------------------------
        try:
            from domain import catalogue as _cat
            from domain import cogs_store as _cs
            from domain import inventory_view as _iv
            try:
                idx = _cat.index(CONFIG_PATH, wsid, mkt, include_drafts=True)
            except Exception:
                idx = {}
            rows = _iv.rows(CONFIG_PATH, wsid, mkt,
                            overrides=_cs.all_overrides(CONFIG_PATH),
                            catalogue=idx)
            cock = _iv.cockpit(rows) or {}
            counts = _iv.counts(rows) or {}
            ctx["cockpit"] = {
                "need_ordering": counts.get("order now", 0)
                                 + counts.get("stockout likely", 0),
                "already_out": sum(1 for r in rows if r.get("already_out")),
                "headline": cock.get("headline") or "",
            }
        except Exception as e:
            notes.append("stock: %s" % str(e)[:120])

        # ---- the real selling rate, from recorded stock history -------------
        # Separate from the cockpit above because it answers a different
        # question: not "what does the app think needs ordering" but "what is
        # selling faster than its cover lasts", measured over the days each
        # product was actually in stock. Left out of ctx entirely when it
        # fails, so the check reports "could not look" rather than "fine".
        try:
            from domain import stock_metrics as _sm
            ctx["coverage"] = _sm.for_account(CONFIG_PATH, wsid, mkt, window=30)
        except Exception as e:
            notes.append("coverage: %s" % str(e)[:120])

        # ---- suppliers with nothing left to buy ----------------------------
        try:
            from domain import stock_alerts as _alerts
            got = _alerts.for_account(CONFIG_PATH, wsid, mkt) or {}
            ctx["supplier_alerts"] = got.get("alerts") or []
        except Exception as e:
            notes.append("suppliers: %s" % str(e)[:120])

        # ---- what the repricer did, and SKUs it found gone -----------------
        try:
            from data import db as _db
            conn = _db.get_db(CONFIG_PATH)
            since = (_dt.datetime.now()
                     - _dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            ctx["repricer_actions"] = [dict(r) for r in conn.execute(
                "SELECT applied FROM sourcing_actions "
                "WHERE workspace_id=? AND marketplace=? AND at>=?",
                (wsid, mkt, since)).fetchall()]
            ctx["delisted"] = [dict(r) for r in conn.execute(
                "SELECT sku FROM sourcing_enrolment "
                "WHERE workspace_id=? AND marketplace=? AND listing_state='gone'",
                (wsid, mkt)).fetchall()]
        except Exception as e:
            notes.append("repricer: %s" % str(e)[:120])

        # ---- yesterday's sales --------------------------------------------
        try:
            from data import db as _db
            y = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
            conn = _db.get_db(CONFIG_PATH)
            # The '*' row is the ACCOUNT TOTAL Amazon reports directly. Preferred
            # over summing the per-ASIN rows: a day can carry the total without
            # the breakdown, and summing an absent breakdown gives 0, which
            # would read as "you sold nothing yesterday".
            row = conn.execute(
                "SELECT ordered_sales AS s FROM sales_daily "
                "WHERE workspace_id=? AND marketplace=? AND date=? AND asin='*'",
                (wsid, mkt, y)).fetchone()
            if not (row and row["s"] is not None):
                row = conn.execute(
                    "SELECT SUM(COALESCE(ordered_sales,0)) AS s, COUNT(*) AS n "
                    "FROM sales_daily WHERE workspace_id=? AND marketplace=? "
                    "AND date=? AND asin<>'*'", (wsid, mkt, y)).fetchone()
                if not (row and row["n"]):
                    row = None
            if row and row["s"] is not None:
                ctx["total_sales"] = float(row["s"])
        except Exception as e:
            notes.append("sales: %s" % str(e)[:120])

        # ---- advertising ----------------------------------------------------
        # DELIBERATELY LEFT ABSENT unless a day of it really exists. ads_daily
        # is the only per-day source and nothing writes it yet; the uploaded
        # Search Term Report covers a whole window, so filling this from it
        # would put a week's spend under yesterday's heading.
        try:
            from data import db as _db
            y = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
            row = _db.get_db(CONFIG_PATH).execute(
                "SELECT SUM(COALESCE(spend,0)) AS sp, SUM(COALESCE(ad_sales,0)) AS sa,"
                "       SUM(COALESCE(ad_orders,0)) AS o "
                "FROM ads_daily WHERE workspace_id=? AND marketplace=? AND date=?",
                (wsid, mkt, y)).fetchone()
            if row and row["sp"] is not None:
                ctx["ads"] = {"spend": row["sp"], "sales": row["sa"],
                              "orders": row["o"]}
        except Exception:
            pass

        out = _dc.run(ctx)
        out["ok"] = True
        out["account"] = wsid
        out["marketplace"] = mkt
        out["ran_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if notes:
            out["notes"] = notes
        return jsonify(out)
