"""A day nobody asked Amazon about is not a day that sold nothing.

    "why have you not fixed the week to date"

WHAT WAS ON SCREEN. The Week to Date card read "£0.00 ↓100.0%" with a flat line
along the bottom, while the Sales Report on the SAME PAGE said "Amazon has data
to 2026-08-20". The card was reporting a total collapse in revenue over three
days nobody had fetched.

WHERE IT CAME FROM. sales_daily is padded to today. Measured on 25 Aug 2026:

    data_availability   sales feed reached 2026-08-20
    sales_daily         rows through 2026-08-25

    2026-08-20   37.07   1 unit     <- the last day Amazon answered for
    2026-08-21 .. 25     0.0  0     <- padding

Five zeros the whole app believed. The comparison week was worse: 21 and 22
August are padding too, so the -100% was measured against a baseline that was
itself part invented, and the 30-day report covered four of them as well.

CHECKED ACROSS THE WHOLE STORE rather than the account it was noticed on: 34
account/marketplace pairs, three carrying padding (jack_uk/UK 5 days,
selvora_limited/UK 5, nestwell_goods/UK 2), and not one padded row anywhere
holds a figure. So dropping them cannot hide real data.

A GENUINE ZERO IS UNTOUCHED. 15 and 16 August sold nothing and Amazon said so.
Those are answers and they stay zeros. The rule is narrow on purpose: past the
fetched range AND nothing in the row.

THE BROWSER WAS ALREADY RIGHT and was being handed zeros to draw -- _wkSum
returns null when nothing is known, _wkBit hides the figure, and the note says
"not in from Amazon yet -- shaded, not zero". All of it was waiting.

AND THE CHART HAD TO KEEP DRAWING. salesChart gave up on "no current values"
before it had even read the comparison, so the fix briefly cost the card its
chart -- the exact thing reported twice before ("even i dont have any sales the
graph should be displayed"). Both series already share one scale; it now gives
up only when NEITHER has a figure.
"""
import json
import os
import sqlite3
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
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


from domain import sales_data as sd

print("=== the rule itself: past the fetched range AND empty ===")
CUT = "2026-08-20"


def row(d, sales=None, units=None, orders=None, sessions=None):
    return {"date": d, "ordered_sales": sales, "units": units,
            "orders": orders, "sessions": sessions, "currency": "GBP"}


held = {
    "2026-08-19": row("2026-08-19", 0.0, 0, 0, None),      # real zero, in range
    "2026-08-20": row("2026-08-20", 37.07, 1, 1, None),    # the last real day
    "2026-08-21": row("2026-08-21", 0.0, 0, 0, None),      # padding
    "2026-08-22": row("2026-08-22", 0.0, 0, 0, None),      # padding
}
kept = sd._drop_padding(dict(held), CUT)
check("a real zero inside the range is kept", "2026-08-19" in kept, True)
check("  because Amazon answered for that day and the answer was none",
      kept.get("2026-08-19", {}).get("ordered_sales"), 0.0)
check("the last measured day is kept", "2026-08-20" in kept, True)
check("an empty day past the range is dropped", "2026-08-21" in kept, False)
check("  and so is the next one", "2026-08-22" in kept, False)

print("\n=== it can never hide a figure ===")
# If a later pass DOES write a real day past the recorded extent -- order_lines
# reaches back further than the report feed -- that row must survive.
for field in ("ordered_sales", "units", "orders", "sessions"):
    one = {"2026-08-24": row("2026-08-24")}
    one["2026-08-24"][field] = 3
    check("a day past the range carrying %s is kept" % field,
          "2026-08-24" in sd._drop_padding(one, CUT), True)

print("\n=== with no recorded extent, nothing is dropped ===")
# An account this has no availability record for must behave exactly as before.
check("no cutoff means no change", sd._drop_padding(dict(held), None), held)
check("  an empty cutoff too", sd._drop_padding(dict(held), ""), held)

print("\n=== and the real store agrees with the rule ===")
conn = sqlite3.connect("altascraper.db")
conn.row_factory = sqlite3.Row
# THE CLAIM THIS FIX RESTS ON, re-checked here rather than trusted: no padded
# row anywhere carries a figure. If that ever stops being true this test fails
# and the rule needs revisiting -- it must not quietly start hiding data.
bad = conn.execute(
    "SELECT COUNT(*) FROM sales_daily s JOIN data_availability a "
    "  ON a.workspace_id=s.workspace_id AND a.marketplace=s.marketplace "
    " AND a.source='sales' "
    "WHERE s.date > a.last_date AND (COALESCE(s.ordered_sales,0)>0 "
    "   OR COALESCE(s.units,0)>0 OR COALESCE(s.orders,0)>0 "
    "   OR COALESCE(s.sessions,0)>0)").fetchone()[0]
