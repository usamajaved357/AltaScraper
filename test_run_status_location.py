# -*- coding: utf-8 -*-
"""The run heartbeat is written where the dashboard reads it (29 Sep 2026).

The generator wrote run_status.json beside the CODE (status_path() with no
app_dir); the dashboard reads it beside CONFIG_PATH (routes/listing_routes).
On the server those are /app and /data, so a running generation looked idle.
Pins: with CONFIG_PATH set, the writer's default IS the reader's folder; a
heartbeat written by start() is seen by classify(app_dir=<config folder>);
with nothing set, the old code-folder default is unchanged.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from listing import run_status as RS           # noqa: E402

tmp = tempfile.mkdtemp(prefix="runstatus_")
cfg = os.path.join(tmp, "config.json")
saved = os.environ.get("CONFIG_PATH")
os.environ["CONFIG_PATH"] = cfg
try:
    check("the writer's default is beside CONFIG_PATH", RS.status_path(), os.path.join(tmp, "run_status.json"))
    check("  the same folder the dashboard reads",
          RS.status_path(), RS.status_path(os.path.dirname(os.path.abspath(cfg))))
    RS.start(total=3, mode="test")
    got = RS.classify(app_dir=os.path.dirname(os.path.abspath(cfg)))
    check("a run the generator started is seen by the reader", got["state"], "RUNNING")
    RS.finish(exit_code=0, summary="done")
    check("  and so is its end", RS.classify(app_dir=tmp)["state"], "STOPPED")
    check("an explicit app_dir still wins", RS.status_path(HERE, account=""), os.path.join(HERE, "run_status.json"))

    print("== one heartbeat per account (account-scope review) ==")
    RS.start(total=5, mode="test", account="acct_a")
    check("a run for account A writes A's own file",
          os.path.exists(os.path.join(tmp, "run_status.acct_a.json")), True)
    check("  account A's bar sees A's run", RS.classify(app_dir=tmp, account="acct_a")["state"], "RUNNING")
    check("  account B's bar sees nothing of it", RS.classify(app_dir=tmp, account="acct_b")["state"], "IDLE")
    RS.beat(idx=2, sku="SKU-A", force=True)
    check("  later beats go to A's file too", RS.read(tmp, account="acct_a").get("sku"), "SKU-A")
    check("an account name cannot climb out of the folder",
          os.path.dirname(RS.status_path(tmp, account="../x")) == tmp, True)
    LR = open(os.path.join(HERE, "routes", "listing_routes.py"), encoding="utf-8").read()
    check("/run/health reads the asking account's heartbeat",
          "run_status.classify(app_dir=_app_dir, proc_alive=alive, account=_acct)" in LR, True)
    check("  and trusts the process handle only if it is that run's",
          "proc.pid == _hb_pid" in LR, True)
    stack = LR.split("def run_stack(")[1].split("\n    @app.route")[0]
    # Re-pinned (security review, 29 Sep 2026): the account must be NAMED, and
    # only a process the app started AND whose pid is that heartbeat's is dumped.
    check("/run/stack needs a NAMED account (never the open one)",
          "_acct = _rqa.named_now()" in stack and "account=_acct" in stack, True)
    check("  and inspects only a process it can prove is that run",
          "proc.pid == pid and proc.poll() is None" in stack, True)
    RQS = open(os.path.join(HERE, "static", "js", "reqscope.js"), encoding="utf-8").read()
    check("  the browser names the account on /run/stack", '"/run/stack"' in RQS, True)
    sys.path.insert(0, HERE)
    from auth import guard as _G
    check("  and it needs edit (it starts a py-spy process)", _G.required_permission("/run/stack", "GET"), "edit")
    # THE REAL GATE, not just the table (security re-check, 29 Sep 2026): while
    # /run/stack was a listed read, check() waved it through before RULES.
    viewer = {"id": "u_v", "role": "viewer", "active": True, "permissions": [],
              "features": {"generate": "view"}, "workspaces": ["*"], "perms_version": 99}
    editor = dict(viewer, permissions=["edit"], features={"generate": "edit"})
    ok_v, _w = _G.check("/run/stack", "GET", viewer, None, {"account": "acct_a"})
    ok_e, _w = _G.check("/run/stack", "GET", editor, None, {"account": "acct_a"})
    check("  a view-only user is REFUSED by guard.check itself", ok_v, False)
    check("  an editor is allowed", ok_e, True)
    check("  and a link from another site is refused",
          bool(_G.cross_site_refusal("GET", "app.example", "https://evil.example", "", "cross-site", "/run/stack")), True)
    GEN = open(os.path.join(HERE, "amazon_listing_generator.py"), encoding="utf-8").read()
    check("the generator names its account when the run starts",
          'run_status.start(total=total, mode=mode, account=str(config.get("_account_id") or ""))' in GEN, True)
    RS.start(total=1, mode="test", account="")
    del os.environ["CONFIG_PATH"]
    check("nothing set -> the code folder, as before",
          RS.status_path(), os.path.join(HERE, "run_status.json"))
finally:
    if saved is not None:
        os.environ["CONFIG_PATH"] = saved
    else:
        os.environ.pop("CONFIG_PATH", None)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
