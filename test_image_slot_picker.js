/* The slot is chosen ON the tile, before you commit to sending.
 *
 * "i should have a button under the image like a dropdown menu which asks me to
 *  select the image type, the pt1, pt2, pt3 or what other, the default selected
 *  option should be pt1 for first image which is secondary image 1 and next
 *  image should have the selected option as pt2 and so on. and user should be
 *  allowed to change the selected option and then send to amazon for upload
 *  with a different button"
 *
 * It used to be one "Send as..." button that read the listing and THEN asked,
 * per image, every time. This is the second report about that control -- the
 * first was "i do not have option here to send an image as pt1 or pt2 or pt3",
 * written by someone looking straight at it. A choice you cannot see until
 * after you commit to making it is not a choice anybody finds.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const LIB = fs.readFileSync("D:/AltaScraper/static/js/listingimages.js", "utf8");

/* Brace-matched body of a named function, so "the tile offers it" can be told
 * apart from "the file contains it somewhere". */
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

console.log("=== every tile carries its own dropdown and its own send button ===");
const draw = fnBody(LIB, "_ilDraw");
truthy("the tile draws a slot picker", /_ilTileSlotPicker\(idx, f, isMain, ptIndex\)/.test(draw));
const picker = fnBody(LIB, "_ilTileSlotPicker");
truthy("  which is a <select>", /<select class="ed" id="il_slot_/.test(picker));
truthy("  listing every slot the product type has", /\(IMGLIB\.slots \|\| \[\]\)\.forEach/.test(picker));
truthy("  and a SEPARATE button that sends", /onclick="ilSendTile\(/.test(picker));
truthy("  which reads whatever the dropdown says at the time",
       /const sel = document\.getElementById\("il_slot_" \+ idx\)/.test(fnBody(LIB, "ilSendTile")));
truthy("the old click-then-ask flow is gone", !/ilPushThis|_ilSlotPicker\(/.test(LIB));
truthy("  and nothing still calls its helper", !/ilSlotCancel\(\)/.test(LIB));

console.log("\n=== the defaults run PT1, PT2, PT3 ... in the order shown ===");
truthy("tiles are numbered across every group", /let tileNo = 0, ptNo = 0;/.test(draw));
truthy("  the main image does not consume a PT number",
       /const ptIndex = isMain \? 0 : \(\+\+ptNo\);/.test(draw));
const def = fnBody(LIB, "_ilDefaultSlot");
truthy("the main image defaults to the main slot",
       /if\(isMain && has\("main_product_image_locator"\)\) return "main_product_image_locator";/.test(def));
truthy("  everything else to its numbered PT",
       /const want = "other_product_image_locator_" \+ ptIndex;/.test(def));
truthy("more images than PT slots falls back to the LAST PT, not to main",
       /return pts\.length \? pts\[pts\.length - 1\]\.key : slots\[0\]\.key;/.test(def));

console.log("\n=== the user can still change it, and is warned about what they picked ===");
truthy("changing the dropdown updates the note", /onchange="ilSlotNote\(/.test(picker));
const note = fnBody(LIB, "ilSlotNote");
// Terse here, in full in the confirm dialog: on a live listing every gallery
// slot is occupied, so the long sentence appeared ten times over and stopped
// being read at all.
truthy("  an occupied slot says it will be replaced",
       /replaces what is in it now/.test(note));
truthy("  an empty one says that too", /empty/.test(note));
truthy("  and the full warning survives where it stops you",
       /This slot ALREADY has an image\. Sending replaces /.test(LIB)
       && /Amazon does not keep the old one/.test(LIB));
truthy("  and the slot's own help is shown", /_ilEsc\(s\.help \|\| ""\)/.test(note));
truthy("a secondary image cannot be set as MAIN",
       /_ilBlockedMain\(f\.group\)/.test(picker));
truthy("  the option is disabled rather than hidden",
       /\(no \? " disabled" : ""\)/.test(picker));
truthy("  and says why", /" — not allowed"/.test(picker));
// One definition of that rule, asked wherever the choice is offered (Rule 12).
truthy("the main-image rule is defined once",
       (LIB.match(/function _ilBlockedMain\(/g) || []).length === 1);
truthy("  and covers A+ module images too", /aplus/.test(fnBody(LIB, "_ilBlockedMain")));

console.log("\n=== the slots are read once, not once per image ===");
truthy("there is a single loader", /async function _ilEnsureSlots\(force\)/.test(LIB));
truthy("  it does not re-read what it already has",
       /if\(IMGLIB\.slots && !force\) return;/.test(fnBody(LIB, "_ilEnsureSlots")));
truthy("  nor run twice at once",
       /if\(IMGLIB\.slotsState === "loading"\) return;/.test(fnBody(LIB, "_ilEnsureSlots")));
truthy("it starts when the library opens", /_ilEnsureSlots\(\);/.test(fnBody(LIB, "openImageLibrary")));
truthy("  without blocking the grid",
       /Not awaited: the grid is usable/.test(LIB));

console.log("\n=== a listing with no slots says so instead of showing an empty box ===");
truthy("failure is a state, not a silence", /IMGLIB\.slotsState = "failed";/.test(LIB));
truthy("  offering a retry", /Slots unavailable — retry/.test(picker));
truthy("  and keeping Amazon's own words", /IMGLIB\.slotsErr = \(j && \(j\.error \|\| j\.note\)\)/.test(LIB));
truthy("redrawing does not throw you out of an open folder",
       /if\(document\.getElementById\("il_pushstatus"\)\) _ilDraw\(\);/.test(LIB));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
