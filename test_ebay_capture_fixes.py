# -*- coding: utf-8 -*-
"""Two eBay fixes settled by the owner-approved read-only capture (30 Sep 2026).

  * api/ebay.country_of("EBAY_US") returned "GB": site_for() only knows Amazon
    codes, so an eBay site id fell through to the UK default and a US supplier
    was costed as delivery to GB (captured: $136.44 international vs $68.15
    domestic on item 398441256608).
  * CALCULATED postage was always skipped. Captured: with the destination
    header eBay returns the calculated cost AND shipToLocationUsedForEstimate
    {postalCode, country}; without it, no shippingOptions at all. A calculated
    option that names the postcode it used is the cost to OUR address.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


from api import ebay as E                      # noqa: E402
from domain import source_fetch as SF          # noqa: E402

print("== country_of ==")
check("EBAY_US is the US, not the UK default", E.country_of("EBAY_US"), "US")
check("EBAY_DE is Germany", E.country_of("EBAY_DE"), "DE")
check("an Amazon code still maps: UK -> GB", E.country_of("UK"), "GB")
check("an Amazon code still maps: US -> US", E.country_of("US"), "US")
check("EBAY_MOTORS (no country) falls back to GB", E.country_of("EBAY_MOTORS"), "GB")
check("nothing -> GB", E.country_of(""), "GB")

print("\n== calculated postage ==")
pick = getattr(SF, "_ebay_option", None)
calc_with = {"shippingCostType": "CALCULATED", "shippingCost": {"value": "68.15", "currency": "USD"},
             "shipToLocationUsedForEstimate": {"postalCode": "10001", "country": "US"},
             "maxEstimatedDeliveryDate": "2026-10-06"}
calc_without = {"shippingCostType": "CALCULATED", "shippingCost": {"value": "9.00", "currency": "USD"}}
fixed = {"shippingCostType": "FIXED", "shippingCost": {"value": "70.00", "currency": "USD"}}
if pick is None:
    fails.append("_ebay_option not found")
    print("  _ebay_option not found in domain/source_fetch.py   FAIL")
else:
    got = pick({"shippingOptions": [fixed, calc_with]})
    check("a calculated option naming its postcode is used (cheapest)",
          (got or {}).get("shippingCostType"), "CALCULATED")
    got = pick({"shippingOptions": [fixed, calc_without]})
    check("a calculated option with no postcode is still skipped",
          (got or {}).get("shippingCostType"), "FIXED")
    check("only an unnamed calculated option -> none",
          pick({"shippingOptions": [calc_without]}), None)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
