"""Returns Intelligence: the parent view, the themes, the badge, the workbook.

    "i want this format for return intelligence in my tool and also when a user
     clicks on download button in excel, this format report should be
     downloaded"

WHAT THE REFERENCE REPORT DOES THAT THE SCREEN DID NOT

A real footwear account, 11,509 FBA returns over eight months, was the test
case, and four things in it had no equivalent here:

    per PARENT      132 child ASINs of one shoe, none of which reads as a
                    problem on its own, add up to 6,412 returns. The screen had
                    a per-SKU table and a product-line table with no sizing
                    split, no child count and no direction.
    per MONTH       whether a line is getting worse. Nothing showed this.
    the COMMENTS    10,199 of them. The screen listed the first forty.
    the BADGE       Amazon's own "frequently returned item" warning. Not in
                    either returns report, not in any API this app has.

THREE THINGS THIS DELIBERATELY DOES DIFFERENTLY FROM THE REFERENCE

1. AT RISK IS AMAZON'S WORD, NOT A THRESHOLD OF OURS. The first version flagged
   anything over 15% and produced 470 rows out of 552, including ASINs with ONE
   order at "100%". It now reads the Return Badge Displayed column and nothing
   else: 54 showing, 43 at risk, on that account.

2. THE WORST PRODUCT LINE HAS A FLOOR. Without one it named a twelve-ASIN sliver
   at 67% on 135 orders, above a real line at 41% on eighteen hundred.
   Arithmetically true and useless.

3. THE PARTIAL MONTH IS EXCLUDED FROM THE TREND. Three weeks of August against
   seven full months reads as a collapse that has not happened.

AND ONE RULE-12 AUDIT, because this touched a concept that already existed in
several places. Every one of these now has exactly one definition:

    what "sellable" means      returns_view.is_sellable
    what a product family is   families.by_asin -> returns_view.line_of
    units sold in a period     sales_data.products
    the findings               returns_intel.insights (screen AND workbook)
"""
import io
import json
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


from domain import returns_intel as ri
from domain import returns_view as rv

# Read once, near the top, because assertions further down all reach for them.
J = read("static", "js", "returns.js")
_rt = read("routes", "returns_routes.py")

# ---------------------------------------------------------------------------
# A small account, made by hand, whose every answer can be worked out on paper.
# Two shoes: a runner in three sizes that runs small, and a sandal in one.
# ---------------------------------------------------------------------------
def R(date, asin, name, reason, disp=None, qty=1, comment=None, sku=""):
    return {"date": date, "asin": asin, "sku": sku or (asin + "-s"),
            "name": name, "qty": qty, "reason": rv.clean_reason(reason),
            "reason_raw": reason, "nature": rv.nature_of(reason),
            "status": "Completed", "resolution": "", "refunded": None,
            "order_amount": None, "category": "",
            "disposition": disp, "comment": comment}


RUN = "Speedy Runner - Black"
SAN = "Beach Sandal - Tan"
RETURNS = (
    # The runner: mostly too small, mostly sellable, and rising month on month.
    [R("2026-01-%02d" % (i + 1), "A1", RUN, "APPAREL_TOO_SMALL", "SELLABLE",
       comment="Way too small, order a size up") for i in range(4)]
    + [R("2026-02-%02d" % (i + 1), "A2", RUN, "APPAREL_TOO_SMALL", "SELLABLE",
         comment="Runs small") for i in range(4)]
    + [R("2026-03-%02d" % (i + 1), "A3", RUN, "APPAREL_TOO_LARGE", "SELLABLE",
         comment="Too big for me") for i in range(2)]
    + [R("2026-04-%02d" % (i + 1), "A1", RUN, "APPAREL_TOO_SMALL", "SELLABLE")
       for i in range(4)]
    + [R("2026-05-%02d" % (i + 1), "A2", RUN, "APPAREL_TOO_SMALL", "SELLABLE")
       for i in range(8)]
    + [R("2026-06-%02d" % (i + 1), "A3", RUN, "APPAREL_TOO_SMALL",
         "CUSTOMER_DAMAGED") for i in range(9)]
    # The sandal: a quality problem, and it comes back damaged.
    + [R("2026-01-%02d" % (i + 1), "B1", SAN, "DEFECTIVE", "DEFECTIVE",
         comment="The strap broke after one wear") for i in range(3)]
    + [R("2026-06-%02d" % (i + 1), "B1", SAN, "NOT_AS_DESCRIBED", "SELLABLE",
         comment="Colour is nothing like the photo") for i in range(2)]
)
SOLD = {"A1": {"units": 100, "sales": 2000.0}, "A2": {"units": 100, "sales": 2000.0},
        "A3": {"units": 100, "sales": 2000.0}, "B1": {"units": 50, "sales": 500.0}}

