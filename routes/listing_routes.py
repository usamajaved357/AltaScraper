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

from routes.stream_pump import pump_lines, spawn
# NOT named _scope: this module already uses `_scope` as a LOCAL boolean inside
# two except blocks (`_scope = type(e).__name__ == "SheetScopeError"`). Python
# treats a name assigned anywhere in a function as local throughout it, so a
# module-level `_scope` is unreachable in those functions and every call raised
# UnboundLocalError -- which surfaced as a 500 on /rows_all and an empty
# listings page. Renaming the import is the small fix; renaming their local
# would be editing code this change has no business touching.
from domain import account_scope as _acctscope   # the ONE "is this the open account" rule
from listing import repo as _repo       # the ONE SKU->row lookup (Rule 12)
from listing import run_status          # honest run state, independent of the log pipe

from listing.compliance import check_category_claims  # category-aware claims screener (task #18)
from listing.restricted import check_restricted_type   # restricted-products library (Shape 2)
from listing.sourcing_viability import check_sourcing_viability  # document-demand risk (WARN only)

# Map the screener's field name -> the sheet column header to WRITE a rewrite into.
# Standard 48-col layout first, then the Miles 12-col layout, so the one-click "Apply
# rewrite" targets the correct column on either sheet format.
_CLAIM_COL_STD = {
    "title": "Title", "item_highlights": "Item Highlights",
    "description": "Description (HTML)",
    "bullet_1": "Bullet 1", "bullet_2": "Bullet 2", "bullet_3": "Bullet 3",
    "bullet_4": "Bullet 4", "bullet_5": "Bullet 5",
}
_CLAIM_COL_MILES = {
    "item_highlights": "Highlights", "description": "Description",
    "bullet_1": "Bullet Point 1", "bullet_2": "Bullet Point 2",
    "bullet_3": "Bullet Point 3", "bullet_4": "Bullet Point 4",
    "bullet_5": "Bullet Point 5",
}


def _claim_write_col(field, r):
    """The header actually present on THIS row for a screener field (standard vs Miles)."""
    std = _CLAIM_COL_STD.get(field, "")
    if std and std in r:
        return std
    miles = _CLAIM_COL_MILES.get(field, "")
    if miles and miles in r:
        return miles
    return std


def _attach_claim_flags(c, r):
    """Re-run the (no-AI, pure pattern-match) category screener on a card's finished
    copy and attach structured flags for the UI badge / in-copy highlight / rewrite.
    Computed at read time so the card always reflects the CURRENT rulebook -- no new
    sheet column. WARN only; carries no blocking effect."""
    bl = c.get("bullets") or []
    view = {
        "title": c.get("title", ""), "item_highlights": c.get("item_highlights", ""),
        "description": c.get("description", ""),
        "bullet_1": bl[0] if len(bl) > 0 else "", "bullet_2": bl[1] if len(bl) > 1 else "",
        "bullet_3": bl[2] if len(bl) > 2 else "", "bullet_4": bl[3] if len(bl) > 3 else "",
        "bullet_5": bl[4] if len(bl) > 4 else "",
    }
    try:
        cc = check_category_claims(view, c.get("product_type", ""))
    except Exception:
        cc = {"hits": [], "summary": ""}
    flags = []
    for h in cc.get("hits", []):
        h2 = dict(h)
        h2["col"] = _claim_write_col(h.get("field", ""), r)
        flags.append(h2)
    c["claim_flags"] = flags
    c["claim_summary"] = cc.get("summary", "")
    c["claim_level"] = ("RED" if any(f.get("severity") == "RED" for f in flags)
                        else ("AMBER" if flags else ""))
    return c


def _attach_restricted(c, r):
    """Run the tuned restricted-products engine (Shape 2, WARN only) on a card and attach
    the result for the 'Restricted products check' panel. Read-only; never blocks. Uses the
    product signals the card already carries (title + product_type + Amazon category +
    marketplace); clean products return matched=False so the panel stays quiet (doormat rule)."""
    try:
        res = check_restricted_type(
            c.get("title", ""), str(c.get("_marketplace", "") or "").upper(),
            product_type=c.get("product_type", ""), category_path=c.get("category", ""))
    except Exception:
        res = {"matched": False, "matches": [], "overall_action": "NONE",
               "message": "", "caveat": ""}
    c["restricted"] = res
    return c


def _attach_identifier(c, r, config_path, workspace_id):
    """Can this listing be created at all -- barcode, exemption, or neither?

        "maybe i used the barcode of my another listing, so the app should tell me"

    Amazon needs ONE product identifier. This says which of the three states a
    listing is in BEFORE it is submitted, because the alternative is what
    actually happened: submitted, "SUBMITTED" on screen for a fortnight, and
    Amazon's refusal sitting unread on the listing.

    The clash is the part that had never been checked. MEASURED: EAN
    4545644574860 was on a LIVE jack_uk listing and on the nestwell_goods one he
    submitted, and Amazon refused the second because the barcode already named
    the first one's ASIN. Sixteen barcodes in the store are on more than one
    listing.

    Read-only, and it never blocks -- it says what will happen. Attached like the
    restricted and viability checks beside it.
    """
    from domain import barcode_clash as _bc
    from listing.barcode import gtin_or_reason

    raw = str(r.get("UPC") or "").strip()
    exempt = str(r.get("GTIN Exemption") or "").strip().lower() in (
        "1", "y", "yes", "true", "on", "x", "exempt")
    code, _typ, why = gtin_or_reason(raw)
    clash = []
    try:
        if code:
            clash = _bc.others_with(config_path, code,
                                    exclude_workspace=workspace_id,
                                    exclude_sku=str(r.get("SKU") or ""))
    except Exception:
        clash = []
    out = {"barcode": code, "raw": raw, "exemption": exempt,
           "why_unusable": ("" if code else why),
           "clash": clash, "clash_note": _bc.sentence(clash, code),
           "blocking": False, "note": ""}
    if code and clash and any(x["live"] for x in clash):
        # The case that already cost him a listing.
        out["blocking"] = True
        out["note"] = out["clash_note"]
    elif not code and not exempt:
        out["blocking"] = True
        out["note"] = ((why or "There is no barcode in the box")
                       + ". Amazon needs a barcode or a GTIN exemption, and the "
                         "exemption is not ticked, so this listing cannot be "
                         "created. Enter a barcode, or tick “Apply for GTIN "
                         "exemption”.")
    elif not code and exempt:
        out["note"] = ("No barcode, and you have ticked the GTIN exemption -- "
                       "so the listing declares to Amazon that this product has "
                       "no barcode.")
    c["identifier"] = out
    return c


def _attach_viability(c, r):
    """Attach the SOURCING VIABILITY result (document-demand risk) for the card's
    'Compliance requirements' panel.

    Deliberately separate from _attach_restricted above, because it answers a
    different question. Restricted = "may I list this at all?". Viability = "which
    safety documents will Amazon demand later, and can I produce them?". The patio
    heater is why: it was never restricted, so that panel stayed silent while the
    BS EN 60335 obligation went unseen until the ASIN was already selling.

    Read-only and WARN-only, exactly like the restricted attach, and equally
    tolerant: a reference-data fault returns an empty result rather than breaking
    the card."""
    try:
        res = check_sourcing_viability(
            title=c.get("title", ""),
            bullets=(c.get("bullets") or []),
            product_type=c.get("product_type", ""),
            category=c.get("category", ""),
            marketplace=str(c.get("_marketplace", "") or "").upper())
    except Exception:
        res = {"matched": False, "risks": [], "verdict": "VIABLE",
               "overall_action": "NONE", "warnings": [], "message": "", "caveat": ""}
    c["viability"] = res
    return c


