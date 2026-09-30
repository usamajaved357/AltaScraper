"""domain/finance_data.py -- what Amazon charged, and what went back to buyers.

WHERE IT COMES FROM
The Finances API -- since 30 Sep 2026 the 2024-06-19 listTransactions, written
back into the v0 listFinancialEvents shape this parser reads (see
domain/finance_transactions.py). This is a different question from the
Sales & Traffic report, not a better answer to the same one:

    Sales & Traffic  ->  what was ORDERED, by order date
    Finances         ->  what was CHARGED and REFUNDED, by posted date

They will never tie out exactly and are not supposed to. An order placed on the
1st and refunded on the 9th is revenue on the 1st and a refund on the 9th. Anyone
comparing the two columns and finding a gap has found the definition, not a bug.

THREE THINGS THIS MODULE IS CAREFUL ABOUT

1. SIGNS. Amazon sends fees negative, because from Amazon's side the money is
   leaving. Stored positive here, because "Amazon fees: 3.00" is what a person
   means by a fee, and a column that is sometimes signed and sometimes not is
   exactly how a profit figure silently comes out backwards. Refunds are stored
   positive too, as money that went back.

2. SKU, NOT ASIN. Financial events are keyed by seller SKU. The dashboard is
   keyed by ASIN. The mapping comes from the live catalogue snapshot the app
   already keeps. Where a SKU cannot be mapped -- a listing deleted since, a SKU
   from before the catalogue was synced -- the money is STILL counted on the
   account total. A fee you cannot attribute is a fee you still paid, and
   dropping it would quietly overstate profit.

3. UNKNOWN FEE TYPES ARE KEPT, NOT DROPPED. Amazon adds fee types without
   notice. Anything unrecognised lands in other_fees and is reported in
   `unknown_fee_types` so it can be classified later. Silently discarding a fee
   type is how a dashboard drifts away from Seller Central by a few percent and
   nobody can say why.

VERIFYING THE SHAPES
Written to Amazon's documented response shape. `raw_sample()` returns one page
verbatim so the first live run can confirm it rather than us assuming -- see
CLAUDE.md Rule 4. Until that run happens, treat the field names here as
unconfirmed.
"""
import time

from data import db as _db

# Fee types, bucketed. The membership tests are on the LOWERCASED type, and by
# substring, because Amazon spells these inconsistently across marketplaces
# (FBAPerUnitFulfillmentFee, FBAPerOrderFulfillmentFee, FBAWeightBasedFee...).
_REFERRAL = ("commission", "referralfee", "variableclosingfee", "fixedclosingfee")
_FBA = ("fba", "fulfillmentfee", "fulfilmentfee", "storagefee", "weightbased",
        "shippingchargeback", "giftwrapchargeback")

# THE PRICE OF A PROMOTION, pulled out of "other".
#
# Amazon charges a fee each time a coupon is redeemed and a flat fee to run a
# Lightning or Best Deal. These used to land in other_fees beside the monthly
# subscription and the digital services fee, where they could not be told apart
# -- and they are the only charges in that bucket that are the price of a
# CHOICE, so they are the only ones worth seeing on their own.
#
# Matched by substring for the same reason the two above are: Amazon spells
# these inconsistently across marketplaces. An unrecognised spelling still lands
# in other_fees and is REPORTED as unknown (see _is_known), so a fee type nobody
# has seen surfaces rather than being quietly absorbed.
_PROMO = ("coupon", "lightningdeal", "bestdeal", "dealfee", "promotionfee")

# Adjustment types that are money coming BACK to you for Amazon's own errors.
_REIMBURSEMENT = ("reimbursement", "warehouse_damage", "warehouse_lost",
                  "reversal_reimbursement", "compensated_clawback")

# Fee types confirmed against a live UK account on 13 Aug 2026. They genuinely
# belong in other_fees; listing them here stops them being reported as
# "unknown" every single pull, so that report keeps meaning "Amazon has started
# charging something we have never seen" rather than being permanent noise.
_KNOWN_OTHER = ("subscription", "digitalservicesfee", "csbafee", "shippinghb")

# Event lists we deliberately DO NOT read, and why. Left explicit so the next
# person does not assume they were forgotten:
#   AdhocDisbursementEventList  -- money moving to your bank. A transfer, not a
#                                  cost; counting it would double-count.
#   DebtRecoveryEventList       -- Amazon recovering a balance already charged
#                                  elsewhere. Counting it charges you twice.
_IGNORED_EVENTS = ("AdhocDisbursementEventList", "DebtRecoveryEventList",
                   "FailedAdhocDisbursementEventList", "LoanServicingEventList",
                   # Amazon Pay (a different business), and the shipment-settle /
                   # trial lists that repeat what ShipmentEventList already holds.
                   "PayWithAmazonEventList", "ShipmentSettleEventList",
                   "TrialShipmentEventList")

# Read in the body of parse_events, each by its own shape. Anything else that
# carries money lands in `adjustments` (signed) through the catch-all, and is
# NAMED in the notes -- so a charge Amazon starts sending tomorrow reaches the
# profit instead of vanishing (owner, 30 Sep 2026: every transaction counted).
_READ_EVENTS = ("ShipmentEventList", "RefundEventList", "ChargebackEventList",
                "GuaranteeClaimEventList", "ServiceFeeEventList", "AdjustmentEventList",
                "ProductAdsPaymentEventList", "CouponPaymentEventList",
                "SellerDealPaymentEventList", "RemovalShipmentEventList",
                "RetrochargeEventList")


