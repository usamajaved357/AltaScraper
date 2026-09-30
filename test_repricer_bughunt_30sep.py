"""Repricer bug hunt (owner, 30 Sep 2026): "can you check the repricer for bugs
and fix them". Each block fails on the code before its fix.

  1. A fresh reading that did not say the stock / postage / currency took the
     listing OUT OF STOCK. Unknown is not out of stock: it must hold.
  2. The four-hourly sweep asked eBay US with the UK postcode "B1 1AA".
  3. A postage policy of 0 days read back as 2 (`0 or 2`).
  4. Two push runs at once could both pass the cooldown and push twice.
"""
import datetime as dt
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


TMP = tempfile.mkdtemp(prefix="altarepr_bh_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "ws1", "label": "One"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "r.db")

from domain import sourcing as S         # noqa: E402
from domain import source_fetch as SF    # noqa: E402
from domain import source_apply as AP    # noqa: E402

NOW = dt.datetime(2026, 9, 30, 12, 0, 0)
FRESH = "2026-09-30 11:00:00"
GOOD = {"status": "fetched", "price": 10.0, "shipping": 0.0, "currency": "GBP",
        "in_stock": True, "dispatch_days": 3, "checked_at": FRESH, "gone_streak": 0}
CUR = {"price": 20.0, "quantity": 3, "lead_days": 1}
RULE = {"currency": "GBP"}


def src(i):
    return {"id": i, "enabled": 1, "url": "https://www.ebay.co.uk/itm/%d" % i}


def one(chk, rule=RULE):
    return S.decide(CUR, [(src(1), chk)], rule, NOW)


print("== 1. unknown is not out of stock ==")
for label, chk, rule in (
        ("stock unknown", dict(GOOD, in_stock=None), RULE),
        ("postage unknown", dict(GOOD, shipping=None), RULE),
        ("price unknown", dict(GOOD, price=None), RULE),
        ("currency unknown", dict(GOOD, currency=""), RULE),
        ("dispatch unknown under a dispatch limit", dict(GOOD, dispatch_days=None),
         dict(RULE, max_dispatch_days=5))):
    d = one(chk, rule)
    check("%s -> nothing pushed, not out of stock" % label,
          (d["action"], d["quantity"]), ("none", None))
    check("  and says why it held", bool(d["blocked_by"]), True)

d = one(dict(GOOD, in_stock=False))
check("a supplier that SAYS out of stock still takes it out of stock",
      (d["action"], d["quantity"]), ("out_of_stock", 0))
# Review, 30 Sep 2026: a sold-out item often has no postage or delivery date;
# the definite "out of stock" must win over the missing fields.
for label, chk, rule in (
        ("out of stock, postage unknown", dict(GOOD, in_stock=False, shipping=None), RULE),
        ("out of stock, price unknown", dict(GOOD, in_stock=False, price=None), RULE),
        ("out of stock, no delivery date under a dispatch limit",
         dict(GOOD, in_stock=False, dispatch_days=None), dict(RULE, max_dispatch_days=5))):
    d = one(chk, rule)
    check("%s -> out of stock, not held" % label,
          (d["action"], d["quantity"]), ("out_of_stock", 0))
d = S.decide(CUR, [(src(1), dict(GOOD, in_stock=False)),
                   (src(2), dict(GOOD, in_stock=None))], RULE, NOW)
check("one out of stock + one unknown -> hold (the unknown one may supply)",
      d["action"], "none")
UD = dict(RULE, direction="up_and_down")   # so a cheaper supplier moves the price
d = S.decide(CUR, [(src(1), dict(GOOD, in_stock=False)),
                   (src(2), dict(GOOD, price=12.0))], UD, NOW)
check("one out of stock + one good -> priced from the good one",
      (d["action"], d["source_id"]), ("update", 2))
d = one(dict(GOOD, in_stock=None), dict(UD, require_in_stock=0))
check("stock unknown is fine when the rule does not require stock",
      d["action"], "update")

print("\n== 2. the sweep's postcode follows each row's marketplace ==")
seen = []
_orig = (SF._repo.enrolled, SF._repo.skus_with_sources, SF._repo.sources_for,
         SF._repo.record_check, SF.check_source)
try:
    SF._repo.enrolled = lambda *a, **k: [
        {"workspace_id": "ws1", "marketplace": "UK", "sku": "A"},
        {"workspace_id": "ws1", "marketplace": "US", "sku": "B"}]
    SF._repo.skus_with_sources = lambda *a, **k: []
    SF._repo.sources_for = lambda cp, ws, m, sku, **k: [
        {"id": sku, "kind": "ebay", "enabled": 1, "url": "https://ebay/itm/1"}]
    SF._repo.record_check = lambda *a, **k: None

    def _fake_check(s, app_id, cert_id, now=None, marketplace=None, postcode=""):
        seen.append((s["id"], marketplace, postcode))
        return {"status": "fetched", "error": ""}
    SF.check_source = _fake_check
    SF.sweep(CFG, {"ebay_app_id": "a", "ebay_cert_id": "c"}, pause=0)
finally:
    (SF._repo.enrolled, SF._repo.skus_with_sources, SF._repo.sources_for,
     SF._repo.record_check, SF.check_source) = _orig
check("UK row -> eBay GB, a UK postcode", seen[0], ("A", "EBAY_GB", "B1 1AA"))
check("US row -> eBay US, a US postcode (was B1 1AA)", seen[1], ("B", "EBAY_US", "10001"))

print("\n== 3. the postage-days setting reaches the decision, and 0 is 0 ==")
check("rule_with_defaults keeps the setting (it used to drop it)",
      S.rule_with_defaults({"shipping_policy_days": 1}).get("shipping_policy_days"), 1)
d = S.decide(CUR, [(src(1), GOOD)], dict(RULE, shipping_policy_days=1), NOW)
check("3-day supplier, 1-day postage -> 2 days handling (was always 1)",
      d["lead_days"], 2)
from domain import source_repo as R      # noqa: E402
check("the setting is accounted for as not-stored-per-SKU",
      R.storable_rule_keys()[1], [])
check("policy_days(0) is 0", S.policy_days(0), 0)
check("policy_days('0') is 0", S.policy_days("0"), 0)
check("unset -> the 2-day default", S.policy_days(None), 2)
check("unreadable -> the 2-day default", S.policy_days("x"), 2)
d = S.decide(CUR, [(src(1), GOOD)], dict(RULE, shipping_policy_days=0), NOW)
check("the breakdown shows the 0 the handling time was worked from",
      (d["breakdown"]["shipping_policy_days"], d["lead_days"]), (0, 3))
RT = open(os.path.join(HERE, "routes", "sourcing_routes.py"), "rb").read().decode("utf-8")
check("no route reads the policy with `or` any more",
      "shipping_policy_days\")\n" not in RT
      and "or _sourcing.SHIPPING_POLICY_DAYS" not in RT, True)

print("\n== 4. one push run at a time ==")
called = []


def creds_for(ws, mkt):
    called.append((ws, mkt))
    raise RuntimeError("should not be reached")


AP._RUN_LOCK.acquire()
try:
    out = AP.run_live(CFG, {"repricer_enabled": True}, creds_for, now=NOW)
finally:
    AP._RUN_LOCK.release()
check("a second run while one is going pushes nothing",
      (out.get("busy"), out.get("pushed")), (True, 0))
check("  and never reaches Amazon", called, [])
out = AP.run_live(CFG, {"repricer_enabled": True}, creds_for, now=NOW)
check("the lock is released afterwards (a normal run goes ahead)",
      out.get("busy"), None)
check("  and a run that raised would still release it",
      AP._RUN_LOCK.acquire(False) and (AP._RUN_LOCK.release() or True), True)

print("\n== 5. the price-move notice uses the marketplace's currency ==")
from domain import currency as CUR       # noqa: E402
check("UK -> £", CUR.symbol_for_marketplace("UK"), "£")
check("US -> $", CUR.symbol_for_marketplace("US"), "$")
check("DE -> € (was £)", CUR.symbol_for_marketplace("de"), "€")
check("an unknown code shows itself, never a guess", CUR.symbol("XYZ"), "XYZ ")
APS = open(os.path.join(HERE, "domain", "source_apply.py"), "rb").read().decode("utf-8")
check("_notify_push asks the shared helper",
      "sym=_currency.symbol_for_marketplace(mkt)" in APS
      and '"$" if str(mkt).upper() == "US"' not in APS, True)

print("\n== 6. the inventory lead time uses the saved postage days ==")
json.dump({"accounts": [{"id": "ws1", "label": "One"}], "shipping_policy_days": 1},
          open(CFG, "w"))
from domain import source_repo as R2      # noqa: E402
from domain import source_run as SR       # noqa: E402
from domain import inventory_view as IV   # noqa: E402
check("one reader of the setting", SR.shipping_policy_days(CFG), 1)
R2.enrol(CFG, "ws1", "UK", "INV1")
_sid = R2.add_source(CFG, "ws1", "UK", "INV1", "https://www.ebay.co.uk/itm/111")
R2.record_check(CFG, _sid, dict(GOOD, dispatch_days=3))
lt = IV.lead_times(CFG, "ws1", "UK").get("INV1") or {}
check("3-day supplier, 1-day postage: handling 2 + postage 1 = 3 (was 1 + 2)",
      (lt.get("handling_days"), lt.get("shipping_policy_days"), lt.get("days")),
      (2, 1, 3))

print("\n== 7. 'supplier ended' is sent once, on the confirming reading ==")
told = []
from domain import notify as NT          # noqa: E402
_o_send, _o_check = NT.supplier_ended, SF.check_source
try:
    NT.supplier_ended = lambda cp, ws, sku, sup, marketplace="": told.append((ws, sku, marketplace))
    SF.check_source = lambda *a, **k: {"status": "gone", "error": "HTTP 404",
                                       "checked_at": FRESH}
    R2.enrol(CFG, "ws1", "UK", "END1")
    R2.add_source(CFG, "ws1", "UK", "END1", "https://www.ebay.co.uk/itm/222")
    R2.add_source(CFG, "ws1", "UK", "DRAFT1", "https://www.ebay.co.uk/itm/333",
                  stage=R2.DRAFT)
    SF.sweep(CFG, {"ebay_app_id": "a", "ebay_cert_id": "c"}, workspace_id="ws1",
             marketplace="UK", pause=0)
    check("first 404: nothing said (not believed yet)",
          [t for t in told if t[1] == "END1"], [])
    SF.sweep(CFG, {"ebay_app_id": "a", "ebay_cert_id": "c"}, workspace_id="ws1",
             marketplace="UK", pause=0)
    check("second 404 in a row: told once", [t for t in told if t[1] == "END1"],
          [("ws1", "END1", "UK")])
    SF.sweep(CFG, {"ebay_app_id": "a", "ebay_cert_id": "c"}, workspace_id="ws1",
             marketplace="UK", pause=0)
    check("third: not told again", len([t for t in told if t[1] == "END1"]), 1)
    check("a draft's supplier is never announced",
          [t for t in told if t[1] == "DRAFT1"], [])
finally:
    NT.supplier_ended, SF.check_source = _o_send, _o_check

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
