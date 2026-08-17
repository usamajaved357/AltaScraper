"""The coupon, and the two opposite-looking treatments that are both correct.

"the profit should be calculated after cutting the promotional charges, the
 coupon or some discount applied on that order if that is not already done ...
 please check the authenticity of this claim first and then apply if i am correct
 dont guess or assume"

Checked, not assumed, on SEVEN real discounted orders across two accounts:

    jack_uk        026-1374880-3466755   21.80 - 0.91 = 20.89 = OrderTotal
    nestwell_goods 206-9874023-3627501   29.99 - 1.50 = 28.49 = OrderTotal
                   202-2446893-7679542   29.99 - 1.50 = 28.49 = OrderTotal
                   202-3734845-7261964   29.99 - 1.50 = 28.49 = OrderTotal
                   203-9865692-8949959   29.99 - 1.50 = 28.49 = OrderTotal
                   202-4024015-1547522   34.99 - 1.75 = 33.24 = OrderTotal
                   203-9384660-6187507   34.99 - 1.75 = 33.24 = OrderTotal

Nestwell runs a 5% coupon on the AltaboltaVoo Ceiling Fan, which is how this got
confirmed at a second price point after the fan went 29.99 -> 34.99. All seven
agree to the penny.

THE ANSWER IS DIFFERENT FOR THE TWO FEEDS, and both are right:

    Orders API   OrderTotal is what the buyer was CHARGED. The coupon is already
                 out. Subtracting it again charges it twice.
    Finances API ItemChargeList Principal and PromotionList are SEPARATE
                 entries, so revenue is GROSS. The coupon must come off.

The rule is not "always subtract the coupon". It is "know what your revenue
figure already includes". This test exists so a later reader who finds one half
does not go and "fix" the other.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from domain import orders_view as OV
from domain import order_profit as OP

print("=== the order row: OrderTotal is already net, so nothing is re-deducted ===")
# The Nestwell fan, exactly as Amazon reports it.
ITEMS = [{"sku": "AltaboltaVoo Ceiling Fan", "qty": 1, "price": 29.99,
          "promo": 1.50}]
cost_of = lambda s: (18.00, "sku")

d = OV.profit_detail(ITEMS, 28.49, cost_of)     # 28.49 = what the buyer paid
check("Amazon's cut is 15% of what the buyer actually paid", d["fees"], 4.27)
check("cost of the fan", d["cogs"], 18.0)
check("profit = 28.49 - 4.27 - 18.00", d["profit"], 6.22)
check("  margin on the discounted price", d["margin_pct"], 21.8)
check("  and the return on the stock", d["roi_pct"], 34.6)

# The double-count this guards against: subtracting the 1.50 again would give
# 4.72, a fifth less, and would make a working coupon look unaffordable.
truthy("the coupon is NOT taken off a second time", d["profit"] > 6.0)
check("  taking it off twice would have given this instead",
      round(6.22 - 1.50, 2), 4.72)

print("\n--- the gross price is NOT what the row starts from ---")
gross = OV.profit_detail(ITEMS, 29.99, cost_of)
truthy("using the pre-coupon price overstates the profit",
       gross["profit"] > d["profit"])
check("  by the coupon, less the fee no longer charged on it",
      round(gross["profit"] - d["profit"], 2), 1.27)
# 1.50 of coupon less 0.23 of referral fee: 15% of 29.99 rounds to 4.50 and 15%
# of 28.49 to 4.27. The penny is the rounding, and pinning 1.28 here would have
# been my arithmetic rather than the code's.

print("\n--- and it is written down where someone would come to change it ---")
V = open(r"D:\AltaScraper\domain\orders_view.py", encoding="utf-8").read()
truthy("the measurement is recorded", "26.89" in V or "20.89" in V)
truthy("  with the seven orders it was measured on",
       "206-9874023-3627501" in V and "026-1374880-3466755" in V)
truthy("  both price points of the Nestwell coupon",
       "28.49" in V and "33.24" in V)
truthy("  and the warning against double-counting",
       "MUST NOT BE TAKEN OUT AGAIN" in V)
truthy("  pointing at the feed that DOES subtract it", "order_profit.py" in V)

print("\n=== the finance path: revenue is gross, so the coupon comes off ===")
LINES = [{"order_id": "A", "sku": "X", "units": 1, "principal": 29.99,
          "tax": 0.0}]
got = OP.for_lines(LINES, 0.15, charge_of=lambda s: (18.00, "sku"),
                   promos_by_order={"A": 1.50})
check("the promotion is counted", got["promos"], 1.5)
truthy("  and taken out of the profit", "promos" in
       open(r"D:\AltaScraper\domain\order_profit.py", encoding="utf-8").read())

without = OP.for_lines(LINES, 0.15, charge_of=lambda s: (18.00, "sku"))
check("no promotion reported means none deducted", without["promos"], 0.0)
check("  and the profit is higher by exactly the coupon",
      round(without["profit"] - got["profit"], 2), 1.5)
# Not by 1.50 plus a fee: on this feed Amazon has already charged the referral
# fee on the FULL principal, so the coupon is a straight cost.

print("\n--- counted once per ORDER, never once per line ---")
TWO = [{"order_id": "A", "sku": "X", "units": 1, "principal": 15.00, "tax": 0.0},
       {"order_id": "A", "sku": "Y", "units": 1, "principal": 14.99, "tax": 0.0}]
two = OP.for_lines(TWO, 0.15, charge_of=lambda s: (9.00, "sku"),
                   promos_by_order={"A": 1.50})
check("a two-line order is discounted once, not twice", two["promos"], 1.5)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
