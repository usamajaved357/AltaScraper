"""A period with nothing in it must SAY so. Silence reads as a fault.

THE REPORT: "the sales report and p&l heatmap do not show data beyond 27th july
no matter if i select 30 day, 60d or 90d", and then, once the cause was known:
"when no data is available its okay but the user should be able to see that
there is no data available or should be seen as zero".

WHAT WAS ACTUALLY WRONG, in three parts.

1. A ROW IS NOT EVIDENCE. live_reconcile.from_lines() writes one sales_daily row
   per day across whatever window it is given. A single year-to-date view
   therefore created a row for every day back to January -- all empty. Nothing
   was fetched for those days; nothing was known about them.

2. AVAILABILITY COUNTED THOSE ROWS. _refresh_availability took MIN(date) over
   the table, so it reported these accounts as having data from 19 May 2025.

3. SO THE SCREEN BELIEVED IT. Asking for 90 days drew ninety columns of blanks
   rather than saying there was nothing there -- and 30, 60 and 90 days all
   showed the same figures with no explanation of why.

Checked against Amazon: it returns a genuine zero for nestwell_goods on
10 July 2026, so the account really was not selling. The data is not missing.
The app was simply never saying so.

A fourth thing, found while fixing it: the report was only ever chased 30 days
back, so a longer period could not fill in even for an account that HAS older
history. That is now bounded by trade instead -- see first_trade().
"""
import os, sys, json, tempfile, shutil
import datetime as dt

sys.path.insert(0, r"D:\AltaScraper")

from data import db as _db
from domain import sales_data as _sd
from domain import sales_fetch as _sf

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-64s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def check_true(label, got):
    check(label, bool(got), True)


TMP = tempfile.mkdtemp(prefix="altaempty_")
CFG = os.path.join(TMP, "config.json")
json.dump({"accounts": [{"id": "acct", "marketplaces": ["UK"],
                         "default_marketplace": "UK"}]}, open(CFG, "w"))
WS, MKT = "acct", "UK"
conn = _db.get_db(CFG)

TODAY = dt.date.today()
D = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()


def day(date, sales=0.0, orders=0, units=0, sessions=0, source=None):
    conn.execute(
        "INSERT INTO sales_daily (workspace_id, marketplace, date, asin, orders,"
        " units, ordered_sales, sessions, currency, orders_source) "
        "VALUES (?,?,?,'*',?,?,?,?,'GBP',?)",
        (WS, MKT, date, orders, units, sales, sessions, source))


print("\n== an empty placeholder row does not count as data ==")
# Five real trading days, and a long run of empty rows before them of exactly
# the kind from_lines used to write.
for n in range(400, 380, -1):
    day(D(n), source="orders_api")            # empty, written by the order feed
day(D(10), sales=100.0, orders=2, units=2, sessions=40)
day(D(9), sales=0.0, orders=0, units=0, sessions=12)   # a genuinely quiet day
day(D(8), sales=250.0, orders=5, units=6, sessions=90)
conn.commit()

_sd._refresh_availability(conn, WS, MKT, "sales")
av = _sd.availability(CFG, WS, MKT)["sales"]
check("availability starts at the first day that carries anything",
      av["first_date"], D(10))
check("  not at the first empty row", av["first_date"] == D(400), False)
check("and ends at the last", av["last_date"], D(8))
# A quiet day BETWEEN trading days is real data and must still be counted --
# otherwise a slow Tuesday would look like a gap in coverage.
check("a quiet day inside the trading period still counts", av["days"], 3)

print("\n== with nothing at all, it still answers ==")
TMP2 = tempfile.mkdtemp(prefix="altaempty2_")
CFG2 = os.path.join(TMP2, "config.json")
json.dump({"accounts": []}, open(CFG2, "w"))
c2 = _db.get_db(CFG2)
c2.execute("INSERT INTO sales_daily (workspace_id, marketplace, date, asin,"
           " orders, units, ordered_sales, currency) VALUES "
           "('w','UK','2026-08-01','*',0,0,0,'GBP')")
c2.commit()
_sd._refresh_availability(c2, "w", "UK", "sales")
a2 = _sd.availability(CFG2, "w", "UK")["sales"]
check("a single quiet day is reported rather than nothing", a2["first_date"],
      "2026-08-01")
