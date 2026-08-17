"""Two bugs found by actually merging two listings on the live UK account.

Asked for as: "you are also allowed to merge the two items of the same type into
a parent ASIN, check 2 asins which makes sense to be merged like weed slasher i
want you to test the variations tool we built, and check the bugs and fix them
while doing it".

The pair: 10.99_3Days_B0GGSCK998 (Black) and 6.89_2Days_B0GY4MTGKD (Green), both
OUTDOOR_LIVING, both AltaboltaVoo, both 800mm weed slashers.

BUG 1 -- themes Amazon offers that the product type cannot use.
  OUTDOOR_LIVING offered ten groupings. Five of them group by color_name,
  material_type or item_display_height, none of which is one of the type's 114
  attributes -- it has `color` and `material`. Picking one got you "these
  products have no material_type set", a refusal nobody can clear, pointing at a
  field that does not exist.

BUG 2 -- every merge was rejected, for every product type.
  The parent went up with four attributes. Amazon holds a parent to the type's
  rules like any other listing:
      'Brand Name' is required but missing.; 'Are batteries required?' is
      required but missing.; 'Dangerous Goods Regulations' is required but
      missing.
  Note what that message proves: the schema's `required` list for the type is
  six attributes and batteries_required is NOT among them. Reading the message
  to get attribute names is forbidden (Rule 4) and would not have worked either.
"""
import json
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from listing import variations as V

# OUTDOOR_LIVING as it really is: measured on the live UK account, 17 Aug 2026.
OL_THEMES = ["COLOR", "COLOR_NAME/MATERIAL_TYPE", "COLOR_NAME/NUMBER_OF_ITEMS",
             "ITEM_DISPLAY_HEIGHT", "ITEM_WEIGHT", "MATERIAL_TYPE",
             "MATERIAL_TYPE/COLOR_NAME", "SIZE", "SIZE/PATTERN", "VOLTAGE"]
OL_ATTRS = {"color", "size", "pattern", "item_weight", "voltage", "material",
            "number_of_items", "brand", "bullet_point", "country_of_origin",
            "item_name", "product_description", "supplier_declared_dg_hz_regulation",
            "batteries_required", "main_product_image_locator"}
SCHEMA = {"attribute_names": sorted(OL_ATTRS),
          "required": ["brand", "bullet_point", "country_of_origin", "item_name",
                       "product_description", "supplier_declared_dg_hz_regulation"],
          "properties": {"variation_theme": {"items": {"properties": {
              "name": {"enum": OL_THEMES}}}}}}

MKT = "A1F83G8C2ARO7P"
def _v(x): return [{"value": x, "marketplace_id": MKT}]

BLACK = {"sku": "10.99_3Days_B0GGSCK998", "raw": {
    "brand": _v("AltaboltaVoo"), "color": _v("Black"),
    "country_of_origin": _v("CN"), "batteries_required": _v(False),
    "supplier_declared_dg_hz_regulation": _v("not_applicable"),
    "bullet_point": _v("Hardened steel blade"),
    "product_description": _v("Black slasher"),
    "item_name": _v("Weed Slasher 800mm"),
    "main_product_image_locator": [{"media_location": "https://x/black.jpg"}],
    "purchasable_offer": _v("10.99"), "fulfillment_availability": _v(3),
    "externally_assigned_product_identifier": _v("5012345678900"),
    "condition_type": _v("new_new")}}
GREEN = {"sku": "6.89_2Days_B0GY4MTGKD", "raw": {
    "brand": _v("AltaboltaVoo"), "color": _v("Green"),
    "country_of_origin": _v("CN"), "batteries_required": _v(False),
    "supplier_declared_dg_hz_regulation": _v("not_applicable"),
    "bullet_point": _v("Wooden handle"),
    "product_description": _v("Green slasher"),
    "item_name": _v("800mm Grass Slasher"),
    "main_product_image_locator": [{"media_location": "https://x/green.jpg"}],
    "purchasable_offer": _v("6.89"), "fulfillment_availability": _v(5),
    "condition_type": _v("new_new")}}
KIDS = [BLACK, GREEN]

# The flattened form the checker compares, as the route builds it.
def flat(k):
    out = {}
    for key, val in k["raw"].items():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            for w in ("value", "name", "media_location"):
                if w in val[0]:
                    out[key] = str(val[0][w]); break
    return {"sku": k["sku"], "product_type": "OUTDOOR_LIVING",
            "brand": "AltaboltaVoo", "item_type_keyword": "",
            "attributes": out, "raw": k["raw"]}
