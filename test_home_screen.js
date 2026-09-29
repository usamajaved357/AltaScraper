// Home, the screen the app opens on (owner, 29 Sep 2026), and the icon rail.
//
// WHAT THIS PINS
//   * The app opens on Home: every default and fallback that said "listings".
//   * UNKNOWN IS NEVER ZERO: orders or listings that failed to load show a dash
//     and the reason, not 0 (a review found both drawing 0 / spinning for ever).
//   * Counts are the owning screen's own (listQueueCount / _ordTabCounts), so a
//     card and the table it opens cannot disagree (Rule 12).
//   * The rail's menu has ONE outside-click listener for the page: a listener
//     per menu outlived its menu and shut the next one as it opened.
//   * The rail is built from the sidebar, including the permission to see Home.
//
// Run: node test_home_screen.js
const fs = require("fs"), vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const HOMEJS = fs.readFileSync("static/js/home.js", "utf8");
const RAIL   = fs.readFileSync("static/js/navrail.js", "utf8");
const SHELL  = fs.readFileSync("static/js/shell.js", "utf8");
const SEARCH = fs.readFileSync("static/js/listings_search.js", "utf8");
const HTML   = fs.readFileSync("templates/dashboard.html", "utf8");
const UIR    = fs.readFileSync("routes/ui_routes.py", "utf8");
const USERS  = fs.readFileSync("static/js/users.js", "utf8");

