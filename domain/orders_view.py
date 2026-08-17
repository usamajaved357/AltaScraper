"""domain/orders_view.py -- every account's orders on one screen.

WHY THIS EXISTS
Seeing what sold meant opening each Amazon account in turn. This puts them in
one list, newest first, with the account each belongs to.

WHAT AMAZON WILL AND WILL NOT GIVE US -- MEASURED, NOT ASSUMED
The customer's NAME, STREET ADDRESS and PHONE NUMBER are not available to this
application. Measured against the live API on 15 Aug 2026, on three accounts:

    getOrders                       BuyerInfo: {}   (empty, always)
    ShippingAddress                 City, StateOrRegion, PostalCode, CountryCode
                                    -- no name, no street, no phone

    createRestrictedDataToken
      dataElements=[buyerInfo]      GRANTED
      dataElements=[shippingAddress] REFUSED:
        "Application does not have access to one or more requested data
         elements: [shippingAddress]"

    and reading an order WITH the granted buyerInfo token still returns
    BuyerInfo: {}

So this is not a gap in the app. Amazon strips personal data from Orders unless
the SP-API application itself is approved for the PII roles, and this one is
approved for neither in practice. The screen therefore shows the partial address
Amazon does give -- town, county, postcode, country, which is enough to tell
orders apart and to spot a delivery region -- and says why the rest is missing
rather than leaving a column mysteriously blank.

Order ITEMS are not restricted and come through in full: ASIN, SKU, title,
quantity and price.
"""

# What a redacted address still tells you. Enough to distinguish orders and to
# see where they are going; not enough to address a parcel.
ADDRESS_FIELDS = ("City", "StateOrRegion", "PostalCode", "CountryCode")

# Said once, here, so the screen and the API reply cannot describe it differently.
PII_NOTE = (
    "Amazon does not release the customer's name, street address or phone "
    "number to this app. Its SP-API application is not approved for those data "
    "elements — asking for them is refused outright ('Application does not have "
    "access to one or more requested data elements: [shippingAddress]'), and "
    "even the buyer-info token that IS granted returns an empty record. To get "
    "them you would have to apply for the PII roles for the application in "
    "Seller Central under Develop Apps, and be approved by Amazon. Everything "
    "below is what Amazon does release."
)


def _money(node):
    try:
        return round(float((node or {}).get("Amount")), 2)
    except (TypeError, ValueError):
        return None


def address_line(addr):
    """The address as one readable line, from the parts Amazon leaves in."""
    a = addr or {}
    bits = [str(a.get(k) or "").strip() for k in
            ("City", "StateOrRegion", "PostalCode", "CountryCode")]
    return ", ".join(b for b in bits if b)


def to_row(order, account_id="", account_label=""):
    """One Amazon order -> the row the list draws.

    Carries the account, because the whole point is not having to know which
    account an order came from before you can look at it.
    """
    o = order or {}
    addr = o.get("ShippingAddress") or {}
    total = o.get("OrderTotal") or {}
    return {
        "order_id": str(o.get("AmazonOrderId") or ""),
        "account_id": account_id,
        "account": account_label or account_id,
        "purchased": str(o.get("PurchaseDate") or ""),
        "updated": str(o.get("LastUpdateDate") or ""),
        "status": str(o.get("OrderStatus") or ""),
        "total": _money(total),
        "currency": str(total.get("CurrencyCode") or ""),
        "units": int(o.get("NumberOfItemsShipped") or 0)
                 + int(o.get("NumberOfItemsUnshipped") or 0),
        "shipped": int(o.get("NumberOfItemsShipped") or 0),
        "unshipped": int(o.get("NumberOfItemsUnshipped") or 0),
        "fulfilment": str(o.get("FulfillmentChannel") or ""),
        "channel": str(o.get("SalesChannel") or ""),
        "prime": bool(o.get("IsPrime")),
        "business": bool(o.get("IsBusinessOrder")),
        "ship_by": str(o.get("LatestShipDate") or ""),
        "deliver_by": str(o.get("LatestDeliveryDate") or ""),
        # WHAT AMAZON RELEASES OF THE DESTINATION. Named honestly: it is a
        # region, not an address, and a column headed "Address" holding only a
        # postcode invites someone to try to post something with it.
        "region": address_line(addr),
        "city": str(addr.get("City") or ""),
        "postcode": str(addr.get("PostalCode") or ""),
        "country": str(addr.get("CountryCode") or ""),
        # Present so the shape never changes, always empty, always explained.
        "buyer_name": "",
        "buyer_phone": "",
        "pii_withheld": True,
    }


