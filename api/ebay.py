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

DEFAULT_MARKETPLACE = "EBAY_GB"     # what the generator has always used

# One cache for the whole process. Shared with the generator on purpose: a token
# is valid for ~2 hours and there is no reason for two callers to fetch two.
_TOKEN_CACHE = {"token": None, "expires_at": 0.0}

_ITEM_ID_RE = re.compile(r"/itm/(?:[^/?]+/)?(\d{9,15})")


def item_id_from_url(url):
    """The numeric item id out of an eBay URL, or "" if it is not one."""
    m = _ITEM_ID_RE.search(url or "")
    return m.group(1) if m else ""


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


def get_item(url_or_id, app_id, cert_id, marketplace=DEFAULT_MARKETPLACE, timeout=15):
    """Fetch one item. Always returns a dict, never raises.

        {"status": OK|GONE|FAILED, "data": {...}|None,
         "http_code": int|None, "error": str, "item_id": str}

    A 400 or 404 is reported as GONE rather than as an error, because that is
    what eBay uses for an item that has ended -- the Browse API does not serve
    ended listings even though the web page often stays up for another 90 days.
    Every other failure is FAILED, which callers must treat as "no information".
    """
    out = {"status": FAILED, "data": None, "http_code": None, "error": "", "item_id": ""}

    s = str(url_or_id or "").strip()
    item_id = s if s.isdigit() else item_id_from_url(s)
    out["item_id"] = item_id
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

    try:
        url = ("https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id"
               "?legacy_item_id=%s" % urllib.parse.quote(item_id))
        req = urllib.request.Request(url, headers={
            "Authorization":           "Bearer %s" % tok,
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
            "Accept":                  "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out["data"] = json.loads(r.read().decode("utf-8"))
        out["status"] = OK
        return out
    except urllib.error.HTTPError as e:
        out["http_code"] = e.code
        out["error"] = "HTTP %s %s" % (e.code, getattr(e, "reason", ""))
        # 400/404 == ended or removed. A fact, not a failure to look.
        out["status"] = GONE if e.code in (400, 404) else FAILED
        return out
    except Exception as e:
        out["error"] = str(e)[:200]
        return out
