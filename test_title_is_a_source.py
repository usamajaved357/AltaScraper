"""The competitor ASIN is a reference, not the product being sold.

CLAUDE.md rule 1 says it plainly: the ASIN in the SKU is a COMPETITOR REFERENCE
used only to pull product data. The listing is a new product under the owner's
own brand. But the auto-fix source chain did not know that -- it read eBay, then
the competitor, then asked the AI, and the TITLE was not a source at all.

Two measured cases, both of them the reported complaint "some information is
filled but do not accurately represent the listing":

    Vacuum Insulated Jug 1.5L     capacity filled 2 litres from eBay
    Spin Mop REFILL SET 4 Heads   size filled "148cm" -- the handle length of
                                  the full mop, which the refill set does not
                                  even include

So the title goes first for facts it states outright, and where a source
contradicts it, the suggestion says so instead of passing quietly.

WHAT THIS DELIBERATELY DOES NOT DO. It infers nothing. A title silent about
capacity contributes nothing about capacity and the chain carries on to eBay
exactly as before -- because a title-shaped guess would be the same mistake in
the opposite direction.
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


import dashboard as D

JUG = "Vacuum Insulated Stainless Steel Jug 1.5L Hot Cold Flask"
FLASK = "Vacuum Insulated Thermos Flask Stainless Steel 2 Litre Hot Cold"
MOP = "Spin Mop Refill Set 4 Microfibre Heads Triangle"
RASP = "Farriers Horse Hoof File Double-Sided Rasp 350mm 14 inch"

print("== a figure the title states outright is taken from the title ==")
check("the jug's capacity value", D.title_fact("capacity.value", JUG), ("1.5", "Title"))
check("  and its unit", D.title_fact("capacity.unit", JUG), ("l", "Title"))
check("  the whole thing when the field is not split",
      D.title_fact("capacity", JUG), ("1.5 l", "Title"))
check("'2 Litre' is read the same as '1.5L'",
      D.title_fact("capacity.value", FLASK), ("2", "Title"))
check("a length in the title", D.title_fact("length.value", RASP), ("350", "Title"))

print("\n== and nothing is inferred when the title is silent ==")
# This is the half that keeps it honest. A title-shaped guess would be the same
# mistake as a competitor-shaped one.
check("the mop title says nothing about capacity",
      D.title_fact("capacity.value", MOP), (None, None))
check("  nor about weight", D.title_fact("weight.value", MOP), (None, None))
check("an empty title contributes nothing",
      D.title_fact("capacity.value", ""), (None, None))
check("a field the rule does not cover is left alone",
      D.title_fact("color", JUG), (None, None))
# "4 Microfibre Heads" is a COUNT, not a capacity or a length. Reading it as a
# measurement is exactly the class of error this exists to stop.
check("a bare count is not read as a measurement",
      D.title_fact("length.value", MOP), (None, None))

print("\n== a source that contradicts the title is flagged, not silenced ==")
w = D.title_disagrees("capacity.value", "2", JUG)
truthy("eBay's 2 against the title's 1.5 warns", w)
truthy("  quoting both figures", "1.5" in w and "2" in w)
truthy("  and saying which one is the product",
       "the product being sold" in w)

check("agreement produces no warning",
      D.title_disagrees("capacity.value", "1.5", JUG), "")
check("  including a trailing-zero spelling of the same number",
      D.title_disagrees("capacity.value", "1.50", JUG), "")
check("silence produces no warning",
      D.title_disagrees("capacity.value", "2", MOP), "")
check("  and neither does a non-numeric value",
      D.title_disagrees("capacity.value", "medium", JUG), "")
check("  nor an empty one", D.title_disagrees("capacity.value", "", JUG), "")

print("\n== the chain reads the title first ==")
src = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
truthy("_from_source consults the title before any source",
       "# THE TITLE FIRST" in src)
truthy("  and the warning is attached to the suggestion",
       "_warn = \"\" if src == \"Title\" else _title_disagrees(field, val)" in src)
truthy("  with rule 1 named, since that is where the rule comes from",
       "CLAUDE.md rule 1" in src)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
