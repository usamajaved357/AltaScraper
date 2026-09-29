/* 4G (29 Sep 2026): writes and streams that let the SERVER'S open account --
 * owned by whichever tab switched last -- decide whose data they touch.
 *
 * Browser side, with the REAL reqscope.js:
 *   - the fetch wrapper now names the account (and marketplace) on /clear_empty,
 *     /rescan/*, /approve, /edit and /brand/* -- callers that sent none;
 *   - acctStreamUrl stamps an EventSource url (EventSource bypasses fetch), and
 *     the Miles generate / optimize / run streams and the brand run use it;
 *   - removing a brand sends the account's id (the route reads `id`).
 * The server side (refusals, brand routes) is test_open_account_gaps_server.py.
 */
const fs = require("fs");
const vm = require("vm");
const path = require("path");
let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(66), ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const R = __dirname;
const src = (f) => fs.readFileSync(path.join(R, "static/js", f), "utf8");

const seen = [];
const s = { console, window: {}, CUR_ACCOUNT: { id: "acct_b" }, WS_MARKET: "DE" };
s.window.fetch = (u) => { seen.push(u); return Promise.resolve({}); };
s.window.window = s.window;
vm.createContext(s);
vm.runInContext("var window = this.window; function acctId(){ return CUR_ACCOUNT.id; }", s);
vm.runInContext(src("reqscope.js").replace(/^function acctId\(\)[\s\S]*?\n\}\r?\n/m, ""), s);

console.log("=== the fetch wrapper names the account on the gaps ===");
for (const p of ["/clear_empty", "/rescan/apply", "/rescan/preview", "/approve", "/edit", "/brand/save", "/brand/list"]) {
  check(p + " is stamped", vm.runInContext("acctScopedPath(" + JSON.stringify(p) + ")", s), true);
}
vm.runInContext("window.fetch('/clear_empty', {method:'POST'})", s);
check("  the url sent carries account and marketplace", seen[seen.length - 1], "/clear_empty?account=acct_b&marketplace=DE");

vm.runInContext("window.fetch('/edit', {method:'POST', body: JSON.stringify({sku:'X', account:'acct_a'})})", s);
check("a body that already names its account (a pinned bulk loop) is NOT stamped",
      seen[seen.length - 1], "/edit");
vm.runInContext("window.fetch('/edit', {method:'POST', body: JSON.stringify({sku:'X'})})", s);
check("  a body that names none is", seen[seen.length - 1], "/edit?account=acct_b&marketplace=DE");

console.log("=== streams name it too ===");
check("acctStreamUrl stamps an EventSource url",
      vm.runInContext("acctStreamUrl('/miles/generate?sheet=x')", s), "/miles/generate?sheet=x&account=acct_b&marketplace=DE");
const miles = src("miles.js");
check("Miles run / generate / optimize streams use it",
      (miles.match(/new EventSource\(\(typeof acctStreamUrl === "function"\) \? acctStreamUrl\(/g) || []).length, 3);
const brand = src("brand_panel.js");
check("the brand run stream uses it", /new EventSource\(\(typeof acctStreamUrl === "function"\) \? acctStreamUrl\(_bu\)/.test(brand), true);
check("removing a brand sends the account's id", /remove_brand[\s\S]{0,400}id:\(typeof acctId === "function" \? acctId\(\) : ""\)/.test(brand), true);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
