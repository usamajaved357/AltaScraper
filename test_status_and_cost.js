/* Four things a row said that the tile beside it contradicted.
 *
 *     "we still record SUBMITTED / Accepted — publishing"
 *     "one is 3 in 1 floor scrub which shows only live but is displayed under
 *      this filter"
 *     "the 3rd filter shows no cost set 23 listings, but the costs are set in
 *      this view"
 *     "for many listings i dont have an option to put the cogs"
 *
 * All four are the same shape: two places answering one question from two
 * different sources, and neither saying which it read.
 *
 * MEASURED on nestwell_goods, 8 Sep 2026, asking Amazon per SKU:
 *   11.59_3Days_B0DNJH3CRX  BUYABLE, qty 10 -- "submit a compliant image to
 *                           lift the suppression"
 *   39.99_3Days_B0G14RGRDC  BUYABLE, qty 1  -- same
 *   9.18_3Days_B0C6XTNXL8   BUYABLE, qty 2  -- MAIN image has text/logo/
 *                           watermark  <- the floor scrub
 *   14.99_2Days_B09V19CTQ5  DISCOVERABLE, qty 0
 * So all four the tile counts are real. What was wrong is that three of them
 * said nothing on their own row.
 */
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
let fails = [];

function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(66) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

const R = f => fs.readFileSync(path.join(HERE, "static", "js", f), "utf8");
const COGS = R("cogs.js");
const EDIT = R("listrow_edit.js");
const DET = R("listrow_detailed.js");
const LS = R("liststatus.js");
const AV = R("autoverify.js");

console.log("=== the cost shown is the cost the app actually has ===");
// The tile counts what the SERVER resolves; the rows were printing a number
// read out of the SKU name, which the server stopped doing when the owner said
// "lets remove the cogs from sku things entirely". 1 row of 86 has a resolved
// cost; the browser printed one on 85.
const _co = COGS.split("function cogsOf(")[1].split("\nfunction ")[0];
falsy("cogsOf no longer reads a cost out of the SKU name",
  /sku\.split\("_"\)\[0\]/.test(_co));
truthy("  a SKU with no cost says so", COGS.indexOf('">set</span>') >= 0
  || COGS.indexOf(">set<") >= 0);
truthy("  and the reason is written down, not just deleted",
  COGS.indexOf("THE SKU-NAME FALLBACK IS GONE") >= 0);

console.log("\n=== and it can be typed, even with no draft row ===");
// A cost is not a column on `listings` -- it is in the COGS store keyed by
// (account, sku), and /cogs/set takes nothing else. 33 of 40 live listings on
// this account have no row here, so the guard turned the control off on exactly
// the listings that needed it.
truthy("the two questions are separate flags now",
  EDIT.indexOf("needsRow: false") >= 0 && EDIT.indexOf("live: false, needsRow: true") >= 0);
truthy("  cost needs no row", /cost:\s*\{[^}]*needsRow:\s*false/.test(EDIT));
truthy("  stock still needs none either", /qty:\s*\{[^}]*needsRow:\s*false/.test(EDIT));
truthy("  price and handling still do",
  /price:\s*\{[^}]*needsRow:\s*true/.test(EDIT)
  && /handling:\s*\{[^}]*needsRow:\s*true/.test(EDIT));
truthy("  the guard reads the new flag", EDIT.indexOf("_f.needsRow !== false") >= 0);
// ...and `live` still means what it always meant, or the save bar starts
// claiming a cost goes to Amazon.
truthy("cost still does not count as reaching Amazon",
  /cost:\s*\{[^}]*live:\s*false/.test(EDIT));
truthy("  which is what the bar wording reads",
  EDIT.indexOf("LR_FIELDS[f].live") >= 0);

console.log("\n=== the row says what the tile counted ===");
// `stored` is THIS APP'S word, and on a row we hold a draft of it is LIVE --
// never SUPPRESSED, because the app does not write Amazon's vocabulary. So the
// badge could only appear on catalogue-only rows while the tile counted every
// row. Same pairing the tile uses, so they cannot disagree.
truthy("the badge reads the catalogue item", DET.indexOf("liveItemForRow(r)") >= 0);
const _ns = DET.split("const _notShowing")[0].slice(-1400);
truthy("  through the shared row-to-item pairing", _ns.indexOf("liveItemForRow") >= 0);
truthy("  falling back to our own word for a catalogue-only row",
  _ns.indexOf("stored") >= 0);
// The three words must stay the same three the filter tests, or the tile and
// the badge drift apart again.
truthy("the same three words the tile tests",
  DET.indexOf('["SUPPRESSED", "INACTIVE", "INCOMPLETE"]') >= 0);
const LIST = R("listings.js");
truthy("  and the filter still tests them",
  LIST.indexOf('s.indexOf("inactive") >= 0') >= 0
  && LIST.indexOf('s.indexOf("suppress") >= 0') >= 0
  && LIST.indexOf('s.indexOf("incomplete") >= 0') >= 0);

console.log("\n=== a record behind Amazon gets corrected ===");
// lsIsWaitingOnAmazon is "SUBMITTED and NOT in the catalogue", so a listing
// stopped being chased at the exact moment Amazon confirmed it -- the moment
// there was finally something to write.
truthy("there is a name for it", LS.indexOf("function lsRecordIsBehind(") >= 0);
truthy("  it is our own words only",
  LS.indexOf("LS_PRE_LIVE") >= 0 && LS.indexOf('"PENDING"') >= 0);
truthy("  and it means Amazon HAS it", /lsInLiveCatalogue\(r\)/.test(
  LS.split("function lsRecordIsBehind(")[1].split("}")[0]));
truthy("the verify sweep now includes them", AV.indexOf("lsRecordIsBehind(r)") >= 0);
// The run itself is unchanged: it still promotes only on Amazon's own BUYABLE.
const GEN = fs.readFileSync(path.join(HERE, "amazon_listing_generator.py"), "utf8");
truthy("  and promotion is still Amazon's BUYABLE, not our guess",
  GEN.indexOf('if "BUYABLE" in _st_up:') >= 0);
// The waiting group is unchanged -- it is a different question and a different
// heading on screen.
truthy("the 'waiting on Amazon' group still means what it did",
  LS.indexOf("return lsSaysSubmitted(r) && !lsInLiveCatalogue(r);") >= 0);

console.log("\nFAILURES: " + fails.length);
fails.forEach(f => console.log("  - " + f));
process.exit(fails.length ? 1 : 0);
