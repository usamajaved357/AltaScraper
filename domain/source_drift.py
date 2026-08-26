"""domain/source_drift.py -- what we THINK a unit costs vs what it costs NOW.

Two different numbers are in play, and neither is wrong:

  COGS          what the stock cost. domain/cogs.py resolves it: a manual
                override if someone typed one, otherwise the number the
                generator baked into the SKU when it created the listing.
                Backward-looking. It is what every profit figure subtracts.

  landed cost   what the supplier is charging RIGHT NOW, from the last reading
                domain/source_fetch.py took: price + postage. Forward-looking.
                It is what domain/sourcing.py prices from, and it never consults
                COGS to do it.

They start life equal, because the generator writes the source cost it just read
into the SKU. Then the supplier changes their price and only one of the two
moves. Nothing was misconfigured and nothing failed -- they simply answer
different questions, and there is no moment at which either is told about the
other. So the gap opens silently and stays open, which is exactly the kind of
number that is believed for months.

The gap MATTERS in a specific direction. These are FBM listings bought when they
sell, so a unit sold today costs today's supplier price, not the price the SKU
was named after. If the supplier has gone UP and COGS has not, every profit
figure for that SKU is overstated by the difference, on every unit, and the
listing looks like the healthy one worth ordering more of.

NOTHING HERE DECIDES ANYTHING
This only compares and reports. The repricer's decisions do not consult it, and
adding it changed no price. It exists so a person can SEE the gap, which is the
whole of the fix at this stage -- see CLAUDE.md Rule 12: the cost is resolved by
domain/cogs.py and the landed cost by domain/sourcing.py, and this file
re-implements neither.
"""
from domain import cogs as _cogs
from domain import sourcing as _sourcing


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def landed_for(pairs, source_id=None):
    """The landed cost to compare against, and which source it came from.

    Prefers the source the decision actually chose, because that is the one the
    price was built from. When nothing was chosen -- every source unreadable, or
    the decision was held -- it falls back to the cheapest reading it CAN see, so
    the drift is still visible on exactly the rows where something is wrong.

    Returns (landed, source_id) and (None, None) when nothing is readable.
    """
    best = (None, None)
    for s, c in (pairs or []):
        cost = _sourcing.landed_cost(c)
        if cost is None:
            continue
        if source_id is not None and s.get("id") == source_id:
            return cost, s.get("id")
        if best[0] is None or cost < best[0]:
            best = (cost, s.get("id"))
    return best


def for_sku(overrides, workspace_id, sku, pairs, source_id=None):
    """The COGS/landed comparison for one SKU, as the screen needs it.

    Every field is None rather than 0 when unknown -- an unknown cost is not a
    free one, the same rule domain/cogs.py states for "0.00".
    """
    cost, csrc = _cogs.resolve(overrides, workspace_id, sku)
    landed, sid = landed_for(pairs, source_id)
    out = {"cogs": cost, "cogs_source": csrc, "landed": landed,
           "source_id": sid, "delta": None, "pct": None, "direction": ""}
    if cost is None or landed is None or cost <= 0:
        return out
    d = round(landed - cost, 2)
    out["delta"] = d
    out["pct"] = round(d / cost * 100.0, 1)
    # Named from the point of view of PROFIT, not of the number: a supplier
    # charging more is "worse", and that is the word the screen should use.
    out["direction"] = "worse" if d > 0 else ("better" if d < 0 else "flat")
    return out


