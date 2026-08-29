"""data/input_row.py -- what a queued product row is called, and whether it is usable.

WHY THIS IS A FOURTH FILE (the brief asked for three).

Two rules were about to be copy-pasted into the uploader, and CLAUDE.md Rule 12
says extract first, then change the one copy:

  1. WHICH HEADER MEANS WHICH COLUMN. amazon_listing_generator.read_input_sheet
     already accepts ebay_link/ebay_url, ebay_price/ebay_cost, amazon_link/
     amazon_url, amazon_price/selling_price, delivery_time/handling_time,
     ean/upc. An uploader with its own private list would accept a spreadsheet
     the generator's own reader would not, or refuse one it would -- and the
     difference would only ever show up as "why did my file import as blank".

  2. WHETHER A ROW CAN BE GENERATED FROM. routes/input_routes.py:85 already
     decides this for a hand-typed row: a source link, an Amazon link or ASIN,
     or a name. Nothing else in the queue is enough to start from.

Both now live here. The uploader calls them. /input/add and read_input_sheet
should be pointed at them too -- see the wiring notes -- at which point there is
one answer to each question instead of three.

NOTHING HERE TOUCHES A DATABASE OR A REQUEST. It maps names and judges rows, so
it can be read and tested on its own.
"""

from data.input_import import COLUMNS


def norm_header(h):
    """A header reduced to something comparable.

    Lowercased, with spaces, underscores, hyphens and dots removed, so
    "eBay Link", "EBAY_LINK", "ebay-link" and "ebay link" are one name. Anything
    that is not a letter or a digit goes, which also disposes of the byte-order
    mark Excel puts on the front of the first header of a CSV export.
    """
    s = str(h if h is not None else "").strip().lower()
    return "".join(ch for ch in s if ch.isalnum())


# Canonical column -> the header spellings that mean it.
#
# The first group of each list is what read_input_sheet accepts; the rest are
# what people actually type.
#
# A BARE "price" IS AMBIGUOUS, AND IS READ AS THE COST.
#
# On a supplier or eBay export "price" is what you pay; on an Amazon export it
# is what it sells for. Nothing in the file says which, so this has to choose,
# and the two ways of being wrong are not equally bad:
#
#   read as cost, actually a sale price  -> selling_price stays empty, the app
#                                           prices from an inflated cost, and
#                                           the listing goes UP.
#   read as sale price, actually a cost  -> the listing is priced AT what you
#                                           paid for it, and every sale loses
#                                           the fees.
#
# So it maps to source_cost: the wrong guess is then visible as a bad margin
# rather than as units going out at cost. The upload result names every column
# it matched, so a file whose "price" really was the sale price shows "Cost"
# in the matched tags and can be corrected before anything is generated.
ALIASES = {
    "ebay_url": ["ebay_link", "ebay_url",
                 "source", "source_link", "source_url", "supplier_link",
                 "supplier_url", "buy_link", "buy_url", "ebay"],
    "amazon_url": ["amazon_link", "amazon_url",
                   "amazon", "competitor_link", "competitor_url", "az_link"],
    "competitor_asin": ["competitor_asin",
                        "asin", "amazon_asin", "competitor", "parent_asin"],
    "item_name": ["item_name",
                  "name", "title", "product", "product_name", "item",
                  "description"],
    "source_cost": ["ebay_price", "ebay_cost", "source_cost",
                    "cost", "buy_price", "supplier_cost", "supplier_price",
                    "unit_cost", "cost_price", "price"],
    "selling_price": ["amazon_price", "selling_price",
                      "sell_price", "sell_at", "sale_price", "list_price",
                      "retail", "retail_price", "rrp"],
    "handling_time": ["delivery_time", "handling_time",
                      "handling", "handling_days", "dispatch",
                      "dispatch_time", "lead_time", "days"],
    "upc": ["ean", "upc",
            "barcode", "gtin", "isbn", "product_id", "ean_upc"],
}

# normalised spelling -> canonical column, built once.
_LOOKUP = {}
for _canon, _names in ALIASES.items():
    _LOOKUP[norm_header(_canon)] = _canon
    for _n in _names:
        _LOOKUP[norm_header(_n)] = _canon


