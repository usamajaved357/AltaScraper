"""A sparse line must still look like a measurement.

    "check the profit lines on the graph of daily sales, that is not how the
     lines are drawn in other places"

WHAT WAS MEASURED in a real browser on the Sales Report chart (jack_uk, 30 days):

    #10b981  Sales           1 path, 2px, solid, gradient fill
    #38bdf8  Profit          4 paths, ALL 1.2px, dash 3,4, opacity 0.55
                             ...and not one solid segment anywhere
    markers                  5 circles at r 2.6

Profit is known only on days where every unit shipped has a cost recorded --
five days out of thirty here, none of them adjacent. So every "run" is a single
point, a single point draws no stroke, and the only blue on the chart was the
dashed bridge BETWEEN the measured days. Beside Sales -- a confident 2px line
with a gradient under it -- the series read as faint and provisional, when those
five points are as measured as any point on the green line.

THE DASHES ARE RIGHT AND STAY. The app does not know what the profit was on the
days in between, and drawing a solid line through them would claim it did. Two
things were wrong, and neither is the dash:

  the measured days looked like nothing   A 2.6px dot in the series colour sits
                                          on a grid of 1px lines and reads as
                                          grid. A lone point is the WHOLE
                                          measurement for that day and now gets
                                          a ring in its own colour.

  the key promised a line that was never  The swatch drew a solid 2px stroke,
  drawn                                   exactly like Sales's. The key and the
                                          chart disagreed and the key was wrong.
                                          It now shows the bridge-and-point that
                                          is actually on the chart, and says on
                                          how many days the series was known.

ONE implementation for the marker. Both charts on this screen had their own copy
of the same `r="2.6"` circle -- which is how only one of them would ever have
been fixed (rule 12).
"""
import io
import json
import os
import re
import subprocess
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


def falsy(label, got):
    check(label, bool(got), False)


def read(*p):
    return io.open(os.path.join(HERE, *p), encoding="utf-8").read()


S = read("static", "js", "salescharts.js")
CODE = "\n".join(l.split("//")[0] for l in S.splitlines()
                 if not l.strip().startswith(("*", "/*", "//")))

print("== one marker, used by both charts ==")
truthy("there is a helper for a run of one", "function _scLonePoint(" in CODE)
check("  and both charts call it", CODE.count("_scLonePoint("), 3)  # 1 def + 2 uses
falsy("no chart draws its own bare dot any more", 'r="2.6" fill="${' in CODE)
truthy("the marker carries a ring", 'r="6"' in CODE and 'opacity="0.18"' in CODE)
# A single-line fragment: the sentence wraps, and matching across the break is
# how these assertions keep failing on correct code.
truthy("  in the series' own colour, not the background's",
       "a halo painted in the panel" in S)

print("\n== the dashed bridge is unchanged ==")
_gj = CODE.split("function _scGapJoin")[1].split("\nfunction ")[0]
truthy("still 1.2px", 'stroke-width="1.2"' in _gj)
truthy("  still dashed", 'stroke-dasharray="3,4"' in _gj)
truthy("  still faded", 'opacity="0.55"' in _gj)
truthy("and why a solid line would be a lie is still recorded",
       "not known that it did" in S)

print("\n== the key shows what was drawn ==")
truthy("each series' shape is recorded while drawing", "const shape = {}" in CODE)
truthy("  how many points", "points:" in CODE)
truthy("  out of how many days", "days:" in CODE)
truthy("  and whether anything solid exists",
       "solid: runs.some(" in CODE)
truthy("the swatch branches on it", "const sparse = sh.points > 0 && !sh.solid" in CODE)
truthy("  a sparse swatch is the bridge and a point",
       'stroke-dasharray="3,4" opacity="0.55"' in CODE.split("const sparse")[1][:600]
       and "<circle" in CODE.split("const sparse")[1][:600])
truthy("  and the label says how sparse",
       "' of ' + sh.days + ' days'" in CODE)
falsy("the label is plain text, not markup",
      "<span" in CODE.split("const label = (spec.label")[1][:300])
truthy("  and why is recorded", "item() escapes the label" in S)