S = rv.summarise(RETURNS, SOLD)
INTEL = ri.build(RETURNS, S, None, SOLD, None)

print("== the returns were counted the way anyone would count them ==")
check("36 units came back", S["units_returned"], 36)
check("  from 4 ASINs", S["unique_skus"], 4)
check("  out of 350 sold", S["total_ordered"], 350)
check("  a rate of 10.29%", S["return_rate"], 10.29)

print("\n== sellable has ONE definition, and it is Amazon's word ==")
check("SELLABLE is sellable", rv.is_sellable("SELLABLE"), True)
check("  and so is the lower-case one", rv.is_sellable("sellable"), True)
check("CUSTOMER_DAMAGED is not", rv.is_sellable("CUSTOMER_DAMAGED"), False)
check("DEFECTIVE is not", rv.is_sellable("DEFECTIVE"), False)
# NOT False. An ungraded return is one nobody looked at, which is a different
# fact from one that was looked at and failed.
check("nothing at all is neither", rv.is_sellable(""), None)
check("  nor is a missing one", rv.is_sellable(None), None)
check("24 of the 36 came back sellable", S["sellable_pct"], 66.7)
check("  all 36 were graded", S["graded"], 36)
_v = rv.summarise([R("2026-01-01", "A1", RUN, "APPAREL_TOO_SMALL")], {})
check("with no FBA file there is no percentage", _v["sellable_pct"], None)
check("  and it is not zero", _v["sellable_pct"] is None, True)

print("\n== the per-product split is counted in the pass that was already there ==")
_a = {x["asin"]: x for x in S["asins"]}
check("A3's 2 too-large returns came back sellable", _a["A3"]["sellable"], 2)
check("  and its 9 too-small ones did not", _a["A3"]["unsellable"], 9)
check("the sandal's 3 defectives are unsellable", _a["B1"]["unsellable"], 3)
check("  its 2 colour returns are sellable", _a["B1"]["sellable"], 2)
_tot = sum(x["sellable"] for x in S["asins"])
check("the per-product sellables add up to the account's",
      _tot, int(round(S["sellable_pct"] / 100.0 * S["graded"])))

print("\n== sizing is its own cause, not a preference ==")
check("too small is sizing", rv.nature_of("APPAREL_TOO_SMALL"), "Sizing & Fit")
check("too large is sizing", rv.nature_of("APPAREL_TOO_LARGE"), "Sizing & Fit")
check("  and poor fit is too", rv.nature_of("POOR_FIT"), "Sizing & Fit")
# The rule that keeps it out of Customer Preference: order matters, and this is
# the assertion that fails if anyone reorders NATURE_RULES.
_names = [n for n, _ in rv.NATURE_RULES]
truthy("sizing is tested BEFORE customer preference",
       _names.index("Sizing & Fit") < _names.index("Customer Preference"))
truthy("  and quality before listing content",
       _names.index("Product Quality") < _names.index("Listing Content"))
check("still not filed as a preference",
      rv.nature_of("APPAREL_TOO_SMALL") == "Customer Preference", False)
check("31 of the 36 are fit", S["natures"]["Sizing & Fit"], 31)

print("\n== one row per parent, keyed the same way the line table is ==")
P = {p["label"]: p for p in INTEL["parents"]}
check("two products, not four ASINs", len(INTEL["parents"]), 2)
truthy("  the runner is one of them", "Speedy Runner" in P)
check("  with its three sizes inside", P["Speedy Runner"]["child_count"], 3)
check("  31 returns", P["Speedy Runner"]["returns"], 31)
check("  out of 300 sold", P["Speedy Runner"]["ordered"], 300)
check("  a rate of 10.33%", P["Speedy Runner"]["return_rate"], 10.33)
check("  86% of all returns", P["Speedy Runner"]["share"], 86.1)
# THE POINT OF ALL OF IT: the parent totals and the Product Line totals are the
# same grouping, by construction -- both call returns_view.line_of.
_lines = {L["line"]: L for L in S["lines"]}
check("the parent table and the line table agree, product for product",
      sorted((k, v["returns"]) for k, v in P.items()),
      sorted((k, v["returns"]) for k, v in _lines.items()))
