"""Fees, refunds and what is actually left -- the arithmetic, asserted.

Three things here are easy to get backwards and expensive when you do:

  * SIGNS. Amazon sends fees negative. Stored positive, or a profit figure comes
    out larger than revenue and looks plausible.
  * SKU vs ASIN. Financial events are keyed by SKU. Money from a SKU that cannot
    be mapped to an ASIN must still reach the account total, or fees quietly go
    missing and everything looks more profitable than it is.
  * POSTED DATE. A refund lands on the day the money went back, which may be a
    day with no sales at all. That day must still appear.
"""
import os, sys, json, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-62s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

TMP = tempfile.mkdtemp(prefix="altafin_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "fin.db")

from domain import finance_data as fd
from domain import sales_data as sd

WS, MKT = "selvora", "UK"
SKUMAP = {"SKU-RED": "B0RED00001", "SKU-BLUE": "B0BLUE0001"}


def money(v, c="GBP"):
    return {"CurrencyAmount": v, "CurrencyCode": c}


EVENTS = {"FinancialEvents": {
    "ShipmentEventList": [{
        "AmazonOrderId": "203-1", "PostedDate": "2026-08-01T10:00:00Z",
        "ShipmentItemList": [
            {"SellerSKU": "SKU-RED", "QuantityShipped": 2,
             "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": money(40.00)}],
             # Amazon sends fees NEGATIVE.
             "ItemFeeList": [{"FeeType": "Commission", "FeeAmount": money(-6.00)},
                             {"FeeType": "FBAPerUnitFulfillmentFee", "FeeAmount": money(-4.00)}],
             "PromotionList": [{"PromotionAmount": money(-2.00)}]},
            {"SellerSKU": "SKU-GHOST", "QuantityShipped": 1,
             "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": money(10.00)}],
             "ItemFeeList": [{"FeeType": "Commission", "FeeAmount": money(-1.50)}]},
        ]}],
    "RefundEventList": [{
        "AmazonOrderId": "203-9", "PostedDate": "2026-08-05T09:00:00Z",
        "ShipmentItemAdjustmentList": [
            {"SellerSKU": "SKU-BLUE", "QuantityShipped": -1,
             "ItemChargeAdjustmentList": [{"ChargeType": "Principal",
                                           "ChargeAmount": money(-25.00)}],
             "ItemFeeAdjustmentList": [{"FeeType": "Commission",
                                        "FeeAmount": money(3.75)}]}]}],
    "ServiceFeeEventList": [{
        "PostedDate": "2026-08-01T23:00:00Z",
        "FeeList": [{"FeeType": "SubscriptionFee", "FeeAmount": money(-25.00)}]}],
    "AdjustmentEventList": [{
        "AdjustmentType": "REVERSAL_REIMBURSEMENT", "PostedDate": "2026-08-05T12:00:00Z",
        "AdjustmentItemList": [{"SellerSKU": "SKU-RED", "TotalAmount": money(8.00)}]}],
}}

print("=== fees are stored POSITIVE, whatever sign Amazon used ===")
rows, notes = fd.parse_events(EVENTS, SKUMAP)
by = {(r["date"], r["asin"]): r for r in rows}
tot1 = by[("2026-08-01", "*")]
check("referral fees are positive", tot1["referral_fees"], 7.5)      # 6.00 + 1.50
check("  FBA fees too", tot1["fba_fees"], 4.0)
check("  and a subscription fee is 'other'", tot1["other_fees"], 25.0)
check("  a funded promo is positive too", tot1["promos"], 2.0)
check("principal is what buyers were charged", tot1["principal"], 50.0)

print("\n=== a SKU with no ASIN still reaches the account total ===")
red = by[("2026-08-01", "B0RED00001")]
check("the mapped SKU gets its own row", (red["referral_fees"], red["fba_fees"]), (6.0, 4.0))
check("the unmapped SKU has NO product row",
      ("2026-08-01", "SKU-GHOST") in by, False)
check("  but its fee is still in the total", tot1["referral_fees"], 7.5)
check("  and it is REPORTED, not hidden", notes["unmapped_skus"], ["SKU-GHOST"])
check("a subscription fee is recognised, not reported as unknown",
      notes["unknown_fee_types"], [])

print("\n=== refunds post on the day the money went back ===")
tot5 = by[("2026-08-05", "*")]
check("refund principal is positive", tot5["refunds"], 25.0)
check("  units refunded counted once", tot5["refund_units"], 1)
check("  the fee Amazon gave back is kept SEPARATE", tot5["refund_fees_returned"], 3.75)
check("  and not netted into fees charged", tot5["referral_fees"], 0.0)
check("a reimbursement is money coming back", tot5["reimbursements"], 8.0)

print("\n=== an undated charge is kept, not silently dropped ===")
# Found against a LIVE UK account, 13 Aug 2026: Amazon sends the monthly
# Subscription fee as a ServiceFeeEvent with a FeeList and NO PostedDate. Without
# a date the row was discarded, understating fees by GBP 30 and overstating what
# was left -- and nothing on screen would have said so.
UNDATED = {"FinancialEvents": {"ServiceFeeEventList": [
    {"FeeList": [{"FeeType": "Subscription", "FeeAmount": money(-30.00)}]}]}}
lost, n_lost = fd.parse_events(UNDATED, SKUMAP)
check("with no fallback there is nothing to place it on", lost, [])
kept, n_kept = fd.parse_events(UNDATED, SKUMAP, fallback_date="2026-08-31")
check("given a fallback day the money is KEPT",
      [r["other_fees"] for r in kept if r["asin"] == "*"], [30.0])
