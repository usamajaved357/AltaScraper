"""Amazon's leftover complaints, and what "live" is allowed to mean.

    "i changed the ean before submitting, i am confused here"

He replaced a clashing barcode, previewed clean, submitted, and the app printed
a red banner quoting Amazon complaining about the OLD code. Measured against
Amazon on 7 Sep 2026 for 9.99_2Days_B0BP1HNW8G (nestwell_goods, UK), through
getListingsItem:

    externally_assigned_product_identifier = [{"value": "4545156646383", ...}]
    summaries: asin=B0HJ2W3XZ1 status=['DISCOVERABLE']
    offers: []   fulfillmentAvailability: []
    [ERROR] 100980 attributeNames=['04545844574868',
                                   'externally_assigned_product_identifier']

Three facts in that one reply:

  1. THE NEW BARCODE WAS SENT AND ARRIVED. The app was right; the banner lied.
  2. AMAZON KEEPS A FAILED SUBMISSION'S ERRORS ATTACHED TO THE SKU. A later,
     successful submission does not clear them. Reading the item's CURRENT
     issues and printing them as though they described the submission just made
     is what produced the banner.
  3. DISCOVERABLE IS NOT SELLABLE. The product page existed; no offer was
     attached. The verify branch treated DISCOVERABLE as LIVE, so a row nobody
     could buy from was one status flip away from showing green.
"""
import ast
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
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from listing import api_issues as A

# Amazon's real reply, verbatim from the probe above.
REAL = [
    {"severity": "ERROR", "code": "100980",
     "message": "Your bar code 04545844574868 is already linked to product "
                "B0H8TFYNB9 which seems different to the product you are "
                "trying to list.",
     "attributeNames": ["04545844574868",
                        "externally_assigned_product_identifier"]},
    {"severity": "ERROR", "code": "13013",
     "message": "Your offer to the SKU cannot be added because the product is "
                "not in the catalogue.",
     "attributeNames": None},
]

print("=== a complaint about a barcode the listing no longer carries ===")
check("the replaced code is named as stale",
      A.stale_identifiers(REAL, "4545156646383"), ["04545844574868"])

# THE 14-DIGIT FORM IS THE SAME NUMBER. Amazon quotes barcodes back padded to a
# 14-digit GTIN; the box holds the EAN-13. Comparing the two as strings would
# report "stale" on a barcode that was never changed -- the opposite mistake,
# and a worse one, because it would tell him to go and fix nothing.
check("the same code quoted back in its 14-digit form is NOT stale",
      A.stale_identifiers(REAL, "4545844574868"), [])
check("  nor with spaces or a leading zero typed in",
      A.stale_identifiers(REAL, " 04545844574868 "), [])

# NOTHING TO COMPARE AGAINST IS NOT EVIDENCE. A listing with no usable barcode
# cannot show that Amazon's complaint is out of date.
check("no barcode on the row -> nothing is claimed to be stale",
      A.stale_identifiers(REAL, ""), [])
check("  an unusable one either", A.stale_identifiers(REAL, "123"), [])

# THE VALUE COMES FROM attributeNames, NEVER FROM THE PROSE (CLAUDE.md Rule 4).
# The message text carries the old code too; reading it from there is how the
# "The"/"Your" phantom-field bug happened.
check("a real field name is never mistaken for a barcode",
      A.stale_identifiers(
          [{"severity": "ERROR", "message": "size is required",
            "attributeNames": ["size", "item_name"]}], "4545156646383"), [])
check("  and a message full of digits with no attributeNames says nothing",
      A.stale_identifiers(
          [{"severity": "ERROR", "attributeNames": [],
            "message": "bar code 04545844574868 is already linked"}],
          "4545156646383"), [])
check("no issues at all", A.stale_identifiers([], "4545156646383"), [])
check("  and None does not raise", A.stale_identifiers(None, "4545156646383"), [])

print("\n=== the verify branch says so instead of repeating it ===")
G = open("amazon_listing_generator.py", encoding="utf-8").read()
truthy("it asks the module that owns Amazon's replies (Rule 12)",
       "_api_issues.stale_identifiers(" in G)
truthy("  and puts the correction in the note",
       "left over from an earlier submission" in G)
truthy("    saying explicitly that it is not about the last submit",
       "does \" \n" not in G and "NOT describe what was last sent" in G)

print("\n=== DISCOVERABLE is not LIVE ===")
# BUYABLE means the offer is attached and someone can buy it. DISCOVERABLE means
# Amazon built the catalogue entry. The branch used to accept either.
_verify = G.split("if verify:")[1].split("\n    # ---- ")[0]
truthy("only BUYABLE promotes a row to LIVE", '"BUYABLE" in _st_up' in _verify)
falsy("  DISCOVERABLE no longer promotes it",
      'any(str(s).upper() in ("BUYABLE", "DISCOVERABLE")' in _verify)
truthy("  it gets its own note instead", '"DISCOVERABLE" in _st_up' in _verify)
truthy("    which says nothing can be bought yet",
       "cannot be bought" in _verify)
truthy("    and that the status is left alone, not downgraded",
       "queue(i, status_col," in _verify)
check("  exactly one branch writes LIVE", _verify.count('"LIVE")'), 1)

print("\n=== the sweep stops asking about a listing seconds old ===")
# submit.js reloads the listings ~5s after a submit, and the on-load sweep asked
# Amazon then -- inside its own documented 5-30 minute publication window. The
# answer could only be the previous attempt's errors, and avMarkAsked then
# pinned that answer on screen for ten minutes.
AV = open(os.path.join("static", "js", "autoverify.js"), encoding="utf-8").read()
truthy("the sweep skips what the submit schedule still owns",
       "function avScheduleStillOwns(" in AV)
truthy("  and the filter is actually applied",
       "!avScheduleStillOwns(r.sku)" in AV)
truthy("  bounded by the schedule's own last step, not a new number",
       "AV_WARN_AT" in AV.split("function avScheduleStillOwns(")[1][:400])

print("\n=== the module still parses (it is imported at submit time) ===")
truthy("api_issues has no syntax error",
       isinstance(ast.parse(open(os.path.join("listing", "api_issues.py"),
                                 encoding="utf-8").read()), ast.Module))

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
