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

print("\n== the WHOLE SCREEN is on that calendar, not just the grid ==")
# THE REPORT: "it says i have 0 ordered product sales on 8/09 but Revenue after
# VAT 18.32 ... most of the numbers are incorrect here".
#
# Four places each decided the calendar for themselves: the route defaulted to
# money, the chart guessed from whether any order was non-zero, the grid asked
# for order but only when it had its own period, and the profit card took a
# fifth route. So one screen ran two calendars at once.
check("the route defaults to the ORDER calendar",
      _sd.series(CFG, WS, MKT, D(30), D(0), vat_rate=0.2, basis="order") is not None,
      True)
_meta = {}
_t = _sd.totals(CFG, WS, MKT, D(30), D(0), vat_rate=0.2, basis="order", meta=_meta)
check("the CARDS take the same calendar as the grid", _meta.get("basis"), "order")
_g = _sd.series(CFG, WS, MKT, D(30), D(0), vat_rate=0.2, basis="order")
check("  and are the sum of the very rows it draws",
      _t["ordered_sales"],
      round(sum(float(r["ordered_sales"]) for r in _g if r.get("ordered_sales")), 2))

# A product filter cannot be re-dated -- one fee covers every product in the
# order -- so it must SAY it fell back rather than mislabel the money view.
_m2 = {}
_sd.series(CFG, WS, MKT, D(30), D(0), asin="B0TEST", vat_rate=0.2,
           basis="order", meta=_m2)
check("a product filter reports the calendar it actually used", _m2.get("basis"), "money")

print("\n== a zero means 'no orders', never 'we were not looking' ==")
# THE HAZARD: from_lines wrote a zero for every day in the window, including
# days BEFORE the order history begins. Asking for year-to-date therefore
# erased every month the history does not cover, and year-to-date then read
# exactly the same as ninety days.
_before = (TODAY - dt.timedelta(days=300)).isoformat()
conn.execute(
    "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, orders,"
    " units, ordered_sales, currency) VALUES (?,?,?,'*',4,4,222.22,'GBP')",
    (WS, MKT, _before))
conn.commit()
res = _lr.from_lines(CFG, WS, MKT, _before, D(0))
check("the rewrite starts where the order history starts",
      res.get("history_starts"), D(20))
kept = conn.execute(
    "SELECT ordered_sales FROM sales_daily WHERE workspace_id=? AND date=? "
    "AND asin='*'", (WS, _before)).fetchone()
check("a day older than the history keeps the report's own figure",
      float(kept[0]), 222.22)

print("\n== fees that cannot be re-dated are kept, not dropped ==")
# A hole is worse than the wrong calendar: a period with sales and no fees
# shows profit equal to revenue, which flatters by exactly Amazon's cut.
_m3 = {}
_old = (TODAY - dt.timedelta(days=290)).isoformat()
# Settled money on the MONEY calendar, from an order far older than anything in
# order_lines -- so it can never be re-dated. This is the real shape of the
# hazard: Amazon has told us what it took, and the order that caused it is
# beyond the horizon this app fetches.
from domain import finance_data as _fd_test
_fd_test.store(CFG, WS, MKT, [{
    "date": _old, "asin": "*", "currency": "GBP",
    "principal": 50.00, "tax": 10.00,
    "referral_fees": 9.99, "fba_fees": 0.0, "other_fees": 0.0,
    "refunds": 0.0, "refund_tax": 0.0, "refund_units": 0,
    "refund_fees_returned": 0.0, "promos": 0.0, "reimbursements": 0.0,
    "units": 1, "cogs": 0.0, "cogs_units": 0,
}])
_rows = _sd.series(CFG, WS, MKT, _old, (TODAY - dt.timedelta(days=280)).isoformat(),
                   vat_rate=0.2, basis="order", meta=_m3)
_fee_days = [r for r in _rows if r.get("total_fees")]
check_true("the fee is still reported somewhere", _fee_days)
check("and the screen is told which calendar that is", _m3.get("basis"), "money")
check_true("with a reason given", _m3.get("basis_note"))

