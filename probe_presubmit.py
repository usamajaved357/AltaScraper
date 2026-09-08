# What is about to be submitted on nestwell_goods, and what will be refused.
#
# Run before a batch submit. Reads only -- nothing is sent, nothing is changed.
# Every check here is one Amazon has already refused a listing over on this
# account, so this is a list of known refusals rather than a general opinion.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MKT, MID = "UK", "A1F83G8C2ARO7P"

from data.store import ListingStore
from domain import barcode_clash as BC
from listing.barcode import gtin_or_reason
from amazon_listing_generator import resolve_account_brand as R

cfg = json.load(open("config.json", encoding="utf-8"))
acct = [x for x in cfg["accounts"] if x.get("id") == ACCOUNT][0]
probe = {"_account_brands": [str(b).strip() for b in (acct.get("brands") or [])],
         "_account_brand": (acct.get("brands") or [""])[0]}

rows = ListingStore(ACCOUNT, config_path="config.json").get_all_rows()
# What Submit actually publishes.
READY = {"API_READY", "APPROVED"}
drafts = [r for r in rows
          if str(r.get("Status") or "").strip().upper() not in ("LIVE",)]

print("=== nestwell_goods: %d rows, %d not marked LIVE ===" % (len(rows), len(drafts)))
by_status = {}
for r in drafts:
    s = str(r.get("Status") or "(blank)").strip().upper()
    by_status[s] = by_status.get(s, 0) + 1
print("  statuses: %s" % by_status)
print("  Submit publishes only: %s" % ", ".join(sorted(READY)))

ready = [r for r in drafts
         if str(r.get("Status") or "").strip().upper() in READY]
print("\n=== %d row(s) Submit would actually send ===" % len(ready))

if not ready:
    print("  none — approve them first, or Submit will skip every row.")

problems = []
for r in ready:
    sku = str(r.get("SKU") or "").strip()
    brand = str(r.get("Brand") or "").strip()
    sent, _note = R(brand, probe)
    why = []

    # 1. THE BARCODE, which is what has actually refused listings here.
    code, _t, bad = gtin_or_reason(r.get("UPC"))
    if not code:
        why.append("no usable barcode (%s)" % (bad or "empty"))
    else:
        local = BC.others_with("config.json", code,
                               exclude_workspace=ACCOUNT, exclude_sku=sku)
        if local:
            first = local[0]
            why.append("barcode also on %s/%s%s"
                       % (first["workspace_id"], first["sku"],
                          " (LIVE)" if first["live"] else ""))
        amz = BC.on_amazon("config.json", ACCOUNT, MKT, code)
        if amz.get("owners"):
            o = amz["owners"][0]
            why.append("barcode already owned by %s on Amazon (%s)"
                       % (o["asin"], (o["brand"] or o["title"] or "")[:30]))
        elif not amz.get("checked"):
            why.append("barcode not checkable against Amazon")

    # 2. THE BRAND. Not a block in this app any more -- Amazon decides -- but
    #    it is the refusal he is living with, so it is worth naming here.
    if sent.strip().lower() == "altaboltavoo":
        why.append("brand AltaboltaVoo — Amazon refuses with 100550 until it "
                   "is connected to THIS account")

    if why:
        problems.append((sku, sent, why))
    print("  %-30s brand=%-16s %s"
          % (sku[:30], sent[:16], "; ".join(why) if why else "looks sendable"))

print("\n=== %d of %d would hit something Amazon has refused before ==="
      % (len(problems), len(ready)))
