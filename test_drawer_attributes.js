// Drive static/js/drawer_attributes.js with real getListingsItem shapes.
//
// WHAT THIS PINS
//
// The drawer now shows Amazon's live value beside the app's own. The decisions
// that matter are all small comparisons, and every one of them is a way to lie
// to the user quietly:
//
//   * "20" vs "20.0"          -> saying a dimension DIFFERS when it does not
//                                would mark most fields on most listings as
//                                disagreeing, and the feature becomes noise
//   * "grams" vs "Grams"      -> saying they MATCH when Amazon will reject one
//   * 4 values, 1 box         -> offering to edit a multi-value attribute drops
//                                the other three on the next submit
//   * the box shows the app's value, never Amazon's -- what is in the box is
//     what a submit sends, and that has to stay true on screen
//
// Run: node test_drawer_attributes.js
const fs = require("fs"), vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }

// ---- the globals the module leans on, as the page provides them -----------
globalThis.window = globalThis;
globalThis.esc = s => String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
// Both from reqscope.js, which the page loads before this module.
globalThis.acctUrl = u => u + "&account=jack_uk";
globalThis.acctBody = o => Object.assign({}, o, {account:"jack_uk"});
globalThis.rowMkt = () => "UK";
globalThis.toast = () => {};
globalThis.uiConfirm = async () => true;
globalThis._rebuildDrawerData = () => { globalThis._REBUILT = (globalThis._REBUILT||0)+1; };
globalThis.isAmazonLive = () => false;
globalThis.ROWS = [];
globalThis.DRAWER_SKU = "";

const ctx = vm.createContext(globalThis);
vm.runInContext(fs.readFileSync("static/js/drawer_attributes.js","utf8"), ctx,
                {filename:"drawer_attributes.js"});

// LIVE_ATTRS is declared `const`, so it is a global LEXICAL binding, not a
// property of the global object -- ctx.LIVE_ATTRS is undefined both here and in
// a browser. Reaching it the way another script on the page would, by name.
const LA = () => vm.runInContext("LIVE_ATTRS", ctx);

const SKU = "12.99_3Days_B0EXAMPLE1";
function seed(values, multi, extra){
  LA()[SKU] = Object.assign(
    {state:"ok", values:values||{}, multi:multi||{}, content:{}, issues:[], skipped:[]},
    extra||{});
}
function seedRaw(rec){ LA()[SKU] = rec; }

// ---------------------------------------------------------------------------
console.log("\nwhich listings are worth asking Amazon about");
// ---------------------------------------------------------------------------
check("a LIVE listing is",       ctx.lvWants({sku:"a", status:"LIVE"}), true);
check("a SUBMITTED one is",      ctx.lvWants({sku:"a", status:"SUBMITTED"}), true);
check("a QUEUED one is not -- nothing is on Amazon to read",
      ctx.lvWants({sku:"a", status:"QUEUED"}), false);
check("nor a GENERATED one",     ctx.lvWants({sku:"a", status:"GENERATED"}), false);
check("and a missing row is not",ctx.lvWants(null), false);

// ---------------------------------------------------------------------------
console.log("\nsame value, written two ways");
// ---------------------------------------------------------------------------
check('"20" and "20.0" are the same number',       ctx.lvSame("20","20.0"), true);
check('"12.75" and "12.750" too',                  ctx.lvSame("12.75","12.750"), true);
check("whitespace does not make a difference",     ctx.lvSame(" grams ","grams"), true);
check('"grams" and "Grams" ARE different -- Amazon\'s enums are case-sensitive',
      ctx.lvSame("grams","Grams"), false);
check("a value against nothing is not a match",    ctx.lvSame("","20"), false);
check("two nothings are",                          ctx.lvSame("",""), true);
check('"20" and "twenty" are not',                 ctx.lvSame("20","twenty"), false);
check("and NaN does not equal itself into a match",ctx.lvSame("NaN","NaN"), true); // string-equal
check("but NaN does not match a number",           ctx.lvSame("NaN","20"), false);

// ---------------------------------------------------------------------------
console.log("\nthe four verdicts");
// ---------------------------------------------------------------------------
seed({colour:"black", material:"steel", "item_weight.unit":"grams"});
check("app and Amazon agree",            ctx.lvVerdict(SKU,"colour","black"), "same");
check("app and Amazon disagree",         ctx.lvVerdict(SKU,"colour","blue"),  "differs");
check("Amazon has it and the app does not", ctx.lvVerdict(SKU,"material",""),  "live_only");
check("the app has it and Amazon does not", ctx.lvVerdict(SKU,"finish","matte"), "app_only");
check("neither has it -> nothing to say",   ctx.lvVerdict(SKU,"finish",""),   "");
check("a nested sub-key is compared like any other",
      ctx.lvVerdict(SKU,"item_weight.unit","grams"), "same");

console.log("\n  ...and nothing is claimed before the answer arrives");
seedRaw({state:"loading", values:{}, multi:{}, content:{}, issues:[]});
check("while loading, no field is marked as differing",
      ctx.lvVerdict(SKU,"colour","blue"), "");
seedRaw({state:"error", values:{}, multi:{}, content:{}, issues:[], error:"timeout"});
check("and a failed read does not silently mean 'Amazon has nothing'",
      ctx.lvVerdict(SKU,"colour","blue"), "");
check("nor does it offer values it never got", ctx.lvKeys(SKU), []);

