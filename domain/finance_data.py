"""domain/finance_data.py -- what Amazon charged, and what went back to buyers.

WHERE IT COMES FROM
The Finances API (listFinancialEvents). This is a different question from the
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
                   "FailedAdhocDisbursementEventList", "LoanServicingEventList")


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
    return "other_fees"


def _is_known(fee_type):
    t = str(fee_type or "").lower().replace("_", "").replace("-", "")
    return any(k in t for k in _KNOWN_OTHER)


# Everything Amazon calls tax on an item line. Shipping tax and gift-wrap tax are
# VAT just the same -- collected from the buyer and owed onward -- so leaving them
# out would understate what is owed and overstate what was kept.
_TAX_TYPES = {"tax", "shippingtax", "giftwraptax", "shipping tax", "giftwrap tax"}


def _blank(date, asin):
    return {"date": date, "asin": asin, "currency": "",
            "referral_fees": 0.0, "fba_fees": 0.0, "other_fees": 0.0,
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

    def count(self, date, sku, units, cost_lookup=None):
        """Units shipped, and what they cost -- on the SAME day basis as the fees.

        Priced HERE, at the line, because this is the only point at which the SKU
        is still in hand. One step later there is only an ASIN, and the SKUs that
        could not be mapped to one would lose their cost entirely -- which would
        understate cost of goods and overstate profit, in that direction, always.
        """
        if not date or not units:
            return
        cost, _src = (cost_lookup(sku) if cost_lookup else (None, ""))
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


def parse_events(payload, sku_to_asin=None, fallback_date=None, cost_lookup=None):
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
    """
    ev = ((payload or {}).get("FinancialEvents")
          if isinstance(payload, dict) else None) or {}
    acc = _Acc(sku_to_asin)
    acc.fallback = str(fallback_date or "")[:10]

    # ---- shipments: the sale itself, its fees and any promo you funded -------
    for sh in (ev.get("ShipmentEventList") or []):
        d = _day(sh.get("PostedDate"))
        for item in (sh.get("ShipmentItemList") or []):
            sku = item.get("SellerSKU")
            acc.count(d, sku, item.get("QuantityShipped") or 0, cost_lookup)
            for ch in (item.get("ItemChargeList") or []):
                _ct = str(ch.get("ChargeType") or "").lower()
                if _ct == "principal":
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
    for rf in (ev.get("RefundEventList") or []):
        d = _day(rf.get("PostedDate"))
        for item in (rf.get("ShipmentItemAdjustmentList") or []):
            sku = item.get("SellerSKU")
            units = abs(int(item.get("QuantityShipped") or 0))
            for ch in (item.get("ItemChargeAdjustmentList") or []):
                _ct = str(ch.get("ChargeType") or "").lower()
                if _ct == "principal":
                    acc.add(d, sku, "refunds", abs(_amt(ch.get("ChargeAmount"))),
                            _cur(ch.get("ChargeAmount")), units=units)
                    units = 0          # count the units once, not per charge line
                elif _ct in _TAX_TYPES:
                    # VAT handed back with the refund. Tracked apart from the tax
                    # collected so neither is quietly netted into the other -- the
                    # two belong to different VAT returns.
                    acc.add(d, sku, "refund_tax", abs(_amt(ch.get("ChargeAmount"))),
                            _cur(ch.get("ChargeAmount")))
            for fee in (item.get("ItemFeeAdjustmentList") or []):
                # On a refund the fee adjustment is POSITIVE -- Amazon giving
                # part of its commission back. Kept separate from fees charged so
                # neither figure is quietly netted into the other.
                acc.add(d, sku, "refund_fees_returned",
                        abs(_amt(fee.get("FeeAmount"))), _cur(fee.get("FeeAmount")))

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
        items = adj.get("AdjustmentItemList") or []
        if items:
            for it in items:
                acc.add(d, it.get("SellerSKU"), "reimbursements",
                        abs(_amt(it.get("TotalAmount"))), _cur(it.get("TotalAmount")))
        else:
            acc.add(d, None, "reimbursements", abs(_amt(adj.get("AdjustmentAmount"))),
                    _cur(adj.get("AdjustmentAmount")))

    rows = [r for r in acc.rows.values() if r["date"]]
    tot_u = sum(r["units"] for r in rows if r["asin"] == "*")
    kno_u = sum(r["cogs_units"] for r in rows if r["asin"] == "*")
    notes = {"units": tot_u, "cogs_units": kno_u,
             "cogs_coverage_pct": (round(kno_u / tot_u * 100, 1) if tot_u else None),
             "unknown_fee_types": sorted(acc.unknown_fees),
             "unmapped_skus": sorted(acc.unmapped_skus)[:50],
             "unmapped_sku_count": len(acc.unmapped_skus),
             "unattributed": acc.unattributed,
             "unattributed_note": (
                 "%.2f of charges arrived with no date of their own (Amazon sends "
                 "the monthly subscription fee this way) and were placed on %s. The "
                 "period total is right; that one day is approximate."
                 % (acc.unattributed, acc.fallback)) if acc.unattributed else ""}
    return rows, notes


# A refunded unit's cost is NOT credited back. The stock left, and whether it
# comes back saleable is not something Amazon tells us here. Not crediting it
# understates profit slightly; crediting it would overstate profit whenever the
# return is damaged, and of the two errors only one gets someone to reorder
# stock that is not selling.
_COLS = ["referral_fees", "fba_fees", "other_fees", "refunds", "refund_units",
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


def sku_map(config_path, account_id, marketplace):
    """SKU -> ASIN from the catalogue the app already holds.

    Read from the live snapshot rather than fetched, because this runs inside a
    finance pull and a second Amazon report there would double its cost for
    information that is already on disk.
    """
    try:
        from domain import live_snapshots as _ls
        rec = _ls.get(config_path, account_id, marketplace) or {}
    except Exception:
        return {}
    out = {}
    for it in (rec.get("items") or []):
        sku, asin = str(it.get("sku") or "").strip(), str(it.get("asin") or "").strip()
        if sku and asin:
            out[sku] = asin
    return out


def series(config_path, workspace_id, marketplace, start, end, asin=None):
    """Finance rows for a range, keyed by date, for joining onto sales."""
    conn = _db.get_db(config_path)
    rows = conn.execute(
        "SELECT * FROM finance_daily WHERE workspace_id=? AND marketplace=? "
        "AND date>=? AND date<=? AND asin=? ORDER BY date",
        (workspace_id, marketplace, start, end, asin or "*")).fetchall()
    return {r["date"]: dict(r) for r in rows}
