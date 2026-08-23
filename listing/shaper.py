"""listing/shaper.py — schema shaping only.

shape_by_schema reads the live Amazon product-type schema and folds a raw value into the
EXACT shape Amazon requires (array vs object, value vs decimal_value, unit enums, nested
sub-attributes). It NEVER guesses the shape — it is driven entirely by the schema passed
in. _lang_for maps a marketplace id to the correct Amazon language_tag. Both moved
verbatim from amazon_listing_generator.py in Phase 5 (behaviour unchanged).
"""
from listing.constants import US_MARKETPLACE_ID
import re
from listing.builder import _is_blank, _item_props, _truthy


def _lang_for(mid: str) -> str:
    """Amazon language_tag for a marketplace id. US needs en_US; UK needs en_GB.
    Sending the wrong one triggers 'Invalid language data provided' on validate."""
    return "en_US" if str(mid) == US_MARKETPLACE_ID else "en_GB"


# Keys Amazon uses to SELECT a value, not to carry one. An object holding nothing but
# these is empty data -- sending it is what makes Amazon say a field "does not have
# enough values", because the `value` it wants is simply absent.
_SELECTOR_KEYS = ("marketplace_id", "language_tag")


def _is_empty_shape(s):
    """True when a shaped value carries no actual data -- e.g. [{"language_tag":"en_GB"}]."""
    if s in (None, "", [], {}):
        return True
    if isinstance(s, list):
        return all(_is_empty_shape(x) for x in s)
    if isinstance(s, dict):
        return all(k in _SELECTOR_KEYS for k in s)
    return False


def _missing_required(schema, obj):
    """Sub-keys the schema demands that this shaped object does not have.

    A half-built object is not partial data, it is a guaranteed rejection --
    Amazon answers "'X' is required but missing" and the listing fails. When a
    required sub-key could not be filled, the honest move is to drop the whole
    object: an optional attribute then simply is not sent, and a required one is
    reported as missing by the caller, which is the truth either way.
    """
    req = schema.get("required") or []
    if not isinstance(req, list):
        return []
    return [k for k in req if k not in obj]


