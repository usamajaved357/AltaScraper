"""A thirty-day average cannot tell selling from stopped selling.

Orbit's inventory agent, asked where its own numbers would be confidently
wrong, named this first and named it precisely:

    "A SKU being discontinued or replaced by a new ASIN. It will show low
     daysOfSupply and large stockGap30d because forecastDemand30d = 30d pace
     x 30. The dashboard still shows it as 'Order now' even if you intend to
     let it sell out. How to spot: if trend is -97% and daily units went
     18,16,15... to 0 for the last week, the 30d pace is stale."

That is the expensive direction to be wrong in. Every other error on this
screen makes somebody look twice; this one tells them to BUY. A product that
sold well for three weeks and nothing since leaves exactly the same thirty-day
average behind it as one still selling.

WHAT THE FIX DOES NOT DO. It does not clear the shortfall or change a status.
The arithmetic is right -- it is real units over real in-stock days. What is in
doubt is whether those days still describe next month, and only the owner knows
whether a listing is being retired. So the row is MARKED and sorted below the
live ones, and the figures are left alone.
"""
import datetime as _dt
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import stock_metrics as SM

TODAY = "2026-08-20"
DAYS = SM._days("2026-07-22", TODAY)          # 30 days


def units(pattern):
    """Map the last len(pattern) days to these unit counts."""
    out = {}
    for d, n in zip(DAYS[-len(pattern):], pattern):
        out[d] = float(n)
    return out


print("== a run of sellable days with no sales is counted ==")
# Sold every day for three weeks, then nothing for the last ten.
sold = [6] * 20 + [0] * 10
check("ten quiet days at the end", SM._quiet_run(DAYS, DAYS, units(sold)), 10)
# Still selling: the run is zero even though there are zeros earlier.
mixed = [6] * 20 + [0] * 8 + [4, 2]
check("a zero followed by a sale ends the run",
      SM._quiet_run(DAYS, DAYS, units(mixed)), 0)
check("a product selling every day has no quiet run",
      SM._quiet_run(DAYS, DAYS, units([5] * 30)), 0)

print("\n== a day it could not be bought says nothing either way ==")
# The last 4 days out of stock, before that it was selling. Those 4 days must
# not be read as "nobody wanted it" -- the same reason the pace excludes them.
in_stock = DAYS[:-4]
check("out-of-stock days do not extend the quiet run",
      SM._quiet_run(DAYS, in_stock, units([5] * 26 + [0, 0, 0, 0])), 0)
# ...but quiet days BEFORE the stockout still count.
check("  while quiet in-stock days before it still count",
      SM._quiet_run(DAYS, in_stock, units([5] * 14 + [0] * 12 + [0, 0, 0, 0])), 12)

print("\n== the threshold is a fortnight of silence, not a single quiet day ==")
truthy("ten quiet days is enough to mark it",
       SM.QUIET_DAYS_FOR_STALE <= 10)
falsy("  but a couple of quiet days is not",
      3 >= SM.QUIET_DAYS_FOR_STALE)

print("\n== the row is marked, and the arithmetic is left alone ==")
src = open(os.path.join(HERE, "domain", "stock_metrics.py"), encoding="utf-8").read()
truthy("the row carries the flag", '"pace_is_stale": bool(stale_why)' in src)
truthy("  and says why in words", '"stale_why": stale_why' in src)
truthy("  and how many quiet days", '"quiet_days": quiet' in src)
# The status must NOT be rewritten -- a shortfall is still a shortfall.
falsy("the status is not overwritten",
      'status = "ok"' in src.split("stale_why = \"\"")[1]
      if "stale_why = \"\"" in src else False)
truthy("a sharp fall also counts, not only silence", "trend <= -80" in src)

print("\n== and it sorts below the live shortfalls ==")
truthy("stale rows sort after live ones",
       '1 if r.get("pace_is_stale") else 0' in src)
truthy("  and are counted for the screen",
       'counts["stale_pace"]' in src)

print("\n== the screen says it on the row, not in a tooltip ==")
ST = open(os.path.join(HERE, "static", "js", "stock.js"), encoding="utf-8").read()
truthy("the warning is drawn", "r.pace_is_stale" in ST)
truthy("  naming the number of quiet days", "sellable days" in ST)
truthy("  and telling the reader what to do", "check before ordering" in ST)

print("\n== and the screen explains how to audit it ==")
truthy("stock_metrics offers the check", '"how_to_check"' in src)
truthy("  naming the pace as the number to check",
       "the days it was in stock, add up the units sold on" in src)
truthy("  saying what else is wrong if it is wrong",
       "everything else on this screen is wrong with it" in src)
truthy("and the screen prints it", "How to check this by hand" in ST)

print("\n== and the table can leave the screen ==")
#     Ava, listing what each of Orbit's pages exports:
#     "Inventory / Restock: CSV of stock + days-of-cover + restock suggestions."
#
# This is the one list somebody works THROUGH -- ordering against it, checking
# it with a supplier -- and it was the only screen of its kind with no way to
# get the list out.
IR = open(os.path.join(HERE, "routes", "inventory_routes.py"),
          encoding="utf-8").read()
truthy("there is an export", '"/inventory/coverage.csv"' in IR)
truthy("  built from the same function as the screen", "_sm.for_account(" in IR)
truthy("  through the shared CSV writer, not a comma join",
       "_sheets.to_csv(" in IR)
falsy("  and it writes no CSV of its own", "csv.writer(" in IR)
# A spreadsheet loses the screen's estimate markers the moment it is opened: a
# column called "Cover" in Excel looks exactly as solid as "On hand".
truthy("the estimated columns say so in their own names",
       '"30-day demand (ESTIMATE)"' in IR
       and '"Days of cover (ESTIMATE)"' in IR
       and '"Short by (ESTIMATE)"' in IR)
truthy("  and the measured ones do not", '"On hand", "Available"' in IR)
# A reader who is sent the file and never saw the screen still gets told.
truthy("the caveats travel with the file",
       'got.get("estimate_note")' in IR and 'got.get("gap_is_not_a_po")' in IR)
truthy("  including how to check the pace by hand",
       'got.get("how_to_check")' in IR)
truthy("  after a blank row, so a sort cannot mistake them for data",
       '[""] * len(headers)' in IR)
truthy("and the screen offers it", "/inventory/coverage.csv" in ST)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