def _amt(node):
    """A money node -> float. Amazon nests the number one level down."""
    if not isinstance(node, dict):
        return 0.0
    for k in ("CurrencyAmount", "Amount", "value"):
        v = node.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _cur(node):
    if not isinstance(node, dict):
        return ""
    return str(node.get("CurrencyCode") or node.get("currency") or "")


def _bucket_fee(fee_type):
    t = str(fee_type or "").lower().replace("_", "").replace("-", "")
    if any(k in t for k in _REFERRAL):
        return "referral_fees"
    if any(k in t for k in _FBA):
        return "fba_fees"
    # BEFORE the other_fees fallback: a coupon fee is a real category, and it
    # was previously indistinguishable from the monthly subscription.
    if any(k in t for k in _PROMO):
        return "promo_fees"
    return "other_fees"


def _is_known(fee_type):
    t = str(fee_type or "").lower().replace("_", "").replace("-", "")
    return any(k in t for k in _KNOWN_OTHER)


# Everything Amazon calls tax on an item line. Shipping tax and gift-wrap tax are
# VAT just the same -- collected from the buyer and owed onward -- so leaving them
# out would understate what is owed and overstate what was kept.
_TAX_TYPES = {"tax", "shippingtax", "giftwraptax", "shipping tax", "giftwrap tax"}

# What the buyer paid US, as opposed to what they paid the taxman. Postage and
# gift wrap are revenue: the buyer hands it over and it lands in the settlement
# exactly as the item price does. Kept in `principal` rather than in columns of
# their own, because every downstream figure -- net proceeds, profit,
# contribution, margin -- means "what the buyer was charged", and splitting them
# out would mean remembering to add them back in five places.
_REVENUE_TYPES = {"principal", "shippingcharge", "giftwrap",
                  "shipping charge", "gift wrap"}


def _blank(date, asin):
    return {"date": date, "asin": asin, "currency": "",
            "referral_fees": 0.0, "fba_fees": 0.0, "other_fees": 0.0,
            "promo_fees": 0.0,
            # Amazon Ads invoices charged to this account (ProductAdsPaymentEventList):
            # the ex-VAT amount and the VAT on it, apart -- a VAT-registered seller
            # reclaims the second, anyone else pays it.
            "ads_charged": 0.0, "ads_charged_tax": 0.0,
            # Every other money movement, SIGNED: + money to you, - a cost.
            "adjustments": 0.0,
            "refunds": 0.0, "refund_units": 0, "refund_fees_returned": 0.0,
            "reimbursements": 0.0, "promos": 0.0, "principal": 0.0, "tax": 0.0, "refund_tax": 0.0,
            "units": 0, "cogs": 0.0, "cogs_units": 0}


def _day(posted):
    """PostedDate -> YYYY-MM-DD. Amazon sends ISO with a Z."""
    return str(posted or "")[:10]


class _Acc:
    """Accumulates per (date, asin) and per (date, '*') at the same time.

    Every amount is added to BOTH its product and the account total, rather than
    the total being summed from the products afterwards. That is what keeps the
    headline right when a SKU cannot be mapped to an ASIN: the money still
    reaches the total even though it never reaches a product row.
    """

    def __init__(self, sku_to_asin=None):
        self.rows = {}
        self.map = {k.strip().upper(): v for k, v in (sku_to_asin or {}).items() if k}
        self.unknown_fees = set()
        self.unmapped_skus = set()
        self.fallback = ""
        self.unattributed = 0.0        # money that had no date of its own
        self.collect = None            # a list: undated charges kept for placing

    def _get(self, date, asin):
        k = (date, asin)
        if k not in self.rows:
            self.rows[k] = _blank(date, asin)
        return self.rows[k]

    def asin_for(self, sku):
        s = str(sku or "").strip().upper()
        if not s:
            return None
        a = self.map.get(s)
        if not a:
            self.unmapped_skus.add(s)
            return None
        return a

    def count(self, date, sku, units, cost_lookup=None, order_id=None):
        """Units shipped, and what they cost -- on the SAME day basis as the fees.

        Priced HERE, at the line, because this is the only point at which the SKU
        is still in hand. One step later there is only an ASIN, and the SKUs that
        could not be mapped to one would lose their cost entirely -- which would
        understate cost of goods and overstate profit, in that direction, always.

        AND THE ORDER IS STILL IN HAND HERE TOO, which is the other half of the
        same argument. A cost typed against ONE order is the top of the trust
        order everywhere else in the app, and this priced by product alone -- so
        the same order showed one profit on the Orders screen and a different one
        in the Sales daily figures. The order id is passed to the cost function,
        which decides; cogs.lookup ignores it, order_cogs.line_cost_fn uses it.
        """
        if not date or not units:
            return
        cost, _src = (cost_lookup(sku, order_id) if cost_lookup else (None, ""))
        line = round(float(cost) * int(units), 4) if cost is not None else 0.0
        targets = ["*"]
        a = self.asin_for(sku)
        if a:
            targets.append(a)
        for t in targets:
            r = self._get(date, t)
            r["units"] = int(r.get("units", 0) + int(units))
            if cost is not None:
                r["cogs"] = round(r.get("cogs", 0.0) + line, 4)
                r["cogs_units"] = int(r.get("cogs_units", 0) + int(units))

    def add(self, date, sku, field, value, currency="", units=0):
        if not value and not units:
            return
        if not date:
            # Undated: keep the money rather than lose it, and say so.
            if self.collect is not None:
                # Placed later, on a stable day (place_undated).
                self.collect.append({"field": field, "sku": sku,
                                     "amount": value, "currency": currency})
                self.unattributed = round(self.unattributed + abs(value), 2)
                return
            if not self.fallback:
                return
            self.unattributed = round(self.unattributed + abs(value), 2)
            date = self.fallback
        targets = ["*"]
        a = self.asin_for(sku)
        if a:
            targets.append(a)
        for t in targets:
            r = self._get(date, t)
            r[field] = round(r.get(field, 0.0) + value, 4)
            if units:
                r["refund_units"] = int(r.get("refund_units", 0) + units)
            if currency and not r["currency"]:
                r["currency"] = currency


