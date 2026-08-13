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


# ---------------------------------------------------------------------------
# WRITES
#
# "Which cell is this?" had TWO implementations: routes/listing_routes.py wrote
# its own a1() by hand, while handling_routes, sync_routes and brand_listing all
# imported rowcol_to_a1 from gspread. And "build a batch payload of
# {range, values} for these named fields" was written out four separate times.
#
# Both live here now. These are also the functions a database backend has to
# replace, so keeping them in one place is what makes that swap a small change
# rather than a hunt through eight files.
# ---------------------------------------------------------------------------

def a1(row, col):
    """A1 notation for a 1-based (row, col). One implementation.

    gspread's rowcol_to_a1 is used when it is importable, so behaviour matches
    the three call sites that already relied on it; the pure-Python fallback
    keeps this module usable without gspread (tests, and any future backend that
    has no Google client at all).
    """
    try:
        from gspread.utils import rowcol_to_a1
        return rowcol_to_a1(row, col)
    except Exception:
        s, c = "", int(col)
        while c:
            c, rem = divmod(c - 1, 26)
            s = chr(65 + rem) + s
        return "%s%d" % (s, int(row))


def cell_updates(row, headers, fields, aliases=None):
    """Batch payload for writing named fields to one row.

    Returns ([{range, values}, ...], written_names). Fields whose column is
    absent are SKIPPED and left out of written_names, so the caller can report
    what actually landed instead of assuming all of it did -- which is what
    sync_routes already did by hand, and what the others silently did not.

    `aliases` maps a field name to several acceptable column headings, matching
    sync_routes' _FIELD_ALIASES behaviour.
    """
    payload, written = [], []
    for name, value in (fields or {}).items():
        names = (aliases or {}).get(name, [name])
        col = find_col(headers, names)
        if not col:
            continue
        payload.append({"range": a1(row, col), "values": [[value]]})
        written.append(name)
    return payload, written


def set_field(ws, row, header, value, headers=None):
    """Write ONE cell, addressed by column NAME rather than number.

    Deliberately uses update_cell, exactly as every current single-cell caller
    did, so the write semantics are unchanged. Returns True if it was written,
    False if that column does not exist.
    """
    hdrs = headers if headers is not None else read_headers(ws)
    col = find_col(hdrs, header)
    if not col:
        return False
    ws.update_cell(row, col, value)
    return True


def set_fields(ws, row, fields, headers=None, aliases=None):
    """Write several named fields to one row in a SINGLE batch call.

    Returns the list of field names actually written. One call instead of one
    per field matters: the sheet API is quota'd per minute, and this is on the
    path that bulk operations take.
    """
    hdrs = headers if headers is not None else read_headers(ws)
    payload, written = cell_updates(row, hdrs, fields, aliases=aliases)
    if payload:
        ws.batch_update(payload)
    return written


def batch_write(ws, payload, chunk=100):
    """Send a prepared payload, in chunks the sheet API will accept.

    The 100-row chunking was already being done by hand in listing_routes; it
    lives here so every bulk writer gets it rather than only the one that
    remembered.
    """
    if not payload:
        return 0
    for i in range(0, len(payload), chunk):
        ws.batch_update(payload[i:i + chunk])
    return len(payload)


def delete_row(ws, row):
    """Remove a row. Named here because a database backend must implement it."""
    ws.delete_rows(int(row))
    return True


def col_letter(col_0):
    """Column letter from a ZERO-based index. 0 -> A, 25 -> Z, 26 -> AA.

    A third implementation of this existed: amazon_listing_generator._col_letter
    and domain/brand_listing._col_letter, on top of the a1() that
    routes/listing_routes.py had written by hand. Zero-based because that is the
    signature both callers already use -- changing it would have been a silent
    off-by-one in code that builds sheet ranges.
    """
    return col_letter_1(int(col_0) + 1)


def col_letter_1(col):
    """Column letter from a ONE-based number. 1 -> A, 26 -> Z, 27 -> AA.

    Both conventions are exposed on purpose. The two copies this replaces used
    DIFFERENT ones -- amazon_listing_generator._col_letter took a 0-based index,
    domain/brand_listing._col_letter took a 1-based number -- with the same
    algorithm underneath. Collapsing them onto one convention would have been a
    silent off-by-one in code that builds sheet ranges, so each caller keeps the
    convention it already used and says which it means.
    """
    s, n = "", int(col)
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ---------------------------------------------------------------------------
# WRITING A WHOLE LISTING ROW
#
# This is the generator's core write, moved out of amazon_listing_generator.py.
# It matters more than the rest: the generator runs as a SEPARATE PROCESS with
# its own sheet client, so until this lived somewhere a database backend could
# reach, a database could only ever be a copy that went stale the moment you
# generated anything.
#
# domain/brand_listing.py calls the same function (via host.sheet_write_row), so
# both writers move together.
# ---------------------------------------------------------------------------

def find_reusable_row(ws, comp_asin="", headers=None, values=None):
    """A row this listing may be written INTO, rather than appending below.

    Keeps the generator's existing priority exactly:
      1) a row with this Competitor ASIN but no SKU -- the row you cleared, so a
         regenerated listing lands back in its original position
      2) the first fully blank data row
      3) None -> the caller appends

    Returns a 1-based sheet row, or None. Never raises.
    """
    try:
        vals = values if values is not None else ws.get_all_values()
    except Exception:
        return None
    if not vals:
        return None

    hdrs = headers if headers is not None else [norm(h) for h in vals[0]]
    def idx(name):
        return hdrs.index(name) if name in hdrs else -1

    a_i, s_i = idx("Competitor ASIN"), idx("SKU")
    t_i, p_i = idx("Title"), idx("Product Type")

    def cell(rv, i):
        return norm(rv[i]) if (0 <= i < len(rv)) else ""

    target = norm(comp_asin)
    if target and a_i >= 0:
        for r in range(1, len(vals)):
            if cell(vals[r], a_i) == target and not cell(vals[r], s_i):
                return r + 1

    keyi = [i for i in (s_i, t_i, a_i, p_i) if i >= 0]
    if keyi:
        for r in range(1, len(vals)):
            if all(not cell(vals[r], i) for i in keyi):
                return r + 1
    return None


def write_row(ws, row_data, comp_asin="", retries=3, log=None, sleep=None):
    """Write one whole listing row. Refills a reusable row, else appends.

    Retries because this is the one write that must not be lost -- the row is
    the product of an entire generation run, including paid model calls. Losing
    it to a transient sheet error means paying to produce it again.

    `log` is a callable rather than a console object: this module is imported by
    the generator (Rich console), by Flask routes (no console), and will be
    imported by a database backend (neither). It must not care which.
    """
    import time as _time
    _sleep = sleep or _time.sleep
    target = find_reusable_row(ws, comp_asin)

    for attempt in range(1, int(retries) + 1):
        try:
            if target:                       # refill in place, keeping its position
                rng = "A%d:%s%d" % (target, col_letter(len(row_data) - 1), target)
                ws.update([row_data], rng, value_input_option="USER_ENTERED")
            else:                            # no gap -> append at the bottom
                ws.append_row(row_data, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            if attempt >= int(retries):
                if log:
                    log("Sheet write failed: %s" % str(e)[:60])
                return False
            _sleep(attempt * 5)
    return False


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
