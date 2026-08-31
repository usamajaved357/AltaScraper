"""api/amazon_metrics.py -- the two figures the database does not already hold.

Transport only. No rules, no decisions, no caching -- that is
data/metrics_cache.py, and what to do with the numbers is
domain/listing_metrics.py.

WHY SO LITTLE IS HERE

Most of what the listings page shows is already in the database and is read
locally (see domain/listing_metrics.py for the measurements). Exactly two things
are not, and only they are fetched:

    sales rank        getCatalogItem, salesRanks -- nothing local records it
    lowest price      getCompetitivePricing -- listings.buy_box_price is the
                      competitor's price captured at GENERATION time, which is
                      a different question from what the market is today

A third, inbound/reserved stock, is NOT here on purpose: domain/inventory_module
.fetch_fba_inventory already pulls exactly that per SKU, with a documented
reason for using the Inventories API over the Reports API (the report role is
not granted on this account). A second FBA fetcher would be the same call
written twice (CLAUDE.md Rule 12).

THE SHAPES ARE THE ONES AMAZON REALLY RETURNS, read off the working code in
amazon_listing_generator.py rather than from memory (Rule 4):

    salesRanks[].classificationRanks[] -> {title, rank}
    salesRanks[].displayGroupRanks[]   -> {title, rank}
    CompetitivePricing.CompetitivePrices[] where CompetitivePriceId == "1"
      -> Price.LandedPrice.Amount            (the buy box)

NOTHING HERE RAISES. Every function returns a dict carrying either the answer or
the reason there is none, because "Amazon refused" and "there is no rank" lead
to opposite conclusions on screen and must not arrive as the same empty value.
This account's SP-API roles have been partial before -- the catalogue call has a
documented fallback for exactly that -- so a refusal is an expected answer, not
an exception.
"""

OK = "ok"
FAILED = "failed"


def _enum(marketplace):
    from sp_api.base import Marketplaces
    code = str(marketplace or "UK").upper()
    return getattr(Marketplaces, code, Marketplaces.UK)


def sales_rank(creds, marketplace, marketplace_id, asin, timeout=30):
    """The listing's best sales rank. Never raises.

    -> {"status", "rank", "category", "ranks": [...], "error"}

    `rank` is the SMALLEST rank across every classification Amazon reports,
    because that is the one Seller Central shows and the one a person means by
    "my rank". All of them come back in `ranks` so nothing is thrown away.
    """
    out = {"status": FAILED, "rank": None, "category": "", "ranks": [], "error": ""}
    if not asin:
        out["error"] = "no asin"
        return out
    try:
        from sp_api.api import CatalogItems
    except Exception as e:
        out["error"] = "sp_api CatalogItems not available: %s" % e
        return out
    try:
        cat = CatalogItems(credentials=creds, marketplace=_enum(marketplace),
                           timeout=timeout)
        res = cat.get_catalog_item(asin=asin, includedData=["salesRanks"],
                                   marketplaceIds=[marketplace_id])
        p = res.payload if hasattr(res, "payload") else (res or {})
    except Exception as e:
        out["error"] = str(e)[:250]
        return out

    ranks = []
    for sr in (p or {}).get("salesRanks", []) or []:
        for r in (sr.get("classificationRanks") or []) + (sr.get("displayGroupRanks") or []):
            try:
                n = int(r.get("rank"))
            except (TypeError, ValueError):
                continue
            title = str(r.get("title") or r.get("classificationName") or "")
            ranks.append({"rank": n, "category": title})
    ranks.sort(key=lambda x: x["rank"])
    out["ranks"] = ranks
    out["status"] = OK
    if ranks:
        out["rank"] = ranks[0]["rank"]
        out["category"] = ranks[0]["category"]
    # No ranks is a real answer -- a product that has never sold has none -- so
    # this stays status OK with rank None, NOT an error.
    return out


def competitive_price(creds, marketplace, marketplace_id, asin, timeout=30):
    """What the market is charging for this ASIN right now. Never raises.

    -> {"status", "buy_box_price", "offer_count", "error"}

    The buy box is CompetitivePriceId "1"; its LandedPrice is what a shopper
    actually pays, price plus shipping, which is the number worth comparing our
    own price against.
    """
    out = {"status": FAILED, "buy_box_price": None, "offer_count": None, "error": ""}
    if not asin:
        out["error"] = "no asin"
        return out
    try:
        from sp_api.api import ProductPricing
    except Exception as e:
        out["error"] = "sp_api ProductPricing not available: %s" % e
        return out
    try:
        pricing = ProductPricing(credentials=creds, marketplace=_enum(marketplace),
                                 timeout=timeout)
        comp = pricing.get_competitive_pricing_for_asins(asin_list=[asin])
        items = comp.payload if isinstance(getattr(comp, "payload", None), list) else []
    except Exception as e:
        out["error"] = str(e)[:250]
        return out

    for item in items:
        product = (item or {}).get("Product", {}) or {}
        cp_block = product.get("CompetitivePricing", {}) or {}
        for cp in cp_block.get("CompetitivePrices", []) or []:
            if str(cp.get("CompetitivePriceId")) == "1":
                try:
                    out["buy_box_price"] = float(
                        ((cp.get("Price") or {}).get("LandedPrice") or {}).get("Amount"))
                except (TypeError, ValueError):
                    pass
        n = 0
        seen = False
        for o in cp_block.get("NumberOfOfferListings", []) or []:
            if str(o.get("condition", "")).lower() == "new":
                try:
                    n += int(o.get("Count") or 0)
                    seen = True
                except (TypeError, ValueError):
                    pass
        if seen:
            out["offer_count"] = n
    out["status"] = OK
    return out