def parse_events(payload, sku_to_asin=None, fallback_date=None, cost_lookup=None,
                 undated=None):
    """Amazon's FinancialEvents -> rows ready for finance_daily.

    Returns (rows, notes). `notes` carries what could not be classified, so an
    unrecognised fee type surfaces instead of vanishing into other_fees unseen.

    fallback_date is used for events Amazon sends with NO PostedDate. A live UK
    account showed the monthly Subscription fee arriving exactly like that -- a
    ServiceFeeEvent carrying a FeeList and nothing else -- and without a date it
    was dropped, understating fees by GBP 30 and overstating what was left. So an
    undated charge is placed on the fallback day and its amount reported in
    `unattributed`. The day it lands on is a guess; the period total is not, and
    of the two the total is the one that must not be wrong.

    `undated`, when given, replaces the fallback day: it is called once with
    every undated charge and returns where each belongs ([{date, field, sku,
    amount, currency}]) -- undated_placer() gives each charge a stable day so
    a re-sync replaces it instead of adding it. (The sync no longer needs it:
    the newer Finances list dates every charge -- see finance_transactions.)
    """
    ev = ((payload or {}).get("FinancialEvents")
          if isinstance(payload, dict) else None) or {}
    acc = _Acc(sku_to_asin)
    acc.fallback = str(fallback_date or "")[:10]
    if undated is not None:
        acc.collect = []

    # ---- shipments: the sale itself, its fees and any promo you funded -------
    for sh in (ev.get("ShipmentEventList") or []):
        d = _day(sh.get("PostedDate"))
        for item in (sh.get("ShipmentItemList") or []):
            sku = item.get("SellerSKU")
            acc.count(d, sku, item.get("QuantityShipped") or 0, cost_lookup,
                      order_id=sh.get("AmazonOrderId"))
            for ch in (item.get("ItemChargeList") or []):
                _ct = str(ch.get("ChargeType") or "").lower()
                # Principal, and the other things the BUYER paid us. A live UK
                # account sends six charge types (probe_finance.py, 14 Aug 2026):
                # Principal, Tax, ShippingCharge, ShippingTax, GiftWrap,
                # GiftWrapTax. Only Principal was kept, so postage a buyer paid
                # was money received and counted nowhere -- zero on that account
                # today because everything ships free, and simply missing the
                # moment anything does not.
                if _ct in _REVENUE_TYPES:
                    acc.add(d, sku, "principal", _amt(ch.get("ChargeAmount")),
                            _cur(ch.get("ChargeAmount")))
                # TAX. Previously dropped on the floor -- it appeared in neither
                # revenue nor cost, so VAT was invisible in every figure the app
                # produced. Kept now whatever it turns out to mean, because the
                # two possibilities need telling apart and only the data can do
                # that: a Tax line ALONGSIDE principal means principal is the
                # ex-VAT price and this is the VAT collected on top; NO tax line
                # on a VAT-registered account means principal is the gross price
                # and the VAT is buried inside it. See vat_for() in sales_data.py.
                elif _ct in _TAX_TYPES:
                    acc.add(d, sku, "tax", _amt(ch.get("ChargeAmount")),
                            _cur(ch.get("ChargeAmount")))
            for fee in (item.get("ItemFeeList") or []):
                ft = fee.get("FeeType")
                bucket = _bucket_fee(ft)
                if bucket == "other_fees" and ft and not _is_known(ft):
                    acc.unknown_fees.add(str(ft))
                # abs(): Amazon sends fees negative; stored positive as a cost.
                acc.add(d, sku, bucket, abs(_amt(fee.get("FeeAmount"))),
                        _cur(fee.get("FeeAmount")))
            for pr in (item.get("PromotionList") or []):
                acc.add(d, sku, "promos", abs(_amt(pr.get("PromotionAmount"))),
                        _cur(pr.get("PromotionAmount")))

    # ---- refunds: principal back to the buyer, and the fee Amazon returns ----
    # A chargeback and an A-to-z guarantee claim take the money back the same
    # way, in the same shape, so they are read as refunds.
    for rf in ((ev.get("RefundEventList") or []) + (ev.get("ChargebackEventList") or [])
               + (ev.get("GuaranteeClaimEventList") or [])):
        d = _day(rf.get("PostedDate"))
        for item in (rf.get("ShipmentItemAdjustmentList") or []):
            sku = item.get("SellerSKU")
            units = abs(int(item.get("QuantityShipped") or 0))
            for ch in (item.get("ItemChargeAdjustmentList") or []):
                _ct = str(ch.get("ChargeType") or "").lower()
                if _ct in _REVENUE_TYPES:
                    acc.add(d, sku, "refunds", abs(_amt(ch.get("ChargeAmount"))),
                            _cur(ch.get("ChargeAmount")), units=units)
                    units = 0          # count the units once, not per charge line
                elif _ct in ("returnshipping", "return shipping", "restockingfee", "restocking fee"):
                    # Postage and restocking on a return go with the refund they
                    # belong to (measured: ReturnShipping -0.01 on nestwell, 30
                    # Sep) -- the same bucket the per-order parser uses.
                    acc.add(d, sku, "refunds", -_amt(ch.get("ChargeAmount")),
                            _cur(ch.get("ChargeAmount")))
                elif _ct in _TAX_TYPES:
                    # VAT handed back with the refund. Tracked apart from the tax
                    # collected so neither is quietly netted into the other -- the
                    # two belong to different VAT returns.
                    acc.add(d, sku, "refund_tax", abs(_amt(ch.get("ChargeAmount"))),
                            _cur(ch.get("ChargeAmount")))
            # THE DISCOUNT YOU FUNDED, REVERSED. Amazon posts it back with the
            # refund (+3.25 on nestwell, 90 days): the buyer got the price LESS
            # the discount back, so the refund is that much smaller. Kept in
            # `refunds` so it stays on the refund's date on both calendars --
            # in `promos` it moved the order's month (review, 30 Sep 2026).
            for pr in (item.get("PromotionAdjustmentList") or []):
                acc.add(d, sku, "refunds", -_amt(pr.get("PromotionAmount")),
                        _cur(pr.get("PromotionAmount")))
            for fee in (item.get("ItemFeeAdjustmentList") or []):
                # SIGNED. Most fee adjustments on a refund are positive -- Amazon
                # giving part of its commission back -- but RefundCommission is
                # NEGATIVE: the fee Amazon KEEPS for processing the refund. abs()
                # counted it as money returned (measured on nestwell, 90 days:
                # Commission +24.39, RefundCommission -4.89 -> stored 29.79, not
                # 20.01; review, 30 Sep 2026).
                acc.add(d, sku, "refund_fees_returned",
                        _amt(fee.get("FeeAmount")), _cur(fee.get("FeeAmount")))

    # ---- service fees: charged against the account, often with no SKU --------
    for sf in (ev.get("ServiceFeeEventList") or []):
        d = _day(sf.get("PostedDate"))
        sku = sf.get("SellerSKU")
        for fee in (sf.get("FeeList") or []):
            ft = fee.get("FeeType")
            bucket = _bucket_fee(ft)
            if bucket == "other_fees" and ft and not _is_known(ft):
                acc.unknown_fees.add(str(ft))
            acc.add(d, sku, bucket, abs(_amt(fee.get("FeeAmount"))),
                    _cur(fee.get("FeeAmount")))

    # ---- adjustments: reimbursements for Amazon's own losses and damage -----
    for adj in (ev.get("AdjustmentEventList") or []):
        d = _day(adj.get("PostedDate"))
        atype = str(adj.get("AdjustmentType") or "").lower()
        if not any(k in atype for k in _REIMBURSEMENT):
            continue
        # SIGNED, as Amazon sends it: a reimbursement is +, a CLAWBACK of one
        # ("compensated_clawback", "ReimbursementClawback") is - money taken
        # back. abs() counted the clawback as money received (review, 30 Sep).
        items = adj.get("AdjustmentItemList") or []
        if items:
            for it in items:
                acc.add(d, it.get("SellerSKU"), "reimbursements",
                        _amt(it.get("TotalAmount")), _cur(it.get("TotalAmount")))
        else:
            acc.add(d, None, "reimbursements", _amt(adj.get("AdjustmentAmount")),
                    _cur(adj.get("AdjustmentAmount")))

    _parse_other_money(ev, acc)

    placed_on = acc.fallback
    if acc.collect is not None:
        placements = undated(acc.collect) or []
        for p in placements:
            acc.add(p["date"], p.get("sku"), p["field"], p["amount"],
                    p.get("currency") or "")
        placed_on = ", ".join(sorted({p["date"] for p in placements})) \
            or "the day each was first seen"

    rows = [r for r in acc.rows.values() if r["date"]]
    tot_u = sum(r["units"] for r in rows if r["asin"] == "*")
    kno_u = sum(r["cogs_units"] for r in rows if r["asin"] == "*")
    notes = {"units": tot_u, "cogs_units": kno_u,
             "cogs_coverage_pct": (round(kno_u / tot_u * 100, 1) if tot_u else None),
             "unknown_fee_types": sorted(acc.unknown_fees),
             # Event lists that carried money and were read by the catch-all.
             "other_event_lists": sorted(getattr(acc, "other_lists", set())),
             "unmapped_skus": sorted(acc.unmapped_skus)[:50],
             "unmapped_sku_count": len(acc.unmapped_skus),
             "unattributed": acc.unattributed,
             "unattributed_note": (
                 "%.2f of charges arrived with no date of their own (Amazon sends "
                 "the monthly subscription fee this way) and were placed on %s. The "
                 "period total is right; that one day is approximate."
                 % (acc.unattributed, placed_on)) if acc.unattributed else ""}
    return rows, notes


