"""domain/order_profit.py -- profit on orders PLACED, from the seller's own costs.

WHY THIS EXISTS
The Sales cards showed "Total Sales GBP 0" beside "Profit GBP 80". Both figures
were right and they described different trades, because Amazon dates its two
feeds differently:

    Orders API / Sales & Traffic report   dated by when the order was PLACED
    finance records                       dated by when the MONEY MOVED

An order placed yesterday is a sale yesterday and a profit whenever Amazon
settles it, which can be weeks. Profit came from the settled side while sales
came from the ordered side, so a row of five cards contradicted itself.

Amazon cannot answer "what did I make on yesterday's orders" -- it reports no
profit against an unsettled order. The seller can, because they know what the
stock cost. Asked for exactly that: "yes use my cost prices for profit".

WHAT IS SUBTRACTED, AND WHERE EACH PART COMES FROM

    revenue        item price + the postage the buyer paid -- everything the
                   buyer handed over, which is the owner's definition:
                   "this is the total revenue i generated ... the fees are cut
                   afterwards from it"
    - VAT          where the company is registered. Amazon reports these order
                   values with VAT already inside them, and that portion is
                   HMRC's, not the seller's. Per account, answered on the
                   account form, never assumed.
    - Amazon fees  estimated until the settlement arrives, at the rate THIS
                   account actually pays, measured from its own settled history
    - stock cost   frozen onto the order when it was seen (domain/order_cogs)
    - promotions   coupons, deals and percent-off funded by the seller. Amazon
                   reports these SEPARATELY from the price, not inside it: the
                   Finances API puts Principal in ItemChargeList and the
                   discount in PromotionList, on the same shipment item. So the
                   revenue above is what the buyer was CHARGED BEFORE the
                   coupon, and the coupon is money that never arrives. Measured
                   on jack_uk: 11.60 funded across five orders, e.g. 29 Jul
                   principal 116.64 with 3.50 of promotion beside it.

                   Taken per ORDER, from order_fees, for two reasons: it keeps
                   the figure on the order's own calendar (see the two calendars
                   above), and finance_daily stores every day TWICE -- an
                   asin='*' rollup row plus one row per real ASIN -- so summing
                   that table without filtering gives exactly double. The series
                   readers filter on asin='*'; a hand-written SUM over the whole
                   table does not, which is how 11.60 first looked like 23.20.
    - charges      postage out, prep, a hand-allocated ad figure
                   (domain/asin_charges)
    - ad spend     ONLY when the Advertising API is connected. Nothing is
                   subtracted while it is not, and the figure says so: "when the
                   api is not there do not subtract anything".

MISSING COSTS ARE NOT ZERO COSTS -- BUT THEY DO NOT HIDE THE FIGURE EITHER
Asked for: "if no cogs are added show profit as wrong i agree do not subtract
cogs this is the standard way, the user should know he needs to add cogs
otherwise the profit numbers wont be accurate."

So an uncosted unit contributes its revenue and no cost, which OVERSTATES profit
-- and every reply says so, loudly, with the count and the products involved.
The overstatement is deliberate and declared, not accidental and hidden.
"""

# Amazon's most common referral rate, and the same constant the Orders screen
# already estimates a single order with. Imported rather than redeclared so
# there is one number, not two that drift.
try:
    from domain.orders_view import DEFAULT_REFERRAL_RATE
except Exception:                                    # importable in isolation
    DEFAULT_REFERRAL_RATE = 0.15

# Below this, a measured rate is not worth trusting -- a couple of settled orders
# can be atypical, and the fee rate moves profit more than anything else here.
MIN_PRINCIPAL_FOR_RATE = 50.0

# How far back to look for settled history when measuring the rate.
RATE_WINDOW_DAYS = 120


