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
    return {"status": status, "price": None, "shipping": None, "currency": "",
            "in_stock": None, "dispatch_days": None, "error": error,
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---- eBay ------------------------------------------------------------------

_EBAY_IN_STOCK = {"IN_STOCK", "LIMITED_STOCK"}
_EBAY_NO_STOCK = {"OUT_OF_STOCK"}


def _ebay_shipping(data):
    """Postage in the item's currency, or None when eBay will not commit to one.

    CALCULATED postage depends on a destination postcode we did not send, so the
    figure (if any) is not the figure we would pay. None is the honest answer --
    the source is then skipped for want of a postage cost, which is visible and
    fixable, rather than costed at zero, which is invisible and wrong.
    """
    for opt in (data.get("shippingOptions") or []):
        if not isinstance(opt, dict):
            continue
        if str(opt.get("shippingCostType") or "").upper() == "CALCULATED":
            continue
        cost = opt.get("shippingCost")
        if isinstance(cost, dict):
            v = _num(cost.get("value"))
            if v is not None:
                return v
    return None


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


def _ebay_dispatch_days(data, now=None):
    """Days until the SOONEST estimated delivery -- see the module note."""
    now = now or _dt.datetime.now()
    best = None
    for opt in (data.get("shippingOptions") or []):
        if not isinstance(opt, dict):
            continue
        for key in ("maxEstimatedDeliveryDate", "minEstimatedDeliveryDate"):
            raw = opt.get(key)
            if not raw:
                continue
            try:
                t = _dt.datetime.strptime(str(raw)[:19], "%Y-%m-%dT%H:%M:%S")
            except (TypeError, ValueError):
                continue
            days = (t - now).days
            if days < 0:
                continue                   # an estimate already in the past
            best = days if best is None else min(best, days)
            break
    return best


def from_ebay_item(data, now=None):
    """A Browse API item -> the common reading. Missing fields stay None."""
    out = _blank(FETCHED)
    if not isinstance(data, dict):
        return _blank(FAILED, "eBay returned no item")
    price = data.get("price") or {}
    out["price"] = _num(price.get("value")) if isinstance(price, dict) else None
    out["currency"] = str((price or {}).get("currency") or "").upper()
    out["shipping"] = _ebay_shipping(data)
    out["in_stock"] = _ebay_stock(data)
    out["available_qty"] = _ebay_qty(data)
    out["dispatch_days"] = _ebay_dispatch_days(data, now)
    if out["price"] is None:
        # An item with no price is not a usable reading, whatever else came back.
        out["status"] = FAILED
        out["error"] = "eBay returned an item with no price"
    return out


# ---- one source ------------------------------------------------------------

def check_source(source, app_id="", cert_id="", now=None, marketplace=None):
    """Read one source. Never raises.

    A shipping_override on the source fills in a postage cost the supplier does
    not publish -- a number the user typed once, which beats one we inferred.
    """
    kind = str((source or {}).get("kind") or "ebay").lower()
    url = (source or {}).get("url") or ""

    if kind == "ebay":
        res = _ebay.get_item(url, app_id, cert_id,
                             marketplace=marketplace or _ebay.DEFAULT_MARKETPLACE)
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

def sweep(config_path, cfg=None, workspace_id=None, marketplace=None,
          pause=0.2, log=None, now=None):
    """Check every source of every ENROLLED SKU, and store the readings.

    Enrolment is what bounds this: nothing is checked, and no supplier is even
    contacted, for a SKU the user has not opted in. Never raises -- it runs on a
    timer, and one bad source must not stop the sweep for everything behind it.
    """
    cfg = cfg() if callable(cfg) else (cfg or {})
    app_id = str(cfg.get("ebay_app_id", "") or "")
    cert_id = str(cfg.get("ebay_cert_id", "") or "")

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
                               marketplace=_ebay.site_for(row["marketplace"]))
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
