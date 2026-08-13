"""routes/live_routes.py — extracted from dashboard.py (Phase 3). Bodies VERBATIM.

Auto-extracted @app.route("/live...") funcs; shared helpers injected. Verified with
verify_free_vars.py.
"""
from flask import request, jsonify, Response, send_from_directory
import urllib
import datetime as _dt

from listing.sourcing_viability import check_sourcing_viability as _viability

# How old an already-generated Amazon report may be before we refuse to reuse it.
# getReports defaults createdSince to 90 DAYS and documents no sort order, so an
# unbounded reuse could serve a weeks-old catalogue as if it were live. Six hours
# keeps ordinary page views fast without ever showing yesterday's catalogue.
_REPORT_REUSE_MAX_AGE = 6 * 3600


def register(app, *, CONFIG_PATH, _IMG_CACHE, _IMG_TTL, _LIVE_CACHE, _LIVE_TTL, _cfg, _estimate_profit, _parse_listings_report, _resolve_cogs, _state, _APLUS_CACHE=None, _APLUS_TTL=1800, _MIRROR_CACHE=None, _MIRROR_TTL=6*3600):
    # How many SKUs one /live/images call will fetch from Amazon. Each SKU is a
    # separate getListingsItem call and SP-API is rate limited, so this is a real
    # constraint, not a guess. What was WRONG was doing it silently: the reply now
    # reports what it did not reach, and the browser asks again for the rest.
    import os as _os
    try:
        _IMG_BATCH = max(10, min(int(_os.environ.get("ALTA_IMG_BATCH") or 40), 200))
    except Exception:
        _IMG_BATCH = 40
    """Attach the /live routes to the existing Flask app."""

    if _APLUS_CACHE is None:
        _APLUS_CACHE = {}
    # Live MIRROR: the REAL per-listing data pulled from Amazon (full attributes) on a
    # Sync -- images, bullets, description, item-type-keyword, variations/theme. Kept
    # server-side, keyed aid::mkt::sku, and shown READ-ONLY beside a live listing. It is
    # a mirror only: it never touches the sheet or a draft row.
    if _MIRROR_CACHE is None:
        _MIRROR_CACHE = {}

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

    @app.route("/live/reconcile", methods=["POST"])
    def live_reconcile():
        """Ask Amazon, per SKU, what state a listing is REALLY in.

        Body: {id, marketplace, skus:[...]} -> {ok, by_sku: {sku: {...}}}

        Three states, and the important subtlety: Amazon CANNOT tell "deleted" apart
        from "never existed" -- getListingsItem answers NOT_FOUND for both. Verified
        against the live account: a SKU our sheet calls LIVE and a SKU our sheet calls
        API_ERROR return the identical error. So this route only reports `gone`; the
        caller must combine it with what the SHEET believed:

            sheet said LIVE/SUBMITTED + gone  -> it was published, then deleted
            sheet said API_ERROR/etc  + gone  -> it was never created; still a draft

        Deciding "deleted" here, without the sheet's belief, would delete drafts.
        """
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        if not skus:
            return jsonify({"ok": True, "by_sku": {}})
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        if not _acc.seller_scope_allowed(acc):   # getListingsItem answers for the token's seller
            return jsonify({"ok": True, "by_sku": {}, "read_only": True}), 200
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        try:
            from sp_api.api import ListingsItemsV20210801 as _LI
            from sp_api.base import Marketplaces as _MK
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api unavailable: {e}"}), 500
        mid = _acc.marketplace_id(mkt) or ""
        locale = "en_US" if mkt == "US" else "en_GB"
        li = _LI(credentials=_acc.account_creds(acc),
                 marketplace=getattr(_MK, mkt, None) or _MK.UK, timeout=60)
        seller = acc.get("seller_id", "")
        out = {}
        for sku in skus[:60]:
            try:
                r = li.get_listings_item(seller, sku, marketplaceIds=[mid] if mid else None,
                                         issueLocale=locale,
                                         includedData=["summaries", "issues", "fulfillmentAvailability"])
                p = r.payload if hasattr(r, "payload") else (r or {})
            except Exception as e:
                msg = str(e)
                if "NOT_FOUND" in msg:
                    out[sku] = {"state": "gone", "reason": "Amazon has no listing with this SKU"}
                else:
                    # a transient failure must NOT be read as "deleted"
                    out[sku] = {"state": "unknown", "reason": f"check failed: {msg[:120]}"}
                continue
            s = ((p or {}).get("summaries") or [{}])[0]
            status = s.get("status") or []
            issues = (p or {}).get("issues") or []
            errs = [x for x in issues if str(x.get("severity", "")).upper() == "ERROR"]
            fa = (p or {}).get("fulfillmentAvailability") or []
            qty = None
            for f in fa:
                q = f.get("quantity")
                if isinstance(q, int):
                    qty = q if qty is None else max(qty, q)
            buyable = "BUYABLE" in status
            # Why is it not buyable? Say so in Amazon's own words where we have them.
            if buyable:
                reason = ""
            elif errs:
                reason = str(errs[0].get("message", ""))[:220]
            elif qty == 0:
                reason = "Out of stock (quantity 0)"
            elif "DISCOVERABLE" in status:
                reason = "Searchable on Amazon but not currently buyable"
            else:
                reason = "Amazon reports no active offer for this listing"
            out[sku] = {
                "state": "live" if buyable else "inactive",
                "status": status, "qty": qty, "reason": reason,
                "asin": s.get("asin", ""), "title": s.get("itemName", ""),
                "issues": [{"severity": x.get("severity"), "code": x.get("code"),
                            "message": str(x.get("message", ""))[:220]} for x in issues[:6]],
            }
        return jsonify({"ok": True, "by_sku": out, "checked": len(out)})

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
        _pending_out = []      # SKUs this call did not reach (see the cap below)
        _failed = []           # SKUs Amazon refused -- usually throttling
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
                # SILENT TRUNCATION WAS THE BUG.
                # This read todo[:40] and said nothing, so asking for images on a
                # catalogue of any size returned the first 40 and left the rest
                # blank with no explanation -- indistinguishable from "Amazon has
                # no image for these". The cap exists for a reason (one
                # getListingsItem call per SKU, and SP-API is rate limited), so it
                # stays; what changes is that the answer now SAYS what it did.
                _batch = _IMG_BATCH
                _did = todo[:_batch]
                _pending = todo[_batch:]
                for sku in _did:
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
                    except Exception as _ie:
                        # A SKU that fails here used to vanish silently, so a
                        # throttled batch was indistinguishable from "Amazon has
                        # no image for these". getListingsItem is rate limited and
                        # throttling is the NORMAL failure on a large catalogue,
                        # so it has to be reported, not swallowed.
                        _failed.append({"sku": sku, "error": str(_ie)[:120]})
                        continue
                _pending_out = _pending
            except Exception as e:
                return jsonify({"ok": False, "error": f"image fetch failed: {str(e)[:160]}",
                                "images": out, "statuses": statuses, "meta": meta}), 502
        # Report what was NOT done, so the caller can ask again for the rest
        # rather than assume it got everything.
        return jsonify({"ok": True, "images": out, "statuses": statuses, "meta": meta,
                        "requested": len(skus), "fetched": len(out),
                        "pending": _pending_out, "failed": _failed,
                        "batch": _IMG_BATCH})

    def _attach_compliance(items, mkt):
        """Work out which documents Amazon can demand, for each live listing.

        COMPUTED WHEN SERVED, NOT WHEN FETCHED. It used to run only on a fresh
        Amazon fetch and get baked into the saved snapshot -- which meant that
        once saved catalogues began being served at any age, a listing showed
        whatever compliance data happened to exist when it was pulled, or none at
        all for anything saved before this feature existed. That is why live
        listings showed no documents.

        Running it on the way out also means editing
        sourcing_viability_rules.json takes effect on the next page load, instead
        of waiting for every marketplace to be re-fetched.

        It is pure pattern matching over the title -- no Amazon calls, no cost --
        so doing it per request is cheap. A listing already selling is exactly
        where a document demand lands: the patio heater was live for months
        before the notice arrived.
        """
        for it in (items or []):
            try:
                _v = _viability(title=it.get("title", ""),
                                product_type=it.get("product_type", ""),
                                marketplace=mkt)
                if _v.get("matched"):
                    it["compliance"] = {
                        "verdict": _v.get("verdict", ""),
                        "risks": [{"id": x["id"], "label": x["label"], "risk": x["risk"],
                                   "docs": x["docs"], "regulator": x.get("regulator", ""),
                                   "reason": x.get("reason", "")}
                                  for x in _v.get("risks", [])],
                        "doc_count": sum(len(x.get("docs") or []) for x in _v.get("risks", [])),
                    }
                else:
                    it.pop("compliance", None)   # a rule was removed -> so is the chip
            except Exception:
                pass              # a compliance fault must never cost you the catalogue
        return items

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
        import domain.live_snapshots as _snap
        if not force and ck in _LIVE_CACHE and (_t.time() - _LIVE_CACHE[ck]["ts"] < _LIVE_TTL):
            return jsonify({"ok": True,
                            "items": _attach_compliance(_LIVE_CACHE[ck]["items"], mkt),
                            "cached": True})
        # DURABLE SNAPSHOT (second line of defence). _LIVE_CACHE is process memory:
        # a container restart or redeploy empties it, and on Render that happens on
        # every deploy. Before going back to Amazon, serve the snapshot written by
        # the last successful fetch -- so a reload shows the SAME catalogue it
        # showed a minute ago instead of silently re-answering from a stale report.
        if not force:
            _rec = _snap.get(CONFIG_PATH, aid, mkt)
            _age = _snap.age_seconds(_rec)
            # NO AGE LIMIT. The last successful sync is shown whatever its age,
            # labelled with WHEN it was pulled.
            #
            # This used to require _age < _LIVE_TTL, which meant a saved
            # catalogue older than the cache window was thrown away and the page
            # went back to Amazon -- so simply leaving the app open for an hour
            # and returning could show an empty list while a report rebuilt.
            # Age decides whether to REFRESH; it must never decide whether you
            # are allowed to see what you already pulled. Until fresher data
            # arrives, the latest data stands, and says when it was taken.
            if _rec and (_rec.get("items") or []):
                _LIVE_CACHE[ck] = {"ts": _t.time() - (_age or 0),
                                   "items": _rec.get("items") or []}
                return jsonify({"ok": True,
                                "items": _attach_compliance(_rec.get("items") or [], mkt),
                                "count": _rec.get("count", 0), "cached": True,
                                "from_snapshot": True, "synced_at": _rec.get("ts"),
                                "age_seconds": _age,
                                "stale": bool(_age and _age > _LIVE_TTL),
                                "partial": _rec.get("partial", False),
                                "warnings": _rec.get("warnings") or [],
                                "report_source": _rec.get("report_source", "")})
            # NOTHING SAVED YET for this account+marketplace. Return immediately
            # and let the background refresh fill it in.
            #
            # This is the fix for "clicking Live on Amazon hangs for 5-10 minutes".
            # Building an Amazon report takes minutes; doing that on the click path
            # meant every visit to the tab blocked on it. Seller Central never does
            # that -- it shows you what it has and catches up afterwards.
            #
            # So the click path NEVER builds a report. It returns what is stored,
            # or says there is nothing yet. Only a background refresh (the timer,
            # or the Sync button) ever waits on Amazon.
            return jsonify({"ok": True, "items": [], "count": 0,
                            "cached": False, "needs_sync": True,
                            "message": "No saved catalogue for this marketplace yet. "
                                       "Fetching it from Amazon in the background -- "
                                       "this first one takes a few minutes."})

        # A FORCED sync takes priority over the background rotation. The
        # refresher is topping up marketplaces nobody is looking at; whoever
        # pressed Sync is waiting at a screen. Telling it we have started makes
        # it stand aside, so the two do not compete for the same per-minute
        # Amazon quota and the manual sync is not slowed by a report nobody
        # asked for.
        #
        # The background refresher calls this same view, so it must NOT count
        # itself as a user -- it sets _bg on the request body.
        if force and not b.get("_bg"):
            try:
                from flask import after_this_request
                import domain.live_refresher as _refresher

                _refresher.user_sync_started(f"{aid}::{mkt}")

                # Released via after_this_request rather than a finally: this
                # view has many return paths (early refusals, the snapshot
                # fallbacks, the error handler), and a finally wrapped around all
                # of them would be easy to get wrong. This fires on every one,
                # including an unhandled exception, so the refresher can never be
                # left permanently paused by a request that died.
                _prio_key = f"{aid}::{mkt}"

                @after_this_request
                def _release_priority(resp, _k=_prio_key):
                    try:
                        _refresher.user_sync_finished(_k)
                    except Exception:
                        pass
                    return resp
            except Exception:
                pass          # priority is an optimisation, never a requirement

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
            # timeout so a stalled Amazon Reports call can't hang the request forever
            # (every other SP-API client here already passes one; this one didn't, which
            # is how a slow report could leave the UI spinning indefinitely).
            try:
                rc = Reports(credentials=creds, marketplace=mkt_enum, timeout=90)
            except TypeError:
                rc = Reports(credentials=creds, marketplace=mkt_enum)
            RT = "GET_MERCHANT_LISTINGS_ALL_DATA"
            doc_id = None
            report_source = "new"
            report_built_at = ""
            warnings = []
            # 0) reuse a recently-generated report ONLY when not forcing. When the
            #    user clicks Sync (force=True), we must generate a FRESH report so
            #    edits made on Amazon are reflected — reusing the old report would
            #    show stale data.
            #
            #    REUSE IS NOW BOUNDED. getReports defaults createdSince to 90 DAYS
            #    ago and documents NO sort order, so the old `pageSize=1 -> reps[0]`
            #    could hand back a report Amazon built weeks ago and the UI would
            #    present it as the live catalogue. That is the "it shows old
            #    listings" bug. We now ask only for reports created since
            #    _REPORT_REUSE_MAX_AGE and pick the genuinely newest by createdTime.
            if not force:
                try:
                    _since = _dt.datetime.utcnow() - _dt.timedelta(seconds=_REPORT_REUSE_MAX_AGE)
                    existing = rc.get_reports(reportTypes=[RT], processingStatuses=["DONE"],
                                              marketplaceIds=[mkt_id] if mkt_id else None,
                                              createdSince=_since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                              pageSize=10)
                    epay = existing.payload if hasattr(existing, "payload") else existing
                    reps = (epay or {}).get("reports", []) if isinstance(epay, dict) else []
                    reps = [r for r in reps if r.get("reportDocumentId")]
                    # newest first, explicitly -- never trust the response order
                    reps.sort(key=lambda r: str(r.get("createdTime") or ""), reverse=True)
                    if reps:
                        doc_id = reps[0].get("reportDocumentId")
                        report_built_at = str(reps[0].get("createdTime") or "")
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
                _idoc = None
                # REUSE a recent DONE inactive report when NOT forcing -- like the active
                # report above. Previously this ALWAYS created a fresh report and polled it
                # (~2-3 min) on EVERY catalogue view, which is why "Live on Amazon" was slow
                # every time. Now a plain view downloads an existing report (seconds); only a
                # forced Sync regenerates it.
                if not force:
                    try:
                        _isince = _dt.datetime.utcnow() - _dt.timedelta(seconds=_REPORT_REUSE_MAX_AGE)
                        _iex = rc.get_reports(reportTypes=["GET_MERCHANT_LISTINGS_INACTIVE_DATA"],
                                              processingStatuses=["DONE"],
                                              marketplaceIds=[mkt_id] if mkt_id else None,
                                              createdSince=_isince.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                              pageSize=10)
                        _iep = _iex.payload if hasattr(_iex, "payload") else _iex
                        _ireps = (_iep or {}).get("reports", []) if isinstance(_iep, dict) else []
                        _ireps = [r for r in _ireps if r.get("reportDocumentId")]
                        _ireps.sort(key=lambda r: str(r.get("createdTime") or ""), reverse=True)
                        if _ireps:
                            _idoc = _ireps[0].get("reportDocumentId")
                    except Exception:
                        _idoc = None
                if not _idoc:
                    _icr = rc.create_report(reportType="GET_MERCHANT_LISTINGS_INACTIVE_DATA",
                                            marketplaceIds=[mkt_id] if mkt_id else None)
                    _irid = (_icr.payload or {}).get("reportId") if hasattr(_icr, "payload") else _icr.get("reportId")
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
                else:
                    # No inactive document at all (report cancelled/fatal/timed out).
                    # Say so instead of silently returning an active-only list that
                    # LOOKS like the whole catalogue -- that silence is how a 64-item
                    # account displayed 16 with no error to explain it.
                    warnings.append("Inactive/suppressed listings could not be loaded "
                                    "(Amazon's inactive report was not ready) — this list "
                                    "shows ACTIVE listings only.")
            except Exception as _ie:
                # never fail the whole catalog because the inactive report misbehaved
                print(f"[live/catalog] inactive report skipped: {_ie}")
                warnings.append(f"Inactive/suppressed listings could not be loaded "
                                f"({type(_ie).__name__}) — this list shows ACTIVE listings only.")
            _attach_compliance(items, mkt)
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
            # AN EMPTY OR SHRUNKEN REPORT MUST NOT ERASE WHAT YOU ALREADY HAVE.
            # Amazon returns 0 rows for reasons that are not errors -- a report
            # still generating, a transient empty, a marketplace briefly not
            # answering. None of those raise, so the last-resort handler below
            # never sees them, and the catalogue would simply be replaced by
            # nothing. That is the "sync wiped my listings" symptom.
            #
            # The rule mirrors what save() already does on disk: a smaller result
            # never silently replaces a larger one. It is REPORTED instead, so a
            # genuine deletion on Amazon is still visible rather than hidden.
            _prev = _snap.get(CONFIG_PATH, aid, mkt) or {}
            _prev_items = _prev.get("items") or []
            if _prev_items and len(items) < len(_prev_items):
                _shrink = len(_prev_items) - len(items)
                _age_prev = _snap.age_seconds(_prev)
                if not items:
                    # Nothing at all came back -- keep the saved copy verbatim.
                    return jsonify({
                        "ok": True, "items": _attach_compliance(_prev_items, mkt),
                        "count": len(_prev_items), "cached": True,
                        "from_snapshot": True, "stale": True,
                        "synced_at": _prev.get("ts"), "age_seconds": _age_prev,
                        "report_source": _prev.get("report_source", ""),
                        "warnings": (_prev.get("warnings") or []) + [
                            "Amazon returned an EMPTY report just now, which usually "
                            "means the report was still being generated. Your last "
                            "successful sync is still shown -- nothing was lost. "
                            "Try Sync again in a minute."]})
                warnings = list(warnings or []) + [
                    f"Amazon returned {len(items)} listing(s), {_shrink} fewer than "
                    f"the last sync ({len(_prev_items)}). Showing the new result. If "
                    f"that is unexpected, sync again -- a partly-built report can "
                    f"come back short."]
            _LIVE_CACHE[ck] = {"ts": _t.time(), "items": items}
            # DURABLE WRITE. Everything above is process memory that a restart or a
            # redeploy erases; this is the copy that survives. save() also refuses to
            # let a PARTIAL result overwrite a larger COMPLETE one, so a failed
            # inactive-report half can no longer shrink a good catalogue on disk.
            _stored = _snap.save(CONFIG_PATH, aid, mkt, items,
                                 report_source=report_source,
                                 partial=bool(warnings), warnings=warnings)
            _kept = (_stored.get("count", len(items)) != len(items))
            return jsonify({"ok": True, "items": items, "count": len(items),
                            "cached": False, "columns": hdr,
                            "report_source": report_source,
                            "report_built_at": report_built_at,
                            "partial": bool(warnings), "warnings": warnings,
                            "snapshot_kept_larger": _kept,
                            "synced_at": _t.time()})
        except Exception as e:
            # Print the FULL traceback to the terminal so the real cause is always
            # visible (the JSON only carries a truncated string). Without this the
            # 500 is a black box -- you see "report flow failed: ..." and nothing more.
            import traceback as _tb
            print("[live/catalog] EXCEPTION during report flow "
                  f"(account={aid} marketplace={mkt}):")
            _tb.print_exc()
            # LAST RESORT: Amazon failed, but we may still hold a saved catalogue on
            # disk from a previous successful sync. Showing it (clearly labelled with
            # its age) beats showing nothing -- an Amazon outage or a slow report must
            # not look like "your listings disappeared".
            _rec = _snap.get(CONFIG_PATH, aid, mkt)
            if _rec and (_rec.get("items") or []):
                _age = _snap.age_seconds(_rec)
                return jsonify({"ok": True,
                                "items": _attach_compliance(_rec.get("items") or [], mkt),
                                "count": _rec.get("count", 0), "cached": True,
                                "from_snapshot": True, "stale": True,
                                # Distinct from merely-old data: Amazon actually
                                # FAILED. The label says "Amazon unreachable" only
                                # for this, so old-but-fine never looks broken.
                                "amazon_failed": True,
                                "synced_at": _rec.get("ts"), "age_seconds": _age,
                                "partial": _rec.get("partial", False),
                                "warnings": (_rec.get("warnings") or []) + [
                                    f"Amazon could not be reached ({type(e).__name__}); "
                                    f"showing the last saved sync."]})
            return jsonify({"ok": False,
                            "error": f"report flow failed: {type(e).__name__}: {str(e)[:220]}"}), 500

    # ---- Full per-listing pull -> the live MIRROR --------------------------------
    def _attr_vals(attrs, key):
        """Pull the list of scalar values from a Listings-API attribute. Attributes come as
        [{"value": x, ...}] (copy fields) or [{"media_location"/"link": url}] (images)."""
        v = attrs.get(key)
        if not isinstance(v, list):
            return [v] if v not in (None, "") else []
        out = []
        for e in v:
            if isinstance(e, dict):
                for k in ("value", "media_location", "link"):
                    if e.get(k) not in (None, ""):
                        out.append(e[k]); break
            elif e not in (None, ""):
                out.append(e)
        return out

    def _attr_one(attrs, key):
        vs = _attr_vals(attrs, key)
        return vs[0] if vs else ""

    def _mirror_images(attrs, summaries):
        imgs = list(_attr_vals(attrs, "main_product_image_locator"))
        for k in sorted(attrs.keys()):
            if k.startswith("other_product_image_locator"):
                imgs += _attr_vals(attrs, k)
        imgs += _attr_vals(attrs, "swatch_image_locator")
        if not imgs and summaries:
            mi = (summaries[0].get("mainImage") or {}) if isinstance(summaries[0], dict) else {}
            if mi.get("link"):
                imgs = [mi["link"]]
        seen, out = set(), []
        for u in imgs:
            u = str(u or "").strip()
            if u and u not in seen:
                seen.add(u); out.append(u)
        return out

    def _mirror_variations(payload):
        """From includedData=relationships: variation theme + child/parent SKUs, if any."""
        theme, children, parents = "", [], []
        for block in (payload.get("relationships") or []):
            for rr in (block.get("relationships") or []):
                if str(rr.get("type", "")).upper() != "VARIATION":
                    continue
                vt = rr.get("variationTheme") or {}
                theme = theme or vt.get("theme") or ""
                children += [c for c in (rr.get("childSkus") or []) if c]
                parents += [p for p in (rr.get("parentSkus") or []) if p]
        # de-dupe
        children = list(dict.fromkeys(children))
        parents = list(dict.fromkeys(parents))
        return {"theme": theme, "child_skus": children, "parent_skus": parents,
                "is_parent": bool(children), "is_child": bool(parents)}

    def _build_mirror_entry(payload):
        payload = payload if isinstance(payload, dict) else {}
        attrs = payload.get("attributes", {}) or {}
        summaries = payload.get("summaries", []) or []
        s0 = summaries[0] if summaries and isinstance(summaries[0], dict) else {}
        var = _mirror_variations(payload)
        return {
            "title": _attr_one(attrs, "item_name") or s0.get("itemName", "") or "",
            "brand": _attr_one(attrs, "brand") or s0.get("brand", "") or "",
            "bullets": _attr_vals(attrs, "bullet_point"),
            "description": _attr_one(attrs, "product_description"),
            "item_type_keyword": _attr_one(attrs, "item_type_keyword") or s0.get("itemClassification", ""),
            "images": _mirror_images(attrs, summaries),
            "variation_theme": var["theme"] or _attr_one(attrs, "variation_theme"),
            "variations": var,
            "asin": s0.get("asin", ""),
            "product_type": s0.get("productType", ""),
            "status": s0.get("status", []),
        }

    @app.route("/live/full_pull", methods=["POST"])
    def live_full_pull():
        """Pull the REAL full data (attributes+relationships) for a batch of live SKUs into
        the mirror. Body: {id, marketplace, skus:[...], force}. Returns {ok, mirror:{sku:{...}}}.
        This is the heavy part of a Sync; it never writes to the sheet."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        force = bool(b.get("force"))
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        # SELLER-SCOPE: getListingsItem answers for the token's own seller.
        if not _acc.seller_scope_allowed(acc):
            return jsonify({"ok": True, "mirror": {}, "read_only": True}), 200
        if not mkt:
            return jsonify({"ok": False, "error": "no marketplace selected"}), 400
        if not skus:
            return jsonify({"ok": True, "mirror": {}})
        import time as _t
        mirror, todo = {}, []
        for sku in skus:
            ck = f"{aid}::{mkt}::{sku}"
            c = _MIRROR_CACHE.get(ck)
            if c and not force and (_t.time() - c["ts"] < _MIRROR_TTL):
                mirror[sku] = c["data"]
            else:
                todo.append(sku)
        if todo:
            try:
                from sp_api.api import ListingsItemsV20210801 as LI
                from sp_api.base import Marketplaces
            except Exception as e:
                return jsonify({"ok": False, "error": f"sp_api unavailable: {e}"}), 500
            mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
            locale = "en_US" if mkt == "US" else "en_GB"
            seller = acc.get("seller_id", "")
            li = LI(credentials=_acc.account_creds(acc),
                    marketplace=getattr(Marketplaces, mkt, None) or Marketplaces.UK, timeout=60)
            pulled = 0
            for sku in todo[:300]:                      # cap one Sync at 300 SKUs
                try:
                    r = li.get_listings_item(
                        seller, sku, marketplaceIds=[mid] if mid else None, issueLocale=locale,
                        includedData=["attributes", "summaries", "relationships", "issues", "fulfillmentAvailability"])
                    p = r.payload if hasattr(r, "payload") else (r or {})
                    entry = _build_mirror_entry(p)
                    _MIRROR_CACHE[f"{aid}::{mkt}::{sku}"] = {"ts": _t.time(), "data": entry}
                    mirror[sku] = entry
                    pulled += 1
                    if pulled % 5 == 0:
                        _t.sleep(1)                     # ~5 req/sec to respect the rate limit
                except Exception:
                    continue                            # a missing/failed SKU just isn't mirrored
        return jsonify({"ok": True, "mirror": mirror, "count": len(mirror),
                        "capped": len(todo) > 300})

    @app.route("/live/mirror", methods=["POST"])
    def live_mirror():
        """Return already-mirrored data (no network) for a batch of SKUs. Body: {id, marketplace,
        skus:[...]} -> {ok, mirror:{sku:{...}}}. Powers the read-only 'Actual on Amazon' view."""
        b = request.get_json(force=True) or {}
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        skus = [str(s).strip() for s in (b.get("skus") or []) if str(s).strip()]
        out = {}
        for sku in skus:
            c = _MIRROR_CACHE.get(f"{aid}::{mkt}::{sku}")
            if c:
                out[sku] = c["data"]
        return jsonify({"ok": True, "mirror": out})

