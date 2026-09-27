"""domain/contribution.py -- what each product actually contributed.

    contribution = charged to buyers
                 - Amazon's fees
                 - refunds
                 + reimbursements
                 - cost of goods
                 - ad spend

The last line is the one that is not there yet. Nothing writes to ads_daily --
there is no Advertising API client and no upload route -- so ad spend is UNKNOWN,
not zero. That distinction is the whole reason this file is careful:

  * subtracting an unknown ad spend as if it were 0.00 would make every
    advertised product look better than it is, by exactly the amount being spent
    on it, and would look completely convincing;
  * so the figure is named "contribution before advertising" everywhere it
    appears, and the ad spend column reports "not connected" rather than a
    confident 0.00.

Rename it the moment ad spend arrives, and not before.

WHY IT DOES NOT DEFINE ITS OWN PROFIT RULE
domain/sales_data.py already decided when a profit figure may be shown at all:
only when EVERY unit in the bucket has a known cost, because uncosted units bring
revenue and no cost and therefore only ever flatter. The same rule applies per
product -- a product with three uncosted units is exactly the product whose
contribution must not be guessed -- so that function is called rather than
repeated (CLAUDE.md Rule 12).

WHICH UNITS, AND WHY IT MATTERS
Everything here is on the MONEY basis: units shipped, from finance_daily, dated
when the money moved. sales_daily counts units ORDERED, dated when the order was
placed. Mixing them produces a contribution per unit that is neither, and the
difference is largest exactly when a period is busy.
"""
from data import db as _db
from domain import sales_data as _sd


