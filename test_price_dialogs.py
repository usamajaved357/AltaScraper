"""Changing a price must not throw browser dialogs, or warn about nothing.

WHAT WAS REPORTED

    "whenever i try to change the price of a sku through the app it gives me 3
     warnings and i dont like this white appearing messages over the window.
     modern apps do not behave like this ... and why is it giving me fake and
     wrong warnings, also fix them, i do not know about which floor is it
     talking about. i was increasing the price, not decreasing it."

Two separate faults, and this pins both.

1. THREE NATIVE DIALOGS. prompt() for the number, confirm() for the preview,
   confirm() again for the floor -- three white system boxes stacked over a dark
   app, each throwing away what the last had shown (screenshots 85, 86, 87).

2. WARNINGS THAT WERE NOT WARNINGS.
     * the floor was computed by floor_from_rate(cost, 0.15), which ignored
       every setting the account had and silently assumed the old built-in
       3.00 postage + 2.00 ads + 1.00 profit. On a 20.99 cost that produced a
       floor of 31.76 when the honest one is 29.63 -- so a price could be
       called a loss when it was not;
     * "this SKU records no source cost" was raised as a warning. It is true of
       every hand-named SKU and says nothing about the change being made;
     * a 30% move was flagged in BOTH directions with "usually a typo -- check
       the decimal point", on a deliberate price RISE, which is the ordinary
       thing this screen is for.
"""
import io
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


JS = io.open(r"D:\AltaScraper\static\js\priceedit.js", encoding="utf-8").read()
PY = io.open(r"D:\AltaScraper\routes\price_routes.py", encoding="utf-8").read()

# Comments in both files describe the dialogs they replaced, by name. Matching
# on the raw text would find those and pass -- or fail -- on the explanation
# rather than on the code. This has caught me out three times in this project,
# so the comments come out first and the assertions run on what executes.
CODE = re.sub(r"//[^\n]*", "", re.sub(r"/\*[\s\S]*?\*/", "", JS))

# Same trap on the Python side, and it caught this test too: price_routes.py now
# carries a comment saying it "called floor_from_rate(cost, 0.15) directly",
# which is the very string the assertion below looks for. Comments and
# docstrings are removed with tokenize rather than a regex, because a # inside a
# string literal is not a comment.
import io as _io
import tokenize as _tok


def _strip_py(src):
    out, prev_end, prev_type = [], (1, 0), None
    try:
        toks = list(_tok.generate_tokens(_io.StringIO(src).readline))
    except Exception:
        return src
    for t in toks:
        if t.type == _tok.COMMENT:
            continue
        # A string on its own line is a docstring, not a value being used.
        if t.type == _tok.STRING and prev_type in (None, _tok.INDENT,
                                                   _tok.NEWLINE, _tok.NL):
            prev_type = t.type
            continue
        out.append(t.string)
        prev_type = t.type
    return " ".join(out)


# tokenize re-joins with single spaces, so exact substrings like
# "floor_price(cost, rule)" no longer appear literally. Both sides are compared
# with ALL whitespace removed, which makes the assertions independent of how the
# line happens to be wrapped as well.
_PYCODE = re.sub(r"\s+", "", _strip_py(PY))


def pyhas(needle):
    return re.sub(r"\s+", "", needle) in _PYCODE


print("=== no native dialogs are left in the price flow ===")
for fn in ("prompt(", "confirm(", "alert("):
    falsy("  %s is gone from the code" % fn, fn in CODE)
truthy("  and it is still mentioned in the comments, so nobody re-adds it",
       "confirm()" in JS)

print("\n=== it is one panel, in the app's own skin ===")
truthy("uses the app's modal, not the browser's", 'className = "modalwrap"' in CODE)
truthy("  with a single send button", 'id="pe_send"' in CODE)
truthy("  and one price box to type into", 'id="pe_price"' in CODE)
truthy("  Escape closes it", '"Escape"' in CODE)
truthy("  Enter sends it", '"Enter"' in CODE)
truthy("  clicking the surround closes it", "ev.target === el" in CODE)
truthy("  and the preview is debounced, not one call per keystroke",
       "setTimeout(_pePreview" in CODE)

print("\n=== below the floor is a deliberate act, not a third dialog ===")
truthy("a tickbox has to be ticked", 'id="pe_below"' in CODE)
truthy("  the button refuses until it is", "b.disabled = !(box && box.checked)" in CODE)
truthy("  and says what it would do", "below the floor" in CODE)
# The browser is not the control. The server is asked again.
truthy("  and the server is still told, so the check is not client-side only",
       "below_floor_ok" in CODE and pyhas("below_floor_ok"))

print("\n=== the floor is the account's own, not a hardcoded 15% rule ===")
truthy("it goes through the one floor function the repricer uses",
       pyhas("_sourcing.floor_price(cost, rule)"))
truthy("  reading the account's stored rule", pyhas("_repo.rule_for("))
falsy("  and no longer hardcodes the rate", pyhas("floor_from_rate(cost, 0.15)"))

print("\n=== warnings are for money at risk; everything else is a note ===")
truthy("the reply separates the two", pyhas('"notes": notes'))
truthy("  a missing cost is a note", pyhas("notes.append(why)"))
truthy("  a price ABOVE the floor is a note, not silence",
       pyhas("still meets"))
truthy("  only a CUT is warned about", pyhas("move <= -30"))
truthy("  a rise is stated, not warned about", pyhas("move >= 30"))
falsy("  and the floor text no longer claims postage and ads were deducted",
      pyhas("postage and advertising are paid"))

print("\n=== the numbers, on the SKU from the screenshots ===")
# 20.99_3Days_B0BYZVM18Y -- the floor shown was 31.76.
from domain import cogs as C
from domain import sourcing as S
from listing import pricing as P

cost = C.cost_from_sku("20.99_3Days_B0BYZVM18Y")
check("the cost still comes out of the SKU", cost, 20.99)
old = P.floor_from_rate(cost, 0.15, 3.00, 2.00, 1.00)
check("  the old floor was the 31.76 he was shown", old, 31.76)
new = S.floor_price(cost, None)
truthy("  the honest floor is lower, because nothing is invented", new < old)
print("       old %.2f -> now %.2f" % (old, new))
truthy("  and it is still above break-even", new > cost / 0.85)
check("  it returns the safety minimum on the cash",
      P.achieved(new, cost, 0.15)["roi_pct"] >= P.PRICING_RULE_MIN_ROI_PCT, True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
