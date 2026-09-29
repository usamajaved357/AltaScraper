# -*- coding: utf-8 -*-
"""4G (29 Sep 2026), server side: a destructive bulk write names its account.

/clear_empty (deletes rows) and /rescan/apply (rewrites flag columns) used
_ws() -- the account the request names, ELSE the server's open account, owned
by whichever tab switched last. With no account named they now REFUSE; named,
they work as before. The brand routes (/brand/save assigns a brand to an
account, /brand/list scopes by it) read the account the page names first.

Also (4G review): the brand run and the Miles streams start paid AI work over a
GET, so they count as work -- a view-only user is refused, and so is a link from
another website; saving the brand panel's Google connection needs
manage_accounts.

SAFE HOWEVER IT IS RUN: it builds its OWN throwaway config and database before
the app is imported (the first version relied on run_tests.py's stand-in, and
run on its own it would have cleared rows in a real account -- review finding).
"""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
fails = []

_TMP = tempfile.mkdtemp(prefix="alta4g_")
_CFG = os.path.join(_TMP, "config.json")
json.dump({"anthropic_api_key": "not-a-key", "google_spreadsheet_id": "not-a-sheet",
           "google_service_account_json": os.path.join(_TMP, "none.json"),
           "accounts": [{"id": "t4g_a", "label": "T A", "marketplaces": ["UK"],
                         "default_marketplace": "UK"},
                        {"id": "t4g_b", "label": "T B", "marketplaces": ["UK"],
                         "default_marketplace": "UK"}]}, open(_CFG, "w"))
os.environ["CONFIG_PATH"] = _CFG
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")
os.environ["ALTASCRAPER_BACKGROUND"] = "off"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


import dashboard as D                                  # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
c = app.test_client()
accts = (c.get("/accounts/list").get_json() or {}).get("accounts") or []
aid = (accts[0] or {}).get("id") if accts else ""
print("  (stand-in account used: %r)" % aid)

print("== with NO account named, a destructive bulk write refuses ==")
r = c.post("/clear_empty", json={})
check("/clear_empty refuses", (r.status_code, "Which account" in (r.get_json() or {}).get("error", "")), (400, True))
r = c.post("/rescan/apply", json={})
check("/rescan/apply refuses", (r.status_code, "Which account" in (r.get_json() or {}).get("error", "")), (400, True))

if aid:
    print("== named, it works as before ==")
    r = c.post("/clear_empty?account=" + aid, json={})
    check("/clear_empty with the account named is not refused for want of one",
          "Which account" in ((r.get_json() or {}).get("error") or ""), False)
    r = c.post("/rescan/apply?account=" + aid, json={})
    check("/rescan/apply with the account named is not refused for want of one",
          "Which account" in ((r.get_json() or {}).get("error") or ""), False)

print("== the brand routes read the account the page names ==")
SRC = open(os.path.join(HERE, "dashboard_brand_patch.py"), encoding="utf-8").read()
code = "\n".join(l for l in SRC.splitlines() if not l.lstrip().startswith("#"))
check("no brand route reads the server's open account directly",
      re.findall(r'_state\.get\("active_account_id"\)', code), [])
check("  both use request_account.current (named first)", code.count("_rqa.current(_state)"), 2)

print("== streams that start paid work are work, not reads ==")
from auth import guard as G                            # noqa: E402
viewer = {"id": "u_v", "role": "viewer", "active": True, "permissions": [],
          "features": {}, "workspaces": ["*"], "perms_version": 99}
for p in ("/brand/run/Acme", "/miles/generate", "/miles/optimize", "/miles/run"):
    ok, _why = G.check(p, "GET", viewer, None, {})
    check("a view-only user may NOT start %s" % p, ok, False)
    check("  and a link from another site is refused",
          bool(G.cross_site_refusal("GET", "app.example", "https://evil.example", "", "cross-site", p)), True)
for p in ("/miles/run_log", "/miles/run_tail", "/miles/runs", "/miles/run_active", "/miles/results"):
    check("%s stays a plain read" % p, G._work_over_get(p), False)
check("saving the brand connection needs manage_accounts",
      G.required_permission("/brand/connection", "POST"), "manage_accounts")

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
