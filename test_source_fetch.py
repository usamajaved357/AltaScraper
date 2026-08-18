"""Phase B -- reading suppliers, without touching the network.

The fetchers are where a wrong answer enters the system. Once a bad number is in
a check row, the decision engine will act on it perfectly correctly and set a
real price. So the cases that matter here are the ones where a supplier tells us
almost nothing: calculated postage, a missing availability block, an ended
listing, a page with no structured data. In every one of those the right answer
is None, and None must survive all the way to the decision.
"""
import os, sys, json, tempfile, shutil, datetime as dt
sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

def truthy(l, g):
    check(l, bool(g), True)

TMP = tempfile.mkdtemp(prefix="altasrcb_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [], "ebay_app_id": "APP", "ebay_cert_id": "CERT"},
          open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "b.db")

from api import ebay as E
from domain import source_fetch as SF
from domain import source_scrape as SC
from domain import source_repo as R
from domain import sourcing as S

WS, MKT, SKU = "jack_uk", "UK", "8.00_3Days_B0G1K5B7QS"
NOW = dt.datetime(2026, 8, 14, 12, 0, 0)


def money(v, cur="GBP"):
    return {"value": str(v), "currency": cur}

def item(price=12.99, ship=3.95, ship_type="FIXED", status="IN_STOCK",
         qty=None, deliver="2026-08-19T12:00:00.000Z"):
    opt = {"shippingCostType": ship_type}
    if ship is not None:
        opt["shippingCost"] = money(ship)
    if deliver:
        opt["maxEstimatedDeliveryDate"] = deliver
    av = {}
    if status:
        av["estimatedAvailabilityStatus"] = status
    if qty is not None:
        av["estimatedAvailableQuantity"] = qty
    return {"price": money(price), "shippingOptions": [opt],
            "estimatedAvailabilities": [av] if av else []}


print("=== the eBay item id comes out of a URL, as it always did ===")
check("a normal item URL", E.item_id_from_url(
      "https://www.ebay.co.uk/itm/123456789012"), "123456789012")
check("  with a slug in front", E.item_id_from_url(
      "https://www.ebay.co.uk/itm/Some-Product-Name/123456789012?hash=x"), "123456789012")
check("not an item URL", E.item_id_from_url("https://www.ebay.co.uk/sch/i.html?_nkw=x"), "")
check("empty", E.item_id_from_url(""), "")
print("  -- and the generator still gets the same answer from its own name --")
import amazon_listing_generator as GEN
check("the generator delegates the regex",
      GEN._extract_ebay_item_id("https://www.ebay.co.uk/itm/123456789012"), "123456789012")
check("  same answer as the client", GEN._extract_ebay_item_id("nonsense"),
      E.item_id_from_url("nonsense"))


print("\n=== an eBay item becomes a reading ===")
g = SF.from_ebay_item(item(), NOW)
check("price", g["price"], 12.99)
check("postage", g["shipping"], 3.95)
check("currency", g["currency"], "GBP")
check("in stock", g["in_stock"], True)
check("dispatch days from the delivery estimate", g["dispatch_days"], 5)
check("status", g["status"], S.FETCHED)

print("  -- stock, in all the ways eBay says it --")
check("LIMITED_STOCK is still in stock",
      SF.from_ebay_item(item(status="LIMITED_STOCK"), NOW)["in_stock"], True)
check("OUT_OF_STOCK is not",
      SF.from_ebay_item(item(status="OUT_OF_STOCK"), NOW)["in_stock"], False)
check("a zero quantity beats a hopeful status",
      SF.from_ebay_item(item(status="IN_STOCK", qty=0), NOW)["in_stock"], False)
check("NO availability block means UNKNOWN, not out of stock",
      SF.from_ebay_item(item(status=None), NOW)["in_stock"], None)
check("  an unrecognised status is unknown too",
      SF.from_ebay_item(item(status="SOMETHING_NEW"), NOW)["in_stock"], None)

