"""Secondary images and A+ that suit the product, and never cut the text in half.

    "the secondary images are meant to drive conversions by addressing buyer
     doubts, highlighting benefits, and overcoming purchasing barriers ... There
     is no need to show the item in all the pictures."

    "the aplus content is not alligned with each other every module contains
     item images ... the cutout text is there but it is half, where is the other
     half, every module do not talk with each other"

THREE FAULTS, ALL MEASURED

  1. EVERY IMAGE SHOWED THE WHOLE PRODUCT. Nothing ever asked how much of the
     product a given image needed, so the answer was always "all of it" and a
     set of eight came out as eight photographs of the same bottle. The slots
     that should have answered a doubt were spent repeating the main image.

     The strongest secondary images on real listings often contain NO product:
     a wall of journal pages under "3,319 peer-reviewed studies"; a
     specification panel with the numbers called out around it.

  2. A+ TEXT WAS CUT IN HALF. _resize_to_exact cover-cropped unconditionally,
     and the models return a roughly square image whatever ratio they are
     asked for. MEASURED on the real output: 4096x4096 cropped to 1464x600
     discards 59% of the height. Every A+ module came back with its headline
     sliced through the middle -- "MULTIVITAMIN.", "WEEKS COVERED.", "2
     CAPSULES", all half gone.

  3. TWO ROLES SILENTLY DID NOTHING. The screen offered "Close-up detail" and
     "Use-case", neither existed server-side, and both fell through to the
     benefit infographic -- so the two roles most likely to break up a
     repetitive set were the two that quietly did not work.

WHAT THIS FILE DOES NOT DO

It does not assert any particular concept. The whole point is that the content
must come from the product -- "we can not tell in secondary images for a table
stand that this is third party lab tested" -- so pinning an expected concept
would be hardcoding the very thing being removed. It pins the MACHINERY that
lets the content vary, and the arithmetic that stops text being destroyed.
"""
import base64
import io
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import ai_providers as _ai       # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


print("\n== every role says how much product it needs ==")
import dashboard as _dash                    # noqa: E402
roles = _dash._SECONDARY_ROLES
truthy("there are roles", roles)
for k, v in roles.items():
    truthy("  %s declares its presence" % k, v.get("present"))
    truthy("  %s has a brief" % k, len(v.get("brief") or "") > 40)
    check("  %s uses a known presence" % k,
          v["present"] in ("hero", "detail", "in_use", "none"), True)

# THE TWO THAT SILENTLY DID NOTHING. The screen offered them; the server did
# not have them; both produced a benefit infographic instead.
for k in ("detail", "usecase"):
    truthy("%s exists server-side now" % k, k in roles)
JS = open(r"D:\AltaScraper\static\js\genimage.js", encoding="utf-8-sig").read()
# Scoped to the secondary roles array. Matching the whole file also catches the
# MAIN-image recipe triples, which are a different list entirely -- and a test
# that fails on an unrelated list is a test nobody reads.
_blk = re.search(r"const roles\s*=\s*\[([\s\S]*?)\n\s*\];", JS)
truthy("the secondary role list was found", _blk)
offered = set(re.findall(r'\["([a-z_]+)"', _blk.group(1) if _blk else ""))
truthy("the screen offers roles", offered)
missing = sorted(offered - set(roles))
check("every role the screen offers really exists", missing, [])
check("  and every role the server has is offered",
      sorted(set(roles) - offered), [])

print("\n== the set is not all hero ==")
# The fault, stated as arithmetic: if every role wanted the whole product, no
# combination of them could ever produce a varied set.
spread = {}
for v in roles.values():
    spread[v["present"]] = spread.get(v["present"], 0) + 1
