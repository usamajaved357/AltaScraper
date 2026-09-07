"""A draft's suppliers stay on the drafts page until the listing sells.

    "these suppliers should be added to the all orders page sources and in
     repricer when the listing goes live, not on draft, on draft the sources
     should stay on the drafts page but should display the handling time, the
     carrier info and delivery time and source price and source name etc same as
     repricer shows it, in the same format"

...and there was nowhere to put a second supplier in the first place:

    "when i download the blank template it do not ask me for more than 1
     supplier, i said ask me for upto 3 suppliers in the template, i will add
     more suppliers if i have them"

MEASURED BEFORE ANY OF THIS WAS WRITTEN: the `listings` table had one supplier
column, `source_url`, and data/column_map.py named no other. listing/suppliers.py
finds supplier columns BY PATTERN, so on a Google Sheet a person could add a
column and it worked -- and on the database, which this account uses, there were
none to find. Every row had exactly one supplier however many links were pasted
in, which is what he hit.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


print("=== there is somewhere to put supplier 2 and 3 ===")
from data import column_map as CM
from data import db as _db

check("the headers exist",
      [h for h in CM.HEADER_TO_COL if h.startswith("Supplier")],
      ["Supplier 2", "Supplier 3"])
check("  mapping to their own columns", CM.HEADER_TO_COL["Supplier 2"], "supplier_2")
# APPENDED, NEVER INSERTED. ORDERED_HEADERS is this dict in order and positional
# writes follow it, so a key in the middle would shift every column after it and
# silently rewrite stored rows.
_keys = list(CM.HEADER_TO_COL)
check("  and appended last, so no stored column shifts",
      _keys[-2:], ["Supplier 2", "Supplier 3"])

conn = _db.get_db("config.json")
_cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
truthy("the live database has them", {"supplier_2", "supplier_3"} <= _cols)

print("\n=== the blank template asks for three, and accepts more ===")
IU = open(os.path.join("routes", "input_upload_routes.py"), encoding="utf-8").read()
_tpl = IU.split("def input_upload_template(")[1]
truthy("the template offers supplier_2 and supplier_3",
       '"supplier_2", "supplier_3"' in _tpl)
truthy("  with an example link in each", _tpl.count("ebay.co.uk/itm/") >= 3)
truthy("  and says they are optional", "OPTIONAL" in _tpl)
truthy("  and that a fourth is just another column", "supplier_4" in _tpl)

# A FOURTH NEEDS NO CODE CHANGE, which is what "i will add more suppliers if i
# have them" asks for. The header matcher is the same pattern the merge module
# uses to find columns, so a header that works in one works in the other.
from data import input_row as IR

check("supplier_2 is understood", IR.column_for("supplier_2"), "supplier_2")
check("  however it is spelt", IR.column_for("Supplier 3"), "supplier_3")
check("  a fourth, with no code change", IR.column_for("supplier_4"), "supplier_4")
check("  and the sheet's other spelling", IR.column_for("Source URL 5"), "supplier_5")
# Position 1 is the column every existing file already uses.
check("supplier 1 is still ebay_url", IR.column_for("supplier_1"), "ebay_url")
check("  as is Source URL", IR.column_for("Source URL"), "ebay_url")
check("something unrelated still means nothing", IR.column_for("random"), "")

print("\n=== an uploaded row carries them through ===")
row, _extras = IR.to_listing_row(
    {"ebay_url": "a://1", "supplier_2": "a://2", "supplier_3": "a://3",
     "item_name": "Spin Mop"}, set())
check("supplier 1 lands in the column it always did", row.get("Source URL"), "a://1")
check("  and 2 and 3 in theirs",
      (row.get("Supplier 2"), row.get("Supplier 3")), ("a://2", "a://3"))
row1, _ = IR.to_listing_row({"ebay_url": "a://1", "item_name": "X"}, set())
falsy("a one-supplier row is unchanged -- no empty columns invented",
      "Supplier 2" in row1)

# ...and the merge module then finds them in priority order.
from listing import suppliers as S
item = {CM.HEADER_TO_COL.get(k, k.strip().lower().replace(" ", "_")): v
        for k, v in row.items()}
check("the merge finds all three, in the owner's order",
      S.urls_from(item, list(row.keys())),
      [(1, "a://1"), (2, "a://2"), (3, "a://3")])

print("\n=== draft suppliers are recorded but NOT tracked ===")
from domain import source_repo as R

check("there are two stages", (R.DRAFT, R.LIVE), ("draft", "live"))
SUP = open(os.path.join("listing", "suppliers.py"), encoding="utf-8").read()
truthy("generation enrols them as drafts", "stage=_repo.DRAFT" in SUP)
# NULL READS AS LIVE. 55 sources were enrolled before this column existed and
# were being tracked; a migration that silently un-tracked them would stop the
# repricer pricing listings it has priced for weeks.
_cols2 = {r[1] for r in conn.execute("PRAGMA table_info(sourcing_sources)")}
truthy("the sources table has a stage", "stage" in _cols2)
truthy("  and a missing one reads as live", "or LIVE" in
       open(os.path.join("domain", "source_repo.py"), encoding="utf-8").read()
       .split("def _stage_of(")[1][:400])

print("\n=== the two live screens cannot see a draft's suppliers ===")
ORD = open(os.path.join("routes", "orders_routes.py"), encoding="utf-8").read()
SRC = open(os.path.join("routes", "sourcing_routes.py"), encoding="utf-8").read()
RUN = open(os.path.join("domain", "source_run.py"), encoding="utf-8").read()
truthy("the order panel asks for live only", "stage=_repo.LIVE" in ORD)
truthy("the repricer screen asks for live only", "stage=_repo.LIVE" in SRC)
truthy("  and so does the decision that sets the price",
       "stage=_repo.LIVE" in RUN)

print("\n=== going BUYABLE is what starts tracking them ===")
G = open("amazon_listing_generator.py", encoding="utf-8").read()
_buy = G.split('if "BUYABLE" in _st_up:')[1].split('elif "DISCOVERABLE"')[0]
truthy("the promotion happens on the BUYABLE branch",
       "promote_to_live(" in _buy)
# NOT on DISCOVERABLE: a product page with no offer attached is not a listing
# the repricer can price. Measured on 9.99_2Days_B0BP1HNW8G, DISCOVERABLE with
# offers: [] for over an hour.
_disc = G.split('elif "DISCOVERABLE" in _st_up:')[1].split("elif _rerrs:")[0]
falsy("  and never on the discoverable-but-not-buyable one",
      "promote_to_live(" in _disc)
truthy("  and it can never lose a row that just went live",
       "could not start tracking suppliers" in G)

print("\n=== a draft's suppliers still get CHECKED, or the panel is empty ===")
# The sweep is bounded by `enrolled`, which a draft is deliberately not in. So
# without this its supplier panel would show names and no prices, for ever --
# and price, carrier and delivery are exactly what was asked for.
truthy("there is a way to list SKUs by whether they HAVE sources",
       hasattr(R, "skus_with_sources"))
check("  drafts and live are separable",
      (len(R.skus_with_sources("config.json", stage=R.LIVE))
       + len(R.skus_with_sources("config.json", stage=R.DRAFT))),
      len(R.skus_with_sources("config.json")))
F = open(os.path.join("domain", "source_fetch.py"), encoding="utf-8").read()
truthy("the sweep adds them to what it reads",
       "skus_with_sources(config_path, workspace_id, marketplace," in F
       and "stage=_repo.DRAFT" in F)
truthy("  without letting them near a price decision",
       "CHECKING A PRICE IS NOT REPRICING" in F)
truthy("  and a failure there does not stop the sweep",
       "still a sweep" in F)

print("\n=== the drafts page draws them in the repricer's own format ===")
DR = open(os.path.join("routes", "draft_sources_routes.py"), encoding="utf-8").read()
truthy("the route asks the shared options builder (Rule 12)",
       "_osrc.options_for(" in DR)
truthy("  for the draft stage by default", "_repo.DRAFT" in DR)
truthy("  and says they are not tracked yet", "once" in DR and "buyable" in DR)
JS = open(os.path.join("static", "js", "draftsources.js"), encoding="utf-8").read()
truthy("the panel reuses the order panel's renderer", "_ordSourcesHtml(" in JS)
falsy("  and draws no supplier table of its own",
      "delivery_min" in JS or "postage_text" in JS)
L = open(os.path.join("static", "js", "listings.js"), encoding="utf-8").read()
truthy("the drawer shows it", "draftSourcesHtml(r)" in L)
H = open(os.path.join("templates", "dashboard.html"), encoding="utf-8").read()
truthy("  and the file is loaded", "/static/js/draftsources.js" in H)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("  - " + f)
raise SystemExit(1 if fails else 0)
