"""domain/pnl.py -- the account's profit and loss, line by line, on one calendar.

WHAT THIS ADDS TO domain/order_profit.py
order_profit answers "what did the orders placed in this window earn", as one
number with a note. This breaks the same period into the LINES a P&L has, so the
question stops being "is 424.01 right" and becomes "where did the money go".

THE FEE RULE: ACTUALS WHERE THEY EXIST, ESTIMATE WHERE THEY DO NOT, LABELLED.

Amazon reports a fee only once an order SETTLES, which lags roughly a fortnight
plus the payout cycle. Measured on this database: 9 of 51 orders placed in the
last thirty days have a settled fee row -- 18%. So "use actuals for everything"
is not a choice that can be made:

    actuals only     82% of the period reports NO fees at all, and profit
                     comes out far too high -- the opposite of the intent
    estimate only    throws away the exact figures Amazon has already sent for
                     the settled fifth, in favour of a rate derived from them

So each order uses its own settled fees where Amazon has sent them, and the
account's measured rate where it has not. Every reply says how much of the
period is which, because a P&L whose fees are four-fifths estimated is a
different document from one that is not, and the reader has to know which they
are holding.

THE RATE IS NOT 15%. It is measured from this account's own settled history --
18.01% on nestwell_goods, because Amazon charges VAT on its own fees here.
domain/order_profit.fee_rate owns that measurement and it is asked, not redone.

REFUNDS SIT ON THE DAY THE MONEY MOVED, NOT THE DAY OF THE ORDER.

    "REFUNDS stay on the refund event date -- NOT re-dated to the original
     order. July's profit stays locked. September's refund hits September's
     P&L."

That is the owner's decision and it is the simpler of the two, with a real
property: a month already read and acted on does not change afterwards. The cost
is that a refund appears in a month whose sale is in another, and the reply says
so rather than leaving it to be inferred.

SHIPPING IS ALREADY IN THE SALES FIGURE, AND IS NOT ADDED AGAIN.
domain/live_reconcile.figures_by_day takes include_shipping=True and its own
docstring says ordered_sales is "what the buyer paid for the goods plus the
postage they paid to have them sent". Adding a shipping-credits line on top of
that would count the postage twice -- which has happened before and was
measured: a card read 114.00 against a true 102.21, over by exactly the 12.24 of
postage. The split is reported instead, so the line can be SEEN without being
added.

VAT COMES OUT, AT THE ACCOUNT'S SETTING.
It used to stay in the profit, shown beside it and never subtracted. On 28 Sep
2026 the owner decided every profit figure follows the VAT rate set on the
account, so this statement now agrees with the Sales card to the penny.

NOTHING IS INVENTED. A figure that cannot be known is None and says why. A zero
is a claim that something was zero, and is only ever written when Amazon said so.
"""
import datetime as _dt

from data import db as _db

