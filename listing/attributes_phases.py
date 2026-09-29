"""listing/attributes_phases.py -- ordered phases of build_api_attributes.

Plan B3 (docs/plans/build-api-attributes.md): the text/offer and the dimension
phases, MOVED VERBATIM out of amazon_listing_generator.build_api_attributes and
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

from listing.builder import _clean_price, _fulfillment, _is_blank, _item_props, _offer
from listing.flat_row import resolve_account_brand
from listing.shaper import _lang_for, _shape_dimensions, _shape_simple, shape_by_schema
from listing.value_snap import _dim_axis_raw


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
