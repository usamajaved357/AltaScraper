"""The Weekly screen says which week it is showing, and why the trend is absent.

TWO FAULTS, ONE SHAPE: the screen stayed silent where silence reads as an answer.

1. THE TWELVE-WEEK TREND REMOVED ITSELF ON EVERY ACCOUNT. _wkTrendCard returned
   "" whenever fewer than two weeks were stored, under a comment claiming it
   "said plainly" that one point is not a trend. It said nothing. Measured the
   day after it shipped: the store holds exactly one week per account --

       jack_uk        UK  2026-08-09
       nestwell_goods UK  2026-08-09

   -- so `built` was 1 everywhere, in every marketplace, and the feature could
   not be found at all. A card announced and then invisible reads as a broken
   build; the real reason is one sentence long and tells the reader what to do.

2. THE DATE BOX AND THE PACK WERE DIFFERENT WEEKS. _wkPick falls back to the
   newest stored week when the box points at one nobody built -- correct, and
   unannounced. Measured on jack_uk: the box read 2026-08-18 and every figure
   below it belonged to the week of 2026-08-09. The box defaults to seven days
   ago, which is usually a week not yet built, so this was the ORDINARY case
   rather than an edge one. Right numbers, wrong heading, no way to tell.
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
    print("  %-68s %s" % (label, "OK" if ok else
                          "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


PROBE = r"""
const fs = require("fs"), vm = require("vm");
globalThis.window = globalThis;
globalThis.addEventListener = function(){};
globalThis.WK = {week: null, weeks: [], trendMetric: "total_sales", fellBack: ""};
globalThis._wkEsc = s => String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
let BOX = "";
globalThis.document = {getElementById: id => (id === "wk_week" ? {value: BOX} : null)};

const src = fs.readFileSync("static/js/weekly.js", "utf8");
const grab = function(name){
  const i = src.indexOf("function " + name + "(");
  if(i < 0) throw new Error("missing " + name);
  let d = 0;
  for(let k = src.indexOf("{", i); k < src.length; k++){
    if(src[k] === "{") d++;
    else if(src[k] === "}"){ d--; if(!d) return src.slice(i, k + 1); }
  }
  throw new Error("unbalanced " + name);
};
// The two constants the grabbed functions close over, taken from the file
// itself rather than retyped -- a copy here could disagree with the app and the
// test would still pass.
// Sliced, not matched: this probe is a Python raw string, so a backslash class
// like \s arrives here doubled and the regex silently matches nothing.
const constOf = function(name){
  const head = "const " + name + " = ";
  const i = src.indexOf(head);
  if(i < 0) throw new Error("missing const " + name);
  const j = src.indexOf(";\n", i);
  return src.slice(i, j + 1);
};
vm.runInThisContext([constOf("WK_TREND_N"), constOf("WK_TREND"),
                     grab("_wkIso"), grab("_wkSpine"), grab("_wkTrendMetric"),
                     grab("_wkTrendVal"), grab("_wkTrendCurrencies"),
                     grab("_wkTrendCard"), grab("_wkPick")].join("\n"));

const wk = function(start, end){
  return {week_start: start, week_end: end, has_business: true,
          has_campaigns: true, currency: "GBP",
          kpis: {total_sales: 10, units: 1, sessions: 5}};
};
const out = {};

// --- 1. ONE stored week: the real state of every account today -------------
WK.weeks = [wk("2026-08-09", "2026-08-15")];
const one = _wkTrendCard();
out.oneIsNotEmpty   = one.length > 0;
out.oneNamesTheCard = /Twelve-week trend/.test(one);
out.oneSaysWhy      = /Only one week is stored/.test(one);
out.oneSaysWhatNext = /Store a second week/.test(one);
out.oneDrawsNoChart = !/wk_trendchart/.test(one);

// --- 2. NO stored weeks: the pack already says the screen is empty ---------
WK.weeks = [];
out.noneStaysSilent = _wkTrendCard();

// --- 3. TWO weeks: the real chart comes back, unchanged --------------------
WK.weeks = [wk("2026-08-09", "2026-08-15"), wk("2026-08-02", "2026-08-08")];
const two = _wkTrendCard();
out.twoDrawsTheChart = /wk_trendchart/.test(two);
out.twoHasChips      = /weeklyTrendPick/.test(two);
out.twoCountsWeeks   = /2 of 12 weeks have a pack/.test(two);
out.twoNoOneWeekNote = !/Only one week is stored/.test(two);

