"""domain/hourly_week.py -- which hour of which day each product sells in.

Built to Orbit's Hourly Sales page, whose own description says exactly what it
is:

    "Total ordered sales per ASIN by local hour of week (America/Los_Angeles),
     trailing 30 days. Each row shows the ASIN's average sales by hour of day,
     color-scaled to its own peak hour; click a row for the full Mon-Sun grid."

WHERE THE FIGURES COME FROM, and why this is the only way.

Amazon publishes no hourly report. The Sales & Traffic report is daily, and the
finance records are dated when money moved. The only source of "an order was
placed at 21:04" is the Orders API -- and an order does not say which ASIN was
in it, so learning that costs ONE FURTHER CALL PER ORDER.

Thirty days of orders is therefore thirty days of calls every time the screen is
opened. So each order is fetched once and kept in order_lines, and a second
visit reads the database. Only orders the app has never seen are fetched.

TIMES ARE STORED IN UTC, exactly as Amazon sends them, and converted to the
marketplace's own zone for display. An order placed at 11pm in London is an
evening sale; storing a local time would make the whole table wrong the moment
the account sells in a second country.

CANCELLED ORDERS ARE NOT SALES and are skipped, the same rule the Live Sales
card uses. A cancelled order counted here would put a peak hour where nothing
was ever shipped.
"""

import datetime as _dt

from data import db as _db

# Cancelled, spelled both ways Amazon spells it.
_DEAD = ("canceled", "cancelled")

# How many orders to fetch item detail for in one pass. SP-API rate limits
# getOrderItems, and a first view of a busy account would otherwise sit there
# for minutes with nothing on screen. What was not fetched is REPORTED rather
# than quietly missing -- see `capped` in summary().
MAX_ORDERS_PER_PASS = 120


def _zone(marketplace):
    from domain import orders_live as _ol
    return _ol.marketplace_zone(marketplace)


def _parse(ts):
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def known_order_ids(config_path, workspace_id, marketplace, since):
    """Orders already in the table, so they are never fetched twice."""
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT DISTINCT order_id FROM order_lines "
        "WHERE workspace_id=? AND marketplace=? AND purchase_date>=?",
        (workspace_id, marketplace, since)).fetchall()
    return {r["order_id"] for r in rows}


def store_lines(config_path, workspace_id, marketplace, lines):
    """Write order lines, ignoring ones already there."""
    if not lines:
        return 0
    conn = _db.get_db(config_path)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for L in lines:
        try:
            # ON CONFLICT rather than OR IGNORE: a line stored before the
            # postage column existed must be able to GAIN its postage when it is
            # fetched again, and a status that has moved on (pending -> shipped,
            # or cancelled) must be able to follow. The frozen cost is left
            # alone -- that is the one field that must never move.
            conn.execute(
                "INSERT INTO order_lines "
                "(workspace_id, marketplace, order_id, purchase_date, asin, sku,"
                " title, units, revenue, shipping, currency, status, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(workspace_id, marketplace, order_id, asin, sku) "
                "DO UPDATE SET shipping=excluded.shipping, "
                "              revenue=excluded.revenue, "
                "              status=excluded.status, "
                "              fetched_at=excluded.fetched_at",
                (workspace_id, marketplace, L["order_id"], L["purchase_date"],
                 L.get("asin") or "", L.get("sku") or "", L.get("title") or "",
                 int(L.get("units") or 0), float(L.get("revenue") or 0),
                 float(L.get("shipping") or 0),
                 L.get("currency") or "", L.get("status") or "", now))
            n += 1
        except Exception:
            continue
    conn.commit()
    return n


