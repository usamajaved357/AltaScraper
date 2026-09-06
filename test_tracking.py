"""domain/tracking.py -- where each parcel is, and what it must refuse to claim.

Every check here is about a wrong answer that would look right. A carrier
matched by a substring, an order shown as delivered because one box of two
arrived, a made-up status filling in for one nobody asked about, a blank cell
read as a deletion -- none of those raise anything, and each one puts a
confident falsehood on the screen that decides whether a refund is argued.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db                    # noqa: E402
from domain import tracking as _tr            # noqa: E402
from domain import tracking_sheet as _ts      # noqa: E402

fails = []
ran = []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


WS, MKT = "__track_test__", "UK"
conn = _db.get_db()
for t in ("order_tracking", "order_lines"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))

print("\ncarrier names -> a stable code")
# THE ONE THAT WAS WRONG. "rm" for Royal Mail is inside "he-RM-es", so a
# substring match handed every Evri parcel to Royal Mail -- the wrong carrier,
# on the screen whose whole job is to say where a parcel is.
check("Hermes is Evri, not Royal Mail", _tr.carrier_code("Hermes"), "evri")
check("myHermes is Evri", _tr.carrier_code("my Hermes"), "evri")
check("Royal Mail", _tr.carrier_code("Royal Mail"), "royalmail")
check("RM on its own is still Royal Mail", _tr.carrier_code("RM"), "royalmail")
check("a service suffix keeps the carrier",
      _tr.carrier_code("ROYAL MAIL 24"), "royalmail")
check("DPD Local is DPD", _tr.carrier_code("DPD Local"), "dpd")
check("AMZL_UK is Amazon", _tr.carrier_code("AMZL_UK"), "amazon")
check("Parcelforce is not Royal Mail",
      _tr.carrier_code("Parcelforce Worldwide"), "parcelforce")
# AN UNKNOWN CARRIER KEEPS ITS OWN NAME rather than being forced to the nearest
# match: a lookup that does not know it says so, which is recoverable. A parcel
# silently tracked against the wrong carrier is not.
check("an unknown carrier is not forced into a known one",
      _tr.carrier_code("Bob the courier"), "bobthecourier")
check("no carrier at all is empty", _tr.carrier_code(""), "")

print("\ncarrier wording -> one of our words")
check("delivered", _tr.normalise("Delivered"), _tr.DELIVERED)
# ORDERING TRAP: "out for delivery" contains "deliver", so a naive map returns
# DELIVERED for a parcel still on the van.
check("out for delivery is not delivered",
      _tr.normalise("Out for delivery"), _tr.OUT_FOR_DELIVERY)
check("dropped off at a ParcelShop",
      _tr.normalise("Item dropped off at ParcelShop"), _tr.COLLECTED)
check("ready to collect is the buyer's end, not ours",
      _tr.normalise("Ready for collection at your local shop"),
      _tr.AWAITING_COLLECTION)
check("a failed delivery is a problem",
      _tr.normalise("Delivery attempt failed"), _tr.EXCEPTION)
check("in transit", _tr.normalise("In transit to depot"), _tr.IN_TRANSIT)
# A STATUS WE HAVE NOT BEEN TAUGHT IS UNKNOWN, never a nearest guess. The
# carrier's own words are kept beside it so nothing is lost meanwhile.
check("an unrecognised status is unknown", _tr.normalise("Wibble"), _tr.UNKNOWN)
check("no status at all is unknown", _tr.normalise(""), _tr.UNKNOWN)

print("\nseveral parcels on one order")
# THE EXPENSIVE ONE. An order in two boxes, one delivered and one still out, is
# NOT delivered -- and saying it is, is how a "where is my order" message gets
# answered wrongly.
check("delivered + in transit is not delivered",
      _tr.summarise_rows([{"status": "delivered"},
                          {"status": "in_transit"}])["status"], _tr.IN_TRANSIT)
check("delivered + a problem is a problem",
      _tr.summarise_rows([{"status": "delivered"},
                          {"status": "exception"}])["status"], _tr.EXCEPTION)
check("delivered + delivered is delivered",
      _tr.summarise_rows([{"status": "delivered"},
                          {"status": "delivered"}])["status"], _tr.DELIVERED)
check("an unknown status does not count as progress",
      _tr.summarise_rows([{"status": "delivered"},
                          {"status": "banana"}])["status"], _tr.UNKNOWN)
check("no parcels is not a status at all",
      _tr.summarise_rows([])["status"], "")
check("one stale parcel makes the line stale",
      _tr.summarise_rows([{"status": "delivered", "stale": False},
                          {"status": "delivered", "stale": True}])["stale"], True)

print("\nnothing is checked until a service is set up")
fn, why = _tr.provider_for({})
check("no key means no lookup", fn, None)
check("and it says why in a sentence", why.endswith("."), True)
check("a key alone is enough to turn it on",
      callable(_tr.provider_for({"track17_key": "x" * 20})[0]), True)
check("an unknown service name is refused, not guessed at",
      _tr.provider_for({"tracking_provider": "nosuchthing"})[0], None)
# THE WHOLE POINT: a status is never invented from a ship date.
r = _tr.refresh(None, lambda: {}, WS, MKT)
check("refresh with no service checks nothing", r["checked"], 0)
check("and reports why rather than succeeding quietly", bool(r.get("error")), True)

print("\nrecording numbers")
for oid in ("T-1", "T-2"):
    conn.execute("INSERT INTO order_lines (workspace_id, marketplace, order_id, "
                 "purchase_date, sku, units, revenue) VALUES (?,?,?,?,?,?,?)",
                 (WS, MKT, oid, "2026-08-10T10:00:00Z", "SKU-A", 1, 20.0))
conn.commit()

check("a number is recorded",
      _tr.add(None, WS, MKT, "T-1", "AB123456789GB", carrier="Royal Mail"), 1)
check("the same number again updates rather than duplicates",
      _tr.add(None, WS, MKT, "T-1", "AB123456789GB", carrier="Evri"), 1)
n = conn.execute("SELECT COUNT(*) FROM order_tracking WHERE workspace_id=?",
                 (WS,)).fetchone()[0]
check("still one row for that parcel", n, 1)
got = _tr.for_orders(None, WS, MKT, ["T-1"])
check("and the carrier was corrected", got["T-1"][0]["carrier_code"], "evri")
check("an order with no number is not invented",
      "T-2" in _tr.for_orders(None, WS, MKT, ["T-2"]), False)
check("an unchecked parcel is stale from the start",
      got["T-1"][0]["stale"], True)

print("\nthe sheet")
check("a real number is accepted",
      _ts.looks_like_tracking("AB123456789GB"), True)
check("spaces are allowed, carriers print them",
      _ts.looks_like_tracking("AB 12 3456 789 GB"), True)
# THE COMMON UPLOAD ACCIDENT: a rearranged sheet putting a date or a price in
# the tracking column. Sending those to a carrier gets "not found" for ever
# without ever saying why.
check("a date is not a tracking number",
      _ts.looks_like_tracking("12/03/2026"), False)
check("a price is not a tracking number",
      _ts.looks_like_tracking("7.50"), False)
check("letters with no digits are not a tracking number",
      _ts.looks_like_tracking("unknown"), False)
check("something too short is not one", _ts.looks_like_tracking("AB12"), False)

hdr = ["order id", "carrier", "tracking"]
res = _ts.apply_sheet(None, WS, MKT, hdr, [
    ["T-2", "DPD", "DPD998877665"],
    ["T-1", "", ""],                              # blank -> LEFT ALONE
    ["T-1", "Royal Mail", "12/03/2026"],          # not a number
    ["999-0000000-0000000", "DPD", "DPD11223344"],  # not this account's order
])
check("the good row was recorded", res["set"], 1)
# A BLANK IS NOT A DELETION. The template hands out every order with the column
# empty, so treating blank as "remove" would wipe the account on the first
# upload of an unedited file.
check("a blank row is skipped, not treated as a deletion", res["blank"], 1)
check("and the number it would have wiped is still there",
      len(_tr.for_orders(None, WS, MKT, ["T-1"]).get("T-1") or []), 1)
check("a date in the tracking column is refused", res["bad_number"], 1)
check("an order this account does not have is reported",
      res["unknown_order"], 1)
check("every row is accounted for",
      res["set"] + res["blank"] + res["bad_number"] + res["unknown_order"], 4)
check("a sheet with no tracking column refuses outright",
      _ts.apply_sheet(None, WS, MKT, ["order id", "cost"],
                      [["T-1", "5.00"]])["ok"], False)

_h, trows = _ts.template_rows(None, WS, MKT)
check("the template has a row per order", len(trows), 2)
check("the two columns to fill in are last and empty",
      [trows[0][-2], trows[0][-1]], ["", ""])
_h2, untracked = _ts.template_rows(None, WS, MKT, only_untracked=True)
check("untracked-only leaves out the ones already done", len(untracked), 0)

print("\nputting it on the order rows")
rows = [{"order_id": "T-1", "account_id": WS, "marketplace": MKT},
        {"order_id": "T-2", "account_id": WS, "marketplace": MKT},
        # ANOTHER ACCOUNT'S ROW, with the same order number. Tracking belongs to
        # one order of one account and must not cross.
        {"order_id": "T-1", "account_id": "someone_else", "marketplace": MKT},
        {"order_id": "T-1", "account_id": WS, "marketplace": ""}]
_tr.attach(None, rows)
check("the order with a parcel gets it", rows[0]["tracking_status"]["count"], 1)
check("another account's row gets nothing",
      rows[2]["tracking_status"]["count"], 0)
check("a row with no marketplace is left alone rather than guessed",
      rows[3]["tracking_status"]["count"], 0)
check("every row has the key, so the page never reads undefined",
      all("tracking" in r for r in rows), True)

print("\nremoving one")
check("one named number goes", _tr.remove(None, WS, MKT, "T-2", "DPD998877665"), 1)
check("removing one that is not there changes nothing",
      _tr.remove(None, WS, MKT, "T-2", "NOPE123456"), 0)
check("the other order's parcel is untouched",
      len(_tr.for_orders(None, WS, MKT, ["T-1"]).get("T-1") or []), 1)

print("\n17TRACK's documented enum maps onto our words")
from api import track17 as _t17          # noqa: E402
# READ FROM THE PUBLISHED DOCUMENT, not from memory. Every value 17TRACK
# publishes has to land on a word this app actually shows, or the status is
# stored and then rendered as "Not checked" for ever.
for k, v in _t17.STATUS.items():
    check("17TRACK %s is a status we can show" % k, v in _tr.STATUS_LABEL, True)
check("its delivered is our delivered", _t17.STATUS["Delivered"], _tr.DELIVERED)
check("its NotFound is not our unknown — they mean different things",
      _t17.STATUS["NotFound"] != _tr.UNKNOWN, True)

print("\nAMAZON'S OWN shipping-confirmation file goes straight in")
# THE FILE THE SELLER ALREADY MADE. When shipments are confirmed in Seller
# Central the seller ends up with this exact file, so it must import unedited --
# otherwise "do not ask me for the tracking again" is answered with "retype it
# into our template", which is the same thing wearing a hat.
#
# Amazon will not give the numbers back through the API. Measured, not assumed,
# on nestwell_goods over 54 real orders of which 49 were shipped merchant-
# fulfilled: the flat-file All Orders report has 33 columns and not one names a
# carrier or a tracking number; the XML version of the SAME report carries a
# FulfillmentData block holding only channel, service level and address, and the
# string "track" does not occur once in 73KB of it; MerchantFulfillment exposes
# get_shipment(id) for a label THIS app bought and has no way to list one it did
# not. So the file is the route, and it has to be a file nobody has to retype.
from domain import tracking_sheet as _ts        # noqa: E402

AMZ = ["order-id", "order-item-id", "quantity", "ship-date", "carrier-code",
       "carrier-name", "tracking-number", "ship-method"]
conn.execute(
    "INSERT INTO order_lines (workspace_id, marketplace, order_id, "
    "purchase_date, asin, sku, title, units, revenue, currency, status) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    (WS, MKT, "T-9", "2026-09-04T01:07:07Z", "B0TEST", "S1", "Fan", 1, 34.99,
     "GBP", "Shipped"))
conn.commit()

got = _ts.apply_sheet(None, WS, MKT, AMZ, [
    ["T-9", "1", "1", "2026-09-05", "Royal Mail", "", "JD0002123456789GB", "Std"],
])
check("Amazon's header resolves the order column", got["columns"]["order"],
      "order-id")
check("  and the tracking column", got["columns"]["tracking"],
      "tracking-number")
check("  and the row is recorded", got["set"], 1)
# THE ONE THAT MATTERS. Amazon fills carrier-CODE for every courier it knows and
# leaves carrier-NAME empty unless the code is "Other". A matcher that finds
# carrier-name and stops reads an empty cell on nearly every row -- and a
# tracking number with no carrier can never be checked with the courier, which
# is the entire point of storing it. Measured: every row imported blank.
row = (_tr.for_orders(None, WS, MKT, ["T-9"]).get("T-9") or [{}])[0]
check("the carrier comes from carrier-code when carrier-name is empty",
      row.get("carrier"), "Royal Mail")
check("  and maps to a courier this app can actually ask",
      row.get("carrier_code"), "royalmail")
check("  with both columns named in the report, not just the first",
      got["columns"]["carrier_columns"], ["carrier-name", "carrier-code"])

# "Other" is Amazon's placeholder meaning "look in the next column". Filing a
# parcel under a courier called Other would make it permanently uncheckable.
_tr.remove(None, WS, MKT, "T-9", "JD0002123456789GB")
_ts.apply_sheet(None, WS, MKT, AMZ, [
    ["T-9", "1", "1", "2026-09-05", "Other", "Yodel", "JD0002123456789GB", "Std"],
])
row = (_tr.for_orders(None, WS, MKT, ["T-9"]).get("T-9") or [{}])[0]
check("\"Other\" defers to the name column beside it", row.get("carrier"),
      "Yodel")

for t in ("order_tracking", "order_lines"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
