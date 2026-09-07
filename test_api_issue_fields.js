/* A field Amazon names in its structured reply gets a BOX, not just a banner.
 *
 *     "amazon rejected size but there is no such field"
 *
 * Amazon refused a MOP listing with "'Size' is required but missing", code
 * 90220, naming `size` in attributeNames. The banner showed it, the chip showed
 * it, the row tinted red -- and there was no box to type it into, so the only
 * thing the reader could do was read the complaint.
 *
 * WHY IT HAPPENED. The list of fields to draw was
 *
 *     reqList  UNION  parseFlagged(r.notes)
 *
 * reqList is the schema's TOP-LEVEL required array. Measured against Amazon's
 * own MOP schema for the UK: 113 properties, and the required array holds SIX
 * -- brand, bullet_point, country_of_origin, item_name, product_description,
 * supplier_declared_dg_hz_regulation. `size` is a real property of that schema
 * and is not in that six. parseFlagged reads Amazon's PROSE out of the Notes
 * column. So a field named only in the structured `issues` array reached the
 * screen as a warning and never as an input.
 *
 * Amazon's required array cannot be the whole story: `size` is conditionally
 * required for this type and Amazon says so only when it refuses. The
 * structured reply is the authority on what it actually wants, and the app
 * already keeps it -- listing/api_issues.py parses it into
 * {code, severity, message, fields} for exactly this purpose.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = "D:\\AltaScraper";

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(62) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                              + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

const AF = fs.readFileSync(path.join(ROOT, "static/js/autofix.js"), "utf8");

console.log("=== the structured reply feeds the field list ===");
truthy("api_issues is read where the list is built",
       /const _apiFlagged=\{\};/.test(AF));
truthy("  and joins the union", /\.\.\.Object\.keys\(_apiFlagged\)/.test(AF));
// RULE 4: never render a name Amazon's prose yielded without checking it
// against the schema. isRealAttr is that check, and it must gate this too.
truthy("  every name is validated against the schema first",
       /if\(!k \|\| !isRealAttr\(k\)\) return;/.test(AF));
// A WARNING is Amazon ACCEPTING the listing and remarking on it. Turning those
// into required-looking boxes would star fields nothing is blocking.
truthy("  only ERROR issues create a field",
       /severity\)\|\|""\)\.toUpperCase\(\)!=="ERROR"\) return;/.test(AF));
truthy("  and Amazon's own words become the hint",
       /_apiFlagged\[k\]=String\(\(i&&i\.message\)/.test(AF));
// The prose parser stays: a listing whose refusal predates the structured
// column still has its fields in Notes, and dropping that would lose them.
truthy("the prose parser is kept as well",
       /const flagged=parseFlagged\(r\.notes, isRealAttr, _plainNotes\);/.test(AF));

console.log("\n=== the behaviour, run ===");
// The union and the filter, lifted out and exercised against Amazon's real
// reply shape for this listing.
function build(reqList, allAttrs, apiIssues, have){
  const a = have || {};
  const isRealAttr = f => allAttrs.indexOf(String(f).split(".")[0]) >= 0;
  const flagged = {};
  const _apiFlagged = {};
  ((apiIssues && apiIssues.issues) || []).forEach(function(i){
    if(String((i && i.severity) || "").toUpperCase() !== "ERROR") return;
    ((i && i.fields) || []).forEach(function(f){
      const k = String(f || "").trim();
      if(!k || !isRealAttr(k)) return;
      if(!_apiFlagged[k]) _apiFlagged[k] = String((i && i.message) || "").trim()
                                          || "Amazon asked for this";
    });
  });
  Object.keys(_apiFlagged).forEach(k => { if(!flagged[k]) flagged[k] = _apiFlagged[k]; });
  const reqUnion = new Set([...reqList, ...Object.keys(flagged),
                            ...Object.keys(_apiFlagged)]);
  return [...reqUnion].filter(k => {
    if(!k) return false;
    if(k in a) return false;
    if(flagged[k]) return true;
    return true;
  }).sort();
}

// Amazon's real MOP schema for the UK, measured 7 Sep 2026.
const MOP_REQ = ["brand", "bullet_point", "country_of_origin", "item_name",
                 "product_description", "supplier_declared_dg_hz_regulation"];
const MOP_ATTRS = MOP_REQ.concat(["size", "package_size_name", "colour",
                                  "material", "item_weight"]);
// Amazon's real refusal, as listing/api_issues.parse() stores it.
const REFUSAL = {issues: [
  {code: "90220", severity: "ERROR", message: "'Size' is required but missing.",
   fields: ["size"]},
]};

check("`size` now appears in the fields to draw",
      build(MOP_REQ, MOP_ATTRS, REFUSAL, {}).indexOf("size") >= 0, true);
// THE OLD BEHAVIOUR, for contrast: with no structured reply it is absent.
check("  and was absent without the structured reply",
      build(MOP_REQ, MOP_ATTRS, null, {}).indexOf("size") >= 0, false);
check("  the schema's own required fields are still there",
      build(MOP_REQ, MOP_ATTRS, REFUSAL, {}).indexOf("brand") >= 0, true);

// A NAME NOT IN THE SCHEMA STILL CANNOT DRAW A BOX. This is the phantom-field
// guard the app already had -- Amazon prose once yielded "The" and "Your" as
// field names -- and routing structured names through the same check keeps it.
const PHANTOM = {issues: [
  {code: "1", severity: "ERROR", message: "Nonsense", fields: ["not_a_field"]},
]};
check("an unknown name is refused a box",
      build(MOP_REQ, MOP_ATTRS, PHANTOM, {}).indexOf("not_a_field") >= 0, false);

// A WARNING is not a blocker.
const WARN = {issues: [
  {code: "2", severity: "WARNING", message: "Consider adding a colour",
   fields: ["colour"]},
]};
check("a WARNING does not create a required box",
      build(MOP_REQ, MOP_ATTRS, WARN, {}).indexOf("colour") >= 0, false);

// A field that already HAS a value needs no box.
check("a field already filled is not asked for again",
      build(MOP_REQ, MOP_ATTRS, REFUSAL, {size: "One Size"}).indexOf("size") >= 0,
      false);

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
