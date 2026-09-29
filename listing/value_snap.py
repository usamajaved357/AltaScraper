"""listing/value_snap.py -- snapping values to what Amazon allows: field keys, value lists, spelling, dimensions, conditional enums.

Moved word for word out of amazon_listing_generator.py (Milestone 4, owner-approved 28 Sep 2026).
amazon_listing_generator.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import re


def _parse_field_key(field_id: str) -> str:
    return field_id.split("[")[0].split("#")[0].strip().lower()


# Field key alias map:
# Amazon uses different field ID names per product type in the Dropdown Lists tab.
# Each entry lists aliases to try in order so we never miss a valid dropdown list.
FIELD_KEY_ALIASES = {
    "size":                ["size", "item_size", "item_package_quantity",
                            "item_display_dimensions", "volume_capacity_name"],
    "color":               ["color", "color_name", "colour", "item_color_name",
                            "exterior_color_name", "color_map"],
    "material":            ["material", "material_type", "item_material_type",
                            "outer_material_type"],
    "target_gender":       ["target_gender", "department", "department_name"],
    "age_range":           ["age_range_description", "age_range", "age_range_name"],
    "condition_type":      ["condition_type", "condition"],
    "country_of_origin":   ["country_of_origin", "country_of_manufacture"],
    "product_tax_code":    ["product_tax_code"],
    "batteries_required":  ["batteries_required", "are_batteries_required"],
    "batteries_included":  ["batteries_included", "are_batteries_included"],
    "fulfillment_channel": ["fulfillment_availability#1.fulfillment_channel_code",
                            "fulfillment_channel_code"],
}


def _smart_vlist(field_name: str, valid_values: dict) -> list:
    """Try all aliases for a field name, return first non-empty list found."""
    for alias in FIELD_KEY_ALIASES.get(field_name, [field_name]):
        result = valid_values.get(alias, [])
        if result:
            return result
    return []


def merge_static_into_runtime(runtime_vv: dict, static_vv: dict) -> dict:
    """
    Overlay static valid-values on top of runtime-loaded ones.
    For each product type covered by static_vv, replace the runtime values
    so the script uses Amazon-published enumerations as the source of truth.
    Product types only present in runtime_vv are preserved (they may exist
    in the Google Sheet template but not in our two XLSM files).
    """
    if not static_vv:
        return runtime_vv
    merged = dict(runtime_vv) if runtime_vv else {}
    for pt, attrs in static_vv.items():
        if pt not in merged:
            merged[pt] = {}
        for attr, values in attrs.items():
            merged[pt][attr] = list(values)  # static wins
    return merged


# BRITISH AND AMERICAN SPELLINGS OF THE SAME WORD. Amazon's UK lists say
# Aluminium, Microfibre, Grey and Colour; the AI and eBay's sellers write them
# either way. Comparing the raw strings makes those a miss, and a miss here
# means the value goes to Amazon unsnapped.
_SPELLING = (("fibre", "fiber"), ("metre", "meter"), ("litre", "liter"),
             ("colour", "color"), ("aluminium", "aluminum"), ("grey", "gray"),
             ("centre", "center"), ("mould", "mold"), ("jewellery", "jewelry"))


def _spell(s: str) -> str:
    out = str(s or "").lower()
    for uk, us in _SPELLING:
        out = out.replace(uk, us)
    return out


def snap_to_valid(value: str, valid_list: list) -> str:
    """Fuzzy match to Amazon's exact valid dropdown value."""
    if not value or not valid_list:
        return ""
    v = value.strip()
    if v in valid_list:
        return v
    v_lower = v.lower()
    for item in valid_list:
        if item.lower() == v_lower:
            return item
    # Same word, other side of the Atlantic.
    v_sp = _spell(v_lower)
    for item in valid_list:
        if _spell(item) == v_sp:
            return item
    # SUBSTRING MATCHING NEEDS SOMETHING TO MATCH ON. With no length guard,
    # "a" matched "Acrylic" and "s" matched "Steel" -- a single character
    # snapping to whichever option happened to contain it. Exact and
    # case-insensitive matching above still catch legitimately short values
    # like the sizes S, M and L, which is why the guard is only here.
    if len(v_lower) >= 3:
        for item in valid_list:
            if item.lower() in v_lower:
                return item
        for item in valid_list:
            if v_lower in item.lower():
                return item
    v_words   = set(v_lower.split())
    best, best_score = "", 0
    for item in valid_list:
        score = len(v_words & set(item.lower().split()))
        if score > best_score:
            best_score, best = score, item
    if best_score >= 1:
        return best
    # THE SAME WORD IN ANOTHER FORM. 'Rectangle' and Amazon's 'Rectangular'
    # share no whole word and neither contains the other, so every strategy
    # above misses -- and it was one of the values sitting unmatched on a real
    # draft. Six characters is enough to make it the same word and short enough
    # to still be a word; anything looser starts matching 'Round' to 'Rounded
    # Corner Something'.
    if len(v_sp) >= 6:
        for item in valid_list:
            i_sp = _spell(item)
            if len(i_sp) >= 6 and i_sp[:6] == v_sp[:6]:
                return item
    # LAST RESORT: AN INITIALISM. Amazon spells its materials out in full, and
    # the trade does not: 'ABS' is Acrylonitrile Butadiene Styrene, 'MDF' is
    # Medium Density Fibreboard, 'PVC' is Polyvinyl Chloride. Found on real
    # drafts, where 'ABS' matched nothing and was sent as-is.
    #
    # Deliberately strict: 2-5 letters, no spaces, and the initials of a
    # MULTI-word option must match exactly. Anything looser starts matching
    # short words to unrelated options.
    if 2 <= len(v) <= 5 and v.isalpha():
        for item in valid_list:
            parts = str(item).split()
            if len(parts) < 2:
                continue
            if "".join(p[0] for p in parts).lower() == v_lower:
                return item
    return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", " ",   html, flags=re.IGNORECASE)
    text = re.sub(r"<li>",      " - ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>",  "",    text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_days(row: dict) -> str:
    days = str(row.get("Handling Days", "")).strip()
    if days.isdigit():
        return days
    nums = re.findall(r"\d+", str(row.get("Handling Time", "")))
    return nums[0] if nums else "3"


# Normalises a measurement unit to the EXACT string Amazon accepts (its unit
# dropdowns are case-sensitive: "kilograms" is REJECTED, "Kilograms" is accepted).
# Amazon's catalogue dimensions block returns lowercase forms, so we must map up.
_DIM_UNIT_NORM = {
    "cm": "Centimeters", "cms": "Centimeters", "centimeter": "Centimeters",
    "centimetre": "Centimeters", "centimetres": "Centimeters", "centimeters": "Centimeters",
    "mm": "Millimeters", "millimeter": "Millimeters", "millimetre": "Millimeters",
    "millimetres": "Millimeters", "millimeters": "Millimeters",
    "m": "Meters", "meter": "Meters", "metre": "Meters", "metres": "Meters", "meters": "Meters",
    "in": "Inches", "ins": "Inches", "inch": "Inches", "inches": "Inches", '"': "Inches",
    "ft": "Feet", "foot": "Feet", "feet": "Feet",
    "g": "Grams", "gm": "Grams", "gms": "Grams", "gram": "Grams", "grams": "Grams",
    "kg": "Kilograms", "kgs": "Kilograms", "kilogram": "Kilograms", "kilograms": "Kilograms",
    "lb": "Pounds", "lbs": "Pounds", "pound": "Pounds", "pounds": "Pounds",
    "oz": "Ounces", "ounce": "Ounces", "ounces": "Ounces",
    "mg": "Milligrams", "milligram": "Milligrams", "milligrams": "Milligrams",
}


def _norm_dim_unit(raw: str) -> str:
    u = str(raw or "").strip().lower().rstrip(".")
    if not u:
        return ""
    u = u.split()[0]                          # "centimeters (cm)" -> "centimeters"
    return _DIM_UNIT_NORM.get(u, u)


def _dim_number(raw) -> str:
    """A physical measurement, written the way a person writes one.

    Amazon's catalogue returns dimensions already converted, so the numbers
    arrive with the full error of that conversion:

        item_length  9.842519675 inches      (25 cm)
        item_height  157.48 inches           (4 m)
        item_width   13.779527545 inches     (35 cm)

    Nine decimal places on the width of a squeegee is not precision, it is
    float noise -- and it is shown to buyers and to whoever is checking the
    draft. Reported as "some data is put in there which do not make any sense".

    Two decimals, with pointless trailing zeros removed -- but NEVER below one
    decimal place, because Amazon rejects a whole number here:

        item_dimensions_fraction  Value '10.' for attribute 'Overall Height
        Derived' has too few decimal places. It has 0 decimal places but the
        minimum allowed is '1'.

    That message is off a real listing, and it is why this returns "35.0" and
    not "35". It also shows what a badly-trimmed number looks like when it
    reaches Amazon -- "10." is a trailing dot with nothing after it, which is
    what stripping zeros without then handling the dot produces.

    Anything that is not a number is handed back untouched rather than mangled.
    """
    s = str(raw if raw is not None else "").strip()
    if not s:
        return ""
    try:
        n = float(s)
    except (TypeError, ValueError):
        return s
    out = "%.2f" % n
    # 9.84 stays; 35.00 becomes 35.0; never 35, and never a bare "35."
    if out.endswith("0") and not out.endswith(".00"):
        out = out[:-1]
    elif out.endswith(".00"):
        out = out[:-2] + "0"
    return out


def _merge_conditional_enums(props: dict, raw: dict) -> dict:
    """Amazon hides many fields' REAL allowed values inside conditional branches
    (allOf / anyOf / oneOf / if-then-else) of the schema, NOT in top-level
    `properties`. The loader used to read only `properties`, so such fields looked
    like free-text (e.g. battery_installation_device_type) even though Amazon
    validates them server-side. This walks the WHOLE schema, collects every enum
    found for each field across ALL branches, and injects the union into
    props[field] so the rest of the app (dropdowns, snapping, hints) sees the real
    list. Purely additive: existing enums are preserved; we only fill gaps/extend.
    """
    # 1) gather: field_name -> set of allowed values (from anywhere in the doc)
    found = {}   # field -> list (order-preserving)

    def _add(field, values):
        if not values:
            return
        bucket = found.setdefault(field, [])
        for v in values:
            sv = str(v)
            if sv not in bucket:
                bucket.append(sv)

    def _enum_under_value(node):
        """Given a field-definition node, return enum at items.properties.value.enum
        (and a few variants), searching simple anyOf wrappers too."""
        out = []
        if not isinstance(node, dict):
            return out
        it = node.get("items", {})
        ip = it.get("properties", {}) if isinstance(it, dict) else {}
        vp = ip.get("value", {}) if isinstance(ip, dict) else {}
        # direct
        if isinstance(vp, dict) and isinstance(vp.get("enum"), list):
            out += vp["enum"]
        # anyOf/oneOf wrappers around value
        for key in ("anyOf", "oneOf", "allOf"):
            for sub in (vp.get(key) or []) if isinstance(vp, dict) else []:
                if isinstance(sub, dict) and isinstance(sub.get("enum"), list):
                    out += sub["enum"]
        # some defs put enum straight on items or the node
        if isinstance(it, dict) and isinstance(it.get("enum"), list):
            out += it["enum"]
        if isinstance(node.get("enum"), list):
            out += node["enum"]
        return out

    def _walk(node):
        if isinstance(node, dict):
            # if this dict is a `properties` map, each key is a field name
            props_map = node.get("properties")
            if isinstance(props_map, dict):
                for fname, fdef in props_map.items():
                    vals = _enum_under_value(fdef)
                    if vals:
                        _add(fname, vals)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(raw)

    # 2) inject: ensure props[field] carries the discovered enum at the standard
    #    location the rest of the app reads (items.properties.value.enum).
    for field, values in found.items():
        if not values:
            continue
        cur = props.get(field)
        if not isinstance(cur, dict):
            cur = {}
        it = cur.setdefault("items", {})
        if not isinstance(it, dict):
            it = {}; cur["items"] = it
        ip = it.setdefault("properties", {})
        if not isinstance(ip, dict):
            ip = {}; it["properties"] = ip
        vp = ip.setdefault("value", {})
        if not isinstance(vp, dict):
            vp = {}; ip["value"] = vp
        existing = vp.get("enum")
        if isinstance(existing, list) and existing:
            # extend without dupes (existing wins ordering)
            merged = list(existing)
            for v in values:
                if v not in merged:
                    merged.append(v)
            vp["enum"] = merged
        else:
            vp["enum"] = values
        props[field] = cur
    return props


def _dim_axis_raw(parent, axis, flat):
    """Return one dimension axis as a 'value unit' string for _shape_dimensions.

    Reads the NESTED item_dimensions[axis] object the EDITOR actually saves (each axis is
    {value, unit}, rebuilt by _renest) FIRST, and falls back to the legacy FLAT item_<axis>
    key only when the nested axis is absent or blank. Before this, the builder read the flat
    keys only, so any axis present just in nested form (commonly width/height) was silently
    dropped -- and Amazon rejected the listing as 'height/width missing'."""
    node = parent.get(axis) if isinstance(parent, dict) else None
    if isinstance(node, dict):
        val = node.get("value", node.get("decimal_value", ""))
        if str(val).strip() != "":
            unit = str(node.get("unit", "")).strip()
            return (str(val).strip() + " " + unit).strip()
    elif node not in (None, ""):
        return str(node)
    return flat
