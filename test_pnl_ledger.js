// The P&L line breakdowns (pnl.js pnlLedger* / pnlMissing*), owner 30 Sep 2026:
// "i want every detailed breakdown of how these profit numbers are calculated
// and also references so i can verify them".
//
// What must hold on screen: a line opens and closes in place; the items'
// total is checked against the line and a difference is shown in RED, never
// hidden; the subtotals are explained from the statement's own lines; the
// missing-cost list names the SKUs and their orders; the CSV carries every
// item, quoted safely; and a reply for an old statement lands nowhere.

const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = [];
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(72) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}

// ---- a tiny DOM: the ledger row, its label button and the missing-list box --
function el(id) {
  const e = {id, attrs: {}, innerHTML: "", className: "",
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
    getAttribute(k) { return this.attrs[k]; }};
  return e;
}
const icon = el("ic"); icon.className = "ti ti-chevron-right";
const btn = el("btn"); btn.querySelector = s => (s === ".ti" ? icon : null);
const td = el("td");
const tr = el("pnl_led_refunds"); tr.attrs.hidden = "";
tr.querySelector = s => (s === "td" ? td : null);
tr.previousElementSibling = {querySelector: s => (s === ".pnl-lx" ? btn : null)};
const miss = el("pnl_missing");
const ELS = {pnl_led_refunds: tr, pnl_missing: miss};