def shape_by_schema(schema, raw, mid, lang="en_GB"):
    t = schema.get("type")
    if t == "array":
        shaped = shape_by_schema(schema.get("items", {}) or {}, raw, mid, lang)
        # never emit [{}] or [{"language_tag": ...}] -- Amazon reads that as "no value"
        return [] if _is_empty_shape(shaped) else [shaped]
    if t == "object":
        props = schema.get("properties", {}) or {}
        obj = {}
        if "marketplace_id" in props: obj["marketplace_id"] = mid
        if "language_tag" in props:   obj["language_tag"]   = lang
        num_key = "decimal_value" if "decimal_value" in props else ("value" if "value" in props else None)
        # READ the leaf's declared type instead of assuming it is numeric. The old code
        # only wrote the leaf when float(raw) succeeded, so a TEXT leaf (furniture_leg's
        # color / material / style, all "type": "string") lost its value entirely and we
        # sent [{"language_tag":"en_GB"}] -- exactly Amazon's
        # "'color#1.value' does not have enough values. The required minimum is '1'".
        leaf_type = ""
        if num_key and isinstance(props.get(num_key), dict):
            leaf_type = str(props[num_key].get("type") or "").lower()
        _numeric_leaf = leaf_type in ("number", "integer")
        val = unit = None
        if isinstance(raw, dict):
            val = raw.get("decimal_value", raw.get("value"))
            unit = raw.get("unit")
        elif isinstance(raw, str):
            if _numeric_leaf or (not leaf_type and "unit" in props):
                # "60 centimeters" -> 60 + centimeters
                p = raw.split()
                if p:
                    try:
                        val = float(p[0]); unit = " ".join(p[1:]) or None
                    except ValueError:
                        val = raw          # not a number after all -> keep the text
            else:
                val = raw                  # a text leaf: the whole string IS the value
        elif raw is not None and not isinstance(raw, (list,)):
            val = raw
        if num_key and val not in (None, ""):
            if _numeric_leaf:
                try: obj[num_key] = float(str(val))
                except (ValueError, TypeError): obj[num_key] = val
            else:
                # A TEXT leaf that declares an enum is a closed list, exactly
                # like `unit` below -- and until now only `unit` was checked
                # against its own. See _snap_enum for the measured case.
                _ven = props[num_key].get("enum") if isinstance(props.get(num_key), dict) else None
                _v = val if not isinstance(val, (int, float)) else str(val)
                if _ven:
                    # A TEXT leaf that declares an enum is a CLOSED list, just
                    # like `unit` below -- and until now only `unit` was checked
                    # against its own. strict: an unmatched value is left out,
                    # and _missing_required below then drops the whole object
                    # rather than sending something Amazon will refuse.
                    _snapped_v = _snap_enum(_ven, _v, strict=True)
                    if _snapped_v is not None:
                        obj[num_key] = _snapped_v
                else:
                    obj[num_key] = _v
        if "unit" in props and unit not in (None, ""):
            uen = props["unit"].get("enum")
            _u = _snap_enum(uen, unit, strict=True) if uen else unit
            if _u is None and isinstance(uen, list) and uen and num_key in obj:
                # THE UNIT IS REAL, IT IS JUST NOT ONE AMAZON TAKES HERE.
                #
                # A strict snap will not match "inches" to "centimeters", and it
                # is right not to -- they are different units and pretending
                # otherwise sends 36 where 91.44 belongs. But dropping the whole
                # object then loses a measurement we actually have, and Amazon
                # reports it as MISSING, which sends you looking for a value that
                # was there all along.
                #
                # Measured: RAKE "Weed Slasher 27-Inch", item_height "36.0
                # inches", schema enum ["centimeters"], reply "[E]
                # item_width_height 'Item Height Unit' is required but missing".
                #
                # So convert it instead, and only when the arithmetic is exact.
                # convert_unit knows length and mass and returns None for
                # anything else, so an unconvertible unit still falls through to
                # the old behaviour -- reported missing rather than guessed.
                for _cand in uen:
                    _conv = convert_unit(obj.get(num_key), unit, _cand)
                    if _conv is not None:
                        obj[num_key] = _conv
                        _u = _cand
                        break
            if _u is not None:
                obj["unit"] = _u
        elif "unit" in props:
            # A ONE-VALUE ENUM IS NOT A CHOICE, and leaving it empty fails the
            # listing over the only answer there is.
            #
            # Measured on a real preview. RAKE, Weed Slasher 27-Inch:
            #
            #     [E] item_width_height 'Item Height Unit' is required but missing
            #
            # and Amazon's own schema for that field says
            #
            #     height.unit  enum: ["centimeters"]
            #
            # One permitted value. There is nothing for a person to decide and
            # nothing for the AI to work out -- any answer other than
            # "centimeters" is invalid, so an empty one is the only way to get it
            # wrong. It was blocking the preview of an otherwise complete
            # listing.
            #
            # Deliberately ONLY when the list has exactly one entry. Two or more
            # and the choice is real (centimeters vs inches changes the number
            # beside it), so it stays missing and is reported, which is what
            # makes the report worth reading.
            _uen = props["unit"].get("enum")
            if isinstance(_uen, list) and len(_uen) == 1 and _uen[0]:
                obj["unit"] = _uen[0]
        for pk, pv in props.items():
            if pk in ("marketplace_id", "language_tag", "unit", num_key): continue
            if isinstance(pv, dict) and pv.get("type") in ("array", "object"):
                # Only shape a sub-field from ITS OWN data. Passing the whole `raw` down
                # when the key is absent made every sibling sub-field shape itself from
                # unrelated data (or from nothing), producing the empty scaffolds above.
                if isinstance(raw, dict):
                    if pk not in raw:
                        continue
                    sub = raw.get(pk)
                else:
                    sub = raw
                s = shape_by_schema(pv, sub, mid, lang)
                if not _is_empty_shape(s):
                    obj[pk] = s
        # An object missing something the schema REQUIRES is a rejection waiting
        # to happen, not partial data. Dropping it means an optional attribute
        # is simply not sent; a required one is reported missing by the caller.
        # The selectors are excluded because they are added above, not supplied.
        if _missing_required(schema, obj):
            return {}
        return obj
    return raw.get("decimal_value", raw.get("value")) if isinstance(raw, dict) else raw


