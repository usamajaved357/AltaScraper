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


# £ per unit. Deliberately constants rather than settings: they are the user's
# actual costs, and a change to them re-prices everything, so it should be a
# visible edit rather than a field someone nudges.
PRICING_RULE_SHIPPING_LABEL = 3.00   # £ per unit -- Royal Mail Tracked 48 baseline
PRICING_RULE_ADS_MARGIN     = 2.00   # £ per unit -- estimated CPA / PPC budget
PRICING_RULE_MIN_PROFIT     = 1.00   # £ per unit -- absolute minimum to accept an order


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
             ads_margin=PRICING_RULE_ADS_MARGIN):
    """What a given price actually returns: {profit, margin_pct, roi_pct}.

    The inverse of the two functions above, and the only place that answers "is
    this listing hitting the target" -- so a flag on a screen and the price the
    repricer computes can never be working from different arithmetic.
    """
    try:
        p = float(price)
        c = float(source_cost)
        r = float(referral_rate)
    except (TypeError, ValueError):
        return {"profit": None, "margin_pct": None, "roi_pct": None}
    profit = p - (p * r) - c - float(shipping_label) - float(ads_margin)
    return {"profit": round(profit, 2),
            "margin_pct": (round(profit / p * 100.0, 1) if p > 0 else None),
            "roi_pct": (round(profit / c * 100.0, 1) if c > 0 else None)}


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
                          min_profit:     float = PRICING_RULE_MIN_PROFIT) -> dict:
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
    floor = floor_from_fees(source_cost, amazon_fees, shipping_label, ads_margin, min_profit)
    competitor_price = float(competitor_price or 0)
    if competitor_price > floor:
        chosen = competitor_price
        source = "competitor (higher than floor)"
    else:
        chosen = floor
        source = "floor (competitor missing or below floor)"
    return {
        "selling_price": chosen,
        "floor":         floor,
        "rule_source":   source,
        "breakdown":     (f"cost {source_cost:.2f} + fees {amazon_fees:.2f} "
                          f"+ ship {shipping_label:.2f} + ads {ads_margin:.2f} "
                          f"+ profit {min_profit:.2f} = floor {floor:.2f}"),
    }
