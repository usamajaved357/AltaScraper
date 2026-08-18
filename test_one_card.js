/* One card design, one action row, and no button another feature already does.
 *
 *   "i see two types of cards style dont make them different make them same and
 *    also remove the unnecessary buttons from the cards as i know we have some
 *    features which does the things for which these buttons were introduced.
 *    live pulling live images from amazon, i believe the app automatically
 *    fetches fresh data now. so we dont need that button also check other
 *    buttons from this logic and delete the un necessary ones"
 *
 * The two designs were visible side by side in his screenshot 84: the drafts
 * cards drew a row of ICONS from rowActions(), and liveTile() in
 * miles_template.js wrote its own row of TEXT-labelled buttons by hand. Same
 * screen, same grid, two designs -- which is what always happens when one list
 * is drawn by two renderers that each build their own buttons.
 *
 * So the test that matters is not "do they look alike" but "is there only ONE
 * definition of the row". A shared function cannot drift; two hand-written rows
 * always will.
 */
const fs = require("fs");

let fails = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + got + " want=" + want));
}
function truthy(l, g) { check(l, !!g, true); }
function falsy(l, g) { check(l, !!g, false); }

const L = fs.readFileSync("D:/AltaScraper/static/js/listings.js", "utf8");
const M = fs.readFileSync("D:/AltaScraper/static/js/miles_template.js", "utf8");
// Both files explain the change in comments, using the very words these
// assertions look for. Strip them, or the test passes on the explanation.
const strip = s => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "")
                    .replace(/<!--[\s\S]*?-->/g, "");
const LC = strip(L), MC = strip(M);

console.log("=== one definition of the action row ===");
check("rowActions is defined once", (LC.match(/function rowActions\(/g) || []).length, 1);
truthy("the drafts card uses it", /class="tileacts">\$\{rowActions\(/.test(LC));
truthy("and so does the live tile now", /rowActions\(/.test(MC));
// The old hand-written row is what made them two designs.
falsy("liveTile no longer writes its own buttons",
      /ti-library-photo"><\/i> Library/.test(MC));
falsy("  nor its own Optimize", /ti-wand"><\/i> Optimize/.test(MC));
falsy("  nor its own Price", /ti-tag"><\/i> Price/.test(MC));
falsy("  nor its own Images", /ti-photo"><\/i> Images/.test(MC));

console.log("\n=== a catalogue tile is live, and says so explicitly ===");
// isAmazonLive() reads an app row. A tile straight from Amazon's catalogue has
// no app row, so without this it would silently lose every live-only button.
truthy("liveTile passes live:true", /\{live:\s*true\}/.test(MC));
truthy("rowActions accepts the override", /opts\.live === undefined/.test(LC));
truthy("  and still works it out for itself otherwise",
       /isAmazonLive\(r\)/.test(LC));

// THE FUNCTION BODY, taken from its own opening line to the next closing brace
// at column 0. Slicing at a comment marker does not work here: LC has had its
// comments removed, so the marker is not in it and indexOf returns -1, which
// silently made this "the rest of the file" and every count below meaningless.
const _rs = LC.indexOf("function rowActions(");
const _re = LC.indexOf("\n}", _rs);
const row = LC.slice(_rs, _re < 0 ? LC.length : _re);

console.log("\n=== the button Sync already does is gone ===");
falsy("no pull-live-images button on any card", /pullLiveRow\(/.test(row));
falsy("  and its icon went with it", /ti-cloud-download/.test(row));
// KEPT as a function: the drawer still offers it for one chosen listing, which
// is a different thing from repeating Sync on every row.
truthy("the function itself is kept", /async function pullLiveRow\(/.test(LC));
truthy("  and is still reachable from the drawer",
       /pullLiveRow\(/.test(LC.slice(LC.indexOf("suggestbtn"))));

console.log("\n=== every surviving button does something nothing else does ===");
// One button per job. If two of these ever call the same function, one of them
// is the next thing to delete.
const rowCalls = (row.match(/;(\w+)\(/g) || []).map(s => s.slice(1, -1))
  .filter(c => c !== "stopPropagation");
const dupes = rowCalls.filter((c, i) => rowCalls.indexOf(c) !== i);
check("no two buttons call the same thing", dupes.join(",") || "none", "none");
for (const fn of ["setStatus", "openStudioSingle", "openImageLibrary",
                  "openDrawer", "autoFixLoop", "optimizeLive", "priceEdit",
                  "tileMenu"]) {
  truthy("  " + fn + " has exactly one button", rowCalls.filter(c => c === fn).length === 1);
}

console.log("\n=== the live-only buttons stay live-only ===");
// Optimize and Price both act on a listing that exists on Amazon. Drawing them
// on a draft offers something that cannot work.
truthy("Optimize is behind the live check", /\$\{live \? `<button[\s\S]{0,200}optimizeLive/.test(row));
truthy("Price is too", /\$\{live \? `<button[\s\S]{0,200}priceEdit/.test(row));
truthy("and the Amazon link needs an ASIN as well as live",
       /\$\{live && r\.asin \?/.test(row));

console.log("\n" + fails + " failed");
process.exit(fails ? 1 : 0);
