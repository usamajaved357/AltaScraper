"""Two reports about the compliance warnings, and both had a different shape
than the report supposed.

    "1. DUPLICATE WARNINGS -- listing/warnings.py stores the same warning twice
     in the warnings JSON array."

NOT THE SAME TYPE TWICE. for_rows builds one warning of each type and
recompute_workspace REPLACES the column rather than appending, so that cannot
happen -- and MEASURED, it does not: 0 of the 171 rows carrying warnings hold a
duplicate (type, message).

What does happen, and is what a reader means, is the same SENTENCE under two
headings: ip_risk and compliance_risk both fell back to the row's general
`notes`, so a listing carrying both risks printed one sentence twice. Measured:
2 rows on jack_uk, both reading "RE-VERIFIED -- LIVE | COMPLIANCE [HIGH]:
electrical | Key reqs..." as an IP warning and again as a compliance one.

    "2. FALSE COMPLIANCE FLAGS -- the compliance checker is matching categories
     like health_beauty, knives_blades, tools_hardware against products that
     don't belong to those categories."

True, and the mechanism is a STRONG keyword that is ordinary English out of
context. Measured on the stored listings, all three title matches that the
existing title/body and weak-keyword rules happily assign:

    "Universal MIXER Tap to Garden Hose"   -> electrical   (plumbing)
    "No-Pump VACUUM Storage Bags"          -> electrical   (says no pump)
    "Coil Spring COMPRESSOR 380mm"         -> electrical   (a hand tool)

THE FIX IS THE PRODUCT TYPE, and the direction of the gate is the whole design:
it can only ever turn a flag DOWN, only on a written-down exclusion, and never
on missing data. A compliance check that guesses its way to silence is worse
than one that is noisy, so every uncertainty flags exactly as it did before.

WHY A BLACKLIST AND NOT THE WHITELIST THAT WAS ASKED FOR. The report suggests
"skip health_beauty unless the product_type is actually health/beauty". A
whitelist means a genuine cosmetic filed under a product type nobody thought to
list gets NO CPSR flag -- a false negative on a legal requirement, which is the
one direction this must not fail in. The blacklist reaches the same result for
the case reported (a tripod stops getting cosmetics rules) without that risk.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def rd(p):
    return io.open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


GEN = rd("amazon_listing_generator.py")
WARN = rd("listing/warnings.py")
FLAGS = rd("listing/flags.py")
RULES = json.loads(rd("compliance_rules.json"))

# The real function, lifted out rather than reimplemented -- the module imports
# rich and sp_api and a great deal else that a test has no business loading.
_ns = {}
_i = GEN.index("def _product_type_allows(")
_j = GEN.index("def check_compliance(")
exec(GEN[_i:_j], _ns)
allows = _ns["_product_type_allows"]


def gate(cat, pt):
    return allows(cat, RULES.get(cat, {}), pt)


print("=== the gate can only ever turn a flag DOWN ===")
# EVERY UNCERTAINTY FLAGS. These four are the ones that matter: a missing field
# must never be read as permission to go quiet.
truthy("no product type at all -> unchanged", gate("electrical", ""))
truthy("  a None product type -> unchanged", gate("electrical", None))
truthy("  a type nobody has written a rule about -> unchanged",
       gate("electrical", "SOMETHING_NOBODY_LISTED"))
truthy("  a category with no gate at all -> unchanged",
       gate("supplements", "TRIPOD"))
truthy("and the direction is written down",
       "can only ever turn a flag DOWN" in GEN)

print("\n=== the false flags that were measured ===")
for cat, pt, what in (("electrical", "STORAGE_BAG", "No-Pump Vacuum Storage Bags"),
                      ("electrical", "THERMOS", "an insulated flask"),
                      ("electrical", "HOSE_PIPE_FITTING", "a hose fitting"),
                      ("electrical", "BLADED_FOOD_PEELER", "a peeler"),
                      ("health_beauty", "TRIPOD", "a selfie stick"),
                      ("health_beauty", "CAMERA_ACCESSORY", "a phone mount"),
                      ("knives_blades", "FAN", "a fan blade"),
                      ("toys_children", "PET_TOY", "a pet ball")):
    falsy("%-14s no longer applies to %-20s (%s)" % (cat, pt, what), gate(cat, pt))

print("\n=== and NOTHING genuine was suppressed ===")
# This is the half that matters. Every one of these is a real match on this
# account's own data.
for cat, pt in (("electrical", "LIGHT_FIXTURE"), ("electrical", "VACUUM_CLEANER"),
                ("electrical", "ELECTRIC_LANTERN"), ("electrical", "LAMP"),
                ("electrical", "HAIR_TRIMMER"), ("electrical", "KEYBOARD_MOUSE_SET"),
                ("electrical", "LIGHTED_OUTDOOR_DISPLAY"),
                ("health_beauty", "SKIN_MOISTURIZER"),
                ("health_beauty", "SKIN_TREATMENT_MASK"),
                ("toys_children", "TOY_FIGURE"),
                ("knives_blades", "KITCHEN_KNIFE"),
                ("medical_devices", "BLOOD_PRESSURE_MONITOR")):
    truthy("%-15s still applies to %s" % (cat, pt), gate(cat, pt))

# AMBIGUOUS TYPES ARE LEFT ALONE ON PURPOSE. OUTDOOR_LIVING really does include
# solar lights and patio heaters; AUTO_PART really does include trailer lamps --
# one of them flags correctly on this very account. Excluding either to catch
# one bad title would suppress real ones.
print("\n=== a genuinely ambiguous type is not gated ===")
truthy("OUTDOOR_LIVING can still be electrical", gate("electrical", "OUTDOOR_LIVING"))
truthy("  and so can AUTO_PART", gate("electrical", "AUTO_PART"))
truthy("  which is said, not left to be discovered",
       "genuinely includes" in GEN or "AUTO_PART really does" in
       (io.open(os.path.join(HERE, "test_compliance_product_type.py"),
                encoding="utf-8").read()))

print("\n=== a downgraded match is reported, never deleted ===")
_cc = GEN[GEN.index("def check_compliance("):]
_cc = _cc[:_cc.index("\ndef ", 10)] if "\ndef " in _cc[10:] else _cc
truthy("it moves to the mentioned list", "_pt_verdict is False" in _cc
       and "mentioned.append" in _cc)
truthy("  naming the word that fired", "_matched_kw +" in _cc)
truthy("  and what Amazon calls the product", "Amazon calls" in _cc)
falsy("  nothing is dropped outright",
      re.search(r"_pt_verdict is False:\s*\n\s*continue", _cc) is not None)

print("\n=== the rulebook holds the lists, not the code ===")
truthy("the exclusions are data", "product_type_never" in json.dumps(RULES))
for cat in ("electrical", "health_beauty", "knives_blades", "tools_hardware"):
    truthy("  %s has one" % cat, bool(RULES.get(cat, {}).get("product_type_never")))
truthy("and the file says what the field means",
       "product_type_gate" in RULES.get("_meta", {}))
# The whitelist form exists for a category that ever wants it, and is not used.
truthy("a whitelist form exists", "product_type_only" in GEN)

print("\n=== the product type actually reaches the checker ===")
truthy("check_compliance takes it", "def check_compliance(item_name: str, listing: dict, rules: dict,"
       in GEN and "product_type: str = \"\"" in GEN)
truthy("  the generator passes it", 'listing.get("product_type", "")' in GEN)
truthy("  and the flags pass runs it too",
       "check_compliance(listing[\"title\"], listing, compliance_rules,\n                            product_type)" in FLAGS)
# It was already in scope there, handed to the sibling check on the next line.
truthy("  it was already in scope, one line below",
       "check_category_claims(listing, product_type)" in FLAGS)

print("\n=== the same sentence is not shown twice ===")
truthy("compliance reads its OWN field first",
       '_s(row, "compliance_notes") or _s(row, "notes")' in WARN)
truthy("  and ip_risk still reads the general one", 'def ip_risk' in WARN)
truthy("there is a guard as well as a fix", "def _dedupe" in WARN)
truthy("  applied to every row", "_dedupe([w for w in found if w])" in WARN)
truthy("  keyed on the message, not only the type", '("*", msg)' in WARN)
truthy("  and the first one wins", "THE FIRST ONE WINS" in WARN)
truthy("the measurement that found it is recorded",
       "0 rows out of 171" in WARN)

# THE DEDUPE ITSELF, RUN.
_wns = {}
_wi = WARN.index("def _dedupe(")
_wj = WARN.index("\ndef ", _wi + 10)
exec(WARN[_wi:_wj], _wns)
dd = _wns["_dedupe"]
a = {"type": "ip_risk", "severity": "high", "message": "Same words."}
b = {"type": "compliance_risk", "severity": "medium", "message": "Same words."}
c = {"type": "no_barcode", "severity": "low", "message": "Different words."}
check("two types, one sentence -> one warning", len(dd([a, b, c])), 2)
check("  the first is the one kept", dd([a, b, c])[0]["type"], "ip_risk")
check("  and a different sentence survives", dd([a, b, c])[1]["type"], "no_barcode")
check("the same warning twice -> once", len(dd([a, dict(a)])), 1)
check("whitespace is not a difference",
      len(dd([a, {"type": "x", "message": "Same   words."}])), 1)
check("nothing in, nothing out", dd([]), [])
check("an empty message is not treated as a duplicate of another empty one",
      len(dd([{"type": "a", "message": ""}, {"type": "b", "message": ""}])), 2)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