def fee_rate(config_path, workspace_id, marketplace, end_date,
             days=RATE_WINDOW_DAYS):
    """(rate, basis, detail) -- what Amazon actually charges THIS account.

    Measured from the finance records: every fee Amazon has taken, over
    everything buyers were charged, across the recent settled past. That is this
    seller's own products in their own categories, which a flat 15% is not.
    """
    import datetime as _dt
    try:
        end = _dt.date.fromisoformat(str(end_date))
    except Exception:
        end = _dt.date.today()
    start = end - _dt.timedelta(days=int(days))

    try:
        from domain import finance_data as _fd
        rows = _fd.series(config_path, workspace_id, marketplace,
                          start.isoformat(), end.isoformat())
    except Exception:
        rows = {}

    # REFERRAL AND FBA ONLY. `other_fees` is where Amazon's charges that are NOT
    # a share of a sale land -- above all the monthly Professional selling
    # subscription. Measured on jack_uk: 25.00 of it arrived on 2026-08-14
    # against 0.00 of sales that day, and including it turned a real 17.5% fee
    # rate into 24.1%, which then came off every estimated profit as though the
    # subscription scaled with revenue. The exported CSV shows 17-18% per day,
    # which is what gave the game away.
    #
    # A fixed monthly cost is a real cost and belongs in the P&L -- it is simply
    # not a RATE, and multiplying it by sales is not a way to charge it.
    fees = principal = other = 0.0
    for r in (rows or {}).values():
        for k in ("referral_fees", "fba_fees"):
            try:
                fees += float(r.get(k) or 0.0)
            except (TypeError, ValueError):
                pass
        try:
            other += float(r.get("other_fees") or 0.0)
        except (TypeError, ValueError):
            pass
        try:
            principal += float(r.get("principal") or 0.0)
        except (TypeError, ValueError):
            pass

    if principal >= MIN_PRINCIPAL_FOR_RATE and fees > 0:
        rate = round(fees / principal, 4)
        detail = ("%.1f%% -- referral and FBA fees Amazon actually charged this "
                  "account on %.2f of settled sales since %s"
                  % (rate * 100, principal, start.isoformat()))
        if other:
            # Named, not hidden. It is money that left the account and the owner
            # should see it; it simply is not part of a per-sale rate.
            detail += (" (a further %.2f of fixed charges, such as the monthly "
                       "selling subscription, is not a per-sale fee and is not "
                       "in this rate)" % other)
        return rate, "measured", detail
    return DEFAULT_REFERRAL_RATE, "assumed", (
        "%.0f%% -- Amazon's usual referral rate, used because this account has "
        "no settled history to measure yet" % (DEFAULT_REFERRAL_RATE * 100))


