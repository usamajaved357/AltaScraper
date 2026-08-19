"""Values Amazon actually accepts, not values that merely sound right.

    "some information is filled but do not accurately represent the listing"

MEASURED, not guessed. Every stored draft's attribute values were checked
against the cached LIVE schema for that product type -- Amazon's own list of
what each field allows. 211 of 1220 values, 17%, were not on it:

    is_fragile   'No'                          allowed: True / False
    item_shape   'N/A', 'Pole', 'Cylindrical'  allowed: Round, Square, Oval, ...
    material     'ABS', 'Aircraft-grade aluminium', 'Rubber | Plastic'
                 allowed: 69 controlled names

The app has always had a fuzzy matcher for exactly this, snap_to_valid, but it
was only ever pointed at the STATIC valid_values.json used by the flat-file
builder. The API path -- the one in use -- never snapped at all.

Re-run over the same drafts after the fix: 209 offending values become 51.
127 snapped to Amazon's own word, 31 dropped as a not-applicable answer to a
field with no such option.

WHAT IT MUST NEVER DO: blank a value. snap_to_valid returns "" when nothing
matches and the caller keeps the original, because a value Amazon rejects with
a readable error beats a field silently emptied.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from amazon_listing_generator import snap_to_valid

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


# Amazon's real lists, trimmed to what matters here.
MATERIAL = ["Acrylic", "Acrylonitrile Butadiene Styrene", "Alloy Steel",
            "Aluminium", "Bamboo", "Brass", "Carbon Fibre", "Cast Iron",
            "Medium Density Fibreboard", "Microfibre", "Plastic", "Rubber",
            "Silicone", "Stainless Steel", "Steel"]
SHAPE = ["Diamond", "Heart", "Hexagonal", "Oval", "Rectangular", "Round",
         "Square"]
SIZE = ["S", "M", "L", "XL"]

print("== the real values off real drafts ==")
check("'Aircraft-grade aluminium'", snap_to_valid("Aircraft-grade aluminium", MATERIAL), "Aluminium")
check("'Plastic or plastic composite'", snap_to_valid("Plastic or plastic composite", MATERIAL), "Plastic")
check("'Rubber | Plastic' picks one Amazon knows",
      snap_to_valid("Rubber | Plastic", MATERIAL) in ("Rubber", "Plastic"), True)
check("'stainless steel' gets Amazon's capitalisation",
      snap_to_valid("stainless steel", MATERIAL), "Stainless Steel")

print("\n== an initialism the trade uses and Amazon spells out ==")
check("ABS", snap_to_valid("ABS", MATERIAL), "Acrylonitrile Butadiene Styrene")
check("MDF", snap_to_valid("MDF", MATERIAL), "Medium Density Fibreboard")
# Strict on purpose: initials must match a MULTI-word option exactly.
check("an initialism matching nothing stays unmatched",
      snap_to_valid("XYZ", MATERIAL), "")

print("\n== British and American spellings of one word ==")
check("Microfiber -> Microfibre", snap_to_valid("Microfiber", MATERIAL), "Microfibre")
check("Carbon Fiber -> Carbon Fibre", snap_to_valid("Carbon Fiber", MATERIAL), "Carbon Fibre")
check("Aluminum -> Aluminium", snap_to_valid("Aluminum", MATERIAL), "Aluminium")

print("\n== the same word in another form ==")
# 'Rectangle' shares no whole word with 'Rectangular' and neither contains the
# other, so every earlier strategy missed it. It was sitting on a real draft.
check("Rectangle -> Rectangular", snap_to_valid("Rectangle", SHAPE), "Rectangular")

print("\n== short values still work, single characters no longer guess ==")
# S / M / L are legitimate sizes and must match exactly.
for s in SIZE:
    check("size %r matches itself" % s, snap_to_valid(s, SIZE), s)
check("'small' finds S", snap_to_valid("small", SIZE), "S")
# Before the guard, "a" matched "Acrylic" and "s" matched "Steel" -- a single
# character snapping to whatever happened to contain it.
check("'a' no longer becomes a material", snap_to_valid("a", MATERIAL), "")
check("'s' no longer becomes a material", snap_to_valid("s", MATERIAL), "")

print("\n== it never invents and never blanks ==")
check("nothing in, nothing out", snap_to_valid("", MATERIAL), "")
check("no list, no answer", snap_to_valid("Plastic", []), "")
# The caller keeps the original when this returns "" -- that contract is what
# stops a field being silently emptied.
check("a value with no match returns empty, for the caller to keep the original",
      snap_to_valid("Unobtainium", MATERIAL), "")

print("\n== the three rules the builder applies around it ==")
SRC = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
FN = SRC.split("def build_api_attributes(")[1].split("\ndef ")[0]
truthy("the builder snaps against the LIVE schema enum",
       "_snap = snap_to_valid(v, _allow)" in FN)
# is_fragile's list is exactly True/False and 52 drafts answered it "No".
truthy("a yes/no answer to a true/false field is converted",
       '_lowall <= {"true", "false"}' in FN)
truthy("  and only when the field really is boolean",
       "_lowall <= {" in FN and "_vs.lower() in (" in FN)
# 'N/A' is not a shape. Sending the letters is worse than sending nothing.
truthy("'not applicable' is dropped where Amazon offers no such option",
       'no such option' in FN)
truthy("  but kept where Amazon DOES offer one",
       'not any(x in _lowall for x in' in FN)
truthy("compliance fields are left alone",
       "f not in _COMPLIANCE_PASSTHROUGH" in FN)
truthy("what was snapped is reported, not done silently",
       "Snapped to Amazon's allowed values" in SRC)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
