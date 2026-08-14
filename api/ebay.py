"""api/ebay.py -- the eBay Browse API client. Transport only, no rules, no UI.

WHY THIS FILE EXISTS
The OAuth dance, the item-id regex and the item GET lived inside
amazon_listing_generator.py, where they were used to enrich a listing at
generation time. The source repricer has to call the SAME endpoint for the same
items, on a timer. A second client would have meant a second token cache (so
twice the token calls), a second item-id regex to fall out of step, and two
different opinions about what an eBay error means.

So they were MOVED here and the generator now calls these. Its behaviour is
unchanged -- same regex, same endpoint, same headers, same 15s timeout, and the
same console lines on failure, which are now printed by the caller because
nothing in api/ is allowed to write to a screen (CLAUDE.md Rule 7).

THE THREE ANSWERS, WHICH IS THE WHOLE POINT
get_item never raises and never returns a bare None. It answers one of:

    OK      we have the item
    GONE    eBay says 400/404. The listing has ENDED or was removed. This is a
            FACT about the world -- you cannot buy from that URL any more.
    FAILED  a timeout, a 5xx, a bad token, no network. We know NOTHING.

The generator only cared whether it got data. The repricer cares enormously
about the difference between the last two: treating FAILED as "no stock" would
take a healthy catalogue out of stock the first time the wifi dropped, and
treating GONE as "try again later" would keep selling something nobody can
supply. domain/sourcing.py acts on that distinction, so it has to be made here,
at the only point where the HTTP status code still exists.
"""
import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

OK     = "ok"
GONE   = "gone"
FAILED = "failed"
# The URL is a variation FAMILY, not one buyable thing. Measured: asking
# get_item_by_legacy_id for a family's id answers HTTP 400, which this layer
# would otherwise report as GONE -- i.e. "the listing has ended" -- and the
# repricer would take a perfectly healthy product out of stock and keep it
# there. It has not ended; the URL just does not say WHICH variation.
GROUP  = "group"

DEFAULT_MARKETPLACE = "EBAY_GB"     # what the generator has always used

# Which eBay site to ask, for a given Amazon marketplace. Asking the wrong one
# does not fail loudly -- eBay answers 404 for an item that exists on a
# different site, which this layer reports as GONE, so a US account's suppliers
# would have looked like a catalogue of ended listings.
SITE_FOR = {
    "UK": "EBAY_GB", "US": "EBAY_US", "DE": "EBAY_DE", "FR": "EBAY_FR",
    "IT": "EBAY_IT", "ES": "EBAY_ES", "IE": "EBAY_IE", "NL": "EBAY_NL",
    "BE": "EBAY_BE", "AT": "EBAY_AT", "PL": "EBAY_PL", "CA": "EBAY_CA",
    "AU": "EBAY_AU",
}


def site_for(marketplace):
    """The eBay site matching an Amazon marketplace, defaulting to the UK."""
    return SITE_FOR.get(str(marketplace or "").upper(), DEFAULT_MARKETPLACE)

# One cache for the whole process. Shared with the generator on purpose: a token
# is valid for ~2 hours and there is no reason for two callers to fetch two.
_TOKEN_CACHE = {"token": None, "expires_at": 0.0}

_ITEM_ID_RE = re.compile(r"/itm/(?:[^/?]+/)?(\d{9,15})")
# A child of a variation listing is the SAME /itm/ id with ?var= on the end.
_VAR_ID_RE = re.compile(r"[?&]var=(\d+)")


def item_id_from_url(url):
    """The numeric item id out of an eBay URL, or "" if it is not one.

    NOTE this is the LISTING's id. For a variation listing every child shares it
    -- see variation_id_from_url, which is what tells them apart.
    """
    m = _ITEM_ID_RE.search(url or "")
    return m.group(1) if m else ""


def variation_id_from_url(url):
    """The ?var= id -- WHICH child of a variation listing this URL points at.

    Measured against the live API on 14 Aug 2026, on a 104-child listing:

        104 children -> 1 distinct legacyItemId
        104 children -> 104 distinct itemId

    So the numeric /itm/ id does NOT identify a child. All 104 carry
    223778867020; only the var= id (522519025283, ...284, ...285) separates
    them, and their prices genuinely differ -- 9.99 to 23.49 across that one
    listing. Tracking a child by the listing id alone would price and stock
    every size and colour off whichever one eBay happened to answer with.
    """
    m = _VAR_ID_RE.search(url or "")
    return m.group(1) if m else ""


