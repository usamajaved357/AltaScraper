/* static/js/orders_board.js -- the Orders page's working layout (design package
 * Direction A, "Orders"), READ-ONLY.
 *
 * Owner decision, 29 Sep 2026 ("Layout first"): the status tabs with counts,
 * the ship-by countdown, row selection and the plan's columns -- and the "Next
 * step" and bulk buttons only OPEN the order or a screen. Nothing here marks an
 * order dispatched, uploads tracking to Amazon, buys from a supplier or writes
 * anything anywhere; each such action is wired later, one at a time, with his
 * OK. The buttons that would do those things are shown switched off and say so.
 *
 * Every state is worked out from what the order row already carries -- status,
 * fulfilment channel, items left to ship, ship-by date, the tracking and the
 * "bought from the supplier" records kept in this app. One of the plan's tabs
 * is NOT drawn, because the app holds nothing to decide it with: "Returns &
 * messages" (Amazon's messages are not available). Drawn empty it would claim
 * "nothing to do".
 *
 * "To buy" (29 Sep 2026): an FBM order still to post with no purchase recorded
 * against it (domain/order_purchases.py -- a record a person makes; the app
 * buys nothing). It is a subset of "To dispatch", not a state of its own.
 */

// Tab id -> label, in the plan's order.
const ORD_TABS = [
  ["action",   "Needs action"],
  ["tobuy",    "To buy"],
  ["dispatch", "To dispatch"],
  ["tracking", "Needs tracking"],
  ["problem",  "Problems"],
  ["transit",  "In transit"],
  ["fba",      "FBA"],
  ["all",      "All"],
];

/* ONE ORDER'S STATE, from the row alone. Order of the checks matters: a
 * problem outranks everything, FBA is Amazon's to ship. The "late" moment is the
 * screen's one ship-by rule (_ordShipMs in orders.js), and a cancel request is a
 * problem only while there is still something to not send -- the same line
 * domain/daily_check.py draws. */
const ORD_TRACKING_WINDOW_DAYS = 3;

/* Something still to send. Amazon sometimes leaves the count out, so the status
 * counts too. The ONE rule, for the state and for "To buy" (Rule 12). */
function _ordUnshipped(r){
  const st = String((r && r.status) || "");
  return Number((r && r.unshipped) || 0) > 0 || st === "Unshipped" || st === "PartiallyShipped";
}

function _ordState(r){
  const st = String(r.status || "");
  const fba = String(r.fulfilment || "").toUpperCase() === "AFN";
  if(st === "Canceled" || st === "Cancelled") return "closed";
  if(st === "Unfulfillable") return "problem";
  if(fba) return "fba";
  if(st === "Pending" || st === "PendingAvailability") return "waiting";
  if(_ordUnshipped(r)){
    if(r.item && r.item.cancel_requested) return "problem";
    const ms = _ordShipMs(r.ship_by);
    if(ms !== null && ms < 0) return "problem";          // late by Amazon's own date
    return "dispatch";
  }
  if(st === "Shipped" || st === "InvoiceUnconfirmed"){
    const t = r.tracking || [];
    if(!t.length){
      // NOT "NEEDS TRACKING" FOREVER. Amazon never sends back tracking entered
      // in Seller Central (measured), so an old shipment with none recorded HERE
      // is usually tracked there. Only a recent one is asked about.
      const at = Date.parse(r.updated || r.purchased || "");
      const recent = !isNaN(at) && (Date.now() - at) < ORD_TRACKING_WINDOW_DAYS * 86400000;
      return recent ? "tracking" : "shipped";
    }
    const s = (r.tracking_status || {}).status;
    if(s === "exception" || s === "not_found") return "problem";   // failed, held, returned, lost, unknown number
    return s === "delivered" ? "done" : "transit";
  }
  return "other";
}

/* Which tab is showing: the one picked, else "Needs action" when anything
 * needs action, else All -- so the first view is never empty for no reason. */