check("  and counts as no days of real data", a2["days"], 0)
shutil.rmtree(TMP2, ignore_errors=True)

print("\n== the backfill is bounded by trade, not by a flat number of days ==")
check("a marketplace that never traded has no first trade",
      _sf.first_trade(CFG, WS, MKT), None)
conn.execute(
    "INSERT INTO order_lines (workspace_id, marketplace, order_id, purchase_date,"
    " asin, sku, units, revenue, status) VALUES (?,?,?,?,?,?,1,10.0,'Shipped')",
    (WS, MKT, "O-1", D(10) + "T10:00:00Z", "B0X", "SKU"))
conn.commit()
check("once it has, that is the floor", _sf.first_trade(CFG, WS, MKT), D(10))

# Ninety-five days back, but the account only started ten days ago -- so at most
# ten days are worth asking Amazon about, not ninety-five.
miss = _sf.missing_days(CFG, WS, MKT, 95)
check_true("nothing before the first order is chased",
           all(d >= D(10) for d in miss))
check_true("and the days it does chase are within the window",
           all(d <= _sf._s(_sf.yesterday()) for d in miss))
check("newest first, so an interrupted backfill keeps the useful end",
      miss == sorted(miss, reverse=True), True)

# A pair that has NEVER traded must keep the short window. Without this it would
# inherit the long one, and eleven European marketplaces per account would each
# ask for three months of report about a country with no customers.
untraded = _sf.missing_days(CFG, "acct", "PL", 95)
check_true("a marketplace with no orders is capped at the short window",
           len(untraded) <= _sf.UNTRADED_DAYS_BACK)
check_true("  and that cap is genuinely shorter than the long one",
           _sf.UNTRADED_DAYS_BACK < 95)

print("\n== and the screen says it, rather than drawing blanks ==")
js = open(r"D:\AltaScraper\static\js\sales.js", encoding="utf-8").read()
check_true("the screen keeps what is available, so any part can say so",
           "SALES.avail = av" in js)
check_true("the range line says where the data starts",
           "trading from " in js)
check_true("and the grid says it where the empty columns are",
           "gnodata" in js)
check_true("  naming the date it starts", "Trading from" in js)
# SHORT ON THE PAGE, FULL ON THE HOVER. "i think the note in english wont be so
# good", and then, of Orbit's own screen: "i think this is the right way to
# write notices" -- a short label, an i, and the explanation only if you ask.
# So the sentence still exists; it lives in a title= attribute, not in the page.
_after = js.split('class="gcogs gnodata"')[1][:600]
check_true("  and the explanation is on a hover, not printed on the page",
           'class="infodot" title=' in _after)
check_true("  with the sentence inside it",
           "This account has nothing before" in _after)
css = open(r"D:\AltaScraper\static\css\dashboard.css", encoding="utf-8").read()
check_true("the note has a style of its own", ".gnodata" in css)

print("\n== a day that took no orders shows 0, not a dash ==")
# "the zeros written also indicates no sales was made so it is right thing."
# An em-dash means "not known"; for what was ORDERED, absence IS the answer.
check_true("the rows where absence means zero are named",
           'const ORDERED = ["ordered_sales", "orders", "units", "order_items"]' in js)
check_true("  and a blank in one of them is drawn as zero",
           "zeroable(m.key, i)) ? 0 : v" in js)
check_true("  with the cell saying why on hover",
           "no orders that day" in js)
# ONLY inside the period Amazon has reported on. Outside it nothing has been
# checked, and a zero there would be the app asserting what it has not looked
# at -- which is exactly what put fifteen months of invented zeros in the store.
check_true("  and only where Amazon has actually reported",
           "d >= knownFrom && d <= knownTo" in js)
# The fee and traffic rows must NOT be zeroed: Amazon settles days later, so a
# blank there genuinely means "not told yet" and a zero would be a lie.
for k in ("referral_fees", "principal", "sessions", "profit"):
    check("%s is left as unknown, not zeroed" % k,
          ('"%s"' % k) in js.split("const ORDERED =")[1].split("]")[0], False)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