def for_lines(lines, rate, vat_rate=None, charge_of=None, promos_by_order=None):
    """Profit across order lines, and exactly what it does not cover.

    `promos_by_order` is {order_id: amount funded}. Optional, so a caller that
    has not looked them up behaves exactly as before rather than failing.

    `lines` are order_lines rows: sku, units, revenue (item price), shipping
    (what the buyer paid for postage), cogs (frozen when the order was seen).
    `charge_of` is f(asin, sku, date) -> (per_unit, parts) from asin_charges.
    """
    revenue = goods = postage = cogs = charges = 0.0
    covered_revenue = 0.0
    units = costed_units = 0
    missing, orders = {}, set()
    charge_parts = {}

    for L in lines or []:
        sku = str((L or {}).get("sku") or "")
        asin = str((L or {}).get("asin") or "")
        try:
            qty = int((L or {}).get("units") or 0)
        except (TypeError, ValueError):
            qty = 0
        try:
            item = float((L or {}).get("revenue") or 0.0)
        except (TypeError, ValueError):
            item = 0.0
        try:
            ship = float((L or {}).get("shipping") or 0.0)
        except (TypeError, ValueError):
            ship = 0.0
        oid = str((L or {}).get("order_id") or "")
        if oid:
            orders.add(oid)

        line_rev = item + ship
        revenue += line_rev
        goods += item
        postage += ship
        units += qty

        cost = (L or {}).get("cogs")
        if cost is None:
            # Counted, named, and reported -- NOT treated as zero silently. The
            # figure is knowingly overstated by this line's cost, and the reply
            # says by how many units and which products.
            missing[sku or asin or "(no sku)"] = \
                missing.get(sku or asin or "(no sku)", 0) + qty
        else:
            try:
                cogs += float(cost) * qty
            except (TypeError, ValueError):
                pass
            costed_units += qty
            covered_revenue += line_rev

        if charge_of:
            try:
                per_unit, parts = charge_of(asin, sku,
                                            str((L or {}).get("purchase_date") or "")[:10])
            except Exception:
                per_unit, parts = 0.0, []
            charges += float(per_unit or 0) * qty
            for p in (parts or []):
                charge_parts[p["label"]] = round(
                    charge_parts.get(p["label"], 0.0) + float(p["amount"] or 0) * qty, 2)

    revenue = round(revenue, 2)

    # WHAT THE COUPON TOOK. Counted once per ORDER, never per line: a promotion
    # is recorded against the order, and adding it up per line would subtract it
    # as many times as the order had items.
    promos = 0.0
    if promos_by_order:
        for _oid in orders:
            try:
                promos += float(promos_by_order.get(_oid) or 0.0)
            except (TypeError, ValueError):
                pass
    promos = round(promos, 2)

    # VAT COMES OUT FIRST. Amazon reports these values with it already inside,
    # so it was never the seller's money and no fee or margin should be worked
    # out against it.
    vat = 0.0
    if vat_rate:
        try:
            r = float(vat_rate)
            if 0 < r < 1:
                vat = round(revenue * r / (1.0 + r), 2)
        except (TypeError, ValueError):
            vat = 0.0
    net_revenue = round(revenue - vat, 2)

    fees = round(net_revenue * float(rate), 2)
    cogs = round(cogs, 2)
    charges = round(charges, 2)
    # The fee is still worked out on net_revenue, NOT on revenue after the
    # coupon: Amazon charges its referral fee on the price the buyer paid, and a
    # seller-funded discount does not reduce it. Subtracting the promotion from
    # the base before applying the rate would quietly understate the fee.
    profit = round(net_revenue - fees - cogs - charges - promos, 2)
    margin = round(profit / net_revenue * 100, 1) if net_revenue else None

    return {
        "profit": profit,
        "margin_pct": margin,
        "revenue": revenue,
        "goods": round(goods, 2),
        "postage": round(postage, 2),
        "vat": vat,
        "net_revenue": net_revenue,
        "fees": fees,
        "cogs": cogs,
        "charges": charges,
        "promos": promos,
        "charge_parts": [{"label": k, "amount": v}
                         for k, v in sorted(charge_parts.items())],
        "units": units,
        "costed_units": costed_units,
        "orders": len(orders),
        "complete": (not missing) and bool(units),
        "missing_skus": sorted(missing.keys())[:20],
        "missing_units": sum(missing.values()),
        # Said plainly, because the number is knowingly too high without it.
        "warning": ("" if not missing else
                    "%d of %d units have no cost recorded, so nothing was "
                    "subtracted for them and this profit is HIGHER than the "
                    "truth. Set a cost on those products to fix it."
                    % (sum(missing.values()), units)),
    }


