"""Leading Indicators -- yesterday against its own history, in sigma.

    Orbit's screen shows each figure for yesterday next to the historical mean
    and standard deviation, expressed in standard deviations, with an ON TRACK
    status.

The whole value of this screen is that it does NOT fire on ordinary noise. So
this test is mostly about the ways it could look authoritative and be
meaningless:

  * a standard deviation computed from four days
  * an infinite sigma because the figure has never moved
  * a baseline that includes the very day being judged, which shrinks every
    genuine spike exactly when the spike is biggest
  * a missing day counted as a zero
  * conversion averaged across products instead of recomputed from its parts
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain import leading as L  # noqa: E402

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


def days(n, start="2026-07-01"):
    import datetime
    d0 = datetime.date.fromisoformat(start)
    return [(d0 + datetime.timedelta(days=i)).isoformat() for i in range(n)]


print("== which way is good is written down ==")
# A rising ACOS and rising sales are both "up". Treating them alike gets one of
# them exactly backwards, and nothing in the numbers says which.
truthy("every indicator declares a direction",
       all(i.get("good") in (L.HIGHER_IS_BETTER, L.LOWER_IS_BETTER)
           for i in L.INDICATORS))
check("sessions: more is better", L.INDEX["sessions"]["good"], L.HIGHER_IS_BETTER)
check("conversion: more is better", L.INDEX["conversion"]["good"], L.HIGHER_IS_BETTER)

print("\n== a small sample has no opinion ==")
# Four days of history is not a measure of anything. Reporting a confident sigma
# from it is the easiest way for this screen to be authoritative and meaningless.
vals = {d: 100 for d in days(5)}
vals["2026-07-05"] = 400
a = L.assess(vals, "2026-07-05", L.HIGHER_IS_BETTER)
check("no sigma below the floor", a["sigma"], None)
check("  the status is unknown, not a pass", a["status"], L.UNKNOWN)
truthy("  and it says why", "Not enough history" in a["note"])
check("  the day count is reported", a["days"], 4)

print("\n== a flat history has no sigma ==")
# Standard deviation zero means every deviation is infinite. True and useless.
flat = {d: 50.0 for d in days(20)}
flat["2026-07-20"] = 51.0
a = L.assess(flat, "2026-07-20", L.HIGHER_IS_BETTER)
check("no infinite sigma", a["sigma"], None)
truthy("  explained in words", "not varied at all" in a["note"])
check("  but the change is still reported", round(a["change"], 2), 1.0)

print("\n== yesterday is not in its own baseline ==")
# Including it drags the mean towards the value being judged and shrinks the
# spike -- worst exactly when the spike is biggest.
base = {d: 100.0 for d in days(20)}
base["2026-07-10"] = 120.0   # a little ordinary variation so stdev > 0
base["2026-07-13"] = 80.0
spike_day = "2026-07-20"
base[spike_day] = 300.0
a = L.assess(base, spike_day, L.HIGHER_IS_BETTER)
check("the baseline is the days BEFORE", a["days"], 19)
# The 19 prior days are seventeen at 100, one at 120 and one at 80 -- which is
# 1900/19 = exactly 100. If the spike had been counted the mean would be 110.
close("  the mean excludes the spike", a["mean"], 100.0)
truthy("  and is nowhere near what including it would give",
       abs(a["mean"] - 110.0) > 5)
truthy("  the spike is large in sigma", a["sigma"] > 4)
check("  and it reads as on track, because up is good here",
      a["status"], L.ON_TRACK)

print("\n== the sign follows the direction, once ==")
# Signed so positive always means BETTER, so no caller has to remember which way
# round each indicator runs.
drop = dict(base)
drop[spike_day] = 20.0
a_hi = L.assess(drop, spike_day, L.HIGHER_IS_BETTER)
truthy("a fall is negative when higher is better", a_hi["sigma"] < 0)
check("  and off track", a_hi["status"], L.OFF)
a_lo = L.assess(drop, spike_day, L.LOWER_IS_BETTER)
truthy("the same fall is POSITIVE when lower is better", a_lo["sigma"] > 0)
check("  and on track", a_lo["status"], L.ON_TRACK)

print("\n== a missing day is not a zero ==")
rows = []
for d in days(20):
    rows.append({"date": d, "sessions": 100, "units": 5, "ordered_sales": 50.0,
                 "page_views": 120, "orders": 5, "buy_box_pct": 90.0})
# One day simply has no row -- Amazon has not reported it.
gone = rows.pop(7)["date"]
s = L.series(rows, L.INDEX["sessions"])
check("the unreported day is absent, not 0", gone in s, False)
check("  and every other day is there", len(s), 19)
truthy("  no zero was invented", 0 not in s.values())

print("\n== a rate is recomputed, never averaged ==")
# Averaging conversion across products weights a product with four sessions the
# same as one with four thousand.
two = [
    {"date": "2026-08-01", "units": 1, "sessions": 4},        # 25%
    {"date": "2026-08-01", "units": 40, "sessions": 4000},    # 1%
]
conv = L.series(two, L.INDEX["conversion"])
# Correct: (1+40) / (4+4000) = 41/4004 = 1.024%. Averaging gives 13%.
close("conversion comes from the totals", conv["2026-08-01"], 41.0 / 4004 * 100)
truthy("  not the mean of the two rates", abs(conv["2026-08-01"] - 13.0) > 5)

print("\n== the double-counting trap ==")
# FOUND BY RUNNING THE REAL SCREEN AGAINST REAL DATA, not by reading the code.
# sales_daily stores every day TWICE: an asin='*' account rollup AND one row per
# real ASIN. jack_uk has 188 rollup rows and 154 per-ASIN rows and they OVERLAP,
# so the first version of the query summed both and doubled every such day.
# domain/order_profit.py had already recorded this exact trap -- "which is how
# 11.60 first looked like 23.20".
#
# The route now takes the rollup alone. The arithmetic here is what would happen
# if it ever stopped doing so, so the consequence is visible rather than
# theoretical.
mixed = [
    {"date": "2026-08-01", "asin": "*", "units": 10, "sessions": 100},
    {"date": "2026-08-01", "asin": "B001", "units": 6, "sessions": 60},
    {"date": "2026-08-01", "asin": "B002", "units": 4, "sessions": 40},
]
both = L.series(mixed, L.INDEX["units"])
check("summing a mixed day doubles it -- which is why the route filters",
      both["2026-08-01"], 20.0)
rollup_only = [r for r in mixed if r["asin"] == "*"]
check("  the rollup alone is the true figure",
      L.series(rollup_only, L.INDEX["units"])["2026-08-01"], 10.0)
per_asin_only = [r for r in mixed if r["asin"] != "*"]
check("  and the per-ASIN rows alone agree with it",
      L.series(per_asin_only, L.INDEX["units"])["2026-08-01"], 10.0)
# Proven in the route rather than here, because it is a SQL decision:
LR = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "routes", "leading_routes.py"), encoding="utf-8").read()
truthy("the route asks for the rollup row only", "AND asin='*' " in LR)
truthy("  and falls back to per-ASIN when there is no rollup",
       "AND asin<>'*' " in LR)

print("\n== the whole screen ==")
rows = []
for i, d in enumerate(days(30)):
    rows.append({"date": d, "sessions": 100 + (i % 5), "units": 5,
                 "ordered_sales": 50.0, "page_views": 120, "orders": 5,
                 "buy_box_pct": 90.0})
day = days(30)[-1]
out = L.build(rows, day=day)
check("every indicator is judged", len(out["indicators"]), len(L.INDICATORS))
check("  for the day asked for", out["day"], day)
truthy("  each carries its own plain-English blurb",
       all(i.get("blurb") for i in out["indicators"]))
truthy("  and a trail to draw", all("trail" in i for i in out["indicators"]))
truthy("  the trail is at most a fortnight",
       all(len(i["trail"]) <= 14 for i in out["indicators"]))
truthy("  the statuses are counted",
       (out["on_track"] + out["watch"] + out["off"] + out["unknown"])
       == len(L.INDICATORS))

print("\n== the day is yesterday, never today ==")
# Amazon's report for the current day is partial all day; judging a part-day
# against whole days would make every morning look like a collapse.
check("yesterday of 2026-08-19", L.yesterday("2026-08-19"), "2026-08-18")

print("\n== nothing at all ==")
out = L.build([], day="2026-08-18")
check("an empty account does not crash", len(out["indicators"]), len(L.INDICATORS))
check("  and everything is unknown", out["unknown"], len(L.INDICATORS))
truthy("  with nothing counted as on track", out["on_track"] == 0)

print("\n%d failed" % len(FAIL))
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)