def to_item(item):
    """One line of an order. Not restricted -- this comes through in full."""
    it = item or {}
    price = it.get("ItemPrice") or {}
    return {
        "asin": str(it.get("ASIN") or ""),
        "sku": str(it.get("SellerSKU") or ""),
        "title": str(it.get("Title") or ""),
        "qty": int(it.get("QuantityOrdered") or 0),
        "qty_shipped": int(it.get("QuantityShipped") or 0),
        "price": _money(price),
        "currency": str(price.get("CurrencyCode") or ""),
        "tax": _money(it.get("ItemTax")),
        "promo": _money(it.get("PromotionDiscount")),
        "gift": bool(it.get("IsGift")),
        "cancel_requested": bool(it.get("BuyerRequestedCancel")),
    }


# ---- what an order actually earned -----------------------------------------
#
# The order total is what the buyer paid, which is not what you keep. Three
# things come out of it and each is a different kind of certainty:
#
#   Amazon's referral fee   a PERCENTAGE, known only approximately here. The
#                           exact figure arrives later in the finance records,
#                           per shipment. This is an estimate and is labelled as
#                           one.
#   the stock               from domain/cogs.py -- the SKU carries it, or you
#                           typed it. NOT KNOWN for hand-made SKUs, and unknown
#                           is not zero.
#   VAT                     already excluded: Amazon reports the order total
#                           ex-VAT on these accounts (measured: Tax arrives as
#                           its own charge, 20% on top of Principal).
#
# THE RULE THAT KEEPS THIS HONEST: if the cost of any line is unknown, the
# order's profit is NOT shown. A partial cost only ever makes an order look
# better than it was, and the one order whose cost is missing is exactly the one
# somebody would use to justify buying more.
DEFAULT_REFERRAL_RATE = 0.15


def profit_for(items, order_total, cost_of, referral_rate=None):
    """(profit, margin_pct, note) for one order, or (None, None, why).

    `cost_of` is a function sku -> (cost_or_None, source), which is
    domain/cogs.lookup -- so the SKU costs, the manual overrides and their
    precedence are decided in exactly one place (Rule 12).

    THE COUPON IS ALREADY OUT, AND MUST NOT BE TAKEN OUT AGAIN.

    Asked as: "the profit should be calculated after cutting the promotional
    charges, the coupon or some discount applied on that order if that is not
    already done ... please check the authenticity of this claim first and then
    apply if i am correct dont guess or assume".

    Checked on SEVEN real discounted orders across two accounts, not one:

        jack_uk        026-1374880-3466755   21.80 - 0.91 = 20.89 = OrderTotal
        nestwell_goods 206-9874023-3627501   29.99 - 1.50 = 28.49 = OrderTotal
                       202-2446893-7679542   29.99 - 1.50 = 28.49 = OrderTotal
                       202-3734845-7261964   29.99 - 1.50 = 28.49 = OrderTotal
                       203-9865692-8949959   29.99 - 1.50 = 28.49 = OrderTotal
                       202-4024015-1547522   34.99 - 1.75 = 33.24 = OrderTotal
                       203-9384660-6187507   34.99 - 1.75 = 33.24 = OrderTotal

    Nestwell runs a 5% coupon on the AltaboltaVoo Ceiling Fan -- which is how
    this was confirmed at a second price point after the fan went 29.99 -> 34.99.
    Every one agrees to the penny.

    So Amazon's OrderTotal is what the buyer was CHARGED, with the coupon
    already deducted. This function starts from OrderTotal, so the discount is
    accounted for; subtracting it a second time would charge the coupon twice
    and understate every discounted order.

    WHICH IS THE OPPOSITE OF THE FINANCE PATH, and both are right. The Finances
    API reports ItemChargeList Principal and PromotionList as SEPARATE entries,
    so there the revenue IS gross and the promotion has to come off -- which is
    what domain/order_profit.py does. Two feeds, two shapes. The rule is not
    "always subtract the coupon", it is "know what your revenue figure already
    includes". test_orders_promo.py pins both halves.
    """
    if order_total is None:
        return None, None, "Amazon has not released this order's total yet"
    rate = DEFAULT_REFERRAL_RATE if referral_rate is None else float(referral_rate)

    cogs, unknown = 0.0, []
    for it in items or []:
        sku = str((it or {}).get("sku") or "")
        qty = int((it or {}).get("qty") or 0) or 1
        cost, _src = cost_of(sku) if cost_of else (None, "")
        if cost is None:
            unknown.append(sku or "(no sku)")
        else:
            cogs += float(cost) * qty
    if unknown:
        return None, None, ("no cost recorded for %s, so this order's profit "
                            "cannot be worked out" % ", ".join(unknown[:3]))

    fees = round(float(order_total) * rate, 2)
    profit = round(float(order_total) - fees - cogs, 2)
    margin = (round(profit / float(order_total) * 100, 1)
              if float(order_total) else None)
    return profit, margin, ("estimated: Amazon's exact fee for this order "
                            "arrives with the finance records")


