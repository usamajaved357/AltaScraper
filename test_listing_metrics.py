"""The numbers beside a listing: where they come from, and what they refuse to say.

WHAT THIS PINS

domain/listing_metrics.py joins three local tables to answer "what has this
listing done". Every way it can go wrong is silent:

  * THE ASIN TRAP. A SKU is price_days_ASIN and that ASIN is the COMPETITOR's
    (CLAUDE.md Rule 1). sales_daily is keyed by OUR asin. Joining on the SKU's
    embedded code attributes a competitor's sales to our listing -- and on the
    real database it matches nothing at all, so the bug would look like "no
    data" rather than like an error.
  * '*' IS THE WHOLE ACCOUNT. sales_daily stores the account-wide daily total
    under asin '*'. Counting it as a product would report every sale the
    business made against one listing.
  * NULL IS NOT ZERO. Amazon reports traffic on only some days (359 of 1079
    rows carry sessions). "Sold nothing" and "not reported" must stay
    distinguishable all the way to the screen, or the dash the view draws is a
    lie.
  * A CACHED BLANK IS FOREVER. data/metrics_cache must never store an empty
    answer: once written it is indistinguishable from "Amazon says there is
    none", and this account's SP-API roles have been partial before.

Everything runs against a temporary database built here, so it tests the SQL
rather than whatever happens to be in the real one.
"""
import os
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL\n      got  %r\n      want %r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altametrics_")
DB = os.path.join(TMP, "altascraper.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write("{}")

# Point the shared db module at the temporary file.
from data import db as _db          # noqa: E402
_db.close_db()
_real_path = _db.db_path
_db.db_path = lambda config_path=None: DB

# Built through the APP'S OWN SCHEMA, not a hand-written copy of it. A local
# CREATE TABLE would drift from data/db.py and the test would go on passing
# against a shape production no longer has -- and it hid a real constraint the
# first time: sales_daily is UNIQUE on (workspace, marketplace, date, asin), so
# a listing's two days below have to be two dates, which is also what the real
# table holds.
conn = _db.get_db(CFG)

TODAY = time.strftime("%Y-%m-%d")
YESTERDAY = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))

# OUR sku carries the COMPETITOR's asin in its name; our own asin is different.
SKU = "9.18_3Days_B0COMPETITOR"
OURS = "B0OURSXXXXX"


def _ins(sql, rows):
    with conn:
        conn.executemany(sql, rows)


_ins("INSERT INTO stock_daily (workspace_id, marketplace, date, sku, asin, qty,"
     " status, fulfillment) VALUES (?,?,?,?,?,?,?,?)", [
         ("ws", "UK", "2026-08-01", SKU, OURS, 9, "Active", "DEFAULT"),
         ("ws", "UK", TODAY,        SKU, OURS, 4, "Active", "DEFAULT"),
         ("ws", "UK", TODAY, "FBA_SKU", "B0FBA000001", 7, "Active", "AMAZON"),
     ])
_ins("INSERT INTO sales_daily (workspace_id, marketplace, date, asin, units,"
     " ordered_sales, sessions, page_views, buy_box_pct) VALUES (?,?,?,?,?,?,?,?,?)", [
         # our listing, two days -- one with traffic reported, one without
         ("ws", "UK", TODAY,     OURS, 3, 89.97, 69, 124, 52.73),
         ("ws", "UK", YESTERDAY, OURS, 1, 24.99, None, None, None),
         # the account-wide total, which must never be read as a product
         ("ws", "UK", TODAY, "*", 999, 99999.0, 5000, 9000, 100.0),
         # the COMPETITOR's asin, which must never be attributed to us
         ("ws", "UK", TODAY, "B0COMPETITOR", 500, 5000.0, 400, 800, 90.0),
     ])
_ins("INSERT INTO order_lines (workspace_id, marketplace, order_id, purchase_date,"
     " sku, asin, units, revenue) VALUES (?,?,?,?,?,?,?,?)", [
         ("ws", "UK", "206-0000001-0000001", TODAY, "ORDERS_ONLY_SKU", "", 2, 40.0),
     ])

from domain import listing_metrics as LM        # noqa: E402
from data import metrics_cache as MC            # noqa: E402

# ---------------------------------------------------------------------------
print("\nthe SKU's embedded ASIN is the COMPETITOR's, and is never used")
# ---------------------------------------------------------------------------
m = LM.for_skus(CFG, "ws", "UK", [SKU])
row = m[SKU]
check("our own asin comes from stock_daily", row.get("asin"), OURS)
check("  not the one in the SKU", row.get("asin") == "B0COMPETITOR", False)
check("the competitor's 500 units are NOT ours", row.get("units"), 4)
check("nor its GBP 5000", round(row.get("sales") or 0, 2), 114.96)

print("\n  ...and the account-wide '*' total is not a product")
check("999 units did not land on this listing", row.get("units") == 999, False)
check("the totals are this listing's own two days", row.get("units"), 3 + 1)

# ---------------------------------------------------------------------------
print("\nnull is not zero, all the way through")
# ---------------------------------------------------------------------------
check("traffic sums only the days Amazon reported", row.get("views"), 124)
check("  and sessions likewise", row.get("sessions"), 69)
_none = LM.for_skus(CFG, "ws", "UK", ["FBA_SKU"])["FBA_SKU"]
check("a listing with no sales rows has NO units field at all",
      "units" in _none, False)
check("  not units=0, which would read as 'sold nothing'", _none.get("units"), None)
truthy("but its stock IS known", _none.get("on_hand") == 7)

