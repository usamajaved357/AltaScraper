"""Every money movement Amazon posts reaches exactly one bucket (owner, 30 Sep
2026: "accurate calculations on profits ... the transactions that are performed
in the account").

Built from the SHAPES measured on nestwell_goods' real Finances events that day
(listFinancialEvents, 90 days): RefundCommission is a negative fee adjustment,
the Amazon Ads invoices come in ProductAdsPaymentEventList in camelCase with a
base and a VAT value, the subscription is an undated ServiceFee, a refund posts
the funded promotion back. The check at the end is the one that matters: the
app's buckets net to the same figure as Amazon's own lines."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from domain import finance_data as FD   # noqa: E402
from domain import order_finance as OF  # noqa: E402

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def m(v):
    return {"CurrencyCode": "GBP", "CurrencyAmount": v}


EV = {
    "ShipmentEventList": [{
        "AmazonOrderId": "202-1", "PostedDate": "2026-09-10T10:00:00Z",
        "ShipmentItemList": [{
            "SellerSKU": "S1", "QuantityShipped": 1,
            "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": m(20.00)}],
            "ItemFeeList": [{"FeeType": "Commission", "FeeAmount": m(-3.00)},
                            {"FeeType": "DigitalServicesFee", "FeeAmount": m(-0.06)}],
            "PromotionList": [{"PromotionType": "X", "PromotionAmount": m(-2.00)}]}]}],
    "RefundEventList": [{
        "AmazonOrderId": "202-1", "PostedDate": "2026-09-12T10:00:00Z",
        "ShipmentItemAdjustmentList": [{
            "SellerSKU": "S1", "QuantityShipped": 1,
            "ItemChargeAdjustmentList": [{"ChargeType": "Principal", "ChargeAmount": m(-20.00)},
                                         {"ChargeType": "ReturnShipping", "ChargeAmount": m(-0.01)}],
            "PromotionAdjustmentList": [{"PromotionType": "X", "PromotionAmount": m(2.00)}],
            "ItemFeeAdjustmentList": [{"FeeType": "Commission", "FeeAmount": m(3.00)},
                                      {"FeeType": "RefundCommission", "FeeAmount": m(-0.60)}]}]}],
    "ServiceFeeEventList": [{"FeeList": [{"FeeType": "Subscription", "FeeAmount": m(-30.00)}]}],
    "ProductAdsPaymentEventList": [{
        "postedDate": "2026-09-16T15:57:58Z", "transactionType": "Charge",
        "baseValue": m(-100.00), "taxValue": m(-20.00), "transactionValue": m(-120.00)}],
    "CouponPaymentEventList": [{"PostedDate": "2026-09-11T00:00:00Z", "TotalAmount": m(-0.50)}],
    "AdjustmentEventList": [{"PostedDate": "2026-09-13T00:00:00Z",
                             "AdjustmentType": "PostageBilling_Postage", "AdjustmentAmount": m(-3.20)}],
    "SellerReviewEnrollmentPaymentEventList": [{"PostedDate": "2026-09-14T00:00:00Z",
                                                "TotalAmount": m(-150.00)}],
    "DebtRecoveryEventList": [{"RecoveryAmount": m(30.00)}],        # a transfer: never counted
}

rows, notes = FD.parse_events({"FinancialEvents": EV}, sku_to_asin={"S1": "B0X"},
                              fallback_date="2026-09-30")
T = {}
for r in rows:
    if r["asin"] == "*":
        for k, v in r.items():
            if isinstance(v, (int, float)):
                T[k] = round(T.get(k, 0) + v, 2)

print("== the account's money, bucket by bucket ==")
check("refund commission is a cost, not money returned (3.00 - 0.60)", T.get("refund_fees_returned"), 2.40)
check("the Ads invoice, ex-VAT", T.get("ads_charged"), 100.00)
check("  and its VAT, apart", T.get("ads_charged_tax"), 20.00)
check("the funded promotion comes back with the refund", T.get("promos"), 0.00)
check("return postage goes with the refund", T.get("refunds"), 20.01)
check("coupon redemption fees are promotion fees", T.get("promo_fees"), 0.50)
check("postage labels and Vine enrolment are counted (signed)", T.get("adjustments"), -153.20)
check("the undated subscription is kept", T.get("other_fees"), 30.06)
check("the catch-all names the list it read", notes.get("other_event_lists"),
      ["SellerReviewEnrollmentPaymentEventList"])

print("\n== it all adds up to Amazon's own figure ==")
net = (T.get("principal", 0) + T.get("tax", 0) - T.get("referral_fees", 0) - T.get("fba_fees", 0)
       - T.get("other_fees", 0) - T.get("promo_fees", 0) - T.get("promos", 0) - T.get("refunds", 0)
       - T.get("refund_tax", 0) + T.get("refund_fees_returned", 0) + T.get("reimbursements", 0)
       - T.get("ads_charged", 0) - T.get("ads_charged_tax", 0) + T.get("adjustments", 0))
amazon = (20.00 - 3.00 - 0.06 - 2.00) + (-20.00 - 0.01 + 2.00 + 3.00 - 0.60) - 30.00 - 120.00 \
         - 0.50 - 3.20 - 150.00
check("buckets net to Amazon's lines (transfers excluded)", round(net, 2), round(amazon, 2))

print("\n== the same order, per order ==")
_res = OF.parse_by_order({"FinancialEvents": EV})
orows = _res[0] if isinstance(_res, tuple) else _res
o = {}
for r in orows:
    if r.get("order_id") == "202-1":
        for k, v in r.items():
            if isinstance(v, (int, float)):
                o[k] = round(o.get(k, 0) + v, 2)
check("the order's refund includes return postage", o.get("refunds"), 20.01)
check("the order's promotion is reversed on refund", o.get("promos"), 0.00)
check("the order's returned fee is net of the refund commission", o.get("refund_fees_returned"), 2.40)

print("\nFAILURES: %d" % len(FAILS) if FAILS else "\nFAILURES: 0")
sys.exit(1 if FAILS else 0)
