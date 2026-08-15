"""Which image slot, and what Amazon will accept in it.

The library could only ever send a MAIN image. Amazon has eighteen image
attributes on a live SPACE_HEATER listing, and which one you send to changes what
the rules are: a lifestyle shot is fine as PT3 and gets the listing SUPPRESSED as
MAIN. So the slot has to be chosen deliberately, and the choice has to say what
it means.
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

from listing import images as I

# Copied from what Amazon returned for SPACE_HEATER on the live UK account,
# 14 Aug 2026 -- including the two UK compliance slots, which exist because it is
# a heater sold in Britain and which no hardcoded list would have contained.
SCHEMA = {"properties": {k: {"title": t} for k, t in [
    ("main_product_image_locator", "Main Product Image Locator"),
    ("other_product_image_locator_1", "Other Product Image Locator 1"),
    ("other_product_image_locator_2", "Other Product Image Locator 2"),
    ("other_product_image_locator_8", "Other Product Image Locator 8"),
    ("swatch_product_image_locator", "Swatch Product Image Locator"),
    ("main_offer_image_locator", "Main Offer Image Locator"),
    ("other_offer_image_locator_1", "Other Offer Image Locator"),
    ("image_locator_eeuk", "UK Energy Efficiency Label"),
    ("image_locator_pfuk", "UK Product Fiche Label"),
    ("item_name", "Title"),                      # not an image; must be ignored
]}}

print("=== the slots come from the schema, never from a list we wrote ===")
slots = I.slots_from_schema(SCHEMA)
keys = [s["key"] for s in slots]
check("nine image slots, and the title is not one of them", len(slots), 9)
check("  item_name is excluded", "item_name" in keys, False)
check("the main image comes first", keys[0], "main_product_image_locator")
check("  labelled plainly", slots[0]["label"], "Main image")
check("PT slots are numbered as Amazon numbers them",
      [s["label"] for s in slots if s["label"].startswith("PT")],
      ["PT1", "PT2", "PT8"])
check("  and in order, not alphabetically", keys[1:4],
      ["other_product_image_locator_1", "other_product_image_locator_2",
       "other_product_image_locator_8"])
check("the swatch is there", "swatch_product_image_locator" in keys, True)
check("offer images are kept apart from product images",
      [s["group"] for s in slots if "offer" in s["key"]], ["offer", "offer"])
check("the UK compliance slots are NOT hidden",
      sorted(s["key"] for s in slots if s["group"] == "other"),
      ["image_locator_eeuk", "image_locator_pfuk"])
truthy("  and carry their own title, since we do not know what they are",
       any("Energy Efficiency" in s["help"] for s in slots))
check("a schema that could not be read yields nothing",
      I.slots_from_schema({}), [])

print("\n=== every slot says what it is for, at the moment you choose it ===")
main = [s for s in slots if s["key"] == I.MAIN][0]
truthy("main warns about the white background", "pure white" in main["help"])
truthy("  and about suppression", "suppress" in main["help"])
pt = [s for s in slots if s["label"] == "PT1"][0]
truthy("PT says text and graphics are allowed", "allowed" in pt["help"])
sw = [s for s in slots if s["key"] == I.SWATCH][0]
truthy("the swatch explains where it appears", "variation" in sw["help"])

print("\n=== Amazon fetches the image itself, so the URL has to be reachable ===")
check("an https url is fine", I.check_url("https://drive.example/x.jpg"), "")
check("  http too", I.check_url("http://x.test/a.png"), "")
check("  and s3, which the schema also allows", I.check_url("s3://bucket/k.jpg"), "")
truthy("an app-internal path is refused",
       "public https" in I.check_url("/media/_acct/jack/SKU/gen_1.png"))
truthy("  and it says what to do instead",
       "Drive" in I.check_url("/media/x.png"))
truthy("a data url is refused too", I.check_url("data:image/png;base64,AAAA"))
truthy("nothing at all is refused", I.check_url(""))

print("\n=== warnings are separate from refusals ===")
# A refusal stops the send; a warning is something you may knowingly accept.
# Mixed together, either real mistakes hide in noise or good work gets blocked.
w = I.warnings(I.MAIN, "https://x/y.jpg", current_value="")
truthy("main always warns about its rules", any("pure white" in x for x in w))
w2 = I.warnings("other_product_image_locator_2", "https://x/y.jpg",
                current_value="https://x/old.jpg")
truthy("replacing an occupied slot is called out",
       any("already has an image" in x for x in w2))
truthy("  and says the old one is not kept", any("not kept" in x for x in w2))
check("an empty PT slot needs no warning at all",
      I.warnings("other_product_image_locator_2", "https://x/y.jpg"), [])
w3 = I.warnings(I.SWATCH, "https://x/y.jpg", is_variation_child=False)
truthy("a swatch on a non-variation listing is pointless, and says so",
       any("nowhere to show" in x for x in w3))
check("  but is fine on a child of a family",
      I.warnings(I.SWATCH, "https://x/y.jpg", is_variation_child=True), [])

print("\n=== an image the app made as SECONDARY may not become the MAIN ===")
# A refusal, not a warning. Secondary and A+ images are generated under rules
# that ALLOW text, graphics and lifestyle scenes -- exactly what Amazon
# suppresses a listing for on the main image. The app knows which is which
# because it files them that way.
truthy("a secondary image is refused from the main slot",
       I.refuse_slot(I.MAIN, "secondary"))
truthy("  and says the app made it that way",
       "generated this as a SECONDARY" in I.refuse_slot(I.MAIN, "secondary"))
truthy("  and offers the alternative", "PT slot" in I.refuse_slot(I.MAIN, "secondary"))
truthy("an A+ module image is refused too", I.refuse_slot(I.MAIN, "aplus/basic"))
truthy("  naming what it is", "A+ module" in I.refuse_slot(I.MAIN, "aplus/premium"))
check("the same secondary image is FINE as PT3",
      I.refuse_slot("other_product_image_locator_3", "secondary"), "")
check("  and as a swatch", I.refuse_slot(I.SWATCH, "secondary"), "")
check("a main-image generation may be the main image",
      I.refuse_slot(I.MAIN, ""), "")
check("  and an uploaded file is not blocked either",
      I.refuse_slot(I.MAIN, "main"), "")

print("\n=== the patch is the shape the schema requires ===")
p = I.build_patch("other_product_image_locator_3", "https://x/y.jpg", "A1F83G8C2ARO7P")
check("replace, at the slot's own path", (p["op"], p["path"]),
      ("replace", "/attributes/other_product_image_locator_3"))
check("  media_location is the required key",
      p["value"][0]["media_location"], "https://x/y.jpg")
check("  and it is marketplace-scoped",
      p["value"][0]["marketplace_id"], "A1F83G8C2ARO7P")
check("whitespace does not travel into the URL",
      I.build_patch(I.MAIN, "  https://x/y.jpg  ", "M")["value"][0]["media_location"],
      "https://x/y.jpg")

print("\n=== the picker is actually GIVEN the image slots ===")
"""Reported: "i still dont have an option to select the image secondary image 1
(pt1), 2 and so on when i go on the product card and clicck the listing images
button".

