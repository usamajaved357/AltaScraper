"""ORDERS_REDESIGN_TASK.md: the expanded order, in about a third of the room.

WHAT THIS FILE IS GUARDING is that a layout change stayed a layout change.

The panel is built from the same `d` the old one was -- same call, same route,
same server figures. The row above it already shows the profit, the margin and
the ROI, so a panel that worked those out again could disagree with the row it
is attached to; every check below that says "not computed here" is protecting
that (CLAUDE.md Rule 12).

AND THAT NOTHING WAS QUIETLY LOST. Four sections became five compact blocks,
which is the kind of change where a fact goes missing and nobody notices for a
month. The four questions -- what was ordered, where to buy it, what it earned,
where it is going -- are each asserted to still have an answer.

THREE BUTTONS THE BRIEF ASKS FOR ARE NOT HERE. "Ship now", "Print label" and
"Invoice": this app has no shipping flow, no label endpoint and no invoice
generator, and there is no route for any of the three. On an order screen a
"Ship now" that silently does nothing is the worst possible button (Rule 4), so
their ABSENCE is asserted rather than left to drift back in.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def rd(p):
    return io.open(os.path.join(HERE, *p.split("/")), encoding="utf-8").read()


P = rd("static/js/orders_panel.js")
O = rd("static/js/orders.js")
CSS = rd("static/css/orders_panel.css")
DASH = rd("static/css/dashboard.css")
HTML = rd("templates/dashboard.html")

# The comments quote what was replaced, so every "no longer does X" check reads
# the code with them stripped.
PCODE = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", P, flags=re.S))
OCODE = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", O, flags=re.S))


def fn(src, name):
    i = src.find("function " + name + "(")
    if i < 0:
        return ""
    j = src.find("\n}", i)
    return src[i:] if j < 0 else src[i:j + 2]


def rule(css, sel):
    i = css.find(sel)
    return css[i + len(sel):css.find("}", i)] if i >= 0 else ""


print("=== it rearranges; it does not fetch or compute ===")
truthy("the panel has its own file", len(P) > 0)
truthy("  and is wired in", "static/js/orders_panel.js" in HTML)
truthy("  with its stylesheet", "static/css/orders_panel.css" in HTML)
# NO SECOND SOURCE OF ANYTHING.
falsy("it makes no request of its own", "fetch(" in PCODE)
# No module-level mutable state: the panel is a pure function of what it is
# handed, so two orders opened in succession cannot leak into each other.
falsy("  and holds no state at module level",
      re.search(r"^(let|var)\s+\w+", PCODE, re.M) is not None)
# The row above shows profit, margin and ROI. The panel must show the SAME ones.
truthy("profit comes from the server's totals", "t.profit" in PCODE)
truthy("  margin and ROI come off the row", "r.margin_pct" in PCODE and "r.roi_pct" in PCODE)
falsy("  neither is worked out here",
      re.search(r"(profit|margin|roi)\s*=\s*[^;]*[*/][^;]*revenue", PCODE, re.I) is not None)

print("\n=== 2a. the bar is proportional, and honest about gaps ===")
truthy("there is a stacked bar", "function _opBar" in P)
truthy("  cost, fee and what is left", all(c in P for c in ("bar-cost", "bar-fee", "bar-profit")))
truthy("  a loss gets its own segment", "bar-loss" in P)
# THE ONE THAT MATTERS: a missing segment silently gives its width to the
# others, so an order with no recorded cost would look like the best on screen.
truthy("nothing is drawn unless all three parts are known",
       "cost === null || fee === null || profit === null" in P)
truthy("  and why is written down", "look like the best one on the screen" in CSS
       or "the most profitable one" in P)
# THE BRIEF'S HEX VALUES ARE APPROXIMATIONS OF TOKENS THIS APP ALREADY HAS.
for hexv in ("#4a8c6f", "#c0392b", "#7fd1a0"):
    falsy("the brief's %s is not hardcoded" % hexv, hexv in CSS)
truthy("  the app's own tokens are used", "var(--ok)" in CSS and "var(--red)" in CSS)
check("the bar is 24px", "height:24px" in rule(CSS, ".o-bar{"), True)

print("\n=== 2b. four cards, saying the same as the row ===")
truthy("the cards exist", "function _opCards" in P)
for label in ("Profit", "ROI", "Margin", "Handling"):
    truthy("  card: " + label, '"' + label + '"' in P or ("Profit at " in P and label == "Profit"))
truthy("the value is 16px bold", "font-size:16px" in rule(CSS, ".o-card-v{"))
truthy("  the label 9px uppercase", "font-size:9px" in rule(CSS, ".o-card-l{")
       and "text-transform:uppercase" in rule(CSS, ".o-card-l{"))
truthy("  on the sidebar ground with a line round it",
       "background:var(--sidebar)" in rule(CSS, ".o-card{")
       and "border:1px solid var(--line)" in rule(CSS, ".o-card{"))
# A MISSING PROFIT IS A DASH WITH A REASON, not a zero.
truthy("no profit shows a dash", "dash" in fn(P, "_opCards"))
truthy("  and says why it is blank", "counting the missing cost as nothing" in P)

print("\n=== 2c. only the actions that exist ===")
truthy("Amazon's own order page", "Amazon order" in P)
truthy("  built from listings.js's domain table, not a second copy",
       "_amzTld(" in P)
truthy("  and omitted rather than guessed if that is missing",
       "catch(e){ return \"\"; }" in P)
truthy("buy from the supplier", "Buy from supplier" in P)
# NOT RE-SORTED HERE, or this button and the table under it could name
# different suppliers.
truthy("  the cheapest one the sources block already flagged", "o.cheapest" in P)
# THE THREE THAT DO NOT EXIST.
for missing in ("Ship now", "Print label", "Invoice"):
    falsy("no '%s' button was invented" % missing, missing in PCODE)
_pflat = re.sub(r"\s+", " ", re.sub(r"^\s*(//|\*)\s?", "", P, flags=re.M))
truthy("  and their absence is explained",
       "no shipping flow, no label endpoint" in _pflat)

print("\n=== 2e. one line where a five-column table was ===")
truthy("the flow line exists", "function _opFlow" in P)
for step in ("Buyer paid", "Amazon fee", "Cost", "Profit"):
    truthy("  step: " + step, '"' + step + '"' in P)
# A MULTI-ITEM ORDER KEEPS THE TABLE. The flow line can show one sum; hiding a
# second product's numbers would be losing data, not compressing it.
truthy("a multi-item order still gets the full table",
       "(bd.lines || []).length > 1" in P and "_ordBreakdownHtml(" in P)
truthy("  and the reason is written down", "losing data rather than compressing it" in P)
# The cost correction moved inline and kept its rules.
truthy("the cost box moved onto the flow", "function _opCostBox" in P)
truthy("  through the same endpoint, unchanged", "ordSetOrderCogs(" in P)
truthy("  still per unit and per order", "for this order only" in P)
truthy("  and blank still clears it", "not known" in fn(P, "_opCostBox"))

print("\n=== 2f. delivery on one line ===")
truthy("one line", "function _opDelivery" in P)
for fact in ("Post by", "Must arrive by", "Going to"):
    truthy("  " + fact, '"' + fact in P)
truthy("  absent rather than blank when Amazon did not say",
       "if(!bits.length) return" in P)
truthy("  10px and muted", "font-size:10px" in rule(CSS, ".o-deliv{"))
truthy("  with one separator above it", "border-top" in rule(CSS, ".o-deliv{"))

print("\n=== 2g. the pills say what kind of fact each figure is ===")
truthy("badges exist", "function _opBadges" in P)
# THE ONE THAT MATTERS: an estimated fee and a settled one both print as money.
truthy("a settled fee is told from an estimated one", "Fee settled by Amazon" in P
       and "Fee estimated at" in P)
truthy("  lines with no cost are named", "with no cost" in P)
truthy("  and a buyer charged more than the lines add up to", "in total" in P)
truthy("green for ok, amber for warn", ".o-badge.ok{" in CSS and ".o-badge.warn{" in CSS)
truthy("  9px with a border", "font-size:9px" in rule(CSS, ".o-badge{"))

print("\n=== 1 and 5. the collapsed row got tighter ===")
truthy("the headings carry a sub-line", "_COLSUB" in O)
for col, sub in (("Item", "product, SKU"), ("Order", "ID, units"),
                 ("Placed", "date, fulfilment")):
    truthy("  %s / %s" % (col, sub), '"' + sub + '"' in O)
truthy("  drawn with the listings table's own class", 'class="th-sub"' in O)
truthy("  which is styled for this table too", "table.ordtable th .th-sub{" in DASH)
# SENTENCE CASE. The app-wide `table th{text-transform:uppercase}` was shouting
# headings that were already written in sentence case.
truthy("the headings stop shouting", "text-transform:none" in rule(DASH, "table.ordtable th{"))
truthy("the cells are 7px in", "padding:7px 10px" in rule(DASH, "table.ordtable td{"))
truthy("  and so are the headings", "padding:7px 10px" in rule(DASH, "table.ordtable th{"))

print("\n=== 4. one row open at a time, as it already was ===")
truthy("the open row is a single value", "ORD.open ===" in OCODE)
truthy("  and the opened row is marked", "ordrow.isopen" in DASH)
truthy("  with the panel reading as part of it",
       "tr.orddetail > td{" in DASH)

print("\n=== nothing is half-written ===")
check("orders_panel.css braces balance", CSS.count("{"), CSS.count("}"))
check("dashboard.css braces balance", DASH.count("{"), DASH.count("}"))
falsy("no mojibake", re.search(r"â€|Â·|â•", P + CSS) is not None)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
