"""Phase D -- the step that actually changes a live listing.

Everything before this decides. This pushes, so the tests are mostly about
REFUSING to: the master switch, the per-SKU arming, the mandatory minimum price,
the cooldown, and the two ways Amazon can say no. A repricer that pushes when it
should not is worse than one that never pushes at all, and the only way to know
which this is, is to try every route to Amazon and check it is shut.

Nothing here touches the network: api/amazon_listings.py is stubbed, and the
stub records exactly what would have been sent.
"""
import os, sys, json, copy, tempfile, shutil, datetime as dt
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

TMP = tempfile.mkdtemp(prefix="altasrcd_")
CFG = os.path.join(TMP, "config.json")
def write_cfg(**extra):
    json.dump({"accounts": [{"id": "jack_uk", "seller_id": "SELLER1",
                             "lwa_client_id": "x", "lwa_client_secret": "y",
                             "refresh_token": "z"}], **extra},
              open(CFG, "w"))
write_cfg()
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "d.db")

from api import amazon_listings as AL
from domain import source_apply as AP
from domain import source_repo as R
from domain import sourcing as S
from domain import live_snapshots as LS

WS, MKT, SKU = "jack_uk", "UK", "8.00_3Days_B0G1K5B7QS"
NOW = dt.datetime(2026, 8, 14, 12, 0, 0)
FRESH = "2026-08-14 11:00:00"

# What Amazon holds for this listing. The patch must be built by EDITING this,
# never by composing a shape from memory.
ATTRS = {
    "purchasable_offer": [{"marketplace_id": "A1F83G8C2ARO7P", "currency": "GBP",
                           "audience": "ALL",
                           "our_price": [{"schedule": [{"value_with_tax": 20.00}]}]}],
    "fulfillment_availability": [{"fulfillment_channel_code": "DEFAULT",
                                  "quantity": 5, "lead_time_to_ship_max_days": 5}],
}

sent = []
class Stub:
    status_get = AL.OK
    status_patch = AL.OK
    amazon_status = "ACCEPTED"
    issues = []
    attrs = ATTRS

def fake_get(creds, mkt, seller, sku, mkt_id, included=None, timeout=60):
    return {"status": Stub.status_get, "attributes": Stub.attrs,
            "product_type": "HOME_BED_AND_BATH", "error": "not found",
            "http_code": 404 if Stub.status_get == AL.GONE else None, "raw": {}}

def fake_patch(creds, mkt, seller, sku, mkt_id, product_type, patches,
               issue_locale="en_GB", timeout=60):
    sent.append({"sku": sku, "product_type": product_type, "patches": patches,
                 "marketplace": mkt, "seller": seller})
    ok = Stub.status_patch == AL.OK
    return {"status": Stub.status_patch, "submission_id": "SUB123",
            "amazon_status": Stub.amazon_status, "issues": Stub.issues,
            "error": "" if ok else "Amazon answered " + Stub.amazon_status}

AP._al.get_item = fake_get
AP._al.patch = fake_patch

def creds_for(ws, mkt):
    return ({"lwa_app_id": "x"}, "A1F83G8C2ARO7P", "SELLER1")

def setup_sku(sku=SKU, price=8.0, ship=1.5, stock=True, disp=3):
    LS.save(CFG, WS, MKT, [{"sku": sku, "price": "20.00", "qty": 5, "handling": 5,
                            "fulfillment": "MFN", "status": "Active"}],
            report_source="test")
    R.enrol(CFG, WS, MKT, sku)
    sid = R.add_source(CFG, WS, MKT, sku, "https://ebay.co.uk/itm/111", label="eBay A")
    R.record_check(CFG, sid, {"status": S.FETCHED, "price": price, "shipping": ship,
                              "currency": "GBP", "in_stock": stock,
                              "dispatch_days": disp, "checked_at": FRESH})
    return sid


print("=== the master switch is OFF until someone turns it on ===")
check("a fresh config is off", AP.is_enabled({}), False)
check("  explicitly false is off", AP.is_enabled({"repricer_enabled": False}), False)
check("  and on is on", AP.is_enabled({"repricer_enabled": True}), True)
check("a callable config works too",
      AP.is_enabled(lambda: {"repricer_enabled": True}), True)


print("\n=== every gate, tried one at a time ===")
setup_sku()
DEC = {"action": "update", "price": 18.24, "quantity": 5, "lead_days": 5,
       "source_id": 1, "reason": "test", "blocked_by": "", "rejections": [],
       "inputs_age_mins": 60}

def why(cfg=None):
    return AP.why_not(CFG, cfg if cfg is not None else {"repricer_enabled": True},
                      WS, MKT, SKU, DEC, NOW)

check("master switch off stops everything", AP.why_not(CFG, {}, WS, MKT, SKU, DEC, NOW),
      "the repricer's master switch is off")
