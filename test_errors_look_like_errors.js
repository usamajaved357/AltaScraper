// A load that FAILED is drawn as a failure, never in the "no data" style.
//
// Several screens drew "Could not load …" inside <div class="empty"> -- the
// same muted, centred box as "nothing here yet" -- so a failure read as an
// empty account (docs/design-system.md, States). pageui.js uiError() is the one
// failure block: marked as an alert, the reason escaped, and a Try again that
// calls the screen's own loader.
"use strict";
const fs = require("fs");
const path = require("path");

let fails = 0, ran = 0;
function check(label, got, want){
  ran++;
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)));
}
const JS = path.join(__dirname, "static", "js");

console.log("\n1. uiError says it is a failure, safely");
const PU = fs.readFileSync(path.join(JS, "pageui.js"), "utf8");
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const a = PU.indexOf("function uiError(");
const uiError = new Function("esc", PU.slice(a, PU.indexOf("\n}", a) + 2) + "\nreturn uiError;")(esc);
const h = uiError("Traffic could not be loaded", "<b>timeout</b> & more", "trafficLoad");
check("it is announced as an alert", /role="alert"/.test(h), true);
check("it is marked as an error", /ui-error/.test(h), true);
check("the reason is escaped", /&lt;b&gt;timeout&lt;\/b&gt; &amp; more/.test(h), true);
check("Try again calls the loader", /onclick="trafficLoad\(\)"/.test(h), true);
check("a hostile loader name cannot inject",
      /onclick="alertxx\(\)"/.test(uiError("t", "", "alert('xx')")), true);

console.log("\n2. no screen draws a failure in the empty style any more");
const bad = [], noSec = [];
for(const f of fs.readdirSync(JS).filter(f => f.endsWith(".js"))){
  const lines = fs.readFileSync(path.join(JS, f), "utf8").split(/\r?\n/);
  lines.forEach((l, i) => {
    // Same line, any quoting or concatenation: '<div class="empty">' + "... could not"
    if(/class=\\?"empty\\?"/.test(l) && /could not/i.test(l)) bad.push(f + ":" + (i + 1));
    // Every caller names the screen that failed (batch 1 review: the open
    // screen is not always the one whose load failed).
    const m = l.match(/\buiError\(("[^"]*"), .*?, ("\w+"), ("\w+")\)/);
    if(/\buiError\(/.test(l) && !/function uiError/.test(l) && !m) noSec.push(f + ":" + (i + 1));
  });
}
check("'could not' drawn inside .empty", bad, []);
check("every uiError call names its loader and its screen", noSec, []);

console.log("\n3. a failure marks ITS screen stale, after navTo has marked it fresh");
{
  const stale = [];
  let tick = null;
  const f = new Function("esc", "screenStale", "setTimeout", "CUR_SEC",
    PU.slice(a, PU.indexOf("\n}", a) + 2) + "\nreturn uiError;");
  const ue = f(esc, s => stale.push(s), fn => { tick = fn; }, "traffic");
  ue("Sales could not be loaded", "x", "salesReload", "sales");
  check("nothing marked until the tick", stale, []);
  tick();
  check("the failed screen, not the open one", stale, ["sales"]);
}

console.log("\n" + ran + " checks, " + fails + " failed");
console.log("FAILURES: " + fails);
process.exit(fails ? 1 : 0);
