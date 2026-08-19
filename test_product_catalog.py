"""The Product Catalog -- Orbit's ASINs page.

A table of every product, and above it four sentences that each change a
decision: how concentrated the revenue is, what one suspension would cost, which
products are listed and earning nothing, and how big the tail is.

The ways this goes wrong are all about claiming more than the data supports:

  * printing "80/20" instead of counting this catalogue's real split
  * calling a product DEAD when the truth is nobody has synced its sales
  * showing a margin against a cost nobody has entered
  * a card reading "Top 0 products generate 80% of revenue"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import product_catalog as PC  # noqa: E402

FAIL = []


def check(label, got, want):
    ok = got == want
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def close(label, got, want, tol=0.01):
    ok = got is not None and abs(got - want) <= tol
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want~%r" % (got, want)))
    if not ok:
        FAIL.append(label)


def truthy(label, got):
    check(label, bool(got), True)


def row(asin, units, rev, date="2026-08-01", parent="", sessions=0):
    return {"asin": asin, "units": units, "ordered_sales": rev, "date": date,
            "parent_asin": parent, "orders": units, "sessions": sessions,
            "currency": "GBP"}


print("== days fold into one row per product ==")
t = PC.totals([row("B001", 2, 20.0, "2026-08-01"),
               row("B001", 3, 30.0, "2026-08-02"),
               row("B002", 1, 5.0, "2026-08-01")])
check("two products", sorted(t), ["B001", "B002"])
check("  units add up", t["B001"]["units"], 5.0)
check("  and so does revenue", t["B001"]["revenue"], 50.0)
check("  the window is recorded", (t["B001"]["first"], t["B001"]["last"]),
      ("2026-08-01", "2026-08-02"))
# The account rollup row must never be counted as a product.
check("the asin='*' rollup is not a product",
      sorted(PC.totals([row("*", 99, 999.0), row("B001", 1, 1.0)])), ["B001"])

print("\n== the 80/20 split is COUNTED, not assumed ==")
# "80/20" is a slogan. What this catalogue's split actually is happens to be the
# entire point of the card.
one_big = [row("B%03d" % i, 1, 1.0) for i in range(1, 10)]
one_big.append(row("BIG", 1, 91.0))
b = PC.build(one_big)
f = b["findings"]
check("one product carrying almost everything is n=1",
      f["concentration"]["n"], 1)
truthy("  and the sentence says so",
       "Top 1 product" in f["concentration"]["label"])
# "Top 1 product ... make 80%" reads as a typo and undermines a card whose whole
# job is to be a plain readable sentence. Found on the live screen.
truthy("  with the verb agreeing", "makes 80%" in f["concentration"]["label"])
# An even catalogue needs most of its products to reach 80%.
even = [row("B%03d" % i, 1, 10.0) for i in range(1, 11)]
fe = PC.build(even)["findings"]
check("an even catalogue needs 8 of 10", fe["concentration"]["n"], 8)
truthy("  which is a different sentence entirely",
       "Top 8 products" in fe["concentration"]["label"])
truthy("  and the verb is plural there",
       "make 80%" in fe["concentration"]["label"]
       and "makes 80%" not in fe["concentration"]["label"])

print("\n== the top performer ==")
close("its share is real", f["top"]["share"], 0.91)
check("  and it names the product", f["top"]["asin"], "BIG")

print("\n== dead is 'listed and earning nothing', not 'unknown' ==")
# A product with no sales ROW might be dead, or might simply predate the sync.
# Counting the second as the first turns a reporting gap into an accusation, so
# the caller says which products the catalogue knows about.
b = PC.build([row("B001", 5, 50.0)], extra_asins=["B002", "B003"])
check("products with no sales still appear", b["products"], 3)
check("  they are counted as dead", b["findings"]["dead"]["n"], 2)
truthy("  and named", "B002" in b["findings"]["dead"]["asins"])
check("  their revenue is zero, not missing",
      [r["revenue"] for r in b["rows"] if r["asin"] == "B002"], [0.0])
# Nothing passed in means nothing claimed.
nb = PC.build([row("B001", 5, 50.0)])
check("without that list, nothing is called dead", nb["findings"]["dead"], None)

print("\n== a margin needs a cost ==")
# A margin against a missing cost reads as "this product makes 100%".
b = PC.build([row("B001", 10, 100.0), row("B002", 10, 100.0)],
             costs={"B001": 4.0})
r1 = [r for r in b["rows"] if r["asin"] == "B001"][0]
r2 = [r for r in b["rows"] if r["asin"] == "B002"][0]
check("a known cost gives a cost total", r1["cogs_total"], 40.0)
close("  and a margin", r1["margin"], 0.60)
check("an unknown cost gives no cost total", r2["cogs_total"], None)
check("  and NO margin", r2["margin"], None)
# The cost may be keyed by SKU rather than ASIN.
b = PC.build([row("B001", 10, 100.0)],
             names={"B001": {"sku": "SKU-1", "title": "T"}},
             costs={"SKU-1": 2.5})
check("a cost held against the SKU is found",
      [r["cogs_total"] for r in b["rows"]], [25.0])

print("\n== the tail is sized ==")
many = [row("B%03d" % i, 1, float(100 - i)) for i in range(1, 21)]
lf = PC.build(many)["findings"]["losers"]
check("the bottom fifth is four of twenty", lf["n"], 4)
truthy("  with its share of revenue", lf["share"] is not None)
truthy("  said in words", "bottom 4" in lf["label"])
truthy("  with the verb agreeing there too", "make " in lf["label"])
one = PC.build([row("A", 1, 9.0), row("B", 1, 1.0)])["findings"]["losers"]
truthy("  and singular when the tail is one product", "makes " in one["label"])

print("\n== nothing is claimed about an empty catalogue ==")
e = PC.build([])
check("no products", e["products"], 0)
check("  no concentration claim", e["findings"]["concentration"], None)
check("  no top performer", e["findings"]["top"], None)
check("  no dead count", e["findings"]["dead"], None)
check("  and no losers", e["findings"]["losers"], None)
# A catalogue that exists but sold nothing must not claim a concentration.
z = PC.build([row("B001", 0, 0.0)])
check("a catalogue with no revenue claims no concentration",
      z["findings"]["concentration"], None)
check("  but does report the dead product", z["findings"]["dead"]["n"], 1)

print("\n== parents and variations are counted from the rows ==")
c = PC.build([row("C1", 1, 1.0, parent="P1"),
              row("C2", 1, 1.0, parent="P1"),
              row("S1", 1, 1.0, parent="")])["counts"]
check("one parent", c["parents"], 1)
check("  two variations", c["variations"], 2)
check("  one standalone", c["standalone"], 1)
# A row naming ITSELF as parent is a parent, not its own child.
c2 = PC.build([row("P1", 1, 1.0, parent="P1")])["counts"]
check("a product that is its own parent is not a variation", c2["variations"], 0)

print("\n== ranking ==")
b = PC.build([row("LOW", 1, 5.0), row("HIGH", 1, 50.0), row("MID", 1, 20.0)])
check("sorted by revenue", [r["asin"] for r in b["rows"]], ["HIGH", "MID", "LOW"])
check("  and ranked", [r["rank"] for r in b["rows"]], [1, 2, 3])
close("  with each one's share", b["rows"][0]["share"], 50.0 / 75.0)

print("\n%d failed" % len(FAIL))
for f_ in FAIL:
    print("  -", f_)
sys.exit(1 if FAIL else 0)
