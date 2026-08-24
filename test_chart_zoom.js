/* Drag across a chart to zoom into those days -- the Keepa gesture.
 *
 *   "if a user wants to select a custom date range, can you make it able to
 *    click and drag the area of the graph which he wants to be zoom in version,
 *    like we have the option in keepa"
 *
 * The gesture already existed on the Sales screen. But salesChart() is SHARED --
 * Sales, Traffic and AI spend all draw with it -- so every chart it drew got the
 * drag hit-targets, and _scDragEnd sent all of them to salesZoomTo(). That had
 * two consequences, both silent:
 *
 *   Dragging a TRAFFIC chart read its column numbers as offsets into the SALES
 *   screen's dates and reloaded a screen you were not looking at.
 *
 *   Dragging the TODAY chart -- twenty-four HOURS -- zoomed the whole screen to
 *   the 9th through 14th DAY of the range. A feature appearing to work.
 *
 * A chart now names its own handler and only zooms if it named one. This file
 * is the guard: opt in, never a fallback, and never promise the gesture on a
 * chart that has not opted in.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const CHARTS = read("static/js/salescharts.js");
const SALES = read("static/js/sales.js");
const TRAF = read("static/js/traffic.js");
const AIU = read("static/js/aiusage.js");

console.log("== a chart zooms only if it named a handler ==");
truthy("there is a per-chart registry", /const _SC_ZOOM\s*=\s*\{\}/.test(CHARTS));
truthy("  charts register through one function", /function scZoomTarget\(/.test(CHARTS));
truthy("  and both chart builders call it",
       (CHARTS.match(/scZoomTarget\(cid0, o\.onZoom\)/g) || []).length === 2);
// THE FALLBACK IS THE BUG. Left in, every chart in the app zooms the Sales
// screen, which is right for two of them and wrong for the rest.
const dragEnd = /function _scDragEnd\([\s\S]*?\n\}/.exec(CHARTS);
truthy("_scDragEnd exists", !!dragEnd);
check("  and has no salesZoomTo fallback",
      /salesZoomTo/.test(dragEnd ? dragEnd[0] : ""), false);
truthy("  it resolves the handler by name",
       /_SC_ZOOM\[cid\]/.test(dragEnd ? dragEnd[0] : ""));

console.log("\n== the charts that CAN zoom, do ==");
truthy("the Sales combined chart opts in",
       /id: "sales_combo", onZoom: "salesZoomTo"/.test(SALES));
truthy("  so does Organic vs PPC, which shares its columns",
       /id: "orgppc", onZoom: "salesZoomTo"/.test(SALES));
for(const id of ["traf_overview", "traf_perf", "traf_channel", "traf_trend"]){
  truthy("traffic " + id + " zooms the TRAFFIC screen",
         new RegExp('id: "' + id + '", onZoom: "trafficZoomTo"').test(TRAF));
}
truthy("AI spend zooms the AI SPEND screen",
       /id: "aiu_daily", onZoom: "aiZoomTo"/.test(AIU));

console.log("\n== the charts that CANNOT zoom, do not ==");
// Their columns are not the screen's dates: seven days of its own, and hours.
for(const bad of ["sales_week", "sales_hourly_chart"]){
  const near = SALES.split(bad)[1] || "";
  check("  " + bad + " names no zoom handler",
        /onZoom/.test(near.slice(0, 400)), false);
}

console.log("\n== every named handler is a function that exists ==");
const ALL = CHARTS + SALES + TRAF + AIU;
const named = [...ALL.matchAll(/onZoom:\s*"([A-Za-z0-9_]+)"/g)].map(m => m[1]);
truthy("some charts opt in at all", named.length >= 6);
const missing = [...new Set(named)].filter(
  fn => !new RegExp("function\\s+" + fn + "\\s*\\(").test(ALL));
check("  and none of them is a typo", missing, []);

console.log("\n== each zoom handler reads ITS OWN screen's dates ==");
// The whole bug in one line: a handler that reads another screen's dates.
const bodies = {
  salesZoomTo: /function salesZoomTo\([\s\S]*?\n\}/.exec(SALES),
  trafficZoomTo: /function trafficZoomTo\([\s\S]*?\n\}/.exec(TRAF),
  aiZoomTo: /function aiZoomTo\([\s\S]*?\n\}/.exec(AIU),
};
truthy("sales reads SALES._chartDates",
       /SALES\._chartDates/.test(bodies.salesZoomTo[0]));
truthy("traffic reads TRAF.data.dates",
       /TRAF\.data \|\| \{\}\)\.dates/.test(bodies.trafficZoomTo[0]));
check("  and never SALES", /SALES\./.test(bodies.trafficZoomTo[0]), false);
truthy("ai spend reads AIU._chartDates",
       /AIU\._chartDates/.test(bodies.aiZoomTo[0]));
check("  and never SALES", /SALES\./.test(bodies.aiZoomTo[0]), false);

console.log("\n== a zoom can be undone, and a preset ends it ==");
for(const [fn, src] of [["salesZoomOut", SALES], ["trafficZoomOut", TRAF],
                        ["aiZoomOut", AIU]]){
  truthy("there is a way back out: " + fn,
         new RegExp("function\\s+" + fn + "\\s*\\(").test(src));
}
truthy("picking a traffic preset clears the zoom",
       /function trafficSetPreset\([\s\S]*?_zoomBack = null/.test(TRAF));
truthy("picking an AI-spend window clears it too",
       /function aiUsageSetDays\([\s\S]*?_zoomBack = null/.test(AIU));

console.log("\n== the footer only promises what the chart can do ==");
// It used to print "drag across to zoom into those days" under EVERY chart,
// including the ones where dragging moved nothing you could see.
// THE CONDITION, NOT THE NOUN. This used to pin the literal "...into those
// days", which went red the moment the bucket's name became a parameter --
// correctly, because these charts are drawn over days, weeks and months and the
// hint said "days" for all three. What the assertion is actually about is that
// the promise only appears when a zoom handler was named, so that is what it
// tests now.
truthy("the line chart's hint is conditional",
       /o\.onZoom \? ' · drag across to zoom into those '/.test(CHARTS));
truthy("  and names the bucket rather than always saying days",
       /drag across to zoom into those ' \+ _scEsc\(units\)/.test(CHARTS));
truthy("the combo chart's hint is conditional",
       /o\.onZoom \? ' · drag across to zoom' : ''/.test(CHARTS));

console.log("\n== the dragged range is actually SENT to the server ==");
truthy("traffic sends preset=custom with dates",
       /TRAF\.preset === "custom" && TRAF\.start && TRAF\.end/.test(TRAF));
truthy("ai spend sends start and end instead of days",
       /AIU\.start && AIU\.end[\s\S]{0,140}start=/.test(AIU));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
