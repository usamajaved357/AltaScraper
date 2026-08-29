"""listing/queued_input.py -- the generator's input, taken from the listings store.

The products a run works from used to come from a Google input sheet, read by
amazon_listing_generator.read_input_sheet. They now come from the listings store:
every row with status=QUEUED, put there by a CSV upload or the "Add a product"
form.

HOW IT REACHES THE GENERATOR. The generator is a subprocess, so the rows are
written to a temp JSON file and its path passed as --input-json. That mirrors
how the sheet was passed -- as a location to read, not as a restructured input
format -- so read_input_sheet and everything downstream of it keep the shape
they already had (CLAUDE.md Rule 10).

THE SHAPE IS read_input_sheet's, EXACTLY, plus one key:

    ebay_url  source_cost  amazon_url  selling_price  item_name  handling_time
    upc       + sku

`sku` is the addition and it is the whole point of this file. A queued row is
already IN the store with a real SKU, so the generator must fill THAT row in
rather than create a second one beside it; process_row reads this key and keeps
the identity instead of building a new one. Without it the finished listing
lands on a new row and the queued one stays QUEUED for ever.
"""
import json
import os
import tempfile

# The keys read_input_sheet produces. Anything downstream expects these names.
PRODUCT_KEYS = ("ebay_url", "source_cost", "amazon_url", "selling_price",
                "item_name", "handling_time", "upc")


def row_to_product(row):
    """One listings-store row -> the product dict the generator reads.

    The cost is not on the row -- `listings` has no column for it -- so it is
    recovered from the SKU, whose first part is the source price by convention
    (build_sku writes "{price}_{N}Days_{ASIN}"). That is the same number the
    upload put there, so nothing is invented.
    """
    sku = str(row.get("sku") or "").strip()
    cost = ""
    head = sku.split("_", 1)[0]
    try:
        if float(head) > 0:
            cost = head
    except (TypeError, ValueError):
        cost = ""

    return {
        "sku": sku,
        "ebay_url": str(row.get("source_url") or "").strip(),
        "amazon_url": "",
        "competitor_asin": str(row.get("competitor_asin") or "").strip(),
        "item_name": str(row.get("title") or "").strip(),
        "source_cost": cost,
        "selling_price": str(row.get("our_price") or "").strip(),
        "handling_time": str(row.get("handling_time")
                             or row.get("handling_days") or "").strip(),
        "upc": str(row.get("upc") or "").strip(),
    }


def products_for(config_path, workspace_id):
    """Every QUEUED row in a workspace, as generator products."""
    from data import queued_store as _qs
    return [row_to_product(r) for r in _qs.queued_rows(config_path, workspace_id)]


def write_temp_input(products):
    """Write products to a temp JSON file and return its path.

    Named so it is recognisable in a temp directory when a run has died and
    left one behind.
    """
    fd, path = tempfile.mkstemp(prefix="altascraper_queued_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(list(products or []), fh, ensure_ascii=False)
    return path


def read_products(path):
    """Read back what write_temp_input wrote. [] if it cannot be read.

    Never raises: a run that cannot read its input file should say "no products"
    the same way an empty sheet does, not stack-trace in a subprocess whose
    output is being streamed to a browser.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for p in data:
        if not isinstance(p, dict):
            continue
        row = {k: str(p.get(k, "") or "") for k in PRODUCT_KEYS}
        # Carried through so process_row can keep the row's identity.
        row["sku"] = str(p.get("sku", "") or "")
        row["competitor_asin"] = str(p.get("competitor_asin", "") or "")
        out.append(row)
    return out