CHECK_KIDS = [flat(BLACK), flat(GREEN)]


print("=== BUG 1: a theme whose axis the product type does not have ===")
check("the type's attributes are read from the schema",
      V.attribute_names(SCHEMA), OL_ATTRS)
check("  and an unknown schema says so, rather than 'nothing'",
      V.attribute_names({}), None)
# None vs empty matters: empty would declare every axis missing and block
# everything, which is the failure mode this whole test exists to prevent.
check("  a TRIMMED schema is not mistaken for the full list",
      V.attribute_names({"properties": {"variation_theme": {}, "x_image": {}}}), None)

check("MATERIAL_TYPE names an attribute this type does not have",
      V.missing_axes("MATERIAL_TYPE", OL_ATTRS), ["material_type"])
check("  it has `material`, and that is NOT taken as a match",
      "material" in OL_ATTRS and V.missing_axes("MATERIAL_TYPE", OL_ATTRS) != [], True)
check("  a two-part theme reports BOTH missing halves",
      V.missing_axes("COLOR_NAME/MATERIAL_TYPE", OL_ATTRS),
      ["color_name", "material_type"])
check("  and one good half is not enough",
      V.missing_axes("COLOR_NAME/NUMBER_OF_ITEMS", OL_ATTRS), ["color_name"])
check("COLOR is fine — the type has `color`", V.missing_axes("COLOR", OL_ATTRS), [])
check("SIZE/PATTERN is fine on both axes", V.missing_axes("SIZE/PATTERN", OL_ATTRS), [])
check("when the attributes are unknown, nothing is ruled out",
      V.missing_axes("MATERIAL_TYPE", None), [])

usable, blocked = V.split_themes(OL_THEMES, OL_ATTRS)
check("5 of the 10 Amazon offers actually work here", usable,
      ["COLOR", "ITEM_WEIGHT", "SIZE", "SIZE/PATTERN", "VOLTAGE"])
check("  and the other 5 are named with the reason", [t for t, _ in blocked],
      ["COLOR_NAME/MATERIAL_TYPE", "COLOR_NAME/NUMBER_OF_ITEMS",
       "ITEM_DISPLAY_HEIGHT", "MATERIAL_TYPE", "MATERIAL_TYPE/COLOR_NAME"])

print("\n--- and the refusal now names the real cause ---")
probs = V.check("P", CHECK_KIDS, "MATERIAL_TYPE", SCHEMA, "OUTDOOR_LIVING")
truthy("it says the TYPE has no such attribute",
       any("has no material_type attribute" in p for p in probs))
truthy("  and offers the groupings that do work",
       any("COLOR" in p and "do work" in p for p in probs))
check("  it does NOT blame the products for a missing value",
      [p for p in probs if "no material_type set" in p], [])

print("\n--- a genuinely missing value is still a genuinely missing value ---")
probs = V.check("P", CHECK_KIDS, "SIZE", SCHEMA, "OUTDOOR_LIVING")
truthy("neither slasher has a size, and SIZE is a real attribute",
       any("no size set" in p for p in probs))

print("\n--- the merge that was actually made ---")
check("Black and Green under COLOR: nothing wrong with it",
      V.check("ALTA-SLASHER-800-PARENT", CHECK_KIDS, "COLOR", SCHEMA,
              "OUTDOOR_LIVING"), [])


print("\n=== BUG 2: the parent Amazon rejected every time ===")
pa = V.parent_attributes(KIDS, "COLOR", title="AltaboltaVoo 800mm Weed Slasher",
                         marketplace_id=MKT,
                         required=V.required_from_schema(SCHEMA))
at = pa["attributes"]

print("--- what the children agree on becomes the family's ---")
check("brand", at.get("brand"), _v("AltaboltaVoo"))
check("  in AMAZON'S shape, not flattened to a string",
      isinstance(at["brand"], list) and "marketplace_id" in at["brand"][0], True)
check("country of origin", at.get("country_of_origin"), _v("CN"))
check("dangerous goods — required, and never in the schema's required list "
      "under that name", at.get("supplier_declared_dg_hz_regulation"),
      _v("not_applicable"))
check("batteries — the one Amazon named as 'Are batteries required?'",
      at.get("batteries_required"), _v(False))