def at_a_glance(pairs, current, rule, source_id=None, promo=None):
    """The row's headline facts, in one place.

    "i want to add some additional info which give me a glance view to be
     displayed on each sku, current source price, current my selling price on
     which the item will be sold if i receive an order and the profit margin and
     the roi i will generate on the sale. source units available, the shipping
     days of the supplier"

    Every figure is about the sale that would happen NOW -- the price Amazon is
    charging today against what the supplier charges today -- not the price the
    repricer would like it to be. Those are two different questions and the
    proposed price is already on the row; this is the one that says what an
    order arriving this minute would actually earn.

    Anything unobtainable is None rather than 0, and the screen leaves it blank.
    An unknown margin shown as 0% is a number someone would act on.
    """
    from listing import pricing as _pricing
    from domain import sourcing as _sourcing
    from domain import promotions as _promos

    out = {"source_price": None, "source_postage": None, "landed": None,
           "sell_price": None, "profit": None, "margin_pct": None,
           "roi_pct": None, "units_available": None, "dispatch_days": None,
           "handling_days": None, "in_stock": None, "fee": None,
           # Filled in only when a discount was actually measured on this SKU.
           "promo": None, "sell_price_promo": None, "profit_promo": None,
           "margin_pct_promo": None, "roi_pct_promo": None}

    chk = None
    for s, c in (pairs or []):
        if not c:
            continue
        if source_id is not None and s.get("id") == source_id:
            chk = c
            break
        if chk is None and _sourcing.landed_cost(c) is not None:
            chk = c
    if chk:
        out["source_price"] = _num(chk.get("price"))
        out["source_postage"] = _num(chk.get("shipping"))
        out["landed"] = _sourcing.landed_cost(chk)
        out["units_available"] = chk.get("available_qty")
        out["dispatch_days"] = chk.get("dispatch_days")
        out["in_stock"] = chk.get("in_stock")
        if out["dispatch_days"] is not None:
            try:
                # The same arithmetic decide() promises Amazon, not a second
                # copy of it (CLAUDE.md Rule 12) -- this report exists to say
                # what WILL happen, so a formula of its own would eventually
                # describe a handling time the repricer never sets.
                rule = _sourcing.rule_with_defaults(rule)
                out["handling_days"] = _sourcing.handling_days(
                    out["dispatch_days"], rule)
            except Exception:
                out["handling_days"] = None

    out["sell_price"] = _num((current or {}).get("price"))
    if out["sell_price"] is not None and out["landed"] is not None:
        r = _sourcing.rule_with_defaults(rule)
        got = _pricing.achieved(out["sell_price"], out["landed"], r["referral_rate"],
                                shipping_label=r["shipping_label"],
                                ads_margin=r["ads_margin"])
        out["profit"] = got.get("profit")
        out["margin_pct"] = got.get("margin_pct")
        out["roi_pct"] = got.get("roi_pct")
        out["fee"] = got.get("fees")

        # AND THE SAME SUM AGAIN WITH THE COUPON ON.
        #
        #     "show profit per unit when no promotion like coupon or discounts
        #      etc are applied and also show the profit when some coupons or
        #      promotions etc are applied ... also show roi and margin in both
        #      cases"
        #
        # Two figures, not one, because they answer different questions: the
        # first is what the listing is worth, the second is what it is actually
        # earning while a coupon runs. A single number hides whichever of those
        # you were not looking at.
        #
        # `promo` is measured from settled orders (domain/promotions.py) -- it is
        # never a setting read from Amazon, because Amazon does not expose one to
        # this app. Absent means no discount was measured, and the two figures
        # are then the same, which is the truth rather than a gap on the screen.
        if promo:
            after = _promos.apply_to(out["sell_price"], promo)
            got2 = _pricing.achieved(after, out["landed"], r["referral_rate"],
                                     shipping_label=r["shipping_label"],
                                     ads_margin=r["ads_margin"])
            out["promo"] = dict(promo)
            out["promo_note"] = _promos.describe(promo)
            out["sell_price_promo"] = after
            out["profit_promo"] = got2.get("profit")
            out["margin_pct_promo"] = got2.get("margin_pct")
            out["roi_pct_promo"] = got2.get("roi_pct")
    return out


def price_history(config_path, source_id, limit=12):
    """What this source has charged, oldest last, for a sparkline or a list.

    Readings that failed are kept rather than filtered out: a run of them is why
    a price looks unchanged for a week, and hiding them would make a stale
    number look like a stable one.
    """
    from domain import source_repo as _repo
    out = []
    for c in _repo.history(config_path, source_id, limit=limit):
        out.append({"at": c.get("checked_at"), "status": c.get("status"),
                    "price": _num(c.get("price")),
                    "shipping": _num(c.get("shipping")),
                    "landed": _sourcing.landed_cost(c),
                    "in_stock": c.get("in_stock")})
    return out


def moved(history):
    """(first, last, delta) across the readings we hold, ignoring the unreadable.

    This is drift WITHIN the supplier's own prices, which is a different question
    from drift against COGS: it answers "has this supplier moved since we started
    watching", and it only becomes interesting once there are a few readings.
    """
    seen = [h["landed"] for h in (history or []) if h.get("landed") is not None]
    if len(seen) < 2:
        return None, None, None
    first, last = seen[-1], seen[0]      # history() returns newest first
    return first, last, round(last - first, 2)
