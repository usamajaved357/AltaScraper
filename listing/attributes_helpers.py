"""listing/attributes_helpers.py -- the pure helpers build_api_attributes uses.

Step B2 of docs/plans/build-api-attributes.md. These were nested functions
inside amazon_listing_generator.build_api_attributes that take everything they
use as arguments -- no closure over the row, the schema, the payload being
built or the engine's globals. Moved VERBATIM (only de-indented); the builder
imports them under the same names. Proven by the 100 golden payloads
(test_build_api_attributes_golden.py).

NOT merged, on purpose (CLAUDE.md Rule 10: move, don't rewrite):
_allowed_values, _enum_of_prop and the enum read inside _cbc_value all read
"Amazon's allowed list" the same way for a well-formed schema, but differ on a
malformed one (_enum_of_prop raises where _allowed_values returns []). Recorded
in docs/known-issues.md; merging them is a separate, tested change.
"""
import re


def _renest(flat: dict) -> dict:
    """Re-nest flat dot-keys into an object tree.

    Handles COLLISION between keys of different depths gracefully:
    e.g. if `flat` contains BOTH `leg.length = "feet"` (an old shallow key
    from a prior schema-extractor version) AND `leg.length.decimal_value =
    "50.0"` + `leg.length.unit = "feet"` (deeper keys from the current
    extractor version), the deeper keys win because they're strictly more
    specific -- the shallow scalar gets promoted to a dict node with the
    scalar preserved under a synthetic `.value` sub-key (so no data is
    silently dropped).

    Before this defensiveness, `cur.setdefault(p, {})` returned the
    existing scalar; the next iteration crashed with 'str object does
    not support item assignment' as soon as the sheet accumulated keys
    at multiple depths -- which was inevitable once the extractor
    started walking deeper on each fix. See the assert-strings that
    Amazon returned from prior runs mixed with the new decimal_value/
    unit sub-keys."""
    nested, plain = {}, {}
    # Iterate shortest-key-first so shallow entries are placed as leaves
    # first, then get PROMOTED to dicts when a deeper sibling arrives.
    # (If we ran longest-first, the deeper writes would land in fresh
    # dicts and the shallow scalar arriving later would overwrite the
    # whole subtree.)
    for k in sorted([x for x in flat.keys() if isinstance(x, str)], key=lambda s: s.count(".")):
        v = flat[k]
        if "." in k and not k.startswith("_"):
            top, rest = k.split(".", 1)
            # If `nested[top]` was previously set to a scalar (from an
            # even-shallower key like just "leg" = "feet"), promote it.
            if top in nested and not isinstance(nested[top], dict):
                _prev = nested[top]
                nested[top] = {"value": _prev}
            cur = nested.setdefault(top, {})
            parts = rest.split(".")
            for p in parts[:-1]:
                if p in cur and not isinstance(cur[p], dict):
                    _prev = cur[p]
                    cur[p] = {"value": _prev}
                cur = cur.setdefault(p, {})
            # Final leaf: if a dict is already there (deeper keys arrived
            # earlier despite sort, or a prior iteration created one),
            # don't overwrite it -- store under `.value` instead.
            _leaf = parts[-1]
            if _leaf in cur and isinstance(cur[_leaf], dict) and not isinstance(v, dict):
                cur[_leaf].setdefault("value", v)
            else:
                cur[_leaf] = v
        else:
            # Plain key (no dot). If nested already has this parent as a
            # dict from a deeper key that came earlier, don't overwrite
            # the dict -- fold the plain value into it as `.value`.
            if k in nested and isinstance(nested[k], dict) and not isinstance(v, dict):
                nested[k].setdefault("value", v)
            else:
                plain[k] = v
    # nested objects win where a flat parent also exists
    for top, obj in nested.items():
        if isinstance(plain.get(top), dict):
            plain[top].update(obj)
        else:
            plain[top] = obj
    return plain


