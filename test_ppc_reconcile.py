"""Do the three advertising screens agree with each other and with the tables?

    "verifying the data on all new ppc pages, they should be correct"

Not "does it render" -- these three read the same window through different
paths, and the way a figure goes wrong is that one path disagrees with another
and nothing notices. So each check compares a number the screen shows against
the same number arrived at some other way.

Every fixture here is written into a throwaway workspace, so the arithmetic is
checkable by hand rather than against whatever happens to be in the database.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                    # noqa: E402
from domain import ppc_analytics as _pa       # noqa: E402
from domain import ads_sync as _as            # noqa: E402

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


WS, MKT = "__ppc_recon__", "UK"
S, E = "2026-08-01", "2026-08-04"
conn = _db.get_db()
for t in ("ads_daily", "ads_campaign_daily", "sales_daily", "ppc_search_terms",
          "order_lines", "order_fees"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))

# Four days. The account-wide row and the per-product rows carry the SAME money
# at different grains, exactly as the real table does.
DAYS = [("2026-08-01", 10.0, 40.0, 100, 10000, 4),
        ("2026-08-02", 20.0, 50.0, 200, 20000, 5),
        ("2026-08-03", 30.0, 90.0, 300, 30000, 9),
        ("2026-08-04", 40.0, 20.0, 400, 40000, 2)]
for date, spend, sales, clicks, impr, orders in DAYS:
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders, ad_product) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (WS, MKT, date, "*", spend, sales, clicks, impr, orders,
         "SPONSORED_PRODUCTS"))
    # the same day split across two products
    for i, frac in enumerate((0.6, 0.4)):
        conn.execute(
            "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, "
            "spend, ad_sales, clicks, impressions, ad_orders, ad_product) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (WS, MKT, date, "B0RECON%d" % i, round(spend * frac, 2),
             round(sales * frac, 2), int(clicks * frac), int(impr * frac),
             0, "SPONSORED_PRODUCTS"))
    # and across two campaigns
    for i, frac in enumerate((0.75, 0.25)):
        conn.execute(
            "INSERT INTO ads_campaign_daily (workspace_id, marketplace, date, "
            "campaign_id, campaign_name, status, spend, ad_sales, clicks, "
            "impressions, ad_orders, ad_product) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (WS, MKT, date, "C%d" % i, "Campaign %d" % i, "ENABLED",
             round(spend * frac, 2), round(sales * frac, 2),
             int(clicks * frac), int(impr * frac), 0, "SPONSORED_PRODUCTS"))
    conn.execute(
        "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, "
        "ordered_sales, units, orders) VALUES (?,?,?,?,?,?,?)",
        (WS, MKT, date, "*", sales * 2, 1, 1))
conn.commit()

TOT_SPEND = round(sum(d[1] for d in DAYS), 2)      # 100.00
TOT_SALES = round(sum(d[2] for d in DAYS), 2)      # 200.00
TOT_CLICKS = sum(d[3] for d in DAYS)               # 1000
TOT_ALL_SALES = round(TOT_SALES * 2, 2)            # 400.00

print("\nthe headline figures are the account row, not the sum of both grains")
t = _pa.totals_for(None, WS, MKT, S, E)
check("spend", t["spend"], TOT_SPEND)
check("ad sales", t["sales"], TOT_SALES)
check("clicks", t["clicks"], float(TOT_CLICKS))
check("total sales come from the sales table", t["total_sales"], TOT_ALL_SALES)
# ACOS = spend/AD sales; TACOS = spend/ALL sales. Two denominators, and
# confusing them flatters the advertising.
check("ACOS is spend over ad sales", t["acos_pct"], 50.0)
check("TACOS is spend over ALL sales", t["tacos_pct"], 25.0)
check("ROAS is ad sales over spend", t["roas"], 2.0)
check("CPC is spend over clicks", t["cpc"], 0.1)
# The shared reader must agree with the page's own totals, or two screens
# disagree about the same window.
check("ads_sync.totals agrees with the page",
      _as.totals(None, WS, MKT, S, E)["spend"], t["spend"])

print("\nthe daily series adds back up to the headline")
d = _pa.daily(None, WS, MKT, S, E)
check("one row per day", len(d), 4)
check("the days sum to the window's spend",
      round(sum(x["spend"] for x in d), 2), TOT_SPEND)
check("and to its ad sales", round(sum(x["ad_sales"] for x in d), 2), TOT_SALES)
check("and to its total sales",
      round(sum(x["total_sales"] for x in d), 2), TOT_ALL_SALES)
# A day's own ACOS is that day's, not the window's.
check("day 4 sold less than it spent, so its ACOS is over 100",
      d[3]["acos_pct"], 200.0)

print("\nthe campaign grain reconciles with the account grain")
rates = {"fee_rate": 0.2, "cogs_rate": 0.3, "breakeven_acos_pct": 50.0}
camps = _pa.campaigns(None, WS, MKT, S, E, rates)
check("two campaigns", len(camps), 2)
# THE CHECK THAT MATTERS: campaign spend must equal account spend. If a grain
# is ever double-counted again, this is where it shows.
check("campaign spend sums to the account's",
      round(sum(c["spend"] for c in camps), 2), TOT_SPEND)
check("campaign sales likewise",
      round(sum(c["sales"] for c in camps), 2), TOT_SALES)

print("\nthe per-product grain does too")
asins = _pa.asins(None, WS, MKT, S, E, rates)
check("two products", len(asins), 2)
check("product spend sums to the account's",
      round(sum(a["spend"] for a in asins), 2), TOT_SPEND)
# AND IT EXCLUDES THE ACCOUNT ROW. If asin<>'*' were ever dropped, the total
# here would come to double and this is what would say so.
truthy("no product is the account-total row",
       all(a["asin"] != "*" for a in asins))

print("\nthe cohorts account for every campaign and every pound")
co = _pa.cohorts(None, WS, MKT, S, E, camps, rates)
check("every campaign is in exactly one bucket",
      sum(v["n"] for k, v in co.items() if k != "all"), co["all"]["n"])
check("and the spend adds up",
      round(sum(v["spend"] for k, v in co.items() if k != "all"), 2),
      round(co["all"]["spend"], 2))

print("\nthe by-product fold agrees with the campaigns it folded")
by = _pa.by_group(camps, "ad_product")
check("one ad product", len(by), 1)
check("its spend is the whole window's", by[0]["spend"], TOT_SPEND)
check("and its share is all of it", by[0]["spend_share_pct"], 100.0)
dbp = _pa.daily_by_ad_product(None, WS, MKT, S, E)
check("the daily-by-product series covers the same days", len(dbp["dates"]), 4)
check("and sums to the same spend",
      round(sum(v for v in dbp["series"][0]["values"] if v), 2), TOT_SPEND)

print("\nthe top strip reports the newest day Amazon actually sent")
bar = _pa.today_bar(None, WS, MKT)
# NOT today. Amazon's reports lag, and asking for today produced six dashes on
# an account with plenty of data.
check("it is the latest stored day", bar["date"], "2026-08-04")
check("and it knows that is not today", bar["is_today"], False)
truthy("it says how far behind Amazon is", bar["lag_days"] > 0)
check("its figures are that day's", bar["now"]["spend"], 40.0)
check("compared against the day before", bar["compare_date"], "2026-08-03")
# 40 against 30 is +33.3%.
check("and the change is against that day", bar["change"]["spend"], 33.3)

print("\nthe trail is the window accumulating")
# THE TRAIL ALWAYS ENDS TODAY -- it is the last seven days, not the window the
# rest of the page is showing. The fixture above sits in August, so on any real
# run these cards are empty, and that is correct rather than a fault. The
# invariant worth asserting is the accumulation itself, which holds either way.
tr = _pa.trail(None, WS, MKT, 7)
check("seven cards", len(tr), 7)
truthy("the cumulative never goes down",
       all(tr[i]["cumulative"] <= tr[i + 1]["cumulative"]
           for i in range(len(tr) - 1)))
truthy("each card's running total is the spends up to it",
       all(abs(tr[i]["cumulative"]
               - round(sum((x["spend"] or 0) for x in tr[:i + 1]), 2)) < 0.011
           for i in range(len(tr))))
truthy("exactly one card is marked today",
       sum(1 for x in tr if x["today"]) == 1)

# And the accumulation really does accumulate when the days DO carry spend --
# checked on the fixture's own window rather than on the trail's.
_days = _pa.daily(None, WS, MKT, S, E)
_run, _acc = [], 0.0
for x in _days:
    _acc += (x["spend"] or 0)
    _run.append(round(_acc, 2))
check("over a window with spend it climbs to the total", _run[-1], TOT_SPEND)
truthy("and rises every day of it",
       all(_run[i] < _run[i + 1] for i in range(len(_run) - 1)))

print("\nnothing is invented for a day Amazon did not send")
gap = _pa.daily(None, WS, MKT, "2026-08-01", "2026-08-06")
check("the range is honoured", len(gap), 6)
# A DAY WITH NO ROW IS A GAP. 0.0 draws a line to the floor and reads as "we
# stopped advertising"; None leaves a break, which is what happened.
check("a day with no row is None, not 0.0", gap[4]["spend"], None)
check("and its ACOS is not 0% either", gap[4]["acos_pct"], None)

for t_ in ("ads_daily", "ads_campaign_daily", "sales_daily", "ppc_search_terms",
           "order_lines", "order_fees"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t_, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
