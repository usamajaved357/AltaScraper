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


# ---- variation families ----------------------------------------------------
#
# WHY A FAMILY CANNOT BE FLATTENED INTO ONE DRAFT
# Measured against the live Browse API on 14 Aug 2026, on one real listing:
#
#     104 children, 1 distinct legacyItemId, 104 distinct itemId
#     child prices from 9.99 to 23.49
#
# So drafting a family as a single row takes one price -- whichever variation
# eBay answers with -- and sells every size and colour at it, wrong by up to
# 2.3x in both directions. And because all 104 share the listing id, the SKU
# shape {cost}_{N}Days_{id} would produce the SAME SKU for all of them: the
# store upserts on SKU, so 103 of the 104 would silently overwrite each other
# and 1 draft would appear where 104 were expected, with no error anywhere.
#
# Children are therefore keyed on {listing}v{variation}, which is the only thing
# that tells them apart, and which api/ebay.get_item can read back.

# eBay's aspect names -> the attribute name Amazon builds a variation axis from.
# Deliberately short: an axis that is guessed wrong is worse than one left out,
# because listing/variations.check() will refuse a theme the schema does not
# allow, but a WRONG theme that the schema does allow is accepted by Amazon and
# quietly groups products by something they do not actually vary on.
AXIS_FOR = {
    "colour": "COLOR", "color": "COLOR",
    "size": "SIZE", "size type": "SIZE",
    "style": "STYLE",
    "material": "MATERIAL",
    "pattern": "PATTERN",
    "flavour": "FLAVOR", "flavor": "FLAVOR",
    "scent": "SCENT",
    "voltage": "VOLTAGE",
    "wattage": "WATTAGE",
}

# Amazon's SKU length limit. Over it we say so rather than truncating: two
# truncated SKUs can collide, and a collision here overwrites a real product.
SKU_MAX = 40


def _aspects(item):
    """One eBay item's aspects as a plain dict."""
    out = {}
    for a in (item or {}).get("localizedAspects") or []:
        if isinstance(a, dict) and a.get("name"):
            out[str(a["name"])] = str(a.get("value") or "")
    return out


def _child_url(child, base=None):
    """The URL that points at THIS variation and no other sibling.

    eBay's own itemWebUrl normally carries ?var=, and when it does it is used
    unchanged. When it does not, one is built -- on whichever eBay domain the
    family itself came from, because .co.uk answers 404 for a .com listing and
    api/ebay reports a 404 as GONE, which reads as "the supplier stopped selling
    it" and would take a live product out of stock.
    """
    web = str((child or {}).get("itemWebUrl") or "")
    if "var=" in web:
        return web
    iid = str((child or {}).get("itemId") or "").split("|")
    listing = str((child or {}).get("legacyItemId") or "")
    listing = listing or (iid[1] if len(iid) == 3 else "")
    var = iid[2] if len(iid) == 3 and iid[2] not in ("", "0") else ""
    if not (listing and var):
        return web
    host = "www.ebay.co.uk"
    for cand in (web, str((base or {}).get("url") or "")):
        if "://" in cand:
            host = cand.split("://", 1)[1].split("/", 1)[0]
            break
    return "https://%s/itm/%s?var=%s" % (host, listing, var)


def varying_aspects(children):
    """The aspect names that actually DIFFER across these children.

    eBay returns every aspect on every child -- brand, material, care
    instructions, the lot -- and only a few of them vary. The ones that vary are
    the variation axes; the rest are shared product facts. Told apart by counting
    distinct values, not by matching names against a list, because a seller can
    vary anything they like.
    """
    seen, order = {}, []
    for c in children or []:
        for name, val in _aspects(c).items():
            if name not in seen:
                seen[name] = set()
                order.append(name)
            seen[name].add(val)
    return [n for n in order if len(seen[n]) > 1]


def suggest_theme(aspect_names, allowed=None):
    """The Amazon variation theme these axes point at. -> (theme, problems).

    theme is "" whenever we cannot say honestly, and problems says why in
    sentences. NOTHING here writes variation_theme onto a listing: the theme is
    a per-product-type enum and must be checked against the live schema
    (CLAUDE.md Rule 4), which is listing/variations.check()'s job at merge time.
    This only proposes.
    """
    problems, axes, unmapped = [], [], []
    for n in aspect_names or []:
        a = AXIS_FOR.get(str(n).strip().lower())
        if a and a not in axes:
            axes.append(a)
        elif not a:
            unmapped.append(str(n))
    if unmapped:
        problems.append(
            "eBay varies these by %s, which has no matching Amazon variation "
            "axis, so that difference cannot be carried across."
            % ", ".join(sorted(set(unmapped))))
    if not axes:
        return "", problems + ["Nothing here maps onto an Amazon variation "
                               "theme, so the family cannot be grouped."]
    if allowed is None:
        # No schema to check against -- the caller has no product type yet. Say
        # so; do not let it read as confirmed.
        return "/".join(axes), problems

    want = set(axes)
    for t in allowed:
        if {p.strip().upper() for p in str(t).split("/") if p.strip()} == want:
            return t, problems
    problems.append(
        "This product type has no variation theme for %s. It allows: %s."
        % (" and ".join(axes), ", ".join(list(allowed)[:12]) or "none at all"))
    return "", problems


