/* The Campaign Analytics search bar, and the one matcher behind it.
 *
 *     "THE SEARCH CAMPAIGNS BAR IS NOT WORKING, i want to search campaigns,
 *      the search bar should use the same logic as amazon uses for the search
 *      bar of campaign manager"
 *
 * THREE FAULTS, all measured on the running screen against this account's 254
 * campaigns before anything was changed:
 *
 *   only the first letter landed -- ppccFilter calls ppccRender(), which
 *     rebuilds the whole of #ppcc_body. The input it drew had no value= and was
 *     a NEW element, so the text and the FOCUS both went. Typing "auto" left
 *     PPCC.q === "a" and the box empty; the u, t and o were delivered to the
 *     page, not to a box.
 *   "  auto  " matched 0 of 254 -- lowercased, never trimmed.
 *   "auto ceiling" matched 0 -- a bare indexOf on the whole name, and the names
 *     are underscore-joined segments (SP_AUTO_CeilingFan_DISC), so two words can
 *     never be one run of characters.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const HERE = __dirname;
let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(60) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
const read = (...p) => fs.readFileSync(path.join(HERE, ...p), "utf8");

// The matcher runs for real, not by reading its source.
const TS = read("static", "js", "textsearch.js");
const ctx = {module: {exports: {}}, console};
vm.createContext(ctx);
vm.runInContext(TS, ctx);
const match = ctx.altaSearchMatch;

// Real names, copied off the running screen.
const NAMES = [
  "SP_AUTO_CeilingFan_DISC",
  "SP_CeilingFan_CATCH ALL_Coverage",
  "SP_NB_CeilingFan_Phrase_DISC",
  "SP_NB_FoldingTrayTable_Exact_GROW",
  "SP_AUTO_ClothesAirer_DISC",
  "SP_MixerTapHoseConnector_CATCH ALL_Coverage",
];
const hits = (q) => NAMES.filter((n) => match(q, [n]));

console.log("=== the matcher, against real campaign names ===");
check("a plain word", hits("auto").length, 2);
check("  case does not matter", hits("AUTO").length, 2);
// TRIMMED. This found nothing at all before -- the spaces were part of the
// needle, and they arrive by pasting.
check("  and it is trimmed", hits("  auto  ").length, 2);
// THE ONE THAT MATTERS. Underscore-joined names cannot be searched any other
// way: "auto ceiling" is not a run of characters in any name that exists.
check("two words, both present", hits("auto ceiling"), ["SP_AUTO_CeilingFan_DISC"]);
check("  and the order does not matter", hits("ceiling auto"), ["SP_AUTO_CeilingFan_DISC"]);
check("  every word must be there, not just one",
      hits("auto foldingtraytable").length, 0);
check("inside a word still matches", hits("ceilingfan").length, 3);
check("nothing matches nothing", hits("zzznothing").length, 0);
// An empty query is not a filter -- callers use this without special-casing it.
check("an empty query keeps everything", hits("").length, NAMES.length);
check("  and so does whitespace", hits("   ").length, NAMES.length);

console.log("\n=== a pasted list: any line, and commas too ===");
check("two names on two lines",
      hits("SP_AUTO_CeilingFan_DISC\nSP_AUTO_ClothesAirer_DISC").length, 2);
check("  comma separated", hits("SP_AUTO_CeilingFan_DISC, SP_AUTO_ClothesAirer_DISC").length, 2);
check("  and a blank line is not a match-everything",
      hits("SP_AUTO_CeilingFan_DISC\n\n").length, 1);

console.log("\n=== two fields do not fuse into one word ===");
// The separator's real job, and the only case it can affect: a SINGLE token.
// Joined with a space these two would read "auto matic" -- joined with nothing
// they would read "automatic" and a search for it would find a campaign that
// contains no such word. Nothing can contain the separator, so it cannot.
check("a word made by joining two fields is not a match",
      match("automatic", ["auto", "matic"]), false);
truthy("  while a real word in one field still is",
       match("automatic", ["SP_AUTOMATIC_Thing", "enabled"]));
// A MULTI-WORD query is deliberately allowed to span fields -- that is how
// "ceiling paused" narrows to paused CeilingFan campaigns, and it is the whole
// point of searching the state alongside the name.
truthy("every-word may span fields, which is the point",
       match("ceiling paused", ["SP_AUTO_CeilingFan_DISC", "paused"]));
truthy("  so the state narrows the list without reaching for a pill",
       match("clothesairer paused", ["SP_AUTO_ClothesAirer_DISC", "paused"]));

console.log("\n=== the campaigns bar uses it, and survives its own redraw ===");
const PC = read("static", "js", "ppccampaigns.js");
truthy("the filter goes through the shared matcher", PC.indexOf("altaSearchMatch(PPCC.q") >= 0);
truthy("  and the field list stays on this screen", PC.indexOf("r.name, r.campaignType") >= 0);
truthy("  with a fallback if textsearch.js did not load",
       PC.indexOf('typeof altaSearchMatch !== "function"') >= 0);
// value= is half the fix: without it the box comes back empty after the redraw.
truthy("the input carries its value", PC.indexOf('value="\' + _pEsc(PPCC.q) + \'"') >= 0);
truthy("  escaped by the one escaper this screen already had",
       PC.indexOf("_pEsc(PPCC.q)") >= 0);
// FOCUS IS THE OTHER HALF. Without it the second keystroke goes to the page.
truthy("the cursor is put back after the redraw", PC.indexOf("function ppccKeepFocus") >= 0);
truthy("  and ppccRender calls it", PC.indexOf("ppccKeepFocus();") >= 0);
truthy("  at the caret, not at the start", PC.indexOf("setSelectionRange(n, n)") >= 0);
// Only when it was already focused -- a filter pill re-renders too, and
// stealing the cursor into the search box then would be its own bug.
truthy("  and only when the box had the cursor", PC.indexOf("PPCC._focus") >= 0);
// The raw text is stored now: it is what goes back into the box.
truthy("the raw text is kept, not a lowercased copy",
       PC.indexOf("PPCC.q = (v == null ? \"\" : String(v));") >= 0);

console.log("\n=== one matcher, not two (Rule 12) ===");
const LS = read("static", "js", "listings.js");
truthy("the listings search asks the same function",
       LS.indexOf("altaSearchMatch(q, fields)") >= 0);
truthy("  and keeps its own field list where its tests read it",
       LS.indexOf("r.sku, r.asin, r.competitor_asin, own") >= 0);
truthy("  with the old behaviour as a fallback",
       LS.indexOf('typeof altaSearchMatch === "function"') >= 0);
const HTML = read("templates", "dashboard.html");
truthy("textsearch.js is loaded", HTML.indexOf("static/js/textsearch.js") >= 0);
truthy("  before listings.js, which calls it",
       HTML.indexOf("static/js/textsearch.js") < HTML.indexOf("static/js/listings.js"));

/* MEASURED IN CHROME on Campaign Analytics, 254 campaigns:
 *
 *   BEFORE   typed "auto" -> box "", focus lost after 'a', PPCC.q "a", 262 rows
 *   AFTER    typed "auto" -> box "auto", focused throughout,
 *                            262 -> 85 -> 51 rows as the letters land
 *            "auto ceiling" -> 1 campaign, "ceiling auto" -> the same 1
 *            "  auto  "     -> 43 (was 0)
 *            "zzznothing"   -> 0
 *   No page errors.
 */
console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
