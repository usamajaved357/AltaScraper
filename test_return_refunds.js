/* Returns > Refunds (static/js/returnrefunds.js): the table, its filters and
 * its states -- loading, error, empty, data, and a reply that arrives after the
 * account was switched (it must land nowhere). Runs the real file, with the
 * real pageui.js helpers, against a DOM stub.
 */
"use strict";
const fs = require("fs");
const vm = require("vm");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(64) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got)
                                                   + " want=" + JSON.stringify(want)));
}
const truthy = (l, g) => check(l, !!g, true);
const read = p => fs.readFileSync(__dirname + "/" + p, "utf8");

function sandbox(reply){
  const els = {};
  const el = id => (els[id] = els[id] || {id, innerHTML: "", value: "", style: {}});
  const s = {
    console, els, Date, Promise,
    document: {getElementById: id => el(id), querySelectorAll: () => []},
    window: {addEventListener(){}},
    setTimeout: () => 1, clearTimeout: () => {},
    esc: x => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"),
    jsArg: x => "'" + String(x == null ? "" : x).replace(/'/g, "\\'") + "'",
    CUR_ACCOUNT: {id: "nestwell_goods"}, WS_MARKET: "UK",
    asked: [],
  };
  s.fetch = url => { s.asked.push(url); return reply(url); };
  vm.createContext(s);
  vm.runInContext(read("static/js/pageui.js"), s);
  vm.runInContext(read("static/js/scopeq.js"), s);
  vm.runInContext(read("static/js/screenstate.js"), s);
  vm.runInContext(read("static/js/returnrefunds.js"), s);
  return s;
}
const ok = body => Promise.resolve({json: () => Promise.resolve(body)});

const DATA = {
  ok: true, workspace: "nestwell_goods", marketplace: "UK", currency: "",
  start: "2026-07-03", end: "2026-09-30", rule: "A flag from this app, not Amazon's verdict.",
  awaiting_classes: ["approved_unrefunded", "pending", "report_no_money"],
  coverage: {held: true},
  classes: [{key: "refunded_full", label: "Refunded"},
            {key: "approved_unrefunded", label: "Approved, not refunded"},
            {key: "report_no_money", label: "Report says refunded, no money"},
            {key: "refund_no_return", label: "Refund, no return"}],
  totals: {refunded: 38.24, refunded_orders: 2, awaiting: 2, awaiting_value: 101.83,
           overdue: 1, mismatches: 1,
           by_class: {refunded_full: 1, approved_unrefunded: 1, report_no_money: 1,
                      refund_no_return: 1}},
  rows: [
    {order_id: "026-8809596-8954764", "class": "approved_unrefunded",
     label: "Approved, not refunded", sku: "S1", name: "Big <thing>", return_date: "2026-09-23",
     status: "Approved", resolution: "StandardRefund", report_refunded: null,
     money_back: 0, days: 7, overdue: true, mismatch: false, note: "Reached you 2026-09-25.",
     tracking_id: "H01", carrier: "Evri"},
    {order_id: "205-4480291-7999557", "class": "report_no_money",
     label: "Report says refunded, no money", sku: "S2", name: "Thing 2", return_date: "2026-09-25",
     status: "PendingApproval", report_refunded: 31.85, money_back: 0, days: 5,
     overdue: false, mismatch: true, note: "no refund posting"},
    {order_id: "026-1108972-7232300", "class": "refunded_full", label: "Refunded",
     sku: "S3", name: "Thing 3", return_date: "2026-08-26", status: "Approved",
     report_refunded: 34.99, money_back: 33.24, money_date: "2026-09-21",
     full_or_partial: "full", days: 26, overdue: false, mismatch: false, note: "before discount"},
    {order_id: "X-NORET", "class": "refund_no_return", label: "Refund, no return",
     sku: "S4", return_date: null, money_back: 5, money_date: "2026-09-15",
     full_or_partial: "partial", days: null, overdue: false, mismatch: false, note: "goodwill"},
  ],
};

(async function(){
  console.log("=== loading, then data ===");
  let release;
  const s = sandbox(() => new Promise(r => { release = () => r({json: () => Promise.resolve(DATA)}); }));
  const p = vm.runInContext("refundsLoad()", s);
  truthy("a loading line while waiting", s.els.returns_refunds.innerHTML.indexOf("Matching returns") >= 0);
  truthy("asks /returns/refunds naming the account", s.asked[0].indexOf("/returns/refunds?account=nestwell_goods") === 0);
  truthy("  and the marketplace and window", /marketplace=UK/.test(s.asked[0]) && /start=\d{4}-/.test(s.asked[0]));
  release(); await p;
  const h = s.els.returns_refunds.innerHTML;
  truthy("four stat cards", ["Refunded", "Awaiting refund", "Overdue", "Mismatches"].every(k => h.indexOf(k) >= 0));
  truthy("a row per return", h.split("<tr>").length - 1 === 4 + 1);
  truthy("status chip with its tone", h.indexOf('rr-chip bad">Approved, not refunded') >= 0);
  truthy("overdue flagged", h.indexOf("rr-flag") >= 0);
  truthy("the product name is escaped", h.indexOf("Big &lt;thing&gt;") >= 0 && h.indexOf("<thing>") < 0);
  truthy("order opens Orders via jsArg", h.indexOf("refundsOpenOrder('026-8809596-8954764')") >= 0);
  truthy("and Seller Central", h.indexOf("sellercentral.amazon.co.uk/orders-v3/order/026-8809596-8954764") >= 0);
  truthy("money back with date and full/partial", h.indexOf("2026-09-21 · full") >= 0);
  truthy("every cell labelled for the phone layout", h.indexOf('data-label="Money back"') >= 0);
  truthy("CSV link names the account", /\/returns\/refunds\.csv\?account=nestwell_goods/.test(h));
  truthy("the rule behind an (i), not a paragraph", h.indexOf("ui-hint") >= 0);

  console.log("=== filters ===");
  vm.runInContext("refundsFilter('report_no_money')", s);
  let f = s.els.returns_refunds.innerHTML;
  check("class filter keeps one row", f.split("<tr>").length - 1, 2);
  truthy("  the one asked for", f.indexOf("205-4480291-7999557") >= 0 && f.indexOf("026-8809596") < 0);
  vm.runInContext("refundsFilter('_awaiting')", s);
  f = s.els.returns_refunds.innerHTML;
  check("awaiting card = approved + pending + report-no-money", f.split("<tr>").length - 1, 3);
  vm.runInContext("refundsFilter('_overdue')", s);
  check("overdue card", s.els.returns_refunds.innerHTML.split("<tr>").length - 1, 2);
  vm.runInContext("refundsFilter('_overdue')", s);
  check("pressing it again clears the filter", s.els.returns_refunds.innerHTML.split("<tr>").length - 1, 5);
  vm.runInContext("RREF.cls = 'pending'; refundsRender()", s);
  truthy("a filter with no rows says so", s.els.returns_refunds.innerHTML.indexOf("No rows match") >= 0);

  console.log("=== error and empty ===");
  const e = sandbox(() => ok({ok: false, error: "no marketplace"}));
  await vm.runInContext("refundsLoad()", e);
  const eh = e.els.returns_refunds.innerHTML;
  truthy("a failure is drawn as a failure", eh.indexOf("ui-error") >= 0 && eh.indexOf("no marketplace") >= 0);
  truthy("  with Try again", eh.indexOf("refundsLoad()") >= 0);
  const n = sandbox(() => ok(Object.assign({}, DATA, {rows: [], coverage: {held: false},
                                               totals: {by_class: {}}})));
  await vm.runInContext("refundsLoad()", n);
  truthy("nothing stored says how to fill it", n.els.returns_refunds.innerHTML.indexOf("Pull from Amazon") >= 0);
  const thrown = sandbox(() => Promise.reject(new Error("down")));
  await vm.runInContext("refundsLoad()", thrown);
  truthy("a network failure is an error, not empty", thrown.els.returns_refunds.innerHTML.indexOf("Could not reach") >= 0);

  console.log("=== after an account switch ===");
  let rel2;
  const w = sandbox(() => new Promise(r => { rel2 = () => r({json: () => Promise.resolve(DATA)}); }));
  const p2 = vm.runInContext("refundsLoad()", w);
  vm.runInContext("CUR_ACCOUNT = {id: 'jack_uk'}; screenForgetAll()", w);
  rel2(); await p2;
  check("A's reply lands nowhere under B", vm.runInContext("RREF.data", w), null);
  check("  and B's panel is not A's rows", w.els.returns_refunds.innerHTML.indexOf("026-8809596") >= 0, false);
  const w2 = sandbox(() => ok(DATA));
  await vm.runInContext("refundsLoad()", w2);
  vm.runInContext("RREF.cls = 'refunded_full'; screenForgetAll()", w2);
  check("a switch drops the held data and filter",
        vm.runInContext("[RREF.data, RREF.cls]", w2), [null, ""]);

  console.log("=== wiring ===");
  const html = read("templates/screens/sec_returns.html");
  truthy("a Refunds tab on the Returns screen", html.indexOf("retview_refunds") >= 0 && html.indexOf("returns_refunds") >= 0);
  truthy("the script is loaded", read("templates/dashboard.html").indexOf("/static/js/returnrefunds.js") >= 0);
  truthy("the view switch knows it", read("templates/dashboard.html").indexOf("refundsOnOpen") >= 0);
  truthy("a pull or upload makes it re-read", read("static/js/returns.js").indexOf("refundsForget") >= 0);

  console.log(fails ? "\nFAILURES: " + fails : "\nall ok");
  process.exit(fails ? 1 : 0);
})();
