"""A compliance warning that cries wolf is worse than no warning at all.

THE REPORT: "wrong compliance docs and warnings are displayed" -- and, with the
evidence, a CHAIR showing:

    HIGH RISK  Cosmetic / skin-contact product  SKIN_CONTACT_COSMETIC
    Detected: names the product: sunscreen
    Docs required: Cosmetic Product Safety Report (CPSR), Product Information
    File (PIF), SCPN notification reference, Full INCI ingredient list

"Sunscreen fabric" is a real outdoor-furniture textile. The rule read it as sun
cream and demanded paperwork for a cosmetic. Someone who sees that twice stops
reading these warnings, and then misses the one that matters.

TWO GUARDS, tested here:
  the material sense of a trigger word is excluded ("sunscreen fabric")
  and a rule cannot fire on a product type it cannot possibly apply to --
  Amazon has already said the thing is a chair, and that is a fact rather than
  an inference from prose.

The second matters more: it catches the next word nobody thought of.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

from listing.sourcing_viability import check_sourcing_viability as chk

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def fired(title, bullets, pt, mkt="UK"):
    r = chk(title=title, bullets=bullets, product_type=pt, marketplace=mkt)
    return [x["id"] for x in r["risks"]]


print("\n== the reported case: a chair is not a cosmetic ==")
check("garden chair with sunscreen fabric",
      fired("Outdoor Zero Gravity Chair, Sunscreen Fabric, UV Resistant Mesh",
            ["Breathable sunscreen fabric mesh", "Rustproof steel frame"],
            "CHAIR"), [])
check("recliner with a sunscreen canopy",
      fired("Garden Recliner Chair with Sun Canopy",
            ["Sunscreen shade canopy blocks UV"], "CHAIR"), [])
check("a sunscreen roller blind",
      fired("Sunscreen Roller Blind 120cm", ["Sunscreen fabric, blocks glare"],
            "WINDOW_TREATMENT"), [])

print("\n== the product type vetoes it even for a word nobody excluded ==")
# The point of the type guard: it does not depend on anybody having thought of
# the phrase in advance.
check("a chair described with an unforeseen cosmetic word",
      fired("Massage Chair with Body Lotion Holder",
            ["Holds your body wash and shampoo"], "CHAIR"), [])
check("a tool with 'oil' in it", fired(
      "Chain Oil Applicator", ["For engine oil and chain oil"], "TOOL"), [])

print("\n== but a REAL cosmetic still demands its paperwork ==")
r = chk(title="Facial Sunscreen SPF 50 Lotion",
        bullets=["Broad spectrum UVA UVB", "Non greasy"],
        product_type="SKIN_CARE_AGENT", marketplace="UK")
check("a sunscreen still fires", [x["id"] for x in r["risks"]],
      ["SKIN_CONTACT_COSMETIC"])
check("  at HIGH risk", r["risks"][0]["risk"], "HIGH")
check("  and still asks for the CPSR",
      any("cpsr" in str(d).lower() for d in r["risks"][0]["docs"]), True)
check("  with a verdict that stops the sourcing", r["verdict"], "NEEDS_DOCS")

print("\n== and a cosmetic with NO product type is still caught ==")
# The guard must not become a way to slip past by omitting the type.
check("no product type means no veto",
      fired("Body Wash and Moisturiser Gift Set",
            ["Shower gel, body lotion"], ""), ["SKIN_CONTACT_COSMETIC"])

print("\n== food rules get the same guard ==")
check("a chair is not food",
      "FOOD_GROCERY" in fired("Dining Chair, Coffee Finish",
                              ["Pairs with a coffee table"], "CHAIR"), False)

print("\n== a bullet's own house style is not evidence of a stolen brand ==")
# FOUND BY RUNNING A REAL LISTING THROUGH THE PIPELINE. Every bullet this app
# writes is "ALL-CAPS LABEL — sentence", and the capitalised-word scan split
# sentences on . ! ? : ; but not on the dash. So the first word after every
# label read as a capital in the MIDDLE of a sentence, which is what the scan
# treats as a possible brand.
#
# Five bullets, five false positives, against a tolerance of four -- so an
# ordinary listing went to IP_HOLD on the strength of its own formatting.
# Measured on the sensory swing: "Heavy-duty, Aerial, Yoga, Sensory, Swing"
# reported as possible brands. Not one of them is a brand.
import json as _json
from listing import compliance as _cmp

_rules = _json.load(open(r"D:\AltaScraper\ip_rules.json", encoding="utf-8"))


def ip(listing, brand="AltaboltaVoo"):
    return _cmp.check_ip_violations(listing, brand, _rules, [])


HOUSE_STYLE = {
    "title": "Aerial Yoga Swing Sensory Hammock 150x280cm Polyester 200kg",
    "bullet_1": "SOFT, SKIN-FRIENDLY POLYESTER FABRIC — The 150 x 280 cm swing "
                "is made from a stretchy, high-density polyester material.",
    "bullet_2": "200 KG LOAD CAPACITY — Heavy-duty aluminium carabiner and "
                "reinforced suspension points are rated to support 200 kg.",
    "bullet_3": "COMPLETE HANGING KIT INCLUDED — The package contains the swing "
                "fabric, a large locking carabiner and an extension strap.",
    "bullet_4": "FOUR VERSATILE USE POSITIONS — Suitable for side-lying rest, "
                "supine back-stretch, cocoon-style wrapping and aerial poses.",
    "bullet_5": "INDOOR AND OUTDOOR USE — Compact folded size makes it easy to "
                "move between a living room beam, garden tree or outdoor frame.",
    "description_html": "<p>Stretchy polyester fabric, soft and breathable.</p>",
    "search_terms": "aerial yoga swing hammock polyester",
}
_out = ip(HOUSE_STYLE)
check("the app's own bullet style raises nothing", _out["unknown_caps"], [])
check("  so the listing is not held", _out["has_violations"], False)

# The guard must not become a way to smuggle a real brand past the scan: a
# genuine unknown capitalised word mid-sentence is still caught.
_sneaky = dict(HOUSE_STYLE)
_sneaky["bullet_1"] = ("SOFT FABRIC — The swing is made by Zorbulex Fabrications "
                       "using Kevlarite thread and Nimbotex weave and Voltraxx "
                       "coating and Quenzo finish.")
_out2 = ip(_sneaky)
check("a real unknown name is still reported",
      len(_out2["unknown_caps"]) >= 4, True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
