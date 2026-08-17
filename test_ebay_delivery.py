# -*- coding: utf-8 -*-
"""What eBay says about getting it here, and the bug that came of ignoring it.

WHAT WAS ASKED FOR
  "you know that there are two things written on the ebay pdp, under the buy
   button ... it should postage free delivery in 2-3 days and then it shows
   estimated between wed 19 aug and thu 20 aug to postal code bh166fh ... what i
   want the information to be shown on my order details is the delivery carrier
   like royal mail tracked 48, if it is available (because not every listing has
   this), if not i am interested in knowing the postage ... and also the delivery
   estimated between wed 19 to 24 aug"

THE BUG FOUND WHILE BUILDING IT
Every one of those facts was already arriving on the same call the price came
from, and all of it was thrown away. Worse, the two fields that WERE read came
from different shipping options:

    the postage COST      the first usable option        (free)
    the dispatch ESTIMATE the soonest date of ANY option (the 8.99 express one)

so the app costed the free service and promised the express service's delivery
date. Measured on a real item, 17 Aug 2026 (probe_ebay_delivery.py, item
186107152290) -- three days it had not paid for. source_fetch's own module note
warns that promising too short costs a late shipment and account health; this was
that, by a route the note did not foresee.

THE FIXTURE BELOW IS THAT ITEM'S REAL RESPONSE, trimmed. Not invented: the whole
point of Rule 4 is that the field names and shapes come from what the API
actually sent.
"""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


from domain import source_fetch as SF                          # noqa: E402
from domain import sourcing as S                               # noqa: E402
from api import ebay as E                                      # noqa: E402

# ---- the real response, trimmed to the shipping block --------------------
# Three options. The cheapest is the SLOWEST, which is what makes this item worth
# keeping as the fixture: any code that mixes the cost of one with the date of
# another gets caught.
ITEM = {
    "price": {"value": "24.99", "currency": "GBP"},
    "estimatedAvailabilities": [{
        "estimatedAvailabilityStatus": "IN_STOCK",
        "availabilityThresholdType": "MORE_THAN",
        "availabilityThreshold": 10,
        "estimatedRemainingQuantity": 33,
    }],
    "shippingOptions": [
        {"shippingServiceCode": "Evri Tracked",
         "shippingCarrierCode": "Hermes",
         "type": "Economy Delivery",
         "shippingCost": {"value": "0.00", "currency": "GBP"},
         "shippingCostType": "FIXED",
         "minEstimatedDeliveryDate": "2026-08-19T10:00:00.000Z",
         "maxEstimatedDeliveryDate": "2026-08-24T10:00:00.000Z"},
        {"shippingServiceCode": "Other 48h courier",
         "type": "Standard Delivery",
         "shippingCost": {"value": "3.99", "currency": "GBP"},
         "shippingCostType": "FIXED",
         "minEstimatedDeliveryDate": "2026-08-19T10:00:00.000Z",
         "maxEstimatedDeliveryDate": "2026-08-24T10:00:00.000Z"},
        {"shippingServiceCode": "Other 24 Hour Courier",
         "type": "Express Delivery",
         "shippingCost": {"value": "8.99", "currency": "GBP"},
         "shippingCostType": "FIXED",
         "minEstimatedDeliveryDate": "2026-08-19T10:00:00.000Z",
         "maxEstimatedDeliveryDate": "2026-08-21T10:00:00.000Z"},
    ],
}
NOW = dt.datetime(2026, 8, 17, 12, 0, 0)

print("=== the three things the order screen needs are captured ===")
got = SF.from_ebay_item(ITEM, NOW)
check("the status is usable", got["status"], S.FETCHED)
check("the price", got["price"], 24.99)
check("the carrier, as eBay NAMES the service", got["carrier"], "Evri Tracked")
check("the postage line, ready to print", got["postage_text"], "Free Evri Tracked")
check("the delivery window opens", got["delivery_min"], "2026-08-19")
check("  and closes", got["delivery_max"], "2026-08-24")

print("\n=== the cost and the date come from THE SAME option ===")
# THE BUG. Cheapest is 0.00 and arrives on the 24th; fastest arrives on the 21st.
# Anything that reports 0.00 alongside the 21st is promising a service it has not
# costed.
check("the postage is the cheapest usable option", got["shipping"], 0.0)
check("  and the date is THAT option's date, not the express one's",
      got["delivery_max"], "2026-08-24")
falsy("  it never promises the express date on the free postage",
      got["delivery_max"] == "2026-08-21")
