"""api/amazon_catalog.py -- what Amazon's catalogue already has. Transport only.

ONE QUESTION: does this barcode already belong to a product?

    "if a draft or the live listing or the deleted listing or anywhere which
     holds information and from where it can detect this barcode is already
     assosiated to this, it should flag in advance"

domain/barcode_clash answers that from the app's OWN rows and always has. What
it cannot see is Amazon, and Amazon is where the collision actually happens:

    MEASURED, 8 Sep 2026. nestwell_goods/11.96_2Days_B0FM82BDC5 was refused with
    code 8541. Its barcode 4545944574867 already belongs to B0H8SYL36V -- which
    is jack_uk/5.98_3Days_B0F7RQLCKC, LIVE on UK, a car headrest pillow. The
    app's own clash check returned nothing, because the app's rows do not record
    that barcode against the jack_uk listing. Amazon knew all along.

WHAT THE SEARCH ACTUALLY COVERS, because it matters and is easy to overstate:

    ONE MARKETPLACE AT A TIME. marketplaceIds is required and the answer is
    scoped to it. Measured with the same barcode: UK returned B0H8SYL36V, DE
    returned nothing. So a UK listing is checked against the UK catalogue and
    says nothing about Germany.

    THE WHOLE CATALOGUE OF THAT MARKETPLACE, not just this seller's listings.
    Any seller's product that owns the code is found, which is the point -- a
    bought or reused EAN usually belongs to somebody else entirely.

NOT EVERY ACCOUNT MAY ASK. Measured the same day: jack_uk, sheelady_us and
selvora_limited all answer 403 Unauthorized on this API; only nestwell_goods
succeeds. So a refusal here is ordinary, not exceptional, and the caller must
treat "could not check" as its own answer rather than as "the barcode is free".

AND NOTHING FOUND IS NOT PROOF THE BARCODE IS FREE.

    MEASURED 8 Sep 2026, and it corrected this file's first wording within a
    day. Barcode 4545987573490 on 7.96_3Days_B0841BD4JY returned
    numberOfResults 0 here, and getCatalogItem on the ASIN Amazon later named
    -- B0H95D18GP -- answered 404 NOT_FOUND in that marketplace. A Preview then
    matched the barcode straight to it, refusing with code 8541.

Amazon's LISTING matcher can see ASINs its public CATALOGUE will not return:
suppressed ones, unpublished ones, and ones deleted since -- which is precisely
what an earlier attempt at the same product leaves behind, and therefore the
most likely kind to collide with. This catches a barcode belonging to a product
that is findable; it cannot catch one belonging to a ghost, and callers must not
word their answer as though it could. Preview remains the final check.
"""

OK = "ok"
NONE = "none"          # asked, and Amazon has nothing with this barcode
DENIED = "denied"      # this account may not ask
FAILED = "failed"      # could not ask -- never means the barcode is free


def _enum(marketplace):
    from sp_api.base import Marketplaces
    code = str(marketplace or "UK").upper()
    if code == "US":
        return Marketplaces.US
    return getattr(Marketplaces, code, Marketplaces.UK)


# Amazon's own name for each kind of code. normalize_gtin gives us "ean"/"upc";
# the catalogue search wants them upper case, and only accepts these four.
_TYPES = {"EAN": "EAN", "UPC": "UPC", "ISBN": "ISBN", "GTIN": "EAN",
          "JAN": "JAN", "GCID": "EAN"}


def owners_of_barcode(creds, marketplace, marketplace_id, barcode,
                      barcode_type="EAN", timeout=30):
    """Which products in this marketplace's catalogue carry this barcode.

    -> {"status", "items": [{"asin", "brand", "title"}], "error"}

    NEVER RAISES, and never answers "free" when it could not look. A network
    blip or a missing role returns FAILED/DENIED, which the caller reports as
    "could not check" -- saying a barcode is unused because the check itself
    broke is the one wrong answer here, since it is the answer that lets the
    submit go ahead.
    """
    out = {"status": FAILED, "items": [], "error": ""}
    code = str(barcode or "").strip()
    if not (code and marketplace_id):
        out["error"] = "need a barcode and a marketplace"
        return out
    kind = _TYPES.get(str(barcode_type or "EAN").upper(), "EAN")
    try:
        # THE VERSIONED CLIENT, explicitly. `CatalogItems` in this library is
        # the older 2020-12-01 shape; 2022-04-01 is the one that takes
        # identifiers/identifiersType and returns summaries with a brand.
        from sp_api.api import CatalogItemsV20220401
        cl = CatalogItemsV20220401(credentials=creds,
                                   marketplace=_enum(marketplace),
                                   timeout=timeout)
        res = cl.search_catalog_items(
            identifiers=[code], identifiersType=kind,
            marketplaceIds=[marketplace_id],
            includedData=["summaries"])
        data = res.payload if hasattr(res, "payload") else (res or {})
    except Exception as e:
        code_n = getattr(e, "code", None) or getattr(e, "status_code", None)
        name = type(e).__name__.lower()
        if code_n == 403 or "forbidden" in name or "unauthorized" in str(e).lower():
            out["status"] = DENIED
            out["error"] = "this account may not read Amazon's catalogue"
            return out
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:180])
        return out

    for it in ((data or {}).get("items") or []):
        s = (it.get("summaries") or [{}])[0] or {}
        out["items"].append({
            "asin": str(it.get("asin") or ""),
            "brand": str(s.get("brand") or ""),
            "title": str(s.get("itemName") or ""),
        })
    out["status"] = OK if out["items"] else NONE
    return out
