"""Hold what I sell at today, on many SKUs at once.

    "why do the repricer wants to reduce my selling price to achieve the target,
     it should not happen"
    "If your supplier drops from 15.34 to 9 i want to stay where it is and take
     the extra margin"

THE BEHAVIOUR ALREADY EXISTED AND ALREADY WORKED. Measured on his own row, a 20%
ROI target with the price held at 21.99:

    supplier 15.34 -> 9.00    target alone would allow 12.71, it holds 21.99
    supplier 15.34 -> 24.00   target needs 33.89, it RISES to 33.89
    supplier 24.00 -> 15.34   it comes back to 21.99, not down to 21.66

What did not exist was any way to SET it without typing a number into each of 67
SKUs one at a time. So the repricer went on cutting prices while the answer sat
there unused. A feature nobody can reach at their own scale is not a feature.

WHY A WRITTEN-DOWN NUMBER AND NOT A "never go down" FLAG -- and this reasoning
is not new, it is in test_hold_price.py: a flag has no memory, so once a cost
spike carries the price to 46 there is nothing to come back TO and every spike
becomes permanent. Today's Amazon price is the one number that means "where I am
now".

I ALSO WARNED THAT HOLDING AN UNDER-WATER LISTING WOULD FREEZE THE LOSS. It does
not, and that is asserted below: a hold is a FLOOR, so a needed rise still
happens. The warning was wrong and the bulk action is safe.
"""
import datetime as dt
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


def truthy(label, got):
    check(label, bool(got), True)


NOW = dt.datetime(2026, 8, 14, 12, 0, 0)
FRESH = "2026-08-14 11:00:00"


def src(i=1):
    return {"id": i, "priority": 100, "enabled": 1, "label": "s", "url": "u"}


def chk(price):
    return {"status": S.FETCHED, "price": price, "shipping": 0.0,
            "in_stock": True, "dispatch_days": 3, "checked_at": FRESH,
            "error": None, "gone_streak": 0}


def decide(sell, cost, rule):
    return S.decide({"price": sell, "quantity": 1, "lead_days": 3},
                    [(src(), chk(cost))], rule, NOW)


print("=== his rule, in his own numbers: 20% ROI, held at what he sells at ===")
# up_and_down explicitly: these check the ARITHMETIC, and up-only --
# the default since 27 Aug 2026 -- would pin the price instead of
# cutting it, which is a different thing and has its own test.
RULE = {"direction": "up_and_down",
        "target_roi_pct": 20.0, "hold_price": 21.99}

# 1. THE COMPLAINT. The target alone would cut 21.99 to 21.66.
check("without a hold, the target cuts the price",
      S.floor_price(15.34, {"target_roi_pct": 20.0}), 21.66)
d = decide(21.99, 15.34, RULE)
check("  with one, it is left alone", d.get("price"), 21.99)
truthy("  and the row says it was held", d.get("held"))

# 2. A CHEAPER SUPPLIER IS EXTRA MARGIN, NOT A LOWER PRICE.
check("the target alone would allow 12.71 on a 9.00 cost",
      S.floor_price(9.00, {"target_roi_pct": 20.0}), 12.71)
d = decide(21.99, 9.00, RULE)
check("  held, it stays at 21.99", d.get("price"), 21.99)

# 3. A DEARER SUPPLIER STILL PUSHES THE PRICE UP. A hold is a floor.
d = decide(21.99, 24.00, RULE)
check("a dearer supplier still raises the price", d.get("price"), 33.89)
check("  and that is NOT reported as a hold", bool(d.get("held")), False)

# 4. AND IT COMES BACK TO THE NUMBER, not to whatever the target allows.
d = decide(28.24, 15.34, RULE)
check("when the cost falls back it returns to the held price",
      d.get("price"), 21.99)

print("\n=== the warning I gave was wrong: a hold cannot freeze a loss ===")
# Selling 24.99 against a 24.00 cost is a loss of about 2.76 a unit.
UNDER = {"target_roi_pct": 20.0, "hold_price": 24.99}
d = decide(24.99, 24.00, UNDER)
truthy("an under-water listing is still lifted", (d.get("price") or 0) > 24.99)
check("  to the price the target needs", d.get("price"), 33.89)

print("\n=== the bulk action ===")
JS = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
truthy("there is one", "async function sourcingHoldAtCurrent(" in JS)
_fn = JS.split("async function sourcingHoldAtCurrent(")[1].split("\n// A PERCENTAGE")[0]
truthy("  it is on the selection bar", "sourcingHoldAtCurrent()" in
       JS.split("function _srcSelBar(")[1].split("async function")[0])
truthy("  and uses each row's OWN current price", "r.current.price" in _fn)
# A hold is a price. There is no honest number for a listing whose price could
# not be read, and inventing one is the fault the hold exists to prevent.
truthy("  a listing with no readable price is skipped",
       "current || {}).price != null" in _fn)
truthy("  and is reported rather than dropped silently", "noPrice" in _fn)
# It replaces an existing hold, so it must say so before it does.
truthy("  an existing held price is named before it is replaced",
       "already have a held price" in _fn and "REPLACED" in _fn)
truthy("  the figures are shown before anything is sent", "hold at " in _fn)
truthy("  and it says nothing on Amazon changes yet",
       "Nothing on Amazon changes now" in _fn)
# THIS PAGE HAS NO WHITE BROWSER DIALOGS, deliberately -- test_repricer_page
# enforces it, and my first cut of this broke that with a confirm() and two
# alert()s. Asserted here too so the next bulk action added to this file does
# not have to rediscover it from a failing test in another file.
truthy("  it asks with the app's own dialog", "await srcConfirm({" in _fn)
falsy = lambda l, g: check(l, bool(g), False)
# CODE ONLY. The comment above the call explains the rule and necessarily
# contains the word confirm() -- matching the raw text finds the explanation and
# calls it a violation, which is the same mistake three earlier assertions in
# this session made against comments.
_code = "\n".join(l.split("//")[0] for l in _fn.splitlines())
falsy("  and not the browser's confirm()",
      "confirm(" in _code.replace("srcConfirm(", ""))
falsy("  nor an alert()", "alert(" in _code)
# ONE VALIDATOR. /sourcing/rules already checks a held price ("40" / "£40" /
# "forty"); a second endpoint would be a second copy of that.
truthy("  it goes through the route that already validates a held price",
       '"/sourcing/rules"' in _fn)
truthy("  failures are listed per SKU", "failed.push" in _fn)

print("\n=== the wording tells the truth about what a hold does ===")
_bar = JS.split("function _srcSelBar(")[1].split("async function")[0]
truthy("the button says a cheaper supplier means margin, not a cut",
       "more margin, not a lower price" in _bar
       or "margin, not a lower price" in _bar)
truthy("  and that a dearer one can still raise it",
       "push the price UP" in _bar)
truthy("  so it can never hold you at a loss", "never hold you at a loss" in _bar)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
