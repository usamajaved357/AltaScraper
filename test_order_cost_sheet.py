"""The order-cost sheet's `cost` is what the WHOLE order line cost.

    OWNER, 12 Oct 2026 (nestwell_goods loss analysis): his sourcing log has one
    row per Amazon order and "Price" is what he paid the supplier for that
    order -- two ceiling fans in one order are 27.98, not 13.99.

The Orders screen asks for "the price you actually paid for that order", but the
upload stored the figure as the PER-UNIT cost (order_lines.cogs), and
order_profit.line_cogs multiplies it by the units again. So a two-unit order
was costed twice over. And a sheet with no SKU column put the one figure on
EVERY line of a two-product order, costing that order once per product.

Run against a throwaway database (ALTASCRAPER_DB), never the owner's own.
Fails on the code before this fix: the two-unit order stores 27.98 a unit
(55.96 a line) and the two-product order is written twice.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

TMP = tempfile.mkdtemp(prefix="ocsheet_")
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')

from data import db as _db                       # noqa: E402
from domain import order_cogs_sheet as _ocs      # noqa: E402
from domain import order_profit as _op           # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


A, M = "acct", "UK"


def add_line(oid, sku, units):
    _db.get_db(CFG).execute(
        "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
        " purchase_date, asin, sku, units, revenue, shipping, currency, status, "
        " cogs, cogs_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (A, M, oid, "2026-09-10T10:00:00Z", "B0" + sku[-8:], sku, units,
         34.99 * units, 0.0, "GBP", "Shipped", None, None))
    _db.get_db(CFG).commit()


def stored(oid, sku):
    r = _db.get_db(CFG).execute(
        "SELECT cogs, units FROM order_lines WHERE workspace_id=? AND "
        "order_id=? AND sku=?", (A, oid, sku)).fetchone()
    return None if r["cogs"] is None else round(float(r["cogs"]), 2)


def line_cost(oid, sku):
    r = _db.get_db(CFG).execute(
        "SELECT * FROM order_lines WHERE workspace_id=? AND order_id=? AND sku=?",
        (A, oid, sku)).fetchone()
    return round(_op.line_cogs(dict(r)), 2)


add_line("203-0000000-0000001", "FAN", 1)
add_line("203-0000000-0000002", "FAN", 2)              # two fans, one order
add_line("203-0000000-0000003", "FAN", 1)              # two products, one order
add_line("203-0000000-0000003", "ROLLER", 1)

# His own sheet's shape: an order column and a cost, no SKU.
heads = ["order id", "cost"]
rep = _ocs.apply_sheet(CFG, A, M, heads, [
    ["203-0000000-0000001", "13.99"],
    ["203-0000000-0000002", "27.98"],
    ["203-0000000-0000003", "21.00"],
    ["203-9999999-9999999", "5.00"],
])

print("== one unit: stored as given ==")
check("single-unit order: 13.99 a unit", stored("203-0000000-0000001", "FAN"), 13.99)

print("== two units: the order's cost is split, not doubled ==")
check("two-unit order stores 13.99 a unit",
      stored("203-0000000-0000002", "FAN"), 13.99)
check("and its line costs what was paid, 27.98",
      line_cost("203-0000000-0000002", "FAN"), 27.98)

print("== two products, no SKU: refused, not written twice ==")
check("fan line left uncosted", stored("203-0000000-0000003", "FAN"), None)
check("roller line left uncosted", stored("203-0000000-0000003", "ROLLER"), None)
check("counted as needing a SKU", rep.get("needs_sku"), 1)

print("== the report accounts for every row ==")
check("lines set", rep.get("set"), 2)
check("unknown order counted", rep.get("unknown_order"), 1)

print("== with a SKU column a two-product order is costed line by line ==")
rep2 = _ocs.apply_sheet(CFG, A, M, ["order id", "sku", "cost"], [
    ["203-0000000-0000003", "FAN", "12.00"],
    ["203-0000000-0000003", "ROLLER", "9.00"],
])
check("fan line 12.00", stored("203-0000000-0000003", "FAN"), 12.0)
check("roller line 9.00", stored("203-0000000-0000003", "ROLLER"), 9.0)
check("both set", rep2.get("set"), 2)

print("== the template shows `cost now` on the same whole-line basis ==")
h, rows = _ocs.template_rows(CFG, A, M)
now = {(r[0], r[2]): r[h.index("cost now")] for r in rows}
check("two-unit line reads 27.98, so copying it across changes nothing",
      now[("203-0000000-0000002", "FAN")], 27.98)

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
