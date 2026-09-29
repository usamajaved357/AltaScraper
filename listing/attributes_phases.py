"""listing/attributes_phases.py -- ordered phases of build_api_attributes.

Plans B3 and B4 (docs/plans/build-api-attributes.md): the text/offer, the
dimension, the pa-mapping and the required-field backfill phases, MOVED VERBATIM out of amazon_listing_generator.build_api_attributes and
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

from listing.attributes_helpers import _allowed_values
from listing.builder import _clean_price, _fulfillment, _is_blank, _item_props, _offer
from listing.constants import US_MARKETPLACE_ID
from listing.flat_row import _COMPLIANCE_PASSTHROUGH, resolve_account_brand
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
