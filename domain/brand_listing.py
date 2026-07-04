"""
brand_listing.py  --  BRAND-MODE generation engine for amazon_listing_generator.py

This is the inverse of the arbitrage path. Instead of scraping a competitor ASIN
and de-branding it, it takes a brand's OWN product (from a Shopify export via
shopify_import.py) and writes an optimised Amazon listing that:

  * KEEPS the brand name (and may lead the title with it),
  * uses the brand's OWN identifiers verbatim (MPN / model / SKU / GTIN) or blank,
  * gates CLAIMS to evidence (see CLAIMS GATE below),
  * runs with or WITHOUT a competitor ASIN (optional enrichment only),
  * outputs English by default, tone-aware of the brand's source language,
  * emits per-field PROVENANCE so the dashboard "i" button can show data sources,
  * converges into the EXISTING build_sheet_row + compliance + IP + export paths.

It deliberately reuses, from the host script (passed in as `host`):
  build_sheet_row, check_compliance, check_ip_violations, sheet_write_row,
  get_product_type_schema, _build_message_content, SYSTEM_PROMPT helpers,
  detect_route / _norm_pt (routing), and the JSON-repair parse.

CLAIMS GATE (final spec)
------------------------
  TIER 1  generic category-standard benefits  -> ALLOWED with no evidence
          (true of ~all products in the category; non-quantified).  tag: INFERRED
  TIER 2  specific / performance claims        -> ONLY if backed by the export
          data or a claim doc; otherwise DROP the claim (do not soften).
          tag: EXPORT (with column) or DOC (with filename)
  TIER 3  regulatory / health claims           -> still pass through the host's
          compliance_rules.json regardless.

PROVENANCE
----------
  Deterministic fields (sku, barcode/GTIN, model/MPN, price, brand, marketplace,
  country_of_origin) are tagged by CODE here -- guaranteed accurate.
  Soft fields (material/colour read from image, a claim tied to a doc, inferred
  benefits) are tagged by CLAUDE in its JSON and merged in. The merged map marks
  each field verified=True (code) or verified=False (model-reported).
"""

import json
import os
import re
from datetime import datetime

# Mirrors dashboard.py's CONFIG_PATH convention so media/recipes read and write
# the SAME directory as the rest of the app (the persistent disk in production,
# e.g. /data when CONFIG_PATH=/data/config.json -- not the ephemeral /app).
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")


def _app_dir() -> str:
    return os.path.dirname(os.path.abspath(CONFIG_PATH))


# =============================================================================
# IDENTITY EXTRACTION  (use the brand's own info; blank if absent; never invent)
# =============================================================================

def extract_identity(product: dict, profile: dict) -> dict:
    """Pull MPN/model, GTIN, SKU from the Shopify product verbatim, by priority.
    Returns identity values + a code-verified provenance fragment."""
    prov = {}

    # --- Model Number: MPN > model metafield > Variant SKU > blank -----------
    mpn   = (product.get("mpn") or product.get("google_mpn") or "").strip()
    model = (product.get("model_number") or product.get("model") or "").strip()
    vsku  = (product.get("sku") or "").strip()
    if mpn:
        model_number, msrc = mpn, "EXPORT:Google Shopping MPN"
    elif model:
        model_number, msrc = model, "EXPORT:Model Number metafield"
    elif vsku:
        model_number, msrc = vsku, "EXPORT:Variant SKU"
    else:
        model_number, msrc = "", "BLANK:no model/MPN/SKU in export"
    prov["model_number"] = {"value": model_number, "source": msrc, "verified": True}

    # --- GTIN / barcode (EAN/UPC) -------------------------------------------
    gtin = (product.get("barcode") or "").strip()
    if gtin:
        prov["product_id"] = {"value": gtin, "source": "EXPORT:Variant Barcode (GTIN)",
                              "verified": True}

    # --- Seller SKU: brand's own SKU, optional brand prefix ------------------
    base_sku = vsku or model_number or _slugish(product.get("title", ""))[:24]
    if profile.get("sku_prefix_enabled") and profile.get("sku_prefix"):
        pref = re.sub(r"[^A-Za-z0-9]+", "", profile["sku_prefix"]).upper()
        sku = f"{pref}-{base_sku}" if pref else base_sku
        ssrc = f"EXPORT:Variant SKU + brand prefix '{pref}-'"
    else:
        sku = base_sku
        ssrc = "EXPORT:Variant SKU" if vsku else "DERIVED:from title"
    prov["sku"] = {"value": sku, "source": ssrc, "verified": True}

    return {
        "model_number": model_number,
        "gtin": gtin,
        "sku": sku,
        "_prov": prov,
    }


