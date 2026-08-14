"""An eBay seller's catalogue: found, reviewed, screened, drafted.

Two things here are easy to get wrong and both are expensive.

A partial sweep presented as a whole catalogue -- eBay has no "list this
seller's inventory" call, so what comes back is what several searches found, and
saying "366 items" instead of "found 366" is how items go missing with nobody
noticing they did.

And a failed check read as a pass. Every screen returns None for "could not
tell", and None must become UNKNOWN, never CLEAR -- otherwise a blocked product
reaches the submit queue with the AI spend already gone.
"""
import sys
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

from domain import seller_import as SI

# Shaped exactly as the live Browse API returned it (probed 14 Aug 2026).
SUMMARY = {
    "legacyItemId": "336583300060",
    "itemId": "v1|336583300060|0",
    "title": "Apple iPad Air (M2) 13 Inch Smart Folio Tablet Case",
    "image": {"imageUrl": "https://i.ebayimg.com/x.jpg"},
    "price": {"value": "77.99", "currency": "GBP"},
    "condition": "New",
    "itemWebUrl": "https://www.ebay.co.uk/itm/336583300060",
    "epid": "12345",
    "categories": [{"categoryName": "Computers"}, {"categoryName": "Tablet Cases"}],
    "shippingOptions": [{"shippingCost": {"value": "3.95", "currency": "GBP"}}],
}

print("=== a search result becomes a row you can look at ===")
r = SI.to_review_row(SUMMARY)
check("the id is the legacy numeric one the rest of the app uses",
      r["item_id"], "336583300060")
check("title", r["title"], SUMMARY["title"])
check("the MAIN IMAGE, which is the point of the review grid",
      r["image"], "https://i.ebayimg.com/x.jpg")
check("price", r["price"], 77.99)
check("postage separately, not folded into the price", r["shipping"], 3.95)
check("the leaf category, not the top one", r["category"], "Tablet Cases")
check("ticked by default -- you untick what you do not want", r["selected"], True)
check("not a variation family", r["is_group"], False)

print("  -- an image can hide in the thumbnails --")
r2 = SI.to_review_row(dict(SUMMARY, image=None,
                           thumbnailImages=[{"imageUrl": "https://t/1.jpg"}]))
check("falls back rather than showing a blank tile", r2["image"], "https://t/1.jpg")
check("and an item with no image at all is not a crash",
      SI.to_review_row({"legacyItemId": "1"})["image"], "")

print("  -- a variation listing is recognised, not flattened --")
grp = SI.to_review_row(dict(SUMMARY, itemGroupType="SELLER_DEFINED_VARIATIONS",
                            itemGroupHref="https://api/x"))
check("marked as a family", grp["is_group"], True)
truthy("  and keeps the link to its children", grp["group_href"])

print("\n=== what a unit costs us ===")
check("item plus the postage TO US", SI.landed_cost(r), 81.94)
check("unknown postage is NOT free postage",
      SI.landed_cost(dict(r, shipping=None)), None)
check("  nor is an unknown price", SI.landed_cost(dict(r, price=None)), None)

print("\n=== screening, before a single draft is made ===")
check("nothing to say -> clear", SI.screen_one(r)["verdict"], SI.CLEAR)

print("  -- Amazon's own answer outranks everything --")
blocked = SI.screen_one(r, restriction_lookup=lambda _r: {
    "blocked": True, "reasons": ["You need approval to sell in Grocery."]})
check("blocked", blocked["verdict"], SI.BLOCKED)
truthy("  carrying Amazon's words", "approval to sell" in blocked["notes"][0])
check("not blocked -> clear",
      SI.screen_one(r, restriction_lookup=lambda _r: {"blocked": False})["verdict"],
      SI.CLEAR)

print("  -- a check that could not run is UNKNOWN, never clear --")
u = SI.screen_one(r, restriction_lookup=lambda _r: None)
check("verdict", u["verdict"], SI.UNKNOWN)
truthy("  and says it could not be asked", "could not be asked" in u["notes"][0])
boom = SI.screen_one(r, restriction_lookup=lambda _r: (_ for _ in ()).throw(RuntimeError("x")))
check("a check that THREW is unknown too, not a crash", boom["verdict"], SI.UNKNOWN)

