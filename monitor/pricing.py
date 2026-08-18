"""monitor/pricing.py — getItemOffers calls + normalization (Stage 3).

SP-API ONLY. Read-only. getItemOffers is BY ASIN (cross-account) — you don't own the ASIN.
Returns a normalized offer set; never raises. Field mapping is grounded in the live response
verified 2026-07-31 (seller NAME is not returned — SellerId only; landed price is computed).
"""
import time

from domain import amazon_flags as _flags


def _mk_enum(mkt):
    from sp_api.base import Marketplaces
    return getattr(Marketplaces, str(mkt).upper(), None) or Marketplaces.UK




def _normalize(pay, asin, marketplace, condition):
    """Turn a getItemOffers payload into our normalized {ok, offers, summary} shape. Shared by
    the single call and every sub-response of the BATCH call."""
    out = {"ok": True, "asin": asin, "marketplace": marketplace, "condition": condition,
           "offers": [], "summary": {}, "error": ""}
    norm = []
    for o in (pay.get("Offers", []) or []):
        lp = o.get("ListingPrice") or {}
        sh = o.get("Shipping") or {}
        fb = o.get("SellerFeedbackRating") or {}
        price = lp.get("Amount")
        ship = sh.get("Amount") or 0
        norm.append({
            "seller_id": o.get("SellerId", ""),
            "price": price, "currency": lp.get("CurrencyCode", ""), "shipping": ship,
            "landed": (round((price or 0) + (ship or 0), 2) if price is not None else None),
            # Through domain/amazon_flags rather than bool(). Amazon sends these
            # as real booleans on this API TODAY, but it sends IsGift on the
            # Orders API as the string "false" and BuyerRequestedCancel as an
            # object -- and bool() of either is True, which is what made every
            # order claim the buyer wanted to cancel it. One reader, so a shape
            # change here cannot quietly turn every competitor into a Buy Box
            # winner (CLAUDE.md Rule 12).
            "fba": _flags.truth(o.get("IsFulfilledByAmazon")),
            "condition": o.get("SubCondition", ""),
            "buybox": _flags.truth(o.get("IsBuyBoxWinner")),
            "feedback_pct": fb.get("SellerPositiveFeedbackRating"),
            "feedback_count": fb.get("FeedbackCount"),
            "prime": _flags.truth((o.get("PrimeInformation") or {}).get("IsPrime")),
            "ships_from": (o.get("ShipsFrom") or {}).get("Country", ""),
        })
    summ = pay.get("Summary", {}) or {}
    out["summary"] = {"total_offer_count": summ.get("TotalOfferCount"), "seller_count": len(norm),
                      "buybox_seller": next((x["seller_id"] for x in norm if x["buybox"]), None),
                      "buybox_price": _first_buybox_price(summ)}
    out["offers"] = norm
    return out


def fetch_offers_batch(creds, requests, condition="New", log=print):
    """getItemOffersBatch: up to 20 (asin x marketplace) requests in ONE API call. `requests` is a
    list of {'asin','marketplace'}. Returns a list of normalized results (same order), each tagged
    with asin+marketplace. Retries the whole batch once on a 429. Never raises."""
    reqs = list(requests)[:20]
    if not reqs:
        return []
    try:
        from sp_api.api import Products
        from sp_api.base import Marketplaces
        import accounts as _acc
    except Exception as e:
        return [{"ok": False, "asin": r["asin"], "marketplace": r["marketplace"],
                 "offers": [], "summary": {}, "error": f"sp_api unavailable: {e}"} for r in reqs]
    body = []
    for r in reqs:
        mid = _acc.marketplace_id(r["marketplace"]) if hasattr(_acc, "marketplace_id") else ""
        body.append({"uri": f"/products/pricing/v0/items/{r['asin']}/offers",
                     "method": "GET", "MarketplaceId": mid,
                     "ItemCondition": r.get("condition") or condition})
    # one client; region is the same for all EU marketplaces so any EU enum works for the endpoint
    prods = Products(credentials=creds, marketplace=_mk_enum(reqs[0]["marketplace"]), timeout=90)
    resp = None
    for attempt in range(2):
        try:
            resp = prods.get_item_offers_batch(body)
            break
        except Exception as e:
            m = str(e).lower()
            if ("quota" in m or "throttl" in m or "429" in m or "too many" in m) and attempt == 0:
                time.sleep(8); continue
            return [{"ok": False, "asin": r["asin"], "marketplace": r["marketplace"],
                     "offers": [], "summary": {}, "error": f"{type(e).__name__}: {str(e)[:160]}"}
                    for r in reqs]
    pay = resp.payload if hasattr(resp, "payload") else resp
    responses = (pay or {}).get("responses", []) if isinstance(pay, dict) else []
    out = []
    for i, r in enumerate(reqs):
        sub = responses[i] if i < len(responses) else {}
        code = ((sub.get("status") or {}).get("statusCode")) if isinstance(sub, dict) else None
        spay = ((sub.get("body") or {}).get("payload")) if isinstance(sub, dict) else None
        if code == 200 and isinstance(spay, dict):
            out.append(_normalize(spay, r["asin"], r["marketplace"], condition))
        else:
            # NOT_FOUND (404) etc. -> a valid "no offers here" result (used by dead-market detection)
            reason = ((sub.get("status") or {}).get("reasonPhrase") or f"HTTP {code}") if isinstance(sub, dict) else "no response"
            res = {"ok": True, "asin": r["asin"], "marketplace": r["marketplace"], "condition": condition,
                   "offers": [], "summary": {"seller_count": 0, "buybox_seller": None,
                                             "total_offer_count": 0}, "error": ""}
            if code and code != 404:
                res["ok"] = False; res["error"] = str(reason)[:160]
            out.append(res)
    return out


def _first_buybox_price(summ):
    try:
        bbp = summ.get("BuyBoxPrices") or []
        if bbp:
            lp = bbp[0].get("LandedPrice") or bbp[0].get("ListingPrice") or {}
            return lp.get("Amount")
    except Exception:
        pass
    return None