# THE REST OF THE ACCOUNT'S MONEY (owner, 30 Sep 2026: "the transactions that
# are performed in the account"). Each list by the shape Amazon documents for
# it; the date field is PostedDate, or postedDate on the Ads invoices (measured,
# 30 Sep 2026: that list is camelCase).
def _money_of(node, *keys):
    for k in keys:
        if isinstance(node.get(k), dict):
            return _amt(node.get(k)), _cur(node.get(k))
    return 0.0, ""


# The total-like field of each other event list, as Amazon's Finances API
# reference names them (the list the review of 30 Sep 2026 found missing:
# SAFE-T reimbursements, tax withheld, value-added services, capacity
# reservation, affordability expenses). Checked in this order; the first one
# present is the event's amount, never a total AND its parts.
_OTHER_AMOUNT_KEYS = ("TotalAmount", "totalAmount", "TransactionValue", "transactionValue",
                      "TransactionAmount", "ReimbursedAmount", "TotalExpense",
                      "AdjustmentAmount", "ChargeAmount", "FeeAmount", "Amount", "amount")
# Always a cost, whatever sign Amazon puts on it.
_COST_KEYS = ("WithheldAmount",)


def _other_event_money(e):
    """One uncatalogued event -> (signed amount, currency): + money to you,
    - a cost. Liquidation pays proceeds less its fee; an event that lists its
    fees (FeeList: imaging services) is their sum."""
    if isinstance(e.get("LiquidationProceedsAmount"), dict):
        p, cur = _money_of(e, "LiquidationProceedsAmount")
        f, _c = _money_of(e, "LiquidationFeeAmount")
        return abs(p) - abs(f), cur
    for k in _COST_KEYS:
        if isinstance(e.get(k), dict):
            v, cur = _money_of(e, k)
            return -abs(v), cur
    v, cur = _money_of(e, *_OTHER_AMOUNT_KEYS)
    if not v and isinstance(e.get("FeeList"), list):
        for f in e["FeeList"]:
            fv, fc = _money_of(f or {}, "FeeAmount")
            v += fv
            cur = cur or fc
    return v, cur


