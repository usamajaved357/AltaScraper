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
truthy("  and every drawn chart carries a viewBox", html.includes("viewBox="));
// AND IT NO LONGER SCALES UNIFORMLY EITHER, which was the other way to get the
// wrong picture. `height:auto` meant halving the width halved the height:
// measured, a 340px phone drew a 340x102 chart where Orbit draws 340x200.
// Orbit holds the height at every width -- 665x200 on desktop, 340x200 on a
// phone -- so the height is now fixed in pixels and the width comes from the
// container. See scChartWidth.
truthy("the height is fixed in pixels, not scaled with the width",
       /height:\d+px/.test(html));
check("  and never left to scale itself", html.includes("height:auto"), false);

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

console.log("\n=== the lines are CURVES, as Orbit's are ===");
// Measured off Orbit's live chart: every one of its paths is made of `C`
// commands -- cubic beziers -- and contains not a single `L`. Ours joined the
// points with straight segments, and that was the difference that survived
// every colour, size and spacing fix. The same numbers drawn as a polyline do
// not read like the same chart.
{
  // Same style as the rest of this file: the real source, run in a function
  // whose return value is what the chart produced.
  const mk = new Function("PTS", "CMP", `
    ${src}
    const document = { getElementById: () => null };
    return {html: salesChart(PTS, {title:"R", kind:"money", id:"curvetest",
                                   compare: CMP}),
            curve: _scCurve};
  `);
  const days = ["2026-08-01","2026-08-02","2026-08-03","2026-08-04","2026-08-05"];
  const pts = days.map((d, i) => ({label: d, value: [10, 45, 20, 60, 35][i]}));
  const res = mk(pts, days.map((d, i) => ({label: d, value: [8, 30, 25, 40, 30][i]})));
  const out = res.html;
  const paths = [...out.matchAll(/<path[^>]*d="([^"]+)"/g)].map(m => m[1]);
  truthy("paths were drawn", paths.length >= 2);
  const curves = paths.reduce((a, d) => a + (d.match(/C/g) || []).length, 0);
  truthy("they are made of cubic beziers", curves > 0);
  // The ONLY L commands allowed are the two that drop the area fill to the
  // axis and close it -- which is exactly what Orbit's area path does too.
  const lines = paths.reduce((a, d) => a + (d.match(/L/g) || []).length, 0);
  check("and no line is drawn as straight segments", lines <= 2, true);

  // MONOTONE, not merely smooth. An ordinary spline overshoots between points,
  // so a flat run followed by a drop would bulge past the values on either
  // side -- on a sales chart, drawing money that was never taken.
  const curve = res.curve;
  const d2 = curve([{x:0,y:100},{x:10,y:100},{x:20,y:100},{x:30,y:10}]);
  const ys = [...d2.matchAll(/[-\d.]+,([-\d.]+)/g)].map(m => parseFloat(m[1]));
  truthy("the curve never leaves the range of the points it joins",
         ys.every(y => y >= 10 - 0.01 && y <= 100 + 0.01));
  // Two points cannot have a tangent; a straight join is correct there.
  truthy("two points are joined without inventing a curve",
         curve([{x:0,y:0},{x:10,y:10}]).indexOf("L") >= 0);
  check("and one point draws no line at all",
        curve([{x:0,y:0}]).indexOf("C") >= 0, false);
}

console.log("\n=== Orbit's geometry, to the pixel ===");
// RE-MEASURED off the live dashboard at 1600px on 15 Aug 2026, from the drawn
// SVG rather than from the panel around it:
//   top cards      viewBox 665 x 200, gridlines at y = 165/125/85/45/5
//   Sales Report   viewBox 1365 x 320, plot x 70 -> 1274.9, y 10 -> 254
// The earlier 597 and 1229 came from a narrower scan. Ratio is what decides
// whether the same numbers read as the same shape, so these are load-bearing.
truthy("the small charts are 665 wide", /o\.width \|\| 665/.test(src));
truthy("  and 200 tall", /o\.height \|\| 200/.test(src));
truthy("  with Orbit's plot padding", /padL = 65, padR = 20, padT = 5, padB = 35/.test(src));
truthy("the combined chart is Orbit's 1365 x 320", /o\.width \|\| 1365/.test(src)
       && /o\.height \|\| 320/.test(src));
// `barsOn`, not `o.bars`: the key can now switch the Orders bars off, and the
// 70px strip reserved for their count axis has to go back to the plot when they
// do -- otherwise hiding the bars leaves a blank margin and a narrower chart.
// Same value as before whenever nothing is hidden, which is the default.
truthy("  with room reserved for the second axis, but only when it has one",
       /padR = \(barsOn \? 90 : 20\)/.test(src));