def register(app, *, CHAT_MODEL, CONFIG_PATH, SCRIPT, SKU_HEADER, STATUS_HEADER, _ANSI, _EDITABLE_COLS, _URL_RE, _VALID_SET_STATUS, _acquire_run_lock, _active_account, _build_patches, _bust_records_cache, _card, _cfg, _client, _drive_folder_id_from_url, _drive_map_get, _drive_map_put, _drive_upload_image, _ebay_creds, _fetch_image_b64, _load_schema, _marketplace_for_row, _media_root, _options_for, _parse_required_missing, _product_types, _records, _resolve_fields, _run_lock, _running, _schema_attrs, _schema_required, _schema_subfields, _sp_creds, _state, _ws, _require_publish=lambda acc=None: acc, _public_media_url=lambda u: ""):
    """Attach the paths:/suggest,/ask,/input_sheet,/row,/rows,/approve,/schema/<path:pt>,/edit,/delete,/clear_empty,/listing/push_image,/run/<mode> routes to the existing Flask app."""

    _LIVE_IMG_KEY = re.compile(
        r"^(main_product_image_locator|other_product_image_locator_\d+|swatch_image_locator)$")

    def _wrong_account(asked, subject="listing"):
        """None when this request may proceed; a refusal response when it may not.

        THE ROUTES THIS GUARDS ALL WORK BY SKU. /row, /edit, /delete and
        /live/pull_row each take a SKU and find it inside whatever workspace the
        SERVER currently has selected -- they never checked that this is the
        workspace the browser is looking at. /rows_all has checked since the
        listings-under-the-wrong-name bug; these four, reached from the same
        screen, did not. That is the shape of hole that survives a fix.

        MEASURED, so the size of it is not overstated: 282 rows across five
        accounts, 282 distinct SKUs, none shared between two accounts. A stale
        account therefore yields "sku not found" today rather than the wrong
        row. It is a latent hazard, not an active leak -- but two of these four
        are WRITES, nothing keeps SKUs unique (they are price_days_ASIN, so two
        accounts sourcing the same product at the same price collide), and the
        cost of the guard is one comparison.

        Callers that send no account are unaffected, so this could go in ahead
        of the callers being taught to send one.
        """
        _aid = _state.get("active_account_id")
        if _acctscope.is_mismatch(asked, _aid):
            return jsonify(_acctscope.refusal(asked, _aid, subject)), 409
        return None

    def _store_for(aid):
        """The listings store for ONE named workspace, on the database backend.

        "no one account data should be shared with another"

        On the database a workspace IS the unit of storage -- data/store.StoreBook
        says it plainly, "on the database a tab is a workspace" -- so a store can
        simply be opened for the account that was asked about. Verified before
        this was used: ListingStore("jack_uk") holds 87 SKUs,
        ListingStore("nestwell_goods") 86, and none is shared between them.

        Returns None when there is no account to open or the backend is not the
        database, so callers keep their existing behaviour rather than losing
        their rows to a helper that could not help.
        """
        aid = str(aid or "").strip()
        if not aid:
            return None
        try:
            from data import choice as _ch
            if _ch.resolve(_cfg(), None) != "db":
                return None
            from data.store import ListingStore, SheetLikeStore
            return SheetLikeStore(ListingStore(aid, config_path=CONFIG_PATH))
        except Exception:
            return None

    def _asked_account():
        """The account the caller named, or None. Body first, then query string.

        Both shapes are in use across the callers -- POST routes carry JSON,
        /row is a GET -- and a route should not care which one reached it.
        """
        try:
            if request.method == "POST":
                b = request.get_json(silent=True) or {}
                if isinstance(b, dict) and "account" in b:
                    return b.get("account")
        except Exception:
            pass
        return request.args.get("account")

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
        # A WRITE: it merges Amazon's live images back into the row.
        _bad = _wrong_account(b.get("account"))
        if _bad:
            return _bad
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
            found = _repo.locate(ws, sku, sku_headers=(SKU_HEADER,))
            if "Attributes JSON" not in found.headers:
                return jsonify({"ok": False, "error": "no attributes column"}), 400
            if not found.ok:
                return jsonify({"ok": False, "error": found.error}), 404
            trow = found.row
            acol = found.col("Attributes JSON")
            try:
                obj = json.loads(_repo.cell_value(ws, trow, acol) or "{}")
            except Exception:
                obj = {}
            if not isinstance(obj, dict):
                obj = {}
            # drop the stale generation-time image locators, then write the live ones
            for k in [k for k in list(obj.keys()) if _LIVE_IMG_KEY.match(str(k))]:
                obj.pop(k, None)
            obj.update(images)
            _repo.set_field(ws, trow, "Attributes JSON", json.dumps(obj),
                            headers=found.headers)
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
        # A WRITE to a LIVE listing (patchListingsItem). It took `id` from the
        # caller and used that account's credentials, so naming another account
        # here would push an image onto their shopfront.
        _bad = _wrong_account(b.get("id"), "listing")
        if _bad:
            return _bad
        # WRITE (patchListingsItem). A workspace that owns its Amazon app passes
        # straight through -- this only stops read-only/borrowing workspaces, which
        # would otherwise patch the LENDER's listing.
        try:
            _require_publish()
        except Exception as _e:
            return jsonify({"ok": False, "read_only": True, "error": str(_e)}), 403
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
                # Prefer Drive if the account has a folder (kept as an optional mirror);
                # otherwise serve the image publicly from the app itself. Drive is no
                # longer required to publish an image to Amazon.
                acc0 = _active_account()
                folder = (acc0 or {}).get("drive_folder_url", "")
                parent_id = _drive_folder_id_from_url(folder) if folder else ""
                if parent_id:
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
                    except Exception:
                        public_url = ""   # fall through to the public app URL
                if not public_url:
                    public_url = _public_media_url(img)
                    if not public_url:
                        return jsonify({"ok": False, "error":
                            "could not build a public URL for this image. On the server, set the "
                            "PUBLIC_BASE_URL environment variable to your app's address "
                            "(e.g. https://altascraper.onrender.com) so Amazon can fetch generated "
                            "images without Google Drive."}), 400
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

        # Rule 1 AGAIN, FOR THE BRAND ITSELF -- the same rule, the same reason.
        #
        # The sources this endpoint reads are the COMPETITOR's: the eBay
        # listing's item specifics and the competitor ASIN's SP-API record. Both
        # carry a Brand, and _from_source matches on the field name, so asking
        # it to fill "brand" returns THEIR brand. Proven by calling it directly:
        # for a Nestwell Goods squeegee it offered
        #
        #     brand = 'YL'   source = eBay
        #
        # and auto-fix applies suggestions without being asked, so a run wrote
        # another company's brand onto the owner's listing. That is the whole
        # thing this app is built not to do (CLAUDE.md Rule 1) -- and it is why
        # a Brand Name box showed "YL" on a row whose Brand column says
        # "Nestwell Goods".
        #
        # The brand is not researched. It is the owner's, it is already on the
        # row, and it is the only answer that can be right.
        _BRAND_FIELDS = {"brand", "brand_name", "manufacturer"}
        _own_brand = (str(row.get("Brand", "") or "").strip()
                      or str(cfg.get("brand_name", "") or "").strip())
        _brand_asked = [f for f in fields
                        if str(f).split(".", 1)[0].strip().lower() in _BRAND_FIELDS]
        fields = [f for f in fields
                  if str(f).split(".", 1)[0].strip().lower() not in _BRAND_FIELDS]

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

        # The brand fields, answered from the row rather than from a competitor.
        for _bf in _brand_asked:
            if _own_brand:
                suggestions.append({
                    "field": _bf, "value": _own_brand,
                    "source": "your own brand", "confidence": "high",
                    "note": "This listing's own brand, taken from the row. Never "
                            "read from the competitor or the eBay source -- their "
                            "brand is theirs.",
                })
            else:
                # Nothing to offer, and inventing one is exactly the failure.
                suggestions.append({
                    "field": _bf, "value": "", "source": "none", "confidence": "low",
                    "note": "No brand is set on this listing or on the account. "
                            "Set it in the row's Brand box or in the account's "
                            "settings -- it must be YOUR brand, and it is never "
                            "taken from the competitor.",
                })
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
            grid = _repo.read_grid(ws)
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
        _bad = _wrong_account(_asked_account())
        if _bad:
            return _bad
        _who = (str(_asked_account() or "").strip()
                or _state.get("active_account_id") or "")
        try:
            _bust_records_cache()                     # force a truly fresh read
            data = _records(_store_for(_who) or _ws(), _use_cache=False)
            for i, r in enumerate(data):
                if str(r.get("SKU", "")).strip() == sku:
                    c = _card(r)
                    c["row"] = i + 2
                    _attach_claim_flags(c, r)
                    _attach_restricted(c, r)
                    _attach_viability(c, r)
                    # Can Amazon create this at all -- barcode, exemption, or
                    # neither, and is the barcode already on another listing.
                    _attach_identifier(c, r, CONFIG_PATH, _who)
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
                _attach_claim_flags(c, r)
                _attach_restricted(c, r)
                _attach_viability(c, r)
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

    def _accounts_on_sheet(sid):
        """List of accounts whose OUTPUT sheet is spreadsheet `sid`. When more than one
        account lives in the same workbook, that workbook is SHARED and each account must
        be scoped to its own tab only."""
        out = []
        try:
            import re as _re2
            import accounts as _accs
            def _sid_of(v):
                v = str(v or "").strip()
                m = _re2.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", v)
                return m.group(1) if m else v
            for a in (_accs.load_accounts(_cfg()) or []):
                if _sid_of(a.get("output_spreadsheet_id", "")) == str(sid):
                    out.append(a)
        except Exception:
            return []
        return out

    def _other_account_gids(sid, aid):
        """Tab gids OWNED by OTHER accounts on spreadsheet `sid` (for the set_active_tab guard)."""
        out = set()
        if not aid:
            return out
        for a in _accounts_on_sheet(sid):
            if str(a.get("id", "")) == str(aid):
                continue
            g = str(a.get("output_tab_gid") or "").strip()
            if g:
                out.add(g)
        return out

    def _demo_rows(aid, found):
        """Sample listings, or None. One helper because /rows_all has several
        return paths and each of them needs the same answer to the same
        question: is this screen about to be empty with no way to fill itself?

        `found` is what the real read produced. Anything at all in it and this
        returns None -- see domain/demo_data.maybe(), and the 115 real drafts
        that an earlier version of this hid.
        """
        try:
            from domain import accounts as _acc_dd
            from domain import demo_data as _dd
            acct = _acc_dd.get_account(
                _cfg() if callable(_cfg) else (_cfg or {}), aid,
                CONFIG_PATH) if aid else None
            d = _dd.maybe(acct, "listings", has_data=bool(found),
                          workspace_id=aid)
            if not d:
                return None
            # THE SAME SHAPE THE REAL ANSWER HAS -- `rows`, a `tabs` manifest
            # and a `source` -- so the screen needs no second rendering path and
            # cannot quietly draw a sample differently from the real thing. Only
            # `demo` and `demo_reason` are added, to be shown.
            return {"ok": True, "rows": d["rows"], "shipping_group": "",
                    "product_types": _product_types(),
                    "tabs": [{"tab": "sample", "tab_gid": "",
                              "count": d["count"], "url": ""}],
                    "source": {"store": "sample", "from_database": 0,
                               "from_sheet": 0,
                               "workspace": str(aid or "_no_account")},
                    "demo": True, "demo_reason": d["demo_reason"]}
        except Exception:
            return None        # never let the sample path break the real one

    @app.route("/rows_all")
    def rows_all():
        """Like /rows, but reads EVERY listing-shaped tab in the ACTIVE workspace's
        output sheet and tags each card with the tab it lives on. Powers the multi-tab
        'All tabs' view so accounts with many output tabs (Miles) are seen in one place
        instead of one tab at a time. Read-only; never writes.

        A tab counts as a listing tab when its header row 1 has BOTH a 'SKU' and a
        'Title' column (the generated-listing shape). Non-listing tabs (input, config,
        notes) are skipped. Each card gains c['tab'] + c['tab_gid']; the response also
        returns a 'tabs' manifest (name, gid, count) so the UI can draw the tab filter."""
        try:
            # Resolve the active workspace's sheet. Mirror _ws()'s scoping guard so an
            # ACCOUNT workspace never falls back to the shared default sheet/tab.
            _aid = _state.get("active_account_id")

            # WHOSE LISTINGS WERE ASKED FOR.
            #
            # This route used to take the browser's word for nothing at all: it
            # read the active account out of stored state and answered. That
            # state is remembered between visits, so a request that arrived
            # before the browser's account switch -- which is exactly what
            # happened on every page load -- was answered with the account that
            # had been open LAST time, and those listings were painted under
            # this account's name.
            #
            # The browser now says which account it is asking about, and a
            # disagreement is refused rather than answered. Refusing is the
            # whole point: answering for the account the server happens to have
            # selected is what produced the wrong listings on screen.
            #
            # An absent parameter is NOT treated as a mismatch, so anything
            # calling this without one behaves exactly as before.
            # The rule itself lives in domain/account_scope.py -- it was written
            # out here and again in orders_routes.py, and a rule about who may
            # see whose data is the worst thing to keep two copies of (rule 12).
            _raw_asked = request.args.get("account")
            if _acctscope.is_mismatch(_raw_asked, _aid):
                return jsonify(_acctscope.refusal(_raw_asked, _aid, "listings")), 200

            # THE ACCOUNT THAT WAS ASKED FOR IS THE ACCOUNT THAT IS READ.
            #
            #     "no one account data should be shared with another"
            #     "i asked for jacks listings so jacks listings should appear,
            #      not another account"
            #
            # MEASURED, on the running app:
            #
            #     /rows_all?account=jack_uk         -> 86 rows, workspace=nestwell_goods
            #     /rows_all?account=nestwell_goods  -> 86 rows, workspace=nestwell_goods
            #
            # Both answers were Nestwell's, because this route read the workspace
            # out of _state -- the server's process-wide "currently open account"
            # -- and ignored the one the request named. The browser does its half
            # correctly: it sends ?account=, drops a reply that arrives after a
            # switch, and honours a refusal. It was the server that answered for
            # whoever happened to be open.
            #
            # NOT A REFUSAL. is_mismatch() above is deliberately always False --
            # refusing on a disagreement was tried and was worse, because the
            # stale value is the GLOBAL and the browser is the one that is right:
            # "i switched from headbanger lures recently but i am on nestwell
            # goods but still i am shown this error". Refusing punished the
            # correct request. Answering the question actually asked fixes both
            # the leak and that.
            #
            # SAFE ON THE DATABASE because a workspace IS the unit of storage
            # there -- data/store.StoreBook says it plainly, "on the database a
            # tab is a workspace". Verified before this was written:
            # ListingStore("jack_uk") holds 87 SKUs, ListingStore("nestwell_goods")
            # 86, and NOT ONE is shared between them.
            _use_aid = str(_raw_asked or "").strip() or _aid

            # WHICH STORE THE LISTINGS ARE ACTUALLY IN.
            #
            # This is the bug behind "I pressed generate an hour ago, the log
            # said it was generating, and now I cannot see the new drafts".
            #
            # The app moved its listings to the database. The generator writes
            # there, /row reads there, every other screen reads there -- but
            # this route went straight to Google Sheets and read the workbook,
            # with no database branch at all. So a run wrote 27 new listings
            # into the database and the Listings screen showed the spreadsheet,
            # which knew nothing about them. Nothing was lost and nothing
            # failed; the screen was simply looking in the other place.
            #
            # _ws() and _records() are the pair the whole app is given by
            # injection, and they already point at whichever store is in use.
            # Going through them is what makes this screen agree with the rest
            # of the app instead of having its own opinion.
            # BOTH STORES, MERGED -- and this is the correction to a change that
            # blanked a live screen.
            #
            # The first version of this branch read the database INSTEAD of the
            # spreadsheet whenever the backend was "db". That is right in
            # principle and wrong in fact: the app is mid-migration, and a
            # workspace's listings can be in either store or split across both.
            # On the server the database did not hold Nestwell Goods' history,
            # so the Listings screen went from "a lot" to "No listings in this
            # view" the moment it deployed. Nothing was deleted; the screen had
            # simply been pointed at the emptier of the two places.
            #
            # So neither store is authoritative and neither is a fallback. Both
            # are read, and the rows are merged on SKU with the database
            # winning, because that is where edits and new runs land. A row in
            # only one of them still appears. The reply says how many came from
            # each, so "where is my listing" is answerable from the screen
            # rather than by reading this file.
            db_cards, db_error, db_store = [], "", None
            try:
                from data import choice as _choice_mod
                _backend = _choice_mod.resolve(_cfg(), None)
            except Exception:
                _backend = "sheets"
            if _backend == "db":
                try:
                    # The NAMED workspace, not the open one. _ws() resolves from
                    # _state and is kept for the no-account case only.
                    db_store = _store_for(_use_aid) if _use_aid else _ws()
                    for r in _records(db_store):
                        c = _card(r)
                        # One store, so one "tab". The multi-tab manifest exists
                        # for workbooks with several listing tabs; the database
                        # has a workspace per account instead.
                        c["tab"] = getattr(db_store, "title", "listings")
                        c["tab_gid"] = ""
                        c["store"] = "database"
                        _attach_claim_flags(c, r)
                        _attach_restricted(c, r)
                        _attach_viability(c, r)
                        db_cards.append(c)
                except Exception as _dbe:
                    # A database that cannot be read must not take the sheet's
                    # rows down with it.
                    db_error = str(_dbe)[:200]

            # INDEPENDENT OF SHEETS, once that has been switched on.
            #
            # The merge above is a BRIDGE, not the destination: while the sheet
            # is still read, a row that exists only there can still surface, and
            # a deletion made in the app can be undone by the spreadsheet. When
            # read_sheets_as_well is off, the database is the whole answer and
            # Google is not contacted at all -- which is also why this returns
            # before the client is ever used.
            try:
                from data import choice as _choice_mod2
                _read_sheets = _choice_mod2.sheets_fallback(_cfg(), None)
            except Exception:
                _read_sheets = True
            if not _read_sheets:
                # AN EMPTY SCREEN THAT CAN NEVER FILL ITSELF gets samples, so a
                # reviewer can see what Listings looks like with a business in
                # it. AFTER the real read and gated on it being empty -- see the
                # note on demo_data.maybe(): gating on "no Amazon account" alone
                # put eight invented rows over Headbanger Lures' 115 real
                # drafts. Sample rows are marked all the way to the screen.
                _demo = _demo_rows(_aid, db_cards)
                if _demo:
                    return jsonify(_demo)
                return jsonify({
                    "ok": True,
                    "shipping_group": _cfg().get("merchant_shipping_group", ""),
                    "product_types": _product_types(),
                    # THE WORKSPACE ACTUALLY READ, not the one the server has
                    # open. The browser checks this field against the account it
                    # asked about; reporting _aid made that check agree with
                    # itself no matter whose rows were in the reply.
                    "source": {"store": "database", "from_database": len(db_cards),
                               "from_sheet": 0,
                               "workspace": str(_use_aid or "_no_account"),
                               "sheets_off": True},
                    "tabs": [{"tab": getattr(db_store, "title", "listings"),
                              "tab_gid": "", "count": len(db_cards), "url": ""}],
                    "rows": db_cards})

            _who = _state.get("active_view") or _aid or "This workspace"
            sid  = _state.get("active_sheet_id") or ""
            if _aid and not sid:
                # No sheet configured. Only an error if there is also nothing in
                # the database -- otherwise this is simply an account that has
                # finished migrating, and saying "nothing was read" over a
                # screenful of listings would be false.
                if db_cards:
                    return jsonify({
                        "ok": True,
                        "shipping_group": _cfg().get("merchant_shipping_group", ""),
                        "product_types": _product_types(),
                        "source": {"store": "database", "from_database": len(db_cards),
                                   "from_sheet": 0,
                                   "workspace": str(_aid or "_no_account")},
                        "tabs": [{"tab": getattr(db_store, "title", "listings"),
                                  "tab_gid": "", "count": len(db_cards), "url": ""}],
                        "rows": db_cards})
                return jsonify({"ok": False, "sheet_scope_error": True,
                    "error": (f"{_who} has no output sheet configured, so nothing was read. "
                              f"Open Account & sheets and paste this account's output Google "
                              f"Sheets link. The app will not fall back to another account's sheet.")}), 200
            if not sid:
                sid = _cfg()["google_spreadsheet_id"]          # dropshipping default
            # ACCOUNT ISOLATION: several accounts can SHARE one workbook, each owning a
            # different tab (jack_uk, selvora, sheelady... all live in one spreadsheet, which
            # ALSO holds many other tabs). A workspace must show ONLY its own account's tab --
            # NEVER another account's, and never the workbook's other loose tabs.
            #   - SHARED workbook (>1 account uses this sheet): show ONLY this account's own
            #     tab (its output_tab_gid, or the resolved active_tab by name). Multi-tab OFF.
            #   - SINGLE-ACCOUNT workbook (e.g. Miles owns its sheet): show ALL listing tabs.
            #     The multi-tab view keeps working there.
            my_gid  = str(_state.get("active_tab_gid") or "").strip()
            my_tab  = str(_state.get("active_tab") or "").strip()
            _shared = _aid and len(_accounts_on_sheet(sid)) > 1
            book = _client().open_by_key(sid)
            SKU_ALIASES = ("SKU", "Sku", "sku")
            # A card is "empty" when sku/title/asin/product_type/price are ALL blank --
            # the same rule the grid uses to hide placeholder rows (isEmptyRow in the JS).
            # Empty cards are still returned (so the 'clear empty rows' note works per tab),
            # but the tab pill count reflects only REAL listings, matching what's shown.
            def _empty_card(c):
                s = lambda x: str(x if x is not None else "").strip()
                return (not s(c.get("sku")) and not s(c.get("title")) and not s(c.get("asin"))
                        and not s(c.get("product_type")) and not s(c.get("price")))
            tabs, cards = [], []
            for ws in book.worksheets():
                # THE FREE CHECKS FIRST. Reading a tab's header row is a call to
                # Google and costs about a second; the two tests below are string
                # comparisons on a title we already have. They used to run AFTER
                # the header read, so a 15-tab workbook made 15 round trips and
                # then threw 14 of the answers away.
                #
                # Measured on jack_uk: open the workbook 4.15s, list the tabs
                # 0.37s, read 15 headers ~17s -- for a shared workbook where only
                # ONE tab was ever going to be used. That was most of the twenty
                # seconds the Listings screen spent before it could draw.
                try:
                    from domain.backup import BACKUP_TAB_PREFIX as _BAK0
                except Exception:
                    _BAK0 = "backup_"
                if str(ws.title or "").startswith(_BAK0):
                    continue
                # On a SHARED workbook only this account's own tab is ever
                # included, so there is no reason to look at any other.
                if _shared:
                    _gid0 = str(ws.id)
                    _mine0 = (_gid0 == my_gid) if my_gid else (ws.title == my_tab)
                    if not _mine0:
                        continue
                try:
                    header = _repo.read_headers(ws)
                except Exception:
                    continue
                # A BACKUP TAB IS NOT A SOURCE.
                #
                # The daily backup writes each workspace's listings into its own
                # backup_ tab in the same workbook. Those tabs are listing-shaped
                # by definition, so without this they would be read back as live
                # rows -- a listing deleted in the app would reappear at the next
                # backup, which is the sync problem being recreated by the very
                # thing meant to end it. The prefix is defined in domain/backup.py
                # and imported, so the two halves cannot drift apart.
                try:
                    from domain.backup import BACKUP_TAB_PREFIX as _BAK
                except Exception:
                    _BAK = "backup_"
                if str(ws.title or "").startswith(_BAK):
                    continue
                if not (any(a in header for a in SKU_ALIASES) and "Title" in header):
                    continue                                    # not a listing tab -> skip
                # On a SHARED workbook, include ONLY this account's own tab.
                if _shared:
                    _gid = str(ws.id)
                    _mine = (_gid == my_gid) if my_gid else (ws.title == my_tab)
                    if not _mine:
                        continue                                # another account's / loose tab -> hide
                recs = _records(ws)
                n = 0
                for r in recs:
                    c = _card(r)
                    c["tab"]     = ws.title
                    c["tab_gid"] = str(ws.id)
                    _attach_claim_flags(c, r)
                    _attach_restricted(c, r)
                    _attach_viability(c, r)
                    c["store"] = "sheet"
                    cards.append(c)
                    if not _empty_card(c):
                        n += 1                                  # count real listings only
                _url = ""
                try: _url = ws.url
                except Exception: _url = ""
                tabs.append({"tab": ws.title, "tab_gid": str(ws.id), "count": n, "url": _url})

            # MERGE. The database wins a clash, because that is where edits and
            # new runs land -- but a SKU that exists only in the spreadsheet is
            # still shown, which is the whole point of doing this rather than
            # choosing one store.
            # The sheet's own answer, kept as it was. The merge below rebinds
            # `cards` and `tabs` to the merged result, and the auto-import
            # further down has to redo that merge against fresh database rows --
            # which it can only do from the un-merged sheet lists.
            sheet_cards, sheet_tabs = cards, list(tabs)
            sheet_only = cards
            if db_cards:
                seen = {str(c.get("sku") or "").strip().upper()
                        for c in db_cards if str(c.get("sku") or "").strip()}
                sheet_only = [c for c in cards
                              if str(c.get("sku") or "").strip().upper() not in seen
                              or not str(c.get("sku") or "").strip()]
                # The database rows first: they are the current ones.
                cards = db_cards + sheet_only
                tabs = ([{"tab": getattr(db_store, "title", "listings"),
                          "tab_gid": "", "count": len(db_cards), "url": ""}] + tabs)

            # ANYTHING STILL ONLY IN THE SPREADSHEET IS BROUGHT IN, HERE, NOW.
            #
            #     "Bring in whatever is left automatically right now, then
            #      remove this banner entirely. It should never appear again.
            #      ... We are fully on the database now."
            #
            # This screen used to draw a notice saying "N of these listings are
            # still only in the Google Sheet" with a button to check what would
            # be brought in. The notice was accurate and useless: it stated a
            # condition only the app could fix, in a place where the only
            # sensible answer was yes, and until somebody pressed it those rows
            # kept appearing and disappearing as the app changed where it read
            # from.
            #
            # So the read does the move. The rows are still MERGED and returned
            # below either way -- if the import fails, or is skipped because it
            # has already been attempted this process, the screen shows exactly
            # what it showed before, just without a notice about it. Nothing on
            # this path can lose a listing: the spreadsheet is only read (see
            # domain/sheet_migration.py) and the merge still shows sheet-only
            # rows whether or not the copy worked.
            if sheet_only and _use_aid:
                try:
                    from domain import sheet_migration as _mig
                    from domain import accounts as _acc_mig
                    _acct = _acc_mig.get_account(_cfg(), _use_aid, CONFIG_PATH)
                    _res = (_mig.auto_import_once(_acct, client=_client(),
                                                  config_path=CONFIG_PATH)
                            if _acct else None)
                    # Re-read the database so THIS reply already reflects the
                    # move, rather than showing the sheet copies once more and
                    # only settling on the next load.
                    _dbs = db_store or _store_for(_use_aid)
                    if _res and _res.get("ok") and _res.get("imported") and _dbs:
                        # PAST THE READ CACHE, or this re-read returns the rows
                        # from BEFORE the import. _records holds a 12-second
                        # cache to survive a refresh-plus-sync burst, and the
                        # database was read a moment ago in this same request --
                        # so the cached copy is guaranteed to be the stale one.
                        _bust_records_cache()
                        _fresh = []
                        for r in _records(_dbs, _use_cache=False):
                            c = _card(r)
                            c["tab"] = getattr(_dbs, "title", "listings")
                            c["tab_gid"] = ""
                            c["store"] = "database"
                            _attach_claim_flags(c, r)
                            _attach_restricted(c, r)
                            _attach_viability(c, r)
                            _fresh.append(c)
                        if _fresh:
                            db_store = _dbs
                            db_cards = _fresh
                            seen = {str(c.get("sku") or "").strip().upper()
                                    for c in db_cards
                                    if str(c.get("sku") or "").strip()}
                            sheet_only = [c for c in sheet_cards
                                          if str(c.get("sku") or "").strip().upper() not in seen
                                          or not str(c.get("sku") or "").strip()]
                            cards = db_cards + sheet_only
                            tabs = ([{"tab": getattr(_dbs, "title", "listings"),
                                      "tab_gid": "", "count": len(db_cards),
                                      "url": ""}] + sheet_tabs)
                except Exception:
                    # An import that cannot run is not a reason to fail the read.
                    pass

            src = {"sheet_id": sid, "tab_count": len(tabs),
                   "from_database": len(db_cards), "from_sheet": len(sheet_only),
                   "store": ("both" if (db_cards and sheet_only)
                             else ("database" if db_cards else "sheet"))}
            if db_error:
                src["database_error"] = db_error
            try: src["url"] = book.url
            except Exception: pass
            return jsonify({"ok": True,
                            "shipping_group": _cfg().get("merchant_shipping_group", ""),
                            "product_types": _product_types(),
                            "source": src, "tabs": tabs, "rows": cards})
        except Exception as e:
            # THE SHEET FAILED. If the database has rows, show them rather than
            # an error page: an unreachable spreadsheet is not a reason to hide
            # listings this app is holding perfectly well.
            try:
                if db_cards:
                    return jsonify({
                        "ok": True,
                        "shipping_group": _cfg().get("merchant_shipping_group", ""),
                        "product_types": _product_types(),
                        "source": {"store": "database", "from_database": len(db_cards),
                                   "from_sheet": 0, "sheet_error": str(e)[:200]},
                        "tabs": [{"tab": getattr(db_store, "title", "listings"),
                                  "tab_gid": "", "count": len(db_cards), "url": ""}],
                        "rows": db_cards})
            except Exception:
                pass
            _scope = type(e).__name__ == "SheetScopeError"
            return (jsonify({"ok": False, "error": str(e), "sheet_scope_error": _scope}),
                    200 if _scope else 500)

    @app.route("/view/set_active_tab", methods=["POST"])
    def set_active_tab():
        """Point the workspace's ACTIVE tab at another tab in the SAME output sheet, so
        the edit / approve / push routes (which all target the active tab via _ws())
        write to the tab the user is actually viewing in the multi-tab view. Only accepts
        a tab that exists in the active sheet; it NEVER changes the sheet itself and only
        mutates in-memory state (resets on account switch). This is what stops a cross-tab
        duplicate SKU from being edited on the wrong tab."""
        b   = request.get_json(force=True) or {}
        gid = str(b.get("gid", "")).strip()
        tab = str(b.get("tab", "")).strip()
        if not gid and not tab:
            return jsonify({"ok": False, "error": "no tab given"}), 400
        try:
            sid  = _state.get("active_sheet_id") or _cfg()["google_spreadsheet_id"]
            book = _client().open_by_key(sid)
            ws = None
            if gid.isdigit():
                try: ws = book.get_worksheet_by_id(int(gid))
                except Exception: ws = None
            if ws is None and tab:
                try: ws = book.worksheet(tab)
                except Exception: ws = None
            if ws is None:
                return jsonify({"ok": False, "error": "tab not found in this sheet"}), 404
            # ISOLATION: never let a workspace point its active tab at a tab OWNED by
            # another account (shared workbook). Belt-and-suspenders: the UI already only
            # offers this account's own tabs.
            if str(ws.id) in _other_account_gids(sid, _state.get("active_account_id")):
                return jsonify({"ok": False, "error": "that tab belongs to a different account"}), 403
            _state["active_tab"]     = ws.title
            _state["active_tab_gid"] = str(ws.id)
            return jsonify({"ok": True, "tab": ws.title, "tab_gid": str(ws.id)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:200]}), 500

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
            ws    = _ws()
            found = _repo.locate(ws, sku, sku_headers=(SKU_HEADER,))
            if not found.ok:
                return jsonify({"ok": False, "error": found.error}), 404
            if not _repo.set_field(ws, found.row, STATUS_HEADER, status,
                                   headers=found.headers):
                return jsonify({"ok": False, "error": "no Status column"}), 400
            _bust_records_cache()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    def _rescan_compute():
        """Re-judge every eligible row from the sheet. Pure read -- writes nothing."""
        import json as _json
        import os as _os
        from listing import flags as _flags
        from amazon_listing_generator import load_ip_rules as _lir

        _base = _os.path.dirname(_os.path.abspath(CONFIG_PATH))
        try:
            with open(_os.path.join(_base, "compliance_rules.json"), encoding="utf-8") as fh:
                _crules = _json.load(fh)
        except Exception:
            _crules = {}
        _iprules = _lir()

        ws   = _ws()
        rows = _records(ws, _use_cache=False)
        out  = []
        for r in rows:
            res = _flags.rescan_row(r, _iprules, _crules)
            # Anything the flags CHANGED, whatever the row's status. The Status
            # column protects itself -- decide_status returns a status it does
            # not own untouched, so it never lands in `changed` for a LIVE or
            # APPROVED row and only Notes / Compliance Risk / IP Risk are
            # written. Filtering the whole ROW out here instead is what left 37
            # already-selling listings wearing a badge from a rule that no
            # longer makes that finding.
            if res["changed"]:
                out.append(res)
        return ws, rows, out

    @app.route("/rescan/preview")
    def rescan_preview():
        """What WOULD change if the flags were re-judged. Writes nothing.

        Exists because a wrong flag rule leaves every already-generated row
        carrying the wrong flag, and regenerating a row to clear it costs ~50s
        and Claude credits for copy that was never the problem.
        """
        try:
            _, rows, changes = _rescan_compute()
            return jsonify({
                "ok": True, "scanned": len(rows), "changes": len(changes),
                "rows": [{"sku": c["sku"], "title": c["title"],
                          "old_status": c["old"]["status"], "new_status": c["new"]["status"],
                          "old_ip": c["old"]["ip_risk"], "new_ip": c["new"]["ip_risk"],
                          "old_comp": c["old"]["compliance_risk"],
                          "new_comp": c["new"]["compliance_risk"],
                          "new_notes": c["new"]["notes"][:300],
                          # So the confirmation can say "badge corrected, status
                          # left alone" rather than leaving somebody to wonder
                          # why a LIVE row still reads LIVE.
                          "status_owned": c.get("status_owned", True),
                          "changed": sorted(c["changed"])}
                         for c in changes[:500]],
            })
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}), 500

    @app.route("/rescan/apply", methods=["POST"])
    def rescan_apply():
        """Write the re-judged flags back. ONLY the four flag columns.

        Copy, prices, SKUs and attributes are never touched.

        The STATUS of an APPROVED, LIVE, ERROR or API_* row is never rewritten --
        that is the operator's decision or Amazon's own state. Its Notes,
        Compliance Risk and IP Risk are, because those three are this app's own
        verdict about its own copy, and a listing that is live on Amazon has as
        much right to a correct badge as one that is not."""
        try:
            ws, _rows, changes = _rescan_compute()
            if not changes:
                return jsonify({"ok": True, "updated": 0, "note": "nothing to change"})

            # Bulk: one pass building SKU -> row for MANY skus, so it shares the
            # repo's rules (read_headers / find_col / norm) rather than calling
            # locate() per row, which would be one column read each.
            headers = _repo.read_headers(ws)
            col = {h: headers.index(h) + 1 for h in
                   ("SKU", "Status", "Notes", "Compliance Risk", "IP Risk")
                   if h in headers}
            if "SKU" not in col:
                return jsonify({"ok": False, "error": "SKU column not found"}), 500

            # Map SKU -> sheet row number once, rather than searching per row.
            # Both sides go through repo.norm: the sheet value used to be stripped
            # while the lookup key below was not, so a SKU carrying a stray space
            # silently matched nothing and its row was skipped without a word.
            sku_rows = {}
            for i, v in enumerate(_repo.column_values(ws, col["SKU"]), start=1):
                s = _repo.norm(v)
                if s and s not in sku_rows:
                    sku_rows[s] = i

            payload, updated = [], 0
            for ch in changes:
                rn = sku_rows.get(_repo.norm(ch["sku"]))
                if not rn:
                    continue
                for key, header in (("status", "Status"), ("notes", "Notes"),
                                    ("compliance_risk", "Compliance Risk"),
                                    ("ip_risk", "IP Risk")):
                    if key in ch["changed"] and header in col:
                        payload.append({"range": _repo.a1(rn, col[header]),
                                        "values": [[ch["new"][key]]]})
                updated += 1

            # One batched write -- 87 rows x 4 columns as single cell updates
            # would be ~350 API calls and would hit Google's per-minute quota.
            # The 100-cell chunking lives in the repo so every bulk writer gets
            # it, not just the one that remembered to write the loop.
            _repo.batch_write(ws, payload)
            _bust_records_cache()
            return jsonify({"ok": True, "updated": updated, "cells": len(payload)})
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}), 500

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
                    # THE STORED COPY TOO. Schemas are now kept on disk between
                    # restarts, so clearing only the in-memory one would leave
                    # "Reload Amazon values now" returning the very copy the
                    # person pressed it because they did not believe -- a button
                    # that looks like it worked and changed nothing.
                    try:
                        from domain import schema_cache as _sc
                        _sc.forget(CONFIG_PATH, pt, _mkt)
                    except Exception:
                        pass
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
        # A WRITE. Refusing costs a retry; getting it wrong edits another
        # account's listing.
        _bad = _wrong_account(b.get("account"))
        if _bad:
            return _bad
        try:
            # THE NAMED WORKSPACE, NOT THE OPEN ONE.
            #
            # This edited whichever workspace the server had selected, and found
            # the row by SKU inside it. The note on _wrong_account argued that
            # was a latent hazard rather than a live one, because "282 rows
            # across five accounts, 282 distinct SKUs, none shared between two
            # accounts" -- a SKU miss would 404 rather than hit the wrong row.
            #
            # THAT MEASUREMENT NO LONGER HOLDS, and the owner is the one who
            # said so: "i am also doing mee too listings on both accounts ...
            # maybe i have set the same sku for those asins in both accounts".
            # A SKU deliberately shared between two accounts turns the 404 into
            # an edit of the other company's listing. Same fix as /rows_all:
            # read and write the workspace that was asked for.
            ws    = _store_for(b.get("account")) or _ws()
            found = _repo.locate(ws, sku, sku_headers=(SKU_HEADER,))
            if not found.ok:
                return jsonify({"ok": False, "error": found.error}), 404
            trow, headers = found.row, found.headers
            if target == "col":
                if key not in _EDITABLE_COLS or key not in headers:
                    return jsonify({"ok": False, "error": "column not editable"}), 400
                _repo.set_field(ws, trow, key, value, headers=headers)
            elif target == "attr":
                if "Attributes JSON" not in headers:
                    return jsonify({"ok": False, "error": "no attributes column"}), 400
                acol = headers.index("Attributes JSON") + 1
                cur  = _repo.cell_value(ws, trow, acol) or "{}"
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
                _repo.set_field(ws, trow, "Attributes JSON",
                                json.dumps(obj, ensure_ascii=False), headers=headers)
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
        # A DELETE, and it can fall back to a row NUMBER below -- which is not
        # even account-specific. Of the four this is the one where answering for
        # the wrong workspace destroys something.
        _bad = _wrong_account(b.get("account"))
        if _bad:
            return _bad
        try:
            # THE NAMED WORKSPACE, NOT THE OPEN ONE -- and this one DELETES.
            # See the note in /edit: the "SKUs are unique across accounts"
            # measurement that made this safe has been withdrawn by the owner,
            # who deliberately reuses a SKU across accounts for me-too listings.
            ws     = _store_for(b.get("account")) or _ws()
            target = None
            if sku:                                   # prefer matching by SKU (stable)
                # A miss stays silent here on purpose: this route falls back to the
                # row number below, which is how a blank row with no SKU is deleted.
                found = _repo.locate(ws, sku, sku_headers=(SKU_HEADER,))
                if found.ok:
                    target = found.row
            if target is None and row:                # fall back to row number (blank rows)
                try:
                    target = int(row)
                except Exception:
                    target = None
            if not target or target < 2:
                return jsonify({"ok": False, "error": "row not found"}), 404
            _repo.delete_row(ws, target)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/clear_empty", methods=["POST"])
    def clear_empty():
        """Delete every data row whose SKU, Title, Competitor ASIN and Product Type are all blank."""
        try:
            ws   = _ws()
            vals = _repo.read_grid(ws)
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
                _repo.delete_row(ws, rownum)
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

        # WHICH ACCOUNT THIS RUN IS FOR -- named by the page, not by a global.
        #
        # _state["active_account_id"] is ONE variable for the whole process. It
        # is not per browser, not per tab, and it is restored from disk on
        # restart, so it drifts from what any given screen is showing. Pressing
        # Generate while looking at Jack Reacherd ran the generator with
        # Nestwell Goods' credentials against Nestwell's sheet, and every line of
        # the log said Nestwell while the screen still said Jack.
        #
        # The page now sends the account it is displaying. Where the two differ
        # the RUN IS REFUSED -- not silently switched to either one. A generate
        # writes listings and a submit reaches Amazon; if there is any doubt
        # about whose account that is, the only safe answer is to do nothing and
        # say so. Reloading the page settles it.
        # The same question the Sales screen asks, answered in the same place --
        # domain/request_account.py. A read there resolves TO the page's account;
        # a write here refuses on a mismatch. Two opposite policies, one module,
        # so neither can quietly drift from the other.
        import domain.request_account as _req_acct
        _mismatch = _req_acct.mismatch_for_write(request, _state, what="run")
        if _mismatch:
            return Response("data: [error] %s\n\nevent: end\ndata: end\n\n"
                            % _mismatch.replace("\n", " "),
                            mimetype="text/event-stream")

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

        # ============ EVERYTHING ABOUT WHO THIS RUN IS FOR, RESOLVED HERE ======
        #
        # THE BUG THIS EXISTS TO KILL. _state is not a plain dict: it keeps a
        # PERSONAL value per signed-in user and falls back to a SHARED,
        # process-wide one whenever there is no request to attribute the read to
        # (domain/workspace_state.py -- _mine() returns None, and the lookup goes
        # to the shared bag).
        #
        # The streaming generator below runs OUTSIDE the request context, by
        # design -- that is why request.args is read up here. But _state and
        # _active_account() were still being read down there, so they did not
        # return the signed-in user's account at all. They returned whatever the
        # SHARED value happened to be, which any background worker or any other
        # session had been free to overwrite.
        #
        # Result: a run started from Jack Reacherd executed as Nestwell Goods --
        # Nestwell's credentials, Nestwell's sheet, Nestwell's workspace -- while
        # the screen said Jack Reacherd throughout, twice, on the live app.
        #
        # An earlier attempt compared the browser's account with _state INSIDE
        # the request, where both correctly said jack_uk, found no mismatch, and
        # let the run proceed to read the shared value later anyway. Comparing
        # the right things in the wrong place proves nothing.
        #
        # So the account, the marketplace and the sheet are all captured NOW, in
        # the request, where the session exists, and the generator is given the
        # values. Nothing inside stream() consults _state again.
        _scope_acc = None
        try:
            _scope_acc = _active_account()
        except Exception:
            _scope_acc = None
        _scope_acct_id = str((_scope_acc or {}).get("id") or "") or _state_account
        _scope_sheet = _state.get("active_sheet_id")
        _scope_tab = _state.get("active_tab")
        _scope_mkt = str(_state.get("active_marketplace") or "")
        _scope_view = _state.get("active_view") or ""

        # THE MISMATCH CHECK THAT USED TO BE HERE HAS GONE, because it is done
        # above by _req_acct.mismatch_for_write() -- the one place that decides
        # whether a write may proceed for the account the page is showing.
        #
        # What was left behind was the OLD copy of that check, still reading a
        # variable the refactor had removed. It was not dead code that merely
        # looked untidy: it raised
        #
        #     NameError: name '_req_account' is not defined
        #
        # on every single run, so /run/generate answered 500 before it did
        # anything. In the browser that is an EventSource that fails to open,
        # and EventSource reports nothing to the page -- so Generate showed an
        # empty log and no error at all, for every account and every item.
        # Found by pressing Generate on a real listing.

        def stream():
            # Keyed on THIS account and THESE SKUs, not on one flag for the whole
            # app: two people in two workspaces are genuinely independent, and a
            # run should only wait for something it would actually collide with.
            _run_acct = _scope_acct_id
            _run_sku = str(_req_skus or "") if mode == "regen" else ""
            if not _acquire_run_lock(_run_acct, _run_sku):
                _why = (_running.get("busy_reason")
                        or "a run is already in progress -- wait for it to finish")
                yield "data: [busy] %s\n\n" % _why
                yield "event: end\ndata: end\n\n"
                return
            try:
                # ---- REPLACED BY /input/upload (CSV/Excel) ------------------
                #
                # AN EMPTY QUEUE IS NOW JUST AN EMPTY QUEUE. Generate used to
                # read the account's Google input sheet by itself whenever the
                # queue was empty. Kept, commented, rather than deleted, so it
                # can be restored by removing the comment markers.
                #
                # It was the right fix for the problem it had: the queue had
                # just moved into the database, Import was a different button on
                # a different part of the screen, and Generate reported "No
                # products found in input sheet" over a sheet holding 84
                # products. Taking the step for the user beat making them
                # remember it.
                #
                # It is the wrong fix once the sheet is not an input at all. The
                # queue is filled by the "Add a product" form or by dropping a
                # CSV/Excel file on it, and a hidden read of a spreadsheet
                # behind those would be the one remaining way for a Google sheet
                # to put products into a run nobody asked it to -- invisible,
                # because the button that used to explain it is gone too.
                #
                # So an empty queue now says it is empty, and the person adds
                # products by the two ways there are.
                #
                # if mode in ("generate", "retry"):
                #     try:
                #         from data import choice as _choice
                #         from data import input_import as _ii
                #         if _choice.resolve(_cfg(), CONFIG_PATH) == "db":
                #             _wsid = _scope_acct_id or "_no_account"
                #             if not _ii.summary(CONFIG_PATH, _wsid).get("count"):
                #                 yield ("data: [input] the queue is empty — "
                #                        "reading this account's input sheet…\n\n")
                #                 _a, _u, _t, _err = _ii.import_for_workspace(
                #                     CONFIG_PATH, _wsid, _scope_acc, _cfg(), _client)
                #                 if _err:
                #                     yield "data: [input] %s\n\n" % str(_err)[:300]
                #                 else:
                #                     yield ("data: [input] imported %d product(s) "
                #                            "from the sheet (%d new)\n\n" % (_t, _a))
                #     except Exception as _e:
                #         # Never fatal: a run that could not pre-import still has
                #         # whatever is already queued, and the generator says so.
                #         yield "data: [input] could not import: %s\n\n" % str(_e)[:200]

                # THE RUN'S PRODUCTS, OUT OF THE LISTINGS STORE.
                #
                # Every row with status=QUEUED, written to a temp JSON file and
                # handed over as --input-json. The generator is a subprocess, so
                # this mirrors how the sheet was passed -- a location to read --
                # rather than restructuring its input format (Rule 10).
                #
                # Only for generate and retry. A preview or a submit works on
                # rows that already exist and has no input to read.
                _queued_file = ""
                if mode in ("generate", "retry"):
                    try:
                        from listing import queued_input as _qin
                        _wsid = _scope_acct_id or "_no_account"
                        _prods = _qin.products_for(CONFIG_PATH, _wsid)
                        if _prods:
                            _queued_file = _qin.write_temp_input(_prods)
                            yield ("data: [input] %d product(s) queued for this "
                                   "run\n\n" % len(_prods))
                        else:
                            yield ("data: [input] nothing is queued — upload a "
                                   "file or add a product on this screen\n\n")
                    except Exception as _qe:
                        yield ("data: [input] could not read the queue: %s\n\n"
                               % str(_qe)[:200])

                # -u = unbuffered child stdout so progress streams live
                extra = ([] if mode == "generate"
                         else ["api", "submit"] if mode == "api_submit"
                         else ["api", "verify"] if mode == "api_verify"
                         else [mode])
                # REGEN: re-run the generator scoped to a specific set of SKUs and the
                # active sheet/tab/marketplace. Needs generator support for --skus.
                if mode == "regen":
                    skus = _req_skus
                    # Captured in the request, not read here: see the block above.
                    _sid = _scope_sheet
                    _tab = _scope_tab
                    _mkt = _scope_mkt
                    extra = ["regen"]
                    if skus: extra += ["--skus", skus]
                    if _sid: extra += ["--sheet", _sid]
                    if _tab: extra += ["--tab", _tab]
                    if _mkt: extra += ["--marketplace", _mkt]
                # SCOPE TO THE ACTIVE ACCOUNT/WORKSPACE for ALL modes (including
                # generate) so listings are created on the CORRECT account's sheet --
                # not the default dropshipping sheet. Account sheet/tab take priority;
                # brand-view scoping (below) refines marketplace for api/submit.
                # Captured in the request context above. Calling
                # _active_account() from in here read the SHARED account, not
                # this user's -- which is exactly how a Jack Reacherd run
                # executed as Nestwell Goods.
                _acc = _scope_acc
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
                # NO ACTIVE ACCOUNT. This branch used to add the Dropshipping
                # workspace's own sheet overrides. That workspace has been
                # removed -- it described itself as "eBay -> Amazon arbitrage",
                # which CLAUDE.md rule 1 says this app does not do -- and no
                # dropshipping_* key was ever present in config.json, so this
                # block never added an argument in any real run. Nothing is
                # passed now and the generator uses its config.json defaults,
                # which is exactly what happened before.
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
                    # All captured in the request context above. Read here they
                    # would come from the SHARED bag -- another user's sheet and
                    # another user's brand view, on a path that submits to
                    # Amazon.
                    _sid = _scope_sheet
                    _tab = _scope_tab
                    _mkt = ""
                    # resolve marketplace from the active brand profile, if any
                    _vk = _scope_view
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
                # Added last, so nothing above can drop it. WITHOUT this file the
                # generator falls back to read_input_sheet -- the old Google
                # path -- and would quietly generate a different set of products
                # from the ones queued on screen. This argument is what decides
                # where a run's input comes from.
                if _queued_file:
                    extra += ["--input-json", _queued_file]
                args = [sys.executable, "-u", SCRIPT] + extra
                yield f"data: [start] {' '.join(args)}\n\n"
                p = spawn(args, stdin=subprocess.PIPE)
                _running["proc"] = p
                # ATTACH THE PROCESS TO ITS SLOT. Without this Stop finds the
                # slot, sees no process on it, removes the slot and terminates
                # nothing -- so Stop reported success while the generator kept
                # running and kept spending. The slot has always had somewhere
                # to put this; nobody ever put it there.
                try:
                    from domain.run_slots import SLOTS as _SLOTS_ATTACH
                    _SLOTS_ATTACH.attach(_running.get("key"), p)
                except Exception:
                    pass
                try:
                    # generation asks once for a brand; feed the configured one (Enter = auto)
                    if mode == "generate":
                        p.stdin.write((_cfg().get("brand_name", "") or "") + "\n")
                    p.stdin.flush()
                    p.stdin.close()
                except Exception:
                    pass
                # pump_lines drains the child on its own thread, so a slow browser
                # can never jam the pipe and freeze the run mid-print. See
                # routes/stream_pump.py for the full explanation.
                for line in pump_lines(p):
                    clean = _ANSI.sub("", line.rstrip("\n"))
                    if clean.strip():
                        yield f"data: {clean}\n\n"
                p.wait()

                # WORK OUT THE WARNINGS, now the rows exist.
                #
                # Over the whole workspace, not just what this run touched: five
                # of the checks are about how rows relate to EACH OTHER (a
                # duplicate barcode is not a property of one row), and
                # generating one listing can create a clash on an older one that
                # would otherwise never be told about it.
                #
                # Never fatal. A run that produced listings has succeeded even if
                # the warnings could not be worked out afterwards.
                if mode in ("generate", "retry"):
                    try:
                        from listing import warnings as _warn
                        _n, _f = _warn.recompute_workspace(
                            CONFIG_PATH, _scope_acct_id or "_no_account")
                        yield ("data: [warnings] checked %d listing(s) — %d "
                               "carry a warning\n\n" % (_n, _f))
                    except Exception as _we:
                        yield ("data: [warnings] could not work them out: %s\n\n"
                               % str(_we)[:200])
                    try:
                        if _queued_file:
                            import os as _os
                            _os.remove(_queued_file)   # it has served its purpose
                    except Exception:
                        pass

                yield f"data: [done] finished (exit code {p.returncode})\n\n"
                yield "event: end\ndata: end\n\n"
            finally:
                with _run_lock:
                    _running["proc"] = None
                    _running["on"] = False

        return Response(stream(), mimetype="text/event-stream")

    @app.route("/run/plan")
    def run_plan():
        """What a Generate would DO, before it does it.

            "check and let me know if the current workflow of listing generation
             works while preventing the already created listing copies to be
             created again"

        Until now the only way to find out what a run would skip was to press
        Generate and read the log as it scrolled -- by which point the money is
        being spent. This answers the question first.

        It calls the generator's OWN duplicate rule (domain/generate_plan reads
        load_existing_skus_and_asins and applies process_row's condition), so it
        cannot disagree with the run it is describing. It spends nothing: no AI
        call, no Amazon call, no write.
        """
        wsid = (request.args.get("account_id") or request.args.get("id") or "").strip()
        if not wsid:
            try:
                acc = _active_account() or {}
            except Exception:
                acc = {}
            wsid = str(acc.get("id") or _state.get("active_account_id") or "")
        if not wsid:
            return jsonify({"ok": False, "error": "No account selected."}), 400
        try:
            from domain import generate_plan as _gp
            out = _gp.for_workspace(CONFIG_PATH, wsid, _cfg() or {})
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "%s: %s" % (type(e).__name__, str(e)[:200])}), 500
        out["ok"] = True
        return jsonify(out)

    @app.route("/run/health")
    def run_health():
        """The honest state of the run -- does NOT depend on the log stream.

        The log panel travels down the same pipe that has twice jammed and frozen
        a run, so it cannot be trusted to report its own health. This reads the
        generator's heartbeat file and asks the OS whether the process is alive.
        A jammed pipe can fake neither.
        """
        # SCOPED TO THE ACCOUNT ASKING.
        #
        # _running is ONE flag for the whole process and the heartbeat is ONE
        # file, so this reported "RUNNING" to every account whenever anything
        # anywhere was running -- the generation bar appeared in accounts that
        # had started nothing, describing somebody else's work. Accounts are
        # independent; their progress bars have to be too.
        #
        # domain/run_slots.py already knows which account each run belongs to,
        # so the slots decide, and the heartbeat only refines the state of a run
        # this account actually owns.
        from domain.run_slots import SLOTS as _SLOTS
        from domain import job_owner as _jo
        _who = ""
        try:
            _who = _jo.current()
        except Exception:
            _who = ""
        _acct = str(_state.get("active_account_id", "") or "")
        _all = _SLOTS.active()
        mine = [s for s in _all
                if str(s.get("account") or "") == _acct
                and (not _who or not s.get("owner") or str(s.get("owner")) == str(_who))]

        if not mine:
            # Nothing of THIS account's is running. Say idle, and say nothing
            # about anyone else's -- a bar that reports another workspace's run
            # is worse than no bar, because it invites you to press Stop on it.
            return jsonify({"state": "IDLE", "detail": "", "total": 0,
                            "stream_attached": False, "mine": 0,
                            "elsewhere": len(_all) - len(mine)})

        proc = _running.get("proc")
        alive = None
        if proc is not None:
            alive = (proc.poll() is None)   # the real handle beats a PID lookup
        info = run_status.classify(app_dir=os.path.dirname(os.path.abspath(CONFIG_PATH)),
                                   proc_alive=alive)
        info["stream_attached"] = bool(_running.get("on"))
        info["mine"] = len(mine)
        info["elsewhere"] = len(_all) - len(mine)
        # Which of this account's runs it is, so the bar names the SKU rather
        # than describing "a run" in the abstract.
        info["skus"] = [s.get("sku") for s in mine if s.get("sku")]
        return jsonify(info)

    @app.route("/run/stack")
    def run_stack():
        """Why is it stuck? Dump the frozen process's actual Python stack.

        This is exactly how both freezes were diagnosed. Read-only: py-spy
        samples the process from outside and never modifies or resumes it.
        """
        info = run_status.classify(app_dir=os.path.dirname(os.path.abspath(CONFIG_PATH)))
        pid = info.get("pid")
        proc = _running.get("proc")
        if proc is not None and proc.poll() is None:
            pid = proc.pid
        if not pid:
            return jsonify({"ok": False, "error": "no run process to inspect"})

        exe = os.path.join(os.path.dirname(sys.executable), "Scripts", "py-spy.exe")
        if not os.path.exists(exe):
            exe = "py-spy"
        try:
            out = subprocess.run([exe, "dump", "--pid", str(pid)],
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=60)
            text = (out.stdout or "") + (out.stderr or "")
            if not text.strip():
                text = "(py-spy returned nothing)"
            return jsonify({"ok": out.returncode == 0, "pid": pid, "dump": text})
        except FileNotFoundError:
            return jsonify({"ok": False, "pid": pid,
                            "error": "py-spy is not installed. Install it with:  "
                                     "python -m pip install py-spy"})
        except Exception as e:
            return jsonify({"ok": False, "pid": pid,
                            "error": f"{type(e).__name__}: {str(e)[:200]}"})

