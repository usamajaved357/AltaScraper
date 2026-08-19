// Nothing on a screen may be CUT OFF AND UNREACHABLE.
//
//     "i have seen the page cutting my visuals and getting out of the screen
//      where i can not see the text or graphics"
//
// Two different faults hide behind that sentence and only one of them is
// visible to a page-width check:
//
//   OVERFLOW   the page is wider than the window. There is a scrollbar, so the
//              content is at least reachable.
//   CLIPPED    an element is wider than an ancestor with overflow:hidden. No
//              scrollbar, no way to reach it — the columns are simply GONE.
//
// MEASURED in a real browser, at 1280px, with real data on screen:
//
//     Weekly KPIs   583px of table invisible
//     Listings       43px, which is the whole Actions column
//     Sales charts    6px of chart drawn outside its own SVG
//
// The page fitted perfectly in every one of those cases, which is why this was
// never caught: the fault is INSIDE a card, not at the edge of the document.
//
// The fix already existed — but only inside mobile.css's phone media query, so
// every desktop kept clipping. This test is the guard against it drifting back
// into a media query, or a new screen putting a wide table in a plain card.
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) { return fs.readFileSync(path.join(__dirname, p), "utf8"); }

const CSS = read("static/css/dashboard.css");
const MOB = read("static/css/mobile.css");
const CHARTS = read("static/js/salescharts.js");

// Is a rule at the top level of the stylesheet, or nested inside an @media?
// "Appears before the first @media in the file" is NOT the same question --
// media queries close, and most of this stylesheet sits after several of them.
// Getting that wrong is how a test claims a working rule is broken, so the
// brace depth is counted properly.
function atTopLevel(css, needle) {
  const at = css.indexOf(needle);
  if (at < 0) return false;
  let depth = 0;
  for (let i = 0; i < at; i++) {
    const c = css[i];
    if (c === "{") depth++;
    else if (c === "}") depth--;
  }
  return depth === 0;
}
// The block this rule lives in, so its contents can be checked.
function ruleBlock(css, needle) {
  const at = css.indexOf(needle);
  if (at < 0) return "";
  const open = css.indexOf("{", at);
  const close = css.indexOf("}", open);
  return css.slice(at, close + 1);
}

console.log("== a wide table scrolls at EVERY width, not just on a phone ==");
// The rule has to apply at every width. Trapped in a phone media query — which
// is exactly where it was — a 1280px desktop keeps clipping and the person
// using it has no idea the columns exist.
check("the card-scroll rule is in dashboard.css",
  /\.card:has\(> table\)/.test(CSS));
check("  and NOT trapped inside a media query",
  atTopLevel(CSS, ".card:has(> table)"));
const block = ruleBlock(CSS, "#workspace .card:has(> table)");
check("  it scrolls rather than hides", /overflow-x:auto !important/.test(block));
check("  the listings wrapper is covered by the same rule",
  /\.ltwrap/.test(block));
// The phone still needs its own part: without a floor the table obeys
// width:100% and squashes instead of scrolling.
check("the phone keeps only its own part — the min-width floor",
  /\.stk-table\{\s*min-width:720px/.test(MOB));

console.log("\n== a chart band stays inside its plot ==");
// Three places clamped the LEFT edge and the WIDTH and never the RIGHT one, so
// on the last point x + width landed outside the SVG and was clipped away.
check("there is one shared band helper", /function _scBand\(/.test(CHARTS));
check("  it clamps the right edge too", /Math\.min\(padL \+ iw, centre \+ half\)/.test(CHARTS));
check("  and never returns a negative width", /Math\.max\(0, right - left\)/.test(CHARTS));
// All three call sites must use it; a leftover copy is a leftover bug.
check("no hand-rolled band survives",
  !/Math\.min\(half \* 2, iw\)/.test(CHARTS));
const uses = (CHARTS.match(/_scBand\(/g) || []).length;
check("  it is used at every site that drew one (3 + the definition)", uses >= 4);

console.log("\n== the measurement itself is repeatable ==");
// Kept as a script rather than described in a comment, because "it fits now" is
// only worth anything if it can be re-checked after the next screen is added.
check("the probe script is checked in",
  fs.existsSync(path.join(__dirname, "tools", "measure_clip.py")));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
