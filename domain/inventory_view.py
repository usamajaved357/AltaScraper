"""domain/inventory_view.py -- what you have, how fast it goes, when it runs out.

    "now start building the inventory feature same like orbit in our app"

ORBIT'S RULES, QUOTED FROM ORBIT
Every definition below that is in quotes was read off Orbit's own tooltips
during the 18 Aug 2026 capture (orbit_inventory/tooltips.md). Where this module
departs from Orbit it says so and why -- guessing at someone else's arithmetic
and presenting it as theirs is how a rebuild inherits a bug nobody can find.

    "display total units = FBA + AWD + 3PL + verified inbound"
    "Current Velocity -- Average units sold per day over the current 30-day
     window. Used as the default demand signal in inventory and forecasting."
    "DOS = displayed total units / current daily velocity"
    "COGS value = displayed units x resolved cost per unit"
    "Status -- Operational replenishment state for the row based on cover and
     planner context. Safe, watch, order soon, order now, and stockout likely
     are ordered from healthiest to most urgent."
    "Review queue -- Filtered rows that are not fully safe and therefore deserve
     operator review. Source gaps count missing AWD, 3PL, or COGS data that
     weaken the decision quality."

WHERE THIS APP IS NOT ORBIT, AND WHY THE MODEL CHANGES

Measured across all six accounts on 18 Aug 2026: **zero FBA units**. Every
listing is merchant-fulfilled. There is no AWD, no 3PL and no inbound, because
there is no warehouse -- stock is bought from an eBay supplier when an order
arrives.

So Orbit's headline question, "how many units are sitting in the network", has
no meaning here, and copying its four-part unit split would produce three empty
columns and one that means something different from what its heading says.

The question that DOES matter for this business is: **when an order comes in,
can it be sourced in time?** That is answerable, because the repricer already
records every supplier's dispatch estimate -- 45 of jack_uk's SKUs have one,
averaging 3.8 days. Orbit cannot ask this at all; it has no supplier data.

So:

    on-hand      the quantity on the Amazon listing. NOT a warehouse count --
                 it is what has been PROMISED to Amazon, and the honest name
                 for it is "listed quantity". Named that way everywhere.
    cover        listed quantity / velocity, which is Orbit's DOS exactly.
    lead time    the supplier's dispatch estimate plus the handling buffer:
                 how long a replacement really takes to arrive.
    at risk      a SKU whose cover is shorter than its lead time. That is the
                 one that hurts: it will run out before more can be got.

THE HONESTY RULES, WHICH ARE THE SAME ONES THE REST OF THIS APP FOLLOWS

  * No velocity is not a velocity of zero. A SKU with no sales in the window
    has `velocity=None`, not 0, and gets no DOS at all -- dividing by zero
    would report infinite cover on a product nobody buys.
  * No cost is not a cost of zero (domain/cogs.py). An uncosted SKU contributes
    nothing to the value total and is COUNTED in `uncosted`, so the figure can
    say what it does not cover.
  * A SKU whose first ever order is inside the window is marked `provisional`:
    two sales in three days is not 0.67 a day sustained, and a reorder built on
    it would be built on a fortnight of nothing.
"""

import datetime as _dt

# Orbit's window, quoted: "the current 30-day window".
WINDOW_DAYS = 30

# The five states, "ordered from healthiest to most urgent" -- Orbit's words and
# Orbit's order. Kept identical so the two screens can be read side by side.
SAFE = "safe"
WATCH = "watch"
ORDER_SOON = "order soon"
ORDER_NOW = "order now"
STOCKOUT = "stockout likely"
UNKNOWN = "unknown"

STATUS_ORDER = [SAFE, WATCH, ORDER_SOON, ORDER_NOW, STOCKOUT, UNKNOWN]

# What each state means, in the app's own words, for the legend and the tooltip.
STATUS_MEANING = {
    SAFE: "Cover is comfortably longer than it takes to get more.",
    WATCH: "Still covered, but the margin over the restock time is thinning.",
    ORDER_SOON: "Cover is approaching the restock time. Order in the next few days.",
    ORDER_NOW: "Cover is barely longer than the restock time. Order today.",
    STOCKOUT: "It will run out before more can arrive.",
    UNKNOWN: "Not enough to judge — no sales in the window, or no quantity.",
}