def _parse_other_money(ev, acc):
    acc.other_lists = set()
    # Amazon Ads invoices: Charge is negative, a refund of one positive.
    for e in (ev.get("ProductAdsPaymentEventList") or []):
        d = _day(e.get("postedDate") or e.get("PostedDate"))
        base, cur = _money_of(e, "baseValue", "BaseValue")
        tax, _c = _money_of(e, "taxValue", "TaxValue")
        if not base and not tax:
            base, cur = _money_of(e, "transactionValue", "TransactionValue")
        acc.add(d, None, "ads_charged", -base, cur)
        acc.add(d, None, "ads_charged_tax", -tax, cur)
    # Coupon redemptions and Lightning / Best Deal fees: the price of a promotion.
    for lst in ("CouponPaymentEventList", "SellerDealPaymentEventList"):
        for e in (ev.get(lst) or []):
            d = _day(e.get("PostedDate") or e.get("postedDate"))
            v, cur = _money_of(e, "TotalAmount", "totalAmount")
            if not v:
                # No total: the parts, where Amazon's reference puts them --
                # the fee inside FeeComponent, the charge inside ChargeComponent
                # (a top-level FeeAmount, read before, is never sent).
                fee, cur = _money_of(e.get("FeeComponent") or {}, "FeeAmount")
                ch, _c = _money_of(e.get("ChargeComponent") or {}, "ChargeAmount")
                v = fee + ch
            acc.add(d, None, "promo_fees", -v, cur)
    # Removals / disposals: the fee is an FBA cost; any liquidation revenue is income.
    for e in (ev.get("RemovalShipmentEventList") or []):
        d = _day(e.get("PostedDate"))
        for it in (e.get("RemovalShipmentItemList") or []):
            fee, cur = _money_of(it, "FeeAmount")
            tx, _c = _money_of(it, "TaxAmount")
            rev, _c2 = _money_of(it, "Revenue")
            acc.add(d, it.get("SellerSKU"), "fba_fees", abs(fee) + abs(tx), cur)
            acc.add(d, it.get("SellerSKU"), "adjustments", rev, cur)
    # Tax retrocharges: signed, as Amazon sends them.
    for e in (ev.get("RetrochargeEventList") or []):
        d = _day(e.get("PostedDate"))
        for k in ("BaseTax", "ShippingTax"):
            v, cur = _money_of(e, k)
            acc.add(d, None, "adjustments", v, cur)
    # Adjustments that are not reimbursements (postage labels bought through
    # Amazon, fee corrections, ...): signed, + to you, - a cost.
    for adj in (ev.get("AdjustmentEventList") or []):
        atype = str(adj.get("AdjustmentType") or "").lower()
        if any(k in atype for k in _REIMBURSEMENT):
            continue                                   # read above as reimbursements
        if "reserve" in atype:
            # A RESERVE is money Amazon holds back from a payout and releases
            # later -- cash timing, not income or cost. Counting it made a
            # held balance read as a loss (review, 30 Sep 2026).
            continue
        d = _day(adj.get("PostedDate"))
        v, cur = _money_of(adj, "AdjustmentAmount")
        acc.add(d, None, "adjustments", v, cur)
    # EVERYTHING ELSE that carries money: one amount per event, the first of the
    # total-like fields present (never a total AND its parts), signed.
    handled = set(_READ_EVENTS) | set(_IGNORED_EVENTS)
    for lst, items in (ev or {}).items():
        if lst in handled or not isinstance(items, list):
            continue
        for e in items:
            if not isinstance(e, dict):
                continue
            v, cur = _other_event_money(e)
            if v:
                acc.other_lists.add(lst)
                acc.add(_day(e.get("PostedDate") or e.get("postedDate")), None,
                        "adjustments", v, cur)


