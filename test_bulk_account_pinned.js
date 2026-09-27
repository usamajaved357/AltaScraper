// A bulk action acts on the account it STARTED in, and stops if that changes.
//
// WHY THIS EXISTS. Every bulk loop in the browser read the open account afresh
// for each SKU, so switching account part-way sent the rest of the loop to the
// NEW account's rows -- and SKUs are shared between accounts, so those rows
// existed. Measured in the master audit (28 Sep 2026) with a probe that
// switched after the first request: S1->A S2->B S3->B. For the GTIN exemption
// that is a declaration to Amazon on the wrong products; for arming, a
// repricer let loose; for Delete, a live listing removed from Amazon.
//
// Each loop is run here for real, in a sandbox, with a fetch() that switches
// the account after the first request. Every request must name the account the
// loop started in, and the loop must stop rather than carry on. Milestone 2.
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
  console.log("  " + label.padEnd(70) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
              + " want=" + JSON.stringify(want)));
}

/* Pull one top-level function (or const) out of a file by name. */
function extract(src, name){
  const re = new RegExp("(^|\\n)(async\\s+)?function\\s+" + name + "\\s*\\(");
  const m = re.exec(src);
  if(!m) throw new Error("no function " + name);
  let i = src.indexOf("{", m.index + m[0].length - 1);
  // skip to the body's opening brace (after the parameter list)
  let depth = 0, p = src.indexOf("(", m.index + m[1].length);
  for(let k = p; k < src.length; k++){
    if(src[k] === "(") depth++;
    else if(src[k] === ")"){ depth--; if(depth === 0){ i = src.indexOf("{", k); break; } }
  }
  depth = 0;
  for(let k = i; k < src.length; k++){
    if(src[k] === "{") depth++;
    else if(src[k] === "}"){ depth--; if(depth === 0) return src.slice(m.index, k + 1); }
  }
  throw new Error("unbalanced " + name);
}

function sandbox(extra){
  const sent = [];
  const ctx = {
    CUR_ACCOUNT: {id: "acct_A"}, WS_MARKET: "UK",
    console, JSON, Object, Set, Map, Array, String, Number, Promise, Math,
    toast: () => {}, uiAlert: async () => {}, uiConfirm: async () => true,
    document: {getElementById: () => null},
    sent,
  };
  ctx.fetch = async (url, opts) => {
    const body = opts && opts.body ? JSON.parse(opts.body) : {};
    sent.push({url, account: body.account || body.id || ""});
    // THE SWITCH, after the first request lands.
    if(sent.length === 1) ctx.CUR_ACCOUNT = {id: "acct_B"};
    return {json: async () => ({ok: true})};
  };
  Object.assign(ctx, extra || {});
  vm.createContext(ctx);
  return ctx;
}

