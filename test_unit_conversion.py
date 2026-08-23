"""A measurement Amazon will not take in the unit we hold it in.

FOUND BY TAKING FIVE REAL DRAFTS TO PREVIEW against Amazon. Three passed, two
did not, and one of the two was this:

    SKU     10.99_3Days_B0GGSDFPSH  "Weed Slasher 27-Inch Hardened Steel"
    type    RAKE
    reply   [E] item_width_height 'Item Height Unit' is required but missing

Three things were true at the same time:

    the draft held    item_height  "36.0 inches"
    Amazon's schema   height.unit  enum: ["centimeters"]
    Amazon reported   the unit MISSING

_snap_enum will not match "inches" to "centimeters", and it is right not to --
they are different units, and matching them would send 36 where 91.44 belongs.
But the object was then dropped for want of a unit, so a listing was blocked by
a measurement it HAD, and the error named the wrong problem: it said missing
when the truth was "in a unit this category does not accept".

So the value is converted instead. 36 inches IS 91.44 centimetres; there is no
judgement in it. After the fix that SKU previews clean against Amazon --
"ok: 1, errors: 0" -- which is the only proof that counts here.

TWO THINGS THIS DELIBERATELY DOES NOT DO. It never converts between different
KINDS of measurement, and it never invents a unit where the schema offers a real
choice -- two permitted units mean the answer changes the number beside it, so
it stays missing and gets reported.
"""
import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from listing import shaper as S

MID = "A1F83G8C2ARO7P"


print("=== the arithmetic, in the spellings that really arrive ===")
# THE SPELLINGS MATTER. _norm_tok strips one trailing "s", so "inches" arrives
# as "inche" -- writing only the tidy singular in the table is how "36 inches"
# silently failed to convert while "1 foot" worked.
for v, frm, to, want in [(36, "inches", "centimeters", 91.44),
                         (36, "inch", "centimeters", 91.44),
                         (1.2, "inches", "centimeters", 3.05),
                         (27, "inches", "centimeters", 68.58),
                         (1, "foot", "centimeters", 30.48),
                         (1, "feet", "centimeters", 30.48),
                         (100, "centimeters", "meters", 1.0),
                         (2, "pounds", "grams", 907.18),
                         (16, "ounces", "grams", 453.59),
                         (5, "centimeters", "centimeters", 5.0)]:
    check("  %-5s %-12s -> %s" % (v, frm, to), S.convert_unit(v, frm, to), want)


print("\n=== and what it refuses ===")
# A unit table is a place to be quietly wrong, so it holds only what can be
# checked in a line, and anything else is refused rather than approximated.
for v, frm, to, why in [(5, "centimeters", "grams", "length is not mass"),
                        (5, "parsecs", "centimeters", "unknown unit"),
                        (5, "amps", "volts", "neither is known"),
                        ("x", "inches", "centimeters", "not a number"),
                        (5, "", "centimeters", "no unit given"),
                        (5, "inches", "", "no target")]:
    check("  %-28s (%s)" % ("%s %s -> %s" % (v, frm or "''", to or "''"), why),
          S.convert_unit(v, frm, to), None)


print("\n=== the real case, through the shaper ===")
# Amazon's own RAKE shape for the field that failed.
RAKE = {"type": "object", "properties": {
    "height": {"type": "object", "required": ["value", "unit"], "properties": {
        "value": {"type": "number"},
        "unit": {"type": "string", "enum": ["centimeters"]}}},
    "width": {"type": "object", "required": ["value", "unit"], "properties": {
        "value": {"type": "number"},
        "unit": {"type": "string", "enum": ["centimeters"]}}}}}
out = S.shape_by_schema(RAKE, {"height": "36.0 inches", "width": "1.2 inches"}, MID)
check("  the height converts", (out.get("height") or {}), {"value": 91.44, "unit": "centimeters"})
check("  and so does the width", (out.get("width") or {}), {"value": 3.05, "unit": "centimeters"})
# It must not disturb a measurement that was already acceptable.
ok_already = S.shape_by_schema(RAKE, {"height": "50 centimeters",
                                      "width": "3 centimeters"}, MID)
check("  a value already in the right unit is untouched",
      (ok_already.get("height") or {}), {"value": 50.0, "unit": "centimeters"})


print("\n=== a one-value enum is filled; a real choice is not ===")
ONE = {"type": "object", "required": ["value", "unit"], "properties": {
    "value": {"type": "number"}, "unit": {"type": "string", "enum": ["centimeters"]}}}
TWO = {"type": "object", "required": ["value", "unit"], "properties": {
    "value": {"type": "number"},
    "unit": {"type": "string", "enum": ["centimeters", "inches"]}}}
check("  one permitted unit, none supplied -> filled",
      S.shape_by_schema(ONE, {"value": 36}, MID), {"value": 36.0, "unit": "centimeters"})
# Two permitted units and no answer is a real gap: centimeters or inches changes
# the number beside it, so it stays missing and is reported.
check("  two permitted units, none supplied -> left missing",
      S.shape_by_schema(TWO, {"value": 36}, MID), {})
check("  and a supplied one is honoured, not overridden",
      S.shape_by_schema(TWO, "36 inches", MID), {"value": 36.0, "unit": "inches"})


print("\n=== a unit it cannot convert is still reported, never guessed ===")
VOLT = {"type": "object", "required": ["value", "unit"], "properties": {
    "value": {"type": "number"}, "unit": {"type": "string", "enum": ["volts"]}}}
check("  '5 amps' into a volts-only field stays empty",
      S.shape_by_schema(VOLT, "5 amps", MID), {})


print("\n=== the note in the code says which listing proved it ===")
SRC = open("listing/shaper.py", encoding="utf-8").read()
truthy("the SKU is named", "10.99_3Days_B0GGSDFPSH" in SRC or "Weed Slasher" in SRC)
truthy("  with Amazon's own wording", "is required but missing" in SRC)
truthy("  and what the schema actually said",
       'enum: ["centimeters"]' in SRC)
# The table is keyed on the normaliser's output, and that is the thing a future
# edit would get wrong.
truthy("the plural trap is written down", "inche" in SRC and "_norm_tok" in SRC)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
