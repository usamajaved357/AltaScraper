# Is 100550 about UNREGISTERED brands, or about THIS PARTICULAR NAME?
#
#     "you are wrong who said we need brand registry to create a listing under
#      a brand name"
#
# He is right: Amazon does not require Brand Registry to create an ASIN under a
# brand name. So the earlier reading of 100550 -- "connect your brand" -- was
# never established, only assumed. This settles it with one experiment.
#
# Same listing, same payload, same second, only the brand string changed:
#
#     A  Nestwell Goods    -- the control, known to pass
#     B  AltaboltaVoo      -- what he wants, known to fail
#     C  an INVENTED name  -- cannot exist in Amazon's catalogue, so it is
#                             definitionally unregistered and unowned
#     D  altaboltavoo      -- same name, different case
#     E  Altabolta Voo     -- same name, spaced
#
# Read it like this:
#   C passes  -> unregistered brands are fine. The problem is the STRING
#                "AltaboltaVoo" specifically -- Amazon already knows it and
#                says this account is not its global_catalog_owner.
#   C fails   -> the account cannot create an ASIN under ANY brand it has not
#                had linked. Nestwell Goods passes only because it is linked.
#                Nothing to do with registration.
#
# VALIDATION_PREVIEW throughout: it creates nothing and changes nothing.
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MID = "A1F83G8C2ARO7P"

# One of the two drafts whose barcode is NOT bound to anything, so error 8541
# cannot fire and mask the answer.
SKU = "13.95_2Days_B0GTZ86HRK"

# Deliberately meaningless. If this string exists as a brand on Amazon the
# experiment is void, which is why it is not a word.
INVENTED = "Zqvurtleplinth"

TRIALS = [
    ("A  Nestwell Goods  (control)", "Nestwell Goods"),
    ("B  AltaboltaVoo    (his)", "AltaboltaVoo"),
    ("C  %-16s (invented)" % INVENTED, INVENTED),
    ("D  altaboltavoo    (lowercase)", "altaboltavoo"),
    ("E  Altabolta Voo   (spaced)", "Altabolta Voo"),
]

import accounts as _acc
from data.store import ListingStore

cfg = json.load(open("config.json", encoding="utf-8"))
acct = [x for x in cfg["accounts"] if x.get("id") == ACCOUNT][0]
seller = acct.get("seller_id")

rows = {str(r.get("SKU") or "").strip(): r
        for r in ListingStore(ACCOUNT, config_path="config.json").get_all_rows()}
row = rows[SKU]
body = json.loads(row.get("API Payload JSON"))

from sp_api.api import ListingsItemsV20210801
from sp_api.base import Marketplaces
li = ListingsItemsV20210801(credentials=_acc.account_creds(acct),
                            marketplace=Marketplaces.UK, timeout=90)


def run(brand):
    b = copy.deepcopy(body)
    at = b.get("attributes") or {}
    at["brand"] = [{"marketplace_id": MID, "language_tag": "en_GB", "value": brand}]
    at["manufacturer"] = [{"marketplace_id": MID, "language_tag": "en_GB",
                           "value": brand}]
    b["attributes"] = at
    try:
        res = li.put_listings_item(seller, SKU, marketplaceIds=[MID],
                                   issueLocale="en_GB", body=b,
                                   mode="VALIDATION_PREVIEW")
        pay = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        return None, [("CALL", "%s: %s" % (type(e).__name__, str(e)[:120]), [])]
    errs = [(str(i.get("code") or ""), str(i.get("message") or ""),
             i.get("attributeNames") or [])
            for i in ((pay or {}).get("issues") or [])
            if str(i.get("severity", "")).upper() == "ERROR"]
    return (pay or {}).get("status"), errs


print("account : %s   sku: %s" % (ACCOUNT, SKU))
print("barcode : %s   (not bound to any ASIN, so 8541 cannot fire)"
      % row.get("UPC"))
print("=" * 78)

verdict = {}
for tag, brand in TRIALS:
    status, errs = run(brand)
    print("\n%s" % tag)
    print("    status=%s  %d error(s)" % (status, len(errs)))
    brandish = False
    for code, msg, names in errs:
        flag = ""
        if code == "100550" or "global_catalog_owner" in (names or []):
            flag = "   <== BRAND"
            brandish = True
        print("      [%s] %s%s" % (code, msg[:110], flag))
        if names:
            print("           attributeNames: %s" % (names,))
    verdict[brand] = (not errs, brandish)

print("\n" + "=" * 78)
print("=== VERDICT ===")
inv_ok, inv_brand = verdict.get(INVENTED, (False, False))
alta_ok, alta_brand = verdict.get("AltaboltaVoo", (False, False))
if inv_ok and alta_brand:
    print("  An INVENTED, definitely-unregistered brand is ACCEPTED, and")
    print("  AltaboltaVoo is refused with the brand error. So registration is")
    print("  irrelevant -- Amazon already knows the string 'AltaboltaVoo' and")
    print("  says this selling account is not its owner in the catalogue.")
elif inv_brand and alta_brand:
    print("  The invented brand is refused the SAME way. So this is not about")
    print("  the name and not about registration: this account may only create")
    print("  ASINs under brands already linked to it.")
elif inv_ok and alta_ok:
    print("  Both accepted. The brand is not the blocker on this listing at all.")
else:
    print("  Mixed result -- read the per-trial output above, do not summarise.")
