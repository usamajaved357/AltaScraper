"""Orders calls use the account's own marketplace, or fail clearly (owner, 29 Sep 2026).

read.txt: "Order items with no default marketplace: Do NOT arbitrarily choose UK
or US. Use the account's explicitly configured/default marketplace. If the
account genuinely has no marketplace configured, fail clearly rather than
silently choosing another country. Consolidate the two disagreeing paths so
they use the same rule."

Before: domain/orders_live fell back to Marketplaces.US, routes/orders_routes to
Marketplaces.UK -- one order, two countries. Now both (and the order feed
beside them) go through domain.orders_live.orders_marketplace. Pinned with a
stand-in Orders client, so nothing reaches Amazon.
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


from sp_api.base import Marketplaces as M
from domain import orders_live as OL

print("=== the rule ===")
for code, want in (("UK", M.UK), ("gb", M.GB), (" us ", M.US), ("DE", M.DE)):
    check("%r -> its own marketplace" % code, OL.orders_marketplace(code), want)
for bad in ("", None, "   ", "EU", "__class__", "marketplace_id", "_value_"):
    try:
        OL.orders_marketplace(bad, "Nestwell Goods")
        check("%r refused" % (bad,), "no error", "NoMarketplace")
    except OL.NoMarketplace as e:
        check("%r refused, naming the account" % (bad,), "Nestwell Goods" in str(e), True)
try:
    OL.orders_marketplace("")
except OL.NoMarketplace as e:
    check("  and saying what to set", "default marketplace in Settings" in str(e), True)

print("=== neither reader guesses a country any more ===")
built = []


class FakeOrders:
    def __init__(self, credentials=None, marketplace=None, **k):
        built.append(marketplace)

    def get_order_items(self, oid):
        return types.SimpleNamespace(payload={"OrderItems": []})

    def get_orders(self, **k):
        return types.SimpleNamespace(payload={"Orders": []})


import sp_api.api as _api
_real = _api.Orders
_api.Orders = FakeOrders
try:
    for fn, call in (("order_items", lambda m: OL.order_items(m, {}, ["1"])),
                     ("fetch_since", lambda m: OL.fetch_since(m, "", {}, OL.day_start("UK"),
                                                              use_cache=False))):
        built.clear()
        try:
            call("")
            check(fn + ": no marketplace refused", "ran", "NoMarketplace")
        except OL.NoMarketplace:
            check(fn + ": no marketplace refused before any client exists", built, [])
        built.clear()
        call("UK")
        check(fn + ": UK asked in the UK (was the US for an unknown)", built, [M.UK])
finally:
    _api.Orders = _real

print("=== the Orders screen uses the same rule ===")
R = open("routes/orders_routes.py", "rb").read().decode("utf-8-sig")
check("no UK guess left in the Orders routes", "Marketplaces.UK" in R, False)
check("both item readers call orders_marketplace", R.count("_ol.orders_marketplace("), 2)
check("the order view refuses clearly (400) with the reason",
      'except _ol.NoMarketplace as e:\n            return jsonify({"ok": False, "error": str(e)}), 400' in R.replace("\r\n", "\n"), True)
L = open("domain/orders_live.py", "rb").read().decode("utf-8")
check("no US guess left in the order reader", "or Marketplaces.US" in L, False)

print("=== the Orders screen says so in its own words (never 'rate limiting') ===")
import json, tempfile
TMP = tempfile.mkdtemp(prefix="altaordmkt_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "acc_eu", "label": "EU Shop", "seller_id": "S1",
                         "default_marketplace": "EU"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "o.db")
from flask import Flask
import routes.orders_routes as OR
app = Flask(__name__); app.secret_key = "t"
OR.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": "acc_eu"}, _state={"active_account_id": "acc_eu"})
cl = app.test_client()
built.clear()
_api.Orders = FakeOrders
try:
    j = cl.post("/orders/items?account=acc_eu",
                json={"orders": [{"order_id": "111-1", "account_id": "acc_eu"}]}).get_json() or {}
    check("/orders/items: not counted as unread", j.get("unread"), 0)
    check("  the note names the account and the bad value",
          "'EU' is not a marketplace" in (j.get("note") or "") and "EU Shop" in (j.get("note") or ""), True)
    check("  and does not blame rate limiting", "rate limiting" in (j.get("note") or ""), False)
    r = cl.get("/orders/detail?order_id=111-1&account=acc_eu")
    check("/orders/detail: a clear 400", (r.status_code, "EU Shop" in (r.get_json() or {}).get("error", "")),
          (400, True))
    check("Amazon was never asked", built, [])
finally:
    _api.Orders = _real

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\none rule for which country an order is read in")
