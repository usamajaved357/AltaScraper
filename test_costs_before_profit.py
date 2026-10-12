"""Every profit screen costs the window's orders BEFORE it reads them.

    OWNER, 12 Oct 2026: "The repricer shows me another number for the profits,
    the Sales tab shows me another number, and the PPC page shows me another
    number. They don't talk to each other."

One of the reasons: a product's cost is frozen onto an order line by
order_cogs.freeze_range, and only /sales/summary ever called it -- half-way
down, after the grid's totals had already been read. P&L, Finance, PPC
Analytics and Brand view read whatever was frozen, so the same order counted
as costed or uncosted depending on which page had been opened first.

Now order_cogs.ensure_costed is the one step, and every route that reads a
window's profit takes it first. Run against a throwaway database.
"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

TMP = tempfile.mkdtemp(prefix="costfirst_")
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')

from data import db as _db                       # noqa: E402
from domain import cogs_store as _cs             # noqa: E402
from domain import order_cogs as _oc             # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


A, M, SKU = "acct", "UK", "7.69_3Days_B0FG7QFJFJ"


def add_line(oid, cogs=None, src=None):
    _db.get_db(CFG).execute(
        "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
        " purchase_date, asin, sku, units, revenue, shipping, currency, status, "
        " cogs, cogs_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (A, M, oid, "2026-09-10T10:00:00Z", "B0FG7QFJFJ", SKU, 1, 14.49, 0.0,
         "GBP", "Shipped", cogs, src))
    _db.get_db(CFG).commit()


def stored(oid):
    r = _db.get_db(CFG).execute(
        "SELECT cogs, cogs_source FROM order_lines WHERE order_id=?",
        (oid,)).fetchone()
    return (None if r["cogs"] is None else round(float(r["cogs"]), 2),
            r["cogs_source"])


print("== ensure_costed: the product cost reaches an uncosted order ==")
add_line("206-0000000-0000001")                        # no cost yet
add_line("206-0000000-0000002", 8.94, "manual-order")  # his own figure
_cs.set_cost(CFG, A, SKU, 7.69)
rep = _oc.ensure_costed(CFG, A, M, "2026-09-01", "2026-09-30")
check("uncosted line takes the product cost", stored("206-0000000-0000001"),
      (7.69, "manual"))
check("an order's own cost is never touched", stored("206-0000000-0000002"),
      (8.94, "manual-order"))
check("and it reports what it did", (rep.get("priced"), rep.get("kept_order_costs")),
      (1, 1))


print("== and does not repeat itself when nothing it reads has changed ==")
check("a second call with nothing new is skipped",
      _oc.ensure_costed(CFG, A, M, "2026-09-01", "2026-09-30").get("unchanged"),
      True)
_oc.set_for_order(CFG, A, M, "206-0000000-0000002", 9.10)
check("an order's own cost set since -> it looks again",
      _oc.ensure_costed(CFG, A, M, "2026-09-01", "2026-09-30").get("unchanged"),
      None)
_cs.set_cost(CFG, A, SKU, 7.99)
check("a product cost changed since -> it looks again",
      _oc.ensure_costed(CFG, A, M, "2026-09-01", "2026-09-30").get("unchanged"),
      None)

print("== every profit route takes the step before it reads ==")


def body(path, func):
    src = open(os.path.join(HERE, path), encoding="utf-8").read()
    m = re.search(r"def %s\(.*?(?=\n    @app\.route|\n    def [a-z_]+\(|\Z)" % func,
                  src, re.S)
    return m.group(0) if m else ""


ROUTES = [
    ("routes/sales_routes.py", "sales_summary", "_sd.totals("),
    ("routes/sales_routes.py", "sales_pnl", "_pnl.build("),
    ("routes/sales_routes.py", "sales_pnl_ledger", "_pl.ledger("),
    ("routes/sales_routes.py", "sales_series", "_sd.series("),
    ("routes/finance_routes.py", "finance_contribution", "_contrib.by_product"),
    ("routes/brandview_routes.py", "brand_marketplaces", "_sd.totals("),
    ("routes/ppc_analytics_routes.py", "ppc_analytics_overview", "_pa.rates("),
    ("routes/ppc_analytics_routes.py", "ppc_analytics_terms", "_pa.rates("),
    ("routes/ppc_analytics_routes.py", "ppc_analytics_campaigns", "_pa.rates("),
]
for path, func, reader in ROUTES:
    b = body(path, func)
    i_e, i_r = b.find("ensure_costed("), b.find(reader)
    check("%s costs first" % func, i_e >= 0 and i_r >= 0 and i_e < i_r, True)

check("freeze_range is called from nowhere else in routes/ but the owner's "
      "explicit re-cost",
      sorted(set(f for f in os.listdir(os.path.join(HERE, "routes"))
                 if f.endswith(".py") and "freeze_range(" in
                 open(os.path.join(HERE, "routes", f), encoding="utf-8").read())),
      ["cogs_mode_routes.py"])

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
