"""One Amazon seller is one workspace.

WHAT WAS SEEN, on the live app, 21 Aug 2026. The account switcher listed seven
entries where the config has six:

    Jack Reacherd (UK)          A34CMN3Q5Q4U3Z
    Sheelady (USA)              A1W1VC2O2BR7M2
    Headbanger Lures            draft-only, no seller
    Miles Lubricants            draft-only
    SELVORA LIMITED             AV6F4N8287Q6F
    Nestwell Goods LTD          A8YN8LJZAAYT4
    Amazon seller ZAAYT4        A8YN8LJZAAYT4   <-- the same company, twice

"Amazon seller ZAAYT4" is the fallback label the OAuth callback builds from the
last six characters of the merchant token when it has no better name.

HOW. The callback names a workspace after the merchant token Amazon returns --
amzn_<token>_<marketplace> -- so that a seller who authorizes AGAIN updates their
record rather than leaving a stale one behind. That much is right. But it only
looked at the id, and never asked whether some OTHER workspace already held that
seller_id. So a seller set up BY HAND -- with a label, an output sheet, a VAT
rate, a COGS mode and a list of eleven marketplaces -- got a second, bare
workspace the first time they authorized.

WHY IT IS NOT COSMETIC. The new record carries none of those settings, so every
screen behaves differently inside it; listings, orders and costs land in
whichever of the two happens to be open; and the account guard treats them as two
different accounts, because by id they are.

TWO SEPARATE THINGS ARE TESTED HERE, and they are separate on purpose:
the CAUSE is fixed, and a duplicate that already exists is REPORTED rather than
repaired. Merging two workspaces moves listings, costs and orders between them,
and which record survives is the owner's decision.
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


from domain import accounts as A

FAKE = {"accounts": [
    {"id": "jack_uk", "label": "Jack Reacherd (UK)", "seller_id": "A34CMN3Q5Q4U3Z",
     "default_marketplace": "UK", "marketplaces": ["UK", "DE", "FR"]},
    {"id": "nestwell_goods", "label": "Nestwell Goods LTD",
     "seller_id": "A8YN8LJZAAYT4", "default_marketplace": "UK",
     "marketplaces": ["UK", "DE", "IT"], "vat_rate": 0,
     "output_spreadsheet_id": "SHEET123"},
    {"id": "headbanger_lures", "label": "Headbanger Lures", "marketplaces": []},
]}

print("== finding the workspace that already IS this seller ==")
check("by the merchant token", A.by_seller_id(FAKE, "A8YN8LJZAAYT4").get("id"),
      "nestwell_goods")
check("  in any case", A.by_seller_id(FAKE, "a8yn8ljzaayt4").get("id"),
      "nestwell_goods")
check("  with stray spaces", A.by_seller_id(FAKE, "  A8YN8LJZAAYT4 ").get("id"),
      "nestwell_goods")
check("a seller nobody has", A.by_seller_id(FAKE, "AZZZZZZZZZZZZ"), {})
check("an empty token matches NOTHING", A.by_seller_id(FAKE, ""), {})
check("  and neither does None", A.by_seller_id(FAKE, None), {})
# Headbanger has no seller_id at all. "" == "" would hand every unconnected
# workspace to the first seller who authorized.
falsy("a workspace with no seller is never matched",
      any(a["id"] == "headbanger_lures"
          for a in [A.by_seller_id(FAKE, "") or {"id": None}]))

print("\n== matched on the seller, NOT on the marketplace ==")
# A workspace holds a LIST of marketplaces: one seller trading in eleven
# countries is one account here. Asking about a country it also sells in must
# not create a second record.
for mkt in ("UK", "DE", "IT", "PL", ""):
    check("  asking about %-3s still finds it" % (mkt or "(none)"),
          A.by_seller_id(FAKE, "A8YN8LJZAAYT4", None, mkt).get("id"),
          "nestwell_goods")

print("\n== duplicates are found, and named ==")
check("a clean config has none", A.duplicate_sellers(FAKE), {})
LIVE = {"accounts": FAKE["accounts"] + [
    {"id": "amzn_a8yn8ljzaayt4_uk", "label": "", "seller_id": "A8YN8LJZAAYT4",
     "marketplace": "UK", "auth": "oauth"}]}
check("the live shape is caught", A.duplicate_sellers(LIVE),
      {"A8YN8LJZAAYT4": ["nestwell_goods", "amzn_a8yn8ljzaayt4_uk"]})
check("  and the CONFIGURED record is the one preferred",
      A.by_seller_id(LIVE, "A8YN8LJZAAYT4", None, "UK").get("id"),
      "nestwell_goods")
truthy("  which is the one holding the sheet",
       A.by_seller_id(LIVE, "A8YN8LJZAAYT4").get("output_spreadsheet_id"))

print("\n== the callback writes into the record that is already there ==")
O = read("routes", "auth_oauth_routes.py")
_cb = O.split("acct_id = \"amzn_%s_%s\"")[1].split("try:\n            _acc.save_account")[0]
truthy("it asks whether this seller already has a workspace",
       "_acc.by_seller_id(cfg, partner, CONFIG_PATH, mkt)" in _cb)
truthy("  only when the derived id found nothing", "if not existing:" in _cb)
truthy("  and then keeps THAT id", 'acct_id = str(existing["id"])' in _cb)
truthy("  so nothing pointing at it is orphaned", "orphaned" in _cb)
# The existing record's own settings must survive: the account dict is built
# with **existing first, so every field it already had is kept unless the
# authorization genuinely replaces it.
truthy("the existing settings are kept", "**existing," in O)
_acct = O.split("account = {")[1].split("}")[0]
for keep in ("refresh_token", "seller_id", "status"):
    truthy("  %s is (re)written by the authorization" % keep, keep in _acct)
falsy("  and the label is not overwritten",
      'label": ("Amazon seller' in _acct)
truthy("  it is only a fallback", 'existing.get("label") or ' in _acct)

print("\n== an existing duplicate is reported, not silently merged ==")
DOC = A.duplicate_sellers.__doc__ or ""
truthy("the helper says why it does not repair", "owner's call" in DOC)
from domain import deploy_check as DC
tmp = tempfile.mkdtemp()
try:
    p = os.path.join(tmp, "config.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(LIVE))
    r = DC.check(p)
    item = [i for i in r["checks"] if "Amazon seller" in i["name"]]
    check("the deployment check has an item for it", len(item), 1)
    if item:
        falsy("  and it fails on the live shape", item[0]["ok"])
        truthy("  naming the seller", "A8YN8LJZAAYT4" in item[0]["detail"])
        truthy("  and both workspaces",
               "nestwell_goods" in item[0]["detail"]
               and "amzn_a8yn8ljzaayt4_uk" in item[0]["detail"])
        truthy("  and saying what it costs",
               "split" in item[0]["why"])
        truthy("  and what to do", "Manage accounts" in item[0]["why"])
    io.open(p, "w", encoding="utf-8").write(json.dumps(FAKE))
    r2 = DC.check(p)
    item2 = [i for i in r2["checks"] if "Amazon seller" in i["name"]]
    truthy("a clean config passes it", item2 and item2[0]["ok"])
except Exception as e:
    fails.append("deployment check")
    print("  FAIL deployment check:", str(e)[:200])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n== against the real config on this machine ==")
try:
    cfg = json.load(io.open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    dupes = A.duplicate_sellers(cfg, "config.json")
    ids = [a.get("id") for a in cfg.get("accounts", [])]
    print("     %d workspaces: %s" % (len(ids), ", ".join(str(i) for i in ids)))
    check("no duplicate seller here", dupes, {})
    # Every workspace that HAS a seller id must be findable by it.
    for a in cfg.get("accounts", []):
        sid = str(a.get("seller_id") or "").strip()
        if sid:
            check("  %s is found by its own token" % a.get("id"),
                  A.by_seller_id(cfg, sid, "config.json").get("id"), a.get("id"))
    print("     (the LIVE app has a seventh, 'Amazon seller ZAAYT4' — same "
          "token as nestwell_goods. This code stops another; that one is a "
          "decision for the owner.)")
except FileNotFoundError:
    print("  (no config.json on this machine)")

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
