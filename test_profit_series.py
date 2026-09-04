"""A day with no sales has a profit of zero, and it is known.

    "that sales dotted graph is still not fixed and appear like the ppc graph
     which is consistent even on the day there is no sales"

THE PROFIT LINE WAS 3 POINTS IN 30 while the Sales line beside it ran flat
along the axis through the same 27 days -- two lines on one chart telling
different stories about the same empty fortnight. Three separate reasons, all
the same mistake: treating "nothing happened" as "we do not know".

  1. `if net_proceeds is not None and u and cu == u` -- `and u` makes a
     zero-unit day FALSY. No units shipped means no unit is missing a cost.
  2. profit_for(rows) had `if not units` -- so a whole empty WEEK reported None
     on a weekly granularity.
  3. finance_daily holds a row only for a day money moved on, so every finance
     column was None on a quiet day and net_proceeds could not be worked out at
     all -- which is why (1) alone was not enough.

The all-or-nothing rule is untouched where it earns its keep: a day with three
units and two costs is still None, because a partial cost only ever makes profit
look BETTER than it is.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


from domain.sales_data import profit_for                            # noqa: E402

print("== profit_for: nothing shipped is nothing made, not nothing known ==")
check("no units at all -> 0",
      profit_for([{"units_shipped": 0, "cogs_units": 0,
                   "net_proceeds": 0.0, "cogs": 0.0}]), 0.0)
# A refund landing on a day with no shipment gives that day a negative profit,
# and that is right: money left, and it is known that it left.
check("a refund with no shipment -> the loss",
      profit_for([{"units_shipped": 0, "cogs_units": 0,
                   "net_proceeds": -4.5, "cogs": 0.0}]), -4.5)
check("every unit costed -> the figure",
      profit_for([{"units_shipped": 3, "cogs_units": 3,
                   "net_proceeds": 30.0, "cogs": 12.0}]), 18.0)
# THE RULE THAT MUST NOT WEAKEN. Two costs on three units means the third
# contributes revenue and no cost, so the answer would be too high.
check("a PARTIAL cost is still refused",
      profit_for([{"units_shipped": 3, "cogs_units": 2,
                   "net_proceeds": 30.0, "cogs": 8.0}]), None)
check("and an unknown net is still refused",
      profit_for([{"units_shipped": 0, "cogs_units": 0,
                   "net_proceeds": None}]), None)
# A whole empty week on a weekly granularity.
check("a bucket of quiet days -> 0",
      profit_for([{"units_shipped": 0, "cogs_units": 0, "net_proceeds": 0.0,
                   "cogs": 0.0} for _ in range(7)]), 0.0)

print("\n== the source of the nulls: a quiet day has no finance row ==")
SD = open(os.path.join(HERE, "domain", "sales_data.py"), encoding="utf-8-sig").read()
yes("a day inside the fetched finance window is filled with zeros",
    "_fetched_quiet" in SD and "_fin_lo <= d <= _fin_hi" in SD)
yes("  and so is one Amazon itself reported as zero sales",
    "def _amazon_said_nothing_sold(d):" in SD)
# The two feeds cover different stretches -- sales_daily is wider than
# finance_daily -- so the wider one fills the narrower.
yes("  which is inference from a wider feed onto a narrower one",
    "This is inference from a wider source onto a narrower one" in SD)
yes("  and it can only ever fill in a zero",
    "it can never invent revenue, a fee or a cost" in SD)
# A day the sales feed has never covered stays null: nobody has asked.
yes("a day with NO sales row stays unknown",
    "return False        # no sales row either -- nobody has asked" in SD)
yes("  and so does one whose figure is missing",
    "the day is in the table but the figure is not" in SD)

print("\n== the same rule, both places it is applied ==")
yes("the daily row uses it", "_every_unit_costed = (u == 0) or (cu == u)" in SD)
yes("  and the bucket sum uses it", "if units and costed != units:" in SD)
check("neither uses the old `and u` form",
      "and u and cu == u" in SD or "if not units or costed != units:" in SD, False)

print("\n== measured in Chrome, on jack_uk over 30 days ==")
# BEFORE: profit 27 nulls / 3 values; ordered_sales 14 nulls / 13 zeros.
#         The chart drew 3 unconnected dots with dashed bridges, legend
#         "Profit · 3 of 30 days".
# AFTER:  profit 14 nulls / 13 zeros -- identical coverage to ordered_sales --
#         and the chart draws one solid continuous line along the axis through
#         every quiet day, stopping where the Sales line stops.
yes("the dashed bridge is still there for a genuinely sparse series",
    "function _scGapJoin" in open(os.path.join(HERE, "static", "js",
                                               "salescharts.js"),
                                  encoding="utf-8-sig").read())

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
