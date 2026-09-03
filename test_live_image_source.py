"""A listing's picture is read from BOTH places Amazon puts it.

    "some products show empty image squares instead of their actual product
     image"

WHAT WAS HAPPENING. /live/images -- the endpoint the background enricher calls
to fill in missing thumbnails -- took the picture from `summaries[0].mainImage`
and looked nowhere else. Amazon does not always put it there. For some listings
the summary has no mainImage key at all and the picture is in
`attributes.main_product_image_locator`, which the same request already
fetches and which the same file already reads elsewhere.

MEASURED on nestwell_goods, 3 Sep 2026. Three of its 37 listings had no picture
in the app. Asked directly through getListingsItem:

    39.99_3Days_B0G14RGRDC   no image in either place -- Amazon genuinely has
                             none, so the empty square is the truth
    8.98_2Days_B0H2WC8DTM    the same
    9.18_3Days_B0C6XTNXL8    summaries: no mainImage key
                             attributes: .../61IaMCcv74L.jpg -- 92KB, HTTP 200

So one of the three was a picture the app had been told about and did not read.
And it could not correct itself: the enricher retries only listings with no
image, and every retry read the same empty field. It would have stayed blank
for as long as the listing existed.

TWO READERS, ONE FILE, DIFFERENT ANSWERS. _mirror_images has always read the
attribute first and the summary second. /live/images read only the summary.
Same question about the same payload (CLAUDE.md Rule 12), and the weaker one
was the one the automatic path used.

NOT A URL PROBLEM. Both stored URLs that do exist were fetched during the
investigation and both answered HTTP 200, so nothing here expires.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


SRC = open(os.path.join(HERE, "routes", "live_routes.py"), encoding="utf-8").read()
_IMAGES_FN = SRC.split("def live_images(")[1].split("\n    @app.route")[0]
_MAIN_FN = SRC.split("def _main_image(")[1].split("\n    def ")[0]
_MIRROR_FN = SRC.split("def _mirror_images(")[1].split("\n    def ")[0]

print("=== there is ONE reader, and it knows both places ===")
truthy("a shared _main_image exists", "def _main_image(" in SRC)
# The CODE, not the docstring: the evidence written above the function names
# both fields, and in the other order, which would make an ordering check on the
# whole function text meaningless.
_MAIN_CODE = _MAIN_FN.split('"""')[2]
truthy("  it tries the attribute first",
       _MAIN_CODE.index("main_product_image_locator")
       < _MAIN_CODE.index("mainImage"))
truthy("  and falls back to the summary", '"mainImage"' in _MAIN_FN
       or "get(\"mainImage\")" in _MAIN_FN)
truthy("  returning \"\" rather than None when there is neither",
       'return ""' in _MAIN_FN)

print("\n=== the endpoint the enricher calls uses it ===")
truthy("/live/images asks the shared reader",
       "_main_image(attrs, summaries)" in _IMAGES_FN)
falsy("  and no longer reads mainImage on its own",
      re.search(r'url\s*=\s*mi\.get\("link"', _IMAGES_FN))
# The request already asked for attributes -- it was using them for the handling
# time and ignoring them for the picture.
truthy("  the attributes it needs were already being fetched",
       "attributes" in _IMAGES_FN and "includedData" in _IMAGES_FN)

print("\n=== the gallery reader goes through it too ===")
truthy("_mirror_images routes its fallback through the shared reader",
       "_main_image(attrs, summaries)" in _MIRROR_FN)
falsy("  rather than keeping its own copy of the summary read",
      re.search(r'mi\s*=\s*\(summaries\[0\]\.get\("mainImage"\)', _MIRROR_FN))
# Its own attribute-first behaviour is unchanged: it still collects every image,
# not just the main one, and the shared reader is only its fallback.
truthy("  and still gathers the other slots and the swatch",
       "other_product_image_locator" in _MIRROR_FN
       and "swatch_image_locator" in _MIRROR_FN)

print("\n=== the empty squares that are TRUE stay empty ===")
# Two of the three measured listings have no image anywhere. Nothing here
# invents one -- there is no placeholder, no competitor's picture, no guess.
falsy("nothing substitutes a stand-in image",
      re.search(r'url\s*=\s*["\']http', _IMAGES_FN))
truthy("a listing Amazon has no picture for is left blank",
       'return ""' in _MAIN_FN)

print("\n=== where the sourcing page reads it from, unchanged ===")
# The repricer draws its thumbnail through domain/catalogue.py, which reads the
# live snapshot and falls back to the draft's supplier photo. That is not what
# was broken and is asserted here so a later "fix" does not move it.
CAT = open(os.path.join(HERE, "domain", "catalogue.py"), encoding="utf-8").read()
truthy("the catalogue lookup reads the live snapshot",
       "live_snapshots" in CAT)
truthy("  and fills gaps from the app's own drafts",
       "_fill_from_drafts" in CAT and "main_product_image_locator" in CAT)
truthy("  never conflating an Amazon picture with a supplier one",
       '"amazon" if img else ""' in CAT and '"supplier"' in CAT)
SR = open(os.path.join(HERE, "routes", "sourcing_routes.py"), encoding="utf-8").read()
truthy("the repricer row gets its picture from that one lookup",
       "_cat.look(idx, d[\"sku\"])" in SR)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
