"""A catalogue that can never be written again is worse than one that is short.

THE BUG THIS PINS

    "the app was showing some items out of stock i went to seller central and
     added stock to some of them in nestwell goods but the app is still showing
     it out of stock even i have refreshed and wait for many hours also"

domain/live_snapshots.save() used to DISCARD an incomplete result wholesale when
the stored record had more listings, and return the previous record untouched.
That guarded a real failure -- the inactive-report half failing and collapsing a
64-item catalogue to 16 -- but it froze EVERYTHING in the record: prices,
statuses, and the quantity the Inventory screen reads.

The caller made it permanent. It raised a warning BECAUSE the new list was
shorter, `partial` was `bool(warnings)`, so any account whose listing count went
down could never write again. The warning even read "Showing the new result",
which was true of the screen and false of the disk.

Measured in live_snapshots.json, 18 Aug 2026:

    nestwell_goods::UK   count 45, ts 04:49:33
                         superseded_by_partial_at 08:36:04
                         last_partial_count 42
    jack_uk::UK          the same signature, ~08:26

Seven nestwell SKUs sat at qty 0 that had been restocked in Seller Central hours
earlier, while the background refresher retried every ten minutes and was refused
every time, silently.

THE RULE NOW, AND WHY IT IS TWO RULES

    a COMPLETE sync REPLACES     it is the authority; a listing missing from it
                                 is gone, and a delete has to be able to reach
                                 the store or the catalogue only ever grows
    an INCOMPLETE sync MERGES    fresh readings win per SKU; listings it never
                                 mentioned are carried from the previous record

Both properties are needed and they pull in opposite directions, which is why
this file tests them against each other rather than one at a time.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"D:\AltaScraper")

from domain import live_snapshots as _snap      # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                  % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altasnap_")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write("{}")


def item(sku, qty, status="Active", **kw):
    d = {"sku": sku, "qty": qty, "status": status, "price": "9.99"}
    d.update(kw)
    return d


def qty_of(rec, sku):
    for it in rec.get("items") or []:
        if it.get("sku") == sku:
            return it.get("qty")
    return "ABSENT"


ACC, MKT = "nestwell_goods", "UK"

print("\n== the exact situation that was frozen ==")
# 45 listings stored by a complete sync, seven of them at zero.
full = [item("SKU%02d" % i, 5) for i in range(1, 39)]
full += [item(s, 0, "Inactive") for s in
         ("10.06_3Days_B0081ZHHTS", "10.39_3Days_B0F6LQ1S93",
          "3.70_3Days_B0DF2W6B6C", "6.89_2Days_B0GY4MTGKD",
          "8.89_2Days_B0FM3Q3FVR", "8.89_3Days_B0CQXJWXQF",
          "8.99_5Days_B09BNLQG2Q")]
rec = _snap.save(CFG, ACC, MKT, full, report_source="new", partial=False)
check("45 listings stored by the complete sync", rec["count"], 45)
check("  and one of them reads zero", qty_of(rec, "6.89_2Days_B0GY4MTGKD"), 0)

# Now the owner restocks in Seller Central and a later sync returns 42 listings
# -- three fewer, which is exactly what made the old code refuse it for ever.
restocked = [item("SKU%02d" % i, 5) for i in range(1, 39)]
restocked += [item("6.89_2Days_B0GY4MTGKD", 12),
              item("8.89_2Days_B0FM3Q3FVR", 8),
              item("10.06_3Days_B0081ZHHTS", 3),
              item("3.70_3Days_B0DF2W6B6C", 0, "Inactive")]
rec = _snap.save(CFG, ACC, MKT, restocked, report_source="new", partial=False)

check("the shorter COMPLETE sync is written, not discarded", rec["count"], 42)
check("  the restocked SKU now reads 12", qty_of(rec, "6.89_2Days_B0GY4MTGKD"), 12)
check("  and the second one reads 8", qty_of(rec, "8.89_2Days_B0FM3Q3FVR"), 8)
check("  a listing that really went is really gone",
      qty_of(rec, "8.99_5Days_B09BNLQG2Q"), "ABSENT")
check("  nothing was carried, because nothing was missing",
      rec.get("carried_listings"), 0)
# The old code left this key behind; its presence means the write was refused.
check("  the record is not marked as superseded",
      "superseded_by_partial_at" in rec, False)

print("\n== reading it back gives the same answer ==")
back = _snap.get(CFG, ACC, MKT) or {}
check("the stored copy has the restocked figure",
      qty_of(back, "6.89_2Days_B0GY4MTGKD"), 12)
check("  and the stored count", back.get("count"), 42)

print("\n== an INCOMPLETE sync still cannot erase a catalogue ==")
# This is the 64 -> 16 collapse: the inactive report fails, so only the active
# listings come back. The three inactive ones must survive.
active_only = [item("SKU%02d" % i, 7) for i in range(1, 39)]
active_only += [item("6.89_2Days_B0GY4MTGKD", 20)]
rec = _snap.save(CFG, ACC, MKT, active_only, report_source="new", partial=True,
                 warnings=["Inactive/suppressed listings could not be loaded"])
check("nothing was lost", rec["count"], 42)
check("  three listings were carried from the previous sync",
      rec.get("carried_listings"), 3)
check("  including the one only the inactive report knew about",
      qty_of(rec, "10.06_3Days_B0081ZHHTS"), 3)
# THE POINT: an incomplete sync still updates what it DID see. This is the half
# the old guard threw away along with everything else.
check("  and the fresh reading still won for a SKU it did see",
      qty_of(rec, "6.89_2Days_B0GY4MTGKD"), 20)
check("  a carried row says so, so nothing mistakes it for confirmed",
      [it.get("carried_from_previous_sync")
       for it in rec["items"] if it["sku"] == "10.06_3Days_B0081ZHHTS"], [True])
check("  and it is still flagged partial", rec["partial"], True)

print("\n== and the store can always move ==")
# The property the old code lost: no state in which a write is refused. Ten
# incomplete syncs in a row, each one smaller, all of them written.
for n in range(10):
    rec = _snap.save(CFG, ACC, MKT, [item("SKU01", 100 + n)],
                     report_source="new", partial=True, warnings=["report failed"])
    check("incomplete sync %d wrote its fresh reading" % (n + 1),
          qty_of(rec, "SKU01"), 100 + n)
check("  and never dropped the rest of the catalogue", rec["count"] >= 42, True)

print("\n== a complete sync is still the authority afterwards ==")
rec = _snap.save(CFG, ACC, MKT, [item("SKU01", 1), item("SKU02", 2)],
                 report_source="new", partial=False)
check("it replaces everything a run of incomplete ones carried", rec["count"], 2)
check("  carrying nothing", rec.get("carried_listings"), 0)

print("\n== images are still carried, which is a different rule ==")
# _carry_forward fills BLANK FIELDS per SKU. Independent of the above, and it
# must keep working for a complete sync -- the report has no images in it.
_snap.save(CFG, ACC, MKT, [item("SKU01", 1, img="https://m.media.../x.jpg")],
           report_source="new", partial=False)
rec = _snap.save(CFG, ACC, MKT, [item("SKU01", 4)], report_source="new",
                 partial=False)
check("a fresh report with no image keeps the one already known",
      [it.get("img") for it in rec["items"]], ["https://m.media.../x.jpg"])
check("  while the quantity still updates", qty_of(rec, "SKU01"), 4)

print("\n== the caller no longer votes with the wrong list ==")
import re                                                        # noqa: E402
SRC = open(r"D:\AltaScraper\routes\live_routes.py", encoding="utf-8-sig").read()
BODY = "\n".join(re.sub(r"#.*$", "", ln) for ln in SRC.split("\n"))
truthy("there is a separate list for things that are not faults",
       re.search(r"^\s*notes\s*=\s*\[\]", BODY, re.M))
truthy("  and the shrink message goes into it",
       re.search(r"notes\s*=\s*list\(notes[\s\S]{0,200}fewer than", BODY))
check("  so a shorter list cannot mark a sync incomplete",
      bool(re.search(r"warnings\s*=\s*list\(warnings[\s\S]{0,200}fewer than", BODY)),
      False)
truthy("partial is still set by a report that genuinely failed",
       re.search(r"warnings\.append\([\s\S]{0,120}could not be loaded", BODY))

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
