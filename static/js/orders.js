// ===================== ORDERS, ACROSS EVERY ACCOUNT =====================
// One list, newest first, with the account each order belongs to — so seeing
// what sold does not mean opening each Amazon account in turn. Click an order
// number to open its lines.
//
// WHAT IS NOT HERE, AND WHY
// The customer's name, street address and phone number. Amazon does not release
// them to this application: asking is refused outright ("Application does not
// have access to one or more requested data elements: [shippingAddress]"), and
// even the buyer-info token that IS granted comes back empty. Measured on three
// accounts. So the destination column shows the part Amazon does give — town,
// county, postcode, country — under a heading that says what it is. A column
// headed "Address" holding only a postcode invites someone to try to post
// something with it.

// profit:true BY DEFAULT — it is what fills the Item column.
//
// It used to be absent, so falsy, so the item, the picture, the margin and the
// ROI were blank on every row until someone found a toggle and pressed it. That
// is not what was asked for: "i want to see the item picture and name of the
// item and profit and roi and margin or each order without opening the order
// details". Without means without.
//
// It is not free — one Amazon call per order, because an order row carries no
// SKU — which is why it loads in TWO passes: see ordersLoad(). The toggle now
// turns it OFF, for when speed matters more than knowing what sold.
// account:"" MEANS THE WORKSPACE YOU HAVE OPEN, and the server resolves it that
// way. It used to default to "__all__", so opening Orders inside Jack Reacherd
// listed Selvora's and Nestwell's orders too -- with the customer's name and
// address on them.
//
// "i see i can see all the other account orders into jacks workspace"
//
// These are separate limited companies with separate sellers and separate
// customers. routes/orders_routes.py already refuses to default to every
// account, and says why at length; the browser was overriding it by asking for
// __all__ outright. Every account at once is still available, but only by
// choosing it in the picker.
// rowsFor: which workspace the rows on screen belong to. Without it, switching
// account re-rendered the previous company's orders -- see ordersOnOpen.
let ORD = {rows: [], summary: {}, days: 30, account: "", q: "",
           open: "", details: {}, busy: false, profit: true, rowsFor: null};

function _oEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _oMoney(v, cur){
  if(v===null||v===undefined) return "—";
  return (cur ? cur+" " : "") + Number(v).toFixed(2);
}
function _oWhen(iso){
  if(!iso) return "—";
  // Amazon returns RFC3339 in UTC. Shown in the reader's own zone, because an
  // order placed "at 23:40" means different days depending on whose clock.
  try{
    const d = new Date(iso);
    return d.toLocaleString(undefined, {year:"numeric", month:"short",
      day:"2-digit", hour:"2-digit", minute:"2-digit"});
  }catch(e){ return iso; }
}

/* WHAT AMAZON'S ORDER STATUSES ACTUALLY MEAN.
 *
 *     "And i see there is written cancel requested i can not understand what it
 *      means."
 *
 * These are Amazon's own words, shown raw. "PartiallyShipped" and "Unshipped"
 * are guessable; "Pending" and "cancel requested" are not, and both are ones
 * where doing the wrong thing costs money -- Pending orders can still vanish,
 * and posting a parcel after a cancellation request means eating the return.
 *
 * ONE TABLE, used by the row, the panel and the tooltip, so a status cannot be
 * described one way in the list and another way when it is opened (Rule 12).
 *
 *   c     the colour
 *   t     a short human label
 *   m     what it means, in plain words
 *   d     what to do about it, when there is something to do
 */
const _ORD_STATUS = {
  Shipped: {c:"var(--ok)", t:"Shipped", tone:"ok",
    m:"You have dispatched it and told Amazon. Nothing further is needed."},
  Unshipped: {c:"var(--warn)", t:"Not shipped yet", tone:"warn",
    m:"The buyer has paid and it is waiting for you to send it.",
    d:"Post it before the ship-by date below, or Amazon counts it late."},
  PartiallyShipped: {c:"var(--warn)", t:"Partly shipped", tone:"warn",
    m:"Some of the items have gone and some have not.",
    d:"Send the rest before the ship-by date below."},
  Pending: {c:"var(--ink3)", t:"Payment not cleared", tone:"",
    m:"Amazon is still taking the buyer's payment. The address and the items "
     + "are not final yet, and the order can still disappear.",
    d:"Do not buy stock for it or post it until it turns to Unshipped."},
  Canceled: {c:"var(--red)", t:"Cancelled", tone:"bad",
    m:"The order is off. No money will arrive for it.",
    d:"If you have already posted it, claim it back through Amazon."},
  Cancelled: {c:"var(--red)", t:"Cancelled", tone:"bad",
    m:"The order is off. No money will arrive for it.",
    d:"If you have already posted it, claim it back through Amazon."},
  InvoiceUnconfirmed: {c:"var(--ink3)", t:"Awaiting invoice", tone:"",
    m:"Shipped, but Amazon is waiting for the invoice for a business buyer."},
  Unfulfillable: {c:"var(--red)", t:"Cannot be fulfilled", tone:"bad",
    m:"Amazon cannot fulfil it from your stock — usually there is none in the "
     + "warehouse, or the item is not sellable."},
};

/* WHERE THE PARCEL IS, as opposed to whether we have marked it shipped.
 *
 * The colours say the same thing the words do, and three of these are not about
 * the parcel at all -- "Not checked" means nobody has asked, "Carrier has no
 * record" means somebody asked and the carrier does not know the number, and
 * those need doing different things about. A mistyped tracking number looks
 * exactly like an unchecked one unless the two are told apart.
 *
 * The server owns the words (domain/tracking.STATUS_LABEL); this owns only how
 * they look, so the two can never drift into naming a status differently. */
const _ORD_PARCEL = {
  pre_transit:        {c:"var(--ink3)", i:"ti-tag",
    m:"A label exists. The carrier has not had the parcel yet."},
  collected:          {c:"var(--as-info)", i:"ti-package",
    m:"The carrier has it."},
  in_transit:         {c:"var(--as-info)", i:"ti-truck",
    m:"On its way."},
  out_for_delivery:   {c:"var(--warn)", i:"ti-truck-delivery",
    m:"Out with the driver today."},
  awaiting_collection:{c:"var(--warn)", i:"ti-building-store",
    m:"At a pickup point, waiting for the buyer to collect it."},
  delivered:          {c:"var(--ok)", i:"ti-circle-check",
    m:"The carrier says it has been delivered."},
  exception:          {c:"var(--red)", i:"ti-alert-triangle",
    m:"Something went wrong — a failed delivery, a hold, or a return."},
  not_found:          {c:"var(--red)", i:"ti-help-circle",
    m:"The carrier was asked and has no record of this number. It is usually "
     + "mistyped, or belongs to a different order."},
  unknown:            {c:"var(--ink3)", i:"ti-clock",
    m:"Nobody has asked the carrier about this one yet."},
};

/* One order's parcels, as one cell.
 *
 * NO TRACKING AND NOT CHECKED ARE DIFFERENT and are drawn differently: an order
 * with no number uploaded says so, because the thing to do about it is upload
 * one, and showing it as "Not checked" would send somebody to press a button
 * that could never help it. */
function _ordParcelCell(r){
  const t = (r && r.tracking) || [];
  if(!t.length){
    return '<span class="cc" style="opacity:.45" title="No tracking number has '
         + 'been uploaded for this order. Use the Tracking sheet buttons above.">'
         + '—</span>';
  }
  const s = (r.tracking_status || {});
  const d = _ORD_PARCEL[s.status] || _ORD_PARCEL.unknown;
  // WHEN IT WAS LAST ASKED, on the label itself. "Delivered" and "it said
  // delivered four days ago and nobody has asked since" are different claims
  // about now, and the second one is the one that gets argued over.
  const when = s.checked_at ? (" · checked " + _oEsc(_oWhen(s.checked_at)))
                            : " · not checked yet";
  let h = '<span style="color:' + d.c + ';white-space:nowrap" title="'
        + _oEsc((d.m || "") + when) + '">'
        + '<i class="ti ' + d.i + '"></i> ' + _oEsc(s.label || "Not checked")
        + (s.count > 1 ? ' <span class="cc">×' + s.count + '</span>' : '')
        + '</span>';
  if(s.stale && s.status !== "unknown"){
    h += '<span class="cc" style="font-size:10px" title="This was last checked '
       + 'more than twelve hours ago, so it may have moved since."> ·  old</span>';
  }
  // THE NUMBERS THEMSELVES, which is what was actually asked for. Wrapped, not
  // truncated: a tracking number with the end cut off cannot be typed into a
  // carrier's website, which is the one thing anybody wants to do with it.
  h += '<div class="cc" style="font-size:10px;line-height:1.5;'
     + 'overflow-wrap:anywhere;margin-top:2px">'
     + t.map(function(x){
         return (x.carrier ? _oEsc(x.carrier) + " " : "")
              + '<code style="font-size:10px">' + _oEsc(x.tracking_number || "")
              + '</code>'
              // The carrier's own words, kept beside our word for them. Every
              // carrier invents its own vocabulary and grouping loses detail
              // the seller sometimes needs.
              + (x.raw_status && x.raw_status !== (s.label || "")
                   ? ' <span title="what the carrier itself said">('
                     + _oEsc(x.raw_status) + ')</span>' : "")
              + (x.check_error
                   ? ' <span style="color:var(--red)" title="' + _oEsc(x.check_error)
                     + '">could not be checked</span>' : "");
       }).join("<br>")
     + '</div>';
  return h;
}

/* The buyer has ASKED to cancel. This is not a status of its own -- it rides on
 * top of one -- so it gets its own entry. It is the single most expensive thing
 * on this screen to misread: the order still reads as a live sale, and posting
 * it means paying to send something that is going to come straight back. */
const _ORD_CANCEL_REQUESTED = {
  t: "Buyer asked to cancel",
  m: "The buyer pressed cancel after ordering. Amazon has not cancelled it "
   + "automatically because it is already too far along, so it is still sitting "
   + "here as a live order.",
  d: "Do not post it. Cancel it in Seller Central, or you pay to send something "
   + "that comes straight back and the buyer can still claim a refund.",
};

/* One status, drawn as a chip with its explanation on hover. `extra` lets the
 * panel add the cancellation request to whatever the status already said. */
function _ordStateChip(status, cancelRequested){
  const s = _ORD_STATUS[status] || {t:String(status||"unknown"), m:"", tone:""};
  const bits = [];
  if(s.m) bits.push(s.m);
  if(s.d) bits.push(s.d);
  let h = '<span class="odp-state ' + (s.tone || '') + '" title="'
        + _oEsc(bits.join(" ")) + '">' + _oEsc(s.t || status) + '</span>';
  if(cancelRequested){
    h += ' <span class="odp-state bad" title="'
      +  _oEsc(_ORD_CANCEL_REQUESTED.m + " " + _ORD_CANCEL_REQUESTED.d) + '">'
      +  '<i class="ti ti-alert-triangle"></i> '
      +  _oEsc(_ORD_CANCEL_REQUESTED.t) + '</span>';
  }
  return h;
}

function ordersOnOpen(){
  // THERE IS NO ACCOUNT PICKER ANY MORE.
  //
  //     "i do not want that option which enables the user to see all the orders
  //      on every account by being in 1 account. i am in nestwell goods why am
  //      i able to see the orders of jack reacherd this should not be
  //      happening"
  //
  // This used to fill a dropdown with EVERY account, so standing in Nestwell
  // you could pick Jack Reacherd and read another company's customers. The
  // "Every account" option was only half of it -- the per-account entries were
  // the other half, and they were added here.
  //
  // Orders belong to the workspace that is open. ORD.account stays "" and the
  // server resolves it, and the server now refuses any other answer, so this
  // cannot be reintroduced from the browser alone.
  ORD.account = "";
  const scope = document.getElementById("ord_scope");
  if(scope){
    const nm = (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.label)
             ? ACTIVE_WS.label : "";
    scope.innerHTML = '<i class="ti ti-lock"></i> ' + _oEsc(nm || "this account");
  }
  // WHOSE ORDERS ARE ON SCREEN RIGHT NOW?
  //
  // This asked only "are there any rows", so switching from Jack Reacherd to
  // Nestwell re-rendered JACK'S rows and never reloaded. Both of the reported
  // faults are that one line:
  //
  //   "i am in nestwell goods why am i able to see the orders of jack reacherd"
  //   "I have received an order on nestwell goods but the app is showing me a
  //    sale in graph but not in the orders tab even after i hit the refresh"
  //
  // The Nestwell order was there the whole time -- MEASURED: order
  // 026-1108972-7232300 for GBP 34.99 is returned by /orders/list and is in
  // sales_daily, which is why the graph had it. The screen was simply showing
  // somebody else's list.
  //
  // So the rows are stamped with the workspace they belong to, and a different
  // workspace forces a reload rather than redrawing the wrong company.
  const _ws = (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.key)
            ? String(ACTIVE_WS.key) : "";
  if(ORD.rowsFor !== _ws){
    ORD.rows = [];
    ORD.details = {};        // per-order panels belong to those rows too
    ORD.open = "";
    ORD.sel = new Set();     // ticked orders belong to those rows too
    ORD.rowsFor = _ws;
  }
  if(!ORD.rows.length) ordersLoad(); else ordersRender();
}

