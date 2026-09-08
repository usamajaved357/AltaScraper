# Which ASIN does each of these barcodes resolve to in Amazon's catalogue?
#
# Error 8541 is triggered by the PRODUCT ID matching an existing ASIN -- Amazon's
# own forums: "occurs when your Product ID, such as UPC, EAN, JAN, and ISBN,
# corresponds to the Product ID of an existing ASIN". The attribute disagreement
# it then lists (colour, title) is the CONSEQUENCE of that match, not its cause.
#
# So the question is not "are these two listings too similar". It is: what does
# 4545944574867 already point at?
#
# Three barcodes are in play and they are all different:
#   4545944574867   what the app's row holds, and what the recorded payload sent
#   04545161767332  what Amazon's message calls the "Merchant" value
#   04545155187597  what Amazon says the ASIN B0HHXTKT3B already has
import json
import time
import urllib.error
import urllib.parse
import urllib.request

ACCOUNT = "nestwell_goods"
MID = "A1F83G8C2ARO7P"
ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"

CODES = ["4545944574867", "4545161767332", "4545155187597"]

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == ACCOUNT][0]

body = urllib.parse.urlencode({
    "grant_type": "refresh_token", "refresh_token": a["refresh_token"],
    "client_id": a["lwa_client_id"], "client_secret": a["lwa_client_secret"],
}).encode()
access = json.loads(urllib.request.urlopen(urllib.request.Request(
    "https://api.amazon.com/auth/o2/token", data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"}),
    timeout=30).read())["access_token"]
H = {"x-amz-access-token": access, "Accept": "application/json"}


def get(url, tries=5):
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(url, headers=H), timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(8 * (i + 1))
                continue
            return {"_http": e.code, "_body": e.read().decode()[:300]}


print("=== what each barcode points at in Amazon's catalogue ===")
for code in CODES:
    url = ENDPOINT + "/catalog/2022-04-01/items?" + urllib.parse.urlencode({
        "marketplaceIds": MID,
        "identifiers": code,
        "identifiersType": "EAN",
        "includedData": "summaries,identifiers",
    })
    d = get(url)
    if "_http" in d:
        print("\n  %s -> HTTP %s %s" % (code, d["_http"], d["_body"][:160]))
        continue
    items = d.get("items") or []
    print("\n  %s -> %d ASIN(s)" % (code, len(items)))
    for it in items:
        s = (it.get("summaries") or [{}])[0]
        print("     %-12s %-22s %s"
              % (it.get("asin"), str(s.get("brand"))[:22],
                 str(s.get("itemName"))[:58]))

print("\n=== and what B0HHXTKT3B is now ===")
d = get(ENDPOINT + "/catalog/2022-04-01/items/B0HHXTKT3B?"
        + urllib.parse.urlencode({"marketplaceIds": MID,
                                  "includedData": "summaries,identifiers"}))
if "_http" in d:
    print("  HTTP %s %s" % (d["_http"], d["_body"][:200]))
else:
    s = (d.get("summaries") or [{}])[0]
    print("  brand=%s  name=%s" % (s.get("brand"), str(s.get("itemName"))[:60]))
    for grp in (d.get("identifiers") or []):
        for i in grp.get("identifiers") or []:
            print("  identifier: %s = %s" % (i.get("identifierType"), i.get("identifier")))