truthy("because both call line_of",
       "line_of" in read("domain", "returns_intel.py"))
falsy("  and returns_intel keeps no grouping rule of its own",
      "_LINE_SPLIT" in read("domain", "returns_intel.py"))

print("\n== the family map is made in ONE place ==")
from domain import families as fam
truthy("families.by_asin exists", hasattr(fam, "by_asin"))
# It is what the route passes, and what summarise's own lines section uses.
_rt = read("routes", "returns_routes.py")
truthy("the route builds it there", "_fam.by_asin(" in _rt)
truthy("  and hands the same map to both", "_rv.summarise(returns, sold, fams)" in _rt)
truthy("  and to the intelligence layer", "_ri.build(returns, s, fams, sold" in _rt)
# A NAMED family beats a name cut at a dash -- that is the whole reason the map
# exists, and line_of has always preferred it.
check("a known family wins over the derived name",
      rv.line_of("Speedy Runner - Black", "Speedy Trainers"), "Speedy Trainers")
check("  and without one the name is cut at the variant",
      rv.line_of("Speedy Runner - Black", None), "Speedy Runner")

print("\n== units sold comes from the app's one reader ==")
truthy("the route calls sales_data.products", "_sd.products(" in _rt)
falsy("  and no longer writes its own SELECT over sales_daily",
      "FROM sales_daily" in _rt)

print("\n== the trend is a shape, and it ignores a part-finished month ==")
check("six months of data", len(INTEL["months"]), 6)
# Every month has a full set of days here, so nothing is partial.
# June stops on the 9th here, so the newest month IS unfinished -- which is
# the ordinary case for a report pulled mid-month.
truthy("the newest month is unfinished", INTEL["partial_last_month"])
check("the runner is getting worse", P["Speedy Runner"]["trend"], "increasing")
check("  4+4+2=10 became 4+8+9=21", sum(
    P["Speedy Runner"]["monthly"][m] for m in INTEL["months"][-3:]), 21)
check("two points are not a direction", ri.trend_of({"2026-01": 1}, ["2026-01"]), "")
check("  nor are three", ri.trend_of({}, ["a", "b", "c"]), "")
check("a 10% rise is noise",
      ri.trend_of({"m1": 10, "m2": 10, "m3": 10, "m4": 11, "m5": 11, "m6": 11},
                  ["m1", "m2", "m3", "m4", "m5", "m6"]), "stable")
check("  a 50% rise is not",
      ri.trend_of({"m1": 10, "m2": 10, "m3": 10, "m4": 15, "m5": 15, "m6": 15},
                  ["m1", "m2", "m3", "m4", "m5", "m6"]), "increasing")
check("  and a fall is reported as one",
      ri.trend_of({"m1": 20, "m2": 20, "m3": 20, "m4": 5, "m5": 5, "m6": 5},
                  ["m1", "m2", "m3", "m4", "m5", "m6"]), "decreasing")

print("\n== a month that has not finished is marked and left out ==")
_part = list(RETURNS) + [R("2026-07-03", "A1", RUN, "APPAREL_TOO_SMALL")]
truthy("a report ending on the 3rd knows July is unfinished",
       ri.partial_last_month(_part))
_full = list(RETURNS) + [R("2026-07-31", "A1", RUN, "APPAREL_TOO_SMALL")]
falsy("  one ending on the 31st knows it is not",
      ri.partial_last_month(_full))
_pi = ri.build(_part, rv.summarise(_part, SOLD), None, SOLD, None)
check("the part month is still SHOWN", len(_pi["months"]), 7)
check("  but not counted in the trend", len(_pi["months_complete"]), 6)
falsy("  it is the newest one that is dropped",
      "2026-07" in _pi["months_complete"])
truthy("the screen marks the column", '"*"' in read("static", "js", "returns.js")
       or '+ "*"' in read("static", "js", "returns.js"))

