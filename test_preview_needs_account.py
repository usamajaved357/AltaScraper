"""A queued Preview/Submit must name its account when it starts (owner, 29 Sep 2026).

read.txt: "Preview queue with no account: REFUSE. A preview job must have an
explicit account at the time it starts. Do not infer ownership later from
whichever account happens to be open."

/run/<mode> already refused with no account open. /preview/enqueue let the job
through with no --account-id, and the generator's credential fallback is the
global block. This drives the route with a stand-in queue (nothing is spawned,
nothing reaches Amazon) and pins: no account -> 400, nothing queued; an account
-> queued, stamped with that account and carrying --account-id.
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
from listing import preview_jobs as PJ
import routes.preview_job_routes as R

queued = []
_real_enqueue, _real_counts = PJ.enqueue, PJ.counts
PJ.enqueue = lambda sku, mode, args, **k: queued.append((sku, mode, args, k)) or "pj_test"
PJ.counts = lambda: {}

ACC = {"acc": None}
# THE GAP. With no account id at all the write check (mismatch_for_write)
# already refuses (409). What got through: the server HAS an id, but its
# record cannot be loaded (deleted, renamed, a failed read) -- the job was
# queued with no account and no --account-id.
STATE = {"active_account_id": "gone_account"}
app = Flask(__name__); app.secret_key = "t"
R.register(app, CONFIG_PATH="config.json", SCRIPT="gen.py", _cfg=lambda: {},
           _active_account=lambda: ACC["acc"], _state=STATE, _require_publish=lambda: None)
c = app.test_client()
try:
    print("=== no account at all: refused by the write check, as before ===")
    STATE["active_account_id"] = ""
    r = c.post("/preview/enqueue", json={"sku": "SKU1", "mode": "api"})
    check("409", r.status_code, 409)
    STATE["active_account_id"] = "gone_account"
    print("=== an account id whose record cannot be loaded ===")
    for acc in (None, {}, {"id": ""}, {"id": "  "}):
        ACC["acc"] = acc
        r = c.post("/preview/enqueue", json={"sku": "SKU1", "mode": "api"})
        check("refused (%r)" % (acc,), (r.status_code, (r.get_json() or {}).get("ok")), (400, False))
    check("  says what to do", "No account is open" in (r.get_json() or {}).get("error", ""), True)
    r = c.post("/preview/enqueue", json={"sku": "SKU1", "mode": "api_submit"})
    check("a submit too", r.status_code, 400)
    check("nothing was queued", queued, [])

    print("=== an account open ===")
    STATE["active_account_id"] = "jack_uk"
    ACC["acc"] = {"id": "jack_uk", "default_marketplace": "UK"}
    r = c.post("/preview/enqueue", json={"sku": "SKU1", "mode": "api"})
    check("queued", (r.status_code, (r.get_json() or {}).get("ok")), (200, True))
    check("  stamped with its account", queued[-1][3].get("account_id"), "jack_uk")
    args = queued[-1][2]
    check("  and the run is told which", args[args.index("--account-id") + 1], "jack_uk")
finally:
    PJ.enqueue, PJ.counts = _real_enqueue, _real_counts

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\na queued preview always names its account")