console.log("== the app opens on Home ==");
truthy("enterAccount lands on Home", /navTo\("home"\);\s*\n\s*altaSyncUrl\(\);/.test(SHELL));
truthy("the address with no screen falls back to Home", SHELL.includes('let   sec = m[2] || "home";'));
truthy("  and an unknown screen too", SHELL.includes('if(ALTA_SECTIONS.indexOf(sec) < 0) sec = "home";'));
truthy("Home is an addressable section", /ALTA_SECTIONS = \["home",/.test(SHELL));
truthy("/w/<ws> redirects to /home", UIR.includes('"/home")'));
truthy("Home has a permission mapping", USERS.includes('home:"listings"'));
truthy("the sidebar has a Home item, highlighted first",
       /<a class="navitem active" data-sec="home"/.test(HTML));
truthy("the panel is included", HTML.includes('{% include "screens/sec_home.html" %}'));
truthy("Home redraws on every visit (outside the fresh-only block)",
       /_mark\(\);\s*\n\s*\}\s*\n(?:\s*\/\/[^\n]*\n)*\s*if\(sec==="home"\)\{ if\(typeof homeOnOpen/.test(SHELL));

console.log("\n== counts come from their owners ==");
truthy("listQueueCount uses the table's own filter test",
       /function listQueueCount\(f\)[\s\S]*?listFilterMatch\(r, f\)/.test(SEARCH));
truthy("  and leaves out published, blank and deleted rows like the Drafts table",
       /function listQueueCount[\s\S]*?isEmptyRow[\s\S]*?isPublishedRow[\s\S]*?isDeletedOnAmazon/.test(SEARCH));
truthy("passFilter asks the same function", /return listFilterMatch\(r, FILTER\);/.test(SEARCH));

// ---- behaviour, with the page's helpers stubbed -----------------------------
const G = {
  window: {}, esc: s => String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
                                  .replace(/>/g,"&gt;").replace(/"/g,"&quot;"),
  jsArg: require("./test_helpers.js").jsArg,
  maySeeSection: () => true,
  ACTIVE_WS: {key: "acct_b", label: "Account B", account: true}, CUR_ACCOUNT: {id: "acct_b"},
  WS_MARKET: "UK", CUR_SEC: "home",
  ROWS_LOADED: true, ROWS: [{sku: "a", status: "ERROR"}, {sku: "b", status: "APPROVED"}],
  listQueueCount: f => f === "refused" ? 1 : f === "approved" ? 1 : 0,
  LIVE_ITEMS: [],
  ORD: {rows: [], rowsFor: "acct_b", loadedFor: "", busy: false, err: "Unauthorized"},
  _ordTabCounts: rows => ({problem: rows.length, tobuy: 0, dispatch: 0, tracking: 0}),
  _ordBuyKnown: () => true,
  DAILY: {data: null, loading: false, note: ""},
  uiError: (t, d) => '<div class="ui-error">' + t + ": " + d + "</div>",
  setTimeout: () => 0, clearTimeout: () => 0, Date,
};
G.window = G;
const HOST = {innerHTML: "", childElementCount: 0, contains: () => false};
G.document = {getElementById: id => id === "home_body" ? HOST : null, activeElement: null};
vm.createContext(G);
vm.runInContext(HOMEJS, G);

let q = vm.runInContext("_hQueues()", G);
const ordCards = q.filter(x => x.kind === "order");
check("failed orders: every order card is unknown, not 0", ordCards.map(x => x.n), [null, null, null, null]);
check("  and carries the reason", ordCards[0].err, "Unauthorized");
check("  and is not shown as still loading", ordCards[0].wait, false);
vm.runInContext("homeRender()", G);
truthy("the reason is said under the cards", HOST.innerHTML.includes("Orders could not be read: Unauthorized"));
truthy("no order card draws a 0", !/data-hk="order:[a-z]+"[^>]*><span class="hm-n">0</.test(HOST.innerHTML));

G.ORD.loadedFor = "acct_b"; G.ORD.err = ""; G.ORD.rows = [{}, {}];
q = vm.runInContext("_hQueues()", G);
check("loaded orders: counts from _ordTabCounts", q.find(x => x.f === "problem").n, 2);

G.ORD.loadedFor = "acct_a"; G.ORD.rowsFor = "acct_a";
q = vm.runInContext("_hQueues()", G);
check("another account's orders are never counted here", q.find(x => x.f === "problem").n, null);

G.ROWS_LOADED = false; G.window.ROWS_ERR = "timed out";
q = vm.runInContext("_hQueues()", G);
const lst = q.filter(x => x.kind === "list");
check("failed listings: unknown, not 0", lst.map(x => x.n), [null, null, null, null]);
check("  and not a spinner for ever", lst[0].wait, false);

G.ROWS_LOADED = true; G.window.ROWS_ERR = "";
q = vm.runInContext("_hQueues()", G);
check("loaded listings: counted by listQueueCount", q.filter(x => x.kind === "list").map(x => x.n), [1, 0, 0, 1]);

// AFTER A SWITCH (Back, marketplace, same account re-entered) screenForgetAll
// empties the rows. The bookkeeping must go with them, or Home reads the empty
// list as "0 orders" and never reloads (change review, 29 Sep 2026).
const SS = fs.readFileSync("static/js/screenstate.js", "utf8");
truthy("a switch forgets whose orders were loaded, and any failure or load",
       /ORD\.rowsFor = null; ORD\.loadedFor = ""; ORD\.err = ""; ORD\.busy = false;/.test(SS));
truthy("  and the daily round's last failure", /T\(DAILY, o => \{[^}]*o\.note = ""/.test(SS));
G.ORD.rows = []; G.ORD.rowsFor = null; G.ORD.loadedFor = ""; G.ORD.err = ""; G.ORD.busy = false;
q = vm.runInContext("_hQueues()", G);
check("after that reset the order cards are unknown, not 0",
      q.filter(x => x.kind === "order").map(x => x.n), [null, null, null, null]);
G.ORD.rowsFor = "acct_b"; G.ORD.loadedFor = "acct_b"; G.ORD.rows = [{}]; G.ORD.q = "smith";
q = vm.runInContext("_hQueues()", G);
check("a search left on the Orders screen: not counted (it would undercount)",
      q.find(x => x.f === "problem").n, null);
truthy("  and says why", /search typed/.test(q.find(x => x.f === "problem").err));
G.ORD.q = "";
const SUB = fs.readFileSync("static/js/submit.js", "utf8");
truthy("a new listings load clears the last failure", /\+\+_ROWS_SEQ;\s*\n\s*window\.ROWS_ERR = "";/.test(SUB));
truthy("  as does an account switch", /ROWS_LOADED = false;\s*\n\s*window\.ROWS_ERR = "";/.test(SHELL));
truthy("  and every failure branch records one",
       (SUB.match(/window\.ROWS_ERR = (?!"")/g) || []).length >= 2);

// NOBODY'S HOME: the "New brand" form keeps the last account's data under
// another name; Home must show none of it (account-scope review).
G.ACTIVE_WS = {key: "", label: "New brand", brand: "new"};
G.ORD.rowsFor = ""; G.ORD.loadedFor = ""; G.ORD.rows = [{}];
check("New brand: Home belongs to nobody", vm.runInContext("_hWs()", G), "");
HOST.childElementCount = 0; vm.runInContext("homeRender()", G);
truthy("  and draws no queue at all", !/hm-card/.test(HOST.innerHTML) && /Open an account/.test(HOST.innerHTML));
G.ACTIVE_WS = {key: "acct_b", label: "Account B", account: true}; G.CUR_ACCOUNT = {id: "acct_a"};
check("mid-switch (workspace and account disagree): nobody's either", vm.runInContext("_hWs()", G), "");
G.CUR_ACCOUNT = {id: "acct_b"};
G.WS_MARKET = "__all__";
HOST.childElementCount = 0; vm.runInContext("homeRender()", G);
truthy("All marketplaces: Today asks for a marketplace instead of guessing one",
       /one marketplace at a time/.test(HOST.innerHTML) && !/Asking Amazon/.test(HOST.innerHTML));
G.WS_MARKET = "UK";
G.LIVE_ITEMS = [{cogs: 0}, {cogs: 0}]; G.LIVE_STORE = {}; G._liveKey = () => "acct_b::UK";
G.liveItemIs = (it, f) => f === "live_nocost" && !it.cogs;
q = vm.runInContext("_hQueues()", G);
check("no-cost card waits for THIS marketplace's catalogue", q.some(x => x.f === "live_nocost"), false);
G.LIVE_STORE = {"acct_b::UK": {items: [{cogs: 0}]}};
q = vm.runInContext("_hQueues()", G);
check("  and counts it once it is there", q.find(x => x.f === "live_nocost").n, 1);

G.maySeeSection = s => s !== "orders";
q = vm.runInContext("_hQueues()", G);
check("no Orders permission: no order cards", q.filter(x => x.kind === "order").length, 0);

console.log("\n== the rail ==");
const openBody = RAIL.slice(RAIL.indexOf("function navRailOpen("), RAIL.indexOf("function _nrOutside("));
truthy("opening a menu adds no document click listener", !/document\.addEventListener\("click"/.test(openBody));
truthy("  one outside-click listener, added once at load",
       (RAIL.match(/document\.addEventListener\("click", _nrOutside\)/g) || []).length === 1);
truthy("a click on the rail itself is left to the rail", /t\.closest\("#navrail"\)/.test(RAIL));
truthy("Home on the rail is the sidebar's Home item, if this person may see it",
       /navitem\[data-sec="home"\][\s\S]{0,80}_nrShown\(home\)/.test(RAIL));
truthy("each group button comes from a .navgroup[data-rail]", RAIL.includes('.navgroup[data-rail]'));
truthy("every group in the sidebar has a rail name",
       (HTML.match(/<div class="navgroup" data-grp="[a-z]+"(?! data-rail=)/g) || []).length === 0);
truthy("Escape knows about the rail's menu", fs.readFileSync("static/js/escape.js", "utf8").includes('"nrfly"'));

console.log(fails ? "\n" + fails + " failed" : "\nFAILURES: 0");
process.exit(fails ? 1 : 0);
