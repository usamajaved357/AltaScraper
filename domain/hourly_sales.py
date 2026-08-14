"""domain/hourly_sales.py -- today's sales by the hour, and yesterday's beside it.

WHY THIS EXISTS, HAVING SAID IT COULD NOT BE BUILT
Orbit's Live Sales card is an hourly curve, and I said we could not match it
because Amazon's Sales & Traffic report is daily. That was the wrong place to
look. Its card says "Based on order dates", and orders carry a purchase
TIMESTAMP -- which the app already pulls. So the curve is derivable from data we
hold, without a new Amazon feed.

WHAT IT IS, AND WHAT IT IS NOT
Orders as PLACED, by the hour, in the account's own timezone. That is a
different measurement from everything on the settled Sales Report below it --
those are units shipped, dated when the money moved -- and the two will not tie
out. The card says so rather than letting the difference look like an error.

Cancellations are included as placed. An order cancelled an hour later still
happened at the hour it was placed, and quietly removing it would make the
morning look different depending on when you looked at the screen.

RUNNING TOTALS, not per-hour bars. Orbit's curve climbs across the day and
yesterday's runs the full 24 hours beside it, so "am I ahead of yesterday" is
answered by which line is higher at the same hour. Per-hour figures answer a
question nobody asks of this card.
"""
import datetime as _dt


def _parse(ts):
    """An Amazon ISO timestamp -> aware datetime, or None."""
    s = str(ts or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def _local(d, tz):
    """UTC -> the account's own day. A UK seller's midnight is not Amazon's."""
    if not tz:
        return d
    try:
        from zoneinfo import ZoneInfo
        return d.astimezone(ZoneInfo(tz))
    except Exception:
        return d


def _fields(o):
    """(purchase timestamp, amount, status) from either order shape.

    The app has two: the flattened one /orders/list hands the browser, and the
    raw SP-API one orders_live.fetch_since returns. Reading both here means the
    caller never has to convert, and a caller that converts is a caller that
    can convert wrongly.
    """
    ts = o.get("purchased") or o.get("PurchaseDate") or ""
    status = str(o.get("status") or o.get("OrderStatus") or "")
    amt = o.get("total")
    if amt in (None, ""):
        tot = o.get("OrderTotal") or {}
        amt = tot.get("Amount")
    try:
        amt = float(amt or 0)
    except (TypeError, ValueError):
        amt = 0.0
    return ts, amt, status


def curve(orders, tz="", now=None, statuses_to_skip=("Cancelled", "Canceled")):
    """-> {"today": [24 running totals], "yesterday": [...], "hours": [...]}.

    `orders` may be either shape the app produces -- see _fields. Anything
    without a usable timestamp is skipped rather than dropped into hour zero,
    which would put a spike at midnight every day.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    now_l = _local(now, tz)
    today = now_l.date()
    yday = today - _dt.timedelta(days=1)

    per = {today: [0.0] * 24, yday: [0.0] * 24}
    counts = {today: 0, yday: 0}
    for o in (orders or []):
        ts, amt, status = _fields(o)
        # A cancelled order is still an order that was placed; only statuses
        # the caller explicitly names are skipped.
        if status in (statuses_to_skip or ()):
            continue
        d = _parse(ts)
        if not d:
            continue
        dl = _local(d, tz)
        day = dl.date()
        if day not in per:
            continue
        per[day][dl.hour] += amt
        counts[day] += 1

    def running(day, upto):
        out, tot = [], 0.0
        for h in range(24):
            tot += per[day][h]
            # HOURS THAT HAVE NOT HAPPENED YET ARE NULL, NOT ZERO. A line that
            # runs flat along the axis to midnight says the day collapsed; a
            # line that stops says the day is still going. Yesterday runs the
            # full 24 because it did.
            out.append(round(tot, 2) if h <= upto else None)
        return out

    return {
        "hours": ["%02d:00" % h for h in range(24)],
        "today": running(today, now_l.hour),
        "yesterday": running(yday, 23),
        "today_orders": counts[today],
        "yesterday_orders": counts[yday],
        "today_total": round(sum(per[today]), 2),
        "yesterday_total": round(sum(per[yday]), 2),
        # Yesterday AT THE SAME HOUR, which is the only fair comparison to put
        # a percentage on. Against yesterday's full day, every morning would
        # look like a collapse.
        "yesterday_so_far": round(sum(per[yday][:now_l.hour + 1]), 2),
        "as_at_hour": now_l.hour,
        "timezone": tz or "UTC",
    }