def profit_detail(items, order_total, cost_of, referral_rate=None):
    """Everything an order row needs about what it made, in one call.

    {profit, margin_pct, roi_pct, cogs, fees, note}

    MARGIN AND ROI ARE DIFFERENT QUESTIONS and the screen shows both, so both
    are worked out here rather than one of them being derived in the browser
    from rounded figures. Margin is profit over what the buyer paid -- is this
    price any good. ROI is profit over what the stock cost -- was this worth
    buying. A 3.00 profit on a 30.00 order is a thin 10% margin and a healthy
    43% return on 7.00 of stock, and those two facts lead to different actions.

    Wraps profit_for so the honesty rule stays in ONE place: if any line's cost
    is unknown, nothing is shown at all.
    """
    profit, margin, note = profit_for(items, order_total, cost_of, referral_rate)
    out = {"profit": profit, "margin_pct": margin, "roi_pct": None,
           "cogs": None, "fees": None, "note": note}
    if profit is None:
        return out
    rate = DEFAULT_REFERRAL_RATE if referral_rate is None else float(referral_rate)
    cogs = 0.0
    for it in items or []:
        cost, _src = cost_of(str((it or {}).get("sku") or "")) if cost_of else (None, "")
        if cost is None:
            return out                      # cannot happen: profit_for refused
        cogs += float(cost) * (int((it or {}).get("qty") or 0) or 1)
    out["cogs"] = round(cogs, 2)
    out["fees"] = round(float(order_total) * rate, 2)
    # Return on the cash. Undefined when the stock cost nothing recorded --
    # dividing by zero would report an infinite return on a free product.
    out["roi_pct"] = round(profit / cogs * 100, 1) if cogs else None
    return out


def item_summary(items):
    """The one line a row shows about WHAT was bought.

    An order can hold several products. The row names the first and says how
    many others there are, rather than listing them all -- the detail panel is
    where the full list belongs, and a row that grows with the order is what
    made this screen cluttered in the first place.
    """
    its = [i for i in (items or []) if i]
    if not its:
        return {"title": "", "sku": "", "asin": "", "extra": 0, "lines": 0}
    first = its[0]
    return {"title": str(first.get("title") or ""),
            "sku": str(first.get("sku") or ""),
            "asin": str(first.get("asin") or ""),
            "extra": max(0, len(its) - 1),
            "lines": len(its)}


def sort_rows(rows):
    """Newest first, across every account.

    Sorted on the ISO purchase date as a STRING on purpose: Amazon returns
    RFC3339 in UTC, which sorts correctly as text, and parsing dates only to
    re-sort them adds a way to fail on a malformed one.
    """
    return sorted(rows or [], key=lambda r: str(r.get("purchased") or ""),
                  reverse=True)


def summarise(rows):
    """Totals for what is on screen. Per currency, never added together."""
    by_cur, statuses = {}, {}
    units = 0
    for r in rows or []:
        cur = r.get("currency") or "?"
        if r.get("total") is not None:
            by_cur[cur] = round(by_cur.get(cur, 0.0) + float(r["total"]), 2)
        units += int(r.get("units") or 0)
        s = r.get("status") or "?"
        statuses[s] = statuses.get(s, 0) + 1
    return {"orders": len(rows or []), "units": units,
            # Kept apart: adding pounds to dollars produces a number that is
            # wrong in both currencies.
            "revenue_by_currency": by_cur,
            # WHICH FIGURE THIS IS. Summed from each order's OrderTotal, so it is
            # what the BUYERS PAID -- shipping included. The Sales screen's Total
            # Sales is ordered PRODUCT sales (the item price), which is what
            # Amazon's own Total Sales shows and what a seller counts. On three
            # orders of one item those two read 102.21 and 89.97: both correct,
            # about different things. Declared here and labelled on screen so the
            # two screens cannot look like they contradict each other. See
            # domain/orders_live.product_sales().
            "revenue_basis": "order_total",
            "statuses": statuses}
