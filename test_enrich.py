"""Images and A+ arrive on their own, like the listings do.

The catalogue report gives titles, prices and statuses but NOT images, and A+
content lives behind a different API again. So opening a workspace meant watching
thumbnails trickle in, and pressing "pull live images" by hand. There was no
reason a person had to ask -- the same background job already keeps the catalogue
fresh.
"""
import os, sys, json, time, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")
from flask import Flask, jsonify, request

import domain.live_snapshots as snap
import domain.live_refresher as ref

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

TMP = tempfile.mkdtemp(prefix="altaenrich_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")

AID, MKT = "selvora", "UK"

def items(n):
    """FRESH dicts every time.

    save() keeps a shallow copy, so two snapshots built from one list would share
    their item dicts and enriching one would silently enrich the other. That is a
    test artifact -- the real callers each parse their own report -- but it made
    three assertions pass or fail for the wrong reason, which is worse than a
    failing test.
    """
    return [{"sku": "S%d" % i, "asin": "B%08d" % i, "title": "t%d" % i} for i in range(n)]

snap.save(CFG, AID, MKT, items(50), report_source="test")
snap.save(CFG, AID, "DE", items(5), report_source="test")

print("=== enrich() adds knowledge without re-dating the catalogue ===")
before = snap.get(CFG, AID, MKT)
ts0, count0 = before["ts"], before["count"]
time.sleep(0.01)
n = snap.enrich(CFG, AID, MKT, {"S0": {"img": "http://x/0.jpg", "status": "Active"}})
after = snap.get(CFG, AID, MKT)
check("one item changed", n, 1)
check("  the image is stored", after["items"][0]["img"], "http://x/0.jpg")
check("  and the status", after["items"][0]["status"], "Active")
check("the catalogue timestamp is UNTOUCHED", after["ts"], ts0)
check("  and the count", after["count"], count0)
check("  but the enrichment is dated", "enriched_ts" in after, True)
check("re-enriching with the same values changes nothing",
      snap.enrich(CFG, AID, MKT, {"S0": {"img": "http://x/0.jpg"}}), 0)
check("empty input is a no-op", snap.enrich(CFG, AID, MKT, {}), 0)
check("an unknown SKU is ignored",
      snap.enrich(CFG, AID, MKT, {"NOPE": {"img": "x"}}), 0)
check("a blank value never overwrites a real one",
      (snap.enrich(CFG, AID, MKT, {"S0": {"img": ""}}),
       snap.get(CFG, AID, MKT)["items"][0]["img"])[1], "http://x/0.jpg")

print("\n=== the biggest gap is closed first ===")
ref._targets = lambda cfg_fn, config_path: [(AID, MKT), (AID, "DE")]
check("UK has more missing than DE", ref._needs_images(lambda: {}, CFG, AID), (AID, MKT))
snap.enrich(CFG, AID, MKT, {("S%d" % i): {"img": "u%d" % i} for i in range(1, 50)})
check("once UK is done, DE is next", ref._needs_images(lambda: {}, CFG, AID), (AID, "DE"))
snap.enrich(CFG, AID, "DE", {("S%d" % i): {"img": "u%d" % i} for i in range(5)})
check("with nothing missing, there is nothing to do",
      ref._needs_images(lambda: {}, CFG, AID), None)

print("\n=== a pass calls the REAL views and writes what they return ===")
# Deliberately BIGGER than ENRICH_PER_PASS, so the budget actually bites. With a
# catalogue smaller than the budget the pass finishes everything and the "chips
# away over several passes" behaviour is never exercised at all.
CATALOGUE = ref.ENRICH_PER_PASS * 2 + 20
# A MARKETPLACE OF ITS OWN, because save() no longer forgets images.
#
# This line used to be `snap.save(..., MKT, ...)` with the comment "reset: no
# images", and it worked because a save REPLACED the stored items outright. That
# is precisely the bug the owner reported:
#
#     "i am not able to see the images of the items in the inventory section, i
#      was able to see it once but now even after clicking on refresh or
#      reloading the page i am not able to see the images"
#
# Amazon's catalogue report carries no images -- they are fetched afterwards, one
# SKU at a time, by the very refresher this file tests. So every Sync wiped every
# thumbnail the refresher had collected and they trickled back over the next
# hour, and pressing Refresh made it worse. save() now carries a known value
# forward when the incoming one is blank.
#
# So this block gets a clean marketplace rather than relying on a wipe. The
# carry-forward itself is asserted below.
MKT2 = "FR"
snap.save(CFG, AID, MKT2, items(CATALOGUE), report_source="test")
calls = {"images": 0, "aplus": 0, "skus": []}

