// Clicking the chart key to hide a line.
//
// "the graph shows orders prior year sales profit and sales under the graph and
//  user is able to click them to enable those options, they are enabled by
//  default and user can hide the lines by again clicking on them"
//
// This RUNS salesCombo rather than reading it, because every failure worth
// catching here is a behaviour: a hidden series that still draws, a key that
// drops the item you just switched off so you cannot switch it back, an axis
// that ignores what is visible, and a redraw that nests a second chart inside
// the first. None of those are visible in the source text.
//
// The live click-through against a real browser is probe_sales_legend.py -- it
// found nothing this could not, but it is what proves the handler is reachable.

const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = [];
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(70) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

// ---- load the chart module ------------------------------------------------
// It is a browser script, not a node module. Run it in a context with just
// enough of a window for the pieces under test; anything that reaches for a
// real element is not what is being tested here.
const src = fs.readFileSync(path.join("static", "js", "salescharts.js"), "utf8");
const sandbox = {
  console: console,
  document: {
    // The redraw path asks for the wrapper. Returning null makes
    // scToggleSeries flip the flag and stop, which is exactly the seam this
    // test wants: the state change without a DOM.
    getElementById: function () { return null; },
    querySelectorAll: function () { return []; },
  },
  window: {},
  setTimeout: function (fn) { return 0; },      // never fire: no DOM to arm
  matchMedia: undefined,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
try {
  vm.runInContext(src, sandbox, { filename: "salescharts.js" });
} catch (e) {
  console.log("  could not load salescharts.js: " + e.message);
  process.exit(1);
}
const { salesCombo, scToggleSeries, scSeriesHidden, SC_OFF } = sandbox;

// ---- a chart with every series on it -------------------------------------
const COLS = ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"];
function opts() {
  return {
    id: "t_combo", columns: COLS, currency: "GBP", width: 1365, height: 320,
    bars:  { label: "Orders", values: [3, 1, 4, 2] },
    lines: [
      { key: "sales",      values: [200, 150, 300, 250] },
      { key: "profit",     values: [20, 15, 30, 25] },
      { key: "prior_year", values: [180, 160, 280, 240] },
    ],
  };
}
// Count the drawn things in the returned markup. Crude on purpose: the test
// must not depend on how the path is built, only on whether it is there.
function drawn(html) {
  return {
    lines: (html.match(/class="series"/g) || []).length,
    bars: (html.match(/class="bar"/g) || []).length,
    keys: (html.match(/class="sc-key(?: off)?"/g) || []).length,
    off: (html.match(/class="sc-key off"/g) || []).length,
    wraps: (html.match(/id="t_combo_wrap"/g) || []).length,
    svgs: (html.match(/id="t_combo_svg"/g) || []).length,
    // The right-hand count axis only belongs on a chart that still has bars.
    rightAxis: /text-anchor="start"/.test(html),
  };
}

console.log("=== everything is shown until it is switched off ===");
const full = drawn(salesCombo(opts()));
check("all four series are in the key", full.keys, 4);
check("  none of them starts switched off", full.off, 0);
truthy("lines are drawn", full.lines > 0);
truthy("bars are drawn", full.bars > 0);
check("exactly one chart", [full.wraps, full.svgs], [1, 1]);

console.log("\n=== switching a line off takes it off the chart ===");
scToggleSeries("t_combo", "profit");
truthy("the state says it is hidden", scSeriesHidden("t_combo", "profit"));
const noProfit = drawn(salesCombo(opts()));
truthy("fewer line paths than before", noProfit.lines < full.lines);
// THE POINT OF THE WHOLE FEATURE: it must still be listed, or there is no way
// back. Building the key from the VISIBLE list instead of the drawable one is
// the obvious way to write this and it is a one-way door.
check("it is still in the key", noProfit.keys, 4);
check("  and marked as off", noProfit.off, 1);

console.log("\n=== and switching it on again restores the chart exactly ===");
scToggleSeries("t_combo", "profit");
falsy("the state says it is shown", scSeriesHidden("t_combo", "profit"));
check("back to the original chart", drawn(salesCombo(opts())), full);

console.log("\n=== hiding a big series rescales the axis ===");
// Sales is 200-300 and profit is 15-30. On a shared axis profit is a line along
// the floor, and rescaling is the only thing that makes it readable -- which is
// why the axis is computed from the visible series and not from all of them.
function leftAxis(html) {
  // The tick text only. The label is on its own line inside the <text> element,
  // so cut at the LAST ">" and drop the trailing "<" -- matching from the first
  // one drags the attributes along and makes the printout unreadable.
  return (html.match(/text-anchor="end"[^>]*>[^<]*</g) || [])
    .map(function (m) { return m.replace(/^[\s\S]*>/, "").replace(/<$/, "").trim(); });
}
const axisAll = leftAxis(salesCombo(opts()));
scToggleSeries("t_combo", "sales");
scToggleSeries("t_combo", "prior_year");
const axisProfitOnly = leftAxis(salesCombo(opts()));
truthy("the axis has labels at all", axisAll.length > 0);
check("the axis changed once the big series went", axisAll === axisProfitOnly, false);
console.log("      with everything: " + JSON.stringify(axisAll));
console.log("      profit only:     " + JSON.stringify(axisProfitOnly));
scToggleSeries("t_combo", "sales");
scToggleSeries("t_combo", "prior_year");

console.log("\n=== the bars switch off too, and take their axis with them ===");
truthy("the count axis is there while the bars are", drawn(salesCombo(opts())).rightAxis);
scToggleSeries("t_combo", "__bars");
const noBars = drawn(salesCombo(opts()));
check("no bars are drawn", noBars.bars, 0);
// An axis reading 0-1-2-3-4 beside a chart with nothing counted on it is
// furniture, and it holds 70px of width that the plot could use.
falsy("  and the count axis goes with them", noBars.rightAxis);
check("  the Orders item is still there to switch back on", noBars.keys, 4);
scToggleSeries("t_combo", "__bars");

console.log("\n=== everything hidden says so, rather than looking like no sales ===");
["sales", "profit", "prior_year", "__bars"].forEach(function (k) {
  scToggleSeries("t_combo", k);
});
const empty = salesCombo(opts());
check("nothing is drawn", drawn(empty).lines + drawn(empty).bars, 0);
truthy("the chart says it is hidden, not that there is nothing",
       /hidden/i.test(empty));
truthy("  and says how to get it back", /click a name/i.test(empty));
check("still exactly one chart", drawn(empty).wraps, 1);
["sales", "profit", "prior_year", "__bars"].forEach(function (k) {
  scToggleSeries("t_combo", k);
});

console.log("\n=== each chart keeps its own switches ===");
// Two charts on one screen (Sales has one, Traffic has four). Hiding Sessions
// on the Traffic overview must not blank the Sales chart.
scToggleSeries("other_combo", "sales");
truthy("the other chart's sales is hidden", scSeriesHidden("other_combo", "sales"));
falsy("  and this chart's is not", scSeriesHidden("t_combo", "sales"));
scToggleSeries("other_combo", "sales");

console.log("\n=== the state resets on a reload, on purpose ===");
// Not localStorage: opening the app to a chart with a line missing, and no
// memory of having hidden it, reads as lost data.
falsy("nothing is persisted", /localStorage|sessionStorage/.test(src));
truthy("  and the file says why", /reads as lost data/i.test(src));

console.log("\n=== the scroll animation is not built a second time ===");
// Rule 12. altaChartsInView in static/js/motion.js already holds a below-fold
// chart at the start of its animation and releases it on scroll; two systems
// animating one element is how you get a chart that plays twice or freezes.
truthy("the redraw re-arms the existing one", src.includes("altaChartsInView"));
falsy("  and does not define its own observer",
      /new IntersectionObserver/.test(src));
const motion = fs.readFileSync(path.join("static", "js", "motion.js"), "utf8");
truthy("the one that does exist is still there",
       motion.includes("function altaChartsInView"));
truthy("  and still releases on scroll", motion.includes("await-view"));

console.log("\n=== the key is a real control, not a span that happens to click ===");
const html = salesCombo(opts());
truthy("it is a button", /<button type="button" class="sc-key/.test(html));
truthy("  with the on/off state announced", /aria-pressed="(true|false)"/.test(html));
truthy("  and a title saying what a click will do",
       /title="(Hide|Show) /.test(html));
const css = fs.readFileSync(path.join("static", "css", "dashboard.css"), "utf8");
truthy("it is styled in the stylesheet", css.includes(".sc-key"));
truthy("  and shows a keyboard focus ring", /\.sc-key:focus-visible/.test(css));
// Dimming alone is how a DISABLED control looks, and these are never disabled.
truthy("  off is struck through, not just faded",
       /\.sc-key\.off span\{[^}]*line-through/.test(css));

console.log("\n" + (fails.length ? "FAILED: " + fails.join(", ") : "all checks passed"));
process.exit(fails.length ? 1 : 0);
