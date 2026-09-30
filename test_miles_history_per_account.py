"""Supplier Import harvested-items history is PER ACCOUNT (30 Sep 2026).

Owner decision: "Supplier Import history MUST be separate per account. The
harvested-item history for Account A must never be shared with Account B. The
'clear history' action must clear only the current account's history."

It was one file for the whole server (miles_harvested.json), so A's harvest
made B's upload report items as "already harvested", and Clear on A wiped B.
Each block below fails on the old code:
  * A's history is not B's history
  * clearing A empties A and leaves B unchanged (module and route)
  * the old shared file is split by EVIDENCE only (a saved run naming the
    account); the rest goes to an unattributed file no account reads
  * no account named -> nothing read, nothing saved, clear refused
  * the routes use domain/miles_history.py; the shared text store is no
    longer folded into the harvest's 'done' set
Plain script: exits non-zero on any failure.
"""
import json
import os
import shutil
import sys
import tempfile
import threading

_REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _REPO)

from flask import Flask  # noqa: E402

from domain import miles_history as MH  # noqa: E402

fails = []


def check(label, ok, detail=""):
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL " + str(detail)))


def src(rel):
    with open(os.path.join(_REPO, rel), encoding="utf-8") as f:
        return f.read()


tmp = tempfile.mkdtemp(prefix="miles_hist_")
try:
    CFG = os.path.join(tmp, "config.json")
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump({}, f)

    print("=== A's history is not B's ===")
    check("a fresh account has no history", MH.load(CFG, "acct_a") == set())
    check("save A", MH.save(CFG, "acct_a", {"MSF1", "MSF2"}))
    check("A reads its own items", MH.load(CFG, "acct_a") == {"MSF1", "MSF2"}, MH.load(CFG, "acct_a"))
    check("B does not see A's items", MH.load(CFG, "acct_b") == set(), MH.load(CFG, "acct_b"))
    MH.save(CFG, "acct_b", {"MSF9"})
    check("B has its own", MH.load(CFG, "acct_b") == {"MSF9"})
    check("A unchanged by B's save", MH.load(CFG, "acct_a") == {"MSF1", "MSF2"})

    print("=== clear A -> A cleared, B unchanged ===")
    check("clear A reports what A held", MH.clear(CFG, "acct_a") == 2)
    check("A is empty", MH.load(CFG, "acct_a") == set())
    check("B is unchanged", MH.load(CFG, "acct_b") == {"MSF9"})

    print("=== no account named ===")
    check("no account reads nothing", MH.load(CFG, "") == set())
    check("no account saves nothing", MH.save(CFG, "", {"X1"}) is False)
    check("no account cannot clear", MH.clear(CFG, "") is None)
    check("and no shared file was written", not os.path.exists(MH.legacy_path(CFG)))

    print("=== an account id cannot escape the folder ===")
    p = MH.account_path(CFG, "../../evil")
    check("path-like id stays under miles_accounts/",
          os.path.abspath(p).startswith(os.path.join(tmp, MH.ACCOUNTS_DIR)), p)
    check("an id cannot name the unattributed folder",
          MH.account_path(CFG, MH.UNATTRIBUTED) != MH.unattributed_path(CFG))

    print("=== the old shared file is split by evidence only ===")
    tmp2 = tempfile.mkdtemp(prefix="miles_hist_mig_")
    try:
        CFG2 = os.path.join(tmp2, "config.json")
        with open(CFG2, "w", encoding="utf-8") as f:
            json.dump({}, f)
        with open(MH.legacy_path(CFG2), "w", encoding="utf-8") as f:
            json.dump(["L1", "L2", "L3", "L4"], f)
        os.makedirs(os.path.join(tmp2, "miles_runs"))
        # A run that names acct_a and harvested L1, generated L2; L3 was only
        # 'processing' (no evidence). A run with no account proves nothing.
        with open(os.path.join(tmp2, "miles_runs", "r1.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "r1", "account": "acct_a", "skus": {
                "L1": {"status": "harvested"}, "L2": {"status": "generated"},
                "L3": {"status": "processing"}}}, f)
        with open(os.path.join(tmp2, "miles_runs", "r2.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "r2", "skus": {"L4": {"status": "harvested"}}}, f)
        plan = MH.plan_migration(CFG2)
        check("dry run counts: 4 old, 2 attributed, 2 unattributed",
              (plan["legacy"], plan["attributed_items"], plan["unattributed"]) == (4, 2, 2), plan)
        check("dry run wrote nothing", os.path.exists(MH.legacy_path(CFG2))
              and not os.path.exists(os.path.join(tmp2, MH.ACCOUNTS_DIR)))
        check("A gets only the items it has evidence for",
              MH.load(CFG2, "acct_a") == {"L1", "L2"}, MH.load(CFG2, "acct_a"))
        check("B gets none of the old entries", MH.load(CFG2, "acct_b") == set(), MH.load(CFG2, "acct_b"))
        check("the unevidenced entries are kept apart",
              set(json.load(open(MH.unattributed_path(CFG2), encoding="utf-8"))) == {"L3", "L4"})
        check("the old file was moved, not left to be read",
              not os.path.exists(MH.legacy_path(CFG2)))
        orig = os.path.join(tmp2, MH.ACCOUNTS_DIR, MH.LEGACY_ORIGINAL, MH.LEGACY_FILE)
        check("the original is kept unchanged",
              set(json.load(open(orig, encoding="utf-8"))) == {"L1", "L2", "L3", "L4"})
        MH.clear(CFG2, "acct_a")
        check("clearing A after migration leaves the kept-apart entries",
              set(json.load(open(MH.unattributed_path(CFG2), encoding="utf-8"))) == {"L3", "L4"})
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    print("=== the routes: upload count and clear are per account ===")
    from routes import miles_routes
    app = Flask("miles_hist_test")
    app.secret_key = "t"
    open_acct = {"id": "acct_a"}
    miles_routes.register(app, _miles_set_pref=lambda *a: True, _miles_get_pref=lambda: {},
                          CONFIG_PATH=CFG, SCRIPT="x.py", _MILES_STATE={},
                          _active_account=lambda: open_acct,
                          _run_lock=threading.Lock(), _running={"on": False, "proc": None})
    c = app.test_client()
    MH.save(CFG, "acct_a", {"MSF1"})
    r = c.post("/miles/upload", json={"items": ["MSF1", "MSF9"], "account": "acct_a"})
    check("A's upload: MSF1 already harvested by A",
          (r.get_json() or {}).get("already_harvested") == ["MSF1"], r.get_json())
    open_acct["id"] = "acct_b"
    r = c.post("/miles/upload", json={"items": ["MSF1", "MSF9"], "account": "acct_b"})
    check("B's upload: A's MSF1 is not 'already harvested' for B, B's own MSF9 is",
          (r.get_json() or {}).get("already_harvested") == ["MSF9"], r.get_json())
    open_acct["id"] = "acct_a"
    r = c.post("/miles/clear_history", json={"account": "acct_a"})
    check("clear on A -> ok, 1 cleared", r.status_code == 200 and (r.get_json() or {}).get("cleared") == 1,
          (r.status_code, r.get_json()))
    check("  A is empty", MH.load(CFG, "acct_a") == set())
    check("  B unchanged", MH.load(CFG, "acct_b") == {"MSF9"}, MH.load(CFG, "acct_b"))

    print("=== source: one helper, no shared 'done' ===")
    R = src("routes/miles_routes.py")
    check("routes no longer use the injected server-wide history",
          "_miles_load_history" not in R and "_miles_save_history" not in R)
    check("the harvest loads the RUN's account history", "_mhist.load(_cfg_path, _run_acct)" in R)
    check("the shared text store is not folded into 'done'",
          "done = set(done) | set(_store.keys())" not in R)
    check("clear no longer wipes the shared text store",
          "write_json_atomic(_sp, {})" not in R)
    D = src("dashboard.py")
    check("dashboard.py no longer defines the shared history",
          "def _miles_load_history" not in D and "def _miles_save_history" not in D)
    # Scope review (30 Sep 2026): the Drive folder is ONE for every account, so
    # finding an item's files there must not write it into this account's
    # history -- that copied A's harvest into B's.
    _drv = R.split("item_has_drive_files(", 1)[1].split("items = _items_after", 1)[0]
    _has = _drv.split("if _has:", 1)[1].split("else:", 1)[0]
    check("files found in the shared Drive folder are not added to this account's history",
          "done.add(" not in _has, _has[:200])
    _after = R.split("items = _items_after", 1)[1][:900]
    check("  and not saved into it either",
          "if _newly_skipped:" in _after
          and "_mhist.save" not in _after.split("if _newly_skipped:", 1)[1].split("if _revived:", 1)[0])
    check("a reserved folder name cannot be opened as an account",
          MH.account_path(CFG, "_unattributed") != MH.account_path(CFG, "x").replace("x", "_unattributed")
          if hasattr(MH, "account_path") else True)
    J = src("static/js/miles.js")
    check("the confirm no longer says the history is shared",
          "shared by every account" not in J.split("function milesClearHistory", 1)[1][:800])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
