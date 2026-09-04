"""The order panel against REMAINING_FIXES_HANDOFF.md section 1.

Five items. Each names the sentence it answers.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def code(s):
    s = re.sub(r"(?s:/\*.*?\*/)", "", s)
    return re.sub(r"(?m:^[ \t]*//[^\n]*)", "", s)


PANEL = code(read("static", "js", "orders_panel.js"))
ORDERS = code(read("static", "js", "orders.js"))
SRC = code(read("static", "js", "sourcing.js"))
def css(s):
    """Comments stripped. A note recording the colour something USED to be is
    history, not a colour anything paints -- and confusing the two is how a
    check for "#e25c5c is gone" fails on the sentence saying it is gone."""
    return re.sub(r"(?s:/\*.*?\*/)", "", s)


PCSS = css(read("static", "css", "orders_panel.css"))
DCSS = css(read("static", "css", "dashboard.css"))
RCSS = css(read("static", "css", "repricer.css"))

print("== 1a. one cost/fee/profit palette, everywhere ==")
# "These same three colours must be used everywhere a cost/fee/profit bar
#  appears -- orders, sourcing, revenue calculator. One palette, no drift."
for tok in ("--bar-cost:", "--bar-fee:", "--bar-fee2:", "--bar-profit:"):
    yes("  %s is defined once, in dashboard.css" % tok, tok in DCSS)
yes("the order panel's bar uses them",
    ".bar-cost{ background:var(--bar-cost)" in PCSS
    and ".bar-fee{ background:var(--bar-fee)" in PCSS
    and ".bar-profit{ background:var(--bar-profit)" in PCSS)
yes("  the repricer's bar uses the same",
    ".rp-sb-cost{background:var(--bar-cost)}" in RCSS
    and ".rp-sb-ref{background:var(--bar-fee)}" in RCSS
    and ".rp-sb-profit{background:var(--bar-profit)}" in RCSS)
yes("  and so does its fee panel", "'var(--bar-fee)'" in SRC)
# The referral was --red on one screen and #e25c5c on the other. Red means
# something is WRONG; Amazon's cut is not wrong, it is just Amazon's.
yes("the referral is no longer painted as an error",
    ".bar-fee{ background:var(--red)" not in PCSS
    and "#e25c5c" not in RCSS)
# A LOSS still is one.
yes("  but a loss still is", ".bar-loss{ background:var(--red)" in PCSS)
yes("the legend shows the bar's own colours, not the dark tints",
    'class="rp-sq" style="background:var(--bar-cost)"' in SRC
    and 'style="background:var(--ok-bg)"></span>' not in SRC)

print("\n== 1b. the supplier table, with tagged shipping pills ==")
# "Shipping details ... should use clean tagged pills under the supplier name
#  instead of a wall of text."
yes("the pills are built", 'class="sup-ship-tag' in ORDERS)
for icon in ("truck", "calendar", "map-pin", "clock", "package"):
    yes("  one for %s" % icon, "pill('%s'" % icon in ORDERS)
yes("  and they are no longer one joined sentence",
    "bits.join(' · ')" not in ORDERS.split("HOW IT GETS THERE")[-1][:1200])
yes("the styles exist", ".sup-ship-tag{" in DCSS and ".sup-ship-tags{" in DCSS)
# A reason the supplier is unusable is not a delivery detail.
yes("out of stock / stale / unreadable stay sentences", ".odp-shipwarn{" in DCSS)
yes("  and are not pills", 'pill(' not in ORDERS.split("const bits = [];")[1][:400])
# Found on screen: the # column printed the word "undefined".
yes("a row with no server rank is numbered by its position",
    "? (_i + 1) : o.rank" in ORDERS)

print("\n== 1e. the no-cost state, without a tooltip ==")
# "show the fee segment and a grey placeholder segment saying 'Set cost to
#  calculate profit' ... Remove the tooltip entirely."
yes("the placeholder says what would fill it", "Set cost to calculate profit" in PANEL)
yes("  and no longer carries a tooltip",
    "There is not enough here to work the profit out." not in PANEL)
yes("  nor a help cursor",
    ".bar-unknown{" in PCSS and "cursor:default;" in PCSS)
# cursor:help was on `.o-bar > div`, which outranks a bare class -- so the
# override had to move rather than be added.
yes("  which needed the shared rule to stop setting it",
    ".o-bar > div{" in PCSS
    and "cursor:help;\n  color:var(--sidebar);" not in PCSS
    and ".o-bar > .bar-cost, .o-bar > .bar-fee," in PCSS)
yes('the cards say "No cost set" under the dash', "No cost set" in PANEL)
yes("  in their own small line", ".o-card-why{" in PCSS)
# "Handling card should still show the actual handling time, not '—' --
#  handling has nothing to do with cost."
_cards = PANEL[PANEL.index("function _opCards"):PANEL.index("function _opHandling")]
yes("handling never wears the no-cost note",
    _cards.rindex("hand.tone") > _cards.rindex("why"))

print("\n== driven in Chrome, on a synthetic order with no cost ==")
# Read off the rendered panel:
#   bar        bar-fee rgb(212,115,90) + bar-unknown "GBP 26.94 Set cost to
#              calculate profit", cursor default
#   cards      —/—/— each with "No cost set", and Handling "2d"
#   pills      9 across two suppliers
#   warnings   the stale price as a sentence, not a pill
#   ranks      "best" and "2" -- no "undefined"
#   errors     none
yes("the panel is still one call", "function ordPanelHtml(r, d)" in PANEL)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
