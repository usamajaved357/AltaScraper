// The accessibility basics added in Milestone 12 stay in place.
//
// From the master audit (28 Sep 2026, section 14): the account and marketplace
// switchers could not be reached by keyboard; toasts were not announced; the
// dialog had no focus trap, no focus return and no label.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = 0, ran = 0;
function check(label, got, want){
  ran++;
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
              + " want=" + JSON.stringify(want)));
}
const read = p => fs.readFileSync(path.join(__dirname, p), "utf8");
const HTML = read("templates/dashboard.html");
const tagOf = id => (HTML.match(new RegExp('<[a-z]+[^>]*id="' + id + '"[^>]*>')) || [""])[0];

console.log("\n1. the switchers can be reached and used from the keyboard");
for(const id of ["nav_acctswitch", "nav_mktswitch", "nav_acctsettings"]){
  const t = tagOf(id);
  check(id + " is announced as a button", /role="button"/.test(t), true);
  check(id + " is a tab stop", /tabindex="0"/.test(t), true);
}
check("the keyboard handler is loaded", /static\/js\/a11y\.js/.test(HTML), true);

console.log("\n2. Enter and Space on a role=button click it -- once");
{
  let listener = null;
  const ctx = {document: {addEventListener: (t, f) => { if(t === "keydown") listener = f; }}};
  vm.createContext(ctx);
  vm.runInContext(read("static/js/a11y.js"), ctx);
  const mk = (tag, role) => { const el = {tagName: tag, clicks: 0,
    getAttribute: a => (a === "role" ? role : null), click(){ this.clicks++; }}; return el; };
  const ev = (key, target) => ({key, target, prevented: false,
                                preventDefault(){ this.prevented = true; }});
  const div = mk("DIV", "button");
  listener(ev("Enter", div)); listener(ev(" ", div));
  check("a div with role=button is clicked by Enter and by Space", div.clicks, 2);
  const btn = mk("BUTTON", "button");
  listener(ev("Enter", btn));
  check("a real <button> is left to the browser (no double click)", btn.clicks, 0);
  const plain = mk("DIV", null);
  listener(ev("Enter", plain));
  check("an ordinary div is not touched", plain.clicks, 0);
  const e = ev(" ", mk("SPAN", "button")); listener(e);
  check("Space does not also scroll the page", e.prevented, true);
}

console.log("\n3. toasts are announced; the dialog is labelled and keeps focus");
check("the toast is a live region",
      /id="toast"[^>]*role="status"[^>]*aria-live="polite"/.test(HTML), true);
const DLG = read("static/js/dialog.js");
check("the dialog is labelled by its title", /aria-labelledby=/.test(DLG), true);
check("  gives focus back to what opened it", /opener\.focus\(\)/.test(DLG), true);
check("  and keeps Tab inside", /e\.key === "Tab"/.test(DLG), true);

console.log("\n" + ran + " checks, " + fails + " failed");
console.log("FAILURES: " + fails);
process.exit(fails ? 1 : 0);
