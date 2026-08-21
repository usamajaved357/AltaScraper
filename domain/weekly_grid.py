"""domain/weekly_grid.py -- the saved weeks as the grid the KPI sheet uses.

    "The current Export button on Weekly KPIs downloads data in a single-column
     format. It must match the exact layout of this Google Sheet ... Column B:
     KPI name ... Column C onward: each column is one week, newest on the left"

WHAT WAS WRONG WITH THE OLD EXPORT. It wrote ONE week, as a vertical list of
key/value pairs, from whichever week happened to be selected. The sheet it is
meant to feed is the opposite shape in every respect: metrics down the side,
weeks across the top, newest first, every saved week present. You could not
paste one into the other, and there was nothing to compare a week against.

THE LAYOUT IS READ FROM THE REAL SHEET, NOT INVENTED. Row for row, from
FF-WEEKLY KPI's:

      A          B                        C, D, E ...
    1            KPI                      week start dates, newest first
    2                                     week end dates
    3            Total Sales
    4            Sessions
    5            Units
    6            Unit Session Percentage
    7            (blank)
    8 .. 28      Ad Sales .. TACOS        the advertising block
    29           (blank)
    30           Units Sold / Products    section header, then one row per ASIN
    ..           Sessions
    ..           Conversion Rate
    ..           Daily Sales Rate

The four product sections sit at rows 30, 39, 48 and 57 in that sheet because it
happens to carry six ASINs. They are laid out by COUNTING here rather than by
those fixed numbers -- an account with nine products would otherwise write its
seventh ASIN over the next section's heading.

TWO THINGS THE SPEC AND THE SHEET DISAGREE ABOUT, and the sheet wins:

  "Row 18: BR (Sponsored Brands) Spend". BR is not Sponsored Brands here. It
  sits directly opposite NB, and domain/weekly_kpi.py computes the pair as
  BRANDED against NON-BRANDED -- campaigns whose name contains one of the
  account's brand terms, against the rest. Reading BR as an ad TYPE would put a
  different measurement under a label that pairs with Non-Brand. Flagged rather
  than silently reinterpreted.

  "WoW % change columns appear after each pair of weeks". There are none in the
  sheet -- columns C to AB are twenty-six consecutive weeks and nothing else --
  so none are written. Adding them would shift every week column and break the
  sync's ability to find the week it is updating.

NUMBERS STAY NUMBERS. Every cell is a float, an int or None, never a formatted
string, and the FORMAT travels beside it in `formats`. A "£1,245.00" that has to
be parsed back before it can be summed is not an export, it is a picture of one.
None means the figure could not be worked out -- an empty cell, never a zero.
"""

# (row label, kpi key, format) for the block above the product sections.
# "" as a key is a spacer row. The labels are the sheet's own spelling, down to
# "Acos" and "T.RoAS" -- this file's job is to match it, not to correct it.
MONEY = "money"
COUNT = "count"
PCT = "pct"
RATIO = "ratio"

# The fourth item is "does this row need the CAMPAIGN export?".
#
# IT MATTERS BECAUSE ZERO IS A CLAIM. weekly_kpi sums an empty campaign list to
# 0, so a week pulled from the API -- which has no advertising half at all,
# because that needs the Advertising API -- printed "Ad Spend 0.00" and "Ad
# Sales 0.00". In a client deck that reads as "we ran ads and made nothing",
# which is a statement about the business rather than about the data. Those rows
# are BLANK when the week has no campaign data, and blank is the truth: nobody
# has told this app what the advertising did.
KPI_ROWS = (
    ("Total Sales",             "total_sales",      MONEY, False),
    ("Sessions",                "sessions",         COUNT, False),
    ("Units",                   "units",            COUNT, False),
    ("Unit Session Percentage", "unit_session_pct", PCT,   False),
    ("",                        "",                 "",    False),
    ("Ad Sales",                "ad_sales",         MONEY, True),
    ("Ad Spend",                "ad_spend",         MONEY, True),
    ("Acos",                    "acos",             PCT,   True),
    ("T.RoAS",                  "troas",            RATIO, True),
    ("Ad Impressions",          "ad_impressions",   COUNT, True),
    ("Ad Clicks",               "ad_clicks",        COUNT, True),
    ("Ad Orders",               "ad_orders",        COUNT, True),
    ("CTR",                     "ctr",              PCT,   True),
    ("Ads CVR",                 "ads_cvr",          PCT,   True),
    ("NTB Orders",              "ntb_orders",       COUNT, True),
    ("BR Spend",                "br_spend",         MONEY, True),
    ("BR Sales",                "br_sales",         MONEY, True),
    ("BR RoAS",                 "br_roas",          RATIO, True),
    ("NB Spend",                "nb_spend",         MONEY, True),
    ("NB Sales",                "nb_sales",         MONEY, True),
    ("NB Orders",               "nb_orders",        COUNT, True),
    ("NB RoAS",                 "nb_roas",          RATIO, True),
    ("NB CPA",                  "nb_cpa",           MONEY, True),
    ("CPA",                     "cpa",              MONEY, True),
    ("CPC",                     "cpc",              MONEY, True),
    ("TACOS",                   "tacos",            PCT,   True),
)