truthy("  none of these was derived from Amazon's message text",
       "batteries_required" in pa["inherited"]
       and "batteries_required" not in SCHEMA["required"])

print("\n--- what they differ on stays OFF the parent ---")
check("colour is what they vary BY, so the parent has none",
      at.get("color"), None)
truthy("  and it is reported as a difference", "color" in pa["differ"])

print("\n--- what a parent must never carry ---")
for k, why in (("purchasable_offer", "a parent cannot be bought"),
               ("fulfillment_availability", "stock belongs to the children"),
               ("condition_type", "the offer's, not the family's"),
               ("externally_assigned_product_identifier",
                "a container has no barcode of its own"),
               ("merchant_suggested_asin", "CLAUDE.md Rule 1, from anywhere")):
    check("no %s — %s" % (k, why), at.get(k), None)
check("it goes up under the GTIN exemption instead",
      at.get("supplier_declared_has_product_identifier_exemption"),
      [{"value": True, "marketplace_id": MKT}])

print("\n--- what makes it a parent ---")
check("parentage", at.get("parentage_level"), [{"value": "parent"}])
check("theme", at.get("variation_theme"), [{"name": "COLOR"}])
check("the title given to it", at["item_name"][0]["value"],
      "AltaboltaVoo 800mm Weed Slasher")

print("\n--- required, and impossible to agree on ---")
# Two products written separately never share a description. Amazon requires
# both anyway, which is what the second rejection was.
truthy("bullet points differ between the children", "bullet_point" in pa["differ"])
truthy("  so do the descriptions", "product_description" in pa["differ"])
check("the parent still has bullet points", at.get("bullet_point"),
      _v("Hardened steel blade"))
check("  and a description", at.get("product_description"), _v("Black slasher"))
check("BORROWED, and it says from which product",
      pa["borrowed"].get("product_description"), "10.99_3Days_B0GGSCK998")
check("  the picture too, because a family with no image is not clicked",
      pa["borrowed"].get("main_product_image_locator"), "10.99_3Days_B0GGSCK998")
check("nothing required is left unsettled", pa["unresolved"], [])

print("\n--- borrowing is only ever for what the type demands ---")
pa2 = V.parent_attributes(KIDS, "COLOR", marketplace_id=MKT, required=[])
check("an optional attribute the children disagree on is NOT borrowed",
      pa2["attributes"].get("bullet_point"), None)
truthy("  though the picture still is", pa2["borrowed"].get("main_product_image_locator"))

print("\n--- an explicit value beats all of it ---")
pa3 = V.parent_attributes(KIDS, "COLOR", marketplace_id=MKT,
                          required=V.required_from_schema(SCHEMA),
                          extra={"product_description": _v("Written for the family")})
check("what was typed wins", pa3["attributes"]["product_description"],
      _v("Written for the family"))
check("  and is no longer called borrowed",
      pa3["borrowed"].get("product_description"), None)

print("\n--- when nobody has it, nothing is invented ---")
bare = [{"sku": "A", "raw": {"brand": _v("X"), "color": _v("Red")}},
        {"sku": "B", "raw": {"brand": _v("X"), "color": _v("Blue")}}]
pa4 = V.parent_attributes(bare, "COLOR", marketplace_id=MKT,
                          required=["brand", "product_description"])
check("the missing one is reported, not filled", pa4["unresolved"],
      ["product_description"])


print("\n=== preview and apply cannot disagree ===")
R = open(r"D:\AltaScraper\routes\variations_routes.py", encoding="utf-8").read()
check("both build the parent with the same function",
      R.count("_var.parent_attributes("), 2)
truthy("both pass the schema's required list",
       R.count("required=_var.required_from_schema(") == 2)
truthy("apply refuses rather than sending an incomplete parent",
       'error": (\n                "The parent listing still needs' in R
       or "still needs %s and neither product" in R)
truthy("Amazon's own shape is kept for writing back", '"raw": a' in R)
truthy("  and not leaked to the browser", 'if k != "raw"' in R)

D = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8").read()
truthy("the cached schema carries the attribute names", '"attribute_names"' in D)
truthy("  and the required list", '"required": [str(r) for r in (raw.get("required")' in D)

J = open(r"D:\AltaScraper\static\js\variations.js", encoding="utf-8").read()
truthy("unusable themes are shown, not silently dropped", "_varBlockedGroup" in J)
truthy("  greyed out so they cannot be picked", "disabled>" in J)
truthy("  with the reason next to each", "u.why" in J)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
