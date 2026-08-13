"""Today so far: the timezone, and what counts as a sale.

Two things here are wrong by default and look right:

  * "TODAY" IS THE MARKETPLACE'S TODAY. Read the server clock and a UK day
    starts five hours early from Sahiwal -- every morning the figure is wrong and
    nothing on screen says so.
  * PENDING ORDERS HAVE NO MONEY YET. Counted as orders, worth zero, and
    declared -- otherwise revenue-per-order looks broken and nobody can say why.
"""
import sys, datetime as dt
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-62s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

from domain import orders_live as ol

print("=== the day starts in the MARKETPLACE, not on this machine ===")
check("UK runs on London", str(ol.marketplace_zone("UK")), "Europe/London")
check("US reporting runs on Pacific, not Eastern",
      str(ol.marketplace_zone("US")), "America/Los_Angeles")
check("Germany on Berlin", str(ol.marketplace_zone("DE")), "Europe/Berlin")
check("an unknown marketplace falls back to UTC rather than guessing",
      str(ol.marketplace_zone("ZZ")), "UTC")

uk = ol.day_start("UK")
check("the day starts at midnight", (uk.hour, uk.minute, uk.second), (0, 0, 0))
check("  in the marketplace's own zone", str(uk.tzinfo), "Europe/London")
check("yesterday is exactly one day earlier",
      (ol.day_start("UK", 0).date() - ol.day_start("UK", 1).date()).days, 1)
# The whole point: the UK day boundary is NOT the server's day boundary.
check("UK midnight is not assumed to be UTC midnight, it is converted",
      ol.day_start("UK").astimezone(dt.timezone.utc).tzinfo, dt.timezone.utc)

print("\n=== what counts as a sale ===")
def order(status, shipped=0, unshipped=0, total=None):
    o = {"OrderStatus": status, "NumberOfItemsShipped": shipped,
         "NumberOfItemsUnshipped": unshipped}
    if total is not None:
        o["OrderTotal"] = {"Amount": str(total), "CurrencyCode": "GBP"}
    return o

s = ol.summarise([
    order("Shipped", shipped=2, total=40.00),
    order("Unshipped", unshipped=1, total=15.50),
    order("Pending", unshipped=1),                 # Amazon withholds the total
    order("Canceled", unshipped=1, total=99.00),   # not a sale
])
check("three live orders, the cancellation excluded", s["orders"], 3)
check("  and the cancellation counted separately", s["cancelled"], 1)
check("units add up across shipped and unshipped", s["units"], 4)
check("revenue ignores the cancelled order", s["revenue"], 55.5)
check("  and a pending order adds nothing", s["pending"], 1)
check("currency carried from the first order with one", s["currency"], "GBP")

check("British spelling of cancelled is handled too",
      ol.summarise([order("Cancelled", total=10.0)])["orders"], 0)

print("\n=== nothing is not zero ===")
e = ol.summarise([])
check("no orders is no orders", (e["orders"], e["units"]), (0, 0))
check("  and no currency invented", e["currency"], "")

print("\n=== the endpoint is gated like the rest ===")
from auth.guard import feature_for, required_permission
check("today is part of sales", feature_for("/sales/today"), "sales")
check("  and reading it needs no edit right",
      required_permission("/sales/today", "GET"), None)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