# A refunded unit's cost is NOT credited back. The stock left, and whether it
# comes back saleable is not something Amazon tells us here. Not crediting it
# understates profit slightly; crediting it would overstate profit whenever the
# return is damaged, and of the two errors only one gets someone to reorder
# stock that is not selling.
_COLS = ["referral_fees", "fba_fees", "other_fees", "promo_fees",
         "ads_charged", "ads_charged_tax", "adjustments",
         "refunds", "refund_units",
         "refund_fees_returned", "reimbursements", "promos", "principal",
         "tax", "refund_tax",
         "units", "cogs", "cogs_units", "currency", "source"]


def store(config_path, workspace_id, marketplace, rows, source="finances_api"):
    """Upsert. A re-fetched day REPLACES it, as with sales."""
    if not rows:
        return 0
    conn = _db.get_db(config_path)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for r in rows:
        r = dict(r)
        r["source"] = source
        vals = [r.get(c) for c in _COLS]
        conn.execute(
            "INSERT INTO finance_daily (workspace_id, marketplace, date, asin, %s, fetched_at) "
            "VALUES (?,?,?,?,%s,?) "
            "ON CONFLICT(workspace_id, marketplace, date, asin) DO UPDATE SET %s, "
            "fetched_at=excluded.fetched_at"
            % (", ".join(_COLS), ",".join("?" * len(_COLS)),
               ", ".join("%s=excluded.%s" % (c, c) for c in _COLS)),
            [workspace_id, marketplace, r["date"], r.get("asin", "*")] + vals + [now])
        n += 1
    conn.commit()
    return n


# UNDATED CHARGES: COUNTED PER HALF-MONTH, EXACTLY (review, 30 Sep 2026).
#
# Amazon sends the monthly Professional subscription as a ServiceFeeEvent with
# NO PostedDate, no order and no settlement group -- three identical
# {"FeeType": "Subscription", -30.00 GBP} events in a 90-day pull, nothing to
# tell them apart. Each pull put them all on ITS last day, and store() replaces
# only the days a pull returns, so earlier placements survived: a re-sync ending
# one day earlier counted 180.00 for a window holding 90.00.
#
# The settlement group would date each one, but that is two more Amazon
# endpoints. Instead finance_fetch pulls on a FIXED GRID of half-months (1st-15th,
# 16th-end; see finance_fetch.periods): every past half-month is fetched WHOLE,
# and the current one only ever grows. Amazon filters by the posting date it
# does not show us, so a half-month fetched whole returns every undated charge
# posted in it -- an exact count. Each charge is recorded once in finance_undated
# on its half-month's last day (today, for the current one); a later pull of the
# same half-month adds only the ones beyond those already recorded there. No
# window ever cuts a half-month in two, so no count is ever ambiguous: neither
# 180.00 for 90.00, nor a new month's charge hidden behind an old backfill.
#
# Placed ONLY for a half-month fetched completely (finance_fetch decides): a day
# row is replaced whole by store(), and a partial pull must never replace a real
# day's trade with a placement-only row.
#
# NOT USED BY THE SYNC SINCE 30 SEP 2026. The sync now reads Finances
# 2024-06-19 (listTransactions), which DATES the subscription, so there is
# nothing to place; a complete re-read deletes the old placements in its window
# (clear_unreturned). Kept for parse_events(undated=) and for reading rows the
# old list stored.
_UNDATED_LOCK = __import__("threading").Lock()


def _undated_key(field, sku, amount, currency):
    return (str(field or ""), str(sku or "").strip().upper(),
            round(float(amount or 0.0), 2), str(currency or ""))


