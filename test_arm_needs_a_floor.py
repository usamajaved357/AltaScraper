"""The row says why it cannot be armed, and a floor can be set on many at once.

    "i am not able to arm a sku"

He could not, and the reason was real: that SKU had no minimum price, and a SKU
cannot be armed without one. But the ONLY place that was said was the Arm
button's tooltip -- text you have to hover to read, and which never appears on a
phone. So the button looked ordinary, did nothing visible, and the answer was
invisible.

MEASURED on his account: 66 of 67 tracked SKUs have no minimum price. So this
was not an edge case, it was the state of almost every row, and the fix he was
being pointed at could only be applied one row at a time.

TWO CHANGES, BOTH ASKED FOR ("yes do both"):

  1. the button names the missing thing and OPENS it, so the fix is one click
     from the problem rather than a hunt through the detail panel
  2. a bulk "Set minimum price" on the selection bar

A SHARE OF TODAY'S SELLING PRICE, NOT OF THE COST, and that is the whole point
of this particular number: the minimum price is the guard that still works when
a supplier's page is MISREAD, so deriving it from the supplier's figure would
tie the safety net to the thing it exists to protect against. It also works
where a cost-based floor could not -- 22 of the 67 have no readable supplier
cost, and those are the ones most in need of a floor.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


JS = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()

print("=== the row says what is missing, instead of a tooltip ===")
truthy("an un-armable SKU says so on the button",
       "Set a minimum price to arm" in JS)
truthy("  the test is the absence of a floor, not a guess",
       "(r.rule||{}).min_price == null" in JS)
truthy("  and pressing it opens the box that fixes it",
       "onclick=\"sourcingMinPrice('+_sarg(r.sku)+')\"" in JS)
# A SKU that CAN be armed must still get the ordinary button, or the change has
# simply replaced one confusing state with another.
truthy("a SKU with a floor still gets a plain Arm",
       "'+_sarg(r.sku)+',true)\">Arm</button>" in JS)
truthy("  and an armed one can still be disarmed", "Armed &mdash; disarm" in JS)

print("\n=== a floor can be set on many at once ===")
truthy("there is a bulk action", "async function sourcingMinPriceBulk(" in JS)
_fn = JS.split("async function sourcingMinPriceBulk(")[1].split("\n/* HOLD WHAT")[0]
truthy("  it is on the selection bar",
       "sourcingMinPriceBulk()" in JS.split("function _srcSelBar(")[1]
                                     .split("async function")[0])
truthy("  worked out from today's Amazon price", "r.current.price" in _fn)
# THE POINT OF THIS NUMBER. A floor derived from the supplier would fail in
# exactly the case it exists for.
truthy("  and NOT from the supplier's cost",
       "NOT from the supplier" in _fn)
truthy("  which is said where the number is typed",
       "misread" in _fn)
truthy("  a listing with no readable price is skipped",
       "current || {}).price != null" in _fn)
truthy("  and counted, not dropped silently", "noPrice" in _fn)

print("\n=== nothing is sent until the real figures are shown ===")
truthy("the percentage is checked before it is used",
       "pct <= 0 || pct > 100" in _fn)
truthy("  and a bad one leaves the box open", "return false;" in _fn)
truthy("every SKU's resulting floor is listed", "never below " in _fn)
truthy("  beside what it sells for now", "sells at " in _fn)
truthy("  an existing floor is named before it is replaced", "REPLACED" in _fn)
truthy("  and it says nothing on Amazon changes", "Nothing on Amazon changes" in _fn)
truthy("failures are reported per SKU", "failed.push" in _fn)
# ONE VALIDATOR: /sourcing/rules already checks a money box ("40" / "£40" /
# "forty"). A second endpoint would be a second copy of that.
truthy("it goes through the route that already validates a price",
       '"/sourcing/rules"' in _fn)

print("\n=== this page still has no white browser dialogs ===")
_code = "\n".join(l.split("//")[0] for l in _fn.splitlines())
falsy("no confirm()", "confirm(" in _code.replace("srcConfirm(", ""))
falsy("no alert()", "alert(" in _code)
falsy("no prompt()", "prompt(" in _code.replace("_srcTargetBox(", ""))
truthy("it asks with the app's own dialogs",
       "_srcModal(" in _fn and "await srcConfirm({" in _fn)

print("\n=== the arithmetic ===")
# 80% of 19.97 is 15.976, which must round to 15.98 and not 15.97 -- a floor
# rounded DOWN is a floor slightly below the one that was agreed to.
m = re.search(r"Math\.round\(Number\(r\.current\.price\) \* pct\) / 100", _fn)
truthy("the floor is price x percent, rounded to the penny", bool(m))
for price, pct, want in ((19.97, 80, 15.98), (29.99, 80, 23.99),
                         (16.99, 80, 13.59), (10.00, 50, 5.00)):
    got = round(price * pct) / 100
    check("  %.2f at %d%% -> %.2f" % (price, pct, want), got, want)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
