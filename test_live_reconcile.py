"""The Orders API is the truth for what sold, and it must reach the STORE.

THE REPORT: "the data is not what truly represent the statts because orbit sales
data is nearly correct but yours is not".

Measured, and correct. On nestwell_goods the screen showed 149.95 for a fortnight
in which the business had taken 323.38 -- 54% of the money missing. On
selvora_limited it showed 0.00 against 947.72 of real trade.

WHY. Amazon publishes the same trade twice: the Orders API within minutes, the
Sales & Traffic report a day or more later, both dated by when the order was
PLACED. This app read the report and used the Orders API only to patch gaps --
and then only in the browser, for the five cards. The charts, the P&L grid and
the CSV export read the stored series, which had nothing.

Orbit's rule, which this now follows: "Orders API wins for top-line
[Sales/Orders/Units] because it's realtime order-date basis."

Amazon is stood in for throughout: what is being tested is which source the app
BELIEVES and what it writes down, not what Amazon says.
"""
import os, sys, json, tempfile, shutil, datetime as dt

sys.path.insert(0, r"D:\AltaScraper")

from data import db as _db
from domain import sales_data as _sd
import domain.live_reconcile as lr

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altalive_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")
WS, MKT = "nestwell_goods", "UK"

TODAY = dt.date.today()
D = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()

# The report's version: it has delivered the older days and nothing since.
_sd.store(CFG, WS, MKT, [
    {"date": D(8), "asin": "*", "units": 1, "orders": 1, "order_items": 1,
     "ordered_sales": 29.99, "sessions": 12, "page_views": 30, "currency": "GBP"},
    {"date": D(6), "asin": "*", "units": 2, "orders": 2, "order_items": 2,
     "ordered_sales": 59.98, "sessions": 40, "page_views": 70, "currency": "GBP"},
])


def _series():
    return {r["date"]: r for r in
            _sd.series(CFG, WS, MKT, D(14), D(0))}


print("\n== before: the store only knows what the report sent ==")
s0 = _series()
check("the report's days are there", round(sum(
    float(r.get("ordered_sales") or 0) for r in s0.values()), 2), 89.97)
# The day is now RETURNED, carrying nothing -- series() covers the whole window
# asked for, so a 90-day chart draws 90 columns rather than stopping at the
# first day of trade. "Absent" therefore means "has no figures", not "has no
# row", and that is what is checked.
check("and the recent days carry nothing yet",
      (s0.get(D(1)) or {}).get("ordered_sales"), None)


# Amazon stood in for: the live feed knows the report's days AND three more.
def _fake_by_day(marketplace, marketplace_id, creds, days=5, price_cache=None,
                 include_shipping=True):
    return {
        "days": {
            D(8): {"orders": 1, "units": 1, "revenue": 29.99,
                   "product_sales": 29.99, "shipping": 0.0},
            D(6): {"orders": 2, "units": 2, "revenue": 59.98,
                   "product_sales": 59.98, "shipping": 0.0},
            # 3 units but only 2 orders -- somebody bought two things at once.
            D(3): {"orders": 2, "units": 3, "revenue": 89.97,
                   "product_sales": 89.97, "shipping": 0.0},
            D(2): {"orders": 3, "units": 3, "revenue": 74.97,
                   "product_sales": 74.97, "shipping": 0.0},
            D(1): {"orders": 1, "units": 1, "revenue": 8.49,
                   "product_sales": 8.49, "shipping": 0.0},
        },
        "currency": "GBP", "since": D(13), "truncated": False,
    }


import domain.orders_live as _ol
_real_by_day = _ol.by_day
_ol.by_day = _fake_by_day
try:
    res = lr.reconcile(CFG, WS, MKT, "A1F83G8C2ARO7P", {}, days=14)
finally:
    _ol.by_day = _real_by_day

print("\n== after: the live truth is in the STORE, not just on a card ==")
s1 = _series()
total = round(sum(float(r.get("ordered_sales") or 0) for r in s1.values()), 2)
check("every penny is now stored", total, 263.40)
check("  which the report alone could not reach", total > 89.97, True)
check("units follow", sum(int(r.get("units") or 0) for r in s1.values()), 10)
check("the days the report never sent are present", D(1) in s1, True)

print("\n== orders means ORDERS, not order items ==")
check("a two-item order counts once", s1[D(3)]["orders"], 2)
check("  while its units count twice over", s1[D(3)]["units"], 3)
check("the report's own item count is still kept", s0[D(6)]["order_items"], 2)

print("\n== where both sources spoke, they agreed ==")
check("no day the report had was changed", res["days_changed"], 0)
check_true("and the reconcile says so, rather than leaving it to be assumed",
           "days_changed" in res)

print("\n== the source of every figure is recorded ==")
check("the live feed is named", s1[D(1)].get("orders_source"), "orders_api")
owned = lr.owned_days(CFG, WS, MKT, D(14), D(0))
check_true("and the days it owns can be listed", D(1) in owned and D(3) in owned)

print("\n== a quiet day is written as a REAL zero ==")
# Otherwise a day the report wrongly shows as busy could never be corrected down.
check("a day with no orders is stored, not skipped", D(5) in s1, True)
# `or` is not usable here: a real 0.0 is falsy and would read as absent, which is
# precisely the distinction being tested. Asked for explicitly instead.
_q = s1[D(5)].get("ordered_sales")
check("  as a real zero, not as missing", (_q is not None, float(_q or 0)),
      (True, 0.0))

print("\n== the report can no longer overwrite the live answer ==")
# Amazon delivers its (later, lower) version of a day the live feed already has.
_sd.store(CFG, WS, MKT, [
    {"date": D(1), "asin": "*", "units": 0, "orders": 0, "order_items": 0,
     "ordered_sales": 0.0, "sessions": 99, "page_views": 210, "currency": "GBP"},
])
s2 = _series()
check("the live sales survive", float(s2[D(1)]["ordered_sales"]), 8.49)
check("  and the live units", int(s2[D(1)]["units"]), 1)
check("  and the live order count", int(s2[D(1)]["orders"]), 1)
print("  -- but everything the report UNIQUELY has still lands:")
check("sessions are taken from the report", int(s2[D(1)]["sessions"]), 99)
check("  and page views", int(s2[D(1)]["page_views"]), 210)

print("\n== per-ASIN rows are left to the report entirely ==")
_sd.store(CFG, WS, MKT, [
    {"date": D(1), "asin": "B0TEST123", "units": 4, "orders": 4,
     "ordered_sales": 44.0, "sessions": 9, "currency": "GBP"},
])
conn = _db.get_db(CFG)
r = conn.execute("SELECT units, ordered_sales FROM sales_daily WHERE asin='B0TEST123'"
                 ).fetchone()
check("a product row is written in full", (r["units"], r["ordered_sales"]), (4, 44.0))

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
