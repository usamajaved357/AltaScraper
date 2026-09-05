"""routes/ads_routes.py -- advertising figures for screens that are not Sales.

WHY A FILE OF ITS OWN
The Sales page's advertising panels live in sales_routes.py because they belong
to that screen's period and its scope. This is the other shape: "for these
products, what did advertising cost", asked by the Listings page and by anything
else that shows a product rather than a period.

WHAT IT DOES NOT DO
It does not compute ACOS twice. domain/sales_data.py already defines ACOS as
spend over ad_sales and the Sales page reads it from there; this returns the same
ratio built the same way, from the same table, and adds no second definition of
what a rate means (CLAUDE.md Rule 12).

IT READS. Nothing here asks Amazon for anything -- it queries ads_daily, which
domain/ads_sync.py fills. A screen that renders a hundred rows must not be able
to make a hundred API calls.

THE ASIN IS OURS, NOT THE COMPETITOR'S
Every row on the Listings page carries two ASINs: the one in its SKU, which is a
COMPETITOR reference used to pull product data during generation, and the account's
own live ASIN. Advertising is bought against OURS. The browser decides which is
which -- static/js/listings.js rowAsin() already owns that rule -- and sends only
the ones it has resolved, so this endpoint never has to guess and can never
report a competitor's ASIN as having cost us money.
"""
from flask import jsonify, request

from routes import scope as _scope_mod


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state):
    """Attach /ads/* to the app."""
    import domain.request_account as _req_acct

    def _account_by_id(aid):
        try:
            import accounts as _acc_mod
            return _acc_mod.get_account(_cfg(), aid, CONFIG_PATH)
        except Exception:
            return None

    def _scope():
        """Which workspace and marketplace this request is about.

        The SAME resolver sales_routes uses, in the same order -- the account
        the PAGE named first, the global only as a fallback. routes/scope.py
        exists precisely so this is not decided a fifteenth way (Rule 12).
        """
        aid, acc = _req_acct.for_read(request, _state, get_account=_account_by_id)
        if acc is None:
            try:
                acc = _active_account()
            except Exception:
                acc = None
        wsid = str(aid or (acc or {}).get("id")
                   or _state.get("active_account_id", "") or "") or "_no_account"
        mkt = _scope_mod.marketplace(
            state=_state, account=(acc or {}),
            asked=(request.args.get("marketplace")
                   or (request.get_json(silent=True) or {}).get("marketplace")))
        return acc, wsid, mkt

    def _window(default_days=30):
        """The period to sum over. Defaults to 30 days ending yesterday.

        Same rule as domain/ads_sync.window(): today is always partial, and a
        part-day counted as a whole one makes the most recent figure dip.
        """
        import datetime as dt
        start = (request.args.get("start") or "").strip()
        end = (request.args.get("end") or "").strip()
        if start and end:
            return start, end
        try:
            days = max(1, min(400, int(request.args.get("days") or default_days)))
        except (TypeError, ValueError):
            days = default_days
        e = dt.date.today() - dt.timedelta(days=1)
        return (e - dt.timedelta(days=days - 1)).isoformat(), e.isoformat()

    @app.route("/ads/by-asin")
    def ads_by_asin():
        """Advertising cost and return, per ASIN, for this workspace.

        Optional ?asins=B0...,B0... narrows it to the products a screen is
        actually showing. Without it, every advertised ASIN in the window comes
        back -- which is what a page wants when it is about to render all of
        them anyway, and is one query either way.

        An ASIN with no advertising is ABSENT from the reply rather than present
        with zeros. A product that was never advertised and a product that was
        advertised and sold nothing are different facts, and the screen has to
        be able to tell them apart.
        """
        from data import db as _db
        _acc, wsid, mkt = _scope()
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        start, end = _window()

        want = [a.strip().upper() for a in
                (request.args.get("asins") or "").split(",") if a.strip()]
        sql = ("SELECT asin, SUM(impressions) impressions, SUM(clicks) clicks, "
               "SUM(spend) spend, SUM(ad_orders) ad_orders, SUM(ad_sales) ad_sales "
               "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
               "AND date>=? AND date<=? AND asin<>'*'")
        args = [wsid, mkt, start, end]
        if want:
            # Chunked into the placeholders SQLite will accept rather than
            # interpolated -- a screen can legitimately ask about hundreds.
            want = want[:900]
            sql += " AND asin IN (%s)" % ",".join("?" * len(want))
            args += want
        sql += " GROUP BY asin"

        out = {}
        conn = _db.get_db(CONFIG_PATH)
        for r in conn.execute(sql, args):
            spend, sales, clicks = r["spend"], r["ad_sales"], r["clicks"]
            out[r["asin"]] = {
                "impressions": r["impressions"], "clicks": clicks,
                "spend": spend, "ad_orders": r["ad_orders"], "ad_sales": sales,
                # None, never 0, when there is no ratio to state: spend with no
                # sales has no ACOS, and 0% would read as perfect efficiency.
                "acos": (100.0 * spend / sales) if (spend is not None and sales) else None,
                "roas": (sales / spend) if (sales is not None and spend) else None,
                "cpc": (spend / clicks) if (spend is not None and clicks) else None,
            }

        # Whether the account is connected at all, so a screen can tell "no ad
        # spend on this product" from "this app cannot see your advertising".
        try:
            from domain import sales_data as _sd
            av = _sd.availability(CONFIG_PATH, wsid, mkt).get("ads") or {}
        except Exception:
            av = {}
        return jsonify({"ok": True, "workspace": wsid, "marketplace": mkt,
                        "start": start, "end": end,
                        "connected": bool(av.get("connected")),
                        "note": av.get("note") or "",
                        "asins": out, "count": len(out)})
