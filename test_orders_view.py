"""Every account's orders on one screen.

WHAT AMAZON WILL NOT GIVE US, MEASURED RATHER THAN ASSUMED.
Asked for the customer's name, address and phone. Probed the live API on three
accounts, 15 Aug 2026:

    getOrders                        BuyerInfo: {}   -- empty, always
    ShippingAddress                  City, StateOrRegion, PostalCode,
                                     CountryCode -- no name, no street, no phone

    createRestrictedDataToken
      dataElements=[buyerInfo]       GRANTED
      dataElements=[shippingAddress] REFUSED -- "Application does not have
                                     access to one or more requested data
                                     elements: [shippingAddress]"

    and reading an order WITH the granted buyerInfo token STILL returns
    BuyerInfo: {}

So it is not a gap in the app: Amazon strips personal data unless the SP-API
application itself is approved for those roles. The screen shows the region
Amazon does release and says why the rest is missing, rather than leaving a
column blank for someone to wonder about.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from domain import orders_view as OV

# Shaped exactly as the live Orders API returned it.
ORDER = {
    "AmazonOrderId": "204-5479997-1722727",
    "PurchaseDate": "2026-08-14T11:01:13Z",
    "LastUpdateDate": "2026-08-14T11:05:00Z",
    "OrderStatus": "Unshipped",
    "OrderTotal": {"CurrencyCode": "GBP", "Amount": "29.99"},
    "NumberOfItemsShipped": 0,
    "NumberOfItemsUnshipped": 1,
    "FulfillmentChannel": "MFN",
    "SalesChannel": "Amazon.co.uk",
    "IsPrime": False,
    "IsBusinessOrder": False,
    "LatestShipDate": "2026-08-16T22:59:59Z",
    "LatestDeliveryDate": "2026-08-20T22:59:59Z",
    # As Amazon really sends it: redacted.
    "BuyerInfo": {},
    "ShippingAddress": {"City": "AYLESBURY", "PostalCode": "HP22 5SL",
                        "CountryCode": "GB"},
}

print("=== one order becomes one row ===")
r = OV.to_row(ORDER, account_id="nestwell_goods", account_label="Nestwell Goods LTD")
check("the order number", r["order_id"], "204-5479997-1722727")
# The whole point of the screen: not having to know which account it came from.
check("which account it belongs to", r["account"], "Nestwell Goods LTD")
check("status", r["status"], "Unshipped")
check("total", (r["total"], r["currency"]), (29.99, "GBP"))
check("units counts shipped AND unshipped", r["units"], 1)
check("  and says how many are still to go", r["unshipped"], 1)

print("\n=== the destination, named honestly ===")
check("the parts Amazon does release, as one line",
      r["region"], "AYLESBURY, HP22 5SL, GB")
# A column headed "Address" holding only a postcode invites someone to try to
# post something with it.
check("the buyer's name is empty, because Amazon withholds it", r["buyer_name"], "")
check("  and so is the phone", r["buyer_phone"], "")
check("  and the row SAYS it is withheld rather than looking like a blank",
      r["pii_withheld"], True)
truthy("there is one explanation, shared by the screen and the API",
       "does not have access" in OV.PII_NOTE and "Seller Central" in OV.PII_NOTE)

print("\n=== newest first, across accounts ===")
rows = [
    OV.to_row(dict(ORDER, AmazonOrderId="A", PurchaseDate="2026-08-01T00:00:00Z"), "a", "A"),
    OV.to_row(dict(ORDER, AmazonOrderId="C", PurchaseDate="2026-08-14T00:00:00Z"), "c", "C"),
    OV.to_row(dict(ORDER, AmazonOrderId="B", PurchaseDate="2026-08-07T00:00:00Z"), "b", "B"),
]
check("sorted newest first regardless of which account",
      [x["order_id"] for x in OV.sort_rows(rows)], ["C", "B", "A"])

print("\n=== totals never add pounds to dollars ===")
mixed = [
    OV.to_row(dict(ORDER, OrderTotal={"CurrencyCode": "GBP", "Amount": "10.00"}), "a", "A"),
    OV.to_row(dict(ORDER, OrderTotal={"CurrencyCode": "USD", "Amount": "20.00"}), "b", "B"),
]
s = OV.summarise(mixed)
check("two orders", s["orders"], 2)
check("  kept apart by currency", s["revenue_by_currency"], {"GBP": 10.0, "USD": 20.0})
check("  and the statuses counted", s["statuses"], {"Unshipped": 2})

print("\n=== an order line ===")
ITEM = {"ASIN": "B0H7N2Q5GG", "SellerSKU": "AltaboltaVoo Ceiling Fan",
        "Title": "Bayonet Ceiling Fan with Light and Remote",
        "QuantityOrdered": 1, "QuantityShipped": 0,
        "ItemPrice": {"CurrencyCode": "GBP", "Amount": "34.99"},
        "BuyerRequestedCancel": False}
it = OV.to_item(ITEM)
check("asin", it["asin"], "B0H7N2Q5GG")
check("sku", it["sku"], "AltaboltaVoo Ceiling Fan")
check("quantity", it["qty"], 1)
check("price", (it["price"], it["currency"]), (34.99, "GBP"))
# Items are NOT restricted -- this is the part that comes through whole.
truthy("the title is there in full", "Bayonet Ceiling Fan" in it["title"])

print("\n=== a broken account does not empty the screen ===")
import inspect as _i
SRC = _i.getsource(__import__("routes.orders_routes", fromlist=["x"]).register)
# "Nestwell's token expired" and "you have no orders" are different facts and
# only one of them is true; a failure that only removes rows says the wrong one.
truthy("one account failing is reported, not swallowed",
       "errors.append" in SRC and "One account failing" in SRC)
truthy("accounts with no Amazon credentials are skipped, not failed on",
       "seller_id" in SRC)
truthy("every account is asked by default", '"__all__"' in SRC)
truthy("the reply carries the same PII explanation the screen shows",
       "pii_note" in SRC)

print("\n=== and it is gated with the money screens ===")
from auth.guard import required_permission, feature_for
check("listing orders needs no special permission",
      required_permission("/orders/list", "GET"), None)
# Orders are turnover one order at a time; someone who may not see revenue must
# not see it this way either.
check("but it belongs to the sales feature", feature_for("/orders/list"), "sales")

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
