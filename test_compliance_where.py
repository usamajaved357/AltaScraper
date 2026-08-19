"""A keyword means different things depending on where it is written.

The compliance check reads the title, the bullets and the search terms as one
blob, and any strong keyword anywhere in it assigned the whole category. But the
title is where a product says what it IS -- Amazon requires that of a title --
while the bullets and search terms are where it says what it is used WITH, what
it is safe NEAR, what it STORES, and every adjacent thing somebody might search
for.

Measured on nestwell_goods, the difference produced these:

    Stand Up Weed Puller     -> food_consumables  "safe near ... edible plants"
    Wireless Earbuds         -> sports_fitness    search terms "gym sport commute"
    Gel Seat Cushion         -> toys_children     "car seat pad"
    Folding Bar Stool        -> toys_children     "folding high chair"
    Foldable Storage Boxes   -> toys_children     "stores ... toys, books"

A weed puller carrying an allergen declaration is not a cautious flag. It is
noise, and noise is what makes a compliance column ignorable.

THE RULE: title evidence assigns the category; body-only evidence is a note and
does not raise the risk. NOTHING IS DISCARDED -- the tests below check that a
lithium battery mentioned in a bullet is still reported, because a fix that
quietly deletes a safety finding is worse than the false flag it replaced.
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


import json

from amazon_listing_generator import check_compliance

RULES = json.load(open("compliance_rules.json", encoding="utf-8"))


def scan(title, **body):
    listing = {"title": title}
    listing.update(body)
    return check_compliance(title, listing, RULES)


print("== the five real ones, from nestwell_goods ==")

r = scan("Stand Up Weed Puller Root Remover Tool Long Handle 3 Claw",
         bullet_1="A safe choice for areas where children, pets, or edible "
                  "plants are present, and avoids any runoff.")
falsy("a weed puller is not a food business",
      "food_consumables" in r["matched_categories"])
truthy("  but the word is still reported",
       "food_consumables" in r["mentioned_categories"])
truthy("  and the note names the word that fired", '"edible"' in r["summary"])
truthy("  and says why it may not apply", "used with" in r["summary"])

r = scan("Wireless Earbuds Bluetooth 5.3 Hi-Fi Stereo ENC Noise Cancelling",
         search_terms="earphones gym sport commute")
falsy("earbuds are not sports equipment",
      "sports_fitness" in r["matched_categories"])

r = scan("Large Gel Seat Cushion Honeycomb Non-Slip Cover 40x35cm Blue",
         bullet_1="Honeycomb breathable cushion car seat pad pressure relief")
falsy("a cushion FOR a car seat is not a child car seat",
      "toys_children" in r["matched_categories"])

r = scan("Folding Bar Stool Padded Seat Backrest Steel Frame 88cm Cream",
         bullet_1="Bar chair home office stool adult folding high chair")
falsy("a tall stool is not an infant high chair",
      "toys_children" in r["matched_categories"])

r = scan("2 Pack 66L Foldable Storage Boxes Lids Steel Frame Clear Window",
         bullet_1="For clothes, bedding, duvets, blankets, towels, toys, "
                  "books and general household items.")
falsy("a box that HOLDS toys is not a toy",
      "toys_children" in r["matched_categories"])

print("\n== a title match still assigns the category, exactly as before ==")
r = scan("Children's Wooden Puzzle Toy Set Educational Blocks Age 3+")
truthy("a toy in the title is a toy",
       "toys_children" in r["matched_categories"])
truthy("  and the risk is raised", r["highest_risk"] == "HIGH")
truthy("  and the summary heads with the category, not a note",
       r["summary"].startswith("COMPLIANCE ["))

r = scan("Upper Arm Blood Pressure Monitor Large LCD Display WHO Indicator")
truthy("a blood pressure monitor is a medical device",
       "medical_devices" in r["matched_categories"])

print("\n== nothing is discarded: a safety word in a bullet still surfaces ==")
r = scan("EMS Foot Massager Mat 8 Modes 19 Levels USB Rechargeable Folding",
         bullet_1="Powered by a built-in lithium-ion cell, charges over USB.")
falsy("it does not hold the row", r["highest_risk"] == "HIGH")
truthy("  but the lithium finding is still reported",
       "lithium_batteries" in r["mentioned_categories"])
truthy("  in words, in the summary", "lithium" in r["summary"].lower())
truthy("  and the note tells the reader to check",
       "Check if it applies" in r["summary"])

print("\n== a note is a note, and cannot become a hold ==")
# decide_status() reads highest_risk only, so this is the guarantee that a
# body-only match can never block a row.
r = scan("Plain Steel Shelf Bracket 200mm Pair",
         bullet_1="Not suitable for toys, medicine, food or supplements.")
check("a disclaimer listing four categories raises no risk",
      r["highest_risk"], "BASELINE")
truthy("  and the one real keyword is still named",
       "toys_children" in r["mentioned_categories"])
# The two guards compose, and the ORDER matters: the older weak-keyword rule
# runs first, so "food" -- which is weak, and had no strong food word beside it
# -- never reaches the new title/body split at all. It is dropped, not demoted
# to a note. Only "toys", which is strong, gets that far. Asserting this is what
# stops the new rule from being read as a replacement for the old one.
falsy("  while a WEAK keyword is dropped outright, not demoted to a note",
      "food_consumables" in r["mentioned_categories"])

print("\n== the note is recognised as ours, so a rescan replaces it ==")
# Without this the Notes cell grows a fresh copy of the note on every rescan.
from listing import flags as F

truthy("split_notes owns the note segment",
       F.owned_note('COMPLIANCE NOTE (no hold): the copy mentions x ("y")'))
truthy("  and still owns the ordinary summary",
       F.owned_note("COMPLIANCE [HIGH]: electrical"))
falsy("  and does not claim somebody else's note",
      F.owned_note("REVIEW: unverified spec (not in captured source)"))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