def group_children(group_data, base_row=None):
    """An eBay item-group response -> one review row per buyable variation.

    Each child keeps its OWN price, image and stock, because those are what
    differ; what it inherits from the family is the category, which eBay does not
    repeat on every child.
    """
    base = base_row or {}
    out = []
    for c in (group_data or {}).get("items") or []:
        row = to_review_row(c)
        listing_id = str(c.get("legacyItemId") or "")
        _l, var_id = ("", "")
        iid = str(c.get("itemId") or "")
        if "|" in iid:
            parts = iid.split("|")
            if len(parts) == 3:
                listing_id = listing_id or parts[1]
                var_id = parts[2] if parts[2] not in ("", "0") else ""
        if not (listing_id and var_id):
            # Without both we cannot tell this child from its siblings, and a
            # SKU that cannot tell them apart overwrites them. Skipped, counted.
            continue
        asp = _aspects(c)
        avail = (c.get("estimatedAvailabilities") or [{}])[0] or {}
        row.update({
            "item_id": "%sv%s" % (listing_id, var_id),
            "listing_id": listing_id,
            "variation_id": var_id,
            # The URL the repricer will read this child by. ?var= is the only
            # part of it that says WHICH child, so a child URL without one is
            # rebuilt -- on the family's own eBay domain, never a hardcoded one.
            "url": _child_url(c, base),
            "aspects": asp,
            "in_stock": str(avail.get("estimatedAvailabilityStatus") or ""),
            "is_group": False,
            "is_child": True,
            "category": row.get("category") or base.get("category") or "",
            "categories": row.get("categories") or base.get("categories") or [],
            "selected": True,
        })
        if not row.get("title"):
            row["title"] = base.get("title") or ""
        out.append(row)
    return out


def expand_group(group_data, base_row=None):
    """A family, ready to draft. -> {"children", "axes", "theme", "problems"}.

    Refuses rather than half-delivers: a family with one readable child is not a
    family, and drafting it as one would put a parent on Amazon with a single
    child underneath, which Amazon accepts and then shows to nobody.
    """
    base = base_row or {}
    kids = group_children(group_data, base)
    raw = (group_data or {}).get("items") or []
    axes = varying_aspects(raw)
    theme, problems = suggest_theme(axes)
    if len(kids) < len(raw):
        problems.append(
            "%d of eBay's %d variations could not be told apart from their "
            "siblings and were left out." % (len(raw) - len(kids), len(raw)))
    if len(kids) < 2:
        problems.append(
            "Only %d variation could be read, and a family needs at least two."
            % len(kids))
    return {"children": kids, "axes": axes, "theme": theme,
            "problems": problems, "count": len(kids),
            "listing_id": (kids[0]["listing_id"] if kids else "")}


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