def _f(v):
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def by_product(config_path, workspace_id, marketplace, start, end, vat_rate=None):
    """One row per ASIN that had money move in the window, biggest revenue first.

    Returns (rows, totals). Every row carries its own coverage, so a product
    whose contribution is blank can say why without the caller guessing.
    """
    conn = _db.get_db(config_path)

    # finance_daily holds fees, refunds, principal, cogs and units PER ASIN, not
    # only per day, so the whole table can be built from what is already stored.
    fin = conn.execute(
        "SELECT asin, "
        "  SUM(COALESCE(principal,0))        principal, "
        "  SUM(COALESCE(referral_fees,0))    referral_fees, "
        "  SUM(COALESCE(fba_fees,0))         fba_fees, "
        "  SUM(COALESCE(other_fees,0))       other_fees, "
        "  SUM(COALESCE(refunds,0))          refunds, "
        "  SUM(COALESCE(refund_units,0))     refund_units, "
        # THE FEE AMAZON GIVES BACK when an order is refunded. It was not
        # selected at all, so the screen charged you the referral fee on a sale
        # that was returned -- understating the contribution of exactly the
        # products with returns. net_proceeds_for adds it back.
        "  SUM(COALESCE(refund_fees_returned,0)) refund_fees_returned, "
        "  SUM(COALESCE(reimbursements,0))   reimbursements, "
        "  SUM(COALESCE(promos,0))           promos, "
        "  SUM(COALESCE(units,0))            units, "
        "  SUM(COALESCE(cogs,0))             cogs, "
        "  SUM(COALESCE(cogs_units,0))       cogs_units, "
        # THE TAX AMAZON ITSELF REPORTED. Without this the aggregated row had no
        # 'tax' key at all, so sales_data.vat_for saw None -- "no tax recorded"
        # -- and fell through to deriving VAT out of the principal. Measured on
        # jack_uk: Amazon sends Tax as its own charge, 80.47 against 402.39 of
        # Principal, which is 20.0% ON TOP, so the principal is already
        # VAT-exclusive and there is nothing to take out. Deriving it anyway
        # removed 67.06 that was never there and cut the reported contribution
        # from 85.62 to 18.56 -- the double deduction the comment in vat_for
        # warns about, arriving by a route it could not see.
        #
        # NOT COALESCE'd to zero: SUM returns NULL when every row is NULL, and
        # that NULL is the difference between "Amazon said no tax" and "we never
        # recorded any". Flattening it to 0.0 would report every pre-tax-capture
        # period as zero-rated.
        "  SUM(tax)                          tax, "
        "  COUNT(tax)                        tax_rows, "
        "  COUNT(*)                          all_rows, "
        "  MAX(currency)                     currency "
        "FROM finance_daily WHERE workspace_id=? AND marketplace=? "
        "  AND date>=? AND date<=? AND asin<>'*' "
        "GROUP BY asin", (workspace_id, marketplace, start, end)).fetchall()

    # Ordered sales and units come from the sales report; kept beside the money
    # figures rather than mixed into them, and labelled as the other basis.
    sales = {r["asin"]: dict(r) for r in conn.execute(
        "SELECT asin, SUM(COALESCE(units,0)) units_ordered, "
        "       SUM(COALESCE(ordered_sales,0)) ordered_sales "
        "FROM sales_daily WHERE workspace_id=? AND marketplace=? "
        "  AND date>=? AND date<=? AND asin<>'*' GROUP BY asin",
        (workspace_id, marketplace, start, end)).fetchall()}

    ads = {r["asin"]: dict(r) for r in conn.execute(
        "SELECT asin, SUM(COALESCE(spend,0)) spend, SUM(COALESCE(ad_sales,0)) ad_sales "
        "FROM ads_daily WHERE workspace_id=? AND marketplace=? "
        "  AND date>=? AND date<=? AND asin<>'*' GROUP BY asin",
        (workspace_id, marketplace, start, end)).fetchall()}

    # WHO EACH ASIN IS, so the screen can say what the product is rather than
    # only B0H7N2Q5GG. A row you cannot identify at a glance is a row nobody
    # reads, and the identity is already in the app -- it just was not joined.
    #
    # FROM THE LIVE SNAPSHOT, which is what Amazon says is on this account.
    # NOT from listings.competitor_asin: per CLAUDE.md Rule 1 that column holds
    # the COMPETITOR's ASIN, the reference the listing was generated from, and
    # our own product carries a different ASIN entirely. Joining on it looks
    # right and would silently print a competitor's product name against our
    # revenue on any ASIN that happened to match. It is the same snapshot
    # domain/finance_data.sku_map already uses to attribute the fees in these
    # very rows, so the two cannot disagree about which product is which.
    #
    # Both are LOOKUPS, never filters: an ASIN with no name still gets its row,
    # because a product missing from the snapshot is exactly the one whose
    # contribution you most need to see.
    names, parents = {}, {}
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, workspace_id, marketplace) or {}
        for it in (rec.get("items") or []):
            a = str(it.get("asin") or "").strip()
            if a and not names.get(a):
                names[a] = str(it.get("title") or it.get("item_name") or "").strip()
    except Exception:
        names = {}
    try:
        for r in conn.execute(
                "SELECT asin, MAX(parent_asin) parent_asin FROM sales_daily "
                "WHERE workspace_id=? AND marketplace=? AND asin<>'*' "
                "  AND parent_asin IS NOT NULL AND parent_asin<>'' "
                "GROUP BY asin", (workspace_id, marketplace)).fetchall():
            # Amazon reports a standalone product as its own parent. Treated as
            # NO parent: grouping by it would otherwise build a family of one
            # around every single product and call that a rollup.
            if r["parent_asin"] != r["asin"]:
                parents[r["asin"]] = r["parent_asin"]
    except Exception:
        # An older database without the column is not a reason to fail the
        # screen; it only means nothing can be grouped by parent.
        parents = {}

    rows = []
    for r in fin:
        d = dict(r)
        asin = d["asin"]
        s = sales.get(asin) or {}
        a = ads.get(asin)

        # PARTIAL TAX COVERAGE IS NOT TAX. Where only some days in the window
        # carried Amazon's tax lines, summing them gives a figure that is right
        # for part of the period and presented as the whole -- which is worse
        # than admitting the gap, because it looks like an answer. Dropped back
        # to unknown, and the rate (if one is set) decides instead.
        if d.get("tax") is not None and d.get("tax_rows") != d.get("all_rows"):
            d["tax"] = None

        # THE WHOLE SUM IN ONE CALL, the same one the Sales screen makes.
        #
        # This was worked out here instead, and it had drifted: it left out the
        # promotions you funded and the fee Amazon returns on a refund. So a
        # coupon showed on this screen as money you kept, and the Finance and
        # Sales screens reported different profit for the same days -- with this
        # one higher. See domain/sales_data.net_proceeds_for.
        m = _sd.net_proceeds_for(d, vat_rate)
        fees = round(_f(m["total_fees"]), 2)
        vat, net_rev, basis = m["vat"], m["net_revenue"], m["vat_basis"]
        net = m["net_proceeds"]
        # A product with rows in finance_daily has had money move, so there is
        # always something to work from -- but never publish None as a number.
        if net is None:
            net = round(_f(d["principal"]) - fees, 2)
            net_rev = round(_f(d["principal"]), 2)

        units = int(d["units"] or 0)
        costed = int(d["cogs_units"] or 0)
        # The same rule the dashboard applies, called rather than repeated: a
        # bucket with any uncosted unit reports nothing at all.
        contribution = _sd.profit_for([{
            "units_shipped": units, "cogs_units": costed,
            "cogs": _f(d["cogs"]), "net_proceeds": net}], allow_uncosted=True)

        row = {
            "asin": asin,
            "title": names.get(asin) or "",
            # "" rather than falling back to the ASIN itself: a product with no
            # parent must not be grouped under a parent of one, which is what
            # defaulting to its own ASIN would silently produce.
            "parent_asin": parents.get(asin) or "",
            "units": units,                       # shipped -- the money basis
            "units_ordered": int(s.get("units_ordered") or 0),
            "revenue": round(_f(d["principal"]), 2),   # what buyers were charged
            "vat": vat,                                # None when nobody has said
            "net_revenue": net_rev,                    # what is actually yours
            "vat_basis": basis,
            "ordered_sales": round(_f(s.get("ordered_sales")), 2),
            "fees": fees,
            "refunds": round(_f(d["refunds"]), 2),
            "refund_units": int(d["refund_units"] or 0),
            "refund_fees_returned": round(_f(d["refund_fees_returned"]), 2),
            "reimbursements": round(_f(d["reimbursements"]), 2),
            "promos": round(_f(d["promos"]), 2),
            "cogs": round(_f(d["cogs"]), 2),
            "cogs_units": costed,
            "uncosted_units": max(0, units - costed),
            "net_proceeds": net,
            # None, not 0.0 -- nothing writes to ads_daily yet, and a zero here
            # would silently inflate every advertised product's contribution.
            "ad_spend": (round(_f(a.get("spend")), 2) if a else None),
            "contribution": contribution,
            "currency": d.get("currency") or "",
        }
        # Over sales AFTER VAT, the same as every other screen.
        row["margin_pct"] = (round(contribution / row["net_revenue"] * 100, 2)
                             if (contribution is not None and row["net_revenue"])
                             else None)
        rows.append(row)

    rows.sort(key=lambda x: (-(x["revenue"] or 0), x["asin"]))
    totals = totals_for(rows)
    totals.update(unattributed(conn, workspace_id, marketplace, start, end, rows))
    # WHAT THE ACCOUNT KEPT, as opposed to what the products contributed between
    # them. Only when the contribution is known at all: subtracting a real cost
    # from an unknown gives an unknown, not a negative.
    if totals.get("contribution") is not None and totals.get("unattributed_fees"):
        totals["account_contribution"] = round(
            totals["contribution"] - totals["unattributed_fees"], 2)
    return rows, totals


