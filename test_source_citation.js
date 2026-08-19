/* Every figure says where it came from.
 *
 * Orbit's brand agent cites every number it gives:
 *
 *     "DE 3P revenue EUR 124,312 MTD (Aug 1-19) vs EUR 198,450 last month full
 *      month -- source: get_brand_snapshot 2026-08-19, marketplace
 *      A1PA6795UKMFR9, 3P side."
 *
 * Our screens showed the figure and not the provenance, which is fine right up
 * until somebody asks why it does not match Seller Central -- and then the
 * first twenty minutes go on working out which feed, which dates, and how
 * stale it is. Amazon has two feeds that describe the same trade and they
 * disagree for days at a time.
 *
 * One component (Rule 12), on the screens whose numbers get questioned.
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
const ctx = {esc: s => String(s == null ? "" : s).replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))};
new Function("exports", "esc", read("static/js/pageui.js") +
             "\nexports.uiSource = uiSource;")(ctx, ctx.esc);
const uiSource = ctx.uiSource;

console.log("== it prints what it is given ==");
const h = uiSource([
  {k: "Source", v: "Amazon Finances"},
  {k: "Dates", v: "2026-08-01 → 2026-08-19"},
], "The Sales screen counts something else.");
truthy("the feed is named", /Amazon Finances/.test(h));
truthy("  and the dates", /2026-08-01/.test(h));
truthy("  and the note", /counts something else/.test(h));

console.log("\n== a blank is dropped, never printed as an em dash ==");
// "Marketplace: —" is worse than no line at all: it looks like a missing value
// rather than one that does not apply.
const h2 = uiSource([
  {k: "Account", v: "jack_uk"},
  {k: "Marketplace", v: ""},
  {k: "Currency", v: null},
  {k: "Basis", v: undefined},
]);
truthy("the value present is shown", /jack_uk/.test(h2));
check("  and the empty ones are not", /Marketplace|Currency|Basis/.test(h2), false);
check("nothing at all renders nothing", uiSource([]), "");
check("  and null is safe", uiSource(null), "");

console.log("\n== it escapes what it is handed ==");
const h3 = uiSource([{k: "Account", v: '<script>x</script>'}]);
check("no raw tag survives", /<script>/.test(h3), false);
truthy("  it is escaped instead", /&lt;script&gt;/.test(h3));

console.log("\n== it is on the screens whose numbers get questioned ==");
const FIN = read("static/js/finance.js");
truthy("Finance cites its source", /uiSource\(\[/.test(FIN));
truthy("  names the Finances feed", /listFinancialEvents/.test(FIN));
// THE most-asked question about either screen.
truthy("  and says why it will not match Sales",
       /counts units ORDERED/.test(FIN));

const RB = read("static/js/reimbursements.js");
truthy("Reimbursements cites its source", /uiSource\(\[/.test(RB));
truthy("  and says only SETTLED orders can be checked", /SETTLED/.test(RB));

const ST = read("static/js/stock.js");
truthy("the coverage tab cites its sources", /uiSource\(\[/.test(ST));
truthy("  naming both feeds", /Stock from/.test(ST) && /Sales from/.test(ST));
// The one claim on that screen a reader would not otherwise know.
truthy("  and that the pace counts in-stock days only",
       /only the days a product was IN STOCK/.test(ST));
truthy("  and that the history is ours, not Amazon's",
       /Amazon keeps no .*stock history/.test(ST));

console.log("\n== one component, not one per screen ==");
for(const f of ["static/js/finance.js", "static/js/reimbursements.js",
                "static/js/stock.js"]){
  check(f.split("/").pop() + " defines no citation renderer of its own",
        /function ui[A-Za-z]*Source/.test(read(f)), false);
}

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
