"""api/amazon_listings.py -- reading and PATCHING one live listing. Transport only.

WHY PATCH AND NOT PUT
amazon_listing_generator.py creates listings with putListingsItem, which replaces
the WHOLE item. Repricing must not do that: a full replace re-submits the title,
bullets, images and every compliance-sensitive attribute on every price change,
so a routine 20p adjustment would put the entire listing back through Amazon's
validation and could overwrite content that was fixed by hand in Seller Central.
patchListingsItem changes named attributes and leaves the rest alone.

WHY IT READS BEFORE IT WRITES
CLAUDE.md Rule 4: do not guess a schema. The exact shape of purchasable_offer
and fulfillment_availability varies by product type and marketplace, and an
invented shape is rejected -- or worse, accepted with the number in the wrong
field. So this fetches the attributes Amazon currently holds, and the caller
edits THAT structure and sends it back. The shape always comes from Amazon.

No rules and no decisions live here. Whether a price SHOULD change is
domain/sourcing.py; whether it is allowed to be pushed is domain/source_apply.py.
"""

OK     = "ok"
GONE   = "gone"        # Amazon does not have this SKU
FAILED = "failed"


def _enum(marketplace):
    from sp_api.base import Marketplaces
    code = str(marketplace or "UK").upper()
    if code == "US":
        return Marketplaces.US
    return getattr(Marketplaces, code, Marketplaces.UK)


def _client(creds, marketplace, timeout=60):
    from sp_api.api import ListingsItemsV20210801
    return ListingsItemsV20210801(credentials=creds, marketplace=_enum(marketplace),
                                  timeout=timeout)


def get_item(creds, marketplace, seller_id, sku, marketplace_id,
             included=("attributes", "summaries", "issues", "productTypes"),
             timeout=60):
    """What Amazon currently holds for this SKU. Never raises.

    -> {"status", "attributes", "product_type", "error", "http_code"}

    WHY productTypes IS ASKED FOR, and why leaving it out was a silent failure.

    The code below reads the product type from `summaries[0].productType` and
    falls back to `productTypes[0].productType`. The fallback existed but could
    never fire, because productTypes was not in the request -- Amazon only sends
    the sections you ask for.

    MEASURED on a live nestwell_goods listing (11.96_2Days_B0FM82BDC5, UK), with
    productTypes added to the request:

        summaries     []                                    <- empty
        productTypes  [{marketplaceId: A1F83G8C2ARO7P,
                        productType: "SQUEEGEE"}]            <- the answer

    So `product_type` came back as "" for every live listing on the account, and
    every caller that needs it was quietly broken:

      variations_routes  every merge reported "could not read the product type"
                         and could never be applied -- reported as "i am not
                         able to go to step 3"
      variant_routes     adding a variant to an existing listing
      source_apply       writing a price back needs the type on a full put

    One default, four callers, one fix. Nothing else in this file changes: the
    fallback that reads the value was already here and correct.
    """
    out = {"status": FAILED, "attributes": None, "product_type": "",
           "summaries": [], "issues": [],
           "error": "", "http_code": None, "raw": None}
    if not (seller_id and sku):
        out["error"] = "need a seller id and a sku"
        return out
    try:
        li = _client(creds, marketplace, timeout)
        res = li.get_listings_item(seller_id, sku,
                                   marketplaceIds=[marketplace_id],
                                   includedData=",".join(included))
        data = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        code = getattr(e, "code", None) or getattr(e, "status_code", None)
        out["http_code"] = code
        # 404 means the SKU is not on the account -- a fact, not a hiccup.
        out["status"] = GONE if code in (404,) else FAILED
        out["error"] = str(e)[:300]
        return out

    data = data or {}
    out["raw"] = data
    out["attributes"] = data.get("attributes") or {}
    summaries = data.get("summaries") or []
    if summaries and isinstance(summaries, list):
        out["product_type"] = str(summaries[0].get("productType") or "")
    if not out["product_type"]:
        pts = data.get("productTypes") or []
        if pts and isinstance(pts, list):
            out["product_type"] = str(pts[0].get("productType") or "")
    # SURFACED, not left buried in `raw`. Both are already asked for and both
    # answer questions the attributes cannot:
    #   summaries  what Amazon SERVES -- the rendition on the product page,
    #              which is re-hosted and never matches the URL submitted
    #   issues     what Amazon accepted and then took exception to, which is the
    #              only place a rejected image is ever mentioned
    # A caller reaching into out["raw"] for these is a caller writing the same
    # three lines again, differently (Rule 12).
    out["summaries"] = summaries if isinstance(summaries, list) else []
    out["issues"] = data.get("issues") or []
    out["status"] = OK
    return out


