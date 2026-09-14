# -*- coding: utf-8 -*-
"""A queued row reaches the generator WITH its Amazon ASIN.

    "why am i seeing that error on almost all of my listings"
    (Amazon: "your product type has been updated from HOME to TABLE")
    "but i did not asked to ignore amazon, why is it happening from aug 29"

MEASURED on 8.59_2Days_B0DNYVCK4J: Amazon's catalogue says B0DNYVCK4J is TABLE.
The generator never asked. listing/queued_input.row_to_product hands a queued
row over with amazon_url="" and the ASIN in competitor_asin -- the listings
table has no Amazon-URL column -- and process_row read ONLY amazon_url. So the
ASIN came out blank, the catalogue was skipped, and infer_product_type fell
back to HOME from the title. Since 29 Aug 2026 (e62dfcb, "one table"), every
upload / "Add a product" row generated with no Amazon source.

These checks RUN the hand-off; they do not grep for it.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(name, got, want):
    if got == want:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s   got=%r want=%r" % (name, got, want))
        FAILS.append(name)


from listing import queued_input as Q
from data.input_row import resolved_asin
import amazon_listing_generator as G

print("== the queued row, through the real temp-file hand-off ==")
store_row = {"sku": "8.59_2Days_B0DNYVCK4J", "competitor_asin": "B0DNYVCK4J",
             "title": "Folding Camping Table Lightweight Aluminium Portable Picnic 40x34cm",
             "source_url": "https://www.ebay.co.uk/itm/336636956670"}
path = Q.write_temp_input([Q.row_to_product(store_row)])
try:
    product = Q.read_products(path)[0]
finally:
    os.remove(path)
check("the link is still empty (no column for it)", product["amazon_url"], "")
check("the ASIN survives the hand-off", product["competitor_asin"], "B0DNYVCK4J")
check("and it is the ASIN the generator resolves", resolved_asin(product), "B0DNYVCK4J")

print("\n== process_row asks the shared resolver, not the link alone ==")
import inspect
src = inspect.getsource(G.process_row)
check("comp_asin comes from resolved_asin", "comp_asin     = resolved_asin(row)" in src, True)
check("  and no longer from the link only", "_extract_asin(amazon_url)" in src, False)

print("\n== a sheet row with only a link still works ==")
sheet = {"amazon_url": "https://www.amazon.co.uk/x/dp/B00TKIAZWG/ref=sr_1", "ebay_url": ""}
check("ASIN read from the link", resolved_asin(sheet), "B00TKIAZWG")
check("_extract_asin still reads a link", G._extract_asin(sheet["amazon_url"]), "B00TKIAZWG")
check("  and a junk link invents nothing", G._extract_asin("https://amazon.co.uk/s?k=x"), "")

print("\n== choosing one queued row by ASIN finds it ==")
got, err = G.select_rows([product], "B0DNYVCK4J", "asin")
check("bare ASIN selects the queued row", (len(got), err), (1, ""))
got, err = G.select_rows([product], "https://www.amazon.co.uk/dp/B0DNYVCK4J", "auto")
check("pasted Amazon link selects it too", (len(got), err), (1, ""))

print()
if FAILS:
    print("FAILED: %d" % len(FAILS))
    sys.exit(1)
print("all passed")
