"""Your work is yours: nobody else's jobs on your screen, nobody stopping yours.

The bug: the job registries recorded WHAT a job was doing but never WHO started
it, so /genimage/jobs_active returned every running job on the server. The
floating status bar polls it every two seconds on every page, so the owner
watched their VA's image generation. Stop All stopped everyone's work.
"""
import os, sys, tempfile, shutil, threading
sys.path.insert(0, r"D:\AltaScraper")
from flask import Flask, jsonify, session
from domain import job_owner as jo
from auth import users

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-60s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

TMP = tempfile.mkdtemp(prefix="altajobs_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")

# A real VA and a real manager, made through the real user store.
va, _ = users.create_user(CFG, email="va@example.com", name="Aisha", role="lister",
                          permissions=["edit"], workspaces=["*"])
boss, _ = users.create_user(CFG, email="boss@example.com", name="Talha", role="owner",
                            permissions=["edit", "manage_users"], workspaces=["*"])
VA_ID, BOSS_ID = va["id"], boss["id"]

JOBS = {}
LOCK = threading.Lock()

app = Flask(__name__)
app.secret_key = "test-only"

@app.route("/signin/<uid>")
def signin(uid):
    session["uid"] = uid
    return jsonify({"ok": True})

@app.route("/start/<label>")
def start(label):
    with LOCK:
        jid = "job_" + label
        JOBS[jid] = jo.stamp({"status": "running", "label": label, "total": 3, "done": 1})
    return jsonify({"ok": True, "job": jid})

@app.route("/active")                       # mirrors /genimage/jobs_active
def active():
    with LOCK:
        return jsonify({"jobs": [{"job": k, "label": j["label"], "mine": jo.mine_only(j)}
                                 for k, j in JOBS.items()
                                 if j["status"] == "running" and jo.may_see(j, CFG)]})

@app.route("/stopall")                      # mirrors /genimage/stop_all
def stopall():
    n = 0
    with LOCK:
        for j in JOBS.values():
            if j["status"] == "running" and jo.mine_only(j):
                j["status"] = "error"; n += 1
    return jsonify({"stopped": n})

def labels(client):
    return sorted(x["label"] for x in client.get("/active").get_json()["jobs"])

vac = app.test_client(); vac.get("/signin/" + VA_ID)
bossc = app.test_client(); bossc.get("/signin/" + BOSS_ID)

print("=== a job records who started it ===")
vac.get("/start/va_images")
check("the VA's job carries their id", JOBS["job_va_images"]["owner"], VA_ID)
bossc.get("/start/boss_images")
check("the owner's job carries theirs", JOBS["job_boss_images"]["owner"], BOSS_ID)
check("  and they are different", VA_ID != BOSS_ID, True)

print("=== ...and each person sees only their own ===")
check("the VA sees just their own", labels(vac), ["va_images"])

print("\n=== except a manager, deliberately ===")
check("someone who manages users sees everything",
      labels(bossc), ["boss_images", "va_images"])
check("  but knows which is theirs",
      sorted((x["label"], x["mine"]) for x in bossc.get("/active").get_json()["jobs"]),
      [("boss_images", True), ("va_images", False)])

print("\n=== Stop All stops all of MINE, not all of EVERYONE'S ===")
check("the VA stops one job", vac.get("/stopall").get_json()["stopped"], 1)
check("  their own is stopped", JOBS["job_va_images"]["status"], "error")
check("  the owner's is untouched", JOBS["job_boss_images"]["status"], "running")
check("a manager's Stop All spares the other person's too",
      bossc.get("/stopall").get_json()["stopped"], 1)

print("\n=== an unowned job stays visible to everyone ===")
# Work started before owners were recorded, or by a background thread. Hiding
# in-flight work would be worse than sharing it.
with LOCK:
    JOBS["job_legacy"] = {"status": "running", "label": "legacy", "total": 1, "done": 0}
check("the VA can see it", "legacy" in labels(vac), True)
check("the owner can see it", "legacy" in labels(bossc), True)
check("and either may stop it", jo.mine_only(JOBS["job_legacy"]), True)

print("\n=== outside a request there is nobody to attribute work to ===")
# Background threads see everything, on purpose. There is no screen to leak to
# and no user to be, and a sweeper or a status logger has to be able to walk the
# whole registry. The same branch covers the shared-password owner, who is by
# definition the only user -- once a real owner account exists the shared
# password stops working, so this cannot become "a signed-in person with no id".
check("current() is empty", jo.current(), "")
check("an unowned job is visible", jo.may_see({"owner": ""}, CFG), True)
check("and so is someone else's, to background code",
      jo.may_see({"owner": "u_someone"}, CFG), True)
check("but background code may not STOP someone else's",
      jo.mine_only({"owner": "u_someone"}), False)

print("\n=== the shared-password owner is the only user, so sees everything ===")
boot = app.test_client()
with boot.session_transaction() as s:
    s["authed"] = True                      # no uid
check("bootstrap sees the other jobs",
      "legacy" in labels(boot), True)

print("\n=== the permission table closes the two open endpoints ===")
from auth.guard import required_permission
check("/genimage/jobs_active needs edit",
      required_permission("/genimage/jobs_active", "GET"), "edit")
check("/preview/jobs needs edit", required_permission("/preview/jobs", "GET"), "edit")
check("  and /genimage/start still needs edit",
      required_permission("/genimage/start_batch", "POST"), "edit")

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