# THE THRESHOLDS, AS MULTIPLES OF THE RESTOCK TIME RATHER THAN FLAT DAYS.
#
# INFERRED, not Orbit's. Orbit states the five names and their order but never
# states its cut-offs, and the handover is explicit that an inferred formula
# must be labelled as one rather than presented as theirs.
#
# Multiples rather than days because a fixed "order at 14 days" is wrong in both
# directions here: a supplier who dispatches next day needs far less warning
# than one who takes ten. Cover is compared against the time it actually takes
# to replace the unit.
RATIO_SAFE = 3.0        # three times the lead time or better
RATIO_WATCH = 2.0
RATIO_SOON = 1.5
RATIO_NOW = 1.0         # below 1.0 it runs out before stock arrives

# Used when a SKU has no supplier on record, so no real lead time is known.
# Deliberately a stated assumption rather than a silent one; every row built
# with it carries lead_known=False and the screen says so.
ASSUMED_LEAD_DAYS = 7


def _f(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _i(v):
    f = _f(v)
    return None if f is None else int(f)


def status_for(cover_days, lead_days):
    """One SKU's replenishment state. Orbit's five names, this app's thresholds.

    `cover_days` is how long the listed quantity lasts at the current velocity.
    `lead_days` is how long a replacement takes to arrive.
    """
    if cover_days is None or lead_days is None:
        return UNKNOWN
    if lead_days <= 0:
        lead_days = 1.0
    r = cover_days / float(lead_days)
    if r >= RATIO_SAFE:
        return SAFE
    if r >= RATIO_WATCH:
        return WATCH
    if r >= RATIO_SOON:
        return ORDER_SOON
    if r >= RATIO_NOW:
        return ORDER_NOW
    return STOCKOUT


# A DAY THE SHELF WAS EMPTY IS NOT A DAY NOBODY WANTED IT.
#
# Velocity was units divided by the whole window, so a product that was out of
# stock for twenty of thirty days reported a third of its real rate -- and that
# rate is what days-of-cover and the reorder quantity are built on. The app was
# therefore under-ordering exactly the products that keep running out, and doing
# it more the worse the stockout was.
#
# stock_daily records qty per SKU per day, so the days it WAS sellable can be
# counted rather than assumed. Two rules keep it honest:
#
#   MIN_OBSERVED_DAYS   Below this much recorded history the adjustment is not
#                       made at all. It began recording on 20 Aug 2026, so for
#                       the first few weeks there is not enough to divide by and
#                       a thin denominator would INFLATE the rate -- the mirror
#                       of the bug being fixed.
#
#   the same days both   When the adjustment IS made, the units counted are only
#   sides               those sold on days that were both recorded and in stock.
#                       Dividing thirty days of sales by ten in-stock days would
#                       treble the answer. Numerator and denominator describe the
#                       same days or the figure means nothing.
#
# Which basis was used is returned, never hidden: a reorder built on one is not
# the same promise as a reorder built on the other.
MIN_OBSERVED_DAYS = 7


def _instock_days(conn, workspace_id, marketplace, start, end):
    """(days recorded at all, {sku: [dates it was in stock]}) for the window."""
    days_seen = set()
    per_sku = {}
    for r in conn.execute(
            "SELECT date, sku, qty FROM stock_daily "
            "WHERE workspace_id=? AND marketplace=? AND date>=? AND date<=?",
            (workspace_id, marketplace, start, end)):
        d = str(r["date"] or "")
        if not d:
            continue
        days_seen.add(d)
        try:
            q = float(r["qty"] or 0)
        except (TypeError, ValueError):
            q = 0.0
        if q > 0:
            per_sku.setdefault(str(r["sku"] or ""), set()).add(d)
    return days_seen, per_sku


def velocity_map(config_path, workspace_id, marketplace, days=WINDOW_DAYS,
                 today=None):
    """{sku: {units, velocity, orders, first_order, provisional, ...}}.

    Orbit's definition, quoted: "Average units sold per day over the current
    30-day window." -- and its inventory agent's correction to it, also quoted:
    "OOS days are excluded from the pace calculation... We do not count an
    out-of-stock day as a zero-sales day, so it does not understate true
    demand."

    Where there is not enough stock history to exclude anything, this divides by
    the WINDOW, not by the days since the first sale. A SKU that sold twice in
    its first three days is not selling 0.67 a day -- it has sold twice.
    Dividing by three would triple every new product's velocity and every
    reorder built on it. Those rows are flagged `provisional` instead, so the
    screen can say the figure is thin rather than quietly inflating it.

    Extra fields, so a reader can see which rate they are looking at:
        velocity_basis   "in-stock days" or "window"
        in_stock_days    days recorded AND sellable, when that basis was used
        observed_days    days of stock history found in the window
        oos_days         recorded days the shelf was empty
    """
    from data import db as _db

    out = {}
    end = today or _dt.date.today()
    start = end - _dt.timedelta(days=int(days))
    try:
        conn = _db.get_db(config_path)
        rows = conn.execute(
            "SELECT sku, SUM(units) u, COUNT(DISTINCT order_id) n, "
            "       MIN(substr(purchase_date,1,10)) first_in_window "
            "FROM order_lines "
            "WHERE workspace_id=? AND marketplace=? AND IFNULL(sku,'')<>'' "
            "  AND lower(IFNULL(status,'')) NOT IN ('canceled','cancelled') "
            "  AND substr(purchase_date,1,10) >= ? "
            "  AND substr(purchase_date,1,10) <= ? "
            "GROUP BY sku", (workspace_id, marketplace,
                             start.isoformat(), end.isoformat())).fetchall()
        # EVER, not just in the window -- that is what says whether a SKU is new
        # or simply having a quiet month, and they need different treatment.
        ever = {}
        for r in conn.execute(
                "SELECT sku, MIN(substr(purchase_date,1,10)) f FROM order_lines "
                "WHERE workspace_id=? AND marketplace=? AND IFNULL(sku,'')<>'' "
                "GROUP BY sku", (workspace_id, marketplace)):
            ever[str(r["sku"])] = r["f"]
        # Units by SKU and DAY, needed only to keep both sides of the division
        # describing the same days.
        by_day = {}
        for r in conn.execute(
                "SELECT sku, substr(purchase_date,1,10) d, SUM(units) u "
                "FROM order_lines "
                "WHERE workspace_id=? AND marketplace=? AND IFNULL(sku,'')<>'' "
                "  AND lower(IFNULL(status,'')) NOT IN ('canceled','cancelled') "
                "  AND substr(purchase_date,1,10) >= ? "
                "  AND substr(purchase_date,1,10) <= ? "
                "GROUP BY sku, d", (workspace_id, marketplace,
                                    start.isoformat(), end.isoformat())):
            by_day.setdefault(str(r["sku"]), {})[str(r["d"])] = _i(r["u"]) or 0
    except Exception:
        return out

    # ITS OWN try, DELIBERATELY. A fault reading the stock history must cost the
    # ADJUSTMENT, not every velocity in the account. Inside the block above, a
    # missing stock_daily returned {} -- so days-of-cover, the reorder quantity
    # and the whole Stock screen would have gone blank, silently, on any
    # deployment where that table had not been created yet. Caught by
    # test_velocity_oos.py's "no stock table at all is not an error".
    try:
        observed, instock = _instock_days(conn, workspace_id, marketplace,
                                          start.isoformat(), end.isoformat())
    except Exception:
        observed, instock = set(), {}

    enough = len(observed) >= MIN_OBSERVED_DAYS

    for r in rows:
        sku = str(r["sku"])
        units = _i(r["u"]) or 0
        first_ever = ever.get(sku) or r["first_in_window"]
        rec = {
            "units": units,
            "velocity": round(units / float(days), 4) if days else None,
            "velocity_basis": "window",
            "orders": _i(r["n"]) or 0,
            "first_order": first_ever,
            "observed_days": len(observed),
            "in_stock_days": None,
            "oos_days": None,
            # A product whose whole history is inside this window has not been
            # observed long enough for a daily rate to mean much.
            "provisional": bool(first_ever and first_ever >= start.isoformat()),
        }
        good = instock.get(sku) or set()
        if enough:
            rec["in_stock_days"] = len(good)
            rec["oos_days"] = len(observed) - len(good)
            if good:
                sold_then = sum(v for d, v in (by_day.get(sku) or {}).items()
                                if d in good)
                rec["velocity"] = round(sold_then / float(len(good)), 4)
                rec["velocity_basis"] = "in-stock days"
            # A SKU recorded as out of stock on EVERY observed day keeps the
            # window rate. There is no in-stock day to divide by, and reporting
            # no velocity would read as "nobody wants it" -- the very mistake
            # this is here to stop.
        out[sku] = rec
    return out


def lead_times(config_path, workspace_id, marketplace):
    """{sku: {days, known, source}} -- how long a replacement really takes.

    THE PART ORBIT CANNOT DO. It has no supplier data at all; this app has been
    reading every tracked supplier's dispatch estimate every few hours, and that
    is the number that decides whether a low stock level actually matters.

    The buffer is the repricer's own handling_buffer_days, so the lead time here
    and the handling time promised to buyers come from one setting (Rule 12).
    """
    from domain import source_repo as _repo
    from domain import sourcing as _sourcing

    out = {}
    try:
        pairs_by_sku = {}
        for row in _repo.enrolled(config_path, workspace_id, marketplace):
            sku = str(row.get("sku") or "")
            if not sku:
                continue
            pairs_by_sku[sku] = _repo.pairs_for(config_path, workspace_id,
                                                marketplace, sku)
    except Exception:
        return out

    for sku, pairs in pairs_by_sku.items():
        try:
            rule = _sourcing.rule_with_defaults(
                _repo.rule_for(config_path, workspace_id, marketplace, sku))
            buffer_days = int(rule.get("handling_buffer_days") or 0)
        except Exception:
            buffer_days = 0
        # THE FASTEST SUPPLIER THAT CAN ACTUALLY BE BOUGHT FROM. Not the
        # cheapest: this is a question about time, and a dead link's dispatch
        # estimate is not a promise anyone can keep.
        best = None
        for _s, chk in (pairs or []):
            if not chk:
                continue
            if str(chk.get("status") or "") != _sourcing.FETCHED:
                continue
            if chk.get("in_stock") is False:
                continue
            d = _i(chk.get("dispatch_days"))
            if d is None:
                continue
            if best is None or d < best:
                best = d
        if best is not None:
            out[sku] = {"days": best + buffer_days, "known": True,
                        "dispatch_days": best, "buffer_days": buffer_days,
                        "source": "supplier"}
    return out


def rows(config_path, workspace_id, marketplace, overrides=None,
         catalogue=None, days=WINDOW_DAYS, today=None):
    """One row per listed SKU: what you have, how fast it goes, when it runs out.

    "Product-level operating ledger" is Orbit's phrase for this table and it is
    the right one -- every figure is about one SKU and the decision it needs.
    """
    from domain import catalogue as _cat
    from domain import cogs as _cogs

    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, workspace_id, marketplace) or {}
    except Exception:
        rec = {}
    items = rec.get("items") or []
    idx = catalogue if catalogue is not None else {}

    vel = velocity_map(config_path, workspace_id, marketplace, days, today)
    leads = lead_times(config_path, workspace_id, marketplace)

    out = []
    for it in items:
        sku = str(it.get("sku") or "").strip()
        if not sku:
            continue
        qty = _i(it.get("qty"))
        price = _f(it.get("price"))
        v = vel.get(sku) or {}
        speed = v.get("velocity")
        cost, cost_src = _cogs.resolve(overrides or {}, workspace_id, sku)

        # COVER. Orbit: "DOS = displayed total units / current daily velocity".
        # None, never infinity: a product nobody buys does not have infinite
        # cover, it has no meaningful cover at all.
        cover = None
        if qty is not None and speed:
            cover = round(qty / speed, 1)

        lead = leads.get(sku)
        lead_days = lead["days"] if lead else ASSUMED_LEAD_DAYS
        state = status_for(cover, lead_days)

        got = _cat.look(idx, sku)
        # WHAT IS MISSING, named. Orbit's review queue counts "source gaps ...
        # that weaken the decision quality"; these are ours.
        gaps = []
        if cost is None:
            gaps.append("no cost")
        if qty is None:
            gaps.append("no quantity")
        if speed is None:
            gaps.append("no sales in the window")
        if not lead:
            gaps.append("no supplier")

        out.append({
            "sku": sku,
            "asin": got.get("asin") or str(it.get("asin") or ""),
            "title": got.get("title") or str(it.get("title") or ""),
            "img": got.get("img") or "",
            "listed_qty": qty,
            "price": price,
            "units_sold": v.get("units"),
            "orders": v.get("orders"),
            "velocity": speed,
            # WHICH RATE THIS IS. A reorder built on "2 a day while it was on
            # the shelf" is not the same promise as one built on "0.67 a day
            # counting the three weeks it was unbuyable", and the difference is
            # threefold on a badly stocked SKU. See velocity_map.
            "velocity_basis": v.get("velocity_basis") or "window",
            "in_stock_days": v.get("in_stock_days"),
            "oos_days": v.get("oos_days"),
            "observed_days": v.get("observed_days"),
            "provisional": bool(v.get("provisional")),
            "cover_days": cover,
            "lead_days": lead_days,
            "lead_known": bool(lead),
            "dispatch_days": (lead or {}).get("dispatch_days"),
            "buffer_days": (lead or {}).get("buffer_days"),
            "unit_cost": cost,
            "cost_source": cost_src,
            "value_at_cost": (None if (cost is None or qty is None)
                              else round(cost * qty, 2)),
            "status": state,
            # ALREADY OUT IS NOT ABOUT TO RUN OUT.
            #
            # Found while testing this against nestwell_goods: five SKUs sitting
            # at quantity 0 while still selling were reported as "runs out
            # 18 Aug", which was today. A prediction about something that has
            # already happened reads as a forecast you have time to act on, and
            # this is the opposite -- the listing is unbuyable right now.
            #
            # Orbit's five state names are kept as they are, so the two screens
            # can still be read side by side; this is a flag on top of the
            # state, and the screen says "out now" instead of a date.
            "already_out": bool(qty is not None and qty <= 0 and speed),
            "gaps": gaps,
            "fulfilment": str(it.get("fulfillment") or ""),
            "listing_status": str(it.get("status") or ""),
            # WHEN IT RUNS OUT, as a date rather than a number of days. "Aug 24"
            # is actionable in a way "6.2" is not.
            "runs_out": (None if cover is None else
                         ((today or _dt.date.today())
                          + _dt.timedelta(days=int(cover))).isoformat()),
        })

    # Most urgent first, then by the money at stake. The whole point of the
    # screen is that the top of it is the work.
    rank = {s: i for i, s in enumerate(STATUS_ORDER)}
    out.sort(key=lambda r: (rank.get(r["status"], 99),
                            -((r["velocity"] or 0) * (r["price"] or 0))))
    return out


