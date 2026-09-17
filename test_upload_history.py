# -*- coding: utf-8 -*-
"""Upload history: every uploaded file that changed data is kept, with what it did.

    "i want to track which files were uploaded recently for creating listings
     like amazon has it it stores file which were used to create or make any
     changes in the listings using the files or templates"
    "all 7, keep forever, new sidebar item"

On a throwaway data directory:
  * domain/upload_log keeps the ORIGINAL bytes and one row per upload, lists an
    account's uploads, never serves one to another account, refuses a stored
    path outside the data directory, and writes the processing report;
  * the page's routes list, detail, download the file and the report, and 404 an
    upload that belongs to another account;
  * three uploads run for real through their routes and land in the history:
    the product template, the product cost sheet and the tracking sheet;
  * the other four hooks are in place, a preview (dry run) is not recorded, and
    the page is wired into the sidebar, the section list and the permissions.
"""
import csv
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


TMP = tempfile.mkdtemp(prefix="altauploads_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "nestwell_goods", "default_marketplace": "UK"},
                        {"id": "jack_uk", "default_marketplace": "UK"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "d.db")

from domain import upload_log as UL            # noqa: E402

print("== domain/upload_log ==")
data = b"sku,cost\nA1,2.50\nB2,abc\n"
uid = UL.record(CFG, "nestwell_goods", "uk", "cost_sheet", "../../costs.csv", data,
                ok=1, errors=1, summary="1 cost set.",
                rows=[{"row": 2, "sku": "A1", "status": "set"},
                      {"row": 3, "sku": "B2", "status": "not a number", "detail": "abc"}],
                skus=["A1"], uploaded_by="va@example.com")
check("recorded", isinstance(uid, int), True)
rec = UL.get(CFG, uid, "nestwell_goods")
path = UL.file_path(CFG, rec)
check("the original bytes are kept", open(path, "rb").read(), data)
check("  inside <data dir>/uploads/<account>/",
      os.path.relpath(path, os.path.realpath(TMP)).replace("\\", "/")
      .startswith("uploads/nestwell_goods/"), True)
check("  the file name cannot climb out", os.path.basename(path), "%d_costs.csv" % uid)
check("status says errors happened", rec["status"], UL.DONE_WITH_ERRORS)
check("marketplace stored upper-case", rec["marketplace"], "UK")
check("who uploaded it", rec["uploaded_by"], "va@example.com")
check("another account cannot read it", UL.get(CFG, uid, "jack_uk"), None)
lst = UL.recent(CFG, "nestwell_goods")
check("listed for its account", [u["id"] for u in lst], [uid])
check("  with its label and SKU count", (lst[0]["kind_label"], lst[0]["sku_count"], lst[0]["has_file"]),
      ("Product cost sheet", 1, True))
check("  and nothing for another account", UL.recent(CFG, "jack_uk"), [])
check("filter by kind", UL.recent(CFG, "nestwell_goods", kind="tracking"), [])

rep = UL.report_csv(rec).decode("utf-8-sig")
lines = list(csv.reader(io.StringIO(rep)))
check("report header names the upload", lines[1][:2], [str(uid), "costs.csv"])
check("report has the row columns in first-seen order", lines[3], ["row", "sku", "status", "detail"])
check("  and one line per reported row", [l[1] for l in lines[4:6]], ["A1", "B2"])

check("a refused whole file is FAILED",
      UL.get(CFG, UL.record(CFG, "nestwell_goods", "UK", "tracking", "t.csv", b"x",
                            error="no columns"), "nestwell_goods")["status"], UL.FAILED)
check("data URL decoded", UL.decode_data_url("data:text/csv;base64,YSxi"), b"a,b")
check("garbage decodes to nothing, not an error", UL.decode_data_url(None), b"")
check("a stored path outside the data directory is refused",
      UL.file_path(CFG, {"stored_path": "../../etc/passwd"}), "")
empty = UL.record(CFG, "nestwell_goods", "UK", "min_prices", "old tab", b"", ok=1)
check("an upload whose file was not sent offers no download",
      [u["has_file"] for u in UL.recent(CFG, "nestwell_goods") if u["id"] == empty], [False])

print("\n== the page's routes ==")
from flask import Flask                          # noqa: E402
from routes import upload_log_routes as ULR      # noqa: E402
from routes import input_upload_routes as IUR    # noqa: E402
from routes import cogs_routes as CR             # noqa: E402
from routes import tracking_routes as TR         # noqa: E402

state = {"active_account_id": "nestwell_goods", "active_marketplace": "UK"}
app = Flask(__name__)
ULR.register(app, CONFIG_PATH=CFG, _state=state)
IUR.register(app, CONFIG_PATH=CFG, _state=state)
_acc = lambda: {"id": "nestwell_goods", "default_marketplace": "UK"}
CR.register(app, _state=state, _COGS_OVERRIDE={}, _save_cogs_overrides=lambda *a, **k: None,
            _estimate_profit=lambda *a, **k: None, CONFIG_PATH=CFG, _active_account=_acc)
TR.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)), _state=state,
            _active_account=_acc)