check("  placed on that day", kept[0]["date"], "2026-08-31")
check("  and the amount is declared, not hidden", n_kept["unattributed"], 30.0)
check("  with a note saying the day is approximate",
      "approximate" in n_kept["unattributed_note"], True)

print("\n=== fee types confirmed against a live account are not 'unknown' ===")
REAL = {"FinancialEvents": {"ShipmentEventList": [{
    "PostedDate": "2026-08-06T16:37:10Z",
    "ShipmentItemList": [{"SellerSKU": "SKU-RED", "QuantityShipped": 1,
        "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": money(34.99)}],
        "ItemFeeList": [
            {"FeeType": "Commission", "FeeAmount": money(-6.30)},
            {"FeeType": "DigitalServicesFee", "FeeAmount": money(-0.13)},
            {"FeeType": "CSBAFee", "FeeAmount": money(0.0)},
            {"FeeType": "FixedClosingFee", "FeeAmount": money(0.0)},
            {"FeeType": "SomethingBrandNew", "FeeAmount": money(-1.00)}]}]}]}}
rr, rn = fd.parse_events(REAL, SKUMAP)
t = [r for r in rr if r["asin"] == "*"][0]
check("commission is a referral fee", t["referral_fees"], 6.3)
check("  the digital services fee is 'other'", t["other_fees"], 1.13)
check("only a genuinely NEW fee type is reported",
      rn["unknown_fee_types"], ["SomethingBrandNew"])

print("\n=== transfers are not costs ===")
# Disbursements are money moving to your bank and debt recovery is Amazon
# reclaiming a balance already charged. Counting either would charge you twice.
XFER = {"FinancialEvents": {
    "AdhocDisbursementEventList": [{"PostedDate": "2026-08-06T16:00:00Z",
                                    "TransferAmount": money(500.00)}],
    "DebtRecoveryEventList": [{"DebtRecoveryType": "DebtPayment"}]}}
xr, _ = fd.parse_events(XFER, SKUMAP, fallback_date="2026-08-31")
check("a disbursement is not counted as anything", xr, [])

print("\n=== stored and joined onto sales ===")
fd.store(CFG, WS, MKT, rows)
# Sales on the 1st only. The 5th has refunds but NO sales.
sd.store(CFG, WS, MKT, [{"date": "2026-08-01", "asin": "*", "units": 3,
                         "ordered_sales": 50.0, "sessions": 100, "currency": "GBP"}])
ser = sd.series(CFG, WS, MKT, "2026-08-01", "2026-08-05")
dates = [r["date"] for r in ser]
check("a refund-only day still appears", "2026-08-05" in dates, True)
check("  which sales alone would have dropped", len(dates), 2)

d1 = [r for r in ser if r["date"] == "2026-08-01"][0]
check("total fees add up", d1["total_fees"], 36.5)                   # 7.5 + 4 + 25
# Net proceeds works off PRINCIPAL, the money-moved figure, not ordered_sales --
# they are dated on different bases and mixing them gives a number that is
# neither. Here both happen to be 50.00.
check("net proceeds = principal - fees - refunds - promos", d1["net_proceeds"], 11.5)
check("  and principal is offered as its own row", d1["principal"], 50.0)
d5 = [r for r in ser if r["date"] == "2026-08-05"][0]
# no sales, 25 refunded, 3.75 fee back, 8 reimbursed
check("a refund day nets negative", d5["net_proceeds"], -13.25)

print("\n=== the roll-up uses the same rules as everything else ===")
t = sd.totals(CFG, WS, MKT, "2026-08-01", "2026-08-05")
check("fees sum across the period", t["total_fees"], 36.5)
check("refunds sum", t["refunds"], 25.0)
# 36.50 fees over 50.00 charged to buyers -- both money-moved figures, one basis.
check("fee rate is fees over what buyers were charged", t["fee_rate"], 73.0)
check("net proceeds sum", t["net_proceeds"], -1.75)                   # 11.50 + -13.25
check("net proceeds is NOT called profit",
      [m[1] for m in sd.METRICS if m[0] == "net_proceeds"], ["Net proceeds"])

print("\n=== nothing at all is not zero ===")
empty, notes2 = fd.parse_events({}, SKUMAP)
check("no events parses to no rows", empty, [])
t2 = sd.totals(CFG, "nobody", MKT, "2026-08-01", "2026-08-05")
check("an account with no finance data reports None, not 0", t2["total_fees"], None)
check("  and no fee rate rather than 0%", t2["fee_rate"], None)

print("\n=== the endpoints ===")
from flask import Flask
import routes.sales_routes as sr
app = Flask(__name__); app.secret_key = "t"
sr.register(app, CONFIG_PATH=CFG, _cfg=lambda: json.load(open(CFG)),
            _active_account=lambda: {"id": WS, "label": "Selvora"},
            _state={"active_account_id": WS, "active_marketplace": MKT})
c = app.test_client()
j = c.get("/sales/series?start=2026-08-01&end=2026-08-05&granularity=day").get_json()
keys = [m["key"] for m in j["metrics"]]
for k in ("referral_fees", "fba_fees", "total_fees", "refunds", "net_proceeds"):
    check("the grid offers %s" % k, k in keys, True)
fee = [m for m in j["metrics"] if m["key"] == "total_fees"][0]
check("fees are marked as lower-is-better", fee["good"], "down")

from auth.guard import feature_for, required_permission
check("the raw diagnostic is feature-gated", feature_for("/sales/finance-raw"), "sales")

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
