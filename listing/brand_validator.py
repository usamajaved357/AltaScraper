"""listing/brand_validator.py — brand selection/validation from the live schema.

pick_brand_for_product reads the brand attribute's allowed values from the product-type
schema and returns the first allowed value (or 'Unbranded' when the field has no enforced
list). Moved verbatim from amazon_listing_generator.py in Phase 5 (behaviour unchanged).
Self-contained (reads only the passed-in schema dict).
"""


def pick_brand_for_product(schema: dict) -> str:
    """Read brand attribute's allowed values from the schema. Return first allowed
    value, or 'Unbranded' if the field has no enforced list."""
    all_fields = schema.get("all", {}) or {}
    brand_meta = all_fields.get("brand") or all_fields.get("brand_name") or {}
    allowed    = brand_meta.get("allowed", []) or []
    if allowed:
        return str(allowed[0])
    return "Unbranded"
