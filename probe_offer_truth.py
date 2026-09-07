# Does a BUYABLE offer exist on this ASIN, and is it ours?
#
#     "on the pdp the asin was mine amazon.co.uk/dp/B0HJ2W3XZ1 i confirmed."
#
# Two of Amazon's seller-side systems say there is no offer:
#   getListingsItem      offers: []   fulfillmentAvailability: []
#   merchant listings report (built 14:05, an hour after the listing)  absent
# and the buyer-facing page says there is one. Both cannot be right, so ask a
# THIRD system that neither of those two feeds -- the Product Pricing API, which
# reports what is actually purchasable.
#
# CLAUDE.md Rule 4: no guessing about which one is stale. Print what each says.
import json
import time
import urllib.request
import urllib.parse
import urllib.error

ACCOUNT = "nestwell_goods"
SKU = "9.99_2Days_B0BP1HNW8G"
ASIN = "B0HJ2W3XZ1"
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


def get(path, params=None, tries=6, label=""):
    url = endpoint + path + (("?" + urllib.parse.urlencode(params, doseq=True))
                             if params else "")
    print("\n" + "=" * 70)
    print(label or path)
    print("=" * 70)
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=H)
            raw = urllib.request.urlopen(r, timeout=60).read()
            try:
                out = json.loads(raw)
            except Exception:
                print(raw.decode("utf-8", "replace")[:1500])
                return None
            print(json.dumps(out, indent=2)[:3000])
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                print("  throttled, waiting %ds" % (12 * (i + 1)))
                time.sleep(12 * (i + 1))
                continue
            print("  HTTP %s: %s" % (e.code, e.read().decode()[:600]))
            return None


# 1. OUR OWN OFFER, by SKU. This is the narrowest possible question: does this
#    seller have a priced offer on this SKU? An answer here with a price is
#    proof the offer exists whatever the listings record says.
get("/products/pricing/v0/price",
    {"MarketplaceId": mid, "Skus": SKU, "ItemType": "Sku"},
    label="1. getPricing by SKU -- our own offer, if we have one")

# 2. THE SAME QUESTION BY ASIN.
get("/products/pricing/v0/price",
    {"MarketplaceId": mid, "Asins": ASIN, "ItemType": "Asin"},
    label="2. getPricing by ASIN")

# 3. EVERY OFFER ON THE PRODUCT, which is what a buyer sees. The offer count and
#    whether one of them is ours (isFulfilledByAmazon / sellerId is not returned
#    for competitors, but MyOffer is flagged).
get("/products/pricing/v0/items/%s/offers" % ASIN,
    {"MarketplaceId": mid, "ItemCondition": "New", "CustomerType": "Consumer"},
    label="3. getItemOffers -- what is purchasable on this ASIN")

# 4. THE PUBLIC CATALOGUE RECORD. The earlier call failed because includedData
#    does not accept "offers" -- these are the values the API actually allows.
get("/catalog/2022-04-01/items/%s" % ASIN,
    {"marketplaceIds": mid,
     "includedData": "summaries,identifiers,productTypes,salesRanks"},
    label="4. catalogItem -- does Amazon's public catalogue have it")