def by_product_orders(config_path, workspace_id, marketplace, start, end,
                      vat_rate=None):
    """The same table, on the ORDER calendar rather than the money calendar.

    WHY BOTH EXIST, AND WHY THIS ONE IS USUALLY THE USEFUL ONE.
    by_product above reads finance_daily -- money that has actually MOVED -- and
    Amazon settles days after the sale. Measured on nestwell_goods for August:
    that view returns ONE product, on an account where forty-five ASINs sold.
    The table is correct and nearly empty, and a screen that shows one row for a
    busy month gets read as "nothing sold".

    This covers every order PLACED in the window, whether Amazon has settled it
    or not. It ties to what was sold; the settlement view ties to the payout.

    THE SAME ARITHMETIC AS THE SALES CARD, CUT BY PRODUCT. Every figure comes
    from order_finance.complete_by_order_date(group="asin") -- the function the
    Sales screen and the P&L add up by day -- and sales_data.net_proceeds_for.
    Measured 27 Sep 2026, the copy of that arithmetic that lived here had
    drifted four ways: it left the VAT IN (worked out, then never subtracted),
    dropped the postage buyers paid, counted CANCELLED orders as sales, and
    charged a two-product order's whole fee to both products. On jack_uk that
    put this screen at 50.19 against the Sales card's 64.70 for the same month.

    REFUNDS KEEP THEIR OWN DATE. The owner's decision, unchanged: a refund
    belongs to the day the money moved, not the day of the sale, so a month
    already read does not change afterwards.

    AN UNCOSTED PRODUCT IS SHOWN, flagged. The owner's rule: "if no cogs are
    added show profit as wrong ... the user should know he needs to add cogs".
    Each row carries uncosted_units, and the notes say the figure is too high.

    Returns (rows, totals) in the SAME shape as by_product, so the screen can
    switch between them without knowing which produced what.
    """
    from domain import order_profit as _op
    from domain import order_finance as _of

    conn = _db.get_db(config_path)

    rate, rate_basis, rate_detail = _op.fee_rate(config_path, workspace_id,
                                                 marketplace, end)
    per = _of.complete_by_order_date(config_path, workspace_id, marketplace,
                                     start, end, fee_rate=rate,
                                     vat_rate=vat_rate, group="asin")

    titles = {}
    try:
        for r in conn.execute(
                "SELECT asin, MIN(title) title FROM order_lines "
                "WHERE workspace_id=? AND marketplace=? "
                "AND substr(purchase_date,1,10)>=? AND substr(purchase_date,1,10)<=? "
                "AND COALESCE(asin,'') <> '' GROUP BY asin",
                (workspace_id, marketplace, start, end)):
            titles[r["asin"]] = r["title"] or ""
    except Exception:
        titles = {}

    # ---- advertising, per ASIN -------------------------------------------
    ads = {}
    for r in conn.execute(
            "SELECT asin, ROUND(SUM(COALESCE(spend,0)),2) spend FROM ads_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=? "
            "AND asin<>'*' GROUP BY asin",
            (workspace_id, marketplace, start, end)):
        ads[r["asin"]] = _f(r["spend"])
    acct_ads = conn.execute(
        "SELECT SUM(spend) s FROM ads_daily WHERE workspace_id=? "
        "AND marketplace=? AND date>=? AND date<=? AND asin='*'",
        (workspace_id, marketplace, start, end)).fetchone()
    acct_ad_spend = (None if not acct_ads or acct_ads["s"] is None
                     else round(_f(acct_ads["s"]), 2))
    ads_connected = bool(ads) or acct_ad_spend is not None

    names, parents = {}, {}
    try:
        from domain import catalogue as _cat
        idx = _cat.merged(config_path, [(workspace_id, marketplace)])
        for asin in per:
            got = _cat.look(idx, None, asin) or {}
            if got.get("title"):
                names[asin] = got["title"]
    except Exception:
        pass
    try:
        for r in conn.execute(
                "SELECT DISTINCT asin, parent_asin FROM sales_daily "
                "WHERE workspace_id=? AND marketplace=? AND asin<>'*' "
                "AND COALESCE(parent_asin,'') <> ''",
                (workspace_id, marketplace)):
            parents[r["asin"]] = r["parent_asin"]
    except Exception:
        parents = {}

    rows = []
    est_rev_total, actual_fee_total = 0.0, 0.0
    unknown_fee_rev, unknown_fee_rows = 0.0, 0
    for asin, d in per.items():
        if not asin:
            # A line Amazon sent with no ASIN has nowhere to be shown; it is in
            # the account's figure, and unattributed_revenue below says so.
            continue
        units = int(d.get("units") or 0)
        costed = int(d.get("cogs_units") or 0)
        cogs = _f(d.get("cogs"))

        m = _sd.net_proceeds_for(d, vat_rate)
        fees = round(_f(m["total_fees"]), 2)
        net = m["net_proceeds"]
        if net is None:
            net = round(_f(d.get("principal")), 2)
        est = _f(d.get("fees_estimated"))
        actual_fee_total += fees - est
        if rate:
            est_rev_total += est / float(rate)
        fee_unknown = int(d.get("orders_fee_unknown") or 0) > 0
        if fee_unknown:
            unknown_fee_rev += _f(d.get("revenue_fee_unknown"))
            unknown_fee_rows += 1
        ad = ads.get(asin)

        # The same rule as everywhere else, called not repeated -- with the
        # owner's allowance for units nobody has costed yet.
        contribution = _sd.profit_for([{
            "units_shipped": units, "cogs_units": costed,
            "cogs": cogs, "net_proceeds": net}], allow_uncosted=True)
        # AND ADVERTISING COMES OFF IT. Only when it is known: subtracting an
        # unknown ad spend as if it were nought makes every advertised product
        # look better than it is, by exactly what is being spent on it.
        if contribution is not None and ad is not None:
            contribution = round(contribution - ad, 2)
        # AND A ROW WHOSE FEE IS UNKNOWN CANNOT STATE A CONTRIBUTION EITHER.
        # The fee was left out, not estimated at nought, so the figure would
        # flatter this product by whatever Amazon charges on its unsettled part.
        if fee_unknown:
            contribution = None

        revenue = round(_f(d.get("principal")) + _f(d.get("tax")), 2)
        net_rev = m["net_revenue"]
        row = {
            "asin": asin,
            "title": names.get(asin) or titles.get(asin) or "",
            "parent_asin": parents.get(asin) or "",
            "units": units,
            "units_ordered": units,
            "revenue": revenue,
            "vat": m["vat"], "net_revenue": net_rev, "vat_basis": m["vat_basis"],
            "ordered_sales": revenue,
            "fees": fees,
            "refunds": round(_f(d.get("refunds")), 2),
            "refund_units": int(d.get("refund_units") or 0),
            "refund_fees_returned": round(_f(d.get("refund_fees_returned")), 2),
            "reimbursements": round(_f(d.get("reimbursements")), 2),
            "promos": round(_f(d.get("promos")), 2),
            "cogs": cogs,
            "cogs_units": costed,
            "uncosted_units": max(0, units - costed),
            "net_proceeds": net,
            "ad_spend": (round(ad, 2) if ad is not None else None),
            "contribution": contribution,
            "currency": d.get("currency") or "",
        }
        # Over sales after VAT, the same as every other screen.
        row["margin_pct"] = (round(contribution / net_rev * 100, 2)
                             if (contribution is not None and net_rev) else None)
        rows.append(row)

    rows.sort(key=lambda x: (-(x["revenue"] or 0), x["asin"]))
    totals = totals_for(rows)
    totals.update(unattributed(conn, workspace_id, marketplace, start, end, rows))

    # ---- THE ACCOUNT'S FIGURE: the Sales card's, to the penny ------------
    #
    # The product rows cannot carry everything the account paid: ad spend no
    # product can be matched to, and money on a line with no ASIN. The step
    # from the products' total to the account's is shown rather than implied,
    # and the account's figure is the one the Sales card and the P&L state.
    acct = _op.for_period(config_path, workspace_id, marketplace, start, end,
                          vat_rate=vat_rate, ads_connected=ads_connected,
                          ad_spend=(acct_ad_spend or 0.0))
    prod_ads = sum(r["ad_spend"] or 0 for r in rows)
    gap_ads = round((acct_ad_spend or 0.0) - prod_ads, 2)
    totals["unattributed_ad_spend"] = gap_ads if gap_ads >= 0.01 else 0.0
    gap_rev = round(acct["revenue"] - (totals.get("revenue") or 0.0), 2)
    totals["unattributed_revenue"] = gap_rev if gap_rev >= 0.01 else 0.0
    totals["unattributed_pct"] = (
        round(totals["unattributed_revenue"] / acct["revenue"] * 100, 1)
        if acct["revenue"] and totals["unattributed_revenue"] else None)
    totals["account_contribution"] = acct["profit"]
    totals["account_margin_pct"] = acct["margin_pct"]
    # THE ACCOUNT-LEVEL AMAZON CHARGE IS NOT ANSWERED HERE on this calendar.
    # unattributed() finds it by comparing the settled feed with the product
    # rows, which only holds when the rows ARE the settled feed; on the order
    # calendar the rows cover unsettled trade too, and the comparison produces
    # a number with no meaning. expenses.overhead_for owns that charge, and the
    # Finance overhead step takes it from there (Rule 12).
    totals["unattributed_fees"] = 0.0
    totals["account_warning"] = acct.get("warning") or ""

    # HOW MUCH OF THIS IS AMAZON'S OWN FIGURE. A table whose fees are four
    # fifths estimated is a different document from one that is not.
    totals["basis"] = "orders"
    totals["fee_rate"] = rate
    totals["fee_rate_basis"] = rate_basis
    totals["fee_rate_detail"] = rate_detail
    totals["fees_actual"] = round(actual_fee_total, 2)
    totals["estimated_revenue"] = round(est_rev_total, 2)
    # The revenue carrying NO fee at all, because none could be measured. A
    # different thing from estimated_revenue, which has a fee with a stated
    # method behind it, and worth its own line: those products show no
    # contribution rather than a flattering one, and the screen should say why.
    totals["unpriced_fee_revenue"] = round(unknown_fee_rev, 2)
    totals["unpriced_fee_products"] = unknown_fee_rows
    totals["ads_connected"] = ads_connected
    return rows, totals


