"""listing/pricing.py -- the pricing rule, in one place.

WHY THIS FILE EXISTS
compute_selling_price and its three constants lived in amazon_listing_generator.py
and set the price on every listing the generator has ever created. The source
repricer needs to answer the SAME question -- what is this unit worth selling at
-- every time a supplier moves their price.

Two implementations of that would have drifted immediately, and the first draft
of the repricer proved it: it used a percentage-margin formula that left out the
postage label and the ads allowance entirely, so on a 9.50 item it produced a
floor of 12.67 against this rule's 18.24, and would have priced at 15.84 while
reporting a healthy margin. The unit would have lost about a pound each time.

So this is now the single definition and both callers use it (CLAUDE.md Rule 12).
compute_selling_price was MOVED here unchanged -- same arithmetic, same rounding,
same returned keys -- so the generator behaves exactly as it did.

THE RULE
    floor = source_cost + amazon_fees + shipping_label + ads_margin + min_profit

Everything in it is money that actually leaves the account for that unit. The
postage label and the ads allowance are the two people forget, and they are worth
5.00 a unit here -- which is the difference between a profit and a quiet loss.

TWO WAYS TO ASK, ONE RULE
The referral fee is a PERCENTAGE OF THE PRICE, so the floor depends on the price
which depends on the floor. There are two honest ways out and this module offers
both, because the two callers arrive with different information:

  floor_from_fees  -- you already know the fee in pounds. The generator does: it
                      asks SP-API for the exact fee at a seed price, prices, then
                      asks again at the new price (see its two-pass call).
  floor_from_rate  -- you only know the fee as a rate. Solves it directly:
                          floor = cost + rate*floor + extras
                          floor = (cost + extras) / (1 - rate)
                      No iteration and no API call, which is what the repricer
                      needs when it is checking hundreds of SKUs on a timer.

They are the same rule and test_sourcing.py asserts they agree, both against each
other and against the price the generator has always produced.
"""
import math


# £ per unit. ALL THREE ARE NOW ZERO, AND THAT IS DELIBERATE.
#
#     "do not add 3 pounds postage and 2 pounds ad cost and 1 pound profit space
#      on your own, if i added this rule earlier, remove it. i want to be shown
#      the profit as the truth"
#
# They were 3.00, 2.00 and 1.00, and they were being subtracted from REPORTED
# PROFIT as well as built into the price -- which is a different thing entirely
# and is what made the app contradict itself. Measured on the latest
# nestwell_goods order, 18 Aug 2026:
#
#     the orders list said   13.49 - 2.02 fee - 8.89 cost      = +2.58, ROI 29%
#     opening the order said 13.49 - 2.02 fee - 8.79 source
#                                  - 3.00 postage - 2.00 ads   = -2.32, ROI -26%
#
# Both were "right" and neither was true: the second was charging the order £5 of
# allowances that no money ever left the account for. A profit figure is a
# statement about money that actually moved, and an allowance is a forecast.
#
# They remain as parameters because the seller really may post a parcel and
# really may spend on ads -- when those numbers are known they belong in
# domain/asin_charges.py, which holds the seller's OWN per-unit charges and is
# already subtracted by domain/order_profit.py. What they must never be again is
# a number this file invents on everyone's behalf.
PRICING_RULE_SHIPPING_LABEL = 0.00   # £ per unit -- set it if you buy a label
PRICING_RULE_ADS_MARGIN     = 0.00   # £ per unit -- set it if you fund ads
PRICING_RULE_MIN_PROFIT     = 0.00   # £ per unit -- see MIN_ROI_PCT below

# WHAT REPLACES THE FLAT £1, AND WHY A PERCENTAGE.
#
# With the three above at zero, a floor of "cost + Amazon's fee" is break-even,
# and a repricer that prices to break-even loses money on every sale it makes.
# So the profit requirement is expressed the way the owner has always expressed
# it -- "maintain at least 20 percent margin or roi" -- as a percentage of the
# cash he puts in, not as a flat pound figure that means 8% on a £12 item and 2%
# on a £60 one.
#
# It is a FLOOR among floors, so it can only ever raise a price. It is visible in
# the repricer as target_roi_pct and can be changed or switched off there.
PRICING_RULE_MIN_ROI_PCT    = 20.0   # % of landed cost, the least a sale may return


def _round_up(v):
    """2dp, rounded UP -- a floor rounded DOWN is not a floor."""
    return math.ceil(round(v * 100, 6)) / 100.0


