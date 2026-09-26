// The listings page redesign of 26 Sep 2026, EXECUTED against the real files.
//
// What the owner asked for (read.txt), and what each part must still get right:
//
//   toolbar    Costs ▾ holds the sheet, the upload and the explainer; the ⋯ menu
//              holds Fix product types, Diagnose, Paste, Reload list and Clear
//              COGS; the card toggle is gone
//   row        the real condition (from Sync), never a hard-coded "New"; no
//              "Business price: account not enrolled"; no Min/Max on the row;
//              the fees as one line under the profit; "Revenue calculator" in
//              the pricing cell; the price box says "app only"
//   moved in   the card's margin/ROI chip, its ad-spend line and its A+ badge;
//              the table's compliance words
//   cards      the card view is retired; "Delete this copy" is in the row menu
//   stats      each card says it can be clicked
//
// This replaces test_card_view.py, which tested the retired card grid. Its
// checks on the margin/ROI chip live on here, because that chip now draws in
// the detailed row -- and here they are RUN, not grepped.
//
// Run: node test_listings_redesign.js
const fs = require("fs");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(70) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

// ---- the page's files, loaded together, as test_listing_views.js does ------
const SRC = ["static/js/liststatus.js", "static/js/cogs.js", "static/js/listrow_edit.js",
             "static/js/listings.js", "static/js/listrow_detailed.js"]
  .map(p => fs.readFileSync(p, "utf8")).join("\n;\n");
globalThis.window = globalThis;
globalThis.esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;")
  .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
globalThis.CUR_SYMBOL = "£";
globalThis.SELECTED = new Set();
globalThis.LIVE_ITEMS = [];
globalThis.thumbUrl = u => u;
globalThis.jsArg = s => JSON.stringify(String(s));
globalThis.toast = () => {};
globalThis.localStorage = {getItem: () => null, setItem: () => {}};
globalThis.document = {getElementById: () => null, querySelectorAll: () => [],
  querySelector: () => null, addEventListener: () => {},
  createElement: () => ({style: {}, classList: {add(){}, remove(){}, toggle(){}}}),
  body: {classList: {add(){}, remove(){}, toggle(){}}}};
globalThis.addEventListener = () => {};
globalThis.setTimeout = () => 0;
globalThis.setInterval = () => 0;
globalThis.fetch = () => Promise.resolve({ok: true, json: () => ({})});
globalThis.location = {href: "", search: "", pathname: "/"};
globalThis.navigator = {userAgent: "node"};
globalThis.matchMedia = () => ({matches: false, addListener(){}, addEventListener(){}});
globalThis.LIST_SOURCE = "all";
globalThis.CUR_ACCOUNT = {id: "acct", label: "Account"};
globalThis.WS_MARKET = "UK";
globalThis.LIVE_MAP = {};
globalThis.sid = s => String(s).replace(/[^a-zA-Z0-9]/g, "_");

const F = new Function(SRC + `
  return {lrProduct, lrPerf, lrPricing, lrStatus, lrFees, detailedHead, detailedRow,
          _econLine, listViewNow,
          setMirror: function(m){ LIVE_MIRROR = m; },
          setAplus:  function(m){ APLUS_BY_ASIN = m; }};`)();

const DRAFT = {sku: "12.50_5Days_B0COMP01", title: "Mixing bowl", status: "GENERATED",
               asin: "B0COMP01", price: 23.90, profit: 5.24, cogs: 12.50,
               cogs_source: "manual", brand: "Nestwell Goods", barcode: "5060891725034",
               restricted: {matched: false}, viability: {matched: false}};

console.log("=== the condition is Amazon's, not a constant ===");
F.setMirror({});
const p0 = F.lrProduct(DRAFT);
truthy("no hard-coded 'Condition New'", p0.indexOf("Condition <strong>New</strong>") < 0);
truthy("  a dash until Sync has read it", /Condition <span class="prod-dim"[^>]*>—<\/span>/.test(p0));
F.setMirror({[DRAFT.sku]: {condition: "new_new"}});
truthy("new_new reads as New", /Condition <strong title="Amazon’s value: new_new">New<\/strong>/.test(F.lrProduct(DRAFT)));
F.setMirror({[DRAFT.sku]: {condition: "used_like_new"}});
truthy("used_like_new reads as Used – like new", F.lrProduct(DRAFT).indexOf("Used – like new") >= 0);
F.setMirror({});

console.log("\n=== the table's compliance words, in the detailed row ===");
truthy("a clear listing says clear", /lr-compwords[\s\S]*shield-check[\s\S]*clear/.test(p0));
const gated = Object.assign({}, DRAFT, {restricted: {matched: true, matches: [{tier: "GATED"}]}});
truthy("a gated one says gated", /lr-compwords[\s\S]*gated/.test(F.lrProduct(gated)));