# From the same option: 17 Aug -> 24 Aug is 7 calendar days.
#
# COUNTED DATE TO DATE, not by subtracting timestamps. eBay stamps its estimates
# at 10:00, so a check at noon on the 17th is 6 days and 22 hours from delivery on
# the 24th, and .days on that truncates to 6. A day short is the direction this
# whole module exists to avoid: it is a handling time that cannot be kept.
check("handling comes from that option too", got["dispatch_days"], 7)
falsy("  and not from the soonest option (which would be 4)",
      got["dispatch_days"] == 4)
# The hour of the check must not move the answer. Same day, three different
# times, one figure.
for hour in (0, 12, 23):
    check("  the same answer whatever time of day it is checked (%02d:00)" % hour,
          SF.from_ebay_item(ITEM, dt.datetime(2026, 8, 17, hour, 30))["dispatch_days"],
          7)

print("\n=== the carrier falls back the way it was asked to ===")
# "if it is available (because not every listing has this), if not i am
# interested in knowing the postage"
no_service = {"price": {"value": "10.00", "currency": "GBP"},
              "shippingOptions": [{"type": "Economy Delivery",
                                   "shippingCost": {"value": "0.00", "currency": "GBP"},
                                   "shippingCostType": "FIXED"}]}
g2 = SF.from_ebay_item(no_service, NOW)
check("with no named service, eBay's class of service is used",
      g2["carrier"], "Economy Delivery")
check("  and the postage line still reads", g2["postage_text"],
      "Free Economy Delivery")
# A paid option names its price in the line, because "postage" with no number is
# not the information anyone wanted.
paid = {"price": {"value": "10.00", "currency": "GBP"},
        "shippingOptions": [{"shippingServiceCode": "Royal Mail Tracked 48",
                             "shippingCost": {"value": "2.80", "currency": "GBP"},
                             "shippingCostType": "FIXED"}]}
g3 = SF.from_ebay_item(paid, NOW)
check("a paid service names the amount", g3["postage_text"],
      "2.80 GBP Royal Mail Tracked 48")
check("  and the carrier is the named service", g3["carrier"],
      "Royal Mail Tracked 48")

print("\n=== nothing is invented when eBay says nothing ===")
bare = {"price": {"value": "5.00", "currency": "GBP"}}
g4 = SF.from_ebay_item(bare, NOW)
check("no shipping options -> postage unknown, not free", g4["shipping"], None)
check("  no carrier", g4["carrier"], "")
check("  no postage line", g4["postage_text"], "")
check("  no delivery window", (g4["delivery_min"], g4["delivery_max"]), ("", ""))
check("  and no handling estimate", g4["dispatch_days"], None)
# CALCULATED postage depends on a destination we may not have sent, so the figure
# is not the one we would pay. The option is skipped entirely rather than costed.
calc = {"price": {"value": "5.00", "currency": "GBP"},
        "shippingOptions": [{"shippingServiceCode": "Courier",
                             "shippingCostType": "CALCULATED",
                             "shippingCost": {"value": "4.20", "currency": "GBP"},
                             "maxEstimatedDeliveryDate": "2026-08-20T10:00:00.000Z"}]}
g5 = SF.from_ebay_item(calc, NOW)
check("calculated postage is not treated as a price", g5["shipping"], None)
check("  and its delivery date is not borrowed either", g5["delivery_max"], "")

print("\n=== a delivery date is tied to the postcode it was worked out for ===")
# Measured: with no postcode eBay said the free service arrives by 21 August;
# with BH166FH it said the 24th. Same option, three days apart. So the postcode
# eBay ECHOES BACK is stored with the date -- what was asked and what was
# answered are different claims.
check("no echo -> no postcode recorded", got["delivery_postcode"], "")
withpc = dict(ITEM)
withpc["shippingOptions"] = [dict(o) for o in ITEM["shippingOptions"]]
withpc["shippingOptions"][0]["shipToLocationUsedForEstimate"] = {
    "postalCode": "BH166FH", "country": "GB"}
g6 = SF.from_ebay_item(withpc, NOW)
check("the postcode eBay used is recorded", g6["delivery_postcode"], "BH166FH")

print("\n=== the postcode is actually sent, and correctly ===")
sent = {}


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        import json
        return json.dumps(self._p).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(req, timeout=None):
    sent["headers"] = dict(req.headers)
    sent["url"] = req.full_url
    return _FakeResp(ITEM)