print("\n== the comments are grouped by what they SAY ==")
T = INTEL["themes"]
check("15 comments were read", T["comments_read"], 15)
_by = {x["theme"]: x for x in T["themes"]}
truthy("'too small' is a theme", "Too small / runs small" in _by)
truthy("  and 'too large' is a different one", "Too large / runs big" in _by)
check("  8 said too small", _by["Too small / runs small"]["count"], 8)
check("  2 said too big", _by["Too large / runs big"]["count"], 2)
truthy("quality is its own theme", "Quality or durability" in _by)
truthy("  and the listing is another", "Not as pictured or described" in _by)
# The reason code and the comment can disagree, and the comment wins here.
check("a comment saying 'half a size too short' is sizing, whatever Amazon "
      "called it", ri.theme_of("Nice shoe but half a size too short"),
      "Too small / runs small")
check("  a comment with nothing in it is placed nowhere",
      ri.theme_of("arrived tuesday"), "")
check("  and neither is an empty one", ri.theme_of(""), "")
# THE HONEST BIT: what could not be placed is counted and said.
check("nothing was left unplaced here", T["unplaced"], 0)
_odd = [R("2026-01-01", "A1", RUN, "UNWANTED_ITEM", "SELLABLE",
          comment="arrived on a tuesday")]
check("an unplaceable comment IS counted as unplaced",
      ri.comment_themes(_odd)["unplaced"], 1)
truthy("the screen says how many it could not place",
       "unplaced" in read("static", "js", "returns.js"))
# Distinct quotes: six copies of one sentence teach nobody anything.
_same = [R("2026-01-01", "A1", RUN, "APPAREL_TOO_SMALL", "SELLABLE",
           comment="Too small") for _ in range(20)]
check("twenty identical comments give one quote",
      len(ri.comment_themes(_same)["themes"][0]["quotes"]), 1)
check("  and still count twenty", ri.comment_themes(_same)["themes"][0]["count"], 20)

print("\n== 'at risk' is AMAZON's word, not a threshold of ours ==")
QUALITY = [
    {"ASIN": "A1", "Product name": RUN, "SKU": "A1-s", "Total orders": "900",
     "Return rate": "31.0%", "NCX rate": "4%", "Top NCX reason": "Too Small\n80%",
     "CX Health": "Very poor", "Return Badge Displayed": "Yes"},
    {"ASIN": "A2", "Product name": RUN, "SKU": "A2-s", "Total orders": "400",
     "Return rate": "18.0%", "NCX rate": "2%", "Top NCX reason": "Too Small",
     "CX Health": "Poor", "Return Badge Displayed": "At risk"},
    # ONE ORDER, ONE RETURN. The old rule called this a 100% emergency.
    {"ASIN": "A9", "Product name": RUN, "SKU": "A9-s", "Total orders": "1",
     "Return rate": "100%", "NCX rate": "0%", "Top NCX reason": "--",
     "CX Health": "Excellent", "Return Badge Displayed": "--"},
    {"ASIN": "B1", "Product name": SAN, "SKU": "B1-s", "Total orders": "50",
     "Return rate": "10.0%", "NCX rate": "1%", "Top NCX reason": "--",
     "CX Health": "Good", "Return Badge Displayed": "--"},
]
AR = ri.at_risk(QUALITY)
check("two of the four are flagged", len(AR), 2)
check("  the badged one first", AR[0]["asin"], "A1")
check("  and it is named as badged", AR[0]["state"], "badge showing")
check("  the other is only at risk", AR[1]["state"], "at risk")
falsy("the one-order 100% ASIN is NOT flagged",
      any(a["asin"] == "A9" for a in AR))
falsy("  and neither is the healthy one",
      any(a["asin"] == "B1" for a in AR))
check("Amazon's two-line reason cell is flattened, not truncated",
      AR[0]["top_reason"], "Too Small 80%")
check("  the rate is a number, not text", AR[0]["return_rate"], 31.0)
check("nothing at all gives nothing", ri.at_risk(None), [])
check("  and an empty file too", ri.at_risk([]), [])

