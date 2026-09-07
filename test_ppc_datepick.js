/* Changing ONE date box must keep the other.
 *
 *     "maybe due to date i am not able to select more than 2 days in past"
 *
 * The boxes show the window on screen. While the 7/14/30/90 buttons are
 * driving, PPCWIN.start and .end are EMPTY -- what the boxes display is the
 * SERVER's window, not a picked one. The handler fell back to PPCWIN, found
 * nothing, and `if(!s) s = e` set the start to the end. So touching the end box
 * collapsed a thirty-day view to a single day, and every attempt to move one
 * end threw the other away.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = "D:\\AltaScraper";

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(60) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                              + " want=" + JSON.stringify(want)));
}

const shared = fs.readFileSync(path.join(ROOT, "static/js/ppcshared.js"), "utf8");
const harness = `
  const window = {};
  const SC_LAST = {};
  // Defined in shell.js, which this file does not load. Same shape: a value
  // safe to drop inside a single-quoted inline handler.
  function jsArg(v){ return "'" + String(v).replace(/'/g, "\\\\'") + "'"; }
  ${shared}
  window.reload = function(){};
  return {W: PPCWIN, setDate: ppcSetDate, range: ppcDateRange,
          clear: ppcClearDates};
`;
const M = new Function(harness)();

// The state the page is in on arrival: day buttons driving, so PPCWIN carries
// no picked dates, and the boxes are drawn from the server's window.
function arrive(){
  M.W.start = ""; M.W.end = "";
  M.range({window: {start: "2026-08-09", end: "2026-09-07"}}, "reload");
}

console.log("=== the boxes show the window the server answered for ===");
arrive();
check("shown start", M.W.shown.start, "2026-08-09");
check("  shown end", M.W.shown.end, "2026-09-07");

console.log("\n=== changing the END keeps the START ===");
// THE BUG: this used to set start = end and leave a one-day window.
arrive();
M.setDate("end", "2026-09-05", "reload");
check("start is untouched", M.W.start, "2026-08-09");
check("  end moved", M.W.end, "2026-09-05");

console.log("\n=== changing the START keeps the END ===");
arrive();
M.setDate("start", "2026-07-01", "reload");
check("start moved back nearly ten weeks", M.W.start, "2026-07-01");
check("  end is untouched", M.W.end, "2026-09-07");

console.log("\n=== and then moving the other one still works ===");
M.setDate("end", "2026-07-15", "reload");
check("start held", M.W.start, "2026-07-01");
check("  end moved", M.W.end, "2026-07-15");

console.log("\n=== a backwards pick is swapped, not refused ===");
// Picking the end first and then an earlier start is a normal way to use two
// boxes; answering it with an error would be pedantry about click order.
arrive();
M.setDate("start", "2026-09-20", "reload");
check("the earlier date is the start", M.W.start, "2026-09-07");
check("  and the later one the end", M.W.end, "2026-09-20");

console.log("\n=== clearing hands the window back to the day buttons ===");
M.clear("reload");
check("start cleared", M.W.start, "");
check("  end cleared", M.W.end, "");

console.log("\n=== the boxes never bar the past ===");
// A `min` would be the other way to produce "cannot select more than 2 days
// back". There is none, and only the future is capped.
const html = (function(){
  M.W.start = ""; M.W.end = "";
  return M.range({window: {start: "2026-08-09", end: "2026-09-07"}}, "reload");
})();
check("no minimum date is set", /min=/.test(html), false);
check("  but the future is capped", /max="20\d\d-\d\d-\d\d"/.test(html), true);
check("  and they are real date inputs", /type="date"/.test(html), true);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
