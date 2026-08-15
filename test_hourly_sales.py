"""Today by the hour, with yesterday behind it -- Orbit's Live Sales card.

I SAID THIS COULD NOT BE BUILT, and I was wrong. The reasoning was that
Amazon's Sales & Traffic report is daily, so an hourly curve needed a feed we
did not have. But Orbit's card says "Based on order dates", and every order
carries a purchase TIMESTAMP that this app already pulls for the "today so far"
figures. The curve was derivable from data in hand the whole time.

WHAT THE TESTS BELOW ARE DEFENDING, in order of how badly each would mislead:

  1. AN HOUR THAT HAS NOT HAPPENED IS NULL, NOT ZERO. A running total that
     drops to the axis at the current hour and stays there until midnight says
     the day collapsed. It is the same mistake as drawing an undelivered day as
     no sales, and on a card titled "live" it is worse, because it looks like
     it is happening now.

  2. YESTERDAY IS COMPARED AT THE SAME HOUR. Against yesterday's FULL day,
     every morning shows a collapse and every evening a recovery, neither of
     which happened.

  3. RUNNING TOTALS, not per-hour amounts. The question is "am I ahead of
     yesterday", answered by which line is higher at the same hour.

  4. A CANCELLED ORDER STILL HAPPENED. It is excluded from the money, but
     removing it retroactively would change this morning's shape depending on
     when you looked at the screen.
"""
import datetime as _dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import hourly_sales as H

NOW = _dt.datetime(2026, 8, 14, 14, 30, tzinfo=_dt.timezone.utc)
ORDERS = [
    {"purchased": "2026-08-14T09:15:00Z", "total": "20.00", "status": "Shipped"},
    {"purchased": "2026-08-14T09:45:00Z", "total": "30.00", "status": "Pending"},
    {"purchased": "2026-08-14T13:00:00Z", "total": "50.00", "status": "Shipped"},
    {"purchased": "2026-08-13T09:00:00Z", "total": "40.00", "status": "Shipped"},
    {"purchased": "2026-08-13T20:00:00Z", "total": "60.00", "status": "Shipped"},
    # The RAW SP-API shape, which the server hands in directly.
    {"PurchaseDate": "2026-08-14T10:00:00Z", "OrderTotal": {"Amount": "5.00"},
     "OrderStatus": "Shipped"},
    {"purchased": "2026-08-14T11:00:00Z", "total": "99.00", "status": "Cancelled"},
    {"purchased": "", "total": "7.00", "status": "Shipped"},
]

c = H.curve(ORDERS, tz="", now=NOW)

print("=== running totals, not per-hour amounts ===")
check("09:00 carries both of that hour's orders", c["today"][9], 50.0)
check("10:00 has carried them forward and added the next", c["today"][10], 55.0)
check("nothing at 11 or 12, so the total holds", c["today"][12], 55.0)
check("13:00 adds the afternoon order", c["today"][13], 105.0)
check("the total is the last real hour", c["today_total"], 105.0)

print("\n=== an hour that has not happened is NULL ===")
check("the current hour is filled", c["today"][14], 105.0)
check("the next one is null, NOT zero", c["today"][15], None)
check("  and so is midnight", c["today"][23], None)
truthy("every remaining hour is null",
       all(c["today"][h] is None for h in range(15, 24)))

print("\n=== yesterday runs the whole day ===")
check("yesterday's morning", c["yesterday"][9], 40.0)
check("yesterday's evening, hours after today stops", c["yesterday"][20], 100.0)
check("  right through to midnight", c["yesterday"][23], 100.0)
truthy("no hour of yesterday is null", all(v is not None for v in c["yesterday"]))

print("\n=== the comparison is at the SAME HOUR ===")
# The whole point: 105 against yesterday-so-far (40), never against
# yesterday's full 100. Otherwise the morning always looks like a collapse.
check("yesterday's full day", c["yesterday_total"], 100.0)
check("yesterday BY THIS HOUR", c["yesterday_so_far"], 40.0)
truthy("they are different, which is why the distinction matters",
       c["yesterday_total"] != c["yesterday_so_far"])

print("\n=== what is counted, and what is not ===")
check("a cancelled order is not in the money", 99.0 in c["today"], False)
check("a pending one IS -- it was placed", c["today"][9], 50.0)
check("today's order count excludes the cancellation", c["today_orders"], 4)
# An order with no timestamp must be skipped, never dropped into hour zero --
# that would put a spike at midnight every single day.
check("an order with no timestamp is skipped, not put at midnight",
      c["today"][0], 0.0)

print("\n=== both order shapes are read ===")
# The app has two: what /orders/list hands the browser, and what the SP-API
# returns. A caller that has to convert is a caller that can convert wrongly.
ts, amt, status = H._fields({"PurchaseDate": "2026-01-01T00:00:00Z",
                             "OrderTotal": {"Amount": "12.34"},
                             "OrderStatus": "Shipped"})
check("the raw SP-API shape", (amt, status), (12.34, "Shipped"))
ts2, amt2, status2 = H._fields({"purchased": "2026-01-01T00:00:00Z",
                                "total": "56.78", "status": "Pending"})
check("the flattened shape", (amt2, status2), (56.78, "Pending"))

print("\n=== the timezone is the account's, not Amazon's ===")
# 23:30 UTC on the 14th is 00:30 on the 15th in London -- a different day. A UK
# seller's midnight is what decides which day an order lands in.
late = [{"purchased": "2026-08-14T23:30:00Z", "total": "10.00", "status": "Shipped"}]
uk = H.curve(late, tz="Europe/London",
             now=_dt.datetime(2026, 8, 15, 10, 0, tzinfo=_dt.timezone.utc))
truthy("an order just before UK midnight counts on the UK day",
       (uk["today_total"] or 0) > 0)

print("\n=== the route is wired ===")
SR = open("routes/sales_routes.py", encoding="utf-8").read()
truthy("there is an hourly endpoint", '"/sales/hourly"' in SR)
truthy("it reuses the existing order fetch rather than calling Amazon twice",
       "_ol.fetch_since" in SR)
truthy("it says when Amazon stopped part-way, so a short curve is not read as low",
       "incomplete rather" in SR)
JS = open("static/js/sales.js", encoding="utf-8").read()
truthy("the card asks for it", "/sales/hourly" in JS)
truthy("and compares against the same hour, not yesterday's whole day",
       "yesterday_so_far" in JS)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
