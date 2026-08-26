"""Suppliers from a sheet, keyed by SKU or by ASIN, and the row at a glance.

"the repricer tool give me an option to upload a sheet containing the sku's or
 original asins of the item, to add their suppliers through a sheet upload, i
 will write, i can use whether the asin whether the sku"

and

"i want to add some additional info which give me a glance view to be displayed
 on each sku, current source price, current my selling price on which the item
 will be sold if i receive an order and the profit margin and the roi i will
 generate on the sale. source units available, the shipping days of the supplier"

The upload's job is matching, and the interesting cases are all failures: a key
that matches nothing, a link nothing can read, an ASIN that matches SEVERAL of
our SKUs. A bulk import that reports a total and nothing else is how twelve
silently-skipped rows become "the repricer is not working" a fortnight later.
"""
import json, os, sys, tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

TMP = tempfile.mkdtemp(prefix="altabulk_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "b.db")

from data import db as _db
from domain import source_bulk as B
from domain import source_repo as R

conn = _db.get_db(CFG)
WS, MKT = "ws", "UK"
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin) VALUES (?,?,?)",
             (WS, "9.99_3Days_B0AAAAAAAA", "B0AAAAAAAA"))
# The same competitor ASIN on TWO of our SKUs -- a relist. An ASIN row must
# attach to both and say so, not silently pick one.
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin) VALUES (?,?,?)",
             (WS, "8.50_2Days_B0BBBBBBBB", "B0BBBBBBBB"))
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin) VALUES (?,?,?)",
             (WS, "9.10_3Days_B0BBBBBBBB", "B0BBBBBBBB"))
conn.commit()


print("=== the columns are found however they are spelled ===")
for header in (["SKU", "Supplier Link"], ["Seller SKU", "url"],
               ["Item SKU", "eBay Source Link"], ["sku ", " LINK "]):
    out = B.apply_rows(CFG, WS, MKT, header,
                       [["9.99_3Days_B0AAAAAAAA", "https://www.ebay.co.uk/itm/111111111111"]])
    check("  %-34s -> ok" % (" / ".join(header)), out.get("ok"), True)

print("\n=== a row can be keyed by SKU or by ASIN ===")
out = B.apply_rows(CFG, WS, MKT, ["sku", "asin", "url"], [
    ["9.99_3Days_B0AAAAAAAA", "", "https://www.ebay.co.uk/itm/222222222222"],
    ["", "B0BBBBBBBB", "https://www.ebay.co.uk/itm/333333333333"],
])
check("both rows attached", out["attached"], 3)      # 1 by SKU + 2 by ASIN
check("  and both SKUs were enrolled by the ASIN row",
      len(out["rows"][1]["matched"]), 2)
truthy("  which it says out loud",
       "carries 2 of your SKUs" in out["rows"][1]["note"])

print("\n=== a key that matches nothing is refused, not invented ===")
# Taking a typed SKU on trust created an enrollment for a listing that does not
# exist, which then sat in the repricer for ever saying it could not be read.
out = B.apply_rows(CFG, WS, MKT, ["sku", "url"],
                   [["NO-SUCH-SKU", "https://www.ebay.co.uk/itm/444444444444"]])
check("nothing attached", out["attached"], 0)
check("  it is skipped", out["skipped"], 1)
truthy("  and named", "NO-SUCH-SKU" in out["rows"][0]["note"])
check("  and it is NOT now enrolled",
      [r for r in R.enrolled(CFG, WS, MKT) if r["sku"] == "NO-SUCH-SKU"], [])

print("\n=== a link that is not a supplier is refused ===")
# Rule 1: the Amazon page is the COMPETITOR the listing was modelled on.
out = B.apply_rows(CFG, WS, MKT, ["sku", "url"],
                   [["9.99_3Days_B0AAAAAAAA", "https://www.amazon.co.uk/dp/B0AAAAAAAA"]])
check("skipped", out["skipped"], 1)
truthy("  saying it is the competitor, not the supplier",
       "competitor" in out["rows"][0]["note"])
