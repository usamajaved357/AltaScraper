"""listing/attribute_defaults.py -- what a remembered per-type default may carry.

"Save as default" (POST /save_default) remembers a draft's filled attributes for
its product type, in ONE file shared by every account (attribute_defaults.json),
and the generator fills any attribute a new draft of that type lacks from it.

THE HOLE (Milestone 2, 28 Sep 2026, the master audit's open Rule 1 question).
It remembered EVERY filled attribute. A draft whose attributes carried `brand`
or `manufacturer` therefore put one company's name into the defaults for every
account -- and the generator only sets `brand` itself when it can resolve the
account's own trademark, so an account where that failed got another company's
brand on a brand-new listing. CLAUDE.md Rule 1: the listing is a new product
under the OWNER'S OWN brand for THAT account.

So identity is never a default. A default is for judgment fields that are the
same for every product of a type (size system, assembly required, material
regulation...), not for who makes it, what it is called, what it costs, or how
Amazon identifies it. The GTIN exemption and merchant_suggested_asin are also
decided elsewhere, by a click and never at all respectively; they are listed
here so a default can never even hold them.

Applied on SAVE (routes/ui_routes.py) and again on LOAD (the generator), so a
file written before this existed is cleaned as it is read.
"""

IDENTITY_FIELDS = frozenset({
    # who makes and sells it -- the account's own
    "brand", "manufacturer", "brand_name", "manufacturer_contact_information",
    # what it is called and says
    "item_name", "bullet_point", "product_description", "generic_keyword",
    # how Amazon identifies it
    "externally_assigned_product_identifier", "external_product_id",
    "external_product_id_type", "merchant_suggested_asin",
    "merchant_suggested_asin_type", "part_number", "model_number", "model_name",
    # the GTIN exemption is claimed by a click on ONE listing (Rule 1)
    "supplier_declared_has_product_identifier_exemption",
    # the offer
    "purchasable_offer", "list_price", "fulfillment_availability",
    "fulfillment_quantity",     # one account's stock is not another's default
    "condition_type", "merchant_shipping_group",
})


def _is_identity(key):
    # Case-insensitive: a hand-edited "Brand" is still a brand.
    k = str(key or "").strip().lower()
    base = k.split(".", 1)[0]                 # dotted "brand.value" forms too
    if base in IDENTITY_FIELDS:
        return True
    # Every picture of one particular product: main, other_N, swatch, offer...
    return base.endswith("_image_locator") or "_image_locator_" in base


def strip_identity(attrs):
    """`attrs` without anything that identifies one product or one seller."""
    if not isinstance(attrs, dict):
        return {}
    return {k: v for k, v in attrs.items() if not _is_identity(k)}


def clean_file_data(data):
    """A whole attribute_defaults.json structure, each type's entry cleaned."""
    if not isinstance(data, dict):
        return {}
    return {pt: strip_identity(v) for pt, v in data.items() if isinstance(v, dict)}