# (section heading, which per-product number, format). The heading goes in
# column A and the word "Products" in column B, exactly as the sheet has it.
PRODUCT_SECTIONS = (
    ("Units Sold",        "units",         COUNT),
    ("Sessions",          "sessions",      COUNT),
    ("Conversion Rate",   "conversion",    PCT),
    ("Daily Sales Rate",  "units_per_day", RATIO),
)

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _long_date(iso):
    """2026-07-19 -> 'July 19, 2026', the sheet's own format.

    Written out rather than strftime'd: %-d is not portable to Windows and
    %#d is not portable off it, and this runs on both.
    """
    s = str(iso or "")[:10]
    try:
        y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
        return "%s %d, %d" % (_MONTHS[m - 1], d, y)
    except (ValueError, IndexError):
        return s


def _num(v):
    """A number, or None. Never a string, never a zero standing in for unknown."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def product_rows(weeks, group="parent"):
    """The ASIN spine: every product across every exported week, biggest first.

    THE UNION, NOT THE NEWEST WEEK'S LIST. A product that sold in March and not
    last week still belongs in a twenty-six week grid; taking the newest week's
    products would silently drop it and leave a hole in every earlier column.

    -> [(key, label, {week_start: {metric: value}})]

    `group` is "parent" to match the sheet, which lists parent ASINs, or "child"
    for the per-variation view. Grouping to a parent is a real aggregation, not
    a relabelling: units and sessions add up, and conversion is recomputed from
    the group's own totals -- averaging the children's percentages would weight
    a variation with five sessions the same as one with two thousand.
    """
    per, title_of, totals = {}, {}, {}
    for w in weeks or []:
        ws = str(w.get("week_start") or "")
        days = int(w.get("days") or 7) or 7
        bucket = {}
        for p in (w.get("products") or []):
            child = str(p.get("child_asin") or "").strip()
            parent = str(p.get("parent_asin") or "").strip()
            key = (parent or child) if group == "parent" else (child or parent)
            if not key:
                continue
            b = bucket.setdefault(key, {"units": 0, "sessions": 0, "sales": 0.0})
            b["units"] += int(_num(p.get("units")) or 0)
            b["sessions"] += int(_num(p.get("sessions")) or 0)
            b["sales"] += float(_num(p.get("sales")) or 0)
            # The first non-empty title wins. A child row grouped to its parent
            # carries the child's title, which is the only name the app has for
            # the parent -- better than an ASIN with nothing beside it.
            if not title_of.get(key):
                title_of[key] = str(p.get("title") or "")
        for key, b in bucket.items():
            # Recomputed from the group's own totals -- see the note above.
            b["conversion"] = ((b["units"] / b["sessions"])
                               if b["sessions"] else None)
            b["units_per_day"] = round(b["units"] / days, 1) if days else None
            per.setdefault(key, {})[ws] = b
            totals[key] = totals.get(key, 0) + b["units"]
    order = sorted(per.keys(), key=lambda k: (-(totals.get(k) or 0), k))
    return [(k, title_of.get(k) or "", per[k]) for k in order]


def build(weeks, group="parent", account_label=""):
    """The whole grid. -> {"rows": [[...]], "formats": [...], "meta": {...}}

    `weeks` is what domain/weekly_kpi.weeks() returns -- newest first, which is
    the order the sheet wants, so nothing is re-sorted here.

    Every row is the full width of the grid so the caller never has to pad, and
    `formats` has one entry per row saying how that row's week cells should be
    shown. The two are parallel lists on purpose: a cell that carries its own
    format is a cell that has been turned into a string.
    """
    weeks = list(weeks or [])
    prods = product_rows(weeks, group)
    width = 2 + len(weeks)

    def row(a="", b="", cells=None):
        out = [a, b]
        out.extend((cells or [])[:len(weeks)])
        while len(out) < width:
            out.append(None)
        return out

    rows, formats = [], []

    def add(r, fmt=""):
        rows.append(r)
        formats.append(fmt)

    # ---- rows 1-2: the week each column covers ----------------------------
    add(row("", "KPI", [_long_date(w.get("week_start")) for w in weeks]))
    add(row("", "", [_long_date(w.get("week_end")) for w in weeks]))

    # ---- the KPI block ----------------------------------------------------
    def _cell(w, key, needs_campaigns):
        # BLANK, NOT ZERO, when the advertising half of the week was never
        # loaded -- see the note on KPI_ROWS. has_campaigns is False on a week
        # pulled from the API, because that half needs the Advertising API.
        if needs_campaigns and not w.get("has_campaigns"):
            return None
        return _num((w.get("kpis") or {}).get(key))

    for label, key, fmt, needs in KPI_ROWS:
        if not label:
            add(row())
            continue
        add(row("", label, [_cell(w, key, needs) for w in weeks]), fmt)

    # ---- the four per-product sections ------------------------------------
    for heading, metric, fmt in PRODUCT_SECTIONS:
        add(row())
        add(row(heading, "Products",
                [_long_date(w.get("week_start")) for w in weeks]))
        add(row("", "", [_long_date(w.get("week_end")) for w in weeks]))
        for key, title, per in prods:
            add(row(key, title,
                    [_num((per.get(str(w.get("week_start") or "")) or {})
                          .get(metric)) for w in weeks]),
                fmt)

    return {
        "rows": rows,
        "formats": formats,
        "meta": {
            "weeks": len(weeks),
            "products": len(prods),
            "group": group,
            "account": account_label,
            "columns": width,
            "first_week": (weeks[0].get("week_start") if weeks else ""),
            "last_week": (weeks[-1].get("week_start") if weeks else ""),
            # Said out loud on the screen and in the workbook, because "BR" is
            # ambiguous and this app's answer is not the obvious one.
            "br_means": ("BR and NB are BRANDED and NON-BRANDED campaigns -- "
                         "split by whether the campaign name contains one of "
                         "this account's brand terms. They are not Sponsored "
                         "Brands and Sponsored Products."),
        },
    }


# ---- the two renderings -----------------------------------------------------

def _csv_cell(v, fmt):
    """A number stays a number; only the FORMAT decides how it looks.

    CSV has no formats, so this is where a percentage becomes readable -- but it
    stays a percentage of the same value, and money keeps two decimals with no
    symbol, because the currency differs per account and a wrong symbol is worse
    than none.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if fmt == PCT:
        return "%.2f%%" % (v * 100.0)
    if fmt == MONEY:
        return "%.2f" % v
    if fmt == RATIO:
        return "%.2f" % v
    if fmt == COUNT:
        return "%d" % int(round(v))
    return v


