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

DEFAULT_RULE = {
    "strategy":             "cheapest",   # 'cheapest' | 'fastest' | 'priority'
    "require_in_stock":     1,
    "max_dispatch_days":    None,         # None = no limit
    "handling_buffer_days": 2,            # promised time is ALWAYS above the source's
    "referral_rate":        DEFAULT_REFERRAL_RATE,
    # The three per-unit costs of the user's pricing rule. Defaults come from
    # listing/pricing.py so there is one definition of what a unit costs to sell;
    # they are here so a SKU that posts in a bigger box can say so.
    "shipping_label":       _pricing.PRICING_RULE_SHIPPING_LABEL,
    "ads_margin":           _pricing.PRICING_RULE_ADS_MARGIN,
    "min_profit":           _pricing.PRICING_RULE_MIN_PROFIT,
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
    "profit_target_kind":   None,         # 'margin' | 'roi' | None
    "profit_target_pct":    None,         # e.g. 20.0
    "min_price":            None,         # absolute floor, whatever the maths says
    "max_price":            None,         # absolute ceiling
    "max_change_pct":       25.0,         # a bigger jump than this waits for a human
    "min_change":           0.20,         # smaller than this is not worth a push
    "stale_after_hours":    24.0,
    "in_stock_quantity":    5,
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
    flat = _pricing.floor_from_rate(c, rule["referral_rate"],
                                    shipping_label=rule["shipping_label"],
                                    ads_margin=rule["ads_margin"],
                                    min_profit=rule["min_profit"])
    tgt = target_floor(c, rule)
    if flat is None:
        return tgt
    if tgt is None:
        return flat
    # The HIGHER of the two, always. A percentage target is a floor being added
    # to the rule, not one replacing it -- so switching it on can raise a price
    # and must never lower one.
    return max(flat, tgt)


def target_floor(cost, rule=None):
    """The price the percentage profit target needs, or None when none is set.

    Separate from floor_price so the screen can say what the target ALONE asks
    for, which is the number a person needs when deciding whether a supplier is
    still worth buying from.
    """
    rule = rule_with_defaults(rule)
    kind = rule.get("profit_target_kind")
    pct = _num(rule.get("profit_target_pct"))
    if not kind or pct is None or pct <= 0:
        return None
    c = _num(cost)
    if c is None or c < 0:
        return None
    return _pricing.floor_from_target(c, rule["referral_rate"], kind, pct,
                                      shipping_label=rule["shipping_label"],
                                      ads_margin=rule["ads_margin"])


def target_status(price, cost, rule=None):
    """Does `price` meet the target? {kind, target_pct, actual_pct, meets, short_by}

    Returns None when no target is set. `meets` is None -- not False -- when the
    figures needed to answer are missing, because "we cannot tell" and "it fails"
    are different things and only one of them is worth flagging.
    """
    rule = rule_with_defaults(rule)
    kind = rule.get("profit_target_kind")
    pct = _num(rule.get("profit_target_pct"))
    if not kind or pct is None or pct <= 0:
        return None
    out = {"kind": kind, "target_pct": pct, "actual_pct": None,
           "meets": None, "short_by": None, "profit": None}
    p, c = _num(price), _num(cost)
    if p is None or c is None or p <= 0 or c < 0:
        return out
    got = _pricing.achieved(p, c, rule["referral_rate"],
                            shipping_label=rule["shipping_label"],
                            ads_margin=rule["ads_margin"])
    actual = got.get("margin_pct") if kind == "margin" else got.get("roi_pct")
    out["profit"] = got.get("profit")
    if actual is None:
        return out
    out["actual_pct"] = actual
    out["meets"] = actual + 0.05 >= pct        # 0.05 absorbs 1dp rounding
    out["short_by"] = (None if out["meets"] else round(pct - actual, 1))
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


def decide(current, pairs, rule=None, now=None):
    """What should happen to this listing. Never raises, never pushes anything.

    `current` is what Amazon has now: {price, quantity, lead_days}.
    `pairs` is [(source, latest_check), ...] for one SKU.

    Returns a decision dict carrying its own justification, which is what gets
    written to sourcing_actions and read back weeks later.
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
           "target": None}

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
        tf = rule.get("profit_target_kind")
        out["reason"] = (
            ("a %s target of %s%% cannot be met at any price once Amazon takes "
             "%.0f%% -- the two are competing for the same pound"
             % (tf, rule.get("profit_target_pct"), rule["referral_rate"] * 100))
            if tf == "margin" and _num(rule.get("profit_target_pct")) is not None
               and (_num(rule.get("profit_target_pct")) / 100.0
                    + rule["referral_rate"]) >= 0.99
            else ("a referral rate of %.0f%% leaves nothing to price into"
                  % (rule["referral_rate"] * 100)))
        return out

    price = floor
    if rule["min_price"] is not None:
        price = max(price, float(rule["min_price"]))

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

    disp = chk.get("dispatch_days")
    lead = (int(disp) + int(rule["handling_buffer_days"])) if disp is not None else None
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
        "profit": round(float(rule["min_profit"]), 2),
        "price": price,
        "sources_usable": len(live) - len(rejections),
        "sources_total": len(live),
        "supplier_dispatch_days": (None if disp is None else int(disp)),
        "buffer_days": int(rule["handling_buffer_days"]),
        "lead_days": lead,
        # Which floor actually decided the price. Without this the breakdown
        # says "1.00 profit" while the price is really being set by a 20% target,
        # and the sum on screen would not add up to the number beside it.
        "target_kind": rule.get("profit_target_kind"),
        "target_pct": rule.get("profit_target_pct"),
        "target_floor": target_floor(cost, rule),
        "at_price": _pricing.achieved(price, cost, rule["referral_rate"],
                                      shipping_label=rule["shipping_label"],
                                      ads_margin=rule["ads_margin"]),
    }

    # The breakdown goes in the reason because this line IS the audit trail --
    # "why is it 18.24" has to be answerable from the log alone, months later.
    out["reason"] = ("%s of %d usable source(s): %s at %.2f landed; price %.2f "
                     "= %.2f cost + %.2f fee + %.2f postage + %.2f ads + %.2f profit%s"
                     % (rule["strategy"], len(live) - len(rejections),
                        src.get("label") or src.get("url"), cost, price,
                        cost, price * rule["referral_rate"], rule["shipping_label"],
                        rule["ads_margin"], rule["min_profit"],
                        "" if lead is None else "; handling %d days (%d + %d buffer)"
                        % (lead, int(disp), int(rule["handling_buffer_days"]))))

    # ---- guards against acting on a number that only LOOKS right ----------
    if cur_price is not None and cur_price > 0:
        move = abs(price - cur_price) / cur_price * 100.0
        if move > rule["max_change_pct"]:
            # Above the floor and still a huge jump. Most likely a misread page,
            # occasionally a real supplier move -- either way a person should see
            # it before the listing does.
            out["action"] = "none"
            out["blocked_by"] = ("price move of %.1f%% exceeds the %.1f%% limit"
                                 % (move, rule["max_change_pct"]))
            return out

        same_lead = (lead is None or cur_lead is None or int(lead) == int(cur_lead))
        same_qty = (cur_qty is None or int(cur_qty) == qty)
        if abs(price - cur_price) < float(rule["min_change"]) and same_lead and same_qty:
            out["action"] = "none"
            out["reason"] = ("already within %.2f of the right price"
                             % float(rule["min_change"]))
            return out

    out["action"] = "update"
    return out
