"""Parent and child, shown the way Amazon holds them.

    "ALSO I WANT MY APP TO SHOW the parents and child relation like we have in
     amazon."

WHAT WAS MISSING, AND WHAT WAS NOT

Everything needed to CREATE a variation family already existed and was well
tested. Nothing existed to VIEW one: the Variations screen is a creation wizard
over a FLAT list, and the only sign of a family anywhere was one line of text on
a selected row of the Listings screen.

The DATA was not missing either. Amazon returns it on getListingsItem under
`relationships`, and routes/live_routes.py has parsed it since the mirror was
built -- but only on the 300-SKU full pull, into an in-memory cache that a
restart erased. So the app knew, briefly, and forgot.

It is now read on the pass that already visits every SKU for its thumbnail, and
stored on the snapshot beside it.

WHAT THIS FILE PINS

  1. a family is assembled from EITHER direction -- a child naming its parent,
     or a parent naming its children -- because either half can be missing and
     using one loses the family whenever the other is the half that failed
  2. an orphan is reported, never hidden
  3. the variation fields survive a Sync, which is the bug the thumbnails had
  4. a zero has a denominator
"""
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import families as _fam          # noqa: E402
from domain import live_snapshots as _snap    # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def fam_by(out, parent):
    return next((f for f in out["families"] if f["parent_sku"] == parent), None)


print("\n== a family, from the parent's side ==")
out = _fam.build([
    {"sku": "P-FAN", "title": "Ceiling fan", "child_skus": ["FAN-W", "FAN-B"],
     "variation_theme": "COLOR"},
    {"sku": "FAN-W", "title": "Ceiling fan white", "qty": "4"},
    {"sku": "FAN-B", "title": "Ceiling fan black", "qty": "0"},
])
f = fam_by(out, "P-FAN")
truthy("the family is found", f)
check("  with both children", f["child_count"], 2)
check("  the theme Amazon gave", f["theme"], "COLOR")
check("  units across the children", f["listed_units"], 4)
check("  and how many can actually be bought", f["in_stock_children"], 1)
check("  the parent is present, so it is not an orphan", f["orphan"], False)

print("\n== the same family, from the children's side only ==")
# Either half can be missing: a SKU may not be enriched yet, or Amazon may
# answer one call and throttle the other. Reading one direction only loses the
# family whenever the SKU carrying the link was the one that failed.
out = _fam.build([
    {"sku": "FAN-W", "title": "white", "qty": "4", "parent_skus": ["P-FAN"],
     "variation_theme": "COLOR"},
    {"sku": "FAN-B", "title": "black", "qty": "2", "parent_skus": ["P-FAN"]},
    {"sku": "P-FAN", "title": "Ceiling fan"},
])
f = fam_by(out, "P-FAN")
truthy("still found with no child_skus anywhere", f)
check("  both children", f["child_count"], 2)
check("  and the theme, carried by a CHILD", f["theme"], "COLOR")

print("\n== both directions at once do not double-count ==")
out = _fam.build([
    {"sku": "P", "child_skus": ["A", "B"], "variation_theme": "SIZE"},
    {"sku": "A", "qty": "1", "parent_skus": ["P"]},
    {"sku": "B", "qty": "1", "parent_skus": ["P"]},
])
check("one family", out["family_count"], 1)
check("  two children, not four", fam_by(out, "P")["child_count"], 2)

print("\n== an orphan is reported, not hidden ==")
out = _fam.build([
    {"sku": "K1", "title": "small", "qty": "3", "parent_skus": ["GONE"],
     "variation_theme": "SIZE"},
    {"sku": "SOLO", "title": "on its own", "qty": "9"},
])
f = fam_by(out, "GONE")
truthy("the family exists even though its parent does not", f)
check("  and says so", f["orphan"], True)
check("  the parent record is None rather than invented", f["parent"], None)
check("  its child is still counted", f["child_count"], 1)
check("  and the stand-alone listing is a single, not a family",
      out["singles"], 1)

print("\n== orphans sort last, biggest families first ==")
out = _fam.build([
    {"sku": "SMALL", "child_skus": ["s1"]}, {"sku": "s1", "qty": "1"},
    {"sku": "BIG", "child_skus": ["b1", "b2", "b3"]},
    {"sku": "b1", "qty": "1"}, {"sku": "b2", "qty": "1"}, {"sku": "b3", "qty": "1"},
    {"sku": "o1", "qty": "1", "parent_skus": ["NOWHERE"]},
])
check("the 3-child family leads", [f["parent_sku"] for f in out["families"]],
      ["BIG", "SMALL", "NOWHERE"])

