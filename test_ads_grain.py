"""ads_daily holds two grains in one table. Everything here is about not adding them.

    asin = '*'      the day's account-wide total      <- from the campaign report
    asin = 'B0...'  that one product on that day      <- from the product report

Both are the SAME MONEY at different resolutions. Summing the table without
naming a grain returns exactly double, and nothing about the number looks wrong:
it is plausible, it moves the right way day to day, and it is twice the truth.
That is what these checks exist to catch.

Measured on nestwell_goods/UK 2026-08-08..09-04 before the fix: '*' rows 256.93,
per-ASIN rows 256.93, unfiltered SUM 513.86, campaign grain 256.93. All 28 of 28
days carried both grains.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

from data import db as _db              # noqa: E402
from domain import ads_sync as _as      # noqa: E402

fails = []
ran = []


def check(label, got, want):
    ran.append(label)
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


WS, MKT = "__ads_grain__", "UK"
conn = _db.get_db()
for t in ("ads_daily", "ads_campaign_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))

# Two days. Each has a '*' total row AND the per-ASIN breakdown of the same
# money -- which is exactly how the real table is shaped.
for date, total, parts in (("2026-08-01", 10.0, (6.0, 4.0)),
                           ("2026-08-02", 20.0, (12.0, 8.0))):
    conn.execute(
        "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
        "ad_sales, clicks, impressions, ad_orders, ad_product) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (WS, MKT, date, "*", total, total * 4, 10, 1000, 2, "SPONSORED_PRODUCTS"))
    for i, p in enumerate(parts):
        conn.execute(
            "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
            "ad_sales, clicks, impressions, ad_orders, ad_product) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (WS, MKT, date, "B00000000%d" % i, p, p * 4, 5, 500, 1,
             "SPONSORED_PRODUCTS"))
conn.commit()

print("\nthe shared reader names a grain")
t = _as.totals(None, WS, MKT, "2026-08-01", "2026-08-02")
# 30.00, not 60.00. The unfiltered sum of that fixture is 60.
check("spend is the account total, not the total plus its own breakdown",
      t["spend"], 30.0)
check("and sales the same way", t["sales"], 120.0)
check("it counts days, not rows", t["days"], 2)
raw = conn.execute("SELECT ROUND(SUM(spend),2) FROM ads_daily WHERE "
                   "workspace_id=? AND marketplace=?", (WS, MKT)).fetchone()[0]
check("an unfiltered SUM really is double — this is what was happening",
      raw, 60.0)

print("\nabsence is not zero")
none = _as.totals(None, "__nobody__", MKT, "2026-08-01", "2026-08-02")
check("an account with no advertising says so", none["has_data"], False)
# A P&L that reads 0.00 for spend cannot be told apart from one that read a real
# zero, and only one of those is safe to subtract from profit.
check("and reports spend as unknown rather than 0.00", none["spend"], None)
check("ACOS with no data is undefined", none["acos_pct"], None)

print("\nACOS and ROAS divide by different things, so they answer differently")
conn.execute("DELETE FROM ads_daily WHERE workspace_id=?", (WS,))
conn.execute(
    "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
    "ad_sales, ad_product) VALUES (?,?,?,?,?,?,?)",
    (WS, MKT, "2026-08-01", "*", 5.0, 0.0, "SPONSORED_PRODUCTS"))
conn.commit()
t2 = _as.totals(None, WS, MKT, "2026-08-01", "2026-08-01")
check("spend spent and nothing sold is still a real spend", t2["spend"], 5.0)
# ACOS is spend/SALES, so nought sales makes it undefined -- and printing 0%
# would read as "this advertising costs nothing", the exact opposite of a
# campaign that spent five pounds and sold nothing.
check("ACOS on no sales is undefined, not 0%", t2["acos_pct"], None)
# ROAS is sales/SPEND, and the denominator is real. Nought back on five pounds
# genuinely IS 0x -- a true and useful figure, not a division by zero. Making it
# None here would hide the worst result the screen can show.
check("ROAS on no sales is a real 0x, because the denominator is spend",
      t2["roas"], 0.0)

# The other half of the pair: sales UNKNOWN is not sales nil.
conn.execute("DELETE FROM ads_daily WHERE workspace_id=?", (WS,))
conn.execute(
    "INSERT INTO ads_daily (workspace_id, marketplace, date, asin, spend, "
    "ad_sales, ad_product) VALUES (?,?,?,?,?,?,?)",
    (WS, MKT, "2026-08-01", "*", 5.0, None, "SPONSORED_PRODUCTS"))
conn.commit()
t3 = _as.totals(None, WS, MKT, "2026-08-01", "2026-08-01")
check("sales Amazon never sent stay unknown", t3["sales"], None)
check("and ROAS on unknown sales is unknown, not 0x", t3["roas"], None)

print("\nno reader may sum the table without naming a grain")
# THE REGRESSION GUARD. Two files did exactly this and each reported double.
# Anything reading ads_daily has to say asin='*' or asin<>'*', or go through
# ads_sync.totals -- which is the point of it existing.
bad = []
for root, _dirs, files in os.walk(HERE):
    if any(p in root for p in (".git", "__pycache__", "worktrees", "node_modules")):
        continue
    for f in files:
        if not f.endswith(".py") or f.startswith("test_") or f.startswith("probe_"):
            continue
        p = os.path.join(root, f)
        try:
            s = open(p, encoding="utf-8").read()
        except Exception:
            continue
        # Each SELECT ... FROM ads_daily, up to the end of its statement.
        for m in re.finditer(r"FROM ads_daily(.{0,400}?)(?:\"\s*\)|\'\s*\)|;)",
                             s, re.S):
            frag = m.group(0)
            if "asin" in frag:
                continue          # names a grain, or selects per-asin explicitly
            if "SUM(" not in frag.upper():
                continue          # not aggregating, so the grain cannot double
            bad.append("%s: %s" % (os.path.relpath(p, HERE),
                                   " ".join(frag.split())[:90]))
for b in bad:
    print("      would double-count:", b)
check("nothing aggregates ads_daily without naming a grain", bad, [])

print("\none advertising profile is one marketplace")
SCH = open(os.path.join(HERE, "data", "scheduler.py"), encoding="utf-8").read()
i = SCH.find("def ads_sync(")
j = SCH.find("\ndef ", i + 10)
job = SCH[i:j]
# The loop is what filed one profile's figures under eleven marketplace names.
truthy("the ads job no longer loops the account's marketplaces",
       'for mkt in (a.get("marketplaces")' not in job)
truthy("it asks which marketplace the profile is actually for",
       "marketplace_for" in job)
truthy("and passes that one through to the report request",
       "request_reports(aid, mkt" in job)
truthy("marketplace_for exists and returns a reason with its answer",
       "def marketplace_for(" in open(os.path.join(HERE, "domain", "ads_sync.py"),
                                      encoding="utf-8").read())

print("\ndeleting stored figures is never a side effect")
AS = open(os.path.join(HERE, "domain", "ads_sync.py"), encoding="utf-8").read()
truthy("drop_marketplace is a dry run unless asked otherwise",
       "def drop_marketplace(config_path, workspace_id, marketplace, dry_run=True)"
       in AS)
truthy("and finding strays is a separate, read-only call",
       "def stray_marketplaces(" in AS)

for t in ("ads_daily", "ads_campaign_daily"):
    conn.execute("DELETE FROM %s WHERE workspace_id=?" % t, (WS,))
conn.commit()

print("\n%d checks, %d failed" % (len(ran), len(fails)))
if fails:
    print("FAILED:")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("all passed")
