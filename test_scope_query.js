// Which account and marketplace a request is about — one builder, every screen.
//
// There were FOUR copies of this, in daily.js, weekly.js, stock.js and
// ppcview.js, and adding a fifth for the trackers is what made someone put them
// side by side. They had already drifted into two different behaviours, and the
// drift was not cosmetic:
//
//   1. daily.js and weekly.js read a variable called WS_ID. Nothing in this app
//      has ever defined WS_ID. Those two screens therefore always sent an EMPTY
//      account id and relied entirely on the server's idea of which account was
//      active. It works today only because selecting an account updates that
//      server state — it is the same shape as the fault that put one account's
//      orders on another account's Orders tab.
//
//   2. Those same two forwarded marketplace=__all__ verbatim. "__all__" is the
//      UI's word for "every marketplace", not a country.
//
// This test exists so the four cannot quietly become four again.
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) {
  return fs.readFileSync(path.join(__dirname, p), "utf8");
}
function codeOnly(s) {
  return s.split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

console.log("== there is one builder ==");
const SRC = read("static/js/scopeq.js");
check("static/js/scopeq.js exists", SRC.length > 200);
check("  and the page loads it", /scopeq\.js\?v=/.test(read("templates/dashboard.html")));

// Run it for real rather than reading it. A regex would pass on a builder that
// was syntactically present and behaviourally wrong, which is the entire fault
// being fixed here.
const sandbox = { CUR_ACCOUNT: null, WS_MARKET: "" };
const fn = new Function("CUR_ACCOUNT", "WS_MARKET",
  SRC + "\nreturn {scopeQs: scopeQs, scopeAccountId: scopeAccountId};");
function run(acct, mkt, extra) {
  return fn(acct, mkt).scopeQs(extra);
}
function runId(acct) {
  return fn(acct, "").scopeAccountId();
}

console.log("\n== it sends what it knows and omits what it does not ==");
check("account and marketplace",
  run({ id: "jack_uk" }, "UK") === "?id=jack_uk&marketplace=UK");
// An ABSENT parameter is how you say "you decide": every route's _scope() falls
// back to the active account when a value is missing. An EMPTY id looks like an
// answer instead.
check("no account means no id at all", run(null, "UK") === "?marketplace=UK");
check("no marketplace means no marketplace at all",
  run({ id: "jack_uk" }, "") === "?id=jack_uk");
check("nothing known means no query string at all", run(null, "") === "");

console.log("\n== '__all__' is not a country ==");
// The bug daily.js and weekly.js carried: forwarding the UI's word for "every
// marketplace" to a server that expects a marketplace code.
check("__all__ is never sent as a marketplace",
  run({ id: "jack_uk" }, "__all__") === "?id=jack_uk");
check("  and the account still is", run(null, "__all__") === "");

console.log("\n== extra parameters ==");
check("extras are appended",
  run({ id: "a" }, "UK", { metric: "bsr" }) === "?id=a&marketplace=UK&metric=bsr");
check("  empty extras are dropped",
  run({ id: "a" }, "UK", { metric: "" }) === "?id=a&marketplace=UK");
check("  and values are encoded",
  run({ id: "a b" }, "UK") === "?id=a%20b&marketplace=UK");

console.log("\n== the id on its own, for form posts ==");
check("the account id is returned", runId({ id: "jack_uk" }) === "jack_uk");
check("  and empty when there is none", runId(null) === "");

console.log("\n== nobody keeps a private copy ==");
// The specific dead variable that started this. If WS_ID comes back, so has the
// bug: a screen reading a variable nothing sets, and silently sending nothing.
["static/js/daily.js", "static/js/weekly.js", "static/js/stock.js",
 "static/js/ppcview.js", "static/js/trackers.js"].forEach(function (f) {
  const s = codeOnly(read(f));
  check("  " + path.basename(f) + " defers to the shared builder",
    /scopeQs\s*\(/.test(s));
  check("    and no longer reads the undefined WS_ID", s.indexOf("WS_ID") < 0);
});

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
