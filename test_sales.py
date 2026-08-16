"""The Sales dashboard: real report JSON in, real endpoints out.

The numbers are the product here, so most of these checks are arithmetic. The
two that matter most:

  * RATES ARE RECOMPUTED, never averaged. The mean of seven daily conversion
    rates is not the week's conversion rate, and the gap widens exactly when the
    days are uneven -- which is when someone is looking.
  * NO DATA is not ZERO. Amazon has a lag and never has today; a day it has not
    delivered must read as "not in yet", not as "you sold nothing".
"""
import os, sys, json, tempfile, shutil, datetime as dt
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-62s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

TMP = tempfile.mkdtemp(prefix="altasales_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "selvora", "label": "Selvora",
                         "marketplaces": ["UK"], "refresh_token": "x",
                         "seller_id": "A1"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "sales.db")

from domain import sales_data as sd

WS, MKT = "selvora", "UK"


def day(d, units, sales, sessions, views, asin=None):
    """One day of Amazon's real report shape."""
    block = {
        "date": d,
        "salesByDate": {
            "orderedProductSales": {"amount": sales, "currencyCode": "GBP"},
            "unitsOrdered": units, "totalOrderItems": units,
            "averageSellingPrice": {"amount": round(sales / units, 2) if units else 0,
                                    "currencyCode": "GBP"},
        },
        "trafficByDate": {"sessions": sessions, "pageViews": views,
                          "buyBoxPercentage": 95.0,
                          "unitSessionPercentage": round(units / sessions * 100, 2) if sessions else 0},
    }
    return block


print("=== Amazon's JSON is parsed into daily rows ===")
doc = {"salesAndTrafficByDate": [
    day("2026-08-01", 10, 100.0, 200, 400),
    day("2026-08-02", 30, 600.0, 300, 600),
]}
rows = sd.parse_report(doc)
check("two days parsed", len(rows), 2)
check("  revenue read from the nested amount", rows[0]["ordered_sales"], 100.0)
check("  units", rows[0]["units"], 10)
check("  sessions from the traffic block", rows[0]["sessions"], 200)
check("  currency carried", rows[0]["currency"], "GBP")
check("  the account total is stored under '*'", rows[0]["asin"], "*")

print("\n=== the per-ASIN block is parsed too ===")
doc2 = {"salesAndTrafficByAsin": [
    {"parentAsin": "B0TEST0001",
     "salesByAsin": {"unitsOrdered": 4,
                     "orderedProductSales": {"amount": 40.0, "currencyCode": "GBP"}},
     "trafficByAsin": {"sessions": 80, "pageViews": 100}}],
    "_date": "2026-08-01"}
arows = sd.parse_report(doc2)
check("one ASIN row", len(arows), 1)
check("  keyed by ASIN", arows[0]["asin"], "B0TEST0001")
check("  dated from the request, not the block", arows[0]["date"], "2026-08-01")

print("\n=== storing, and what dates exist ===")
check("rows written", sd.store(CFG, WS, MKT, rows), 2)
av = sd.availability(CFG, WS, MKT)
check("availability knows the first day", av["sales"]["first_date"], "2026-08-01")
check("  and the last", av["sales"]["last_date"], "2026-08-02")
check("  and how many", av["sales"]["days"], 2)
check("ads are NOT connected", av["ads"]["connected"], False)
check("  and say why", "Advertising API" in av["ads"]["note"], True)

print("\n=== re-fetching a day REPLACES it (Amazon revises recent days) ===")
sd.store(CFG, WS, MKT, sd.parse_report({"salesAndTrafficByDate": [
    day("2026-08-02", 25, 500.0, 300, 600)]}))
s = sd.series(CFG, WS, MKT, "2026-08-01", "2026-08-02")
check("still two days, not three", len(s), 2)
check("  and the revised figure won", s[1]["units"], 25)

print("\n=== THE ARITHMETIC THAT MATTERS: rates are recomputed ===")
t = sd.totals(CFG, WS, MKT, "2026-08-01", "2026-08-02")
check("units summed", t["units"], 35)
check("revenue summed", t["ordered_sales"], 600.0)
check("sessions summed", t["sessions"], 500)
# Day 1: 10/200 = 5.00%. Day 2: 25/300 = 8.33%. Mean of the two = 6.67%.
# The TRUE period rate is 35/500 = 7.00%. Averaging is wrong by a third of a point.
check("conversion is 35/500, not the mean of 5.00 and 8.33", t["unit_session_pct"], 7.0)
check("  (the wrong answer would have been 6.67)", round((5.0 + 8.33) / 2, 2), 6.67)
check("average selling price is revenue/units", t["avg_selling_price"], 17.14)

