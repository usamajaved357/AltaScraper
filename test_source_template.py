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

rows = B.template_rows("/cfg", "ws", "UK", ENROLLED, catalogue=IDX, current=CURRENT)

print("=== the columns the upload will read back ===")
check("four of them", B.TEMPLATE_HEADERS,
      ["sku", "asin", "product", "supplier link"])
# ONE link column, not a current/new pair. That pair is the obvious design and
# it is a trap: _pick falls back to a substring match, "current supplier link"
# contains "supplier link", and it comes first -- so the upload would have
# re-applied the OLD links and silently ignored every new one just typed.
check("only one of them is a link column",
      len([h for h in B.TEMPLATE_HEADERS if "link" in h]), 1)

print("\n--- and every one is a name the parser already knows ---")
for i, (h, wanted) in enumerate((("sku", B._SKU_COLS), ("asin", B._ASIN_COLS),
                                 ("supplier link", B._URL_COLS))):
    truthy("%-16s is matched" % h, h in wanted)
# Proved against the real matcher, not by eye: a header the parser misses turns
# a working file into "no supplier link column found".
check("the matcher finds the sku column", B._pick(B.TEMPLATE_HEADERS, B._SKU_COLS), 0)
check("  the asin column", B._pick(B.TEMPLATE_HEADERS, B._ASIN_COLS), 1)
check("  and the link column", B._pick(B.TEMPLATE_HEADERS, B._URL_COLS), 3)
# 3, not 2: "product" must not be mistaken for anything.

print("\n=== a row per enrolled SKU, filled in ===")
check("one for each", len(rows), 3)
by = {r[0]: r for r in rows}
check("the SKU is written for you", sorted(by.keys()),
      ["10.39_3Days_B0F6LQ1S93", "9.99_2Days_B0GXYZ1234", "cleaning brush_11GBP"])
check("our ASIN when the catalogue knows it",
      by["10.39_3Days_B0F6LQ1S93"][1], "B0H56PTHG6")
check("  and the product name", by["10.39_3Days_B0F6LQ1S93"][2],
      "Charcoal BBQ Grill")
check("  and the link it already has",
      by["10.39_3Days_B0F6LQ1S93"][3],
      "https://www.ebay.co.uk/itm/336530856611")

print("\n--- a SKU the catalogue does not know still gets a usable row ---")
r = by["9.99_2Days_B0GXYZ1234"]
check("the ASIN is read out of the SKU itself", r[1], "B0GXYZ1234")
check("  no name is invented", r[2], "")
check("  and the link is blank, which is the job", r[3], "")
# Rule 1: that ASIN is the COMPETITOR's, which is what the upload matches on and
# how the app already finds a listing from a pasted ASIN.

print("\n=== the rows that need doing come FIRST ===")
# Forty already-filled rows above the three that need a link is how those three
# get missed.
check("the blank one is at the top", rows[0][0], "9.99_2Days_B0GXYZ1234")
truthy("  and the filled ones below it", bool(rows[-1][3]))

print("\n=== the file itself ===")
csv = B.to_csv(B.TEMPLATE_HEADERS, rows)
truthy("starts with a BOM, so Excel does not mangle a pound sign",
       csv.startswith("\ufeff"))
truthy("the header is the first line",
       csv.split("\n")[0].endswith("sku,asin,product,supplier link"))
truthy("a title containing a comma is quoted",
       '"' in B.to_csv(B.TEMPLATE_HEADERS,
                       [["s", "a", "Grill, Large", ""]]))

print("\n--- and it round-trips through the reader that will receive it ---")
heads, back, err = B.read_table(csv.encode("utf-8"), "supplier-links.csv")
check("it reads without complaint", err, "")
check("the headers survive", [h.strip().lstrip("\ufeff") for h in heads],
      B.TEMPLATE_HEADERS)
check("  and every row", len(back), 3)
check("the link column is still found in what came back",
      B._pick(heads, B._URL_COLS), 3)
check("  and the sku column", B._pick(heads, B._SKU_COLS), 0)

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
truthy("  and it says untouched rows are left alone",
       "Rows you leave" in J and "not changed" in J)

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

print("\n--- and a picture on every row ---")
truthy("the row draws the product", "_srcItemCell(" in J)
truthy("  from the shared catalogue, via the row itself", "r.item" in J)
truthy("  falling back to an icon rather than a broken image",
       "ti ti-photo" in J)
truthy("  with the SKU as small print under the name", "it.title ? '10px'" in J)
R2 = open(r"D:\AltaScraper\routes\sourcing_routes.py", encoding="utf-8").read()
truthy("the server attaches it", '"item": _cat.look(idx, d["sku"])' in R2)
truthy("  building the index once for the whole list, not per row",
       "idx = _cat.index(CONFIG_PATH, wsid, mkt)" in R2)

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
