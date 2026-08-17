// The Week to Date card, and the dashed line that is supposed to be last week.
//
// "week to date graph is shown as empty to me on jack reacherd"
// "even i dont have any sales the graph should be displayed"
// "the dotted lines are not acccurately representing last week data in all
//  graphs all over the app"
// "on orbit there is sales data displayed, and it starts from sunday and ends
//  at saturday"
//
// Four separate faults, all measured on jack_uk for the week of 16 August 2026.

const fs = require("fs");
const S = fs.readFileSync("static/js/sales.js", "utf8");

let fails = [];
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(72) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

console.log("=== the week starts on Sunday, in one place ===");
truthy("there is one constant for it", S.includes("const SALES_WEEK_START = 0"));
truthy("  and it says which day 0 is", S.includes("0 = Sunday, 1 = Monday"));
truthy("  and why it is not Monday any more",
       S.includes("it starts from sunday and ends at saturday"));
truthy("the window is worked out from it",
       S.includes("(today.getUTCDay() - SALES_WEEK_START + 7) % 7"));
falsy("  and not from a hard-coded Monday offset",
      S.includes("(today.getUTCDay() + 6) % 7"));
// The variables were called mon/lastMon while holding a Sunday, which is a
// comment that lies in the one place comments cannot be edited away.
falsy("no variable still called `mon` holding the week start",
      S.includes("const mon = new Date(Date.UTC("));
truthy("  it is called what it is", S.includes("const wkStart = new Date(Date.UTC("));

console.log("\n=== the chart is drawn even when nothing sold ===");
// It was replaced by the sentence "Nothing recorded for this week yet" whenever
// no metric had a non-zero cell -- so a quiet week produced no chart at all.
// Asserted on the CODE, not the prose: the sentence still appears once, in the
// comment recording what was removed and why, and a test that forbids naming a
// bug is a test that deletes the reason it was fixed.
falsy("the 'nothing recorded' dead end no longer replaces the chart",
      S.includes("host.innerHTML = '<div class=\"cc\" style=\"padding:14px;font-size:12px\">'\n      + 'Nothing recorded"));
check("  and the sentence survives only as the note about it",
      (S.match(/Nothing recorded for this week yet/g) || []).length, 1);
truthy("  in a comment", S.includes('// It was replaced by the sentence "Nothing recorded'));
truthy("a week with no sales still gets a series",
       S.includes("function _sWeekSeries"));
truthy("  a week with no COLUMNS is the only thing that has none",
       S.includes("if(!n) return null;"));
truthy("  and a day Amazon has not delivered stays null, not zero",
       S.includes("would draw a sale of nothing on a day nobody has"));

console.log("\n=== one metric for both weeks ===");
// Each week picked its own: net_revenue when it had any non-zero cell, else
// ordered_sales. MEASURED on jack_uk, week of 16 August --
//   this week  net_revenue [0.0, null]   ordered_sales [0.0, 0.0]
//   last week  net_revenue [x5 null, 85.17, null]   ordered_sales [...102.21...]
// -- so the solid line could be ordered_sales and the dashed line net_revenue:
// two different quantities on one axis, one of them after Amazon's fees and the
// other before, with the dashed line sitting lower for no reason but arithmetic.
truthy("the metric is chosen once, from both replies",
       S.includes("function _sWeekMetric(now, before)"));
truthy("  by which is best KNOWN across the two", S.includes("nOrd > nNet"));
truthy("  and both series are read from that one",
       S.includes("_sWeekSeries(now, wkKey)") && S.includes("_sWeekSeries(before, wkKey)"));
truthy("with the measurement that proved it written down",
       S.includes("[0.0, null]") && S.includes("85.17"));

console.log("\n=== last week is paired BY DATE, not by position ===");
// A reply carries only the buckets it has figures for. Position-paired, last
// Friday's takings get drawn under this Sunday and labelled Last Week -- which
// is what the main chart had already been fixed for.
truthy("seven days are subtracted from the date",
       S.includes("dt.getTime() - 7 * 86400000"));
truthy("  and the day before is looked up by that date",
       S.includes("(back in was) ? was[back] : null"));
falsy("  rather than taken from the same array position",
      S.includes("const byPos = (before.columns||[])"));

console.log("\n=== a quiet period still draws its line ===");
// anyReal drops a series with no NON-ZERO value, which is as true of a period
// that traded nothing as of one nobody has figures for. A dashed line missing
// from a chart reads as the comparison being broken.
truthy("there is a separate test for 'known at all'", S.includes("const anyKnown ="));
truthy("  and it accepts a zero", S.includes("return v !== null && v !== undefined; });"));
truthy("the main chart's comparison uses it", S.includes("if(!anyKnown(cmpCells)) cmpCells = null;"));
falsy("  and no longer drops a zero period", S.includes("if(!anyReal(cmpCells)) cmpCells = null;"));
truthy("the week card's does too",
       S.includes("p.value !== null && p.value !== undefined; })) cmp = null;"));
truthy("and the difference between the two is written down",
       S.includes("nothing known   -> no line") &&
       S.includes("known, and zero -> a line along the bottom"));

console.log("\nFAILURES: " + fails.length);
fails.forEach(f => console.log("   - " + f));
process.exit(fails.length ? 1 : 0);