// The two top cards no longer hard-code a width: they measure their own card,
// with Orbit's 665 as the fallback, and hold Orbit's 200px height.
// Four matches, not two: each card measures once when it draws and once more in
// the closure that redraws it after a resize.
truthy("both top cards measure their own card rather than assuming a width",
       (sales.match(/scChartWidth\("sales_(week|hourly)", 665\)/g) || []).length >= 2);
truthy("  and each leaves a way to redraw itself at a new width",
       /SALES\._weekDraw/.test(sales) && /SALES\._hourlyDraw/.test(sales));
truthy("a resize redraws rather than refetches",
       /addEventListener\("resize", salesOnResize\)/.test(sales)
       && !/salesLoadWeek\(\)/.test(sales.slice(sales.indexOf("function salesOnResize"),
                                                sales.indexOf("function salesOnResize") + 900)));
truthy("  and only when the WIDTH changed, so a phone's address bar cannot flicker it",
       /if\(w === _sLastW\) return;/.test(sales));
check("  and both hold Orbit's 200px height",
      (sales.match(/height: 200, compare: cmp/g) || []).length, 2);
truthy("the Sales Report asks for Orbit's 320",
       /scChartWidth\("sales_charts", 1365\), height: 320/.test(sales));
truthy("and Organic vs PPC for Orbit's 380",
       /scChartWidth\("sales_orgppc", 1365\), height: 380/.test(sales));

console.log("\n=== a narrow screen loses width, not height ===");
// "in the mobile view the graphs do not look as original they are too short".
// MEASURED on Orbit at 390px: every chart keeps its height and only the width
// changes -- Live Sales 340x200, Sales Report 340x320, Organic vs PPC 332x380.
{
  const mk = new Function("W", "PTS", `
    ${src}
    const document = { getElementById: () => null };
    return salesChart(PTS, {kind:"money", id:"narrow", width:W, height:200,
                            compact:true, scale:"band"});
  `);
  const days = ["2026-08-09","2026-08-10","2026-08-11","2026-08-12"];
  const pts = days.map((d, i) => ({label: d, value: 10 + i}));
  const phone = mk(340, pts), desktop = mk(665, pts);
  truthy("the phone chart is drawn at the phone's width",
         phone.includes('viewBox="0 0 340 200"'));
  truthy("  and the desktop one at the desktop's",
         desktop.includes('viewBox="0 0 665 200"'));
  check("both are exactly 200 tall",
        [/height:200px/.test(phone), /height:200px/.test(desktop)], [true, true]);
  // The plot has to re-lay-out narrower, not shrink: the right-hand edge of the
  // plot moves in, the axis padding does not.
  const rightOf = h => {
    const m = [...h.matchAll(/<line x1="65" y1="[\d.]+" x2="(\d+)"/g)].map(x => +x[1]);
    return m.length ? m[0] : null;
  };
  check("the gridlines stop at the phone's plot edge", rightOf(phone), 320);
  check("  and at the desktop's", rightOf(desktop), 645);
  // Below 240 there is no room for an axis and dates, so the fallback is used
  // rather than a squashed picture.
  const tiny = new Function(`
    ${src}
    const document = { getElementById: () => ({clientWidth: 120}) };
    return scChartWidth("x", 665);
  `)();
  check("a container too narrow to draw in falls back", tiny, 665);
  const measured = new Function(`
    ${src}
    const document = { getElementById: () => ({clientWidth: 341}) };
    return scChartWidth("x", 665);
  `)();
  check("and a real width is used as measured", measured, 341);
}

console.log("\n=== a count axis has whole numbers on it ===");
// THE BUG: "where i have 1 order the pillar rise upto 50 on y axis". The bars
// were scaled by _scNiceMax, which returns 1 for a peak of 1 -- so a single
// order drew a FULL-HEIGHT pillar, every day with one order drew an identical
// full-height pillar (which is what "the pillars are hardcoded" looks like),
// and the five ticks rounded to 0, 0, 1, 1, 1.
{
  const nice = new Function(`${src}; return {count: _scNiceCount, max: _scNiceMax};`)();
  check("one order does not fill the chart", nice.count(1), 4);
  check("  nor do two", nice.count(2), 4);
  check("five orders get a 0-2-4-6-8 axis", nice.count(5), 8);
  check("and Orbit's own peak gives Orbit's own axis", nice.count(106), 160);
  // Every tick must be a whole number of orders at every scale, because half an
  // order does not exist. This is the property the old code broke.
  let bad = [];
  for(let peak = 1; peak <= 500; peak++){
    const top = nice.count(peak);
    [0, 0.25, 0.5, 0.75, 1].forEach(f => {
      if(Math.abs(top * f - Math.round(top * f)) > 1e-9) bad.push(peak);
    });
    if(top < peak) bad.push("too low at " + peak);
  }
  check("no peak from 1 to 500 produces a fractional tick", bad.slice(0, 5), []);
  check("the old money scale is untouched -- it still may be fractional",
        nice.max(1), 1);
}

