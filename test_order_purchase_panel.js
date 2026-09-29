// The "Bought from the supplier?" box on an opened order (static/js/orders.js
// ordPurchasePanel, 30 Sep 2026). A RECORD a person makes -- nothing is bought.
//
// Pins: FBA orders get no box; recorded purchases are listed with a Remove that
// carries the row's own account and marketplace; the form posts to
// /orders/purchase with the row's account (never the open one); no money is
// asked for (the Cost box is the one place for that); supplier text is escaped
// and inline-handler data goes through jsArg; both panel layouts call it.

const fs = require("fs");
const vm = require("vm");

let fails = [];
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(70) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}

const JS = fs.readFileSync(__dirname + "/static/js/orders.js", "utf8");
function lift(name) {
  const i = JS.indexOf((name.startsWith("async ") ? "" : "function ") + name + "(");
  const at = name.startsWith("async ") ? JS.indexOf(name + "(") : i;
  if (at < 0) throw new Error("not found: " + name);
  return JS.slice(at, JS.indexOf("\n}", at) + 2);
}

const posted = [];
const sb = {
  console, jsArg: require("./test_helpers.js").jsArg, ORD: { details: {} },
  _oWhen: s => String(s || "—"), toast: () => {}, ordersRender: () => {},
  ordersLoad: async () => {}, ordersToggle: (o, a) => { sb.toggled.push(a); }, toggled: [],
  _ordState: r => (r.status === "Canceled" ? "closed" : "dispatch"),
  fetch: async (url, init) => { posted.push({ url, body: JSON.parse(init.body) }); return { json: async () => ({ ok: true }) }; },
  document: { getElementById: id => ({ ordbuy_sup: { value: "Argos", defaultValue: "Argos" },
                                       ordbuy_ref: { value: " A-1 " }, ordbuy_note: { value: "" } }[id] || null) },
};
vm.createContext(sb);
// The page's own escape, lifted from orders.js rather than a stand-in (review).
vm.runInContext(lift("_oEsc"), sb);
vm.runInContext(lift("ordPurchasePanel") + "\n" + lift("async function _ordWriteThenReload")
  + "\n" + lift("async function ordRecordPurchase") + "\n" + lift("async function ordRemovePurchase"), sb);

const row = { order_id: "206-1", account_id: "acct_b", marketplace: "UK", fulfilment: "MFN" };

console.log("=== what is drawn ===");
check("FBA orders get no box (Amazon ships them)", sb.ordPurchasePanel(Object.assign({}, row, { fulfilment: "AFN" }), null), "");
const empty = sb.ordPurchasePanel(Object.assign({}, row, { purchases: [] }), { label: "Argos", url: "https://a.example/p" });
check("the form is offered", /Mark as bought/.test(empty), true);
check("  the supplier box starts with the cheapest supplier", /id="ordbuy_sup"[^>]*value="Argos"/.test(empty), true);
check("  it says nothing is bought by the app", /Nothing is ordered or paid for by this app/.test(empty), true);
check("  no amount box -- the cost lives in the Cost box", /ordbuy_(paid|cost|price|amount)/.test(empty), false);
const unknown = sb.ordPurchasePanel(Object.assign({}, row, { purchases: null }), null);
check("purchases unreadable -> says so, still offers the form", [/Could not read/.test(unknown), /Mark as bought/.test(unknown)], [true, true]);
const one = sb.ordPurchasePanel(Object.assign({}, row, { purchases: [
  { id: 7, supplier: 'Bad<b>"x', supplier_url: "https://s.example/o", supplier_ref: "R1", bought_at: "2026-09-30T10:00:00", bought_by: "a@b" }] }), null);
check("a recorded purchase is listed", /Bought/.test(one) && /R1/.test(one), true);
check("  supplier text is escaped", /Bad&lt;b&gt;&quot;x/.test(one) && !/Bad<b>/.test(one), true);
const cancelled = sb.ordPurchasePanel(Object.assign({}, row, { status: "Canceled", purchases: [{ id: 3, supplier: "S" }] }), null);
check("cancelled order: lists what was recorded, offers no new record",
      [/Bought/.test(cancelled), /Mark as bought/.test(cancelled)], [true, false]);
