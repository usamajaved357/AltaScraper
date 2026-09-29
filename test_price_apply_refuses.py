# -*- coding: utf-8 -*-
"""A live price change refuses a price that is not a price -- at APPLY, not only
at preview (price-write map F1, 29 Sep 2026).

/listing/price/apply took any float: 0, -5, "nan" and "inf" went on to read the
live listing and patch Amazon, because only /listing/price/preview checked.
Pins, with Amazon stubbed so nothing can be sent, that apply refuses them BEFORE
any Amazon call, and that a real price still goes through to the patch.
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
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


TMP = tempfile.mkdtemp(prefix="altaprice_")
CFG = os.path.join(TMP, "app.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "p.db")

from flask import Flask                            # noqa: E402
from api import amazon_listings as AL              # noqa: E402
from domain import accounts as ACC                 # noqa: E402
import routes.price_routes as PR                   # noqa: E402

CALLS = []
ACCOUNT = {"id": "acct_a", "label": "A", "seller_id": "S1", "marketplaces": ["UK"],
           "default_marketplace": "UK", "lwa_client_id": "x", "refresh_token": "y"}
AL.get_item = lambda *a, **k: (CALLS.append("get_item"), {
    "status": AL.OK, "productType": "KITCHEN", "attributes": {"purchasable_offer": [{
        "marketplace_id": "A1F83G8C2ARO7P", "currency": "GBP",
        "our_price": [{"schedule": [{"value_with_tax": 10.0}]}]}]}})[1]
AL.patch = lambda *a, **k: (CALLS.append("patch"), {"status": AL.OK})[1]
ACC.seller_scope_allowed = lambda acc: True
ACC.account_creds = lambda acc: {"lwa_app_id": "x"}

app = Flask(__name__)
PR.register(app, CONFIG_PATH=CFG, _cfg=lambda: {"accounts": [ACCOUNT]},
            _active_account=lambda: ACCOUNT, _state={"active_account_id": "acct_a",
                                                      "active_marketplace": "UK"})
PR.register  # noqa
c = app.test_client()


def apply(price):
    del CALLS[:]
    r = c.post("/listing/price/apply", json={"sku": "S-1", "price": price, "confirmed": True,
                                             "id": "acct_a", "marketplace": "UK",
                                             "below_floor_ok": True})
    return r.status_code, list(CALLS)


for bad in (0, -5, "0", "nan", "inf", "-inf"):
    code, calls = apply(bad)
    check("apply refuses %r before any Amazon call" % (bad,), (code, calls), (400, []))
code, calls = apply("abc")
check("apply refuses text", (code, calls), (400, []))
code, calls = apply(12.49)
check("a real price still reads the listing and patches it", calls, ["get_item", "patch"])
r = c.post("/listing/price/preview", json={"sku": "S-1", "price": 0, "id": "acct_a", "marketplace": "UK"})
check("preview refuses zero with the same words",
      "zero or less is not a price" in (r.get_json() or {}).get("error", ""), True)

print("== one rule for every price-writing route ==")
from listing import pricing as PX                  # noqa: E402
check("usable_price: a real price", PX.usable_price("12.49"), (12.49, ""))
check("  zero / negative", [PX.usable_price(0)[1], PX.usable_price(-1)[1]], ["not_positive", "not_positive"])
check("  NaN / infinity / text", [PX.usable_price(x)[1] for x in ("nan", "inf", "-inf", "abc", None)],
      ["not_a_number"] * 5)
check("  the repricer's typed box: symbols and commas", PX.usable_price("£1,299.50", strip_symbols=True), (1299.5, ""))
del CALLS[:]
r = c.post("/listing/price/percent_apply", json={"rows": [{"sku": "S-1", "new": "inf"}, {"sku": "S-2", "new": "nan"}],
                                                  "confirmed": True, "id": "acct_a", "marketplace": "UK"})
check("percent apply refuses infinity and NaN before any Amazon call",
      (r.status_code, list(CALLS), len((r.get_json() or {}).get("failures") or [])), (400, [], 2))
SRC = open(os.path.join(HERE, "routes", "sourcing_routes.py"), encoding="utf-8").read()
check("the repricer's manual price uses the same rule",
      "usable_price(str(b.get(\"price\")), strip_symbols=True)" in SRC, True)

print("== a hand-made price change is written down ==")
from domain import source_repo as SR               # noqa: E402
before = len(SR.recent_actions(CFG, "acct_a", "UK", "S-1"))
apply(12.49)
acts = SR.recent_actions(CFG, "acct_a", "UK", "S-1")
check("apply records the change (record_action no longer fails silently)", len(acts), before + 1)
a0 = acts[0] if acts else {}
check("  with the old and the new price", (a0.get("from_price"), a0.get("to_price")), (10.0, 12.49))
check("  marked applied (it reached Amazon)", a0.get("applied"), 1)
check("  and says it came from the price editor", "price editor" in (a0.get("reason") or ""), True)
from domain import source_apply as SA              # noqa: E402
check("  under its own action, so it does NOT start the repricer's rest period",
      (a0.get("action"), SA._last_applied(CFG, "acct_a", "UK", "S-1")), ("price_editor", None))
SA.record_manual_price(CFG, "acct_a", "UK", "S-1", 13.0, was=12.49, how="", who="t")
check("the repricer's own box still pauses the repricer, as before",
      (SA._last_applied(CFG, "acct_a", "UK", "S-1") or {}).get("action"), "update")
from domain import daily_check as DC               # noqa: E402
res = DC.check_repricer({"repricer_actions": [{"action": "price_editor", "applied": 1},
                                               {"action": "update", "applied": 1}]})
check("the morning check counts only the repricer's changes", res.get("value"), "1")

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
