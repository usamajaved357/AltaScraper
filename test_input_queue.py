"""Products added in the app, without a spreadsheet.

The Generate screen showed the Google input sheet READ-ONLY: you could look at
it, and changing anything meant leaving the app, editing in Google, coming back
and pressing Import. The queue itself already lived in the database; only the
way IN was still a spreadsheet.

The trap in adding one row at a time: import_rows keys on the row's POSITION in
the source sheet. That is right for an import -- re-importing updates in place
instead of duplicating -- and useless by hand, where every added row would be
index 0 and would overwrite the last one.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

TMP = tempfile.mkdtemp()
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write('{"db_path": "%s"}' % os.path.join(TMP, "t.db").replace("\\", "/"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")

from data import input_import as ii

WS = "jack_uk"
print("=== adding products by hand ===")
a = ii.add_row(CFG, WS, {"ebay_url": "https://www.ebay.co.uk/itm/111",
                         "item_name": "Ceiling fan", "source_cost": "32.99",
                         "handling_time": "3"})
b = ii.add_row(CFG, WS, {"ebay_url": "https://www.ebay.co.uk/itm/222",
                         "item_name": "Weed slasher", "source_cost": "7.15"})
c = ii.add_row(CFG, WS, {"amazon_url": "https://www.amazon.co.uk/dp/B0H7N2Q5GG",
                         "item_name": "Third"})
check("three products queued", ii.summary(CFG, WS)["count"], 3)
# THE BUG THIS GUARDS: keyed on sheet position, all three would be row_index 0
# and the queue would hold ONE product with the last one's values.
rows = ii.rows(CFG, WS)
check("  each got its own row", len(rows), 3)
check("  with distinct positions", len({r["row_index"] for r in rows}), 3)
check("  and they are all still there, not overwritten",
      sorted(r["item_name"] for r in rows), ["Ceiling fan", "Third", "Weed slasher"])
check("an Amazon link yields its ASIN without being asked",
      [r["competitor_asin"] for r in rows if r["item_name"] == "Third"],
      ["B0H7N2Q5GG"])
check("hand-added rows are marked as such, not as sheet rows",
      {r["source"] for r in rows}, {"app"})

print("\n=== editing one ===")
check("a price is set", ii.update_row(CFG, WS, a, {"selling_price": "59.99"}), 1)
check("  and reads back", [r["selling_price"] for r in ii.rows(CFG, WS)
                           if r["id"] == a], ["59.99"])
check("only the given column changes",
      [r["item_name"] for r in ii.rows(CFG, WS) if r["id"] == a], ["Ceiling fan"])
check("a column the queue does not have is ignored, not written",
      ii.update_row(CFG, WS, a, {"nonsense": "x"}), 0)
# Scoped by workspace so an id from elsewhere cannot reach across.
check("an id from another workspace edits nothing",
      ii.update_row(CFG, "nestwell_goods", a, {"item_name": "hijacked"}), 0)
check("  and the row is untouched",
      [r["item_name"] for r in ii.rows(CFG, WS) if r["id"] == a], ["Ceiling fan"])

print("\n=== removing one ===")
check("it goes", ii.delete_row(CFG, WS, b), 1)
check("  two left", ii.summary(CFG, WS)["count"], 2)
check("another workspace cannot delete it",
      ii.delete_row(CFG, "nestwell_goods", a), 0)
check("  so it is still there", ii.summary(CFG, WS)["count"], 2)

print("\n=== a sheet import lands AFTER what was typed, not on top of it ===")
# next_index is why. Import writes by position from 0; without this the first
# imported row would overwrite the first hand-added one.
ii.import_rows(CFG, WS, [{"ebay_url": "https://www.ebay.co.uk/itm/999",
                          "item_name": "From the sheet"}], source="sheet")
names = [r["item_name"] for r in ii.rows(CFG, WS)]
truthy("the sheet row arrived", "From the sheet" in names)
truthy("  and the hand-added one survived", "Ceiling fan" in names)
check("the next hand-added row goes after everything",
      ii.next_index(CFG, WS) > max(r["row_index"] for r in ii.rows(CFG, WS)), True)

print("\n=== the generator reads the same queue, unchanged ===")
from amazon_listing_generator import read_input_sheet

class _Grid(object):
    """A worksheet with pre-set values -- read_input_sheet asks for nothing else."""
    def __init__(self, values): self._v = values
    def get_all_values(self): return self._v

got = read_input_sheet(ii.InputGrid(CFG, WS))
truthy("it reads the hand-added products", len(got) >= 2)
_names = " ".join(str(g) for g in got)
truthy("  including one that never touched a spreadsheet", "Ceiling fan" in _names)

print("\n=== a source link is enough; a competitor ASIN is not required ===")
# read_input_sheet required amazon_url and dropped everything else in silence.
# Per Rule 1 the ASIN is a COMPETITOR REFERENCE for pulling product data, not
# the thing being listed -- so the eBay link, which the generator already reads
# title, specifics and images from, is a perfectly good starting point. On a
# spreadsheet the drop was invisible; typed into the app it is a trap.
_only_ebay = read_input_sheet(_Grid([
    ["ebay_url", "amazon_url", "item_name"],
    ["https://www.ebay.co.uk/itm/555", "", "Only a source link"],
    ["", "https://www.amazon.co.uk/dp/B0H7N2Q5GG", "Only a competitor"],
    ["", "", "Neither"],
]))
check("a row with only a source link is kept",
      any(p["item_name"] == "Only a source link" for p in _only_ebay), True)
check("  a row with only a competitor link still is too",
      any(p["item_name"] == "Only a competitor" for p in _only_ebay), True)
check("  and a row with neither is still dropped -- nothing to generate from",
      any(p["item_name"] == "Neither" for p in _only_ebay), False)

print("\n=== the endpoints are gated ===")
from auth.guard import required_permission
check("adding needs edit", required_permission("/input/add", "POST"), "edit")
check("editing needs edit", required_permission("/input/update", "POST"), "edit")
# Deleting one row is still throwing work away, like clearing the queue.
check("deleting needs approve_delete",
      required_permission("/input/delete", "POST"), "approve_delete")
check("clearing still needs approve_delete",
      required_permission("/input/clear", "POST"), "approve_delete")

print("\n=== the screen owns its own functions ===")
IQ = open(r"D:\AltaScraper\static\js\inputqueue.js", encoding="utf-8").read()
SH = open(r"D:\AltaScraper\static\js\shell.js", encoding="utf-8").read()
truthy("the queue file defines them", "function loadInputSheet()" in IQ)
# shell.js loads LAST, so a leftover copy there would silently win and the
# screen would go back to being read-only.
check("shell.js no longer defines a rival copy",
      "async function loadInputSheet()" in SH, False)
check("  nor the filter", "function filterInputSheet()" in SH, False)

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