cli = app.test_client()

j = cli.get("/uploads/list?account=nestwell_goods").get_json()
check("list", (j["ok"], len(j["uploads"]) >= 1, "cost_sheet" in j["kinds"]), (True, True, True))
check("detail carries the rows",
      len(cli.get("/uploads/detail/%d?account=nestwell_goods" % uid).get_json()["upload"]["report"]), 2)
r = cli.get("/uploads/file/%d?account=nestwell_goods" % uid)
check("file download is the original", (r.status_code, r.data), (200, data))
check("  named as uploaded", "costs.csv" in r.headers.get("Content-Disposition", ""), True)
r = cli.get("/uploads/report/%d?account=nestwell_goods" % uid)
check("report download", (r.status_code, r.mimetype), (200, "text/csv"))
check("another account's upload is 404 (file)",
      cli.get("/uploads/file/%d?account=jack_uk" % uid).status_code, 404)
check("  (detail)", cli.get("/uploads/detail/%d?account=jack_uk" % uid).status_code, 404)
check("  (report)", cli.get("/uploads/report/%d?account=jack_uk" % uid).status_code, 404)

print("\n== real uploads land in the history ==")
tpl = ("ebay_url,supplier_2,item_name,source_cost\n"
       "https://www.ebay.co.uk/itm/407153403493,https://www.ebay.co.uk/itm/318548785995,Sleeping pad,12.50\n"
       ",,,\n"
       "https://www.ebay.co.uk/itm/357421503276,,Litter picker,\n").encode("utf-8")
r = cli.post("/input/upload", data={"file": (io.BytesIO(tpl), "product-queue-template.csv")},
             content_type="multipart/form-data")
jj = r.get_json()
up = UL.recent(CFG, "nestwell_goods", kind="product_template")
check("template upload still works", (jj["ok"], jj["added"]), (True, 2))
check("  and is recorded", len(up), 1)
full = UL.get(CFG, up[0]["id"], "nestwell_goods")
check("  with the original file", open(UL.file_path(CFG, full), "rb").read(), tpl)
# Numbered the way the upload's own "Row N" errors are: the file reader drops
# blank lines before numbering, so the third product line is row 3.
check("  a report row per product row (the blank line is not one)",
      [(r["row"], r["status"]) for r in full["report"]], [(2, "added"), (3, "added")])
check("  the new SKUs", full["skus"], sorted(r["sku"] for r in full["report"]))
check("  which are the SKUs the upload created",
      sorted(full["skus"]), sorted(p["sku"] for p in jj["preview"]))
check("  counts match the upload's answer", (full["rows_ok"], full["rows_skipped"]), (jj["added"], jj["skipped"]))

bad = cli.post("/input/upload", data={"file": (io.BytesIO(b"colour,size\nred,big\n"), "wrong.csv")},
               content_type="multipart/form-data")
check("a file with no recognised columns is refused", bad.status_code, 400)
check("  and recorded as FAILED",
      [u["status"] for u in UL.recent(CFG, "nestwell_goods", kind="product_template")][0], UL.FAILED)

cost = b"sku,cost\nSKU-1,3.20\nSKU-2,\n"
before = len(UL.recent(CFG, "nestwell_goods", kind="cost_sheet"))
cli.post("/cogs/upload_sheet", data={"file": (io.BytesIO(cost), "costs.csv"), "dry_run": "1"},
         content_type="multipart/form-data")
check("a cost sheet PREVIEW is not recorded",
      len(UL.recent(CFG, "nestwell_goods", kind="cost_sheet")), before)
r = cli.post("/cogs/upload_sheet", data={"file": (io.BytesIO(cost), "costs.csv")},
             content_type="multipart/form-data")
got = UL.recent(CFG, "nestwell_goods", kind="cost_sheet")
check("the cost sheet itself is", (r.status_code, len(got)), (200, before + 1))
check("  with its counts", (got[0]["rows_ok"], got[0]["rows_skipped"], got[0]["skus"]), (1, 1, ["SKU-1"]))

trk = b"order_id,tracking\n204-1234567-1234567,1Z999AA10123456784\n"
r = cli.post("/tracking/upload?account=nestwell_goods&marketplace=UK",
             data={"file": (io.BytesIO(trk), "tracking.csv"), "id": "nestwell_goods",
                   "marketplace": "UK"}, content_type="multipart/form-data")
