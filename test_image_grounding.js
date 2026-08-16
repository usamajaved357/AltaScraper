/* An image is designed from the LISTING, not from a photograph and a title.
 *
 * "create secondary images for 5 items and see if they allign with the content
 *  used in the listing copy ... the images should reflect accurately what is
 *  present in the item details and secondary images should not differ with each
 *  other"
 *
 * Four separate places dropped the listing on the floor, all in the same
 * direction, so every image was designed blind:
 *
 *   the Studio put the sku on the job WRAPPER and the worker dispatches the
 *   PAYLOAD, so _listing_for() got nothing -- for every kind of image;
 *
 *   studioStrategize sent product_image and title only, so the CONCEPTS were
 *   invented before the copy was read;
 *
 *   listing_facts() carried the bullets, description, size, material and colour
 *   -- everything except included_components, the one field that decides how
 *   many of each thing may appear;
 *
 *   genimage_from_concept never asked for the listing at all, while telling the
 *   model to reproduce the reference photo EXACTLY -- which reproduces objects
 *   that are not being sold.
 *
 * Measured on the hammock (four pieces, one carabiner): concepts said "all five
 * components" and described a strap that is not in the kit. After: "all four kit
 * components", and a generated flat-lay headed "4-Piece Complete Kit" with every
 * callout naming the object it touches.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(68) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const R = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const DASH = R("dashboard.py");
const AI = R("domain/ai_providers.py");
const GJS = R("static/js/genimage.js");
const GR = R("routes/genimage_routes.py");

console.log("=== the sku reaches every image endpoint ===");
truthy("the worker stamps it onto the payload",
       /if job\.get\("sku"\) and not payload\.get\("sku"\):/.test(DASH));
truthy("  once, rather than in each caller",
       (DASH.match(/payload\["sku"\] = job\.get\("sku"\)/g) || []).length === 1);
truthy("the strategist is told which listing it is designing for",
       /sku:sku, listing:\(it\|\|null\)/.test(GJS));

console.log("\n=== what is in the box travels with the listing ===");
truthy("listing_facts includes the contents", /WHAT IS IN THE BOX/.test(AI));
truthy("  labelled as the complete list",
       /the complete list -- show nothing beyond/.test(AI));
truthy("  read from the attributes", /included_components/.test(AI));

console.log("\n=== the strategist gets the listing, not just a look at the photo ===");
// product_spec is a VISION summary; on five real products it mentioned the
// contents in none of them, so the concepts counted objects in the supplier photo.
truthy("the facts go in as their own block", /THE LISTING ITSELF SAYS THIS/.test(AI));
truthy("  outranking the photograph and the description",
       /IT OUTRANKS BOTH THE PHOTOGRAPH/.test(AI));
truthy("  and the route passes the listing through",
       /listing=_listing_for\(b\)\)/.test(GR));

console.log("\n=== a set may not disagree with itself ===");
truthy("every concept shows the same physical product",
       /EVERY CONCEPT SHOWS THE SAME PHYSICAL PRODUCT/.test(AI));
truthy("  same quantities across the set",
       /every other\s*"\s*"?concept that shows it shows the same quantity/.test(AI)
       || /shows the same quantity/.test(AI));
truthy("  nothing that is not supplied, not even as a prop",
       /not as a prop, not for scale/.test(AI));
truthy("  and silence means one", /Where the details are silent "\s*"?about a quantity, show one/.test(AI)
       || /about a quantity, show one/.test(AI));

console.log("\n=== the image step knows it too ===");
truthy("the brief carries the listing facts", /WHAT THIS PRODUCT ACTUALLY IS -- from the listing itself/.test(GR));
truthy("  and outranks the reference on contents", /OUTRANKS the reference photograph on contents/.test(GR));
truthy("  copy the appearance, never the object count",
       /copy the product's "\s*"?appearance from it, never its object count/.test(GR)
       || /never its object count/.test(GR));
truthy("a callout must name what it points at",
       /every label must name the/.test(GR) && /object its line actually touches/.test(GR));

console.log("\n=== and none of it is written for one product ===");
// "keep in mind that the rules of image gen are universal for all type of items"
const blocks = [
  AI.slice(AI.indexOf("EVERY CONCEPT SHOWS THE SAME PHYSICAL PRODUCT"),
           AI.indexOf("EVERY CONCEPT SHOWS THE SAME PHYSICAL PRODUCT") + 1600),
  GR.slice(GR.indexOf("WHAT THIS PRODUCT ACTUALLY IS"),
           GR.indexOf("WHAT THIS PRODUCT ACTUALLY IS") + 1400),
];
["hammock","carabiner","grease","battery","torch","yoga"].forEach(function(w){
  truthy("  no mention of " + w,
         blocks.every(b => b.toLowerCase().indexOf(w) < 0));
});

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