def catalogue(creds, marketplace, seller_id, marketplace_id,
              page_size=20, max_pages=200, timeout=60):
    """EVERY listing on the account, from Amazon's Listings API. Never raises.

    -> {"status", "items": [ ... ], "error", "http_code", "pages", "raw_count"}

    WHY THIS EXISTS -- IT REPLACES A REPORT.

        "if api gives more accurate data and quick use it instead of reports"

    The catalogue was built from GET_MERCHANT_LISTINGS_ALL_DATA merged with
    GET_MERCHANT_LISTINGS_INACTIVE_DATA. Measured on nestwell_goods/UK on
    7 Sep 2026, against the newest report Amazon held (built 14:05:24Z, an hour
    after the listing in question was created):

        report        39 listings   1 request, QUOTA'D (~1/min), minutes to build
                      -- and it did NOT contain 9.99_2Days_B0BP1HNW8G at all
        this call     40 listings   2 requests, ungated, 1.4-1.9 seconds
                      -- including that SKU, BUYABLE, £19.99, qty 10

    That gap is not a rounding error: it is the reported symptom. A listing
    Amazon had published an hour earlier could not be seen in the app however
    many times Sync was pressed, because the report Sync reads did not have it.

    IT ALSO CARRIES THE HANDLING TIME, which the report does not
    (dashboard.py:2765 says so, having dumped all 30 columns to check). The app
    fetches that per-SKU afterwards; from here it arrives in the same call.

    THE SHAPE IS _parse_listings_report's SHAPE, deliberately. Everything
    downstream -- the snapshot, the catalogue screen, the repricer -- already
    reads those keys, and a second shape would mean every reader learning which
    source it came from (Rule 12). Two adapters, one vocabulary.

    NOT EVERY ACCOUNT MAY USE THIS. Measured the same day: jack_uk, sheelady_us
    and selvora_limited all answer 403 Unauthorized, having no Listings role
    granted; only nestwell_goods succeeds. So this returns a status the caller
    must check, and the caller keeps the report path for the rest.
    """
    out = {"status": FAILED, "items": [], "error": "", "http_code": None,
           "pages": 0, "raw_count": 0}
    if not (seller_id and marketplace_id):
        out["error"] = "need a seller id and a marketplace id"
        return out
    raw = []
    token = None
    expected = None
    try:
        cl = _client(creds, marketplace, timeout=timeout)
        while True:
            kw = {"marketplaceIds": [marketplace_id],
                  "pageSize": int(page_size),
                  "includedData": ["summaries", "offers",
                                   "fulfillmentAvailability", "attributes"]}
            if token:
                kw["pageToken"] = token
            resp = cl.search_listings_items(seller_id, **kw)
            data = resp.payload if hasattr(resp, "payload") else (resp or {})
            raw.extend((data or {}).get("items") or [])
            out["pages"] += 1
            if expected is None:
                try:
                    expected = int((data or {}).get("numberOfResults"))
                except (TypeError, ValueError):
                    expected = None
            # WHERE THE NEXT PAGE TOKEN ACTUALLY IS. sp-api lifts `pagination`
            # out of the body and hands it back as `next_token`; the payload's
            # own pagination key comes through as null. Reading only the payload
            # stopped after ONE page and quietly returned 20 of 40 listings --
            # a half catalogue that looks exactly like a complete one, which is
            # the failure mode this whole change exists to remove.
            token = getattr(resp, "next_token", None)
            if not token:
                token = ((data or {}).get("pagination") or {}).get("nextToken")
            if not token or out["pages"] >= int(max_pages):
                break
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
        out["http_code"] = getattr(e, "code", None) or getattr(e, "status_code", None)
        return out
    # AMAZON SAYS HOW MANY THERE ARE. If we did not collect that many, say so
    # rather than returning a short list as though it were the catalogue -- the
    # caller keeps its previous snapshot instead of shrinking it.
    if expected is not None and len(raw) < expected:
        out["error"] = ("collected %d of %d listing(s) Amazon reported"
                        % (len(raw), expected))
        out["items"] = []
        return out
    out["raw_count"] = len(raw)
    out["expected"] = expected
    out["items"] = [_as_catalogue_row(i, marketplace_id) for i in raw]
    out["items"] = [i for i in out["items"] if i.get("sku")]
    out["status"] = OK
    return out


