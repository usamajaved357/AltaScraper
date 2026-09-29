// The Orders layout (static/js/orders_board.js) -- the design plan's Orders
// page, READ-ONLY by the owner's choice (29 Sep 2026, "Layout first").
//
// Pins: each order lands in the right tab from the data it carries; the counts
// add up; the first view is never empty for no reason; and the read-only
// promise -- nothing in the file calls the server, every "Next step" only opens
// the order, and the buttons that would act for real are switched off.

const fs = require("fs");
const vm = require("vm");

let fails = [];
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(70) + (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}

const SRC = fs.readFileSync("static/js/orders_board.js", "utf8");
const sb = { console, Date, ORD: {}, jsArg: require("./test_helpers.js").jsArg,
  _oEsc: s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
  _oWhen: s => String(s), _ordParcelCell: () => "PARCEL", ordersRender: () => {} };
// The screen's one ship-by rule lives in orders.js; lifted from there, not copied.
const _OJS = fs.readFileSync("static/js/orders.js", "utf8");
const _i = _OJS.indexOf("function _ordShipMs("), _j = _OJS.indexOf("\n}", _i) + 2;
vm.createContext(sb);
vm.runInContext(_OJS.slice(_i, _j), sb);
vm.runInContext(SRC, sb);

const H = 3600000, iso = ms => new Date(Date.now() + ms).toISOString();
const row = (o) => Object.assign({ order_id: "O" + Math.random(), status: "Unshipped", fulfilment: "MFN", unshipped: 1 }, o);

console.log("=== every order lands in the tab its data says ===");
check("unshipped FBM, ship-by ahead -> to dispatch", sb._ordState(row({ ship_by: iso(5 * H) })), "dispatch");
check("unshipped FBM, ship-by passed -> problem (late)", sb._ordState(row({ ship_by: iso(-H) })), "problem");
check("buyer asked to cancel -> problem", sb._ordState(row({ ship_by: iso(5 * H), item: { cancel_requested: true } })), "problem");
check("Amazon cannot fulfil -> problem", sb._ordState(row({ status: "Unfulfillable", unshipped: 0 })), "problem");
check("shipped recently, no tracking -> needs tracking", sb._ordState(row({ status: "Shipped", unshipped: 0, updated: iso(-5 * H) })), "tracking");
check("shipped long ago, no tracking here -> just shipped (Amazon hides seller tracking)",
      sb._ordState(row({ status: "Shipped", unshipped: 0, updated: iso(-10 * 24 * H) })), "shipped");
check("parcel exception -> problem", sb._ordState(row({ status: "Shipped", unshipped: 0, tracking: [{}], tracking_status: { status: "exception" } })), "problem");
check("carrier does not know the number -> problem", sb._ordState(row({ status: "Shipped", unshipped: 0, tracking: [{}], tracking_status: { status: "not_found" } })), "problem");
check("pre-order -> waiting", sb._ordState(row({ status: "PendingAvailability" })), "waiting");
check("cancel asked after it shipped -> not a problem", sb._ordState(row({ status: "Shipped", unshipped: 0, updated: iso(-H), item: { cancel_requested: true } })), "tracking");
check("shipped with tracking -> in transit", sb._ordState(row({ status: "Shipped", unshipped: 0, tracking: [{}], tracking_status: { status: "in_transit" } })), "transit");
check("delivered -> done (All only)", sb._ordState(row({ status: "Shipped", unshipped: 0, tracking: [{}], tracking_status: { status: "delivered" } })), "done");
check("FBA -> fba", sb._ordState(row({ fulfilment: "AFN", status: "Shipped", unshipped: 0 })), "fba");
check("payment not cleared -> waiting (All only)", sb._ordState(row({ status: "Pending" })), "waiting");
check("cancelled -> closed (All only)", sb._ordState(row({ status: "Canceled", unshipped: 0 })), "closed");

console.log("\n=== the counts add up ===");
const rows = [row({ ship_by: iso(5 * H) }), row({ ship_by: iso(-H) }), row({ status: "Shipped", unshipped: 0 }),
              row({ fulfilment: "AFN", status: "Shipped", unshipped: 0 }), row({ status: "Pending" }),
              row({ status: "Shipped", unshipped: 0, updated: iso(-H) })];
const c = sb._ordTabCounts(rows);
check("Needs action = dispatch + tracking + problem", c.action, c.dispatch + c.tracking + c.problem);
check("All counts every order", c.all, rows.length);
// Re-pinned 29 Sep 2026: "To buy" is drawn now that purchases are recorded
// (domain/order_purchases.py); "Returns & messages" still has no data.
check("the plan's tabs, in order, minus the one with no data", vm.runInContext("ORD_TABS", sb).map(t => t[0]),
      ["action", "tobuy", "dispatch", "tracking", "problem", "transit", "fba", "all"]);

