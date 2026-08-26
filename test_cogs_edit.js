// Setting what the stock cost: one cell at a time, or a whole sheet.
//
// THE RULE THAT MATTERS: 0.00 means UNKNOWN, not free. build_sku writes it when
// it had no cost to write, and hand-made SKUs carry none at all. An item that
// appears to cost nothing looks infinitely profitable, and is precisely the
// item someone would then order more of.
"use strict";
const fs = require("fs");
const path = require("path");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                    + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }

const src = fs.readFileSync(path.join(__dirname, "static/js/cogs.js"), "utf8");
// `split: _cgSplit` used to be exported here and no longer exists, which made
// this whole file crash on load rather than fail an assertion -- so every check
// below it, including the 0.00-means-unknown rule, had silently stopped running.
// See the "a sheet of costs" section for where that parser went.
const api = new Function("jsArg", "CUR_SYMBOL", src + `
  return {cogsOf, cogsCell, LOCAL: COGS_LOCAL};
`)(s => JSON.stringify(s), "£");

console.log("=== where the cost comes from ===");
check("a generated SKU carries it",
      api.cogsOf({sku: "32.99_3Days_B012B7726O"}), {cost: 32.99, source: "sku"});
// The one that produces a confident wrong number if got wrong.
check("0.00 is UNKNOWN, not free",
      api.cogsOf({sku: "0.00_3Days_B012B7726O"}), {cost: null, source: ""});
check("a hand-made SKU has no cost at all",
      api.cogsOf({sku: "46 pcs wrench"}), {cost: null, source: ""});
check("a stored cost is used when there is one",
      api.cogsOf({sku: "x_3Days_y", cogs: 4.5, cogs_source: "sku"}),
      {cost: 4.5, source: "sku"});

console.log("\n=== the cell says WHICH of the three it is ===");
truthy("no cost invites you to set one",
       /set<\/span>/.test(api.cogsCell({sku: "46 pcs wrench"})));
truthy("a known cost is shown as money",
       api.cogsCell({sku: "32.99_3Days_B0"}).indexOf("32.99") > 0);
// A figure you typed beating one parsed off a SKU is the whole point of an
// override; it has to be visible that it did.
truthy("a typed cost is marked as yours",
       /vertical-align:super/.test(
         api.cogsCell({sku: "a_3Days_b", cogs: 9.99, cogs_source: "manual"})));
truthy("the cell is clickable", /cogsEdit\(/.test(api.cogsCell({sku: "a"})));
// It sits inside a row whose click opens the drawer.
truthy("  and clicking it does not open the row behind it",
       /event\.stopPropagation\(\)/.test(api.cogsCell({sku: "a"})));

console.log("\n=== a sheet of costs ===");
// THE PARSER IS NOT IN THE BROWSER ANY MORE, and that is the fix rather than a
// regression. This section used to test _cgSplit, a line splitter that split on
// commas -- which is not what a CSV is. A product name like "Grill, Large" is
// quoted and contains one, so every column after it shifted and the cost was
// read from the wrong place. The sheet this app hands out is full of such names.
//
// routes/cogs_routes.cogs_upload_sheet now reads the file server-side through
// domain/source_bulk.read_table, which uses a real CSV reader and can also open
// a spreadsheet, which the browser version could not. So what is asserted here
// is that the browser no longer has an opinion about parsing -- keeping a second
// splitter alongside the real one is exactly how the two drift (rule 12).
const PY = fs.readFileSync(path.join(__dirname, "routes/cogs_routes.py"), "utf8");
truthy("the browser no longer splits the file itself", !/_cgSplit/.test(src));
truthy("  it hands the file to the server", /\/cogs\/upload_sheet/.test(src)
       || /\/cogs\/upload/.test(src));
truthy("the server parses it with a real CSV reader",
       /read_table/.test(PY));
truthy("  and says so, so nobody puts a splitter back in the browser",
       /split each line on commas/.test(PY));
// The confirmation has to come from the SAME reader that will do the work, or
// "Set the cost on 412 SKUs?" is the browser's guess at a number it cannot know.
truthy("the count offered for confirmation is measured, not guessed",
       /dry_run/.test(PY) && /READS THE FILE AND WRITES NOTHING/.test(PY));
// A bulk overwrite changes every profit figure in the app.
// uiConfirm, not confirm -- the app draws its own now. AWAITED, because a
// Promise is truthy and a forgotten await would approve every overwrite.
truthy("the count is confirmed before anything is written",
       /Set the cost on/.test(src) && /await uiConfirm\(/.test(src));
truthy("  and unusable rows are counted, not silently dropped",
       /skipped \d*/.test(src) || /bad\.length/.test(src));

console.log("\n=== clearing is not the same as zero ===");
truthy("an empty box clears the override rather than setting 0",
       /raw === "" \? null/.test(src));
truthy("  and the code says why", /different answers/.test(src));
truthy("a negative cost is refused", /val < 0/.test(src));

console.log("\n=== it is the way IN to the one resolver, not a second one ===");
truthy("saving goes through /cogs/set", /"\/cogs\/set"/.test(src));
// /cogs/upload_sheet, not /cogs/upload -- the second of the two upload paths was
// removed when the parsing moved to the server, and this assertion still named
// the one that went.
truthy("bulk goes through /cogs/upload_sheet", /"\/cogs\/upload_sheet"/.test(src));
check("  and nothing here writes to the listings store directly",
      /\/edit"/.test(src), false);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
