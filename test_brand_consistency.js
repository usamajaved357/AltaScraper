/* Every screen should look like the same product.
 *
 * "i want you to design the theme of image library and the image studio and
 *  asin monitor and import seller and repricer and generate and submit by
 *  following the same branding which we are using in sales, hourly sales
 *  traffic ai spend and return intelligence"
 *
 * Those five were built to one pattern:
 *
 *     .wspanel  >  .wstoolbar.bleed  >  h2 + a .ti icon + a .sub line
 *               >  a card, a title, a sub-line, chips for the controls
 *
 * The older screens predate it and were each dressed by hand -- bare <button>s,
 * borders and radii typed inline, a heading with no icon. They worked
 * identically and looked like six different products.
 *
 * What is checked here is the SHAPE, not the pixels: that each screen has the
 * header the others have, and that the pieces they were missing exist under one
 * name rather than being retyped per screen. A screenshot test would fail on
 * every deliberate change; this fails only when a screen drops out of the
 * pattern.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const read = p => fs.readFileSync((__dirname + "/") + p, "utf8");
const HTML = read("templates/dashboard.html");
const CSS  = read("static/css/dashboard.css");

/* The markup of one screen's section, from its opening div to the next one. */
function section(id){
  const i = HTML.indexOf('id="sec_' + id + '"');
  if(i < 0) return "";
  const j = HTML.indexOf('id="sec_', i + 10);
  return HTML.slice(i, j < 0 ? i + 6000 : j);
}

console.log("=== every screen introduces itself the same way ===");
// The five that set the pattern, and the ones brought into line with it.
// "generate" left this list on 28 Sep 2026: the Generate & submit screen was
// retired on 26 Sep (562b4d8, docs/changelog.md) -- the generation flow moved
// onto the Listings page. See the block further down that pins it stays gone.
const SCREENS = ["sales", "traffic", "returns", "aiusage", "hourly",
                 "monitor", "sellerimport", "sourcing"];
SCREENS.forEach(function(id){
  const s = section(id);
  truthy("  " + id.padEnd(13) + " has a header", /wstoolbar|panelsub/.test(s));
});

console.log("\n=== an icon and a sentence, not a bare word ===");
["traffic", "returns", "aiusage", "hourly", "monitor",
 "sellerimport", "sourcing"].forEach(function(id){
  const s = section(id);
  truthy("  " + id.padEnd(13) + " names itself with an icon",
         /<(h2|div class="pagetitle")><i class="ti ti-[a-z0-9\-]+"><\/i>/.test(s));
  truthy("  " + id.padEnd(13) + " says what it is for",
         /class="(sub|panelsub)"/.test(s));
});

