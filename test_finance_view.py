"""The Finance screen's "vs previous" and overhead panels (architecture batch A8).

Both moved word for word from routes/finance_routes.py into
domain/finance_view.py. A full JSON snapshot of /finance/contribution on this
fixture was identical before and after the move (29 Sep 2026); these are the
figures it showed, pinned through the route so the wiring is covered too.
"""
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import os, sys, json, tempfile
sys.path.insert(0, _REPO)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


TMP = tempfile.mkdtemp(prefix="altafinview_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "ws1", "label": "WS One", "vat_rate": 0.2}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "v.db")

from data import db as _db
c = _db.get_db(CFG)
for d, a, p in (("2026-07-10", "B01", 20.0), ("2026-07-20", "B02", 30.0),
                ("2026-08-05", "B01", 25.0), ("2026-08-06", "*", 0.0)):
    c.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, referral_fees, "
              "fba_fees, other_fees, refunds, refund_units, reimbursements, promos, principal, "
              "units, cogs, cogs_units, currency, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ("ws1", "UK", d, a, 1.5, 2.0, 0.3, 0.0, 0, 0.0, 0.0, p, 1, 4.0, 1, "GBP", "t"))
c.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, units, ordered_sales, "
          "currency) VALUES ('ws1','UK','2026-08-05','B01',1,25.0,'GBP')")
c.commit()

from flask import Flask
import routes.finance_routes as fr
app = Flask(__name__); app.secret_key = "t"
fr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {}, _state={})
cl = app.test_client()
j = cl.get("/finance/contribution?account=ws1&marketplace=UK"
           "&start=2026-08-01&end=2026-08-31&basis=settlement").get_json() or {}

print("=== the previous window ===")
p = j.get("previous") or {}
check("is the same length, just before", (p.get("start"), p.get("end")),
      ("2026-07-01", "2026-07-31"))
check("  its contribution", p.get("contribution"), 26.07)
check("  its products", p.get("products"), 2)
b = cl.get("/finance/contribution?account=ws1&marketplace=UK"
           "&start=bad&end=2026-08-31&basis=settlement").get_json() or {}
check("an unreadable date: no previous window", b.get("previous"), None)

print("=== the overhead ===")
o = j.get("overhead") or {}
check("the charge that belongs to no order", [(i["label"], i["amount"]) for i in o.get("items", [])],
      [("Amazon charges that belong to no order", 0.3), ("Your own costs", None)])
check("  total", o.get("total"), 0.3)
check("  contribution and net profit", (o.get("contribution"), o.get("net_profit")), (13.03, 12.73))

print("=== on the order calendar, from the account's figure ===")
oj = cl.get("/finance/contribution?account=ws1&marketplace=UK"
            "&start=2026-08-01&end=2026-08-31&basis=orders").get_json() or {}
oo = oj.get("overhead") or {}
check("contribution is the account's figure", oo.get("contribution"),
      (oj.get("totals") or {}).get("account_contribution"))
check("  the overhead is the same on both calendars", oo.get("total"), o.get("total"))

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nthe Finance panels are unchanged")
