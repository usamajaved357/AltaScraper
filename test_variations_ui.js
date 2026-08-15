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

console.log("\n=== step 3 can actually be REACHED ===");
/* Reported: "it is giving error which i select 2 products of same type. i am not
 * able to go to step 3."
 *
 * Two separate faults, and neither was about the products being the same type:
 *
 *   1. VAR_STEPS names three steps and _varSteps was only ever called with 1 and
 *      2. The third step existed in the caption and nowhere else -- there was no
 *      code path that could reach it, so it was not blocked, it was never built.
 *
 *   2. Arriving at step 2 immediately ran the check with no theme chosen and
 *      painted a red "Not ready yet". Nothing was wrong: choosing the theme is
 *      the job of the step you have just arrived at.
 */
function stepSandbox(reply){
  const sb = makeSandbox();
  sb.fetch = function(url, opts){
    return Promise.resolve({json: () => Promise.resolve(reply(String(url), opts))});
  };
  vm.createContext(sb);
  vm.runInContext(src, sb);
  return sb;
}

check("the screen names three steps", run(makeSandboxWithSrc(), "VAR_STEPS.length"), 3);
function makeSandboxWithSrc(){
  const s = makeSandbox();
  vm.runInContext(src, s);
  return s;
}
{
  const s = makeSandboxWithSrc();
  const three = run(s, "_varSteps(3)");
  truthy("and step 3 can be drawn as the current one",
         three.indexOf("Check and join") >= 0);
  // The first two are marked done with a tick when you are on the third.
  check("  with the first two behind you", (three.match(/✓/g) || []).length, 2);
}

(async function(){
  // Two products of the same type, a theme chosen, and a server that says the
  // checks passed. This must land on step 3 with the apply button on screen.
  const sb5 = stepSandbox(function(url){
    if(url.indexOf("/variations/themes") >= 0){
      return {ok: true, product_type: "SQUEEGEE", themes: ["SIZE", "COLOR"], checked: true};
    }
    if(url.indexOf("/variations/preview") >= 0){
      return {ok: true, can_apply: true, problems: [], parent_sku: "FAN-PARENT",
              product_type: "SQUEEGEE",
              payload: {theme: "SIZE", parent: {sku: "FAN-PARENT"},
                        children: [{sku: "FAN-WHITE"}, {sku: "FAN-BLACK"}]}};
    }
    return {ok: true};
  });
  run(sb5, `VARS.items = [
    {sku: "FAN-WHITE", title: "white", asin: "B01", product_type: "SQUEEGEE"},
    {sku: "FAN-BLACK", title: "black", asin: "B02", product_type: "SQUEEGEE"}];
    VARS.picked = ["FAN-WHITE", "FAN-BLACK"];`);

  let err = null;
  try{ await run(sb5, "variationsStep2()"); }catch(e){ err = String(e); }
  check("step 2 runs without throwing", err, null);
  // THE const BUG. `pt` was declared const and reassigned from the server's
  // answer six lines later, inside a try with an empty catch -- so the
  // TypeError vanished and the fallback never happened.
  truthy("  and reassigning the product type from the server does not throw",
         !(err || "").indexOf || (err || "").indexOf("constant") < 0);
  const s2 = sb5.els.varbody.innerHTML || "";
  truthy("step 2 offers the theme picker", s2.indexOf("var_theme") >= 0);
  truthy("  and its own step element, so step 3 can move it",
         s2.indexOf('id="var_steps"') >= 0);
  // Arriving must NOT open on a telling-off.
  const first = sb5.els.varpreview.innerHTML || "";
  check("arriving at step 2 does not open on a problem list",
        first.indexOf("Still to do") >= 0, false);

  err = null;
  try{
    run(sb5, "document.getElementById('var_theme').value = 'SIZE';");
    await run(sb5, "variationsPreview()");
  }catch(e){ err = String(e); }
  check("the check runs without throwing", err, null);
  const steps = sb5.els.var_steps.innerHTML || "";
  truthy("STEP 3 IS NOW THE CURRENT STEP", steps.indexOf("Check and join") >= 0);
  const prev = sb5.els.varpreview.innerHTML || "";
  truthy("  and the payload that would be sent is shown",
         prev.indexOf("FAN-PARENT") >= 0);
  truthy("  with the button that sends it",
         prev.indexOf("variationsApply()") >= 0);

  // And when the checks do NOT pass, it stays on 2 and says what is left.
  const sb6 = stepSandbox(function(url){
    if(url.indexOf("/variations/themes") >= 0){
      return {ok: true, product_type: "SQUEEGEE", themes: ["SIZE"], checked: true};
    }
    return {ok: true, can_apply: false, parent_sku: "P1",
            problems: ["Pick what makes these products different from each other."]};
  });
  run(sb6, `VARS.items = [{sku:"A", product_type:"SQUEEGEE"},{sku:"B", product_type:"SQUEEGEE"}];
            VARS.picked = ["A","B"];`);
  await run(sb6, "variationsStep2()");
  await run(sb6, "variationsPreview()");
  truthy("an unfinished family stays on step 2",
         (sb6.els.var_steps.innerHTML || "").indexOf("2 Say what differs") >= 0);
  truthy("  and lists what is left to do, not an error",
         (sb6.els.varpreview.innerHTML || "").indexOf("Still to do") >= 0);
  check("  in amber, not red",
        (sb6.els.varpreview.innerHTML || "").indexOf("#4a2323") >= 0, false);

  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();
