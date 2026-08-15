"""probe_audit_sales.py -- prove the stored figures against the raw orders.

Not a check that the app agrees with itself. This lists EVERY order Amazon
returns, one line each, adds them up by hand, and compares that to what the app
has stored. If the two differ, the app is wrong and the difference is printed.

    python probe_audit_sales.py selvora_limited UK
    python probe_audit_sales.py nestwell_goods UK --days 14 --list
"""
import json
import sys
import datetime as dt
from collections import defaultdict

sys.path.insert(0, r"D:\AltaScraper")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    aid, marketplace = args[0], args[1].upper()
    days = 14
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except Exception:
            pass
    show_each = "--list" in argv

    cfg = json.load(open("config.json", encoding="utf-8"))
    acc = next((a for a in (cfg.get("accounts") or [])
                if str(a.get("id")) == aid), None)
    if not acc:
        print("no account called %r" % aid)
        return 1

    from domain import accounts as _acc
    from domain import sales_data as _sd
    import domain.orders_live as _ol
    import domain.hourly_week as _hw
    from sp_api.base import Marketplaces
    import dashboard as D

    creds = _acc.account_creds(acc)
    mkt = getattr(Marketplaces, marketplace, None) or Marketplaces.UK
    since = _ol.day_start(marketplace, days_ago=days - 1)
    tz = _ol.marketplace_zone(marketplace)

    # ---- THE RAW TRUTH: every order, counted by hand -----------------------
    orders, truncated = _ol.fetch_since(marketplace, mkt.marketplace_id, creds, since)
    priced, unpriced, complete = _ol.product_sales(
        marketplace, creds, orders,
        cache=_hw.price_cache(D.CONFIG_PATH, aid, marketplace))

    by_day = defaultdict(lambda: {"ids": set(), "units": 0, "sales": 0.0})
    dead = 0
    for o in orders:
        status = str(o.get("OrderStatus") or "")
        oid = str(o.get("AmazonOrderId") or "")
        if status.lower() in _ol._DEAD:
            dead += 1
            continue
        raw = str(o.get("PurchaseDate") or "")
        try:
            d = dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(tz)
        except Exception:
            continue
        ds = d.date().isoformat()
        b = by_day[ds]
        b["ids"].add(oid)
        try:
            u = int(o.get("NumberOfItemsShipped") or 0) + int(o.get("NumberOfItemsUnshipped") or 0)
        except (TypeError, ValueError):
            u = 0
        b["units"] += u
        amt, _cur = _ol.revenue_of(priced.get(oid), True)
        if not amt:
            amt, _cur = _ol._amount(o)
        b["sales"] += float(amt or 0)
        if show_each:
            print("   %s  %-20s %-11s %2d units  %8.2f"
                  % (d.strftime("%Y-%m-%d %H:%M"), oid[-18:], status, u, amt))

    print("\nAmazon returned %d order(s) since %s (%d cancelled, ignored)%s"
          % (len(orders), since.date(), dead,
             "  [MORE PAGES EXIST]" if truncated else ""))
    if unpriced:
        print("%d order(s) Amazon would not itemise -- those used OrderTotal" % unpriced)

    # ---- WHAT THE APP STORES ----------------------------------------------
    stored = {r["date"]: r for r in _sd.series(
        D.CONFIG_PATH, aid, marketplace,
        since.date().isoformat(), dt.date.today().isoformat())}

    print("\n%-12s | %-24s | %-24s |" % ("", "   COUNTED BY HAND", "   WHAT THE APP STORES"))
    print("%-12s | %8s %6s %7s | %8s %6s %7s | %s"
          % ("date", "sales", "units", "orders", "sales", "units", "orders", ""))
    print("-" * 84)

    h_s = h_u = h_o = 0
    a_s = a_u = a_o = 0
    bad = 0
    for ds in sorted(set(by_day) | set(stored)):
        b = by_day.get(ds)
        s = stored.get(ds) or {}
        hs = round(b["sales"], 2) if b else 0.0
        hu = b["units"] if b else 0
        ho = len(b["ids"]) if b else 0
        as_ = float(s.get("ordered_sales") or 0)
        au = int(s.get("units") or 0)
        ao = int(s.get("orders") or 0)
        h_s += hs; h_u += hu; h_o += ho
        a_s += as_; a_u += au; a_o += ao
        ok = (abs(hs - as_) < 0.02 and hu == au and ho == ao)
        if not ok:
            bad += 1
        print("%-12s | %8.2f %6d %7d | %8.2f %6d %7d | %s"
              % (ds, hs, hu, ho, as_, au, ao, "" if ok else "MISMATCH"))

    print("-" * 84)
    print("%-12s | %8.2f %6d %7d | %8.2f %6d %7d |"
          % ("TOTAL", h_s, h_u, h_o, a_s, a_u, a_o))
    print()
    if bad:
        print("%d day(s) do NOT match. The stored figures are wrong." % bad)
        return 1
    print("Every day matches the raw orders. The stored figures are true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
