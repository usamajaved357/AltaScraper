# Can searchListingsItems supply EVERY field the catalogue screen draws?
#
# _parse_listings_report (dashboard.py:2765) yields exactly these keys, and the
# replacement has to yield the same ones or the screen quietly loses a column:
#   sku asin title price qty status brand fulfillment ship_group barcode
#
# summaries/offers/fulfillmentAvailability cover the first six. brand,
# ship_group and barcode live in `attributes`, which costs payload -- so measure
# whether they are actually there and what the page weighs.
import json
import time
import urllib.request
import urllib.parse

ACCOUNT = "nestwell_goods"
mid = "A1F83G8C2ARO7P"
endpoint = "https://sellingpartnerapi-eu.amazon.com"

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == ACCOUNT][0]
seller = a.get("seller_id") or c.get("seller_id")

body = urllib.parse.urlencode({
    "grant_type": "refresh_token", "refresh_token": a["refresh_token"],
    "client_id": a["lwa_client_id"], "client_secret": a["lwa_client_secret"],
}).encode()
req = urllib.request.Request(
    "https://api.amazon.com/auth/o2/token", data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"})
access = json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]
H = {"x-amz-access-token": access, "Accept": "application/json"}

t0 = time.time()
url = endpoint + "/listings/2021-08-01/items/%s?" % seller + urllib.parse.urlencode({
    "marketplaceIds": mid, "pageSize": 20,
    "includedData": "summaries,offers,fulfillmentAvailability,attributes",
})
raw = urllib.request.urlopen(
    urllib.request.Request(url, headers=H), timeout=60).read()
doc = json.loads(raw)
print("one page of 20, with attributes: %d bytes, %.1fs"
      % (len(raw), time.time() - t0))

items = doc.get("items") or []
have = {"brand": 0, "ship_group": 0, "barcode": 0, "price": 0, "qty": 0,
        "title": 0, "asin": 0, "status": 0}
for it in items:
    at = it.get("attributes") or {}
    s = (it.get("summaries") or [{}])[0]
    if at.get("brand"):
        have["brand"] += 1
    if at.get("merchant_shipping_group"):
        have["ship_group"] += 1
    if at.get("externally_assigned_product_identifier"):
        have["barcode"] += 1
    if it.get("offers"):
        have["price"] += 1
    if it.get("fulfillmentAvailability"):
        have["qty"] += 1
    if s.get("itemName"):
        have["title"] += 1
    if s.get("asin"):
        have["asin"] += 1
    if s.get("status"):
        have["status"] += 1

print("\nof %d listings on this page, how many carry each field:" % len(items))
for k in ("sku", "asin", "title", "price", "qty", "status", "brand",
          "ship_group", "barcode"):
    if k == "sku":
        print("  %-12s %d" % (k, len([i for i in items if i.get("sku")])))
    else:
        print("  %-12s %d" % (k, have.get(k, 0)))

if items:
    at = items[0].get("attributes") or {}
    print("\nsample values from the first listing:")
    print("  brand      = %s" % json.dumps(at.get("brand"))[:160])
    print("  ship_group = %s" % json.dumps(at.get("merchant_shipping_group"))[:160])
    print("  barcode    = %s" % json.dumps(
        at.get("externally_assigned_product_identifier"))[:200])
    print("  fulfil     = %s" % json.dumps(
        items[0].get("fulfillmentAvailability"))[:200])
    print("  handling   = %s" % json.dumps(
        at.get("fulfillment_availability"))[:250])
    print("\n  attribute keys available: %d" % len(at))
