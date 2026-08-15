"""probe_ordertotal.py -- what does an order's money ACTUALLY consist of?

CLAUDE.md Rule 4: do not guess. The app's Total Sales card and its live chart
fill both come from domain/orders_live._amount(), which reads OrderTotal.Amount.
The owner counted 89.97 for three orders (3 x 29.99) where the app showed
102.21. The 12.24 difference has to be explained by what Amazon sends, not by a
plausible story about shipping -- so this prints OrderTotal beside the sum of
the ITEM prices, the shipping, and the tax, per order, and says which one
matches the figure the owner counted.

Reads only. Nothing is written and nothing is sent to Amazon beyond the orders
list and one getOrderItems call per order.

    python probe_ordertotal.py jack_uk UK
    python probe_ordertotal.py jack_uk UK --days 14
"""
import json
import sys
import datetime as dt

sys.path.insert(0, r"D:\AltaScraper")


def _m(d, key):
    """The CurrencyAmount-style money field `key`, as a float."""
    v = (d or {}).get(key) or {}
    try:
        return float(v.get("Amount") or 0.0)
    except (TypeError, ValueError):
        return 0.0


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
    from sp_api.api import Orders
    from sp_api.base import Marketplaces

    creds = _acc.account_creds(acc)
    mkt = getattr(Marketplaces, marketplace, None) or Marketplaces.US
    mkt_id = mkt.marketplace_id
    oc = Orders(credentials=creds, marketplace=mkt)

    end = dt.datetime.utcnow()
    start = end - dt.timedelta(days=days)
    print("account : %s (%s / %s)" % (account_id, marketplace, mkt_id))
    print("window  : %s .. %s UTC\n" % (start.date(), end.date()))

    orders, truncated = _ol.fetch_since(marketplace, mkt_id, creds, start)
    if truncated:
        print("(more pages exist than were read)")
    print("orders returned: %d\n" % len(orders))
    if not orders:
        print("Nothing in the window.")
        return 0

    tot_ordertotal = tot_item = tot_ship = tot_tax = tot_promo = 0.0
    print("%-20s %-12s %10s %10s %10s %10s %10s"
          % ("order", "status", "OrderTotal", "items", "shipping", "tax", "promo"))
    for o in orders:
        oid = str(o.get("AmazonOrderId") or "?")
        status = str(o.get("OrderStatus") or "?")
        ot = _m(o, "OrderTotal")

        items = []
        try:
            r = oc.get_order_items(oid)
            pay = r.payload if hasattr(r, "payload") else (r or {})
            items = (pay or {}).get("OrderItems") or []
        except Exception as e:
            print("   (could not read items for %s: %s)" % (oid, str(e)[:80]))

        it = sum(_m(i, "ItemPrice") for i in items)
        sh = sum(_m(i, "ShippingPrice") for i in items)
        tx = sum(_m(i, "ItemTax") for i in items) + sum(_m(i, "ShippingTax") for i in items)
        pr = sum(_m(i, "PromotionDiscount") for i in items)

        tot_ordertotal += ot
        tot_item += it
        tot_ship += sh
        tot_tax += tx
        tot_promo += pr
        print("%-20s %-12s %10.2f %10.2f %10.2f %10.2f %10.2f"
              % (oid[-18:], status[:12], ot, it, sh, tx, pr))

    print("-" * 86)
    print("%-33s %10.2f %10.2f %10.2f %10.2f %10.2f"
          % ("TOTAL", tot_ordertotal, tot_item, tot_ship, tot_tax, tot_promo))
    print()
    print("what the app shows today (OrderTotal)        : %.2f" % tot_ordertotal)
    print("sum of ItemPrice ('ordered product sales')   : %.2f" % tot_item)
    print("ItemPrice minus promotions                   : %.2f" % (tot_item - tot_promo))
    print()
    print("Seller Central's 'Ordered product sales' is the ITEM price line.")
    print("Whichever of these matches what you counted is the one the card should show.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
