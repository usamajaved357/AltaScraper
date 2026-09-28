// The product page never lets a reply for one account change another's screen.
//
// editField (autofix.js) is how the PDP saves a field. Its reply used to update
// the row with that SKU in ROWS whenever it landed -- after a switch, that is
// the NEW account's same-SKU row (SKUs repeat across accounts). And the PDP
// image generator (pdp_imagegen.js) polled forever after a 404 and placed a
// finished batch into whatever listing was open (known-issues: PDP).
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
const JS = f => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
function sliceFn(src, name){
  const a = src.indexOf("async function " + name + "(");
  let depth = 0, i = src.indexOf("{", a);
  for(; i < src.length; i++){
    if(src[i] === "{") depth++;
    else if(src[i] === "}"){ depth--; if(depth === 0) break; }
  }
  return src.slice(a, i + 1);
}

(async () => {
  console.log("\n1. editField: a save reply after a switch leaves the new account's row alone");
  const AF = JS("autofix.js");
  const scope = {acct: "A", gen: 1};
  let release;
  const env = {
    ROWS: [{sku: "SAME-SKU", title: "A's title"}],
    acctBody: o => Object.assign({account: scope.acct}, o),
    screenScope: () => ({acct: scope.acct, gen: scope.gen}),
    screenStillIn: sc => sc.acct === scope.acct && sc.gen === scope.gen,
    fetch: () => new Promise(res => { release = () => res({json: async () => ({ok: true})}); }),
    updateLocalCol: (r, k, v) => { r[k] = v; },
  };
  const names = Object.keys(env);
  const editField = new Function(...names, sliceFn(AF, "editField") + "\nreturn editField;")
                      (...names.map(k => env[k]));
  const p = editField("SAME-SKU", "col", "title", "typed in A");
  // The switch: B is now open, and B has a row with the same SKU.
  scope.acct = "B"; scope.gen = 2;
  env.ROWS.length = 0; env.ROWS.push({sku: "SAME-SKU", title: "B's title"});
  release();
  const got = await p;
  check("the save is reported as done (the server wrote to A)", got.ok, true);
  check("  and marked stale", !!got.stale, true);
  check("B's same-SKU row is untouched", env.ROWS[0].title, "B's title");

  console.log("\n2. the barcode save and the image generator honour it");
  const PDP = JS("pdp.js");
  const bc = sliceFn(PDP, "pdpBarcodeSave");
  check("pdpBarcodeSave returns on a stale save before touching ROWS",
        bc.indexOf("if(j.stale) return;") > 0 && bc.indexOf("if(j.stale) return;") < bc.indexOf("ROWS[i]"), true);
  const IG = JS("pdp_imagegen.js");
  check("the PDP image poller stops on 404", /_r\.status === 404\)\{\s*clearInterval\(t\);\s*PDPIG\.running = false;/.test(IG), true);
  check("  and does not place a batch after the account/marketplace moved",
        IG.indexOf("_moved() ? 0 : await _pdpigPlace(") > 0, true);

  console.log("\n" + ran + " checks, " + fails + " failed");
  console.log("FAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})().catch(e => { console.log("CRASHED: " + (e && e.stack || e)); process.exit(1); });