async function ordersLoad(){
  const body = document.getElementById("ordbody");
  if(!body) return;
  // A RELOAD IS NEVER DROPPED. This returned early while another load was in
  // flight, so changing the days or the account during one -- which takes the
  // best part of a minute -- was silently ignored: the screen kept the old
  // window, said nothing, and the toolbar showed the setting you thought you
  // had applied. Measured as a screen showing 35 orders while its own note
  // described 145.
  //
  // Instead every load takes a ticket, and a result is thrown away if a newer
  // load has started since. The most recent request always wins, which is the
  // one the person is actually looking at.
  const mine = ORD.loadId = (ORD.loadId || 0) + 1;
  ORD.busy = true;
  ORD.err = "";
  body.innerHTML = '<div class="cc" style="padding:18px"><span class="genspin"></span> '
    + 'Asking every account for its orders…</div>';
  // Built once, OUTSIDE the try, because the second pass below is handed this
  // exact string and must ask the identical question.
  // THE ACCOUNT TRAVELS WITH THE REQUEST.
  //
  //     "i see the orders of nestwell goods are shown in the jack reacherd
  //      account, and i am not able to see the jack reacherds orders"
  //
  // This used to send an EMPTY account and let the server decide. Every guard
  // on both sides was correct -- measured, each account returns only its own
  // rows -- but with nothing named there was no way for the two to disagree
  // OUT LOUD. If they ever did, the server quietly won and this screen drew
  // another company's customers under the open account's name.
  //
  // Now the browser says whose orders it is drawing, the server refuses a
  // mismatch outright (409), and the answer is checked again below before it
  // is rendered. Three chances to notice instead of none.
  const askedFor = ORD.account
    || ((typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.key)
          ? String(ACTIVE_WS.key) : "");
  const base = "days=" + encodeURIComponent(ORD.days)
             + "&account=" + encodeURIComponent(askedFor)
             + (ORD.q ? "&q=" + encodeURIComponent(ORD.q) : "");
  try{
    const j = await (await fetch("/orders/list?" + base)).json();
    if(mine !== ORD.loadId) return;             // a newer load has taken over
    // AND THE WORKSPACE HAS NOT CHANGED WHILE WE WAITED. The load ticket above
    // catches a newer LOAD; this catches a newer ACCOUNT, which can change
    // without one -- the fetch takes the best part of a minute.
    const nowWs = (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.key)
      ? String(ACTIVE_WS.key) : "";
    if(askedFor && nowWs && askedFor !== nowWs) return;
    if(j && j.account_mismatch){
      ORD.err = j.error || "That is not the account that is open.";
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _oEsc(j.error || "That is not the account that is open.") + '</div>';
      return;
    }
    if(!j || !j.ok){
      // Remembered, so Home can say the orders could not be read rather than
      // count an empty list as zero orders.
      ORD.err = (j&&j.error)||"Could not load orders";
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _oEsc((j&&j.error)||"Could not load orders") + '</div>';
      return;
    }
    ORD.rows = j.rows || []; ORD.summary = j.summary || {}; ORD.meta = j;
    // Ticks only for orders still in the list (days or search changed).
    if(ORD.sel){
      const _ids = new Set(ORD.rows.map(function(r){ return String(r.order_id); }));
      ORD.sel = new Set([...ORD.sel].filter(function(id){ return _ids.has(id); }));
    }
    // Stamped with WHOSE rows these are, so ordersOnOpen can tell a redraw of
    // the right list from a redraw of the last one.
    ORD.rowsFor = nowWs || askedFor;
    ORD.loadedFor = ORD.rowsFor;   // read successfully, for this account (Home)
    ORD.err = "";
    ordersRender();
  }catch(e){
    if(mine === ORD.loadId){
      ORD.err = String(e);
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _oEsc(String(e)) + '</div>';
    }
    return;
  }finally{ if(mine === ORD.loadId) ORD.busy = false; }
  if(mine !== ORD.loadId) return;
  // SECOND PASS, and the reason there are two.
  //
  // What was sold, and what it earned, cost one Amazon call per order — the
  // order row carries no SKU, and without a SKU there is no product and no
  // cost. Sixty of those in a row is most of a minute, so asking for them
  // before drawing anything would leave the screen empty for that long, and
  // that is exactly why this was made opt-in in the first place.
  //
  // So: the list appears at once, and the items fill in behind it. Nobody waits
  // for the whole thing to know whether their orders loaded.
  if(ORD.profit) ordersFillItems(mine);
}

// How many orders to read per screenful. Each is one Amazon call, so this is a
// real ceiling and the screen says when it bites rather than trimming quietly.
const ORD_ITEM_CAP = 60;

// The products and the earnings, for the orders ALREADY on screen.
//
// It asks /orders/items with those orders' ids -- it does NOT fetch the order
// list a second time. Doing that was two full order-feed calls for one screen,
// and Amazon throttled the second: it came back empty and the screen said
// "Profit worked out for all 0", which is indistinguishable from an account
// with no orders.
//
// `mine` is the load ticket from ordersLoad. If a newer load has started -- the
// days changed, the account changed -- this answer is for a question nobody is
// asking any more and is dropped rather than merged onto whatever is now on
// screen.
async function ordersFillItems(mine){
  const st = document.getElementById("ord_fillnote");
  const rows = (ORD.rows || []).slice(0, ORD_ITEM_CAP);
  if(!rows.length) return;
  ORD.filling = true;
  if(st) st.innerHTML = '<span class="genspin"></span> reading what sold — '
                      + rows.length + ' order' + (rows.length===1?'':'s') + '…';
  try{
    const j = await (await fetch("/orders/items", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({orders: rows.map(function(r){
        return {order_id:r.order_id, account_id:r.account_id, total:r.total};
      })})})).json();
    if(mine !== ORD.loadId) return;
    ORD.filling = false;
    if(!j || !j.ok){ if(st) st.textContent = ""; return; }
    const by = j.items || {};
    ORD.rows = (ORD.rows||[]).map(function(r){
      const m = by[r.order_id];
      return m ? Object.assign({}, r, m) : r;
    });
    const over = (ORD.rows||[]).length - rows.length;
    ORD.meta = Object.assign({}, ORD.meta||{}, {profit_note:
      [j.note || "",
       over > 0 ? ("The newest " + rows.length + " were read; " + over
                   + " older ones were not — narrow the days to see those.") : ""
      ].filter(Boolean).join(" ")});
    ordersRender();
  }catch(e){
    ORD.filling = false;
    if(st) st.textContent = "";
  }
}

function ordersSetDays(d){ ORD.days = d; ordersLoad(); }
function ordersToggleProfit(){
  ORD.profit = !ORD.profit;
  const b = document.getElementById("ord_profit");
  if(b) b.classList.toggle("on", ORD.profit);
  ordersLoad();
}
/* Kept as a no-op rather than deleted: an old cached page can still call it,
   and the honest answer is that orders belong to the open workspace. Silently
   switching account is the behaviour being removed, so it does nothing. */
function ordersSetAccount(){ ORD.account = ""; ordersLoad(); }
let _ordTimer = null;
function ordersFilter(v){
  ORD.q = v || "";
  clearTimeout(_ordTimer);
  _ordTimer = setTimeout(ordersLoad, 250);
}

// The picture and the name of what was bought.
//
// THE SERVER RESOLVES THE PICTURE. This used to match against LIVE_ITEMS, the
// catalogue the LISTINGS screen loads -- so opening Orders directly, which is
// how anyone actually opens Orders, left that array empty and every row showed
// a name and a grey placeholder. Now item.img arrives with the row, from the
// same cached snapshot the listing cards use, so one product cannot end up with
// two different pictures in one app.
//
// LIVE_ITEMS is still consulted, but only as a fallback for a product the
// snapshot has not caught up with. An order with several products names the
// first and says how many more, because a row that grows with the order is what
// made this screen cluttered.
function _ordItemImage(item){
  if(!item) return "";
  if(item.img) return item.img;
  const items = (typeof LIVE_ITEMS !== "undefined" && LIVE_ITEMS) ? LIVE_ITEMS : [];
  const norm = v => String(v == null ? "" : v).trim().toUpperCase();
  const sku = norm(item.sku), asin = norm(item.asin);
  let byAsin = "";
  for(const it of items){
    if(!it) continue;
    const url = it.img || it.image || "";
    if(!url) continue;
    if(sku && norm(it.sku) === sku) return url;
    if(asin && !byAsin && norm(it.asin) === asin) byAsin = url;
  }
  return byAsin;
}

function _ordItemCell(r){
  const it = r.item;
  if(!it || (!it.title && !it.sku)){
    // WHY THIS CELL IS EMPTY, and there are two different reasons.
    //
    // Reading what was in an order costs one Amazon call per order, so it only
    // happens when profit is asked for, and then only for the newest N. A row
    // past that ceiling has not been read -- which is not the same as an order
    // with nothing in it, and telling someone to tick a box they have already
    // ticked is worse than saying nothing.
    const why = !ORD.profit
      ? 'turn “work out profit” back on to see the item'
      : (ORD.filling ? 'still reading this one from Amazon…'
                     : 'past the profit limit for this load');
    // A mark, not a sentence (owner, 30 Sep 2026: "less words"); the
    // reason is the hover text.
    return '<span class="cc" style="font-size:11px;opacity:.55" title="'
         + _oEsc(why) + '">' + (ORD.filling ? '<span class="genspin"></span>' : '\u2014') + '</span>';
  }
  const img = _ordItemImage(it);
  return '<div style="display:flex;gap:8px;align-items:center">'
    + (img
        ? '<img src="' + _oEsc(thumbUrl(img, 34)) + '" loading="lazy" decoding="async" style="width:34px;height:34px;'
          + 'object-fit:contain;background:var(--sidebar);border-radius:5px;flex:0 0 34px">'
        : '<span style="width:34px;height:34px;border-radius:5px;background:var(--sidebar);'
          + 'display:inline-flex;align-items:center;justify-content:center;flex:0 0 34px">'
          + '<i class="ti ti-photo" style="opacity:.4"></i></span>')
    + '<span style="min-width:0">'
    // Two lines, not one. A product name cut to "BASED Pomade f..." identifies
    // nothing, and this column had 230px while Profit, Margin and ROI each had
    // a whole column for four characters.
    + '<span style="font-size:11.5px;display:-webkit-box;-webkit-line-clamp:2;'
    + '-webkit-box-orient:vertical;overflow:hidden;line-height:1.25;'
    + 'max-width:330px" title="'
    + _oEsc(it.title || it.sku) + '">' + _oEsc(it.title || it.sku) + '</span>'
    + '<span class="cc" style="font-size:10px">' + _oEsc(it.sku)
    + (it.extra ? (' · +' + it.extra + ' more') : '') + '</span>'
    + '</span></div>';
}

// A percentage, coloured against its OWN thresholds, blank when unknown.
function _ordPct(v, good, ok, title){
  if(v === null || v === undefined)
    return '<span class="cc" style="opacity:.5">—</span>';
  const n = Number(v);
  const col = n >= good ? "var(--ok,#8fd694)" : (n >= ok ? "var(--warn)" : "var(--red)");
  return '<span style="color:' + col + '" title="' + _oEsc(title || '') + '">'
       + n.toFixed(1) + '%</span>';
}