truthy("a SKU in dry run is not pushed", "dry run" in why())

R.enrol(CFG, WS, MKT, SKU, mode="live")
truthy("armed but with NO minimum price is still refused", "minimum price" in why())
truthy("  and the refusal explains why that matters",
       "misread supplier cost" in why())

# The per-unit allowances are stated, not assumed. 3.00 postage / 2.00 ads /
# 1.00 profit were the defaults when 18.24 was written into DEC above; they are
# 0.00 now, and min_roi_pct is the separate never-sell-at-break-even floor.
R.save_rule(CFG, WS, MKT, SKU, {"min_price": 12.00, "shipping_label": 3.00,
                                "ads_margin": 2.00, "min_profit": 1.00,
                                "min_roi_pct": 0})
check("armed, with a minimum, master on -> allowed", why(), "")

print("  -- a held decision is never pushed --")
truthy("blocked decisions stay blocked",
       AP.why_not(CFG, {"repricer_enabled": True}, WS, MKT, SKU,
                  dict(DEC, blocked_by="price move of 90% exceeds the limit"), NOW))
check("a no-op is not pushed",
      AP.why_not(CFG, {"repricer_enabled": True}, WS, MKT, SKU,
                 dict(DEC, action="none"), NOW), "nothing to change")


print("\n=== the patch is built by EDITING what Amazon returned ===")
# ONLY WHAT DIFFERS IS SENT.
#
#     "if the prices dont need to be changed i think repricer should not change
#      anything, if a price change is required yes we should do it. the stock
#      update is requured, yes do it"
#
# ATTRS is a listing already at quantity 5 and 5 days, and DEC asks for 5 and 5
# -- so the availability patch has nothing to say and is not sent. This used to
# assert two operations, from when the price was rewritten on every push
# whether or not it had moved. See test_push_only_changes.py for the full set.
patches, err = AP.build_patches(ATTRS, DEC, "A1F83G8C2ARO7P")
check("no error", err, "")
check("the price moved, the stock did not: one operation", len(patches), 1)
po = [p for p in patches if p["path"].endswith("purchasable_offer")][0]
check("  the price went into the schedule Amazon gave us",
      po["value"][0]["our_price"][0]["schedule"][0]["value_with_tax"], 18.24)
check("  and the rest of the offer is untouched",
      (po["value"][0]["currency"], po["value"][0]["audience"]), ("GBP", "ALL"))

# The same decision against a listing Amazon has let run out. Now BOTH go, and
# the availability shape is still built by editing what Amazon returned.
_oos = copy.deepcopy(ATTRS)
_oos["fulfillment_availability"][0]["quantity"] = 0
_oos["fulfillment_availability"][0]["lead_time_to_ship_max_days"] = 2
patches2, err2 = AP.build_patches(_oos, DEC, "A1F83G8C2ARO7P")
check("stock is wrong too: two operations", len(patches2), 2)
fa = [p for p in patches2 if p["path"].endswith("fulfillment_availability")][0]
check("  quantity set", fa["value"][0]["quantity"], 5)
check("  handling set", fa["value"][0]["lead_time_to_ship_max_days"], 5)
check("  the channel code is left alone",
      fa["value"][0]["fulfillment_channel_code"], "DEFAULT")
check("the original is NOT mutated",
      ATTRS["purchasable_offer"][0]["our_price"][0]["schedule"][0]["value_with_tax"], 20.0)

print("  -- and refuses rather than inventing one --")
_p, e = AP.build_patches({"fulfillment_availability": ATTRS["fulfillment_availability"]},
                         DEC, "A1F83G8C2ARO7P")
truthy("no purchasable_offer -> refused", "no purchasable_offer" in e)
_p, e2 = AP.build_patches({"purchasable_offer": [{"currency": "GBP"}]},
                          DEC, "A1F83G8C2ARO7P")
truthy("  an offer with no price schedule -> refused", "inventing a shape" in e2)
_p, e3 = AP.build_patches({"purchasable_offer": ATTRS["purchasable_offer"]},
                          dict(DEC, price=None, quantity=0, lead_days=None),
                          "A1F83G8C2ARO7P")
truthy("  no fulfillment_availability -> refused", "fulfillment_availability" in e3)

print("  -- a handling time is not written where none existed --")
no_lead = {"purchasable_offer": ATTRS["purchasable_offer"],
           "fulfillment_availability": [{"fulfillment_channel_code": "DEFAULT",
                                         "quantity": 2}]}
p2, _e = AP.build_patches(no_lead, DEC, "A1F83G8C2ARO7P")
fa2 = [p for p in p2 if p["path"].endswith("fulfillment_availability")][0]
check("quantity still set", fa2["value"][0]["quantity"], 5)
check("  but no lead time invented",
      "lead_time_to_ship_max_days" in fa2["value"][0], False)


