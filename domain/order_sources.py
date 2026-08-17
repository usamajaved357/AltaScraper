"""domain/order_sources.py -- "an order came in; where do I buy it from?"

    "display the source links in the order details arranged by low to high
     price, which tells the user you have received an order and you can place
     the order from one of these. also show handling time and profit pounds if
     the user place order from each link what will be the profit and when will
     my order will be delivered to the buyer"

ONE FUNCTION, TWO SCREENS. Order details asks it, and so does the repricer --
"i want to see this information of the source in the repricer as well". Written
once here so the two cannot come to disagree about which link is cheapest or what
it would earn (CLAUDE.md Rule 12).

WHAT IT DOES NOT DO
It does not decide anything. domain/sourcing.py owns every rule about which source
may be used and what price to set; this ranks what is there and works out what
each one would earn, for a person to choose from. Two consequences:

  * a source sourcing.py would REFUSE is still listed. Out of stock, ended,
    unreadable -- they are shown, marked, and sorted below the buyable ones. The
    owner needs to know a link exists and is dead, which is the whole point of
    the out-of-stock alert; hiding it would make three sources look like one.
  * the profit figure comes from listing/pricing.achieved(), which is the one
    implementation of "what does this price actually return" and the same one the
    repricer prices against. A second copy here would drift and the order screen
    would quietly contradict the repricer.

PER SKU, NEVER PER ASIN. A single ASIN can carry several SKUs with different
costs and different rules, so everything here is keyed by SKU -- see the note at
the top of domain/sourcing.py.
"""
from domain import source_repo as _repo
from domain import sourcing as _sourcing
from listing import pricing as _pricing

# The three states a link can be in, from the point of view of someone about to
# buy from it. Named so a screen never has to test strings itself.
BUYABLE = "buyable"          # in stock, readable, has a price
UNKNOWN = "unknown"          # we could not read it this time; it may be fine
DEAD = "dead"                # out of stock, or the listing has ended


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _state(check):
    """buyable / unknown / dead for one reading. Never guesses in the good direction."""
    if not check:
        return UNKNOWN
    status = str(check.get("status") or "")
    if status == _sourcing.GONE:
        return DEAD
    if status != _sourcing.FETCHED:
        return UNKNOWN
    if check.get("in_stock") is False:
        return DEAD
    if _f(check.get("price")) is None:
        return UNKNOWN
    # in_stock None means eBay did not say. NOT treated as dead -- that would
    # hide a link that is probably fine -- and not as buyable either.
    return BUYABLE if check.get("in_stock") else UNKNOWN


def _delivery_text(check):
    """"Wed 19 Aug to Mon 24 Aug", or one date, or "".

    The wording the owner used: "delivery estimated between wed 19 aug and thu 20
    aug". Built here rather than in the screen because the repricer wants the same
    sentence.
    """
    lo = str((check or {}).get("delivery_min") or "")
    hi = str((check or {}).get("delivery_max") or "")

    def pretty(iso):
        # Mon 24 Aug. Done by hand rather than with strftime %a/%b, which follow
        # the machine's locale -- a server set to another language would print a
        # day name the owner does not read.
        try:
            y, m, d = (int(x) for x in iso.split("-"))
        except (ValueError, AttributeError):
            return ""
        import datetime as _dt
        try:
            dd = _dt.date(y, m, d)
        except ValueError:
            return ""
        days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        return "%s %d %s" % (days[dd.weekday()], dd.day, months[dd.month - 1])

    a, b = pretty(lo), pretty(hi)
    if a and b and a != b:
        return "%s to %s" % (a, b)
    return b or a or ""


