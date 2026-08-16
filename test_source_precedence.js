/* eBay is the truth. The competitor is a different seller's similar product.
 *
 * "the content writer should consider the ebay as the truth for writing content,
 *  dont take anything from anywhere else including amazon if it opposes the
 *  information which is available on ebay"
 *
 * The code had said so since it was written -- "eBay is the SOURCE OF TRUTH for
 * content (title, specs, images)" -- but the PROMPT said the opposite:
 *
 *   "EBAY CROSS-REFERENCE (same product listed on eBay UK -- use to validate and
 *    fill attribute gaps from Amazon competitor data, but Amazon data takes
 *    precedence where they conflict)"
 *
 * plus "Only state specs confirmed in competitor data". A comment does not reach
 * the model; the prompt does. So where the two disagreed, the model was told to
 * believe the competitor -- and did.
 *
 * Caught on a real listing: eBay said "1x Hammock, 1x Buckle, 1x Connecting
 * strap, 1x Extension strap" and the draft claimed "2 x locking carabiners".
 * That is hardware the buyer never receives, described by us, in writing.
 *
 * Checked as text because a prompt IS text: the only thing that decides this is
 * what the model is told, so what it is told is what has to be asserted.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(68) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const GEN = fs.readFileSync("D:/AltaScraper/amazon_listing_generator.py", "utf8");

console.log("=== the prompt no longer ranks the competitor above the source ===");
truthy("the old precedence sentence is gone",
       !/Amazon data takes\s*"?\s*\n?\s*"?precedence where they conflict/.test(GEN));
truthy("  and is not written anywhere else either",
       !/takes precedence where they conflict/.test(GEN));
truthy("the source listing is named as what we actually buy",
       /WHAT WE ARE ACTUALLY BUYING AND SHIPPING -- THE SOURCE LISTING ON EBAY/.test(GEN));
truthy("  and wins every conflict, in as many words",
       /THIS WINS, every time, with/.test(GEN) && /no exceptions/.test(GEN));
truthy("  with the competitor allowed only to fill a silence",
       /may only fill a gap this is silent on/.test(GEN));

console.log("\n=== package contents are not pooled from two listings ===");
// The specific failure. A competitor listing that includes more parts must not
// add parts to ours, and must not raise a quantity.
truthy("adding an item to the contents is forbidden",
       /do not add an item/.test(GEN));
truthy("  and so is inflating a quantity",
       /do not increase a quantity/.test(GEN));
truthy("contents come from the source alone",
       /Package contents, part quantities and what is 'included' come from the/.test(GEN));
truthy("  and one means one", /If it says one of something, say one/.test(GEN));

console.log("\n=== the accuracy rule points at the right listing ===");
truthy("a spec seen only at the competitor is not a fact about our item",
       /A spec that appears ONLY in competitor data is not a fact about/.test(GEN));
truthy("  the old wording is gone",
       !/Only state specs confirmed in competitor data/.test(GEN));

console.log("\n=== the competitor is labelled for what it is ===");
truthy("the title says it is another seller's product",
       /a DIFFERENT seller's similar product -- reference only/.test(GEN));
truthy("the specs say they are outranked",
       /outranked by the source listing/.test(GEN));
// Rule 1: the ASIN is a competitor reference, never our listing.
truthy("and the file still says why that matters",
       /CLAUDE\.md Rule 1/.test(GEN));

console.log("\n=== the rule is universal, not written for one product ===");
// "keep in mind that the rules of image gen are universal for all type of items
//  we are not selling limited categories or limited items"
["hammock", "carabiner", "yoga", "swing"].forEach(function(w){
  const near = new RegExp("(WHAT WE ARE ACTUALLY BUYING[\\s\\S]{0,1400})", "");
  const block = (GEN.match(near) || ["", ""])[1];
  truthy("  the prompt block does not mention " + w,
         block.toLowerCase().indexOf(w) < 0);
});

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
