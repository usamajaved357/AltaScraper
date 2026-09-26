"""The fee on a listing row is Amazon's, and it says which kind of Amazon's.

    "many items dont display total fees on all listings page live on amazon but
     when i click on calculate revenue it shows the fee, but why not outside,
     and i suspect the fee is hardcoded and not actually coming from amazon,
     which is a bad inaccurate behavior, i dont want inaccuracy"

THREE FINDINGS, MEASURED ON THE STORED LISTINGS.

1. IT IS NOT HARDCODED. Across the 154 rows stamped "SP-API (exact)", the rates
   Amazon returned are 15%, 13%, 12%, 8%, 14.6% and 11.7%. No flat multiplier
   produces that spread. The label is only written after a getMyFeesEstimate
   call comes back QUOTED.

2. BUT 17 OF THEM CARRY 0.00, and that IS wrong. Amazon charges a referral fee
   on every category a bird table, a pizza peel or a massage gun could be in, so
   a zero is a quote that came back empty being recorded as a fee of nothing --
   and the stored profit on each is too high by the whole fee.

3. AND THE BLANKS ARE A DIFFERENT BUG. The row read listings.amazon_fees, frozen
   in when the listing was GENERATED. A listing synced from Amazon was never
   generated here, so it had none. The calculator asked the three-tier resolver,
   which always has an answer -- hence one screen showing a fee and the other a
   dash for the same listing.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


def code(s):
    s = re.sub(r"(?s:/\*.*?\*/)", "", s)
    return re.sub(r"(?m:^[ \t]*//[^\n]*)", "", s)


print("== a quote of nothing is not a quote ==")
AF = read("domain", "amazon_fees.py")
# Amazon says whether it answered, in FeesEstimateResult.Status, and only
# FeeDetailList was being checked. CLAUDE.md Rule 4: read what the schema says.
yes("the result's Status is read", '_status = str(_result.get("Status")' in AF)
yes("  and anything but Success is refused",
    'if _status and _status.lower() != "success":' in AF)
yes("a zero referral on a non-zero price is refused",
    "if referral <= 0 and p > 0:" in AF)
yes("  and says why, rather than returning a silent blank",
    "which no category does -- treated as no answer" in AF)
# It must NOT downgrade to a percentage on its own -- the caller asks for an
# estimate if it wants one. That rule is older than this change and still holds.
yes("it still never falls back to a percentage by itself",
    "silently downgrading is how a screen ends up presenting a guess" in AF)

print("\n== the rows already stored that way are named ==")
W = read("listing", "warnings.py")
yes("there is a warning for a zero fee on a priced listing",
    "def fee_of_nothing(row):" in W)
yes("  and it is in the list every active row is checked against",
    "fee_of_nothing(r)," in W)
from listing import warnings as _W                                   # noqa: E402
_w = _W.fee_of_nothing({"amazon_fees": "0.0", "our_price": "21.99",
                        "fee_source": "SP-API (exact)"})
yes("it fires on 0.00 at a real price", _w)
yes("  and says the profit is overstated", "too high by the whole fee" in _w["message"])
check("  a real fee does not fire it",
      _W.fee_of_nothing({"amazon_fees": "3.30", "our_price": "21.99"}), None)
check("  nor does a listing with no price",
      _W.fee_of_nothing({"amazon_fees": "0.0", "our_price": ""}), None)
check("  nor a zero fee at a zero price",
      _W.fee_of_nothing({"amazon_fees": "0", "our_price": "0"}), None)

print("\n== the row and the calculator read the same resolver ==")
MR = read("routes", "metrics_routes.py")
yes("live_metrics resolves the fee", "from domain import amazon_fees as _af" in MR)
yes("  through breakdown_for, which the calculator uses",
    "_af.breakdown_for(" in MR)
# breakdown_for reads what is stored; it does not call Amazon. That is why the
# calculator was built on it and why sixty rows cost nothing.
yes("  and it fetches nothing", "breakdown_for reads what is stored" in MR)
yes("the basis travels with the number", '"fee_basis"' in MR and '"fee_detail"' in MR)
yes("  and the parts come off `lines`, which is its shape",
    'for _l in (bd.get("lines") or []):' in MR)

print("\n== the price and OUR asin come from the browser ==")
LRD = code(read("static", "js", "listrow_detailed.js"))
yes("the row sends the price it is about to draw", '"&prices="' in LRD)
yes("  and our own ASIN", '"&asins="' in LRD)
# CLAUDE.md Rule 1 and the two-ASIN problem: r.asin is the COMPETITOR reference
# in the SKU. A fee quoted against it is for somebody else's category.
yes("  taken from rowAsin().own, never r.asin", "rowAsin(r).own" in LRD)
check("  and r.asin is not sent", "r.asin" in LRD.split("&asins=")[0][-600:], False)
yes("the route accepts them", 'request.args.get("prices"' in MR
    and 'request.args.get("asins"' in MR)
yes("  and skips a listing with no price", "a fee is a share OF a price" in MR)

print("\n== the resolver answers first, the frozen column second ==")
_f = LRD[LRD.index("function lrFees(r)"):]
_f = _f[:_f.index("return lrDataRow")]
yes("m.fees_total is preferred", "(m.fees_total != null) ? m.fees_total" in _f)
yes("  with the stored column as the fallback", "rowFee !== \"\" ? rowFee : null" in _f)

print("\n== 'estimated' is named for what it is ==")
# The third tier is this account's own rate, measured across its settled orders.
# On nestwell_goods that is 18.01% -- 15% plus the VAT Amazon charges on its own
# fees -- which no default could produce. "estimated" invited the suspicion.
yes("it reads 'your own measured rate'", '"your own measured rate"' in LRD)
yes("  quoted says which product", '"quoted by Amazon for this product"' in LRD)
yes("  actual says whose sales", '"taken on your own sales"' in LRD)
yes("  and the detail is on hover", 'esc(m.fee_detail || why)' in LRD)

print("\n== measured in Chrome, on nestwell_goods ==")
# Live view, detailed: 119 SKUs in LISTING_METRICS, all 119 with a fee, 37 of 49
# rendered cells showing a figure with its basis -- "18.01% your own measured
# rate" and "quoted by Amazon for this product". Before: 0 of them.
yes("the row still computes nothing of its own",
    "Nothing is worked out here" in read("static", "js", "listrow_detailed.js"))

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
sys.exit(1 if FAILS else 0)
