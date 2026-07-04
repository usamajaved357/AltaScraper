"""listing/compliance.py — proactive compliance-safe defaults.

apply_compliance_safe_defaults sets each hazard/regulatory field to its safest,
non-cascading 'not applicable / none' value from the live schema, so a non-chemical
retail item never errors on an empty or trigger-y compliance dropdown. _enum_for and
_pick_not_applicable are its schema helpers. Moved verbatim from
amazon_listing_generator.py in Phase 5 (behaviour unchanged); self-contained.
"""

# Values that mean "no hazard / not regulated" -- preferred for family-1 fields,
# matched case-insensitively against the schema's own enum.
_NOT_APPLICABLE_SYNONYMS = (
    "not_applicable", "notapplicable", "not_app", "none", "no", "not_regulated",
    "non_hazardous", "no_ghs", "not_classified", "does_not_apply", "n_a", "na",
    "exempt", "no_warning_applicable",
)

# Family-1 compliance fields we proactively neutralise (in addition to whatever
# the live `required` list contains). These are the usual error sources.
_HAZARD_QUESTION_FIELDS = (
    "ghs", "hazmat", "pesticide_marking", "supplier_declared_material_regulation",
    "california_proposition_65_compliance_type", "contains_liquid_contents",
    "dangerous_goods_regulation",
)


def _enum_for(prop: dict):
    """Pull the allowed-value enum for an attribute from its schema property."""
    if not isinstance(prop, dict):
        return []
    if isinstance(prop.get("enum"), list):
        return [str(x) for x in prop["enum"]]
    items = prop.get("items", {}) if isinstance(prop.get("items"), dict) else {}
    ip = items.get("properties", {}) if isinstance(items, dict) else {}
    for key in ("value", "class", "type"):
        vp = ip.get(key, {}) if isinstance(ip, dict) else {}
        if isinstance(vp, dict) and isinstance(vp.get("enum"), list):
            return [str(x) for x in vp["enum"]]
    if isinstance(items.get("enum"), list):
        return [str(x) for x in items["enum"]]
    return []


def _pick_not_applicable(enum):
    """From an enum, return the 'not applicable / none' value if present, else
    None. Never returns a value that is itself a cascade trigger like 'ghs'."""
    if not enum:
        return None
    low = {str(e).lower(): e for e in enum}
    for syn in _NOT_APPLICABLE_SYNONYMS:
        if syn in low:
            return low[syn]
    # fuzzy contains (e.g. "not_applicable_for_this_item")
    for lk, orig in low.items():
        if any(s in lk for s in ("not_applic", "not applic", "not_regul", "no_haz", "non_haz", "not_class")):
            return orig
    return None


def apply_compliance_safe_defaults(A: dict, props: dict, required: set, mid: str,
                                   is_battery: bool):
    """Proactively set every hazard/regulatory compliance field to its safest,
    non-cascading value (the 'not applicable / none' branch from the live schema),
    so a non-chemical retail item never errors on an empty or trigger-y compliance
    dropdown. Returns a list of (field, value, reason) describing what was set, so
    the dashboard can SHOW the user (choice 2b) and let them override.

    Battery fields are NOT neutralised here -- a real battery is filled honestly by
    the dedicated battery logic. This only handles the 'is there a hazard?' family.
    """
    notes = []
    # 1) the family-1 hazard questions Amazon offers a 'not applicable' for
    for f in _HAZARD_QUESTION_FIELDS:
        if f == "ghs":
            continue  # ghs is structural; handled by the dedicated GHS net
        prop = props.get(f, {}) if isinstance(props.get(f), dict) else {}
        enum = _enum_for(prop)
        # only act if the field is plausibly relevant (in schema OR required OR
        # already present with a value we need to validate)
        if not prop and f not in required and f not in A:
            continue
        # If the field is ALREADY set (by the AI or user), validate that value
        # against the schema's allowed list. A valid value is kept; an INVALID
        # one (e.g. the AI guessed hazmat="Transportation", which Amazon rejects)
        # is replaced with the not-applicable option. This is the fix for
        # "hazmat does not have the expected value(s)".
        if f in A:
            _cur = A[f]
            _curval = ""
            if isinstance(_cur, list) and _cur and isinstance(_cur[0], dict):
                _curval = str(_cur[0].get("value", ""))
            elif _cur is not None:
                _curval = str(_cur)
            if enum:
                _enum_low = {str(e).lower(): e for e in enum}
                if _curval.lower() in _enum_low:
                    continue  # already a valid Amazon value -> leave it
                # invalid -> replace with not-applicable (or safest valid value)
                na = _pick_not_applicable(enum) or enum[0]
                A[f] = [{"value": na, "marketplace_id": mid}]
                notes.append((f, na, f'auto: replaced invalid value "{_curval}" with a valid one'))
            # no enum to check against -> leave whatever is there
            continue
        # Not set yet -> fill with the not-applicable option.
        na = _pick_not_applicable(enum)
        if na is not None:
            A[f] = [{"value": na, "marketplace_id": mid}]
            notes.append((f, na, "auto: not-applicable (no hazard for this product)"))
        elif f in required and enum:
            # required but no 'not applicable' option -> safest available non-empty
            safe = enum[0]
            A[f] = [{"value": safe, "marketplace_id": mid}]
            notes.append((f, safe, "auto: required field, picked safest allowed value"))
    return notes
