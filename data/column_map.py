"""data/column_map.py -- translate between the sheet's column names and the DB's.

WHY THIS EXISTS
The sheet's columns are written for humans: "Buy Box Price (GBP)", "Search Terms
/ KW", "Viable?". Those cannot be SQL column names. The database uses clean ones.

Everything the app already does reads rows with the SHEET's names --
g("UPC"), g("Status"), g("Notes") -- in roughly 300 places. Translating here,
once, is what lets all of those keep working untouched. Translating at the call
sites would mean editing 300 of them.

VERIFIED AGAINST THE REAL HEADERS
HEADER_TO_COL was checked against FIXED_HEADERS in amazon_listing_generator.py:
49 headers, 49 mappings, exact match in both directions. That check matters more
than it looks -- a single missing key would make g("That Header") return "" for
ever, silently, with no error anywhere. There is a test for it in
verify_column_map() below; run it after ANY change to FIXED_HEADERS.
"""

HEADER_TO_COL = {
    "Competitor ASIN":        "competitor_asin",
    "Source URL":             "source_url",
    "UPC":                    "upc",
    "SKU":                    "sku",
    "Platform":               "platform",
    "Buy Box Price (GBP)":    "buy_box_price",
    "Our Price (GBP)":        "our_price",
    "Amazon Fees (GBP)":      "amazon_fees",
    "Fee Source":             "fee_source",
    "Profit (GBP)":           "profit",
    "Margin %":               "margin_pct",
    "ROI %":                  "roi_pct",
    "Viable?":                "viable",
    "Product Type":           "product_type",
    "Amazon Category":        "amazon_category",
    "Subcategory":            "subcategory",
    "VOC Source":             "voc_source",
    "VOC Review Count":       "voc_review_count",
    "Target Demographic":     "target_demographic",
    "Pain Points":            "pain_points",
    "Purchase Trigger":       "purchase_trigger",
    "Title":                  "title",
    "Bullet 1":               "bullet_1",
    "Bullet 2":               "bullet_2",
    "Bullet 3":               "bullet_3",
    "Bullet 4":               "bullet_4",
    "Bullet 5":               "bullet_5",
    "Description (HTML)":     "description_html",
    "Search Terms / KW":      "search_terms",
    "Autocomplete Keywords":  "autocomplete_keywords",
    "Material":               "material",
    "Colour":                 "colour",
    "Size":                   "size",
    "Number of Items":        "number_of_items",
    "Target Gender":          "target_gender",
    "Age Range":              "age_range",
    "Compliance Notes":       "compliance_notes",
    "Handling Time":          "handling_time",
    "Handling Days":          "handling_days",
    "Status":                 "status",
    "Date Processed":         "date_processed",
    "Brand":                  "brand",
    "Model Number":           "model_number",
    "Notes":                  "notes",
    "Compliance Risk":        "compliance_risk",
    "IP Risk":                "ip_risk",
    "Attributes JSON":        "attributes_json",
    "Item Highlights":        "item_highlights",
    "API Payload JSON":       "api_payload_json",
}

COL_TO_HEADER = {v: k for k, v in HEADER_TO_COL.items()}

# Columns on the listings table that are NOT sheet columns -- bookkeeping the
# database keeps for itself. Excluded when a row is handed back to the app so it
# sees exactly the shape the sheet gave it, no more.
INTERNAL_COLS = {"id", "workspace_id", "created_at", "updated_at", "listing_marketplace"}

# Stored as REAL, so they must go in as numbers and come back as strings -- the
# sheet always handed the app strings, and code downstream assumes that.
NUMERIC_COLS = {"buy_box_price", "our_price", "amazon_fees", "profit",
                "margin_pct", "roi_pct"}


def row_to_header_dict(db_row, include_internal=False):
    """DB row -> dict keyed by SHEET column names.

    This is what makes g('UPC'), g('Status'), g('Notes') keep working with no
    change to the calling code. Values come back as strings because that is what
    a sheet read produced, and downstream code does things like
    .strip() on them -- handing back a float here would break those call sites
    in ways that only show up at runtime.
    """
    out = {}
    for k, v in dict(db_row).items():
        if k in INTERNAL_COLS and not include_internal:
            continue
        key = COL_TO_HEADER.get(k, k)
        out[key] = "" if v is None else str(v)
    return out


def header_dict_to_row(header_dict):
    """Dict keyed by SHEET column names -> dict keyed by DB column names.

    Unknown keys are dropped rather than passed through: letting an unmapped key
    reach the SQL layer turns a harmless typo into an SQL error at write time.
    Numeric columns are coerced, and a blank becomes NULL rather than 0 -- "no
    price recorded" and "priced at zero" are different facts and the difference
    matters to every margin calculation downstream.
    """
    out = {}
    for k, v in (header_dict or {}).items():
        col = HEADER_TO_COL.get(k)
        if col is None:
            if k in COL_TO_HEADER:          # already a DB column name
                col = k
            else:
                continue
        if col in NUMERIC_COLS:
            out[col] = _num(v)
        else:
            out[col] = None if v is None else str(v)
    return out


def _num(v):
    """A number, or None. Tolerates '£12.34', '45%', '1,234' and ''."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    for ch in "£$€%,":
        s = s.replace(ch, "")
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None


def verify_column_map(fixed_headers):
    """Check the map still covers every header. Returns (ok, problems).

    Call this at beta startup and from the tests. A silent gap here does not
    raise -- it just makes one column of data vanish -- so it is worth an
    explicit check rather than trusting that the two lists stayed in step.
    """
    problems = []
    for h in fixed_headers:
        if h not in HEADER_TO_COL:
            problems.append("header in the app but NOT mapped: %r" % h)
    for h in HEADER_TO_COL:
        if h not in fixed_headers:
            problems.append("mapped but no longer a real header: %r" % h)
    cols = list(HEADER_TO_COL.values())
    for c in set(cols):
        if cols.count(c) > 1:
            problems.append("two headers map onto the same column: %r" % c)
    return (not problems), problems