def price_cache(config_path, workspace_id, marketplace):
    """Per-order product sales, remembered in the order_lines table.

    WHY THE SALES SCREEN NEEDS THIS. Pricing an order costs one getOrderItems
    call, measured at about a second each. Live Sales prices today's orders and
    yesterday's for the comparison, so a handful of orders turned a 5s panel
    into a 10s one -- on the screen whose whole point is being live.

    An order's item prices do not change once Amazon has given them up, so this
    is permanent, not timed. And it is THIS table rather than a new one because
    the hourly page is already filling it with exactly these numbers: two stores
    of the same fact is how two screens come to disagree about one order.

    Duck-typed to what orders_live.product_sales() asks for: get() and put().
    """
    class _Cache(object):
        def get(self, order_ids):
            ids = [str(i) for i in (order_ids or []) if i]
            if not ids:
                return {}
            conn = _db.get_db(config_path)
            out = {}
            # Chunked: SQLite has a limit on how many parameters one statement
            # may carry, and a busy month can exceed it.
            for i in range(0, len(ids), 400):
                chunk = ids[i:i + 400]
                # shipping IS NOT NULL, deliberately. Lines stored before the
                # postage column existed carry NULL, and treating that as zero
                # would freeze "the buyer paid nothing to have it sent" into
                # every old order for ever. Left out of the cache, they are
                # simply fetched once more and filled in.
                q = ("SELECT order_id, SUM(revenue) AS rev, "
                     "       SUM(shipping) AS ship, "
                     "       MAX(currency) AS cur "
                     "FROM order_lines "
                     "WHERE workspace_id=? AND marketplace=? "
                     "  AND shipping IS NOT NULL "
                     "  AND order_id IN (%s) GROUP BY order_id"
                     % ",".join("?" * len(chunk)))
                for r in conn.execute(q, [workspace_id, marketplace] + chunk):
                    out[r["order_id"]] = (round(float(r["rev"] or 0), 2),
                                          round(float(r["ship"] or 0), 2),
                                          r["cur"] or "")
            return out

        def put(self, orders, items_by_order):
            meta = {str(o.get("AmazonOrderId") or ""): o for o in (orders or [])}
            lines = []
            for oid, its in (items_by_order or {}).items():
                o = meta.get(oid) or {}
                for it in its:
                    lines.append({
                        "order_id": oid,
                        "purchase_date": str(o.get("PurchaseDate") or ""),
                        "asin": it.get("asin", ""), "sku": it.get("sku", ""),
                        "title": it.get("title", ""),
                        "units": it.get("units", 0),
                        "revenue": float(it.get("price") or 0),
                        "shipping": float(it.get("shipping") or 0),
                        "currency": it.get("currency", ""),
                        "status": str(o.get("OrderStatus") or ""),
                    })
            return store_lines(config_path, workspace_id, marketplace, lines)

    return _Cache()


def fetch(config_path, workspace_id, marketplace, marketplace_id, creds, days=30,
          max_orders=MAX_ORDERS_PER_PASS):
    """Pull any orders in the window this app has not already stored.

    Returns {"fetched", "orders_seen", "capped"}. `capped` is true when there
    were more new orders than one pass will take -- the screen says so rather
    than presenting a partial picture as a complete one.
    """
    from domain import orders_live as _ol
    since = _ol.day_start(marketplace, days_ago=max(0, int(days) - 1))
    orders, _truncated = _ol.fetch_since(marketplace, marketplace_id, creds, since)

    since_iso = since.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    known = known_order_ids(config_path, workspace_id, marketplace, since_iso)

    todo = []
    for o in orders or []:
        if str(o.get("OrderStatus") or "").lower() in _DEAD:
            continue
        oid = str(o.get("AmazonOrderId") or "")
        if not oid or oid in known:
            continue
        todo.append(o)

    capped = len(todo) > max_orders
    todo = todo[:max_orders]

    # ONE reader of "what was in this order", shared with the Sales screen --
    # which sums these same item prices to get the day's product sales. Two
    # copies of this loop is how two screens come to disagree about one order.
    by_order, _complete = _ol.order_items(
        marketplace, creds, [str(o.get("AmazonOrderId") or "") for o in todo],
        max_orders=max_orders)

    lines, done = [], 0
    for o in todo:
        oid = str(o.get("AmazonOrderId") or "")
        when = str(o.get("PurchaseDate") or "")
        status = str(o.get("OrderStatus") or "")
        items = by_order.get(oid)
        if items is None:
            # AMAZON WOULD NOT ITEMISE THIS ORDER -- usually a rate limit. It
            # used to be skipped entirely, so the order vanished from the sales
            # figures altogether: measured on selvora_limited, 229.93 across
            # seven orders simply absent from a thirty-day total.
            #
            # A sale we cannot break down is still a sale. It is recorded from
            # the order's own totals, with no ASIN or SKU because we genuinely
            # do not know them, and with revenue split off the OrderTotal. The
            # blank SKU is also what makes it eligible to be fetched again and
            # filled in properly once Amazon will answer.
            from domain import orders_live as _ol2
            amt, cur = _ol2._amount(o)
            try:
                qty = int(o.get("NumberOfItemsShipped") or 0) + \
                      int(o.get("NumberOfItemsUnshipped") or 0)
            except (TypeError, ValueError):
                qty = 0
            if amt or qty:
                lines.append({
                    "order_id": oid, "purchase_date": when,
                    "asin": "", "sku": "", "title": "(not itemised by Amazon)",
                    "units": qty, "revenue": float(amt or 0), "shipping": 0.0,
                    "currency": cur or "", "status": status,
                })
            continue
        for it in items:
            lines.append({
                "order_id": oid, "purchase_date": when,
                "asin": it.get("asin", ""),
                "sku": it.get("sku", ""),
                "title": it.get("title", ""),
                "units": it.get("units", 0),
                "revenue": float(it.get("price") or 0),
                "currency": it.get("currency", ""), "status": status,
            })
        done += 1
    store_lines(config_path, workspace_id, marketplace, lines)
    return {"fetched": done, "orders_seen": len(orders or []), "capped": capped}


