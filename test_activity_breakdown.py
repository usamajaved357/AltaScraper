# -*- coding: utf-8 -*-
"""The Employee Performance overview's shapes (domain/activity.breakdown, 30 Sep 2026).

    "Employee Performance: research-first redesign (overview + drill-down; no
     invented score; work by feature/account/marketplace, failures/corrections,
     trends)"

On a throwaway database:
  * actions and failures per day, bucketed in the VIEWER's calendar (?tz=);
  * per person per day (days active), per account + marketplace, per kind of
    work with the latest failure's reason;
  * "changed after sending": an edit/re-push on a SKU the SAME account had
    already submitted -- not one made before the submit, not another account's,
    not a failed edit;
  * the same filters as the summary (person, a limited viewer's accounts);
  * no score field anywhere.
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


TMP = tempfile.mkdtemp(prefix="altabreak_")
CFG = os.path.join(TMP, "app.json")
json.dump({"accounts": [{"id": "acct_a"}, {"id": "acct_b"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "b.db")

from domain import activity as A              # noqa: E402

# 2027-01-15 00:30 UTC -- 23:30 on the 14th for a viewer at UTC-1 (offset +60).
import calendar                               # noqa: E402
T = float(calendar.timegm((2027, 1, 15, 0, 30, 0)))


def rec(action, cat, *, ts, ws="acct_a", mkt="UK", sku="S1", ok=True, user="u_ali", detail=None):
    return A.record(CFG, action, category=cat, workspace_id=ws, marketplace=mkt,
                    entity_type="sku", entity_id=sku, ok=ok, user_id=user, ts=ts,
                    summary=action, detail=detail)


rec("listing.edit", "listings", ts=T - 7200, sku="S1")                     # before the submit
rec("amazon.submit", "amazon", ts=T - 3600, sku="S1")
rec("listing.edit", "listings", ts=T, sku="S1")                            # after: counts
rec("listing.edit", "listings", ts=T + 60, sku="S1")                       # after: counts
rec("listing.edit", "listings", ts=T + 120, sku="S1", ok=False,
    detail={"error": "Amazon said no"})                                    # failed: not a change
rec("listing.edit", "listings", ts=T + 180, sku="S1", ws="acct_b")         # other account's S1
rec("price.set", "pricing", ts=T + 86400, sku="S2", mkt="DE", user="u_sara")

ALL = (T - 86400 * 3, T + 86400 * 3)

print("== per day, in the viewer's calendar ==")
utc = A.breakdown(CFG, *ALL, tz_minutes=0)
west = A.breakdown(CFG, *ALL, tz_minutes=60)
check("UTC viewer: the 15th holds the four edits after midnight UTC",
      {d["day"]: d["actions"] for d in utc["days"]}.get("2027-01-15"), 4)
check("UTC-1 viewer: the same four are still the 14th where they sit",
      {d["day"]: d["actions"] for d in west["days"]}.get("2027-01-14"), 6)
check("failures per day", {d["day"]: d["failed"] for d in utc["days"]}.get("2027-01-15"), 1)
check("days each person was active", sorted(utc["by_day"]["u_ali"]), ["2027-01-14", "2027-01-15"])

print("\n== where and what ==")
places = {(p["workspace_id"], p["marketplace"]): (p["actions"], p["failed"]) for p in utc["places"]}
check("per account + marketplace", places, {("acct_a", "UK"): (5, 1), ("acct_b", "UK"): (1, 0),
                                            ("acct_a", "DE"): (1, 0)})
edit = [a for a in utc["actions"] if a["action"] == "listing.edit"][0]
check("per kind of work, busiest first", utc["actions"][0]["action"], "listing.edit")
check("  with its failures and the latest reason", (edit["failed"], edit["last_error"]), (1, "Amazon said no"))

print("\n== changed after it was sent ==")
check("two edits on one product, after its submit, same account",
      utc["after_sent"], {"edits": 2, "skus": 1})
check("a period that starts after the submit still sees it (the submit is any time before)",
      A.breakdown(CFG, T - 10, T + 100)["after_sent"], {"edits": 2, "skus": 1})

print("\n== the summary's filters apply ==")
check("one person", sorted(A.breakdown(CFG, *ALL, user_id="u_sara")["by_day"]), ["u_sara"])
lim = A.breakdown(CFG, *ALL, workspaces=["acct_b"])
check("a viewer limited to acct_b sees only acct_b", [p["workspace_id"] for p in lim["places"]], ["acct_b"])
check("  and no after-sent from acct_a", lim["after_sent"], {"edits": 0, "skus": 0})
check("no score anywhere", any(k in json.dumps(utc).lower() for k in ("score", "rating", "rank")), False)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
