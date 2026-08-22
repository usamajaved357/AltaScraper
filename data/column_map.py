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
import re

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

# Alternative spellings of the SAME column, accepted on IMPORT only.
#
# Found by auditing the real spreadsheet before importing anything: the US tab
# names its money columns "($)" while the UK tabs use "(GBP)". Without these, an
# import of a US tab would have dropped every price, fee and profit silently --
# no error, just four blank columns and every margin reading zero.
#
# The currency belongs to the marketplace, not to the column: the database column
# is buy_box_price either way. COL_TO_HEADER is unchanged, so what comes BACK out
# is always the canonical FIXED_HEADERS name and nothing downstream sees a
# second spelling.
HEADER_ALIASES = {
    "Buy Box Price ($)":   "buy_box_price",
    "Our Price ($)":       "our_price",
    "Amazon Fees ($)":     "amazon_fees",
    "Profit ($)":          "profit",
    "Buy Box Price (USD)": "buy_box_price",
    "Our Price (USD)":     "our_price",
    "Amazon Fees (USD)":   "amazon_fees",
    "Profit (USD)":        "profit",
    "Buy Box Price (EUR)": "buy_box_price",
    "Our Price (EUR)":     "our_price",
    "Amazon Fees (EUR)":   "amazon_fees",
    "Profit (EUR)":        "profit",
    "Buy Box Price (£)":   "buy_box_price",
    "Our Price (£)":       "our_price",
    "Amazon Fees (£)":     "amazon_fees",
    "Profit (£)":          "profit",

    # MILES' SHEETS SPELL THE COPY COLUMNS DIFFERENTLY, and these are the
    # listing's actual words -- the bullets, the description, the backend
    # keywords. Without these aliases an import reads the sheet, finds no
    # column it recognises for any of them, and writes the rows in with the
    # copy silently missing. Every other field would look right, which is
    # exactly how that would have gone unnoticed.
    #
    # Found by /backup/verify, which reports the columns an import does not
    # understand rather than dropping them quietly: 74 Miles rows, 11 unknown
    # columns, six of them the product copy.
    "Bullet Point 1":      "bullet_1",
    "Bullet Point 2":      "bullet_2",
    "Bullet Point 3":      "bullet_3",
    "Bullet Point 4":      "bullet_4",
    "Bullet Point 5":      "bullet_5",
    "Description":         "description_html",
    "Backend Keywords":    "search_terms",
    # The Miles sheet's name for the compliance notes column. The app already
    # treats the two as one thing -- dashboard._card reads
    # gm("Compliance Notes", "Compliance Report") -- so leaving it unmapped meant
    # the notes were read for under a name nothing had ever stored, and every
    # Miles listing showed an empty compliance panel with no error.
    "Compliance Report":   "compliance_notes",
    # "Column 1", "Column 12", "Column 13" and "Uploaded" are deliberately NOT
    # mapped. They are spreadsheet scaffolding, not listing data, and inventing
    # a home for them would put junk into columns that mean something.
}


def col_for_header(header):
    """DB column for a sheet header, accepting the alternative spellings."""
    return HEADER_TO_COL.get(header) or HEADER_ALIASES.get(header)

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
        col = col_for_header(k)             # accepts "(GBP)" and "($)" alike
        if col is None:
            if k in COL_TO_HEADER:          # already a DB column name
                col = k
            else:
                continue
        if col in NUMERIC_COLS:
            out[col] = _num(v)
        else:
            out[col] = None if v is None else _no_none_word(str(v))
    return out


# The four characters N-o-n-e, standing in a text column where nothing was
# meant. They get there honestly: the generator's own prompt asks the model for
# "battery / electrical / chemical flags or None", so the model writes the word,
# and it is stored as though it were a value.
#
# 361 stored cells carry one -- 193 in compliance notes, 168 in the VOC source
# -- and every one is then displayed, concatenated and searched as content. It
# is what made the IP panel read "forbidden phrase - compatible with None": the
# phrase was "compatible with", and "None" was simply the next cell joined onto
# it.
#
# ONLY when it is the entire value. A note that genuinely begins "None -
# operates at 240 V AC mains voltage" is a real sentence about a real product
# and must survive untouched.
_NONE_WORDS = {"none", "null", "nan", "n/a", "na", "undefined"}


