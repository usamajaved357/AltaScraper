"""domain/stock_metrics.py -- coverage, and how fast a thing really sells.

Built to the method Orbit's inventory agent described when asked for its exact
formulas, because the method is right and the difference it makes is large:

    available            = on hand + inbound
    in-stock rate        = share of days in the window the SKU was sellable
    OOS-adjusted pace    = mean daily units over IN-STOCK DAYS ONLY
    velocity trend       = (7-day pace - 30-day pace) / 30-day pace
    forecast demand 30d  = 30-day pace x 30
    days of cover        = on hand / 30-day pace
    stock gap 30d        = forecast demand - available

THE ADJUSTMENT IS THE WHOLE POINT. A flat units/days average counts every day
the product was out of stock as a day it sold nothing, which understates demand
by exactly the amount that matters -- the days you could have sold and had
nothing to sell. Excluding those days is what turns a sales figure into a
demand figure.

A COVERAGE SHORTFALL IS NOT A PURCHASE ORDER. The gap says what would run out
over the next thirty days at the current pace. It does not know a minimum order
quantity, a case pack, a lead time or what the money is doing, so it does not
say how much to buy. Orbit's own agent draws the same line and it is the honest
one.

WHERE IT REFUSES TO ANSWER

The pace needs to know which days the SKU was sellable, and that history only
exists from the day the app started recording it (see domain/stock_history.py).
Every figure carries the number of days it was actually computed over, and a
window with too little history returns "not enough history yet" rather than a
confident number built on three days.
"""
import datetime as _dt

from data import db as _db
from domain import stock_history as _sh

# Below this many known days in the window, a pace is noise wearing a decimal
# point. Two weeks of evidence is the least that says anything about a rate.
MIN_DAYS_FOR_PACE = 7


def _days(start, end):
    a = _dt.date.fromisoformat(start)
    b = _dt.date.fromisoformat(end)
    out = []
    while a <= b:
        out.append(a.isoformat())
        a += _dt.timedelta(days=1)
    return out


def _units_by_sku_day(config_path, workspace_id, marketplace, start, end):
    """Units ORDERED per SKU per day, from the orders the app already stores.

    order_lines is used rather than sales_daily because sales_daily is keyed by
    ASIN and stock is keyed by SKU -- and one ASIN can be several SKUs. Joining
    demand to stock through the wrong key is how a product looks well covered
    while one of its SKUs is empty.
    """
    conn = _db.get_db(config_path)
    out = {}
    try:
        cur = conn.execute(
            "SELECT sku, substr(purchase_date,1,10) d, SUM(COALESCE(units,0)) u "
            "FROM order_lines WHERE workspace_id=? AND marketplace=? "
            "  AND substr(purchase_date,1,10)>=? AND substr(purchase_date,1,10)<=? "
            "GROUP BY sku, d", (workspace_id, marketplace, start, end))
        for r in cur:
            if r["sku"]:
                out.setdefault(r["sku"], {})[r["d"]] = float(r["u"] or 0)
    except Exception:
        return {}
    return out


def _pace(days, in_stock, units_by_day):
    """Mean daily units over the in-stock days only. None when too few."""
    usable = [d for d in in_stock if d in days]
    if len(usable) < MIN_DAYS_FOR_PACE:
        return None, len(usable)
    total = sum(units_by_day.get(d, 0.0) for d in usable)
    return round(total / len(usable), 3), len(usable)


# A run of recent sellable days with no sales at all, at which point the
# thirty-day average is describing a past that has stopped.
QUIET_DAYS_FOR_STALE = 10


def _quiet_run(days, in_stock, units_by_day):
    """How many sellable days at the END of the window sold nothing.

    Counted over IN-STOCK days only, for the same reason the pace is: a day the
    product could not be bought is not a day nobody wanted it.
    """
    marks = set(in_stock)
    run = 0
    for d in reversed(days):
        if d not in marks:
            continue                     # out of stock -- says nothing either way
        if units_by_day.get(d, 0.0) > 0:
            break
        run += 1
    return run