print("\n=== buy box is weighted by page views, not averaged flat ===")
sd.store(CFG, WS, MKT, [
    {"date": "2026-08-03", "asin": "*", "buy_box_pct": 50.0, "page_views": 10,
     "units": 1, "sessions": 10, "currency": "GBP"},
    {"date": "2026-08-04", "asin": "*", "buy_box_pct": 100.0, "page_views": 990,
     "units": 1, "sessions": 10, "currency": "GBP"}])
t2 = sd.totals(CFG, WS, MKT, "2026-08-03", "2026-08-04")
check("a 10-view day cannot outweigh a 990-view day", t2["buy_box_pct"], 99.5)
check("  (a flat mean would have said 75.0)", round((50.0 + 100.0) / 2, 1), 75.0)

print("\n=== NO DATA IS NOT ZERO ===")
t3 = sd.totals(CFG, WS, MKT, "2026-09-01", "2026-09-30")
check("a range Amazon has not delivered has no revenue", t3["ordered_sales"], None)
check("  not 0", t3["ordered_sales"] is None, True)
check("  and no days", t3["days"], 0)
check("ad spend with no ads connected is None, never 0", t3["spend"], None)

print("\n=== the endpoints ===")
from flask import Flask
import routes.sales_routes as sr
app = Flask(__name__)
app.secret_key = "t"
_state = {"active_account_id": WS, "active_marketplace": MKT}
sr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS, "label": "Selvora"}, _state=_state)
c = app.test_client()

j = c.get("/sales/availability").get_json()
check("availability answers", j["ok"], True)
check("  naming the workspace", j["workspace"], WS)

j = c.get("/sales/summary?start=2026-08-01&end=2026-08-02").get_json()
_labels = [x["label"] for x in j["cards"]]
# PROFIT AND MARGIN ARE CARDS NOW. They were already being calculated -- the
# totals carried profit and margin_pct all along -- and the cards showed only
# revenue, orders, units and ad spend, so the screen worked out the one number
# the business runs on and then did not display it.
check("summary returns the full card row",
      _labels,
      ["Revenue", "Net of VAT", "Profit", "Margin", "Stock cost",
       "Amazon fees", "Orders", "Units", "Refunds", "Ad Spend"])
# The order is the order the question gets asked in: what came in, what was
# left, on what margin, off how many units.
check("  revenue first", _labels[0], "Revenue")
check("  profit and margin sit together, before the volume counts",
      _labels.index("Margin") - _labels.index("Profit"), 1)
check("  and both come before Units", _labels.index("Margin") < _labels.index("Units"), True)
check("  revenue card carries the total", j["cards"][0]["value"], 600.0)
_by = {x["label"]: x for x in j["cards"]}
check("  ad spend is None, not 0", _by["Ad Spend"]["value"], None)
# A margin is a percentage; formatting it as money would put a currency symbol
# in front of "20".
check("  margin is typed as a percentage", _by["Margin"]["kind"], "pct")
check("  and the page is told ads are not connected", j["ads_connected"], False)
check("the comparison window is the SAME LENGTH just before",
      (j["compared_to"]["start"], j["compared_to"]["end"]),
      ("2026-07-30", "2026-07-31"))
check("  with no baseline, delta is None rather than 0%",
      j["cards"][0]["delta_pct"], None)

j = c.get("/sales/series?start=2026-08-01&end=2026-08-02&granularity=day").get_json()
check("series returns two columns", j["columns"], ["2026-08-01", "2026-08-02"])
check("  a metric per row, with its own direction",
      [m["good"] for m in j["metrics"] if m["key"] == "spend"] or ["absent"], ["absent"])
rev = [m for m in j["metrics"] if m["key"] == "ordered_sales"][0]
check("  revenue cells line up with the columns", rev["cells"], [100.0, 500.0])
check("  a metric with no data anywhere is omitted",
      any(m["key"] == "impressions" for m in j["metrics"]), False)

print("\n=== weekly roll-up recomputes rates rather than summing them ===")
j = c.get("/sales/series?start=2026-08-01&end=2026-08-02&granularity=week").get_json()
check("both days fall in one week", len(j["columns"]), 1)
conv = [m for m in j["metrics"] if m["key"] == "unit_session_pct"][0]
check("  the week's conversion is 35/500 = 7.0", conv["cells"], [7.0])

