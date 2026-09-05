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
specifies in their message the exact new value" -- and a module that CANNOT
write cannot be made to break that rule by a later mistake.

THAT GUARANTEE IS ENFORCED, NOT PROMISED. Amazon's reporting API needs a POST to
ASK for a report, so a POST does exist here -- and it is whitelisted to the
reporting paths in _post_json(). Anything else raises before a request is built.
A whitelist is the difference between "we do not write bids" and "we cannot",
and only the second survives somebody adding a helpful convenience later.

READING A REPORT IS NOT WRITING. The POST creates a report job on Amazon's side;
it changes no campaign, no bid, no budget and no state on the advertising
account. It is a read expressed in an awkward verb.

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
    """One authenticated GET. Read-only by construction."""
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


# ---------------------------------------------------------------------------
# READING CAMPAIGN DATA
# ---------------------------------------------------------------------------
#
# BUILT BEFORE THE CREDENTIALS EXISTED, and that was the whole problem with it.
#
# CLAUDE.md Rule 4 is explicit: never guess what Amazon returns, read the schema.
# Every field name below was originally from Amazon's published documentation and
# NOT from a live response, which is a materially weaker thing.
#
# CONNECTED 5 Sep 2026 (nestwell_goods, EU, profile 3291303541830197) and the
# check the next paragraph prescribes was run. It found two wrong names: the
# spCampaigns report sends `campaignStatus` and `campaignBudgetAmount`, and
# neither was among the candidates, so state and budget silently read as unset on
# real data. Both are corrected in MAPPING below, from the live response.
#
# The metric names were right: impressions, clicks, cost, purchases30d, sales30d
# and advertisedAsin all arrive exactly as listed.
#
# STILL UNVERIFIED, because no report that carries them has been pulled yet:
# search_term, keyword, match_type, target_type. Check them the same way before
# trusting anything they feed.
#
# ALSO FOUND: the v2 campaign endpoints used by raw_sample() and campaigns() are
# GONE -- /v2/sp/campaigns and /v2/sp/adGroups both return HTTP 404
# {"code":"NOT_FOUND","details":"Method Not Found"}. Amazon retired v2; the
# replacement is a POST to /sp/campaigns/list, which _post_json's whitelist
# deliberately refuses. Structure data therefore has to come from the reports
# (which carry campaign id, name, status and budget) or the whitelist has to be
# widened by a deliberate decision. Reporting is unaffected and works.
#
# So the code is built to be CORRECTED IN ONE PLACE rather than to be right
# first time:
#
#   * every field is looked up through _pick() with several candidate names,
#     because Amazon's v2 and v3 APIs spell the same thing differently and the
#     campaign endpoints are mid-migration
#   * raw_sample() returns Amazon's UNTOUCHED response, so the moment the
#     connection works one call shows exactly what really arrives
#   * nothing silently defaults to 0: a field that could not be found comes back
#     None, so a mapping that misses shows as "unknown" rather than as a
#     campaign that spent nothing
#
# The first thing to do once the API is connected is call raw_sample() and check
# the names against MAPPING. That is Rule 4's own prescription -- add the
# diagnostic, read what Amazon actually sends, fix from what it says.

# Paths a POST may reach. Reporting only: asking for a report changes nothing on
# the advertising account, and nothing else may be posted at all.
_POST_ALLOWED = ("/reporting/reports",)


def _post_json(path, creds, marketplace, body, with_profile=True):
    """POST, whitelisted to the reporting paths. Anything else raises.

    This is what keeps "cannot write a bid" true rather than merely intended:
    the check is on the path, before a request object exists, so a later caller
    cannot reach a campaign-write endpoint through this function however it is
    called.
    """
    if not any(path.startswith(p) for p in _POST_ALLOWED):
        raise RuntimeError(
            "Refused: %s is not a reporting path. This module reads; it does "
            "not write campaigns, bids or budgets (CLAUDE.md Rule 8)." % path)
    url = endpoint_for(marketplace).rstrip("/") + path
    headers = {
        "Authorization": "Bearer " + access_token(creds),
        "Amazon-Advertising-API-ClientId": creds.get("ads_client_id", ""),
        "Content-Type": "application/vnd.createasyncreportrequest.v3+json",
    }
    if with_profile and creds.get("ads_profile_id"):
        headers["Amazon-Advertising-API-Scope"] = str(creds["ads_profile_id"])
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:400]
        except Exception:
            pass
        raise RuntimeError("Amazon Advertising refused the report request "
                           "(HTTP %s). %s" % (e.code, detail))


