"""A calendar month is not thirty days.

    Ava, on its own most common way of giving an answer that looks right and
    is not:

    "Mixing time grains. get_brand_snapshot = calendar month MTD ...
     get_morning_brief = last 30d ... User asks 'last month' and I answer with
     30d comparison if I don't label grain. Looks right, 9 days off."

Nine days off, on a money screen, with nothing on the page saying which was
used. The fix is not to choose the better grain -- there isn't one -- it is to
offer BOTH BY NAME so neither can stand in for the other, and to make the
assistant say which it used.

The arithmetic below is the part that quietly breaks: a month is 28, 29, 30 or
31 days, and "the first of last month to the last of last month" has to be
right in all four cases, including across a year boundary and in a leap year.
"""
import datetime as _dt
import os
import re
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


# The rule as sales_routes._range implements it, exercised directly so the
# arithmetic is tested rather than the routing.
def last_month(today):
    end = _dt.date.fromisoformat(today) - _dt.timedelta(days=1)   # yesterday
    last_end = end.replace(day=1) - _dt.timedelta(days=1)
    return last_end.replace(day=1).isoformat(), last_end.isoformat()


def this_month(today):
    end = _dt.date.fromisoformat(today) - _dt.timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat()


def rolling(today, days):
    end = _dt.date.fromisoformat(today) - _dt.timedelta(days=1)
    return (end - _dt.timedelta(days=days - 1)).isoformat(), end.isoformat()


print("== last month is the whole previous calendar month ==")
check("from 20 Aug", last_month("2026-08-20"), ("2026-07-01", "2026-07-31"))
check("  a 30-day month", last_month("2026-07-05"), ("2026-06-01", "2026-06-30"))
check("  across the new year", last_month("2027-01-09"), ("2026-12-01", "2026-12-31"))
check("  February, ordinary year", last_month("2027-03-04"), ("2027-02-01", "2027-02-28"))
check("  February, leap year", last_month("2028-03-04"), ("2028-02-01", "2028-02-29"))
# The first of the month is the awkward one: yesterday is in the month before,
# so "last month" is the month before THAT.
check("  asked on the 1st", last_month("2026-08-01"), ("2026-06-01", "2026-06-30"))

print("\n== and it is genuinely a different period from 30 days ==")
lm = last_month("2026-08-20")
r30 = rolling("2026-08-20", 30)
truthy("they do not match", lm != r30)
d = (_dt.date.fromisoformat(lm[0]) - _dt.date.fromisoformat(r30[0])).days
# Ava's "9 days off" was MTD against a rolling 30. Last-month against a rolling
# 30 is further apart still -- they do not even overlap on the end date.
check("  twenty days apart at the start, asked on 20 August", abs(d), 20)
truthy("  and they do not share an end date either", lm[1] != r30[1])
# Nor is "this month" the same as either -- that one is also partial.
tm = this_month("2026-08-20")
truthy("this month is a third, shorter period", tm[0] > lm[1])
check("  and it is partial: 19 days, not a month",
      (_dt.date.fromisoformat(tm[1]) - _dt.date.fromisoformat(tm[0])).days + 1, 19)

print("\n== both grains exist by name on the server ==")
src = open(os.path.join(HERE, "routes", "sales_routes.py"), encoding="utf-8").read()
truthy("lastmonth is a preset", 'preset in ("lastmonth", "last_month")' in src)
truthy("  and mtd is too", 'if preset == "mtd":' in src)
truthy("  with the reason recorded", "A CALENDAR MONTH IS NOT THIRTY DAYS" in src)

print("\n== and on the screen ==")
fin = open(os.path.join(HERE, "static", "js", "finance.js"), encoding="utf-8").read()
truthy("a Last month chip exists", '"Last month"' in fin)
truthy("  alongside 30 days, so neither stands in for the other",
       '"30 days"' in fin and '"This month"' in fin)
# Day 0 of this month is the last day of the previous one -- which is how the
# browser side avoids needing to know how long February was.
truthy("  and the browser uses day 0 rather than counting days",
       "end.setDate(0)" in fin)

print("\n== the assistant is told they are different ==")
at = open(os.path.join(HERE, "domain", "agent_tools.py"), encoding="utf-8").read()
truthy("the preset list offers both", "lastmonth" in at and "mtd" in at)
truthy("  and warns they are not interchangeable",
       "nine days wrong in August" in at)
truthy("  and says what to do when the question is ambiguous",
       "say which you used, and offer the other" in at)
ar = open(os.path.join(HERE, "routes", "agent_routes.py"), encoding="utf-8").read()
truthy("the system prompt names the grain rule", "WHICH PERIOD, EXACTLY" in ar)
truthy("  and requires it in the answer", "used in the answer, every time" in ar)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
