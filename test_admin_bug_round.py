"""Admin screens bug round (30 Sep 2026): users, accounts, settings, Supplier
Import, sync, AI spend, performance and the account switch.

Each block below fails without its fix:
  * a NEW account whose name slugs to an existing id is refused (it silently
    overwrote that account and blanked its secrets)
  * an empty secret never overwrites a stored one in save_account
  * /accounts/select refuses an unknown id BEFORE moving the server's state
  * the account editor's marketplace box is built from the account's own
    marketplaces, so saving never resets MX / DE / CA to UK
  * /miles/stop only stops a Supplier Import run of the caller's account
  * /sync/capabilities returns each account's status (the pill read "?")
  * users.public() carries the RAW feature overrides beside the resolved ones
  * a grant wider than the caller holds is refused
  * "New link" / password reset ends existing sessions (guard compares the
    session's version)
Plain script: exits non-zero on any failure.
"""
import os
import re
import sys
import json
import shutil
import tempfile
import subprocess

_REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _REPO)

from flask import Flask, jsonify, session

fails = []


def check(label, ok, detail=""):
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL " + str(detail)))


def src(rel):
    with open(os.path.join(_REPO, rel), encoding="utf-8") as f:
        return f.read()


TMP = tempfile.mkdtemp(prefix="admin_bug_round_")
CFG = os.path.join(TMP, "cfg_for_test.json")      # never the owner's file


def write_cfg(obj):
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(obj, f)