console.log("\n=== and every screen's name is the SAME SIZE ===");
// THIS TEST USED TO EXEMPT SALES. It said "Sales draws its own 28px title, so
// it is exempt from the h2 rule" -- writing the inconsistency down as a rule
// instead of removing it. A screen whose name is 15px next to one whose name is
// 28px reads as a panel inside something else, and that single difference was
// most of why the newer tabs looked unfinished. Reported as: "i asked you to
// adapt the new branding today, it meaned make the features look good looking".
truthy("the page title is a class, not an inline size on one screen",
       /\.pagehead \.pagetitle\{|\.pagehead h1,\.pagehead \.pagetitle\{/.test(CSS)
       || /\.pagehead h1,\s*\.pagehead \.pagetitle\{/.test(CSS));
truthy("  at the size Sales always used", /font-size:28px/.test(CSS));
truthy("Sales uses it rather than an inline style",
       /<div class="pagetitle" id="sales_title">/.test(HTML));
truthy("  and no longer sets the size by hand",
       !/font-size:28px;font-weight:600;line-height:30\.8px/.test(HTML));
/* THERE ARE TWO SHARED HEADERS, NOT ONE, AND THAT IS DELIBERATE.
 *
 *     .pagehead .pagetitle   28px   4 screens (Sales, generate, sellerimport, sourcing)
 *     .wstoolbar h2          15px  35 screens (Listings, Orders, Returns, Monitor, ...)
 *
 * This block asserted that all four of the named screens use .pagehead. The ASIN
 * Monitor no longer does, on purpose: it had a third, bespoke header of its own
 * and was moved onto .wstoolbar to match the thirty-five, after "the current
 * theme of the page is not alligned with our all other app". Demanding .pagehead
 * back would undo that.
 *
 * So what is guarded is the invariant that actually prevents drift -- a screen's
 * title comes from a SHARED class and never from a hand-set size. Which of the
 * two tiers a screen sits in is a design decision, and collapsing 28px and 15px
 * into one size is a change across thirty-nine screens that nobody has asked
 * for; it is recorded here rather than made silently.
 */
["monitor", "sellerimport", "sourcing"].forEach(function(id){
  const s = section(id);
  truthy("  " + id.padEnd(13) + " takes its title from a shared header",
         /class="pagehead"/.test(s) || /class="wstoolbar/.test(s));
  // Only the TITLE element. Scoping this to the whole section caught a hint
  // caption and a footnote that legitimately set their own size, which is not
  // what this is about -- a body element choosing 11.5px is not the page name
  // choosing to look different from every other page name.
  const title = (s.match(/<(?:h1|h2)[^>]*>/) || s.match(/<div class="pagetitle"[^>]*>/) || [""])[0];
  truthy("    and the title itself sets no size by hand",
         !!title && !/font-size/.test(title));
});

console.log("\n=== the pieces exist ONCE, under one name ===");
// A card called .salespanel is why Traffic had to borrow a sales class and the
// other screens drew their own borders instead. One rule, two names.
truthy("there is a card name that is not called 'sales'",
       /\.panelcard,\s*\n?\s*\.salespanel\{/.test(CSS));
truthy("chips can carry an intent", /\.db-chip\.go\{/.test(CSS)
       && /\.db-chip\.risk\{/.test(CSS));
truthy("  and one of them can be the primary action", /\.db-chip\.primary\{/.test(CSS));
truthy("a disabled chip looks disabled", /\.db-chip\[disabled\]\{/.test(CSS));
truthy("a modal's title sits with its icon", /\.modal \.paneltitle\{/.test(CSS));

// RE-PINNED 28 Sep 2026 (Milestone 1). This block checked the Generate &
// submit screen's chips and selector card. That screen was RETIRED on 26 Sep
// (562b4d8, recorded in docs/changelog.md and known-issues): its flow moved onto
// the Listings page. What is worth pinning now is that it stays retired, rather
// than a half-screen coming back with bare buttons.
console.log("\n=== the retired Generate & submit screen stays retired ===");
truthy("there is no separate Generate screen", section("generate") === "");

console.log("\n=== the modals do not change key ===");
// The Image Studio is no longer a modal -- it is its own screen, asked for as
// "make the image studio as its own seperate page". What this pinned still
// holds and still matters: it introduces itself, and it says what it will NOT
// do. Only where that lives has changed, from a modal panelhead to the screen's
// own toolbar.
truthy("Image Studio introduces itself",
       /<h2><i class="ti ti-photo-edit"><\/i> Image Studio<\/h2>/.test(HTML));
truthy("  and says what it will not do", /Nothing here reaches Amazon/.test(HTML));
truthy("  on its own screen, not in a dialog",
       /id="sec_imagestudio" class="wspanel"/.test(HTML));
truthy("  and the body it renders into is unchanged, so nothing had to move",
       /id="studiobody"/.test(HTML));
const lib = read("static/js/listingimages.js");
truthy("the Image Library uses the shared title class",
       /class="paneltitle"/.test(lib));
// A bare file input is drawn by the browser in its own colours, so it arrived
// as the one light-grey control on a dark panel.
truthy("its upload control is not a raw browser file button",
       /class="visually-hidden"/.test(lib) && /<label class="db-chip" for="il_upload"/.test(lib));
truthy("  and the input is still reachable by keyboard",
       /\.visually-hidden\{/.test(CSS) && !/\.visually-hidden\{[^}]*display:none/.test(CSS));

// RE-PINNED 28 Sep 2026. The "Add a product" form this checked was removed on
// the owner's request (5e78d3e, docs/decisions.md 27 Sep); inputqueue.js keeps a
// note where it was. Pinned: it has not come back with its old accent outline.
console.log("\n=== the queue's add-form stays removed ===");
const iq = read("static/js/inputqueue.js");
truthy("no full accent outline is drawn", !/border:1px solid var\(--accent\)/.test(iq));
truthy("  and the removal is recorded where the form was",
       /THE "ADD A PRODUCT" FORM WAS HERE/.test(iq));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
