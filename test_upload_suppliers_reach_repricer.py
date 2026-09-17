# -*- coding: utf-8 -*-
"""Every supplier in an uploaded file reaches the generator and the repricer.

    "I generated the listings with 3 suppliers (ebay links) in the template and
     the drafts are generated but the repricer has received only 1 supplier in
     it, other 2 are not there"

The upload stored supplier_2 and supplier_3 on the queued row, but
listing/queued_input handed the generator ebay_url alone, so process_row fell
back to [(1, ebay_url)]: supplier 1 was fetched and enrolled, 2 and 3 never.

PINNED, on a throwaway database:
  * listing/suppliers.from_listing_row reads every supplier column, in order,
    one link pasted twice being one supplier;
  * an uploaded row -> queued product -> temp JSON -> read_products keeps all
    three, as (position, url);
  * source_repo.listing_supplier_urls answers through the same reader;
  * the one-time repair adds the missing ones only where the bug's signature is,
    keeps the live/draft stage, leaves alone a SKU whose recorded suppliers the
    row does not name, and runs once.
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
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


TMP = tempfile.mkdtemp(prefix="altasupp_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "nestwell_goods"}]}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "d.db")

from data import db as _db                    # noqa: E402
from data import queued_store as QS           # noqa: E402
from data import input_row as IR              # noqa: E402
from domain import source_repo as REPO        # noqa: E402
from listing import suppliers as SUP          # noqa: E402
from listing import queued_input as QIN       # noqa: E402

W = "nestwell_goods"
S1 = "https://www.ebay.co.uk/itm/407153403493?var=677326367933"
S2 = "https://www.ebay.co.uk/itm/318548785995?var=616911433808"
S3 = "https://www.ebay.co.uk/itm/298495568629?var=595341682894"

print("== from_listing_row ==")
check("all three, in order",
      SUP.from_listing_row({"source_url": S1, "supplier_3": S3, "supplier_2": S2}),
      [(1, S1), (2, S2), (3, S3)])
check("blanks skipped, the same link twice is one supplier",
      SUP.from_listing_row({"source_url": S1, "supplier_2": "", "supplier_3": S1 + "/"}),
      [(1, S1)])
check("a row with no supplier 1 still gives the rest",
      SUP.from_listing_row({"source_url": "", "supplier_2": S2}), [(2, S2)])
check("the number orders them, not the text",
      [p for p, _ in SUP.from_listing_row({"supplier_10": "a", "supplier_9": "b", "source_url": "c"})],
      [1, 9, 10])

print("\n== an uploaded row keeps all three suppliers on the way to the generator ==")
headers = ["ebay_url", "supplier_2", "supplier_3", "amazon_url", "item_name",
           "source_cost", "selling_price", "upc", "handling_time"]
mapping, matched, ignored = IR.map_headers(headers)
product = IR.row_to_product([S1, S2, S3, "https://www.amazon.co.uk/dp/B0D4DFGSP4", "Sleeping pad",
                             "12.50", "", "", "3"], mapping)
QS.add_queued(CFG, W, product)
queued = QIN.products_for(CFG, W)
check("one queued product", len(queued), 1)
check("it carries every supplier", queued[0].get("supplier_urls"), [(1, S1), (2, S2), (3, S3)])
path = QIN.write_temp_input(queued)
back = QIN.read_products(path)
os.remove(path)
check("and the generator reads all three back", back[0].get("supplier_urls"),
      [(1, S1), (2, S2), (3, S3)])
check("ebay_url is still supplier 1", back[0].get("ebay_url"), S1)
sku = queued[0]["sku"]

print("\n== source_repo.listing_supplier_urls answers through the same reader ==")
check("the queued row's three", REPO.listing_supplier_urls(CFG, W, sku),
      [(1, S1), (2, S2), (3, S3)])

print("\n== the one-time repair ==")
conn = _db.get_db(CFG)


def add_row(s, status, s1, s2="", s3=""):
    conn.execute("INSERT INTO listings (workspace_id, sku, status, source_url, supplier_2, supplier_3) "
                 "VALUES (?,?,?,?,?,?)", (W, s, status, s1, s2, s3))
    conn.commit()


def urls(s, mkt="UK"):
    return sorted((r["url"], r["stage"] or "") for r in conn.execute(
        "SELECT url, stage FROM sourcing_sources WHERE workspace_id=? AND marketplace=? AND sku=?",
        (W, mkt, s)))


# the bug: supplier 1 recorded, 2 and 3 only on the row
add_row("DRAFT-BUG", "GENERATED", S1, S2, S3)
SUP.enrol(CFG, W, "UK", "DRAFT-BUG", [(1, S1)])
# the same, on a listing already live
add_row("LIVE-BUG", "LIVE", S1, S2, "")
SUP.enrol(CFG, W, "UK", "LIVE-BUG", [(1, S1)])
REPO.promote_to_live(CFG, W, "UK", "LIVE-BUG")
# the owner has a supplier the row does not name -- not ours to touch
add_row("OWNER-EDITED", "LIVE", S1, S2, "")
SUP.enrol(CFG, W, "UK", "OWNER-EDITED", [(1, S1)])
REPO.ensure_source(CFG, W, "UK", "OWNER-EDITED", "https://www.ebay.co.uk/itm/999", stage=REPO.LIVE)
# already complete
add_row("COMPLETE", "GENERATED", S1, S2, "")
SUP.enrol(CFG, W, "UK", "COMPLETE", [(1, S1), (2, S2)])
# supplier 1 removed by the owner, supplier 2 kept -- not the bug's signature
add_row("S1-REMOVED", "GENERATED", S1, S2, S3)
SUP.enrol(CFG, W, "UK", "S1-REMOVED", [(2, S2)])
# no supplier at all -- join_live's job, not this one
add_row("NONE", "GENERATED", S1, S2, "")

res = SUP.run_row_supplier_repair_once(CFG)
check("repaired exactly the two with the bug's signature",
      sorted(set(res["skus"])), ["DRAFT-BUG", "LIVE-BUG"])
check("a draft gets its missing two, as drafts",
      urls("DRAFT-BUG"), sorted([(S1, "draft"), (S2, "draft"), (S3, "draft")]))
check("a live listing's missing one is live", urls("LIVE-BUG"),
      sorted([(S1, "live"), (S2, "live")]))
check("priority follows the column number",
      [r["priority"] for r in conn.execute(
          "SELECT priority FROM sourcing_sources WHERE sku='DRAFT-BUG' ORDER BY priority")], [1, 2, 3])
check("an owner-edited SKU is left alone", len(urls("OWNER-EDITED")), 2)
check("a complete SKU is unchanged", len(urls("COMPLETE")), 2)
check("a SKU whose supplier 1 was removed is left alone", urls("S1-REMOVED"), [(S2, "draft")])
check("a SKU with no supplier is not this repair's", urls("NONE"), [])
check("the queued row from the upload (no supplier recorded) is untouched", urls(sku), [])

conn.execute("DELETE FROM sourcing_sources WHERE sku='DRAFT-BUG' AND url<>?", (S1,))
conn.commit()
check("it runs once: a second start does nothing", SUP.run_row_supplier_repair_once(CFG), None)
check("  so a supplier removed after the repair stays removed", urls("DRAFT-BUG"), [(S1, "draft")])
check("the mark is beside config.json",
      os.path.exists(os.path.join(TMP, SUP._REPAIR_MARK)), True)

print()
if fails:
    print("FAILED: %d" % len(fails))
    sys.exit(1)
print("all passed")