print("\n== VAT is asked about PER ORDER, because Amazon answers per order ==")
# THE REPORT: "revenue after vat and other things they are not seems to be
# accurate".
#
# Amazon does not always itemise the VAT. Where it collects the tax it sends a
# Tax line and the Principal beside it is NET; where the seller accounts for
# the VAT themselves it sends NO tax line and the Principal is the whole price
# the buyer paid. Both shapes arrive on the SAME DAY -- measured on
# selvora_limited, 28 July: 15 of 17 orders with no tax line and 2 with one.
#
# Taking the day's total as reported called 601.08 "Charged to buyers (ex VAT)"
# when 88.76 of it was VAT that had never been taken out.
for oid, gross, pr, tx in (("VAT-SHOWN", 36.00, 30.00, 6.00),   # Amazon itemised
                           ("VAT-HIDDEN", 36.00, 36.00, 0.0)):  # Amazon did not
    conn.execute(
        "INSERT INTO order_lines (workspace_id, marketplace, order_id,"
        " purchase_date, asin, sku, units, revenue, shipping, cogs, status) "
        "VALUES (?,?,?,?,?,?,1,?,0,4.0,'Shipped')",
        (WS, MKT, oid, D(40) + "T09:00:00Z", "B0VAT", "8.00_3Days_B0VAT", gross))
    _of.store(CFG, WS, MKT, [{
        "order_id": oid, "posted_date": D(30),
        "referral_fees": 5.40, "fba_fees": 0.0, "other_fees": 0.0,
        "principal": pr, "tax": tx, "refunds": 0.0, "refund_tax": 0.0,
        "refund_units": 0, "refund_fees_returned": 0.0, "promos": 0.0,
        "units": 1, "currency": "GBP",
    }])
conn.commit()
v = _of.complete_by_order_date(CFG, WS, MKT, D(40), D(40),
                               fee_rate=0.15, vat_rate=0.2)[D(40)]
# 30.00 net as reported, plus 36.00 gross split into 30.00 + 6.00 -> 60.00 net
check("the order Amazon itemised is taken as reported, and the one it did not "
      "is split", v["principal"], 60.0)
check("  so the VAT covers BOTH orders, not just the itemised one", v["tax"], 12.0)
check("  and the day says how much of that it worked out itself",
      v["vat_derived"], 6.0)
check("  on how many orders", v["orders_vat_derived"], 1)
check("ex-VAT + VAT comes back to what the buyers paid",
      round(v["principal"] + v["tax"], 2), 72.0)

# An account that is NOT VAT-registered must have nothing taken out.
n = _of.complete_by_order_date(CFG, WS, MKT, D(40), D(40),
                               fee_rate=0.15, vat_rate=0)[D(40)]
check("a business not registered for VAT has none deducted", n["principal"], 66.0)
check("  and nothing is invented", n["vat_derived"], 0.0)

print("\n== where Amazon's own two feeds disagree, the screen says so ==")
# Both figures come from Amazon and neither can be derived from the other, so
# nothing adjusts one to fit. What must not happen is silence: showing
# 601.08 + 15.80 under a sales row of 605.77 and leaving it to be noticed reads
# as a fault in the app rather than a fact about the data.
conn.execute(
    "INSERT INTO order_lines (workspace_id, marketplace, order_id, purchase_date,"
    " asin, sku, units, revenue, shipping, cogs, status) "
    "VALUES (?,?,?,?,?,?,1,?,0,3.0,'Shipped')",
    (WS, MKT, "MISMATCH-1", D(45) + "T09:00:00Z", "B0GAP", "8.00_3Days_B0GAP", 30.00))
conn.commit()
# Amazon settles it at a different total from the one its Orders feed gave.
_of.store(CFG, WS, MKT, [{
    "order_id": "MISMATCH-1", "posted_date": D(35),
    "referral_fees": 5.00, "fba_fees": 0.0, "other_fees": 0.0,
    "principal": 30.00, "tax": 6.00, "refunds": 0.0, "refund_tax": 0.0,
    "refund_units": 0, "refund_fees_returned": 0.0, "promos": 0.0,
    "units": 1, "currency": "GBP",
}])
_m4 = {}
_sd.series(CFG, WS, MKT, D(45), D(45), vat_rate=0.2, basis="order", meta=_m4)
_tie = _m4.get("tie_out") or {}
check("the day that does not add up is counted", _tie.get("days"), 1)
check("  and by how much", _tie.get("amount"), 6.0)
check_true("  with an explanation, not just a number", _tie.get("note"))
# A day that DOES add up must not be flagged -- a caveat on every day is noise.
_m5 = {}
_sd.series(CFG, WS, MKT, D(20), D(20), vat_rate=0.2, basis="order", meta=_m5)
check("a day that reconciles is not flagged", _m5.get("tie_out"), None)

print("\n== the currency survives a range that starts before trading did ==")
# "Total Sales 583" with no pound sign on 90d and ytd, beside "GBP 384" on 30d:
# rows[0] is a day with no trade, and a day with no trade carries no currency.
check("an empty leading run does not lose the currency",
      _sd.currency_of([{"currency": ""}, {"currency": ""}, {"currency": "GBP"}]),
      "GBP")
check("  and no rows at all is still safe", _sd.currency_of([]), "")

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
