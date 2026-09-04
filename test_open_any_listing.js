/* Clicking a listing -- any listing -- opens it.
 *
 *     "when i click on many listings on live on amazon page inside all
 *      listings page, a message appears the listing is not on this screen, i
 *      should be able to open all the listings"
 *
 * The cause: two functions decided the same thing. openLiveListing() asked
 * whether this app holds a draft and sent the rest to the live optimiser;
 * openListing() went straight to pdpOpen(), which is built from a row in ROWS
 * and refuses when there is none. The live TILE used the first, the DETAILED
 * view's row used the second, so the same listing opened from one view and
 * refused from another.
 *
 * Measured on nestwell_goods: 18 of the 62 SKUs Amazon reports have no row in
 * this app -- which is why it was "many listings", not one.
 */
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
let fails = 0;
function ok(label, cond) {
  if (!cond) fails++;
  console.log("  " + (cond ? "OK  " : "FAIL") + "  " + label);
}

function read(...p) {
  return fs.readFileSync(path.join(ROOT, ...p), "utf8");
}
/* Comments stripped: a test that passes on a note ABOUT the fix has caught
 * nothing. This has happened here often enough to be worth the helper. */
function code(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
}

const LIST = code(read("static", "js", "listings.js"));
const PDP = code(read("static", "js", "pdp.js"));
const DET = code(read("static", "js", "listrow_detailed.js"));
const MIL = code(read("static", "js", "miles_template.js"));

console.log("\n== one function decides where a listing opens ==");
// IT NO LONGER ASKS. CLAUDE_CODE_PROMPT_amazon_listings.md:
//     "ALL listings open the PDP overlay regardless of origin. A listing
//      synced from Amazon is still a listing you manage."
// The draft check was the right condition for a page that could only be built
// from a row. pdpOpen draws one from Amazon's own catalogue and attributes now
// (pdpCatalogueRow), so there is nothing left for the branch to protect.
// See test_every_listing_opens.py.
ok("openListing goes straight to the product page",
   /function openListing\(sku, asin\)\{[\s\S]{0,200}?pdpOpen\(s\); return;/.test(LIST));
ok("  and no longer routes anything to the optimize modal",
   !/function openListing\(sku, asin\)\{[\s\S]{0,400}?optimizeLive\(/.test(LIST));
ok("openLiveListing now decides nothing of its own",
   /function openLiveListing\(asin, sku\)\{\s*openListing\(sku, asin\);\s*\}/.test(LIST));

console.log("\n== no route reaches the product page with a SKU it cannot draw ==");
// Every caller goes through openListing / openLiveListing. The two exceptions
// are inside the product page itself and inside the drawer, where the row is
// in ROWS by definition.
function count(s, re) { return (s.match(re) || []).length; }
// These two files draw the rows the complaint was about. Neither may call the
// product page directly any more -- that is what left a catalogue-only listing
// unopenable from the detailed view while the tile opened it fine.
ok("the detailed view never calls pdpOpen itself", count(DET, /pdpOpen\(/g) === 0);
ok("  nor do the live tiles", count(MIL, /pdpOpen\(/g) === 0);
// In listings.js it appears four times and every one is accounted for:
//
//   twice inside openListing   after the draft check, and as its last line
//   once on the drawer's       "open full screen" button, where the row is in
//     header button            ROWS by definition -- the drawer is showing it
//   once at the top of         the redirect that makes the side drawer
//     openDrawer               unreachable -- see test_one_detail_view.js
//
// The fourth is what closes the last route to the old panel, so this count
// going UP is not a regression by itself; a NEW one outside those four is.
ok("in listings.js it is only inside openListing, openDrawer and the button",
   count(LIST, /pdpOpen\(/g) === 3);
const inOpen = LIST.slice(LIST.indexOf("function openListing(sku, asin)"));
// No guard any more -- every listing is drawable.
ok("  and it is unconditional",
   /if\(typeof pdpOpen === "function"\)\{ pdpOpen\(s\); return; \}/.test(inOpen));

console.log("\n== the ASIN handed to the optimiser is OURS, never the competitor's ==");
// CLAUDE.md Rule 1 and the two-ASIN problem: on a row this app generated,
// r.asin is the COMPETITOR reference embedded in the SKU. Opening the live
// optimiser on it would pull down somebody else's listing.
ok("it comes from Amazon's own catalogue", /function liveAsinFor\(sku\)/.test(LIST));
ok("  by SKU, not by r.asin",
   /liveAsinFor[\s\S]{0,320}LIVE_ITEMS\.find\(x => String\(x && x\.sku\) === s\)/.test(LIST));
ok("  and an unknown one is empty, not guessed",
   /function liveAsinFor[\s\S]{0,300}return ""/.test(LIST));

console.log("\n== the last-line message says something true ==");
ok("it names the SKU and what to do about it",
   /holds no draft of/.test(PDP) && /Press Sync/.test(PDP));
ok("  and no longer says 'not on this screen'",
   !/not on this screen\."\)/.test(PDP));

console.log("\n" + (fails ? fails + " FAILED" : "0 failed"));
process.exit(fails ? 1 : 0);
