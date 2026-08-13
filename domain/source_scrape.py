"""domain/source_scrape.py -- reading a supplier page that has no API.

ISOLATED ON PURPOSE
This is the least trustworthy code in the repricer, so it is kept in its own
file and hands back the same record shape as the eBay client. Nothing in here
decides anything; a change to a supplier's HTML can make this return "I don't
know" but it cannot reach domain/sourcing.py and move a price.

WHAT IT WILL AND WILL NOT READ
It reads JSON-LD -- the schema.org Product/Offer block that most shopping sites
publish for Google. That is a PUBLISHED STANDARD with named fields, so reading
it is not guesswork.

It will NOT hunt for a price in arbitrary HTML. Every "find the biggest number
near a pound sign" heuristic eventually finds the wrong number -- an accessory,
a monthly instalment, a "was" price, a quantity break -- and a wrong cost here
does not show up as a wrong number on a screen. It sets a real selling price.
So a page with no structured data returns FAILED, which the decision engine
treats as "we learned nothing" and leaves the listing alone.

When a site needs supporting and publishes nothing, add it to _SITE_READERS with
an explicit rule for that domain. That is a deliberate, reviewable act rather
than a heuristic that silently starts being wrong.

POSTAGE IS USUALLY NOT IN THERE
JSON-LD rarely carries a postage cost, and unknown postage is not free postage
(it would understate the cost and pull the price down). Rather than guess, a
source can carry a shipping_override the user types once -- a known constant
beats an inferred number.
"""
import json
import re
import urllib.request

# The CHECK vocabulary, not the HTTP one -- what we can say about the SUPPLIER,
# which is the only thing domain/sourcing.py acts on.
from domain.sourcing import FETCHED, GONE, FAILED

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S)

_IN_STOCK = {"instock", "in_stock", "onlineonly", "instoreonly", "limitedavailability"}
_NO_STOCK = {"outofstock", "soldout", "discontinued", "preorder", "backorder"}


def _num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _walk(node):
    """Every dict inside an arbitrarily nested JSON-LD blob."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            for d in _walk(v):
                yield d
    elif isinstance(node, list):
        for v in node:
            for d in _walk(v):
                yield d


def _offers_from(html):
    """The first schema.org Offer with a price. None if the page has none."""
    for block in _LD_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue                       # a malformed block is not a price
        for node in _walk(data):
            t = node.get("@type") or node.get("type") or ""
            types = [t] if isinstance(t, str) else list(t or [])
            if not any(str(x).lower() == "offer" for x in types):
                continue
            if _num(node.get("price")) is not None:
                return node
    return None


def _stock_from(offer):
    """True / False / None. None means the page did not say."""
    av = offer.get("availability") or offer.get("itemCondition_availability")
    if not av:
        return None
    key = str(av).rsplit("/", 1)[-1].strip().lower().replace(" ", "")
    if key in _IN_STOCK:
        return True
    if key in _NO_STOCK:
        return False
    return None


# Explicit per-domain readers, for sites that publish nothing usable. Each entry
# is domain -> callable(html) -> dict of the same fields. Empty by design: a
# reader is added when a real site needs one, against that site's real HTML.
_SITE_READERS = {}


def read(url, timeout=20):
    """Read a supplier page. Never raises.

    -> {"status", "price", "shipping", "currency", "in_stock", "dispatch_days",
        "error"}  with shipping and dispatch_days almost always None.
    """
    out = {"status": FAILED, "price": None, "shipping": None, "currency": "",
           "in_stock": None, "dispatch_days": None, "error": ""}
    if not url:
        out["error"] = "no url"
        return out

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-GB,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(3_000_000)        # a supplier page that big is not a page
            html = raw.decode(r.headers.get_content_charset() or "utf-8", "replace")
    except Exception as e:
        code = getattr(e, "code", None)
        # 404/410 == the product page is gone. A fact, like an ended eBay item.
        if code in (404, 410):
            out["status"] = GONE
            out["error"] = "page is gone (HTTP %s)" % code
        else:
            out["error"] = str(e)[:200]
        return out

    host = re.sub(r"^www\.", "", (re.split(r"/+", url + "//")[1] or "")).lower()
    reader = _SITE_READERS.get(host)
    if reader:
        try:
            got = reader(html) or {}
            out.update({k: v for k, v in got.items() if k in out})
            out["status"] = FETCHED if out["price"] is not None else FAILED
            if out["price"] is None:
                out["error"] = "the reader for %s found no price" % host
            return out
        except Exception as e:
            out["error"] = "reader for %s failed: %s" % (host, str(e)[:120])
            return out

    offer = _offers_from(html)
    if not offer:
        # Deliberately not a fallback to guessing. Unknown is a safe answer.
        out["error"] = ("no structured product data on this page -- add a reader "
                        "for %s to support it" % host)
        return out

    out["price"] = _num(offer.get("price"))
    out["currency"] = str(offer.get("priceCurrency") or "").upper()
    out["in_stock"] = _stock_from(offer)
    sh = offer.get("shippingDetails") or {}
    for node in _walk(sh):
        cand = _num((node.get("shippingRate") or {}).get("value")
                    if isinstance(node.get("shippingRate"), dict) else None)
        if cand is not None:
            out["shipping"] = cand
            break
    out["status"] = FETCHED
    return out