// --- 4. the picker: asked for a week that exists ---------------------------
WK.weeks = [wk("2026-08-09", "2026-08-15"), wk("2026-08-02", "2026-08-08")];
BOX = "2026-08-03";
const hit = _wkPick();
out.hitPicksTheAsked = hit.week_start;
out.hitSaysNothing   = WK.fellBack;

// --- 5. asked for a week nobody built -- THE ORDINARY CASE -----------------
BOX = "2026-08-18";
const miss = _wkPick();
out.missShowsNewest  = miss.week_start;
out.missRecordsAsked = WK.fellBack;

// --- 6. and it is CLEARED again, not left set for ever ---------------------
BOX = "2026-08-03";
_wkPick();
out.clearedOnNextPick = WK.fellBack;

// --- 7. an empty box is not a fallback: nothing was asked for --------------
BOX = "";
const blank = _wkPick();
out.blankShowsNewest = blank.week_start;
out.blankSaysNothing = WK.fellBack;

// --- 8. nothing stored at all is not a fallback either ---------------------
WK.weeks = []; BOX = "2026-08-18";
out.emptyStoreReturns = _wkPick();
out.emptyStoreSaysNothing = WK.fellBack;

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
        print("  FAIL weekly.js threw:", (r.stderr or "")[:500])
        raise SystemExit(1)
    g = json.loads(r.stdout.strip().splitlines()[-1])
except FileNotFoundError:
    print("  (node is not on this machine -- not exercised)")
    raise SystemExit(0)

print("=== one stored week: the card explains itself instead of vanishing ===")
truthy("it draws something", g["oneIsNotEmpty"])
truthy("  under the name it was announced by", g["oneNamesTheCard"])
truthy("  saying why there is no line yet", g["oneSaysWhy"])
truthy("  and what would produce one", g["oneSaysWhatNext"])
# A single dot on an axis looks like a chart that failed to load, which is the
# reason the card refused to draw in the first place. That judgement stands.
truthy("  without drawing a one-point chart", g["oneDrawsNoChart"])

print("\n=== no stored weeks: still silent, because the pack already says so ===")
check("nothing is added to an empty screen", g["noneStaysSilent"], "")

print("\n=== two weeks: the chart itself is unchanged ===")
truthy("the chart host is back", g["twoDrawsTheChart"])
truthy("  with its metric chips", g["twoHasChips"])
truthy("  and the count of weeks that have a pack", g["twoCountsWeeks"])
truthy("  and no leftover one-week notice", g["twoNoOneWeekNote"])

print("\n=== the week shown is the week named, or it says otherwise ===")
check("a week that exists is the one picked", g["hitPicksTheAsked"], "2026-08-02")
check("  and nothing is announced", g["hitSaysNothing"], "")
check("a week nobody built falls back to the newest", g["missShowsNewest"],
      "2026-08-09")
check("  and the week that was asked for is recorded", g["missRecordsAsked"],
      "2026-08-18")
# Set-only would caption every later week as a fallback, which is a new way of
# saying something untrue.
check("the notice clears on the next pick", g["clearedOnNextPick"], "")
check("an empty date box is not a fallback", g["blankShowsNewest"], "2026-08-09")
check("  because nothing was asked for", g["blankSaysNothing"], "")
check("with nothing stored there is nothing to fall back to",
      g["emptyStoreReturns"], None)
check("  so nothing is claimed", g["emptyStoreSaysNothing"], "")

print("\n=== and the render actually shows it ===")
JS = open("static/js/weekly.js", encoding="utf-8").read()
truthy("the render reads the flag", "if(WK.fellBack){" in JS)
truthy("  names the week that was asked for", "No pack for the week of" in JS)
truthy("  and the week being shown instead",
       "_wkEsc(w.week_start)" in JS.split("if(WK.fellBack){")[1][:700])
# Above every figure, not below them: a reader who scrolls past it has already
# read the numbers under the wrong heading.
_i_note = JS.find("if(WK.fellBack){")
_i_half = JS.find("Half a pack.")
truthy("  before any figure on the page", 0 < _i_note < _i_half)
truthy("the field exists on WK from the start", "fellBack: \"\"" in JS)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
