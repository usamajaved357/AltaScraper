# -*- coding: utf-8 -*-
"""Employee Performance: the recorder, the permission and the reads.

    "Track meaningful business actions, not meaningless UI clicks."
    "Only appropriate owner/admin/manager roles should see employee-wide performance."

  * the ONE after-request hook (routes/activity_routes.py) records a catalogued
    write with who / account / marketplace / entity / result, records a failure
    (HTTP error, {"ok": false}, an SSE "[error]") as ok=False, and records
    nothing for reads, uncatalogued writes, 401s or another website's request;
  * it uses the guard's own reading of the account, so ?account= and a body
    account are both seen; /edit records the FIELD name and a short new value;
    uploaded files are recorded by NAME only; secrets never reach a row;
  * recording can never change or break the answer;
  * view_activity: in the owner and manager presets, granted by role to records
    written before it existed, required by /activity; a viewer limited to one
    account reads only that account's rows;
  * every catalogued path is a real route in the app.
"""
import io
import json
import os
import re
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


TMP = tempfile.mkdtemp(prefix="altaactrec_")
CFG = os.path.join(TMP, "app.json")
json.dump({"accounts": [{"id": "acct_a"}, {"id": "acct_b"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "r.db")

from flask import Flask, Response, jsonify, request   # noqa: E402
from auth import users as U, guard as G               # noqa: E402
from domain import activity as A, activity_catalog as C   # noqa: E402
import routes.activity_routes as R                    # noqa: E402

ali = U.create_user(CFG, "ali@example.test", name="Ali", role="lister", workspaces=["acct_a"])[0]["id"]
mgr = U.create_user(CFG, "mo@example.test", name="Mo", role="manager", workspaces=["acct_a"])[0]["id"]
boss = U.create_user(CFG, "boss@example.test", name="Boss", role="owner", workspaces=["*"])[0]["id"]
bea = U.create_user(CFG, "bea@example.test", name="Bea", role="lister", workspaces=["acct_b"])[0]["id"]

app = Flask(__name__)
app.secret_key = "test-only"


@app.route("/edit", methods=["POST"])
def _edit():
    b = request.get_json(force=True) or {}
    if b.get("sku") == "BAD":
        return jsonify({"ok": False, "error": "no such SKU"})
    if b.get("key") == "Source URL":
        return jsonify({"ok": False, "error": "column not editable"}), 400
    # Like the real /edit: WRITE the new value, so a before-value read after
    # the write would record new -> new and fail the test.
    if b.get("account") and b.get("target") in ("col", "attr"):
        from data.backend import store_for
        from listing import repo as _r
        ws = store_for(b["account"], {}, CFG)
        found = _r.locate(ws, b.get("sku"))
        if found.ok:
            if b["target"] == "col" and b.get("key") in found.headers:
                _r.set_field(ws, found.row, b["key"], b.get("value"), headers=found.headers)
            elif b["target"] == "attr":
                obj = _r.attributes_of(ws, found.row, found.headers)
                obj[b["key"]] = b.get("value")
                _r.set_field(ws, found.row, "Attributes JSON", json.dumps(obj), headers=found.headers)
    return jsonify({"ok": True})


@app.route("/run/<mode>")
def _run(mode):
    if request.args.get("fail"):
        return Response("data: [error] account mismatch\n\nevent: end\ndata: end\n\n",
                        mimetype="text/event-stream")
    return Response("data: started\n\n", mimetype="text/event-stream")


@app.route("/cogs/upload_sheet", methods=["POST"])
def _up():
    return jsonify({"ok": True, "set": 2})


@app.route("/users/update", methods=["POST"])
def _uu():
    return jsonify({"ok": True})


@app.route("/listing/price/apply", methods=["POST"])
def _price():
    return jsonify({"ok": False, "error": "Amazon refused"}), 502


@app.route("/rows_all")
def _read():
    return jsonify({"ok": True})


@app.route("/something/new", methods=["POST"])
def _uncat():
    return jsonify({"ok": True})


@app.route("/accounts/save", methods=["POST"])
def _acct():
    return jsonify({"ok": True})


@app.route("/users/delete", methods=["POST"])
def _udel():
    return jsonify({"ok": True})


@app.route("/preview/enqueue", methods=["POST"])
def _enq():
    return jsonify({"ok": True, "job": "j1"})


@app.route("/approve", methods=["POST"])
def _refused():
    # what the doorman answers when the permission is missing
    return jsonify({"ok": False, "error": "You do not have permission to approve.", "forbidden": True}), 403


@app.route("/delete", methods=["POST"])
def _redirected():
    from flask import redirect
    return redirect("/login")


R.register(app, CONFIG_PATH=CFG)
c = app.test_client()


def as_user(uid):
    with c.session_transaction() as s:
        s["authed"] = True
        s["uid"] = uid


def rows():
    return A.entries(CFG, 0, 4e9, limit=1000)["rows"]


print("== what is recorded ==")
as_user(ali)
c.post("/edit", json={"sku": "SKU-1", "key": "item_name", "value": "Garlic Press", "account": "acct_a",
                      "marketplace": "UK", "password": "hunter2"})
r = rows()[0]
check("an edit is one row", len(rows()), 1)
check("who, account, marketplace", (r["user_id"], r["user_label"], r["workspace_id"], r["marketplace"]),
      (ali, "Ali", "acct_a", "UK"))
check("kind and entity", (r["category"], r["action"], r["entity_type"], r["entity_id"]),
      ("listings", "listing.edit", "sku", "SKU-1"))
check("the FIELD changed and its short new value",
      (r["detail"]["values"].get("field"), r["detail"]["values"].get("new_value")), ("item_name", "Garlic Press"))
check("a human sentence", r["summary"], "Edited a listing SKU-1")
check("no secret in the row", "hunter2" in json.dumps(r), False)

c.post("/edit", json={"sku": "BAD", "key": "x", "value": "y", "account": "acct_a"})
check("{ok:false} is recorded as a failure, with the reason",
      (rows()[0]["ok"], rows()[0]["detail"].get("error")), (False, "no such SKU"))

c.post("/listing/price/apply", json={"sku": "SKU-2", "price": 9.99, "account": "acct_a"})
check("an HTTP error is a failure too", (rows()[0]["ok"], rows()[0]["http_status"]), (False, 502))
check("  and its summary says so", rows()[0]["summary"].endswith("failed: Amazon refused"), True)
check("  a price value is on the safe list", rows()[0]["detail"]["values"].get("price"), 9.99)

c.get("/run/api_submit?account=acct_a&marketplace=UK&skus=A1,B2,C3")
r = rows()[0]
check("a GET that starts work (submit) is recorded, account from ?account=",
      (r["category"], r["action"], r["workspace_id"], r["entity_count"]), ("amazon", "amazon.submit", "acct_a", 3))
c.get("/run/generate?account=acct_a&fail=1")
check("an SSE '[error]' reply is a failure",
      (rows()[0]["action"], rows()[0]["ok"], rows()[0]["detail"].get("error")),
      ("listing.generate", False, "account mismatch"))

c.post("/cogs/upload_sheet", data={"account": "acct_a",
                                   "file": (io.BytesIO(b"sku,cost\nA,1\n"), "costs.csv")},
       content_type="multipart/form-data")
r = rows()[0]
check("an upload: the file NAME, never its content",
      (r["category"], r["detail"].get("files"), "sku,cost" in json.dumps(r)), ("files", ["costs.csv"], False))

as_user(boss)
c.post("/accounts/save", json={"id": "acct_b", "name": "B Ltd", "refresh_token": "Atzr|SECRET",
                               "client_secret": "cs", "lwa_client_id": "amzn1", "aws_secret_access_key": "k"})
r = rows()[0]
check("account settings: who and which account", (r["user_label"], r["workspace_id"]), ("Boss", "acct_b"))
check("  credentials never stored, not even their names",
      [s for s in ("Atzr", "SECRET", "refresh_token", "client_secret", "aws_secret") if s in json.dumps(r)], [])

n = len(rows())
c.get("/rows_all?account=acct_a")
c.post("/something/new", json={"account": "acct_a"})
check("reads and uncatalogued writes are not recorded", len(rows()), n)
with c.session_transaction() as s:
    s.clear()
c.post("/edit", json={"sku": "X", "key": "k", "value": "v"}, headers={"Origin": "https://evil.example"})
check("another website's request is not recorded", len(rows()), n)

print("== review fixes: what counts, and as what ==")
as_user(ali)
c.post("/preview/enqueue", json={"sku": "ONE-1", "mode": "api_submit", "account": "acct_a"})
check("one product's Submit through the queue is a SUBMIT, not a preview",
      (rows()[0]["action"], rows()[0]["category"]), ("amazon.submit", "amazon"))
c.post("/preview/enqueue", json={"sku": "ONE-1", "mode": "api", "account": "acct_a"})
check("  and a queued preview stays a preview", rows()[0]["action"], "amazon.preview")
n = len(rows())
c.get("/run/api_verify?account=acct_a&skus=A1,B2")
c.get("/run/api?account=acct_a&skus=A1")
check("automatic checks the app starts by itself are not counted", len(rows()), n)
c.post("/approve", json={"sku": "SKU-9", "status": "approved", "account": "acct_a"})
r = rows()[0]
check("a guard refusal is recorded as REFUSED, not as failed work",
      (r["ok"], (r["detail"] or {}).get("refused"), r["summary"].startswith("Refused: ")), (False, True, True))
n = len(rows())
c.post("/delete", json={"sku": "SKU-9", "account": "acct_a"})
check("a redirect (to sign-in) records nothing", len(rows()), n)
as_user(boss)
c.post("/users/update", json={"id": ali, "role": "manager"})
check("team work names the person, not their id",
      ("Ali" in rows()[0]["summary"], ali in rows()[0]["summary"]), (True, False))

print("== an edit keeps the OLD value too (master baatain: safe before/after) ==")
from data.store import ListingStore            # noqa: E402
ListingStore("acct_a", config_path=CFG).upsert_row(
    {"SKU": "BEF-1", "Status": "GENERATED", "Title": "Old title",
     "Attributes JSON": json.dumps({"color": "red"})})
ListingStore("acct_b", config_path=CFG).upsert_row(
    {"SKU": "BEF-1", "Status": "GENERATED", "Title": "B's title"})
as_user(ali)
c.post("/edit", json={"sku": "BEF-1", "target": "col", "key": "Title", "value": "New title", "account": "acct_a"})
v = rows()[0]["detail"]["values"]
check("a column edit: old and new", (v.get("old_value"), v.get("new_value")), ("Old title", "New title"))
c.post("/edit", json={"sku": "BEF-1", "target": "attr", "key": "color", "value": "blue", "account": "acct_a"})
v = rows()[0]["detail"]["values"]
check("an attribute edit: old and new", (v.get("old_value"), v.get("new_value")), ("red", "blue"))
c.post("/edit", json={"sku": "BEF-1", "target": "col", "key": "Title", "value": "x"})
check("no account named: no old value is guessed from any store",
      "old_value" in rows()[0]["detail"].get("values", {}), False)
c.post("/edit", json={"sku": "BEF-1", "target": "col", "key": "Title", "value": "Third", "account": "acct_a"})
v = rows()[0]["detail"]["values"]
check("the stub really wrote, so the old value is read BEFORE the write",
      (v.get("old_value"), v.get("new_value")), ("New title", "Third"))
c.post("/edit", json={"sku": "BEF-1", "target": "col", "key": "Title", "value": "x", "workspace_id": "acct_a"})
check("an account named any other way than `account` (what /edit writes) keeps no old value",
      "old_value" in rows()[0]["detail"].get("values", {}), False)
c.post("/edit", json={"sku": "BEF-1", "target": "col", "key": "Source URL", "value": "x", "account": "acct_a"})
check("a refused edit changed nothing, so it keeps no old value",
      (rows()[0]["ok"], "old_value" in rows()[0]["detail"].get("values", {})), (False, False))
DASH = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
check("the doorman is registered before the recorder (a refused request reads nothing)",
      0 < DASH.find("app.before_request(_make_doorman(") < DASH.find("_activity_routes.register(app"), True)
c.post("/edit", json={"sku": "BEF-1", "target": "col", "key": "api_key", "value": "x", "account": "acct_a"})
check("a secret-named field keeps neither value",
      [k for k in ("old_value", "new_value") if k in (rows()[0]["detail"] or {}).get("values", {})], [])

print("== signed out: nothing is written ==")
app2 = Flask("with_password")
app2.secret_key = "test-only-2"


@app2.route("/run/<mode>")
def _run2(mode):
    return Response("data: started\n\n", mimetype="text/event-stream")


R.register(app2, CONFIG_PATH=CFG, APP_PASSWORD="a-password")
c2 = app2.test_client()
n = len(rows())
c2.get("/run/api_submit?account_id=acct_a&skus=X", headers={"Accept": "text/html"})
check("a signed-out request is never credited to anyone", len(rows()), n)
with c2.session_transaction() as s2:
    s2["authed"] = True
    s2["uid"] = ali
c2.get("/run/api_submit?account=acct_a&skus=X")
check("  while the same request signed in is recorded", len(rows()), n + 1)

_orig = A.record
A.record = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
as_user(boss)
resp = c.post("/users/delete", json={"id": ali})
A.record = _orig
check("a recording failure never changes the answer", (resp.status_code, resp.get_json()), (200, {"ok": True}))

print("== view_activity ==")
check("owner and manager presets hold it",
      ("view_activity" in U.ROLES["owner"], "view_activity" in U.ROLES["manager"],
       "view_activity" in U.ROLES["lister"]), (True, True, False))
old_manager = {"role": "manager", "active": True, "permissions": ["edit", "publish"], "perms_version": 2}
check("a manager written before it existed gets it from the role",
      U.has_permission(old_manager, "view_activity"), True)
check("  a lister does not", U.has_permission(dict(old_manager, role="lister"), "view_activity"), False)
check("  and a deliberate removal holds once stamped",
      U.has_permission(dict(old_manager, perms_version=U.PERMS_VERSION), "view_activity"), False)
check("/activity needs view_activity", G.required_permission("/activity/summary", "GET"), "view_activity")
ok_l, _ = G.check("/activity/list", "GET", U.get_user(CFG, ali), None, {})
ok_m, _ = G.check("/activity/list", "GET", U.get_user(CFG, mgr), None, {})
check("the guard refuses a lister and lets a manager in", (ok_l, ok_m), (False, True))
ok_x, _ = G.check("/activity/list", "GET", U.get_user(CFG, mgr), None, {"account": "acct_b"})
check("  but not into an account the manager may not open", ok_x, False)

print("== reading ==")
A.record(CFG, "image.generate", category="images", workspace_id="acct_b", user_id=boss)
as_user(mgr)
j = c.get("/activity/list?from=0&to=4000000000").get_json()
check("a manager limited to acct_a reads only acct_a rows",
      sorted({x["workspace_id"] for x in j["rows"]}), ["acct_a"])
as_user(boss)
j = c.get("/activity/list?from=0&to=4000000000").get_json()
check("an all-accounts owner reads every row, including team admin (no account)",
      sorted({x["workspace_id"] for x in j["rows"]}), ["", "acct_a", "acct_b"])
s = c.get("/activity/summary?from=0&to=4000000000").get_json()
check("summary lists every team member so a quiet one shows as 0",
      sorted(t["label"] for t in s["team"]), ["Ali", "Bea", "Boss", "Mo"])

print("== account scope (review fixes) ==")
as_user(mgr)
s = c.get("/activity/summary?from=0&to=4000000000").get_json()
check("a manager limited to acct_a is not told who works only in acct_b",
      sorted(t["label"] for t in s["team"]), ["Ali", "Boss", "Mo"])
check("  and the team list carries no email addresses",
      any("email" in t for t in s["team"]), False)
for sentinel in ("__all__", "_no_account"):
    r2 = c.get("/activity/list?from=0&to=4000000000&account=" + sentinel)
    j2 = r2.get_json() or {}
    check("  ?account=%s names no account: still only acct_a" % sentinel,
          sorted({x["workspace_id"] for x in j2.get("rows", [])}) if r2.status_code == 200 else "refused",
          ["acct_a"] if r2.status_code == 200 else "refused")
as_user(boss)
n = len(rows())
c.post("/edit?id=acct_a", json={"sku": "TWO-ACCTS", "key": "k", "value": "v", "account": "acct_b"})
two = [x for x in rows() if x["entity_id"] == "TWO-ACCTS"][0]
check("a request naming two accounts is filed under neither",
      (two["workspace_id"], (two["detail"] or {}).get("accounts_named")), ("", 2))
check("  and the other account's id is not stored in it", "acct_b" in json.dumps(two["detail"]), False)
as_user(mgr)
j3 = c.get("/activity/list?from=0&to=4000000000").get_json()
check("  so a manager of acct_a never sees it",
      any(x["entity_id"] == "TWO-ACCTS" for x in j3["rows"]), False)
as_user(boss)
# As the acct_a manager: 6 from the first section + submit, preview, refusal, the
# signed-in app2 submit, and 6 of the 7 before/after edits -- the one naming no
# account is filed under none, which a scoped manager does not see.
check("summary counts per person", [p["total"] for p in s["people"] if p["user_id"] == ali], [16])
check("a bad period is refused plainly",
      c.get("/activity/list?from=10&to=5").status_code, 400)
f = c.get("/activity/list?from=0&to=4000000000&user=%s&ok=0" % ali).get_json()
check("filter to one person's failures", [x["action"] for x in f["rows"]],
      # newest first: the refused "Source URL" edit, the guard refusal, then the rest
      ["listing.edit", "listing.status", "listing.generate", "price.set", "listing.edit"])

print("== the catalogue names real routes ==")
src = ""
for d in ("routes",):
    for fn in os.listdir(os.path.join(HERE, d)):
        if fn.endswith(".py"):
            src += open(os.path.join(HERE, d, fn), encoding="utf-8").read()
missing = []
for methods, path, how, *_rest in C.CATALOG:
    if path.startswith("/run/"):
        # the mode must be one /run/<mode> actually accepts
        mm = re.search(r'if mode not in \(([^)]*)\)', src)
        ok_p = '"/run/<mode>"' in src and bool(mm) and ('"%s"' % path.split("/")[2]) in mm.group(1)
    elif how == "/":
        ok_p = ('"%s/' % path) in src or ('"%s"' % path) in src
    else:
        ok_p = ('"%s"' % path) in src
    if not ok_p:
        missing.append(path)
check("every catalogued path exists in routes/", missing, [])
check("routes that only LIST or CHECK are not work (re-review)",
      [p for p in ("/product_types/drafts", "/run/api", "/run/api_verify", "/listing/price/preview")
       if any(e[1] == p for e in C.CATALOG)], [])
check("/sync/mark_status is account-level, not a listing action",
      [e[3] for e in C.CATALOG if e[1] == "/sync/mark_status"], ["team"])
check("no catalogue GET except the /run work starters",
      sorted(p for m, p, *_ in C.CATALOG if "GET" in m and not p.startswith("/run/")), [])

print("\nFAILURES: %d" % len(fails))
for x in fails:
    print("  - " + x)
sys.exit(1 if fails else 0)
