"""The generator's input comes from an imported queue, not from Google.

This was the LAST live Google Sheets dependency. Reading it live meant no listing
could be started unless Google was reachable, the service account still had
access, and the sheet kept its name and tab.

The critical property: what the generator reads from the queue must be identical
to what it would have read from the sheet. If those two disagree, listings get
generated from subtly different data depending on which path ran, which is the
worst kind of bug -- correct-looking output built from the wrong numbers.
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

TMP = tempfile.mkdtemp(prefix="altainput_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "test.db")

from data import input_import as ii
from amazon_listing_generator import read_input_sheet

WS = "selvora"


class FakeSheet(object):
    """A worksheet, as far as read_input_sheet is concerned."""
    def __init__(self, grid): self.grid = grid
    def get_all_values(self): return self.grid


# A REAL-shaped input sheet: the column names these sheets actually use, which
# are not the names the app stores internally.
SHEET = [
    ["Amazon Link", "eBay Link", "Item Name", "eBay Price", "Amazon Price",
     "Delivery Time", "EAN"],
    ["https://www.amazon.co.uk/dp/B0G1K5B7QS", "https://ebay.co.uk/itm/1234",
     "Kitchen Spatula Set", "4.20", "8.00", "3", "5012345678900"],
    ["https://www.amazon.co.uk/dp/B083HN61GL", "https://ebay.co.uk/itm/5678",
     "Garden Hose 20m", "11.50", "24.99", "5", ""],
    ["", "", "", "", "", "", ""],                       # blank row
    ["not-a-url", "https://ebay.co.uk/itm/9", "No Amazon link", "1", "2", "1", ""],
]

print("=== the sheet is read by the GENERATOR'S own reader ===")
products = read_input_sheet(FakeSheet(SHEET))
check("blank rows are skipped, rows without an Amazon link too", len(products), 3)
check("  the cost is read from 'eBay Price'", products[0]["source_cost"], "4.20")
check("  the price from 'Amazon Price'", products[0]["selling_price"], "8.00")
check("  handling from 'Delivery Time'", products[0]["handling_time"], "3")
check("  the barcode from 'EAN'", products[0]["upc"], "5012345678900")

print("\n=== importing stores them ===")
added, updated, total = ii.import_from_worksheet(CFG, WS, FakeSheet(SHEET))
check("every product was added", added, 3)
check("  none updated on a first import", updated, 0)
check("  and the count is reported", total, 3)
s = ii.summary(CFG, WS)
check("the queue knows how many it holds", s["count"], 3)
check("  and when it was imported", bool(s["imported_at"]), True)
check("the ASIN is derived from the Amazon link",
      ii.rows(CFG, WS)[0]["competitor_asin"], "B0G1K5B7QS")

print("\n=== re-importing updates in place, it does not duplicate ===")
added, updated, total = ii.import_from_worksheet(CFG, WS, FakeSheet(SHEET))
check("nothing added", added, 0)
check("  everything updated", updated, 3)
check("  the queue is still the same size", ii.summary(CFG, WS)["count"], 3)

print("\n=== THE CRITICAL PROPERTY: queue == sheet ===")
# What the generator reads from the queue must equal what it would have read
# straight from the sheet. Anything else means listings built from different
# numbers depending on which path ran.
from_queue = read_input_sheet(ii.InputGrid(CFG, WS))
check("same number of products", len(from_queue), len(products))
check("IDENTICAL products, field for field", from_queue, products)

print("\n=== a changed sheet updates the queue ===")
CHANGED = [r[:] for r in SHEET]
CHANGED[1][4] = "9.99"                      # Amazon Price
ii.import_from_worksheet(CFG, WS, FakeSheet(CHANGED))
check("the new price is in the queue",
      read_input_sheet(ii.InputGrid(CFG, WS))[0]["selling_price"], "9.99")
check("  and still matches a direct read",
      read_input_sheet(ii.InputGrid(CFG, WS)),
      read_input_sheet(FakeSheet(CHANGED)))

print("\n=== an import never deletes ===")
SHORTER = [SHEET[0], SHEET[1]]              # the sheet lost a row
ii.import_from_worksheet(CFG, WS, FakeSheet(SHORTER))
check("the queue keeps what the sheet dropped", ii.summary(CFG, WS)["count"], 3)
check("clearing is the only way work leaves", ii.clear(CFG, WS), 3)
check("  and then it is empty", ii.summary(CFG, WS)["count"], 0)
check("an empty queue reads as no products",
      read_input_sheet(ii.InputGrid(CFG, WS)), [])

print("\n=== workspaces do not see each other's queues ===")
ii.import_from_worksheet(CFG, "green_haven", FakeSheet(SHEET))
check("green_haven has its own", ii.summary(CFG, "green_haven")["count"], 3)
check("  selvora is still empty", ii.summary(CFG, WS)["count"], 0)

print("\n=== the generator switches source by backend, not by guesswork ===")
src = open(r"D:\AltaScraper\amazon_listing_generator.py", encoding="utf-8").read()
check("it uses the imported queue on the db backend",
      "if _use_db:\n        from data.input_import import InputGrid" in src, True)
check("  and read_input_sheet is UNCHANGED by it",
      "def read_input_sheet(ws_in) -> list:" in src, True)
check("  the config carries its own path", 'cfg["_config_path"] = str(CONFIG_PATH)' in src, True)
check("it says out loud when the queue is empty",
      "imported queue is EMPTY" in src, True)

print("\n=== the endpoints are gated sensibly ===")
from auth.guard import required_permission
check("reading the queue needs nothing special",
      required_permission("/input/status", "GET"), None)
check("importing needs edit", required_permission("/input/import", "POST"), "edit")
check("clearing needs approve_delete",
      required_permission("/input/clear", "POST"), "approve_delete")

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
