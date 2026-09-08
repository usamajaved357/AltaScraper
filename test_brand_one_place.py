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

THE SWAP WAS REMOVED ON 8 SEP 2026, at the owner's instruction:

    "please do not force the listing to use the brand name from the approved or
     added brand list just allow the types brand name to go to amazon if there
     is a typo or some error amazon will reveal in preview"

    "that altaboltaVoo is not a brand registry brand, that is just a brand name
     amazon allowed me to use so let me use it"

He is right, and Amazon's own enforcement is why it is safe: a brand this
account may not use CANNOT create a listing -- Amazon refuses with code 100550
and returns the Manage Your Brands link. The swap was guarding against a case
Amazon already blocks, and paying for it by sending listings out under a brand
nobody chose.

The app cannot ever know the answer for itself, either. Amazon's documentation
is explicit that SP-API "doesn't provide information about intellectual property
restrictions for new products or details about gated brands" -- there is no
endpoint to read the approved list and none to apply for one. So the account's
Brands list is the owner's own note, useful for spotting a stale value and never
authoritative enough to overrule what he typed.

WHAT SURVIVES is the reporting. A brand that is not on the list is still said
out loud, because a leaked value looks exactly like a deliberate one -- and the
global config brand is still never borrowed for a blank row, which is the
separate leak that put one account's brand on another's listings.
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

print("\n== an unlisted brand is SENT AS TYPED, and remarked on ==")
# THE SWAP IS GONE, at the owner's instruction on 8 Sep 2026:
#
#     "please do not force the listing to use the brand name from the approved
#      or added brand list just allow the types brand name to go to amazon if
#      there is a typo or some error amazon will reveal in preview"
#
# The argument is Amazon's own enforcement. A brand this account does not own
# CANNOT create a listing -- Amazon refuses with code 100550 and hands back the
# Manage Your Brands link. So the case the swap guarded against is one Amazon
# already blocks, at the only place that knows which brands are approved, while
# the swap itself sent listings out under a brand nobody chose (his first report,
# quoted at the top of this file).
#
# The app cannot close that gap either: Amazon's docs say SP-API "doesn't
# provide information about intellectual property restrictions for new products
# or details about gated brands". There is no list to read and none to apply to.
got, note = R("AltaboltaVoo", ONE)
check("what was typed is what is sent", got, "AltaboltaVoo")
truthy("  and it is still remarked on", note)
truthy("  naming what was typed", "AltaboltaVoo" in note)
truthy("  and what the account lists", "Nestwell Goods" in note)
# The note is now about a value being SENT, not one being CHANGED.
truthy("  saying it goes as typed", "as typed" in note)
truthy("  and that Amazon is the authority", "100550" in note)
falsy("  it no longer claims to have substituted anything",
      "instead" in note.lower())

print("\n== an account with no brands listed still sends what was typed ==")
# An empty list is far more likely to mean "not filled in" than "owns no
# brands", and this used to BLOCK the submit outright.
got, note = R("AltaboltaVoo", NONE_SET)
check("the typed brand is sent", got, "AltaboltaVoo")
truthy("  and it says nothing here could confirm it",
       "no brands listed" in note)
check("a row with no brand at all still sends none",
      R("", NONE_SET), ("", ""))
# The global config brand is NEVER borrowed once an account is resolved -- that
# leak is how one account's brand reached another's listings, and it is a
# DIFFERENT thing from sending what the owner typed.
check("the global brand is not borrowed for a blank row",
      R("", {"_account_brands": [], "_account_brand": "",
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
