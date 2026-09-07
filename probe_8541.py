# Amazon code 8541 on 11.96_2Days_B0FM82BDC5, and why auto-fix chased colour.
#
# Amazon's words:
#   "The '{color.value,color.standardized_values}' conflicts with 1 ASINs
#    (Merchant Green / Amazon Blue) for B0HJ3W6M84.
#    The 'standard_product_id' conflicts with 1 ASINs
#    (Merchant ["04545161767332"] / Amazon ["04545155187597"]) for B0HHXTKT3B."
#
# Two ASINs are named and neither is random:
#   B0HHXTKT3B  is THIS SKU's own ASIN
#   B0HJ3W6M84  is another listing on this same account
#
# So the question is not "what colour" -- it is which barcode this listing is
# being submitted with, and whose it is.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MKT, MID = "UK", "A1F83G8C2ARO7P"
SKU = "11.96_2Days_B0FM82BDC5"
SENT = "04545161767332"        # what Amazon says we sent
AMZ = "04545155187597"         # what Amazon says the ASIN already has

import accounts as _acc
from api import amazon_listings as AL
from data.store import ListingStore
from listing.barcode import normalize_gtin

print("=== what THIS APP holds for the row ===")
st = ListingStore(ACCOUNT, config_path="config.json")
rows = st.get_all_rows()
row = next((r for r in rows if str(r.get("SKU") or "").strip() == SKU), None)
if not row:
    print("  no row for %s" % SKU)
else:
    for k in ("SKU", "UPC", "Status", "Competitor ASIN", "Title", "Color",
              "Colour", "GTIN Exemption"):
        if k in row:
            print("  %-18s %s" % (k, str(row.get(k))[:70]))
    print("  normalize_gtin(UPC) -> %s" % (normalize_gtin(row.get("UPC")),))

print("\n=== who else on this account holds those two barcodes ===")
for code in (SENT, AMZ):
    want, _t = normalize_gtin(code)
    hits = []
    for r in rows:
        got, _t2 = normalize_gtin(r.get("UPC"))
        if got and want and got == want:
            hits.append((str(r.get("SKU")), str(r.get("Status"))))
    print("  %s (%s) -> %s" % (code, want, hits or "no row here has it"))

print("\n=== what AMAZON holds, per SKU ===")
a = [x for x in json.load(open("config.json", encoding="utf-8"))["accounts"]
     if x.get("id") == ACCOUNT][0]
res = AL.catalogue(_acc.account_creds(a), MKT, a.get("seller_id"), MID)
live = {i["sku"]: i for i in (res.get("items") or [])}
for sku, i in sorted(live.items()):
    if i.get("asin") in ("B0HHXTKT3B", "B0HJ3W6M84") or sku == SKU:
        print("  %-30s asin=%-12s barcode=%-16s title=%s"
              % (sku[:30], i.get("asin"), i.get("barcode") or "(none)",
                 str(i.get("title"))[:44]))

print("\n=== does the app's own clash checker see this? ===")
try:
    from domain import barcode_clash as BC
    print("  functions: %s" % [n for n in dir(BC) if not n.startswith("_")])
    for fn in ("clashes_for", "find", "check", "for_barcode", "lookup"):
        if hasattr(BC, fn):
            import inspect
            print("  %s%s" % (fn, inspect.signature(getattr(BC, fn))))
except Exception as e:
    print("  could not load: %s" % e)
