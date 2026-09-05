"""domain/pnl.py -- the account P&L, and the four things it must never do.

Every check here is about honesty rather than arithmetic. The arithmetic is one
subtraction; what makes a P&L trustworthy is that it refuses to state things it
does not know, and says which of its figures Amazon sent and which this app
worked out.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db          # noqa: E402
from domain import pnl as _pnl      # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT = "__pnl_test__", "UK"
conn = _db.get_db()
for t in ("order_lines", "order_fees", "finance_daily", "ads_daily",
          "sales_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))

# Two orders placed in the window. One Amazon has settled, one it has not.
conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
             "purchase_date, sku, units, revenue, cogs, cogs_source) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "S-1", "2026-08-10T10:00:00Z", "A", 1, 100.0, 40.0, "sku"))
conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
             "purchase_date, sku, units, revenue, cogs, cogs_source) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "U-1", "2026-08-20T10:00:00Z", "B", 1, 100.0, None, ""))
# Amazon's own fees for the settled one.
conn.execute("INSERT INTO order_fees (workspace_id, marketplace, order_id, "
             "posted_date, referral_fees, fba_fees, other_fees, principal) "
             "VALUES (?,?,?,?,?,?,?,?)",
             (WS, MKT, "S-1", "2026-08-14", 15.0, 0.0, 1.0, 100.0))
# A refund, on ITS OWN date, belonging to a sale from before the window.
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
             "refunds, refund_units, other_fees) VALUES (?,?,?,?,?,?,?)",
             (WS, MKT, "2026-08-25", "*", 30.0, 1, 25.0))
conn.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
             "ordered_sales, units, currency) VALUES (?,?,?,?,?,?,?)",
             (WS, MKT, "2026-08-10", "*", 200.0, 2, "GBP"))
conn.commit()

try:
    r = _pnl.build(None, WS, MKT, "2026-08-01", "2026-08-31")

    print("== fees: Amazon's where it has sent them, the rate where it has not ==")
    cov = r["fee_coverage"]
    check("both orders are counted", cov["orders"], 2)
    check("  one of them is settled", cov["settled"], 1)
    check("  so the window is half settled", cov["pct_settled"], 50.0)
    check("Amazon's own referral fee is used, not a rate", r["referral_fees"], 15.0)
    truthy("  and it is labelled as part-actual",
           r["basis"]["referral_fees"] == "part-actual")
    truthy("the unsettled order is charged at a rate instead",
           r["fees_estimated"] > 0)
    check("  applied ONLY to the revenue Amazon has not itemised",
          r["unsettled_revenue"], 100.0)
    truthy("  and that line says it is an estimate",
           "estimate" in r["basis"]["fees_estimated"])

    print("\n== a refund sits on the day the money moved ==")
    check("the refund is subtracted", r["refunds"], 30.0)
    truthy("  and the reader is told it is not re-dated",
           any("not the day of the original order" in n for n in r["notes"]))

    print("\n== nothing is invented ==")
    truthy("an uncosted unit is reported, not costed at zero",
           r["uncosted_units"] == 1)
    truthy("  and the profit says out loud that it is too high",
           any("HIGHER than the truth" in n for n in r["notes"]))
    check("no advertising data means None, never 0.00", r["ad_spend"], None)
    truthy("  and that is said too",
           any("not the same as having spent nothing" in n for n in r["notes"]))

    print("\n== charges that belong to no order are not silently dropped ==")
    # 25.00 of account-level other_fees against 1.00 attached to an order.
    check("the unattributed remainder is found", r["unattributed_fees"], 24.0)
    truthy("  and named as a fixed cost that is NOT in the profit",
           any("belong to the account rather than to any order" in n
               for n in r["notes"]))

    print("\n== the postage trap ==")
    truthy("it refuses to add a shipping-credits line",
           any("count it twice" in n for n in r["notes"]))
    truthy("  and there is no such line in the statement",
           not any(k == "shipping_credits" for k, _l, _s in _pnl.LINES))

    print("\n== the arithmetic still adds up ==")
    # 200 sales - 30 refunds - 40 cogs - (15 + 0 + 1 + estimate) + 0 - 0
    expected = round(200.0 - 30.0 - 40.0 - r["fees_total"], 2)
    check("profit is the lines subtracted from each other", r["profit"], expected)
    check("  net sales is sales minus refunds", r["net_sales"], 170.0)
finally:
    for t in ("order_lines", "order_fees", "finance_daily", "ads_daily",
              "sales_daily"):
        conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
    conn.commit()

print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
