# -*- coding: utf-8 -*-
"""An upload keeps the Amazon link, and the eBay photos survive the merge.

    "the drafted created have the sku format like 00_3Days_336636956670 and
     also i see no images shown in these drafts, what is the issue, i suspect
     we are off from our original track of creating drafts"

    "images was supposed to be coming from ebay why my draftws dont have images"

TWO SEPARATE LOSSES OF DATA, which is why nothing was left to show.

MEASURED on the file that produced those rows (product-queue-template.csv, 14
rows, uploaded 11 Sep 2026): every row had an ebay_url, supplier_2, supplier_3
AND an amazon_url. Every amazon_url was an ordinary /dp/ link and the shared
extractor reads an ASIN from all fourteen. Row 7 is B099NVTV5F -- the row whose
SKU came out as 0.00_3Days_336636956670.

ONE. THE UPLOAD THREW THE AMAZON LINK AWAY. build_queued_sku and to_listing_row
read `competitor_asin` and nothing else, so with no ASIN column the SKU fell
back to the eBay item id. The link was not stored either -- `listings` has no
Amazon-URL column and _write_extras drops the one in `extras` -- so by
generation time the generator's own _extract_asin(amazon_url) had nothing to
read. The reason is written in a comment in input_row.py: "The ASIN is NOT
derived here: input_import.add_row already fills competitor_asin from
amazon_url." True until the queue table was removed and the upload stopped going
through add_row. A comment cannot notice that its caller has moved.

TWO. THE SUPPLIER MERGE THREW THE EBAY PHOTOS AWAY. fetch_ebay_supplement
returns the eBay photo URLs as `images`, and the generator has read them since
July (comp_data["images"] = ebay_supp["images"][:5]). listing/suppliers.merge
arrived on 7 Sep 2026 -- five days before this upload -- and became the thing
handing that dict over. `images` was not in MERGE_KEYS, so the URLs were fetched
and dropped one step later, on every run, while image_count survived: a run
could log "7 imgs" over a draft with no pictures at all.

EITHER ONE ALONE AND THERE WOULD STILL HAVE BEEN IMAGES -- Amazon's via the
ASIN, or eBay's via the merge. Both at once is why the drafts were empty.

The SKU's 0.00 is NOT a bug and is not fixed here: that slot is the source cost,
it is read from the file, and the file left it blank. The template now says so.
"""
import os
import re
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


def truthy(name, got):
    check(name, bool(got), True)


def falsy(name, got):
    check(name, bool(got), False)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8") as fh:
        return fh.read()


# ===================================================================== images
print("== the eBay photos survive the merge ==")
from listing import suppliers as S

truthy("images is a merged key", "images" in S.MERGE_KEYS)

EBAY_PICS = ["https://i.ebayimg.com/1.jpg", "https://i.ebayimg.com/2.jpg"]
P1 = {"title": "Spin Mop Refill", "description": "", "price": "9.99",
      "condition": "New", "category_path": "",
      "item_specifics": {"Brand": "Unbranded"},
      "image_count": 2, "images": list(EBAY_PICS)}
merged, prov = S.merge([(1, "https://ebay/itm/1", P1)])
check("the URLs come out, not just a count", merged.get("images"), EBAY_PICS)
check("  and the count matches what is carried", merged.get("image_count"), 2)
# The generator reads exactly this key; if it is empty the draft has no pictures.
truthy("which is what the generator reads",
       'comp_data["images"] = ebay_supp["images"]' in read("amazon_listing_generator.py"))

print("\n  supplier 1's photos stand; a later seller only fills a gap")
P2 = {"title": "", "description": "d", "price": "", "condition": "",
      "category_path": "", "item_specifics": {}, "image_count": 5,
      "images": ["https://i.ebayimg.com/other.jpg"]}
m2, _ = S.merge([(1, "a://1", P1), (2, "a://2", P2)])
check("supplier 1's pictures win", m2.get("images"), EBAY_PICS)
NOPICS = dict(P1, images=[], image_count=0)
m3, _ = S.merge([(1, "a://1", NOPICS), (2, "a://2", P2)])
check("  supplier 2 supplies them when 1 had none",
      m3.get("images"), ["https://i.ebayimg.com/other.jpg"])
