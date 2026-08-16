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

    print("\n== TWO ACCOUNTS MUST NEVER SHARE A CACHED ORDER LIST ==")
    # The key was marketplace + marketplace_id + window, and every UK account
    # shares all three -- so three separate companies collided on one key and
    # whichever asked first served its orders to the other two. Caught when a
    # backfill reported the identical "17 orders seen" for jack_uk,
    # selvora_limited and nestwell_goods, which are different businesses.
    ol._ORDERS_CACHE.clear()
    calls["n"] = 0
    A = {"refresh_token": "tok-A", "lwa_app_id": "app-A", "seller_id": "AAA"}
    B = {"refresh_token": "tok-B", "lwa_app_id": "app-B", "seller_id": "BBB"}
    ol.fetch_since("UK", "A1F83G8C2ARO7P", A, since)
    check("the first account asks Amazon", calls["n"], 1)
    ol.fetch_since("UK", "A1F83G8C2ARO7P", B, since)
    check("a DIFFERENT account asks for itself", calls["n"], 2)
    ol.fetch_since("UK", "A1F83G8C2ARO7P", A, since)
    check("  and the first is still cached", calls["n"], 2)
    check("the two keys differ",
          ol._orders_key("UK", "M", since, None, A)
          == ol._orders_key("UK", "M", since, None, B), False)
    check_true("and neither key contains the secret",
               "tok-A" not in ol._orders_key("UK", "M", since, None, A))

    # Counted as DELTAS from here on. Absolute totals meant that inserting a
    # section above silently broke every assertion below it, which is a test
    # that fails for the wrong reason.
    def since_last():
        n = calls["n"] - since_last.mark
        since_last.mark = calls["n"]
        return n
    since_last.mark = calls["n"]

    print("\n== a DIFFERENT window is still a real question ==")
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, ol.day_start("UK", 6))
    check("a wider window is never answered from a narrower one", since_last(), 1)

    print("\n== insisting on fresh data is still possible ==")
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, since, use_cache=False)
    check("use_cache=False goes to Amazon", since_last(), 1)

    print("\n== an expired entry is not reused ==")
    for k in list(ol._ORDERS_CACHE):
        t, o, tr = ol._ORDERS_CACHE[k]
        ol._ORDERS_CACHE[k] = (t - ol._ORDERS_TTL - 5, o, tr)
    ol.fetch_since("UK", "A1F83G8C2ARO7P", {}, since)
    check("a stale entry is asked again", since_last(), 1)

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

print("\n== the background poll does not spend the quota on empty marketplaces ==")
# THE LOG, on one startup:
#     live orders jack_uk::NL  -> error: handshake timed out
#     live orders jack_uk::PL  -> 14 day(s) written, 0 changed
#     live orders jack_uk::DE  -> 14 day(s) written, 0 changed
#     live orders selvora::FR  -> error: handshake timed out
#
# These accounts are registered across most of Europe and trade in the UK.
# Thirty-three account+marketplace pairs on one fifteen-minute clock is about
# two Orders calls a minute against a quota of roughly one -- so the screen's
# own request queued behind them and Live Sales answered QuotaExceeded. The
# catalogue refresh has had REFRESH_AFTER_EMPTY for this since it was written;
# the live orders poll did not.
import os, json, tempfile, shutil
from domain import live_refresher as _lrf
from data import db as _tdb

_TMP = tempfile.mkdtemp(prefix="altaquota_")
_CFG = os.path.join(_TMP, "config.json")
json.dump({"accounts": [{"id": "acct", "marketplaces": ["UK", "PL"]}]}, open(_CFG, "w"))
_c = _tdb.get_db(_CFG)
_c.execute(
    "INSERT INTO order_lines (workspace_id, marketplace, order_id, purchase_date,"
    " asin, sku, units, revenue, status) VALUES "
    "('acct','UK','O-1','2026-08-01T10:00:00Z','B0X','SKU',1,10.0,'Shipped')")
_c.commit()
_lrf._LIVE_TRADED.clear()
check("a marketplace that trades is known to trade",
      _lrf._has_traded(_CFG, "acct", "UK"), True)
check("  and one that never has is not",
      _lrf._has_traded(_CFG, "acct", "PL"), False)

_lrf._LIVE_LAST.clear()
_lrf._LIVE_TRADED.clear()
# Both were polled a little over the fifteen-minute mark.
_lrf._LIVE_LAST["acct::UK"] = time.time() - (_lrf.LIVE_EVERY + 60)
_lrf._LIVE_LAST["acct::PL"] = time.time() - (_lrf.LIVE_EVERY + 60)
check("the trading marketplace is due again", _lrf._live_due("acct", "UK", _CFG), True)
check("  the empty one is not -- it backs off to six hours",
      _lrf._live_due("acct", "PL", _CFG), False)
_lrf._LIVE_LAST["acct::PL"] = time.time() - (_lrf.LIVE_EVERY_EMPTY + 60)
check("  but it IS still polled eventually, so a first order there shows up",
      _lrf._live_due("acct", "PL", _CFG), True)
check_true("the back-off is longer than the normal rhythm",
           _lrf.LIVE_EVERY_EMPTY > _lrf.LIVE_EVERY)
# A COLD STORE MUST NOT LOOK LIKE AN EMPTY MARKETPLACE. On a fresh deploy no
# marketplace has any order history -- including the one that trades -- and
# backing them all off would stop the poll that fills the table in the first
# place. Nothing would ever arrive.
_lrf._LIVE_TRADED.clear()
check("an account with no history anywhere is polled normally",
      _lrf._has_traded(_CFG, "brand-new-account", "UK"), True)
check("  which is not true of a marketplace on an account that HAS traded",
      _lrf._has_traded(_CFG, "acct", "PL"), False)
shutil.rmtree(_TMP, ignore_errors=True)

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