def cockpit(rows_in, today=None):
    """The banner and the stat cards, from the rows the table is already drawing.

    Computed FROM the rows rather than by a second pass over the data, so the
    headline and the table can never disagree -- which is the fault this app has
    had to fix on three other screens.
    """
    day = today or _dt.date.today()
    rows_in = rows_in or []

    critical = [r for r in rows_in if r["status"] in (ORDER_NOW, STOCKOUT)]
    valued = [r for r in rows_in if r["value_at_cost"] is not None]
    covered = [r for r in rows_in if r["cover_days"] is not None]
    review = [r for r in rows_in if r["gaps"]]

    units = sum((r["listed_qty"] or 0) for r in rows_in)
    value = round(sum(r["value_at_cost"] for r in valued), 2)

    # REVENUE AT RISK.
    #
    # INFERRED. Orbit shows the figure ("$141K / 4.5K risky units") but never
    # states how it gets it. This one is: for every SKU that runs out before more
    # can arrive, the sales it would have made during the gap.
    #
    #     days short   = lead time - cover
    #     units missed = velocity x days short
    #     at risk      = units missed x selling price
    #
    # It is a forecast and is labelled as one on screen. It is deliberately NOT
    # the value of the whole SKU: losing three days of sales is not losing the
    # product.
    at_risk_units = 0.0
    at_risk_value = 0.0
    for r in critical:
        if r["cover_days"] is None or not r["velocity"]:
            continue
        short = max(0.0, float(r["lead_days"]) - float(r["cover_days"]))
        missed = r["velocity"] * short
        at_risk_units += missed
        if r["price"]:
            at_risk_value += missed * r["price"]

    # THE NEXT ONE TO GO. Orbit puts this in the banner and it is the single
    # most useful line on the screen: a date, not a count.
    # ONES ALREADY OUT COME FIRST, because "runs out on the 20th" is a warning
    # and "has been unbuyable since some point before now" is a fact. Within
    # each group the biggest seller leads -- a product selling 22 a month being
    # out matters more than one that sold once.
    out_now = sorted([r for r in rows_in if r.get("already_out")],
                     key=lambda r: -(r["velocity"] or 0))
    soonest = None
    if out_now:
        soonest = out_now[0]
    else:
        for r in covered:
            d = r["runs_out"]
            if d and (soonest is None or d < soonest["runs_out"]):
                soonest = r

    return {
        "as_at": day.isoformat(),
        "skus": len(rows_in),
        "critical": len(critical),
        "critical_skus": [r["sku"] for r in critical[:20]],
        "listed_units": units,
        "value_at_cost": value,
        "valued_skus": len(valued),
        "uncosted_skus": len(rows_in) - len(valued),
        # Orbit calls this AVG COVER. Only over SKUs that HAVE a cover: averaging
        # in the ones with no sales would report a number about products nobody
        # is buying.
        "avg_cover_days": (round(sum(r["cover_days"] for r in covered)
                                 / len(covered), 1) if covered else None),
        "covered_skus": len(covered),
        "at_risk_units": int(round(at_risk_units)),
        "at_risk_value": round(at_risk_value, 2),
        "review_queue": len(review),
        "next_stockout": (None if not soonest else {
            "sku": soonest["sku"], "title": soonest["title"],
            "date": soonest["runs_out"], "cover_days": soonest["cover_days"],
            "already_out": bool(soonest.get("already_out"))}),
        # How many are unbuyable RIGHT NOW. Separate from `critical`, which
        # includes the ones that still have stock but not enough of it.
        "out_now": len(out_now),
        "out_now_skus": [r["sku"] for r in out_now[:20]],
        "window_days": WINDOW_DAYS,
    }


