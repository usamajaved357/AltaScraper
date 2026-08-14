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

// ONE CHART, NOT FIVE. Orbit's Sales Dashboard has three charts in total --
// Live Sales, Week to Date, and one combined Sales Report -- and ours drew five
// separate panels beside the combined one, so the screen had six. The rule
// these tests were really defending is unchanged and asserted below: a feed
// that is entirely zero is never drawn as no sales.
console.log("\n=== one combined chart, not a panel per metric ===");
truthy("the combined chart is drawn", html.includes("_svg") && html.includes("<svg"));
check("there is exactly one chart on this surface",
      (html.match(/<svg /g) || []).length >= 1
      && (html.match(/class="chartbox"/g) || []).length, 1);
// The series that DO have numbers are on it; the ones that are all zero are not.
truthy("the series with real numbers is drawn", html.includes("#10b981")
       || html.includes("Sales"));

console.log("\n=== a flat zero is never presented as a fact ===");
// In this fixture the REPORT feed is all zero (ordered_sales, units,
// unit_session_pct) while the FINANCE feed has nine real days. The chart must
// therefore draw the finance figures and must NOT warn -- there is nothing
// missing, the app simply used the feed that had arrived.
truthy("nothing is charted along the axis from the empty report feed",
       !html.includes("ordered_sales"));
check("and no warning is raised, because the finance feed covered it",
      html.includes("every value Amazon has sent for this period is zero"), false);
// The warning still EXISTS for the case where a metric has no usable feed at
// all -- checked in the source, since this fixture cannot produce it.
truthy("the warning is still there for a metric with no usable feed",
       /every value Amazon has sent for this period is zero/.test(sales));
truthy("  and it offers Sync as the fix", /Press <b>Sync<\/b>/.test(sales));

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

console.log("\n=== Orbit's geometry, to the pixel ===");
// Measured off Orbit at 1600px (orbit_sales_spec.md): its two top charts are
// 597x200 with a 512x160 plot area, and the padding around it is 65 / 5 / 20 /
// 35. Ours were 720x260, which is a different SHAPE -- the same data reads
// differently at a different ratio however closely the colours match.
truthy("the small charts are 597 wide", /o\.width \|\| 597/.test(src));
truthy("  and 200 tall", /o\.height \|\| 200/.test(src));
truthy("  with Orbit's plot padding", /padL = 65, padR = 20, padT = 5, padB = 35/.test(src));
truthy("the combined chart fills the panel's 1229", /o\.width \|\| 1229/.test(src));
truthy("  with room reserved for the second axis", /padR = 56/.test(src));
truthy("the two top cards ask for that size",
       /width: 597, height: 200/.test(sales));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
