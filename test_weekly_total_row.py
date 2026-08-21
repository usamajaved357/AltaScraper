"""The account TOTAL row is not a product, and counting it doubles the week.

    "we have that section build in the app for campaing manager report and
     busiiness child asins report check bugs and see if it actually works"

It works. Both reports are recognised by their columns, an unrecognised file is
refused with the columns it did have, the two halves merge into one frozen week,
and the SP-API path returns real figures. What it got WRONG was arithmetic.

sales_daily stores one row per day per child ASIN AND one row with asin='*',
which data/db.py documents where the column is defined:

    asin '*' is the account+marketplace TOTAL for that day. Amazon reports the
    total separately from the per-ASIN breakdown and the two do not always add
    up ... so the total is stored as Amazon gives it rather than summed on read.

The weekly pull selected `asin IS NOT NULL AND asin<>''` -- which excludes a
missing ASIN and an empty one, and keeps the total. So the total was summed
alongside the products it is the total OF.

MEASURED on jack_uk, week of 10 Aug 2026: one ASIN sold 3 units and the '*' row
carried the same 3, so the pack reported 6 units and 540 sessions against a true
3 and 270. Every headline figure was roughly double, and unit_session_pct --
units over sessions -- survived only because both halves doubled together.

Nine other per-product queries in this app filter '*' (contribution.py,
sales_data.py, traffic_view.py, catalog_page_routes.py, daily_routes.py,
returns_routes.py). This one did not, which is the whole bug.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


WR = open(os.path.join(HERE, "routes", "weekly_routes.py"), encoding="utf-8").read()

print("== the weekly pull excludes the account total row ==")
_fn = WR.split("def _sales_traffic_table")[1].split("\n    def ")[0]
truthy("the query filters asin<>'*'", "asin<>'*'" in _fn)
truthy("  and says what '*' is", "ACCOUNT TOTAL" in _fn)
truthy("  with the measured cost of not filtering it",
       "6 units and 540 sessions" in _fn or "roughly DOUBLE" in _fn)

print("\n== and it is not the only query that has to know ==")
# If this convention is ever missed again it will be in a NEW query, so the
# check is that every per-product read of sales_daily filters the total -- not
# just the one that was wrong.
import glob
offenders = []
for p in glob.glob("domain/*.py") + glob.glob("routes/*.py"):
    src = open(p, encoding="utf-8").read()
    # A per-product read groups by asin. One that does must exclude '*' --
    # UNLESS it already names the ASINs it wants, in which case the IN clause is
    # the filter and '*' can only appear if a caller asked for it by name.
    # (domain/traffic_view.asin_daily is that case: five named ASINs for the Top
    # ASINs Trend. My first version of this rule flagged it, wrongly.)
    for m in re.finditer(r"FROM sales_daily(.{0,400}?)GROUP BY asin", src, re.S):
        clause = m.group(1).replace(" ", "")
        if "asin<>'*'" in clause or 'asin<>"*"' in clause:
            continue
        if "asinIN(" in clause or "asin=?" in clause:
            continue
        offenders.append("%s: %s" % (os.path.basename(p),
                                     m.group(1).strip()[:70].replace("\n", " ")))
if offenders:
    print("  per-ASIN queries that do NOT exclude the total:")
    for o in offenders:
        print("    ", o)
check("every per-ASIN read of sales_daily excludes the total", offenders, [])

print("\n== the two reports are still told apart by their columns ==")
# The families are named in domain/weekly_kpi.py, which is where the columns are
# actually inspected -- weekly_routes.py only hands the file over. My first
# version of these two looked in the route file and found nothing, which said
# something about my assertion rather than about the code.
WK = open(os.path.join(HERE, "domain", "weekly_kpi.py"), encoding="utf-8").read()
truthy("business child report is recognised", "business_child" in WK)
truthy("campaign manager export is recognised", "campaign_manager" in WK)
# An unrecognised file must be refused, not silently stored as an empty week.
truthy("an unknown file is refused",
       "does not look like either report" in WR)
truthy("  and is told which columns it did have",
       "The file has these columns" in WR)

print("\n== the advertising half says WHY it is missing ==")
# An empty advertising section looks exactly like a week with no ads in it.
truthy("the Ads API gap is named, not left as zeros",
       "Advertising API" in WR and "separate login" in WR)
truthy("  with the workaround", "upload the Campaign Manager export" in WR)

print("\n== a pulled week and an uploaded week use ONE parser ==")
# Two parsers would let the same week come out differently depending on how it
# arrived, which is the failure the file's own header warns about.
truthy("the pull is shaped like an upload",
       "SAME {headers, rows} shape" in WR or "shaped like an upload" in WR)
truthy("  so weekly_kpi has one parser", "one parser rather than two" in WR)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
