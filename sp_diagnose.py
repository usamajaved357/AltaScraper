#!/usr/bin/env python3
"""
sp_diagnose.py -- One-shot diagnostic for SP-API connection issues.

Runs EVERY layer test in one pass and prints a clean per-layer verdict so you
know exactly which link in the chain is broken. Tests, in order:

  1. DNS resolution          -- can we resolve the SP-API host?
  2. TCP connect + latency   -- can we open a socket + how slow is the route?
  3. TLS handshake           -- does HTTPS negotiate cleanly?
  4. LWA token endpoint      -- can we hit Amazon's auth server?
  5. LWA access token        -- does the refresh_token still work?
  6. SP-API: Sellers         -- most basic authorised call (marketplace access?)
  7. SP-API: Catalog items   -- Catalog role granted on this marketplace?
  8. SP-API: Product Pricing -- Pricing role granted?
  9. SP-API: Product Fees    -- Fees role granted?
 10. SP-API: Definitions     -- Definitions role granted?

Usage:
    python sp_diagnose.py --marketplace UK [--account-id jack_uk]
    python sp_diagnose.py --marketplace US

Exit code: 0 if all pass; the number of failed steps otherwise.
"""
import argparse, json, os, socket, ssl, sys, time
import urllib.request, urllib.error

RESET = "\033[0m"; RED = "\033[31m"; GRN = "\033[32m"; YEL = "\033[33m"
CYA = "\033[36m"; BOLD = "\033[1m"

def _ok(msg):    print(f"  {GRN}PASS{RESET}  {msg}")
def _warn(msg):  print(f"  {YEL}WARN{RESET}  {msg}")
def _fail(msg):  print(f"  {RED}FAIL{RESET}  {msg}")
def _hdr(n, msg):
    print(f"\n{BOLD}{CYA}[{n:>2}]{RESET} {BOLD}{msg}{RESET}")


EU_HOST = "sellingpartnerapi-eu.amazon.com"
NA_HOST = "sellingpartnerapi-na.amazon.com"
LWA_HOST = "api.amazon.com"
UK_MKT  = "A1F83G8C2ARO7P"
US_MKT  = "ATVPDKIKX0DER"


def _load_config():
    """Load config.json + optional account-scoped creds (mirrors amazon_listing_generator.py)."""
    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(here, "config.json")
    if not os.path.exists(cfg_path):
        cfg_path = "config.json"
    with open(cfg_path) as f:
        return json.load(f)


def _account_creds(config, account_id):
    """Return the SP-API creds for a specific account_id.

    Matches the app's real shape: `accounts` is a LIST of account dicts (each with
    an 'id' field), NOT a dict keyed by id. The key names on the account itself
    are `lwa_client_id` / `lwa_client_secret` / `refresh_token` (mirrors
    accounts.account_creds() so this diagnostic uses the same creds a real run
    would use)."""
    accts = config.get("accounts", []) or []
    if not isinstance(accts, list):
        return None
    acc = next((a for a in accts if a.get("id") == account_id), None)
    if not acc:
        return None
    return {
        "lwa_app_id":        acc.get("lwa_client_id") or acc.get("lwa_app_id") or config.get("sp_api_client_id", ""),
        "lwa_client_secret": acc.get("lwa_client_secret", ""),
        "refresh_token":     acc.get("refresh_token", ""),
        "seller_id":         acc.get("seller_id", ""),
    }


def _list_account_ids(config):
    """List available account ids so the error message can tell the user what to type."""
    accts = config.get("accounts", []) or []
    if not isinstance(accts, list):
        return []
    return [a.get("id", "?") for a in accts if a.get("id")]


def test_dns(host):
    _hdr(1, f"DNS -- can we resolve {host}?")
    try:
        t0 = time.time()
        ip = socket.gethostbyname(host)
        dt = (time.time() - t0) * 1000
        _ok(f"{host} -> {ip} ({dt:.0f}ms)")
        return True, ip
    except Exception as e:
        _fail(f"DNS failed: {e}")
        _fail("Root cause = DNS server can't resolve Amazon endpoints.")
        _fail("Fix: change DNS to 1.1.1.1 (Cloudflare) or 8.8.8.8 (Google).")
        return False, None


