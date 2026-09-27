// After an account switch, no screen shows -- or keeps -- the old account's data.
//
// WHY THIS EXISTS (master audit, 28 Sep 2026, section 4):
//   S4  most screens kept their last reply in an object and skipped the load
//       when it was there, so reopening one in account B redrew account A.
//   S5  a reply landing after the switch was painted anyway; and "if busy,
//       return" dropped B's request while A's was still in flight.
//   S3  the Dr PPC console kept A's plan draft, and Save posted it into B.
//   S7  SKU-keyed caches (LIVE_MIRROR, COGS_LOCAL, ...) answered B's rows with
//       A's figures.
// The real files run here in a sandbox; `fetch` switches the account while a
// request is in flight, exactly like pressing the switcher mid-load.
// Milestone 3.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS = path.join(__dirname, "static", "js");
const read = f => fs.readFileSync(path.join(JS, f), "utf8");
let fails = 0, ran = 0;
function check(label, got, want){
  ran++;
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(68) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
              + " want=" + JSON.stringify(want)));
}

function makeDom(){
  const els = {};
  return {
    els,
    getElementById(id){
      if(!els[id]) els[id] = {id, innerHTML: "", style: {}, value: "",
                              querySelector: () => null, remove(){ delete els[id]; }};
      return els[id];
    },
    querySelectorAll: () => [],
    addEventListener(){},
  };
}

