// A media folder says which PRODUCT it is, and its pictures step like Drive.
//
//     "allow me to swich between images within the folder of the sku by the
//      arrows as we have an option in the google drive and also write the name
//      of the item first 4 words only and the asin of the item along with the
//      main image of the item on the folder containing the images created for
//      that sku"
//
// Two halves, and each has one way of going quietly wrong:
//
//   THE ASIN. A SKU here looks like price_days_ASIN — 10.06_3Days_B0081ZHHTS —
//   and that trailing ASIN is a COMPETITOR REFERENCE used to pull product data
//   during generation (CLAUDE.md Rule 1). It is not this listing's ASIN.
//   Printing it as "the ASIN of the item" would label every folder in the app
//   with somebody else's product, and it would look completely correct.
//
//   THE DOWNLOAD BUTTON. Arrows that change the picture but leave the buttons
//   behind mean Download quietly saves the image you were looking at three
//   arrows ago — worse than having no button at all.
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
    .filter((l) => !l.trim().startsWith("//"))
    .map((l) => l.replace(/\s\/\/.*$/, ""))
    .join("\n");
}

const SET = codeOnly(read("static/js/settings.js"));
const IL = codeOnly(read("static/js/listingimages.js"));
const PY = read("routes/media_routes.py");
const CSS = read("static/css/dashboard.css");

console.log("== the folder carries the product, not just a filename ==");
check("the server attaches a title", /f\["title"\] = /.test(PY));
check("  an ASIN", /f\["asin"\] = /.test(PY));
check("  and the main image", /f\["img"\] = /.test(PY));
// Through the ONE shared lookup, so this folder shows the same picture and
// title as Sales, Traffic and Orders rather than a fourth reading of the
// snapshot that quietly disagrees with them.
check("through the shared catalogue lookup",
  /from domain import catalogue as _cat/.test(PY));
check("  not a private reading of the snapshot",
  !/live_snapshots/.test(PY));
// A folder the catalogue cannot name must still list its images.
check("a folder with no product still renders", /except Exception:/.test(PY) &&
  /f\.setdefault\("title", ""\)/.test(PY));

console.log("== the competitor ASIN in the SKU is not the product's ASIN ==");
// It is used to FIND the record and never reported as the item's own.
check("the SKU tail is only used to look up", /tail = f\["sku"\]\.rsplit/.test(PY));
check("  and only when the catalogue found nothing",
  /if not rec\.get\("title"\) and not rec\.get\("asin"\)/.test(PY));
check("  the ASIN shown comes from the record", /rec\.get\("asin"\)/.test(PY));
// The screen only prints an ASIN when there is a real one.
check("the screen shows no ASIN when there is none", /f\.asin\s*\n?\s*\?/.test(SET) ||
  /f\.asin$/m.test(SET) || /var _asin = f\.asin/.test(SET));

console.log("== four words, because it is a label not a title ==");
check("the name is cut to four words", /\.slice\(0,4\)/.test(SET));
check("  with an ellipsis when there was more", /_more\?'…':''/.test(SET));
// The full title stays reachable — the cut is for the eye, not the data.
check("  and the full title is kept on hover", /title="'\+esc\(f\.title\)/.test(SET));

console.log("== arrows step through the folder ==");
check("the viewer takes a list and a position",
  /function ilPreview\(url, name, items, index\)/.test(IL));
// Backwards compatible: it is the shared viewer for BOTH galleries and the
// other one has no list to give it.
check("  called with two arguments it behaves as before",
  /Array\.isArray\(items\)/.test(IL));
check("  arrows appear only when there is more than one", /const many = list\.length > 1/.test(IL));
check("there is a step function", /function ilStep\(n\)/.test(IL));
check("  it swaps the src rather than rebuilding the overlay",
  /img\.src = it\.url/.test(IL));
// Wrapping means you can never tell whether you have seen everything.
check("  it stops at the ends rather than wrapping",
  /if\(to < 0 \|\| to >= set\.items\.length\) return/.test(IL));
check("  and dims the arrow that can do nothing", /classList\.toggle\("off"/.test(IL));

console.log("== the buttons move with the picture ==");
// Otherwise Download saves the image you were looking at three arrows ago.
check("Download is re-pointed on every step", /ilpreviewdl/.test(IL) &&
  /dl\.setAttribute/.test(IL));
check("  and so is Open", /op\.setAttribute/.test(IL));
check("  the counter is updated too", /ilpreviewcount/.test(IL));

console.log("== the keyboard works ==");
check("left and right arrows step", /ArrowLeft" \|\| ev\.key === "ArrowRight"/.test(IL));
check("  and are stopped from reaching the page", /ev\.preventDefault\(\)/.test(IL));
// Escape must close the PREVIEW and stop there, or a glance at one picture
// costs you the panel behind it.
check("Escape still closes only the viewer", /ev\.key === "Escape"/.test(IL) &&
  /ev\.stopPropagation\(\)/.test(IL));

console.log("== the folder list is not copied into every cell ==");
// A folder of twenty images would otherwise carry twenty copies of its own
// contents in its own markup.
check("the list is held once per SKU", /_MEDIA_FOLDERS\[f\.sku\]/.test(SET));
check("  and the cell just calls it by index", /mediaOpenAt\('/.test(SET) ||
  /mediaOpenAt\(/.test(SET));
check("  with a lookup that falls back safely",
  /if\(typeof ilPreview === 'function'\)/.test(SET));

console.log("== it is styled ==");
["mfpic", "mfname", "mfasin", "mfsku", "ilnav", "ilprev", "ilnext"].forEach(function (c) {
  check("  ." + c + " has a rule", new RegExp("\\." + c + "[\\s,{:]").test(CSS));
});

console.log("\n" + FAIL.length + " failed");
FAIL.forEach((f) => console.log("  - " + f));
process.exit(FAIL.length ? 1 : 0);
