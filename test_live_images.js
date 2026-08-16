/* A live listing's card shows the picture that is ON Amazon.
 *
 * "the images on the cards should reflect the images which are on amazon,
 *  atleast the live listings section should follow this rule"
 *
 * The live group holds two kinds of row, and only one of them was right:
 *
 *   liveCatalog  Amazon has it, this app has no draft. Drawn by liveTile(),
 *                from it.img -- the real main image, fetched per SKU by
 *                /live/images. Correct already.
 *   liveRows     Amazon has it AND this app holds a draft. Drawn by card(),
 *                from the DRAFT's own attributes -- which hold whatever the
 *                generator put there, very often the eBay or competitor photo
 *                the listing was built from.
 *
 * So the rows you have worked on most were the ones showing the wrong picture,
 * and the fix is not to change where a draft's images come from -- the AI
 * reference picker needs exactly those -- but to prefer Amazon's when we have
 * one, for display only.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(66) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const L = read("static/js/listings.js");
const M = read("static/js/miles_template.js");
const G = read("static/js/genimage.js");

function fnBody(src, name){
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if(!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  if(i < 0) return "";
  for(let j = i, depth = 0; j < src.length; j++){
    if(src[j] === "{") depth++;
    else if(src[j] === "}" && --depth === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}

console.log("=== the card prefers what Amazon is showing ===");
truthy("there is a resolver for it", /function _liveImageFor\(r\)/.test(L));
truthy("  reading the catalogue Amazon returned", /LIVE_ITEMS/.test(fnBody(L, "_liveImageFor")));
truthy("  and the image fetched per SKU", /it\.img \|\| it\.image/.test(fnBody(L, "_liveImageFor")));
// Two SKUs can share one ASIN. The SKU is what identifies the listing, so an
// ASIN match must never beat it.
const lif = fnBody(L, "_liveImageFor");
truthy("SKU wins over ASIN", /if\(s && norm\(it\.sku\) === s\) return url;/.test(lif));
truthy("  ASIN is only a fallback", /if\(a && !byAsin && norm\(it\.asin\) === a\) byAsin = url;/.test(lif));

console.log("\n=== both views use it, so they cannot disagree ===");
truthy("the card does", /const urls=_cardImages\(r\);/.test(fnBody(L, "card")));
truthy("the table row does", /_cardImages\(r\)/.test(fnBody(L, "tableRow")));
truthy("Amazon's image comes first", /return \[live\]\.concat/.test(fnBody(L, "_cardImages")));
truthy("  and the draft's are still there behind it",
       /own\.filter\(u => u !== live\)/.test(fnBody(L, "_cardImages")));
truthy("a listing with no Amazon image falls back to the draft's",
       /if\(!live\) return own;/.test(fnBody(L, "_cardImages")));

console.log("\n=== the AI reference picker is deliberately NOT changed ===");
// eBay is the truth of what the item IS. That is a different question from what
// Amazon is currently displaying, and the studio needs the first one.
truthy("_rowImages still reads the draft's own attributes",
       /JSON\.parse\(r\.attrs\|\|'\{\}'\)/.test(fnBody(L, "_rowImages")));
truthy("  and does not consult the live catalogue",
       !/LIVE_ITEMS/.test(fnBody(L, "_rowImages")));
truthy("the image studio still uses it", /_rowImages\(it\)/.test(G));
truthy("  and the reason is written down", /eBay is the truth of what the item is/.test(L));

console.log("\n=== an image that arrives late still reaches the card ===");
// liveTile has a liveimg_ slot to patch. A card does not -- it reads the image
// at render time -- so without a re-render the picture arrived and nothing on
// screen changed.
const fli = fnBody(M, "fetchLiveImages");
truthy("the tile's slot is still patched directly", /liveimg_/.test(fli));
truthy("  and a row without one forces a redraw", /else changed = true;/.test(fli));
truthy("  which is what actually repaints", /if\(changed\) render\(\);/.test(fli));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
