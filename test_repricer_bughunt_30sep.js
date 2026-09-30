/* Repricer screen bugs found in the 30 Sep 2026 bug hunt. Each check fails on
 * the code before its fix. Runs the real sourcingGetFees for the first one. */
const fs = require("fs"), vm = require("vm"), path = require("path");
const read = (f) => fs.readFileSync(path.join(__dirname, "static/js", f), "utf8");
const ACT = read("sourcing_actions.js"), DET = read("sourcing_detail.js"),
      ROW = read("sourcing_row.js"), MAIN = read("sourcing.js");
let fails = 0;
const check = (label, ok) => { if (!ok) fails++; console.log("  %s %s", label.padEnd(66), ok ? "OK" : "FAIL"); };

(async function () {
  // 1. The "Amazon fee" pill passes the SKU: only that SKU is asked about.
  const fn = (ACT.match(/async function sourcingGetFees\(btn, sku\)\{[\s\S]*?\n\}/) || [""])[0];
  check("sourcingGetFees takes a SKU", !!fn);
  const sent = [];
  const ctx = {
    _srcUrl: (u) => u, _srcBody: (o) => JSON.stringify(o), toast: () => {},
    srcConfirm: async () => {}, sourcingLoad: () => {},
    fetch: async (u, o) => { sent.push(JSON.parse(o.body)); return { json: async () => ({ ok: true, note: "" }) }; },
  };
  vm.createContext(ctx);
  vm.runInContext(fn + "\nthis.f = sourcingGetFees;", ctx);
  await ctx.f("SKU-1");
  check("the pill (called with a SKU) asks about that SKU only",
        JSON.stringify(sent[0]) === JSON.stringify({ skus: ["SKU-1"] }));
  sent.length = 0;
  await ctx.f(null);
  check("the toolbar button (no SKU) still asks about all of them",
        JSON.stringify(sent[0]) === "{}");

  // 2. The supplier table's delivery line is given the fields it reads.
  check("the delivery line is handed delivery_min/max, not delivery_text",
        /delivery_min: s\.delivery_min/.test(DET) && !/delivery_text: s\.delivery_text/.test(DET));

  // 3. Unknown suppliers are not described as unbuyable.
  check("the n/m tag counts unknown links apart from dead ones",
        /o\.state === 'unknown'/.test(ROW) && /unknown, not out/.test(ROW));

  // 4. The master switch comes from the list reply, never "off" on a failed fetch.
  check("the master switch is read from the list reply",
        /SRC_MASTER = !!j\.master_enabled/.test(MAIN) && !/catch\(e\)\{ _master = false; \}/.test(MAIN));

  // 5. An account switch resets everything the Repricer holds (runs the real
  //    _screenResetHeld with the Repricer's globals declared as the files do).
  const SS = fs.readFileSync(path.join(__dirname, "static/js/screenstate.js"), "utf8");
  const reset = (SS.match(/function _screenResetHeld\(\)\{[\s\S]*?\n\}/) || [""])[0];
  const c2 = { document: { getElementById: () => null } };
  vm.createContext(c2);
  vm.runInContext(
    "let SRC_ROWS=[1]; let SRC_RULE={}; let SRC_ROW_RULES={a:1}; let SRC_MASTER=true;"
    + "let SRC_MKT='UK'; let SRC_DEFAULT_TARGET={k:1}; let SRC_FILTER='armed';"
    + "let SRC_LAST_J={}; let SRC_LASTBULK={attached:3}; let SRC_SEL=new Set(['x']);"
    + "let SRC_PICK_SEQ=4;\n" + reset + "\n_screenResetHeld();"
    + "this.out={f:SRC_FILTER,b:SRC_LASTBULK,r:SRC_ROWS.length,s:SRC_SEL.size,"
    + "p:SRC_PICK_SEQ,m:SRC_MASTER,j:SRC_LAST_J};", c2);
  const o = c2.out;
  check("switch clears the card filter and the last upload report",
        o.f === "" && o.b === null);
  check("  and the rows, the ticked SKUs and the master switch",
        o.r === 0 && o.s === 0 && o.m === false && o.j === null);
  check("  and abandons a picker load in flight", o.p === 5);

  // 6. The Enroll picker drops a late or superseded reply.
  const RA = read("sourcing_row_actions.js");
  check("the picker checks its sequence and the account before painting",
        /const seq = \+\+SRC_PICK_SEQ/.test(RA) && /if\(stale\(\)\) return;/.test(RA));
  check("  and Enroll posts to the account the list was drawn for",
        /_srcBody\(\{sku:sku\}, sc\)/.test(RA));
  check("sourcingLoad paints only its newest reply",
        /_seq !== SRC_LOAD_SEQ/.test(MAIN));

  // 7. "Last sheet upload": Track everything no longer stores a bare list, and
  //    the report draws nothing for anything but an upload reply.
  const DLG = read("sourcing_dialogs.js");
  const rep = (DLG.match(/function sourcingUploadReport\(\)\{[\s\S]*?\n\}/) || [""])[0];
  const c3 = { _sesc: String };
  vm.createContext(c3);
  vm.runInContext("let SRC_LASTBULK=[{sku:'A'}];\n" + rep
    + "\nthis.a=sourcingUploadReport(); SRC_LASTBULK={attached:2,rows:[]};"
    + "this.b=sourcingUploadReport();", c3);
  check("a list of rows draws no report (was 'undefined attached')", c3.a === "");
  check("  an upload reply still draws one", /2 attached/.test(c3.b));
  check("Track everything does not set it", !/SRC_LASTBULK = j\.rows/.test(DLG));

  // 8. Save dialogs: one save at a time, errors shown, account checked.
  check("the Save button is disabled while saving",
        /if\(okBtn\.disabled\) return;/.test(DLG) && /okBtn\.disabled = true;/.test(DLG));
  check("  a thrown save is said, not silent", /toast\("Not saved: "/.test(DLG));
  check("  a switch while open saves nothing", /_srcStillIn\(openScope\)/.test(DLG));

  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();
