// The Image Library as its own page.
//
//     "make the image library work on its own as a separate page, i should not
//      have to go from one page to another to just create images"
//
// It was a modal over Listings, opened from a row. Right when you are already
// looking at a row and want its pictures; wrong as the place you go to WORK on
// images, because every SKU meant going back to Listings, finding the row, and
// opening it again — the round trip being complained about.
//
// TWO THINGS THIS MUST NOT DO:
//
//   BE A SECOND LIBRARY. A copy would drift from the original the first time
//   either was improved, and the library is the most-edited screen in this app.
//   There is ONE, and it renders into whichever host is set (Rule 12).
//
//   FORGET TO HAND IT BACK. Leaving the page without releasing the host means
//   the next press of the images button on a Listings row draws into a
//   container on a screen nobody is looking at, and the modal opens empty.
//   That is the kind of fault that appears a week later and looks unrelated.
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

const IL = codeOnly(read("static/js/listingimages.js"));
const PG = codeOnly(read("static/js/imagelibrary.js"));
const SHELL = codeOnly(read("static/js/shell.js"));
const HTML = read("templates/dashboard.html");
const CSS = read("static/css/dashboard.css");

console.log("== there is still only ONE library ==");
check("the library can be told where to draw", /function ilRenderInto\(/.test(IL));
check("  through one body lookup", /function _ilBody\(/.test(IL));
check("  which the renderer uses", /const b = _ilBody\(\)/.test(IL));
// The page calls the real thing rather than reimplementing it.
check("the page opens the REAL library", /openImageLibrary\(IMGP\.sku/.test(PG));
check("  and does not draw its own grid",
  !/mediagrid|il_upstatus|ilSetMain/.test(PG));

console.log("== the modal is still the default ==");
// The row button is a real workflow and moving it was not asked for.
check("the host starts empty", /let _IL_HOST = ""/.test(IL));
check("  so nothing changes until a page sets it",
  /if\(!_IL_HOST\)\{/.test(IL));
check("  the modal is still built when there is no page host",
  /host\.classList\.add\("open"\)/.test(IL));

console.log("== leaving hands it back ==");
// Without this the next row-button press draws into a page nobody is on.
check("the page has a leave hook", /function imagelibOnLeave\(/.test(PG));
check("  which clears the host", /ilRenderInto\(""\)/.test(PG));
check("  and navTo calls it on the way out",
  /CUR_SEC === "imagelib" && sec !== "imagelib"/.test(SHELL));
check("  before the section changes",
  SHELL.indexOf("imagelibOnLeave") < SHELL.indexOf("CUR_SEC=sec"));

console.log("== the picker is the point of the page ==");
check("products are listed", /imgp-row/.test(PG));
check("  searchable by sku, asin and title",
  /r\.sku.*indexOf/.test(PG) && /r\.asin/.test(PG) && /r\.title/.test(PG));
// The list itself moved into static/js/productpicker.js when the Image Studio
// needed the identical picker -- two copies would have drifted the first time
// either page changed how a product is chosen. So this page must USE the shared
// one rather than fetch its own, which is a stronger statement than the one
// this assertion used to make.
check("  from the shared picker, not a second fetch",
  /ppLoad\(/.test(PG) && !/\/catalog\/products/.test(PG));
check("  and the picker is the thing that fetches",
  /\/catalog\/products/.test(codeOnly(read("static/js/productpicker.js"))));
// A picker of four hundred rows is a scrollbar nobody uses, and a silent cap
// reads as "that is all there is".
check("  capped, and it says so", /slice\(0, 60\)/.test(PG) && /Showing 60 of/.test(PG));
check("the chosen product is named", /imgp_which/.test(PG));

console.log("== the picker does not scroll away ==");
// Choosing the next product must not push the images off screen — that is the
// round trip this page exists to remove.
check("the two sit side by side", /\.imgp-split\{display:grid/.test(CSS));
check("  with the picker pinned", /\.imgp-left\{[^}]*position:sticky/.test(CSS));
check("  and stacking on a narrow screen",
  /@media \(max-width:900px\)\{[\s\S]{0,200}\.imgp-split\{grid-template-columns:1fr\}/.test(CSS));

console.log("== it is reachable ==");
check("there is a nav item", /data-sec="imagelib"/.test(HTML));
check("  a panel", /id="sec_imagelib"/.test(HTML));
check("  a container for the library", /id="imgp_lib"/.test(HTML));
check("  the script is loaded", /imagelibrary\.js\?v=/.test(HTML));
check("  and navTo knows it",
  /"imagelib"/.test(SHELL) && /imagelibOnOpen/.test(SHELL));

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
