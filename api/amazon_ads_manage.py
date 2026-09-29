"""api/amazon_ads_manage.py -- Sponsored Products campaign management (Ads API v3).

    "many campaigns are actually turned off in seller central but are shown as
     enabled here and i also want an option to turn on or off the campaigns and
     change the budget, bids and rules and every other feature that we have in
     seller central, i want it here"                    -- owner, 30 Sep 2026

WHY A SECOND MODULE. api/amazon_ads.py reads and is kept unable to write (its
_POST_ALLOWED is the reporting path only, and tests pin that). Writing is a
different kind of call and lives here, behind its OWN exact list of what may be
called -- method and path, matched exactly, not by prefix -- so nothing else on
the advertising account can be reached through this module either.

WHAT IT CAN DO, and nothing more:
  read   the live campaign / ad group / keyword / target lists (POST .../list
         is Amazon's read; it changes nothing)
  write  a campaign's state or daily budget; an ad group's state or default
         bid; a keyword's or product target's state or bid; add negative
         keywords. Every write is the OWNER'S typed value, confirmed, and is
         only ever called by domain/ppc_control, which reads the value first,
         reads it back after, and records all three (CLAUDE.md Rule 8).

THE SHAPES are Amazon's Sponsored Products v3 ones (vnd.sp*.v3+json). Amazon
answers a write with 207 multi-status: per item success or error, so a batch is
never assumed to have worked as a whole.
"""
import json
import urllib.error
import urllib.request

from api import amazon_ads as _ads

_TIMEOUT = 30

# (method, path) -> content type. EXACT matches only.
_ALLOWED = {
    ("POST", "/sp/campaigns/list"): "application/vnd.spCampaign.v3+json",
    ("POST", "/sp/adGroups/list"): "application/vnd.spAdGroup.v3+json",
    ("POST", "/sp/keywords/list"): "application/vnd.spKeyword.v3+json",
    ("POST", "/sp/targets/list"): "application/vnd.spTargetingClause.v3+json",
    ("POST", "/sp/negativeKeywords/list"): "application/vnd.spNegativeKeyword.v3+json",
    ("PUT", "/sp/campaigns"): "application/vnd.spCampaign.v3+json",
    ("PUT", "/sp/adGroups"): "application/vnd.spAdGroup.v3+json",
    ("PUT", "/sp/keywords"): "application/vnd.spKeyword.v3+json",
    ("PUT", "/sp/targets"): "application/vnd.spTargetingClause.v3+json",
    ("POST", "/sp/negativeKeywords"): "application/vnd.spNegativeKeyword.v3+json",
}

STATES = ("ENABLED", "PAUSED")          # ARCHIVED is final on Amazon: not offered


