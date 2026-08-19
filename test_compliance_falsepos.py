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
from listing import compliance as _cmp

# THROUGH THE APP'S OWN LOADER, not json.load. The file stores
# "safe_capitalised_words" and "max_allowed_caps_words_unrecognised"; it is
# load_ip_rules() that turns those into the "safe_capitalised_lc" and
# "max_unrecognised" keys the check actually reads. Reading the file directly
# tested a run with an EMPTY 919-word allowlist -- a harder test than reality,
# which sounds safe until it hides a rule that only misbehaves once the
# allowlist is present.
from amazon_listing_generator import load_ip_rules as _load_ip

_rules = _load_ip()


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

# ---------------------------------------------------------------------------
print("\n== a hold needs EVIDENCE; a guess is only ever a note ==")
# THE REPORT: "i see ip hold and ip high symbols on many items where it does
# not have to be". Measured across the 295 stored listings: 72 rows carried an
# IP flag, and re-judging them found 68 occurrences of a comparative phrase of
# which exactly TWO pointed at a brand (iPhone, macOS). The other rows were held
# for saying what their product fits, or for ordinary nouns inside the app's own
# Title Case feature lists.


def body(*bullets):
    d = {"title": "Garden Hose Connector Set Brass 3/4 Inch",
         "description_html": "", "search_terms": ""}
    for i, b in enumerate(bullets, 1):
        d["bullet_%d" % i] = b
    return d


# --- the phrase must point AT something before it holds --------------------
_generic = ip(body("COMPATIBLE WITH UK TAPS — Compatible with standard garden "
                   "tap outlets commonly found on UK properties."))
check("'compatible with standard garden tap outlets' does not hold",
      _generic["has_violations"], False)
check("  but it is still reported", _generic["phrase_generic"], ["compatible with"])
check("  and the note says so rather than saying IP RISK",
      _generic["summary"].startswith("IP NOTE (no hold)"), True)

_brandy = ip(body("WORKS WITH YOUR PHONE — Works with recent iPhone 12, 13 and "
                  "14 series models."))
check("'works with recent iPhone' DOES hold", _brandy["has_violations"], True)
check("  and names what it found", _brandy["phrase_evidence"], ["works with iPhone"])
check("  under the IP RISK head", _brandy["summary"].startswith("IP RISK"), True)

# camelCase is the shape that carried the one real leak in the whole stored set.
check("a lower-case-initial brand is still caught",
      ip(body("PLUG AND PLAY — Compatible with macOS out of the box."))
      ["has_violations"], True)

# --- the scan must not read past the end of the clause ---------------------
check("a full stop ends the lookahead",
      ip(body("FITS MOST MIXERS — Compatible with circlip-style hubs. Check the "
              "underside of your stand mixer for the fitting."))["has_violations"],
      False)
check("a colon ends it too",
      ip(body("MAGNETIC BOARD — Works with magnets: Compatible with all "
              "magnet-backed items including fridge magnets."))["has_violations"],
      False)
check("and a comma ends it",
      ip(body("SWEDISH HERITAGE — Made by Selvora Limited, a Swedish brand "
              "trusted by anglers."), brand="Selvora Limited")["has_violations"],
      False)
# The comma guard must not hide a real name: a list's FIRST item is inside it.
check("  without hiding the first name in a list",
      ip(body("TOOL FIT — Compatible with Makita, Bosch and DeWalt "
              "batteries."))["has_violations"], True)

# --- words that name nobody --------------------------------------------
_own = ip(body("QUALITY BRANDED APPAREL — Each pair arrives in a branded hard "
               "zipper case with a microfibre cleaning cloth."))
check("'branded' on your own merchandise does not hold",
      _own["has_violations"], False)
check("  and is reported as note-only", _own["phrase_note_only"], ["branded"])
check("'universal fit' is an overclaim, not a trademark hold",
      ip(body("STRETCHY UNIVERSAL FIT — The naturally elastic neoprene "
              "accommodates most head sizes."))["has_violations"], False)

# --- but the unconditional claims still fire -------------------------------
check("'oem approved' still holds on its own",
      ip(body("GENUINE QUALITY — This part is OEM approved for peace of "
              "mind."))["has_violations"], True)
check("'manufacturer recommended' still holds",
      ip(body("TRUSTED — Manufacturer recommended for daily "
              "use."))["has_violations"], True)

# --- and the caps guess never holds, however many it finds -----------------
_many = ip(body("FEATURE PACKED — Three Modes, Battery Indicator, Tripod Base, "
                "Hanging Hook, Magnetic Mount, Folding Handle and Carry Strap."))
check("a pile of capitalised nouns is reported",
      len(_many["unknown_caps"]) > _rules.get("max_unrecognised", 4), True)
check("  but never holds the listing on its own", _many["has_violations"], False)
check("  and the note calls it unconfirmed",
      "unconfirmed" in _many["summary"], True)

# A competitor's brand is PROOF and still holds on its own -- that check is
# what the hold is for, and it is untouched.
check("a competitor's brand in the copy still holds",
      _cmp.check_ip_violations(body("BUILT TO LAST — A sturdy connector for "
                                    "your Hozelock system."),
                               "AltaboltaVoo", _rules,
                               ["Hozelock"])["has_violations"], True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
