"""Four fixes: column alignment, deleted SKUs, a backup, and the slow Orders page.

"in the listings section i see that the header and the details under it do not
 match"
"the template and the repricer is saving the skus which i have deleted already,
 turn off the auto repricing for that sku and give warning"
"i think we should have a button that saves the data of the deleted listings as
 a backup"
"the orders page takes too much long to reflect the item name and image etc"
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)
def falsy(l, g): check(l, bool(g), False)

L = open(r"D:\AltaScraper\static\js\listings.js", encoding="utf-8").read()
M = open(r"D:\AltaScraper\static\js\miles_template.js", encoding="utf-8").read()
O = open(r"D:\AltaScraper\routes\orders_routes.py", encoding="utf-8").read()
R = open(r"D:\AltaScraper\routes\sourcing_routes.py", encoding="utf-8").read()
SR = open(r"D:\AltaScraper\domain\source_repo.py", encoding="utf-8").read()
J = open(r"D:\AltaScraper\static\js\sourcing.js", encoding="utf-8").read()

print("=== the table columns line up ===")
# liveTableRow shipped with NINE cells against a ten-column header, so the whole
# live view was shifted one place left: pictures under the checkbox, actions
# under "Compliance". HTML does not complain -- a short row just draws short.
truthy("the live row has a select cell like every other row",
       '<td class="selcol">' in L)
# THIS USED TO PIN THE CELL AS EMPTY -- '<td class="selcol"></td>' -- and to
# require the sentence explaining why. Both were a proxy for the real point,
# which the heading above states: the columns line up. The cell has since been
# filled with a checkbox (the bulk bar grew stock/price/handling, which are live
# Amazon changes and want exactly these rows), and pinning the empty version
# would have made this test defend the bug. The count is asserted directly in
# test_live_row_select.py, against the rendered row rather than its source.
truthy("  and it now offers a tick, like the tile does",
       "<td class=\"selcol\">${rowSelectBox({sku: it.sku||''})}</td>" in L)
truthy("and a mismatch is now SHOUTED rather than left to be seen",
       "the columns will not line up" in L)
truthy("  counted from the header itself, not a hard-coded number",
       '(head.match(/<th\\b/g) || []).length' in L)
truthy("  naming which builder is wrong", "liveTableRow" in L and "tableRow" in L)

print("\n=== a SKU deleted on Amazon stops being priced ===")
from domain import sourcing as S
from domain import source_repo as SRepo
check("the store has a name for it", SRepo.GONE, "gone")
check("  and for the opposite", SRepo.LIVE_OK, "ok")
truthy("marking it gone DISARMS it in the same statement",
       "mode='dry_run' WHERE workspace_id=?" in SR)
# Matched on a fragment that cannot straddle a line wrap -- the sentence is
# there, my first attempt at quoting it just broke across one.
truthy("  and the reason is written down", "the pricer will go on" in SR)
truthy("  while its sources and history are kept", "are worth" in SR
       and "relisted tomorrow" in SR)

print("\n--- and the decision refuses before anything else ---")
d = S.decide({"price": 21.99, "quantity": 5, "lead_days": 4}, [], {},
             listing_state="gone")
check("it is blocked", d["blocked_by"], "this listing is gone from Amazon")
truthy("  saying there is no offer to price", "no offer to" in d["reason"])
truthy("  and that auto-pricing is off", "switched off" in d["reason"])
check("  and no price is proposed", d["price"], None)
check("the state travels with the decision", d["listing_state"], "gone")
# Checked BEFORE the sources, because nothing below it can matter.
d2 = S.decide({"price": 21.99}, [], {}, listing_state="ok")
check("an ok listing is not blocked by this", d2["blocked_by"], "")

print("\n--- 'nobody looked' is not 'it is gone' ---")
d3 = S.decide({"price": 21.99}, [], {}, listing_state=None)
check("an unchecked SKU behaves as before", d3["blocked_by"], "")
truthy("and a timeout is never taken as deletion",
       "Amazon would not answer\" is NOT \"the listing is gone" in R)

print("\n--- the screen says so, and offers the check ---")
truthy("a red chip on the row", "_goneChip" in J and "deleted on Amazon" in J)
truthy("  saying auto-pricing is already off", "auto-pricing switched off" in J)
truthy("a button to ask Amazon about every tracked SKU",
       "sourcingCheckListings" in J and "/sourcing/check_listings" in R)
truthy("  which warns that it costs a call per SKU", "per SKU, so it takes" in J)
truthy("and the template leaves the deleted ones out",
       "!= _repo.GONE" in R)
truthy("  saying how many it dropped", "X-Alta-Skipped-Deleted" in R)

print("\n=== every rule is per SKU, never per ASIN ===")
# "the repricer should work for each sku, because a single asin can have more
#  than 1 sku. the rule is per sku and not per asin"
SS = open(r"D:\AltaScraper\domain\sourcing.py", encoding="utf-8").read()
truthy("said in decide()", "PER SKU, NEVER PER ASIN" in SS)
truthy("  with the reason", "can carry several of our SKUs" in SS)
# Asserted on CODE, with comments AND docstrings removed. The prose says the word
# ASIN four times, in the paragraph explaining why nothing reads one -- a test
# that forbade the word outright would delete its own explanation. Parsed rather
# than pattern-matched, because a docstring is not something a regex can find the
# end of reliably.
import ast as _ast
_tree = _ast.parse(SS)
for _n in _ast.walk(_tree):
    # Blank out every docstring, so what is left is only what runs.
    if isinstance(_n, (_ast.Module, _ast.FunctionDef, _ast.ClassDef)):
        if (_n.body and isinstance(_n.body[0], _ast.Expr)
                and isinstance(_n.body[0].value, _ast.Constant)
                and isinstance(_n.body[0].value.value, str)):
            _n.body[0].value.value = ""
_live = _ast.unparse(_tree)
falsy("and no line of code in the rules module reads an ASIN",
      "asin" in _live.lower())

print("\n=== the deleted listings can be saved before they go ===")
truthy("there is a backup", "function backupDeletedRows" in M)
truthy("  offered BEFORE the delete, not beside it",
       "Asking afterwards would be asking too late" in M)
truthy("  keeping every field rather than a chosen few",
       "you did not have to know in advance" in M)
truthy("  including the nested ones", "_nested_json" in M)
truthy("  quoted properly", 'replace(/"/g, \'""\')' in M)
truthy("  with a BOM so Excel reads it", '"\\ufeff" + lines.join' in M)
truthy("  named for the account and the day", "deleted-listings-" in M)
# IT MOVED, AND TO A BETTER PLACE. It used to sit on a one-line red warning that
# named the first three SKUs and hid the rest -- the only trace deleted listings
# had anywhere in the app. They have their own view now ("Removed"), so the
# backup is offered next to the listings it would back up, where they can be
# looked at first. Asked for as: "i also asked you to give me a button where the
# deleted listings go when they are deleted from amazon but they are stored in
# the app".
truthy("and it is offered beside the listings themselves",
       "Save a backup" in M and "backupDeletedRows()" in M)
truthy("  which now have a view of their own",
       'LIST_SOURCE==="removed"' in M)
truthy("  reachable from the toolbar", 'data-src="removed"' in
       open(r"D:\AltaScraper\templates\dashboard.html", encoding="utf-8").read())
truthy("  and the old warning points at it instead of hiding them",
       "see ${goneRows.length>1?'them':'it'} in Removed" in M)
# Clearing them is still a deliberate act and still says it does not touch Amazon.
truthy("  clearing is still separate from Amazon",
       "does not touch Amazon" in M)

print("\n=== the Orders page reads what it already knows ===")
# Measured: ~65s for 24 orders, one sequential Amazon call each. After: 2.5s on
# the first pass and 0.0s on the second.
truthy("the store is asked first", "_items_from_store" in O)
truthy("  because an order's contents never change",
       "never change once it is placed" in O)
truthy("  from the table that already holds them", "FROM order_lines" in O)
truthy("what Amazon returns is kept", "_store_items(" in O)
truthy("  through the writer that already exists, not a second one",
       "_hw.store_lines(" in O)
truthy("  and a failed cache write never breaks the page",
       "a cache must never be the reason this fails" in O)
truthy("the purchase date travels, so a cached row is dated",
       'r.get("purchased") or ""' in O)
truthy("and the module docstring no longer claims nothing is cached",
       "Its CONTENTS are not" in O)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