print("\n=== export is built from the SAME output as the screen ===")
r = c.get("/sales/export?start=2026-08-01&end=2026-08-02")
check("csv served", r.status_code, 200)
body = r.get_data(as_text=True)
check("  headed with the dates", body.splitlines()[0],
      "Metric,2026-08-01,2026-08-02")
check("  and carries the same revenue", "100.0,500.0" in body, True)
check("  filename names the range",
      'sales_day_2026-08-01_to_2026-08-02.csv' in r.headers.get("Content-Disposition", ""), True)

print("\n=== a parent's variations are kept apart, not collapsed onto the parent ===")
# asinGranularity CHILD sends BOTH ids on every block. Keying on the parent made
# every variation the same row, and the unique index then overwrote them one by
# one -- a parent with five children silently kept only the last.
def asin_block(child, parent, units, sales, sessions):
    return {"date": "2026-08-01", "parentAsin": parent, "childAsin": child,
            "salesByAsin": {"unitsOrdered": units,
                            "orderedProductSales": {"amount": sales, "currencyCode": "GBP"}},
            "trafficByAsin": {"sessions": sessions, "pageViews": sessions * 2}}

kids = sd.parse_report({"salesAndTrafficByAsin": [
    asin_block("BCHILD01", "BPARENT1", 10, 100.0, 40),
    asin_block("BCHILD02", "BPARENT1", 15, 300.0, 60),
    asin_block("BCHILD03", "BPARENT1",  5,  50.0, 20),
]})
check("three variations parsed", len(kids), 3)
check("  keyed by the CHILD asin", sorted(r["asin"] for r in kids),
      ["BCHILD01", "BCHILD02", "BCHILD03"])
check("  with the parent kept alongside", kids[0]["parent_asin"], "BPARENT1")
sd.store(CFG, WS, MKT, kids)
back = sd.series(CFG, WS, MKT, "2026-08-01", "2026-08-01", "BCHILD02")
check("  and all three SURVIVE the write", len(sd.products(CFG, WS, MKT, "2026-08-01", "2026-08-01")), 3)
check("  each keeping its own numbers", (back[0]["units"], back[0]["ordered_sales"]), (15, 300.0))

print("\n=== the product filter offers what actually sold, biggest first ===")
j = c.get("/sales/products?start=2026-08-01&end=2026-08-01").get_json()
check("products answers", j["ok"], True)
check("  three products", j["count"], 3)
check("  ordered by revenue", [p["asin"] for p in j["products"]],
      ["BCHILD02", "BCHILD01", "BCHILD03"])
check("  the account total is not offered as a product",
      any(p["asin"] == "*" for p in j["products"]), False)

j = c.get("/sales/series?start=2026-08-01&end=2026-08-01&asin=BCHILD02").get_json()
rev = [m for m in j["metrics"] if m["key"] == "ordered_sales"][0]
check("  filtering to one ASIN returns only its sales", rev["cells"], [300.0])

print("\n=== a price is recomputed, never summed ===")
j = c.get("/sales/series?start=2026-08-01&end=2026-08-02&granularity=week").get_json()
def cell(k):
    m = [x for x in j["metrics"] if x["key"] == k]
    return m[0]["cells"][0] if m else None
check("average selling price is revenue / units", cell("avg_selling_price"),
      round(cell("ordered_sales") / cell("units"), 2))
check("  which is NOT the sum of the daily prices", cell("avg_selling_price") > 100, False)

print("\n=== a bad custom date falls back instead of reaching SQL ===")
j = c.get("/sales/series?start=banana&end=2026-08-02").get_json()
check("nonsense dates do not 500", j["ok"], True)
check("  and resolve to a preset instead of 'custom'", j["preset"], "30d")
j = c.get("/sales/series?start=2026-08-02&end=2026-08-01").get_json()
check("a backwards range is swapped, not left empty", (j["start"], j["end"]),
      ("2026-08-01", "2026-08-02"))

print("\n=== a fully synced account is not nagged for ever ===")
from domain import sales_fetch as sf
WS2 = "syncprobe"
end = dt.date.today() - dt.timedelta(days=1)
for i in range(30):
    d = (end - dt.timedelta(days=i)).strftime("%Y-%m-%d")
    # `sessions` because that is what a day the REPORT delivered looks like.
    # A row with sales but no traffic is what the ORDER FEED writes, and those
    # days must still be fetched from the report -- otherwise sessions, page
    # views and conversion stay blank on them for ever. See sales_fetch._held.
    sd.store(CFG, WS2, MKT, [{"date": d, "asin": "*", "units": 1,
                              "ordered_sales": 1.0, "sessions": 5,
                              "currency": "GBP"}])
