# -*- coding: utf-8 -*-
"""Extra handling days: an account default every SKU follows, unless it has its own.

THE REQUEST (owner, 27 Oct 2026):

  "I can add +1, +2, or +3 of my own choice by bulk-selecting them and then
   changing it."
  "You're right that I should be able to override the default setting by
   selecting and changing things in it."
  "If I want to see the items that have a collective shipping time of less than
   5 days, I should be able to see them: 2 days handling, 3 days shipping"

So:
  * the account's Extra handling (the sku='' rule row) applies to every SKU
    with no number of its own;
  * a SKU's own number wins, including an own 0;
  * an empty value puts a SKU back on the account default (it used to store 0,
    which made "back to default" impossible);
  * the screen can tell own from inherited (source_repo.own_rules);
  * "days to the buyer" is handling + postage, worked out in one place
    (sourcing.buyer_days) and carried on the decision's breakdown.
"""
# THE TREE THIS TEST LIVES IN (see test_hold_price.py).
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, _REPO)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


def truthy(l, g):
    check(l, bool(g), True)


from domain import sourcing as S                              # noqa: E402

NOW = dt.datetime(2026, 10, 27, 12, 0, 0)
AT = NOW.strftime("%Y-%m-%d %H:%M:%S")


def pair(dispatch_days, price=10.0):
    return [({"id": 1, "url": "https://www.ebay.co.uk/itm/1", "label": "itm/1",
              "kind": "ebay", "enabled": 1, "priority": 100},
             {"status": S.FETCHED, "price": price, "shipping": 0.0,
              "currency": "GBP", "in_stock": True, "dispatch_days": dispatch_days,
              "error": "", "checked_at": AT, "gone_streak": 0})]


print("=== days to the buyer = handling + postage, in one place ===")
check("1 day handling + 2 days postage = 3", S.buyer_days(1, {}), 3)
check("  the saved postage setting is used", S.buyer_days(2, {"shipping_policy_days": 3}), 5)
check("  a postage of 0 is a real 0", S.buyer_days(2, {"shipping_policy_days": 0}), 2)
check("  unknown handling -> unknown total, not a guess", S.buyer_days(None, {}), None)

print("\n=== the decision carries it, with the extra days in it ===")
rule = S.rule_with_defaults({"handling_buffer_days": 1, "shipping_policy_days": 2,
                             "min_price": 1.0})
d = S.decide({"price": 30.0, "quantity": 3, "lead_days": 1}, pair(3), rule, NOW)
b = d.get("breakdown") or {}
check("eBay 3 days -> handling 1 + 1 extra = 2", b.get("lead_days"), 2)
check("  and the buyer is shown 2 + 2 postage = 4", b.get("buyer_days"), 4)
check("  the supplier's own days are still there to show", b.get("supplier_dispatch_days"), 3)
check("  and so are the extra days", b.get("buffer_days"), 1)

print("\n=== the account default, and a SKU's own number ===")
TMP = tempfile.mkdtemp(prefix="altaxh_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "xh.db")
from domain import source_repo as R                            # noqa: E402

R.save_rule(CFG, "ws", "UK", "", {"handling_buffer_days": 1})
R.save_rule(CFG, "ws", "UK", "OWN-2", {"handling_buffer_days": 2})
R.save_rule(CFG, "ws", "UK", "OWN-0", {"handling_buffer_days": 0})
R.save_rule(CFG, "ws", "UK", "FLOOR-ONLY", {"min_price": 5.0})


def buf(sku):
    return S.rule_with_defaults(R.rule_for(CFG, "ws", "UK", sku))["handling_buffer_days"]


check("a SKU with no rule row follows the account (+1)", buf("NEW"), 1)
check("  and so does one whose row sets something else", buf("FLOOR-ONLY"), 1)
check("a SKU's own +2 wins", buf("OWN-2"), 2)
check("  and an own 0 wins too -- 0 is a choice, not 'unset'", buf("OWN-0"), 0)
check("handling for a 3-day supplier on the default: 1 + 1",
      S.handling_days(3, S.rule_with_defaults(R.rule_for(CFG, "ws", "UK", "NEW"))), 2)

own = R.own_rules(CFG, "ws", "UK")
check("own_rules: the +2 is OWN-2's own", own.get("OWN-2", {}).get("handling_buffer_days"), 2)
check("  the 0 is OWN-0's own", own.get("OWN-0", {}).get("handling_buffer_days"), 0)
check("  FLOOR-ONLY has no number of its own",
      "handling_buffer_days" in own.get("FLOOR-ONLY", {}), False)
check("  and the account's row is not a SKU", "" in own, False)
check("  another account sees none of them", R.own_rules(CFG, "other", "UK"), {})

print("\n=== the route: empty means 'follow the account' ===")
import dashboard as D                                          # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "xh.db")


def post(rule, sku="OWN-2"):
    with app.test_client() as c:
        return c.post("/sourcing/rules", json={"id": "ws", "marketplace": "UK",
                                               "sku": sku, "rule": rule})


r = post({"handling_buffer_days": None})
check("null is accepted", r.status_code, 200)
check("  and OWN-2 is back on the account's +1", buf("OWN-2"), 1)
check("  with nothing of its own left",
      "handling_buffer_days" in R.own_rules(CFG, "ws", "UK").get("OWN-2", {}), False)
r = post({"handling_buffer_days": 3})
check("+3 is saved as its own", (r.status_code, buf("OWN-2")), (200, 3))
r = post({"handling_buffer_days": ""})
check("an empty box puts it back on the default too", (r.status_code, buf("OWN-2")), (200, 1))
r = post({"handling_buffer_days": 0})
check("an explicit 0 is kept as its own 0", (r.status_code, buf("OWN-2")), (200, 0))
check("  and is listed as its own",
      R.own_rules(CFG, "ws", "UK").get("OWN-2", {}).get("handling_buffer_days"), 0)
check("31 days is refused", post({"handling_buffer_days": 31}).status_code, 400)
check("a negative is refused", post({"handling_buffer_days": -1}).status_code, 400)
r = post({"handling_buffer_days": 2}, sku="")
check("the account default is set the same way (sku '')", r.status_code, 200)
check("  and a SKU with none of its own follows it", buf("NEW"), 2)

print("\n=== the Repricer list says which numbers are a SKU's own ===")
SRC = open(os.path.join(_REPO, "routes", "sourcing_routes.py"), encoding="utf-8").read()
truthy("each row carries own_rule, from own_rules", '"own_rule": _own_rules.get(' in SRC)

print("\n" + ("FAILURES: %s" % ", ".join(fails) if fails else "FAILURES: 0"))
sys.exit(1 if fails else 0)
