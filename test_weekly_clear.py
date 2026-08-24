"""Clearing the weeks already uploaded, so fresh reports can go in cleanly.

    "give me an option to delete or clear all data which is already UPLOADED IN
     THE weekly kpi's page, i want to upload my new data when the old one is
     deleted to avoid any confusion"

Weeks could be uploaded and re-uploaded but never removed. Re-uploading the SAME
week corrects it -- store() replaces rather than duplicates -- but a week loaded
against the wrong account, or built from the wrong export, stayed in the pack
for good, and every week-on-week comparison after it read against a week that
should not have been there.

THE THREE THINGS THIS HAS TO GET RIGHT, in order of how bad they are:

  1. ONE ACCOUNT AND ONE MARKETPLACE. Every workspace's weeks share one table
     and the page shows one account at a time. A clear that ignored the scope
     would wipe another account's reporting history with nothing to say so
     until a week was missing from a client report.
  2. THE NUMBER IN THE WARNING IS THE NUMBER THAT GOES. A confirmation that
     says 1 and deletes 20 is worse than no confirmation.
  3. IT SAYS THERE IS NO WAY BACK. The row holds a frozen JSON pack; the only
     recovery is re-uploading the source reports.

Run against a temporary config so the real weekly_kpi table is never touched.
"""
import json
import os
import shutil
import sys
import tempfile

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import weekly_kpi as WK

TMP = tempfile.mkdtemp(prefix="wkclear_")
CFG = os.path.join(TMP, "config.json")
with open(CFG, "w", encoding="utf-8") as fh:
    json.dump({}, fh)


def seed():
    """Four weeks across two accounts and two marketplaces."""
    for wsid, mkt, weeks in (("jack_uk", "UK", ["2026-08-02", "2026-08-09"]),
                             ("jack_uk", "DE", ["2026-08-09"]),
                             ("nestwell_goods", "UK", ["2026-08-09"])):
        for w in weeks:
            WK.store(CFG, wsid, mkt, {"week_start": w, "week_end": w,
                                      "kpis": {"units": 1}}, source="test")


seed()

print("=== the count is real, and it is per account AND marketplace ===")
check("jack_uk UK has two", WK.count_weeks(CFG, "jack_uk", "UK"), 2)
check("jack_uk DE has one", WK.count_weeks(CFG, "jack_uk", "DE"), 1)
check("nestwell_goods UK has one", WK.count_weeks(CFG, "nestwell_goods", "UK"), 1)
check("an account with none says none", WK.count_weeks(CFG, "selvora_limited", "UK"), 0)
# The warning quotes this number, so a count that disagreed with the delete
# would be a dialog that lies.
check("  and it matches what a clear would remove",
      WK.count_weeks(CFG, "jack_uk", "UK"), 2)


print("\n=== clearing one scope leaves every other alone ===")
check("it reports what it removed", WK.clear(CFG, "jack_uk", "UK"), 2)
check("jack_uk UK is empty", WK.count_weeks(CFG, "jack_uk", "UK"), 0)
# THE MARKETPLACE IS PART OF THE SCOPE, not just the account. A seller reporting
# on UK and DE separately must not lose Germany by tidying Britain.
check("  jack_uk DE is untouched", WK.count_weeks(CFG, "jack_uk", "DE"), 1)
check("  and so is nestwell_goods UK", WK.count_weeks(CFG, "nestwell_goods", "UK"), 1)


print("\n=== one week can go without taking the year with it ===")
seed()
check("jack_uk UK is back to two", WK.count_weeks(CFG, "jack_uk", "UK"), 2)
check("deleting one week removes one",
      WK.clear(CFG, "jack_uk", "UK", week_start="2026-08-02"), 1)
check("  and the other survives", WK.count_weeks(CFG, "jack_uk", "UK"), 1)
_left = WK.weeks(CFG, "jack_uk", "UK")
check("  the right one survived", [w["week_start"] for w in _left], ["2026-08-09"])
check("a week that is not there removes nothing",
      WK.clear(CFG, "jack_uk", "UK", week_start="1999-01-01"), 0)


print("\n=== a missing scope deletes NOTHING, rather than everything ===")
_before = sum(WK.count_weeks(CFG, a, m) for a, m in
              (("jack_uk", "UK"), ("jack_uk", "DE"), ("nestwell_goods", "UK")))