check("holding every day, nothing is missing",
      sf.missing_days(CFG, WS2, MKT, 30), [])
check("  but the recent ones are still due for revision",
      len(sf.revisable_days(CFG, WS2, MKT, 30)), sf.REVISE_DAYS)

print("\n=== permissions ===")
from auth.guard import required_permission, feature_for
from auth import users
check("sales is its own feature", "sales" in users.FEATURES, True)
check("a lister gets NO sales by default", users.ROLE_FEATURES["lister"]["sales"], "none")
check("a manager sees it read-only", users.ROLE_FEATURES["manager"]["sales"], "view")
check("every /sales path is feature-gated", feature_for("/sales/summary"), "sales")
check("pulling from Amazon needs edit", required_permission("/sales/sync", "POST"), "edit")
check("  but reading does not", required_permission("/sales/summary", "GET"), None)

print("\n=== per-product breakdown, and the parent rollup ===")
# parent_asin has been stored since the report was first parsed and never shown.
# A t-shirt in six sizes read as six weak products instead of one strong one.
from data import db as _dbmod
_sdbd = sd
_c = _dbmod.get_db(CFG)
for _d, _asin, _par, _u, _rev, _sess in (
        ("2026-08-01", "B0CHILD001", "B0PARENT01", 3, 60.0, 100),
        ("2026-08-01", "B0CHILD002", "B0PARENT01", 2, 40.0,  50),
        ("2026-08-02", "B0CHILD001", "B0PARENT01", 1, 20.0,  25),
        ("2026-08-01", "B0SOLO0001", "",           4, 80.0, 200)):
    _c.execute("INSERT OR REPLACE INTO sales_daily (workspace_id, marketplace, date, "
               "asin, parent_asin, units, ordered_sales, sessions, order_items) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (WS, MKT, _d, _asin, _par, _u, _rev, _sess, _u))
_c.commit()

by_asin = _sdbd.breakdown(CFG, WS, MKT, "2026-08-01", "2026-08-31", "asin")
ids = [r["k"] for r in by_asin]
# Earlier sections of this test seeded their own ASINs, so assert about the rows
# added HERE rather than about the whole account -- a test that only passes on an
# empty database is a test that will break the moment anything else is added.
check("one row per child ASIN",
      sorted(i for i in ids if i.startswith("B0")),
      ["B0CHILD001", "B0CHILD002", "B0SOLO0001"])
check("  no ASIN appears twice", len(ids), len(set(ids)))
c1 = [r for r in by_asin if r["k"] == "B0CHILD001"][0]
check("  units summed across days", c1["units"], 4)
check("  revenue too", c1["revenue"], 80.0)
check("  conversion is recomputed from the totals, not averaged",
      c1["conversion"], round(4 / 125 * 100, 2))
check("  average price from the totals", c1["avg_price"], 20.0)

by_par = _sdbd.breakdown(CFG, WS, MKT, "2026-08-01", "2026-08-31", "parent")
pids = [r["k"] for r in by_par]
check("variations collapse into the parent",
      sorted(i for i in pids if i.startswith("B0")), ["B0PARENT01", "B0SOLO0001"])
check("  and the children no longer appear on their own",
      any(i in pids for i in ("B0CHILD001", "B0CHILD002")), False)
p = [r for r in by_par if r["k"] == "B0PARENT01"][0]
check("  its units are the children's added up", p["units"], 6)
check("  and its revenue", p["revenue"], 120.0)
check("  it says how many variations", p["children"], 2)
solo = [r for r in by_par if r["k"] == "B0SOLO0001"][0]
check("a product with NO parent keeps its own identity", solo["units"], 4)
check("  and is not lumped in with every other parentless product",
      solo["children"], 1)
_revs = [r["revenue"] or 0 for r in by_par]
check("biggest revenue first", _revs, sorted(_revs, reverse=True))

j = c.get("/sales/breakdown?preset=30d&group=parent").get_json()
check("the endpoint answers", j["ok"], True)
check("  honouring the grouping", j["group"], "parent")
check("  an unknown grouping falls back to per-ASIN",
      c.get("/sales/breakdown?preset=30d&group=nonsense").get_json()["group"], "asin")

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
