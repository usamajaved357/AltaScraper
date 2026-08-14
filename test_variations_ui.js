/* The Variations screen must actually RUN.
 *
 * Reported: "the variation families page is still not working it is showing me
 * ReferenceError: h is not defined".
 *
 * It was not subtly broken -- it never drew anything. variationsRender built
 * its markup with `h += ...` from its first line and never declared `h`, so the
 * function threw before producing a single element. It read as fine because
 * `let h` does appear a few lines above, at the top of _varSteps(), which is a
 * different function returning its own string.
 *
 * The other tests for this screen check the SHAPE of the source text, which is
 * exactly why they passed while the page was dead. This one executes the real
 * file against a DOM stub, which is the only way that class of fault shows up.
 */
"use strict";
const fs = require("fs");
const vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(60) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

// A DOM thin enough to be honest: elements remember their innerHTML, which is
// all these renderers touch.
function makeSandbox(){
  const els = {};
  const el = id => (els[id] = els[id] || {id, innerHTML: "", value: "",
                                          style: {}, dataset: {},
                                          classList: {add(){}, remove(){}, toggle(){}},
                                          querySelectorAll: () => [],
                                          addEventListener(){}});
  const s = {
    console,
    document: {
      getElementById: id => el(id),
      querySelectorAll: () => [],
      querySelector: () => null,
      createElement: () => ({style: {}, classList: {add(){}, remove(){}}}),
    },
    window: {addEventListener(){}, matchMedia: () => ({matches: false})},
    // The debounce on the search box calls these; without them the harness
    // raises a ReferenceError of its OWN and blames the code under test.
    setTimeout: () => 1,
    clearTimeout: () => {},
    fetch: () => Promise.resolve({json: () => Promise.resolve({ok: true, rows: []})}),
    toast: () => {},
    esc: x => String(x == null ? "" : x),
    // Defined in users.js and used by EIGHT other files, variations.js among
    // them. In the browser that works because classic scripts share one global
    // scope; here the file is loaded on its own, so the harness has to supply
    // it or every row that renders a click handler throws.
    jsArg: s => "'" + String(s == null ? "" : s).replace(/\\/g, "\\\\")
                       .replace(/'/g, "\\'") + "'",
    CUR_ACCOUNT: {id: "jack_uk", label: "Jack"},
    WS_MARKET: "UK",
    els,
  };
  s.window.document = s.document;
  vm.createContext(s);
  return s;
}

const src = fs.readFileSync("D:/AltaScraper/static/js/variations.js", "utf8");

// A top-level `let` in a vm script does NOT become a property of the sandbox,
// so VARS and the functions have to be reached by evaluating inside the
// context rather than off the sandbox object. Everything below goes through
// this, which also means the calls are made exactly as the browser makes them.
function run(sb, code){
  return vm.runInContext(code, sb);
}
function callSafely(sb, code){
  try{ run(sb, code); return null; }
  catch(e){ return String(e); }
}

console.log("=== the screen renders without throwing ===");
const sb = makeSandbox();
vm.runInContext(src, sb);

// Step 1: the picker, with nothing loaded yet.
run(sb, "VARS.items = [];");
let threw = callSafely(sb, "variationsRender('')");
check("variationsRender does not throw", threw, null);
truthy("and it put something on the page", (sb.els.varbody.innerHTML || "").length > 200);

// The explanation, the steps and the search box are the three things step 1 is.
const out1 = sb.els.varbody.innerHTML || "";
truthy("it explains what a variation family IS before asking anything",
       out1.indexOf("What this does") >= 0);
truthy("it says nothing is sent until you have seen it",
       out1.indexOf("Nothing is sent to Amazon") >= 0);
truthy("it offers the search box", out1.indexOf("varq") >= 0);

console.log("\n=== with listings loaded ===");
const sb2 = makeSandbox();
vm.runInContext(src, sb2);
run(sb2, `VARS.items = [
  {sku: "FAN-WHITE", title: "Ceiling fan, white", asin: "B01", status: "LIVE"},
  {sku: "FAN-BLACK", title: "Ceiling fan, black", asin: "B02", status: "LIVE"},
  {sku: "LAMP-1",    title: "Desk lamp",          asin: "B03", status: "LIVE"}];`);
threw = callSafely(sb2, "variationsRender('')");
check("it renders a list without throwing", threw, null);
const out2 = sb2.els.varbody.innerHTML || "";
truthy("the listings are on the page", out2.indexOf("FAN-WHITE") >= 0);
truthy("  all of them", out2.indexOf("LAMP-1") >= 0);

// Filtering is the next thing anyone does.
threw = callSafely(sb2, "variationsRender('fan')");
check("filtering does not throw", threw, null);

console.log("\n=== step 2 renders too ===");
// The step the screen was reported dead-ending at previously.
const sb3 = makeSandbox();
vm.runInContext(src, sb3);
run(sb3, `VARS.items = [
  {sku: "FAN-WHITE", title: "Ceiling fan, white", asin: "B01", status: "LIVE"},
  {sku: "FAN-BLACK", title: "Ceiling fan, black", asin: "B02", status: "LIVE"}];
  VARS.picked = ["FAN-WHITE", "FAN-BLACK"];`);
threw = callSafely(sb3,
  "typeof variationsBuild === 'function' ? variationsBuild() : variationsRender('')");
check("the second step does not throw", threw, null);

console.log("\n=== every variations* function is callable ===");
// A cheap sweep for the same class of fault: call each renderer and make sure
// none dies on an undeclared variable.
const sb4 = makeSandbox();
vm.runInContext(src, sb4);
run(sb4, "VARS.items = [];");
const names = run(sb4,
  "Object.getOwnPropertyNames(this).concat([]), " +
  "['variationsRender','variationsFilter','variationsBuild','variationsPreview'," +
  "'variationsOnOpen','variationsPick','variationsLoad']" +
  ".filter(n => typeof eval('typeof ' + n) === 'string' && eval('typeof ' + n) === 'function')");
truthy("there are variations* functions to call", (names || []).length > 0);
(names || []).forEach(function(n){
  // A ReferenceError is the bug this file exists for. Anything else (no
  // network, a missing element) is the stub, not the code.
  const e2 = callSafely(sb4, n + "('')");
  // Boolean(), because check() compares strictly and `null` is not `false` --
  // a passing call would otherwise be reported as a failure.
  const isRef = Boolean(e2 && e2.indexOf("ReferenceError") >= 0);
  check("  " + n + " raises no ReferenceError", isRef, false);
});

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
