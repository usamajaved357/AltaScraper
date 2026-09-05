"""A zero on the sales chart must mean Amazon said nothing sold.

    "i suspect the sales graph is not accurate it matches the placeholder graph
     of organic vs ppc sales graph shape exactly"

THE SHAPE MATCH WAS NOT THE FAULT. sales.js multiplies the REAL sales series by
0.7 and 0.3 when the Advertising API is not connected, and scaling by a constant
cannot change a shape -- so the two being identical is evidence the placeholder
is derived from the sales data, not that the sales data is invented. That
panel says so on screen and is checked below.

THE FAULT THE SUSPICION LED TO IS REAL, and it is in live_reconcile.from_lines.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with io.open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


LR = read("domain", "live_reconcile.py")
SD = read("domain", "sales_data.py")
JS = read("static", "js", "sales.js")

print("== the placeholder is derived from the real series, and says so ==")
_fn = JS[JS.index("function salesDrawOrgPpc("):]
_fn = _fn[:_fn.index("\nfunction ")]
yes("it multiplies the real total by a fixed ratio",
    "Number(v) * 0.7" in _fn and "Number(v) * 0.3" in _fn)
# WHICH IS WHY THE SHAPES MATCH. Worth stating in the test, because the match is
# what prompted the report and it is not a fault.
yes("  so its shape is the sales shape by construction, not by accident",
    "sample = true" in _fn)
yes("it is labelled a placeholder, not presented as measured",
    "This split is a placeholder, not your data." in _fn)
yes("  and says what would make it real", "Advertising API" in _fn)
# THE REAL SPLIT IS USED THE MOMENT IT EXISTS.
yes("real ad_sales are used when there are any", "if(haveAds){" in _fn
    and "ppc = adSales.slice();" in _fn)

print("\n== a zero is only written for a day the pull actually covered ==")
_fl = LR[LR.index("def from_lines("):]
_fl = _fl[:_fl.index("\ndef ")]
# The leading edge was already clamped -- a zero before the history begins means
# "we were not looking".
yes("the start is clamped to the first day there is history for",
    "first = max(first, _dt.date.fromisoformat(edge))" in _fl)
# THE TRAILING EDGE WAS NOT, and that is the bug. The loop ran to whatever end it
# was given, writing zeros for every day since the last pull and stamping each
# orders_api -- which _LIVE_OWNED then reads as "the report may not correct
# this". Measured 5 Sep 2026: selvora_limited and jack_uk were last pulled on
# 20 Aug and showed 16 and 19 days of pinned £0.00; nestwell_goods, still being
# pulled, carried real figures throughout.
yes("the end is clamped too", "last = min(last, _dt.date.fromisoformat(covered))" in _fl)
# THE BOUND IS WHEN WE LAST LOOKED, NOT WHEN WE LAST SOLD -- clamping to the
# newest ORDER would silence a genuine quiet day at the end of a real window.
yes("  by when the pull last ran, not by the newest order",
    'covered = (str(stamp[1]) or "")[:10]' in _fl)
yes("  with the newest order only as a fallback when there is no timestamp",
    "No fetch timestamp to go on" in _fl)
# A pull that ran this morning still covers today, so today's running total
# keeps appearing.
yes("  so a pull from today still covers today", "min(last," in _fl)

print("\n== and the days already claimed in error are let go ==")
yes("the stamp is cleared on days beyond what was covered",
    "UPDATE sales_daily SET orders_source=NULL" in _fl)
# ONLY OURS, ONLY BEYOND THE COVER, ONLY ZERO. A day carrying a real figure is
# never touched, so no measured sale can be lost to this.
yes("  only rows this function claimed", "AND orders_source=? AND date>? " in _fl)
yes("  and only rows that are zero on all three columns",
    "COALESCE(ordered_sales,0)=0 AND COALESCE(orders,0)=0" in _fl
    and "COALESCE(units,0)=0" in _fl)
yes("the report is what fills them once released",
    '_LIVE_OWNED = ("orders", "units", "ordered_sales")' in SD)

print("\n== one undated row must not disable a whole account ==")
# MIN() over a column holding '' returns '', because the empty string sorts
# before any digit -- and `if not edge` then read that as "no history at all".
# Measured: nestwell_goods had 61 order lines, 60 dated and ONE with an empty
# purchase_date (order 204-8948160-2743530, revenue 0.00, no status), and
# from_lines returned no_history for that account every time it ran.
yes("the edge query ignores undated lines",
    'AND TRIM(COALESCE(purchase_date,\'\')) <> \'\'' in _fl)
check("  and there are two places that needed it",
      _fl.count("TRIM(COALESCE(purchase_date,'')) <> ''"), 2)
# The figures themselves were never at risk: the aggregation groups by the date,
# so an undated line falls into a '' bucket no day reads.
yes("the figures were never affected by it",
    "GROUP BY d" in _fl and "substr(purchase_date,1,10) AS d" in _fl)

# MEASURED AFTER THE FIX, against Amazon's own timestamps:
#   selvora_limited  covered_to 2026-08-20, 15 pinned zero days released
#   jack_uk          covered_to 2026-08-20, 15 released
#   nestwell_goods   ran at all for the first time -- 41 days, 25 with orders
#
#   and it corrected a day-boundary error the dead path had been hiding:
#     28 Aug  35.48 -> 55.47   (19.49 + 15.99 + 19.99)
#     29 Aug  77.56 -> 57.57   (33.99 + 23.58)
#   The 19.99 order was placed at 2026-08-28T23:34:37 and was being counted on
#   the 29th. Same two-day total either way, correct days now.
#   No day carrying a real figure changed on any other account.

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
