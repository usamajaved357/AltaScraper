/* The Import button sits with the sheet settings, in both editors, defined once. */
const fs = require("fs");
let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(60),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const shell = fs.readFileSync("D:/AltaScraper/static/js/shell.js", "utf8");
const routes = fs.readFileSync("D:/AltaScraper/routes/input_routes.py", "utf8");
// WHERE THE SHEET-FINDING LIVES NOW. It was written out inside the import route,
// and then Generate needed exactly the same thing -- open the account's sheet,
// resolve the tab by gid, read it with the generator's own reader. Two copies
// would be two opinions about which sheet an account's products come from, and
// that kind of disagreement is invisible until listings appear in the wrong
// place. It moved to data/input_import.py and both callers use it (Rule 12).
const impl = fs.readFileSync("D:/AltaScraper/data/input_import.py", "utf8");

// ONE EDITOR NOW, not two. The Dropshipping sheet editor has gone with the
// workspace it belonged to -- it described itself as "eBay -> Amazon
// arbitrage", which CLAUDE.md rule 1 says this app does not do. Every account
// sets its own sheets from its own card, which is where this always belonged.
console.log("=== one definition, one editor ===");
check("the row is built in one place",
      (shell.match(/function _importInputRow\(/g) || []).length, 1);
check("  and rendered in the account sheet editor",
      (shell.match(/\$\{_importInputRow\(\)\}/g) || []).length, 1);
check("the import call is defined once",
      (shell.match(/async function importInputSheet\(/g) || []).length, 1);
check("the status reader too",
      (shell.match(/async function refreshInputStatus\(/g) || []).length, 1);

console.log("\n=== it sits with the sheets, not somewhere else ===");
// In the account editor it sits between the input and output sheet rows, so
// the three things about one sheet are read together.
const acInput = shell.indexOf('id="ac_input_url"');
const acRow = shell.indexOf("${_importInputRow()}");
const acOutput = shell.indexOf('id="ac_output_url"');
check("Account: between the input and output sheet rows",
      acInput < acRow && acRow < acOutput, true);
// And nothing is left pointing at the editor that has gone.
check("no leftover Dropshipping sheet fields",
      shell.indexOf('id="ds_input_url"'), -1);
check("  nor its save handler",
      /saveDropshippingSheets/.test(shell), false);

console.log("\n=== the editor shows what is already imported ===");
// \r?\n, not a literal \n: this repo checks out CRLF on Windows, so the literal
// form passes until git next rewrites the file and then fails with the code
// completely unchanged.
check("the account editor refreshes the count",
      /How many products are already imported[\s\S]{0,120}refreshInputStatus\(\);/.test(shell), true);
check("the status always names the DATE",
      /j\.imported_at \? \(" · "\+j\.imported_at\)/.test(shell), true);
check("  and says plainly when there is nothing",
      /nothing imported yet/.test(shell), true);

console.log("\n=== the result distinguishes new rows from updated ones ===");
check("added and updated are both reported",
      /j\.added\+" new, "\+j\.updated\+" updated"/.test(shell), true);
check("the button cannot be double-pressed",
      /btn\.disabled=true/.test(shell) && /btn\.disabled=false/.test(shell), true);
check("failures show the server's reason",
      /esc\(\(j&&j\.error\)\|\|"failed"\)/.test(shell), true);

console.log("\n=== the server finds the sheet wherever it is configured ===");
check("an account's own input sheet",
      /account\.get\("input_spreadsheet_id"\)/.test(impl), true);
// The Dropshipping workspace kept its input sheet under dropshipping_* config
// keys. It has been removed -- it described itself as "eBay -> Amazon
// arbitrage", which CLAUDE.md rule 1 says this app does not do -- and no
// dropshipping_* key was ever present in config.json, so that branch never
// returned a value in any real run. Asserting its ABSENCE now.
check("no Dropshipping-only sheet keys are read",
      /dropshipping_input_spreadsheet_id/.test(impl), false);
check("  nor its tab", /dropshipping_input_tab_gid/.test(impl), false);
check("and the app-wide default last",
      /cfg\.get\("input_spreadsheet_id"\)/.test(impl), true);
check("a missing sheet is a clear refusal, not a crash",
      /has no input sheet configured/.test(impl), true);
// The point of moving it: Generate no longer tells you to press Import, it
// imports. Both paths call the same function.
check("the import route calls the shared one",
      /import_for_workspace\(/.test(routes), true);
const listing = fs.readFileSync("D:/AltaScraper/routes/listing_routes.py", "utf8");
check("  and so does Generate, when the queue is empty",
      /import_for_workspace\(/.test(listing), true);
check("  saying so in the run log rather than silently",
      /the queue is empty/.test(listing), true);
// "Import failed" on an account with several sheets configured sends you
// looking through all of them.
check("a failed read names WHICH sheet",
      /Could not read the input sheet \(%s/.test(impl), true);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
