/* The Returns Intelligence page, laid out as the report it came from.
 *
 * "the return intelligence page is not as it is in the html file it should be
 *  following exactly same design, if the data is not available for now, just
 *  show me some stale numbers but i want to see that format in the app and it
 *  should work when data is available"
 *
 * So two things have to hold at once, and they pull against each other:
 *
 *   the FORMAT is visible before the data exists -- every panel drawn, with a
 *   sample figure in it, so the layout can be judged now
 *
 *   and no sample figure can EVER be mistaken for a real one. A plausible
 *   number on a page about money is worse than an empty panel, because it gets
 *   acted on. Every placeholder is dimmed, italic, and labelled, and the page
 *   says at the top that it is showing samples.
 *
 * This executes the real file against a DOM stub, both ways round.
 */
"use strict";
const fs = require("fs");
const vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(60) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }
function falsy(label, got){ check(label, !!got, false); }

function sandbox(){
  const els = {};
  const el = id => (els[id] = els[id] || {id, innerHTML: "", value: "", style: {}});
  const s = {
    console, els,
    document: {getElementById: id => el(id), querySelectorAll: () => []},
    window: {addEventListener(){}},
    fetch: () => Promise.resolve({json: () => Promise.resolve({ok: true})}),
    toast: () => {},
    setTimeout: () => 1, clearTimeout: () => {},
    // Defined in users.js; the table header uses it.
    jsArg: x => "'" + String(x == null ? "" : x).replace(/'/g, "\\'") + "'",
  };
  vm.createContext(s);
  vm.runInContext(fs.readFileSync("D:/AltaScraper/static/js/returns.js", "utf8"), s);
  return s;
}

// The panels the report has, in its order. "Disposition & Recovery" is written
// with the entity because the title goes through the escaper, as every piece of
// text on the page should.
const PANELS = ["Daily Returns Volume", "Issue Nature Classification",
                "Return Reasons Breakdown", "Disposition &amp; Recovery",
                "Return Status", "SKU-Level Returns Detail",
                "Customer Voice Analysis", "Actionable Insights"];
// And the six figures across the top.
const KPIS = ["Total returns", "Return rate", "Refunded", "Sellable returns",
              "Avg daily returns", "Unique SKUs"];

console.log("=== with NO data: the format is visible, and marked as samples ===");
const a = sandbox();
vm.runInContext("RET.data = {ok:true, total_returns:0, natures:{}, reasons:{}, " +
                "dispositions:{}, statuses:{}, daily:{}, asins:[], comments:[]};" +
                "returnsRender();", a);
const empty = a.els.retbody.innerHTML || "";
truthy("the page renders at all", empty.length > 1000);
PANELS.forEach(p => truthy("  panel: " + p, empty.indexOf(p) >= 0));
KPIS.forEach(k => truthy("  figure: " + k, empty.indexOf(k) >= 0));
// The honesty half.
truthy("it says at the top that these are samples",
       empty.indexOf("No returns recorded for this period") >= 0);
truthy("  and that they are placeholders, not data",
       empty.indexOf("placeholders, not") >= 0);
truthy("  and that nothing is stored", empty.indexOf("not stored") >= 0);
// The two reports, named, with where to find each -- Amazon's own naming is
// not guessable ("Customer Concessions").
truthy("both reports are named", empty.indexOf("FBA Customer Returns") >= 0
       && empty.indexOf("Seller-fulfilled returns") >= 0);
truthy("  with where to find them", empty.indexOf("Customer Concessions") >= 0);
truthy("  and what each one fills in", empty.indexOf("Fills in:") >= 0);
truthy("  and a button for each", (empty.match(/Upload this one/g) || []).length === 2);
truthy("every sample figure is marked", empty.indexOf("ri-sample") >= 0);
check("  and there are several of them",
      (empty.match(/ri-sample/g) || []).length > 5, true);

console.log("\n=== with real data: the samples are gone ===");
const b = sandbox();
vm.runInContext(`RET.data = {ok:true, total_returns:212, total_ordered:2438,
  return_rate:8.7, refunded:4182.5, refunded_is_actual:true, unique_skus:54,
  natures:{"Product Quality":84,"Listing Content":52,"Customer Preference":46,
           "Shipping / Delivery":30},
  nature_actions:{"Product Quality":"talk to the supplier, or stop selling it"},
  reasons:{"Item defective":48,"Not as described":37},
  dispositions:{"Sellable":98,"Customer damaged":54},
  statuses:{"Completed":176},
  daily:{"2026-05-14":6,"2026-05-15":18,"2026-05-16":9},
  asins:[{asin:"B01",title:"Shaker bottle",returns:12,units_sold:300,rate:4.0,
          refunded:180.0,top_reason:"Item defective"}],
  comments:[{text:"Stopped working after two weeks",sku:"SKU-1",
             reason:"Item defective",nature:"Product Quality"}]};
  returnsRender();`, b);
const full = b.els.retbody.innerHTML || "";
truthy("the page renders", full.length > 1000);
PANELS.forEach(p => truthy("  panel: " + p, full.indexOf(p) >= 0));

console.log("\n  -- and the real figures are in it --");
truthy("the total", full.indexOf("212") >= 0);
truthy("the return rate", full.indexOf("8.7%") >= 0);
truthy("units ordered", full.indexOf("2,438") >= 0);
truthy("the product row", full.indexOf("Shaker bottle") >= 0);
truthy("the customer's own words",
       full.indexOf("Stopped working after two weeks") >= 0);
truthy("the peak day is named", full.indexOf("2026-05-15") >= 0);

// THE POINT: with real data, nothing on the page is dimmed as a sample.
console.log("\n  -- and nothing is dimmed as a sample --");
check("no sample markers at all", (full.match(/ri-sample/g) || []).length, 0);
falsy("no sample banner", full.indexOf("No returns recorded") >= 0);

console.log("\n=== the insights are derived, not invented ===");
// Each names the figure it came from, so it can be checked rather than believed.
truthy("an insight was raised from the nature mix",
       full.indexOf("Product Quality — 40% of returns") >= 0
       || /Product Quality — \d+% of returns/.test(full));
truthy("  and it says what to do", full.indexOf("talk to the supplier") >= 0);
truthy("  and shows the arithmetic behind it", /\d+ of \d+ returned units/.test(full));

console.log("\n=== what the seller-fulfilled report cannot give is SAID ===");
const c = sandbox();
vm.runInContext(`RET.data = {ok:true, total_returns:5, natures:{"Product Quality":5},
  reasons:{"Item defective":5}, dispositions:{}, statuses:{}, daily:{"2026-05-01":5},
  asins:[], comments:[], has_comments:false, has_disposition:false};
  returnsRender();`, c);
const partial = c.els.retbody.innerHTML || "";
truthy("the missing disposition data is explained",
       partial.indexOf("needs an FBA") >= 0);
truthy("  and so are the missing comments",
       partial.indexOf("carries no customer comments") >= 0);
truthy("  naming the file that would fix it",
       partial.indexOf("FBA Customer Returns") >= 0);

console.log("\n=== a report Amazon could not build is not an error page ===");
// "Amazon is still building the report" and "this account is seller-fulfilled
// so there is no FBA report" are ordinary states. A red message where the
// screen should be tells you nothing about returns and hides the layout.
const d = sandbox();
vm.runInContext(`RET.data = {ok:true, total_returns:0, natures:{}, reasons:{},
  dispositions:{}, statuses:{}, daily:{}, asins:[], comments:[],
  no_report:"Amazon is still building the report. Try again in a minute."};
  returnsRender();`, d);
const blocked = d.els.retbody.innerHTML || "";
truthy("the page still renders", blocked.length > 1000);
truthy("it says there is no report yet", blocked.indexOf("No report yet") >= 0);
truthy("  and repeats Amazon's own reason",
       blocked.indexOf("still building the report") >= 0);
truthy("  and offers the upload instead", blocked.indexOf("upload one instead") >= 0);
PANELS.forEach(p => truthy("  panel still drawn: " + p, blocked.indexOf(p) >= 0));

console.log("\n=== the report's design system is in the stylesheet ===");
const css = fs.readFileSync("D:/AltaScraper/static/css/dashboard.css", "utf8");
[".ri-kpis", ".ri-kpi", ".ri-card", ".ri-daily", ".ri-hbar", ".ri-mini",
 ".ri-comment", ".ri-insight", ".ri-sev", ".ri-sample"].forEach(function(c2){
  truthy("  " + c2, css.indexOf(c2) >= 0);
});
truthy("six KPI cards across, as the report has them",
       /\.ri-kpis\{[\s\S]{0,200}repeat\(6, 1fr\)/.test(css));

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
