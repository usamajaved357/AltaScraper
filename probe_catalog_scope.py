# What does a barcode lookup actually search, and which accounts can do it?
#
#     "will it check all barcodes from my asins on amazon or all amazon catalog
#      all over the world"
#
# Three things to establish before building on it:
#   1. is B0H8SYL36V -- the ASIN that owns 4545944574867 -- one of HIS listings,
#      or somebody else's? That decides whether the search reaches past his own
#      catalogue.
#   2. is it MARKETPLACE-scoped or worldwide? marketplaceIds is a required
#      parameter, so the answer should be "the marketplace you ask about" --
#      test the same barcode against UK and US and compare.
#   3. which of his accounts may call it at all? The Listings API answers 403 on
#      three of the four; the Catalogue role is granted separately.
import json
import time
import urllib.error
import urllib.parse
import urllib.request

CODE = "4545944574867"          # the one that caused the 8541
ASIN = "B0H8SYL36V"             # what it resolves to

MARKETS = {
    "UK": ("https://sellingpartnerapi-eu.amazon.com", "A1F83G8C2ARO7P"),
    "US": ("https://sellingpartnerapi-na.amazon.com", "ATVPDKIKX0DER"),
    "DE": ("https://sellingpartnerapi-eu.amazon.com", "A1PA6795UKMFR9"),
}

cfg = json.load(open("config.json", encoding="utf-8"))


def token(acct):
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": acct["refresh_token"],
        "client_id": acct["lwa_client_id"], "client_secret": acct["lwa_client_secret"],
    }).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://api.amazon.com/auth/o2/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}),
        timeout=30).read())["access_token"]


def get(endpoint, path, params, access, tries=4):
    url = endpoint + path + "?" + urllib.parse.urlencode(params, doseq=True)
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(
                url, headers={"x-amz-access-token": access,
                              "Accept": "application/json"}), timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(6 * (i + 1))
                continue
            return {"_http": e.code, "_body": e.read().decode()[:200]}


print("=== 1. is %s one of his own listings, on any account? ===" % ASIN)
from data.store import ListingStore
from domain import live_snapshots as SNAP
for acct in cfg.get("accounts", []):
    aid = acct.get("id")
    try:
        rows = ListingStore(aid, config_path="config.json").get_all_rows()
    except Exception:
        rows = []
    hit = [r for r in rows if ASIN in json.dumps(dict(r))]
    for mkt in ("UK", "US"):
        rec = SNAP.get("config.json", aid, mkt) or {}
        for it in (rec.get("items") or []):
            if str(it.get("asin") or "") == ASIN:
                hit.append({"live": mkt, "sku": it.get("sku")})
    print("  %-18s rows=%-4d holds %s: %s" % (aid, len(rows), ASIN,
                                              hit if hit else "no"))

print("\n=== 2. same barcode, three marketplaces ===")
acct = [x for x in cfg["accounts"] if x.get("id") == "nestwell_goods"][0]
tk = token(acct)
for name, (endpoint, mid) in MARKETS.items():
    d = get(endpoint, "/catalog/2022-04-01/items",
            {"marketplaceIds": mid, "identifiers": CODE,
             "identifiersType": "EAN", "includedData": "summaries"}, tk)
    if "_http" in d:
        print("  %-3s HTTP %s %s" % (name, d["_http"], d["_body"][:110]))
        continue
    items = d.get("items") or []
    print("  %-3s %d result(s)" % (name, len(items)), end="")
    for it in items:
        s = (it.get("summaries") or [{}])[0]
        print("  -> %s / %s / %s" % (it.get("asin"), s.get("brand"),
                                     str(s.get("itemName"))[:40]), end="")
    print()

print("\n=== 3. which accounts may call the Catalogue API ===")
for a in cfg.get("accounts", []):
    aid = a.get("id")
    if not (a.get("refresh_token") and a.get("lwa_client_id")):
        print("  %-18s no credentials" % aid)
        continue
    mkt = "US" if str(a.get("default_marketplace") or "").upper() == "US" else "UK"
    endpoint, mid = MARKETS[mkt]
    try:
        tk2 = token(a)
    except Exception as e:
        print("  %-18s auth failed: %s" % (aid, str(e)[:60]))
        continue
    d = get(endpoint, "/catalog/2022-04-01/items",
            {"marketplaceIds": mid, "identifiers": CODE,
             "identifiersType": "EAN", "includedData": "summaries"}, tk2)
    if "_http" in d:
        print("  %-18s (%s) HTTP %s" % (aid, mkt, d["_http"]))
    else:
        print("  %-18s (%s) OK -- %d result(s)"
              % (aid, mkt, len(d.get("items") or [])))
