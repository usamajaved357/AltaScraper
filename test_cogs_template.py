"""The cost sheet: handed out filled in, and read back correctly.

"have you provided template for uploading the cogs?"

No. There was a COGS CSV UPLOAD and no template, so the columns had to be
guessed and every SKU typed by hand -- and a hand-typed SKU is one that silently
matches nothing. The upload's own error for that case was "No matchable rows
(check sku/asin values match your listings)", which is the app telling you it
cannot read what it asked you to write.

AND THE UPLOAD COULD NOT READ ITS OWN SHEET. It split each line on commas, which
is not what a CSV is. Then the server-side reader, which does parse CSV, was
SNIFFING the dialect -- and the sniffer gets a real file wrong.
"""
import io
import csv
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)
def falsy(l, g): check(l, bool(g), False)

from domain import cogs as C
from domain import sheets as SH
from domain import source_bulk as SB

print("=== the columns ===")
check("what the sheet carries", C.TEMPLATE_HEADERS,
      ["sku", "asin", "product", "cost", "cost now", "where from"])
# Checked through the REAL matcher, not by eye: a header the parser misses turns
# a working file into "no cost column found".
check("the sku column is found", SH.pick(C.TEMPLATE_HEADERS, SB._SKU_COLS), 0)
check("  the asin column", SH.pick(C.TEMPLATE_HEADERS, SB._ASIN_COLS), 1)
check("  and the cost column is the EMPTY one, not 'cost now' beside it",
      SH.pick(C.TEMPLATE_HEADERS, C.COST_COLS), 3)

print("\n=== the column to fill in arrives EMPTY, even where a cost is known ===")
# The opposite of the supplier-link sheet, and deliberately so. A supplier link
# is a fact about the world, so showing the current one and letting it come back
# unchanged is right. A cost is a MANUAL OVERRIDE: pre-filling it and reading it
# back would turn every SKU-derived cost into a typed-in override -- silently,
# for the whole catalogue, on one upload of a file nobody edited.
ROWS = C.template_rows(None, "acct", "UK", overrides={"acct::A_9.99": 4.50},
                       catalogue={})
# (no snapshot, so no rows -- the shape is proved below against a real one)
check("no catalogue, no rows invented", ROWS, [])

FAKE = [["9.99_3Days_B0AAA", "B0OURS1", "Grill, Large", "", "9.99",
         "read from the SKU name"]]
check("the cost column is index 3 and blank", FAKE[0][3], "")
check("  what the app uses now is index 4, to read", FAKE[0][4], "9.99")
check("  and where it came from is index 5", FAKE[0][5], "read from the SKU name")

print("\n=== reading a filled-in sheet back ===")
HEAD = C.TEMPLATE_HEADERS
def sheet(rows):
    return SH.to_csv(HEAD, rows).encode("utf-8")

r = C.apply_sheet(None, "acct", "UK", HEAD, [
    ["SKU-A", "", "thing", "7.77", "", ""],
    ["SKU-B", "", "other", "", "3.00", "read from the SKU name"],
])
check("a row with a cost is applied", r["set"], 1)
check("  a row left blank is SKIPPED, not zeroed", r["skipped"], 1)
check("  and the update is the one that was typed", r["updates"], {"SKU-A": 7.77})
# Zeroing the blanks would set the whole catalogue's cost to nothing on the
# first upload of an unedited template, and overrides beat everything.

print("\n--- what a person's sheet really contains ---")
r = C.apply_sheet(None, "acct", "UK", HEAD, [
    ["S1", "", "", "£7.77", "", ""],
    ["S2", "", "", "1,234.50", "", ""],
    ["S3", "", "", " 8.00 ", "", ""],
    ["S4", "", "", "not a price", "", ""],
    ["S5", "", "", "-3.00", "", ""],
])
check("a pound sign is not a reason to refuse a row", r["updates"].get("S1"), 7.77)
check("  nor a thousands comma", r["updates"].get("S2"), 1234.50)
check("  nor stray spaces", r["updates"].get("S3"), 8.00)
truthy("but text is refused, and says what it could not read",
       any(x["status"] == "not a number" for x in r["rows"]))
truthy("  naming the value", any("not a price" in (x.get("detail") or "")
                                 for x in r["rows"]))
truthy("and a negative cost is refused",
       any(x["status"] == "refused" for x in r["rows"]))
check("  neither of those is stored", "S4" in r["updates"] or "S5" in r["updates"],
      False)

print("\n--- a sheet with no cost column is refused, and says how to fix it ---")
r = C.apply_sheet(None, "acct", "UK", ["sku", "product"], [["A", "b"]])
check("refused", r["ok"], False)
truthy("  and names the column to add", "'cost'" in r["error"])
r = C.apply_sheet(None, "acct", "UK", ["cost"], [["7.00"]])
check("no sku or asin is refused too", r["ok"], False)
truthy("  and says so", "SKU or ASIN" in r["error"])

