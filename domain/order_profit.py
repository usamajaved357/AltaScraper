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
    # OVER WHAT THE BUYER PAID, VAT INCLUDED -- principal plus the tax Amazon
    # itemised beside it. Amazon charges its referral fee on the VAT-inclusive
    # price, and the other two tiers of the fee rate are measured on that same
    # base (amazon_fees.rate_from_orders: "15.0% of what the buyer paid and 18.0%
    # of the principal, and only the first can be multiplied by a shelf price").
    # This one divided by the principal alone, which on a VAT-registered account
    # is the price WITHOUT VAT -- so jack_uk measured 17.5% where Amazon takes
    # about 14.6% of the shelf price, and every listing priced on this fallback
    # was charged a fifth too much in fees. Measured 28 Sep 2026. On accounts
    # that are not VAT-registered the tax is nought and nothing changes.
    #
    # ONLY VAT, NEVER A SALES TAX. The tax column also carries US sales tax,
    # which Amazon collects as marketplace facilitator and does NOT charge its
    # referral fee on -- and which order_lines' revenue (the base the estimate
    # is applied to) leaves out. So the tax is added only on an account that is
    # VAT-registered. Found by the review of the profit work, 28 Sep 2026.
    try:
        from domain import unit_profit as _up
        _vr = _up.account_vat_rate(config_path, workspace_id)
        with_tax = _vr is not None and float(_vr) > 0
    except Exception:
        with_tax = False
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
        for k in (("principal", "tax") if with_tax else ("principal",)):
            try:
                principal += float(r.get(k) or 0.0)
            except (TypeError, ValueError):
                pass

    if principal >= MIN_PRINCIPAL_FOR_RATE and fees > 0:
        rate = round(fees / principal, 4)
        detail = ("%.1f%% -- referral and FBA fees Amazon actually charged this "
                  "account on %.2f that buyers paid (VAT included where the "
                  "account is VAT-registered) since %s"
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


def line_cogs(L):
    """What one order line's stock cost -> float, or None when it has no cost
    (NOT zero -- the owner's rule). The one answer for_lines adds up and the
    P&L ledger lists line by line (domain/pnl_ledger)."""
    L = L or {}
    cost = L.get("cogs")
    if cost is None:
        return None
    try:
        qty = int(L.get("units") or 0)
    except (TypeError, ValueError):
        qty = 0
    try:
        return float(cost) * qty
    except (TypeError, ValueError):
        return 0.0


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

        line_cost = line_cogs(L)
        if line_cost is None:
            # Counted, named, and reported -- NOT treated as zero silently. The
            # figure is knowingly overstated by this line's cost, and the reply
            # says by how many units and which products.
            missing[sku or asin or "(no sku)"] = \
                missing.get(sku or asin or "(no sku)", 0) + qty
        else:
            cogs += line_cost
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


def period_money(config_path, workspace_id, marketplace, start, end, rate,
                 vat_rate=None, asin=None):
    """The window's money on the ORDER calendar, summed. -> a dict.

    THE ONE PLACE A PERIOD'S MONEY IS ADDED UP. The Sales Profit card, the P&L
    and the Finance screen's account figure all come from here, because on 27
    Sep 2026 they were four separate calculations and, for the same seven units
    on jack_uk, reported 64.70, 80.76, 64.43 and 50.19 (CLAUDE.md Rule 12).

    Built from the two shared pieces that already existed:
      order_finance.complete_by_order_date  every order placed in the window --
                                            Amazon's own fees, VAT and coupons
                                            once settled, the account's measured
                                            fee rate until then -- and refunds
                                            on the day the money went back
      sales_data.net_proceeds_for           what was kept out of it
    """
    from domain import order_finance as _of
    from domain import sales_data as _sd

    # ONE PRODUCT, when the screen is filtered to one: the same function cut by
    # product, so a filtered Profit card is that product's figure -- its own
    # orders, its own refunds -- rather than the account's minus that product's
    # ad spend, which is what it read when the filter was ignored here.
    if asin:
        per = _of.complete_by_order_date(config_path, workspace_id, marketplace,
                                         start, end, fee_rate=rate,
                                         vat_rate=vat_rate, group="asin")
        days = {asin: per[asin]} if asin in per else {}
    else:
        days = _of.complete_by_order_date(config_path, workspace_id, marketplace,
                                          start, end, fee_rate=rate,
                                          vat_rate=vat_rate)
    money_keys = ("referral_fees", "fba_fees", "other_fees", "promo_fees",
                  "principal", "tax", "refunds", "refund_tax",
                  "refund_fees_returned", "reimbursements", "promos",
                  "fees_estimated", "revenue_fee_unknown", "charges")
    count_keys = ("refund_units", "orders_settled", "orders_estimated",
                  "orders_fee_unknown", "orders_vat_derived")
    tot = {k: 0.0 for k in money_keys}
    tot.update({k: 0 for k in count_keys})
    cur = ""
    for d in days.values():
        for k in money_keys:
            tot[k] += float(d.get(k) or 0.0)
        for k in count_keys:
            tot[k] += int(d.get(k) or 0)
        cur = cur or d.get("currency") or ""
    tot = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in tot.items()}

    # `tax` is always present here, so net_proceeds_for takes it as the VAT and
    # `principal` as what is left -- complete_by_order_date has already decided,
    # order by order, whether Amazon itemised it or it had to be taken out.
    m = _sd.net_proceeds_for(tot, vat_rate)
    out = dict(tot)
    out.update({
        "currency": cur,
        "revenue": round(tot["principal"] + tot["tax"], 2),   # what buyers paid
        "vat": round(tot["tax"], 2),
        "net_revenue": round(tot["principal"], 2),
        "fees": round(float(m["total_fees"] or 0.0), 2),
        "fees_actual": round(float(m["total_fees"] or 0.0)
                             - tot["fees_estimated"], 2),
        "net_proceeds": (m["net_proceeds"] if m["net_proceeds"] is not None
                         else round(tot["principal"], 2)),
    })

    # WHICH VAT THIS IS. Named with sales_data's four words so every screen
    # explains it the same way.
    unsettled = tot["orders_estimated"] + tot["orders_fee_unknown"]
    try:
        r = None if vat_rate in (None, "") else float(vat_rate)
    except (TypeError, ValueError):
        r = None
    if r is None:
        # Nobody has said whether this account is registered. Amazon's own tax
        # lines have been taken out where it sent them; anything it has not
        # settled, or settled without a tax line, cannot be known.
        vb = (_sd.VAT_UNKNOWN if (unsettled or not tot["tax"]) and tot["principal"]
              else _sd.VAT_FROM_AMAZON)
    elif r == 0:
        vb = _sd.VAT_FROM_AMAZON if tot["tax"] else _sd.VAT_NONE
    else:
        vb = (_sd.VAT_DERIVED if (unsettled or tot["orders_vat_derived"])
              else _sd.VAT_FROM_AMAZON)
    out["vat_basis"] = vb
    return out


