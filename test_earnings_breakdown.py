# -*- coding: utf-8 -*-
"""Why the profit figures were blank, and the sum that explains them.

REPORTED
  "i am not able to see the earnings of each order and not the breakdown of the
   item that how many are cogs how much fee deducted, i dont find the calculations
   accurate, and also not able to see the profits accurate profits after putting
   the cogs in a sheet in the repricer"

THE ROOT CAUSE, measured on the real database 17 Aug 2026
The cost sheet was built from the CATALOGUE SNAPSHOT and nothing else. The snapshot
is not the same thing as "what this account sells":

    selvora_limited   snapshot 7 SKUs   sold 4 SKUs   2 of them NOT in the snapshot
                      OO-96JX-Z7ND               52 orders   1,757.97 of revenue
                      Italian Brainrot Tung...    5 orders       49.95

So the two products earning nearly all of that account's money had NO ROW on the
cost sheet. There was nowhere to type their cost. Without a cost no profit can be
worked out, so every one of those orders reported "profit not known" -- and filling
in the sheet and uploading it changed nothing, because the SKUs were never on it.

The manual cost store was empty (0 entries) on an account with 108 order lines.

TWO FIXES, TESTED HERE
  1. the cost sheet lists every SKU that has SOLD, biggest earner first, as well
     as everything listed and everything the repricer tracks;
  2. an order shows its sum line by line -- what the buyer paid, Amazon's cut,
     what the stock cost, what is left -- so a figure can be checked instead of
     taken on trust, and a line with no cost names itself instead of blanking the
     whole panel.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-66s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


TMP = tempfile.mkdtemp(prefix="altaearn_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "e.db")

from data import db as _db                                     # noqa: E402
from domain import cogs as C                                   # noqa: E402
from domain import orders_view as OV                           # noqa: E402

WS, MKT = "acct", "UK"
conn = _db.get_db(CFG)


print("=== 1. the cost sheet lists what you SELL, not just what is listed ===")
# The selvora shape: a small catalogue snapshot and a best seller that is not in
# it. Written straight into order_lines, which is where the app records a sale.
for i in range(52):
    conn.execute(
        "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
        " purchase_date, sku, title, units, revenue, currency) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (WS, MKT, "O%03d" % i, "2026-08-1%d" % (i % 10), "BIG-SELLER",
         "The one that earns", 1, 33.81, "GBP"))
conn.execute(
    "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
    " purchase_date, sku, title, units, revenue, currency) "
    "VALUES (?,?,?,?,?,?,?,?,?)",
    (WS, MKT, "O999", "2026-08-11", "SMALL-SELLER", "A quiet one", 1, 9.99, "GBP"))
conn.commit()

rows = C.template_rows(CFG, WS, MKT, overrides={})
skus = [r[0] for r in rows]
truthy("a SKU that has sold is on the sheet, even with no listing for it",
       "BIG-SELLER" in skus)
truthy("  and so is the quieter one", "SMALL-SELLER" in skus)
# THE ORDER MATTERS. The biggest revenue with no cost is the biggest hole in the
# profit figures, so it is the first row -- not wherever the alphabet puts it.
check("the biggest earner with no cost is the FIRST row", skus[0], "BIG-SELLER")
check("  then the next", skus[1], "SMALL-SELLER")
# And the row says why it is there, so a SKU nobody recognises explains itself.
first = rows[0]
truthy("the row says it has sold, and how often", "SOLD 52 times" in first[5])
truthy("  and that no cost is known for it", "not known" in first[5])
check("  the cost column is empty, ready to fill in", first[3], "")

print("\n  -- having SOLD wins over merely being listed --")
# A SKU in BOTH the snapshot and the orders must read as SOLD: that is the fact
# that decides how urgent a missing cost is. The snapshot is added first, so
# without the override it would say "listed on Amazon" and sort below products
# nobody has ever bought.
from domain import live_snapshots as _ls                        # noqa: E402
_ls.put(CFG, WS, MKT, {"items": [
    {"sku": "BIG-SELLER", "asin": "B0BIG", "title": "The one that earns"},
    {"sku": "NEVER-SOLD", "asin": "B0NEV", "title": "Sitting there"},
]}) if hasattr(_ls, "put") else None
rows2 = C.template_rows(CFG, WS, MKT, overrides={})
by = {r[0]: r for r in rows2}
if "NEVER-SOLD" in by:
    truthy("a listed-but-unsold SKU is still offered a cost",
           "NEVER-SOLD" in by)
    truthy("  and is marked as merely listed",
           "listed on Amazon" in by["NEVER-SOLD"][5])
    truthy("a SKU that is both listed and sold reads as SOLD",
           "SOLD" in by["BIG-SELLER"][5])
    check("  and still comes first", [r[0] for r in rows2][0], "BIG-SELLER")
else:
    print("  (no snapshot writer on live_snapshots -- union still checked above)")

print("\n  -- a cost that IS known drops down the list --")
rows3 = C.template_rows(CFG, WS, MKT, overrides={"acct::BIG-SELLER": 12.00})
check("the costed SKU is no longer the first job",
      [r[0] for r in rows3][0], "SMALL-SELLER")
big = {r[0]: r for r in rows3}["BIG-SELLER"]
check("  its current cost is shown, to read", big[4], "12.00")
check("  and the fill-in column is STILL empty", big[3], "")
truthy("  with where that cost came from", "you set it" in big[5])


print("\n=== 2. an order shows its sum, line by line ===")
items = [
    {"sku": "A", "asin": "B0A", "title": "Thing one", "qty": 2, "price": 40.00},
    {"sku": "B", "asin": "B0B", "title": "Thing two", "qty": 1, "price": 10.00},
]
costs = {"A": (7.50, "manual"), "B": (3.00, "sku")}
bd = OV.line_breakdown(items, 50.00, lambda s: costs.get(s, (None, "")))
a, b = bd["lines"]
check("line A: what the buyer paid", a["revenue"], 40.00)
# 15% of the 50.00 order is 7.50, split by what each line sold for: 40/50 and
# 10/50. Not split evenly -- that would overcharge the cheaper line.
check("line A: Amazon's cut, its share of the order's fee", a["fee"], 6.00)
check("line B: and its smaller share", b["fee"], 1.50)
check("  which add up to the order's fee", round(a["fee"] + b["fee"], 2), 7.50)
check("line A: the stock cost, 2 units at 7.50", a["cogs"], 15.00)
check("  with the per-unit figure kept, since qty is 2", a["unit_cost"], 7.50)
check("line A: what is left", a["profit"], 19.00)
check("  the margin on it", a["margin_pct"], 47.5)
check("  and the return on the stock", a["roi_pct"], 126.7)
check("line B: profit", b["profit"], 5.50)
t = bd["totals"]
check("the order's revenue", t["revenue"], 50.00)
check("  its fees", t["fees"], 7.50)
check("  its cost", t["cogs"], 18.00)
check("  and its profit", t["profit"], 24.50)
truthy("every cost is known, so the total may be shown", t["cogs_complete"])
check("nothing is uncosted", t["uncosted_lines"], 0)
# The sum has to actually add up, or the panel is four unrelated numbers.
check("revenue - fees - cost = profit",
      round(t["revenue"] - t["fees"] - t["cogs"], 2), t["profit"])

print("\n  -- one uncosted line names itself and does not blank the rest --")
half = OV.line_breakdown(items, 50.00, lambda s: {"A": (7.50, "manual")}.get(s, (None, "")))
la, lb = half["lines"]
check("the costed line still reports its profit", la["profit"], 19.00)
check("  the uncosted one reports none", lb["profit"], None)
check("  but still shows what it sold for", lb["revenue"], 10.00)
check("  and the fee it carried", lb["fee"], 1.50)
truthy("  and names its own gap", "no cost recorded" in lb["note"])
falsy("  the costed line has nothing to complain about", la["note"])
ht = half["totals"]
# THE ALL-OR-NOTHING RULE STILL HOLDS for the order total: counting an uncosted
# product as free would make the order look better than it is.
check("the order total is withheld", ht["profit"], None)
check("  and says how many lines are the reason", ht["uncosted_lines"], 1)
falsy("  and does not claim the cost is complete", ht["cogs_complete"])
check("  while still totalling the cost it DOES know", ht["cogs"], 15.00)

print("\n  -- postage and coupons show up as the gap they are --")
# The order total and the lines legitimately differ. The screen says so rather
# than letting the two numbers sit next to each other unexplained.
post = OV.line_breakdown(items, 54.99, lambda s: costs.get(s, (None, "")))
check("the lines add to 50.00", post["totals"]["revenue"], 50.00)
check("  while the buyer was charged 54.99", post["totals"]["order_total"], 54.99)

print("\n  -- nothing to show is not an error --")
empty = OV.line_breakdown([], 0, lambda s: (None, ""))
check("no items -> no lines", empty["lines"], [])
none_total = OV.line_breakdown(items, None, lambda s: costs.get(s, (None, "")))
check("no order total yet -> no fee is invented",
      none_total["lines"][0]["fee"], None)
check("  and no profit either", none_total["lines"][0]["profit"], None)
check("  but the cost is still known", none_total["lines"][0]["cogs"], 15.00)

print("\n=== 3. the order detail actually SENDS the breakdown ===")
# It called profit_for, which answers with one number and a note -- so the panel
# had nothing to lay out and no way to name which line was missing a cost.
import ast                                                      # noqa: E402
# utf-8-SIG. Several files in this repo start with a byte-order mark -- it
# predates this work, Python reads source as utf-8-sig so it never mattered, and
# reading one back as plain utf-8 hands ast.parse a U+FEFF it refuses. Use the
# same encoding Python itself uses for source.
src = open(os.path.join("routes", "orders_routes.py"), encoding="utf-8-sig").read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
        body = getattr(node, "body", [])
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body[0].value.value = ""
code = ast.unparse(tree)
truthy("the detail route works out the breakdown", "line_breakdown" in code)
truthy("  and puts it in the answer", "'breakdown'" in code or '"breakdown"' in code)

js = open(os.path.join("static", "js", "orders.js"), encoding="utf-8").read()
truthy("the screen draws it", "_ordBreakdownHtml" in js)
truthy("  with a column for what the buyer paid", "Buyer paid" in js)
truthy("  one for Amazon's fee", "Amazon fee" in js)
truthy("  one for the cost", ">Cost<" in js)
truthy("  and one for the profit", ">Profit<" in js)
truthy("  and it says the fee is an estimate", "estimated at" in js)

print("\n=== 4. the repricer says how many supplier links a SKU has ===")
# "i am not able to see all the source links in the repricer" -- they were all
# drawn, but only inside a panel opened by a button labelled "Why?", so the count
# was invisible.
sjs = open(os.path.join("static", "js", "sourcing.js"), encoding="utf-8").read()
truthy("there is a count on the row", "_srcCountChip" in sjs)
truthy("  it is drawn on every row", "_srcCountChip(r, id)" in sjs)
truthy("  a SKU with none says so in amber", "no supplier" in sjs)
truthy("  and clicking it opens the list", "sourcingToggleDetail" in sjs)
# The detail panel must still list EVERY source, not the chosen one.
truthy("the panel loops over all of them", "(r.sources||[]).forEach" in sjs)

print("\n" + ("FAILURES: %s" % ", ".join(fails) if fails else "FAILURES: 0"))
sys.exit(1 if fails else 0)
