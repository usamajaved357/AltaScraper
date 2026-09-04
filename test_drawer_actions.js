/* The listing drawer: fewer buttons, and the ones left say what they do.
 *
 *     "i want to minimize the buttons, because i believe many tasks are already
 *      handled by other processes or button already working on the backend etc"
 *
 * Fifteen controls sat in one flat wrapping row, every one the same size and
 * weight, so nothing looked more important than anything else. Each was put
 * through the same test the CARD's buttons were put through -- does something
 * else already do this? -- and this time several failed it.
 *
 * ONE was deleted. "Suggest missing fields" is step one of Auto-fix, which sits
 * beside it: autofix.js calls suggestFields() and then applies the result.
 *
 * The rest were DEMOTED, not removed, because each is still the only way to do
 * something -- just not something you do to every listing:
 *
 *   Refresh dropdowns   openDrawer already fetches a missing schema; this is for
 *                       when Amazon CHANGES one, and is the only cache-buster.
 *   Pull live images    Sync does the whole account.
 *   Push image / Upload the Image Library does both, and shows you the image
 *                       first.
 *   Delete              destructive, and it sat inline between Ask Claude and
 *                       the edge of the drawer.
 *
 * And Approve + Hold became ONE control, because they are one setting with two
 * values -- drawn as two buttons, neither could show which was already true.
 */
"use strict";
const fs = require("fs");
const { stripJsComments } = require("./test_helpers.js");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(l, g) { check(l, !!g, true); }
function falsy(l, g) { check(l, !!g, false); }

const RAW = fs.readFileSync("D:/AltaScraper/static/js/listings.js", "utf8");
const L = stripJsComments(RAW);
const CSS = fs.readFileSync("D:/AltaScraper/static/css/dashboard.css", "utf8");

