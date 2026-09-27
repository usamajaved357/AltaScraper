"""domain/expenses.py and the P&L lines that depend on it.

The costs Amazon never sees, and the one it charges against no order. Every
check is about a figure the statement must not invent: an unrecorded cost is not
a zero cost, a month is not thirty days, and VAT is never taken off quietly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                # noqa: E402
from domain import expenses as _exp       # noqa: E402
from domain import pnl as _pnl            # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT = "__exp_test__", "UK"
conn = _db.get_db()
for t in ("manual_expenses", "order_lines", "order_fees", "finance_daily",
          "sales_daily", "ads_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\na monthly amount is shared out by day, not by a flat thirty")
# 12 of August's 31 days. A flat /30 would give 24.00 and quietly lose a day
# every long month.
check("12 days of a 31-day month",
      _exp.apportion(60.0, "2026-08-01", "2026-08-12", "2026-01-01", None), 23.23)
check("the whole month is the whole amount",
      _exp.apportion(60.0, "2026-08-01", "2026-08-31", "2026-01-01", None), 60.0)
# February is shorter, so a day of it is worth MORE of the monthly amount.
check("a day of February is worth more than a day of August",
      _exp.apportion(28.0, "2026-02-01", "2026-02-01", "2026-01-01", None), 1.0)
check("a window spanning two months uses each month's own length",
      _exp.apportion(60.0, "2026-07-20", "2026-08-10", "2026-01-01", None), 42.58)

print("\na cost only counts while it was actually running")
check("one that ended before the window contributes nothing",
      _exp.apportion(60.0, "2026-08-01", "2026-08-31", "2026-01-01", "2026-06-30"), 0.0)
check("one that starts after it likewise",
      _exp.apportion(60.0, "2026-08-01", "2026-08-31", "2026-09-01", None), 0.0)
# NO END DATE MEANS STILL RUNNING, which is the normal state of a subscription.
# Treating it as ended is how a live cost silently drops out of every window.
check("no end date means it is still being charged",
      _exp.apportion(60.0, "2026-08-01", "2026-08-31", "2026-01-01", None), 60.0)
check("and it is counted from its start, not before",
      _exp.apportion(60.0, "2026-08-01", "2026-08-31", "2026-08-16", None), 16.0 / 31 * 60
      and round(16.0 / 31 * 60, 2))

print("\nwhat it refuses to store")
_id, why = _exp.add(None, WS, name="", amount=10, starts="2026-08-01")
truthy("a cost with no name is refused", why)
_id, why = _exp.add(None, WS, name="x", amount="abc", starts="2026-08-01")
truthy("an amount that is not a number is refused", why)
# A NEGATIVE COST IS INCOME, and calling it a cost subtracts it twice -- once
# by its sign and once by the P&L's own minus.
_id, why = _exp.add(None, WS, name="x", amount=-5, starts="2026-08-01")
truthy("a negative cost is refused, with the reason", "negative" in (why or ""))
_id, why = _exp.add(None, WS, name="x", amount=5, starts="not-a-date")
truthy("a start that is not a date is refused", why)
_id, why = _exp.add(None, WS, name="x", amount=5, starts="2026-08-10",
                    ends="2026-08-01")
truthy("an end before the start is refused", why)

print("\nrecording, reading back, removing")
eid, why = _exp.add(None, WS, name="Accountant", amount=90.0,
                    starts="2026-01-01", category="Professional")
check("a good one is stored", bool(eid) and not why, True)
w = _exp.for_window(None, WS, MKT, "2026-08-01", "2026-08-31")
check("it lands in the window", w["count"], 1)
check("at its full monthly amount for a whole month", w["total"], 90.0)
check("and carries how many days it covered", w["items"][0]["days"], 31)
half = _exp.for_window(None, WS, MKT, "2026-08-01", "2026-08-15")
check("half a month is half the money", half["total"], round(15.0 / 31 * 90, 2))

# An account-wide cost belongs to every marketplace: an accountant's fee is not
# a UK cost or a German one, and forcing it to be either makes every
# single-marketplace P&L wrong in the same direction.
check("an account-wide cost shows for any marketplace",
      _exp.for_window(None, WS, "DE", "2026-08-01", "2026-08-31")["count"], 1)

check("removing it takes it out", _exp.remove(None, WS, eid), 1)
check("and removing it twice changes nothing", _exp.remove(None, WS, eid), 0)

print("\nthe P&L subtracts them, and says when there are none")
conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
             "purchase_date, sku, units, revenue, cogs, cogs_source) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "E-1", "2026-08-10T10:00:00Z", "A", 1, 100.0, 40.0, "sku"))
# THE SALES LINE COMES FROM sales_daily, NOT FROM order_lines.revenue. They are
# different feeds answering different questions -- one is what Amazon reported
# sold, the other is the order rows this app stored -- and the VAT below is
# derived from the SALES line, so without this the gross is nought and the
# derived VAT is a truthful nought about nothing.
conn.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
             "ordered_sales, units, orders) VALUES (?,?,?,?,?,?,?)",
             (WS, MKT, "2026-08-10", "*", 100.0, 1, 1))
conn.commit()

before = _pnl.build(None, WS, MKT, "2026-08-01", "2026-08-31")
# RECORDED NONE AND SPENT NONE ARE DIFFERENT. An account where nobody has
# entered a cost reports None, so the line reads "not known" rather than a
# confident 0.00 saying this business has no overheads at all.
check("with nothing recorded the line is unknown, not zero",
      before["manual_expenses"], None)
truthy("and the statement says so",
       any("No costs of your own are recorded" in n for n in before["notes"]))

_exp.add(None, WS, name="Software", amount=31.0, starts="2026-01-01")
after = _pnl.build(None, WS, MKT, "2026-08-01", "2026-08-31")
check("once recorded it is a real figure", after["manual_expenses"], 31.0)
check("and profit is lower by exactly that",
      round(before["profit"] - after["profit"], 2), 31.0)

# RE-PINNED 28 Sep 2026. This section used to pin "VAT is shown beside the
# profit and never subtracted". The owner decided (D1, profit-accuracy work)
# that every profit figure follows the VAT rate set on the account, so the
# statement now TAKES IT OUT -- and still never invents it where no rate is set.
print("\nVAT follows the account's own setting, and is never invented")
v = after.get("vat") or {}
# No rate set and no tax from Amazon: UNKNOWN, not zero. Silently subtracting a
# fifth from an unregistered seller is as wrong as leaving it in for a
# registered one, so neither is done.
check("no rate and no Amazon tax is unknown", v.get("basis"), "unknown")
check("and the VAT amount is not invented", v.get("amount"), None)
truthy("the risk is stated in words",
       "overstated" in (v.get("explain") or ""))

zero = _pnl.build(None, WS, MKT, "2026-08-01", "2026-08-31", 0)
# A RATE OF 0 IS A REAL ANSWER -- not registered -- and produces a real zero.
check("a rate of zero means not registered", (zero.get("vat") or {}).get("basis"),
      "none")
check("so the VAT is a measured nought", (zero.get("vat") or {}).get("amount"), 0.0)

twenty = _pnl.build(None, WS, MKT, "2026-08-01", "2026-08-31", 0.2)
tv = twenty.get("vat") or {}
check("a rate of 20% derives the tax", tv.get("basis"), "derived")
# THE SALES FIGURE ALREADY INCLUDES THE VAT, so the tax in it is gross x r/(1+r)
# -- 16.67 of 100, not 20. Multiplying by the rate takes out a fifth too much.
check("and takes it OUT of the gross rather than adding it on",
      tv.get("amount"), round(100.0 * 0.2 / 1.2, 2))
# Lower by the VAT LESS the fee on it: this order is unsettled, so its fee is
# estimated at the account's rate on sales AFTER VAT, and taking the VAT out
# shrinks that estimate too. 16.67 - 16.67 x 15% = 14.17.
_v = round(100.0 * 0.2 / 1.2, 2)
check("and the profit is lower by that VAT, less the fee on it",
      round(after["profit"] - twenty["profit"], 2),
      round(_v - _v * float(twenty["fee_rate"]), 2))
check("the statement carries it as its own line", twenty.get("vat_line"),
      round(100.0 * 0.2 / 1.2, 2))

print("\nthe Amazon charge that belongs to no order")
# An order-joined fee query cannot see the monthly subscription: Amazon posts it
# against the account. Measured at 60.00 on the real data.
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
             "other_fees) VALUES (?,?,?,?,?)", (WS, MKT, "2026-08-05", "*", 60.0))
conn.commit()
s = _exp.suggest(None, WS, MKT, "2026-08-01", "2026-08-31")
truthy("it is found", bool(s))
check("at the amount Amazon charged", (s or {}).get("amount"), 60.0)
# Wording re-pinned 28 Sep 2026: the charge is now taken off net profit by
# itself (expenses.overhead_for), so the offer says that rather than "it is not
# in the profit".
truthy("and explained rather than just reported",
       "belongs to no order" in ((s or {}).get("why") or "")
       and "will not be counted twice" in ((s or {}).get("why") or ""))
_exp.add(None, WS, name="Amazon selling subscription", amount=60.0,
         starts="2026-08-01", marketplace=MKT)
# OFFERING IT TWICE IS HOW IT GETS SUBTRACTED TWICE.
check("once recorded, it is not suggested again",
      _exp.suggest(None, WS, MKT, "2026-08-01", "2026-08-31"), None)

for t in ("manual_expenses", "order_lines", "order_fees", "finance_daily",
          "sales_daily", "ads_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