print("\n== the drawing rules themselves ==")
probe = r"""
const fs=require("fs"),vm=require("vm");
globalThis.document={getElementById:()=>null,querySelectorAll:()=>[],
  createElement:()=>({}),addEventListener(){},body:{}};
globalThis.window=globalThis; globalThis.addEventListener=()=>{};
globalThis.localStorage={getItem:()=>null,setItem(){},removeItem(){}};
vm.runInThisContext(fs.readFileSync("static/js/salescharts.js","utf8"),{filename:"sc.js"});
const m = _scLonePoint(10, 20, "#38bdf8");
const circles = (m.match(/<circle/g)||[]).length;
const radii = [...m.matchAll(/r="([\d.]+)"/g)].map(x=>Number(x[1]));
// A gap join between two runs, and none for a single run.
const x = i => i*10, y = v => 100-v;
const one  = _scGapJoin([[{i:0,v:1}]], x, y, "#38bdf8");
const two  = _scGapJoin([[{i:0,v:1}],[{i:5,v:9}]], x, y, "#38bdf8");
const four = _scGapJoin([[{i:0,v:1}],[{i:5,v:9}],[{i:9,v:3}],[{i:12,v:4}]], x, y, "#38bdf8");
console.log(JSON.stringify({
  circles, radii,
  ringBiggerThanDot: Math.max(...radii) > Math.min(...radii),
  colourUsed: (m.match(/#38bdf8/g)||[]).length,
  bridges1: (one.match(/<path/g)||[]).length,
  bridges2: (two.match(/<path/g)||[]).length,
  bridges4: (four.match(/<path/g)||[]).length,
  bridgeIsFaint: /opacity="0.55"/.test(two) && /stroke-width="1.2"/.test(two),
  bridgeIsDashed: /stroke-dasharray="3,4"/.test(two),
  emptyRuns: _scGapJoin([], x, y, "#000") === "",
  // A run that is missing an endpoint must not throw or draw nonsense.
  ragged: _scGapJoin([[],[{i:2,v:3}]], x, y, "#000"),
}));
"""
try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run(["node", path], capture_output=True, text=True, cwd=HERE,
                         timeout=120)
    os.unlink(path)
    if out.returncode != 0:
        fails.append("salescharts.js threw")
        print("  FAIL:", (out.stderr or "")[:400])
    else:
        g = json.loads(out.stdout.strip().splitlines()[-1])
        check("a lone point is a ring and a dot", g["circles"], 2)
        truthy("  the ring is the bigger of the two", g["ringBiggerThanDot"])
        check("  both in the series colour", g["colourUsed"], 2)
        check("one run needs no bridge", g["bridges1"], 0)
        check("two runs get one", g["bridges2"], 1)
        check("four runs get three", g["bridges4"], 3)
        truthy("  thin and faded", g["bridgeIsFaint"])
        truthy("  and dashed", g["bridgeIsDashed"])
        truthy("nothing to join draws nothing", g["emptyRuns"])
        check("an empty run is skipped, not drawn as NaN", g["ragged"], "")
except FileNotFoundError:
    print("  (node not on this machine -- not exercised)")
except Exception as e:
    fails.append("drawing probe")
    print("  FAIL drawing probe:", str(e)[:250])

print("\n== and why the profit line is sparse in the first place ==")
# Not a drawing fault: 5 of 47 SKUs have no cost, so profit is only known on
# days where every unit shipped was costed. The screen says so already, and this
# checks that it still does -- the line stops being sparse when the costs are in.
truthy("the Sales screen explains the missing costs",
       "no cost" in read("static", "js", "sales.js"))
try:
    from domain import sales_data as _sd
    import datetime as _dt
    end = _dt.date.today() - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=29)
    rows = _sd.series("config.json", "jack_uk", "UK", start.isoformat(),
                      end.isoformat(), basis="order")
    known = sum(1 for r in rows if r.get("profit") is not None)
    print("     jack_uk: profit known on %d of %d days in the window"
          % (known, len(rows)))
    truthy("  which is why it draws as points rather than a line",
           known < len(rows))
except Exception as e:
    print("  (could not read the window: %s)" % str(e)[:120])

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