def _slugish(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", (s or "").strip()).strip("-").upper()


# =============================================================================
# PROMPT BUILDER
# =============================================================================

def build_brand_prompt(product: dict, profile: dict, identity: dict,
                       schema: dict, keywords: list, claim_docs: list,
                       competitor_specs: str = "") -> str:
    """Build the brand-mode prompt. Emits the SAME JSON contract as the arbitrage
    build_prompt PLUS a `_provenance` map. Claims gated to evidence."""

    brand        = profile.get("brand_name", "") or product.get("vendor", "")
    vendor       = product.get("vendor", "")
    marketplace  = profile.get("marketplace", "UK")
    coo          = profile.get("country_of_origin", "").strip()
    lead_brand   = profile.get("lead_with_brand", True)
    voice_mode   = profile.get("voice_mode", "regenerate")
    tone_lang    = profile.get("tone_language", "en")
    source_lang  = product.get("source_lang") or profile.get("source_language", "en")

    spelling = "US English (color, optimize, aluminum)" if marketplace == "US" \
        else "British English (colour, optimise, aluminium)"

    # ---- format limits (profile-overridable; defaults now match the app-wide
    #      spec: 75-char title, 2000-char desc, 500-char bullets, item highlights,
    #      punctuation-free 249-byte search terms) ----------------------------
    _title_max = int(profile.get("title_max_chars", 75) or 75)
    _desc_spec = profile.get("description_spec", "up to 2000 characters including HTML tags")
    _kw_boxes  = int(profile.get("keyword_boxes", 1) or 1)

    # ---- source copy block (voice) -----------------------------------------
    source_copy = product.get("body_text") or product.get("alt_description") or ""
    if source_lang != "en" and tone_lang == "en":
        # Source copy is non-English, output is English -> translate the VOICE,
        # never output the source language verbatim.
        voice_instr = (
            f"The brand's source copy is in {source_lang}. The OUTPUT MUST be in English. "
            f"Carry the brand's tone/character into English -- TRANSLATE and ADAPT the voice, "
            f"never copy or output the source language verbatim.")
    elif source_lang != "en" and tone_lang == source_lang:
        # User deliberately chose to output in the brand's own language.
        voice_instr = (
            f"Output in {source_lang}, matching the brand's source-copy language. "
            f"{'Preserve' if voice_mode == 'preserve' else 'Refresh'} the brand's phrasing, "
            f"restructured for Amazon, subject to the claims gate below.")
    elif voice_mode == "preserve":
        voice_instr = (
            "PRESERVE the brand's voice: keep their phrasing and positioning where it is "
            "strong, but restructure for Amazon and apply the claims gate below. Output English.")
    else:
        voice_instr = (
            "REGENERATE: write fresh Amazon-optimised copy in the brand's general tone. "
            "Output English. Do not copy the source phrasing.")

    voice_notes = profile.get("voice_notes", "").strip()
    voice_block = f"\nBRAND VOICE NOTES:\n{voice_notes}\n" if voice_notes else ""

    src_block = f"\nBRAND SOURCE COPY (for voice + facts, subject to the claims gate):\n{source_copy[:2500]}\n" \
        if source_copy else "\n(No source copy provided.)\n"

    # ---- specs from export --------------------------------------------------
    spec_bits = []
    for k in ("product_type", "category_path", "tags"):
        v = product.get(k)
        if v:
            spec_bits.append(f"  {k}: {v if not isinstance(v, list) else ', '.join(v)}")
    if product.get("options"):
        spec_bits.append("  variants: " + "; ".join(
            f"{name}={'/'.join(vals)}" for name, vals in product["options"].items()))
    if product.get("price") is not None:
        spec_bits.append(f"  price: {product['price']}")
    specs_section = "\n".join(spec_bits) if spec_bits else "  (minimal structured specs)"

    # ---- claim docs ---------------------------------------------------------
    if claim_docs:
        doc_names = ", ".join(d["name"] for d in claim_docs)
        claims_evidence = (
            f"\nCLAIM-SUPPORT DOCUMENTS attached above ({len(claim_docs)}): {doc_names}\n"
            "State a specific or performance claim only when one of these documents "
            "or the brand source copy/specs supports it. Record where each claim came "
            "from in the separate `_provenance` map (use DOC:<filename> for a document).")
    else:
        claims_evidence = (
            "\nNO claim-support documents were provided. State ONLY: "
            "(a) generic category-standard benefits true of essentially all products of this "
            "type (non-quantified, e.g. 'lightweight', 'designed for everyday use') -- record "
            "these as INFERRED in the `_provenance` map; and (b) specific facts explicitly "
            "present in the brand source copy/specs -- record these as EXPORT in the "
            "`_provenance` map. Leave out any specific or performance claim you cannot ground.")

    # ---- keywords -----------------------------------------------------------
    kw_section = ""
    if keywords:
        kw_line = ", ".join(k.get("keyword", "") for k in keywords[:25] if k.get("keyword"))
        kw_section = f"\nKEYWORDS (weave naturally, do not stuff):\n  {kw_line}\n"

    comp_section = f"\nOPTIONAL COMPETITOR REFERENCE (context only, never a source of claims, never name it):\n{competitor_specs}\n" \
        if competitor_specs else ""

    title_rule = (
        f"TITLE (max {_title_max} chars): may LEAD with the brand name \"{brand}\"."
        if lead_brand else
        f"TITLE (max {_title_max} chars): do not lead with the brand name.")
    coo_rule = (f"Country of origin: {coo} (brand-stated)." if coo
                else "Country of origin: only if stated by the brand; otherwise leave the attribute out.")

    # ---- size / pack suffix -------------------------------------------------
    # The size is usually inside the source PDP title (e.g. "... 5 Gallon Pail")
    # or the harvested volume label (e.g. "5 Gal. / PAIL"). We tell the model to
    # detect it and append a normalised size to the END of the title.
    _volume = (product.get("volume") or "").strip()
    size_block = (f"SIZE / PACK (harvested): {_volume}\n" if _volume else "")
    size_rule = (
        "SIZE SUFFIX (REQUIRED): Detect the product's size/pack from the source "
        "PRODUCT TITLE and the harvested SIZE/PACK field. Append it to the END of "
        "the title as a short normalised suffix using the actual size, e.g. "
        "'5 Gal Pail', '55 Gal Drum', '3 Quart Box', '1 Gal Jug', '5 Gallon Pail'. "
        "Use 'Gal' for gallons and keep the container word (Pail/Drum/Box/Jug/Case) "
        "if present. If no size is anywhere in the source, omit the suffix rather "
        "than inventing one. Keep the whole title within the character limit.")

    return (
        f"MARKETPLACE: Amazon {marketplace}\n"
        f"MODE: BRAND-OWNER LISTING (the seller owns/represents this brand)\n"
        f"BRAND: {brand}\n"
        f"VENDOR (from catalogue): {vendor}\n"
        f"PRODUCT TITLE (source): {product.get('title','')}\n"
        f"{size_block}"
        f"IDENTIFIERS (use verbatim; already validated -- do NOT alter): "
        f"SKU={identity['sku']} | Model/MPN={identity['model_number'] or '(blank)'} | "
        f"GTIN={identity['gtin'] or '(none)'}\n"
        f"{voice_block}"
        f"{src_block}"
        f"\nEXPORT SPECS:\n{specs_section}\n"
        f"{claims_evidence}\n"
        f"{kw_section}"
        f"{comp_section}"
        "\n===================================\n"
        "VOICE\n"
        "===================================\n"
        f"{voice_instr}\n"
        "\n===================================\n"
        "CLAIMS GATE -- MANDATORY\n"
        "===================================\n"
        "- TIER 1 generic category benefits (non-quantified, true of all such products): state freely. Record as INFERRED in the _provenance map.\n"
        "- TIER 2 specific/performance claims (e.g. UV400, polarised, scratch-resistant, %, ratings):\n"
        "  state these when grounded in the brand source copy/specs (record as EXPORT) or a claim doc (record as DOC:<file>).\n"
        "  When a claim is not grounded, leave it out and write around it. State certifications, test results, or medical/health claims only with a supporting document.\n"
        "\n"
        "PROVENANCE GOES IN THE MAP, NOT THE COPY: The title, bullets, item_highlights, and description must read as clean, customer-facing sales copy with NO tags, brackets, or source labels inside them. Put every INFERRED / EXPORT / DOC / IMAGE label ONLY inside the separate `_provenance` map at the end. A customer reads the listing fields; the _provenance map is for internal review.\n"
        "\n===================================\n"
        "IDENTITY & ACCURACY\n"
        "===================================\n"
        f"- Brand is \"{brand}\". Keep it. {title_rule}\n"
        f"- {size_rule}\n"
        f"- {coo_rule}\n"
        "- Use the brand's OWN identifiers (above) verbatim. Never fabricate a model/MPN/SKU.\n"
        f"- Spelling: {spelling}.\n"
        "- Materials, colours, dimensions read from the images are fine (tag IMAGE).\n"
        "\n===================================\n"
        f"AMAZON {marketplace} COMPLIANCE\n"
        "===================================\n"
        f"TITLE max {_title_max} chars, sentence case, lead with the highest-value search keywords. ITEM HIGHLIGHTS (max 125 chars): one punchy line that captures the single most compelling reason to buy — the standout benefit or differentiator (e.g. 'Fully synthetic ISO 46 protection for rotary screw, vane and reciprocating compressors'). Make it scannable and benefit-led, not a feature dump. BULLETS: write 5, each max 500 chars. Start each bullet with a 2-4 word BENEFIT DESCRIPTOR in caps, then an em-dash, then a sentence explaining what that feature does for the buyer (e.g. 'EXTENDED EQUIPMENT LIFE — The ISO 46 viscosity grade maintains a stable oil film that protects compressor bearings and rotors during continuous-duty operation.'). Lead each bullet with a real search keyword in the first few words. Amazon indexes the first ~1000 bytes across bullets.\n"
        + f"DESCRIPTION HTML (<p><ul><li><b><br> only) {_desc_spec}. "
        + ("SEARCH TERMS (fill close to 249 bytes): write the words and short phrases a buyer types into Amazon search for this product. Build them from: the viscosity grade and its variants (e.g. iso 46, iso vg 46, vg 46), the product type and synonyms (compressor oil, compressor fluid, compressor lubricant, air compressor oil), the application (rotary screw compressor oil, reciprocating compressor oil), and the base chemistry (synthetic compressor oil, diester oil). Lowercase, single spaces, no punctuation, no brand name, no SKU. Worked example for an ISO 46 synthetic air compressor oil: 'compressor oil iso 46 iso vg 46 vg 46 synthetic compressor oil air compressor lubricant rotary screw compressor oil reciprocating compressor oil industrial compressor fluid machine oil'.\n" if _kw_boxes < 2 else
           "GENERIC KEYWORDS: TWO sets (generic_keywords_1, generic_keywords_2), each close to 250 bytes, written as real buyer search phrases (product type + viscosity + application + synonyms). Lowercase, single spaces, no punctuation, no brand repeats.\n")
        + "\n===================================\n"
        "PRODUCT ATTRIBUTES -- read the attached product images\n"
        "===================================\n"
        "Populate product_attributes with every attribute that applies (material, color, number_of_items,\n"
        "included_components, item_shape, special_features, country_of_origin, is_fragile, etc.) using exact\n"
        "accepted strings where the schema enumerates them. Non-applicable free-text -> \"N/A\"; non-applicable\n"
        "enum -> omit. Read colour/material/shape from the images when not in text (tag IMAGE).\n"
        "\n===================================\n"
        "OUTPUT -- valid JSON only, no markdown\n"
        "===================================\n"
        "Return the SAME object the arbitrage path returns, PLUS a `_provenance` map.\n"
        "{\n"
        '  "amazon_category": "", "amazon_subcategory": "",\n'
        '  "target_demographic": "", "pain_points": "", "purchase_trigger": "",\n'
        '  "title": "", "item_highlights": "", "bullet_1": "", "bullet_2": "", "bullet_3": "", "bullet_4": "", "bullet_5": "",\n'
        '  "description": "<p>...</p>", "search_terms": "",\n'
        + ('  "generic_keywords_1": "", "generic_keywords_2": "",\n' if _kw_boxes >= 2 else "") +
        '  "material": "", "colour": "", "size": "", "number_of_items": "",\n'
        '  "target_gender": "Unisex", "age_range": "Adult", "compliance_notes": "None",\n'
        '  "product_attributes": { "material": "", "color": "", "number_of_items": 1, "country_of_origin": "" },\n'
        '  "_provenance": {\n'
        '     "title":   {"source": "INFERRED|EXPORT|DOC:<file>|IMAGE|COMPETITOR", "note": ""},\n'
        '     "bullet_1":{"source": "...", "note": "which claim came from where"},\n'
        '     "material":{"source": "IMAGE|EXPORT|INFERRED", "note": ""}\n'
        '     /* include an entry for every field you filled with a non-generic value */\n'
        "  }\n"
        "}"
    )


# =============================================================================
# PROVENANCE MERGE  (code-verified deterministic fields win over model-reported)
# =============================================================================

def merge_provenance(identity: dict, profile: dict, listing: dict) -> dict:
    """Combine code-verified provenance (identity + config) with Claude's
    self-reported `_provenance`. Code-verified entries are marked verified=True."""
    merged = {}
    # model-reported first (verified=False)
    for field, info in (listing.get("_provenance") or {}).items():
        if isinstance(info, dict):
            merged[field] = {"source": info.get("source", "INFERRED"),
                             "note": info.get("note", ""), "verified": False}
    # code-verified overrides
    for field, info in (identity.get("_prov") or {}).items():
        merged[field] = info
    merged["brand"]       = {"value": profile.get("brand_name", ""), "source": "CONFIG:brand profile", "verified": True}
    merged["marketplace"] = {"value": profile.get("marketplace", "UK"), "source": "CONFIG:brand profile", "verified": True}
    if profile.get("country_of_origin"):
        merged["country_of_origin"] = {"value": profile["country_of_origin"],
                                       "source": "CONFIG:brand profile", "verified": True}
    return merged


# =============================================================================
# COMPATIBILITY SHELLS  (so the existing build_sheet_row works unchanged)
# =============================================================================

def compute_brand_price(product: dict, profile: dict):
    """Convert the Shopify source price to the Amazon target price.

    Profile keys:
      source_currency : e.g. 'SEK' (just a label, for clarity)
      fx_rate         : multiply source price by this to get target currency
                        (e.g. SEK->GBP ~ 0.075). Default 1.0 (no conversion).
      price_markup    : multiply again by this (e.g. 1.0 = none, 1.4 = +40%).
      price_round_99  : if true, round to .99 (e.g. 14.27 -> 14.99).
      price_fixed     : if set (>0), use this exact price and ignore everything else.

    Returns (final_price_float, note_str).
    """
    raw = product.get("price")
    try:
        raw = float(raw) if raw is not None else 0.0
    except (ValueError, TypeError):
        raw = 0.0

    fixed = profile.get("price_fixed")
    if fixed:
        try:
            return round(float(fixed), 2), f"fixed price {fixed}"
        except (ValueError, TypeError):
            pass

    try:
        fx = float(profile.get("fx_rate") or 1.0)
    except (ValueError, TypeError):
        fx = 1.0
    try:
        markup = float(profile.get("price_markup") or 1.0)
    except (ValueError, TypeError):
        markup = 1.0

    price = raw * fx * markup
    if profile.get("price_round_99") and price > 0:
        price = float(int(price)) + 0.99
    price = round(price, 2)

    src_cur = profile.get("source_currency", "src")
    tgt_cur = "GBP" if profile.get("marketplace", "UK") == "UK" else "USD"
    note = f"{raw} {src_cur} x fx {fx} x markup {markup} = {price} {tgt_cur}"
    return price, note


def _shells(product: dict, profile: dict, identity: dict):
    """Synthesize the comp_data / pricing / financials / voc_data shells that
    build_sheet_row expects, for a product that has NO competitor."""
    price, price_note = compute_brand_price(product, profile)
    comp_data = {
        "asin": "", "title": product.get("title", ""),
        "brand": profile.get("brand_name", "") or product.get("vendor", ""),
        "product_type": product.get("product_type", "") or "PRODUCT",
        "attributes": {}, "images": product.get("images", [])[:5],
        "sales_rank": [],
    }
    pricing = {"buy_box_price": float(price) if price else 0.0}
    financials = {
        "selling_price": float(price) if price else 0.0,
        "total_amazon_fees": 0.0, "fee_source": "n/a (brand)",
        "profit": 0.0, "margin_pct": "n/a", "roi_pct": "n/a", "viable": "BRAND",
        "price_note": price_note,
    }
    voc_data = {"source": "brand", "review_count": 0}
    return comp_data, pricing, financials, voc_data


# =============================================================================
# PER-PRODUCT RUNNER  (brand-mode sibling of host.process_row)
# =============================================================================

def _img_to_data_url(src: str) -> str:
    """Resolve an image reference to a base64 data URL that image_gen accepts.
    Handles: http(s) URLs (with SSL verification DISABLED, since supplier sites
    like mileslubricants.com have broken certs), local file paths, /media/ paths,
    and existing data URLs. Returns '' on failure."""
    if not src:
        return ""
    s = str(src).strip()
    if s.startswith("data:"):
        return s
    try:
        import base64 as _b64, mimetypes as _mt
        from pathlib import Path as _Path
        # http(s): fetch with verification off (broken supplier certs)
        if s.startswith(("http://", "https://")):
            import urllib.request as _u, ssl as _ssl
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            req = _u.Request(s, headers={"User-Agent": "Mozilla/5.0"})
            with _u.urlopen(req, timeout=30, context=ctx) as r:
                data = r.read()
            mime = _mt.guess_type(s)[0] or "image/jpeg"
            return f"data:{mime};base64," + _b64.b64encode(data).decode("ascii")
        # local /media/ path -> resolve under the app's media dir
        if s.startswith("/media/"):
            p = _Path(_app_dir()) / "media" / s[len("/media/"):]
            if p.exists():
                mime = _mt.guess_type(str(p))[0] or "image/png"
                return f"data:{mime};base64," + _b64.b64encode(p.read_bytes()).decode("ascii")
            return ""
        # absolute or relative local file path
        p = _Path(s)
        if p.exists():
            mime = _mt.guess_type(str(p))[0] or "image/png"
            return f"data:{mime};base64," + _b64.b64encode(p.read_bytes()).decode("ascii")
    except Exception:
        pass
    return ""


def _lookup_brand_recipe(brand: str):
    """Return (template_image_path_or_url, instructions) for the brand's first
    saved image recipe, or ('', '') if none. Reads the same recipes.json the
    dashboard's Image Studio writes."""
    try:
        import json as _json
        from pathlib import Path as _Path
        rp = _Path(_app_dir()) / "image_recipes.json"
        if not rp.exists():
            rp = _Path(_app_dir()) / "recipes.json"
        if not rp.exists():
            return "", ""
        data = _json.loads(rp.read_text(encoding="utf-8"))
        lst = data.get(brand) or []
        if not lst:
            # fall back to any brand's first recipe so the user still gets a style
            for _bn, _l in data.items():
                if _l:
                    lst = _l
                    break
        if lst:
            r = lst[0]
            tpl = r.get("template_image", "") or ""
            # local /media path -> absolute file path the image_gen fetcher can read
            if tpl.startswith("/media/"):
                tpl_local = _Path(_app_dir()) / "media" / tpl[len("/media/"):]
                if tpl_local.exists():
                    tpl = str(tpl_local)
            return tpl, r.get("instructions", "") or ""
    except Exception:
        pass
    return "", ""


def _save_main_image(sku: str, image_b64: str, account_id: str = "") -> str:
    """Persist a generated main image to the account-scoped media library and
    return a URL path the dashboard serves. Mirrors the dashboard's layout:
    account media live under media/_acct/<aid>/<sku>/, served at the matching
    /media/_acct/<aid>/<sku>/<file> URL."""
    try:
        import base64 as _b64, time as _t
        from pathlib import Path as _Path
        media = _Path(_app_dir()) / "media"
        if account_id:
            base = media / "_acct" / _safe_seg(account_id) / _safe_seg(sku)
            urlpfx = f"/media/_acct/{_safe_seg(account_id)}/{_safe_seg(sku)}"
        else:
            base = media / _safe_seg(sku)
            urlpfx = f"/media/{_safe_seg(sku)}"
        base.mkdir(parents=True, exist_ok=True)
        fname = f"main_{int(_t.time())}.png"
        (base / fname).write_bytes(_b64.b64decode(image_b64))
        return f"{urlpfx}/{fname}"
    except Exception:
        return ""


def _safe_seg(s: str) -> str:
    """Filesystem-safe path segment from a SKU."""
    import re as _re
    return _re.sub(r"[^A-Za-z0-9_.-]", "_", str(s or "item"))[:64]


MILES_SHEET_HEADERS = [
    "SKU", "Title", "Item Highlights",
    "Bullet Point 1", "Bullet Point 2", "Bullet Point 3",
    "Bullet Point 4", "Bullet Point 5", "Description", "Backend Keywords",
    "Column 1", "Compliance Report", "Uploaded",
]

_PROV_TAG = re.compile(
    r'\s*\[\s*(?:EXPORT|INFERRED|IMAGE|COMPETITOR|DOC)[^\]]*\]',
    re.I)

_PHONE_PATTERN = re.compile(
    r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'       # US phone: 877-683-8086
    r'|\b\d{1,3}[-.\s]\d{3}[-.\s]\d{4}\b'       # variations
)

def _strip_prov(s: str) -> str:
    """Remove inline provenance tags, phone numbers, and trailing SKU/MPN
    references that shouldn't appear in customer-facing listing copy."""
    s = _PROV_TAG.sub("", s or "")
    s = _PHONE_PATTERN.sub("", s)
    # Remove trailing "SKU: MSFxxxxxx" or "MPN: MSFxxxxxx" patterns
    s = re.sub(r'\bSKU\s*[:/]\s*MSF\d+\b', '', s, flags=re.I)
    s = re.sub(r'\bMPN\s*[:/]\s*MSF\d+\b', '', s, flags=re.I)
    # Clean up leftover punctuation artifacts
    s = re.sub(r'\s*[—–-]\s*$', '', s)  # trailing dashes
    s = re.sub(r'\s{2,}', ' ', s)       # double spaces
    return s.strip()


def _strip_html_to_text(html: str) -> str:
    """Convert the listing's HTML description to plain text (the Miles sheet
    stores a plain-text description, not HTML)."""
    if not html:
        return ""
    t = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"</\s*(p|li|ul|ol)\s*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)                 # drop remaining tags
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def _miles_write_row(host, ws, row_values: list) -> bool:
    """Append a row to the Miles sheet at the first truly empty row (by scanning
    column A / SKU), ensuring the Miles header is in row 1 first. Using an
    explicit row index avoids gspread append_row landing far below the data."""
    try:
        existing = ws.row_values(1)
    except Exception:
        existing = []
    try:
        if not existing:
            ws.update([MILES_SHEET_HEADERS], "A1")
        elif existing[:1] and existing[0].strip().upper() != "SKU":
            ws.insert_row(MILES_SHEET_HEADERS, 1)
    except Exception:
        pass

    for attempt in range(1, 4):
        try:
            # Find the next empty row by reading column A (SKU). The first row
            # with no SKU value is where we write -- right below the last listing.
            col_a = ws.col_values(1)            # includes header at index 0
            next_row = len(col_a) + 1           # 1-based row just after last filled
            # Write the row explicitly at that position (A{next_row}).
            end_col = _col_letter(len(row_values))
            rng = f"A{next_row}:{end_col}{next_row}"
            # gspread 6.x signature: update(values, range_name, ...)
            ws.update([row_values], rng, value_input_option="USER_ENTERED")
            # Read-back verification: confirm the SKU actually landed in A{next_row}
            try:
                check = ws.acell(f"A{next_row}").value
            except Exception:
                check = None
            wrote_sku = (row_values[0] if row_values else "")
            if check and str(check).strip() == str(wrote_sku).strip():
                host.console.print(f"  [green]   -> CONFIRMED row {next_row} of "
                                   f"'{ws.title}' (SKU {wrote_sku})[/green]")
                return True
            else:
                host.console.print(f"  [yellow]   -> write to row {next_row} did NOT "
                                   f"verify (read back '{check}'); retrying[/yellow]")
                raise RuntimeError("write did not verify")
        except Exception as e:
            if attempt == 3:
                host.console.print(f"  [red]Miles sheet write failed after 3 tries: "
                                   f"{str(e)[:120]}[/red]")
                return False
            import time as _t
            _t.sleep(attempt * 3)
    return False


def _col_letter(n: int) -> str:
    """1-based column number -> spreadsheet letter (1->A, 27->AA)."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def process_brand_row(product: dict, profile: dict, *, host, client, ws_out,
                      creds: dict, config: dict, idx: int, total: int,
                      taken_skus: set, compliance_rules: dict, ip_rules: dict,
                      static_vv: dict, claim_docs: list,
                      competitor_specs: str = "") -> bool:
    """Generate one brand listing and write it to the same output sheet/contract
    as the arbitrage path. Returns True on success."""
    console = host.console
    brand   = profile.get("brand_name", "") or product.get("vendor", "")
    title0  = product.get("title", "")[:55]

    console.print(f"\n{'='*60}")
    console.print(f"[bold magenta][{idx}/{total}] BRAND[/bold magenta] {brand} :: {title0}")
    console.print(f"{'='*60}")

    # 1) identity (code-verified, never invented)
    identity = extract_identity(product, profile)
    sku = identity["sku"]
    # DUPLICATE GUARD: if this SKU is already in the sheet, SKIP it (do not
    # regenerate or append -N) unless the profile explicitly opts to replace.
    # This stops re-runs from re-listing products you've already generated.
    if sku in taken_skus and not profile.get("replace_existing"):
        console.print(f"  [dim]skip: SKU {sku} already exists (set 'replace_existing' "
                      f"to regenerate)[/dim]")
        return False
    taken_skus.add(sku)
    console.print(f"  SKU: {sku} | Model/MPN: {identity['model_number'] or '(blank)'} | "
                  f"GTIN: {identity['gtin'] or '(none)'}")

    # 2) product type schema (reuse host) -- use the brand's marketplace so a
    # US brand queries the US catalogue (not the UK one, which causes NOT_FOUND)
    product_type = product.get("product_type", "") or "PRODUCT"
    # Amazon product types are specific UPPER_SNAKE tokens. Shopify gives free
    # text ("Sunglasses"). Normalise + map common ones so schema resolves.
    _PT_MAP = {
        "SUNGLASSES": "SUNGLASSES", "SUNGLASS": "SUNGLASSES",
        "EYEWEAR": "SUNGLASSES", "FISHING SUNGLASSES": "SUNGLASSES",
        "FISHING LURE": "FISHING_BAIT", "FISHING LURES": "FISHING_BAIT",
        "LURE": "FISHING_BAIT", "BAIT": "FISHING_BAIT",
        "T SHIRT": "SHIRT", "T-SHIRT": "SHIRT", "TEE": "SHIRT",
        "HAT": "HAT", "CAP": "HAT", "BEANIE": "HAT",
        "HOODIE": "SHIRT", "SWEATSHIRT": "SHIRT",
        "BACKPACK": "BACKPACK", "BAG": "BACKPACK",
    }
    _pt_norm = re.sub(r"[^A-Za-z0-9 ]", " ", str(product_type)).strip().upper()
    _pt_norm = re.sub(r"\s+", " ", _pt_norm)
    product_type = _PT_MAP.get(_pt_norm, product_type.upper().replace(" ", "_"))
    _mkt = profile.get("marketplace", "UK")
    try:
        schema = host.get_product_type_schema(product_type, creds, marketplace=_mkt)
    except Exception:
        schema = {"all": {}}

    # 3) keywords (reuse host autocomplete on the product's own term)
    try:
        core = host.extract_core_search_term(product_type or title0)
        keywords = host.get_autocomplete_keywords(core)
    except Exception:
        keywords = []

    # 4) build prompt + attach images AND claim docs
    prompt = build_brand_prompt(product, profile, identity, schema, keywords,
                                claim_docs, competitor_specs)
    content = host._build_message_content(prompt, product.get("images", []))
    # attach claim docs (PDF/image) as additional document blocks
    for d in claim_docs:
        block_type = "document" if d["media_type"] == "application/pdf" else "image"
        content.insert(0, {
            "type": block_type,
            "source": {"type": "base64", "media_type": d["media_type"], "data": d["data"]},
        })

    # 5) call Claude (reuse host system prompt + JSON repair)
    console.print("  Generating (brand voice, claims-gated)...", end=" ")
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=5000,
            system=host.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        listing = json.loads(raw)
        console.print("done")
        status = "NEEDS_REVIEW"
    except Exception as e:
        console.print(f"[red]failed: {str(e)[:120]}[/red]")
        return False

    # length guards (mirror host) -- respect the profile's title limit (default 75)
    _tmax = int(profile.get("title_max_chars", 75) or 75)
    if len(listing.get("title", "")) > _tmax:
        _cap = getattr(host, "cap_chars", None)
        listing["title"] = _cap(listing["title"], _tmax) if _cap else listing["title"][:_tmax]
    # Item Highlights cap (new app-wide field)
    if listing.get("item_highlights"):
        _cap = getattr(host, "cap_chars", None)
        listing["item_highlights"] = _cap(listing["item_highlights"], 125) if _cap else listing["item_highlights"][:125]
    # If the listing came back with two generic-keyword boxes, fold them into the
    # single search_terms cell for the sheet (kept as separate fields too, for the
    # live-Amazon upload step).
    gk1 = (listing.get("generic_keywords_1") or "").strip()
    gk2 = (listing.get("generic_keywords_2") or "").strip()
    if (gk1 or gk2) and not listing.get("search_terms"):
        listing["search_terms"] = (gk1 + " " + gk2).strip()
    # Backend search terms: strip punctuation, single-space, 249-byte cap (app-wide)
    _clean = getattr(host, "clean_search_terms", None)
    if _clean:
        listing["search_terms"] = _clean(listing.get("search_terms", ""))
        if gk1:
            listing["generic_keywords_1"] = _clean(gk1)
        if gk2:
            listing["generic_keywords_2"] = _clean(gk2)
    else:
        st = listing.get("search_terms", "")
        if len(st.encode("utf-8")) > 249:
            st = st.encode("utf-8")[:249].decode("utf-8", "ignore")
            listing["search_terms"] = st

    # 6) provenance merge (code-verified wins)
    provenance = merge_provenance(identity, profile, listing)
    # Keep provenance in a SEPARATE key so it never renders as an attribute row
    # ([object Object] bug). The dashboard reads _provenance for the "i" button.
    pa = listing.setdefault("product_attributes", {})
    # Store provenance INSIDE product_attributes so it serializes into the sheet's
    # Attributes JSON column -- the dashboard reads it for the "i" button and hides
    # it from the attribute rows (via _AHIDE). Top-level copy kept for any direct use.
    pa["_provenance"] = provenance
    listing["_provenance"] = provenance
    if identity["gtin"]:
        pa.setdefault("externally_assigned_product_identifier", identity["gtin"])

    # 7) compliance + IP -- INFORMATIONAL by default for brand mode.
    # Brand listings should NOT be auto-held just because no claim docs were
    # attached or because some benefits are generic/inferred. We surface findings
    # as review notes; only a genuine regulatory HIGH (not doc-related) suggests
    # a hold, and even then we leave the row reviewable rather than blocking.
    notes_parts = []
    comp_result = host.check_compliance(title0, listing, compliance_rules)
    compliance_risk = comp_result.get("highest_risk", "")
    if comp_result.get("matched_categories"):
        notes_parts.append(comp_result["summary"])

    # brand-specific forbidden brands fold into the IP check via ip_rules
    ip_rules_eff = dict(ip_rules or {})
    if profile.get("forbidden_brands"):
        fb = set(ip_rules_eff.get("forbidden_brands", [])) | set(profile["forbidden_brands"])
        ip_rules_eff["forbidden_brands"] = list(fb)

    # Profile-level extra safe words (e.g. lubricant regulatory/technical terms)
    _extra_safe = {w.lower() for w in profile.get("safe_words_extra", [])}
    # Profile-level phrase overrides -- remove phrases that are fine for this brand
    _allowed_phrases = {p.lower() for p in profile.get("allowed_phrases_override", [])}
    if _allowed_phrases:
        ip_rules_eff["forbidden_phrases"] = [
            p for p in ip_rules_eff.get("forbidden_phrases", [])
            if p.lower() not in _allowed_phrases
        ]
    # For Miles (SDS-grounded lubricant copy), disable the unknown-caps scan
    # entirely. Every sentence has capitalised technical terms (ISO, NFPA,
    # Viscosity, etc.) and the caps-scan creates endless false positives.
    # The REAL IP protection is the forbidden-brands list (166 OEM names +
    # 44 spec codes) which still fires regardless of this threshold.
    if profile.get("miles_sheet_format"):
        ip_rules_eff["max_unrecognised"] = 9999
    # The brand's OWN vocabulary (brand name, vendor, model/MPN/SKU, option values,
    # product-type words) is legitimate in brand mode -- add it to the caps safe-set
    # so the IP scanner doesn't flag the brand's own terms and hold every listing.
    own_terms = set()
    # Extract all word tokens from brand identity + the listing title so that
    # product-name words (e.g. "Stratus", "Nimbus") are automatically safe.
    for src in (brand, product.get("vendor", ""), identity.get("model_number", ""),
                identity.get("sku", ""), product.get("product_type", ""),
                product.get("title", ""), listing.get("title", "")):
        for tok in re.split(r"[\s/_\-]+", str(src)):
            tok = tok.strip()
            if len(tok) >= 2:
                own_terms.add(tok.lower())
    for vals in (product.get("options") or {}).values():
        for v in vals:
            for tok in re.split(r"[\s/_\-]+", str(v)):
                tok = tok.strip()
                if len(tok) >= 2:
                    own_terms.add(tok.lower())
    existing_safe = ip_rules_eff.get("safe_capitalised_lc", set())
    if not isinstance(existing_safe, set):
        existing_safe = set(existing_safe)
    ip_rules_eff["safe_capitalised_lc"] = existing_safe | own_terms | _extra_safe
    ip_result = host.check_ip_violations(listing, brand, ip_rules_eff)
    ip_risk = ""
    if ip_result.get("has_violations"):
        # Note only -- do NOT auto-hold. Real comparative-phrase hits ("compatible
        # with", etc.) are worth a review note; the user decides via the dashboard.
        notes_parts.append(ip_result["summary"])
        ip_risk = "REVIEW"

    # 8) converge into the EXISTING sheet row + write
    comp_data, pricing, financials, voc_data = _shells(product, profile, identity)
    row_in = {"ebay_url": "", "upc": identity["gtin"]}
    handling = str(profile.get("handling_time", "3"))

    # --- Miles custom sheet format -------------------------------------------
    # Write the user's exact column layout instead of the 48-col FIXED_HEADERS:
    # SKU | Title | Bullet Point 1..5 | Description | Backend Keywords |
    # Column 1 | Compliance Report | Uploaded
    if profile.get("miles_sheet_format"):
        _clean = getattr(host, "clean_search_terms", None)
        _bk = listing.get("search_terms", "")
        if _clean:
            _bk = _clean(_bk)
        # Strip SKU/MPN from keywords (not a search term buyers use)
        _sku_lc = sku.lower()
        _bk = " ".join(w for w in _bk.split() if w != _sku_lc)

        # If the AI returned PROSE instead of keywords (contains filler/connective
        # words), discard it -- the enricher below will build clean keywords.
        _prose_markers = {"utilizes", "designed", "provide", "helping", "demanding",
                          "continuous", "conditions", "maintain", "components",
                          "suited", "across", "broad", "delivering", "engineered",
                          "formulated", "providing", "meeting", "requirements",
                          "inferred", "export", "specification", "matched"}
        _bk_words = set(_bk.lower().split())
        if len(_bk_words & _prose_markers) >= 2:
            _bk = ""   # reset; rebuild cleanly from curated phrases below

        # Keyword enrichment: if AI returned sparse keywords (< 180 bytes),
        # aggressively derive additional terms from REAL search-keyword
        # components (not prose words). Buyers search "compressor oil iso 46",
        # not "utilizes demanding continuous". We build from curated phrase
        # parts: product type + viscosity + application + chemistry + synonyms.
        if len(_bk.encode("utf-8")) < 180:
            _extras = []
            _title_lc = listing.get("title", "").lower()
            _all_text = (listing.get("title", "") + " "
                         + " ".join(listing.get(f"bullet_{i}", "") for i in range(1, 6))
                         + " " + (product.get("description", "") or "")).lower()

            # 1. Viscosity grade variants (the #1 search component for lubricants)
            _grades = set()
            for m in re.finditer(r"iso\s*v?g?\s*(\d+)", _all_text):
                _grades.add(m.group(1))
            for g in _grades:
                _extras += [f"iso {g}", f"iso vg {g}", f"vg {g}", f"{g} weight",
                            f"{g} grade"]

            # 2. Product-type phrases (detected from title/text)
            _type_map = {
                "compressor": ["compressor oil", "compressor fluid",
                               "compressor lubricant", "air compressor oil",
                               "air compressor lubricant", "rotary screw compressor oil",
                               "industrial compressor oil", "screw compressor oil",
                               "reciprocating compressor oil", "vane compressor oil"],
                "hydraulic":  ["hydraulic oil", "hydraulic fluid", "anti wear hydraulic",
                               "aw hydraulic oil", "industrial hydraulic oil",
                               "pump oil", "machine hydraulic fluid"],
                "gear":       ["gear oil", "gear lubricant", "industrial gear oil",
                               "extreme pressure gear", "ep gear oil",
                               "gearbox oil", "enclosed gear oil"],
                "turbine":    ["turbine oil", "circulating oil", "bearing oil",
                               "rust oxidation oil", "ro turbine oil"],
                "coolant":    ["compressor coolant", "synthetic coolant",
                               "coolant fluid", "cooling lubricant"],
                "cleaner":    ["compressor cleaner", "system flush", "flush fluid",
                               "deposit cleaner", "varnish remover"],
                "way":        ["way oil", "slideway oil", "machine way lube"],
                "vacuum":     ["vacuum pump oil", "vacuum pump fluid"],
            }
            for key, phrases in _type_map.items():
                if key in _title_lc:
                    _extras += phrases

            # 3. Chemistry / attribute phrases (only if present in the text)
            _attr_map = {
                "synthetic":   ["synthetic oil", "full synthetic", "synthetic lubricant"],
                "diester":     ["diester oil", "diester base", "ester compressor oil"],
                "mineral":     ["mineral oil", "petroleum base"],
                "non-hazard":  ["non hazardous oil", "low hazard lubricant"],
                "food":        ["food grade oil", "fg lubricant", "h1 lubricant"],
            }
            for key, phrases in _attr_map.items():
                if key in _all_text:
                    _extras += phrases

            # 4. Generic high-volume synonyms always relevant for lubricants
            _extras += ["industrial oil", "machine oil", "lubricating oil"]

            # Build supplemental string. Dedupe whole phrases, and skip a phrase
            # only if it's an EXACT duplicate already in the keyword string.
            _bk_lc = _bk.lower()
            _supp_words = []
            _seen_supp = set()
            for w in _extras:
                wl = w.lower().strip()
                if not wl or len(wl) < 3:
                    continue
                if wl in _seen_supp:
                    continue
                # skip if this exact phrase already appears in current keywords
                if re.search(r"(?:^|\s)" + re.escape(wl) + r"(?:$|\s)", _bk_lc):
                    continue
                _supp_words.append(wl)
                _seen_supp.add(wl)
            _supp = " ".join(_supp_words)
            if _clean:
                _supp = _clean(_supp)
            combined = (_bk + " " + _supp).strip()
            # Byte-cap at 249
            if len(combined.encode("utf-8")) > 249:
                _bk_b = combined.encode("utf-8")[:249].decode("utf-8", "ignore")
                _bk = _bk_b[:_bk_b.rfind(" ")].strip() if " " in _bk_b else _bk_b
            else:
                _bk = combined
        # For Miles lubricant listings the generic category-compliance scanner
        # fires false positives (lubricant copy mentions "health", "fire" from
        # NFPA ratings which triggers food/electrical/sports categories).
        # Only surface real IP violations, not category mismatches.
        comp_report = "Generated"
        if ip_result.get("has_violations") and notes_parts:
            # Filter to only genuine IP findings, not compliance categories
            ip_notes = [n for n in notes_parts if "IP" in n or "brand" in n.lower()
                        or "forbidden" in n.lower() or "phrase" in n.lower()]
            if ip_notes:
                comp_report = "REVIEW: " + " | ".join(ip_notes)
        elif compliance_risk in ("HIGH", "MEDIUM") and notes_parts:
            # Only flag if not a known false-positive category for lubricants
            _false_pos = {"electrical", "sports_fitness", "food_consumables",
                          "medical_health", "tools_hardware"}
            comp_cats = set()
            for n in notes_parts:
                if "[HIGH]" in n or "[MEDIUM]" in n:
                    for cat in _false_pos:
                        if cat in n:
                            comp_cats.add(cat)
            real_issues = [n for n in notes_parts
                           if not any(fp in n for fp in _false_pos)]
            if real_issues:
                comp_report = f"{compliance_risk} risk: " + " | ".join(real_issues)
        # --- Auto main image (when account has the image_template feature) ----
        _main_img_url = ""
        if profile.get("auto_image"):
            try:
                _imgs = product.get("images") or []
                _src = _imgs[0] if _imgs else ""
                if not _src:
                    console.print("  [yellow]auto-image: no product photo harvested -- skipped[/yellow]")
                else:
                    # Resolve the harvested product image to a data URL (supplier
                    # site has a broken SSL cert, so verification is disabled).
                    _src_data = _img_to_data_url(_src)
                    if not _src_data:
                        console.print("  [yellow]auto-image: could not load product photo -- skipped[/yellow]")
                    else:
                        # Use the SAME image pipeline the dashboard uses
                        # (ai_providers + OpenRouter/Seedream), not a separate
                        # Gemini path. Brand recipe (if any) becomes the brief.
                        from domain import ai_providers as _aip
                        _tpl, _instr = _lookup_brand_recipe(profile.get("brand_name", ""))
                        _brief = (_instr or
                                  "Clean Amazon main image on pure white background, "
                                  "product centred, no props or text, studio lighting.")
                        _tpl_data = _img_to_data_url(_tpl) if _tpl else ""
                        console.print("  generating main image...", end=" ")
                        _res = _aip.run_pipeline(
                            profile.get("_config", {}),
                            brief=_brief,
                            reference_image=_src_data,
                            product_title=listing.get("title", ""),
                            image_kind="main",
                            read_product=True,
                            strength=0.25,
                            extra_reference=_tpl_data)
                        if _res.get("ok") and _res.get("image_b64"):
                            _main_img_url = _save_main_image(
                                sku, _res["image_b64"], profile.get("_account_id", ""))
                            console.print("[green]done[/green]")
                        elif _res.get("ok") and _res.get("image_url"):
                            _main_img_url = _res["image_url"]
                            console.print("[green]done (url)[/green]")
                        else:
                            console.print(f"[yellow]skipped: {str(_res.get('error',''))[:80]}[/yellow]")
            except Exception as _ie:
                console.print(f"  [yellow]auto-image error: {str(_ie)[:100]}[/yellow]")

        miles_row = [
            sku,
            _strip_prov(listing.get("title", "")),
            _strip_prov(listing.get("item_highlights", "")),
            _strip_prov(listing.get("bullet_1", "")),
            _strip_prov(listing.get("bullet_2", "")),
            _strip_prov(listing.get("bullet_3", "")),
            _strip_prov(listing.get("bullet_4", "")),
            _strip_prov(listing.get("bullet_5", "")),
            _strip_prov(listing.get("description", "")),
            _bk,
            _main_img_url,
            comp_report,
            "No",
        ]
        ok = _miles_write_row(host, ws_out, miles_row)
        console.print(f"  [{'green' if ok else 'red'}]{'written (Miles format)' if ok else 'write failed'}[/]"
                      f" | status={status}")
        return bool(ok)

    row_data = host.build_sheet_row(
        "", row_in, listing, comp_data, financials, pricing, voc_data, keywords,
        handling, handling, sku, status,
        brand=brand, model_number=identity["model_number"],
        notes=" | ".join(notes_parts), compliance_risk=compliance_risk, ip_risk=ip_risk,
        marketplace=profile.get("marketplace", "UK"))
    ok = host.sheet_write_row(ws_out, row_data, "")
    console.print(f"  [{'green' if ok else 'red'}]{'written' if ok else 'write failed'}[/]"
                  f" | status={status}")
    return bool(ok)
