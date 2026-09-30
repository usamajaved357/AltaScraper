"""Finances 2024-06-19 (listTransactions) read through the one finance parser.

Owner, 30 Sep 2026: "do the newer finance list switch". The old list (v0
listFinancialEvents) left out money Amazon was still holding and showed a
released hold on the RELEASE day: nestwell_goods' 2 Jul - 29 Sep refunds read
140.62 where 156.61 went back (a 15.99 refund of 24 Sep was on hold).

  1. CHARACTERIZATION: what the (unchanged) v0 parser makes of a fixture of
     old-list events, pinned.
  2. The SAME money as newer-list transactions gives the SAME rows, column for
     column, through finance_transactions.to_events -- in finance_daily and in
     order_fees. Shapes copied from a live nestwell_goods pull (30 Sep 2026).
  3. What only the newer list can do: a held refund dated on the day it was
     given; a released hold counted once, on its own day; a transaction on two
     pages counted once.
  4. The rest: ad invoice VAT, subscription, coupon fees, adjustments, the
     transactions that are not income or cost, an unknown type kept.
  5. fetch_range asks the 2024-06-19 client, pages with nextToken, sends no
     marketplaceId.

No Amazon call is made.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from domain import finance_data as fd
from domain import finance_transactions as ftx
from domain import order_finance as of
from domain import finance_fetch as ff

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

SMAP = {"SKU-A": "B0AAAAAAAA", "SKU-B": "B0BBBBBBBB"}


# ---- the old list's events (v0 shape, as Amazon sends them) -----------------
def m0(v):
    return {"CurrencyAmount": v, "CurrencyCode": "GBP"}

V0 = {"FinancialEvents": {
    "ShipmentEventList": [{
        "AmazonOrderId": "203-0000001", "PostedDate": "2026-09-02T10:00:00Z",
        "ShipmentItemList": [{
            "SellerSKU": "SKU-A", "QuantityShipped": 1,
            "ItemChargeList": [{"ChargeType": "Principal", "ChargeAmount": m0(29.99)},
                               {"ChargeType": "Tax", "ChargeAmount": m0(0.0)}],
            "ItemFeeList": [{"FeeType": "Commission", "FeeAmount": m0(-5.40)},
                            {"FeeType": "DigitalServicesFee", "FeeAmount": m0(-0.11)}],
            "PromotionList": [{"PromotionAmount": m0(-1.50)}]}]}],
    "RefundEventList": [
        {"AmazonOrderId": "206-0000002", "PostedDate": "2026-09-16T22:56:41Z",   # partial
         "ShipmentItemAdjustmentList": [{
             "SellerSKU": "SKU-B", "QuantityShipped": 1,
             "ItemChargeAdjustmentList": [{"ChargeType": "Principal", "ChargeAmount": m0(-8.69)}],
             "ItemFeeAdjustmentList": [{"FeeType": "Commission", "FeeAmount": m0(1.36)},
                                       {"FeeType": "RefundCommission", "FeeAmount": m0(-0.28)},
                                       {"FeeType": "DigitalServicesFee", "FeeAmount": m0(0.03)}]}]},
        {"AmazonOrderId": "203-0000003", "PostedDate": "2026-09-01T23:51:30Z",
         "ShipmentItemAdjustmentList": [{
             "SellerSKU": "SKU-A", "QuantityShipped": 1,
             "ItemChargeAdjustmentList": [{"ChargeType": "ReturnShipping", "ChargeAmount": m0(-0.01)},
                                          {"ChargeType": "Principal", "ChargeAmount": m0(-29.99)}],
             "PromotionAdjustmentList": [{"PromotionAmount": m0(1.50)}],
             "ItemFeeAdjustmentList": [{"FeeType": "Commission", "FeeAmount": m0(5.40)},
                                       {"FeeType": "RefundCommission", "FeeAmount": m0(-1.08)},
                                       {"FeeType": "DigitalServicesFee", "FeeAmount": m0(0.11)}]}]}],
    "ServiceFeeEventList": [
        {"PostedDate": "2026-09-19T23:40:31Z",
         "FeeList": [{"FeeType": "Subscription", "FeeAmount": m0(-30.0)}]},
        {"PostedDate": "2026-09-17T06:57:07Z",
         "FeeList": [{"FeeType": "CouponParticipationFee", "FeeAmount": m0(-2.40)}]},
        {"PostedDate": "2026-09-17T06:52:32Z",
         "FeeList": [{"FeeType": "CouponPerformanceFee", "FeeAmount": m0(0.0)}]}],
    "ProductAdsPaymentEventList": [
        {"postedDate": "2026-09-16T15:57:58Z", "transactionType": "Charge",
         "baseValue": m0(-200.42), "taxValue": m0(-40.08), "transactionValue": m0(-240.50)}],
    "AdjustmentEventList": [
        {"PostedDate": "2026-09-10T08:00:00Z", "AdjustmentType": "WAREHOUSE_DAMAGE",
         "AdjustmentAmount": m0(12.0),
         "AdjustmentItemList": [{"SellerSKU": "SKU-A", "TotalAmount": m0(12.0)}]},
        {"PostedDate": "2026-09-11T08:00:00Z", "AdjustmentType": "PostageBilling_Postage",
         "AdjustmentAmount": m0(-3.20), "AdjustmentItemList": []}],
}}


# ---- the same money on the newer list (2024-06-19 shape, as measured) -------
def m(v):
    return {"currencyAmount": v, "currencyCode": "GBP"}

def n(t, v, kids=()):
    return {"breakdownType": t, "breakdownAmount": m(v), "breakdowns": list(kids)}

def fee(t, v):
    # A fee as Amazon itemises it: its own total, split into Base and Tax.
    base = round(v / 1.2, 2)
    return n(t, v, [n("Base", base), n("Tax", round(v - base, 2))])

def ctx(sku, q=1):
    return [{"contextType": "ProductContext", "sku": sku, "asin": SMAP.get(sku),
             "quantityShipped": q}]

def rel(**kw):
    return [{"relatedIdentifierName": k, "relatedIdentifierValue": v} for k, v in kw.items()]

def tx(tid, ttype, posted, total, items, status="RELEASED", related=None, desc=""):
    return {"transactionId": tid, "transactionType": ttype, "transactionStatus": status,
            "postedDate": posted, "totalAmount": m(total), "description": desc or ttype,
            "relatedIdentifiers": related or [], "items": items, "breakdowns": [],
            "marketplaceDetails": {"marketplaceName": "Amazon.co.uk"}}

def sale(tid, order, posted, status="RELEASED", related=None, sku="SKU-A"):
    return tx(tid, "Shipment", posted, 22.98, [{
        "totalAmount": m(22.98), "contexts": ctx(sku),
        "breakdowns": [n("DigitalServicesFee", -0.11, [fee("DigitalServicesFee", -0.11)]),
                       n("ProductCharges", 29.99, [n("OurPricePrincipal", 29.99)]),
                       n("AmazonFees", -5.40, [fee("Commission", -5.40)]),
                       n("PromoRebates", -1.50, [n("OurPriceDiscount", -1.50)])]}],
        status=status, related=(related or []) + rel(ORDER_ID=order))

def refund(tid, order, posted, sku, principal, comm, rcomm, dst, status="RELEASED",
           related=None, promo=0.0, other=0.0):
    b = [n("DigitalServicesFee", dst, [fee("DigitalServicesFee", dst)]),
         n("ProductCharges", principal, [n("OurPricePrincipal", principal)]),
         n("AmazonFees", round(comm + rcomm, 2), [fee("Commission", comm), fee("RefundCommission", rcomm)])]
    if promo:
        b.append(n("PromoRebates", promo, [n("OurPriceDiscount", promo)]))
    if other:
        b.append(n("Other", other, [n("ReturnShippingPrincipal", other)]))
    return tx(tid, "Refund", posted, 0.0, [{"totalAmount": m(0.0), "contexts": ctx(sku),
                                            "breakdowns": b}],
              status=status, related=(related or []) + rel(ORDER_ID=order))

V2024 = [
    sale("t-sale", "203-0000001", "2026-09-02T10:00:00Z"),
    refund("t-rf-b", "206-0000002", "2026-09-16T22:56:41Z", "SKU-B", -8.69, 1.36, -0.28, 0.03),
    refund("t-rf-c", "203-0000003", "2026-09-01T23:51:30Z", "SKU-A", -29.99, 5.40, -1.08, 0.11,
           promo=1.50, other=-0.01),
    tx("t-sub", "ServiceFee", "2026-09-19T23:40:31Z", -30.0, [{
        "totalAmount": m(-30.0), "contexts": [{"contextType": "ProductContext", "sku": None,
                                                "asin": None, "quantityShipped": 0}],
        "breakdowns": [n("AmazonFees", -30.0, [fee("Subscription", -30.0)])]}], desc="Subscription"),
    tx("t-cpn", "ServiceFee", "2026-09-17T06:57:07Z", -2.40, [{
        "totalAmount": m(-2.40), "contexts": [],
        "breakdowns": [n("AmazonFees", -2.40, [n("CouponParticipationFeeRollup", -2.40, [
            fee("CouponParticipationFee", -2.40)])])]}], desc="CouponParticipationEvent"),
    tx("t-cpf", "ServiceFee", "2026-09-17T06:52:32Z", 0.0, [{
        "totalAmount": m(0.0), "contexts": [],
        "breakdowns": [n("AmazonFees", 0.0, [n("CouponPerformanceFeeRollup", 0.0, [
            n("CouponPerformanceFee", 0.0, [n("Base", -2.35), n("Promo", 2.35)])])])]}]),
    tx("t-ads", "ProductAdsPayment", "2026-09-16T15:57:58Z", -240.50, [{
        "totalAmount": m(-240.50), "contexts": None,
        "breakdowns": [n("Base", -200.42), n("Tax", -40.08)]}]),
    # Adjustment shapes: NOT yet seen on a live account (none in 125 days of
    # nestwell_goods); built to Amazon's documented fields.
    tx("t-adj1", "Adjustment", "2026-09-10T08:00:00Z", 12.0, [{
        "totalAmount": m(12.0), "contexts": ctx("SKU-A"),
        "breakdowns": [n("WAREHOUSE_DAMAGE", 12.0)]}], desc="WAREHOUSE_DAMAGE"),
    tx("t-adj2", "Adjustment", "2026-09-11T08:00:00Z", -3.20, [],
       desc="PostageBilling_Postage"),
]

COLS = [c for c in fd._COLS if c not in ("source",)]


def table(rows):
    return {(r["date"], r["asin"]): {c: (round(r.get(c) or 0, 2) if c != "currency"
                                         else r.get(c)) for c in COLS} for r in rows}


print("== 1. characterization: the v0 parser on old-list events ==")
r0, n0 = fd.parse_events(V0, SMAP)
t0 = table(r0)
star = {d: t0[(d, a)] for (d, a) in t0 if a == "*"}
check("sale day: principal / referral / other / promos / units",
      [star["2026-09-02"][c] for c in ("principal", "referral_fees", "other_fees", "promos", "units")],
      [29.99, 5.40, 0.11, 1.50, 1])
check("partial refund: refunds / units / fees returned (RefundCommission signed)",
      [star["2026-09-16"][c] for c in ("refunds", "refund_units", "refund_fees_returned")],
      [8.69, 1, 1.11])
check("refund with the funded discount and return postage: 29.99+0.01-1.50",
      [star["2026-09-01"][c] for c in ("refunds", "refund_fees_returned")], [28.50, 4.43])
check("ad invoice apart from its VAT",
      [star["2026-09-16"][c] for c in ("ads_charged", "ads_charged_tax")], [200.42, 40.08])
check("subscription in other fees", star["2026-09-19"]["other_fees"], 30.0)
check("coupon participation fee in promo fees", star["2026-09-17"]["promo_fees"], 2.40)
check("reimbursement, signed", star["2026-09-10"]["reimbursements"], 12.0)
check("postage adjustment, signed", star["2026-09-11"]["adjustments"], -3.20)
check("product rows: the sale under its ASIN",
      t0[("2026-09-02", "B0AAAAAAAA")]["principal"], 29.99)
check("no unknown fee types", n0["unknown_fee_types"], [])
o0, s0 = of.parse_by_order(V0)

print("\n== 2. the same money on the newer list: the same rows ==")
ev, info = ftx.to_events(V2024)
r2, n2 = fd.parse_events(ev, SMAP)
t2 = table(r2)
check("same (date, asin) rows", sorted(t2), sorted(t0))
diff = [(k, c, t0[k][c], t2.get(k, {}).get(c)) for k in t0 for c in COLS
        if t0[k][c] != t2.get(k, {}).get(c)]
check("every finance_daily column equal", diff, [])
check("no unknown fee types", n2["unknown_fee_types"], [])
o2, s2 = of.parse_by_order(ev)
key = lambda rows: sorted((r["order_id"], r["posted_date"], tuple(r[c] for c in of._COLS))
                          for r in rows)
check("order_fees rows equal", key(o2), key(o0))

print("\n== 3. what only the newer list gets right ==")
held = [
    # A refund given on 24 Sep and still on hold (DD7) -- the old list omitted it.
    refund("t-held-rf", "202-6550607", "2026-09-24T22:27:04Z", "SKU-B", -15.99, 2.88, -0.58,
           0.06, status="DEFERRED"),
    # A sale still on hold.
    sale("t-held-sale", "205-0000009", "2026-09-29T07:34:32Z", status="DEFERRED"),
    # A refund held, then released: the original (on the day it was given)...
    refund("t-orig", "026-4940553", "2026-08-18T18:06:53Z", "SKU-A", -8.49, 0.82, -0.17, 0.02,
           status="DEFERRED_RELEASED", related=rel(RELEASE_TRANSACTION_ID="t-release")),
    # ...and its release, eight days later.
    refund("t-release", "026-4940553", "2026-08-26T13:51:10Z", "SKU-A", -8.49, 0.82, -0.17, 0.02,
           status="RELEASED", related=rel(DEFERRED_TRANSACTION_ID="t-orig")),
]
ev3, info3 = ftx.to_events(held + [held[0]])          # the same one again: a page overlap
r3, _n3 = fd.parse_events(ev3, SMAP)
s3 = {r["date"]: r for r in r3 if r["asin"] == "*"}
check("held refund: on the day it was given (24 Sep), counted once",
      (s3.get("2026-09-24") or {}).get("refunds"), 15.99)
check("held sale: counted", (s3.get("2026-09-29") or {}).get("principal"), 29.99)
check("released hold: on the day it happened (18 Aug)",
      (s3.get("2026-08-18") or {}).get("refunds"), 8.49)
check("  and NOT again on the release day (26 Aug)", "2026-08-26" in s3, False)
check("info: one release skipped, one duplicate, two held",
      (info3["skipped_releases"], info3["duplicates"], info3["deferred"]), (1, 1, 2))
o3, _ = of.parse_by_order(ev3)
check("order_fees: the released refund once, on 18 Aug",
      sorted((r["order_id"], r["posted_date"], r["refunds"]) for r in o3
             if r["order_id"] == "026-4940553"), [("026-4940553", "2026-08-18", 8.49)])

print("\n== 4. not income or cost; unknown types kept ==")
other = [tx("t-tr", "Transfer", "2026-09-05T00:00:00Z", -500.0, []),
         tx("t-debt", "DebtRecovery", "2026-07-31T20:09:27Z", 30.0, []),
         tx("t-micro", "AdhocDisbursement", "2026-08-06T16:37:16Z", -0.01, []),
         tx("t-new", "SomethingNew", "2026-09-12T00:00:00Z", -4.0, [])]
ev4, info4 = ftx.to_events(other)
r4, n4 = fd.parse_events(ev4, SMAP)
s4 = {r["date"]: r for r in r4 if r["asin"] == "*"}
check("payout, debt payment and micro-deposit: ignored", info4["ignored"], 3)
check("  nothing stored for them", sorted(s4), ["2026-09-12"])
check("an unknown type: signed into adjustments", s4["2026-09-12"]["adjustments"], -4.0)
check("  and NAMED", n4["other_event_lists"], ["Transaction:SomethingNew"])

print("\n== 5. fetch_range reads the 2024-06-19 list ==")
src = open(ff.__file__, encoding="utf-8").read()
check("the client is built with version=2024-06-19",
      ("version=FINANCES_VERSION" in src, ff.FINANCES_VERSION), (True, "2024-06-19"))
from sp_api.api import Finances
from sp_api.api.finances.finances_2024_06_19 import FinancesV20240619
check("the installed library maps that version to FinancesV20240619",
      Finances._VERSION_MAP.get(ff.FINANCES_VERSION) is FinancesV20240619, True)
calls = []
class _Resp:
    def __init__(self, p): self.payload = p
class _Fake:
    def list_transactions(self, **kw):
        calls.append(kw)
        if not kw.get("nextToken"):
            return _Resp({"transactions": V2024[:3], "nextToken": "p2"})
        return _Resp({"transactions": V2024[2:]})        # t-rf-c on both pages
_real_client, _real_pause = ff._client, ff.PAUSE
ff._client = lambda mkt, creds: _Fake()
ff.PAUSE = 0
try:
    evf, tok, pages = ff.fetch_range("UK", {}, "2026-09-01", "2026-09-15")
finally:
    ff._client, ff.PAUSE = _real_client, _real_pause
check("two pages, no token left", (pages, tok), (2, None))
check("page 2 carries nextToken AND the window", sorted(calls[1]),
      ["nextToken", "postedAfter", "postedBefore"])
check("no marketplaceId: the whole account's money", any("marketplaceId" in c for c in calls), False)
check("a transaction on two pages counted once", evf["info"]["duplicates"], 1)
rf, _ = fd.parse_events(evf, SMAP)
check("  so the pages parse to the same rows as the list read once",
      table(rf), table(fd.parse_events(ftx.to_events(V2024)[0], SMAP)[0]))

print("\n== 6. replies read through the REAL library response (change review) ==")
import json as _json
from sp_api.base._core import parse_response
class _Http:
    """What the library's transport hands parse_response: status, body, headers."""
    def __init__(self, body, status=200):
        self.status_code, self._body, self.headers = status, body, {}
    def json(self):
        if isinstance(self._body, str):
            return _json.loads(self._body)
        return self._body
