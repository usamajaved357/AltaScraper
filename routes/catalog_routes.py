"""routes/catalog_routes.py -- ASIN research (READ-ONLY).

One endpoint: look up ANY ASIN's live catalogue data (title, brand, product type, specs,
and image URLs) via the SP-API Catalog Items API. This needs only the Catalog role that the
app already uses during generation -- NO listing/publish rights, and it writes NOTHING to
Amazon. It's the "research a competitor ASIN, then build your own listing" step, surfaced as
a standalone tool. The UI hands the result off to the existing Image Studio + copy generator.
"""
from flask import request, jsonify

_INCLUDED_FULL = ["summaries", "images", "attributes", "productTypes", "salesRanks",
                  "dimensions", "identifiers"]
_INCLUDED_MIN = ["summaries", "productTypes", "images"]


def register(app, *, _cfg, _state, CONFIG_PATH):

    def _real_creds_for(mkt):
        """A connected account's SP-API creds for the requested marketplace (prefer one whose
        default marketplace matches; else any with real creds). Catalog reads are marketplace-
        scoped, so any valid creds with the Catalog role can read that marketplace's catalogue."""
        try:
            import accounts as _acc
        except Exception:
            return None, None, None
        cfg = _cfg() or {}
        try:
            accts = _acc.load_accounts(cfg, CONFIG_PATH) or []
        except Exception:
            accts = list(cfg.get("accounts", []) or [])

        def real(a):
            try:
                c = _acc.account_creds(a)
                rt = str((c or {}).get("refresh_token", "") or "")
                if rt and not rt.startswith("PUT_"):
                    return c
            except Exception:
                pass
            return None

        # 1) an account whose default marketplace matches
        for a in accts:
            if str(a.get("default_marketplace", "")).upper() == mkt:
                c = real(a)
                if c:
                    return c, a, _acc
        # 2) the active account, then any account, with real creds
        aid = _state.get("active_account_id")
        ordered = [a for a in accts if a.get("id") == aid] + accts
        for a in ordered:
            c = real(a)
            if c:
                return c, a, _acc
        return None, None, _acc

    @app.route("/catalog/lookup", methods=["POST"])
    def catalog_lookup():
        b = request.get_json(force=True) or {}
        asin = str(b.get("asin", "") or "").strip().upper()
        mkt = str(b.get("marketplace", "") or _state.get("active_marketplace") or "UK").upper()
        if mkt == "GB":
            mkt = "UK"
        if not asin or len(asin) < 8:
            return jsonify({"ok": False, "error": "Enter a valid ASIN (e.g. B0XXXXXXXX)."}), 400

        creds, acc, _acc = _real_creds_for(mkt)
        if not creds:
            return jsonify({"ok": False, "error": "No connected account has SP-API credentials to "
                            "read the catalogue. Add credentials to an account first."}), 400
        try:
            from sp_api.api import CatalogItemsV20220401 as CatalogItems
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api Catalog not available: {e}"}), 500

        mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
        mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.UK
        try:
            cat = CatalogItems(credentials=creds, marketplace=mkt_enum, timeout=30)
            try:
                res = cat.get_catalog_item(asin=asin, includedData=_INCLUDED_FULL,
                                           marketplaceIds=[mid] if mid else None)
            except Exception as full_err:
                # Some roles read the catalogue but are denied the richer blocks (attributes),
                # and Amazon then denies the WHOLE call -- retry with the minimal always-on set.
                le = (type(full_err).__name__ + " " + str(full_err)).lower()
                if any(k in le for k in ("forbidden", "unauthorized", "accessdenied", "access to requested")):
                    res = cat.get_catalog_item(asin=asin, includedData=_INCLUDED_MIN,
                                               marketplaceIds=[mid] if mid else None)
                else:
                    raise
            p = res.payload if hasattr(res, "payload") else (res or {})
        except Exception as e:
            import traceback
            print(f"[catalog/lookup] EXCEPTION for {asin} ({mkt}):")
            traceback.print_exc()
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}), 502

        summaries = p.get("summaries") or [{}]
        summ = summaries[0] if summaries else {}
        title = summ.get("itemName", "") or ""
        brand = summ.get("brand", "") or summ.get("manufacturer", "") or ""
        pt_list = p.get("productTypes") or [{}]
        product_type = (pt_list[0].get("productType", "") if pt_list else "") or ""

        attributes = {}
        for k, vlist in (p.get("attributes") or {}).items():
            if not isinstance(vlist, list) or not vlist:
                continue
            vals = []
            for entry in vlist:
                v = entry.get("value") if isinstance(entry, dict) else entry
                if v is not None and str(v).strip() and str(v) not in vals:
                    vals.append(str(v).strip())
            if vals:
                attributes[k] = " | ".join(vals)[:300]
        for sk, dest in (("manufacturer", "manufacturer"), ("modelNumber", "model_number"),
                         ("colorName", "color"), ("size", "size"), ("styleName", "style"),
                         ("packageQuantity", "package_quantity")):
            sv = summ.get(sk)
            if sv and str(sv).strip():
                attributes.setdefault(dest, str(sv).strip())

        images = []
        for img_set in (p.get("images") or []):
            if img_set.get("marketplaceId") in (mid, None, ""):
                for img in img_set.get("images", []):
                    link = img.get("link", "")
                    if link and link not in images:
                        images.append(link)
        # keep the biggest few, de-duped (Amazon returns multiple sizes of the same shot)
        images = images[:12]

        sales_rank = []
        for sr in (p.get("salesRanks") or []):
            for rank in (sr.get("classificationRanks", []) + sr.get("displayGroupRanks", [])):
                t = rank.get("title") or rank.get("classificationName") or ""
                if t:
                    sales_rank.append({"category": t, "rank": rank.get("rank") or rank.get("value") or 0})

        if not title and not images and not attributes:
            return jsonify({"ok": False, "error": "Amazon returned no data for that ASIN in "
                            + mkt + ". Check the ASIN and marketplace."}), 404

        return jsonify({"ok": True, "asin": asin, "marketplace": mkt,
                        "account": (acc.get("label") if acc else ""),
                        "title": title, "brand": brand, "product_type": product_type,
                        "attributes": attributes, "images": images, "sales_rank": sales_rank})
