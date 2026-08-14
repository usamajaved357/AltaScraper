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
             included=("attributes", "summaries", "issues"), timeout=60):
    """What Amazon currently holds for this SKU. Never raises.

    -> {"status", "attributes", "product_type", "error", "http_code"}
    """
    out = {"status": FAILED, "attributes": None, "product_type": "",
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
    out["status"] = OK
    return out


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
