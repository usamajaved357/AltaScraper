"""A sale is the product price. One definition, everywhere.

THE REPORT: "i received the sales of 89.97 and that is only yesterday" while the
app showed 102.21.

Both figures were right about different things. Amazon sends two:

    ItemPrice    29.99 x 3 = 89.97   the goods -- "ordered product sales"
    OrderTotal   34.07 x 3 = 102.21  what the buyer paid, shipping included

Confirmed against the live API with probe_ordertotal.py. Seller Central's Total
Sales, and the Sales & Traffic report's ordered_sales column, are both the FIRST
one -- so that is what the app must mean by a sale.

This is not only a labelling matter. The Sales chart fills days the report has
not delivered from the Orders API; with OrderTotal in those days and ItemPrice in
the reported ones, two bars side by side were measuring different things.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

import domain.orders_live as ol
import domain.orders_view as ov

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


# The three real orders, exactly as Amazon returned them.
ORDERS = [
    {"AmazonOrderId": "03-9146006-2288343", "OrderStatus": "Unshipped",
     "PurchaseDate": "2026-08-14T18:04:11Z", "NumberOfItemsUnshipped": 1,
     "OrderTotal": {"Amount": "34.07", "CurrencyCode": "GBP"}},
    {"AmazonOrderId": "05-6472614-6875507", "OrderStatus": "Unshipped",
     "PurchaseDate": "2026-08-14T19:22:03Z", "NumberOfItemsUnshipped": 1,
     "OrderTotal": {"Amount": "34.07", "CurrencyCode": "GBP"}},
    {"AmazonOrderId": "03-4273159-9993160", "OrderStatus": "Unshipped",
     "PurchaseDate": "2026-08-14T21:40:55Z", "NumberOfItemsUnshipped": 1,
     "OrderTotal": {"Amount": "34.07", "CurrencyCode": "GBP"}},
    # A cancelled order is not a sale, whichever figure is used.
    {"AmazonOrderId": "03-0000000-0000000", "OrderStatus": "Canceled",
     "PurchaseDate": "2026-08-14T09:00:00Z", "NumberOfItemsUnshipped": 1,
     "OrderTotal": {"Amount": "34.07", "CurrencyCode": "GBP"}},
]
PRICED = {o["AmazonOrderId"]: (29.99, "GBP") for o in ORDERS[:3]}

print("\n== the figure the owner counted is the one reported ==")
s = ol.summarise(ORDERS, PRICED)
check("revenue is 3 x 29.99, the goods", s["revenue"], 89.97)
check("not 3 x 34.07, which adds shipping", s["revenue"] == 102.21, False)
check("the cancelled order is not a sale", s["orders"], 3)
check("and is counted as cancelled", s["cancelled"], 1)
check("the basis is declared, not assumed", s["basis"], "product_sales")

print("\n== without prices it still answers, and says which figure it gave ==")
s0 = ol.summarise(ORDERS)
check("falls back to what was charged", s0["revenue"], 102.21)
check("and SAYS it fell back", s0["basis"], "order_total")
check_true("so the two can never be confused for each other",
           s["basis"] != s0["basis"])

print("\n== one order Amazon would not price does not vanish ==")
partial = dict(PRICED)
partial.pop("03-4273159-9993160")
sp = ol.summarise(ORDERS, partial)
check("two priced + one charged, nothing lost", sp["revenue"], round(29.99 * 2 + 34.07, 2))
check_true("which is nearer the truth than dropping the order",
           sp["revenue"] > 59.98)

print("\n== the Orders screen declares its own, different, basis ==")
rows = [ov.to_row(o, account_id="jack_uk") for o in ORDERS]
os_ = ov.summarise(rows)
check("the Orders screen still totals what buyers paid",
      os_["revenue_by_currency"].get("GBP"), 136.28)
check("but now says so", os_["revenue_basis"], "order_total")
check_true("and the screen prints that beside the figure",
           "charged, incl. shipping" in open(
               r"D:\AltaScraper\static\js\orders.js", encoding="utf-8").read())

print("\n== there is ONE reader of what an order contained ==")
src = open(r"D:\AltaScraper\domain\hourly_week.py", encoding="utf-8").read()
check_true("the hourly page uses the shared reader", "_ol.order_items(" in src)
check("and no longer calls Amazon itself", "get_order_items" in src, False)
ol_src = open(r"D:\AltaScraper\domain\orders_live.py", encoding="utf-8").read()
check("orders_live is the single caller", ol_src.count("get_order_items("), 1)

print("\n== the shape the hourly page needs is the shape it gets ==")
# order_items returns lines keyed the same way for both callers; asserted on the
# contract rather than by calling Amazon.
for field in ("asin", "sku", "title", "units", "price", "currency"):
    check_true('a line carries "%s"' % field, '"%s":' % field in ol_src)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
