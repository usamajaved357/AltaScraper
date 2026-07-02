"""
shopify_import.py  --  Shopify product-export -> internal product-dict adapter.

Build #1 of the BRAND-LISTING feature for amazon_listing_generator.py.

WHY THIS EXISTS
---------------
The original app generates Amazon listings by scraping a COMPETITOR ASIN and
de-branding it. The brand-listing feature is the inverse: a brand (or a reseller's
multi-vendor store) gives us their OWN Shopify catalogue, and Claude writes
optimised Amazon listings in the brand's voice, with claims gated to supporting
docs.

This module is the first piece: it turns a Shopify product-export CSV into the
SAME internal product-dict shape the rest of the pipeline already consumes, so
nothing downstream (schema fetch, compliance, IP scan, sheet write, exports) has
to change.

WHAT IT HANDLES (learned from a real export, not assumed)
---------------------------------------------------------
  * Delimiter auto-detect      : Shopify exports can be ',' OR ';' (EU stores use ';').
  * Encoding auto-detect        : UTF-8 / UTF-8-BOM / cp1252 (Windows/EU exports).
  * Variant + image collapse    : 1 parent row (has Title) + N continuation rows
                                  (Image Src only). Collapse to one product.
  * Multi-variant products      : Option1/2/3 values collected; price range derived.
  * Body (HTML) -> clean text   : tags stripped, entities decoded, whitespace tidied.
  * Vendor per product          : drives reseller-mode per-vendor brand handling.
  * Barcode mojibake            : leading stray byte (e.g. '?') from cp1252 stripped.
  * Status filter               : skip draft/archived unless caller asks for them.

OUTPUT: list[dict], each dict shaped to feed build_brand_prompt(). Keys mirror the
competitor-data dict (`comp_data`) used by the arbitrage path where it makes sense,
so the two paths converge cleanly before export.
"""

import csv
import html
import io
import re
from collections import Counter
from pathlib import Path


# =============================================================================
# SOURCE-LANGUAGE DETECTION  (dependency-free, feeds the dashboard tone dropdown)
# =============================================================================
# The tone dropdown shows English first (default, selected). If the brand's
# source copy is NOT English, the detected language is offered as a second
# option. Output stays English unless the user deliberately switches. This
# detector decides what that second option is (or that there is none).
#
# Heuristic: high-frequency stopword density per language. Cheap, no model, and
# accurate enough for "which language is this copy mostly in" (validated at
# 159/165 Swedish on a real Swedish eyewear catalogue, clean separation).

_STOPWORDS = {
    "en": "the and to of a in is it you that he was for on are with as his they at be this from or have an",
    "sv": "och att det som en av är för på med inte den till han har de ett om så men vi kan jag du den här",
    "pt": "que não uma para com por como mais mas dos das são você está muito quando ser tem foi pelo",
    "es": "que no una para con por como más pero los las son está muy cuando ser tiene fue el la de y",
    "de": "und der die das den dem ein eine ist nicht mit auf für von im zu sich auch werden wird bei",
    "fr": "le la les des une que pas pour dans qui est avec sur ne se au ce il elle nous vous par",
    "it": "che non una per con come più ma dei delle sono molto quando essere ha stato dal il lo di e",
    "nl": "de het een en van te dat die is in op met voor niet aan zijn er maar als ook door om",
}
_STOP_SETS = {lang: set(words.split()) for lang, words in _STOPWORDS.items()}
_LANG_NAMES = {
    "en": "English", "sv": "Swedish", "pt": "Portuguese", "es": "Spanish",
    "de": "German", "fr": "French", "it": "Italian", "nl": "Dutch",
}
_WORD_RE = re.compile(r"[a-zA-ZàâäáãåçéèêëíìîïóòôöõúùûüñÀÂÄÁÃÅÇÉÈÊËÍÌÎÏÓÒÔÖÕÚÙÛÜÑ]+")


def detect_language(text: str):
    """Return (lang_code, confidence_pct). 'en' on empty/unknown."""
    if not text:
        return "en", 0.0
    words = _WORD_RE.findall(text.lower())
    if not words:
        return "en", 0.0
    counts = Counter(words)
    scores = {lang: sum(counts[w] for w in sset) for lang, sset in _STOP_SETS.items()}
    best_lang = max(scores, key=scores.get)
    conf = round(scores[best_lang] / len(words) * 100, 1)
    if conf < 3.0:                 # too little signal -> assume English
        return "en", conf
    return best_lang, conf


