"""domain/ppc_analytics.py -- the figures behind the three advertising screens.

Every check is about a number the screen must refuse to state rather than about
arithmetic. The arithmetic is division; what makes an advertising screen
trustworthy is that it will not print 0% for a ratio nobody could compute, will
not call a campaign unprofitable on a guessed margin, and will not draw a chart
through hours nobody measured.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                      # noqa: E402
from domain import ppc_analytics as _pa         # noqa: E402

fails, ran = [], []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT = "__ppc_pages__", "UK"
conn = _db.get_db()
for t in ("ads_daily", "ads_campaign_daily", "sales_daily", "ppc_search_terms",
          "order_lines"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))

# Two days. The account total at asin='*' AND the same money per product, which
# is how the real table is shaped.
for date, spend, sales in (("2026-08-01", 10.0, 40.0), ("2026-08-02", 20.0, 50.0)):
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders, ad_product) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (WS, MKT, date, "*", spend, sales, 20, 2000, 2, "SPONSORED_PRODUCTS"))
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders, ad_product) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (WS, MKT, date, "B0TEST0001", spend, sales, 20, 2000, 2,
         "SPONSORED_PRODUCTS"))
    conn.execute(
        "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
        "ordered_sales, units, sessions, page_views, buy_box_pct) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (WS, MKT, date, "*", 100.0, 4, 200, 250, 95.0))
conn.commit()

print("\nthe account total, never the total plus its own breakdown")
t = _pa.totals_for(None, WS, MKT, "2026-08-01", "2026-08-02")
# 30, not 60. The per-product rows hold the same money at a finer grain.
check("spend is the account row alone", t["spend"], 30.0)
check("ad sales likewise", t["sales"], 90.0)
check("total sales come from the sales table's own account row",
      t["total_sales"], 200.0)
# TACOS is spend over ALL sales; ACOS is spend over AD sales. Two different
# denominators, and confusing them flatters the advertising.
check("ACOS divides by AD sales", t["acos_pct"], 33.3)
check("TACOS divides by ALL sales", t["tacos_pct"], 15.0)

print("\na ratio nobody could compute is not zero")
r0 = _pa._rate(5.0, 0)
check("a rate over nothing is undefined", r0, None)
check("a rate over an unknown is undefined", _pa._rate(5.0, None), None)
check("a real rate is a real rate", _pa._rate(1.0, 4.0), 25.0)
empty = _pa.totals_for(None, "__nobody__", MKT, "2026-08-01", "2026-08-02")
check("an account with no advertising reports absence", empty["has_data"], False)
check("and its spend is unknown, not 0.00", empty["spend"], None)

print("\na day with no row draws a gap, not a floor")
d = _pa.daily(None, WS, MKT, "2026-08-01", "2026-08-04")
check("every day in the range is present", len(d), 4)
check("a day with data has a figure", d[0]["spend"], 10.0)
# THE ONE THAT MATTERS FOR THE CHART. 0.0 draws a line to the floor and reads as
# "we stopped advertising"; None leaves a gap, which is what actually happened.
check("a day with no advertising row is None, not 0.0", d[2]["spend"], None)
check("and its ACOS is not 0% either", d[2]["acos_pct"], None)

print("\nprofit is refused when the rates behind it cannot be measured")
# No order_lines and no settled fees for this workspace, so neither rate exists.
rates = _pa.rates(None, WS, MKT, "2026-08-01", "2026-08-02")
check("no costed orders means no cost rate", rates["cogs_rate"], None)
check("and therefore no break-even ACOS", rates["breakeven_acos_pct"], None)

conn.execute(
    "INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, "
    "campaign_id, campaign_name, status, budget, spend, ad_sales, clicks, "
    "impressions, ad_orders, ad_product) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (WS, MKT, "2026-08-01", "C1", "Sells things", "ENABLED", 5.0,
     10.0, 40.0, 20, 2000, 2, "SPONSORED_PRODUCTS"))
conn.execute(
    "INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, "
    "campaign_id, campaign_name, status, budget, spend, ad_sales, clicks, "
    "impressions, ad_orders, ad_product) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (WS, MKT, "2026-08-01", "C2", "Sells nothing", "ENABLED", 5.0,
     8.0, 0.0, 30, 3000, 0, "SPONSORED_PRODUCTS"))
conn.execute(
    "INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, "
    "campaign_id, campaign_name, status, budget, spend, ad_sales, clicks, "
    "impressions, ad_orders, ad_product) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (WS, MKT, "2026-08-01", "C3", "Did not run", "PAUSED", 5.0,
     0.0, 0.0, 0, 0, 0, "SPONSORED_PRODUCTS"))
conn.commit()

camps = _pa.campaigns(None, WS, MKT, "2026-08-01", "2026-08-02", rates)
by = {c["campaign_id"]: c for c in camps}
check("three campaigns", len(camps), 3)
# WITHOUT A MEASURED MARGIN, PROFIT IS BLANK -- not zero, and not a guess. A
# campaign switched off on the strength of an invented margin is a real cost.
check("profit is not invented without rates", by["C1"]["profit"], None)
check("and the screen is told it could not be estimated",
      by["C1"]["profit_estimated"], False)
# ...but two things ARE knowable with no rates at all, and they are the two most
# actionable states on the screen.
check("spent and sold nothing is knowable without any rate",
      by["C2"]["cohort"], _pa.NO_SALES)
check("spent nothing and sold nothing is a different thing entirely",
      by["C3"]["cohort"], _pa.NO_ACTIVITY)
check("a campaign with sales stays unclassified until profit can be worked out",
      by["C1"]["cohort"], None)

print("\nwith rates, the cohorts sort against THIS account's break-even")
# 20% fee, 30% stock -> half of every pound is margin, so break-even ACOS is 50%.
fixed = {"fee_rate": 0.20, "cogs_rate": 0.30, "breakeven_acos_pct": 50.0}
camps2 = _pa.campaigns(None, WS, MKT, "2026-08-01", "2026-08-02", fixed)
by2 = {c["campaign_id"]: c for c in camps2}
# 40 sales - 10 spend - 8 fee - 12 stock = 10.
check("profit is sales less spend, fee and stock", by2["C1"]["profit"], 10.0)
check("ACOS 25% against a 50% break-even is profitable",
      by2["C1"]["cohort"], _pa.PROFITABLE)
check("and it is labelled an estimate", by2["C1"]["profit_estimated"], True)

print("\nthe cohorts reconcile")
co = _pa.cohorts(None, WS, MKT, "2026-08-01", "2026-08-02", camps2, fixed)
check("every campaign is in exactly one bucket",
      sum(v["n"] for k, v in co.items() if k != "all"), co["all"]["n"])
check("and the spend adds up too",
      round(sum(v["spend"] for k, v in co.items() if k != "all"), 2),
      round(co["all"]["spend"], 2))

print("\nopportunity is None when there is nothing to gain")
check("no spend means no opportunity, not a zero score",
      by2["C3"]["opportunity"], None)
truthy("clicks that bought nothing score high",
       (by2["C2"]["opportunity"] or 0) > (by2["C1"]["opportunity"] or 0))

print("\nbranded is unknown, not false, when no brand words are set")
rows = [{"branded": None, "spend": 1.0, "sales": 2.0, "clicks": 1, "orders": 0,
         "impressions": 10, "profit": None}]
bs = _pa.branded_split(rows)
# THE ONE THAT WAS WRONG FIRST TIME. is_branded answers None when the brand list
# is empty -- "not set up: not 'no', which is a claim". Reading that as falsey
# reported every term as non-branded and would have shown a confident 0%
# branded spend for an account that had simply never typed its brand in.
check("an unanswered split reports no counts", bs["branded_terms"], None)
truthy("and says why", bool(bs.get("why")))
mixed = _pa.branded_split([
    {"branded": True, "spend": 1.0, "sales": 5.0, "clicks": 1, "orders": 1,
     "impressions": 10, "profit": None},
    {"branded": False, "spend": 3.0, "sales": 6.0, "clicks": 2, "orders": 1,
     "impressions": 20, "profit": None}])
check("a real split counts branded terms", mixed["branded_terms"], 1)
check("and non-branded ones", mixed["non_branded_terms"], 1)

print("\nwhat cannot be drawn says so")
av = _pa.availability(None, WS, MKT)
# THE TWO PANELS THE SPEC ASKED FOR THAT CANNOT BE HONEST. No hourly rows exist
# anywhere, so the day trail and the day x hour heatmap report unavailable
# rather than drawing a curve through hours nobody measured.
check("hourly is never available", av["hourly"]["ok"], False)
truthy("and it explains why in a sentence", len(av["hourly"]["why"]) > 40)
truthy("one ad product is flagged, because a missing one flatters every ACOS",
       bool(av["ad_products"]["why"]))
check("campaigns are available here", av["campaigns"]["ok"], True)

print("\nnothing in this module can write to Amazon")
SRC = open(os.path.join(HERE, "domain", "ppc_analytics.py"), encoding="utf-8").read()
RT = open(os.path.join(HERE, "routes", "ppc_analytics_routes.py"),
          encoding="utf-8").read()
# CLAUDE.md Rule 8: never a bid, never a budget, never a campaign state.
for word in ("updateCampaign", "putCampaign", "bid=", "set_bid", "budget="):
    check("no %s anywhere in the computation layer" % word,
          word in SRC, False)
check("every route is a GET", 'methods=["POST"]' in RT, False)
check("and none of them writes", "DELETE FROM" in RT or "UPDATE " in RT, False)

for t in ("ads_daily", "ads_campaign_daily", "sales_daily", "ppc_search_terms",
          "order_lines"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
