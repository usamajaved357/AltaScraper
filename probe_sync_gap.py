# Why Sync cannot see a listing Amazon has published.
#
#     "the listing which i created using this app is now in amazon but after
#      clicking sync also i am not able to see it in my app"
#
# Sync does NOT read the Listings API. It builds the catalogue from
# GET_MERCHANT_LISTINGS_ALL_DATA merged with GET_MERCHANT_LISTINGS_INACTIVE_DATA
# (routes/live_routes.py:770, :929). So the question is not "is the listing on
# Amazon" -- it plainly is -- but "is it in those two reports".
#
# Step 1 is free: what did the last Sync actually store?
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SKU = "9.99_2Days_B0BP1HNW8G"
ASIN = "B0HJ2W3XZ1"
ACCOUNT = "nestwell_goods"
MKT = "UK"

from domain import live_snapshots as snap

rec = snap.get("config.json", ACCOUNT, MKT) or {}
items = rec.get("items") or []
print("=== what the app stored from the last Sync ===")
print("  account %s / %s" % (ACCOUNT, MKT))
print("  items stored      : %d" % len(items))
print("  snapshot age (s)  : %s" % snap.age_seconds(rec))
print("  report_source     : %s" % rec.get("report_source"))
print("  partial           : %s" % rec.get("partial"))

hit = [i for i in items if str(i.get("sku") or "").strip() == SKU]
hit_asin = [i for i in items if str(i.get("asin") or "").strip() == ASIN]
print("\n  this SKU in the snapshot : %s" % (json.dumps(hit[0])[:300] if hit else "NO"))
print("  this ASIN in the snapshot: %s" % ("yes" if hit_asin else "NO"))

# Anything else created today? If the snapshot has nothing recent at all, the
# gap is the snapshot's age rather than this one listing.
newest = sorted(items, key=lambda i: str(i.get("open_date") or ""), reverse=True)[:5]
print("\n  newest 5 by open_date:")
for i in newest:
    print("    %-28s %-12s %s" % (str(i.get("sku"))[:28], i.get("asin"),
                                  i.get("open_date")))
