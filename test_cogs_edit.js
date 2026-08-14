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
const api = new Function("jsArg", "CUR_SYMBOL", src + `
  return {cogsOf, cogsCell, split: _cgSplit, LOCAL: COGS_LOCAL};
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
check("comma separated", api.split("SKU,COGS"), ["SKU", "COGS"]);
check("tab separated too", api.split("SKU\tCOGS"), ["SKU", "COGS"]);
// Product names contain commas constantly; splitting naively corrupts the row.
check("a quoted field keeps its commas",
      api.split('"Fan, 52cm, white",12.50'), ["Fan, 52cm, white", "12.50"]);
check("  and an escaped quote survives",
      api.split('"He said ""hi""",1'), ['He said "hi"', "1"]);

truthy("columns are found by NAME, not position", /head\.indexOf/.test(src));
truthy("  accepting what people actually call them",
       /sellersku/.test(src) && /costofgoods/.test(src));
truthy("a file with no cost column is refused with what it DID find",
       /Found: /.test(src));
// A bulk overwrite changes every profit figure in the app.
truthy("the count is confirmed before anything is written",
       /Set the cost on/.test(src) && /confirm\(/.test(src));
truthy("  and unusable rows are counted, not silently dropped",
       /skipped \d*/.test(src) || /bad\.length/.test(src));

console.log("\n=== clearing is not the same as zero ===");
truthy("an empty box clears the override rather than setting 0",
       /raw === "" \? null/.test(src));
truthy("  and the code says why", /different answers/.test(src));
truthy("a negative cost is refused", /val < 0/.test(src));

console.log("\n=== it is the way IN to the one resolver, not a second one ===");
truthy("saving goes through /cogs/set", /"\/cogs\/set"/.test(src));
truthy("bulk goes through /cogs/upload", /"\/cogs\/upload"/.test(src));
check("  and nothing here writes to the listings store directly",
      /\/edit"/.test(src), false);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