console.log("\n=== pricing: app only, no business price, no min/max, fees inline ===");
const pr = F.lrPricing(DRAFT);
truthy("the price box says 'app only'", /class="lr-apponly">app only</.test(pr));
truthy("no 'Business price' line", pr.indexOf("Business price") < 0);
truthy("no Min / Max boxes on the row", !/>Min<|>Max</.test(pr));
truthy("the fees are a line in the cell", /class="fee-line"/.test(pr));
truthy("  under the profit", pr.indexOf(">Profit<") < pr.indexOf('class="fee-line"'));
truthy("'Revenue calculator' is in the cell", pr.indexOf("Revenue calculator") >= 0);
truthy("  and still opens the panel, not a page", /class="fee-link" onclick="event\.stopPropagation\(\);revOpen\(/.test(pr));

console.log("\n=== the header: no fees column; pricing says app only ===");
const head = F.detailedHead([DRAFT]);
check("seven columns", (head.match(/<th\b/g) || []).length, 7);
truthy("no Estimated fees column", head.indexOf("Estimated fees") < 0);
truthy("Pricing says 'app only · not sent to Amazon'", head.indexOf("app only · not sent to Amazon") >= 0);
const row = F.detailedRow(DRAFT);
check("  and a row has the same seven cells", (row.match(/<td\b/g) || []).length, 7);

console.log("\n=== the card's margin/ROI chip, now in the detailed row ===");
const e1 = F._econLine(DRAFT);
truthy("a draft's stored profit draws the chip", /class="profchip tone-/.test(e1));
truthy("  margin and ROI are both labelled", /margin 21\.9%/.test(e1) && /ROI 41\.9%/.test(e1));
truthy("  with the same margin bands the card used", /margin >= 25/.test(SRC) && /margin >= 10/.test(SRC));
check("no profit figure -> no chip", F._econLine(Object.assign({}, DRAFT, {profit: ""})), "");
// THE BUG FIXED WITH THIS MOVE: a catalogue row carries its profit as an
// object, which the digit-strip used to turn into a confident "£0.00".
const CAT = {sku: "LIVE-9", price: 18.5,
             profit: {net: 7.72, margin: 41.7, roi: 104.3, price: 18.5, cogs: 7.4, referral: 2.78}};
const e2 = F._econLine(CAT);
truthy("a catalogue row's profit object is read, not zeroed", e2.indexOf("£7.72") >= 0 && e2.indexOf("£0.00") < 0);
truthy("  with its own margin and ROI", /margin 41\.7%/.test(e2) && /ROI 104\.3%/.test(e2));
truthy("  in the healthy band", /tone-ok/.test(e2));
// ON A DRAFT TOO: the card showed it on drafts, and Performance used to stop at
// "Not yet live" before reaching it.
const pd = F.lrPerf(DRAFT);
truthy("the chip is in Performance on a draft", pd.indexOf("Not yet live") >= 0 && pd.indexOf("profchip") >= 0);

console.log("\n=== page views and rank on one line; still dashes when unknown ===");
const perf = F.lrPerf(Object.assign({}, DRAFT, {status: "LIVE"}));
truthy("one compact line", /class="lr-compact"/.test(perf));
truthy("  no separate Page views / Sales rank rows", !/>Page views<|>Sales rank</.test(perf));

console.log("\n=== the A+ badge, from the card, in the status cell ===");
F.setAplus({});
truthy("no A+ -> no badge", F.lrStatus(DRAFT).indexOf("lr-aplus") < 0);

console.log("\n=== toolbar, menus and the retired card view ===");
const TPL = fs.readFileSync("templates/dashboard.html", "utf8");
const GF = fs.readFileSync("static/js/genflow.js", "utf8");
const LJ = fs.readFileSync("static/js/listings.js", "utf8");
const tpl = id => { const s = TPL.slice(TPL.indexOf('<template id="' + id + '">'));
                    return s.slice(0, s.indexOf("</template>")); };
truthy("a Costs ▾ button", /onclick="toolbarMenu\(event, 'tpl_costs'\)"/.test(TPL));
["/cogs/template.csv", 'onclick="cogsUploadOpen()"', 'onclick="cogsExplain()"'].forEach(m =>
  truthy("  Costs holds " + m, tpl("tpl_costs").indexOf(m) >= 0));
["ptFixDrafts()", "runSpDiagnose()", "openPasteListing()", "refreshView()"].forEach(m =>
  truthy("⋯ holds " + m, tpl("tpl_more_tools").indexOf(m) >= 0));
truthy("⋯ holds Clear COGS, as a danger item", /class="danger[^"]*"[^>]*onclick="cogsClearAll\(\)"/.test(tpl("tpl_more_danger")));
truthy("the ⋯ menu adds both groups", /_tplHtml\("tpl_more_tools"\)/.test(GF) && /_tplHtml\("tpl_more_danger"\)/.test(GF));
truthy("  Retry, Export, Preview, Submit and Stop are still in it",
       ["runMode(\\'retry\\')", "runMode(\\'export\\')", "runMode(\\'api\\')", "submitLive()", "stopRun()"]
         .every(s => GF.indexOf(s) >= 0));
const wstool = TPL.slice(TPL.indexOf('class="wstoolbar"'), TPL.indexOf('<template id="tpl_costs">'));
["ptFixDrafts()", "runSpDiagnose()", "cogsClearAll()"].forEach(m =>
  truthy("  " + m + " is no longer a toolbar button", wstool.indexOf('onclick="' + m + '"') < 0));
truthy("no card toggle", TPL.indexOf('data-view="grid"') < 0);
truthy("Delete this copy is in the row menu, on duplicates only",
       /isDuplicate\(_r\)\)[\s\S]{0,120}delDuplicate\(/.test(LJ));
truthy("Min / max is in the row menu", /lrRuleDialog\('/.test(LJ));
truthy("the stat cards say they can be clicked", /"Click to filter"/.test(LJ));

console.log("\n" + (fails ? fails + " FAILED" : "all passed"));
process.exit(fails ? 1 : 0);