print("\n== one row per ASIN, because the badge is on the listing ==")
# Amazon's export has a row per SKU. Three SKUs of one listing arrived as three
# identical rows, same ASIN, same rate, same badge.
DUPES = [
    {"ASIN": "A1", "SKU": "s1", "Total orders": "14", "Return rate": "50.8%",
     "CX Health": "Very poor", "Return Badge Displayed": "Yes",
     "Product name": RUN, "Top NCX reason": "Performance"},
    {"ASIN": "A1", "SKU": "s2", "Total orders": "1", "Return rate": "50.8%",
     "CX Health": "Excellent", "Return Badge Displayed": "Yes",
     "Product name": RUN, "Top NCX reason": "--"},
    {"ASIN": "A1", "SKU": "s3", "Total orders": "1", "Return rate": "50.8%",
     "CX Health": "Excellent", "Return Badge Displayed": "At risk",
     "Product name": RUN, "Top NCX reason": "--"},
]
D = ri.at_risk(DUPES)
check("three rows become one", len(D), 1)
check("  and it says there were three", D[0]["sku_rows"], 3)
check("  the SKU kept is the one that actually sells", D[0]["sku"], "s1")
check("  badged wins over at risk", D[0]["state"], "badge showing")
# NOTHING IS SUMMED. Amazon's per-SKU orders and rate are its own figures;
# adding them would invent a number it never gave.
check("  orders are not added up", D[0]["orders"], 14.0)
check("  nor is the rate touched", D[0]["return_rate"], 50.8)

print("\n== Amazon's pipe-joined comments are made readable ==")
check("the questionnaire answers become dots",
      rv.tidy_comment("Too Small|Width too narrow|No"),
      "Too Small · Width too narrow · No")
check("  nothing is dropped",
      rv.tidy_comment("a|b|c").count("·"), 2)
check("  and stray whitespace goes", rv.tidy_comment("  a   b \n"), "a b")
check("  an empty one stays empty", rv.tidy_comment(None), "")
_p = rv.summarise([R("2026-01-01", "A1", RUN, "APPAREL_TOO_SMALL", "SELLABLE",
                     comment="Too Small|Length too short|No")])
falsy("the raw comment list has no pipes left",
      "|" in _p["comments"][0]["text"])
truthy("  and the themes read the same tidied text",
       "·" in ri.comment_themes([R("2026-01-01", "A1", RUN, "APPAREL_TOO_SMALL",
                                   "SELLABLE",
                                   comment="Too Small|Length too short|No")]
                                )["themes"][0]["quotes"][0])
truthy("there is one definition of it", hasattr(rv, "tidy_comment"))
truthy("  and returns_intel calls it", "_rv.tidy_comment" in
       read("domain", "returns_intel.py"))

print("\n== a 180-character product title does not make a row 12 lines tall ==")
_C = read("static", "css", "dashboard.css")
truthy("there is a clamp class", ".ri-name{" in _C)
truthy("  of two lines", "-webkit-line-clamp:2" in _C)
truthy("  with the full title in the tooltip", 'class="ri-name" title="' in J)
# Five tables on this screen print a product title: product lines, parents,
# months, SKUs, and the at-risk list. All five clamp.
check("  used by every table that shows one", J.count('class="ri-name"'), 5)
check("  and the width is on the CELL, not the clamped box",
      J.count('class="ri-namecell"'), 5)
truthy("    which is why the returns figure no longer prints through the name",
       ".ri-namecell{ width:" in _C)

print("\n== the sizing cause has a colour of its own ==")
truthy("it is in the map", '"Sizing & Fit":' in J)
falsy("  so it is not drawn as Unclassified grey",
      '"Sizing & Fit":        "#8b90a0"' in J)

print("\n== adding the quality file does not delete the returns ==")
# It used to call returnsLoad(), which PULLS FROM AMAZON -- so on an account
# whose returns had been uploaded, adding a file emptied the page.
falsy("the quality upload no longer re-pulls from Amazon",
      "returnsQualityFile" in J and "returnsLoad();" in J.split(
          "async function returnsQualityFile")[1].split("\n}")[0])
truthy("  it renders the answer it was given",
       "RET.data = j; returnsRender();" in J.split(
           "async function returnsQualityFile")[1][:1400])
truthy("  which the route rebuilds whole", "out.update(counts)" in _rt)

