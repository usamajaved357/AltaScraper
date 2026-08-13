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

console.log("=== one definition, two editors ===");
check("the row is built in one place",
      (shell.match(/function _importInputRow\(/g) || []).length, 1);
check("  and rendered in both sheet editors",
      (shell.match(/\$\{_importInputRow\(\)\}/g) || []).length, 2);
check("the import call is defined once",
      (shell.match(/async function importInputSheet\(/g) || []).length, 1);
check("the status reader too",
      (shell.match(/async function refreshInputStatus\(/g) || []).length, 1);

console.log("\n=== it sits with the sheets, not somewhere else ===");
// In the Dropshipping editor it follows the input sheet URL row; in the account
// editor it sits between the input and output sheet rows.
const dsInput = shell.indexOf('id="ds_input_url"');
const dsRow = shell.indexOf("${_importInputRow()}");
check("Dropshipping: right after the input sheet URL", dsInput < dsRow, true);
const acInput = shell.indexOf('id="ac_input_url"');
const acRow = shell.indexOf("${_importInputRow()}", dsRow + 1);
const acOutput = shell.indexOf('id="ac_output_url"');
check("Account: between the input and output sheet rows",
      acInput < acRow && acRow < acOutput, true);

console.log("\n=== both editors show what is already imported ===");
check("Dropshipping refreshes the count",
      /refreshInputStatus\(\);\n\}\nasync function saveDropshippingSheets/.test(shell), true);
check("the account editor does too",
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
check("an account's own input sheet", /acc\.get\("input_spreadsheet_id"\)/.test(routes), true);
check("the Dropshipping workspace's own keys",
      /dropshipping_input_spreadsheet_id/.test(routes), true);
check("  including its tab", /dropshipping_input_tab_gid/.test(routes), true);
check("and the app-wide default last",
      /cfg\.get\("input_spreadsheet_id"\)/.test(routes), true);
check("a missing sheet is a clear refusal, not a crash",
      /has no input sheet configured/.test(routes), true);
check("a failed read names WHICH sheet",
      /Could not read the input sheet \(%s\)/.test(routes), true);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
