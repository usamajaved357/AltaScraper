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

print("\n=== a variation family is not one product ===")
# Shaped exactly as get_items_by_item_group returned it, probed 14 Aug 2026 on a
# real 104-child listing. The two numbers that matter:
#     104 children -> 1 distinct legacyItemId
#     104 children -> 104 distinct itemId
# and child prices running 9.99 to 23.49.
def _kid(var, colour, size, price, img):
    return {
        "itemId": "v1|223778867020|%s" % var,
        "legacyItemId": "223778867020",         # THE SAME ON EVERY CHILD
        "title": "Fruit of The Loom Mens T Shirts",
        "image": {"imageUrl": img},
        "price": {"value": price, "currency": "GBP"},
        "itemWebUrl": "https://www.ebay.co.uk/itm/223778867020?var=%s" % var,
        "shippingOptions": [{"shippingCost": {"value": "0.00", "currency": "GBP"}}],
        "estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK"}],
        "localizedAspects": [
            {"name": "Colour", "value": colour},
            {"name": "Size", "value": size},
            {"name": "Brand", "value": "Fruit of The Loom"},   # never varies
            {"name": "Garment Care", "value": "Machine Washable"},
        ],
    }

# Priced as the real one is: sizes of the same colour share a price, colours do
# not. That is what makes the listing id useless as a key -- 104 children over
# only 6 distinct prices.
GROUP = {"items": [
    _kid("522519025283", "Black", "S", "14.49", "https://i.ebayimg.com/b.jpg"),
    _kid("522519025284", "Black", "M", "14.49", "https://i.ebayimg.com/b.jpg"),
    _kid("522519025285", "Grey",  "L", "23.49", "https://i.ebayimg.com/g.jpg"),
]}
FAMILY_ROW = dict(SI.to_review_row({
    "legacyItemId": "223778867020",
    "itemGroupType": "SELLER_DEFINED_VARIATIONS",
    "itemGroupHref": ("https://api.ebay.com/buy/browse/v1/item/"
                      "get_items_by_item_group?item_group_id=223778867020"),
    "title": "Fruit of The Loom Mens T Shirts",
    "categories": [{"categoryName": "T-Shirts"}],
}))

truthy("a family is recognised as one", FAMILY_ROW["is_group"])
check("the group id comes out of the href",
      E.group_id_from_href(FAMILY_ROW["group_href"]), "223778867020")
check("  and a href without one gives nothing", E.group_id_from_href("x"), "")

print("\n--- which id actually tells the children apart ---")
check("the /itm/ id is the same for every child",
      len({k["legacyItemId"] for k in GROUP["items"]}), 1)
check("  so the ?var= id is the only thing that differs",
      E.variation_id_from_url(GROUP["items"][0]["itemWebUrl"]), "522519025283")
check("a plain item URL has no variation id",
      E.variation_id_from_url("https://www.ebay.co.uk/itm/223778867020"), "")
check("  and the listing id still reads off it",
      E.item_id_from_url(GROUP["items"][2]["itemWebUrl"]), "223778867020")
check("the full id is rebuilt from the two",
      E.full_item_id("223778867020", "522519025283"), "v1|223778867020|522519025283")
check("  a non-variation item ends in |0", E.full_item_id("223"), "v1|223|0")
check("  and split undoes it",
      E.split_item_id("v1|223778867020|522519025283"), ("223778867020", "522519025283"))
check("  |0 means 'no variation', not variation zero",
      E.split_item_id("v1|223|0"), ("223", ""))
check("  nonsense splits to nothing", E.split_item_id("223778867020"), ("", ""))

print("\n--- only what VARIES is a variation axis ---")
check("colour and size vary; brand and care instructions do not",
      SI.varying_aspects(GROUP["items"]), ["Colour", "Size"])
check("one child on its own varies by nothing",
      SI.varying_aspects(GROUP["items"][:1]), [])
theme, probs = SI.suggest_theme(["Colour", "Size"])
check("the UK spelling maps onto Amazon's axis names", theme, "COLOR/SIZE")
check("  with nothing to complain about", probs, [])
theme2, probs2 = SI.suggest_theme(["Colour", "Bundle Listing"])
check("an aspect with no Amazon axis is REPORTED, not silently dropped",
      len(probs2), 1)
