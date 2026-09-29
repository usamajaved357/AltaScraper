"""A remembered per-type default never carries a brand, name, identifier or offer.

attribute_defaults.json is shared by EVERY account, and the generator fills any
attribute a new draft lacks from it. It used to remember every filled attribute,
so one account's `brand` could land on another account's brand-new listing --
CLAUDE.md Rule 1 (Milestone 2, 28 Sep 2026). Checked on save, on load, and on a
file written before the rule existed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from listing import attribute_defaults as AD                           # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


print("\n1. what a default may hold")
saved = {"brand": "Jack Reacherd", "manufacturer": "Jack Reacherd",
         "brand.value": "Jack Reacherd", "item_name": "A thing",
         "externally_assigned_product_identifier": "5012345678900",
         "supplier_declared_has_product_identifier_exemption": "true",
         "merchant_suggested_asin": "B0G1K5B7QS", "list_price": "9.99",
         "other_product_image_locator_1": "http://x/y.jpg",
         "swatch_product_image_locator": "http://x/s.jpg",
         "fulfillment_quantity": "12", "Brand": "Selvora",
         "is_assembly_required": "false", "material": "Steel",
         "size_system": "UK"}
kept = AD.strip_identity(saved)
check("the judgment fields are kept",
      sorted(kept), ["is_assembly_required", "material", "size_system"])
for k in ("brand", "manufacturer", "brand.value", "item_name",
          "externally_assigned_product_identifier",
          "supplier_declared_has_product_identifier_exemption",
          "merchant_suggested_asin", "list_price", "other_product_image_locator_1",
          "swatch_product_image_locator", "fulfillment_quantity", "Brand"):
    check("  %s is never remembered" % k, k in kept, False)

print("\n2. a file written before the rule is cleaned as it is read")
old_file = {"HOME": {"brand": "Selvora", "material": "Wood"},
            "TOOLS": {"manufacturer": "Green Haven"}, "junk": "not a dict"}
check("brand gone, material kept, junk dropped",
      AD.clean_file_data(old_file), {"HOME": {"material": "Wood"}, "TOOLS": {}})

print("\n3. both doors use it")
UI = open(os.path.join(HERE, "routes", "ui_routes.py"), encoding="utf-8").read()
check("save strips identity", "_adef.strip_identity(attrs)" in UI, True)
check("  and cleans the whole file it writes", "_adef.clean_file_data(data)" in UI, True)
check("  and writes it atomically", "write_json_atomic(path, data" in UI, True)
GEN = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
_ld = GEN[GEN.index("def _load_attr_defaults"):]
_ld = _ld[:_ld.index("\ndef ")]
check("the generator cleans what it loads", "_clean_defaults(" in _ld, True)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
print("FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
