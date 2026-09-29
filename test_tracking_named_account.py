# -*- coding: utf-8 -*-
"""Tracking routes act only for the account the request names (29 Sep 2026).

They used to fall back to the server's open account and marketplace -- owned by
whichever tab switched last -- so a request naming none was filed under another
company's orders (CLAUDE.md Rule 14). Pins: no account named -> refused and
nothing stored; named -> works, under that account, in the account's OWN
marketplace when none is asked; the route reads no _state selection at all.

SAFE HOWEVER IT IS RUN: its own throwaway config and database.
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

_TMP = tempfile.mkdtemp(prefix="alttrk_")
_CFG = os.path.join(_TMP, "config.json")
json.dump({"anthropic_api_key": "not-a-key", "google_spreadsheet_id": "not-a-sheet",
           "google_service_account_json": os.path.join(_TMP, "none.json"),
           "accounts": [{"id": "tk_a", "label": "T A", "marketplaces": ["UK"], "default_marketplace": "UK"},
                        {"id": "tk_b", "label": "T B", "marketplaces": ["DE"], "default_marketplace": "DE"}]},
          open(_CFG, "w"))
os.environ["CONFIG_PATH"] = _CFG
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")
os.environ["ALTASCRAPER_BACKGROUND"] = "off"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


import dashboard as D                          # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
c = app.test_client()
# The server's open selection points at tk_a/UK -- the old fallback would use it.
D._state["active_account_id"] = "tk_a"
D._state["active_marketplace"] = "UK"

from domain import tracking as TR              # noqa: E402

r = c.post("/tracking/set", json={"order_id": "111-1", "tracking_number": "RM123456789GB"})
check("no account named -> refused", r.status_code, 400)
check("  and nothing stored under the open account", TR.for_orders(_CFG, "tk_a", "UK", ["111-1"]), {})
r = c.get("/tracking/summary")
check("a read with no account named is refused too", r.status_code, 400)

r = c.post("/tracking/set", json={"account": "tk_b", "order_id": "222-1", "tracking_number": "RM123456789GB"})
check("named -> saved", (r.status_code, (r.get_json() or {}).get("ok")), (200, True))
check("  under THAT account, in its own marketplace (DE, not the open UK)",
      [t["tracking_number"] for t in (TR.for_orders(_CFG, "tk_b", "DE", ["222-1"]).get("222-1") or [])],
      ["RM123456789GB"])
check("  and not under the open account", TR.for_orders(_CFG, "tk_a", "UK", ["222-1"]), {})

print("== the shared Orders rules (domain/order_scope) ==")
r = c.post("/tracking/set", json={"account": "tk_a", "marketplace": "DE", "order_id": "333-1",
                                  "tracking_number": "RM123456789GB"})
check("a marketplace that is not the account's own -> refused", r.status_code, 400)
check("  and nothing stored anywhere",
      [TR.for_orders(_CFG, "tk_a", m, ["333-1"]) for m in ("UK", "DE")], [{}, {}])
r = c.post("/tracking/set", json={"account": "nope", "order_id": "333-2", "tracking_number": "RM123456789GB"})
check("an account this app does not have -> refused", r.status_code in (403, 404), True)
r = c.get("/tracking/summary?account=__all__&marketplace=UK")
check("the all-accounts placeholder is not an account", r.status_code in (403, 404), True)

print("== a number that records a send to Amazon needs publish to remove ==")
from domain import job_owner as JO             # noqa: E402
from auth import users as U                    # noqa: E402
TR.add(_CFG, "tk_a", "UK", "444-1", "RM111111111GB", carrier="RM", source="amazon")
TR.add(_CFG, "tk_a", "UK", "444-1", "RM222222222GB", carrier="RM", source="upload")
_real_current, _real_get = JO.current, U.get_user
JO.current = lambda: "u_lister"
U.get_user = lambda cp, uid: {"id": uid, "role": "custom", "active": True, "permissions": ["edit"],
                              "features": {}, "workspaces": ["*"], "perms_version": 99}
try:
    r = c.post("/tracking/set", json={"account": "tk_a", "order_id": "444-1",
                                      "tracking_number": "RM111111111GB", "remove": True})
    check("without publish: the Amazon-send record cannot be removed", r.status_code, 403)
    check("  and it is still there", len(TR.for_orders(_CFG, "tk_a", "UK", ["444-1"])["444-1"]), 2)
    r = c.post("/tracking/set", json={"account": "tk_a", "order_id": "444-1",
                                      "tracking_number": "RM222222222GB", "remove": True})
    check("  an ordinary number can be, as before", (r.status_code, (r.get_json() or {}).get("removed")), (200, 1))
    U.get_user = lambda cp, uid: {"id": uid, "role": "custom", "active": True,
                                  "permissions": ["edit", "publish"], "features": {},
                                  "workspaces": ["*"], "perms_version": 99}
    r = c.post("/tracking/set", json={"account": "tk_a", "order_id": "444-1",
                                      "tracking_number": "RM111111111GB", "remove": True})
    check("with publish: it can be removed (to allow a resend)", (r.status_code, (r.get_json() or {}).get("removed")), (200, 1))
finally:
    JO.current, U.get_user = _real_current, _real_get

SRC = open(os.path.join(HERE, "routes", "tracking_routes.py"), encoding="utf-8").read()
code = "\n".join(l for l in SRC.splitlines() if not l.lstrip().startswith("#"))
check("the route reads no open-account or open-marketplace selection",
      re.findall(r'_state\.get\("active_(account_id|marketplace)"|_state\)\.get\("active_', code), [])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
