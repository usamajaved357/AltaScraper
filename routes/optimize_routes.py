"""routes/optimize_routes.py — live-listing optimisation endpoints, extracted from dashboard.py (Phase 3).

register(app, ...) injection pattern; route bodies moved VERBATIM (CLAUDE.md §10).
Optimize-only helpers (_extract_editable_fields, _fetch_page_text) move in with the
routes as nested functions; shared helpers (_state, _cfg, CONFIG_PATH, _build_patches)
are injected (_build_patches is also used by /listing/push_image, which stays in
dashboard.py for now).

Routes: POST /optimize/fetch, POST /optimize/diagnose_fill, POST /optimize/push,
        POST /optimize/from_source
"""
import json
import re

from flask import request, jsonify


def register(app, *, _state, _cfg, CONFIG_PATH, _build_patches):
    """Attach the /optimize/* routes to the existing Flask app."""

    @app.route("/optimize/fetch", methods=["POST"])
    def optimize_fetch():
        """Read-only: pull a live listing's CURRENT data from Amazon so the user can
        draft edits against it. Nothing is changed. Uses getListingsItem."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        sku = (b.get("sku", "") or "").strip()
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        if not sku:
            return jsonify({"ok": False, "error": "missing sku"}), 400
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            return jsonify({"ok": False, "error": "connect this account first"}), 400
        creds = _acc.account_creds(acc)
        seller = acc.get("seller_id", "")
        try:
            from sp_api.api import ListingsItemsV20210801 as LI
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
        mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
        mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
        try:
            li = LI(credentials=creds, marketplace=mkt_enum)
            resp = li.get_listings_item(
                seller, sku,
                marketplaceIds=[mid] if mid else None,
                includedData="attributes,summaries,issues")
            pay = resp.payload if hasattr(resp, "payload") else resp
        except Exception as e:
            return jsonify({"ok": False, "error": f"getListingsItem failed: {str(e)[:240]}"}), 502
        # extract the editable fields from the attributes block
        attrs = (pay or {}).get("attributes", {}) if isinstance(pay, dict) else {}
        summaries = (pay or {}).get("summaries", []) if isinstance(pay, dict) else []
        issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
        ptype = ""
        if summaries and isinstance(summaries, list):
            ptype = summaries[0].get("productType", "")
        fields = _extract_editable_fields(attrs)
        # parse issues into a tidy, actionable list naming the exact attributes at fault
        parsed_issues = []
        for iss in issues:
            if not isinstance(iss, dict):
                continue
            names = iss.get("attributeNames") or iss.get("attributeName") or []
            if isinstance(names, str):
                names = [names]
            parsed_issues.append({
                "code": iss.get("code", ""),
                "message": iss.get("message", ""),
                "severity": iss.get("severity", ""),    # ERROR / WARNING / INFO
                "attributes": names,
                "enforcement": (iss.get("enforcements", {}) or {}).get("actions", []),
            })
        # which status does Amazon report?
        listing_status = ""
        if summaries and isinstance(summaries, list):
            st_arr = summaries[0].get("status", []) or []
            listing_status = ", ".join(st_arr) if isinstance(st_arr, list) else str(st_arr)
        return jsonify({"ok": True, "sku": sku, "asin": (summaries[0].get("asin", "") if summaries else ""),
                        "product_type": ptype, "marketplace": mkt, "marketplace_id": mid,
                        "fields": fields, "raw_attributes": attrs,
                        "issues": parsed_issues, "listing_status": listing_status})


    @app.route("/optimize/diagnose_fill", methods=["POST"])
    def optimize_diagnose_fill():
        """Look at the listing's SP-API issues (the real reason for the red dot) and
        ask the AI to suggest values ONLY for the flagged attributes. Returns
        suggestions for the user to review — nothing is pushed here."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        sku = (b.get("sku", "") or "").strip()
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        if not sku:
            return jsonify({"ok": False, "error": "missing sku"}), 400
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        creds = _acc.account_creds(acc)
        seller = acc.get("seller_id", "")
        mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
        try:
            from sp_api.api import ListingsItemsV20210801 as LI
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
        mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
        try:
            li = LI(credentials=creds, marketplace=mkt_enum)
            resp = li.get_listings_item(seller, sku, marketplaceIds=[mid] if mid else None,
                                        includedData="attributes,summaries,issues")
            pay = resp.payload if hasattr(resp, "payload") else resp
        except Exception as e:
            return jsonify({"ok": False, "error": f"getListingsItem failed: {str(e)[:240]}"}), 502
        attrs = (pay or {}).get("attributes", {}) if isinstance(pay, dict) else {}
        summaries = (pay or {}).get("summaries", []) if isinstance(pay, dict) else []
        issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
        ptype = summaries[0].get("productType", "") if summaries else ""
        title = ""
        try:
            title = attrs.get("item_name", [{}])[0].get("value", "")
        except Exception:
            title = ""

        # collect the attributes Amazon is complaining about (missing/invalid)
        flagged = []
        for iss in issues:
            if not isinstance(iss, dict):
                continue
            names = iss.get("attributeNames") or iss.get("attributeName") or []
            if isinstance(names, str):
                names = [names]
            for nm in names:
                flagged.append({"attribute": nm, "message": iss.get("message", ""),
                                "severity": iss.get("severity", "")})
        # de-dup by attribute name
        seen = set(); flagged_u = []
        for f in flagged:
            if f["attribute"] and f["attribute"] not in seen:
                seen.add(f["attribute"]); flagged_u.append(f)

        if not flagged_u:
            return jsonify({"ok": True, "flagged": [], "suggestions": {},
                            "note": "No attribute-level issues reported. The red status may be due to "
                                    "pricing, images, or a category review rather than a missing field."})

        # ask the AI to suggest values for ONLY the flagged attributes
        key = (_cfg().get("anthropic_api_key") or "").strip()
        if not key:
            return jsonify({"ok": True, "flagged": flagged_u, "suggestions": {},
                            "note": "No anthropic_api_key set — showing the flagged fields without AI suggestions."})
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            # give the AI the product context + the current attribute values for reference
            ctx_attrs = {k: attrs.get(k) for k in list(attrs.keys())[:60]}
            sys = (
                "You are an Amazon catalog specialist. Given a product and a list of attributes Amazon "
                "flagged as missing or invalid, suggest a sensible, compliant value for EACH flagged "
                "attribute. Use the product title and existing attributes to infer realistic values "
                "(e.g. dimensions, material, color, unit). For measurements include the unit. If a value "
                "genuinely cannot be inferred and would need the seller to measure/know it, return null for "
                "that attribute and a short 'needs' note. Do NOT invent certifications, safety claims, or "
                "identifiers (UPC/EAN/GTIN). Return ONLY JSON: "
                '{"attribute_name": {"value": <value or null>, "note": "<short reason / what unit>"}}.'
            )
            user = (f"Product title: {title}\nProduct type: {ptype}\n\n"
                    f"Flagged attributes:\n{json.dumps(flagged_u, ensure_ascii=False)}\n\n"
                    f"Existing attributes (for reference):\n{json.dumps(ctx_attrs, ensure_ascii=False)[:6000]}\n\n"
                    "Suggest values for the flagged attributes now. JSON only.")
            msg = client.messages.create(model="claude-sonnet-4-5", max_tokens=1500,
                                         system=sys, messages=[{"role": "user", "content": user}])
            raw = "".join(getattr(x, "text", "") for x in msg.content).strip()
            raw = re.sub(r"^```json|```$", "", raw).strip()
            suggestions = json.loads(raw) if raw else {}
        except Exception as e:
            return jsonify({"ok": True, "flagged": flagged_u, "suggestions": {},
                            "note": f"Could not get AI suggestions ({str(e)[:120]}). Showing flagged fields only."})

        return jsonify({"ok": True, "flagged": flagged_u, "suggestions": suggestions,
                        "product_type": ptype, "title": title})


    def _extract_editable_fields(attrs):
        """Pull current values for the editable fields out of the SP-API attributes
        object (which is {attr_name: [{value/...}]}). Returns a tidy dict."""
        def first(name, key="value"):
            v = attrs.get(name)
            if isinstance(v, list) and v:
                item = v[0]
                if isinstance(item, dict):
                    return item.get(key, item.get("value", ""))
            return ""
        # bullets are bullet_point: list of {value}
        bullets = []
        bp = attrs.get("bullet_point")
        if isinstance(bp, list):
            bullets = [x.get("value", "") for x in bp if isinstance(x, dict)]
        # price
        price = ""
        pp = attrs.get("purchasable_offer")
        try:
            if isinstance(pp, list) and pp:
                price = pp[0]["our_price"][0]["schedule"][0]["value_with_tax"]
        except Exception:
            price = first("list_price", "value") or ""
        return {
            "title": first("item_name"),
            "bullets": bullets,
            "description": first("product_description"),
            "price": str(price),
            "main_image": first("main_product_image_locator", "media_location") or first("main_product_image_locator"),
        }


    @app.route("/optimize/push", methods=["POST"])
    def optimize_push():
        """GATED push: apply ONLY the fields the user explicitly approved to the live
        listing via patchListingsItem. The frontend sends only checked fields; we
        double-check an explicit confirm flag is present."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        if not b.get("confirmed"):
            return jsonify({"ok": False, "error": "push not confirmed"}), 400
        aid = b.get("id", "") or _state.get("active_account_id", "")
        sku = (b.get("sku", "") or "").strip()
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        ptype = b.get("product_type", "") or ""
        changes = b.get("changes", {})   # {field: new_value} -- ONLY approved fields
        if not sku or not changes:
            return jsonify({"ok": False, "error": "missing sku or no approved changes"}), 400
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            return jsonify({"ok": False, "error": "connect this account first"}), 400
        creds = _acc.account_creds(acc)
        seller = acc.get("seller_id", "")
        mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
        # build JSON Patch operations for only the approved fields
        patches = _build_patches(changes)
        if not patches:
            return jsonify({"ok": False, "error": "no patchable fields in approved changes"}), 400
        try:
            from sp_api.api import ListingsItemsV20210801 as LI
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
        mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
        body = {"productType": ptype or "PRODUCT", "patches": patches}
        try:
            li = LI(credentials=creds, marketplace=mkt_enum)
            resp = li.patch_listings_item(
                seller, sku,
                marketplaceIds=[mid] if mid else None,
                body=body)
            pay = resp.payload if hasattr(resp, "payload") else resp
        except Exception as e:
            return jsonify({"ok": False, "error": f"patchListingsItem failed: {str(e)[:240]}"}), 502
        status = (pay or {}).get("status", "") if isinstance(pay, dict) else ""
        issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
        ok = status.upper() in ("ACCEPTED", "VALID") or not issues
        return jsonify({"ok": ok, "status": status, "issues": issues,
                        "pushed_fields": list(changes.keys()), "raw": pay})


    def _fetch_page_text(url, limit=9000):
        """Fetch a web page and return cleaned visible text (best-effort)."""
        try:
            import urllib.request, gzip, io, re as _re
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"})
            raw = urllib.request.urlopen(req, timeout=20).read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            html = raw.decode("utf-8", "replace")
            # strip scripts/styles, collapse tags to text
            html = _re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
            text = _re.sub(r"(?s)<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:limit]
        except Exception as e:
            return f"__FETCH_ERROR__: {e}"


    @app.route("/optimize/from_source", methods=["POST"])
    def optimize_from_source():
        """Read the REAL product from an eBay and/or Amazon URL, then rewrite the
        listing copy (title/bullets/description) for the user's own brand. Returns
        JSON suggestions for the optimize editor to apply. Nothing is sent to Amazon."""
        b = request.get_json(force=True) or {}
        ebay_url = (b.get("ebay_url", "") or "").strip()
        amazon_url = (b.get("amazon_url", "") or "").strip()
        current = b.get("current", {}) or {}        # current title/bullets/description
        product_type = b.get("product_type", "")
        instruction = (b.get("instruction", "") or "").strip()   # user's custom request to the AI
        aid = b.get("id", "") or _state.get("active_account_id", "")
        if not ebay_url and not amazon_url and not instruction:
            return jsonify({"ok": False, "error": "Provide a product link and/or a custom instruction."}), 400

        # resolve the account's brand as OPTIONAL context (do NOT force it into copy,
        # and never fall back to the account label as a brand)
        brand = ""
        try:
            import accounts as _acc
            acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
            if acc:
                bl = [x for x in (acc.get("brands") or []) if x and x.strip()]
                brand = bl[0] if bl else ""
        except Exception:
            brand = ""

        sources = []
        for label, u in (("eBay", ebay_url), ("Amazon", amazon_url)):
            if not u:
                continue
            txt = _fetch_page_text(u)
            if txt.startswith("__FETCH_ERROR__"):
                sources.append(f"[{label} link could not be fetched: {txt}]")
            else:
                sources.append(f"=== {label} source page ===\n{txt}")
        source_blob = "\n\n".join(sources) if sources else "(no source link provided — work from the current copy and the user's instruction)"

        key = (_cfg().get("anthropic_api_key") or "").strip()
        if not key:
            return jsonify({"ok": False, "error": "No anthropic_api_key in config.json"}), 400
        try:
            import anthropic
        except ImportError:
            return jsonify({"ok": False, "error": "anthropic not installed"}), 500

        # load compliance + IP guidance if present so the rewrite respects them
        compliance_hint = ""
        try:
            import os as _o
            if _o.path.exists("ip_rules.json"):
                ipr = json.load(open("ip_rules.json", encoding="utf-8"))
                forb = ipr.get("forbidden_phrases", []) or ipr.get("forbidden", [])
                if forb:
                    compliance_hint += ("\nDo NOT use these trademarked/forbidden phrases: "
                                        + ", ".join(list(forb)[:60]) + ".")
        except Exception:
            pass

        system = (
            "You are an expert Amazon listing copywriter helping a seller fix/optimize a live listing. "
            "You may be given: the raw text of the REAL product page (eBay/Amazon), the seller's current "
            "copy, and a custom instruction from the seller. Identify what the product ACTUALLY is, then "
            "write accurate, conversion-focused Amazon copy.\n"
            "HARD RULES:\n"
            "- Follow the seller's custom instruction exactly when given (e.g. whether or not to include a "
            "brand name, tone, focus, length).\n"
            "- Be factually faithful to the real product; do NOT invent specs not supported by the source.\n"
            "- Do NOT copy the source text verbatim; do NOT mention the source seller or their brand.\n"
            "- Do NOT force any brand name into the title or copy unless the seller asks for it. If the "
            "seller says not to include a brand, write generic brandless copy.\n"
            "- Stay Amazon-compliant: no medical/disease claims, no '#1/best seller' unverifiable claims, "
            "no guarantee/cure language." + compliance_hint + "\n"
            'Return ONLY JSON: {"title": "<=200 chars", "bullets": [5 strings], "description": "2-4 short paragraphs"}. '
            "No preamble, no markdown."
        )
        brand_line = (f"Seller's brand (available if the instruction asks to use it; otherwise do NOT insert it): {brand}\n"
                      if brand else "Seller has no brand set — write brandless unless the instruction says otherwise.\n")
        user_msg = (
            f"Product type: {product_type or 'unknown'}\n"
            + brand_line
            + (f"\nSELLER'S CUSTOM INSTRUCTION (follow this):\n{instruction}\n" if instruction else "\n(No custom instruction given — just produce accurate, optimized copy.)\n")
            + f"\nSELLER'S CURRENT COPY:\n{json.dumps(current, ensure_ascii=False)[:2000]}\n\n"
            f"REAL PRODUCT SOURCE TEXT:\n{source_blob[:14000]}\n\n"
            "Now produce the JSON copy following all rules and the seller's instruction."
        )
        try:
            client = anthropic.Anthropic(api_key=key)
            resp = client.messages.create(
                model="claude-sonnet-4-5", max_tokens=1500,
                system=system, messages=[{"role": "user", "content": user_msg}])
            txt = "".join(getattr(blk, "text", "") for blk in resp.content).strip()
            txt = txt.replace("```json", "").replace("```", "").strip()
            data = json.loads(txt)
            return jsonify({"ok": True, "suggestion": {
                "title": data.get("title", ""),
                "bullets": data.get("bullets", []) if isinstance(data.get("bullets"), list) else [],
                "description": data.get("description", ""),
            }, "brand": brand, "fetched": [s[:60] for s in sources]})
        except json.JSONDecodeError:
            return jsonify({"ok": False, "error": "AI returned non-JSON; try again."}), 502
        except Exception as e:
            return jsonify({"ok": False, "error": f"AI error: {str(e)[:200]}"}), 502
