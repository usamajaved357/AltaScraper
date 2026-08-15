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
    """OrderTotal -- what the BUYER paid, shipping included.

    Not the same thing as sales, and not what Seller Central calls Total Sales.
    Kept for the places that genuinely mean "what was charged"; anything
    reporting sales wants product_sales() below.
    """
    tot = order.get("OrderTotal") or {}
    try:
        return float(tot.get("Amount") or 0.0), str(tot.get("CurrencyCode") or "")
    except (TypeError, ValueError):
        return 0.0, ""


# One getOrderItems call per order, so this is bounded. Far above a normal day
# for this business; a bigger seller gets a partial figure that says it is
# partial rather than a wrong one that does not.
MAX_ITEM_LOOKUPS = 200


def order_items(marketplace, creds, order_ids, max_orders=MAX_ITEM_LOOKUPS):
    """The line items of each order: {order_id: [line, ...]}, and whether all fit.

    THE ONE PLACE THAT ASKS AMAZON WHAT WAS IN AN ORDER. The hourly page needed
    per-item detail (which ASIN, at what price, at what hour) and the Sales
    screen needs the per-order total of those same item prices; both were going
    to want their own copy of this loop, and two copies of "what did Amazon
    say this order contained" is how two screens come to disagree about one
    order.

    Each line: {asin, sku, title, units, price, currency}. `price` is ItemPrice
    -- the money for the goods, which is what Amazon calls ordered product sales
    and what the seller counts. It excludes shipping.
    """
    from sp_api.api import Orders
    from sp_api.base import Marketplaces
    mkt = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.US
    oc = Orders(credentials=creds, marketplace=mkt)

    ids = [str(i) for i in (order_ids or []) if i]
    complete = len(ids) <= int(max_orders)
    out = {}
    for oid in ids[:int(max_orders)]:
        try:
            r = oc.get_order_items(oid)
            pay = r.payload if hasattr(r, "payload") else r
            items = (pay or {}).get("OrderItems") or []
        except Exception:
            # Not recorded as an empty order: an order we could not read is not
            # an order worth nothing, and treating it as zero would quietly
            # understate the day. It is simply absent, and callers count it.
            continue
        lines = []
        for it in items:
            ip = it.get("ItemPrice") or {}
            try:
                qty = int(it.get("QuantityOrdered") or 0)
            except (TypeError, ValueError):
                qty = 0
            try:
                price = float(ip.get("Amount") or 0.0)
            except (TypeError, ValueError):
                price = 0.0
            lines.append({
                "asin": str(it.get("ASIN") or ""),
                "sku": str(it.get("SellerSKU") or ""),
                "title": str(it.get("Title") or ""),
                "units": qty,
                "price": price,
                "currency": str(ip.get("CurrencyCode") or ""),
            })
        out[oid] = lines
    return out, complete


def product_sales(marketplace, creds, orders, max_orders=MAX_ITEM_LOOKUPS):
    """Ordered product sales per order: {order_id: (amount, currency)}, + how many
    could not be read.

    WHY THIS EXISTS: the owner counted 89.97 for three orders and the app showed
    102.21. Both were right about different things -- 3 x 29.99 of goods, plus
    3 x 4.08 of shipping. Amazon's own Total Sales, the Sales & Traffic report's
    ordered_sales, and what a seller means by "my sales" are all the FIRST one.

    This matters beyond the label. The Sales chart fills days the report has not
    delivered from the Orders API; with OrderTotal there, a filled day and a
    reported day were measuring different things and the bars were not
    comparable to each other.
    """
    ids = [str(o.get("AmazonOrderId") or "") for o in (orders or [])
           if str(o.get("OrderStatus") or "").lower() not in _DEAD]
    ids = [i for i in ids if i]
    items, complete = order_items(marketplace, creds, ids, max_orders=max_orders)
    out = {}
    for oid in ids:
        lines = items.get(oid)
        if lines is None:
            continue
        amt = round(sum(float(l.get("price") or 0.0) for l in lines), 2)
        cur = next((l.get("currency") for l in lines if l.get("currency")), "")
        out[oid] = (amt, cur)
    return out, len(ids) - len(out), complete


def summarise(orders, priced=None):
    """Orders -> the numbers a person wants. Pending counted, but not banked.

    `priced` is {order_id: (amount, currency)} from product_sales(). Given it,
    revenue is ordered PRODUCT sales -- the item price, which is what Amazon's
    own Total Sales shows and what the seller counts. Without it, revenue falls
    back to OrderTotal, which also includes shipping.
    """
    priced = priced or {}
    out = {"orders": 0, "units": 0, "revenue": 0.0, "pending": 0,
           "cancelled": 0, "currency": "",
           "basis": "product_sales" if priced else "order_total"}
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
        oid = str(o.get("AmazonOrderId") or "")
        amt, cur = priced[oid] if oid in priced else _amount(o)
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

    # PRODUCT SALES, not OrderTotal. These figures are used to fill the days the
    # Sales & Traffic report has not delivered yet, and that report's
    # ordered_sales is the item price -- so filling with OrderTotal put shipping
    # into some bars of a chart and not others, and the bars stopped being
    # comparable. See product_sales().
    priced, unpriced, priced_complete = {}, 0, True
    try:
        priced, unpriced, priced_complete = product_sales(marketplace, creds, orders)
    except Exception:
        priced, unpriced, priced_complete = {}, 0, False

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
        oid = str(o.get("AmazonOrderId") or "")
        if oid in priced:
            amt, cur = priced[oid]
        else:
            # Amazon would not give up this order's items. Fall back to what the
            # buyer was charged rather than counting the order as worthless, and
            # say so on the way out -- a figure that is 4.08 high is far less
            # wrong than a sale that vanished.
            amt, cur = _amount(o)
        if amt:
            d["revenue"] = round(d["revenue"] + amt, 2)
            if cur and not currency:
                currency = cur
    return {"days": dict(sorted(out.items())), "currency": currency,
            "truncated": bool(truncated),
            "basis": "product_sales" if priced else "order_total",
            "unpriced_orders": int(unpriced),
            "priced_complete": bool(priced_complete),
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

    # Ordered product sales, not OrderTotal -- see product_sales(). Best effort:
    # if Amazon will not answer, summarise() falls back per order and says which
    # basis it ended up on, rather than mixing the two without saying.
    def _priced(os_):
        try:
            p, _unpriced, _ok = product_sales(marketplace, creds, os_)
            return p
        except Exception:
            return {}

    out = {"ok": True, "today": summarise(orders, _priced(orders)),
           "as_at": _iso(now),
           "day_started": _iso(start), "truncated": truncated,
           "timezone": str(marketplace_zone(marketplace))}

    if compare:
        y_start = day_start(marketplace, 1)
        y_until = y_start + (now - start)          # the same elapsed slice
        y_orders, y_trunc = fetch_since(marketplace, marketplace_id, creds,
                                        y_start, until=y_until)
        out["yesterday"] = summarise(y_orders, _priced(y_orders))
        out["yesterday_truncated"] = y_trunc
        out["compared_to"] = "the same time yesterday"
        for k in ("orders", "units", "revenue"):
            a, b = out["today"].get(k), out["yesterday"].get(k)
            out.setdefault("delta_pct", {})[k] = (
                round((a - b) / b * 100, 1) if b else None)
    return out
