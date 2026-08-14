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
        "  SUM(COALESCE(reimbursements,0))   reimbursements, "
        "  SUM(COALESCE(promos,0))           promos, "
        "  SUM(COALESCE(units,0))            units, "
        "  SUM(COALESCE(cogs,0))             cogs, "
        "  SUM(COALESCE(cogs_units,0))       cogs_units, "
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

        fees = round(_f(d["referral_fees"]) + _f(d["fba_fees"]) + _f(d["other_fees"]), 2)
        # VAT out before anything else -- it was collected, never earned. Same
        # function the dashboard uses, so the two screens cannot disagree about
        # what a product's revenue actually was (Rule 12).
        vat, net_rev, basis = _sd.vat_for(d, vat_rate)
        net = round(net_rev - fees - _f(d["refunds"]) + _f(d["reimbursements"]), 2)

        units = int(d["units"] or 0)
        costed = int(d["cogs_units"] or 0)
        # The same rule the dashboard applies, called rather than repeated: a
        # bucket with any uncosted unit reports nothing at all.
        contribution = _sd.profit_for([{
            "units_shipped": units, "cogs_units": costed,
            "cogs": _f(d["cogs"]), "net_proceeds": net}])

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
        row["margin_pct"] = (round(contribution / row["revenue"] * 100, 2)
                             if (contribution is not None and row["revenue"]) else None)
        rows.append(row)

    rows.sort(key=lambda x: (-(x["revenue"] or 0), x["asin"]))
    return rows, totals_for(rows)


def totals_for(rows):
    """The footer line. Contribution is recomputed, never summed.

    Summing the per-product contributions would silently drop every product whose
    own figure was withheld, and present the remainder as the total -- a smaller
    number wearing the label of a complete one.
    """
    t = {k: 0 for k in ("units", "units_ordered", "refund_units", "cogs_units",
                        "uncosted_units")}
    for k in ("revenue", "ordered_sales", "fees", "refunds", "reimbursements",
              "promos", "cogs", "net_proceeds", "net_revenue"):
        t[k] = 0.0
    for r in rows:
        for k in list(t):
            t[k] += (r.get(k) or 0)
    for k in ("revenue", "ordered_sales", "fees", "refunds", "reimbursements",
              "promos", "cogs", "net_proceeds", "net_revenue"):
        t[k] = round(t[k], 2)
    # VAT stays None if it is unknown ANYWHERE -- a total that quietly counts the
    # unknown rows as zero would understate what is owed.
    t["vat"] = (None if any(r.get("vat") is None for r in rows)
                else round(sum(r.get("vat") or 0 for r in rows), 2))
    t["vat_basis"] = next((r.get("vat_basis") for r in rows if r.get("vat_basis")), "")

    t["products"] = len(rows)
    t["ad_spend"] = None if all(r.get("ad_spend") is None for r in rows) \
        else round(sum(r.get("ad_spend") or 0 for r in rows), 2)
    t["contribution"] = _sd.profit_for([{
        "units_shipped": t["units"], "cogs_units": t["cogs_units"],
        "cogs": t["cogs"], "net_proceeds": t["net_proceeds"]}])
    t["margin_pct"] = (round(t["contribution"] / t["revenue"] * 100, 2)
                       if (t["contribution"] is not None and t["revenue"]) else None)
    t["currency"] = next((r.get("currency") for r in rows if r.get("currency")), "")
    return t


def notes(rows, totals):
    """What the screen has to say out loud, so no figure is read as more than it is."""
    out = []
    basis = totals.get("vat_basis") or ""
    if basis == _sd.VAT_UNKNOWN:
        out.append("VAT is not set for this account, so nothing has been taken out "
                   "for it. If you are VAT-registered and Amazon's figures include "
                   "VAT, every contribution here is overstated by roughly a sixth. "
                   "Set the account's VAT rate and press Sync.")
    elif basis == _sd.VAT_DERIVED:
        out.append("Amazon did not itemise VAT, so it has been taken out of the "
                   "charged amount at the account's rate. Revenue below is what "
                   "buyers paid; contribution is worked out on the figure after VAT.")
    elif basis == _sd.VAT_FROM_AMAZON:
        out.append("Amazon reported VAT separately, so the revenue below is already "
                   "net of it — nothing further has been deducted.")
    if totals.get("ad_spend") is None:
        out.append("Ad spend is not connected, so this is contribution BEFORE "
                   "advertising. On any product you advertise, the real "
                   "contribution is lower by whatever you spent on it.")
    blank = [r["asin"] for r in rows if r["contribution"] is None]
    if blank:
        out.append("%d product%s have units with no known cost, so no contribution "
                   "is shown for them — a partial cost would only ever make them "
                   "look better than they are. Set a cost, then press Sync."
                   % (len(blank), "" if len(blank) == 1 else "s"))
    return out
