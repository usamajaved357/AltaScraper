/* The Repricer has to show WHAT A UNIT COSTS NOW, not only what it cost once.
 *
 * "many items cogs are changed, how will it work? i want to see the change in
 *  the pricing of the source"
 *
 * Two numbers, neither wrong, that never talk to each other:
 *
 *   COGS          what the generator baked into the SKU name (or a manual
 *                 override). Backward-looking. Every profit figure subtracts it.
 *   landed cost   what the supplier charges right now. Forward-looking. The
 *                 repricer prices from it and never consults COGS.
 *
 * They start equal and drift apart silently. What is checked here is that the
 * gap is DRAWN -- on the collapsed row, so you meet it without going looking --
 * and that the price sum is laid out in labelled parts rather than as one dense
 * sentence, which is the form the user could not read.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const JS = fs.readFileSync("D:/AltaScraper/static/js/sourcing.js", "utf8");
const PY = fs.readFileSync("D:/AltaScraper/domain/sourcing.py", "utf8");
const DR = fs.readFileSync("D:/AltaScraper/domain/source_drift.py", "utf8");
const RT = fs.readFileSync("D:/AltaScraper/routes/sourcing_routes.py", "utf8");

console.log("=== the drift is visible without expanding anything ===");
truthy("the collapsed row carries a cost chip", /_driftChip\(r\.drift\)/.test(JS));
truthy("  which says which way it moved", /cost '\+\(flat \? 'unchanged' : \(worse\?'up':'down'\)\)/.test(JS));
truthy("  and explains what it means for profit on hover",
       /profit is overstated by/.test(JS));
truthy("a flat cost is not dressed as a warning",
       /const col = flat \? '' :/.test(JS));

console.log("\n=== the price sum is a list, not a sentence ===");
truthy("there is a breakdown renderer", /function _priceBreakdown/.test(JS));
truthy("  drawn in the detail panel", /_priceBreakdown\(d\.breakdown, cur\)/.test(JS));
[["What the supplier charges", "the supplier's price"],
 ["So one unit costs you", "the landed cost"],
 ["Amazon's cut", "the referral fee"],
 ["Your postage to the buyer", "the shipping label"],
 ["Set aside for ads", "the ads allowance"],
 ["Profit left over", "the profit"],
 ["Price it should sell at", "the total"]].forEach(function(p){
  truthy("  names " + p[1], JS.indexOf(p[0]) > 0);
});
truthy("the fee is explained as a cut of the PRICE, not of the cost",
       /% of the selling price, not of the cost/.test(JS));

console.log("\n=== the numbers come from the decision, not from its prose ===");
// Reading them back out of the reason sentence would be deriving meaning from
// human-readable text, and would break the moment the wording improved.
truthy("the decision carries a structured breakdown", /out\["breakdown"\] = \{/.test(PY));
["supplier_price", "cost", "fee", "fee_rate", "postage_label", "ads", "profit",
 "price", "lead_days", "buffer_days"].forEach(function(k){
  truthy("  including " + k, new RegExp('"' + k + '":').test(PY));
});
truthy("and the sentence is still written for the log",
       /this line IS the audit trail/.test(PY));
truthy("  the UI does not parse that sentence",
       !/reason\.(match|split|replace)/.test(JS));

console.log("\n=== one cost resolver, one landed-cost function ===");
// Re-deriving either here would be a second answer to a question that already
// has one (CLAUDE.md Rule 12).
truthy("cost comes from domain/cogs.py", /from domain import cogs as _cogs/.test(DR));
truthy("  via resolve(), so a manual override still wins",
       /_cogs\.resolve\(overrides, workspace_id, sku\)/.test(DR));
truthy("landed cost comes from domain/sourcing.py",
       /_sourcing\.landed_cost\(c\)/.test(DR));
truthy("  and is not recomputed as price+shipping anywhere here",
       !/price.*\+.*shipping/.test(DR.replace(/#.*/g, "").replace(/"""[\s\S]*?"""/g, "")));
truthy("unknown stays unknown rather than becoming zero",
       /if cost is None or landed is None or cost <= 0:/.test(DR));

console.log("\n=== the route serves it, and the overrides reach it ===");
truthy("rows carry their drift", /"drift": _drift\.for_sku\(/.test(RT));
truthy("  built with the shared override dict", /_COGS_OVERRIDE, d\["workspace_id"\]/.test(RT));
truthy("  which is optional so the tests can register without it",
       /_COGS_OVERRIDE=None/.test(RT));
truthy("each source carries its readings", /"history": _drift\.price_history/.test(RT));

console.log("\n=== history shows failures rather than hiding them ===");
truthy("a reading that could not be read is still listed",
       /could not read/.test(JS));
truthy("  because a run of them is why a price looks unchanged",
       /kept rather than filtered out/.test(DR));
truthy("one reading is not a history", /hist\.length<2/.test(JS));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
