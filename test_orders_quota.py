"""We must not spend Amazon's order quota on questions we have already asked.

THE REPORT: Live Sales showing
    "Live Sales could not be loaded. The request failed.
     [{'code': 'QuotaExceeded', 'message': 'You exceeded your quota ...'}]"

Amazon allows getOrders roughly ONCE A MINUTE (0.0167/s, burst 20). Measured,
one Sales screen load made FOUR of them: /sales/today asked twice -- once for
today and once for the same slice of yesterday -- /sales/recent once, and the
background reconcile once, all for overlapping windows of the same account. A
few reopenings spent the burst, and the screen then reported Amazon's raw
refusal dict as though the app had broken.

Two things are tested: that the same window is not asked for twice inside the
cache window, and that today+yesterday now come from ONE read.

Amazon is stood in for -- what matters is how often we would call it.
"""
import sys, time

sys.path.insert(0, r"D:\AltaScraper")

import domain.orders_live as ol

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


calls = {"n": 0}
NOW = ol._dt.datetime.now(ol.marketplace_zone("UK"))


def _order(hours_ago, oid):
    when = NOW - ol._dt.timedelta(hours=hours_ago)
    return {"AmazonOrderId": oid, "OrderStatus": "Shipped",
            "PurchaseDate": when.astimezone(ol._dt.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "NumberOfItemsShipped": 1, "NumberOfItemsUnshipped": 0,
            "OrderTotal": {"Amount": "10.00", "CurrencyCode": "GBP"}}


class _FakeOrders:
    def __init__(self, *a, **k):
        pass

    def get_orders(self, **kw):
        calls["n"] += 1
        # ONE FOR TODAY, ONE INSIDE YESTERDAY'S COMPARABLE SLICE.
        #
        # The comparison covers only the SAME elapsed time of day -- comparing
        # 10am today against a full day yesterday shows a collapse every morning
        # -- so at 00:16 that slice is sixteen minutes long. A fixed "26 hours
        # ago" therefore falls outside it at some hours and inside at others,
        # which made this test pass or fail depending on when it was run. Both
        # orders are now placed relative to the elapsed time itself.
        elapsed = (NOW - ol.day_start("UK", 0)).total_seconds() / 3600.0
        return type("R", (), {"payload": {
            "Orders": [_order(min(1.0, elapsed / 2.0), "TODAY-1"),
                       _order(24.0 + elapsed / 2.0, "YDAY-1")]}})()


import sp_api.api as _api
_real_orders = _api.Orders
_api.Orders = _FakeOrders
ol._ORDERS_CACHE.clear()

try:
    print("\n== the same window is not asked for twice ==")
    calls["n"] = 0
    since = ol.day_start("UK", 1)
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, since)
    check("the first ask reaches Amazon", calls["n"], 1)
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, since)
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, since)
    check("the next two are answered from the last reply", calls["n"], 1)

    print("\n== a DIFFERENT window is still a real question ==")
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, ol.day_start("UK", 6))
    check("a wider window is never answered from a narrower one", calls["n"], 2)

    print("\n== insisting on fresh data is still possible ==")
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, since, use_cache=False)
    check("use_cache=False goes to Amazon", calls["n"], 3)

    print("\n== an expired entry is not reused ==")
    for k in list(ol._ORDERS_CACHE):
        t, o, tr = ol._ORDERS_CACHE[k]
        ol._ORDERS_CACHE[k] = (t - ol._ORDERS_TTL - 5, o, tr)
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, since)
    check("a stale entry is asked again", calls["n"], 4)

    print("\n== today AND yesterday come from ONE read ==")
    ol._ORDERS_CACHE.clear()
    calls["n"] = 0
    res = ol.today("UK", "A1F83G8C2ARO7P", {}, compare=True)
    check("one call, not two", calls["n"], 1)
    check_true("today is reported", res["today"]["orders"] >= 1)
    check_true("yesterday is reported too", "yesterday" in res)
    check("and they are split, not double counted",
          res["today"]["orders"], 1)
    check("  yesterday has its own order", res["yesterday"]["orders"], 1)

    print("\n== the cache cannot grow without limit ==")
    ol._ORDERS_CACHE.clear()
    for i in range(ol._ORDERS_MAX + 10):
        ol.fetch_since("UK", "A1F83G8C2ARO7P", {},
                       ol.day_start("UK", 0) - ol._dt.timedelta(hours=i))
    check_true("it is bounded", len(ol._ORDERS_CACHE) <= ol._ORDERS_MAX)
finally:
    _api.Orders = _real_orders
    ol._ORDERS_CACHE.clear()

print("\n== a quota refusal reads as waiting, not as a fault ==")
js = open(r"D:\AltaScraper\static\js\sales.js", encoding="utf-8").read()
check_true("the screen recognises a throttle", "quotaexceeded" in js.lower())
check_true("  and says nothing is wrong with the figures",
           "Nothing is wrong with your figures" in js)
check_true("  and does not print Amazon's raw dict for it",
           "raw && !throttled" in js)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