def to_csv(grid):
    """The grid as CSV text, in the sheet's layout."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for r, fmt in zip(grid["rows"], grid["formats"]):
        w.writerow([r[0], r[1]] + [_csv_cell(v, fmt) for v in r[2:]])
    return buf.getvalue()


# Excel/Sheets number formats, by our format name. The same strings the
# reference workbook uses, so a pasted column looks like the ones beside it.
SHEET_FORMATS = {
    MONEY: "#,##0.00",
    COUNT: "#,##0",
    PCT: "0.00%",
    RATIO: "#,##0.00",
    "": None,
}

_CURRENCY_PREFIX = {"GBP": "£", "USD": "$", "EUR": "€",
                    "CAD": "$", "AUD": "$", "SEK": "", "PLN": ""}


def money_format(currency=""):
    """The money format for this account's currency.

    A SYMBOL ONLY WHEN IT IS KNOWN. These accounts span GBP, EUR and USD, and a
    "$" printed over a euro figure is a confident lie -- worse than a bare
    number, because it reads as a fact. An unknown currency gets #,##0.00 and
    the column header says which account it is.
    """
    p = _CURRENCY_PREFIX.get(str(currency or "").strip().upper(), "")
    return ('"%s"#,##0.00' % p) if p else "#,##0.00"


def sheet_rows(grid):
    """The values to send to Google Sheets, for value_input_option=USER_ENTERED.

    TWO CONVERSIONS, both because of how USER_ENTERED works -- it treats each
    value as though a person had typed it into the cell:

      None -> ""      gspread will not send a None, and an empty cell is what a
                      figure that could not be worked out should look like.
      0.0275 -> "2.75%"
                      typed as text with a % sign, Sheets stores the NUMBER
                      0.0275 and formats the cell as a percentage by itself.
                      Sending the bare fraction would display "0.0275", which
                      is the same value and unreadable.

    Everything else stays a number, so the column can be summed and charted.
    That is the whole reason for writing to a sheet rather than pasting a
    picture of one.
    """
    out = []
    for r, fmt in zip(grid["rows"], grid["formats"]):
        line = [r[0], r[1]]
        for v in r[2:]:
            if v is None:
                line.append("")
            elif isinstance(v, str):
                line.append(v)
            elif fmt == PCT:
                line.append("%.2f%%" % (v * 100.0))
            elif fmt == COUNT:
                line.append(int(round(v)))
            else:
                line.append(round(float(v), 2))
        out.append(line)
    return out


def sheet_number_formats(grid, currency=""):
    """[(first_row, last_row, pattern)] over the WEEK columns, 1-based.

    Contiguous runs of the same format are merged, so a 52-row grid needs about
    six formatting calls instead of fifty-two. The percentage rows are left out
    on purpose -- sheet_rows already gives Sheets a percentage to recognise, and
    formatting them again would be a second opinion about the same cells.
    """
    runs, cur, start = [], None, None
    money = money_format(currency)
    pattern = {MONEY: money, COUNT: SHEET_FORMATS[COUNT],
               RATIO: SHEET_FORMATS[RATIO]}
    for i, fmt in enumerate(grid["formats"], start=1):
        p = pattern.get(fmt)
        if p != cur:
            if cur:
                runs.append((start, i - 1, cur))
            cur, start = p, i
    if cur:
        runs.append((start, len(grid["formats"]), cur))
    return runs
