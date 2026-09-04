/* One table, one card -- and no quiet seventh copy.
 *
 *     "the sizing and the theme of the repricer page is nice, i want this to
 *      be applied on all listings page and the catalog page"
 *
 * Making the three screens match was the easy half. The hard half is that they
 * STAY matched: the app had grown SIX definitions of two ideas, one at a time,
 * each perfectly reasonable on the day it was written --
 *
 *     tables   .lt (Listings)   .stk-table (Catalog, Stock, PPC)   .rp-tbl
 *     cards    .metric (Listings)   .ui-stat (most screens)   .rp-mc
 *
 * -- plus a seventh in JavaScript, where catalogpage.js hand-wrote the same
 * three divs pageui.js already emits. Nothing here checks that the look is
 * NICE; that is a judgement and it belongs to him. What it checks is that
 * there is only ONE of it, which is the thing a future edit can quietly undo.
 */
const fs = require("fs");
const R = "D:/AltaScraper/";
let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(62),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const read = (p) => fs.readFileSync(R + p, "utf8");

const tpl = read("templates/dashboard.html");
const shared = read("static/css/datatable.css");
const dash = read("static/css/dashboard.css");
const repr = read("static/css/repricer.css");
const mob = read("static/css/mobile.css");
const pageui = read("static/js/pageui.js");
const listings = read("static/js/listings.js");
const catalog = read("static/js/catalogpage.js");
const motion = read("static/js/motion.js");

