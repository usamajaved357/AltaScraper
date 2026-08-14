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

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
