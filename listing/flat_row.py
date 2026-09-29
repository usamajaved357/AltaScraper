"""listing/flat_row.py -- building a flat-file row: SKU and model numbers, financials, the account's brand, column maps, the row gate.

Moved word for word out of amazon_listing_generator.py (Milestone 4, owner-approved 28 Sep 2026).
amazon_listing_generator.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import re
from listing.builder import _clean_price
from listing.hazmat import _has_battery
import json
from listing.barcode import normalize_gtin, gtin_or_reason, gtin_digits   # single source of barcode truth
from listing.product_type_rules import derive_product_type_code
from listing.value_snap import _clean_days, _norm_dim_unit, _smart_vlist, _strip_html, snap_to_valid


MIN_MARGIN     = 20.0


def calculate_financials(source_cost: float, selling_price: float,
                          shipping_cost: float, fees: dict) -> dict:
    total_costs = round(source_cost + shipping_cost + fees["total_amazon_fees"], 2)
    profit      = round(selling_price - total_costs, 2)
    margin      = round((profit / selling_price) * 100, 1) if selling_price > 0 else 0
    roi         = round((profit / source_cost)    * 100, 1) if source_cost  > 0 else 0
    return {
        "source_cost":       source_cost,
        "shipping_cost":     shipping_cost,
        "referral_fee":      fees["referral_fee"],
        "variable_closing":  fees["variable_closing"],
        "total_amazon_fees": fees["total_amazon_fees"],
        "total_costs":       total_costs,
        "selling_price":     selling_price,
        "profit":            profit,
        "margin_pct":        f"{margin}%",
        "roi_pct":           f"{roi}%",
        "viable":            "YES" if margin >= MIN_MARGIN else "LOW MARGIN",
        "fee_source":        fees["fee_source"],
    }


def build_sku(source_cost: float, handling_days: str, comp_asin: str,
              taken_skus: set) -> tuple:
    """
    SKU format: {source_price}_{N}Days_{COMP_ASIN}
    e.g. 7.99_3Days_B0XYZ12345
    If the resulting SKU is already taken in this run or previous runs,
    append _2, _3, etc. Returns (sku, was_duplicate).
    """
    price_part = f"{source_cost:.2f}" if source_cost > 0 else "0.00"
    days_part  = f"{handling_days}Days" if handling_days else "3Days"
    base       = f"{price_part}_{days_part}_{comp_asin}"
    if base not in taken_skus:
        return base, False
    n = 2
    while f"{base}_{n}" in taken_skus:
        n += 1
    return f"{base}_{n}", True


def next_model_number(brand: str, product_type: str, counter: dict) -> str:
    """Generate model number: {first 4 of brand}-{3-letter category code}-{seq:03d}.
    Mutates the counter dict in place. Caller is responsible for saving."""
    prefix = re.sub(r"[^A-Za-z0-9]", "", brand or "Unb")[:4].title() or "Unbr"
    code   = derive_product_type_code(product_type)
    key    = f"{prefix}-{code}"
    counter[key] = counter.get(key, 0) + 1
    return f"{prefix}-{code}-{counter[key]:03d}"


def is_model_number_required(schema: dict) -> bool:
    """True iff schema marks any of model_number / model / part_number as required."""
    required = schema.get("required", {}) or {}
    for field in ("model_number", "model", "part_number"):
        if field in required:
            return True
    return False


def resolve_account_brand(row_brand, config):
    """(brand_to_send, note) -- THE one place that decides whose brand goes out.

    A listing must go out under THIS ACCOUNT'S OWN TRADEMARK. The Brand column
    is trusted only when it names one of the account's registered brands
    (accounts can have several); anything else is a stale or leaked value and
    the account's primary trademark is used instead. It is NEVER
    config["brand_name"] when an account is resolved -- that global is exactly
    how one account's brand once ended up on another's listings.

    A BRAND SWAP IS NEVER SILENT, and that is what this exists for:

        "I am trying to put the brand name as AltaboltaVoo while creating a new
         listing on Nestwell Goods account, my nestwell goods account has that
         brand name approved in the seller central ... but the app says
         'Amazon flagged this - review the value'"

    Measured: nestwell_goods is configured with brands ['Nestwell Goods'].
    Typing AltaboltaVoo was REPLACED with 'Nestwell Goods' without a word, so
    the listing went out under a brand nobody chose and the only clue was a
    generic flag on a field the editor would not let you fix.

    The guard stays -- one account's trademark on another's listing is the worse
    fault. But the app cannot know which brands Amazon approved for an account;
    only the owner knows, and the account's Brands list is where they say so. So
    the swap is ANNOUNCED, with the exact thing to do about it.

    ...AND THE SWAP IS GONE. IT REPORTS NOW, AND SENDS WHAT WAS TYPED.

        "please do not force the listing to use the brand name from the
         approved or added brand list just allow the types brand name to go to
         amazon if there is a typo or some error amazon will reveal in preview"

    He is right, and the argument is Amazon's own enforcement. A brand this
    account does not own CANNOT be used to create a listing: Amazon refuses it
    with code 100550, "You need to connect your brand X with your account to
    create new ASINs with this brand", and hands back the Manage Your Brands
    link. So the worst case the substitution was written to prevent -- one
    account's trademark on another's listing -- is a case Amazon already blocks,
    at the only place that actually knows which brands are approved.

    And the substitution had its own cost, in his words the first time:

        "Typing AltaboltaVoo was REPLACED with 'Nestwell Goods' without a word"

    Replacing it did not make the listing correct. It made it go out under a
    brand nobody chose, and hid the thing that needed fixing.

    THE APP CANNOT KNOW WHICH BRANDS AMAZON APPROVED, and this is not a gap that
    can be closed: Amazon's own documentation says SP-API "doesn't provide
    information about intellectual property restrictions for new products or
    details about gated brands". There is no endpoint to read the list and none
    to apply. So the account's Brands list is a note the owner keeps for himself
    -- useful for spotting a stale value, and never authoritative enough to
    overrule what he typed.

    THE NOTE STAYS. A brand that is not on the account's list is still worth
    saying out loud, because a leaked or stale value looks exactly like a
    deliberate one. What changed is that it is now a remark about a value being
    sent, not an announcement of a value being changed.

    ONE COPY, used by build_api_attributes and by the submit guard (rule 12).
    They disagreed about nothing, but two copies of "whose brand is this" is one
    more than a listing can safely have.
    """
    brand = str(row_brand or "").strip()
    acct = [str(x).strip() for x in (config.get("_account_brands") or [])
            if str(x).strip()]
    if acct:
        if brand and brand not in acct:
            return brand, (
                "Brand: the row says %r, which is not one of this account's "
                "listed brands (%s). Sending it as typed — Amazon decides which "
                "brands this account may use, and refuses with code 100550 if "
                "it is not linked. If %r is right, add it to the account's "
                "Brands list so this note stops; if it is not, change it on the "
                "row." % (brand, ", ".join(acct), brand))
        # Typed and recognised, or nothing typed -- then the account's primary,
        # which is the only case left where the app supplies a brand at all.
        return (brand or acct[0]), ""
    if config.get("_account_brand") is not None:
        # Account resolved and no trademark listed. A TYPED brand still goes --
        # the list is the owner's own note, not Amazon's permission, and an
        # empty list is far more likely to mean he has not filled it in than
        # that he owns no brands. Only a row with no brand at all sends none,
        # because there is then nothing to send and nothing to borrow.
        if brand:
            return brand, (
                "Brand: sending %r as typed. This account has no brands listed "
                "in its settings, so nothing here could confirm it — Amazon "
                "will, and refuses with code 100550 if the brand is not linked "
                "to the account." % brand)
        return "", ""
    return (brand or config.get("brand_name", "")), ""   # legacy / no account


# Safety & compliance attribute keys whose values are taken verbatim from the
# live SP-API schema enum (injected into the generation prompt). These are
# written to the flat file WITHOUT fuzzy snapping, because the static
# valid-values lists for these columns are frequently incomplete and snapping
# would blank a correct "No"/"Not Applicable" answer or match the wrong option.
_COMPLIANCE_PASSTHROUGH = {
    "supplier_declared_dg_hz_regulation",
    "contains_liquid_contents",
    "ghs",
    "ghs_classification_class",
    "hazmat",
    "batteries_required",
    "batteries_included",
    "supplier_declared_material_regulation",
    "pesticide_marking",
    "california_proposition_65_compliance_type",
}


def build_flat_row(sheet_row: dict, brand: str, manufacturer: str,
                   cols_map: dict, valid_values: dict,
                   product_type: str, browse_node: str,
                   shipping_group: str = "") -> list:
    total    = cols_map["TOTAL_COLS"]
    out      = [""] * total
    title    = str(sheet_row.get("Title",                ""))[:200]
    upc      = str(sheet_row.get("UPC",                  "")).strip()
    asin     = str(sheet_row.get("Competitor ASIN",      "")).strip()
    sku      = str(sheet_row.get("SKU",                  "")).strip()
    price    = _clean_price(sheet_row.get("Our Price (GBP)", ""))
    desc     = _strip_html(str(sheet_row.get("Description (HTML)", "")))[:2000]
    keywords = str(sheet_row.get("Search Terms / KW",    ""))[:249]
    handling = _clean_days(sheet_row)
    battery  = _has_battery(sheet_row)

    def vv(field_name: str) -> list:
        return _smart_vlist(field_name, valid_values)

    # Constrained fields -- all snapped from live dropdown lists
    material = snap_to_valid(
        str(sheet_row.get("Material", "")).split(",")[0].strip().replace("N/A", ""),
        vv("material"))

    colour_raw = str(sheet_row.get("Colour", "")).replace("N/A", "")
    colour     = snap_to_valid(colour_raw, vv("color")) if vv("color") else colour_raw

    size_raw = str(sheet_row.get("Size", "")).replace("N/A", "")
    # Leave blank when no valid list -- raw values fail dropdown validation
    size     = snap_to_valid(size_raw, vv("size")) if vv("size") else ""

    gender   = snap_to_valid(
        str(sheet_row.get("Target Gender", "Unisex")).replace("N/A", "Unisex"),
        vv("target_gender")) or "Unisex"

    age      = snap_to_valid(
        str(sheet_row.get("Age Range", "Adult")).replace("N/A", "Adult"),
        vv("age_range")) or "Adult"

    condition = snap_to_valid("New",         vv("condition_type"))     or "New"
    fulfill   = snap_to_valid("DEFAULT",     vv("fulfillment_channel")) or "DEFAULT"
    country   = snap_to_valid("China",       vv("country_of_origin"))  or "China"
    batt_yes  = snap_to_valid("Yes",         vv("batteries_required")) or "Yes"
    batt_no   = snap_to_valid("No",          vv("batteries_required")) or "No"
    tax_code  = snap_to_valid("A_GEN_NOTAX", vv("product_tax_code"))   or "A_GEN_NOTAX"

    # Product Id: real barcode if the sheet provides one, else BLANK (GTIN-exempt).
    # Never write the competitor's ASIN -- you cannot list a new product under it.
    # normalize_gtin is the ONE place that decides this (listing/barcode.py):
    # it strips separators and unwraps a 14-digit GTIN back to the EAN-13 it is.
    # Empty type -> no usable barcode -> leave blank; needs GTIN exemption.
    prod_id, _pid_type = normalize_gtin(upc)
    prod_id_type       = _pid_type.upper()

    # Per-row brand from sheet wins; fall back to the export-level default.
    row_brand        = str(sheet_row.get("Brand", "")).strip()
    effective_brand  = row_brand or brand
    # Per-row model number: blank means category does not require it.
    row_model_number = str(sheet_row.get("Model Number", "")).strip()

    # Title must NOT lead with the brand -- strip it from the start if present
    # (covers rows already generated under the old brand-first prompt).
    title_clean = title
    _bn = effective_brand.strip()
    if _bn and title_clean.lower().startswith(_bn.lower()):
        title_clean = title_clean[len(_bn):].lstrip(" -\u2013\u2014:|,").strip()

    def s(key: str, val):
        idx = cols_map.get(key)
        if idx is not None and idx < total:
            out[idx] = str(val) if val is not None else ""

    s("SKU",                           sku)
    s("Product Type",                  product_type)
    s("Listing Action",                "Create or Replace (Full Update)")
    s("Item Name",                     title_clean)
    s("Brand Name",                    effective_brand)
    s("Product Id Type",               prod_id_type)
    s("Product Id",                    prod_id)
    s("Browse Node 1",                 browse_node)
    if row_model_number:
        s("Model Number",              row_model_number)
        s("model_name",                row_model_number)   # own-brand: mirror model number
        s("part_number",               row_model_number)
    s("Manufacturer",                  manufacturer)
    s("Product Description",           desc)
    s("Bullet Point 1",                str(sheet_row.get("Bullet 1", ""))[:500])
    s("Bullet Point 2",                str(sheet_row.get("Bullet 2", ""))[:500])
    s("Bullet Point 3",                str(sheet_row.get("Bullet 3", ""))[:500])
    s("Bullet Point 4",                str(sheet_row.get("Bullet 4", ""))[:500])
    s("Bullet Point 5",                str(sheet_row.get("Bullet 5", ""))[:500])
    s("Generic Keyword",               keywords)
    s("Material",                      material)
    s("Colour",                        colour)
    s("Size",                          size)
    s("Number of Items",               str(sheet_row.get("Number of Items", "1")) or "1")
    s("Target Gender",                 gender)
    s("Age Range Description",         age)
    s("Item Condition",                condition)
    s("List Price with Tax",           price)
    s("Product Tax Code",              tax_code)
    s("Fulfillment Channel Code (UK)", fulfill)
    s("Quantity (UK)",                 "99")
    s("Handling Time (UK)",            handling)
    s("Your Price GBP",                price)
    s("Country of Origin",             country)
    s("Are batteries required?",       batt_yes if battery else batt_no)
    s("Are batteries included?",       batt_yes if battery else batt_no)
    if shipping_group:
        s("merchant_shipping_group",   shipping_group)

    # --- Pillars 3-4: map the full attribute object generated for this product --
    # Reads the "Attributes JSON" column. Enumerated values are snapped to Amazon's
    # accepted strings (left BLANK if no clean match -- never writes an invalid enum
    # or "N/A" into a dropdown). Free-text values are written as-is. Skips fields
    # already written above so we never double-write.
    _already = {"material", "color", "colour", "size", "number_of_items",
                "country_of_origin", "item_condition", "item_type_keyword",
                "item_length", "item_width", "item_height", "item_depth",
                "item_weight", "length", "width", "height", "depth", "weight",
                "item_package_length", "item_package_width", "item_package_height",
                "item_package_weight", "package_length", "package_width",
                "package_height", "package_weight"}
    try:
        _gen = json.loads(str(sheet_row.get("Attributes JSON", "") or "{}"))
    except Exception:
        _gen = {}
    if isinstance(_gen, dict):
        for _ak, _av in _gen.items():
            _akl = str(_ak).strip().lower()
            if _akl in _already or _av is None or str(_av).strip() == "":
                continue
            if _akl not in cols_map:
                continue                      # template has no column for this attribute
            # Safety & compliance fields: their value comes from the live SP-API
            # schema enum injected into the generation prompt, so it is already a
            # valid Amazon string. Write it directly -- snapping it against the
            # (sometimes incomplete) static valid-values list would wrongly blank
            # a correct answer like "No" or "Not Applicable", or fuzzy-match it to
            # the wrong option (e.g. "Not Applicable" -> "GHS").
            if _akl in _COMPLIANCE_PASSTHROUGH:
                s(_akl, str(_av).strip()[:120])
                continue
            _vlist = vv(_akl)
            if _vlist:                        # enumerated: snap; blank if no clean match
                _snapped = snap_to_valid(str(_av).replace("N/A", "").strip(), _vlist)
                if _snapped:
                    s(_akl, _snapped)
            else:                             # free-text: write value, or N/A (accepted as text)
                _clean = str(_av).strip()
                if _clean:
                    s(_akl, _clean[:500])

    # --- Dimensions: fill a field-GROUP only when every axis it needs has a value.
    # Amazon errors on a partially filled group (e.g. depth/width/height with depth
    # missing), so we gather the measurements we actually have, then for each
    # template group write it ONLY if all its required axes are covered. Item and
    # package scopes are independent.
    _dim_groups = cols_map.get("_DIM_GROUPS") or {}

    def _split_dim(_raw):
        m = re.match(r"\s*(-?[\d.]+)\s*(.*)$", str(_raw).strip())
        if not m:
            return None, None
        return m.group(1).rstrip("."), _norm_dim_unit(m.group(2))

    _have = {"item": {}, "package": {}}       # scope -> axis -> (value, unit)
    _DIM_SOURCES = (
        ("item",    "height", ("item_height", "height")),
        ("item",    "length", ("item_length", "length")),
        ("item",    "width",  ("item_width", "width")),
        ("item",    "depth",  ("item_depth", "depth")),
        ("item",    "weight", ("item_weight", "weight")),
        ("package", "height", ("item_package_height", "package_height")),
        ("package", "length", ("item_package_length", "package_length")),
        ("package", "width",  ("item_package_width", "package_width")),
        ("package", "weight", ("item_package_weight", "package_weight")),
    )
    for _scope, _axis, _src_keys in _DIM_SOURCES:
        for _sk in _src_keys:
            _raw = _gen.get(_sk)
            if _raw and str(_raw).strip():
                _v, _u = _split_dim(_raw)
                if _v is not None:
                    _have[_scope][_axis] = (_v, _u)
                break

    for _scope, _groups in _dim_groups.items():
        for _gkey, _axes in _groups.items():
            _need = [a for a, slots in _axes.items() if slots.get("value")]
            if not _need or not all(a in _have[_scope] for a in _need):
                continue                      # incomplete group -> leave blank
            for _a in _need:
                _v, _u = _have[_scope][_a]
                for _ci in _axes[_a].get("value", []):
                    if not out[_ci]:
                        out[_ci] = _v
                if _u:
                    for _ci in _axes[_a].get("unit", []):
                        if not out[_ci]:
                            out[_ci] = _u

    # --- Compliance safety net: these are near-universal for ordinary retail
    # goods and Amazon BLOCKS the listing when a required one is missing. If the
    # generation step didn't emit them, write the safe default so we never ship a
    # row that fails on an empty compliance dropdown.
    for _ck, _default in (("supplier_declared_dg_hz_regulation", "Not Applicable"),
                          ("contains_liquid_contents", "No")):
        _ci = cols_map.get(_ck)
        if _ci is not None and not out[_ci]:
            out[_ci] = _default

    return out


# Always written even if the product-type schema omits them (offer/control/
# identity/image fields the schema skips or that the template needs structurally).
_ALWAYS_WRITE_TOKENS = (
    "contribution_sku", "record_action", "product_type", "parent_sku",
    "child_parent_sku_relationship", "variation_theme", "purchasable_offer",
    "list_price", "fulfillment_availability", "merchant_shipping_group",
    "product_tax_code", "image_locator", "product_id", "condition_type",
)


def build_col_attr_map(template_path: str) -> dict:
    """1-based column index -> base attribute key (text before '[' or '#'),
    read from the template's field-ID row (row 5). Used by the schema gate."""
    import openpyxl
    # NOT read_only -- see the same note in domain/unified_export.build_field_map.
    # A read-only sheet takes max_column from the extent the FILE declares, and
    # Amazon's generated workbooks have been measured declaring a rectangle far
    # smaller than their contents. Understating it here would map only the first
    # few field IDs, so the schema gate below would stop checking most of the
    # row. That fails OPEN (an unmapped column is never cleared), which is why
    # nothing has ever looked wrong.
    wb = openpyxl.load_workbook(template_path, keep_vba=True)
    ws = wb["Template"] if "Template" in wb.sheetnames else wb[wb.sheetnames[0]]
    out = {}
    for c in range(1, ws.max_column + 1):
        fid = ws.cell(row=5, column=c).value
        if fid:
            out[c] = re.split(r"[\[#]", str(fid))[0].strip().lower()
    wb.close()
    return out


def gate_built_row(built_row: list, col_attr_map: dict, applicable: set) -> int:
    """Clear cells whose attribute is NOT in the product type's schema, so grey/
    not-applicable template fields never get filled. Fail-open: if `applicable`
    is empty (schema fetch failed) nothing is cleared -- we never silently drop
    data, worst case is the old behaviour. Returns count of cells cleared."""
    if not applicable:
        return 0
    cleared = 0
    for c, attr in col_attr_map.items():
        i = c - 1
        if i >= len(built_row) or built_row[i] in (None, ""):
            continue
        if any(tok in attr for tok in _ALWAYS_WRITE_TOKENS):
            continue
        if attr not in applicable:
            built_row[i] = ""
            cleared += 1
    return cleared
