# Find a listing that Amazon WILL accept under AltaboltaVoo, and name every
# barcode that is bound to an existing ASIN so they can be replaced.
#
#     "i am able to create a listing from the brand name nestwell goods but not
#      from AltaboltaVoo, this thing should be fixed"
#
# VALIDATION_PREVIEW only -- creates nothing, changes nothing.
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MID = "A1F83G8C2ARO7P"
BRAND = "AltaboltaVoo"

import accounts as _acc
from data.store import ListingStore

cfg = json.load(open("config.json", encoding="utf-8"))
acct = [x for x in cfg["accounts"] if x.get("id") == ACCOUNT][0]
seller = acct.get("seller_id")

rows = ListingStore(ACCOUNT, config_path="config.json").get_all_rows()
have = [r for r in rows if str(r.get("API Payload JSON") or "").strip()]

from sp_api.api import ListingsItemsV20210801
from sp_api.base import Marketplaces
li = ListingsItemsV20210801(credentials=_acc.account_creds(acct),
                            marketplace=Marketplaces.UK, timeout=90)

_ASIN = re.compile(r"\bB0[A-Z0-9]{8}\b")

print("%-30s %-14s %s" % ("SKU", "under Alta", "why / bound to"))
print("-" * 92)
works, bound = [], []
for r in have:
    sku = str(r.get("SKU") or "").strip()
    body = json.loads(r.get("API Payload JSON"))
    b = copy.deepcopy(body)
    at = b.get("attributes") or {}
    at["brand"] = [{"marketplace_id": MID, "language_tag": "en_GB", "value": BRAND}]
    at["manufacturer"] = [{"marketplace_id": MID, "language_tag": "en_GB",
                           "value": BRAND}]
    b["attributes"] = at
    try:
        res = li.put_listings_item(seller, sku, marketplaceIds=[MID],
                                   issueLocale="en_GB", body=b,
                                   mode="VALIDATION_PREVIEW")
        pay = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        print("%-30s %-14s %s" % (sku[:30], "call failed", str(e)[:40]))
        continue
    errs = [i for i in ((pay or {}).get("issues") or [])
            if str(i.get("severity", "")).upper() == "ERROR"]
    if not errs:
        works.append(sku)
        print("%-30s %-14s %s" % (sku[:30], "ACCEPTED", "-- would go live as " + BRAND))
        continue
    e = errs[0]
    code = str(e.get("code") or "")
    msg = str(e.get("message") or "")
    if code == "8541":
        a = _ASIN.findall(msg)
        bound.append((sku, str(r.get("UPC") or ""), a[0] if a else "?"))
        print("%-30s %-14s barcode %s is bound to %s"
              % (sku[:30], "blocked", str(r.get("UPC"))[:14], a[0] if a else "?"))
    elif code == "100550" or "connect your brand" in msg.lower():
        print("%-30s %-14s BRAND NOT PERMITTED" % (sku[:30], "blocked"))
    else:
        print("%-30s %-14s [%s] %s" % (sku[:30], "blocked", code, msg[:44]))

print("\n=== summary ===")
print("  accepted under %s        : %d" % (BRAND, len(works)))
print("  blocked by a bound barcode : %d" % len(bound))
if works:
    print("\n  These would list under %s right now:" % BRAND)
    for s in works:
        print("    %s" % s)
if bound:
    print("\n  These need a barcode that is not already in use:")
    for sku, upc, asin in bound:
        print("    %-30s current barcode %-16s bound to %s" % (sku[:30], upc, asin))