got = UL.recent(CFG, "nestwell_goods", kind="tracking")
check("the tracking sheet is recorded (status %d)" % r.status_code,
      any(u["filename"] == "tracking.csv" for u in got), True)

print("\n== the other hooks, and the page's wiring ==")
SR = read("routes", "sourcing_routes.py")
check("supplier links upload records", '"supplier_links"' in SR, True)
check("min prices upload records", '"min_prices"' in SR, True)
check("order costs upload records", '"order_costs"' in read("routes", "cogs_mode_routes.py"), True)
check("miles upload records", '"miles_items"' in read("routes", "miles_routes.py"), True)
check("the min-price screen sends the file", "file: _file" in read("static", "js", "sourcing.js"), True)
check("the Miles screen sends the file", "uphFileForUpload(MILES_FILE)" in read("static", "js", "miles.js"), True)
T = read("templates", "dashboard.html")
check("a sidebar item", 'data-sec="uploads"' in T, True)
check("a panel to draw into", 'id="sec_uploads"' in T, True)
check("the script is loaded", "/static/js/uploadhistory.js" in T, True)
check("  after listings.js, whose file reader it uses",
      T.find("/static/js/listings.js") < T.find("/static/js/uploadhistory.js"), True)
check("the section has an address", '"uploads"' in read("static", "js", "shell.js"), True)
check("the section opens the page", "uploadsOnOpen()" in read("static", "js", "shell.js"), True)
check("the nav item hides with its permission", 'uploads:"generate"' in read("static", "js", "users.js"), True)
from auth import guard as G                       # noqa: E402
check("the routes are governed as generate", G.feature_for("/uploads/list"), "generate")
check("dashboard registers the routes", "upload_log_routes.register" in read("dashboard.py"), True)

print("\n== the page draws, in node ==")
import shutil                                     # noqa: E402
import subprocess                                 # noqa: E402
node = shutil.which("node")
if not node:
    check("node available", False, True)
else:
    js = read("static", "js", "uploadhistory.js") + r"""
;(function(){
  // The type filter is already filled (two options), so the stand-in page needs
  // no createElement.
  const els = {uph_body: {innerHTML: ""}, uph_kind: {options: [1, 2], value: ""}};
  global.document = {getElementById: id => els[id] || null};
  global.esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");
  global.acctUrl = u => u + (u.indexOf("?") >= 0 ? "&" : "?") + "account=nestwell_goods";
  UPH.kinds = {cost_sheet: "Product cost sheet"};
  UPH.uploads = [{id: 7, uploaded_at: "2026-09-17 10:00:00", kind: "cost_sheet",
    kind_label: "Product cost sheet", filename: "costs<1>.csv", bytes: 2048, marketplace: "UK",
    status: "done_with_errors", rows_ok: 3, rows_skipped: 1, rows_error: 2, sku_count: 3,
    skus: ["A","B","C"], uploaded_by: "", has_file: true, summary: "3 costs set."}];
  UPH.open = 7; UPH.detail = {7: {report: [{row: 2, sku: "A", status: "set"}]}};
  uploadsRender();
  const h = els.uph_body.innerHTML;
  console.log(JSON.stringify({
    result: uphResultText(UPH.uploads[0]),
    nothing: uphResultText({status: "failed"}),
    fileLink: h.indexOf("/uploads/file/7?account=nestwell_goods") >= 0,
    reportLink: h.indexOf("/uploads/report/7?account=nestwell_goods") >= 0,
    escaped: h.indexOf("costs&lt;1>.csv") >= 0,
    status: h.indexOf("Done, with errors") >= 0,
    detailRow: h.indexOf(">set<") >= 0,
    owner: h.indexOf(">owner<") >= 0
  }));
})();
"""
    p = os.path.join(TMP, "uph.js")
    open(p, "w", encoding="utf-8").write(js)
    res = subprocess.run([node, p], capture_output=True, text=True, encoding="utf-8")
    try:
        o = json.loads(res.stdout.strip().splitlines()[-1])
    except Exception:
        o = {}
        print(res.stdout, res.stderr)
    check("result in words", o.get("result"), "3 done · 1 skipped · 2 with errors")
    check("  and a failed upload says nothing was applied", o.get("nothing"), "nothing applied")
    check("file and report links carry the account",
          (o.get("fileLink"), o.get("reportLink")), (True, True))
    check("the file name is escaped", o.get("escaped"), True)
    check("status, detail rows, and 'owner' for an unnamed uploader",
          (o.get("status"), o.get("detailRow"), o.get("owner")), (True, True, True))

print()
if fails:
    print("FAILED: %d" % len(fails))
    sys.exit(1)
print("all passed")
