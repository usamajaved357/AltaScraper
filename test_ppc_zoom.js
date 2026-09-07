/* Does drag-to-zoom resolve column indices into real dates now? */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = "D:\\AltaScraper";

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(58) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                              + " want=" + JSON.stringify(want)));
}

const shared = fs.readFileSync(path.join(ROOT, "static/js/ppcshared.js"), "utf8");

// A minimal world: SC_LAST as salesCombo fills it, plus the loaders the zoom
// calls at the end.
const harness = `
  const SC_LAST = {
    ppca_rev:   {columns: ["2026-08-09","2026-08-10","2026-08-11","2026-08-12"]},
    ppcc_spend: {columns: ["2026-09-01","2026-09-02","2026-09-03"]},
  };
  let reloaded = 0;
  const window = {};
  ${shared}
  window.ppcaLoad = function(){ reloaded++; };
  return {
    resolve: ppcZoomResolve, zoom: ppcZoomTo, PPCWIN: PPCWIN,
    reloads: function(){ return reloaded; },
  };
`;
const W = new Function(harness)();

console.log("=== an INDEX becomes the date that column was drawn with ===");
check("index 0 on ppca_rev", W.resolve(0, "ppca_rev"), "2026-08-09");
check("  index 3", W.resolve(3, "ppca_rev"), "2026-08-12");
// THE BUG: this used to become the literal string "23", which reached the
// server as a date and answered "Invalid isoformat string: '23'".
check("an index past the end clamps rather than escaping",
      W.resolve(23, "ppca_rev"), "2026-08-12");
check("a different chart uses ITS OWN columns",
      W.resolve(1, "ppcc_spend"), "2026-09-02");

console.log("\n=== a real DATE is passed straight through ===");
// The day-trail cards call the same handler with dates, which is why one
// function had to take both.
check("a date stays a date", W.resolve("2026-08-20", "ppca_rev"), "2026-08-20");
check("  and is trimmed to ten characters",
      W.resolve("2026-08-20T00:00:00Z", "ppca_rev"), "2026-08-20");

console.log("\n=== the window it sets ===");
W.zoom(1, 3, "ppca_rev", "ppcaLoad");
check("start", W.PPCWIN.start, "2026-08-10");
check("  end", W.PPCWIN.end, "2026-08-12");
check("  and it reloaded once", W.reloads(), 1);

// A BACKWARDS DRAG IS STILL A RANGE. Dragging right-to-left is normal.
W.zoom(3, 1, "ppca_rev", "ppcaLoad");
check("dragging backwards gives the same window", [W.PPCWIN.start, W.PPCWIN.end],
      ["2026-08-10", "2026-08-12"]);

console.log("\n=== it refuses rather than sending rubbish ===");
const before = [W.PPCWIN.start, W.PPCWIN.end];
check("an unknown chart id changes nothing",
      W.zoom(0, 2, "no_such_chart", "ppcaLoad"), false);
check("  and the window is untouched", [W.PPCWIN.start, W.PPCWIN.end], before);
check("nulls change nothing", W.zoom(null, null, "ppca_rev", "ppcaLoad"), false);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
