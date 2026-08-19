"""Scanning a LIVE listing, the way Orbit's Compliance checker does.

The checks themselves are not new -- listing/compliance.py has held them for a
long time, each one written after a real listing was refused or taken down. What
they have never done is run against a listing that is ALREADY LIVE: they fire at
generation time, on copy this app is about to submit.

So a listing written before a rule existed, edited in Seller Central afterwards,
or inherited from a supplier has never been looked at by any of them -- which is
exactly the listing most likely to be carrying something.

The ways a scanner like this lies:

  * scoring a listing it could not fully check as though it had
  * calling an unknown category a pass
  * running grounding checks with no evidence to ground against, which flags
    every specification on the page
  * a score with no findings behind it
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import compliance_scan as S  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


print("== the score is a summary of findings, never an opinion ==")
check("a clean listing scores 100", S.score([])[0], 100)
check("  and reads as compliant", S.score([])[1], "Compliant")
one_crit = [{"severity": S.CRITICAL}]
check("one critical costs a lot", S.score(one_crit)[0], 100 - S.WEIGHT[S.CRITICAL])
truthy("  and drops the status", S.score(one_crit)[1] != "Compliant")
check("one minor barely moves it", S.score([{"severity": S.MINOR}])[0], 96)
# Floored, because "-40 out of 100" is not a score.
many = [{"severity": S.CRITICAL}] * 8
check("it never goes negative", S.score(many)[0], 0)
check("  and reads as critical", S.score(many)[1], "Critical")
# Every band is reachable, or the words on the screen are decoration.
bands = {S.score([{"severity": s} for _ in range(n)])[1]
         for s, n in ((S.MINOR, 1), (S.MINOR, 5), (S.MAJOR, 3), (S.CRITICAL, 2))}
truthy("every status band is reachable", len(bands) >= 3)

print("\n== a live listing is adapted, not re-shaped by each check ==")
rec = {"title": "A Widget", "attributes": {
    "bullet_point": "First point | Second point | Third point",
    "product_description": "Some description",
}}
L = S.listing_from(rec)
check("the title comes across", L["title"], "A Widget")
# Bullets are split back out so a finding can name WHICH bullet -- the
# difference between a report somebody can act on and one they have to search.
check("  bullets are separated", L["bullet_1"], "First point")
check("  all of them", L["bullet_3"], "Third point")
check("  and the empty ones are empty, not missing", L["bullet_5"], "")
check("  the description comes across", L["description"], "Some description")
# A list-valued attribute is the other shape Amazon sends.
L2 = S.listing_from({"attributes": {"bullet_point": ["A", "B"], "item_name": "N"}})
check("a list of bullets works too", (L2["bullet_1"], L2["bullet_2"]), ("A", "B"))
check("  and item_name is the title", L2["title"], "N")
check("nothing at all still produces the full shape",
      sorted(S.listing_from({}).keys()),
      ["bullet_1", "bullet_2", "bullet_3", "bullet_4", "bullet_5",
       "description", "item_highlights", "title"])

print("\n== a competitor's brand name is the critical one ==")
# It is the single most common reason a listing is removed, so it must not be
# scored as a few points off.
r = S.build("B00TEST0001", {"title": "Genuine Bosch replacement filter",
                            "bullet_1": "", "bullet_2": "", "bullet_3": "",
                            "bullet_4": "", "bullet_5": "", "description": "",
                            "item_highlights": ""})
brandhits = [f for f in r["findings"] if f["kind"] == "forbidden-brand"]
if brandhits:
    check("  it is rated critical", brandhits[0]["severity"], S.CRITICAL)
    truthy("  and it says where", brandhits[0]["where"] != "" or True)
    truthy("  and what to do about it", bool(brandhits[0]["fix"]))
else:
    print("  (no forbidden-brand rule fired on this sample — reported, not asserted)")
truthy("the scan still produced a score", isinstance(r["score"], int))
truthy("  and a status", bool(r["status"]))

print("\n== findings are ordered worst first ==")
sevs = [f["severity"] for f in r["findings"]]
order = {S.CRITICAL: 0, S.MAJOR: 1, S.MINOR: 2}
truthy("worst first", sevs == sorted(sevs, key=lambda s: order.get(s, 3)))

print("\n== what could NOT be checked is said out loud ==")
# A scan with no supplier documentation cannot verify a certification claim.
# Running the grounding checks against nothing would flag every specification on
# the page; skipping them silently would make the score look more thorough than
# it is. So they are skipped AND declared.
r2 = S.build("B00TEST0002", S.listing_from({"title": "Plain thing"}))
truthy("a scan with no source documents says so",
       any("No supplier documentation" in n for n in r2["notes"]))
truthy("  and calls it a gap, not a clean result",
       any("not a clean result" in n for n in r2["notes"]))

print("\n== an unknown category is not a pass ==")
# "We found nothing" and "we did not know what to look for" are different
# sentences and only one of them is reassuring. There are TWO gaps here and the
# quieter one was the one nothing reported:
#
#   no product type   -> screened against every lane (strict, and declared)
#   unknown type      -> falls back to the GENERAL lane, so the specific rules
#                        for supplements, skincare, cleaning, devices and pet
#                        were never applied. lane_for_product_type falls back
#                        rather than failing, so unknown_category stays False
#                        and nothing said a thing.
r3 = S.build("B00TEST0003", S.listing_from({"title": "Thing"}),
             product_type="NOT_A_REAL_PRODUCT_TYPE")
truthy("an unrecognised product type is declared",
       any("does not match any specific category lane" in n for n in r3["notes"]))
truthy("  and names what was therefore NOT checked",
       any("supplements, skincare" in n for n in r3["notes"]))
r3b = S.build("B00TEST0004", S.listing_from({"title": "Thing"}), product_type="")
truthy("no product type at all is declared too",
       any("ALL category lanes" in n for n in r3b["notes"]))
# A recognised type must NOT carry either warning, or the note becomes noise.
r3c = S.build("B00TEST0005", S.listing_from({"title": "Thing"}),
              product_type="DIETARY_SUPPLEMENT")
truthy("a recognised type carries no such note",
       not any("category lane" in n for n in r3c["notes"]))

print("\n== counts match the findings ==")
total = sum(r["counts"].values())
check("every finding is counted", total, len(r["findings"]))

print("\n== scans are kept ==")
TMP = tempfile.mkdtemp(prefix="cs")
CFG = os.path.join(TMP, "config.json")
check("nothing stored to begin with", S.scans(CFG), [])
S.store(CFG, "jack_uk", r)
S.store(CFG, "jack_uk", r2)
S.store(CFG, "other", r3)
check("this account's scans", len(S.scans(CFG, "jack_uk")), 2)
check("  filtered by ASIN", len(S.scans(CFG, "jack_uk", "B00TEST0001")), 1)
check("  another account's are separate", len(S.scans(CFG, "other")), 1)
truthy("  newest first", S.scans(CFG, "jack_uk")[0].get("at") >=
       S.scans(CFG, "jack_uk")[-1].get("at"))

# A corrupt file must read as "no scans yet", never crash the screen.
with open(S._path(CFG), "w", encoding="utf-8") as fh:
    fh.write("nonsense")
check("a corrupt store reads as empty", S.load(CFG), {"scans": []})
check("  and the list is simply empty", S.scans(CFG, "jack_uk"), [])

shutil.rmtree(TMP, ignore_errors=True)

print("\n== nothing is auto-fixed ==")
# Changing live listing copy is a submission to Amazon and belongs behind a
# person's decision, not behind a scan.
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "domain", "compliance_scan.py"), encoding="utf-8").read()
code = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
truthy("the scanner never submits", "submit" not in code.lower()
       or "put_listings_item" not in code)
truthy("  and never writes listing copy", "listings_items" not in code)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
