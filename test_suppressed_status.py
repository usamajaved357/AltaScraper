"""A suppression is read from Amazon's structured field, and it does not go stale.

    "when I fix those main images by replacing them with the one that were
     following the policies ... the suppression was removed by Amazon when I
     opened the Seller Central ... but when I come to app the app still says
     that they are suppressed in the all listing page"

THREE FAULTS BEHIND ONE SYMPTOM, and this pins all three.

  1. the fast catalogue call never asked Amazon for `issues`, so it could only
     ever say Active/Inactive -- the suppression word had to come from somewhere
     else
  2. that somewhere else was a per-SKU pass whose answer was stored beside the
     product IMAGE and reused for 24 hours, under a constant whose own comment
     reads "product images rarely change"
  3. and it decided by searching Amazon's PROSE for the word "suppress", which
     Amazon also uses in sentences that mean the opposite

Every payload below is real, captured from nestwell_goods/UK on 19 Sep 2026.
"""
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import listing_status as S          # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(p):
    with open(r"D:\AltaScraper\%s" % p, encoding="utf-8-sig") as f:
        return f.read()


# ---- the real issues, verbatim ---------------------------------------------

# 6.65_2Days_B0D2RLWFBF carries BOTH of these at once. The first is the
# enforcement; the second contains the word "suppression" inside a sentence
# saying there is none.
ENFORCED = {
    "code": "18027", "severity": "ERROR",
    "message": ("We believe the main image has text, logo, graphic or watermark "
                "which is not permitted for this product type. Please submit a "
                "compliant image to lift the suppression."),
    "categories": ["INVALID_IMAGE", "PRODUCT"],
    "enforcements": {"actions": [{"action": "SEARCH_SUPPRESSED"}],
                     "exemption": {"status": "NOT_EXEMPT"}},
}
NOT_ENFORCED = {
    "code": "100581", "severity": "WARNING",
    "message": ("The MAIN image you submitted for US/Global has text, logo, "
                "graphic and watermark, which is not permitted for this product "
                "type in GB store. As a result, your image(s) will not be "
                "considered for display to customers, but this will not lead to "
                "ASIN suppression. No action is required at this time."),
}
MISSING_ATTR = {
    "code": "18448", "severity": "WARNING",
    "message": ("Your submission is missing few key attributes: "
                "maximum_weight_recommendation."),
    "attributeNames": ["maximum_weight_recommendation"],
    "categories": ["MISSING_ATTRIBUTE", "PRODUCT"],
}
BUYABLE = [{"status": ["BUYABLE", "DISCOVERABLE"]}]


def prose_test(issues):
    """The test that was there, kept so the difference can be measured."""
    return any("suppress" in str(i.get("message", "")).lower() for i in issues)


print("\n== the fact comes from the structured field, never the prose ==")
check("an enforcement Amazon actually applied", S.suppressed([ENFORCED]), True)
check("a message that says there is NO suppression is not one",
      S.suppressed([NOT_ENFORCED]), False)
# THE WHOLE POINT, in one line: on that message the two tests disagree, and the
# old one is the one that is wrong.
check("  ...and that is exactly where the old prose test failed",
      prose_test([NOT_ENFORCED]), True)
check("an ordinary missing-attribute warning is not one",
      S.suppressed([MISSING_ATTR]), False)
check("no issues at all is not one", S.suppressed([]), False)
check("  nor is None", S.suppressed(None), False)
check("a malformed issue does not raise", S.suppressed([None, "x", {}]), False)
check("an enforcement action we do not know is not assumed to suppress",
      S.suppressed([{"enforcements": {"actions": [{"action": "LISTING_REMOVED"}]}}]),
      False)

print("\n== suppressed outranks BUYABLE, which is why it was missed ==")
# MEASURED: four of the five suppressed nestwell_goods listings still report
# BUYABLE. `"Active" if "BUYABLE" in statuses` called every one of them Active.
check("a suppressed listing still reports BUYABLE, and is still suppressed",
      S.of(BUYABLE, [ENFORCED, NOT_ENFORCED]), S.SUPPRESSED)
check("  the fifth reports no status at all and is still suppressed",
      S.of([{"status": []}], [ENFORCED]), S.SUPPRESSED)
check("a buyable listing with only warnings is Active",
      S.of(BUYABLE, [MISSING_ATTR]), S.ACTIVE)
check("  and one whose only mention of suppression denies it is Active too",
      S.of(BUYABLE, [NOT_ENFORCED]), S.ACTIVE)
check("not buyable, but an ERROR to fix -> Incomplete",
      S.of([{"status": ["DISCOVERABLE"]}], [{"severity": "ERROR", "message": "x"}]),
      S.INCOMPLETE)
check("not buyable and nothing to fix -> Inactive",
      S.of([{"status": ["DISCOVERABLE"]}], []), S.INACTIVE)
check("no summaries at all -> Inactive, not a crash", S.of([], []), S.INACTIVE)
check("a caller that did not ask for issues gets what it always got",
      S.of(BUYABLE, None), S.ACTIVE)

print("\n== one function decides it, for both paths (Rule 12) ==")
AL = read("api/amazon_listings.py")
LR = read("routes/live_routes.py")
yes("the catalogue call asks Amazon for issues", '"issues"]' in AL)
yes("  and the row's status comes from the shared function",
    "_status.of(item.get(\"summaries\")" in AL)
check("  it no longer decides Active/Inactive on its own",
      '"Active" if "BUYABLE" in statuses else "Inactive"' in AL, False)
yes("the per-SKU pass asks the same function", "_lstatus.of(summaries, issues)" in LR)
check("  and no longer greps Amazon's prose",
      'in str(iss.get("message", "")).lower()' in LR, False)
check("nothing anywhere still reads a suppression out of a message",
      bool(re.search(r'"suppress" in str\(', AL + LR)), False)

print("\n== the status has its own clock, the picture keeps its day ==")
yes("a status age exists and is not the image's", "_STATUS_MAX_AGE" in LR)
yes("  it is far shorter than the 24h image cache",
    re.search(r"_STATUS_MAX_AGE\s*=\s*15 \* 60", LR))
yes("  a stale status sends the SKU back to Amazon", "_status_stale(c, _age)" in LR)
# THE COST GUARD. Re-asking every Active listing every 15 minutes would be one
# rate-limited request per SKU per quarter hour, for ever, to be told nothing.
_fn = LR[LR.index("def _status_stale"):]
_fn = _fn[:_fn.index("\n        for sku in skus")]
yes("  but only for a listing that is NOT already Active", 'st == "Active"' in _fn)
yes("  and an entry with no status is left alone", "if not st" in _fn)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