truthy("  and it is named", "Bundle Listing" in probs2[0])
check("  the axes that do map are still used", theme2, "COLOR")
check("nothing mappable at all is a refusal, not an empty theme",
      SI.suggest_theme(["Bundle Listing"])[0], "")
# Against a real schema the theme must be one the product type ALLOWS (Rule 4).
check("the schema's own ordering wins over ours",
      SI.suggest_theme(["Colour", "Size"], allowed=["SIZE/COLOR", "COLOR"])[0],
      "SIZE/COLOR")
check("  and a type with no such theme is refused, not approximated",
      SI.suggest_theme(["Colour", "Size"], allowed=["SIZE", "COLOR"])[0], "")

print("\n--- the collision, shown rather than asserted ---")
# What keying children on the LISTING id does, run against the same fixture.
# The store upserts on SKU, so every collision here is a draft that silently
# overwrites another one -- no error, just fewer rows than variations.
_old = ["%.2f_3Days_%s" % (float(k["price"]["value"]), k["legacyItemId"])
        for k in GROUP["items"]]
_new = ["%.2f_3Days_%sv%s" % (float(k["price"]["value"]), k["legacyItemId"],
                              k["itemId"].split("|")[2]) for k in GROUP["items"]]
check("keyed on the listing id, two of these three collapse into one",
      len(set(_old)), 2)          # Black/S and Black/M become the same SKU
check("  because only the COST tells them apart, and sizes share a cost",
      _old[0] == _old[1], True)
check("keyed on the variation id, all three survive", len(set(_new)), 3)
# On the measured 104-child listing this is 104 children over 6 distinct prices:
# 98 drafts lost. In the shipped code it was worse still -- a family was drafted
# as ONE row, so 103 never existed at all.

exp = SI.expand_group(GROUP, FAMILY_ROW)
check("every variation came across", exp["count"], 3)
check("the family knows what it varies by", exp["theme"], "COLOR/SIZE")
kids = exp["children"]
check("each child gets its OWN id",
      len({k["item_id"] for k in kids}), 3)
check("  keyed on listing + variation", kids[0]["item_id"], "223778867020v522519025283")
check("each child keeps its own price", [k["price"] for k in kids],
      [14.49, 14.49, 23.49])
check("  and its own image, because the colour is what changed",
      [k["image"][-5:] for k in kids], ["b.jpg", "b.jpg", "g.jpg"])
check("  and a URL that names WHICH child",
      E.variation_id_from_url(kids[2]["url"]), "522519025285")
check("the category comes down from the family", kids[0]["category"], "T-Shirts")

drafts, fprobs = SI.family_drafts(exp, FAMILY_ROW, account_id="a", marketplace="UK")
check("one parent plus one draft per variation", len(drafts), 4)
check("THREE DISTINCT SKUS -- one row per family would have made one",
      len({d["sku"] for d in drafts[1:]}), 3)
check("  each carrying its own cost", sorted(d["sku"] for d in drafts[1:]),
      ["14.49_3Days_223778867020v522519025283",
       "14.49_3Days_223778867020v522519025284",
       "23.49_3Days_223778867020v522519025285"])
truthy("  and every one of them fits Amazon's SKU limit",
       all(len(d["sku"]) <= SI.SKU_MAX for d in drafts))

print("\n--- the screening verdict survives the expansion ---")
# A family is ONE product on eBay, so its verdict is every child's verdict. If
# it stayed on the parent alone it would sit on the one row nobody submits, and
# 104 children would each look clear.
_screened = dict(FAMILY_ROW, screen={"verdict": SI.DOCS,
                                     "notes": ["Amazon will demand a test certificate."]})
_sd, _ = SI.family_drafts(SI.expand_group(GROUP, _screened), _screened,
                          account_id="a", marketplace="UK")
truthy("the parent keeps the warning that was paid for before drafting",
       "test certificate" in _sd[0]["notes"])
truthy("  and still says it is the group",
       "not for sale" in _sd[0]["notes"])
check("every child carries it too, not just the parent",
      sum(1 for d in _sd[1:] if "test certificate" in d["notes"]), 3)

