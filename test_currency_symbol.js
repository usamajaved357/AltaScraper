// One currency-code to symbol map.
//
// There were FOUR — salescharts.js, stock.js, weekly.js, and a fifth idea of it
// in listings.js — and they had already disagreed: two rendered Canadian
// dollars as a bare "$" where another rendered "C$". On a screen that can show
// two dollar markets that is the difference between a readable figure and a
// wrong one.
//
// FOUND WHILE ADDING A FIFTH, and the fifth was worse. Three new screens
// (Trackers, Leading Indicators, Product Catalog) had been written against a
// variable called CURRENCY_SYMBOL that HAS NEVER EXISTED anywhere in this app.
// All three printed money with no symbol at all — "540.91" where it should read
// "£540.91" — and nothing failed, because the guard was
// `typeof CURRENCY_SYMBOL !== "undefined" ? ... : ""`.
//
// And fixing it turned up a second fault: weekly.js is loaded BEFORE money.js in
// the page, so reading the map at module scope captured an empty object and
// silently dropped every symbol on that screen. Load order must not be able to
// do that.
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) { return fs.readFileSync(path.join(__dirname, p), "utf8"); }
function codeOnly(s) {
  return s.split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

const SRC = read("static/js/money.js");
const HTML = read("templates/dashboard.html");

// Run it rather than grep it: a regex passes on a map that is present and wrong.
const api = new Function("CUR_SYMBOL",
  SRC + "\nreturn {curSymbol: curSymbol, curMoney: curMoney, CUR_SYMBOLS: CUR_SYMBOLS};")("£");

console.log("== the map is real ==");
check("there is a shared map", Object.keys(api.CUR_SYMBOLS).length > 12);
check("  GBP", api.curSymbol("GBP") === "£");
check("  USD", api.curSymbol("USD") === "$");
check("  EUR", api.curSymbol("EUR") === "€");

console.log("== two dollar markets are not the same symbol ==");
// The disagreement the four copies already had.
check("CAD is not a bare $", api.curSymbol("CAD") !== "$");
check("  AUD is not a bare $", api.curSymbol("AUD") !== "$");
check("  and they differ from each other", api.curSymbol("CAD") !== api.curSymbol("AUD"));
check("  and from USD", api.curSymbol("CAD") !== api.curSymbol("USD"));

console.log("== an unknown code returns the code, not a guess ==");
// "SGD 40.00" is correct and readable; picking "$" would be a different
// currency presented as though it were the same one.
check("an unknown code shows itself", api.curSymbol("XYZ").indexOf("XYZ") === 0);
check("  and never a guessed symbol", api.curSymbol("XYZ").indexOf("$") < 0);
check("no code falls back to the workspace symbol", api.curSymbol("") === "£");
check("  or to an explicit fallback", api.curSymbol("", "€") === "€");

console.log("== money reads as money ==");
check("symbol and two decimals", api.curMoney(540.9, "GBP") === "£540.90");
// A missing figure and a figure of zero are different answers, and only one of
// them is a fact.
check("nothing known is a dash, not 0.00", api.curMoney(null, "GBP") === "—");
check("  and so is a non-number", api.curMoney("n/a", "GBP") === "—");
check("  but zero is zero", api.curMoney(0, "GBP") === "£0.00");

console.log("== nobody keeps a private copy ==");
["static/js/salescharts.js", "static/js/stock.js", "static/js/weekly.js"].forEach(function (f) {
  const s = codeOnly(read(f));
  // A private map is a literal with several currency codes in it.
  const own = /\{\s*GBP:\s*"£"[^}]*USD/.test(s) || /\{\s*USD:\s*"\$"[^}]*GBP/.test(s);
  check("  " + path.basename(f) + " has no map of its own", !own);
});
// The variable that never existed must not come back.
["static/js/trackers.js", "static/js/leading.js", "static/js/catalogpage.js"].forEach(function (f) {
  const s = codeOnly(read(f));
  check("  " + path.basename(f) + " no longer reads CURRENCY_SYMBOL",
    s.indexOf("CURRENCY_SYMBOL") < 0);
  check("    and uses the shared one", /curSymbol\(/.test(s));
});

console.log("== load order cannot empty it ==");
// weekly.js is loaded BEFORE money.js. Reading the map at module scope captured
// an empty object and silently dropped every symbol on that screen.
const WK = codeOnly(read("static/js/weekly.js"));
const SC = codeOnly(read("static/js/salescharts.js"));
check("weekly resolves when called, not at load",
  !/const _WK_SYMS\s*=/.test(WK) && /typeof curSymbol === "function"/.test(WK));
check("  and so does salescharts",
  !/const SC_CUR\s*=/.test(SC) && /function _scCur\(/.test(SC));
// Belt as well as braces: it is also loaded first now.
const iMoney = HTML.indexOf("js/money.js");
const iWeekly = HTML.indexOf("js/weekly.js");
const iStock = HTML.indexOf("js/stock.js");
check("money.js is loaded before weekly.js", iMoney > 0 && iMoney < iWeekly);
check("  and before stock.js", iMoney > 0 && iMoney < iStock);

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
