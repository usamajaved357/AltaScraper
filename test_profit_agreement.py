"""Every screen that states a profit for a window must state THE SAME profit.

Measured on 27 Sep 2026 against a copy of the real data, for one account and one
month, the app gave four different answers for the same seven units:

    Sales Profit card   64.70  (31.3%)      Sales P&L    80.76  (36.9%)
    Sales grid          64.43  (31.2%)      Finance      50.19  (22.5%)

and on nestwell_goods the card and P&L counted 23 uncosted units as free while
the grid and Finance hid the figure. Each screen did its own arithmetic. This
test builds one small account by hand, works out the answer on paper, and
checks every screen against that one answer.

The rules it pins, each the owner's (see active/plan-profit-accuracy.md):
  * VAT comes out at the account's own setting, on every screen (D1, 28 Sep)
  * refunds count on the day the money went back, never re-dated to the order
    ("July's profit stays locked. September's refund hits September's P&L.")
  * an uncosted unit is SHOWN, not hidden, with a warning that the figure is
    too high ("if no cogs are added show profit as wrong ... the user should
    know he needs to add cogs")
  * margin is profit over sales after VAT
  * all measured ad spend comes off the headline, including spend no product
    can be matched to

Runs on its own temporary database; nothing real is read or written.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
_TMP = tempfile.mkdtemp(prefix="profit_agree_")
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "t.db")

from data import db as _db                      # noqa: E402
from domain import order_profit as _op          # noqa: E402
from domain import pnl as _pnl                  # noqa: E402
from domain import contribution as _contrib     # noqa: E402
from domain import order_finance as _of         # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT, VAT = "__agree__", "UK", 0.2
conn = _db.get_db()


def ins(table, **kv):
    conn.execute("INSERT INTO %s (%s) VALUES (%s)"
                 % (table, ", ".join(kv), ",".join("?" * len(kv))), list(kv.values()))


def line(oid, date, sku, asin, units, revenue, shipping, cogs, status="Shipped"):
    ins("order_lines", workspace_id=WS, marketplace=MKT, order_id=oid,
        purchase_date=date + "T10:00:00Z", sku=sku, asin=asin, units=units,
        revenue=revenue, shipping=shipping, cogs=cogs,
        cogs_source=(None if cogs is None else "sku"), status=status, currency="GBP")


# ---- the fee rate this account pays, measured from July -----------------
# 180.00 of fees on 1000.00 of principal with 200.00 of VAT itemised beside it:
# 15% of what buyers paid (18% of the principal alone). The rate is a share of
# the VAT-INCLUSIVE price, the base Amazon charges its fee on.
ins("finance_daily", workspace_id=WS, marketplace=MKT, date="2026-07-01", asin="*",
    principal=1000.0, tax=200.0, referral_fees=180.0, fba_fees=0.0, other_fees=0.0,
    currency="GBP")

# ---- orders placed in August ---------------------------------------------
# O1: one product, postage paid, SETTLED. Amazon itemised 20.00 of VAT.
line("O1", "2026-08-05", "SA", "A1", 1, 100.0, 20.0, 30.0)
ins("order_fees", workspace_id=WS, marketplace=MKT, order_id="O1",
    posted_date="2026-08-15", referral_fees=15.0, fba_fees=0.0, other_fees=1.0,
    promo_fees=2.0, principal=100.0, tax=20.0, promos=5.0, currency="GBP")
# O2: TWO products in one order, SETTLED. The order's 18.00 fee must be split
# between them, not charged to each in full.
line("O2", "2026-08-10", "SA", "A1", 1, 60.0, 0.0, 30.0)
line("O2", "2026-08-10", "SB", "B1", 1, 60.0, 0.0, 20.0)
ins("order_fees", workspace_id=WS, marketplace=MKT, order_id="O2",
    posted_date="2026-08-20", referral_fees=18.0, fba_fees=0.0, other_fees=0.0,
    principal=100.0, tax=20.0, promos=0.0, currency="GBP")
# O3: NOT settled, and nobody has entered a cost for B1.
line("O3", "2026-08-20", "SB", "B1", 2, 96.0, 0.0, None)
# O4: cancelled. Not a sale.
line("O4", "2026-08-22", "SA", "A1", 5, 500.0, 0.0, 30.0, status="Canceled")

# ---- refunds, on the day the money went back -----------------------------
# 25 Aug: a refund on a JULY order. It belongs to August.
for a in ("*", "A1"):
    ins("finance_daily", workspace_id=WS, marketplace=MKT, date="2026-08-25", asin=a,
        refunds=24.0, refund_units=1, refund_fees_returned=3.0, reimbursements=4.0,
        currency="GBP")
# 2 Sep: a refund on O1, an AUGUST order. It belongs to September.
ins("order_fees", workspace_id=WS, marketplace=MKT, order_id="O1",
    posted_date="2026-09-02", refunds=12.0, refund_units=1, currency="GBP")
for a in ("*", "A1"):
    ins("finance_daily", workspace_id=WS, marketplace=MKT, date="2026-09-02", asin=a,
        refunds=12.0, refund_units=1, currency="GBP")

# ---- advertising: 10.00 on the account, 7.00 of it matched to A1 ---------
ins("ads_daily", workspace_id=WS, marketplace=MKT, date="2026-08-12", asin="*", spend=10.0)
ins("ads_daily", workspace_id=WS, marketplace=MKT, date="2026-08-12", asin="A1", spend=7.0)
conn.commit()

# ---- the answer, worked out on paper --------------------------------------
#   sales charged to buyers  120 + 120 + 96                      = 336.00
#   VAT                      20 (Amazon) + 20 (Amazon) + 96/6    =  56.00
#   sales after VAT                                              = 280.00
#   Amazon fees   O1 15+1+2 (coupon fee)  O2 18  O3 96 x 15%     =  50.40
#   promotions you funded (O1)                                   =   5.00
#   refunds in August (the July order's), less fee returned 3,
#     plus a reimbursement of 4                                  =  17.00
#   stock: O1 30, O2 30+20, O3 unknown (2 units)                 =  80.00
#   advertising                                                  =  10.00
#   profit = 280 - 50.40 - 5 - 24 + 3 + 4 - 80 - 10              = 117.60
#   margin = 117.60 / 280                                        =  42.0%
START, END = "2026-08-01", "2026-08-31"
PROFIT, MARGIN = 117.6, 42.0

print("\nthe Sales Profit card (order_profit.for_period)")
card = _op.for_period(None, WS, MKT, START, END, vat_rate=VAT,
                      ads_connected=True, ad_spend=10.0)
check("profit", card.get("profit"), PROFIT)
check("margin is profit over sales after VAT", card.get("margin_pct"), MARGIN)
check("VAT comes out at the account's rate / Amazon's own figure", card.get("vat"), 56.0)
check("sales after VAT", card.get("net_revenue"), 280.0)
check("Amazon fees: settled where settled, 15% where not, coupon fee included",
      card.get("fees"), 50.4)
check("refunds are August's by refund date, not the order's", card.get("refunds"), 24.0)
check("the cancelled order is not a sale", card.get("revenue"), 336.0)
check("uncosted units are counted", card.get("missing_units"), 2)
truthy("and the figure SAYS it is too high", "HIGHER" in (card.get("warning") or ""))

print("\nthe Sales P&L statement (pnl.build)")
pl = _pnl.build(None, WS, MKT, START, END, VAT)
check("profit before your own costs is the card's figure",
      pl.get("profit_before_own_costs"), PROFIT)
check("net profit with no own costs recorded is the same figure", pl.get("profit"), PROFIT)
check("margin", pl.get("margin_pct"), MARGIN)
check("VAT is TAKEN OUT, at the account's setting (D1)",
      (pl.get("vat") or {}).get("amount"), 56.0)
check("refunds sit on their own date", pl.get("refunds"), 24.0)
check("coupons you funded are subtracted", pl.get("promos"), 5.0)
check("advertising", pl.get("ad_spend"), 10.0)

print("\nthe Finance screen (contribution.by_product_orders)")
rows, tot = _contrib.by_product_orders(None, WS, MKT, START, END, vat_rate=VAT)
by = {r["asin"]: r for r in rows}
check("revenue includes the postage the buyer paid, like Sales", tot.get("revenue"), 336.0)
check("VAT across the products", tot.get("vat"), 56.0)
check("fees across the products add up to the account's, split per order",
      tot.get("fees"), 50.4)
check("B1 carries half of O2's fee, not all of it, plus its estimate",
      (by.get("B1") or {}).get("fees"), round(18.0 / 2 + 96.0 * 0.15, 2))
truthy("B1 is SHOWN despite its uncosted units",
       (by.get("B1") or {}).get("contribution") is not None)
check("and says how many units have no cost", (by.get("B1") or {}).get("uncosted_units"), 2)
check("ad spend no product can be matched to is carried",
      tot.get("unattributed_ad_spend"), 3.0)
check("the account's figure is the card's figure",
      tot.get("account_contribution"), PROFIT)
check("margin is over sales after VAT", tot.get("margin_pct"),
      (round(tot["contribution"] / tot["net_revenue"] * 100, 2) if tot.get("contribution") is not None and tot.get("net_revenue") else "n/a"))

print("\nthe order-calendar money every screen draws on")
money = _of.complete_by_order_date(None, WS, MKT, START, END, fee_rate=0.15,
                                   vat_rate=VAT)
check("August's refunds are the 24.00 paid on 25 Aug",
      round(sum(d.get("refunds") or 0 for d in money.values()), 2), 24.0)
check("and they sit on 25 Aug", (money.get("2026-08-25") or {}).get("refunds"), 24.0)
check("the reimbursement is carried, on its own date",
      (money.get("2026-08-25") or {}).get("reimbursements"), 4.0)

print("\nthe Sales grid's Profit row, over a window where every unit is costed")
# 1-12 Aug: O1 and O2 only. 200 after VAT - fees 36 - coupon 5 - stock 80 -
# advertising 10 = 69.00. The grid withholds a figure while any unit in it is
# uncosted (a cell has nowhere to put the warning), so it is compared here.
from domain import sales_data as _sd                                  # noqa: E402
g_rows = _sd.series(None, WS, MKT, "2026-08-01", "2026-08-12", vat_rate=VAT,
                    basis="order")
g_card = _op.for_period(None, WS, MKT, "2026-08-01", "2026-08-12",
                        vat_rate=VAT, ads_connected=True, ad_spend=10.0)
check("the card", g_card.get("profit"), 69.0)
check("the grid's total is the card's figure", _sd.aggregate(g_rows, "profit"), 69.0)
check("and so is its margin", _sd.aggregate(g_rows, "margin_pct"), 34.5)

print("\nSeptember gets September's refund, even though the order was August's")
sep = _op.for_period(None, WS, MKT, "2026-09-01", "2026-09-30", vat_rate=VAT)
check("refund", sep.get("refunds"), 12.0)
check("so September shows a loss of exactly that", sep.get("profit"), -12.0)

print("\nan account with no VAT rate set")
nov = _op.for_period(None, WS, MKT, START, END, vat_rate=None,
                     ads_connected=True, ad_spend=10.0)
check("the unsettled order's VAT is not known, so the basis says unknown",
      nov.get("vat_basis"), "unknown")
check("the P&L says the same", (_pnl.build(None, WS, MKT, START, END, None)
                                .get("vat") or {}).get("basis"), "unknown")

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