def _call(method, path, creds, marketplace, body):
    """One authenticated call on the list above. Raises RuntimeError with
    Amazon's own words on refusal."""
    ctype = _ALLOWED.get((method, path))
    if not ctype:
        raise RuntimeError("Refused: %s %s is not on this module's list." % (method, path))
    if not creds.get("ads_profile_id"):
        raise RuntimeError("No advertising profile is set for this account.")
    url = _ads.endpoint_for(marketplace).rstrip("/") + path
    headers = {
        "Authorization": "Bearer " + _ads.access_token(creds),
        "Amazon-Advertising-API-ClientId": creds.get("ads_client_id", ""),
        "Amazon-Advertising-API-Scope": str(creds["ads_profile_id"]),
        "Content-Type": ctype,
        "Accept": ctype,
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        raise RuntimeError("Amazon Advertising refused %s %s (HTTP %s). %s"
                           % (method, path, e.code, detail))


def _list(path, key, creds, marketplace, body):
    """Every page of a v3 list call -> [items]."""
    out, token, pages = [], None, 0
    while True:
        b = dict(body)
        b["maxResults"] = 500
        if token:
            b["nextToken"] = token
        got = _call("POST", path, creds, marketplace, b) or {}
        out.extend(got.get(key) or [])
        token = got.get("nextToken")
        pages += 1
        if not token or pages >= 40:
            return out


def _states(include_archived=True):
    s = ["ENABLED", "PAUSED"] + (["ARCHIVED"] if include_archived else [])
    return {"stateFilter": {"include": s}}


def list_campaigns(creds, marketplace):
    """Every SP campaign as Amazon holds it NOW -> [{campaign_id, name, state,
    budget, budget_type, targeting_type, start_date, end_date}]."""
    out = []
    for c in _list("/sp/campaigns/list", "campaigns", creds, marketplace, _states()):
        bud = c.get("budget") or {}
        out.append({"campaign_id": str(c.get("campaignId") or ""),
                     "name": c.get("name") or "",
                     "state": str(c.get("state") or "").upper(),
                     "budget": bud.get("budget"),
                     "budget_type": bud.get("budgetType") or "",
                     "targeting_type": c.get("targetingType") or "",
                     "start_date": c.get("startDate") or "",
                     "end_date": c.get("endDate") or ""})
    return out


def _in_campaign(campaign_id):
    return {"campaignIdFilter": {"include": [str(campaign_id)]}}


def list_ad_groups(creds, marketplace, campaign_id):
    return [{"ad_group_id": str(g.get("adGroupId") or ""), "name": g.get("name") or "",
             "state": str(g.get("state") or "").upper(), "default_bid": g.get("defaultBid")}
            for g in _list("/sp/adGroups/list", "adGroups", creds, marketplace,
                           dict(_states(False), **_in_campaign(campaign_id)))]


def list_keywords(creds, marketplace, campaign_id):
    return [{"keyword_id": str(k.get("keywordId") or ""), "ad_group_id": str(k.get("adGroupId") or ""),
             "text": k.get("keywordText") or "", "match_type": k.get("matchType") or "",
             "state": str(k.get("state") or "").upper(), "bid": k.get("bid")}
            for k in _list("/sp/keywords/list", "keywords", creds, marketplace,
                           dict(_states(False), **_in_campaign(campaign_id)))]


def list_targets(creds, marketplace, campaign_id):
    out = []
    for t in _list("/sp/targets/list", "targetingClauses", creds, marketplace,
                   dict(_states(False), **_in_campaign(campaign_id))):
        expr = t.get("expression") or []
        label = ", ".join("%s %s" % (e.get("type", ""), e.get("value", "")) for e in expr
                          if isinstance(e, dict)).strip()
        out.append({"target_id": str(t.get("targetId") or ""), "ad_group_id": str(t.get("adGroupId") or ""),
                    "label": label or (t.get("expressionType") or ""),
                    "state": str(t.get("state") or "").upper(), "bid": t.get("bid")})
    return out


def list_negative_keywords(creds, marketplace, campaign_id):
    return [{"id": str(k.get("keywordId") or ""), "ad_group_id": str(k.get("adGroupId") or ""),
             "text": k.get("keywordText") or "", "match_type": k.get("matchType") or "",
             "state": str(k.get("state") or "").upper()}
            for k in _list("/sp/negativeKeywords/list", "negativeKeywords", creds, marketplace,
                           dict(_states(False), **_in_campaign(campaign_id)))]


def _multi(got, key):
    """A 207 multi-status reply -> (ok: bool, error text)."""
    part = (got or {}).get(key) or {}
    errs = part.get("error") or []
    if errs:
        e = errs[0] or {}
        msgs = [x.get("errorValue", {}) for x in (e.get("errors") or [])]
        txt = "; ".join(json.dumps(m)[:200] for m in msgs) or json.dumps(e)[:300]
        return False, txt
    return bool(part.get("success")), ""


def update_campaign(creds, marketplace, campaign_id, state=None, budget=None):
    item = {"campaignId": str(campaign_id)}
    if state:
        item["state"] = state
    if budget is not None:
        item["budget"] = {"budget": float(budget), "budgetType": "DAILY"}
    return _multi(_call("PUT", "/sp/campaigns", creds, marketplace, {"campaigns": [item]}),
                  "campaigns")


def update_ad_group(creds, marketplace, ad_group_id, state=None, default_bid=None):
    item = {"adGroupId": str(ad_group_id)}
    if state:
        item["state"] = state
    if default_bid is not None:
        item["defaultBid"] = float(default_bid)
    return _multi(_call("PUT", "/sp/adGroups", creds, marketplace, {"adGroups": [item]}),
                  "adGroups")


def update_keyword(creds, marketplace, keyword_id, state=None, bid=None):
    item = {"keywordId": str(keyword_id)}
    if state:
        item["state"] = state
    if bid is not None:
        item["bid"] = float(bid)
    return _multi(_call("PUT", "/sp/keywords", creds, marketplace, {"keywords": [item]}),
                  "keywords")


def update_target(creds, marketplace, target_id, state=None, bid=None):
    item = {"targetId": str(target_id)}
    if state:
        item["state"] = state
    if bid is not None:
        item["bid"] = float(bid)
    return _multi(_call("PUT", "/sp/targets", creds, marketplace, {"targetingClauses": [item]}),
                  "targetingClauses")


def add_negative_keyword(creds, marketplace, campaign_id, ad_group_id, text, match_type):
    item = {"campaignId": str(campaign_id), "adGroupId": str(ad_group_id),
            "keywordText": str(text), "matchType": match_type, "state": "ENABLED"}
    return _multi(_call("POST", "/sp/negativeKeywords", creds, marketplace,
                        {"negativeKeywords": [item]}), "negativeKeywords")