# What each line is, in the order a P&L reads. `sign` is how it moves profit.
LINES = (
    ("ordered_sales", "Sales", +1),
    # VAT OUT, at the account's own setting -- the owner's decision of 28 Sep
    # 2026. It used to be left in the profit and only shown beside it.
    ("vat_line", "VAT", -1),
    ("refunds", "Refunds", -1),
    ("net_sales", "Net sales", 0),
    ("cogs", "Cost of goods", -1),
    ("referral_fees", "Amazon referral fees", -1),
    ("fba_fees", "FBA fees", -1),
    # THE PRICE OF A PROMOTION, on its own line. Coupon redemptions and deal
    # fees used to sit inside "other" beside the monthly subscription, where
    # they could not be told apart -- and they are the only charge in that
    # bucket that is the price of a CHOICE, so they are the one worth seeing.
    ("promo_fees", "Coupon and deal fees", -1),
    ("other_fees", "Other Amazon fees", -1),
    ("fees_estimated", "Fees not yet itemised", -1),
    # COUPONS AND DEALS YOU FUNDED -- the discount itself, not Amazon's fee for
    # running it (that is promo_fees above). Amazon sends the full price and the
    # discount separately, so leaving this out counted the discount as money
    # kept. The Sales card always subtracted it; the statement did not.
    ("promos", "Coupons and deals you funded", -1),
    ("refund_fees_returned", "Fees returned on refunds", +1),
    ("reimbursements", "Reimbursements", +1),
    ("charges", "Your per-product charges", -1),
    ("ad_spend", "Advertising", -1),
    # THE SALES CARD'S FIGURE. Everything above is the same calculation the card
    # makes (domain/order_profit.for_period); only the line below is the
    # statement's own.
    ("profit_before_own_costs", "Profit before your own costs", 0),
    # What Amazon charged the ACCOUNT and no order carries -- the monthly
    # selling subscription. Measured, so it comes off; not when it is already
    # recorded as one of your own costs below (expenses.overhead_for).
    ("account_charges", "Amazon charges on the account", -1),
    # Every other Amazon posting, signed (postage labels, Vine, retrocharges ...).
    ("other_amazon", "Other Amazon transactions", +1),
    ("manual_expenses", "Your own costs", -1),
    ("profit", "Net profit", 0),
)

# A LINE WITH NO ACTUALS BEHIND IT IS UNKNOWN, NOT ZERO.
#
# When Amazon has itemised nothing for a window, the three fee categories have
# no measured value -- and printing "Amazon referral fees 0.00" beside 233.22 of
# estimated fees says something false twice over: that no referral fee was
# charged, and that the estimate belongs to no category. The estimate is ONE
# rate over the revenue Amazon has not broken down, so it cannot honestly be
# divided between them. It gets its own line and the categories report None.
_FEE_LINES = ("referral_fees", "fba_fees", "promo_fees", "other_fees")


def _f(v):
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# What each VAT basis means, in the words the screen shows. domain/sales_data
# owns the four names; this owns only how to explain them on a P&L (Rule 12).
_VAT_EXPLAIN = {
    "amazon": ("Amazon's own VAT figures for this window, summed from the "
               "settled orders. This is the reliable one."),
    "derived": ("Worked out from the VAT rate set on this account, because "
                "Amazon did not send tax figures for these orders. It assumes "
                "every sale carried that rate."),
    "none": ("This account is set as not VAT-registered, so nothing is taken "
             "out. If that is wrong, the profit above is overstated by roughly "
             "the VAT rate."),
    "unknown": ("No VAT rate is set for this account and Amazon sent no tax "
                "figures, so VAT cannot be worked out. If this account IS "
                "registered, the profit above is overstated — a fifth of it at "
                "a 20% rate."),
}


# The orders PLACED in a window that are real sales. DISTINCT, because an order
# with three products has three order_lines rows and joining fees to it row by
# row counted its fees three times; and cancelled orders are not sales, the
# same rule every other order-calendar figure applies
# (order_finance.complete_by_order_date).
_PLACED = ("SELECT DISTINCT order_id FROM order_lines WHERE workspace_id=? "
           "AND marketplace=? AND lower(COALESCE(status,'')) NOT IN "
           "('canceled','cancelled') AND substr(purchase_date,1,10)>=? "
           "AND substr(purchase_date,1,10)<=?")


def fee_coverage(config_path, workspace_id, marketplace, start, end):
    """How much of this window Amazon has actually settled. -> a dict.

    The number that decides whether the fees below are measured or estimated,
    and the one a reader needs before trusting either.
    """
    conn = _db.get_db(config_path)
    args = (workspace_id, marketplace, start, end)
    placed = conn.execute("SELECT COUNT(*) FROM (%s)" % _PLACED,
                          args).fetchone()[0] or 0
    # A refund posting is an order_fees row too; only a SALE settling counts.
    settled = conn.execute(
        "SELECT COUNT(DISTINCT f.order_id) FROM order_fees f "
        "WHERE f.workspace_id=? AND f.marketplace=? AND f.order_id IN (%s) "
        "AND (COALESCE(f.principal,0)<>0 OR COALESCE(f.referral_fees,0)<>0 "
        "  OR COALESCE(f.fba_fees,0)<>0 OR COALESCE(f.other_fees,0)<>0 "
        "  OR COALESCE(f.promo_fees,0)<>0 OR COALESCE(f.tax,0)<>0)" % _PLACED,
        (workspace_id, marketplace) + args).fetchone()[0] or 0
    pct = round(100.0 * settled / placed, 1) if placed else None
    return {"orders": placed, "settled": settled, "pct_settled": pct,
            "estimated": placed - settled}


