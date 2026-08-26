"""Tracking a SKU's true cost should not mean typing its supplier link in again.

"i want to enroll all my items to the repricer so i want to make sure it is
 working right so for now give me option to turn on or off the auto pricing set,
 but uploading or selecting the skus in the repricer means to track their true
 costs from the sources"

Two things in that. TRACKING IS NOT PRICING -- enrolling a SKU starts a cost
history and nothing else, which is why it is safe to enroll the whole catalogue.
And the supplier link should not have to be supplied: the app BUILT these
listings from a source and wrote it down at the time. It is just written in two
places, so both are asked.

The case that matters most is the one that looks like a link and is not: a SKU
whose recorded source is an amazon.co.uk/dp/... page. That is the COMPETITOR the
listing was modelled on, never where the stock is bought (CLAUDE.md Rule 1).
Attaching it as a supplier would produce a source that answers "could not tell"
on every sweep for ever, and the repricer would correctly do nothing, silently.
"""
import json, os, sys, tempfile

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-66s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)

TMP = tempfile.mkdtemp(prefix="altalink_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG, "w"))
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "l.db")

from data import db as _db
from domain import source_link as L

conn = _db.get_db(CFG)


print("=== what counts as a supplier link ===")
check("an eBay item link is one", L.classify("https://www.ebay.co.uk/itm/1234567890")[0], "ebay")
check("  http and no www is still one", L.classify("http://ebay.co.uk/itm/163818606052")[0], "ebay")
check("a plain shop page is readable by the scraper",
      L.classify("https://somesupplier.co.uk/product/42")[0], "html")
# The one that matters.
check("an Amazon product page is NOT a supplier",
      L.classify("https://www.amazon.co.uk/dp/B0F2HDJ8RP")[0], "")
truthy("  and it says why, in the owner's own terms",
       "competitor" in L.classify("https://www.amazon.co.uk/dp/B0F2HDJ8RP")[1])
check("an eBay link with no item number cannot be priced from",
      L.classify("https://www.ebay.co.uk/sch/i.html?_nkw=grease+gun")[0], "")
check("nothing at all", L.classify("")[0], "")
check("  and text that is not a url", L.classify("ask dave")[0], "")


print("\n=== where it looks, and in what order ===")
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, source_url) "
             "VALUES (?,?,?,?)",
             ("ws", "9.99_3Days_B0AAAAAAAA", "B0AAAAAAAA",
              "https://www.ebay.co.uk/itm/111111111111"))
# The SAME product, a different SKU: the generator re-created the row.
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, source_url) "
             "VALUES (?,?,?,?)",
             ("ws", "9.99_3Days_B0BBBBBBBB", "B0BBBBBBBB",
              "https://www.ebay.co.uk/itm/222222222222"))
# A listing whose recorded source is the COMPETITOR page, with the real supplier
# sitting in the import queue -- the exact shape seen on the live account.
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, source_url) "
             "VALUES (?,?,?,?)",
             ("ws", "7.59_2Days_B0CCCCCCCC", "B0CCCCCCCC",
              "https://www.amazon.co.uk/dp/B0CCCCCCCC/?ref=x"))
conn.execute("INSERT INTO input_products (workspace_id, competitor_asin, amazon_url, ebay_url) "
             "VALUES ('ws', ?, ?, ?)",
             ("B0CCCCCCCC", "https://www.amazon.co.uk/dp/B0CCCCCCCC",
              "https://www.ebay.co.uk/itm/333333333333"))
# The SAME competitor ASIN in another account, with a different supplier. An
# unscoped lookup would hand one account the other's supplier and price from it.
conn.execute("INSERT INTO input_products (workspace_id, competitor_asin, amazon_url, ebay_url) "
             "VALUES ('rival', ?, ?, ?)",
             ("B0EEEEEEEE", "https://www.amazon.co.uk/dp/B0EEEEEEEE",
              "https://www.ebay.co.uk/itm/999999999999"))
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, source_url) "
             "VALUES (?,?,?,?)",
             ("ws", "5.00_2Days_B0EEEEEEEE", "B0EEEEEEEE",
              "https://www.amazon.co.uk/dp/B0EEEEEEEE"))
conn.commit()

r = L.for_sku(CFG, "ws", "9.99_3Days_B0AAAAAAAA")
check("the listing's own record is used first", r["url"], "https://www.ebay.co.uk/itm/111111111111")
check("  and said so", r["where"], "the listing's own record")

r = L.for_sku(CFG, "ws", "7.59_2Days_B0CCCCCCCC")
check("an Amazon source falls through to the import queue",
      r["url"], "https://www.ebay.co.uk/itm/333333333333")
check("  and says where it ended up", r["where"], "the import queue")

# A SKU with no row of its own, but the same competitor ASIN as one that has.
r = L.for_sku(CFG, "ws", "12.00_2Days_B0BBBBBBBB")
check("a re-created SKU finds the product's other listing",
      r["url"], "https://www.ebay.co.uk/itm/222222222222")
check("  and says it came from elsewhere", r["where"], "another listing for the same product")

r = L.for_sku(CFG, "ws", "46 pcs wrench")
check("a hand-made SKU has nothing to find", r["url"], "")
truthy("  and says so plainly", "no source link was recorded" in r["why"])

r = L.for_sku(CFG, "other-account", "9.99_3Days_B0AAAAAAAA")
check("one account's listings are not another's", r["url"], "")
# The import queue is keyed by competitor ASIN, and two accounts can watch the
# same competitor with different suppliers. This is the leak that would price
# one account's listing from the other's supplier, silently and for ever.
r = L.for_sku(CFG, "ws", "5.00_2Days_B0EEEEEEEE")
check("nor is one account's import queue", r["url"], "")


print("\n=== the reason is said once, not once per place it was tried ===")
conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, source_url) "
             "VALUES (?,?,?,?)",
             ("ws", "8.89_3Days_B0DDDDDDDD", "B0DDDDDDDD",
              "https://www.ebay.co.uk/sch/i.html?_nkw=thing"))
conn.execute("INSERT INTO input_products (workspace_id, competitor_asin, amazon_url, ebay_url) "
             "VALUES ('ws', ?, ?, ?)",
             ("B0DDDDDDDD", "https://www.amazon.co.uk/dp/B0DDDDDDDD",
              "https://www.ebay.co.uk/sch/i.html?_nkw=thing"))
conn.commit()
r = L.for_sku(CFG, "ws", "8.89_3Days_B0DDDDDDDD")
check("still no usable link", r["url"], "")
check("  and the same complaint is not repeated", r["why"].count("no item number"), 1)


print("\n=== Rule 1: the ASIN in a SKU is the COMPETITOR's ===")
# It is used to look a row up and for nothing else. Worth asserting, because a
# helper that resolves an ASIN from a SKU is exactly the shape of thing that
# gets reused later for the wrong purpose.
src = open(r"D:\AltaScraper\domain\source_link.py", encoding="utf-8").read()
truthy("the file says so where it does it", "COMPETITOR" in src and "Rule 1" in src)
truthy("nothing here writes anything", "INSERT" not in src.upper().replace("INSERT QUEUE", ""))

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
