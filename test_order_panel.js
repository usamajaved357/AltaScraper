/* The order panel has to be ARRANGED, and say what Amazon's words mean.
 *
 *   "RIGHT NOW THE TEXT APPEARS IN A FREE FORM WHEN I CLICK ON THE ORDER NUMBER
 *    INSIDE THE ORDERS TAB ... also the order page is not arranged the, text
 *    mixes freely into each other."
 *
 *   "And i see there is written cancel requested i can not understand what it
 *    means."
 *
 *   "it should show the name of the item, the clickable asin which opens the
 *    item ... also show the ship by and deliver by date of the item which is
 *    provided by amazon to the seller."
 *
 * The layout fault was structural, not cosmetic: every element carried its own
 * inline padding and font size, so nothing shared a baseline and there was no
 * grid for anything to line up against. So the test that matters is not "does
 * it look nice" -- it is "is the layout described in ONE place", which is what
 * makes it possible to line up at all. Hence the assertions about classes
 * existing in the stylesheet and inline styling being gone from the panel.
 */
const fs = require("fs");
const path = require("path");
const ROOT = "D:\\AltaScraper";

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + got + " want=" + want));
}
function truthy(l, g) { check(l, !!g, true); }
function falsy(l, g) { check(l, !!g, false); }

const JS = fs.readFileSync(path.join(ROOT, "static", "js", "orders.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "static", "css", "dashboard.css"), "utf8");

// The comments in orders.js quote the complaint verbatim, including the phrases
// this test looks for. Strip them, or the assertions pass on the explanation.
const CODE = JS.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

console.log("=== the layout is described in the stylesheet, not per element ===");
for (const cls of [".odp", ".odp-sec", ".odp-h", ".odp-item", ".odp-title",
                   ".odp-ids", ".odp-src", ".odp-kv", ".odp-state", ".odp-i"]) {
  truthy("  " + cls + " is a real class", CSS.indexOf(cls + "{") >= 0
         || CSS.indexOf(cls + " ") >= 0 || CSS.indexOf(cls + ",") >= 0);
}
truthy("the supplier list is a grid, so its columns line up",
       /\.odp-src\{[^}]*display:grid/.test(CSS.replace(/\s+/g, "")));
truthy("  and a long title is clamped rather than pushing the row about",
       /line-clamp/.test(CSS));

console.log("\n=== and the panel stopped styling itself inline ===");
// The old panel was one wall of style="..." attributes. A couple survive on
// purpose (a colour that depends on a value), so this is a ceiling rather than
// a ban -- but it was over thirty.
const panel = CODE.slice(CODE.indexOf("function _ordDetailHtml"),
                         CODE.indexOf("function _ordDp"));
const inline = (panel.match(/style="/g) || []).length;
check("  _ordDetailHtml carries almost no inline styling", inline <= 2, true);
console.log("       (" + inline + " inline style attributes left in it)");

console.log("\n=== the four sections, in the order the questions get asked ===");
// REWRITTEN, NOT DELETED. These four headings were the panel; the panel is a
// compact one now (static/js/orders_panel.js) and the long version below them
// is the fallback for when that file has not loaded. The QUESTIONS are the
// same four and every one of them is still answered -- that is what this
// checks, rather than the headings that used to introduce them.
for (const h of ["What was ordered", "Where to buy it", "What it earned", "Delivery"]) {
  truthy("  the fallback still has: " + h, CODE.indexOf(h) >= 0);
}
const PANEL = fs.readFileSync(path.join(ROOT, "static", "js", "orders_panel.js"), "utf8");
const PCODE = PANEL.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
truthy("the compact panel is what actually draws", /ordPanelHtml\(r, d\)/.test(CODE));
truthy("  with the long one kept as a fallback",
       /typeof ordPanelHtml === "function"/.test(CODE));
// WHAT WAS ORDERED -> the row above carries it; what the row does NOT carry is
// the ASIN and the cancellation reason, and those are kept.
truthy("  what was ordered: the ASIN and the state chip", /_ordDp\(it\.asin/.test(PCODE)
       && /_ordStateChip\(/.test(PCODE));
// THE FULL TABLE, not the one-line summary. Asked for directly: "show the full
// table with columns (# / Supplier / You pay / Dispatch / Stock / You keep) as
// in the mockup, not collapsed to one line. The data is already there." It is,
// and _ordSourcesHtml draws exactly that table -- the compact flag was asking
// it for its summary instead. What still matters is that it is the sources
// block's OWN rendering rather than a second table written in the panel.
truthy("  where to buy it: the sources block's own table",
       /_ordSourcesHtml\(block,/.test(PCODE));
check("    in full, not collapsed to a line",
      /compact:\s*true/.test(PCODE), false);
truthy("  what it earned: the flow line", /function _opFlow/.test(PANEL));
truthy("  delivery: one line", /function _opDelivery/.test(PANEL));

console.log("\n=== the ASIN opens the product ===");
truthy("it is an anchor, not text", /_ordDp\(it\.asin/.test(CODE));
truthy("  opening in a new tab", /target="_blank"/.test(CODE));
truthy("  built by listings.js's own domain table, not a second copy",
       /typeof _dpUrl === "function"/.test(CODE));
// A link that goes somewhere plausible and wrong is worse than no link.
truthy("  and omitted rather than guessed if that is missing",
       /return "";/.test(CODE.slice(CODE.indexOf("function _ordDp"),
                                    CODE.indexOf("function _ordWhyText"))));

console.log("\n=== the dates Amazon holds you to ===");
truthy("post-by is labelled in plain words", /Post it by/.test(CODE));
truthy("  and says what happens after it", /counts it late/.test(CODE));
truthy("must-arrive-by is there too", /Must arrive by/.test(CODE));
truthy("  and says whose promise it is", /what the buyer was promised/.test(CODE));

console.log("\n=== Amazon's statuses, explained ===");
truthy("there is one table of meanings", /_ORD_STATUS = \{/.test(CODE));
for (const s of ["Shipped", "Unshipped", "Pending", "Canceled", "PartiallyShipped"]) {
  truthy("  " + s + " has a meaning", new RegExp(s + ":\\s*\\{[^}]*m:").test(CODE));
}
truthy("Pending warns you off buying stock for it",
       /Do not buy stock for it/.test(CODE));
truthy("  because a pending order can still vanish",
       /can still disappear/.test(CODE));

console.log("\n=== 'cancel requested', which was the one he could not read ===");
truthy("it has its own entry", /_ORD_CANCEL_REQUESTED/.test(CODE));
truthy("  saying what happened", /pressed cancel after ordering/.test(CODE));
truthy("  and what to do", /Do not post it/.test(CODE));
truthy("  and why it still looks like a live order",
       /too far along/.test(CODE));
// It rides on top of a status rather than replacing one, so both must show.
truthy("  it is shown BESIDE the status, not instead of it",
       /_ordStateChip\(o\.status \|\| r\.status, it\.cancel_requested\)/.test(CODE));
truthy("  and spelled out on the line, not only in a tooltip",
       /_ordWhyText/.test(CODE));

console.log("\n=== the list and the panel describe a status the same way ===");
// Two tables would drift, and the first symptom would be the list calling
// something Unshipped while the panel called it something else.
const tables = (CODE.match(/_ORD_STATUS\s*=/g) || []).length;
check("  exactly one status table exists", tables, 1);
truthy("  and the row reads its label from it", /st\.t \|\| r\.status/.test(CODE));

console.log("\n=== the fee is not called an estimate once Amazon has settled ===");
truthy("the panel asks which it got", /fees_basis === "actual"/.test(CODE));
truthy("  and says so", /Amazon has settled this order/.test(CODE));
truthy("  and says the other thing otherwise",
       /has not settled this order yet/.test(CODE));

console.log("\n" + fails + " failed");
process.exit(fails ? 1 : 0);