check("no account", WK.clear(CFG, "", "UK"), 0)
check("  no marketplace", WK.clear(CFG, "jack_uk", ""), 0)
check("  neither", WK.clear(CFG, None, None), 0)
_after = sum(WK.count_weeks(CFG, a, m) for a, m in
             (("jack_uk", "UK"), ("jack_uk", "DE"), ("nestwell_goods", "UK")))
check("  and nothing was lost", _after, _before)

# The marketplace is upper-cased on the way in by store(); a clear typed in
# lower case must still find them or it silently does nothing.
seed()
check("a lower-case marketplace still matches", WK.clear(CFG, "jack_uk", "uk"), 2)

shutil.rmtree(TMP, ignore_errors=True)


print("\n=== the route asks before it deletes, and refuses a moved target ===")
RT = open("routes/weekly_routes.py", encoding="utf-8").read()
truthy("there is a count endpoint to word the warning with",
       '@app.route("/weekly/count")' in RT)
truthy("  and it deletes nothing",
       "clear(" not in RT.split("def weekly_count")[1].split("@app.route")[0])
truthy("the clear endpoint exists",
       '@app.route("/weekly/clear", methods=["POST"])' in RT)
_clear = RT.split("def weekly_clear")[1].split("@app.route")[0]
truthy("  it goes through the store rather than its own SQL",
       "_wk.clear(CONFIG_PATH" in _clear and "DELETE FROM" not in _clear)
truthy("  it refuses without an account and a marketplace",
       "Open an account and pick a marketplace first" in _clear)
truthy("  and refuses when the number moved under the dialog",
       "expect" in _clear and "409" in _clear)
truthy("  reporting what actually went", '"deleted": gone' in _clear)
# Deleting ONE week is not a bulk delete and must not be blocked by the count
# check, which is about "all of them".
truthy("  the single-week path is not gated on the total",
       "if not week and expected is not None" in _clear)


print("\n=== it needs the same permission as any other bulk delete ===")
from auth import guard
check("/weekly/clear needs approve_delete",
      guard.required_permission("/weekly/clear", "POST"), "approve_delete")
check("  uploading a week is still ordinary editing",
      guard.required_permission("/weekly/upload", "POST"), "edit")
check("  and reading the count is a read",
      guard.required_permission("/weekly/count", "GET"), None)


print("\n=== the screen warns, with the number, and says what it cannot undo ===")
JS = open("static/js/weekly.js", encoding="utf-8").read()
_fn = JS.split("async function weeklyClearAll")[1].split("\nasync function weeklyPull")[0]
truthy("the count comes from the server, not the rows on screen",
       '"/weekly/count"' in _fn)
truthy("  because the page draws a capped list",
       "capped list" in JS.split("CLEARING WHAT WAS UPLOADED")[1][:900])
truthy("nothing is deleted without a confirm", "confirm(" in _fn)
truthy("  which states the number", 'Delete all " + n + " stored week' in _fn)
truthy("  and names the account and marketplace", "for \" + where + \"?" in _fn)
truthy("  says it cannot be undone", "cannot be undone" in _fn)
truthy("  and that other accounts are safe",
       "Other accounts and other marketplaces are not touched" in _fn)
truthy("the agreed number is sent back with the request", "expect: n" in _fn)
truthy("no dialog at all when there is nothing stored",
       "if(!n){" in _fn and "no stored weeks" in _fn)
truthy("the page reloads afterwards so the screen agrees with the store",
       "await weeklyLoad()" in _fn)

HTML = open("templates/dashboard.html", encoding="utf-8").read()
truthy("the button is on the weekly toolbar", 'onclick="weeklyClearAll()"' in HTML)
_sec = HTML.split('id="sec_weekly"')[1][:4000]
truthy("  in the same toolbar as the uploads it undoes",
       'onclick="weeklyClearAll()"' in _sec and "weeklyUploadOpen" in _sec)
CSS = open("static/css/dashboard.css", encoding="utf-8").read()
truthy("  and it does not look like the buttons that ADD data",
       ".db-chip.wkwipe{color:var(--red)}" in CSS.replace(" ", "")
       or "wkwipe" in CSS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
