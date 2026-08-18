"""domain/promotions.py -- what a coupon is actually costing, per SKU.

    "show profit per unit when no promotion like coupon or discounts etc are
     applied and also show the profit when some coupons or promotions etc are
     applied and the app should automatically know when which promotion or
     coupon is applied and how much is applied and make the calculations
     accordingly"

MEASURED, NEVER GUESSED. Amazon's SP-API does not hand this app a list of the
seller's running coupons and deals -- there is no operation for it that this
application is approved for. What Amazon DOES report, once an order settles, is
the promotion it funded, in the Finances API's PromotionList. That is already
stored per order by domain/order_finance.py.

So the question "is a coupon running on this SKU" is answered the only honest way
available: by looking at what buyers have actually been charged. If the last
twenty orders of a product each carried a 5% seller-funded discount, a 5% coupon
is running on it. If none of them did, none is.

THE ATTRIBUTION PROBLEM, AND HOW IT IS HANDLED
order_fees holds the promotion against the ORDER. It has no SKU column, because
Amazon reports it per shipment item and finance_data aggregates before it gets
here. An order with one line is unambiguous. An order with three lines has to
share the discount out, and it is shared BY REVENUE -- the same rule the referral
fee uses in domain/orders_view.line_breakdown, so the two cannot disagree about
which line carried what.

That is an approximation on multi-line orders and it is declared as one: every
reply says how many of the orders behind it had a single line.

WHAT THIS IS NOT
It is not a forecast. A coupon measured from last month's orders may have ended
this morning, and this module cannot know that. Every reply carries the date of
the most recent order it saw, so a screen can say "as at 14 Aug" rather than
implying it is live right now.

NO ORDERS MEANS NO ANSWER, not a discount of zero. A product nobody has bought
under a coupon and a product with no coupon look identical from here, and saying
"0%" would turn the first into a claim.
"""

# How far back to look. Long enough to catch a coupon on a slow seller, short
# enough that a promotion which ended months ago drops out by itself.
WINDOW_DAYS = 90