function ordersRender(){
  const body = document.getElementById("ordbody");
  if(!body) return;
  // THE LAST PLACE IT COULD GO WRONG, GUARDED AT THE POINT OF PAINTING.
  //
  // The server is scoped, the request names the account, the reply is checked
  // and the rows are stamped -- and this is still worth having, because it is
  // the only guard that does not depend on any of the others being right. A row
  // belonging to another account is DROPPED here rather than drawn, whatever
  // put it in the list.
  //
  // Measured on this build, across four account switches in a real browser:
  // every row already belonged to the open account, so this drops nothing
  // today. It is here so that it keeps dropping nothing tomorrow.
  const _openWs = (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.key)
    ? String(ACTIVE_WS.key) : "";
  let _foreign = 0;
  if(_openWs && (ORD.rows || []).length){
    const keep = ORD.rows.filter(function(r){
      const rid = String(r.account_id || "");
      if(rid && rid !== _openWs){ _foreign++; return false; }
      return true;
    });
    if(_foreign) ORD.rows = keep;
  }
  const m = ORD.meta || {}, s = ORD.summary || {};
  let h = "";
  if(_foreign){
    // Said out loud rather than silently dropped: if this ever fires, it is a
    // fault worth reporting, not a tidy-up worth hiding.
    h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px;padding:8px 11px;'
      +  'border:1px solid var(--red-line);background:var(--red-bg);border-radius:6px;color:var(--red)">'
      +  '<i class="ti ti-alert-triangle"></i> ' + _foreign + ' order'
      +  (_foreign === 1 ? "" : "s") + ' belonging to another account '
      +  'were not shown. Please report this — it should not happen.</div>';
  }

  // Which accounts answered, and which did not. An account whose token expired
  // is a different fact from having no orders, and the difference is invisible
  // if a failure only removes rows.
  (m.errors || []).forEach(function(e){
    h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px;padding:8px 11px;'
      +  'border:1px solid var(--warn-line);background:var(--warn-bg);border-radius:6px">'
      +  '<i class="ti ti-alert-triangle"></i> <b>' + _oEsc(e.account) + '</b> — '
      +  _oEsc(e.error)
      // AMAZON'S OWN WORDS, KEPT BUT NOT LEADING. The sentence above is what to
      // do about it; this is what to search for when the sentence turns out not
      // to cover the case. Only shown when it says something the sentence does
      // not already -- an unrecognised error is passed through as-is, and
      // printing it twice reads as a rendering fault.
      +  ((e.raw && e.raw !== e.error)
            ? '<div style="opacity:.7;margin-top:4px;font-size:10.5px">Amazon '
              + 'said: ' + _oEsc(e.raw) + '</div>'
            : '')
      +  '</div>';
  });

  // WHAT THE PERIOD CAME TO. This was one thin line of 12.5px text above the
  // table -- the same four facts, in the typography of a caption.
  const cur = Object.keys(s.revenue_by_currency || {});
  // Per currency, never added together: pounds plus dollars is a number that is
  // wrong in both. One card per currency, so two currencies read as two figures
  // rather than one wrong one.
  const _revCards = cur.map(function(c){
    return {label: "Charged" + (cur.length > 1 ? " (" + c + ")" : ""),
            value: _oEsc(c) + " " + Number(s.revenue_by_currency[c]).toFixed(2),
            // SAID OUT LOUD, because the Sales screen shows a different figure
            // for these same orders and neither is wrong. This is what buyers
            // PAID, shipping included; Total Sales on the Sales screen is
            // ordered product sales, which excludes it. On three orders of one
            // item they read 102.21 and 89.97, and an unexplained gap between
            // two of your own screens is worse than either.
            note: "incl. shipping",
            title: "Summed from each order's total, so it includes shipping. "
                 + "The Sales screen shows ordered product sales, which excludes "
                 + "shipping - that is the figure Amazon calls Total Sales."};
  });
  // Profit only exists once the second pass has worked out what sold, so it is
  // shown as unknown until then rather than as zero.
  let _pf = null, _pfCur = "", _pfKnown = 0, _pfBlank = 0;
  (ORD.rows || []).forEach(function(r){
    if(r.profit === null || r.profit === undefined){ _pfBlank++; return; }
    _pf = (_pf === null ? 0 : _pf) + Number(r.profit);
    _pfCur = _pfCur || r.currency || "";
    _pfKnown++;
  });
  // NOTHING COUNTED IS NOT NOTHING SOLD.
  //
  // The banner above already says an account refused. The cards under it went on
  // to print "Orders 0 / last 30 days" and the panel said "No orders in the last
  // 30 days" -- both stated as measurements, in an account where Amazon had
  // simply declined to answer. MEASURED on jack_uk/UK: the Orders API returns
  // Unauthorized, and the screen reported nought orders, nought units and no
  // rows, all of it confident.
  //
  // A count is only a count when somebody was actually able to count. When every
  // account asked came back an error, the figure is UNKNOWN and says so; when
  // some did, the number stands but is marked as partial, because a total that
  // is missing an account is not the total.
  const _asked = (m.accounts_asked || []).length;
  const _failed = (m.errors || []).length;
  const _noneAnswered = _failed > 0 && _failed >= Math.max(1, _asked);
  const _somefailed = _failed > 0 && !_noneAnswered;
  const _partly = _somefailed
    ? " · " + _failed + " of " + _asked + " accounts did not answer"
    : "";
  h += uiStats([
    {label: "Orders",
     value: _noneAnswered ? "—" : (s.orders || 0),
     note: _noneAnswered ? "not known — Amazon refused"
                         : ("last " + ORD.days + " days" + _partly)},
    {label: "Units",
     value: _noneAnswered ? "—" : (s.units || 0),
     note: _noneAnswered ? "not known"
           : ((s.orders ? ((s.units || 0) / s.orders).toFixed(1) : "0")
              + " per order")},
  ].concat(_revCards).concat([
    {label: "Profit", value: (_pf === null ? "" : _oMoney(_pf, _pfCur)),
     tone: (_pf === null) ? "" : (_pf < 0 ? "bad" : "good"),
     note: (_pf === null)
           ? (ORD.profit ? "working out\u2026" : "Profit is off")
           : (_pfBlank ? _pfKnown + " of " + (_pfKnown + _pfBlank)
                         + " costed" : "all orders")},
  ]));

  if(!ORD.rows.length){
    h += '<div class="cc" style="padding:20px;border:1px dashed var(--line2);border-radius:6px">'
      // AN EMPTY LIST BECAUSE NOBODY ANSWERED IS NOT AN EMPTY LIST OF ORDERS.
      // "No orders in the last 30 days" is a finding; this is the absence of
      // one, and saying the first when the second is true is how somebody
      // concludes their account has stopped selling.
      +  (_noneAnswered
            ? '<b>Not known.</b> Amazon would not list orders for '
              + _oEsc((m.accounts_asked || []).join(", ") || "this account")
              + ', so this is empty because nothing could be read — not because '
              + 'nothing sold. The reason is in the message above.'
            : 'No orders in the last ' + ORD.days + ' days'
              + (ORD.q ? ' matching “' + _oEsc(ORD.q) + '”' : '')
              + '. Accounts asked: '
              + _oEsc((m.accounts_asked||[]).join(", ") || "none") + '.'
              + (_somefailed
                   ? ' ' + _failed + ' of them did not answer, so orders they '
                     + 'hold would not be here either way.'
                   : ''))
      +  '</div>';
    body.innerHTML = h; return;
  }

  // The second pass reports itself here — how far it got, and whether it is
  // still going. An Item column that is filling in looks identical to one that
  // gave up, unless it says which.
  // ONLY WHAT NEEDS ACTING ON (owner, 30 Sep 2026: "less words"). "Profit
  // worked out for all 7" is the normal case and says nothing; a cap or an
  // unread order is kept, as a small warning line.
  const _pn = String(m.profit_note || "");
  const _pnPlain = /^Profit worked out for all \d+\.?$/.test(_pn.trim());
  h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px" id="ord_fillnote">'
    +  ((_pn && !_pnPlain)
        ? '<i class="ti ti-alert-triangle" style="color:var(--warn)"></i> ' + _oEsc(_pn)
        : (ORD.filling
            ? '<span class="genspin"></span> working out profit…' : ''))
    +  '</div>';

  // FEWER COLUMNS, MORE IN EACH.
  //
  // "the orders tab on the screen is too cluttered maybe it needs resizing and
  //  also i want to see the item picture and name of the item and profit and roi
  //  and margin or each order without opening the order details"
  //
  // Nine columns at a 900px minimum, and the two things you actually want --
  // what was sold and what it made -- were the two that were not there.
  //
  // Account only appears when more than one is on screen; on a single account
  // it repeated the same word down the page. Ships-to and Channel move into the
  // Placed cell as small print, because they are things you glance at, not
  // things you compare down a column.
  const _multi = (function(){
    const seen = {};
    (ORD.rows || []).forEach(function(r){ seen[r.account_id || ""] = 1; });
    return Object.keys(seen).length > 1;
  })();
  // EACH HEADING SAYS WHAT IS UNDER IT, on a second line.
  //
  //     "Column headers use sentence case with a subtitle line."
  //
  // Every one of these cells carries TWO facts -- the order id and its unit
  // count, the date and the fulfilment channel, the status and how many are
  // left to ship -- and the heading named only the first. The same pattern as
  // the listings table's own two-line headers, and the same class, so the two
  // tables cannot end up with two answers to "what does a column heading look
  // like" (Rule 12).
  const _COLSUB = {
    Item: "product, SKU", Order: "ID, units", Account: "which company",
    Placed: "date, fulfilment", Status: "and what is left to ship",
    Parcel: "carrier, tracking",
    Total: "buyer paid", Profit: "after fees and cost",
    Margin: "of the price", ROI: "on the cost",
  };
  // THE PLAN'S LAYOUT (design package Direction A, "Orders"; owner, 29 Sep 2026:
  // "Layout first"). Tabs by what each order needs, the next ship-by as a
  // countdown, a channel filter, ticking rows, and the plan's columns. Read
  // only: every "Next step" opens the order -- see static/js/orders_board.js.
  //
  // NOTHING THE OWNER ASKED TO SEE ON THE ROW IS LOST ("i want to see the item
  // picture and name of the item and profit and roi and margin of each order
  // without opening the order details"): picture and name in Item, margin and
  // ROI under Profit, and the total the buyer paid under the order number.
  _COLSUB.Order = "ID, placed, paid";
  _COLSUB.Item = "product, ASIN";
  _COLSUB.Channel = "who ships it";
  _COLSUB.State = "Amazon's word";
  _COLSUB["Due / next"] = "ship-by, or the parcel";
  _COLSUB.Cost = "stock";
  _COLSUB.Profit = "margin · ROI";
  _COLSUB["Next step"] = "opens the order";
  const cols = ['sel', 'Order', 'Item'].concat(_multi ? ['Account'] : [])
               .concat(['Channel', 'State', 'Due / next', 'Cost', 'Profit', 'Next step']);
  const _shown = _ordVisible(ORD.rows);
  h += '<div class="ord-board">' + _ordCountdownHtml(ORD.rows) + _ordTabsHtml(ORD.rows)
    +  _ordFiltersHtml(_shown.length, ORD.rows.length) + _ordBulkBar() + '</div>';
  const _allTicked = _shown.length > 0 && _shown.every(function(r){ return _ordSel().has(String(r.order_id)); });
  // THE ORDER BESIDE THE TABLE, on a laptop or wider (owner decision, 28 Sep
  // 2026: "keep the Orders table as the main view; selecting an order may open
  // the side detail panel; the panel must not replace the table workflow").
  // A second column, not an overlay: every row stays visible and clickable, and
  // clicking another row swaps the panel. Narrower than 1100px there is no room
  // for two columns, so the order opens under its row as it always has.
  const _side = _ordSideMode();
  const _openRow = _side && ORD.open
    ? ORD.rows.filter(function(r){ return r.order_id === ORD.open; })[0] : null;
  if(_openRow) h += '<div class="ord-split"><div class="ord-main">';
  // THE LIST GOES COMPACT WHILE AN ORDER IS OPEN BESIDE IT (owner, 30 Sep
  // 2026: "i liked the previous version ... but the words in each other").
  // Nine columns beside a panel is what overprinted; with the order open, the
  // list keeps the tick, the order, the item, the state and the profit, and the
  // rest is in the panel. CSS only (.ord-compact) -- the cells are the same.
  h += '<div class="panelcard" style="padding:0;overflow:hidden">'
    +  '<div style="overflow-x:auto"><table class="kv ordtable ord-board-table'
    +  (_openRow ? ' ord-compact' : '') + '" '
    +  'style="width:100%;min-width:760px">'
    +  '<thead><tr>'
    +  cols.map(function(t){
         if(t === 'sel'){
           return '<th class="ord-selcell"><input type="checkbox" data-fk="selall" aria-label="Select every order shown"'
                + (_allTicked ? ' checked' : '') + ' onchange="ordersSelAllShown(this.checked)"></th>';
         }
         // One word per heading; what it holds is the hover text (owner,
         // 30 Sep 2026: "too much text scattered").
         return '<th data-label="' + _oEsc(t) + '"' + (t === 'Item' ? ' style="width:28%"' : '')
              + (_COLSUB[t] ? ' title="' + _oEsc(_COLSUB[t]) + '"' : '') + '>'
              + (t === 'Due / next' ? 'Due' : t === 'Next step' ? '' : t)
              + '</th>'; }).join("")
    +  '</tr></thead><tbody>';

  // "To buy" with the purchase records unreadable is UNKNOWN, not empty: saying
  // "Nothing in this tab" would read as "nothing left to buy" (change review).
  const _buyUnknown = (typeof _ordTab === "function" && _ordTab() === "tobuy"
                       && typeof _ordBuyKnown === "function" && !_ordBuyKnown(ORD.rows));
  if(!_shown.length && _buyUnknown){
    h += '<tr><td colspan="' + cols.length + '" class="cc" style="padding:16px">'
      +  'Could not read which orders were marked as bought, so this tab cannot '
      +  'say what is still to buy. Reload the page to try again.'
      +  '</td></tr>';
  }else if(!_shown.length){
    h += '<tr><td colspan="' + cols.length + '" class="cc" style="padding:16px">'
      +  'Nothing in this tab' + (ORD.channel ? ' for this channel' : '') + '. '
      +  (ORD.rows.length ? 'The other tabs hold the rest of the ' + ORD.rows.length + ' orders.' : '')
      +  '</td></tr>';
  }
  _shown.forEach(function(r){
    const isOpen = (ORD.open === r.order_id);
    const ticked = _ordSel().has(String(r.order_id));
    // Reachable from the keyboard: Tab to a row, Enter or Space opens it.
    h += '<tr class="ordrow' + (isOpen ? ' isopen' : '') + (ticked ? ' rowon' : '') + '" tabindex="0"'
      +  ' aria-expanded="' + (isOpen ? 'true' : 'false') + '"'
      +  ' data-oid="' + _oEsc(r.order_id) + '"'
      +  ' onkeydown="ordersRowKey(event,' + jsArg(r.order_id) + ',' + jsArg(r.account_id) + ')"'
      +  ' onclick="ordersToggle('
      +  jsArg(r.order_id) + ',' + jsArg(r.account_id) + ')">'
      +  '<td class="ord-selcell" onclick="event.stopPropagation()"><input type="checkbox"'
      +  ' data-fk="sel:' + _oEsc(r.order_id) + '"'
      +  ' aria-label="Select order ' + _oEsc(r.order_id) + '"' + (ticked ? ' checked' : '')
      +  ' onchange="ordersSelToggle(' + jsArg(r.order_id) + ', this.checked)"></td>'
      +  '<td data-label="Order" style="white-space:nowrap;min-width:158px">'
      +  '<code style="font-size:11px;color:var(--accent2)">' + _oEsc(r.order_id)
      +  '</code>' + (isOpen ? ' <i class="ti ti-chevron-down ord-chev"></i>'
                             : ' <i class="ti ti-chevron-right ord-chev" style="opacity:.4"></i>')
      +  '<div class="cc" style="font-size:10.5px" title="' + _oEsc(_oWhen(r.purchased)) + '">'
      +  _oEsc(_ordShortDay(r.purchased)) + ' · <b style="color:var(--ink)">'
      +  _oEsc(_oMoney(r.total, r.currency)) + '</b>'
      +  (Number(r.units || 0) > 1 ? ' · ×' + Number(r.units) : '') + '</div>'
      +  '</td>'
      +  '<td data-label="Item" style="min-width:200px">' + _ordItemCell(r) + '</td>'
      +  (_multi ? ('<td data-label="Account" style="font-size:11.5px">' + _oEsc(r.account) + '</td>') : '')
      +  '<td data-label="Channel">' + _ordChannelCell(r)
      +  ((r.prime || r.business) ? '<div class="cc" style="font-size:10px">'
          + (r.prime ? 'Prime' : '') + (r.prime && r.business ? ' · ' : '') + (r.business ? 'Business' : '') + '</div>' : '')
      +  '</td>'
      // AMAZON'S WORD, WITH WHAT IT MEANS ON HOVER -- the same chip the order
      // panel uses (_ordStateChip), so the list and the panel cannot describe
      // one status two ways (Rule 12).
      +  '<td data-label="State" style="font-size:11.5px">'
      +  _ordStateChip(r.status, r.item && r.item.cancel_requested)
      +  (Number(r.unshipped || 0) > 1 ? '<div class="cc" style="font-size:10px;white-space:nowrap">'
                        + r.unshipped + ' to ship</div>' : '')
      +  '</td>'
      +  '<td data-label="Due / next" style="font-size:11.5px">' + _ordDueCell(r) + '</td>'
      +  '<td data-label="Cost" style="font-size:11.5px;white-space:nowrap">'
      +  (r.cogs != null ? _oEsc(_oMoney(r.cogs, r.currency))
                         : '<span class="cc" style="opacity:.5" title="No cost recorded for what sold">—</span>')
      +  '</td>'
      // WHAT IT EARNED. Blank rather than zero when a cost is unknown -- a
      // partial cost only ever makes an order look better than it was, and the
      // order whose cost is missing is exactly the one someone would use to
      // justify buying more.
      +  '<td data-label="Profit" style="font-size:11.5px;white-space:nowrap"'
      +  (r.profit_note ? ' title="' + _oEsc(r.profit_note) + '"' : '') + '>'
      +  (r.profit === undefined
          ? '<span class="cc" style="opacity:.5">—</span>'
          : r.profit === null
            ? '<span class="cc" title="' + _oEsc(r.profit_note || "")
              + '">not known</span>'
            : '<span style="color:' + (r.profit > 0 ? "var(--ok,#8fd694)" : "var(--red)")
              + '">' + _oEsc(_oMoney(r.profit, r.currency)) + '</span>')
      // MARGIN AND ROI answer different questions -- margin says whether the
      // PRICE is any good, ROI whether the stock was worth BUYING -- so each
      // keeps its own threshold, and neither is invented when the cost is not.
      +  '<div style="font-size:10.5px">'
      +  _ordPct(r.margin_pct, 20, 8, 'Profit as a share of what the buyer paid, after VAT')
      +  ' · ROI ' + _ordPct(r.roi_pct, 30, 12, 'Profit as a share of what the stock cost') + '</div>'
      +  '</td>'
      +  '<td data-label="Next step">' + _ordNextBtn(r) + '</td>'
      +  '</tr>';
    if(isOpen && !_openRow){
      h += '<tr class="orddetail"><td colspan="' + cols.length + '">'
        +  '<div id="orddet_' + _oEsc(r.order_id) + '">'
        +  (ORD.details[r.order_id] ? _ordDetailHtml(r) :
            '<div class="cc" style="padding:10px"><span class="genspin"></span> '
            + 'Reading the order…</div>')
        +  '</div></td></tr>';
    }
  });
  h += '</tbody></table></div></div>';
  if(_openRow){
    h += '</div><aside class="ord-side" aria-label="Order ' + _oEsc(_openRow.order_id) + '">'
      +  '<div class="ord-side-h"><code>' + _oEsc(_openRow.order_id) + '</code>'
      +  '<button class="ord-side-x" data-oid="' + _oEsc(_openRow.order_id) + '" onclick="ordersToggle(' + jsArg(_openRow.order_id)
      +  ',' + jsArg(_openRow.account_id) + ')" aria-label="Close this order" title="Close">'
      +  '<i class="ti ti-x"></i></button></div>'
      +  '<div id="orddet_' + _oEsc(_openRow.order_id) + '">'
      +  (ORD.details[_openRow.order_id] ? _ordDetailHtml(_openRow) :
          '<div class="cc" style="padding:10px"><span class="genspin"></span> '
          + 'Reading the order…</div>')
      +  '</div></aside></div>';
  }

  // WHAT AMAZON WITHHOLDS, said once at the bottom rather than as an empty
  // column with no explanation.
  if(m.pii_note){
    h += '<div class="cc" style="font-size:11px;margin-top:10px;opacity:.75">'
      +  '<i class="ti ti-info-circle"></i> ' + _oEsc(m.pii_note) + '</div>';
  }
  // The redraw replaces the focused row with a new element; see _ordRefocus.
  const _hadRow = _ordFocusedOid();
  body.innerHTML = h;
  if(_hadRow) _ordRefocus(_hadRow);
}