def column_for(header):
    """The queue column this header means, or "" if it means nothing to us."""
    return _LOOKUP.get(norm_header(header), "")


def map_headers(headers):
    """Work out what an uploaded file's header row is offering.

    Returns (mapping, matched, ignored):
        mapping  {position: column} for the columns we understood
        matched  the canonical columns found, in COLUMNS order
        ignored  the original header text of everything we did not understand

    A repeated column keeps the FIRST one. A file with "cost" and "unit_cost"
    both present is ambiguous, and silently letting the later one win would mean
    the number you saw in the preview is not the number that was stored.
    """
    mapping, seen, ignored = {}, set(), []
    for i, h in enumerate(headers or []):
        col = column_for(h)
        if not col:
            if str(h or "").strip():
                ignored.append(str(h).strip())
            continue
        if col in seen:
            ignored.append(str(h).strip())
            continue
        seen.add(col)
        mapping[i] = col
    matched = [c for c in COLUMNS if c in seen]
    return mapping, matched, ignored


# WHAT MAKES A ROW WORTH QUEUEING.
#
# The same test /input/add applies to a hand-typed row (routes/input_routes.py).
# A row with none of these cannot be generated from and would sit in the queue
# looking like work.
IDENTIFYING = ("ebay_url", "amazon_url", "competitor_asin", "item_name")

WHY_NOT = ("Give at least a source link, an Amazon link or ASIN, or a product "
           "name — otherwise there is nothing to generate from.")


def is_generatable(product):
    """Is there anything here to start from?"""
    p = product or {}
    return any(str(p.get(k, "") or "").strip() for k in IDENTIFYING)


# ===========================================================================
# FROM AN UPLOADED PRODUCT TO A ROW IN THE LISTINGS STORE
# ===========================================================================
#
# The queue table is gone. An upload, or the "Add a product" form, now writes
# straight into the listings store with status=QUEUED, and the generator picks
# those rows up and fills the rest in. One table, one source of truth.
#
# THE SKU IS REAL FROM THE START, not a temporary id renamed later. The store is
# keyed by (workspace, sku) -- upsert_row, update_fields and delete_row all take
# it -- so a temp id would have to be RENAMED during generation, which upsert
# cannot do (it would insert a second row). And the SKU format carries meaning
# here: roughly sixty places parse or match on it, and a "Q-1724934567-001"
# satisfies none of them.
#
# So it is built at upload time by the generator's OWN build_sku, with the
# generator's own collision suffixes (_2, _3). Same function, same format, so a
# row queued by an upload is indistinguishable from one the generator made.

# The SKU's price part is the SOURCE COST, not the selling price. build_sku
# names the parameter source_cost, and the generator writes "Missing source
# price -- SKU price part defaulted to 0.00" when it is absent. Filling that
# slot with the selling price would produce a SKU the generator would not have
# built, which is exactly the rename this design exists to avoid.
SKU_PRICE_FIELDS = ("source_cost", "selling_price")

DEFAULT_DAYS = "3"
NO_ASIN = "NOASIN"