# Amazon's product-id types that are actually barcodes. An ASIN or an ISBN
# printed under the word EAN is worse than the blank it replaces -- the same
# rule dashboard.py applies to the report's product-id-type column.
_BARCODE_TYPES = {"ean", "upc", "gtin", "gcid", "isbn13"}


def _first(attrs, key, field="value"):
    """The first scalar of a Listings attribute, or "". Attributes arrive as
    [{"value": x, "marketplace_id": ...}] and a missing one must not raise."""
    v = (attrs or {}).get(key)
    if not isinstance(v, list) or not v:
        return ""
    e = v[0]
    if isinstance(e, dict):
        return str(e.get(field, "") or "")
    return str(e or "")


def _as_catalogue_row(item, marketplace_id):
    """One API listing -> the dict _parse_listings_report produces.

    Kept beside the call rather than in the route, because the mapping is a fact
    about Amazon's reply shape, not a decision about what to show.
    """
    s = (item.get("summaries") or [{}])[0] or {}
    attrs = item.get("attributes") or {}
    offers = item.get("offers") or []
    avail = item.get("fulfillmentAvailability") or []

    price = ""
    if offers:
        p = offers[0].get("price") or {}
        price = str(p.get("amount", "") or "")

    qty, channel, handling = "", "", ""
    if avail:
        a0 = avail[0] or {}
        q = a0.get("quantity")
        qty = "" if q is None else str(q)
        channel = str(a0.get("fulfillmentChannelCode", "") or "")
    # The handling time the report has never carried. It is on the ATTRIBUTE,
    # not on the fulfillmentAvailability summary, which is why asking for
    # attributes is worth the payload.
    fa = attrs.get("fulfillment_availability")
    if isinstance(fa, list) and fa and isinstance(fa[0], dict):
        lt = fa[0].get("lead_time_to_ship_max_days")
        handling = "" if lt is None else str(lt)
        if not channel:
            channel = str(fa[0].get("fulfillment_channel_code", "") or "")

    # BUYABLE is the only status that means somebody can buy it. DISCOVERABLE
    # alone is a product page with no offer attached -- see the verify branch in
    # amazon_listing_generator.py, where treating the two as one put a green row
    # on screen for a listing nobody could purchase.
    statuses = [str(x).upper() for x in (s.get("status") or [])]
    status = "Active" if "BUYABLE" in statuses else "Inactive"

    barcode = ""
    ident = attrs.get("externally_assigned_product_identifier")
    if isinstance(ident, list) and ident and isinstance(ident[0], dict):
        if str(ident[0].get("type", "") or "").lower() in _BARCODE_TYPES:
            barcode = str(ident[0].get("value", "") or "")

    return {
        "sku":   str(item.get("sku", "") or ""),
        "asin":  str(s.get("asin", "") or ""),
        "title": str(s.get("itemName", "") or ""),
        "price": price,
        "qty":   qty,
        "status": status,
        "brand": _first(attrs, "brand"),
        "fulfillment": channel,
        "ship_group": _first(attrs, "merchant_shipping_group"),
        "barcode": barcode,
        # NOT IN THE REPORT'S SHAPE, and additive on purpose: a reader that does
        # not know about it is unaffected, and the one that does is spared a
        # per-SKU getListingsItem for every listing on the account.
        "handling_time": handling,
        # What Amazon literally said, kept so a screen can tell "page created,
        # no offer" from "suppressed" without asking Amazon again.
        "amazon_status": statuses,
    }


