"""domain/sourcing.py -- which supplier to buy from, and what that means for the listing.

This module decides. It does not fetch and it does not write. Everything here is
a pure function over data someone else gathered, which is deliberate: this is the
first part of the app that can change a live listing while nobody is watching,
and the only way to be sure of it is to be able to run every awkward case through
it without touching the network.

THE DECISION, IN ORDER
    filter -> rank -> pick.  Sources that cannot be used are dropped with a
    reason; the survivors are ordered by the user's strategy; the first one wins.
    If nothing survives, that is the out-of-stock signal -- but only if we
    actually LEARNED that, which is the whole difficulty (see below).

THREE THINGS A CHECK CAN TELL US, NOT TWO
    fetched -- we have real numbers.
    gone    -- the supplier's listing has ENDED. eBay's Browse API answers 400/404
               for an ended item (see fetch_ebay_supplement in the generator, which
               already documents this). That is a fact: you cannot buy from that
               URL any more -- ONCE IT IS CONFIRMED. A 404 is also what a blip,
               a rate-limit and a marketplace mismatch look like, so one on its
               own is treated as a failed read and a second is waited for. See
               gone_confirmed().
    failed  -- a timeout, a 5xx, an expired token, no network. We learned NOTHING.

    Collapsing 'failed' into 'out of stock' is the single most expensive mistake
    available here. A wobbly connection at 3am would take the whole catalogue out
    of stock, and the listings would lose their rank while the supplier was fine
    the entire time. So: when every source is blind, the answer is to do nothing.
    Only evidence moves a listing.

    Note where the asymmetry sits. A price change has three guards in front of
    it (max_change_pct, min_change, min_price). Going out of stock had none and
    needed only one reading, which made the CHEAPEST reading to obtain the one
    with the least standing behind it.

    This is the same rule as 0.00 not meaning free in domain/cogs.py. Unknown is
    not a value.

THE PRICE COMES FROM listing/pricing.py, NOT FROM HERE
    The price is the user's existing pricing rule and nothing else:

        price = source_cost + Amazon fee + postage label + ads allowance + min profit

    That is the same rule the generator uses to price a listing when it creates
    it, which is the point -- a listing repriced here must not jump away from the
    price it was created at. The competitor Buy Box is deliberately NOT consulted:
    the user asked for price to follow the supplier only.

    Two costs in that formula are easy to confuse and both are real:
      * the supplier's postage TO US is part of landed_cost below;
      * the postage label WE buy to send it on is shipping_label in the rule.
    Leaving either out prices the unit at a loss.

THREE GUARDS, AND WHAT EACH ONE ACTUALLY STOPS
    A supplier page can be misread -- a "from GBP 2.99", an accessory's price, a
    quantity break, the wrong currency. All of those make the source look CHEAPER
    than it is, so we price LOWER, and stock sells at a loss quickly and without
    complaint. It is worth being exact about which guard catches which fault,
    because it is tempting to believe the floor catches everything and it does not:

      the floor    stops us pricing below our COSTS. It is computed FROM the
                   source cost, so if that cost is wrong the floor is wrong with
                   it. It cannot catch a misparse. This is the guard people assume
                   covers them, and it is the one that does not.
      min_price    an absolute number the user sets per SKU. This IS the backstop
                   against a misread cost, because it does not depend on the
                   reading. Nothing should be armed to 'live' without one.
      max_change_pct catches the sudden misparse -- a cost that halves overnight
                   produces a price move far outside the limit, and the decision
                   is held for a human instead of pushed.

A NOTE ON THE FEE RATE
    referral_rate defaults to 0.15, matching _estimate_profit in dashboard.py and
    the generator's own fallback. Amazon's real referral fee varies by category
    (8% to 15%+), and the generator can fetch the exact figure from SP-API's
    Product Fees API. Doing that per SKU on a timer would be far too many calls,
    so this uses the rate -- which means where the rate is too LOW the floor is
    too low, the dangerous direction. It is per-rule for that reason and should be
    set per category on any SKU where the margin is thin.
"""
import datetime as _dt

from listing import pricing as _pricing   # the ONE definition of the pricing rule


# ---- what a check can be ---------------------------------------------------
FETCHED = "fetched"      # we have numbers
GONE    = "gone"         # the listing has ended -- once confirmed twice running
FAILED  = "failed"       # we learned nothing at all

DEFAULT_REFERRAL_RATE = 0.15

# What a marketplace charges in. Used to refuse a supplier quoting in another
# currency, which would otherwise be the quietest way to lose money here: a
# supplier at "10.00" USD read as though it were GBP looks about 20% cheaper
# than it is, so the floor comes out 20% low and the listing is underpriced --
# with every guard in this module agreeing that the number is fine, because the
# arithmetic IS fine. Only the units are wrong.
CURRENCY_FOR = {
    "UK": "GBP", "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL",
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR", "NL": "EUR",
    "BE": "EUR", "IE": "EUR", "AT": "EUR", "PL": "PLN", "SE": "SEK",
    "TR": "TRY", "AE": "AED", "SA": "SAR", "EG": "EGP", "IN": "INR",
    "JP": "JPY", "AU": "AUD", "SG": "SGD",
}

# HOW LONG THE POSTAGE ITSELF TAKES, once it has left. The Royal Mail / Evri
# service on these listings delivers in two days, and Amazon already counts
# that separately from the handling time -- so the handling time must NOT
# include it. See handling_days(). Editable in Settings, because a seller who
# switches to a next-day courier is making a one-day promise, not a two-day one.
SHIPPING_POLICY_DAYS = 2