/* WHERE TO BUY THIS ONE FROM.
 *
 * "display the source links in the order details arranged by low to high price,
 *  which tells the user you have received an order and you can place the order
 *  from one of these. also show handling time and profit pounds if the user place
 *  order from each link what will be the profit and when will my order will be
 *  delivered to the buyer"
 *
 * The ranking, the profit and the delivery wording all come from the server
 * (domain/order_sources.py), which the repricer screen also asks -- so the two
 * cannot disagree about which link is cheapest or what it would earn. Nothing is
 * worked out here; this only draws it.
 *
 * A DEAD LINK IS STILL SHOWN, greyed and labelled. Three sources where two have
 * ended is a different situation from one source, and hiding the ended ones makes
 * them look the same.
 */
/* WHAT THE DELIVERY LINE MEANS, said once.
 *
 *     "also show statements like this Free Other Courier 3 days · arrives Wed
 *      19 Aug to Thu 20 Aug to B11AA · 3 days handling · 1 left. like it is and
 *      also explain in a i button somewhere what this line means."
 *
 * Every part of that sentence comes from a different place and two of them are
 * easy to read as each other -- the supplier's dispatch time and the delivery
 * window are both "days", and only one of them is a promise to the buyer.
 */
const _ORD_SHIP_HELP =
  "Each supplier line reads: what their postage costs and who carries it · when "
+ "it would reach the address Amazon gave for this order · how long the supplier "
+ "takes to dispatch it · how many they have left.\n\n"
+ "\"Free Other Courier 3 days\" is the postage option itself — free, an "
+ "unnamed courier, quoted as 3 days in transit.\n\n"
+ "\"arrives Wed 19 Aug to Thu 20 Aug to B11AA\" is eBay's own delivery "
+ "estimate, worked out for that postcode. Without a postcode eBay returns no "
+ "delivery information at all, so one is always sent.\n\n"
+ "\"3 days handling\" is the SUPPLIER's dispatch time, not yours. The handling "
+ "time the app promises Amazon is this plus a safety buffer.\n\n"
+ "\"1 left\" is the stock the supplier says remains. One left is a reason to "
+ "buy now or to line up a second source.";

/* WHERE TO BUY THIS LINE FROM.
 *
 *     "should reflect all the available source links which are provided by the
 *      user ... arranged in order of which the source link is cheapest ... and
 *      also reflect how much will the order cost if the user purchase from each
 *      source and what will be the amount of profit in pounds and in roi"
 *
 * Ranking, cost and profit all come from domain/order_sources.py -- the same
 * function the repricer uses, so the two screens cannot disagree about which
 * link is cheapest or what it would earn. Nothing is worked out here; this only
 * draws it. The rank is re-derived on every read, so a supplier who puts their
 * price up moves down the list by itself.
 *
 * A DEAD LINK IS STILL SHOWN, greyed and labelled. Three sources where two have
 * ended is a different situation from one source, and hiding the ended ones
 * makes them look the same.
 */
/* ONE RENDERER, TWO AMOUNTS OF ROOM.
 *
 *     "the repricer details are taking too much space and looks cluttered,
 *      make it look a good ai, taking less space and still displaying all
 *      information"
 *
 * An ORDER panel shows one order, so the full table is right there: four columns,
 * a sentence under each supplier saying how it ships, and a note explaining what
 * the two money columns mean.
 *
 * The REPRICER draws the same block for every tracked SKU. Measured on jack_uk,
 * 64 SKUs: the page is 19,201px tall and this section is 8,888px of it -- 46% --
 * with "Cheapest first — it re-sorts itself..." repeated 55 times and "this
 * reading is out of date" 57 times. The same two sentences, over and over, are
 * not information after the first reading.
 *
 * So `opts.compact` folds it to ONE line that still carries the answer -- how
 * many suppliers, the cheapest landed cost, what you keep, how many could not be
 * read -- and opens to the identical table on click. Nothing is removed; the
 * default is a summary instead of the whole thing. A second renderer for the
 * narrow case would have drifted from this one (rule 12), so it is an argument.
 */
