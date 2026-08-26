""""Profit left over" is what is left over, not what was asked for.

    "profit left over can not be zero in this case because the source is 24 and
     i am selling it on 24.99 so this is not true whatever the explanation is
     saying"

Right, and worse than it looked from the screen.

The Why? panel is headed "How this price was worked out" and lists the parts of
a sum, ending in the price. The "Profit left over" line was
rule["min_profit"] -- an INPUT, the flat amount you insist on ON TOP of
everything else -- drawn under the label "what you keep per unit", which is an
OUTPUT. At its default of 0.00 the panel told the owner he keeps nothing per
unit, on a price built to earn him 20%.

MEASURED on his own row (cost 24.00, referral 15%, min_roi_pct 20):

    supplier   24.00
    fee         5.08     <- matches his screenshot exactly
    postage     0.00
    ads         0.00
    profit      0.00     <- min_profit, and untrue
    price      33.89

    24.00 + 5.08 + 0.00 + 0.00 + 0.00 = 29.08, against a price of 33.89.
    4.81 missing from a sum laid out to be added up -- and that 4.81 IS the
    profit, exactly 20% of the 24.00 he paid.

The breakdown's own comment already warned about this: "the breakdown says '1.00
profit' while the price is really being set by a 20% target, and the sum on
screen would not add up to the number beside it". `targets` was added so the
screen COULD explain it; this line went on lying anyway.

So the test is arithmetic, not wording: THE PARTS MUST ADD UP TO THE PRICE, and
they must do so whichever floor won -- the flat minimum, the safety floor, a
target, or a held price.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from domain import sourcing as S

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def close(label, got, want, tol=0.02):
    ok = got is not None and abs(float(got) - float(want)) <= tol
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


import datetime as dt

# The same fixture shapes test_sourcing.py uses -- a check carries a status and
# a reading time, and a stale or status-less one is deliberately not actionable.
NOW = dt.datetime(2026, 8, 14, 12, 0, 0)
FRESH = "2026-08-14 11:00:00"


def src(i):
    return {"id": i, "priority": 100, "enabled": 1, "label": "source %d" % i,
            "url": "https://ebay.co.uk/itm/%d" % i}


def chk(price, shipping=0.0, dispatch=3):
    return {"status": S.FETCHED, "price": price, "shipping": shipping,
            "in_stock": True, "dispatch_days": dispatch,
            "checked_at": FRESH, "error": None, "gone_streak": 0}


def parts_add_up(d, label):
    """The listed parts must reconstruct the price the panel names."""
    b = d.get("breakdown") or {}
    if b.get("price") is None:
        FAILS.append(label + " (no breakdown)")
        print("  %-66s FAIL no breakdown" % label)
        return
    total = (float(b["cost"]) + float(b["fee"]) + float(b["postage_label"])
             + float(b["ads"]) + float(b["profit"]))
    close(label, total, float(b["price"]))


print("=== the owner's own row: 24.00 landed, 15% fee, 20% safety floor ===")
d = S.decide({"price": 24.99, "quantity": 1, "lead_days": 3},
             [(src(1), chk(price=24.00))], {}, NOW)
b = d.get("breakdown") or {}
print("     price=%s cost=%s fee=%s profit=%s"
      % (b.get("price"), b.get("cost"), b.get("fee"), b.get("profit")))
close("the fee is the 5.08 that was on his screen", b.get("fee"), 5.08)
# THE HEADLINE FAILURE. It was 0.00.
close("  profit left over is 4.81, not nought", b.get("profit"), 4.81)
close("  which is 20% of the 24.00 paid",
      (float(b["profit"]) / float(b["cost"])) * 100, 20.0, tol=0.2)
parts_add_up(d, "  and the parts add up to the price")
# The input is still available, under its own name, for "you asked for at least".
check("the flat minimum is still carried separately", b.get("min_profit"), 0.0)

print("\n=== it adds up whichever floor decides the price ===")
cases = [
    ("flat minimum only", {"min_roi_pct": 0, "min_profit": 2.00}),
    ("safety floor", {}),
    ("an ROI target", {"target_roi_pct": 35.0}),
    ("a margin target", {"target_margin_pct": 30.0}),
    ("both targets", {"target_roi_pct": 35.0, "target_margin_pct": 30.0}),
    ("a flat profit as well", {"target_roi_pct": 25.0, "min_profit": 1.50}),
    ("postage and ads too",
     {"target_roi_pct": 25.0, "shipping_label": 3.00, "ads_margin": 1.00}),
    ("a held price", {"hold_price": 44.00}),
]
for name, rule in cases:
    dd = S.decide({"price": 24.99, "quantity": 1, "lead_days": 3},
                  [(src(1), chk(price=24.00))], rule, NOW)
    parts_add_up(dd, name)

print("\n=== the profit really is what the target asked for ===")
d2 = S.decide({"price": 10.00, "quantity": 1, "lead_days": 3},
              [(src(1), chk(price=24.00))], {"target_roi_pct": 35.0}, NOW)
b2 = d2.get("breakdown") or {}
close("a 35% ROI target leaves 35% of the cost",
      (float(b2["profit"]) / float(b2["cost"])) * 100, 35.0, tol=0.3)
d3 = S.decide({"price": 10.00, "quantity": 1, "lead_days": 3},
              [(src(1), chk(price=24.00))], {"target_margin_pct": 30.0}, NOW)
b3 = d3.get("breakdown") or {}
close("a 30% margin target leaves 30% of the PRICE",
      (float(b3["profit"]) / float(b3["price"])) * 100, 30.0, tol=0.3)

print("\n=== the screen shows the return beside the profit ===")
JS = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
truthy = lambda l, g: check(l, bool(g), True)
# The labelled price list this asserted is gone -- every line of it is now a
# segment of the stacked bar or one of the four tiles, so the list was the same
# figures a second time in words. What must NOT be lost is that a percentage
# says what it is a percentage OF: "20%" alone is unreadable, and ROI and margin
# are measured against different things. Both tiles say so on hover.
truthy("the ROI tile names what the profit is a return ON",
       "share of the cash you put in" in JS)
truthy("  and margin is named against a different thing",
       "share of what the buyer paid" in JS)
truthy("  worked out from the same two figures above",
       "(b.profit / b.cost) * 100" in JS)
# "you asked for at least X" is only worth saying when X is actually set.
# The flat minimum is a RULE, so it now sits with the other rules as a pill
# showing its value -- or the word "none". Better than the old footnote, which
# appeared only when the minimum happened to be set: a rule you cannot see is a
# rule you cannot check.
truthy("a flat minimum is shown as a rule, set or not",
       "pill('ROI'" in JS and "+ '%' : 'none'" in JS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
