// The listings page after the owner's 27 Sep 2026 instructions (read.txt):
//
//   1  the detailed row is back as it was before the 26 Sep redesign -- the
//      separate Fees column, Min/Max and the business-price line on the row, no
//      card features moved in -- EXCEPT the real condition, which the owner
//      chose to keep
//   2  stat cards keep the "Click to filter" hint
//   3  three view toggles again: table, detailed, card
//   4  the "Add a product" form is gone
//   5  the upload zone is one line, and an empty queue is one line with its
//      controls hidden
//   and the toolbar changes that were approved stay: Costs ▾, the ⋯ menu,
//   Refresh as "Reload list" inside it.
//
// Run: node test_listings_restore.js
const fs = require("fs");
let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(68) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(l, g){ check(l, !!g, true); }
const rd = p => fs.readFileSync(p, "utf8");
const TPL = rd("templates/dashboard.html"), LS = rd("static/js/listings.js"),
      LRD = rd("static/js/listrow_detailed.js"), MT = rd("static/js/miles_template.js"),
      IQ = rd("static/js/inputqueue.js"), IU = rd("static/js/inputupload.js"),
      GF = rd("static/js/genflow.js"), GFCSS = rd("static/css/genflow.css");

console.log("=== 1. the detailed row as it was ===");
truthy("the Fees column is back", /th\("col-fees", "Estimated fees"/.test(LRD) && /class="col-fees">' \+ lrFees\(r\)/.test(LRD));
truthy("Min/Max are on the row", /\+ lrFloorCeiling\(r\)/.test(LRD));
truthy("the business-price line is back", LRD.indexOf("Business price: account not enrolled") >= 0);
check("no card features moved in (margin/ROI, ad spend, A+)",
      [/_econLine\(r\)/.test(LRD), /_ppcLine\(r\)/.test(LRD), /function lrAplusBadge/.test(LRD)], [false, false, false]);
truthy("but the condition is Amazon's, not a hard-coded New",
       /Condition ' \+ lrCondition\(r\)/.test(LRD) && LRD.indexOf("Condition <strong>New</strong>") < 0);

console.log("\n=== 2. stat cards say they can be clicked ===");
truthy("Click to filter", /"Click to filter"/.test(LS));

console.log("\n=== 3. three view toggles, card view back ===");
check("table, detailed and card", (TPL.match(/data-view="(table|detailed|grid)"/g) || []).sort(),
      ['data-view="detailed"', 'data-view="grid"', 'data-view="table"']);
truthy("the card renderers are back", /function card\(r\)/.test(LS) && /function liveTile\(it\)/.test(MT));
truthy("table is the default again", /let LIST_VIEW = "table"/.test(LS));

console.log("\n=== 4. no Add a product form ===");
check("the form and its submit are gone",
      [/Add a product<\/p>/.test(IQ), /iq_new_/.test(IQ), /function inputQueueAdd/.test(IQ)], [false, false, false]);

console.log("\n=== 5. the upload zone and an empty queue are one line ===");
truthy("the drop zone is one row with the template link in it",
       /iup-zone iup-line/.test(IU) && /Drop a spreadsheet here/.test(IU) && /Download template<\/a>/.test(IU));
truthy("  the template link does not open the file picker", /iup-link" onclick="event\.stopPropagation\(\)"/.test(IU));
truthy("an empty queue says so in one line",
       IQ.indexOf("No products queued · drop a spreadsheet or click <b>Upload template</b>") >= 0);
truthy("  and hides the header's controls until something is queued",
       /classList\.toggle\("iq-empty", !IQ\.rows\.length\)/.test(IQ)
       && /\.genflow-queue\.iq-empty \.genflow-qhead\{ display: none; \}/.test(GFCSS));
truthy("Upload template still opens and closes the section", /onclick="genflowToggle\(\)"/.test(TPL));

console.log("\n=== the approved toolbar stays ===");
truthy("Costs ▾", /toolbarMenu\(event, 'tpl_costs'\)/.test(TPL));
truthy("the ⋯ menu carries the moved tools", /<template id="tpl_more_tools">/.test(TPL) && /_tplHtml\("tpl_more_tools"\)/.test(GF));
truthy("Refresh is 'Reload list' inside it", /onclick="refreshView\(\)"[^>]*>[\s\S]{0,80}Reload list/.test(TPL));

console.log("\n" + (fails ? fails + " FAILED" : "all passed"));
process.exit(fails ? 1 : 0);
