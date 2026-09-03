"""routes/revenue_routes.py -- what one unit actually earns, at a given price.

    "Currently clicking 'Calculate revenue' navigates to the product detail
     page. Amazon opens a side drawer with a Revenue Calculator."

ONE ROUTE, AND IT DECIDES NOTHING:

    GET /listing/revenue?sku=...&price=...&shipping=...

Every number in the answer is fetched from the module that already owns it,
which is the whole design (CLAUDE.md Rule 12):

    Amazon's charges   domain/amazon_fees.breakdown_for -- the three-tier
                       resolver: what Amazon actually took on this product's
                       settled orders, else Amazon's own quote, else this
                       account's measured referral rate. Never a flat 15%.
    the cost           domain/cogs.resolve -- the typed override, else the
                       SKU's own price prefix, else nothing known.
    units sold         domain/listing_metrics.for_skus -- the same 30-day
                       figures the listing row shows.
    our ASIN           domain/listing_metrics.own_asins -- NEVER the ASIN in
                       the SKU, which is the competitor this listing was
                       researched from (CLAUDE.md Rule 1). A fee quoted against
                       somebody else's ASIN would be a fee for their product's
                       category.

NOTHING HERE CALLS AMAZON. breakdown_for reads the stored quote and the
measured rate; it does not fetch. So the drawer can be dragged through a dozen
prices without spending a single SP-API call, and it works with SP-API down.
The "ask Amazon for this product's fees" button is /sourcing/fees and stays
where it is.

WHY SHIPPING IS A SEPARATE INPUT. Amazon's referral fee is charged on what the
BUYER PAID -- item plus any postage they were charged -- so a calculator that
takes only the item price understates the fee on every order with postage.
amazon_fees.estimate says so in its own docstring; this passes the sum.

NET PROCEEDS IS NOT PROFIT AND IS NOT CALLED PROFIT. It is what arrives minus
what Amazon takes minus what the unit cost. It excludes postage you buy, ads,
storage, and returns, because this app does not hold those per unit -- and a
"profit" figure that quietly omitted them would be trusted.
"""
from flask import request, jsonify

from domain import amazon_fees as _fees
from domain import listing_metrics as _lm


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def register(app, *, CONFIG_PATH, _cfg, _active_account, _state, _resolve_cogs):
    """Attach /listing/revenue. `_resolve_cogs` is the app's COGS override map."""

    def _scope():
        acc = _active_account() or {}
        wsid = str(acc.get("id") or _state.get("active_account_id") or "")
        mkt = str(request.args.get("mkt")
                  or acc.get("default_marketplace")
                  or _state.get("active_marketplace") or "UK").strip().upper()
        return wsid, mkt, acc

    @app.route("/listing/revenue")
    def listing_revenue():
        wsid, mkt, acc = _scope()
        if not wsid:
            return jsonify({"ok": False,
                            "error": "open an account workspace first"}), 400
        sku = (request.args.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400

        # OUR ASIN, and the drawer says so when there is none. Amazon quotes a
        # fee against an ASIN's category; without ours there is nothing to look
        # up and the referral falls back to the account's measured rate --
        # which breakdown_for already reports as its basis rather than passing
        # off as a quote.
        asin = ""
        try:
            asin = (_lm.own_asins(CONFIG_PATH, wsid, mkt, [sku]) or {}).get(sku, "")
        except Exception:
            asin = ""

        # THE PRICE BEING ASKED ABOUT, sent by the drawer as it is typed. The
        # browser already holds the listing's price and passes it on the first
        # call, so this route does not read the listings table at all -- one
        # fewer thing that can disagree with what is on screen.
        price = _f(request.args.get("price"), 0.0) or 0.0
        shipping = _f(request.args.get("shipping"), 0.0) or 0.0
        if price < 0 or shipping < 0:
            return jsonify({"ok": False,
                            "error": "price and shipping cannot be negative"}), 400

        # Amazon takes its cut on what the buyer paid, postage included.
        gross = round(float(price) + float(shipping), 2)

        # ---- what the stock cost -------------------------------------------
        # The app's own resolver, not a second reading of the SKU here: it
        # applies the typed override first and falls back to the SKU's price
        # prefix, and that order is the whole point of the field.
        try:
            cost, cost_source = _resolve_cogs(wsid, sku)
        except Exception:
            cost, cost_source = None, ""

        # ---- what Amazon takes ---------------------------------------------
        # is_fba comes from the stock reading, not from a guess: stock_daily
        # carries the fulfilment channel per SKU. Unknown is treated as
        # merchant, which is what breakdown_for's FBA line already says
        # ("not charged -- you post this yourself") and is true of these
        # accounts -- measured, all 100 SKUs with a reading are DEFAULT.
        is_fba = False
        metrics = {}
        try:
            metrics = (_lm.for_skus(CONFIG_PATH, wsid, mkt, [sku]) or {}).get(sku, {})
            is_fba = str(metrics.get("fulfillment") or "").upper() in ("AMAZON", "AFN")
        except Exception:
            metrics = {}

        cur = _mkt_currency(mkt)
        try:
            fees = _fees.breakdown_for(CONFIG_PATH, wsid, mkt, asin, gross,
                                       is_fba=is_fba, currency=cur)
        except Exception as e:
            return jsonify({"ok": False, "error": "fees: %s" % str(e)[:200]}), 500

        taken = _f(fees.get("total"), 0.0) or 0.0
        net = round(gross - taken - (cost or 0.0), 2) if cost is not None else None
        # MARGIN IS A SHARE OF WHAT THE BUYER PAID, which is the same base
        # Amazon's referral fee uses -- so the two figures on this panel are
        # measured against the same thing.
        margin = (round(net / gross * 100.0, 1)
                  if (net is not None and gross > 0) else None)

        return jsonify({
            "ok": True,
            "sku": sku,
            "asin": asin,
            "currency": cur,
            "price": round(float(price), 2),
            "shipping": round(float(shipping), 2),
            "gross": gross,
            "cost": cost,
            "cost_source": cost_source,
            "fees": fees,
            "fees_total": round(taken, 2),
            "net": net,
            "margin_pct": margin,
            # Context, not part of the sum: how this product has actually been
            # selling, so a margin can be read as "on 12 units" rather than in
            # the abstract. Absent stays absent -- see listing_metrics.
            "units_30d": metrics.get("units"),
            "sales_30d": metrics.get("sales"),
            "fulfilment": metrics.get("fulfillment") or "",
        })

    def _mkt_currency(mkt):
        """The currency Amazon charges in for this marketplace.

        Small enough to live here, and it agrees with static/js/marketplaces.js
        -- if this ever grows past a handful it belongs in one shared table.
        """
        m = str(mkt or "").upper()
        if m in ("US", "USA"):
            return "USD"
        if m in ("CA",):
            return "CAD"
        if m in ("AU",):
            return "AUD"
        if m in ("DE", "FR", "IT", "ES", "NL", "BE", "IE", "PL", "SE"):
            return "EUR"
        return "GBP"