def floor_from_target(source_cost, referral_rate, target_kind, target_pct,
                      shipping_label=PRICING_RULE_SHIPPING_LABEL,
                      ads_margin=PRICING_RULE_ADS_MARGIN):
    """The price at which profit reaches a PERCENTAGE target. None if impossible.

    The flat min_profit above is a fixed number of pounds, which is the right
    guard on a cheap unit and nearly meaningless on an expensive one: £1 on a
    £12 cost is 8% back, £1 on a £60 cost is under 2%. Asked for as "maintain at
    least 20 percent margin or roi".

    MARGIN AND ROI ARE DIFFERENT QUESTIONS AND GIVE DIFFERENT PRICES
      margin  profit as a share of what the CUSTOMER pays. Solving
                  p(1-r) - (c+s+a) = p*t
              gives  p = (c+s+a) / (1 - r - t)
              Note what that denominator does: the target competes with Amazon's
              cut for the same pound. At a 15% fee a margin target of 85% or more
              has no solution at any price, and one just under it prices into the
              thousands -- so it is refused rather than returned.
      roi     profit as a share of what YOU paid. Solving
                  p(1-r) - (c+s+a) = c*t
              gives  p = (c+s+a+c*t) / (1-r)
              Always solvable, and on cheap stock a far lower price than the same
              number expressed as margin: at £11.95 landed, 20% ROI is £23.93 and
              20% margin is £25.72.

    Returns None when the target cannot be met, rather than a number that only
    looks like a price.
    """
    try:
        c = float(source_cost)
        r = float(referral_rate)
        t = float(target_pct) / 100.0
    except (TypeError, ValueError):
        return None
    kind = str(target_kind or "").strip().lower()
    if c < 0 or r < 0 or t < 0 or kind not in ("margin", "roi"):
        return None
    extras = float(shipping_label) + float(ads_margin)
    if kind == "roi":
        denom = 1.0 - r
        if denom <= 0.01:
            return None
        return _round_up((c + extras + c * t) / denom)
    denom = 1.0 - r - t
    # Same guard as floor_from_rate: a denominator at or below zero flips the
    # sign and hands back a NEGATIVE price that still passes a "> 0" check.
    if denom <= 0.01:
        return None
    return _round_up((c + extras) / denom)


def achieved(price, source_cost, referral_rate,
             shipping_label=PRICING_RULE_SHIPPING_LABEL,
             ads_margin=PRICING_RULE_ADS_MARGIN,
             other_fees=0.0, promos=0.0):
    """What a given price actually returns: {profit, margin_pct, roi_pct, ...}.

    THE OWNER'S FORMULA, IN ONE LINE:

        profit = what the buyer paid
               - what the stock cost
               - Amazon's referral fee
               - Amazon's FBA fee, if it was fulfilled by Amazon
               - Amazon's fixed closing fee, on media items
               - any coupon or discount the seller funded

    `price` is the whole of what the buyer paid, postage included, because that
    is what Amazon charges its referral fee on. `other_fees` carries the FBA and
    closing fees -- ZERO unless something actually knows them, never guessed;
    domain/amazon_fees.py is what fills them in from Amazon's own settlement.

    `promos` is a coupon the seller funded. It defaults to 0 and MUST be left at
    0 when `price` came from the Orders API, whose OrderTotal already has the
    coupon deducted -- subtracting it again charges the discount twice. See the
    note in domain/orders_view.profit_for, which proved that on seven real
    orders across two accounts.

    shipping_label and ads_margin are the seller's own per-unit costs and are
    0.00 by default. They exist so a caller that KNOWS them can pass them; this
    function no longer invents them. See the constants above for the order that
    was reported as a £2.32 loss when it had in fact made £2.58.

    The returned dict also carries `fees`, `cost` and `deductions` so a screen
    can show the sum rather than only its answer.
    """
    try:
        p = float(price)
        c = float(source_cost)
        r = float(referral_rate)
    except (TypeError, ValueError):
        return {"profit": None, "margin_pct": None, "roi_pct": None,
                "fees": None, "cost": None, "deductions": None}
    referral = p * r
    extras = float(shipping_label or 0) + float(ads_margin or 0)
    fees = referral + float(other_fees or 0)
    profit = p - fees - c - extras - float(promos or 0)
    return {"profit": round(profit, 2),
            "margin_pct": (round(profit / p * 100.0, 1) if p > 0 else None),
            "roi_pct": (round(profit / c * 100.0, 1) if c > 0 else None),
            # The parts, so a breakdown never has to re-derive them and get a
            # different answer to the total sitting beside it.
            "referral": round(referral, 2),
            "fees": round(fees, 2),
            "cost": round(c, 2),
            "seller_costs": round(extras, 2),
            "promos": round(float(promos or 0), 2),
            "deductions": round(fees + c + extras + float(promos or 0), 2)}


