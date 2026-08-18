"""domain/daily_check.py -- the daily round, run by the app instead of by hand.

    "i want to design a page where all of these metrics results are being shown
     and it highlights the things which are off track"

WHAT THIS REPLACES

A Fillout form (Screenshot 89) listing fourteen CSA checks somebody opens every
morning, works through in Seller Central, and ticks off:

    Daily PPC Sales · PPC Orders Number · PPC Spend · Organic vs PPC Sales ·
    BUYER MSGs · Last 24hrs Shipment Status · Account Health · Performance
    Notification · FBM Orders · NCX Rate · A to Z Claims · Inventory
    Performance · Stranded Listings Check · Creator Connection Check

A checklist is a way of remembering to look. The looking is the part a computer
should do, and the only output that matters is the short list of things that are
WRONG today.

THE THREE ANSWERS, AND WHY THERE ARE THREE

    ok        looked at it; it is fine. Says the figure anyway, because "fine"
              with no number is not something anyone can act on tomorrow.
    off       looked at it; it needs attention today, and it says what and why.
    unknown   COULD NOT LOOK. Not "fine" -- names exactly what is missing.

The third one is the whole integrity of the page. A check that cannot run and
renders as a green tick is worse than no page at all: it is the checklist being
ticked without the looking, which is the failure mode the paper form already
has. Six of the fourteen genuinely cannot be answered from anything this app can
reach, and each of those says which connection it needs.

WHY A THRESHOLD IS NEVER INVENTED

Some of these have an obvious line -- an unshipped order past its ship-by date
is late, full stop. Others do not: there is no honest universal number for "PPC
spend is too high today". Where no line exists, the check reports the figure and
marks itself `ok`, because presenting a made-up target as a verdict is how a
page like this stops being believed. Nothing here compares against a target
nobody set.

Every check is a pure function of a `ctx` dict the caller assembles. That keeps
the awkward part -- which of these needs a live Amazon call and which is already
on disk -- in the route, and leaves the judgements testable on their own.
"""
import datetime as _dt

# What a check can say about itself.
OK = "ok"
OFF = "off"
UNKNOWN = "unknown"

# The groups the paper form uses, kept so somebody can move between the two.
G_ORDERS = "Orders & fulfilment"
G_LISTINGS = "Listings"
G_STOCK = "Stock"
G_ADS = "Advertising"
G_ACCOUNT = "Account"
G_MONEY = "Money"


def _r(key, title, group, status, value="", detail="", needs="", action=""):
    """One row of the round."""
    return {"key": key, "title": title, "group": group, "status": status,
            "value": value, "detail": detail, "needs": needs, "action": action}


