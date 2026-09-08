# Which ACCOUNT is AltaboltaVoo actually connected to?
#
#     "still amazon is saying You need to connect your brand AltaboltaVoo with
#      your account ... i told you this is not brand registry thing, i am
#      allowed to use this name"
#
# He is allowed to use it -- and Manage Your Brands links a brand to ONE SELLING
# ACCOUNT at a time. B0H8SYL36V carries brand AltaboltaVoo and is
# jack_uk/5.98_3Days_B0F7RQLCKC. So the question worth answering before
# theorising: which of his accounts have LIVE listings under this brand, and is
# nestwell_goods one of them?
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BRAND = "AltaboltaVoo"

import accounts as _acc
from api import amazon_listings as AL
from data.store import ListingStore
from domain import live_snapshots as SNAP

cfg = json.load(open("config.json", encoding="utf-8"))

print("=== what each account CLAIMS in its settings ===")
for a in cfg.get("accounts", []):
    print("  %-18s brands=%s" % (a.get("id"), a.get("brands")))

print("\n=== live listings on Amazon carrying that brand, per account ===")
for a in cfg.get("accounts", []):
    aid = a.get("id")
    if not (a.get("refresh_token") and a.get("seller_id")):
        print("  %-18s no credentials" % aid)
        continue
    mkt = "US" if str(a.get("default_marketplace") or "").upper() == "US" else "UK"
    mid = _acc.marketplace_id(mkt) or ""
    res = AL.catalogue(_acc.account_creds(a), mkt, a.get("seller_id"), mid)
    if res.get("status") != AL.OK:
        # Fall back to what we already hold, so a 403 does not blank the answer.
        rec = SNAP.get("config.json", aid, mkt) or {}
        items = rec.get("items") or []
        src = "stored snapshot"
    else:
        items = res["items"]
        src = "Amazon, now"
    hits = [i for i in items
            if str(i.get("brand") or "").strip().lower() == BRAND.lower()]
    print("  %-18s (%s, %s) %d of %d listing(s) are %s"
          % (aid, mkt, src, len(hits), len(items), BRAND))
    for h in hits[:4]:
        print("       %-30s %-12s %s"
              % (str(h.get("sku"))[:30], h.get("asin"),
                 str(h.get("title"))[:40]))

print("\n=== rows in the app using that brand, per account ===")
for a in cfg.get("accounts", []):
    aid = a.get("id")
    try:
        rows = ListingStore(aid, config_path="config.json").get_all_rows()
    except Exception:
        continue
    n = [r for r in rows
         if str(r.get("Brand") or "").strip().lower() == BRAND.lower()]
    if n:
        print("  %-18s %d row(s)" % (aid, len(n)))
        for r in n[:5]:
            print("       %-30s status=%s"
                  % (str(r.get("SKU"))[:30], r.get("Status")))
