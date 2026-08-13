"""Phase C -- the dry run, and the screen that shows it.

The dry run's value depends entirely on it being the REAL decision. If it were a
preview assembled for display, reading it for a week would prove nothing. So the
tests here check that what gets recorded is what domain/sourcing.py actually
decided, that it is recorded as not-applied, and that the two situations where a
guard is missing -- an unknown current price, an FBA listing -- are refused out
loud rather than papered over.
"""
import os, sys, json, tempfile, shutil, datetime as dt
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

TMP = tempfile.mkdtemp(prefix="altasrcc_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [], "ebay_app_id": "A", "ebay_cert_id": "C"}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "c.db")

from domain import source_repo as R
from domain import source_run as RUN
from domain import sourcing as S
from domain import live_snapshots as LS

WS, MKT = "jack_uk", "UK"
SKU = "8.00_3Days_B0G1K5B7QS"
FBA_SKU = "9.00_3Days_B0FBA00001"
NOW = dt.datetime(2026, 8, 14, 12, 0, 0)
FRESH = "2026-08-14 11:00:00"


def snapshot(items):
    LS.save(CFG, WS, MKT, items, report_source="test")

def reading(sid, price=8.0, ship=1.5, stock=True, disp=3, status=S.FETCHED, at=FRESH):
    R.record_check(CFG, sid, {"status": status, "price": price, "shipping": ship,
                              "currency": "GBP", "in_stock": stock,
                              "dispatch_days": disp, "checked_at": at})


print("=== what Amazon has now, read from the catalogue we already hold ===")
snapshot([{"sku": SKU, "asin": "B0OURS0001", "price": "20.00", "qty": 5,
           "handling": 5, "fulfillment": "MFN", "status": "Active"},
          {"sku": FBA_SKU, "asin": "B0OURS0002", "price": "25.00", "qty": 9,
           "handling": None, "fulfillment": "AFN", "status": "Active"}])
cur = RUN.current_for(CFG, WS, MKT, SKU)
check("price", cur["price"], 20.0)
check("quantity", cur["quantity"], 5)
check("handling", cur["lead_days"], 5)
check("a SKU that is not in the snapshot says so", RUN.current_for(CFG, WS, MKT, "NOPE"), {})
check("and case does not matter",
      RUN.current_for(CFG, WS, MKT, SKU.lower())["price"], 20.0)


print("\n=== the ordinary case: it decides, and writes down what it decided ===")
R.enrol(CFG, WS, MKT, SKU)
sid = R.add_source(CFG, WS, MKT, SKU, "https://ebay.co.uk/itm/111", label="eBay A")
reading(sid)

current, d = RUN.decide_one(CFG, WS, MKT, SKU, NOW)
check("it would update", d["action"], "update")
check("  to the price the rule gives (9.50 landed -> 18.24)", d["price"], 18.24)
check("  handling 3 + 2 buffer", d["lead_days"], 5)

print("  -- and the recorded row IS that decision, not a retelling of it --")
res = RUN.dry_run(CFG, WS, MKT, now=NOW)
check("one SKU considered", res["skus"], 1)
check("  counted as a change", res["counts"]["update"], 1)
acts = R.recent_actions(CFG, WS, MKT, SKU)
check("an action was written", len(acts), 1)
a = acts[0]
check("  recorded as NOT applied", a["applied"], 0)
check("  the price it would set", a["to_price"], 18.24)
check("  and what it is now", a["from_price"], 20.0)
check("  the handling it would set", a["to_lead_days"], 5)
check("  naming the source used", a["source_id"], sid)
truthy("  with the arithmetic kept", "postage" in (a["reason"] or ""))
check("  the action matches what decide() said", a["action"], d["action"])
check("  and so does the price", a["to_price"], d["price"])


print("\n=== a guard that cannot run is refused, not skipped ===")
print("  -- unknown current price means max_change_pct has nothing to compare --")
R.enrol(CFG, WS, MKT, "NOT_IN_SNAPSHOT")
sid2 = R.add_source(CFG, WS, MKT, "NOT_IN_SNAPSHOT", "https://ebay.co.uk/itm/222")
reading(sid2)
_c, d2 = RUN.decide_one(CFG, WS, MKT, "NOT_IN_SNAPSHOT", NOW)
check("held rather than pushed", d2["action"], "none")
truthy("  and says the limit could not be applied", "change limit" in d2["blocked_by"])
truthy("  and tells you what to do about it", "Sync the catalogue" in d2["reason"])

print("  -- an FBA listing is not ours to reprice --")
R.enrol(CFG, WS, MKT, FBA_SKU)
sid3 = R.add_source(CFG, WS, MKT, FBA_SKU, "https://ebay.co.uk/itm/333")
reading(sid3, stock=False)
_c3, d3 = RUN.decide_one(CFG, WS, MKT, FBA_SKU, NOW)
check("no action", d3["action"], "none")
check("  named plainly", d3["blocked_by"], "this is an FBA listing")
truthy("  it does NOT go out of stock on a supplier's stock",
       "not ours to set" in d3["reason"])

print("  -- a SKU whose sources are all unreadable is left alone --")
R.enrol(CFG, WS, MKT, "BLIND_SKU")
snapshot([{"sku": SKU, "price": "20.00", "qty": 5, "handling": 5, "fulfillment": "MFN"},
          {"sku": FBA_SKU, "price": "25.00", "qty": 9, "fulfillment": "AFN"},
          {"sku": "BLIND_SKU", "price": "30.00", "qty": 5, "handling": 5,
           "fulfillment": "MFN"}])
sid4 = R.add_source(CFG, WS, MKT, "BLIND_SKU", "https://ebay.co.uk/itm/444")
reading(sid4, status=S.FAILED, price=None, ship=None, stock=None, disp=None)
_c4, d4 = RUN.decide_one(CFG, WS, MKT, "BLIND_SKU", NOW)
check("nothing happens", d4["action"], "none")
truthy("  because we learned nothing", "no usable data" in d4["blocked_by"])
check("  and the quantity is untouched", d4["quantity"], None)


print("\n=== the whole pass survives one broken SKU ===")
res = RUN.dry_run(CFG, WS, MKT, now=NOW)
check("every enrolled SKU considered", res["skus"], 4)
check("  and each got a row", len(res["decisions"]), 4)
check("  held ones are counted", res["counts"]["blocked"] >= 3, True)


print("\n=== the endpoints ===")
from flask import Flask
import routes.sourcing_routes as sr
app = Flask(__name__); app.secret_key = "t"
sr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS, "label": "Jack UK"},
            _state={"active_account_id": WS, "active_marketplace": MKT})
