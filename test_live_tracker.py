"""domain/live_tracker.py -- the Live Tracker.

THE PAGE IS NAMED AFTER SOMETHING THAT DOES NOT EXIST.

LIVE-TRACKER-BUILD-PROMPT.md is an hourly page: "Last 24 Hours" and "Last 7
Days" both plot one point per hour. Amazon publishes no hourly advertising data
and will not be persuaded to -- asked directly on 6 Sep 2026, spCampaigns,
spAdvertisedProduct and the placement report each refused timeUnit HOURLY with
"configuration timeUnit is not supported for this report type".

So the checks here are mostly about what the page must NOT do: claim hourly data
is available, carry a cumulative line flat across a day nobody measured, invent
a units figure that is really the order count under another name, or split a
campaign's placement spend across the ASINs it advertises.

The placement breakdown IS real -- that request was accepted -- and it lives in
its own table for a reason the two-grain bug already taught this app once.
"""
import datetime as _dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                        # noqa: E402
from domain import live_tracker as _lt            # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT = "__livetrack__", "UK"
conn = _db.get_db()
for t in ("ads_daily", "sales_daily", "ads_placement_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

TODAY = _dt.date.today()


def day(n):
    return (TODAY - _dt.timedelta(days=n)).isoformat()


# Four days of advertising, with a DELIBERATE HOLE two days ago: Amazon sent
# nothing for it. Everything below turns on that hole being treated as unknown
# rather than as nought.
for n, spend, sales in ((5, 10.0, 40.0), (4, 20.0, 50.0), (3, 30.0, 60.0),
                        (1, 40.0, 70.0)):
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders) VALUES (?,?,?,'*',?,?,?,?,?)",
        (WS, MKT, day(n), spend, sales, 10 * n, 1000 * n, 2))
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders) VALUES (?,?,?,?,?,?,?,?,?)",
        (WS, MKT, day(n), "B0LIVE0001", spend, sales, 10 * n, 1000 * n, 2))
for n in (5, 4, 3, 2, 1):
    conn.execute(
        "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
        "ordered_sales, units) VALUES (?,?,?,'*',?,?)",
        (WS, MKT, day(n), 200.0, 5))
conn.commit()

# ---------------------------------------------------------------------------
print("\nthe page never claims to have hourly data")
# ---------------------------------------------------------------------------
s = _lt.series(None, WS, MKT, 7)
check("hourly is reported as unavailable", s["hourly_available"], False)
truthy("  and the reason names Amazon's own refusal",
       "timeUnit HOURLY" in s["hourly_why"] or "HOURLY" in s["hourly_why"])
truthy("  quoting the error verbatim",
       "not supported for this report type" in s["hourly_why"])
check("every range offered is in days",
      sorted({r[2] for r in _lt.RANGES}), [7, 14, 30])

# ---------------------------------------------------------------------------
print("\na day Amazon did not report is a hole, in both views")
# ---------------------------------------------------------------------------
byday = {p["date"]: p for p in s["points"]}
check("the whole range is present, gaps included", len(s["points"]), 7)
check("a reported day has its figure", byday[day(3)]["spend"], 30.0)
# THE ONE THAT MATTERS. 0.0 draws a line to the floor and reads as "we stopped
# advertising"; None leaves a gap, which is what actually happened.
check("an unreported day is None, not 0.0", byday[day(2)]["spend"], None)
check("  and its TACOS is not 0% either", byday[day(2)]["tacos_pct"], None)

cum = _lt.series(None, WS, MKT, 7, cumulative=True)
cby = {p["date"]: p for p in cum["points"]}
check("cumulative adds up as it goes", cby[day(3)]["spend"], 60.0)
# A cumulative line that steps FLAT across an unmeasured day is
# indistinguishable from one that steps flat across a day of no spend.
check("and still leaves the unmeasured day empty", cby[day(2)]["spend"], None)
check("  resuming from the real running total afterwards",
      cby[day(1)]["spend"], 100.0)

# ---------------------------------------------------------------------------
print("\nratios are recomputed per point, never accumulated")
# ---------------------------------------------------------------------------
# A ratio of two running totals is not the running total of a ratio, and only
# the first of those is a number anybody wants.
p3 = cby[day(3)]
check("cumulative TACOS divides the running totals",
      p3["tacos_pct"], round(100.0 * p3["spend"] / p3["total_sales"], 2))
