"""Cost of goods, and the profit built on it.

The generator writes the source cost into every SKU it makes
({cost}_{N}Days_{COMPETITOR_ASIN}), so the cost is already there. Three ways
that goes wrong, all of which produce a confident number that is too HIGH:

  * 0.00 READ AS FREE. build_sku writes 0.00 when it had no cost. An item with
    no cost looks infinitely profitable -- and that is the item someone then
    reorders.
  * HAND-MADE SKUs. "46 pcs wrench" has no cost in it. 22 of the 107 live SKUs
    are like that.
  * PARTIAL COVERAGE SUMMED ANYWAY. Uncosted units bring revenue and no cost, so
    a bucket that quietly skips them reports profit that is too high, on exactly
    the products nobody has costed.

Profit is therefore withheld unless EVERY unit in the bucket is costed.
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-62s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

TMP = tempfile.mkdtemp(prefix="altacogs_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "c.db")

from domain import cogs
from domain import finance_data as fd
from domain import sales_data as sd

WS, MKT = "jack_uk", "UK"

print("=== the cost written into the SKU ===")
check("a generated SKU carries its cost", cogs.cost_from_sku("15.09_3DAYS_B0F7D29MFZ"), 15.09)
check("  mixed case Days", cogs.cost_from_sku("8.00_3Days_B0G1K5B7QS"), 8.0)
check("  a de-duplicated SKU still parses", cogs.cost_from_sku("11.95_3Days_B09JYYJR7H_2"), 11.95)
check("0.00 is UNKNOWN, not free", cogs.cost_from_sku("0.00_3Days_B0XYZ12345"), None)
check("a hand-made SKU has no cost", cogs.cost_from_sku("46 pcs wrench"), None)
check("  nor this one", cogs.cost_from_sku("AltaboltaVoo Ceiling Fan"), None)
check("  nor a random code", cogs.cost_from_sku("1U-OMQC-HX2V"), None)
check("empty is not zero", cogs.cost_from_sku(""), None)

print("\n=== a person always beats the SKU ===")
ov = {"jack_uk::15.09_3DAYS_B0F7D29MFZ": 12.00}
check("a manual override wins",
      cogs.resolve(ov, WS, "15.09_3DAYS_B0F7D29MFZ"), (12.0, "manual"))
check("  and is scoped to its account",
      cogs.resolve(ov, "other_acct", "15.09_3DAYS_B0F7D29MFZ"), (15.09, "sku"))
check("without an override the SKU is used",
      cogs.resolve({}, WS, "15.09_3DAYS_B0F7D29MFZ"), (15.09, "sku"))
check("with neither, there is no cost", cogs.resolve({}, WS, "46 pcs wrench"), (None, ""))
check("an override can rescue an uncosted SKU",
      cogs.resolve({"jack_uk::46 pcs wrench": 4.5}, WS, "46 pcs wrench"), (4.5, "manual"))

print("\n=== dashboard.py and the sales screen use the SAME resolver ===")
import dashboard as dash
check("dashboard delegates the SKU parse",
      dash._cogs_from_sku("15.09_3DAYS_B0F7D29MFZ"), 15.09)
check("  and gets the same answer as the module",
      dash._cogs_from_sku("0.00_3Days_B0XYZ12345"), cogs.cost_from_sku("0.00_3Days_B0XYZ12345"))

print("\n=== cost is priced at the SHIPMENT LINE, where the SKU still exists ===")
def money(v):
    return {"CurrencyAmount": v, "CurrencyCode": "GBP"}

def shipment(date, lines):
    return {"PostedDate": date + "T10:00:00Z", "ShipmentItemList": [
        {"SellerSKU": sku, "QuantityShipped": q,
         "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": money(rev)}],
         "ItemFeeList": [{"FeeType": "Commission", "FeeAmount": money(-fee)}]}
        for sku, q, rev, fee in lines]}

SKUMAP = {"10.00_3Days_B0AAAAAAAA": "B0OURS00001",
          "46 pcs wrench": "B0OURS00002"}
LOOK = cogs.lookup({}, WS)

# Day 1: everything costed.  2 units at 10.00 cost, 60.00 revenue, 9.00 fees.
ev1 = {"FinancialEvents": {"ShipmentEventList": [
    shipment("2026-08-01", [("10.00_3Days_B0AAAAAAAA", 2, 60.00, 9.00)])]}}
rows, notes = fd.parse_events(ev1, SKUMAP, cost_lookup=LOOK)
tot = [r for r in rows if r["asin"] == "*"][0]
check("units shipped counted", tot["units"], 2)
check("  cost of goods = 2 x 10.00", tot["cogs"], 20.0)
check("  and every unit is costed", tot["cogs_units"], 2)
check("coverage is reported", notes["cogs_coverage_pct"], 100.0)

# Day 2: one costed line and one that has no cost at all.
ev2 = {"FinancialEvents": {"ShipmentEventList": [
    shipment("2026-08-02", [("10.00_3Days_B0AAAAAAAA", 1, 30.00, 4.50),
                            ("46 pcs wrench", 1, 25.00, 3.75)])]}}
rows2, notes2 = fd.parse_events(ev2, SKUMAP, cost_lookup=LOOK)
tot2 = [r for r in rows2 if r["asin"] == "*"][0]
check("both units counted", tot2["units"], 2)
check("  but only one is costed", tot2["cogs_units"], 1)
check("  cost covers only that one", tot2["cogs"], 10.0)
check("coverage says so", notes2["cogs_coverage_pct"], 50.0)

print("\n=== profit is withheld unless EVERY unit is costed ===")
fd.store(CFG, WS, MKT, rows)
fd.store(CFG, WS, MKT, rows2)
ser = sd.series(CFG, WS, MKT, "2026-08-01", "2026-08-02")
d1 = [r for r in ser if r["date"] == "2026-08-01"][0]
d2 = [r for r in ser if r["date"] == "2026-08-02"][0]
# 60.00 charged - 9.00 fees = 51.00 net, - 20.00 cost = 31.00
check("a fully costed day reports profit", d1["profit"], 31.0)
check("  and a margin on what buyers were charged", d1["margin_pct"], 51.67)
check("a partly costed day reports NOTHING", d2["profit"], None)
check("  not a margin either", d2["margin_pct"], None)
check("  though its cost of goods is still shown", d2["cogs"], 10.0)

print("\n=== a week containing one uncosted day is not 'the rest of the week' ===")
w = sd.aggregate(ser, "profit")
check("the whole bucket is withheld", w, None)
check("  and so is its margin", sd.aggregate(ser, "margin_pct"), None)
check("but the costed day alone still reports",
      sd.aggregate([d1], "profit"), 31.0)
check("  and fees still sum across both", sd.aggregate(ser, "total_fees"), 17.25)

print("\n=== coverage is reported so a blank profit can be explained ===")
cov = cogs.coverage(CFG, WS, MKT, {})
check("coverage answers even with no snapshot", isinstance(cov, dict), True)
check("  with a total", "total" in cov, True)

print("\n=== the summary endpoint carries the reason ===")
from flask import Flask
import routes.sales_routes as sr
app = Flask(__name__); app.secret_key = "t"
sr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS, "label": "Jack UK"},
            _state={"active_account_id": WS, "active_marketplace": MKT})
c = app.test_client()
j = c.get("/sales/summary?start=2026-08-01&end=2026-08-02").get_json()
check("summary reports COGS coverage", "cogs_coverage" in j, True)
j2 = c.get("/sales/series?start=2026-08-01&end=2026-08-02&granularity=day").get_json()
keys = [m["key"] for m in j2["metrics"]]
for k in ("cogs", "profit", "margin_pct", "units_shipped"):
    check("the grid offers %s" % k, k in keys, True)
prof = [m for m in j2["metrics"] if m["key"] == "profit"][0]
check("profit is blank on the uncosted day, not zero", prof["cells"], [31.0, None])

print("\n=== a cost typed later reaches a day only when that day is re-pulled ===")
# The screen tells the user to set a cost and then press Sync. This is that path,
# end to end. It runs LAST because it re-prices 2026-08-02, and the checks above
# depend on that day still being the uncosted one.
#
# If this ever stops working the on-screen note becomes a lie, which is worse
# than a blank profit: the user follows it, sees nothing change, and concludes
# the profit figure itself is broken.
LOOK2 = cogs.lookup({"jack_uk::46 pcs wrench": 5.00}, WS)
rows2b, notes2b = fd.parse_events(ev2, SKUMAP, cost_lookup=LOOK2)
tot2b = [r for r in rows2b if r["asin"] == "*"][0]
check("the override prices the previously uncosted unit", tot2b["cogs_units"], 2)
check("  cost of goods is now both units", tot2b["cogs"], 15.0)
check("  coverage reaches 100%", notes2b["cogs_coverage_pct"], 100.0)

fd.store(CFG, WS, MKT, rows2b)          # a re-pull REPLACES the stored day
ser2 = sd.series(CFG, WS, MKT, "2026-08-02", "2026-08-02")
d2b = [r for r in ser2 if r["date"] == "2026-08-02"][0]
# 55.00 charged - 8.25 fees = 46.75 net, - 15.00 cost = 31.75
check("profit appears for that day once it is re-pulled", d2b["profit"], 31.75)
check("  a cost typed on the listings screen is what did it", d2b["cogs"], 15.0)

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
