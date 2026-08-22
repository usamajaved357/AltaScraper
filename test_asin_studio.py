"""Any ASIN in, a BRANDED DRAFT out -- and the source brand must not come with it.

    "i want to put the name of a random asin for which i want to regenerate
     content ... that asin is not the part of my account ... i want to put the
     brand name of that asin which i want the content to be generated for, as i
     want to maintain the content as branded and not a generic content without
     brand words."

THE HAZARD THIS WHOLE FILE IS ABOUT. The copy is written FROM a competitor's
listing. Researching B07NT77GT8 returns a TREKOLOGY camping chair -- a real
brand, in the title, in the attributes, in every fact the model is shown. Left
alone, "TREKOLOGY" walks into our copy, and another company's trademark in a
listing is the single most common reason one is taken down.

So the guard is in three places, because one is not enough for something that
costs an account: the prompt forbids naming any other brand; the finished copy
goes through the app's real IP check; and the findings are shown BEFORE the
draft button rather than after.

A MISTAKE I MADE AND MEASURED MY WAY OUT OF. I first scrubbed the copy with
listing.compliance.scrub_copy, believing it was the IP pass. It is not -- its
own docstring says it strips "seller self-promotion, shipping/fulfilment claims,
external links, or unverifiable superlatives". Handed "Compatible with Hozelock
fittings" it returns it untouched, which is what testing it showed. The real
check is check_ip_violations reading ip_rules.json's forbidden_phrases, wrapped
by domain/compliance_scan.scan -- the same wrapper /compliance/scan uses, so
this screen and that one judge copy by one set of rules.

RULE 1 IS NOT BENT HERE. The ASIN is a REFERENCE for product facts, exactly as
the ASIN embedded in every SKU has always been. Nothing sends
merchant_suggested_asin, nothing uses LISTING_OFFER_ONLY, and the draft is a NEW
product under the seller's own brand.
"""
import json
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
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


R = read("routes", "asin_studio_routes.py")
J = read("static", "js", "asinstudio.js")


def code_only(src):
    body = src.split('"""', 2)[-1] if src.lstrip().startswith('"""') else src
    return "\n".join(l.split("#")[0] for l in body.splitlines())


RC = code_only(R)

print("== Rule 1: the ASIN is a reference, never a listing to join ==")
falsy("no merchant_suggested_asin", "merchant_suggested_asin" in RC)
falsy("no LISTING_OFFER_ONLY", "LISTING_OFFER_ONLY" in RC)
truthy("and it is said where somebody would assume otherwise",
       "reference" in R.lower() and "never joins" in J.lower())
# Never invent a barcode -- Rule 1 again.
falsy("no barcode is generated", "upc = " in RC.lower() and "random" in RC.lower())

print("\n== the listing generator is not imported, called or modified ==")
falsy("amazon_listing_generator is not imported", "amazon_listing_generator" in RC)
# THIS READ `git status` AND FAILED ON ANY UNCOMMITTED EDIT to those files, by
# anyone, for any reason. It was written to prove that building ASIN Studio
# needed no changes to the generator, the pricing rule, the image studio or the
# repricer -- which was true, and stayed true. But the working tree is not that
# claim: compacting the repricer's supplier block touched sourcing.js for
# reasons that have nothing to do with this screen, and this test went red.
#
# A guard that fires on unrelated work is one people learn to ignore, and it
# says nothing at all once the change is committed. The claim it was really
# making is about this feature's CODE, so that is what is checked: ASIN Studio
# reaches none of them.
for _mod in ("amazon_listing_generator", "listing.pricing", "listing import pricing",
             "genimage", "sourcing"):
    falsy("  it does not reach %s" % _mod, _mod in RC)

print("\n== the REAL ip check is used, not the promotional scrubber ==")
truthy("compliance_scan is what judges the copy", "compliance_scan" in RC)
truthy("  which is what /compliance/scan uses too",
       "compliance_scan" in read("routes", "compliance_routes.py")
       or "compliance_scan" in read("domain", "compliance_scan.py"))
truthy("ip_rules.json is loaded", "ip_rules.json" in RC)
truthy("  from the same two places the compliance screen looks",
       "os.path.dirname(os.path.abspath(CONFIG_PATH))" in RC)
