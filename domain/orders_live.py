"""domain/orders_live.py -- today, so far.

WHY THIS EXISTS AT ALL
The Sales & Traffic report never has today and is often still revising
yesterday. That is fine for a 30-day grid and useless for the one question
people actually open a dashboard to ask: how are we doing right now. The Orders
API answers it, because orders appear there within minutes of being placed.

WHAT IT IS NOT
It is not the same number as the report, and it never will be. Orders here are
counted the moment they are placed; the report counts them after Amazon has
settled what an order finally was. Today's figure will move, and yesterday's
figure from here will not match yesterday's figure from the report. Both are
right. They are answers to different questions, which is why this is shown as
"today so far" beside the grid rather than as another column inside it.

TIMEZONE IS NOT A DETAIL
"Today" means today in the MARKETPLACE, not on the server. A UK seller's day
starts in London; Amazon's US reporting day runs on Pacific time. Reading the
server clock would start the day at the wrong hour, and every morning the figure
would be wrong by however far Sahiwal is from London -- five hours of orders
missing or counted twice.

PENDING ORDERS HAVE NO TOTAL
Amazon withholds the money on an order until it leaves Pending. Those orders are
counted as orders, but contribute nothing to revenue, and the reply says how
many so a low revenue-per-order can be explained rather than doubted.
"""
import datetime as _dt

# Amazon reports each marketplace on its own clock. These are the reporting
# zones, not the countries' capitals -- US Seller Central reports on Pacific.
_TZ = {
    "US": "America/Los_Angeles", "CA": "America/Los_Angeles",
    "MX": "America/Los_Angeles", "BR": "America/Sao_Paulo",
    "UK": "Europe/London", "GB": "Europe/London", "IE": "Europe/Dublin",
    "DE": "Europe/Berlin", "FR": "Europe/Paris", "IT": "Europe/Rome",
    "ES": "Europe/Madrid", "NL": "Europe/Amsterdam", "SE": "Europe/Stockholm",
    "PL": "Europe/Warsaw", "BE": "Europe/Brussels", "TR": "Europe/Istanbul",
    "AE": "Asia/Dubai", "SA": "Asia/Riyadh", "EG": "Africa/Cairo",
    "IN": "Asia/Kolkata", "SG": "Asia/Singapore", "JP": "Asia/Tokyo",
    "AU": "Australia/Sydney",
}

# Orders in these states are not sales. CANCELED is spelled Amazon's way.
_DEAD = ("canceled", "cancelled")

MAX_PAGES = 10          # a very busy day; beyond this the figure is reported partial


def marketplace_zone(marketplace):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(_TZ.get(str(marketplace).upper(), "UTC"))
    except Exception:
        return _dt.timezone.utc


def day_start(marketplace, days_ago=0):
    """Midnight in the marketplace's own timezone, as an aware datetime."""
    tz = marketplace_zone(marketplace)
    now = _dt.datetime.now(tz)
    d = (now - _dt.timedelta(days=int(days_ago))).date()
    return _dt.datetime(d.year, d.month, d.day, tzinfo=tz)


def _iso(dt):
    return dt.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload(resp):
    return resp.payload if hasattr(resp, "payload") else resp


def _amount(order):
    tot = order.get("OrderTotal") or {}
    try:
        return float(tot.get("Amount") or 0.0), str(tot.get("CurrencyCode") or "")
    except (TypeError, ValueError):
        return 0.0, ""


def summarise(orders):
    """Orders -> the numbers a person wants. Pending counted, but not banked."""
    out = {"orders": 0, "units": 0, "revenue": 0.0, "pending": 0,
           "cancelled": 0, "currency": ""}
    for o in orders or []:
        status = str(o.get("OrderStatus") or "").lower()
        if status in _DEAD:
            out["cancelled"] += 1
            continue
        out["orders"] += 1
        try:
            out["units"] += int(o.get("NumberOfItemsShipped") or 0) \
                          + int(o.get("NumberOfItemsUnshipped") or 0)
        except (TypeError, ValueError):
            pass
        amt, cur = _amount(o)
        if amt:
            out["revenue"] = round(out["revenue"] + amt, 2)
            if cur and not out["currency"]:
                out["currency"] = cur
        elif status == "pending":
            # Amazon withholds the total until an order leaves Pending. Counted
            # as an order, worth nothing yet, and declared so the gap is
            # explained rather than looking like missing money.
            out["pending"] += 1
    return out