The finder above was right all along. What reached it was not.

dashboard._variation_schema fetches a product type's schema and then keeps ONE
property -- variation_theme -- because it was written for the variation checker.
It is injected as `_schema_for` into routes/variations_routes.py, and that module
serves TWO screens: the variation checker AND /listing/image_slots. So the image
picker was handed a schema with a single property in it and correctly found no
image slots. Every product type, every listing, every time.

A test of slots_from_schema alone could never catch that, because the fault was
in what the caller passed. So this checks the caller.
"""
_DASH = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8").read()
_i = _DASH.find("def _variation_schema")
_body = _DASH[_i:_DASH.find("\ndef ", _i + 10)]
truthy("the cached schema keeps variation_theme", '"variation_theme"' in _body)
truthy("  AND every image attribute, which the picker reads",
       'if "image" in k.lower()' in _body)
check("  by matching on the key, not a hand-written list of slot names",
      "for k, v in props.items()" in _body, True)
# A named list would silently drop any slot Amazon adds later; the finder
# already sorts MAIN / PT / swatch / offer out of whatever it is given.
check("  so a slot Amazon adds later is not silently dropped",
      "other_product_image_locator_1" in _body, False)

print("\n=== an occupied slot is reported as occupied ===")
"""The second half, and the dangerous half. Every slot read "empty" on a listing
with five images on it, because the attribute flattener only knew "value" and
"name".

MEASURED on a live UK listing:

    main_product_image_locator:
      [{"media_location": "https://m.media-amazon.com/images/I/61qid...jpg",
        "marketplace_id": "A1F83G8C2ARO7P"}]

Sending to an occupied slot replaces its image and Amazon keeps no copy. Saying
"empty" about a slot that has one would have let someone destroy an image
without ever being asked.
"""
_VR = open(r"D:\AltaScraper\routes\variations_routes.py", encoding="utf-8").read()
truthy("the flattener knows the image wrapper's key",
       '"media_location"' in _VR)
truthy("  and the keys are declared once, not per branch",
       "_VALUE_KEYS = " in _VR)
check("  both branches use that one list",
      len([1 for line in _VR.splitlines() if "for k in _VALUE_KEYS" in line]), 2)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