def _n(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# The checks that CAN be answered
# ---------------------------------------------------------------------------

def check_unshipped(ctx):
    """Orders waiting to go out, and any already past their ship-by date.

    LATE IS THE ONLY HARD LINE ON THIS PAGE. An unshipped order whose
    LatestShipDate has passed is late by Amazon's own definition, not by a rule
    invented here, and it damages the account's late-dispatch metric.
    """
    orders = ctx.get("orders")
    if orders is None:
        return _r("unshipped", "Orders waiting to go out", G_ORDERS, UNKNOWN,
                  needs="the live order list, which could not be read just now")

    now = ctx.get("now") or _dt.datetime.now(_dt.timezone.utc)
    waiting, late = [], []
    for o in orders:
        st = str(o.get("status") or "")
        if st not in ("Unshipped", "PartiallyShipped", "Pending"):
            continue
        waiting.append(o)
        by = _parse_when(o.get("ship_by"))
        if by and by < now and st != "Pending":
            late.append(o)

    if late:
        return _r("unshipped", "Orders waiting to go out", G_ORDERS, OFF,
                  value="%d late" % len(late),
                  detail="%d order%s past the ship-by date Amazon gave, out of "
                         "%d waiting. Late dispatch is the metric this damages."
                         % (len(late), "" if len(late) == 1 else "s",
                            len(waiting)),
                  action="Ship these first, or confirm dispatch if they have "
                         "already gone.")
    return _r("unshipped", "Orders waiting to go out", G_ORDERS, OK,
              value=str(len(waiting)),
              detail="None past its ship-by date."
                     if waiting else "Nothing waiting.")


def check_cancel_requests(ctx):
    """Buyers who pressed cancel on an order that is still live.

    NOT ONE OF THE FOURTEEN, and it belongs here more than several that are:
    posting one costs the postage out AND the return, and the order looks
    entirely normal on every other screen.
    """
    orders = ctx.get("orders")
    if orders is None:
        return _r("cancel_requested", "Buyers asking to cancel", G_ORDERS,
                  UNKNOWN, needs="the live order list")
    hits = [o for o in orders
            if o.get("cancel_requested")
            and str(o.get("status") or "") in ("Unshipped", "PartiallyShipped",
                                               "Pending")]
    if hits:
        return _r("cancel_requested", "Buyers asking to cancel", G_ORDERS, OFF,
                  value=str(len(hits)),
                  detail="%d order%s the buyer has asked to cancel and Amazon "
                         "has not cancelled automatically."
                         % (len(hits), "" if len(hits) == 1 else "s"),
                  action="Do not post these. Cancel in Seller Central, or you "
                         "pay to send something that comes straight back.")
    return _r("cancel_requested", "Buyers asking to cancel", G_ORDERS, OK,
              value="0", detail="No live order has a cancellation request.")


def check_fbm(ctx):
    """How many of the day's orders you have to post yourself."""
    orders = ctx.get("orders")
    if orders is None:
        return _r("fbm", "Orders you post yourself", G_ORDERS, UNKNOWN,
                  needs="the live order list")
    mfn = [o for o in orders if str(o.get("fulfilment") or "").upper() == "MFN"]
    # A count with no line to cross. Reported, never judged -- there is no
    # honest threshold for "too many merchant-fulfilled orders".
    return _r("fbm", "Orders you post yourself", G_ORDERS, OK,
              value=str(len(mfn)),
              detail="%d of %d order%s %s merchant-fulfilled."
                     % (len(mfn), len(orders), "" if len(orders) == 1 else "s",
                        "is" if len(mfn) == 1 else "are"))


def check_stranded(ctx):
    """Listings that are not buyable -- inactive, suppressed or incomplete.

    Amazon's word is "stranded" when stock exists but the listing does not sell
    it. Everything that is not Active is money doing nothing, so all of it is
    reported and the ones holding stock are named first.
    """
    items = ctx.get("listings")
    if items is None:
        return _r("stranded", "Listings not selling", G_LISTINGS, UNKNOWN,
                  needs="the stored catalogue — press Sync on the Listings screen")
    bad, with_stock = [], []
    for it in items:
        st = str((it or {}).get("status") or "").strip().lower()
        if st and st != "active":
            bad.append(it)
            if _n(it.get("qty")) > 0:
                with_stock.append(it)
    if with_stock:
        names = ", ".join(str(i.get("sku") or "?") for i in with_stock[:3])
        return _r("stranded", "Listings not selling", G_LISTINGS, OFF,
                  value="%d holding stock" % len(with_stock),
                  detail="%d listing%s not buyable, and %d of them still %s "
                         "stock: %s%s"
                         % (len(bad), "" if len(bad) == 1 else "s",
                            len(with_stock),
                            "holds" if len(with_stock) == 1 else "hold", names,
                            "…" if len(with_stock) > 3 else ""),
                  action="Open each in Seller Central and fix what it is "
                         "suppressed or inactive for.")
    if bad:
        return _r("stranded", "Listings not selling", G_LISTINGS, OK,
                  value=str(len(bad)),
                  detail="%d not buyable, none of them holding stock."
                         % len(bad))
    return _r("stranded", "Listings not selling", G_LISTINGS, OK, value="0",
              detail="Every listing is buyable.")


def check_delisted(ctx):
    """SKUs the repricer found no longer on Amazon at all."""
    gone = ctx.get("delisted")
    if gone is None:
        return _r("delisted", "SKUs gone from Amazon", G_LISTINGS, UNKNOWN,
                  needs="the repricer's own listing check")
    if gone:
        return _r("delisted", "SKUs gone from Amazon", G_LISTINGS, OFF,
                  value=str(len(gone)),
                  detail="%d enrolled SKU%s no longer answers on Amazon."
                         % (len(gone), "" if len(gone) == 1 else "s"),
                  action="Either the listing was removed or the SKU changed. "
                         "Un-enrol them or fix the listing.")
    return _r("delisted", "SKUs gone from Amazon", G_LISTINGS, OK, value="0")


def check_stock(ctx):
    """Products that need ordering now, or are already out."""
    cockpit = ctx.get("cockpit")
    if cockpit is None:
        return _r("stock", "Stock running out", G_STOCK, UNKNOWN,
                  needs="the Inventory screen's data")
    crit = _n(cockpit.get("need_ordering"))
    out = _n(cockpit.get("already_out"))
    if out or crit:
        bits = []
        if out:
            bits.append("%d already out of stock" % out)
        if crit:
            bits.append("%d need ordering now" % crit)
        return _r("stock", "Stock running out", G_STOCK, OFF,
                  value=" · ".join(bits),
                  detail=str(cockpit.get("headline") or ""),
                  action="Open Inventory → What to order.")
    return _r("stock", "Stock running out", G_STOCK, OK, value="0",
              detail=str(cockpit.get("headline") or "Nothing needs ordering."))


def check_suppliers(ctx):
    """Enrolled SKUs with nowhere left to buy from."""
    alerts = ctx.get("supplier_alerts")
    if alerts is None:
        return _r("suppliers", "Suppliers out of stock", G_STOCK, UNKNOWN,
                  needs="the repricer's supplier readings")
    n = len(alerts)
    if n:
        return _r("suppliers", "Suppliers out of stock", G_STOCK, OFF,
                  value=str(n),
                  detail="%d SKU%s where every supplier is out of stock or "
                         "ended — nothing can be bought to fulfil %s."
                         % (n, "" if n == 1 else "s",
                            "it" if n == 1 else "them"),
                  action="Set the quantity to 0 or find another supplier.")
    return _r("suppliers", "Suppliers out of stock", G_STOCK, OK, value="0",
              detail="Every enrolled SKU has a supplier that can be bought from.")


def check_repricer(ctx):
    """What the repricer changed while nobody was watching.

    Never a fault -- it is the app doing its job. It is here because "why is my
    price different this morning" is a question worth being able to answer
    before a client asks it.
    """
    acts = ctx.get("repricer_actions")
    if acts is None:
        return _r("repricer", "Prices changed overnight", G_MONEY, UNKNOWN,
                  needs="the repricer's action log")
    pushed = [a for a in acts if _n(a.get("applied")) == 1]
    failed = [a for a in acts if _n(a.get("applied")) == -1]
    if failed:
        return _r("repricer", "Prices changed overnight", G_MONEY, OFF,
                  value="%d failed" % len(failed),
                  detail="%d change%s pushed, %d failed to reach Amazon."
                         % (len(pushed), "" if len(pushed) == 1 else "s",
                            len(failed)),
                  action="Open the Repricer to see what Amazon refused.")
    return _r("repricer", "Prices changed overnight", G_MONEY, OK,
              value=str(len(pushed)),
              detail="%d price change%s pushed in the last day."
                     % (len(pushed), "" if len(pushed) == 1 else "s")
                     if pushed else "Nothing changed.")


def check_sync(ctx):
    """Did last night's data actually arrive?

    THE CHECK THAT MAKES THE OTHERS MEAN ANYTHING. Every figure above is read
    from data this app syncs. If the sync did not run, they are all quietly
    describing yesterday, and every one of them would still say "ok".
    """
    age = ctx.get("data_age_hours")
    if age is None:
        return _r("sync", "Data is up to date", G_ACCOUNT, UNKNOWN,
                  needs="the sync job history")
    if age > 36:
        return _r("sync", "Data is up to date", G_ACCOUNT, OFF,
                  value="%.0f hours old" % age,
                  detail="The catalogue has not been refreshed since then, so "
                         "every figure on this page describes that moment, not "
                         "today.",
                  action="Press Sync on the Listings screen.")
    return _r("sync", "Data is up to date", G_ACCOUNT, OK,
              value="%.0f hours old" % age)


def check_ads(ctx):
    """Yesterday's advertising: spend, sales, orders.

    ONE CHECK, NOT THREE. The paper form lists Daily PPC Sales, PPC Orders
    Number and PPC Spend separately, which made sense when a person was reading
    three numbers off one screen. They come from one place and are missing or
    present together.
    """
    ads = ctx.get("ads")
    if ads is None:
        return _r("ads", "Advertising yesterday", G_ADS, UNKNOWN,
                  needs="the Amazon Advertising API, which is a separate login "
                        "from SP-API (Settings → Amazon Advertising "
                        "credentials). The uploaded Search Term Report covers a "
                        "whole window, not a day, so it cannot answer this.")
    spend = ads.get("spend")
    sales = ads.get("sales")
    orders = _n(ads.get("orders"))
    acos = (spend / sales) if (spend and sales) else None
    return _r("ads", "Advertising yesterday", G_ADS, OK,
              value="%s spend · %s sales · %d orders"
                    % (_money(spend), _money(sales), orders),
              detail=("ACOS %.1f%%" % (acos * 100)) if acos else "")


def check_organic_split(ctx):
    """How much of yesterday came from advertising rather than on its own."""
    total = ctx.get("total_sales")
    ads = ctx.get("ads")
    if total is None:
        return _r("organic", "Organic vs paid", G_ADS, UNKNOWN,
                  needs="yesterday's sales, which the app syncs from Amazon")
    if ads is None or ads.get("sales") is None:
        return _r("organic", "Organic vs paid", G_ADS, UNKNOWN,
                  value="%s total" % _money(total),
                  needs="the advertising half — the Advertising API. Total "
                        "sales are known; what came from ads is not.")
    ad_sales = float(ads.get("sales") or 0)
    if ad_sales > total:
        # Real and worth naming rather than showing a negative organic figure.
        return _r("organic", "Organic vs paid", G_ADS, OFF,
                  value="ad sales exceed total",
                  detail="Ad sales of %s against total sales of %s. The two "
                         "come from different reports over different windows, "
                         "so this pair cannot be compared today."
                         % (_money(ad_sales), _money(total)))
    organic = total - ad_sales
    share = (ad_sales / total) if total else None
    return _r("organic", "Organic vs paid", G_ADS, OK,
              value="%s organic · %s paid" % (_money(organic), _money(ad_sales)),
              detail=("%.0f%% of sales came from advertising" % (share * 100))
                     if share is not None else "")


def _money(v):
    if v is None:
        return "—"
    try:
        return "%.2f" % float(v)
    except (TypeError, ValueError):
        return "—"


def _parse_when(v):
    """Amazon's timestamps, as an aware datetime. None when it did not say."""
    s = str(v or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)


# ---------------------------------------------------------------------------
# The checks that CANNOT be answered, and exactly why
# ---------------------------------------------------------------------------
#
# Listed rather than left off. A checklist that silently drops the six things it
# cannot do looks complete and is not, and somebody still has to know to go and
# look at them by hand. Each says the one thing that would change it.

CANNOT = [
    ("buyer_msgs", "Buyer messages", G_ACCOUNT,
     "Amazon does not publish an unanswered-message count through SP-API at "
     "all — the Messaging API only says what you are ALLOWED to send. This has "
     "to be read in Seller Central."),
    ("account_health", "Account health", G_ACCOUNT,
     "The Account Health rating needs a restricted SP-API role this "
     "application is not approved for. Seller Central → Account Health."),
    ("performance_notifications", "Performance notifications", G_ACCOUNT,
     "Needs the SP-API Notifications service and a public endpoint for Amazon "
     "to deliver to. Nothing in this app subscribes to it yet."),
    ("ncx", "NCX rate", G_ACCOUNT,
     "The negative-customer-experience rate comes from Voice of the Customer, "
     "another restricted role. The Returns screen shows the same complaints "
     "grouped by cause, which is the actionable half of it."),
    ("atoz", "A-to-Z claims", G_MONEY,
     "The column exists in the returns report this app already downloads, but "
     "it is not read yet. That is a small change, not a missing connection."),
    ("creator_connection", "Creator Connection", G_ACCOUNT,
     "Amazon has no API and no report for Creator Connection — it is Seller "
     "Central only."),
]


def unavailable():
    """Every check that cannot run, with the reason and no verdict."""
    return [_r(k, t, g, UNKNOWN, needs=why) for (k, t, g, why) in CANNOT]


CHECKS = (check_unshipped, check_cancel_requests, check_fbm, check_stranded,
          check_delisted, check_stock, check_suppliers, check_repricer,
          check_sync, check_ads, check_organic_split)


def run(ctx):
    """The whole round. Off-track first -- that is the only reason to open it.

    Within each status the original order is kept, so the page does not
    reshuffle itself between two visits that found the same things.
    """
    rows = [fn(ctx or {}) for fn in CHECKS] + unavailable()
    rank = {OFF: 0, UNKNOWN: 1, OK: 2}
    rows.sort(key=lambda r: rank.get(r["status"], 3))
    counts = {OFF: 0, OK: 0, UNKNOWN: 0}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "checks": rows,
        # n_ok, NOT ok. The route adds its own "ok": True success flag, which
        # silently overwrote the count of passing checks -- so the API reported
        # `ok: true` where a reader would expect a number, and any caller
        # trusting it got a boolean. Measured on nestwell_goods.
        "n_off": counts[OFF],
        "n_ok": counts[OK],
        "n_unknown": counts[UNKNOWN],
        # The headline. Never "all clear" when something could not be looked at
        # -- that is the sentence this whole page exists to avoid.
        "headline": _headline(counts),
    }


def _headline(counts):
    off, unknown = counts.get(OFF, 0), counts.get(UNKNOWN, 0)
    if off:
        return "%d thing%s need%s attention today" % (
            off, "" if off == 1 else "s", "s" if off == 1 else "")
    if unknown:
        return "Nothing found wrong, but %d check%s could not run" % (
            unknown, "" if unknown == 1 else "s")
    return "Everything checked is fine"
