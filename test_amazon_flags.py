"""Amazon's true and false, read the way Amazon actually writes them.

THE BUG THIS PINS

    "ON ORDERS DETAIL PAGE IT SHOWS ON EVERY ORDER THAT BUYER ASKED TO cancell"

Every order claimed the buyer wanted to cancel it, including orders that had
already shipped. The code read:

    "cancel_requested": bool(it.get("BuyerRequestedCancel")),

probe_cancel_flag.py read 15 real order lines from nestwell_goods and printed
the raw payload. In ONE OrderItem, three different shapes:

    BuyerRequestedCancel   dict   {"IsBuyerRequestedCancel": "false",
                                   "BuyerCancelReason": ""}
    IsGift                 str    "false"
    IsTransparency         bool   False

bool() of a non-empty dict is True. bool("false") is True. Two flags were on for
every order in the account, permanently.

WHY THE TEST IS SHAPED LIKE THIS

Not "does BuyerRequestedCancel work now" -- that passes until the next Amazon
field arrives as a string. Every shape Amazon has been SEEN to use is exercised
against one shared reader, and the false-yes direction is checked hardest,
because a warning shown wrongly is worse than one missed: it is what stops the
screen being believed at all.
"""
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import amazon_flags as _flags       # noqa: E402
from domain import orders_view as _ov           # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


print("\n== the exact payload Amazon sent, measured 18 Aug 2026 ==")
# Copied from probe_cancel_flag.py output, order 203-1413769-2862763, Shipped.
REAL = {
    "ProductInfo": {"NumberOfItems": "1"},
    "BuyerInfo": {},
    "ItemTax": {"CurrencyCode": "GBP", "Amount": "0.00"},
    "QuantityShipped": 2,
    "BuyerRequestedCancel": {"IsBuyerRequestedCancel": "false",
                             "BuyerCancelReason": ""},
    "ItemPrice": {"CurrencyCode": "GBP", "Amount": "69.98"},
    "ASIN": "B0H7N2Q5GG",
    "SellerSKU": "AltaboltaVoo Ceiling Fan",
    "Title": "Bayonet Ceiling Fan with Light and Remote",
    "IsGift": "false",
    "IsTransparency": False,
    "QuantityOrdered": 2,
    "OrderItemId": "65843524080602",
}
got = _ov.to_item(REAL)
check("a shipped order does NOT say the buyer asked to cancel",
      got["cancel_requested"], False)
check("  and is not a gift either", got["gift"], False)
check("  no reason, because there is nothing to cancel", got["cancel_reason"], "")
# The rest of the line must still be read correctly -- this changed a shared
# function and the easy mistake is to fix the flag and break the money.
check("  the price still reads", got["price"], 69.98)
check("  and the quantity", got["qty"], 2)

print("\n== a buyer who really did ask ==")
asked = dict(REAL, BuyerRequestedCancel={"IsBuyerRequestedCancel": "true",
                                         "BuyerCancelReason": "Ordered by mistake"})
got = _ov.to_item(asked)
check("is reported", got["cancel_requested"], True)
check("  with the reason they gave, which Amazon carries and we were dropping",
      got["cancel_reason"], "Ordered by mistake")

print("\n== every shape Amazon has been seen to use ==")
for value, want in ((True, True), (False, False),
                    ("true", True), ("false", False),
                    ("True", True), ("FALSE", False),
                    ("yes", True), ("no", False),
                    ("1", True), ("0", False),
                    (1, True), (0, False),
                    (None, False), ("", False)):
    check("truth(%r)" % (value,), _flags.truth(value), want)

print("\n== an object that wraps the flag ==")
check("named explicitly",
      _flags.truth({"IsBuyerRequestedCancel": "true"},
                   "IsBuyerRequestedCancel"), True)
check("  and found by its Is-prefix when it is not named",
      _flags.truth({"IsBuyerRequestedCancel": "true"}), True)
check("  false inside stays false",
      _flags.truth({"IsBuyerRequestedCancel": "false"}), False)
# THE BUG ITSELF: a non-empty object is not a yes.
check("an object carrying a NO is not True just for existing",
      _flags.truth({"IsBuyerRequestedCancel": "false", "BuyerCancelReason": ""}),
      False)
check("an empty object is not a yes", _flags.truth({}), False)
check("an object with no flag in it is not a yes",
      _flags.truth({"BuyerCancelReason": ""}), False)
check("a named key that is absent falls back to the Is-prefix",
      _flags.truth({"IsGift": "true"}, "IsSomethingElse"), True)

print("\n== unknown means no, never yes ==")
# These are warnings. A false alarm is worse than a miss, because it is what
# teaches somebody to ignore the screen.
for value in ([], ["true"], object(), "maybe", "  ", "null"):
    check("truth(%.24r) is False" % (value,), _flags.truth(value), False)

print("\n== the reason text ==")
check("read from the object", _flags.text(
    {"IsBuyerRequestedCancel": "true", "BuyerCancelReason": "Too slow"},
    "BuyerCancelReason"), "Too slow")
check("  empty stays empty rather than becoming a sentence",
      _flags.text({"BuyerCancelReason": ""}, "BuyerCancelReason"), "")
check("  and a non-object does not raise",
      _flags.text("false", "BuyerCancelReason"), "")

print("\n== one reader, not five ==")
# There were five bool(x.get("Is...")) sites making the same assumption. If one
# is left behind, the same bug is one Amazon change away in that screen instead.
import re                                                        # noqa: E402
for path in ("domain/orders_view.py", "monitor/pricing.py"):
    src = open(r"D:\AltaScraper\%s" % path, encoding="utf-8-sig").read()
    body = re.sub(r'"""[\s\S]*?"""', "", src)
    body = "\n".join(re.sub(r"#.*$", "", ln) for ln in body.split("\n"))
    stray = re.findall(r'bool\(\s*[\w.]*\.get\(\s*"Is', body)
    check("%s casts no Amazon flag with bool()" % path, stray, [])
    check("  it uses the shared reader instead",
          bool(re.search(r"_flags\.truth\(", body)), True)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
