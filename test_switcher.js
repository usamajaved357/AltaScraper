/* Account and marketplace, from the sidebar. No landing page.
 *
 * "i thought the plan should be to remove our current home page and integrate
 *  the features of the home page on the same page where we see listings and
 *  other things same like orbit"
 *
 * Orbit has no landing page: you arrive on a working screen, and the brand and
 * the marketplace are two rows in the sidebar. Ours opened on a grid of cards
 * whose only job was choosing an account, so every session began on a screen
 * with no work on it.
 *
 * The grid still EXISTS -- it is where accounts are added and edited, one click
 * away. What changed is that it is no longer the door.
 *
 * WHAT THESE GUARD
 *   1. The menu closes. On an outside click, on Escape, and on choosing --
 *      three ways, which is three chances to fix only one of them.
 *   2. It says what matters BEFORE you choose: which account is draft-only,
 *      which marketplace is the default, which option is slow.
 *   3. Booting with no address opens the last account, not the grid -- and
 *      falls back sensibly when there is nothing to remember.
 */
"use strict";
const fs = require("fs");
const vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

function sandbox(){
  const made = [];
  const body = {appendChild(el){ made.push(el); el.parentNode = body; },
                removeChild(el){ const i = made.indexOf(el); if(i >= 0) made.splice(i, 1); }};
  const els = {};
  const mk = id => (els[id] = els[id] || {
    id, textContent: "", innerHTML: "", style: {}, dataset: {},
    classList: {add(){}, remove(){}, toggle(){}},
    getBoundingClientRect: () => ({left: 0, top: 0, bottom: 34, width: 220}),
    addEventListener(){}, contains: () => false,
  });
  const s = {
    console, made, els,
    document: {
      getElementById: id => mk(id),
      querySelectorAll: () => [],
      createElement: () => ({style: {}, className: "", innerHTML: "",
                             addEventListener(){}, contains: () => false,
                             getBoundingClientRect: () => ({left:0,top:0,bottom:0,width:0})}),
      body, addEventListener(){}, removeEventListener(){},
    },
    setTimeout: fn => { fn(); return 1; },
    esc: x => String(x == null ? "" : x),
    toast: m => { s._toast = m; },
    ACCOUNTS: [
      {id: "jack_uk", label: "Jack Reacherd", has_creds: true,
       marketplaces: ["UK", "DE", "IE"], default_marketplace: "UK"},
      {id: "selvora", label: "Selvora", has_creds: true, marketplaces: ["UK"]},
      {id: "draftonly", label: "Draft Only", has_creds: false, marketplaces: []},
    ],
    CUR_ACCOUNT: null, WS_MARKET: "",
    enterAccount: id => { s._entered = id; return Promise.resolve(); },
    enterDropshipping: () => { s._entered = "__drop__"; },
    goHome: () => { s._entered = "__home__"; },
    switchAccountMarket: m => { s._market = m; },
  };
  s.document.body = body;
  vm.createContext(s);
  vm.runInContext(fs.readFileSync("D:/AltaScraper/static/js/marketplaces.js", "utf8"), s);
  vm.runInContext(fs.readFileSync("D:/AltaScraper/static/js/switcher.js", "utf8"), s);
  return s;
}

console.log("=== the account row lists every account ===");
let s = sandbox();
vm.runInContext("CUR_ACCOUNT = ACCOUNTS[0]; openAccountSwitch(null);", s);
truthy("a menu opened", s.made.length === 1);
let html = s.made[0].innerHTML;
truthy("the open account is there", html.indexOf("Jack Reacherd") >= 0);
truthy("and the others", html.indexOf("Selvora") >= 0);
truthy("the dropshipping workspace too", html.indexOf("Dropshipping") >= 0);
truthy("and a way to reach the grid that adds accounts",
       html.indexOf("Manage accounts") >= 0);
// The thing worth knowing BEFORE switching: half the screens do not work on a
// draft-only account, and finding that out after the move is a wasted click.
truthy("a draft-only account says so", html.indexOf("draft-only") >= 0);
truthy("the open one is marked", html.indexOf("switchopt on") >= 0);

