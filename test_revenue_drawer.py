"""Priority 4 of LISTINGS_FUNCTIONAL_FIXES.md: the revenue calculator.

    "Currently clicking 'Calculate revenue' navigates to the product detail
     page. Amazon opens a side drawer."

WHAT THIS FILE IS MOSTLY GUARDING IS THE RESTRAINT, not the feature.

A calculator is the easiest place in an app to end up with a second opinion
about a fee -- and it would be the one people believed, because it is the one
with "Revenue Calculator" written on it. So the checks below are largely that
nothing here works anything out: the panel asks /listing/revenue, and that route
asks domain/amazon_fees, domain/cogs and domain/listing_metrics, which are the
same three the listing row already uses (CLAUDE.md Rule 12).

AND THAT IT DOES NOT OVERSTATE WHAT IT KNOWS. The brief asks for Storage cost,
Fulfilment cost and Miscellaneous rows. This app holds none of the three per
unit. Three empty boxes would imply the total below them accounted for those
costs; it does not, and the panel says so in a sentence instead (Rule 4).
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


RT = rd("routes/revenue_routes.py")
JS = rd("static/js/revenue.js")
CSS = rd("static/css/revenue.css")
LR = rd("static/js/listrow_detailed.js")
HTML = rd("templates/dashboard.html")
DASH = rd("dashboard.py")
FEES = rd("domain/amazon_fees.py")


def code(js):
    """JavaScript without comments -- the comments quote what was replaced."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return "\n".join(l.split("//")[0] for l in js.splitlines()
                     if not l.strip().startswith(("*", "//")))


print("=== it opens a panel, and the list stays put ===")
truthy("the link opens the calculator", "revOpen(" in LR)
# THE ONE fee-link ON THE ROW. It used to call openListing, which is what took
# you away from the list. Scoped to the tag itself so the check cannot be
# satisfied -- or broken -- by an openListing anywhere else in the file.
_link = re.search(r'<span class="fee-link"[^>]*onclick="([^"]*)"', LR)
truthy("  the Calculate revenue link exists", _link is not None)
falsy("  and no longer navigates to the product page",
      _link is not None and "openListing" in _link.group(1))
truthy("  it opens the panel instead",
       _link is not None and "revOpen(" in _link.group(1))
truthy("the panel is 400px on the right", "width:400px" in CSS)
truthy("  full height beside the list", "height:100vh" in CSS)
truthy("  and slides rather than appearing", "transform:translateX(100%)" in CSS)
# The scrim is a SIBLING, so a click inside the panel cannot close it.
truthy("clicking away closes it", "rev-scrim" in CSS and 'scrim.onclick = revClose' in JS)
truthy("Escape closes it", "function _revEsc" in JS)
truthy("  but not while a number is being typed",
       't.tagName === "INPUT"' in JS)
# The z-index is chosen against the bands the app already uses.
truthy("it layers under the product page, over the list", "z-index:76" in CSS)
truthy("  and the choice is justified against the other layers",
       "chrome 10-40" in CSS)
truthy("a phone gets a sheet from the bottom", "translateY(100%)" in CSS)

print("\n=== it computes nothing ===")
# THE WHOLE POINT. Arithmetic here would be a second opinion about a fee.
_c = code(JS)
falsy("no fee arithmetic in the browser",
      re.search(r"\*\s*0\.1[0-9]|referral\s*=|\*\s*rate", _c) is not None)
truthy("every figure comes from one route", "/listing/revenue?sku=" in JS)
# Matched on unwrapped text -- the sentence spans two comment lines.
_flat = re.sub(r"\s+", " ", re.sub(r"^\s*(//|\*)\s?", "", JS, flags=re.M))
truthy("  and the reason is written down",
       "second opinion about a fee" in _flat)
# The one multiplication that IS here is net x units sold, which is not a fee.
truthy("the only sum shown is net times units sold",
       "Number(d.net) * Number(d.units_30d)" in _c)

print("\n=== the route asks the modules that already own each number ===")
truthy("Amazon's charges from the three-tier resolver",
       "_fees.breakdown_for(" in RT)