function fnBody(src, name) {
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if (!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  if (i < 0) return "";
  for (let j = i, d = 0; j < src.length; j++) {
    if (src[j] === "{") d++;
    else if (src[j] === "}" && --d === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}

// REWRITTEN, NOT DELETED, AND THE FILE ITSELF SAYS WHERE EVERYTHING WENT.
//
// This read a .dwbar out of drawerContent and checked six buttons on it. The
// drawer was redesigned since -- _dwShell builds a sticky header instead, and
// listings.js carries a note headed "WHERE THE OLD DRAWER HEADER WENT" listing
// each control's new home. Nothing was removed; the bar was.
//
// So the check is the same one it always was -- every action is still reachable
// from the drawer -- asked of the shell that actually draws them.
const D = fnBody(L, "drawerContent");
const SH = fnBody(L, "_dwShell");
truthy("the drawer shell was found", SH.length > 2000);
truthy("  and the redesign says where each control went",
       L.indexOf("WHERE THE OLD DRAWER HEADER WENT") >= 0);

console.log("=== every action is still reachable from the drawer ===");
const DRAWER = SH + D;
for (const [what, mark] of [["Preview", "previewOne("], ["Auto-fix", "autoFixLoop("],
                            ["Submit", "submitOne("], ["Image Studio", "openStudioSingle("],
                            ["Ask Claude", "askAbout("], ["More", "drawerMore("]]) {
  truthy("  " + what + " is there", DRAWER.indexOf(mark) >= 0);
}
// THE THREE THAT MATTER STILL CARRY COLOUR AND THE REST DO NOT. When everything
// is emphasised, nothing is -- the same rule, in the class names the shell uses.
truthy("Preview, Auto-fix and Submit are the emphasised three",
       /dw2-ib" onclick="previewOne\(/.test(SH)
       && /dw2-ib accent" onclick="autoFixLoop\(/.test(SH)
       && /dw2-ib success" onclick="submitOne\(/.test(SH));
truthy("  and the rest are quiet", /dw2-ib" onclick="drawerMore\(/.test(SH));
// A READ-ONLY WORKSPACE MAY NOT PUBLISH, and the button says so rather than
// failing when pressed.
truthy("a read-only workspace gets a locked Submit",
       /Read-only workspace/.test(SH) && /disabled/.test(SH));

console.log("\n=== the one that was deleted, and why it could be ===");
// The BUTTON, not the identifier: the note above explaining why it went names
// the function, and a bare identifier match cannot tell an explanation from a
// control.
falsy("Suggest missing fields is gone from the drawer",
      /onclick="suggestFields\(/.test(SH + D));
// It is not dead: auto-fix is the thing that calls it now.
const AF = stripJsComments(fs.readFileSync("D:/AltaScraper/static/js/autofix.js", "utf8"));
truthy("  because Auto-fix calls it", /suggestFields\(/.test(AF));
truthy("  and then applies the result", /\/edit|_afApply|applyOne/.test(AF));

console.log("\n=== the demoted ones are one click away, not gone ===");
const M = fnBody(L, "drawerMore");
truthy("the overflow exists", M.length > 200);
for (const [what, mark] of [["Refresh dropdown options", "refreshSchemaFor("],
                            ["Image library", "openImageLibrary("],
                            ["Pull live images", "pullLiveRow("],
                            ["Push image live", "pushImageLive("],
                            ["Delete", "delRow("]]) {
  truthy("  " + what + " is in it", M.indexOf(mark) >= 0);
}
// The two that act on a LIVE listing must not be offered on a draft: there is
// nothing on Amazon to pull from or push to.
// Both must sit inside the SAME isLive branch. Measured by position rather than
// by one long regex over a thousand characters of markup, which is a shape that
// breaks whenever a title is reworded.
const _lv = M.indexOf("isLive"), _pl = M.indexOf("pullLiveRow"),
      _ps = M.indexOf("pushImageLive"), _end = M.indexOf(': ""');
truthy("the live-only two are behind the live check",
       _lv >= 0 && _lv < _pl && _pl < _ps && _ps < _end);
truthy("delete is marked as destructive", /class="danger"/.test(M));
// It reuses the card's menu rather than inventing a second menu style.
truthy("it reuses the existing menu component", /className\s*=\s*"tilemenu"/.test(M));
truthy("  and closes the previous one first", /closeTileMenu\(\)/.test(M));
// The drawer is pinned to the right edge, so a menu laid out rightwards from the
// button opens off-screen.
truthy("it is placed so it cannot open off the right edge",
       /rect\.right - 232/.test(M));

console.log("\n=== status: one control, and it never lies ===");
// THE SEGMENTED CONTROL BECAME TWO LIT ICONS in the redesign, and the reason it
// existed is unchanged: Approve and Hold are one choice, and the half that is
// already true has to show as true rather than as a button you might press
// again. Same rule, two buttons that light instead of two halves of one.
truthy("Approve and Hold both set the status", /setStatus\('\$\{esc\(r\.sku\)\}','APPROVED'/.test(SH)
       && /setStatus\('\$\{esc\(r\.sku\)\}','NEEDS_REVIEW'/.test(SH));
truthy("  the one that is true is lit", /on-approve/.test(SH) && /on-hold/.test(SH));
truthy("  and says so rather than offering it again",
       /Already approved/.test(SH) && /Already held/.test(SH));
/* THE TOGGLE CANNOT SPEAK FOR EVERY STATUS. Measured on the 173 stored
 * listings: 84 are APPROVED or NEEDS_REVIEW, and the other 89 are LIVE,
 * COMPLIANCE_HOLD, API_READY, API_ERROR, SUBMITTED or PARENT -- Amazon's state
 * or the app's, not a choice anybody makes in this drawer. On those, a bare
 * toggle lights neither half and says nothing at all. */
// AND THE REAL STATUS IS STILL ALWAYS ON SCREEN. Measured on the 173 stored
// listings: 84 are APPROVED or NEEDS_REVIEW, and the other 89 are LIVE,
// COMPLIANCE_HOLD, API_READY, API_ERROR, SUBMITTED or PARENT -- Amazon's state
// or the app's, not a choice anybody makes in this drawer. On those the two
// icons light neither way, so the badge is the only thing that says what the
// listing actually is.
truthy("the real status is shown as well", /class="badge \$\{badgeClass\(r\.status\)\}"/.test(SH));
truthy("  using the same class the card and the table use",
       /badgeClass\(/.test(L));

console.log("\n=== Orbit, and it stays put while the drawer scrolls ===");
truthy("the bar is sticky", /\.dwbar\{position:sticky/.test(CSS));
truthy("  with Orbit's radius and one-pixel border",
       /\.dwbar\{[^}]*border-radius:10px/.test(CSS.replace(/\s+/g, "")) ||
       /border-radius:10px/.test(CSS.slice(CSS.indexOf(".dwbar{"), CSS.indexOf(".dwbar{") + 400)));
// The colour still carries the meaning it did when these were two buttons:
// Approve was green and Hold was plain. Merging them must not flatten both into
// one accent, or the colour would only say "this is the selected one".
truthy("  the approved half is green",
       /\.dwseg-b\.on:first-child\{background:var\(--green\)/.test(CSS));
truthy("  and the held half is amber, not the same colour",
       /\.dwseg-b\.on:last-child\{background:var\(--warn/.test(CSS));
// A sticky bar on a phone eats a third of the screen, and two groups do not fit
// side by side.
truthy("a phone gets it unstuck and stacked",
       /\.dwbar\{position:static;flex-direction:column/.test(CSS.replace(/\s+/g, " ")));

console.log("\n=== nothing that was demoted lost its function ===");
const ALL = fs.readdirSync("D:/AltaScraper/static/js").filter(f => f.endsWith(".js"))
  .map(f => fs.readFileSync("D:/AltaScraper/static/js/" + f, "utf8")).join("\n");
for (const f of ["refreshSchemaFor", "pullLiveRow", "pushImageLive",
                 "uploadMainImage", "suggestFields", "openImageLibrary"]) {
  truthy("  " + f + " still exists", new RegExp("function\\s+" + f + "\\s*\\(").test(ALL));
}
// Upload was demoted on the grounds that the Library already does it. If that
// stopped being true the demotion would have quietly removed the only way in.
truthy("the Image Library really does offer upload",
       /uploadMainImage\(/.test(fs.readFileSync(
         "D:/AltaScraper/static/js/listingimages.js", "utf8")));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
