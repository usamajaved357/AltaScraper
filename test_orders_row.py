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
truthy("reading the items is ON by default", "profit: true" in JS)
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
truthy("the row carries its own image", 'it["img"] = _cat_look(' in R)
truthy("the page still falls back to its own catalogue",
       "if(item.img) return item.img;" in JS and "LIVE_ITEMS" in JS)

print("\n--- and ONE lookup does it, for every screen that needs it ---")
# Orders needed the picture, Traffic already had a title lookup, and Sales
# needed both. Three readings of one snapshot drift: one matches SKU before
# ASIN, another only ASIN, a third folds case and the fourth does not, and the
# same product ends up with two pictures in one app. CLAUDE.md Rule 12.
truthy("orders asks the shared catalogue", "from domain import catalogue" in R)
C = open(r"D:\AltaScraper\domain\catalogue.py", encoding="utf-8").read()
truthy("  which is where the snapshot is actually read", "live_snapshots" in C)
truthy("  and SKU beats ASIN, in one place", "WHY SKU BEATS ASIN" in C)
T = open(r"D:\AltaScraper\domain\traffic_view.py", encoding="utf-8").read()
truthy("traffic asks it too", "_cat.titles(" in T)
truthy("  and no longer reads the snapshot itself",
       "live_snapshots" not in T)
S = open(r"D:\AltaScraper\routes\sales_routes.py", encoding="utf-8").read()
truthy("and so does the Sales breakdown", "_cat.index(" in S)
truthy("  giving each product row its picture and name",
       'r["img"] =' in S and 'r["title"] =' in S)
SJ = open(r"D:\AltaScraper\static\js\sales.js", encoding="utf-8").read()
truthy("  which the table then draws", "r.img" in SJ and "r.title" in SJ)

print("\n=== each account's orders stay in its own account ===")
# "i see i can see all the other account orders into jacks workspace" -- the
# route already refused to default to every account; the browser asked for
# __all__ outright, overriding it.
truthy("the default is the workspace you have open",
       'account: ""' in JS)
truthy("  and __all__ is no longer the default", 'account: "__all__"' not in JS)
H = open(r"D:\AltaScraper\templates\dashboard.html", encoding="utf-8").read()
# THE PICKER IS GONE, and with it the ability to read another company's orders
# from inside this one. It used to offer "Every account" AND an entry per
# account, and the per-account entries were the half that actually did the
# damage: pick Jack Reacherd while standing in Nestwell and the choice stuck.
#
#     "i do not want that option which enables the user to see all the orders on
#      every account by being in 1 account. i am in nestwell goods why am i able
#      to see the orders of jack reacherd this should not be happening"
truthy("there is no account picker on the orders screen",
       'id="ord_account"' not in H)
truthy("  the screen says whose orders these are instead",
       'id="ord_scope"' in H)
truthy("  and nothing fills a picker with every account",
       "sel.appendChild(o)" not in JS)
# A rule that only exists in the browser is not a rule -- the endpoint is
# reachable directly.
R0 = open(r"D:\AltaScraper\routes\orders_routes.py", encoding="utf-8").read()
truthy("the server refuses every-account outright",
       'if want == "__all__"' in R0)
truthy("  and an unresolvable account returns NOTHING, not everything",
       "return []" in R0 and "NO ACCOUNT RESOLVED MEANS NONE" in R0)
# The other half of the same fault: the rows on screen outliving the account
# they belong to.
truthy("the rows are stamped with whose they are", "ORD.rowsFor" in JS)
truthy("  and a different workspace forces a reload",
       "ORD.rowsFor !== _ws" in JS)
SS = open(r"D:\AltaScraper\static\js\screenstate.js", encoding="utf-8").read()
truthy("switching workspace forgets the orders held in memory",
       "ORD.rows = []" in SS)
truthy("  including whose they were", 'ORD.account = ""' in SS)
truthy("  and abandons any load still running", "ORD.loadId" in SS)

print("\n=== the visuals ===")
truthy("the table is in a panel like every other screen", 'class="panelcard"' in JS)
truthy("  with its spacing in the stylesheet, not in a template literal",
       "padding:6px 8px" not in JS)
CSS = open(r"D:\AltaScraper\static\css\dashboard.css", encoding="utf-8").read()
truthy("there is a rule for this table", "table.ordtable" in CSS)
truthy("  rows are separated by a line", "table.ordtable td{" in CSS)
truthy("  small print does not sit on the line above it",
       "table.ordtable td .cc{ margin-top:3px" in CSS)
truthy("  cells are centred, so a 34px picture does not float",
       "vertical-align:middle" in CSS)
truthy("  the headings stay put down a long list", "position:sticky" in CSS)

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
