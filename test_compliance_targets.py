"""A product is not the thing it cleans off.

"i still see that a brush is flagged for ... HIGH RISK Chemical or cleaning
 product CHEMICALS_CLEANING ... Detected: names the product: adhesive"

It is a floor scrub brush. Its description says the scraper "tackles dried
residue and ADHESIVE MARKS", and the word "adhesive" is a strong trigger, so the
rule fired on its own and demanded CLP classification, an SDS, REACH
registration and a poison-centre notification for a brush.

There were already two rules for this shape of mistake:

    accessory   "patio heater COVER" is not a heater      -- words BEHIND
    compat      "works on electric hobs" is not a hob     -- words IN FRONT

Missing was the third: the trigger as the thing the product ACTS ON. That is
target_pattern, and unlike compat it is applied to STRONG terms too -- a strong
term fires the rule by itself, so it is exactly the one that needs demoting.

And the product type gets its veto back. The mechanism was already there and
documented ("a chair is not a cosmetic, whatever words are in its description")
and simply had no entries for these rules.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-68s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from listing import restricted as R
from listing import sourcing_viability as SV


print("=== the trigger as a target, not as the product ===")
p = R.target_pattern("adhesive")
truthy("'tackles dried residue and adhesive marks'",
       p.search("the scraper tackles dried residue and adhesive marks"))
truthy("'removes adhesive from floors'", p.search("removes adhesive from floors"))
truthy("'adhesive residue'", p.search("lifts adhesive residue"))
# The other direction MUST still fire: a real adhesive is a real chemical.
check("'strong adhesive formula bonds in 30 seconds' is NOT demoted",
      bool(p.search("strong adhesive formula bonds in 30 seconds")), False)
check("'contains adhesive resin' is NOT demoted",
      bool(p.search("contains adhesive resin")), False)
# Generic, not written for one word.
q = R.target_pattern("rust")
truthy("the same shape works for any trigger word", q.search("protects against rust"))
truthy("  and its noun form", q.search("removes rust stains"))
check("  'rust remover concentrate' is not demoted",
      bool(q.search("rust remover concentrate")), False)


print("\n=== the brush is no longer a chemical ===")
BRUSH = dict(
    title="3-in-1 Floor Scrub Brush Long Handle 120 Rotating Head Squeegee",
    bullets=["The stiff bristles agitate and lift ground-in dirt, the scraper "
             "tackles dried residue and adhesive marks, and the squeegee clears "
             "dirty water efficiently from hard floors."],
    product_type="CLEANING_BRUSH", category="Home & Kitchen")
res = SV.check_sourcing_viability(**BRUSH)
ids = [r["id"] for r in res["risks"]]
check("no chemical risk", "CHEMICALS_CLEANING" in ids, False)
check("  and nothing else fired on it either", ids, [])
check("  so the verdict is viable", res["verdict"], "VIABLE")

print("\n=== a real chemical still fires ===")
res2 = SV.check_sourcing_viability(
    title="Heavy Duty Drain Cleaner 1L Caustic Formula",
    bullets=["Dissolves hair and grease blockages fast."],
    product_type="CLEANING_AGENT", category="Home & Kitchen")
truthy("drain cleaner is still flagged",
       "CHEMICALS_CLEANING" in [r["id"] for r in res2["risks"]])

print("\n=== the product type vetoes a substance rule ===")
# Amazon's own classification is a fact; the prose is an inference.
rules = {r["id"]: r for r in SV._RULE_LIST}
truthy("CHEMICALS_CLEANING knows a brush is not a chemical",
       "CLEANING_BRUSH" in rules["CHEMICALS_CLEANING"]["not_types"])
truthy("  nor a vacuum cleaner",
       "VACUUM_CLEANER" in rules["CHEMICALS_CLEANING"]["not_types"])
truthy("TEXTILES_CLOTHING knows a light fitting is not a textile",
       "LIGHT_FIXTURE" in rules["TEXTILES_CLOTHING"]["not_types"])
truthy("MAINS_ELECTRICAL knows a drill bit carries no mains supply",
       "DRILL_BITS" in rules["MAINS_ELECTRICAL"]["not_types"])
truthy("SKIN_CONTACT_COSMETIC knows machine lubricant is not skincare",
       "MACHINE_LUBRICANT" in rules["SKIN_CONTACT_COSMETIC"]["not_types"])


print("\n=== the demotion patterns are built on demand ===")
# 771 regexes at import cost 3.3s of a startup the app is measured on, and
# almost none are ever consulted -- a demotion pattern is only needed when its
# term actually appeared.
r0 = SV._RULE_LIST[0]
truthy("accessory is lazy", isinstance(r0["accessory"], SV._Lazy))
truthy("compat is lazy", isinstance(r0["compat"], SV._Lazy))
truthy("target is lazy", isinstance(r0["target"], SV._Lazy))
check("a term the rule does not have still returns None",
      r0["target"].get("definitely-not-a-trigger-word"), None)
# It must behave exactly as the dict it replaced.
_t = next(iter(r0["target"]._terms))
truthy("a term it does have compiles and is remembered",
       r0["target"].get(_t) is r0["target"].get(_t))

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
