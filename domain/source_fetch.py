"""domain/source_fetch.py -- turn a supplier page into one reading.

Every fetcher, whatever it talks to, returns the SAME record:

    {"status": ok|gone|failed, "price", "shipping", "currency",
     "in_stock": True|False|None, "dispatch_days", "checked_at", "error"}

That uniformity is the point. domain/sourcing.py decides from this shape alone
and has no idea whether the number came from an API or a page, so a new kind of
supplier is a new fetcher here and nothing else changes.

WHAT THIS MODULE REFUSES TO DO
It does not turn "I could not tell" into a number. Unknown postage stays None
rather than becoming 0.00, unknown stock stays None rather than becoming False.
Both would be quietly wrong in the expensive direction -- free postage makes an
item look cheaper than it is and prices the listing down; a False stock reading
takes a healthy listing out of stock. The decision engine knows what to do with
None; it cannot recover from a confident wrong value.

THE DISPATCH TIME IS A CONSERVATIVE READ
eBay's Browse API gives an estimated DELIVERY date, not a dispatch time. Used as
dispatch_days that overstates -- delivery is always on or after dispatch -- so
the handling time we promise comes out LONGER than strictly needed. That is the
safe direction: too long costs some conversion, too short costs a late shipment
and account health. It is flagged here because it is the one field in this file
inferred rather than read, and probe_ebay.py exists to check it against what a
real item actually returns.
"""
import datetime as _dt
import time

from api import ebay as _ebay
from domain import source_repo as _repo
from domain import source_scrape as _scrape
from domain.sourcing import FETCHED, GONE, FAILED   # the ONE check vocabulary

# api/ebay.py reports on the HTTP CALL ('ok' -- the request worked); a check
# record reports on the SUPPLIER ('fetched' -- we have their numbers). They are
# different statements and they were briefly given the same three names, which
# meant every reading landed in the database as 'ok', every reading looked
# unreadable to the decision engine, and the repricer did nothing at all --
# silently, because "no usable data" correctly means "change nothing". Translated
# here, in one table, so the two can never drift apart again.
#
# GROUP maps to FAILED, deliberately, and NOT to GONE. A variation-family URL is
# a live product we simply cannot read a single price or stock level from, so the
# honest answer is "we learned nothing" -- which changes nothing. Reading it as
# GONE would be a definite statement that the supplier has stopped selling, and
# domain/sourcing.py acts on definite statements: it would take the listing out
# of stock. The error text names the fix, so it is a FAILED that explains itself.
_FROM_TRANSPORT = {_ebay.OK: FETCHED, _ebay.GONE: GONE, _ebay.FAILED: FAILED,
                   _ebay.GROUP: FAILED}


