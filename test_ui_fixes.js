// Four things that were wrong on screen.
//
// "i see that my every live listing shows a red or orange dots on them, donot
//  set the status to review when there is no problem in it ... if there is no
//  flag no need to highlight, if there is a api error than it should show that
//  dot"
// "you said i will be able to preview images by clicking on them like in drive
//  when i go to the images section on the app, which is not truth"
// "also i do not have a download button in the image refs tab"
// "i am not able to understand how to create variations using it. give me a how
//  this page works button on the variations page"

const fs = require("fs");
const L = fs.readFileSync("static/js/listings.js", "utf8");
const S = fs.readFileSync("static/js/settings.js", "utf8");
const G = fs.readFileSync("static/js/guide.js", "utf8");
const H = fs.readFileSync("templates/dashboard.html", "utf8");
const C = fs.readFileSync("static/css/dashboard.css", "utf8");

let fails = [];
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(70) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

console.log("=== the dot reports a PROBLEM, not a stored word ===");
// It coloured straight off r.status, so a listing that went live months ago but
// whose row still says API_ERROR from a failed attempt before that showed red
// for ever. The counts along the top already reclassify those as LIVE; the dot
// did not, so the tiles and the counts disagreed.
truthy("the dot asks Amazon whether the listing is live",
       L.includes("live = isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown)"));
truthy("  a live listing with nothing against it is quiet",
       L.includes('if(_rowHasFlag(r)) return "var(--warn)";') &&
       L.includes('return "var(--ink3)";              // quiet'));
truthy("  and a real flag still shows", L.includes("function _rowHasFlag"));
truthy("an API error still gets its dot",
       L.includes('if(isHold(s) || s === "API_ERROR" || s === "ERROR") return "var(--red)";'));

console.log("\n--- and a flag means one of the checks that already run ---");
// Compliance, restricted types, IP and claim risks -- not a status word.
truthy("IP risk", L.includes('r.ip_risk || ""'));
truthy("claim risks", L.includes("r.claim_flags || []"));
truthy("compliance document demands", L.includes("v.matched && (v.risks || []).length"));
truthy("restricted product types", L.includes("rs.matched &&"));

console.log("\n--- the status pill agrees with the dot ---");
truthy("the pill shows what is true today", L.includes("_statusPill(_shownStatus(r))"));
truthy("  which is LIVE when Amazon says so", L.includes("function _shownStatus"));
truthy("  and the reason is recorded",
       L.includes("not as it was stored"));

console.log("\n=== the image previewer, in the Image refs grid ===");
// It called window.open(), which hands the picture to the browser and takes you
// out of the app to look at it.
falsy("clicking no longer opens a browser tab",
      S.includes('onclick="window.open(\\\'' ) ||
      S.includes("img src=\"'+esc(im.url)+'\" loading=\"lazy\" onclick=\"window.open("));
truthy("it opens the full-screen viewer", S.includes("ilPreview("));
truthy("  the SAME one the image library uses, not a second copy",
       S.includes("Rule 12") && S.includes("ilPreview in listingimages.js"));
truthy("  with window.open kept only as a fallback",
       S.includes("typeof ilPreview === 'function'"));
truthy("and the cursor says it can be clicked", S.includes("cursor:zoom-in"));

console.log("\n=== the download button ===");
truthy("every image cell has one", S.includes('class="mediadl"'));
truthy("  going through the library's own download", S.includes("ilDownloadOne("));
truthy("  and it is styled", C.includes(".mediadl{"));
truthy("  in the one corner the other three buttons do not use",
       C.includes("bottom:4px;right:4px") &&
       C.includes(".mediadel is top-right"));

console.log("\n=== the Variations guide ===");
truthy("there is a guide for it", G.includes("variations: {"));
truthy("  reached from the page", H.includes("openGuide('variations')"));
truthy("  with a button that says what it is",
       /openGuide\('variations'\)[^>]*>\s*<i class="ti ti-book"><\/i> How this page works/.test(H));

console.log("\n--- and it explains the things that actually catch people out ---");
truthy("that a family is built from LIVE listings, not drafts",
       G.includes("a draft cannot be in one until it has"));
truthy("that the parent cannot be bought",
       G.includes("<b>nobody can buy</b>"));
truthy("that only the allowed groupings are offered, with the rest explained",
       G.includes("greyed with the reason"));
truthy("that the preview IS the payload", G.includes("preview <b>is</b> the payload"));
truthy("what the parent inherits and what it borrows",
       G.includes("<b>inherits</b>") && G.includes("<b>borrows</b>"));
truthy("that the parent goes up first, and nothing follows if it fails",
       G.includes("If the parent is \nrefused") || G.includes("nothing else is sent"));
truthy("and the reason all of it is checked beforehand",
       G.includes("WITHOUT COMPLAINING"));

// "change this altascraper bar from the top i dont like it Put a stylish A
//  symbol on the top of it"
//
// The wordmark spent 110px of the top bar naming the app on the only screen you
// cannot reach without already knowing which app you opened. What was left had
// to earn its place, so it is DRAWN rather than typed: a letterform in a
// rounded box goes soft at 22px and two strokes with round joins do not.
console.log("\n=== the top bar carries a mark, not a wordmark ===");
truthy("the mark is an SVG", H.includes('<svg class="amark"'));
truthy("  drawn as strokes, so it stays sharp when small",
       H.includes('stroke-linejoin="round"') && H.includes('class="glyph"'));
truthy("  with the tile behind it", H.includes('class="tile"'));
check("the wordmark is gone", H.includes("<span>AltaScraper</span>"), false);
// It is a mark, not a control -- a logo that opens a dialog is a surprise
// rather than a shortcut, and switching account is a sidebar row that says so.
truthy("it is still not clickable", H.includes('class="brandmark" style="cursor:default"'));
// Screen readers and hover both need the name the picture no longer spells.
truthy("  but it still says what it is",
       H.includes('aria-label="AltaScraper"') && H.includes('title="AltaScraper"'));
truthy("the gradient falls back where no second accent is themed",
       C.includes("stop-color:var(--accent2,var(--accent))"));
// The login screens keep their wordmark on purpose: that IS where you need to
// be told which app you have reached.
truthy("the lettered tile is kept for the screens that still use it",
       C.includes(".appbar .brandmark .dot{"));

console.log("\nFAILURES: " + fails.length);
fails.forEach(f => console.log("   - " + f));
process.exit(fails.length ? 1 : 0);