def floor_from_fees(source_cost, amazon_fees,
                    shipping_label=PRICING_RULE_SHIPPING_LABEL,
                    ads_margin=PRICING_RULE_ADS_MARGIN,
                    min_profit=PRICING_RULE_MIN_PROFIT):
    """The floor when the Amazon fee is already known in pounds.

    Rounded to 2dp exactly as the original did, so the generator's prices do not
    move by a penny as a result of this extraction.
    """
    return round(source_cost + amazon_fees + shipping_label + ads_margin + min_profit, 2)


def floor_from_rate(source_cost, referral_rate,
                    shipping_label=PRICING_RULE_SHIPPING_LABEL,
                    ads_margin=PRICING_RULE_ADS_MARGIN,
                    min_profit=PRICING_RULE_MIN_PROFIT):
    """The same floor, when the fee is only known as a rate. None if impossible.

    A rate at or above 1.0 would divide by zero or flip the sign and hand back a
    NEGATIVE floor that still passes a "> 0" check, so it is refused outright.
    """
    try:
        cost = float(source_cost)
        rate = float(referral_rate)
    except (TypeError, ValueError):
        return None
    if cost < 0 or rate < 0:
        return None
    denom = 1.0 - rate
    if denom <= 0.01:
        return None
    return _round_up((cost + shipping_label + ads_margin + min_profit) / denom)


def compute_selling_price(source_cost: float,
                          amazon_fees: float,
                          competitor_price: float,
                          shipping_label: float = PRICING_RULE_SHIPPING_LABEL,
                          ads_margin:     float = PRICING_RULE_ADS_MARGIN,
                          min_profit:     float = PRICING_RULE_MIN_PROFIT,
                          min_roi_pct:    float = PRICING_RULE_MIN_ROI_PCT) -> dict:
    """Apply the user's pricing rule.

    Returns dict with:
      selling_price -- what to charge on the listing
      floor         -- the calculated cost-plus floor
      rule_source   -- 'competitor' (matched Buy Box) | 'floor' (used cost formula)
      breakdown     -- component list for the log line

    NOTE: Amazon fees are price-sensitive (referral fee is a % of selling price),
    so a naive floor with a fixed fee estimate under-prices. This is handled by
    the caller: it computes an initial fee at a reasonable seed price, calls this
    function, then re-fetches fees at the new price and calls this again once.
    Two passes is enough to converge for standard referral rates.

    NOTE 2: this raises the price to a competitor sitting ABOVE the floor. That
    is right when creating a listing, where the competitor is the market signal.
    The repricer deliberately does NOT use this -- the user asked for price to
    follow the supplier only -- so it calls floor_from_rate directly.
    """
    flat = floor_from_fees(source_cost, amazon_fees, shipping_label, ads_margin, min_profit)

    # THE PERCENTAGE FLOOR, so removing the flat £1 cannot list anything at
    # break-even. With the three per-unit constants at 0.00, `flat` above is
    # exactly cost + Amazon's fee -- a price at which the listing makes nothing
    # at all. That is not a floor, it is the line a floor sits above.
    #
    # Taken as the HIGHER of the two, never as a replacement, so this can only
    # raise a price. Where a competitor sits above both -- which is the ordinary
    # case for these listings -- the competitor still wins and the price is
    # completely unchanged by any of this.
    roi = None
    if min_roi_pct:
        roi = floor_from_target(source_cost, 0.0, "roi", min_roi_pct,
                                shipping_label, ads_margin)
        # floor_from_target works from a RATE, and here the fee is already known
        # in pounds, so the rate is passed as 0 and the fee added on afterwards.
        if roi is not None:
            roi = round(roi + float(amazon_fees), 2)
    floor = max(x for x in (flat, roi) if x is not None)

    competitor_price = float(competitor_price or 0)
    if competitor_price > floor:
        chosen = competitor_price
        source = "competitor (higher than floor)"
    else:
        chosen = floor
        source = "floor (competitor missing or below floor)"
    parts = (f"cost {source_cost:.2f} + fees {amazon_fees:.2f}")
    if shipping_label:
        parts += f" + ship {shipping_label:.2f}"
    if ads_margin:
        parts += f" + ads {ads_margin:.2f}"
    if min_profit:
        parts += f" + profit {min_profit:.2f}"
    if roi is not None and roi >= (flat or 0):
        parts += f" (raised to {min_roi_pct:g}% return on the {source_cost:.2f} cost)"
    return {
        "selling_price": chosen,
        "floor":         floor,
        "rule_source":   source,
        "breakdown":     f"{parts} = floor {floor:.2f}",
    }
