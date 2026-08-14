"""Making a variation family, and every reason to refuse before sending one.

Amazon accepts a half-formed family without complaint and the products simply
stop appearing in search. There is no error to react to, so every check has to
happen BEFORE anything is sent -- which is what this file is mostly about.
"""
import sys
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

from listing import variations as V

SCHEMA = {"properties": {"variation_theme": {
    "type": "array",
    "items": {"properties": {"name": {"enum": ["SIZE", "COLOR", "SIZE_COLOR"]}}},
}}}
NO_VAR_SCHEMA = {"properties": {"item_name": {"type": "array"}}}

def kid(sku, **attrs):
    return {"sku": sku, "product_type": "SHIRT", "attributes": attrs}

KIDS = [kid("SH-RED-S", size="Small"), kid("SH-RED-M", size="Medium"),
        kid("SH-RED-L", size="Large")]


print("=== the theme comes out of the schema, never out of us ===")
check("themes read from the product type", V.themes_from_schema(SCHEMA),
      ["SIZE", "COLOR", "SIZE_COLOR"])
check("a type with no variation_theme supports none",
      V.themes_from_schema(NO_VAR_SCHEMA), [])
check("  and neither does an empty schema", V.themes_from_schema({}), [])
check("SIZE varies on one axis", V.theme_axes("SIZE"), ["size"])
check("SIZE_COLOR varies on TWO", sorted(V.theme_axes("SIZE_COLOR")), ["color", "size"])
check("  British spelling lands on the same axis", V.theme_axes("COLOUR"), ["color"])


print("\n=== a good merge passes ===")
check("no problems", V.check("SH-PARENT", KIDS, "SIZE", SCHEMA, "SHIRT"), [])


print("\n=== and every bad one is refused, with the reason ===")
def why(parent, kids, theme, schema=SCHEMA, pt="SHIRT"):
    return " | ".join(V.check(parent, kids, theme, schema, pt))

truthy("no parent SKU", "needs a parent SKU" in why("", KIDS, "SIZE"))
truthy("only one child", "at least two products" in why("P", KIDS[:1], "SIZE"))
truthy("the parent is also a child",
       "parent is the group" in why("SH-RED-S", KIDS, "SIZE"))
truthy("the same SKU twice",
       "listed twice" in why("P", KIDS + [kid("SH-RED-S", size="Small")], "SIZE"))
truthy("no theme picked", "what makes these products different" in why("P", KIDS, ""))
truthy("a theme this type does not allow",
       "not a variation theme this product type allows" in why("P", KIDS, "FLAVOR"))
truthy("  and it says which ARE allowed", "SIZE, COLOR" in why("P", KIDS, "FLAVOR"))
truthy("a product type that cannot vary at all",
       "does not support variations at all" in why("P", KIDS, "SIZE", NO_VAR_SCHEMA))

print("  -- the ones that would silently produce a broken family --")
same = [kid("A", size="Large"), kid("B", size="Large")]
truthy("two children with the SAME size under a SIZE theme",
       "has the same size" in why("P", same, "SIZE"))
truthy("  and it explains why that is not a family",
       "compete with each other" in why("P", same, "SIZE"))
blank = [kid("A", size="Small"), kid("B")]
truthy("a child with no value on the axis", "no size set" in why("P", blank, "SIZE"))
truthy("  naming which one", why("P", blank, "SIZE").startswith("B has no size"))
mixed = [dict(kid("A", size="S"), product_type="SHIRT"),
         dict(kid("B", size="M"), product_type="SHOES")]
truthy("children of different product types",
       "different product types" in why("P", mixed, "SIZE", SCHEMA, ""))

print("  -- a two-axis theme checks BOTH axes --")
two = [kid("A", size="S", color="Red"), kid("B", size="S", color="Blue")]
check("same size, different colour is a valid SIZE_COLOR family",
      V.check("P", two, "SIZE_COLOR", SCHEMA, "SHIRT"), [])
same_both = [kid("A", size="S", color="Red"), kid("B", size="S", color="Red")]
truthy("identical on both axes is refused",
       V.check("P", same_both, "SIZE_COLOR", SCHEMA, "SHIRT"))


print("\n=== the preview IS the payload ===")
b = V.build("SH-PARENT", KIDS, "SIZE", "SHIRT")
p = b["parent"]
check("the parent is marked as one",
      p["attributes"]["parentage_level"], [{"value": "parent"}])
check("  carries the theme", p["attributes"]["variation_theme"], [{"name": "SIZE"}])
check("  and is NOT buyable: no price", "purchasable_offer" in p["attributes"], False)
check("  and no stock", "fulfillment_availability" in p["attributes"], False)

check("every child is marked as one", len(b["children"]), 3)
c0 = b["children"][0]
check("  parentage", c0["attributes"]["parentage_level"], [{"value": "child"}])
check("  the same theme as the parent",
      c0["attributes"]["variation_theme"], [{"name": "SIZE"}])
check("  and it names its parent",
      c0["attributes"]["child_parent_sku_relationship"],
      [{"child_relationship_type": "variation", "parent_sku": "SH-PARENT"}])
check("all three point at the same parent",
      {x["attributes"]["child_parent_sku_relationship"][0]["parent_sku"]
       for x in b["children"]}, {"SH-PARENT"})
check("no child carries a price either",
      any("purchasable_offer" in x["attributes"] for x in b["children"]), False)
check("the axes travel with it", b["axes"], ["size"])


print("\n=== the suggested parent SKU is only a suggestion ===")
check("built from what the children share",
      V.suggest_parent_sku(KIDS), "SH-RED-PARENT")
check("  it does not stop mid-token",
      V.suggest_parent_sku([kid("ABC-1"), kid("ABC-2")]), "ABC-PARENT")
check("nothing in common falls back to the first",
      V.suggest_parent_sku([kid("XX"), kid("ZZZZ")]), "XX-PARENT")
check("no children, no suggestion", V.suggest_parent_sku([]), "")

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