app = Flask(__name__)
app.secret_key = "t"

@app.route("/live/images", methods=["POST"])
def live_images():
    b = request.get_json(force=True) or {}
    skus = b.get("skus") or []
    calls["images"] += 1
    calls["skus"] += skus
    return jsonify({"ok": True,
                    "images": {s: "http://img/%s.jpg" % s for s in skus},
                    "statuses": {s: "Active" for s in skus},
                    "meta": {s: {"fulfillment": "FBM", "handling": 3} for s in skus},
                    "failed": [], "pending": []})

@app.route("/live/aplus", methods=["POST"])
def live_aplus():
    calls["aplus"] += 1
    return jsonify({"ok": True, "by_asin": {"B00000001": {"modules": 2}}})

ref.ENRICH_PAUSE = 0            # no need to actually wait in a test
note = ref._enrich_one(app, CFG, AID, MKT2)
rec = snap.get(CFG, AID, MKT2)
withimg = [i for i in rec["items"] if i.get("img")]
check("it stopped at the per-pass budget", len(calls["skus"]), ref.ENRICH_PER_PASS)
check("  in batches", calls["images"], ref.ENRICH_PER_PASS // ref.ENRICH_BATCH)
check("that many images were saved", len(withimg), ref.ENRICH_PER_PASS)
check("  with their real status", withimg[0]["status"], "Active")
check("  and fulfillment", withimg[0]["fulfillment"], "FBM")
check("  and handling time", withimg[0]["handling"], 3)
check("A+ was warmed once", calls["aplus"], 1)
check("the note says what happened and what is left",
      ("images %d/%d saved" % (ref.ENRICH_PER_PASS, ref.ENRICH_PER_PASS) in note
       and "%d still to do" % (CATALOGUE - ref.ENRICH_PER_PASS) in note), True)

print("\n=== the next passes continue where the last stopped ===")
calls["skus"] = []
ref._enrich_one(app, CFG, AID, MKT2)
check("no SKU was fetched twice",
      len(set(calls["skus"]) & {i["sku"] for i in withimg}), 0)
check("two passes have done twice the budget",
      sum(1 for i in snap.get(CFG, AID, MKT2)["items"] if i.get("img")),
      ref.ENRICH_PER_PASS * 2)
ref._enrich_one(app, CFG, AID, MKT2)          # the remainder
check("the whole catalogue is covered",
      sum(1 for i in snap.get(CFG, AID, MKT2)["items"] if i.get("img")), CATALOGUE)
check("a complete marketplace reports so and calls nothing",
      ref._enrich_one(app, CFG, AID, MKT2), "images complete")

print("\n=== a person syncing always comes first ===")
snap.save(CFG, AID, MKT, items(50), report_source="test")
calls["images"] = 0; calls["aplus"] = 0
ref.user_sync_started("%s::%s" % (AID, MKT2))
ref._enrich_one(app, CFG, AID, MKT2)
check("no image calls while they sync", calls["images"], 0)
check("no A+ call either", calls["aplus"], 0)
check("and nothing is queued behind them",
      ref._needs_images(lambda: {}, CFG, AID), None)
ref.user_sync_finished("%s::%s" % (AID, MKT2))

print("\n=== a marketplace with no snapshot is skipped, not crashed on ===")
check("says so plainly", ref._enrich_one(app, CFG, "nosuch", "US"), "no snapshot")

print("\n=== A SYNC NO LONGER THROWS AWAY WHAT THIS FILE JUST COLLECTED ===")
# The bug, in the owner's words:
#
#     "i am not able to see the images of the items in the inventory section, i
#      was able to see it once but now even after clicking on refresh or
#      reloading the page i am not able to see the images"
#
# Amazon's catalogue report carries NO images. This refresher fetches them
# afterwards, sixty SKUs a pass. save() then replaced the stored items outright,
# so every Sync wiped the lot and they trickled back over the following hour --
# and pressing Refresh, the obvious response to a missing picture, destroyed
# exactly the work that would have fixed it.
#
# Measured on nestwell_goods before the fix: 39 of 45 items had an image, and 0
# immediately after a sync.
MKT3 = "IT"
snap.save(CFG, AID, MKT3, items(4), report_source="test")
snap.enrich(CFG, AID, MKT3, {"S0": {"img": "http://kept/0.jpg"},
                             "S1": {"img": "http://kept/1.jpg"}})
check("two images collected", sum(
    1 for i in snap.get(CFG, AID, MKT3)["items"] if i.get("img")), 2)

# A fresh report: same SKUs, updated titles, and NO images -- exactly what
# Amazon sends.
fresh = [{"sku": "S%d" % i, "asin": "B%08d" % i, "title": "NEW%d" % i}
         for i in range(4)]
rec = snap.save(CFG, AID, MKT3, fresh, report_source="test")
after = {i["sku"]: i for i in snap.get(CFG, AID, MKT3)["items"]}
check("the images SURVIVE the sync", sum(
    1 for i in after.values() if i.get("img")), 2)
check("  S0 keeps its picture", after["S0"]["img"], "http://kept/0.jpg")
check("  while its title is updated by the report", after["S0"]["title"], "NEW0")
check("  and one that never had a picture still has none",
      after["S2"].get("img", ""), "")
check("  the record says how many it carried", rec.get("carried_forward"), 2)

# A REPORT THAT DOES CARRY AN IMAGE STILL WINS. This only fills gaps -- it is not
# a freeze, and a listing whose picture genuinely changed must update.
snap.save(CFG, AID, MKT3,
          [{"sku": "S0", "asin": "B00000000", "title": "N", "img": "http://new/0.jpg"}],
          report_source="test")
check("a real value from the report overrules the stored one",
      snap.get(CFG, AID, MKT3)["items"][0]["img"], "http://new/0.jpg")

print("\n=== thumbnails ask the CDN for the size they will be drawn at ===")
# "please check all places in the app where thumbnail images are displayed and
#  check if we can lower the load time"
#
# Every product picture is a full-size Amazon CDN file scaled down by CSS to
# 34-88px. Amazon takes a size directive in the filename, so the app asks for
# one -- kilobytes instead of most of a megabyte, per picture, per row.
import io as _io
import re as _re
T = _io.open(r"D:\AltaScraper\static\js\thumbs.js", encoding="utf-8").read()
check("there is ONE helper, not one rule per file",
      len(_re.findall(r"function thumbUrl\(", T)), 1)
for f in ("stock.js", "orders.js", "sourcing.js", "sales.js", "listings.js",
          "miles_template.js"):
    src = _io.open(r"D:\AltaScraper\static\js\%s" % f, encoding="utf-8").read()
    check("  %s routes its thumbnails through it" % f,
          ("thumbUrl(" in src or "thumbImg(" in src), True)
check("it is loaded before anything that draws a picture",
      _io.open(r"D:\AltaScraper\templates\dashboard.html",
               encoding="utf-8").read().index("js/thumbs.js")
      < _io.open(r"D:\AltaScraper\templates\dashboard.html",
                 encoding="utf-8").read().index("js/listings.js"), True)

print("\n=== the views are reused, not reimplemented (Rule 12) ===")
src = open(r"D:\AltaScraper\domain\live_refresher.py", encoding="utf-8").read()
check("it calls the real /live/images view",
      'app.view_functions.get("live_images")' in src, True)
check("  and the real /live/aplus view",
      'app.view_functions.get("live_aplus")' in src, True)
check("  and never talks to SP-API itself", "sp_api" in src, False)
check("the refresher runs it after every catalogue refresh",
      "_enrich_one(app, config_path, target[0], target[1], log)" in src, True)
check("  and again while idle", "_needs_images(cfg_fn, config_path, account_id)" in src, True)

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)


