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
               URL any more.
    failed  -- a timeout, a 5xx, an expired token, no network. We learned NOTHING.

    Collapsing 'failed' into 'out of stock' is the single most expensive mistake
    available here. A wobbly connection at 3am would take the whole catalogue out
    of stock, and the listings would lose their rank while the supplier was fine
    the entire time. So: when every source is blind, the answer is to do nothing.
    Only evidence moves a listing.

    This is the same rule as 0.00 not meaning free in domain/cogs.py. Unknown is
    not a value.

THREE GUARDS, AND WHAT EACH ONE ACTUALLY STOPS
    A supplier page can be misread -- a "from GBP 2.99", an accessory's price, a
    quantity break, the wrong currency. All of those make the source look CHEAPER
    than it is, so we price LOWER, and stock sells at a loss quickly and without
    complaint. It is worth being exact about which guard catches which fault,
    because it is tempting to believe the floor catches everything and it does not:

      floor_price   stops us pricing below our MARGIN RULE. It is computed FROM
                    the source cost, so if that cost is wrong the floor is wrong
                    with it. It cannot catch a misparse. This is the guard people
                    assume covers them, and it is the one that does not.
      min_price     an absolute number the user sets per SKU. This IS the backstop
                    against a misread cost, because it does not depend on the
                    reading. Nothing should be armed to 'live' without one.
      max_change_pct catches the sudden misparse -- a cost that halves overnight
                    produces a price move far outside the limit, and the decision
                    is held for a human instead of pushed.

A NOTE ON THE FEE RATE
    referral_rate defaults to 0.15, matching _estimate_profit in dashboard.py.
    Amazon's real referral fee varies by category (8% to 15%+), so this default
    is a guide, not a quote. Where it is too LOW the floor is too low, which is
    the dangerous direction -- so it is per-rule and should be set per category
    for any SKU where margin is thin.
"""
import math
import datetime as _dt


# ---- what a check can be ---------------------------------------------------
FETCHED = "fetched"      # we have numbers
GONE    = "gone"         # the supplier's listing has ended -- definitive
FAILED  = "failed"       # we learned nothing at all

DEFAULT_REFERRAL_RATE = 0.15

DEFAULT_RULE = {
    "strategy":             "cheapest",   # 'cheapest' | 'fastest' | 'priority'
    "require_in_stock":     1,
    "max_dispatch_days":    None,         # None = no limit
    "handling_buffer_days": 2,            # promised time is ALWAYS above the source's
    "min_margin_pct":       10.0,         # below this we will not sell at all
    "target_margin_pct":    25.0,         # what we aim for when we can
    "referral_rate":        DEFAULT_REFERRAL_RATE,
    "min_price":            None,         # absolute floor, whatever the maths says
    "max_price":            None,         # absolute ceiling
    "max_change_pct":       25.0,         # a bigger jump than this waits for a human
    "min_change":           0.20,         # smaller than this is not worth a push
    "stale_after_hours":    24.0,
    "in_stock_quantity":    5,
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


def _round_up(v):
    """2dp, rounded UP.

    Always up, because every price this module produces is bounded below by a
    floor. Rounding a floor DOWN would put the price under it, which is the one
    direction that costs money.
    """
    return math.ceil(round(v * 100, 6)) / 100.0


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
        return False, "the supplier's listing has ended"
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

def _price_for_margin(cost, margin_pct, referral_rate):
    """The price at which `margin_pct` of it is left after cost and referral fee.

        price - price*fee - cost >= price*margin
        price >= cost / (1 - fee - margin)

    None when the denominator is zero or negative, which means the rule is
    asking for a margin that cannot exist at that fee -- 90% margin on a 15%
    fee, say. Returning None (and refusing to price) is right: any number
    produced there would be nonsense, and a negative denominator would flip the
    division and hand back a NEGATIVE price that still passes a "> 0" check.
    """
    c = _num(cost)
    if c is None or c < 0:
        return None
    fee = _num(referral_rate)
    m = _num(margin_pct)
    if fee is None or m is None:
        return None
    denom = 1.0 - fee - (m / 100.0)
    if denom <= 0.01:                  # 0.01 not 0: past here prices explode
        return None
    return _round_up(c / denom)


def floor_price(cost, rule=None):
    """The lowest price we are willing to sell at. Nothing may go below this."""
    rule = rule_with_defaults(rule)
    return _price_for_margin(cost, rule["min_margin_pct"], rule["referral_rate"])


def target_price(cost, rule=None):
    """The price we would like, if nothing else constrains it."""
    rule = rule_with_defaults(rule)
    return _price_for_margin(cost, rule["target_margin_pct"], rule["referral_rate"])


# ---- the decision ----------------------------------------------------------

def _blind(check, rule, now):
    """True when this check told us nothing we can act on.

    'gone' is NOT blind -- an ended listing is a fact about the world. A stale
    reading IS blind: it describes a supplier as they were yesterday, and acting
    on it is acting on a guess.
    """
    if not check:
        return True
    st = check.get("status")
    if st == GONE:
        return False
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
           "rejections": [], "inputs_age_mins": None}

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

    floor = floor_price(cost, rule)
    if floor is None:
        out["blocked_by"] = "margin rule cannot be met at any price"
        out["reason"] = ("min margin %.1f%% plus %.0f%% referral fee leaves nothing "
                         "to price into" % (rule["min_margin_pct"],
                                            rule["referral_rate"] * 100))
        return out

    price = max(target_price(cost, rule) or floor, floor)
    if rule["min_price"] is not None:
        price = max(price, float(rule["min_price"]))

    # A ceiling below the floor means there is no price that is both acceptable
    # to the user and profitable. Going out of stock is the honest outcome --
    # the alternative is selling at a loss because a number was configured.
    if rule["max_price"] is not None:
        if floor > float(rule["max_price"]):
            out["action"] = "out_of_stock"
            out["quantity"] = 0
            out["reason"] = ("cheapest source costs %.2f, which needs %.2f to make "
                             "%.1f%% -- above the %.2f ceiling"
                             % (cost, floor, rule["min_margin_pct"],
                                float(rule["max_price"])))
            return out
        price = min(price, float(rule["max_price"]))

    disp = chk.get("dispatch_days")
    lead = (int(disp) + int(rule["handling_buffer_days"])) if disp is not None else None
    qty = int(rule["in_stock_quantity"])

    out.update({"price": price, "quantity": qty, "lead_days": lead})
    out["reason"] = ("%s of %d usable source(s): %s at %.2f landed; price %.2f "
                     "(floor %.2f)%s"
                     % (rule["strategy"], len(live) - len(rejections),
                        src.get("label") or src.get("url"), cost, price, floor,
                        "" if lead is None else ", handling %d days (%d + %d buffer)"
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
