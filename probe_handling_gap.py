# Which live listings actually have an editable draft row, and where the two
# handling numbers disagree.
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.store import ListingStore
import accounts as _acc
from api import amazon_listings as AL

st = ListingStore("nestwell_goods", config_path="config.json")
rows = st.get_all_rows()
by = {str(r.get("SKU") or "").strip(): r for r in rows}

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == "nestwell_goods"][0]
res = AL.catalogue(_acc.account_creds(a), "UK", a.get("seller_id"),
                   "A1F83G8C2ARO7P")
live = res.get("items") or []

print("live on amazon        : %d" % len(live))
print("store rows            : %d" % len(rows))
have = [i for i in live if i["sku"] in by]
print("live WITH a draft row : %d" % len(have))
print("live with NO draft row: %d   <- these draw a READ-ONLY box"
      % (len(live) - len(have)))

cnt = collections.Counter(
    str(by[i["sku"]].get("Handling Days") or "") for i in have)
print("their stored Handling Days: %s" % dict(cnt))

print("\n%-32s %-5s %-5s" % ("SKU", "app", "amz"))
n = 0
for i in have:
    ours = str(by[i["sku"]].get("Handling Days") or "").strip()
    amz = str(i.get("handling_time") or "").strip()
    if ours != amz:
        n += 1
        if n <= 10:
            print("%-32s %-5s %-5s" % (i["sku"][:32], ours, amz))
print("total disagreeing: %d of %d" % (n, len(have)))

print("\n=== the SKUs Amazon has that this app has no row for ===")
for i in live:
    if i["sku"] not in by:
        print("  %-32s amz handling=%s" % (i["sku"][:32], i.get("handling_time")))
