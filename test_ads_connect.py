"""The Amazon Advertising connection -- read-only, and honest about the region.

    "i want each and every feature and page about the inventory and ppc, of
     orbit into my app, please built them"

Six of Orbit's PPC features are not blocked on effort. They are blocked on a
connection this app did not have:

    the day trail (cumulative spend by hour)    the report has no hour
    the 7 / 14 / 30 day toggle                  one report is one window
    the per-ASIN table                          the report has no ASIN column
    Sponsored Products / Brands / Display       the report is SP only
    the enabled / paused filter                 the report has no status
    the live tracker                            needs live campaign data

The Advertising API is a DIFFERENT product from SP-API: its own developer
registration, its own Login-with-Amazon application, its own refresh token, and
an account concept of its own (a PROFILE -- one advertising account in one
marketplace). An SP-API token will not authenticate against it and none can be
derived from it, so it has to be connected separately and only the account owner
can do that.

WHAT THIS FILE PINS

  1. IT CANNOT WRITE. Rule 8 says never change a bid or a budget without an
     explicit value in the message. A module with no POST cannot be made to
     break that rule by a later mistake, so the absence is tested.
  2. The region is DERIVED from the marketplace, not configured. A token issued
     in Europe fails against the North America host with a 401 that reads
     exactly like bad credentials, and that is the mistake this will meet most
     often.
  3. Nothing is guessed. Four credentials are needed; the test says which are
     missing rather than failing with a network error.
"""
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

from api import amazon_ads as _ads          # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


print("\n== the region is derived from the marketplace, never configured ==")
# A configured region is a region that can disagree with the marketplace the
# rest of the app is using. This one cannot.
for mkt, want in (("UK", "EU"), ("GB", "EU"), ("DE", "EU"), ("FR", "EU"),
                  ("US", "NA"), ("CA", "NA"), ("MX", "NA"), ("BR", "NA"),
                  ("JP", "FE"), ("AU", "FE"), ("SG", "FE")):
    check("%s is served by %s" % (mkt, want), _ads.region_for(mkt), want)
check("  lower case is the same marketplace", _ads.region_for("uk"), "EU")
check("  and an unknown one does not crash a screen",
      _ads.region_for("ZZ"), "EU")
check("  nor does None", _ads.region_for(None), "EU")
check("each region has its own host",
      len({_ads.endpoint_for(m) for m in ("UK", "US", "JP")}), 3)
truthy("the EU host is the EU one", "-eu." in _ads.endpoint_for("UK"))

print("\n== four credentials, and it says which are missing ==")
check("nothing set -> all four named", _ads.missing(_ads.creds_for({})),
      list(_ads.FIELDS))
part = {"ads_client_id": "x", "ads_client_secret": "y"}
check("half set -> only the half that is missing",
      _ads.missing(_ads.creds_for(part)),
      ["ads_refresh_token", "ads_profile_id"])
check("  whitespace is not a credential",
      _ads.missing(_ads.creds_for({"ads_client_id": "   "})),
      list(_ads.FIELDS))

print("\n== an account may advertise through its own login ==")
# Same shape as the eBay keys: one set serves every account, and an account
# advertising through its own agency login overrides it.
g = {"ads_client_id": "GLOBAL", "ads_client_secret": "GS",
     "ads_refresh_token": "GR", "ads_profile_id": "1"}
a = {"ads_client_id": "ACCOUNT", "ads_profile_id": "2"}
c = _ads.creds_for(g, a)
check("the account's client id wins", c["ads_client_id"], "ACCOUNT")
check("  and its profile", c["ads_profile_id"], "2")
check("  while the global secret is still used", c["ads_client_secret"], "GS")
check("a callable config is accepted, like everywhere else in this app",
      _ads.creds_for(lambda: g)["ads_client_id"], "GLOBAL")