def put(creds, marketplace, seller_id, sku, marketplace_id, product_type,
        attributes, issue_locale="en_GB", timeout=90):
    """Create or fully replace a listing. Never raises.

    Used for a VARIATION PARENT, which does not exist until it is made. Always
    requirements="LISTING" -- a new product under our own brand, per CLAUDE.md
    Rule 1. Never LISTING_OFFER_ONLY, and no merchant_suggested_asin: a parent is
    a container for our own children, not an offer on somebody else's ASIN.
    """
    out = {"status": FAILED, "submission_id": "", "amazon_status": "",
           "issues": [], "error": ""}
    if not product_type:
        out["error"] = "no product type"
        return out
    try:
        li = _client(creds, marketplace, timeout)
        res = li.put_listings_item(
            seller_id, sku,
            marketplaceIds=[marketplace_id],
            body={"productType": product_type,
                  "requirements": "LISTING",
                  "attributes": attributes or {}},
            issueLocale=issue_locale)
        data = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        out["error"] = str(e)[:300]
        return out

    data = data or {}
    out["submission_id"] = str(data.get("submissionId") or "")
    out["amazon_status"] = str(data.get("status") or "")
    out["issues"] = list(data.get("issues") or [])
    out["status"] = OK if out["amazon_status"].upper() == "ACCEPTED" else FAILED
    if out["status"] != OK and not out["error"]:
        out["error"] = "Amazon answered %s" % (out["amazon_status"] or "nothing")
    return out


def patch(creds, marketplace, seller_id, sku, marketplace_id, product_type,
          patches, issue_locale="en_GB", timeout=60):
    """Send a patch. Never raises. Returns Amazon's verdict, not our hope of it.

    -> {"status", "submission_id", "amazon_status", "issues", "error"}

    A patch is ACCEPTED or INVALID synchronously; publication is asynchronous, so
    ACCEPTED means Amazon took it, not that it is live yet. The caller records
    what Amazon said rather than assuming success -- an INVALID that we logged as
    applied would leave the app believing a price it never set.
    """
    out = {"status": FAILED, "submission_id": "", "amazon_status": "",
           "issues": [], "error": ""}
    if not patches:
        out["error"] = "nothing to patch"
        return out
    if not product_type:
        out["error"] = "no product type -- Amazon rejects a patch without one"
        return out
    try:
        li = _client(creds, marketplace, timeout)
        res = li.patch_listings_item(
            seller_id, sku,
            marketplaceIds=[marketplace_id],
            body={"productType": product_type, "patches": patches},
            issueLocale=issue_locale)
        data = res.payload if hasattr(res, "payload") else res
    except Exception as e:
        out["error"] = str(e)[:300]
        return out

    data = data or {}
    out["submission_id"] = str(data.get("submissionId") or "")
    out["amazon_status"] = str(data.get("status") or "")
    out["issues"] = list(data.get("issues") or [])
    # ACCEPTED is the only answer that means Amazon took it.
    out["status"] = OK if out["amazon_status"].upper() == "ACCEPTED" else FAILED
    if out["status"] != OK and not out["error"]:
        out["error"] = "Amazon answered %s" % (out["amazon_status"] or "nothing")
    return out
