# Report vs API, measured on the real account, before changing what Sync reads.
#
#     "if api gives more accurate data and quick use it instead of reports, use
#      what do you think is better"
#
# The answer has to be measured, not assumed, and on three axes -- because a
# source that is faster but knows less is not better:
#
#   COVERAGE  does it contain every listing, including the new one the report
#             is missing?
#   FIELDS    does it carry what the catalogue screen actually draws -- title,
#             ASIN, status, PRICE, QUANTITY?
#   COST      how many requests and how long, against Amazon's limits?
#
# Nothing here writes anything.
import json
import time
import urllib.request
import urllib.parse
import urllib.error

ACCOUNT = "nestwell_goods"
NEW_SKU = "9.99_2Days_B0BP1HNW8G"
mid = "A1F83G8C2ARO7P"
endpoint = "https://sellingpartnerapi-eu.amazon.com"

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == ACCOUNT][0]
seller = a.get("seller_id") or c.get("seller_id")

body = urllib.parse.urlencode({
    "grant_type": "refresh_token",
    "refresh_token": a["refresh_token"],
    "client_id": a["lwa_client_id"],
    "client_secret": a["lwa_client_secret"],
}).encode()
req = urllib.request.Request(
    "https://api.amazon.com/auth/o2/token", data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"})
access = json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]
H = {"x-amz-access-token": access, "Accept": "application/json"}

CALLS = {"n": 0}


def get(path, params=None, tries=6):
    url = endpoint + path + (("?" + urllib.parse.urlencode(params, doseq=True))
                             if params else "")
    for i in range(tries):
        try:
            CALLS["n"] += 1
            r = urllib.request.Request(url, headers=H)
            return json.loads(urllib.request.urlopen(r, timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(6 * (i + 1))
                continue
            raise


print("=== searchListingsItems: every listing on the account ===")
t0 = time.time()
items, token, pages = [], None, 0
while True:
    p = {"marketplaceIds": mid, "pageSize": 20,
         "includedData": "summaries,offers,fulfillmentAvailability"}
    if token:
        p["pageToken"] = token
    doc = get("/listings/2021-08-01/items/%s" % seller, p)
    items.extend(doc.get("items") or [])
    pages += 1
    token = (doc.get("pagination") or {}).get("nextToken")
    if not token or pages > 60:
        break
secs = time.time() - t0
print("  listings returned : %d" % len(items))
print("  pages / requests  : %d" % pages)
print("  wall clock        : %.1fs" % secs)

have_offer = [i for i in items if (i.get("offers") or [])]
have_qty = [i for i in items if (i.get("fulfillmentAvailability") or [])]
print("  with an offer     : %d" % len(have_offer))
print("  with a quantity   : %d" % len(have_qty))

skus = [str(i.get("sku") or "") for i in items]
print("  the new SKU is present: %s" % (NEW_SKU in skus))

st = {}
for i in items:
    s = (i.get("summaries") or [{}])[0]
    for x in (s.get("status") or ["(none)"]):
        st[x] = st.get(x, 0) + 1
print("  statuses          : %s" % st)

print("\n  what one item carries:")
if items:
    print("   " + json.dumps(items[0], indent=2)[:900].replace("\n", "\n   "))

print("\n=== getPricing: the price the Listings API would not give ===")
# Batched 20 SKUs a call, which is the documented maximum.
t0 = time.time()
priced = {}
for n in range(0, len(skus), 20):
    chunk = [s for s in skus[n:n + 20] if s]
    if not chunk:
        continue
    doc = get("/products/pricing/v0/price",
              {"MarketplaceId": mid, "Skus": chunk, "ItemType": "Sku"})
    for row in (doc.get("payload") or []):
        offers = ((row.get("Product") or {}).get("Offers") or [])
        if offers:
            bp = ((offers[0].get("BuyingPrice") or {}).get("ListingPrice") or {})
            priced[str(row.get("SellerSKU") or "")] = (
                bp.get("Amount"), offers[0].get("FulfillmentChannel"))
psecs = time.time() - t0
print("  SKUs with a live price: %d of %d" % (len(priced), len(skus)))
print("  requests              : %d" % ((len(skus) + 19) // 20))
print("  wall clock            : %.1fs" % psecs)
print("  the new SKU priced    : %s" % (priced.get(NEW_SKU),))

print("\n=== what the report holds, for comparison ===")
print("  (measured separately: GET_MERCHANT_LISTINGS_ALL_DATA built 14:05:24Z")
print("   carried 39 listings and did NOT include %s)" % NEW_SKU)

print("\n=== totals ===")
print("  API requests used this run: %d" % CALLS["n"])
print("  API wall clock            : %.1fs" % (secs + psecs))
print("  a report costs one quota'd request and MINUTES to build")