out = B.apply_rows(CFG, WS, MKT, ["sku", "url"],
                   [["9.99_3Days_B0AAAAAAAA", "https://www.ebay.co.uk/sch/i.html?_nkw=x"]])
check("an eBay search link is skipped too", out["skipped"], 1)

print("\n=== running it twice does not double anything up ===")
before = len(R.sources_for(CFG, WS, MKT, "9.99_3Days_B0AAAAAAAA"))
B.apply_rows(CFG, WS, MKT, ["sku", "url"],
             [["9.99_3Days_B0AAAAAAAA", "https://www.ebay.co.uk/itm/222222222222"]])
check("no new supplier", len(R.sources_for(CFG, WS, MKT, "9.99_3Days_B0AAAAAAAA")), before)

print("\n=== a sheet with no usable columns says which is missing ===")
out = B.apply_rows(CFG, WS, MKT, ["name", "price"], [["a", "1"]])
check("refused", out["ok"], False)
truthy("  naming the link column", "link" in out.get("error", ""))
out = B.apply_rows(CFG, WS, MKT, ["url"], [["https://www.ebay.co.uk/itm/1"]])
check("refused without a key", out["ok"], False)
truthy("  naming SKU or ASIN", "SKU" in out.get("error", ""))

print("\n=== nothing here arms anything ===")
# Tracking is not pricing. A SKU added by sheet is in dry run like any other.
check("everything it enrolled is in dry run",
      sorted({r["mode"] for r in R.enrolled(CFG, WS, MKT)}), ["dry_run"])

print("\n=== the glance figures ===")
from domain import source_drift as D
pairs = [({"id": 1, "enabled": 1},
          {"status": "fetched", "price": 10.79, "shipping": 0.49, "in_stock": True,
           "dispatch_days": 2, "available_qty": 93,
           "checked_at": "2026-08-17 10:00:00"})]
g = D.at_a_glance(pairs, {"price": 16.99}, {})
check("what a unit costs delivered", g["landed"], 11.28)
check("what Amazon charges today", g["sell_price"], 16.99)
# THIS TEST USED TO ASSERT THE PROFIT WAS NEGATIVE, AND IT WAS WRONG.
#
# 16.99 sold, 11.28 to buy, 2.55 to Amazon: the sale makes 3.16. It reported
# -1.84 because a 3.00 postage allowance and a 2.00 ads allowance were being
# subtracted from every figure whether or not that money had ever moved -- the
# same fault the owner found on a real order:
#
#     "the profit in the orders page is shown as 2.58 ... but when i click on
#      the order to see the breakdown it shows source price is 8.79 profit is
#      -2.32 and roi is -26%"
#
# Both allowances default to 0.00 now, so this is the arithmetic he asked for:
# what the buyer paid, less what the stock cost, less what Amazon actually took.
check("the profit on that sale is what is left after Amazon and the stock",
      g["profit"], 3.16)
truthy("  and it is a profit, not the loss the padding used to report",
       g["profit"] > 0)
check("  margin is that over what the buyer paid", g["margin_pct"], 18.6)
check("  and ROI is it over what you paid", g["roi_pct"], 28.0)
check("how many the supplier has", g["units_available"], 93)
check("the supplier's dispatch time", g["dispatch_days"], 2)
# A 2-day supplier and a 2-day postage service: max(0, 2 - 2) = 0 days of
# handling, which means "posted the same day". The buyer is still promised 2
# days, because Amazon adds the postage transit on top of the handling time.
check("  less the postage, which Amazon promises separately",
      g["handling_days"], 0)

print("  -- unknown stays unknown --")
g2 = D.at_a_glance([], {"price": 16.99}, {})
check("no reading -> no cost", g2["landed"], None)
check("  and no margin invented", g2["margin_pct"], None)
g3 = D.at_a_glance(pairs, {}, {})
check("no Amazon price -> no margin", g3["margin_pct"], None)
check("  but the supplier facts still show", g3["units_available"], 93)

try:
    conn.close()
except Exception:
    pass
os.environ.pop("ALTASCRAPER_DB", None)
import shutil
shutil.rmtree(TMP, ignore_errors=True)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
