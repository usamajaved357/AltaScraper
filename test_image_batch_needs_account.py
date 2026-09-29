"""An image batch pins its account when it BEGINS (owner decision, 29 Sep 2026).

read.txt: "Image batch with no account: REFUSE AT START. Capture and pin the
account when the batch begins. Never file images under whichever account is
open when processing finishes."

Before: a batch started with no account was stamped _acct_id="" and the worker
filled the gap when each image FINISHED -- from the open account (the folder)
and the open account's Drive (the copy). Now:
  - /genimage/start_batch refuses (400) before any job or thread exists;
  - the worker reads only the stamped account, never the open one.
The route is driven with stand-ins (no image is generated, no AI is called).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


from flask import Flask
import routes.genimage_routes as G

started, made = [], []
_n = lambda *a, **k: None
STATE = {"active_account_id": ""}
app = Flask(__name__); app.secret_key = "t"
G.register(app, CONFIG_PATH="config.json", _CREATIVE_STRATEGIES={}, _IMG_JOBS={},
           _IMG_JOBS_LOCK=None, _SECONDARY_ROLES={}, _active_brand=_n, _cfg=lambda: {},
           _imgresult=_n, _load_img_instructions=_n, _load_recipes=_n,
           _new_img_job=lambda n, **k: made.append(n) or "img_test",
           _records=_n, _run_img_jobs_bg=lambda jid, jobs, kind: started.append((jid, jobs, kind)),
           _safe_sku=lambda s: s, _save_img_instructions=_n, _sku_dir=_n, _state=STATE,
           _write_attrs_for_sku=_n, _ws=_n)
c = app.test_client()
BODY = {"kind": "main", "jobs": [{"sku": "S1", "payload": {}, "_acct_id": "sneaky"}]}

print("=== no account: refused at the start ===")
r = c.post("/genimage/start_batch", json=BODY)
check("400", (r.status_code, (r.get_json() or {}).get("ok")), (400, False))
check("  says what to do", "No account is open" in (r.get_json() or {}).get("error", ""), True)
check("  no job was made, no thread started", (made, started), ([], []))

print("=== an account named by the page ===")
import time
r = c.post("/genimage/start_batch?account=tab_account",
           json={"kind": "main", "jobs": [{"sku": "S1", "payload": {}, "_acct_id": "sneaky"}]})
check("started", (r.status_code, (r.get_json() or {}).get("ok")), (200, True))
for _ in range(50):
    if started:
        break
    time.sleep(0.02)
check("  every job pinned to that account (not the browser's value)",
      [j.get("_acct_id") for j in started[0][1]], ["tab_account"])

print("=== an account open on the server ===")
STATE["active_account_id"] = "open_account"
started.clear()
r = c.post("/genimage/start_batch", json={"kind": "main", "jobs": [{"sku": "S2", "payload": {}}]})
for _ in range(50):
    if started:
        break
    time.sleep(0.02)
check("pinned to it at the start", [j.get("_acct_id") for j in started[0][1]], ["open_account"])

print("=== the worker never looks at the open account ===")
IJ = open("domain/image_jobs.py", "rb").read().decode("utf-8")
w = IJ[IJ.index("def _run_img_jobs_bg_inner("):]
check("files by the stamped account only",
      '_aid = str(job.get("_acct_id", "") or "")' in w
      and '_acct_id", "") or _app._state' not in w, True)
check("no Drive copy without the stamped account's own Drive",
      "acc = acc or _app._active_account()" not in w and "if not _aid or not acc:" in w, True)

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nan image batch is pinned to its account from the start")
