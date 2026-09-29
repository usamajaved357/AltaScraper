"""listing/attributes_phases.py -- ordered phases of build_api_attributes.

Plans B3-B5 (docs/plans/build-api-attributes.md): the text/offer, the
dimension, the pa-mapping, the required-field backfill and the compliance phases, MOVED VERBATIM out of amazon_listing_generator.build_api_attributes and
called from it in the same place, in the same order. Every Amazon payload must
stay byte-identical: test_build_api_attributes_golden.py (100 golden payloads)
is the proof.

Each phase takes what it used to read from the enclosing function as
arguments -- the attributes dict `A` being built, the row accessor `g`, the
schema test `has`, the `put` writer, the parsed attributes `pa` (mutated in
place exactly as before), `props`, `config`, the marketplace id `mid` and the
engine's `console` -- so no line of the moved code changed. Nothing here
imports the engine (it runs as __main__; importing it loads a second copy).
"""
import re

from listing.attributes_helpers import (_allowed_values, _cbc_value, _enum_of_prop,
                                        _has_real_number, _valid_text_attr, _watt_number)
from listing.builder import _clean_price, _fulfillment, _is_blank, _item_props, _offer, _truthy
from listing.compliance import apply_compliance_safe_defaults
from listing.constants import US_MARKETPLACE_ID
from listing.flat_row import _COMPLIANCE_PASSTHROUGH, resolve_account_brand
from listing.hazmat import _build_ghs_from_schema
from listing.shaper import _lang_for, _shape_dimensions, _shape_simple, shape_by_schema
from listing.value_snap import _dim_axis_raw, snap_to_valid


def phase_text_offer(A, row, props, pa, config, mid, g, has, put, console):
    """Title, bullets, description, keywords, brand, condition, manufacturer /
    model / part, offer and fulfilment. -> the cleaned price (read later by the
    list_price step)."""
    # --- title / bullets / description / keywords (localised text) -----------
    if has("item_name") and g("Title"):
        put("item_name", _shape_simple(props["item_name"], g("Title"), mid))

    if has("bullet_point"):
        bl = []
        for i in range(1, 6):
            b = g(f"Bullet {i}")
            if b:
                bl += _shape_simple(props["bullet_point"], b, mid)
        if bl:
            A["bullet_point"] = bl

    if has("product_description") and g("Description (HTML)"):
        desc = re.sub(r"<[^>]+>", " ", g("Description (HTML)"))
        desc = re.sub(r"\s+", " ", desc).strip()
        put("product_description", _shape_simple(props["product_description"], desc, mid))

    if has("generic_keyword") and g("Search Terms / KW"):
        put("generic_keyword", _shape_simple(props["generic_keyword"], g("Search Terms / KW"), mid))

    # --- brand / condition ----------------------------------------------------
    # Brand = the ACCOUNT'S OWN TRADEMARK, which is the authority. Trust the Brand
    # column only when it is one of THIS account's registered brands (supports
    # multi-brand accounts); otherwise the column holds a stale/leaked value -> use
    # the account's primary trademark. NEVER the global config["brand_name"] -- that
    # leak is exactly how one account's brand ended up on another's listings.
    brand, _brand_note = resolve_account_brand(g("Brand"), config)
    if _brand_note:
        console.print("  [yellow]%s[/yellow]" % _brand_note)
    if has("brand") and brand:
        put("brand", _shape_simple(props["brand"], brand, mid))
    if has("condition_type"):
        put("condition_type", _shape_simple(props["condition_type"], "new_new", mid))

    # --- manufacturer / model / part (required by many types) -----------------
    # Prefer a real value scraped from the competitor; otherwise the generated model
    # number from the "Model Number" column.
    #
    # It used to fall back to the SKU. Our SKU is price_handlingdays_competitorASIN
    # (e.g. "12.74_2Days_B00IE769RO"), so listings went live on Amazon with that string
    # published as their Model Number and Part Number -- exposing our pricing, handling
    # time and the competitor's ASIN on the public product page. Never publish the SKU
    # as product data. If we have no real model number, omit the field: it is only
    # written when the schema exposes it, and Amazon reports it as missing if required,
    # which is a fixable error rather than permanently-wrong public data.
    model_default = (g("Model Number")
                     or str(pa.get("model_number") or pa.get("part_number") or "").strip())
    if has("manufacturer"):
        put("manufacturer", _shape_simple(props["manufacturer"], pa.get("manufacturer") or brand, mid))
    if has("model_number") and (pa.get("model_number") or model_default):
        put("model_number", _shape_simple(props["model_number"], pa.get("model_number") or model_default, mid))
    if has("part_number") and (pa.get("part_number") or model_default):
        put("part_number", _shape_simple(props["part_number"], pa.get("part_number") or model_default, mid))

    # --- offer + fulfillment --------------------------------------------------
    price = _clean_price(g("Our Price (GBP)"))   # strip any "GBP"/symbol so float() works (was dropping list_price)
    if not _is_blank(price):
        try:
            A["purchasable_offer"] = _offer(price, mid)
        except Exception:
            pass
    _qty = pa.pop("fulfillment_quantity", None)            # per-listing stock from the dashboard; blank -> config default
    try:
        _qty = int(str(_qty).strip()) if str(_qty).strip() not in ("", "None") else int(config.get("default_quantity", 10))
    except Exception:
        _qty = int(config.get("default_quantity", 10))
    A["fulfillment_availability"] = _fulfillment(_qty, g("Handling Days"))
    return price


def phase_dimensions(A, props, pa, mid, has):
    """item / package dimensions, then every composite dimension field."""
    # --- dimensions (composite if the type uses it) ---------------------------
    # Read each axis from the NESTED item_dimensions[axis] object (what the editor saves,
    # rebuilt by _renest) FIRST, falling back to the legacy flat item_<axis> key. Reading
    # flat-only used to drop any axis present only in nested form (commonly width/height),
    # so Amazon rejected the listing as missing them. Same fix for item_package_dimensions.
    if has("item_dimensions"):
        _idim = pa.get("item_dimensions")
        d = _shape_dimensions(props["item_dimensions"],
                              _dim_axis_raw(_idim, "length", pa.get("item_length")),
                              _dim_axis_raw(_idim, "width",  pa.get("item_width")),
                              _dim_axis_raw(_idim, "height", pa.get("item_height")), mid)
        if d:
            A["item_dimensions"] = d
    if has("item_package_dimensions"):
        _pdim = pa.get("item_package_dimensions")
        d = _shape_dimensions(props["item_package_dimensions"],
                              _dim_axis_raw(_pdim, "length", pa.get("item_package_length")),
                              _dim_axis_raw(_pdim, "width",  pa.get("item_package_width")),
                              _dim_axis_raw(_pdim, "height", pa.get("item_package_height")), mid)
        if d:
            A["item_package_dimensions"] = d

    # composite dimension variants some categories require instead of item_dimensions.
    # Schema-driven: any field whose item properties contain axis sub-fields
    # (length/width/height/depth) with their own value+unit is a composite dim
    # attribute and gets routed through shape_by_schema. Previously this loop
    # hardcoded ("item_depth_width_height", "item_length_width_height") -- but
    # Amazon uses more variants than that (item_length_width for flat/flexible
    # products like expandable hoses is a notable example). Missing variants
    # were silently dropped by _shape_simple's fallback return-[] at line 4343,
    # causing "X Unit is required but missing" errors even after Applied values
    # were correctly saved. Now every axis-shaped field is handled by name.
    _axis_names = ("length", "width", "height", "depth")
    def _is_composite_dim(fname):
        if not isinstance(props.get(fname), dict):
            return False
        _fip = _item_props(props[fname])
        # must have at least ONE axis key, and no top-level value/unit (those
        # single-axis attributes are handled by _shape_simple already).
        _has_axis = any(a in _fip for a in _axis_names)
        _has_flat = ("value" in _fip)
        return _has_axis and not _has_flat
    _axes_src = {"length": pa.get("item_length"), "width": pa.get("item_width"),
                 "height": pa.get("item_height"),
                 "depth":  pa.get("item_depth") or pa.get("item_length")}
    # Merge in any user-supplied nested values from pa (e.g. _renest folded
    # item_length_width.width.value into pa["item_length_width"]["width"]).
    # These take priority over the generic item_length / item_width columns.
    def _from_user_composite(fname):
        v = pa.get(fname)
        if not isinstance(v, dict):
            return {}
        out = {}
        for axis in _axis_names:
            av = v.get(axis)
            if isinstance(av, dict):
                # {value|decimal_value: "0.0", unit: "centimeters"} -> "0.0 centimeters"
                # Amazon nests some axes as `decimal_value` (leg/cable/HARDWARE_TUBING)
                # and others as `value`. _renest stores whichever the AI applied, so
                # accept both or the applied measurement is silently dropped and the
                # field is shaped from empty generic columns (rejected as invalid).
                num = av.get("decimal_value", av.get("value"))
                unit = av.get("unit")
                if num not in (None, "") and unit:
                    out[axis] = f"{num} {unit}"
                elif num not in (None, ""):
                    out[axis] = str(num)
            elif isinstance(av, list) and av and isinstance(av[0], dict):
                # already-shaped list: preserve as-is by picking the first entry
                num = av[0].get("decimal_value", av[0].get("value"))
                unit = av[0].get("unit")
                if num not in (None, "") and unit:
                    out[axis] = f"{num} {unit}"
        return out
    for _fname in list(props.keys()):
        if not _is_composite_dim(_fname):
            continue
        if _fname in A:
            continue
        _user_axes = _from_user_composite(_fname)
        _merged_axes = dict(_axes_src)
        _merged_axes.update({k: v for k, v in _user_axes.items() if v})
        # Schema-driven shaping. shape_by_schema reads the LIVE schema at every
        # level -- array-vs-object wrapping, `value` vs `decimal_value` leaf, and
        # enum units are all READ, never assumed. This is what leg/cable need:
        # their `length` axis is itself a `type: array` whose item leaf key is
        # `decimal_value` (one level deeper than _shape_axes looked, so _shape_axes
        # defaulted to a flat `value` object and Amazon rejected it as invalid).
        # We pass ONLY the axes the field's own schema declares AND that carry a
        # value, so absent axes never fold into empty {}/[{}] wrappers.
        _fip = _item_props(props[_fname])
        _raw_axes = {k: v for k, v in _merged_axes.items()
                     if k in _fip and not _is_blank(v)}
        # A composite is NOT only its dimension axes. furniture_leg also carries color,
        # material and style -- and _from_user_composite() above only ever collected
        # length/width/height/depth, so the values the user typed for those three were
        # never passed to the shaper. Amazon then reported them as missing
        # ("'color#1.value' does not have enough values"). Feed EVERY sub-field the
        # schema declares and the user actually supplied.
        _user_obj = pa.get(_fname)
        if isinstance(_user_obj, dict):
            for _sk, _sv in _user_obj.items():
                if _sk in _axis_names or _sk not in _fip or _sk in _raw_axes:
                    continue
                if isinstance(_sv, dict):
                    _sv = _sv.get("value", _sv.get("decimal_value"))
                elif isinstance(_sv, list) and _sv and isinstance(_sv[0], dict):
                    _sv = _sv[0].get("value", _sv[0].get("decimal_value"))
                if not _is_blank(_sv):
                    _raw_axes[_sk] = _sv
        if not _raw_axes:
            continue
        d = shape_by_schema(props[_fname], _raw_axes, mid, _lang_for(mid))
        if d:
            A[_fname] = d


