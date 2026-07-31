"""monitor/pricing.py — getItemOffers calls + normalization (Stage 3).

SP-API ONLY. Read-only. getItemOffers is BY ASIN (cross-account) — you don't own the ASIN.
Returns a normalized offer set; never raises. Field mapping is grounded in the live response
verified 2026-07-31 (seller NAME is not returned — SellerId only; landed price is computed).
"""
import time


def _mk_enum(mkt):
    from sp_api.base import Marketplaces
    return getattr(Marketplaces, str(mkt).upper(), None) or Marketplaces.UK


def fetch_offers(creds, asin, marketplace, condition="New", log=print):
    """ALL current offers on `asin` in `marketplace`. Normalized dict, never raises.
    NOTE: getItemOffers returns Amazon's ~20 most-competitive offers, not every offer."""
    out = {"ok": False, "asin": asin, "marketplace": marketplace, "condition": condition,
           "offers": [], "summary": {}, "error": ""}
    try:
        from sp_api.api import Products
    except Exception as e:
        out["error"] = f"sp_api unavailable: {e}"; return out
    try:
        import accounts as _acc
        _ = _acc.marketplace_id(marketplace) if hasattr(_acc, "marketplace_id") else ""
    except Exception:
        pass
    try:
        prods = Products(credentials=creds, marketplace=_mk_enum(marketplace), timeout=60)
        resp = None
        for attempt in range(2):
            try:
                resp = prods.get_item_offers(asin, item_condition=condition)
                break
            except Exception as e:
                m = str(e).lower()
                if ("quota" in m or "throttl" in m or "429" in m or "too many" in m) and attempt == 0:
                    time.sleep(5); continue
                out["error"] = f"{type(e).__name__}: {str(e)[:180]}"; return out
        pay = resp.payload if hasattr(resp, "payload") else resp
        pay = pay if isinstance(pay, dict) else {}
        norm = []
        for o in (pay.get("Offers", []) or []):
            lp = o.get("ListingPrice") or {}
            sh = o.get("Shipping") or {}
            fb = o.get("SellerFeedbackRating") or {}
            price = lp.get("Amount")
            ship = sh.get("Amount") or 0
            norm.append({
                "seller_id": o.get("SellerId", ""),
                "price": price,
                "currency": lp.get("CurrencyCode", ""),
                "shipping": ship,
                "landed": (round((price or 0) + (ship or 0), 2) if price is not None else None),
                "fba": bool(o.get("IsFulfilledByAmazon")),
                "condition": o.get("SubCondition", ""),
                "buybox": bool(o.get("IsBuyBoxWinner")),
                "feedback_pct": fb.get("SellerPositiveFeedbackRating"),
                "feedback_count": fb.get("FeedbackCount"),
                "prime": bool((o.get("PrimeInformation") or {}).get("IsPrime")),
                "ships_from": (o.get("ShipsFrom") or {}).get("Country", ""),
            })
        summ = pay.get("Summary", {}) or {}
        bb = next((x["seller_id"] for x in norm if x["buybox"]), None)
        out["summary"] = {
            "total_offer_count": summ.get("TotalOfferCount"),
            "seller_count": len(norm),
            "buybox_seller": bb,
            "buybox_price": _first_buybox_price(summ),
        }
        out["offers"] = norm
        out["ok"] = True
        return out
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:180]}"; return out


def _first_buybox_price(summ):
    try:
        bbp = summ.get("BuyBoxPrices") or []
        if bbp:
            lp = bbp[0].get("LandedPrice") or bbp[0].get("ListingPrice") or {}
            return lp.get("Amount")
    except Exception:
        pass
    return None
