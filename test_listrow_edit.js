/* Priority 1 of LISTINGS_FUNCTIONAL_FIXES.md: the broken interactions.
 *
 * TWO OF THE SIX HAD A DIFFERENT TRUTH THAN THE BRIEF STATED, and both are
 * asserted here as what they actually are:
 *
 *   1.1 "the three-dot menu does nothing" -- it THREW. drawerMore read
 *       ev.target.closest("button") and then that element's rectangle, and in
 *       the detailed row the dots are an <i>. closest() returned null, the next
 *       line was a TypeError, and because the menu had already been appended by
 *       then the result was a position:fixed element with no top or left parked
 *       below the page, with no click-away listener.
 *
 *   1.2 "clicking the product title does nothing" -- the title has carried
 *       onclick="openListing(sku)" since the view was built, and the ASIN opens
 *       Amazon in a new tab, which is exactly the arrangement the brief asks
 *       for. Pinned here so that if it ever stops being true, this says so.
 *
 *   1.3 "price editing does nothing" -- it SAVED, immediately, on change. What
 *       was missing was any way to see it had or to take it back.
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
function falsy(label, got){ check(label, !!got, false); }

const D = "D:/AltaScraper/";
const LS = fs.readFileSync(D + "static/js/listings.js", "utf8");
const LR = fs.readFileSync(D + "static/js/listrow_detailed.js", "utf8");
const ED = fs.readFileSync(D + "static/js/listrow_edit.js", "utf8");
const CG = fs.readFileSync(D + "static/js/cogs.js", "utf8");
const UI = fs.readFileSync(D + "static/js/pageui.js", "utf8");
const AF = fs.readFileSync(D + "static/js/autofix.js", "utf8");
const CSS = fs.readFileSync(D + "static/css/listrow_edit.css", "utf8");
const H = fs.readFileSync(D + "templates/dashboard.html", "utf8");

/* The body of one function, so a claim cannot be satisfied by a line somewhere
 * else in a 3,000-line file. */
function fn(src, name){
  const i = src.indexOf("function " + name + "(");
  if(i < 0) return "";
  const j = src.indexOf("\n}", i);
  return j < 0 ? src.slice(i) : src.slice(i, j + 2);
}

console.log("== 1.1 the three-dot menu ==");
const DM = fn(LS, "drawerMore");
truthy("drawerMore exists", DM.length > 0);
// THE BUG ITSELF: an anchor that had to be a <button>.
falsy("it no longer demands a <button> before measuring",
      /const btn = ev\.target\.closest\("button"\);\s*\n\s*const rect = btn\.getBoundingClientRect/.test(DM));
truthy("the element the handler is on is the anchor", /ev\.currentTarget/.test(DM));
truthy("  with closest('button') kept as a fallback", /closest\("button"\)/.test(DM));
truthy("  and a plain target as the last one", /\|\| ev\.target;/.test(DM));
// MEASURED BEFORE ANYTHING IS BUILT, so a failure cannot strand a menu in the
// DOM the way the throw did.
const iRect = DM.indexOf("getBoundingClientRect");
const iAppend = DM.indexOf("appendChild");
truthy("the rectangle is taken before the menu is created", iRect > 0 && iRect < iAppend);
truthy("  and no anchor means no menu at all", /if\(!anchor \|\| !anchor\.getBoundingClientRect\) return;/.test(DM));
truthy("the row still calls it from an <i>", /ti-dots act-dots/.test(LR));
truthy("  and the reason it used to fail is written down",
      /closest\(\) returned null/.test(DM));

