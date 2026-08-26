"""The repricer page: every supplier visible, both profit figures, bulk actions.

WHAT WAS ASKED FOR, in his words:

    "in the repricer similarly i want to be shown all the available supplier/
     source links and highlight the cheapest of all of them, and show the source
     price of the cheapest show the current selling price of the sku as selling
     price, show profit per unit when no promotion like coupon or discounts etc
     are applied and also show the profit when some coupons or promotions etc
     are applied and the app should automatically know when which promotion or
     coupon is applied and how much is applied and make the calculations
     accordingly, also show roi and margin in both cases and the handling time
     set for each item at that time and under it where the source links are
     mentioned show the delivery time of the suppliers. rest rules stays the
     same but give a button on the top of the page which explains how do this
     page works ... also allow to select multiple skus at once and unroll them
     from tracking, also give the option in the template in the repricer page to
     add multiple supplier links ... supplier 1, supplier 2 ... upto 10"

THE PART THAT NEEDED A DECISION: "the app should automatically know ... which
promotion or coupon is applied". Amazon does not expose the seller's running
coupons to this application -- there is no operation for it we are approved for.
What it does report, once an order settles, is the promotion the SELLER funded,
in the Finances API's PromotionList, and that is already stored per order.

So it is MEASURED from what buyers were actually charged, never guessed, and
every figure says so. That is asserted here, because an inferred number
presented as a setting read from Amazon would be the app claiming something it
cannot know.
"""
import io
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


J = io.open(r"D:\AltaScraper\static\js\sourcing.js", encoding="utf-8").read()
G = io.open(r"D:\AltaScraper\static\js\guide.js", encoding="utf-8").read()
R = io.open(r"D:\AltaScraper\routes\sourcing_routes.py", encoding="utf-8").read()
# The comments quote the request verbatim, so they are stripped before any
# assertion runs on "the code says X".
JS = re.sub(r"//[^\n]*", "", re.sub(r"/\*[\s\S]*?\*/", "", J))

from domain import promotions as P
from domain import source_drift as D

print("=== the coupon is MEASURED, and never claimed to be read from Amazon ===")
truthy("there is one module that answers it", hasattr(P, "measured"))
truthy("  it says Amazon does not expose running coupons",
       "does not expose" in P.__doc__ or "not hand this app a list" in P.__doc__)
truthy("  and every description repeats that, where it will be read",
       "does not tell this app which coupons are running" in P.describe(
           {"amount_per_unit": 1.0, "pct": 5.0, "orders": 3, "settled_orders": 3,
            "last_order": "2026-08-01", "exact": True}))

print("\n--- one order is an anecdote, not a coupon ---")
check("at least two settled orders are needed", P.MIN_ORDERS >= 2, True)
# NO ORDERS MEANS NO ANSWER. A product nobody has bought under a coupon and one
# with no coupon look identical from here, and "0%" would turn the first into a
# claim.
check("nothing measured -> the price is unchanged, not discounted to zero",
      P.apply_to(24.99, None), 24.99)
check("  and a measured discount comes off", P.apply_to(24.99,
      {"amount_per_unit": 1.25}), 23.74)
check("  a silly figure cannot make a negative price",
      P.apply_to(2.00, {"amount_per_unit": 99.0}), 0.0)

print("\n--- it measures the COUPON, not an average across orders without one ---")
# Measured on jack_uk: 4 of 11 settled orders carried one. Averaging all eleven
# reported "2% off" for a discount that is really about 5%, because the seven
# undiscounted orders diluted it.
truthy("orders with no discount are skipped when measuring the rate",
       "if promo <= 0:" in io.open(r"D:\AltaScraper\domain\promotions.py",
                                   encoding="utf-8").read())
truthy("  but counted, so the screen can say how often it applied",
       "settled_orders" in P.measured.__doc__ or "settled_orders" in
       io.open(r"D:\AltaScraper\domain\promotions.py", encoding="utf-8").read())