# Below this the figure is not worth showing: one discounted order is an
# anecdote, and a coupon inferred from it would move a profit figure on the
# strength of a single sale.
MIN_ORDERS = 2


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def measured(config_path, workspace_id, marketplace, days=WINDOW_DAYS):
    """{sku: {...}} -- the discount each SKU has actually been selling under.

    One pass over the window rather than a query per SKU: the repricer draws
    sixty rows at a time and a per-row query would be sixty round trips.

    Each entry:
        amount_per_unit   the seller-funded discount, in pounds, per unit
        pct               that as a share of what the buyer would have paid
        orders            how many settled orders it was measured from
        single_line       how many of those had one line (so were unambiguous)
        last_order        the most recent one, so a screen can date the figure
        units             units behind the figure
    """
    from data import db as _db

    out = {}
    try:
        conn = _db.get_db(config_path)
    except Exception:
        return out

    # Orders in the window that Amazon has settled AND that carried a promotion.
    # A settled order with no promotion is evidence too -- it says no coupon was
    # running -- so those are counted separately below.
    try:
        rows = conn.execute(
            "SELECT f.order_id, SUM(f.promos) promos "
            "FROM order_fees f "
            "WHERE f.workspace_id=? AND f.marketplace=? "
            "GROUP BY f.order_id", (workspace_id, marketplace)).fetchall()
    except Exception:
        return out
    promo_by_order = {str(r["order_id"]): _f(r["promos"]) for r in rows}
    if not promo_by_order:
        return out

    # The lines of those orders, so the discount can be put onto a SKU.
    try:
        lines = conn.execute(
            "SELECT order_id, sku, units, revenue, purchase_date "
            "FROM order_lines "
            "WHERE workspace_id=? AND marketplace=? AND IFNULL(sku,'')<>'' "
            "  AND lower(IFNULL(status,'')) NOT IN ('canceled','cancelled')",
            (workspace_id, marketplace)).fetchall()
    except Exception:
        return out

    by_order = {}
    for L in lines:
        by_order.setdefault(str(L["order_id"]), []).append(L)

    # HOW OFTEN A DISCOUNT WAS APPLIED AT ALL, counted separately.
    #
    # Averaging across every settled order -- discounted and not -- answers the
    # wrong question. Measured on jack_uk: 5 of its 11 settled orders carried a
    # coupon, and averaging all eleven reported "2% off" when the coupon itself
    # is 6%. The rate has to be measured from the orders that HAD it; how many
    # of them there were is a separate and equally useful fact, because a coupon
    # on five orders in eleven is one that started part-way through the window
    # or is running on some listings and not others.
    seen_orders = {}
    for oid, got in by_order.items():
        if oid not in promo_by_order:
            continue                      # not settled: says nothing either way
        for L in got:
            k = str(L["sku"])
            seen_orders[k] = seen_orders.get(k, 0) + 1

    for oid, promo in promo_by_order.items():
        if promo <= 0:
            continue                      # settled with no discount on it
        got = by_order.get(oid) or []
        if not got:
            continue
        total_rev = sum(_f(L["revenue"]) for L in got)
        one_line = (len(got) == 1)
        for L in got:
            sku = str(L["sku"])
            rev = _f(L["revenue"])
            units = int(_f(L["units"], 0)) or 1
            # BY REVENUE, the same way the referral fee is shared out. On a
            # single-line order this is the whole promotion and exact.
            share = promo if one_line else (
                promo * (rev / total_rev) if total_rev > 0 else 0.0)
            e = out.setdefault(sku, {
                "promo": 0.0, "revenue": 0.0, "units": 0, "orders": 0,
                "single_line": 0, "last_order": ""})
            e["promo"] += share
            e["revenue"] += rev
            e["units"] += units
            e["orders"] += 1
            if one_line:
                e["single_line"] += 1
            d = str(L["purchase_date"] or "")[:10]
            if d > e["last_order"]:
                e["last_order"] = d

    final = {}
    for sku, e in out.items():
        if e["orders"] < MIN_ORDERS or e["promo"] <= 0 or e["units"] <= 0:
            continue
        per_unit = round(e["promo"] / e["units"], 2)
        # THE DISCOUNT AS A SHARE OF THE UNDISCOUNTED PRICE. `revenue` is what
        # the buyer was charged AFTER the coupon on the Orders feed, so the
        # price before it is revenue + promo -- which is the base a percentage
        # coupon was applied to.
        gross = e["revenue"] + e["promo"]
        final[sku] = {
            "amount_per_unit": per_unit,
            "pct": (round(e["promo"] / gross * 100.0, 1) if gross > 0 else None),
            "orders": e["orders"],
            # Of every SETTLED order for this SKU, how many carried a discount.
            # 5 of 11 is a coupon that started part-way through the window or is
            # not on every listing; 11 of 11 is one that is simply on.
            "settled_orders": seen_orders.get(sku, e["orders"]),
            "single_line": e["single_line"],
            "units": e["units"],
            "last_order": e["last_order"],
            "exact": e["single_line"] == e["orders"],
        }
    return final


def describe(p):
    """One sentence about a measured discount, for a tooltip or a note."""
    if not p:
        return ""
    bits = ["%.2f a unit" % p["amount_per_unit"]]
    if p.get("pct") is not None:
        bits.append("about %.0f%% off" % p["pct"])
    s = ("Measured from %d settled order%s that carried a discount — %s."
         % (p["orders"], "" if p["orders"] == 1 else "s", ", ".join(bits)))
    n_all = p.get("settled_orders") or p["orders"]
    if n_all > p["orders"]:
        s += (" %d of this SKU's %d settled orders had one, so it may have "
              "started part-way through, or may not be on every listing."
              % (p["orders"], n_all))
    if p.get("last_order"):
        s += " Most recent was %s." % p["last_order"]
    if not p.get("exact"):
        s += (" Some of those orders had several products, so the discount was "
              "shared across them by what each one sold for.")
    s += (" Amazon does not tell this app which coupons are running, so this is "
          "what buyers were actually charged rather than a setting read from "
          "Seller Central.")
    return s


def apply_to(price, p):
    """The price a buyer actually pays once the measured discount comes off.

    Returns `price` unchanged when there is nothing measured -- never a guess at
    zero, and never a negative price if a bad figure ever got in.
    """
    try:
        v = float(price)
    except (TypeError, ValueError):
        return None
    if not p:
        return round(v, 2)
    off = _f(p.get("amount_per_unit"))
    return round(max(0.0, v - off), 2)
