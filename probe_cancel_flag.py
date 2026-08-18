"""What does Amazon ACTUALLY send for BuyerRequestedCancel and IsGift?

CLAUDE.md Rule 4: never guess a value Amazon returns -- print the raw thing and
read it.

    "ON ORDERS DETAIL PAGE IT SHOWS ON EVERY ORDER THAT BUYER ASKED TO cancell"

domain/orders_view.to_item does `bool(it.get("BuyerRequestedCancel"))`. If Amazon
sends a JSON boolean that is right. If it sends the STRING "false" -- which is
what the Orders API v0 schema says for this field -- then bool("false") is True
in Python and EVERY order claims the buyer asked to cancel. Same shape question
for IsGift right beside it.

Read-only: it lists orders and their items and changes nothing.

    python probe_cancel_flag.py [account_id] [MARKETPLACE] [days]
"""
import datetime as dt
import json
import sys

sys.path.insert(0, r"D:\AltaScraper")

CONFIG = r"D:\AltaScraper\config.json"
FIELDS = ("BuyerRequestedCancel", "BuyerCancelReason", "IsGift",
          "IsTransparency", "SerialNumberRequired")


def main(account_id=None, marketplace="UK", days=14):
    from data import settings as _settings
    from domain import accounts as _acc
    import domain.orders_live as _ol
    from sp_api.api import Orders
    from sp_api.base import Marketplaces

    cfg = _settings.load(CONFIG)
    wss = cfg.get("workspaces") or []
    if account_id:
        wss = [w for w in wss if str(w.get("id")) == str(account_id)]
    if not wss:
        print("no account matched %r; known: %s"
              % (account_id, [w.get("id") for w in (cfg.get("workspaces") or [])]))
        return 1

    seen, n_items, shown = {}, 0, 0
    for acc in wss:
        creds = _acc.account_creds(acc)
        mkt = getattr(Marketplaces, marketplace, None) or Marketplaces.UK
        oc = Orders(credentials=creds, marketplace=mkt)
        start = dt.datetime.utcnow() - dt.timedelta(days=days)
        print("\n=== %s / %s ===" % (acc.get("id"), marketplace))
        try:
            orders, _ = _ol.fetch_since(marketplace, mkt.marketplace_id, creds,
                                        start)
        except Exception as e:
            print("  could not list orders:", str(e)[:170])
            continue
        print("  %d orders in the last %d days" % (len(orders), days))

        for o in orders[:15]:
            oid = str(o.get("AmazonOrderId") or "")
            try:
                r = oc.get_order_items(oid)
                pay = r.payload if hasattr(r, "payload") else (r or {})
                items = (pay or {}).get("OrderItems") or []
            except Exception as e:
                print("  %s: items failed: %s" % (oid, str(e)[:110]))
                continue
            for it in items:
                n_items += 1
                for f in FIELDS:
                    if f not in it:
                        continue
                    v = it.get(f)
                    key = (f, type(v).__name__, repr(v))
                    seen[key] = seen.get(key, 0) + 1
            if shown < 2 and items:
                shown += 1
                print("  RAW ITEM, order %s, status %s:"
                      % (oid, o.get("OrderStatus")))
                print("   ", json.dumps(items[0], indent=1)[:1000])

    print("\n" + "=" * 70)
    print("WHAT AMAZON SENDS   (%d item lines read)" % n_items)
    print("=" * 70)
    if not seen:
        print("  none of these fields came back on any line")
    for (f, t, v), n in sorted(seen.items()):
        note = ""
        if t == "str" and f in ("BuyerRequestedCancel", "IsGift",
                                "IsTransparency", "SerialNumberRequired"):
            # The point of the probe: a non-empty string is ALWAYS truthy.
            note = "   <-- bool(%s) == %s" % (v, bool(v.strip("'\"")))
        print("  %-24s %-5s %-12s x%-4d%s" % (f, t, v, n, note))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(main(a[0] if a else None,
                  a[1] if len(a) > 1 else "UK",
                  int(a[2]) if len(a) > 2 else 14))