print("\n=== both sums, on every row that has a discount ===")
_rule = {"referral_rate": 0.15, "shipping_label": 0, "ads_margin": 0,
         "min_roi_pct": 20}
_pairs = [({"id": 1, "enabled": 1},
           {"status": "fetched", "price": 10.00, "shipping": 1.00,
            "in_stock": True, "dispatch_days": 3, "available_qty": 7,
            "checked_at": "2026-08-17 10:00:00"})]
plain = D.at_a_glance(_pairs, {"price": 24.99}, _rule)
check("without a coupon: what one unit costs delivered", plain["landed"], 11.0)
check("  what Amazon charges today", plain["sell_price"], 24.99)
check("  the profit on that sale", plain["profit"], 10.24)
check("  and no coupon figures are invented", plain["profit_promo"], None)

promo = {"amount_per_unit": 1.25, "pct": 5.0, "orders": 4, "settled_orders": 4,
         "units": 4, "last_order": "2026-08-14", "exact": True}
withp = D.at_a_glance(_pairs, {"price": 24.99}, _rule, promo=promo)
check("with a coupon: the full-price figures are UNCHANGED",
      (withp["profit"], withp["margin_pct"], withp["roi_pct"]),
      (plain["profit"], plain["margin_pct"], plain["roi_pct"]))
check("  and the discounted price is beside them", withp["sell_price_promo"], 23.74)
check("  with its own profit", withp["profit_promo"], 9.18)
truthy("  its own margin", withp["margin_pct_promo"] is not None)
truthy("  and its own ROI", withp["roi_pct_promo"] is not None)
truthy("  plus the sentence explaining where the figure came from",
       "settled order" in (withp.get("promo_note") or ""))
# THE COUPON MAKES IT WORSE, ALWAYS. If these ever came out equal the screen
# would be showing two identical columns and implying a coupon costs nothing.
truthy("the coupon really does reduce the profit",
       withp["profit_promo"] < withp["profit"])

print("\n=== the row draws both, and says which is which ===")
# THE SCREEN IS A TABLE NOW, so the figures that were a strip of labelled cells
# on a bordered card are split between COLUMNS -- where a header names each one
# once instead of sixty-seven times -- and the panel that opens under a row.
#
# What is asserted is the same in substance: both prices are shown, both sets of
# margin and ROI are shown, the handling time is shown, and none of the coupon
# figures appear on a SKU where no discount was measured.
truthy("the full-price price is a column of its own",
       ">Price</th>" in JS or "title=\"What it sells for on Amazon now" in JS)
truthy("  the cheapest source's two halves are columns too",
       ">Item</th>" in JS and ">Post</th>" in JS)
truthy("  and the discounted price is labelled where it appears",
       "'After coupon'" in JS)
# TWO STRIPS: the figures at the listed price, then the same figures again with
# the coupon on. Asserted by splitting on the heading between them rather than
# by counting the word "Margin" in the whole file -- the rules pills carry an
# ROI and a Margin pill too, and a count would silently pass or fail on those.
_full, _sep, _promo = JS.partition("With the coupon on")
truthy("margin and ROI appear at the listed price",
       "'Margin'," in _full and "'ROI'," in _full)
truthy("  and again with the coupon on",
       bool(_sep) and "'Margin'," in _promo and "'ROI'," in _promo)
truthy("the handling time in force is shown", "'Handling'," in JS)
truthy("  and it says the postage is NOT in that number",
       "counted by Amazon separately" in JS)
truthy("  because the decision took the postage days off",
       "postage already covers" in io.open(
           r"D:\AltaScraper\domain\sourcing.py", encoding="utf-8").read())
falsy("no coupon columns on a SKU with no measured discount",
      "if(p){" not in JS)

print("\n=== every supplier link is on the row, not behind a button ===")
truthy("the server ranks them with the ORDER screen's own function",
       "_osrc.options_for(" in R)