def detect_catalogue_language(products: list):
    """Dominant source language across a parsed catalogue. Returns
    {'code', 'name', 'is_english', 'per_lang': {code: count}} for the dropdown."""
    tally = Counter()
    for p in products:
        src = p.get("body_text") or p.get("alt_description") or p.get("title") or ""
        code, _ = detect_language(src)
        tally[code] += 1
    if not tally:
        code = "en"
    else:
        code = tally.most_common(1)[0][0]
    return {
        "code": code,
        "name": _LANG_NAMES.get(code, code),
        "is_english": code == "en",
        "per_lang": dict(tally),
    }


# --- Shopify export column names (stable across versions) --------------------
COL_HANDLE      = "Handle"
COL_TITLE       = "Title"
COL_BODY        = "Body (HTML)"
COL_VENDOR      = "Vendor"
COL_CATEGORY    = "Product Category"
COL_TYPE        = "Type"
COL_TAGS        = "Tags"
COL_PUBLISHED   = "Published"
COL_STATUS      = "Status"
COL_SKU         = "Variant SKU"
COL_PRICE       = "Variant Price"
COL_COMPARE     = "Variant Compare At Price"
COL_GRAMS       = "Variant Grams"
COL_BARCODE     = "Variant Barcode"
COL_IMAGE       = "Image Src"
COL_IMAGE_ALT   = "Image Alt Text"
COL_SEO_TITLE   = "SEO Title"
COL_SEO_DESC    = "SEO Description"
COL_OPT1_NAME   = "Option1 Name"
COL_OPT1_VAL    = "Option1 Value"
COL_OPT2_NAME   = "Option2 Name"
COL_OPT2_VAL    = "Option2 Value"
COL_OPT3_NAME   = "Option3 Name"
COL_OPT3_VAL    = "Option3 Value"
COL_BARCODE2    = "Variant Barcode"

# Shopify metafield columns vary by store; we surface a few common useful ones.
# (Localized description metafields like the Swedish 'Beskrivning' are detected
#  dynamically below rather than hardcoded.)


# =============================================================================
# ENCODING + DELIMITER DETECTION
# =============================================================================

