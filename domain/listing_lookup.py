"""domain/listing_lookup.py -- one listing row, by SKU.

WHY THIS EXISTS
Image generation was given a photograph and a title. Everything else the app
knows about the product -- what it does, what it is made of, how big it is in
centimetres -- was sitting in the listing row one lookup away and was never
fetched, so the model guessed the scale and invented the uses.

Two callers need that row (the image routes and the A+ routes) and neither
should grow its own copy of "find the listing for this SKU": two copies would be
two answers about which row a SKU refers to, and the wrong one produces a spec
for a different product without ever erroring.

Never raises. A missing row means the caller carries on exactly as it did
before, with the photograph and the title.
"""


def row_by_sku(ws, sku, records=None):
    """The listing row for a SKU, as a plain dict keyed by the sheet's column
    names. Returns {} when it cannot be found, for any reason.

    Reads through listing/repo so it works the same on the database backend as
    on a sheet -- the store presents itself as a worksheet precisely so callers
    like this one do not have to know which is in use.
    """
    sku = str(sku or "").strip()
    if not sku or ws is None:
        return {}
    try:
        from listing import repo as _repo
        found = _repo.locate(ws, sku, sku_headers=("SKU",))
        if not found.ok:
            return {}
        values = _repo.read_row(ws, found.row) if hasattr(_repo, "read_row") else None
        if values is None:
            grid = _repo.read_grid(ws) or []
            if found.row - 1 >= len(grid):
                return {}
            values = grid[found.row - 1]
        headers = found.headers or []
        return {h: (values[i] if i < len(values) else "")
                for i, h in enumerate(headers) if h}
    except Exception:
        return {}


def facts_for(ws, sku, records=None):
    """The listing's own words about a product, ready for the image prompt.

    Convenience over row_by_sku + ai_providers.listing_facts, so a caller that
    only wants the block does not have to know about either.
    """
    row = row_by_sku(ws, sku, records)
    if not row:
        return {}
    return row
