/* ONE product detail view.
 *
 *     "The app has TWO different product detail views that appear in different
 *      contexts ... These are completely different UIs showing the same data.
 *      This is confusing -- the user doesn't know which one will appear when.
 *      Fix: pick ONE."
 *
 * THE TRACE THE BRIEF ASKED FOR. openDrawer is called from eighteen places
 * across five files, and only six of them are a user opening something:
 *
 *   listings.js   the compliance chip on a tile        -> now openListingAt
 *   listings.js   the "no copy yet" chip               -> now openListingAt
 *   listings.js   the claim-risk chip                  -> now openListingAt
 *   listings.js   "Edit details" in the tile menu      -> now openListing
 *   listings.js   openListing's own last-line fallback -> kept, see below
 *   runqueue.js   clicking a run in the queue          -> now openListing
 *
 * The other twelve are re-render guards shaped `if(DRAWER_SKU === sku)
 * openDrawer(sku)` -- they redraw a drawer that is ALREADY open after a schema
 * load, a run finishing or a mirror arriving. They cannot fire now: DRAWER_SKU
 * is never set, so the condition is never true.
 *
 * THE DOOR IS CLOSED AT openDrawer ITSELF rather than at the call sites,
 * because closing one door shuts a nineteenth caller written next month too
 * (CLAUDE.md Rule 12).
 *
 * NOTHING IS DELETED. The drawer's builders are shared with the product page --
 * _fullDataParts, dwTitleParts, dwBulletCards, the bullet byte budget -- so
 * removing the component would take the page's own contents with it. What is
 * removed is the ROUTE to it. And the fallback stays a fallback: with pdp.js
 * unloaded there is no full-page view to send anyone to, and a listing that
 * opens NOTHING is worse than one that opens the old panel.
 */
const fs = require("fs");
const path = require("path");

let fails = 0;
function ok(label, cond) {
  if (!cond) fails++;
  console.log("  " + (cond ? "OK  " : "FAIL") + "  " + label);
}
function read(...p) { return fs.readFileSync(path.join(__dirname, ...p), "utf8"); }
function code(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
}

const LIST = code(read("static", "js", "listings.js"));
const RQ = code(read("static", "js", "runqueue.js"));
const MIL = code(read("static", "js", "miles_template.js"));
const AF = code(read("static", "js", "autofix.js"));
const HW = code(read("static", "js", "howworks.js"));

console.log("\n== the door is closed at openDrawer ==");
ok("openDrawer sends you to the product page",
   /function openDrawer\(sku, jumpGen\)\{\s*if\(typeof pdpOpen === "function"\)\{\s*pdpOpen\(sku\);\s*return;\s*\}/
     .test(LIST));
ok("  and only falls through when there is no product page to use",
   LIST.indexOf('if(typeof pdpOpen === "function"){\n    pdpOpen(sku);')
     < LIST.indexOf("DRAWER_SKU=sku;"));

console.log("\n== no opener goes to the drawer any more ==");
ok("the compliance chip opens the Compliance tab",
   /tiledocs[\s\S]{0,400}openListingAt\('\$\{esc\(r\.sku\)\}','compliance'\)/.test(LIST));
ok("the claim chip does too",
   /tileclaim[\s\S]{0,200}openListingAt\('\$\{esc\(r\.sku\)\}','compliance'\)/.test(LIST));
ok("the 'no copy yet' chip opens the details tab",
   /tilecopy[\s\S]{0,500}openListingAt\('\$\{esc\(r\.sku\)\}','details'\)/.test(LIST));
ok("'Edit details' in the tile menu goes through openListing",
   /onclick="openListing\('\$\{esc\(sku\)\}'\);closeTileMenu\(\)"/.test(LIST));
ok("clicking a run in the queue goes through openListing",
   /function rqOpenJob\(sku\)\{[\s\S]{0,200}openListing\(sku\)/.test(RQ));
ok("  with the drawer only as its own last line",
   /rqOpenJob[\s\S]{0,300}else if\(typeof openDrawer === "function"\)/.test(RQ));

console.log("\n== every remaining caller is a guard that cannot fire ==");
// A guard reads "if the drawer is already open on this SKU, redraw it".
// DRAWER_SKU is only ever assigned inside openDrawer's fallback, which needs
// pdp.js to be missing -- so in a loaded app none of these is ever true.
const guards = [];
[["listings.js", LIST], ["miles_template.js", MIL],
 ["autofix.js", AF], ["howworks.js", HW]].forEach(function (pair) {
  const re = /openDrawer\(/g;
  let m;
  while ((m = re.exec(pair[1]))) {
    const line = pair[1].slice(pair[1].lastIndexOf("\n", m.index) + 1,
                              pair[1].indexOf("\n", m.index));
    if (/function openDrawer/.test(line)) continue;
    if (/openDrawer\(s\);/.test(line)) continue;          // openListing's fallback
    // The WHOLE line is what decides; only the printed label is trimmed.
    // autofix.js's guard is inside a .then() on a long line, and truncating
    // before testing is how a guard gets mistaken for an opener.
    guards.push({file: pair[0], full: line, line: line.trim().slice(0, 70)});
  }
});
guards.forEach(function (g) {
  ok("  " + g.file + ": " + g.line, /DRAWER_SKU/.test(g.full));
});
ok("there are guards, and they were all checked", guards.length >= 5);

console.log("\n== DRAWER_SKU is set in exactly one place ==");
// Three: the declaration, the open, and the close. Anything more means a
// second place decided the drawer was showing, and the guards would wake up.
const sets = (LIST.match(/DRAWER_SKU\s*=\s*[^=]/g) || []);
ok("three assignments: declared, opened, closed (found " + sets.length + ")",
   sets.length === 3);
ok("  and the opening one is behind the pdpOpen check",
   LIST.indexOf("DRAWER_SKU=sku;") > LIST.indexOf("pdpOpen(sku);\n    return;"));

console.log("\n== a submit shows progress and a toast, not a panel of details ==");
ok("enqueue opens the RUNS panel, not the drawer",
   /rqEnqueue[\s\S]{0,900}rqTogglePanel\(\)/.test(RQ));
ok("  and never openDrawer", !/rqEnqueue[\s\S]{0,900}openDrawer\(/.test(RQ));
ok("the outcome is spoken as a toast", /function _rqSayOutcome/.test(RQ)
   && /toast\(what \+ " — Amazon accepted it/.test(RQ));

console.log("\n== driven in Chrome ==");
// Called on a real listing; each read back drawer/PDP state, then closed:
//   openDrawer(sku)          drawer false  pdp true  tab details  DRAWER_SKU null
//   openListing(sku)         drawer false  pdp true  tab details
//   openListingAt(...)       drawer false  pdp true  tab compliance
//   openLiveListing("",sku)  drawer false  pdp true  tab details
//   rqOpenJob(sku)           drawer false  pdp true  tab details
//   pdpOpen(sku)             drawer false  pdp true  tab details
//   page errors: 0
ok("openListingAt exists and takes a tab",
   /function openListingAt\(sku, tab\)/.test(LIST));
ok("  and the tab is a preference, not a requirement",
   /String\(PDP_SKU\) === String\(sku\)\)\{\s*pdpTab\(tab\);/.test(LIST));

console.log("\n" + (fails ? fails + " FAILED" : "0 failed"));
process.exit(fails ? 1 : 0);
