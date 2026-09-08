# Which identifier does this listing actually SEND, and is 8541 handled at all?
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SKU = "11.96_2Days_B0FM82BDC5"
from data.store import ListingStore
from listing.barcode import normalize_gtin, gtin_or_reason

st = ListingStore("nestwell_goods", config_path="config.json")
row = next(r for r in st.get_all_rows() if str(r.get("SKU") or "").strip() == SKU)

print("=== the identifier this row would send ===")
upc = row.get("UPC")
print("  UPC column      : %r" % upc)
print("  gtin_or_reason  : %r" % (gtin_or_reason(upc),))
print("  GTIN Exemption  : %r" % row.get("GTIN Exemption"))

print("\n=== is a second identifier hiding in Attributes JSON? ===")
raw = row.get("Attributes JSON") or "{}"
try:
    pa = json.loads(raw)
except Exception as e:
    pa = {}
    print("  unreadable: %s" % e)
for k in sorted(pa):
    if "identifier" in k or "product_id" in k or "gtin" in k or k == "color":
        print("  %-46s %s" % (k, json.dumps(pa[k])[:120]))
print("  (attributes stored: %d keys)" % len(pa))
blob = json.dumps(pa)
for code in ("4545161767332", "4545155187597", "4545944574867"):
    print("  %s in Attributes JSON: %s" % (code, code in blob))

print("\n=== what the last preview actually sent ===")
pay = row.get("API Payload JSON") or ""
if not pay.strip():
    print("  (no payload recorded)")
else:
    try:
        body = json.loads(pay)
        at = (body or {}).get("attributes") or {}
        print("  requirements: %s   productType: %s"
              % (body.get("requirements"), body.get("productType")))
        for k in ("externally_assigned_product_identifier",
                  "supplier_declared_has_product_identifier_exemption",
                  "merchant_suggested_asin", "color"):
            if k in at:
                print("  %-52s %s" % (k, json.dumps(at[k])[:140]))
        b = json.dumps(at)
        for code in ("4545161767332", "4545155187597", "4545944574867"):
            print("  %s in the sent payload: %s" % (code, code in b))
    except Exception as e:
        print("  unreadable: %s" % e)

print("\n=== and what Amazon said back, as stored ===")
from listing import api_issues as AI
rec = AI.parse(row.get("API Issues JSON"))
print("  at=%s mode=%s status=%s" % (rec.get("at"), rec.get("mode"), rec.get("status")))
for i in rec.get("issues") or []:
    print("  [%s] %s  fields=%s" % (i["severity"], i["code"], i["fields"]))
    print("       %s" % i["message"][:220])

print("\n=== does anything in the app understand code 8541? ===")
import subprocess
for f in ("static/js/amazon_errors.js", "static/js/autofix.js",
          "amazon_listing_generator.py", "listing/api_issues.py"):
    src = open(f, encoding="utf-8", errors="replace").read()
    print("  %-34s 8541:%-5s 'more than one ASIN':%s"
          % (f, "8541" in src, "more than one ASIN" in src))
