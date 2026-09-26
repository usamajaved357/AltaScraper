// lsCheckStates (static/js/liststatus.js): the four verdicts the PDP rail and
// the Safety & Compliance badges both read (the owner's PDP redesign, 26 Sep
// 2026) -- and the Restricted count that was always 0.
//
// THE BUG. The rail tested the LENGTH of r.restricted's `matched`, but `matched`
// is a boolean (listing/restricted.py "matched": bool(matches); the same for
// r.viability in listing/sourcing_viability.py). A boolean has no length, so a
// restricted product's light never turned red from its own verdict, and the
// count beside it was always 0. The lists are `matches` and `risks`.
//
// Run: node test_check_states.js
const fs = require("fs");
let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
const LS = fs.readFileSync("static/js/liststatus.js", "utf8");
const F = new Function(LS + "\nreturn {lsCheckStates, lsRestrictedHits, lsViabilityHits};")();

console.log("=== the row's own verdicts are counted from their lists ===");
const restricted = {restricted: {matched: true, matches: [{tier: "GATED"}, {tier: "GATED"}]}};
check("two restricted matches -> 2", F.lsRestrictedHits(restricted), 2);
check("  and the light is red with the count",
      [F.lsCheckStates(restricted).restricted.tone, F.lsCheckStates(restricted).restricted.n], ["bad", 2]);
const docs = {viability: {matched: true, risks: [{risk: "HIGH"}]}};
check("one document demand -> amber, 1",
      [F.lsCheckStates(docs).compliance.tone, F.lsCheckStates(docs).compliance.n], ["warn", 1]);
check("a clean row -> green everywhere, Amazon not asked yet",
      ["restricted", "compliance", "claims", "amazon"].map(k => F.lsCheckStates({})[k].tone),
      ["ok", "ok", "ok", "info"]);
check("matched:false is not a hit", F.lsRestrictedHits({restricted: {matched: false, matches: []}}), 0);

console.log("\n=== Amazon's own answer ===");
const refused = {api_issues: {issues: [{severity: "ERROR"}, {severity: "ERROR"}]}};
check("two errors -> red, 2 errors",
      [F.lsCheckStates(refused).amazon.tone, F.lsCheckStates(refused).amazon.errors], ["bad", 2]);
check("previewed and clean -> green",
      F.lsCheckStates({api_issues: {issues: []}}).amazon.tone, "ok");
const clash = {identifier: {clash: [{live: false}]}};
check("a barcode on a draft -> amber, named",
      [F.lsCheckStates(clash).amazon.tone, F.lsCheckStates(clash).amazon.detail], ["warn", "barcode clash"]);

console.log("\n=== nothing reads .matched.length any more ===");
const JS = ["listings.js", "pdp.js", "listrow_detailed.js", "liststatus.js"]
  .map(f => fs.readFileSync("static/js/" + f, "utf8")).join("\n");
check("no .matched.length anywhere", /\.matched\.length/.test(JS), false);

console.log("\n" + (fails ? fails + " FAILED" : "all passed"));
process.exit(fails ? 1 : 0);