DEFAULT_RULE = {
    "strategy":             "cheapest",   # 'cheapest' | 'fastest' | 'priority'
    "require_in_stock":     1,
    "max_dispatch_days":    None,         # None = no limit
    # EXTRA days on top of the worked-out handling time, for a supplier you do
    # not trust to dispatch when it says it will. Zero by default: the formula
    # in handling_days() already turns eBay's promise into Amazon's, and a
    # padding of 2 applied to every SKU whether or not anyone asked for it was
    # the same "helpful" default the three pricing allowances were removed for.
    # Set it per SKU, on the supplier that has actually let you down.
    "handling_buffer_days": 0,
    "referral_rate":        DEFAULT_REFERRAL_RATE,
    # The three per-unit costs of the user's pricing rule. Defaults come from
    # listing/pricing.py so there is one definition of what a unit costs to sell;
    # they are here so a SKU that posts in a bigger box can say so.
    "shipping_label":       _pricing.PRICING_RULE_SHIPPING_LABEL,
    "ads_margin":           _pricing.PRICING_RULE_ADS_MARGIN,
    "min_profit":           _pricing.PRICING_RULE_MIN_PROFIT,
    # NEVER SELL AT BREAK-EVEN. Separate from the two profit TARGETS below, and
    # deliberately so.
    #
    # The three amounts above used to default to 3.00, 2.00 and 1.00, which meant
    # every rule implicitly demanded at least a pound of profit whether or not
    # anyone had asked for one. The owner asked for those to go -- "do not add 3
    # pounds postage and 2 pounds ad cost and 1 pound profit space on your own"
    # -- and they have. With all three at zero, cost + Amazon's fee is the whole
    # floor, and that is the price at which a sale earns nothing at all.
    #
    # So the safety floor is stated as a percentage of the cash actually put in,
    # which means the same thing on a 12.00 unit and a 60.00 one. A flat pound
    # does not: it is 8% back on one and under 2% on the other.
    #
    # It is NOT a target. targets_set() ignores it, so "no target set" still
    # means what it always meant and the screen can still say so. It is the line
    # below which the app will not go, and setting it to 0 removes it.
    "min_roi_pct":          _pricing.PRICING_RULE_MIN_ROI_PCT,
    # What this listing sells in. Set from the marketplace by source_run.py; a
    # supplier quoting anything else is refused rather than silently converted
    # at 1:1. None disables the check, which is only right where every source is
    # known to quote in the listing's own currency.
    "currency":             None,
    # A PERCENTAGE profit target, on top of the flat min_profit above. Off until
    # set, because switching it on re-prices things. 'margin' is profit as a
    # share of what the customer pays; 'roi' as a share of what you paid, and the
    # two give very different prices from the same cost -- see
    # listing/pricing.py:floor_from_target. The price takes whichever floor is
    # HIGHEST, so setting a target can never quietly lower a price.
    #
    # TWO TARGETS, SET INDEPENDENTLY, and both apply. Asked for as "give me 2
    # different boxes for setting the roi or margin target on repricer".
    #
    # It used to be one box and a kind, so choosing margin threw away whatever
    # ROI you wanted. They are not alternatives -- "at least 20% margin AND at
    # least 30% back on the cash" is a perfectly ordinary thing to want, and on
    # an 11.95 unit those ask for 26.08 and 20.73, so neither implies the other.
    #
    # The price takes the HIGHEST floor of all of them, so adding a target can
    # raise a price and can never quietly lower one.
    "target_margin_pct":    None,         # profit / what the customer pays
    "target_roi_pct":       None,         # profit / what you paid
    # The single-target form this replaced. Still READ, so an account that set a
    # target before this change keeps it -- rule_with_defaults folds it into
    # whichever of the two above it names. Never written any more.
    "profit_target_kind":   None,         # 'margin' | 'roi' | None
    "profit_target_pct":    None,         # e.g. 20.0
    "min_price":            None,         # absolute floor, whatever the maths says
    "max_price":            None,         # absolute ceiling
    # THE PRICE THIS PRODUCT SELLS AT, held even when the target does not need it.
    #
    #   "i want the repricer to not to change my price if the margin or roi target
    #    set is less than my selling price ... if i am selling at 40 and the source
    #    is 12, and the roi is set to 20 percent, it should not decrease my price
    #    to maintain 20 percent roi. but if source price suddenly goes upto 35
    #    pounds and i am selling at 40 pounds, so then it should increase my
    #    selling price but when the source again came back to 12 or 20 pounds my
    #    selling price should be set to 40 again ... this rule is for the items
    #    where i am sure that this is the market price and this product sells on
    #    this price point no matter the roi or margin"
    #
    # Everything else in this file computes a FLOOR -- the least the price may be
    # -- and then sets the price to it. That is right when the target is what
    # decides the price, and wrong when the market decides it: a 12.00 cost with a
    # 20% ROI target asks 18.24, so a product selling perfectly well at 40.00 was
    # being cut by more than half to hit a target it had already beaten.
    #
    # hold_price is just one more floor, and that is the whole trick. price =
    # max(target floor, min_price, hold_price):
    #
    #   source at 12.00  ->  floor 18.24, hold 40.00  ->  40.00   (held)
    #   source at 35.00  ->  floor 46.24, hold 40.00  ->  46.24   (rises)
    #   source back to 12 -> floor 18.24, hold 40.00  ->  40.00   (returns)
    #
    # so "come back to 40" needs no memory of having been at 40. A ratchet that
    # remembered the last price could not answer what to return to after the price
    # had risen; a written-down number always can.
    #
    # SEPARATE FROM min_price ON PURPOSE. min_price means "below this I lose
    # money" -- a safety floor. hold_price means "this is what the market pays" --
    # a commercial decision. One number for both would mean that dropping the
    # floor for a clearance also gave the repricer permission to undercut the
    # market price, and that raising the market price also raised the
    # loss-protection floor.
    #
    # IT NEVER FORCES A LOSS. It is a floor among floors, so when the cost rises
    # past it the higher floor wins and the price goes UP -- which is the
    # behaviour asked for. It cannot hold a price below what the unit costs.
    "hold_price":           None,         # the market price, held against targets
    "max_change_pct":       25.0,         # a bigger jump than this waits for a human
    "min_change":           0.20,         # smaller than this is not worth a push
    "stale_after_hours":    24.0,
    # HOW MANY UNITS TO SHOW WHILE A SUPPLIER CAN SUPPLY.
    #
    #     "make me in stock to 3 units when the supplier is out of stock and if
    #      i have only 1 unit left in stock but the supplier is still in stock
    #      restock my qty to 3 maintain it until the supplier is out of stock"
    #
    # Three, and MAINTAINED at three rather than set once: decide() treats a
    # quantity that no longer matches this number as a reason to push, so two
    # sales off a stock of three put it back to three on the next check. It is
    # not a forecast of how many can be bought -- nothing is held in a warehouse
    # -- it is how many Amazon may sell before the next check, and a low number
    # is the guard against selling more than the supplier can send.
    "in_stock_quantity":    3,
    # How many readings in a row must say ENDED before we believe it. Price
    # changes have three guards; going out of stock had none, and it only ever
    # took one answer. 1 restores that. See gone_confirmed().
    "confirm_gone_checks":  2,
}