class _Lib:
    def __init__(self, body, status=200): self.body, self.status = body, status
    def list_transactions(self, **kw):
        return parse_response(_Http(self.body, self.status), method="GET")
one = [V2024[0]]
# MEASURED 30 Sep 2026 (live GET, nestwell_goods, 125 days, 224 transactions on
# one page): top-level keys ["payload", "statusCode"], payload keys
# ["transactions"]. No account had a second page, so where nextToken sits on a
# multi-page reply is Amazon's documented place (payload.nextToken) -- and the
# library's resp.next_token is read as well in case it arrives at top level.
txs, tok = ff._list_page(_Lib({"payload": {"transactions": one, "nextToken": "T2"},
                                "statusCode": 200}), "a", "b")
check("measured shape: transactions read, nextToken inside the payload", (len(txs), tok), (1, "T2"))
txs, tok = ff._list_page(_Lib({"transactions": one, "nextToken": "T3"}), "a", "b")
check("nextToken at top level: taken from resp.next_token", (len(txs), tok), (1, "T3"))
txs, tok = ff._list_page(_Lib({"payload": {"transactions": []}, "statusCode": 200}), "a", "b")
check("a genuine empty page is empty, not an error", (txs, tok), ([], None))
for label, body, status in (("an error body with no 'errors' key", {"message": "Endpoint request timed out"}, 504),
                            ("a non-JSON body", "<html>gateway</html>", 502),
                            ("a payload without transactions", {"payload": {}}, 200)):
    try:
        ff._list_page(_Lib(body, status), "a", "b")
        got = "no error"
    except Exception as ex:
        got = "raised" if "no transactions list" in str(ex) else "other: %s" % ex
    check("%s RAISES (never read as zero money)" % label, got, "raised")