def _read_text(path: str) -> str:
    """Read the file as text, trying encodings in the order most likely to be
    lossless for a Shopify export. cp1252 decodes almost anything, so it is the
    safety net -- but we try the stricter UTF variants first to keep proper UTF-8
    stores intact."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # latin-1 can decode any byte, so we never reach here -- but be safe.
    return raw.decode("cp1252", errors="replace")


def _detect_delimiter(header_line: str) -> str:
    """Shopify exports are comma-delimited by default, but EU/localized exports
    are often semicolon-delimited. Decide by which produces the known 'Handle'
    first column and more recognised headers."""
    candidates = (",", ";", "\t")
    best, best_score = ",", -1
    for d in candidates:
        cells = [c.strip().strip('"') for c in header_line.split(d)]
        score = sum(1 for c in cells if c in (
            COL_HANDLE, COL_TITLE, COL_BODY, COL_VENDOR, COL_PRICE, COL_SKU, COL_IMAGE))
        if cells and cells[0] == COL_HANDLE:
            score += 5
        if score > best_score:
            best, best_score = d, score
    return best


# =============================================================================
# CLEANING HELPERS
# =============================================================================

_TAG_RE      = re.compile(r"<[^>]+>")
_WS_RE       = re.compile(r"[ \t\r\f\v]+")
_MULTINL_RE  = re.compile(r"\n{3,}")
_BARCODE_RE  = re.compile(r"[^0-9]")          # for stripping mojibake off barcodes


def strip_html(raw: str) -> str:
    """Shopify Body (HTML) -> clean readable text for Claude. Block tags become
    line breaks so list structure survives; inline tags vanish; entities decode."""
    if not raw:
        return ""
    text = raw
    # Turn common block boundaries into newlines before stripping tags.
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|ul|ol|section)\s*>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", " - ", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _MULTINL_RE.sub("\n\n", text)
    # tidy " - " bullets that ended up mid-line
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def clean_barcode(raw: str) -> str:
    """cp1252 decoding can prepend a stray glyph (seen as '?') to EAN/UPC values.
    Keep digits only; return '' if nothing usable remains."""
    if not raw:
        return ""
    digits = _BARCODE_RE.sub("", raw)
    # EAN-13 / UPC-A / EAN-8 lengths; anything else we still return as-is digits.
    return digits


def _price_float(raw: str):
    if not raw:
        return None
    m = re.sub(r"[^\d.]", "", str(raw).replace(",", "."))
    try:
        return round(float(m), 2) if m else None
    except ValueError:
        return None


# =============================================================================
# CORE: collapse rows into products
# =============================================================================

def _find_desc_metafield_keys(fieldnames) -> list:
    """Detect localized/custom description metafield columns (e.g. the Swedish
    'Beskrivning (product.metafields.custom.beskrivning)') so we can offer them
    as a secondary description source if Body (HTML) is thin."""
    keys = []
    for f in fieldnames or []:
        low = f.lower()
        if "metafields" in low and any(t in low for t in
                                       ("beskrivning", "description", "descripcion",
                                        "beschreibung", "body", "content")):
            keys.append(f)
    return keys


def load_shopify_products(
    path: str,
    include_statuses=("active", ""),     # "" = published rows with blank status
    require_price: bool = False,
) -> list:
    """
    Parse a Shopify product-export CSV into a list of product dicts.

    Each product dict:
      {
        "handle":        str,
        "title":         str,
        "vendor":        str,            # drives reseller per-vendor brand handling
        "category_path": str,            # Shopify "Product Category" (Google taxonomy)
        "product_type":  str,            # Shopify "Type"
        "tags":          [str, ...],
        "sku":           str,            # primary variant SKU
        "price":         float | None,
        "price_max":     float | None,   # for multi-variant range
        "compare_at":    float | None,
        "grams":         int | None,
        "barcode":       str,            # cleaned EAN/UPC
        "options":       {name: [values...]},   # variant axes
        "images":        [url, ...],     # parent + continuation, de-duped
        "image_alts":    [str, ...],
        "seo_title":     str,
        "seo_description": str,
        "body_text":     str,            # cleaned Body (HTML)
        "body_html":     str,            # raw, in case caller wants it
        "alt_description": str,          # best localized/custom description metafield
        "status":        str,

        # Convergence keys -- mirror the arbitrage comp_data so downstream code
        # (build_sheet_row, schema routing) treats both paths uniformly:
        "source":        "shopify",
        "attributes":    {},             # filled later from options/specs if needed
      }
    """
    text = _read_text(path)
    # Pull header line to detect delimiter.
    first_nl = text.find("\n")
    header_line = text[:first_nl] if first_nl != -1 else text
    delim = _detect_delimiter(header_line)

    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    fieldnames = reader.fieldnames or []
    desc_keys = _find_desc_metafield_keys(fieldnames)

    products = []          # ordered list
    by_handle = {}         # handle -> product dict (for attaching continuation rows)

    for raw_row in reader:
        handle = (raw_row.get(COL_HANDLE) or "").strip()
        if not handle:
            continue
        title = (raw_row.get(COL_TITLE) or "").strip()

        if title:
            # ---- PARENT ROW: new product -----------------------------------
            opts = {}
            for nkey, vkey in ((COL_OPT1_NAME, COL_OPT1_VAL),
                               (COL_OPT2_NAME, COL_OPT2_VAL),
                               (COL_OPT3_NAME, COL_OPT3_VAL)):
                oname = (raw_row.get(nkey) or "").strip()
                oval  = (raw_row.get(vkey) or "").strip()
                if oname and oname.lower() != "title" and oval and oval.lower() != "default title":
                    opts.setdefault(oname, [])
                    if oval not in opts[oname]:
                        opts[oname].append(oval)

            body_html = raw_row.get(COL_BODY) or ""
            body_text = strip_html(body_html)

            alt_desc = ""
            for dk in desc_keys:
                cand = strip_html(raw_row.get(dk) or "")
                if len(cand) > len(alt_desc):
                    alt_desc = cand

            price = _price_float(raw_row.get(COL_PRICE))
            grams_raw = re.sub(r"[^\d]", "", str(raw_row.get(COL_GRAMS) or ""))
            tags = [t.strip() for t in (raw_row.get(COL_TAGS) or "").split(",") if t.strip()]

            prod = {
                "handle":        handle,
                "title":         title,
                "vendor":        (raw_row.get(COL_VENDOR) or "").strip(),
                "category_path": (raw_row.get(COL_CATEGORY) or "").strip(),
                "product_type":  (raw_row.get(COL_TYPE) or "").strip(),
                "tags":          tags,
                "sku":           (raw_row.get(COL_SKU) or "").strip(),
                "price":         price,
                "price_max":     price,
                "compare_at":    _price_float(raw_row.get(COL_COMPARE)),
                "grams":         int(grams_raw) if grams_raw else None,
                "barcode":       clean_barcode(raw_row.get(COL_BARCODE)),
                "options":       opts,
                "images":        [],
                "image_alts":    [],
                "seo_title":     (raw_row.get(COL_SEO_TITLE) or "").strip(),
                "seo_description": (raw_row.get(COL_SEO_DESC) or "").strip(),
                "body_text":     body_text,
                "body_html":     body_html,
                "alt_description": alt_desc,
                "status":        (raw_row.get(COL_STATUS) or "").strip().lower(),
                "source":        "shopify",
                "attributes":    {},
            }
            _attach_image(prod, raw_row)
            products.append(prod)
            by_handle[handle] = prod
        else:
            # ---- CONTINUATION ROW: extra image and/or extra variant --------
            prod = by_handle.get(handle)
            if not prod:
                continue
            _attach_image(prod, raw_row)
            # extra variant price (multi-variant products): widen the range + opts
            vprice = _price_float(raw_row.get(COL_PRICE))
            if vprice is not None:
                if prod["price"] is None or vprice < prod["price"]:
                    prod["price"] = vprice
                if prod["price_max"] is None or vprice > prod["price_max"]:
                    prod["price_max"] = vprice
            for nkey, vkey in ((COL_OPT1_NAME, COL_OPT1_VAL),
                               (COL_OPT2_NAME, COL_OPT2_VAL),
                               (COL_OPT3_NAME, COL_OPT3_VAL)):
                oname = (raw_row.get(nkey) or "").strip()
                oval  = (raw_row.get(vkey) or "").strip()
                if oname and oname.lower() != "title" and oval and oval.lower() != "default title":
                    prod["options"].setdefault(oname, [])
                    if oval not in prod["options"][oname]:
                        prod["options"][oname].append(oval)

    # --- status filter -------------------------------------------------------
    if include_statuses is not None:
        allow = {s.lower() for s in include_statuses}
        products = [p for p in products if p["status"] in allow]
    if require_price:
        products = [p for p in products if p["price"] is not None]

    # --- per-product source-language tag (feeds the tone dropdown) -----------
    for p in products:
        src = p.get("body_text") or p.get("alt_description") or p.get("title") or ""
        code, conf = detect_language(src)
        p["source_lang"] = code
        p["source_lang_conf"] = conf

    return products


def _attach_image(prod: dict, raw_row: dict):
    img = (raw_row.get(COL_IMAGE) or "").strip()
    if img and img not in prod["images"]:
        prod["images"].append(img)
        prod["image_alts"].append((raw_row.get(COL_IMAGE_ALT) or "").strip())


# =============================================================================
# DIAGNOSTIC CLI
# =============================================================================

if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "products_export_all_products.csv"
    # By default show ALL statuses in the diagnostic so nothing looks "missing".
    prods = load_shopify_products(p, include_statuses=None)
    print(f"Parsed {len(prods)} products from {p}")
    by_status = {}
    by_vendor = {}
    for pr in prods:
        by_status[pr["status"]] = by_status.get(pr["status"], 0) + 1
        by_vendor[pr["vendor"]] = by_vendor.get(pr["vendor"], 0) + 1
    print("By status :", dict(sorted(by_status.items(), key=lambda x: -x[1])))
    print("Top vendors:", dict(sorted(by_vendor.items(), key=lambda x: -x[1])[:6]))
    catlang = detect_catalogue_language(prods)
    print(f"Source lang: dominant={catlang['name']} ({catlang['code']}), "
          f"english={catlang['is_english']}, breakdown={catlang['per_lang']}")
    if catlang["is_english"]:
        print("  -> Tone dropdown: English only")
    else:
        print(f"  -> Tone dropdown: [English (default)] [{catlang['name']}]")
    print()
    for pr in prods[:3]:
        print("=" * 64)
        print(f"  {pr['title']}")
        print(f"    vendor   : {pr['vendor']}")
        print(f"    type     : {pr['product_type']}   |   category: {pr['category_path']}")
        print(f"    sku      : {pr['sku']}   barcode: {pr['barcode']}   "
              f"price: {pr['price']}" + (f"-{pr['price_max']}" if pr['price_max'] != pr['price'] else ""))
        print(f"    options  : {pr['options'] or '(single variant)'}")
        print(f"    images   : {len(pr['images'])}")
        print(f"    body_text: {len(pr['body_text'])} chars | "
              f"alt_desc: {len(pr['alt_description'])} chars | "
              f"seo_title: {pr['seo_title'][:40]!r}")
        print(f"    preview  : {pr['body_text'][:160]!r}")
