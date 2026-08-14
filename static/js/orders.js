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

let ORD = {rows: [], summary: {}, days: 30, account: "__all__", q: "",
           open: "", details: {}, busy: false};

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
  if(!body || ORD.busy) return;
  ORD.busy = true;
  body.innerHTML = '<div class="cc" style="padding:18px"><span class="genspin"></span> '
    + 'Asking every account for its orders…</div>';
  try{
    const qs = "days=" + encodeURIComponent(ORD.days)
             + "&account=" + encodeURIComponent(ORD.account)
             + (ORD.q ? "&q=" + encodeURIComponent(ORD.q) : "")
             // Opt-in: it costs one Amazon call per order, because an order row
             // carries no SKU and without a SKU there is no cost.
             + (ORD.profit ? "&with_profit=1" : "");
    const j = await (await fetch("/orders/list?" + qs)).json();
    if(!j || !j.ok){
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _oEsc((j&&j.error)||"Could not load orders") + '</div>';
      return;
    }
    ORD.rows = j.rows || []; ORD.summary = j.summary || {}; ORD.meta = j;
    ordersRender();
  }catch(e){
    body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + _oEsc(String(e)) + '</div>';
  }finally{ ORD.busy = false; }
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

  if(m.profit_note){
    h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px">'
      +  '<i class="ti ti-info-circle"></i> ' + _oEsc(m.profit_note) + '</div>';
  }

  h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:900px">'
    +  '<thead><tr>'
    +  ['Order', 'Account', 'Placed', 'Status', 'Units', 'Total',
        'Profit', 'Ships to', 'Channel'].map(function(t){
         return '<th style="text-align:left;font-size:10.5px;padding:6px 8px;'
              + 'white-space:nowrap">' + t + '</th>'; }).join("")
    +  '</tr></thead><tbody>';

  ORD.rows.forEach(function(r){
    const st = _ORD_STATUS[r.status] || {c:"var(--ink2)"};
    const isOpen = (ORD.open === r.order_id);
    h += '<tr style="cursor:pointer" onclick="ordersToggle(' + jsArg(r.order_id)
      +  ',' + jsArg(r.account_id) + ')">'
      +  '<td style="padding:6px 8px;white-space:nowrap">'
      +  '<code style="font-size:11.5px;color:var(--accent2)">' + _oEsc(r.order_id)
      +  '</code>' + (isOpen ? ' <i class="ti ti-chevron-down"></i>'
                             : ' <i class="ti ti-chevron-right" style="opacity:.4"></i>')
      +  '</td>'
      +  '<td style="padding:6px 8px;font-size:11.5px">' + _oEsc(r.account) + '</td>'
      +  '<td style="padding:6px 8px;font-size:11.5px;white-space:nowrap">'
      +  _oEsc(_oWhen(r.purchased)) + '</td>'
      +  '<td style="padding:6px 8px;font-size:11.5px;color:' + st.c + '">'
      +  _oEsc(r.status)
      +  (r.unshipped ? ' <span class="cc">(' + r.unshipped + ' to ship)</span>' : '')
      +  '</td>'
      +  '<td style="padding:6px 8px;font-size:11.5px">' + (r.units||0) + '</td>'
      +  '<td style="padding:6px 8px;font-size:11.5px;white-space:nowrap">'
      +  _oEsc(_oMoney(r.total, r.currency)) + '</td>'
      // WHAT IT EARNED. Blank rather than zero when a cost is unknown -- a
      // partial cost only ever makes an order look better than it was, and the
      // order whose cost is missing is exactly the one someone would use to
      // justify buying more.
      +  '<td style="padding:6px 8px;font-size:11.5px;white-space:nowrap"'
      +  (r.profit_note ? ' title="' + _oEsc(r.profit_note) + '"' : '') + '>'
      +  (r.profit === undefined
          ? '<span class="cc" style="opacity:.5">—</span>'
          : r.profit === null
            ? '<span class="cc" title="' + _oEsc(r.profit_note || "")
              + '">not known</span>'
            : '<span style="color:' + (r.profit > 0 ? "var(--ok,#8fd694)" : "var(--red)")
              + '">' + _oEsc(_oMoney(r.profit, r.currency))
              + (r.margin_pct !== null && r.margin_pct !== undefined
                  ? ' <span class="cc">' + Number(r.margin_pct).toFixed(1) + '%</span>'
                  : '') + '</span>')
      +  '</td>'
      +  '<td style="padding:6px 8px;font-size:11.5px">'
      +  (r.region ? _oEsc(r.region) : '<span class="cc">—</span>') + '</td>'
      +  '<td style="padding:6px 8px;font-size:11px" class="cc">'
      +  _oEsc(r.fulfilment) + (r.prime ? ' · Prime' : '')
      +  (r.business ? ' · Business' : '') + '</td>'
      +  '</tr>';
    if(isOpen){
      h += '<tr><td colspan="9" style="padding:0 8px 10px">'
        +  '<div id="orddet_' + _oEsc(r.order_id) + '">'
        +  (ORD.details[r.order_id] ? _ordDetailHtml(r) :
            '<div class="cc" style="padding:10px"><span class="genspin"></span> '
            + 'Reading the order…</div>')
        +  '</div></td></tr>';
    }
  });
  h += '</tbody></table></div>';

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
