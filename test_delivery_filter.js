/* The Repricer's Delivery column, Delivery filter and Extra handling controls
 * (owner, 27 Oct 2026):
 *
 *   "Whenever I want to see the products that have a handling time of less
 *    than 3 days, I should be able to filter them. If I want to select all of
 *    them and then set a certain handling time ... I should be able to do that."
 *   "If I want to see the items that have a collective shipping time of less
 *    than 5 days, I should be able to see them"
 *   "It should be clear to me that these products have a handling time on the
 *    supplier as this, but we have +1 handling time on these items ... But I
 *    don't want it to be like sentences and a lot of buttons."
 *
 * Runs the real _srcVisible, _srcDeliveryDays and _rpDelivery. */
const fs = require("fs"), vm = require("vm"), path = require("path");
const read = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const MENU = read("sourcing_menu.js"), ROW = read("sourcing_row.js"),
      BULK = read("sourcing_bulk.js"), ACT = read("sourcing_row_actions.js"),
      DET = read("sourcing_detail.js"), MAIN = read("sourcing.js"),
      ACTIONS = read("sourcing_actions.js"),
      STATE = read("screenstate.js");
let fails = 0;
const check = (label, ok) => { if (!ok) fails++; console.log("  %s %s", label.padEnd(66), ok ? "OK" : "FAIL"); };
const pick = (src, re) => { const m = src.match(re); if (!m) { fails++; console.log("  could not find " + re); } return m ? m[0] : ""; };