def unattributed(conn, workspace_id, marketplace, start, end, rows):
    """What the account was charged and paid that no product row carries.

    Returns {unattributed_fees, unattributed_revenue, unattributed_units,
             unattributed_pct, account_contribution}.

    WHY THIS SCREEN IS INCOMPLETE WITHOUT IT -- TWO SEPARATE THINGS
    Both end up in the same place: on the account-total row (asin='*') and on no
    product. Both are correct storage. Neither was visible on the screen.

    1. CHARGES WITH NO SKU. The GBP 25-a-month Professional selling subscription
       above all. There is no honest way to split it across products, so it sits
       on the account and nowhere else. Measured on jack_uk, 22 Jul to 16 Aug
       2026: products contributed 80.11 between them while the account was
       charged 50.00 of subscription, on the 14th and the 16th. The page said
       80.11 and the account kept 30.11.

    2. SALES WHOSE SKU COULD NOT BE MATCHED TO A PRODUCT. Financial events are
       keyed by seller SKU and this app is keyed by ASIN; the mapping comes from
       the live catalogue snapshot. A SKU that is not in the snapshot -- a
       listing deleted since, or an account whose catalogue has never been fully
       synced -- keeps its money on the account total. That is right, because a
       sale you cannot attribute is still a sale, but it means the LIST of
       products can be missing most of the trade.

       Measured on selvora_limited, 5 to 16 Aug 2026: 1909.11 of revenue and 60
       units on the account, 330.57 and 9 units across the one product with a
       row. The Finance screen showed one product and 17% of the money, with
       nothing to say the other 83% existed. Its snapshot holds 7 items.

    THE COMPARISON IS AGAINST THE SUM OF THE PRODUCT ROWS, never against a
    second hard-coded query, so a charge type Amazon invents next year turns up
    here without this function being taught its name.
    """
    out = {"unattributed_fees": 0.0, "unattributed_revenue": 0.0,
           "unattributed_units": 0, "unattributed_pct": None,
           "account_contribution": None}
    try:
        star = conn.execute(
            "SELECT SUM(COALESCE(referral_fees,0)) referral_fees, "
            "       SUM(COALESCE(fba_fees,0))      fba_fees, "
            "       SUM(COALESCE(other_fees,0))    other_fees, "
            "       SUM(COALESCE(principal,0))     principal, "
            "       SUM(COALESCE(units,0))         units "
            "FROM finance_daily WHERE workspace_id=? AND marketplace=? "
            "  AND date>=? AND date<=? AND asin='*'",
            (workspace_id, marketplace, start, end)).fetchone()
    except Exception:
        return out
    if not star:
        return out

    # Rounded before each comparison, not after: a float difference of 1e-13
    # across twenty days would otherwise be reported as unattributed money.
    #
    # ONLY A POSITIVE GAP IS EVER REPORTED. A negative one would mean the
    # products carry more than the account total does, which account-level
    # charges cannot produce -- it would be a storage fault. Inventing a negative
    # "unattributed cost" would quietly INCREASE the reported contribution, and
    # that is the one direction this must never move.
    def _gap(account_value, product_value):
        g = round(_f(account_value) - _f(product_value), 2)
        return g if g >= 0.01 else 0.0

    out["unattributed_fees"] = _gap(
        sum(_f(star[k]) for k in ("referral_fees", "fba_fees", "other_fees")),
        sum(_f(r.get("fees")) for r in rows))
    out["unattributed_revenue"] = _gap(
        star["principal"], sum(_f(r.get("revenue")) for r in rows))
    units_gap = int(round(_f(star["units"]) - sum(int(r.get("units") or 0)
                                                 for r in rows)))
    out["unattributed_units"] = max(0, units_gap)

    # AS A SHARE OF THE ACCOUNT'S OWN REVENUE, because 1578 means nothing on its
    # own and "83% of the money is not on this screen" cannot be misread.
    acct_rev = _f(star["principal"])
    if acct_rev and out["unattributed_revenue"]:
        out["unattributed_pct"] = round(
            out["unattributed_revenue"] / acct_rev * 100, 1)
    return out


