"""probe_ebay.py -- show what eBay ACTUALLY returns for one item, and what we made of it.

CLAUDE.md Rule 4: do not guess a field name or a container shape. Read the raw
response and build the parser from what it literally says.

One field in domain/source_fetch.py is inferred rather than read -- dispatch_days
comes from an estimated DELIVERY date, because the Browse API item response has
no handling-time field. This is how to check that against a real item, and to
confirm the postage and stock fields are where we think they are.

    python probe_ebay.py https://www.ebay.co.uk/itm/123456789012
    python probe_ebay.py 123456789012 --raw       (the whole JSON)

Credentials come from config.json (ebay_app_id / ebay_cert_id), the same ones
the generator uses. Nothing is written and nothing is sent to Amazon.
"""
import json
import sys

sys.path.insert(0, r"D:\AltaScraper")

from api import ebay as _ebay
from domain import source_fetch as _sf


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    want_raw = "--raw" in argv
    if not args:
        print(__doc__)
        return 2

    try:
        cfg = json.load(open("config.json", encoding="utf-8"))
    except Exception as e:
        print("could not read config.json: %s" % e)
        return 1
    app_id = str(cfg.get("ebay_app_id", "") or "")
    cert_id = str(cfg.get("ebay_cert_id", "") or "")
    if not (app_id and cert_id):
        print("no eBay credentials in config.json (ebay_app_id / ebay_cert_id)")
        return 1

    res = _ebay.get_item(args[0], app_id, cert_id)
    print("status    : %s" % res["status"])
    print("item id   : %s" % res["item_id"])
    if res["http_code"]:
        print("http      : %s" % res["http_code"])
    if res["error"]:
        print("error     : %s" % res["error"])
    if res["status"] != _ebay.OK:
        if res["status"] == _ebay.GONE:
            print("\n-> eBay says this listing has ENDED. The repricer treats that as a "
                  "fact about the world, not as a failure to look.")
        return 0

    data = res["data"]
    print("\n--- the fields we read ---")
    for key in ("price", "shippingOptions", "estimatedAvailabilities"):
        print("%s:\n%s\n" % (key, json.dumps(data.get(key), indent=2)[:1500]))

    print("--- what our parser made of it ---")
    got = _sf.from_ebay_item(data)
    for k in ("status", "price", "shipping", "currency", "in_stock", "dispatch_days"):
        print("  %-14s %r" % (k, got.get(k)))
    if got.get("shipping") is None:
        print("\n  NOTE: postage came back unknown. Either eBay quoted CALCULATED "
              "postage (needs a destination postcode) or there was none in the "
              "response. Set a shipping_override on the source rather than letting "
              "it be costed at zero.")
    if got.get("dispatch_days") is None:
        print("\n  NOTE: no delivery estimate in the response, so dispatch is unknown. "
              "That only blocks the source if max_dispatch_days is set.")

    if want_raw:
        print("\n--- the whole response ---")
        print(json.dumps(data, indent=2)[:200000])
    else:
        print("\n(run with --raw to dump the whole response)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
