"""listing/shaper.py — schema shaping only.

shape_by_schema reads the live Amazon product-type schema and folds a raw value into the
EXACT shape Amazon requires (array vs object, value vs decimal_value, unit enums, nested
sub-attributes). It NEVER guesses the shape — it is driven entirely by the schema passed
in. Moved verbatim from amazon_listing_generator.py in Phase 5 (behaviour unchanged).
"""


def shape_by_schema(schema, raw, mid, lang="en_GB"):
    t = schema.get("type")
    if t == "array":
        shaped = shape_by_schema(schema.get("items", {}) or {}, raw, mid, lang)
        return [shaped] if shaped is not None else []
    if t == "object":
        props = schema.get("properties", {}) or {}
        obj = {}
        if "marketplace_id" in props: obj["marketplace_id"] = mid
        if "language_tag" in props:   obj["language_tag"]   = lang
        num_key = "decimal_value" if "decimal_value" in props else ("value" if "value" in props else None)
        num=unit=None
        if isinstance(raw, str):
            p=raw.split()
            if p:
                try: num=float(p[0]); unit=" ".join(p[1:]) or None
                except ValueError: pass
        elif isinstance(raw, dict):
            num=raw.get("decimal_value", raw.get("value")); unit=raw.get("unit")
        if num_key and num not in (None,""):
            try: obj[num_key]=float(str(num))
            except (ValueError,TypeError): obj[num_key]=num
        if "unit" in props and unit not in (None,""):
            uen=props["unit"].get("enum")
            obj["unit"]=(next((e for e in uen if str(e).lower()==str(unit).strip().lower()), unit)
                         if uen else unit)
        for pk,pv in props.items():
            if pk in ("marketplace_id","language_tag","unit",num_key): continue
            if isinstance(pv,dict) and pv.get("type") in ("array","object"):
                sub = raw.get(pk) if isinstance(raw,dict) and pk in raw else raw
                s = shape_by_schema(pv, sub, mid, lang)
                if s not in (None,[],{}): obj[pk]=s
        return obj
    return raw.get("decimal_value", raw.get("value")) if isinstance(raw,dict) else raw
