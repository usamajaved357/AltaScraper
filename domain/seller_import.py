"""domain/seller_import.py -- an eBay seller's catalogue, reviewed, then drafted.

THE SHAPE OF IT
    find      every item of one seller's we can locate
    review    you see each one with its main image and untick what you do not want
    screen    the ticked ones are checked against Amazon BEFORE anything is drafted
    draft     what survives becomes a draft in this app, not a listing on Amazon

Nothing here reaches Amazon. Drafting puts rows in front of you; publishing them
is the approve-and-submit path that already exists, unchanged.

WHAT "FOUND" MEANS, AND WHAT IT DOES NOT
eBay has no "list this seller's inventory" call -- a seller filter alone is
rejected outright, so api/ebay.search_seller unions several searches. The result
is everything those searches found, which is not provably everything the seller
has. Every count this module produces carries that with it, and the screen says
"found N" rather than "N items". Presenting a partial sweep as a whole catalogue
is how items go missing with nobody ever noticing they did.

WHY SCREENING HAPPENS BEFORE DRAFTING, NOT AFTER
A draft that can never be published is worse than no draft: it costs the AI spend
to generate, sits in the queue looking like work, and only fails at submit --
by which time the money is gone and the reason is a rejection message. Asking
Amazon first is cheap.

RULE 1 HOLDS THROUGHOUT
These become NEW listings under our own brands. The eBay item is a SOURCE -- it
supplies the product data and, through the repricer, the price and stock we track
it by. It is not an offer we are joining, and nothing here sends a
merchant_suggested_asin or asks for LISTING_OFFER_ONLY.
"""

# What a screened item may come back as. Ordered worst to best, because the
# summary reports the worst outcome across a batch.
BLOCKED = "blocked"      # Amazon will not let this account list it
DOCS = "docs"            # listable, but paperwork will be demanded
CAUTION = "caution"      # a rule of ours says look before leaping
UNKNOWN = "unknown"      # we could not find out -- NOT the same as fine
CLEAR = "clear"

_ORDER = {BLOCKED: 0, DOCS: 1, CAUTION: 2, UNKNOWN: 3, CLEAR: 4}


def _money(node):
    try:
        return round(float((node or {}).get("value")), 2)
    except (TypeError, ValueError):
        return None


def to_review_row(summary):
    """One eBay search result -> the row the review grid draws.

    The main image is the point of this screen: a title alone is not enough to
    decide whether you want to sell something, and a grid of titles gets ticked
    through without being read.
    """
    s = summary or {}
    img = (s.get("image") or {}).get("imageUrl") or ""
    if not img:
        thumbs = s.get("thumbnailImages") or []
        if thumbs and isinstance(thumbs[0], dict):
            img = thumbs[0].get("imageUrl") or ""
    ship = None
    for opt in (s.get("shippingOptions") or []):
        c = (opt or {}).get("shippingCost")
        if isinstance(c, dict):
            ship = _money(c)
            break
    cats = [c.get("categoryName") for c in (s.get("categories") or [])
            if isinstance(c, dict) and c.get("categoryName")]
    group = str(s.get("itemGroupType") or "")
    return {
        "item_id": str(s.get("legacyItemId") or s.get("itemId") or ""),
        "title": str(s.get("title") or ""),
        "image": img,
        "price": _money(s.get("price")),
        "shipping": ship,
        "currency": str((s.get("price") or {}).get("currency") or ""),
        "condition": str(s.get("condition") or ""),
        "url": str(s.get("itemWebUrl") or ""),
        "epid": str(s.get("epid") or ""),
        "categories": cats,
        "category": cats[-1] if cats else "",
        # A variation family on eBay, which we mirror rather than flatten.
        "is_group": group.upper().startswith("SELLER_DEFINED"),
        "group_href": str(s.get("itemGroupHref") or ""),
        # Ticked by default: the common case is wanting most of a seller's range
        # and rejecting a few. The count is confirmed before anything is drafted.
        "selected": True,
    }


def landed_cost(row):
    """What one unit costs us: the item plus the postage TO US.

    None when either is unknown, exactly as in domain/sourcing.py -- unknown
    postage is not free postage, and pricing from a cost that is missing half of
    itself produces a confident, wrong, and too-low price.
    """
    p, s = row.get("price"), row.get("shipping")
    if p is None or s is None:
        return None
    return round(float(p) + float(s), 2)