console.log("=== the shared sheet is actually served ===");
check("datatable.css is linked", /href="\/static\/css\/datatable\.css/.test(tpl), true);
// Load order decides who wins a tie. It must come after dashboard.css, whose
// rules it replaces, and before repricer.css, which still overrides a few
// things for the price screen alone.
const at = (s) => tpl.indexOf(s);
check("  after dashboard.css, whose rules it takes over",
      at("css/datatable.css") > at("css/dashboard.css"), true);
check("  before repricer.css, which still overrides a little",
      at("css/datatable.css") < at("css/repricer.css"), true);

console.log("\n=== one table, named by every screen that draws one ===");
// The rule lists all four class names rather than renaming anything: listings.js
// alone is 160KB and a rename across it is surface with no upside.
for (const cls of [".rp-tbl th", ".lt th", ".stk-table th", ".dt-tbl th"]) {
  check(cls + " gets the shared header", shared.indexOf(cls) >= 0, true);
}
check("  headers are 9px uppercase", /font-size:9px[\s\S]{0,120}text-transform:uppercase/.test(shared), true);
check("  cells are 13px on 6px padding",
      /padding:6px 5px[\s\S]{0,200}font-size:13px/.test(shared), true);

console.log("\n=== and nowhere else defines one ===");
// The old blocks were REMOVED, not merely outranked. A rule that still exists
// but loses is the next person's evidence that two definitions are fine.
check("dashboard.css no longer sizes .lt headers",
      /\.lt th\{[^}]*font-size:11px/.test(dash), false);
check("dashboard.css no longer sizes .stk-table",
      /\.stk-table\{\s*width:100%/.test(dash), false);
check("repricer.css no longer defines the table",
      /\.rp-tbl th\{/.test(repr), false);

console.log("\n=== one card ===");
check("the shared sheet defines it", /\.rp-mc, \.ui-stat, \.dt-mc\{/.test(shared), true);
check("dashboard.css no longer defines .ui-stat",
      /\.ui-stat\{background:rgb/.test(dash), false);
check("repricer.css no longer defines .rp-mc",
      /\.rp-mc\{background:/.test(repr), false);
// .metric was Listings' own card. It is gone, not just unused: leaving the CSS
// behind is how the app got to six definitions in the first place.
check(".metric is retired from dashboard.css",
      /\.metric\{background:var\(--panel\)/.test(dash), false);
check("  and nothing draws it any more", /class="metric[" ]/.test(listings), false);
check("  its dead grid is gone from dashboard.css", /\.metricgrid\{/.test(dash), false);
// Matched as a SELECTOR -- followed by a brace or a comma -- not as the word.
// The note left behind explaining why it went says "metricgrid", and a test
// that cannot tell an explanation from a rule would fail on the comment that
// exists to prevent exactly this being re-added.
check("  and from mobile.css", /\.metricgrid\s*[{,]/.test(mob), false);

console.log("\n=== the thumbnail rule sizes thumbnails and nothing else ===");
//     "what is this where are the pictures"
//
// .pii-img reads like a thumbnail class and is not: it is the privacy-blur
// marker, put on anything holding a customer-identifying picture -- including
// the card view's 180px photo area. Sizing it 36px square shrank every draft
// card's photo to a badge in the corner while the live cards beside them, in
// the same grid row, kept theirs. Its only legitimate rule is the blur.
check(".pii-img is not sized as a thumbnail",
      /\.pii-img[^{}]*\{[^}]*width:36px/.test(shared), false);
check("  its blur rule is untouched in dashboard.css",
      /body\.privacy-on \.pii-img img/.test(dash), true);
// The card's photo area must stay the size it was. Nothing in the shared sheet
// may reach it.
check("nothing in the shared sheet sizes .tileimg",
      /\.tileimg[^{}]*\{/.test(shared), false);
// REWRITTEN, NOT DELETED. This asserted `height:180px`, which was right until
// the card-view pass: a fixed pixel height on a column whose WIDTH follows the
// window meant the picture area was a different shape on a wide screen from a
// narrow one. It is a 1:1 ratio now, so every card's photo is the same shape at
// every size. The POINT of the check is unchanged -- dashboard.css owns the
// size of the card's photo area, and the shared sheet may not reach it.
check("  and dashboard.css still owns its shape",
      /\.tileimg\{[^}]*aspect-ratio:1\/1/.test(dash), true);

console.log("\n=== the number comes before the label ===");
// This is the half of the difference that is structural rather than a size: a
// row of cards should read as a row of NUMBERS, not a row of words.
const stat = pageui.slice(pageui.indexOf("function uiStat("));
check("uiStat emits the value first",
      stat.indexOf("ui-stat-v") < stat.indexOf('<div class="ui-stat-k"'), true);

console.log("\n=== one builder, not one per screen ===");
check("Listings calls the shared uiStat", /uiStat\(\{/.test(listings), true);
check("  and no longer writes its own tile markup",
      /<p class="n">/.test(listings), false);
check("Catalog calls the shared uiStats", /uiStats\(/.test(catalog), true);
check("  and no longer hand-writes .ui-stat divs",
      /'<div class="ui-stat '/.test(catalog), false);

console.log("\n=== the share bar says what the number is a share of ===");
check("uiStat draws one when given a share", /ui-stat-bar/.test(pageui), true);
check("  and only then",
      /o\.share !== null && o\.share !== undefined/.test(pageui), true);
check("  clamped, so a bad denominator cannot draw past the card",
      /Math\.max\(0, Math\.min\(100,/.test(pageui), true);
check("the shared sheet positions it", /\.ui-stat-bar\{|, \.ui-stat-bar\{/.test(shared), true);

console.log("\n=== four is the cap, not the assumption ===");
// Orders draws three. A flat repeat(4) left it with an empty quarter, which
// reads as a card that failed to load.
check("fewer than four cards get fewer columns",
      /:not\(:has\(> :nth-child\(4\)\)\)/.test(shared), true);
check("  down to one across", /:not\(:has\(> :nth-child\(2\)\)\)/.test(shared), true);

console.log("\n=== the count-up followed the card ===");
check("motion.js animates the shared number", /\.ui-stat-v/.test(motion), true);
// It rewrites the text to animate it, so anything carrying a symbol -- "60%",
// "£1,240", an em-dash for not-yet -- would come back as a naked number.
check("  and only when the value is a bare count",
      /\^\[0-9\]\[0-9,\]\*\$/.test(motion), true);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
