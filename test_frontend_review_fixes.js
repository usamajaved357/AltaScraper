/* Front-end review fixes (29 Sep 2026).
 *
 * 1. The detailed listing row's Min/Max save sent `JSON.stringify(_srcBody(b))`
 *    -- but _srcBody already returns the JSON text, so the server got a quoted
 *    STRING, b.get("rule") failed, and every save said "Could not save".
 * 2. DRAFT_SRC (a draft's suppliers and profit) and AIMG (Amazon image slots)
 *    were never cleared on an account or marketplace switch, so B's same-SKU
 *    draft showed A's suppliers (and UK's showed after switching to US).
 *
 * Runs the REAL lrSaveRule and _screenResetHeld from their files.
 */
const fs = require("fs");
const vm = require("vm");
const path = require("path");
let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(66), ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
function fn(file, name) {
  const src = fs.readFileSync(path.join(__dirname, "static/js", file), "utf8");
  const m = src.match(new RegExp("(?:async )?function " + name + "\\(([\\s\\S]*?)\\r?\\n\\}\\r?\\n"));
  if (!m) throw new Error("cannot find " + name + " in " + file);
  return m[0];
}

(async () => {
  console.log("=== the detailed row's rule save sends ONE layer of JSON ===");
  {
    const sent = [];
    const s = {
      console, toast() {}, lrRule: () => ({}),
      fetch: (url, opt) => { sent.push(opt.body); return Promise.resolve({ json: () => Promise.resolve({ ok: true }) }); },
    };
    vm.createContext(s);
    vm.runInContext(fn("sourcing.js", "_srcScopeNow").replace(/^function/, "function"), s);
    vm.runInContext(fn("sourcing.js", "_srcBody"), s);
    // the account on screen, as _srcScopeNow would report it
    vm.runInContext("_srcScopeNow = function(){ return {id: 'acct_a', marketplace: 'UK'}; };", s);
    vm.runInContext(fn("listrow_detailed.js", "lrSaveRule"), s);
    await vm.runInContext("lrSaveRule('SKU-1', 'min_price', {value: '9.50'})", s);
    let parsed = null;
    try { parsed = JSON.parse(sent[0]); } catch (e) { parsed = "unparseable"; }
    check("the body parses to an OBJECT (not a quoted string)", typeof parsed, "object");
    check("  carrying the rule, the account and the marketplace",
          parsed && [parsed.rule && parsed.rule.min_price, parsed.id, parsed.marketplace], [9.5, "acct_a", "UK"]);
  }

  console.log("=== an account switch forgets a draft's suppliers and image slots ===");
  {
    const s = { console, document: { getElementById: () => null } };
    vm.createContext(s);
    vm.runInContext("const DRAFT_SRC = {'SKU-1': {state: 'ok', options: [{label: 'A supplier'}]}};" +
                    "let AIMG = {sku: 'SKU-1', state: 'ok', data: {x: 1}, err: '', justSent: 'x'};", s);
    vm.runInContext(fn("screenstate.js", "_screenResetHeld"), s);
    vm.runInContext("_screenResetHeld()", s);
    check("DRAFT_SRC is emptied", vm.runInContext("Object.keys(DRAFT_SRC).length", s), 0);
    check("AIMG is back to its empty shape (fields kept)",
          vm.runInContext("[AIMG.sku, AIMG.state, AIMG.data, AIMG.justSent, 'err' in AIMG]", s), ["", "", null, "", true]);
  }
  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();