# ---------------------------------------------------------------------------
print("\navailable is only filled where it is actually knowable")
# ---------------------------------------------------------------------------
check("merchant-fulfilled: on-hand IS available", row.get("available"), 4)
check("FBA: available is NOT assumed from on-hand", "available" in _none, False)
truthy("  because reserved stock is only in the FBA API, and that is cached "
       "separately", _none.get("fulfillment") == "AMAZON")

# ---------------------------------------------------------------------------
print("\nthe newest stock reading wins")
# ---------------------------------------------------------------------------
check("today's 4, not August's 9", row.get("on_hand"), 4)
check("and it says when it was counted", row.get("stock_as_of"), TODAY)

# ---------------------------------------------------------------------------
print("\norder lines fill the gap when there is no own-ASIN yet")
# ---------------------------------------------------------------------------
oo = LM.for_skus(CFG, "ws", "UK", ["ORDERS_ONLY_SKU"])["ORDERS_ONLY_SKU"]
check("units come from the order lines", oo.get("units"), 2)
check("  and say so", oo.get("units_source"), "order_lines")
check("where Amazon's own report exists, IT wins", row.get("units_source"),
      "amazon_report")

# ---------------------------------------------------------------------------
print("\nit answers for every SKU asked about, and invents nothing")
# ---------------------------------------------------------------------------
many = LM.for_skus(CFG, "ws", "UK", [SKU, "FBA_SKU", "NEVER_SEEN"])
check("one entry per SKU", sorted(many.keys()), sorted(["FBA_SKU", "NEVER_SEEN", SKU]))
check("an unknown SKU carries no figures",
      [k for k in many["NEVER_SEEN"] if k != "days"], [])
check("no SKUs asked -> nothing back", LM.for_skus(CFG, "ws", "UK", []), {})
check("a wrong workspace yields no figures",
      [k for k in LM.for_skus(CFG, "other", "UK", [SKU])[SKU] if k != "days"], [])
check("a wrong marketplace likewise",
      [k for k in LM.for_skus(CFG, "ws", "US", [SKU])[SKU] if k != "days"], [])

# ---------------------------------------------------------------------------
print("\ncoverage reports what the window really had")
# ---------------------------------------------------------------------------
cov = LM.coverage(CFG, "ws", "UK")
check("two days of sales exist", cov["sales_days"], 2)
check("  against a 30 day window", cov["days"], 30)
truthy("and the last stock date is named", cov["stock_last"] == TODAY)

# ---------------------------------------------------------------------------
print("\nthe cache never stores a blank as if it were an answer")
# ---------------------------------------------------------------------------
check("an empty dict is refused", MC.put(CFG, "ws", "UK", SKU, "rank", {}), False)
check("None is refused",          MC.put(CFG, "ws", "UK", SKU, "rank", None), False)
check("a non-dict is refused",    MC.put(CFG, "ws", "UK", SKU, "rank", "12"), False)
truthy("a real answer is kept",   MC.put(CFG, "ws", "UK", SKU, "rank",
                                         {"rank": 24810, "category": "Garden"}))
got = MC.get(CFG, "ws", "UK", [SKU])
check("and comes back", got[SKU]["rank"]["data"]["rank"], 24810)
check("  fresh",        got[SKU]["rank"]["stale"], False)

print("\n  ...and the two TTLs are the two different questions")
check("a price goes stale in 4 hours",  MC.TTL["pricing"], 4 * 3600)
check("FBA stock likewise",             MC.TTL["fba"], 4 * 3600)
check("a sales rank lasts a day",       MC.TTL["rank"], 24 * 3600)
_old = time.time() - 5 * 3600
MC.put(CFG, "ws", "UK", SKU, "pricing", {"buy_box_price": 9.99}, now=_old)
MC.put(CFG, "ws", "UK", SKU, "rank", {"rank": 1}, now=_old)
g2 = MC.get(CFG, "ws", "UK", [SKU])
check("after 5 hours the price is stale", g2[SKU]["pricing"]["stale"], True)
check("  but the rank is not",            g2[SKU]["rank"]["stale"], False)
check("a stale row is still RETURNED, marked -- not thrown away",
      g2[SKU]["pricing"]["data"]["buy_box_price"], 9.99)
check("stale_skus names only what needs fetching",
      MC.stale_skus(CFG, "ws", "UK", [SKU], "pricing"), [SKU])
check("  and not what is fresh", MC.stale_skus(CFG, "ws", "UK", [SKU], "rank"), [])
check("a SKU never cached needs fetching",
      MC.stale_skus(CFG, "ws", "UK", ["NEW_SKU"], "rank"), ["NEW_SKU"])

print("\n  ...the freshness line is read off what was stored")
truthy("newest() finds the most recent write",
       abs(MC.newest(CFG, "ws", "UK", [SKU]) - _old) < 2)
check("forget() clears it", MC.forget(CFG, "ws", "UK", [SKU]) >= 2, True)
check("  and then there is nothing", MC.get(CFG, "ws", "UK", [SKU]), {})
check("  so newest() is 0 again", MC.newest(CFG, "ws", "UK", [SKU]), 0.0)

# ---------------------------------------------------------------------------
print("\nnothing raises on a database that does not have the tables")
# ---------------------------------------------------------------------------
EMPTY = os.path.join(TMP, "empty.db")
sqlite3.connect(EMPTY).close()
_db.close_db()
_db.db_path = lambda config_path=None: EMPTY
try:
    check("for_skus survives", LM.for_skus(CFG, "ws", "UK", [SKU])[SKU], {"days": 30})
    check("coverage survives", LM.coverage(CFG, "ws", "UK")["sales_days"], 0)
    check("own_asins survives", LM.own_asins(CFG, "ws", "UK"), {})
except Exception as e:                                            # noqa: BLE001
    fails.append("raised on an empty database: %s" % e)
    print("  FAIL raised on an empty database:", e)

_db.close_db()
_db.db_path = _real_path

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
