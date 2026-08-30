// The full-screen product page: what it is made of, and how you get in and out.
//
// WHAT THIS PINS
//
// The page is deliberately almost empty of its own logic -- it arranges blocks
// the drawer already builds. That design has exactly one way to fail badly, and
// it is not a visual one:
//
//   * _fullDataParts returns eight named blocks and _fullDataInner composes
//     them. Add a ninth and forget to compose it, and the DRAWER silently loses
//     a section -- no error, no blank space, just a panel that stopped being
//     there. The parity check below is the guard for that.
//   * Two title editors saving to the same cell is how they end up disagreeing
//     about what you typed. There must be exactly one, used by both views.
//   * A SKU is price_days_ASIN -- it has dots in it. If the router's section
//     regex swallows /w/x/listing/9.18_3Days_B0C6XTNXL8, a link to a real row
//     lands on the grid and looks ignored.
//   * Going back must not lose the grid's scroll position: hiding an element
//     collapses the page height and the browser clamps scrollTop to zero.
//
// Run: node test_pdp.js
const fs = require("fs"), vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const AUTOFIX  = fs.readFileSync("static/js/autofix.js", "utf8");
const LISTINGS = fs.readFileSync("static/js/listings.js", "utf8");
const SHELL    = fs.readFileSync("static/js/shell.js", "utf8");
const DRAWER   = fs.readFileSync("static/js/drawer.js", "utf8");

// ---------------------------------------------------------------------------
console.log("\nevery block that is computed is also composed");
// ---------------------------------------------------------------------------
// _fullDataParts ends with `return {a: x, b: y, ...}`. _fullDataInner reads
// them back as p.a + p.b + ... Those two sets must match exactly: a block in
// the object but not in the composition is a section the drawer stopped
// showing, and nothing else would notice.
const retM = /return \{highlights:[\s\S]*?\};/.exec(AUTOFIX);
truthy("_fullDataParts returns a named object", !!retM);
const produced = retM ? (retM[0].match(/(\w+):/g) || []).map(s => s.slice(0, -1)).sort() : [];

const innerM = /function _fullDataInner\(r\)\{[\s\S]*?\n\}/.exec(AUTOFIX);
truthy("_fullDataInner exists as the drawer's composer", !!innerM);
const composed = innerM
  ? [...new Set((innerM[0].match(/\bp\.(\w+)/g) || []).map(s => s.slice(2)))].sort() : [];

check("the drawer composes exactly the blocks that are produced", composed, produced);
check("and there are eight of them", produced.length, 8);

const pdpSrc = fs.readFileSync("static/js/pdp.js", "utf8");
const pdpUses = [...new Set((pdpSrc.match(/\bp\.(\w+)/g) || []).map(s => s.slice(2)))].sort();
check("the product page places every one of them too", pdpUses, produced);

