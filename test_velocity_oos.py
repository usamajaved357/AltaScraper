"""A day the shelf was empty is not a day nobody wanted it.

    "Counting it as a zero-sales day understates true demand"
        -- the question put to Orbit's inventory agent, and its answer:
    "OOS days are excluded from the OOS-adjusted pace calculation -- that is the
     adjustment. We do not count an out-of-stock day as a zero-sales day, so it
     does not understate true demand."

THIS APP DID COUNT THEM. velocity_map divided units by the whole window, so a
product out of stock for twenty of thirty days reported a THIRD of its real
rate -- and that rate is what days-of-cover and the reorder quantity are built
on. The app was therefore under-ordering exactly the products that keep running
out, and under-ordering them more the worse the stockout was.

WHY IT CAN BE FIXED NOW. stock_daily records qty per SKU per day, so the days a
SKU was sellable can be COUNTED rather than assumed. It began recording on
20 Aug 2026, which is the whole reason for the first rule below.

TWO RULES KEEP IT HONEST, and both are the mirror of the bug being fixed:

  MIN_OBSERVED_DAYS   Below this much recorded history no adjustment is made at
                      all. A thin denominator would INFLATE the rate, which is
                      the same fault the other way round.

  the same days on    When the adjustment IS made, the units counted are only
  both sides          those sold on days that were both recorded AND in stock.
                      Dividing thirty days of sales by ten in-stock days would
                      treble the answer. Numerator and denominator must describe
                      the same days or the figure means nothing.

And which basis was used is returned and shown, never hidden: a reorder built on
"2 a day while it was on the shelf" is not the same promise as one built on
"0.67 a day counting the three weeks it was unbuyable".
"""
import datetime as _dt
import io
import json
import os
import shutil
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
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


from data import db as _db
from domain import inventory_view as IV

print("== the rules are stated in the code ==")
SRC = read("domain", "inventory_view.py")
truthy("there is a minimum history", "MIN_OBSERVED_DAYS" in SRC)
truthy("  and it is at least a week", IV.MIN_OBSERVED_DAYS >= 7)
truthy("the basis is returned, not hidden", '"velocity_basis"' in SRC)
truthy("  and reaches the row", '"velocity_basis": v.get("velocity_basis")' in SRC)
truthy("the screen shows which rate it is",
       'r.velocity_basis === "in-stock days"' in read("static", "js", "stock.js"))
truthy("  and says what was left out",
       "out of stock on" in read("static", "js", "stock.js"))

