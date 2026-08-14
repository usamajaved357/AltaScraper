// The Finance screen's own arithmetic: filters, the parent rollup, and the
// totals under a filtered table.
//
// The trap this exists for: with a filter on, the footer used to show the
// SERVER's whole-period totals. "Loss-making" with a healthy contribution
// underneath it is the most misleading arrangement this screen could produce.
"use strict";
const fs = require("fs");
const path = require("path");

let fails = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                    + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }

const src = fs.readFileSync(path.join(__dirname, "static/js/finance.js"), "utf8");

// Rows shaped as domain/contribution.by_product really returns them -- the three
// on jack_uk are real, the loss-maker and the family are added to exercise the
// paths the live account does not currently have.
const ROWS = [
  {asin: "B0H7N2Q5GG", title: "Bayonet Ceiling Fan", parent_asin: "",
   units: 13, revenue: 370.74, vat: 0, fees: 60.4, cogs: 196.3, refunds: 0,
   ad_spend: null, uncosted_units: 0, contribution: 78.76, margin_pct: 21.24},
  {asin: "B0H8PQBH55", title: "Weed Slasher", parent_asin: "",
   units: 1, revenue: 18.32, vat: 0, fees: 3.2, cogs: 10.99, refunds: 0,
   ad_spend: null, uncosted_units: 0, contribution: 4.14, margin_pct: 22.6},
  {asin: "B0H8SWCZ6G", title: "Pinch Bolt Set", parent_asin: "",
   units: 1, revenue: 13.33, vat: 0, fees: 2.1, cogs: 8.49, refunds: 0,
   ad_spend: null, uncosted_units: 0, contribution: -5.00, margin_pct: -37.5},
  {asin: "B0KID1", title: "Sock Small", parent_asin: "B0PARENT",
   units: 4, revenue: 40.00, vat: 0, fees: 6.0, cogs: 20.0, refunds: 0,
   ad_spend: null, uncosted_units: 0, contribution: 14.0, margin_pct: 35.0},
  {asin: "B0KID2", title: "Sock Large", parent_asin: "B0PARENT",
   units: 2, revenue: 20.00, vat: 0, fees: 3.0, cogs: 0, refunds: 0,
   ad_spend: null, uncosted_units: 2, contribution: null, margin_pct: null},
];

const harness = `
  ${src}
  const document = { getElementById: () => null };
  FIN.rows = ROWS;
  return {matching: _finMatching, rollup: _finRollup, totals: _finTotals, FIN: FIN};
`;
const api = new Function("ROWS", "jsArg", harness)(ROWS, s => JSON.stringify(s));

console.log("=== the filters ===");
check("Profitable", api.matching("profit").map(r => r.asin),
      ["B0H7N2Q5GG", "B0H8PQBH55", "B0KID1"]);
check("Loss-making", api.matching("loss").map(r => r.asin), ["B0H8SWCZ6G"]);
// A product with no contribution is its own answer. Counted as a loss it would
// fill "Loss-making" with products whose cost simply is not known, and someone
// would go and delist a product that is fine.
check("No contribution is its OWN bucket, not a loss",
      api.matching("blank").map(r => r.asin), ["B0KID2"]);
check("  the three buckets add up to everything",
      api.matching("profit").length + api.matching("loss").length
        + api.matching("blank").length, ROWS.length);
check("All", api.matching("all").length, 5);

console.log("\n=== rolled up to the parent ===");
const rolled = api.rollup(ROWS);
check("five products become four rows", rolled.length, 4);
const fam = rolled.filter(r => r.asin === "B0PARENT")[0];
truthy("the family exists", fam);
check("  its money adds up", [fam.units, fam.revenue, fam.fees], [6, 60, 9]);
// Averaging the children's 35% and (blank) would be meaningless; and a family
// holding one uncosted child cannot report a contribution at all.
check("  one child with no contribution withholds the FAMILY's",
      fam.contribution, null);
check("  so there is no margin to state either", fam.margin_pct, null);
truthy("  and it says how many children it holds", /2 children/.test(fam.title));
check("a product with no parent is NOT wrapped in a family of one",
      rolled.filter(r => r.asin === "B0H7N2Q5GG")[0].title, "Bayonet Ceiling Fan");

console.log("\n=== totals belong to what is on screen ===");
const all = api.totals(ROWS);
check("every row: contribution withheld because one is unknown",
      all.contribution, null);
const lossOnly = api.totals(api.matching("loss"));
check("Loss-making totals the LOSS, not the whole period", lossOnly.contribution, -5);
check("  and its margin is that loss over that revenue", lossOnly.margin_pct, -37.51);
const profitOnly = api.totals(api.matching("profit"));
check("Profitable totals only the profitable rows", profitOnly.contribution, 96.9);
check("  products counted", profitOnly.products, 3);
check("ad spend stays NULL rather than becoming a confident zero",
      profitOnly.ad_spend, null);

console.log("\n=== the period is stated, not assumed ===");
truthy("there are date presets", /7 days|30 days|90 days/.test(src));
truthy("  including this month and this quarter", /This month/.test(src) && /This quarter/.test(src));
truthy("picking a preset fills the date boxes", /fin_start/.test(src) && /_finIso/.test(src));
truthy("  and typing a date clears the preset",
       /financePreset\(''\)/.test(fs.readFileSync(
         path.join(__dirname, "templates/dashboard.html"), "utf8")));
truthy("the screen says which days it counted", /money that moved between/.test(src));
truthy("  and whose money, on which marketplace",
       /account_label/.test(src) && /FIN\.meta\.marketplace/.test(src));
truthy("  and warns when the totals are a filtered subset",
       /not the whole period/.test(src));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
