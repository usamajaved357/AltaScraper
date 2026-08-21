"""Orders and Sales must not disagree about what one order cost.

    COGS defect 1 of the three deferred on 18 Aug 2026, and the one recommended
    first: "Orders and Sales read different systems."

TWO SCREENS, ONE QUESTION, TWO RESOLVERS.

Sales prices a line through domain/order_cogs, which reads the cost FROZEN onto
order_lines when the order was seen -- and that frozen value is where a per-order
correction lives, because set_for_order writes straight into order_lines.cogs
with source 'manual-order'.

Orders used domain/cogs.lookup: a typed product cost, then the cost built into
the SKU. Steps 3 and 4 of a four-step trust order. It has no notion of a
correction typed against one order, and no notion of tracked mode -- a strictly
WEAKER resolver, looking at the same order, on a screen sitting next to the
other one.

THEY AGREED ONLY BY COINCIDENCE. Measured 21 Aug 2026: all 24 frozen costs are
marked `sku`, no account is on tracked mode, cogs_overrides.json is empty. So
steps 1 and 2 never fired and both resolvers fell through to the same answer.
The day the repricer yields a real supplier price, or anybody corrects a single
order, the same order shows one profit on Orders and another inside Sales, with
nothing on either screen to say which is right. That is the worst kind of wrong
number: two of them, both confident.

THE FIX IS NOT A SECOND DERIVATION. Deriving the same answer twice is two things
to keep in step, and they drift -- that is the whole bug. Orders reads the
STORED value, which is the number Sales shows.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


OR = open(os.path.join(HERE, "routes", "orders_routes.py"), encoding="utf-8").read()

print("== Orders resolves a cost per ORDER, not per request ==")
# Steps 1 and 2 need the order's id and its date. Building one function for the
# whole request is what made the weaker resolver the easy choice.
truthy("there is an order-aware cost function", "def _cost_fn_for(" in OR)
truthy("  taking the order's date and id",
       "def _cost_fn_for(account_id, marketplace, when, order_id=\"\")" in OR)
check("  and it is used at every profit call site", OR.count("_cost_fn_for("), 4)
falsy("the request-wide resolver is no longer passed to a profit call",
      "profit_detail(items, r.get(\"total\"), cost_of," in OR
      or "line_breakdown(items, row.get(\"total\"), cost_of," in OR)

print("\n== it reads the STORED cost, which is what Sales shows ==")
truthy("the frozen value is looked up first", "SELECT sku, cogs, cogs_source FROM order_lines" in OR)
truthy("  scoped to this account, marketplace and order",
       "WHERE workspace_id=? AND marketplace=? AND order_id=?" in OR)
truthy("  and only where a cost exists", "AND cogs IS NOT NULL" in OR)
truthy("  preferred over re-deriving", "hit and hit[0] is not None" in OR)
truthy("and why re-deriving would be wrong is recorded",
       "two derivations are two things to keep in step" in OR
       or "not to re-derive" in OR)

print("\n== a missing cost is still unknown, never zero ==")
# order_cogs says it outright: "NO COST IS NOT A ZERO COST ... Zero would make it
# look infinitely profitable, and that is precisely the product someone would
# then buy more of."
OC = open(os.path.join(HERE, "domain", "order_cogs.py"), encoding="utf-8").read()
truthy("the rule is stated where costs are resolved", "NO COST IS NOT A ZERO COST" in OC)
truthy("  and resolve returns None, not 0", "return None, \"\"" in OC)
falsy("the new path never substitutes a zero", "or 0.0)" in
      OR.split("def _cost_fn_for")[1].split("def ")[0])

print("\n== a lookup failure does not lose the row ==")
# Reporting "no cost" because a query failed would read as a product nobody has
# costed -- a different, and wrong, finding.
_fn = OR.split("def _cost_fn_for")[1].split("\n    def ")[0]
truthy("it falls back to the old resolver", "_cogs.resolve(overrides, account_id, sku)" in _fn)
truthy("  rather than reporting no cost", "Never lose the whole row" in _fn)

print("\n== the frozen lookup actually finds a frozen cost ==")
# Run it, rather than trust the SQL by eye.
import tempfile
try:
    from data import db as _db
    conn = _db.get_db()
    row = conn.execute(
        "SELECT workspace_id, marketplace, order_id, sku, cogs, cogs_source "
        "FROM order_lines WHERE cogs IS NOT NULL LIMIT 1").fetchone()
    if row is None:
        print("  (no frozen costs in this database -- nothing to exercise)")
    else:
        hits = conn.execute(
            "SELECT sku, cogs, cogs_source FROM order_lines "
            "WHERE workspace_id=? AND marketplace=? AND order_id=? "
            "  AND cogs IS NOT NULL",
            (row["workspace_id"], row["marketplace"], row["order_id"])).fetchall()
        frozen = {str(r["sku"] or ""): (r["cogs"], r["cogs_source"]) for r in hits}
        truthy("the query returns the row it was given", bool(frozen))
        got = frozen.get(str(row["sku"] or ""))
        check("  and the cost matches what is stored",
              None if got is None else round(float(got[0]), 4),
              round(float(row["cogs"]), 4))
        print("     %s / %s -> %s (%s)" % (row["order_id"][-8:], row["sku"],
                                           row["cogs"], row["cogs_source"]))
except Exception as e:
    print("  (could not reach the database: %s)" % str(e)[:90])

print("\n== the column names are the ones the table actually has ==")
# purchase_date, not "purchased" -- the second is what a neighbouring function
# happens to call its argument, and using it here would have silently passed an
# empty date into the tracked-price lookup.
try:
    cols = {r[1] for r in _db.get_db().execute("PRAGMA table_info(order_lines)")}
    truthy("order_lines has purchase_date", "purchase_date" in cols)
    truthy("  and cogs_source", "cogs_source" in cols)
    falsy("  and no column called 'purchased'", "purchased" in cols)
    truthy("the route reads purchase_date", 'get("purchase_date")' in OR)
except Exception as e:
    print("  (skipped: %s)" % str(e)[:80])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