def _num(v):
    if v is None or v == "":
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _blank(status=FAILED, error=""):
    # The delivery fields are "" and not None: they are text on a screen, and a
    # missing one means "eBay did not say", which reads the same as blank. The
    # numbers stay None because None and 0.00 are different facts about money.
    return {"status": status, "price": None, "shipping": None, "currency": "",
            "in_stock": None, "dispatch_days": None, "error": error,
            "carrier": "", "postage_text": "", "seller": "",
            "delivery_min": "", "delivery_max": "", "delivery_postcode": "",
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---- eBay ------------------------------------------------------------------

_EBAY_IN_STOCK = {"IN_STOCK", "LIMITED_STOCK"}
_EBAY_NO_STOCK = {"OUT_OF_STOCK"}


def _ebay_option(data):
    """THE ONE postage option everything else is read from, or None.

    WHY ONE OPTION AND NOT THE BEST OF EACH FIELD
    This is a bug fix, not a tidy-up. A real item (186107152290, measured 17 Aug
    2026 -- probe_ebay_delivery.py) offers three:

        Evri Tracked           free    arrives by 24 Aug
        Other 48h courier      3.99    arrives by 24 Aug
        Other 24 Hour Courier  8.99    arrives by 21 Aug

    The postage cost was taken from the first usable option (free) while the
    dispatch estimate scanned ALL of them for the SOONEST date (21 Aug, the 8.99
    one). So the app costed the free service and promised the express service's
    delivery date -- three days it had not paid for. The module note at the top
    warns that promising too short costs a late shipment and account health; this
    is that, arriving by a route the note did not foresee.

    So: choose the option once, and let the price, the carrier, the delivery
    window and the dispatch estimate all come from that same option. They then
    describe one real way of buying the thing.

    CHEAPEST, because that is what would actually be bought -- the repricer's
    whole job is the landed cost. Ties broken by the earlier delivery, so a free
    service that arrives sooner wins over an equally free one that does not.
    eBay tends to return them cheapest-first already, but "tends to" is not a
    rule to rest a price on.

    CALCULATED postage is skipped: it depends on a destination postcode, so the
    figure (if any) is not the figure we would pay. Skipping the option is the
    honest answer -- the source is then left without a postage cost, which is
    visible and fixable, rather than costed at zero, which is invisible and wrong.
    """
    best, best_key = None, None
    for opt in (data.get("shippingOptions") or []):
        if not isinstance(opt, dict):
            continue
        if str(opt.get("shippingCostType") or "").upper() == "CALCULATED":
            continue
        cost = opt.get("shippingCost")
        v = _num(cost.get("value")) if isinstance(cost, dict) else None
        if v is None:
            continue
        # The max date, not the min: it is the one that can be promised. Missing
        # dates sort last so an option that gives one beats an option that does
        # not, at the same price.
        when = str(opt.get("maxEstimatedDeliveryDate") or "9999")
        key = (v, when)
        if best_key is None or key < best_key:
            best, best_key = opt, key
    return best


def _ebay_shipping(opt):
    """Postage in the item's currency, or None when eBay will not commit to one."""
    if not isinstance(opt, dict):
        return None
    cost = opt.get("shippingCost")
    return _num(cost.get("value")) if isinstance(cost, dict) else None


def _ebay_carrier(opt):
    """What it says on the eBay page: "Evri Tracked", "Royal Mail Tracked 48".

    shippingServiceCode FIRST. That is the NAMED service and it is the line a
    person reads under the buy button; shippingCarrierCode is the bare company
    ("Hermes") and says less about what is being promised. Measured on a live
    item: serviceCode "Evri Tracked", carrierCode "Hermes". Two of the three
    options on that item had no carrierCode at all and a serviceCode on every one.
    """
    if not isinstance(opt, dict):
        return ""
    for key in ("shippingServiceCode", "shippingCarrierCode"):
        v = str(opt.get(key) or "").strip()
        if v:
            return v
    # "Economy Delivery" -- eBay's own class of service, when it names nothing
    # better. Still more use than an empty cell.
    return str(opt.get("type") or "").strip()


def _ebay_delivery(opt):
    """(min, max) delivery as YYYY-MM-DD, either or both possibly ''."""
    out = []
    for key in ("minEstimatedDeliveryDate", "maxEstimatedDeliveryDate"):
        raw = str((opt or {}).get(key) or "")[:10]
        out.append(raw if len(raw) == 10 else "")
    return out[0], out[1]


def _ebay_postcode_used(data):
    """The postcode eBay says it computed the estimate to, or "".

    Read back from eBay's own echo rather than from what was sent, because the two
    are different claims: the header is what was asked and
    shipToLocationUsedForEstimate is what was answered. A date with no postcode
    behind it must not be shown to a buyer as a promise.
    """
    for opt in (data.get("shippingOptions") or []):
        if not isinstance(opt, dict):
            continue
        loc = opt.get("shipToLocationUsedForEstimate")
        if isinstance(loc, dict) and loc.get("postalCode"):
            return str(loc["postalCode"]).strip().upper()
    return ""


def _postage_text(opt, currency):
    """The sentence, built once here rather than in each screen that shows it.

    Mirrors what eBay prints under the buy button:

        "Free Evri Tracked"
        "3.99 GBP Other 48h courier"
        "Free Economy Delivery"

    Three screens want this line -- order details, the repricer and the sourcing
    table -- and rebuilding it in each is how they come to disagree about the same
    supplier (Rule 12).
    """
    if not isinstance(opt, dict):
        return ""
    cost = _ebay_shipping(opt)
    name = _ebay_carrier(opt)
    if cost is None:
        money = ""
    elif cost <= 0:
        money = "Free"
    else:
        money = "%.2f %s" % (cost, currency or "")
    return " ".join(x for x in (money.strip(), name) if x).strip()


def _ebay_stock(data):
    """True / False / None from estimatedAvailabilities."""
    avails = data.get("estimatedAvailabilities") or []
    for a in avails:
        if not isinstance(a, dict):
            continue
        qty = a.get("estimatedAvailableQuantity")
        if isinstance(qty, (int, float)) and qty <= 0:
            return False
        st = str(a.get("estimatedAvailabilityStatus") or "").upper()
        if st in _EBAY_IN_STOCK:
            return True
        if st in _EBAY_NO_STOCK:
            return False
    return None


def _ebay_qty(data):
    """How many the supplier says are left, or None.

    eBay answers this two ways and the difference matters. estimatedAvailable-
    Quantity is a real count. estimatedRemainingQuantity comes with a THRESHOLD
    ("MORE_THAN 10"), which is a floor and not a count -- a listing showing 94
    there may have far more. Both are better than a bare yes/no, so both are
    used, the exact one first.
    """
    for a in (data.get("estimatedAvailabilities") or []):
        if not isinstance(a, dict):
            continue
        for k in ("estimatedAvailableQuantity", "estimatedRemainingQuantity"):
            q = a.get(k)
            if isinstance(q, (int, float)):
                return int(q)
    return None


def _ebay_dispatch_days(opt, now=None):
    """Days until the estimated delivery of THE OPTION WE COSTED.

    It used to take the soonest date across every option, which is how the free
    postage came to be promised with the express delivery date -- see
    _ebay_option. One option, one promise.

    The MAX date, not the min: eBay gives a window and the far end is the one
    that can be promised. See the module note -- this is used as dispatch_days,
    which overstates, and overstating is the safe direction.
    """
    if not isinstance(opt, dict):
        return None
    now = now or _dt.datetime.now()
    for key in ("maxEstimatedDeliveryDate", "minEstimatedDeliveryDate"):
        raw = opt.get(key)
        if not raw:
            continue
        try:
            t = _dt.datetime.strptime(str(raw)[:19], "%Y-%m-%dT%H:%M:%S")
        except (TypeError, ValueError):
            continue
        # CALENDAR DAYS, from date to date. Subtracting the timestamps and taking
        # .days TRUNCATES: eBay stamps its estimates at 10:00, so checking at noon
        # on the 17th for delivery on the 24th gave 6 days and 22 hours, reported
        # as 6. That is a day SHORT, which is the direction this file exists to
        # avoid -- a handling time we cannot keep. eBay commits to a DATE; the
        # answer is how many days away that date is, and the hour on either side
        # has nothing to do with it.
        days = (t.date() - now.date()).days
        if days < 0:
            continue                       # an estimate already in the past
        return days
    return None


def _ebay_seller(data):
    """Who is selling it, as eBay names them. "" when eBay did not say.

    Browse API returns seller as {"username", "feedbackPercentage",
    "feedbackScore"}. The username is the name shown on the listing page, so it
    is the one a person can recognise and check. Nothing is invented: no
    username means "", and the screen falls back to naming the site.
    """
    s = data.get("seller") if isinstance(data, dict) else None
    if not isinstance(s, dict):
        return ""
    return str(s.get("username") or "").strip()


def from_ebay_item(data, now=None):
    """A Browse API item -> the common reading. Missing fields stay None."""
    out = _blank(FETCHED)
    if not isinstance(data, dict):
        return _blank(FAILED, "eBay returned no item")
    price = data.get("price") or {}
    out["price"] = _num(price.get("value")) if isinstance(price, dict) else None
    out["currency"] = str((price or {}).get("currency") or "").upper()
    # ONE OPTION, chosen once, and every postage fact read off it -- so the cost,
    # the carrier, the delivery window and the handling estimate all describe the
    # same real way of buying it. See _ebay_option.
    opt = _ebay_option(data)
    out["shipping"] = _ebay_shipping(opt)
    out["in_stock"] = _ebay_stock(data)
    out["available_qty"] = _ebay_qty(data)
    out["dispatch_days"] = _ebay_dispatch_days(opt, now)
    out["carrier"] = _ebay_carrier(opt)
    out["seller"] = _ebay_seller(data)
    out["postage_text"] = _postage_text(opt, out["currency"])
    out["delivery_min"], out["delivery_max"] = _ebay_delivery(opt)
    out["delivery_postcode"] = _ebay_postcode_used(data)
    if out["price"] is None:
        # An item with no price is not a usable reading, whatever else came back.
        out["status"] = FAILED
        out["error"] = "eBay returned an item with no price"
    return out


# ---- one source ------------------------------------------------------------

def check_source(source, app_id="", cert_id="", now=None, marketplace=None,
                 postcode=""):
    """Read one source. Never raises.

    A shipping_override on the source fills in a postage cost the supplier does
    not publish -- a number the user typed once, which beats one we inferred.

    `postcode` is the DESTINATION, and it changes the delivery estimate eBay
    returns -- measured three days apart on one option. Passed when the
    destination is known (an order has the buyer's postcode); left empty for the
    routine sweep, where there is no one buyer to compute for. When it is empty
    eBay still answers, but for a notional buyer, and delivery_postcode comes back
    blank so a screen can tell the two apart.
    """
    kind = str((source or {}).get("kind") or "ebay").lower()
    url = (source or {}).get("url") or ""

    if kind == "ebay":
        res = _ebay.get_item(url, app_id, cert_id,
                             marketplace=marketplace or _ebay.DEFAULT_MARKETPLACE,
                             postcode=postcode)
        status = _FROM_TRANSPORT.get(res["status"], FAILED)
        if status == GONE:
            out = _blank(GONE, res["error"] or "the eBay listing has ended")
        elif status != FETCHED:
            out = _blank(FAILED, res["error"] or "eBay fetch failed")
        else:
            out = from_ebay_item(res["data"], now)
    else:
        got = _scrape.read(url)
        out = _blank(got.get("status") or FAILED, got.get("error") or "")
        for k in ("price", "shipping", "currency", "in_stock", "dispatch_days"):
            out[k] = got.get(k)

    ov = _num((source or {}).get("shipping_override"))
    if ov is not None and out.get("shipping") is None and out["status"] == FETCHED:
        out["shipping"] = ov
    return out


# ---- the sweep -------------------------------------------------------------

# WHERE THE SWEEP PRETENDS TO BE DELIVERING TO, and why it must pretend something.
#
# This started as a display detail and turned out to be a pricing bug. Measured on
# six live sources, 17 Aug 2026:
#
#   with no postcode      eBay returned NO shippingOptions AT ALL for five of the
#                         six, so postage came back unknown -- and source_fetch
#                         correctly refuses to cost an unknown postage, so those
#                         sources were being SKIPPED for want of a figure eBay
#                         would have given if asked.
#   with no postcode      the sixth answered "International Priority, 20.04 USD"
#                         -- eBay costing delivery to some notional buyer abroad.
#                         20.04 of phantom postage on a 16.18 item.
#   with BH166FH          all six answered "Free Royal Mail Tracked 48" or
#                         similar, delivery by 20 August.
#
# So a destination is not optional. It is set per account in config.json as
# `sourcing_postcode`; when nobody has set one these are used, and they are
# deliberately central, ordinary, mainland postcodes -- nowhere with an island or
# highland surcharge, so the postage read is the one most buyers would be quoted
# rather than the best or worst case.
#
# THIS IS AN APPROXIMATION AND IT IS MEANT TO BE. The real destination is the
# buyer's address, which is not known until an order exists -- and for an order it
# IS known and IS passed (see check_source). The sweep is pricing before any buyer
# exists, so a representative postcode is the honest answer; the one used is
# stored on every reading (delivery_postcode) so a figure can always be traced to
# the destination it was worked out for.
_FALLBACK_POSTCODE = {
    "GB": "B1 1AA",          # central Birmingham -- mainland, no surcharge
    "US": "10001",           # Manhattan
    "DE": "10115",           # central Berlin
    "FR": "75001",           # central Paris
    "IT": "00184",           # central Rome
    "ES": "28013",           # central Madrid
    "NL": "1012",            # central Amsterdam
    "PL": "00-001",          # central Warsaw
}


def destination_postcode(cfg, marketplace=None):
    """The postcode the sweep costs delivery to. Never empty.

    An account's own setting wins; otherwise a representative postcode for the
    marketplace's country. Returning "" would put us back to eBay answering for a
    notional overseas buyer -- see _FALLBACK_POSTCODE.
    """
    own = str((cfg or {}).get("sourcing_postcode") or "").strip()
    if own:
        return own
    return _FALLBACK_POSTCODE.get(_ebay.country_of(marketplace), "B1 1AA")


def sweep(config_path, cfg=None, workspace_id=None, marketplace=None,
          pause=0.2, log=None, now=None):
    """Check every source of every ENROLLED SKU, and store the readings.

    Enrollment is what bounds this: nothing is checked, and no supplier is even
    contacted, for a SKU the user has not opted in. Never raises -- it runs on a
    timer, and one bad source must not stop the sweep for everything behind it.
    """
    cfg = cfg() if callable(cfg) else (cfg or {})
    app_id = str(cfg.get("ebay_app_id", "") or "")
    cert_id = str(cfg.get("ebay_cert_id", "") or "")
    postcode = destination_postcode(cfg, marketplace)

    rows = _repo.enrolled(config_path, workspace_id, marketplace)
    counts = {"skus": 0, "sources": 0, FETCHED: 0, GONE: 0, FAILED: 0}
    missing_creds = False

    for row in rows:
        counts["skus"] += 1
        srcs = _repo.sources_for(config_path, row["workspace_id"],
                                 row["marketplace"], row["sku"])
        for s in srcs:
            if not s.get("enabled", 1):
                continue
            if str(s.get("kind") or "ebay").lower() == "ebay" and not (app_id and cert_id):
                missing_creds = True
            # The eBay SITE has to match the Amazon marketplace: a US account's
            # supplier asked of eBay UK answers 404, which reads as "ended".
            chk = check_source(s, app_id, cert_id, now=now,
                               marketplace=_ebay.site_for(row["marketplace"]),
                               postcode=postcode)
            _repo.record_check(config_path, s["id"], chk)
            counts["sources"] += 1
            counts[chk["status"]] = counts.get(chk["status"], 0) + 1
            if log:
                log("%s :: %s -> %s %s" % (row["sku"], s.get("label") or s.get("url"),
                                           chk["status"], chk.get("error") or ""))
            if pause:
                time.sleep(pause)

    out = {"ok": True, "checked": counts["sources"], "skus": counts["skus"],
           "readable": counts[FETCHED], "ended": counts[GONE],
           "unreadable": counts[FAILED]}
    if missing_creds:
        out["note"] = ("eBay credentials are not set -- add them under Settings "
                       "so eBay sources can be read")
    if not rows:
        out["note"] = "no SKUs are enrolled in the repricer yet"
    return out
