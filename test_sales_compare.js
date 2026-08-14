/* The comparison line: what Orbit's charts have that these did not.
 *
 * Reported twice: "the sales dashboard is still not same like orbit, the graphs
 * are not how orbit tool has it". The audit of Orbit's own front end
 * (orbit_full_audit.md 4.11) names what is different:
 *
 *   "Line -- today vs yesterday overlay, gold #fbbf24 for current, grey dashed
 *    for comparison"
 *   "Area -- gradient fill under line"
 *
 * A single line answers "what happened". It cannot answer "is that any good",
 * which is the question actually being asked of a sales chart -- and answering
 * it meant changing the dates and trying to remember the old shape.
 *
 * The traps this pins down are all about not lying with the second line:
 *   - both series MUST share one scale, or the crossing means nothing
 *   - a missing day in the comparison is a gap, never a zero
 *   - mismatched lengths must drop the comparison rather than pair day 5
 *     against day 6
 *   - the hover has to report BOTH, or the second line is decoration
 */
"use strict";
const fs = require("fs");
const vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }
function falsy(label, got){ check(label, !!got, false); }

const sandbox = { document: { getElementById: () => null }, console };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("D:/AltaScraper/static/js/salescharts.js", "utf8"), sandbox);

const days = ["2026-08-01","2026-08-02","2026-08-03","2026-08-04","2026-08-05"];
const now  = days.map((d, i) => ({label: d, value: [10, 20, 30, 40, 50][i]}));
const prev = days.map((d, i) => ({label: d, value: [ 8, 12, 35, 20, 25][i]}));

console.log("=== one line, as before ===");
const plain = sandbox.salesChart(now, {title: "Revenue", kind: "money", id: "t1"});
truthy("it still draws", plain.indexOf("<svg") >= 0);
falsy("no comparison line when none was given", plain.indexOf("stroke-dasharray") >= 0);
falsy("and no legend for a single series", plain.indexOf("the period before") >= 0);

console.log("\n=== two lines ===");
const both = sandbox.salesChart(now, {title: "Revenue", kind: "money", id: "t2",
                                      compare: prev});
truthy("the comparison is drawn dashed", both.indexOf("stroke-dasharray") >= 0);
// The literal values, not sandbox.SC_* -- a top-level `const` is not a property
// of the global object, so reading it back would be undefined and every colour
// check would pass against nothing.
truthy("  in neutral grey, not a second bright colour", both.indexOf("#6b7280") >= 0);
truthy("the current period is Orbit's gold", both.indexOf("#fbbf24") >= 0);
truthy("there is a legend now", both.indexOf("the period before") >= 0);
truthy("  naming this period too", both.indexOf("this period") >= 0);

console.log("\n=== the area is a gradient, not a flat wash ===");
truthy("a gradient is defined", both.indexOf("linearGradient") >= 0);
truthy("  and the area is painted with it", both.indexOf("fill=\"url(#t2_grad)\"") >= 0);
// Two charts on one page must not share one definition and therefore one colour.
const other = sandbox.salesChart(now, {title: "Units", kind: "count", id: "t3",
                                       color: "#8fd694"});
truthy("each chart has its OWN gradient id", other.indexOf("t3_grad") >= 0);
falsy("  and does not reach for another chart's", other.indexOf("t2_grad") >= 0);

console.log("\n=== both series share one scale ===");
// THE TRAP: two lines on separate scales that cross each other say something
// untrue, and the crossing is what the eye reads first. A comparison that goes
// far higher than the current period must lift the axis for BOTH.
const huge = days.map((d, i) => ({label: d, value: [800, 900, 850, 870, 880][i]}));
const scaled = sandbox.salesChart(now, {title: "Revenue", kind: "money", id: "t4",
                                        compare: huge});
// With a top of ~900 the axis labels must reach that far; a 50-max axis would
// mean the comparison was drawn off the top or on its own scale.
truthy("the axis covers the taller series", /[>\s](9|10)\d\d\.\d\d</.test(scaled)
       || scaled.indexOf("900.00") >= 0 || scaled.indexOf("1000.00") >= 0);

console.log("\n=== a gap in the comparison is a gap ===");
const holed = [{label: days[0], value: 8}, {label: days[1], value: null},
               {label: days[2], value: 35}, {label: days[3], value: null},
               {label: days[4], value: 25}];
const g = sandbox.salesChart(now, {title: "Revenue", kind: "money", id: "t5",
                                   compare: holed});
// Each unbroken run is its own path, so a comparison of 8, gap, 35, gap, 25 is
// three single points and NO line at all -- certainly not one drawn straight
// through the days that have no figure.
//
// Counted inside the chart only. The legend's own swatch is a dashed line too,
// and a test that cannot tell the key from the data would pass on the key.
const chartOnly = g.slice(g.indexOf("<svg class=\"chartbox\""));
const dashed = (chartOnly.match(/stroke-dasharray/g) || []).length;
check("the comparison is not drawn through the gaps", dashed, 0);
// And the legend is still there, so this is not passing because nothing drew.
truthy("  while the key still says what the dashes would be",
       g.indexOf("the period before") >= 0);