def to_draft(row, *, account_id, marketplace, source_cost=None, days=3,
             family=None):
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
    attrs = {}
    if row.get("image"):
        # There is no image COLUMN. The app keeps a listing's main image inside
        # attributes_json under Amazon's own attribute name, which is what the
        # image library and the submit path both read -- so a draft written any
        # other way would show a blank tile and nothing would say why.
        attrs["main_product_image_locator"] = row["image"]

    if family:
        # The eBay family, recorded so it can be rebuilt on Amazon LATER.
        #
        # It cannot be built now, and pretending otherwise would be the bug: a
        # variation family is three attributes written onto listings that ALREADY
        # EXIST on Amazon (listing/variations.py), and these are drafts that do
        # not exist there yet. /variations/candidates reads live listings for
        # exactly that reason. So this is the note that lets the Variations
        # screen fill itself in once the children are published, rather than a
        # claim that the family is done.
        #
        # The leading underscore keeps it out of what is sent to Amazon --
        # build_api_attributes drops every key that starts with one.
        attrs["_family"] = {
            "role": family.get("role") or "child",
            "parent_sku": family.get("parent_sku") or "",
            "listing_id": family.get("listing_id") or "",
            "variation_id": row.get("variation_id") or "",
            # PROPOSED, not confirmed: variation_theme is a per-product-type enum
            # and no product type has been chosen yet. listing/variations.check()
            # tests it against the live schema at merge time (Rule 4).
            "proposed_theme": family.get("theme") or "",
            "theme_confirmed": False,
            "axis_values": family.get("axis_values") or {},
            "ebay_aspects": row.get("aspects") or {},
        }
        # Where an axis maps onto a column the store already has, fill it: the
        # generator and the editor both read these, so a child arrives knowing
        # what makes it different instead of needing it typed back in.
        for axis, val in (family.get("axis_values") or {}).items():
            col = {"COLOR": "colour", "SIZE": "size",
                   "MATERIAL": "material"}.get(str(axis).upper())
            if col and val:
                out[col] = str(val)[:120]

    if attrs:
        import json as _json
        out["attributes_json"] = _json.dumps(attrs)
    if len(out["sku"]) > SKU_MAX:
        # Not truncated: two truncated SKUs can land on the same string, and the
        # store upserts on SKU, so a collision silently overwrites a real product.
        notes.append("This SKU is %d characters and Amazon's limit is %d — "
                     "shorten it before submitting."
                     % (len(out["sku"]), SKU_MAX))
        out["notes"] = " | ".join(n for n in notes if n)[:900]
    if row.get("category"):
        out["subcategory"] = row["category"][:120]
    out["platform"] = "ebay"          # where this draft came from
    # Carried for the caller and for tests; the store ignores what it does not
    # know, and these are how the importer explains itself afterwards.
    out["_source"] = {
        "role": (family or {}).get("role") or "single",
        "url": row.get("url") or "",
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


def parent_sku_for(listing_id):
    """The SKU of the family itself -- the thing nobody buys.

    Deliberately NOT listing/variations.suggest_parent_sku, which builds a parent
    SKU out of the text its children share. These children share almost nothing:
    the SKU shape leads with the source cost and the costs differ (9.99 to 23.49
    on the measured listing), so the shared stem collapses to a character or two
    and the fallback is the whole of the first child's SKU with -PARENT on the
    end -- 44 characters, past Amazon's limit, and named after one arbitrary
    child. The eBay listing id is what the family actually is.
    """
    return "PARENT_%s" % str(listing_id or "").strip()


def family_drafts(expanded, base_row, *, account_id, marketplace, days=3):
    """An expanded eBay family -> the parent draft and one draft per child.

    Returns (drafts, problems). Refuses -- empty drafts, problems said plainly --
    rather than producing something half-formed, because Amazon accepts a
    half-formed family without complaint and the products simply stop appearing.
    """
    problems = list(expanded.get("problems") or [])
    kids = expanded.get("children") or []
    if len(kids) < 2:
        return [], problems or ["This family has fewer than two variations."]

    listing_id = expanded.get("listing_id") or ""
    psku = parent_sku_for(listing_id)
    theme = expanded.get("theme") or ""
    # eBay aspect name -> Amazon axis, for the axes that actually vary.
    axis_of = {}
    for n in expanded.get("axes") or []:
        a = AXIS_FOR.get(str(n).strip().lower())
        if a:
            axis_of[n] = a

    drafts = []
    parent_row = dict(base_row or {})
    parent_row.setdefault("image", kids[0].get("image") or "")
    parent = to_draft(parent_row, account_id=account_id, marketplace=marketplace,
                      source_cost=None, days=days,
                      family={"role": "parent", "parent_sku": psku,
                              "listing_id": listing_id, "theme": theme})
    parent["sku"] = psku
    # The parent is not buyable, so it has no price, no stock and no supplier to
    # track. Saying so on the row keeps it out of the repricer and out of every
    # profit figure, where a parent counts as a product with no cost.
    parent["status"] = "PARENT"
    # PREPENDED, not replacing: the screening verdict is already in these notes
    # -- "Amazon is likely to demand documents for this" -- and overwriting them
    # would throw away the one warning that was paid for before drafting.
    parent["notes"] = " | ".join(filter(None, [
        ("The group itself — not for sale, and not priced. Its %d variations "
         "carry the price and the stock. %s"
         % (len(kids),
            ("Proposed grouping: %s, which is checked against Amazon's schema "
             "when you merge them." % theme) if theme
            else "No Amazon variation theme could be worked out for it yet.")),
        parent.get("notes") or ""]))[:900]
    parent["_source"]["role"] = "parent"
    drafts.append(parent)

    for k in kids:
        fam = {"role": "child", "parent_sku": psku, "listing_id": listing_id,
               "theme": theme,
               "axis_values": {axis_of[n]: v
                               for n, v in (k.get("aspects") or {}).items()
                               if n in axis_of}}
        # The screening was done on the FAMILY, and a family is one product on
        # eBay -- so its verdict is every child's verdict. Without this the
        # "needs documents" warning would sit on the parent alone, which is the
        # one row nobody submits, and 104 children would each look clear.
        kid = dict(k)
        if base_row and base_row.get("screen") and not kid.get("screen"):
            kid["screen"] = base_row["screen"]
        d = to_draft(kid, account_id=account_id, marketplace=marketplace,
                     days=days, family=fam)
        drafts.append(d)
    return drafts, problems
