"""domain/drppc_performance.py and domain/drppc_activity.py.

WHAT IS BEING DEFENDED HERE IS THE RIGHT TO REFUSE.

A performance page exists to say "this is normal" or "this is not". Both are
claims, and a page that makes them from four days of history, or from a mean it
could not compute, is worse than one that says nothing -- somebody acts on it.

So the checks below are mostly about the cases where a verdict must NOT appear:
too little history, a metric that could not be worked out, a baseline with no
spread, a week with no week before it, and an account with no advertising at all.

The activity ledger is defended on a different point: it must not become a
second copy of facts that are already recorded elsewhere, because then the
ledger and the original can disagree and the ledger is the one people trust.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                        # noqa: E402
from domain import drppc_performance as _dp       # noqa: E402
from domain import drppc_activity as _da          # noqa: E402

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


WS, MKT = "__drppc_perf__", "UK"
conn = _db.get_db()
for t in ("ads_daily", "sales_daily", "ads_campaign_daily", "drppc_plans",
          "drppc_rules", "drppc_events", "ppc_search_terms"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.execute("DELETE FROM sync_jobs WHERE workspace_id=?", (WS,))
conn.commit()


def add_day(date, spend, sales, clicks, orders, total_sales):
    """One day at the ACCOUNT grain, which is the only grain these read."""
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders, ad_product) "
        "VALUES (?,?,?,'*',?,?,?,?,?,'SPONSORED_PRODUCTS')",
        (WS, MKT, date, spend, sales, clicks, 1000, orders))
    conn.execute(
        "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
        "ordered_sales, units) VALUES (?,?,?,'*',?,?)",
        (WS, MKT, date, total_sales, 1))


# Thirty flat days, then one that is plainly different. Flat on purpose: it
# makes the standard deviation small, so the odd day out has a large z and the
# scoring is being tested rather than the noise.
import datetime as _dt                            # noqa: E402

BASE_DAY = _dt.date(2026, 8, 1)
for i in range(30):
    d = (BASE_DAY + _dt.timedelta(days=i)).isoformat()
    add_day(d, 10.0 + (i % 3) * 0.5, 40.0 + (i % 3), 50 + (i % 3), 2, 100.0)
ODD = (BASE_DAY + _dt.timedelta(days=30)).isoformat()
add_day(ODD, 60.0, 40.0, 300, 2, 100.0)           # spend six times normal
conn.commit()

# ---------------------------------------------------------------------------
print("\nthe day being scored is never part of its own baseline")
# ---------------------------------------------------------------------------
s = _dp.scorecard(None, WS, MKT, 60)
check("the latest complete day is the one scored", s["day"], ODD)
b = s["baseline"]
check("the baseline ends the day BEFORE it", b["end"],
      (BASE_DAY + _dt.timedelta(days=29)).isoformat())
check("and covers the days that exist", b["days_with_data"], 30)
truthy("which is enough to score against", b["enough"])

by = {c["key"]: c for c in s["cards"]}
# THE ONE THAT MATTERS. A day six times normal must not come out "in line". If
# the day were inside its own baseline it would drag the mean towards itself.
check("a day far from normal is called off baseline", by["spend"]["status"],
      "off")
check("  and the expected value is the baseline's, not the day's",
      round(by["spend"]["expected"], 1), 10.5)
check("  and it is off because of the SPEND, not the day's date",
      by["spend"]["value"], 60.0)
# THE SAME DAY IS OFF ON ONE METRIC AND NOT ON ANOTHER, which is the point of
# scoring per metric: a day is not uniformly good or bad.
#
# Ad sales cycle 40/41/42, so the mean is 41 and the spread is under a pound.
# The odd day's 40 is a difference of one pound and 1.2 standard deviations --
# "drifting", not "off". A TIGHT BASELINE MAKES SMALL MOVES SIGNIFICANT, and it
# should: an account that has spent within a pound of the same figure for a
# month has just done something different, even if the amount looks trivial.
check("a small move against a tight baseline is drifting, not nothing",
      by["ad_sales"]["status"], "drifting")
check("  even though the money moved by one pound",
      round(by["ad_sales"]["delta"], 1), -1.0)
# CVR collapses on the odd day: six times the clicks for the same two orders.
# Correct, and worth pinning down -- it is the kind of movement a person would
# want to see flagged.
check("and a metric that collapsed is off", by["cvr_pct"]["status"], "off")
# Total sales are identical on every fixture day, so the baseline has NO spread.
# A difference of nothing is still "in line"; any difference at all cannot be
# scored, because there is no scale to measure it against.
check("a baseline with no spread still recognises an identical day",
      by["total_sales"]["status"], "in_line")

# ---------------------------------------------------------------------------
print("\nand it refuses to score what it cannot")
# ---------------------------------------------------------------------------
SHORT = "__drppc_short__"
conn.execute("DELETE FROM ads_daily WHERE workspace_id=?", (SHORT,))
conn.execute("DELETE FROM sales_daily WHERE workspace_id=?", (SHORT,))
for i in range(4):
    d = (BASE_DAY + _dt.timedelta(days=i)).isoformat()
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders) VALUES (?,?,?,'*',?,?,?,?,?)",
        (SHORT, MKT, d, 10.0, 40.0, 50, 1000, 2))
conn.commit()
s2 = _dp.scorecard(None, SHORT, MKT, 60)
b2 = s2["baseline"]
check("three days of history is not a baseline", b2["enough"], False)
truthy("  and it says why", "%d" % _dp.MIN_BASELINE_DAYS in b2["why"])
# NOT ONE CARD GETS A VERDICT. Two different reasons appear and both are
# refusals: "unscored" is too little history, "unknown" is a metric the day
# itself could not produce (this fixture stores no sales, so TACOS has no
# denominator). What must never appear is in line, drifting or off.
got = sorted({c["status"] for c in s2["cards"]})
check("  every card refuses, one way or the other", got, ["unknown", "unscored"])
check("  and none of them reaches a verdict",
      [c["key"] for c in s2["cards"]
       if c["status"] in ("in_line", "drifting", "off")], [])

# An account with no advertising at all: not a zero-spend account.
s3 = _dp.scorecard(None, "__nobody__", MKT)
check("an account with no advertising has nothing to score", s3["has_data"],
      False)
check("  and no cards rather than six empty ones", s3["cards"], [])
truthy("  with the reason", s3["why"])

# ---------------------------------------------------------------------------
print("\ntwo kinds of missing day, and they mean opposite things")
# ---------------------------------------------------------------------------
m = b["metrics"]["acos_pct"]
# Every fixture day has sales, so ACOS is computable on all of them.
check("no advertising day failed to produce an ACOS", m["unmeasurable"], 0)
# The 60-day window reaches back before this account existed. Those days are
# NOT evidence gaps and must not be reported as such.
truthy("days before the account started are counted separately",
       m["outside_history"] > 0)
g = _dp.gaps(None, WS, MKT, s, b)
truthy("the gap list mentions the short history",
       any("asked for 60 days" in x for x in g))
check("and never calls a pre-history day an unmeasurable one",
      any("could not be worked out on" in x for x in g), False)

# ---------------------------------------------------------------------------
print("\na week against the week before it")
# ---------------------------------------------------------------------------
t = _dp.trend(None, WS, MKT, 7)
truthy("there is a trend", t["has_data"])
check("the recent window ends on the latest complete day", t["recent"]["end"],
      ODD)
check("  and the prior window ends the day before it starts",
      t["prior"]["end"],
      (_dt.date.fromisoformat(t["recent"]["start"])
       - _dt.timedelta(days=1)).isoformat())
check("both windows are seven days", (t["recent"]["days"], t["prior"]["days"]),
      (7, 7))
# RATIOS CHANGE IN POINTS, money in per cent. Reporting a ratio's move as a
# percentage of itself describes something nobody asked about.
truthy("money changes are a percentage", isinstance(t["change"]["spend"], float))
check("ACOS moves in points, computed from the recomputed ratios",
      t["change"]["acos_pct"],
      round(t["recent"]["acos_pct"] - t["prior"]["acos_pct"], 1))

# ---------------------------------------------------------------------------
print("\ncampaigns are matched by id, so a rename is not two events")
# ---------------------------------------------------------------------------
for i in range(14):
    d = (BASE_DAY + _dt.timedelta(days=17 + i)).isoformat()
    # Same campaign_id throughout, renamed halfway. Matching on the NAME would
    # report one campaign stopped and another started -- two large fictitious
    # movements out of one rename.
    conn.execute(
        "INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, "
        "campaign_id, campaign_name, status, budget, ad_product, spend, "
        "ad_sales, ad_orders, clicks, impressions, fetched_at) "
        "VALUES (?,?,?,?,?,'ENABLED',10,'SPONSORED_PRODUCTS',?,?,?,?,?,?)",
        (WS, MKT, d, "c1", "Old name" if i < 7 else "New name",
         5.0, 20.0, 1, 10, 500, "2026-09-01T00:00:00"))
conn.commit()
dr = _dp.drivers(None, WS, MKT, 7)
rows = [r for r in dr["rows"] if r["campaign_id"] == "c1"]
check("the renamed campaign is one row, not two", len(rows), 1)
check("  and it is continuing, not new", rows[0]["state"], "continuing")
check("  with no fictitious movement", rows[0]["spend_delta"], 0.0)

lg = _dp.largest(None, WS, MKT, 7)
truthy("the largest-spender table names the campaign",
       lg["rows"] and lg["rows"][0]["campaign"])

# ---------------------------------------------------------------------------
print("\nthe plan panels report absence rather than an empty box")
# ---------------------------------------------------------------------------
p = _dp.plan_sections(None, WS, MKT, t)
check("with no plan there is no pacing", p["has_plan"], False)
truthy("  and it says what would fix it", "activ" in p["why"].lower())
truthy("rank is named as not recorded at all", p["rank_why"])

# ---------------------------------------------------------------------------
print("\nthe ledger derives history rather than copying it")
# ---------------------------------------------------------------------------
from domain import drppc_console as _dc          # noqa: E402

_dc.plan_save_draft(None, WS, MKT, {"identity": {"title": "a plan"}}, "tester")
_dc.plan_activate(None, WS, MKT, 1, "tester")
_dc.rule_add(None, WS, MKT, "branded", "search_term", "contains", "ours", 10,
             "our own name")
ev = _da.events(None, WS, MKT)
kinds = {e["action"] for e in ev}
truthy("the plan's creation is in the ledger", "plan_revision_created" in kinds)
truthy("  and its activation separately", "plan_activated" in kinds)
truthy("the lane rule is there too", "lane_rule_added" in kinds)
# NOT COPIED. Nothing wrote those into drppc_events -- they are read from the
# rows that already hold them, so the ledger cannot disagree with the plan.
n = conn.execute("SELECT COUNT(*) FROM drppc_events WHERE workspace_id=?",
                 (WS,)).fetchone()[0]
check("and none of it was copied into the events table", n, 0)

check("newest first", ev[0]["at"] >= ev[-1]["at"], True)
check("filtering by kind narrows it",
      {e["kind"] for e in _da.events(None, WS, MKT, kind="plan")}, {"plan"})
check("filtering by actor too",
      {e["actor"] for e in _da.events(None, WS, MKT, actor="human")}, {"human"})

# An event with no other home IS stored, and only a known kind is accepted.
rid = _da.record(None, WS, MKT, "system", "human", "settings_saved",
                 "Console settings saved", "profile changed", "workspace", WS,
                 "tester")
truthy("an event with nowhere else to live is stored", rid)
check("an unknown kind is refused rather than stored unfilterable",
      _da.record(None, WS, MKT, "vibes", "human", "x", "y"), None)
check("an unknown actor likewise",
      _da.record(None, WS, MKT, "system", "robot", "x", "y"), None)

sug = _da.suggestions(None, WS, MKT)
check("nothing is ever queued for apply", sug["cards"], [])
truthy("  and it says that is about this app, not this account",
       "does not write to Amazon" in sug["why"])

for t_ in ("ads_daily", "sales_daily", "ads_campaign_daily", "drppc_plans",
           "drppc_rules", "drppc_events", "ppc_search_terms"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t_, (WS,))
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t_, (SHORT,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    for f in fails:
        print("  FAILED:", f)
    sys.exit(1)
