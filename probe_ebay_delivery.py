"""probe_ebay_delivery.py -- what eBay actually tells us about delivery.

    python probe_ebay_delivery.py [item-url-or-id] [POSTCODE]

WHY THIS EXISTS (CLAUDE.md Rule 4, applied to eBay rather than Amazon)
The Order details screen is meant to show, for each supplier link:

    the carrier            "Royal Mail Tracked 48"     -- when there is one
    the postage as written  "Free delivery in 2-3 days" -- when there is not
    the delivery estimate  "between Wed 19 and Mon 24 Aug"

Every one of those is on the eBay page under the buy button. None of them is
necessarily in the API response, and the API is what we have. So this asks for a
real item and prints the shipping block VERBATIM, twice:

    without a destination postcode   -- what the app asks for today
    with one                         -- via X-EBAY-C-ENDUSERCTX

and reports which fields appear only in the second. eBay's estimates are
computed to a destination; asking without one may get no estimate at all, which
would mean the app cannot show a delivery date until it starts sending the
postcode.

Guessing the field names off the documentation is what Rule 4 forbids. This
prints them.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, r"D:\AltaScraper")

DEFAULT_POSTCODE = "BH166FH"


def creds():
    import dashboard as D
    cfg = D._cfg()
    for key in ("ebay", "ebay_api", "sourcing"):
        blk = cfg.get(key) or {}
        if isinstance(blk, dict) and (blk.get("app_id") or blk.get("client_id")):
            return (blk.get("app_id") or blk.get("client_id"),
                    blk.get("cert_id") or blk.get("client_secret"))
    return cfg.get("ebay_app_id", ""), cfg.get("ebay_cert_id", "")


def a_source_url():
    """A real supplier link the app is already tracking, so the item exists."""
    import dashboard as D
    from data import db as _db
    conn = _db.get_db(D.CONFIG_PATH)
    # A source that read OK last time it was checked, so the probe is not
    # measuring an ended listing. sourcing_sources holds the links;
    # sourcing_checks holds what each one answered.
    for r in conn.execute(
            "SELECT s.url FROM sourcing_sources s "
            "  JOIN sourcing_checks c ON c.source_id = s.id "
            " WHERE s.kind='ebay' AND c.status='fetched' "
            " ORDER BY c.checked_at DESC LIMIT 1").fetchall():
        return r["url"]
    for r in conn.execute(
            "SELECT url FROM sourcing_sources WHERE kind='ebay' LIMIT 1"
            ).fetchall():
        return r["url"]
    return ""


def fetch(item_id, tok, marketplace="EBAY_GB", postcode=None):
    """One getItem call. Returns (http_code, data_or_error_text).

    THE LEGACY ENDPOINT, which is what api/ebay.py uses for a plain listing. A
    URL carries eBay's OLD numeric id (186107152290); /buy/browse/v1/item/{id}
    wants the NEW opaque one and answers 400 to an old one. The first run of this
    probe hit exactly that and reported "no shippingOptions" for an item that has
    them -- an HTTP 400 read as an answer about delivery.
    """
    url = ("https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id"
           "?legacy_item_id=" + urllib.parse.quote(str(item_id)))
    headers = {
        "Authorization": "Bearer " + tok,
        "X-EBAY-C-MARKETPLACE-ID": marketplace,
        "Accept": "application/json",
    }
    if postcode:
        # THE HEADER THE APP DOES NOT SEND TODAY. eBay computes a delivery
        # estimate to a destination; with no destination there is nothing to
        # compute. country and zip, comma separated, exactly as documented --
        # and this probe exists to find out whether it changes the answer.
        headers["X-EBAY-C-ENDUSERCTX"] = (
            "contextualLocation=country%%3DGB%%2Czip%%3D%s" % postcode)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return None, {"error": "%s: %s" % (type(e).__name__, e)}


def show(label, data):
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)
    if not isinstance(data, dict):
        print("  no dict back: %r" % (data,))
        return {}
    opts = data.get("shippingOptions")
    if opts is None:
        print("  NO shippingOptions KEY AT ALL")
        return {}
    if not opts:
        print("  shippingOptions is an empty list")
        return {}
    # A LIST, not a merged dict. The first version of this collapsed all three
    # options into one dict, so the comparison below only ever saw the LAST
    # option -- and reported "nothing changed" while option[0]'s delivery date
    # had moved by three days. A probe that misreports its own evidence is worse
    # than no probe.
    out = []
    for i, o in enumerate(opts):
        print("\n  --- shippingOptions[%d] ---" % i)
        for k in sorted(o.keys()):
            print("    %-34s %s" % (k, json.dumps(o[k])))
        out.append(dict(o))
    return out


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    postcode = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_POSTCODE
    from api import ebay as _ebay

    app_id, cert_id = creds()
    if not app_id:
        print("no eBay credentials in config.json -- cannot probe")
        return 1

    src = arg or a_source_url()
    if not src:
        print("no eBay item to probe. Pass a URL or an item id:")
        print("    python probe_ebay_delivery.py https://www.ebay.co.uk/itm/1234...")
        return 1
    # item_id_from_URL. Guessing the name got a function that does not exist and
    # a silent fall-through to the whole URL, which is what produced the 400.
    item_id = _ebay.item_id_from_url(src) if "/" in str(src) else str(src)
    if not item_id:
        print("could not read an item id out of: %s" % src[:120])
        return 1
    print("item: %s   (from %s)" % (item_id, src[:70]))

    tok = _ebay.token(app_id, cert_id)
    if not tok:
        print("could not get an eBay token")
        return 1

    code_a, data_a = fetch(item_id, tok)
    print("\nwithout a postcode: HTTP %s" % code_a)
    a = show("WITHOUT a destination postcode (what the app sends today)", data_a)

    code_b, data_b = fetch(item_id, tok, postcode=postcode)
    print("\nwith postcode %s: HTTP %s" % (postcode, code_b))
    b = show("WITH X-EBAY-C-ENDUSERCTX zip=%s" % postcode, data_b)

    print("\n" + "=" * 70)
    print("WHAT THE POSTCODE ADDS")
    print("=" * 70)
    # OPTION BY OPTION, matched by position. eBay returns them in the same order
    # both times here; if that ever stops being true this prints a mismatch
    # rather than a quiet wrong comparison.
    if len(a) != len(b):
        print("  DIFFERENT NUMBER OF OPTIONS: %d without, %d with" % (len(a), len(b)))
    for i in range(max(len(a), len(b))):
        oa, ob = (a[i] if i < len(a) else {}), (b[i] if i < len(b) else {})
        only = [k for k in ob if k not in oa]
        chg = [k for k in ob if k in oa and ob[k] != oa[k]]
        print("\n  option[%d] %s" % (i, ob.get("shippingServiceCode") or "?"))
        print("    only with a postcode: %s" % (only or "none"))
        print("    changed:              %s" % (chg or "none"))
        for k in chg:
            print("      %-28s %s  ->  %s"
                  % (k, json.dumps(oa[k]), json.dumps(ob[k])))

    print("\n  --- the things the screen needs, per option ---")
    for i, ob in enumerate(b):
        cost = (ob.get("shippingCost") or {}).get("value")
        print("    [%d] %-22s carrier=%-10s cost=%-6s %s -> %s"
              % (i, ob.get("shippingServiceCode") or "?",
                 ob.get("shippingCarrierCode") or "-",
                 cost if cost is not None else "-",
                 str(ob.get("minEstimatedDeliveryDate"))[:10],
                 str(ob.get("maxEstimatedDeliveryDate"))[:10]))
    missing = [w for w, k in (("carrier", "shippingServiceCode"),
                              ("postage cost", "shippingCost"),
                              ("delivery window", "maxEstimatedDeliveryDate"))
               if not any(k in o for o in b)]
    print("    NOT RETURNED BY ANY OPTION: %s" % (missing or "nothing -- all present"))

    # The item's own handling/dispatch statement, which is not in shippingOptions.
    print("\n  --- elsewhere in the item ---")
    for k in ("estimatedAvailabilities", "shipToLocations", "returnTerms",
              "sellerItemRevision", "itemLocation"):
        if k in (data_b or {}):
            print("    %s: %s" % (k, json.dumps(data_b[k])[:300]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
