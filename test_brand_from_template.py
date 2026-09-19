"""The brand typed in the template is the brand the listing goes out under.

    "i wrote the brand name as Gregvilo in the template and downloaded it back
     in the app for listing generation but when the listing generated it shows
     my brand name as Nestwell Goods even though i did not put it there"

THE SWAP WAS REMOVED ON 8 SEP 2026 -- resolve_account_brand sends what was typed
and only reports when it is not on the account's list (test_brand_one_place.py).
It went on happening anyway, because the typed brand never reached that function.
It was lost at THREE separate hops, and any one of them alone would have been
enough to cause this:

  1. listing/queued_input.row_to_product built the generator's product from the
     stored row and left `brand` out of it
  2. ...and PRODUCT_KEYS left it out too, so even once (1) was fixed the temp
     JSON the subprocess reads would have dropped it again on the way back in
  3. amazon_listing_generator.process_row ran `if user_brand: chosen_brand =
     user_brand` -- and user_brand is the brand for the RUN, which for any run
     under a resolved account is the account's own trademark. So the account
     brand won before the row was ever consulted, and was then written onto the
     finished row, which is the value build_api_attributes later reads back.

The sheet path (read_input_sheet) had the same hole as (1).

This walks a product through every hop with the real code.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(p):
    with open(os.path.join(HERE, p), encoding="utf-8-sig") as f:
        return f.read()


from data import input_row as IR                      # noqa: E402
from listing import queued_input as QI                # noqa: E402

TYPED = "Gregvilo"
ACCOUNT = "Nestwell Goods"
PRODUCT = {"ebay_url": "https://www.ebay.co.uk/itm/123456789012",
           "competitor_asin": "B0HK1CTPSB",
           "item_name": "Portable Telescopic Folding Tool",
           "selling_price": "19.99", "source_cost": "8.00",
           "handling_time": "3", "brand": TYPED}

print("\n== hop 1: the upload writes it onto the queued row ==")
row, extras = IR.to_listing_row(PRODUCT, set())
check("the Brand column is stored as typed", row.get("Brand"), TYPED)
# A BLANK IS NOT A MISSING VALUE. It is the instruction to use the account's own
# brand, so the column must stay ABSENT rather than be written empty -- an empty
# string here would look like a deliberate "no brand" further down.
_blank, _ = IR.to_listing_row(dict(PRODUCT, brand=""), set())
check("  a row that named no brand writes no Brand at all",
      "Brand" in _blank, False)
yes("  and the uploader recognises the column",
    "brand" in IR.QUEUE_COLUMNS)

print("\n== hop 2: the queued row reaches the generator with it ==")
STORED = {"sku": extras["sku"], "source_url": PRODUCT["ebay_url"],
          "competitor_asin": "B0HK1CTPSB", "title": PRODUCT["item_name"],
          "our_price": "19.99", "handling_time": "3", "brand": TYPED}
prod = QI.row_to_product(STORED)
check("the product handed to the generator carries it", prod.get("brand"), TYPED)
check("  a row with no brand carries a blank, not a missing key",
      QI.row_to_product(dict(STORED, brand="")).get("brand"), "")

print("\n== hop 3: it survives the temp file the subprocess reads ==")
# read_products rebuilds each product from PRODUCT_KEYS and drops anything not in
# it, so hop 2 alone would have changed nothing.
yes("brand is one of the keys that survive", "brand" in QI.PRODUCT_KEYS)
path = QI.write_temp_input([prod])
try:
    back = QI.read_products(path)
finally:
    os.unlink(path)
check("and it is still there on the other side",
      (back or [{}])[0].get("brand"), TYPED)

print("\n== hop 4: the row's brand outranks the run's ==")
G = read("amazon_listing_generator.py")
_sel = G[G.index("# --- Brand selection per product"):]
_sel = _sel[:_sel.index("# --- Model Number")]
yes("the row is asked first", 'row_brand = str(row.get("brand", "") or "").strip()' in _sel)
yes("  through the one function that decides whose brand goes out (Rule 12)",
    "resolve_account_brand(row_brand, config)" in _sel)
yes("  and the run's brand is now the FALLBACK, not the winner",
    "elif user_brand:" in _sel)
check("  the unconditional override is gone",
      re.search(r"^\s*if user_brand:\s*$", _sel, re.M) is not None, False)
# The note must still be printed: a brand that is not on the account's list looks
# exactly like a leaked one, and saying so is the whole of what survived the
# 8 Sep change.
yes("  a brand not on the account's list is still announced",
    "_row_brand_note" in _sel)

print("\n== the sheet path had the same hole ==")
_rd = G[G.index("def read_input_sheet"):]
_rd = _rd[:_rd.index("# A ROW NEEDS A SOURCE")]
yes("read_input_sheet carries the sheet's Brand column too",
    '"brand":' in _rd)

print("\n== and the fallback is untouched ==")
import amazon_listing_generator as _G                 # noqa: E402
CFG = {"_account_brand": ACCOUNT, "_account_brands": [ACCOUNT],
       "brand_name": "SomeGlobalLeftover"}
got, note = _G.resolve_account_brand(TYPED, CFG)
check("a typed brand goes out as typed", got, TYPED)
yes("  with the note that it is not on the account's list", note)
check("a row that named none still uses the account's own brand",
      _G.resolve_account_brand("", CFG)[0], ACCOUNT)
# THE LEAK THAT MUST NOT COME BACK: the global config brand is never borrowed for
# a blank row once an account is resolved. That is a different fault from this
# one and its guard lives in the same function.
check("  and never the global config brand",
      _G.resolve_account_brand("", CFG)[0] == "SomeGlobalLeftover", False)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
