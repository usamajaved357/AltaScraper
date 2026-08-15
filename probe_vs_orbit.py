"""probe_vs_orbit.py -- do our figures match the feed Orbit says it trusts?

Orbit's own answer, in its words:

  A1  "Total Sales, Total Orders, Total Units: SP-API Orders API -
       /orders/v0/orders + orderItems. This is what drives the Leading
       Indicators snapshot and orders_based_pl_v3. Not settlement."
  A2  "Orders API wins for top-line [Sales/Orders/Units] because it's realtime
       order-date basis. If Business Report says orderedProductSales = $1,000
       and Orders API sums to $1,050 for same day, dashboard shows Orders API
       figure for Sales."
  B8  "One Order, N Units. Total Orders = count distinct amazonOrderId,
       Total Units = sum quantityOrdered."

This app prefers the Sales & Traffic REPORT and only fills days the report has
not delivered. That is the opposite priority, and this prints both side by side
so the difference is a measurement rather than an argument.

Reads only.

    python probe_vs_orbit.py jack_uk UK
    python probe_vs_orbit.py jack_uk UK --days 14
"""
import json
import sys
import datetime as dt

sys.path.insert(0, r"D:\AltaScraper")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    account_id, marketplace = args[0], args[1].upper()
    days = 14
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except Exception:
            pass

    cfg = json.load(open("config.json", encoding="utf-8"))
    acc = next((a for a in (cfg.get("accounts") or [])
                if str(a.get("id")) == account_id), None)
    if not acc:
        print("no account called %r" % account_id)
        return 1

    from domain import accounts as _acc
    from domain import sales_data as _sd
    import domain.orders_live as _ol
    import domain.hourly_week as _hw
    from sp_api.base import Marketplaces
    import dashboard as D

    creds = _acc.account_creds(acc)
    mkt = getattr(Marketplaces, marketplace, None) or Marketplaces.UK
    end = dt.date.today()
    start = end - dt.timedelta(days=days - 1)

    # OURS: what the app stores and shows, from the report.
    rows = _sd.series(D.CONFIG_PATH, account_id, marketplace,
                      start.isoformat(), end.isoformat())
    ours = {r["date"]: r for r in rows}

    # ORBIT'S BASIS: the Orders API, counted its way.
    cache = _hw.price_cache(D.CONFIG_PATH, account_id, marketplace)
    live = _ol.by_day(marketplace, mkt.marketplace_id, creds,
                      days=min(days, 30), price_cache=cache)
    theirs = live.get("days") or {}

    print("account %s (%s)   %s .. %s\n" % (account_id, marketplace, start, end))
    print("%-12s | %-26s | %-26s |" % ("", "  REPORT (what we show)", "  ORDERS API (Orbit's)"))
    print("%-12s | %8s %7s %7s | %8s %7s %7s | %s"
          % ("date", "sales", "units", "items", "sales", "units", "orders", "agrees?"))
    print("-" * 92)

    dates = sorted(set(ours) | set(theirs))
    tot_r_sales = tot_l_sales = 0.0
    tot_r_units = tot_l_units = 0
    disagreements = 0
    for d in dates:
        r = ours.get(d) or {}
        l = theirs.get(d) or {}
        rs = r.get("ordered_sales")
        ru = r.get("units")
        ri = r.get("orders")
        ls = l.get("product_sales")
        lu = l.get("units")
        lo = l.get("orders")

        tot_r_sales += float(rs or 0)
        tot_l_sales += float(ls or 0)
        tot_r_units += int(ru or 0)
        tot_l_units += int(lu or 0)

        # Only compare where the Orders API has an opinion.
        note = ""
        if l:
            same_sales = abs(float(rs or 0) - float(ls or 0)) < 0.01
            same_units = int(ru or 0) == int(lu or 0)
            if not (same_sales and same_units):
                note = "NO"
                disagreements += 1
                if rs in (None, 0) and ls:
                    note = "NO  report has nothing"
            else:
                note = "yes"
        print("%-12s | %8s %7s %7s | %8s %7s %7s | %s"
              % (d,
                 "-" if rs is None else ("%.2f" % rs), ru if ru is not None else "-",
                 ri if ri is not None else "-",
                 "-" if ls is None else ("%.2f" % ls), lu if lu is not None else "-",
                 lo if lo is not None else "-",
                 note))

    print("-" * 92)
    print("%-12s | %8.2f %7d %7s | %8.2f %7d %7s |"
          % ("TOTAL", tot_r_sales, tot_r_units, "", tot_l_sales, tot_l_units, ""))
    print()
    print("days where the two disagree: %d" % disagreements)
    print()
    print("Orbit shows the RIGHT-HAND figures. This app shows the LEFT-HAND ones,")
    print("filling in from the right only where the report sent nothing at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
