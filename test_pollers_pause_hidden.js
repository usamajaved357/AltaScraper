// The always-on pollers ask nothing while the tab is hidden, and catch up the
// moment it is shown. (Master audit section 10: three of them polled hidden
// tabs all day -- health every 60 s, the monitor and notification badges every
// 120 s. Milestone 11.)
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = 0, ran = 0;
function check(label, got, want){
  ran++;
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
              + " want=" + JSON.stringify(want)));
}
const read = p => fs.readFileSync(path.join(__dirname, p), "utf8");

let tick = null, onVis = null, gap = null;
const doc = {hidden: false,
             addEventListener: (t, f) => { if(t === "visibilitychange") onVis = f; }};
const ctx = {document: doc, setTimeout, clearTimeout,
             setInterval: (f, ms) => { tick = f; gap = ms; return 1; }, clearInterval(){}};
vm.createContext(ctx);
vm.runInContext(read("static/js/poller.js"), ctx);

let calls = 0;
vm.runInContext("altaEvery", ctx)(60000, () => { calls++; });
tick();
check("a visible tab asks on each tick", calls, 1);
doc.hidden = true; tick(); tick();
check("a hidden tab asks nothing", calls, 1);
doc.hidden = false; onVis();
check("shown again, it asks at once", calls, 2);

// THE CALLERS' ORDER. All three write altaEvery(fn, ms), the setInterval way;
// before 30 Sep 2026 that passed the function as the DELAY and a number as the
// callback, so none of them ever polled again (the bell stayed stale).
let calls2 = 0;
vm.runInContext("altaEvery", ctx)(() => { calls2++; }, 120000);
check("called (fn, ms): the delay is the number", gap, 120000);
tick();
check("  and each tick calls the function", calls2, 1);

console.log("\n  the three always-on pollers use it:");
for(const [f, fn] of [["static/js/listings.js", "pollHealth"],
                      ["static/js/monitor.js", "refreshMonBadge"],
                      ["static/js/notify.js", "notifPoll"]]){
  const src = read(f);
  check("  " + fn, new RegExp("altaEvery[^;\\n]*\\(" + fn + ",").test(src)
                    && !new RegExp("setInterval\\(" + fn + ",").test(src), true);
}

console.log("\n" + ran + " checks, " + fails + " failed");
console.log("FAILURES: " + fails);
process.exit(fails ? 1 : 0);