console.log("\n=== To buy: still to post, nobody recorded buying it ===");
const nb = sb._ordNeedsBuying;
check("to dispatch, no purchase recorded -> to buy", nb(row({ ship_by: iso(5 * H), purchases: [] })), true);
check("to dispatch, bought -> not to buy", nb(row({ ship_by: iso(5 * H), purchases: [{ id: 1 }] })), false);
check("late and not bought -> still to buy", nb(row({ ship_by: iso(-H), purchases: [] })), true);
check("buyer asked to cancel -> not to buy", nb(row({ ship_by: iso(5 * H), purchases: [], item: { cancel_requested: true } })), false);
check("purchases could not be read -> claims nothing", nb(row({ ship_by: iso(5 * H), purchases: null })), false);
check("  nor when the field is missing", nb(row({ ship_by: iso(5 * H) })), false);
check("FBA -> never to buy", nb(row({ fulfilment: "AFN", status: "Unshipped", purchases: [] })), false);
check("already shipped -> not to buy", nb(row({ status: "Shipped", unshipped: 0, updated: iso(-H), purchases: [] })), false);
check("Amazon cannot fulfil -> not to buy", nb(row({ status: "Unfulfillable", unshipped: 1, purchases: [] })), false);
check("payment not cleared -> not to buy yet", nb(row({ status: "Pending", purchases: [] })), false);
const buyRows = [row({ ship_by: iso(5 * H), purchases: [] }), row({ ship_by: iso(5 * H), purchases: [{ id: 2 }] })];
const bc = sb._ordTabCounts(buyRows);
check("the To buy count is the unbought ones only", [bc.tobuy, bc.dispatch], [1, 2]);
sb.ORD.tab = "tobuy"; sb.ORD.channel = ""; sb.ORD.open = "";
check("the To buy tab shows only the unbought one", sb._ordVisible(buyRows).map(r => r.order_id), [buyRows[0].order_id]);
check("late, and Amazon left the unshipped count out -> still to buy (review)",
      nb(row({ status: "Unshipped", unshipped: 0, ship_by: iso(-H), purchases: [] })), true);
sb.ORD.tab = "all";
const tabsKnown = sb._ordTabsHtml(buyRows);
check("tab count shown when purchases were read", /To buy <span class="ord-tab-n">1</.test(tabsKnown), true);
const tabsUnknown = sb._ordTabsHtml([row({ ship_by: iso(5 * H), purchases: null }), row({ fulfilment: "AFN", status: "Shipped", unshipped: 0 })]);
check("unreadable purchases -> a dash, never a 0 that means 'nothing to buy'", /To buy <span class="ord-tab-n cc"[^>]*>—</.test(tabsUnknown), true);
check("  FBA rows with no purchases field do not cause the dash",
      /To buy <span class="ord-tab-n">0</.test(sb._ordTabsHtml([row({ fulfilment: "AFN", status: "Shipped", unshipped: 0 })])), true);
sb.ORD.tab = undefined;
sb.ORD.rows = rows; sb.ORD.tab = undefined;
check("first view: Needs action when anything needs it", sb._ordTab(), "action");
sb.ORD.rows = [row({ fulfilment: "AFN", status: "Shipped", unshipped: 0 })];
check("  and All when nothing does, never an empty tab by default", sb._ordTab(), "all");
// The table body lives in orders.js's renderer: with the tab on To buy and the
// records unreadable it must not fall through to "Nothing in this tab".
const _BODY = _OJS.slice(_OJS.indexOf("const _buyUnknown"), _OJS.indexOf("_shown.forEach(function(r){"));
check("To buy, records unreadable -> the body says it cannot tell, not 'Nothing'",
      /_buyUnknown[\s\S]*Could not read which orders were marked as bought[\s\S]*else if\(!_shown\.length\)[\s\S]*Nothing in this tab/.test(_BODY), true);
check("  and it asks the board's one rule", /_ordBuyKnown\(ORD\.rows\)/.test(_BODY), true);

console.log("\n=== what is shown ===");
sb.ORD.rows = rows; sb.ORD.tab = "fba"; sb.ORD.channel = ""; sb.ORD.open = rows[0].order_id;
check("the open order stays in view whatever the tab", sb._ordVisible(rows).some(r => r.order_id === rows[0].order_id), true);
sb.ORD.open = ""; sb.ORD.sel = new Set([rows[0].order_id]); sb.ordersSetTab("all");
check("changing tab clears the ticks", sb.ORD.sel.size, 0);

console.log("\n=== read-only, as the owner chose ===");
check("the file makes no network calls", /\bfetch\(|XMLHttpRequest|sendBeacon/.test(SRC), false);
const btn = sb._ordNextBtn(row({ ship_by: iso(5 * H) }));
check("a Next step only opens the order", /onclick="event\.stopPropagation\(\);ordersToggle\(/.test(btn), true);
sb.ORD.rows = rows; sb.ORD.sel = new Set([rows[0].order_id]);
const bar = sb._ordBulkBar();
check("Buy from suppliers is switched off", /disabled[^>]*>[^<]*<i class="ti ti-shopping-cart/.test(bar), true);
check("Mark dispatched is switched off", /disabled[^>]*>[^<]*<i class="ti ti-truck-delivery/.test(bar), true);
check("  and says why", /Not switched on yet/.test(bar), true);

if (fails.length) { console.log("\nFAILED: " + fails.length); process.exit(1); }
console.log("\nall Orders layout checks passed");
