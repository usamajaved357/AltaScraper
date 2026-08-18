"""The daily round: what is wrong today, and never a tick for what was not looked at.

    "i want to design a page where all of these metrics results are being shown
     and it highlights the things which are off track"

WHAT IT REPLACES

A Fillout checklist (Screenshot 89) of fourteen CSA checks somebody opens every
morning, works through in Seller Central, and ticks off:

    Daily PPC Sales · PPC Orders Number · PPC Spend · Organic vs PPC Sales ·
    BUYER MSGs · Last 24hrs Shipment Status · Account Health · Performance
    Notification · FBM Orders · NCX Rate · A to Z Claims · Inventory
    Performance · Stranded Listings Check · Creator Connection Check

THE ONE PROPERTY EVERYTHING ELSE RESTS ON

A check that COULD NOT RUN must never render as fine. That is the paper form's
own failure mode -- ticked without the looking -- and reproducing it in software
would make the page actively worse than the form, because software looks
authoritative. Six of the fourteen genuinely cannot be answered from anything
this app can reach, and each has to say which connection it needs.

So the hardest checks here are the negative ones: absent data produces
`unknown`, unknown is counted separately from ok, and the headline refuses to
say "everything is fine" while anything went unchecked.

AND NO INVENTED THRESHOLDS. Some of these have a real line -- an unshipped
order past Amazon's own ship-by date is late. Others do not: there is no honest
universal number for "PPC spend is too high today". Where no line exists the
figure is reported without a verdict, because a made-up target presented as a
judgement is how a page like this stops being believed.
"""
import datetime as _dt
import sys

sys.path.insert(0, r"D:\AltaScraper")

from domain import daily_check as _dc      # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


NOW = _dt.datetime(2026, 8, 18, 12, 0, tzinfo=_dt.timezone.utc)


def by_key(out, key):
    return next((c for c in out["checks"] if c["key"] == key), None)


print("\n== an empty context checks NOTHING, and says so ==")
# The sharpest case: no data at all. Every answerable check must come back
# unknown, and not one of them may say ok.
out = _dc.run({})
oks = [c for c in out["checks"] if c["status"] == _dc.OK]
check("nothing is reported as fine", oks, [])
check("  nothing is reported as off either",
      [c for c in out["checks"] if c["status"] == _dc.OFF], [])
check("  every row is unknown", out["n_unknown"], len(out["checks"]))
truthy("  and each says what it needs",
       all(c["needs"] for c in out["checks"]))
# THE HEADLINE MUST NOT SAY ALL CLEAR.
check("the headline does not claim everything is fine",
      "Everything checked is fine" in out["headline"], False)
truthy("  it says how many could not run", "could not run" in out["headline"])

print("\n== the six that cannot be answered are LISTED, not dropped ==")
# A round that silently omits what it cannot do looks complete and is not.
keys = {c["key"] for c in _dc.unavailable()}
for k in ("buyer_msgs", "account_health", "performance_notifications", "ncx",
          "atoz", "creator_connection"):
    truthy("%s is shown with its reason" % k, k in keys)
for c in _dc.unavailable():
    check("  %s is never ok" % c["key"], c["status"], _dc.UNKNOWN)
    truthy("  %s names what it needs" % c["key"], len(c["needs"]) > 30)

print("\n== late is the one hard line, and it is Amazon's own ==")
ctx = {"now": NOW, "orders": [
    {"status": "Unshipped", "ship_by": "2026-08-17T10:00:00Z"},   # late
    {"status": "Unshipped", "ship_by": "2026-08-19T10:00:00Z"},   # fine
    {"status": "Shipped", "ship_by": "2026-08-01T10:00:00Z"},     # gone already
]}
c = _dc.check_unshipped(ctx)
check("an order past its ship-by date is off track", c["status"], _dc.OFF)
truthy("  and it says how many", "1 late" in c["value"])
truthy("  out of how many waiting", "out of 2 waiting" in c["detail"])
# Shipped orders are not waiting, however old.
c2 = _dc.check_unshipped({"now": NOW, "orders": [
    {"status": "Shipped", "ship_by": "2026-01-01T00:00:00Z"}]})
check("a shipped order is never late", c2["status"], _dc.OK)
check("  and is not counted as waiting", c2["value"], "0")
# Pending is Amazon still authorising payment -- not the seller's to ship yet.
c3 = _dc.check_unshipped({"now": NOW, "orders": [
    {"status": "Pending", "ship_by": "2026-01-01T00:00:00Z"}]})
check("a Pending order is not called late", c3["status"], _dc.OK)
# No ship-by date means Amazon did not say. Not late.
c4 = _dc.check_unshipped({"now": NOW, "orders": [{"status": "Unshipped"}]})
check("an order with no ship-by date is not assumed late", c4["status"], _dc.OK)
check("no order list at all is unknown, not zero",
      _dc.check_unshipped({})["status"], _dc.UNKNOWN)

print("\n== stranded listings: stock behind a closed door comes first ==")
c = _dc.check_stranded({"listings": [
    {"sku": "A", "status": "Suppressed", "qty": "4"},
    {"sku": "B", "status": "Inactive", "qty": "0"},
    {"sku": "C", "status": "Active", "qty": "9"},
]})
check("a suppressed listing holding stock is off track", c["status"], _dc.OFF)
truthy("  and the SKU is named", "A" in c["detail"])
truthy("  with the count of both", "2 listings not buyable" in c["detail"])
# Not buyable but holding nothing is worth knowing and is not urgent.
c2 = _dc.check_stranded({"listings": [
    {"sku": "B", "status": "Inactive", "qty": "0"},
    {"sku": "C", "status": "Active", "qty": "1"}]})
