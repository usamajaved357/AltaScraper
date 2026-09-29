"""domain/report_parsers.py -- reading uploaded reports: 3PL stock, sales and uplift CSVs, Amazon's listings report.

Moved word for word out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026).
dashboard.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import re


def _parse_pct_from_context(ctx: str, key: str, default=None):
    """Find something like 'TACOS 15%' or 'target tacos: 15' in the user's
    context string. Returns None if not found -- caller adds to `missing` list.
    NEVER invents a value."""
    import re
    if not ctx:
        return default
    pat = re.compile(rf"{key}\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?", re.I)
    m = pat.search(ctx)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return default
    return default


def _parse_3pl_csv(raw_bytes: bytes) -> dict:
    """Parse an uploaded 3PL stock CSV. Expected columns (order-insensitive):
      sku (or SKUs, natural sku, sku)
      3PL Stock (Available at Warehouse)
      In-Transit Stock (Sea/Truck to 3PL)
      Ordered Quantity
    Returns dict keyed by SKU.
    """
    import csv, io
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    by_sku = {}
    # tolerant column name matching
    def _pick(row, options):
        for opt in options:
            for k in row:
                if k and k.strip().lower() == opt.lower():
                    return row[k]
        # fuzzier: substring match
        for opt in options:
            for k in row:
                if k and opt.lower() in k.strip().lower():
                    return row[k]
        return ""
    for row in reader:
        sku = _pick(row, ["sku", "skus", "seller sku", "natural sku"])
        if not sku:
            continue
        by_sku[sku.strip()] = {
            "sku":            sku.strip(),
            "pl3_available":  _num(_pick(row, ["3pl stock", "available at warehouse", "warehouse stock"])),
            "pl3_in_transit": _num(_pick(row, ["in-transit", "in transit", "sea/truck"])),
            "pl3_ordered":    _num(_pick(row, ["ordered quantity", "on order", "ordered qty"])),
        }
    return by_sku


def _num(x, default=0.0) -> float:
    if x is None or x == "":
        return default
    try:
        s = str(x).replace(",", "").strip()
        return float(s) if s else default
    except (ValueError, TypeError):
        return default


def _parse_sales_csv(raw_bytes: bytes) -> dict:
    """Parse a Daily Sales CSV. Only needs SKU + per-day rate (units/day).
    Expected columns: sku, daily_rate  OR  sku, sales_last_30, window_days.
    Returns {sku: {sales_last_n, sales_window_days}}.
    """
    import csv, io
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    by_sku = {}
    def _pick(row, options):
        for opt in options:
            for k in row:
                if k and k.strip().lower() == opt.lower():
                    return row[k]
        for opt in options:
            for k in row:
                if k and opt.lower() in k.strip().lower():
                    return row[k]
        return ""
    for row in reader:
        sku = _pick(row, ["sku", "seller sku"])
        if not sku:
            continue
        # daily_rate is preferred; fallback to sales/window
        daily = _pick(row, ["daily rate", "daily_rate", "units per day", "sales per day"])
        sales_n = _pick(row, ["sales_last_n", "sales", "units", "sales last 30"])
        window = _pick(row, ["window_days", "window", "days"])
        if daily != "":
            by_sku[sku.strip()] = {
                "sales_last_n":       _num(daily),
                "sales_window_days":  1,
            }
        else:
            by_sku[sku.strip()] = {
                "sales_last_n":       _num(sales_n),
                "sales_window_days":  _num(window, default=30) or 30,
            }
    return by_sku


def _parse_uplift_csv(raw_bytes: bytes, field: str) -> dict:
    """Parse a YoY or PD uplift CSV (sku -> uplift fraction).
    field: 'yoy_uplift' or 'pd_uplift'
    Expected columns: sku, uplift (or the specific field name)
    """
    import csv, io
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    by_sku = {}
    def _pick(row, options):
        for opt in options:
            for k in row:
                if k and k.strip().lower() == opt.lower():
                    return row[k]
        return ""
    for row in reader:
        sku = _pick(row, ["sku", "seller sku"])
        if not sku:
            continue
        val = _pick(row, [field, "uplift", "increment", "yoy", "pd"])
        by_sku[sku.strip()] = _num(val)
    return by_sku


def _parse_listings_report(text):
    """Parse the TSV from GET_MERCHANT_LISTINGS_ALL_DATA into compact dicts.
    Header names vary slightly between accounts/marketplaces, so match flexibly."""
    if not text:
        return []
    lines = text.splitlines()
    if not lines:
        return []
    header = [h.strip().lower().replace("_", "-") for h in lines[0].split("\t")]
    # WHAT THIS REPORT DOES NOT CONTAIN (checked, not assumed -- rule 4).
    # The 30 columns Amazon sends for GET_MERCHANT_LISTINGS_ALL_DATA were dumped
    # for jack_uk/UK on 2026-08-20 and there is NO handling-time column. The
    # nearest-looking candidate, will-ship-internationally, reads a constant 3 on
    # every row -- including SKUs named 2Days and 5Days -- so it is not a
    # disguised handling time. Do not add a col(r, "handling", ...) here hoping
    # it turns up; the figure comes from getListingsItem
    # (attributes.fulfillment_availability[0].lead_time_to_ship_max_days) and is
    # merged into the catalogue in routes/live_routes.py.

    def col(row, *names):
        # exact match first
        for n in names:
            if n in header:
                i = header.index(n)
                if i < len(row):
                    return row[i].strip()
        # fuzzy: any header that contains the wanted token
        for n in names:
            for i, h in enumerate(header):
                if n in h and i < len(row):
                    v = row[i].strip()
                    if v:
                        return v
        return ""

    out = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        r = ln.split("\t")
        title = col(r, "item-name", "title", "product-name")
        out.append({
            "sku":   col(r, "seller-sku", "sku"),
            "asin":  col(r, "asin1", "asin"),
            "title": title,
            "price": col(r, "price"),
            "qty":   col(r, "quantity"),
            "status": col(r, "status", "listing-status") or "Active",
            "brand": col(r, "brand", "brand-name"),
            "fulfillment": col(r, "fulfillment-channel", "fulfilment-channel"),
            "ship_group": col(r, "merchant-shipping-group", "merchant-shipping-group-name"),
            # THE BARCODE, WHICH THIS REPORT HAS BEEN CARRYING ALL ALONG.
            #
            #     "my listings on all listings page shows ean none, this is not
            #      possible, my every listing has ean"
            #
            # He is right, and the database agrees: 271 of 303 listings hold a
            # UPC, and 86 of 86 on nestwell_goods. The rows saying "none" are
            # the ones that come from THIS report rather than from a draft --
            # Amazon's own catalogue -- and it was parsed without ever reading
            # the identifier column.
            #
            # ONLY WHEN IT IS ACTUALLY A BARCODE. Amazon's product-id column
            # holds whichever identifier the listing was created with, and
            # product-id-type says which: 1 ASIN, 2 ISBN, 3 UPC, 4 EAN. An ASIN
            # printed under the word EAN would be worse than the blank it
            # replaces, so the type is checked and anything that is not a
            # barcode is left out. A report with neither column simply yields
            # "", which is what happened before this line existed.
            "barcode": _report_barcode(col(r, "product-id", "product_id"),
                                       col(r, "product-id-type", "product_id_type")),
        })
    return out


# The values Amazon uses in product-id-type. 1 and 2 are an ASIN and an ISBN,
# which are not barcodes and must never be shown as one.
_REPORT_BARCODE_TYPES = {"3", "4", "UPC", "EAN", "GTIN", "GCID"}


def _report_barcode(value, kind):
    """The product id from a listings report, but only when it IS a barcode.

    Returns "" for an ASIN, an ISBN, an unknown type, or a missing column --
    the same empty string the parser produced before it read this at all, so a
    report shaped differently from the ones seen here loses nothing.
    """
    v = str(value or "").strip()
    if not v:
        return ""
    k = str(kind or "").strip().upper()
    if not k:
        # NO TYPE COLUMN AT ALL. A bare 12-14 digit number is a UPC or an EAN;
        # an ASIN is ten characters and starts with a letter, so the two cannot
        # be confused by length. Anything else is left alone.
        return v if (v.isdigit() and 12 <= len(v) <= 14) else ""
    return v if k in _REPORT_BARCODE_TYPES else ""


def _parse_required_missing(note: str):
    """Pull field keys out of an API-preview note like
    "[E] warranty_description 'Product Warranty' is required but missing."."""
    import re
    out = []
    for m in re.finditer(r"\[E\]\s*([a-z0-9_]+)", note or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    # also catch "'x' is required"
    for m in re.finditer(r"([a-z0-9_]{3,})\s+'[^']+'\s+is required", note or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out
