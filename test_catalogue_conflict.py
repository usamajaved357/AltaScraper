"""Auto-fix spent two rounds on a colour that was never wrong.

    "a color is not something amazon should stuck on"

Right, and it was not really stuck on the colour. The run he pasted:

    -- round 1 --   suggest color = Green   APPLIED color   PREVIEW: error
    -- round 2 --   suggest color = Green   APPLIED color   PREVIEW: error
                    -- identical to the previous round, no progress.

Amazon's answer, code 8541:

    "We found more than one ASIN matching the SKU data provided. The
     '{color.value,color.standardized_values}' conflicts with 1 ASINs in the
     catalogue (Merchant Green / Amazon Blue) for B0HJ3W6M84. The
     'standard_product_id' conflicts ... for B0HHXTKT3B."

WHAT WAS MEASURED FIRST, before anything was written:

  * the app sent 4545944574867 -- the row's own barcode, recorded in the
    API Payload JSON. Not the ...332 Amazon quotes back.
  * that barcode is on no other row here, and barcode_clash.others_with
    returns nothing for it. The identifier was never the fault.
  * NOTHING in the app understood code 8541 -- not amazon_errors.js, not
    autofix.js, not the generator, not api_issues.py.

So Amazon names whichever attribute DISAGREES with an ASIN it thinks we are
describing. The field is a symptom of the match, not a wrong value -- and the
only value that satisfies the complaint is Amazon's own, which would attach a
new product to somebody else's ASIN. CLAUDE.md Rule 1.
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
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from listing import api_issues as A

REAL = {"issues": [{
    "severity": "ERROR", "code": "8541",
    "message": ("We found more than one ASIN matching the SKU data provided. The "
                "'{color.value,color.standardized_values}' conflicts with 1 ASINs "
                "in the catalogue (Merchant [en_GB: value \"Green\"] / Amazon "
                "'[en_GB: value \"Blue\"]' for B0HJ3W6M84). The "
                "'standard_product_id' conflicts with 1 ASINs in the catalogue "
                "(Merchant [\"04545161767332\"] / Amazon '[\"04545155187597\"]' "
                "for B0HHXTKT3B)."),
    "attributeNames": ["color", "externally_assigned_product_identifier"]}]}

print("=== a catalogue match is recognised, and by its CODE ===")
cc = A.catalogue_conflict(REAL)
truthy("Amazon's 8541 is recognised", cc)
check("  by the code, not the prose", cc["code"], "8541")
# THE DECISION IS THE CODE. A message that merely reads like one must not
# trigger it, or a wording change at Amazon silently turns the guard off or on.
falsy("the same words with another code are NOT one",
      A.catalogue_conflict({"issues": [{"severity": "ERROR", "code": "4000001",
                                        "message": REAL["issues"][0]["message"],
                                        "attributeNames": ["color"]}]}))
falsy("an ordinary rejection is not one",
      A.catalogue_conflict({"issues": [{"severity": "ERROR", "code": "90220",
                                        "message": "size is required but missing",
                                        "attributeNames": ["size"]}]}))
falsy("no issues at all", A.catalogue_conflict({"issues": []}))
falsy("  and a blank record does not raise", A.catalogue_conflict(""))

print("\n=== it names the products, for the sentence only ===")
check("both ASINs are pulled out", cc["asins"], ["B0HJ3W6M84", "B0HHXTKT3B"])
check("  and the fields Amazon blamed", cc["fields"],
      ["color", "externally_assigned_product_identifier"])

print("\n=== the sentence says what to do, and what not to ===")
note = A.catalogue_conflict_note(cc)
truthy("it says the value is not the fault", "not a value being wrong" in note)
truthy("  names the products", "B0HJ3W6M84" in note)
truthy("  and the fields", "color" in note)
# THE THING IT MUST NEVER SUGGEST. Adopting Amazon's value is the piggyback
# listing Rule 1 exists to prevent, and it is the one step Amazon's own message
# offers first.
truthy("it refuses to adopt Amazon's value", "somebody else's ASIN" in note)
truthy("  and gives the two real ways out",
       "different product" in note and "Selling Partner Support" in note)
check("no conflict -> no sentence", A.catalogue_conflict_note(None), "")

print("\n=== auto-fix stops on the FIRST round, not the second ===")
D = open("dashboard.py", encoding="utf-8").read()
truthy("the loop asks the module", "_api_issues.catalogue_conflict(" in D)
truthy("  and shows its sentence", "_api_issues.catalogue_conflict_note(" in D)
# Before the "identical to the previous round" test, or it spends a round
# re-applying a value that was already right -- which is what he watched.
_err = D.split('if verdict == "error":')[1].split("entry[\"diagnosis\"] = f\"Unclear")[0]
truthy("  before the identical-round check",
       _err.index("catalogue_conflict(") < _err.index("prev_errors == key"))
truthy("  and it breaks out rather than continuing",
       "matched this to an existing ASIN" in _err)

print("\n=== and the drawer explains it instead of quoting Amazon ===")
AE = open(os.path.join("static", "js", "amazon_errors.js"), encoding="utf-8").read()
truthy("there is a pattern for it", "catalogue_match_conflict" in AE)
truthy("  matching Amazon's own wording", "more than one asin matching" in AE.lower())
truthy("  and it tells him NOT to take Amazon's values",
       "Do NOT change your values to Amazon" in AE)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
