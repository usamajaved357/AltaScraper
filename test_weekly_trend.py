"""Twelve weeks of shape, and every kind of missing drawn as a gap.

The cards say what happened this week and the table says what the numbers were.
Neither answers the question a weekly pack is read for -- IS THIS GOING UP OR
DOWN -- which a column of figures hides and a shape shows at a glance.

THE WHOLE RISK IS IN THE MISSING WEEKS, so that is what this tests. There are
three separate ways a point can be absent, and all three must break the line
rather than touch the axis:

  1. THE WEEK WAS NEVER BUILT. Somebody skipped an upload. If the chart plotted
     the rows that happen to be in the database, a skipped week would close up
     and a smooth line would run through a hole that is really there.

  2. THE WEEK IS HALF A PACK. Business Report uploaded, campaign export not. Ad
     spend is MISSING, not nought. Drawn as zero it reads as a week somebody
     switched the ads off -- a different and far more alarming story than
     "nobody uploaded the second file".

  3. THE FIGURE ITSELF IS NULL. RoAS with no spend, TACOS with no sales.

A zero and a gap are different weeks. Every one of these is the same class of
fault as the four spreadsheet defects the feature was built to replace: a wrong
number that arrives quietly.

The functions are RUN, in node, against the real weekly.js -- not read for
strings. A regex over source cannot tell whether a gap survives to the chart.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


# Weeks arrive from the server newest first (ORDER BY week_start DESC), which is
# what _wkSpine relies on to find the right-hand end. Sunday starts the week,
# matching weekly_kpi.week_bounds.
#
#   16 Aug  full pack
#   09 Aug  business only      -> every ad figure is a gap
#   02 Aug  MISSING ENTIRELY   -> a hole in the calendar
#   26 Jul  campaigns only     -> sales, units, sessions are gaps
#   19 Jul  full pack, but no spend, so RoAS is null in the pack itself
WEEKS = [
    {"week_start": "2026-08-16", "week_end": "2026-08-22", "currency": "GBP",
     "has_business": True, "has_campaigns": True,
     "kpis": {"total_sales": 6100.0, "units": 140, "sessions": 4900,
              "ad_spend": 800.0, "ad_sales": 2400.0, "roas": 3.0,
              "acos": 0.3333, "tacos": 0.1311, "cpc": 0.55}},
    {"week_start": "2026-08-09", "week_end": "2026-08-15", "currency": "GBP",
     "has_business": True, "has_campaigns": False,
     "kpis": {"total_sales": 5800.0, "units": 132, "sessions": 4700,
              "ad_spend": 0, "ad_sales": 0, "roas": None,
              "acos": None, "tacos": None, "cpc": None}},
    {"week_start": "2026-07-26", "week_end": "2026-08-01", "currency": "GBP",
     "has_business": False, "has_campaigns": True,
     "kpis": {"total_sales": 0, "units": 0, "sessions": 0,
              "ad_spend": 640.0, "ad_sales": 1900.0, "roas": 2.97,
              "acos": 0.3368, "tacos": None, "cpc": 0.51}},
    {"week_start": "2026-07-19", "week_end": "2026-07-25", "currency": "GBP",
     "has_business": True, "has_campaigns": True,
     "kpis": {"total_sales": 5200.0, "units": 120, "sessions": 4400,
              "ad_spend": 0.0, "ad_sales": 0.0, "roas": None,
              "acos": None, "tacos": 0.0, "cpc": None}},
]

PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.addEventListener = function(){};
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  createElement: () => ({innerHTML: "", querySelector: () => null}),
  addEventListener(){}
};
globalThis.fetch = () => Promise.resolve({json: () => Promise.resolve({ok: true})});
vm.runInThisContext(fs.readFileSync("static/js/weekly.js", "utf8"),
                    {filename: "weekly.js"});

WK.weeks = __WEEKS__;
WK.week = WK.weeks[0];

const spine = _wkSpine();
const vals = function(key){
  WK.trendMetric = key;
  const m = _wkTrendMetric();
  return spine.map(c => _wkTrendVal(m, c));
};

console.log(JSON.stringify({
  spineLen:      spine.length,
  spineStarts:   spine.map(c => c.week_start),
  spineBuilt:    spine.filter(c => !!c.week).length,
  sales:         vals("total_sales"),
  units:         vals("units"),
  adSpend:       vals("ad_spend"),
  roas:          vals("roas"),
  acos:          vals("acos"),
  tacos:         vals("tacos"),
  cardHasChart:  /id="wk_trendchart"/.test(_wkTrendCard()),
  cardCounts:    /4 of 12 weeks have a pack/.test(_wkTrendCard()),
  cardSaysGaps:  /8 not built, shown as gaps/.test(_wkTrendCard()),
  oneWeekNoCard: (function(){
                   const keep = WK.weeks;
                   WK.weeks = [keep[0]];
                   const h = _wkTrendCard();
                   WK.weeks = keep;
                   // Was `h === ""`. See the note beside the assertion.
                   return {noChart: !/id="wk_trendchart"/.test(h),
                           explains: /Only one week is stored/.test(h)};
                 })(),
  noWeeksNoCrash:(function(){
                   const keep = WK.weeks;
                   WK.weeks = [];
                   let ok;
                   try { ok = (_wkSpine().length === 0) && (_wkTrendCard() === ""); }
                   catch(e){ ok = "THREW " + e; }
                   WK.weeks = keep;
                   return ok;
                 })(),
  currencies:    _wkTrendCurrencies(spine),
  mixedCur:      (function(){
                   const keep = JSON.stringify(WK.weeks);
                   WK.weeks[1].currency = "USD";
                   const c = _wkTrendCurrencies(_wkSpine());
                   WK.weeks = JSON.parse(keep);
                   return c;
                 })(),
  metricKeys:    WK_TREND.map(m => m.key),
  metricNeeds:   WK_TREND.map(m => m.needs),
  defaultMetric: (function(){ WK.trendMetric = null; return _wkTrendMetric().key; })(),
  unknownMetric: (function(){ WK.trendMetric = "nope"; return _wkTrendMetric().key; })()
}));
"""