# --- measurement/enum shapers moved from amazon_listing_generator.py (Phase 5, verbatim). _shape_list_price stays in the engine (mutable MARKETPLACE_ID). ---

def _split_value_unit(s):
    """'30 centimetres' -> (30.0,'centimetres'); '1.5 kg' -> (1.5,'kg'); '7' -> (7.0,None).
    Also handles Amazon snake_case units (the schema-native shape) like
    '80.0 kilometers_per_hour' -> (80.0, 'kilometers_per_hour'), which is what
    the dashboard's AI suggester emits when it fills a nested value+unit field
    as a single string. Prior to this fix the unit character class excluded
    underscores/hyphens, so '80.0 kilometers_per_hour' matched nothing and the
    whole string was written as a bare value with no unit -- Amazon then
    rejected the listing with 'The provided value for Maximum Speed is invalid'
    (or 'can't accept the milliamp_hour you entered for Battery Capacity Unit'
    for the battery capacity case)."""
    m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z][A-Za-z0-9 ._-]*)?\s*$", str(s))
    if not m:
        return None, None
    unit = (m.group(2) or "").strip() or None
    return float(m.group(1)), unit

def _norm_tok(s) -> str:
    s = str(s).strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    s = s.replace("metre", "meter").replace("litre", "liter")
    return s[:-1] if s.endswith("s") else s


