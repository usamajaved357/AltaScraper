# Find a draft with a CLEAN barcode and preview it under AltaboltaVoo.
#
#     "use the brand name AltaboltaVoo on a draft listing preview it and check
#      if some error appears. if there is a gtin error, use a listing which dont
#      have that gtin error"
#
# VALIDATION_PREVIEW only. It creates nothing and changes nothing -- it is the
# same call the app's own Preview makes, and Amazon answers with its issue list.
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MKT, MID = "UK", "A1F83G8C2ARO7P"
BRAND = "AltaboltaVoo"

import accounts as _acc
from data.store import ListingStore
from domain import barcode_clash as BC
from listing.barcode import gtin_or_reason

cfg = json.load(open("config.json", encoding="utf-8"))
acct = [x for x in cfg["accounts"] if x.get("id") == ACCOUNT][0]
seller = acct.get("seller_id")

rows = ListingStore(ACCOUNT, config_path="config.json").get_all_rows()
drafts = [r for r in rows
          if str(r.get("Status") or "").upper() not in ("LIVE",)
          and str(r.get("API Payload JSON") or "").strip()]
print("drafts with a recorded payload: %d" % len(drafts))

print("\n=== looking for one with a barcode nobody else owns ===")
chosen = None
looked = 0
for r in drafts:
    if chosen or looked >= 12:            # 2 catalogue calls/sec -- stay polite
        break
    sku = str(r.get("SKU") or "").strip()
    code, _t, why = gtin_or_reason(r.get("UPC"))
    if not code:
        print("  %-30s skipped: %s" % (sku[:30], (why or "no barcode")[:40]))
        continue
    local = BC.others_with("config.json", code,
                           exclude_workspace=ACCOUNT, exclude_sku=sku)
    if local:
        print("  %-30s skipped: also on %s/%s"
              % (sku[:30], local[0]["workspace_id"], local[0]["sku"][:18]))
        continue
    looked += 1
    amz = BC.on_amazon("config.json", ACCOUNT, MKT, code)
    if amz.get("owners"):
        print("  %-30s skipped: barcode owned by %s on Amazon"
              % (sku[:30], amz["owners"][0]["asin"]))
        continue
    if not amz.get("checked"):
        print("  %-30s skipped: could not check Amazon" % sku[:30])
        continue
    print("  %-30s CLEAN barcode %s" % (sku[:30], code))
    chosen = r

if not chosen:
    print("\nno draft found with a demonstrably clean barcode in the first %d "
          "checked" % looked)
    raise SystemExit(1)

sku = str(chosen.get("SKU") or "").strip()
body = json.loads(chosen.get("API Payload JSON"))
print("\n=== previewing %s under brand %r ===" % (sku, BRAND))
print("  title: %s" % str(chosen.get("Title"))[:60])

from sp_api.api import ListingsItemsV20210801
from sp_api.base import Marketplaces

li = ListingsItemsV20210801(credentials=_acc.account_creds(acct),
                            marketplace=Marketplaces.UK, timeout=90)


def preview(brand_name):
    b = copy.deepcopy(body)
    at = b.get("attributes") or {}
    at["brand"] = [{"marketplace_id": MID, "language_tag": "en_GB",
                    "value": brand_name}]
    b["attributes"] = at
    try:
        res = li.put_listings_item(seller, sku, marketplaceIds=[MID],
                                   issueLocale="en_GB", body=b,
                                   mode="VALIDATION_PREVIEW")
        pay = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        print("  %-16s CALL FAILED %s: %s" % (brand_name, type(e).__name__,
                                              str(e)[:150]))
        return None
    issues = (pay or {}).get("issues") or []
    errs = [i for i in issues if str(i.get("severity", "")).upper() == "ERROR"]
    print("\n  brand=%-16s status=%-9s %d error(s)"
          % (brand_name, (pay or {}).get("status"), len(errs)))
    for i in errs:
        code = str(i.get("code") or "")
        msg = str(i.get("message") or "")
        flag = "   <== BRAND" if code == "100550" else ""
        print("     [%s] %s%s" % (code, msg, flag)); print("           attributeNames: %s" % (i.get("attributeNames"),))
    if not errs:
        print("     no errors â€” Amazon would accept this listing")
    return errs


e_own = preview("Nestwell Goods")
e_alt = preview(BRAND)

print("\n=== verdict ===")
if e_alt is None or e_own is None:
    print("  could not complete the comparison")
else:
    brand_errs = [i for i in e_alt if str(i.get("code")) == "100550"]
    if brand_errs:
        print("  AMAZON REFUSES THE BRAND on this account. Not the app.")
    else:
        print("  Amazon does NOT refuse %s. Errors under both brands: %d vs %d"
              % (BRAND, len(e_own), len(e_alt)))