p3d = byday[day(3)]
check("daily TACOS divides that day alone",
      p3d["tacos_pct"], round(100.0 * 30.0 / 200.0, 2))

# ---------------------------------------------------------------------------
print("\nthe cards report what is measured and refuse what is not")
# ---------------------------------------------------------------------------
k = _lt.kpis(None, WS, MKT, 7)
check("spend is the account row summed", k["spend"], 100.0)
truthy("there is data", k["has_data"])
# UNITS IS NOT ORDERS. The mockup asks for both; only ad ORDERS are attributed,
# and showing the order count twice under two names is a lie of arithmetic.
check("units is refused rather than filled with the order count", k["units"],
      None)
truthy("  with the reason", k["units_why"])
truthy("  which is not simply the orders figure", k["orders"] != k["units"])

empty = _lt.kpis(None, "__nobody__", MKT, 7)
check("an account with no advertising says so", empty["has_data"], False)
check("  and its spend is unknown, not 0.00", empty["spend"], None)

# ---------------------------------------------------------------------------
print("\nplacements: real when stored, honest when not")
# ---------------------------------------------------------------------------
p = _lt.placements(None, WS, MKT, 7)
check("with nothing stored it says so", p["has_data"], False)
truthy("  and explains where the rows come from", p["why"])

for n, place, spend in ((3, "Top of Search on-Amazon", 18.0),
                        (3, "Detail Page on-Amazon", 9.0),
                        (3, "Other on-Amazon", 3.0),
                        (1, "Top of Search on-Amazon", 25.0),
                        (1, "Other on-Amazon", 15.0)):
    conn.execute(
        "INSERT INTO ads_placement_daily (workspace_id, marketplace, date, "
        "campaign_id, campaign_name, placement, impressions, clicks, spend, "
        "ad_orders, ad_sales) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (WS, MKT, day(n), "c1", "SP_Test", place, 500, 20, spend, 1, spend * 2))
conn.commit()

p = _lt.placements(None, WS, MKT, 7)
check("now it has data", p["has_data"], True)
check("three placements", len(p["rows"]), 3)
top = p["rows"][0]
check("the biggest spender sorts first", top["placement"],
      "Top of Search on-Amazon")
check("  summed across days", top["spend"], 43.0)
check("  with a readable name", top["label"], "Top of Search")
check("shares add up to a hundred",
      round(sum(r["share_pct"] for r in p["rows"])), 100)
# NOT AVAILABLE PER ASIN, and said rather than left to be discovered. The
# placement report groups by campaign; a campaign usually advertises several
# products, and splitting its spend between them would be an assumption
# presented as a measurement.
check("per-ASIN placement is declared unsupported", p["asin_supported"], False)
truthy("  with the reason", "campaign" in (p.get("asin_why") or ""))

# An unrecognised placement is shown under Amazon's own spelling, not dropped:
# a placement nobody has seen before is still real spend.
conn.execute(
    "INSERT INTO ads_placement_daily (workspace_id, marketplace, date, "
    "campaign_id, campaign_name, placement, impressions, clicks, spend, "
    "ad_orders, ad_sales) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    (WS, MKT, day(1), "c1", "SP_Test", "Somewhere New", 10, 1, 2.0, 0, 0.0))
conn.commit()
p2 = _lt.placements(None, WS, MKT, 7)
labels = {r["label"] for r in p2["rows"]}
truthy("an unknown placement is kept under Amazon's own name",
       "Somewhere New" in labels)

# ---------------------------------------------------------------------------
print("\nper product, and one product's own line")
# ---------------------------------------------------------------------------
pr = _lt.products(None, WS, MKT, 7)
check("the advertised product is listed", len(pr["rows"]), 1)
check("  and never the account-total row",
      [r for r in pr["rows"] if r["asin"] == "*"], [])
check("  with its spend summed", pr["rows"][0]["spend"], 100.0)

one = _lt.daily_for_asin(None, WS, MKT, "B0LIVE0001", 7)
check("every day in the range is present", len(one["points"]), 7)
oby = {x["date"]: x for x in one["points"]}
check("a day it ran has a figure", oby[day(3)]["spend"], 30.0)
check("a day it did not is None, not 0.0", oby[day(2)]["spend"], None)

for t in ("ads_daily", "sales_daily", "ads_placement_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    sys.exit(1)
print("all passed")