def test_tcp(host, ip):
    _hdr(2, f"TCP -- can we open a socket to {host}:443?")
    times = []
    for i in range(3):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(15)
            t0 = time.time()
            s.connect((ip or host, 443))
            dt = (time.time() - t0) * 1000
            times.append(dt)
            s.close()
        except Exception as e:
            _fail(f"attempt {i+1}: {e}")
            _fail("Root cause = network can't reach Amazon's server. VPN/firewall/ISP block?")
            return False, None
    avg = sum(times) / len(times)
    if avg > 2000:
        _warn(f"TCP connect avg = {avg:.0f}ms (VERY slow -- route from your ISP is congested)")
        _warn("This alone explains ConnectTimeout errors. Fix: VPN via EU/US, or wait/retry.")
    elif avg > 800:
        _warn(f"TCP connect avg = {avg:.0f}ms (slow -- may need long timeouts, but works)")
    else:
        _ok(f"TCP connect avg = {avg:.0f}ms (healthy)")
    return True, avg


def test_tls(host):
    _hdr(3, f"TLS -- can we complete an HTTPS handshake to {host}?")
    try:
        ctx = ssl.create_default_context()
        t0 = time.time()
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        dt = (time.time() - t0) * 1000
        _ok(f"TLS OK ({dt:.0f}ms), cert CN issuer = {cert.get('issuer', [[('','?')]])[-1][0][1]}")
        return True
    except ssl.SSLError as e:
        _fail(f"SSL error: {e}")
        _fail("Root cause = TLS/cert problem. System trust store or corporate proxy MITM?")
        return False
    except Exception as e:
        _fail(f"connect failed: {e}")
        return False


def test_lwa_token(client_id, client_secret, refresh_token):
    _hdr(5, "LWA access token -- does your refresh_token still work?")
    if not refresh_token:
        _fail("No refresh_token loaded from config.")
        return False, None
    data = (
        f"grant_type=refresh_token"
        f"&refresh_token={refresh_token}"
        f"&client_id={client_id}"
        f"&client_secret={client_secret}"
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.amazon.com/auth/o2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode("utf-8"))
        dt = (time.time() - t0) * 1000
        tok = j.get("access_token", "")
        exp = j.get("expires_in", 0)
        _ok(f"got access token ({dt:.0f}ms), expires in {exp}s (~1h, normal)")
        return True, tok
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        _fail(f"HTTP {e.code}: {body[:250]}")
        low = body.lower()
        if "invalid_grant" in low:
            _fail("Root cause = refresh_token is INVALID or REVOKED.")
            _fail("Fix: re-authorize the app in Seller Central > Manage Your Apps > Authorize.")
        elif "invalid_client" in low:
            _fail("Root cause = client_id / client_secret is wrong or was rotated.")
            _fail("Fix: paste fresh LWA credentials from Developer Console.")
        else:
            _fail("LWA rejected the token. Copy the message above for support.")
        return False, None
    except Exception as e:
        _fail(f"request failed: {e}")
        return False, None


