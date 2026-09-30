"""domain/finance_transactions.py -- Amazon's newer Finances list, read into the
shape the rest of the app already understands.

WHY THE NEWER LIST (owner, 30 Sep 2026: "do the newer finance list switch")
The old list (Finances v0, listFinancialEvents) LEAVES OUT money Amazon is still
holding. A new seller's money is held until delivery + 7 days ("DD7"), and while
it is held the old list does not show it at all:

  * a 15.99 refund given on 24 Sep (nestwell_goods, 202-6550607-9979568) was
    missing, so 2 Jul - 29 Sep read 140.62 of refunds where 156.61 went back;
  * 20 sales worth 382.42 on hold were missing too;
  * when a hold ends, the old list shows the money on the RELEASE day -- a
    refund given on 18 Aug was shown on 26 Aug, which breaks the owner's rule
    that a refund sits on the day the money went back (docs/decisions.md).

The newer list (Finances 2024-06-19, listTransactions) returns every
transaction, held ones included, each dated on the day it happened
(`postedDate`) and marked with a `transactionStatus`:

    RELEASED            an ordinary transaction, or the RELEASE of a held one
    DEFERRED            still held -- dated on the day it happened
    DEFERRED_RELEASED   was held, now released -- still dated on the day it
                        happened, and it names its release (RELEASE_TRANSACTION_ID)

A released hold therefore appears TWICE: the original (DEFERRED_RELEASED, on the
day it happened) and its release (RELEASED, carrying DEFERRED_TRANSACTION_ID,
on the day the hold ended). The original is the one counted; the release is
skipped, so nothing is counted twice and nothing moves to the release day.
Measured on nestwell_goods, 125 days: 83 released holds, every release names
its original, no orphans.

WHY IT IS TRANSLATED RATHER THAN PARSED AFRESH
finance_data.parse_events and order_finance.parse_by_order already classify
every charge, fee, refund and invoice, with a year of corrections in them
(RefundCommission signed, the funded discount reversed on a refund, return
postage with its refund, ad-invoice VAT apart, ...). A second parser for the
new shape would be the same rules written twice, and they would drift
(CLAUDE.md Rule 12). So each transaction is written back into the old event
shape -- the fee, charge and promotion NAMES are the same ones the old list
used (measured side by side, 30 Sep 2026) -- and the one parser reads it.

THE SHAPE, as measured on nestwell_goods (UK), 30 Sep 2026
Money is {"currencyAmount", "currencyCode"}. Each ITEM carries a ProductContext
(sku, asin, quantityShipped) and a breakdown tree, e.g. on a sale:
    ProductCharges -> OurPricePrincipal
    AmazonFees     -> Commission -> Base, Tax
    DigitalServicesFee -> DigitalServicesFee -> Base, Tax
    PromoRebates   -> OurPriceDiscount
A fee is the node whose children are only leaves (Base / Tax / Promo), and its
amount is the node's own total -- VAT included, exactly as the old list's
FeeAmount was. The subscription arrives DATED (ServiceFee, "Subscription"), so
the undated-charge workaround the old list needed is not used for these rows.
"""

# Transactions that are not income or cost: payouts to the bank, a debt paid
# off by card, a micro-deposit, a loan, money Amazon sets aside. The old parser
# ignores the same lists (finance_data._IGNORED_EVENTS) for the same reasons.
_IGNORED = ("transfer", "disbursement", "debtrecovery", "debtpayment", "loan",
            "reserve", "paywithamazon")

# Leaves that split a fee into its parts. A node whose children are all leaves
# is ONE fee, counted at its own total.
_FEE_PARTS = ("base", "tax", "promo")


def _money(node):
    """The newer list's money -> the old list's money node."""
    node = node if isinstance(node, dict) else {}
    try:
        v = float(node.get("currencyAmount") or 0.0)
    except (TypeError, ValueError):
        v = 0.0
    return {"CurrencyAmount": v, "CurrencyCode": str(node.get("currencyCode") or "")}


def _amt(node):
    return _money(node)["CurrencyAmount"]