def phase_pa_map(A, pa, props, required, pt, mid, console):
    """The flat product_attributes (pa) into A: our name -> Amazon's name,
    snapped to Amazon's allowed values, unknown names dropped and named."""
    # --- write the flat product_attributes (pa) into A ----------------------
    # pa holds BOTH the generator's attributes AND any values the user applied
    # via "Suggest missing fields"/the editor (saved to Attributes JSON). Each
    # is written if the schema lists it OR it's a required field (Amazon's
    # ENFORCED schema omits some required fields' defs, so `has(f)` alone would
    # wrongly drop user-applied values like material/color/light_source).
    skip_axes = {"item_length", "item_width", "item_height",
                 "item_package_length", "item_package_width", "item_package_height"}
    # These need a SPECIAL structure (nested composite / integer / strict enum),
    # not a flat value. Let the specialized backfill below shape them so a plain
    # text value applied in the editor (e.g. battery="Lithium Ion") doesn't get
    # written in the wrong shape and then rejected as "missing".
    _special_shape = {"battery", "num_batteries", "light_source", "power_source_type",
                      "has_multiple_battery_powered_components", "supplier_declared_dg_hz_regulation",
                      "special_feature", "warranty_description", "safety_data_sheet_url", "ghs"}
    # OUR NAME -> AMAZON'S NAME. The generation prompt asks the AI for a fixed
    # list of useful facts, and a few of them are asked for under a name Amazon
    # does not use. Renaming keeps the VALUE, which is real and researched;
    # dropping it would throw away work and then look like the AI failed.
    #   special_features  Amazon's key is singular. It is in _special_shape
    #                     below, which shapes it properly.
    #   item_condition    Amazon's key is condition_type, and this function has
    #                     already set it to new_new further up -- so the AI's
    #                     "New" is a duplicate under a name Amazon rejects.
    alias     = {"colour": "color", "special_features": "special_feature",
                 "item_condition": "condition_type"}
    # WHAT AMAZON HAS NO FIELD FOR, DROPPED AND NAMED.
    #
    #     "we dont need to be sending unnecessary information to amazon like
    #      [W] included_components ... does not belong or is no longer
    #      applicable to the product type you were trying to list"
    #
    # Measured on four real SQUEEGEE drafts: 7 to 11 attributes per listing that
    # this product type has no field for at all -- included_components,
    # unit_count_type, item_type_keyword, item_condition, special_features. The
    # generation prompt asks for them on every product regardless of type, and
    # this loop sent every one of them.
    #
    # ONLY when a schema actually loaded. With no schema we cannot tell "Amazon
    # has no such field" from "we failed to ask", and dropping on a failed fetch
    # would quietly strip a good listing. The dropped names are collected and
    # printed, never discarded in silence.
    # _allowed_values: moved to listing/attributes_helpers.py (plan B2, verbatim).

    _schema_names = set(props or {}) | set(required or set())
    _dropped_unknown = []
    _snapped = []
    for k, v in pa.items():
        if k in skip_axes or _is_blank(v):
            continue
        f = alias.get(k, k)
        if f in A or f in _special_shape:
            continue
        _fprop = props.get(f) if isinstance(props.get(f), dict) else {}
        if not _fprop and _schema_names and f not in _schema_names:
            _dropped_unknown.append(k if k == f else ("%s (as %s)" % (k, f)))
            continue
        # SNAP TO AMAZON'S OWN VOCABULARY BEFORE SENDING.
        #
        #     "some information is filled but do not accurately represent
        #      the listing"
        #
        # Measured over every stored draft, checking each value against the
        # cached live schema: 211 of 1220 values -- 17% -- are not on Amazon's
        # list for their field.
        #
        #     is_fragile   'No'                       allowed: True / False
        #     item_shape   'N/A', 'Pole', 'Cylindrical'  allowed: Round, Square,
        #                                                Rectangular, Oval, ...
        #     material     'ABS', 'Aircraft-grade aluminium', 'Rubber | Plastic'
        #                  allowed: 69 controlled names incl. 'Aluminium' and
        #                  'Acrylonitrile Butadiene Styrene'
        #
        # The app has always had a 5-strategy matcher for exactly this --
        # snap_to_valid -- but it was only ever pointed at the STATIC
        # valid_values.json used by the flat-file builder. The API path, which
        # is the one in use, never snapped at all. Same function, pointed at the
        # LIVE schema, which is the authority (CLAUDE.md Rule 12).
        #
        # NEVER BLANKS. snap_to_valid returns "" when nothing matches, and the
        # original value is kept in that case -- a value Amazon rejects with a
        # readable error beats a field silently emptied.
        if isinstance(v, str) and f not in _COMPLIANCE_PASSTHROUGH:
            _allow = _allowed_values(_fprop)
            if _allow:
                _lowall = {str(a).strip().lower() for a in _allow}
                _vs = v.strip()
                # A YES/NO ANSWER TO A TRUE/FALSE FIELD. is_fragile's allowed
                # list is exactly True and False, and 52 stored drafts answer
                # it "No". Only fires when the field really is boolean, so it
                # cannot touch a field where "No" is itself an option.
                if _lowall <= {"true", "false"} and _vs.lower() in (
                        "yes", "no", "y", "n", "true", "false"):
                    _want = "true" if _vs.lower() in ("yes", "y", "true") else "false"
                    _snap = next((a for a in _allow if str(a).lower() == _want), "")
                # "NOT APPLICABLE" ON A FIELD WITH NO SUCH OPTION. 'N/A' is not
                # a shape. Where Amazon offers no not-applicable value, the
                # honest thing is to send nothing rather than the letters N/A.
                elif (_vs.lower().replace(".", "").replace(" ", "") in
                        ("na", "n/a", "none", "notapplicable", "nil", "-")
                      and not any(x in _lowall for x in
                                  ("n/a", "na", "none", "not applicable"))):
                    _dropped_unknown.append("%s (was %r, no such option)" % (f, _vs[:20]))
                    continue
                else:
                    _snap = snap_to_valid(v, _allow)
                if _snap and _snap != v:
                    _snapped.append("%s %r -> %r" % (f, v[:28], _snap))
                    v = _snap
        # Written even when Amazon's slim ENFORCED schema omits the definition,
        # as long as the field EXISTS for this product type -- has(f) alone
        # wrongly dropped user-applied values like material / color /
        # light_source, which is what caused "X required but missing".
        shaped = _shape_simple(_fprop, v, mid) if _fprop else [{"value": str(v), "marketplace_id": mid}]
        if shaped:
            A[f] = shaped
    if _dropped_unknown:
        console.print("  [yellow]Not sent -- %s has no such attribute: %s[/yellow]"
                      % (pt, ", ".join(sorted(_dropped_unknown))))
    if _snapped:
        console.print("  [cyan]Snapped to Amazon's allowed values: %s[/cyan]"
                      % "; ".join(_snapped[:8]))