// ---------------------------------------------------------------------------
console.log("\nthe box keeps the APP's value; Amazon's is shown underneath");
// ---------------------------------------------------------------------------
seed({colour:"black"});
const below = ctx.lvBelow(SKU, "colour", "blue");
truthy("Amazon's value is rendered under the control", below.indexOf("black") >= 0);
truthy("with a button to take it",                     below.indexOf("lvUse(") >= 0);
check("a field that agrees gets no second line",       ctx.lvBelow(SKU,"colour","black"), "");
check("nor does a field only the app has",             ctx.lvBelow(SKU,"finish","matte"), "");

seed({desc:"y".repeat(400)});
const longb = ctx.lvBelow(SKU, "desc", "z");
truthy("400 characters do not blow the cell open", longb.indexOf("…") >= 0);
truthy("and the full text is still in the title attribute",
       longb.indexOf("y".repeat(400)) >= 0);

// ---------------------------------------------------------------------------
console.log("\nmore than one value on Amazon is read-only, and says so");
// ---------------------------------------------------------------------------
seed({special_feature:"portable"}, {special_feature:4});
const mtag = ctx.lvTag(SKU, "special_feature", "");
truthy("the tag says how many Amazon holds", mtag.indexOf("4 values on Amazon") >= 0);
check("and NO 'use this' button is offered, so the other three cannot be dropped",
      ctx.lvBelow(SKU,"special_feature","").indexOf("lvUse(") >= 0, false);
truthy("but Amazon's first value is still visible",
       ctx.lvBelow(SKU,"special_feature","").indexOf("portable") >= 0);

console.log("\n  ...and a multi flagged on the PARENT covers its sub-keys");
seed({"battery.cell_composition":"lithium_ion"}, {battery:2});
truthy("a sub-key of a multi-valued parent is read-only too",
       ctx.lvTag(SKU,"battery.cell_composition","").indexOf("2 values on Amazon") >= 0);

// ---------------------------------------------------------------------------
console.log("\nthe strip above the grid");
// ---------------------------------------------------------------------------
seed({colour:"black", material:"steel", size:"large"});
const row = {sku:SKU, status:"LIVE", attributes:{colour:"black", size:"small"}};
const bar = ctx.lvBanner(row);
truthy("counts what matches",            bar.indexOf(">1 match<") >= 0);
truthy("counts what differs",            bar.indexOf(">1 differ<") >= 0);
truthy("counts what only Amazon has",    bar.indexOf(">1 only on Amazon<") >= 0);
truthy("offers to fill the empty ones",  bar.indexOf("lvFillEmpty(") >= 0);
truthy("and to re-read from Amazon",     bar.indexOf("lvRefresh(") >= 0);

console.log("\n  ...a listing Amazon does not have says so instead of looking broken");
seedRaw({state:"gone", values:{}, multi:{}, content:{}, issues:[],
         reason:"Amazon has no listing with this SKU on this account."});
const goneBar = ctx.lvBanner(row);
truthy("it is stated plainly",  goneBar.indexOf("no listing with this SKU") >= 0);
truthy("and re-checking is offered", goneBar.indexOf("lvRefresh(") >= 0);

console.log("\n  ...a FAILED read is never reported as 'Amazon has nothing'");
seedRaw({state:"error", values:{}, multi:{}, content:{}, issues:[],
         error:"getListingsItem timed out"});
const errBar = ctx.lvBanner(row);
truthy("the reason is shown",   errBar.indexOf("getListingsItem timed out") >= 0);
truthy("and the app's own values are explicitly NOT called wrong",
       errBar.indexOf("not confirmed") >= 0);

console.log("\n  ...Amazon's own errors on the listing surface here");
seed({colour:"black"}, {}, {issues:[
  {code:"90220", message:"Item weight is required.", severity:"ERROR", attributes:["item_weight"]},
  {code:"88888", message:"A suggestion, not a problem.", severity:"WARNING", attributes:[]}]});
const iss = ctx.lvBanner(row);
truthy("an ERROR is shown",            iss.indexOf("Item weight is required.") >= 0);
truthy("named with its attribute",     iss.indexOf("item_weight") >= 0);
check("a WARNING is not raised as an error",
      iss.indexOf("A suggestion, not a problem.") >= 0, false);

console.log("\n  ...and a listing that was never submitted gets no strip at all");
check("nothing is drawn for a QUEUED row",
      ctx.lvBanner({sku:SKU, status:"QUEUED", attributes:{}}), "");

// ---------------------------------------------------------------------------
console.log("\nfilling empty fields never overwrites one that has a value");
// ---------------------------------------------------------------------------
const calls = [];
globalThis.fetch = async (url, opt) => {
  calls.push(JSON.parse(opt.body));
  return {json: async () => ({ok:true})};
};
ctx.fetch = globalThis.fetch;
seed({colour:"red", material:"steel", size:"large"}, {size:3});
const r2 = {sku:SKU, status:"LIVE", attributes:{colour:"black", material:""}};
ctx.ROWS = [r2]; globalThis.ROWS = ctx.ROWS;
ctx.DRAWER_SKU = SKU;
(async () => {
  await ctx.lvFillEmpty(SKU);
  const keys = calls.map(c => c.key).sort();
  check("only the EMPTY field is written", keys, ["material"]);
  check("the value written is Amazon's",
        (calls.find(c => c.key === "material")||{}).value, "steel");
  check("a field the app already filled is left alone",
        keys.indexOf("colour") >= 0, false);
  check("and a multi-valued attribute is never bulk-filled",
        keys.indexOf("size") >= 0, false);
  check("the write goes through /edit as an attribute, not to Amazon",
        (calls[0]||{}).target, "attr");

  console.log("\n%d failed", fails);
  process.exit(fails ? 1 : 0);
})();
