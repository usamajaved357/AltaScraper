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

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
