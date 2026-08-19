"""RULE 1 -- the business model, enforced rather than promised.

    This app creates BRAND NEW Amazon listings under the owner's own brand
    names. It is NEVER doing "me too" / piggyback / offer-only listings on other
    sellers' ASINs. The ASIN in the SKU (price_days_ASIN) is a COMPETITOR
    REFERENCE used only during generation to pull product data. It is not the
    target listing.

    NEVER: send merchant_suggested_asin. NEVER: requirements LISTING_OFFER_ONLY.
    NEVER: a fake or AI-generated barcode.
    ALWAYS: requirements "LISTING", and the GTIN exemption when there is no
    real barcode.

WHY THIS TEST EXISTS NOW AND NOT BEFORE.

Rule 1 is the most important rule in this codebase and it had almost no test.
It turned out to be breakable. MEASURED: a row whose Attributes JSON contained
merchant_suggested_asin came through build_api_attributes with it INTACT, and
would have gone to Amazon beside requirements="LISTING" --

    attributes_json carries it -> merchant_suggested_asin present: True

which is one attribute turning a new own-brand product into an offer on
somebody else's ASIN. Two 'keep' sets preserve unknown-but-present fields, on
the sound general reasoning that a field which is there was put there for a
reason. Sound in general; wrong for the one field that changes what the listing
IS.

So the check is not "does the code look right". It builds a payload from a
deliberately poisoned row and looks at what comes out.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


import amazon_listing_generator as G  # noqa: E402

MID = "A1F83G8C2ARO7P"
PROPS = {k: {"type": "array"} for k in (
    "item_name", "brand", "product_description", "condition_type",
    "merchant_suggested_asin", "externally_assigned_product_identifier",
    "supplier_declared_has_product_identifier_exemption")}
REQUIRED = ["item_name", "brand"]
CFG = {"_config_path": os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "config.json"),
       "_account_id": "jack_uk", "marketplace_id": MID}


def build(row):
    return G.build_api_attributes(dict(row), "HOME", PROPS, REQUIRED, CFG)


BASE = {"SKU": "8.00_3Days_B0COMPETIT", "Title": "A Thing",
        "Brand": "Jack Reacherd", "Product Type": "HOME", "UPC": ""}

print("== merchant_suggested_asin cannot reach Amazon ==")
# The breach this test was written for. Poisoned through the attributes blob,
# which is what the AI writes and what a seller import carries.
a = build(dict(BASE, **{"Attributes JSON":
                        json.dumps({"merchant_suggested_asin":
                                    [{"value": "B0COMPETIT"}]})}))
check("dropped when it arrives in the attributes blob",
      "merchant_suggested_asin" in a, False)
# And through a plain column, the other way a sheet can carry it.
a = build(dict(BASE, merchant_suggested_asin="B0COMPETIT"))
check("  and when it arrives as a column", "merchant_suggested_asin" in a, False)
# The typed variant Amazon also accepts.
a = build(dict(BASE, **{"Attributes JSON":
                        json.dumps({"merchant_suggested_asin_type": [{"value": "ASIN"}]})}))
check("  and the _type variant with it", "merchant_suggested_asin_type" in a, False)

print("\n== it is dropped LAST, so nothing can re-add it ==")
# Enforced at the end of build_api_attributes, after every keep-set and after
# the identifier decision -- so Rule 1 is a property of the payload rather than
# a promise made by each of its callers.
SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "amazon_listing_generator.py"), encoding="utf-8").read()
i_drop = SRC.find('for _forbidden in ("merchant_suggested_asin"')
i_keep = SRC.find("_keep_unknown = {")
truthy("the drop exists", i_drop > 0)
truthy("  and comes AFTER the keep-set that would preserve it",
       i_keep > 0 and i_drop > i_keep)
truthy("  and it says so out loud when it fires", "Dropped %s" in SRC or
       "Dropped {_forbidden}" in SRC)

print("\n== every write to Amazon asks for a NEW LISTING ==")
# requirements decides what the submission IS. LISTING_OFFER_ONLY would make it
# an offer on an existing ASIN, which is the whole thing Rule 1 forbids.
WRITE_FILES = ["amazon_listing_generator.py", "api/amazon_listings.py"]
for f in WRITE_FILES:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
    if not os.path.exists(p):
        continue
    src = open(p, encoding="utf-8").read()
    body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))
    reqs = re.findall(r'"requirements":\s*"([A-Z_]+)"', body)
    truthy("  %s sets requirements" % f, reqs)
    check("    every one of them is LISTING (%s)" % f,
          sorted(set(reqs)), ["LISTING"])
    check("    and LISTING_OFFER_ONLY is never a value (%s)" % f,
          'requirements": "LISTING_OFFER_ONLY' in body, False)

print("\n== no barcode is ever invented ==")
# "Never send fake, placeholder, or AI-generated UPC/EAN barcodes to Amazon."
a = build(dict(BASE, UPC=""))
check("no barcode -> no identifier is sent",
      "externally_assigned_product_identifier" in a, False)
check("  and the GTIN exemption is claimed instead",
      "supplier_declared_has_product_identifier_exemption" in a, True)
truthy("  as a true value",
       a["supplier_declared_has_product_identifier_exemption"][0].get("value") is True)

# A REAL barcode is sent, and the exemption dropped -- claiming both would be
# telling Amazon two different things about the same product.
a = build(dict(BASE, UPC="5060541510005"))
if "externally_assigned_product_identifier" in a:
    check("a real barcode IS sent", True, True)
    check("  and the exemption is dropped with it",
          "supplier_declared_has_product_identifier_exemption" in a, False)
else:
    # Rejected by normalize_gtin -> exemption, which is also correct behaviour.
    check("a barcode that fails validation falls back to the exemption",
          "supplier_declared_has_product_identifier_exemption" in a, True)

# An obviously invented one must not be sent.
a = build(dict(BASE, UPC="000000000000"))
check("an all-zero barcode is not sent",
      "externally_assigned_product_identifier" in a, False)
check("  the exemption is claimed instead",
      "supplier_declared_has_product_identifier_exemption" in a, True)

print("\n== the SKU's ASIN is a reference, not the target ==")
# price_days_ASIN. The ASIN identifies the competitor product the data came
# from; it must never become the thing being listed.
a = build(dict(BASE, SKU="8.00_3Days_B0COMPETIT"))
blob = json.dumps(a)
check("the competitor ASIN is not sent as an identifier",
      "B0COMPETIT" in json.dumps(a.get("externally_assigned_product_identifier", "")),
      False)
check("  nor as a suggested ASIN", "merchant_suggested_asin" in a, False)

print("\n== the auto-fix loop cannot re-introduce one ==")
RT = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "routes", "listing_routes.py"), encoding="utf-8").read()
truthy("auto-fix strips identifier fields", "_ID_SKIP" in RT)
for f in ("externally_assigned_product_identifier", "merchant_suggested_asin"):
    truthy("  including %s" % f, f in RT)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
