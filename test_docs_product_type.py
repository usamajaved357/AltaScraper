"""Amazon's own product type can FIRE a document rule, not only silence one.

    "i want to correct the logic which dont highlights wrong or miss the things
     needed to be highlighted for all future items"

THE GAP, measured across the 173 stored drafts in nestwell_goods and jack_uk.
A risk class could say `not_product_types` -- a veto, so a garden chair stops
demanding a Cosmetic Product Safety Report because "sunscreen fabric" is in its
description. There was no opposite. The product type could stop a rule and never
start one, so the most authoritative fact available was ignored whenever the
title happened not to contain a listed word:

    product_type BATTERY      "6V 4R25 Zinc-Carbon Lantern Batteries 996"
                              No risk at all. The battery class is triggered by
                              "lithium", "li-ion", "18650" -- and these are
                              zinc-carbon, so every non-lithium chemistry fell
                              through a rule whose own label said lithium.

    product_type POWER_STRIP  "6 Gang Extension Lead Individually Switched"
                              No risk at all. "extension lead" was not a trigger
                              word, though a mains extension lead is among the
                              most enforced things OPSS looks at.

A title is written by a person and can say anything. A product type is chosen
from Amazon's taxonomy, so where one exists it is better evidence than the prose.

AND IT MUST NOT CRY WOLF. The veto still runs first, `exclude` still applies, and
the types listed are only those where the classification IS the risk. Checked
against the tools that merely mention the risky thing -- a battery cable crimping
tool, a grease gun, a paint roller -- all of which stay clean.
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
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from listing.sourcing_viability import check_sourcing_viability as V


def risks(title, pt="", cat="", mkt="UK"):
    r = V(title=title, bullets=[], product_type=pt, category=cat, marketplace=mkt)
    return {x["id"] for x in (r.get("risks") or [])}


print("=== the two the audit found, both now flagged ===")
truthy("a product Amazon types BATTERY needs battery documents",
       "BATTERY_POWERED" in risks(
           "6V 4R25 Zinc-Carbon Lantern Batteries 996 PJ996 908 430", "BATTERY"))
truthy("  and it no longer has to be lithium to count",
       "BATTERY_POWERED" in risks("6V 4R25 Zinc-Carbon Lantern Batteries", ""))
truthy("a mains extension lead is a mains electrical product",
       "MAINS_ELECTRICAL" in risks(
           "6 Gang Extension Lead Individually Switched 2 Metre Cable"))
truthy("  by its type as well as its words",
       "MAINS_ELECTRICAL" in risks("6 Gang Trailing Block", "POWER_STRIP"))


print("\n=== and the tools that only MENTION them stay clean ===")
# Every one of these is a real row in the accounts. A warning on them is the
# kind that teaches somebody to click past the one that matters.
falsy("a battery cable crimping tool is not a battery",
      risks("Battery Cable Lug Crimping Tool Kit with 60 Copper Ring Terminals",
            "CRIMPING_PLIERS") & {"BATTERY_POWERED"})
falsy("a grease gun is a tool, not the grease",
      risks("Heavy Duty Pistol Grip Grease Gun 6000 PSI Aluminium 400cc",
            "AUTO_ACCESSORY") & {"CHEMICALS_CLEANING"})
falsy("a paint roller is not paint",
      risks("8-Piece Refillable Paint Roller Set with Edger, Corner Brush",
            "PAINT_BRUSH") & {"CHEMICALS_CLEANING"})
falsy("a 24V cigarette-lighter fan is not a mains product",
      risks("24V Dual Head Car Fan 360 Rotatable 2-Speed Cigarette Lighter",
            "AUTO_PART") & {"MAINS_ELECTRICAL"})
# But the substance in the applicator IS the substance, and Amazon's type says so
# even though the title reads "Grease Gun Cartridges".
truthy("the CARTRIDGES of grease are the grease",
       "CHEMICALS_CLEANING" in risks(
           "3oz Grease Gun Cartridges 85g General Purpose Twin Pack",
           "MACHINE_LUBRICANT"))


print("\n=== the veto still beats the new trigger ===")
# not_product_types was the whole reason a garden recliner stopped demanding a
# Cosmetic Product Safety Report. A positive trigger must never undo that.
import listing.sourcing_viability as SV
_vetoed = [(r["id"], t) for r in SV._RULE_LIST for t in r.get("not_types", ())]
truthy("there are vetoes to respect", len(_vetoed) > 0)
for rid, t in _vetoed[:6]:
    got = risks("a product whose words could suggest anything", t)
    check("  %s cannot fire on a %s" % (rid, t), rid in got, False)
# And a rule may not list the same type both ways -- that is a contradiction
# nobody would spot on screen.
for r in SV._RULE_LIST:
    both = set(r.get("types", ())) & set(r.get("not_types", ()))
    check("  %s does not both require and forbid a type" % r["id"], sorted(both), [])


print("\n=== the rulebook still loads and says what it now means ===")
with open("sourcing_viability_rules.json", encoding="utf-8") as fh:
    RB = json.load(fh)
classes = {c["id"]: c for c in RB["risk_classes"]}
check("every risk class survived the edit", len(classes), 15)
# The label named one chemistry while the rule covered several. A warning whose
# title contradicts its own trigger reads as a mistake and gets dismissed.
check("the battery class is no longer labelled lithium-only",
      classes["BATTERY_POWERED"]["label"], "Product containing batteries")
truthy("  though lithium still fires it",
       "lithium" in classes["BATTERY_POWERED"]["triggers"]["strong"])
truthy("  and so do the other chemistries",
       "alkaline battery" in classes["BATTERY_POWERED"]["triggers"]["strong"])
# Lubricants are chemical mixtures with an SDS, and the class stopped at
# cleaners. jack_uk sells twenty of them.
truthy("lubricants come under the chemicals rule",
       "lubricant" in classes["CHEMICALS_CLEANING"]["triggers"]["strong"])
truthy("  with the tools that apply them excluded",
       "grease gun" in classes["CHEMICALS_CLEANING"]["exclude"])

print("\n=== a type nobody listed changes nothing ===")
# The default must stay "judge it on the words", or every unlisted product type
# becomes a silent behaviour change.
before = risks("Stainless Steel Kitchen Colander 24cm")
after = risks("Stainless Steel Kitchen Colander 24cm", "SOME_TYPE_NOBODY_LISTED")
check("an unlisted type is neither a trigger nor a veto", sorted(after), sorted(before))

print("\n=== and the reason names the type, not a word that is not there ===")
# A title with NO battery word in it, so the type is the only thing that can
# fire the rule -- on "Zinc-Carbon Lantern Batteries" the keywords get there
# first and the type is never consulted, which would test nothing.
r = V(title="6V 4R25 996 PJ996 908 430 Spring Terminals", bullets=[],
      product_type="BATTERY", category="", marketplace="UK")
truthy("the type alone is enough to raise it",
       "BATTERY_POWERED" in {x["id"] for x in (r.get("risks") or [])})
sig = [s for x in (r.get("risks") or []) for s in (x.get("signals") or [])]
truthy("  and it says Amazon classified it, rather than naming an absent word",
       any("Amazon lists this as" in s for s in sig))

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