function _ordSourcesHtml(block, forTitle, view){
  if(!block) return '';
  // `view`, not `opts`: `opts` is already this function's list of supplier
  // options a few lines down, and shadowing it here would have made the compact
  // summary read the settings object as if it were the suppliers.
  const _cmp = !!(view && view.compact);
  // A <details> when folded, so opening it needs no JavaScript and the browser
  // keeps it open while the row redraws around it.
  const _open = _cmp ? '<details class="odp-sec odp-sec-c">' : '<div class="odp-sec">';
  const _shut = _cmp ? '</details>' : '</div>';
  const head = _open
    + (_cmp ? '' :
       '<h4 class="odp-h"><i class="ti ti-shopping-cart"></i>Where to buy it'
       + (forTitle ? '<span class="odp-count">· ' + _oEsc(forTitle) + '</span>' : '')
       + '</h4>');

  // Both of these are a fact worth reading at a glance, so folded they are the
  // summary line itself rather than something to open. _shut, not a literal
  // '</div>': the wrapper is a <details> when compact.
  if(block.error){
    return head
         + (_cmp ? '<summary class="odp-c-sum odp-c-bad">'
                   + '<i class="ti ti-alert-triangle"></i> Could not read the '
                   + 'supplier links</summary>' : '')
         + '<div class="odp-note warn">Could not read the supplier links: '
         + _oEsc(block.error) + '</div>' + _shut;
  }
  const opts = block.options || [], s = block.summary || {};
  if(!opts.length){
    return head
         + (_cmp ? '<summary class="odp-c-sum odp-c-bad">'
                   + '<i class="ti ti-plus"></i> No supplier yet</summary>' : '')
         + '<div class="odp-note">No supplier links are tracked for this '
         + 'SKU. Add one in the Repricer to see where to buy it and what it '
         + 'would earn.</div>' + _shut;
  }

  let h = head;

  /* THE ONE LINE, when there is no room for the table.
   *
   * It has to answer, without opening: can I buy this, for how much, what is
   * left, and is anything wrong. Those are the four the table is read for.
   * "Every supplier is out of stock" is still shouted in full below, because it
   * is the one state where the summary is not enough.
   */
  if(_cmp){
    // The one the table would mark "best", or the first that can be bought at
    // all. Read off the same flag the rows use, not re-derived by sorting here.
    const best = opts.filter(function(o){ return o.cheapest; })[0]
              || opts.filter(function(o){ return o.state !== 'dead'
                     && o.landed !== null && o.landed !== undefined; })[0];
    const dead  = opts.filter(function(o){ return o.state === 'dead'; }).length;
    const unk   = opts.filter(function(o){ return o.state === 'unknown'; }).length;
    const stale = opts.filter(function(o){ return o.stale; }).length;
    const parts = [];
    parts.push('<b>' + opts.length + '</b> supplier' + (opts.length === 1 ? '' : 's'));
    if(best && best.landed !== null && best.landed !== undefined){
      parts.push('best <b>' + _oEsc(_oMoney(best.landed, best.currency)) + '</b>'
                 + (best.label ? ' <span class="cc">'
                    + _oEsc(String(best.label).slice(0, 26)) + '</span>' : ''));
      if(best.profit !== null && best.profit !== undefined){
        parts.push('you keep <b' + (best.profit < 0 ? ' class="neg"' : '') + '>'
          + _oEsc(_oMoney(best.profit, best.currency)) + '</b>'
          + (best.roi_pct === null || best.roi_pct === undefined ? ''
             : ' <span class="cc">' + Number(best.roi_pct).toFixed(0) + '% ROI</span>'));
      }
    }
    // WHAT IS WRONG, counted rather than repeated per row. 57 copies of "this
    // reading is out of date" said the same thing 57 times; "2 out of date"
    // says it once and is the number you act on.
    const warn = [];
    if(dead)  warn.push(dead + ' ended or out of stock');
    if(unk)   warn.push(unk + ' could not be read');
    if(stale) warn.push(stale + ' out of date');
    if(warn.length) parts.push('<span class="odp-c-warn">' + warn.join(' · ') + '</span>');
    h += '<summary class="odp-c-sum">'
      +  '<i class="ti ti-chevron-right odp-c-chev"></i>'
      +  '<i class="ti ti-shopping-cart"></i> '
      +  parts.join('<span class="odp-c-dot">·</span>')
      +  '</summary><div class="odp-c-body">';
  }

  // EVERY LINK GONE. The loudest thing this panel can say, so it goes first: the
  // order has to be fulfilled and there is nowhere to buy it.
  if(s.all_dead){
    h += '<div class="odp-note warn" style="margin:0 0 8px">'
      +  '<i class="ti ti-alert-triangle"></i> <b>Every supplier for this SKU is '
      +  'out of stock or ended.</b> There is nowhere to buy this order from '
      +  'right now.</div>';
  }

  h += '<div class="odp-src">'
    +  '<div class="odp-src-h">#</div>'
    +  '<div class="odp-src-h">Supplier</div>'
    +  '<div class="odp-src-h r">You pay</div>'
    +  '<div class="odp-src-h r">You keep</div>';

  opts.forEach(function(o, _i){
    const dead = o.state === 'dead', unknown = o.state === 'unknown';
    const cls = dead ? ' odp-row-dead' : '';
    // The cheapest buyable one is marked, so the choice is obvious at a glance
    // rather than being inferred from the order of the rows.
    //
    // AND A ROW WITHOUT A RANK IS NUMBERED WHERE IT SITS. o.rank comes from the
    // server and is not always there; when it was missing this printed the word
    // "undefined" in the # column, which is the first thing the eye lands on in
    // that table. The rows are already in the order the server chose, so the
    // position IS the rank -- there is nothing to work out.
    const rank = (o.rank === null || o.rank === undefined || o.rank === "")
      ? (_i + 1) : o.rank;
    h += '<div class="odp-rank' + (o.cheapest ? ' best' : '') + cls + '">'
      +  (o.cheapest ? 'best' : (dead ? '—' : (unknown ? '?' : rank)))
      +  '</div>'
      +  '<div class="' + cls.trim() + '"><a class="odp-link" target="_blank" '
      +  'rel="noopener noreferrer" href="' + _oEsc(o.url) + '">'
      +  _oEsc(o.label || o.url) + '</a></div>'
      // LANDED COST -- the item plus its postage, which is what leaves the bank.
      // data-lbl carries the column heading down onto the cell. On a phone the
      // four columns stack into two and the header row is dropped, so without
      // this the numbers would be two unlabelled amounts sitting side by side.
      // The attribute is inert on a desktop, where the header row is still there.
      +  '<div class="odp-num r' + cls + '" data-lbl="You pay">'
      +  (o.landed === null || o.landed === undefined
          ? '<span class="cc">—</span>'
          : _oEsc(_oMoney(o.landed, o.currency)))
      +  '</div>'
      // PROFIT IN POUNDS, with ROI beside it -- both were asked for by name.
      +  '<div class="odp-num r' + cls
      +  (o.profit !== null && o.profit !== undefined && o.profit < 0
          ? ' neg' : '') + '" data-lbl="You keep">'
      +  (o.profit === null || o.profit === undefined
          ? '<span class="cc">—</span>'
          : '<b>' + _oEsc(_oMoney(o.profit, o.currency)) + '</b>'
            + (o.roi_pct === null || o.roi_pct === undefined ? ''
               : '<span class="sub"> · ' + Number(o.roi_pct).toFixed(0)
                 + '% ROI</span>'))
      +  '</div>';

    // HOW IT GETS THERE AND WHEN -- ONE PILL PER FACT, not one sentence.
    //
    //     "Shipping details for each supplier should use clean tagged pills
    //      under the supplier name instead of a wall of text."
    //
    // It was five separate facts joined with middots:
    //
    //     Free Royal Mail Tracked 48 · arrives Mon 7 Sep to Wed 9 Sep to B11AA
    //     · 5 days handling · 10 left
    //
    // and at 10px across a full-width row nothing in it was findable. The facts
    // are unchanged and none is dropped; each gets its own chip with an icon
    // that says which kind of fact it is, so "when does it arrive" and "how many
    // are left" are picked out by shape rather than by reading the line.
    //
    // THE PROBLEMS STAY AS SENTENCES. Out of stock, a failed read and a stale
    // price are not attributes of the delivery -- they are reasons this supplier
    // may not be usable at all, and a chip the same size as "5d handling" would
    // bury them.
    const pill = function(icon, text, extra){
      return '<span class="sup-ship-tag' + (extra ? ' ' + extra : '') + '">'
           + '<i class="ti ti-' + icon + '"></i>' + _oEsc(text) + '</span>';
    };
    let pills = "";
    if(o.postage_text) pills += pill('truck', o.postage_text);
    if(o.delivery_text) pills += pill('calendar', 'Arrives ' + o.delivery_text);
    if(o.delivery_postcode) pills += pill('map-pin', 'to ' + o.delivery_postcode);
    if(o.dispatch_days !== null && o.dispatch_days !== undefined){
      pills += pill('clock', o.dispatch_days + 'd handling');
    }
    if(o.available_qty !== null && o.available_qty !== undefined){
      pills += pill('package', o.available_qty + ' left');
    }
    const bits = [];
    if(dead){
      bits.push(o.status === 'gone' ? 'the listing has ended' : 'out of stock');
    }
    if(unknown && o.error) bits.push('could not read it: ' + _oEsc(o.error));
    // A PRICE FROM YESTERDAY IS NOT A PRICE. Said plainly rather than left for
    // someone to work out from a timestamp.
    if(o.stale) bits.push('this reading is out of date — press Check in the Repricer');
    h += '<div class="odp-ship' + cls + '">'
      +  (pills ? '<span class="sup-ship-tags">' + pills + '</span>' : '')
      +  (bits.length ? '<span class="odp-shipwarn">' + bits.join(' · ')
                        + '</span>' : '')
      +  '</div>';
  });
  h += '</div>';

  // WHAT THE PROFIT IS MEASURED AGAINST, and what that delivery line means.
  //
  // ONCE PER SCREEN WHEN THERE ARE MANY. This sentence never changes, and the
  // repricer drew it under all 55 supplier blocks -- the same 180 characters,
  // 55 times, which is a paragraph of the page spent saying one thing. The
  // repricer states it once above the list instead; an order panel shows one
  // order, so it keeps it where it is.
  if(!_cmp){
    h += '<div class="odp-note">'
      +  '<button class="odp-i" type="button" title="' + _oEsc(_ORD_SHIP_HELP)
      +  '" aria-label="What the delivery line means">i</button> '
      +  'Cheapest first — it re-sorts itself when a supplier changes their price. '
      +  '“You pay” is their price plus their postage. '
      +  (block.unit_price !== null && block.unit_price !== undefined
          ? '“You keep” is what is left of the '
            + _oEsc(_oMoney(block.unit_price, (opts[0] || {}).currency))
            + ' this buyer actually paid, after Amazon’s fee and that supplier.'
          : '“You keep” is what is left after Amazon’s fee and that supplier.')
      +  '</div>';
  }
  return h + (_cmp ? '</div>' : '') + _shut;
}

/* WHAT THE ORDER EARNED, AND WHERE IT WENT.
 *
 * "i am not able to see the earnings of each order and not the breakdown of the
 *  item that how many are cogs how much fee deducted, i dont find the
 *  calculations accurate"
 *
 * A single "Earned 4.20" cannot be checked. This lays the sum out so every number
 * can be argued with: what the buyer paid, Amazon's cut, what the stock cost,
 * what is left -- per line and then for the order.
 *
 * A LINE WITH NO COST STILL APPEARS, naming its own gap. The order's total profit
 * is still withheld when any line is uncosted (a total that ignores one product
 * is worse than no total), but the panel now says WHICH product and what to do.
 */
