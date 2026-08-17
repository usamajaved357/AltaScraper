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
truthy("margin and ROI have their own columns", "'Margin', 'ROI'" in JS)
truthy("  coloured against their own thresholds",
       "_ordPct(r.margin_pct, 20, 8" in JS and "_ordPct(r.roi_pct, 30, 12" in JS)
truthy("  and neither is invented when unknown",
       'return \'<span class="cc" style="opacity:.5">—</span>\'' in JS)
truthy("the account column only appears when there is more than one",
       "_multi ? ['Account'] : []" in JS)
truthy("the table is narrower than it was", "min-width:760px" in JS)
truthy("  and no longer 900", "min-width:900px" not in JS)
truthy("the Item column gets the width, not the four-character money ones",
       "width:34%" in JS and "_narrow[t]" in JS)
truthy("  and a long product name wraps rather than being cut to nothing",
       "-webkit-line-clamp:2" in JS)

print("\n=== it shows all of that WITHOUT being asked ===")
# "i dont think my all requests are addressed, no images and details of the item
#  etc are displayed in the order tab" -- because it was opt-in and the option
# defaulted to off, so the Item column was blank until you found a button.
truthy("reading the items is ON by default", "busy: false, profit: true}" in JS)
truthy("  and the button starts in the on state",
       'class="db-chip on" id="ord_profit"' in
       open(r"D:\AltaScraper\templates\dashboard.html", encoding="utf-8").read())

print("\n--- but the list is not made to wait for it ---")
truthy("the list is drawn first, then the items fill in",
       "ordersFillItems(mine)" in JS and "SECOND PASS" in JS)
truthy("the second pass does NOT refetch the order list",
       "/orders/items" in JS and '"/orders/list?" + asked' not in JS)
truthy("  it sends the orders already on screen",
       "orders: rows.map(" in JS)
truthy("a stale answer is dropped, not merged onto a screen that moved on",
       "if(mine !== ORD.loadId) return;" in JS)
truthy("and a reload is never silently dropped while one is running",
       "ORD.loadId = (ORD.loadId || 0) + 1" in JS and "if(!body) return;" in JS)

print("\n=== the picture is resolved by the SERVER ===")
# It was matched in the page against LIVE_ITEMS -- the catalogue the LISTINGS
# screen loads. Open Orders directly, as anyone does, and that array is empty:
# every row had a name and a grey placeholder. Measured: 0 pictures on 35 rows.
R = open(r"D:\AltaScraper\routes\orders_routes.py", encoding="utf-8").read()
truthy("the row carries its own image", 'it["img"] = (pics.get(' in R)
truthy("  from the same snapshot the listing cards use", "live_snapshots" in R)
truthy("  matched on SKU before ASIN",
       '_key(it.get("sku"))\n                             or pics.get(_key(it.get("asin")))' in R
       or 'pics.get(_key(it.get("sku")))' in R)
truthy("the page still falls back to its own catalogue",
       "if(item.img) return item.img;" in JS and "LIVE_ITEMS" in JS)

print("\n=== a failed read is counted, not swallowed ===")
truthy("unread orders are counted", "unread += 1" in R)
truthy("  and reported", "could not be read from Amazon" in R)
truthy("the items route reports its own unread count",
       "could not be read from Amazon" in R and '"unread": unread' in R)
truthy("  and one definition of what an order earned, not two",
       R.count("_ov.profit_detail(") == 2 and R.count("def profit_detail") == 0)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