parent = drafts[0]
check("the parent is named after the eBay listing, not after a child",
      parent["sku"], "PARENT_223778867020")
check("  it is not for sale", parent["status"], "PARENT")
truthy("  and it says so in words", "not for sale" in parent["notes"])
check("  it has no cost baked into a SKU", "_3Days_" in parent["sku"], False)

import json as _j
kid = drafts[2]
fam = _j.loads(kid["attributes_json"])["_family"]
check("a child knows its parent", fam["parent_sku"], "PARENT_223778867020")
check("  and which variation of the eBay listing it is",
      fam["variation_id"], "522519025284")
check("the theme is recorded as PROPOSED, never as settled",
      (fam["proposed_theme"], fam["theme_confirmed"]), ("COLOR/SIZE", False))
check("what makes this child different is on the row itself",
      (kid["colour"], kid["size"]), ("Black", "M"))
_unknown2 = [k for k in kid if not k.startswith("_") and k not in _known]
check("every key a child writes is one the store actually has", _unknown2, [])

print("\n--- _family is ours, and must never be posted to Amazon ---")
import amazon_listing_generator as GEN
import inspect as _insp
_bsrc = _insp.getsource(GEN.build_api_attributes)
truthy("underscore keys are stripped as a RULE, not one name at a time",
       'startswith("_")' in _bsrc)
truthy("  which is what keeps _family out", "pa.pop(_k" in _bsrc)

print("\n--- a family that cannot be read is skipped, not guessed at ---")
check("one readable variation is not a family",
      SI.family_drafts(SI.expand_group({"items": GROUP["items"][:1]}, FAMILY_ROW),
                       FAMILY_ROW, account_id="a", marketplace="UK")[0], [])
_bad = {"items": [dict(_kid("0", "Black", "S", "9.99", "x"), itemId="v1|223|0")]}
check("a child with no variation id is left out rather than colliding",
      SI.expand_group(_bad, FAMILY_ROW)["count"], 0)
truthy("  and the drop is counted, not silent",
       any("left out" in p for p in SI.expand_group(_bad, FAMILY_ROW)["problems"]))

print("\n=== a family URL is not an ended listing ===")
# Measured: get_item_by_legacy_id answers HTTP 400 for a variation family's id,
# exactly as it does for a listing that has ended. Reading the two as the same
# thing would take a live, selling product out of stock and keep it there.
from domain import source_fetch as SF
from domain import sourcing as S
check("the transport has a word for it", E.GROUP, "group")
check("every transport status is still translated",
      sorted(SF._FROM_TRANSPORT), sorted([E.OK, E.GONE, E.FAILED, E.GROUP]))
check("a family reads as 'we learned nothing'",
      SF._FROM_TRANSPORT[E.GROUP], S.FAILED)
check("  and NOT as 'the supplier stopped selling it'",
      SF._FROM_TRANSPORT[E.GROUP] == S.GONE, False)
_gsrc = _insp.getsource(E.get_item)
truthy("get_item asks the group endpoint before calling anything dead",
       "item_group(" in _gsrc)
truthy("  and fetches a named child by its own id, not the listing's",
       "full_item_id(item_id, var_id)" in _gsrc)

print("\n=== drafted items are watched from the moment they exist ===")
import os, tempfile, json as _json2
_tmp = tempfile.mkdtemp()
_cfgp = os.path.join(_tmp, "config.json")
open(_cfgp, "w").write(_json2.dumps({"db_path": os.path.join(_tmp, "t.db")}))
from domain import source_repo as SR
_id1, _new1 = SR.ensure_source(_cfgp, "w", "UK", "SKU1",
                               "https://www.ebay.co.uk/itm/1?var=2", kind="ebay")
truthy("the first import adds the source", _new1)
_id2, _new2 = SR.ensure_source(_cfgp, "w", "UK", "SKU1",
                               "https://www.ebay.co.uk/itm/1?var=2", kind="ebay")
check("importing the same seller again does NOT add it twice", _new2, False)
check("  it is the same row", _id2, _id1)
_id3, _new3 = SR.ensure_source(_cfgp, "w", "UK", "SKU1",
                               "https://www.ebay.co.uk/itm/1?var=3", kind="ebay")