def _key(s):
    return str(s or "").lower().replace("_", "").replace(" ", "").replace("-", "")


def _related(tx, name):
    for r in (tx.get("relatedIdentifiers") or []):
        if str(r.get("relatedIdentifierName") or "").upper() == name:
            return str(r.get("relatedIdentifierValue") or "")
    return ""


def is_release(tx):
    """The RELEASE of a held transaction: its original (DEFERRED_RELEASED, dated
    on the day it happened) is the one counted, so this one never is."""
    return (str(tx.get("transactionStatus") or "").upper() == "RELEASED"
            and bool(_related(tx, "DEFERRED_TRANSACTION_ID")))


def _product(item):
    for c in (item.get("contexts") or []):
        if isinstance(c, dict) and (c.get("sku") or c.get("asin")
                                    or "quantityShipped" in c):
            return c
    return {}


def _kids(node):
    return [k for k in (node.get("breakdowns") or []) if isinstance(k, dict)]


def _fees(node):
    """A breakdown node -> [(fee type, money)] at the level a fee is named."""
    kids = _kids(node)
    if not kids or all(not _kids(k) and _key(k.get("breakdownType")) in _FEE_PARTS
                       for k in kids):
        return [(str(node.get("breakdownType") or ""), node.get("breakdownAmount"))]
    out = []
    for k in kids:
        out += _fees(k)
    return out


def _withheld(name):
    """Tax Amazon WITHHOLDS as marketplace facilitator. The old parser never
    read ItemTaxWithheldList, so these are left out here too."""
    k = _key(name)
    return "withheld" in k or "marketplacefacilitator" in k


def _charge_type(name, parent=""):
    """A sales-side leaf -> the old list's ChargeType, or None when the name is
    not one the old parser counted (the caller keeps it as a named adjustment)."""
    n = _key(name)
    whole = _key(parent) + n
    if "tax" in n:
        if "shipping" in whole:
            return "ShippingTax"
        if "giftwrap" in whole:
            return "GiftWrapTax"
        return "Tax"
    if "returnshipping" in whole:
        return "ReturnShipping"
    if "restocking" in whole:
        return "RestockingFee"
    if "shipping" in whole:
        return "ShippingCharge"
    if "giftwrap" in whole:
        return "GiftWrap"
    if "principal" in n or n == "productcharges":
        return "Principal"
    return None


def _charges(node, parent="", info=None):
    """A sales-side node -> [(ChargeType or None, name, money)], one per leaf.
    Tax that Amazon WITHHELD is left out (counted in info), as the old parser
    left out ItemTaxWithheldList."""
    kids = _kids(node)
    name = str(node.get("breakdownType") or "")
    if _withheld(name):
        if info is not None:
            info["withheld_ignored"] = info.get("withheld_ignored", 0) + 1
        return []
    if not kids:
        # "Base" / "Tax" under a named charge: the charge's own name decides.
        label = name if _key(name) not in ("base",) else parent
        return [(_charge_type(label, parent), label, node.get("breakdownAmount"))]
    out = []
    for k in kids:
        out += _charges(k, name, info)
    return out


def _is_promo(cat):
    return "promo" in _key(cat)


def _is_charge(cat):
    c = _key(cat)
    return (c in ("productcharges", "other", "charges") or "shipping" in c
            or "giftwrap" in c or "tax" in c or c.endswith("charges"))


