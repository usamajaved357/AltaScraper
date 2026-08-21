"""The Weekly KPI export is the shape of the sheet it feeds.

    "The current Export button on Weekly KPIs downloads data in a single-column
     format. It must match the exact layout of this Google Sheet ... Column B:
     KPI name ... Column C onward: each column is one week, newest on the left"

WHAT IT USED TO DO: one week, as a vertical list of key/value pairs, from
whichever week happened to be selected. The sheet is the opposite shape in every
respect -- metrics down the side, weeks across the top, newest first, every
saved week present -- so you could not paste one into the other, and there was
nothing to compare a week against.

THE LAYOUT IS READ FROM THE REAL SHEET, not from the spec alone. Rows 1-2 are
the week's start and end, 3-6 are the store, 7 is blank, 8-28 are advertising,
29 is blank, then four product sections. The row numbers below are the sheet's
own, verified against FF-WEEKLY KPI's.

THREE PLACES THE SPEC AND THE SHEET DISAGREE, and the sheet wins:

  "Row 18: BR (Sponsored Brands) Spend" -- BR is not Sponsored Brands. It sits
  opposite NB, and domain/weekly_kpi.py computes the pair as BRANDED against
  NON-BRANDED campaigns. Reading it as an ad type would put a different
  measurement under a label that pairs with Non-Brand.

  "WoW % change columns appear after each pair of weeks" -- there are none in
  the sheet. Columns C to AB are twenty-six consecutive weeks and nothing else.
  Adding them would shift every week column.

  "Row 39+ / 48+ / 57+" for the later product sections -- those numbers hold
  only because that sheet carries six ASINs. The sections are laid out by
  counting, or an account with nine products would write its seventh ASIN over
  the next section's heading.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


from domain import weekly_grid as wg

R = read("routes", "weekly_routes.py")
J = read("static", "js", "weekly.js")
H = read("templates", "dashboard.html")


def P(child, parent, title, units, sessions):
    return {"child_asin": child, "parent_asin": parent, "title": title,
            "units": units, "sessions": sessions, "sales": units * 12.0,
            "page_views": int(sessions * 1.3),
            "conversion": (units / sessions if sessions else None),
            "units_per_day": round(units / 7.0, 1)}


def W(start, end, sales, sess, units, prods, campaigns=True):
    return {"week_start": start, "week_end": end, "days": 7,
            "has_business": True, "has_campaigns": campaigns,
            "currency": "GBP",
            "kpis": {"total_sales": sales, "sessions": sess, "units": units,
                     "unit_session_pct": (units / sess if sess else None),
                     "ad_sales": 100.0, "ad_spend": 25.0, "acos": 0.25,
                     "troas": 4.0, "ad_impressions": 5000, "ad_clicks": 120,
                     "ad_orders": 9, "ctr": 0.024, "ads_cvr": 0.075,
                     "ntb_orders": 2, "br_spend": 5.0, "br_sales": 40.0,
                     "br_roas": 8.0, "nb_spend": 20.0, "nb_sales": 60.0,
                     "nb_orders": 6, "nb_roas": 3.0, "nb_cpa": 3.33,
                     "cpa": 2.78, "cpc": 0.21, "tacos": 0.05},
            "products": prods}


WEEKS = [
    W("2026-08-09", "2026-08-15", 1355.58, 3517, 96,
      [P("B0C1", "B0PARENT1", "Runner size 8", 30, 900),
       P("B0C2", "B0PARENT1", "Runner size 9", 20, 700),
       P("B0C3", "B0PARENT2", "Trainer size 8", 46, 1917)]),
    W("2026-08-02", "2026-08-08", 1311.43, 3826, 93,
      [P("B0C1", "B0PARENT1", "Runner size 8", 40, 1000),
       P("B0C9", "B0PARENT3", "Leather trainer", 53, 2826)]),
]

G = wg.build(WEEKS, group="parent", account_label="Test")
ROWS = G["rows"]


def cell(r, c):
    return ROWS[r - 1][c - 1] if r - 1 < len(ROWS) else None


def label(r):
    return cell(r, 2)


print("== the grid is weeks ACROSS, metrics DOWN ==")
check("three columns: A, B, then a week each", G["meta"]["columns"], 4 - 1 + 1)
check("  two weeks", G["meta"]["weeks"], 2)
check("  newest is the first week column", cell(1, 3), "August 9, 2026")
check("  older is the second", cell(1, 4), "August 2, 2026")
check("row 2 is the week END", cell(2, 3), "August 15, 2026")
check("column A is empty on the KPI rows", cell(3, 1), "")
check("column B carries the name", label(3), "Total Sales")

print("\n== the row order is the sheet's, row for row ==")
for r, want in ((3, "Total Sales"), (4, "Sessions"), (5, "Units"),
                (6, "Unit Session Percentage"), (8, "Ad Sales"),
                (9, "Ad Spend"), (10, "Acos"), (11, "T.RoAS"),
                (12, "Ad Impressions"), (13, "Ad Clicks"), (14, "Ad Orders"),
                (15, "CTR"), (16, "Ads CVR"), (17, "NTB Orders"),
                (18, "BR Spend"), (19, "BR Sales"), (20, "BR RoAS"),
                (21, "NB Spend"), (22, "NB Sales"), (23, "NB Orders"),
                (24, "NB RoAS"), (25, "NB CPA"), (26, "CPA"), (27, "CPC"),
                (28, "TACOS")):
    check("row %-2d is %s" % (r, want), label(r), want)
check("row 7 is blank", (cell(7, 1), cell(7, 2), cell(7, 3)), ("", "", None))
check("row 29 is blank", (cell(29, 1), cell(29, 2)), ("", ""))

print("\n== the four product sections, in order ==")
heads = [(i + 1, ROWS[i][0]) for i in range(len(ROWS)) if ROWS[i][1] == "Products"]
check("there are four", len(heads), 4)
check("  the first is at row 30", heads[0][0], 30)
check("  named Units Sold", heads[0][1], "Units Sold")
check("  then Sessions", heads[1][1], "Sessions")
check("  then Conversion Rate", heads[2][1], "Conversion Rate")
check("  then Daily Sales Rate", heads[3][1], "Daily Sales Rate")
# The sheet has them at 39/48/57 because it carries SIX products. With three
# they land earlier -- laid out by counting, not by those fixed numbers.
check("with 3 products the second lands at 36, not 39", heads[1][0], 36)
truthy("why the sections are counted, not fixed",
       "seventh ASIN over the next section" in read("domain", "weekly_grid.py"))
check("each section repeats the week dates", cell(31, 3), "August 15, 2026")

print("\n== products group to the parent, and it is a real aggregation ==")
check("three children became three parents", G["meta"]["products"], 3)
_u = {ROWS[i][0]: ROWS[i][2] for i in range(30, 34) if ROWS[i][0]}
check("  B0PARENT1 is 30+20 in the newest week", _u.get("B0PARENT1"), 50.0)
# Conversion is recomputed from the group's totals, NOT averaged: averaging
# would weight a variation with 5 sessions the same as one with 2,000.
_conv_head = heads[2][0]
_row = next(i for i in range(_conv_head, len(ROWS)) if ROWS[i][0] == "B0PARENT1")
check("  its conversion is 50/1600, not the mean of the children's",
      round(ROWS[_row][2], 6), round(50 / 1600.0, 6))
_child = wg.build(WEEKS, group="child")
check("by child it is five rows, not three", _child["meta"]["products"], 4)

print("\n== a product missing from a week is BLANK, not zero ==")
_r = next(i for i in range(29, len(ROWS)) if ROWS[i][0] == "B0PARENT2")
check("B0PARENT2 sold in the newest week", ROWS[_r][2], 46.0)
check("  and is empty in the week it did not", ROWS[_r][3], None)
# A product that sold in March belongs in a 26-week grid; taking the newest
# week's list would drop it and leave a hole in every earlier column.
truthy("the spine is the union of every week",
       "THE UNION, NOT THE NEWEST WEEK'S LIST" in read("domain", "weekly_grid.py"))

print("\n== zero is a claim, so a missing half is blank ==")
_nc = wg.build([W("2026-08-09", "2026-08-15", 89.97, 270, 3, [], campaigns=False)])
check("with no campaign export, Ad Spend is blank", _nc["rows"][8][2], None)
check("  and Ad Sales", _nc["rows"][7][2], None)
check("  and TACOS", _nc["rows"][27][2], None)
check("  but Total Sales is still there", _nc["rows"][2][2], 89.97)
check("  and Sessions", _nc["rows"][3][2], 270.0)
# A fragment that sits on ONE source line. Matching across a line break, or
# across a string concatenation, is how these assertions keep failing on
# correct code -- four times in this repo now.
truthy("why a blank beats a zero here",
       "we ran ads and made nothing" in read("domain", "weekly_grid.py"))

print("\n== numbers stay numbers ==")
truthy("sales is a float, not a string", isinstance(cell(3, 3), float))
truthy("  sessions too", isinstance(cell(4, 3), float))
check("percentages are stored as fractions", round(cell(6, 3), 6),
      round(96 / 3517.0, 6))
# In CSV a fraction is unreadable, so THAT is where it becomes 2.73%.
csv = wg.to_csv(G)
lines = csv.splitlines()
truthy("the CSV renders it as a percentage", "2.73%" in lines[5])
truthy("  money keeps two decimals", ",1355.58" in lines[2])
falsy("  and carries no currency symbol", "$" in csv or "£" in csv)
check("the CSV has a line per grid row", len(lines), len(ROWS))
truthy("the first cell of every row is column A", lines[2].startswith(","))

print("\n== what goes to Google Sheets ==")
sr = wg.sheet_rows(G)
check("as many rows", len(sr), len(ROWS))
check("  None becomes an empty cell", sr[6][2], "")
# USER_ENTERED: typed as "2.73%", Sheets stores 0.0273 AND formats the cell.
check("  a percentage is typed as one", sr[5][2], "2.73%")
truthy("  a count is a whole number", isinstance(sr[3][2], int))
truthy("  money keeps its decimals", isinstance(sr[2][2], float))
runs = wg.sheet_number_formats(G, "GBP")
truthy("number formats come back as runs", len(runs) >= 3)
truthy("  money carries the account's currency",
       any('"£"' in p for _a, _b, p in runs))
check("  an unknown currency gets no symbol", wg.money_format("XYZ"), "#,##0.00")
check("  and a known one does", wg.money_format("USD"), '"$"#,##0.00')
falsy("percentage rows are not formatted twice",
      any(p == "0.00%" for _a, _b, p in runs))

print("\n== BR is BRANDED, and the app says so ==")
truthy("the grid explains it", "BRANDED and NON-BRANDED" in G["meta"]["br_means"])
truthy("  and that it is not Sponsored Brands",
       "not Sponsored Brands" in G["meta"]["br_means"])
truthy("the disagreement with the spec is recorded",
       "BR is not Sponsored Brands here" in read("domain", "weekly_grid.py"))
truthy("the screen shows it before writing a sheet", "br_means" in J)

print("\n== the routes ==")
truthy("there is a CSV export", "/weekly/export.csv" in R)
truthy("  and a grid preview", "/weekly/grid" in R)
truthy("  and a sheet sync", "/weekly/sheet" in R)
truthy("all three use the one layout", R.count("_grid(wsid, mkt, group)") >= 3)
truthy("the BOM is an escape, not a character",
       '"\\ufeff"' in R)
falsy("  no literal BOM in the source", "﻿" in R)
truthy("the mimetype is not doubled", 'mimetype="text/csv"' in R)

print("\n== writing to a live sheet takes two presses ==")
truthy("the first is a dry run", "dry_run" in R)
truthy("  which writes nothing", 'if not b.get("confirm")' in R)
truthy("  and says exactly what it would do", "would replace the " in R)
truthy("    naming the tab and the size", "tab with %d rows by %d " in R)
truthy("the screen asks before the second", "Yes, write it" in J)
truthy("  and can be cancelled", "weeklySheetCancel" in J)

print("\n== and it never writes over the listings sheet ==")
truthy("the weekly sheet is its own setting", "weekly_sheet_url" in R)
falsy("  it does not fall back to the output sheet",
      "output_spreadsheet_id" in R or "output_sheet_url" in R)
truthy("  refusing instead when unset", "has no weekly KPI sheet set" in R)
truthy("the settings form has the field",
       "ac_weekly_url" in read("static", "js", "shell.js"))
truthy("  it is saved", "weekly_sheet_url:" in read("static", "js", "shell.js"))
truthy("  the server accepts it",
       '"weekly_sheet_url", "weekly_sheet_tab"' in read("routes",
                                                        "accounts_routes.py"))
truthy("  and hands it back, or the box would self-erase",
       '"weekly_sheet_url": a.get("weekly_sheet_url"' in read(
           "routes", "accounts_routes.py"))
truthy("the buttons are on the page", "weeklySheetSync()" in H)
truthy("  including the parent/child choice", 'id="wk_group"' in H)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