try:
    # ------------------------------------------------------------------
    print("=== accounts: a new account may not land on an existing one ===")
    from domain import accounts as acc
    cfg = {"accounts": [{"id": "jack_uk", "label": "Jack UK",
                         "refresh_token": "Atzr|real", "lwa_client_secret": "s3"}]}
    check("new label that slugs to an existing id is refused",
          bool(acc.new_account_clash(cfg, "Jack UK")))
    check("a genuinely new label is allowed",
          acc.new_account_clash(cfg, "Brand New Co") == "")

    write_cfg(cfg)
    acc.save_account(cfg, CFG, {"id": "jack_uk", "label": "Jack UK",
                                "refresh_token": "", "lwa_client_secret": ""})
    with open(CFG, encoding="utf-8") as f:
        saved = json.load(f)["accounts"][0]
    check("empty secrets never overwrite stored ones",
          saved.get("refresh_token") == "Atzr|real" and saved.get("lwa_client_secret") == "s3",
          saved)

    # ------------------------------------------------------------------
    print("=== /accounts/select and /accounts/save ===")
    from routes import accounts_routes
    app = Flask("acc_test")
    app.secret_key = "t"
    _state = {"active_account_id": "jack_uk", "active_marketplace": "UK"}
    accounts_routes.register(app, _state=_state, _cfg=lambda: cfg, CONFIG_PATH=CFG,
                             _LIVE_CACHE={}, live_catalog=lambda: None,
                             OUTPUT_TAB="", ConfigError=Exception, _client=lambda: None)
    c = app.test_client()
    r = c.post("/accounts/select", json={"id": "no_such_account"})
    check("unknown account -> 404", r.status_code == 404, r.status_code)
    check("...and the server's open account did not move",
          _state.get("active_account_id") == "jack_uk", _state)
    r = c.post("/accounts/save", json={"label": "Jack UK"})
    check("Add account with an existing name -> 409", r.status_code == 409, r.status_code)
    check("...with a message naming the clash",
          "already exists" in (r.get_json() or {}).get("error", ""))
    r = c.post("/accounts/delete", json={"id": "no_such_account"})
    check("deleting an unknown account says so (not ok:true)",
          r.status_code == 404 and not (r.get_json() or {}).get("ok"))

    # ------------------------------------------------------------------
    print("=== account editor: marketplace choices are the account's own ===")
    s = src("static/js/shell.js")
    m = re.search(r"function _acctMktOptions\(a\)\{.*?\n\}\n", s, re.S)
    check("_acctMktOptions exists", bool(m))
    check("the editor uses it (no hard-coded UK/US pair)",
          "${_acctMktOptions(a)}" in s and '<option value="UK"${' not in s)
    if m and shutil.which("node"):
        js = ("function esc(x){return String(x);}\nfunction mktName(m){return m;}\n"
              + m.group(0)
              + "\nconst a=_acctMktOptions({marketplaces:['MX','CA','US'],default_marketplace:'MX'});"
              + "\nconst b=_acctMktOptions({marketplaces:[],default_marketplace:'DE'});"
              + "\nconst c=_acctMktOptions({});"
              + "\nconsole.log(JSON.stringify([a,b,c]));")
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        try:
            a_, b_, c_ = json.loads(out.stdout.strip().splitlines()[-1])
        except Exception:
            a_ = b_ = c_ = ""
        check("MX default stays selected", '<option value="MX" selected>' in a_, a_)
        check("UK is not offered for an MX/CA/US account", 'value="UK"' not in a_, a_)
        check("DE default kept even with no marketplaces detected",
              '<option value="DE" selected>' in b_, b_)
        check("a new account still gets UK and US", 'value="UK"' in c_ and 'value="US"' in c_, c_)

    # ------------------------------------------------------------------
    print("=== enterAccount / enterWorkspace ===")
    check("enterAccount no longer falls back to ACCOUNTS[0]",
          "|| ACCOUNTS[0];" not in s.split("async function enterAccount", 1)[1][:600])
    check("enterAccount has a sequence guard", "_mySeq !== _ENTER_SEQ" in s)
    check("enterWorkspace clears CUR_ACCOUNT", "CUR_ACCOUNT = null;" in
          s.split("async function enterWorkspace", 1)[1][:2500])
    check("deleteAccount reads the reply", "Could not delete:" in s)

    # ------------------------------------------------------------------
    print("=== Supplier Import: stop is scoped to the caller's run ===")
    from routes import miles_routes
    from domain import miles_runlog as rl
    import threading
    mapp = Flask("miles_test")
    mapp.secret_key = "t"
    open_acct = {"id": "mine"}
    _running = {"on": False, "proc": None}
    miles_routes.register(mapp, _miles_set_pref=lambda *a: True, _miles_get_pref=lambda: {},
                          CONFIG_PATH=CFG, SCRIPT="x.py", _MILES_STATE={},
                          _active_account=lambda: open_acct,
                          _miles_load_history=lambda: set(),
                          _miles_save_history=lambda s: None,
                          _run_lock=threading.Lock(), _running=_running)
    mc = mapp.test_client()
    r = mc.post("/miles/stop", json={"account": "mine"})
    check("no Miles run -> refused, nothing killed",
          r.status_code == 409 and not (r.get_json() or {}).get("killed"), r.status_code)
    rid = "20260930_000000_test"
    rl._RUNS[rid] = {"proc": None, "meta": {"id": rid, "state": "running",
                                            "account": "other", "owner": "",
                                            "skus": {}, "counts": {}},
                     "lines": ["secret line"], "lock": threading.Lock()}
    rl._ACTIVE["id"] = rid
    r = mc.post("/miles/stop", json={"account": "mine"})
    check("another account's run -> 403", r.status_code == 403, r.status_code)
    r = mc.get("/miles/run_tail?id=" + rid + "&account=mine")
    check("another account's run log is not tailed",
          (r.get_json() or {}).get("lines") == [], r.get_json())
    r = mc.get("/miles/run_active?account=mine")
    check("another account's run is not 'active' here",
          (r.get_json() or {}).get("active") is False)
    r = mc.get("/miles/run_log?id=../../cfg_for_test")
    check("run_log refuses a path-like id", r.status_code == 404, r.status_code)
    rl._RUNS[rid]["meta"]["account"] = "mine"
    r = mc.post("/miles/stop", json={"account": "mine"})
    check("the caller's own run -> stopped", r.status_code == 200 and (r.get_json() or {}).get("ok"),
          (r.status_code, r.get_json()))
    rl._RUNS.pop(rid, None)
    rl._ACTIVE["id"] = None
    # Review fixes (30 Sep 2026).
    _running["on"] = True
    _running["proc"] = None
    r = mc.post("/miles/stop", json={"account": "mine"})
    check("a stuck lock (no live run, no process) is still released by Stop",
          r.status_code == 200 and (r.get_json() or {}).get("released") and not _running["on"],
          (r.status_code, r.get_json(), _running))
    for path in ("/miles/run?account=other", "/miles/generate?account=other",
                 "/miles/optimize?account=other"):
        r = mc.get(path)
        body = r.get_data(as_text=True)
        check("%s with another account open is refused, not run" % path.split("?")[0],
              "[error]" in body and "ACCOUNT_MISMATCH" in body and "event: end" in body, body[:120])
    mj = src("static/js/miles.js")
    check("a run's lines stop painting after an account switch",
          "!screenStillIn(_sc)) return;" in mj.split("function milesRun", 1)[1][:2500])
    check("miles.js escapes t.source", "_milesEsc(t.source)" in mj and "'+t.source+'" not in mj)
    check("clear history asks first", "uiConfirm(" in mj.split("function milesClearHistory", 1)[1][:600])

    # ------------------------------------------------------------------
    print("=== sync: capabilities carry the status ===")
    from routes import sync_routes
    import listing.sync as lsync
    _orig_cap = lsync.capability
    lsync.capability = lambda a: {"pull_enabled": True, "pull_confirmed": True,
                                  "push_enabled": False, "push_confirmed": False,
                                  "reason": "r", "status": "confirmed"}
    try:
        sapp = Flask("sync_test")
        sync_routes.register(sapp, _cfg=lambda: cfg, _active_account=lambda: {"id": "jack_uk"},
                             _records=lambda ws: [], _ws=lambda: None,
                             _bust_records_cache=lambda: None, CONFIG_PATH=CFG)
        sc = sapp.test_client()
        j = sc.get("/sync/capabilities").get_json() or {}
        check("status is returned", (j.get("accounts") or [{}])[0].get("status") == "confirmed", j)
        r = sc.post("/sync/pull/apply", json={"sku": "X", "fields": {}, "account": "other"})
        check("apply for an account that is not open -> 409", r.status_code == 409, r.status_code)
        r = sc.post("/sync/pull/apply", json={"sku": "X", "fields": {}})
        check("apply that names no account is refused (review, 30 Sep 2026)",
              r.status_code >= 400 and not (r.get_json() or {}).get("ok"), r.status_code)
    finally:
        lsync.capability = _orig_cap
    sj = src("static/js/sync.js")
    check("SYNC_LAST pins the account", "account:_syncAcct()" in sj)
    check("apply sends the pinned account", "_syncBody(body, _pin)" in sj)

    # ------------------------------------------------------------------
    print("=== users: raw overrides, grant limits, session version ===")
    from auth import users
    u = {"id": "u1", "role": "lister", "features": {"orders": "view", "bogus": "edit"},
         "workspaces": ["a"], "password_hash": "x"}
    pub = users.public(u)
    check("public() carries the raw overrides", pub.get("feature_overrides") == {"orders": "view"},
          pub.get("feature_overrides"))
    check("...and still the resolved levels", pub["features"].get("returns") == "view"
          and "listings" in pub["features"])

    scoped = {"id": "boss", "role": "manager", "workspaces": ["a"], "active": True,
              "permissions": ["edit", "manage_users"], "perms_version": users.PERMS_VERSION,
              "password_hash": "x"}
    wide = users.prospective(None, role="lister", permissions=["edit"], workspaces=["*"])
    check("scoped admin cannot grant every account",
          bool(users.grant_exceeds(scoped, None, wide)))
    other = users.prospective(None, role="viewer", permissions=[], workspaces=["b"])
    check("scoped admin cannot grant an account they lack",
          bool(users.grant_exceeds(scoped, None, other)))
    pub_perm = users.prospective(None, role="lister", permissions=["publish"], workspaces=["a"],
                                 features={"listings": "view"})
    check("cannot grant a permission they do not hold",
          "publish" in users.grant_exceeds(scoped, None, pub_perm).lower()
          or bool(users.grant_exceeds(scoped, None, pub_perm)))
    ok_grant = users.prospective(None, role="viewer", permissions=["edit"], workspaces=["a"],
                                 features={f: "none" for f in users.FEATURES})
    check("a grant within their own is allowed",
          users.grant_exceeds(scoped, None, ok_grant) == "",
          users.grant_exceeds(scoped, None, ok_grant))
    target = {"id": "t", "role": "lister", "workspaces": ["a", "z"], "active": True,
              "permissions": ["edit"], "perms_version": users.PERMS_VERSION,
              "features": {f: "none" for f in users.FEATURES}}
    keep = users.prospective(target, workspaces=["a", "z"])
    check("keeping an account the editor lacks is allowed",
          users.grant_exceeds(scoped, target, keep) == "", users.grant_exceeds(scoped, target, keep))
    uj = src("static/js/users.js")
    check("users.js carries unseen workspaces through Save", "USERS_BY_ID[id]" in uj
          and "payload.workspaces.push(w)" in uj)
    check("editors start from the overrides", "userEditorFeatures(u)" in uj
          and "userEditorFeatures" in src("static/js/permissions.js"))

    # session version: a reset ends the old session.
    from auth import guard
    rec, token = users.create_user(CFG, "owner@example.com", role="owner")
    users.accept_invite(CFG, token, "password-one")
    uid = rec["id"]
    gapp = Flask("guard_test")
    gapp.secret_key = "t"
    gapp.before_request(guard.make_doorman(CFG, ""))

    @gapp.route("/ping")
    def _ping():
        return jsonify({"ok": True})

    gc = gapp.test_client()
    with gc.session_transaction() as sess:
        sess["authed"] = True
        sess["uid"] = uid
    r = gc.get("/ping", headers={"Accept": "application/json"})
    check("a signed-in session works", r.status_code == 200, r.status_code)
    with gc.session_transaction() as sess:
        stamped = sess.get("sv")
    check("...and is stamped with the session version", stamped == 0, stamped)
    tok2, err = users.new_invite(CFG, uid)
    check("new link bumps the session version",
          users.session_version(users.get_user(CFG, uid)) == 1)
    users.accept_invite(CFG, tok2, "password-two")
    r = gc.get("/ping", headers={"Accept": "application/json"})
    check("the old session is signed out after a reset", r.status_code == 401, r.status_code)
    # A session from BEFORE versions existed (no "sv") for somebody already
    # reset is over too -- stamping it would let the reset browser back in.
    gc2 = gapp.test_client()
    with gc2.session_transaction() as sess:
        sess["authed"] = True
        sess["uid"] = uid
    r = gc2.get("/ping", headers={"Accept": "application/json"})
    check("an unversioned session of a reset user is signed out", r.status_code == 401, r.status_code)
    check("the email sign-in stamps the version too",
          'session["sv"] = users.session_version(user)' in src("routes/dash_auth_routes.py"))

    # Nobody resets or removes someone who holds more than they do.
    owner_rec = users.get_user(CFG, uid)
    check("a scoped admin is outranked by the owner",
          bool(users.grant_exceeds(scoped, None, owner_rec)))
    ur = src("routes/users_routes.py")
    for fn in ("def users_invite", "def users_delete"):
        check("%s refuses when the caller is outranked" % fn.split()[1],
              "_outranks(" in ur.split(fn, 1)[1].split("@app.route", 1)[0])

    # The bell and /media never fall back to the server's open account.
    nr = src("routes/notify_routes.py")
    for fn in ("def notify_inbox", "def notify_read"):
        body = nr.split(fn, 1)[1].split("@app.route", 1)[0].split("\n    def ", 1)[0]
        check("%s reads only the named account" % fn.split()[1],
              "_named_only()" in body and "_acct()" not in body)
    mr = src("routes/media_routes.py").split("def _foreign_account_refusal", 1)[1].split("@app.route", 1)[0]
    check("/media normalises the path before the account check", "normpath" in mr)
    check("/media has no 'open account' shortcut", "_rqa.current" not in mr)

    # ------------------------------------------------------------------
    print("=== small ones ===")
    check("aiusage defaults a scoped caller to the open account", "_aiScope()" in src("static/js/aiusage.js"))
    au = src("domain/ai_usage.py")
    check("ai_usage no longer passes the literal 'unknown'",
          'or "unknown",' not in au)
    check("performance empty state checks the total",
          "if (!total) {" in src("static/js/performance.js"))
    check("guard checks credentials_source_account_id",
          '"credentials_source_account_id")' in src("auth/guard.py"))
    bp = src("static/js/brand_panel.js")
    check("brand panel escapes brand_name and vendors",
          "_bEsc(b.brand_name)" in bp and "_bEsc(v.name)" in bp)
    st = src("static/js/settings.js")
    check("saveAISettings reads the reply",
          "Could not save: " in st.split("async function saveAISettings", 1)[1][:900])
    sr = src("routes/settings_routes.py")
    check("settings ads/tracking no longer ignore a failed write",
          "_settings.write_raw(raw, CONFIG_PATH)\n            _state" not in sr.replace("\r\n", "\n"))
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
