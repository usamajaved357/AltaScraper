"""A product with no battery must not be declared as dangerous goods.

THE BUG. build_api_attributes builds the `hazmat` attribute from Amazon's live
schema. Its free-text `value` sub-field was filled with "UN3481" -- the UN
number for "lithium-ion batteries contained in equipment" -- for EVERY product
whose schema declares a hazmat field, battery or no battery.

The gate was written and then never used. Six lines above it:

    # Does this product carry a (lithium) battery? hazmat is only meaningful then.
    _hz_has_batt = (...)

and `_hz_has_batt` was never read again -- pyflakes reports it as an assigned-
but-unused local. The comment on the line that fills the value even claimed a
gate existed: "(Only reached when hazmat is being built, which is itself gated
on a battery being present.)" It was not.

WHY IT MATTERS MORE THAN A WRONG FIELD. A UN number is a dangerous-goods
DECLARATION, made to Amazon, on the owner's behalf, about a product he never
said was hazardous. CLAUDE.md Rule 1 forbids exactly this shape of thing for the
GTIN exemption ("Claiming the exemption is a DECLARATION TO AMAZON ... The app
must never make that declaration on his behalf"), and the GHS block 700 lines
earlier in the same file already refuses to "mislabel the product with a real
hazard class" rather than satisfy a required field dishonestly.

The no-schema fallback branch, sixty lines below the bug, gated on the battery
and always did -- so the same generator answered the same question two different
ways depending on whether Amazon's schema happened to load.

These tests read the source rather than running build_api_attributes, which
needs a live schema, a marketplace and a console. What is asserted is the shape
of the decision: the gate exists, it is used at both places the UN number can be
set, and the fallback branch still agrees with it.
"""
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
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


SRC = open("amazon_listing_generator.py", encoding="utf-8").read()

# The whole hazmat section: from the schema-loaded branch to the minimal-mode
# block that follows it.
HZ = SRC.split("# hazmat: build from the LIVE schema structure")[1]
HZ = HZ.split("# MINIMAL MODE:")[0]
SCHEMA_BRANCH = HZ.split("        # SCHEMA DIDN'T LOAD for hazmat")[0]
FALLBACK_BRANCH = HZ.split("        # SCHEMA DIDN'T LOAD for hazmat")[1]

print("=== the battery gate exists and is actually used ===")
truthy("the gate is worked out", "_hz_has_batt = (" in SCHEMA_BRANCH)
# The bug in one line: assigned once, read never.
_uses = len(re.findall(r"_hz_has_batt", SCHEMA_BRANCH))
truthy("  and it is read, not just assigned (this is the bug)", _uses >= 3)
print("     _hz_has_batt appears %d times in the schema branch" % _uses)

print("\n=== the UN number is only set when there is a battery ===")
# Both places the UN number can be written must be gated. The second one --
# "guarantee the UN number is present" -- would otherwise put it straight back
# for a product type whose `aspect` enum offers no not-applicable option, since
# that falls through to _senum[0], which IS united_nations_regulatory_id.
_un_lines = [ln.strip() for ln in SCHEMA_BRANCH.splitlines()
             if "UN3481" in ln and not ln.strip().startswith("#")]
check("there are exactly two places the UN number is set", len(_un_lines), 2)
truthy("  the sub-field loop is gated",
       'elif _sk == "value" and _hz_has_batt:' in SCHEMA_BRANCH)
truthy("  and so is the belt-and-braces line below it",
       re.search(r"if \(_hz_has_batt\s*\n\s*and str\(_hz_obj\.get\(\"aspect\"",
                 SCHEMA_BRANCH) is not None)

print("\n=== a product with no battery declares nothing ===")
# With no battery, _hz_obj never gets a `value`, and the existing guard below
# refuses to ship a hazmat object without one -- so it is dropped, which is the
# same answer the fallback branch gives.
truthy("an object with no value is not shipped",
       'if _has_real_subfield and _hz_obj.get("value"):' in SCHEMA_BRANCH)
truthy("  and dropping it says why, so it is visible rather than silent",
       "no battery evidence" in SCHEMA_BRANCH)

print("\n=== the two branches agree with each other ===")
# The fallback branch was always right. It is asserted here so a future edit
# cannot fix one branch and leave the other, which is how this started.
truthy("the no-schema branch still gates on a battery",
       "if _hz_batt:" in FALLBACK_BRANCH)
truthy("  and still drops a half-built hazmat when there is none",
       'A.pop("hazmat", None)' in FALLBACK_BRANCH)

print("\n=== the file's own policy, stated elsewhere, is not contradicted ===")
# The GHS block would rather flip the DG regulation away from 'ghs' than claim a
# hazard class the product does not have. Same question, same answer.
truthy("GHS refuses to mislabel a non-chemical product",
       "rather than mislabel the" in SRC)
truthy("  and never invents a GHS class when the schema offers no honest one",
       "no honest GHS class -> stop declaring GHS as the DG regulation" in SRC)

print("\n=== Rule 1: the exemption is never claimed by the app ===")
# Sitting alongside, because it is the same principle and the same file was
# where it was got right. listing/barcode.py used to instruct the opposite.
BC = open(os.path.join("listing", "barcode.py"), encoding="utf-8").read()
falsy("the barcode module no longer tells callers to claim the exemption",
      "must claim the GTIN\n    exemption" in BC)
truthy("  it says send nothing instead", "must send NOTHING" in BC)
truthy("  and carries the owner's own words for why",
       "dont apply for exemption automatically" in BC)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