function _ordTab(){
  if(ORD.tab) return ORD.tab;
  return (ORD.rows || []).some(function(r){ return _ordInTab(_ordState(r), "action", r); }) ? "action" : "all";
}

/* STILL TO BUY: an FBM order still to post -- on time or late -- that nobody
 * has recorded buying. A buyer's cancel request is NOT to buy. Purchases that
 * could not be read (r.purchases not a list) claim nothing either way. */
function _ordNeedsBuying(r){
  if(!r || !Array.isArray(r.purchases) || r.purchases.length) return false;
  if(r.item && r.item.cancel_requested) return false;
  const s = _ordState(r);
  if(s === "dispatch") return true;
  return s === "problem" && String(r.status || "") !== "Unfulfillable"
      && _ordUnshipped(r);
}

/* Could the purchase records be read for every order they matter to? When not,
 * "To buy" shows a dash rather than a count -- a 0 would say "nothing to buy"
 * when the app simply does not know. */
function _ordBuyKnown(rows){
  return !(rows || []).some(function(r){
    return String(r.fulfilment || "").toUpperCase() !== "AFN" && !Array.isArray(r.purchases);
  });
}

function _ordInTab(state, tab, r){
  if(tab === "all") return true;
  if(tab === "tobuy") return _ordNeedsBuying(r);
  if(tab === "action") return state === "dispatch" || state === "tracking" || state === "problem";
  return state === tab;
}

function _ordTabCounts(rows){
  const c = {};
  ORD_TABS.forEach(function(t){ c[t[0]] = 0; });
  (rows || []).forEach(function(r){
    const s = _ordState(r);
    ORD_TABS.forEach(function(t){ if(_ordInTab(s, t[0], r)) c[t[0]]++; });
  });
  return c;
}

/* The rows the current tab and channel filter show. */
function _ordVisible(rows){
  const tab = _ordTab(), ch = ORD.channel || "";
  return (rows || []).filter(function(r){
    if(ORD.open && r.order_id === ORD.open) return true;   // the open order stays in view
    if(ch && String(r.fulfilment || "").toUpperCase() !== ch) return false;
    return _ordInTab(_ordState(r), tab, r);
  });
}

// Changing what is shown clears the ticks, so "N selected" is always what you see.
function ordersSetTab(t){ ORD.tab = t; if(ORD.sel) ORD.sel.clear(); ordersRender(); }
function ordersSetChannel(c){ ORD.channel = c; if(ORD.sel) ORD.sel.clear(); ordersRender(); }

function _ordTabsHtml(rows){
  const c = _ordTabCounts(rows);
  const buyKnown = _ordBuyKnown(rows);
  const tab = _ordTab();
  const TIP = {tracking: "Shipped in the last " + ORD_TRACKING_WINDOW_DAYS + " days with no tracking recorded "
                 + "in this app. Amazon does not send back tracking entered in Seller Central.",
               tobuy: "Orders you post yourself, still to send, that nobody has marked as bought "
                 + "from the supplier. Open one and press Mark as bought once you have bought it."};
  return '<div class="ord-tabs" role="group" aria-label="Show orders by what they need">'
    + ORD_TABS.map(function(t){
        const on = t[0] === tab;
        const bad = t[0] === "problem" && c[t[0]] > 0;
        return '<button type="button" aria-pressed="' + (on ? "true" : "false") + '"'
          + ' data-fk="tab:' + t[0] + '"' + (TIP[t[0]] ? ' title="' + _oEsc(TIP[t[0]]) + '"' : '')
          + ' class="ord-tab' + (on ? ' on' : '') + '" onclick="ordersSetTab(' + jsArg(t[0]) + ')">'
          + _oEsc(t[1]) + ' ' + ((t[0] === "tobuy" && !buyKnown)
              ? '<span class="ord-tab-n cc" title="Could not read which orders were marked as bought">—</span>'
              : '<span class="ord-tab-n' + (bad ? ' bad' : '') + '">' + c[t[0]] + '</span>') + '</button>';
      }).join("")
    + '</div>';
}