def _pick(d, *names):
    """The first of these keys that is present. None when none of them are.

    Several candidate names per field, because Amazon spells the same thing
    differently between the v2 and v3 campaign endpoints and this code was
    written before it could see a real response. When the connection is live,
    check MAPPING against raw_sample() and delete the ones that never appear.
    """
    if not isinstance(d, dict):
        return None
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# Every field name this module depends on, in ONE table. When the API is
# connected, this is the only thing that should need correcting.
MAPPING = {
    "campaign_id": ("campaignId", "campaign_id", "id"),
    "campaign_name": ("name", "campaignName", "campaign_name"),
    # CORRECTED 5 Sep 2026 FROM A LIVE RESPONSE, not from documentation.
    # The spCampaigns report sends `campaignStatus` and `campaignBudgetAmount`.
    # Neither was in the candidate lists, so both came back "" and None on real
    # data -- a campaign with a £5 budget read as having no budget, and an
    # ENABLED campaign read as having no state. Exactly the failure the header
    # warned about: names written from the docs before anything could be read.
    "state": ("campaignStatus", "state", "status", "servingStatus"),
    "budget": ("campaignBudgetAmount", "budget", "dailyBudget", "budgetAmount"),
    # DAILY reports carry the day; SUMMARY reports do not.
    "date": ("date", "startDate"),
    "target_type": ("targetingType", "targeting_type"),
    "impressions": ("impressions",),
    "clicks": ("clicks",),
    "spend": ("cost", "spend"),
    # 30d first (Sponsored Products, verified), then 14d (Brands and Display,
    # whose longest window is 14 days). One row only ever carries one of them,
    # so the order is a preference, not a fallback that could double count.
    "orders": ("purchases30d", "purchases14d", "attributedConversions30d",
               "purchases", "orders"),
    "sales": ("sales30d", "sales14d", "attributedSales30d", "sales",
              "attributedSales1d"),
    "search_term": ("searchTerm", "query", "search_term"),
    "keyword": ("keywordText", "targeting", "keyword", "matchedTarget"),
    "match_type": ("matchType", "match_type"),
    "asin": ("advertisedAsin", "asin", "promotedAsin"),
}


def _row(d):
    """One performance row, normalised, with nothing invented.

    A metric Amazon did not send is None, NOT 0. A campaign whose spend could
    not be read must not appear to have spent nothing -- that is the difference
    between "no data" and "free", and only one of them is a reason to relax.
    """
    out = {}
    for key, names in MAPPING.items():
        v = _pick(d, *names)
        out[key] = v
    for k in ("impressions", "clicks", "spend", "orders", "sales", "budget"):
        out[k] = _num(out.get(k))
    for k in ("campaign_id", "campaign_name", "state", "target_type",
              "search_term", "keyword", "match_type", "asin", "date"):
        out[k] = str(out[k]) if out.get(k) is not None else ""
    return out


def raw_sample(creds, marketplace, what="campaigns"):
    """Amazon's UNTOUCHED response, for checking MAPPING against reality.

    Rule 4's own prescription: when a value is wrong, do not guess -- add a
    diagnostic that prints the raw thing Amazon sends, read it, and fix from
    what it literally says. This exists from the start because the mapping above
    was written without a live connection to read.
    """
    if what == "profiles":
        return _get("/v2/profiles", creds, marketplace, with_profile=False)
    if what == "adgroups":
        return _get("/v2/sp/adGroups?count=5", creds, marketplace)
    return _get("/v2/sp/campaigns?count=5", creds, marketplace)


def campaigns(creds, marketplace):
    """Every Sponsored Products campaign, normalised.

    Structure only -- name, state, budget, targeting type. The PERFORMANCE
    numbers come from a report (see report_request), because the campaign
    endpoint does not carry them.
    """
    got = _get("/v2/sp/campaigns", creds, marketplace)
    return [_row(c) for c in (got or []) if isinstance(c, dict)]


