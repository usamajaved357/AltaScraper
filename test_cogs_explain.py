"""One place to upload a cost sheet, and one page that says how costs work.

    "what is the priority of cogs and do they works and uploading the cogs sheet
     should be in the one place, not scattered everywhere and what is the
     priority and how do the calculations works in the both scenarios, the
     should be able to understand this, can you add a button which explains all
     of it?"

TWO UPLOADS, AND THE VISIBLE ONE WAS THE UNSAFE ONE. Both posted to
/cogs/upload_sheet, so they agreed about how a file is READ. They disagreed
about something that matters more: the toolbar's uploadCogsCsv wrote
immediately, while cogs.js dry-runs the file, says how many costs it would set
and how many rows it cannot use, and asks. A bulk overwrite of what things cost
moves every profit figure in the app.

THE EXPLANATION ALSO ALREADY EXISTED and was unreachable: rendered into a folded
<details> below the grid, and only when window.LOGIC_VISIBLE is on.

AND IT HAD GONE STALE. It described a pricing rule of "+£3 postage +£2 ads +£1
profit" that the app abandoned -- all three constants are 0.00 now, replaced by
a 20% ROI floor, because those allowances were being subtracted from REPORTED
profit as well as built into the price and made the app contradict itself.
"""
import os
import re
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


HTML = open("templates/dashboard.html", encoding="utf-8").read()
COGSJS = open("static/js/cogs.js", encoding="utf-8").read()
MILES = open("static/js/miles_template.js", encoding="utf-8").read()
HOW = open("static/js/howworks.js", encoding="utf-8").read()
RT = open("routes/cogs_routes.py", encoding="utf-8").read()


print("=== the cost sheet is uploaded in exactly ONE place ===")
check("one upload control in the markup",
      len(re.findall(r"cogsUploadOpen\(\)", HTML)), 1)
truthy("  and it is the one that asks first",
       "dry" in COGSJS.split("async function cogsUploadFile")[1][:900])
truthy("the second upload's file input is gone", 'id="cogscsv"' not in HTML)
truthy("  and so is the function behind it",
       "async function uploadCogsCsv" not in MILES)
truthy("  with a note saying where it went, not just a hole",
       "cogsUploadOpen" in MILES and "scattered" in MILES)
# It also must not have moved to a bar that only appears when rows are ticked:
# a whole-account price list has nothing to do with the current selection.
_selbar = HTML.split('id="selbar"')[1].split("</div>")[0] if 'id="selbar"' in HTML else ""
truthy("the upload is not in the selection bar", "cogsUploadOpen" not in _selbar)
truthy("the sheet to fill in is still offered", "/cogs/template.csv" in HTML)


print("\n=== there is a button that explains it, and it is not hidden ===")
truthy("the button exists", 'onclick="cogsExplain()"' in HTML)
# SHORTENED IN THE DENSITY PASS. The toolbar had to fit on one line, and
# "How costs work" became "How costs" -- test_layout_density.py asserts that
# rename by name. The point here is unchanged: the button says what it is for
# rather than being an unlabelled icon.
truthy("  and says what it is for", "How costs" in HTML)
truthy("the handler exists", "async function cogsExplain" in COGSJS)
_fn = COGSJS.split("async function cogsExplain")[1].split("\n/* ---- TAKING")[0]
# ONE copy of the explanation. howworks.js already had it; a second wording would
# drift from the first the next time either changed (rule 12).
truthy("it reads the existing registry rather than restating it",
       "LOGIC_REGISTRY()" in _fn and "reg.cogs" in _fn)
truthy("  including how the selling price is worked out",
       "reg.pricing_rule" in _fn)
# LOGIC_VISIBLE hides implementation detail from a user. How the owner's own
# money is worked out is not implementation detail.
truthy("it is not gated behind the admin-only flag", "LOGIC_VISIBLE" not in _fn)


print("\n=== it shows THIS ACCOUNT'S figures, not only the rules ===")
truthy("it asks the server for them", "/cogs/count" in _fn)
for word in ("you set", "SKU name", "not known"):
    truthy("  it names the %r bucket" % word, word in _fn)