print("\n== built to test it: one SKU out of stock for 21 of 31 days ==")
tmp = tempfile.mkdtemp()
try:
    cfg = os.path.join(tmp, "config.json")
    io.open(cfg, "w", encoding="utf-8").write(json.dumps({"accounts": []}))
    conn = _db.get_db(cfg)
    today = _dt.date(2026, 8, 31)
    start = today - _dt.timedelta(days=30)
    conn.execute("CREATE TABLE IF NOT EXISTS order_lines (workspace_id TEXT, "
                 "marketplace TEXT, order_id TEXT, sku TEXT, units INT, "
                 "status TEXT, purchase_date TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS stock_daily (workspace_id TEXT, "
                 "marketplace TEXT, date TEXT, sku TEXT, asin TEXT, qty INT, "
                 "status TEXT, fulfillment TEXT, recorded_at TEXT)")
    OL = ("INSERT INTO order_lines (workspace_id,marketplace,order_id,sku,units,"
          "status,purchase_date) VALUES (?,?,?,?,?,?,?)")
    SD = ("INSERT INTO stock_daily (workspace_id,marketplace,date,sku,asin,qty,"
          "status,fulfillment,recorded_at) VALUES (?,?,?,?,?,?,?,?,?)")
    n = 0
    for i in range(31):
        d = (start + _dt.timedelta(days=i)).isoformat()
        instock = i >= 21                     # on sale for the last 10 days only
        conn.execute(SD, ("w", "UK", d, "A", "ASINA", 5 if instock else 0,
                          "Active", "DEFAULT", d))
        if instock:
            n += 1
            conn.execute(OL, ("w", "UK", "o%d" % n, "A", 2, "Shipped", d))
        conn.execute(SD, ("w", "UK", d, "B", "ASINB", 9, "Active", "DEFAULT", d))
        conn.execute(OL, ("w", "UK", "p%d" % i, "B", 1, "Shipped", d))
    conn.commit()

    v = IV.velocity_map(cfg, "w", "UK", 30, today)
    check("the stocked-out SKU sold 20 units", v["A"]["units"], 20)
    check("  over 10 days it was actually on sale", v["A"]["in_stock_days"], 10)
    check("  and was out on the other 21", v["A"]["oos_days"], 21)
    check("  so its rate is 2 a day", v["A"]["velocity"], 2.0)
    check("  on the in-stock basis", v["A"]["velocity_basis"], "in-stock days")
    print("     (the old answer was %.2f -- a third of the truth)" % (20 / 30.0))
    check("a SKU in stock all month is unchanged at 1 a day",
          v["B"]["velocity"], 1.0)
    check("  with no out-of-stock days", v["B"]["oos_days"], 0)

    print("\n== the numerator and the denominator describe the same days ==")
    # Sales BEFORE the stock record starts must not be divided by in-stock days.
    conn.execute("DELETE FROM stock_daily WHERE date < ?",
                 ((today - _dt.timedelta(days=9)).isoformat(),))
    conn.commit()
    v4 = IV.velocity_map(cfg, "w", "UK", 30, today)
    # 10 days of records, all in stock for A; A sold 2/day on each of them.
    check("only the recorded, in-stock days count", v4["A"]["in_stock_days"], 10)
    check("  and the rate stays 2 a day, not 20 units over 10 days of a "
          "30-day window", v4["A"]["velocity"], 2.0)
    check("  B likewise", v4["B"]["velocity"], 1.0)

    print("\n== too little history makes NO adjustment ==")
    conn.execute("DELETE FROM stock_daily WHERE date < ?",
                 ((today - _dt.timedelta(days=2)).isoformat(),))
    conn.commit()
    v2 = IV.velocity_map(cfg, "w", "UK", 30, today)
    check("3 days is not enough", v2["A"]["velocity_basis"], "window")
    check("  so the window rate stands", round(v2["A"]["velocity"], 4),
          round(20 / 30.0, 4))
    check("  and the row says how much history there was",
          v2["A"]["observed_days"], 3)

    print("\n== out of stock on EVERY recorded day keeps the window rate ==")
    # There is no in-stock day to divide by, and reporting no velocity would
    # read as "nobody wants it" -- the very mistake this exists to stop.
    conn.execute("DELETE FROM stock_daily")
    for i in range(31):
        d = (start + _dt.timedelta(days=i)).isoformat()
        conn.execute(SD, ("w", "UK", d, "A", "ASINA", 0, "Inactive", "DEFAULT", d))
    conn.commit()
    v3 = IV.velocity_map(cfg, "w", "UK", 30, today)
    check("it falls back rather than reporting nothing",
          v3["A"]["velocity_basis"], "window")
    check("  with a real rate", round(v3["A"]["velocity"], 4), round(20 / 30.0, 4))
    check("  and 0 in-stock days recorded", v3["A"]["in_stock_days"], 0)

    print("\n== no stock table at all is not an error ==")
    conn.execute("DROP TABLE stock_daily")
    conn.commit()
    v5 = IV.velocity_map(cfg, "w", "UK", 30, today)
    check("every SKU still gets a rate", sorted(v5), ["A", "B"])
    check("  on the window basis", v5["A"]["velocity_basis"], "window")
except Exception as e:
    fails.append("the built fixture")
    print("  FAIL:", str(e)[:300])
finally:
    try:
        _db.get_db(cfg).close()
    except Exception:
        pass
    shutil.rmtree(tmp, ignore_errors=True)

print("\n== and against the real database, whatever it holds today ==")
try:
    conn = _db.get_db()
    have = conn.execute("SELECT COUNT(DISTINCT date) d, MIN(date) a, MAX(date) b "
                        "FROM stock_daily").fetchone()
    print("     stock_daily holds %s day(s): %s to %s"
          % (have["d"], have["a"], have["b"]))
    from domain import inventory_view as _iv
    for ws, mkt in [("jack_uk", "UK"), ("nestwell_goods", "UK")]:
        v = _iv.velocity_map("config.json", ws, mkt, 30)
        bases = {}
        for r in v.values():
            bases[r["velocity_basis"]] = bases.get(r["velocity_basis"], 0) + 1
        print("     %-18s %d SKUs, bases: %s" % (ws, len(v), bases))
        # Whatever the basis, a velocity must never be negative or absurd.
        bad = [k for k, r in v.items()
               if r["velocity"] is not None and r["velocity"] < 0]
        check("  %s has no negative velocity" % ws, bad, [])
    if (have["d"] or 0) < _iv.MIN_OBSERVED_DAYS:
        print("     (fewer than %d days recorded, so nothing is adjusted YET --"
              " that is the rule working, not a failure)" % _iv.MIN_OBSERVED_DAYS)
except Exception as e:
    print("  (could not reach the database: %s)" % str(e)[:120])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
