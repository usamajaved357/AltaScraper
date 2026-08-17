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
let ORD = {rows: [], summary: {}, days: 30, account: "", q: "",
           open: "", details: {}, busy: false, profit: true};

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

const _ORD_STATUS = {
  Shipped:            {c:"#8fd694"},
  Unshipped:          {c:"#e8c66a"},
  PartiallyShipped:   {c:"#e8c66a"},
  Pending:            {c:"#8b949e"},
  Canceled:           {c:"#e88a8a"},
  Cancelled:          {c:"#e88a8a"},
};

function ordersOnOpen(){
  // The account picker is filled from the accounts the app already knows, so it
  // cannot drift from what /orders/list will actually ask.
  const sel = document.getElementById("ord_account");
  if(sel && sel.options.length <= 1 && typeof ACCOUNTS !== "undefined" && ACCOUNTS){
    ACCOUNTS.forEach(function(a){
      if(!a || !a.id) return;
      const o = document.createElement("option");
      o.value = a.id; o.textContent = a.label || a.id;
      sel.appendChild(o);
    });
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
  const base = "days=" + encodeURIComponent(ORD.days)
             + "&account=" + encodeURIComponent(ORD.account)
             + (ORD.q ? "&q=" + encodeURIComponent(ORD.q) : "");
  try{
    const j = await (await fetch("/orders/list?" + base)).json();
    if(mine !== ORD.loadId) return;             // a newer load has taken over
    if(!j || !j.ok){
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _oEsc((j&&j.error)||"Could not load orders") + '</div>';
      return;
    }
    ORD.rows = j.rows || []; ORD.summary = j.summary || {}; ORD.meta = j;
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
function ordersSetAccount(a){ ORD.account = a; ordersLoad(); }
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
        ? '<img src="' + _oEsc(img) + '" loading="lazy" style="width:34px;height:34px;'
          + 'object-fit:contain;background:#0d1220;border-radius:5px;flex:0 0 34px">'
        : '<span style="width:34px;height:34px;border-radius:5px;background:#0d1220;'
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
  const m = ORD.meta || {}, s = ORD.summary || {};
  let h = "";

  // Which accounts answered, and which did not. An account whose token expired
  // is a different fact from having no orders, and the difference is invisible
  // if a failure only removes rows.
  (m.errors || []).forEach(function(e){
    h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px;padding:8px 11px;'
      +  'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
      +  '<i class="ti ti-alert-triangle"></i> <b>' + _oEsc(e.account) + '</b> — '
      +  _oEsc(e.error) + '</div>';
  });

  const cur = Object.keys(s.revenue_by_currency || {});
  h += '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:baseline;'
    +  'margin:0 0 10px;font-size:12.5px">'
    +  '<b>' + (s.orders || 0) + ' order' + ((s.orders===1)?'':'s') + '</b>'
    +  '<span class="cc">' + (s.units || 0) + ' units</span>'
    // Per currency, never added together: pounds plus dollars is a number that
    // is wrong in both.
    +  cur.map(function(c){
         return '<span class="cc">' + _oEsc(c) + ' '
              + Number(s.revenue_by_currency[c]).toFixed(2) + '</span>'; }).join("")
    // SAID OUT LOUD, because the Sales screen shows a different figure for these
    // same orders and neither is wrong. This is what the buyers PAID, shipping
    // included; Total Sales on the Sales screen is ordered product sales, which
    // excludes it. On three orders of one item they read 102.21 and 89.97, and
    // an unexplained gap between two of your own screens is worse than either.
    +  (cur.length ? '<span class="cc" title="Summed from each order&#39;s total, so '
                   + 'it includes shipping. The Sales screen shows ordered product '
                   + 'sales, which excludes shipping — that is the figure Amazon '
                   + 'calls Total Sales.">charged, incl. shipping</span>' : '')
    +  '<span class="cc">last ' + ORD.days + ' days</span>'
    +  '</div>';

  if(!ORD.rows.length){
    h += '<div class="cc" style="padding:20px;border:1px dashed #2a3446;border-radius:6px">'
      +  'No orders in the last ' + ORD.days + ' days'
      +  (ORD.q ? ' matching “' + _oEsc(ORD.q) + '”' : '')
      +  '. Accounts asked: ' + _oEsc((m.accounts_asked||[]).join(", ") || "none")
      +  '.</div>';
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
              + '>' + t + '</th>'; }).join("")
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
      +  '<td style="font-size:11.5px;color:' + st.c + '">'
      +  '<span style="white-space:nowrap">' + _oEsc(r.status) + '</span>'
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
    +  'border:1px solid #26303f;border-radius:6px;line-height:1.6">'
    +  '<i class="ti ti-info-circle"></i> ' + _oEsc(m.pii_note || "") + '</div>';
  body.innerHTML = h;
}

function _ordDetailHtml(r){
  const d = ORD.details[r.order_id] || {};
  const items = d.items || [];
  if(d.error){
    return '<div class="cc" style="padding:10px;color:var(--red)">'
         + _oEsc(d.error) + '</div>';
  }
  let h = '<div style="border:1px solid #26303f;border-radius:8px;padding:10px 12px">'
        + '<div style="font-size:11.5px;font-weight:600;margin-bottom:6px">'
        + items.length + ' line' + (items.length===1?'':'s') + ' in this order</div>';
  items.forEach(function(it){
    h += '<div style="display:flex;gap:10px;align-items:baseline;padding:5px 0;'
      +  'border-top:1px solid #1c2531;font-size:11.5px">'
      +  '<span style="flex:1;min-width:0">'
      +  '<span style="display:block;overflow:hidden;text-overflow:ellipsis;'
      +  'white-space:nowrap" title="' + _oEsc(it.title) + '">'
      +  _oEsc(it.title || "(no title)") + '</span>'
      +  '<code class="cc" style="font-size:10px">' + _oEsc(it.sku)
      +  (it.asin ? ' · ' + _oEsc(it.asin) : '') + '</code></span>'
      +  '<span class="cc" style="white-space:nowrap">' + it.qty + ' ×</span>'
      +  '<span style="white-space:nowrap">' + _oEsc(_oMoney(it.price, it.currency))
      +  '</span>'
      +  (it.cancel_requested
          ? '<span style="color:var(--warn);white-space:nowrap">cancel requested</span>'
          : '')
      +  '</div>';
  });
  const o = d.order || {};
  // What it earned, worked out from the lines that are already here.
  if(o.profit !== undefined){
    h += '<div style="margin-top:8px;padding-top:7px;border-top:1px solid #1c2531;'
      +  'font-size:11.5px">'
      +  (o.profit === null
          ? '<span class="cc">Profit not known — ' + _oEsc(o.profit_note || "") + '</span>'
          : '<b>Earned ' + _oEsc(_oMoney(o.profit, o.currency)) + '</b>'
            + (o.margin_pct !== null && o.margin_pct !== undefined
                ? ' <span class="cc">(' + Number(o.margin_pct).toFixed(1) + '% margin)</span>'
                : '')
            + '<div class="cc" style="font-size:10.5px;margin-top:2px">'
            + _oEsc(o.profit_note || "") + '</div>')
      +  '</div>';
  }
  h += '<div class="cc" style="font-size:11px;margin-top:8px;padding-top:7px;'
    +  'border-top:1px solid #1c2531">'
    +  'Ship by ' + _oEsc(_oWhen(o.ship_by)) + ' · deliver by '
    +  _oEsc(_oWhen(o.deliver_by))
    +  (o.region ? ' · to ' + _oEsc(o.region) : '')
    +  '</div></div>';
  return h;
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
