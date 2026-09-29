# -*- coding: utf-8 -*-
"""ALTASCRAPER_BACKGROUND=off: a test or parallel copy starts no background work.

Roadmap, safe parallel server test (29 Sep 2026): a second copy of the app on a
copy of the data must not repeat production's timers -- above all sourcing_apply,
which pushes repricer prices -- nor its monitor loop, live refresher or nightly
Google backup. Pins that each of the four starters stops when the switch is off,
and that the default (unset) is unchanged.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from config import background as BG            # noqa: E402

print("== the switch ==")
check("unset: background work is on (nothing changes by default)", BG.enabled({}), True)
for v in ("off", "OFF", "0", "false", "no", " off "):
    check("  %r switches it off" % v, BG.enabled({BG.ENV: v}), False)
check("  any other value leaves it on", BG.enabled({BG.ENV: "on"}), True)

os.environ[BG.ENV] = "off"
try:
    print("== every starter honours it ==")
    from data import scheduler as S
    r = S.start()
    check("job timers (incl. repricer apply) do not start", (r.get("ok"), "=off" in r.get("error", "")), (False, True))
    check("  and no scheduler exists", bool(S._scheduler and S._scheduler.running), False)

    from domain import live_refresher as LR
    logs = []
    r = LR.start(None, lambda: {}, "unused.json", log=logs.append)
    check("live refresher does not start", (r.get("ok"), LR._STATE.get("running")), (False, False))
    check("  and says why", any("=off" in m for m in logs), True)

    from domain import backup as B
    said = []
    B.NIGHTLY.start(None, "unused.json", lambda: [], log=said.append)
    check("nightly backup does not arm", B.NIGHTLY.running, False)
    check("  and says why", any("=off" in m for m in said), True)

    from monitor import checker as M
    M.start_scheduler(lambda: {}, "unused.json")
    check("ASIN monitor loop does not start", M._SCHED_STARTED, False)

    print("== jobs can still be run on purpose, and say what happened ==")
    import threading
    from flask import Flask
    app = Flask("bg_test")
    import tempfile
    TMPCFG = os.path.join(tempfile.mkdtemp(prefix="altabg_"), "app.json")
    os.environ.pop("ALTASCRAPER_DB", None)
    before = {t.name for t in threading.enumerate()}
    r = S.register_jobs(app, config_path=TMPCFG, cfg=lambda: {})
    rules = {str(x) for x in app.url_map.iter_rules()}
    check("/jobs/status and /jobs/run still registered",
          ("/jobs/status" in rules, "/jobs/run/<job_type>" in rules), (True, True))
    check("the one-time supplier repair thread does not start",
          "supplier-repair" in {t.name for t in threading.enumerate()} - before, False)
    check("register_jobs reports the switch", (r.get("ok"), "=off" in r.get("error", "")), (False, True))
    jr = S.run_job("catalog_sync")
    check("running the catalogue job by hand says the refresher did not start",
          (jr.get("ok"), "=off" in (jr.get("error") or "")), (False, True))
    from routes import backup_routes as BR
    app2 = Flask("bg_test2")
    BR.register(app2, CONFIG_PATH=TMPCFG, _cfg=lambda: {}, _client=None, _state={})
    says = app2.test_client().get("/backup/status").get_json() or {}
    check("the backup status says why nothing runs", "=off" in str(says.get("says", "")), True)
finally:
    os.environ.pop(BG.ENV, None)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