def _item_lines(item, refund=False, unknown=None, info=None):
    """One item -> the old ShipmentItem / ShipmentItemAdjustment shape.

    A charge whose name the old parser did not count is NOT made principal: it
    is appended to `unknown` as (name, money) and kept, signed, as a named
    adjustment (to_events) -- the same way an unknown transaction type is."""
    ctx = _product(item)
    charges, fees, promos = [], [], []
    for cat in _kids(item):
        name = str(cat.get("breakdownType") or "")
        if _withheld(name):
            if info is not None:
                info["withheld_ignored"] = info.get("withheld_ignored", 0) + 1
            continue
        if _is_promo(name):
            promos.append({"PromotionAmount": _money(cat.get("breakdownAmount"))})
        elif _is_charge(name):
            for t, label, m in _charges(cat, info=info):
                if t is None:
                    if unknown is not None and _amt(m):
                        unknown.append((label or name, m))
                    continue
                charges.append({"ChargeType": t, "ChargeAmount": _money(m)})
        else:
            fees += [{"FeeType": t, "FeeAmount": _money(m)} for t, m in _fees(cat)]
    line = {"SellerSKU": ctx.get("sku"), "ASIN": ctx.get("asin"),
            "QuantityShipped": ctx.get("quantityShipped") or 0}
    if refund:
        line.update({"ItemChargeAdjustmentList": charges,
                     "ItemFeeAdjustmentList": fees,
                     "PromotionAdjustmentList": promos})
    else:
        line.update({"ItemChargeList": charges, "ItemFeeList": fees,
                     "PromotionList": promos})
    return line


def _head(tx):
    return {"AmazonOrderId": _related(tx, "ORDER_ID"),
            "PostedDate": tx.get("postedDate"),
            "MarketplaceName": (tx.get("marketplaceDetails") or {}).get("marketplaceName"),
            "TransactionId": tx.get("transactionId"),
            "TransactionStatus": tx.get("transactionStatus")}


def _service_fee(tx):
    fees = []
    sku = None
    for it in (tx.get("items") or []):
        sku = sku or _product(it).get("sku")
        for cat in _kids(it):
            fees += [{"FeeType": t, "FeeAmount": _money(m)} for t, m in _fees(cat)]
    if not fees:
        # No items: the transaction's own expense breakdown, or its total.
        for top in _kids(tx):
            if _key(top.get("breakdownType")) == "expenses":
                for cat in _kids(top):
                    fees += [{"FeeType": t, "FeeAmount": _money(m)} for t, m in _fees(cat)]
        if not fees and _amt(tx.get("totalAmount")):
            fees = [{"FeeType": tx.get("description") or "ServiceFee",
                     "FeeAmount": _money(tx.get("totalAmount"))}]
    return {"PostedDate": tx.get("postedDate"), "SellerSKU": sku,
            "FeeDescription": tx.get("description"), "FeeList": fees,
            "TransactionId": tx.get("transactionId")}


def _ads_payment(tx):
    base = tax = 0.0
    cur = _money(tx.get("totalAmount"))["CurrencyCode"]
    for it in (tx.get("items") or []):
        for leaf in _kids(it):
            k = _key(leaf.get("breakdownType"))
            if k == "base":
                base += _amt(leaf.get("breakdownAmount"))
            elif k == "tax":
                tax += _amt(leaf.get("breakdownAmount"))
    e = {"postedDate": tx.get("postedDate"), "transactionType": tx.get("description"),
         "transactionValue": _money(tx.get("totalAmount")),
         "TransactionId": tx.get("transactionId")}
    if base or tax:
        e["baseValue"] = {"CurrencyAmount": round(base, 2), "CurrencyCode": cur}
        e["taxValue"] = {"CurrencyAmount": round(tax, 2), "CurrencyCode": cur}
    return e


def _names(tx):
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(str(n.get("breakdownType") or ""))
            walk(_kids(n))
    walk(_kids(tx))
    for it in (tx.get("items") or []):
        walk(_kids(it))
    return out


def _adjustment(tx):
    """Kept in the old shape so the old rules decide it: a reimbursement is
    found by its type's words, a reserve is skipped, the rest is signed."""
    words = [str(tx.get("description") or "")] + _names(tx)
    atype = " ".join(w for w in words if w)
    atype = atype + " " + atype.replace(" ", "_")
    items = []
    for it in (tx.get("items") or []):
        sku = _product(it).get("sku")
        if sku:
            items.append({"SellerSKU": sku, "TotalAmount": _money(it.get("totalAmount"))})
    if items and abs(sum(i["TotalAmount"]["CurrencyAmount"] for i in items)
                     - _amt(tx.get("totalAmount"))) >= 0.005:
        items = []                  # the parts do not add up: use the total
    return {"PostedDate": tx.get("postedDate"), "AdjustmentType": atype,
            "AdjustmentAmount": _money(tx.get("totalAmount")),
            "AdjustmentItemList": items, "TransactionId": tx.get("transactionId")}


