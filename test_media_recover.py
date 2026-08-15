"""Can the app tell "filed under another workspace" apart from "gone"?

The complaint was "I generated listing images before the new deployment, now the
image library is empty on the server." Those two causes need opposite responses,
so the thing being tested is that the app distinguishes them and recovers the
recoverable one WITHOUT ever losing a file.

Drives the real module and the real routes against a temporary media folder.
"""
import os, sys, json, tempfile, shutil

sys.path.insert(0, r"D:\AltaScraper")

from flask import Flask
import domain.media_recover as mr

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altamedia_")
MEDIA = os.path.join(TMP, "media")


def put(rel, body=b"\x89PNG-not-really"):
    p = os.path.join(MEDIA, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(body)
    return p


# Three images for jack_uk where they belong; two filed under an account that no
# longer exists; one dropped in the shared root, which no workspace ever lists.
put("_acct/jack_uk/SKU-A/one.jpg")
put("_acct/jack_uk/SKU-A/aplus/basic/two.png")
put("_acct/jack_uk/SKU-B/three.jpg")
put("_acct/ghost_acct/SKU-A/lost1.jpg")
put("_acct/ghost_acct/SKU-C/lost2.jpg")
put("SKU-A/stray.jpg")
put("_acct/jack_uk/SKU-A/notes.txt", b"not an image")

print("\n== the survey sees every image, wherever it is ==")
s = mr.survey(MEDIA, known_account_ids=["jack_uk"])
check("every image is found, in all three locations", s["total_images"], 6)
check("the .txt is not counted as an image",
      sum(f["images"] for l in s["locations"] for f in l["skus"]), 6)
check("three distinct locations", len(s["locations"]), 3)

by = {l["account_id"]: l for l in s["locations"]}
check("jack_uk's own images", by["jack_uk"]["images"], 3)
check("jack_uk is not orphaned", by["jack_uk"]["orphaned"], False)
check("the shared root is flagged orphaned", by[""]["orphaned"], True)
check("an account that no longer exists is flagged orphaned",
      by["ghost_acct"]["orphaned"], True)
check("orphan total is what no workspace can show", s["orphaned_images"], 3)
check_true("subfolders (aplus/basic) are counted",
           by["jack_uk"]["images"] == 3)

print("\n== a dry run reports and touches nothing ==")
d = mr.relocate(MEDIA, "ghost_acct", "jack_uk", dry_run=True)
check("dry run lists the files it would move", d["moved"], 2)
check("dry run says it is a dry run", d["dry_run"], True)
check("nothing actually moved", mr.survey(MEDIA)["total_images"], 6)
check_true("the ghost folder still holds its files",
           os.path.exists(os.path.join(MEDIA, "_acct", "ghost_acct", "SKU-A", "lost1.jpg")))

print("\n== the real move puts them where the library looks ==")
r = mr.relocate(MEDIA, "ghost_acct", "jack_uk", dry_run=False)
check("both files moved", r["moved"], 2)
after = mr.survey(MEDIA, known_account_ids=["jack_uk"])
check("NO IMAGE WAS LOST", after["total_images"], 6)
check("jack_uk now shows them", {l["account_id"]: l for l in after["locations"]}["jack_uk"]["images"], 5)
check("the ghost location is gone from the survey",
      "ghost_acct" in [l["account_id"] for l in after["locations"]], False)
check_true("the file is really at the destination",
           os.path.exists(os.path.join(MEDIA, "_acct", "jack_uk", "SKU-C", "lost2.jpg")))

print("\n== a name clash keeps BOTH files, never overwrites ==")
put("_acct/other/SKU-A/one.jpg", b"DIFFERENT-CONTENT")
r2 = mr.relocate(MEDIA, "other", "jack_uk", dry_run=False)
check("the clashing file was renamed, not dropped", r2["renamed"], 1)
check("still nothing lost", mr.survey(MEDIA)["total_images"], 7)
orig = os.path.join(MEDIA, "_acct", "jack_uk", "SKU-A", "one.jpg")
check("the original was not overwritten", open(orig, "rb").read(), b"\x89PNG-not-really")
kept = [f for f in os.listdir(os.path.join(MEDIA, "_acct", "jack_uk", "SKU-A"))
        if f.startswith("one") and "recovered" in f]
check("the incoming file was kept under a new name", len(kept), 1)

print("\n== moving somewhere pointless is refused ==")
try:
    mr.relocate(MEDIA, "jack_uk", "jack_uk", dry_run=True)
    check("same source and destination is refused", "no error", "ValueError")
except ValueError:
    check("same source and destination is refused", "ValueError", "ValueError")
bad = mr.relocate(MEDIA, "nope_not_here", "jack_uk", dry_run=True)
check("a missing source location is reported, not crashed", bad["ok"], False)

print("\n== the disk verdict is evidence, not a guess ==")
DATA = os.path.join(TMP, "data")
os.makedirs(DATA, exist_ok=True)

# An unmounted path on a PaaS box is THE failure that loses images silently.
# os.path.ismount is what tells the truth; force the answer the kernel would
# give for a plain container directory.
# This is the case that only ever fires on the Linux server, which is exactly
# why it must be exercised here -- a check that can only be tested in production
# is a check nobody tests. os.name and ismount are both read at call time, so
# standing in for the kernel drives the REAL code path rather than a copy of it.
real_ismount, real_name = os.path.ismount, os.name
try:
    os.name = "posix"
    os.path.ismount = lambda p: os.path.dirname(p) == p   # nothing but the root
    mr._RECORDED.clear()
    ev = mr.disk_evidence(DATA, on_paas=True)
    check("an unmounted folder on a PaaS box reads EPHEMERAL", ev["verdict"], "EPHEMERAL")
    check_true("and says so in plain words", "WIPES" in ev["detail"])
    check_true("and names the folder that is at risk", DATA in ev["detail"])
    check("on_volume is a definite no, not a shrug", ev["on_volume"], False)

    os.path.ismount = lambda p: p == DATA or os.path.dirname(p) == p
    mr._RECORDED.clear()
    ev2 = mr.disk_evidence(DATA, on_paas=True)
    check("a mounted volume reads PERSISTENT", ev2["verdict"], "PERSISTENT")
    check("and reports which mount it found", ev2["mount_point"], DATA)

    # A volume mounted at /data with CONFIG_PATH=/data/sub/config.json is still
    # persistent -- the mount is a PARENT of the data dir, not the data dir.
    sub = os.path.join(DATA, "sub")
    os.makedirs(sub, exist_ok=True)
    mr._RECORDED.clear()
    ev3 = mr.disk_evidence(sub, on_paas=True)
    check("a folder INSIDE a mounted volume is persistent too", ev3["verdict"], "PERSISTENT")

    # Not on a PaaS at all: no volume to expect, so no alarm.
    mr._RECORDED.clear()
    os.path.ismount = lambda p: os.path.dirname(p) == p
    ev4 = mr.disk_evidence(DATA, on_paas=False)
    check("a local machine is never accused of being ephemeral",
          ev4["verdict"] in ("UNKNOWN", "PERSISTENT"), True)
finally:
    os.path.ismount, os.name = real_ismount, real_name
    mr._RECORDED.clear()

print("\n== the marker accumulates proof across deploys ==")
DATA2 = os.path.join(TMP, "data2")
os.makedirs(DATA2, exist_ok=True)
h1 = mr.record_boot(DATA2, build_id="aaaaaaaa")
check("first boot recorded", h1["boots"], 1)
check_true("the marker is writable", h1["writable"])
# Opening /diag five times is not five boots. Without this guard the number
# would measure how often the diagnostics page was viewed.
for _ in range(5):
    mr.disk_evidence(DATA2, on_paas=True)
check("re-reading does NOT inflate the count", mr.record_boot(DATA2)["boots"], 1)
mr.record_boot(DATA2, build_id="aaaaaaaa", force=True)   # a restart, same build
h3 = mr.record_boot(DATA2, build_id="bbbbbbbb", force=True)   # a NEW deploy
check("every real boot is counted", h3["boots"], 3)
check("only distinct builds are remembered", len(h3["builds"]), 2)
DATA = DATA2
ev3 = mr.disk_evidence(DATA, on_paas=True)
check("surviving a second build is treated as proof", ev3["survived_deploy"], True)
check("...and that proof outranks the mount reading", ev3["verdict"], "PERSISTENT")

print("\n== deploy_check reports it on /diag and at boot ==")
import domain.deploy_check as dc
CFG = os.path.join(DATA, "config.json")
open(CFG, "w").write("{}")
res = dc.check(CFG)
row = [c for c in res["checks"] if c["name"] == "State survives a deploy"]
check("the deployment check still has the row", len(row), 1)
check_true("and it now carries the evidence, not the path shape",
           "boots" in row[0]["detail"] or "mount" in row[0]["detail"]
           or "survived" in row[0]["detail"] or "container filesystem" in row[0]["detail"])
check_true("the fix names media/ as being at risk too",
           "generated image" in (row[0]["why"] or ""))

print("\n== the routes answer ==")
app = Flask(__name__)
import routes.media_recover_routes as rr


def _root():
    return MEDIA


rr.register(app, _media_root=_root, _cfg=lambda: {}, CONFIG_PATH=CFG)
c = app.test_client()
j = c.get("/media/recover/survey").get_json()
check("survey route answers", j["ok"], True)
check("survey route counts the same images", j["total_images"], 7)
check_true("survey route carries the disk verdict", bool(j["disk"]["verdict"]))

put("_acct/late_acct/SKU-Z/z.jpg")
j2 = c.post("/media/recover/move", json={"from": "late_acct", "to": "jack_uk"}).get_json()
check("move route defaults to a dry run", j2["dry_run"], True)
check("...so the file is still where it was", mr.survey(MEDIA)["total_images"], 8)
j3 = c.post("/media/recover/move",
            json={"from": "late_acct", "to": "jack_uk", "dry_run": False}).get_json()
check("an explicit dry_run=false moves it", j3["moved"], 1)
check("and still loses nothing", mr.survey(MEDIA)["total_images"], 8)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
if fails:
    for f in fails:
        print("  FAILED:", f)
sys.exit(1 if fails else 0)
