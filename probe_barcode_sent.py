# What did Amazon actually RECEIVE for this SKU, and what is it complaining about?
#
# The owner replaced a clashing barcode, previewed clean, submitted, and the
# re-check still reported the OLD code. Two possibilities, and only Amazon can
# tell them apart:
#
#   (a) the new code never reached Amazon -- the submitted payload still carried
#       the old one, and the app is wrong;
#   (b) the new code DID reach Amazon, and the issue being reported is the
#       leftover from the earlier contribution, which getListingsItem keeps
#       attached to the SKU. Then the app is reporting a stale complaint as if
#       it were about the submission just made.
#
# CLAUDE.md Rule 4: read what Amazon literally holds. No guessing.
import json
import urllib.request
import urllib.parse
import urllib.error

ACCOUNT = "nestwell_goods"
SKU = "9.99_2Days_B0BP1HNW8G"
OLD = "04545844574868"
NEW = "4545156646383"

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == ACCOUNT][0]
mid = "A1F83G8C2ARO7P"                      # UK
endpoint = "https://sellingpartnerapi-eu.amazon.com"
seller = a.get("seller_id") or c.get("seller_id")
print("account %s  seller %s" % (ACCOUNT, seller))

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
print("token OK\n")

url = ("%s/listings/2021-08-01/items/%s/%s?"
       % (endpoint, seller, urllib.parse.quote(SKU, safe=""))
       ) + urllib.parse.urlencode({
           "marketplaceIds": mid,
           "issueLocale": "en_GB",
           "includedData": "summaries,attributes,issues,offers,fulfillmentAvailability",
       })
r = urllib.request.Request(url, headers={"x-amz-access-token": access,
                                         "Accept": "application/json"})
try:
    p = json.loads(urllib.request.urlopen(r, timeout=60).read())
except urllib.error.HTTPError as e:
    print("HTTP %s: %s" % (e.code, e.read().decode()[:600]))
    raise SystemExit(1)

attrs = p.get("attributes") or {}
print("=== WHAT AMAZON HOLDS AS THE IDENTIFIER ===")
found = False
for k, v in attrs.items():
    if "identifier" in k or "gtin" in k or "upc" in k or "ean" in k:
        print("  %s = %s" % (k, json.dumps(v)))
        found = True
if not found:
    print("  (no identifier attribute stored on the item)")

blob = json.dumps(attrs)
print("\n  old code %s present in stored attributes: %s" % (OLD, OLD in blob))
print("  new code %s present in stored attributes: %s" % (NEW, NEW in blob))

print("\n=== SUMMARIES ===")
for s in (p.get("summaries") or []):
    print("  asin=%s status=%s createdDate=%s lastUpdated=%s"
          % (s.get("asin"), s.get("status"), s.get("createdDate"),
             s.get("lastUpdatedDate")))

print("\n=== ISSUES ===")
for i in (p.get("issues") or []):
    print("  [%s] code=%s attrs=%s" % (i.get("severity"), i.get("code"),
                                       i.get("attributeNames")))
    print("      %s" % str(i.get("message"))[:300])

print("\n=== IS THERE ACTUALLY AN OFFER? ===")
print("  offers: %s" % json.dumps(p.get("offers"), indent=2)[:800])
print("  fulfilmentAvailability: %s" % json.dumps(p.get("fulfillmentAvailability")))
print("  purchasable/price attrs:")
for k in ("purchasable_offer", "list_price", "fulfillment_availability",
          "merchant_suggested_asin", "condition_type"):
    if k in attrs:
        print("    %s = %s" % (k, json.dumps(attrs[k])[:300]))

print("\n=== raw keys ===", sorted(p.keys()))
