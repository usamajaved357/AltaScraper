/* A listing's images are reachable from the listing, and "set as main" is ONE rule.
 *
 * What was missing: the app generated images and filed them per SKU, but there
 * was no way to see a listing's images from the listing, choose the main one, or
 * upload your own. They existed and were unreachable.
 *
 * Rule 12: "make this the main image" was implemented FOUR times before this.
 */
const fs = require("fs");

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(60),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");

const lib = read("static/js/listingimages.js");
const autofix = read("static/js/autofix.js");
const miles = read("static/js/miles_template.js");
const settings = read("static/js/settings.js");
const listings = read("static/js/listings.js");
const tpl = read("templates/dashboard.html");

console.log("=== one implementation of 'make this the main image' ===");
check("setMainImage is defined once",
      (lib.match(/^async function setMainImage\(/m) || []).length, 1);
// The ONLY place allowed to POST that key to /edit is the shared helper.
const ALL = {autofix, miles, settings, listings, listingimages: lib};
let writers = [];
for (const [name, src] of Object.entries(ALL)) {
  const hits = (src.match(/key:\s*["']main_product_image_locator["']/g) || []).length;
  if (hits) writers.push(name + ":" + hits);
}
check("only listingimages.js writes that field", writers.join(","), "listingimages:1");

console.log("\n=== the four old copies now call it ===");
check("autofix uploadMainImage calls it",
      /await setMainImage\(sku, pub,/.test(autofix), true);
check("autofix applyGen calls it",
      /await setMainImage\(sku, useUrl,/.test(autofix), true);
check("miles_template calls it",
      /await setMainImage\(sku, url, \{message:'Set as main image'\}\)/.test(miles), true);
check("settings calls it",
      /await setMainImage\(sku, useUrl,/.test(settings), true);

console.log("\n=== the panel exists and is reachable ===");
check("openImageLibrary is defined", /function openImageLibrary\(/.test(lib), true);
check("it reads the existing media library", /\/media\/list\?sku=/.test(lib), true);
check("  rather than a new endpoint", /\/images\/list/.test(lib), false);
check("upload uses the existing upload route", /\/media\/upload/.test(lib), true);
check("push uses the existing push route", /\/listing\/push_image/.test(lib), true);
check("draft rows get a library button",
      /openImageLibrary\('\$\{esc\(r\.sku\)\}'/.test(listings), true);
check("live rows get one too",
      /openImageLibrary\('\$\{esc\(it\.sku\|\|''\)\}', true\)/.test(listings), true);
check("the file is loaded by the page",
      /\/static\/js\/listingimages\.js\?v=/.test(tpl), true);

console.log("\n=== drafts stage, live pushes ===");
check("Push to Amazon is only offered for a live listing",
      /if\(IMGLIB\.live\)\{/.test(lib), true);
check("  and it confirms nothing is sent by merely choosing",
      /until you Submit/.test(lib), true);
check("the panel prefers a PUBLIC url for uploads",
      /drive_direct_url/.test(lib), true);
check("  and says so when there is none",
      /reachable by Amazon/.test(lib), true);

console.log("\n=== the live image pull stops lying about what it fetched ===");
const live = read("routes/live_routes.py");
// Match the STATEMENT, not the word. The comment above the fix quotes the old
// code on purpose, and an assertion that trips over its own explanation is a
// worse test than none.
check("the silent 40 cap is gone", /for sku in todo\[:40\]/.test(live), false);
check("  the loop now runs over a named batch", /for sku in _did:/.test(live), true);
check("the batch size is named", /_IMG_BATCH/.test(live), true);
check("  and configurable", /ALTA_IMG_BATCH/.test(live), true);
check("unreached SKUs are reported", /"pending": _pending_out/.test(live), true);
check("refused SKUs are reported", /"failed": _failed/.test(live), true);
check("  instead of being swallowed",
      /except Exception:\n {24}continue/.test(live), false);
check("the browser tells you the count",
      /Amazon would not return \(usually rate limiting/.test(miles), true);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