def screen_one(row, *, restriction_lookup=None, restricted_type=None,
               compliance=None):
    """Whether this item may be listed, and what it will cost you to try.

    Every check is injected, so this function makes no calls of its own and can
    be tested against every combination without a network. Each returns None to
    mean "could not tell", which becomes UNKNOWN -- never CLEAR. Treating a
    failed check as a pass is how a blocked product reaches the submit queue.
    """
    notes, verdict = [], CLEAR

    def worse(v):
        return v if _ORDER[v] < _ORDER[verdict] else verdict

    # 1. Amazon's own answer, where the item maps to something Amazon already
    #    has. This is the only authoritative one; the rest are our rules.
    if restriction_lookup:
        try:
            res = restriction_lookup(row)
        except Exception:
            res = None
        if res is None:
            verdict = worse(UNKNOWN)
            notes.append("Amazon could not be asked whether this is restricted.")
        elif res.get("blocked"):
            verdict = worse(BLOCKED)
            for m in (res.get("reasons") or ["Amazon restricts this product."]):
                notes.append(m)

    # 2. Product types we know Amazon gates or refuses.
    if restricted_type:
        try:
            rt = restricted_type(row)
        except Exception:
            rt = None
        if rt:
            verdict = worse(BLOCKED if rt.get("blocked") else CAUTION)
            notes.append(rt.get("message") or "This product type is restricted.")

    # 3. Categories that reliably demand paperwork -- safety data sheets, test
    #    certificates, age declarations. Listable, but not free to list, and
    #    finding that out at submit time is the expensive way.
    if compliance:
        try:
            c = compliance(row)
        except Exception:
            c = None
        if c and c.get("docs"):
            verdict = worse(DOCS)
            notes.append(c.get("message")
                         or "Amazon is likely to demand documents for this.")

    return {"verdict": verdict, "notes": notes,
            "item_id": row.get("item_id"), "title": row.get("title")}


def screen(rows, **kw):
    """Screen a batch. Returns (rows_with_verdicts, summary)."""
    out, counts = [], {k: 0 for k in _ORDER}
    for r in rows or []:
        res = screen_one(r, **kw)
        counts[res["verdict"]] += 1
        out.append(dict(r, screen=res))
    total = len(out)
    return out, {
        "total": total,
        "counts": counts,
        "draftable": total - counts[BLOCKED],
        # The worst thing in the batch, because a summary that averages away a
        # blocked product is a summary that gets it drafted.
        "worst": min(counts and [k for k in _ORDER if counts.get(k)] or [CLEAR],
                     key=lambda k: _ORDER[k]),
    }


def to_draft(row, *, account_id, marketplace, source_cost=None, days=3):
    """A screened, wanted item -> the draft row the rest of the app understands.

    The SKU carries the source cost and the eBay item id in the shape the app
    already uses -- {cost}_{N}Days_{id} -- so cost of goods, the repricer and
    everything built on that format keep working without a special case.

    NOTE the third field is the EBAY item id, not an Amazon ASIN. The format is
    positional and every reader takes only the leading cost (domain/cogs.py), so
    this is safe -- and it means the draft records where it came from, which
    nothing else was recording.
    """
    cost = source_cost if source_cost is not None else landed_cost(row)
    cost_s = ("%.2f" % float(cost)) if cost is not None else "0.00"
    # The KEYS here are the store's own column names (data/column_map.py), not
    # names of our own: ListingStore writes what it recognises and a key it has
    # never heard of is simply dropped, silently, so a draft would arrive with no
    # title and nobody would be told why.
    notes = []
    scr = (row.get("screen") or {})
    if scr.get("notes"):
        notes.extend(scr["notes"])
    if row.get("is_group"):
        notes.append("eBay lists this as a variation family — its children come "
                     "across as one Amazon family rather than separate products.")
    out = {
        "sku": "%s_%dDays_%s" % (cost_s, int(days), row.get("item_id") or ""),
        "title": row.get("title") or "",
        "source_url": row.get("url") or "",
        "handling_days": int(days),
        # Nothing is approved by arriving. It becomes a draft to be looked at,
        # which is the whole point of this pipeline over listing directly.
        "status": "NEEDS_REVIEW",
        "notes": " | ".join(n for n in notes if n)[:900],
    }
    if row.get("image"):
        # There is no image COLUMN. The app keeps a listing's main image inside
        # attributes_json under Amazon's own attribute name, which is what the
        # image library and the submit path both read -- so a draft written any
        # other way would show a blank tile and nothing would say why.
        import json as _json
        out["attributes_json"] = _json.dumps(
            {"main_product_image_locator": row["image"]})
    if row.get("category"):
        out["subcategory"] = row["category"][:120]
    out["platform"] = "ebay"          # where this draft came from
    # Carried for the caller and for tests; the store ignores what it does not
    # know, and these are how the importer explains itself afterwards.
    out["_source"] = {
        "item_id": row.get("item_id") or "",
        "cost": cost,
        "currency": row.get("currency") or "",
        "category": row.get("category") or "",
        "is_group": bool(row.get("is_group")),
        "group_href": row.get("group_href") or "",
        "account_id": account_id,
        "marketplace": marketplace,
        "verdict": scr.get("verdict") or "",
    }
    return out
