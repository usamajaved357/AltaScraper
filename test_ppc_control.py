"""Campaign controls (owner, 30 Sep 2026: "an option to turn on or off the
campaigns and change the budget, bids ... i want it here") and the true
campaign status ("many campaigns are actually turned off in seller central but
are shown as enabled here").

Amazon is replaced by a stub: nothing here reaches the network.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


TMP = tempfile.mkdtemp(prefix="altappcctl_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "ws1", "label": "One"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "c.db")

from api import amazon_ads_manage as M     # noqa: E402
from domain import ppc_control as PC       # noqa: E402
from domain import sales_queries as SQ     # noqa: E402
from domain import ads_sync as AS          # noqa: E402
from data import db as _db                 # noqa: E402

print("== 1. the module can reach only its own list ==")
try:
    M._call("PUT", "/sp/campaigns/../../v2/profiles", {"ads_profile_id": "1"}, "UK", {})
    refused = False
except RuntimeError as e:
    refused = "Refused" in str(e)
check("anything off the exact list is refused before a request exists", refused, True)
check("  the read module still cannot write", __import__("api.amazon_ads", fromlist=["x"])._POST_ALLOWED,
      ("/reporting/reports",))

# ---- a stub Amazon -----------------------------------------------------------
LIVE = {"campaigns": [{"campaign_id": "C1", "name": "Hose exact", "state": "ENABLED", "budget": 10.0,
                       "budget_type": "DAILY", "targeting_type": "MANUAL"},
                      {"campaign_id": "C2", "name": "Mat auto", "state": "PAUSED", "budget": 5.0,
                       "budget_type": "DAILY", "targeting_type": "AUTO"}]}
CALLS = []
AS.creds_or_why = lambda ws, cp=None: ({"ads_profile_id": "1"}, None)
M.list_campaigns = lambda c, m: [dict(x) for x in LIVE["campaigns"]]


def _upd(c, m, cid, state=None, budget=None):
    CALLS.append(("campaign", cid, state, budget))
    for x in LIVE["campaigns"]:
        if x["campaign_id"] == cid:
            if state:
                x["state"] = state
            if budget is not None:
                x["budget"] = budget
    return True, ""


M.update_campaign = _upd

print("\n== 2. Amazon's current state is what the page says ==")
c = _db.get_db(CFG)
c.execute("INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, campaign_id, campaign_name, "
          "status, budget, spend, ad_sales, clicks, impressions, ad_orders) VALUES "
          "('ws1','UK','2026-09-20','C2','Mat auto','ENABLED',5,1,0,1,10,0)")
c.commit()
r = PC.refresh_campaigns(CFG, "ws1", "UK")
check("the live list is read and kept", (r.get("ok"), r.get("count")), (True, 2))
lat = SQ.campaign_latest(CFG, "ws1", "UK")
check("a campaign paused in Seller Central reads PAUSED, not its last report row",
      (lat["C2"]["status"], lat["C2"]["status_source"]), ("PAUSED", "amazon"))
check("  and a campaign with no report rows at all is still known", lat["C1"]["status"], "ENABLED")

print("\n== 3. a change is the owner's typed value, read before and after ==")
check("no value typed, nothing changes",
      PC.change(CFG, "ws1", "UK", "campaign", "C1", "C1", amount="")["ok"], False)
check("a zero budget is refused", PC.change(CFG, "ws1", "UK", "campaign", "C1", "C1", amount="0")["ok"], False)
check("a slipped decimal (50000) is refused",
      PC.change(CFG, "ws1", "UK", "campaign", "C1", "C1", amount="50000")["ok"], False)
check("  and none of those reached Amazon", CALLS, [])
g = PC.change(CFG, "ws1", "UK", "campaign", "C1", "C1", amount="12.5", who="owner")
check("a typed budget is sent, read back and verified",
      (g["ok"], g["before"]["budget"], g["after"]["budget"], g["verified"]), (True, 10.0, 12.5, True))
g = PC.change(CFG, "ws1", "UK", "campaign", "C2", "C2", state="enabled")
check("switching a paused campaign on", (g["ok"], g["after"]["state"]), (True, "ENABLED"))
check("  and the kept list follows", SQ.campaign_latest(CFG, "ws1", "UK")["C2"]["status"], "ENABLED")
check("ARCHIVED is not offered", PC.change(CFG, "ws1", "UK", "campaign", "C1", "C1", state="ARCHIVED")["ok"], False)
check("an id Amazon does not have is refused",
      PC.change(CFG, "ws1", "UK", "campaign", "NOPE", "NOPE", state="PAUSED")["ok"], False)
ev = [row["action"] for row in c.execute("SELECT action FROM drppc_events ORDER BY id")]
check("every step is in the ledger: requested, sent, verified",
      ev[:3], ["change_requested", "change_sent", "change_verified"])

print("\n== 4. the routes ==")
RT = open(os.path.join(HERE, "routes", "ppc_control_routes.py"), "rb").read().decode("utf-8")
check("a write needs confirmed=True", RT.count('b.get("confirmed") is not True') >= 2, True)
check("  and an account NAMED by the request (never the open one)",
      "The request did not say which account" in RT, True)
G = open(os.path.join(HERE, "auth", "guard.py"), "rb").read().decode("utf-8")
check("writes need publish; reading the list needs ppc",
      G.index('("/ppc/control/campaigns",') < G.index('("/ppc/control",') < G.index('("/ppc",'), True)
JS = open(os.path.join(HERE, "static", "js", "ppccontrol.js"), "rb").read().decode("utf-8")
check("a money box starts empty (nothing suggested)", '+ "\\nType the new amount.", "",' in JS, True)
check("the account is pinned before the dialog", "screenStillIn(pin)" in JS, True)

print("\n== 5. the routes, driven (review of 30 Sep 2026) ==")
from flask import Flask                     # noqa: E402
import routes.ppc_control_routes as R       # noqa: E402
AS.marketplace_for = lambda cp, acc: ("UK", "")       # the profile covers UK
app = Flask(__name__)
R.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
           _state={"active_account_id": "ws1", "active_marketplace": "IT"},
           _active_account=lambda: {"id": "ws1"})
cl = app.test_client()
g = cl.post("/ppc/control/change", json={"confirmed": True, "entity_id": "ws1", "kind": "campaign",
                                         "campaign_id": "C1", "state": "PAUSED"})
check("no account named -> refused, even with an id that looks like one",
      (g.status_code, "did not say which account" in g.get_json()["error"]), (400, True))
g = cl.post("/ppc/control/change", json={"confirmed": True, "account": "ws1", "marketplace": "IT",
                                         "entity_id": "C1", "kind": "campaign", "campaign_id": "C1",
                                         "state": "PAUSED"})
check("a screen naming another marketplace than the ad profile's is refused",
      (g.status_code, "advertising is on UK" in g.get_json()["error"]), (409, True))
before = list(CALLS)
g = cl.post("/ppc/control/change", json={"account": "ws1", "marketplace": "UK", "entity_id": "C1",
                                         "kind": "campaign", "campaign_id": "C1", "state": "PAUSED"})
check("not confirmed -> refused, nothing sent", (g.status_code, CALLS == before), (400, True))
g = cl.get("/ppc/control/campaigns?account=ws1&marketplace=IT")
check("reading the list files it under the PROFILE's marketplace, not the screen's",
      (g.get_json().get("marketplace"),
       c.execute("SELECT COUNT(*) FROM ads_campaigns WHERE marketplace='IT'").fetchone()[0]), ("UK", 0))

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
