# Test the SP-API LIBRARY exactly as the generator uses it (not raw HTTP).
# This isolates whether the bug is in the python-amazon-sp-api library.
# Run: py -3.11 test_library.py
import json, sys, traceback

print("=" * 60)
print("  LIBRARY TEST — uses python-amazon-sp-api like the generator")
print("=" * 60)

# 1. library version
try:
    import sp_api
    print("sp_api version:", getattr(sp_api, "__version__", "UNKNOWN"))
except Exception as e:
    print("cannot import sp_api:", e); sys.exit(1)

# 2. what credentials does the library REQUIRE?
try:
    from sp_api.base.credential_provider import required_credentials
    print("library REQUIRES these credential fields:", required_credentials)
    needs_aws = any("aws" in c or "role" in c or "secret_key" in c for c in required_credentials)
    if needs_aws:
        print("  *** This version REQUIRES AWS IAM credentials (old version).")
        print("  *** That is almost certainly why it fails: your creds are LWA-only.")
        print("  *** FIX: upgrade the library:  py -3.11 -m pip install --upgrade python-amazon-sp-api")
except Exception as e:
    print("could not read required_credentials:", e)

# 3. build creds exactly like the generator
c = json.load(open("config.json", encoding="utf-8"))
a = [x for x in c["accounts"] if x.get("id") == "sheelady_us"][0]
creds = {
    "lwa_app_id": a.get("lwa_client_id") or a.get("lwa_app_id", ""),
    "lwa_client_secret": a.get("lwa_client_secret", ""),
    "refresh_token": a.get("refresh_token", ""),
}
print("\npassing creds with keys:", list(creds.keys()))

# 4. call catalog through the library — same as get_competitor_asin_data
try:
    from sp_api.api import CatalogItemsV20220401 as CatalogItems
    from sp_api.base import Marketplaces
    cat = CatalogItems(credentials=creds, marketplace=Marketplaces.US)
    print("CatalogItems client built. Endpoint:", getattr(cat, "endpoint", "?"))
    res = cat.get_catalog_item(
        asin="B09SD3W56K",
        includedData=["summaries", "productTypes"],
        marketplaceIds=["ATVPDKIKX0DER"],
    )
    p = res.payload
    summ = (p.get("summaries") or [{}])
    print("\n  *** LIBRARY CALL SUCCEEDED ***")
    print("  title:", (summ[0].get("itemName") or "")[:60])
    print("  -> The library works. The generator should work now.")
except Exception as e:
    print("\n  *** LIBRARY CALL FAILED ***")
    print("  error type:", type(e).__name__)
    print("  error:", str(e)[:300])
    print("\n  Full traceback:")
    traceback.print_exc()
    # Try to show what request it actually built
    try:
        print("\n  client endpoint was:", cat.endpoint)
        print("  client region was:", getattr(cat, "region", "?"))
    except Exception:
        pass
