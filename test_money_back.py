"""Money Amazon owes back, checked against Amazon's own published rule.

    "i want each and every feature and page about the inventory and ppc, of
     orbit into my app, please built them"

Orbit has a Reimbursements page. Most of what such a page usually lists is FBA
-- units lost or damaged in a warehouse -- and there are ZERO FBA units across
all six accounts here. Listing those categories would be theatre.

What happens on every account is a refund, and a refund has arithmetic Amazon
publishes:

    on a refund Amazon returns the referral fee it took, minus an administration
    fee of the lesser of 5.00 or 20% of that referral fee

`order_fees` already stores what Amazon ACTUALLY took and ACTUALLY gave back,
per order, from the Finances API. So this is checkable rather than estimated.

WHAT THIS FILE LEANS ON

The false-positive direction, hard. A page that invents claims is worse than no
page: the first one you chase and lose teaches you to ignore it. So the real
rows from the live database -- where Amazon behaved correctly -- must produce
NOTHING, and the arithmetic must be exact rather than approximately right.

It also pins that this thing FILES NOTHING. Finding money is one action;
raising a case with Amazon is another, and it is a person's to take.
"""
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import money_back as _mb        # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def order(**kw):
    d = {"order_id": "203-0000000-0000000", "posted_date": "2026-08-14",
         "currency": "GBP", "workspace_id": "selvora_limited",
         "marketplace": "UK", "principal": 0, "referral_fees": 0,
         "refunds": 0, "refund_fees_returned": 0}
    d.update(kw)
    return d


print("\n== Amazon's rule, stated ==")
check("it may keep 20% of a small fee", _mb.keep_allowed(5.84), 5.84 * 0.20)
check("  but never more than the flat cap", _mb.keep_allowed(100.00),
      _mb.ADMIN_FEE_CAP)
check("  and nothing at all of nothing", _mb.keep_allowed(0), 0.0)

print("\n== the real orders from the live database ==")
# Read off order_fees on 18 Aug 2026. Amazon kept LESS than its cap on every
# one, so the honest answer is nothing owed -- and that is the answer that
# matters most, because it is the one the page will give almost always.
REAL = [(36.20, 7.00, 36.20, 6.55),
        (32.54, 6.21, 32.54, 5.90),
        (32.49, 5.84, 32.49, 4.80),
        (32.49, 5.85, 32.49, 4.81),
        (29.16, 4.99, 29.16, 4.09)]
for principal, referral, refund, back in REAL:
    check("a %.2f sale refunded, %.2f fee, %.2f returned -> no claim"
          % (principal, referral, back),
          _mb.check_order(order(principal=principal, referral_fees=referral,
                                refunds=refund, refund_fees_returned=back)),
          None)

print("\n== the boundary, exactly ==")
# Kept precisely the cap: allowed, nothing owed.
check("keeping exactly the cap is not a claim",
      _mb.check_order(order(principal=32.49, referral_fees=5.84, refunds=32.49,
                            refund_fees_returned=5.84 - (5.84 * 0.20))), None)
# A penny over the cap is still under the noise floor, and chasing pennies is
# how a real one gets buried.
check("a penny over the cap is rounding, not a claim",
      _mb.check_order(order(principal=32.49, referral_fees=5.84, refunds=32.49,
                            refund_fees_returned=5.84 - (5.84 * 0.20) - 0.01)),
      None)

print("\n== a real over-charge is caught, with the sum shown ==")
c = _mb.check_order(order(principal=32.49, referral_fees=5.84, refunds=32.49,
                          refund_fees_returned=0.0))
truthy("Amazon returning nothing at all is a claim", c)
check("  owed is the fee minus what it may keep", c["owed"],
      round(5.84 - 5.84 * 0.20, 2))
check("  and every figure behind it is on the row", sorted(
      k for k in c if k in ("principal", "refunded", "referral_fee",
                            "fee_on_refunded_part", "returned", "kept",
                            "allowed_to_keep", "owed")),
      ["allowed_to_keep", "fee_on_refunded_part", "kept", "owed", "principal",
       "referral_fee", "refunded", "returned"])
truthy("  with a sentence that could be typed into a case", "20%" in c["why"])

print("\n== a partial refund only claims its share ==")
c = _mb.check_order(order(principal=32.00, referral_fees=6.00, refunds=16.00,
                          refund_fees_returned=0.0))
check("half the sale came back, so half the fee is in scope",
      c["fee_on_refunded_part"], 3.00)
check("  owed is that share minus 20% of it", c["owed"], round(3.00 * 0.80, 2))
check("  and the share is stated", c["share_pct"], 50.0)
# A refund larger than the principal is tax and postage coming back too. It does
# not increase the referral fee that was charged.
c = _mb.check_order(order(principal=30.00, referral_fees=5.00, refunds=36.00,
                          refund_fees_returned=0.0))
check("a refund bigger than the sale is still capped at the whole fee",
      c["fee_on_refunded_part"], 5.00)
check("  and the share never exceeds 100%", c["share_pct"], 100.0)

print("\n== unknown is never a claim ==")
check("no refund, nothing to check",
      _mb.check_order(order(principal=30, referral_fees=5, refunds=0)), None)
check("no referral fee was taken, so none can be owed",
      _mb.check_order(order(principal=30, referral_fees=0, refunds=30)), None)
check("no principal, so the share of the sale cannot be worked out",
      _mb.check_order(order(principal=0, referral_fees=5, refunds=30)), None)
check("an empty row does not raise", _mb.check_order({}), None)
check("  nor does a None-filled one",
      _mb.check_order({"refunds": None, "principal": None,
                       "referral_fees": None}), None)
check("  nor text where a number should be",
      _mb.check_order(order(principal="x", referral_fees="y", refunds="z")), None)

print("\n== a zero has a denominator ==")
# "Nothing owed" means one thing when 200 refunds were examined and something
# entirely different when none were. The page cannot say the first while meaning
# the second.
SRC = open(r"D:\AltaScraper\domain\money_back.py", encoding="utf-8-sig").read()
for field in ("orders_checked", "refunds_checked"):
    truthy("find() reports %s alongside the answer" % field, field in SRC)
JS = open(r"D:\AltaScraper\static\js\stock.js", encoding="utf-8-sig").read()
truthy("and the page prints it", re.search(r"refunds_checked[\s\S]{0,200}orders_checked", JS))
truthy("  saying so plainly when no refund has settled yet",
       "No refunds have settled yet" in JS)

print("\n== it finds; it does not file ==")
BODY = "\n".join(re.sub(r"#.*$", "", ln) for ln in SRC.split("\n"))
BODY = re.sub(r'"""[\s\S]*?"""', "", BODY)
for banned in ("requests.", "http", "post(", "submit", "claim("):
    check("money_back.py never reaches out to anything (%r)" % banned,
          banned in BODY, False)
truthy("the page says it files nothing", "never files a claim" in JS)
ROUTES = open(r"D:\AltaScraper\routes\inventory_routes.py",
              encoding="utf-8-sig").read()
truthy("the route is read-only", "/inventory/money-back" in ROUTES)
check("  with no POST", bool(re.search(
      r'"/inventory/money-back"[^)]*methods', ROUTES)), False)

print("\n== it is reachable as one of the inventory pages ==")
truthy("there is a tab for it", re.search(r'k: "money"', JS))
truthy("  the other Orbit tabs are there too",
       all(('k: "%s"' % k) in JS for k in ("overview", "actions", "forecast")))
truthy("  and choosing one is remembered across a redraw",
       re.search(r"STOCK\.tab = k", JS))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
