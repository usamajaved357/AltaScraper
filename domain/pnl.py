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

NOTHING IS INVENTED. A figure that cannot be known is None and says why. A zero
is a claim that something was zero, and is only ever written when Amazon said so.
"""
import datetime as _dt

from data import db as _db

# What each line is, in the order a P&L reads. `sign` is how it moves profit.
LINES = (
    ("ordered_sales", "Sales", +1),
    ("refunds", "Refunds", -1),
    ("net_sales", "Net sales", 0),
    ("cogs", "Cost of goods", -1),
    ("referral_fees", "Amazon referral fees", -1),
    ("fba_fees", "FBA fees", -1),
    ("other_fees", "Other Amazon fees", -1),
    ("fees_estimated", "Fees not yet itemised", -1),
    ("reimbursements", "Reimbursements", +1),
    ("ad_spend", "Advertising", -1),
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
_FEE_LINES = ("referral_fees", "fba_fees", "other_fees")


def _f(v):
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def fee_coverage(config_path, workspace_id, marketplace, start, end):
    """How much of this window Amazon has actually settled. -> a dict.

    The number that decides whether the fees below are measured or estimated,
    and the one a reader needs before trusting either.
    """
    conn = _db.get_db(config_path)
    placed = conn.execute(
        "SELECT COUNT(DISTINCT order_id) FROM order_lines WHERE workspace_id=? "
        "AND marketplace=? AND substr(purchase_date,1,10)>=? "
        "AND substr(purchase_date,1,10)<=?",
        (workspace_id, marketplace, start, end)).fetchone()[0] or 0
    settled = conn.execute(
        "SELECT COUNT(DISTINCT o.order_id) FROM order_lines o "
        "JOIN order_fees f ON f.workspace_id=o.workspace_id "
        "  AND f.marketplace=o.marketplace AND f.order_id=o.order_id "
        "WHERE o.workspace_id=? AND o.marketplace=? "
        "AND substr(o.purchase_date,1,10)>=? AND substr(o.purchase_date,1,10)<=?",
        (workspace_id, marketplace, start, end)).fetchone()[0] or 0
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
        "SELECT o.order_id, SUM(f.referral_fees) ref, SUM(f.fba_fees) fba, "
        "       SUM(f.other_fees) oth "
        "FROM order_lines o "
        "JOIN order_fees f ON f.workspace_id=o.workspace_id "
        "  AND f.marketplace=o.marketplace AND f.order_id=o.order_id "
        "WHERE o.workspace_id=? AND o.marketplace=? "
        "AND substr(o.purchase_date,1,10)>=? AND substr(o.purchase_date,1,10)<=? "
        "GROUP BY o.order_id",
        (workspace_id, marketplace, start, end)).fetchall()
    tot = {"referral_fees": 0.0, "fba_fees": 0.0, "other_fees": 0.0}
    ids = set()
    for r in rows:
        ids.add(str(r["order_id"]))
        tot["referral_fees"] += _f(r["ref"])
        tot["fba_fees"] += _f(r["fba"])
        tot["other_fees"] += _f(r["oth"])
    return {k: round(v, 2) for k, v in tot.items()}, ids


def build(config_path, workspace_id, marketplace, start, end, vat_rate=None):
    """The whole statement. Never raises; unknown lines are None with a reason."""
    from domain import order_profit as _op
    from domain import sales_data as _sd

    conn = _db.get_db(config_path)
    out = {"ok": True, "workspace": workspace_id, "marketplace": marketplace,
           "start": start, "end": end, "notes": [], "basis": {}}

    # ---- what was sold, on the ORDER calendar -----------------------------
    tot = _sd.totals(config_path, workspace_id, marketplace, start, end,
                     None, vat_rate)
    sales = _f(tot.get("ordered_sales"))
    out["currency"] = tot.get("currency") or ""

    # ---- fees: actuals where settled, the account's own rate where not ----
    cov = fee_coverage(config_path, workspace_id, marketplace, start, end)
    actual, settled_ids = _settled_fees(conn, workspace_id, marketplace,
                                        start, end)

    # The revenue that has NOT settled, so the rate is applied only to that.
    unsettled_rev = 0.0
    for r in conn.execute(
            "SELECT order_id, SUM(COALESCE(revenue,0)) rev FROM order_lines "
            "WHERE workspace_id=? AND marketplace=? "
            "AND substr(purchase_date,1,10)>=? AND substr(purchase_date,1,10)<=? "
            "GROUP BY order_id",
            (workspace_id, marketplace, start, end)):
        if str(r["order_id"]) not in settled_ids:
            unsettled_rev += _f(r["rev"])
    unsettled_rev = round(unsettled_rev, 2)

    rate, rate_basis, rate_detail = _op.fee_rate(config_path, workspace_id,
                                                 marketplace, end)
    estimated_fees = round(unsettled_rev * float(rate or 0), 2)

    out["fee_coverage"] = cov
    out["fee_rate"] = rate
    out["fee_rate_basis"] = rate_basis
    out["fee_rate_detail"] = rate_detail
    out["fees_actual"] = actual
    out["fees_estimated"] = estimated_fees
    out["unsettled_revenue"] = unsettled_rev
    # The estimate cannot be split by kind -- it is one rate over the revenue
    # Amazon has not itemised yet. Said, rather than divided up plausibly.

    # ---- refunds: their OWN date, never re-dated --------------------------
    ref = conn.execute(
        "SELECT ROUND(SUM(COALESCE(refunds,0)),2) r, "
        "       SUM(COALESCE(refund_units,0)) u, "
        "       ROUND(SUM(COALESCE(refund_fees_returned,0)),2) back, "
        "       ROUND(SUM(COALESCE(reimbursements,0)),2) reimb "
        "FROM finance_daily WHERE workspace_id=? AND marketplace=? "
        "AND asin='*' AND date>=? AND date<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    refunds = _f(ref["r"]) if ref else 0.0
    fees_back = _f(ref["back"]) if ref else 0.0
    reimb = _f(ref["reimb"]) if ref else 0.0

    # ---- cost of goods, frozen onto the orders ---------------------------
    cg = conn.execute(
        "SELECT ROUND(SUM(COALESCE(cogs,0) * COALESCE(units,1)),2) c, "
        "       SUM(CASE WHEN cogs IS NULL THEN COALESCE(units,1) ELSE 0 END) missing, "
        "       SUM(COALESCE(units,1)) units "
        "FROM order_lines WHERE workspace_id=? AND marketplace=? "
        "AND substr(purchase_date,1,10)>=? AND substr(purchase_date,1,10)<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    cogs = _f(cg["c"]) if cg else 0.0
    missing_units = int((cg["missing"] if cg else 0) or 0)
    total_units = int((cg["units"] if cg else 0) or 0)

    # ---- advertising ------------------------------------------------------
    ad = conn.execute(
        "SELECT ROUND(SUM(COALESCE(spend,0)),2) s FROM ads_daily "
        "WHERE workspace_id=? AND marketplace=? AND asin='*' "
        "AND date>=? AND date<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    ad_spend = _f(ad["s"]) if ad else 0.0
    ads_connected = bool(ad and ad["s"] is not None)

    fees_total = round(actual["referral_fees"] + actual["fba_fees"]
                       + actual["other_fees"] + estimated_fees - fees_back, 2)
    net_sales = round(sales - refunds, 2)
    profit = round(net_sales - cogs - fees_total + reimb - ad_spend, 2)

    # A category Amazon has itemised nothing for is UNKNOWN, not zero -- see
    # _FEE_LINES. Where it HAS itemised some of the window, the figure is real
    # and is shown, with `basis` saying it covers only part of the period.
    any_actual = any(actual[k] for k in _FEE_LINES)
    cat = {k: (actual[k] if any_actual else None) for k in _FEE_LINES}
    for k in _FEE_LINES:
        out["basis"][k] = ("actual" if (any_actual and not unsettled_rev)
                           else ("part-actual" if any_actual else "not itemised"))
    out["basis"]["fees_estimated"] = "estimated at the account's measured rate"

    out.update({
        "ordered_sales": sales,
        "refunds": refunds,
        "refund_units": int((ref["u"] if ref else 0) or 0),
        "refund_fees_returned": fees_back,
        "net_sales": net_sales,
        "cogs": cogs,
        "referral_fees": cat["referral_fees"],
        "fba_fees": cat["fba_fees"],
        "other_fees": cat["other_fees"],
        "fees_total": fees_total,
        "reimbursements": reimb,
        "ad_spend": ad_spend if ads_connected else None,
        "manual_expenses": None,
        "profit": profit,
        "margin_pct": (round(profit / net_sales * 100, 1) if net_sales else None),
        "units": total_units,
        "uncosted_units": missing_units,
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
    if unattributed > 0:
        out["notes"].append(
            "%s%.2f of Amazon's charges in this window belong to the account "
            "rather than to any order -- the monthly selling subscription is "
            "the usual one. It is NOT in the profit above, because it cannot "
            "be attached to a sale. Treat it as a fixed monthly cost."
            % ((out.get("currency") + " ") if out.get("currency") else "",
               unattributed))
    if not ads_connected:
        out["notes"].append(
            "No advertising data for this window, so nothing was subtracted for "
            "it. That is not the same as having spent nothing.")
    out["notes"].append(
        "Sales already include the postage buyers paid, so there is no separate "
        "shipping-credits line -- adding one would count it twice.")
    return out