truthy("some roles show no product at all", spread.get("none", 0) >= 3)
truthy("  some show only a part", spread.get("detail", 0) >= 2)
truthy("  some show it in a real scene", spread.get("in_use", 0) >= 2)
check("  and hero is not the majority",
      spread.get("hero", 0) <= len(roles) // 2, True)

print("\n== the instruction and the attachment agree ==")
# Telling the model "do not show the product" while handing it the product
# photograph is a contradiction, and the photograph wins -- which is how every
# slot ended up with another picture of the bottle.
RT = open(r"D:\AltaScraper\routes\genimage_routes.py", encoding="utf-8-sig").read()
truthy("there is a rule per presence", "_PRESENCE_RULES" in RT)
truthy("  and 'none' forbids the product outright",
       "DO NOT SHOW THE PRODUCT IN THIS IMAGE AT ALL" in RT)
truthy("the reference is withheld for a product-free image",
       re.search(r'_ref\s*=\s*""\s*if\s+presence\s*==\s*"none"', RT))
truthy("  including the second anchoring reference",
       re.search(r"_want_ref\s*=\s*presence\s*!=\s*\"none\"", RT))
# ...and a product-free concept must not be refused for having no photo.
truthy("a product-free concept is not refused for lacking a reference",
       re.search(r'if not product_image and presence != "none"', RT))

print("\n== the strategist decides it per product ==")
# A fixed rota would be the same generic list the prompt already warns against:
# a bench needs scale against a person, a supplement needs its facts panel.
AI = open(r"D:\AltaScraper\domain\ai_providers.py", encoding="utf-8-sig").read()
truthy("the model is asked for a presence per concept", "_PRESENCE_BRIEF" in AI)
truthy("  and returns it in the JSON", '"product_presence"' in AI)
truthy("  told not to make them all hero", "DO NOT make every concept" in AI)
# The exact fault named in the request.
truthy("  and warned against carrying one product's answer to another",
       "meaningless on a table stand" in AI)

print("\n== A+ modules are one page, not a pile ==")
truthy("there is a story arc", "_APLUS_STORY" in AI)
for role in ("open", "problem", "answer", "proof", "detail", "use", "compare",
             "close"):
    truthy("  the arc offers '%s'" % role, ("  %s " % role) in AI)
truthy("each module carries its role", '"role"' in AI)
truthy("  and the headline it carries", '"headline"' in AI)
truthy("  and must hand over to the next",
       "MUST HAND OVER TO THE NEXT" in AI)
# "every module do not talk with each other" was partly a LOOK problem: seven
# modules each styled differently read as seven different brands.
truthy("  with one look held across the whole page",
       "SET THE LOOK ONCE AND HOLD IT" in AI)
truthy("modules are generated at their OWN size",
       "_APLUS_MODULES.get(_tier)" in RT)

print("\n== the resize can no longer cut anything in half ==")
# THE ARITHMETIC OF THE BUG. A square composition into a premium A+ banner.
def _png(w, h, colour=(20, 20, 20)):
    from PIL import Image
    im = Image.new("RGB", (w, h), colour)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _size(b64):
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(b64))).size


sq = _png(4096, 4096)
out = _ai._resize_to_exact(sq, 1464, 600)
check("a square into a premium banner still comes out exactly right",
      _size(out), (1464, 600))
# It must have been CONTAINED, not cropped -- a cover-crop here discards 59%.
cover = max(1464 / 4096, 600 / 4096)
lost = 1.0 - min(1464 / (4096 * cover), 600 / (4096 * cover))
truthy("  and a cover-crop here would have discarded over half the height",
       lost > 0.5)
truthy("  so the code contains and pads instead", "_SAFE_CROP" in AI)
check("  the threshold is a small crop, not a large one",
      _ai._SAFE_CROP <= 0.15, True)

# A SMALL mismatch should still crop -- padding a 3% difference would put
# pointless bars on every image.
near = _png(1500, 600)
out2 = _ai._resize_to_exact(near, 1464, 600)
check("a near-match is cropped, not padded", _size(out2), (1464, 600))
# An exact match is returned untouched.
exact = _png(970, 600)
check("an exact match is left alone", _ai._resize_to_exact(exact, 970, 600),
      exact)
