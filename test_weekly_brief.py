"""The summary nobody had to ask for.

    Ava, asked what it would write every week without being prompted:
    "Headline ... winners/losers ... Profit truth: net profit after fees, with
     COGS coverage % - why: revenue lies if cost missing ... Off-track reds ...
     Never sums 3P+1P, always labels partial month."

And on the question that surfaces what you have not noticed:

    "Rank off-track sigma across all 10 marketplaces - what's the top 3 reds
     brand-wide this week? - you'll miss BE/NL/SE otherwise."

Every other screen here is scoped to the account you have open, which is right
for working and wrong for noticing: the account with a problem this week is the
one nobody opened. This is the only screen that looks everywhere at once.

THE TWO THINGS MOST WORTH HOLDING OPEN

A FALLER MUST HAVE FALLEN. Taking the two lowest movers reported "biggest
fallers: +201%, +2157%" on a week where every account grew. True as an
ordering, false as a sentence -- and the sentence is what gets read.

NOTHING IS SUMMED ACROSS CURRENCIES. jack_uk sells in GBP and sheelady_us in
USD; "total revenue 12,400" across the two is a number with no unit that
flatters whichever way the rate has moved. The absence of a headline total is
deliberate and is asserted here so nobody adds one back.
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
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import weekly_brief as WB

print("== a change needs a baseline to be a change ==")
check("ordinary growth", WB._pct(150, 100), 50.0)
check("  and a fall", WB._pct(50, 100), -50.0)
check("no baseline is not infinite growth", WB._pct(150, 0), None)
check("  and neither is nothing at all", WB._pct(0, 0), None)
check("nothing to compare gives nothing", WB._pct(None, 100), None)
check("  text is not a figure", WB._pct("n/a", 100), None)

print("\n== the window is seven WHOLE days, ending yesterday ==")
check("seven days back", WB._days_ago("2026-08-19", 6), "2026-08-13")
check("  and the week before that", WB._days_ago("2026-08-19", 13), "2026-08-06")
check("  across a month boundary", WB._days_ago("2026-09-03", 6), "2026-08-28")

print("\n== a faller must actually have fallen ==")
src = open(os.path.join(HERE, "domain", "weekly_brief.py"), encoding="utf-8").read()
truthy("the fallers list is filtered by sign",
       'r["change_pct"] < 0' in src)
truthy("  and the risers too", 'r["change_pct"] > 0' in src)
truthy("  with the measurement recorded beside it",
       "biggest fallers: +201%, +2157%" in src)
# Both lists must be able to be EMPTY. A week where everything grew has no
# fallers, and inventing two is the bug this replaced.
truthy("  so either list can come back empty", "[:2]" in src)

print("\n== nothing is summed across currencies ==")
truthy("the refusal is stated", "no_total" in src)
truthy("  in words, on the response",
       "a number with no unit" in src)
# The one thing that must never appear: a single revenue figure for everything.
falsy("there is no brand-wide revenue total",
      "brand_revenue" in src or "total_revenue" in src)
truthy("every row carries its own currency", '"currency": now.get("currency")' in src)

print("\n== a section that could not look says so ==")
truthy("each section collects its own notes", 'brief[key].get("notes")' in src)
truthy("  and they are gathered in one place", '"could_not_look"' in src)
# The distinction that a zero cannot make.
truthy("no ad data is not the same as no ad spend",
       "That is not the same as spending nothing" in src)
truthy("  and it says profit has no ad spend taken off",
       "no ad " in src and "spend subtracted from them" in src)

print("\n== profit is reported with its coverage, never without ==")
truthy("cost coverage is read per account", "_cogs.coverage(" in src)
truthy("  the percentage comes from cogs, not recomputed here",
       'entry["coverage_pct"] = cov.get("pct")' in src)
truthy("  and the uncosted products are named, so it is a job",
       '"missing_skus"' in src)
truthy("  with the reason spelled out",
       "ever be flattered" in src)

print("\n== it reads the daily rows the same way the other screen does ==")
# Two copies of that query would be two opinions about what a day's figures
# are, and the disagreement would be a silent doubling.
truthy("it calls the shared reader", "_lead.rows_for(" in src)
falsy("  and has no SQL of its own for sales_daily",
      "FROM sales_daily" in src)

print("\n== a near miss is not a red ==")
truthy("only OFF is carried", "!= _lead.OFF" in src)
truthy("  and WATCH is deliberately left out",
       "a brief nobody finishes" in src)

print("\n== stock: a shortfall on a pace that has stopped is not urgent ==")
truthy("stale rows are kept out of the running-out list",
       'not r.get("pace_is_stale")' in src)
truthy("  and the reason is given",
       "on a pace that has stopped." in src)

print("\n== and it says which period it is ==")
truthy("the period is stated once, plainly", '"period_note"' in src)
truthy("  and why it ends yesterday",
       "Amazon has no figures for today" in src)

print("\n== the route ==")
br = open(os.path.join(HERE, "routes", "brief_routes.py"), encoding="utf-8").read()
truthy("GET only", 'methods=["GET"]' in br)
truthy("  it is not scoped to the open account",
       "NOT SCOPED TO THE OPEN ACCOUNT" in br)
truthy("  a bad date is refused rather than guessed", "Bad date" in br)
dash = open(os.path.join(HERE, "dashboard.py"), encoding="utf-8").read()
truthy("and it is registered", "_brief_routes.register(" in dash)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
