"""Do not send Amazon attributes the product type does not have.

    "we dont need to be sending unnecessary information to amazon like
     [W] included_components  You submitted an attribute Included Components
     that does not belong or is no longer applicable to the product type you
     were trying to list."

MEASURED, on the four real SQUEEGEE drafts in Nestwell Goods. SQUEEGEE's live
schema declares 140 attribute names. Each draft carried 7 to 11 attributes that
are not among them:

    included_components   item_condition      item_type_keyword
    unit_count_type       special_features    contains_liquid_contents
    item_height / item_length / item_width / item_package_*

The generation prompt asks the AI for those names on every product, whatever its
type, and build_api_attributes then wrote every key it found -- deliberately,
because an earlier fix had found that dropping unlisted keys lost values Amazon
really did want (special_feature, warranty_description, safety_data_sheet_url).

Both halves are true. The resolution is not "keep everything" or "drop anything
unlisted", it is:

  * three of those names ARE real attributes under a different name, so they are
    RENAMED rather than dropped -- the value is researched and worth keeping;
  * a name the schema has never heard of is dropped, and NAMED in the log;
  * and nothing is dropped at all when no schema loaded, because then "Amazon
    has no such field" cannot be told apart from "we failed to ask".
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


SRC = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
FN = SRC.split("def build_api_attributes(")[1].split("\ndef ")[0]

print("== the gate exists, and only bites when a schema loaded ==")
truthy("the schema's own names are collected",
       "_schema_names = set(props or {}) | set(required or set())" in FN)
truthy("  an unknown attribute is skipped",
       "if not _fprop and _schema_names and f not in _schema_names:" in FN)
# THE GUARD THAT MATTERS. Without `_schema_names and`, a failed schema fetch
# would strip every attribute off a perfectly good listing.
truthy("  and never when the schema failed to load",
       "_schema_names and f not in _schema_names" in FN)
truthy("what was dropped is collected", "_dropped_unknown" in FN)
truthy("  and printed, not silently discarded",
       "has no such attribute" in FN)

print("\n== the ones that are real under another name are RENAMED ==")
for ours, amazons in (("special_features", "special_feature"),
                      ("item_condition", "condition_type"),
                      ("colour", "color")):
    truthy("%s -> %s" % (ours, amazons),
           '"%s": "%s"' % (ours, amazons) in FN)
# condition_type is set by this function itself, so the AI's duplicate must not
# overwrite the correct new_new with the word "New".
truthy("the builder still sets condition_type itself",
       'put("condition_type", _shape_simple(props["condition_type"], "new_new", mid))' in FN)
truthy("  and an aliased key cannot overwrite it",
       "if f in A or f in _special_shape:" in FN)

print("\n== the fields an earlier fix was protecting are still protected ==")
# These were the reason the loop kept unlisted keys. They are handled by the
# specialised shaper ABOVE the loop, so they never reach the drop at all.
for name in ("special_feature", "warranty_description", "safety_data_sheet_url"):
    truthy("%s is shaped specially, not dropped" % name,
           '"%s"' % name in FN.split("_special_shape = {")[1].split("}")[0])

print("\n== the function still compiles and kept its shape ==")
tree = ast.parse(SRC)
names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
truthy("build_api_attributes is still there", "build_api_attributes" in names)

print("\n== Rule 1 is untouched by any of this ==")
truthy("merchant_suggested_asin is still stripped",
       'for _forbidden in ("merchant_suggested_asin", "merchant_suggested_asin_type")' in SRC)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
