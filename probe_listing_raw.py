# The whole of what Amazon returns for this SKU, unfiltered, plus what the
# account's listings look like from the other directions the app can ask from.
#
#     "the listing which i created using this app is now in amazon but after
#      clicking sync also i am not able to see it in my app, also my offer is
#      attached to the asin, i have verified from pdp on amazon co uk"
#
# getListingsItem says offers: [] and status DISCOVERABLE. The PDP says
# otherwise. One of those is stale, and guessing which would be guessing
# (CLAUDE.md Rule 4), so: print everything.
import json
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


def call(path, params, label):
    url = endpoint + path + "?" + urllib.parse.urlencode(params, doseq=True)
    r = urllib.request.Request(url, headers={"x-amz-access-token": access,
                                             "Accept": "application/json"})
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)
    try:
        out = json.loads(urllib.request.urlopen(r, timeout=60).read())
        print(json.dumps(out, indent=2)[:4000])
        return out
    except urllib.error.HTTPError as e:
        print("HTTP %s: %s" % (e.code, e.read().decode()[:500]))
        return None


call("/listings/2021-08-01/items/%s/%s" % (seller, urllib.parse.quote(SKU, safe="")),
     {"marketplaceIds": mid, "issueLocale": "en_GB",
      "includedData": "summaries,offers,fulfillmentAvailability,procurement,relationships"},
     "1. getListingsItem -- the SKU, everything except attributes")

# THE SEARCH ENDPOINT is what a catalogue sync would use, and it answers from a
# different index than the single-item read. If the app's Sync misses the
# listing, this is where it would be missing FROM.
call("/listings/2021-08-01/items/%s" % seller,
     {"marketplaceIds": mid, "includedData": "summaries,offers",
      "identifiers": SKU, "identifiersType": "SKU", "pageSize": 10},
     "2. searchListingsItems by SKU -- what a catalogue sweep would find")

call("/listings/2021-08-01/items/%s" % seller,
     {"marketplaceIds": mid, "includedData": "summaries",
      "identifiers": ASIN, "identifiersType": "ASIN", "pageSize": 10},
     "3. searchListingsItems by ASIN")

# WHAT THE BUYER SEES. If the offer is on the PDP, it is in the catalogue's
# offer count even when the seller-side listing record has not caught up.
call("/catalog/2022-04-01/items/%s" % ASIN,
     {"marketplaceIds": mid,
      "includedData": "summaries,offers,identifiers,productTypes"},
     "4. catalogItem -- the public product, and how many offers it shows")
