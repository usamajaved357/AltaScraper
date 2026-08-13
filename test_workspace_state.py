"""Two people, two workspaces, no crossing over.

The bug: the selected workspace -- and therefore which Google Sheet is read and
written -- lived in ONE dict in the server process. A VA opening their workspace
silently moved the owner's too, so the owner's next Approve/Delete/Submit went to
the VA's sheet.

Drives the REAL WorkspaceState through real Flask sessions with two clients.
"""
import sys
sys.path.insert(0, r"D:\AltaScraper")
from flask import Flask, jsonify, session
from domain.workspace_state import WorkspaceState

KEYS = ("active_account_id", "active_marketplace", "active_sheet_id",
        "active_tab", "active_tab_gid", "active_view")

fails = []
def check(label, got, want):
    ok = got == want
    if not ok: fails.append(label)
    print("  %-60s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))

app = Flask(__name__)
app.secret_key = "test-only"
_state = WorkspaceState({"cfg": None, "gc": None, "schemas": {}, "vv": None}, scoped=KEYS)

@app.route("/signin/<uid>")
def signin(uid):
    session["uid"] = uid
    return jsonify({"ok": True})

@app.route("/select/<ws>")
def select(ws):
    _state["active_account_id"] = ws
    _state["active_sheet_id"] = "sheet_of_" + ws
    return jsonify({"ok": True})

@app.route("/whoami")
def whoami():
    # This is what _ws() and _active_account() effectively ask.
    return jsonify({"account": _state.get("active_account_id"),
                    "sheet": _state.get("active_sheet_id"),
                    "personal": _state.is_personal()})

@app.route("/cache/set")
def cache_set():
    _state["cfg"] = {"loaded": True}
    return jsonify({"ok": True})

@app.route("/cache/get")
def cache_get():
    return jsonify({"cfg": _state.get("cfg")})

print("=== the shared default, before anyone signs in ===")
_state.set_shared("active_account_id", "jack_uk")
_state.set_shared("active_sheet_id", "sheet_of_jack_uk")
anon = app.test_client()
j = anon.get("/whoami").get_json()
check("a signed-out caller sees the shared default", j["account"], "jack_uk")
check("  and is not treated as personal", j["personal"], False)

print("\n=== two signed-in people pick different workspaces ===")
owner = app.test_client(); owner.get("/signin/u_owner")
va = app.test_client(); va.get("/signin/u_va")
owner.get("/select/selvora")
va.get("/select/green_haven")

o = owner.get("/whoami").get_json()
v = va.get("/whoami").get_json()
check("the owner is on their own workspace", o["account"], "selvora")
check("  reading their own sheet", o["sheet"], "sheet_of_selvora")
check("the VA is on theirs", v["account"], "green_haven")
check("  reading their own sheet", v["sheet"], "sheet_of_green_haven")
check("this is the whole bug: they differ", o["account"] != v["account"], True)

print("\n=== the VA switching does NOT move the owner ===")
va.get("/select/dropshipping")
o2 = owner.get("/whoami").get_json()
check("the owner is where they left off", o2["account"], "selvora")
check("  and still on their own sheet", o2["sheet"], "sheet_of_selvora")
check("the VA moved", va.get("/whoami").get_json()["account"], "dropshipping")

print("\n=== nor does it move the shared default on disk ===")
check("the process-wide value is untouched",
      _state.shared("active_account_id"), "jack_uk")
check("  which is what app_state.json saves",
      {k: _state.shared(k) for k in ("active_account_id", "active_sheet_id")},
      {"active_account_id": "jack_uk", "active_sheet_id": "sheet_of_jack_uk"})
check("a signed-out caller still sees the default",
      anon.get("/whoami").get_json()["account"], "jack_uk")

print("\n=== a personal choice survives the next request ===")
check("the owner's selection persists in their session",
      owner.get("/whoami").get_json()["account"], "selvora")
check("  and again", owner.get("/whoami").get_json()["account"], "selvora")

print("\n=== the shared caches stay shared ===")
owner.get("/cache/set")
check("the VA sees the cache the owner built",
      va.get("/cache/get").get_json()["cfg"], {"loaded": True})
check("  and so does a signed-out background request",
      anon.get("/cache/get").get_json()["cfg"], {"loaded": True})
check("the cache is NOT in anyone's session", "cfg" in KEYS, False)

print("\n=== background work (no request at all) uses the shared value ===")
check("outside a request context", _state.get("active_account_id"), "jack_uk")
check("  and is not personal", _state.is_personal(), False)
_state["active_account_id"] = "set_by_background"
check("  a background write goes to the shared value",
      _state.shared("active_account_id"), "set_by_background")
check("  and does not disturb the owner",
      owner.get("/whoami").get_json()["account"], "selvora")

print("\n=== it still behaves like a dict ===")
check("`in` finds a shared key", "cfg" in _state, True)
check("`in` is false for something absent", "nope" in _state, False)
check("get() honours a default", _state.get("nope", "dflt"), "dflt")
check("setdefault works", _state.setdefault("brand_new", 7), 7)
check("pop works", _state.pop("brand_new"), 7)
check("update works", (_state.update({"vv": 42}), _state.get("vv"))[1], 42)
with app.test_request_context("/"):
    session["uid"] = "u_x"
    check("`in` finds a personal key", "active_account_id" in _state, True)
    _state["active_view"] = "Selvora"
    check("  a personal write is readable back", _state["active_view"], "Selvora")
    check("  and did not leak to shared", _state.shared("active_view"), None)

print("\n=== the shared-password owner (no account) uses the shared value ===")
boot = app.test_client()
with boot.session_transaction() as s:
    s["authed"] = True            # signed in, but with no user id
check("bootstrap sees the shared value",
      boot.get("/whoami").get_json()["account"], "set_by_background")
check("  and is not personal", boot.get("/whoami").get_json()["personal"], False)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