def for_period(config_path, workspace_id, marketplace, start, end,
               overrides=None, vat_rate=None, ads_connected=False,
               ad_spend=0.0, revenue=None, units=None, asin=None):
    """Profit on orders PLACED between two dates, from the seller's own costs.

    Returns the figure, how the fee rate was arrived at, and what it does not
    cover -- so the screen can state all three rather than showing a number and
    hoping.

    THE HEADLINE PROFIT, and the P&L and the Finance screen report this same
    figure (see period_money). What goes into it:

        sales after VAT            at the account's VAT setting
      - Amazon's fees              settled where Amazon has settled, the
                                   account's measured rate where it has not
      - coupons you funded
      - refunds                    on the day the money went back
      + fees returned on refunds, + reimbursements
      - stock cost                 frozen onto each order; an uncosted unit is
                                   counted as nothing and the figure SAYS so
      - your per-product charges   (asin_charges)
      - advertising                every pound measured, once it is connected

    `revenue` and `units` are what the screen's own cards show. They are no
    longer used to recompute the figure: the money now comes from the same
    order rows the cards are built from. If they ever disagree, the reply says
    so instead of quietly re-basing the fees on a different set of trade.

    `asin` narrows everything to one product, for a screen filtered to it --
    and then `ad_spend` must be that product's spend, which is what the Sales
    screen passes.
    """
    lines = lines_between(config_path, workspace_id, marketplace, start, end)
    if asin:
        lines = [L for L in lines if str(L.get("asin") or "") == str(asin)]
    rate, basis, detail = fee_rate(config_path, workspace_id, marketplace, end)

    def _charge_of(asin, sku, on_date):
        from domain import asin_charges as _ac
        return _ac.per_unit(config_path, workspace_id, marketplace, asin,
                            sku=sku, on_date=on_date)

    # The LINES answer what only they know: what the stock cost, which units
    # have no cost, the owner's own per-product charges, goods versus postage.
    # Their money arithmetic is not used -- period_money owns that.
    out = for_lines(lines, rate if rate is not None else 0.0,
                    vat_rate=vat_rate, charge_of=_charge_of)
    lines_revenue = out["revenue"]     # what the order rows say buyers paid
    money = period_money(config_path, workspace_id, marketplace, start, end,
                         rate, vat_rate, asin=asin)

    ads = (round(float(ad_spend or 0), 2) if ads_connected else None)
    # The per-unit charges come from period_money, the same figure the Sales
    # grid and the Finance rows subtract (order_finance works them out once).
    out["charges"] = money["charges"]
    profit = round(money["net_proceeds"] - out["cogs"] - money["charges"]
                   - (ads or 0.0), 2)
    net_rev = money["net_revenue"]
    out.update({
        "profit": profit,
        # PROFIT OVER SALES AFTER VAT, on every screen.
        "margin_pct": round(profit / net_rev * 100, 1) if net_rev else None,
        "revenue": money["revenue"],
        "vat": (None if money["vat_basis"] == "unknown" and not money["vat"]
                else money["vat"]),
        "vat_basis": money["vat_basis"],
        "net_revenue": net_rev,
        "fees": money["fees"],
        "fees_actual": money["fees_actual"],
        "fees_estimated": money["fees_estimated"],
        "promo_fees": money["promo_fees"],
        "promos": money["promos"],
        "refunds": money["refunds"],
        "refund_units": money["refund_units"],
        "refund_fees_returned": money["refund_fees_returned"],
        "reimbursements": money["reimbursements"],
        "net_proceeds": money["net_proceeds"],
        "orders_settled": money["orders_settled"],
        "orders_estimated": money["orders_estimated"],
        "orders_fee_unknown": money["orders_fee_unknown"],
        "revenue_fee_unknown": money["revenue_fee_unknown"],
        "currency": money["currency"],
    })

    # THE CARD'S OWN REVENUE, compared rather than substituted -- against what
    # the ORDER ROWS say buyers paid, which is what the card is built from
    # (live_reconcile.from_lines). Not against Amazon's settled principal plus
    # tax: that legitimately differs on fully refunded and cross-border orders
    # (sales_data.series says so), and comparing with it would leave a "press
    # Sync" note that never goes away. A difference here means the two stores
    # have drifted, which must be visible -- it is how "Total Sales 1,248,
    # Profit 1,728" happened.
    try:
        if (revenue is not None and not asin
                and abs(float(revenue) - float(lines_revenue)) > 0.01):
            out["revenue_note"] = (
                "The orders behind this profit come to %.2f, and the sales "
                "figure on screen is %.2f. They are built from the same orders, "
                "so the gap means one of them has not caught up yet -- press "
                "Sync." % (float(lines_revenue), float(revenue)))
    except (TypeError, ValueError):
        pass

    notes = []
    if out.get("warning"):
        notes.append(out["warning"])
    if money["orders_fee_unknown"]:
        notes.append(
            "%d order(s) worth %.2f have NO fee in this figure: the account has "
            "no measured fee rate yet, so the fee was left out rather than "
            "guessed. Profit is higher than the truth by whatever Amazon "
            "charges." % (money["orders_fee_unknown"],
                          money["revenue_fee_unknown"]))
    if money["vat_basis"] == "unknown":
        notes.append(
            "No VAT rate is set for this account, so VAT has only been taken "
            "out where Amazon itemised it. If the account is VAT-registered, "
            "this profit is too high. Set the rate on the account.")
    if out.get("revenue_note"):
        notes.append(out["revenue_note"])
    # A PER-PRODUCT CHARGE THAT LOOKS LIKE ADVERTISING, beside measured ad
    # spend. asin_charges was where a hand-allocated ad figure went while the
    # Ads API was not connected; once it is, both come off and the same money
    # is subtracted twice. Not decided here -- the label is the owner's own
    # words -- only said, so he can remove whichever one he no longer wants.
    if ads_connected and ads:
        _adlike = [p["label"] for p in (out.get("charge_parts") or [])
                   if any(w in str(p.get("label") or "").lower()
                          for w in ("advert", "ppc", "sponsored", " ads", "ads "))
                   or str(p.get("label") or "").strip().lower() in ("ad", "ads")]
        if _adlike:
            notes.append(
                "Your per-product charges include %s, which looks like an "
                "advertising allowance -- and the advertising Amazon measured is "
                "also taken off. If both are the same money, remove the "
                "allowance on the product so it is not counted twice."
                % ", ".join('"%s"' % x for x in _adlike[:3]))
    out["notes"] = notes

    # AD SPEND ONLY WHEN IT IS KNOWN. Asked for: build it the way Orbit does --
    # subtracted once the Advertising API is connected, and nothing subtracted
    # at all while it is not. A guessed ad figure would move profit more than
    # anything else on this screen.
    out["ads_connected"] = bool(ads_connected)
    out["ad_spend"] = ads

    out.update({
        "rate": rate, "rate_basis": basis, "rate_detail": detail,
        "start": start, "end": end, "basis": "order",
        "vat_rate": vat_rate,
        "note": ("Worked out from your own cost prices, because Amazon reports "
                 "no profit against an order until it settles. Fees: Amazon's "
                 "own where it has settled the order, otherwise " + detail
                 + ". Refunds are counted on the day the money went back."
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
        "       cogs_source, currency, status, purchase_date, title "
        "FROM order_lines "
        "WHERE workspace_id=? AND marketplace=? "
        "  AND substr(purchase_date, 1, 10) >= ? "
        "  AND substr(purchase_date, 1, 10) <= ? ",
        (workspace_id, marketplace, str(start), str(end))).fetchall()
    # Cancelled orders are not sales and must not carry a profit either.
    dead = ("canceled", "cancelled")
    return [dict(r) for r in rows
            if str(r["status"] or "").lower() not in dead]