def run_probe():
    src = PROBE.replace("__WEEKS__", json.dumps(WEEKS))
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, src.encode("utf-8"))
    os.close(fd)
    try:
        out = subprocess.run(["node", path], capture_output=True, text=True,
                             cwd=HERE)
    finally:
        os.unlink(path)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "")[:600])
    return json.loads(out.stdout.strip().splitlines()[-1])


try:
    g = run_probe()
except FileNotFoundError:
    print("  (node is not on this machine -- the trend was not exercised)")
    raise SystemExit(0)
except Exception as e:
    print("  FAIL weekly.js threw:", str(e)[:600])
    raise SystemExit(1)


print("=== twelve weeks is a CALENDAR, not the twelve rows that exist ===")
check("twelve points are plotted", g["spineLen"], 12)
# Eleven steps back from 16 Aug, not twelve: the newest week is one of the
# twelve, not the week after them.
check("  oldest on the left, newest on the right",
      (g["spineStarts"][0], g["spineStarts"][-1]), ("2026-05-31", "2026-08-16"))
check("  every one is seven days after the last",
      g["spineStarts"][:4], ["2026-05-31", "2026-06-07", "2026-06-14", "2026-06-21"])
check("  four of them have a pack", g["spineBuilt"], 4)
# THE HOLE IS THE POINT. 2 Aug was never built and sits between two weeks that
# were. Charting only the stored rows would close it up and run a smooth line
# through a week nobody has any figures for.
truthy("the skipped week is present in the calendar",
       "2026-08-02" in g["spineStarts"])


print("\n=== a week nobody built is a gap, not a zero ===")
_i = g["spineStarts"].index("2026-08-02")
check("sales that week", g["sales"][_i], None)
check("  units", g["units"][_i], None)
check("  ad spend", g["adSpend"][_i], None)
# And every week before the first upload. The first pack is 19 Jul, at index 7,
# so the seven before it are empty -- a new account's first chart is mostly gap
# and must not read as a collapse from nothing.
check("every week before the first pack is a gap", g["sales"][:7], [None] * 7)
check("  and the first real one is where the pack is", g["sales"][7], 5200.0)


