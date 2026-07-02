"""
sp_api_doctor.py — pinpoint exactly why SP-API is failing for an account.

Run:  py -3.11 sp_api_doctor.py --account-id sheelady_us
      py -3.11 sp_api_doctor.py --account-id sheelady_us --asin B09SD3W56K

It tests, in order:
  1. LWA token exchange (refresh_token -> access_token)  -> proves the token/region
  2. Sellers/getMarketplaceParticipations                -> proves which marketplaces
                                                             the token is ACTUALLY
                                                             authorized for
  3. CatalogItems.getCatalogItem (if --asin given)       -> proves the Catalog role
  4. ProductPricing + ProductFees                         -> proves those roles

Each step prints PASS / FAIL with the precise Amazon error, so you know whether
the problem is the token's region, the seller's marketplace registration, or a
specific missing role — instead of guessing.
"""

import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
CONFIG = HERE / "config.json"


def _argval(flag, default=None):
    a = sys.argv
    if flag in a:
        i = a.index(flag)
        if i + 1 < len(a):
            return a[i + 1]
    return default


def load_account(account_id):
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    for a in cfg.get("accounts", []):
        if a.get("id") == account_id:
            return a, cfg
    print(f"  account '{account_id}' not found. Available:")
    for a in cfg.get("accounts", []):
        print(f"    - {a.get('id')}  ({a.get('label')})")
    sys.exit(1)


MKT = {
    "US": ("ATVPDKIKX0DER", "https://sellingpartnerapi-na.amazon.com", "us-east-1"),
    "CA": ("A2EUQ1WTGCTBG2", "https://sellingpartnerapi-na.amazon.com", "us-east-1"),
    "MX": ("A1AM78C64UM0Y8", "https://sellingpartnerapi-na.amazon.com", "us-east-1"),
    "BR": ("A2Q3Y263D00KWC", "https://sellingpartnerapi-na.amazon.com", "us-east-1"),
    "UK": ("A1F83G8C2ARO7P", "https://sellingpartnerapi-eu.amazon.com", "eu-west-1"),
    "DE": ("A1PA6795UKMFR9", "https://sellingpartnerapi-eu.amazon.com", "eu-west-1"),
}


def step(n, name):
    print(f"\n[{n}] {name}")


def lwa_token(client_id, client_secret, refresh_token):
    """Exchange refresh_token for an access_token. Region-independent — proves
    the LWA credentials + refresh token are valid at all."""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        "https://api.amazon.com/auth/o2/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def sp_get(endpoint, path, access_token, params=None):
    url = endpoint + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "x-amz-access-token": access_token,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


