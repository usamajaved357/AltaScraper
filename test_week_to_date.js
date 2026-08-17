/* Week to Date is a CALENDAR week, and its comparison is the same slice of the
 * week before.
 *
 * "Week-to-date (WTD) is a calendar-week cut, not a rolling last-7-days window.
 *  Week start: Monday"
 *
 * The window itself was already right: Monday of this calendar week through
 * today, requested on its own rather than sliced out of whatever range the user
 * last picked (on a 90-day view there is no "this week" to slice, and a custom
 * range may contain no Monday at all).
 *
 * The COMPARISON was not. Last week is fetched Monday to Sunday so the dashed
 * line has somewhere to come from, and the change chip summed both in full -- a
 * partial week against a whole one. On a Wednesday that is three days against
 * seven: about -57% on trade that had not moved. Its tooltip said "against the
 * same days last week" while doing exactly the opposite.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const S = fs.readFileSync("D:/AltaScraper/static/js/sales.js", "utf8");

function fnBody(src, name){
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if(!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  for(let j = i, d = 0; j < src.length; j++){
    if(src[j] === "{") d++;
    else if(src[j] === "}" && --d === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}
const W = fnBody(S, "salesLoadWeek");

console.log("=== the window is a calendar week, starting on the set day ===");
// CHANGED FROM MONDAY TO SUNDAY, deliberately, and this is the record of it.
//
// The instruction was "Week start Monday". Then, measured against the thing this
// card is read beside: "on orbit there is sales data displayed, and it starts
// from sunday and ends at saturday". Amazon's own reports run Sunday to Saturday
// as well, and a week-on-week card offset by a day from the one you are
// comparing it against is not a comparison.
//
// So the day is now a named constant instead of an arithmetic trick, and this
// test pins THAT rather than pinning one particular day -- changing the
// constant should not break the test that the window is built from it.
truthy("which day the week starts on is a named constant",
       /const SALES_WEEK_START = [0-6];/.test(S));
truthy("  and it is Sunday, to agree with Orbit and with Amazon",
       /const SALES_WEEK_START = 0;/.test(S));
truthy("the offset is worked out FROM the constant",
       /const dow = \(today\.getUTCDay\(\) - SALES_WEEK_START \+ 7\) % 7;/.test(W));
truthy("  and the week starts there", /today\.getUTCDate\(\) - dow/.test(W));
truthy("it runs to today, not seven days back", /base\(wkStart, today\)/.test(W));
truthy("  which is a calendar cut, not a rolling window",
       !/86400000 \* 7\s*\)?\s*,\s*today/.test(W));
truthy("the prior week is the calendar week before",
       /prevStart = new Date\(wkStart\.getTime\(\) - 7 \* 86400000\)/.test(W));
truthy("it is asked for on its own, not sliced from the chosen range",
       /Built from a request of its own/.test(S));

console.log("\n=== the change compares the SAME days ===");
truthy("only as many days as this week has are summed",
       /cellsOf\(mBefore\)\.slice\(0, daysSoFar\)/.test(W));
truthy("  counted from this week's own cells",
       /const daysSoFar = cellsOf\(mNow\)\.length;/.test(W));
truthy("  and the tooltip says how many that is",
       /against the same " \+ daysSoFar \+ " day/.test(W));
truthy("the old whole-week sum is gone",
       !/const a = sum\(mNow\), b = sum\(mBefore\);/.test(W));

console.log("\n=== the dashed line is described as it is drawn ===");
truthy("the caption names the days on the chart",
       /cmp\[0\] \? cmp\[0\]\.label/.test(W));
truthy("  not last week's Sunday", !/iso\(lastMon\) \+ " to " \+ iso\(lastEnd\)\)/.test(W));

console.log("\n=== the two lines still sit day-under-day ===");
// Whatever dates they carry, Sunday belongs under Sunday -- that is the whole
// point of a week-on-week picture.
//
// CHANGED FROM POSITION TO DATE, and this is why. Position pairing is right only
// while both replies carry every day of their week, and a reply carries only the
// buckets it has figures for. The main chart had already been fixed for exactly
// this -- "a 30-day request came back with 28 columns for this period and 1 for
// the period before". Position-paired, last Friday's takings are drawn under
// this Sunday and labelled Last Week, which is the report "the dotted lines are
// not acccurately representing last week data in all graphs all over the app".
truthy("the comparison is paired by DATE, seven days back",
       /dt\.getTime\(\) - 7 \* 86400000/.test(W));
truthy("  looked up by that date", /\(back in was\) \? was\[back\] : null/.test(W));
truthy("  and not by array position", !/const byPos = \(before\.columns\|\|\[\]\)/.test(W));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