print("\n=== an armed SKU actually gets pushed ===")
sent.clear()
res = AP.apply_one(CFG, {"repricer_enabled": True}, {"c": 1}, "A1F83G8C2ARO7P",
                   "SELLER1", WS, MKT, SKU, NOW)
check("applied", res["applied"], 1)
check("  one call to Amazon", len(sent), 1)
check("  for the right SKU", sent[0]["sku"], SKU)
check("  with a product type", sent[0]["product_type"], "HOME_BED_AND_BATH")
acts = R.recent_actions(CFG, WS, MKT, SKU)
check("  recorded as applied", acts[0]["applied"], 1)
truthy("  with Amazon's submission id kept", "SUB123" in acts[0]["reason"])

print("  -- and then the cooldown stops it happening again --")
sent.clear()
res2 = AP.apply_one(CFG, {"repricer_enabled": True}, {"c": 1}, "A1F83G8C2ARO7P",
                    "SELLER1", WS, MKT, SKU, NOW + dt.timedelta(hours=1))
check("not pushed again", res2["applied"], 0)
check("  nothing sent", len(sent), 0)
truthy("  and it says how long to wait", "waiting 4 hours" in res2["blocked_by"])

print("  -- until enough time has passed --")
sent.clear()
res3 = AP.apply_one(CFG, {"repricer_enabled": True}, {"c": 1}, "A1F83G8C2ARO7P",
                    "SELLER1", WS, MKT, SKU, NOW + dt.timedelta(hours=5))
check("pushed once the cooldown expires", res3["applied"], 1)


print("\n=== when Amazon says no, we do not record a success ===")
Stub.status_patch, Stub.amazon_status = AL.FAILED, "INVALID"
Stub.issues = [{"message": "Price is below the minimum allowed"}]
sent.clear()
res4 = AP.apply_one(CFG, {"repricer_enabled": True}, {"c": 1}, "A1F83G8C2ARO7P",
                    "SELLER1", WS, MKT, SKU, NOW + dt.timedelta(hours=10))
check("recorded as a FAILED push, not a success", res4["applied"], -1)
truthy("  carrying Amazon's own words", "below the minimum" in res4["blocked_by"])
check("  and the log agrees",
      R.recent_actions(CFG, WS, MKT, SKU)[0]["applied"], -1)
Stub.status_patch, Stub.amazon_status, Stub.issues = AL.OK, "ACCEPTED", []

print("  -- a SKU Amazon does not have --")
Stub.status_get = AL.GONE
sent.clear()
res5 = AP.apply_one(CFG, {"repricer_enabled": True}, {"c": 1}, "A1F83G8C2ARO7P",
                    "SELLER1", WS, MKT, SKU, NOW + dt.timedelta(hours=20))
check("nothing pushed", res5["applied"], 0)
check("  and nothing sent", len(sent), 0)
truthy("  said plainly", "does not have this SKU" in res5["blocked_by"])
Stub.status_get = AL.OK


print("\n=== the whole live pass ===")
# A fresh SKU with no push history, because the one above is now inside its
# cooldown -- and its reading would be stale by the time the cooldown expired,
# which is itself correct: a 30-hour-old reading must not move a live price.
LIVE_SKU = "9.50_3Days_B0LIVE00001"
R.enrol(CFG, WS, MKT, SKU, mode="dry_run")          # stand the first one down
LS.save(CFG, WS, MKT,
        [{"sku": SKU, "price": "20.00", "qty": 5, "handling": 5, "fulfillment": "MFN"},
         {"sku": LIVE_SKU, "price": "22.00", "qty": 5, "handling": 5,
          "fulfillment": "MFN", "status": "Active"}], report_source="test")
lsid = R.add_source(CFG, WS, MKT, LIVE_SKU, "https://ebay.co.uk/itm/222", label="eBay B")
R.record_check(CFG, lsid, {"status": S.FETCHED, "price": 8.0, "shipping": 1.5,
                           "currency": "GBP", "in_stock": True, "dispatch_days": 3,
                           "checked_at": FRESH})
# Same as above: the three per-unit allowances are stated rather than assumed,
# because they no longer default to 3.00/2.00/1.00. 9.50 landed then prices at
# 18.24, which is inside the 25% change cap from 22.00 -- with them at zero it
# would ask 13.42, a 39% cut, and the cap would rightly refuse to push it.
R.save_rule(CFG, WS, MKT, LIVE_SKU, {"min_price": 12.0, "shipping_label": 3.00,
                                     "ads_margin": 2.00, "min_profit": 1.00,
                                     "min_roi_pct": 0})

sent.clear()
out = AP.run_live(CFG, {}, creds_for, now=NOW)
check("master off -> nothing at all", out["pushed"], 0)
check("  and nothing sent", len(sent), 0)
truthy("  and it says so", "master switch is off" in out["note"])

