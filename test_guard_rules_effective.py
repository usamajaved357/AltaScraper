# -*- coding: utf-8 -*-
"""A permission rule must mean what it says (lesson L-dead-permission-rule).

auth/guard.check lets a READ through on the feature's "view" level BEFORE it
consults RULES. So a RULES entry covering a path that answers GET is not
enforced for that GET -- unless the path is in WORK_OVER_GET. That is by
design for reads, and it is how two holes happened:
  * GET /run/api_submit let a view-only user submit (master audit C4, 28 Sep)
  * GET /run/stack's new "edit" was never consulted (security re-check, 29 Sep)

This test walks EVERY route x method of the real app and lists those where a
permission is declared (required_permission) but a view-only user passes
guard.check. Each must be in INTENDED_OPEN with its reason; a NEW one fails
until someone decides: it is a read (add it here, with why) or it is work
(put it in WORK_OVER_GET). A listed one that is no longer open fails too, so
the list stays true.

SAFE HOWEVER IT IS RUN: its own throwaway config and database.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
fails = []

_TMP = tempfile.mkdtemp(prefix="altarules_")
_CFG = os.path.join(_TMP, "config.json")
json.dump({"anthropic_api_key": "not-a-key", "google_spreadsheet_id": "not-a-sheet",
           "google_service_account_json": os.path.join(_TMP, "none.json"),
           "accounts": [{"id": "ra", "label": "R A", "marketplaces": ["UK"], "default_marketplace": "UK"}]},
          open(_CFG, "w"))
os.environ["CONFIG_PATH"] = _CFG
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")
os.environ["ALTASCRAPER_BACKGROUND"] = "off"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


# Reads a view-only user may make although the path sits under a rule written
# for its WRITES. Reason per group; checked against the code on 29 Sep 2026.
_SETTINGS_READ = "settings read: returns only whether a key is stored + its last 4 characters; writing needs manage_accounts (WRITE_RULES)"
_SOURCING_READ = "Repricer screen read (templates, rules, alerts, defaults): shows figures, changes nothing; every /sourcing write needs publish"
_PPC_READ = "PPC analytics read: figures only (Rule 8: nothing here touches a bid or budget); the ppc permission gates the writes"
INTENDED_OPEN = {
    ("GET", "/submit/precheck"): "a dry check of what a submit would send; sends nothing (the submit itself needs publish)",
    ("POST", "/view/set"): "switching which sheet/tab the page READS -- navigation, not data (guard treats the view switch as a read)",
    ("GET", "/ppc/analytics/overview"): _PPC_READ,
    ("GET", "/ppc/analytics/terms"): _PPC_READ,
    ("GET", "/ppc/analytics/campaigns"): _PPC_READ,
    ("GET", "/ppc/analytics/terms.csv"): _PPC_READ,
    ("GET", "/ppc/download/<path:fname>"): _PPC_READ,
    ("GET", "/ppc/analytics"): _PPC_READ,
    ("GET", "/ppc/analytics.csv"): _PPC_READ,
    ("GET", "/ppc/brand_terms"): _PPC_READ,
    ("GET", "/ppc/live"): _PPC_READ,
    ("GET", "/ppc/live/asin"): _PPC_READ,
    # Added 30 Sep 2026 with the campaign controls: these two READ Amazon's
    # campaign list / one campaign's structure and change nothing; the writes
    # (/ppc/control/change, /ppc/control/negative) need publish.
    ("GET", "/ppc/control/campaigns"): "reads Amazon's campaign list (state, budget); changes nothing -- the /ppc/control writes need publish",
    ("GET", "/ppc/control/structure"): "reads one campaign's ad groups/keywords/targets from Amazon; changes nothing -- writes need publish",
    # ("GET", "/notify/inbox") WAS HERE and is gone (30 Sep 2026): the bell now
    # has its own RULES line with None -- open to every signed-in user, not
    # merely left open under manage_accounts -- so it declares no permission.
    ("GET", "/notify/channels"): "channel list WITHOUT the webhook URL (include_secret is never passed); changing needs manage_accounts",
    ("GET", "/notify/log"): "what was sent, read-only",
    ("GET", "/sourcing/template.csv"): _SOURCING_READ,
    ("GET", "/sourcing/alerts"): _SOURCING_READ,
    ("GET", "/sourcing/default_direction"): _SOURCING_READ,
    ("GET", "/sourcing/default_target"): _SOURCING_READ,
    ("GET", "/sourcing/default_stock"): _SOURCING_READ,
    ("GET", "/sourcing/rules_all"): _SOURCING_READ,
    ("GET", "/sourcing/master"): _SOURCING_READ,
    ("GET", "/sourcing/shipping_policy"): _SOURCING_READ,
    ("GET", "/settings/ads"): _SETTINGS_READ,
    ("GET", "/settings/tracking"): _SETTINGS_READ,
    ("GET", "/settings/ebay"): _SETTINGS_READ,
    # Customer messages mailbox (30 Sep 2026): host, port, address, and whether
    # a password is stored + its last 4 -- never the password.
    ("GET", "/settings/mailbox"): _SETTINGS_READ,
    ("GET", "/genimage/jobs_active"): "which image jobs are running (progress only)",
    ("GET", "/run/plan"): "a generation PLAN: spends and writes nothing (WORK_OVER_GET_EXCEPT)",
    ("GET", "/preview/jobs"): "preview-queue status, filtered per job by who may see its account",
}

import dashboard as D                          # noqa: E402
app = D.build_app()
from auth import guard as G                    # noqa: E402
from auth import users as U                    # noqa: E402

viewer = {"id": "u_view", "role": "custom", "active": True, "permissions": [],
          "features": {f: "view" for f in U.FEATURES}, "workspaces": ["*"], "perms_version": 99}


def walk():
    """{(method, route): permission} a view-only user passes although declared."""
    found = {}
    for rule in app.url_map.iter_rules():
        concrete = rule.rule.replace("<", "").replace(">", "")
        for m in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            need = G.required_permission(concrete, m)
            if not need:
                continue
            ok, _why = G.check(concrete, m, viewer, {"account": "ra"}, {"account": "ra"})
            if ok:
                found[(m, rule.rule)] = need
    return found


open_now = walk()

print("== every declared permission is enforced, or its openness is intended ==")
new = sorted(set(open_now) - set(INTENDED_OPEN))
stale = sorted(set(INTENDED_OPEN) - set(open_now))
check("no route declares a permission a view-only user slips past (unlisted)", new, [])
check("every INTENDED_OPEN entry is still open (the list stays true)", stale, [])
check("every intended one has a reason", [k for k, v in INTENDED_OPEN.items() if len(v) < 20], [])

print("\n== the two past holes stay closed ==")
for path in ("/run/api_submit", "/run/stack"):
    ok, _w = G.check(path, "GET", viewer, None, {"account": "ra"})
    check("a view-only user cannot GET %s" % path, ok, False)

print("\n== the checker catches the class (a deliberate bad example) ==")
saved = list(G.RULES)
try:
    G.RULES.insert(0, ("/orders/list", "publish"))          # a rule on a plain read
    planted = sorted(set(walk()) - set(INTENDED_OPEN))
    check("a permission put on a GET route the read shortcut ignores is reported",
          planted, [("GET", "/orders/list")])
finally:
    G.RULES[:] = saved

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