def phase_required_backfill(A, pa, props, required, mid, g):
    """Every required field still unset gets a safe, valid value.
    -> the names it filled (the builder prints them later)."""
    # --- REQUIRED-FIELD BACKFILL --------------------------------------------
    # Amazon rejects a listing when a category-required attribute is missing
    # ("X is required but missing"). For any field the schema marks required but
    # we still haven't set, fill a safe, valid value derived from what we know,
    # or snap to the first allowed enum value. This makes VALIDATION_PREVIEW pass
    # on required-but-unmapped fields instead of erroring.
    _row_title = g("Item Name") or g("Title") or ""
    _row_model = g("Model Number")
    _row_brand = g("Brand Name") or g("Brand") or g("Manufacturer") or ""
    _row_country = g("Country of Origin") or g("Country/Region of Origin") or ""
    _backfilled = []
    for _rf in required:
        if _rf in A:
            continue
        _before_keys = set(A.keys())
        # Amazon often lists a field under `required` without including its full
        # property definition in `properties` (ENFORCED mode returns a slim set,
        # or the def lives in a referenced sub-schema). Don't skip those -- we
        # still fill them with a sensible value. `_prop` may be {} in that case.
        _prop = props.get(_rf) if isinstance(props.get(_rf), dict) else {}
        # Pull the allowed enum list (if any) so we can snap to a legal value.
        _items   = _prop.get("items", {}) if isinstance(_prop.get("items"), dict) else {}
        _ip      = _items.get("properties", {}) if isinstance(_items, dict) else {}
        _vp      = _ip.get("value", {}) if isinstance(_ip, dict) else {}
        _enum    = (_vp.get("enum") or _ip.get("enum") or _items.get("enum") or _prop.get("enum") or [])
        # Sensible content-derived defaults for the common required offenders.
        _default = None
        _hay = (_row_title + " " + g("Product Description")).lower()
        _is_rechargeable = any(w in _hay for w in ["rechargeable", "usb", "usb-c", "type-c", "li-ion", "lithium"])
        if _rf in ("model_name", "model"):
            _default = _row_model or _row_title[:60] or _row_brand or "Standard"
        elif _rf == "part_number":
            _default = _row_model or "NA"
        elif _rf in ("manufacturer",):
            _default = _row_brand or "Generic"
        elif _rf == "num_batteries":
            _default = "1"
        elif _rf == "battery_type":
            _default = "battery_type_lithium_ion" if _is_rechargeable else "battery_type_a"
        elif _rf == "power_source_type":
            _default = "battery_powered" if _is_rechargeable else "corded_electric"
        elif _rf == "warranty_description":
            _default = "No warranty"
        elif _rf in ("number_of_items", "unit_count"):
            _default = "1"
        elif _rf == "country_of_origin":
            _default = _row_country or "CN"
        elif _rf in ("included_components",):
            _default = _row_title[:60] or "Main unit"
        elif _rf in ("specific_uses_for_product", "recommended_uses_for_product"):
            _default = "General use"
        elif _rf == "lithium_battery_packaging":
            _default = "batteries_contained_in_equipment" if _is_rechargeable else None
        elif _rf == "material":
            _default = g("Material") or ("Aluminum Alloy" if ("flashlight" in _hay or "torch" in _hay) else "Plastic")
        elif _rf == "color":
            _default = g("Colour") or g("Color") or "Black"
        elif _rf == "item_type_keyword":
            # short keyword describing the item; derive from product type/title
            _default = (g("Product Type") or "").replace("_", " ").lower() or _row_title[:30] or "flashlight"
        elif _rf == "special_feature":
            _default = "Rechargeable" if _is_rechargeable else "Portable"
        elif _rf == "light_source":
            # enum field -> Amazon expects values like 'led'. Prefer the user's
            # applied value (normalised) and snap to the enum; default 'led'.
            _applied = str(pa.get("light_source", "")).strip().lower().replace(" ", "_")
            if not _enum:
                _enum = ["led", "incandescent", "fluorescent", "halogen",
                         "xenon", "neon", "laser", "lcd", "oled", "solar_powered"]
            _default = _applied if (_applied and _applied in _enum) else (
                "led" if (_applied in ("", "led") or "led" in _applied) else
                (_applied if _applied else "led"))
            if _default not in _enum:
                _default = "led" if "led" in _enum else _enum[0]
        elif _rf == "power_source_type":
            # enum field. Prefer applied value; map common synonyms.
            _applied = str(pa.get("power_source_type", "")).strip().lower().replace(" ", "_")
            if not _enum:
                _enum = ["battery_powered", "corded_electric", "ac_dc",
                         "solar_powered", "hand_powered", "usb"]
            # USB-charged rechargeable torch -> battery_powered (most accurate)
            _syn = {"usb": "battery_powered", "usb-c": "battery_powered",
                    "rechargeable": "battery_powered", "battery": "battery_powered",
                    "corded": "corded_electric", "mains": "corded_electric"}
            _cand = _syn.get(_applied, _applied)
            _default = _cand if (_cand and _cand in _enum) else (
                "battery_powered" if _is_rechargeable else "corded_electric")
            if _default not in _enum:
                _default = _enum[0]
        elif _rf == "ghs":
            # GHS hazard classification -> for a non-chemical retail item.
            if not _enum:
                _enum = ["not_applicable"]
            _default = "not_applicable"
        elif _rf in ("safety_data_sheet_url", "msds_url"):
            # not a chemical product -> no SDS; write empty so the field is present
            _default = ""
        elif _rf in ("included_in_warranty",):
            _default = "No warranty"
        elif _rf in ("style", "style_name"):
            _default = _row_title[:40] or "Standard"
        elif _rf in ("wattage",):
            _default = None
        elif _rf in ("is_assembly_required",):
            _default = None

        # --- nested composite fields: shape EXACTLY per the FLASHLIGHT schema ---
        # (verified against getDefinitions: battery>average_life{value,unit};
        #  num_batteries>{quantity:int, type:enum}; light_source>type>{value,language_tag})
        if _rf == "battery" and _rf not in A:
            # battery.average_life -> [{value: <hours>, unit: "hours"}]
            _life = 6.0
            try:
                import re as _re
                m = _re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", _hay)
                if m:
                    _life = float(m.group(1))
            except Exception:
                _life = 6.0
            A["battery"] = [{
                "average_life": [{"value": _life, "unit": "hours"}],
                "marketplace_id": mid,
            }]
            continue
        if _rf == "num_batteries" and _rf not in A:
            # num_batteries -> [{quantity: <int>, type: <enum>}]; built-in
            # lithium cell isn't a standard AA/AAA size -> "nonstandard_battery".
            _bt_enum = ["12v", "9v", "a", "aa", "aaa", "aaaa", "c", "d", "nonstandard_battery"]
            try:
                _bt = props["num_batteries"]["items"]["properties"]["type"]
                _bt_enum = _bt.get("enum") or _bt_enum
            except Exception:
                pass
            _applied_bt = str(pa.get("num_batteries", "")).strip().lower()
            _bt_val = "nonstandard_battery"
            for _opt in _bt_enum:
                if _opt == _applied_bt:
                    _bt_val = _opt
                    break
            _qty = 1
            try:
                _qty = int(float(str(pa.get("num_batteries", "1")).strip() or "1"))
            except Exception:
                _qty = 1
            if _qty < 0:
                _qty = 1
            A["num_batteries"] = [{
                "quantity": _qty,
                "type": _bt_val,
                "marketplace_id": mid,
            }]
            continue
        if _rf == "light_source" and _rf not in A:
            # light_source -> [{type: [{value: <str>, language_tag: <locale>}]}]
            _ls_val = str(pa.get("light_source", "")).strip() or "LED"
            _lang = "en_US" if mid == US_MARKETPLACE_ID else "en_GB"
            A["light_source"] = [{
                "type": [{"value": _ls_val, "language_tag": _lang}],
                "marketplace_id": mid,
            }]
            continue
        if _rf == "has_multiple_battery_powered_components" and _rf not in A:
            A[_rf] = [{"value": False, "marketplace_id": mid}]
            continue
        if _rf in ("supplier_declared_dg_hz_regulation",) and _rf not in A:
            # Transport DG regulation. CRITICAL: if this is set to "ghs", Amazon
            # then REQUIRES a GHS hazard class (explosive/flammable/etc.) -- and
            # there is NO "not applicable" GHS class, so a non-chemical product
            # like a flashlight can never satisfy it. So we must NEVER let this
            # field fall back to "ghs". Prefer the lithium-battery value when the
            # schema offers one (a rechargeable torch), else "not_applicable".
            _pref = []
            if _is_rechargeable:
                _pref = ["battery_lithium_ion", "lithium_ion", "battery", "transportation"]
            _pref += ["not_applicable", "not_app", "none"]
            _val = None
            if _enum:
                # pick the first preferred value that actually exists in the enum
                _enum_low = {str(e).lower(): e for e in _enum}
                for _p in _pref:
                    if _p in _enum_low:
                        _val = _enum_low[_p]; break
                if _val is None:
                    # last resort: ANY enum value that is NOT ghs (never trigger GHS)
                    _val = next((e for e in _enum if str(e).lower() != "ghs"), None)
            if _val is None:
                _val = ("battery_lithium_ion" if _is_rechargeable else "not_applicable")
            A[_rf] = [{"value": _val, "marketplace_id": mid}]
            continue
        # Build the field value: numeric vs simple vs enum. Build the structure
        # DIRECTLY (array-of-one + marketplace_id) so it works even when `_prop`
        # is empty (field required but no property def returned by Amazon).
        def _put_simple(val):
            A[_rf] = [{"value": val, "marketplace_id": mid}]

        # CONSERVATIVE GUARD: never inject a guessed text value into a field that
        # has a format/pattern/numeric constraint we can't satisfy. Filling these
        # with the product title creates "does not meet pattern" errors that are
        # worse than leaving the field for the user. Skip them entirely.
        _pattern = ""
        _ptype = ""
        try:
            _vp2 = (_prop.get("items", {}).get("properties", {}).get("value", {})
                    if isinstance(_prop, dict) else {})
            _pattern = _vp2.get("pattern", "") or _prop.get("pattern", "")
            _ptype   = _vp2.get("type", "") or _prop.get("type", "")
        except Exception:
            _pattern, _ptype = "", ""
        # fields that are IDs / numeric / pattern-constrained -> don't guess
        _NO_GUESS = ("browse_node" in _rf or _rf.endswith("_id") or "url" in _rf
                     or _rf in ("recommended_browse_nodes", "external_product_id",
                                "gtin", "ean", "upc", "isbn", "model_number"))
        try:
            if _rf in ("num_batteries", "number_of_items", "unit_count"):
                _put_simple(int(_default) if _default else 1)
            elif _enum:
                # snap to first allowed value (or a content default if it's in the enum)
                _pick = _default if (_default and _default in _enum) else _enum[0]
                _put_simple(str(_pick))
            elif _default is not None and str(_default) != "":
                # respect a numeric type / pattern: only write if the default fits
                if _pattern:
                    import re as _re_pat
                    if _re_pat.match(_pattern.replace("\\A", "^").replace("\\z", "$"), str(_default)):
                        _put_simple(str(_default))
                    # else: skip -- a guessed value won't match the pattern
                elif _ptype in ("integer", "number"):
                    try:
                        _put_simple(float(_default) if "." in str(_default) else int(_default))
                    except Exception:
                        pass  # not numeric -> skip rather than send bad data
                else:
                    _put_simple(str(_default))
            elif _default == "":
                # explicitly-empty default (e.g. SDS url for a non-chemical item)
                _put_simple("")
            elif _NO_GUESS or _pattern or _ptype in ("integer", "number"):
                # required, no safe default, and we MUST NOT guess (ID/numeric/
                # pattern field) -> leave it for the user instead of injecting junk
                pass
            else:
                # CATCH-ALL: plain free-text field, still required, no default ->
                # a neutral value is acceptable here.
                _put_simple(_row_title[:30] or "Standard")
        except Exception:
            # never let backfill crash the build; just skip the field
            pass
        if _rf in A and _rf not in _before_keys:
            _backfilled.append(_rf)

    return _backfilled


