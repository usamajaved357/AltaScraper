"""listing/handling.py — bulk handling-time (lead_time_to_ship_max_days) updates.

One job: change a LIVE listing's handling time on Amazon, safely.

Handling time on Amazon lives in the `fulfillment_availability` attribute as
`lead_time_to_ship_max_days`. To change it WITHOUT guessing the attribute's shape
(Rule 4) we READ the listing's current fulfillment_availability via getListingsItem,
change ONLY that one number, and PATCH the whole array back. Reading Amazon's own
current value as the template preserves quantity + fulfillment_channel_code and never
invents a structure.

Seller-scope only: patch/getListingsItem answer for the token's own seller, so a
borrowed (read-only) workspace is refused — it must never write into a lender's catalogue.
"""


def _marketplace_enum(mkt):
    from sp_api.base import Marketplaces
    return getattr(Marketplaces, mkt, None) or Marketplaces.UK


def push_handling_time(cfg, acc, sku, days, marketplace):
    """Set lead_time_to_ship_max_days = `days` on ONE live listing.

    Returns {ok, sku, before, after, product_type, error, issues}. `before` is the
    handling time Amazon had (None if it had none); `after` is what we set. Never raises
    — every failure is returned so the caller can report it per-SKU.
    """
    out = {"ok": False, "sku": sku, "before": None, "after": days,
           "product_type": "", "error": "", "issues": []}
    try:
        import accounts as _acc
    except Exception as e:
        out["error"] = f"accounts module unavailable: {e}"; return out
    # Seller scope: a borrowed token would patch the LENDER's listing. Refuse.
    try:
        if hasattr(_acc, "seller_scope_allowed") and not _acc.seller_scope_allowed(acc):
            out["error"] = (f"{acc.get('label') or acc.get('id')} is read-only (borrows catalogue "
                            f"access, has no Amazon account of its own) — it cannot write to Amazon.")
            return out
    except Exception:
        pass
    try:
        from sp_api.api import ListingsItemsV20210801 as LI
    except Exception as e:
        out["error"] = f"sp_api unavailable: {e}"; return out

    mkt = (marketplace or acc.get("default_marketplace") or "UK").upper()
    mkt = "UK" if mkt == "GB" else mkt
    mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
    locale = "en_US" if mkt == "US" else "en_GB"
    seller = acc.get("seller_id", "")
    try:
        li = LI(credentials=_acc.account_creds(acc), marketplace=_marketplace_enum(mkt), timeout=60)
    except Exception as e:
        out["error"] = f"could not init client: {str(e)[:160]}"; return out

    # 1) READ the current attributes + product type (the template we patch on top of).
    try:
        r = li.get_listings_item(seller, sku, marketplaceIds=[mid] if mid else None,
                                 issueLocale=locale, includedData=["attributes", "summaries"])
        pay = r.payload if hasattr(r, "payload") else (r or {})
    except Exception as e:
        msg = str(e)
        out["error"] = ("Amazon has no listing with this SKU (nothing to update)."
                        if "NOT_FOUND" in msg else f"read failed: {msg[:160]}")
        return out
    pay = pay if isinstance(pay, dict) else {}
    attrs = pay.get("attributes", {}) or {}
    summaries = pay.get("summaries", []) or []
    pt = ""
    if summaries and isinstance(summaries[0], dict):
        pt = summaries[0].get("productType", "") or ""
    if not pt:
        pt = attrs.get("product_type") or ""
        if isinstance(pt, list) and pt:
            pt = (pt[0] or {}).get("value", "") if isinstance(pt[0], dict) else str(pt[0])
    out["product_type"] = pt or ""
    if not pt:
        out["error"] = "could not determine the listing's product type from Amazon"; return out

    # 2) MODIFY only lead_time_to_ship_max_days, keeping every other field intact.
    fa = attrs.get("fulfillment_availability")
    had_fa = isinstance(fa, list) and len(fa) > 0
    if had_fa:
        try:
            out["before"] = fa[0].get("lead_time_to_ship_max_days")
        except Exception:
            out["before"] = None
        new_fa = []
        for entry in fa:
            e2 = dict(entry) if isinstance(entry, dict) else {}
            e2["lead_time_to_ship_max_days"] = days
            new_fa.append(e2)
    else:
        # No fulfillment_availability yet (e.g. FBA, or handling never set). Add a minimal
        # merchant-fulfilled entry. Amazon rejects this for FBA-only listings — reported per-SKU.
        new_fa = [{"fulfillment_channel_code": "DEFAULT", "lead_time_to_ship_max_days": days}]

    body = {"productType": pt, "patches": [{
        "op": "replace" if had_fa else "add",
        "path": "/attributes/fulfillment_availability",
        "value": new_fa,
    }]}

    # 3) PATCH it back.
    try:
        pr = li.patch_listings_item(seller, sku, marketplaceIds=[mid] if mid else None,
                                    issueLocale=locale, body=body)
        ppay = pr.payload if hasattr(pr, "payload") else (pr or {})
    except Exception as e:
        out["error"] = f"patch failed: {str(e)[:200]}"; return out
    ppay = ppay if isinstance(ppay, dict) else {}
    status = str(ppay.get("status", "")).upper()
    issues = ppay.get("issues", []) or []
    out["issues"] = [{"severity": x.get("severity"), "code": x.get("code"),
                      "message": str(x.get("message", ""))[:220]} for x in issues[:6]]
    errs = [x for x in issues if str(x.get("severity", "")).upper() == "ERROR"]
    if errs:
        out["error"] = str(errs[0].get("message", ""))[:220]
        out["ok"] = False
    else:
        # ACCEPTED means Amazon queued the change (it applies within minutes).
        out["ok"] = status in ("ACCEPTED", "VALID", "")
        if not out["ok"] and not out["error"]:
            out["error"] = f"unexpected status: {status or '(none)'}"
    out["status"] = status
    return out
