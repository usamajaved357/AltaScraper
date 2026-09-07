# Why a listing Amazon is selling shows up under "Not showing".
#
#     "one is 3 in 1 floor scrub which shows only live but is displayed under
#      this filter"
#
# routes/live_routes.py decides the word, in this order:
#     an issue mentioning "suppress"  -> Suppressed
#     BUYABLE                         -> Active
#     any ERROR issue                 -> Incomplete
#     anything else                   -> Inactive
#
# So SUPPRESSED WINS OVER BUYABLE. And we know from 9.99_2Days_B0BP1HNW8G that
# Amazon keeps a failed submission's issues attached to a SKU long after they
# stop being true. If a stale issue happens to contain the word "suppress", a
# listing Amazon is actively selling is filed under "Not showing".
#
# This asks Amazon for the status AND the issues of every listing, and prints
# what the app would call each one.
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "nestwell_goods"
MID = "A1F83G8C2ARO7P"
ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"

c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == ACCOUNT][0]
seller = a.get("seller_id")

body = urllib.parse.urlencode({
    "grant_type": "refresh_token", "refresh_token": a["refresh_token"],
    "client_id": a["lwa_client_id"], "client_secret": a["lwa_client_secret"],
}).encode()
access = json.loads(urllib.request.urlopen(urllib.request.Request(
    "https://api.amazon.com/auth/o2/token", data=body,
    headers={"Content-Type": "application/x-www-form-urlencoded"}),
    timeout=30).read())["access_token"]
H = {"x-amz-access-token": access, "Accept": "application/json"}


def get(url, tries=6):
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(url, headers=H), timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(8 * (i + 1))
                continue
            raise


# Every SKU, with its status.
items, token = [], None
while True:
    p = {"marketplaceIds": MID, "pageSize": 20,
         "includedData": "summaries,offers,fulfillmentAvailability"}
    if token:
        p["pageToken"] = token
    d = get(ENDPOINT + "/listings/2021-08-01/items/%s?" % seller
            + urllib.parse.urlencode(p))
    items.extend(d.get("items") or [])
    token = (d.get("pagination") or {}).get("nextToken")
    if not token:
        break
print("listings: %d\n" % len(items))


def word(st_arr, issues):
    """Exactly what routes/live_routes.py would call it."""
    has_error = any(str(i.get("severity", "")).upper() == "ERROR" for i in issues)
    suppressed = any("suppress" in str(i.get("message", "")).lower() for i in issues)
    if suppressed:
        return "Suppressed"
    if "BUYABLE" in st_arr:
        return "Active"
    if has_error:
        return "Incomplete"
    return "Inactive"


def not_showing(w):
    s = w.lower()
    return ("inactive" in s) or ("suppress" in s) or ("incomplete" in s)


print("%-30s %-22s %-11s %-5s %s" % ("SKU", "amazon status", "app calls it",
                                     "qty", "why"))
print("-" * 108)
flagged = []
for it in sorted(items, key=lambda x: str(x.get("sku"))):
    sku = str(it.get("sku"))
    s0 = (it.get("summaries") or [{}])[0] or {}
    st_arr = [str(x).upper() for x in (s0.get("status") or [])]
    qty = ""
    fa = it.get("fulfillmentAvailability") or []
    if fa:
        qty = fa[0].get("quantity")
    # Issues cost one call per SKU, so only ask where it could change the word.
    d = get(ENDPOINT + "/listings/2021-08-01/items/%s/%s?" % (
        seller, urllib.parse.quote(sku, safe=""))
        + urllib.parse.urlencode({"marketplaceIds": MID, "issueLocale": "en_GB",
                                  "includedData": "issues"}))
    issues = d.get("issues") or []
    w = word(st_arr, issues)
    if not_showing(w):
        why = "; ".join(str(i.get("message", ""))[:90] for i in issues[:2]) or "(no issues)"
        flagged.append((sku, st_arr, w, qty, why))
        print("%-30s %-22s %-11s %-5s %s"
              % (sku[:30], ",".join(st_arr), w, qty, why[:60]))

print("\n=== the %d the tile would show ===" % len(flagged))
for sku, st_arr, w, qty, why in flagged:
    print("\n  %s" % sku)
    print("     amazon status : %s" % ",".join(st_arr))
    print("     app calls it  : %s" % w)
    print("     quantity      : %s" % qty)
    print("     issues        : %s" % (why[:400] or "none"))
    if "BUYABLE" in st_arr and w == "Suppressed":
        print("     >>> AMAZON IS SELLING THIS. The word comes from an issue "
              "mentioning 'suppress', which is tested BEFORE buyable.")