print("\n== the test never raises, and says which kind of not-working ==")
r = _ads.test({}, {}, "UK")
check("unset is reported as not connected", r["connected"], False)
check("  with the four names, not a network error", len(r["missing"]), 4)
truthy("  and the region, because that is the usual mistake", r.get("region"))
truthy("  in words somebody can act on", "Still needed" in r["error"])
# Credentials that are set but wrong must not throw either -- a screen that
# crashes on a bad token tells you nothing about the token.
r2 = _ads.test({"ads_client_id": "no", "ads_client_secret": "no",
                "ads_refresh_token": "no", "ads_profile_id": "1"}, {}, "UK")
check("credentials that Amazon refuses are reported, not raised",
      r2["connected"], False)
check("  and nothing is claimed to be missing", r2["missing"], [])
truthy("  Amazon's own words are passed through", r2.get("error"))

print("\n== IT CANNOT WRITE (Rule 8) ==")
SRC = open(r"D:\AltaScraper\api\amazon_ads.py", encoding="utf-8-sig").read()
BODY = re.sub(r'"""[\s\S]*?"""', "", SRC)
BODY = "\n".join(re.sub(r"#.*$", "", ln) for ln in BODY.split("\n"))
# The ONE POST is the token exchange, which is how a read authenticates.
posts = re.findall(r'method="POST"', BODY)
check("exactly one POST exists, and it is the login", len(posts), 1)
# The generic poster is fine; what matters is that its ONLY call site is the
# token exchange. A second call site would be a way to send something.
calls = re.findall(r"(?<!def )\b_post_form\(([A-Za-z_]+)", BODY)
check("  its only caller is the token exchange", calls, ["TOKEN_URL"])
for banned in ("putCampaign", "updateCampaign", "createCampaign", "bid",
               "budget", "negativeKeyword", 'method="PUT"', 'method="DELETE"',
               'method="PATCH"'):
    check("no way to change a campaign (%r)" % banned, banned in BODY, False)
truthy("every advertising call goes through the one read helper",
       re.search(r"def _get\(path, creds", BODY))

print("\n== the settings route keeps secrets secret ==")
RT = open(r"D:\AltaScraper\routes\settings_routes.py", encoding="utf-8-sig").read()
truthy("there is a route to set them", '"/settings/ads"' in RT)
truthy("  and one that tests the connection", '"/settings/ads/test"' in RT)
# GET returns whether a secret is stored and its tail, never the value.
m = re.search(r'def settings_ads\(\)[\s\S]*?def settings_ads_test', RT)
truthy("the GET body was found", m)
body = m.group(0) if m else ""
for secret in ("ads_client_secret", "ads_refresh_token"):
    check("GET never returns %s itself" % secret,
          bool(re.search(r'"%s":\s*str\(cfg' % secret, body)), False)
truthy("  it reports only whether one is stored",
       '"has_secret"' in body and '"has_refresh"' in body)
truthy("  and a masked tail so you can tell which is saved", '"secret_tail"' in body)
# A blank secret must KEEP the stored one, or correcting the profile id wipes
# the token -- the same rule the eBay cert already follows.
truthy("a blank secret keeps the stored one",
       re.search(r"if v and not v\.startswith", body))
truthy("credentials are written through the one atomic writer",
       "_settings.write_raw(" in body)

print("\n== it is guarded ==")
G = open(r"D:\AltaScraper\auth\guard.py", encoding="utf-8-sig").read()
# /settings/ads sits under the /settings prefix, which already requires
# manage_accounts. Pinned because the prefix rule is easy to move.
truthy("/settings requires manage_accounts",
       re.search(r'\("/settings",\s*"manage_accounts"\)', G))

print("\n== the screen can connect it ==")
JS = open(r"D:\AltaScraper\static\js\settings.js", encoding="utf-8-sig").read()
truthy("there is a form", "saveAdsSettings" in JS)
truthy("  and a test button", "testAdsSettings" in JS)
truthy("  which lists the profiles this login can see", "useAdsProfile" in JS)
truthy("  so the profile id is picked, not typed from a screenshot",
       re.search(r"use this[\s\S]{0,120}useAdsProfile", JS))
truthy("  and it names the region when the connection fails",
       re.search(r"advertising endpoint", JS))

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
