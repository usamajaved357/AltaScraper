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
  Shipped: {c:"#8fd694", t:"Shipped", tone:"ok",
    m:"You have dispatched it and told Amazon. Nothing further is needed."},
  Unshipped: {c:"#e8c66a", t:"Not shipped yet", tone:"warn",
    m:"The buyer has paid and it is waiting for you to send it.",
    d:"Post it before the ship-by date below, or Amazon counts it late."},
  PartiallyShipped: {c:"#e8c66a", t:"Partly shipped", tone:"warn",
    m:"Some of the items have gone and some have not.",
    d:"Send the rest before the ship-by date below."},
  Pending: {c:"#8b949e", t:"Payment not cleared", tone:"",
    m:"Amazon is still taking the buyer's payment. The address and the items "
     + "are not final yet, and the order can still disappear.",
    d:"Do not buy stock for it or post it until it turns to Unshipped."},
  Canceled: {c:"#e88a8a", t:"Cancelled", tone:"bad",
    m:"The order is off. No money will arrive for it.",
    d:"If you have already posted it, claim it back through Amazon."},
  Cancelled: {c:"#e88a8a", t:"Cancelled", tone:"bad",
    m:"The order is off. No money will arrive for it.",
    d:"If you have already posted it, claim it back through Amazon."},
  InvoiceUnconfirmed: {c:"#8b949e", t:"Awaiting invoice", tone:"",
    m:"Shipped, but Amazon is waiting for the invoice for a business buyer."},
  Unfulfillable: {c:"#e88a8a", t:"Cannot be fulfilled", tone:"bad",
    m:"Amazon cannot fulfil it from your stock — usually there is none in the "
     + "warehouse, or the item is not sellable."},
};

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
    scope.textContent = nm ? (nm + " only") : "this account only";
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
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _oEsc(j.error || "That is not the account that is open.") + '</div>';
      return;
    }
    if(!j || !j.ok){
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _oEsc((j&&j.error)||"Could not load orders") + '</div>';
      return;
    }
    ORD.rows = j.rows || []; ORD.summary = j.summary || {}; ORD.meta = j;
    // Stamped with WHOSE rows these are, so ordersOnOpen can tell a redraw of
    // the right list from a redraw of the last one.
    ORD.rowsFor = nowWs || askedFor;
    ordersRender();
  }catch(e){
    if(mine === ORD.loadId){
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
    return '<span class="cc" style="font-size:11px;opacity:.55" title="'
         + _oEsc(why) + '">' + _oEsc(why) + '</span>';
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
            note: "charged, incl. shipping — the Sales screen excludes it",
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
           ? (ORD.profit ? "still working out what sold" : "turn on Work out profit")
           : (_pfBlank ? _pfKnown + " of " + (_pfKnown + _pfBlank)
                         + " orders costed" : "across every order here")},
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
  h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px" id="ord_fillnote">'
    +  (m.profit_note
        ? '<i class="ti ti-info-circle"></i> ' + _oEsc(m.profit_note)
        : (ORD.filling
            ? '<span class="genspin"></span> working out what sold…' : ''))
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
    Total: "buyer paid", Profit: "after fees and cost",
    Margin: "of the price", ROI: "on the cost",
  };
  const cols = ['Item', 'Order'].concat(_multi ? ['Account'] : [])
               .concat(['Placed', 'Status', 'Total', 'Profit', 'Margin', 'ROI']);
  // The Item column gets the room. The money columns need four characters each
  // and were taking a ninth of the screen apiece, which is why the product name
  // -- the thing the column exists for -- was cut to nothing.
  const _narrow = {'Total':1, 'Profit':1, 'Margin':1, 'ROI':1, 'Status':1};
  // IN A PANEL, LIKE EVERY OTHER SCREEN. This table sat bare on the page
  // background, at 6px row padding, with two lines of text in most cells and no
  // line between rows -- so one order's small print ran straight into the next
  // order's title. "i see text written into one another, no proper spacing and
  // good visuals like other pages".
  //
  // .panelcard and .ordtable are the shared vocabulary; the numbers live in
  // dashboard.css beside every other table's, not in this string.
  h += '<div class="panelcard" style="padding:0;overflow:hidden">'
    +  '<div style="overflow-x:auto"><table class="kv ordtable" '
    +  'style="width:100%;min-width:760px">'
    +  '<thead><tr>'
    +  cols.map(function(t){
         return '<th'
              + (t === 'Item' ? ' style="width:34%"' : (_narrow[t] ? ' style="width:9%"' : ''))
              + '>' + t
              + (_COLSUB[t] ? '<span class="th-sub">' + _oEsc(_COLSUB[t]) + '</span>' : '')
              + '</th>'; }).join("")
    +  '</tr></thead><tbody>';

  ORD.rows.forEach(function(r){
    const st = _ORD_STATUS[r.status] || {c:"var(--ink2)"};
    const isOpen = (ORD.open === r.order_id);
    h += '<tr class="ordrow' + (isOpen ? ' isopen' : '') + '" onclick="ordersToggle('
      +  jsArg(r.order_id) + ',' + jsArg(r.account_id) + ')">'
      // WHAT WAS SOLD, which is the first thing anyone wants from a list of
      // orders and was not on it at all. The picture comes from the live
      // catalogue this app already holds -- no extra call -- and falls back to
      // an icon rather than a broken image.
      +  '<td style="min-width:230px">' + _ordItemCell(r) + '</td>'
      +  '<td style="white-space:nowrap">'
      +  '<code style="font-size:11px;color:var(--accent2)">' + _oEsc(r.order_id)
      +  '</code>' + (isOpen ? ' <i class="ti ti-chevron-down"></i>'
                             : ' <i class="ti ti-chevron-right" style="opacity:.4"></i>')
      +  '<div class="cc" style="font-size:10px">' + (r.units||0) + ' unit'
      +  ((r.units||0) === 1 ? '' : 's') + '</div>'
      +  '</td>'
      +  (_multi ? ('<td style="font-size:11.5px">'
                    + _oEsc(r.account) + '</td>') : '')
      // NOT nowrap on the whole cell. It was, and the small print underneath --
      // "MFN · SMETHWICK, West Midlands, B67 7LW, GB" -- could not wrap, so it
      // ran straight out of its column and printed over the Status beside it.
      // That is the "text written into one another" on this screen. The DATE
      // keeps its nowrap, because a date broken across two lines is worse than
      // a wide column; the address wraps.
      +  '<td style="font-size:11.5px;max-width:210px">'
      +  '<span style="white-space:nowrap">' + _oEsc(_oWhen(r.purchased)) + '</span>'
      // The two columns that used to sit on the right, as small print here.
      +  '<div class="cc" style="font-size:10px;white-space:normal;'
      +  'overflow-wrap:anywhere">'
      +  _oEsc(r.fulfilment || '') + (r.prime ? ' · Prime' : '')
      +  (r.business ? ' · Business' : '')
      +  (r.region ? ' · ' + _oEsc(r.region) : '') + '</div>'
      +  '</td>'
      // AMAZON'S WORD, WITH WHAT IT MEANS ON HOVER. "Pending" and "Unshipped"
      // are the two that cost money to misread, and the raw word said nothing.
      // Same table the panel uses, so the list and the panel cannot describe
      // one status two ways (Rule 12).
      +  '<td style="font-size:11.5px;color:' + st.c + '" title="'
      +  _oEsc([st.m, st.d].filter(Boolean).join(" ")) + '">'
      +  '<span style="white-space:nowrap">' + _oEsc(st.t || r.status) + '</span>'
      // On its own line rather than trailing the status: "Unshipped (1 to ship)"
      // is too wide for a 9% column and wrapped into the cell above it.
      +  (r.unshipped ? '<div class="cc" style="font-size:10px;white-space:nowrap">'
                        + r.unshipped + ' to ship</div>' : '')
      +  '</td>'
      +  '<td style="font-size:11.5px;white-space:nowrap">'
      +  _oEsc(_oMoney(r.total, r.currency)) + '</td>'
      // WHAT IT EARNED. Blank rather than zero when a cost is unknown -- a
      // partial cost only ever makes an order look better than it was, and the
      // order whose cost is missing is exactly the one someone would use to
      // justify buying more.
      +  '<td style="font-size:11.5px;white-space:nowrap"'
      +  (r.profit_note ? ' title="' + _oEsc(r.profit_note) + '"' : '') + '>'
      +  (r.profit === undefined
          ? '<span class="cc" style="opacity:.5">—</span>'
          : r.profit === null
            ? '<span class="cc" title="' + _oEsc(r.profit_note || "")
              + '">not known</span>'
            : '<span style="color:' + (r.profit > 0 ? "var(--ok,#8fd694)" : "var(--red)")
              + '">' + _oEsc(_oMoney(r.profit, r.currency)) + '</span>')
      +  '</td>'
      // MARGIN AND ROI, in their own columns. They answer different questions --
      // margin says whether the PRICE is any good, ROI says whether the stock
      // was worth BUYING -- so they are coloured against different thresholds
      // rather than one shared rule of thumb, and neither is invented when the
      // cost behind it is unknown.
      +  '<td style="font-size:11.5px;white-space:nowrap">'
      +  _ordPct(r.margin_pct, 20, 8,
                'Profit as a share of what the buyer paid') + '</td>'
      +  '<td style="font-size:11.5px;white-space:nowrap"'
      +  (r.cogs != null ? ' title="on ' + _oEsc(_oMoney(r.cogs, r.currency))
                           + ' of stock"' : '') + '>'
      +  _ordPct(r.roi_pct, 30, 12,
                'Profit as a share of what the stock cost') + '</td>'
      +  '</tr>';
    if(isOpen){
      h += '<tr class="orddetail"><td colspan="' + cols.length + '">'
        +  '<div id="orddet_' + _oEsc(r.order_id) + '">'
        +  (ORD.details[r.order_id] ? _ordDetailHtml(r) :
            '<div class="cc" style="padding:10px"><span class="genspin"></span> '
            + 'Reading the order…</div>')
        +  '</div></td></tr>';
    }
  });
  h += '</tbody></table></div></div>';

  // WHAT AMAZON WITHHOLDS, said once at the bottom rather than as an empty
  // column with no explanation.
  h += '<div class="cc" style="font-size:11.5px;margin-top:12px;padding:9px 11px;'
    +  'border:1px solid var(--line2);border-radius:6px;line-height:1.6">'
    +  '<i class="ti ti-info-circle"></i> ' + _oEsc(m.pii_note || "") + '</div>';
  body.innerHTML = h;
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

  opts.forEach(function(o){
    const dead = o.state === 'dead', unknown = o.state === 'unknown';
    const cls = dead ? ' odp-row-dead' : '';
    // The cheapest buyable one is marked, so the choice is obvious at a glance
    // rather than being inferred from the order of the rows.
    h += '<div class="odp-rank' + (o.cheapest ? ' best' : '') + cls + '">'
      +  (o.cheapest ? 'best' : (dead ? '—' : (unknown ? '?' : o.rank)))
      +  '</div>'
      +  '<div class="' + cls.trim() + '"><a class="odp-link" target="_blank" '
      +  'rel="noopener" href="' + _oEsc(o.url) + '">'
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

    // HOW IT GETS THERE AND WHEN, spanning the grid on its own line so it can be
    // a full sentence without squeezing the numbers.
    const bits = [];
    if(o.postage_text) bits.push(_oEsc(o.postage_text));
    if(o.delivery_text){
      bits.push('arrives ' + _oEsc(o.delivery_text)
        + (o.delivery_postcode ? ' to ' + _oEsc(o.delivery_postcode) : ''));
    }
    if(o.dispatch_days !== null && o.dispatch_days !== undefined){
      bits.push(o.dispatch_days + ' day' + (o.dispatch_days === 1 ? '' : 's')
                + ' handling');
    }
    if(o.available_qty !== null && o.available_qty !== undefined){
      bits.push(o.available_qty + ' left');
    }
    if(dead){
      bits.push(o.status === 'gone' ? 'the listing has ended' : 'out of stock');
    }
    if(unknown && o.error) bits.push('could not read it: ' + _oEsc(o.error));
    // A PRICE FROM YESTERDAY IS NOT A PRICE. Said plainly rather than left for
    // someone to work out from a timestamp.
    if(o.stale) bits.push('this reading is out of date — press Check in the Repricer');
    h += '<div class="odp-ship' + cls + '">' + (bits.length ? bits.join(' · ') : '')
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
      +  '<td style="padding:3px 4px;color:var(--warn)">'
      +  (l.cogs === null || l.cogs === undefined ? money(null)
          : '−' + _oEsc(_oMoney(l.cogs, currency))
            + (l.qty > 1 && l.unit_cost !== null
                ? ' <span class="cc">(' + _oEsc(_oMoney(l.unit_cost, currency))
                  + ' ea)</span>' : ''))
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
      h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
        +  'margin:3px 0">'
        +  (bd.lines.length > 1
            ? '<code class="cc" style="font-size:9.5px;max-width:170px;'
              + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
              + _oEsc(l.sku) + '</code>' : '')
        +  '<input id="' + id + '" class="ed" style="width:100px" '
        +  'placeholder="' + (unit === null ? 'e.g. 15.10'
              : _oEsc(Number(unit).toFixed(2))) + '">'
        +  '<button class="ghost" onclick="ordSetOrderCogs('
        +  jsArg(orderId) + ',' + jsArg(l.sku || '') + ',' + jsArg(id) + ','
        +  jsArg(accountId || '') + ',' + jsArg(marketplace || '') + ')">Save</button>'
        +  (l.qty > 1 ? '<span class="cc">x ' + l.qty + ' units</span>' : '')
        +  '</div>';
    });
    h += '<div class="cc">Leave the box empty and press Save to clear a cost '
      +  'and put that line back to “not known”.</div></div>';
  }
  return h + '</div>';
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
  try{
    const j = await (await fetch("/cogs/order", {
      method: "POST", headers: {"Content-Type": "application/json"},
      // account_id is the key request_account.named() reads. "account" is not.
      body: JSON.stringify({account_id: accountId || "",
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
        ? "Cost cleared — that line is back to “not known”."
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

async function ordersToggle(orderId, accountId){
  if(ORD.open === orderId){ ORD.open = ""; ordersRender(); return; }
  ORD.open = orderId;
  ordersRender();
  if(ORD.details[orderId]){ return; }
  try{
    const j = await (await fetch("/orders/detail?order_id="
      + encodeURIComponent(orderId) + "&account=" + encodeURIComponent(accountId))).json();
    ORD.details[orderId] = j && j.ok ? j : {error: (j && j.error) || "could not read it"};
  }catch(e){
    ORD.details[orderId] = {error: String(e)};
  }
  if(ORD.open === orderId) ordersRender();
}
