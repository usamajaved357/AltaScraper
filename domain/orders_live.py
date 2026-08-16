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

    Each line: {asin, sku, title, units, price, shipping, currency}.

    `price` is ItemPrice -- the money for the goods, which is what Amazon calls
    ordered product sales. `shipping` is ShippingPrice, the postage the BUYER
    paid, kept as its own number rather than added in. Both are wanted and they
    are not interchangeable: Seller Central reconciles against the first, and the
    owner's revenue is the two together. Folded into one field, neither question
    could be answered afterwards.
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
            sp = it.get("ShippingPrice") or {}
            try:
                qty = int(it.get("QuantityOrdered") or 0)
            except (TypeError, ValueError):
                qty = 0

            def _money(node):
                try:
                    return float((node or {}).get("Amount") or 0.0)
                except (TypeError, ValueError):
                    return 0.0

            lines.append({
                "asin": str(it.get("ASIN") or ""),
                "sku": str(it.get("SellerSKU") or ""),
                "title": str(it.get("Title") or ""),
                "units": qty,
                "price": _money(ip),
                "shipping": _money(sp),
                "currency": str(ip.get("CurrencyCode")
                                or sp.get("CurrencyCode") or ""),
            })
        out[oid] = lines
    return out, complete


def revenue_of(priced_entry, include_shipping):
    """(amount, currency) for one priced order, on the chosen definition.

    ONE PLACE decides what "revenue" adds up, because the choice is genuinely
    two different questions and both get asked:

      item only        Amazon's Ordered Product Sales, and what Seller Central
                       shows -- the figure to reconcile against.
      item + postage   everything the buyer handed over, which is the money the
                       business actually took: "this is the total revenue i
                       generated ... the fees are cut afterwards from it".
    """
    if not priced_entry:
        return 0.0, ""
    item, ship, cur = priced_entry
    return (round(float(item) + (float(ship) if include_shipping else 0.0), 2),
            cur)


def product_sales(marketplace, creds, orders, max_orders=MAX_ITEM_LOOKUPS,
                  cache=None):
    """Per order: {order_id: (item_price, buyer_postage, currency)}, and how many
    could not be read.

    WHY THIS EXISTS: the owner counted 89.97 for three orders and the app showed
    102.21. Both were right about different things -- 3 x 29.99 of goods, plus
    3 x 4.08 of postage. Amazon's own Total Sales and the Sales & Traffic
    report's ordered_sales are the FIRST one; the owner's revenue is the two
    together. BOTH are kept, separately, and revenue_of() decides which a given
    screen is asking for -- because a figure that has already added them cannot
    be taken apart again to reconcile against Seller Central.

    This matters beyond the label. The Sales chart fills days the report has not
    delivered from the Orders API; with OrderTotal there, a filled day and a
    reported day were measuring different things and the bars were not
    comparable to each other.
    """
    live = [o for o in (orders or [])
            if str(o.get("OrderStatus") or "").lower() not in _DEAD]
    ids = [str(o.get("AmazonOrderId") or "") for o in live]
    ids = [i for i in ids if i]

    # ALREADY KNOWN ORDERS COST NOTHING. getOrderItems is one call per order and
    # measured at about a second each, which turned Live Sales from a 5s panel
    # into a 10s one -- unacceptable on the screen that is meant to be live. An
    # order's item prices do not change once Amazon has given them up, so this
    # cache is permanent rather than timed, and only orders never seen before
    # are fetched. Optional: without one, everything is fetched as before.
    known = {}
    if cache is not None:
        try:
            known = cache.get(ids) or {}
        except Exception:
            known = {}
    todo = [i for i in ids if i not in known]

    items, complete = order_items(marketplace, creds, todo, max_orders=max_orders)
    if cache is not None and items:
        try:
            cache.put(live, items)
        except Exception:
            pass      # a cache that will not write must never fail the read

    out = dict(known)
    for oid in todo:
        lines = items.get(oid)
        if lines is None:
            continue
        item = round(sum(float(l.get("price") or 0.0) for l in lines), 2)
        ship = round(sum(float(l.get("shipping") or 0.0) for l in lines), 2)
        cur = next((l.get("currency") for l in lines if l.get("currency")), "")
        out[oid] = (item, ship, cur)
    return out, len(ids) - len(out), complete