(async () => {
  const REQ = read("reqscope.js");

  console.log("\n1. GTIN exemption, several at once");
  {
    const ctx = sandbox({
      selectedSkus: () => ["S1", "S2", "S3"],
      splitByDraft: s => ({drafts: s, live: []}),
    });
    vm.runInContext(REQ + "\n" + read("gtin.js"), ctx);
    await vm.runInContext("bulkGtinExemption(true)", ctx);
    check("every request named the account the loop started in",
          ctx.sent.map(s => s.account), ["acct_A"]);
    check("  and it stopped instead of carrying on in the new one",
          ctx.sent.length, 1);
  }

  console.log("\n2. repricer: arm several at once");
  {
    const SRC = read("sourcing.js");
    const ctx = sandbox({SRC_MASTER: true, sourcingLoad: async () => {}});
    vm.runInContext(
      ["_srcBody", "_srcScopeNow", "_srcStillIn", "sourcingBulkArm"]
        .map(n => extract(SRC, n)).join("\n")
      + '\nconst _SRC_MOVED = "moved";'
      + '\nfunction _srcPicked(){ return ["S1","S2","S3"]; }', ctx);
    await vm.runInContext("sourcingBulkArm(true)", ctx);
    check("every arm named the account the loop started in",
          ctx.sent.map(s => s.account), ["acct_A"]);
    check("  and it stopped", ctx.sent.length, 1);
  }

  console.log("\n3. repricer: one rule across several");
  {
    const SRC = read("sourcing.js");
    const ctx = sandbox({sourcingLoad: async () => {}, SRC_ROWS: []});
    vm.runInContext(
      ["_srcBody", "_srcScopeNow", "_srcStillIn", "_srcBulkRule",
       "sourcingSaveRuleQuiet"].map(n => extract(SRC, n)).join("\n")
      + '\nconst _SRC_MOVED = "moved";'
      + '\nfunction _srcPicked(){ return ["S1","S2","S3"]; }', ctx);
    await vm.runInContext('_srcBulkRule({direction: "up_only"}, "x")', ctx);
    check("every rule save named the account the loop started in",
          ctx.sent.map(s => s.account), ["acct_A"]);
  }

  console.log("\n4. Delete and Approve, several at once");
  for(const [fn, url] of [["bulkDelete", "/delete"], ["bulkStatus", "/approve"]]){
    const MT = read("miles_template.js");
    const ctx = sandbox({
      selectedSkus: () => ["S1", "S2", "S3"],
      splitByDraft: s => ({drafts: s, amazonOnly: []}),
      _draftOnlyNote: () => "",
      ROWS: [{sku: "S1", row: 3}, {sku: "S2", row: 2}, {sku: "S3", row: 1}],
      clearSelection: () => {}, loadRows: () => {},
    });
    vm.runInContext(REQ + "\n" + extract(MT, fn), ctx);
    await vm.runInContext(fn + (fn === "bulkStatus" ? '("APPROVED")' : "()"), ctx);
    check(url + ": every request named the account the loop started in",
          ctx.sent.map(s => s.account), ["acct_A"]);
    check(url + ":   and it stopped", ctx.sent.length, 1);
  }

  console.log("\n4b. switched WHILE THE QUESTION WAS OPEN: nothing is sent");
  for(const [fn, arg] of [["bulkDelete", "()"], ["bulkStatus", '("APPROVED")']]){
    const MT = read("miles_template.js");
    const ctx = sandbox({
      selectedSkus: () => ["S1", "S2"],
      splitByDraft: s => ({drafts: s, amazonOnly: []}),
      _draftOnlyNote: () => "",
      ROWS: [{sku: "S1", row: 2}, {sku: "S2", row: 1}],
      clearSelection: () => {}, loadRows: () => {},
    });
    ctx.uiConfirm = async () => { ctx.CUR_ACCOUNT = {id: "acct_B"}; return true; };
    vm.runInContext(REQ + "\n" + extract(MT, fn), ctx);
    await vm.runInContext(fn + arg, ctx);
    check(fn + ": nothing sent to the account switched to mid-question",
          ctx.sent.filter(s => s.account === "acct_B").length, 0);
  }
  {
    const ctx = sandbox({
      selectedSkus: () => ["S1", "S2"],
      splitByDraft: s => ({drafts: s, live: []}),
    });
    ctx.uiConfirm = async () => { ctx.CUR_ACCOUNT = {id: "acct_B"}; return true; };
    vm.runInContext(REQ + "\n" + read("gtin.js"), ctx);
    await vm.runInContext("bulkGtinExemption(true)", ctx);
    check("GTIN: no declaration sent to the account switched to mid-question",
          ctx.sent.filter(s => s.account === "acct_B").length, 0);
  }

  console.log("\n5. the ticks do not survive a change of account");
  const SHELL = read("shell.js");
  const ea = extract(SHELL, "enterAccount");
  check("enterAccount clears the listing ticks", /SELECTED\.clear\(\)/.test(ea), true);
  check("  and the repricer's", /SRC_SEL\s*=\s*new Set\(\)/.test(ea), true);

  console.log("\n" + ran + " checks, " + fails + " failed");
  console.log("FAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})().catch(e => { console.log("CRASHED: " + (e && e.stack || e)); process.exit(1); });