# Every module size in the catalogue must survive the round trip.
for tier, mods in (_dash._APLUS_MODULES or {}).items():
    for m in mods:
        got = _size(_ai._resize_to_exact(sq, m["w"], m["h"]))
        check("  %s/%s comes out %dx%d" % (tier, m["id"], m["w"], m["h"]),
              got, (m["w"], m["h"]))

print("\n== padding takes the image's own colour, not white ==")
# White bars on a dark composition look like a mistake; the edge colour reads
# as a deliberate margin.
dark = _png(4096, 4096, (18, 22, 30))
padded = _ai._resize_to_exact(dark, 1464, 600)
from PIL import Image                                            # noqa: E402
im = Image.open(io.BytesIO(base64.b64decode(padded)))
corner = im.getpixel((5, 5))
truthy("a dark image gets a dark margin, not white bars", sum(corner) < 200)

print("\n== the model is told to compose for the shape ==")
# Containing is a safety net. A square composition inside a wide banner is a
# small picture with big margins -- correct, and not what anyone wanted.
truthy("the target shape is stated in words", "CANVAS AND LAYOUT" in AI)
truthy("  named as a wide banner when it is one", "WIDE BANNER" in AI)
truthy("  with a safe area so text never sits on the edge", "SAFE AREA" in AI)

print("\n== a phone gets its own composition, not the desktop squeezed ==")
#     "in premium aplus content there is mobile version and desktop version but
#      app is not making separate diensions content"
AP = open(r"D:\AltaScraper\routes\aplus_routes.py", encoding="utf-8-sig").read()
_prem = {m["id"]: m for m in (_dash._APLUS_MODULES.get("premium") or [])}
truthy("the full-width premium banner declares a mobile size",
       (_prem.get("premium_full") or {}).get("mobile"))
truthy("  and so does the premium header",
       (_prem.get("premium_header") or {}).get("mobile"))
truthy("the route can be asked for either screen", 'b.get("viewport"' in AP)
truthy("  and the mobile one is COMPOSED for a phone",
       "THIS IS THE MOBILE RENDITION" in AP)
truthy("  stacked rather than laid out wide", "STACKED vertically" in AP)
# THE TRAP: asking for mobile but still cutting to the desktop numbers would
# quietly produce the desktop image again.
check("the desktop size is not used to cut the mobile image",
      'mod["w"]' in AP.split("def aplus_generate")[-1].split("_resize_to_exact")[-1][:200],
      False)
truthy("  the chosen size is what is asked for and cut to",
       "_resize_to_exact(gen[\"image_b64\"], _w, _h)" in AP)
truthy("  and the result says which screen it is for", 'gen["viewport"]' in AP)
# RULE 4: the desktop figures are Amazon's; the mobile default is ours, and
# saying so is the difference between a default and a claim.
truthy("the mobile size is declared an assumption, not an Amazon figure",
       "APLUS_MOBILE_IS_ASSUMED" in open(r"D:\AltaScraper\dashboard.py",
                                         encoding="utf-8-sig").read())
truthy("  and that is sent to the screen", "mobile_size_note" in AP)

print("\n== what the image may SAY is checked on both paths ==")
# This lived on the hand-built role path only -- and the strategist path, the
# one people actually use, had no guard at all. It is what produced
# "AMINO ACIDS / L ranteine" on a real ingredient panel.
truthy("the text rules are one block", "_IMAGE_TEXT_RULES" in RT)
check("  used more than once", RT.count("_IMAGE_TEXT_RULES") >= 3, True)
truthy("  no figure that is not in the spec",
       "that is not given in the product spec above" in RT)
truthy("  and no invented ingredient names",
       "Inventing a plausible-looking name" in RT)
truthy("  no medical wording", "NO health, medical, therapeutic" in RT)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
