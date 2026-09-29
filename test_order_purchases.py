# -*- coding: utf-8 -*-
"""Orders "To buy" (30 Sep 2026): recording that an order was bought from the supplier.

A RECORD A PERSON MAKES -- the app buys nothing. Pins:
  - the record is kept per order of ONE account; another account's rows never
    see it, and removing needs the id AND the order AND the account to match
  - no money is stored (the order's cost is order_lines.cogs -- Rule 12)
  - only a web address is kept as the supplier link (no javascript: links)
  - the routes REFUSE when no account is named -- never the server's open one
  - the list attaches purchases like tracking, and "could not read" is None,
    not "none recorded"
  - tracking.attach behaves exactly as before after sharing its grouping
  - the write is recorded in the activity log and needs "edit"

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

_TMP = tempfile.mkdtemp(prefix="altabuy_")
_CFG = os.path.join(_TMP, "config.json")
json.dump({"anthropic_api_key": "not-a-key", "google_spreadsheet_id": "not-a-sheet",
           "google_service_account_json": os.path.join(_TMP, "none.json"),
           "accounts": [{"id": "tb_a", "label": "T A", "marketplaces": ["UK"],
                         "default_marketplace": "UK"},
                        {"id": "tb_b", "label": "T B", "marketplaces": ["UK", "DE"],
                         "default_marketplace": "UK"}]}, open(_CFG, "w"))
os.environ["CONFIG_PATH"] = _CFG
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")
os.environ["ALTASCRAPER_BACKGROUND"] = "off"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-72s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from domain import order_purchases as P       # noqa: E402
from domain import tracking as T              # noqa: E402

print("== the domain record ==")
pid = P.record(_CFG, "tb_a", "uk", "111-1", supplier="Argos",
               supplier_url="https://argos.example/x", supplier_ref="A99", note="n", who="me@x")
check("recorded, with an id", pid > 0, True)
got = P.for_orders(_CFG, "tb_a", "UK", ["111-1"])
rec = (got.get("111-1") or [{}])[0]
check("read back by account + marketplace (any case)", [rec.get("supplier"), rec.get("supplier_ref"), rec.get("bought_by")], ["Argos", "A99", "me@x"])
check("the time carries its zone (UTC), so the browser shows it right",
      str(rec.get("bought_at") or "").endswith("+00:00"), True)
check("no money column in what is returned", any(k in rec for k in ("paid", "cost", "price", "amount")), False)
check("another account sees nothing for the same order id", P.for_orders(_CFG, "tb_b", "UK", ["111-1"]), {})
check("an empty id list reads nothing, not the whole account", P.for_orders(_CFG, "tb_a", "UK", []), {})
bad = P.record(_CFG, "tb_a", "UK", "111-2", supplier_url="javascript:alert(1)")
check("a non-web link is dropped", (P.for_orders(_CFG, "tb_a", "UK", ["111-2"])["111-2"][0]["supplier_url"]), "")
check("refused without an order", P.record(_CFG, "tb_a", "UK", ""), 0)
check("remove with the wrong account removes nothing", P.remove(_CFG, "tb_b", "UK", "111-2", bad), 0)
check("remove with the wrong order removes nothing", P.remove(_CFG, "tb_a", "UK", "111-1", bad), 0)
check("remove with all four matching removes it", P.remove(_CFG, "tb_a", "UK", "111-2", bad), 1)

print("== attached to order rows ==")
rows = [{"order_id": "111-1", "account_id": "tb_a", "marketplace": "UK"},
        {"order_id": "111-9", "account_id": "tb_a", "marketplace": "UK"},
        {"order_id": "111-1", "account_id": "tb_b", "marketplace": "UK"},
        {"order_id": "111-1", "account_id": "", "marketplace": "UK"}]
P.attach(_CFG, rows)
check("bought order carries its record", len(rows[0]["purchases"]), 1)
check("unbought order carries an empty list", rows[1]["purchases"], [])
check("same order id on another account is not bought", rows[2]["purchases"], [])
check("a row with no account is unknown (None), never matched", rows[3]["purchases"], None)

from domain import order_attach as OA          # noqa: E402
r2 = [{"order_id": "1", "account_id": "a", "marketplace": "UK"}]


def _boom(a, m, ids):
    raise RuntimeError("no table")


OA.attach(r2, _boom, lambda r, got: r.__setitem__("x", got))
check("a failed read is None (unknown), not []", r2[0]["x"], None)

print("== tracking.attach unchanged by the shared grouping ==")
T.add(_CFG, "tb_a", "UK", "111-1", "RM123456789GB", carrier="Royal Mail")
tr = [{"order_id": "111-1", "account_id": "tb_a", "marketplace": "uk"},
      {"order_id": "111-1", "account_id": "tb_b", "marketplace": "UK"},
      {"order_id": "", "account_id": "tb_a", "marketplace": "UK"}]
T.attach(_CFG, tr)
check("tracked order gets its parcel", [p["tracking_number"] for p in tr[0]["tracking"]], ["RM123456789GB"])
check("other account: empty list, as before", tr[1]["tracking"], [])
check("unmatchable row: empty list (not None), as before", tr[2]["tracking"], [])
check("  and a summary is still set", "tracking_status" in tr[2], True)

print("== the routes ==")
import dashboard as D                          # noqa: E402
app = D.build_app()
app.config["TESTING"] = True
c = app.test_client()
r = c.post("/orders/purchase", json={"order_id": "222-1", "supplier": "X"})
check("no account named -> refused", (r.status_code, "Which account" in (r.get_json() or {}).get("error", "")), (400, True))
r = c.post("/orders/purchase", json={"account": "nope", "order_id": "222-1"})
check("an account this app does not have -> refused", r.status_code in (403, 404), True)
r = c.post("/orders/purchase", json={"account": "tb_a", "marketplace": "DE", "order_id": "222-1"})
check("a marketplace not the account's own -> refused", r.status_code, 400)
r = c.post("/orders/purchase", json={"account": "tb_a", "order_id": ""})
check("no order -> refused", r.status_code, 400)
r = c.post("/orders/purchase", json={"account": "tb_b", "marketplace": "DE", "order_id": "222-1",
                                     "supplier": "Y", "supplier_ref": "R1"})
j = r.get_json() or {}
check("named account + own marketplace -> recorded", (r.status_code, j.get("ok")), (200, True))
check("  filed under that account and marketplace", len(P.for_orders(_CFG, "tb_b", "DE", ["222-1"]).get("222-1") or []), 1)
check("  and not under the other marketplace", P.for_orders(_CFG, "tb_b", "UK", ["222-1"]), {})
r = c.post("/orders/purchase/remove", json={"account": "tb_a", "marketplace": "UK", "order_id": "222-1", "purchase_id": j.get("id")})
check("removing it through another account finds nothing", r.status_code, 404)
r = c.post("/orders/purchase/remove", json={"account": "tb_b", "marketplace": "DE", "order_id": "222-1", "purchase_id": j.get("id")})
check("removing it through its own account works", (r.get_json() or {}).get("removed"), 1)

print("== a person limited to ONE account (account-scope review) ==")
from auth import guard as G                    # noqa: E402
limited = {"id": "u_l", "role": "custom", "active": True, "permissions": ["edit"],
           "features": {"orders": "edit"}, "workspaces": ["tb_b"], "perms_version": 99}
check("the record number is not read as an account",
      G.named_workspaces("/orders/purchase/remove", {}, {"account": "tb_b", "purchase_id": 7}), ["tb_b"])
ok, why = G.check("/orders/purchase/remove", "POST", limited, {"account": "tb_b", "purchase_id": 7}, {})
check("they may remove a record on their own account", (ok, why), (True, why))
ok, _w = G.check("/orders/purchase", "POST", limited, {"account": "tb_b", "order_id": "1"}, {})
check("they may record on their own account", ok, True)
ok, _w = G.check("/orders/purchase", "POST", limited, {"account": "tb_a", "order_id": "1"}, {})
check("they may NOT record on another account", ok, False)
ok, _w = G.check("/orders/purchase/remove", "POST", limited, {"account": "tb_a", "purchase_id": 7}, {})
check("they may NOT remove on another account", ok, False)

print("== recorded as work; needs edit ==")
from domain import activity_catalog as AC      # noqa: E402
d1 = AC.match("POST", "/orders/purchase") or ()
d2 = AC.match("POST", "/orders/purchase/remove") or ()
check("recording is in the activity log", d1[3:4], ("order.purchase",))
check("removing is its own entry (not swallowed by the shorter path)", d2[3:4], ("order.purchase_remove",))
check("recording needs edit", G.required_permission("/orders/purchase", "POST"), "edit")
check("removing needs edit", G.required_permission("/orders/purchase/remove", "POST"), "edit")
check("  written down in RULES, not a fallthrough",
      [p for p, _perm in G.RULES if p.startswith("/orders/purchase")], ["/orders/purchase/remove", "/orders/purchase"])

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.stdout.flush()
os._exit(1 if fails else 0)
