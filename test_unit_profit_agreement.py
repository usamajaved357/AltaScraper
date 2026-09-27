"""One listing, one price: every screen that states what a unit earns agrees.

Measured 27 Sep 2026, a listing's profit was worked out four ways:

    the price editor        Amazon's fee on the price, VAT left IN the profit,
                            skipping what Amazon actually took on this product
    the Live rows           a flat 15%, VAT left in (dashboard._estimate_profit)
    the cost editor         the same flat 15%
    the repricer            the three-tier fee, VAT left in its break-even too

and an order's profit on the Orders screen left VAT in as well. Now they share
domain/unit_profit.at_price and listing/pricing.achieved, the account's fee
rate is measured over what buyers PAID (the base Amazon charges on), and VAT
comes out at the account's setting.

Runs on its own temporary database; nothing real is read or written.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
_TMP = tempfile.mkdtemp(prefix="unit_profit_")
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")

from data import db as _db                      # noqa: E402
from domain import amazon_fees as _af           # noqa: E402
from domain import order_profit as _op          # noqa: E402
from domain import orders_view as _ov           # noqa: E402
from domain import sourcing as _src             # noqa: E402
from domain import unit_profit as _up           # noqa: E402
from listing import pricing as _pricing         # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


conn = _db.get_db()
WS, MKT, VAT = "__unit__", "UK", 0.2


def ins(table, **kv):
    conn.execute("INSERT INTO %s (%s) VALUES (%s)"
                 % (table, ", ".join(kv), ",".join("?" * len(kv))), list(kv.values()))


print("\nthe account's fee rate is a share of what buyers PAID")
# jack_uk's own settled figures: 70.42 of fees on 402.39 of principal, with
# 80.47 of VAT itemised beside it.
ins("finance_daily", workspace_id=WS, marketplace=MKT, date="2026-08-14", asin="*",
    principal=402.39, tax=80.47, referral_fees=70.42, fba_fees=0.0, other_fees=0.0,
    currency="GBP")
conn.commit()
rate, basis, _d = _op.fee_rate(None, WS, MKT, "2026-09-01")
check("70.42 of 482.86 -- 14.58%, not 17.5% of the principal alone",
      round(rate, 4), round(70.42 / 482.86, 4))

print("\none listing at 29.99 costing 10.00, on a VAT-registered account")
P, C = 29.99, 10.0
u = _up.at_price(None, WS, MKT, "SKU1", "B0UNIT0001", P, C, vat_rate=VAT)
fee = round(P * rate, 2)
vat = round(P - P / 1.2, 2)
want = round(P / 1.2 - fee - C, 2)
check("VAT comes out: 29.99 includes 5.00 of it", u["vat"], vat)
check("Amazon's fee at this account's measured rate", u["fees_total"], fee)
check("what the unit earns: 24.99 - fee - 10.00", u["profit"], want)
check("margin over the price after VAT", u["margin_pct"],
      round(want / (P / 1.2) * 100, 1))

print("\nthe other screens say the same")
est = _up.as_estimate(u)
check("the Live row and the cost editor", est["net"], want)
got = _pricing.achieved(P, C, rate, vat_rate=VAT)
check("the repricer's arithmetic", got["profit"], want)
rule = _src.rule_with_defaults({"referral_rate": rate, "vat_rate": VAT})
check("the repricer's price breakdown",
      _src.target_status(P, C, dict(rule, target_roi_pct=1.0))["profit"], want)
items = [{"sku": "SKU1", "qty": 1, "price": P}]
op, om, _n = _ov.profit_for(items, P, lambda s: (C, "sku"), referral_rate=rate,
                            vat_rate=VAT)
check("an order of one on the Orders screen", op, want)

print("\nthe repricer's break-even now covers the VAT")
floor = _pricing.floor_from_rate(C, rate, vat_rate=VAT)
be = _pricing.achieved(floor, C, rate, vat_rate=VAT)
check("at its break-even price the unit makes nothing, not minus the VAT",
      abs(be["profit"]) <= 0.01, True)
old = _pricing.floor_from_rate(C, rate)
check("the old floor, VAT ignored, loses money once VAT is paid",
      _pricing.achieved(old, C, rate, vat_rate=VAT)["profit"] < -0.5, True)
t = _pricing.floor_from_target(C, rate, "margin", 20, vat_rate=VAT)
check("a 20% margin target is met on the price after VAT",
      abs(_pricing.achieved(t, C, rate, vat_rate=VAT)["margin_pct"] - 20.0) <= 0.1,
      True)
r = _pricing.floor_from_target(C, rate, "roi", 20, vat_rate=VAT)
check("a 20% ROI target is met",
      abs(_pricing.achieved(r, C, rate, vat_rate=VAT)["roi_pct"] - 20.0) <= 0.1, True)

print("\nwithout VAT nothing moves")
check("achieved is unchanged", _pricing.achieved(P, C, 0.15)["profit"],
      round(P - P * 0.15 - C, 2))
check("the floor is unchanged", _pricing.floor_from_rate(C, 0.15),
      _pricing._round_up(C / 0.85))

print("\nthe first tier reaches the price editor")
# Two settled single-line orders for SKU2: Amazon took 4.50 on each 29.99 --
# 15.0% of what the buyer paid, this product's own rate.
for i in (1, 2):
    oid = "T%d" % i
    ins("order_lines", workspace_id=WS, marketplace=MKT, order_id=oid,
        purchase_date="2026-08-0%dT10:00:00Z" % i, sku="SKU2", asin="B0UNIT0002",
        units=1, revenue=29.99, shipping=0.0, cogs=10.0, status="Shipped",
        currency="GBP")
    ins("order_fees", workspace_id=WS, marketplace=MKT, order_id=oid,
        posted_date="2026-08-1%d" % i, referral_fees=4.50, fba_fees=0.0,
        other_fees=0.0, principal=24.99, tax=5.00, promos=0.0, currency="GBP")
conn.commit()
bd = _af.breakdown_for(None, WS, MKT, "B0UNIT0002", 29.99, sku="SKU2")
check("breakdown_for finds what Amazon actually took on this product",
      bd["basis"], _af.ACTUAL)
check("  and charges that", bd["total"], 4.5)

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
