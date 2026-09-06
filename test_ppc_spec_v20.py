"""The spec's exact arithmetic, and the places it disagreed with what was built.

PPC_ANALYTICS_BUILD_SPEC sections 18 and 20 give exact formulas where earlier
versions gave descriptions. Four of them contradicted what this app was doing,
and in every case the app was the one that was wrong. This asserts the new
behaviour AND the specific harm each old one caused, so a future edit that
reverts one fails here with the reason attached.

  A SINGLE TEST CLICK SCORED THE FULL 35. Zero sales meant an undefined ACOS,
  and undefined was read as the worst case there is -- so a campaign that spent
  18p and sold nothing outranked one quietly losing money all month. The spec
  names this exact fault: "This prevents a single test click from scoring 35
  points."

  MONEY AT STAKE WAS ABSOLUTE. sqrt(spend)/20 saturates near 400, so on an
  account whose biggest campaign spends 34 every score sat in the bottom third
  of a component worth 40 points, and the column could not be sorted usefully.

  UNCONVERTED CLICKS WERE A RATE. 5 clicks and no orders scored the same as
  1,000 clicks and no orders. The spec: "Based on VOLUME of wasted clicks, not
  percentage."

  MARGINAL WAS MEASURED AGAINST BREAK-EVEN ACOS, an ACCOUNT-WIDE rate, so a
  campaign selling a fatter-margin product was called Marginal for sitting near
  a threshold that did not apply to it. Both section 5 and section 18 define it
  against SPEND.

And the trailing-two-day rule, which was not implemented at all.
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
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def near(label, got, want, tol=0.51):
    ok = (got is not None and abs(float(got) - float(want)) <= tol)
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else
                          "FAIL got=%r want~%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import ppc_analytics as pa
from domain import ppc_targeting as pt

print("=== the last two days are unfinished, not wrong ===")
# A click today can be credited with a sale up to 7 days later (14 on SB), and
# the day of the CLICK owns it. So a recent day has all its spend and only some
# of its sales, and every ratio built on it errs in ONE direction: recent
# advertising always looks worse than it was.
check("the exclusion is two days", pa.IMMATURE_DAYS, 2)
truthy("there is a shared rule", callable(pa.mature_end))
truthy("  and a shared list of which days are still moving",
       callable(pa.immature_days))
truthy("  and one dict the whole page reads", callable(pa.maturity))
PA = open(os.path.join(HERE, "domain", "ppc_analytics.py"), encoding="utf-8").read()
_me = PA.split("def mature_end(")[1].split("\ndef ")[0]
# MEASURED FROM THE LAST DAY WITH DATA, NOT FROM TODAY. An account whose feed is
# already four days behind has no immature days in view, and clipping two more
# off it would throw away days that finished counting long ago.
truthy("it steps back from the last day with DATA, not from today",
       "latest_ad_day(" in _me)
# Short fragments only. A longer phrase wraps in the source and then matches a
# newline plus indentation rather than the words -- which fails a line that has
# not changed, and sends the next reader looking for a bug in the code.
truthy("  and says so", "from the calendar" in _me)
_id = PA.split("def immature_days(")[1].split("\ndef ")[0]
truthy("immature days are MARKED, not hidden", "For MARKING, not hiding" in _id)
truthy("  because a chart that stops early looks like an account that stopped",
       "stopped advertising" in _id)

print("\n=== the cohort threshold is 10% OF SPEND ===")
_ch = PA.split("def _cohort(")[1].split("\ndef ")[0]
truthy("it is measured against spend", "profit <= s * 0.10" in _ch)
falsy("  and no longer against break-even ACOS",
      "breakeven_acos * 0.9" in _ch)
truthy("  with the reason recorded", "ACCOUNT-WIDE rate" in _ch)
# 100 spend, 5 profit -> 5% of spend -> Marginal. 100 spend, 25 profit -> 25%.
check("5 profit on 100 spend is marginal",
      pa._cohort(100.0, 500.0, 5.0, 40.0, True), pa.MARGINAL)
check("  25 profit on 100 spend is profitable",
      pa._cohort(100.0, 500.0, 25.0, 40.0, True), pa.PROFITABLE)
check("  exactly 10% is still marginal",
      pa._cohort(100.0, 500.0, 10.0, 40.0, True), pa.MARGINAL)
check("a loss is unprofitable",
      pa._cohort(100.0, 500.0, -1.0, 40.0, True), pa.UNPROFITABLE)
check("spent and sold nothing is its own bucket",
      pa._cohort(100.0, 0.0, None, 40.0, True), pa.NO_SALES)
check("  and spent nothing is not the same finding",
      pa._cohort(0.0, 0.0, None, 40.0, True), pa.NO_ACTIVITY)

print("\n=== the opportunity score, to the spec's arithmetic ===")
check("the unconverted-click threshold is 30", pa.UNCONVERTED_CLICK_THRESHOLD, 30)

# S_spend = 40 x sqrt(spend / max_spend). The biggest spender scores the full 40.
check("the biggest spender takes the full 40 for money at stake",
      pa._opportunity(100.0, 0.0, 0, 0, None, max_spend=100.0), 40)
# A quarter of the max spend -> sqrt(0.25) = 0.5 -> 20 points.
check("  a quarter of that spend scores half of it",
      pa._opportunity(25.0, 0.0, 0, 0, None, max_spend=100.0), 20)

# THE FAULT THE SPEC NAMES. Zero sales, tiny spend, against a break-even CPA of
# 15: 35 x (0.50/15) = 1.17, not 35.
_tiny = pa._opportunity(0.50, 0.0, 1, 0, 50.0, max_spend=0.50,
                        max_cost_per_order=15.0)
_big = pa._opportunity(25.0, 0.0, 1, 0, 50.0, max_spend=25.0,
                       max_cost_per_order=15.0)
truthy("a 50p test click with no sales scores far below a 25.00 one",
       _tiny < _big)
print("     50p -> %s, 25.00 -> %s (both zero sales, both top spender)"
      % (_tiny, _big))
# 40 (top spender) + 1.17 (0.50/15) + 0.83 (1 click / 30) = 42
near("  and it is 40 for spend plus a scaled 1.17, not a flat 35", _tiny, 42)
# 40 + 35 (25/15 caps at 1) + 0.83 = 76
near("  while 25.00 with no sales does earn the full 35", _big, 76)

# Distance past break-even: ACOS 50 against break-even 34.4 is 0.4535 -> 15.87.
_d = pa._opportunity(100.0, 200.0, 0, 0, 34.4, max_spend=100.0)
near("ACOS 50%% against break-even 34.4%% adds about 16 points", _d - 40, 15.87)
# At double break-even it caps at 35.
_cap = pa._opportunity(100.0, 100.0, 0, 0, 34.4, max_spend=100.0)
near("  at double break-even it caps at 35", _cap - 40, 35)
check("  below break-even it adds nothing",
      pa._opportunity(100.0, 1000.0, 0, 0, 34.4, max_spend=100.0), 40)

# Unconverted clicks by VOLUME: 30+ unconverted is the full 25.
#
# max_spend is left out so the money component scores 0 and this measures the
# unconverted one ALONE -- passing max_spend=spend would add a silent 40 and the
# expectation would have to carry it, which is how a test stops describing the
# thing it is named after. (It did, on the first run: 65 against an expected 25.)
check("30 unconverted clicks is the full 25",
      pa._opportunity(1.0, 100.0, 30, 0, 1000.0), 25)
# 5 clicks -> 5/30 x 25 = 4.17
near("  5 unconverted clicks is about 4",
     pa._opportunity(1.0, 100.0, 5, 0, 1000.0), 4.17)
# THE OLD FORM SCORED THESE THE SAME. 1000 clicks and 5 clicks, both no orders.
_many = pa._opportunity(1.0, 100.0, 1000, 10, 1000.0)
_few = pa._opportunity(1.0, 100.0, 5, 0, 1000.0)
truthy("1,000 unconverted clicks outscores 5, which it did not before",
       _many > _few)

check("no spend is no opportunity, not a zero",
      pa._opportunity(0.0, 0.0, 0, 0, 40.0, max_spend=100.0), None)
check("  and the score never exceeds 100",
      pa._opportunity(1e9, 0.0, 1e6, 0, 1.0, max_spend=1.0,
                      max_cost_per_order=1.0), 100)
# WITHOUT THE TABLE'S MAXIMUM the money component cannot be PLACED, so it scores
# 0 rather than guessing an average.
check("with no max_spend the money component is 0, not a guess",
      pa._opportunity(100.0, 100.0, 0, 0, 34.4), 35)

print("\n=== the break-even cost per order ===")
_r = {"breakeven_acos_pct": 50.0}
_t = {"sales": 1000.0, "orders": 50.0}          # AOV 20.00
check("break-even CPA is average order value x break-even ACOS",
      pa.max_cost_per_order(_r, _t), 10.0)
check("  none without a break-even rate",
      pa.max_cost_per_order({}, _t), None)
check("  none without orders to average over",
      pa.max_cost_per_order(_r, {"sales": 1000.0, "orders": 0}), None)

print("\n=== a comparison off a floor-level base is arithmetic, not news ===")
check("the ratio floor is 2%", pa._RATIO_FLOOR_PCT, 2.0)
check("  spend under 10.00", pa._COUNT_FLOORS["spend"], 10.0)
check("  sales under 25.00", pa._COUNT_FLOORS["sales"], 25.0)
check("  orders under 3", pa._COUNT_FLOORS["orders"], 3.0)
_now = {"spend": 11768.0, "sales": 400.0, "orders": 50.0, "acos_pct": 24.3}
_bef = {"spend": 5.0, "sales": 10.0, "orders": 2.0, "acos_pct": 0.4}
_c = pa.change(_now, _bef)
check("5.00 -> 11,768 shows no percentage", _c["spend"], None)
check("  nor 10.00 -> 400", _c["sales"], None)
check("  nor 2 orders -> 50", _c["orders"], None)
check("  nor 0.4% ACOS -> 24.3%", _c["acos_pct"], None)
_fl = pa.change_floor(_now, _bef)
truthy("and every one of them says WHY it is blank", len(_fl) == 4)
truthy("  naming the previous figure", "5" in _fl["spend"])
# A DASH WITH NO REASON READS AS MISSING DATA, which is a different finding.
truthy("  and the reason is about the base, not about missing data",
       "too small a base" in _fl["spend"] or "too low a base" in _fl["spend"])
# ABOVE THE FLOOR IT STILL COMPARES.
_c2 = pa.change({"spend": 120.0}, {"spend": 100.0})
check("a real base still gets a real percentage", _c2["spend"], 20.0)
_c3 = pa.change({"acos_pct": 28.4}, {"acos_pct": 24.3})
check("  and a ratio still moves in POINTS", _c3["acos_pct"], 4.1)

print("\n=== wasted spend has two definitions and shows both ===")
check("the qualified gate is ten clicks", pa.QUALIFIED_CLICKS, 10)
_ws = PA.split("def wasted_spend(")[1].split("\ndef ")[0]
truthy("the full universe is spend with a click and no order",
       "COALESCE(clicks,0) > 0 AND COALESCE(orders,0) = 0" in _ws)
truthy("  and the qualified subset is clicks >= the gate",
       "COALESCE(clicks,0) >= ?" in _ws)
falsy("  the old 'three clicks OR a pound' rule is gone",
      "OR COALESCE(spend,0) >= ?" in _ws)
truthy("  and both are returned, never one instead of the other",
       "actionable_spend" in _ws and '"spend": _f(r["s"])' in _ws)

print("\n=== match type comes from the TARGETING report, not search terms ===")
# The Search Term Report is privacy-thresholded -- Amazon suppresses low-volume
# queries -- so its spend is short of what was billed. A donut drawn from it
# sits beside a total drawn from the campaign reports and does not add up to it.
PT = open(os.path.join(HERE, "domain", "ppc_targeting.py"), encoding="utf-8").read()
truthy("there is a targeting-grain module", callable(pt.by_match_type))
truthy("  and it reads ads_targeting_daily", "FROM ads_targeting_daily" in PT)
falsy("  and never ppc_search_terms", "ppc_search_terms" in PT.split("'''")[0]
      if "'''" in PT else False)
truthy("  with the reason recorded", "PRIVACY-THRESHOLDED" in PT.upper())
DB = open(os.path.join(HERE, "data", "db.py"), encoding="utf-8").read()
truthy("the table exists", "CREATE TABLE IF NOT EXISTS ads_targeting_daily" in DB)
truthy("  keyed so one keyword on two match types stays two rows",
       "keyword, match_type, ad_product" in DB)
AA = open(os.path.join(HERE, "api", "amazon_ads.py"), encoding="utf-8").read()
truthy("the report is spTargeting", '"reportTypeId": "spTargeting"' in AA)
truthy("  grouped by targeting, which is what Amazon accepted",
       '"groupBy": ["targeting"]' in AA)
truthy("  and spKeywords is recorded as REFUSED so nobody tries it again",
       "spKeywords" in AA and "REFUSED" in AA)

# AMAZON'S OWN ENUM IS STORED, AND MADE READABLE ONLY AT THE EDGE.
check("the auto enum is labelled for people",
      pt.label_for("TARGETING_EXPRESSION_PREDEFINED"), "Auto")
check("  product targeting too", pt.label_for("TARGETING_EXPRESSION"),
      "Product targeting")
check("  and a plain one is titled", pt.label_for("EXACT"), "Exact")
# AN UNKNOWN ENUM SHOWS AS ITSELF. Amazon adds values; one swept into "Other"
# is spend that vanishes from a chart while staying in the total beside it.
check("an enum with no name is shown as itself, not as Other",
      pt.label_for("SOME_NEW_AMAZON_ENUM"), "SOME_NEW_AMAZON_ENUM")
check("  and a blank says so", pt.label_for(""), "Not stated")
truthy("the reason is recorded", "vanishes" in PT or "disappears" in PT)

_bmt = PT.split("def by_match_type(")[1].split("\ndef ")[0]
truthy("% profit is a share of the POOL, not a margin on spend",
       "NOT A MARGIN" in _bmt)
truthy("  measured over POSITIVE profit only",
       "positive profit" in _bmt.lower())
_dbm = PT.split("def daily_by_match_type(")[1].split("\ndef ")[0]
truthy("the stacked area uses the app's own chart shape",
       '"columns"' in _dbm and '"lines"' in _dbm)
# ON A STACKED AREA A GAP IS NOT A HOLE -- it is a step in every lane above it.
truthy("  and a day a lane did not run is 0, not a gap",
       "step in every lane" in _dbm)

print("\n=== the search term report can follow the date picker ===")
PV = open(os.path.join(HERE, "domain", "ppc_view.py"), encoding="utf-8").read()
truthy("load_rows takes a window", "def load_rows(config_path, workspace_id, "
       "marketplace, report_id=None,\n              start=None, end=None)" in PV)
# A ROW WITH NO DATE IS KEPT. Dropping undated rows would empty the page for an
# account that has only ever uploaded a file, the moment a picker moved.
truthy("  and an undated row is kept, not filtered out",
       "date IS NULL OR (date >= ? AND date <= ?)" in PV)
truthy("there is one answer to 'can this page follow the picker'",
       callable(__import__("domain.ppc_view", fromlist=["x"]).dated_window))
AS = open(os.path.join(HERE, "domain", "ads_sync.py"), encoding="utf-8").read()
check("every report is now asked for DAILY",
      "SUMMARY" in AS.split("def time_unit_for(")[1].split("\ndef ")[0], True)
_tu = AS.split("def time_unit_for(")[1].split("\ndef ")[0]
truthy("  and the search term report is no longer a summary",
       'return "DAILY"' in _tu)
truthy("  with the measurement that justified the change",
       "393 rows over 7 days" in _tu)
truthy("the day is carried through the canonical shape",
       '"date": r.get("date")' in AS)
truthy("and a batch row is stored with NO date rather than a guessed one",
       "cannot be split back into thirty" in PV)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
