"""What was counted, and what was assumed, are not the same claim.

    Ava, asked whether it ever estimates or fills a gap:
    "No for financials ... Only labeled estimates are forward-looking inventory
     math: days-of-cover, stockout risk, restock suggestion -- these ARE
     estimates by definition. I label them."

That line is worth keeping. What a product HAS and what it DID are counted; what
it WILL do is arithmetic resting on the assumption that the next thirty days
look like the last thirty. Printing both in the same typeface invites the second
to be trusted like the first -- and the second is the one that gets quoted in a
purchasing decision.

And a period that has not finished is not a period. Comparing a part-month
against a whole one and reading the difference as a fall is the easiest mistake
on any money screen.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import stock_metrics as SM

print("== the two lists exist and do not overlap ==")
src = open(os.path.join(HERE, "domain", "stock_metrics.py"), encoding="utf-8").read()
truthy("measured fields are named", '"measured": measured' in src)
truthy("estimated fields are named", '"estimated": estimated' in src)

# Pull them out of the source so the test reads the real lists.
import ast
tree = ast.parse(src)
lists = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        t = node.targets[0]
        if isinstance(t, ast.Name) and t.id in ("measured", "estimated"):
            try:
                lists[t.id] = ast.literal_eval(node.value)
            except Exception:
                pass
truthy("both lists were read", set(lists) == {"measured", "estimated"})
check("nothing is in both", sorted(set(lists["measured"]) & set(lists["estimated"])), [])

print("\n== the right things are in each ==")
# Counted: what is there, what sold, how often it was sellable.
for f in ("on_hand", "days_known", "oos_days", "in_stock_rate", "pace_30d"):
    truthy("%s is a measurement" % f, f in lists["measured"])
# Assumed: everything that describes a future.
for f in ("forecast_demand_30d", "days_of_cover", "stock_gap_30d"):
    truthy("%s is an estimate" % f, f in lists["estimated"])

print("\n== and it says so in words, not only in a key ==")
truthy("the note explains the difference",
       "ESTIMATES" in SM.for_account.__doc__ or "estimate_note" in src)
truthy("  naming the assumption",
       "assume the next thirty days look like" in src)

print("\n== the screen marks the estimated columns ==")
ST = open(os.path.join(HERE, "static", "js", "stock.js"), encoding="utf-8").read()
truthy("an Est. marker exists", "const EST =" in ST)
for col in ("30-day demand", "Cover", "Short by"):
    truthy("  '%s' carries it" % col, ("'" + col + "' + EST") in ST
           or ('"' + col + '\' + EST') in ST or (col + "' + EST") in ST)
# The measured columns must NOT be marked, or the distinction says nothing.
truthy("  'Pace / day' does not", "Pace / day' + EST" not in ST)
truthy("  'In stock' does not", "In stock' + EST" not in ST)

print("\n== a period that includes today says so ==")
FIN = open(os.path.join(HERE, "static", "js", "finance.js"), encoding="utf-8").read()
truthy("Finance checks whether the window reaches today",
       "FIN.meta.end >= _today" in FIN)
truthy("  and says the period is not over", "not over" in FIN)
# The reason it matters, not just the fact.
truthy("  and why that matters for a comparison",
       "reads as a fall that has not happened" in FIN)
truthy("  and that Amazon keeps posting after the day",
       "posts fees and refunds for a day after" in FIN)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
