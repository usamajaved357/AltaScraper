"""probe_productsales.py -- does the live feed now report what the seller counts?

The owner counted 89.97 for three orders; the app showed 102.21 because it read
OrderTotal, which adds shipping. domain/orders_live.by_day() now sums ItemPrice
instead. This prints what by_day() actually returns, per day, so the figure can
be checked against Seller Central rather than trusted.

Reads only.

    python probe_productsales.py jack_uk UK
    python probe_productsales.py jack_uk UK --days 7
"""
import json
import sys

sys.path.insert(0, r"D:\AltaScraper")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    account_id, marketplace = args[0], args[1].upper()
    days = 7
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
    import domain.orders_live as _ol
    from sp_api.base import Marketplaces

    creds = _acc.account_creds(acc)
    mkt = getattr(Marketplaces, marketplace, None) or Marketplaces.US

    res = _ol.by_day(marketplace, mkt.marketplace_id, creds, days=days)
    cur = res.get("currency") or ""
    print("account : %s (%s)   basis: %s" % (account_id, marketplace,
                                             res.get("basis")))
    print("since   : %s" % res.get("since"))
    if res.get("unpriced_orders"):
        print("NOTE    : %d order(s) Amazon would not price -- those fell back "
              "to OrderTotal" % res["unpriced_orders"])
    if not res.get("priced_complete", True):
        print("NOTE    : more orders than the item-lookup cap; figure is partial")
    print()
    print("%-12s %8s %8s %10s %10s %10s"
          % ("date", "orders", "units", "goods", "postage", "REVENUE"))
    tot_o = tot_u = 0
    tot_r = tot_g = tot_s = 0.0
    for d, v in (res.get("days") or {}).items():
        print("%-12s %8d %8d %10.2f %10.2f %10.2f"
              % (d, v["orders"], v["units"], v.get("product_sales", 0.0),
                 v.get("shipping", 0.0), v["revenue"]))
        tot_o += v["orders"]
        tot_u += v["units"]
        tot_r += v["revenue"]
        tot_g += v.get("product_sales", 0.0)
        tot_s += v.get("shipping", 0.0)
    print("-" * 62)
    print("%-12s %8d %8d %10.2f %10.2f %10.2f %s"
          % ("TOTAL", tot_o, tot_u, tot_g, tot_s, tot_r, cur))
    print()
    print("REVENUE  %.2f  <- what the Sales cards show: everything the buyer paid,"
          % tot_r)
    print("                 with Amazon's fees taken off afterwards.")
    print("goods    %.2f  <- Amazon's 'Ordered product sales'. THIS is the figure"
          % tot_g)
    print("                 to reconcile against Seller Central; postage is not in it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
