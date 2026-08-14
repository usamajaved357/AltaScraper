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
            "statuses": statuses}
