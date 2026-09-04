/* Both charts on the sales page draw the same way.
 *
 *     "The main Sales chart draws clean continuous lines that go through zero.
 *      The Organic vs PPC chart below it draws dotted/broken lines that
 *      disconnect on days with zero sales."
 *
 * MEASURED IN CHROME BEFORE CHANGING ANYTHING, and the premise did not hold:
 * both Organic and PPC came back as ONE path each, stroke-dasharray empty,
 * running flat along £0 through every zero-sale day exactly as the Sales line
 * above does. There was no gap to close -- salesDrawOrgPpc already maps a zero
 * total to a zero, and only a genuinely MISSING day becomes null.
 *
 * Two things did make the second chart look broken, and both are fixed:
 *
 *   1. .ri-sample dimmed the WHOLE figure to 45% -- axis labels, grid, legend
 *      and the two 2px lines -- beside a full-strength chart above it. A 2px
 *      line at 45% on a dark ground is what a broken line looks like.
 *
 *   2. Neither chart shaded the days with no data. This file's own rule says
 *      "A missing day breaks the line and is shaded, so the gap looks like a
 *      gap", and the single-metric charts do it -- salesCombo, which draws BOTH
 *      of these, never did. So both lines simply stopped on Aug 20 with a
 *      fortnight of empty grid beside them and nothing to say why.
 */
const fs = require("fs");
const path = require("path");

let fails = 0;
function ok(label, cond) {
  if (!cond) fails++;
  console.log("  " + (cond ? "OK  " : "FAIL") + "  " + label);
}
function read(...p) {
  return fs.readFileSync(path.join(__dirname, ...p), "utf8");
}
function code(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
}

const SC = code(read("static", "js", "salescharts.js"));
const SALES = code(read("static", "js", "sales.js"));
const CSS = read("static", "css", "dashboard.css");

console.log("\n== a zero-sale day is a point at zero, not a missing point ==");
ok("organic keeps a zero as a zero",
   /organic = total\.map\(function\(t, i\)\{[\s\S]{0,220}if\(t === null \|\| t === undefined\) return null;/
     .test(SALES));
ok("  and only a genuinely missing day becomes null",
   /return Math\.max\(0, Number\(t\) - a\);/.test(SALES));
ok("the two series are solid, not dashed",
   /organic:\s*\{label: "Organic",[^}]*dash: "",/.test(SC)
   && /ppc:\s*\{label: "PPC",[^}]*dash: "",/.test(SC));

console.log("\n== the placeholder figure is marked, but readable ==");
ok("the sample dimming is no longer 45%", !/\.ri-sample\{ opacity:\.45;/.test(CSS));
ok("  it is .72", /\.ri-sample\{ opacity:\.72; font-style:italic; \}/.test(CSS));
ok("  and the banner still says it in words, which is the load-bearing part",
   /This split is a placeholder, not your data/.test(SALES));

console.log("\n== both charts shade the days nothing was measured on ==");
// salesCombo draws the Sales Report AND the Organic vs PPC panel, so one
// implementation gives both of them the behaviour (CLAUDE.md Rule 12).
const combo = SC.slice(SC.indexOf("function salesCombo"));
ok("salesCombo builds a gaps layer", /let gaps = "";/.test(combo));
ok("  from days where no CURRENT series has a value",
   /!CONTEXT\[l\.key\] && _scNum\(\(l\.values \|\| \[\]\)\[i\]\) !== null/.test(combo));
// Without this the main chart would never shade anything: its green Sales line
// stops on Aug 20 and the grey prior-period line runs on to Sep 3.
ok("  and prior/prior_year do not count as current",
   /const CONTEXT = \{prior: 1, prior_year: 1\};/.test(combo));
ok("  a bar still counts", /const anyBar = barsOn && _scNum\(\(bars\.values \|\| \[\]\)\[i\]\) !== null;/
   .test(combo));
ok("  it is rendered", /\+ defs \+ grid \+ gaps \+ barsSvg \+ linesSvg \+ xl \+ hits/.test(combo));
ok("  behind the bars and lines, never over them",
   combo.indexOf("grid + gaps + barsSvg") >= 0);
ok("  in the same grey the single-metric charts use",
   (SC.match(/fill="#7b8794" opacity="0\.07"/g) || []).length === 2);

console.log("\n== driven in Chrome ==");
// Recorded so the numbers survive the terminal. Read off the live page:
//   Organic  #10b981  one path, dash "", flat along £0 Aug 5-13 and Aug 18-19
//   PPC      #8b5cf6  one path, dash ""
//   Sales    #10b981  one path, dash ""
//   both charts shade Aug 21 - Sep 3, where this account's data ends
ok("the file still says why a gap is not drawn through",
   /They never draw a zero where there is no data/.test(read("static", "js", "salescharts.js")));

console.log("\n" + (fails ? fails + " FAILED" : "0 failed"));
process.exit(fails ? 1 : 0);
