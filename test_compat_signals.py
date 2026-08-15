"""Compatibility is not identity.

THE REPORT: "Hand-Forged Iron Wok 28cm Uncoated Flat Bottom with Wooden Lid"
came back as a HIGH RISK mains-powered electrical product needing a BS EN 60335
test report from an ISO 17025 lab. It is a lump of steel.

WHAT ACTUALLY HAPPENED. The title on its own was clean. The listing's bullets
said, perfectly correctly:

    "Works on gas, electric and induction hobs, and in the oven up to 250C"

and the rule paired its corroborating words (iron, oven, hob) with its context
word (electric) and fired. The word was there; it described what the pan is
USED WITH.

WHY THIS MATTERS MORE THAN IT LOOKS. A false HIGH RISK is not a harmless extra
check. It is the fastest way to teach someone to ignore this panel, and the
panel exists for the electric patio heater that listed quietly and then had a
test report demanded months later. Every false alarm spends the credibility the
real one depends on.

THE FIX, in the same shape as the accessory rule that already existed ("patio
heater COVER" is not a heater): a trigger that appears ONLY inside a
compatibility phrase is dropped from the evidence. Dropped, not vetoed -- a
listing that says both "works on electric hobs" AND "1500W mains powered" still
has the second, and must still fire.
"""
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from listing.sourcing_viability import check_sourcing_viability
from listing.restricted import compat_pattern, COMPAT_LEADS


def ids(**kw):
    r = check_sourcing_viability(marketplace="UK", **kw)
    return sorted((m.get("id") or "") for m in (r.get("risks") or r.get("matches") or []))


WOK = "Hand-Forged Iron Wok 28cm Uncoated Flat Bottom with Wooden Lid"
WOK_BULLETS = [
    "Works on gas, electric and induction hobs, and in the oven up to 250C",
    "Season the wok before first use, then re-season after each deep clean",
    "Uncoated carbon steel - no chemical coating to scratch or flake",
    "Flat bottom sits steady on any hob without a wok ring",
]

print("=== the wok that started this ===")
check("the title alone was always clean", ids(title=WOK), [])
check("and now the bullets are too", ids(title=WOK, bullets=WOK_BULLETS), [])
check("  bullets on their own as well", ids(bullets=WOK_BULLETS), [])

print("\n=== the phrase that did it ===")
check("works on ... electric hobs",
      ids(title="Wok", bullets=["Works on gas, electric and induction hobs"]), [])
for lead in ["compatible with", "suitable for", "for use on", "safe for",
             "designed for", "ideal for", "can be used on"]:
    check("  %-18s electric hobs" % lead,
          ids(title="Wok", bullets=[lead + " electric and induction hobs"]), [])

print("\n=== but a product that IS electrical still fires ===")
# The whole point of the panel. These must be untouched.
truthy("a 2100W patio heater",
       "MAINS_ELECTRICAL" in ids(title="Electric Patio Heater 2100W with UK plug"))
truthy("a mains-powered hair dryer",
       "MAINS_ELECTRICAL" in ids(title="Hair Dryer 2000W mains powered, BS1363 plug"))
truthy("an electric hob itself", "MAINS_ELECTRICAL" in ids(title="Electric hob"))

print("\n=== and a listing that says BOTH still fires ===")
# Dropped from the evidence, not a veto on the whole rule. A kettle that
# mentions being compatible with something is still a kettle.
truthy("works on electric hobs AND is itself 1500W mains powered",
       "MAINS_ELECTRICAL" in ids(
           title="Electric Kettle",
           bullets=["Works on electric hobs", "1500W mains powered with UK plug"]))

print("\n=== word boundaries, which were already right ===")
# Checked because the report named them: "Uncoated" reading as "coat", and a
# seasoned pan reading as "seasoning".
check("'Uncoated' does not name a coat", ids(title="Uncoated cast iron pan"), [])
check("'season the wok' is not a seasoning", ids(title="Season the wok before use"), [])
truthy("but a real coat still counts",
       "TEXTILES_CLOTHING" in ids(title="Winter coat, wool"))
truthy("and a real seasoning still counts",
       "FOOD_GROCERY" in ids(title="Cajun seasoning 200g"))

print("\n=== the pattern itself ===")
p = compat_pattern("electric")
truthy("it matches across the words a real sentence puts in between",
       bool(p.search("works on gas, electric and induction hobs")))
truthy("  and a plain compatibility phrase", bool(p.search("compatible with electric ovens")))
check("but not a lead that is a whole clause away",
      bool(p.search("suitable for children. This electric heater is rated 2000W")), False)
check("and not the trigger on its own", bool(p.search("electric heater")), False)
truthy("there are several leads, because people write this many ways",
       len(COMPAT_LEADS) > 10)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
