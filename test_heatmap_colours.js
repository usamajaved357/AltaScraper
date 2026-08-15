/* The profit-and-loss heatmap has a logic, and it was not following it.
 *
 * "the colors in the profit and loss heatmap has a logic, i want you to check
 *  if that is following the logic"
 *
 * IT WAS NOT. Every row was shaded on one green scale running from the row's
 * lowest value to its highest. On a Profit row that goes from -50 to +100 that
 * made a fifty-pound LOSS the palest green on the row -- green meaning good,
 * and a faint green reading as "a quiet day" rather than "money went out". The
 * sign, which is the only thing anyone looks at on a profit row, was the one
 * thing the colour did not carry.
 *
 * The logic a P&L heatmap has to follow: DIVERGE AT ZERO. Red below, green
 * above, intensity from distance from zero -- not from position between the
 * row's two extremes.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const src = fs.readFileSync("D:/AltaScraper/static/js/sales.js", "utf8");
const tint = new Function("V", "LO", "HI", "KEY", `
  ${src.slice(src.indexOf("const _S_SIGNED"), src.indexOf("/* ---- actions"))}
  return _sTint(V, LO, HI, KEY);
`);

const isRed = c => /239, ?68, ?68/.test(c);
const isGreen = c => /45, ?212, ?168/.test(c);
const alpha = c => { const m = /,\s*\.?(\d+)\)/.exec(c || ""); return m ? Number("." + m[1]) : 0; };

console.log("=== a profit row that contains a loss ===");
// The row this exists for: -50 to +100.
truthy("a loss is RED", isRed(tint(-50, -50, 100, "profit")));
truthy("  and so is a small one", isRed(tint(-5, -50, 100, "profit")));
truthy("a profit is GREEN", isGreen(tint(100, -50, 100, "profit")));
truthy("  and so is a small one", isGreen(tint(5, -50, 100, "profit")));
check("break-even is left unshaded", tint(0, -50, 100, "profit"), "");

console.log("\n  -- the old behaviour, stated so it cannot come back --");
// Under the single-hue scale, -50 was f=0 and therefore the PALEST GREEN.
truthy("a loss is not shaded green at all",
       !isGreen(tint(-50, -50, 100, "profit")));

console.log("\n=== intensity comes from distance from ZERO ===");
truthy("a bigger loss is stronger than a small one",
       alpha(tint(-50, -50, 100, "profit")) > alpha(tint(-5, -50, 100, "profit")));
truthy("a bigger profit is stronger than a small one",
       alpha(tint(100, -50, 100, "profit")) > alpha(tint(5, -50, 100, "profit")));
// Each side scaled against its own worst case, so one catastrophic day does
// not flatten every profit on the row into an identical shade.
const withDisaster = tint(100, -5000, 100, "profit");
const without = tint(100, -50, 100, "profit");
check("a huge loss elsewhere does not wash out the profits",
      alpha(withDisaster), alpha(without));

console.log("\n=== margin behaves the same way ===");
truthy("a negative margin is red", isRed(tint(-12, -12, 30, "margin_pct")));
truthy("a positive one is green", isGreen(tint(30, -12, 30, "margin_pct")));

console.log("\n=== rows that cannot go negative keep the single scale ===");
// Sessions, units, revenue: there is no "bad" end, only more and less.
truthy("the lowest sessions figure is still green",
       isGreen(tint(0, 0, 500, "sessions")));
truthy("  and the highest is stronger",
       alpha(tint(500, 0, 500, "sessions")) > alpha(tint(0, 0, 500, "sessions")));
check("a row where every value is identical is not shaded",
      tint(5, 5, 5, "sessions"), "");

console.log("\n=== nothing is shaded on colour alone ===");
// Every cell prints its number, so the grid reads in black and white and to
// anyone who cannot separate red from green. Colour only ranks.
truthy("the cell writes its value into the table, not just a tooltip",
       />'\+_sEsc\(txt\)\+'<\/td>/.test(src));
check("a missing day gets no shading at all", tint(null, 0, 10, "profit"), "");
check("  and neither does a value that is not a number",
      tint("n/a", 0, 10, "profit"), "");

console.log("\n=== the signed list names the metrics that can go negative ===");
["profit", "margin_pct"].forEach(function(k){
  truthy("  " + k, src.indexOf('"' + k + '"') >= 0);
});

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
