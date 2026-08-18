/* Image Studio: its own screen, and a brand choice that reaches the prompt.
 *
 *   "make the image studio as its own seperate page and let the user chose the
 *    brand name for its item, whether he wants the images to be unbranded
 *    (without brand name printed on it), or branded (any name he can type or
 *    select from the registered trademarks"
 *
 * WHY "BRANDED" IS A THIRD RULE AND NOT THE OPPOSITE OF UNBRANDED
 *
 * There were two logo rules and neither could do what was asked:
 *
 *   remove   erase whatever branding the photo has, blend the surface clean
 *   keep     reproduce the product's own logo faithfully
 *
 * "Branded" is remove-THEN-apply, in one instruction, because two passes over
 * the same surface is how a ghost of the old logo survives under the new one.
 * This is the app's actual business (CLAUDE.md Rule 1): brand new listings under
 * the owner's own names, built from a competitor's product data.
 *
 * WHAT THIS PINS
 *   1. the three modes produce three genuinely different instructions
 *   2. the older callers still get byte-identical behaviour
 *   3. the choice REACHES the server, not just the screen
 *   4. a name that is not the seller's is warned about, never silently printed
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK"
    : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const HTML = read("templates/dashboard.html");
const GEN  = read("static/js/genimage.js");
const PY   = read("routes/genimage_routes.py");
const SHELL = read("static/js/shell.js");

console.log("=== it is its own screen, not a dialog ===");
truthy("there is a section for it", /id="sec_imagestudio" class="wspanel"/.test(HTML));
truthy("  and a nav item", /data-sec="imagestudio"/.test(HTML));
truthy("  the shell shows it", /"imagestudio"/.test(SHELL));
truthy("  and calls its open hook", /imagestudioOnOpen/.test(SHELL));
// The modal is GONE. Leaving it would mean two elements owning #studiobody.
check("the old modal is gone", /id="imgstudio"/.test(HTML), false);
truthy("but the body everything renders into is unchanged",
       /id="studiobody"/.test(HTML));
// FIVE places opened it by hand. With the modal gone each would have been a
// silent no-op -- the studio never appearing, nothing thrown to say why.
// COMMENTS STRIPPED FIRST. The comment explaining why the modal went names the
// very call it replaced, so matching the raw source makes this fail on its own
// documentation -- a trap this suite has fallen into three times.
const strip = s => s.replace(/\/\*[\s\S]*?\*\//g, "")
                    .split("\n").map(l => l.replace(/\/\/.*$/, "")).join("\n");
const CODE = strip(GEN) + strip(read("static/js/asinresearch.js"))
           + strip(read("static/js/pastelisting.js"));
check("nothing still reaches for the modal element",
      /getElementById\("imgstudio"\)/.test(CODE), false);
truthy("they all go through one function instead", /function _studioShow/.test(GEN));
for(const f of ["static/js/asinresearch.js", "static/js/pastelisting.js"]){
  truthy("  " + f + " uses it", /_studioShow\(\)/.test(read(f)));
}
truthy("and there is a way back to Listings", /navTo\('listings'\)/.test(HTML));

console.log("\n=== the choice is on screen, all three at once ===");
truthy("a brand pane is drawn", /function brandPaneHTML/.test(GEN));
for(const mode of ["unbranded", "branded", "keep"]){
  truthy("  " + mode + " is offered", new RegExp('value="' + mode + '"').test(GEN));
}
truthy("the registered names are offered as one-tap chips",
       /_studioBrands\(\)/.test(GEN) && /brandchip/.test(GEN));
truthy("  read from the account's own brands", /CUR_ACCOUNT\.brands/.test(GEN));
// "any name he can type" -- a brand may be registered and not recorded here,
// and refusing it would be the app deciding what the seller owns.
truthy("  and any other name can be typed", /id="src_brand_name"/.test(GEN));
truthy("an account with no brand recorded is told why the list is empty",
       /no brand recorded/.test(GEN));

console.log("\n=== the choice REACHES the server ===");
// A control that changes nothing is worse than no control.
truthy("the run sends the mode", /brand_mode:\s*bmode/.test(GEN));
truthy("  and the name", /brand_name:\s*bname/.test(GEN));
truthy("the route reads the mode", /b\.get\("brand_mode"/.test(PY));
truthy("  and the name", /b\.get\("brand_name"/.test(PY));
truthy("  and reports back what it applied", /"brand_applied"/.test(PY));

console.log("\n=== the three rules are genuinely different ===");
truthy("there is one function that decides", /def _brand_rule\(/.test(PY));
const rule = PY.slice(PY.indexOf("def _brand_rule("));
// BRANDED must do BOTH halves, in one instruction.
truthy("branded erases the old marking first", /FIRST remove any existing brand/.test(rule));
truthy("  then prints the chosen name", /THEN print/.test(rule));
truthy("  following the surface, so it is not pasted over the photo",
       /curve, perspective, lighting/.test(rule));
truthy("  and leaves no ghost of the old marking",
       /no trace, outline or shadow/.test(rule));
// A main image may not carry invented graphics -- a printed brand NAME on the
// product is a product feature; a made-up logo is a compliance problem.
truthy("  without inventing a logo, mascot or emblem",
       /do NOT invent a graphic logo/.test(rule));
truthy("unbranded says so explicitly", /NO brand name at all/.test(rule));
truthy("keep reproduces the product's own", /_RULE_KEEP/.test(rule));

console.log("\n=== the older callers are untouched ===");
// Every existing caller sends source/preserve_logo and no mode. Changing what
// they produce would have been a silent behaviour change across the app.
truthy("no mode falls back to the original pair",
       /No explicit mode: the original behaviour/.test(PY));
truthy("  and the two original texts are still the ones used",
       /_RULE_REMOVE if remove_logo else _RULE_KEEP/.test(PY));

console.log("\n=== a name that is not yours is a trademark problem ===");
// Warned, never blocked: it may be theirs and simply not recorded here.
truthy("a typed name is checked against the account's own",
       /function studioBrandTyped/.test(GEN));
truthy("  and warns when it is not one of them",
       /trademark infringement/.test(GEN));
truthy("  saying Amazon removes the listing rather than asking",
       // The sentence is built by concatenation, so it is matched in the half
       // that survives the join rather than across it.
       /removes the listing rather/.test(GEN));
check("  but it does not refuse to generate",
      /return;\s*\/\/ blocked/.test(GEN), false);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