def _settled_fees(conn, workspace_id, marketplace, start, end):
    """Amazon's own fees for orders PLACED in this window. -> (dict, set).

    Joined back to the order's PLACED date, not the date the money moved: these
    are the fees belonging to this window's trade, and a fee is not a refund --
    it is part of the sale it came from. The refunds below are the ones that
    deliberately sit on their own date instead.
    """
    rows = conn.execute(
        "SELECT f.order_id, SUM(f.referral_fees) ref, SUM(f.fba_fees) fba, "
        "       SUM(f.other_fees) oth, SUM(f.promo_fees) promo, "
        "       COUNT(f.promo_fees) promo_n "
        "FROM order_fees f "
        "WHERE f.workspace_id=? AND f.marketplace=? AND f.order_id IN (%s) "
        "GROUP BY f.order_id" % _PLACED,
        (workspace_id, marketplace, workspace_id, marketplace, start, end)
    ).fetchall()
    tot = {"referral_fees": 0.0, "fba_fees": 0.0, "other_fees": 0.0,
           "promo_fees": 0.0}
    ids = set()
    # ROWS STORED BEFORE promo_fees EXISTED HAVE THEIR COUPON FEES INSIDE
    # other_fees, and their column is NULL. Counting them as 0.00 would claim
    # the coupon fees were measured at nothing when they were never separated.
    # `separated` says whether ANY row in the window has been through the newer
    # sync, and the caller reports the line as unknown when none has.
    separated = False
    for r in rows:
        ids.add(str(r["order_id"]))
        tot["referral_fees"] += _f(r["ref"])
        tot["fba_fees"] += _f(r["fba"])
        tot["other_fees"] += _f(r["oth"])
        tot["promo_fees"] += _f(r["promo"])
        if (r["promo_n"] or 0):
            separated = True
    out = {k: round(v, 2) for k, v in tot.items()}
    out["_promo_separated"] = separated
    return out, ids


