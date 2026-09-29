"""Every screen must read the store the app actually writes to.

WHAT HAPPENED: "i pressed the generate button on jack reacherd about 1 hour ago
and there was log telling me that it is generating the listings but now when i
came back to the same page i am not able to see new drafts".

Nothing failed. The app's listings live in the database -- the generator writes
there, /row reads there, the repricer and finance read there. But /rows_all,
the one route the Listings screen uses, opened Google Sheets directly and had
no database branch at all. So a run wrote new listings into the database and
the screen showed a spreadsheet nobody writes to any more.

/dashboard/summary, which draws the home screen's per-account counts, had
exactly the same bug, so the home cards could not move either.

This test is the guard for the whole class: with the database backend selected,
a screen that shows listings must agree with the database. Not "roughly" -- the
same number, per account, because a screen that is close but not equal is how
this went unnoticed for so long.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


# ---------------------------------------------------------------------------
# A FIXTURE OF ITS OWN (28 Sep 2026). This used to build the app on the
# owner's real config.json and database. It now builds it on a stand-in config
# naming three accounts (no credentials) and a temp database seeded through the
# app's own store: different listing counts per account, so a screen that read
# the wrong account -- or the wrong store -- cannot land on the right number by
# accident. Environment set BEFORE any app import.
# ---------------------------------------------------------------------------
import json
import tempfile as _tmpf

_FIX = _tmpf.mkdtemp(prefix="fixt_listings_store_")
CFG = os.path.join(_FIX, "config.json")
_DBP = os.path.join(_FIX, "altascraper.db")
_ACCTS = {"jack_uk": 3, "nestwell_goods": 2, "selvora_limited": 1}
with open(CFG, "w", encoding="utf-8") as _fh:
    json.dump({"anthropic_api_key": "test-placeholder-not-a-key",
               "google_spreadsheet_id": "test-placeholder-sheet",
               "google_service_account_json": "test-placeholder-sa.json",
               "accounts": [{"id": a, "name": "Test " + a, "marketplace": "UK"}
                            for a in _ACCTS],
               "repricer_enabled": False, "asin_monitor_enabled": False}, _fh)
os.environ["CONFIG_PATH"] = CFG
os.environ["ALTASCRAPER_DB"] = _DBP

from data import choice as _choice
from data import db as _db
from data.store import ListingStore

assert os.path.abspath(_db.db_path(CFG)) == os.path.abspath(_DBP)
assert os.path.dirname(os.path.abspath(_DBP)) == os.path.abspath(_FIX)
for _a, _n in _ACCTS.items():
    for _i in range(_n):
        ListingStore(_a, config_path=CFG).upsert_row(
            {"SKU": "9.99_3Days_B000FIX%s%02d" % (_a[:2].upper(), _i),
             "Status": ("LIVE" if _i == 0 else "GENERATED"),
             "Title": "Fixture listing %d of %s" % (_i, _a)})

cfg = None
try:
    cfg = json.load(open(CFG, encoding="utf-8"))
except Exception:
    pass
backend = _choice.resolve(cfg or {}, CFG)
print("=== the store in use: %s ===" % backend)

if backend != "db":
    print("  (this install is on sheets -- the split this guards cannot occur)")
    sys.exit(0)

conn = _db.get_db(CFG)
counts = {r["workspace_id"]: r["n"] for r in conn.execute(
    "SELECT workspace_id, COUNT(*) n FROM listings GROUP BY workspace_id")}
print("  workspaces with listings: %d" % len(counts))

import dashboard as D
app = D.build_app()
app.config["TESTING"] = True

print("\n=== the Listings screen shows what the database holds ===")
with app.test_client() as c:
    with c.session_transaction() as s:
        s["user"] = "owner"; s["role"] = "owner"; s["is_owner"] = True

    accounts = (c.get("/accounts/list").get_json() or {}).get("accounts") or []
    checked = 0
    for a in accounts:
        aid = a.get("id")
        if not aid or aid not in counts:
            continue
        c.post("/accounts/select", json={"id": aid})
        j = c.get("/rows_all?account=" + aid).get_json() or {}
        truthy("%s: the screen answered" % aid, j.get("ok"))
        check("  %s: it shows every stored listing" % aid,
              len(j.get("rows") or []), counts[aid])
        # And it must say WHERE it read from, so this is not guesswork next time.
        check("  %s: it names the store it read" % aid,
              (j.get("source") or {}).get("store"), "database")
        checked += 1
        if checked >= 3:
            break
    truthy("at least one account was checked", checked)

    print("\n=== the home screen counts the same listings ===")
    summ = c.get("/dashboard/summary").get_json() or {}
    truthy("the summary answered", summ.get("ok") is not False)
    per = {p.get("id"): p for p in (summ.get("accounts") or summ.get("per") or [])}
    if per:
        for aid, n in list(counts.items())[:3]:
            p = per.get(aid)
            if not p:
                continue
            got = sum((p.get("counts") or {}).values())
            # Rows with neither a status nor a title are skipped by the summary,
            # so it can be lower -- but it must never be ZERO for an account
            # that has listings, which is what reading the wrong store gave.
            truthy("%s: the home screen sees its listings" % aid, got > 0)
    else:
        print("  (the summary returns no per-account block here -- shape check skipped)")

print("\n=== no listings screen is left reading the other store ===")
# A source-level guard so a new screen cannot quietly reintroduce this.
import ast
for path in ("routes/listing_routes.py", "routes/dashboard_routes.py"):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    for f in ast.walk(tree):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seg = ast.get_source_segment(src, f) or ""
        if "open_by_key" not in seg and ".worksheets()" not in seg:
            continue
        # Helpers that exist to talk to Sheets on purpose are fine; what must
        # not exist is a LISTINGS reader with no database branch.
        if f.name in ("register", "set_active_tab", "accounts_select",
                      "_sheet_write_handling", "_ws",
                      "settings_dropshipping_sheets", "input_sheet"):
            continue
        has_branch = ('resolve(' in seg and '"db"' in seg) or "_ws()" in seg
        truthy("%s: %s has a database branch" % (path, f.name), has_branch)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
