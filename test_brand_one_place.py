"""Whose brand goes on the listing, decided once and never in silence.

    "I am trying to put the brand name as AltaboltaVoo while creating a new
     listing on Nestwell Goods account, my nestwell goods account has that
     brand name approved in the seller central ... but the app says
     'Amazon flagged this - review the value'"

    "why do i have 2 places in the listing tab to put a brand name, i thought
     it should be 1"

Both reports are the same fault seen from two sides.

MEASURED: nestwell_goods was configured with brands ['Nestwell Goods'].
Typing AltaboltaVoo into the Brand column was REPLACED with 'Nestwell Goods'
without a word, so the listing went out under a brand nobody chose -- and the
only clue was a generic "Amazon flagged this" on a field the editor would not
let you fix anyway.

THE GUARD ITSELF IS RIGHT AND STAYS. A listing must go out under THIS account's
own trademark; one account's brand on another's listing is the worse fault, and
it has happened here before (a competitor's eBay data once supplied brand='YL').
What was wrong was the silence: the app cannot know which brands Amazon approved
for an account, only the owner can, and the account's Brands list is where they
say so.
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


from amazon_listing_generator import resolve_account_brand as R

ONE = {"_account_brands": ["Nestwell Goods"], "_account_brand": "Nestwell Goods"}
TWO = {"_account_brands": ["AltaboltaVoo", "Jack Reacherd"],
       "_account_brand": "AltaboltaVoo"}
NONE_SET = {"_account_brands": [], "_account_brand": ""}
NO_ACCOUNT = {"brand_name": "Legacy Global"}

print("== a registered brand is used as typed ==")
check("the account's own brand", R("Nestwell Goods", ONE), ("Nestwell Goods", ""))
check("  and the second of several", R("Jack Reacherd", TWO), ("Jack Reacherd", ""))
check("  with nothing to report", R("AltaboltaVoo", TWO)[1], "")

print("\n== an unregistered brand is swapped -- and SAID ==")
got, note = R("AltaboltaVoo", ONE)
check("the account's first brand is sent", got, "Nestwell Goods")
truthy("  and the swap is announced", note)
truthy("  naming what was typed", "AltaboltaVoo" in note)
truthy("  and what was sent instead", "Nestwell Goods" in note)
# The note must say what to DO. "Brand was changed" is not actionable.
truthy("  and exactly what to do about it", "Brands list" in note)
truthy("  including the case where the owner is right",
       "really is" in note and "Seller Central" in note)

print("\n== an account with no brand sends none, rather than borrowing ==")
got, note = R("AltaboltaVoo", NONE_SET)
check("nothing is sent", got, "")
truthy("  and it says why", "no registered brand" in note)
# The global config brand is NEVER used once an account is resolved -- that
# leak is how one account's brand reached another's listings.
check("the global brand is not borrowed",
      R("x", {"_account_brands": [], "_account_brand": "",
              "brand_name": "Someone Else"})[0], "")

print("\n== with no account at all, the legacy fallback still works ==")
check("the row wins", R("Typed", NO_ACCOUNT), ("Typed", ""))
check("  and the config default fills a blank", R("", NO_ACCOUNT),
      ("Legacy Global", ""))

print("\n== an empty brand on a registered account is not 'wrong' ==")
# Blank means "not filled in", not "a brand that failed the check". It must not
# produce a swap note about a value nobody typed.
got, note = R("", ONE)
check("the account brand is used", got, "Nestwell Goods")
check("  with no complaint", note, "")

print("\n== one copy of the rule, used by both callers ==")
src = open(os.path.join(HERE, "amazon_listing_generator.py"),
           encoding="utf-8").read()
check("the helper is defined once",
      src.count("def resolve_account_brand("), 1)
check("  and called from the builder and the submit guard",
      src.count("resolve_account_brand("), 3)   # 1 def + 2 calls
truthy("  with the reason recorded", "ONE COPY, used by build_api_attributes" in src)
# The old inline copies must be gone, or they will drift.
falsy("no inline copy is left behind",
      "if _rb not in _acct_brands:" in src)

print("\n== and the editor stops offering a second brand box ==")
JS = open(os.path.join(HERE, "static", "js", "autofix.js"), encoding="utf-8").read()
truthy("brand-ish attributes are recognised", "const BRAND_KEYS=" in JS)
truthy("  and rendered as an explanation, not an input",
       "BRAND_KEYS.indexOf(String(k).toLowerCase()) >= 0" in JS)
truthy("  saying where the brand really comes from",
       "not typed here" in JS)
truthy("  and where to add one", "Manage accounts" in JS)
truthy("  with the report quoted beside it",
       "why do i have 2 places in the listing tab" in JS)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
