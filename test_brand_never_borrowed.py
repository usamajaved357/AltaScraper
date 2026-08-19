"""The brand is the owner's. It is never read from the competitor.

    CLAUDE.md Rule 1: this app creates NEW listings under the owner's own brand
    names. The ASIN in the SKU is a COMPETITOR REFERENCE used only to pull
    product data. It is not the target listing.

WHAT WAS FOUND. A Brand Name box showed "YL" on a row whose Brand column says
"Nestwell Goods", and Amazon had flagged it. "YL" appears NOWHERE in the
database -- not in the row, not in the attributes, not in the live snapshot --
so it was not stored, it was SUGGESTED.

Every source /suggest reads belongs to somebody else: the eBay listing's item
specifics and the competitor ASIN's SP-API record. Both carry a Brand, and the
source lookup matches on field name, so asking it to fill "brand" hands back
theirs. Proven by calling the resolver directly with a synthetic source:

    brand = 'YL'   source = eBay

And auto-fix applies suggestions without being asked, so a run wrote another
company's brand onto the owner's listing.

TWO LOCKS, because one was clearly not enough:
  the route      supplies the owner's brand from the row instead of asking;
  the resolver   refuses to read a brand from any source at all, so a future
                 caller cannot reintroduce it by forgetting the first.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


import dashboard as D

# The sources really are the competitor's. This is the shape they arrive in.
SOURCES = {
    "ebay": {"Brand": "YL", "Material": "Aluminium", "Colour": "Blue"},
    "sp": {"brand": "YL", "material": "Aluminium", "color": "Blue"},
}
CFG = {"anthropic_api_key": ""}       # no AI: what the SOURCES gave, and only that

_real = D._load_schema
D._load_schema = lambda pt, *a, **k: {"enums": {}, "subfields": {}}


def resolve(fields):
    out = D._resolve_fields(CFG, list(fields), {}, SOURCES,
                            "Window Cleaning Kit Extendable Pole Squeegee 3m",
                            "SQUEEGEE", "UK")
    return {s["field"]: s for s in out}


print("== the competitor's brand is never offered ==")
got = resolve(["brand", "brand_name", "manufacturer", "material", "color"])
for f in ("brand", "brand_name", "manufacturer"):
    check("%s is not filled from a source" % f, got[f].get("value"), "")
    check("  and says where a brand comes from",
          "never" in str(got[f].get("note", "")).lower(), True)
    # Marked code-owned so the auto-fix loop does not try to apply an empty value.
    check("  and is code-owned, so auto-fix leaves it alone",
          bool(got[f].get("_code_owned")), True)

print("\n== everything else still fills from the source, as before ==")
check("material still comes from eBay", got["material"].get("value"), "Aluminium")
check("colour still comes from eBay", got["color"].get("value"), "Blue")

print("\n== a brand-ish sub-field is caught too ==")
got2 = resolve(["brand.value"])
check("brand.value is not filled either", got2["brand.value"].get("value"), "")

D._load_schema = _real

print("\n== the route answers with the OWNER's brand instead ==")
SRC = open(os.path.join(HERE, "routes", "listing_routes.py"), encoding="utf-8").read()
FN = SRC.split("def suggest():")[1].split("\n    @app.route")[0]
truthy("the route knows which fields are brand fields",
       '_BRAND_FIELDS = {"brand", "brand_name", "manufacturer"}' in FN)
truthy("  it reads the brand off the ROW",
       'str(row.get("Brand", "") or "").strip()' in FN)
truthy("  falling back to the account's configured brand",
       'cfg.get("brand_name", "")' in FN)
truthy("  and it removes them from the fields the sources are asked for",
       "_brand_asked = [f for f in fields" in FN)
truthy("  then answers them itself", 'for _bf in _brand_asked:' in FN)
# With no brand anywhere, inventing one is exactly the failure being fixed.
truthy("  with nothing invented when no brand is set",
       '"value": "", "source": "none"' in FN)

print("\n== the barcode rule it sits beside is untouched ==")
truthy("identifiers are still stripped", "_ID_SKIP = {" in FN)
for f in ("externally_assigned_product_identifier", "merchant_suggested_asin"):
    truthy("  %s still cannot be guessed" % f, f in FN)

print("\n== and the builder still sends the owner's brand ==")
GEN = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
truthy("build_api_attributes sets brand from the row",
       'put("brand", _shape_simple(props["brand"], brand, mid))' in GEN)
truthy("merchant_suggested_asin is still dropped outright",
       'for _forbidden in ("merchant_suggested_asin", "merchant_suggested_asin_type")' in GEN)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
