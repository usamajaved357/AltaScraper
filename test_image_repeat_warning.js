/* Nobody sets out to make thirty-six images of one product.
 *
 *     "warn the user if he is creating the images for the same item second
 *      time. i see a user has created 36 images for the same item, i dont want
 *      that happen again"
 *
 * A warning existed. It guarded THREE of the five ways to start a generation --
 * and the two it missed were the ordinary ones: generating from the source
 * image, and generating concepts one at a time. Each click is small and nothing
 * ever said how many were already there, which is precisely how a number like
 * thirty-six is reached without anybody deciding to.
 *
 * Every path asks now, and the question is worth reading: how many exist, and
 * when the newest was made. "12 images" and "12 images, newest an hour ago" are
 * different situations, and the second is the one that runs away.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(60) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }

const G = fs.readFileSync("D:/AltaScraper/static/js/genimage.js", "utf8");

console.log("== every way in asks first ==");
// Five call sites, one definition.
const calls = (G.match(/confirmIfExisting\(/g) || []).length;
check("the check is defined once and called from every path", calls >= 6, true);
truthy("  the source-image path asks",
       /if\(!await confirmIfExisting\(STUDIO\.skus, "images"\)\) return;\s*\n\s*if\(total>4/.test(G));
truthy("  generating one concept asks",
       /async function studioGenConcept\(i\)\{[\s\S]{0,400}?confirmIfExisting/.test(G));
truthy("  generating all concepts asks",
       /async function studioGenAllConcepts\(auto\)\{[\s\S]{0,400}?confirmIfExisting/.test(G));
// Those two had to become async to be able to await it.
truthy("  and both were made async to do it",
       /async function studioGenConcept/.test(G)
       && /async function studioGenAllConcepts/.test(G));

console.log("\n== even when the batch is small ==");
// The old paid-call confirm only fired above four. A single generate, clicked
// nine times, never asked anything at all.
truthy("the existing-images question comes BEFORE the >4 paid-call one",
       G.indexOf('confirmIfExisting(STUDIO.skus, "images")) return;\n  if(total>4')
       < G.indexOf('This will generate "+total+" image(s)'));
truthy("  and it is not gated on the batch size",
       !/total>4 &&[\s\S]{0,60}confirmIfExisting/.test(G));

console.log("\n== the question says how many, and how recent ==");
truthy("it counts what is already there", /worst = Math\.max\(worst, n\)/.test(G));
truthy("  and leads with the number once it is silly",
       /worst >= 8/.test(G) && /already has " \+ worst/.test(G));
truthy("  it reads the newest timestamp", /f\.made_at > newest/.test(G));
truthy("  and says it in minutes, hours or days",
       /min ago/.test(G) && /h ago/.test(G) && /days ago/.test(G));

console.log("\n== and it is honest about what generating again does ==");
truthy("it does not replace anything", /does not replace the old ones/.test(G));
truthy("  nothing is deleted", /nothing is deleted/.test(G));
truthy("  each one costs", /paid call/.test(G));
truthy("  and somebody has to choose afterwards", /which of them to use/.test(G));

console.log("\n== one click can be many images, and it says how many ==");
//     "i suspect there is some issue with the app itself which iss generating
//      a large number of images like more than 20 on a single click"
//
// Correct. _conceptJobs is PRODUCTS × CONCEPTS -- the strategist returns 3
// ideas for a main image, 8 for secondary, 5 or 7 for A+. Three products with
// the secondary set is 3 × 8 = 24 images from one press, and the multiplication
// is the invisible part: the screen lists 8 ideas and never mentions the 3
// products they will be run against.
truthy("the job builder multiplies products by concepts",
       /STUDIO\.skus\.forEach\([\s\S]{0,200}?concepts\.forEach\(/.test(G));
truthy("  and the confirm spells the arithmetic out",
       /product.*× "\+concepts\.length\+" idea/.test(G));
// "Suggest & auto-generate" passed auto=true and skipped the paid-call confirm
// entirely. The user opted in to GENERATING, not to a number never shown.
check("auto no longer buys silence",
      /!auto && jobs\.length>4/.test(G), false);
truthy("  the count is confirmed however it was started",
       /if\(jobs\.length>4 && !confirm\(/.test(G));
truthy("  and the measurement is recorded beside it",
       /more than 20 on a single/.test(G));
// The other batch paths already showed their arithmetic; they must keep it.
truthy("the secondary path still shows its arithmetic",
       /product\(s\) × "\+roles\.length/.test(G));
truthy("  and the A\+ path too", /product\(s\) × "\+mods\.length/.test(G));

console.log("\n== the timestamp it relies on is actually served ==");
const M = fs.readFileSync("D:/AltaScraper/routes/media_routes.py", "utf8");
truthy("/media/list returns made_at", /"made_at": _made/.test(M));
truthy("  from the file's own mtime", /_made = int\(_st\.st_mtime\)/.test(M));
// Parsing the name would be blank for uploads; a column right for some images
// and empty for others is worse than a duller one that is always right.
truthy("  not parsed out of the filename",
       /not a timestamp parsed out of/.test(M));

console.log("\n" + fails + " failed");
process.exit(fails ? 1 : 0);