print("  -- our own rules --")
check("a restricted product type",
      SI.screen_one(r, restricted_type=lambda _r: {"blocked": True,
                                                   "message": "no"})["verdict"],
      SI.BLOCKED)
check("  a type worth a look but not blocked",
      SI.screen_one(r, restricted_type=lambda _r: {"blocked": False,
                                                   "message": "check"})["verdict"],
      SI.CAUTION)
d = SI.screen_one(r, compliance=lambda _r: {"docs": True,
                                            "message": "Needs a safety data sheet."})
check("paperwork is flagged BEFORE the money is spent", d["verdict"], SI.DOCS)
truthy("  saying which", "safety data sheet" in d["notes"][0])

print("  -- the worst answer wins, it is not averaged away --")
both = SI.screen_one(r, restriction_lookup=lambda _r: {"blocked": True, "reasons": ["no"]},
                     compliance=lambda _r: {"docs": True, "message": "papers"})
check("blocked beats docs", both["verdict"], SI.BLOCKED)
check("  and both reasons are kept", len(both["notes"]), 2)

print("\n=== a batch reports the worst thing in it ===")
rows = [dict(r, item_id="1"), dict(r, item_id="2"), dict(r, item_id="3")]
def only_two_blocked(x):
    return {"blocked": x["item_id"] == "2", "reasons": ["nope"]}
out, summ = SI.screen(rows, restriction_lookup=only_two_blocked)
check("every row keeps its own verdict",
      [x["screen"]["verdict"] for x in out], [SI.CLEAR, SI.BLOCKED, SI.CLEAR])
check("the summary counts them", summ["counts"][SI.BLOCKED], 1)
check("  and says how many could be drafted", summ["draftable"], 2)
check("  and reports the WORST, not the commonest", summ["worst"], SI.BLOCKED)
_o, s2 = SI.screen(rows)
check("an all-clear batch says so", s2["worst"], SI.CLEAR)

print("\n=== drafting ===")
d = SI.to_draft(r, account_id="jack_uk", marketplace="UK")
check("the SKU carries the cost, in the format the whole app already reads",
      d["sku"], "81.94_3Days_336583300060")
from domain import cogs as C
check("  so cost of goods reads it back with no special case",
      C.cost_from_sku(d["sku"]), 81.94)
check("it records where it came from", d["_source"]["item_id"], "336583300060")
check("  and the link", d["source_url"], SUMMARY["itemWebUrl"])
import json as _j
check("  the image, in attributes_json where the app actually reads it",
      _j.loads(d["attributes_json"])["main_product_image_locator"], r["image"])
check("  and the platform it came from", d["platform"], "ebay")
check("  the title, under the name the STORE knows", d["title"], SUMMARY["title"])
check("  and the handling days that went into the SKU", d["handling_days"], 3)
# The store writes what it recognises and drops the rest without a word, so a
# key of our own invention would arrive as a blank column and no error.
from data import column_map as _CM
_known = set((_CM.HEADER_TO_COL or {}).values()) | set(_CM.INTERNAL_COLS or [])
_unknown = [k for k in d if not k.startswith("_") and k not in _known]
check("every key we write is one the store actually has", _unknown, [])
check("NOTHING is approved by arriving", d["status"], "NEEDS_REVIEW")
check("an unknown cost does not become a free product",
      SI.to_draft(dict(r, shipping=None), account_id="a", marketplace="UK")["sku"],
      "0.00_3Days_336583300060")
check("  and 0.00 is read back as UNKNOWN, not as free",
      C.cost_from_sku("0.00_3Days_336583300060"), None)

print("\n=== the sweep never claims to be the whole catalogue ===")
from api import ebay as E
truthy("there is a term list to sweep with", len(E.SWEEP_TERMS) >= 5)
import inspect
src = inspect.getsource(E.search_seller)
truthy("the meta says it is not complete", '"complete": False' in src)
truthy("  and records which terms were used", 'meta["terms"]' in src)
truthy("  and keeps eBay's own reported total apart from what we found",
       "highest_reported_total" in src)
check("no seller, no calls", E.search_seller("", "a", "b")[0], [])

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