print("\n== nothing invented from nothing ==")
check("no items, no families", _fam.build([])["family_count"], 0)
check("  None does not raise", _fam.build(None)["family_count"], 0)
check("  a listing with no relationships is a single",
      _fam.build([{"sku": "X", "qty": "1"}])["singles"], 1)
check("  and rubbish in the list is skipped",
      _fam.build([{"sku": "X"}, "not a dict", None, 42])["counted"], 1)
# An empty relationships list is Amazon saying "no family", not a family of none.
check("an empty child list is not a family",
      _fam.build([{"sku": "P", "child_skus": []}])["family_count"], 0)
# A SKU with a blank parent must not create a family keyed on "".
check("a blank parent sku creates nothing",
      _fam.build([{"sku": "A", "parent_skus": [""]}])["family_count"], 0)

print("\n== the fields survive a Sync ==")
# THE EXACT BUG THE THUMBNAILS HAD. The catalogue report carries no
# relationships, so a straight replace would wipe every family the refresher had
# learned, on every Sync -- and pressing Refresh would make it worse.
for f in ("parent_skus", "child_skus", "variation_theme"):
    check("%s is carried forward when a fresh report omits it" % f,
          f in _snap._ENRICHED_FIELDS, True)
merged, kept = _snap._carry_forward(
    [{"sku": "A", "qty": "5"}],
    [{"sku": "A", "qty": "1", "parent_skus": ["P"], "variation_theme": "COLOR",
      "img": "x.jpg"}])
check("  the family survives", merged[0].get("parent_skus"), ["P"])
check("  and the theme", merged[0].get("variation_theme"), "COLOR")
check("  while the fresh quantity still wins", merged[0].get("qty"), "5")

print("\n== it is collected on the pass that already visits every SKU ==")
LR = open(r"D:\AltaScraper\routes\live_routes.py", encoding="utf-8-sig").read()
truthy("the per-SKU call asks Amazon for relationships",
       re.search(r'includedData="summaries,issues,fulfillmentAvailability,'
                 r'attributes,relationships"', LR))
truthy("  read through the one helper that understands the block",
       re.search(r"_var = _mirror_variations\(", LR))
RF = open(r"D:\AltaScraper\domain\live_refresher.py", encoding="utf-8-sig").read()
for f in ("parent_skus", "child_skus", "variation_theme"):
    truthy("the refresher stores %s" % f, ('fields["%s"]' % f) in RF)
# A stand-alone listing must not get an empty parent written against it, or
# "not in a family" becomes indistinguishable from "not looked at yet".
truthy("  only when the SKU is really in a family",
       re.search(r'if m\.get\("parent_skus"\):', RF))

print("\n== a zero has a denominator ==")
SRC = open(r"D:\AltaScraper\domain\families.py", encoding="utf-8-sig").read()
truthy("for_account reports how much of the catalogue has been asked",
       "relationships_known_for" in SRC)
JS = open(r"D:\AltaScraper\static\js\variations.js", encoding="utf-8-sig").read()
truthy("and the screen tells the two apart",
       "No variation families found" in JS
       and "Nothing has been read yet" in JS)
# It must LEAD with what is true and qualify after -- an earlier version led
# with "press Sync" whenever one listing was outstanding, so 46 of 47 read as
# "not ready" when it was effectively done.
truthy("  and says how many are still outstanding without hiding the answer",
       re.search(r"No variation families found[\s\S]{0,600}not been read "
                 r"individually yet", JS))

print("\n== the screen shows the family, and creating one still works ==")
truthy("families are loaded when the screen opens", "varFamiliesLoad()" in JS)
truthy("  a parent opens to reveal its children", "varFamilyToggle" in JS)
truthy("  drawn into its own host so the picker is not rebuilt",
       'id="varfamilies"' in JS)
truthy("  and redrawn after the wizard repaints over it",
       re.search(r"host\.innerHTML = h;\s*\n\s*//[\s\S]{0,200}varFamiliesRender\(\)", JS))
# The three-step wizard is what CREATES families and must be untouched.
truthy("the creation wizard is still there",
       'VAR_STEPS = ["Pick the products"' in JS)
VR = open(r"D:\AltaScraper\routes\variations_routes.py", encoding="utf-8-sig").read()
truthy("the families route is read-only",
       re.search(r'@app\.route\("/variations/families"\)\s*\n\s*def', VR))
# The "already in a family" chip read parent_sku -- singular -- which nothing
# has ever written, so it has been dead since it was added.
truthy("the already-in-a-family chip reads the field that exists",
       "_skus_first(it.get(\"parent_skus\"))" in VR)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
