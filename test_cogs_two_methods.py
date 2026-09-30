"""Product cost has exactly TWO sources, and the order-specific one wins.

    OWNER DECISION, 30 Sep 2026:
    "There are TWO ways to provide product cost. METHOD 1 -- PRODUCT-LEVEL
     COST: the product's normal/default cost, entered manually in the app OR by
     uploading a sheet; it belongs to the product. METHOD 2 -- ORDER-LEVEL COST:
     a cost specifically for an order. ORDER-SPECIFIC COST > PRODUCT-LEVEL COST
     for that order. Example: product default GBP10, order-specific GBP8 -> that
     order uses GBP8; the product default stays GBP10 for other orders. ... An
     order-specific cost must NOT overwrite the product default."

Run against a throwaway database and a throwaway cost file (ALTASCRAPER_DB and
a temp config path), never the owner's own.

THE CHARACTERIZATION HALF pins what already held on 30 Sep 2026:
  * setting an order's cost leaves the product default and every other order
    alone
  * the Orders resolver (order_cogs.line_cost_fn) and the Sales reader
    (order_profit.lines_between, after freeze_range) give the same cost
  * an ordinary re-cost (no force) never touches an order-specific cost

THE REGRESSION HALF is what did NOT hold:
  * "Work costs out again" on the Sales bar posts force:true, and freeze_range
    with force re-resolved EVERY line from the product cost -- including the
    ones the owner had set for that order alone. The GBP8 became GBP10 again,
    the one outcome the rule forbids.
  * lines frozen under the retired sources ('sku' -- the number read out of a
    SKU name, 'tracked' -- a supplier price the repricer happened to record)
    are neither method. They outranked the product cost for ever, so a third
    source nobody set was still deciding old orders' profit.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

TMP = tempfile.mkdtemp(prefix="cogs2m_")
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')

from data import db as _db                       # noqa: E402
from domain import cogs_store as _cs             # noqa: E402
from domain import order_cogs as _oc             # noqa: E402
from domain import order_profit as _op           # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


A, M, SKU = "acct", "UK", "10.00_3Days_B0TESTTEST"
DAY = "2026-09-10"


def add_line(oid, sku=SKU, cogs=None, src=None):
    _db.get_db(CFG).execute(
        "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
        " purchase_date, asin, sku, units, revenue, shipping, currency, status, "
        " cogs, cogs_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (A, M, oid, DAY + "T10:00:00Z", "B0TESTTEST", sku, 1, 20.0, 0.0,
         "GBP", "Shipped", cogs, src))


def stored(oid, sku=SKU):
    r = _db.get_db(CFG).execute(
        "SELECT cogs, cogs_source FROM order_lines WHERE workspace_id=? AND "
        "order_id=? AND sku=?", (A, oid, sku)).fetchone()
    return (None if r["cogs"] is None else round(float(r["cogs"]), 2),
            r["cogs_source"])


def orders_cost(oid, sku=SKU):
    """What the Orders screen resolves -- the same call routes/orders_routes makes."""
    f = _oc.line_cost_fn(CFG, A, M, overrides=_cs.all_overrides(CFG),
                         order_ids=[oid], default_order_id=oid)
    c, _src = f(sku)
    return None if c is None else round(c, 2)


def sales_cost(oid, sku=SKU, force=False):
    """What the Sales profit card reads: freeze, then the stored line."""
    _oc.freeze_range(CFG, A, M, DAY, DAY, _oc.DEFAULT_MODE,
                     _cs.all_overrides(CFG), force=force)
    for L in _op.lines_between(CFG, A, M, DAY, DAY):
        if L["order_id"] == oid and L["sku"] == sku:
            return None if L["cogs"] is None else round(float(L["cogs"]), 2)
    return "missing"


# ---------------------------------------------------------------------------
print("== the owner's example: product GBP10, one order GBP8 ==")
_cs.set_cost(CFG, A, SKU, 10)
add_line("111-0000001-0000001")
add_line("111-0000002-0000002")
check("before: order 1 uses the product cost (Orders)",
      orders_cost("111-0000001-0000001"), 10.0)
check("before: order 1 uses the product cost (Sales)",
      sales_cost("111-0000001-0000001"), 10.0)

n = _oc.set_for_order(CFG, A, M, "111-0000001-0000001", 8, sku=SKU)
check("the order cost was written to one line", n, 1)
check("order 1 now costs 8 on Orders", orders_cost("111-0000001-0000001"), 8.0)
check("order 1 now costs 8 on Sales", sales_cost("111-0000001-0000001"), 8.0)
check("  and is marked as the owner's order-specific figure",
      stored("111-0000001-0000001")[1], "manual-order")

print("\n== an order cost does NOT touch the product default ==")
_cs.load(CFG, force=True)
check("the product default is still 10",
      _cs.find(_cs.all_overrides(CFG), A, SKU)[0], 10.0)
check("the other order still costs 10 on Orders",
      orders_cost("111-0000002-0000002"), 10.0)
check("the other order still costs 10 on Sales",
      sales_cost("111-0000002-0000002"), 10.0)

print("\n== an ordinary re-cost leaves the order cost alone ==")
check("re-cost without force keeps 8", sales_cost("111-0000001-0000001"), 8.0)

print("\n== 'Work costs out again' (force) must not undo it either ==")
# THE REGRESSION. cogsmode.js cogsRefreeze posts force:true; freeze_range used
# to re-resolve this line from the product cost and write 10 over the 8.
_cs.set_cost(CFG, A, SKU, 12)
check("force re-cost keeps the order's 8", sales_cost("111-0000001-0000001",
                                                        force=True), 8.0)
check("  still marked order-specific", stored("111-0000001-0000001")[1],
      "manual-order")
check("  and Orders agrees", orders_cost("111-0000001-0000001"), 8.0)
check("force re-cost DOES move the other order to the new default",
      sales_cost("111-0000002-0000002", force=True), 12.0)
check("  and Orders agrees", orders_cost("111-0000002-0000002"), 12.0)

print("\n== clearing the order cost falls back to the product cost ==")
_oc.set_for_order(CFG, A, M, "111-0000001-0000001", None, sku=SKU)
check("Orders falls back to the product default",
      orders_cost("111-0000001-0000001"), 12.0)
check("Sales falls back to the product default",
      sales_cost("111-0000001-0000001"), 12.0)

print("\n== a retired third source does not outrank the product cost ==")
# 'sku' (read out of the SKU's name) and 'tracked' (a supplier price reading)
# are not either of the two methods. Where the product now has a cost, the
# owner's explicit "Work costs out again" (force) replaces them, on both
# screens alike. Merely OPENING Sales does not (review, 30 Sep 2026): that is a
# read, and old figures he has seen must not move silently -- and until the
# re-cost both screens show the SAME stored figure. Orders is asked FIRST here,
# so the agreement does not depend on Sales having run.
add_line("111-0000003-0000003", cogs=7.0, src="sku")
add_line("111-0000004-0000004", cogs=6.5, src="tracked")
check("before any re-cost, Orders shows the stored legacy figure",
      orders_cost("111-0000003-0000003"), 7.0)
check("  opening Sales does not rewrite it", sales_cost("111-0000003-0000003"), 7.0)
check("  and Orders still agrees", orders_cost("111-0000003-0000003"), 7.0)
check("'Work costs out again' gives a legacy 'sku' line the product cost",
      sales_cost("111-0000003-0000003", force=True), 12.0)
check("  and Orders agrees", orders_cost("111-0000003-0000003"), 12.0)
check("'Work costs out again' gives a legacy 'tracked' line the product cost",
      sales_cost("111-0000004-0000004", force=True), 12.0)
check("  and Orders agrees", orders_cost("111-0000004-0000004"), 12.0)

# With NO product cost to replace it, the old figure is kept rather than wiped:
# blanking a number the owner has been looking at is a decision, not a cleanup.
SKU2 = "5.00_3Days_B0OTHEROTHR"
add_line("111-0000005-0000005", sku=SKU2, cogs=5.0, src="sku")
check("a legacy line with no product cost keeps its figure, even on a re-cost",
      sales_cost("111-0000005-0000005", sku=SKU2, force=True), 5.0)

print("\n== a frozen product-level copy is still product-level ==")
# Frozen when first seen, at the product cost of the time. Typing a new product
# cost does not silently rewrite last month (cogsmode.js says so on screen); a
# re-cost does. It never outranks an order-specific cost.
_cs.set_cost(CFG, A, SKU, 14)
check("an already-costed order keeps the cost it was frozen at",
      sales_cost("111-0000002-0000002"), 12.0)
check("  and Orders shows the same", orders_cost("111-0000002-0000002"), 12.0)

_db.close_db()
os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
