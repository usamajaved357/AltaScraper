"""routes/live_routes.py — extracted from dashboard.py (Phase 3). Bodies VERBATIM.

Auto-extracted @app.route("/live...") funcs; shared helpers injected. Verified with
verify_free_vars.py.
"""
from flask import request, jsonify, Response, send_from_directory
import urllib


def register(app, *, CONFIG_PATH, _IMG_CACHE, _IMG_TTL, _LIVE_CACHE, _LIVE_TTL, _cfg, _estimate_profit, _parse_listings_report, _resolve_cogs, _state, _APLUS_CACHE=None, _APLUS_TTL=1800):
    """Attach the /live routes to the existing Flask app."""

    if _APLUS_CACHE is None:
        _APLUS_CACHE = {}

    # A+ image references come back as a media-library path, not a URL:
    #   "uploadDestinationId": "aplus-media-library-service-media/<uuid>.png"
    # Verified against Amazon: prefixing it with this host returns the real PNG (200,
    # image/png). Nothing in the API response gives a usable URL directly.
    _APLUS_IMG_HOST = "https://m.media-amazon.com/images/S/"

    def _aplus_img_url(dest):
        d = str(dest or "").strip()
        if not d:
            return ""
        if d.startswith("http://") or d.startswith("https://"):
            return d
        return _APLUS_IMG_HOST + d.lstrip("/")

    def _aplus_walk_images(node, out):
        """Collect every image in a content document, whatever module type holds it.

        The document is a contentModuleList of ~25 possible module shapes (standardText,
        premiumImageCarousel, ...), all but one null per module, each nesting images at a
        different depth. Rather than hard-code the shapes, walk for any dict carrying an
        uploadDestinationId -- the one field every image component has.
        """
        if isinstance(node, dict):
            dest = node.get("uploadDestinationId")
            if dest:
                size = ((node.get("imageCropSpecification") or {}).get("size") or {})
                out.append({
                    "url": _aplus_img_url(dest),
                    "alt": node.get("altText") or "",
                    "w": ((size.get("width") or {}).get("value")),
                    "h": ((size.get("height") or {}).get("value")),
                })
            for v in node.values():
                _aplus_walk_images(v, out)
        elif isinstance(node, list):
            for v in node:
                _aplus_walk_images(v, out)
        return out

    @app.route("/live/aplus", methods=["POST"])
    def live_aplus():
        """A+ content (EBC) for this account's ASINs, straight from Amazon.

        getListingsItem does NOT return A+ modules -- they live behind the separate A+
        Content API -- which is why the product card only ever showed main + secondary
        images. Body: {id, marketplace, force}. Returns {ok, by_asin: {asin: {...}}}.
        """
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        force = bool(b.get("force"))
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        # SELLER SCOPE: these are the account's OWN A+ documents. A borrowed token would
        # return the lender's A+ content.
        if not _acc.seller_scope_allowed(acc):
            return jsonify({"ok": True, "by_asin": {}, "read_only": True}), 200
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400

        import time as _t
        ck = f"{aid}::{mkt}"
        if not force and ck in _APLUS_CACHE and (_t.time() - _APLUS_CACHE[ck]["ts"] < _APLUS_TTL):
            return jsonify({"ok": True, "by_asin": _APLUS_CACHE[ck]["by_asin"], "cached": True})

        try:
            from sp_api.api import AplusContent
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api AplusContent not available: {e}"}), 500
        mid = _acc.marketplace_id(mkt) or ""
        try:
            ap = AplusContent(credentials=_acc.account_creds(acc),
                              marketplace=getattr(Marketplaces, mkt, None) or Marketplaces.UK,
                              timeout=60)
            # 1) every content document on the account (paginated)
            docs, token = [], None
            for _ in range(10):
                kw = {"marketplaceId": mid}
                if token:
                    kw["pageToken"] = token
                r = ap.search_content_documents(**kw)
                pay = r.payload if hasattr(r, "payload") else r
                docs.extend((pay or {}).get("contentMetadataRecords", []) or [])
                token = (pay or {}).get("nextPageToken")
                if not token:
                    break
            by_asin = {}
            for d in docs:
                key = d.get("contentReferenceKey")
                meta = d.get("contentMetadata") or {}
                if not key:
                    continue
                # 2) which ASINs is it attached to?
                try:
                    rr = ap.list_content_document_asin_relations(contentReferenceKey=key,
                                                                 marketplaceId=mid)
                    rp = rr.payload if hasattr(rr, "payload") else rr
                    asins = [x.get("asin") for x in (rp or {}).get("asinMetadataSet", []) if x.get("asin")]
                except Exception:
                    asins = []
                if not asins:
                    continue
                # 3) the modules + their images
                try:
                    dr = ap.get_content_document(contentReferenceKey=key, marketplaceId=mid,
                                                 includedDataSet=["CONTENTS"])
                    dp = dr.payload if hasattr(dr, "payload") else dr
                    doc = ((dp or {}).get("contentRecord") or {}).get("contentDocument") or {}
                except Exception:
                    continue
                mods = doc.get("contentModuleList") or []
                images = _aplus_walk_images(mods, [])
                # de-dupe: the same image can appear in several modules
                seen, uniq = set(), []
                for im in images:
                    if im["url"] and im["url"] not in seen:
                        seen.add(im["url"]); uniq.append(im)
                entry = {"key": key, "name": doc.get("name") or meta.get("name") or "",
                         "status": meta.get("status") or "", "module_count": len(mods),
                         "images": uniq}
                for a in asins:
                    by_asin.setdefault(a, []).append(entry)
            _APLUS_CACHE[ck] = {"ts": _t.time(), "by_asin": by_asin}
            return jsonify({"ok": True, "by_asin": by_asin, "documents": len(docs), "cached": False})
        except Exception as e:
            return jsonify({"ok": False, "error": f"A+ Content API failed: {str(e)[:200]}"}), 502

    @app.route("/live/images", methods=["POST"])
    def live_images():
        """Fetch real main images for a batch of SKUs via getListingsItem (summaries
        only — lightweight). Cached per SKU for 24h so it's only slow the first time.
        Body: {id, marketplace, skus:[...]}. Returns {ok, images:{sku:url}}."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        skus = [s for s in (b.get("skus") or []) if s]
        if not skus:
            return jsonify({"ok": True, "images": {}})
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        # SELLER-SCOPE (getListingsItem answers for the token's own seller id).
        if not _acc.seller_scope_allowed(acc):
            return jsonify({"ok": False, "error":
                f"{acc.get('label') or aid} has no Amazon account of its own"}), 400
        import time as _t
        out = {}
        statuses = {}
        meta = {}
        todo = []
        for sku in skus:
            ck = f"{aid}::{mkt}::{sku}"
            c = _IMG_CACHE.get(ck)
            if c and (_t.time() - c["ts"] < _IMG_TTL):
                out[sku] = c["url"]
                if c.get("status"):
                    statuses[sku] = c["status"]
                if c.get("fulfillment") or c.get("handling") is not None:
                    meta[sku] = {"fulfillment": c.get("fulfillment", ""), "handling": c.get("handling")}
            else:
                todo.append(sku)
        if todo:
            try:
                from sp_api.api import ListingsItemsV20210801 as LI
                from sp_api.base import Marketplaces
                creds = _acc.account_creds(acc)
                seller = acc.get("seller_id", "")
                mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
                mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
                li = LI(credentials=creds, marketplace=mkt_enum)
                for sku in todo[:40]:
                    try:
                        resp = li.get_listings_item(seller, sku,
                                                    marketplaceIds=[mid] if mid else None,
                                                    includedData="summaries,issues,fulfillmentAvailability,attributes")
                        pay = resp.payload if hasattr(resp, "payload") else resp
                        summaries = (pay or {}).get("summaries", []) if isinstance(pay, dict) else []
                        issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
                        fa = (pay or {}).get("fulfillmentAvailability", []) if isinstance(pay, dict) else []
                        attrs = (pay or {}).get("attributes", {}) if isinstance(pay, dict) else {}
                        url = ""
                        real_status = ""
                        fulfillment = ""
                        handling = None
                        # fulfillment channel + handling time
                        if fa and isinstance(fa, list):
                            code = fa[0].get("fulfillmentChannelCode", "") if isinstance(fa[0], dict) else ""
                            if code:
                                fulfillment = "FBA" if ("AMAZON" in code.upper()) else "FBM"
                        # handling/lead time from attributes (FBM): lead_time_to_ship_max_days
                        try:
                            lt = attrs.get("fulfillment_availability") or []
                            if lt and isinstance(lt, list):
                                handling = lt[0].get("lead_time_to_ship_max_days")
                        except Exception:
                            handling = None
                        if handling is None:
                            try:
                                lt2 = attrs.get("lead_time_to_ship_max_days") or []
                                if lt2 and isinstance(lt2, list):
                                    handling = lt2[0].get("value")
                            except Exception:
                                handling = None
                        if summaries:
                            s0 = summaries[0]
                            mi = s0.get("mainImage") or {}
                            url = mi.get("link", "") if isinstance(mi, dict) else ""
                            live_title = s0.get("itemName", "") or ""
                            st_arr = s0.get("status", []) or []
                            has_error = any((iss.get("severity", "") == "ERROR") for iss in issues if isinstance(iss, dict))
                            suppressed = any(("suppress" in str(iss.get("message", "")).lower()
                                              or "search suppress" in str(iss.get("message", "")).lower())
                                             for iss in issues if isinstance(iss, dict))
                            if suppressed:
                                real_status = "Suppressed"
                            elif "BUYABLE" in st_arr:
                                real_status = "Active"
                            elif has_error:
                                real_status = "Incomplete"
                            elif st_arr:
                                real_status = "Inactive"
                            else:
                                real_status = "Inactive"
                            if not fulfillment:
                                fc = s0.get("fulfillmentChannel", "")
                                if fc:
                                    fulfillment = "FBA" if "AMAZON" in str(fc).upper() else "FBM"
                        _IMG_CACHE[f"{aid}::{mkt}::{sku}"] = {"url": url, "status": real_status,
                                                              "fulfillment": fulfillment, "handling": handling,
                                                              "ts": _t.time()}
                        if url:
                            out[sku] = url
                        if real_status:
                            statuses[sku] = real_status
                        # carry the live title (reflects edits immediately) in meta
                        _lt = ""
                        try:
                            _lt = live_title
                        except Exception:
                            _lt = ""
                        if fulfillment or handling is not None or _lt:
                            meta[sku] = {"fulfillment": fulfillment, "handling": handling, "title": _lt}
                    except Exception:
                        continue
            except Exception as e:
                return jsonify({"ok": False, "error": f"image fetch failed: {str(e)[:160]}",
                                "images": out, "statuses": statuses, "meta": meta}), 502
        return jsonify({"ok": True, "images": out, "statuses": statuses, "meta": meta})

    @app.route("/live/catalog", methods=["POST"])
    def live_catalog():
        """Fetch the account's LIVE Amazon listings for a marketplace via the Reports
        API (GET_MERCHANT_LISTINGS_ALL_DATA), parse, cache, and return them. This is
        the seller's already-published catalog -- separate from app drafts."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        force = bool(b.get("force"))
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        # SELLER-SCOPE. A borrowed token authenticates as the LENDER, so this report
        # would return the lender's listings under this workspace's name. Refuse.
        if not _acc.seller_scope_allowed(acc):
            if _acc.is_borrowed(acc):
                return jsonify({"ok": False, "read_only": True, "error":
                    f"{acc.get('label') or aid} is a read-only workspace — it has no Amazon "
                    f"account of its own, so it has no live listings. It borrows catalogue "
                    f"access only."}), 200
            return jsonify({"ok": False, "error": "account has no real refresh token yet"}), 400
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400

        ck = f"{aid}::{mkt}"
        import time as _t
        if not force and ck in _LIVE_CACHE and (_t.time() - _LIVE_CACHE[ck]["ts"] < _LIVE_TTL):
            return jsonify({"ok": True, "items": _LIVE_CACHE[ck]["items"], "cached": True})
        # on a forced sync, also drop the per-listing image/status/meta cache for
        # this account+marketplace so titles/images/status/fulfillment all refresh
        if force:
            _pref = f"{aid}::{mkt}::"
            for _k in [k for k in list(_IMG_CACHE.keys()) if k.startswith(_pref)]:
                _IMG_CACHE.pop(_k, None)

        creds = _acc.account_creds(acc)
        try:
            from sp_api.api import Reports
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api Reports not available: {e}"}), 500
        mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.UK
        try:
            import accounts as _acc2
            mkt_id = _acc2.marketplace_id(mkt) if hasattr(_acc2, "marketplace_id") else ""
        except Exception:
            mkt_id = ""
        try:
            rc = Reports(credentials=creds, marketplace=mkt_enum)
            RT = "GET_MERCHANT_LISTINGS_ALL_DATA"
            doc_id = None
            report_source = "new"
            # 0) reuse a recently-generated report ONLY when not forcing. When the
            #    user clicks Sync (force=True), we must generate a FRESH report so
            #    edits made on Amazon are reflected — reusing the old report would
            #    show stale data.
            if not force:
                try:
                    existing = rc.get_reports(reportTypes=[RT], processingStatuses=["DONE"],
                                              marketplaceIds=[mkt_id] if mkt_id else None, pageSize=1)
                    epay = existing.payload if hasattr(existing, "payload") else existing
                    reps = (epay or {}).get("reports", []) if isinstance(epay, dict) else []
                    if reps:
                        doc_id = reps[0].get("reportDocumentId")
                        report_source = "reused"
                except Exception:
                    doc_id = None
            # 1) else create a fresh report
            if not doc_id:
                cr = rc.create_report(reportType=RT,
                                      marketplaceIds=[mkt_id] if mkt_id else None)
                rid = (cr.payload or {}).get("reportId") if hasattr(cr, "payload") else cr.get("reportId")
                if not rid:
                    return jsonify({"ok": False, "error": "no reportId returned"}), 502
                # 2) poll for completion — up to ~4 minutes (Amazon reports can be slow)
                for attempt in range(60):
                    st = rc.get_report(rid)
                    pay = st.payload if hasattr(st, "payload") else st
                    status = pay.get("processingStatus")
                    if status == "DONE":
                        doc_id = pay.get("reportDocumentId"); break
                    if status in ("CANCELLED", "FATAL"):
                        return jsonify({"ok": False, "error": f"report {status}"}), 502
                    _t.sleep(2 if attempt < 10 else 4)   # poll fast early, slower later
                if not doc_id:
                    return jsonify({"ok": False, "error":
                        "Amazon is still generating the report (large catalogs can take several minutes). "
                        "Click Sync again in a minute — the report will usually be ready and load instantly."}), 504
            # 3) download + decode the document (param is 'download', not 'decrypt')
            doc = rc.get_report_document(doc_id, download=True)
            dpay = doc.payload if hasattr(doc, "payload") else doc
            # when download=True, the library fetches+decrypts and puts text in 'document'
            text = ""
            if isinstance(dpay, dict):
                text = dpay.get("document", "") or ""
            if not text:
                text = getattr(doc, "document", "") or ""
            # some versions return the URL only; fetch it ourselves as a fallback
            if not text and isinstance(dpay, dict) and dpay.get("url"):
                try:
                    import urllib.request, gzip, io
                    raw = urllib.request.urlopen(dpay["url"], timeout=60).read()
                    if dpay.get("compressionAlgorithm") == "GZIP" or raw[:2] == b"\x1f\x8b":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", "replace")
                except Exception as _e:
                    return jsonify({"ok": False, "error": f"could not download report doc: {_e}"}), 502
            items = _parse_listings_report(text)
            # GET_MERCHANT_LISTINGS_ALL_DATA returns ACTIVE listings only, so a listing
            # Amazon has deactivated or suppressed simply vanished from this view -- and
            # since Amazon is now the sole authority for "live", it would be demoted to
            # "not confirmed by Amazon". Merge the inactive report so every listing on
            # the account is shown, each carrying its real status.
            try:
                _icr = rc.create_report(reportType="GET_MERCHANT_LISTINGS_INACTIVE_DATA",
                                        marketplaceIds=[mkt_id] if mkt_id else None)
                _irid = (_icr.payload or {}).get("reportId") if hasattr(_icr, "payload") else _icr.get("reportId")
                _idoc = None
                for _a in range(45):
                    _ist = rc.get_report(_irid)
                    _ip = _ist.payload if hasattr(_ist, "payload") else _ist
                    if _ip.get("processingStatus") == "DONE":
                        _idoc = _ip.get("reportDocumentId"); break
                    if _ip.get("processingStatus") in ("CANCELLED", "FATAL"):
                        break
                    _t.sleep(2 if _a < 10 else 4)
                if _idoc:
                    _id_ = rc.get_report_document(_idoc, download=True)
                    _idp = _id_.payload if hasattr(_id_, "payload") else _id_
                    _itext = (_idp or {}).get("document", "") if isinstance(_idp, dict) else ""
                    _seen = {str(i.get("sku", "")).strip().upper() for i in items}
                    for _ii in _parse_listings_report(_itext):
                        if str(_ii.get("sku", "")).strip().upper() in _seen:
                            continue
                        _ii["status"] = _ii.get("status") or "Inactive"
                        items.append(_ii)
            except Exception as _ie:
                # never fail the whole catalog because the inactive report misbehaved
                print(f"[live/catalog] inactive report skipped: {_ie}")
            # enrich each item with COGS + profit estimate
            for it in items:
                cost, csrc = _resolve_cogs(aid, it.get("sku", ""))
                if cost is not None:
                    it["cogs"] = cost
                    it["cogs_source"] = csrc
                    prof = _estimate_profit(it.get("price", ""), cost)
                    if prof:
                        it["profit"] = prof
            # capture the header so we can diagnose missing-title issues
            hdr = []
            try:
                hdr = [h.strip() for h in (text.splitlines()[0].split("\t"))] if text else []
            except Exception:
                hdr = []
            _LIVE_CACHE[ck] = {"ts": _t.time(), "items": items}
            return jsonify({"ok": True, "items": items, "count": len(items),
                            "cached": False, "columns": hdr, "report_source": report_source})
        except Exception as e:
            return jsonify({"ok": False, "error": f"report flow failed: {str(e)[:220]}"}), 500

