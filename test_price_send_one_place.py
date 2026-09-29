# -*- coding: utf-8 -*-
"""4F (29 Sep 2026): every price writer sends through ONE function.

domain/source_apply.push_patches is the send for the repricer (apply_one), the
repricer's price box (/sourcing/manual_price), the price editor
(/listing/price/apply) and the percentage change (/listing/price/percent_apply).
Each keeps its own gates and its own words; only the send is shared.

Pins: accepted-only; a refusal worded from Amazon's issues with each caller's
own default and width; the locale follows the marketplace; and no price writer
calls amazon_listings.patch by hand any more (a fifth copy is the drift this
removes). Amazon is never contacted: amazon_listings.patch is replaced.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from api import amazon_listings as AL          # noqa: E402
from domain import source_apply as SA          # noqa: E402

seen = []


def fake(reply):
    def _p(creds, mkt, seller, sku, mid, pt, patches, issue_locale=""):
        seen.append((mkt, sku, mid, pt, issue_locale))
        return reply
    return _p


print("== the send ==")
AL.patch = fake({"status": AL.OK, "submission_id": "sub-1", "issues": [], "error": ""})
check("accepted -> (True, '', submission id)", SA.push_patches({}, "UK", "S", "SKU1", "M", "PT", [1]), (True, "", "sub-1"))
check("  UK asks for en_GB issues", seen[-1][4], "en_GB")
SA.push_patches({}, "us", "S", "SKU1", "M", "PT", [1])
check("  US (any case) asks for en_US issues", seen[-1][4], "en_US")
long = "x" * 300
AL.patch = fake({"status": "INVALID", "submission_id": "", "error": "",
                 "issues": [{"message": long}, {"message": "b"}, {"message": "c"}, {"message": "d"}]})
ok, why, sub = SA.push_patches({}, "UK", "S", "SKU1", "M", "PT", [1])
check("refused -> not ok, no submission id", (ok, sub), (False, ""))
check("  default words + Amazon's issues, 120 characters each, three at most",
      why, "Amazon rejected the change -- " + "x" * 120 + "; b; c")
ok, why, _ = SA.push_patches({}, "UK", "S", "SKU1", "M", "PT", [1], rejected="Amazon rejected it", issue_width=140)
check("  the price editor keeps its own words and width",
      why, "Amazon rejected it -- " + "x" * 140 + "; b; c")
AL.patch = fake({"status": "ERROR", "submission_id": "", "error": "throttled", "issues": []})
check("an error from the call is shown as it came", SA.push_patches({}, "UK", "S", "SKU1", "M", "PT", [1])[1], "throttled")

print("\n== every price writer uses it ==")
SRC = {n: open(os.path.join(HERE, *p), encoding="utf-8").read() for n, p in (
    ("source_apply", ("domain", "source_apply.py")),
    ("price_routes", ("routes", "price_routes.py")),
    ("sourcing_routes", ("routes", "sourcing_routes.py")))}
check("the repricer (apply_one) sends through push_patches",
      "push_patches(creds, mkt, seller_id, sku, marketplace_id," in SRC["source_apply"].split("def apply_one(")[1], True)
check("the price editor and the percentage change do (2 calls)", SRC["price_routes"].count("_apply.push_patches("), 2)
check("  with their own words kept", SRC["price_routes"].count('rejected="Amazon rejected it", issue_width=140'), 2)
check("the repricer's price box does", SRC["sourcing_routes"].count("_apply.push_patches("), 1)
for n in ("price_routes", "sourcing_routes"):
    check("%s calls amazon_listings.patch by hand nowhere" % n, re.findall(r"_al\.patch\(", SRC[n]), [])
check("source_apply calls it once (inside push_patches)", SRC["source_apply"].count("_al.patch("), 1)

print("\n== one wording for a refused write (api/amazon_listings.refusal_text) ==")
res = {"error": "", "issues": [{"message": "m" * 200}, {"message": "two"}, {"message": "three"}]}
check("error missing -> default, then issues", AL.refusal_text(res, "Amazon rejected it"),
      "Amazon rejected it -- " + "m" * 140 + "; two; three")
check("  the variation children keep their width and count",
      AL.refusal_text(res, "rejected", width=120, count=2), "rejected -- " + "m" * 120 + "; two")
check("an error wins over the default, with no issues it stands alone",
      AL.refusal_text({"error": "throttled", "issues": []}, "x"), "throttled")
LR = open(os.path.join(HERE, "routes", "listing_routes.py"), encoding="utf-8").read()
VR = open(os.path.join(HERE, "routes", "variations_routes.py"), encoding="utf-8").read()
check("the listing image push uses it", '_al.refusal_text(res, "Amazon rejected it")' in LR, True)
check("the variation image push and parent use it (2)", VR.count('_al.refusal_text(res, "Amazon rejected'), 2)
check("the variation children use it", '_al.refusal_text(r, "rejected", width=120, count=2)' in VR, True)
check("the price send uses it", "_al.refusal_text(res, rejected, issue_width)" in SRC["source_apply"], True)
check("no route words Amazon's issues by hand any more",
      [n for n, s in (("listing_routes", LR), ("variations_routes", VR), ("price_routes", SRC["price_routes"]),
                      ("sourcing_routes", SRC["sourcing_routes"]))
       if re.search(r'i\.get\("message"\) or ""\)\[:1[24]0\]', s)], [])

print("\n== one credential lookup for the repricer (F7) ==")
from domain import accounts as ACC             # noqa: E402
ACC.account_creds = lambda a: {"token": a.get("id")}
cfg = {"accounts": [{"id": "a1", "seller_id": "S1"}, {"id": "a2", "seller_id": "S2"}]}
got = SA.seller_creds(cfg, "a2", "UK")
check("the named account's creds, marketplace id and seller id",
      (got[0], got[2], bool(got[1])), ({"token": "a2"}, "S2", True))
check("  a settings reader works the same as the settings", SA.seller_creds(lambda: cfg, "a1", "UK")[2], "S1")
try:
    SA.seller_creds(cfg, "nope", "UK")
    check("an unknown account is refused", "returned", "RuntimeError")
except RuntimeError as e:
    check("an unknown account is refused, by name", str(e), "no account called nope")
SCH = open(os.path.join(HERE, "data", "scheduler.py"), encoding="utf-8").read()
check("the timer job uses it", "_sapply.seller_creds(c, ws, mkt)" in SCH, True)
check("the Repricer screen uses it", "_sapply.seller_creds(_cfg, workspace_id, marketplace)" in SRC["sourcing_routes"], True)
check("  and neither builds credentials by hand any more",
      ["account_creds(" in SCH.split("def creds_for(ws, mkt):")[1].split("return _sapply.run_live")[0],
       "account_creds(" in SRC["sourcing_routes"].split("def _creds_for(")[1].split("def _where")[0]],
      [False, False])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