function _ordBreakdownHtml(bd, currency, orderId, accountId, marketplace){
  if(!bd || !bd.lines || !bd.lines.length) return '';
  const t = bd.totals || {};
  const money = function(v){
    return (v === null || v === undefined)
      ? '<span class="cc">—</span>' : _oEsc(_oMoney(v, currency));
  };
  const actual = (t.fees_basis === "actual");
  let h = '<div class="odp-sec">'
        + '<h4 class="odp-h"><i class="ti ti-receipt-pound"></i>What it earned'
        + '<span class="odp-count">· ' + (actual
            ? 'Amazon’s own settled figures'
            : 'fee estimated until Amazon settles it') + '</span></h4>'
        + '<table style="width:100%;font-size:11px;border-collapse:collapse">'
        + '<thead><tr style="color:var(--ink2);text-align:right">'
        + '<th style="text-align:left;font-weight:500;padding:2px 4px">Item</th>'
        + '<th style="font-weight:500;padding:2px 4px">Buyer paid</th>'
        + '<th style="font-weight:500;padding:2px 4px">Amazon fee</th>'
        + '<th style="font-weight:500;padding:2px 4px">Cost</th>'
        + '<th style="font-weight:500;padding:2px 4px">Profit</th>'
        + '</tr></thead><tbody>';
  bd.lines.forEach(function(l){
    h += '<tr style="text-align:right;border-top:1px solid var(--line2)">'
      +  '<td style="text-align:left;padding:3px 4px;max-width:190px">'
      +  '<span style="display:block;overflow:hidden;text-overflow:ellipsis;'
      +  'white-space:nowrap" title="' + _oEsc(l.title) + '">'
      +  _oEsc(l.title || l.sku || '(no title)') + '</span>'
      +  '<code class="cc" style="font-size:9.5px">' + _oEsc(l.sku)
      +  (l.qty > 1 ? ' · ' + l.qty + ' units' : '') + '</code></td>'
      +  '<td style="padding:3px 4px">' + money(l.revenue) + '</td>'
      // Shown as a deduction, with a minus, so the row reads as a sum rather
      // than as four unrelated numbers.
      +  '<td style="padding:3px 4px;color:var(--warn)">'
      +  (l.fee === null || l.fee === undefined ? money(null)
          : '−' + _oEsc(_oMoney(l.fee, currency))) + '</td>'
      // THE COST, AND WHERE IT CAME FROM, on the row whose profit it decided.
      //
      //     "the profit i see how can i know it is calculated using these cogs"
      //
      // The number alone cannot answer that: 14.99 read out of the SKU and
      // 14.99 typed in by hand look identical, and only one of them is the
      // figure the owner just uploaded. cogs_source has always come back on
      // every line (domain/orders_view.py:382) and nothing displayed it, so
      // the profit was traceable in the data and not on the screen.
      +  '<td style="padding:3px 4px;color:var(--warn)" title="'
      +  _oEsc(l.cogs_source === "manual-order" || l.cogs_source === "frozen"
               ? "This is the cost you set for this order. The profit beside it "
                 + "is worked out from this number."
               : l.cogs_source === "manual"
               ? "A cost you set against this product, used for every order of it."
               : l.cogs_source === "tracked"
               ? "The supplier's price at the moment this order arrived."
               : l.cogs_source === "sku"
               ? "Read from the cost written into the SKU. Set a cost for this "
                 + "order to override it."
               : "No cost is known for this line, so nothing was subtracted and "
                 + "the profit is higher than the truth.") + '">'
      +  (l.cogs === null || l.cogs === undefined ? money(null)
          : '−' + _oEsc(_oMoney(l.cogs, currency))
            + (l.qty > 1 && l.unit_cost !== null
                ? ' <span class="cc">(' + _oEsc(_oMoney(l.unit_cost, currency))
                  + ' ea)</span>' : ''))
      +  ((l.cogs_source === "manual-order" || l.cogs_source === "frozen")
          ? ' <span class="cc" style="font-size:9.5px">yours</span>' : '')
      +  '</td>'
      +  '<td style="padding:3px 4px;font-weight:600'
      +  (l.profit !== null && l.profit !== undefined && l.profit < 0
          ? ';color:var(--red)' : '') + '">'
      +  money(l.profit)
      +  (l.roi_pct !== null && l.roi_pct !== undefined
          ? ' <span class="cc" style="font-weight:400">'
            + Number(l.roi_pct).toFixed(0) + '%</span>' : '')
      +  '</td></tr>';
    // The gap, named on the line it belongs to rather than as one message for
    // the whole order.
    if(l.note){
      h += '<tr><td colspan="5" class="cc" style="padding:0 4px 4px;'
        +  'font-size:10px;color:var(--gold)">' + _oEsc(l.note) + '</td></tr>';
    }
  });
  h += '</tbody><tfoot><tr style="text-align:right;border-top:1px solid var(--line2)">'
    +  '<td style="text-align:left;padding:4px;font-weight:600">Order</td>'
    +  '<td style="padding:4px">' + money(t.revenue) + '</td>'
    +  '<td style="padding:4px;color:var(--warn)">'
    +  (t.fees === null || t.fees === undefined ? money(null)
        : '−' + _oEsc(_oMoney(t.fees, currency))) + '</td>'
    +  '<td style="padding:4px;color:var(--warn)">'
    +  (t.cogs_complete ? '−' + _oEsc(_oMoney(t.cogs, currency))
        : '<span class="cc">part only</span>') + '</td>'
    +  '<td style="padding:4px;font-weight:700">' + money(t.profit) + '</td>'
    +  '</tr></tfoot></table>';

  // WHY A TOTAL IS MISSING, and what the fee figure really is.
  const notes = [];
  if(t.profit === null && t.uncosted_lines){
    notes.push(t.uncosted_lines + ' item' + (t.uncosted_lines === 1 ? '' : 's')
      + ' above have no cost recorded, so the order total is left blank rather '
      + 'than counting them as free. Set a cost for THIS order below, or set '
      + 'the product\'s cost on the Costs sheet to fix it everywhere.');
  }
  // VAT, taken out of each line's profit at the account's own setting -- the
  // columns above are what the buyer paid, so without this the row would not
  // add up to the profit beside it.
  if(Number(t.vat) > 0){
    notes.push('VAT of ' + _oMoney(t.vat, currency)
      + (t.vat_rate ? ' (this account’s ' + Math.round(Number(t.vat_rate) * 1000) / 10
                      + '%)' : '')
      + ' is inside what the buyer paid and has been taken out of the profit — '
      + 'it is collected for HMRC, not earned.');
  }
  if(t.order_total !== null && t.order_total !== undefined
     && Math.abs((t.revenue || 0) - t.order_total) > 0.02){
    notes.push('The buyer was charged ' + _oMoney(t.order_total, currency)
      + ' in total — the difference from the lines above is postage, gift wrap '
      + 'or a coupon.');
  }
  // WHERE THE FEE CAME FROM. Amazon's own settled figure once it has one, and
  // said as such -- the panel used to call every fee an estimate, including the
  // ones Amazon had already itemised.
  if(actual){
    notes.push('Amazon has settled this order, so the fee above is what it '
      + 'actually took — referral, and FBA where it applied — split across the '
      + 'lines by what each one sold for.');
  }else{
    notes.push('Amazon has not settled this order yet, so its fee is '
      + 'estimated at ' + Math.round((t.fee_rate || 0.15) * 100) + '% — this account’s '
      + 'own measured rate where there is enough history to measure one — and '
      + 'split across the lines by what each one sold for.');
  }
  notes.forEach(function(n){
    h += '<div class="odp-note">' + _oEsc(n) + '</div>';
  });

  // CORRECT THIS ONE ORDER'S COST, HERE.
  //
  //     "my typed cogs win but it should be only for that order not all time
  //      frames and all orders"
  //
  // /cogs/order has done exactly that for a while -- writes onto the order
  // line, marked 'manual-order' so nothing later overwrites it -- and NOTHING
  // IN THE BROWSER CALLED IT. A finished endpoint with no way to reach it is a
  // feature nobody has.
  //
  // It belongs here rather than on a settings screen because this is where the
  // wrong number is visible: the panel has just said which lines have no cost.
  // Sending somebody to a sheet to fix what they are looking at is how the
  // note above used to end.
  //
  // Blank clears it, putting the order back to "not known" -- which is a real
  // thing to want, and different from typing 0.
  //
  // ONE INPUT PER LINE, CARRYING ITS OWN SKU. set_for_order without a sku
  // updates EVERY line of the order to the same figure -- correct for the
  // single-item orders that are most of them, silently wrong for a two-item
  // order where the products cost different amounts. The sku is always sent.
  //
  // PER UNIT, and it says so. order_lines.cogs is the unit cost -- the Cost
  // column above shows the line (unit x quantity), and putting the line total
  // into a per-unit field on a 3-unit order overstates the cost threefold.
  if(orderId){
    h += '<div class="odp-note">'
      +  '<div style="margin-bottom:4px">Wrong cost? Correct it for '
      +  '<b>this order only</b> — per unit, and no other order changes.</div>';
    bd.lines.forEach(function(l, i){
      // No sku on a multi-line order means the write could not be aimed at one
      // line, and set_for_order would set them all. Better no control than one
      // that quietly corrects the wrong product too.
      if(!l.sku && bd.lines.length > 1) return;
      const id = 'ordcogs_' + i;
      const unit = (l.unit_cost !== null && l.unit_cost !== undefined)
        ? l.unit_cost
        : ((l.cogs !== null && l.cogs !== undefined && l.qty)
            ? (Number(l.cogs) / Number(l.qty)) : null);
      // THE COST THAT IS SET GOES IN value=, NOT placeholder=.
      //
      //     "i uploaded the cogs ... give a green message showing confirmation
      //      the cogs are updated but when i click on the order and see there
      //      is a box which still asks for cogs, if the cogs are updated,
      //      where can i see them"
      //
      // It was in the placeholder. A placeholder is grey ghost text that
      // disappears the moment you type -- it reads as an empty box asking for
      // a number, which is exactly what an unset cost looks like. So a cost
      // that HAD been saved was indistinguishable on screen from one that
      // never was, and the only way to find out was to save something and
      // watch whether anything changed.
      //
      // In value= it is a real, editable figure: visibly there, and still
      // clearable, because the note below promises that clearing it works.
      const shown = (unit === null) ? "" : Number(unit).toFixed(2);
      // AND WHERE THE NUMBER CAME FROM, in the owner's words rather than the
      // stored code. "you set this" is the entire answer to "are my uploaded
      // costs actually being used", and it costs one line on screen.
      // `tracked` and `sku` ARE HISTORY, AND ARE LABELLED AS HISTORY. Neither
      // is a source any more -- nothing is read out of a SKU name or a supplier
      // price. But order lines costed BEFORE that change still carry the word
      // (measured: 50 lines across two accounts all say `sku`), so the label
      // cannot simply be deleted or those rows would show a blank provenance.
      // It says when it was worked out instead, so nobody reads it as a thing
      // the app is still doing.
      const WHENCE = {
        "manual-order": "you set this",
        "frozen": "you set this",
        "manual": "you set this for this product",
        "tracked": "an old cost, from the supplier price at the time",
        "sku": "an old cost, read from the SKU name before costs became "
               + "something you set",
      };
      const whence = WHENCE[String(l.cogs_source || "")] || "";
      h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
        +  'margin:3px 0">'
        +  (bd.lines.length > 1
            ? '<code class="cc" style="font-size:9.5px;max-width:170px;'
              + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
              + _oEsc(l.sku) + '</code>' : '')
        +  '<input id="' + id + '" class="ed" style="width:100px" '
        +  'value="' + _oEsc(shown) + '" '
        +  'placeholder="' + (unit === null ? 'e.g. 15.10' : '') + '">'
        +  '<button class="ghost" onclick="ordSetOrderCogs('
        +  jsArg(orderId) + ',' + jsArg(l.sku || '') + ',' + jsArg(id) + ','
        +  jsArg(accountId || '') + ',' + jsArg(marketplace || '') + ')">Save</button>'
        +  (l.qty > 1 ? '<span class="cc">x ' + l.qty + ' units</span>' : '')
        +  (whence ? '<span class="cc" style="font-size:10.5px">' + _oEsc(whence)
                     + '</span>' : '')
        +  '</div>';
    });
    h += '<div class="cc">Leave the box empty and press Save to clear a cost '
      +  'and put that line back to “not known”.</div></div>';
  }

  return h + '</div>';
}

/* THIS ORDER'S PARCEL, ADDED BY HAND.
 *
 * The sheet on the toolbar is for a hundred of them; this is for the one you
 * are looking at, which is the shape a single missing number actually has --
 * the same reasoning as the cost box, and the same place: where the gap is
 * visible.
 *
 * Amazon does not hand these back, so there is no "refresh from Amazon" that
 * could fill it in. It is typed or it is not there.
 *
 * ONE FUNCTION, called by both the compact panel and the long fallback, so the
 * two layouts cannot end up offering different things (CLAUDE.md Rule 12). */
function ordParcelPanel(r){
  const orderId = (r && r.order_id) || "";
  const accountId = (r && r.account_id) || "";
  const marketplace = (r && r.marketplace) || "";
  let h = "";
  if(orderId){
    const parcels = (r && r.tracking) || [];
    h += '<div class="odp-note">'
      +  '<div style="margin-bottom:4px"><b><i class="ti ti-truck"></i> Tracking</b> '
      +  '<i class="ti ti-info-circle cc" title="Amazon does not give back the tracking '
      +  'numbers you upload to it, so they are recorded here. A parcel is checked with the '
      +  'carrier only when you press Check parcels, and only once a tracking service is set '
      +  'up in Settings; until then it reads Not checked."></i></div>';
    parcels.forEach(function(p){
      const d = _ORD_PARCEL[p.status] || _ORD_PARCEL.unknown;
      h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
        +  'margin:3px 0">'
        +  '<span style="color:' + d.c + '" title="' + _oEsc(d.m || "") + '">'
        +  '<i class="ti ' + d.i + '"></i> '
        +  _oEsc(p.status_label || "Not checked") + '</span>'
        +  '<code style="font-size:10.5px">' + _oEsc(p.tracking_number || "")
        +  '</code>'
        +  (p.carrier ? '<span class="cc" style="font-size:10.5px">'
                        + _oEsc(p.carrier) + '</span>' : '')
        // WHAT THE CARRIER ITSELF SAID, kept beside our word for it. Every
        // carrier invents its own vocabulary and the mapped word loses detail
        // the seller sometimes needs.
        +  (p.raw_status ? '<span class="cc" style="font-size:10.5px" '
                           + 'title="the carrier\'s own words">“'
                           + _oEsc(p.raw_status) + '”</span>' : '')
        +  (p.check_error ? '<span class="cc" style="font-size:10.5px;'
                            + 'color:var(--red)">' + _oEsc(p.check_error)
                            + '</span>' : '')
        +  '<button class="ghost" onclick="ordRemoveTracking('
        +  jsArg(orderId) + ',' + jsArg(p.tracking_number || '') + ','
        +  jsArg(accountId || '') + ',' + jsArg(marketplace || '')
        +  ')" title="Forget this number. Only this one — a split shipment '
        +  'keeps its others.">Remove</button>'
        +  '</div>';
    });
    h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
      +  'margin:3px 0">'
      +  '<input id="ordtrk_num" class="ed" style="width:170px" '
      +  'placeholder="tracking number">'
      +  '<input id="ordtrk_car" class="ed" style="width:110px" '
      +  'placeholder="carrier">'
      +  '<button class="ghost" onclick="ordAddTracking('
      +  jsArg(orderId) + ',' + jsArg(accountId || '') + ','
      +  jsArg(marketplace || '') + ')">Add</button>'
      +  '</div>'
      +  _ordShipBox(r)
      +  '</div>';
  }
  return h;
}

/* TELL AMAZON IT IS DISPATCHED -- previewed here, sent only when switched on.
 *
 * One Amazon call does both "mark dispatched" and "upload tracking" (its
 * schema requires the tracking), so this uses the tracking number and carrier
 * typed in the boxes just above. Preview reads the order's lines from Amazon
 * and sends nothing; the server says whether sending is switched on, and only
 * then is a Send button drawn (domain/ship_confirm.py). FBM orders still to
 * post only. */
function _ordShipBox(r){
  if(!r || !r.order_id) return "";
  if(String(r.fulfilment || "").toUpperCase() === "AFN") return "";
  if(typeof _ordUnshipped === "function" && !_ordUnshipped(r)) return "";
  return '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0 3px">'
    + '<button class="ghost" onclick="ordShipPreview(' + jsArg(r.order_id) + ','
    + jsArg(r.account_id || "") + ',' + jsArg(r.marketplace || "") + ',this)"'
    + ' title="Shows what Amazon would be told. Sends nothing.">'
    + '<i class="ti ti-eye"></i> Preview dispatch to Amazon</button>'
    + '</div><div id="ordship_out" class="cc"></div>';
}

function _ordShipBody(orderId, accountId, marketplace){
  const v = function(id){ return ((document.getElementById(id) || {}).value || "").trim(); };
  return {account: accountId || "", marketplace: marketplace || "", order_id: orderId,
          tracking_number: v("ordtrk_num"), carrier: v("ordtrk_car")};
}