def place_undated(config_path, workspace_id, marketplace, charges, start, end):
    """Record this half-month's new undated charges; return all its placements.

    [start, end] is ONE half-month (its end clamped to today), fetched whole.
    -> [{date, field, sku, amount, currency}], for parse_events to add back.

    Read-then-insert under a process lock AND an IMMEDIATE transaction, so two
    syncs of one account at once (the refresher and the Finance button) cannot
    both see "none recorded" and both insert the same 30.00 for good.
    """
    seen = {}
    for c in (charges or []):
        k = _undated_key(c.get("field"), c.get("sku"), c.get("amount"), c.get("currency"))
        seen[k] = seen.get(k, 0) + 1
    conn = _db.get_db(config_path)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    with _UNDATED_LOCK:
        if conn.in_transaction:
            conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        try:
            placed = {}
            for r in conn.execute(
                    "SELECT field, sku, amount, currency, placed_on FROM finance_undated "
                    "WHERE workspace_id=? AND marketplace=? AND placed_on>=? "
                    "AND placed_on<=? ORDER BY placed_on, id",
                    (workspace_id, marketplace, str(start), str(end))).fetchall():
                placed.setdefault(_undated_key(r["field"], r["sku"], r["amount"],
                                               r["currency"]), []).append(r["placed_on"])
            for k, n in seen.items():
                for _i in range(n - len(placed.get(k, []))):
                    conn.execute(
                        "INSERT INTO finance_undated (workspace_id, marketplace, field, "
                        "sku, amount, currency, placed_on, first_seen_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (workspace_id, marketplace, k[0], k[1], k[2], k[3], str(end), now))
                    placed.setdefault(k, []).append(str(end))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return [{"date": d, "field": k[0], "sku": k[1] or None, "amount": k[2],
             "currency": k[3]}
            for k, days in placed.items() for d in days]


def stored_placements(config_path, workspace_id, marketplace, start, end):
    """The undated charges ALREADY recorded on start..end, recording nothing.

    For a day read on its own (a half-month too busy to read whole): its row is
    replaced, so the charges placed on it must go back in -- but a day's count
    of undated charges is not the half-month's, so nothing new is recorded.
    """
    return [{"date": r["placed_on"], "field": r["field"], "sku": r["sku"] or None,
             "amount": r["amount"], "currency": r["currency"]}
            for r in _db.get_db(config_path).execute(
                "SELECT field, sku, amount, currency, placed_on FROM finance_undated "
                "WHERE workspace_id=? AND marketplace=? AND placed_on>=? "
                "AND placed_on<=? ORDER BY placed_on, id",
                (workspace_id, marketplace, str(start), str(end))).fetchall()]


def undated_placer(config_path, workspace_id, marketplace, start, end):
    """place_undated bound to one half-month, in the shape parse_events(undated=) takes."""
    return lambda charges: place_undated(config_path, workspace_id, marketplace,
                                         charges, start, end)


def has_rows(config_path, workspace_id, marketplace, start, end):
    """True when finance_daily already holds an account row on start..end."""
    return _db.get_db(config_path).execute(
        "SELECT 1 FROM finance_daily WHERE workspace_id=? AND marketplace=? "
        "AND asin='*' AND date>=? AND date<=? LIMIT 1",
        (workspace_id, marketplace, str(start), str(end))).fetchone() is not None


def clear_unreturned(config_path, workspace_id, marketplace, start, end,
                     kept_days, kept_orders=None, products=True):
    """After start..end was fetched WHOLE: remove what it no longer returns.
    -> the dates whose finance_daily rows were removed.

    A complete read is Amazon's whole answer for those days, and a dated
    transaction is returned by every read that covers its day, so a row missing
    from it holds nothing Amazon still reports. Two kinds were measured:

      * an undated charge (the monthly subscription) an old pull filed on its
        own last day -- the newer Finances list dates it, so its finance_undated
        placement goes too;
      * a held sale or refund the OLD list showed on the day the hold was
        RELEASED. The newer list shows it on the day it happened (finance_
        transactions), so the release-day copy would count it twice
        (026-4940553-7399509: refunded 18 Aug, shown by the old list 26 Aug).

    kept_days: {(date, asin)} this read returned. kept_orders: {(order_id,
    posted_date)} it returned for order_fees, or None to leave order_fees alone
    (its parse failed, so nothing is known about it). products=False leaves
    per-product rows alone (a read with no SKU map could not have written any).

    order_fees is order_finance's table; the delete sits here beside the
    finance_daily one because it is the same rule for the same read.
    """
    conn = _db.get_db(config_path)
    s, e = str(start), str(end)
    kept_days = kept_days or set()
    gone = set()
    for r in conn.execute(
            "SELECT date, asin FROM finance_daily WHERE workspace_id=? AND "
            "marketplace=? AND date>=? AND date<=?",
            (workspace_id, marketplace, s, e)).fetchall():
        if not products and r["asin"] != "*":
            continue
        if (r["date"], r["asin"]) not in kept_days:
            conn.execute("DELETE FROM finance_daily WHERE workspace_id=? AND "
                         "marketplace=? AND date=? AND asin=?",
                         (workspace_id, marketplace, r["date"], r["asin"]))
            gone.add(r["date"])
    conn.execute("DELETE FROM finance_undated WHERE workspace_id=? AND "
                 "marketplace=? AND placed_on>=? AND placed_on<=?",
                 (workspace_id, marketplace, s, e))
    if kept_orders is not None:
        for r in conn.execute(
                "SELECT order_id, posted_date FROM order_fees WHERE workspace_id=? "
                "AND marketplace=? AND posted_date>=? AND posted_date<=?",
                (workspace_id, marketplace, s, e)).fetchall():
            if (r["order_id"], r["posted_date"]) not in kept_orders:
                conn.execute("DELETE FROM order_fees WHERE workspace_id=? AND "
                             "marketplace=? AND order_id=? AND posted_date=?",
                             (workspace_id, marketplace, r["order_id"],
                              r["posted_date"]))
    conn.commit()
    return sorted(gone)


def sku_map(config_path, account_id, marketplace):
    """SKU -> ASIN from the catalogue the app already holds, AND from what sold.

    Read from what is on disk rather than fetched, because this runs inside a
    finance pull and a second Amazon report there would double its cost for
    information the app already has.

    THE SNAPSHOT IS NOT THE SAME THING AS "WHAT THIS ACCOUNT SELLS", and a SKU
    missing from it loses its fees off every per-product figure. asin_for() files
    an unmapped SKU's money against the account total only, which keeps the
    headline right -- deliberately -- but means the product's own row shows the
    sale with none of the fees that came with it. That reads as a product doing
    better than it is, which is the direction that gets more of it ordered.

    Measured 7 Sep 2026, the day the Finances role was granted:
      nestwell_goods  4 of its 16 selling SKUs were not in the snapshot
      selvora_limited 4 of 4 -- including OO-96JX-Z7ND, 52 orders, 1,757.97
    On selvora NOT ONE fee could reach a product row.

    So order_lines is unioned in: a SKU that has SOLD carries the ASIN it sold
    as, and that is already local. THE SNAPSHOT WINS where both know a SKU --
    it is what Amazon says is listed TODAY, while an order line is a record of
    what was true when it shipped, and a relisted SKU can have moved ASIN since.

    Same union, same reason, as domain/cogs.template_rows (Rule 12).
    """
    out = {}
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace) or {}
    except Exception:
        rec = {}
    for it in (rec.get("items") or []):
        sku, asin = str(it.get("sku") or "").strip(), str(it.get("asin") or "").strip()
        if sku and asin:
            out[sku] = asin

    # WHAT HAS ACTUALLY SOLD. Never fatal: losing this half must not lose the
    # snapshot half, which is what every account had before today.
    try:
        from data import db as _dbm
        seen = {str(k).strip().upper() for k in out}
        for r in _dbm.get_db(config_path).execute(
                "SELECT sku, asin, COUNT(*) n FROM order_lines "
                "WHERE workspace_id=? AND IFNULL(sku,'') != '' "
                "AND IFNULL(asin,'') != '' "
                "GROUP BY sku, asin ORDER BY n DESC", (str(account_id or ""),)):
            sku = str(r["sku"] or "").strip()
            asin = str(r["asin"] or "").strip()
            k = sku.upper()
            if not sku or not asin or k in seen:
                continue
            # Ordered by how often the pair was seen, so a SKU that has sold
            # under two ASINs takes the one it sold as MOST, not the one the
            # database happened to return first.
            seen.add(k)
            out[sku] = asin
    except Exception:
        pass
    return out


