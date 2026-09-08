# CAN this account create ANY listing under AltaboltaVoo?
#
#     "i am able to create a listing from the brand name nestwell goods but not
#      from AltaboltaVoo, this thing should be fixed"
#
# Every test so far used a barcode already bound to a Nestwell-Goods ASIN, so
# every failure could be explained twice over and none of them settled it. This
# separates the two causes by previewing the SAME listing three ways:
#
#     A  brand Nestwell Goods, barcode as-is   -> the control
#     B  brand AltaboltaVoo,  barcode as-is    -> what he sees
#     C  brand AltaboltaVoo,  NO barcode       -> Amazon cannot match on the
#                                                 identifier, so anything it
#                                                 says about the brand is about
#                                                 THE BRAND
#
# If C never mentions 100550 or the brand, the brand is permitted and the whole
# problem is bound barcodes. If C does, the brand is genuinely blocked.
#
# VALIDATION_PREVIEW throughout: it creates nothing and changes nothing.
import copy
import json
import os
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
print("listings with a recorded payload: %d" % len(have))

from sp_api.api import ListingsItemsV20210801
from sp_api.base import Marketplaces
li = ListingsItemsV20210801(credentials=_acc.account_creds(acct),
                            marketplace=Marketplaces.UK, timeout=90)


def run(sku, body, brand, drop_id):
    b = copy.deepcopy(body)
    at = b.get("attributes") or {}
    at["brand"] = [{"marketplace_id": MID, "language_tag": "en_GB", "value": brand}]
    at["manufacturer"] = [{"marketplace_id": MID, "language_tag": "en_GB",
                           "value": brand}]
    if drop_id:
        at.pop("externally_assigned_product_identifier", None)
    b["attributes"] = at
    try:
        res = li.put_listings_item(seller, sku, marketplaceIds=[MID],
                                   issueLocale="en_GB", body=b,
                                   mode="VALIDATION_PREVIEW")
        pay = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        return None, [("CALL", "%s: %s" % (type(e).__name__, str(e)[:100]))]
    issues = (pay or {}).get("issues") or []
    out = [(str(i.get("code") or ""), str(i.get("message") or ""))
           for i in issues if str(i.get("severity", "")).upper() == "ERROR"]
    return (pay or {}).get("status"), out


def show(tag, status, errs):
    print("    %-34s status=%-8s %d error(s)" % (tag, status, len(errs)))
    for code, msg in errs:
        brandish = ("100550" in code) or ("connect your brand" in msg.lower())
        print("       [%s] %s%s" % (code, msg[:120],
                                    "   <== BRAND PERMISSION" if brandish else ""))


brand_blocked = 0
tested = 0
for r in have[:4]:
    sku = str(r.get("SKU") or "").strip()
    body = json.loads(r.get("API Payload JSON"))
    print("\n" + "=" * 74)
    print("%s   %s" % (sku, str(r.get("Title"))[:44]))
    tested += 1

    s1, e1 = run(sku, body, "Nestwell Goods", False)
    show("A  Nestwell Goods + barcode", s1, e1)
    s2, e2 = run(sku, body, BRAND, False)
    show("B  AltaboltaVoo  + barcode", s2, e2)
    s3, e3 = run(sku, body, BRAND, True)
    show("C  AltaboltaVoo  NO barcode", s3, e3)

    if any(("100550" in c) or ("connect your brand" in m.lower()) for c, m in e3):
        brand_blocked += 1

print("\n" + "=" * 74)
print("=== VERDICT over %d listing(s) ===" % tested)
if brand_blocked:
    print("  Amazon BLOCKS the brand on this account (%d of %d showed 100550 "
          "with no barcode in play)." % (brand_blocked, tested))
else:
    print("  Amazon does NOT block the brand. With the barcode removed -- so it")
    print("  cannot match an existing ASIN -- not one preview complained about")
    print("  AltaboltaVoo. Every failure in B is a BARCODE already bound to an")
    print("  ASIN branded Nestwell Goods, which is what the old brand swap")
    print("  created. A barcode not already in use will list under AltaboltaVoo.")