# How many of a base unit each one is. Length in millimetres, mass in grams --
# the base is arbitrary, only the ratios matter.
#
# KEYED ON WHAT _norm_tok ACTUALLY PRODUCES, which is not always the singular.
# It strips one trailing "s", so "inches" arrives as "inche" and "feet" stays
# "feet". Writing the tidy singular here and hoping is how "36 inches" silently
# failed to convert while "1 foot" worked -- so both forms are listed and the
# test below feeds the real spellings through rather than the neat ones.
_UNIT_SCALE = {
    "length": {"millimeter": 1.0, "centimeter": 10.0, "meter": 1000.0,
               "inch": 25.4, "inche": 25.4,
               "foot": 304.8, "feet": 304.8, "ft": 304.8,
               "yard": 914.4, "mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4},
    "mass":   {"gram": 1.0, "kilogram": 1000.0, "milligram": 0.001,
               "ounce": 28.349523125, "pound": 453.59237,
               "g": 1.0, "kg": 1000.0, "mg": 0.001, "oz": 28.349523125,
               "lb": 453.59237},
}


def _dimension_of(tok):
    for dim, table in _UNIT_SCALE.items():
        if tok in table:
            return dim
    return None


def convert_unit(value, frm, to):
    """`value` expressed in `to`, or None when the two are not comparable.

    ARITHMETIC, NOT A GUESS, and that is the whole justification for doing it at
    all: 36 inches IS 91.44 centimetres, and no judgement is involved.

    MEASURED, on a real preview. RAKE, "Weed Slasher 27-Inch":

        the draft held   item_height  "36.0 inches"
        Amazon's schema  height.unit  enum: ["centimeters"]
        Amazon replied   [E] item_width_height 'Item Height Unit' is required
                             but missing

    All three statements were true at once. _snap_enum refuses to match "inches"
    to "centimeters" -- correctly, because they are different units and saying
    otherwise would send 36 where 91.44 belongs -- and the object was then
    dropped for want of a unit. So the listing was blocked by a measurement it
    HAD, in a unit Amazon would not take, with an error naming the wrong
    problem.

    Only length and mass. Anything else returns None and the value is left
    alone: a unit table is a place to be quietly wrong, so it holds what can be
    checked in a line and nothing else.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    a, b = _norm_tok(frm), _norm_tok(to)
    if not a or not b:
        return None
    if a == b:
        return v
    da, db = _dimension_of(a), _dimension_of(b)
    if not da or da != db:
        return None
    out = v * _UNIT_SCALE[da][a] / _UNIT_SCALE[da][b]
    # Two decimals is what Amazon shows and what every other measurement in this
    # file carries; more just prints float noise (91.44000000000001).
    return round(out + 0.0, 2)

def _snap_enum(enum_list, raw, strict=False):
    """Snap a raw string to the nearest accepted enum token. Returns raw unchanged
    if no confident match (so VALIDATION_PREVIEW surfaces it rather than guessing).

    strict=True returns None instead of the unchanged raw. Use it where the list
    is genuinely CLOSED and an unmatched value can only be rejected -- there,
    passing the value through does not surface anything useful, it just fails
    the listing every time. Measured case:

        [E] unit_count Based on the data from '', the 'count' on the field
        '"type.value"' for the attribute 'Unit Count' is not a valid value.

    Amazon's raw schema for MACHINE_LUBRICANT says, in as many words:

        unit_count.items.properties.type.properties.value.enum
            ["gram", "millilitre"]

    and we send "Count". Returning None lets the caller drop the field rather
    than guess "gram" -- a grease cartridge is not measured in count, and
    picking the first item off the list because it is first is exactly the
    guessing CLAUDE.md rule 4 forbids.

    The default stays False so every existing caller behaves as before.
    """
    if not enum_list:
        return None if (strict and str(raw).strip() == "") else str(raw)
    r  = str(raw).strip().lower()
    rn = r.replace(" ", "_")
    for e in enum_list:                                   # exact
        if str(e).strip().lower() == r:
            return e
    for e in enum_list:                                   # normalised (spaces->_)
        if str(e).strip().lower().replace(" ", "_") == rn:
            return e
    rt = _norm_tok(raw)                                   # spelling/plural (centimetres->centimeter)
    for e in enum_list:
        if _norm_tok(e) == rt:
            return e
    for e in enum_list:                                   # containment
        el = str(e).strip().lower()
        if rn and (rn in el or el in rn):
            return e
    return None if strict else str(raw)

def _item_required(field_schema: dict):
    """The sub-keys Amazon REQUIRES inside this attribute's item object.

    Amazon declares them at items.required for an array attribute and at
    required for a bare object, and this reads whichever is there. Used to
    decide whether a half-built object should be sent at all -- see
    _shape_simple. Selectors are excluded because they are added by us, not
    supplied by the data.
    """
    if not isinstance(field_schema, dict):
        return []
    it = field_schema.get("items")
    src = it if isinstance(it, dict) else field_schema
    req = src.get("required")
    if not isinstance(req, list):
        return []
    return [k for k in req if k not in ("marketplace_id", "language_tag")]


def _sub_req(sub_schema):
    """A nested sub-schema's own required list, wherever it declares it."""
    if not isinstance(sub_schema, dict):
        return []
    it = sub_schema.get("items")
    src = it if isinstance(it, dict) else sub_schema
    req = src.get("required")
    return req if isinstance(req, list) else []


def _coerce_value(val_schema: dict, raw, strict=False):
    enum = val_schema.get("enum")
    if enum:
        return _snap_enum(enum, raw, strict=strict)
    t = val_schema.get("type")
    if t == "boolean":
        return _truthy(raw)
    if t == "integer":
        try:
            return int(float(str(raw)))
        except Exception:
            return raw
    if t == "number":
        try:
            return float(str(raw))
        except Exception:
            return raw
    return str(raw)

def _shape_simple(field_schema: dict, raw, mid: str):
    """Build a one-element attribute array for a scalar/text/measure attribute,
    using the schema's item properties to decide marketplace_id / language_tag /
    value type / unit.

    `raw` can be:
      - a plain string like '80.0 kilometers_per_hour' (typed by user or a
        single-box AI suggestion)
      - a dict like {'value': '80.0', 'unit': 'kilometers_per_hour'} (produced
        by _renest when the dashboard's sub-field boxes were filled and their
        flat 'maximum_speed.value'/'maximum_speed.unit' keys folded up)
      - a dict with ARBITRARY multi-sub-field shape like unit_count:
        {'value': '1.0', 'type': 'Count'}   where 'type' is itself a nested
        object in the schema, not a flat unit. Same for num_batteries and
        other Amazon attributes that use per-key nested wrappers.
    All three must produce the correct Amazon-shaped payload. Prior versions
    only handled the first two and dropped/mangled the third."""
    ip  = _item_props(field_schema)
    obj = {}
    if "marketplace_id" in ip:
        obj["marketplace_id"] = mid
    if "language_tag" in ip:
        obj["language_tag"] = _lang_for(mid)

    # ---- GENERALISED DICT PATH: sub-fields folded by _renest. Handles any
    # multi-sub-field attribute like unit_count {value, type} where each key
    # may itself be nested or flat in the schema. This runs BEFORE the special
    # value+unit path so composite fields don't get miscategorised. -------
    if isinstance(raw, dict):
        # Identify all sub-keys the schema declares (excluding plumbing that's
        # already been added above).
        _plumbing = {"marketplace_id", "language_tag", "audience"}
        _schema_keys = [k for k in ip.keys() if k not in _plumbing]
        # Skip this branch and fall through to the legacy value+unit path if
        # this attribute is just plain value+unit (the old code handles those
        # more richly, including value-only strings and unit defaults).
        _is_plain_vu = (set(_schema_keys) <= {"value", "unit"})
        if not _is_plain_vu and _schema_keys:
            _wrote_any = False
            for sk in _schema_keys:
                if sk not in raw:
                    continue
                sub_raw = raw[sk]
                sub_schema = ip[sk]
                # Introspect the sub-schema. Amazon often nests inner shapes at
                # items.properties (not top-level properties) and often omits
                # the type: array marker. Use _item_props which handles both,
                # falling back to top-level properties if items.properties is
                # absent. Without this cable.length / leg.length -- which are
                # themselves value+unit objects -- get exposed as a flat sub-
                # key, and Amazon rejects the incomplete shape.
                _sub_ip = _item_props(sub_schema)
                if not _sub_ip and isinstance(sub_schema, dict):
                    _sub_ip = sub_schema.get("properties", {}) or {}
                # If the sub-schema itself is a nested object with value/unit,
                # recurse via _shape_simple on a synthetic wrapper.
                #
                # Bug C fix: _shape_simple always returns a LIST ([obj]). Amazon
                # accepts an array only where the sub-schema is actually an array
                # (type: array / has an `items` wrapper). For a plain nested OBJECT
                # slot -- e.g. leg.length / cable.length, which are single
                # {decimal_value, unit} objects -- assigning the list produces
                # `length: [{...}]` and Amazon rejects the whole parent as invalid.
                # Decide per sub-schema whether the slot wants an array or a bare
                # object, and unwrap the single-element list when it wants an object.
                def _sub_is_array(_ss):
                    if not isinstance(_ss, dict):
                        return False
                    return _ss.get("type") == "array" or isinstance(_ss.get("items"), dict)
                def _emit(_sk, _shaped, _ss):
                    if _shaped and not _sub_is_array(_ss) and isinstance(_shaped, list) and len(_shaped) == 1:
                        obj[_sk] = _shaped[0]
                    else:
                        obj[_sk] = _shaped
                if isinstance(sub_raw, dict) and _sub_ip:
                    # array-wrapped nested: schema like {type: object, items: {props}}
                    # OR just an object with props -- normalise via _shape_simple.
                    # Carry the sub-schema's OWN required list into the wrapper.
                    # Without it the recursion cannot tell a complete object
                    # from one holding nothing but a language_tag, and Amazon
                    # answers "'type.value' does not have enough values".
                    _synthetic = {"items": {"properties": _sub_ip,
                                            "required": _sub_req(sub_schema)}}
                    _shaped = _shape_simple(_synthetic, sub_raw, mid)
                    if _shaped:
                        _emit(sk, _shaped, sub_schema)
                        _wrote_any = True
                elif _sub_ip:
                    # Nested schema (props exist) but the user gave a flat value.
                    # Wrap it as {"value": sub_raw}.
                    # Carry the sub-schema's OWN required list into the wrapper.
                    # Without it the recursion cannot tell a complete object
                    # from one holding nothing but a language_tag, and Amazon
                    # answers "'type.value' does not have enough values".
                    _synthetic = {"items": {"properties": _sub_ip,
                                            "required": _sub_req(sub_schema)}}
                    _shaped = _shape_simple(_synthetic, sub_raw, mid)
                    if _shaped:
                        _emit(sk, _shaped, sub_schema)
                        _wrote_any = True
                else:
                    # Flat sub-key: assign directly, coercing to schema type.
                    _st = sub_schema.get("type") if isinstance(sub_schema, dict) else None
                    if _st == "boolean":
                        obj[sk] = _truthy(sub_raw)
                    elif _st == "integer":
                        try: obj[sk] = int(float(str(sub_raw)))
                        except Exception: obj[sk] = sub_raw
                    elif _st == "number":
                        try: obj[sk] = float(str(sub_raw))
                        except Exception: obj[sk] = sub_raw
                    else:
                        obj[sk] = sub_raw
                    _wrote_any = True
            if _wrote_any:
                # Same rule as at the bottom of this function: if a sub-field
                # Amazon requires could not be built, the whole attribute goes
                # rather than arriving incomplete. This is the branch unit_count
                # takes -- value shaped fine, type could not, and sending
                # {value} alone earns "'type' is required but missing".
                _needed = [k for k in _item_required(field_schema) if k not in obj]
                if _needed:
                    return []
                return [obj]
            # else: fall through to legacy paths

    # The numeric leaf key is `value` for most attributes but `decimal_value`
    # for some nested measures (leg.length, cable.length -- HARDWARE_TUBING,
    # MASSAGER). Treat whichever the schema declares as THE numeric key so the
    # inner {decimal_value, unit} object is built correctly and coerced to a
    # number, instead of falling through and being left as a raw string list.
    _numk = "value" if "value" in ip else ("decimal_value" if "decimal_value" in ip else None)
    if _numk:
        vp = ip[_numk]
        if "unit" in ip:
            # DICT PATH: sub-fields were filled and _renest folded them here
            if isinstance(raw, dict):
                num_raw = raw.get(_numk, raw.get("value", raw.get("decimal_value")))
                unit    = raw.get("unit")
                try:
                    obj[_numk] = float(str(num_raw)) if num_raw not in (None, "") else _coerce_value(vp, num_raw)
                except (ValueError, TypeError):
                    obj[_numk] = _coerce_value(vp, num_raw)
                up = ip["unit"]
                if unit:
                    obj["unit"] = _snap_enum(up.get("enum"), unit) if up.get("enum") else unit
                elif up.get("default"):
                    obj["unit"] = up.get("default")
            else:
                # STRING PATH: single combined value like '80.0 kilometers_per_hour'
                num, unit = _split_value_unit(raw)
                if num is None:
                    obj[_numk] = _coerce_value(vp, raw)
                else:
                    obj[_numk] = num
                    up = ip["unit"]
                    obj["unit"] = _snap_enum(up.get("enum"), unit) if up.get("enum") else (unit or up.get("default"))
        else:
            # DICT PATH: sub-fields (maybe just 'value'?) folded up.
            #
            # STRICT on an enum leaf. This is the leaf that carried "Count" into
            # unit_count.type.value, where Amazon's raw schema allows only
            # ["gram", "millilitre"] -- see _snap_enum. Nothing matched means we
            # do not know the unit, so the key is left out and the object is
            # dropped below rather than rejected by Amazon on every attempt.
            _src = (raw.get(_numk, raw.get("value", raw.get("decimal_value")))
                    if isinstance(raw, dict) and
                       (_numk in raw or "value" in raw or "decimal_value" in raw)
                    else raw)
            _cv = _coerce_value(vp, _src, strict=True)
            if _cv is not None:
                obj[_numk] = _cv
    elif ip:
        # item is an object but has no 'value' key we recognise -> best effort
        return []
    else:
        obj = {"value": str(raw)}
    # A required sub-key we could not fill makes this object a guaranteed
    # rejection, not partial data -- Amazon answers "'X' is required but
    # missing". Dropping it means an optional attribute simply is not sent, and
    # a required one is reported missing by the caller. Either is the truth.
    if obj and _item_required(field_schema):
        _missing = [k for k in _item_required(field_schema) if k not in obj]
        if _missing:
            return []
    # An object carrying nothing but the selectors we added ourselves is not a
    # value -- Amazon reads [{"language_tag":"en_GB"}] as "does not have enough
    # values". Same rule _is_empty_shape applies on the other path; it belongs
    # on both, and it is the backstop for any sub-schema that declares no
    # required list of its own.
    if isinstance(obj, dict) and obj and all(k in _SELECTOR_KEYS for k in obj):
        return []
    return [obj] if obj else []

def _shape_dimensions(field_schema: dict, length, width, height, mid: str):
    """Composite dimensions attribute, e.g. item_dimensions / item_package_dimensions
    with length/width/height each {value, unit}."""
    ip  = _item_props(field_schema)
    obj = {}
    if "marketplace_id" in ip:
        obj["marketplace_id"] = mid
    for axis, raw in (("length", length), ("width", width), ("height", height)):
        if axis in ip and not _is_blank(raw):
            num, unit = _split_value_unit(raw)
            axp = ip[axis].get("properties", {})
            up  = axp.get("unit", {})
            d   = {}
            if num is not None:
                d["value"] = num
            if unit or up.get("default"):
                d["unit"] = _snap_enum(up.get("enum"), unit) if up.get("enum") else (unit or up.get("default"))
            if d:
                obj[axis] = d
    axis_keys = [k for k in obj if k != "marketplace_id"]
    return [obj] if axis_keys else []

def _shape_axes(field_schema: dict, values: dict, mid: str):
    """Composite dimension attribute with whatever axes the schema declares
    (length / width / height / depth) -- e.g. item_depth_width_height,
    item_length_width_height, which some categories require instead of
    item_dimensions. `values` maps an axis name -> 'value + unit' string."""
    ip  = _item_props(field_schema)
    obj = {}
    if "marketplace_id" in ip:
        obj["marketplace_id"] = mid
    for axis in ("length", "width", "height", "depth"):
        if axis not in ip:
            continue
        raw = values.get(axis)
        if _is_blank(raw):
            continue
        num, unit = _split_value_unit(raw)
        axp = ip[axis].get("properties", {})
        # The numeric leaf key is usually `value`, but some composite fields
        # (HARDWARE_TUBING `leg`, MASSAGER `cable`, etc.) declare the length
        # axis with a `decimal_value` leaf instead. Writing `value` there makes
        # Amazon reject the WHOLE parent object as "invalid" even though the
        # number+unit are correct. Read the leaf name from the schema so any
        # future variant self-corrects (same principle as the item_length_width
        # schema-driven fix). See the leg/cable auto-fix loop that stalled at
        # IDENTICAL because the applied value was reshaped to the wrong leaf.
        _num_key = "decimal_value" if "decimal_value" in axp else "value"
        up  = axp.get("unit", {})
        d   = {}
        if num is not None:
            d[_num_key] = num
        if unit or up.get("default"):
            d["unit"] = _snap_enum(up.get("enum"), unit) if up.get("enum") else (unit or up.get("default"))
        if d:
            obj[axis] = d
    axis_keys = [k for k in obj if k != "marketplace_id"]
    return [obj] if axis_keys else []

def _shape_weight(field_schema: dict, raw, mid: str):
    """Single weight attribute {value, unit}, e.g. website_shipping_weight.

    Accepts a flat 'value unit' string OR a nested {value|decimal_value, unit} dict --
    the shape _renest produces when the editor's weight sub-field boxes were filled (the
    sheet stores item_weight as dotted item_weight.value/.unit keys). Without the dict
    branch, a nested item_weight fed here parsed to nothing and website_shipping_weight
    was silently dropped -- the same class of bug as the item_dimensions flat/nested
    mismatch."""
    if isinstance(raw, dict):
        _v = raw.get("value", raw.get("decimal_value", ""))
        _u = str(raw.get("unit", "")).strip()
        raw = (str(_v).strip() + " " + _u).strip() if str(_v).strip() != "" else ""
    if _is_blank(raw):
        return []
    ip = _item_props(field_schema)
    num, unit = _split_value_unit(raw)
    o = {}
    if "marketplace_id" in ip:
        o["marketplace_id"] = mid
    if num is not None:
        o["value"] = num
    up = ip.get("unit", {})
    if unit or up.get("default"):
        o["unit"] = _snap_enum(up.get("enum"), unit) if up.get("enum") else (unit or up.get("default"))
    return [o] if "value" in o else []
