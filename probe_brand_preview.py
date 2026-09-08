# Will AMAZON accept AltaboltaVoo on the nestwell_goods account, or not?
#
#     "i am still getting that error, app is not letting me use the brand name"
#     -- and Seller Central shows "AltaboltaVoo branded ... Approved".
#
# Two claims that cannot both be true, and no amount of reading the app settles
# it. So: send one listing to Amazon in VALIDATION_PREVIEW mode -- which creates
# NOTHING, changes nothing, and returns Amazon's own issue list -- once with the
# brand as Nestwell Goods and once as AltaboltaVoo, everything else identical.
#
# Whatever comes back is Amazon's answer for THIS selling account, which is the
# question. CLAUDE.md Rule 4: read the reply, do not reason about it.
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MKT, MID = "UK", "A1F83G8C2ARO7P"

import accounts as _acc
from data.store import ListingStore

cfg = json.load(open("config.json", encoding="utf-8"))
acct = [x for x in cfg["accounts"] if x.get("id") == ACCOUNT][0]
seller = acct.get("seller_id")
print("account %s  seller %s" % (ACCOUNT, seller))

# A row with a recorded payload -- a real, complete listing body.
rows = ListingStore(ACCOUNT, config_path="config.json").get_all_rows()
row = None
for r in rows:
    p = str(r.get("API Payload JSON") or "").strip()
    if p and str(r.get("Status") or "").upper() != "LIVE":
        try:
            body = json.loads(p)
            if (body.get("attributes") or {}).get("brand"):
                row = (r, body)
                break
        except Exception:
            pass
if not row:
    print("no draft row has a recorded payload to test with")
    raise SystemExit(1)

r, body = row
# A SKU THAT DOES NOT EXIST, so nothing can attach to a real listing even by
# accident. VALIDATION_PREVIEW does not create, but the SKU is still the
# address, and using a live one would report on that listing rather than this
# question.
sku = "ZZTEST_BRANDCHECK_DELETE_ME"
print("testing with the payload from %s, under a throwaway SKU\n"
      % str(r.get("SKU"))[:40])

from sp_api.api import ListingsItemsV20210801
from sp_api.base import Marketplaces

li = ListingsItemsV20210801(credentials=_acc.account_creds(acct),
                            marketplace=Marketplaces.UK, timeout=90)


def try_brand(name):
    b = copy.deepcopy(body)
    at = b.get("attributes") or {}
    at["brand"] = [{"marketplace_id": MID, "language_tag": "en_GB", "value": name}]
    # The identifier would collide on its own and drown the answer we want.
    at.pop("externally_assigned_product_identifier", None)
    at.pop("supplier_declared_has_product_identifier_exemption", None)
    b["attributes"] = at
    try:
        res = li.put_listings_item(seller, sku, marketplaceIds=[MID],
                                   issueLocale="en_GB", body=b,
                                   mode="VALIDATION_PREVIEW")
        pay = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        print("  %-16s CALL FAILED: %s: %s" % (name, type(e).__name__, str(e)[:160]))
        return
    issues = (pay or {}).get("issues") or []
    errs = [i for i in issues if str(i.get("severity", "")).upper() == "ERROR"]
    print("  %-16s status=%-9s %d error(s)"
          % (name, (pay or {}).get("status"), len(errs)))
    for i in errs:
        code = str(i.get("code") or "")
        msg = str(i.get("message") or "")
        mark = "  <== BRAND" if code == "100550" or "connect your brand" in msg.lower() else ""
        print("      [%s] %s%s" % (code, msg[:150], mark))


print("=== Amazon's answer, same listing, two brands ===")
try_brand("Nestwell Goods")
print()
try_brand("AltaboltaVoo")