def fetch_since(marketplace, marketplace_id, creds, since, until=None,
                max_pages=MAX_PAGES):
    """Orders created since a moment. Returns (orders, truncated)."""
    from sp_api.api import Orders
    from sp_api.base import Marketplaces
    mkt = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.US
    oc = Orders(credentials=creds, marketplace=mkt)

    kw = {"CreatedAfter": _iso(since),
          "MarketplaceIds": [marketplace_id] if marketplace_id else [mkt.marketplace_id]}
    if until:
        kw["CreatedBefore"] = _iso(until)

    got, token, pages = [], None, 0
    while pages < int(max_pages):
        resp = oc.get_orders(**kw) if not token else oc.get_orders(NextToken=token, **{
            "MarketplaceIds": kw["MarketplaceIds"]})
        pay = _payload(resp) or {}
        got.extend(pay.get("Orders") or [])
        pages += 1
        token = pay.get("NextToken")
        if not token:
            return got, False
    return got, True


def by_day(marketplace, marketplace_id, creds, days=5):
    """Orders per day for the last `days` days, from the ORDERS API.

    WHY THIS EXISTS: "but in amazon i am able to see the sales from yesterday
    accurately, why not here".

    Because Seller Central reads this feed and the Sales screen was reading the
    other one. Amazon publishes the same trade twice:

        Orders API                live, within minutes, dated by ORDER date
        Sales & Traffic report    a day or two behind, dated by ORDER date

    Both count an order on the day it was placed, so they are the SAME
    measurement -- the report is the settled, aggregated version that arrives
    later. That is what makes it safe to fill the report's missing tail from
    here, and it is not the same thing at all as mixing in the finance feed,
    which is dated by when the money moved and belongs to different days.

    Bucketed by the MARKETPLACE'S OWN date, not UTC and not the browser's: an
    order placed at 11pm on the 14th in London is a sale on the 14th, and this
    app is run from a timezone five hours ahead of it.

    -> {"days": {"2026-08-14": {orders, units, revenue}}, "currency", "truncated"}
    """
    days = max(1, min(int(days or 1), 30))
    since = day_start(marketplace, days_ago=days - 1)
    orders, truncated = fetch_since(marketplace, marketplace_id, creds, since)

    tz = marketplace_zone(marketplace)
    out, currency = {}, ""
    for o in orders or []:
        status = str(o.get("OrderStatus") or "").lower()
        if status in _DEAD:
            continue
        raw = str(o.get("PurchaseDate") or "")
        if not raw:
            continue
        try:
            # Amazon sends UTC with a Z; Python wants +00:00.
            dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            key = dt.astimezone(tz).date().isoformat()
        except Exception:
            continue
        d = out.setdefault(key, {"orders": 0, "units": 0, "revenue": 0.0})
        d["orders"] += 1
        try:
            d["units"] += int(o.get("NumberOfItemsShipped") or 0) \
                        + int(o.get("NumberOfItemsUnshipped") or 0)
        except (TypeError, ValueError):
            pass
        amt, cur = _amount(o)
        if amt:
            d["revenue"] = round(d["revenue"] + amt, 2)
            if cur and not currency:
                currency = cur
    return {"days": dict(sorted(out.items())), "currency": currency,
            "truncated": bool(truncated),
            "since": since.date().isoformat()}


def today(marketplace, marketplace_id, creds, compare=True):
    """Today so far, and the same slice of yesterday for honest comparison.

    The comparison stops at the SAME TIME of day, not at yesterday's total.
    Comparing 10am today against a full day yesterday shows a collapse every
    morning and a recovery every evening, neither of which happened.
    """
    start = day_start(marketplace, 0)
    now = _dt.datetime.now(marketplace_zone(marketplace))
    orders, truncated = fetch_since(marketplace, marketplace_id, creds, start)
    out = {"ok": True, "today": summarise(orders), "as_at": _iso(now),
           "day_started": _iso(start), "truncated": truncated,
           "timezone": str(marketplace_zone(marketplace))}

    if compare:
        y_start = day_start(marketplace, 1)
        y_until = y_start + (now - start)          # the same elapsed slice
        y_orders, y_trunc = fetch_since(marketplace, marketplace_id, creds,
                                        y_start, until=y_until)
        out["yesterday"] = summarise(y_orders)
        out["yesterday_truncated"] = y_trunc
        out["compared_to"] = "the same time yesterday"
        for k in ("orders", "units", "revenue"):
            a, b = out["today"].get(k), out["yesterday"].get(k)
            out.setdefault("delta_pct", {})[k] = (
                round((a - b) / b * 100, 1) if b else None)
    return out