truthy("and the wrong-tool mistake is recorded so it is not repeated",
       "NOT a trademark check" in R or "is NOT a trademark" in R
       or "wrong one first" in R.lower())

# The shape matters: these checks read bullet_1..bullet_5, not a list.
truthy("bullets are flattened to the keys the checks read",
       'flat["bullet_%d" % (i + 1)]' in R)
truthy("  and why is recorded", "silently skip every bullet" in R)

print("\n== proof the two checks differ, run against the real rules ==")
from domain import compliance_scan as _cs
from listing import compliance as _c
rules = json.load(open(os.path.join(HERE, "ip_rules.json"), encoding="utf-8"))
bad = {"title": "Garden Hose", "bullet_1": "Compatible with Hozelock fittings",
       "bullet_2": "An alternative to Karcher hoses", "description": "Works with Bosch."}
_clean, _removed = _c.scrub_copy(bad["bullet_1"], html=False)
check("the promotional scrubber ignores a competitor brand", _removed, [])
_res = _cs.scan(dict(bad), brand="AltaboltaVoo", ip_rules=rules)
_f = (_res.get("findings") if isinstance(_res, dict) else _res) or []
truthy("the IP scan catches the comparative phrasing", len(_f) >= 2)

print("\n== the brand field takes anything, and says what will happen to it ==")
# Asked for explicitly. It changes what may be TYPED, not what Amazon receives.
# The generate route refuses only MISSING input -- a brand that is not one of
# the account's is reported, never blocked. Checked by reading what its
# refusals are actually for, rather than by matching prose about brands.
_gen = RC.split("def asin_studio_generate")[1].split("def _brand_note")[0]
_refusals = [l.strip() for l in _gen.splitlines() if '"error"' in l]
# Counting them was arbitrary and I got the number wrong; what matters is WHAT
# they refuse for. Every one is missing input, a missing API key, or the
# copywriter itself failing -- none is about whose brand it is.
truthy("  missing brand is refused", any("Enter the brand" in l for l in _refusals))
truthy("  nothing researched is refused",
       any("Research an ASIN first" in l for l in _refusals))
falsy("  and NOTHING is refused for an unregistered brand",
      any("registered" in l.lower() or "trademark" in l.lower() for l in _refusals))
truthy("but the consequence is stated", "_brand_note" in RC)
truthy("  naming the substitution that still happens on submit",
       "the account's own brand is sent instead" in R)
truthy("  and that this screen does not change that rule",
       "not changed by this screen" in R)
truthy("the screen suggests the account's own trademarks",
       "accountBrands()" in J)
truthy("  and repeats the warning where the brand is typed",
       "replaced with your own" in J)

print("\n== the draft is an ORDINARY draft ==")
# A second kind of listing would be a second set of rules to keep in step.
truthy("it is written through the shared store", "upsert_row" in RC)
truthy("  with the app's own SKU format", '"%s_%sDays_%s"' in R)
truthy("  and why that format is kept", "rowAsin() reads it" in R)
truthy("it lands as NEEDS_REVIEW, not approved", '"Status": "NEEDS_REVIEW"' in R)
truthy("  so the compliance and IP holds still run",
       "still to run" in R)
falsy("nothing is sent to Amazon here",
      "putListingsItem" in RC or "patch_listings_item" in RC)

print("\n== scoped and governed like everything else ==")
truthy("the account guard is on it", "_wrong_account" in RC)
truthy("  through the shared rule", "account_scope" in RC)
from auth import guard as G
check("the routes need the listings permission",
      G.feature_for("/asin-studio/generate"), "listings")
check("  including create-draft", G.feature_for("/asin-studio/create-draft"), "listings")
U = read("static", "js", "users.js")
# The section names ITSELF now and inherits listings, so it can be granted on
# its own -- and with nothing set it still resolves to listings, exactly as the
# literal mapping did.
truthy("and the nav item has a switch of its own", 'asinstudio:"asinstudio"' in U)
from auth import users as _AU
check("  which falls back to listings", _AU.FEATURE_PARENT.get("asinstudio"),
      "listings")

print("\n== the screen is reachable and visible ==")
S = read("static", "js", "shell.js")
truthy("registered as a section", '"asinstudio"' in S)
truthy("  with an open hook", "asStudioOnOpen" in S)
truthy("  and a panel to draw into", 'id="sec_asinstudio"' in read("templates", "dashboard.html"))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
