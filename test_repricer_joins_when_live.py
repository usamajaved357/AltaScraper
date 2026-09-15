# -*- coding: utf-8 -*-
"""A listing joins the repricer when it goes live -- and a draft is never a deletion.

    "see Screenshot (166).png why so many items left repricer and new listings
     didn't joined repricer?"

    "i received an order of the sku 12.90_2Days_B0CZ6SWQQY and its asin is
     B0HJ8S7C82, i received its order but couldn't find it in repricer, no
     suppliers, why? i think i am creating listings with their suppliers in the
     sheet, so the suppliers should already be there"

THREE FAULTS, one question -- "when does a listing belong in the repricer?" --
answered three different ways.

ONE. SELLER IMPORT ENROLLED DRAFTS. /seller/draft put every draft into the
repricer the moment it was saved. The daily check asked Amazon for each SKU,
Amazon answered 404 because they were never published, and 29 children of eBay
listing 188400267090 were announced as "29 listings left the repricer" -- which
reads as live listings vanishing. It also contradicted the owner's 7 Sep 2026
instruction: suppliers join the repricer "when the listing goes live, not on
draft".

TWO. GOING LIVE NEVER ENROLLED ANYTHING. promote_to_live moved a supplier's
STAGE and stopped. Every repricer screen lists enrolled SKUs, so a listing could
be selling with suppliers and never appear.

THREE. OLDER LISTINGS NEVER HAD THEIR SUPPLIERS COPIED. Measured on
nestwell_goods 12.90_2Days_B0CZ6SWQQY: Active in the live catalogue as
B0HJ8S7C82, an eBay link on its own row -- and no source and no enrolment in the
repricer. It was generated 13 Aug; copying a row's suppliers across only began
with generation on 7 Sep (3cdf2cf).

WHAT IS PINNED:
  * the one rule that decides joining (source_repo.auto_enrol), including the
    two cases where joining would be wrong: disarming an armed SKU, and
    re-adding one the owner removed;
  * suppliers are read back off the listing row for listings made before 7 Sep;
  * the live-catalogue save is what triggers it, for Active listings only;
  * a never-published draft answering 404 is not reported as a deletion, while
    a SKU with no listing row keeps the old reading;
  * seller import no longer enrols drafts.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-68s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


# A throwaway database and config, set BEFORE anything opens the real one.
TMP = tempfile.mkdtemp(prefix="altajoin_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "nestwell_goods", "seller_id": "SELLER1",
                         "marketplace": "UK", "lwa_client_id": "x",
                         "lwa_client_secret": "y", "refresh_token": "z"}]},
          open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "d.db")

from data import db as _db                        # noqa: E402
from data.store import ListingStore               # noqa: E402
from domain import source_repo as R               # noqa: E402
from listing import suppliers as S                # noqa: E402

WS, MKT = "nestwell_goods", "UK"
conn = _db.get_db(CFG)


def enrol_row(sku):
    r = conn.execute("SELECT enrolled, mode, listing_state FROM sourcing_enrolment "
                     "WHERE workspace_id=? AND marketplace=? AND sku=?",
                     (WS, MKT, sku)).fetchone()
    return None if r is None else (int(r[0]), r[1], r[2])


# ----------------------------------------------------------------------------
print("== the one rule that decides joining ==")

check("a SKU never in the repricer is ADDED", R.auto_enrol(CFG, WS, MKT, "NEW-1"), R.ADDED)
check("  in dry run", enrol_row("NEW-1")[:2], (1, "dry_run"))

R.enrol(CFG, WS, MKT, "ARMED-1", mode="live")
check("an ARMED SKU is left alone", R.auto_enrol(CFG, WS, MKT, "ARMED-1"), "")
# THE ONE THAT WOULD HURT. enrol() overwrites the mode on conflict, so a naive
# join would silently disarm this on the next sync.
check("  and is still armed", enrol_row("ARMED-1")[:2], (1, "live"))

R.enrol(CFG, WS, MKT, "OWNER-OUT", mode="dry_run")
R.unenrol(CFG, WS, MKT, "OWNER-OUT")               # taken out by hand
check("a SKU the OWNER removed is not put back", R.auto_enrol(CFG, WS, MKT, "OWNER-OUT"), "")
check("  and stays out", enrol_row("OWNER-OUT")[0], 0)

R.enrol(CFG, WS, MKT, "APP-OUT", mode="live")
R.stop_tracking(CFG, WS, MKT, "APP-OUT")           # the app removed it: 404
check("a SKU the APP removed REJOINS when live again",
      R.auto_enrol(CFG, WS, MKT, "APP-OUT"), R.REJOINED)
check("  enrolled, and no longer marked gone",
      (enrol_row("APP-OUT")[0], enrol_row("APP-OUT")[2]), (1, R.LIVE_OK))
check("  still disarmed -- marking it gone disarmed it, and joining re-arms nothing",
      enrol_row("APP-OUT")[1], "dry_run")


# ----------------------------------------------------------------------------
print("\n== the reported SKU: supplier on the row, nothing in the repricer ==")
SKU = "12.90_2Days_B0CZ6SWQQY"
EBAY = "https://www.ebay.co.uk/itm/225692129265"
store = ListingStore(WS, config_path=CFG)
store.upsert_row({"SKU": SKU, "Status": "GENERATED", "Source URL": EBAY,
                  "Competitor ASIN": "B0CZ6SWQQY", "Title": "Garden Hose"})

check("the row's supplier is readable", R.listing_supplier_urls(CFG, WS, SKU), [(1, EBAY)])
falsy("  and the repricer has none -- as measured", R.has_sources(CFG, WS, MKT, SKU))

got = S.join_live(CFG, WS, MKT, [SKU])
check("joining back-fills the supplier from the row", got["backfilled"], [SKU])
truthy("  so the repricer now has it", R.has_sources(CFG, WS, MKT, SKU))
check("  and the listing is added", got["added"], [SKU])
check("  in dry run", enrol_row(SKU)[:2], (1, "dry_run"))
_stages = {r["stage"] for r in (dict(x) for x in conn.execute(
    "SELECT stage FROM sourcing_sources WHERE sku=?", (SKU,)))}
check("  and its supplier is LIVE, so the pricing pass can see it", _stages, {R.LIVE})

got2 = S.join_live(CFG, WS, MKT, [SKU])
check("joining twice changes nothing", (got2["added"], got2["backfilled"]), ([], []))
check("  and does not duplicate the supplier",
      conn.execute("SELECT COUNT(*) FROM sourcing_sources WHERE sku=?", (SKU,)).fetchone()[0], 1)

store.upsert_row({"SKU": "NO-SUPPLIER", "Status": "LIVE", "Title": "x"})
got3 = S.join_live(CFG, WS, MKT, ["NO-SUPPLIER"])
check("a live listing with no supplier anywhere is not enrolled",
      got3["no_supplier"], ["NO-SUPPLIER"])
check("  (nothing for the repricer to price from)", enrol_row("NO-SUPPLIER"), None)


# ----------------------------------------------------------------------------
print("\n== what triggers it: saving Amazon's live catalogue, Active only ==")
from domain import live_snapshots as L            # noqa: E402

for sku, url in (("ACTIVE-1", "https://www.ebay.co.uk/itm/1"),
                 ("SUPPRESSED-1", "https://www.ebay.co.uk/itm/2")):
    store.upsert_row({"SKU": sku, "Status": "GENERATED", "Source URL": url, "Title": sku})
L.save(CFG, WS, MKT, [{"sku": "ACTIVE-1", "asin": "B0AAAAAAAA", "status": "Active"},
                      {"sku": "SUPPRESSED-1", "asin": "B0BBBBBBBB", "status": "Suppressed"}])
check("an Active listing joins when the catalogue is saved", enrol_row("ACTIVE-1")[:2], (1, "dry_run"))
check("  a Suppressed one does not -- nobody can buy it", enrol_row("SUPPRESSED-1"), None)


# ----------------------------------------------------------------------------
print("\n== a never-published draft is not a deletion ==")
from api import amazon_listings as AL             # noqa: E402
from domain import source_run as RUN              # noqa: E402

DRAFT_SKU, NOROW_SKU = "11.99_3Days_188400267090v695912644567", "SKU-NO-ROW"
store.upsert_row({"SKU": DRAFT_SKU, "Status": "NEEDS_REVIEW", "Title": "draft"})
for sku in (DRAFT_SKU, NOROW_SKU):
    R.enrol(CFG, WS, MKT, sku, mode="dry_run")
_404 = {"status": AL.GONE, "attributes": None, "product_type": "",
        "error": "not found", "http_code": 404, "raw": None}
_real_get = AL.get_item
AL.get_item = lambda creds, mkt, seller, sku, mid, included=None, timeout=60: (
    _404 if sku in (DRAFT_SKU, NOROW_SKU) else
    {"status": AL.OK, "attributes": {}, "product_type": "X", "error": "",
     "http_code": 200, "raw": {}})
try:
    acc = json.load(open(CFG))["accounts"][0]
    res = RUN.check_listings(CFG, acc, WS, MKT)
finally:
    AL.get_item = _real_get

truthy("the draft is reported as not published", DRAFT_SKU in res["not_published"])
falsy("  and NOT as gone", DRAFT_SKU in res["gone"])
falsy("  and NOT in the removed list the 'left the repricer' notice reads",
      DRAFT_SKU in res["removed"])
check("  it still leaves the repricer -- a draft does not belong there",
      enrol_row(DRAFT_SKU)[0], 0)
check("  marked so it rejoins by itself once live", enrol_row(DRAFT_SKU)[2], R.GONE)
truthy("  and the note says so", "never been published" in res["note"])
# A SKU with no listing row here keeps the old reading: nothing can prove it was
# a draft, and a real deletion must never be explained away.
truthy("a 404 with no listing row is still treated as a deletion", NOROW_SKU in res["removed"])

check("the draft rejoins when Amazon lists it", R.auto_enrol(CFG, WS, MKT, DRAFT_SKU), R.REJOINED)


# ----------------------------------------------------------------------------
print("\n== seller import no longer enrols drafts ==")
SR = open(os.path.join("routes", "seller_routes.py"), encoding="utf-8").read()
_draft_fn = SR.split("def seller_draft(")[1]
falsy("the draft route calls enrol() on nothing", "_repo.enrol(" in _draft_fn)
truthy("  it records the eBay supplier at stage DRAFT instead", "stage=_repo.DRAFT" in _draft_fn)

SCH = open(os.path.join("data", "scheduler.py"), encoding="utf-8").read()
truthy("the daily job words drafts differently from deletions",
       "taken out of the repricer until" in SCH)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
