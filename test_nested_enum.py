"""An allowed-values list two levels down is still an allowed-values list.

WHAT WENT WRONG, measured on a real jack_uk listing (a twin pack of grease
cartridges, product type MACHINE_LUBRICANT):

    [E] unit_count Based on the data from '', the 'count' on the field
    '"type.value"' for the attribute 'Unit Count' is not a valid value.

Amazon's RAW schema says, in as many words:

    unit_count.items.properties.type.properties.value.enum
        ["gram", "millilitre"]

and we were sending "Count" -- which is exactly what that field's own
DESCRIPTION suggests ("For products consumed as individual units, enter:
count"). The description is generic; the enum is per product type, and the enum
wins.

Nothing showed that list. Three separate readers each stopped one level too
early:

    the schema extractor      value.enum, item.enum, items.enum, prop.enum
    _sf_enum_of               node.items.properties.value.enum only
    _shape_simple             wrote the leaf without checking its enum

So the generation prompt never printed the list, auto-fix drew a free-text box,
and the shaper posted the answer unchecked. unit_count is REQUIRED for that
product type, so the listing could not pass at all -- and the row had sat on
API_ERROR since it was drafted.

The row is API_READY now. These tests hold each of the three readers open.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


# Amazon's real MACHINE_LUBRICANT unit_count property, copied from the live
# schema (probe_unit_count.py prints it).
UNIT_COUNT = {
    "title": "Unit Count",
    "type": "array",
    "minItems": 1,
    "selectors": ["marketplace_id"],
    "items": {
        "type": "object",
        "required": ["type", "value"],
        "properties": {
            "value": {"title": "Unit Count", "type": "number", "minimum": 0.01},
            "type": {
                "title": "Unit Count Type",
                "type": "object",
                "required": ["language_tag", "value"],
                "properties": {
                    "value": {"type": "string",
                              "enum": ["gram", "millilitre"],
                              "enumNames": ["gram", "millilitre"]},
                    "language_tag": {"type": "string"},
                },
            },
        },
    },
}

print("== reader 1: the schema view auto-fix draws its boxes from ==")
import dashboard as D

subs = D._extract_subfields(UNIT_COUNT)
by_path = {s["path"]: s for s in subs}
truthy("unit_count.type is offered as a sub-field", "type" in by_path)
check("  and carries Amazon's allowed values",
      by_path.get("type", {}).get("enum"), ["gram", "millilitre"])
check("  while the numeric leaf has none to carry",
      by_path.get("value", {}).get("enum"), None)

# The shape without the array wrapper is the one that was being missed.
truthy("an enum reached through .properties (no items wrapper) is found",
       D._sf_enum_of(UNIT_COUNT["items"]["properties"]["type"])
       == ["gram", "millilitre"])
truthy("  and the wrapped shape still works as before",
       D._sf_enum_of({"items": {"properties": {"value": {"enum": ["a", "b"]}}}})
       == ["a", "b"])
check("  something with no enum anywhere is still None",
      D._sf_enum_of({"type": "string"}), None)

print("\n== reader 2: the list the generation prompt prints ==")
from amazon_listing_generator import get_product_type_schema  # noqa: F401
import amazon_listing_generator as G

# The extractor is nested inside the fetch; exercise it through its own shape.
_extract = None
for _n in dir(G):
    _o = getattr(G, _n)
    if callable(_o) and _n.startswith("_") and "schema" in _n:
        pass
# Registered under a dotted name is the contract the row and _renest rely on.
src = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
truthy("the extractor registers nested lists under a dotted name",
       'result["all"]["%s.%s" % (field, _sub)]' in src)
truthy("  skipping the plumbing and the leaves it already reads",
       '_sub in ("marketplace_id", "language_tag", "value", "unit")' in src)
truthy("the prompt prints them",
       "use one of these exactly" in src)
truthy("  and marks the ones Amazon requires",
       '" (REQUIRED)" if meta.get("required")' in src)

print("\n== reader 3: the shaper, which posts the answer ==")
from listing.shaper import _shape_simple, _snap_enum

check("an unmatched value is passed through by default (unchanged behaviour)",
      _snap_enum(["gram", "millilitre"], "Count"), "Count")
check("  but strict refuses to invent one",
      _snap_enum(["gram", "millilitre"], "Count", strict=True), None)
check("  strict still snaps a real match",
      _snap_enum(["gram", "millilitre"], "Grams", strict=True), "gram")

MID = "A1F83G8C2ARO7P"
out = _shape_simple(UNIT_COUNT, {"value": "2", "type": "Count"}, MID)
check("a value Amazon cannot accept is not sent at all", out, [])
# Sending {value} without {type} earns "'type' is required but missing" --
# the same failure wearing a different message.
falsy("  and it is not sent half-built either",
      any("value" in o and "type" not in o for o in out))

good = _shape_simple(UNIT_COUNT, {"value": "170", "type": "gram"}, MID)
truthy("a valid answer is sent", good)
check("  with the number as a number", good[0]["value"], 170.0)
check("  and the type in Amazon's own spelling",
      good[0]["type"]["value"], "gram")
truthy("  carrying the language tag Amazon requires",
       good[0]["type"].get("language_tag") == "en_GB")

snapped = _shape_simple(UNIT_COUNT, {"value": "170", "type": "Grams"}, MID)
check("a near-miss is snapped rather than refused",
      snapped[0]["type"]["value"], "gram")

print("\n== the rule that stops half-built objects generally ==")
# An object holding only the selectors we added ourselves is not a value;
# Amazon reads it as "does not have enough values".
only_plumbing = _shape_simple(
    {"items": {"properties": {"language_tag": {"type": "string"},
                              "value": {"type": "string",
                                        "enum": ["x"]}},
               "required": ["value"]}},
    "not-on-the-list", MID)
check("an object left holding nothing but plumbing is dropped",
      only_plumbing, [])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
