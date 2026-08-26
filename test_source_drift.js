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
const CSS = fs.readFileSync("D:/AltaScraper/static/css/repricer.css", "utf8");
const PY = fs.readFileSync("D:/AltaScraper/domain/sourcing.py", "utf8");
const DR = fs.readFileSync("D:/AltaScraper/domain/source_drift.py", "utf8");
const RT = fs.readFileSync("D:/AltaScraper/routes/sourcing_routes.py", "utf8");

console.log("=== the drift is visible without expanding anything ===");
// THE FLAG MOVED, AND THAT IS THE POINT OF THE REDESIGN.
//
// It used to be _driftChip, one of four chips laid across a bordered card. The
// screen is a table now -- one row per SKU, labels in a header rather than
// repeated sixty-seven times -- and the chips were the loudest thing on every
// row whether or not they said anything. So the drift is an 8px mark beside the
// product name, drawn ONLY when the cost has actually moved, with the full
// sentence still in the panel underneath.
//
// What is asserted is unchanged: the gap is visible WITHOUT expanding anything,
// it says which way the cost went, and it explains what that does to a profit
// figure. Only where it is drawn has changed.
truthy("the collapsed row flags a moved cost",
       /flags \+= '<span class="rp-tag"/.test(JS));
truthy("  drawn only when it has actually moved",
       /if\(dft\.delta != null && dft\.delta !== 0\)/.test(JS));
truthy("  which says which way it moved",
       /dft\.delta > 0 \? '&uarr;' : '&darr;'/.test(JS));
truthy("  and explains what it means for profit on hover",
       /profit figures are out\s*'?\s*\+?\s*'?\s*by about/.test(JS));
truthy("a flat cost is not dressed as a warning",
       !/flags \+= .*cost.*unchanged/.test(JS));
// The full explanation is one line and a tooltip now, not a paragraph -- but it
// still has to name BOTH costs and say which way the profit figures are wrong,
// because "cost up 9%" on its own does not tell you a number elsewhere is
// overstated.
truthy("  and the panel still names both costs",
       /Cost was <b>' \+ _smoney\(dr\.cogs\)/.test(JS));
truthy("    and which way the profit figures are out",
       /dr\.delta > 0 \? 'overstated' : 'understated'/.test(JS));
truthy("    with the full explanation on hover",
       /profit figures still subtract the old one/i.test(JS));

console.log("\n=== the price sum is a PICTURE, not a list ===");
// IT USED TO BE A LIST, and the list was the right answer to the question that
// was asked of it then: "price 20.33 = 11.28 cost + 3.05 fee + 3.00 postage"
// is five numbers run together, and a labelled column beat a sentence.
//
// The panel now draws the same five numbers as ONE BAR, segments flexed by
// their own amounts. That answers the question the list answered badly: not
// "what are the parts" but "what SHARE of the price is left". A profit of 2.02
// means nothing until you can see it is a seventh of the bar and the supplier
// is two thirds of it. Keeping the list as well would be the same five figures
// twice, which is what made the panel long enough to need scrolling.
truthy("there is a stacked-bar renderer", /function _stackBar/.test(JS));
truthy("  drawn in the detail panel", /_stackBar\(b\) \+ _metStrip\(r\)/.test(JS));
[[/class="rp-sb-cost"/, "the supplier's cost"],
 [/class="rp-sb-ref"/, "the referral fee"],
 [/class="rp-sb-close"/, "the closing fee"],
 [/class="rp-sb-profit"/, "the profit"],
 [/class="rp-sb-loss"/, "a price that does not cover its cost"]].forEach(function(p){
  truthy("  has a segment for " + p[1], p[0].test(JS));
});
// SEGMENT WIDTHS ARE TRUE TO THE MONEY. A bar whose parts are not proportional
// is a picture that lies, and it would lie about exactly the thing it is drawn
// to show.
truthy("  flexed by the amounts themselves",
       /style="flex:' \+ cost \+ '"/.test(JS)
       && /style="flex:' \+ profit \+ '"/.test(JS));
// ...except the closing fee, which is usually pennies and would be a sliver too
// thin to read. It gets a floor width instead of a share, and the CSS says so.
truthy("  except the closing fee, which gets a floor width",
       /\.rp-sb-close\{flex:0 0 auto;min-width:40px/.test(CSS));
truthy("the fee is still explained as a cut of the PRICE, not of the cost",
       /share of the cash you put in/.test(JS)
       && /share of what the buyer paid/.test(JS));

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
// THE HISTORY IS A LINE NOW, and the two halves of it treat a failed reading
// differently -- on purpose.
//
// The 70x24 sparkline SKIPS an unreadable reading, because there is no honest
// height to draw it at: plotting it at zero would show a line diving to the
// floor, which says "the supplier gave it away" when what happened is that
// nobody could reach the page. A gap in the line is the truth.
//
// The full chart, which the sparkline opens into, LISTS it -- with a dash where
// the amount would be -- because there the date column gives it somewhere to
// be, and a run of failures is exactly why a price can look unchanged for days.
truthy("the sparkline never draws a reading it could not read",
       /p\.landed != null && isFinite\(p\.landed\)/.test(JS));
truthy("  and the full chart still lists it, with no amount",
       /isFinite\(v\) \? _smoney\(v\) : '&mdash;'/.test(JS));
truthy("  because a run of them is why a price looks unchanged",
       /kept rather than filtered out/.test(DR));
truthy("one reading is not a history", /if\(all\.length < 2\) return ''/.test(JS));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
