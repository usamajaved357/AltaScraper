"""Image, image-generation and Variations requests answer for the TAB's account.

The server keeps one "open account" for every tab; the last tab to switch owns
it. These routes read only that, so with two tabs open the image library showed
the other account's pictures, an upload was filed under it, and Variations read
Amazon with its credentials. Found by tools/browser_smoke.py's two-tab check
(28 Sep 2026). No app, no database, no network.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from flask import Flask

from domain import request_account as RA

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


app = Flask(__name__)
STATE = {"active_account_id": "tab2_account"}

print("\n1. current(): the page's account, else the server's open one")
with app.test_request_context("/media/list?account=tab1_account"):
    check("?account= names it", RA.current(STATE), "tab1_account")
with app.test_request_context("/media/upload", method="POST", json={"account": "tab1_account"}):
    check("a POST body names it", RA.current(STATE), "tab1_account")
with app.test_request_context("/media/list"):
    check("nothing named -> the open account, as before", RA.current(STATE), "tab2_account")
with app.test_request_context("/media/list", method="GET", json={"account": "x"}):
    check("a GET body never names it (the guard cannot see it)", RA.current(STATE), "tab2_account")
check("outside a request (a worker) -> the open account", RA.current(STATE), "tab2_account")

print("\n2. the routes read it, not the global")


def src(rel):
    return open(os.path.join(HERE, *rel.split("/")), encoding="utf-8").read()


MEDIA = src("routes/media_routes.py")
GEN = src("routes/genimage_routes.py")
LIST = src("routes/listing_routes.py")
VAR = src("routes/variations_routes.py")
DASH = src("dashboard.py")


def body_of(s, route):
    part = s.split('@app.route("%s"' % route)[1]
    return part.split("\n    @app.route")[0]


for route in ("/media/upload", "/media/list", "/media/zip"):
    b = body_of(MEDIA, route)
    check(route + " uses current()", "_rqa.current(_state)" in b
          and 'active_account_id", "") or ""' not in b, True)
for route in ("/genimage/jobs_active", "/genimage/stop_all", "/genimage/start_batch",
              "/genimage/save_to_media"):
    b = body_of(GEN, route)
    check(route + " uses current()", "_rqa.current(_state)" in b
          and '_state.get("active_account_id"' not in b, True)
check("/run/health uses current()",
      "_rqa.current(_state)" in body_of(LIST, "/run/health"), True)
check("an upload's Drive copy never goes to another account's Drive",
      'str((acc or {}).get("id") or "") != str(aid or "")' in body_of(MEDIA, "/media/upload"), True)
dele = body_of(MEDIA, "/media/delete")
check("/media/delete refuses another account's folder",
      '_parts[0] == "_acct"' in dele and "_rqa.current(_state)" in dele
      and dele.index('_parts[0] == "_acct"') < dele.index("os.remove(fpath)"), True)
media_root = DASH.split("def _account_media_root(")[1].split("\ndef ")[0]
check("the media folder helper defaults to current()", "_rqa.current(_state)" in media_root, True)
scope = VAR.split("    def _scope():")[1].split("\n    def ")[0]
check("Variations _scope is the shared resolver", "_scope_mod.for_request(" in scope, True)
live = VAR.split("    def _live_attributes(")[1].split("\n    def ")[0]
check("Variations reads Amazon with the asked account's credentials",
      "get_account(" in live and "str(wsid)" in live, True)

print("\n3. /media/delete, driven for real against a temporary media folder")
import re
import shutil
import tempfile

tmp = tempfile.mkdtemp(prefix="media_")
try:
    def _safe(s):
        return re.sub(r"[^A-Za-z0-9._-]", "_", str(s or "_misc"))[:120] or "_misc"

    for acct in ("tab1_account", "tab2_account"):
        d = os.path.join(tmp, "_acct", acct, "SKU1")
        os.makedirs(d)
        open(os.path.join(d, "a.jpg"), "wb").write(b"x")
    mapp = Flask("media_test")
    from routes import media_routes as MR
    _n = lambda *a, **k: None
    MR.register(mapp, _media_root=lambda: tmp, _safe_sku=_safe, _sku_dir=_n,
                _state=STATE, _active_account=lambda: {"id": "tab2_account"},
                _drive_folder_id_from_url=_n, _records=_n, _ws=_n,
                _drive_upload_image=_n, _drive_map_put=_n,
                _account_media_root=lambda aid=None: tmp, _sniff_image_ext=_n,
                _to_jpeg_bytes=_n, _drive_map_remove=_n, _drive_delete_file=_n)
    c = mapp.test_client()
    r = c.post("/media/delete?account=tab1_account",
               json={"url": "/media/_acct/tab2_account/SKU1/a.jpg"})
    check("tab 1 cannot delete tab 2's image", r.status_code, 403)
    check("  and it is still there",
          os.path.exists(os.path.join(tmp, "_acct", "tab2_account", "SKU1", "a.jpg")), True)
    r = c.post("/media/delete?account=tab1_account",
               json={"url": "/media/_acct/tab1_account/SKU1/a.jpg"})
    check("tab 1 can delete its own", (r.status_code, (r.get_json() or {}).get("ok")),
          (200, True))
    check("  and it is gone",
          os.path.exists(os.path.join(tmp, "_acct", "tab1_account", "SKU1", "a.jpg")), False)
    # The review's bypasses: all normalise to tab 2's file.
    for sneaky in ("/media/./_acct/tab2_account/SKU1/a.jpg",
                   "/media/_acct/./tab2_account/SKU1/a.jpg"):
        r = c.post("/media/delete?account=tab1_account", json={"url": sneaky})
        check("refused: " + sneaky, r.status_code, 403)
    if os.name == "nt":
        for sneaky in ("/media/_ACCT/tab2_account/SKU1/a.jpg",
                       "/media/_acct\\tab2_account\\SKU1\\a.jpg"):
            r = c.post("/media/delete?account=tab1_account", json={"url": sneaky})
            check("refused (Windows): " + sneaky, r.status_code, 403)
    check("  tab 2's image survived every attempt",
          os.path.exists(os.path.join(tmp, "_acct", "tab2_account", "SKU1", "a.jpg")), True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n4. the one 'active account' every route asks for follows the request")
aa = DASH.split("def _active_account():")[1].split("\ndef ")[0]
check("_active_account() resolves through current()", "_rqa.current(_state)" in aa, True)
ws = DASH.split("def _ws():")[1].split("\ndef ")[0]
check("_ws() refuses the server's sheet for another tab's account",
      "sheet_mismatch(_state)" in ws and ws.index("sheet_mismatch") < ws.index("active_sheet_id"), True)
job = DASH.split("def _new_img_job(")[1].split("\ndef ")[0]
check("an image job is labelled with the request's account", "_rqa_current(_state)" in job, True)
with app.test_request_context("/sync/pull?account=tab1_account"):
    check("sheet_mismatch: another tab's account -> refused",
          bool(RA.sheet_mismatch(STATE)), True)
with app.test_request_context("/sync/pull?account=tab2_account"):
    check("sheet_mismatch: the open account -> allowed", RA.sheet_mismatch(STATE), "")
with app.test_request_context("/sync/pull"):
    check("sheet_mismatch: nothing named -> allowed (old behaviour)", RA.sheet_mismatch(STATE), "")
for rel in ("routes/settings_routes.py", "routes/input_routes.py",
            "routes/input_upload_routes.py", "routes/miles_template_routes.py",
            "routes/autofix_job_routes.py"):
    s = src(rel)
    check(rel + " reads current()", "_rqa_current(_state)" in s, True)
GS = body_of(GEN, "/genimage/start_batch")
check("start_batch never keeps an _acct_id the browser sent",
      'jb["_acct_id"] = _acct_now' in GS and "setdefault(\"_acct_id\"" not in GS, True)

print("\n5. on the database the ROWS follow the request too (the live backend)")
from data import backend as BE
with app.test_request_context("/live/pull_row", method="POST", json={"account": "tab1_account"}):
    check("a request naming tab 1 opens tab 1's store", BE.workspace_of(STATE), "tab1_account")
with app.test_request_context("/live/pull_row", method="POST", json={"account": "__all__"}):
    check("a placeholder is never an account", BE.workspace_of(STATE), "tab2_account")
with app.test_request_context("/rows"):
    check("nothing named -> the open account's store, as before",
          BE.workspace_of(STATE), "tab2_account")
check("outside a request (a worker) -> the open account's store",
      BE.workspace_of(STATE), "tab2_account")
with app.test_request_context("/x?account=_no_account"):
    check("current() ignores placeholders too", RA.current(STATE), "tab2_account")

print("\n6. the rest of what a tab's request touches is that account's")
brand = DASH.split("def _active_brand():")[1].split("\ndef ")[0]
check("the brand name is not the open account's view when another tab asks",
      "_other_tab" in brand and "_rqa.current(_state)" in brand, True)
instr = DASH.split("def _load_img_instructions(")[1].split("\ndef ")[0]
check("image instructions default to the request's account", "_rqa.current(_state)" in instr, True)
worker = DASH.split("def _run_img_jobs_bg_inner(")[1].split("\ndef ")[0]
check("the worker loads the BATCH's instructions", "_load_img_instructions(_job_acct or None)" in worker, True)
MISC = src("routes/misc_routes.py")
check("/dup_check asks Amazon in the tab's marketplace",
      "_scope_mod.marketplace(" in body_of(MISC, "/dup_check"), True)
AF = src("routes/autofix_job_routes.py")
check("auto-fix refuses up front when the tab shows another account",
      'mismatch_for_write(request, _state, what="auto-fixed")' in AF, True)

check("each image is made on an internal request naming the BATCH's account",
      worker.count("query_string=_job_q") >= 5 and 'payload.pop("account", None)' in worker
      and "test_request_context(json=payload)" not in worker, True)
PI = body_of(LIST, "/listing/push_image")
check("push_image refuses when its rows and its push would be two accounts",
      'if str(aid) != str(_rqa.current(_state)):' in PI
      and PI.index("_rqa.current(_state)):") < PI.index("_records(_ws())"), True)
check("push_image takes the tab's marketplace, not another tab's selection",
      '_state.get("active_marketplace")' not in PI, True)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