def rule_with_defaults(rule=None):
    """A complete rule, with anything unset filled in from DEFAULT_RULE.

    A NULL in the database means "never set this one", so it falls back rather
    than overriding with None. That is safe here because every setting whose
    sensible value is "no limit" -- max_dispatch_days, min_price, max_price --
    already defaults to None, so nothing needs a stored NULL to carry meaning.
    """
    out = dict(DEFAULT_RULE)
    for k, v in (rule or {}).items():
        if k in out and v is not None:
            out[k] = v
    # THE OLD SINGLE TARGET, FOLDED IN. An account that set "20% roi" before
    # there were two boxes has profit_target_kind='roi' and profit_target_pct=20
    # in its stored rule and nothing else. Read here rather than migrated in the
    # database, so the change cannot half-apply: the old fields are still the
    # truth for those accounts until someone sets a new one, and the new box
    # wins the moment they do.
    kind = str(out.get("profit_target_kind") or "").strip().lower()
    pct = out.get("profit_target_pct")
    if kind in ("margin", "roi") and pct is not None:
        key = "target_margin_pct" if kind == "margin" else "target_roi_pct"
        if out.get(key) is None:
            out[key] = pct
    return out


def _num(v):
    """A float, or None. Never raises, never guesses."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _parse_ts(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(str(s)[:19], fmt)
        except (TypeError, ValueError):
            continue
    return None


def age_minutes(check, now):
    """How old this reading is, or None if it carries no usable timestamp.

    None is treated as 'too old to trust' by every caller rather than as fresh --
    an undated reading is not a recent one.
    """
    t = _parse_ts((check or {}).get("checked_at"))
    if t is None or now is None:
        return None
    return (now - t).total_seconds() / 60.0


def landed_cost(check, fx=1.0):
    """Item price PLUS shipping, in our currency. None if either is unknown.

    Shipping is part of the cost, so comparing item prices alone would pick a
    "cheaper" source that costs more once posted. And unknown shipping is not
    free shipping: a fetcher that could not read a postage cost must leave it
    None, and this returns None rather than quietly costing it at zero -- which
    would understate cost and pull the price down.
    """
    if not check or check.get("status") != FETCHED:
        return None
    p, s = _num(check.get("price")), _num(check.get("shipping"))
    if p is None or s is None or p < 0 or s < 0:
        return None
    f = _num(fx)
    if f is None or f <= 0:
        return None
    return round((p + s) * f, 4)


def gone_confirmed(check, rule=None):
    """Has this source said ENDED often enough that we believe it?

    'gone' is the one reading that can zero a live listing's quantity, and until
    now a single one did it. That is the wrong amount of evidence: eBay's API
    answers 404 for an item that has genuinely ended AND, now and then, for one
    that is perfectly alive -- a blip, a rate-limit wearing a 404, a site that
    does not match the marketplace (source_fetch.py already documents that last
    one). Acting on the first sighting takes a live listing out of stock, where
    it stays until the next sweep puts it back.

    So it has to say so twice running. The count travels ON the reading as
    `gone_streak`, because a check dict is all decide() is ever given;
    source_repo.latest_checks() is what puts it there. A reading that arrives
    WITHOUT one has no history behind it and cannot be confirmed -- which fails
    towards leaving the listing alone, the only safe direction here.

    This is the single definition of "confirmed gone": both usable() and
    _blind() ask it, so the two cannot drift apart.
    """
    need = int(rule_with_defaults(rule).get("confirm_gone_checks") or 1)
    if need <= 1:
        return True
    try:
        return int((check or {}).get("gone_streak")) >= need
    except (TypeError, ValueError):
        return False


def usable(source, check, rule, now):
    """(True, "") if this source could be bought from, else (False, why not).

    The reason is written for the person reading the dry-run log, not for a
    developer, because that log is the whole basis on which they decide to arm
    this thing.
    """
    rule = rule_with_defaults(rule)
    if not (source or {}).get("enabled", 1):
        return False, "source turned off"
    if not check:
        return False, "never checked"

    st = check.get("status")
    if st == FAILED:
        return False, "last check failed (%s)" % (str(check.get("error") or "no detail")[:80])
    if st == GONE:
        if gone_confirmed(check, rule):
            return False, "the supplier's listing has ended"
        # Not buyable either way -- but the log has to say WHICH of the two this
        # is, because one takes the listing out of stock and the other waits.
        return False, ("the supplier's listing looks ended, but only on this one "
                       "reading -- waiting for a second before believing it")
    if st != FETCHED:
        return False, "no usable reading"

    age = age_minutes(check, now)
    if age is None:
        return False, "reading has no timestamp"
    if age > rule["stale_after_hours"] * 60.0:
        return False, "reading is %.1f hours old" % (age / 60.0)

    cost = landed_cost(check)
    if cost is None:
        return False, "price or postage unknown"

    # Units, not arithmetic. Nothing downstream can catch this: a USD figure
    # treated as GBP produces a floor that is internally consistent and about a
    # fifth too low. Refused outright rather than converted, because a stale or
    # invented exchange rate would be a second way to be confidently wrong.
    want_cur = str(rule.get("currency") or "").upper()
    got_cur = str(check.get("currency") or "").upper()
    if want_cur and got_cur and got_cur != want_cur:
        return False, ("priced in %s, but this listing sells in %s"
                       % (got_cur, want_cur))
    if want_cur and not got_cur:
        return False, "the supplier's currency is unknown"

    if rule["require_in_stock"]:
        if check.get("in_stock") is None:
            return False, "stock unknown"
        if not check.get("in_stock"):
            return False, "out of stock at the supplier"

    md = rule["max_dispatch_days"]
    if md is not None:
        d = check.get("dispatch_days")
        if d is None:
            return False, "dispatch time unknown"
        if int(d) > int(md):
            return False, "dispatches in %d days, limit is %d" % (int(d), int(md))

    return True, ""


def handling_days(dispatch_days, rule=None, shipping_policy_days=None):
    """How many days to promise Amazon, from how long the supplier takes.

        "handling = eBay_dispatch_days - 2 + user_buffer"

    THE PROMISE THE BUYER SEES IS HANDLING + SHIPPING, NOT HANDLING ALONE.
    Amazon shows a delivery date built from two numbers: the handling time we
    set, and the transit time of the postage service on the listing. The old
    formula added the supplier's dispatch time to a buffer and called that
    handling -- which quietly promised the supplier's days TWICE, once as our
    handling and again as the courier's transit.

    A 3-day eBay supplier used to become 3 + 2 = 5 days handling, plus 2 days
    of Royal Mail on top: a 7-day promise for something eBay said would be
    there in 3. That is not caution, it is losing the buy box for a week to
    describe a three-day product.

    Now the 2 days of postage we already promise are taken OFF, because they
    are counted by Amazon separately:

        handling = max(0, supplier dispatch - shipping policy) + buffer

    so 3-day dispatch becomes 1 day handling + 2 days shipping = the 3 days
    eBay actually promised.

    CLAMPED AT ZERO, never negative. A 1-day supplier gives max(0, -1) = 0,
    which means "posted the same day" -- and the shipping policy still carries
    the transit. Amazon rejects a negative handling time outright.

    ONE PLACE (CLAUDE.md Rule 12). Three screens worked this out separately --
    the decision itself, the drift report and the stock cover forecast -- and a
    change like this one made in two of the three would have shown two
    different promised dates for the same SKU on the same day.

    Returns None when the supplier's dispatch time is unknown, because a
    handling time invented from nothing is a delivery date invented from
    nothing.
    """
    if dispatch_days is None:
        return None
    r = rule or {}
    # The setting, if the caller stamped one on the rule (source_run does, from
    # config.json), then the explicit argument, then the module default. Same
    # order referral_rate follows, so the two settings behave alike.
    policy = shipping_policy_days
    if policy is None:
        policy = r.get("shipping_policy_days")
    if policy is None:
        policy = SHIPPING_POLICY_DAYS
    try:
        policy = max(0, int(policy))
    except (TypeError, ValueError):
        policy = SHIPPING_POLICY_DAYS
    try:
        buf = int(r.get("handling_buffer_days") or 0)
    except (TypeError, ValueError):
        buf = 0
    return max(0, int(dispatch_days) - policy) + buf


def handling_sentence(lead, dispatch_days, rule=None,
                      shipping_policy_days=None):
    """"handling 1 day -- the supplier dispatches in 3, 2 of which your postage
    already covers" -- the arithmetic in handling_days(), in words.

    Written once because two of decide()'s reasons quote it, and a formula
    explained two different ways is read as two different formulas.
    """
    if lead is None or dispatch_days is None:
        return ""
    r = rule or {}
    policy = shipping_policy_days
    if policy is None:
        policy = r.get("shipping_policy_days")
    try:
        policy = max(0, int(policy))
    except (TypeError, ValueError):
        policy = SHIPPING_POLICY_DAYS
    try:
        buf = int(r.get("handling_buffer_days") or 0)
    except (TypeError, ValueError):
        buf = 0
    s = ("handling %d day%s -- the supplier dispatches in %d, %d of which your "
         "postage already covers"
         % (lead, "" if lead == 1 else "s", int(dispatch_days), policy))
    if buf:
        s += ", plus %d extra day%s you asked for" % (buf, "" if buf == 1 else "s")
    return s


def _sort_key(pair, strategy):
    src, chk = pair
    cost = landed_cost(chk)
    disp = chk.get("dispatch_days")
    disp = 9999 if disp is None else int(disp)
    prio = int(src.get("priority") or 100)
    if strategy == "fastest":
        return (disp, cost, prio)
    if strategy == "priority":
        return (prio, cost, disp)
    return (cost, prio, disp)          # 'cheapest' is the default


def choose(pairs, rule, now):
    """Pick a source. Returns (chosen_pair_or_None, rejections).

    rejections is every source that could not be used and the reason, kept even
    when one IS chosen, because "why did it not use my cheapest supplier" is the
    question this feature will be asked most often.
    """
    rule = rule_with_defaults(rule)
    ok, rejected = [], []
    for src, chk in pairs:
        good, why = usable(src, chk, rule, now)
        if good:
            ok.append((src, chk))
        else:
            rejected.append({"source_id": src.get("id"),
                             "label": src.get("label") or src.get("url"),
                             "reason": why})
    if not ok:
        return None, rejected
    ok.sort(key=lambda p: _sort_key(p, rule["strategy"]))
    return ok[0], rejected


# ---- prices ----------------------------------------------------------------

def floor_price(cost, rule=None):
    """What this unit has to fetch, by the user's pricing rule. None if impossible.

    Delegates to listing/pricing.py -- the same rule the generator prices with --
    rather than working it out again here. `cost` is the LANDED cost of buying
    the unit (supplier price plus their postage to us); the postage label we then
    buy to send it to the customer is a separate line inside the rule.
    """
    rule = rule_with_defaults(rule)
    c = _num(cost)
    if c is None or c < 0:
        return None
    # A TARGET THAT CANNOT BE MET IS NOT A TARGET THAT IS ABSENT. Without this,
    # an impossible margin target produced no floor of its own and the unit was
    # priced to the flat minimum instead -- quietly, while the screen said a 95%
    # floor was in force.
    if unreachable_targets(c, rule):
        return None
    flat = _pricing.floor_from_rate(c, rule["referral_rate"],
                                    shipping_label=rule["shipping_label"],
                                    ads_margin=rule["ads_margin"],
                                    min_profit=rule["min_profit"])
    # THE SAFETY FLOOR. With the three per-unit amounts at 0.00, `flat` above is
    # exactly cost + Amazon's fee -- break-even. See min_roi_pct in DEFAULT_RULE.
    safety = None
    _mr = _num(rule.get("min_roi_pct"))
    if _mr is not None and _mr > 0:
        safety = _pricing.floor_from_target(c, rule["referral_rate"], "roi", _mr,
                                            shipping_label=rule["shipping_label"],
                                            ads_margin=rule["ads_margin"])
    floors = [f for f in (flat, safety) if f is not None]
    flat = max(floors) if floors else None

    tgt = target_floor(c, rule)
    if flat is None:
        return tgt
    if tgt is None:
        # NOTHING ASKS FOR ANY PROFIT AT ALL -- every amount and both targets
        # are zero. Break-even, and that is now the answer rather than a
        # refusal. Owner's decision, 27 Aug 2026:
        #
        #     "Default should be 0% -- meaning the repricer prices at breakeven
        #      (no profit, no loss) as the absolute floor. The user sets their
        #      own target."
        #
        # It used to return None here, on the argument that pricing to
        # break-even is worse than the padding it replaced. That argument was
        # answerable while min_roi_pct defaulted to 20 and this branch was
        # unreachable in practice; with the default at 0 it is the ordinary
        # case, and refusing would mean a fresh account could not price at all.
        #
        # Break-even is a real and defensible floor: cost plus Amazon's cut is
        # the price below which a sale destroys money, so it is the right
        # ABSOLUTE limit. Everything above it is a commercial decision, and
        # those belong to the owner -- one click on a row's ROI or Margin pill,
        # or "New SKUs start at" in the menu.
        return flat
    # The HIGHER of the two, always. A percentage target is a floor being added
    # to the rule, not one replacing it -- so switching it on can raise a price
    # and must never lower one.
    return max(flat, tgt)


def has_profit_requirement(rule=None):
    """Does this rule ask for ANY profit at all? True/False.

    True when a percentage target is set, or when one of the per-unit amounts is
    non-zero -- a flat min_profit, or a postage or ads allowance the owner has
    entered, all of which put the floor above break-even.

    Exists because "no requirement" became possible for the first time when the
    invented 3.00/2.00/1.00 defaults were removed. Before that every rule
    implicitly demanded at least a pound, so nothing had to ask.
    """
    rule = rule_with_defaults(rule)
    if targets_set(rule):
        return True
    for k in ("min_roi_pct", "min_profit", "shipping_label", "ads_margin"):
        v = _num(rule.get(k))
        if v is not None and v > 0:
            return True
    return False


def targets_set(rule=None):
    """[(kind, pct), ...] for every target actually set. Empty when none are.

    Both can be on at once, which is the whole point of the two boxes.
    """
    rule = rule_with_defaults(rule)
    out = []
    for kind, key in (("margin", "target_margin_pct"), ("roi", "target_roi_pct")):
        pct = _num(rule.get(key))
        if pct is not None and pct > 0:
            out.append((kind, pct))
    return out


def unreachable_targets(cost, rule=None):
    """Targets that are set but that NO price can satisfy. [(kind, pct), ...]

    Only a margin target can be one: Amazon's cut comes out of the same price,
    so margin + referral >= 100% is asking for more than the whole pound. ROI is
    measured against the cost and has no such ceiling -- 500% is ambitious, not
    impossible.

    Told apart from "no target set" ON PURPOSE. Both used to come back as a
    plain None from target_floor, so an impossible target was silently dropped
    and the SKU priced to the flat minimum -- the exact thing this module warns
    about everywhere else: a floor you believe is in force while the app prices
    to £1. The route refuses to SAVE an unreachable margin target, but a rule
    saved earlier can be made unreachable later by raising the referral rate,
    and nothing would have said so.
    """
    rule = rule_with_defaults(rule)
    c = _num(cost)
    if c is None or c < 0:
        return []
    out = []
    for kind, pct in targets_set(rule):
        if _pricing.floor_from_target(c, rule["referral_rate"], kind, pct,
                                      shipping_label=rule["shipping_label"],
                                      ads_margin=rule["ads_margin"]) is None:
            out.append((kind, pct))
    return out


def target_floor(cost, rule=None):
    """The price EVERY percentage target needs met, or None when none is set.

    Separate from floor_price so the screen can say what the targets ALONE ask
    for, which is the number a person needs when deciding whether a supplier is
    still worth buying from.

    With both targets on this is the higher of the two floors, for the same
    reason floor_price takes the higher of flat-and-target: a target is a floor
    being ADDED, so having two can raise the price and must never lower it.

    None means either no target is set or one cannot be met at any price. Those
    are different, and floor_price asks unreachable_targets() to tell them apart
    rather than pricing as though the target were absent.
    """
    rule = rule_with_defaults(rule)
    c = _num(cost)
    if c is None or c < 0:
        return None
    floors = []
    for kind, pct in targets_set(rule):
        f = _pricing.floor_from_target(c, rule["referral_rate"], kind, pct,
                                       shipping_label=rule["shipping_label"],
                                       ads_margin=rule["ads_margin"])
        if f is not None:
            floors.append(f)
    return max(floors) if floors else None


def target_status(price, cost, rule=None):
    """Does `price` meet the targets? None when none are set.

    {kind, target_pct, actual_pct, meets, short_by, profit, parts}

    THE TOP LEVEL IS THE WORST-PERFORMING TARGET -- the one that decides whether
    this SKU is flagged -- and `parts` holds every target separately so the
    screen can show both. Meeting your margin target while missing your ROI
    target is not "on target", so the flag follows the one that fails.

    `meets` is None -- not False -- when the figures needed to answer are
    missing, because "we cannot tell" and "it fails" are different things and
    only one of them is worth flagging.
    """
    rule = rule_with_defaults(rule)
    want = targets_set(rule)
    if not want:
        return None

    p, c = _num(price), _num(cost)
    got = None
    if p is not None and c is not None and p > 0 and c >= 0:
        got = _pricing.achieved(p, c, rule["referral_rate"],
                                shipping_label=rule["shipping_label"],
                                ads_margin=rule["ads_margin"])

    parts = []
    for kind, pct in want:
        one = {"kind": kind, "target_pct": pct, "actual_pct": None,
               "meets": None, "short_by": None,
               "profit": (got or {}).get("profit")}
        actual = None if got is None else (
            got.get("margin_pct") if kind == "margin" else got.get("roi_pct"))
        if actual is not None:
            one["actual_pct"] = actual
            one["meets"] = actual + 0.05 >= pct    # 0.05 absorbs 1dp rounding
            one["short_by"] = (None if one["meets"] else round(pct - actual, 1))
        parts.append(one)

    # The one that decides the flag: a failure if any fails, otherwise the
    # tightest of them. Unknown only when NOTHING could be worked out.
    failed = [x for x in parts if x["meets"] is False]
    if failed:
        lead = max(failed, key=lambda x: x["short_by"] or 0)
    else:
        known = [x for x in parts if x["meets"] is True]
        lead = (min(known, key=lambda x: (x["actual_pct"] or 0) - x["target_pct"])
                if known else parts[0])
    out = dict(lead)
    out["parts"] = parts
    return out


# ---- the decision ----------------------------------------------------------

def _blind(check, rule, now):
    """True when this check told us nothing we can act on.

    A CONFIRMED 'gone' is NOT blind -- an ended listing is a fact about the
    world. A single unconfirmed 'gone' is treated exactly like a read that
    failed, because that is precisely what it might be, and the branch below
    that handles unreadable sources already does the right thing with it:
    holds the listing and says why. A stale reading IS blind: it describes a
    supplier as they were yesterday, and acting on it is acting on a guess.
    """
    if not check:
        return True
    st = check.get("status")
    if st == GONE:
        return not gone_confirmed(check, rule)
    if st != FETCHED:
        return True
    age = age_minutes(check, now)
    return age is None or age > rule["stale_after_hours"] * 60.0


def decide(current, pairs, rule=None, now=None, listing_state=None):
    """What should happen to this listing. Never raises, never pushes anything.

    `current` is what Amazon has now: {price, quantity, lead_days}.
    `pairs` is [(source, latest_check), ...] for one SKU.
    `listing_state` is 'gone' when Amazon no longer has the SKU, 'ok' when it
    does, and None when nobody has looked.

    Returns a decision dict carrying its own justification, which is what gets
    written to sourcing_actions and read back weeks later.

    EVERY RULE HERE IS PER SKU, NEVER PER ASIN, and that is deliberate: one ASIN
    can carry several of our SKUs -- bought from different suppliers, at
    different costs, with different handling times -- so a decision made for the
    ASIN would price all of them from one of their costs. The enrollment, the
    sources and the rule are all keyed on sku alone; nothing in this module ever
    reads an ASIN.
    """
    rule = rule_with_defaults(rule)
    now = now or _dt.datetime.now()
    current = current or {}
    cur_price = _num(current.get("price"))
    cur_qty   = current.get("quantity")
    cur_lead  = current.get("lead_days")

    out = {"action": "none", "price": None, "quantity": None, "lead_days": None,
           "source_id": None, "reason": "", "blocked_by": "",
           "rejections": [], "inputs_age_mins": None,
           # None means "no target set", not "meets it" -- the screen has to be
           # able to tell those apart before it draws a flag.
           "target": None,
           # How far the price is moving, and whether that is past the notify
           # threshold. Always present so a caller never has to guess whether a
           # missing key means "small move" or "not worked out" -- move_pct is
           # None until there is a current price to measure against.
           "move_pct": None, "large_move": False, "large_move_note": "",
           "listing_state": listing_state or ""}

    # THE LISTING IS NOT THERE ANY MORE. Checked before anything else, because
    # nothing below it can matter: there is no offer to price.
    #
    # "the template and the repricer is saving the skus which i have deleted
    #  already, turn off the auto repricing for that sku and give warning to tell
    #  that this offer is deleted"
    #
    # Measured on jack_uk: six of 67 enrolled SKUs answer 404 GONE from Amazon,
    # and the repricer was still working out prices for all six.
    if str(listing_state or "") == "gone":
        out["blocked_by"] = "this listing is gone from Amazon"
        out["reason"] = ("Amazon no longer has this SKU, so there is no offer to "
                         "price. Auto-pricing has been switched off for it. "
                         "Remove it from the repricer, or relist it on Amazon.")
        return out

    live = [(s, c) for s, c in (pairs or []) if s.get("enabled", 1)]
    if not live:
        out["reason"] = "no sources are set up for this SKU"
        return out

    chosen, rejections = choose(live, rule, now)
    out["rejections"] = rejections

    # ---- nothing usable. Did we LEARN that, or just fail to look? ----------
    if chosen is None:
        # Going out of stock requires a definite answer about EVERY source. One
        # unreadable source is enough to stop it, because that source might be
        # perfectly able to supply -- and a network blip at 3am that took the
        # whole catalogue out of stock would cost rank on listings whose
        # suppliers were fine the entire time.
        #
        # A source rejected for being too slow or out of stock is NOT unreadable:
        # we know what it is, it simply fails the rule. Those can take a listing
        # out of stock, because that is what the rule asked for.
        blind = [s for s, c in live if _blind(c, rule, now)]
        if blind:
            out["blocked_by"] = ("no usable data from %d of %d sources"
                                 % (len(blind), len(live)))
            out["reason"] = ("nothing can be sourced from the sources we CAN read, "
                             "and %d could not be read -- leaving the listing "
                             "exactly as it is" % len(blind))
            return out
        out["action"] = "out_of_stock"
        out["quantity"] = 0
        out["reason"] = ("no source can supply this: "
                         + "; ".join("%s (%s)" % (r["label"], r["reason"])
                                     for r in rejections[:4]))
        return out

    src, chk = chosen
    cost = landed_cost(chk)
    out["source_id"] = src.get("id")
    out["inputs_age_mins"] = age_minutes(chk, now)

    # The price IS the floor. The user asked for price to follow the supplier
    # only, so unlike listing creation there is no competitor Buy Box pulling it
    # up -- see compute_selling_price in listing/pricing.py, which does that and
    # is deliberately not called here.
    floor = floor_price(cost, rule)

    # WHAT THIS LISTING IS EARNING RIGHT NOW, against the target if one is set.
    # Computed from the CURRENT Amazon price, not the proposed one, because the
    # question a flag answers is "is this SKU underwater today" -- and it is
    # attached whatever the decision turns out to be, including the ones that
    # change nothing, since those are exactly the SKUs a flag has to survive.
    out["target"] = target_status(cur_price, cost, rule)

    if floor is None:
        out["blocked_by"] = "the pricing rule cannot be met at any price"
        # WHICH target is impossible, by name. Only a MARGIN target can be:
        # Amazon's cut comes out of the same price, so margin + referral >= 100%
        # is asking for more than the whole pound. An ROI target has no such
        # ceiling -- it is measured against the cost, not the price -- so it is
        # never the culprit and is not blamed.
        rate = rule["referral_rate"]
        bad = unreachable_targets(cost, rule)
        if bad:
            out["reason"] = (
                "a %s target of %g%% cannot be met at any price once Amazon "
                "takes %.0f%% -- the two are competing for the same pound"
                % (bad[0][0], bad[0][1], rate * 100))
        elif not has_profit_requirement(rule):
            # Said in full, because it is the one refusal the owner can fix in a
            # moment and would otherwise read as a fault in the app.
            out["reason"] = (
                "no profit requirement is set for this SKU, so there is nothing "
                "to price towards -- cost plus Amazon's fee is break-even. Set a "
                "margin or an ROI target in the repricer's settings and it will "
                "price to it. (Nothing is assumed on your behalf any more: the "
                "3.00 postage, 2.00 ads and 1.00 profit that used to be added "
                "automatically have been removed.)")
        else:
            out["reason"] = ("a referral rate of %.0f%% leaves nothing to price "
                             "into" % (rate * 100))
        return out

    price = floor
    if rule["min_price"] is not None:
        price = max(price, float(rule["min_price"]))

    # THE MARKET PRICE, HELD. See hold_price in DEFAULT_RULE for the reasoning.
    #
    # Applied as one more floor rather than as a special case, so the source
    # rising past it automatically wins and the price goes UP -- it can never
    # hold a price below what the unit costs to sell.
    #
    # `held` is recorded because the screen has to be able to say WHY the price is
    # 40.00 when the target only asked 18.24. A price with no explanation is a
    # price someone will override by hand.
    hold = _num(rule.get("hold_price"))
    out["held"] = False
    if hold is not None and hold > 0:
        if hold > price:
            out["held"] = True
            out["held_at"] = round(hold, 2)
            out["held_over"] = round(price, 2)     # what the rules alone asked
            price = hold
        else:
            # The cost has risen past the held price, so the held price is no
            # longer the binding constraint and the floor is. Recorded so the log
            # shows the hold was considered and beaten, not ignored.
            out["hold_exceeded"] = round(hold, 2)

    # A ceiling below the floor means there is no price that is both acceptable
    # to the user and profitable. Going out of stock is the honest outcome --
    # the alternative is selling at a loss because a number was configured.
    if rule["max_price"] is not None:
        if floor > float(rule["max_price"]):
            out["action"] = "out_of_stock"
            out["quantity"] = 0
            out["reason"] = ("this costs %.2f landed and needs %.2f to cover fees, "
                             "postage and profit -- above the %.2f ceiling"
                             % (cost, floor, float(rule["max_price"])))
            return out
        price = min(price, float(rule["max_price"]))
        # A CEILING BELOW THE HELD PRICE. Contradictory settings -- hold at 40 with
        # a 30 ceiling -- and the ceiling wins, because it is the one that says
        # "never above this". But the hold must then stop CLAIMING to have set the
        # price: the reason sentence would have read "HELD at 30.00" when 30.00 is
        # the ceiling, and a log that misnames what decided a price is worse than
        # one that says nothing.
        if out.get("held") and price < float(out.get("held_at") or 0):
            out["held"] = False
            out["hold_capped"] = {"hold": out.pop("held_at", None),
                                  "ceiling": round(float(rule["max_price"]), 2)}
            out.pop("held_over", None)

    disp = chk.get("dispatch_days")
    lead = handling_days(disp, rule)
    qty = int(rule["in_stock_quantity"])

    out.update({"price": price, "quantity": qty, "lead_days": lead})

    # The SAME numbers as the reason sentence below, structured. The sentence is
    # the permanent record; this is so a screen can lay the sum out in labelled
    # parts without reading them back out of prose, which would be deriving
    # meaning from human-readable text (CLAUDE.md Rule 4) and would break the
    # moment the wording was improved.
    out["breakdown"] = {
        "supplier_price": _num(chk.get("price")),
        "supplier_postage": _num(chk.get("shipping")),
        "cost": round(cost, 2),
        "fee": round(price * rule["referral_rate"], 2),
        "fee_rate": rule["referral_rate"],
        "postage_label": round(float(rule["shipping_label"]), 2),
        "ads": round(float(rule["ads_margin"]), 2),
        # WHAT IS ACTUALLY LEFT, NOT WHAT WAS ASKED FOR.
        #
        #     "profit left over can not be zero in this case because the source
        #      is 24 and i am selling it on 24.99 so this is not true"
        #
        # Right, and worse than it looked. This was rule["min_profit"] -- an
        # INPUT, the flat amount you insist on ON TOP of everything else -- drawn
        # on screen under the label "Profit left over / what you keep per unit",
        # which is an OUTPUT. With min_profit at its default of 0.00 the panel
        # told you that you keep nothing per unit, on a price built to earn 20%.
        #
        # MEASURED on the owner's own row (cost 24.00, referral 15%, min_roi 20%):
        #
        #     supplier   24.00
        #     fee         5.08     <- matches the screen exactly
        #     postage     0.00
        #     ads         0.00
        #     profit      0.00     <- min_profit, and untrue
        #     price      33.89
        #
        #     24.00 + 5.08 + 0 + 0 + 0.00 = 29.08, against a price of 33.89.
        #     4.81 simply missing from a sum laid out to be added up -- and that
        #     4.81 IS the profit, exactly 20% of the 24.00 paid.
        #
        # The note two fields down already warned about this: "the breakdown says
        # '1.00 profit' while the price is really being set by a 20% target, and
        # the sum on screen would not add up to the number beside it". `targets`
        # was added so the screen COULD explain it; this line kept lying anyway.
        #
        # Derived from the price, so the column adds up whichever floor won --
        # flat minimum, safety floor, a target, or a held price.
        "profit": round(price - cost - float(rule["shipping_label"])
                        - float(rule["ads_margin"])
                        - (price * rule["referral_rate"]), 2),
        # The input is still carried, separately and under its own name, because
        # "you asked for at least X" is a real thing to want to show. It is no
        # longer what the profit line reads.
        "min_profit": round(float(rule["min_profit"]), 2),
        "price": price,
        "sources_usable": len(live) - len(rejections),
        "sources_total": len(live),
        "supplier_dispatch_days": (None if disp is None else int(disp)),
        "buffer_days": int(rule["handling_buffer_days"] or 0),
        # The postage days already promised separately, taken off the handling
        # time rather than promised twice. Carried so the screen can show the
        # subtraction instead of a number that looks two days short.
        "shipping_policy_days": int(rule.get("shipping_policy_days")
                                    or SHIPPING_POLICY_DAYS),
        "lead_days": lead,
        # Which floor actually decided the price. Without this the breakdown
        # says "1.00 profit" while the price is really being set by a 20% target,
        # and the sum on screen would not add up to the number beside it.
        # Every target that is on, so the breakdown can say which one set the
        # price rather than naming a single "kind" that no longer exists.
        "targets": [{"kind": k, "pct": p} for k, p in targets_set(rule)],
        "target_floor": target_floor(cost, rule),
        # THE HELD PRICE, and whether it is what set the price. Without both, a
        # screen showing "1.00 profit + 20% ROI" beside a price of 40.00 has no
        # way to say that neither of them decided it.
        "hold_price": (None if hold is None else round(hold, 2)),
        "held": bool(out.get("held")),
        # What the rules on their own would have asked for. This is the number the
        # owner wants to see NOT being used.
        "rules_price": (out.get("held_over") if out.get("held") else price),
        "at_price": _pricing.achieved(price, cost, rule["referral_rate"],
                                      shipping_label=rule["shipping_label"],
                                      ads_margin=rule["ads_margin"]),
    }

    # The breakdown goes in the reason because this line IS the audit trail --
    # "why is it 18.24" has to be answerable from the log alone, months later.
    #
    # A HELD PRICE GETS ITS OWN SENTENCE. The sum below explains a price built up
    # from cost + fee + postage + ads + profit, and a held price is not built that
    # way -- printing that sum beside 40.00 would be a breakdown that does not add
    # up to the number it is next to. So say what actually decided it, and what the
    # rules would have asked for, which is the comparison the owner wants.
    if out.get("held"):
        out["reason"] = ("%s of %d usable source(s): %s at %.2f landed; HELD at "
                         "%.2f (the market price) -- the rules alone would have "
                         "priced it at %.2f, which is lower, so it was not used%s"
                         % (rule["strategy"], len(live) - len(rejections),
                            src.get("label") or src.get("url"), cost,
                            price, out["held_over"],
                            "" if lead is None else
                            "; " + handling_sentence(lead, disp, rule)))
    else:
        # WRITTEN AS SENTENCES A PERSON READS, not as a formula.
        #
        #   "first of all this is very confusing even i am not able to
        #    understand what do it means"
        #
        # It used to read: "cheapest of 1 usable source(s): eBay item
        # 234416204068 at 12.99 landed; price 22.35 = 12.99 cost + 3.35 fee +
        # 3.00 postage + 2.00 ads + 1.00 profit; handling 5 days (3 + 2 buffer)".
        # Three semicolon-joined clauses, an arithmetic identity in the middle,
        # and the two largest terms in it were amounts nobody had asked for.
        #
        # Now: where it is being bought, what it costs, what it will sell for,
        # what that leaves, and how long it takes -- one thing per clause, in
        # the order somebody actually asks them.
        got = _pricing.achieved(price, cost, rule["referral_rate"],
                                shipping_label=rule["shipping_label"],
                                ads_margin=rule["ads_margin"])
        bits = []
        n_usable = len(live) - len(rejections)
        bits.append("Buying from %s at %.2f delivered%s."
                    % (src.get("label") or src.get("url"), cost,
                       "" if n_usable <= 1 else
                       " -- the %s of %d sources that can be used"
                       % ("cheapest" if rule["strategy"] == "cheapest"
                          else rule["strategy"], n_usable)))
        bits.append("Selling at %.2f leaves %.2f a unit after Amazon's %.2f fee%s."
                    % (price, got["profit"] if got["profit"] is not None else 0.0,
                       price * rule["referral_rate"],
                       "" if not (rule["shipping_label"] or rule["ads_margin"])
                       else " and your %.2f of postage and ads"
                            % (float(rule["shipping_label"])
                               + float(rule["ads_margin"]))))
        if got.get("roi_pct") is not None:
            bits.append("That is %.0f%% back on what you paid and %.0f%% of the "
                        "sale price." % (got["roi_pct"], got["margin_pct"] or 0))
        tset = targets_set(rule)
        if tset:
            bits.append("The price is the least that meets your %s."
                        % " and ".join("%g%% %s target" % (p, k)
                                       for k, p in tset))
        if out.get("hold_exceeded") is not None:
            bits.append("Your held price of %.2f no longer covers the cost, so "
                        "the price has risen above it." % out["hold_exceeded"])
        elif out.get("hold_capped"):
            bits.append("Your held price of %.2f was capped by the %.2f ceiling."
                        % (out["hold_capped"]["hold"],
                           out["hold_capped"]["ceiling"]))
        if lead is not None:
            bits.append(handling_sentence(lead, disp, rule).capitalize() + ".")
        out["reason"] = " ".join(bits)

    # ---- guards against acting on a number that only LOOKS right ----------
    if cur_price is not None and cur_price > 0:
        move = abs(price - cur_price) / cur_price * 100.0
        out["move_pct"] = round(move, 1)
        if move > rule["max_change_pct"]:
            # IT NO LONGER STOPS. Asked for plainly:
            #
            #     "i dont want the app to hold the change if there is more than
            #      the max change value, i just want it to send me the
            #      notification"
            #
            # This used to set action="none" and blocked_by, so a big move sat
            # waiting to be noticed -- and the run that produced it happens every
            # four hours, usually with nobody watching. A held price is not a
            # safe price: while it waits, the listing is at the OLD number, which
            # is the one the supplier's move just made wrong.
            #
            # max_change_pct now means "tell me above this", not "stop above
            # this". The change goes through; the flag below is what the apply
            # step turns into a notification (domain/source_apply.py).
            out["large_move"] = True
            out["large_move_note"] = (
                "price move of %.1f%% is over your %.1f%% notify threshold"
                % (move, rule["max_change_pct"]))

        same_lead = (lead is None or cur_lead is None or int(lead) == int(cur_lead))
        same_qty = (cur_qty is None or int(cur_qty) == qty)
        if abs(price - cur_price) < float(rule["min_change"]) and same_lead and same_qty:
            out["action"] = "none"
            out["reason"] = ("already within %.2f of the right price"
                             % float(rule["min_change"]))
            return out

    out["action"] = "update"
    return out
