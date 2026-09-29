"""The same profit on every screen (owner, 30 Sep 2026: "make sure we have
accurate calculations on profits in every screen accross the app").

Each block pins one finding of the independent review of that work, and fails
on the code before the fix:
  1. ads measured day by day: Ads API from the day it reports, invoices before;
     an unset VAT rate is UNKNOWN (no VAT added, said), not "not registered"
  2. the settlement tab measures "no row carries it" against the product rows
     (a SKU's removal fee was counted in its row AND in the overhead)
  3. a window with settled sales but no per-order postings keeps the old rule
  4. the money calendar does not take the account charges off twice
  5. a refund comes off an order on the same footing as its revenue
  6. every transaction: clawbacks signed, reserves ignored, the lists the
     catch-all could not read
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


TMP = tempfile.mkdtemp(prefix="altaprofit_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "ws1", "label": "One", "vat_rate": 0}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "p.db")

from data import db as _db                 # noqa: E402
from domain import ad_cost as AC           # noqa: E402
from domain import expenses as EX          # noqa: E402
from domain import sales_data as SD        # noqa: E402
from domain import orders_view as OV       # noqa: E402
from domain import finance_data as FD      # noqa: E402
from domain import order_finance as OF     # noqa: E402

c = _db.get_db(CFG)


def fin(mkt, date, asin, **kw):
    cols = ["workspace_id", "marketplace", "date", "asin", "currency", "source"] + list(kw)
    c.execute("INSERT INTO finance_daily (%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))),
              ["ws1", mkt, date, asin, "GBP", "t"] + list(kw.values()))


def ads(mkt, date, spend):
    c.execute("INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend) VALUES (?,?,?,?,?)",
              ("ws1", mkt, date, "*", spend))


# UK: an ad invoice on 3 Sep, the Ads API from 10 Sep.
fin("UK", "2026-09-03", "*", ads_charged=50.0, ads_charged_tax=10.0)
ads("UK", "2026-09-10", 5.0)
ads("UK", "2026-09-11", 5.0)
# ES: the subscription (30 other) and a removal fee (2 FBA) on the account row;
# the removal fee is also on its product's row.
fin("ES", "2026-09-05", "*", other_fees=30.0, fba_fees=2.0, principal=0.0)
fin("ES", "2026-09-05", "B01", fba_fees=2.0, principal=0.0)
# DE: settled sales with FBA fees, but no per-order postings kept.
fin("DE", "2026-09-06", "*", other_fees=30.0, fba_fees=3.0, principal=20.0)
# FR: only the subscription, for the calendar test.
fin("FR", "2026-09-07", "*", other_fees=30.0, principal=0.0, referral_fees=0.0)
c.commit()

print("== 1. what advertising cost ==")
check("VAT setting: unset is unknown", [AC.vat_registered(v) for v in (None, "", 0, 0.2)],
      [None, None, False, True])
days, info = AC.by_day(CFG, "ws1", "UK", "2026-09-01", "2026-09-11", False)
check("invoice before the API's first day, API after (not API only)",
      (days.get("2026-09-03"), days.get("2026-09-10"), days.get("2026-09-11")), (60.0, 6.0, 6.0))
check("  both sources named", info["source"], "both")
check("  VAT added: 10 on the invoice + 20% on 10 of API spend", info["vat_added"], 12.0)
days, info = AC.by_day(CFG, "ws1", "UK", "2026-09-01", "2026-09-11", None)
check("unset VAT rate: nothing added", sum(days.values()), 60.0)
check("  and said", "not set" in info["note"], True)

print("\n== 2. the settlement tab's account charge ==")
check("orders calendar: no order carries either fee",
      EX.account_level_charge(CFG, "ws1", "ES", "2026-09-01", "2026-09-30"), 32.0)
check("settlement: the removal fee is on its product row already",
      EX.account_level_charge(CFG, "ws1", "ES", "2026-09-01", "2026-09-30",
                              attributed_by="products"), 30.0)

print("\n== 3. settled sales, no per-order postings ==")
check("only the 'other' fees are sure to be the account's",
      EX.account_level_charge(CFG, "ws1", "DE", "2026-09-01", "2026-09-30"), 30.0)

print("\n== 4. the money calendar counts the subscription once ==")
by_order = EX.account_money_by_day(CFG, "ws1", "FR", "2026-09-01", "2026-09-30")
by_money = EX.account_money_by_day(CFG, "ws1", "FR", "2026-09-01", "2026-09-30", fees_in_rows=True)
check("order calendar: the 30 is placed on its day",
      round(sum(v["account_charges"] for v in by_order.values()), 2), 30.0)
check("money calendar: already in the day's fees, nothing more",
      round(sum(v["account_charges"] for v in by_money.values()), 2), 0.0)
t = SD.totals(CFG, "ws1", "FR", "2026-09-01", "2026-09-30", vat_rate=0, basis="money")
check("the money-calendar profit falls by 30, not 60", t.get("profit"), -30.0)

print("\n== 5. a refund on the order's own footing ==")
d = {"profit": 10.0, "cogs": 5.0, "margin_pct": 50.0, "note": ""}
OV.apply_refund(d, {"refunds": 10.0, "refund_tax": 2.0, "refund_fees_returned": 1.2},
                vat_rate=0.2, order_total=24.0)
check("price + listed tax back, VAT out once, fee back", d["profit"], 1.2)
check("  margin over the same base (24 less its VAT)", d["margin_pct"], 6.0)
check("  what went back is named", d["refunded"], 12.0)

print("\n== 6. every transaction ==")
m = lambda v: {"CurrencyCode": "GBP", "CurrencyAmount": v}  # noqa: E731
EV = {
    "AdjustmentEventList": [
        {"PostedDate": "2026-09-10T00:00:00Z", "AdjustmentType": "WAREHOUSE_DAMAGE",
         "AdjustmentAmount": m(8.0)},
        {"PostedDate": "2026-09-11T00:00:00Z", "AdjustmentType": "COMPENSATED_CLAWBACK",
         "AdjustmentAmount": m(-3.0)},
        {"PostedDate": "2026-09-12T00:00:00Z", "AdjustmentType": "ReserveDebit",
         "AdjustmentAmount": m(-100.0)}],
    "FBALiquidationEventList": [{"PostedDate": "2026-09-13T00:00:00Z",
                                 "LiquidationProceedsAmount": m(12.0),
                                 "LiquidationFeeAmount": m(2.0)}],
    "TaxWithholdingEventList": [{"PostedDate": "2026-09-13T00:00:00Z", "WithheldAmount": m(1.5)}],
    "ImagingServicesFeeEventList": [{"PostedDate": "2026-09-13T00:00:00Z",
                                     "FeeList": [{"FeeType": "ImagingFee", "FeeAmount": m(-4.0)}]}],
    "CouponPaymentEventList": [{"PostedDate": "2026-09-14T00:00:00Z",
                                "FeeComponent": {"FeeType": "CouponRedemptionFee", "FeeAmount": m(-0.6)},
                                "ChargeComponent": {"ChargeType": "Tax", "ChargeAmount": m(-0.12)}}],
}
rows, notes = FD.parse_events({"FinancialEvents": EV}, sku_to_asin={}, fallback_date="2026-09-30")
T = {}
for r in rows:
    if r["asin"] == "*":
        for k, v in r.items():
            if isinstance(v, (int, float)):
                T[k] = round(T.get(k, 0) + v, 2)
check("a clawback is money taken back (8 - 3), a reserve is not income or cost",
      T.get("reimbursements"), 5.0)
check("liquidation 12 - 2, tax withheld -1.5, imaging fee -4",
      T.get("adjustments"), 4.5)
check("a coupon with no total: its fee and charge components", T.get("promo_fees"), 0.72)

REF = {"RefundEventList": [{"AmazonOrderId": "R-1", "PostedDate": "2026-09-20T00:00:00Z",
                            "ShipmentItemAdjustmentList": [{
                                "SellerSKU": "S", "QuantityShipped": 1,
                                "ItemChargeAdjustmentList": [
                                    {"ChargeType": "Principal", "ChargeAmount": m(-10.0)}],
                                "PromotionAdjustmentList": [{"PromotionAmount": m(1.0)}]}]}]}
orows, _sk = OF.parse_by_order({"FinancialEvents": REF})
check("a refund-only order row carries no promotion (so it never looks settled)",
      [r["promos"] for r in orows], [0.0])
check("  its refund is net of the coupon posted back", [r["refunds"] for r in orows], [9.0])

print("\nFAILURES: %d" % len(FAILS))
sys.exit(1 if FAILS else 0)