def summarise(orders, priced=None, include_shipping=True):
    """Orders -> the numbers a person wants. Pending counted, but not banked.

    `priced` is {order_id: (item, postage, currency)} from product_sales().
    Given it, revenue is built by revenue_of() -- item price plus the buyer's
    postage by default, because that is the money the business actually took.
    `product_sales` is reported alongside regardless, so the figure that
    reconciles against Seller Central is never lost.

    Without `priced`, revenue falls back to OrderTotal.
    """
    priced = priced or {}
    out = {"orders": 0, "units": 0, "revenue": 0.0, "pending": 0,
           "cancelled": 0, "currency": "",
           "product_sales": 0.0, "shipping": 0.0,
           "basis": ("revenue_with_postage" if (priced and include_shipping)
                     else "product_sales" if priced else "order_total")}
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
        if oid in priced:
            amt, cur = revenue_of(priced[oid], include_shipping)
            out["product_sales"] = round(out["product_sales"] + priced[oid][0], 2)
            out["shipping"] = round(out["shipping"] + priced[oid][1], 2)
        else:
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


# ONE ORDER LIST, SHARED FOR A MINUTE.
#
# getOrders is limited to ONE CALL A MINUTE (0.0167/s, burst 20). Measured, a
# single Sales screen load made FOUR of them -- /sales/today asks twice (today,
# and the same slice of yesterday), /sales/recent once, and the background
# reconcile once -- all for overlapping windows of the same account. A few
# screen loads spent the burst and Live Sales came back "QuotaExceeded".
#
# Orders do not change in a minute in any way that matters here, and every
# caller is reading the same thing. Keyed on the exact window so a wider request
# is never answered from a narrower one.
_ORDERS_CACHE = {}
_ORDERS_TTL = 90          # seconds
_ORDERS_MAX = 24          # windows remembered; beyond this the oldest go


def _creds_id(creds):
    """A short, stable id for WHOSE credentials these are. Never the secret.

    THE CACHE KEY MUST NAME THE ACCOUNT. Without this it was
    marketplace + marketplace_id + window -- and every UK account shares those,
    so three separate companies collided on one key and whichever asked first
    served its orders to the other two. Caught because a backfill reported the
    identical "17 orders seen" for jack_uk, selvora_limited and nestwell_goods.

    Hashed, and only the hash is ever kept or shown: a cache key is not a place
    to hold a refresh token.
    """
    import hashlib
    if isinstance(creds, dict):
        seed = "|".join(str(creds.get(k) or "") for k in
                        ("refresh_token", "lwa_app_id", "seller_id"))
    else:
        seed = str(creds or "")
    if not seed.strip("|"):
        return "anon"
    return hashlib.sha256(seed.encode("utf-8", "replace")).hexdigest()[:16]


def _orders_key(marketplace, marketplace_id, since, until, creds=None):
    return "%s::%s::%s::%s::%s" % (_creds_id(creds), str(marketplace).upper(),
                                   marketplace_id or "", _iso(since),
                                   _iso(until) if until else "")


def fetch_since(marketplace, marketplace_id, creds, since, until=None,
                max_pages=MAX_PAGES, use_cache=True):
    """Orders created since a moment. Returns (orders, truncated).

    Answered from the last 90 seconds' reply where possible -- see
    _ORDERS_CACHE. Pass use_cache=False to insist on a fresh read.
    """
    import time as _t
    key = _orders_key(marketplace, marketplace_id, since, until, creds)
    if use_cache:
        hit = _ORDERS_CACHE.get(key)
        if hit and (_t.time() - hit[0]) < _ORDERS_TTL:
            return hit[1], hit[2]

    from sp_api.api import Orders
    from sp_api.base import Marketplaces
    mkt = getattr(Marketplaces, str(marketplace).upper(), None) or Marketplaces.US
    oc = Orders(credentials=creds, marketplace=mkt)

    kw = {"CreatedAfter": _iso(since),
          "MarketplaceIds": [marketplace_id] if marketplace_id else [mkt.marketplace_id]}
    if until:
        kw["CreatedBefore"] = _iso(until)

    def _remember(orders, truncated):
        if len(_ORDERS_CACHE) >= _ORDERS_MAX:
            for old in sorted(_ORDERS_CACHE, key=lambda k: _ORDERS_CACHE[k][0])[:6]:
                _ORDERS_CACHE.pop(old, None)
        _ORDERS_CACHE[key] = (_t.time(), orders, truncated)
        return orders, truncated

    got, token, pages = [], None, 0
    while pages < int(max_pages):
        resp = oc.get_orders(**kw) if not token else oc.get_orders(NextToken=token, **{
            "MarketplaceIds": kw["MarketplaceIds"]})
        pay = _payload(resp) or {}
        got.extend(pay.get("Orders") or [])
        pages += 1
        token = pay.get("NextToken")
        if not token:
            return _remember(got, False)
    return _remember(got, True)


