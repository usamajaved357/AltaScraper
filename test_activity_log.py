# -*- coding: utf-8 -*-
"""The one activity/audit log (Employee Performance, 29 Sep 2026).

    "Do NOT create separate tracking systems for each feature."
    "Never log: passwords, API keys, tokens, credentials, secret configuration"
    "Do not invent a performance score. Record objective work/activity evidence."

On a throwaway data directory, domain/activity.py:
  * records one row per action with who / when / account / marketplace / kind /
    entity / result, and names the person as they were AT THE TIME;
  * never stores a secret-named key, cuts long strings and lists, keeps no file
    bytes -- and "keywords" (PPC work) is not mistaken for a key;
  * never raises: an unknown kind or a broken database returns None;
  * reads back newest first, filtered by person / accounts / marketplace / kind /
    result and period; a viewer limited to some accounts never gets another
    account's rows, nor a row with no account;
  * summarises per person as plain counts -- no score field anywhere.
"""
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


TMP = tempfile.mkdtemp(prefix="altaactivity_")
CFG = os.path.join(TMP, "app.json")
json.dump({"accounts": [{"id": "acct_a"}, {"id": "acct_b"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "a.db")

from auth import users as U                    # noqa: E402
from domain import activity as A              # noqa: E402

ALI = U.create_user(CFG, "ali@example.test", name="Ali", role="lister", workspaces=["acct_a"])[0]["id"]

print("== record ==")
T0 = 1_800_000_000.0
rid = A.record(CFG, "listing.edit", category="listings", workspace_id="acct_a",
               marketplace="uk", entity_type="sku", entity_id="SKU-1",
               summary="Edited the title of SKU-1", user_id=ALI, ts=T0,
               detail={"fields": ["title"], "password": "hunter2", "api_key": "AKIA",
                       "refresh_token": "Atzr|x", "client_secret": "s", "lwa_app_id": "x",
                       "keywords": ["garlic press"], "note": "x" * 500,
                       "image": "data:image/png;base64,AAAA",
                       "skus": ["S%d" % i for i in range(50)],
                       "nested": {"auth_header": "Bearer y", "sku": "SKU-1"}})
check("a row id comes back", isinstance(rid, int), True)
row = A.entries(CFG, T0 - 1, T0 + 1)["rows"][0]
check("who: id and name at the time", (row["user_id"], row["user_label"]), (ALI, "Ali"))
check("account and marketplace (upper-cased)", (row["workspace_id"], row["marketplace"]), ("acct_a", "UK"))
check("kind, action, entity", (row["category"], row["action"], row["entity_type"], row["entity_id"]),
      ("listings", "listing.edit", "sku", "SKU-1"))
check("result defaults to ok", row["ok"], True)
d = row["detail"]
check("secret-named keys are DROPPED, not masked",
      sorted(k for k in ("password", "api_key", "refresh_token", "client_secret", "lwa_app_id") if k in d), [])
check("  also inside nested dicts", "auth_header" in d["nested"], False)
check("  and no secret VALUE survives anywhere",
      any(s in json.dumps(d) for s in ("hunter2", "AKIA", "Atzr", "Bearer")), False)
check("'keywords' is PPC work, kept", d.get("keywords"), ["garlic press"])
check("long strings are cut", len(d["note"]) <= A.MAX_STR + 1, True)
check("file content is never stored", d["image"], "<file>")
check("a long list becomes a count and the first ids",
      (d["skus"]["count"], len(d["skus"]["first"])), (50, A.MAX_LIST_IDS))

print("== never fatal ==")
check("unknown kind is refused quietly", A.record(CFG, "x", category="nonsense"), None)
from data import db as _DB                    # noqa: E402
_real = _DB.get_db


def _broken(*a, **k):
    raise RuntimeError("disk full")


_DB.get_db = _broken
check("a broken database returns None, never raises",
      A.record(CFG, "x", category="listings", user_id="", ts=T0), None)
_DB.get_db = _real

print("== who, when nobody is signed in ==")
A.record(CFG, "repricer.run", category="repricer", workspace_id="acct_b", user_id="", ts=T0 + 5)
sys_row = [r for r in A.entries(CFG, T0, T0 + 10)["rows"] if r["action"] == "repricer.run"][0]
check("background work is the system, with its own id (never the shared owner)",
      (sys_row["user_id"], sys_row["user_label"]), (A.SYSTEM_ID, A.SYSTEM_LABEL))

print("== reading and filters ==")
A.record(CFG, "image.generate", category="images", workspace_id="acct_a", marketplace="UK",
         entity_count=4, user_id=ALI, ts=T0 + 60)
A.record(CFG, "amazon.submit", category="amazon", workspace_id="acct_b", marketplace="DE",
         ok=False, summary="Amazon refused", user_id=ALI, ts=T0 + 120)
A.record(CFG, "team.user_update", category="team", workspace_id="", user_id=ALI, ts=T0 + 180)
A.record(CFG, "listing.edit", category="listings", workspace_id="acct_a", user_id=ALI, ts=T0 + 99999)
W = (T0 - 1, T0 + 1000)
allr = A.entries(CFG, *W)
check("newest first", [r["action"] for r in allr["rows"]][:2], ["team.user_update", "amazon.submit"])
check("period excludes rows outside it", allr["total"], 5)
check("by person", A.entries(CFG, *W, user_id=ALI)["total"], 4)
check("the system is its own filter", A.entries(CFG, *W, user_id=A.SYSTEM_ID)["total"], 1)
check("  and is not the shared-password owner", A.entries(CFG, *W, user_id="")["total"], 0)
check("by kind", A.entries(CFG, *W, category="images")["total"], 1)
check("failures only", [r["action"] for r in A.entries(CFG, *W, ok=False)["rows"]], ["amazon.submit"])
check("by marketplace", A.entries(CFG, *W, marketplace="de")["total"], 1)
only_a = A.entries(CFG, *W, workspaces=["acct_a"])["rows"]
check("a viewer limited to acct_a sees only acct_a rows",
      sorted({r["workspace_id"] for r in only_a}), ["acct_a"])
check("  and never a row with no account", any(r["workspace_id"] == "" for r in only_a), False)
check("an empty account list sees nothing", A.entries(CFG, *W, workspaces=[])["total"], 0)
check("limit and offset page the rows",
      [len(A.entries(CFG, *W, limit=2)["rows"]), len(A.entries(CFG, *W, limit=2, offset=4)["rows"])], [2, 1])

print("== summary: counts, no score ==")
s = A.summary(CFG, *W)
ali_s = [p for p in s if p["user_id"] == ALI][0]
check("per person totals", (ali_s["total"], ali_s["failed"]), (4, 1))
check("per kind counts", {k: v["actions"] for k, v in ali_s["by_category"].items()},
      {"listings": 1, "images": 1, "amazon": 1, "team": 1})
check("items count what one action touched", ali_s["by_category"]["images"]["items"], 4)
check("busiest person first", s[0]["user_id"], ALI)
check("no score anywhere", "score" in json.dumps(s).lower(), False)
check("summary respects the account limit",
      [p["total"] for p in A.summary(CFG, *W, workspaces=["acct_b"])], [1, 1])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