check("  Remove carries the row's account and marketplace",
      /ordRemovePurchase\(&quot;206-1&quot;,7,&quot;acct_b&quot;,&quot;UK&quot;\)|ordRemovePurchase\("206-1",7,"acct_b","UK"\)/.test(one)
      || one.indexOf("ordRemovePurchase(" + sb.jsArg("206-1") + "," + sb.jsArg(7) + "," + sb.jsArg("acct_b") + "," + sb.jsArg("UK") + ")") >= 0, true);

console.log("\n=== what is sent ===");
(async () => {
  await sb.ordRecordPurchase("206-1", "acct_b", "UK", "https://a.example/p");
  const p = posted[0] || {};
  check("records to /orders/purchase", p.url, "/orders/purchase");
  check("  naming the ROW's account and marketplace", [p.body.account, p.body.marketplace, p.body.order_id], ["acct_b", "UK", "206-1"]);
  check("  with the typed supplier, ref (trimmed) and the supplier's link", [p.body.supplier, p.body.supplier_ref, p.body.supplier_url], ["Argos", "A-1", "https://a.example/p"]);
  sb.document.getElementById = id => ({ ordbuy_sup: { value: "Other shop", defaultValue: "Argos" } }[id] || { value: "" });
  await sb.ordRecordPurchase("206-1", "acct_b", "UK", "https://a.example/p");
  check("a changed supplier name drops the old supplier's link", posted[1].body.supplier_url, "");
  await sb.ordRemovePurchase("206-1", 7, "acct_b", "UK");
  check("remove posts purchase_id (never `id`, which the guard reads as an account)",
        [posted[2].url, posted[2].body.purchase_id, "id" in posted[2].body, posted[2].body.account],
        ["/orders/purchase/remove", 7, false, "acct_b"]);

  console.log("\n=== one press, one record; no reopen after an account switch ===");
  const btn = { disabled: false };
  const n0 = posted.length;
  const p1 = sb.ordRecordPurchase("206-1", "acct_b", "UK", "", btn);
  const p2 = sb.ordRecordPurchase("206-1", "acct_b", "UK", "", btn);
  await Promise.all([p1, p2]);
  check("a double click records once", posted.length - n0, 1);
  sb.fetch = async (url, init) => { posted.push({ url, body: JSON.parse(init.body) }); return { json: async () => ({ ok: false, error: "no" }) }; };
  const btn2 = { disabled: false };
  await sb.ordRecordPurchase("206-1", "acct_b", "UK", "", btn2);
  check("a refused save frees the button again", btn2.disabled, false);
  sb.fetch = async (url, init) => { sb.ACTIVE_WS = { key: "acct_c" }; return { json: async () => ({ ok: true }) }; };
  sb.toggled.length = 0;
  await sb.ordRemovePurchase("206-1", 7, "acct_b", "UK");
  check("switched account mid-save -> the old account's order is not reopened", sb.toggled.length, 0);
  sb.ACTIVE_WS = { key: "acct_b" };
  sb.fetch = async () => ({ json: async () => ({ ok: true }) });
  await sb.ordRemovePurchase("206-1", 7, "acct_b", "UK");
  check("  same account -> reopened as before", sb.toggled, ["acct_b"]);

  console.log("\n=== both panel layouts use the one function ===");
  const PANEL = fs.readFileSync(__dirname + "/static/js/orders_panel.js", "utf8");
  check("compact panel calls ordPurchasePanel, with the opened order's own list",
        /ordPurchasePanel\(r, _opBestSource\(d, items\), o\.purchases\)/.test(PANEL), true);
  const freshFirst = sb.ordPurchasePanel(Object.assign({}, row, { purchases: [] }), null, [{ id: 9, supplier: "Fresh" }]);
  check("the opened order's list wins over a stale list row", /Fresh/.test(freshFirst), true);
  const noFresh = sb.ordPurchasePanel(Object.assign({}, row, { purchases: [{ id: 4, supplier: "RowOne" }] }), null, undefined);
  check("  and the row's list is used when the detail has none", /RowOne/.test(noFresh), true);
  check("long fallback calls ordPurchasePanel", /h \+= ordPurchasePanel\(r,/.test(JS), true);
  check("tracking writes share the same write-then-reload", /_ordWriteThenReload\("\/tracking\/set"/.test(JS), true);

  if (fails.length) { console.log("\nFAILED: " + fails.length); process.exit(1); }
  console.log("\nall purchase panel checks passed");
})();
