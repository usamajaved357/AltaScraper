"""The P&L grid must be readable ACROSS a row.

THE REPORT: "the p&l heatmap do not seems to be telling the truth ... revenue
after vat and other things they are not seems to be accurate".

It was telling two truths at once. Sales were dated by when the order was
PLACED and every settled figure by when the MONEY MOVED, and Amazon settles ten
to twelve days later -- so on jack_uk every money row fell on Jul 22 to Aug 12
and every sales row on Aug 14, and NO DAY carried both. Any arithmetic across a
row was meaningless.

Amazon names the order on each fee (measured: 13 of 13 shipment events, 1 of 1
refunds), so every fee can be reported on the day its order was placed. Orders
Amazon has not settled yet get their fee ESTIMATED at the rate this account
actually pays -- which is Orbit's rule as well: "Finances API basis when final,
else estimate on order date".

Amazon is stood in for. What is being tested is the shape of the answer.
"""
import os, sys, json, tempfile, shutil
import datetime as dt

sys.path.insert(0, r"D:\AltaScraper")

from data import db as _db
from domain import sales_data as _sd
from domain import order_finance as _of
import domain.live_reconcile as _lr

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altapnl_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "acct", "vat_rate": 0.2,
                         "marketplaces": ["UK"]}]}, open(CFG, "w"))
WS, MKT = "acct", "UK"
conn = _db.get_db(CFG)

TODAY = dt.date.today()
D = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()

# Two orders on the SAME day. One Amazon has settled; one it has not.
for oid, day, gross, cogs in (("SETTLED-1", D(20), 36.00, 8.0),
                              ("PENDING-1", D(20), 36.00, 8.0)):
    conn.execute(
        "INSERT INTO order_lines (workspace_id, marketplace, order_id,"
        " purchase_date, asin, sku, units, revenue, shipping, cogs, status) "
        "VALUES (?,?,?,?,?,?,1,?,0,?,'Shipped')",
        (WS, MKT, oid, day + "T12:00:00Z", "B0TEST", "8.00_3Days_B0TEST",
         gross, cogs))
conn.commit()

# The settled one: Amazon took its cut, and posted it TEN DAYS LATER.
_of.store(CFG, WS, MKT, [{
    "order_id": "SETTLED-1", "posted_date": D(10),
    "referral_fees": 4.50, "fba_fees": 0.0, "other_fees": 0.0,
    "principal": 30.00, "tax": 6.00, "refunds": 0.0, "refund_tax": 0.0,
    "refund_units": 0, "refund_fees_returned": 0.0, "promos": 0.0,
    "units": 1, "currency": "GBP",
}])

print("\n== the fee is reported on the ORDER's day, not the payment day ==")
by = _of.by_order_date(CFG, WS, MKT, D(30), D(0))
check("the settled fee lands on the order's date", D(20) in by, True)
check("  and NOT on the day the money moved", D(10) in by, False)
check("  with Amazon's own figure", by[D(20)]["referral_fees"], 4.5)

print("\n== an unsettled order is estimated, not left out ==")
full = _of.complete_by_order_date(CFG, WS, MKT, D(30), D(0),
                                  fee_rate=0.15, vat_rate=0.2)
day = full[D(20)]
check("both orders are counted", day["units"], 2)
check("one settled, one estimated", (day["orders_settled"], day["orders_estimated"]),
      (1, 1))
check_true("the estimate is declared", day["fees_estimated"] > 0)
# settled principal 30.00 + estimated 36.00/1.2 = 30.00
check("the ex-VAT money covers BOTH orders", day["principal"], 60.0)
check("  and the VAT with it", day["tax"], 12.0)
check("the cost of both is counted", day["cogs"], 16.0)
check("  and both units are costed", day["cogs_units"], 2)

print("\n== so the day can be read across ==")
_lr.from_lines(CFG, WS, MKT, D(30), D(0))
rows = _sd.series(CFG, WS, MKT, D(30), D(0), vat_rate=0.2, basis="order")
row = next((r for r in rows if r["date"] == D(20)), None)
check_true("the day exists in the series", row is not None)
check("sales and money are on the SAME day",
      bool(row.get("ordered_sales")) and bool(row.get("principal")), True)
check("ex-VAT + VAT = what the buyer paid",
      round(float(row["principal"]) + float(row["tax"]), 2),
      round(float(row["ordered_sales"]), 2))
check("Revenue after VAT is the ex-VAT figure",
      float(row["net_revenue"]), float(row["principal"]))

fees = float(row["total_fees"])
expect_np = round(float(row["net_revenue"]) - fees, 2)
check("net proceeds = revenue - fees", float(row["net_proceeds"]), expect_np)
check("profit = net proceeds - cost", float(row["profit"]),
      round(expect_np - float(row["cogs"]), 2))
check_true("and profit does not exceed the sales",
           float(row["profit"]) <= float(row["ordered_sales"]))

print("\n== on the MONEY basis the old view is unchanged ==")
m = _sd.series(CFG, WS, MKT, D(30), D(0), vat_rate=0.2, basis="money")
mrow = next((r for r in m if r["date"] == D(10)), None)
check("the settled money still appears on its payment day", mrow is not None, True)

print("\n== percentages are not rounded into oblivion ==")
# 2 units in 500 sessions is 0.4%, and used to round to 0.0 and vanish.
check("a small conversion survives", _sd._pct(2, 500), 0.4)
check("  and is not inflated either", _sd._pct(9, 513), 1.75)
check("a fee rate keeps its decimal", _sd._pct(71.83, 402.39), 17.85)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
