"""A cost set after Amazon's money was pulled reaches the settled figures.

    OWNER, 12 Oct 2026: "My goal is to have accurate profit numbers and/or loss
    numbers inside each tab of finance."

finance_daily.cogs was priced when finance was pulled. The order-cost sheet he
uploaded afterwards changed the Sales card and the Finance orders tab, but not
the Finance settlement tab or a product-filtered Sales grid -- until "Re-read
95 days". finance_data.recost now rebuilds those costs from order_fees (units
each order settled each day) and order_lines (each unit's cost now), and only
on a day that fully reconciles. order_cogs.ensure_costed -- the step every
profit screen takes -- runs it. Throwaway database.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

TMP = tempfile.mkdtemp(prefix="recost_")
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')

from data import db as _db                       # noqa: E402
from domain import finance_data as _fd           # noqa: E402
from domain import order_cogs as _oc             # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


A, M = "acct", "UK"
c = _db.get_db(CFG)


def line(oid, asin, units, cogs, src=None):
    c.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
              "purchase_date, asin, sku, units, revenue, shipping, currency, "
              "status, cogs, cogs_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (A, M, oid, "2026-09-01T10:00:00Z", asin, "SKU-" + asin, units,
               34.99 * units, 0.0, "GBP", "Shipped", cogs, src))


def fee(oid, day, units):
    c.execute("INSERT INTO order_fees (workspace_id, marketplace, order_id, "
              "posted_date, units) VALUES (?,?,?,?,?)", (A, M, oid, day, units))


def fin(day, asin, units, cogs, cogs_units):
    c.execute("INSERT INTO finance_daily (workspace_id, marketplace, date, asin, "
              "units, cogs, cogs_units, principal) VALUES (?,?,?,?,?,?,?,?)",
              (A, M, day, asin, units, cogs, cogs_units, 34.99 * units))


# 5 Sep: two fans settle. Pulled before any cost was set.
line("203-1", "B0FAN", 1, 13.99, "manual-order")
line("203-2", "B0FAN", 2, 13.25, "manual-order")      # two fans, one order
fee("203-1", "2026-09-05", 1)
fee("203-2", "2026-09-05", 2)
fin("2026-09-05", "*", 3, 0.0, 0)
fin("2026-09-05", "B0FAN", 3, 0.0, 0)
# 6 Sep: one settled unit has no order line here (older than the history).
fee("203-9", "2026-09-06", 1)
line("203-3", "B0FAN", 1, 12.99, "manual-order")
fee("203-3", "2026-09-06", 1)
fin("2026-09-06", "*", 2, 15.00, 1)
# 7 Sep (review, 12 Oct 2026): a line never frozen -- sold in another
# marketplace of the account -- still has its product cost; a two-product
# order settling one unit on its own cannot be traced to a product; a
# cancelled line settles nothing.
from domain import cogs_store as _cs              # noqa: E402
_cs.set_cost(CFG, A, "SKU-B0MAT", 6.50)
c.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
          "purchase_date, asin, sku, units, revenue, currency, status) "
          "VALUES (?,?,?,?,?,?,?,?,?,?)",
          (A, "DE", "203-4", "2026-03-01T10:00:00Z", "B0MAT", "SKU-B0MAT", 1,
           12.0, "EUR", "Shipped"))
fee("203-4", "2026-09-07", 1)
line("203-5", "B0FAN", 1, 13.99, "manual-order")
c.execute("UPDATE order_lines SET status='Canceled' WHERE order_id='203-5'")
line("203-5", "B0MAT", 1, 6.50, "manual-order")
fee("203-5", "2026-09-07", 1)
fin("2026-09-07", "*", 2, 0.0, 0)
# 8 Sep: two products in one order, one unit settles alone.
line("203-6", "B0FAN", 1, 13.99, "manual-order")
line("203-6", "B0MAT", 1, 6.50, "manual-order")
fee("203-6", "2026-09-08", 1)
fin("2026-09-08", "*", 1, 3.0, 1)
c.commit()

rep = _oc.ensure_costed(CFG, A, M, "2026-09-01", "2026-09-30")


def row(day, asin):
    r = c.execute("SELECT cogs, cogs_units FROM finance_daily WHERE date=? "
                  "AND asin=?", (day, asin)).fetchone()
    return (round(float(r["cogs"] or 0), 2), int(r["cogs_units"] or 0))


print("== a day that reconciles takes the costs held now ==")
check("account row: 13.99 + 2 x 13.25", row("2026-09-05", "*"), (40.49, 3))
check("product row too", row("2026-09-05", "B0FAN"), (40.49, 3))
print("== a day that does not reconcile keeps what it had ==")
check("6 Sep untouched (one unit cannot be traced)", row("2026-09-06", "*"),
      (15.0, 1))
check("ensure_costed reports the re-cost",
      (rep.get("finance_recost") or {}).get("rewritten"), 3)
print("== the review's cases ==")
check("an unfrozen line is priced from its product cost; a cancelled line "
      "settles nothing", row("2026-09-07", "*"), (13.0, 2))
check("one unit of a two-product order settling alone is not guessed",
      row("2026-09-08", "*"), (3.0, 1))

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
