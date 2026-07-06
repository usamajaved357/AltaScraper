"""listing/hazmat.py — battery/chemical hazard detection and hazmat field building.

Moved verbatim from amazon_listing_generator.py in Phase 5 (behaviour unchanged):
  _has_battery            — detect battery/lithium/electrical items from Compliance Notes
  _build_ghs_from_schema  — build a valid GHS (chemical hazard) attribute object driven
                            entirely by the live schema's own structure/allowed values
Both are self-contained (no module-level dependencies).
"""


def _has_battery(row: dict) -> bool:
    return any(w in str(row.get("Compliance Notes", "")).lower()
               for w in ["battery", "lithium", "electrical"])


def _build_ghs_from_schema(ghs_schema: dict, mid: str):
    """Build a valid `ghs` attribute object from the live schema's own structure
    and allowed values. Amazon's GHS is a nested object; the exact sub-fields vary
    by marketplace/type. We read the schema, find the classification-style enum,
    and pick a 'not classified / not applicable / none' value if the schema offers
    one (so a non-hazardous retail item declares 'no GHS hazard' correctly rather
    than sending a flat string Amazon rejects). Returns a list-wrapped object, or
    None if no valid structure can be built (caller then omits it)."""
    if not isinstance(ghs_schema, dict):
        return None
    # GHS is typically an array of objects: items.properties.{...}
    items = ghs_schema.get("items", {}) if isinstance(ghs_schema.get("items"), dict) else {}
    item_props = items.get("properties", {}) if isinstance(items.get("properties"), dict) else {}
    if not item_props:
        # some schemas put properties directly on the field
        item_props = ghs_schema.get("properties", {}) if isinstance(ghs_schema.get("properties"), dict) else {}
    if not item_props:
        return None

    def _enum_of(node):
        if not isinstance(node, dict):
            return []
        if isinstance(node.get("enum"), list):
            return [str(x) for x in node["enum"]]
        # nested array: items.properties.value.enum  OR items.enum
        it = node.get("items", {})
        if isinstance(it, dict):
            if isinstance(it.get("enum"), list):
                return [str(x) for x in it["enum"]]
            ip = it.get("properties", {})
            if isinstance(ip, dict):
                for key in ("value", "classification", "class"):
                    vp = ip.get(key, {})
                    if isinstance(vp, dict) and isinstance(vp.get("enum"), list):
                        return [str(x) for x in vp["enum"]]
        return []

    def _pick_safe(values):
        # prefer an explicit "not applicable / not classified / none" option
        low = {v.lower(): v for v in values}
        for needle in ("not applicable", "not_applicable", "notapplicable",
                       "not classified", "not_classified", "none", "no",
                       "not regulated", "non-hazardous", "no ghs"):
            for lk, orig in low.items():
                if needle in lk:
                    return orig
        return values[0] if values else None

    # find the classification-style sub-field that carries the enum
    obj = {}
    for sub_name, sub_node in item_props.items():
        vals = _enum_of(sub_node)
        if vals:
            chosen = _pick_safe(vals)
            if chosen is None:
                continue
            sn = sub_node if isinstance(sub_node, dict) else {}
            if sn.get("type") == "array":
                # the inner item object names its scalar key explicitly (e.g.
                # classification -> items.properties has a single key "class").
                # Use that real key, NOT a hard-coded "value".
                _inner = (sn.get("items", {}) or {})
                _inner_props = _inner.get("properties", {}) if isinstance(_inner, dict) else {}
                if isinstance(_inner_props, dict) and _inner_props:
                    # pick the key that actually carries the enum, else the first
                    _key = None
                    for _ik, _iv in _inner_props.items():
                        if isinstance(_iv, dict) and isinstance(_iv.get("enum"), list):
                            _key = _ik; break
                    if _key is None:
                        # honour the item's "required" list if present
                        _req_inner = _inner.get("required", []) if isinstance(_inner.get("required"), list) else []
                        _key = (_req_inner[0] if _req_inner else next(iter(_inner_props.keys())))
                    obj[sub_name] = [{_key: chosen}]
                else:
                    obj[sub_name] = [chosen]
            else:
                obj[sub_name] = chosen
    if not obj:
        return None
    # add marketplace_id at the object level if the schema's item allows it
    if "marketplace_id" in item_props:
        obj["marketplace_id"] = mid
    return [obj]
