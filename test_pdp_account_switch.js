// The product page must not carry one account's listing into another account.
//
// WHAT HAPPENED (read from the code on 27 Sep 2026, then run here to prove it)
//
// SKUs are not unique across accounts: the owner lists the same product on two
// of his companies and may reuse the SKU. The product page (#pdp) holds state
// keyed by SKU alone, and switching account did nothing to it:
//
//   * enterAccount() never closed the page, so it stayed open on account A's
//     listing while CUR_ACCOUNT became B (reachable with the Ctrl+K palette,
//     which sits above the page, and with Back/Forward).
//   * A save from that still-open page is stamped with acctBody() -- the
//     account open NOW, i.e. B -- so A's page wrote into B's same-SKU row.
//   * LIVE_ATTRS (Amazon's live data for the page) and PDPI (the image tab)
//     are keyed by SKU only and were never cleared, so B's page for the same
//     SKU showed A's Amazon copy and A's picture slots.
//   * A reply sent for A that landed after the switch (/row, live attributes)
//     was checked by SKU only, so it was merged into / painted over B.
//
// These tests run the REAL shell.js / pdp.js / drawer_attributes.js /
// pdp_images.js / autofix.js / reqscope.js in a sandbox with a stub page and a
// scripted fetch whose replies are released by the test, so a "late reply" is
// exactly that. They do not start the app or touch any real account.
//
// Run: node test_pdp_account_switch.js
const fs = require("fs"), vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(74) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

/* ---- a stub page: every element exists and accepts whatever is done to it ---- */
function makeEl(id){
  const classes = new Set();
  return {
    id, innerHTML: "", textContent: "", value: "", style: {}, dataset: {},
    onclick: null, children: [], tagName: "DIV",
    classList: {
      add: (...c) => c.forEach(x => classes.add(x)),
      remove: (...c) => c.forEach(x => classes.delete(x)),
      toggle: (c, on) => { const v = on === undefined ? !classes.has(c) : !!on;
                           v ? classes.add(c) : classes.delete(c); return v; },
      contains: c => classes.has(c),
    },
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener(){}, removeEventListener(){}, setAttribute(){},
    getAttribute: () => null, removeAttribute(){}, appendChild(){}, remove(){},
    contains: () => false, focus(){}, blur(){}, scrollIntoView(){},
    getBoundingClientRect: () => ({top: 0, left: 0, width: 0, height: 0}),
  };
}

function makeSandbox(){
  const els = {};
  const document = {
    getElementById: id => (els[id] = els[id] || makeEl(id)),
    querySelector: () => null, querySelectorAll: () => [],
    createElement: t => makeEl("new-" + t), addEventListener(){},
    removeEventListener(){}, body: makeEl("body"), activeElement: null,
    documentElement: makeEl("html"),
  };
  // A fetch whose every call is recorded and answered only when the test says.
  const calls = [];
  function fetch(url, opts){
    const call = {url: String(url), opts: opts || {}, body: null, resolve: null};
    try{ call.body = opts && opts.body ? JSON.parse(opts.body) : null; }catch(e){}
    const p = new Promise(res => { call.resolve = (json) => res({ok: true, status: 200,
                                        json: () => Promise.resolve(json)}); });
    calls.push(call);
    return p;
  }
  const ctx = {
    console, document, fetch, calls, els,
    setTimeout: (f) => 0, clearTimeout(){}, setInterval: () => 0, clearInterval(){},
    requestAnimationFrame: f => 0,
    localStorage: {getItem: () => null, setItem(){}, removeItem(){}},
    sessionStorage: {getItem: () => null, setItem(){}, removeItem(){}},
    location: {pathname: "/", search: "", hash: "", href: "http://x/"},
    history: {pushState(){}, replaceState(){}, state: null},
    navigator: {userAgent: "node"}, scrollTo(){}, scrollY: 0,
    addEventListener(){}, removeEventListener(){}, getComputedStyle: () => ({}),
    matchMedia: () => ({matches: false, addEventListener(){}}),
    URLSearchParams, Promise, Set, Map, JSON, Math, Date, String, Number, Array, Object,
  };
  ctx.window = ctx; ctx.self = ctx;
  vm.createContext(ctx);
  return ctx;
}

const FILES = ["static/js/reqscope.js", "static/js/shell.js", "static/js/pdp.js",
               "static/js/drawer_attributes.js", "static/js/pdp_images.js",
               "static/js/autofix.js"];

