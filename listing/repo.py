"""listing/repo.py -- the ONE way to find a listing row and read its columns.

WHY THIS EXISTS (Rule 12)
"Find the row number for this SKU" was written out SEVEN separate times, by hand,
in four files:

    routes/listing_routes.py   201, 770, 930, 998
    dashboard.py               2864
    routes/handling_routes.py  46
    routes/sync_routes.py      179

They were not identical, and the differences were real rather than cosmetic:

  * dashboard.py compared str(v).strip() == str(sku).strip(). The four in
    listing_routes compared str(v).strip() == sku -- the incoming SKU was NOT
    stripped. So a SKU carrying a stray trailing space matched through one code
    path and silently reported "not found" through the others. Same listing,
    same sheet, different answer depending on which button was pressed.
  * sync_routes.py hardcoded the string "SKU" instead of using SKU_HEADER, so a
    change to that constant would have broken sync quietly while everything else
    kept working.
  * handling_routes.py accepted SEVERAL possible column names and walked several
    tabs, skipping ones without the column. That is not sloppiness -- it is doing
    a different job -- so it is preserved here as an option, not flattened away.
  * A missing SKU column produced four different outcomes: HTTP 400, an
    unhandled crash, a RuntimeError, and a silent no-op.

CANONICAL BEHAVIOUR ADOPTED HERE
  - both sides are stripped before comparing (dashboard.py's version, which was
    the correct one; this FIXES the other five rather than changing them)
  - the SKU column is found by name, never by a hardcoded literal
  - a missing column is REPORTED, not guessed at -- the caller decides whether
    that is a 400, a skip, or an error, so no behaviour is lost

THIS MODULE MUST NOT IMPORT FLASK.
amazon_listing_generator.py runs as a SEPARATE PROCESS with its own sheet client.
It has to be able to import this too, or the seven copies simply become eight.
"""

DEFAULT_SKU_HEADERS = ("SKU",)


class Located:
    """The answer to "where is this SKU?".

    Carries the headers alongside the row because every caller needs both -- it
    finds the row, then immediately looks up another column to read or write.
    Returning them together is what stops callers re-reading row 1 themselves.
    """
    __slots__ = ("row", "headers", "sku_col", "error")

    def __init__(self, row=None, headers=None, sku_col=None, error=None):
        self.row = row
        self.headers = headers or []
        self.sku_col = sku_col
        self.error = error

    @property
    def ok(self):
        return self.row is not None and not self.error

    def col(self, name, default=None):
        """1-based column number for a header, or `default` if it is absent."""
        try:
            return self.headers.index(name) + 1
        except ValueError:
            return default

    def __repr__(self):
        return "Located(row=%r, sku_col=%r, error=%r)" % (self.row, self.sku_col, self.error)


def norm(v):
    """How a SKU is compared. One definition, used on BOTH sides.

    Stripping only the sheet's value and not the caller's was the bug: a SKU with
    a trailing space matched in one place and vanished in six others.
    """
    return str(v if v is not None else "").strip()


def read_headers(ws):
    """Row 1, stripped. Never raises -- an unreadable sheet returns []."""
    try:
        return [norm(h) for h in ws.row_values(1)]
    except Exception:
        return []


def find_col(headers, names):
    """1-based column for the first of `names` present in `headers`, else None.

    Takes a LIST of acceptable names so handling_routes' more permissive lookup
    keeps working -- it accepts several spellings of the SKU column across tabs.
    """
    if isinstance(names, str):
        names = (names,)
    for n in names:
        if n in headers:
            return headers.index(n) + 1
    return None


def locate(ws, sku, sku_headers=DEFAULT_SKU_HEADERS, headers=None):
    """Find the row holding `sku`. Returns a Located; NEVER raises.

    Not raising is deliberate. The seven call sites wanted four different things
    to happen when the column was missing, so this reports the problem and lets
    each caller keep its own behaviour instead of forcing one on all of them.
    """
    hdrs = headers if headers is not None else read_headers(ws)
    if not hdrs:
        return Located(headers=[], error="could not read the header row")

    kcol = find_col(hdrs, sku_headers)
    if not kcol:
        return Located(headers=hdrs, error="no SKU column")

    target = norm(sku)
    if not target:
        return Located(headers=hdrs, sku_col=kcol, error="no SKU given")

    try:
        values = ws.col_values(kcol)
    except Exception as e:
        return Located(headers=hdrs, sku_col=kcol,
                       error="could not read the SKU column: %s" % str(e)[:120])

    for i, v in enumerate(values, start=1):
        if norm(v) == target:
            return Located(row=i, headers=hdrs, sku_col=kcol)

    return Located(headers=hdrs, sku_col=kcol, error="sku not found in sheet")


def locate_in_tabs(book, sku, sku_headers=DEFAULT_SKU_HEADERS, tabs=None):
    """Search several tabs and return (worksheet, Located) for the first hit.

    This is handling_routes' behaviour, preserved: it walks every tab, skips ones
    with no SKU column rather than failing, and stops at the first match.
    Returns (None, Located(error=...)) when nothing matches anywhere.
    """
    checked, had_col = 0, False
    try:
        sheets = tabs if tabs is not None else book.worksheets()
    except Exception as e:
        return None, Located(error="could not list tabs: %s" % str(e)[:120])

    for ws in sheets:
        checked += 1
        found = locate(ws, sku, sku_headers=sku_headers)
        if found.error == "no SKU column":
            continue                      # not a listings tab -- skip, do not fail
        had_col = True
        if found.ok:
            return ws, found

    if not had_col:
        return None, Located(error="no tab has a SKU column (%d checked)" % checked)
    return None, Located(error="sku not found in any of the %d tabs" % checked)