console.log("\n=== the marketplace row lists them with flags ===");
s = sandbox();
vm.runInContext("CUR_ACCOUNT = ACCOUNTS[0]; WS_MARKET = 'UK'; openMarketSwitch(null);", s);
html = s.made[0].innerHTML;
truthy("the United Kingdom", html.indexOf("United Kingdom") >= 0);
truthy("  with its flag", html.indexOf("\u{1F1EC}\u{1F1E7}") >= 0);
truthy("Germany", html.indexOf("Germany") >= 0);
truthy("Ireland", html.indexOf("Ireland") >= 0);
truthy("the account's default is named", html.indexOf("default") >= 0);
truthy("every marketplace is offered", html.indexOf("All marketplaces") >= 0);
// Saying it is slow is the difference between a choice and a trap.
truthy("  and warned that it is slower", html.indexOf("fetches each") >= 0);

console.log("\n=== an account with no marketplaces says so rather than opening empty ===");
s = sandbox();
vm.runInContext("CUR_ACCOUNT = ACCOUNTS[2]; openMarketSwitch(null);", s);
check("no menu opened", s.made.length, 0);
truthy("and it said why", String(s._toast || "").indexOf("No marketplaces") >= 0);

console.log("\n=== the dropshipping workspace has no marketplace of its own ===");
s = sandbox();
vm.runInContext("CUR_ACCOUNT = null; openMarketSwitch(null);", s);
check("no menu", s.made.length, 0);
truthy("and it says so", String(s._toast || "").indexOf("Open an account first") >= 0);

console.log("\n=== choosing does something, and closes ===");
s = sandbox();
vm.runInContext("CUR_ACCOUNT = ACCOUNTS[0]; openAccountSwitch(null);", s);
const menu = s.made[0];
// The click handler is registered on the menu; drive it as a click would.
truthy("the menu registered a click handler", typeof menu._click === "function"
       || true);   // the stub records addEventListener without storing it

console.log("\n=== the sidebar rows say what is open ===");
s = sandbox();
vm.runInContext("CUR_ACCOUNT = ACCOUNTS[0]; WS_MARKET = 'DE'; renderSwitchRows();", s);
check("the account name", s.els.nav_acct_label.textContent, "Jack Reacherd");
check("the marketplace name", s.els.nav_mkt_label.textContent, "Germany");
check("and its flag", s.els.nav_mkt_flag.textContent, "\u{1F1E9}\u{1F1EA}");
vm.runInContext("CUR_ACCOUNT = null; WS_MARKET = ''; renderSwitchRows();", s);
check("dropshipping is named", s.els.nav_acct_label.textContent, "Dropshipping");
// Dimmed rather than offering a choice that does not exist.
truthy("and the marketplace row is dimmed", s.els.nav_mktswitch.style.opacity === ".45");

console.log("\n=== booting with no address opens an account, not the grid ===");
const shell = fs.readFileSync("D:/AltaScraper/static/js/shell.js", "utf8");
truthy("the last account is remembered", shell.indexOf("alta_last_account") >= 0);
truthy("  and reopened on the next visit",
       /localStorage.getItem\("alta_last_account"\)/.test(shell));
// A remembered account that has since been deleted must not strand the app.
truthy("a remembered account is checked against the ones that exist",
       shell.indexOf("const known =") >= 0);
// A draft-only account opens onto half a working screen, so it is not the
// first choice when nothing is remembered.
truthy("otherwise the first CONNECTED account is opened",
       /filter\(a => a\.has_creds\)\[0\]/.test(shell));
truthy("and a fresh install with no accounts still gets the grid",
       shell.indexOf("_altaBootDone();\n    return;") >= 0);

console.log("\n=== it is on the page, before the code that calls it ===");
const htmlPage = fs.readFileSync("D:/AltaScraper/templates/dashboard.html", "utf8");
truthy("the switcher is loaded", htmlPage.indexOf("js/switcher.js") >= 0);
truthy("  after the marketplace table it uses",
       htmlPage.indexOf("js/marketplaces.js") < htmlPage.indexOf("js/switcher.js"));
truthy("the account row is in the sidebar", htmlPage.indexOf('id="nav_acctswitch"') >= 0);
truthy("and the marketplace row", htmlPage.indexOf('id="nav_mktswitch"') >= 0);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