truthy("  and sends them with the row", '"options": _opts' in R)
# ONE RANKING, TWO LAYOUTS -- and that is the correct reading of Rule 12.
#
# The Repricer used to borrow the order panel's renderer outright. It now draws
# its own compact TABLE (_supTable), because the two screens are answering
# different questions: an order has one supplier and you want its full story,
# while the Repricer has sixty-seven SKUs and you want several suppliers lined
# up so their prices can be compared down a column.
#
# What must NOT be duplicated is the thinking, and it is not: the ranking, the
# landed cost, the "you keep" figure and the delivery sentence are all computed
# once in domain/order_sources.options_for and simply drawn twice. Two layouts
# over one calculation is not two copies of the logic.
truthy("the row draws them from the SAME ranked options",
       "function _supTable(" in JS and "r.options || []" in JS)
truthy("  keyed on the fields options_for actually returns",
       "s.source_id" in JS and "s.state === 'dead'" in JS
       and "o.state === 'buyable'" in JS)
truthy("  and it still uses the shared delivery sentence",
       "_srcDeliveryLine({" in JS)
truthy("  which puts the cheapest first and marks it",
       "odp-rank" in io.open(r"D:\AltaScraper\static\js\orders.js",
                             encoding="utf-8").read())
truthy("  and carries each supplier's delivery estimate",
       "delivery_text" in io.open(r"D:\AltaScraper\domain\order_sources.py",
                                  encoding="utf-8").read())
# A SKU WITH NO SUPPLIER SAYS SO rather than drawing an empty table. It was the
# guard against orders.js not having loaded; the renderer is local now, so the
# case that remains is the real one -- a tracked SKU nobody has linked yet.
truthy("a SKU with no supplier link says so rather than drawing nothing",
       "No supplier link on this SKU yet" in JS)

print("\n=== select several SKUs and stop tracking them at once ===")
truthy("each row has a tickbox", 'class="srcsel"' in JS)
truthy("  the selection is kept by SKU, not by row number", "SRC_SEL" in JS)
truthy("  select-all and clear exist", "sourcingSelectAll" in JS)
truthy("  the bar only appears when something is picked",
       "if(!picked.length){ el.innerHTML" in JS)
truthy("  and only counts SKUs still on screen", "shown.has(s)" in JS)
truthy("the endpoint takes many at once", "/sourcing/unenrol_bulk" in R)
truthy("  and nothing is deleted by it",
       "history are kept" in R or "supplier links and price history are kept" in R)
truthy("  which is said BEFORE the click, not after",
       "are KEPT" in J)
# Armed SKUs are the ones where this matters most.
truthy("it warns when some of them are armed", "of them armed" in JS)

print("\n=== and the white browser dialogs are gone from this page too ===")
falsy("no confirm() left in the code", "confirm(" in JS.replace("srcConfirm(", ""))
truthy("  replaced by one in the app's own skin", "function srcConfirm" in JS)
truthy("  Escape cancels it", '"Escape"' in JS)
truthy("  and it resolves like confirm(), so callers only gained an await",
       "resolve(v)" in JS)

print("\n=== the explainer button ===")
# The call sits inside a JS string that becomes an onclick attribute, so in the
# source it is escaped: openGuide(\'repricer\').
truthy("it is on the page", "openGuide(" in JS and "repricer" in JS
       and "How this page works" in JS)
truthy("  and there is a guide behind it", "repricer: {" in G)
# THE CLAIM, NOT THE SENTENCE. These pinned three exact phrasings, and all
# three went red when the guide was rewritten into lists -- while every one of
# the facts they exist to protect was still there, reworded. A test that fails
# on a synonym is protecting the prose, not the reader, so each now looks for
# the thing that must be TRUE of the guide.
_g = G.lower()
truthy("  leading with the thing that confuses people",
       "changes nothing on amazon" in _g or "nothing here changes" in _g)
truthy("  explaining what each figure means",
       "cheapest source" in _g and "what you paid" in _g
       and "selling price" in _g)
truthy("  where the coupon figure comes from",
       "measured from what buyers were" in _g and "settled orders" in _g)
truthy("  and that nothing is added that he did not enter",
       "0.00 unless you set them" in G)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