const s = { _sesc: (x) => String(x).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;") };
vm.createContext(s);
vm.runInContext("var SRC_ROWS = []; var SRC_FILTER = ''; var SRC_DFILT = {by: '', max: 3};"
  + " var SRC_RULE = {handling_buffer_days: 1};\n"
  + pick(MENU, /function _srcVisible\(\)\{[\s\S]*?\n\}/) + "\n"
  + pick(MENU, /function _srcDeliveryDays\(r, by\)\{[\s\S]*?\n\}/) + "\n"
  + pick(ACT, /function _srcAcctBuffer\(\)\{[\s\S]*?\n\}/) + "\n"
  + pick(ACT, /function _srcBufOwn\(r\)\{[\s\S]*?\n\}/) + "\n"
  + pick(ROW, /function _rpDelivery\(r\)\{[\s\S]*?\n\}/), s);

// Postage 2 days, the account's Extra handling +1:
//   FAST  supplier 1d -> handling 0 + 1 default extra = 1 -> buyer 3
//   MID   supplier 3d -> handling 1 + 2 own extra     = 3 -> buyer 5
//   SLOW  supplier 6d -> handling 4 + own 0           = 4 -> buyer 6
//   NONE  no delivery date at all
const row = (sku, eb, lead, buf, own, mode, action) => ({
  sku, mode: mode || "dry_run", own_rule: own ? { handling_buffer_days: buf } : {},
  current: { lead_days: lead },
  decision: { action: action || "nothing", breakdown: eb == null ? {} : {
    supplier_dispatch_days: eb, lead_days: lead, buffer_days: buf,
    shipping_policy_days: 2, buyer_days: lead + 2 } } });
const ROWS = [row("FAST", 1, 1, 1, false, "live"), row("MID", 3, 3, 2, true),
              row("SLOW", 6, 4, 0, true, "live", "update"), row("NONE", null, null, 0, false)];
const shown = (by, max, card, op) => {
  s.SRC_ROWS = ROWS; s.SRC_DFILT = { by, max, op: op || "le" }; s.SRC_FILTER = card || "";
  return vm.runInContext("_srcVisible().map(function(r){ return r.sku; }).join(',')", s);
};

console.log("=== the filter ===");
check("off: every row", shown("", 3) === "FAST,MID,SLOW,NONE");
check("to the buyer in 5 days or less: FAST and MID", shown("total", 5) === "FAST,MID");
check("handling 3 days or less: FAST and MID", shown("handling", 3) === "FAST,MID");
check("handling 1 day or less: FAST only", shown("handling", 1) === "FAST");
check("supplier 3 days or less: FAST and MID", shown("supplier", 3) === "FAST,MID");
check("handling EXACTLY 1: FAST only", shown("handling", 1, "", "eq") === "FAST");
check("handling EXACTLY 3: MID only (up to 3 would add FAST)", shown("handling", 3, "", "eq") === "MID"
      && shown("handling", 3) === "FAST,MID");
check("handling exactly 2: nobody", shown("handling", 2, "", "eq") === "");
check("exactly still leaves out a SKU with no delivery date", shown("total", 0, "", "eq").indexOf("NONE") < 0);
check("up to / exactly is one more segmented control, not a row of buttons",
      /uiSeg\(SRC_DFILT_OP, SRC_DFILT\.op === "eq" \? "eq" : "le", "sourcingDeliveryOp"\)/.test(MENU)
      && /\{v: "le", label: "up to"\}, \{v: "eq", label: "exactly"\}/.test(MENU));
check("  and the focus goes back to whichever of the two had it",
      /a\.closest\("#src_dbar \.seg"\)/.test(MENU));
check("a SKU with no delivery date is never counted as short", shown("total", 60).indexOf("NONE") < 0);
check("it combines with the cards: armed AND to the buyer in 6 or less",
      shown("total", 6, "armed") === "FAST,SLOW");
check("  and with Would change", shown("handling", 9, "update") === "SLOW");
check("'Tracked' (the empty card) clears it as well",
      /function sourcingFilter\(key\)\{[\s\S]*?if\(!key\) SRC_DFILT\.by = "";/.test(MENU));
check("changing it clears the ticks, like a card does",
      /function _srcDeliveryRedraw\(\)\{[\s\S]*?SRC_SEL = new Set\(\);/.test(MENU));
check("  and gives the focus back only to what had it (no phone keyboard on a tap)",
      /const inBox = [\s\S]*?inBox \? document\.getElementById\("src_dmax"\)\s*: segNow \? segNow\.querySelector\("\.segbtn\.on"\) : null;/.test(MENU));
check("the box is text with a number keypad, so the caret survives the redraw",
      /id="src_dmax" type="text" inputmode="numeric"/.test(MENU));
check("the number is applied as typed, not on the change a click fires",
      /oninput="sourcingDeliveryMax\(this\.value\)"/.test(MENU) && !/onchange="sourcingDeliveryMax/.test(MENU));
check("'Tracked' is lit only when neither filter is on",
      /const on = key \? \(SRC_FILTER === key\) : \(!SRC_FILTER && !SRC_DFILT\.by\);/.test(DET));
check("the empty table says when the delivery limit is the cause",
      /SRC_DFILT\.by \? 'No SKU is within that delivery limit\. '/.test(MAIN));
check("ONE control, from the shared segmented helper",
      /uiSeg\(SRC_DFILT_BY, SRC_DFILT\.by, "sourcingDeliveryBy"\)/.test(MENU));
check("  drawn under the stat cards", /_statCards\(j\) \+ _srcDeliveryBar\(\)/.test(MAIN));
check("an account switch turns it off", /SRC_DFILT\.by = ""/.test(STATE));

console.log("\n=== the Delivery cell: numbers, not sentences ===");
const cell = (r) => vm.runInContext("_rpDelivery(" + JSON.stringify(r) + ")", s);
const fast = cell(ROWS[0]), mid = cell(ROWS[1]), slow = cell(ROWS[2]), none = cell(ROWS[3]);
check("the total to the buyer leads", /<b>3d<\/b>/.test(fast) && /<b>5d<\/b>/.test(mid));
check("  with its handling + postage beside it", /\(1\+2\)/.test(fast) && /\(3\+2\)/.test(mid));
check("then the supplier's days -- 'Supplier', which may be a website", /Supplier 1d/.test(fast) && /Supplier 3d/.test(mid) && !/eBay/.test(fast + mid));
check("an own +2 is in plain ink, bold", /<b style="color:var\(--ink\)">\+2<\/b>/.test(mid));
check("an inherited +1 is muted, like the pill's 'default'", /<span>\+1<\/span><\/div>/.test(fast) && !/<b[^>]*>\+1/.test(fast));
check("no colour that means 'caution' on this screen", !/rp-y/.test(fast + mid + slow));
check("an own +0 under a +1 default is shown (it is opting out)", /<b style="color:var\(--ink\)">\+0<\/b>/.test(slow));
s.SRC_RULE = {handling_buffer_days: 0};
check("  but with no default above it, +0 is not drawn", !/\+0/.test(cell(ROWS[2])));
s.SRC_RULE = {handling_buffer_days: 1};
check("the sum is in the tooltip", /handling 3d \(incl\. \+2 extra, this SKU.s own\) \+ postage 2d = 5d/.test(mid));
check("  and says when the extra is the account's", /account default/.test(fast));
check("no delivery date: a dash, never a 0", /&mdash;/.test(none) && !/0d/.test(none));
const unknownOwn = cell(Object.assign({}, ROWS[0], {own_rule: null}));
check("own_rule unknown: drawn as own, never guessed to be default", /color:var\(--ink\)">\+1/.test(unknownOwn));
check("  and its tooltip claims neither own nor default",
      /incl\. \+1 extra\)/.test(unknownOwn) && !/own|account default/.test(unknownOwn.split('"')[1]));
check("the column has a heading", />Delivery<\/th>/.test(MAIN));
check("the open panel still spans every column", /colspan="11"/.test(ROW) && !/colspan="10"/.test(ROW));

console.log("\n=== setting the extra days ===");
check("the selection bar has Set extra handling", /onclick="sourcingBulkBuffer\(\)"[\s\S]*?Set extra handling<\/button>/.test(BULK));
check("  the single and the bulk save patch the held rows ONE way",
      /_srcPatchRow\(sku, rule, scope\);/.test(BULK) && /_srcPatchRow\(sku, rule, scope\);/.test(ACTIONS));
const pr = { inScope: true };
vm.createContext(pr);
vm.runInContext("var SRC_ROWS = []; function _srcStillIn(sc){ return inScope; }\n"
  + pick(ACTIONS, /function _srcPatchRow\(sku, rule, scope\)\{[\s\S]*?\n\}/), pr);
pr.SRC_ROWS = [{ sku: "A", rule: { handling_buffer_days: 1 }, own_rule: { handling_buffer_days: 1, min_price: 5 } }];
vm.runInContext("_srcPatchRow('A', {handling_buffer_days: null}, {s: 1})", pr);
check("  back to Default: the row's own number goes, its other own values stay",
      !("handling_buffer_days" in pr.SRC_ROWS[0].own_rule) && pr.SRC_ROWS[0].own_rule.min_price === 5);
vm.runInContext("_srcPatchRow('A', {handling_buffer_days: 2}, {s: 1})", pr);
check("  +2: recorded as its own", pr.SRC_ROWS[0].own_rule.handling_buffer_days === 2);
pr.inScope = false;
vm.runInContext("_srcPatchRow('A', {handling_buffer_days: 9}, {s: 1})", pr);
check("  a reply landing after an account switch paints nothing",
      pr.SRC_ROWS[0].rule.handling_buffer_days === 2 && pr.SRC_ROWS[0].own_rule.handling_buffer_days === 2);
check("Stop tracking acts only on ticked rows that are on screen, like the rest of the bar",
      /async function sourcingUnenrolSelected\(\)\{[\s\S]*?const skus = _srcPicked\(\);/.test(BULK));
check("the typing timer is cancelled on an account switch", /clearTimeout\(SRC_DMAX_T\)/.test(STATE)
      && /if\(!SRC_LAST_J\) return;/.test(MENU));
check("  saved through the same per-SKU route as every bulk setting",
      /_srcBulkRule\(\{handling_buffer_days: v\}/.test(BULK));
check("the ⋯ menu has the account's Extra handling", /sourcingBuffer\(''\)/.test(MENU));
check("pill, menu and bar share ONE dialog",
      (ACT.match(/function _srcBufferModal\(/g) || []).length === 1
      && /_srcBufferModal\(/.test(BULK) && /sourcingBuffer\(sku, btn\)\{[\s\S]*?_srcBufferModal\(/.test(ACT));
check("  offering +0 to +3 and Default",
      /\[0, 1, 2, 3\]/.test(ACT) && /label: "Default \+" \+ dflt/.test(ACT));
check("the bulk dialog opens with nothing chosen and will not save blind",
      /_srcBufferModal\([\s\S]*?\}, true\);/.test(BULK) && /if\(blank && !SRC_BUF_TOUCHED\)/.test(ACT));
check("  where Default is sent as null (follow the account)",
      /onSave\(v === "" \? null : \+v\)/.test(ACT));
check("the chosen segment is lit in place, not rebuilt (keeps the focus)",
      /classList\.toggle\("on"/.test(pick(ACT, /function _srcBufMark\(v\)\{[\s\S]*?\n\}/))
      && !/innerHTML/.test(pick(ACT, /function _srcBufMark\(v\)\{[\s\S]*?\n\}/)));
check("the number box has a real label", /<label for="src_buf"/.test(ACT));
check("the account dialog says how many SKUs follow it, and how many are armed",
      /'Followed by <b>' \+ follow\.length \+ '<\/b> of ' \+ rows\.length[\s\S]*?armed\)/.test(ACT));
check("pill, cell, menu and dialogs read the two facts from ONE helper each",
      /_srcBufOwn\(r\)/.test(DET) && /_srcBufOwn\(r\)/.test(ROW) && /_srcAcctBuffer\(\)/.test(MENU)
      && /_srcAcctBuffer\(\)/.test(BULK) && !/SRC_RULE \|\| \{\}\)\.handling_buffer_days/.test(ACT + BULK + MENU));
check("the single-SKU save goes through the screen's one sourcingSaveRule",
      /async function sourcingBuffer\(sku, btn\)\{[\s\S]*?await sourcingSaveRule\(sku, \{handling_buffer_days: v\}/.test(ACT));
check("the pill says when it is following the default, muted",
      /bufOwn === false \? ' <span class="rp-d" style="font-weight:400">default<\/span>' : ''/.test(DET));

console.log("\n=== the dialog's Save, run for real ===");
const d = { _srcModal: null, toast: (m) => { d.toasted = m; }, uiSeg: () => "", SRC_RULE: {} };
d._srcModal = (title, body, onOk) => { d.onOk = onOk; };
const box = { value: "", validity: { badInput: false } };
d.document = { getElementById: (id) => (id === "src_buf" ? box : null), querySelectorAll: () => [] };
vm.createContext(d);
vm.runInContext("var SRC_BUF_ITEMS = []; var SRC_BUF_TOUCHED = false;\n"
  + pick(ACT, /function _srcBufferModal\([\s\S]*?\n\}/) + "\n"
  + pick(ACT, /function _srcBufMark\(v\)\{[\s\S]*?\n\}/), d);
const save = async (typed, bad, blank, touch) => {
  let sent = "not called"; d.toasted = "";
  vm.runInContext("_srcBufferModal('t', null, 1, null, " + (blank ? "true" : "false") + ")", d);
  box.value = typed; box.validity.badInput = !!bad;
  if (touch) vm.runInContext("_srcBufMark(" + JSON.stringify(typed) + ")", d);
  d.onSaveHook = (v) => { sent = v; return true; };
  vm.runInContext("_srcBufferModal('t', null, 1, function(v){ return onSaveHook(v); }, "
                  + (blank ? "true" : "false") + ")", d);
  if (touch) vm.runInContext("_srcBufMark(" + JSON.stringify(typed) + ")", d);
  const ok = await d.onOk();
  return { ok, sent, toasted: d.toasted };
};
(async () => {
  let r = await save("2", false, false, true);
  check("'2' sends the number 2", r.sent === 2 && r.ok === true);
  r = await save("", false, false, true);
  check("an empty box sends null (Default)", r.sent === null);
  r = await save("31", false, false, true);
  check("31 is refused before anything is sent", r.sent === "not called" && r.ok === false && /0 to 30/.test(r.toasted));
  r = await save("1.5", false, false, true);
  check("1.5 is refused", r.sent === "not called" && r.ok === false);
  r = await save("", true, false, true);
  check("a box the browser cannot read is refused, not taken as Default", r.sent === "not called" && r.ok === false);
  r = await save("", false, true, false);
  check("the bulk dialog refuses a Save with nothing chosen", r.sent === "not called" && r.ok === false);
  r = await save("3", false, true, true);
  check("  and sends +3 once one is", r.sent === 3);
  console.log("\nFAILURES: " + fails);
  process.exit(fails ? 1 : 0);
})();
