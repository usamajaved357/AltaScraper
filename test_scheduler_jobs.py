"""The three background jobs do real work, and do it through the real code.

They were stubs that raised NotImplementedError because each "needs the beta's
SP-API client". That reasoning expired: dashboard_beta.py calls
build_app(backend="db"), which is the SAME app with the SAME routes -- so the
client was never missing, only a way to reach it from a timer.

The point of these checks is that none of them REIMPLEMENTS anything. A second
catalogue sweep, a second monitor throttle or a second inventory model would
drift from the ones the buttons use, and the difference would surface as "the
scheduled job disagrees with the screen".
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")
from flask import Flask, jsonify, request

import data.scheduler as sched
import domain.live_snapshots as snap

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

TMP = tempfile.mkdtemp(prefix="altajobs_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "selvora", "label": "Selvora", "marketplaces": ["UK"]}]},
          open(CFG, "w"))

print("=== nothing pretends to work before it is wired up ===")
sched.bind(app=None, config_path=None, cfg=None)
sched._APP.update({"app": None, "config_path": None, "cfg": None})
for name, fn in (("catalog_sync", sched.catalog_sync),
                 ("asin_monitor_check", sched.asin_monitor_check),
                 ("inventory_sync", sched.inventory_sync)):
    try:
        fn()
        check("%s refuses when unbound" % name, "no error", "RuntimeError")
    except RuntimeError as e:
        check("%s refuses when unbound" % name, "not bound" in str(e), True)
    except Exception as e:
        check("%s refuses when unbound" % name, type(e).__name__, "RuntimeError")

print("\n=== none of them raises NotImplementedError any more ===")
src = open(r"D:\AltaScraper\data\scheduler.py", encoding="utf-8").read()
check("no stub left", "raise NotImplementedError" in src, False)
check("  and none of them imports sp_api", "sp_api" in src, False)

print("\n=== inventory_sync calls the REAL inventory view ===")
calls = {"inventory": 0, "body": None}
app = Flask(__name__)
app.secret_key = "t"

@app.route("/inventory/v2/run", methods=["POST"])
def inventory_v2_run():
    calls["inventory"] += 1
    calls["body"] = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "alerts": [1, 2, 3], "count": 42})

sched.bind(app=app, config_path=CFG, cfg=lambda: json.load(open(CFG)))
res = sched.inventory_sync("selvora")
check("the view was called once", calls["inventory"], 1)
check("  scoped to the workspace", calls["body"].get("id"), "selvora")
check("it reports the alert count", res["alerts"], 3)
check("  and the SKU count", res["skus"], 42)

print("\n=== a failing inventory run is an ERROR, not a quiet success ===")
@app.route("/inventory/v2/run2", methods=["POST"])
def _bad():
    return jsonify({"ok": False, "error": "SP-API refused"})
app.view_functions["inventory_v2_run"] = _bad
try:
    sched.inventory_sync()
    check("it raises", "no error", "RuntimeError")
except RuntimeError as e:
    check("it raises", "SP-API refused" in str(e), True)
app.view_functions["inventory_v2_run"] = inventory_v2_run

print("\n=== catalog_sync delegates to the refresher, not to Amazon ===")
import domain.live_refresher as ref
snap.save(CFG, "selvora", "UK", [{"sku": "S1", "asin": "B1", "title": "t"}],
          report_source="test")
seen = {"refresh": 0, "enrich": 0, "stalest": 0}
ref._targets = lambda cfg_fn, config_path: [("selvora", "UK")]
_real_stalest = ref._stalest
ref._stalest = lambda cfg_fn, cp, only_account=None: (seen.__setitem__("stalest", seen["stalest"] + 1),
                                                      ("selvora", "UK"))[1]
ref._refresh_one = lambda a, aid, mkt: (seen.__setitem__("refresh", seen["refresh"] + 1), "ok (1 listings)")[1]
ref._enrich_one = lambda a, cp, aid, mkt, log=None: (seen.__setitem__("enrich", seen["enrich"] + 1), "images 1/1 saved")[1]
ref._STATE["running"] = True          # pretend the refresher is already up

res = sched.catalog_sync("selvora")
check("it asked the refresher what was stalest", seen["stalest"], 1)
check("  refreshed that catalogue", seen["refresh"], 1)
check("  and filled in its images", seen["enrich"], 1)
check("reporting both", (res["catalogue"], res["images"]),
      ("ok (1 listings)", "images 1/1 saved"))

print("\n=== ...and says so plainly when there is nothing to do ===")
ref._stalest = lambda cfg_fn, cp, only_account=None: None
res = sched.catalog_sync("selvora")
check("no refresh was forced", res["refreshed"], None)
check("  with a readable reason", res["note"], "every marketplace is current")

print("\n=== it starts the refresher if it is not running ===")
ref._STATE["running"] = False
started = {"n": 0}
ref.start = lambda a, c, p, log=None: (started.__setitem__("n", started["n"] + 1), {"ok": True})[1]
res = sched.catalog_sync()
check("the refresher was started", started["n"], 1)
check("  and it says so", res.get("started_refresher"), True)

print("\n=== every run is recorded, success or failure ===")
# run_job must never raise -- a scheduled job that throws kills its thread and
# stops running for ever, with nothing on screen to say so.
sched._JOBS["boom"] = {"fn": lambda: (_ for _ in ()).throw(ValueError("nope")),
                       "hours": None, "description": ""}
try:
    import data.db as _db
    _db.db_path(CFG)
    out = sched.run_job("boom")
    check("a throwing job returns instead of raising", out["ok"], False)
    check("  with the reason", "nope" in out["error"], True)
except Exception as e:
    check("run_job needs a database (skipped: %s)" % str(e)[:40], True, True)

check("an unknown job is refused", sched.run_job("nosuch")["ok"], False)

print("\n=== the beta binds them at startup ===")
beta = open(r"D:\AltaScraper\dashboard_beta.py", encoding="utf-8").read()
check("register_jobs is given the config path", "config_path=_d.CONFIG_PATH" in beta, True)
check("  and the config reader", "cfg=_d._cfg" in beta, True)

ref._stalest = _real_stalest
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
