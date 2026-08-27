"""What actually gets sent to Amazon, and what deliberately does not.

    "if the prices dont need to be changed i think repricer should not change
     anything, if a price change is required yes we should do it. the stock
     update is requured, yes do it"

The repricer used to patch the price on EVERY push, because a decision always
carries one. So a run whose only real change was putting stock back to three
also rewrote the price to the number it already was -- arithmetically harmless,
and not harmless at all: it is an edit to a live offer, it appears in Amazon's
own change history, and it makes "the repricer changed my price" true on a day
when it changed nothing.

The two halves are independent now. These check that, both ways round, because
the failure that matters is not "it sent too much" -- it is "in making it send
less, it stopped sending the stock".
"""
import copy
import sys

sys.path.insert(0, r"D:\AltaScraper")
from domain import source_apply as AP        # noqa: E402

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    print("  %-58s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def attrs(price, qty, lead=3):
    """What Amazon hands back for a live FBM offer, in its own shape."""
    return {
        "purchasable_offer": [{
            "our_price": [{"schedule": [{"value_with_tax": price}]}],
        }],
        "fulfillment_availability": [{
            "fulfillment_channel_code": "DEFAULT",
            "quantity": qty,
            "lead_time_to_ship_max_days": lead,
        }],
    }


def paths(patches):
    return sorted(p["path"].rsplit("/", 1)[-1] for p in patches)


MKT = "A1F83G8C2ARO7P"

print("=== the price moves: the price is sent ===")
p, err = AP.build_patches(attrs(15.49, 3), {"price": 15.63, "quantity": 3,
                                            "lead_days": 3}, MKT)
check("no error", err, "")
check("only the offer is patched", paths(p), ["purchasable_offer"])

print("\n=== the price does not move, the stock does: STOCK ONLY ===")
# This is the case he asked for. Stock has gone to 0 on Amazon; the price is
# already right. The offer must not be touched.
p, err = AP.build_patches(attrs(15.63, 0), {"price": 15.63, "quantity": 3,
                                            "lead_days": 3}, MKT)
check("no error", err, "")
check("only availability is patched", paths(p), ["fulfillment_availability"])
check("  and it carries the new quantity",
      p[0]["value"][0]["quantity"], 3)

print("\n=== nothing differs: nothing is sent ===")
p, err = AP.build_patches(attrs(15.63, 3), {"price": 15.63, "quantity": 3,
                                            "lead_days": 3}, MKT)
check("no patches", p, [])
check("and it says so", err, "there is nothing to change")

print("\n=== both differ: both are sent ===")
p, err = AP.build_patches(attrs(15.49, 0), {"price": 15.63, "quantity": 3,
                                            "lead_days": 3}, MKT)
check("two patches", paths(p),
      ["fulfillment_availability", "purchasable_offer"])

print("\n=== a float read back from Amazon is not a price change ===")
# 15.629999999999999 is the same price as 15.63. Compared with a bare != it is
# not, and every push for ever would rewrite the price to itself -- which is
# precisely the behaviour being removed.
p, err = AP.build_patches(attrs(15.629999999999999, 3),
                          {"price": 15.63, "quantity": 3, "lead_days": 3}, MKT)
check("no patches", p, [])
check("and it says so", err, "there is nothing to change")
# ...but a penny IS a change.
p, err = AP.build_patches(attrs(15.62, 3), {"price": 15.63, "quantity": 3,
                                            "lead_days": 3}, MKT)
check("one penny is still a change", paths(p), ["purchasable_offer"])

print("\n=== the handling time on its own ===")
p, err = AP.build_patches(attrs(15.63, 3, lead=3),
                          {"price": 15.63, "quantity": 3, "lead_days": 5}, MKT)
check("availability only", paths(p), ["fulfillment_availability"])
check("  carrying the new handling time",
      p[0]["value"][0]["lead_time_to_ship_max_days"], 5)

print("\n=== going out of stock still goes ===")
# quantity 0 against a listing showing 3: the out-of-stock path must survive
# the same-value check, or a supplier running dry would stop reaching Amazon.
p, err = AP.build_patches(attrs(15.63, 3), {"price": None, "quantity": 0,
                                            "lead_days": None}, MKT)
check("availability is patched", paths(p), ["fulfillment_availability"])
check("  with zero", p[0]["value"][0]["quantity"], 0)

print("\n=== a missing quantity is set, not skipped ===")
a = attrs(15.63, 3)
del a["fulfillment_availability"][0]["quantity"]
p, err = AP.build_patches(a, {"price": 15.63, "quantity": 3,
                              "lead_days": 3}, MKT)
check("availability is patched", paths(p), ["fulfillment_availability"])

print("\n=== the shapes Amazon refuses are still refused ===")
p, err = AP.build_patches({}, {"price": 15.63}, MKT)
check("no offer to edit", err.startswith("this listing has no purchasable_offer"),
      True)
p, err = AP.build_patches({"purchasable_offer": [{"our_price": [{"schedule": [{}]}]}]},
                          {"price": 15.63}, MKT)
check("no our_price schedule",
      err.startswith("purchasable_offer carries no our_price schedule"), True)

print("\n=== nothing about Rule 1 moved ===")
# The patches edit price, stock and handling and NOTHING else. A patch that
# reached brand, title or an identifier would be a listing-mode change by the
# back door (CLAUDE.md Rule 1).
p, err = AP.build_patches(attrs(15.49, 0), {"price": 15.63, "quantity": 3,
                                            "lead_days": 4}, MKT)
touched = sorted(x["path"] for x in p)
check("only the two attribute paths", touched,
      ["/attributes/fulfillment_availability", "/attributes/purchasable_offer"])
blob = repr(p)
for word in ("merchant_suggested_asin", "LISTING_OFFER_ONLY", "brand",
             "item_name", "externally_assigned_product_identifier"):
    check("  no %s" % word, word in blob, False)

print("\nFAILURES: %d" % fails)
sys.exit(1 if fails else 0)
