/* THE TWO VIEWS OF THE LISTINGS SCREEN ARE ONE SCREEN.
 *
 * THE REPORT: "the grid view listings and list view listings donot talk to
 * each other".
 *
 * They did not, in two separate ways:
 *
 *   1. THE TABLE OFFERED NOTHING. The card had a checkbox and seven buttons;
 *      the table row had neither. Every batch action on this screen works off
 *      the selection, so in the list view there was no way to select anything
 *      and therefore no way to run any of them.
 *
 *   2. SELECTING IN ONE DID NOT SHOW IN THE OTHER. toggleSelect looked for
 *      '.lcard[data-sku=...]' -- a class that appears nowhere in the app; the
 *      cards are '.tile'. So it had never matched a single element, and the
 *      only reason the grid appeared to work was that the checkbox drew its own
 *      tick before the handler ran.
 *
 * The fix is Rule 12: ONE builder for a row's buttons and ONE for its checkbox,
 * called by both renderers. So the test that matters is not "do both spell out
 * the same markup" -- it is "does each of them defer to the shared one", which
 * is the only shape that cannot drift apart again.
 */
const fs = require("fs");

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  %s %s", label.padEnd(62),
              ok ? "OK" : `FAIL got=${JSON.stringify(got)} want=${JSON.stringify(want)}`);
}
const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const listings = read("static/js/listings.js");
const css = read("static/css/dashboard.css");

/* The file with its comments taken out.
 *
 * Needed for the '.lcard' check below: the comment that RECORDS the bug names
 * the dead class, so searching the raw file finds the explanation and reports
 * it as the fault. What matters is that no code looks for it. */
// BY SCANNING, NOT BY REGEX -- see test_helpers.js. The regex version deleted
// 5,716 characters of listings.js, because a regex literal ending [^.;|]*/gi
// reads as the end of a block comment. It is why "auto-fix: reachable" reported
// that autoFixLoop does not exist when it plainly does.
const { stripJsComments } = require("./test_helpers.js");
function codeOnly(src) {
  return stripJsComments(src);
}

/* The source of one named function, brace-matched. */
function fnBody(src, name) {
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if (!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  if (i < 0) return "";
  for (let j = i, depth = 0; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}

const card = fnBody(listings, "card");
const row = fnBody(listings, "tableRow");
const acts = fnBody(listings, "rowActions");
const box = fnBody(listings, "rowSelectBox");
const toggle = fnBody(listings, "toggleSelect");

console.log("\n=== there is ONE builder for each, not one per view ===");
check("a shared builder for a row's buttons exists", acts.length > 0, true);
check("a shared builder for a row's checkbox exists", box.length > 0, true);

console.log("\n=== and BOTH views use them ===");
check("the card gets its buttons from the shared builder",
      /rowActions\(/.test(card), true);
check("the table row gets its buttons from the same one",
      /rowActions\(/.test(row), true);
check("the card gets its checkbox from the shared builder",
      /rowSelectBox\(/.test(card), true);
check("the table row gets its checkbox from the same one",
      /rowSelectBox\(/.test(row), true);

console.log("\n=== the actions a selection depends on are actually there ===");
// Named individually rather than counted: a count passes while the wrong seven
// buttons are present, and the point is that these specific things are reachable
// from EITHER view.
// EDIT AND AUTO-FIX ARE NOT ICONS IN THE ACTION BAR, and looking for them there
// was the fault rather than a missing button. Opening the editor is what
// CLICKING THE ROW does -- the picture and the title both call openDrawer, in
// the card and in the table row alike -- and Auto-fix is a labelled button
// inside the drawer that opens, not a fifth icon competing with the others.
// So each is checked where it actually is, and both views are checked for the
// ones that genuinely belong to the shared builder.
[["select for batch actions", /toggleSelect\(/, box],
 ["approve", /setStatus\(/, acts],
 ["image studio", /openStudioSingle\(/, acts],
 ["image library", /openImageLibrary\(/, acts],
 ["the overflow menu", /tileMenu\(/, acts]].forEach(function (t) {
  check("  " + t[0], t[1].test(t[2]), true);
});
// WHAT CHANGED, AND WHAT DID NOT. Clicking a card or a row still opens the
// listing for editing -- that is what this pins, and it is unchanged. WHERE it
// opens moved: openListing() sends it to the full-screen product page
// (static/js/pdp.js), falling back to the drawer when that file has not loaded.
// Both views are built from the same editors; see _fullDataParts in autofix.js.
check("  edit: the card opens the editor when clicked",
      /openListing\(/.test(card), true);
check("  edit: and so does the table row",
      /openListing\(/.test(row), true);
check("  auto-fix: reachable once a listing is open",
      /autoFixLoop\(/.test(codeOnly(listings)), true);

console.log("\n=== a selection made in one view shows in the other ===");
// THE BUG: '.lcard' does not exist in this app. Searching for it meant the
// handler never found anything to update, in either direction.
check("no CODE looks for the class that does not exist",
      /\.lcard/.test(codeOnly(listings)), false);
check("the handler finds every element carrying that SKU",
      /querySelectorAll\('\[data-sku="'/.test(toggle), true);
check("  matched safely, so a SKU with a quote in it cannot break the lookup",
      /CSS\.escape/.test(toggle), true);
check("  and it updates the card", /classList\.contains\("tile"\)/.test(toggle), true);
check("  and the table row", /tagName === "TR"/.test(toggle), true);
check("  and ticks the box in whichever view is not showing",
      /box\.checked = on/.test(toggle), true);

console.log("\n=== the table row can be found by SKU at all ===");
check("the row carries its SKU", /data-sku="\$\{esc\(r\.sku\)\}"/.test(row), true);
check("the card carries its SKU", /data-sku="\$\{esc\(r\.sku\)\}"/.test(card), true);

console.log("\n=== select-all, which only the table can offer ===");
check("the table header has a select-all",
      /selectAllVisible\(this\.checked\)/.test(listings), true);
check("  reusing the existing function rather than a second one",
      (listings.match(/function selectAllVisible/g) || []).length, 1);

console.log("\n=== the table's own controls are styled ===");
[".lt .selcol", ".lt input.rowsel", ".lt tbody tr.rowon", ".lt .acts"].forEach(function (s) {
  check("  " + s + " has a rule", css.indexOf(s) >= 0, true);
});

console.log("\nFAILURES: %d", fails);
process.exit(fails ? 1 : 0);