print("\n== the findings are derived, and there is one set of them ==")
IN2 = ri.build(RETURNS, S, None, SOLD, QUALITY)
titles = [x["title"] for x in IN2["insights"]]
truthy("fit is called out", any("Fit is" in t for t in titles))
truthy("  with the real share in the title", any("86.1" in t for t in titles))
truthy("the badge is called out", any("badge" in t.lower() for t in titles))
truthy("  the rising line too", any("worse" in t for t in titles))
for x in IN2["insights"]:
    truthy("  '%s...' carries a figure" % x["title"][:30],
           any(ch.isdigit() for ch in x["body"]))
    truthy("    and something to do", len(x.get("action") or "") > 20)
truthy("the worst line needs to be BIG enough to be worst",
       "share" in read("domain", "returns_intel.py").split(
           "the worst product line")[1][:900])
# A sliver at a huge rate must not outrank a real line.
_sliver = list(RETURNS) + [R("2026-05-01", "Z9", "Tiny Thing - One",
                             "DEFECTIVE", "DEFECTIVE")]
_ss = {"Z9": {"units": 1, "sales": 10.0}}
_ss.update(SOLD)
_si = ri.build(_sliver, rv.summarise(_sliver, _ss), None, _ss, None)
falsy("a 1-of-1 product is not named the worst line",
      any("Tiny Thing" in x["title"] for x in _si["insights"]))

print("\n== the screen and the workbook say the same thing ==")
J = read("static", "js", "returns.js")
truthy("the screen reads the server's findings", "intel.insights" in J)
falsy("  and no longer derives its own",
      "nature_actions || {})[r.name]" in J)
AP = IN2["action_plan"]
check("every finding becomes a plan row", len(AP), len(IN2["insights"]))
check("  a high one is CRITICAL", AP[0]["priority"], "CRITICAL")
for a in AP:
    truthy("  '%s...' has a scope" % a["action"][:26], a["scope"])
    truthy("    and a timeline", a["timeline"])

print("\n== the SKU table's three blank columns ==")
# They asked for keys the server has never sent. Blank on every row of every
# account, for as long as the screen has existed.
truthy("Product now reads the key that exists", 'r.name || ""' in J)
truthy("  Sold too", "r.ordered ?" in J)
falsy("  and the three that never existed are gone",
      "r.title" in J or "r.units_sold" in J or "r.top_reason" in J)
truthy("the top reason is worked out from the reasons object", "topReason(r)" in J)
truthy("sorting by a text column sorts as text", "localeCompare" in J)

print("\n== sellable is read, not re-derived, on the screen ==")
truthy("it takes the server's percentage", "d.sellable_pct" in J)
falsy("  and its own regex over disposition names is gone",
      "/sellable|good/i.test(k)" in J)

print("\n== the workbook ==")
try:
    from domain import returns_excel as rx
    wb = rx.build(S, IN2, {"account": "Test", "start": "2026-01-01",
                           "end": "2026-06-30", "source_note": "test"})
    want = ["Executive Summary", "By Parent", "By Parent — Monthly",
            "SKU Detail", "Sellable by Parent", "Return Reasons", "At Risk",
            "Action Plan"]
    check("eight sheets", wb.sheetnames, want)
    ws = wb["By Parent"]
    check("  a header row of 16 columns", ws.max_column, 16)
    _labels = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
    truthy("  the runner has a row", "Speedy Runner" in _labels)
    _r = _labels.index("Speedy Runner") + 1
    check("  with the same 31 returns the screen shows",
          ws.cell(row=_r, column=2).value, 31)
    # A RATE IS A NUMBER WITH A FORMAT, not the text "8.67%" -- otherwise the
    # column cannot be sorted, which is the only reason to export at all.
    check("  the rate is stored as a number", ws.cell(row=_r, column=4).value,
          0.1033)
    check("    formatted as a percentage",
          ws.cell(row=_r, column=4).number_format, "0.0%")
    ws2 = wb["By Parent — Monthly"]
    check("  a month column each, plus name, total and trend",
          ws2.max_column, 6 + 3)
    ws3 = wb["Action Plan"]
    check("  every finding is in the plan", ws3.max_row - 4, len(AP))
    # An account with no Listing Quality file must not get an empty table that
    # reads as "Amazon has flagged nothing".
    wb2 = rx.build(S, INTEL, {})
    _ar = wb2["At Risk"]
    truthy("  without the quality file the At Risk sheet says why",
           "no Listing Quality" in str(_ar.cell(row=2, column=1).value or ""))
    data = rx.to_bytes(S, IN2, {})
    truthy("  it serialises", len(data) > 8000)
    check("    as a real xlsx", data[:2], b"PK")
