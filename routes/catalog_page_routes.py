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
        costs = {}
        try:
            from domain import cogs_store as _cogs
            prefix = "%s::" % wsid
            for k, v in (_cogs.all_overrides(CONFIG_PATH) or {}).items():
                ks = str(k)
                if not ks.startswith(prefix):
                    continue
                sku = ks[len(prefix):].strip().upper()
                if sku:
                    costs[sku] = v
        except Exception:
            pass

        out = _pc.build(rows, names=names, costs=costs, extra_asins=extra)
        out.update({"ok": True, "account": wsid, "marketplace": mkt,
                    "period": period, "start": start, "end": end,
                    "rows_read": len(rows),
                    "catalogue_known": len(known)})
        if not rows and not known:
            out["note"] = ("Nothing has been stored for this account and "
                           "marketplace yet — no sales rows and no catalogue "
                           "snapshot. Sync a sales report or refresh the "
                           "listings first.")
        return jsonify(out)