console.log("\n== 1.1 what the menu offers ==");
truthy("Edit listing", /<i class="ti ti-edit"><\/i> Edit listing/.test(DM));
truthy("View on Amazon", /View on Amazon/.test(DM));
truthy("Copy ASIN", /Copy ASIN/.test(DM));
truthy("Delete listing (already there)", /Delete listing/.test(DM));
// OUR ASIN, NEVER THE COMPETITOR'S -- a SKU is price_days_ASIN and that ASIN
// belongs to somebody else (CLAUDE.md Rule 1).
truthy("the ASIN comes from rowAsin, not from the SKU", /rowAsin\(_r\)/.test(DM));
truthy("  and only the 'own' one is used", /const ourAsin = _a\.own/.test(DM));
falsy("  the competitor's is never linked", /_a\.source/.test(DM));
truthy("a listing with no ASIN says so instead of hiding the items",
       /No ASIN yet/.test(DM));
// NOTHING INVENTED. The brief asks for Duplicate; nothing in the app can do it.
falsy("no Duplicate item was invented", /> Duplicate</.test(DM));
truthy("  and the absence is explained", /NO "DUPLICATE"/.test(DM));

console.log("\n== one clipboard helper, not a fifth copy ==");
truthy("uiCopy exists in pageui.js", /function uiCopy/.test(UI));
truthy("  it handles the API being absent", /navigator\.clipboard\.writeText/.test(UI)
       && /will not let the page copy/.test(UI));
// THE FAILURE THAT MATTERED: writeText rejects asynchronously, so a try/catch
// around it reports success over an empty clipboard.
truthy("  and the async rejection, which a try/catch misses",
       /Copy refused by the browser/.test(UI));