truthy("a different VARIATION of the same listing is a different source", _new3)
check("  so the SKU now has two", len(SR.sources_for(_cfgp, "w", "UK", "SKU1")), 2)
check("an empty URL adds nothing",
      SR.ensure_source(_cfgp, "w", "UK", "SKU1", "")[1], False)

_rsrc = _insp.getsource(__import__("routes.seller_routes", fromlist=["x"]).register)
truthy("enrolment is DRY RUN -- it watches, it does not reprice",
       'mode="dry_run"' in _rsrc)
truthy("  the parent is never enrolled: nothing supplies it",
       'src.get("role") == "parent"' in _rsrc)
truthy("  a failed enrolment does not lose the draft that saved",
       "enrol_errors" in _rsrc)
truthy("  and a family whose variations cannot be read is skipped, not flattened",
       "left out rather than drafted" in _rsrc)
truthy("  the expansion ceiling is reported, never applied quietly",
       "would_draft" in _rsrc)

# Adding a supplier BY HAND goes through the same two rules, in the one place
# that adds sources -- otherwise a family URL pasted into the repricer would sit
# in every sweep answering "could not tell", and the repricer would correctly do
# nothing, silently, for ever.
_ssrc = _insp.getsource(__import__("routes.sourcing_routes",
                                   fromlist=["x"]).register)
truthy("a family URL is refused where you can still fix it",
       "_ebay.GROUP" in _ssrc)
truthy("  and a link that names a variation goes straight through",
       "variation_id_from_url(url)" in _ssrc)
truthy("  the same link twice does not become two sources",
       "ensure_source(" in _ssrc)

print("\n=== the screening verdict survives onto the draft, in words ===")
# It was a toast on one screen. Click anywhere and the answer to "which of these
# needs documents, and which documents" was gone, on the screen whose whole
# purpose is deciding what to spend generation credits on.
for _v, _expect in ((SI.BLOCKED, "AMAZON BLOCKS THIS"),
                    (SI.DOCS, "AMAZON WILL ASK FOR DOCUMENTS"),
                    (SI.CAUTION, "WORTH CHECKING"),
                    (SI.UNKNOWN, "COULD NOT BE CHECKED")):
    _d = SI.to_draft(dict(r, screen={"verdict": _v,
                                     "notes": ["A test certificate is required."]}),
                     account_id="a", marketplace="UK")
    truthy("a %s draft says so at the front of its notes" % _v,
           _d["notes"].startswith(_expect[:20]))
    truthy("  and still carries the reason", "test certificate" in _d["notes"])
_clear = SI.to_draft(dict(r, screen={"verdict": SI.CLEAR, "notes": []}),
                     account_id="a", marketplace="UK")
# No WARNING heading -- the point of the check. It does carry one note, which is
# what the draft IS rather than what is wrong with it: reported as "import from
# supplier button is drafting the listings as empty ... and no content is written
# in them", which is true and deliberate and was nowhere stated.
for _bad in ("AMAZON BLOCKS", "WILL ASK FOR DOCUMENTS", "WORTH CHECKING",
             "COULD NOT BE CHECKED"):
    check("a clear draft is not headed %r" % _bad, _bad in _clear["notes"], False)
truthy("but it does say its copy has not been written yet",
       _clear["notes"].startswith("COPY NOT WRITTEN YET"))
truthy("  and how to write it", "Regenerate copy" in _clear["notes"])

_js = open(r"D:\AltaScraper\static\js\sellerimport.js", encoding="utf-8").read()
truthy("the screen keeps the summary instead of toasting it",
       "SIMP.screenSummary" in _js)
truthy("  and every verdict opens its own reasons in place",
       "function sellerWhy" in _js)
truthy("  rather than hiding them in a tooltip nobody can hold still for",
       "Click to read the full reasons" in _js)

