"""An order row says what was sold and what it made, without being opened.

"the orders tab on the screen is too cluttered maybe it needs resizing and also
 i want to see the item picture and name of the item and profit and roi and
 margin or each order without opening the order details"

Nine columns at a 900px minimum, and the two things anyone actually wants from a
list of orders -- what was in it, and whether it was worth selling -- were the
two that were not there.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-68s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from domain import orders_view as OV

ITEMS = [{"sku": "A", "asin": "B0AAA", "title": "Grease Gun Cartridges", "qty": 2},
         {"sku": "B", "asin": "B0BBB", "title": "Second thing", "qty": 1}]
COSTS = {"A": 3.00, "B": 5.00}
cost_of = lambda s: (COSTS.get(s), "sku") if s in COSTS else (None, "")


print("=== margin and ROI are different questions, so both are answered ===")
d = OV.profit_detail(ITEMS, 30.00, cost_of)
check("cost of the stock", d["cogs"], 11.0)          # 2 x 3.00 + 1 x 5.00
check("Amazon's cut", d["fees"], 4.5)                # 15% of 30.00
check("profit", d["profit"], 14.5)
check("margin is profit over what the buyer paid", d["margin_pct"], 48.3)
check("ROI is profit over what the stock cost", d["roi_pct"], 131.8)
truthy("  and they are genuinely different numbers",
       d["margin_pct"] != d["roi_pct"])

print("\n=== an unknown cost shows NOTHING, not a partial figure ===")
# A partial cost only ever makes an order look better than it was, and the order
# whose cost is missing is exactly the one someone would use to buy more stock.
d2 = OV.profit_detail(ITEMS, 30.00, lambda s: (3.00, "sku") if s == "A" else (None, ""))
check("no profit", d2["profit"], None)
check("  no margin", d2["margin_pct"], None)
check("  no ROI either", d2["roi_pct"], None)
truthy("  and it says which SKU is missing a cost", "B" in (d2["note"] or ""))

print("\n=== free stock does not report an infinite return ===")
d3 = OV.profit_detail([{"sku": "Z", "qty": 1}], 10.0, lambda s: (0.0, "manual"))
check("ROI is undefined, not infinity", d3["roi_pct"], None)
truthy("  but the profit is still known", d3["profit"] is not None)

print("\n=== the row names what was bought ===")
s = OV.item_summary(ITEMS)
check("the first item's title", s["title"], "Grease Gun Cartridges")
check("  its sku", s["sku"], "A")
check("  its asin, for finding the picture", s["asin"], "B0AAA")
check("  and how many others there are", s["extra"], 1)
check("an empty order says nothing rather than crashing",
      OV.item_summary([])["title"], "")

print("\n=== the screen ===")
JS = open(r"D:\AltaScraper\static\js\orders.js", encoding="utf-8").read()
truthy("there is an Item column", "'Item', 'Order'" in JS)
truthy("  with a picture", "_ordItemImage(" in JS)
truthy("  taken from the catalogue already held, not a new call",
       "LIVE_ITEMS" in JS and "no extra call to Amazon" in JS)
truthy("  matched on SKU before ASIN", "norm(it.sku) === sku) return url" in JS)
truthy("margin and ROI have their own columns", "'Margin', 'ROI'" in JS)
truthy("  coloured against their own thresholds",
       "_ordPct(r.margin_pct, 20, 8" in JS and "_ordPct(r.roi_pct, 30, 12" in JS)
truthy("  and neither is invented when unknown",
       'return \'<span class="cc" style="opacity:.5">—</span>\'' in JS)
truthy("the account column only appears when there is more than one",
       "_multi ? ['Account'] : []" in JS)
truthy("the table is narrower than it was", "min-width:760px" in JS)
truthy("  and no longer 900", "min-width:900px" not in JS)
truthy("an empty item cell says WHY it is empty",
       "turn on “work out profit”" in JS and "past the profit limit" in JS)

print("\n=== a failed read is counted, not swallowed ===")
R = open(r"D:\AltaScraper\routes\orders_routes.py", encoding="utf-8").read()
truthy("unread orders are counted", "unread += 1" in R)
truthy("  and reported", "could not be read from Amazon" in R)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