print("\n=== half a pack: the missing half is a gap, the present half is real ===")
_b = g["spineStarts"].index("2026-08-09")     # business only
check("its sales are real", g["sales"][_b], 5800.0)
# THE ONE THAT WOULD MISLEAD MOST. The pack stores ad_spend as 0 for this week
# because nothing was counted; plotted as 0 the line dives to the axis and reads
# as "the ads were switched off".
check("  its ad spend is a gap, though the pack holds 0", g["adSpend"][_b], None)
check("  and its RoAS is a gap", g["roas"][_b], None)
_c = g["spineStarts"].index("2026-07-26")     # campaigns only
check("the campaigns-only week has real spend", g["adSpend"][_c], 640.0)
check("  but its sales are a gap, though the pack holds 0", g["sales"][_c], None)
check("  and its units", g["units"][_c], None)
# TACOS needs BOTH halves -- it is all spend over all sales.
check("TACOS is a gap on both half packs",
      (g["tacos"][_b], g["tacos"][_c]), (None, None))


print("\n=== a figure the arithmetic could not produce is a gap too ===")
_d = g["spineStarts"].index("2026-07-19")     # full pack, no spend at all
check("a full week with no spend still charts its sales", g["sales"][_d], 5200.0)
check("  but RoAS is a gap, not 0", g["roas"][_d], None)
check("  and ACOS", g["acos"][_d], None)
# A REAL ZERO SURVIVES AS ZERO. TACOS really was 0.0 that week -- no spend
# against real sales -- and turning that into a gap would be the same fault in
# the other direction.
check("  while a TACOS that really was nought is plotted", g["tacos"][_d], 0.0)


print("\n=== rates are scaled, because the axis prints what it is given ===")
_e = g["spineStarts"].index("2026-08-16")
# The pack stores 0.3333, and salesChart's percentage axis prints the number as
# it receives it. Unscaled this axis would read "0%" for a third.
check("ACOS reaches the chart as 33.33, not 0.3333",
      round(g["acos"][_e], 2), 33.33)
check("  and TACOS as 13.11", round(g["tacos"][_e], 2), 13.11)
check("money is not scaled", g["sales"][_e], 6100.0)
check("  nor is RoAS", g["roas"][_e], 3.0)


print("\n=== the card says what it is showing ===")
truthy("there is somewhere to draw", g["cardHasChart"])
truthy("  it says how many weeks have a pack", g["cardCounts"])
truthy("  and that the rest are gaps rather than nothing", g["cardSaysGaps"])
# ONE POINT IS NOT A TREND. A single dot reads as a chart that failed to draw,
# so no chart is still right.
#
# THIS USED TO REQUIRE THE CARD TO BE EMPTY, and that was the bug. Measured the
# day after this shipped: the store holds exactly one week per account, so every
# account fell into this branch and the twelve-week trend could not be found
# anywhere in the app. The card now says which of the two it is -- there is no
# line yet, and why -- which is what the code comment beside it always claimed
# it did. Drawing no chart and saying nothing are different answers.
truthy("one week draws no chart", g["oneWeekNoCard"]["noChart"])
truthy("  but says why, instead of removing itself",
       g["oneWeekNoCard"]["explains"])
check("no weeks at all is not a crash", g["noWeeksNoCrash"], True)


print("\n=== money is not charted across two currencies ===")
check("one currency is seen when there is one", g["currencies"], ["GBP"])
check("  and both when a week was reported differently",
      sorted(g["mixedCur"]), ["GBP", "USD"])


print("\n=== the metric list, and a bad pick ===")
check("nine metrics are offered", len(g["metricKeys"]), 9)
truthy("  sales is the default", g["defaultMetric"] == "total_sales")
# A stale chip from an older page must not blank the chart.
check("an unknown metric falls back rather than breaking",
      g["unknownMetric"], "total_sales")
check("TACOS is the only one needing both halves",
      [k for k, n in zip(g["metricKeys"], g["metricNeeds"]) if n == "both"],
      ["tacos"])


print("\n=== drawn with the app's one chart, not a fifth (Rule 12) ===")
JS = open("static/js/weekly.js", encoding="utf-8").read()
truthy("it calls salesChart", "salesChart(points" in JS)
truthy("  and measures its box the shared way", 'scChartWidth("wk_trendchart"' in JS)
# Nulls must reach salesChart AS nulls -- it is the shared chart that knows to
# break the line rather than touch the axis, and any || 0 on the way there would
# undo every assertion above.
truthy("no null is quietly turned into a zero on the way",
       "value: _wkTrendVal(m, c)" in JS)