check("not buyable but holding no stock is reported, not raised",
      c2["status"], _dc.OK)
check("  with the number", c2["value"], "1")
check("all active is a clean pass",
      _dc.check_stranded({"listings": [{"sku": "C", "status": "Active"}]})["status"],
      _dc.OK)
check("no catalogue is unknown", _dc.check_stranded({})["status"], _dc.UNKNOWN)

print("\n== a buyer asking to cancel is caught before it is posted ==")
c = _dc.check_cancel_requests({"orders": [
    {"status": "Unshipped", "cancel_requested": True},
    {"status": "Shipped", "cancel_requested": True},   # too late to matter
]})
check("a live order with a cancellation request is off track",
      c["status"], _dc.OFF)
check("  and only the live one counts", c["value"], "1")
truthy("  with what it costs to ignore", "comes straight back" in c["action"])

print("\n== no invented thresholds ==")
# There is no honest universal number for "too many merchant-fulfilled orders",
# so the count is reported and never judged.
c = _dc.check_fbm({"orders": [{"fulfilment": "MFN"}] * 500})
check("500 merchant-fulfilled orders is still not a fault", c["status"], _dc.OK)
check("  the figure is simply reported", c["value"], "500")
# Same for advertising: spend is spend. It has no line without a target.
c = _dc.check_ads({"ads": {"spend": 9999.0, "sales": 10.0, "orders": 1}})
check("huge ad spend is reported, not judged", c["status"], _dc.OK)
truthy("  with the ratio stated so a person can judge it", "ACOS" in c["detail"])

print("\n== the sync check is what makes the others mean anything ==")
# Every figure above is read from synced data. If the sync did not run they all
# quietly describe an older day -- and every one of them would still say ok.
check("fresh data passes", _dc.check_sync({"data_age_hours": 4})["status"], _dc.OK)
c = _dc.check_sync({"data_age_hours": 50})
check("two-day-old data is off track", c["status"], _dc.OFF)
truthy("  and says the figures describe that moment, not today",
       "not today" in c["detail"])
check("an unknown age is unknown", _dc.check_sync({})["status"], _dc.UNKNOWN)

print("\n== organic vs paid: half an answer is said to be half ==")
c = _dc.check_organic_split({"total_sales": 500.0})
check("with no ad data it is unknown", c["status"], _dc.UNKNOWN)
truthy("  but the half that IS known is still shown", "500.00" in c["value"])
truthy("  and it names the missing half", "Advertising API" in c["needs"])
c = _dc.check_organic_split({"total_sales": 500.0,
                             "ads": {"sales": 200.0, "spend": 50.0}})
check("with both it splits them", c["status"], _dc.OK)
truthy("  organic is the remainder", "300.00 organic" in c["value"])
truthy("  and the share is stated", "40% of sales" in c["detail"])
# Ad sales above total sales means two different windows, not a discovery.
c = _dc.check_organic_split({"total_sales": 100.0, "ads": {"sales": 900.0}})
check("ad sales exceeding total is named, not shown as negative organic",
      c["status"], _dc.OFF)
truthy("  saying why the pair cannot be compared",
       "different reports" in c["detail"])

print("\n== off-track first, because that is the only reason to open it ==")
out = _dc.run({
    "now": NOW,
    "orders": [{"status": "Unshipped", "ship_by": "2026-08-17T00:00:00Z"}],
    "listings": [{"sku": "C", "status": "Active"}],
    "delisted": [], "supplier_alerts": [], "repricer_actions": [],
    "data_age_hours": 2,
    "cockpit": {"need_ordering": 0, "already_out": 0, "headline": "fine"},
})
check("the first row needs attention", out["checks"][0]["status"], _dc.OFF)
statuses = [c["status"] for c in out["checks"]]
check("  and no ok row sits above an off one",
      statuses.index(_dc.OK) > max(i for i, s in enumerate(statuses)
                                   if s == _dc.OFF), True)
truthy("the headline counts them", "need" in out["headline"])

print("\n== the counts are numbers, not a success flag ==")
# n_ok, not ok: the route adds its own {"ok": True} and silently overwrote the
# count, so the API reported a boolean where a reader expects a number.
for k in ("n_off", "n_ok", "n_unknown"):
    truthy("run() reports %s" % k, isinstance(out.get(k), int))
check("  and does not claim the key the route needs", "ok" in out, False)
check("  the counts add up", out["n_off"] + out["n_ok"] + out["n_unknown"],
      len(out["checks"]))

print("\n== nothing here reaches out or changes anything ==")
import re                                                        # noqa: E402
SRC = open(r"D:\AltaScraper\domain\daily_check.py", encoding="utf-8-sig").read()
BODY = re.sub(r'"""[\s\S]*?"""', "", SRC)
BODY = "\n".join(re.sub(r"#.*$", "", ln) for ln in BODY.split("\n"))
for banned in ("requests.", "urllib", "INSERT", "UPDATE", "DELETE", "commit("):
    check("the round never %r" % banned, banned in BODY, False)
# One broken feed must not turn twelve checks green.
RT = open(r"D:\AltaScraper\routes\daily_routes.py", encoding="utf-8-sig").read()
truthy("every source is fetched in its own try", RT.count("except Exception") >= 5)
truthy("  and a failure leaves the key ABSENT rather than empty",
       "leaves its key ABSENT" in RT)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
