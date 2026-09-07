# Does searchListingsItems return the listings the INACTIVE report exists for?
#
#     "if we are using reports anywhere else and we have a api available for
#      that same purpose check it and advice"
#
# Sync asks Amazon for TWO reports: the active listings and then the inactive
# ones, merged, because GET_MERCHANT_LISTINGS_ALL_DATA carries only ACTIVE
# listings (routes/live_routes.py:907). Amazon allows roughly one report request
# a minute, so the second is the one that usually gets throttled -- which is why
# suppressed listings intermittently vanish from the screen.
#
# If the Listings API returns every listing WITH its status, both reports go and
# the throttling problem goes with them. nestwell_goods currently has no
# inactive listing at all (the inactive report came back with a header and no
# rows), so this asks every account, to find one that does.
import json
import time
import urllib.request
import urllib.parse
import urllib.error

ENDPOINTS = {"UK": ("https://sellingpartnerapi-eu.amazon.com", "A1F83G8C2ARO7P"),
             "US": ("https://sellingpartnerapi-na.amazon.com", "ATVPDKIKX0DER")}

c = json.load(open("config.json", encoding="utf-8"))

for acct in c.get("accounts", []):
    aid = acct.get("id")
    mkt = "US" if str(acct.get("default_marketplace") or "").upper() == "US" else "UK"
    endpoint, mid = ENDPOINTS[mkt]
    seller = acct.get("seller_id") or c.get("seller_id")
    print("\n" + "=" * 70)
    print("%s  (%s, seller %s)" % (aid, mkt, seller))
    print("=" * 70)
    if not (acct.get("refresh_token") and seller):
        print("  no credentials on this account -- skipped")
        continue
    try:
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": acct["refresh_token"],
            "client_id": acct["lwa_client_id"],
            "client_secret": acct["lwa_client_secret"],
        }).encode()
        req = urllib.request.Request(
            "https://api.amazon.com/auth/o2/token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        access = json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]
    except Exception as e:
        print("  could not authenticate: %s" % str(e)[:120])
        continue
    H = {"x-amz-access-token": access, "Accept": "application/json"}

    t0 = time.time()
    items, token, pages = [], None, 0
    try:
        while True:
            p = {"marketplaceIds": mid, "pageSize": 20,
                 "includedData": "summaries"}
            if token:
                p["pageToken"] = token
            url = endpoint + "/listings/2021-08-01/items/%s?" % seller \
                + urllib.parse.urlencode(p)
            r = urllib.request.Request(url, headers=H)
            doc = json.loads(urllib.request.urlopen(r, timeout=60).read())
            items.extend(doc.get("items") or [])
            pages += 1
            token = (doc.get("pagination") or {}).get("nextToken")
            if not token or pages > 200:
                break
    except urllib.error.HTTPError as e:
        print("  HTTP %s: %s" % (e.code, e.read().decode()[:250]))
        continue
    except Exception as e:
        print("  failed: %s" % str(e)[:150])
        continue

    st = {}
    for i in items:
        s = (i.get("summaries") or [{}])[0]
        key = ",".join(sorted(s.get("status") or [])) or "(no status)"
        st[key] = st.get(key, 0) + 1
    print("  listings : %d   pages: %d   %.1fs" % (len(items), pages, time.time() - t0))
    print("  statuses : %s" % st)
    # THE POINT OF THE SECOND REPORT: anything that is not buyable.
    not_buyable = [i for i in items
                   if "BUYABLE" not in ((i.get("summaries") or [{}])[0].get("status") or [])]
    print("  NOT buyable (what the inactive report is for): %d" % len(not_buyable))
    for i in not_buyable[:5]:
        s = (i.get("summaries") or [{}])[0]
        print("    %-30s %-12s %s" % (str(i.get("sku"))[:30], s.get("asin"),
                                      s.get("status")))
