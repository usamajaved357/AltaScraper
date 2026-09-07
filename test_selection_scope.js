/* A bulk action acted on more listings than the tile said.
 *
 *     "i selected 36 listings by going to first filter and select all and then
 *      set the handling time by using the bulk option as 2 day handling time
 *      and got this message why"
 *
 * 46 went, not 36. SELECTED survives a change of tab and of filter -- on
 * purpose, so a selection can be built across pages -- and selectAllVisible
 * ADDS to it rather than replacing it. Ten rows ticked in an earlier view were
 * still in there.
 *
 * The reply then measured everything against a total he had never been shown:
 *
 *     Saved: 13    +  33 with no listing row  = 46
 *     Pushed: 36   +  10 not live yet         = 46
 *
 * Neither pair matched the 36 on the tile he had just used, so both looked
 * wrong. They were right; the total was missing.
 *
 * MEASURED AFTERWARDS: all 36 live listings on nestwell_goods hold
 * lead_time_to_ship_max_days = 2 at Amazon. The push did exactly what he asked.
 */
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
let fails = [];

function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(68) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

const R = f => fs.readFileSync(path.join(HERE, "static", "js", f), "utf8");
const L = R("listings.js");
const H = R("handling.js");
const M = R("miles_template.js");
const G = R("gtin.js");

console.log("=== the selection can be counted against what is on screen ===");
truthy("there is a count of what is off-screen",
  L.indexOf("function selectedOffScreen(") >= 0);
const _off = L.split("function selectedOffScreen(")[1].split("\n/*")[0];
truthy("  it asks what is actually drawn", _off.indexOf("visibleSelectableSkus()") >= 0);
// NOTHING DRAWN YET is not "everything is off screen" -- during a load that
// would claim the whole selection was elsewhere.
truthy("  and says nothing when nothing is drawn yet",
  _off.indexOf("if(!here.size) return 0;") >= 0);
// The selection is NOT narrowed. Carrying one across pages is the point of it.
falsy("the selection is not silently cleared on a view change",
  /SELECTED\.clear\(\)/.test(L.split("function selectAllVisible(")[1].split("}")[0] || ""));

console.log("\n=== the bar says so ===");
const _bar = L.split("function updateSelBar(")[1].split("\nfunction ")[0];
truthy("the count appears beside 'N selected'",
  _bar.indexOf("not in this view") >= 0);
truthy("  with the reason on hover", _bar.indexOf("cnt.title") >= 0);

console.log("\n=== and every bulk action says it before acting ===");
// ONE SENTENCE, NOT FOUR. A copy per caller is how one of them ends up without
// it -- and the two that cannot be taken back are Delete and the exemption.
truthy("there is one shared sentence",
  L.indexOf("function selectionScopeNote(") >= 0);
truthy("  it is empty when the selection is all on screen",
  L.split("function selectionScopeNote(")[1].indexOf('if(!off) return "";') >= 0);
truthy("handling asks for it", H.indexOf("selectionScopeNote(") >= 0);
truthy("delete asks for it", M.indexOf("selectionScopeNote(") >= 0);
truthy("  the GTIN exemption too", G.indexOf("selectionScopeNote(") >= 0);
// Each names what is about to happen, so the sentence is not generic.
truthy("  and each names its own action",
  H.indexOf('selectionScopeNote("sending this to Amazon")') >= 0
  && M.indexOf('selectionScopeNote("deleting anything")') >= 0
  && G.indexOf('selectionScopeNote("declaring this")') >= 0);

console.log("\n=== the reply states the total it acted on ===");
truthy("the count comes first", H.indexOf("on ${skus.length} listing(s).") >= 0);
// Two questions, two headings: what Amazon now holds, and what this app
// recorded. They are different numbers for a real reason -- 33 of those
// listings have no row here at all -- and stacking them as one list is what
// made "Saved: 13" read as a failure.
truthy("Amazon and our own copy are separated",
  H.indexOf("On Amazon — this is the number buyers see") >= 0
  && H.indexOf("Recorded here — this app's own copy") >= 0);
truthy("  a refusal sits with the push, not with the save",
  H.indexOf("Amazon refused: ${realFail}") >= 0);
const _amzBlock = H.split("On Amazon — this is the number buyers see")[1]
  .split("Recorded here")[0];
truthy("    which means it is above the save line",
  _amzBlock.indexOf("Amazon refused") >= 0);

console.log("\nFAILURES: " + fails.length);
fails.forEach(f => console.log("  - " + f));
process.exit(fails.length ? 1 : 0);