truthy("the card is drawn after the HTML is in the page, so it can be measured",
       JS.index("host.innerHTML = h;\n  // AFTER") > 0)
CSS = open("static/css/dashboard.css", encoding="utf-8").read()
truthy("the picked chip is filled, not just outlined", ".wk-tchip.on{" in CSS)

print("\n=== and the gap survives all the way into the drawn SVG ===")
# EVERYTHING ABOVE CHECKS AN ARRAY OF NULLS. This checks the picture. A null
# that reaches salesChart and is then drawn as a point on the axis would pass
# every assertion so far and still be the exact lie this feature must not tell.
DRAW = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.addEventListener = function(){};
let HTML = "";
globalThis.document = {
  getElementById: (id) => (id === "wk_trendchart"
      ? {clientWidth: 900, getBoundingClientRect: () => ({width: 900}),
         set innerHTML(v){ HTML = v; }, get innerHTML(){ return HTML; }}
      : null),
  querySelectorAll: () => [], addEventListener(){},
  createElement: () => ({innerHTML: "", querySelector: () => null})
};
vm.runInThisContext(fs.readFileSync("static/js/salescharts.js","utf8"),{filename:"sc.js"});
vm.runInThisContext(fs.readFileSync("static/js/weekly.js","utf8"),{filename:"wk.js"});
WK.weeks = __WEEKS__; WK.week = WK.weeks[0];
const draw = function(m){ WK.trendMetric = m; _wkDrawTrend(); return HTML; };
const sales = draw("total_sales"), spend = draw("ad_spend");
const lone = s => (s.match(/<circle/g) || []).length / 2;   // halo + dot
const segs = s => (s.match(/<path[^>]+class="?sc-line/g) || []).length;
WK.weeks[1].currency = "USD";
const mixed = draw("total_sales"), rate = draw("roas");
console.log(JSON.stringify({
  salesIsSvg: /<svg/.test(sales), spendIsSvg: /<svg/.test(spend),
  salesLone: lone(sales), spendLone: lone(spend),
  salesLen: sales.length,
  mixedRefused: /not in one currency/.test(mixed),
  mixedNoSvg: !/<svg/.test(mixed),
  rateStillDrawn: /<svg/.test(rate)
}));
"""
try:
    _src = DRAW.replace("__WEEKS__", json.dumps(WEEKS))
    _fd, _p = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(_fd, _src.encode("utf-8"))
    os.close(_fd)
    _o = subprocess.run(["node", _p], capture_output=True, text=True, cwd=HERE)
    os.unlink(_p)
    if _o.returncode != 0:
        FAILS.append("the chart threw")
        print("  FAIL the chart threw:", (_o.stderr or "")[:400])
    else:
        d = json.loads(_o.stdout.strip().splitlines()[-1])
        truthy("a real chart is produced", d["salesIsSvg"] and d["spendIsSvg"])
        truthy("  a whole one, not a stub", d["salesLen"] > 4000)
        # A LONE POINT IS A POINT WITH A GAP EITHER SIDE, and salesChart rings
        # it rather than leaving it invisible between two breaks. Ad spend has
        # exactly one: 16 Aug, cut off because 9 Aug has no campaign half. If
        # that half pack had been plotted as zero there would be no lone point
        # at all -- so this number is the gap, measured on the picture.
        check("  the half pack really does break the ad-spend line",
              d["spendLone"], 1)
        # Sales has exactly one, and WHICH one is the proof: 19 Jul is cut off
        # on both sides -- by the campaigns-only week of 26 Jul on one side and
        # the week nobody built on the other. Two different kinds of missing,
        # both breaking the same line. Plot either as zero and this dot becomes
        # part of a run instead.
        check("  and the sales line breaks at BOTH kinds of missing week",
              d["salesLone"], 1)
        truthy("mixed currencies refuse to draw money", d["mixedRefused"])
        truthy("  and draw nothing rather than something wrong", d["mixedNoSvg"])
        truthy("  while RoAS, a ratio, still draws", d["rateStillDrawn"])
except FileNotFoundError:
    print("  (node is not on this machine -- the drawing was not exercised)")
except Exception as e:
    FAILS.append("the drawing probe")
    print("  FAIL probe:", str(e)[:300])


print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