function sandbox(){
  const document = makeDom();
  const ctx = {
    document, console, JSON, Object, Array, String, Number, Math, Date, Set, Map,
    Promise, isFinite, encodeURIComponent, setTimeout, clearTimeout,
    CUR_ACCOUNT: {id: "acct_A"}, WS_MARKET: "UK",
    toast(){}, esc: s => String(s == null ? "" : s),
    jsArg: require("./test_helpers.js").jsArg,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(read("scopeq.js") + "\n" + read("screenstate.js"), ctx);
  return ctx;
}

/* A fetch whose reply is held until release() -- so the test can switch the
   account while it is "in flight". */
function heldFetch(ctx, reply){
  const pending = [];
  ctx.fetch = function(url){
    return new Promise(res => pending.push(() => res({
      ok: true, headers: {get: () => "application/json"},
      json: async () => (typeof reply === "function" ? reply(url) : reply),
    })));
  };
  return {release: () => { while(pending.length) pending.shift()(); },
          count: () => pending.length};
}
const tick = () => new Promise(r => setTimeout(r, 0));
function switchTo(ctx, id){
  ctx.CUR_ACCOUNT = {id};
  vm.runInContext("screenForgetAll()", ctx);
}

(async () => {
  console.log("\n1. Finance: a reply landing after the switch is not painted (S5)");
  {
    const ctx = sandbox();
    vm.runInContext(read("finance.js"), ctx);
    ctx.financeRender = () => { ctx.__painted = (ctx.__painted || 0) + 1; };
    const f = heldFetch(ctx, {ok: true, rows: [{asin: "A-ROW"}], totals: {}});
    const p = vm.runInContext("financeLoad()", ctx);
    await tick();
    switchTo(ctx, "acct_B");
    f.release(); await p;
    check("account A's rows were not drawn on account B's screen",
          ctx.__painted || 0, 0);
    check("  and not kept either", vm.runInContext("FIN.rows.length", ctx), 0);
  }

  console.log("\n2. Hourly: the old request's busy flag does not block the new one (S5)");
  {
    const ctx = sandbox();
    vm.runInContext(read("hourly.js"), ctx);
    ctx.hourlyRender = () => {};
    const f = heldFetch(ctx, url => ({ok: true, url}));
    vm.runInContext("hourlyLoad()", ctx);           // A's request, held
    await tick();
    switchTo(ctx, "acct_B");
    vm.runInContext("hourlyLoad()", ctx);           // B's request must go out
    await tick();
    check("account B's request was sent while A's was still in flight",
          f.count(), 2);
    f.release(); await tick(); await tick();
    const got = vm.runInContext("HRLY.data && HRLY.data.url", ctx) || "";
    check("  and what is kept is B's", /account=acct_B/.test(got), true);
    check("  (the request now names its account -- S8)", /account=/.test(got), true);
  }

  console.log("\n3. Reopening a screen after the switch loads, not redraws (S4)");
  {
    const ctx = sandbox();
    vm.runInContext(read("ppcanalytics.js").replace(/^[\s\S]*?(const PPCA\s*=)/, "$1"), ctx);
    vm.runInContext("PPCA.data = {who: 'acct_A'}; PPCA.loading = true;", ctx);
    switchTo(ctx, "acct_B");
    check("PPCA.data is gone", vm.runInContext("PPCA.data", ctx), null);
    check("  and its loading flag is clear", vm.runInContext("PPCA.loading", ctx), false);
  }

  console.log("\n4. Dr PPC: a plan drafted in A is never saved into B (S3)");
  {
    const ctx = sandbox();
    vm.runInContext(read("drppc_console.js"), ctx);
    vm.runInContext("DRPC.draft = {goal: 'acct_A plan'}; DRPC.plan = {x: 1};", ctx);
    switchTo(ctx, "acct_B");
    check("the draft is dropped on the switch", vm.runInContext("DRPC.draft", ctx), null);
    let posted = 0;
    ctx.fetch = async () => { posted++; return {json: async () => ({ok: true})}; };
    ctx.ppcQS = () => "account=acct_B";
    await vm.runInContext("drpcSavePlan()", ctx);
    check("  and Save sends nothing", posted, 0);
  }

  console.log("\n5. SKU-keyed caches are emptied (S7)");
  {
    const ctx = sandbox();
    vm.runInContext("var LIVE_MIRROR = {SKU1: {price: 9}}; var COGS_LOCAL = {SKU1: 3};"
      + "var LISTING_METRICS = {SKU1: {}}; var LR_ASKED = new Set(['SKU1']);"
      + "var SCHEMAS = {HOME: {_mkt: 'UK'}}; var PPC_BY_ASIN = {B0: {}};"
      + "var PPC_KEY = 'acct_A|UK';", ctx);
    switchTo(ctx, "acct_B");
    check("LIVE_MIRROR", vm.runInContext("Object.keys(LIVE_MIRROR).length", ctx), 0);
    check("COGS_LOCAL (read before the row's own cost)",
          vm.runInContext("Object.keys(COGS_LOCAL).length", ctx), 0);
    check("LISTING_METRICS / LR_ASKED",
          vm.runInContext("Object.keys(LISTING_METRICS).length + LR_ASKED.size", ctx), 0);
    check("SCHEMAS (UK schema drawn for a US listing)",
          vm.runInContext("Object.keys(SCHEMAS).length", ctx), 0);
    check("PPC per ASIN, and the key it was for",
          vm.runInContext("[PPC_BY_ASIN, PPC_KEY]", ctx), [null, ""]);
  }

  console.log("\n6. A -> B -> A still abandons the first A request");
  {
    const ctx = sandbox();
    const sc = vm.runInContext("screenScope()", ctx);
    switchTo(ctx, "acct_B"); switchTo(ctx, "acct_A");
    ctx.__sc = sc;
    check("same account and marketplace, but not the same visit",
          vm.runInContext("screenStillIn(__sc)", ctx), false);
  }

  console.log("\n7. a schema asked for before the switch does not leave B without one");
  {
    const ctx = sandbox();
    vm.runInContext("var SCHEMAS = {};", ctx);
    vm.runInContext(read("howworks.js"), ctx);
    const f = heldFetch(ctx, {ok: true, enums: {x: 1}, marketplace: "UK"});
    const pA = vm.runInContext('_loadOneSchema("HOME", "?mkt=UK", "UK")', ctx);
    await tick();
    switchTo(ctx, "acct_B");                        // abandons A's request
    const pB = vm.runInContext('_loadOneSchema("HOME", "?mkt=UK", "UK")', ctx);
    await tick();
    check("B asked afresh instead of sharing A's request", f.count(), 2);
    f.release(); await pA; await pB;
    check("  and B has its schema", !!vm.runInContext("SCHEMAS.HOME", ctx), true);
  }

  console.log("\n8. repricer rules, families and keyword reports are reset too");
  {
    const ctx = sandbox();
    vm.runInContext("var SRC_ROW_RULES = {SKU1: {min_price: '9'}}; var SRC_MASTER = true;"
      + "var LR_RULES_ASKED = true; var LR_FAMILIES = {P: {}}; var LR_FAM_ASKED = true;"
      + "var SQP = {data: {a: 1}, note: 'x', loading: true};", ctx);
    switchTo(ctx, "acct_B");
    check("A's floor is not left to pre-fill B's dialog",
          vm.runInContext("Object.keys(SRC_ROW_RULES).length", ctx), 0);
    check("  the rules and families will be asked for again",
          vm.runInContext("[LR_RULES_ASKED, LR_FAMILIES, LR_FAM_ASKED]", ctx), [false, null, false]);
    check("  the auto-pricing flag is not A's", vm.runInContext("SRC_MASTER", ctx), false);
    check("  the keyword report is gone", vm.runInContext("SQP.data", ctx), null);
  }

  console.log("\n9. the inventory badge updates on entering an account");
  {
    // enterAccount calls invBadgeRefresh BEFORE screenForgetAll -- the order
    // that made every reply look stale when it checked the whole scope.
    const ctx = sandbox();
    ctx.CUR_ACCOUNT = {id: "acct_B"};
    vm.runInContext(read("inventory.js"), ctx);
    const f = heldFetch(ctx, {count: 7});
    const p = vm.runInContext("invBadgeRefresh()", ctx);
    await tick();
    vm.runInContext("screenForgetAll()", ctx);      // the rest of enterAccount
    f.release(); await p;
    check("the badge shows B's count",
          vm.runInContext('document.getElementById("inv_badge").textContent', ctx), 7);
  }

  console.log("\n" + ran + " checks, " + fails + " failed");
  console.log("FAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})().catch(e => { console.log("CRASHED: " + (e && e.stack || e)); process.exit(1); });