print("\n=== eBay answers an unknown seller with the WHOLE CATALOGUE ===")
# Measured on the live API, 15 Aug 2026, and this is the entire reason this
# section exists:
#
#   sellers:{worldcarparts_uk}             HTTP 200  total 24,947   all matched
#   sellers:{definitely_not_a_seller_xyz}  HTTP 200  total 96,686,299  0 matched
#   nonsensefield:{x}                      HTTP 200  total 96,686,299  0 matched
#
# 96.7 million is the whole of eBay. An unrecognised filter is not rejected, it
# is DISCARDED, and the query runs without it. Two real shop names the owner
# supplied were unrecognised on every eBay site in every capitalisation, so
# "import this seller" imported thousands of other people's products and
# presented them as one seller's range.
_calls = {"n": 0}
def _fake_search(pages):
    """Stand in for urlopen, handing back pre-built pages."""
    import json as _j, io
    def _open(req, timeout=None):
        i = min(_calls["n"], len(pages) - 1)
        _calls["n"] += 1
        body = _j.dumps(pages[i]).encode("utf-8")
        class _R:
            def read(self_inner): return body
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
        return _R()
    return _open

def _item(n, who):
    return {"itemId": "v1|%d|0" % n, "legacyItemId": str(n),
            "title": "thing %d" % n, "seller": {"username": who},
            "price": {"value": "9.99", "currency": "GBP"}}

import urllib.request as _ur
_real_open = _ur.urlopen
E._TOKEN_CACHE["token"] = "t"
E._TOKEN_CACHE["expires_at"] = 9e18
try:
    # 1. eBay ignored the filter: a page of OTHER people's items.
    _calls["n"] = 0
    _ur.urlopen = _fake_search([{"total": 96686299,
                                 "itemSummaries": [_item(i, "someone_else")
                                                   for i in range(10)]}])
    items, meta = E.search_seller("5277RON-OFFICIAL", "a", "b",
                                  terms=("a",), pages_per_term=1, per_page=10)
    check("not one of those items is imported", len(items), 0)
    check("  and it is recorded as an unknown seller", meta["seller_known"], False)
    check("  every foreign item was counted, not quietly dropped",
          meta["rejected"], 10)
    truthy("  the error says eBay answered with its whole catalogue",
           any("whole catalogue" in e for e in meta["errors"]))

    # 2. A real seller: everything comes through untouched.
    _calls["n"] = 0
    _ur.urlopen = _fake_search([{"total": 24947,
                                 "itemSummaries": [_item(i, "worldcarparts_uk")
                                                   for i in range(10)]}])
    items2, meta2 = E.search_seller("worldcarparts_uk", "a", "b",
                                    terms=("a",), pages_per_term=1, per_page=10)
    check("a real seller's items all come through", len(items2), 10)
    check("  nothing rejected", meta2["rejected"], 0)
    check("  and it is recorded as known", meta2["seller_known"], True)

    # 3. The dangerous middle case: MOSTLY theirs, with strangers mixed in.
    _calls["n"] = 0
    mixed = ([_item(i, "worldcarparts_uk") for i in range(6)]
             + [_item(100 + i, "somebody_else") for i in range(4)])
    _ur.urlopen = _fake_search([{"total": 500, "itemSummaries": mixed}])
    items3, meta3 = E.search_seller("worldcarparts_uk", "a", "b",
                                    terms=("a",), pages_per_term=1, per_page=10)
    check("strangers are dropped even when most of the page is right",
          len(items3), 6)
    check("  and counted", meta3["rejected"], 4)

    # 4. Case never decides it. eBay usernames are not case sensitive and
    #    refusing on capitalisation would reject a seller who does exist.
    _calls["n"] = 0
    _ur.urlopen = _fake_search([{"total": 5,
                                 "itemSummaries": [_item(1, "WorldCarParts_UK")]}])
    items4, meta4 = E.search_seller("worldcarparts_uk", "a", "b",
                                    terms=("a",), pages_per_term=1, per_page=10)
    check("capitalisation does not reject a real seller", len(items4), 1)
finally:
    _ur.urlopen = _real_open
    E._TOKEN_CACHE["token"] = None

truthy("a link can be used instead of a name", hasattr(E, "seller_of"))
_fsrc = _insp.getsource(__import__("routes.seller_routes",
                                   fromlist=["x"]).register)
truthy("  and the route accepts one where a name is asked for",
       "seller_of(" in _fsrc)
truthy("  an unknown seller is REFUSED, not returned as a catalogue",
       'meta.get("seller_known") is False' in _fsrc)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