truthy("  a long value is not echoed into a toast", /s\.length <= 40/.test(UI));
truthy("the menu uses it", /uiCopy\('/.test(DM));
truthy("the auto-fix trace uses it", /uiCopy\(txt, "Trace copied"\)/.test(AF));
truthy("the payload viewer uses it", /uiCopy\(document\.getElementById\('pl_/.test(AF));
// The two big trace exports keep their own window fallback on purpose.
truthy("the exports that fall back to a window are left alone",
       (AF.match(/navigator\.clipboard\.writeText/g) || []).length === 2);
truthy("  and that is said, not left to be discovered",
       /NOT used by the two auto-fix TRACE exports/.test(UI));

console.log("\n== 1.2 the title opens the listing, the ASIN opens Amazon ==");
const PR = fn(LR, "lrProduct");
truthy("the title opens the listing", /class="prod-title"[\s\S]*?openListing/.test(PR));
truthy("  through the one function that decides which view", /function openListing/.test(LS));
truthy("the ASIN is a link to Amazon", /class="asin-link" href/.test(PR));
truthy("  in a new tab", /target="_blank"/.test(PR));
truthy("  and it does not also open the listing", /onclick="event\.stopPropagation\(\)"/.test(PR));
// A draft has no ASIN of its own; the competitor's must not look like one.
truthy("a draft's competitor ASIN is not given a link", /not live yet · from/.test(PR));

console.log("\n== 1.3 the Save all / Cancel bar ==");
truthy("the module exists", ED.length > 0);
truthy("it is loaded", /static\/js\/listrow_edit\.js/.test(H));
truthy("  and its styles", /static\/css\/listrow_edit\.css/.test(H));
// AFTER listrow_detailed.css, which it has to override.
truthy("  after the row's own stylesheet",
       H.indexOf("listrow_edit.css") > H.indexOf("listrow_detailed.css"));

truthy("the price box no longer saves on change",
       !/onchange="saveEdit\(this/.test(fn(LR, "lrPriceBox")));
truthy("  it stages instead", /lrEditBox\(/.test(fn(LR, "lrPriceBox")));
truthy("typing stages the value", /function lrEditStage/.test(ED));
truthy("the bar counts SKUs", /" SKU" \+ \(n === 1 \? "" : "s"\) \+ " edited"/.test(ED));
truthy("Cancel exists", /function lrEditCancel/.test(ED));
truthy("Save all exists", /async function lrEditSaveAll/.test(ED));

// CANCEL IS INSTANT AND MAKES NO CALL -- stated in the brief and easy to get
// wrong by re-rendering.
const CAN = fn(ED, "lrEditCancel");
falsy("Cancel makes no request", /fetch\(/.test(CAN));
falsy("  and does not re-render the table", /render\(\)/.test(CAN));
truthy("  it writes each box's own original back",
       /getAttribute\("data-lr-orig"\)/.test(CAN));
// The original lives ON the element, because the table is rebuilt constantly.
truthy("the original is carried on the element", /data-lr-orig="/.test(ED));
truthy("  and why is recorded", /destroyed with the element it belongs to/.test(ED));

// TYPED BACK TO THE ORIGINAL IS NOT AN EDIT.
truthy("a value typed back to its original is dropped", /function _lrSame/.test(ED));
truthy("  numerically, so 9.10 and 9.1 are one price", /isFinite\(na\) && isFinite\(nb\) && na === nb/.test(ED));
truthy("  but blank and 0 are never the same", /if\(sa === "" \|\| sb === ""\) return false;/.test(ED));

// A FAILURE MUST NOT LOSE THE OTHERS.
const SAV = fn(ED, "lrEditSaveAll");
truthy("each field is saved separately", /for\(const j of jobs\)/.test(SAV));
truthy("  a failure keeps its edit", /j\.el\.classList\.add\("err"\)/.test(SAV));
truthy("  and is named with the reason", /failed\[0\]\.why/.test(SAV));
truthy("a saved value becomes the new original",
       /setAttribute\("data-lr-orig"/.test(SAV));

console.log("\n== every field saves through the route that already owned it ==");
truthy("price -> /edit as its column", /_lrSaveCol\(sku, "Our Price \(GBP\)", value\)/.test(ED));
truthy("handling -> /edit as its column", /_lrSaveCol\(sku, "Handling Days", value\)/.test(ED));
truthy("cost -> cogsSet in cogs.js", /return cogsSet\(sku, val\)/.test(ED));
truthy("stock -> /stock\\/bulk_update", /"\/stock\/bulk_update"/.test(ED));
// Both columns must actually be editable server-side.
const DASH = fs.readFileSync(D + "dashboard.py", "utf8");
truthy("the server allows Our Price (GBP)", /"Our Price \(GBP\)"/.test(DASH.slice(DASH.indexOf("_EDITABLE_COLS"))));
truthy("  and Handling Days", /"Handling Days"/.test(DASH.slice(DASH.indexOf("_EDITABLE_COLS"))));
// ONE CALLER OF /cogs/set, extracted rather than copied.
// ONE CALLER OF /edit TOO. saveEdit had the request inline; the bar needs to
// write a field with no element to style, and a second POST would have been a
// second opinion about what an empty attribute means (deleted) versus an empty
// column (saved as empty).
truthy("editField is the one caller of /edit", /async function editField/.test(AF)
       && (AF.match(/fetch\("\/edit"/g) || []).length === 1);
truthy("  saveEdit is now the element around it", /const j = await editField\(sku, target, key, value\);/.test(AF));
truthy("  and the bar goes through it as well", /return editField\(sku, "col", key, value\);/.test(ED));
falsy("  listrow_edit does not post to /edit itself", /fetch\(\s*["']\/edit/.test(ED));
truthy("  the attr-vs-col rule stayed in one place",
       /delete r\.attributes\[key\]/.test(AF)
       && !/delete r\.attributes\[key\]/.test(ED));

truthy("cogsSet is the one caller of /cogs/set",
       (CG.match(/["']\/cogs\/set["']/g) || []).length === 1);
truthy("  and the click-to-edit cell goes through it too", /const res = await cogsSet\(sku, val\)/.test(CG));
// It NAMES the route in its own documentation, which is wanted; what must not
// exist is a second request to it.
falsy("listrow_edit does not post to it itself",
      /fetch\(\s*["'][^"']*cogs/.test(ED));

console.log("\n== stock is the one that reaches Amazon, and says so ==");
truthy("only stock is marked live", /qty:      \{label: "stock",        live: true\}/.test(ED));
truthy("  price is not", /price:    \{label: "price",        live: false\}/.test(ED));
truthy("a live change is confirmed first", /uiConfirm\(/.test(SAV));
truthy("  naming how many listings", /live\.length/.test(SAV));
truthy("the bar says where the changes go", /stock goes to Amazon; the rest is saved here/.test(ED));
truthy("  and when nothing does", /saved in this app, not sent to Amazon/.test(ED));
// The local copy of Amazon's answer is kept in step, or the next render shows
// the old number over a listing that has changed.
truthy("a saved quantity updates the cached metric",
       /LISTING_METRICS\[sku\]\.available = qty/.test(ED));

console.log("\n== 1.4 cost, 1.5 handling, 1.6 stock ==");
const CR = fn(LR, "lrCostRow");
truthy("cost is a box", /lrEditBox\(\{sku: r\.sku, field: "cost"/.test(CR));
truthy("  and cogsOf still decides what the cost IS", /cogsOf\(r\)/.test(CR));
falsy("  it is not pre-filled with zero", /toFixed\(2\) : "0/.test(CR));
truthy("  an unknown cost shows as not set", /placeholder: "not set"/.test(CR));

const HR = fn(LR, "lrHandRow");
truthy("handling is a box", /lrEditBox\(\{sku: r\.sku, field: "handling"/.test(HR));
truthy("  it edits OUR number", /r\.handling_days/.test(HR));
// Amazon's own figure is a reading, and _handCell is the one place that
// compares the two.
truthy("  Amazon's own figure is kept as a read-out", /_handCell\(r\)/.test(HR));
truthy("  only where the two can disagree", /live && typeof _handCell/.test(HR));

const AV = fn(LR, "lrAvailRow");
const CE = fn(LR, "lrCanEditQty");
truthy("stock is editable on a merchant listing", /lrEditBox\(\{sku: r\.sku, field: "qty"/.test(AV));
truthy("  decided by the fulfilment channel", /ff === "DEFAULT" \|\| ff === "MFN"/.test(CE));
// AN UNKNOWN CHANNEL IS NOT A MERCHANT ONE.
truthy("  an unread channel is read-only, not assumed merchant", /return false;/.test(CE));
truthy("  and says why rather than showing a bare dash",
       /has not been read yet/.test(AV));
truthy("  FBA says whose stock it is", /Amazon holds this stock/.test(AV));
truthy("the measurement behind the default is recorded",
       /all 100 SKUs with a stock reading on this account are DEFAULT/.test(LR));

console.log("\n== an unsaved edit survives a re-render ==");
truthy("there is a restore", /function lrEditRestore/.test(ED));
truthy("  called after the view draws", /setTimeout\(lrEditRestore, 0\)/.test(LR));
truthy("  and why it cannot be called directly", /this function returns a STRING/.test(LR));

console.log("\n== the bar's look was measured, not copied ==");
// The brief specifies #0F8B8D with white text. Measured at 3.35:1.
falsy("the brief's hardcoded teal is not used", /0F8B8D/i.test(CSS));
truthy("  the app's measured pairing is", /var\(--accent-bg\)/.test(CSS));
truthy("  and the reason is written down", /is not a contrast, it is a glare/.test(CSS.replace(/\s+/g, " ")));
// z-index has to sit under the confirm dialog it triggers.
truthy("the bar sits under the dialogs it opens", /z-index:50/.test(CSS));
truthy("  chosen against the bands already in use", /chrome\s*\n?\s*10-40/.test(CSS));
truthy("the dirty state sets the whole border shorthand",
       /\.lr-edit\.dirty\{\s*\n?\s*border:1px solid var\(--warn\)/.test(CSS));
truthy("  because .price-input-wrap input sets border:none",
       /border:none/.test(CSS));

console.log("\n== nothing is half-written ==");
check("listrow_edit.css braces balance", (CSS.match(/\{/g)||[]).length, (CSS.match(/\}/g)||[]).length);
falsy("no mojibake", /â€|Â·|â•/.test(ED + CSS + LR + LS + CG + UI));

console.log("\n" + fails + " failed");
process.exit(fails ? 1 : 0);