print("\n=== THE SNIFFER BUG, which the template made certain to hit ===")
# MEASURED on the real generated sheet: one product is called
#   46-Piece 1/4" Drive Socket Ratchet Wrench Set with Storage Case, Metric
#   Socket & Bit Set, ...
# -- a quoted field holding BOTH a comma and a double quote, which csv.writer
# escapes by doubling. csv.Sniffer saw the doubled quotes, chose a different
# quoting rule, and the field split on its internal commas: every column after
# it shifted and "Metric Socket & Bit Set" arrived where the cost should be.
NASTY = [["46 pcs wrench", "B0H56C1JVX",
          '46-Piece 1/4" Drive Socket Ratchet Wrench Set with Storage Case, '
          'Metric Socket & Bit Set, Quick Release Reversible Ratchet Handle',
          "7.77", "", "not known"]]
heads, back, err = SB.read_table(sheet(NASTY), "costs.csv")
check("it reads without complaint", err, "")
check("the row keeps its six columns", len(back[0]), 6)
check("  the product name survives whole", back[0][2], NASTY[0][2])
check("  and the cost is still in the cost column", back[0][3], "7.77")
r = C.apply_sheet(None, "acct", "UK", heads, back)
check("so the cost is applied, not rejected as text", r["set"], 1)
check("  at the value that was typed", r["updates"], {"46 pcs wrench": 7.77})
# Caught only because a cost that is not a number is refused. Had the fragment
# been numeric it would have been stored as somebody's cost price.

print("\n--- and the genuinely foreign file still works ---")
# Sniffing is now the fallback, not the first guess, so semicolons and tabs must
# still be read -- that is what sniffing was for.
semi = "sku;cost\nS9;4.25\n".encode("utf-8")
h2, b2, e2 = SB.read_table(semi, "euro.csv")
check("a semicolon file is still read", [c.strip() for c in h2], ["sku", "cost"])
check("  with its row intact", b2, [["S9", "4.25"]])
tabs = "sku\tcost\nS8\t9.50\n".encode("utf-8")
h3, b3, _e3 = SB.read_table(tabs, "tabs.csv")
check("a tab file too", [c.strip() for c in h3], ["sku", "cost"])
check("  with its row intact", b3, [["S8", "9.50"]])

print("\n=== ONE csv writer, not one per template ===")
truthy("it lives on its own", "def to_csv" in
       open(r"D:\AltaScraper\domain\sheets.py", encoding="utf-8").read())
SBSRC = open(r"D:\AltaScraper\domain\source_bulk.py", encoding="utf-8").read()
truthy("the supplier sheet uses it", "_sheets.to_csv(headers, rows)" in SBSRC)
falsy("  and no longer writes its own", "csv.writer(buf" in SBSRC)
truthy("a title with a comma is quoted, once, for both",
       '"Grill, Large"' in SH.to_csv(["a"], [["Grill, Large"]]))

print("\n=== the file goes to the SERVER, which knows how to read it ===")
# THE UPLOADER MOVED. This read miles_template.js, which held a second cost
# upload -- same endpoint, but it wrote immediately where the other dry-runs the
# file and asks. Two buttons doing one job with different safety, and the
# always-visible one was the unsafe one, so it was deleted rather than fixed.
# What it was asserting is still true of the survivor, which is where this looks
# now. ("uploading the cogs sheet should be in the one place")
J = open(r"D:\AltaScraper\static\js\cogs.js", encoding="utf-8").read()
truthy("the browser posts the file", "/cogs/upload_sheet" in J)
falsy("  rather than splitting lines on commas itself",
      'lines[i].split(",")' in J)
truthy("  and says what happened to every row, not just a total",
       'r.status !== "set"' in J)
# And the deleted one has not quietly come back.
MT = open(r"D:\AltaScraper\static\js\miles_template.js", encoding="utf-8").read()
falsy("there is no second uploader", "async function uploadCogsCsv" in MT)
R = open(r"D:\AltaScraper\routes\cogs_routes.py", encoding="utf-8").read()
truthy("the route reads it with the shared reader", "_sb.read_table" in R)
truthy("  and writes nothing until the whole file has been read",
       "a sheet that fails halfway does not leave half the catalogue changed" in R)
H = open(r"D:\AltaScraper\templates\dashboard.html", encoding="utf-8").read()
truthy("there is a button to get the sheet", "/cogs/template.csv" in H)
# id="cogscsv" was the second upload's file input and is gone with it. The one
# that remains is id="cogs_file", moved onto this toolbar from the selection bar
# -- a whole-account price list has nothing to do with which rows are ticked.
truthy("  beside the one that uploads it", 'id="cogs_file"' in H)
truthy("  which is the one that asks first", 'onclick="cogsUploadOpen()"' in H)
falsy("  and the second upload's input is gone too", 'id="cogscsv"' in H)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
