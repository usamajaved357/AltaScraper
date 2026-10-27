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
      STATE = read("screenstate.js");
let fails = 0;
const check = (label, ok) => { if (!ok) fails++; console.log("  %s %s", label.padEnd(66), ok ? "OK" : "FAIL"); };
const pick = (src, re) => { const m = src.match(re); if (!m) { fails++; console.log("  could not find " + re); } return m ? m[0] : ""; };

const s = { _sesc: (x) => String(x).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;") };
vm.createContext(s);
vm.runInContext("var SRC_ROWS = []; var SRC_FILTER = ''; var SRC_DFILT = {by: '', max: 3};\n"
  + pick(MENU, /function _srcVisible\(\)\{[\s\S]*?\n\}/) + "\n"
  + pick(MENU, /function _srcDeliveryDays\(r, by\)\{[\s\S]*?\n\}/) + "\n"
  + pick(ROW, /function _rpDelivery\(r\)\{[\s\S]*?\n\}/), s);

// Three SKUs, postage 2 days:
//   FAST  eBay 1d -> handling 0 + 1 default extra = 1 -> buyer 3
//   MID   eBay 3d -> handling 1 + 2 own extra     = 3 -> buyer 5
//   SLOW  eBay 6d -> handling 4                   = 4 -> buyer 6
//   NONE  no delivery date at all
const row = (sku, eb, lead, buf, own, mode, action) => ({
  sku, mode: mode || "dry_run", own_rule: own ? { handling_buffer_days: buf } : {},
  current: { lead_days: lead },
  decision: { action: action || "nothing", breakdown: eb == null ? {} : {
    supplier_dispatch_days: eb, lead_days: lead, buffer_days: buf,
    shipping_policy_days: 2, buyer_days: lead + 2 } } });
const ROWS = [row("FAST", 1, 1, 1, false, "live"), row("MID", 3, 3, 2, true),
              row("SLOW", 6, 4, 0, false, "live", "update"), row("NONE", null, null, 0, false)];
const shown = (by, max, card) => {
  s.SRC_ROWS = ROWS; s.SRC_DFILT = { by, max }; s.SRC_FILTER = card || "";
  return vm.runInContext("_srcVisible().map(function(r){ return r.sku; }).join(',')", s);
};

console.log("=== the filter ===");
check("off: every row", shown("", 3) === "FAST,MID,SLOW,NONE");
check("to the buyer in 5 days or less: FAST and MID", shown("total", 5) === "FAST,MID");
check("handling 3 days or less: FAST and MID", shown("handling", 3) === "FAST,MID");
check("handling 1 day or less: FAST only", shown("handling", 1) === "FAST");
check("eBay 3 days or less: FAST and MID", shown("ebay", 3) === "FAST,MID");
check("a SKU with no delivery date is never counted as short", shown("total", 60).indexOf("NONE") < 0);
check("it combines with the cards: armed AND to the buyer in 6 or less",
      shown("total", 6, "armed") === "FAST,SLOW");
check("  and with Would change", shown("handling", 9, "update") === "SLOW");
check("'Tracked' (the empty card) clears it as well",
      /function sourcingFilter\(key\)\{[\s\S]*?if\(!key\) SRC_DFILT\.by = "";/.test(MENU));
check("changing it clears the ticks, like a card does",
      /function _srcDeliveryRedraw\(\)\{\s*SRC_SEL = new Set\(\);/.test(MENU));
check("ONE control, from the shared segmented helper",
      /uiSeg\(SRC_DFILT_BY, SRC_DFILT\.by, "sourcingDeliveryBy"\)/.test(MENU));
check("  drawn under the stat cards", /_statCards\(j\) \+ _srcDeliveryBar\(\)/.test(MAIN));
check("an account switch turns it off", /SRC_DFILT\.by = ""/.test(STATE));

console.log("\n=== the Delivery cell: numbers, not sentences ===");
const cell = (r) => vm.runInContext("_rpDelivery(" + JSON.stringify(r) + ")", s);
const fast = cell(ROWS[0]), mid = cell(ROWS[1]), slow = cell(ROWS[2]), none = cell(ROWS[3]);
check("the total to the buyer leads", /<b>3d<\/b>/.test(fast) && /<b>5d<\/b>/.test(mid));
check("  with its handling + postage beside it", /\(1\+2\)/.test(fast) && /\(3\+2\)/.test(mid));
check("then the supplier's days", /eBay 1d/.test(fast) && /eBay 3d/.test(mid));
check("an own +2 is gold", /<b class="rp-y">\+2<\/b>/.test(mid));
check("an inherited +1 is plain", /<b class="">\+1<\/b>/.test(fast));
check("no extra days, no +0 clutter", !/\+0/.test(slow));
check("the sum is in the tooltip", /handling 3d \(incl\. \+2 extra, this SKU.s own\) \+ postage 2d = 5d/.test(mid));
check("  and says when the extra is the account's", /account default/.test(fast));
check("no delivery date: a dash, never a 0", /&mdash;/.test(none) && !/0d/.test(none));
check("the column has a heading", />Delivery<\/th>/.test(MAIN));
check("the open panel still spans every column", /colspan="11"/.test(ROW) && !/colspan="10"/.test(ROW));

console.log("\n=== setting the extra days ===");
check("the selection bar has Extra handling", /onclick="sourcingBulkBuffer\(\)"/.test(BULK));
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
      /onSave\(v === "" \? null : v\)/.test(ACT));
check("the pill says when it is following the default", /bufOwn \? '' : ' <span class="rp-off">default<\/span>'/.test(DET));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