/* THE NEXT SHIP-BY, AS A COUNTDOWN. The plan's "dispatch cutoff 14:00" -- this
 * app has no cutoff setting, so it counts to the earliest ship-by Amazon set
 * on an order still to dispatch, which is the deadline that actually costs a
 * late-shipment mark. Warning under 2 hours, danger under 30 minutes. */
function _ordNextDue(rows){
  let best = null;
  (rows || []).forEach(function(r){
    if(_ordState(r) !== "dispatch") return;
    const ms = _ordShipMs(r.ship_by);
    if(ms !== null && (best === null || ms < best.ms)) best = {ms: ms, r: r};
  });
  return best;
}

function _ordLeft(ms){
  const m = Math.max(0, Math.round(ms / 60000));
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  return d ? (d + "d " + h + "h") : (h ? (h + "h " + mm + "m") : (mm + "m"));
}

function _ordCountdownHtml(rows){
  const n = _ordNextDue(rows);
  if(!n) return '<span class="ord-due-head cc">Nothing waiting to dispatch</span>';
  const left = n.ms;
  const tone = left < 30 * 60000 ? " bad" : (left < 2 * 3600000 ? " warn" : "");
  return '<span class="ord-due-head' + tone + '" title="The earliest ship-by date Amazon set on an '
    + 'order still to dispatch. Post it before then, or Amazon counts it late.">'
    + 'Next ship-by ' + _oEsc(_oWhen(n.r.ship_by)) + ' · <b>' + _ordLeft(left) + ' left</b></span>';
}

/* DUE / NEXT: what the clock says for this order, by its state. */
function _ordDueCell(r){
  const s = _ordState(r);
  if(s === "dispatch" || (s === "problem" && r.ship_by && Number(r.unshipped || 0) > 0)){
    const left = _ordShipMs(r.ship_by);
    if(left === null) return '<span class="cc">no ship-by date</span>';
    if(left < 0) return '<span class="ord-due bad">late by ' + _ordLeft(-left) + '</span>';
    const tone = left < 24 * 3600000 ? " warn" : "";
    return '<span class="ord-due' + tone + '">ship by ' + _oEsc(_oWhen(r.ship_by))
      + '<br><span class="cc">' + _ordLeft(left) + ' left</span></span>';
  }
  if(s === "tracking") return '<span class="ord-due warn">no tracking yet</span>';
  if(s === "transit" || s === "done") return _ordParcelCell(r);
  if(s === "problem" && (r.tracking || []).length) return _ordParcelCell(r);
  if(s === "shipped") return '<span class="cc" title="No tracking recorded in this app. Amazon does not send back tracking entered in Seller Central.">shipped</span>';
  if(s === "waiting") return '<span class="cc">payment not cleared</span>';
  if(s === "fba") return '<span class="cc">Amazon ships it</span>';
  return '<span class="cc">—</span>';
}

/* THE ONE NEXT STEP, per the plan's table -- but every one of them OPENS the
 * order (its panel has the sources to buy from, the tracking box and the
 * details). None of them does the thing it names; see the top of this file. */
const _ORD_NEXT = {
  dispatch: ["Dispatch", "primary", "Open this order: where to buy it from, and the tracking box once it is posted"],
  tracking: ["Add tracking", "primary", "Open this order to record its tracking number"],
  problem:  ["See problem", "danger", "Open this order to see what is wrong"],
  transit:  ["Track", "", "Open this order to see where the parcel is"],
  fba:      ["View", "", "Open this order"],
  waiting:  ["View", "", "Open this order -- Amazon is still taking payment, so do not buy or post yet"],
  done:     ["View", "", "Open this order"],
  shipped:  ["View", "", "Open this order"],
  closed:   ["View", "", "Open this order"],
  other:    ["View", "", "Open this order"],
};