c = app.test_client()

j = c.get("/sourcing/list").get_json()
check("the screen gets its rows", len(j["rows"]), 4)
row = [r for r in j["rows"] if r["sku"] == SKU][0]
check("  with the decision", row["decision"]["action"], "update")
check("  and the suppliers behind it", len(row["sources"]), 1)
truthy("  each carrying its reading", row["sources"][0]["check"]["price"])
truthy("  and the rule in force", j["rule"]["strategy"])

print("  -- listing does NOT write to the log (it is a view, not a run) --")
before = len(R.recent_actions(CFG, WS, MKT, SKU))
c.get("/sourcing/list")
check("no new rows from looking", len(R.recent_actions(CFG, WS, MKT, SKU)), before)

print("  -- enrol / unenrol --")
check("enrolling needs a sku",
      c.post("/sourcing/enrol", json={}).status_code, 400)
c.post("/sourcing/enrol", json={"sku": "NEW_SKU"})
check("a new SKU is enrolled in DRY RUN, never live",
      [r for r in R.enrolled(CFG, WS, MKT) if r["sku"] == "NEW_SKU"][0]["mode"],
      "dry_run")
c.post("/sourcing/enrol", json={"sku": "NEW_SKU", "enrolled": False})
check("  and can be removed",
      any(r["sku"] == "NEW_SKU" for r in R.enrolled(CFG, WS, MKT)), False)

print("  -- adding a supplier --")
bad = c.post("/sourcing/source/add",
             json={"sku": SKU, "url": "https://www.ebay.co.uk/sch/i.html?_nkw=drill"})
check("a search page is refused, not stored", bad.status_code, 400)
truthy("  with a usable reason", "/itm/" in bad.get_json()["error"])
ok = c.post("/sourcing/source/add",
            json={"sku": SKU, "url": "https://www.ebay.co.uk/itm/987654321012"})
check("a real item link is accepted", ok.get_json()["ok"], True)
check("  and kind is inferred as ebay",
      [s for s in R.sources_for(CFG, WS, MKT, SKU) if s["id"] == ok.get_json()["id"]][0]["kind"],
      "ebay")
other = c.post("/sourcing/source/add",
               json={"sku": SKU, "url": "https://supplier.example.com/p/1"})
check("a non-eBay link is accepted as html",
      [s for s in R.sources_for(CFG, WS, MKT, SKU)
       if s["id"] == other.get_json()["id"]][0]["kind"], "html")

print("  -- rules --")
c.post("/sourcing/rules", json={"rule": {"strategy": "fastest", "max_change_pct": 12.0}})
r = R.rule_for(CFG, WS, MKT, "")
check("saved", (r["strategy"], r["max_change_pct"]), ("fastest", 12.0))
c.post("/sourcing/rules", json={"rule": {"nonsense_field": 1}})
check("an unknown setting is dropped, not stored",
      "nonsense_field" in R.rule_for(CFG, WS, MKT, ""), False)

print("  -- the log --")
lg = c.get("/sourcing/log?sku=" + SKU).get_json()
truthy("the audit trail is readable", len(lg["actions"]) > 0)
check("  and every row of it is unapplied",
      all(a["applied"] == 0 for a in lg["actions"]), True)


print("\n=== permissions: looking is open, changing needs publish ===")
from auth import guard
def needs(path, method="POST"):
    return guard.required_permission(path, method)
check("reading the dry run", needs("/sourcing/list", "GET"), None)
check("reading the log", needs("/sourcing/log", "GET"), None)
check("enrolling a SKU", needs("/sourcing/enrol"), "publish")
check("adding a supplier", needs("/sourcing/source/add"), "publish")
check("editing the rules", needs("/sourcing/rules"), "publish")
check("running it", needs("/sourcing/check"), "publish")
check("the screen rides on the listings area",
      guard.feature_for("/sourcing/list"), "listings")
check("  and so does the run", guard.feature_for("/sourcing/check"), "listings")

print("  -- a lister could not arm this even if the button were drawn --")
lister = {"role": "lister", "permissions": ["edit"], "active": True,
          "features": {"listings": "edit"}, "workspaces": ["*"]}
allowed, msg = guard.check("/sourcing/enrol", "POST", lister, {})
check("enrolling refused", allowed, False)
truthy("  and told why", msg)
check("but they may read the dry run",
      guard.check("/sourcing/list", "GET", lister, None)[0], True)
owner = {"role": "owner", "permissions": list(guard.users.PERMISSIONS),
         "active": True, "features": {"listings": "edit"}, "workspaces": ["*"]}
check("an owner may enrol", guard.check("/sourcing/enrol", "POST", owner, {})[0], True)

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
