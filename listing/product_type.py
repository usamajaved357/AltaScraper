"""listing/product_type.py -- every listing knows what Amazon calls it.

THE PROBLEM, IN THE OWNER'S WORDS:

    "but why are we having products with no product type, the app should be
     able to pull the product type of the items, dont skip compliance checks"

MEASURED, on his own database: 32 of 303 listings have no product_type. All 32
are on jack_uk; 30 are GENERATED, one is a variation PARENT and one is QUEUED.
Their SKUs carry eBay item ids (336475288886) where an ASIN would be, so there
was never an ASIN to read a type from, and the paths that made them -- the
variation children, the parent row, the Miles rows -- did not infer one either.

WHY A BLANK IS NOT HARMLESS. The compliance gate reads product_type to decide
whether a category can apply to this product at all. With no type it cannot
decide, and the choice is between flagging things that are not electrical and
missing things that are. Two of those 32 are "12V 10A AC to DC Adapter 120W
Power Supply" and "100W Rechargeable LED Work Light" -- both genuinely
electrical, both with an electrical flag resting on a field that is empty.

The answer is not to change how the gate treats a blank. It is to stop having
blanks.

WHERE THE ANSWER COMES FROM, BEST FIRST

  1. what the row already says          -- never overwritten
  2. Amazon, for a listing that is live -- its own answer, not ours
  3. the title                          -- infer_product_type, one shared rule
                                           set (CLAUDE.md Rule 12)

AND "HOME" IS NOT AN ANSWER. infer_product_type falls back to "HOME" so that a
submit always has a real type to send. Writing that onto a row is a different
act: the gate would then read "HOME" as a FACT about the product, and for the
12V power supply above that would turn its electrical check off -- the exact
failure this module exists to prevent. So nothing is stored unless a rule
actually matched, and a row we cannot type stays blank.
"""
import json


def from_title(title, comp_data=None):
    """The type the title implies, or "" if nothing matched.

    Deliberately thin: the rules live in amazon_listing_generator's
    _PT_INFER_RULES, which is also what the generator uses when it creates a
    listing, so a type inferred here and a type inferred there cannot differ.
    """
    try:
        from amazon_listing_generator import infer_product_type
    except Exception:
        return ""
    return infer_product_type(dict(comp_data or {}), item_name=str(title or ""),
                              default="") or ""


def from_amazon(config_path, account, marketplace, sku):
    """What Amazon itself calls this SKU. "" when it cannot say.

    Only useful for a listing that is actually on Amazon. Goes through
    api/amazon_listings, which is the one place that knows how to fetch a live
    listing -- including productTypes in includedData, without which
    product_type comes back empty for every live listing (Rule 12).
    """
    try:
        import accounts as _acc
        from api import amazon_listings as _al
    except Exception:
        return ""
    try:
        got = _al.get_item(_acc.account_creds(account), marketplace,
                           str(account.get("seller_id") or ""), sku,
                           _acc.marketplace_id(marketplace) or "")
    except Exception:
        return ""
    if not isinstance(got, dict) or got.get("status") != getattr(_al, "OK", "ok"):
        return ""
    return str(got.get("product_type") or "").strip()


def resolve(row, comp_data=None):
    """The product type for one row, without asking Amazon. "" if unknown."""
    have = str((row or {}).get("product_type") or "").strip()
    if have:
        return have
    # The attributes the generator stored are a better haystack than the title
    # alone -- item_type_keyword and the browse nodes are in there.
    cd = dict(comp_data or {})
    if not cd:
        try:
            cd = json.loads(str((row or {}).get("attributes_json") or "") or "{}")
            if not isinstance(cd, dict):
                cd = {}
            cd = {"attributes": cd}
        except Exception:
            cd = {}
    return from_title((row or {}).get("title") or "", cd)


def backfill(config_path, workspace_id):
    """Fill in the blanks for one workspace. Returns (blank_before, filled).

    NOTHING WITH A TYPE IS TOUCHED, and nothing is invented: a row whose title
    matches no rule is left blank, because a wrong type is worse than none --
    it is the difference between "we do not know" and a false statement the
    compliance gate will act on.

    Safe to run on every recompute; a row it cannot type simply stays blank and
    is tried again next time, which is what should happen after a Sync brings
    Amazon's own answer in.
    """
    from data import db as _db

    conn = _db.get_db(config_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT sku, title, product_type, attributes_json FROM listings "
        "WHERE workspace_id=? AND COALESCE(product_type,'')=''", (workspace_id,))]
    if not rows:
        return 0, 0

    filled = 0
    for r in rows:
        pt = resolve(r)
        if not pt:
            continue
        conn.execute(
            "UPDATE listings SET product_type=? WHERE workspace_id=? AND sku=?",
            (pt, workspace_id, r.get("sku")))
        filled += 1
    if filled:
        conn.commit()
    return len(rows), filled


def still_blank(config_path, workspace_id):
    """The SKUs that even the title could not type, so a screen can say so
    rather than leaving the field quietly empty."""
    from data import db as _db
    try:
        conn = _db.get_db(config_path)
        return [r[0] for r in conn.execute(
            "SELECT sku FROM listings WHERE workspace_id=? "
            "AND COALESCE(product_type,'')=''", (workspace_id,))]
    except Exception:
        return []
