/* The home screen chooses an account AND a marketplace, with flags.
 *
 * "the home page of the app i dont like it ... orbit has the option to choose a
 *  marketplace and also the account with flag shown of the countries"
 *
 * The home screen's one job is picking an account, and nearly every account
 * here sells in more than one country. Picking the account and then hunting for
 * the marketplace switcher is a step that need not exist, so a flag opens the
 * account already on that marketplace.
 *
 * WHAT THESE GUARD
 *   1. ONE table of what a marketplace code means. It was written out three
 *      times -- the home cards, the switcher, and a currency ternary that had
 *      already drifted apart on which countries use the euro.
 *   2. An unknown code shows as itself, not as nothing. Amazon adds
 *      marketplaces, and a code this table has not met is a reason to show
 *      something plain rather than an empty card.
 *   3. The flag is shown WITH the code. Several of these are blue-and-white
 *      European flags and at 12px they are guesswork.
 */
"use strict";
const fs = require("fs");
const vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(60) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const sandbox = {console};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("D:/AltaScraper/static/js/marketplaces.js", "utf8"), sandbox);

console.log("=== every marketplace has a flag, a name and a currency ===");
check("UK", [sandbox.mktFlag("UK"), sandbox.mktShort("UK"), sandbox.mktSymbol("UK")],
      ["\u{1F1EC}\u{1F1E7}", "UK", "\u00a3"]);
check("US", [sandbox.mktShort("US"), sandbox.mktSymbol("US")], ["USA", "$"]);
check("DE is euro", sandbox.mktSymbol("DE"), "\u20ac");
check("IE is euro too -- the case the old ternary got wrong",
      sandbox.mktSymbol("IE"), "\u20ac");
check("SE is not", sandbox.mktSymbol("SE"), "kr");
check("a lowercase code still resolves", sandbox.mktShort("uk"), "UK");

console.log("\n=== an unknown code is shown, not dropped ===");
// Amazon adds marketplaces. A code this table has not met must still render.
const zz = sandbox.mktInfo("ZZ");
truthy("it has a flag of some kind", zz.flag);
check("and shows the code as its name", zz.short, "ZZ");
truthy("and does not throw", sandbox.mktChip("ZZ").indexOf("ZZ") >= 0);
check("an empty code does not crash either", typeof sandbox.mktChip(""), "string");

console.log("\n=== the chip carries the flag AND the code ===");
const chip = sandbox.mktChip("FR");
truthy("the flag is there", chip.indexOf("\u{1F1EB}\u{1F1F7}") >= 0);
truthy("and so is the code, because flags alone are guesswork at 12px",
       chip.indexOf("FR") >= 0);

console.log("\n=== the home cards and the switcher both use it ===");
const shell = fs.readFileSync("D:/AltaScraper/static/js/shell.js", "utf8");
truthy("the home card draws flags", shell.indexOf("mktflag") >= 0);
truthy("clicking one opens the account at that marketplace",
       shell.indexOf("enterAccountAt(") >= 0);
truthy("  and that function exists",
       shell.indexOf("async function enterAccountAt") >= 0);
truthy("the switcher draws flags too", /mktFlag\(m\)/.test(shell));
// Rule 12: the currency ternary existed twice and had drifted. Both gone.
check("no inline currency ternary is left",
      /CUR_SYMBOL\s*=\s*\(/.test(shell), false);
truthy("both places ask the one table", (shell.match(/mktSymbol\(/g) || []).length >= 2);

console.log("\n=== it is loaded before the code that uses it ===");
const html = fs.readFileSync("D:/AltaScraper/templates/dashboard.html", "utf8");
const iM = html.indexOf("js/marketplaces.js");
const iS = html.indexOf("js/shell.js");
truthy("marketplaces.js is on the page", iM > 0);
truthy("and loads before shell.js, which draws the flags", iM > 0 && iM < iS);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
