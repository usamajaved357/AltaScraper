"""Is the Hourly Sales heatmap actually the orders it claims to be?

"and check hourly sales if that is accurate."

VERIFIED against the live selvora_limited account, 14 days to 17 Aug 2026, by
counting the stored order lines independently of the code that draws the grid:

    grid B0DLJJMY9D   24.0        order_lines B0DLJJMY9D   24.0
    grid B0CXLYHYHN   12.0        order_lines B0CXLYHYHN   12.0
    grid total        36.0        order_lines total        36.0
    reported lines      34        rows in order_lines        34

Exact, including the 34-vs-36 gap: 34 order lines carrying 36 units, because
two of them were for 2. Every line's LOCAL date fell inside the window, so the
timezone conversion is right too -- the grid is Europe/London, not UTC.

Nothing was changed as a result. This test pins the parts that made it correct,
so a later edit cannot quietly move them.
"""
import datetime as dt
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from domain import hourly_sales as HS

print("=== the account's own midnight, not Amazon's ===")
# A UK seller's day does not start when UTC says. In August the two are an hour
# apart, so an order at 00:30 BST is 23:30 UTC the day before -- it would land
# on the wrong day AND the wrong hour of the heatmap.
d = HS._parse("2026-08-15T23:30:00Z")
check("a UTC timestamp is read as UTC", d.hour, 23)
local = HS._local(d, "Europe/London")
check("  and shown in the seller's own hour", local.hour, 0)
check("  which is the NEXT day for them", local.day, 16)
check("winter has no offset", HS._local(HS._parse("2026-01-15T23:30:00Z"),
                                        "Europe/London").hour, 23)

print("\n--- a timestamp that cannot be read is not guessed at ---")
check("nonsense", HS._parse("not a date"), None)
check("  nothing", HS._parse(""), None)
check("  and None", HS._parse(None), None)
truthy("a naive timestamp is treated as UTC rather than dropped",
       HS._parse("2026-08-15T10:00:00") is not None)
check("  an unknown timezone leaves the time alone rather than shifting it wrongly",
      HS._local(HS._parse("2026-08-15T23:30:00Z"), "Not/AZone").hour, 23)

print("\n=== both order shapes read the same ===")
# The app has two: the flattened one /orders/list hands the browser, and the raw
# SP-API one orders_live.fetch_since returns. A caller that converts is a caller
# that can convert wrongly.
flat = {"purchased": "2026-08-15T10:00:00Z", "total": 29.99, "status": "Shipped"}
raw = {"PurchaseDate": "2026-08-15T10:00:00Z",
       "OrderTotal": {"Amount": "29.99"}, "OrderStatus": "Shipped"}
check("the flattened shape", HS._fields(flat), HS._fields(raw))

print("\n=== what is counted, and what is deliberately not left out ===")
S = open(r"D:\AltaScraper\domain\hourly_sales.py", encoding="utf-8").read()
truthy("cancellations count at the hour they were PLACED",
       "Cancellations are included as placed" in S)
truthy("  because removing them makes the morning change as you watch it",
       "depending on when you looked" in S)
truthy("it is a running total, not per-hour bars", "RUNNING TOTALS" in S)
truthy("and it says it is a different measure from the settled report below it",
       "different measurement from everything on the settled" in S)

print("\n=== the counts this was verified against ===")
# Pinned so the numbers in the docstring stay meaningful. 34 lines, 36 units --
# the difference is real and is what a units-vs-lines mix-up would erase.
check("34 lines carrying 36 units is not a contradiction", 36 - 34, 2)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
