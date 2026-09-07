# What the "Not showing" tile is actually testing, on the real catalogue.
#
#     "when i click on not showing filter in the all listing page, it shows me
#      exactly 4 listings ... one of them is out of stock on amazon but is
#      displayed as live inactive in the app, one is live but shown as LIVE ...
#      one is 3 in 1 floor scrub which shows only live but is displayed under
#      this filter"
#
# liveItemIs(it, "live_notshowing") in static/js/listings.js reads it.status and
# matches on three substrings: "inactive", "suppress", "incomplete". So the
# question is what `status` each catalogue item is actually carrying -- and
# where that string came from.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MKT = "UK"
MID = "A1F83G8C2ARO7P"

import accounts as _acc
from api import amazon_listings as AL
from domain import live_snapshots as SNAP


def not_showing(status):
    """The exact test the tile uses."""
    s = str(status or "").lower()
    return ("inactive" in s) or ("suppress" in s) or ("incomplete" in s)


print("=== 1. what the SAVED snapshot holds (what the screen actually reads) ===")
rec = SNAP.get("config.json", ACCOUNT, MKT) or {}
items = rec.get("items") or []
print("  items: %d   source: %s   age: %ss"
      % (len(items), rec.get("report_source"), int(SNAP.age_seconds(rec) or 0)))
hits = [i for i in items if not_showing(i.get("status"))]
print("  MATCHING 'Not showing': %d" % len(hits))
for i in hits:
    print("     %-32s status=%-24r qty=%-5s asin=%s"
          % (str(i.get("sku"))[:32], i.get("status"), i.get("qty"), i.get("asin")))

from collections import Counter
print("\n  every status value in the snapshot:")
for v, n in Counter(str(i.get("status")) for i in items).most_common():
    print("     %-26r %d" % (v, n))

print("\n=== 2. what AMAZON says right now, per SKU ===")
a = [x for x in json.load(open("config.json", encoding="utf-8"))["accounts"]
     if x.get("id") == ACCOUNT][0]
res = AL.catalogue(_acc.account_creds(a), MKT, a.get("seller_id"), MID)
if res.get("status") != AL.OK:
    print("  could not read: %s" % res.get("error"))
    raise SystemExit(1)
live = {i["sku"]: i for i in res["items"]}
print("  listings: %d" % len(live))
print("\n  every amazon_status combination:")
for v, n in Counter(",".join(i.get("amazon_status") or [])
                    for i in res["items"]).most_common():
    print("     %-26r %d" % (v, n))

print("\n=== 3. where the snapshot and Amazon disagree ===")
print("  %-32s %-22s %-22s %s" % ("SKU", "snapshot status", "amazon status", "qty"))
n = 0
for sku, i in sorted(live.items()):
    snap = next((x for x in items if str(x.get("sku")) == sku), None)
    s_status = (snap or {}).get("status")
    a_status = ",".join(i.get("amazon_status") or [])
    mapped = i.get("status")
    if not_showing(s_status) != not_showing(mapped):
        n += 1
        print("  %-32s %-22r %-22r %s"
              % (sku[:32], s_status, a_status, i.get("qty")))
print("  disagreeing: %d" % n)

print("\n=== 4. the listing that says SUBMITTED but has an ASIN ===")
from data.store import ListingStore
st = ListingStore(ACCOUNT, config_path="config.json")
for r in st.get_all_rows():
    sku = str(r.get("SKU") or "").strip()
    stt = str(r.get("Status") or "").strip().upper()
    if stt in ("SUBMITTED", "PENDING") and sku:
        i = live.get(sku)
        print("  %-32s app=%-10s amazon=%-24s asin=%s"
              % (sku[:32], stt,
                 ",".join((i or {}).get("amazon_status") or []) or "(not on amazon)",
                 (i or {}).get("asin") or ""))
        print("       notes: %s" % str(r.get("Notes") or "")[:160])
