/* One "Live on Amazon" group, and a total that counts what is under it.
 *
 * "i see the live on amazon section shows 43 total listings and 55 live
 *  listings on nestwell goods, also i dont like that separation of Live on
 *  Amazon - no draft in this app ... and Live on Amazon"
 *
 * THE COUNT. The Live view renders two things: the app's own rows that Amazon
 * confirmed live, and the catalogue entries with no app row. `total` was set to
 * the SECOND group only -- liveCount, the catalogue items left after the
 * matching ones were removed -- so it counted the tail and not the head. It
 * printed "TOTAL LISTINGS 43" directly above "LIVE 55": a total smaller than one
 * of its own parts, which is how it got noticed.
 *
 * THE SPLIT. Both sections were headed "Live on Amazon", the second with a
 * paragraph after it. To someone looking for their live listings they are one
 * thing. The difference is real, so it is still marked -- on the row that has
 * it -- but it is a fact about a listing, not a category of listing.
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

const L = fs.readFileSync("D:/AltaScraper/static/js/listings.js", "utf8");
const M = fs.readFileSync("D:/AltaScraper/static/js/miles_template.js", "utf8");

console.log("=== the total counts both halves of the live list ===");
truthy("the live app rows are worked out once and named",
       /const _liveAppRows = _tabRows\.filter\(/.test(L));
truthy("  and the total includes them",
       /total = _liveAppRows\.length \+ liveCount;/.test(L));
truthy("  it is no longer the catalogue remainder alone",
       !/if\(LIST_SOURCE==='live'\) total = liveCount;/.test(L));
// The two sets were built by filtering with the same predicate twice, and the
// count of it was then never taken -- which is how the rows went missing.
check("the predicate is not run twice to build the same two sets",
      (L.match(/_tabRows\.filter\(r=>isActuallyLive\(/g) || []).length, 1);

console.log("\n=== and the LIVE tile cannot exceed the total beside it ===");
truthy("in the live view they count the same set", /c\.LIVE = total;/.test(L));

console.log("\n=== one group, not two ===");
truthy("the two sub-captions are gone", !/const _amzSub/.test(M));
truthy("  including the one that was a paragraph",
       !/Price, images and optimisation still work; Sync brings the full listing in\.<\/div>/.test(M));
truthy("the list is drawn without them",
       /let liveHtml  = \(liveRows\.length \? listBlock\(liveRows\) : ""\)/.test(M));

console.log("\n=== the difference is still said, on the row that has it ===");
truthy("a catalogue-only listing is badged", /&gt;no draft<\/span>|>no draft<\/span>/.test(M));
truthy("  and the badge explains what it means",
       /this app holds no draft of it/.test(M));
truthy("  including that everything still works on it",
       /Price, images and optimisation all still work from here/.test(M));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