check("    and the count follows the pictures", m3.get("image_count"), 1)
check("  their source is traceable", (prov.get("images") or {}).get("supplier"), 1)

print("\n  a merge with no photos at all is unchanged")
BARE = {"title": "t", "description": "", "price": "1.00", "condition": "New",
        "category_path": "", "item_specifics": {}, "image_count": 7}
m4, _ = S.merge([(1, "a://1", BARE)])
check("no images key -> empty list, never None", m4.get("images"), [])
# test_suppliers.py pins this: the most any ONE seller had, never the sum.
check("  and image_count still reports the best seller's", m4.get("image_count"), 7)


# ======================================================================= ASIN
print("\n== the Amazon link in the file becomes the ASIN ==")
from data import input_row as IR

AMZ = ("https://www.amazon.co.uk/Kebuye-Alcohol-Based-Markers-Colours/dp/"
       "B099NVTV5F/ref=sr_1_16_sspa?dib=eyJ2IjoiMSJ9")
EBAY = "https://www.ebay.co.uk/itm/336636956670?_trkparms=amclksrc%3DITM"

check("the ASIN is read out of the link",
      IR.resolved_asin({"amazon_url": AMZ}), "B099NVTV5F")
check("  an explicit ASIN column still wins",
      IR.resolved_asin({"competitor_asin": "B0AAAAAAAA", "amazon_url": AMZ}),
      "B0AAAAAAAA")
check("  and a row with neither has none", IR.resolved_asin({"ebay_url": EBAY}), "")
check("  a junk link invents nothing",
      IR.resolved_asin({"amazon_url": "https://www.amazon.co.uk/s?k=markers"}), "")

# THE ROW ITSELF. The Amazon URL has no column on `listings`, so an ASIN not
# captured on this line is gone for good.
row, extras = IR.to_listing_row({"ebay_url": EBAY, "amazon_url": AMZ}, set())
check("the row stores the ASIN", row.get("Competitor ASIN"), "B099NVTV5F")
check("  and the SKU carries it, not the eBay id",
      row.get("SKU"), "0.00_3Days_B099NVTV5F")
falsy("  the eBay item id is no longer the name",
      "336636956670" in str(row.get("SKU")))

print("\n  the eBay fallback still works for a row with no Amazon link")
row2, _ = IR.to_listing_row({"ebay_url": EBAY}, set())
check("eBay id is used when there is nothing better",
      row2.get("SKU"), "0.00_3Days_336636956670")

print("\n  the cost still comes from the file, and only from the file")
row3, _ = IR.to_listing_row({"amazon_url": AMZ, "source_cost": "4.20",
                             "handling_time": "2"}, set())
check("source_cost becomes the first part of the SKU",
      row3.get("SKU"), "4.20_2Days_B099NVTV5F")


# =================================================================== template
print("\n== the template says where to put the source price ==")
UP = read("routes", "input_upload_routes.py")
truthy("source_cost is a column in the blank file", '"source_cost"' in UP)
truthy("  and it says what it is for", "WHAT YOU PAY THE SUPPLIER" in UP)
truthy("  that it becomes the SKU", "first part of the SKU" in UP)
truthy("  and that it cannot be corrected later",
       "never rewritten" in UP or "fixed when the row is created" in UP)
truthy("the Amazon link is asked for, with the reason",
       "amazon_url whenever you have it" in UP)


# =============================================== one extractor, not a fourth
print("\n== one ASIN extractor, not a fourth copy (Rule 12) ==")
SRC = read("data", "input_row.py")
truthy("input_row reuses input_import's", "from data.input_import import _asin_of" in SRC)
falsy("  and defines no regex of its own",
      bool(re.search(r"re\.(search|match)\([^)]*dp\b", SRC)))
truthy("build_queued_sku goes through it", "asin = resolved_asin(product)" in SRC)
truthy("to_listing_row goes through the same one",
       '"Competitor ASIN": resolved_asin(p)' in SRC)

print()
if FAILS:
    print("%d FAILED" % len(FAILS))
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("all checks passed")
