# "i clicked on the handling time changed it to 2 ... but still app shows 3"
#
# Two numbers live on a row and only one of them can be typed:
#   handling_days   what the APP holds -- the editable one
#   handling_time   what AMAZON holds -- read back from the catalogue
# _handCell (static/js/listings.js:1566) shows Amazon's when the listing is
# live, and warns when the two disagree.
#
# So: did the edit reach the store at all? Read the store directly rather than
# reasoning about the write path.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MKT = "UK"
MID = "A1F83G8C2ARO7P"

from data.store import ListingStore

st = ListingStore(ACCOUNT, config_path="config.json")
rows = st.get_all_rows()
print("=== what the APP stores ===")
print("  rows: %d" % len(rows))
counts = {}
for r in rows:
    v = str(r.get("handling_days", "") or "").strip() or "(blank)"
    counts[v] = counts.get(v, 0) + 1
print("  handling_days across the store: %s" % counts)

# What Amazon holds, for the same SKUs, from the call the catalogue now uses.
import accounts as _acc
from api import amazon_listings as AL

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == ACCOUNT][0]
res = AL.catalogue(_acc.account_creds(a), MKT, a.get("seller_id"), MID)
amz = {}
if res.get("status") == AL.OK:
    for i in res["items"]:
        amz[i["sku"]] = i.get("handling_time", "")
print("\n=== what AMAZON holds ===")
ac = {}
for v in amz.values():
    k = str(v or "").strip() or "(blank)"
    ac[k] = ac.get(k, 0) + 1
print("  listings: %d   handling: %s" % (len(amz), ac))

print("\n=== the rows where they disagree ===")
n = 0
for r in rows:
    sku = str(r.get("sku", "") or "")
    ours = str(r.get("handling_days", "") or "").strip()
    theirs = str(amz.get(sku, "") or "").strip()
    if not theirs or not ours:
        continue
    if ours != theirs:
        n += 1
        if n <= 15:
            print("  %-30s app=%-4s amazon=%-4s  status=%s"
                  % (sku[:30], ours, theirs, r.get("status")))
print("  total disagreeing: %d" % n)

print("\n=== is the column even writable / present? ===")
from data import column_map as CM
print("  'Handling Days' -> %s" % CM.HEADER_TO_COL.get("Handling Days")
      if hasattr(CM, "HEADER_TO_COL") else "  (map shape differs)")
try:
    import dashboard as D
    print("  editable columns include it: %s"
          % ("Handling Days" in getattr(D, "_EDITABLE_COLS", set())))
except Exception as e:
    print("  could not read _EDITABLE_COLS: %s" % str(e)[:120])
