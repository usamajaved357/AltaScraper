# Does the brand name "AltaboltaVoo" already exist in Amazon's UK catalogue,
# and on what?
#
# The brand experiment showed Amazon treats it differently from a name it has
# never seen:
#
#     Zqvurtleplinth  (invented)  -> 5665   "brand name has not been approved"
#     Altabolta Voo   (spaced)    -> 5665   "brand name has not been approved"
#     AltaboltaVoo                -> 100550 global_catalog_owner
#     altaboltavoo    (lowercase) -> 100550 global_catalog_owner
#
# 5665 is "Amazon does not know this name, ask for approval". 100550 is
# "Amazon knows this name and you are not its owner". So the name is already in
# the catalogue, case-insensitively, and the question is what carries it.
#
# Read-only: searchCatalogItems. Two calls, well inside the 2/sec limit.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MID = "A1F83G8C2ARO7P"
BRAND = "AltaboltaVoo"

import accounts as _acc

cfg = json.load(open("config.json", encoding="utf-8"))
acct = [x for x in cfg["accounts"] if x.get("id") == ACCOUNT][0]

from sp_api.api import CatalogItemsV20220401
from sp_api.base import Marketplaces
cat = CatalogItemsV20220401(credentials=_acc.account_creds(acct),
                            marketplace=Marketplaces.UK, timeout=90)


def show(label, **kw):
    print("\n" + "=" * 74)
    print(label)
    try:
        res = cat.search_catalog_items(
            marketplaceIds=[MID],
            includedData=["summaries", "identifiers"],
            pageSize=20, **kw)
        pay = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        print("   call failed: %s: %s" % (type(e).__name__, str(e)[:160]))
        return
    items = (pay or {}).get("items") or []
    total = (pay or {}).get("numberOfResults")
    print("   numberOfResults=%s   returned=%d" % (total, len(items)))
    for it in items:
        asin = it.get("asin")
        sums = it.get("summaries") or []
        s = sums[0] if sums else {}
        print("   %-12s brand=%-20s %s"
              % (asin, str(s.get("brand"))[:20], str(s.get("itemName"))[:44]))


show("A  brandNames=[%s]" % BRAND, brandNames=[BRAND])
show("B  keywords=[%s]" % BRAND, keywords=[BRAND])
