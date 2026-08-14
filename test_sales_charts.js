// The sales charts, run against the series Amazon actually returned.
//
// The bug this exists to stop: the four charts were pinned to the Sales &
// Traffic report's columns, and that report lags the finance records by days.
// Measured on jack_uk -- nine days of real sales in the finance records, three
// days in the report, every one of them zero. So three of the four charts drew
// a confident flat line along the axis for an account that was selling 15 units
// for GBP 370. A flat zero is not neutral: it reads as "sales collapsed".
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                    + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }

// Load the two real files into one scope, as the browser does.
const src = fs.readFileSync(path.join(ROOT, "static/js/salescharts.js"), "utf8");
const sales = fs.readFileSync(path.join(ROOT, "static/js/sales.js"), "utf8");

// Only the chart-picking function is needed from sales.js; the rest reaches for
// the DOM at load time. Pulled out by name so it stays the SHIPPED code.
const start = sales.indexOf("function salesDrawCharts");
const end = sales.indexOf("\nasync function salesReload");
if (start < 0 || end < 0) { console.log("could not find salesDrawCharts"); process.exit(1); }
const picker = sales.slice(start, end);

let captured = [];
const harness = `
  ${src}
  const _sEsc = s => String(s == null ? "" : s);
  // The chart picker records the columns it drew (so a drag can turn two
  // positions back into two dates) and reads the zoom state, so the harness
  // needs the same global the page has.
  const SALES = {preset:"30d", start:"", end:"", _zoomBack:null, _chartDates:null};
  let _html = "";
  const document = { getElementById: () => ({ set innerHTML(v){ _html = v; } }) };
  ${picker}
  salesDrawCharts(SER);
  return {html: _html, dates: SALES._chartDates};
`;

// The real response, saved from the live account.
const fixturePath = path.join(ROOT, "test_fixtures_sales_series.json");
const SER = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

const _out = new Function("SER", harness)(SER);
const html = _out.html;

console.log("=== the charts drawn from real data ===");
const titles = [...html.matchAll(/font-weight:600">([A-Za-z ]+)<\/div>/g)].map(m => m[1]);
console.log("  drawn: " + JSON.stringify(titles));

// The metrics that are all zero in this fixture, and the ones that are not.
const by = {};
(SER.metrics || []).forEach(m => { by[m.key] = m.cells; });
const allZero = k => (by[k] || []).filter(v => v !== null).every(v => Number(v) === 0);
truthy("the fixture really does have an all-zero ordered_sales", allZero("ordered_sales"));
truthy("  and an all-zero units", allZero("units"));
truthy("  while net_revenue genuinely has numbers", !allZero("net_revenue"));

check("Revenue is drawn -- from the feed that has data", titles.includes("Revenue"), true);
check("Units is drawn", titles.includes("Units"), true);
check("Profit is drawn", titles.includes("Profit"), true);
check("Conversion is NOT drawn: every value Amazon sent is zero",
      titles.includes("Conversion"), false);

console.log("\n=== a flat zero is never presented as a fact ===");
truthy("the skipped ones are named, not silently missing",
       html.includes("Not drawn:") && html.includes("Conversion"));
truthy("  and the reason is given in words",
       html.includes("every value Amazon has sent for this period is zero"));

console.log("\n=== every chart says which Amazon feed it came from ===");
truthy("Revenue names its source", html.includes("from the finance records"));
truthy("  and reports that the other feed disagrees",
       html.includes("Sales &amp; Traffic report shows zero for the same period")
       || html.includes("Sales & Traffic report shows zero for the same period"));

console.log("\n=== the axis text is not stretched ===");
// preserveAspectRatio="none" mapped the viewBox to the container width while
// leaving the vertical scale at 1, so every label was smeared or squashed by
// however wide the panel was, and the stroke thickened in one direction only.
// Asserted against the RENDERED output, not the source -- the source also
// contains the string in the comment explaining why it is gone.
truthy("no chart distorts its own coordinate system",
       !html.includes('preserveAspectRatio="none"'));
truthy("  they scale uniformly instead", html.includes("height:auto"));
truthy("  and every drawn chart carries a viewBox", html.includes("viewBox="));

console.log("\n=== hover actually reports something ===");
// The hit targets carried a <title>, which is the browser's own tooltip: about a
// second to appear, gone the moment the pointer moves, unstyleable, and absent
// entirely on a touch screen. "Nothing comes up when I hover" was accurate.
truthy("hovering calls a handler rather than relying on a native tooltip",
       html.includes("onmousemove=\"_scHover("));
check("  and no chart still leans on <title> for its readout",
      /<title>/.test(html), false);
truthy("there is a readout element to write into", html.includes("_read"));
truthy("  a marker line", html.includes("_vl"));
truthy("  and a dot on the point", html.includes("_dot"));

console.log("\n=== drag across to zoom, the Keepa gesture ===");
truthy("a press starts a range", html.includes("onmousedown=\"_scDragStart("));
truthy("  releasing ends it", html.includes("onmouseup=\"_scDragEnd("));
truthy("  and the range shades while being chosen", html.includes("_sel"));
truthy("the chart tells you the gesture exists",
       html.includes("drag across to zoom"));
truthy("sales.js turns two columns back into two dates",
       /function salesZoomTo/.test(sales));
truthy("  keeping the columns it drew so it can", /_chartDates/.test(sales));
// A zoom with no way out is a trap: the only route back would be remembering
// what the range used to be.
truthy("  and there is a way back out", /function salesZoomOut/.test(sales));
truthy("  which is offered on screen, not just in the date boxes",
       /Back to the full range/.test(sales));
check("a click is not a drag -- one column zooms to nothing",
      /if\(b - a < 1\) return;/.test(src), true);

console.log("\n=== big enough to read a shape off ===");
truthy("the charts are taller than they were", /o\.height \|\| 260/.test(src));
truthy("  and laid out two across rather than four",
       /minmax\(460px,1fr\)/.test(sales));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
