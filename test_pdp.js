// The full-screen listing editor: what it is made of, and how you get in and out.
//
// WHAT THIS PINS
//
// The page is deliberately almost empty of its own logic -- it arranges blocks
// the drawer already builds and presents the attribute model the drawer already
// computes. That design has a small number of ways to fail badly, and none of
// them are visual:
//
//   * _fullDataParts returns the blocks and _fullDataInner composes them. Add
//     one and forget to compose it and the DRAWER silently loses a section --
//     no error, no blank space, just a panel that stopped being there.
//   * Two title editors saving to the same cell is how they end up disagreeing
//     about what you typed. There must be exactly one, used by both views.
//   * The attribute table must not re-decide which fields Amazon requires. If
//     it did, one view could mark a field required and the other not.
//   * A SKU is price_days_ASIN -- it has dots. If the router's section regex
//     swallows /w/x/listing/9.18_3Days_B0C6XTNXL8, a link to a real row lands
//     on the grid and looks ignored.
//   * The overlay must sit UNDER the toast, the menus and the dialogs, or
//     every "Saved ✓" and every confirm is invisible behind it.
//   * Escape must not close the page out from under a half-typed field.
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
const PDPJS    = fs.readFileSync("static/js/pdp.js", "utf8");
const PDPCSS   = fs.readFileSync("static/css/pdp.css", "utf8");
const DASHCSS  = fs.readFileSync("static/css/dashboard.css", "utf8");

// ---------------------------------------------------------------------------
console.log("\nevery block that is computed is also composed");
// ---------------------------------------------------------------------------
const retM = /return \{highlights:[\s\S]*?attrModel: \{[\s\S]*?\}\};/.exec(AUTOFIX);
truthy("_fullDataParts returns a named object", !!retM);

const innerM = /function _fullDataInner\(r\)\{[\s\S]*?\n\}/.exec(AUTOFIX);
truthy("_fullDataInner exists as the drawer's composer", !!innerM);
const composed = innerM
  ? [...new Set((innerM[0].match(/\bp\.(\w+)/g) || []).map(s => s.slice(2)))].sort() : [];
// The drawer's own eight. The extras (the split halves and the model) exist for
// the product page and are deliberately NOT in the drawer's composition --
// adding them would show identity twice.
check("the drawer still composes its original eight blocks", composed,
      ["attrs","bullets","desc","folds","highlights","identity","images","search"]);

const pdpUses = [...new Set((PDPJS.match(/\bp\.(\w+)/g) || []).map(s => s.slice(2)))].sort();
// `attrs` (the drawer's cell grid) is deliberately absent: this page draws the
// same attributes as a table from attrModel instead.
check("and the product page places the rest", pdpUses,
      ["addCtrl","attrModel","bullets","compliance","desc","highlights",
       "identityOnly","images","offerOnly","search","tools"]);
