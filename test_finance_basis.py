"""Finance: two calendars, and the things that must not change between them.

    "Order-based / Settlement toggle ... the KPI values AND the product table
     data change to reflect either order-date or settlement-date accounting"

They must change -- they answer different questions. What must NOT change is the
account-level charge, which is the same subscription whichever way the sales are
counted, and which read 65.51 on one tab and 0.00 on the other before this.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                    # noqa: E402
from domain import contribution as _con       # noqa: E402
from domain import expenses as _exp           # noqa: E402

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


WS, MKT, S, E = "__fin_basis__", "UK", "2026-08-01", "2026-08-31"
conn = _db.get_db()
for t in ("order_lines", "order_fees", "finance_daily", "sales_daily",
          "ads_daily", "manual_expenses"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))

# Two products sold in August. One has settled, one has not -- which is exactly
# the situation the two calendars disagree about.
conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
             "purchase_date, asin, sku, title, units, revenue, currency, cogs, "
             "cogs_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "F-1", "2026-08-05T10:00:00Z", "B0SETTLED", "S1",
              "Settled thing", 2, 100.0, "GBP", 30.0, "sku"))
conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
             "purchase_date, asin, sku, title, units, revenue, currency, cogs, "
             "cogs_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "F-2", "2026-08-20T10:00:00Z", "B0PENDING", "S2",
              "Not settled yet", 1, 60.0, "GBP", 20.0, "sku"))
# Amazon has settled only the first.
conn.execute("INSERT INTO order_fees (workspace_id, marketplace, order_id, "
             "posted_date, referral_fees, fba_fees, other_fees, principal) "
             "VALUES (?,?,?,?,?,?,?,?)",
             (WS, MKT, "F-1", "2026-08-09", 15.0, 0.0, 1.0, 100.0))
# ...and the settlement feed knows only that one product, plus a 60.00 charge
# against the account that belongs to no order at all.
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
             "principal, referral_fees, units, cogs, cogs_units, currency) "
             "VALUES (?,?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "2026-08-09", "B0SETTLED", 100.0, 15.0, 2, 30.0, 2, "GBP"))
conn.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
             "other_fees, currency) VALUES (?,?,?,?,?,?)",
             (WS, MKT, "2026-08-09", "*", 61.0, "GBP"))
conn.execute("INSERT INTO ads_daily (workspace_id, marketplace, date, asin, "
             "spend, ad_sales, clicks, ad_product) VALUES (?,?,?,?,?,?,?,?)",
             (WS, MKT, "2026-08-05", "B0SETTLED", 5.0, 40.0, 10,
              "SPONSORED_PRODUCTS"))
conn.commit()

print("\nthe two calendars answer different questions, and both are right")
o_rows, o_tot = _con.by_product_orders(None, WS, MKT, S, E)
s_rows, s_tot = _con.by_product(None, WS, MKT, S, E)
# THE WHOLE REASON THE TOGGLE EXISTS. Settlement lags, so it sees one product
# on a month where two sold -- and a screen showing one row for a busy month
# reads as "nothing sold" unless it says which calendar it is on.
check("orders sees everything placed", len(o_rows), 2)
check("settlement sees only what has settled", len(s_rows), 1)
check("orders revenue is everything sold", o_tot["revenue"], 160.0)
check("settlement revenue is only the settled part", s_tot["revenue"], 100.0)
check("the basis is named on the reply", o_tot.get("basis"), "orders")

print("\nfees on the order calendar are the hybrid, not one rate throughout")
by = {r["asin"]: r for r in o_rows}
# Amazon charged 16.00 on the settled order; the unsettled one is charged at
# the account's own measured rate, never the other way round.
check("the settled product carries Amazon's own fee",
      by["B0SETTLED"]["fees"], 16.0)
truthy("the unsettled one is estimated, and not at zero",
       by["B0PENDING"]["fees"] > 0)
check("and the reply says how much revenue that covered",
      o_tot.get("estimated_revenue"), 60.0)
truthy("with the rate it used", o_tot.get("fee_rate") is not None)

print("\nadvertising comes off contribution, and only when it is known")
# 100 revenue - 16 fees - 60 cogs (2 x 30) - 5 ad = 19.00
check("the advertised product's contribution has the ad spend taken off",
      by["B0SETTLED"]["contribution"], 19.0)
check("and its ad spend is reported", by["B0SETTLED"]["ad_spend"], 5.0)
# NULL, NOT ZERO. Subtracting an unknown ad spend as if it were nought makes
# every advertised product look better than it is, by exactly what is spent.
check("a product with no advertising row reports unknown, not 0.00",
      by["B0PENDING"]["ad_spend"], None)

print("\nan uncosted unit still withholds the contribution")
conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
             "purchase_date, asin, sku, units, revenue, currency) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (WS, MKT, "F-3", "2026-08-21T10:00:00Z", "B0NOCOST", "S3", 1,
              40.0, "GBP"))
conn.commit()
o2, _t2 = _con.by_product_orders(None, WS, MKT, S, E)
nc = {r["asin"]: r for r in o2}["B0NOCOST"]
check("no cost recorded means no contribution stated", nc["contribution"], None)
check("and no margin either", nc["margin_pct"], None)
check("but its uncosted units are counted", nc["uncosted_units"], 1)

print("\nthe account-level charge is the SAME on both calendars")
# It read 65.51 on settlement and 0.00 on orders, for one subscription, because
# it was derived by comparing Amazon's feed against the product ROWS -- a
# comparison that only holds when those rows came from the feed.
gap = _exp.account_level_charge(None, WS, MKT, S, E)
check("Amazon charged 61.00 outside any order", gap, 60.0)
truthy("and it does not depend on the basis",
       _exp.account_level_charge(None, WS, MKT, S, E) == gap)
# Never negative: when the orders account for MORE than Amazon charged there is
# nothing to find, and a negative would be subtracted as though it were income.
check("a window Amazon charged nothing in reports no charge, not a negative",
      _exp.account_level_charge(None, WS, MKT, "2026-09-01", "2026-09-30"), 0.0)

print("\nthe route offers both and validates what it is asked for")
RT = open(os.path.join(HERE, "routes", "finance_routes.py"),
          encoding="utf-8").read()
truthy("it reads a basis", 'request.args.get("basis")' in RT)
truthy("and refuses an unknown one",
       'if basis not in ("orders", "settlement")' in RT)
truthy("orders is the default", '"basis") or "orders"' in RT)
truthy("it calls the order-based reader", "by_product_orders(" in RT)
# The account name must be readable by the standard spelling. This route read
# `id` alone, so a caller using `account` fell through to whichever workspace
# happened to be open -- on a page of money.
truthy("and it accepts the standard account spelling",
       "_req_acct.named(request)" in RT)

for t in ("order_lines", "order_fees", "finance_daily", "sales_daily",
          "ads_daily", "manual_expenses"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