async function ordShipPreview(orderId, accountId, marketplace, btn){
  const out = document.getElementById("ordship_out");
  if(btn){ if(btn.disabled) return; btn.disabled = true; }
  if(out) out.textContent = "Asking Amazon for this order's lines…";
  try{
    const j = await (await fetch("/orders/ship/preview", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(_ordShipBody(orderId, accountId, marketplace))})).json();
    if(!out) return;
    if(!j || !j.ok){
      ORD.shipPreview = null;
      out.textContent = "Not ready to send: " + ((j && j.error) || "unknown");
      return;
    }
    // WHAT WAS PREVIEWED IS WHAT IS SENT: kept here, and Send refuses if the
    // boxes have changed since (review finding).
    ORD.shipPreview = {order_id: orderId, body: _ordShipBody(orderId, accountId, marketplace),
                       summary: j.summary || ""};
    let h = _oEsc(j.summary || "");
    if(j.switched_on){
      h += ' <button class="ghost" onclick="ordShipConfirm(' + jsArg(orderId) + ','
        + jsArg(accountId) + ',' + jsArg(marketplace) + ',this)">'
        + '<i class="ti ti-truck-delivery"></i> Send to Amazon</button>';
    }else{
      h += '<br>' + _oEsc(j.why_off || "Sending is switched off.");
    }
    out.innerHTML = h;
  }catch(e){
    if(out) out.textContent = "Could not preview that: " + e;
  }finally{
    if(btn) btn.disabled = false;
  }
}

async function ordShipConfirm(orderId, accountId, marketplace, btn){
  if(btn){ if(btn.disabled) return; btn.disabled = true; }
  const pv = ORD.shipPreview;
  const now = _ordShipBody(orderId, accountId, marketplace);
  if(!pv || pv.order_id !== orderId || JSON.stringify(pv.body) !== JSON.stringify(now)){
    const out = document.getElementById("ordship_out");
    if(out) out.textContent = "The tracking or carrier changed since the preview. "
                            + "Press Preview again so what is sent is what you saw.";
    return;
  }
  const msg = pv.summary + " The buyer is told it is on its way, and it cannot "
            + "be taken back from here. Send it?";
  const yes = (typeof uiConfirm === "function")
    ? await uiConfirm(msg, {title: "Send to Amazon?", ok: "Send to Amazon",
                            cancel: "Don't send", danger: true})
    : false;
  if(!yes){ if(btn) btn.disabled = false; return; }
  const res = await _ordWriteThenReload("/orders/ship/confirm", pv.body, orderId, accountId,
    "Sent.", "Not sent to Amazon: ");
  ORD.shipPreview = null;
  // Free the button ONLY after a clear refusal. After no reply, or an answer
  // that says the result is not known, it stays off: it may have been sent.
  if(btn && res && !res.ok && !res.uncertain) btn.disabled = false;
}

/* Record or forget ONE order's tracking number.
 *
 * The account and the marketplace are the ROW'S, passed down, exactly as the
 * cost box does it and for the same reason: writing against whichever workspace
 * happens to be open would put the number on a different company's order.
 *
 * Not optimistic. The panel is redrawn from what came BACK, so a refused save
 * cannot look like a successful one. */
async function ordAddTracking(orderId, accountId, marketplace){
  const num = ((document.getElementById("ordtrk_num") || {}).value || "").trim();
  const car = ((document.getElementById("ordtrk_car") || {}).value || "").trim();
  if(!num){
    if(typeof toast === "function") toast("Type a tracking number first.");
    return;
  }
  await _ordTrackWrite({account: accountId || "", marketplace: marketplace || "",
                        order_id: orderId, tracking_number: num, carrier: car},
                       orderId, accountId,
                       "Tracking recorded for this order.");
}

async function ordRemoveTracking(orderId, number, accountId, marketplace){
  await _ordTrackWrite({account: accountId || "", marketplace: marketplace || "",
                        order_id: orderId, tracking_number: number,
                        remove: true},
                       orderId, accountId, "That number has been forgotten.");
}

async function _ordTrackWrite(body, orderId, accountId, okMsg){
  // WHETHER IT WILL EVER BE CHECKED, said at the moment the number is stored
  // (the server's `note`) rather than left to be discovered as a column of
  // "Not checked".
  await _ordWriteThenReload("/tracking/set", body, orderId, accountId, okMsg);
}

/* POST one order's own record, then redraw that order from the server.
 *
 * Shared by the tracking box and the "bought it" record (Rule 12). Not
 * optimistic: the row and panel are rebuilt from what the server now holds, so
 * a refused save cannot look like a successful one. The reply's `note`, if
 * any, is added to the message. */
async function _ordWriteThenReload(url, body, orderId, accountId, okMsg, failWord){
  // -> the server's reply ({ok, ...}), or null when no reply could be read.
  const fail = failWord || "Could not save that: ";
  try{
    const j = await (await fetch(url, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})).json();
    if(!j || !j.ok){
      // An answer that says the result is NOT KNOWN is not a failure: the
      // "not saved / not sent" prefix would contradict it (seen in the
      // browser check), so it is shown in its own words.
      if(typeof toast === "function")
        toast((j && j.uncertain ? "" : fail) + ((j && j.error) || "unknown"));
      return j || null;
    }
    if(typeof toast === "function")
      toast(okMsg + (j.note ? " " + j.note : ""));
    delete ORD.details[orderId];
    ORD.open = "";
    ordersRender();
    if(typeof ordersLoad === "function") await ordersLoad();
    // Reopen only if this tab is still on the order's account: switched while
    // the save was in flight, the old account's order is not reopened here.
    const nowWs = (typeof ACTIVE_WS !== "undefined" && ACTIVE_WS && ACTIVE_WS.key)
      ? String(ACTIVE_WS.key) : "";
    if(!accountId || !nowWs || nowWs === String(accountId))
      ordersToggle(orderId, accountId || "");
    return j;
  }catch(e){
    if(typeof toast === "function") toast(fail + e);
    return null;
  }
}

/* "I BOUGHT THIS FROM THE SUPPLIER" -- recorded, never done.
 *
 * The app buys nothing: "Buy from supplier" only opens the supplier's page.
 * Once the person has bought it there, this records that they did, so the
 * board's "To buy" tab can tell a bought order from one still to buy. What it
 * COST goes in the Cost box on the same panel -- the one place an order's cost
 * lives -- so no amount is asked for here (Rule 12).
 *
 * Only for orders the seller posts (FBM). `best` is the cheapest supplier the
 * sources block already marked, used to fill the supplier box in.
 *
 * ONE FUNCTION, called by both panel layouts (Rule 12). */
function ordPurchasePanel(r, best, fresh){
  const orderId = (r && r.order_id) || "";
  if(!orderId) return "";
  if(String((r && r.fulfilment) || "").toUpperCase() === "AFN") return "";
  const accountId = (r && r.account_id) || "";
  const marketplace = (r && r.marketplace) || "";
  // `fresh` is the opened order's own list (/orders/detail), read after the
  // list: preferred, so a list reload that failed after a save cannot show
  // the order as not yet bought and invite a second record (change review).
  const recs = Array.isArray(fresh) ? fresh : (r ? r.purchases : null);
  // A CANCELLED order lists what was recorded (it may have been bought before
  // the cancel) but offers no new record.
  const closed = (typeof _ordState === "function") && _ordState(r) === "closed";
  let h = '<div class="odp-note">'
    + '<div style="margin-bottom:4px"><b><i class="ti ti-shopping-cart"></i> Bought from supplier</b> '
    + '<i class="ti ti-info-circle cc" title="Record it here once you have bought it on the '
    + 'supplier\'s site. Nothing is ordered or paid for by this app; what it cost goes in '
    + 'the Cost box."></i></div>';
  if(recs === null || recs === undefined){
    h += '<div class="cc">Could not read whether this order was already '
      + 'recorded as bought.</div>';
  }
  (recs || []).forEach(function(p){
    const who = p.bought_by ? " by " + p.bought_by : "";
    const sup = p.supplier_url
      ? '<a class="link" target="_blank" rel="noopener noreferrer" href="' + _oEsc(p.supplier_url)
        + '">' + _oEsc(p.supplier || "supplier") + '</a>'
      : _oEsc(p.supplier || "supplier not named");
    h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:3px 0">'
      + '<span style="color:var(--green)"><i class="ti ti-circle-check"></i> Bought</span>'
      + '<span>' + sup + '</span>'
      + (p.supplier_ref ? '<code style="font-size:10.5px" title="The supplier\'s order number">'
                          + _oEsc(p.supplier_ref) + '</code>' : '')
      + '<span class="cc" style="font-size:10.5px">' + _oEsc(_oWhen(p.bought_at) + who) + '</span>'
      + (p.note ? '<span class="cc" style="font-size:10.5px">“' + _oEsc(p.note) + '”</span>' : '')
      + '<button class="ghost" onclick="ordRemovePurchase(' + jsArg(orderId) + ','
      + jsArg(p.id) + ',' + jsArg(accountId) + ',' + jsArg(marketplace)
      + ')" title="Forget this record. Nothing at the supplier changes.">Remove</button>'
      + '</div>';
  });
  if(closed) return h + '<div class="cc">This order was cancelled.</div></div>';
  const sup = (best && best.label) ? String(best.label) : "";
  const url = (best && best.url) ? String(best.url) : "";
  h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:3px 0">'
    + '<input id="ordbuy_sup" class="ed" style="width:130px" placeholder="supplier"'
    + ' value="' + _oEsc(sup) + '">'
    + '<input id="ordbuy_ref" class="ed" style="width:140px" placeholder="supplier order no.">'
    + '<input id="ordbuy_note" class="ed" style="width:150px" placeholder="note (optional)">'
    + '<button class="ghost" onclick="ordRecordPurchase(' + jsArg(orderId) + ','
    + jsArg(accountId) + ',' + jsArg(marketplace) + ',' + jsArg(url) + ',this)">'
    + 'Mark as bought</button>'
    + '</div></div>';
  return h;
}

async function ordRecordPurchase(orderId, accountId, marketplace, url, btn){
  // ONE PRESS, ONE RECORD. An order may carry several records (two suppliers),
  // so a double click would really record it twice; the button waits instead.
  if(btn){ if(btn.disabled) return; btn.disabled = true; }
  const v = function(id){ return ((document.getElementById(id) || {}).value || "").trim(); };
  const supplier = v("ordbuy_sup");
  // The supplier's link is kept only when the box still names the supplier it
  // came with -- a changed name with the old link would point at the wrong shop.
  const keepUrl = url && supplier && document.getElementById("ordbuy_sup")
    && supplier === String(document.getElementById("ordbuy_sup").defaultValue || "");
  const res = await _ordWriteThenReload("/orders/purchase",
    {account: accountId || "", marketplace: marketplace || "", order_id: orderId,
     supplier: supplier, supplier_url: keepUrl ? url : "",
     supplier_ref: v("ordbuy_ref"), note: v("ordbuy_note")},
    orderId, accountId, "Recorded as bought.");
  // Refused: the panel was not redrawn, so the same button is pressable again.
  if(!(res && res.ok) && btn) btn.disabled = false;
}

async function ordRemovePurchase(orderId, id, accountId, marketplace){
  await _ordWriteThenReload("/orders/purchase/remove",
    // purchase_id, not id: the guard reads a body `id` as an ACCOUNT name, so a
    // person limited to some accounts was refused (account-scope review).
    {account: accountId || "", marketplace: marketplace || "", order_id: orderId, purchase_id: id},
    orderId, accountId, "That record has been removed.");
}

/* Write one order line's cost, then redraw from the server's answer.
 *
 * Not optimistic: the panel shows what came BACK, because the point of a typed
 * cost is that it is the figure of record, and showing it before it is stored
 * would make a failed save look like a success.
 *
 * /cogs/order has done exactly this since it was written -- and nothing in the
 * browser called it. It is reached from here now.
 *
 * The account and the marketplace are the ROW'S, passed down, not the open
 * workspace's. Orders can be listed across every account from the picker, and
 * writing a cost against whichever account happens to be open would put it on a
 * different company's order line. */
async function ordSetOrderCogs(orderId, sku, inputId, accountId, marketplace){
  const el = document.getElementById(inputId);
  const raw = ((el && el.value) || "").trim();
  if(raw !== "" && !isFinite(Number(raw))){
    if(typeof toast === "function") toast("That cost is not a number.");
    return;
  }
  // AN EMPTY BOX IS NOT ALWAYS "CLEAR IT". The saved cost is shown only as the
  // box's placeholder, so pressing Save without typing sent cost:null and wiped
  // it (master audit, UX #1). Clearing stays possible -- it is now a question.
  if(raw === "" && el && el.dataset && el.dataset.has === "1"){
    const _msg = "Clear the cost on this order? This line goes back to "
               + "the product's own cost (or “not known” if it has none). To change it, type the new cost instead.";
    const _ok = (typeof uiConfirm === "function") ? await uiConfirm(_msg) : false;
    if(!_ok) return;
  }
  try{
    const j = await (await fetch("/cogs/order", {
      method: "POST", headers: {"Content-Type": "application/json"},
      // "account" is read by request_account.named() (ACCOUNT_KEYS) -- the ORDER'S account, not the open one.
      body: JSON.stringify({account: accountId || "",
                            marketplace: marketplace || "",
                            order_id: orderId, sku: sku || "",
                            cost: raw === "" ? null : raw})
    })).json();
    if(!j || !j.ok){
      if(typeof toast === "function"){
        toast("Could not save that cost: " + ((j && j.error) || "unknown"));
      }
      return;
    }
    if(typeof toast === "function"){
      toast(raw === ""
        ? "Cost cleared — that line uses the product's own cost again."
        : "Saved at " + raw + " per unit. This order only.");
    }
    // Redraw from the server. The panel's figures AND the row's profit, margin
    // and ROI are all worked out from this cost, so the list is reloaded too --
    // otherwise the row keeps showing the profit it had before the correction.
    delete ORD.details[orderId];
    ORD.open = "";
    ordersRender();
    if(typeof ordersLoad === "function") await ordersLoad();
    ordersToggle(orderId, accountId || "");
  }catch(e){
    if(typeof toast === "function") toast("Could not save that cost: " + e);
  }
}