// Nothing may be produced that NO view shows. Only TOP-LEVEL keys count --
// everything after `attrModel: {` is that model's own contents, not a block.
const topLevel = retM ? retM[0].slice(0, retM[0].indexOf("attrModel: {")) : "";
const produced = [...new Set((topLevel.match(/(?:^|[{,]\s*)(\w+):/gm) || [])
  .map(s => s.replace(/[^\w:]/g, "").slice(0, -1)))].concat("attrModel");
const shown = new Set([...composed, ...pdpUses]);
check("no block is produced that neither view shows",
      produced.filter(k => k && !shown.has(k)), []);

console.log("\n  ...and the split halves add up to the whole");
truthy("identity+offer is what the drawer's one section holds",
       /secIdentity = dwSection\("Identity and offer", _ptTag, idRows \+ offerRows\)/.test(AUTOFIX));
truthy("compliance+tools is what the drawer's fold run holds",
       /const folds = _vf\.compliance \+ toolFolds;/.test(AUTOFIX));
truthy("and _dwVerdictFolds is still those same two groups joined",
       /return p\.compliance \+ p\.mirror;/.test(LISTINGS));

// ---------------------------------------------------------------------------
console.log("\nthere is exactly ONE title editor");
// ---------------------------------------------------------------------------
truthy("dwTitleParts is defined once, in drawer.js", /function dwTitleParts\(/.test(DRAWER));
check("  and not a second time anywhere else",
      (AUTOFIX + LISTINGS + PDPJS).match(/function dwTitleParts\(/g), null);
check("the drawer calls it", /dwTitleParts\(r,/.test(LISTINGS), true);
check("the product page calls it too", /dwTitleParts\(r,/.test(PDPJS), true);
const titleSaves = (DRAWER + LISTINGS + PDPJS + AUTOFIX).match(/col.{0,2},.{0,2}Title/g) || [];
check("only one control in the app saves to the Title column", titleSaves.length, 1);

// ---------------------------------------------------------------------------
console.log("\nthe attribute table decides nothing of its own");
// ---------------------------------------------------------------------------
truthy("it is handed the model rather than deriving one",
       /function pdpAttrTable\(m\)/.test(PDPJS));
truthy("required comes from the model's reqList / flagged, not a new rule",
       /m\.reqList/.test(PDPJS) && /m\.flagged\[k\]/.test(PDPJS));
truthy("allowed values come from the model's enums",   /m\.enums\[k\]/.test(PDPJS));
truthy("the editable cell is the shared editCell()",   /editCell\(sku, "attr", k/.test(PDPJS));
truthy("the comparison is the shared lvVerdict()",     /lvVerdict\(sku, k, val\)/.test(PDPJS));
truthy("and 'use' is the shared lvUse()",              /lvUse\(/.test(PDPJS));
// The table must not build its own list of which fields exist.
check("it never re-reads the schema itself",
      /SCHEMAS\[/.test(PDPJS.slice(PDPJS.indexOf("function pdpAttrTable"))), false);
check("nor re-parses Amazon's flagged-field notes",
      /parseFlagged\(/.test(PDPJS), false);

// ---------------------------------------------------------------------------
console.log("\nclicking a listing goes through one function");
// ---------------------------------------------------------------------------
truthy("openListing exists", /function openListing\(/.test(LISTINGS));
truthy("it prefers the full-screen page", /pdpOpen\(sku\)/.test(LISTINGS));
truthy("and falls back to the drawer when pdp.js has not loaded",
       /typeof pdpOpen === "function"[\s\S]{0,80}openDrawer\(sku\)/.test(LISTINGS));
check("the tile image, tile body, table row and Review button all use it",
      (LISTINGS.match(/openListing\('/g) || []).length, 4);
truthy("the drawer keeps its own way back to full screen",
       /pdpOpen\('\$\{esc\(r\.sku\)\}'\)/.test(LISTINGS));
truthy("and the drawer is still reachable from the grid's badges / tile menu",
       (LISTINGS.match(/openDrawer\('\$\{esc\(/g) || []).length >= 3);

// ---------------------------------------------------------------------------
console.log("\nthe overlay sits UNDER everything that must float over it");
// ---------------------------------------------------------------------------
const zOf = (css, re) => { const m = re.exec(css); return m ? parseInt(m[1], 10) : null; };
const zPdp = zOf(PDPCSS, /#pdp\{[\s\S]*?z-index:\s*(\d+)/);
truthy("the overlay declares a z-index", zPdp !== null);
[["the toast — every \"Saved ✓\"", /\.toast\{[^}]*?z-index:(\d+)/],
 ["the tile menu — what More opens", /\.tilemenu\{[^}]*?z-index:(\d+)/],
 ["the image library / studio modal", /\.modalwrap\{[^}]*?z-index:(\d+)/],
 ["the run queue panel", /\.rqpanel\{[^}]*?z-index:(\d+)/]].forEach(function(t){
  const z = zOf(DASHCSS, t[1]);
  check("  " + t[0] + " is above it", (z !== null && z > zPdp), true);
});
const zDrawer = zOf(DASHCSS, /\.drawer\{position:fixed[^}]*?z-index:(\d+)/);
check("  but it covers the drawer", (zDrawer !== null && zPdp > zDrawer), true);
// The dialogs live in their own file and are far above everything.
const zDlg = zOf(fs.readFileSync("static/css/dialog.css", "utf8"), /\.uidlg-wrap\{[^}]*?z-index:(\d+)/);
check("  and uiConfirm is above it", (zDlg !== null && zDlg > zPdp), true);

// ---------------------------------------------------------------------------
console.log("\nthe address, using the router's OWN regexes");
// ---------------------------------------------------------------------------
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
check("the section regex does not match a listing address",
      SRE.exec("/w/jack_uk/listing/" + SKU), null);
truthy("but still matches a plain section", !!SRE.exec("/w/jack_uk/sales"));

// ---------------------------------------------------------------------------
console.log("\nthe page itself");
// ---------------------------------------------------------------------------
const els = {};
function el(id){
  if(!els[id]) els[id] = {id:id, innerHTML:"", style:{},
                          classList:{_s:new Set(),
                            add(c){this._s.add(c);}, remove(c){this._s.delete(c);},
                            contains(c){return this._s.has(c);}}};
  return els[id];
}
const bodyCls = new Set();
let keyHandler = null;
globalThis.window = globalThis;
globalThis.document = {
  getElementById: id => (id === "pdp" ? el("pdp") : null),
  querySelector: () => globalThis.__dlgOpen || null,
  activeElement: null,
  addEventListener: (t, fn) => { if(t === "keydown") keyHandler = fn; },
  body: {classList: {add: c => bodyCls.add(c), remove: c => bodyCls.delete(c),
                     contains: c => bodyCls.has(c)}},
};
globalThis.requestAnimationFrame = fn => fn();
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
globalThis.CUR_SYMBOL = "£";
globalThis.lsStatusOf = r => String(r.status||"").toUpperCase();
globalThis.lsWarnings = r => ({n:(r.warnings||[]).length, high:1, list:r.warnings||[]});
globalThis.rowAsin = r => ({own: r.asin || "", source: ""});
globalThis.rowMkt = () => "UK";
globalThis.isAmazonLive = () => true;
globalThis.ownLiveAsin = r => r.asin || "";
globalThis._rowImages = () => ["http://img/1.jpg"];
globalThis._dwCost = () => "£9.18";
globalThis._cleanLabel = s => String(s);
globalThis.identifierPanel = () => "<IDPANEL>";
globalThis.complianceBanner = () => "<COMPBANNER>";
globalThis.editCell = (sku,t,k,v) => '<EDIT:' + k + ':' + (v==null?"":v) + '>';
globalThis.lvGet = () => globalThis.__live;
globalThis.lvVerdict = (sku, k, val) => {
  const L = globalThis.__live; if(!L || L.state !== "ok") return "";
  const has = Object.prototype.hasOwnProperty.call(L.values, k);
  const app = String(val == null ? "" : val).trim();
  if(!has && !app) return ""; if(!has) return "app_only"; if(!app) return "live_only";
  return String(L.values[k]) === app ? "same" : "differs";
};
globalThis.dwTitleParts = (r, cid) => ({cid, editor:"<TITLE-EDITOR>", count:"<COUNT>",
                                        indexTag:"<IDXTAG>", warnNote:"<TITLEWARN>"});
globalThis._dwWarnings = r => (r.warnings && r.warnings.length ? "<WARNINGS>" : "");
globalThis._fullDataParts = () => ({
  highlights:"<HI>", bullets:"<BUL>", search:"<SRCH>", desc:"<DESC>", images:"<IMG>",
  identity:"<IDENT>", attrs:"<ATTRSGRID>", folds:"<FOLDS>",
  identityOnly:"<IDENTONLY>", offerOnly:"<OFFERONLY>",
  compliance:"<COMPLIANCE>", tools:"<TOOLS>", addCtrl:"<ADDCTRL>",
  attrModel:{sku:SKU, a:{colour:"black", size:"small"},
             aKeys:["colour","size"], missing:["material"],
             enums:{colour:["black","white"]}, reqList:["material"], allAttrs:[],
             titles:{}, flagged:{}, subs:{}, prov:{}, addable:[], productType:"BRUSH"}});
globalThis.ACTIVE_WS = {key:"jack_uk", brand:"Jack Reacherd"};
globalThis.WS_READONLY = false;
const ROW = {sku:SKU, status:"LIVE", asin:"B0H8VHDX8B", title:"A brush",
             product_type:"BRUSH", brand:"Nestwell", barcode:"4553334465572",
             profit:"8.57", claim_flags:[{}], warnings:[{severity:"high"}]};
globalThis.ROWS = [ROW];
globalThis.__live = {state:"ok", values:{colour:"black", material:"steel"}, multi:{},
                     amazon_status:"BUYABLE"};

const ctx = vm.createContext(globalThis);
vm.runInContext(PDPJS, ctx, {filename:"pdp.js"});
const G = e => vm.runInContext(e, ctx);

check("closed to begin with", ctx.pdpIsOpen(), false);
check("and it has no address while closed", ctx.pdpPath(), "");

globalThis.scrollY = 742;
ctx.pdpOpen(SKU);
check("opening records the listing", G("PDP_SKU"), SKU);
truthy("the panel is shown",  el("pdp").style.display === "block");
truthy("and slides in",       el("pdp").classList.contains("in"));
truthy("the body is locked so the grid cannot scroll behind it", bodyCls.has("pdp-on"));
truthy("the drawer is closed, so there is only one title box on screen",
       globalThis.__drawerClosed);
truthy("Amazon's live values are asked for", globalThis.__lvAsked);
check("the address becomes the listing's",
      ctx.pdpPath(), "/w/jack_uk/listing/" + encodeURIComponent(SKU));

let html = el("pdp").innerHTML;
console.log("\n  ...the hero, as the mockup draws it");
truthy("the product title",  html.indexOf("A brush") >= 0);
truthy("the ASIN",           html.indexOf("B0H8VHDX8B") >= 0);
truthy("the SKU",            html.indexOf(SKU) >= 0);
truthy("the barcode",        html.indexOf("4553334465572") >= 0);
truthy("the brand",          html.indexOf("Nestwell") >= 0);
truthy("a status badge that includes what Amazon says",
       html.indexOf("LIVE · BUYABLE") >= 0);
truthy("the profit badge",   html.indexOf("Profit £8.57") >= 0);
truthy("a warning badge",    html.indexOf("1 warning") >= 0);

console.log("\n  ...the top bar and the rail");
truthy("back, Preview, Auto-fix, Submit and More",
       /pdpClose\(\)/.test(html) && /previewOne\(/.test(html) && /autoFixLoop\(/.test(html)
       && /submitOne\(/.test(html) && /drawerMore\(/.test(html));
truthy("Image studio and Ask Claude on the rail",
       /openStudioSingle\(/.test(html) && /askAbout\(/.test(html));
truthy("the four checks",
       /pdp-ck/.test(html) && html.indexOf("Restricted") >= 0
       && html.indexOf("Amazon feedback") >= 0);
truthy("a claim risk is counted, not just named", html.indexOf("1 claim risk") >= 0);
truthy("all five tabs", PDP_TABS_ok(html));
function PDP_TABS_ok(h){
  return ["Product details","Images","Attributes","Offer","Compliance"]
    .every(t => h.indexOf(t) >= 0);
}

console.log("\n  ...a blocking problem is never put behind a tab (Rule 1)");
truthy("the identifier panel is on every tab", html.indexOf("<IDPANEL>") >= 0);
truthy("and so is the compliance banner",      html.indexOf("<COMPBANNER>") >= 0);

console.log("\n  ...each tab shows its own blocks and not the others'");
const tabHas = {};
["details","images","attributes","offer","compliance"].forEach(function(t){
  ctx.pdpTab(t); tabHas[t] = el("pdp").innerHTML;
});
truthy("details: title, highlights, bullets, description, search terms",
       ["<TITLE-EDITOR>","<HI>","<BUL>","<DESC>","<SRCH>"].every(m => tabHas.details.indexOf(m) >= 0));
check("  and not the attributes grid", tabHas.details.indexOf("<ATTRSGRID>") >= 0, false);
truthy("images: the image block", tabHas.images.indexOf("<IMG>") >= 0);
truthy("offer: the offer rows, then identity",
       tabHas.offer.indexOf("<OFFERONLY>") >= 0
       && tabHas.offer.indexOf("<IDENTONLY>") > tabHas.offer.indexOf("<OFFERONLY>"));
truthy("compliance: warnings, the verdicts, then the tools",
       ["<WARNINGS>","<COMPLIANCE>","<TOOLS>"].every(m => tabHas.compliance.indexOf(m) >= 0));
truthy("attributes: the add-optional picker is kept",
       tabHas.attributes.indexOf("<ADDCTRL>") >= 0);

console.log("\n  ...the attributes table");
const at = tabHas.attributes;
truthy("a row per attribute, with Amazon's value beside ours",
       at.indexOf("<EDIT:colour:black>") >= 0 && at.indexOf("<EDIT:size:small>") >= 0);
truthy("a required field Amazon has not been asked about still appears",
       at.indexOf("<EDIT:material:>") >= 0);
truthy("  marked as required",  at.indexOf("pdp-req") >= 0 || at.indexOf("pdp-reqsoft") >= 0);
truthy("agreement is shown",    at.indexOf("pdp-ai match") >= 0);
truthy("only-on-Amazon is shown and offers 'use'",
       at.indexOf("pdp-ai onlyamz") >= 0 && /lvUse\(/.test(at));
truthy("only-ours is shown",    at.indexOf("pdp-ai onlyus") >= 0);
truthy("the summary counts",    at.indexOf("1 match") >= 0 && at.indexOf("1 only Amazon") >= 0);
truthy("filters are offered",   at.indexOf("pdpAttrFilter(") >= 0);
truthy("and bulk fill when Amazon has fields we do not",
       at.indexOf("lvFillEmpty(") >= 0);

console.log("\n  ...filtering hides rows without changing the counts");
ctx.pdpTab("attributes");            // the loop above left us on Compliance
ctx.pdpAttrFilter("differs");
const filtered = el("pdp").innerHTML;
check("a filter with no matches says so, rather than showing an empty box",
      filtered.indexOf("Nothing matches this filter") >= 0, true);
truthy("the summary still reports every attribute", filtered.indexOf("1 match") >= 0);
ctx.pdpAttrFilter("all");

console.log("\n  ...a multi-valued attribute is read-only here too");
globalThis.__live = {state:"ok", values:{colour:"black"}, multi:{colour:3}, amazon_status:""};
ctx.pdpTab("attributes");
const multi = el("pdp").innerHTML;
check("no editor is offered for it", multi.indexOf("<EDIT:colour:") >= 0, false);
truthy("and it says how many Amazon holds", multi.indexOf("pdp-ro") >= 0);
globalThis.__live = {state:"ok", values:{colour:"black", material:"steel"}, multi:{},
                     amazon_status:"BUYABLE"};

console.log("\n  ...a failed read is never reported as \"Amazon has nothing\"");
globalThis.__live = {state:"error", values:{}, multi:{}, error:"timed out"};
ctx.pdpTab("attributes");
truthy("the reason is shown", el("pdp").innerHTML.indexOf("could not read Amazon: timed out") >= 0);
globalThis.__live = {state:"ok", values:{colour:"black", material:"steel"}, multi:{},
                     amazon_status:"BUYABLE"};
ctx.pdpTab("details");

console.log("\n  ...a read-only workspace cannot submit from here either");
globalThis.WS_READONLY = true; ctx.pdpRender();
check("Submit is gone", /submitOne\(/.test(el("pdp").innerHTML), false);
truthy("and it says why", el("pdp").innerHTML.indexOf("Read-only workspace") >= 0);
globalThis.WS_READONLY = false; ctx.pdpRender();

console.log("\n  ...Escape");
globalThis.document.activeElement = {tagName:"DIV", isContentEditable:true, blur(){ globalThis.__blurred = true; }};
keyHandler({key:"Escape"});
check("does NOT close the page while you are typing", ctx.pdpIsOpen(), true);
truthy("  it leaves the field instead, which commits the edit", globalThis.__blurred);
globalThis.document.activeElement = {tagName:"BODY", isContentEditable:false};
globalThis.__dlgOpen = {};                       // a confirm dialog is open
keyHandler({key:"Escape"});
check("nor while a dialog is over it", ctx.pdpIsOpen(), true);
globalThis.__dlgOpen = null;
keyHandler({key:"Escape"});
check("but it does close otherwise", ctx.pdpIsOpen(), false);
check("and the grid's scroll position comes back", globalThis.__scrolledTo, 742);
check("a stray Escape with nothing open is harmless",
      (function(){ try{ keyHandler({key:"Escape"}); return "fine"; }catch(e){ return String(e); } })(), "fine");

console.log("\n  ...going back restores the grid exactly as it was");
ctx.pdpOpen(SKU); ctx.pdpClose();
truthy("the body lock is released", !bodyCls.has("pdp-on"));
truthy("the slide class is cleared", !el("pdp").classList.contains("in"));
check("the address goes back to the section's", ctx.pdpPath(), "");

console.log("\n  ...moving between two listings keeps the ORIGINAL grid position");
globalThis.scrollY = 300; ctx.pdpOpen(SKU);
globalThis.scrollY = 0;
globalThis.ROWS.push({sku:"OTHER", status:"QUEUED", title:"b"});
ctx.pdpOpen("OTHER");
check("  and a new listing starts on the first tab", G("PDP_TAB"), "details");
ctx.pdpClose();
check("back still lands where the grid was, not at 0", globalThis.__scrolledTo, 300);

console.log("\n  ...a SKU that is not on this screen is refused, not shown empty");
check("pdpOpenFromUrl says so", ctx.pdpOpenFromUrl("NOT_A_REAL_SKU"), false);
check("  the page stays closed", ctx.pdpIsOpen(), false);
check("pdpOpenFromUrl opens a real one", ctx.pdpOpenFromUrl(SKU), true);

console.log("\n  ...a builder that throws does not leave a blank page");
const _good = globalThis._fullDataParts;
globalThis._fullDataParts = () => { throw new Error("schema exploded"); };
ctx.pdpRender();
truthy("the failure is named",  el("pdp").innerHTML.indexOf("schema exploded") >= 0);
truthy("the raw row is still readable", el("pdp").innerHTML.indexOf("B0H8VHDX8B") >= 0);
truthy("and there is still a way back", el("pdp").innerHTML.indexOf("pdpClose()") >= 0);
globalThis._fullDataParts = _good;

console.log("\n  ...a rebuild only touches the listing that is open");
ctx.pdpOpen(SKU);
el("pdp").innerHTML = "STALE";
ctx.pdpRebuild("SOME_OTHER_SKU");
check("another SKU's rebuild is ignored", el("pdp").innerHTML, "STALE");
ctx.pdpRebuild(SKU);
truthy("its own rebuild redraws", el("pdp").innerHTML.indexOf("<TITLE-EDITOR>") >= 0);

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