def options_for(config_path, workspace_id, marketplace, sku, sell_price=None,
                rule=None, now=None, fx=1.0, fee_amount=None):
    """Every tracked source for one SKU, cheapest to buy from first.

    Each option carries what it costs, what it would earn at `sell_price`, how it
    gets here and when. `sell_price` is what the buyer actually paid for THIS
    order -- not the current listing price -- so the profit shown is the profit on
    the order in front of you.

    `fee_amount` is what Amazon ACTUALLY took, in pounds, when that is known --
    domain/amazon_fees.py gets it from Amazon's own settlement. Given it, the
    profit here is worked out against the same fee the order's own profit used,
    so the two figures on one screen cannot disagree. Without it, the rule's rate
    is applied, which is the estimate this always used.

    NOTHING IS ADDED THAT AMAZON DOES NOT CHARGE. This used to subtract a 3.00
    postage allowance and a 2.00 advertising allowance from every option, so the
    order the list reported as +2.58 opened showing -2.32 -- the same order, £5
    apart, because one of the two was charging it for money that never moved.
    Those allowances are now 0.00 unless the owner sets them; see
    listing/pricing.py.
    """
    pairs = _repo.pairs_for(config_path, workspace_id, marketplace, sku)
    if not pairs:
        return []
    rule = _sourcing.rule_with_defaults(rule)
    price = _f(sell_price)

    out = []
    for source, check in pairs:
        state = _state(check)
        landed = _sourcing.landed_cost(check, fx) if check else None
        row = {
            "source_id": source.get("id"),
            "url": source.get("url") or "",
            "label": source.get("label") or source.get("url") or "",
            "kind": source.get("kind") or "ebay",
            "enabled": bool(source.get("enabled", 1)),
            "state": state,
            "status": (check or {}).get("status") or "",
            "checked_at": (check or {}).get("checked_at") or "",
            "error": (check or {}).get("error") or "",
            "price": _f((check or {}).get("price")),
            "shipping": _f((check or {}).get("shipping")),
            "landed": landed,
            "currency": (check or {}).get("currency") or "",
            "in_stock": (check or {}).get("in_stock"),
            "available_qty": (check or {}).get("available_qty"),
            # HOW IT GETS HERE AND WHEN -- see domain/source_fetch.py.
            "carrier": (check or {}).get("carrier") or "",
            "postage_text": (check or {}).get("postage_text") or "",
            "delivery_min": (check or {}).get("delivery_min") or "",
            "delivery_max": (check or {}).get("delivery_max") or "",
            "delivery_text": _delivery_text(check),
            "delivery_postcode": (check or {}).get("delivery_postcode") or "",
            # The supplier's own dispatch estimate, in days. This is what the
            # handling time we promise Amazon is built from.
            "dispatch_days": (check or {}).get("dispatch_days"),
            "profit": None, "margin_pct": None, "roi_pct": None,
        }

        # WHAT IT WOULD EARN. Only when both numbers are real: a profit worked out
        # from a missing cost is a number that looks like an answer.
        if price is not None and landed is not None:
            if fee_amount is not None:
                # Amazon's real figure. Passed as a fee in pounds with the rate
                # at zero, so the ONE implementation of "what does this price
                # return" still does the arithmetic (Rule 12) rather than a
                # second copy of it appearing here.
                got = _pricing.achieved(price, landed, 0.0,
                                        rule["shipping_label"],
                                        rule["ads_margin"],
                                        other_fees=fee_amount)
                row["fee_basis"] = "actual"
            else:
                got = _pricing.achieved(price, landed, rule["referral_rate"],
                                        rule["shipping_label"], rule["ads_margin"])
                row["fee_basis"] = "estimated"
            row["profit"] = got.get("profit")
            row["margin_pct"] = got.get("margin_pct")
            row["roi_pct"] = got.get("roi_pct")
            # The sum, so the panel can lay it out instead of only showing the
            # answer and leaving the owner to work out where it came from.
            row["fee"] = got.get("fees")
            row["deductions"] = got.get("deductions")

        # HOW OLD THE READING IS. A price from four days ago is not a price you
        # can buy at, and the screen has to be able to say so.
        if check and now is not None:
            row["age_minutes"] = _sourcing.age_minutes(check, now)
            stale_after = rule.get("stale_after_hours")
            if row["age_minutes"] is not None and stale_after:
                row["stale"] = row["age_minutes"] > float(stale_after) * 60
            else:
                row["stale"] = False
        else:
            row["age_minutes"] = None
            row["stale"] = check is None

        out.append(row)

    # CHEAPEST FIRST, and dead links last whatever they cost.
    #
    # "arranged by low to high price". A dead link with no price would sort to the
    # front on a None, so the state leads the key: buyable, then unknown, then
    # dead. Within a group, the landed cost -- and a missing cost sorts last
    # rather than first, because an unknown price is not a cheap one.
    order = {BUYABLE: 0, UNKNOWN: 1, DEAD: 2}
    out.sort(key=lambda r: (order.get(r["state"], 3),
                            r["landed"] if r["landed"] is not None else 1e12,
                            str(r["url"])))
    # The rank AFTER sorting, so a screen can say "cheapest" without re-deriving
    # it and getting a different answer.
    for i, r in enumerate(out):
        r["rank"] = i + 1
        r["cheapest"] = (i == 0 and r["state"] == BUYABLE)
    return out


def summary(options):
    """One line about the set, for the alert and for the screen header.

    Returns {total, buyable, dead, unknown, all_dead, best_profit, best_url}.
    all_dead is what the out-of-stock notification is built on: it is True only
    when there IS at least one source and NONE of them can be bought from.
    """
    total = len(options or [])
    buyable = [o for o in (options or []) if o["state"] == BUYABLE]
    dead = [o for o in (options or []) if o["state"] == DEAD]
    unknown = [o for o in (options or []) if o["state"] == UNKNOWN]
    profits = [o["profit"] for o in buyable if o.get("profit") is not None]
    best = max(profits) if profits else None
    return {
        "total": total,
        "buyable": len(buyable),
        "dead": len(dead),
        "unknown": len(unknown),
        # EVERY source gone. Deliberately NOT true when a source merely could not
        # be read: "we could not look" is not "there is nowhere to buy it", and
        # raising an out-of-stock alert on a failed fetch would cry wolf every
        # time eBay had a bad minute.
        "all_dead": bool(total and not buyable and not unknown),
        "best_profit": best,
        "best_url": next((o["url"] for o in buyable
                          if o.get("profit") == best), "") if best is not None
                    else (buyable[0]["url"] if buyable else ""),
    }