function _ordNextBtn(r){
  const n = _ORD_NEXT[_ordState(r)] || _ORD_NEXT.other;
  return '<button type="button" class="ord-next ' + n[1] + '" title="' + _oEsc(n[2]) + '"'
    + ' data-fk="next:' + _oEsc(r.order_id) + '"'
    + ' onclick="event.stopPropagation();ordersToggle(' + jsArg(r.order_id) + ',' + jsArg(r.account_id) + ')">'
    + _oEsc(n[0]) + '</button>';
}

function _ordChannelCell(r){
  const f = String(r.fulfilment || "").toUpperCase();
  if(f === "AFN") return '<span class="ord-ch fba" title="Fulfilled by Amazon">FBA</span>';
  if(f === "MFN") return '<span class="ord-ch fbm" title="Fulfilled by you">FBM</span>';
  return '<span class="cc">' + _oEsc(f || "—") + '</span>';
}

/* ---- selection: which orders are ticked (this account's rows only) ---- */
function _ordSel(){ if(!ORD.sel) ORD.sel = new Set(); return ORD.sel; }

function ordersSelToggle(oid, on){
  const s = _ordSel();
  if(on) s.add(String(oid)); else s.delete(String(oid));
  ordersRender();
}

function ordersSelAllShown(on){
  const s = _ordSel();
  _ordVisible(ORD.rows).forEach(function(r){ if(on) s.add(String(r.order_id)); else s.delete(String(r.order_id)); });
  ordersRender();
}

function ordersSelClear(){ _ordSel().clear(); ordersRender(); }

/* Order numbers of the ticked orders, one per line, onto the clipboard. The one
 * bulk action that is live: it only copies text. */
function ordersCopyIds(){
  const ids = (ORD.rows || []).map(function(r){ return String(r.order_id); })
    .filter(function(id){ return _ordSel().has(id); });
  if(typeof uiCopy === "function") uiCopy(ids.join("\n"), ids.length + " order number" + (ids.length === 1 ? "" : "s") + " copied");
}

function _ordBulkBar(){
  const ids = (ORD.rows || []).filter(function(r){ return _ordSel().has(String(r.order_id)); });
  if(!ids.length) return "";
  const off = 'disabled title="Not switched on yet. Each real action on orders is wired only with the owner\'s OK."';
  return '<div class="ord-bulk" role="region" aria-label="Selected orders">'
    + '<b>' + ids.length + ' selected</b>'
    + '<button type="button" class="db-chip" data-fk="bulk:copy" onclick="ordersCopyIds()"><i class="ti ti-copy"></i> Copy order numbers</button>'
    + '<button type="button" class="db-chip" ' + off + '><i class="ti ti-shopping-cart"></i> Buy from suppliers</button>'
    + '<button type="button" class="db-chip" ' + off + '><i class="ti ti-truck-delivery"></i> Mark dispatched</button>'
    + '<span class="spacer" style="flex:1"></span>'
    + '<button type="button" class="db-chip" data-fk="bulk:clear" onclick="ordersSelClear()">Clear</button>'
    + '</div>';
}

function _ordFiltersHtml(shown, total){
  const ch = ORD.channel || "";
  const chip = function(v, label){
    return '<button type="button" class="db-chip' + (ch === v ? ' on' : '') + '" aria-pressed="'
      + (ch === v ? 'true' : 'false') + '" data-fk="ch:' + (v || 'all') + '" onclick="ordersSetChannel(' + jsArg(v) + ')">' + label + '</button>';
  };
  return '<div class="ord-filters">'
    + '<span class="cc">Channel</span>' + chip("", "All") + chip("MFN", "FBM") + chip("AFN", "FBA")
    + '<span class="spacer" style="flex:1"></span>'
    + '<span class="cc">' + shown + ' shown' + (shown !== total ? ' of ' + total : '') + '</span>'
    + '</div>';
}
