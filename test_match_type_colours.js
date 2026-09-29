// Campaign Analytics: every match type has its own colour, and the chart uses it.
//
// Owner decision, 28 Sep 2026: "Exact = red, Auto = pink, they must be clearly
// distinguishable."
//
// The bug this pins: the spend-per-day chart borrowed metric keys for its lines
// by POSITION (ad_spend, ad_sales, roas, clicks, ad_spend...), so with the five
// match types in the server's order the 1st (Exact) and the 5th (Auto) both
// came out ad_spend red -- and, sharing a key, hid together when either was
// clicked in the chart key. Meanwhile the ring beside it coloured Exact green.

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

// ---- the design tokens: Exact red, Auto pink, not the same ----------------
const css = fs.readFileSync(path.join("static", "css", "foundations.css"), "utf8");
function tok(name) {
  const m = css.match(new RegExp("--" + name + ":\\s*(#[0-9a-fA-F]{6})"));
  return m ? m[1].toLowerCase() : null;
}
check("--as-viz-exact is red", tok("as-viz-exact"), "#ef4444");
check("--as-viz-auto is pink", tok("as-viz-auto"), "#f472b6");

// ---- the Campaign Analytics map uses those tokens --------------------------
const pc = fs.readFileSync(path.join("static", "js", "ppccampaigns.js"), "utf8");
const mcol = (pc.match(/const MCOL = \{([\s\S]*?)\};/) || [])[1] || "";
function col(k) {
  const m = mcol.match(new RegExp("\\b" + k + ':\\s*"([^"]+)"'));
  return m ? m[1] : null;
}
check("MCOL.EXACT -> --as-viz-exact", col("EXACT"), "var(--as-viz-exact)");
check("MCOL auto -> --as-viz-auto",
      col("TARGETING_EXPRESSION_PREDEFINED"), "var(--as-viz-auto)");
const all = ["EXACT", "PHRASE", "BROAD", "TARGETING_EXPRESSION",
             "TARGETING_EXPRESSION_PREDEFINED"].map(col);
check("five match types, five different colours", new Set(all).size, 5);
check("no chart line on this screen borrows a metric key any more",
      /key:\s*(PKEY\[|KEYMAP\[)/.test(pc), false);
check("ad-product lines wear their ring colour (PCOL)",
      /key: "ap_"[\s\S]{0,120}color: PCOL\[k\]/.test(pc), true);
check("match-type lines wear their ring colour (MCOL)",
      /let key = "mt_"[\s\S]{0,200}color: MCOL\[k\]/.test(pc), true);
check("placement lines are keyed by position, not a shared metric key",
      /key: "pl_" \+ i/.test(pc), true);

// ---- the shared chart draws a line in the colour it names -----------------
const src = fs.readFileSync(path.join("static", "js", "salescharts.js"), "utf8");
const sandbox = {
  console: console,
  document: { getElementById: function () { return null; },
              querySelectorAll: function () { return []; } },
  setTimeout: function () { return 0; },
  matchMedia: undefined,
};
sandbox.window = sandbox;
sandbox.jsArg = require("./test_helpers.js").jsArg;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: "salescharts.js" });

const svg = sandbox.salesCombo({
  id: "mt_test", columns: ["2026-09-01", "2026-09-02"], bars: null,
  lines: [
    {key: "mt_EXACT", label: "Exact", color: "var(--as-viz-exact)", values: [1, 2]},
    {key: "mt_TARGETING_EXPRESSION_PREDEFINED", label: "Auto",
     color: "var(--as-viz-auto)", values: [3, 4]},
  ],
  width: 800, height: 280});
check("Exact line stroked red token",
      svg.indexOf('stroke="var(--as-viz-exact)"') >= 0, true);
check("Auto line stroked pink token",
      svg.indexOf('stroke="var(--as-viz-auto)"') >= 0, true);
check("a metric-keyed line with no colour keeps its SC_SERIES colour",
      sandbox._scSpec({key: "ad_sales"}, {}).color, "#38bdf8");
check("an unknown key with no colour falls back to the default",
      sandbox._scSpec({key: "zz"}, {color: "#8fd694"}).color, "#8fd694");

if (fails.length) { console.log("\nFAILED: " + fails.length); process.exit(1); }
console.log("\nall match-type colour checks passed");