def for_period(config_path, workspace_id, marketplace, start, end,
               overrides=None, vat_rate=None, ads_connected=False,
               ad_spend=0.0, revenue=None, units=None):
    """Profit on orders PLACED between two dates, from the seller's own costs.

    Returns the figure, how the fee rate was arrived at, and what it does not
    cover -- so the screen can state all three rather than showing a number and
    hoping.
    """
    lines = lines_between(config_path, workspace_id, marketplace, start, end)
    rate, basis, detail = fee_rate(config_path, workspace_id, marketplace, end)

    def _charge_of(asin, sku, on_date):
        from domain import asin_charges as _ac
        return _ac.per_unit(config_path, workspace_id, marketplace, asin,
                            sku=sku, on_date=on_date)

    # WHAT EACH ORDER'S COUPON COST, keyed by order id so it lands on the
    # ORDER's calendar rather than the settlement's. order_fees already holds it
    # per order; only settled orders have one, which is correct -- an unsettled
    # order has not had its promotion reported yet, and inventing one would be a
    # guess. Never fatal: a missing table means no promotions, not no profit.
    promos_by_order = {}
    try:
        from data import db as _db
        conn = _db.get_db(config_path)
        for r in conn.execute(
                "SELECT order_id, SUM(promos) p FROM order_fees "
                "WHERE workspace_id=? AND marketplace=? AND IFNULL(promos,0) <> 0 "
                "GROUP BY order_id", (workspace_id, marketplace)):
            promos_by_order[str(r["order_id"])] = float(r["p"] or 0.0)
    except Exception:
        promos_by_order = {}

    out = for_lines(lines, rate, vat_rate=vat_rate, charge_of=_charge_of,
                    promos_by_order=promos_by_order)

    # REVENUE COMES FROM THE FIGURE ON THE CARD, not from a second derivation.
    #
    # This used to add up order_lines itself. order_lines and sales_daily are
    # filled by different passes over different windows, so on a live account
    # they drifted -- and profit was worked out over MORE trade than sales was,
    # which produced "Total Sales 1,248, Profit 1,728". Profit exceeding revenue
    # is not a rounding fault, it is two different questions on one row.
    #
    # Given the revenue the screen is showing, everything is recomputed against
    # it, so the two cannot disagree by construction. The lines are still used
    # for what only they know: what the stock cost, and which units have no cost.
    if revenue is not None:
        try:
            rev = round(float(revenue), 2)
        except (TypeError, ValueError):
            rev = out["revenue"]
        vat = 0.0
        if vat_rate:
            try:
                r = float(vat_rate)
                if 0 < r < 1:
                    vat = round(rev * r / (1.0 + r), 2)
            except (TypeError, ValueError):
                vat = 0.0
        net = round(rev - vat, 2)
        fees = round(net * float(rate), 2)
        # The promotion is subtracted here too. This branch recomputes profit
        # against the revenue the CARD is showing, and it used to drop every
        # deduction the first pass had worked out except cogs and charges -- so
        # on any window the screen supplied a revenue for, the coupon came back.
        profit = round(net - fees - out["cogs"] - out["charges"]
                       - float(out.get("promos") or 0.0), 2)
        out.update({
            "revenue": rev, "vat": vat, "net_revenue": net, "fees": fees,
            "profit": profit,
            "margin_pct": round(profit / net * 100, 1) if net else None,
            # The unit count the screen is showing, so "x of y units have no
            # cost" counts against the same y the owner can see.
            "units": int(units) if units is not None else out["units"],
        })
        _u = out["units"] or 0
        _missing = max(0, _u - int(out["costed_units"] or 0))
        out["missing_units"] = _missing
        out["complete"] = (_missing == 0 and _u > 0)
        out["warning"] = ("" if not _missing else
                          "%d of %d units have no cost recorded, so nothing was "
                          "subtracted for them and this profit is HIGHER than "
                          "the truth. Set a cost on those products to fix it."
                          % (_missing, _u))

    # AD SPEND ONLY WHEN IT IS KNOWN. Asked for: build it the way Orbit does --
    # subtracted once the Advertising API is connected, and nothing subtracted
    # at all while it is not. A guessed ad figure would move profit more than
    # anything else on this screen.
    out["ads_connected"] = bool(ads_connected)
    out["ad_spend"] = round(float(ad_spend or 0), 2) if ads_connected else None
    if ads_connected and ad_spend:
        out["profit"] = round(out["profit"] - float(ad_spend), 2)
        out["margin_pct"] = (round(out["profit"] / out["net_revenue"] * 100, 1)
                             if out["net_revenue"] else None)

    out.update({
        "rate": rate, "rate_basis": basis, "rate_detail": detail,
        "start": start, "end": end, "basis": "order",
        "vat_rate": vat_rate,
        "note": ("Worked out from your own cost prices, because Amazon reports "
                 "no profit against an order until it settles. Fees: " + detail
                 + ("" if ads_connected else
                    " Advertising is not connected, so no ad spend is "
                    "subtracted.")),
    })
    return out


def lines_between(config_path, workspace_id, marketplace, start, end):
    """Stored order lines for orders PLACED in the window.

    purchase_date is the full UTC timestamp Amazon sent, so the range is
    compared on its date part.
    """
    from data import db as _db
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT order_id, sku, asin, units, revenue, shipping, cogs, "
        "       cogs_source, currency, status, purchase_date "
        "FROM order_lines "
        "WHERE workspace_id=? AND marketplace=? "
        "  AND substr(purchase_date, 1, 10) >= ? "
        "  AND substr(purchase_date, 1, 10) <= ? ",
        (workspace_id, marketplace, str(start), str(end))).fetchall()
    # Cancelled orders are not sales and must not carry a profit either.
    dead = ("canceled", "cancelled")
    return [dict(r) for r in rows
            if str(r["status"] or "").lower() not in dead]
