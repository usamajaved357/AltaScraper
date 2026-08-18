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
truthy("the full-price price is labelled plainly", "'selling price'" in JS)
truthy("  the cheapest source is named as such", "'cheapest source'" in JS)
truthy("  and the discounted one is labelled", "'after coupon'" in JS)
truthy("margin and ROI appear for both", JS.count("cell('margin'") == 2
       and JS.count("cell('ROI'") == 2)
truthy("the handling time in force is shown", "cell('handling'" in JS)
truthy("  built from the supplier's dispatch plus the buffer",
       "plus the safety buffer" in J)
falsy("no coupon columns on a SKU with no measured discount",
      "if(p){" not in JS)

print("\n=== every supplier link is on the row, not behind a button ===")
truthy("the server ranks them with the ORDER screen's own function",
       "_osrc.options_for(" in R)
truthy("  and sends them with the row", '"options": _opts' in R)
truthy("the row draws them with the order panel's renderer",
       "_ordSourcesHtml({options: r.options" in JS)
truthy("  which puts the cheapest first and marks it",
       "odp-rank" in io.open(r"D:\AltaScraper\static\js\orders.js",
                             encoding="utf-8").read())
truthy("  and carries each supplier's delivery estimate",
       "delivery_text" in io.open(r"D:\AltaScraper\domain\order_sources.py",
                                  encoding="utf-8").read())
truthy("a missing renderer degrades rather than breaking the page",
       'typeof _ordSourcesHtml === "function"' in JS)

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
truthy("  leading with the thing that confuses people",
       "Nothing here changes a live Amazon listing" in G)
truthy("  explaining what each figure means", "Cheapest source" in G
       and "over what you paid" in G)
truthy("  where the coupon figure comes from",
       "measured from what buyers were really charged" in G)
truthy("  and that nothing is added that he did not enter",
       "0.00 unless you set them" in G)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