def totals_for(rows):
    """The footer line. Contribution is recomputed, never summed.

    Summing the per-product contributions would silently drop every product whose
    own figure was withheld, and present the remainder as the total -- a smaller
    number wearing the label of a complete one.
    """
    t = {k: 0 for k in ("units", "units_ordered", "refund_units", "cogs_units",
                        "uncosted_units")}
    for k in ("revenue", "ordered_sales", "fees", "refunds", "reimbursements",
              "refund_fees_returned", "promos", "cogs", "net_proceeds",
              "net_revenue"):
        t[k] = 0.0
    for r in rows:
        for k in list(t):
            t[k] += (r.get(k) or 0)
    for k in ("revenue", "ordered_sales", "fees", "refunds", "reimbursements",
              "refund_fees_returned", "promos", "cogs", "net_proceeds",
              "net_revenue"):
        t[k] = round(t[k], 2)
    # VAT stays None if it is unknown ANYWHERE -- a total that quietly counts the
    # unknown rows as zero would understate what is owed.
    t["vat"] = (None if any(r.get("vat") is None for r in rows)
                else round(sum(r.get("vat") or 0 for r in rows), 2))
    t["vat_basis"] = next((r.get("vat_basis") for r in rows if r.get("vat_basis")), "")

    t["products"] = len(rows)
    t["ad_spend"] = None if all(r.get("ad_spend") is None for r in rows) \
        else round(sum(r.get("ad_spend") or 0 for r in rows), 2)
    # THE SUM OF THE ROWS' OWN FIGURES, so the footer is what the column above
    # it adds up to -- with a withheld row withholding the total, because a
    # total that silently skips a product is a smaller number wearing the label
    # of a complete one. A row is withheld only when its FEE is unknown; an
    # uncosted row is shown, flagged (the owner's rule, see profit_for).
    if any(r.get("contribution") is None for r in rows):
        t["contribution"] = None
    else:
        t["contribution"] = round(sum(r["contribution"] for r in rows), 2)
    # Over sales AFTER VAT, the same as every other screen.
    t["margin_pct"] = (round(t["contribution"] / t["net_revenue"] * 100, 2)
                       if (t["contribution"] is not None and t["net_revenue"])
                       else None)
    # The one implementation of "which currency is this?" -- this used to be it,
    # spelled out here while three other places took rows[0] and got "" on any
    # range starting before the account's first sale. Now shared, so they cannot
    # drift apart again.
    t["currency"] = _sd.currency_of(rows)
    return t