print("  -- postage, and the trap in it --")
check("CALCULATED postage is UNKNOWN, not free",
      SF.from_ebay_item(item(ship=0.0, ship_type="CALCULATED"), NOW)["shipping"], None)
check("  no postage block at all is unknown",
      SF.from_ebay_item(item(ship=None), NOW)["shipping"], None)
check("free postage really is zero",
      SF.from_ebay_item(item(ship=0.0), NOW)["shipping"], 0.0)

print("  -- a reading with no price is not a reading --")
bad = SF.from_ebay_item({"price": {}}, NOW)
check("status failed", bad["status"], S.FAILED)
truthy("  and says why", "no price" in bad["error"])
check("garbage in", SF.from_ebay_item(None, NOW)["status"], S.FAILED)

print("  -- a delivery estimate in the past is not negative dispatch --")
check("stale estimate ignored",
      SF.from_ebay_item(item(deliver="2026-08-01T12:00:00.000Z"), NOW)["dispatch_days"], None)
check("no estimate at all",
      SF.from_ebay_item(item(deliver=None), NOW)["dispatch_days"], None)


print("\n=== ended, failed, and the difference between them ===")
calls = {}
def fake_get_item(url, app, cert, marketplace=None, postcode="", timeout=15):
    # postcode and timeout accepted because the real one takes them. A stub with
    # a narrower signature than the thing it stands in for turns a working call
    # into a TypeError -- which is a test failure that says nothing about the app.
    calls["postcode"] = postcode
    return calls["next"]
E_real = E.get_item
SF._ebay.get_item = fake_get_item

calls["next"] = {"status": E.GONE, "data": None, "http_code": 404,
                 "error": "HTTP 404 ", "item_id": "1"}
c = SF.check_source({"kind": "ebay", "url": "https://ebay.co.uk/itm/1"}, "A", "C")
check("a 404 is GONE, not a failure", c["status"], S.GONE)

calls["next"] = {"status": E.FAILED, "data": None, "http_code": 503,
                 "error": "HTTP 503 ", "item_id": "1"}
c = SF.check_source({"kind": "ebay", "url": "https://ebay.co.uk/itm/1"}, "A", "C")
check("a 503 is FAILED -- we learned nothing", c["status"], S.FAILED)
check("  and carries no invented numbers", (c["price"], c["in_stock"]), (None, None))

# NOTE: these fixtures are what api/ebay.py returns, so they carry the TRANSPORT
# status ("ok" -- the HTTP call worked). check_source translates it to the check
# status ("fetched" -- we have the supplier's numbers). Writing S.FETCHED here
# would be testing a value the client never produces.
calls["next"] = {"status": E.OK, "data": item(), "http_code": None,
                 "error": "", "item_id": "1"}
c = SF.check_source({"kind": "ebay", "url": "https://ebay.co.uk/itm/1"}, "A", "C")
check("a good one comes through", (c["status"], c["price"]), (S.FETCHED, 12.99))
check("  the transport's 'ok' became the check's 'fetched'",
      (E.OK, c["status"]), ("ok", "fetched"))

print("  -- a typed postage cost fills a gap the supplier left --")
calls["next"] = {"status": E.OK, "data": item(ship=None), "http_code": None,
                 "error": "", "item_id": "1"}
c = SF.check_source({"kind": "ebay", "url": "https://ebay.co.uk/itm/1",
                     "shipping_override": 4.25}, "A", "C")
check("override used when eBay gave nothing", c["shipping"], 4.25)
calls["next"] = {"status": E.OK, "data": item(ship=3.95), "http_code": None,
                 "error": "", "item_id": "1"}
c = SF.check_source({"kind": "ebay", "url": "https://ebay.co.uk/itm/1",
                     "shipping_override": 4.25}, "A", "C")
check("  but the supplier's real figure wins when there is one", c["shipping"], 3.95)


