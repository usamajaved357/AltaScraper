"""probe_screens_audit.py -- Live Sales, Week to Date and the Sales Report.

Each is checked against the raw Amazon orders for the same window, counted here
rather than taken from the app. A screen that agrees with the app but not with
Amazon has not been checked at all.

    python probe_screens_audit.py
    python probe_screens_audit.py jack_uk UK
"""
import sys
import datetime as dt
from collections import defaultdict

sys.path.insert(0, r"D:\AltaScraper")


def hand_count(aid, mkt, since, until=None):
    """Amazon's own orders, added up here: (sales, units, orders)."""
    import dashboard as D
    from domain import accounts as _acc
    import domain.orders_live as _ol
    import domain.hourly_week as _hw

    a = next((x for x in D._cfg()["accounts"] if x["id"] == aid), None)
    creds = _acc.account_creds(a)
    from sp_api.base import Marketplaces
    mid = getattr(Marketplaces, mkt).marketplace_id
    orders, _t = _ol.fetch_since(mkt, mid, creds, since, until=until)
    priced, _u, _c = _ol.product_sales(
        mkt, creds, orders, cache=_hw.price_cache(D.CONFIG_PATH, aid, mkt))
    ids, units, sales = set(), 0, 0.0
    for o in orders:
        if str(o.get("OrderStatus") or "").lower() in _ol._DEAD:
            continue
        oid = str(o.get("AmazonOrderId") or "")
        ids.add(oid)
        try:
            units += int(o.get("NumberOfItemsShipped") or 0) + \
                     int(o.get("NumberOfItemsUnshipped") or 0)
        except (TypeError, ValueError):
            pass
        amt, _cur = _ol.revenue_of(priced.get(oid), True)
        if not amt:
            amt, _cur = _ol._amount(o)
        sales += float(amt or 0)
    return round(sales, 2), units, len(ids)


def audit(aid, mkt):
    import dashboard as D
    import domain.orders_live as _ol
    import domain.hourly_week as _hw
    from domain import accounts as _acc
    from domain import sales_data as _sd
    from sp_api.base import Marketplaces

    a = next((x for x in D._cfg()["accounts"] if x["id"] == aid), None)
    if not a:
        return ["no such account"]
    try:
        creds = _acc.account_creds(a)
        mid = getattr(Marketplaces, mkt).marketplace_id
    except Exception as e:
        print("\n%s (%s): %s" % (aid, mkt, str(e)[:70]))
        return []

    print("\n%s\n%s (%s)\n%s" % ("=" * 66, aid, mkt, "=" * 66))
    bad = []

    def chk(name, a_, b_, tol=0.02):
        ok = (abs(a_[0] - b_[0]) < tol and a_[1] == b_[1] and a_[2] == b_[2])
        print("   %-26s screen %8.2f/%s/%s   raw %8.2f/%s/%s   %s"
              % (name, a_[0], a_[1], a_[2], b_[0], b_[1], b_[2],
                 "OK" if ok else "MISMATCH"))
        if not ok:
            bad.append("%s: %s vs %s" % (name, a_, b_))

    # ---- LIVE SALES: today so far ----------------------------------------
    try:
        res = _ol.today(mkt, mid, creds, compare=True,
                        price_cache=_hw.price_cache(D.CONFIG_PATH, aid, mkt))
        t = res["today"]
        screen = (round(float(t.get("revenue") or 0), 2),
                  int(t.get("units") or 0), int(t.get("orders") or 0))
        raw = hand_count(aid, mkt, _ol.day_start(mkt, 0))
        chk("Live Sales (today)", screen, raw)
        y = res.get("yesterday") or {}
        now = dt.datetime.now(_ol.marketplace_zone(mkt))
        y_start = _ol.day_start(mkt, 1)
        y_until = y_start + (now - _ol.day_start(mkt, 0))
        yscreen = (round(float(y.get("revenue") or 0), 2),
                   int(y.get("units") or 0), int(y.get("orders") or 0))
        chk("  vs same time yesterday", yscreen,
            hand_count(aid, mkt, y_start, until=y_until))
    except Exception as e:
        print("   Live Sales failed: %s" % str(e)[:90])
        bad.append("live sales: %s" % str(e)[:80])

    # ---- WEEK TO DATE and the SALES REPORT --------------------------------
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    for name, start in (("Week to Date", monday),
                        ("Sales Report (30d)", today - dt.timedelta(days=29))):
        rows = _sd.series(D.CONFIG_PATH, aid, mkt, start.isoformat(),
                          today.isoformat(),
                          vat_rate=_sd.vat_rate_for(D._cfg, aid), basis="order")
        screen = (round(sum(float(r.get("ordered_sales") or 0) for r in rows), 2),
                  sum(int(r.get("units") or 0) for r in rows),
                  sum(int(r.get("orders") or 0) for r in rows))
        since = _ol.day_start(mkt, days_ago=(today - start).days)
        chk(name, screen, hand_count(aid, mkt, since))
    return bad


def main(argv):
    import dashboard as D
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) >= 2:
        pairs = [(args[0], args[1].upper())]
    else:
        pairs = []
        for a in (D._cfg().get("accounts") or []):
            m = (a.get("default_marketplace")
                 or (a.get("marketplaces") or [None])[0])
            if a.get("id") and m:
                pairs.append((a["id"], str(m).upper()))

    allbad = {}
    for aid, mkt in pairs:
        try:
            b = audit(aid, mkt)
        except Exception as e:
            b = ["audit failed: %s" % str(e)[:120]]
        if b:
            allbad[aid] = b

    print("\n%s\nSUMMARY\n%s" % ("=" * 66, "=" * 66))
    if not allbad:
        print("Live Sales, Week to Date and the Sales Report all match Amazon.")
        return 0
    for aid, b in allbad.items():
        print("\n%s:" % aid)
        for x in b:
            print("   - %s" % x)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
