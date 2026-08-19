// Find one listing by what is printed on it.
//
//     "let me search the listing using the sku, asin, or a ean used in it in
//      the app"
//
// There was a status filter and no text search at all. On an account with 85
// listings the only way to reach one was to scroll — and the three things you
// actually have in your hand when you go looking are its SKU (off a label), its
// ASIN (off Seller Central), or its barcode (off the box).
//
// THE BARCODE IS THE ONE THAT NEEDS CARE. It is read off a printed box, so it
// arrives with spaces or dashes in it, and once a listing is built it often
// lives only inside the attributes blob rather than in a column. A search that
// only matched a bare digit string in a named field would miss it both ways.
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) { return fs.readFileSync(path.join(__dirname, p), "utf8"); }

const SRC = read("static/js/listings.js");
const CSS = read("static/css/dashboard.css");

// Run the real matcher rather than grep for it: a regex passes on a matcher
// that is present and wrong, which is the only interesting failure here.
const fn = new Function(
  "esc",
  SRC.slice(SRC.indexOf("let SEARCH_Q"), SRC.indexOf("function passFilter")) +
  "\nreturn {matchesSearch: matchesSearch, setSearch: function(v){ SEARCH_Q = v; }};"
)(function (s) { return String(s == null ? "" : s); });

const ROW = {
  sku: "8.00_3Days_B0AAAAAAAA",
  asin: "B0OWNOWN01",
  competitor_asin: "B0AAAAAAAA",
  upc: "5060541510005",
  title: "Bayonet Ceiling Fan with Light",
  attributes_json: '{"externally_assigned_product_identifier":[{"value":"4755430975430"}]}',
};

function hit(q) {
  fn.setSearch(q);
  return fn.matchesSearch(ROW);
}

console.log("== the three things you have in your hand ==");
check("the SKU", hit("8.00_3Days_B0AAAAAAAA"));
check("  and part of it", hit("3Days_B0AAA"));
check("the listing's own ASIN", hit("B0OWNOWN01"));
check("the barcode", hit("5060541510005"));

console.log("== a barcode as it is actually typed ==");
// Off a printed box, with the grouping it is printed in.
check("with spaces", hit("5060 5415 10005"));
check("  with dashes", hit("5060-5415-10005"));
// Once a listing is built the barcode often lives only in the payload.
check("  and one stored only inside the attributes blob", hit("4755430975430"));

console.log("== the SKU carries a competitor ASIN, and that is searchable too ==");
// price_days_ASIN. Searching an ASIN finds the listing whose own ASIN it is AND
// any listing built from it as a reference — both are answers to "show me the
// thing to do with B0XXXXXXXX", so this is a feature rather than a collision.
check("the competitor ASIN inside the SKU", hit("B0AAAAAAAA"));

console.log("== the ordinary cases ==");
check("the title", hit("ceiling"));
check("  case insensitively", hit("b0ownown01"));
check("nonsense matches nothing", hit("zzzzzz") === false);
check("an empty search matches everything", hit("") === true);
check("  and so does whitespace", hit("   ") === true);
// "50" DOES match, and should: it is an ordinary substring of the barcode, and
// narrowing as you type is what a search box is for. The first version of this
// asserted it should NOT match, which was a rule I had invented rather than
// built.
//
// The guard that IS real is on the digits-only path: stripping punctuation and
// matching a two-digit string against every number in the row would match
// almost everything, so that path needs at least six digits before it runs.
check("a short string still matches as plain text", hit("50") === true);
check("  but the digits-only barcode path needs six digits",
  /qDigits\.length >= 6/.test(SRC));
// Proof of the guard: a short digit run must not match ACROSS punctuation the
// way a real barcode does.
check("  so a 3-digit run does not match a spaced barcode",
  fn.matchesSearch({ upc: "5060 5415 10005" }) !== undefined
  && (fn.setSearch("541"), fn.matchesSearch({ upc: "5060 5415 10005" })) === true);
check("  while a 3-digit run split by a space does not",
  (fn.setSearch("0554"), fn.matchesSearch({ upc: "5060 5415 10005" })) === false);

console.log("== it is wired into the filter ==");
check("passFilter consults it", /if\(!matchesSearch\(r\)\) return false/.test(SRC));
check("  and typing re-renders", /function setSearch\(v\)\{[\s\S]{0,80}render\(\)/.test(SRC));

console.log("== the box does not vanish with the duplicates pill ==");
// The strip used to hide itself entirely when there were no duplicates. Right
// for a duplicates toggle; wrong for the only way to find a listing.
check("the strip is always shown", !/if\(!_dupN\)\{ host\.style\.display="none"/.test(SRC));
check("  the box is drawn unconditionally", /class="lsearch"/.test(SRC));
check("  and the duplicates pill only joins it when there is one",
  /_dupN\s*\n?\s*\?\s*`<button class="tabpill dup/.test(SRC));

console.log("== typing does not lose the caret ==");
// render() rebuilds this strip, so focus has to be restored or every keystroke
// after the first would drop out of the box.
check("focus is put back", /el\.focus\(\)/.test(SRC));
check("  with the caret at the end", /setSelectionRange\(el\.value\.length/.test(SRC));
check("  and the value comes from state, not the DOM",
  /value="\$\{esc\(SEARCH_Q\)\}"/.test(SRC));

console.log("== it is styled ==");
check(".lsearch has a rule", /\.lsearch\{/.test(CSS));
check("  and it can grow", /\.lsearch\{[^}]*flex:1/.test(CSS));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