def undated_lumps(config_path, workspace_id, marketplace, start, end):
    """Fees sitting on a day that had no trade. -> {amount, days, why}.

    WHY A SHORT WINDOW CAN SHOW A CONFIDENT LOSS ON A GOOD ACCOUNT.

        "nestwell goods uk last 30 days, profit showed minus there"

    Amazon sends the monthly Subscription fee as a ServiceFeeEvent with NO
    PostedDate. parse_events keeps it rather than dropping it -- losing it would
    understate fees by thirty pounds a month -- and places it on the day it was
    first seen (place_undated; before 30 Sep 2026, the last day of every pull),
    reporting the amount in `unattributed` so the caller can say so. That note is returned by the SYNC and never stored, so by the
    time a screen draws the day, nothing knows the charge was undated.

    Measured on nestwell_goods/UK: 2026-09-07 carries 30.00 of other_fees with
    zero units, zero principal and zero referral. Over thirty days that is noise
    against 859 of sales. Over the last two days it is the entire figure, and
    the profit card reads -30.00 for an account that traded perfectly well.

    HOW AN UNDATED CHARGE IS RECOGNISED AFTER THE FACT: a day with fees on it
    and no trade at all. Nothing was sold, so a selling fee cannot have been
    incurred that day -- the charge belongs to the period, not to the date it
    was filed under. That test needs no new column and cannot mistake a real
    trading day for one of these.

    The window total is RIGHT either way. This exists so a screen can say which
    part of a short window's loss is a monthly charge that happened to land in
    it, rather than leaving the reader to conclude the advertising lost money.
    """
    out = {"amount": 0.0, "days": [], "why": ""}
    try:
        conn = _db.get_db(config_path)
        rows = conn.execute(
            "SELECT date, "
            "  ROUND(COALESCE(other_fees,0) + COALESCE(referral_fees,0) "
            "        + COALESCE(fba_fees,0), 2) fees "
            "FROM finance_daily "
            "WHERE workspace_id=? AND marketplace=? AND asin='*' "
            "  AND date>=? AND date<=? "
            "  AND COALESCE(units,0) = 0 "
            "  AND COALESCE(principal,0) = 0 "
            "  AND (COALESCE(other_fees,0) + COALESCE(referral_fees,0) "
            "       + COALESCE(fba_fees,0)) > 0 "
            "ORDER BY date",
            (workspace_id, marketplace, str(start), str(end))).fetchall()
    except Exception:
        return out
    for r in rows:
        # This module has no _f helper -- an earlier draft assumed one, and the
        # NameError was swallowed by the caller's try/except, so the figure came
        # back silently absent rather than wrong. Converted inline.
        try:
            fee = float(r["fees"] or 0.0)
        except (TypeError, ValueError):
            fee = 0.0
        out["days"].append({"date": r["date"], "fees": round(fee, 2)})
        out["amount"] = round(out["amount"] + fee, 2)
    if out["amount"]:
        out["why"] = (
            "%.2f of the fees in this window sit on %s, %s that sold nothing at "
            "all: account charges such as the monthly subscription, not the "
            "cost of any sale. The "
            "window's total is right; over a short window it makes the profit "
            "look worse than the trading was."
            % (out["amount"],
               ", ".join(d["date"] for d in out["days"]),
               "a day" if len(out["days"]) == 1 else "days"))
    return out


def series(config_path, workspace_id, marketplace, start, end, asin=None):
    """Finance rows for a range, keyed by date, for joining onto sales."""
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT * FROM finance_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=? ORDER BY date",
        (workspace_id, marketplace, start, end, asin or "*")).fetchall()
    return {r["date"]: dict(r) for r in rows}