def _no_none_word(s):
    return "" if s.strip().lower() in _NONE_WORDS else s


# Money as it is actually written in the sheet. Symbols AND three-letter codes:
# the real spreadsheet stores "GBP16.00" and "GBP-5.85", not "£16.00". Stripping
# only the symbols left float("GBP16.00") to fail, which returned None and made
# the price NULL -- 53 of 55 prices lost on the first real import, silently,
# because a missing price looks exactly like a blank cell.
_MONEY_JUNK = re.compile(r"(?i)\b(?:GBP|USD|EUR|AUD|CAD|JPY|SEK|PLN|MXN|BRL|INR)\b"
                         r"|[£$€¥,%\s]")


# A price written with a word attached. These are the ONLY words a money column
# may carry and still be read as a number.
#
# The last resort below used to pull the first run of digits out of ANY string,
# so a sentence became money:
#
#     "Miles NXT POE-LT 320 -- Full Synthetic Polyol Ester..."  -> profit 320.00
#     "ISO 220"                                                 ->  220.00
#     "Bullet Point 3"                                          ->    3.00
#
# Those are real values that were stored on real rows (see the column-shift
# repair in data/store.py): a product's VISCOSITY GRADE recorded as its profit in
# pounds. Nothing warned, because a number is exactly what the caller asked for.
#
# A LENGTH LIMIT DOES NOT SEPARATE THESE. "ISO 220" is shorter than the genuine
# "approx 12.50", so any threshold loose enough to keep the second accepts the
# first. What actually tells them apart is the WORD: a price is qualified by a
# small, closed set of them, and "ISO" is not in it. Anything else is prose that
# happens to contain a digit, and prose is not a price.
_NUM_QUALIFIERS = {"approx", "approximately", "about", "circa", "ca", "each",
                   "ea", "per", "unit", "from", "up", "to", "around", "est",
                   "estimated", "inc", "incl", "exc", "excl", "vat", "rrp", "was",
                   # Currency CODES belong here, not in _MONEY_JUNK. That regex
                   # requires a word boundary (\bGBP\b) and the real sheet writes
                   # "GBP16.00" with no space -- P runs straight into 1, so there
                   # is no boundary and the code is never stripped. The old
                   # digit-scrape swallowed it by accident; this has to allow it
                   # on purpose, or the exact format that cost 53 of 55 prices on
                   # the first real import goes back to returning nothing.
                   "gbp", "usd", "eur", "aud", "cad", "jpy", "sek", "pln",
                   "mxn", "brl", "inr"}


def _num(v):
    """A number, or None. Tolerates 'GBP16.00', '£12.34', '-26.60%', '1,234', ''.

    A value that is prose which merely CONTAINS a digit returns None -- see
    _NUM_QUALIFIERS.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _MONEY_JUNK.sub("", str(v)).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    # Last resort: a number with a recognised qualifier, like "approx 12.50".
    # Split the ORIGINAL rather than the stripped form -- _MONEY_JUNK removes
    # spaces, which would run the qualifier into the number.
    raw = str(v).strip()
    m = re.fullmatch(r"(?i)\s*((?:[A-Za-z.]+\s*)*?)"
                     r"([-+]?[£$€¥]?\s*\d[\d,]*(?:\.\d+)?)"
                     r"\s*%?\s*((?:[A-Za-z.]+\s*)*)", raw)
    if not m:
        return None
    # EVERY word around the number must be a recognised qualifier. Several are
    # allowed ("9.99 inc VAT"), because each one is still checked -- letting a
    # second word through unchecked is what the allowlist exists to prevent.
    words = (m.group(1) + " " + m.group(3)).replace(".", " ").split()
    if any(w.lower() not in _NUM_QUALIFIERS for w in words):
        return None
    try:
        return float(_MONEY_JUNK.sub("", m.group(2)))
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