# The compliance block calls the backfill by the name it had in the engine.
_phase_required_backfill = phase_required_backfill


def phase_compliance(A, row, pa, props, required, config, mid, g, console,
                     _LAST_COMPLIANCE_NOTES):
    """Special nested fields, battery evidence, safe compliance defaults, the UK
    responsible person, the lithium group, the required-field backfill, the
    final GHS net, the conditionally-required net, always-rebuild-clean and
    schema-independent hardening -- in ONE function because these steps read and
    rewrite the same fields several times and their ORDER is the rule (plan B5).
    `_LAST_COMPLIANCE_NOTES` is the engine's own dict, passed in and filled in
    place. -> (_backfilled, _has_battery), both read by the builder afterwards."""
    # --- SPECIAL NESTED FIELDS (always shaped to Amazon's exact structure) ----
    # FLASHLIGHT (and similar electronics) need these in a specific nested shape.
    # Amazon reports a malformed value as "required but missing", and these are
    # conditionally required for battery products even though they're NOT in the
    # static `required` list -- so shape them whenever the row/applied data
    # references them or it's clearly a battery-powered item. Structures verified
    # against getDefinitions.
    _hay_sf = (g("Item Name") + " " + g("Title") + " " + g("Product Description")).lower()
    # Only treat this as a battery product if the SCHEMA actually requires the
    # battery fields OR the user already supplied them. Keyword-only guessing
    # forced FLASHLIGHT battery structures onto unrelated product types (e.g. a
    # MASSAGER wants different sub-fields) and created errors. Be conservative:
    # follow what THIS product type's schema asks for.
    def _req_or_present(name):
        return name in required or name in pa or isinstance(props.get(name), dict)
    _kw_batt = any(w in _hay_sf for w in ["battery", "rechargeable", "lithium",
                                          "li-ion", "usb", "torch", "flashlight", "led"])
    # battery group only fires when the schema/user signals it, not on keywords alone
    _is_batt = _kw_batt and (_req_or_present("battery") or _req_or_present("num_batteries")
                             or _req_or_present("power_source_type"))
    _lang_sf = "en_US" if mid == US_MARKETPLACE_ID else "en_GB"

    def _has_prop(name):
        return isinstance(props.get(name), dict)

    # IS THERE ACTUALLY A BATTERY IN THIS PRODUCT?
    #
    # Nothing asked that before. _has_prop was standing in for it -- but that is
    # True whenever the schema merely DECLARES the field, and almost every
    # product type declares the battery fields. Measured on two real jack_uk
    # rows, both product type THERMOS:
    #
    #     Vacuum Insulated Stainless Steel Jug 1.5L   8 battery attributes sent
    #     Vacuum Insulated Thermos Flask 2 Litre      9 battery attributes sent
    #
    # and the payload contradicted itself in the same breath:
    #
    #     batteries_required        false
    #     batteries_included        false
    #     contains_battery_or_cell  "battery"     <- plus 1 lithium-ion cell,
    #     num_batteries             1                alkaline composition
    #
    # A vacuum flask has no battery. That is not merely noise:
    # contains_battery_or_cell is a REGULATORY declaration that changes how
    # Amazon ships and handles the item, so answering it "yes" by default is a
    # false declaration made on the owner's account. It also pulled in
    # non_lithium_battery_packaging as required, one of the three errors keeping
    # the row unlistable.
    #
    # ONE question, asked once, used by every battery field below (rule 12).
    def _flagged(_k):
        """The row's answer to a batteries_* question: True, False, or None."""
        _v = pa.get(_k)
        if _v is None or str(_v).strip() == "":
            return None
        return str(_v).strip().lower() in ("true", "yes", "y", "1")

    def _battery_evidence():
        # 1. Real battery data supplied for THIS product outranks everything.
        _b = pa.get("battery")
        if isinstance(_b, dict) and any(str(x).strip() for x in _b.values()):
            return True
        try:
            if int(float(str(pa.get("num_batteries") or 0))) > 0:
                return True
        except (TypeError, ValueError):
            pass
        # 2. An explicit answer on the row -- either way. A stated "no" is
        #    evidence, and it is the part that was being ignored.
        for _k in ("batteries_required", "batteries_included",
                   "are_batteries_included"):
            _f = _flagged(_k)
            if _f is not None:
                return _f
        # 3. Otherwise the keyword + schema detection, exactly as before.
        return bool(_is_batt)

    _has_battery = _battery_evidence()

    # GLOBAL SAFE-DEFAULTS: neutralise the hazard/regulatory compliance fields to
    # their 'not applicable / none' option from the live schema, so a non-chemical
    # gadget never errors on a compliance dropdown and never trips a cascade like
    # the dg-regulation "ghs" trap. Records what it set so the dashboard can show
    # the user (choice 2b).
    try:
        _compliance_notes = apply_compliance_safe_defaults(A, props, required, mid, _is_batt)
    except Exception:
        _compliance_notes = []
    if _compliance_notes:
        console.print(f"  [cyan]Compliance auto-set ({len(_compliance_notes)} field(s)) "
                      f"-- shown so you can override:[/cyan]")
        for _cf, _cv, _cr in _compliance_notes:
            console.print(f"    [dim]\u2022 {_cf} = \"{_cv}\"  ({_cr})[/dim]")
        # stash for any downstream reporter (dashboard reads the run log)
        try:
            _LAST_COMPLIANCE_NOTES[row.get("SKU", "") or row.get("Sku", "")] = _compliance_notes
        except Exception:
            pass

    # UK RESPONSIBLE PERSON: for Amazon.co.uk listings, fill the responsible-person
    # / manufacturer-contact compliance fields from the account's saved RP details.
    # Only for UK/GB runs (mid != US) and only when the schema actually declares
    # the field, so US listings are untouched and we never send a field Amazon
    # doesn't expect.
    if mid != US_MARKETPLACE_ID:
        _rp = (config.get("_uk_responsible_person") or {}) if isinstance(config, dict) else {}
        if isinstance(_rp, dict) and (_rp.get("name") or _rp.get("address")):
            _rp_name = str(_rp.get("name", "")).strip()
            _rp_addr = str(_rp.get("address", "")).strip()
            _rp_email = str(_rp.get("email", "")).strip()
            _rp_phone = str(_rp.get("phone", "")).strip()
            # Amazon UK uses a handful of possible field names across product types.
            # Fill whichever the live schema declares.
            for _rpf in ("manufacturer_contact_information", "responsible_person_address",
                         "eu_responsible_person", "uk_responsible_person"):
                if _rpf in A or not isinstance(props.get(_rpf), dict):
                    continue
                _block = ", ".join([p for p in (_rp_name, _rp_addr, _rp_email, _rp_phone) if p])
                A[_rpf] = [{"value": _block[:500], "marketplace_id": mid}]
                _compliance_notes.append((_rpf, _block[:60] + ("…" if len(_block) > 60 else ""),
                                          "auto: UK Responsible Person from account settings"))

    # light_source -> [{type: [{value, language_tag}]}]
    if ("light_source" in pa or _has_prop("light_source") or "led" in _hay_sf) and "light_source" not in A:
        _ls_val = str(pa.get("light_source", "")).strip() or "LED"
        A["light_source"] = [{"type": [{"value": _ls_val, "language_tag": _lang_sf}],
                              "marketplace_id": mid}]

    # num_batteries -> [{quantity:int, type:enum}]
    # _has_prop dropped for the same reason as `battery` below: it is true for
    # any type that merely declares the field, so a thermos was told it takes
    # one nonstandard battery while the very next line said batteries_required
    # is false.
    if ("num_batteries" in pa or "num_batteries" in required or _has_battery) \
            and "num_batteries" not in A:
        _bt_enum = ["12v", "9v", "a", "aa", "aaa", "aaaa", "c", "d", "nonstandard_battery"]
        try:
            _bt_enum = props["num_batteries"]["items"]["properties"]["type"].get("enum") or _bt_enum
        except Exception:
            pass
        _applied_bt = str(pa.get("num_batteries", "")).strip().lower()
        _bt_val = next((o for o in _bt_enum if o == _applied_bt), "nonstandard_battery")
        try:
            _qty = max(0, int(float(str(pa.get("num_batteries", "1")).strip() or "1")))
        except Exception:
            _qty = 1
        A["num_batteries"] = [{"quantity": _qty, "type": _bt_val, "marketplace_id": mid}]

    # battery -> [{cell_composition:[{value}], average_life:[{value,unit}]}]
    # Amazon's error names "Battery Cell Composition" -> cell_composition is the
    # part it wants. Include both; rechargeable torch -> lithium_ion.
    # _has_prop("battery") was in this condition and had to come out: it is true
    # for any product type whose schema merely DECLARES the field, which is most
    # of them, so every thermos got a full alkaline-cell battery object built for
    # it. See _battery_evidence below for the measurement. A battery is now built
    # when the row supplies one, when Amazon requires one, or when there is real
    # evidence of one -- never because the schema knows the word.
    if ("battery" in pa or "battery" in required or _has_battery) and "battery" not in A:
        # If _renest folded user-supplied sub-field values into pa["battery"] as
        # a nested dict (e.g. {"capacity":{"value":"2000","unit":"milliamp_hour"}}),
        # capture them so we merge OVER our defaults instead of throwing them
        # away. Without this, the hardcoded defaults below always win and the
        # user's Applied values silently vanish.
        _user_bat = pa.get("battery")
        _user_bat_dict = _user_bat if isinstance(_user_bat, dict) else {}
        _life = 6.0
        try:
            import re as _re_sf
            _m = _re_sf.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", _hay_sf)
            if _m:
                _life = float(_m.group(1))
        except Exception:
            _life = 6.0
        # cell_composition enum (snap if schema provides it); lithium_ion default
        _cc_enum = []
        try:
            _ccp = props["battery"]["items"]["properties"]["cell_composition"]
            _cc_enum = (_ccp.get("items", {}).get("properties", {}).get("value", {}).get("enum")
                        or _ccp.get("items", {}).get("enum") or _ccp.get("enum") or [])
        except Exception:
            _cc_enum = []
        # Prefer a user-supplied cell_composition (from sub-field editor) over
        # a string applied to the parent 'battery' key.
        _user_cc = ""
        if _user_bat_dict.get("cell_composition"):
            _uc = _user_bat_dict["cell_composition"]
            if isinstance(_uc, list) and _uc:
                _user_cc = str(_uc[0].get("value") if isinstance(_uc[0], dict) else _uc[0])
            elif isinstance(_uc, dict):
                _user_cc = str(_uc.get("value", ""))
            else:
                _user_cc = str(_uc)
        _applied_cc = (_user_cc or str(pa.get("battery", "") if not isinstance(pa.get("battery"), dict) else "")).strip().lower().replace(" ", "_").replace("-", "_")
        _rech_sf = any(w in _hay_sf for w in ["rechargeable", "usb", "li-ion", "lithium", "type-c"])
        _cc_val = "lithium_ion" if _rech_sf else "alkaline"
        if _applied_cc in ("lithium_ion", "lithium", "li_ion", "lithium_polymer", "alkaline",
                           "nickel_metal_hydride", "lithium_metal"):
            _cc_val = "lithium_ion" if _applied_cc in ("lithium", "li_ion") else _applied_cc
        if _cc_enum and _cc_val not in _cc_enum:
            _cc_val = "lithium_ion" if "lithium_ion" in _cc_enum else _cc_enum[0]
        # SCHEMA-AWARE: only include the sub-fields THIS product type's battery
        # object actually declares. Different product types want different
        # sub-fields (e.g. MASSAGER requires charge_time; FLASHLIGHT doesn't).
        _bat_subs = {}
        try:
            _bat_subs = props["battery"]["items"]["properties"] or {}
        except Exception:
            _bat_subs = {}

        # Helper: extract a user-supplied value+unit sub-field from _user_bat_dict.
        # Returns (value, unit) or (None, None). Handles the shape _renest
        # produces: {"capacity": {"value": "2000", "unit": "milliamp_hour"}}.
        def _user_vu(subname):
            n = _user_bat_dict.get(subname)
            if isinstance(n, dict):
                return n.get("value"), n.get("unit")
            if isinstance(n, list) and n and isinstance(n[0], dict):
                return n[0].get("value"), n[0].get("unit")
            return None, None

        _bat_obj = {"marketplace_id": mid}
        if not _bat_subs or "cell_composition" in _bat_subs:
            _bat_obj["cell_composition"] = [{"value": _cc_val}]
        if not _bat_subs or "average_life" in _bat_subs:
            _uv, _uu = _user_vu("average_life")
            try:    _v = float(_uv) if _uv not in (None, "") else _life
            except Exception: _v = _life
            _bat_obj["average_life"] = [{"value": _v, "unit": (_uu or "hours")}]
        if not _bat_subs or "weight" in _bat_subs:
            _uv, _uu = _user_vu("weight")
            try:    _v = float(_uv) if _uv not in (None, "") else 50.0
            except Exception: _v = 50.0
            _bat_obj["weight"] = [{"value": _v, "unit": (_uu or "grams")}]
        # product-type-specific sub-fields, added ONLY when the schema declares them
        if "charge_time" in _bat_subs:
            _uv, _uu = _user_vu("charge_time")
            try:    _v = float(_uv) if _uv not in (None, "") else 3.0
            except Exception: _v = 3.0
            _bat_obj["charge_time"] = [{"value": _v, "unit": (_uu or "hours")}]
        if "capacity" in _bat_subs:
            _uv, _uu = _user_vu("capacity")
            try:    _v = float(_uv) if _uv not in (None, "") else 1000.0
            except Exception: _v = 1000.0
            _bat_obj["capacity"] = [{"value": _v, "unit": (_uu or "milliamp_hour")}]
        A["battery"] = [_bat_obj]

    # --- LITHIUM BATTERY GROUP (required once a lithium cell is declared) -----
    # Declaring a lithium-ion battery triggers Amazon's hazmat group. These are
    # best-effort structures for a built-in rechargeable lithium-ion torch.
    # SCHEMA-DRIVEN HAZMAT NET (independent of keyword detection).
    # Some product types (e.g. UNMANNED_AERIAL_VEHICLE / drones) REQUIRE
    # contains_battery_or_cell + number_of_lithium_ion_cells even when the
    # title/description contain none of the battery keywords, so _is_batt stays
    # False and the keyword-gated block below never runs. The dashboard, however,
    # still marks these two fields [CODE-OWNED] "filled on Preview" purely by
    # field NAME -- so the AI is told not to fill them and Preview never fills
    # them either. Result: both sit missing and the auto-fix loop stalls at
    # IDENTICAL forever. Ground truth is the schema, not keywords: if THIS
    # product type declares/requires these fields, fill their safe defaults
    # regardless of _is_batt. Only the two flagged fields -- we do NOT force the
    # full lithium composite block onto a non-keyword product.
    def _schema_wants(_f):
        return (_f in required) or isinstance(props.get(_f), dict)

    # _cbc_value: moved to listing/attributes_helpers.py (plan B2, verbatim).

    # ANSWERED ONLY WHEN AMAZON ACTUALLY REQUIRES IT, and answered HONESTLY.
    #
    # Two changes from before. It used to fire on _schema_wants -- which is true
    # for any type that merely declares the field -- and it only ever knew how to
    # say yes. Now: a field Amazon does not require is left alone unless this
    # product really has a battery, and when it is required the answer follows
    # the evidence rather than defaulting to yes.
    if (("contains_battery_or_cell" in required) or _has_battery) \
            and "contains_battery_or_cell" not in A:
        _cbc = _cbc_value(props.get("contains_battery_or_cell", {}), _has_battery)
        if _cbc is not None:
            A["contains_battery_or_cell"] = [{"value": _cbc, "marketplace_id": mid}]
    if (("number_of_lithium_ion_cells" in required) or _has_battery) \
            and "number_of_lithium_ion_cells" not in A:
        A["number_of_lithium_ion_cells"] = [{"value": (1 if _has_battery else 0),
                                             "marketplace_id": mid}]

    _is_lithium = _is_batt and any(w in _hay_sf for w in ["lithium", "li-ion", "li_ion", "rechargeable", "usb"])
    if _is_lithium:
        # contains_battery_or_cell -> boolean (yes, it does)
        if "contains_battery_or_cell" not in A:
            A["contains_battery_or_cell"] = [{"value": True, "marketplace_id": mid}]
        # number_of_lithium_ion_cells -> integer
        if "number_of_lithium_ion_cells" not in A:
            A["number_of_lithium_ion_cells"] = [{"value": 1, "marketplace_id": mid}]
        # number_of_lithium_metal_cells -> 0 (it's ion, not metal)
        if "number_of_lithium_metal_cells" not in A:
            A["number_of_lithium_metal_cells"] = [{"value": 0, "marketplace_id": mid}]
        # lithium_battery -> composite: packaging, energy_content (value+unit),
        # weight. Built-in cell -> "batteries_contained_in_equipment".
        if "lithium_battery" not in A:
            A["lithium_battery"] = [{
                "packaging": [{"value": "batteries_contained_in_equipment"}],
                "energy_content": [{"value": 10.0, "unit": "watt_hours"}],
                "weight": [{"value": 50.0, "unit": "grams"}],
                "marketplace_id": mid,
            }]

    # power_source_type -> simple enum [{value}]
    if ("power_source_type" in pa or _has_prop("power_source_type") or _is_batt) and "power_source_type" not in A:
        _ps_enum = []
        try:
            _psp = props["power_source_type"]
            _ps_enum = (_psp.get("items", {}).get("properties", {}).get("value", {}).get("enum")
                        or _psp.get("items", {}).get("enum") or _psp.get("enum") or [])
        except Exception:
            _ps_enum = []
        _applied_ps = str(pa.get("power_source_type", "")).strip().lower().replace(" ", "_")
        _syn = {"usb": "battery_powered", "usb-c": "battery_powered", "usb_c": "battery_powered",
                "rechargeable": "battery_powered", "battery": "battery_powered",
                "corded": "corded_electric", "mains": "corded_electric"}
        _ps_val = _syn.get(_applied_ps, _applied_ps) or ("battery_powered" if _is_batt else "")
        if _ps_enum and _ps_val not in _ps_enum:
            _ps_val = "battery_powered" if "battery_powered" in _ps_enum else _ps_enum[0]
        if _ps_val:
            A["power_source_type"] = [{"value": _ps_val, "marketplace_id": mid}]

    # has_multiple_battery_powered_components -> boolean. Answering "no" about a
    # product with no battery at all is not wrong, but it is a battery question
    # on a vacuum flask -- so it goes with the rest of the group unless Amazon
    # actually asks. (Line 6113 fills it too, but only when Amazon has named it
    # as a required field, which is the case where answering IS correct.)
    if ("has_multiple_battery_powered_components" in pa
            or "has_multiple_battery_powered_components" in required
            or _has_battery) \
            and "has_multiple_battery_powered_components" not in A:
        A["has_multiple_battery_powered_components"] = [{"value": False, "marketplace_id": mid}]

    # ghs (Globally Harmonized System hazard labelling). Amazon models this as a
    # nested object, NOT a flat value -- a flat string like "not_applicable" is
    # rejected ("GHS Class is required but missing"). For most non-chemical retail
    # items GHS is optional and best OMITTED. BUT some product types (e.g.
    # FLASHLIGHT in some marketplaces) list `ghs` as REQUIRED -- there we must send
    # a real structure built from the schema's own allowed values, or Amazon
    # rejects the listing for the missing required field.
    # GHS (Globally Harmonized System chemical hazard labelling). Amazon models it
    # as a NESTED object and makes it REQUIRED only when
    # supplier_declared_dg_hz_regulation is set to "ghs". There is NO "not
    # applicable" GHS class -- the only values are real chemical hazards
    # (explosive, flammable, corrosive, toxic, ...), so a non-chemical product like
    # a flashlight can never legitimately satisfy a GHS requirement. Strategy:
    #   1. Drop any flat/garbage ghs value the AI may have written.
    #   2. Work out whether GHS is actually being demanded (static required OR
    #      dg_regulation == ghs).
    #   3. If demanded: build a valid structure from the schema. If the schema has
    #      no genuinely-applicable "no real hazard" class, prefer to flip
    #      dg_regulation AWAY from ghs to "not_applicable" so GHS is no longer
    #      required -- correct for a non-chemical item -- rather than mislabel the
    #      product with a real hazard class.
    def _dg_value():
        v = A.get("supplier_declared_dg_hz_regulation")
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return str(v[0].get("value", "")).lower()
        return str(v or "").lower()
    # 1) drop flat/garbage ghs
    if "ghs" in A and not (isinstance(A.get("ghs"), list)
                           and A["ghs"] and isinstance(A["ghs"][0], dict)):
        del A["ghs"]
    # 2) is GHS demanded?
    _ghs_demanded = ("ghs" in required) or (_dg_value() == "ghs")
    if _ghs_demanded and "ghs" not in A:
        _ghs_obj = _build_ghs_from_schema(props.get("ghs", {}), mid)
        # _build_ghs_from_schema only returns a value if the schema offered a
        # "no real hazard"-style option. For FLASHLIGHT it won't (all classes are
        # real hazards) -> _ghs_obj is None -> flip dg_regulation off ghs instead.
        if _ghs_obj is not None:
            A["ghs"] = _ghs_obj
        else:
            # no honest GHS class -> stop declaring GHS as the DG regulation
            _dg_enum = []
            try:
                _dgp = props.get("supplier_declared_dg_hz_regulation", {})
                _dgi = _dgp.get("items", {}) if isinstance(_dgp.get("items"), dict) else {}
                _dgip = _dgi.get("properties", {}) if isinstance(_dgi, dict) else {}
                _dgvp = _dgip.get("value", {}) if isinstance(_dgip, dict) else {}
                _dg_enum = (_dgvp.get("enum") or _dgip.get("enum") or _dgi.get("enum") or [])
            except Exception:
                _dg_enum = []
            _safe = "not_applicable"
            if _dg_enum:
                _low = {str(e).lower(): e for e in _dg_enum}
                _safe = _low.get("not_applicable") or next(
                    (e for e in _dg_enum if str(e).lower() != "ghs"), _dg_enum[0])
            A["supplier_declared_dg_hz_regulation"] = [{"value": _safe, "marketplace_id": mid}]

    # Fields whose items REQUIRE language_tag + value (per schema):
    # special_feature, warranty_description, safety_data_sheet_url. Build them
    # with language_tag so Amazon accepts them (missing language_tag reads as
    # "required but missing").
    def _put_lang(field, value, split=False):
        if split:
            _parts = [s.strip() for s in str(value).replace(";", ",").split(",") if s.strip()]
            if _parts:
                A[field] = [{"value": p, "language_tag": _lang_sf, "marketplace_id": mid}
                            for p in _parts[:5]]
        else:
            if str(value).strip():
                A[field] = [{"value": str(value).strip(), "language_tag": _lang_sf,
                             "marketplace_id": mid}]

    if "special_feature" in pa and str(pa.get("special_feature", "")).strip():
        _put_lang("special_feature", pa["special_feature"], split=True)
    if "warranty_description" in pa and str(pa.get("warranty_description", "")).strip():
        _put_lang("warranty_description", pa["warranty_description"])
    if "safety_data_sheet_url" in pa and str(pa.get("safety_data_sheet_url", "")).strip():
        _put_lang("safety_data_sheet_url", pa["safety_data_sheet_url"])

    # --- required-field backfill: listing/attributes_phases (plan B4, verbatim)
    _backfilled = _phase_required_backfill(A, pa, props, required, mid, g)
    # FINAL GHS SAFETY NET (runs after dg_regulation is fully resolved above).
    # If, after everything, the DG regulation is "ghs" but we have no valid ghs
    # object, the listing WILL be rejected ("GHS Class is required but missing").
    # A flashlight has no honest GHS hazard class, so flip the regulation to a
    # non-ghs value instead of mislabelling the product.
    def _dg_value_final():
        v = A.get("supplier_declared_dg_hz_regulation")
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return str(v[0].get("value", "")).lower()
        return str(v or "").lower()
    if _dg_value_final() == "ghs":
        _has_valid_ghs = (isinstance(A.get("ghs"), list) and A.get("ghs")
                          and isinstance(A["ghs"][0], dict) and A["ghs"][0].get("classification"))
        if not _has_valid_ghs:
            _ghs_obj2 = _build_ghs_from_schema(props.get("ghs", {}), mid)
            if _ghs_obj2 is not None:
                A["ghs"] = _ghs_obj2
            else:
                _dg_enum2 = []
                try:
                    _dgp = props.get("supplier_declared_dg_hz_regulation", {})
                    _dgi = _dgp.get("items", {}) if isinstance(_dgp.get("items"), dict) else {}
                    _dgip = _dgi.get("properties", {}) if isinstance(_dgi, dict) else {}
                    _dgvp = _dgip.get("value", {}) if isinstance(_dgip, dict) else {}
                    _dg_enum2 = (_dgvp.get("enum") or _dgip.get("enum") or _dgi.get("enum") or [])
                except Exception:
                    _dg_enum2 = []
                _safe2 = "not_applicable"
                if _dg_enum2:
                    _low2 = {str(e).lower(): e for e in _dg_enum2}
                    _safe2 = _low2.get("not_applicable") or next(
                        (e for e in _dg_enum2 if str(e).lower() != "ghs"), _dg_enum2[0])
                A["supplier_declared_dg_hz_regulation"] = [{"value": _safe2, "marketplace_id": mid}]
                A.pop("ghs", None)   # not needed once regulation isn't ghs

    # CONDITIONALLY-REQUIRED SAFETY NET ------------------------------------------
    # Amazon does NOT list these in the static `required` set, so the backfill
    # loop above never fills them -- yet VALIDATION_PREVIEW demands them anyway for
    # battery/electronic items. That is the exact "required but missing" cycle on
    # model_name / special_feature / warranty_description /
    # battery_installation_device_type, plus the hazmat structure error. Fill them
    # here, schema-driven, so the listing validates on the FIRST preview.
    # _enum_of_prop: moved to listing/attributes_helpers.py (plan B2, verbatim).

    _cond_title = g("Item Name") or g("Title") or ""
    _cond_hay   = (_cond_title + " " + g("Product Description")).lower()
    _cond_rech  = any(w in _cond_hay for w in ["rechargeable", "usb", "usb-c", "type-c", "li-ion", "lithium"])

    # --- ALWAYS-REBUILD-CLEAN for the conditionally-required fields ----------
    # ROOT CAUSE of the recurring "X is required but missing" while the box looks
    # filled: earlier layers (the _put_lang fills and the required-backfill loop)
    # may put a HALF-BUILT or EMPTY value into A under these keys. The old guards
    # here were `if "field" not in A:` -- so when a broken value already existed,
    # the safety net SKIPPED it ("already present") and the broken value shipped,
    # and Amazon reported it missing/invalid. Fix: don't trust an existing value
    # -- validate it, and rebuild into Amazon's exact array-of-one structure
    # whenever it's absent, empty, or malformed.
    _lang_c = "en_US" if mid == US_MARKETPLACE_ID else "en_GB"

    # _valid_text_attr: moved to listing/attributes_helpers.py (plan B2, verbatim).

    # model_name (free text): mirror the generated model number, else short title.
    if not _valid_text_attr(A.get("model_name")):
        _mn = g("Model Number") or (_cond_title[:60].strip()) or "Standard"
        A["model_name"] = [{"value": _mn, "marketplace_id": mid}]

    # special_feature (SINGULAR is what Amazon wants; the AI often writes the
    # PLURAL `special_features`). Reconcile: prefer an already-valid singular,
    # else pull from singular/plural in the row JSON, else a sensible default.
    if not _valid_text_attr(A.get("special_feature")):
        _sf_src = ""
        for _k in ("special_feature", "special_features"):
            _v = pa.get(_k)
            if isinstance(_v, str) and _v.strip():
                _sf_src = _v.strip(); break
            if isinstance(_v, list) and _v:
                _sf_src = ", ".join(str(x) for x in _v if str(x).strip()); break
        if not _sf_src:
            _sf_src = "Rechargeable" if _cond_rech else "Portable"
        _sf_vals = [s.strip() for s in _sf_src.replace(";", ",").split(",") if s.strip()][:5] or [_sf_src]
        A["special_feature"] = [{"value": v, "language_tag": _lang_c, "marketplace_id": mid} for v in _sf_vals]
    # never ship the plural variant -- Amazon ignores it and it confuses audits
    A.pop("special_features", None)

    # warranty_description (free text). Use ONE consistent default everywhere
    # (the required-backfill loop used "No warranty"; reconcile to the real one).
    if not _valid_text_attr(A.get("warranty_description")):
        A["warranty_description"] = [{"value": "1 Year Manufacturer Warranty",
                                      "language_tag": _lang_c, "marketplace_id": mid}]

    # battery_installation_device_type: this field is NOT really free-text even
    # when the schema hides its enum -- Amazon validates it SERVER-SIDE against
    # battery.cell_composition. Sending the product name ("Flashlight"/"flashlight")
    # or "Installed in device" is REJECTED ("not a valid value"). The accepted
    # values are device-CATEGORY tokens (underscored). For a consumer torch the
    # correct token is "installed_in_equipment" (verified via getDefinitions:
    # allowed = installed_in_equipment | installed_in_vehicle | installed_in_vessel
    # | not_installed; a built-in battery = installed_in_equipment). Override via config
    # so it can be changed without editing code.
    # battery_installation_device_type: the allowed value depends on the battery
    # CHEMISTRY (Amazon's allOf[98] conditional). VERIFIED via getDefinitions:
    #   - lithium chemistry (lithium_ion/metal/polymer, etc.) -> the THEN branch
    #     allows ONLY: installed_in_vehicle | installed_in_vessel | not_installed
    #     (installed_in_equipment is NOT allowed for lithium!)
    #   - non-lithium -> the ELSE branch also allows installed_in_equipment.
    # A built-in lithium torch that isn't a vehicle/vessel -> "not_installed".
    # Detect the chemistry we actually send in A["battery"].
    _cc_sent = ""
    try:
        _cc_sent = str(A["battery"][0]["cell_composition"][0]["value"]).strip().lower()
    except Exception:
        _cc_sent = ""
    _is_lith = ("lithium" in _cc_sent) or (not _cc_sent and (_cond_rech or "lithium" in _cond_hay))
    _bidt_default = (config.get("battery_installation_device_type_default")
                     or ("not_installed" if _is_lith else "installed_in_equipment"))
    _bidt_enum = _enum_of_prop(props.get("battery_installation_device_type", {}))
    # This block had no guard at all, so EVERY listing declared how its battery
    # is installed -- including a vacuum flask, which was told
    # "installed_in_equipment" on the same payload that said batteries_required
    # is false. Where a battery is installed is a battery question; it is asked
    # only when there is a battery, or when Amazon requires an answer.
    _want_bidt = ("battery_installation_device_type" in pa
                  or "battery_installation_device_type" in required
                  or _has_battery)
    if not _want_bidt:
        A.pop("battery_installation_device_type", None)
    elif _bidt_enum:
        # Pick the chemistry-correct default FIRST (for lithium that's
        # not_installed; installed_in_equipment is rejected for lithium). Only
        # fall back to other tokens if the default isn't an allowed option.
        _pick = None
        for _cand in _bidt_enum:
            if str(_cand).strip().lower() == _bidt_default.lower():
                _pick = _cand; break
        if not _pick:
            # ordered preference that is SAFE for lithium first
            _pref = (["not_installed", "installed_in_vehicle", "installed_in_vessel"]
                     if _is_lith else
                     ["installed_in_equipment", "not_installed"])
            for _want in _pref:
                for _cand in _bidt_enum:
                    if str(_cand).strip().lower() == _want:
                        _pick = _cand; break
                if _pick: break
        A["battery_installation_device_type"] = [{"value": _pick or _bidt_enum[0], "marketplace_id": mid}]
    else:
        # no enum exposed -> use the chemistry-correct token (NOT the product name)
        _cur = ""
        if isinstance(A.get("battery_installation_device_type"), list) and A["battery_installation_device_type"]:
            _cur = str(A["battery_installation_device_type"][0].get("value", "")).strip()
        # replace any known-bad value. For lithium, installed_in_equipment is BAD.
        _bad_tokens = ["flashlight", "torch", "installed in device", "installed_in_device",
                       "flash light", "consumer_electronics"]
        if _is_lith:
            _bad_tokens.append("installed_in_equipment")
        _bad = (not _cur) or _cur.lower() in _bad_tokens
        _val = _bidt_default if _bad else _cur
        A["battery_installation_device_type"] = [{"value": _val, "marketplace_id": mid}]

    # --- SCHEMA-INDEPENDENT COMPLIANCE HARDENING -----------------------------
    # The fixes above lean on the live schema (enum snapping). But the schema
    # call can intermittently fail ("Amazon's value lists haven't loaded"), and
    # when props is empty the enum branches do nothing, so raw bad values (e.g.
    # the word "cell", or "Flashlight") sail through to Amazon. These fields have
    # KNOWN-GOOD values for a battery item regardless of schema, so set them
    # deterministically here. This is what makes the listing pass even on a run
    # where the schema didn't load.
    _bs_hay = (_cond_title + " " + g("Product Description") + " "
               + g("Included Components") + " " + g("Bullet Point 1")).lower()
    _has_battery = (
        _truthy(g("Batteries Included") or g("Are Batteries Included") or g("batteries_included"))
        or _cond_rech or "battery" in _bs_hay or "lithium" in _bs_hay
    )

    if _has_battery:
        # contains_battery_or_cell: the CORRECT value depends on the field's schema
        # type, which differs by product type/marketplace:
        #   - if it's an ENUM (dropdown), Amazon wants the allowed STRING (e.g. "Yes")
        #   - if it's a BOOLEAN, Amazon wants JSON true/false
        # The old code always sent boolean True, which fails when the field is an
        # enum ("select an approved value from the list"). Detect and match.
        _cbc_prop = props.get("contains_battery_or_cell", {})
        _cbc_enum = _enum_of_prop(_cbc_prop)
        if _cbc_enum:
            # pick the allowed value meaning "yes"
            _yes = None
            for _e in _cbc_enum:
                if str(_e).strip().lower() in ("yes", "true", "1"):
                    _yes = _e; break
            A["contains_battery_or_cell"] = [{"value": _yes or _cbc_enum[0], "marketplace_id": mid}]
        else:
            # boolean type, or schema not loaded -> JSON boolean true is the
            # documented default shape for this attribute.
            A["contains_battery_or_cell"] = [{"value": True, "marketplace_id": mid}]

        # battery_installation_device_type: the allowed value depends on battery
        # CHEMISTRY. For lithium, installed_in_equipment is REJECTED; valid are
        # not_installed | installed_in_vehicle | installed_in_vessel. Detect what
        # chemistry we actually sent and choose accordingly.
        _cc_sent2 = ""
        try:
            _cc_sent2 = str(A["battery"][0]["cell_composition"][0]["value"]).strip().lower()
        except Exception:
            _cc_sent2 = ""
        _is_lith2 = ("lithium" in _cc_sent2) or (not _cc_sent2 and _has_battery)
        _bidt_default2 = (config.get("battery_installation_device_type_default")
                          or ("not_installed" if _is_lith2 else "installed_in_equipment"))
        _bidt_enum2 = _enum_of_prop(props.get("battery_installation_device_type", {}))
        _cur_bidt = ""
        if isinstance(A.get("battery_installation_device_type"), list) and A["battery_installation_device_type"]:
            _cur_bidt = str(A["battery_installation_device_type"][0].get("value", "")).strip()
        # for lithium, treat installed_in_equipment in the current value as BAD
        _cur_is_bad = _cur_bidt.lower() in (
            "flashlight", "torch", "installed in device", "installed_in_device",
            "flash light", "consumer_electronics") or (_is_lith2 and _cur_bidt.lower() == "installed_in_equipment")
        if _bidt_enum2:
            if _cur_bidt not in _bidt_enum2 or _cur_is_bad:
                _pick2 = None
                for _cand in _bidt_enum2:
                    if str(_cand).strip().lower() == _bidt_default2.lower():
                        _pick2 = _cand; break
                if not _pick2:
                    _pref2 = (["not_installed", "installed_in_vehicle", "installed_in_vessel"]
                              if _is_lith2 else ["installed_in_equipment", "not_installed"])
                    for _want in _pref2:
                        for _cand in _bidt_enum2:
                            if str(_cand).strip().lower() == _want:
                                _pick2 = _cand; break
                        if _pick2: break
                A["battery_installation_device_type"] = [{"value": _pick2 or _bidt_enum2[0], "marketplace_id": mid}]
        else:
            A["battery_installation_device_type"] = [
                {"value": (_bidt_default2 if (not _cur_bidt or _cur_is_bad) else _cur_bidt), "marketplace_id": mid}]

    # wattage: RECURRING PROBLEM. Amazon needs wattage as {value:<number>,
    # unit:<watts>} together. But the value/unit often arrive as separate nested
    # keys, and when the schema fails to load we can't confirm the unit token --
    # so a number ships with no unit and Amazon rejects it ("None ... Wattage").
    # Wattage is OPTIONAL for a flashlight/torch. The safe, permanent fix is:
    # only KEEP wattage if we have BOTH a real number AND can pair a unit with it;
    # otherwise DROP it entirely. A torch listing is valid without wattage.
    _watt_in_a = A.get("wattage")

    # _watt_number: moved to listing/attributes_helpers.py (plan B2, verbatim).

    # Determine if this product type even declares wattage (when schema loaded).
    _watt_declared = isinstance(props.get("wattage"), dict) and bool(props.get("wattage"))
    _wnum = _watt_number(_watt_in_a) if _watt_in_a is not None else ""

    if _wnum and _watt_declared:
        # we have a number AND the schema is present -> ship value+unit together
        try:
            _wval = float(_wnum) if ("." in _wnum) else int(_wnum)
        except Exception:
            _wval = _wnum
        A["wattage"] = [{"value": _wval, "unit": "watts", "marketplace_id": mid}]
    else:
        # no number, OR schema not loaded (can't confirm the unit) -> drop it.
        # Torches don't require wattage, so this never blocks the listing.
        if "wattage" in A:
            A.pop("wattage", None)
            try:
                console.print("  [dim]wattage dropped (optional for this product; "
                              "avoids the missing-unit rejection)[/dim]")
            except Exception:
                pass

    # FINAL wattage guard (bulletproof): never return an empty/None/partial wattage.
    # _has_real_number: moved to listing/attributes_helpers.py (plan B2, verbatim).

    if "wattage" in A:
        _wf = A.get("wattage")
        _ok = _has_real_number(_wf) and isinstance(_wf, list) and _wf and isinstance(_wf[0], dict) and str(_wf[0].get("unit", "")).strip()
        if not _ok:
            A.pop("wattage", None)
            try:
                console.print("  [dim]wattage dropped (no real value/unit) -- optional for this product[/dim]")
            except Exception:
                pass

    # never ship the plural special_features (belt-and-braces; also done above)
    A.pop("special_features", None)

    # hazmat: build from the LIVE schema structure, ALWAYS rebuilt clean.
    # Two real Amazon errors this fixes (seen on FLASHLIGHT/US):
    #   1) "Hazmat Aspect does not have the expected value(s)" -> the `aspect`
    #      sub-field must be a value from its enum. For flashlights the schema's
    #      ONLY allowed aspect is 'united_nations_regulatory_id'.
    #   2) "field 'value' ... does not have enough values (min 1)" -> the `value`
    #      sub-field is FREE TEXT (no enum), so the old loop skipped it and left it
    #      empty. We must fill it. For a lithium battery packed inside the device
    #      the correct UN id is UN3481 (lithium-ion batteries contained in
    #      equipment). We only set hazmat when the product actually has a battery.
    #
    # Rebuild policy: do NOT trust a pre-existing hazmat value (it may be a flat
    # {value:..} or half-built). Validate it; if any enum sub-field is wrong or the
    # required free-text `value` is blank, rebuild the whole object.
    _hz_prop = props.get("hazmat", {}) if isinstance(props.get("hazmat"), dict) else {}
    if _hz_prop:
        _hz_items = _hz_prop.get("items", {}) if isinstance(_hz_prop.get("items"), dict) else {}
        _hz_props = _hz_items.get("properties", {}) if isinstance(_hz_items, dict) else {}
        # One-time visibility: print hazmat's real sub-fields + their allowed values.
        try:
            _hz_report = {}
            for _sk, _sv in _hz_props.items():
                _hz_report[_sk] = [str(x) for x in (_sv.get("enum") or [])] if isinstance(_sv, dict) else "free-text"
            console.print(f"  [dim]hazmat schema sub-fields: {_hz_report}[/dim]")
        except Exception:
            pass

        # Does this product carry a (lithium) battery? hazmat is only meaningful then.
        _hz_has_batt = (
            _truthy(g("Batteries Included") or g("Are Batteries Included") or g("batteries_included"))
            or _cond_rech
            or "battery" in _cond_hay or "lithium" in _cond_hay
        )

        # Build the correct object from the live sub-fields.
        _hz_obj = {"marketplace_id": mid}
        for _sk, _sv in _hz_props.items():
            if _sk in ("marketplace_id", "language_tag"):
                continue
            _senum = [str(x) for x in (_sv.get("enum") or [])] if isinstance(_sv, dict) else []
            if _senum:
                # enum sub-field (e.g. `aspect`): prefer a not-applicable style
                # value if the schema offers one; otherwise take the only/first
                # allowed value (for flashlights that's united_nations_regulatory_id).
                _low = {e.lower(): e for e in _senum}
                _val = (_low.get("not_applicable") or _low.get("none")
                        or _low.get("no_warning_applicable")
                        or next((e for e in _senum if "not_applic" in e.lower() or "no_haz" in e.lower()), None)
                        or _senum[0])
                _hz_obj[_sk] = _val
            elif _sk == "value" and _hz_has_batt:
                # FREE-TEXT required value. For a battery-in-equipment the correct
                # UN id is UN3481.
                #
                # THE GATE THAT WAS MISSING. The comment here used to read "Only
                # reached when hazmat is being built, which is itself gated on a
                # battery being present" -- and there was no such gate.
                # `_hz_has_batt` was worked out six lines above, under the comment
                # "hazmat is only meaningful then", and then never read. So every
                # product whose schema declares a hazmat field was told to Amazon
                # as UN3481 -- "lithium-ion batteries contained in equipment" --
                # whether or not it had a battery in it.
                #
                # That is a dangerous-goods DECLARATION made on the owner's behalf
                # about a product he never said was hazardous, which is the same
                # thing CLAUDE.md Rule 1 forbids for the GTIN exemption. This file
                # already refuses to do it elsewhere: the GHS block above would
                # rather flip the DG regulation away from "ghs" than "mislabel the
                # product with a real hazard class". The branch below, for when the
                # schema fails to load, gates on exactly this and always did.
                _hz_obj[_sk] = "UN3481"

        # If aspect resolved to the UN regulatory id but value somehow didn't get
        # set (schema variation), guarantee the UN number is present -- for a
        # product that actually carries one. Without a battery this line put the
        # UN number back after the gate above had left it out, because an `aspect`
        # enum offering no not-applicable option falls through to _senum[0], which
        # on these product types IS united_nations_regulatory_id.
        if (_hz_has_batt
                and str(_hz_obj.get("aspect", "")).lower() == "united_nations_regulatory_id"
                and not _hz_obj.get("value")):
            _hz_obj["value"] = "UN3481"

        # Decide whether the existing value is already valid (so we don't churn).
        _existing = A.get("hazmat")
        _needs = True
        if isinstance(_existing, list) and _existing and isinstance(_existing[0], dict):
            _needs = False
            _ex0 = _existing[0]
            for _sk, _sv in _hz_props.items():
                _senum = [str(x).lower() for x in (_sv.get("enum") or [])] if isinstance(_sv, dict) else []
                if _senum:
                    if str(_ex0.get(_sk, "")).lower() not in _senum:
                        _needs = True; break
                elif _sk == "value":
                    # required free-text value must be non-empty
                    if not str(_ex0.get(_sk, "")).strip():
                        _needs = True; break

        _has_real_subfield = any(k not in ("marketplace_id", "language_tag") for k in _hz_obj)
        if _needs:
            if _has_real_subfield and _hz_obj.get("value"):
                A["hazmat"] = [_hz_obj]
            else:
                # Couldn't build a valid hazmat object -> drop it rather than ship
                # an invalid shape. hazmat is conditionally-required and the lithium
                # info is also carried by the dangerous-goods regulation field.
                #
                # A PRODUCT WITH NO BATTERY LANDS HERE, and that is the right
                # outcome: nothing is declared. If Amazon does require hazmat for
                # this product type it will say so, and a person can answer it --
                # the same way an absent barcode is left for Amazon to refuse
                # rather than answered with an exemption nobody asked for.
                if not _hz_has_batt and isinstance(A.get("hazmat"), (list, dict)):
                    try:
                        console.print("  [dim]hazmat dropped -- no battery evidence "
                                      "on this product, so there is no dangerous "
                                      "goods declaration to make[/dim]")
                    except Exception:
                        pass
                A.pop("hazmat", None)
    else:
        # SCHEMA DIDN'T LOAD for hazmat (props empty / value lists failed). We
        # still must not ship a half-built hazmat that a manual edit may have left
        # in the row (e.g. {aspect: united_nations_regulatory_id} with no value,
        # or a flat scalar "not_applicable"). Repair it deterministically.
        _hz_batt = (
            _truthy(g("Batteries Included") or g("Are Batteries Included") or g("batteries_included"))
            or _cond_rech or "battery" in _cond_hay or "lithium" in _cond_hay
        )
        _ex = A.get("hazmat")
        _ex0 = _ex[0] if (isinstance(_ex, list) and _ex and isinstance(_ex[0], dict)) else {}
        _aspect = str(_ex0.get("aspect", "")).strip()
        _value  = str(_ex0.get("value", "")).strip()
        if _hz_batt:
            # Known-correct hazmat for a lithium battery packed in equipment.
            A["hazmat"] = [{
                "aspect": _aspect or "united_nations_regulatory_id",
                "value":  _value or "UN3481",
                "marketplace_id": mid,
            }]
        else:
            # No battery and no schema to validate against -> a flat scalar or
            # partial object is risky; drop it (dg regulation carries any info).
            if not (_aspect and _value):
                A.pop("hazmat", None)
    return _backfilled, _has_battery