console.log("\n=== the last pillar is not written on ===");
// THE OTHER HALF: "i see numbers written on the last one orange pillar". The
// columns were spread edge to edge, so the last one sat ON the right-hand plot
// edge and half a 32-wide bar hung into the strip the orders axis is drawn in.
// Orbit uses a band scale -- measured: bar centre, line point and date label all
// meet at 90.08, half a 40.17 band in from a plot that starts at 70.
{
  const mk = new Function("COLS", "VALS", `
    ${src}
    const document = { getElementById: () => null };
    return salesCombo({id:"bandtest", columns: COLS, bars:{label:"Orders", values:VALS},
                       lines:[{key:"sales", values: VALS.map(v => v*10)}]});
  `);
  const cols = [];
  for(let i = 0; i < 30; i++) cols.push("2026-07-" + String(15 + i).padStart(2, "0"));
  const out = mk(cols, cols.map((_, i) => 100 + i));
  const bars = [...out.matchAll(/class="bar" d="M([\d.]+),/g)].map(m => parseFloat(m[1]));
  check("thirty days draw thirty bars", bars.length, 30);
  const W = 1365, padL = 70, padR = 90;
  const slot = (W - padL - padR) / 30;
  truthy("the first bar starts inside the plot, not on its edge", bars[0] > padL);
  // The right-hand labels are drawn at W - padR + 8. Nothing may reach them.
  const lastRight = bars[bars.length - 1] + Math.min(32, slot * 0.8);
  truthy("and the last bar ends clear of the count axis", lastRight <= W - padR + 0.5);
  // Bar centre and line point must coincide, or the picture lies about which
  // day it is describing.
  const firstLine = parseFloat((/<path class="series" d="M([\d.]+),/.exec(out) || [])[1]);
  const firstCentre = bars[0] + Math.min(32, slot * 0.8) / 2;
  truthy("the line's first point sits over the first bar",
         Math.abs(firstLine - firstCentre) < 0.6);
  // Every day labelled, as Orbit labels all thirty of its.
  const labels = (out.match(/text-anchor="middle" font-size="11"/g) || []).length;
  check("all thirty days are labelled", labels, 30);
  truthy("the bars are Orbit's gold at Orbit's opacity",
         out.includes('fill="#fbbf24" opacity="0.3"'));
  truthy("  with only the top corners rounded", /A4,4,0,0,1/.test(out.replace(/\s/g, "")));
}

console.log("\n=== the week chart names its days ===");
// "week to date looks nothing like orbit". Measured: Orbit's Week to Date reads
// Sun, Mon, Tue, Wed, Thu, Fri, Sat -- seven labels at band centres. Ours read
// "Aug 9 … Aug 15" spread edge to edge.
{
  const mk = new Function("PTS", `
    ${src}
    const document = { getElementById: () => null };
    return salesChart(PTS, {kind:"money", id:"wtd", width:665, height:200,
                            scale:"band", xLabel:"dow"});
  `);
  // 2026-08-09 is a Sunday.
  const days = ["2026-08-09","2026-08-10","2026-08-11","2026-08-12",
                "2026-08-13","2026-08-14","2026-08-15"];
  const out = mk(days.map((d, i) => ({label: d, value: 10 + i})));
  const texts = [...out.matchAll(/fill="rgb\(156,163,175\)">([A-Za-z]{3})</g)].map(m => m[1]);
  check("the week reads as days of the week", texts,
        ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]);
  // At band centres, so the first label is not half-clipped by the y-axis.
  const xs = [...out.matchAll(/<text x="([\d.]+)" y="173"/g)].map(m => parseFloat(m[1]));
  check("seven of them", xs.length, 7);
  truthy("the first sits half a band in from the axis", Math.abs(xs[0] - 106.43) < 0.5);
  truthy("and the last half a band in from the right", Math.abs(xs[6] - 603.57) < 0.5);
  truthy("the gridlines are Orbit's dashed rule",
         out.includes('stroke="rgb(55,65,81)" stroke-width="1" stroke-dasharray="3 3"'));
  truthy("  and the tick text its 11px grey",
         out.includes('font-size="11"') && out.includes('fill="rgb(156,163,175)"'));
}

console.log("\n=== which lines are shaded is a fact about each line ===");
// Measured: Sales is an AREA (gradient 0.30), Prior Year is an AREA too though
// dashed (0.15), Profit is a LINE with no fill at all. Ours filled under
// anything solid, which shaded Profit and left Prior Year flat -- the opposite
// of Orbit on both counts.
{
  const spec = new Function(`${src}; return SC_SERIES;`)();
  check("Sales is filled", spec.sales.fill, 0.30);
  check("Prior Year is filled at half strength, dash and all", spec.prior_year.fill, 0.15);
  check("  and it really is the dashed one", spec.prior_year.dash, "5 3");
  check("Profit is not filled", spec.profit.fill, 0);
  check("  and it is solid, not dashed", spec.profit.dash, "");
}

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