let fetched = [];
let reply = null;
const sb = {
  console, setTimeout,
  document: {getElementById: id => ELS[id] || null},
  fetch: async (url) => { fetched.push(url); return {json: async () => reply}; },
  toast: () => {},
};
sb.window = sb;
sb.esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
sb.jsArg = s => "'" + String(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'")
  .replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;") + "'";
vm.createContext(sb);
for (const f of ["pageui.js", "pnl.js"]) {
  vm.runInContext(fs.readFileSync(path.join("static", "js", f), "utf8"), sb);
}
const R = code => vm.runInContext(code, sb);

// A statement shaped like /sales/pnl's.
const L = (key, sign, value) => ({key, label: key, sign, value, basis: ""});
const lines = [L("ordered_sales", 1, 100), L("vat_line", -1, 0), L("refunds", -1, 12.5),
  L("net_sales", 0, 87.5), L("cogs", -1, 40), L("referral_fees", -1, null),
  L("fees_estimated", -1, 15), L("reimbursements", 1, 2), L("ad_spend", -1, 10),
  L("profit_before_own_costs", 0, 24.5), L("account_charges", -1, 25),
  L("other_amazon", 1, -1.5), L("manual_expenses", -1, 3), L("profit", 0, -5)];
R("PNL.data = " + JSON.stringify({workspace: "acc_a", marketplace: "UK", start: "2026-08-01",
  end: "2026-08-31", currency: "GBP", lines}) + "; PNL.seq = 7;");

console.log("== subtotals are explained from the statement's own lines ==");
let st = R("pnlSubtotalItems('net_sales', PNL.data.lines)");
check("net sales = sales - VAT - refunds", st.total, 87.5);
st = R("pnlSubtotalItems('profit_before_own_costs', PNL.data.lines)");
check("profit before own costs adds every line above it", st.total, 24.5);
check("  a 'not known' line is said, counted as 0",
      st.items.filter(i => !i.known).map(i => i.label), ["referral_fees"]);
st = R("pnlSubtotalItems('profit', PNL.data.lines)");
check("net profit = before own costs - charges + other (signed) - own", st.total, -5);

console.log("\n== the reconciliation check ==");
let rc = R("pnlLedgerRecon(12.5, 12.5, 3, 'GBP')");
check("equal -> ok", rc.state, "ok");
check("  and says both figures", rc.text, "3 items · items total £12.50 = line £12.50");
rc = R("pnlLedgerRecon(12.49, 12.5, 3, 'GBP')");
check("a penny out -> bad", rc.state, "bad");
check("  names the difference", rc.text.includes("difference −£0.01"), true);
check("a line that is not known -> said so", R("pnlLedgerRecon(4, null, 1, 'GBP')").state, "unknown");

console.log("\n== open, load, draw, close ==");
reply = {ok: true, line: "refunds", total: 12.5, count: 2, items: [
  {date: "2026-08-18", order_id: "206-1", sku: "SKU<1>", qty: 1, amount: 10, source: "Amazon refund posting", ref: "full refund of 10.00"},
  {date: "2026-08-25", order_id: "", sku: "", qty: null, amount: 2.5, source: "Amazon's day total, no order held", ref: ""}]};
(async () => {
  R("pnlLedgerToggle('refunds')");
  check("opening shows the row", tr.attrs.hidden, undefined);
  check("  and says it is loading", td.innerHTML.includes("Loading the items"), true);
  check("  and the button says expanded", btn.attrs["aria-expanded"], "true");
  await new Promise(r => setTimeout(r, 10));
  check("asked for THIS statement's line, account and dates",
        fetched[0], "/sales/pnl/ledger?line=refunds&account=acc_a&marketplace=UK&start=2026-08-01&end=2026-08-31");
  check("items drawn", td.innerHTML.includes("206-1"), true);
  check("  the check passes and is shown", td.innerHTML.includes("items total £12.50 = line £12.50"), true);
  check("  the order links to Seller Central", td.innerHTML.includes("sellercentral.amazon.co.uk/orders-v3/order/206-1"), true);
  check("  and opens on Orders", td.innerHTML.includes("pnlOpenOrder('206-1')"), true);
  check("  text is escaped", td.innerHTML.includes("SKU&lt;1&gt;"), true);
  check("  a CSV button is offered", td.innerHTML.includes("Download CSV"), true);
  R("pnlLedgerToggle('refunds')");
  check("closing hides it again", tr.attrs.hidden, "");
  check("  and empties it", td.innerHTML, "");
  check("  the chevron turns back", icon.className, "ti ti-chevron-right");

  console.log("\n== a mismatch is RED, not hidden ==");
  R("PNL.ledgers.refunds.total = 11.5; PNL.open.refunds = true; pnlLedgerDraw('refunds')");
  check("the banner is drawn as an alert", /pnl-rec bad" role="alert"/.test(td.innerHTML), true);
  check("  and says report it", td.innerHTML.includes("Please report this"), true);

  console.log("\n== errors and empties ==");
  R("PNL.ledgers.refunds = {error: 'boom'}; pnlLedgerDraw('refunds')");
  check("an error is an error, with a retry", td.innerHTML.includes("Could not load the items")
        && td.innerHTML.includes("Try again"), true);
  R("PNL.ledgers.refunds = {ok: true, items: [], total: 0}; pnlLedgerDraw('refunds')");
  check("no items -> the empty state, not a blank", td.innerHTML.includes("Nothing in this window"), true);

  console.log("\n== a reply for an OLD statement lands nowhere ==");
  reply = {ok: true, items: [{date: "x", order_id: "OLD", amount: 1}], total: 1};
  R("delete PNL.ledgers.refunds; pnlLedgerFetch('refunds'); PNL.seq = 8;");
  await new Promise(r => setTimeout(r, 10));
  check("the stale reply is dropped", R("(PNL.ledgers.refunds || {}).loading === true"), true);
  R("PNL.seq = 7");

  console.log("\n== the products with no cost ==");
  reply = {ok: true, line: "cogs", total: 40, items: [], missing_units: 3, missing: [
    {sku: "SKU-D", title: "Garden <hose>", units: 3, value: 37.5,
     orders: [{order_id: "U-1", date: "2026-08-20", qty: 2, value: 25},
              {order_id: "U-3", date: "2026-08-29", qty: 1, value: 12.5}]}]};
  R("PNL.ledgers = {}; pnlMissingOpen()");
  await new Promise(r => setTimeout(r, 10));
  check("the list is drawn", miss.innerHTML.includes("Products with no cost"), true);
  check("  names the SKU and title (escaped)", miss.innerHTML.includes("SKU-D")
        && miss.innerHTML.includes("Garden &lt;hose&gt;"), true);
  check("  lists every order", ["U-1", "U-3"].every(o => miss.innerHTML.includes("pnlOpenOrder('" + o + "')")), true);
  check("  with a product-cost box", miss.innerHTML.includes('id="pnl_mc_0"'), true);
  check("  and a box per order", miss.innerHTML.includes('id="pnl_moc_0_1"'), true);
  check("the uncosted count opens it", R("pnlPlainHtml({lines: PNL.data.lines, uncosted_units: 3}, 'GBP')")
        .includes('onclick="pnlMissingOpen();return false"'), true);
  R("pnlMissingClose()");
  check("closing empties it", miss.innerHTML, "");

  console.log("\n== saving a cost: the right account, and failures said ==");
  const toasts = [];
  sb.toast = t => toasts.push(t);
  let setCalls = [];
  sb.cogsSet = async (sku, cost) => { setCalls.push([sku, cost]); return {ok: true}; };
  sb.acctId = () => "acc_b";                    // the open account is NOT the statement's
  R("PNL.ledgers.cogs = " + JSON.stringify(reply) + ";");
  const inp = el("pnl_mc_0"); inp.value = "6"; ELS.pnl_mc_0 = inp;
  fetched = [];
  await R("pnlMissingSave(0)");
  check("another account open -> nothing is saved", [setCalls.length, fetched.length], [0, 0]);
  check("  and it says why", toasts.pop().includes("account changed"), true);
  sb.acctId = () => "acc_a";
  sb.pnlReload = () => {};
  R("pnlReload = function(){}");
  reply = {ok: false, error: "no marketplace"};
  await R("pnlMissingSave(0)");
  check("the product cost is saved for the statement's account's SKU", setCalls[0], ["SKU-D", 6]);
  check("  then re-costed on these orders only, for this account and window",
        fetched[0], "/cogs/refreeze");
  check("  a failed re-cost is SAID, not reported as done",
        toasts.pop().includes("could not be put on these orders"), true);
  const ss = fs.readFileSync(path.join("static", "js", "screenstate.js"), "utf8");
  check("an account switch drops the open lines, their items and the list",
        /o\.open = \{\}; o\.ledgers = \{\}; o\.missingOpen = false/.test(ss), true);

  console.log("\n== the CSV ==");
  const csv = R("pnlLedgerCsv([{date:'2026-08-18', order_id:'206-1', sku:'A,B', qty:1, amount:10.1234, source:'say \"hi\"', ref:''}])");
  const rows = csv.split("\n");
  check("a header row", rows[0], "date,order_id,sku,qty,amount,source,reference");
  check("commas and quotes are quoted; amounts unrounded", rows[1],
        '2026-08-18,206-1,"A,B",1,10.1234,"say ""hi""",');
  const f = R("pnlLedgerCsv([{date:'', order_id:'', sku:'=HYPERLINK(1)', qty:null, amount:-1.5, source:'x', ref:''}])").split("\n")[1];
  check("a formula-looking SKU stays text; a negative amount stays a number", f, ",,'=HYPERLINK(1),,-1.5,x,");
  R("PNL.ledgers.cogs = {ok: true, items: [], missing: [{sku: '(no sku)', has_sku: false, title: '', units: 1, value: 5, orders: [{order_id: 'Z-1', date: 'd', qty: 1, value: 5}]}]}; PNL.missingOpen = true; _pnlMissingDraw()");
  check("a line with no SKU offers only the per-order cost", [miss.innerHTML.includes('id="pnl_mc_0"'),
        miss.innerHTML.includes('id="pnl_moc_0_0"')], [false, true]);

  if (fails.length) { console.log("\nFAILED: " + fails.length); process.exit(1); }
  console.log("\nall P&L ledger checks passed");
})();
