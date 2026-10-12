"""Every profit says which one it is; every ad spend says it is before VAT.

    OWNER, 12 Oct 2026: "The repricer shows me another number for the profits,
    the Sales tab shows me another number, and the PPC page shows me another
    number." Asked, he chose one calculation with three labelled levels:
    order profit (before ads) / profit after ads / net profit.

And the ad screens labelled Campaign Manager's ex-VAT spend "What Amazon
charged" -- on an account that cannot reclaim VAT, Amazon charged 1.2x that.
Source-text checks: the labels are the behaviour here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def js(name):
    return open(os.path.join(HERE, "static", "js", name), encoding="utf-8").read()


print("== the three levels ==")
check("All Orders: Order profit, before ads", '"Order profit"' in js("orders.js"), True)
check("Sales card: Net profit", 'label: "Net profit"' in js("sales_live.js"), True)
check("  with unsettled orders marked", "not settled yet (fee estimated)"
      in js("sales_live.js"), True)
check("Repricer: the next sale, not the past", ">Profit next sale</th>"
      in js("sourcing.js"), True)

print("== ad spend says it is before VAT ==")
check("PPC Analytics card is SPEND (EX VAT) when VAT is a cost",
      '"SPEND (EX VAT)"' in js("ppcanalytics.js"), True)
for f in ("sales_campaigns.js", "ppccampaigns.js", "ppcterms.js"):
    check("%s: before VAT" % f, "before VAT" in js(f), True)
    check("  and no longer 'What Amazon charged' over it",
          "What Amazon charged for" in js(f), False)

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
