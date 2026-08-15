"""Stop asking Amazon questions it keeps refusing.

THE REPORT: "about the background log, stop that from being happening app should
stop retrying for the marketplaces amazon refused".

Seen repeatedly in the live refresher's log:

    jack_uk::IE          InvalidInput
    nestwell_goods::IE   InvalidInput
    selvora_limited::IE  InvalidInput
    sheelady_us::MX      Unauthorized
    sheelady_us::CA      Unauthorized

Every one of those spends a report request against a quota SHARED with the sales
figures the owner is waiting for -- three in quick succession already earn a
QuotaExceeded. So this is not log tidiness; it is why real data arrives late.

The rules being tested: a refusal about the REQUEST rests the pair, a refusal
about Amazon being busy does not, the rest gets longer the more it happens, and
one success clears the record completely.
"""
import os, sys, json, time, tempfile, shutil

sys.path.insert(0, r"D:\AltaScraper")

import domain.marketplace_health as mh

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altamkt_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w").write("{}")

print("\n== Amazon's real refusals are recognised as being about the request ==")
for e in ("failed: report flow failed: SellingApiBadRequestException: "
          "[{'code': 'InvalidInput', 'message': ...}]",
          "failed: report flow failed: SellingApiForbiddenException: "
          "[{'code': 'Unauthorized', 'message': ...}]",
          "error: AccessDenied"):
    check_true("permanent: %s" % e[:44], mh.looks_permanent(e))

print("\n== Amazon merely being busy is NOT held against the pair ==")
for e in ("error: Read timed out", "failed: QuotaExceeded",
          "error: 503 Service Unavailable", "error: connection reset"):
    check("transient: %-34s" % e[:34], mh.looks_permanent(e), False)

print("\n== one refusal is not enough to rest a marketplace ==")
mh.record(CFG, "jack_uk", "IE", ok=False, error="InvalidInput")
check("still asked after a single refusal",
      mh.skip_reason(CFG, "jack_uk", "IE"), "")

print("\n== two refusals and it is rested ==")
mh.record(CFG, "jack_uk", "IE", ok=False, error="InvalidInput")
why = mh.skip_reason(CFG, "jack_uk", "IE")
check_true("now rested", bool(why))
check_true("and says how many times and why", "2 times" in why and "InvalidInput" in why)

print("\n== a busy Amazon never rests a pair, however often ==")
for _ in range(6):
    mh.record(CFG, "jack_uk", "UK", ok=False, error="QuotaExceeded")
check("a working marketplace is never parked for being busy",
      mh.skip_reason(CFG, "jack_uk", "UK"), "")

print("\n== the rest gets longer the more it is refused ==")
mh.record(CFG, "sheelady_us", "MX", ok=False, error="Unauthorized")
r2 = mh.record(CFG, "sheelady_us", "MX", ok=False, error="Unauthorized")
first = r2["rest_until"] - time.time()
r3 = mh.record(CFG, "sheelady_us", "MX", ok=False, error="Unauthorized")
second = r3["rest_until"] - time.time()
check_true("the second rest is longer than the first", second > first)
check_true("but it stops growing at a day", second <= 24 * 3600 + 5)

print("\n== one success wipes the record ==")
mh.record(CFG, "sheelady_us", "MX", ok=True)
check("asked again immediately after it works",
      mh.skip_reason(CFG, "sheelady_us", "MX"), "")
check("and it is gone from the rested list",
      [x for x in mh.status(CFG) if x["pair"] == "sheelady_us::MX"], [])

print("\n== the rest expires on its own ==")
check_true("rested now", bool(mh.skip_reason(CFG, "jack_uk", "IE")))
check("asked again once the rest is over",
      mh.skip_reason(CFG, "jack_uk", "IE", now=time.time() + 25 * 3600), "")

print("\n== the refresher's target list actually shrinks ==")
pairs = [("jack_uk", "UK"), ("jack_uk", "IE"), ("sheelady_us", "US")]
keep, skipped = mh.filter_targets(CFG, pairs)
check("the refused pair is dropped", ("jack_uk", "IE") in keep, False)
check("the working ones are kept", len(keep), 2)
check("and what was dropped is reported, not silent", len(skipped), 1)

print("\n== it is visible on /diag rather than only in a log ==")
st = mh.status(CFG)
ie = [x for x in st if x["pair"] == "jack_uk::IE"]
check("the rested pair is listed", len(ie), 1)
check_true("with the reason", "InvalidInput" in ie[0]["last_error"])
check_true("and when it will be tried again", ie[0]["resumes_in_minutes"] > 0)

print("\n== a corrupt or missing store never breaks the refresher ==")
open(os.path.join(TMP, "marketplace_health.json"), "w").write("{ not json")
check("unreadable store means ask normally",
      mh.skip_reason(CFG, "jack_uk", "IE"), "")
k2, _s2 = mh.filter_targets(CFG, pairs)
check("  and every pair is kept", len(k2), 3)

print("\n== the refresher consults it ==")
src = open(r"D:\AltaScraper\domain\live_refresher.py", encoding="utf-8").read()
check_true("targets are filtered", "filter_targets" in src)
check_true("and every outcome is recorded", "_mh.record(" in src)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