check("no row past a fetched range carries a figure", bad, 0)
padded = conn.execute(
    "SELECT COUNT(*) FROM sales_daily s JOIN data_availability a "
    "  ON a.workspace_id=s.workspace_id AND a.marketplace=s.marketplace "
    " AND a.source='sales' WHERE s.asin='*' AND s.date > a.last_date").fetchone()[0]
print("     (padded rows currently in the store: %d)" % padded)
conn.close()

print("\n=== both load sites are cut, not just the first ===")
SRC = open(os.path.join("domain", "sales_data.py"), encoding="utf-8").read()
# The order basis re-reads sales_daily after live_reconcile rewrites it. A cut
# applied only to the first read would leave the default basis uncut.
check("every read of sales_daily in series() is filtered",
      SRC.count("_drop_padding("), 3)      # the def, plus two call sites
truthy("the cutoff is read once", SRC.count("_cut = _sales_cutoff(") == 1)
truthy("and it fails open", "return None" in
       SRC.split("def _sales_cutoff(")[1].split("def ")[0])

print("\n=== the chart survives a period whose own days are unknown ===")
PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.document = {getElementById: () => null, addEventListener(){}};
globalThis.addEventListener = function(){};
const src = fs.readFileSync("static/js/salescharts.js", "utf8");
vm.runInThisContext(src);
const days = ["2026-08-23","2026-08-24","2026-08-25"];
const none = days.map(d => ({label: d, value: null}));
const was  = days.map((d,i) => ({label: d, value: [0, 73.59, 37.07][i]}));
const out = {};
// This week unknown, last week known -- the Week to Date card on 25 Aug.
const withCmp = salesChart(none, {title: "", kind: "money", compare: was,
                                  scale: "band", width: 665, height: 200});
out.drawsWithCompare = withCmp.indexOf("<svg") >= 0;
out.shadesEveryGap   = (withCmp.match(/opacity="0.07"/g) || []).length;
out.noCurrentLine    = withCmp.indexOf('stroke="#') < 0
                       || !/class="series"[^>]*stroke="#[0-9a-fA-F]{6}"/.test(withCmp);
// Neither known: no chart, but the sentence must not claim there were none.
const neither = salesChart(none, {title: "Week to Date", kind: "money",
                                  unit: "day", scale: "band"});
out.neitherNoSvg    = neither.indexOf("<svg") < 0;
out.neitherSaysNotKnown = /no figures for these days yet/.test(neither);
out.neitherRefusesNone  = /not the same as none/.test(neither);
out.neitherNotNothing   = !/nothing in this period yet/.test(neither);
// A genuinely empty range still says so -- there are no days to know about.
const empty = salesChart([], {title: "Week to Date", kind: "money"});
out.emptySaysNothing = /nothing in this period yet/.test(empty);
console.log(JSON.stringify(out));
"""
try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, PROBE.encode("utf-8"))
    os.close(fd)
    r = subprocess.run(["node", path], capture_output=True, text=True,
                       encoding="utf-8", cwd=HERE)
    os.unlink(path)
    if r.returncode != 0:
        print("  FAIL salescharts.js threw:", (r.stderr or "")[:400])
        raise SystemExit(1)
    g = json.loads(r.stdout.strip().splitlines()[-1])
except FileNotFoundError:
    print("  (node is not on this machine -- chart half not exercised)")
    g = None

if g:
    # THE CARD MUST NOT DISAPPEAR. Reported twice before this fix existed.
    truthy("a chart is still drawn when only last week is known",
           g["drawsWithCompare"])
    check("  every unknown day is shaded", g["shadesEveryGap"], 3)
    truthy("  and no line is drawn through this week", g["noCurrentLine"])
    truthy("with neither known there is no chart", g["neitherNoSvg"])
    # "nothing in this period yet" is the same claim as plotting a zero.
    truthy("  but it says the figures are not known", g["neitherSaysNotKnown"])
    truthy("  and that this is not the same as none", g["neitherRefusesNone"])
    truthy("  never calling unmeasured days nothing", g["neitherNotNothing"])
    # A range with no days in it is a different fact and keeps its own words.
    truthy("an empty range still says nothing happened", g["emptySaysNothing"])

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
