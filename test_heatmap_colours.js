/* The P&L heatmap's colour has one meaning: IMPACT ON PROFIT.
 *
 * Stated by the owner, and it is the right model:
 *
 *   "Hue = direction of impact on profit, not just up/down. Income lines
 *    (Revenue, Gross Profit, Net Profit, Units, Orders): Green = up vs prior
 *    period, Red = down. Cost lines (COGS, FBA fees, Referral fees, Ad Spend,
 *    Refunds, Storage): Inverse - Green = down (favorable to profit), Red = up
 *    (unfavorable). So red always means bad for profit, green always good."
 *
 * WHAT IT USED TO DO. Every row was shaded on one green scale by the SIZE of
 * the number, so a month of record Amazon fees was the darkest green on the
 * sheet -- green meaning good. The colour carried "this is a big number", which
 * nobody needs, because the number is printed in the cell.
 *
 *   "Intensity / saturation = magnitude of change ... It's scaled per row, not
 *    across the whole table. A dark red in Referral Fees does NOT equal same $
 *    as dark red in Revenue - it's dark because it's a big move for that line."
 *
 * Which is why the scale is a PERCENTAGE against the previous column: a
 * percentage is per-row by construction.
 *
 * ONE THING IS KEPT from the rule this replaces. A profit row that goes -80
 * then -50 has improved, and on change alone the -50 would be green -- a green
 * cell on a day that lost fifty pounds. On the rows where the sign is the whole
 * point, a negative value is red regardless. That is not an exception to "red
 * means bad for profit"; it is the clearest case of it.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const src = fs.readFileSync("D:/AltaScraper/static/js/sales.js", "utf8");
const body = src.slice(src.indexOf("const _S_SIGNED"), src.indexOf("/* ---- actions"));
const tint = new Function("V", "P", "K", "G", body + " return _sTint(V,P,K,G);");
const delta = new Function("V", "P", body + " return _sDeltaPct(V,P);");

const isRed = c => /239,\s?68,\s?68/.test(c);
const isGreen = c => /45,\s?212,\s?168/.test(c);
const alpha = c => { const m = /,\s*\.(\d+)\)/.exec(c || ""); return m ? Number("." + m[1]) : 0; };

console.log("=== an INCOME line: up is good ===");
truthy("revenue up is green", isGreen(tint(130, 100, "ordered_sales", "up")));
truthy("revenue down is red", isRed(tint(70, 100, "ordered_sales", "up")));
truthy("orders up is green", isGreen(tint(12, 10, "orders", "up")));
truthy("units down is red", isRed(tint(8, 10, "units", "up")));

console.log("\n=== a COST line: the SAME movement means the opposite ===");
// This is the whole point. Fees rising is a red day even though the number rose.
truthy("fees UP is RED", isRed(tint(130, 100, "referral_fees", "down")));
truthy("fees DOWN is GREEN", isGreen(tint(70, 100, "referral_fees", "down")));
truthy("ad spend up is red", isRed(tint(130, 100, "spend", "down")));
truthy("refunds down is green", isGreen(tint(70, 100, "refunds", "down")));
truthy("cost of goods up is red", isRed(tint(130, 100, "cogs", "down")));

console.log("\n  -- the old behaviour, stated so it cannot come back --");
// Under the size scale, the biggest fee figure on the row was the darkest GREEN.
truthy("a rise in fees is not green",
       !isGreen(tint(130, 100, "referral_fees", "down")));
truthy("and a fall in revenue is not green",
       !isGreen(tint(70, 100, "ordered_sales", "up")));

console.log("\n=== intensity is the SIZE of the change ===");
check("under 1% is flat and left unshaded", tint(100.4, 100, "ordered_sales", "up"), "");
truthy("a 3% move is faint", alpha(tint(103, 100, "ordered_sales", "up")) > 0);
truthy("  and a 30% move is stronger",
       alpha(tint(130, 100, "ordered_sales", "up"))
       > alpha(tint(103, 100, "ordered_sales", "up")));
truthy("the steps climb all the way",
       alpha(tint(103, 100, "ordered_sales", "up"))
       < alpha(tint(107, 100, "ordered_sales", "up"))
       && alpha(tint(107, 100, "ordered_sales", "up"))
       < alpha(tint(115, 100, "ordered_sales", "up"))
       && alpha(tint(115, 100, "ordered_sales", "up"))
       < alpha(tint(130, 100, "ordered_sales", "up")));
// Scaled per ROW by construction: the same PERCENTAGE gives the same strength
// whatever the units, so a big move in fees is as visible as one in revenue.
check("the same % move is the same strength on any row",
      alpha(tint(130, 100, "ordered_sales", "up")),
      alpha(tint(70, 100, "referral_fees", "down")));

console.log("\n=== a loss is red however it got there ===");
truthy("a loss that is improving is still red", isRed(tint(-50, -80, "profit", "up")));
truthy("  and at full strength", alpha(tint(-50, -80, "profit", "up")) >= 0.4);
truthy("a negative margin is red", isRed(tint(-5, -2, "margin_pct", "up")));
truthy("a profit that grew is green", isGreen(tint(125, 100, "profit", "up")));
truthy("a profit that shrank is red", isRed(tint(75, 100, "profit", "up")));

console.log("\n=== the change itself ===");
check("a straightforward rise", delta(130, 100), 30);
check("a fall", delta(50, 100), -50);
check("from zero to something is a big move, not infinity", delta(50, 0), 100);
check("zero to zero is flat", delta(0, 0), 0);
check("nothing before it cannot be a change", delta(100, null), null);
check("and neither can a missing value", delta(null, 100), null);

console.log("\n=== nothing rests on colour alone ===");
check("the first column is not shaded", tint(100, null, "ordered_sales", "up"), "");
check("a missing day is not shaded", tint(null, 100, "profit", "up"), "");
check("  nor a value that is not a number", tint("n/a", 100, "profit", "up"), "");
truthy("every cell prints its number", />'\+_sEsc\(txt\)\+'<\/td>/.test(src));
// "Hover any cell - it shows exact $ and % delta vs prior that drove the color."
truthy("and the hover gives the figure it is compared against",
       /% vs "/.test(src) && /_sNum\(prev, m\.kind, ser\.currency\)/.test(src));
truthy("  saying which way that is for profit",
       /better for profit/.test(src) && /worse for profit/.test(src));

console.log("\n=== the direction comes from the metric, not from this file ===");
// `good` is set beside each metric's own definition in domain/sales_data.py, so
// a new cost row cannot be added and be shaded as though it were income.
truthy("the tint is told which way is good", /_sTint\(shown, prev, m\.key, m\.good\)/.test(src));
truthy("the server sends it", /"good": good/.test(
       fs.readFileSync("D:/AltaScraper/routes/sales_routes.py", "utf8")));
["profit", "margin_pct"].forEach(function(k){
  truthy("  " + k + " is known to be signed", src.indexOf('"' + k + '"') >= 0);
});

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