# Amazon's v3 reporting: ask for a report, poll until it is built, download it.
# Same three-step shape as the SP-API reports this app already handles.
#
# THREE AD PRODUCTS, THREE SETS OF REPORTS. Sponsored Products, Sponsored Brands
# and Sponsored Display are separate products with separate report types and
# separate column vocabularies. `adProduct` on a spec says which one; anything
# without it is Sponsored Products.
#
# VERIFIED vs NOT, and the difference matters (Rule 4):
#
#   SPONSORED PRODUCTS   spCampaigns and spAdvertisedProduct have been pulled
#                        live and their columns confirmed against real rows --
#                        impressions, clicks, cost, purchases30d, sales30d,
#                        advertisedAsin, campaignStatus, campaignBudgetAmount.
#
#   BRANDS AND DISPLAY   NOT VERIFIED. These specs are from Amazon's published
#                        documentation and have never been run, because the one
#                        connected account advertises Sponsored Products only
#                        and a report for a product with no campaigns proves
#                        nothing about the column names.
#
# So they are built to FAIL LOUDLY rather than quietly: a wrong column makes
# Amazon reject the report request outright with its own message, which
# report_request already raises verbatim. What must never happen is a report
# that succeeds and maps to nothing, which is why _row() returns None for a
# field it cannot find instead of 0. The first time either of these is run
# against a real account with campaigns, check raw_sample/the raw download
# against MAPPING before trusting a single figure.
REPORT_TYPES = {
    "campaign": {
        "reportTypeId": "spCampaigns",
        "groupBy": ["campaign"],
        "columns": ["campaignId", "campaignName", "impressions", "clicks",
                    "cost", "purchases30d", "sales30d", "campaignStatus",
                    "campaignBudgetAmount"],
    },
    "search_term": {
        "reportTypeId": "spSearchTerm",
        "groupBy": ["searchTerm"],
        "columns": ["campaignId", "campaignName", "searchTerm", "keyword",
                    "matchType", "impressions", "clicks", "cost",
                    "purchases30d", "sales30d"],
    },
    "advertised_product": {
        "reportTypeId": "spAdvertisedProduct",
        "groupBy": ["advertiser"],
        "columns": ["campaignId", "campaignName", "advertisedAsin",
                    "impressions", "clicks", "cost", "purchases30d", "sales30d"],
    },
    # ---- SPONSORED BRANDS -- UNVERIFIED, never run. See the note above. ------
    # Brands does not offer the 30-day attribution window Products does; 14 days
    # is its longest, so the column names differ and are NOT interchangeable.
    "sb_campaign": {
        "adProduct": "SPONSORED_BRANDS",
        "reportTypeId": "sbCampaigns",
        "groupBy": ["campaign"],
        "columns": ["campaignId", "campaignName", "impressions", "clicks",
                    "cost", "purchases14d", "sales14d", "campaignStatus",
                    "campaignBudgetAmount"],
    },
    # ---- SPONSORED DISPLAY -- UNVERIFIED, never run. ------------------------
    "sd_campaign": {
        "adProduct": "SPONSORED_DISPLAY",
        "reportTypeId": "sdCampaigns",
        "groupBy": ["campaign"],
        "columns": ["campaignId", "campaignName", "impressions", "clicks",
                    "cost", "purchases14d", "sales14d", "campaignStatus",
                    "campaignBudgetAmount"],
    },
    "sd_advertised_product": {
        "adProduct": "SPONSORED_DISPLAY",
        "reportTypeId": "sdAdvertisedProduct",
        "groupBy": ["advertiser"],
        "columns": ["campaignId", "campaignName", "promotedAsin",
                    "impressions", "clicks", "cost", "purchases14d", "sales14d"],
    },
}

# Which report kinds belong to each ad product, so a caller can ask for "all of
# Brands" without knowing the kind names. Sponsored Brands has no advertised
# product report in the same shape as the other two, so it is absent rather than
# guessed at.
KINDS_BY_PRODUCT = {
    "SPONSORED_PRODUCTS": ("campaign", "advertised_product"),
    "SPONSORED_BRANDS": ("sb_campaign",),
    "SPONSORED_DISPLAY": ("sd_campaign", "sd_advertised_product"),
}

# Only the first is proven against a live account.
VERIFIED_PRODUCTS = ("SPONSORED_PRODUCTS",)


def ad_product_of(kind):
    """Which advertising product a report kind belongs to."""
    return (REPORT_TYPES.get(kind) or {}).get("adProduct", "SPONSORED_PRODUCTS")


