"""The defects the independent review found in the first profit-agreement change.

Each section reproduces one finding from the review of commit b834412 (28 Sep
2026) and pins the fix, so it cannot come back:

  1. PPC Analytics took ad spend off twice (the Sales profit already had it off)
  2. any expense named "...subscription" stopped Amazon's own charge coming off,
     for every month, whatever it was for
  3. the Amazon account charge compared two calendars, so a July order's fee
     settled in August was charged in both months
  4. per-product charges came off the card and the P&L only -- not the Sales
     grid or the Finance rows
  5. with a product filter on, the Profit card was the account's profit minus
     that one product's ad spend
  6. Finance's settlement view dropped coupon and deal fees

Runs on its own temporary database; nothing real is read or written.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
_TMP = tempfile.mkdtemp(prefix="profit_review_")
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")
# The account's own settings -- above all its VAT rate, which the fee rate
# and every profit figure read from the account (domain/unit_profit).
# A temporary config.json, so nothing real is read.
with open(os.path.join(_TMP, "config.json"), "w") as _fh:
    _fh.write('{"accounts": []}')
os.environ["CONFIG_PATH"] = os.path.join(_TMP, "config.json")

from data import db as _db                      # noqa: E402
from domain import asin_charges as _ac          # noqa: E402
from domain import contribution as _contrib     # noqa: E402
from domain import expenses as _exp             # noqa: E402
from domain import order_profit as _op          # noqa: E402
from domain import pnl as _pnl                  # noqa: E402
from domain import ppc_analytics as _pa         # noqa: E402
from domain import sales_data as _sd            # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


conn = _db.get_db()


def ins(table, **kv):
    conn.execute("INSERT INTO %s (%s) VALUES (%s)"
                 % (table, ", ".join(kv), ",".join("?" * len(kv))), list(kv.values()))


def line(ws, oid, date, sku, asin, units, revenue, cogs):
    ins("order_lines", workspace_id=ws, marketplace="UK", order_id=oid,
        purchase_date=date + "T10:00:00Z", sku=sku, asin=asin, units=units,
        revenue=revenue, shipping=0.0, cogs=cogs, cogs_source="sku",
        status="Shipped", currency="GBP")


def settle(ws, oid, posted, ref, principal, other=0.0):
    ins("order_fees", workspace_id=ws, marketplace="UK", order_id=oid,
        posted_date=posted, referral_fees=ref, fba_fees=0.0, other_fees=other,
        principal=principal, tax=0.0, promos=0.0, currency="GBP")


print("\n1. PPC Analytics' net profit is the Sales profit, ads taken off ONCE")
W1 = "__rv1__"
ins("finance_daily", workspace_id=W1, marketplace="UK", date="2026-08-10", asin="*",
    principal=100.0, referral_fees=15.0, fba_fees=0.0, other_fees=0.0,
    units=1, cogs=30.0, cogs_units=1, currency="GBP")
ins("ads_daily", workspace_id=W1, marketplace="UK", date="2026-08-10", asin="*",
    spend=10.0)
conn.commit()
st = _sd.totals(None, W1, "UK", "2026-08-01", "2026-08-31", vat_rate=0)
check("the Sales profit: 100 - 15 fees - 30 stock - 10 ads", st.get("profit"), 45.0)
npf = _pa.net_profit(None, W1, "UK", "2026-08-01", "2026-08-31",
                     totals={"spend": 10.0})
check("PPC Analytics states the same figure", npf.get("net_profit"), 45.0)

print("\n2. only an AMAZON entry stands in for Amazon's own charge, per window")
W2 = "__rv2__"
for _d in ("2026-08-14", "2026-09-14"):
    ins("finance_daily", workspace_id=W2, marketplace="UK", date=_d, asin="*",
        other_fees=25.0, currency="GBP")
conn.commit()
_exp.add(None, W2, name="Helium 10 subscription", amount=39.0,
         starts="2026-01-01", category="Software")
ov = _exp.overhead_for(None, W2, "UK", "2026-08-01", "2026-08-31")
check("a Helium 10 subscription does not replace Amazon's 25.00",
      ov["amazon_account_charges"], 25.0)
check("and is still an own cost of its own", ov["own_costs"], 39.0)
_exp.add(None, W2, name="Amazon selling subscription", amount=25.0,
         starts="2026-09-01", category="Amazon", marketplace="UK")
ov = _exp.overhead_for(None, W2, "UK", "2026-08-01", "2026-08-31")
check("an Amazon entry starting 1 Sep changes nothing in August",
      ov["amazon_account_charges"], 25.0)
ov = _exp.overhead_for(None, W2, "UK", "2026-09-01", "2026-09-30")
check("from September it is not charged again", ov["amazon_account_charges"], 0.0)

print("\n3. an order's fee is not also an account charge in the next month")
W3 = "__rv3__"
line(W3, "J1", "2026-07-20", "S", "A", 1, 50.0, 10.0)
settle(W3, "J1", "2026-08-05", 7.5, 50.0, other=2.0)
ins("finance_daily", workspace_id=W3, marketplace="UK", date="2026-08-05", asin="*",
    principal=50.0, referral_fees=7.5, other_fees=2.0, currency="GBP")
conn.commit()
check("August finds no account-level charge -- the 2.00 belongs to order J1",
      _exp.account_level_charge(None, W3, "UK", "2026-08-01", "2026-08-31"), 0.0)
check("and July's P&L carries it in the order's fees",
      _pnl.build(None, W3, "UK", "2026-07-01", "2026-07-31", 0).get("other_fees"), 2.0)
check("while August's net profit does not take it again",
      _pnl.build(None, W3, "UK", "2026-08-01", "2026-08-31", 0).get("account_charges"),
      0.0)

print("\n4 & 5. per-product charges and the product filter, on every screen")
W4 = "__rv4__"
line(W4, "P1", "2026-08-05", "SA", "A1", 1, 100.0, 30.0)
line(W4, "P2", "2026-08-06", "SB", "B1", 1, 60.0, 20.0)
settle(W4, "P1", "2026-08-15", 15.0, 100.0)
settle(W4, "P2", "2026-08-16", 9.0, 60.0)
_ac.save(None, W4, "UK", "A1", "Prep", 5.0, effective_from="2026-01-01")
conn.commit()
S, E = "2026-08-01", "2026-08-12"
card = _op.for_period(None, W4, "UK", S, E, vat_rate=0)
# 160 - fees 24 - stock 50 - prep 5 = 81
check("the card takes the 5.00 prep off", card.get("profit"), 81.0)
check("the P&L the same", _pnl.build(None, W4, "UK", S, E, 0).get("profit_before_own_costs"),
      81.0)
rows, tot = _contrib.by_product_orders(None, W4, "UK", S, E, vat_rate=0)
check("the Finance product rows add up to the same", tot.get("contribution"), 81.0)
check("  and A1's row carries its charge", {r["asin"]: r for r in rows}["A1"]["charges"], 5.0)
g = _sd.series(None, W4, "UK", S, E, vat_rate=0, basis="order")
check("the Sales grid's total the same", _sd.aggregate(g, "profit"), 81.0)
one = _op.for_period(None, W4, "UK", S, E, vat_rate=0, asin="A1")
# A1 only: 100 - 15 - 30 - 5 = 50
check("filtered to A1, the card is A1's own figure", one.get("profit"), 50.0)
check("  over A1's own sales", one.get("revenue"), 100.0)

print("\n6. Finance's settlement view takes coupon and deal fees off")
W6 = "__rv6__"
ins("finance_daily", workspace_id=W6, marketplace="UK", date="2026-08-10", asin="C1",
    principal=40.0, referral_fees=6.0, fba_fees=0.0, other_fees=0.0,
    promo_fees=2.0, units=1, cogs=10.0, cogs_units=1, currency="GBP")
conn.commit()
srows, _st = _contrib.by_product(None, W6, "UK", "2026-08-01", "2026-08-31",
                                 vat_rate=0)
check("the coupon fee is in the product's fees", srows[0]["fees"], 8.0)
check("and so off its contribution: 40 - 8 - 10", srows[0]["contribution"], 22.0)

print("\n--- the second review (of the per-product change) ---")

print("\n7. US sales tax is not part of the fee base")
W7 = "__rv7__"          # not VAT-registered (no rate in the account config)
ins("finance_daily", workspace_id=W7, marketplace="US", date="2026-08-10", asin="*",
    principal=1000.0, tax=70.0, referral_fees=150.0, fba_fees=0.0, other_fees=0.0,
    currency="USD")
conn.commit()
_r7, _b7, _d7 = _op.fee_rate(None, W7, "US", "2026-09-01")
check("150 of fees on 1000 of sales is 15%, sales tax left out", round(_r7, 4), 0.15)

print("\n8. a product's own rate counts the postage its buyers paid")
from domain import amazon_fees as _af                                  # noqa: E402
W8 = "__rv8__"
for i in (1, 2, 3):
    oid = "Q%d" % i
    ins("order_lines", workspace_id=W8, marketplace="UK", order_id=oid,
        purchase_date="2026-08-0%dT10:00:00Z" % i, sku="SQ", asin="B0POST0001",
        units=1, revenue=20.0, shipping=4.0, cogs=8.0, status="Shipped",
        currency="GBP")
    settle(W8, oid, "2026-08-1%d" % i, 3.60, 24.0)
conn.commit()
bd8 = _af.breakdown_for(None, W8, "UK", "B0POST0001", 24.0, sku="SQ")
check("3.60 on 24.00 paid is 15%, so 24.00 is charged 3.60", bd8["total"], 3.6)

print("\n9. an 'Amazon PPC' cost is not Amazon's account charge")
W9 = "__rv9__"
ins("finance_daily", workspace_id=W9, marketplace="UK", date="2026-08-14", asin="*",
    other_fees=30.0, currency="GBP")
conn.commit()
_exp.add(None, W9, name="Amazon PPC (manual)", amount=120.0, starts="2026-01-01")
check("the 30.00 subscription still comes off",
      _exp.overhead_for(None, W9, "UK", "2026-08-01", "2026-08-31")
      ["amazon_account_charges"], 30.0)

print("\n10. the settled history is read once, and again the moment it changes")
_a = _af._settled_orders(None, W8, "UK")
check("asked twice, the same answer is reused",
      _af._settled_orders(None, W8, "UK") is _a, True)
line(W8, "Q9", "2026-08-09", "SQ", "B0POST0001", 1, 20.0, 8.0)
settle(W8, "Q9", "2026-08-19", 3.0, 20.0)
conn.commit()
check("a new settlement is seen at once",
      len(_af._settled_orders(None, W8, "UK")[0]), len(_a[0]) + 1)

print("\n11. the cost editor asks the one per-unit answer")
_CR = open(os.path.join(HERE, "routes", "cogs_routes.py"), encoding="utf-8").read()
check("it calls unit_profit.at_price, not the flat-15% estimate",
      "_up.at_price(" in _CR and "_estimate_profit(b.get" not in _CR, True)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