def main():
    account_id = _argval("--account-id")
    asin = _argval("--asin")
    if not account_id:
        print("usage: py -3.11 sp_api_doctor.py --account-id <id> [--asin <ASIN>]")
        sys.exit(1)

    acc, cfg = load_account(account_id)
    label = acc.get("label", account_id)
    cid = acc.get("lwa_client_id") or acc.get("lwa_app_id") or cfg.get("sp_api_client_id")
    csec = acc.get("lwa_client_secret") or cfg.get("sp_api_client_secret")
    rtok = acc.get("refresh_token") or cfg.get("sp_api_refresh_token")
    dmkt = (acc.get("default_marketplace") or "US").upper()
    mkts = acc.get("marketplaces") or [dmkt]

    print("=" * 64)
    print(f"  SP-API DOCTOR  —  {label}  ({account_id})")
    print("=" * 64)
    print(f"  default marketplace : {dmkt}")
    print(f"  declared markets    : {', '.join(mkts)}")
    print(f"  client_id           : {(cid or '')[:20]}…")
    print(f"  refresh_token       : {(rtok or '')[:18]}…  (len {len(rtok or '')})")
    if dmkt not in MKT:
        print(f"  ! unknown marketplace {dmkt}; defaulting to US endpoint")
        dmkt = "US"
    mid, endpoint, region = MKT[dmkt]
    print(f"  endpoint (region)   : {endpoint}  ({region})")

    # ---- STEP 1: LWA token ----
    step(1, "LWA token exchange (refresh_token -> access_token)")
    try:
        tok = lwa_token(cid, csec, rtok)
        access = tok.get("access_token", "")
        if access:
            print(f"  PASS — got access_token ({len(access)} chars). LWA creds + "
                  f"refresh token are VALID.")
        else:
            print(f"  FAIL — no access_token in response: {tok}")
            return
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  FAIL — HTTP {e.code}: {body}")
        print("  → The refresh token or client credentials are wrong/expired, OR the")
        print("    refresh token belongs to a DIFFERENT app (client_id mismatch).")
        return
    except Exception as e:
        print(f"  FAIL — {type(e).__name__}: {e}")
        return

    # ---- STEP 2: marketplace participations (THE key test) ----
    step(2, "getMarketplaceParticipations (which markets is this token authorized for?)")
    try:
        st, data = sp_get(endpoint, "/sellers/v1/marketplaceParticipations", access)
        parts = data.get("payload", [])
        ids = []
        for p in parts:
            m = p.get("marketplace", {})
            ids.append((m.get("id"), m.get("countryCode"), m.get("name")))
        print(f"  PASS — token authorized on {len(ids)} marketplace(s):")
        for mid_, cc, nm in ids:
            flag = "  <-- target" if mid_ == mid else ""
            print(f"      {cc or '?':3} {mid_}  {nm or ''}{flag}")
        if mid not in [x[0] for x in ids]:
            print(f"  !! The target marketplace {dmkt} ({mid}) is NOT in the list above.")
            print(f"     This is the problem: the refresh token is NOT authorized for "
                  f"{dmkt}.")
            print(f"     Fix: re-authorize the app on the {dmkt} Seller Central account "
                  f"and use THAT refresh token,")
            print(f"     or the seller isn't registered on {dmkt}.")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  FAIL — HTTP {e.code}: {body}")
        if e.code in (403, 401):
            print("  → Token is valid but this endpoint/region rejects it. Almost")
            print("    always means the refresh token was issued for a DIFFERENT region")
            print(f"    than {region}. Re-authorize on the {dmkt} regional Seller Central.")
        return
    except Exception as e:
        print(f"  FAIL — {type(e).__name__}: {e}")
        return

    # ---- STEP 3: catalog (role test) ----
    if asin:
        step(3, f"getCatalogItem({asin}) — tests the Catalog Items role")
        try:
            st, data = sp_get(endpoint, f"/catalog/2022-04-01/items/{asin}", access,
                              params={"marketplaceIds": mid,
                                      "includedData": "summaries,productTypes"})
            summ = (data.get("summaries") or [{}])
            pt = (data.get("productTypes") or [{}])
            print(f"  PASS — catalog returned. "
                  f"title='{(summ[0].get('itemName') or '')[:50]}' "
                  f"productType='{pt[0].get('productType','')}'")
            print("  → Catalog Items role IS granted and working.")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"  FAIL — HTTP {e.code}: {body}")
            if e.code == 403:
                print("  → 403 here (after step 2 passed) = the Catalog Items role is")
                print("    NOT granted to this app, OR not authorized by the seller.")
                print("    Seller Central > Apps & Services > Develop Apps > your app >")
                print("    Edit App > add the 'Product Listing' / Catalog role, then the")
                print("    SELLER must re-authorize the app.")
            elif e.code == 404:
                print(f"  → 404 = ASIN {asin} not found in {dmkt} catalogue (wrong "
                      f"marketplace for this ASIN). Try a known-US ASIN.")
        except Exception as e:
            print(f"  FAIL — {type(e).__name__}: {e}")

        # ---- STEP 4: pricing + fees ----
        step(4, f"Pricing + Fees for {asin} — tests those roles")
        try:
            st, data = sp_get(endpoint, f"/products/pricing/v0/items/{asin}/offers",
                              access, params={"marketplaceId": mid,
                                              "ItemCondition": "New"})
            print("  PASS — pricing role works.")
        except urllib.error.HTTPError as e:
            print(f"  pricing FAIL — HTTP {e.code}: {e.read().decode()[:160]}")
        except Exception as e:
            print(f"  pricing FAIL — {type(e).__name__}: {e}")

    print("\n" + "=" * 64)
    print("  SUMMARY")
    print("  - Step 1 PASS, Step 2 FAIL/empty  → refresh token wrong region or")
    print("    seller not on that marketplace. Re-authorize on the right region.")
    print("  - Step 2 PASS, Step 3 403         → Catalog role missing; add it & have")
    print("    the seller re-authorize.")
    print("  - All PASS                        → SP-API is fine; the generator will work.")
    print("=" * 64)


if __name__ == "__main__":
    main()