// ---------------------------------------------------------------------------
console.log("\nthere is exactly ONE title editor");
// ---------------------------------------------------------------------------
truthy("dwTitleParts is defined once, in drawer.js",
       /function dwTitleParts\(/.test(DRAWER));
check("  and not a second time anywhere else",
      (AUTOFIX + LISTINGS + pdpSrc).match(/function dwTitleParts\(/g), null);
check("the drawer calls it rather than building its own",
      /dwTitleParts\(r,/.test(LISTINGS), true);
check("the product page calls it too",
      /dwTitleParts\(r,/.test(pdpSrc), true);
// The giveaway for a second editor is a second element that saves to the Title
// column. There must be exactly one across every file. The quotes are escaped
// in the source (it is built inside a JS string), hence the loose middle.
const titleSaves = (DRAWER + LISTINGS + pdpSrc + AUTOFIX).match(/col.{0,2},.{0,2}Title/g) || [];
check("only one control in the app saves to the Title column", titleSaves.length, 1);

// ---------------------------------------------------------------------------
console.log("\nclicking a listing goes through one function");
// ---------------------------------------------------------------------------
truthy("openListing exists", /function openListing\(/.test(LISTINGS));
truthy("it prefers the full-screen page", /pdpOpen\(sku\)/.test(LISTINGS));
truthy("and falls back to the drawer when pdp.js has not loaded",
       /typeof pdpOpen === "function"[\s\S]{0,80}openDrawer\(sku\)/.test(LISTINGS));
// The four ways into a listing from the grid. Counted as call sites, not as
// `onclick="openListing`, because the Review button runs event.stopPropagation()
// first (it sits inside a row that is itself clickable).
const gridEntries = (LISTINGS.match(/openListing\('/g) || []).length;
check("the tile image, tile body, table row and Review button all use it", gridEntries, 4);
truthy("the drawer keeps its own way back to full screen",
       /pdpOpen\('\$\{esc\(r\.sku\)\}'\)/.test(LISTINGS));
// The drawer must NOT have been orphaned: the badges and the tile menu still
// open it directly, which is what makes it the quick view rather than dead code.
truthy("and the drawer is still reachable from the grid's badges / tile menu",
       (LISTINGS.match(/openDrawer\('\$\{esc\(/g) || []).length >= 3);

// ---------------------------------------------------------------------------
console.log("\nthe address, using the router's OWN regexes");
// ---------------------------------------------------------------------------
// Lifted from shell.js rather than restated, so a change there fails here.
const lmM  = /const lm = (\/\^[^\n]*?\/)\.exec/.exec(SHELL);
const secM = /: (\/\^\\\/w[^\n]*?\/)\.exec\(location\.pathname/.exec(SHELL);
truthy("the listing regex was found in shell.js", !!lmM);
truthy("the section regex was found in shell.js", !!secM);
const LRE = lmM ? eval(lmM[1]) : /$^/;
const SRE = secM ? eval(secM[1]) : /$^/;

const SKU = "9.18_3Days_B0C6XTNXL8";
const m1 = LRE.exec("/w/jack_uk/listing/" + SKU);
truthy("a listing address matches", !!m1);
check("  the workspace comes out", m1 && m1[1], "jack_uk");
check("  and the SKU survives its dots", m1 && m1[2], SKU);
check("a trailing slash is tolerated",
      (LRE.exec("/w/jack_uk/listing/" + SKU + "/") || [])[2], SKU);
check("an encoded slash in a SKU survives",
      decodeURIComponent((LRE.exec("/w/jack_uk/listing/A%2FB") || [])[2] || ""), "A/B");
check("a plain section is NOT read as a listing", LRE.exec("/w/jack_uk/listings"), null);
check("nor is the workspace root", LRE.exec("/w/jack_uk"), null);
// And the other way: the section regex must not claim a listing address.
check("the section regex does not match a listing address (3 segments)",
      SRE.exec("/w/jack_uk/listing/" + SKU), null);
truthy("but still matches a plain section", !!SRE.exec("/w/jack_uk/sales"));

// ---------------------------------------------------------------------------
console.log("\nthe page itself");
// ---------------------------------------------------------------------------
const els = {};
function el(id){
  if(!els[id]) els[id] = {id:id, innerHTML:"", style:{}, dataset:{}};
  return els[id];
}
const bodyCls = new Set();
globalThis.window = globalThis;
globalThis.document = {
  getElementById: id => (id === "pdp" ? el("pdp") : null),
  body: {classList: {add: c => bodyCls.add(c), remove: c => bodyCls.delete(c),
                     contains: c => bodyCls.has(c)}},
};
globalThis.scrollY = 0;
globalThis.scrollTo = (x, y) => { globalThis.__scrolledTo = y; globalThis.scrollY = y; };
globalThis.esc = s => String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
                                                .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
globalThis.sid = s => String(s).replace(/[^a-zA-Z0-9]/g, "_");
globalThis.toast = m => { globalThis.__toast = m; };
globalThis.closeDrawer = () => { globalThis.__drawerClosed = true; };
globalThis.altaSyncUrl = () => { globalThis.__urlSynced = (globalThis.__urlSynced||0) + 1; };
globalThis.lvEnsure = () => { globalThis.__lvAsked = true; };
globalThis.loadSchemas = () => Promise.resolve();
globalThis.bulletMeter = () => {};
globalThis.SCHEMAS = {};
globalThis.lsStatusOf = r => String(r.status||"").toUpperCase();
globalThis.rowAsin = r => ({own: r.asin || "", source: ""});
globalThis.rowMkt = () => "UK";
globalThis.dwTitleParts = (r, cid) => ({cid, editor:"<TITLE-EDITOR>", count:"<COUNT>",
                                        indexTag:"<IDXTAG>", warnNote:"<TITLEWARN>"});
globalThis._dwWarnings = r => (r.warnings ? "<WARNINGS>" : "");
globalThis._fullDataParts = () => ({highlights:"<HI>", bullets:"<BUL>", search:"<SRCH>",
                                    desc:"<DESC>", images:"<IMG>", identity:"<IDENT>",
                                    attrs:"<ATTRS>", folds:"<FOLDS>"});
globalThis.ACTIVE_WS = {key:"jack_uk", brand:"Jack Reacherd"};
globalThis.WS_READONLY = false;
const ROW = {sku:SKU, status:"LIVE", asin:"B0H8VHDX8B", title:"A brush", product_type:"BRUSH",
             warnings:'[{"severity":"high"}]'};
globalThis.ROWS = [ROW];

const ctx = vm.createContext(globalThis);
vm.runInContext(pdpSrc, ctx, {filename:"pdp.js"});
const G = e => vm.runInContext(e, ctx);   // PDP_SKU is a `let`, not a global prop

check("closed to begin with", ctx.pdpIsOpen(), false);
check("and it has no address while closed", ctx.pdpPath(), "");

globalThis.scrollY = 742;                       // the grid, scrolled down
ctx.pdpOpen(SKU);
check("opening records the listing", G("PDP_SKU"), SKU);
truthy("the page is shown",        el("pdp").style.display === "block");
truthy("the grid is hidden by a body class", bodyCls.has("pdp-on"));
truthy("the drawer is closed, so there is only one title box on screen",
       globalThis.__drawerClosed);
truthy("Amazon's live values are asked for", globalThis.__lvAsked);
check("the address becomes the listing's",
      ctx.pdpPath(), "/w/jack_uk/listing/" + encodeURIComponent(SKU));

const html = el("pdp").innerHTML;
console.log("\n  ...and it is built from the drawer's blocks, not new ones");
[["title editor","<TITLE-EDITOR>"],["images","<IMG>"],["bullets","<BUL>"],
 ["highlights","<HI>"],["description","<DESC>"],["search terms","<SRCH>"],
 ["warnings","<WARNINGS>"],["identity","<IDENT>"],["compliance folds","<FOLDS>"],
 ["attributes","<ATTRS>"]].forEach(([name, mark]) =>
   truthy("  " + name + " is on the page", html.indexOf(mark) >= 0));

console.log("\n  ...laid out as the mockup draws it");
const iLeft = html.indexOf('class="pdp-col left"'), iRight = html.indexOf('class="pdp-col right"');
const iWide = html.indexOf('class="pdp-wide"');
truthy("a left column, then a right one", iLeft >= 0 && iRight > iLeft);
truthy("attributes full width, below both", iWide > iRight);
truthy("copy on the left",    html.indexOf("<DESC>") > iLeft && html.indexOf("<DESC>") < iRight);
truthy("context on the right", html.indexOf("<IDENT>") > iRight);
truthy("warnings first in the right column",
       html.indexOf("<WARNINGS>") < html.indexOf("<IDENT>"));
truthy("the status badge is shown", html.indexOf("pdp-badge live") >= 0);
truthy("the ASIN is shown",         html.indexOf("B0H8VHDX8B") >= 0);
truthy("back, Preview, Auto-fix and Submit are all present",
       /pdpClose\(\)/.test(html) && /previewOne\(/.test(html)
       && /autoFixLoop\(/.test(html) && /submitOne\(/.test(html));

console.log("\n  ...and a read-only workspace cannot submit from here either");
globalThis.WS_READONLY = true; ctx.pdpRender();
check("Submit is gone", /submitOne\(/.test(el("pdp").innerHTML), false);
truthy("and it says why", el("pdp").innerHTML.indexOf("Read-only workspace") >= 0);
globalThis.WS_READONLY = false; ctx.pdpRender();

console.log("\n  ...going back restores the grid exactly as it was");
ctx.pdpClose();
check("the page is closed",   ctx.pdpIsOpen(), false);
truthy("the grid is shown again", !bodyCls.has("pdp-on"));
check("and the scroll position is put back", globalThis.__scrolledTo, 742);
check("the address goes back to the section's", ctx.pdpPath(), "");

console.log("\n  ...moving between two listings keeps the ORIGINAL grid position");
globalThis.scrollY = 300; ctx.pdpOpen(SKU);      // enter from the grid at 300
globalThis.scrollY = 0;                          // the page itself is at the top
globalThis.ROWS.push({sku:"OTHER", status:"QUEUED", title:"b"});
ctx.pdpOpen("OTHER");                            // straight to another listing
ctx.pdpClose();
check("back still lands where the grid was, not at 0", globalThis.__scrolledTo, 300);

console.log("\n  ...and a SKU that is not on this screen is refused, not shown empty");
check("pdpOpenFromUrl says so", ctx.pdpOpenFromUrl("NOT_A_REAL_SKU"), false);
check("  the page stays closed", ctx.pdpIsOpen(), false);
check("pdpOpenFromUrl opens a real one", ctx.pdpOpenFromUrl(SKU), true);
ctx.pdpClose();

console.log("\n  ...a builder that throws does not leave a blank page");
ctx.pdpOpen(SKU);                       // the previous block closed it
const _goodParts = globalThis._fullDataParts;
globalThis._fullDataParts = () => { throw new Error("schema exploded"); };
ctx.pdpRender();
truthy("the failure is named",  el("pdp").innerHTML.indexOf("schema exploded") >= 0);
truthy("the raw row is still readable", el("pdp").innerHTML.indexOf("B0H8VHDX8B") >= 0);
truthy("and there is still a way back", el("pdp").innerHTML.indexOf("pdpClose()") >= 0);
globalThis._fullDataParts = _goodParts;

console.log("\n  ...a rebuild only touches the listing that is open");
ctx.pdpOpen(SKU);
el("pdp").innerHTML = "STALE";
ctx.pdpRebuild("SOME_OTHER_SKU");
check("another SKU's rebuild is ignored", el("pdp").innerHTML, "STALE");
ctx.pdpRebuild(SKU);
truthy("its own rebuild redraws", el("pdp").innerHTML.indexOf("<ATTRS>") >= 0);

// ---------------------------------------------------------------------------
console.log("\nthe rebuild path reaches both views");
// ---------------------------------------------------------------------------
truthy("_rebuildDrawerData also refreshes the product page",
       /_rebuildDrawerData\(sku\)\{[\s\S]{0,900}pdpRebuild\(sku\)/.test(AUTOFIX));
const DA = fs.readFileSync("static/js/drawer_attributes.js", "utf8");
truthy("and so does the live-attributes answer when it lands",
       /PDP_SKU[\s\S]{0,200}pdpRebuild\(sku\)/.test(DA));

console.log("\n%d failed", fails);
process.exit(fails ? 1 : 0);