print("\n== 7. charge names the old parser did not count; withheld tax ==")
odd = sale("t-odd", "203-0000077", "2026-09-05T10:00:00Z")
odd["items"][0]["breakdowns"].append(n("ProductCharges", 2.0, [n("SomeNewSurcharge", 2.0)]))
odd["items"][0]["breakdowns"].append(n("TaxWithheld", -4.0, [n("MarketplaceFacilitatorVAT-Principal", -4.0)]))
odd["items"][0]["breakdowns"].append(n("Tax", 0.0, [n("OurPriceTax", 4.0),
                                                   n("OurPriceTaxWithheld", -4.0)]))
ev7, info7 = ftx.to_events([odd])
r7, n7 = fd.parse_events(ev7, SMAP)
s7 = [r for r in r7 if r["asin"] == "*"][0]
check("an unknown charge is NOT principal", s7["principal"], 29.99)
check("  it is kept, signed, in adjustments", s7["adjustments"], 2.0)
check("  and named", n7["other_event_lists"], ["Charge:SomeNewSurcharge"])
check("tax collected is kept; withheld tax is left out (as v0 did)", s7["tax"], 4.0)
check("  withheld lines counted in info", info7["withheld_ignored"], 2)
check("  and none of it reaches fees", (s7["other_fees"], n7["unknown_fee_types"]), (0.11, []))

print("\n%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