print("\n=== a page with no API: structured data only, never a guess ===")
LD = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Thing",
 "offers":{"@type":"Offer","price":"19.99","priceCurrency":"GBP",
           "availability":"https://schema.org/InStock"}}
</script></head><body>Sale! 2.99 GBP accessory  1.00 GBP/month</body></html>"""
off = SC._offers_from(LD)
truthy("the schema.org offer is found", off)
check("  its price, not the 2.99 sitting in the page text",
      SC._num(off.get("price")), 19.99)
check("  in stock", SC._stock_from(off), True)
check("OutOfStock", SC._stock_from({"availability": "https://schema.org/OutOfStock"}), False)
check("an availability we do not know is UNKNOWN",
      SC._stock_from({"availability": "https://schema.org/SomeNewThing"}), None)
check("no availability field is unknown", SC._stock_from({}), None)
check("a page with no structured data yields nothing",
      SC._offers_from("<html><body>Price: Â£4.99</body></html>"), None)
check("  and malformed JSON-LD does not become a price",
      SC._offers_from('<script type="application/ld+json">{oops</script>'), None)


print("\n=== the readings are stored, and read back with their unknowns intact ===")
R.enrol(CFG, WS, MKT, SKU)
sid1 = R.add_source(CFG, WS, MKT, SKU, "https://ebay.co.uk/itm/111",
                    kind="ebay", label="eBay A", priority=10)
sid2 = R.add_source(CFG, WS, MKT, SKU, "https://ebay.co.uk/itm/222",
                    kind="ebay", label="eBay B", priority=20)
check("two sources", len(R.sources_for(CFG, WS, MKT, SKU)), 2)

R.record_check(CFG, sid1, {"status": S.FETCHED, "price": 8.0, "shipping": 1.5,
                           "currency": "GBP", "in_stock": True, "dispatch_days": 3,
                           "checked_at": "2026-08-14 11:00:00"})
R.record_check(CFG, sid2, {"status": S.FETCHED, "price": 9.0, "shipping": None,
                           "currency": "GBP", "in_stock": None, "dispatch_days": None,
                           "checked_at": "2026-08-14 11:00:00"})
latest = R.latest_checks(CFG, [sid1, sid2])
check("true stays True", latest[sid1]["in_stock"], True)
check("UNKNOWN stays None, not False", latest[sid2]["in_stock"], None)
check("unknown postage stays None", latest[sid2]["shipping"], None)

R.record_check(CFG, sid1, {"status": S.FETCHED, "price": 7.5, "shipping": 1.5,
                           "currency": "GBP", "in_stock": True, "dispatch_days": 3,
                           "checked_at": "2026-08-14 11:30:00"})
check("only the newest reading is 'latest'",
      R.latest_checks(CFG, [sid1])[sid1]["price"], 7.5)
check("  but the history is kept", len(R.history(CFG, sid1)), 2)

print("  -- and they arrive in the shape the decision engine wants --")
pairs = R.pairs_for(CFG, WS, MKT, SKU)
check("one pair per source", len(pairs), 2)
# The old per-unit allowances, stated rather than assumed: they used to be the
# defaults (3.00 postage, 2.00 ads, 1.00 profit) and are 0.00 now, and this test
# is about reading stored rows -- not about what a default happens to be.
_ALLOW = {"shipping_label": 3.00, "ads_margin": 2.00, "min_profit": 1.00,
          "min_roi_pct": 0}
d = S.decide({"price": 20.0, "quantity": 5, "lead_days": 5}, pairs, _ALLOW, NOW)
check("it decides from stored rows", d["action"], "update")
check("  using the one with a known postage", d["source_id"], sid1)
truthy("  and explains why the other was skipped",
       any("postage" in r["reason"] for r in d["rejections"]))


print("\n=== rules: the account default, and one SKU that differs ===")
R.save_rule(CFG, WS, MKT, "", {"strategy": "fastest", "max_change_pct": 10.0,
                               "in_stock_quantity": 3})
R.save_rule(CFG, WS, MKT, SKU, {"max_change_pct": 40.0})
r = R.rule_for(CFG, WS, MKT, SKU)
check("the SKU's own value wins", r["max_change_pct"], 40.0)
check("  the account default still applies", r["strategy"], "fastest")
check("  and is not blanked by the override row", r["in_stock_quantity"], 3)
check("a SKU with no override just gets the default",
      R.rule_for(CFG, WS, MKT, "other")["max_change_pct"], 10.0)


print("\n=== the sweep only touches SKUs someone enrolled ===")
seen = []
def fake_check(source, app_id="", cert_id="", now=None, marketplace=None,
               postcode=""):
    seen.append(source["label"])
    # THE SWEEP MUST PASS A DESTINATION. eBay returns no shipping options at all
    # without one, so a sweep that forgot it would read every source as having
    # unknown postage -- and unknown postage means the source is skipped.
    seen_postcode.append(postcode)
    return {"status": S.FETCHED, "price": 8.0, "shipping": 1.5, "currency": "GBP",
            "in_stock": True, "dispatch_days": 3, "error": "",
            "carrier": "Royal Mail Tracked 48",
            "postage_text": "1.50 GBP Royal Mail Tracked 48",
            "delivery_min": "2026-08-17", "delivery_max": "2026-08-20",
            "delivery_postcode": "B11AA",
            "checked_at": "2026-08-14 12:00:00"}
seen_postcode = []
_real_check = SF.check_source
SF.check_source = fake_check

R.add_source(CFG, WS, MKT, "NOT_ENROLLED_SKU", "https://ebay.co.uk/itm/999",
             label="should never be read")
res = SF.sweep(CFG, {"ebay_app_id": "A", "ebay_cert_id": "C"}, pause=0)
check("both enrolled sources checked", res["checked"], 2)
check("  one SKU", res["skus"], 1)
check("  the un-enrolled SKU was never contacted",
      "should never be read" in seen, False)
check("  all readable", res["readable"], 2)
# A DESTINATION ON EVERY CHECK. eBay returns no shippingOptions at all without
# one -- measured on six live sources, five came back with no postage figure and
# the sixth was quoted 20.04 USD of international postage. An unknown postage
# means the source is skipped, so a sweep that forgot the postcode would silently
# stop repricing most of the catalogue.
truthy("every check was given a destination postcode",
       seen_postcode and all(seen_postcode))
check("  and it is the one for this marketplace", sorted(set(seen_postcode)),
      ["B1 1AA"])

print("  -- a disabled source is left alone --")
seen.clear()
R.set_source_enabled(CFG, sid2, False)
res = SF.sweep(CFG, {"ebay_app_id": "A", "ebay_cert_id": "C"}, pause=0)
check("only the enabled one", res["checked"], 1)

print("  -- and it says so when it cannot work --")
seen.clear()
R.unenrol(CFG, WS, MKT, SKU)
res = SF.sweep(CFG, {}, pause=0)
check("nothing enrolled", res["checked"], 0)
truthy("  and explains the empty result", "enrolled" in (res.get("note") or ""))

SF.check_source = _real_check
SF._ebay.get_item = E_real


print("\n=== the generator's own eBay enrichment still behaves as it did ===")
# fetch_ebay_supplement kept its parsing and its console lines; only the
# transport moved into api/ebay.py. It must still return the same empty dict on
# every failure and the same fields on success.
GEN._ebay_api.get_item = fake_get_item
RICH = {"title": "A Thing", "price": money(12.99),
        "localizedAspects": [{"name": "Brand", "value": "Acme"}],
        "condition": "New", "shortDescription": "<p>Nice   thing</p>",
        "image": {"imageUrl": "http://img/1.jpg"},
        "additionalImages": [{"imageUrl": "http://img/2.jpg"}]}

calls["next"] = {"status": E.OK, "data": RICH, "http_code": None,
                 "error": "", "item_id": "1"}
sup = GEN.fetch_ebay_supplement("https://ebay.co.uk/itm/1", "A", "C")
check("title comes through", sup["title"], "A Thing")
check("  price is formatted as before", sup["price"], "GBP 12.99")
check("  item specifics parsed", sup["item_specifics"].get("Brand"), "Acme")
check("  html stripped and whitespace collapsed", sup["description"], "Nice thing")
check("  images counted", sup["image_count"], 2)

calls["next"] = {"status": E.GONE, "data": None, "http_code": 404,
                 "error": "HTTP 404 ", "item_id": "1"}
check("an ended listing returns the empty shape, not a crash",
      GEN.fetch_ebay_supplement("https://ebay.co.uk/itm/1", "A", "C")["title"], "")
calls["next"] = {"status": E.FAILED, "data": None, "http_code": None,
                 "error": "timed out", "item_id": "1"}
check("  and so does a timeout",
      GEN.fetch_ebay_supplement("https://ebay.co.uk/itm/1", "A", "C")["item_specifics"], {})
check("no credentials, no call",
      GEN.fetch_ebay_supplement("https://ebay.co.uk/itm/1", "", "")["title"], "")


print("\n=== the two vocabularies stay joined up ===")
# This is the guard for a bug that got all the way to a passing fetcher: the
# client says 'ok' about an HTTP call, a check says 'fetched' about a supplier,
# and for a while both were written into the database as 'ok'. Every reading
# then looked unreadable to the decision engine and the repricer did nothing at
# all -- silently, because "no usable data" correctly means "change nothing".
check("every transport status is translated",
      sorted(SF._FROM_TRANSPORT), sorted([E.OK, E.GONE, E.FAILED, E.GROUP]))
# GROUP is the fourth. A variation-family URL answers HTTP 400 to the same
# question an ENDED listing does -- measured on the live API -- so without this
# the repricer would read a live, selling product as gone and take it out of
# stock. It maps to FAILED, meaning "we learned nothing", which changes nothing.
check("a variation family is not a dead listing",
      SF._FROM_TRANSPORT[E.GROUP], S.FAILED)
check("  and definitely not GONE, which would stop it selling",
      SF._FROM_TRANSPORT[E.GROUP] == S.GONE, False)
check("  and only ever into a status the decision engine knows",
      sorted(set(SF._FROM_TRANSPORT.values())),
      sorted([S.FETCHED, S.GONE, S.FAILED]))
check("  'ok' is NOT a check status", S.FETCHED == E.OK, False)
check("the scraper speaks the check vocabulary too",
      (SC.FETCHED, SC.GONE, SC.FAILED), (S.FETCHED, S.GONE, S.FAILED))
usable_now = dt.datetime(2026, 8, 14, 12, 0, 0)
fresh = {"status": S.FETCHED, "price": 8.0, "shipping": 1.5, "in_stock": True,
         "dispatch_days": 3, "checked_at": "2026-08-14 11:00:00"}
check("a freshly fetched reading is actually usable",
      S.usable({"enabled": 1}, fresh, {}, usable_now)[0], True)
check("  the same reading labelled 'ok' is NOT",
      S.usable({"enabled": 1}, dict(fresh, status=E.OK), {}, usable_now)[0], False)


print("\n=== the job is registered like every other ===")
from data import scheduler as SCH
check("sourcing_check exists", "sourcing_check" in SCH._JOBS, True)
check("  on a timer", SCH._JOBS["sourcing_check"]["hours"], 4)
truthy("  with a description", SCH._JOBS["sourcing_check"]["description"])
check("  and is refused cleanly when unbound",
      SCH.run_job("sourcing_check", None)["ok"], False)

os.environ.pop("ALTASCRAPER_DB", None)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
sys.exit(1 if fails else 0)
