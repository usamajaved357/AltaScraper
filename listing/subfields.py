"""listing/subfields.py -- reading an Amazon attribute schema's subfields and enums.

Moved word for word out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026).
dashboard.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""



_SUBFIELD_PLUMBING = {"language_tag", "marketplace_id", "audience"}


def _sf_enum_of(node):
    """Enum list for a schema node, unwrapping a localized array+items.value wrapper."""
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("enum"), list):
        return [str(x) for x in node["enum"]]
    # Amazon writes this shape two ways, and until now only the first was read:
    #
    #   with the array wrapper     node.items.properties.value.enum
    #   without it                 node.properties.value.enum
    #
    # unit_count.type is the second kind -- a plain object whose `value` carries
    # the closed list ["gram", "millilitre"] on MACHINE_LUBRICANT. Returning
    # None for it meant auto-fix drew a free-text box, the AI answered "Count"
    # from the field's description, and Amazon refused it every time. The
    # surrounding code already guards against Amazon omitting the array marker
    # (see _extract_subfields); this is the same omission, one level in.
    for _src in (node.get("items"), node):
        if not isinstance(_src, dict):
            continue
        props = _src.get("properties")
        vp = props.get("value") if isinstance(props, dict) else None
        if isinstance(vp, dict) and isinstance(vp.get("enum"), list):
            return [str(x) for x in vp["enum"]]
    return None


def _sf_kind(node):
    t = node.get("type") if isinstance(node, dict) else None
    return "number" if t in ("number", "integer") else "text"


def _extract_subfields(prop) -> list:
    """Return the fillable sub-field controls Amazon expects under ONE attribute.
    [] -> plain single-value attribute. Otherwise a list of {path,label,kind,enum}.
    'path' is dot-joined keys UNDER the attribute, saved flat as '<field>.<path>'.

    Handles Amazon's habit of nesting attributes two levels deep -- e.g.
    `cable.length` in MASSAGER is itself a `{value, unit}` object, not a scalar.
    Without walking into the child's inner `items.properties` we'd expose
    `cable.length` as a single box and the AI would fill only the number OR
    only the unit, producing 'invalid value for cable' rejections. Amazon's
    schema often omits an explicit `type: "array"` marker on the inner wrapper,
    so we probe for `items.properties` and `properties` regardless of the
    marker. Same fix applies to `leg.length` (HARDWARE_TUBING) and any other
    attribute where the second level is itself a value+unit pair."""
    if not isinstance(prop, dict):
        return []
    node = prop
    if isinstance(node.get("items"), dict):
        # Unwrap array wrapper whether or not the "type": "array" marker is
        # present -- Amazon frequently omits it on inner wrappers.
        node = node["items"]
    sub = node.get("properties") if isinstance(node, dict) else None
    if not isinstance(sub, dict):
        return []
    keys = [k for k in sub.keys() if k not in _SUBFIELD_PLUMBING]
    if keys == ["value"]:
        return []
    out = []
    for k in keys:
        child = sub[k]
        cnode = child
        # Unwrap child's array/items wrapper regardless of "type" marker
        if isinstance(child, dict) and isinstance(child.get("items"), dict):
            cnode = child["items"]
        cprops = {}
        if isinstance(cnode, dict) and isinstance(cnode.get("properties"), dict):
            cprops = {ck: cv for ck, cv in cnode["properties"].items()
                      if ck not in _SUBFIELD_PLUMBING}
        if set(cprops.keys()) == {"value", "unit"}:
            out.append({"path": k + ".value", "label": (k + " value").replace("_", " "),
                        "kind": _sf_kind(cprops["value"]), "enum": _sf_enum_of(cprops["value"])})
            out.append({"path": k + ".unit", "label": (k + " unit").replace("_", " "),
                        "kind": "text", "enum": _sf_enum_of(cprops["unit"])})
        elif cprops:
            # Grandchildren present but not the plain value+unit shape: recurse
            # so multi-level nested objects (like some battery.capacity variants)
            # get exposed at every leaf. Prevents "invalid value" rejections
            # on nested composites the AI could otherwise only half-fill.
            grand = _extract_subfields(child)
            if grand:
                for g in grand:
                    out.append({"path": k + "." + g["path"], "label": (k + " " + g["label"]),
                                "kind": g.get("kind"), "enum": g.get("enum")})
            else:
                out.append({"path": k, "label": k.replace("_", " "),
                            "kind": _sf_kind(child), "enum": _sf_enum_of(child)})
        else:
            out.append({"path": k, "label": k.replace("_", " "),
                        "kind": _sf_kind(child), "enum": _sf_enum_of(child)})
    return out