def _removal(tx):
    items = []
    for it in (tx.get("items") or []):
        v = _money(it.get("totalAmount"))
        row = {"SellerSKU": _product(it).get("sku")}
        if v["CurrencyAmount"] < 0:
            row["FeeAmount"] = v
        else:
            row["Revenue"] = v
        items.append(row)
    if not items:
        v = _money(tx.get("totalAmount"))
        items = [{"FeeAmount": v} if v["CurrencyAmount"] < 0 else {"Revenue": v}]
    return {"PostedDate": tx.get("postedDate"), "RemovalShipmentItemList": items,
            "TransactionId": tx.get("transactionId")}


def _list_for(ttype):
    """transactionType -> (old event list, builder) or None to ignore it."""
    t = _key(ttype)
    if any(k in t for k in _IGNORED):
        return None
    if t == "shipment":
        return "ShipmentEventList", "shipment"
    if "chargeback" in t:
        return "ChargebackEventList", "refund"
    if "guarantee" in t or "atoz" in t:
        return "GuaranteeClaimEventList", "refund"
    if "refund" in t:
        return "RefundEventList", "refund"
    if "productads" in t:
        return "ProductAdsPaymentEventList", "ads"
    if "servicefee" in t:
        return "ServiceFeeEventList", "service"
    if "coupon" in t:
        return "CouponPaymentEventList", "total"
    if "deal" in t:
        return "SellerDealPaymentEventList", "total"
    if "removal" in t:
        return "RemovalShipmentEventList", "removal"
    if "adjustment" in t or "reimbursement" in t:
        return "AdjustmentEventList", "adjustment"
    # Anything else that carries money is still counted -- signed, in
    # `adjustments`, and NAMED in the sync's notes (other_event_lists), so a
    # transaction type Amazon starts sending tomorrow reaches the profit.
    return "Transaction:%s" % (ttype or "unknown"), "total"


def to_events(transactions):
    """[transaction] -> ({"FinancialEvents": {list: [event]}}, info).

    info: {"skipped_releases", "ignored", "duplicates", "deferred"} -- counts,
    for the sync's notes. A transaction id seen twice (overlapping pages) is
    counted once."""
    ev, seen = {}, set()
    info = {"skipped_releases": 0, "ignored": 0, "duplicates": 0, "deferred": 0,
            "transactions": 0, "withheld_ignored": 0}
    for tx in (transactions or []):
        if not isinstance(tx, dict):
            continue
        info["transactions"] += 1
        tid = tx.get("transactionId")
        if tid:
            if tid in seen:
                info["duplicates"] += 1
                continue
            seen.add(tid)
        if is_release(tx):
            info["skipped_releases"] += 1
            continue
        where = _list_for(tx.get("transactionType"))
        if where is None:
            info["ignored"] += 1
            continue
        if str(tx.get("transactionStatus") or "").upper() == "DEFERRED":
            info["deferred"] += 1
        lst, kind = where
        if kind in ("shipment", "refund"):
            e = _head(tx)
            unknown = []
            lines = [_item_lines(it, refund=(kind == "refund"), unknown=unknown, info=info)
                     for it in (tx.get("items") or [])]
            e["ShipmentItemAdjustmentList" if kind == "refund" else "ShipmentItemList"] = lines
            for label, mny in unknown:
                ev.setdefault("Charge:%s" % label, []).append(
                    {"PostedDate": tx.get("postedDate"), "TotalAmount": _money(mny),
                     "TransactionId": tid})
        elif kind == "service":
            e = _service_fee(tx)
        elif kind == "ads":
            e = _ads_payment(tx)
        elif kind == "adjustment":
            e = _adjustment(tx)
        elif kind == "removal":
            e = _removal(tx)
        else:
            e = {"PostedDate": tx.get("postedDate"),
                 "TotalAmount": _money(tx.get("totalAmount")),
                 "TransactionId": tid}
        ev.setdefault(lst, []).append(e)
    return {"FinancialEvents": ev}, info
