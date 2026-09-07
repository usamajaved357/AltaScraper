/* Change the price and the profit beside it has to change too.
 *
 *     "the listing was saying that the profit in this item is 1.76 and so i
 *      changed the selling price by 3 pounds but the app was not able to change
 *      the profit calculation at the glance at the same moment in mili seconds,
 *      the profit remained the same value as it was before"
 *
 * WHY IT DID NOT. r.profit is not derived from r.price. It is a SEPARATE stored
 * figure the generator worked out once, with the real fee -- listings.js says
 * so where it draws it. updateLocalCol set r.price and stopped, so the profit,
 * and the margin and ROI derived from it, went on describing a price that no
 * longer existed, and looked authoritative while doing it.
 *
 * THE ARITHMETIC IS NOT COPIED INTO THE BROWSER. Profit is price less cost less
 * what Amazon takes, and the last of those is a three-tier resolver (what
 * Amazon actually took on settled orders, else Amazon's own quote, else this
 * account's MEASURED referral rate -- never a flat 15%). /listing/revenue is
 * the one caller of it. A JavaScript copy would drift the first time a fee rule
 * changed, and drift silently, because both would look plausible (Rule 12).
 */
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
let fails = [];

function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(66) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

const P = fs.readFileSync(path.join(HERE, "static", "js", "profit.js"), "utf8");
const A = fs.readFileSync(path.join(HERE, "static", "js", "autofix.js"), "utf8");
const L = fs.readFileSync(path.join(HERE, "static", "js", "listings.js"), "utf8");
const H = fs.readFileSync(path.join(HERE, "templates", "dashboard.html"), "utf8");

console.log("=== the figure is asked for, never computed here ===");
truthy("it asks the route that owns the fee resolver",
  P.indexOf('"/listing/revenue?sku="') >= 0);
// The formula must not exist in the browser in any form. These are the shapes a
// copy would take: a referral rate, or price-minus-cost arithmetic.
// CODE ONLY. The file explains what it is NOT doing -- "never a flat 15%" --
// and counting the explanation would flag the very thing it warns against.
const _pcode = P.split("\n")
  .filter(l => { const s = l.trim();
                 return s && !s.startsWith("*") && !s.startsWith("//")
                        && !s.startsWith("/*"); })
  .join("\n");
falsy("no fee rate is written in the browser", /0\.15|15\s*%|referral\s*\*/.test(_pcode));
falsy("  and no profit arithmetic either",
  /price\s*-\s*cost|price\s*-\s*cogs|-\s*referral/.test(_pcode));

console.log("\n=== the cost sent is the one the screen is showing ===");
// cogsOf() still falls back to the SKU's price prefix; the SERVER stopped doing
// that ("lets remove the cogs from sku things entirely"). Measured on
// nestwell_goods: the browser shows a cost on 85 of 86 rows, the server
// resolves one on 1. Without sending it, every recomputed profit on those 85
// would come back blank while the cost box beside it still read 9.99.
truthy("the displayed cost is passed", P.indexOf('"&cost=" + encodeURIComponent') >= 0);
truthy("  taken from the one place that decides it", P.indexOf("cogsOf(r)") >= 0);
truthy("  and only when it is a real number above zero",
  P.indexOf("Number(c.cost) > 0") >= 0);
const R = fs.readFileSync(path.join(HERE, "routes", "revenue_routes.py"), "utf8");
truthy("the route accepts it", R.indexOf('request.args.get("cost")') >= 0);
// A cost the owner actually SET must never be overridden by one the browser
// happens to be drawing.
truthy("  but only when it has none of its own",
  R.split('request.args.get("cost")')[0].trim().endsWith("if cost is None:\n            _shown = _f(")
  || R.indexOf("if cost is None:\n            _shown") >= 0);

console.log("\n=== an older answer can never overwrite a newer one ===");
// Typing a price fires an edit per blur. A reply for the previous price landing
// after the current one would paint the wrong profit -- the same out-of-order
// fault the barcode check guards against.
truthy("each request is sequenced per SKU", P.indexOf("_PROFIT_SEQ") >= 0);
truthy("  and a stale reply is dropped",
  P.indexOf("seq !== _PROFIT_SEQ[sku]") >= 0);

console.log("\n=== an unknown cost stays unknown ===");
// The row hides the whole margin/ROI line when there is no profit, rather than
// printing zeroes: an item that appears to cost nothing looks infinitely
// profitable. So a null must become a blank, not a 0.
truthy("no net -> the profit is blanked, not zeroed",
  P.indexOf('j.net === null || j.net === undefined) ? ""') >= 0);
truthy("  and a failed lookup changes nothing at all",
  P.indexOf("if(!j) return;") >= 0);
truthy("  a row that is not on screen is not invented",
  P.indexOf("if(!r) return;") >= 0);

console.log("\n=== nothing is written back ===");
// The stored column is the generator's. Rewriting it from here would put a
// second author on a column one thing owns.
falsy("it never posts to /edit", P.indexOf('"/edit"') >= 0);
falsy("  nor anywhere else", P.indexOf("method: \"POST\"") >= 0
  || P.indexOf('method:"POST"') >= 0);

console.log("\n=== both places a price changes call it ===");
// One is a single edit; the other is every bulk price change, which came
// through applyPushedLocally and restated forty profits at once.
const _ulc = A.split("function updateLocalCol(")[1].split("\n/* WRITE ONE FIELD")[0];
truthy("the single edit refreshes it",
  _ulc.indexOf('key === "Our Price (GBP)"') >= 0
  && _ulc.indexOf("profitRefresh(r.sku, value)") >= 0);
const _apl = L.split("function applyPushedLocally(")[1].split("\n/* WHICH OF THE TWO")[0];
truthy("the bulk push refreshes it too", _apl.indexOf("profitRefresh(s, _newPrice)") >= 0);
truthy("  only when a price was actually in the patch",
  _apl.indexOf("rowPatch.price !== undefined") >= 0);
// Both call it defensively, so the file loading late cannot throw.
truthy("both check the function exists first",
  (_ulc.match(/typeof profitRefresh === "function"/g) || []).length === 1
  && (_apl.match(/typeof profitRefresh === "function"/g) || []).length === 1);

console.log("\n=== and it is actually loaded ===");
truthy("the page loads profit.js", H.indexOf("/static/js/profit.js") >= 0);

console.log("\nFAILURES: " + fails.length);
fails.forEach(f => console.log("  - " + f));
process.exit(fails.length ? 1 : 0);