def to_order(rows_in, horizon_days=30, today=None):
    """What to order, how many, and by when. Orbit's Actions tab.

        "Approval Queue -- Primary execution system of record for Steven
         inventory actions."  (quoted)

    Orbit's version proposes purchase orders and can execute them behind
    approval gates. THIS ONE ONLY EVER PROPOSES. Nothing here places an order,
    messages a supplier or touches Amazon -- see the module docstring and
    CLAUDE.md Rule 8. It is a list to work from.

    HOW MANY. Enough to cover the restock time plus `horizon_days` of selling,
    less what is already listed:

        need = velocity x (lead_days + horizon_days) - listed_qty

    INFERRED, and stated rather than hidden: Orbit does not publish its reorder
    quantity rule. The shape is the standard one -- cover the lead time so you
    do not run out while waiting, plus a horizon so you are not ordering again
    next week.

    BY WHEN. The last day an order can be placed and still arrive before the
    stock runs out: runs_out minus the lead time. A date in the past means it
    is already too late to avoid a gap, which is worth saying out loud.
    """
    day = today or _dt.date.today()
    out = []
    for r in (rows_in or []):
        if not r.get("velocity"):
            continue                     # nothing to forecast from
        if r["status"] not in (ORDER_NOW, STOCKOUT, ORDER_SOON, WATCH):
            continue
        lead = float(r.get("lead_days") or ASSUMED_LEAD_DAYS)
        qty = int(r.get("listed_qty") or 0)
        need = r["velocity"] * (lead + float(horizon_days)) - qty
        if need <= 0:
            continue
        units = int(round(need + 0.4999))     # never round a shortfall down
        cost = r.get("unit_cost")
        cover = r.get("cover_days")
        # The last day this can be ordered and still land before the shelf is
        # empty. Negative means the gap is already unavoidable.
        days_left = None if cover is None else round(cover - lead, 1)
        out.append({
            "sku": r["sku"], "asin": r.get("asin"), "title": r.get("title"),
            "img": r.get("img"), "status": r["status"],
            "already_out": bool(r.get("already_out")),
            "listed_qty": qty, "velocity": r["velocity"],
            "cover_days": cover, "lead_days": lead,
            "lead_known": bool(r.get("lead_known")),
            "units": units,
            "unit_cost": cost,
            "spend": (None if cost is None else round(cost * units, 2)),
            "order_by": (None if days_left is None else
                         (day + _dt.timedelta(days=int(days_left))).isoformat()),
            "days_left": days_left,
            "late": bool(days_left is not None and days_left < 0),
            "horizon_days": horizon_days,
            "provisional": bool(r.get("provisional")),
            "why": ("It is out of stock and still selling."
                    if r.get("already_out") else
                    "%.1f days of cover against a %d day restock."
                    % (cover or 0, int(lead))),
        })
    # Most urgent first: already out, then least time left, then FASTEST SELLER.
    #
    # The tiebreak is velocity, not spend. Sorting by money buried the worst
    # problem on the real data: nestwell's ceiling fan sells 0.73 a day and
    # needs 28 units, but it has no cost recorded, so `spend` was None -> 0 and
    # it sorted BELOW four products selling one unit a month. A figure being
    # unknown must never make a row look unimportant -- the same rule that
    # governs missing costs everywhere else in this app.
    out.sort(key=lambda x: (not x["already_out"],
                            x["days_left"] if x["days_left"] is not None else 1e9,
                            -(x["velocity"] or 0)))
    return out