function load(){
  const ctx = makeSandbox();
  // Globals these files read but that live in files not loaded here
  // (listings.js, miles_template.js, ...). Declared first, only if nothing
  // loaded below declares them.
  const PRELUDE_NAMES = {
    ROWS: "[]", TABS: "[]", ROWS_LOADED: "false", DUP_INDEX: "null",
    LIVE_ITEMS: "[]", APLUS_BY_ASIN: "{}", APLUS_ERROR: "''", AMZ_STATE: "{}",
    LIST_SOURCE: "'drafts'", WS_MARKET: "''", CUR_SYMBOL: "'£'", SCHEMAS: "{}",
    LIVE_MIRROR: "{}", SELECTED: "new Set()", DRAWER_SKU: "''",
  };
  const srcAll = FILES.map(f => fs.readFileSync(f, "utf8")).join("\n");
  let prelude = "";
  for(const [k, v] of Object.entries(PRELUDE_NAMES)){
    const declared = new RegExp("^(?:let|const|var)\\s+" + k + "\\b", "m").test(srcAll);
    if(!declared) prelude += "var " + k + " = " + v + ";\n";
  }
  vm.runInContext(prelude, ctx, {filename: "prelude"});
  for(const f of FILES){
    vm.runInContext(fs.readFileSync(f, "utf8"), ctx, {filename: f});
  }
  // Screen-only helpers from files not loaded (or too heavy to draw here) are
  // replaced by counters. Everything under test -- enterAccount, pdpOpen,
  // pdpClose, pdpRefreshChecks, lvEnsure, lvGet, editField, acctBody/acctUrl --
  // is the real code.
  vm.runInContext(`
    var __renders = 0;
    pdpRender = function(){ __renders++; };
    function render(){} function summary(){} function toast(){}
    function loadRows(){} function loadLiveCatalog(){} function navTo(){}
    function altaSyncUrl(){} function renderDataSource(){} function closeAccounts(){}
    function crumbSet(){} function renderSwitchRows(){}
    function bmkRefresh(){} function startAutoSync(){} function screenForgetAll(){}
    function altaCountReset(){} function invBadgeRefresh(){} function closeDrawer(){}
    function mktSymbol(){ return "£"; } function _wsColorKey(){ return {bg:"", fg:""}; }
    function _initials(){ return ""; } function esc(s){ return String(s == null ? "" : s); }
    function isAmazonLive(){ return false; } function rowMkt(){ return "UK"; }
    function updateLocalCol(r, k, v){ r[k] = v; }
    function loadSchemas(){ return Promise.resolve(); }
    function pdpHeroRefresh(){} function pdpFieldEdited(){} function _pdpiPaint(){}
  `, ctx);
  return ctx;
}

const run = (ctx, code) => vm.runInContext(code, ctx);
const tick = () => new Promise(r => setImmediate(r));
async function settle(){ for(let i = 0; i < 20; i++) await tick(); }
function answerAll(ctx, match, json){
  ctx.calls.filter(c => c.url.indexOf(match) >= 0 && !c.done)
           .forEach(c => { c.done = true; c.resolve(json); });
}

const SKU = "9.99_2Days_B0SHARED01";   // the SAME SKU on both accounts

async function openOnA(ctx){
  run(ctx, `
    ACCOUNTS = [{id:"acct_a", label:"A", marketplaces:["UK"], default_marketplace:"UK"},
                {id:"acct_b", label:"B", marketplaces:["UK"], default_marketplace:"UK"}];
    CUR_ACCOUNT = ACCOUNTS[0];
    ROWS = [{sku:"${SKU}", status:"LIVE", title:"A's title", product_type:"HOME"}];
  `);
  run(ctx, `pdpOpen("${SKU}")`);
  await settle();
}

async function switchToB(ctx){
  const p = run(ctx, `enterAccount("acct_b")`);
  await settle();
  answerAll(ctx, "/accounts/select", {ok: true});
  await p;
  await settle();
  // B's own rows arrive (loadRows is stubbed; this is what it would set).
  run(ctx, `ROWS = [{sku:"${SKU}", status:"LIVE", title:"B's title", product_type:"HOME"}]`);
}