def by_day(marketplace, marketplace_id, creds, days=5, price_cache=None,
           include_shipping=True):
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
        priced, unpriced, priced_complete = product_sales(
            marketplace, creds, orders, cache=price_cache)
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
        d = out.setdefault(key, {"orders": 0, "units": 0, "revenue": 0.0,
                                 "product_sales": 0.0, "shipping": 0.0})
        d["orders"] += 1
        try:
            d["units"] += int(o.get("NumberOfItemsShipped") or 0) \
                        + int(o.get("NumberOfItemsUnshipped") or 0)
        except (TypeError, ValueError):
            pass
        oid = str(o.get("AmazonOrderId") or "")
        if oid in priced:
            amt, cur = revenue_of(priced[oid], include_shipping)
            d["product_sales"] = round(d["product_sales"] + priced[oid][0], 2)
            d["shipping"] = round(d["shipping"] + priced[oid][1], 2)
        else:
            # Amazon would not give up this order's items. Fall back to what the
            # buyer was charged rather than counting the order as worthless, and
            # say so on the way out -- a sale that is slightly off is far less
            # wrong than a sale that vanished.
            amt, cur = _amount(o)
        if amt:
            d["revenue"] = round(d["revenue"] + amt, 2)
            if cur and not currency:
                currency = cur
    return {"days": dict(sorted(out.items())), "currency": currency,
            "truncated": bool(truncated),
            "basis": ("revenue_with_postage" if (priced and include_shipping)
                      else "product_sales" if priced else "order_total"),
            "unpriced_orders": int(unpriced),
            "priced_complete": bool(priced_complete),
            "since": since.date().isoformat()}


def today(marketplace, marketplace_id, creds, compare=True, price_cache=None,
          include_shipping=True):
    """Today so far, and the same slice of yesterday for honest comparison.

    The comparison stops at the SAME TIME of day, not at yesterday's total.
    Comparing 10am today against a full day yesterday shows a collapse every
    morning and a recovery every evening, neither of which happened.
    """
    start = day_start(marketplace, 0)
    now = _dt.datetime.now(marketplace_zone(marketplace))
    y_start = day_start(marketplace, 1)

    # ONE CALL FOR BOTH DAYS. This asked Amazon twice -- once for today, once for
    # the same slice of yesterday -- and getOrders is limited to ONE CALL A
    # MINUTE. Two calls per screen load, on a screen people reopen, is how Live
    # Sales came to show "QuotaExceeded" instead of figures.
    #
    # Yesterday's window is a subset of "since yesterday began", so one read
    # covers both and the split is done here, for free.
    span_from = y_start if compare else start
    orders_all, truncated = fetch_since(marketplace, marketplace_id, creds,
                                        span_from)

    def _placed(o):
        raw = str(o.get("PurchaseDate") or "")
        try:
            return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None

    orders = [o for o in orders_all
              if (_placed(o) or start) >= start] if compare else orders_all

    # Ordered product sales, not OrderTotal -- see product_sales(). Best effort:
    # if Amazon will not answer, summarise() falls back per order and says which
    # basis it ended up on, rather than mixing the two without saying.
    def _priced(os_):
        try:
            p, _unpriced, _ok = product_sales(marketplace, creds, os_,
                                              cache=price_cache)
            return p
        except Exception:
            return {}

    out = {"ok": True,
           "today": summarise(orders, _priced(orders), include_shipping),
           "as_at": _iso(now),
           "day_started": _iso(start), "truncated": truncated,
           "timezone": str(marketplace_zone(marketplace))}

    if compare:
        y_until = y_start + (now - start)          # the same elapsed slice
        # Split from the one read above rather than asking Amazon again.
        y_orders = [o for o in orders_all
                    if (_placed(o) is not None
                        and y_start <= _placed(o) < y_until)]
        out["yesterday"] = summarise(y_orders, _priced(y_orders),
                                     include_shipping)
        out["yesterday_truncated"] = truncated
        out["compared_to"] = "the same time yesterday"
        for k in ("orders", "units", "revenue"):
            a, b = out["today"].get(k), out["yesterday"].get(k)
            out.setdefault("delta_pct", {})[k] = (
                round((a - b) / b * 100, 1) if b else None)
    return out