truthy("  which is the one that reads the tiers", "def breakdown_for(" in FEES)
truthy("the cost from the app's own resolver", "_resolve_cogs(wsid, sku)" in RT)
truthy("the 30-day units from the listing metrics", "_lm.for_skus(" in RT)
# OUR ASIN, NEVER THE COMPETITOR'S -- a fee quoted against somebody else's ASIN
# is a fee for their product's category (CLAUDE.md Rule 1).
truthy("our own ASIN, from the bridge that knows the difference",
       "_lm.own_asins(" in RT)
truthy("  and why that matters is recorded",
       "competitor this listing was" in RT)
falsy("  the SKU is never parsed for an ASIN here",
      re.search(r"sku\.split|_Days_|split\(\"_\"\)", RT) is not None)

print("\n=== nothing here calls Amazon ===")
# A drawer wired to oninput must not be able to spend an SP-API call per
# keystroke. breakdown_for reads the stored quote and the measured rate.
falsy("no SP-API client is built", "sp_api" in RT or "ProductPricing" in RT)
falsy("  and no quote is requested", "_fees.quote(" in RT)
truthy("  which is stated", "NOTHING HERE CALLS AMAZON" in RT)
# AND THE TYPING IS DEBOUNCED. "24.99" is five keystrokes.
truthy("typing is debounced", "REV_TIMER = setTimeout" in JS)
truthy("  and a stale reply for another listing is dropped",
       "if(REV_SKU !== sku) return;" in JS)

print("\n=== the referral fee is charged on what the buyer paid ===")
# amazon_fees.estimate says so in its own docstring: passing the item price
# alone understates the fee on every order with postage.
truthy("delivery is its own input", 'id="rev_ship"' in JS)
truthy("  and is added before the fee is worked out",
       "gross = round(float(price) + float(shipping), 2)" in RT)
truthy("  the row says why", "not on the item price alone" in JS)
truthy("  and the module it follows agrees",
       "item plus any postage the buyer was" in FEES)

print("\n=== which of the three tiers this is, in words ===")
truthy("the basis is shown", "_revBasis" in JS)
for tier, words in (("actual", "measured on this product"),
                    ("quoted", "Amazon’s own quote"),
                    ("", "this account’s measured rate")):
    truthy("  '%s' is spelled out" % (tier or "estimated"), words in JS)
truthy("with the detail on hover", "d.fees.detail" in JS)

print("\n=== a fee that is NOT charged is shown, not dropped ===")
# "FBA 0.00, you post this yourself" answers a question a missing row leaves
# open. breakdown_for returns `charged` for exactly this.
truthy("the not-charged lines are drawn", "l.charged" in JS)
truthy("  dimmed rather than hidden", ".rev-row.off{" in CSS)
truthy("  and the route returns that flag", '"charged"' in FEES)

print("\n=== what the number is NOT is said, not implied ===")
# THE BRIEF ASKS FOR THREE ROWS THIS APP CANNOT FILL.
# Checked against the CODE, not the comments -- the comment above these rows is
# the record of WHY they are absent, and searching the whole file for the words
# finds that explanation and calls it the thing it is explaining.
for absent in ("Storage", "Miscellaneous", "Fulfilment cost"):
    falsy("no empty '%s' box was drawn" % absent, absent in _c)
truthy("the omission is stated instead",
       "Postage you buy, ads, storage and returns are not in this" in JS)
truthy("  and the reason it is not called profit",
       "worse than one that names what it left out" in JS)
truthy("no cost known means no net figure, and it says so",
       "No cost is known for this SKU" in JS)

print("\n=== it is wired up ===")
truthy("the route is registered", "revenue_routes.register(" in DASH)
truthy("  with the app's own cogs resolver", "_resolve_cogs=_resolve_cogs" in DASH)
truthy("the script is loaded", "static/js/revenue.js" in HTML)
truthy("  and the stylesheet", "static/css/revenue.css" in HTML)

print("\n=== nothing is half-written ===")
check("revenue.css braces balance", CSS.count("{"), CSS.count("}"))
falsy("no mojibake", re.search(r"â€|Â·|â•", RT + JS + CSS) is not None)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