def build(config_path, workspace_id, marketplace, start, end, vat_rate=None):
    """The whole statement. Never raises; unknown lines are None with a reason.

    THE SAME PROFIT AS THE SALES CARD, broken into lines. Every figure down to
    "Profit before your own costs" comes from domain/order_profit.for_period,
    which the card itself shows -- so the two cannot disagree (CLAUDE.md Rule
    12). Measured 27 Sep 2026 on jack_uk for the same month: card 64.70,
    statement 80.76. The statement had its own sales figure (from a different
    table than its costs), left VAT in, ignored coupons you funded, and counted
    a multi-product order's fees once per product.

    Only the last step is the statement's own: the costs Amazon never sees.
    """
    from domain import order_profit as _op
    from domain import expenses as _exp

    conn = _db.get_db(config_path)
    out = {"ok": True, "workspace": workspace_id, "marketplace": marketplace,
           "start": start, "end": end, "notes": [], "basis": {}}

    # ---- advertising, as it COST the account --------------------------------
    # The one rule (domain/ad_cost): the Ads API where it covers the window,
    # else Amazon's ad invoices; plus the VAT on ads for an account that cannot
    # reclaim it (owner, 30 Sep 2026).
    from domain import ad_cost as _adc
    _ad = _adc.for_window(config_path, workspace_id, marketplace, start, end,
                          vat_registered=bool(vat_rate and float(vat_rate) > 0))
    ads_connected = _ad["cost"] is not None
    ad_spend = _f(_ad["cost"]) if ads_connected else 0.0
    out["ads_source"] = _ad["source"]
    out["ads_vat_added"] = _ad["vat_added"]
    if _ad.get("note"):
        out["notes"].append(_ad["note"])

    # ---- everything down to the headline profit: ONE calculation --------
    est = _op.for_period(config_path, workspace_id, marketplace, start, end,
                         vat_rate=vat_rate, ads_connected=ads_connected,
                         ad_spend=ad_spend)
    out["currency"] = est.get("currency") or ""
    rate, rate_detail = est.get("rate"), est.get("rate_detail") or ""

    cov = fee_coverage(config_path, workspace_id, marketplace, start, end)
    actual, _ids = _settled_fees(conn, workspace_id, marketplace, start, end)

    out["fee_coverage"] = cov
    out["fee_rate"] = rate
    out["fee_rate_basis"] = est.get("rate_basis")
    out["fee_rate_detail"] = rate_detail
    out["fees_actual"] = actual
    out["fees_estimated"] = est.get("fees_estimated") or 0.0
    # The revenue Amazon has not itemised yet: the part the estimate is charged
    # on (fees / rate, on the same base the rate was measured on --
    # order_profit.fee_rate) plus the part with no measurable rate at all.
    unsettled_rev = float(est.get("revenue_fee_unknown") or 0.0)
    if rate:
        unsettled_rev += float(out["fees_estimated"]) / float(rate)
    out["unsettled_revenue"] = round(unsettled_rev, 2)

    # ---- the costs Amazon knows nothing about ----------------------------
    #
    # The accountant, the software, the packaging -- and the monthly selling
    # subscription, which Amazon charges against the ACCOUNT rather than any
    # order, so every order-joined query above is blind to it by construction.
    # domain/expenses.py owns the apportioning: a monthly amount contributes
    # only the days of it that fall in this window.
    #
    # AND THE CHARGE AMAZON POSTS AGAINST THE ACCOUNT -- the monthly selling
    # subscription -- which no order carries. expenses.overhead_for owns both,
    # and the Finance screen asks it the same question (Rule 12).
    try:
        ov = _exp.overhead_for(config_path, workspace_id, marketplace, start, end)
    except Exception:
        ov = {"amazon_account_charges": 0.0, "own_costs": 0.0,
              "own_costs_detail": {"total": 0.0, "count": 0, "recorded": 0,
                                   "items": []}}
    man = ov["own_costs_detail"]
    manual = round(float(man.get("total") or 0), 2)
    account_charges = float(ov.get("amazon_account_charges") or 0.0)
    # Every other Amazon posting, signed (+ money in, - a cost; 30 Sep 2026).
    other_amazon = float(ov.get("amazon_other_transactions") or 0.0)

    # A category Amazon has itemised nothing for is UNKNOWN, not zero -- see
    # _FEE_LINES. Where it HAS itemised some of the window, the figure is real
    # and is shown, with `basis` saying it covers only part of the period.
    any_actual = any(actual[k] for k in _FEE_LINES)
    cat = {k: (actual[k] if any_actual else None) for k in _FEE_LINES}
    for k in _FEE_LINES:
        out["basis"][k] = ("actual" if (any_actual and not out["fees_estimated"])
                           else ("part-actual" if any_actual else "not itemised"))

    # COUPON FEES ARE UNKNOWN, NOT NOUGHT, UNTIL THE WINDOW HAS BEEN RE-SYNCED.
    #
    # Rows stored before promo_fees existed keep their coupon and deal fees
    # inside other_fees, and their column is NULL. Reporting 0.00 there would
    # say this account ran no promotions -- which is a claim, and a wrong one on
    # any account that did. The line stays unknown until at least one row in the
    # window has been through the newer sync.
    if not actual.get("_promo_separated"):
        cat["promo_fees"] = None
        out["basis"]["promo_fees"] = "not separated yet"
    out["basis"]["fees_estimated"] = "estimated at the account's measured rate"

    sales = est["revenue"]
    vat_amount = est.get("vat")
    refunds = est.get("refunds") or 0.0
    net_sales = round(sales - float(vat_amount or 0.0) - refunds, 2)
    operating = est["profit"]
    profit = round(operating - account_charges - manual + other_amazon, 2)
    missing_units = int(est.get("missing_units") or 0)
    total_units = int(est.get("units") or 0)

    # ---- VAT: TAKEN OUT AT THE ACCOUNT'S SETTING --------------------------
    #
    # This used to be shown beside the profit and never subtracted, because
    # "whether an account IS registered is not something this app can measure".
    # The account form now asks, and on 28 Sep 2026 the owner decided every
    # profit figure follows that answer (D1, active/plan-profit-accuracy.md).
    # The old side figure was also wrong: it used the tax on SETTLED orders as
    # the tax for the whole window, so on jack_uk it took out 5.83 of 41.31.
    vb = est.get("vat_basis") or ""
    out["vat"] = {
        "amount": vat_amount,
        "basis": vb,
        "rate": vat_rate,
        "sales_gross": sales,
        "sales_ex_vat": est.get("net_revenue"),
        # Kept for anything still reading it: the profit IS now ex VAT.
        "profit_ex_vat": profit,
        "explain": _VAT_EXPLAIN.get(vb, ""),
    }

    out.update({
        "ordered_sales": sales,
        "vat_line": vat_amount,
        "refunds": refunds,
        "refund_units": est.get("refund_units") or 0,
        "refund_fees_returned": est.get("refund_fees_returned") or 0.0,
        "net_sales": net_sales,
        "cogs": est["cogs"],
        "referral_fees": cat["referral_fees"],
        "fba_fees": cat["fba_fees"],
        "promo_fees": cat["promo_fees"],
        "other_fees": cat["other_fees"],
        "fees_total": est.get("fees"),
        "promos": est.get("promos") or 0.0,
        "reimbursements": est.get("reimbursements") or 0.0,
        "charges": est.get("charges") or 0.0,
        "ad_spend": ad_spend if ads_connected else None,
        "profit_before_own_costs": operating,
        "account_charges": round(account_charges, 2),
        "other_amazon": round(other_amazon, 2),
        "account_charge_in_own_costs": bool(ov.get("amazon_charge_in_own_costs")),
        # RECORDED NONE AND SPENT NONE ARE DIFFERENT. An account where nobody
        # has entered a single cost reports None, so the line reads "not
        # recorded" rather than a confident 0.00 that says this business has no
        # overheads. Once anything is recorded, 0.00 for a window it does not
        # reach is a real measurement and is shown as one.
        "manual_expenses": (manual if man.get("recorded") else None),
        "manual_expense_detail": man,
        "profit": profit,
        # Over sales after VAT, the same as every other screen.
        "margin_pct": (round(profit / est["net_revenue"] * 100, 1)
                       if est.get("net_revenue") else None),
        "units": est.get("units") or 0,
        "uncosted_units": est.get("missing_units") or 0,
    })

    # ---- what the reader has to know before trusting any of it -----------
    if cov["pct_settled"] is not None and cov["pct_settled"] < 100:
        out["notes"].append(
            "Amazon has settled %d of %d orders in this window (%.0f%%). Those "
            "carry their real fees; the other %d are charged at %.2f%% -- %s. "
            "The figure tightens on its own as Amazon settles."
            % (cov["settled"], cov["orders"], cov["pct_settled"] or 0,
               cov["estimated"], float(rate or 0) * 100, rate_detail))
    if missing_units:
        out["notes"].append(
            "%d of %d units have no cost recorded, so nothing was subtracted "
            "for them and this profit is HIGHER than the truth."
            % (missing_units, total_units))
    if refunds:
        out["notes"].append(
            "Refunds are counted on the day Amazon moved the money, not the day "
            "of the original order -- so a refund here may belong to a sale in "
            "an earlier period. A month already closed does not change.")

    # FIXED CHARGES BELONG TO NO ORDER, so an order-joined query cannot see
    # them. Measured on nestwell_goods: the fees above come to 1.28 of "other"
    # while the account was actually charged 61.28 -- the missing 60.00 is the
    # monthly selling subscription, which Amazon posts against the account and
    # not against any sale. Excluding it from the per-sale RATE is correct (it
    # does not scale with revenue, and including it once turned a real 17.5%
    # into 24.1% on jack_uk). Excluding it from the PROFIT is not, and it is
    # not yet subtracted anywhere. Said here rather than left to be discovered.
    acct_only = conn.execute(
        "SELECT ROUND(SUM(COALESCE(other_fees,0)),2) o FROM finance_daily "
        "WHERE workspace_id=? AND marketplace=? AND asin='*' "
        "AND date>=? AND date<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    settled_other = _f(acct_only["o"]) if acct_only else 0.0
    unattributed = round(settled_other - actual["other_fees"], 2)
    out["account_level_fees"] = settled_other
    out["unattributed_fees"] = unattributed if unattributed > 0 else 0.0

    # AND IT CAN NOW BE ACTED ON RATHER THAN JUST REPORTED.
    #
    # This note used to end "Treat it as a fixed monthly cost", which asked the
    # reader to hold a number in their head and do something about it elsewhere
    # -- the step nobody takes. expenses.suggest hands back the figure and the
    # wording so the screen can offer a button, and returns None once something
    # matching is recorded, because offering to add a cost that is already being
    # subtracted is how it gets subtracted twice.
    try:
        out["suggested_expense"] = _exp.suggest(config_path, workspace_id,
                                                marketplace, start, end)
    except Exception:
        out["suggested_expense"] = None
    if out["account_charges"]:
        out["notes"].append(
            "%s%.2f of Amazon's charges in this window belong to the account "
            "rather than to any order -- the monthly selling subscription is "
            "the usual one. It is taken off net profit on its own line, because "
            "no per-order figure can carry it."
            % ((out.get("currency") + " ") if out.get("currency") else "",
               out["account_charges"]))
    if man.get("count"):
        out["notes"].append(
            "%d of your own costs fall in this window, coming to %s%.2f. A "
            "monthly amount contributes only the days of it inside the window, "
            "so a fortnight carries half a month's subscription."
            % (man["count"],
               (out.get("currency") + " ") if out.get("currency") else "",
               manual))
    elif not man.get("recorded"):
        out["notes"].append(
            "No costs of your own are recorded, so nothing was subtracted for "
            "the accountant, the software, the packaging or the Amazon monthly "
            "subscription. That is not the same as having none, and this profit "
            "is HIGHER than the truth by whatever they come to.")
    if not ads_connected:
        out["notes"].append(
            "No advertising data for this window, so nothing was subtracted for "
            "it. That is not the same as having spent nothing.")
    out["notes"].append(
        "Sales already include the postage buyers paid, so there is no separate "
        "shipping-credits line -- adding one would count it twice.")
    # VAT IS TAKEN OUT AT THE ACCOUNT'S SETTING, and the statement says how it
    # was worked out -- or, where no rate is set, that it could not be.
    v = out.get("vat") or {}
    if v.get("basis") in ("unknown", "none"):
        out["notes"].append(v.get("explain") or "")
    elif v.get("amount"):
        out["notes"].append(
            "VAT of %s%.2f has been taken out, because it is collected for HMRC "
            "rather than earned. %s"
            % ((out.get("currency") + " ") if out.get("currency") else "",
               v["amount"], v.get("explain") or ""))
    if out.get("charges"):
        out["notes"].append(
            "Your per-product charges (postage out, prep and the like, set on "
            "each product) come to %s%.2f and are subtracted."
            % ((out.get("currency") + " ") if out.get("currency") else "",
               out["charges"]))
    return out