console.log("\n=== a mismatched comparison is dropped, not paired up ===");
const short = prev.slice(0, 3);
const mism = sandbox.salesChart(now, {title: "Revenue", kind: "money", id: "t6",
                                      compare: short});
falsy("three days are not compared against five", mism.indexOf("stroke-dasharray") >= 0);
falsy("  and no legend claims otherwise", mism.indexOf("the period before") >= 0);

console.log("\n=== the hover reports both, and the change between them ===");
truthy("the readout carries the earlier figure", both.indexOf("before:") >= 0);
truthy("  and the percentage change", both.indexOf("%)") >= 0);
// 10 against 8 is +25%; the first column must say so.
truthy("computed, not guessed", both.indexOf("+25%") >= 0);
// A previous value of zero cannot produce a percentage -- dividing by it would
// print Infinity, which is the sort of thing that ends up in a screenshot.
const zeroPrev = days.map(d => ({label: d, value: 0}));
const z = sandbox.salesChart(now, {title: "Revenue", kind: "money", id: "t7",
                                   compare: zeroPrev});
falsy("no percentage against a zero", z.indexOf("Infinity") >= 0);
truthy("  but the earlier figure is still shown", z.indexOf("before:") >= 0);

console.log("\n=== sales.js asks for the period before ===");
const SALES_JS = fs.readFileSync("D:/AltaScraper/static/js/sales.js", "utf8");
truthy("there is a loader for it", SALES_JS.indexOf("async function salesLoadCompare") >= 0);
truthy("it is not awaited with the main load, so charts draw first",
       SALES_JS.indexOf("salesLoadCompare(sum).catch") >= 0);
truthy("it carries the product filter across",
       /q\.push\("asin="/.test(SALES_JS.slice(SALES_JS.indexOf("salesLoadCompare"))));
truthy("and the marketplace",
       /marketplace=/.test(SALES_JS.slice(SALES_JS.indexOf("salesLoadCompare"))));
truthy("the comparison is matched by metric key, not by position",
       SALES_JS.indexOf("m.key === key") >= 0);
truthy("and the dates it covers are said on the chart",
       SALES_JS.indexOf("dashed line is") >= 0);

console.log("\n=== the two periods are matched BY DATE, on real reply shapes ===");
// MEASURED, and it is why this is not a length check. Asking jack_uk for 30
// days returned 28 columns for this period and 1 for the period before: the
// reply carries only the buckets that have figures. Pairing by position would
// have compared 15 June against 15 July. Requiring equal lengths -- which is
// what this originally did -- meant the comparison never drew at all.
const picker = (function(){
  const s = SALES_JS.indexOf("function salesDrawCharts");
  const e = SALES_JS.indexOf("\nasync function salesReload");
  return SALES_JS.slice(s, e);
})();

function drawWith(seriesNow, compare, offsetDays){
  let out = "";
  const fn = new Function("SC_SRC", "SER", "CMP", "OFF", `
    ${fs.readFileSync("D:/AltaScraper/static/js/salescharts.js", "utf8")}
    const _sEsc = s => String(s == null ? "" : s);
    const SALES = {preset:"30d", start:"", end:"", _zoomBack:null, _chartDates:null,
                   compare: CMP, compareOffsetDays: OFF, compareRange:"before"};
    let _html = "";
    const document = { getElementById: () => ({ set innerHTML(v){ _html = v; } }) };
    ${picker}
    salesDrawCharts(SER);
    return _html;
  `);
  return fn(null, seriesNow, compare, offsetDays);
}

// Five days now; the period before returns only the TWO days it has figures
// for -- different length, and out of step with the current columns.
const nowSer = {
  columns: ["2026-08-06","2026-08-07","2026-08-08","2026-08-09","2026-08-10"],
  metrics: [{key: "net_revenue", cells: [10, 20, 30, 40, 50]}],
};
const prevSer = {
  columns: ["2026-08-02","2026-08-04"],     // 4 and 2 days before the window
  metrics: [{key: "net_revenue", cells: [7, 9]}],
};
const drawn = drawWith(nowSer, prevSer, 5);
truthy("a comparison of different length still draws", drawn.indexOf("stroke-dasharray") >= 0);
// 6 Aug looks back to 1 Aug (absent -> gap); 7 Aug to 2 Aug -> 7; 9 Aug to
// 4 Aug -> 9. So the hover for 7 Aug must report 7, not the first cell.
truthy("each day is compared against the SAME day of the earlier period",
       drawn.indexOf("before: 7.00") >= 0);
truthy("  and the other matched day too", drawn.indexOf("before: 9.00") >= 0);
truthy("a day the earlier period has no figure for reads as a dash, not zero",
       drawn.indexOf("before: —") >= 0);

// And when nothing lines up at all -- an offset that lands between buckets --
// there must be no second line rather than a line made entirely of gaps.
const noneMatch = drawWith(nowSer, {columns: ["2025-01-01"],
                                    metrics: [{key: "net_revenue", cells: [5]}]}, 5);
const chartPart = noneMatch.slice(noneMatch.indexOf("<svg class=\"chartbox\""));
check("nothing aligned means no comparison at all",
      (chartPart.match(/stroke-dasharray/g) || []).length, 0);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
