"""test_reports_bug_round.py -- the reports screens bug round (30 Sep 2026).

    "look for bugs in all screens one by one and fix them all across the app"

Covers the fixes made to Home, Daily round, Weekly brief, Sales, Traffic,
Hourly and Weekly KPIs. Behavioural where the code can run without a browser,
database or Amazon; source pins where it cannot. Plain script: exits non-zero
on failure, like every other test_*.py here.
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


def src(*parts):
    return io.open(os.path.join(HERE, *parts), encoding="utf-8").read()


def node(js):
    """Run a snippet of JavaScript and return its printed JSON."""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True,
                         cwd=HERE, timeout=60)
    if out.returncode != 0:
        print(out.stderr[-600:])
        return None
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        print(out.stdout[-400:])
        return None


def fn_src(text, name):
    """The source of one top-level JS function (up to the next '\\n}')."""
    i = text.find("function " + name + "(")
    if i < 0:
        return ""
    j = text.find("\n}", i)
    return text[i:j + 2]


# ---------------------------------------------------------------------------
print("\n== BRIEF: only visible accounts, every marketplace ==")
from domain import weekly_brief as WB

cfg = {"accounts": [
    {"id": "a", "name": "Alpha", "default_marketplace": "uk"},
    {"id": "b", "name": "Beta", "default_marketplace": "DE",
     "marketplaces": ["DE", "FR", "de"]},
    {"id": "c", "name": "Gamma"},
]}
acc = WB._accounts(cfg)
check("one entry per (account, marketplace)",
      [(a["id"], a["marketplace"]) for a in acc],
      [("a", "UK"), ("b", "DE"), ("b", "FR"), ("c", "")])
check("a multi-marketplace account names the marketplace on its label",
      [a["label"] for a in acc if a["id"] == "b"], ["Beta (DE)", "Beta (FR)"])
check("a single-marketplace label is unchanged",
      [a["label"] for a in acc if a["id"] == "a"], ["Alpha"])
check("the visibility rule filters accounts before anything is read",
      sorted({a["id"] for a in WB._accounts(cfg, visible=lambda r: r["id"] != "b")}),
      ["a", "c"])
BR = src("routes", "brief_routes.py")
truthy("the route passes the signed-in user's rule (auth.users.visible_accounts)",
       "visible_accounts(" in BR and "visible=_visible" in BR)
BJ = src("static", "js", "brief.js")
truthy("brief.js: newest request wins", "my !== BRIEF.seq" in BJ)

# ---------------------------------------------------------------------------
print("\n== DAILY: a refused order list is 'could not check', never green ==")
from routes import daily_routes as DR
from domain import daily_check as DC

check("an ok reply with rows is usable",
      DR._orders_problem({"ok": True, "rows": [], "errors": [],
                          "accounts_asked": ["a"]}), "")
truthy("an ok reply carrying errors is NOT usable",
       DR._orders_problem({"ok": True, "rows": [],
                           "errors": [{"account": "a", "error": "Unauthorized"}],
                           "accounts_asked": ["a"]}))
truthy("no account asked (no credentials) is NOT usable",
       DR._orders_problem({"ok": True, "rows": [], "errors": [],
                           "accounts_asked": []}))
truthy("a failed reply is NOT usable", DR._orders_problem({"ok": False}))

got = DC.run({"orders_error": "Amazon did not return the order list: Unauthorized"})
by = {c["key"]: c for c in got["checks"]}
for k in ("unshipped", "cancel_requested", "fbm"):
    check("  %s is unknown when the list was refused" % k, by[k]["status"], DC.UNKNOWN)
truthy("  and says why", "Unauthorized" in by["unshipped"]["needs"])
check("checks that can never run are marked `always`",
      sorted(c["key"] for c in got["checks"] if c.get("always")),
      sorted(k for (k, _t, _g, _w) in DC.CANNOT))
falsy("a check that normally runs is not marked `always`", by["unshipped"].get("always"))
DRS = src("routes", "daily_routes.py")
truthy("the round asks for the marketplace it is checking",
       '"&marketplace=" + _q(mkt)' in DRS)
truthy("the repricer read selects `action` so price-editor rows are left out",
       "SELECT applied, action FROM sourcing_actions" in DRS)
truthy("yesterday is the marketplace's own day (orders_live.day_start)",
       "day_start(mkt, days_ago=1)" in DRS)
ORS = src("routes", "orders_routes.py")
truthy("/orders/list honours ?marketplace= only for the account's own",
       "want_mkt in own" in ORS)
DJ = src("static", "js", "daily.js")
truthy("daily.js: newest run wins", "my !== DAILY.seq" in DJ)
truthy("daily.js: a failed re-run is shown above the previous round",
       "Showing the previous round" in DJ)
HJ = src("static", "js", "home.js")
truthy("home.js names the checks that normally run and could not today",
       "!c.always" in HJ and "Could not check today" in HJ)

# ---------------------------------------------------------------------------
print("\n== WEEKLY: the right change, the right account, the right week ==")
from domain import weekly_kpi as WKd

weeks = [{"week_start": "2026-09-20", "kpis": {"total_sales": 200.0}},
         {"week_start": "2026-09-13", "kpis": {"total_sales": 100.0}},
         {"week_start": "2026-08-30", "kpis": {"total_sales": 50.0}}]
ch = WKd.changes_by_week(weeks)
check("a week with its calendar predecessor gets a change",
      round(ch["2026-09-20"]["total_sales"]["pct"], 2), 1.0)
falsy("a week whose week before is missing gets none (a gap is not 'the week before')",
      "2026-09-13" in ch)
WR = src("routes", "weekly_routes.py")
truthy("the half-built pack is keyed by week", "_pending_key(wsid, mkt, week_start)" in WR)
truthy("/weekly/clear forgets the held halves", "_forget_pending(wsid, mkt" in WR)
truthy("the grid header names the REQUESTED account",
       "_acc.get_account(" in WR.split("def _grid(")[1].split("@app.route")[0])
WJ = src("static", "js", "weekly.js")
q = node(
    "var WS_MARKET='__all__', CUR_ACCOUNT={id:'acme'};"
    "var document={getElementById:function(){return {value:'parent'};}};"
    + fn_src(WJ, "_wkGroup") + fn_src(WJ, "_wkQuery")
    + "console.log(JSON.stringify(_wkQuery()));")
falsy("_wkQuery never sends __all__", q is None or "__all__" in (q or "").lower())
d = node(
    "var WK={change:{x:{from:0,to:5,delta:5,pct:null,better:true}}};"
    "function _wkEsc(s){return String(s);}"
    + fn_src(WJ, "_wkDelta") + "console.log(JSON.stringify(_wkDelta('x')));")
truthy("a rise from zero reads 'new', not '+0.0%'", d and ">new<" in d and "0.0%" not in d)
truthy("the shown week's own change is used", "WK.changes[WK.week.week_start]" in WJ)
truthy("the Rows dropdown cancels a pending sheet write",
       'onchange="weeklySheetCancel()"' in src("templates", "screens", "sec_weekly.html"))

# ---------------------------------------------------------------------------
print("\n== TRAFFIC: parent trend, equal windows, gaps kept ==")
from domain import traffic_view as TV

check("a window missing its last 2 of 7 days compares 5 days against 5",
      TV._equal_length_prev(("2026-09-01", "2026-09-07"), "2026-09-08",
                            {"missing_days": 2, "last": "2026-09-12"}),
      ("2026-09-01", "2026-09-05"))
check("nothing missing leaves the previous window alone",
      TV._equal_length_prev(("2026-09-01", "2026-09-07"), "2026-09-08",
                            {"missing_days": 0, "last": "2026-09-14"}),
      ("2026-09-01", "2026-09-07"))
check("every day of the window is on the axis",
      TV._all_dates("2026-09-28", "2026-10-01"),
      ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"])
TVS = src("domain", "traffic_view.py")
truthy("the trend groups by the same key as the table",
       "asin_daily(config_path, workspace_id, marketplace, start, end,\n"
       "                           [r[\"asin\"] for r in top], group=group)" in TVS)
TJ = src("static", "js", "traffic.js")
falsy("traffic.js no longer drops a load while busy", "if(TRAF.busy) return;" in TJ)
truthy("  newest request wins", "my !== TRAF.seq" in TJ)
truthy("a nested zoom keeps the first way back", "if(!TRAF._zoomBack) TRAF._zoomBack" in TJ)

# ---------------------------------------------------------------------------
print("\n== HOURLY ==")
HW = src("domain", "hourly_week.py")
truthy("a placeholder-only order is not 'known' (so it is itemised later)",
       "AND COALESCE(sku,'')<>''" in HW.split("def known_order_ids")[1].split("def ")[0])
truthy("the placeholder is removed once real lines are stored",
       "DELETE FROM order_lines" in HW.split("def store_lines")[1].split("def ")[0])
truthy("cancelled orders are excluded from the summary",
       "NOT IN ('canceled','cancelled')" in HW.split("def summary")[1])
truthy("the summary reports the days actually stored", '"first_day": first_day' in HW)
HJS = src("static", "js", "hourly.js")
falsy("hourly.js no longer drops a load while busy", "if(HRLY.busy) return;" in HJS)
truthy("  newest request wins", "my !== HRLY.seq" in HJS)
truthy("the pull's message survives the redraw", "(HRLY.status || \"\")" in HJS)
truthy("the Mon-Sun grid is shaded against its busiest cell", "_hCell(v, gridPeak)" in HJS)

# ---------------------------------------------------------------------------
print("\n== SALES ==")
SJ = src("static", "js", "sales.js")
spans = node(fn_src(SJ, "_sBucketSpan") + fn_src(SJ, "_sBackKey") + (
    "console.log(JSON.stringify({"
    "w:_sBucketSpan('2026-09-07','week'), m:_sBucketSpan('2026-02','month'),"
    "d:_sBucketSpan('2026-09-07','day'),"
    "bw:_sBackKey('2026-09-07',30,'week'), bm:_sBackKey('2026-09',30,'month'),"
    "by:_sBackKey('2026-09-07',364,'week'), bd:_sBackKey('2026-09-07',7,'day')}));"))
spans = spans or {}
check("a Week column zooms to Monday..Sunday", spans.get("w"), ["2026-09-07", "2026-09-13"])
check("a Month column zooms to its first..last day", spans.get("m"), ["2026-02-01", "2026-02-28"])
check("a Day column is that day", spans.get("d"), ["2026-09-07", "2026-09-07"])
check("the prior-period line finds a Week bucket (snapped to Monday)",
      spans.get("bw"), "2026-08-03")
check("  and a Month bucket", spans.get("bm"), "2026-08")
check("  and a prior-year Week lines up weekday on weekday", spans.get("by"), "2025-09-08")
check("  and a Day is the plain shift", spans.get("bd"), "2026-08-31")
truthy("picking a preset ends a zoom",
       "SALES._zoomBack = null" in fn_src(SJ, "salesSet"))
truthy("salesZoomTo redraws the filters", "salesDrawFilters()" in fn_src(SJ, "salesZoomTo"))
truthy("_sFetch drops a reply after a scope change (screenStillIn)",
       "screenStillIn(_sc)" in fn_src(SJ, "_sFetch"))
truthy("salesReload: newest load wins (loadSeq)", "SALES.loadSeq" in SJ
       and "if(SALES.busy){ SALES._again = true; return; }" not in SJ)
truthy("_sQuery sends the comparison choice", "compare_kind=year" in SJ)
SRS = src("routes", "sales_routes.py")
truthy("/sales/summary shifts 364 days for the prior year",
       'compare_kind' in SRS and "timedelta(days=364)" in SRS)
SCJ = src("static", "js", "sales_cards.js")
truthy("the cards' LY/was label follows the reply, not the picker",
       "_sPrevLabel(sum)" in SCJ and 'SALES.compareKind === "year" ? "LY"' not in SCJ)
SW = src("static", "js", "sales_week.js")
truthy("week to date uses the browser's local day", "today.getDay()" in SW
       and "today.getUTCDay()" not in SW)
truthy("week-to-date errors use the shared error card", '_sCardError(host' in SW)
truthy("the ad footer uses the shared currency symbol", "curSymbol(cur)" in SW)
truthy("the Week to Date hint says Sunday", "Sunday to today" in
       src("templates", "screens", "sec_sales.html"))
SG = src("static", "js", "sales_grid.js")
falsy("heatmap clicks while loading are no longer dropped",
      "if(SALES.gridBusy) return;" in SG)
truthy("a custom grid period sends its dates", 'q.push("start="' in fn_src(SG, "salesLoadGrid"))
truthy("reloads draw the grid in the grid's own period", "function salesRedrawGrid" in SG)
SB = src("static", "js", "sales_breakdown.js")
truthy("the Product column sorts A-Z the same way as the numbers",
       'dir*(x<y?-1:x>y?1:0)' in SB)
SCP = src("static", "js", "sales_campaigns.js")
truthy("Organic vs PPC: connected with no ad sales is measured, not 'not connected'",
       "ser.ads.ok === true" in SCP)

print("\nFAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
