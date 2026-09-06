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
    # THE PRICE OF A PROMOTION, on its own line. Coupon redemptions and deal
    # fees used to sit inside "other" beside the monthly subscription, where
    # they could not be told apart -- and they are the only charge in that
    # bucket that is the price of a CHOICE, so they are the one worth seeing.
    ("promo_fees", "Coupon and deal fees", -1),
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


def _vat_for_window(conn, workspace_id, marketplace, start, end, vat_rate,
                    gross):
    """(vat, basis) for the whole window. Amazon's own figures where it sent them.

    AMAZON'S TAX COLUMN IS PREFERRED OVER ANY RATE, and `is not None` is the
    test rather than truthiness: a stored 0.00 means "we read Amazon's tax lines
    and they came to zero", while NULL means "this row predates us capturing tax
    at all". Treating a real zero as absent would fall through to the rate and
    subtract VAT from a figure that is already net of it.
    """
    from domain import sales_data as _sd

    row = conn.execute(
        "SELECT SUM(f.tax) t, COUNT(f.tax) n FROM order_lines o "
        "JOIN order_fees f ON f.workspace_id=o.workspace_id "
        "  AND f.marketplace=o.marketplace AND f.order_id=o.order_id "
        "WHERE o.workspace_id=? AND o.marketplace=? "
        "AND substr(o.purchase_date,1,10)>=? AND substr(o.purchase_date,1,10)<=?",
        (workspace_id, marketplace, start, end)).fetchone()
    if row and (row["n"] or 0):
        return round(float(row["t"] or 0), 2), _sd.VAT_FROM_AMAZON

    # Nothing settled yet, so fall back to the account's rate -- and say so.
    if vat_rate in (None, ""):
        return None, _sd.VAT_UNKNOWN
    try:
        r = float(vat_rate)
    except (TypeError, ValueError):
        return None, _sd.VAT_UNKNOWN
    if r == 0:
        return 0.0, _sd.VAT_NONE
    if r <= 0 or r >= 1:
        return None, _sd.VAT_UNKNOWN
    # The sales figure INCLUDES the VAT, so the tax in it is gross x r/(1+r),
    # not gross x r. Multiplying by the rate is the classic way to take out a
    # fifth too much -- the same formula sales_data.vat_for uses (Rule 12).
    return round(float(gross) * r / (1.0 + r), 2), _sd.VAT_DERIVED


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
        "       SUM(f.other_fees) oth, SUM(f.promo_fees) promo, "
        "       COUNT(f.promo_fees) promo_n "
        "FROM order_lines o "
        "JOIN order_fees f ON f.workspace_id=o.workspace_id "
        "  AND f.marketplace=o.marketplace AND f.order_id=o.order_id "
        "WHERE o.workspace_id=? AND o.marketplace=? "
        "AND substr(o.purchase_date,1,10)>=? AND substr(o.purchase_date,1,10)<=? "
        "GROUP BY o.order_id",
        (workspace_id, marketplace, start, end)).fetchall()
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

    # ---- the costs Amazon knows nothing about ----------------------------
    #
    # The accountant, the software, the packaging -- and the monthly selling
    # subscription, which Amazon charges against the ACCOUNT rather than any
    # order, so every order-joined query above is blind to it by construction.
    # domain/expenses.py owns the apportioning: a monthly amount contributes
    # only the days of it that fall in this window.
    from domain import expenses as _exp
    try:
        man = _exp.for_window(config_path, workspace_id, marketplace, start, end)
    except Exception:
        man = {"total": 0.0, "count": 0, "recorded": 0, "items": []}
    manual = round(float(man.get("total") or 0), 2)

    # promo_fees is INSIDE other_fees on rows the newer sync has not touched, so
    # adding both would double count. It is added only once it is separated.
    fees_total = round(actual["referral_fees"] + actual["fba_fees"]
                       + actual["other_fees"]
                       + (actual["promo_fees"]
                          if actual.get("_promo_separated") else 0.0)
                       + estimated_fees - fees_back, 2)
    net_sales = round(sales - refunds, 2)
    profit = round(net_sales - cogs - fees_total + reimb - ad_spend - manual, 2)

    # A category Amazon has itemised nothing for is UNKNOWN, not zero -- see
    # _FEE_LINES. Where it HAS itemised some of the window, the figure is real
    # and is shown, with `basis` saying it covers only part of the period.
    any_actual = any(actual[k] for k in _FEE_LINES)
    cat = {k: (actual[k] if any_actual else None) for k in _FEE_LINES}
    for k in _FEE_LINES:
        out["basis"][k] = ("actual" if (any_actual and not unsettled_rev)
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

    # ---- VAT: BOTH WAYS, AND NEVER SUBTRACTED BEHIND YOUR BACK -----------
    #
    # VAT is collected on the buyer's behalf and never earned, so a VAT-
    # registered seller's real revenue is lower than the sales line above. But
    # whether an account IS registered is not something this app can measure,
    # and quietly subtracting a fifth of the revenue from somebody who is not
    # would be as wrong as leaving it in for somebody who is.
    #
    # Measured on this database: nestwell_goods and selvora_limited are both
    # configured vat_rate=0. If either is actually registered, the profit above
    # is overstated by roughly a fifth. That is exactly the sort of thing that
    # has to be SHOWN rather than decided.
    #
    # So the statement carries both figures and says which basis produced them.
    # `profit` stays on the gross basis -- the number that was there before --
    # and `profit_ex_vat` sits beside it.
    vat_amount, vat_basis = _vat_for_window(conn, workspace_id, marketplace,
                                            start, end, vat_rate, sales)
    out["vat"] = {
        "amount": vat_amount,
        "basis": vat_basis,
        "rate": vat_rate,
        # Gross is what Amazon reports and what the lines above use.
        "sales_gross": sales,
        "sales_ex_vat": (round(sales - vat_amount, 2)
                         if vat_amount is not None else None),
        "profit_ex_vat": (round(profit - vat_amount, 2)
                          if vat_amount is not None else None),
        "explain": _VAT_EXPLAIN.get(vat_basis, ""),
    }

    out.update({
        "ordered_sales": sales,
        "refunds": refunds,
        "refund_units": int((ref["u"] if ref else 0) or 0),
        "refund_fees_returned": fees_back,
        "net_sales": net_sales,
        "cogs": cogs,
        "referral_fees": cat["referral_fees"],
        "fba_fees": cat["fba_fees"],
        "promo_fees": cat["promo_fees"],
        "other_fees": cat["other_fees"],
        "fees_total": fees_total,
        "reimbursements": reimb,
        "ad_spend": ad_spend if ads_connected else None,
        # RECORDED NONE AND SPENT NONE ARE DIFFERENT. An account where nobody
        # has entered a single cost reports None, so the line reads "not
        # recorded" rather than a confident 0.00 that says this business has no
        # overheads. Once anything is recorded, 0.00 for a window it does not
        # reach is a real measurement and is shown as one.
        "manual_expenses": (manual if man.get("recorded") else None),
        "manual_expense_detail": man,
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
    if unattributed > 0 and out.get("suggested_expense"):
        out["notes"].append(
            "%s%.2f of Amazon's charges in this window belong to the account "
            "rather than to any order -- the monthly selling subscription is "
            "the usual one. It is NOT in the profit above, because no per-order "
            "query can see it. Add it as a monthly cost and it will be."
            % ((out.get("currency") + " ") if out.get("currency") else "",
               unattributed))
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
    # VAT IS SHOWN, NEVER SILENTLY TAKEN OUT. The headline profit above is on
    # the gross basis; profit_ex_vat sits beside it, and this says which is
    # which so nobody has to guess which one they are reading.
    v = out.get("vat") or {}
    if v.get("basis") in ("unknown", "none"):
        out["notes"].append(v.get("explain") or "")
    elif v.get("amount"):
        out["notes"].append(
            "The profit above INCLUDES VAT of %s%.2f, because VAT is collected "
            "for HMRC rather than earned. Profit net of it is %s%.2f. Nothing "
            "was subtracted automatically -- both figures are here so you can "
            "use the one that applies. %s"
            % ((out.get("currency") + " ") if out.get("currency") else "",
               v["amount"],
               (out.get("currency") + " ") if out.get("currency") else "",
               v.get("profit_ex_vat") or 0.0, v.get("explain") or ""))
    return out