R.enrol(CFG, WS, MKT, "DRY_ONE")            # enrolled but never armed
R.enrol(CFG, WS, MKT, LIVE_SKU, mode="live")
sent.clear()
out = AP.run_live(CFG, {"repricer_enabled": True}, creds_for, now=NOW)
check("only ARMED SKUs are even considered", out["armed"], 1)
check("  and it pushed that one", out["pushed"], 1)
check("  sending exactly one patch", len(sent), 1)
check("  for the armed SKU", sent[0]["sku"], LIVE_SKU)

print("  -- a stale reading does not move a live price --")
sent.clear()
out = AP.run_live(CFG, {"repricer_enabled": True}, creds_for,
                  now=NOW + dt.timedelta(hours=30))
check("nothing pushed on 30-hour-old readings", out["pushed"], 0)
check("  and nothing sent", len(sent), 0)

print("  -- one broken SKU does not stop the rest --")
R.save_rule(CFG, WS, MKT, "BROKEN", {"min_price": 5.0})
R.enrol(CFG, WS, MKT, "BROKEN", mode="live")
def bad_creds(ws, mkt):
    raise RuntimeError("no credentials for this account")
out = AP.run_live(CFG, {"repricer_enabled": True}, bad_creds, now=NOW)
check("both armed SKUs were attempted", out["armed"], 2)
check("  and the pass completed", out["ok"], True)
check("  reporting the ones it skipped", out["skipped"], 2)


print("\n=== the endpoints ===")
from flask import Flask
import routes.sourcing_routes as sr
app = Flask(__name__); app.secret_key = "t"
_state = {"active_account_id": WS, "active_marketplace": MKT}
sr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS}, _state=_state)
c = app.test_client()

print("  -- arming refuses without a minimum price --")
R.save_rule(CFG, WS, MKT, "NEEDS_MIN", {"max_change_pct": 20.0})
R.enrol(CFG, WS, MKT, "NEEDS_MIN")
r = c.post("/sourcing/arm", json={"sku": "NEEDS_MIN", "live": True})
check("refused", r.status_code, 400)
truthy("  with the reason", "minimum price" in r.get_json()["error"])
check("  and it is still in dry run",
      [x for x in R.enrolled(CFG, WS, MKT) if x["sku"] == "NEEDS_MIN"][0]["mode"],
      "dry_run")

c.post("/sourcing/rules", json={"sku": "NEEDS_MIN", "rule": {"min_price": 9.99}})
r = c.post("/sourcing/arm", json={"sku": "NEEDS_MIN", "live": True})
check("with a minimum it arms", r.get_json()["mode"], "live")
truthy("  and says what it will and will not do", "never below 9.99" in r.get_json()["note"])
check("disarming always works",
      c.post("/sourcing/arm", json={"sku": "NEEDS_MIN", "live": False}).get_json()["mode"],
      "dry_run")

print("  -- the master switch round-trips through config --")
check("off to start", c.get("/sourcing/master").get_json()["enabled"], False)
c.post("/sourcing/master", json={"enabled": True})
check("turned on", json.load(open(CFG)).get("repricer_enabled"), True)
check("  and reported on", c.get("/sourcing/master").get_json()["enabled"], True)
c.post("/sourcing/master", json={"enabled": False})
check("turned off again", c.get("/sourcing/master").get_json()["enabled"], False)

print("  -- the screen can tell you whether it is live --")
j = c.get("/sourcing/list").get_json()
check("master state is reported", j["master_enabled"], False)
row = [x for x in j["rows"] if x["sku"] == SKU][0]
check("  and each row carries its own minimum price", row["rule"]["min_price"], 12.0)
check("  and that this one was stood down", row["mode"], "dry_run")
armed = [x for x in j["rows"] if x["sku"] == LIVE_SKU][0]
check("  while the armed one says so", armed["mode"], "live")
check("a SKU with no minimum shows it as unset -- which is why Arm refuses",
      [x for x in j["rows"] if x["sku"] == "DRY_ONE"][0]["rule"]["min_price"], None)

print("  -- permissions --")
from auth import guard
check("arming needs publish", guard.required_permission("/sourcing/arm", "POST"), "publish")
check("the master switch needs publish",
      guard.required_permission("/sourcing/master", "POST"), "publish")
check("pushing needs publish", guard.required_permission("/sourcing/apply", "POST"), "publish")

print("\n=== the timer cannot skip the gates ===")
from data import scheduler as SCH
check("the apply job exists", "sourcing_apply" in SCH._JOBS, True)
check("  on the same 4 hour beat", SCH._JOBS["sourcing_apply"]["hours"], 4)
check("  and refuses cleanly when unbound",
      SCH.run_job("sourcing_apply", None)["ok"], False)

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