def summary(config_path, workspace_id, marketplace, days=30, metric="units",
            top_n=25):
    """Per ASIN: the 24-hour profile, the Mon-Sun grid, and the window totals.

    metric is "units" or "revenue" -- Orbit offers both, and they answer
    different questions: which hour sells the most THINGS, and which hour brings
    in the most MONEY. On a catalogue with a wide price range they are not the
    same hour.
    """
    metric = "revenue" if metric == "revenue" else "units"
    conn = _db.get_db(config_path)
    since = (_dt.date.today() - _dt.timedelta(days=max(1, int(days)) - 1)).isoformat()
    rows = conn.execute(
        "SELECT asin, title, purchase_date, units, revenue, currency "
        "FROM order_lines WHERE workspace_id=? AND marketplace=? "
        "  AND substr(purchase_date,1,10)>=? AND asin<>''",
        (workspace_id, marketplace, since)).fetchall()

    tz = _zone(marketplace)
    by = {}
    currency = ""
    for r in rows:
        dt = _parse(r["purchase_date"])
        if not dt:
            continue
        local = dt.astimezone(tz)
        # Monday = 0, to match "the full Mon-Sun grid".
        dow, hour = local.weekday(), local.hour
        a = by.setdefault(r["asin"], {
            "asin": r["asin"], "title": r["title"] or "",
            "hours": [0.0] * 24,
            "grid": [[0.0] * 24 for _ in range(7)],
            "units": 0, "revenue": 0.0, "orders": 0,
        })
        v = (r["units"] or 0) if metric == "units" else float(r["revenue"] or 0)
        a["hours"][hour] += v
        a["grid"][dow][hour] += v
        a["units"] += (r["units"] or 0)
        a["revenue"] = round(a["revenue"] + float(r["revenue"] or 0), 2)
        a["orders"] += 1
        if not a["title"] and r["title"]:
            a["title"] = r["title"]
        if not currency and r["currency"]:
            currency = r["currency"]

    out = sorted(by.values(),
                 key=lambda x: (-(x[metric] or 0), x["asin"]))[:top_n]
    for a in out:
        peak = max(a["hours"]) if a["hours"] else 0
        a["peak"] = peak
        # The peak HOUR, named, because "your best hour is 8pm" is the sentence
        # someone acts on -- it decides when a deal or a bid change goes live.
        a["peak_hour"] = (a["hours"].index(peak) if peak else None)
        a["hours"] = [round(v, 2) for v in a["hours"]]
        a["grid"] = [[round(v, 2) for v in row] for row in a["grid"]]
    return {
        "days": int(days), "metric": metric, "since": since,
        "timezone": str(getattr(tz, "key", "") or tz),
        "currency": currency,
        "asins": out,
        "lines": len(rows),
        "empty": not out,
    }
