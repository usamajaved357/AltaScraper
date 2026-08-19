/* Amazon's rejections, in language a person can act on.
 *
 *     "when amazon is rejecting something or there is an error i should be able
 *      to see what is it and also i should be able to understand it"
 *
 * Every message below is VERBATIM from the app's own database -- 97 Amazon
 * lines across every account, pulled out and bucketed by shape before a single
 * pattern was written (CLAUDE.md Rule 4: build the fix from what Amazon really
 * says). Five patterns already existed and read 86 of the 97. The six shapes
 * they could not read are the ones added here.
 *
 * The raw text is NEVER discarded -- it stays under a "Show original Amazon
 * message" toggle. The translation decides what you read FIRST, not what you
 * are allowed to see.
 */
"use strict";
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const read = p => fs.readFileSync("D:/AltaScraper/" + p, "utf8");
const g = {};
new Function("window", read("static/js/amazon_errors.js"))(g);
const tr = g.translateAmazonError;
const render = g.renderAmazonErrors;

// Verbatim, from the database. Curly quotes included -- they are Amazon's.
const REAL = {
  not_applicable:
    "included_components You submitted an attribute Included Components that does not belong or is no longer applicable to the product type you were trying to list. We are ignoring the value and processing your submission to ensure a smoother listing experience.",
  too_few_decimals:
    "item_dimensions_fraction Value '10.' for attribute 'Overall Height Derived' has too few decimal places. It has 0 decimal places but the minimum allowed is '1'.",
  too_few_decimals_2:
    "item_dimensions_fraction Value '350.' for attribute 'Item Dimensions Fraction Length' has too few decimal places. It has 0 decimal places but the minimum allowed is '1'.",
  provided_invalid:
    "item_display_dimensions The provided value for \u2018Item Display Width\u2019 is invalid",
  provided_invalid_2:
    "maximum_speed The provided value for \u2018Maximum Speed\u2019 is invalid",
  linked_elsewhere:
    "04545944574867 Your bar code 04545944574867 is already linked to product B0H8SYL36V which seems different to the product you are trying to list. If your bar code is correct, contact Selling Partner Support to raise a dispute.",
  under_review:
    "We are reviewing this listing to determine if any additional information is required. Please allow up to 48 hours for this process to complete. You will be notified here if your action is needed, otherwise the listing will be published.",
  not_enough_values:
    "item_package_dimensions The field 'width.unit' for the attribute 'Package Width Unit' does not have enough values. The required minimum is '1' value(s).",
  required_missing:
    "size 'Size' is required but missing.",
  not_in_catalogue:
    "Your offer to the SKU cannot be added because the product is not in the catalogue. Check your submission data to see if there are any other errors",
};

console.log("== every real message is translated ==");
Object.keys(REAL).forEach(k => {
  const r = tr(REAL[k], {});
  truthy(k + " is understood", r.matched);
});

console.log("\n== and each one is told the RIGHT thing ==");
// A wrong explanation is worse than none, so the id is pinned per shape.
check("a not-applicable attribute", tr(REAL.not_applicable, {}).id, "attr_not_applicable");
check("  and it says no action is needed",
      /no action needed/i.test(tr(REAL.not_applicable, {}).action), true);

const dec = tr(REAL.too_few_decimals, {});
check("too few decimal places", dec.id, "too_few_decimals");
truthy("  it quotes the value Amazon refused", /10\./.test(dec.plain));
// '10.' is a trailing dot with nothing after it -- a badly trimmed number, not
// something anybody typed. Saying so is the whole point.
truthy("  and says the value was trimmed badly", /trimmed badly/i.test(dec.plain));
truthy("  the fix is to write it with a decimal", /10\.0/.test(dec.action));
truthy("  a well-formed whole number is NOT called malformed",
       !/trimmed badly/i.test(tr(
         "item_dimensions_fraction Value '10' for attribute 'X' has too few decimal places. It has 0 decimal places but the minimum allowed is '1'.", {}).plain));

const pv = tr(REAL.provided_invalid, {});
check("the provided value is invalid", pv.id, "provided_value_invalid");
truthy("  it names the sub-field from the curly quotes",
       /Item Display Width/.test(pv.plain));
truthy("  and the parent attribute", /item_display_dimensions/.test(pv.plain));
// Amazon does not say why, so neither should we.
truthy("  it admits Amazon gave no reason", /did not say why/i.test(pv.plain));

const bc = tr(REAL.linked_elsewhere, {});
check("a barcode linked to another product", bc.id, "barcode_linked_elsewhere");
truthy("  it names the barcode", /04545944574867/.test(bc.plain));
truthy("  and the ASIN it belongs to", /B0H8SYL36V/.test(bc.plain));
// Rule 1: never invent a barcode.
truthy("  and says never to invent one", /never invent/i.test(bc.action));

const ur = tr(REAL.under_review, {});
check("under review", ur.id, "under_review");
truthy("  it says this is NOT a rejection", /not a rejection/i.test(ur.plain));
truthy("  and that there is nothing to do", /nothing to do/i.test(ur.action));

console.log("\n== the raw text is always kept ==");
const out = render([REAL.too_few_decimals], REAL.too_few_decimals, {});
truthy("something was translated", out.matched);
truthy("  and the verbatim message is still there",
       out.html.indexOf("Show original Amazon message") >= 0);
truthy("  including Amazon's own wording", /too few decimal places/.test(out.html));

console.log("\n== an unknown message is shown, not swallowed ==");
const odd = render(["something Amazon has never said before"], "raw", {});
check("nothing pretended to match", odd.matched, false);
truthy("  but the text is still displayed",
       /something Amazon has never said before/.test(odd.html));

console.log("\n== the listing card uses the SAME translator ==");
const L = read("static/js/listings.js");
truthy("formatFindings calls renderAmazonErrors",
       /renderAmazonErrors\(_plain, body, _ctx\)/.test(L));
truthy("  it passes the row for barcode/product-type context",
       /formatFindings\(findings, r\)/.test(L));
truthy("  and falls back to the raw list when nothing matches",
       /if\(_t\.matched\) return _t\.html;/.test(L));
// The Preview and Submit panels were already using it; they must keep doing so.
for(const f of ["static/js/submit.js", "static/js/runqueue.js"]){
  truthy(f.split("/").pop() + " still uses it",
         read(f).indexOf("renderAmazonErrors(") >= 0);
}

console.log("\n== a broken pattern can never break the display ==");
g.AMZ_ERROR_PATTERNS.push({id: "boom", test: function(){ throw new Error("x"); },
                           build: function(){ return {}; }});
let threw = false;
try { tr("anything at all", {}); } catch(e){ threw = true; }
check("a throwing pattern is contained", threw, false);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
