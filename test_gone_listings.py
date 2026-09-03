"""A listing deleted on Amazon leaves the repricer by itself.

    "if the listing is deleted from my sellercentral i think the app knows it,
     so lets remove the deleted items from repricer automatically"

It did know -- and only when somebody pressed "Check listings". Nothing ran that
check on a timer, so a SKU deleted in Seller Central stayed in the repricer,
was priced every four hours, and sat in the list looking like a live product
until a person happened to ask.

WHAT THIS GUARDS

  only a 404 counts     api/amazon_listings maps HTTP 404 alone to GONE and
                        everything else -- a timeout, or the 403 an account
                        without SP-API roles answers with -- to FAILED. A SKU
                        Amazon would not talk about must be left exactly as it
                        was. Measured on jack_uk, whose Product Fees role is
                        missing: every one of its SKUs answers 403, and not one
                        of them may be treated as deleted.

  removal keeps         unenrol() sets enrolled=0. The row, the supplier links,
  everything            the price history and the rule all survive, so a
                        relisted SKU can be re-enrolled with all of it intact.
                        That is what makes this safe to do unattended.

  one implementation    the button and the daily job call the same function.
                        Two copies would drift into "the automatic one removes
                        things the button does not" (CLAUDE.md Rule 12).

Nothing here touches the network: api/amazon_listings.get_item is stubbed and
the stub decides what Amazon "answers" per SKU.
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-66s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


def truthy(l, g):
    check(l, bool(g), True)


def falsy(l, g):
    check(l, bool(g), False)


TMP = tempfile.mkdtemp(prefix="altagone_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "jack_uk", "seller_id": "SELLER1",
                         "marketplace": "UK", "lwa_client_id": "x",
                         "lwa_client_secret": "y", "refresh_token": "z"}]},
          open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "d.db")

from api import amazon_listings as AL          # noqa: E402
from domain import source_repo as R            # noqa: E402
from domain import source_run as RUN           # noqa: E402

WS, MKT = "jack_uk", "UK"
LIVE, DELETED, SILENT = "SKU-LIVE", "SKU-DELETED", "SKU-403"

for sku in (LIVE, DELETED, SILENT):
    R.enrol(CFG, WS, MKT, sku, mode="live")
R.add_source(CFG, WS, MKT, DELETED, "https://example.invalid/thing", kind="ebay")

# What Amazon answers for each SKU. 404 is the ONLY deletion.
ANSWERS = {
    LIVE:    {"status": AL.OK, "attributes": {}, "product_type": "X",
              "error": "", "http_code": 200, "raw": {}},
    DELETED: {"status": AL.GONE, "attributes": None, "product_type": "",
              "error": "not found", "http_code": 404, "raw": None},
    SILENT:  {"status": AL.FAILED, "attributes": None, "product_type": "",
              "error": "Unauthorized", "http_code": 403, "raw": None},
}
AL.get_item = lambda creds, mkt, seller, sku, mid, included=None, timeout=60: \
    ANSWERS[sku]

acc = json.load(open(CFG))["accounts"][0]

print("=== before the check, all three are in the repricer ===")
check("three enrolled", len(R.enrolled(CFG, WS, MKT)), 3)

print("\n=== the check runs, and only the 404 is removed ===")
got = RUN.check_listings(CFG, acc, WS, MKT)
check("all three were asked about", got["checked"], 3)
check("the deleted one is reported gone", got["gone"], [DELETED])
check("  and taken out of the repricer", got["removed"], [DELETED])
check("the live one is still there", got["still_there"], 1)
check("the one Amazon would not answer for is left alone",
      got["unreadable"], [SILENT])

print("\n=== what the repricer sees afterwards ===")
left = [r["sku"] for r in R.enrolled(CFG, WS, MKT)]
check("the deleted SKU is out of the enrolled list", DELETED in left, False)
check("  and the live one is untouched", LIVE in left, True)
check("  and so is the one that only failed to answer", SILENT in left, True)

print("\n=== nothing was deleted ===")
# The row survives with its state, so the screen can say WHY it left, and a
# relisted SKU can be re-enrolled with everything it had.
from data import db as _db                     # noqa: E402
row = _db.get_db(CFG).execute(
    "SELECT enrolled, mode, listing_state FROM sourcing_enrolment "
    " WHERE workspace_id=? AND marketplace=? AND sku=?",
    (WS, MKT, DELETED)).fetchone()
truthy("the enrolment row is still there", row is not None)
check("  marked as gone", row["listing_state"], R.GONE)
check("  unenrolled", row["enrolled"], 0)
# Disarmed as well as unenrolled: unenrolled-but-armed is a SKU nothing watches
# and something could still push to.
check("  and disarmed, not just hidden", row["mode"], "dry_run")
check("its supplier link survives",
      len(R.sources_for(CFG, WS, MKT, DELETED)), 1)

print("\n=== re-enrolling brings it back whole ===")
R.enrol(CFG, WS, MKT, DELETED, mode="dry_run")
back = [r["sku"] for r in R.enrolled(CFG, WS, MKT)]
check("it is in the repricer again", DELETED in back, True)
check("  with its supplier still attached",
      len(R.sources_for(CFG, WS, MKT, DELETED)), 1)

print("\n=== a caller can ask for the old behaviour ===")
# Marking without removing, for a caller that wants to see them first.
R.enrol(CFG, WS, MKT, DELETED, mode="live")
got2 = RUN.check_listings(CFG, acc, WS, MKT, remove_gone=False)
check("nothing is removed when it is not asked for", got2["removed"], [])
check("  but it is still reported gone", got2["gone"], [DELETED])
check("  and still disarmed", _db.get_db(CFG).execute(
    "SELECT mode FROM sourcing_enrolment WHERE sku=?", (DELETED,)
).fetchone()["mode"], "dry_run")

print("\n=== an account that cannot be asked is refused, not guessed at ===")
bad = RUN.check_listings(CFG, {"id": WS}, WS, MKT)   # no seller_id
truthy("no seller id -> an error, not a purge", bad["error"])
check("  and nothing was removed", bad["removed"], [])

print("\n=== one implementation, two callers ===")
SR = open(os.path.join(r"D:\AltaScraper", "routes", "sourcing_routes.py"),
          encoding="utf-8").read()
SCH = open(os.path.join(r"D:\AltaScraper", "data", "scheduler.py"),
           encoding="utf-8").read()
truthy("the button calls the shared checker", "_run.check_listings(" in SR)
falsy("  and no longer has its own copy of the loop",
      "got = _al.get_item(creds, mkt, seller, sku, mid)" in SR)
truthy("the job calls the same one", "_run.check_listings(" in SCH)
truthy("  and is registered to run daily",
       'register_job("sourcing_listings", sourcing_listings, hours=24' in SCH)
# The four-hourly pricing pass must NOT carry this: one getListingsItem per
# enrolled SKU every four hours is four hundred calls a day to learn something
# that changes rarely.
falsy("it is not bolted onto the four-hourly pricing pass",
      "check_listings(" in SCH.split("def sourcing_check(")[1]
      .split("\ndef ")[0])

print("\n=== the automatic pass says what it did ===")
# The button toasts its note at the person who pressed it. The daily job has
# nobody watching, so a row that disappeared with no explanation anywhere would
# be a worse screen than the one showing a deleted SKU.
_job = SCH.split("def sourcing_listings(")[1].split("\ndef ")[0]
truthy("the job records a notification when it removes something",
       "_notify.announce(" in _job and "LISTING_GONE" in _job)
truthy("  naming the SKUs it took out", 'got["removed"]' in _job)
truthy("  and only when it removed something",
       'if got["removed"]:' in _job)
truthy("  without letting a failed notification undo the removal",
       "never let saying so undo the doing" in _job)
NT = open(os.path.join(r"D:\AltaScraper", "domain", "notify.py"),
          encoding="utf-8").read()
truthy("the kind exists", 'LISTING_GONE = "listing_gone"' in NT)
falsy("  and stays in the app rather than pinging Slack",
      "LISTING_GONE" in NT.split("OUTBOUND_KINDS = (")[1].split(")")[0])
JS = open(os.path.join(r"D:\AltaScraper", "static", "js", "notify.js"),
          encoding="utf-8").read()
truthy("  with an icon of its own in the bell",
       'k === "listing_gone"' in JS)

print("\n=== the evidence standard is written down where it is applied ===")
FN = open(os.path.join(r"D:\AltaScraper", "domain", "source_run.py"),
          encoding="utf-8").read().split("def check_listings(")[1] \
    .split("\ndef ")[0]
truthy("only a 404 counts as deleted", "_al.GONE" in FN)
truthy("  and everything else is left exactly as it was",
       "is NOT" in FN and "unreadable" in FN)
truthy("  with the 403 account named as the reason why", "403" in FN)

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