(async function main(){

console.log("\n1. the page does not stay open on A's listing after switching to B");
{
  const ctx = await load();
  await openOnA(ctx);
  check("opened on A: the page shows the shared SKU", run(ctx, "PDP_SKU"), SKU);
  await switchToB(ctx);
  check("after switching to B the page is closed", run(ctx, "PDP_SKU"), "");
  check("  and the page's overlay is taken down (body loses pdp-on)",
        ctx.document.body.classList.contains("pdp-on"), false);
}

console.log("\n2+3. nothing typed on A's page can be saved into B");
{
  const ctx = await load();
  await openOnA(ctx);
  await switchToB(ctx);
  // If the page were still open, this is what its next blur-save does: the
  // save helper is real, the body comes from acctBody() at the moment of saving.
  const stillOpen = run(ctx, "PDP_SKU") === SKU;
  if(stillOpen){
    run(ctx, `editField("${SKU}", "col", "Title", "typed on A's page")`);
    await settle();
    const edit = ctx.calls.find(c => c.url === "/edit");
    // Recorded, not asserted: this is the evidence of what the bug did.
    console.log("      [evidence] page still open after the switch; its save went to account="
                + JSON.stringify(edit && edit.body && edit.body.account));
  }
  check("no save from A's page can reach B: the page is not open to save from", stillOpen, false);
}

console.log("\n4. SKU-keyed page state from A is not shown for B's same SKU");
{
  const ctx = await load();
  await openOnA(ctx);
  // A's live attributes arrive while A is open.
  answerAll(ctx, "/listing/live_attributes", {ok: true, on_amazon: true,
            values: {item_name: "A's Amazon title"}, content: {}, multi: {}, issues: []});
  await settle();
  check("A's Amazon data was cached while A was open",
        run(ctx, `(lvGet("${SKU}")||{}).state`), "ok");
  run(ctx, `PDPI.sku = "${SKU}"; PDPI.library = ["a-picture.jpg"];`);   // A's image tab had loaded
  await switchToB(ctx);
  check("after the switch, B does not see A's Amazon data for the same SKU",
        run(ctx, `lvGet("${SKU}")`), null);
  check("  nor A's image tab state", run(ctx, "PDPI.sku"), "");
}

console.log("\n5. a reply sent for A that lands after the switch is dropped");
{
  const ctx = await load();
  await openOnA(ctx);
  const rowCall = ctx.calls.find(c => c.url.indexOf("/row?") === 0);
  truthy("the page asked /row for A", rowCall && rowCall.url.indexOf("account=acct_a") > 0);
  const lvCall = ctx.calls.find(c => c.url.indexOf("/listing/live_attributes") === 0);
  truthy("  and live attributes for A", lvCall && lvCall.url.indexOf("account=acct_a") > 0);
  await switchToB(ctx);
  // B opens the same SKU (as the palette or Back would leave it).
  run(ctx, `pdpOpen("${SKU}")`);
  await settle();
  // NOW A's replies land.
  rowCall.done = true;
  rowCall.resolve({ok: true, row: {sku: SKU, title: "A's title", identifier: {verdict: "A's"}}});
  lvCall.done = true;
  lvCall.resolve({ok: true, on_amazon: true, values: {item_name: "A's Amazon title"},
                  content: {}, multi: {}, issues: []});
  await settle();
  check("B's row keeps B's title (A's late /row reply not merged)",
        run(ctx, `(ROWS.find(x => x.sku === "${SKU}")||{}).title`), "B's title");
  check("B's row does not carry A's barcode verdict",
        run(ctx, `((ROWS.find(x => x.sku === "${SKU}")||{}).identifier||{}).verdict || null`), null);
  const lv = run(ctx, `(lvGet("${SKU}")||{}).values`);
  check("B's page does not show A's late Amazon data",
        lv && lv.item_name === "A's Amazon title", false);
}

console.log("\n5b. after the switch, B's page asks Amazon about B's own listing");
{
  const ctx = await load();
  await openOnA(ctx);
  await switchToB(ctx);
  const before = ctx.calls.filter(c => c.url.indexOf("/listing/live_attributes") === 0).length;
  run(ctx, `pdpOpen("${SKU}")`);
  await settle();
  const lvB = ctx.calls.filter(c => c.url.indexOf("/listing/live_attributes") === 0).slice(before);
  check("B's page makes its own live-attributes request", lvB.length, 1);
  truthy("  naming account B", lvB[0] && lvB[0].url.indexOf("account=acct_b") > 0);
  if(lvB[0]){
    lvB[0].done = true;
    lvB[0].resolve({ok: true, on_amazon: true, values: {item_name: "B's Amazon title"},
                    content: {}, multi: {}, issues: []});
  }
  await settle();
  check("  and B's answer is what B's page holds",
        run(ctx, `(lvGet("${SKU}")||{values:{}}).values.item_name`), "B's Amazon title");
}

console.log("\n7. a MARKETPLACE switch is a change of product context too");
{
  const ctx = await load();
  await openOnA(ctx);
  run(ctx, `WS_MARKET = "UK"`);
  const rowCall = ctx.calls.find(c => c.url.indexOf("/row?") === 0);
  answerAll(ctx, "/listing/live_attributes", {ok: true, on_amazon: true,
            values: {item_name: "UK title"}, content: {}, multi: {}, issues: []});
  await settle();
  const p = run(ctx, `switchAccountMarket("DE")`);
  await settle();
  answerAll(ctx, "/accounts/select", {ok: true});
  await p; await settle();
  check("switching UK -> DE closes the page", run(ctx, "PDP_SKU"), "");
  check("  and the UK Amazon data is not offered in DE", run(ctx, `lvGet("${SKU}")`), null);
  run(ctx, `pdpOpen("${SKU}")`);
  await settle();
  rowCall.done = true;
  rowCall.resolve({ok: true, row: {sku: SKU, title: "UK row", identifier: {verdict: "UK"}}});
  await settle();
  check("  a /row reply sent for UK is not merged into the DE page's row",
        run(ctx, `(ROWS.find(x => x.sku === "${SKU}")||{}).title`), "A's title");
}

console.log("\n8. re-entering the SAME account and marketplace changes nothing");
{
  const ctx = await load();
  await openOnA(ctx);
  run(ctx, `WS_MARKET = "UK"`);
  const p = run(ctx, `enterAccount("acct_a")`);
  await settle();
  answerAll(ctx, "/accounts/select", {ok: true});
  await p; await settle();
  check("the page stays open on the same listing", run(ctx, "PDP_SKU"), SKU);
}

console.log("\n9. an image-tab load started for A cannot fill B's image tab");
{
  const ctx = await load();
  await openOnA(ctx);
  run(ctx, `pdpImagesLoad("${SKU}", "HOME")`);
  await settle();
  const slotsA = ctx.calls.find(c => c.url.indexOf("/listing/image_slots") === 0);
  const libA = ctx.calls.find(c => c.url.indexOf("/media/list") === 0);
  await switchToB(ctx);
  run(ctx, `pdpOpen("${SKU}"); pdpImagesLoad("${SKU}", "HOME")`);
  await settle();
  slotsA.done = true; slotsA.resolve({ok: true, slots: [{key: "A-slot"}], live: true, checked: true});
  libA.done = true; libA.resolve({ok: true, folders: [{files: [{url: "a-picture.jpg"}]}]});
  await settle();
  check("B's image tab has none of A's slots",
        run(ctx, "PDPI.slots.map(s => s.key)"), []);
  check("  nor A's library", run(ctx, "PDPI.library.map(f => f.url)"), []);
  check("  and it is marked as B's (account::workspace::marketplace)", run(ctx, "PDPI.ctx"),
        "acct_b::acct_b::UK");
}

console.log("\n10. a field being typed in saves to ITS account before the switch");
{
  const ctx = await load();
  await openOnA(ctx);
  // A focused field inside the page whose blur saves (as dwBlurSave does).
  run(ctx, `
    var __field = {tagName: "DIV", isContentEditable: true,
                   blur: function(){ editField("${SKU}", "col", "Title", "typed on A"); }};
    document.activeElement = __field;
    document.getElementById("pdp").contains = function(el){ return el === __field; };
  `);
  await switchToB(ctx);
  const edit = ctx.calls.find(c => c.url === "/edit");
  check("the in-progress edit was saved", !!edit, true);
  check("  to account A, where it was typed", edit && edit.body && edit.body.account, "acct_a");
}

console.log("\n11. a late image-slot save for A does not touch B's row");
{
  const ctx = await load();
  await openOnA(ctx);
  run(ctx, `PDPI.sku = "${SKU}"; pdpImgAssign("main_product_image_locator", "a.jpg", {quiet: true})`);
  await settle();
  const assign = ctx.calls.find(c => c.url === "/edit");
  check("the slot save named account A", assign && assign.body && assign.body.account, "acct_a");
  await switchToB(ctx);
  assign.done = true; assign.resolve({ok: true});
  await settle();
  check("  B's same-SKU row is not given A's picture",
        run(ctx, `JSON.stringify((ROWS.find(x => x.sku === "${SKU}")||{}).attributes || {})`), "{}");
}

console.log("\n12. leaving the page on a switch does not add a history step for the old account");
{
  const ctx = await load();
  await openOnA(ctx);
  check("pdpLeaveContext exists", run(ctx, "typeof pdpLeaveContext"), "function");
  run(ctx, `var __syncs = 0; altaSyncUrl = function(){ __syncs++; };`);
  run(ctx, `if(typeof pdpLeaveContext === "function") pdpLeaveContext();`);
  check("closing for a context change leaves the address bar to the switch", run(ctx, "__syncs"), 0);
  run(ctx, `pdpOpen("${SKU}"); __syncs = 0; pdpClose();`);
  check("  while an ordinary close still updates it", run(ctx, "__syncs"), 1);
}

console.log("\n13. entering another workspace (brand view) closes the page");
{
  const ctx = await load();
  await openOnA(ctx);
  run(ctx, `
    VIEWS = [{key: "brand_x", label: "Brand X", brand: "X", marketplace: "US"}];
    ACTIVE_WS = {key: "acct_a", label: "A", account: true};
    function _wsColor(){ return {bg: "", fg: ""}; } function _mktOf(v){ return v.marketplace || ""; }
    function updateSelBar(){}
  `);
  const p = run(ctx, `enterWorkspace("brand_x")`);
  await settle();
  answerAll(ctx, "/view/set", {ok: true});
  try{ await p; }catch(e){ /* screen-only steps after the switch are not under test */ }
  await settle();
  check("the page is closed", run(ctx, "PDP_SKU"), "");
}

console.log("\n14. a FAILED marketplace detection for another account moves nothing");
{
  const ctx = await load();
  await openOnA(ctx);
  run(ctx, `WS_MARKET = "UK"; CUR_ACCOUNT.has_creds = true;`);
  const p = run(ctx, `detectMarketplaces("acct_b")`);
  await settle();
  answerAll(ctx, "/accounts/detect_marketplaces", {ok: false, error: "no role"});
  await settle();
  answerAll(ctx, "/accounts/list", {ok: true, accounts: [
    {id: "acct_a", label: "A", marketplaces: ["UK"], has_creds: true},
    {id: "acct_b", label: "B", marketplaces: ["DE"], has_creds: true}]});
  await p; await settle();
  check("the open marketplace is still UK", run(ctx, "WS_MARKET"), "UK");
  check("  and the page is still open on A's listing", run(ctx, "PDP_SKU"), SKU);
}

console.log("\n15. Back from A's listing to B's GRID saves the field being typed, to A, and closes the page");
{
  const ctx = await load();
  await openOnA(ctx);
  run(ctx, `
    ACTIVE_WS = {key: "acct_a", label: "A", account: true};
    VIEWS = [];
    var __field = {tagName: "DIV", isContentEditable: true,
                   blur: function(){ editField("${SKU}", "col", "Title", "typed on A"); }};
    document.activeElement = __field;
    document.getElementById("pdp").contains = function(el){ return el === __field; };
    var __pushes = 0; history.pushState = function(){ __pushes++; };
    function _altaBootDone(){} function setListSource(){}
  `);
  ctx.location.pathname = "/w/acct_b/listings";
  const p = run(ctx, `altaRouteFromUrl()`);
  await settle();
  answerAll(ctx, "/accounts/select", {ok: true});
  try{ await p; }catch(e){}
  await settle();
  const edit = ctx.calls.find(c => c.url === "/edit");
  check("the in-progress edit was saved", !!edit, true);
  check("  to account A, where it was typed", edit && edit.body && edit.body.account, "acct_a");
  check("  and the page is closed", run(ctx, "PDP_SKU"), "");
  check("  and B's Amazon data cache starts empty", run(ctx, `lvGet("${SKU}")`), null);
}

console.log("\n6. detecting another account's marketplaces does not quietly make it the open one");
{
  // switcher.js can run "Detect marketplaces" for an account that is NOT the
  // open one. shell.js then assigned CUR_ACCOUNT to it -- with the grid, the
  // header, the server's selection and ROWS all still describing the open
  // account -- so every later save (acctBody) named the other account.
  const ctx = await load();
  await openOnA(ctx);
  const p = run(ctx, `detectMarketplaces("acct_b")`);
  await settle();
  answerAll(ctx, "/accounts/detect_marketplaces", {ok: true, marketplaces: ["UK", "DE"]});
  await settle();
  answerAll(ctx, "/accounts/list", {ok: true, accounts: [
    {id: "acct_a", label: "A", marketplaces: ["UK"]},
    {id: "acct_b", label: "B", marketplaces: ["UK", "DE"]}]});
  await p; await settle();
  check("the open account is still A", run(ctx, "CUR_ACCOUNT && CUR_ACCOUNT.id"), "acct_a");
  run(ctx, `editField("${SKU}", "col", "Title", "typed on A")`);
  await settle();
  const edit = ctx.calls.find(c => c.url === "/edit");
  check("  so a save on A's screen still names A", edit && edit.body && edit.body.account, "acct_a");
}

console.log("\n" + (fails ? fails + " FAILED" : "all passed"));
process.exit(fails ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