def _is_public_url(u):
    u = str(u or "").strip()
    return u.lower().startswith("http://") or u.lower().startswith("https://")


def _allowed_values(fprop):
    """Amazon's allowed list for this field, read the same way the schema
    extractor reads it -- value.enum, then item.enum, then the field's own."""
    if not isinstance(fprop, dict):
        return []
    items = fprop.get("items", {})
    ip = items.get("properties", {}) if isinstance(items, dict) else {}
    vp = ip.get("value", {}) if isinstance(ip, dict) else {}
    out = (vp.get("enum") if isinstance(vp, dict) else None) \
        or (ip.get("enum") if isinstance(ip, dict) else None) \
        or (items.get("enum") if isinstance(items, dict) else None) \
        or fprop.get("enum") or []
    return [str(a) for a in out]


def _cbc_value(_prop, _yes=True):
    # contains_battery_or_cell is an ENUM (e.g. "Yes"/"No") for some product
    # types (UNMANNED_AERIAL_VEHICLE) and a BOOLEAN for others. Sending JSON
    # `true` to an enum field fails with "select an approved value from the
    # list". Inspect the schema: if it declares an enum, pick the allowed
    # value meaning "yes"; otherwise fall back to boolean True.
    _enum = []
    if isinstance(_prop, dict):
        _it  = _prop.get("items", {}) if isinstance(_prop.get("items"), dict) else {}
        _itp = _it.get("properties", {}) if isinstance(_it, dict) else {}
        _vpp = _itp.get("value", {}) if isinstance(_itp, dict) else {}
        _enum = [str(x) for x in (_vpp.get("enum") or _itp.get("enum")
                                  or _it.get("enum") or _prop.get("enum") or [])]
    _want = ("yes", "true", "1") if _yes else ("no", "false", "0",
                                               "no_battery", "none")
    if _enum:
        for _e in _enum:
            if str(_e).strip().lower() in _want:
                return _e
        # Nothing on the list says what we mean. Do NOT fall back to the
        # first entry -- that is how "battery" ended up on a vacuum flask.
        return None
    return bool(_yes)


def _enum_of_prop(_p):
    if not isinstance(_p, dict):
        return []
    _it  = _p.get("items", {}) if isinstance(_p.get("items"), dict) else {}
    _itp = _it.get("properties", {}) if isinstance(_it, dict) else {}
    _vpp = _itp.get("value", {}) if isinstance(_itp, dict) else {}
    return [str(x) for x in (_vpp.get("enum") or _itp.get("enum") or _it.get("enum") or _p.get("enum") or [])]


def _valid_text_attr(_v):
    # Valid = non-empty list whose every entry is a dict with a non-empty
    # `value`. Anything else (missing, "", [], flat string, dict missing
    # value) is treated as broken and rebuilt.
    if not isinstance(_v, list) or not _v:
        return False
    for _e in _v:
        if not isinstance(_e, dict):
            return False
        if not str(_e.get("value", "")).strip():
            return False
    return True


def _watt_number(_v):
    """Return the numeric part of a wattage value in any shape, or '' if none."""
    cand = ""
    if isinstance(_v, list) and _v:
        f = _v[0]
        cand = (f.get("value") if isinstance(f, dict) else f)
    elif isinstance(_v, dict):
        cand = _v.get("value")
    else:
        cand = _v
    if cand is None:
        return ""
    m = re.search(r"-?\d+(?:\.\d+)?", str(cand))
    return m.group(0) if m else ""


def _has_real_number(_v):
    cand = None
    if isinstance(_v, list) and _v:
        first = _v[0]
        cand = first.get("value") if isinstance(first, dict) else first
    elif isinstance(_v, dict):
        cand = _v.get("value")
    else:
        cand = _v
    if cand is None:
        return False
    s = str(cand).strip().lower()
    if s in ("", "none", "null"):
        return False
    return bool(re.search(r"-?\d", s))