/* THE ORDER PANEL, IN SECTIONS.
 *
 *     "RIGHT NOW THE TEXT APPEARS IN A FREE FORM WHEN I CLICK ON THE ORDER
 *      NUMBER INSIDE THE ORDERS TAB ... the order page is not arranged the,
 *      text mixes freely into each other."
 *
 * It was one stack of divs, each carrying its own inline padding and font size,
 * with nothing sharing a baseline and no grid for anything to line up against.
 * Text positioned only relative to the text before it runs together the moment
 * one piece grows -- which a long Amazon product title does immediately.
 *
 * Four sections now, each with a heading, in the order the questions are asked:
 *
 *      What was ordered      the product, its ASIN as a link, quantity, price
 *      Where to buy it       every supplier link, cheapest first
 *      What it earned        the sum, line by line
 *      Delivery              the dates Amazon holds you to
 *
 * The shapes live in dashboard.css under .odp -- see the block there. Almost no
 * inline styling is left here, which is the actual fix: a panel whose layout is
 * described in one place can be made to line up, and one where every element
 * describes itself cannot.
 */
function _ordDetailHtml(r){
  const d = ORD.details[r.order_id] || {};
  const items = d.items || [];
  if(d.error){
    return '<div class="odp"><div class="odp-sec" style="color:var(--red)">'
         + _oEsc(d.error) + '</div></div>';
  }
  // THE COMPACT PANEL, in static/js/orders_panel.js.
  //
  //     "The expanded order detail takes ~600px+ of vertical height ... The new
  //      layout fits all of that into ~300px."
  //
  // Same `d`, same call, same route -- it rearranges, it does not fetch or
  // compute. The long version below is kept as the fallback for the case where
  // that file has not loaded, so a missing script costs the new layout rather
  // than the order details.
  if(typeof ordPanelHtml === "function") return ordPanelHtml(r, d);

  const o = d.order || {};
  let h = '<div class="odp">';

  // ---- what was ordered ------------------------------------------------
  h += '<div class="odp-sec">'
    +  '<h4 class="odp-h"><i class="ti ti-package"></i>What was ordered'
    +  '<span class="odp-count">· ' + items.length + ' item'
    +  (items.length === 1 ? '' : 's') + '</span></h4>';
  items.forEach(function(it){
    h += '<div class="odp-item">'
      +  '<div class="odp-title">' + _oEsc(it.title || "(no title)") + '</div>'
      +  '<div class="odp-qty">' + it.qty + ' ×</div>'
      +  '<div class="odp-price">' + _oEsc(_oMoney(it.price, it.currency)) + '</div>'
      +  '<div class="odp-ids">'
      // THE ASIN, AS A LINK THAT OPENS THE PRODUCT. Asked for directly: "it
      // should show the name of the item, the clickable asin which opens the
      // item". It was plain text before, so the one thing you would want to
      // click on this panel was the one thing you could not.
      +  (it.asin
          ? '<a class="odp-id link" target="_blank" rel="noopener" href="'
            + _oEsc(_ordDp(it.asin, r.marketplace)) + '" '
            + 'title="Open this product on Amazon">' + _oEsc(it.asin)
            + ' <i class="ti ti-external-link"></i></a>'
          : '')
      +  (it.sku ? '<span class="odp-id" title="Your own SKU for this product">'
                   + _oEsc(it.sku) + '</span>' : '')
      +  _ordStateChip(o.status || r.status, it.cancel_requested)
      +  '</div>';
    // The explanation, spelled out rather than left to a tooltip, for the two
    // states where acting on the wrong reading costs real money.
    const why = _ordWhyText(o.status || r.status, it.cancel_requested,
                            it.cancel_reason);
    if(why) h += '<div class="odp-why">' + why + '</div>';
    h += '</div>';
  });
  h += '</div>';

  // ---- where to buy it -------------------------------------------------
  items.forEach(function(it){
    const block = (d.sources || {})[it.sku];
    const body = _ordSourcesHtml(block, items.length > 1 ? it.title : "");
    if(body) h += body;
  });

  // ---- what it earned --------------------------------------------------
  // r.order_id, not o.order_id: `r` is the row this panel belongs to and always
  // carries the id -- `d.order` is whatever the detail call returned, and its
  // key name is Amazon's, not ours.
  h += _ordBreakdownHtml(d.breakdown, o.currency, r.order_id,
                         r.account_id, r.marketplace);

  // ---- where the parcel is ---------------------------------------------
  // Bought, then posted, then tracked -- the order the work happens in.
  h += ordPurchasePanel(r, (typeof _opBestSource === "function")
                             ? _opBestSource(d, d.items || []) : null,
                        (d.order || {}).purchases);
  h += ordParcelPanel(r);

  // ---- delivery --------------------------------------------------------
  h += '<div class="odp-sec">'
    +  '<h4 class="odp-h"><i class="ti ti-truck-delivery"></i>Delivery</h4>'
    +  '<dl class="odp-kv">'
    +  '<dt>Post it by</dt><dd>' + _oEsc(_oWhen(o.ship_by))
    +  ' <span class="cc">— Amazon counts it late after this</span></dd>'
    +  '<dt>Must arrive by</dt><dd>' + _oEsc(_oWhen(o.deliver_by))
    +  ' <span class="cc">— what the buyer was promised</span></dd>'
    +  (o.region ? '<dt>Going to</dt><dd>' + _oEsc(o.region) + '</dd>' : '')
    +  '</dl></div>';

  return h + '</div>';
}

/* The product's page on the right Amazon. listings.js owns the marketplace ->
 * domain table, so it is borrowed rather than copied (Rule 12); if that file
 * has not loaded the link is simply omitted rather than pointing somewhere
 * plausible and wrong. */
function _ordDp(asin, market){
  try{
    if(typeof _dpUrl === "function") return _dpUrl(asin, market);
  }catch(e){}
  return "";
}

/* The sentence under a line, for the states where the obvious action is the
 * wrong one. Everything else is left to the chip's tooltip -- a paragraph on
 * every Shipped order is noise, and noise is what makes a real warning
 * invisible. */
function _ordWhyText(status, cancelRequested, cancelReason){
  const bits = [];
  if(cancelRequested){
    // Amazon carries the buyer's stated reason in the same object as the flag.
    // It is usually empty; when it is not, it is the most useful sentence on
    // the screen, so it goes first.
    bits.push('<b style="color:var(--red)">' + _oEsc(_ORD_CANCEL_REQUESTED.t)
              + (cancelReason ? ': ' + _oEsc(cancelReason) : '')
              + '.</b> ' + _oEsc(_ORD_CANCEL_REQUESTED.m) + ' '
              + _oEsc(_ORD_CANCEL_REQUESTED.d));
  }
  const s = _ORD_STATUS[status];
  if(s && s.d && (status === "Pending" || status === "Unfulfillable")){
    bits.push(_oEsc(s.m) + ' ' + _oEsc(s.d));
  }
  return bits.join("<br>");
}

/* "29 Sep" -- the day an order was placed, short; the full date and time is
 * the cell's hover text (owner, 30 Sep 2026: "less words"). */
function _ordShortDay(iso){
  const t = Date.parse(iso || "");
  if(isNaN(t)) return String(iso || "");
  try{ return new Date(t).toLocaleDateString("en-GB", {day: "numeric", month: "short"}); }
  catch(e){ return String(iso).slice(0, 10); }
}

function _ordWhenCell(iso){
  const w = String(_oWhen(iso) || "");
  const k = w.lastIndexOf(", ");
  if(k < 0) return '<span style="white-space:nowrap">' + _oEsc(w) + '</span>';
  return '<span style="white-space:nowrap">' + _oEsc(w.slice(0, k)) + ',</span> '
       + '<span style="white-space:nowrap">' + _oEsc(w.slice(k + 2)) + '</span>';
}

/* THE ONE SHIP-BY RULE for the Orders screen (Rule 12): milliseconds until
 * Amazon's LatestShipDate, negative once it has passed -- which is when Amazon
 * counts the order late. null when Amazon gave no date. The board's tabs and
 * countdown and the order panel's "Post by" all read it. */
function _ordShipMs(shipBy){
  const t = Date.parse(shipBy || "");
  return isNaN(t) ? null : t - Date.now();
}

/* Two columns (table + order panel) only where there is ROOM for both: a
 * laptop-or-wider window AND an Orders area wide enough that the table keeps
 * its 760px beside a 380px panel. The window alone was not enough -- with the
 * sidebar open on a 1366 laptop the table lost Profit, Margin and ROI behind a
 * sideways scroll, which is the panel replacing the table after all. */
// 520 (30 Sep 2026, master-detail): beside an open order the list is COMPACT
// (.ord-compact -- tick, order, item, state, profit), which fits in ~520px, so
// every desktop window (>=1100px) opens the order on the right again. The
// nine-column table needed 980px here, which pushed a normal laptop back to
// the under-the-row "dropdown" the owner did not want. The panel is 400-480px
// (orders_panel.css .ord-split); 400 is the narrowest it gets.
const ORD_SIDE_MIN = 520 + 400 + 16;
function _ordSideMode(){
  try{
    if(!(window.matchMedia && window.matchMedia("(min-width: 1100px)").matches)) return false;
    const b = document.getElementById("ordbody");
    return !!(b && b.clientWidth >= ORD_SIDE_MIN);
  }catch(e){ return false; }
}

async function ordersToggle(orderId, accountId){
  if(ORD.open === orderId){ ORD.open = ""; ordersRender(); return; }
  ORD.open = orderId;
  ordersRender();
  if(ORD.details[orderId]){ return; }
  // PINNED TO THE CACHE THIS REQUEST BELONGS TO. Switching account replaces
  // ORD.details with a fresh object; a reply landing after that must go into
  // the old one, not be filed under the new account.
  const cache = ORD.details;
  try{
    const j = await (await fetch("/orders/detail?order_id="
      + encodeURIComponent(orderId) + "&account=" + encodeURIComponent(accountId))).json();
    cache[orderId] = j && j.ok ? j : {error: (j && j.error) || "could not read it"};
  }catch(e){
    cache[orderId] = {error: String(e)};
  }
  if(ORD.details === cache && ORD.open === orderId) ordersRender();
}

/* Escape closes the order open beside the list (escape.js's one handler calls
 * this for .ord-side) and puts the keyboard back on its row. */
function ordersCloseSide(){
  const oid = ORD.open;
  if(!oid) return;
  ORD.open = "";
  ordersRender();
  _ordRefocus(oid);
}

/* Enter or Space on a focused row opens it, as a click does. */
function ordersRowKey(e, orderId, accountId){
  if(e.target !== e.currentTarget) return;           // a control inside the row
  if(e.key === "Enter" || e.key === " "){ e.preventDefault(); ordersToggle(orderId, accountId); }
}

/* The table is redrawn on every toggle AND when the order's details arrive, so
 * the row that had focus becomes a new element. Only when focus was on a row
 * (or the panel's close button) is it put back -- never stolen from a field. */
function _ordFocusedOid(){
  const a = document.activeElement;
  if(!a || !a.closest) return "";
  // Any Orders control that names itself (tab, channel, checkbox, next step,
  // bulk button): restored by that name after the redraw.
  if(a.getAttribute && a.getAttribute("data-fk")) return "fk:" + a.getAttribute("data-fk");
  if(a.classList.contains("ordrow")) return a.getAttribute("data-oid") || "";
  if(a.classList.contains("ord-side-x")) return a.getAttribute("data-oid") || "";
  return "";
}
function _ordRefocus(orderId){
  const k = String(orderId);
  const el = k.indexOf("fk:") === 0
    ? document.querySelector('[data-fk="' + k.slice(3).replace(/["\\]/g, "") + '"]')
    : document.querySelector('tr.ordrow[data-oid="' + k.replace(/["\\]/g, "") + '"]');
  if(el) el.focus({preventScroll: true});
}

// When the room changes (window resized, sidebar opened or closed) an open
// order moves between the side panel and its row. Only redrawn when the answer
// actually flips, so resizing does not redraw the table on every pixel.
try{
  let _ordWasSide = null, _ordT = 0;
  window.addEventListener("resize", function(){
    clearTimeout(_ordT);
    _ordT = setTimeout(function(){
      const now = _ordSideMode();
      if(ORD.open && now !== _ordWasSide && typeof ordersRender === "function") ordersRender();
      _ordWasSide = now;
    }, 150);
  });
}catch(e){ /* no window: inline only */ }
