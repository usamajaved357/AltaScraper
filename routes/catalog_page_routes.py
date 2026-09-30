"""routes/catalog_page_routes.py -- the Product Catalog (Orbit's ASINs page).

    GET /catalog/products?period=all|month|quarter|year

One endpoint. The arithmetic and the four findings live in
domain/product_catalog.py and take rows, so they are tested without a database.
This fetches the rows, the names and the costs.

WHY THE PERIOD MATTERS MORE HERE THAN ELSEWHERE. "Dead inventory" is a claim
about a window: a product with no sales in the last month is not the same as one
with no sales ever, and the difference is whether somebody should act. The window
is always stated back to the screen for that reason.

NOT TO BE CONFUSED WITH routes/catalog_routes.py, which looks up ONE ASIN on
Amazon for research. This one reads the products this account already sells, out
of the app's own database, and calls nothing.
"""
import datetime

from flask import jsonify, request

from domain import product_catalog as _pc

PERIODS = {
    "month": 30,
    "quarter": 90,
    "year": 365,
    "all": 0,
}


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None):
    """Attach /catalog/products to the app."""

    def _scope():
        # The shared resolver (routes/scope.pair): the marketplace follows the
        # account the PAGE named, not the server's open one (Rule 12).
        from routes import scope as _scope_mod
        return _scope_mod.pair(request, state=_state,
                               active_account=_active_account, cfg=_cfg,
                               config_path=CONFIG_PATH, last_resort="UK")

    @app.route("/catalog/products", methods=["GET"])
    def catalog_products():
        wsid, mkt = _scope()
        period = (request.args.get("period") or "all").strip().lower()
        if period not in PERIODS:
            period = "all"
        days = PERIODS[period]
        end = datetime.date.today().isoformat()
        start = ""
        if days:
            start = (datetime.date.today()
                     - datetime.timedelta(days=days)).isoformat()

        try:
            from data import db as _db
            con = _db.get_db(CONFIG_PATH)
            # PER-ASIN ROWS ONLY. Every day is stored twice -- an asin='*'
            # account rollup and one row per real ASIN -- and this page is about
            # products, so the rollup is not one of them. (Summing both is how
            # 11.60 once appeared as 23.20 elsewhere in this app.)
            q = ("SELECT date, asin, parent_asin, units, orders, ordered_sales, "
                 "       sessions, currency "
                 "FROM sales_daily "
                 "WHERE workspace_id=? AND marketplace=? AND asin<>'*' ")
            args = [wsid, mkt]
            if start:
                q += " AND date>=? AND date<=? "
                args += [start, end]
            rows = [dict(r) for r in con.execute(q, args).fetchall()]
            # HOW FAR BACK THE STORED SALES GO. "Earning nothing" is only a
            # finding when the sales cover the WHOLE window (bug round 30 Sep
            # 2026): with thirty days synced, "last year" called every product
            # that sold in month two dead. See product_catalog.sales_span.
            first_synced, last_synced = _pc.sales_span(CONFIG_PATH, wsid, mkt)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not read the sales table: %s"
                                     % str(e)[:180]}), 500

        # Names and pictures from the ONE shared lookup, so a product looks the
        # same here as it does on Sales, Traffic, Orders and the media library.
        names, known = {}, []
        try:
            from domain import catalogue as _cat
            idx = _cat.index(CONFIG_PATH, wsid, mkt) or {}
            for rec in idx.values():
                a = str((rec or {}).get("asin") or "").strip().upper()
                if a and a not in names:
                    names[a] = rec
                    known.append(a)
        except Exception:
            pass

        # WHICH PRODUCTS COUNT AS "LISTED AND EARNING NOTHING".
        #
        # Only ones the catalogue actually knows about. A product absent from
        # BOTH the catalogue and the sales table has not been shown to be dead
        # -- it has not been shown to exist -- and counting it would turn a
        # reporting gap into an accusation.
        sold = {str(r.get("asin") or "").upper() for r in rows}
        extra = [a for a in known if a not in sold]

        # COSTS FOR THIS ACCOUNT ONLY.
        #
        # The store is keyed "<account>::<SKU>". Splitting off the account and
        # keeping the SKU would let one account's cost appear against another's
        # product wherever two accounts happen to use the same SKU -- and these
        # accounts do reuse SKU shapes, so it would happen. The prefix is
        # matched, not discarded.
        #
        # THROUGH cogs_store.find, THE ONE MATCHER (bug round 30 Sep 2026). This
        # split the keys itself and stored them UPPER-CASED, then looked them
        # up by the catalogue's SKU exactly as spelled -- "10.99_3Days_B0..."
        # never matched "10.99_3DAYS_B0...", so costs the owner had entered
        # showed as "not set". find() is account-scoped and case-insensitive,
        # the same rule every other cost reader uses (Rule 12).
        costs = {}
        try:
            from domain import cogs_store as _cogs
            _ov = _cogs.all_overrides(CONFIG_PATH) or {}
            for rec in names.values():
                sku = str((rec or {}).get("sku") or "").strip()
                if not sku or sku in costs:
                    continue
                v, _k = _cogs.find(_ov, wsid, sku)
                if v is not None:
                    costs[sku] = v
        except Exception:
            pass

        covered = bool(first_synced) and (not start or first_synced <= start)
        out = _pc.build(rows, names=names, costs=costs, extra_asins=extra,
                        sales_cover=covered)
        # The marketplace's currency, so the screen prints money in the
        # currency it is actually in rather than the account's default.
        currency = ""
        for r in rows:
            if r.get("currency"):
                currency = str(r["currency"])
                break
        if not currency:
            try:
                from domain import sourcing as _src
                currency = _src.CURRENCY_FOR.get(str(mkt or "").upper(), "")
            except Exception:
                currency = ""
        out.update({"ok": True, "account": wsid, "marketplace": mkt,
                    "period": period, "start": start, "end": end,
                    "currency": currency,
                    "sales_first_date": first_synced,
                    "sales_last_date": last_synced,
                    "sales_cover_window": covered,
                    "rows_read": len(rows),
                    "catalogue_known": len(known)})
        if not rows and not known:
            out["note"] = ("Nothing has been stored for this account and "
                           "marketplace yet — no sales rows and no catalogue "
                           "snapshot. Sync a sales report or refresh the "
                           "listings first.")
        return jsonify(out)
