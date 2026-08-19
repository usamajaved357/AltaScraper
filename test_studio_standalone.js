// The Image Studio must work on its own page, from nothing.
//
//     "i wanted the image studio as a separate page and wanted to work it as a
//      separate page, i should not have to go to another screen to generate
//      image to complete the image gen pipeline. the image studio page all
//      alone should be able to do it"
//
// Its empty state said, in so many words, "Open Listings and press the photo
// button" — which IS the round trip. It was a screen that could only be ENTERED
// from somewhere else, carrying state somewhere else had set up.
//
// TWO THINGS THIS MUST NOT DO:
//
//   TAKE OVER THE OLD PATH. Selecting rows in Listings and pressing the photo
//   button still has to work exactly as before. That workflow is right when you
//   are already looking at the rows, and it was not asked to move.
//
//   REPLACE imagestudioOnOpen(). genimage.js already defines it, and this file
//   loads AFTER — so naming the new handler the same thing would have silently
//   replaced the original and stopped the studio re-rendering what Listings had
//   handed it. Nothing would throw; the screen would just be blank on the path
//   that used to work.
const fs = require("fs");
const path = require("path");

const FAIL = [];
function check(label, ok) {
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL"));
  if (!ok) FAIL.push(label);
}
function read(p) { return fs.readFileSync(path.join(__dirname, p), "utf8"); }
function codeOnly(s) {
  return s.split("\n")
    .filter((l) => !l.trim().startsWith("//") && !l.trim().startsWith("*")
                   && !l.trim().startsWith("/*"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

const SP = codeOnly(read("static/js/studiopicker.js"));
const PP = codeOnly(read("static/js/productpicker.js"));
const GI = codeOnly(read("static/js/genimage.js"));
const SHELL = codeOnly(read("static/js/shell.js"));
const HTML = read("templates/dashboard.html");

console.log("== the studio picks its own product ==");
check("there is a picker on the page", /id="studio_picker"/.test(HTML));
check("  and the old go-to-Listings message is gone",
  !/Open <b>Listings<\/b> and press the/.test(HTML));
check("  it renders through the shared picker", /ppRender\("studio_picker_list"/.test(SP));
check("  and choosing one fills STUDIO", /STUDIO = \{/.test(SP));

console.log("== it fills STUDIO the way Listings does ==");
// Everything downstream — main images, secondary sets, A+ modules, the concept
// strategist — reads STUDIO. If this builds a different shape, the pipeline
// half-works in ways that are hard to attribute.
["skus", "items", "brand", "manualRef", "recipes", "results"].forEach(function (k) {
  check("  STUDIO." + k + " is set", new RegExp(k + ":").test(SP));
});
// The attributes are the FACTS the A+ and secondary generators are built from.
// The Research ASIN handoff had to be fixed for dropping exactly these.
check("  including the attributes, which are the facts", /attributes:/.test(SP));

console.log("== it does not replace the existing handler ==");
check("genimage.js still owns imagestudioOnOpen",
  /function imagestudioOnOpen\(\)/.test(GI));
check("  the picker uses its OWN name", /function studioPickerOnOpen\(/.test(SP));
check("  and does NOT redefine the original",
  !/function imagestudioOnOpen\(/.test(SP));
check("  it calls the original after drawing the picker",
  /imagestudioOnOpen\(\)/.test(SP));
check("navTo prefers the picker and falls back",
  /studioPickerOnOpen/.test(SHELL) && /else if\(typeof imagestudioOnOpen/.test(SHELL));

console.log("== one picker, not two ==");
// The Image Library grew one first. A second copy drifts the moment either page
// changes how a product is chosen, and the symptom is two screens disagreeing
// about what this account sells.
check("the picker is its own file", PP.length > 400);
check("  it is what fetches the products", /\/catalog\/products/.test(PP));
check("  the studio does not fetch its own", !/\/catalog\/products/.test(SP));
const IL = codeOnly(read("static/js/imagelibrary.js"));
check("  nor does the image library", !/\/catalog\/products/.test(IL));
check("  both go through ppLoad", /ppLoad\(/.test(SP) && /ppLoad\(/.test(IL));
// Fetched once and shared: two screens asking for the same list on every visit
// is two waits for the same answer.
check("  and it is fetched once", /PPICK\.loaded && !force/.test(PP));

console.log("== an account switch invalidates it ==");
// Showing one account's products on another's screen is the exact fault the
// rest of this app has been hardening against.
check("there is a way to clear it", /function ppInvalidate\(/.test(PP));

console.log("== an empty list says what to do ==");
// This is the state a brand-new account is in, and "no products" alone reads as
// a broken screen.
check("it explains rather than showing nothing",
  /No products yet for this account/.test(PP));
check("  and names the way round it", /Research ASIN/.test(PP));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
