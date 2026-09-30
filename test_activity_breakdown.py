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

print("\n== a BATCH submit is one row PER PRODUCT (owner, 30 Sep 2026) ==")
from domain import activity_catalog as C      # noqa: E402


class _Reply:                                  # a streamed run's reply
    status_code = 200
    is_streamed = True


B0 = T + 10000
rec("listing.edit", "listings", ts=B0 + 5, sku="B07")                      # before the batch
twenty = ["B%02d" % i for i in range(1, 21)]
batch = C.rows("GET", "/run/api_submit", {}, {"account": "acct_a", "marketplace": "UK",
                                              "skus": ",".join(twenty)}, None, _Reply())
check("a 20-product batch -> 20 rows, each one product",
      (len(batch), [b["entity_id"] for b in batch], {b["entity_count"] for b in batch}),
      (20, twenty, {1}))
check("  all the same batch_id and batch_size, the same account and action",
      (len({b["detail"]["batch_id"] for b in batch}), {b["detail"]["batch_size"] for b in batch},
       {b["workspace_id"] for b in batch}, {b["action"] for b in batch}),
      (1, {20}, {"acct_a"}, {"amazon.submit"}))
check("  each says which product and that it was one of 20",
      batch[7]["summary"], "Submitted listings to Amazon B08 (one of 20)")
check("  kept in one go", A.record_many(CFG, [dict(b, ts=B0 + 10, user_id="u_ali") for b in batch],
                                        method="GET", path="/run/api_submit"), 20)
rec("listing.edit", "listings", ts=B0 + 20, sku="B08")                     # in the batch: counts
rec("listing.edit", "listings", ts=B0 + 30, sku="B99")                     # not in it
rec("listing.edit", "listings", ts=B0 + 40, sku="B08", ws="acct_b")        # other account's B08
BW = (B0, B0 + 100)
check("an edit on a product sent in a batch counts; B99, acct_b's B08 and the earlier B07 do not",
      A.breakdown(CFG, *BW)["after_sent"], {"edits": 1, "skus": 1})
people = {p["user_id"]: p for p in A.summary(CFG, *BW)}
check("  the batch counts as 20 submits, 20 items (no double count)",
      people["u_ali"]["by_category"]["amazon"], {"actions": 20, "failed": 0, "items": 20})

check("a refused batch stays ONE row (nothing was attempted)",
      len(C.rows("GET", "/run/api_submit", {}, {"account": "acct_a", "skus": "X1,X2,X3"},
                 None, type("R", (), {"status_code": 403, "is_streamed": True})())), 1)
big = C.rows("GET", "/run/api_submit", {}, {"account": "acct_a",
             "skus": ",".join("Z%04d" % i for i in range(C.MAX_BATCH_ROWS + 5))}, None, _Reply())
check("past the cap the rest are counted on the last row",
      (len(big), big[-1]["detail"].get("batch_overflow"), "batch_overflow" in big[0]["detail"]),
      (C.MAX_BATCH_ROWS, 5, False))
check("one product is still one row with no batch", [
      (r["entity_id"], "batch_id" in r["detail"]) for r in C.rows(
          "GET", "/run/api_submit", {}, {"account": "acct_a", "skus": "ONE"}, None, _Reply())],
      [("ONE", False)])

print("\n== the summary's filters apply ==")
check("one person", sorted(A.breakdown(CFG, *ALL, user_id="u_sara")["by_day"]), ["u_sara"])
lim = A.breakdown(CFG, *ALL, workspaces=["acct_b"])
check("a viewer limited to acct_b sees only acct_b", [p["workspace_id"] for p in lim["places"]], ["acct_b"])
check("  and no after-sent from acct_a", lim["after_sent"], {"edits": 0, "skus": 0})
check("no score anywhere", any(k in json.dumps(utc).lower() for k in ("score", "rating", "rank")), False)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
