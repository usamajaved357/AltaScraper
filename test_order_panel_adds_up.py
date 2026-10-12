"""The All Orders panel's line adds up to the profit printed at its end.

    OWNER, 12 Oct 2026: "the ROI and the profit numbers that the All Orders
    page shows me are not accurate."

The panel drew "Buyer paid -> Amazon fee -> Cost = Profit" from the lines' item
price (before the coupon, no postage) with no refund in it, while the profit was
worked on the order total, its VAT and its refund. On a refunded order it read
"34.99 -> -6.43 -> -13.99 = -16.22", which no reader can make add up.

Now the server sends the base it used (order_total, order_vat) and what the
refund took off (refund_net), and the panel draws all of them. And the profit
tile says what it is: order profit, before ads, cancelled orders out.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from domain import orders_view as _ov            # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def cost_of(sku):
    return (13.99, "manual-order")


ITEMS = [{"sku": "FAN", "qty": 1, "price": 36.99, "title": "Ceiling fan"}]
FEES = {"total": 6.43, "referral": 5.25}

for vat_rate, label in ((0.0, "not VAT-registered"), (0.2, "VAT-registered")):
    print("== %s ==" % label)
    bd = _ov.line_breakdown(ITEMS, 34.99, cost_of, fees=FEES, vat_rate=vat_rate)
    t = bd["totals"]
    check("the base is what the buyer paid", t["order_total"], 34.99)
    check("its VAT is sent", t["order_vat"] is not None, True)
    s = round(t["order_total"] - t["order_vat"] - t["fees"] - t["cogs"], 2)
    check("paid - VAT - fee - cost = profit", s, t["profit"])

    _ov.apply_refund(t, {"refunds": 34.99, "refund_tax": 0.0,
                         "refund_fees_returned": 4.20},
                     vat_rate=vat_rate, order_total=34.99)
    check("a refund says what it took off", t.get("refund_net") is not None, True)
    s2 = round(t["order_total"] - t["order_vat"] - t["fees"] - t["cogs"]
               - t["refund_net"], 2)
    check("  and the line still adds up after it", s2, t["profit"])

print("== the panel draws every step ==")
JS = open(os.path.join(HERE, "static", "js", "orders_panel.js"),
          encoding="utf-8").read()
flow = JS.split("function _opFlow(")[1].split("\nfunction ")[0]
check("starts from the order total", "t.order_total" in flow, True)
check("takes the VAT off", "t.order_vat" in flow, True)
check("shows the refund", "t.refund_net" in flow and "Refunded" in flow, True)

print("== the tile says what it is ==")
OJ = open(os.path.join(HERE, "static", "js", "orders.js"), encoding="utf-8").read()
check("labelled order profit, before ads",
      '"Order profit"' in OJ and "before ads" in OJ, True)
check("cancelled orders are not in it", '"canceled"' in OJ, True)
check("orders not shipped yet are said", "not shipped yet" in OJ, True)

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