def for_account(config_path, workspace_id, marketplace, window=30, today=None):
    """Every SKU's coverage picture, worst first. Reads only."""
    end = today or _dt.date.today().isoformat()
    start = (_dt.date.fromisoformat(end) - _dt.timedelta(days=window - 1)).isoformat()
    start7 = (_dt.date.fromisoformat(end) - _dt.timedelta(days=6)).isoformat()
    days30 = _days(start, end)
    days7 = _days(start7, end)

    cov = _sh.coverage(config_path, workspace_id, marketplace)
    stock = _sh.history(config_path, workspace_id, marketplace, start, end)
    units = _units_by_sku_day(config_path, workspace_id, marketplace, start, end)

    # Today's position comes from the latest reading we hold, not from an
    # average -- "how much is there" is a fact, not a trend.
    rows = []
    for sku, by_date in stock.items():
        latest_day = max(by_date.keys()) if by_date else ""
        on_hand = by_date.get(latest_day)
        on_hand = int(on_hand) if on_hand is not None else None
        # Merchant-fulfilled: there is no inbound-to-Amazon leg, and inventing
        # one would flatter every gap. Kept as a named zero so the arithmetic
        # below reads the same as Amazon's own.
        inbound = 0
        available = (on_hand or 0) + inbound

        marks = _sh.in_stock_days(by_date, days30)
        marks7 = _sh.in_stock_days(by_date, days7)
        u = units.get(sku, {})

        pace30, n30 = _pace(days30, marks["in_stock"], u)
        pace7, n7 = _pace(days7, marks7["in_stock"], u)

        known = len(marks["known"])
        oos = len(marks["oos"])
        in_stock_rate = round(100.0 * len(marks["in_stock"]) / known, 1) if known else None

        forecast = round(pace30 * 30, 1) if pace30 is not None else None
        cover = (round(on_hand / pace30, 1)
                 if (pace30 and on_hand is not None and pace30 > 0) else None)
        gap = round(forecast - available, 1) if forecast is not None else None
        trend = (round(100.0 * (pace7 - pace30) / pace30, 1)
                 if (pace7 is not None and pace30) else None)

        # IS THE PACE STILL DESCRIBING THE PRESENT?
        #
        # Orbit's inventory agent, asked where its own numbers would be
        # confidently wrong, named this first and named it precisely:
        #
        #     "A SKU being discontinued or replaced by a new ASIN. It will show
        #      low daysOfSupply and large stockGap30d because forecastDemand30d
        #      = 30d pace x 30. The dashboard still shows it as 'Order now' even
        #      if you intend to let it sell out. How to spot: if trend is -97%
        #      and daily units went 18,16,15... to 0 for the last week, the 30d
        #      pace is stale."
        #
        # That is the expensive direction to be wrong in. Every other error here
        # makes somebody look twice; this one tells them to BUY. A thirty-day
        # mean cannot tell a product that is selling from one that stopped
        # selling three weeks ago -- both leave the same average behind.
        #
        # Not a status of its own, and it does not clear the shortfall. The
        # shortfall is real arithmetic on real days. What is in doubt is whether
        # those days still describe next month, and only the owner knows whether
        # this listing is being retired.
        quiet = _quiet_run(days30, marks["in_stock"], u)
        stale = (quiet >= QUIET_DAYS_FOR_STALE
                 or (trend is not None and trend <= -80))

        # THE STATUS, and what it is allowed to mean.
        if on_hand is not None and available <= 0:
            status, why = "out_of_stock", "Nothing sellable right now."
        elif pace30 is None:
            status, why = "unknown", (
                "Not enough recorded history yet to say how fast it sells -- "
                "%d day(s) of the last %d are known." % (known, window))
        elif gap is not None and gap > 0:
            status, why = "needs_attention", (
                "At %.2f a day it would sell about %.0f in thirty days and there "
                "are %d." % (pace30, forecast, available))
        else:
            status, why = "ok", "Covered for the next thirty days at this pace."

        stale_why = ""
        if stale and status in ("needs_attention", "ok"):
            if quiet >= QUIET_DAYS_FOR_STALE:
                stale_why = ("It has been sellable for the last %d days and sold "
                             "none of them. The thirty-day average is being held "
                             "up by sales that have stopped, so the shortfall "
                             "below is probably describing a month that will not "
                             "repeat." % quiet)
            else:
                stale_why = ("Sales are down %.0f%% on the last seven days "
                             "against the thirty-day average. The shortfall "
                             "below is worked out from the thirty-day figure, "
                             "which the recent days no longer support."
                             % abs(trend))

        rows.append({
            "sku": sku, "asin": (by_date and "") or "",
            "on_hand": on_hand, "inbound": inbound, "available": available,
            "days_known": known, "oos_days": oos, "in_stock_rate": in_stock_rate,
            "pace_30d": pace30, "pace_30d_days": n30,
            "pace_7d": pace7, "pace_7d_days": n7,
            "velocity_trend_pct": trend,
            "forecast_demand_30d": forecast,
            "days_of_cover": cover,
            "stock_gap_30d": gap,
            "status": status, "why": why,
            # The shortfall stands; whether it still describes next month does
            # not. Named separately so a screen can mark the row without the
            # figures changing underneath it.
            "pace_is_stale": bool(stale_why),
            "stale_why": stale_why,
            "quiet_days": quiet,
        })

    order = {"out_of_stock": 0, "needs_attention": 1, "unknown": 2, "ok": 3}
    # A shortfall whose pace has gone quiet sorts BELOW the live ones. It stays
    # in the list -- it may well be a real problem -- but it should not sit at
    # the top of a reorder list looking urgent when the product has not sold
    # anything for a fortnight.
    rows.sort(key=lambda r: (order.get(r["status"], 9),
                             1 if r.get("pace_is_stale") else 0,
                             -(r["stock_gap_30d"] or 0)))

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    counts["stale_pace"] = sum(1 for r in rows if r.get("pace_is_stale"))

    # WHICH OF THESE ARE MEASUREMENTS AND WHICH ARE ESTIMATES.
    #
    #     Ava, on when it is willing to estimate at all:
    #     "No for financials ... Only labeled estimates are forward-looking
    #      inventory math: days-of-cover, stockout risk, restock suggestion --
    #      these ARE estimates by definition. I label them."
    #
    # That line is worth keeping. What a product HAS and what it DID are counted;
    # what it will do is arithmetic on an assumption that tomorrow looks like the
    # last thirty days. Printing both in the same typeface invites the second to
    # be trusted like the first.
    measured = ["on_hand", "available", "days_known", "oos_days",
                "in_stock_rate", "pace_30d", "pace_7d", "velocity_trend_pct"]
    estimated = ["forecast_demand_30d", "days_of_cover", "stock_gap_30d"]

    return {
        "ok": True, "window": window, "start": start, "end": end,
        "rows": rows, "counts": counts, "skus": len(rows),
        "history": cov,
        "measured": measured, "estimated": estimated,
        "estimate_note": ("Cover, thirty-day demand and the gap are ESTIMATES: "
                          "they assume the next thirty days look like the days "
                          "measured. What is on hand, what sold and how often "
                          "it was in stock are counted, not assumed."),
        # Said plainly wherever this is drawn: the pace is only as good as the
        # history behind it, and the history starts when recording started.
        "note": ("Stock levels are recorded each time the live catalogue "
                 "refreshes. There are %d day(s) so far%s. A pace needs at "
                 "least %d known in-stock days before it is reported."
                 % (cov["days"],
                    (", from %s" % cov["first"]) if cov["first"] else "",
                    MIN_DAYS_FOR_PACE)),
        "gap_is_not_a_po": ("The thirty-day gap is a coverage shortfall, not a "
                            "purchase order. It does not know your minimum "
                            "order quantity, case pack or lead time."),
        # HOW TO CATCH THIS SCREEN LYING, without taking its word for anything.
        #
        # Orbit's inventory agent was asked which single number to check by
        # hand each week to keep it honest, and the answer was the right one:
        # the pace, because everything else here is built on it. Repeating that
        # here rather than keeping it to ourselves -- a screen that tells you
        # how to audit it is worth more than one that asks to be believed.
        "how_to_check": ("Pick one SKU. Over the last thirty days count only "
                         "the days it was in stock, add up the units sold on "
                         "those days, and divide. That is the pace shown here. "
                         "If your figure and this one are far apart, either the "
                         "stock history or the order data is wrong -- and since "
                         "cover and the gap are both worked out from the pace, "
                         "everything else on this screen is wrong with it."),
        "stale_note": ("A pace can go stale: a product that sold well for three "
                       "weeks and nothing since still leaves a healthy "
                       "thirty-day average behind it, and would otherwise read "
                       "as 'order more'. Rows where that has happened are "
                       "marked and sorted below the live ones."),
    }
