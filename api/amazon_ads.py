"""api/amazon_ads.py -- the Amazon Advertising API, which is NOT the SP-API.

    "i want each and every feature and page about the inventory and ppc, of
     orbit into my app, please built them"

Six of Orbit's PPC features cannot be built from the Search Term Report and are
not blocked on effort -- they are blocked on this connection:

    the day trail (cumulative spend by hour)    the report has no hour
    the 7 / 14 / 30 day toggle                  one report is one window
    the per-ASIN table                          the report has no ASIN column
    Sponsored Products / Brands / Display       the report is SP only
    the enabled / paused filter                 the report has no status
    the live tracker                            needs live campaign data

WHY IT IS A SEPARATE CONNECTION

The Advertising API is a different product from SP-API with its own developer
registration, its own Login-with-Amazon application, its own refresh token and
its own idea of an account -- a PROFILE, which is one advertising account in one
marketplace. An SP-API refresh token will not authenticate here and there is no
way to derive one from the other. It has to be connected separately, once, and
that is a thing only the account owner can do.

WHAT THIS FILE IS, AND IS NOT

It is the connection and the read calls. It is NOT a bid manager: nothing here
writes a bid, a budget, a negation or a campaign state. CLAUDE.md Rule 8 --
"NEVER change bids or budgets on any campaign unless the user explicitly
specifies in their message the exact new value" -- and a module that cannot
write cannot be made to break that rule by a later mistake. Every function below
is a GET or a report request.

THE REGIONS ARE NOT INTERCHANGEABLE
A token issued in Europe does not work against the North America endpoint, and
the failure is a 401 that reads like bad credentials. The marketplace decides
the host, so it is derived rather than configured -- one fewer thing to get
wrong, and it cannot drift from the marketplace the rest of the app is using.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

# One advertising endpoint per region. Amazon publishes these; a token is bound
# to the region it was issued in.
ENDPOINTS = {
    "NA": "https://advertising-api.amazon.com",
    "EU": "https://advertising-api-eu.amazon.com",
    "FE": "https://advertising-api-fe.amazon.com",
}
TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# Which region a marketplace belongs to. The same split SP-API uses, kept here
# rather than imported so this module has no dependency on the SP-API layer --
# they are genuinely different connections and coupling them is how a change to
# one silently breaks the other.
_REGION = {
    "US": "NA", "CA": "NA", "MX": "NA", "BR": "NA",
    "UK": "EU", "GB": "EU", "DE": "EU", "FR": "EU", "IT": "EU", "ES": "EU",
    "NL": "EU", "SE": "EU", "PL": "EU", "BE": "EU", "IE": "EU", "TR": "EU",
    "AE": "EU", "SA": "EU", "EG": "EU", "IN": "EU", "ZA": "EU",
    "JP": "FE", "AU": "FE", "SG": "FE",
}

# The four things a connection needs. Named here so the settings screen, the
# test and the error messages cannot disagree about what is missing.
FIELDS = ("ads_client_id", "ads_client_secret", "ads_refresh_token",
          "ads_profile_id")

_TIMEOUT = 30
# An access token lasts an hour. Cached per client id + refresh token so a
# screen that makes four calls does not fetch four tokens.
_TOKENS = {}


def region_for(marketplace):
    """Which advertising host serves this marketplace."""
    return _REGION.get(str(marketplace or "").strip().upper(), "EU")


def endpoint_for(marketplace):
    return ENDPOINTS[region_for(marketplace)]


def creds_for(cfg, account=None):
    """The advertising credentials to use, account first then global.

    The same shape as the eBay keys: one set can serve every account, and an
    account that advertises through its own agency login overrides it. Returns
    a dict of the four FIELDS, with "" for anything unset.
    """
    cfg = (cfg() if callable(cfg) else cfg) or {}
    acc = account or {}
    out = {}
    for f in FIELDS:
        out[f] = str(acc.get(f) or cfg.get(f) or "").strip()
    return out


def missing(creds):
    """Which of the four are not set. Empty list means it is ready to try."""
    return [f for f in FIELDS if not (creds or {}).get(f)]


def _post_form(url, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def access_token(creds):
    """Trade the refresh token for an access token. Cached until it expires.

    Raises RuntimeError with Amazon's own words on failure -- the message is the
    whole diagnosis here, because "invalid_grant" and "invalid_client" mean very
    different things and both look like "it did not work" if paraphrased.
    """
    ck = (creds.get("ads_client_id", ""), creds.get("ads_refresh_token", ""))
    hit = _TOKENS.get(ck)
    if hit and hit["expires_at"] > time.time() + 60:
        return hit["token"]
    try:
        got = _post_form(TOKEN_URL, {
            "grant_type": "refresh_token",
            "refresh_token": creds.get("ads_refresh_token", ""),
            "client_id": creds.get("ads_client_id", ""),
            "client_secret": creds.get("ads_client_secret", ""),
        })
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        raise RuntimeError("Amazon refused the advertising login (HTTP %s). %s"
                           % (e.code, detail))
    except Exception as e:
        raise RuntimeError("Could not reach Amazon's login service: %s"
                           % str(e)[:200])
    tok = got.get("access_token")
    if not tok:
        raise RuntimeError("Amazon returned no access token: %s"
                           % json.dumps(got)[:300])
    _TOKENS[ck] = {"token": tok,
                   "expires_at": time.time() + int(got.get("expires_in") or 3600)}
    return tok


def _get(path, creds, marketplace, with_profile=True, accept=None):
    """One authenticated GET. Read-only by construction -- there is no _post."""
    url = endpoint_for(marketplace).rstrip("/") + path
    headers = {
        "Authorization": "Bearer " + access_token(creds),
        "Amazon-Advertising-API-ClientId": creds.get("ads_client_id", ""),
    }
    if with_profile and creds.get("ads_profile_id"):
        headers["Amazon-Advertising-API-Scope"] = str(creds["ads_profile_id"])
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        # 401 against the WRONG REGION reads exactly like bad credentials, and
        # that is the mistake this will meet most often, so it is named.
        hint = ""
        if e.code in (401, 403):
            hint = (" This can also mean the token was issued in a different "
                    "region — this marketplace is served by the %s endpoint."
                    % region_for(marketplace))
        raise RuntimeError("Amazon Advertising refused the request (HTTP %s).%s %s"
                           % (e.code, hint, detail))


def profiles(creds, marketplace):
    """Every advertising profile this login can see.

    A PROFILE is one advertising account in one marketplace, and its id is what
    every other call is scoped to. Listing them is the honest way to set that
    id: pick from what Amazon says exists rather than typing a number from a
    screenshot.

    Called WITHOUT a profile scope, because it is the call that tells you what
    the scopes are.
    """
    got = _get("/v2/profiles", creds, marketplace, with_profile=False)
    out = []
    for p in (got or []):
        if not isinstance(p, dict):
            continue
        acc = p.get("accountInfo") or {}
        out.append({
            "profile_id": str(p.get("profileId") or ""),
            "country": str(p.get("countryCode") or ""),
            "currency": str(p.get("currencyCode") or ""),
            "timezone": str(p.get("timezone") or ""),
            "type": str(acc.get("type") or ""),
            "name": str(acc.get("name") or ""),
            "marketplace_id": str(acc.get("marketplaceStringId") or ""),
        })
    return out


def test(cfg, account, marketplace):
    """Is this connection working? -> a dict a screen can render directly.

    Never raises. A connection test that throws is a connection test that tells
    you nothing, and "it is not set up" and "it is set up wrongly" need
    different answers.
    """
    creds = creds_for(cfg, account)
    gaps = missing(creds)
    if gaps:
        return {"ok": False, "connected": False, "missing": gaps,
                "region": region_for(marketplace),
                "error": "Not connected yet. Still needed: " + ", ".join(
                    f.replace("ads_", "").replace("_", " ") for f in gaps)}
    try:
        found = profiles(creds, marketplace)
    except Exception as e:
        return {"ok": False, "connected": False, "missing": [],
                "region": region_for(marketplace), "error": str(e)[:400]}

    want = str(creds["ads_profile_id"])
    match = next((p for p in found if p["profile_id"] == want), None)
    return {
        "ok": True,
        "connected": True,
        "region": region_for(marketplace),
        "endpoint": endpoint_for(marketplace),
        "profiles": found,
        "profile_id": want,
        # A profile id that is real but belongs to another marketplace is the
        # second most common mistake after the region, and it fails later with
        # empty reports rather than an error. Said now.
        "profile_matches": bool(match),
        "profile": match or None,
        "note": ("" if match else
                 "That profile id is not in the list this login can see for %s. "
                 "Reports would come back empty rather than failing, so pick one "
                 "from the list." % str(marketplace or "").upper()),
    }