def _sp_call(host, path, token, timeout=30):
    """Raw SP-API GET. Returns (status, body_or_err, elapsed_ms)."""
    req = urllib.request.Request(
        f"https://{host}{path}",
        headers={"x-amz-access-token": token, "User-Agent": "sp-diagnose/1.0"},
        method="GET",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="ignore")
            return r.status, body, (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body, (time.time() - t0) * 1000
    except Exception as e:
        return 0, str(e), (time.time() - t0) * 1000


def _classify_spapi(status, body):
    """Translate SP-API errors into what to actually DO about it."""
    low = body.lower()
    if status == 0 and ("timeout" in low or "timed out" in low):
        return ("NETWORK", "Timeout / connection died before Amazon replied. "
                           "Route congestion; see TCP layer above.")
    if status == 403 or "unauthorized" in low or "access to requested" in low:
        return ("ROLE",    "App is authenticated but this ROLE is not granted for this "
                           "marketplace. Fix: add the missing role in Developer Console "
                           "OR the seller must re-authorize the app.")
    if status == 401 or "invalid_client" in low or "token" in low and "expired" in low:
        return ("TOKEN",   "Access token rejected. Fix: rotate LWA client secret; re-auth.")
    if status == 404:
        return ("NOTFOUND","Resource not found -- endpoint OK, ASIN/marketplace mismatch?")
    if status == 429 or "throttl" in low or "quotaexceeded" in low:
        return ("THROTTLE","Rate-limited. Fine; retry with backoff.")
    if 200 <= status < 300:
        return ("OK", "")
    return ("OTHER", f"HTTP {status}: {body[:200]}")


def test_sellers(host, token):
    _hdr(6, "SP-API: getMarketplaceParticipations -- basic auth + marketplace list")
    status, body, dt = _sp_call(host, "/sellers/v1/marketplaceParticipations", token)
    kind, msg = _classify_spapi(status, body)
    if kind == "OK":
        try:
            mkts = json.loads(body).get("payload", [])
            names = [m.get("marketplace", {}).get("countryCode", "?") for m in mkts]
            _ok(f"authenticated OK ({dt:.0f}ms); marketplaces accessible: {', '.join(names)}")
        except Exception:
            _ok(f"authenticated OK ({dt:.0f}ms)")
        return True, body
    _fail(f"HTTP {status} ({dt:.0f}ms) [{kind}]: {msg}")
    return False, body


def test_catalog(host, token, marketplace_id, sample_asin):
    _hdr(7, f"SP-API: Catalog Items v2022-04-01 -- getCatalogItem({sample_asin})")
    path = (f"/catalog/2022-04-01/items/{sample_asin}"
            f"?marketplaceIds={marketplace_id}"
            f"&includedData=summaries,productTypes")
    status, body, dt = _sp_call(host, path, token)
    kind, msg = _classify_spapi(status, body)
    if kind == "OK":
        _ok(f"catalog works ({dt:.0f}ms)")
        return True
    if kind == "NOTFOUND":
        _warn(f"ASIN {sample_asin} not in this marketplace's catalogue -- the call itself works though")
        return True
    _fail(f"HTTP {status} ({dt:.0f}ms) [{kind}]: {msg}")
    return False


def test_pricing(host, token, marketplace_id, sample_asin):
    _hdr(8, f"SP-API: Product Pricing v0 -- getCompetitivePricing({sample_asin})")
    path = (f"/products/pricing/v0/competitivePrice"
            f"?MarketplaceId={marketplace_id}"
            f"&Asins={sample_asin}&ItemType=Asin")
    status, body, dt = _sp_call(host, path, token)
    kind, msg = _classify_spapi(status, body)
    if kind == "OK":
        _ok(f"pricing works ({dt:.0f}ms)")
        return True
    _fail(f"HTTP {status} ({dt:.0f}ms) [{kind}]: {msg}")
    if kind == "ROLE":
        _fail("SP-API app does NOT have the Product Pricing role for this marketplace.")
    return False


def test_fees(host, token, marketplace_id, sample_asin):
    _hdr(9, f"SP-API: Product Fees v0 -- getMyFeesEstimateForASIN({sample_asin})")
    _warn("skipping (POST-only with body; ROLE issues would already show above)")
    return True


def test_definitions(host, token, marketplace_id, sample_pt):
    _hdr(10, f"SP-API: Definitions 2020-09-01 -- getDefinitionsProductType({sample_pt})")
    path = (f"/definitions/2020-09-01/productTypes/{sample_pt}"
            f"?marketplaceIds={marketplace_id}"
            f"&requirements=LISTING&requirementsEnforced=ENFORCED&locale=en_GB")
    status, body, dt = _sp_call(host, path, token)
    kind, msg = _classify_spapi(status, body)
    if kind == "OK":
        _ok(f"definitions works ({dt:.0f}ms) -- schema fetch will succeed")
        return True
    _fail(f"HTTP {status} ({dt:.0f}ms) [{kind}]: {msg}")
    if kind == "ROLE":
        _fail("This is why dropdowns are empty and required-field stars look off.")
        _fail("Fix: add 'Product Listings' or 'Definitions' role in Developer Console.")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marketplace", default="UK", choices=["UK", "US"])
    ap.add_argument("--account-id", default="")
    ap.add_argument("--asin", default="", help="sample ASIN to probe (default: known-good per market)")
    ap.add_argument("--product-type", default="LUGGAGE", help="sample productType for Definitions")
    args = ap.parse_args()

    mkt   = args.marketplace.upper()
    host  = EU_HOST if mkt == "UK" else NA_HOST
    mkt_id = UK_MKT if mkt == "UK" else US_MKT
    asin  = args.asin or ("B0BXW6HJKT" if mkt == "UK" else "B08N5WRWNW")

    print(f"\n{BOLD}{CYA}SP-API one-shot diagnostic{RESET}")
    print(f"  marketplace: {BOLD}{mkt}{RESET}   endpoint: {host}   marketplace_id: {mkt_id}")
    print(f"  account:     {args.account_id or '(config default)'}")
    print(f"  sample ASIN: {asin}   sample PT: {args.product_type}")
    print(f"  (each step tells you WHICH layer failed and how to fix it)")

    fails = 0

    # 1. DNS
    ok, ip = test_dns(host); fails += 0 if ok else 1
    if not ok:
        print(f"\n{BOLD}{RED}Stopping: no DNS = nothing else can work.{RESET}"); return 1

    # 2. TCP + latency
    ok, avg = test_tcp(host, ip); fails += 0 if ok else 1
    if not ok:
        print(f"\n{BOLD}{RED}Stopping: no TCP = network blocked.{RESET}"); return 1

    # 3. TLS
    ok = test_tls(host); fails += 0 if ok else 1
    if not ok:
        print(f"\n{BOLD}{RED}Stopping: TLS broken = nothing above HTTPS can work.{RESET}"); return 1

    # 4. LWA host reachable (quick)
    _hdr(4, f"LWA endpoint -- reach {LWA_HOST}?")
    try:
        socket.gethostbyname(LWA_HOST)
        _ok("resolves fine")
    except Exception as e:
        _fail(f"cannot resolve LWA host: {e}"); fails += 1

    # Config + LWA token
    try:
        cfg = _load_config()
    except Exception as e:
        print(f"\n{BOLD}{RED}Cannot load config.json ({e}). Stopping.{RESET}"); return 1

    creds = None
    if args.account_id:
        creds = _account_creds(cfg, args.account_id)
        if not creds:
            avail = _list_account_ids(cfg)
            print(f"\n{BOLD}{RED}Account '{args.account_id}' not found in config.json.{RESET}")
            if avail:
                print(f"  Available account ids: {', '.join(avail)}")
                print(f"  Retry with:  python sp_diagnose.py --marketplace {mkt} --account-id <id>")
            else:
                print("  No accounts array in config.json -- omit --account-id to use top-level creds.")
            return 1
    else:
        creds = {
            "lwa_app_id":        cfg.get("sp_api_client_id", ""),
            "lwa_client_secret": cfg.get("sp_api_client_secret", ""),
            "refresh_token":     cfg.get("sp_api_refresh_token", ""),
        }

    ok, token = test_lwa_token(creds["lwa_app_id"], creds["lwa_client_secret"], creds["refresh_token"])
    fails += 0 if ok else 1
    if not ok:
        print(f"\n{BOLD}{RED}Stopping: no LWA token = no SP-API calls possible.{RESET}"); return fails

    # SP-API layer tests
    ok, _sellers_body = test_sellers(host, token); fails += 0 if ok else 1
    ok = test_catalog(host, token, mkt_id, asin);  fails += 0 if ok else 1
    ok = test_pricing(host, token, mkt_id, asin);  fails += 0 if ok else 1
    ok = test_fees(host, token, mkt_id, asin);     fails += 0 if ok else 1
    ok = test_definitions(host, token, mkt_id, args.product_type); fails += 0 if ok else 1

    # Verdict
    print()
    if fails == 0:
        print(f"{BOLD}{GRN}All checks passed.{RESET} If UK still fails during a real run, the cause is")
        print("intermittent (slow route + short default timeout). Retries in the app now handle that.")
    else:
        print(f"{BOLD}{RED}{fails} check(s) failed.{RESET} Each FAIL line above says WHICH layer and HOW to fix it.")
    return fails


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ncancelled.")
        sys.exit(130)