import urllib.request                                          # noqa: E402
_real_open = urllib.request.urlopen
_real_token = E.token
urllib.request.urlopen = _fake_urlopen
E.token = lambda *a, **k: "TOK"
try:
    E.get_item("https://www.ebay.co.uk/itm/186107152290", "APP", "CERT",
               marketplace="UK", postcode="bh16 6fh")
    ctx = sent["headers"].get("X-ebay-c-enduserctx") or \
        sent["headers"].get("X-EBAY-C-ENDUSERCTX") or ""
    truthy("the delivery-context header is sent", ctx)
    # Escaped INSIDE the header value: the header syntax uses = and , itself.
    truthy("  with the postcode, spaces removed and upper-cased",
           "BH166FH" in ctx)
    truthy("  and the country, escaped as eBay documents",
           "country%3DGB" in ctx and "zip%3D" in ctx)
    falsy("  no raw space survives into a header", " " in ctx)
    # THE COUNTRY, NOT THE SITE ID. site_for('UK') is 'EBAY_GB'; sending that
    # asks eBay about a country called EBAY_GB.
    falsy("  the site id is not sent as the country", "EBAY_GB" in ctx)
    check("country_of resolves the marketplace", E.country_of("UK"), "GB")
    check("  and passes an eBay site id through", E.country_of("EBAY_GB"), "GB")
    check("  and falls back rather than sending nonsense",
          E.country_of("EBAY_MOTORS"), "GB")

    sent.clear()
    E.get_item("https://www.ebay.co.uk/itm/186107152290", "APP", "CERT",
               marketplace="UK")
    hdrs = sent["headers"]
    falsy("with no postcode the header is left off entirely",
          any("enduserctx" in k.lower() for k in hdrs))
finally:
    urllib.request.urlopen = _real_open
    E.token = _real_token

print("\n=== the sweep always has a destination to cost delivery to ===")
# NOT A DISPLAY DETAIL. Measured on six live sources: with no postcode eBay
# returned no shippingOptions at all for five of them -- so postage was unknown,
# and an unknown postage means the source is skipped -- and quoted the sixth at
# "International Priority, 20.04 USD", costing delivery to a notional buyer
# abroad. With a postcode all six came back "Free Royal Mail Tracked 48" or
# similar. An empty destination is a pricing fault, not a missing nicety.
check("with nothing set, a representative UK postcode is used",
      SF.destination_postcode({}, "UK"), "B1 1AA")
check("  the account's own setting wins",
      SF.destination_postcode({"sourcing_postcode": "SW1A 1AA"}, "UK"), "SW1A 1AA")
check("  and it follows the marketplace's country",
      SF.destination_postcode({}, "US"), "10001")
check("  an unknown marketplace still gets one", SF.destination_postcode({}, "ZZ"),
      "B1 1AA")
truthy("it is never empty", all(SF.destination_postcode({}, m)
                               for m in ("UK", "US", "DE", "", None, "MOTORS")))
# The sweep must actually pass it, or all of the above is decoration.
import inspect                                                 # noqa: E402
src = inspect.getsource(SF.sweep)
truthy("the sweep works one out", "destination_postcode" in src)
truthy("  and hands it to the check", "postcode=postcode" in src)

print("\n=== the reading survives being stored and read back ===")
TMP = tempfile.mkdtemp(prefix="altaebaydel_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write('{"accounts": []}')
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "d.db")
from domain import source_repo as R                            # noqa: E402

sid = R.add_source(CFG, "ws", "UK", "SKU-1",
                   "https://www.ebay.co.uk/itm/186107152290", kind="ebay")
sid = sid if isinstance(sid, int) else \
    R.sources_for(CFG, "ws", "UK", "SKU-1")[0]["id"]
R.record_check(CFG, sid, g6)
back = R.latest_checks(CFG, [sid])[sid]
check("the carrier came back", back["carrier"], "Evri Tracked")
check("  the postage line", back["postage_text"], "Free Evri Tracked")
check("  the window", (back["delivery_min"], back["delivery_max"]),
      ("2026-08-19", "2026-08-24"))
check("  and the postcode it was worked out for",
      back["delivery_postcode"], "BH166FH")
# A reading with none of it stores blanks, not nulls that a screen has to guard.
R.record_check(CFG, sid, g4)
back2 = R.latest_checks(CFG, [sid])[sid]
check("a reading with no delivery info stores blanks", back2["carrier"], "")
check("  not None, so no screen has to guard for it", back2["postage_text"], "")

print("\n" + ("FAILURES: %s" % ", ".join(fails) if fails else "FAILURES: 0"))
sys.exit(1 if fails else 0)
