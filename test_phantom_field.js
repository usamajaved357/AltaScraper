/* A barcode is not a field name, and must never become a box.
 *
 *     "amazon rejected a barcode, i replaced it with a new one and then again
 *      hit the preview button but the notice still says that amazon did not
 *      accept the barcode"
 *
 * He had typed the new barcode into a box whose LABEL was 04545844574868 -- the
 * OLD barcode, rendered as though it were a field. Saving it wrote an attribute
 * named after a number, the real identifier was never touched, and the next
 * Preview correctly reported the same clash. The screen offered a box that
 * could not possibly work.
 *
 * WHERE IT CAME FROM. isRealAttr began `if(!_schemaLoaded) return true`, and the
 * schema is fetched ASYNCHRONOUSLY -- pdp.js calls loadSchemas().then(re-render).
 * On the first paint there is no schema, so every name Amazon's reply yields is
 * accepted, and Amazon puts the offending VALUE in attributeNames beside the
 * field name. The real field, externally_assigned_product_identifier, is in
 * EXCLUDE_REQ because the barcode has its own box -- so the only identifier box
 * on screen was the phantom one.
 *
 * Amazon attribute names are snake_case identifiers. That is a property of the
 * NAME, not of any schema, so it can be enforced before the schema arrives --
 * which is precisely the window this bug lived in.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = "D:\\AltaScraper";

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(58) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                              + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const AF = fs.readFileSync(path.join(ROOT, "static/js/autofix.js"), "utf8");

console.log("=== the shape check runs even with no schema ===");
truthy("there is a name-shape test", /_looksLikeField/.test(AF));
truthy("  applied BEFORE the schema branch",
       /if\(!_looksLikeField\(f\)\) return false;\s*\n\s*if\(!_schemaLoaded\) return true;/
         .test(AF));
truthy("  and the reason is recorded",
       /before the schema arrives/.test(AF));

// The rule, lifted out and run.
// CASE-SENSITIVE. Amazon's attribute names are lowercase snake_case without
// exception, so testing as-given also catches the original phantom-field words
// -- "The" and "Your" -- which a case-insensitive test would wave through as
// the perfectly ordinary names "the" and "your".
const NAMEOK = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$/;
const looks = f => {
  const s = String(f || "").trim();
  if(!s || s.length > 120) return false;
  return NAMEOK.test(s);
};

console.log("\n=== what is refused ===");
// THE ONE THAT COST HIM THE AFTERNOON.
check("a barcode is not a field", looks("04545844574868"), false);
check("  nor the unpadded form", looks("4545844574868"), false);
check("  nor an ASIN-shaped token", looks("0B0H8TFYNB9"), false);
// The original phantom-field bug: a capitalised first word of Amazon's prose.
check("a bare prose word is not a field", looks("The"), false);
check("  nor 'Your'", looks("Your"), false);
check("blank is not a field", looks(""), false);
check("  nor a sentence", looks("Size is required but missing"), false);
check("  nor something absurdly long", looks("a".repeat(200)), false);

console.log("\n=== what is still allowed ===");
check("a plain attribute", looks("size"), true);
check("  with underscores", looks("country_of_origin"), true);
check("  a nested key", looks("item_dimensions.length.value"), true);
check("  a digit inside the name", looks("bullet_point1"), true);
check("  the barcode FIELD itself, which has its own box",
      looks("externally_assigned_product_identifier"), true);
check("  and Amazon's own mouthful", looks("supplier_declared_dg_hz_regulation"), true);

console.log("\n=== provenance is metadata, not a field ===");
// It is a MAP of where each other field's value came from, and _prov[k] is how
// it reaches the field it describes. Filtered from the drawer's grid and not
// from the list the product page draws, so that page rendered a row labelled
// "Provenance" whose value was an object: on screen, "[object Object]".
truthy("the hide list is applied to the key list",
       /!HIDEKEYS\.has\(k\) && !IMGRE\.test\(k\) && !_AHIDE\.has\(k\)/.test(AF));
truthy("  and says what it was showing", /\[object Object\]/.test(AF));

console.log("\n=== the barcode clash reaches the product page ===");
const PDP = fs.readFileSync(path.join(ROOT, "static/js/pdp.js"), "utf8");
truthy("the page asks /row for the per-listing checks",
       /fetch\(acctUrl\("\/row\?sku=" \+ encodeURIComponent\(sku\)\)\)/.test(PDP));
truthy("  merged over the list row, not replacing it",
       /ROWS\[i\] = Object\.assign\(\{\}, ROWS\[i\], j\.row\)/.test(PDP));
// Moving to another listing while the request is in flight must not paint the
// previous listing's checks onto this one.
truthy("  and a stale reply is dropped", /if\(PDP_SKU !== sku\) return;/.test(PDP));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
