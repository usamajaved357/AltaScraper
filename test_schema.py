"""
test_schema.py  --  ONE-RUN comprehensive diagnostic for the SP-API
Product Type Definitions (schema) call.

Captures EVERYTHING in a single run so we don't diagnose piecemeal:
  1. library version
  2. RAW HTTP getDefinitions  (proves the Amazon side, like the doctor did)
  3. RAW HTTP searchDefinitions (lists product types your token CAN see)
  4. LIBRARY getDefinitions  (exactly what the generator does) + full error
  5. tries several parameter variations to find one that works

Run:  py -3.11 test_schema.py
(Run it from the app folder so it can read config.json.)
"""
import json, sys, os, traceback, urllib.request, urllib.parse, urllib.error

PT  = sys.argv[1] if len(sys.argv) > 1 else "FLASHLIGHT"   # product type to test
ACC = "sheelady_us"
MKT_ID = "ATVPDKIKX0DER"            # US
ENDPOINT = "https://sellingpartnerapi-na.amazon.com"
LOCALE = "en_US"

print("=" * 64)
print(f"  SCHEMA DIAGNOSTIC  (productType={PT}, marketplace=US)")
print("=" * 64)

# ---- load creds from config (same source the generator uses) ----
cfg = json.load(open("config.json", encoding="utf-8"))
a = [x for x in cfg["accounts"] if x.get("id") == ACC][0]
CID = a["lwa_client_id"]; CSEC = a["lwa_client_secret"]; RT = a["refresh_token"]
print(f"account: {a.get('label','?')}  client_id={CID[:40]}…")

# ---- 1. library version ----
try:
    import sp_api
    print("sp_api package present at:", os.path.dirname(sp_api.__file__))
except Exception as e:
    print("cannot import sp_api:", e); sys.exit(1)

# ---- get an access token (raw) ----
def get_token():
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": RT,
        "client_id": CID, "client_secret": CSEC}).encode()
    req = urllib.request.Request("https://api.amazon.com/auth/o2/token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]

try:
    TOKEN = get_token()
    print("LWA token: OK\n")
except Exception as e:
    print("LWA token FAILED:", e); sys.exit(1)

def raw_get(path, params):
    url = f"{ENDPOINT}{path}?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "x-amz-access-token": TOKEN, "Accept": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.read().decode()[:600], dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600], dict(e.headers)
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}", {}

# ---- 2. RAW getDefinitions (the exact call, via raw HTTP) ----
print("-" * 64)
print("2) RAW HTTP  getDefinitionsProductType")
st, body, hdrs = raw_get(
    f"/definitions/2020-09-01/productTypes/{PT}",
    {"marketplaceIds": MKT_ID, "requirements": "LISTING",
     "requirementsEnforced": "ENFORCED", "locale": LOCALE})
print(f"   HTTP {st}")
print(f"   body: {body}")
if st != 200:
    print(f"   x-amzn-RequestId: {hdrs.get('x-amzn-RequestId') or hdrs.get('x-amzn-requestid','?')}")
print()

# ---- 2b. RAW getDefinitions with NO requirements params (simplest form) ----
print("2b) RAW HTTP  getDefinitions (minimal params, marketplaceIds only)")
st2, body2, _ = raw_get(
    f"/definitions/2020-09-01/productTypes/{PT}",
    {"marketplaceIds": MKT_ID})
print(f"   HTTP {st2}")
print(f"   body: {body2}")
print()

# ---- 3. RAW searchDefinitions (what product types CAN this token see?) ----
print("-" * 64)
print("3) RAW HTTP  searchDefinitionsProductTypes (lists accessible types)")
st3, body3, _ = raw_get("/definitions/2020-09-01/productTypes",
                        {"marketplaceIds": MKT_ID})
print(f"   HTTP {st3}")
if st3 == 200:
    try:
        types = [t.get("name") for t in json.loads(body3).get("productTypes", [])]
        print(f"   token can see {len(types)} product types. Sample: {types[:15]}")
        print(f"   '{PT}' in list: {PT in types}")
    except Exception:
        print(f"   body: {body3}")
else:
    print(f"   body: {body3}")
print()

# ---- 4. LIBRARY getDefinitions (exactly like the generator) ----
print("-" * 64)
print("4) LIBRARY  ProductTypeDefinitions.get_definitions_product_type")
creds = {"lwa_app_id": CID, "lwa_client_secret": CSEC, "refresh_token": RT}
try:
    from sp_api.api import ProductTypeDefinitions
    from sp_api.base import Marketplaces
    ptd = ProductTypeDefinitions(credentials=creds, marketplace=Marketplaces.US)
    print(f"   client endpoint: {ptd.endpoint}")
    resp = ptd.get_definitions_product_type(
        productType=PT, requirements="LISTING",
        requirementsEnforced="ENFORCED", locale=LOCALE,
        marketplaceIds=[MKT_ID])
    link = resp.payload.get("schema", {}).get("link", {}).get("resource", "")
    print(f"   *** LIBRARY SUCCEEDED ***  schema link present: {bool(link)}")
    if link:
        print(f"   link: {link[:80]}…")
except Exception as e:
    print(f"   *** LIBRARY FAILED ***")
    print(f"   type: {type(e).__name__}")
    print(f"   error: {str(e)[:300]}")
    for attr in ("code", "error", "headers", "amzn_request_id"):
        v = getattr(e, attr, None)
        if v is not None:
            print(f"   e.{attr} = {str(v)[:200]}")
    print("   traceback:")
    traceback.print_exc()
print()

# ---- 5. variations to find a working combination ----
print("-" * 64)
print("5) LIBRARY parameter variations (find one that works)")
variations = [
    dict(requirements="LISTING", requirementsEnforced="ENFORCED", locale=LOCALE),
    dict(requirements="LISTING", locale=LOCALE),
    dict(requirements="LISTING_PRODUCT_ONLY", locale=LOCALE),
    dict(locale=LOCALE),
    dict(),
]
try:
    from sp_api.api import ProductTypeDefinitions
    from sp_api.base import Marketplaces
    ptd = ProductTypeDefinitions(credentials=creds, marketplace=Marketplaces.US)
    for v in variations:
        try:
            resp = ptd.get_definitions_product_type(
                productType=PT, marketplaceIds=[MKT_ID], **v)
            link = resp.payload.get("schema", {}).get("link", {}).get("resource", "")
            print(f"   PASS  {v}  -> link={bool(link)}")
        except Exception as e:
            print(f"   FAIL  {v}  -> {type(e).__name__}: {str(e)[:80]}")
except Exception as e:
    print("   could not build client:", e)

print("\n" + "=" * 64)
print("DONE. Send the entire output above.")
print("=" * 64)