# HOW LOUD EACH NOTE IS.
#
# They were all one colour, which put "83% of your revenue is not on this screen"
# in the same amber box as "ad spend is not connected yet". The first means the
# page is not answering the question; the second is a caveat on an answer that is
# otherwise right. A reader who has learned to skim the amber boxes will skim
# both.
#
#   BAD   the figures on screen do not add up to the account. Read this or be
#         misled.
#   WARN  the figures are right as far as they go, and here is the limit.
#   INFO  how a figure was worked out.
NOTE_BAD = "bad"
NOTE_WARN = "warn"
NOTE_INFO = "info"


def notes(rows, totals):
    """What the screen has to say out loud, so no figure is read as more than it is.

    Returns a list of {text, level}. It used to return plain strings; callers that
    only want the words can join `n["text"]`.
    """
    out = []

    def say(level, text):
        out.append({"text": text, "level": level})

    cur = totals.get("currency") or ""

    # ORDER MATTERS: loudest first. These are read top to bottom and the last one
    # in a stack of five gets read least, so the note about money that is not on
    # the screen goes above the notes about how the money on it was worked out.

    # SALES MISSING FROM THE LIST ENTIRELY. A page showing 17% of the money with
    # no warning is not a page with a caveat, it is the wrong answer -- so this is
    # the one note marked BAD.
    missing = totals.get("unattributed_revenue") or 0
    if missing:
        pct = totals.get("unattributed_pct")
        say(NOTE_BAD,
            "%.2f %s of revenue%s%s is NOT in the list below. Amazon reports "
            "money against the seller SKU, and these sales are on SKUs that are "
            "not in this account's catalogue snapshot — usually listings deleted "
            "since, or an account whose catalogue has never been fully pulled. "
            "The money is counted on the account, but it cannot be shown against "
            "a product. Press Sync on the Listings screen to refresh the "
            "catalogue, then Sync here."
            % (float(missing), cur,
               ("" if not pct else " (%.1f%% of the total)" % pct),
               ("" if not totals.get("unattributed_units")
                else " and %d units" % totals["unattributed_units"])))

    # CHARGES THAT BELONG TO NO PRODUCT. Second, because it changes the headline
    # rather than the list: a page totalling every product reads as what the
    # account made, and account-level fees are not in any product's row.
    gap = totals.get("unattributed_fees") or 0
    if gap:
        acct = totals.get("account_contribution")
        # BAD when it can be shown what the account actually kept, because then
        # the footer figure is demonstrably not the answer. WARN when the
        # contribution is unknown anyway and this is one more reason why.
        say(NOTE_BAD if acct is not None else NOTE_WARN,
            "%.2f %s of Amazon's charges in this period belong to no single "
            "product — the monthly selling subscription is the usual one — so "
            "they are in none of the rows below.%s"
            % (float(gap), cur,
               ("" if acct is None else
                " The products contributed %.2f between them; after these "
                "charges the account kept %.2f."
                % (float(totals.get("contribution") or 0), float(acct)))))

    basis = totals.get("vat_basis") or ""
    if basis == _sd.VAT_UNKNOWN:
        # Not INFO: an unset VAT rate on a registered business overstates every
        # figure on the screen by a sixth, which is a wrong answer, not a caveat.
        say(NOTE_BAD,
            "VAT is not set for this account, so nothing has been taken out "
            "for it. If you are VAT-registered and Amazon's figures include "
            "VAT, every contribution here is overstated by roughly a sixth. "
            "Set the account's VAT rate and press Sync.")
    elif basis == _sd.VAT_DERIVED:
        say(NOTE_INFO,
            "Amazon did not itemise VAT, so it has been taken out of the "
            "charged amount at the account's rate. Revenue below is what "
            "buyers paid; contribution is worked out on the figure after VAT.")
    elif basis == _sd.VAT_FROM_AMAZON:
        say(NOTE_INFO,
            "Amazon reported VAT separately, so the revenue below is already "
            "net of it — nothing further has been deducted.")

    promos = totals.get("promos") or 0
    if promos:
        # Amount with the currency CODE rather than a symbol: there is no shared
        # symbol table in domain/ and adding a fourth money formatter to get a "£"
        # is not worth it (Rule 12). "12.34 GBP" is unambiguous.
        say(NOTE_INFO,
            "%.2f %s of coupons and deals you funded has been taken off. "
            "Amazon sends the full price and the discount separately, so "
            "the Revenue column below is what buyers were charged BEFORE "
            "your discount — the money you actually received is lower by "
            "this amount." % (float(promos), cur))
    if totals.get("ad_spend") is None:
        say(NOTE_WARN,
            "Ad spend is not connected, so this is contribution BEFORE "
            "advertising. On any product you advertise, the real "
            "contribution is lower by whatever you spent on it.")
    # UNCOSTED UNITS ARE SHOWN, AND SAID. The owner's rule: "if no cogs are
    # added show profit as wrong ... the user should know he needs to add
    # cogs". Those products' contribution counts their stock as costing
    # nothing, so it is too high by whatever the stock really cost.
    uncosted = [r for r in rows if (r.get("uncosted_units") or 0) > 0]
    if uncosted:
        say(NOTE_WARN,
            "%d product%s have %d unit%s with no cost recorded, so nothing was "
            "subtracted for that stock and their contribution is HIGHER than "
            "the truth. Set a cost, then press Sync."
            % (len(uncosted), "" if len(uncosted) == 1 else "s",
               sum(r["uncosted_units"] for r in uncosted),
               "" if sum(r["uncosted_units"] for r in uncosted) == 1 else "s"))
    blank = [r["asin"] for r in rows if r["contribution"] is None]
    if blank:
        say(NOTE_WARN,
            "%d product%s show no contribution because Amazon's fee on them "
            "could not be worked out -- this account has no measured fee rate "
            "yet, and leaving the fee out would flatter them."
            % (len(blank), "" if len(blank) == 1 else "s"))
    ua = totals.get("unattributed_ad_spend") or 0
    if ua:
        say(NOTE_INFO,
            "%.2f %s of ad spend could not be matched to any product, so it is "
            "in no row below. It is taken off the account's figure (%s), which "
            "is the same profit the Sales screen shows."
            % (float(ua), cur,
               ("%.2f %s" % (float(totals["account_contribution"]), cur))
               if totals.get("account_contribution") is not None else "not known"))
    return out
