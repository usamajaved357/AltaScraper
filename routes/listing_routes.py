"""routes/listing_routes.py — extracted from dashboard.py (Phase 3). Bodies VERBATIM.

Auto-extracted @app.route("paths:/suggest,/ask,/input_sheet,/row,/rows,/approve,/schema/<path:pt>,/edit,/delete,/clear_empty,/listing/push_image,/run/<mode>...") funcs; shared helpers injected. Verified with
verify_free_vars.py.
"""
from flask import request, jsonify, Response, send_from_directory
import json
import os
import re
import subprocess
import sys


def register(app, *, CHAT_MODEL, CONFIG_PATH, SCRIPT, SKU_HEADER, STATUS_HEADER, _ANSI, _EDITABLE_COLS, _URL_RE, _VALID_SET_STATUS, _acquire_run_lock, _active_account, _build_patches, _bust_records_cache, _card, _cfg, _client, _drive_folder_id_from_url, _drive_map_get, _drive_map_put, _drive_upload_image, _ebay_creds, _fetch_image_b64, _load_schema, _marketplace_for_row, _media_root, _options_for, _parse_required_missing, _product_types, _records, _resolve_fields, _run_lock, _running, _schema_attrs, _schema_required, _schema_subfields, _sp_creds, _state, _ws, _require_publish=lambda acc=None: acc):
    """Attach the paths:/suggest,/ask,/input_sheet,/row,/rows,/approve,/schema/<path:pt>,/edit,/delete,/clear_empty,/listing/push_image,/run/<mode> routes to the existing Flask app."""

    _LIVE_IMG_KEY = re.compile(
        r"^(main_product_image_locator|other_product_image_locator_\d+|swatch_image_locator)$")

    @app.route("/live/pull_row", methods=["POST"])
    def live_pull_row():
        """Pull a LIVE listing's REAL data from Amazon into the row.

        The app only ever showed the images captured at GENERATION time (the eBay/competitor
        URLs in main_product_image_locator), so a listing that is live on Amazon still displayed
        the wrong photos, and A+/Image Studio reported "no reference image". This calls
        getListingsItem(attributes,summaries) and merges EVERY live image locator -- the main
        image plus every other_product_image_locator_N (the secondary images) -- back into the
        row's Attributes JSON, replacing the stale generation-time ones.
        """
        b = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        if not sku:
            return jsonify({"ok": False, "error": "missing sku"}), 400
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        acc = _active_account()
        if not acc:
            return jsonify({"ok": False, "error": "open an Amazon account workspace first"}), 400
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            return jsonify({"ok": False, "error": "this account is not connected to Amazon"}), 400

        mkt = (acc.get("default_marketplace") or "UK").strip().upper()
        try:
            from sp_api.api import ListingsItemsV20210801 as _LI
            from sp_api.base import Marketplaces as _MK
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api unavailable: {e}"}), 500
        mkt_enum = getattr(_MK, mkt, None) or getattr(_MK, "UK")
        mid = _acc.marketplace_id(mkt) or ""
        try:
            li = _LI(credentials=_acc.account_creds(acc), marketplace=mkt_enum, timeout=60)
            resp = li.get_listings_item(acc.get("seller_id", ""), sku,
                                        marketplaceIds=[mid] if mid else None,
                                        includedData="attributes,summaries")
            pay = resp.payload if hasattr(resp, "payload") else (resp or {})
        except Exception as e:
            return jsonify({"ok": False, "error": f"Amazon call failed: {str(e)[:180]}"}), 502

        live_attrs = (pay or {}).get("attributes", {}) or {}
        summaries  = (pay or {}).get("summaries", []) or []

        def _media(v):
            """Image attributes look like [{"media_location": "https://...", ...}]."""
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return str(v[0].get("media_location") or v[0].get("value") or "").strip()
            return ""

        images = {}
        for k, v in live_attrs.items():
            if _LIVE_IMG_KEY.match(str(k)):
                u = _media(v)
                if u.startswith("http"):
                    images[str(k)] = u
        # Fall back to the summary's main image if Amazon didn't return the attribute.
        if "main_product_image_locator" not in images and summaries:
            mi = summaries[0].get("mainImage") or {}
            if isinstance(mi, dict) and str(mi.get("link", "")).startswith("http"):
                images["main_product_image_locator"] = mi["link"]

        if not images:
            return jsonify({"ok": False,
                            "error": "Amazon returned no images for this SKU"}), 404

        try:
            ws = _ws()
            headers = ws.row_values(1)
            if "Attributes JSON" not in headers:
                return jsonify({"ok": False, "error": "no attributes column"}), 400
            kcol = headers.index(SKU_HEADER) + 1
            trow = None
            for i, v in enumerate(ws.col_values(kcol), start=1):
                if str(v).strip() == sku:
                    trow = i
                    break
            if not trow:
                return jsonify({"ok": False, "error": "sku not found in sheet"}), 404
            acol = headers.index("Attributes JSON") + 1
            try:
                obj = json.loads(ws.cell(trow, acol).value or "{}")
            except Exception:
                obj = {}
            if not isinstance(obj, dict):
                obj = {}
            # drop the stale generation-time image locators, then write the live ones
            for k in [k for k in list(obj.keys()) if _LIVE_IMG_KEY.match(str(k))]:
                obj.pop(k, None)
            obj.update(images)
            ws.update_cell(trow, acol, json.dumps(obj))
            try:
                _bust_records_cache()
            except Exception:
                pass
        except Exception as e:
            return jsonify({"ok": False, "error": f"sheet write failed: {str(e)[:160]}"}), 500

        return jsonify({"ok": True, "sku": sku, "images": images, "count": len(images),
                        "asin": (summaries[0].get("asin", "") if summaries else ""),
                        "status": (summaries[0].get("status", []) if summaries else [])})

    @app.route("/listing/push_image", methods=["POST"])
    def listing_push_image():
        """Push ONLY the main image to the LIVE Amazon listing via patchListingsItem.
        Amazon must be able to fetch the image over the public internet, so we resolve
        the row's main image to a PUBLIC Drive direct URL (uploading to Drive first if
        it isn't there yet). Local /media/... paths are never sent to Amazon."""
        try:
            import accounts as _acc
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        b = request.get_json(force=True) or {}
        if not b.get("confirmed"):
            return jsonify({"ok": False, "error": "not confirmed"}), 400
        sku = (b.get("sku", "") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "missing sku"}), 400
        aid = b.get("id", "") or _state.get("active_account_id", "")
        mkt = (b.get("marketplace", "") or _state.get("active_marketplace") or "").upper()
        ptype = b.get("product_type", "") or ""

        # 1) find the row's current main image (what the user saved via "use as main")
        img = (b.get("image_url", "") or "").strip()
        if not img:
            try:
                _rec = next((r for r in _records(_ws())
                             if str(r.get("SKU", "")).strip() == sku), None)
            except Exception:
                _rec = None
            if _rec:
                for _k in ("main_product_image_locator", "Main Image", "main_image"):
                    if _rec.get(_k):
                        img = str(_rec.get(_k)).strip(); break
                if not img:
                    try:
                        _attrs = json.loads(_rec.get("Attributes JSON", "") or "{}")
                        img = str(_attrs.get("main_product_image_locator", "")).strip()
                    except Exception:
                        img = ""
        if not img:
            return jsonify({"ok": False, "error": "no main image found on this listing"}), 400

        # 2) resolve to a PUBLIC url Amazon can fetch
        public_url = ""
        if re.match(r"^https?://", img, re.I) and "/media/" not in img:
            # already a public URL (e.g. an lh3 Drive link or competitor URL)
            public_url = img
        else:
            # it's a local /media path -> use the Drive map, or upload to Drive now
            mapped = _drive_map_get(img)
            if mapped and mapped.get("direct_url"):
                public_url = mapped["direct_url"]
            else:
                # upload the local file to Drive right now, make public, map it
                m = re.match(r"^/media/(.+)$", img)
                if not m:
                    return jsonify({"ok": False, "error": "main image is a local path that can't be resolved"}), 400
                relpath = m.group(1)
                if ".." in relpath or relpath.startswith("/"):
                    return jsonify({"ok": False, "error": "bad image path"}), 400
                fpath = os.path.normpath(os.path.join(_media_root(), relpath))
                if not fpath.startswith(os.path.normpath(_media_root())) or not os.path.exists(fpath):
                    return jsonify({"ok": False, "error": "main image file not found on disk"}), 400
                acc0 = _active_account()
                folder = (acc0 or {}).get("drive_folder_url", "")
                parent_id = _drive_folder_id_from_url(folder)
                if not parent_id:
                    return jsonify({"ok": False, "error": "no Drive folder set for this account — can't make the image public for Amazon"}), 400
                try:
                    _prodttl = ""
                    try:
                        _rec2 = next((r for r in _records(_ws())
                                      if str(r.get("SKU", "")).strip() == sku), None)
                        _prodttl = (_rec2 or {}).get("Title", "") or ""
                    except Exception:
                        _prodttl = ""
                    res = _drive_upload_image(parent_id, sku, _prodttl, fpath,
                                              filename=os.path.basename(fpath))
                    public_url = res.get("direct_url", "")
                    if res.get("id"):
                        _drive_map_put(img, {"drive_id": res.get("id"),
                                             "direct_url": res.get("direct_url", ""),
                                             "view_url": res.get("view_url", "")})
                except Exception as e:
                    return jsonify({"ok": False, "error": f"could not upload image to Drive: {str(e)[:160]}"}), 502
        if not public_url:
            return jsonify({"ok": False, "error": "could not resolve a public image URL for Amazon"}), 400

        # 3) patch ONLY the main image on the live listing (reuse the gated push)
        acc = _acc.get_account(_cfg(), aid, CONFIG_PATH)
        if not acc:
            return jsonify({"ok": False, "error": "account not found"}), 404
        rt = str(acc.get("refresh_token", ""))
        if not rt or rt.startswith(("PUT_", "ROTATE")):
            return jsonify({"ok": False, "error": "connect this account first"}), 400
        creds = _acc.account_creds(acc)
        seller = acc.get("seller_id", "")
        mid = _acc.marketplace_id(mkt) if hasattr(_acc, "marketplace_id") else ""
        patches = _build_patches({"main_image": public_url})
        if not patches:
            return jsonify({"ok": False, "error": "could not build image patch"}), 400
        try:
            from sp_api.api import ListingsItemsV20210801 as LI
            from sp_api.base import Marketplaces
        except Exception as e:
            return jsonify({"ok": False, "error": f"sp_api Listings not available: {e}"}), 500
        mkt_enum = getattr(Marketplaces, mkt, None) or Marketplaces.US
        body = {"productType": ptype or "PRODUCT", "patches": patches}
        try:
            li = LI(credentials=creds, marketplace=mkt_enum)
            resp = li.patch_listings_item(seller, sku,
                                          marketplaceIds=[mid] if mid else None, body=body)
            pay = resp.payload if hasattr(resp, "payload") else resp
        except Exception as e:
            return jsonify({"ok": False, "error": f"patchListingsItem failed: {str(e)[:240]}"}), 502
        status = (pay or {}).get("status", "") if isinstance(pay, dict) else ""
        issues = (pay or {}).get("issues", []) if isinstance(pay, dict) else []
        ok = status.upper() in ("ACCEPTED", "VALID") or not issues
        return jsonify({"ok": ok, "status": status, "issues": issues,
                        "public_url": public_url, "raw": pay})

    @app.route("/suggest", methods=["POST"])
    def suggest():
        """For a listing's missing/flagged fields, produce a value for each, walking a
        SOURCE PRIORITY chain and labelling where each answer came from:
          1) eBay source (the item we actually sell) -- item specifics
          2) SP-API competitor ASIN data (Amazon)
          3) Amazon search (best-effort; honest about confidence)
          4) AI reasoning (clearly labelled)
        Returns: {ok, product:{title,...}, suggestions:[{field,value,source,confidence,note}]}
        The eBay product stays the anchor throughout."""
        b = request.get_json(force=True) or {}
        sku    = str(b.get("sku", "")).strip()
        fields = b.get("fields") or []          # field keys to fill; empty = infer from flags
        if not sku:
            return jsonify({"ok": False, "error": "missing sku"}), 400

        cfg = _cfg()
        # find the row
        recs = _records(_ws())
        row = None
        for r in recs:
            if str(r.get("SKU", "")).strip() == sku:
                row = r
                break
        if not row:
            return jsonify({"ok": False, "error": "sku not found in current view"}), 404

        try:
            attrs = json.loads(row.get("Attributes JSON") or "{}")
            if not isinstance(attrs, dict): attrs = {}
        except Exception:
            attrs = {}
        title       = row.get("Title", "") or row.get("Product Title", "")
        product_type= row.get("Product Type", "") or attrs.get("product_type", "")
        ebay_url    = row.get("eBay URL", "") or row.get("Source URL", "") or row.get("eBay Link", "")
        comp_asin   = row.get("Competitor ASIN", "") or row.get("ASIN", "")
        marketplace = _marketplace_for_row(row)

        # if no explicit fields requested, derive from the flag note (required-but-missing)
        if not fields:
            note = (row.get("Notes", "") or "") + " " + (row.get("Comp Notes", "") or "")
            fields = _parse_required_missing(note)

        # Rule 1: NEVER let the AI guess a product identifier / barcode. The owner
        # supplies real purchased EANs in the sheet's UPC ("Barcode / GTIN") box, and
        # the builder uses that as the single source of truth (else it claims the GTIN
        # exemption). Strip any identifier field so the auto-fix loop can't invent one.
        _ID_SKIP = {"externally_assigned_product_identifier", "standard_product_id",
                    "external_product_id", "merchant_suggested_asin"}
        fields = [f for f in fields
                  if str(f).split(".", 1)[0].strip().lower() not in _ID_SKIP]

        # ---- gather SOURCES (the eBay product is the anchor) ----
        sources = {"ebay": {}, "sp": {}, "ebay_image": "", "raw": {}}
        # tier 1: eBay specifics
        try:
            from amazon_listing_generator import fetch_ebay_supplement
            _eb_app, _eb_cert = _ebay_creds()   # account override wins, else global
            eb = fetch_ebay_supplement(ebay_url, _eb_app, _eb_cert)
            sources["ebay"] = (eb.get("item_specifics") or {})
            imgs = eb.get("images") or eb.get("image_urls") or []
            sources["ebay_image"] = imgs[0] if imgs else (attrs.get("main_product_image_locator", "") or "")
            sources["raw"]["ebay_title"] = eb.get("title", "")
            sources["raw"]["ebay_desc"]  = eb.get("description", "")
        except Exception as e:
            sources["raw"]["ebay_error"] = str(e)[:160]
        # tier 2: SP-API competitor data
        if comp_asin:
            try:
                from amazon_listing_generator import get_competitor_asin_data
                sp = get_competitor_asin_data(comp_asin, _sp_creds(marketplace))
                sources["sp"] = sp.get("attributes", sp) if isinstance(sp, dict) else {}
            except Exception as e:
                sources["raw"]["sp_error"] = str(e)[:160]

        # ---- per-field resolution via the priority chain + AI to finalise ----
        suggestions = _resolve_fields(cfg, fields, attrs, sources, title, product_type, marketplace)
        return jsonify({"ok": True,
                        "product": {"title": title, "sku": sku, "product_type": product_type,
                                    "ebay_image": sources["ebay_image"], "ebay_url": ebay_url},
                        "suggestions": suggestions})

    @app.route("/ask", methods=["POST"])
    def ask():
        b       = request.get_json(force=True) or {}
        history = b.get("messages", [])
        ctx     = b.get("context")
        uploads = b.get("images", [])
        key = (_cfg().get("anthropic_api_key") or "").strip()
        if not key:
            return jsonify({"ok": False, "error": "No anthropic_api_key in config.json"}), 400
        if not history:
            return jsonify({"ok": False, "error": "empty message"}), 400
        try:
            import anthropic
        except ImportError:
            return jsonify({"ok": False, "error": "anthropic not installed (pip install anthropic)"}), 500
        try:
            client = anthropic.Anthropic(api_key=key)
            system = (
                "You are a practical assistant embedded in an Amazon UK listing tool. You help the seller "
                "choose values for listing attributes (size, is_assembly_required, material, dimensions, "
                "item_type_keyword, colour, etc.) for the product they are listing. Give concise, decisive "
                "answers with brief reasoning. Use UK marketplace conventions and metric units where relevant. "
                "If the user shares a competitor image, read it carefully and answer what it shows (for example "
                "whether assembly looks required). If unsure, say so and say how to confirm. Keep answers short "
                "unless asked for more detail."
            )
            api_messages = []
            for m in history:
                role = "assistant" if m.get("role") == "assistant" else "user"
                api_messages.append({"role": role, "content": str(m.get("text", ""))})
            if api_messages and api_messages[-1]["role"] == "user":
                last_text = api_messages[-1]["content"]
                blocks = []
                for img in uploads:
                    d = img.get("data")
                    if d:
                        blocks.append({"type": "image", "source": {
                            "type": "base64", "media_type": img.get("media_type", "image/jpeg"), "data": d}})
                for u in _URL_RE.findall(last_text)[:4]:
                    got = _fetch_image_b64(u)
                    if got:
                        blocks.append({"type": "image", "source": {
                            "type": "base64", "media_type": got[0], "data": got[1]}})
                prefix = ""
                if ctx:
                    prefix = ("The user is asking about this listing:\n"
                              + json.dumps(ctx, ensure_ascii=False, indent=2) + "\n\n")
                blocks.append({"type": "text", "text": prefix + last_text})
                api_messages[-1]["content"] = blocks
            resp  = client.messages.create(model=CHAT_MODEL, max_tokens=1500,
                                           system=system, messages=api_messages)
            reply = "".join(getattr(p, "text", "") for p in resp.content
                            if getattr(p, "type", "") == "text")
            return jsonify({"ok": True, "reply": reply or "(no text in response)"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]}), 500

    @app.route("/input_sheet")
    def input_sheet():
        """Return the active account's INPUT sheet as a grid (headers + rows) so it can
        be shown inside the app without opening Google Sheets separately. Read-only."""
        acc = _active_account()
        if not acc:
            return jsonify({"ok": False, "error": "no active account"}), 400
        sid = (acc.get("input_spreadsheet_id") or "").strip()
        gid = str(acc.get("input_tab_gid") or "").strip()
        in_url = acc.get("input_sheet_url", "") or ""
        if not sid:
            m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", in_url)
            if m:
                sid = m.group(1)
        if not sid:
            return jsonify({"ok": False, "error": "no input sheet configured for this account"}), 400
        try:
            book = _client().open_by_key(sid)
            ws = None
            if gid.isdigit():
                try:
                    ws = book.get_worksheet_by_id(int(gid))
                except Exception:
                    ws = None
            if ws is None:
                ws = book.sheet1
            title = ws.title
            grid = ws.get_all_values()
            headers = grid[0] if grid else []
            rows = grid[1:] if len(grid) > 1 else []
            view_url = f"https://docs.google.com/spreadsheets/d/{sid}/edit"
            if gid.isdigit():
                view_url += f"#gid={gid}"
            return jsonify({"ok": True, "title": title, "headers": headers, "rows": rows,
                            "row_count": len(rows), "col_count": len(headers),
                            "sheet_id": sid, "gid": gid, "view_url": view_url})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500

    @app.route("/row")
    def single_row():
        """Return one row's fresh data by SKU (cache-bypassed) so the drawer can
        refresh its status/notes right after an API preview/submit."""
        sku = (request.args.get("sku") or "").strip()
        if not sku:
            return jsonify({"ok": False, "error": "missing sku"}), 400
        try:
            _bust_records_cache()                     # force a truly fresh read
            data = _records(_ws(), _use_cache=False)
            for i, r in enumerate(data):
                if str(r.get("SKU", "")).strip() == sku:
                    c = _card(r)
                    c["row"] = i + 2
                    return jsonify({"ok": True, "row": c})
            return jsonify({"ok": False, "error": "sku not found"}), 404
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/rows")
    def rows():
        try:
            ws    = _ws()
            data  = _records(ws)
            cards = []
            for i, r in enumerate(data):
                c = _card(r)
                c["row"] = i + 2          # actual sheet row number (row 1 = header)
                cards.append(c)
            # Report the sheet/tab we ACTUALLY read, straight off the worksheet object,
            # so the header shows the real data source rather than what config claims.
            src = {}
            try:
                src = {"sheet_id": ws.spreadsheet.id, "tab": ws.title,
                       "tab_gid": str(ws.id), "url": ws.url}
            except Exception:
                src = {}
            return jsonify({"ok": True,
                            "shipping_group": _cfg().get("merchant_shipping_group", ""),
                            "product_types": _product_types(),
                            "source": src,
                            "rows": cards})
        except Exception as e:
            # SheetScopeError (dashboard.py) = this workspace has no sheet/tab configured.
            # Checked by name to avoid a circular import back into dashboard.
            _scope = type(e).__name__ == "SheetScopeError"
            return (jsonify({"ok": False, "error": str(e), "sheet_scope_error": _scope}),
                    200 if _scope else 500)

    @app.route("/approve", methods=["POST"])
    def approve():
        body   = request.get_json(force=True) or {}
        sku    = str(body.get("sku", "")).strip()
        status = str(body.get("status", "")).strip().upper()
        if status not in _VALID_SET_STATUS:
            return jsonify({"ok": False, "error": "invalid status"}), 400
        if not sku:
            return jsonify({"ok": False, "error": "no sku"}), 400
        try:
            ws      = _ws()
            headers = ws.row_values(1)
            scol    = headers.index(STATUS_HEADER) + 1
            kcol    = headers.index(SKU_HEADER) + 1
            target  = None
            for i, v in enumerate(ws.col_values(kcol), start=1):
                if str(v).strip() == sku:
                    target = i
                    break
            if not target:
                return jsonify({"ok": False, "error": "sku not found in sheet"}), 404
            ws.update_cell(target, scol, status)
            _bust_records_cache()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/schema/<path:pt>")
    def schema(pt):
        try:
            # The listing's OWN marketplace can be passed explicitly (?mkt=US) so the
            # right schema+creds are used regardless of the global active_marketplace.
            # This fixes US-account listings loading an empty UK schema (wrong creds).
            _mkt_param = (request.args.get("mkt") or "").strip().upper()
            _prev_mkt = _state.get("active_marketplace", "")
            if _mkt_param:
                _state["active_marketplace"] = _mkt_param
            try:
                # ?refresh=1 clears the cached schema for this product type so the new
                # (unenforced-merged) enums are re-fetched without a server restart.
                if request.args.get("refresh"):
                    _mkt = str(_state.get("active_marketplace", "") or "UK").upper()
                    _state["schemas"].pop(f"{pt}::{_mkt}", None)
                payload = {"ok": True, "enums": _options_for(pt), "required": _schema_required(pt),
                           "attrs": _schema_attrs(pt), "subfields": _schema_subfields(pt),
                           "titles": _load_schema(pt).get("titles", {}),
                           "marketplace": str(_state.get("active_marketplace", "") or "UK").upper(),
                           "enum_count": len(_options_for(pt)),
                           "schema_error": _load_schema(pt).get("_error", "")}
                return jsonify(payload)
            finally:
                # restore global state so a one-off schema fetch doesn't change the
                # user's active workspace marketplace
                if _mkt_param:
                    _state["active_marketplace"] = _prev_mkt
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/edit", methods=["POST"])
    def edit():
        b      = request.get_json(force=True) or {}
        sku    = str(b.get("sku", "")).strip()
        target = b.get("target")
        key    = str(b.get("key", "")).strip()
        value  = b.get("value", "")
        if not sku or not key:
            return jsonify({"ok": False, "error": "missing sku/key"}), 400
        try:
            ws      = _ws()
            headers = ws.row_values(1)
            kcol    = headers.index(SKU_HEADER) + 1
            trow    = None
            for i, v in enumerate(ws.col_values(kcol), start=1):
                if str(v).strip() == sku:
                    trow = i
                    break
            if not trow:
                return jsonify({"ok": False, "error": "sku not found in sheet"}), 404
            if target == "col":
                if key not in _EDITABLE_COLS or key not in headers:
                    return jsonify({"ok": False, "error": "column not editable"}), 400
                ws.update_cell(trow, headers.index(key) + 1, value)
            elif target == "attr":
                if "Attributes JSON" not in headers:
                    return jsonify({"ok": False, "error": "no attributes column"}), 400
                acol = headers.index("Attributes JSON") + 1
                cur  = ws.cell(trow, acol).value or "{}"
                try:
                    obj = json.loads(cur)
                except Exception:
                    obj = {}
                if not isinstance(obj, dict):
                    obj = {}
                if str(value).strip() == "":
                    obj.pop(key, None)
                else:
                    # PREFIX CLEANUP: when writing a deeper dot-key like
                    # `leg.length.decimal_value`, purge any shallower keys at
                    # the same prefix (`leg`, `leg.length`) that are STRINGS.
                    # Without this, older shallow saves (from prior schema-
                    # extractor versions) sit alongside new deeper saves and
                    # collide in the generator's _renest, crashing with
                    # "'str' object does not support item assignment".
                    # Only strip when the shallower value is a scalar -- if
                    # it's already a dict (a previous nested write), leave it
                    # alone. Also strip DEEPER keys under the same prefix when
                    # we write a scalar (rare -- happens if user manually
                    # replaces a nested attr with a single value).
                    if "." in key:
                        parts = key.split(".")
                        for i in range(1, len(parts)):
                            prefix = ".".join(parts[:i])
                            if prefix in obj and not isinstance(obj[prefix], dict):
                                obj.pop(prefix, None)
                    else:
                        # New scalar write: strip any dot-keys underneath us
                        _pfx = key + "."
                        for _stale in [k for k in list(obj.keys()) if k.startswith(_pfx)]:
                            obj.pop(_stale, None)
                    obj[key] = value
                ws.update_cell(trow, acol, json.dumps(obj, ensure_ascii=False))
            else:
                return jsonify({"ok": False, "error": "bad target"}), 400
            _bust_records_cache()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/delete", methods=["POST"])
    def delete_row():
        b   = request.get_json(force=True) or {}
        sku = str(b.get("sku", "")).strip()
        row = b.get("row")
        try:
            ws     = _ws()
            target = None
            if sku:                                   # prefer matching by SKU (stable)
                headers = ws.row_values(1)
                if SKU_HEADER in headers:
                    kcol = headers.index(SKU_HEADER) + 1
                    for i, v in enumerate(ws.col_values(kcol), start=1):
                        if str(v).strip() == sku:
                            target = i
                            break
            if target is None and row:                # fall back to row number (blank rows)
                try:
                    target = int(row)
                except Exception:
                    target = None
            if not target or target < 2:
                return jsonify({"ok": False, "error": "row not found"}), 404
            ws.delete_rows(target)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/clear_empty", methods=["POST"])
    def clear_empty():
        """Delete every data row whose SKU, Title, Competitor ASIN and Product Type are all blank."""
        try:
            ws   = _ws()
            vals = ws.get_all_values()
            if not vals:
                return jsonify({"ok": True, "deleted": 0})
            headers = vals[0]
            keycols = [headers.index(h) for h in (SKU_HEADER, "Title", "Competitor ASIN", "Product Type")
                       if h in headers]
            blanks = []
            for r in range(1, len(vals)):                       # data rows (row 2 = index 1)
                rv = vals[r]
                if all((c >= len(rv) or not str(rv[c]).strip()) for c in keycols):
                    blanks.append(r + 1)                        # 1-based sheet row
            for rownum in sorted(blanks, reverse=True):         # bottom-up keeps indices valid
                ws.delete_rows(rownum)
            return jsonify({"ok": True, "deleted": len(blanks)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/run/<mode>")
    def run(mode):
        if mode not in ("generate", "retry", "export", "api", "api_submit", "api_verify", "regen"):
            return Response("data: [error] unknown mode\n\nevent: end\ndata: end\n\n",
                            mimetype="text/event-stream")

        # IMPORTANT: read request.args HERE, inside the request context. The streaming
        # generator below runs OUTSIDE the request context, where `request` is gone --
        # touching it there raises "Working outside of request context" and kills the
        # stream before any data is sent (looks like "couldn't reach the stream").
        _req_skus = (request.args.get("skus") or "").strip()
        _req_select = (request.args.get("select") or "").strip()
        _req_select_type = (request.args.get("select_type") or "auto").strip()
        _req_minimal = (request.args.get("minimal") or "") == "1"

        # PUBLISH GATE. api_submit writes to Amazon. A workspace with no Amazon app of
        # its own must never reach the generator: the generator falls back to the global
        # sp_api_* credential block, which is jack_uk's -- so a submit from a read-only
        # workspace would publish into Jack Reacherd's catalogue.
        if mode in ("api_submit", "api_verify"):
            try:
                _require_publish()
            except Exception as _e:
                _msg = str(_e).replace("\n", " ")
                return Response(f"data: [error] {_msg}\n\nevent: end\ndata: end\n\n",
                                mimetype="text/event-stream")

        def stream():
            if not _acquire_run_lock():
                yield "data: [busy] a run is already in progress -- wait for it to finish\n\n"
                yield "event: end\ndata: end\n\n"
                return
            try:
                # -u = unbuffered child stdout so progress streams live
                extra = ([] if mode == "generate"
                         else ["api", "submit"] if mode == "api_submit"
                         else ["api", "verify"] if mode == "api_verify"
                         else [mode])
                # REGEN: re-run the generator scoped to a specific set of SKUs and the
                # active sheet/tab/marketplace. Needs generator support for --skus.
                if mode == "regen":
                    skus = _req_skus
                    _sid = _state.get("active_sheet_id")
                    _tab = _state.get("active_tab")
                    _mkt = _state.get("active_marketplace") or ""
                    extra = ["regen"]
                    if skus: extra += ["--skus", skus]
                    if _sid: extra += ["--sheet", _sid]
                    if _tab: extra += ["--tab", _tab]
                    if _mkt: extra += ["--marketplace", _mkt]
                # SCOPE TO THE ACTIVE ACCOUNT/WORKSPACE for ALL modes (including
                # generate) so listings are created on the CORRECT account's sheet --
                # not the default dropshipping sheet. Account sheet/tab take priority;
                # brand-view scoping (below) refines marketplace for api/submit.
                try:
                    _acc = _active_account()
                except Exception:
                    _acc = None
                if _acc:
                    _acc_id = _acc.get("id") or ""
                    if _acc_id and "--account-id" not in extra:
                        extra += ["--account-id", _acc_id]
                    _acc_sheet = _acc.get("output_spreadsheet_id") or ""
                    _acc_tab = _acc.get("output_tab") or _acc.get("output_worksheet") or ""
                    _acc_out_gid = str(_acc.get("output_tab_gid") or "")
                    _acc_in_sheet = _acc.get("input_spreadsheet_id") or ""
                    _acc_in_gid = str(_acc.get("input_tab_gid") or "")
                    if _acc_sheet and "--sheet" not in extra:
                        extra += ["--sheet", _acc_sheet]
                    if _acc_tab and "--tab" not in extra:
                        extra += ["--tab", _acc_tab]
                    if _acc_out_gid and "--tab-gid" not in extra:
                        extra += ["--tab-gid", _acc_out_gid]
                    if _acc_in_sheet and "--input-sheet" not in extra:
                        extra += ["--input-sheet", _acc_in_sheet]
                    if _acc_in_gid and "--input-tab-gid" not in extra:
                        extra += ["--input-tab-gid", _acc_in_gid]
                    # marketplace (US/UK) for this account -- so pricing, fees, SP-API
                    # and the flat-file route match the account, not the UK default.
                    _acc_mkt = (_acc.get("default_marketplace") or "").strip().upper()
                    if _acc_mkt not in ("US", "UK", "GB") and _acc.get("marketplaces"):
                        # pick the first US/UK/GB entry, not blindly [0] (which can be
                        # MX/CA/BR -> generator would fall through to the UK default
                        # and deny a US token on catalog/pricing/fees).
                        for _mm in _acc["marketplaces"]:
                            _mmu = str(_mm).strip().upper()
                            if _mmu in ("US", "UK", "GB"):
                                _acc_mkt = _mmu
                                break
                    if _acc_mkt and "--marketplace" not in extra:
                        extra += ["--marketplace", _acc_mkt]
                else:
                    # DROPSHIPPING (no active account): honour the user-assigned default
                    # sheets from "AI & settings ▸ Dropshipping sheets", if set. Purely
                    # additive -- when unset, nothing is passed and the generator uses
                    # its config.json defaults exactly as before (zero regression). We
                    # pass BOTH the tab name (--tab, for api/regen whose run_api opens
                    # the worksheet by name) and the gid (--tab-gid, for generate whose
                    # init_sheets resolves by gid), so either path targets the right tab.
                    _cfg0 = _cfg()
                    _ds_out  = str(_cfg0.get("dropshipping_output_spreadsheet_id") or "").strip()
                    _ds_otab = str(_cfg0.get("dropshipping_output_tab") or "").strip()
                    _ds_ogid = str(_cfg0.get("dropshipping_output_tab_gid") or "").strip()
                    _ds_in   = str(_cfg0.get("dropshipping_input_spreadsheet_id") or "").strip()
                    _ds_igid = str(_cfg0.get("dropshipping_input_tab_gid") or "").strip()
                    if _ds_out and "--sheet" not in extra:
                        extra += ["--sheet", _ds_out]
                    if _ds_otab and "--tab" not in extra:
                        extra += ["--tab", _ds_otab]
                    if _ds_ogid and "--tab-gid" not in extra:
                        extra += ["--tab-gid", _ds_ogid]
                    if _ds_in and "--input-sheet" not in extra:
                        extra += ["--input-sheet", _ds_in]
                    if _ds_igid and "--input-tab-gid" not in extra:
                        extra += ["--input-tab-gid", _ds_igid]
                # If a brand view is active, scope api preview/submit to THAT sheet +
                # marketplace only -- so it never previews every marketplace/account
                # at once (which would waste credits), and validates against the
                # correct catalogue (US for US brands).
                if mode in ("api", "api_submit", "api_verify"):
                    # per-listing Preview/Submit/Verify: a ?skus= filter limits to those SKUs
                    _api_skus = _req_skus
                    if _api_skus and "--skus" not in extra:
                        extra += ["--skus", _api_skus]
                    if _req_minimal and "--minimal" not in extra:
                        extra += ["--minimal"]
                    _sid = _state.get("active_sheet_id")
                    _tab = _state.get("active_tab")
                    _mkt = ""
                    # resolve marketplace from the active brand profile, if any
                    _vk = _state.get("active_view") or ""
                    if _vk:
                        try:
                            import glob as _glob, os as _os
                            for _pf in _glob.glob(_os.path.join(_os.path.dirname(CONFIG_PATH), "brands", "*", "profile.json")):
                                _p = json.load(open(_pf, encoding="utf-8"))
                                if (_p.get("brand_name") or "") == _vk:
                                    _mkt = _p.get("marketplace", "") or ""
                                    break
                        except Exception:
                            pass
                    if _sid:
                        extra += ["--sheet", _sid]
                    if _tab:
                        extra += ["--tab", _tab]
                    if _mkt:
                        extra += ["--marketplace", _mkt]
                # ROW SELECTION (generate only): limit the run to chosen input rows.
                # Empty -> generator processes all rows (unchanged).
                if mode == "generate" and _req_select:
                    extra += ["--select", _req_select]
                    extra += ["--select-type", _req_select_type or "auto"]
                args = [sys.executable, "-u", SCRIPT] + extra
                yield f"data: [start] {' '.join(args)}\n\n"
                p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
                _running["proc"] = p
                try:
                    # generation asks once for a brand; feed the configured one (Enter = auto)
                    if mode == "generate":
                        p.stdin.write((_cfg().get("brand_name", "") or "") + "\n")
                    p.stdin.flush()
                    p.stdin.close()
                except Exception:
                    pass
                for line in iter(p.stdout.readline, ""):
                    clean = _ANSI.sub("", line.rstrip("\n"))
                    if clean.strip():
                        yield f"data: {clean}\n\n"
                p.wait()
                yield f"data: [done] finished (exit code {p.returncode})\n\n"
                yield "event: end\ndata: end\n\n"
            finally:
                with _run_lock:
                    _running["proc"] = None
                    _running["on"] = False

        return Response(stream(), mimetype="text/event-stream")