def forecast(rows_in, horizons=(30, 60, 90, 180)):
    """Projected burn. Orbit's Forecasting tab, quoted:

        "Inventory Projections -- Projects future inventory burn by combining
         current stock, forecast demand, and dated inbound arrivals."

    No inbound here, because there is none -- see the module docstring. So it
    combines the two things that do exist: what is listed, and how fast it goes.

    Per horizon: how many units will sell, how many of those are covered by
    stock already listed, what the shortfall is, and what that shortfall would
    cost to buy. Straight-line at the current rate, which is stated on screen --
    it is a projection, not a seasonal model, and pretending otherwise on 30
    days of history would be inventing precision.
    """
    out = []
    for h in horizons:
        units = short = 0.0
        cost = 0.0
        skus_short = 0
        priced = True
        for r in (rows_in or []):
            v = r.get("velocity")
            if not v:
                continue
            will_sell = v * h
            units += will_sell
            have = float(r.get("listed_qty") or 0)
            gap = max(0.0, will_sell - have)
            if gap > 0:
                short += gap
                skus_short += 1
                c = r.get("unit_cost")
                if c is None:
                    priced = False
                else:
                    cost += c * gap
        out.append({
            "days": h,
            "units_selling": int(round(units)),
            "units_short": int(round(short)),
            "skus_short": skus_short,
            "cost_to_cover": round(cost, 2),
            # Whether that cost covers every short SKU or only the priced ones.
            # A buying budget that quietly omits a product is worse than none.
            "cost_complete": priced,
        })
    return out


def counts(rows_in):
    """How many SKUs are in each state, for the legend and the filter chips."""
    out = {s: 0 for s in STATUS_ORDER}
    for r in (rows_in or []):
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out