truthy("  and survives the figures not arriving",
       "the explanation stands without the figures" in _fn)
_count = RT.split("def cogs_count")[1].split("@app.route")[0]
truthy("the endpoint returns the breakdown", '"breakdown"' in _count)
for k in ("manual", "from_sku", "unknown", "known", "total"):
    truthy("  including %s" % k, '"%s"' % k in _count)
truthy("  it cannot go negative when an override is on an unlisted SKU",
       "max(0," in _count)
truthy("  and a failure there still answers the count",
       "except Exception" in _count)


print("\n=== the explanation answers what was actually asked ===")
_reg = HOW.split("cogs: { title")[1].split("pricing_rule: {")[0]
truthy("the PRIORITY is stated as an order, not a list",
       "in this order" in _reg and "stops at the first" in _reg)
truthy("  a cost you set wins", "Always wins" in _reg)
truthy("  the SKU name is second", "SKU's own name" in _reg)
truthy("  and not-known is a third answer, not a zero",
       "Not known" in _reg)
# The one that produces a confident wrong number if it is misunderstood.
truthy("0.00 is explained as UNKNOWN rather than free",
       "means UNKNOWN, not free" in _reg)
truthy("BOTH calculations are given, with the difference named",
       "an estimate, before you sell" in _reg
       and "measured, after you sell" in _reg)
truthy("  the estimate names its 15% stand-in", "15% of price" in _reg)
truthy("  the measured one names Amazon's own settlement",
       "the fees Amazon charged" in _reg)
truthy("  and it says WHICH part differs between them",
       "it is the FEE that differs, not the cost" in _reg)
truthy("'do they work' is answered, with the reason it is worth asking",
       "Do they actually reach everything?" in _reg)


print("\n=== and the pricing rule it quotes is the one the app follows ===")
# The explainer described +£3 postage +£2 ads +£1 profit. Those constants are all
# 0.00 now: they were being subtracted from reported profit as well as built into
# the price, so the same order read +2.58 in one place and -2.32 in another.
import importlib
_p = importlib.import_module("listing.pricing")
check("the postage allowance really is zero", _p.PRICING_RULE_SHIPPING_LABEL, 0.0)
check("  the ads allowance too", _p.PRICING_RULE_ADS_MARGIN, 0.0)
check("  and the flat minimum profit", _p.PRICING_RULE_MIN_PROFIT, 0.0)
# ZERO NOW, BY THE OWNER'S DECISION (27 Aug 2026): "Default should be 0% --
# meaning the repricer prices at breakeven (no profit, no loss) as the absolute
# floor. The user sets their own target."
#
# The 20% here was doing more than a default. Because it is a floor among
# floors it silently raised the price of every SKU that had never set a target,
# so an account that had deliberately set NONE was still priced to 20% back
# while the screen said "Target: none". A default that moves prices is not a
# default; it is a setting nobody chose.
check("no hidden percentage floor is applied", _p.PRICING_RULE_MIN_ROI_PCT, 0.0)
# What remains is the ABSOLUTE floor, and it is a real one: cost plus Amazon's
# cut is the price below which a sale destroys money.
from domain import sourcing as _s
_be = _s.floor_price(24.00, None)
truthy("  but break-even is still enforced", _be is not None and _be > 24.00)
truthy("  and a target still raises it",
       _s.floor_price(24.00, {"target_roi_pct": 20.0}) > _be)

_rule = HOW.split("pricing_rule: { title")[1].split("},")[0]
truthy("the explainer no longer prices in £3 and £2",
       "+ £3 postage label + £2 ads allowance" not in _rule)
truthy("  it says they are gone, rather than quietly dropping them",
       "are GONE, on purpose" in _rule)
truthy("  showing the contradiction they caused",
       "+£2.58" in _rule and "−£2.32" in _rule)
truthy("  and names what replaced the flat £1",
       ("%g" % _p.PRICING_RULE_MIN_ROI_PCT) + "%" in _rule)


print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
