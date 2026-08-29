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