def _first_number(product, fields):
    """The first of `fields` that parses as a number, else 0.0."""
    import re as _re
    for f in fields:
        raw = str((product or {}).get(f, "") or "")
        m = _re.search(r"\d+(?:\.\d+)?", raw.replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                continue
    return 0.0


def ebay_ids(url):
    """(listing_id, variation_id) out of an eBay URL. Either may be "".

    BOTH, because the /itm/ number does not identify a product on a variation
    listing. api/ebay.py records the measurement: on a live 104-child listing
    all 104 children share ONE /itm/ id and are told apart only by ?var=, with
    prices genuinely ranging from 9.99 to 23.49 across that one listing.

    Matching duplicates on the /itm/ id alone would therefore report every child
    of a variation listing as a duplicate of its 103 siblings -- noise that
    would bury the real duplicates the warning exists to surface.

    api.ebay owns both regexes; there are three other copies of this extraction
    in the generator that disagree about how many digits an id has (\\d{6,} vs
    \\d{9,15}), and this deliberately is not a fourth (CLAUDE.md Rule 12).
    """
    try:
        from api import ebay as _ebay
        return (_ebay.item_id_from_url(url or ""),
                _ebay.variation_id_from_url(url or ""))
    except Exception:
        return "", ""


def build_queued_sku(product, taken_skus):
    """The real SKU for a product being queued. (sku, was_duplicate).

    Falls back the way the brief asked: no cost -> 0.00 (a shape that already
    exists in the data, e.g. 0.00_2Days_B0FFH5P2VY), no days -> 3, no ASIN ->
    NOASIN.
    """
    from amazon_listing_generator import build_sku      # lazy: it is a big module
    cost = _first_number(product, SKU_PRICE_FIELDS)
    days = str((product or {}).get("handling_time", "") or "").strip()
    import re as _re
    m = _re.search(r"\d+", days)
    days = m.group(0) if m else DEFAULT_DAYS
    asin = str((product or {}).get("competitor_asin", "") or "").strip().upper()
    if not asin:
        # The eBay item id is what the seller-import path already puts in this
        # slot (see SKUs like 23.99_3Days_336475288886v54595), so it is a better
        # answer than NOASIN when there is one.
        lid, vid = ebay_ids((product or {}).get("ebay_url", ""))
        asin = (lid + ("v" + vid if vid else "")) if lid else NO_ASIN
    return build_sku(cost, days, asin, set(taken_skus or ()))


def placeholder_warning(product, sku):
    """A warning when the SKU could not be built from anything real, else None."""
    has_cost = _first_number(product, SKU_PRICE_FIELDS) > 0
    has_asin = NO_ASIN not in str(sku)
    if has_cost or has_asin:
        return None
    return {
        "type": "placeholder_sku",
        "severity": "low",
        "message": ("No price or ASIN — the SKU is a placeholder and will be "
                    "updated during generation."),
        "details": {"sku": sku},
    }


def to_listing_row(product, taken_skus):
    """An uploaded/typed product -> (row for the listings store, extras).

    `row` uses the store's own SHEET header names, because that is what
    upsert_row accepts. `extras` carries what the listings table has no column
    for: the source cost (which lives in the COGS store) and the eBay ids and
    warnings (written straight to their columns).

    Sparse on purpose. Title, bullets, images, fees and the rest are the
    generator's job; this records only what was actually supplied.
    """
    p = product or {}
    sku, was_dup = build_queued_sku(p, taken_skus)
    lid, vid = ebay_ids(p.get("ebay_url", ""))

    row = {
        "SKU": sku,
        "Status": "QUEUED",
        "Source URL": str(p.get("ebay_url", "") or "").strip(),
        "Competitor ASIN": str(p.get("competitor_asin", "") or "").strip().upper(),
        "Title": str(p.get("item_name", "") or "").strip(),
        "UPC": str(p.get("upc", "") or "").strip(),
    }
    price = str(p.get("selling_price", "") or "").strip()
    if price:
        row["Our Price (GBP)"] = price
    days = str(p.get("handling_time", "") or "").strip()
    if days:
        row["Handling Time"] = days
        row["Handling Days"] = days

    extras = {
        "sku": sku,
        "was_duplicate_sku": was_dup,
        "ebay_item_id": lid,
        "ebay_variation_id": vid,
        # No column on `listings` holds the supplier cost -- it lives in the
        # COGS store, keyed by (account, sku). Recorded there rather than
        # dropped, so the margin figures have something to work from.
        "source_cost": _first_number(p, ("source_cost",)),
        "amazon_url": str(p.get("amazon_url", "") or "").strip(),
        "warnings": [w for w in (placeholder_warning(p, sku),) if w],
    }
    return row, extras


def row_to_product(row, mapping):
    """One file row + the header mapping -> a queue product dict.

    Every column the queue has is present, blank where the file did not offer
    it, so a caller never has to ask whether a key exists. The ASIN is NOT
    derived here: input_import.add_row already fills competitor_asin from
    amazon_url when it is empty, and a second implementation of that would be
    the third copy of the same three-line regex.
    """
    out = {c: "" for c in COLUMNS}
    for i, col in (mapping or {}).items():
        if i < len(row):
            v = row[i]
            out[col] = "" if v is None else str(v).strip()
    return out