except ImportError as e:
    print("     (openpyxl not installed: %s)" % e)

print("\n== a sheet that throws costs one sheet, not the download ==")
try:
    from domain import returns_excel as rx2
    broken = dict(IN2)
    broken["parents"] = [{"label": None, "returns": "not a number",
                          "monthly": None, "reasons": None}]
    wb3 = rx2.build(S, broken, {})
    check("still eight sheets", len(wb3.sheetnames), 8)
except ImportError:
    pass
except Exception as e:
    fails.append("a bad row took the whole workbook down")
    print("  FAIL: %s" % str(e)[:200])

print("\n== the route ==")
truthy("there is a download", "/returns/export.xlsx" in _rt)
truthy("  and a place to put the quality file", "/returns/quality" in _rt)
truthy("the quality file is recognised by its columns, not its name",
       "return badge" in _rt and "cx health" in _rt)
truthy("the export refuses politely when nothing is loaded",
       "nothing to export yet" in _rt)
falsy("  rather than sending an empty workbook",
      "return Response(b\"\"" in _rt)
truthy("the workbook is never cached", '"Cache-Control": "no-store"' in _rt)
truthy("  and is sent as a real attachment", "attachment; filename=" in _rt)
truthy("the analysis is kept so the export matches the screen", "_LAST" in _rt)
truthy("  and the memory is capped", "_LAST_MAX" in _rt)
H = read("templates", "dashboard.html")
truthy("the buttons are on the page", "returnsExport()" in H)
truthy("  including the quality upload", "returnsQualityOpen()" in H)
truthy("  which names where to find it in Seller Central",
       "Voice of the Customer" in H)

print("\n== against the real footwear file, if it is still on this machine ==")
_dl = os.path.join(os.path.expanduser("~"), "Downloads", "667160020686.csv")
if os.path.exists(_dl):
    import csv
    with io.open(_dl, encoding="utf-8", errors="replace", newline="") as fh:
        _rd = csv.reader(fh)
        _h = next(_rd)
        _rows = list(_rd)
    _ret, _kind, _skip = rv.parse_rows(_h, _rows)
    check("11,509 returns", len(_ret), 11509)
    check("  read as FBA", _kind, "fba")
    check("  none skipped", _skip, 0)
    _s = rv.summarise(_ret)
    check("  5,388 too small", _s["reasons"]["APPAREL_TOO_SMALL"], 5388)
    check("  1,835 too large", _s["reasons"]["APPAREL_TOO_LARGE"], 1835)
    check("  7,223 about fit", _s["natures"]["Sizing & Fit"], 7223)
    check("  92.1% sellable", _s["sellable_pct"], 92.1)
    _i = ri.build(_ret, _s, None, None, None)
    check("  eight months", len(_i["months"]), 8)
    truthy("  the last one is part-finished", _i["partial_last_month"])
    truthy("  more than 10,000 comments were read",
           _i["themes"]["comments_read"] > 10000)
    truthy("  and the biggest theme is sizing",
           "small" in _i["themes"]["themes"][0]["theme"].lower())
    _q = os.path.join(os.path.expanduser("~"), "Downloads",
                      "Listing_Summary_Report.csv")
    if os.path.exists(_q):
        with io.open(_q, encoding="utf-8-sig", errors="replace",
                     newline="") as fh:
            _lsr = list(csv.DictReader(fh))
        _ar = ri.at_risk(_lsr)
        # AMAZON'S OWN COLUMN gives 43 "At risk" ROWS and 54 "Yes" rows out of
        # 552 -- but a row is a SKU and the badge is on the LISTING, so those
        # 97 rows are 82 listings. Both figures are true; this is the one you
        # can act on, which is why it is the one shown.
        check("  34 listings at risk", sum(1 for a in _ar
                                           if a["state"] == "at risk"), 34)
        check("  48 already badged", sum(1 for a in _ar
                                         if a["state"] == "badge showing"), 48)
        check("  from 97 rows in Amazon's file",
              sum(a["sku_rows"] for a in _ar), 97)
        # THE FIGURE THE OLD RULE PRODUCED, kept as the thing not to go back to.
        truthy("  not the 470 a 15% threshold gave", len(_ar) < 200)
else:
    print("     (the returns file is not in Downloads — the rest still stands)")

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
