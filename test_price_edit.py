"""Changing a live selling price from the app.

THE TRAP: purchasable_offer is not a number. It is a nest of marketplace,
audience, currency and a dated schedule, and its shape differs by product type.
dashboard._build_patches composes a minimal one of its own --

    [{"our_price": [{"schedule": [{"value_with_tax": 12.34}]}]}]

-- and the operation is REPLACE, so sending that drops the currency, the
audience and the marketplace from a live offer. Measured against a real listing,
Amazon actually holds:

    [{"audience": "ALL", "currency": "GBP",
      "marketplace_id": "A1F83G8C2ARO7P",
      "our_price": [{"schedule": [{"value_with_tax": 29.99}]}]}]

So this screen uses domain/source_apply.build_patches, which deep-copies what
Amazon returned and changes only the number inside it (CLAUDE.md Rule 4), and
which the repricer already uses -- one builder, not two opinions (Rule 12).
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

from domain import source_apply as SA

# Exactly as the live UK account returned it.
REAL = {"purchasable_offer": [{
    "audience": "ALL", "currency": "GBP",
    "marketplace_id": "A1F83G8C2ARO7P",
    "our_price": [{"schedule": [{"value_with_tax": 29.99}]}]}]}

print("=== the patch edits Amazon's own offer, it does not replace it ===")
patches, err = SA.build_patches(REAL, {"price": 32.99}, "A1F83G8C2ARO7P")
check("no error", err, "")
check("one operation", len(patches), 1)
check("  on the offer", patches[0]["path"], "/attributes/purchasable_offer")
off = patches[0]["value"][0]
check("the new price is in", off["our_price"][0]["schedule"][0]["value_with_tax"], 32.99)
# These are what a hand-built minimal offer silently drops, on a REPLACE.
check("  the currency survives", off.get("currency"), "GBP")
check("  the audience survives", off.get("audience"), "ALL")
check("  the marketplace survives", off.get("marketplace_id"), "A1F83G8C2ARO7P")
check("and the original is not mutated",
      REAL["purchasable_offer"][0]["our_price"][0]["schedule"][0]["value_with_tax"],
      29.99)

print("\n=== a shape we cannot edit is refused, never invented ===")
_p, e1 = SA.build_patches({}, {"price": 9.99}, "M")
check("no offer at all -> refused", bool(e1), True)
check("  and nothing is sent", _p, [])
_p2, e2 = SA.build_patches({"purchasable_offer": [{"audience": "ALL"}]},
                           {"price": 9.99}, "M")
check("an offer with no price schedule -> refused", bool(e2), True)
truthy("  saying why, in words", "without inventing a shape" in e2)

print("\n=== the floor is the app's own pricing rule, not a new one ===")
from listing import pricing as P
from domain import cogs as C
cost = C.cost_from_sku("10.00_2Days_B0F7X6NPLH")
check("the cost comes out of the SKU", cost, 10.0)
# THE ACCOUNT'S RULE, NOT A HARDCODED ONE. This screen used to call
# floor_from_rate(cost, 0.15) directly, which ignores every setting the owner
# made. It goes through sourcing.floor_price now -- the same function the
# repricer prices with -- so the number this screen warns about and the number
# the repricer works to cannot drift apart (Rule 12).
from domain import sourcing as SRC
floor = SRC.floor_price(cost, None)
truthy("a floor is produced", floor and floor > cost)
# Selling at cost is a loss once Amazon's cut is paid, and selling at cost plus
# the fee earns nothing at all. The floor has to clear BOTH or it protects
# nothing -- which is what the never-sell-at-break-even minimum is for.
truthy("  and it is above break-even, not merely above the cost",
       floor > cost / (1 - 0.15))
truthy("  by at least the safety return on the cash",
       P.achieved(floor, cost, 0.15)["roi_pct"] >= P.PRICING_RULE_MIN_ROI_PCT)
check("  and the old hardcoded rule would NOT have cleared it",
      P.floor_from_rate(cost, 0.15) < floor, True)
check("an unknown cost gives no floor rather than a wrong one",
      C.cost_from_sku("0.00_3Days_B0F7X6NPLH"), None)

print("\n=== the route refuses what should never reach Amazon ===")
import inspect as _i
SRC = _i.getsource(__import__("routes.price_routes", fromlist=["x"]).register)
truthy("zero and negative prices are refused", "is not a price" in SRC)
truthy("  suggesting the right tool instead", "set its stock to zero" in SRC)
truthy("the listing is read LIVE before any patch is built",
       "_live(sku, acc, mkt)" in SRC and "get_item(" in SRC)
truthy("  and a listing Amazon will not return stops it",
       "so nothing was sent" in SRC)
truthy("below the floor is refused SERVER-side, not only warned about",
       "below_floor_ok" in SRC)
truthy("  because a dialog somebody clicked through is not a control",
       "not a control" in SRC)
truthy("a workspace with no Amazon account of its own cannot change a price",
       "seller_scope_allowed" in SRC)
truthy("the change is recorded where the repricer records its own",
       "record_action" in SRC)
truthy("it uses the shared patch builder, not a second opinion",
       "_apply.build_patches" in SRC)

print("\n=== and it is gated as publishing ===")
from auth.guard import required_permission as rp
# The preview sends nothing to Amazon, so it needs only what seeing a listing
# needs. Applying changes what buyers pay.
check("preview needs nothing special", rp("/listing/price/preview", "POST"), None)
check("applying needs publish", rp("/listing/price/apply", "POST"), "publish")

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