def full_item_id(listing_id, variation_id=""):
    """The v1|listing|variation id the Browse API uses for ONE buyable thing."""
    if not listing_id:
        return ""
    return "v1|%s|%s" % (listing_id, variation_id or "0")


def split_item_id(item_id):
    """v1|listing|variation -> (listing, variation). ("", "") if it is not one."""
    parts = str(item_id or "").split("|")
    if len(parts) != 3 or not parts[1].isdigit():
        return "", ""
    var = parts[2] if parts[2].isdigit() and parts[2] != "0" else ""
    return parts[1], var


def group_id_from_href(href):
    """The item_group_id out of an itemGroupHref, or ""."""
    s = str(href or "")
    if "item_group_id=" not in s:
        return ""
    return s.split("item_group_id=")[1].split("&")[0].strip()


def token(app_id, cert_id, timeout=15):
    """A client-credentials token, cached until a minute before it expires.

    Returns "" rather than raising: every caller here has something sensible to
    do with "no token", and an exception out of a timer job would kill the sweep
    for every other SKU behind it.
    """
    if _TOKEN_CACHE["token"] and time.time() < _TOKEN_CACHE["expires_at"] - 60:
        return _TOKEN_CACHE["token"]
    if not app_id or not cert_id:
        return ""
    try:
        creds_b64 = base64.b64encode(("%s:%s" % (app_id, cert_id)).encode()).decode()
        req = urllib.request.Request(
            "https://api.ebay.com/identity/v1/oauth2/token",
            data=b"grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
            headers={
                "Authorization": "Basic %s" % creds_b64,
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
        _TOKEN_CACHE["token"] = payload.get("access_token", "")
        _TOKEN_CACHE["expires_at"] = time.time() + payload.get("expires_in", 7200)
        return _TOKEN_CACHE["token"]
    except Exception:
        return ""


# Terms used to sweep a seller's catalogue. See search_seller for why a sweep is
# needed at all. Single letters cast the widest net -- eBay matches them inside
# titles -- and the set is deliberately small: each is a paid-for API call, and
# the returns fall away sharply after the common vowels.
SWEEP_TERMS = ("a", "e", "i", "o", "u", "s", "n", "r", "t", "l")


def search_seller(seller, app_id, cert_id, marketplace=DEFAULT_MARKETPLACE,
                  terms=None, pages_per_term=3, per_page=200, timeout=20,
                  log=None):
    """Everything of one seller's we can find. Returns (items, meta).

    THERE IS NO "LIST THIS SELLER'S INVENTORY" CALL.
    Measured against the live API on 14 Aug 2026: a seller filter on its own is
    rejected --

        "The call must have a valid 'q', 'category_ids', 'charity_ids',
         'epid' or 'gtin' query parameter."

    -- so the only way through Browse is to search FOR something and filter the
    results by seller. This runs several searches and unions them, keyed on the
    item id.

    Which means the result is "everything these searches found", NOT "everything
    this seller has", and the two must never be presented as the same thing. The
    meta carries `complete: False` and the terms used, so the screen can say
    "found 366" instead of implying a total. A number that quietly claims to be
    a whole catalogue is how items go missing without anybody noticing.
    """
    out = {}
    meta = {"seller": seller, "terms": [], "calls": 0, "errors": [],
            "complete": False, "reported_totals": []}
    if not seller:
        meta["errors"].append("no seller given")
        return [], meta

    tok = token(app_id, cert_id, timeout=timeout)
    if not tok:
        meta["errors"].append("could not get an eBay token")
        return [], meta

    for term in (terms or SWEEP_TERMS):
        meta["terms"].append(term)
        offset = 0
        for _page in range(int(pages_per_term)):
            q = urllib.parse.urlencode({
                "q": term, "limit": int(per_page), "offset": offset,
                "filter": "sellers:{%s}" % seller,
            })
            url = ("https://api.ebay.com/buy/browse/v1/item_summary/search?" + q)
            req = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + tok,
                "X-EBAY-C-MARKETPLACE-ID": marketplace,
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read().decode("utf-8"))
                meta["calls"] += 1
            except Exception as e:
                meta["errors"].append("%s: %s" % (term, str(e)[:120]))
                break

            got = data.get("itemSummaries") or []
            if data.get("total") is not None:
                meta["reported_totals"].append(int(data.get("total") or 0))
            for it in got:
                key = str(it.get("legacyItemId") or it.get("itemId") or "")
                if key and key not in out:
                    out[key] = it
            if log:
                log("%s '%s' offset %d -> %d items (%d unique so far)"
                    % (seller, term, offset, len(got), len(out)))
            if len(got) < int(per_page):
                break                       # that term is exhausted
            offset += int(per_page)

    meta["found"] = len(out)
    meta["highest_reported_total"] = max(meta["reported_totals"] or [0])
    return list(out.values()), meta


def item_group(group_id, app_id, cert_id, marketplace=DEFAULT_MARKETPLACE,
               timeout=20):
    """Every child of an eBay variation listing. -> {"status","data","error"}.

    An eBay listing with itemGroupType SELLER_DEFINED_VARIATIONS is one listing
    holding many buyable variations; this returns them so the family can be
    rebuilt on Amazon the way the seller has it.
    """
    out = {"status": FAILED, "data": None, "error": ""}
    if not group_id:
        out["error"] = "no item group id"
        return out
    tok = token(app_id, cert_id, timeout=timeout)
    if not tok:
        out["error"] = "could not get an eBay token"
        return out
    try:
        url = ("https://api.ebay.com/buy/browse/v1/item/get_items_by_item_group"
               "?item_group_id=" + urllib.parse.quote(str(group_id)))
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + tok,
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out["data"] = json.loads(r.read().decode("utf-8"))
        out["status"] = OK
    except urllib.error.HTTPError as e:
        out["status"] = GONE if e.code in (400, 404) else FAILED
        out["error"] = "HTTP %s" % e.code
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def get_item(url_or_id, app_id, cert_id, marketplace=DEFAULT_MARKETPLACE, timeout=15):
    """Fetch one item. Always returns a dict, never raises.

        {"status": OK|GONE|FAILED, "data": {...}|None,
         "http_code": int|None, "error": str, "item_id": str}

    A 400 or 404 is reported as GONE rather than as an error, because that is
    what eBay uses for an item that has ended -- the Browse API does not serve
    ended listings even though the web page often stays up for another 90 days.
    Every other failure is FAILED, which callers must treat as "no information".
    """
    out = {"status": FAILED, "data": None, "http_code": None, "error": "",
           "item_id": "", "variation_id": ""}

    s = str(url_or_id or "").strip()
    # Three shapes reach here: a bare numeric listing id, a full v1|x|y item id,
    # and a URL -- which may carry ?var= naming one child of a family.
    if "|" in s:
        item_id, var_id = split_item_id(s)
    elif s.isdigit():
        item_id, var_id = s, ""
    else:
        item_id, var_id = item_id_from_url(s), variation_id_from_url(s)
    out["item_id"] = item_id
    out["variation_id"] = var_id
    if not item_id:
        out["error"] = "not an eBay item URL"
        return out
    if not app_id or not cert_id:
        out["error"] = "no eBay credentials configured"
        return out

    tok = token(app_id, cert_id, timeout=timeout)
    if not tok:
        out["error"] = "could not get an eBay token"
        return out

    def _get(url):
        req = urllib.request.Request(url, headers={
            "Authorization":           "Bearer %s" % tok,
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
            "Accept":                  "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    # A named child is fetched BY that child. The legacy endpoint cannot express
    # "the black one in a medium" -- it answers with whichever variation eBay
    # picks -- and on a listing whose children run 9.99 to 23.49 that is a price
    # taken from the wrong product.
    if var_id:
        url = ("https://api.ebay.com/buy/browse/v1/item/%s"
               % urllib.parse.quote(full_item_id(item_id, var_id), safe=""))
    else:
        url = ("https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id"
               "?legacy_item_id=%s" % urllib.parse.quote(item_id))

    try:
        out["data"] = _get(url)
        out["status"] = OK
        return out
    except urllib.error.HTTPError as e:
        out["http_code"] = e.code
        out["error"] = "HTTP %s %s" % (e.code, getattr(e, "reason", ""))
        # 400/404 == ended or removed. A fact, not a failure to look.
        out["status"] = GONE if e.code in (400, 404) else FAILED
    except Exception as e:
        out["error"] = str(e)[:200]
        return out

    # ...unless it is a variation FAMILY, which answers 400 to the very same
    # question while being entirely alive. Before calling a product dead --
    # which stops it selling -- ask the one question that tells the two apart.
    if out["status"] == GONE and not var_id:
        grp = item_group(item_id, app_id, cert_id, marketplace=marketplace,
                         timeout=timeout)
        if grp["status"] == OK and (grp["data"] or {}).get("items"):
            out["status"] = GROUP
            out["data"] = grp["data"]
            out["error"] = (
                "This eBay URL is a variation listing with %d variations, not a "
                "single product, so there is no one price or stock level to read "
                "from it. Use the link to the exact variation — it ends in "
                "?var=… — or import the seller's listing as a family."
                % len(grp["data"]["items"]))
    return out
