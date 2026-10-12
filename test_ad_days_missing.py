"""A day the ad download missed is named, not counted as a day of no ads.

domain/ad_cost.by_day sums the Ads API's account rows day by day. A report that
failed or expired leaves no row for its day, and that day then added nothing to
the ad cost -- so profit rose by that day's spend with no word on any screen
(found 12 Oct 2026, nestwell_goods loss analysis). Now the gap is listed in the
note every profit screen shows. Days after the last stored day are NOT a gap:
they are simply not downloaded yet, and naming them would cry wolf every day.

Run against a throwaway database (ALTASCRAPER_DB), never the owner's own.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

TMP = tempfile.mkdtemp(prefix="addays_")
os.environ["ALTASCRAPER_DB"] = os.path.join(TMP, "t.db")
CFG = os.path.join(TMP, "config.json")
open(CFG, "w", encoding="utf-8").write('{"accounts": [{"id": "acct"}]}')

from data import db as _db                       # noqa: E402
from domain import ad_cost as _ac                # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


A, M = "acct", "UK"
conn = _db.get_db(CFG)
for day, spend in (("2026-08-01", 10.0), ("2026-08-02", 12.0),
                   ("2026-08-04", 9.0)):              # 3 Aug never downloaded
    conn.execute("INSERT INTO ads_daily (workspace_id, marketplace, date, asin, "
                 "spend, ad_sales, source) VALUES (?,?,?,?,?,?,?)",
                 (A, M, day, "*", spend, 0.0, "api"))
conn.commit()

print("== a gap between stored days is named ==")
w = _ac.for_window(CFG, A, M, "2026-08-01", "2026-08-06", True)
check("the cost is what was stored", w["cost"], 31.0)
check("the missing day is listed", w.get("missing_days"), ["2026-08-03"])
check("and the note says so", "2026-08-03" in (w.get("note") or ""), True)
check("  without naming the days not downloaded yet",
      "2026-08-05" in (w.get("note") or ""), False)

print("== a gap at the END of a window is still a gap when later days exist ==")
w3 = _ac.for_window(CFG, A, M, "2026-08-02", "2026-08-03", True)
check("3 Aug named though the window ends on it", w3.get("missing_days"),
      ["2026-08-03"])

print("== no gap, no warning ==")
w2 = _ac.for_window(CFG, A, M, "2026-08-01", "2026-08-02", True)
check("nothing listed", w2.get("missing_days"), None)
check("nothing said", "downloaded" in (w2.get("note") or ""), False)

print()
if fails:
    print("FAILED: %d" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL PASSED")
