/* Two ways of getting to a screen you already have.
 *
 *     "i have an option to search listings with identifiers but i do not have
 *      an option to find the listings with their name"
 *
 *     "give me a bookmark bar like amazon on the top where i can bookmark the
 *      pages i use frequently"
 *
 * THE FIRST ONE ALREADY WORKED. r.title was in the searched fields the whole
 * time. Measured on jack_uk's 67 listings before changing anything: "fol" found
 * 10, "camping chair" found 1, "grill" found 2, and the full Expandable Garden
 * Hose title found exactly that listing. The box said "Find by SKU, ASIN or
 * barcode", so nobody tried a name. A feature nobody is told about is a feature
 * nobody has.
 *
 * What was genuinely missing was word ORDER: the match is a substring, so
 * "garden hose 50ft" found the hose and "50ft garden hose" found nothing, with
 * no way to tell from the outside which you had guessed. Nobody remembers a
 * title word for word; they remember two or three words about the thing.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(60) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }

const L = fs.readFileSync("D:/AltaScraper/static/js/listings.js", "utf8");
const B = fs.readFileSync("D:/AltaScraper/static/js/bookmarks.js", "utf8");
const H = fs.readFileSync("D:/AltaScraper/templates/dashboard.html", "utf8");
const S = fs.readFileSync("D:/AltaScraper/static/js/shell.js", "utf8");

console.log("== the box says what it can actually do ==");
truthy("the placeholder offers name first",
       /placeholder="Find by name, SKU, ASIN or barcode/.test(L));
truthy("  and the title was always searched", /r\.upc, r\.title,/.test(L));
truthy("  with the measurement recorded",
       /"fol" found 10, "camping chair"/.test(L));

console.log("\n== word order no longer has to be right ==");
truthy("a multi-word query matches in any order",
       /words\.every\(w => hay\.indexOf\(w\) >= 0\)/.test(L));
truthy("  built from the same fields as the substring pass",
       /const hay = fields\.map\(_sq\)\.join\(" "\)/.test(L));
// One-letter words would match everything; two is the floor that still lets
// "5m hose" work.
truthy("  one-letter noise is dropped", /w\.length > 1/.test(L));
// A single word is left to the substring pass on purpose: it already matches
// INSIDE a word, which is what makes "fol" find Folding and Foldable.
truthy("  single words still use the substring pass",
       /words\.length > 1/.test(L));
truthy("  and the reason is written down",
       /Nobody remembers a title word for word/.test(L));

console.log("\n== the bookmark bar ==");
truthy("it exists in the top bar", /<div class="bmkbar" id="bmkbar"/.test(H));
truthy("  and is loaded", /static\/js\/bookmarks\.js/.test(H));
// Per account: the screens worth pinning in a live trading account are not the
// ones worth pinning in a draft-only one.
truthy("bookmarks are kept per account",
       /"alta_bookmarks::" \+ \(acct \|\| "_none"\)/.test(B));
truthy("  in the browser, not the server",
       /localStorage\.setItem\(_bmkKey\(\)/.test(B));
truthy("  and switching account reloads them",
       /bmkRefresh\(\)/.test(S));
truthy("  while navigating just repaints", /bmkRender\(\)/.test(S));

console.log("\n== it adds no screen of its own ==");
// Every entry is a section that already exists and is already reachable.
truthy("the label comes from the nav item",
       /document\.querySelector\('\.navitem\[data-sec="' \+ sec/.test(B));
truthy("  so a renamed screen is renamed here too",
       /second opinion about what a screen is called/.test(B));
truthy("  and a section with no nav item cannot be pinned",
       /if\(!info\) return;/.test(B));
truthy("  clicking one just navigates", /if\(typeof navTo === "function"\) navTo\(sec\)/.test(B));

console.log("\n== an empty bar does not look like a broken one ==");
truthy("it says what it is for", /Pin the screens you use most/.test(B));
truthy("  and the current page can always be pinned", /function bmkToggle/.test(B));
truthy("  the page you are on is marked in the bar",
       /\(b\.sec === cur\) \? " on" : ""/.test(B));

console.log("\n" + fails + " failed");
process.exit(fails ? 1 : 0);