def report_request(creds, marketplace, kind, start, end, time_unit="SUMMARY"):
    """Ask Amazon to build one report. Returns its id.

    A POST, and the only kind this module can make -- see _post_json.

    time_unit "DAILY" gives one row per day instead of one row for the whole
    window. That is what ads_daily needs -- it is keyed on the day, and a
    SUMMARY report cannot be stored there at all because it carries no date.
    Amazon requires the `date` column when the unit is DAILY and REFUSES it when
    the unit is SUMMARY, so the column list is built to match rather than being
    a fixed constant.
    """
    spec = REPORT_TYPES.get(kind)
    if not spec:
        raise RuntimeError("Unknown report kind: %s" % kind)
    unit = str(time_unit or "SUMMARY").upper()
    if unit not in ("SUMMARY", "DAILY"):
        raise RuntimeError("Unknown time unit: %s" % time_unit)
    cols = list(spec["columns"])
    if unit == "DAILY" and "date" not in cols:
        cols.insert(0, "date")
    body = {
        "name": "altascraper %s %s %s..%s" % (kind, unit.lower(), start, end),
        "startDate": start,
        "endDate": end,
        "configuration": {
            # Sponsored Products unless the spec says otherwise. Brands and
            # Display are separate products with their own report types.
            "adProduct": spec.get("adProduct", "SPONSORED_PRODUCTS"),
            "groupBy": spec["groupBy"],
            "columns": cols,
            "reportTypeId": spec["reportTypeId"],
            "timeUnit": unit,
            "format": "GZIP_JSON",
        },
    }
    got = _post_json("/reporting/reports", creds, marketplace, body) or {}
    rid = got.get("reportId") or got.get("reportid")
    if not rid:
        raise RuntimeError("Amazon returned no report id: %s"
                           % json.dumps(got)[:300])
    return str(rid)


def report_status(creds, marketplace, report_id):
    """{status, url} for a report being built."""
    got = _get("/reporting/reports/" + str(report_id), creds, marketplace) or {}
    return {"status": str(got.get("status") or ""),
            "url": str(got.get("url") or ""),
            "failure": str(got.get("failureReason") or "")}


def report_download(url):
    """Fetch and decompress a finished report. Returns a list of rows.

    The download URL is pre-signed and takes no auth header -- sending one is a
    403, which is a confusing way to fail.
    """
    import gzip
    import io
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        raw = r.read()
    try:
        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    except Exception:
        # Amazon has been known to serve it uncompressed despite GZIP_JSON.
        pass
    txt = raw.decode("utf-8", "replace").strip()
    if not txt:
        return []
    try:
        got = json.loads(txt)
    except Exception:
        # Some report types come back as one JSON object per line.
        got = [json.loads(l) for l in txt.splitlines() if l.strip()]
    if isinstance(got, dict):
        got = got.get("rows") or got.get("data") or []
    return [_row(r) for r in got if isinstance(r, dict)]


def report(creds, marketplace, kind, start, end, wait=90, on_wait=None,
           time_unit="SUMMARY"):
    """The whole three-step sequence, or an explanation of why not.

    Polls for up to `wait` seconds. Amazon builds these in anything from a few
    seconds to a couple of minutes, so a caller that cannot wait gets a clear
    "still building" rather than a silent empty list.
    """
    rid = report_request(creds, marketplace, kind, start, end, time_unit)
    waited = 0
    while waited < wait:
        st = report_status(creds, marketplace, rid)
        s = st["status"].upper()
        if s in ("COMPLETED", "SUCCESS"):
            if not st["url"]:
                return {"ok": False, "report_id": rid,
                        "error": "Amazon says the report is ready but gave no "
                                 "download link."}
            return {"ok": True, "report_id": rid,
                    "rows": report_download(st["url"])}
        if s in ("FAILURE", "FAILED", "CANCELLED"):
            return {"ok": False, "report_id": rid,
                    "error": "Amazon could not build the report: %s"
                             % (st["failure"] or s)}
        time.sleep(5)
        waited += 5
        if on_wait:
            try:
                on_wait(waited)
            except Exception:
                pass
    return {"ok": False, "report_id": rid, "pending": True,
            "error": "Amazon is still building the report after %ds. It keeps "
                     "building — ask again shortly with this id." % wait}
