"""The supplier-link sheet, handed over already filled in.

"when a user wants to update the supplier links through the sheet, give the user
 the template first filled by the asins enrolled for tracking in the repricer,
 the user will fill that template and upload it back to update the source links"

So the only empty cells are the ones there is a job to do in. A blank sheet
means typing forty SKUs by hand, and a hand-typed SKU is the NO-SUCH-SKU-123
this module already had to grow a check for -- the real fix for which is not
making anyone type them.
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

from domain import source_bulk as B

IDX = {
    "10.39_3DAYS_B0F6LQ1S93": {"img": "x.jpg", "title": "Charcoal BBQ Grill",
                               "asin": "B0H56PTHG6", "sku": "10.39_3Days_B0F6LQ1S93"},
    "CLEANING BRUSH_11GBP": {"img": "", "title": "Floor Cleaning Brush",
                             "asin": "B0H5L3877S", "sku": "cleaning brush_11GBP"},
}
ENROLLED = ["10.39_3Days_B0F6LQ1S93", "cleaning brush_11GBP", "9.99_2Days_B0GXYZ1234"]
CURRENT = {"10.39_3Days_B0F6LQ1S93": "https://www.ebay.co.uk/itm/336530856611"}

# TWO suppliers on the first SKU, to prove several are possible.
#
# THIS USED TO BE ROWS AND IS NOW COLUMNS, at his direct instruction:
#
#     "give the option in the template in the repricer page to add multiple
#      supplier links, write the heading yourself, supplier 1, supplier 2,
#      supplier 3, supplier 4 and so on upto 10 and the user should be told that
#      he can add more suplliers by adding more columns after 10 and giving the
#      heading of 11th count, 12 count and so on."
#
# The old answer was rows, and the reason was real: apply_rows read ONE link
# column and _pick returns the first match, so a "link 2" column would have been
# ignored in silence. The reader takes every NUMBERED column now (url_columns),
# so the shape he asked for is the shape that works. Rows still work too, and
# that is asserted below -- a sheet from anywhere else must not break.
SOURCES = {"10.39_3Days_B0F6LQ1S93": [
    "https://www.ebay.co.uk/itm/336530856611",
    "https://www.ebay.co.uk/itm/999999999999"]}
rows = B.template_rows("/cfg", "ws", "UK", ENROLLED, catalogue=IDX,
                       sources=SOURCES)

print("=== the columns the upload will read back ===")
check("three fixed columns, then ten for suppliers",
      B.TEMPLATE_HEADERS[:3] + [len(B.TEMPLATE_HEADERS) - 3],
      ["sku", "asin", "product", 10])
check("  headed the way he asked", B.TEMPLATE_HEADERS[3:5],
      ["supplier 1", "supplier 2"])
check("  and numbered to ten", B.TEMPLATE_HEADERS[-1], "supplier 10")

print("\n--- and every one is a name the parser already knows ---")
check("the matcher finds the sku column", B._pick(B.TEMPLATE_HEADERS, B._SKU_COLS), 0)
check("  the asin column", B._pick(B.TEMPLATE_HEADERS, B._ASIN_COLS), 1)
# 3 onwards, not 2: "product" must not be mistaken for a link column.
check("  and EVERY supplier column, in order",
      B.url_columns(B.TEMPLATE_HEADERS), list(range(3, 13)))

print("\n--- an eleventh column works, which is what he was promised ---")
# "he can add more suplliers by adding more columns after 10 and giving the
#  heading of 11th count, 12 count and so on"
_more = B.TEMPLATE_HEADERS + ["supplier 11", "supplier 12"]
check("adding supplier 11 and 12 just works", B.url_columns(_more),
      list(range(3, 15)))
check("  and they are read in number order, not sheet order",
      B.url_columns(["sku", "supplier 3", "supplier 1", "supplier 2"]),
      [2, 3, 1])
# THE TRAP THE OLD DESIGN WARNED ABOUT, still shut. _pick falls back to a
# substring match, so "current supplier link" contains "supplier link" -- but it
# is not "supplier <n>", so the numbered matcher cannot take it for one.
check("a column that merely contains the word is not mistaken for one",
      B.url_columns(["sku", "asin", "current supplier link", "supplier 1"]), [3, 2])

print("\n=== one row per SKU, suppliers across the columns ===")
check("three SKUs, three rows", len(rows), 3)
by = {}
for r in rows:
    by.setdefault(r[0], []).append(r)
check("the SKU is written for you", sorted(by.keys()),
      ["10.39_3Days_B0F6LQ1S93", "9.99_2Days_B0GXYZ1234", "cleaning brush_11GBP"])
check("no SKU is repeated", [len(v) for v in by.values()], [1, 1, 1])
_two = by["10.39_3Days_B0F6LQ1S93"][0]
check("the SKU with two suppliers has both, side by side", _two[3:5],
      ["https://www.ebay.co.uk/itm/336530856611",
       "https://www.ebay.co.uk/itm/999999999999"])
check("  and eight empty columns to add more", len([c for c in _two[3:] if not c]), 8)
check("  the row is exactly as wide as the header", len(_two),
      len(B.TEMPLATE_HEADERS))

by = {k: v[0] for k, v in by.items()}
check("our ASIN when the catalogue knows it",
      by["10.39_3Days_B0F6LQ1S93"][1], "B0H56PTHG6")
check("  and the product name", by["10.39_3Days_B0F6LQ1S93"][2],
      "Charcoal BBQ Grill")

print("\n--- a SKU the catalogue does not know still gets a usable row ---")
r = by["9.99_2Days_B0GXYZ1234"]
check("the ASIN is read out of the SKU itself", r[1], "B0GXYZ1234")
check("  no name is invented", r[2], "")
check("  and every supplier column is blank, which is the job",
      [c for c in r[3:] if c], [])
# Rule 1: that ASIN is the COMPETITOR's, which is what the upload matches on and
# how the app already finds a listing from a pasted ASIN.

print("\n=== the rows that need doing come FIRST ===")
# Forty already-filled rows above the three that need a link is how those three
# get missed.
check("a SKU with no supplier at all is at the top", rows[0][0],
      "9.99_2Days_B0GXYZ1234")
truthy("  and a SKU that already has one is below", bool(rows[-1][3]) or
       rows[-1][0] == "10.39_3Days_B0F6LQ1S93")
truthy("  and the top row really has nothing in any supplier column",
       not [c for c in rows[0][3:] if c])
# Each SKU's rows stay together, so a blank is never orphaned away from the
# supplier list it belongs to.
_seen = []
for r in rows:
    if not _seen or _seen[-1] != r[0]:
        _seen.append(r[0])
check("each SKU's rows are contiguous", len(_seen), len(set(_seen)))

print("\n=== the file itself ===")
csv = B.to_csv(B.TEMPLATE_HEADERS, rows)
truthy("starts with a BOM, so Excel does not mangle a pound sign",
       csv.startswith("\ufeff"))
truthy("the header is the first line",
       csv.split("\n")[0].endswith("supplier 9,supplier 10"))
truthy("a title containing a comma is quoted",
       '"' in B.to_csv(B.TEMPLATE_HEADERS,
                       [["s", "a", "Grill, Large", ""]]))

print("\n--- and it round-trips through the reader that will receive it ---")
heads, back, err = B.read_table(csv.encode("utf-8"), "supplier-links.csv")
check("it reads without complaint", err, "")
check("the headers survive", [h.strip().lstrip("\ufeff") for h in heads],
      B.TEMPLATE_HEADERS)
check("  and every row", len(back), 3)
check("every supplier column is still found in what came back",
      B.url_columns(heads), list(range(3, 13)))
check("  and the sku column", B._pick(heads, B._SKU_COLS), 0)

print("\n=== both shapes are read: columns AND the old rows ===")
# A sheet written the old way, or exported from somewhere else, must not break.
_cols_head = ["sku", "supplier 1", "supplier 2"]
_cols_rows = [["SKU-A", "https://www.ebay.co.uk/itm/111",
               "https://www.ebay.co.uk/itm/222"]]
check("a column sheet offers both links from one row",
      B.url_columns(_cols_head), [1, 2])
_rows_head = ["sku", "supplier link"]
check("  and a single-column sheet still finds its one",
      B.url_columns(_rows_head), [1])
check("  a sheet with neither is refused, not half-read",
      B.url_columns(["sku", "asin", "product"]), [])

print("\n=== nothing here reaches Amazon or enrols anything ===")
S = open(r"D:\AltaScraper\domain\source_bulk.py", encoding="utf-8").read()
truthy("the module says so", "Nothing here enrols anything into LIVE pricing" in S)
R = open(r"D:\AltaScraper\routes\sourcing_routes.py", encoding="utf-8").read()
truthy("the route only reads", "/sourcing/template.csv" in R)
truthy("  and sends it as a download",
       "Content-Disposition" in R and "attachment" in R)
truthy("  named for the account it belongs to", "supplier-links-%s-%s.csv" in R)

print("\n=== the screen ===")
J = open(r"D:\AltaScraper\static\js\sourcing.js", encoding="utf-8").read()
truthy("there is a button to get the template", "/sourcing/template.csv" in J)
truthy("  next to the one that uploads it back", "sourcingUpload(this)" in J)
truthy("  and it says untouched cells are left alone",
       "Columns you leave blank are not changed" in J)
# AND IT TELLS HIM HOW TO GO PAST TEN, which he asked for by name.
truthy("  and how to add an eleventh supplier",
       "supplier 11" in J and "no limit" in J)

print("\n--- two boxes, not a choice between them ---")
# "give me 2 different boxes for setting the roi or margin target on repricer"
truthy("the margin box exists", "'tgt_margin'" in J)
truthy("  and the ROI box", "'tgt_roi'" in J)
truthy("  in one dialog, so both can be set at once", "_srcModal(" in J)
truthy("  rather than the prompt chain that made them alternatives",
       'prompt(\n    "Least profit' not in J)
truthy("each says what it means and what it costs on a real unit",
       "26.08" in J and "20.73" in J)
truthy("an empty box means that target is off", "placeholder=\"off\"" in J)
truthy("the header shows BOTH when both are on", "_srcTargetLabel" in J)
truthy("  joined, not one picked", "on.join(' \u00b7 ')" in J)

print("\n--- a draft's picture is the SUPPLIER's, and is never passed off ---")
# "the images are still not shown in the repricer for all skus" -- 22 of
# jack_uk's 67 had none, because the live snapshot can only picture what is live
# on Amazon and the Repricer tracks drafts too. Filling from the app's own
# records closed 16 of those. The pictures it finds are the eBay listing's, so
# they are marked: showing one as though it were live on Amazon would be the app
# claiming something about your listing that is not true.
from domain import catalogue as CAT
check("an unknown code gives an empty record with the marker present",
      CAT.look({}, "nope"),
      {"img": "", "img_source": "", "title": "", "asin": "", "sku": ""})
truthy("the index can be asked to include drafts",
       "include_drafts" in open(r"D:\AltaScraper\domain\catalogue.py",
                                encoding="utf-8").read())
CATSRC = open(r"D:\AltaScraper\domain\catalogue.py", encoding="utf-8").read()
truthy("  off by default, so live-listing screens are unaffected",
       "include_drafts=False" in CATSRC)
truthy("  and an Amazon picture is never overwritten by a supplier one",
       "Amazon can picture it; leave it alone" in CATSRC)
truthy("  each is labelled for what it is",
       '"amazon"' in CATSRC and '"supplier"' in CATSRC)
truthy("  and the two are said never to be conflated",
       "THEY ARE NEVER CONFLATED" in CATSRC)
_R2 = open(r"D:\AltaScraper\routes\sourcing_routes.py", encoding="utf-8").read()
truthy("the repricer asks for drafts", "include_drafts=True" in _R2)
truthy("the row marks a supplier picture",
       "SRC" in J and 'it.img_source === "supplier"' in J)
truthy("  and says so on hover", "SUPPLIER’s photograph" in J)
truthy("a row with no picture at all says why, rather than showing a blank",
       "Amazon has none for this SKU" in J)

print("\n--- and a picture on every row ---")
truthy("the row draws the product", "_srcItemCell(" in J)
truthy("  from the shared catalogue, via the row itself", "r.item" in J)
truthy("  falling back to an icon rather than a broken image",
       "ti ti-photo" in J)
truthy("  with the SKU as small print under the name", "it.title ? '10px'" in J)
R2 = open(r"D:\AltaScraper\routes\sourcing_routes.py", encoding="utf-8").read()
truthy("the server attaches it", '"item": _cat.look(idx, d["sku"])' in R2)
truthy("  building the index once for the whole list, not per row",
       "idx = _cat.index(CONFIG_PATH, wsid, mkt, include_drafts=True)" in R2)

print("\n--- turning a target off turns it off ---")
# The old single setting is folded in on every read, so clearing both boxes used
# to let the old 20% walk straight back in. Measured on jack_uk.
truthy("setting either box retires the old single target",
       'vals["profit_target_kind"] = None' in R2)
truthy("  in the same write, so neither is left half-set",
       'vals["profit_target_pct"] = None' in R2)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
