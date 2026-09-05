/* static/js/returnslist.js -- every return, one row each, and what may be done.
 *
 * WHY THIS IS NOT IN returns.js
 * That file draws Returns INTELLIGENCE: reasons grouped into causes, rates,
 * trends, the things you fix a listing or a supplier with. This is the
 * operational half -- one row per return, with Amazon's own status on it, and a
 * detail view for a single one. Different question, different screen, its own
 * file (CLAUDE.md Rule 7).
 *
 * IT READS WHAT WAS KEPT, NOT WHAT AMAZON WILL SAY NOW.
 * /returns/list answers from the returns table, which accumulates. Amazon caps
 * its seller-fulfilled report at 60 days, so a return from four months ago
 * cannot be re-fetched -- it can only be remembered. That is the whole reason
 * the store exists, and it is why this screen and the "Pull from Amazon" button
 * answer different questions.
 *
 * NOTHING HERE WRITES. No message is sent, no refund is issued, no return is
 * approved. The detail view ASKS Amazon which messages it would permit and
 * shows that list, because the list genuinely differs between orders and
 * assuming a fixed set would put buttons on screen that cannot work. Sending is
 * a separate decision with its own confirmation.
 */
var RETL = {rows: [], statuses: {}, coverage: {}, note: "",
            sort: "date", desc: true, status: "", q: "",
            loading: false, open: null, detail: null};

function _rlEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function _rlMoney(v){
  if(v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if(!isFinite(n)) return "—";
  const sym = (typeof CUR_SYMBOL !== "undefined") ? CUR_SYMBOL : "";
  return sym + n.toFixed(2);
}

/* Amazon's own words, coloured by what they mean for you.
 * Deliberately NOT a rule of ours about which statuses are "bad": the status
 * column belongs to Amazon and a second opinion about a state we do not own is
 * how two screens come to disagree. Only the colour is ours. */
function _rlStatusTone(s){
  const t = String(s || "").toLowerCase();
  if(t.indexOf("cancel") >= 0 || t.indexOf("closed") >= 0) return "cc";
  if(t.indexOf("pending") >= 0 || t.indexOf("request") >= 0) return "warn";
  if(t.indexOf("approv") >= 0 || t.indexOf("complet") >= 0
     || t.indexOf("refund") >= 0) return "ok";
  return "";
}

function returnsListOnOpen(){
  if(!RETL.rows.length && !RETL.loading) returnsListLoad();
  else returnsListRender();
}

async function returnsListLoad(){
  const host = document.getElementById("returns_list");
  if(!host) return;
  RETL.loading = true;
  host.innerHTML = '<div class="cc" style="padding:16px">'
    + '<span class="genspin"></span> Loading stored returns…</div>';
  try{
    const qs = [];
    const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
              ? CUR_ACCOUNT.id : "";
    const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
    if(a) qs.push("id=" + encodeURIComponent(a));
    if(m && m !== "__all__") qs.push("marketplace=" + encodeURIComponent(m));
    const r = await fetch("/returns/list?" + qs.join("&"));
    const j = await r.json();
    RETL.rows = (j && j.rows) || [];
    RETL.statuses = (j && j.statuses) || {};
    RETL.coverage = (j && j.coverage) || {};
    RETL.note = (j && j.note) || ((j && !j.ok && j.error) || "");
  }catch(e){
    RETL.rows = []; RETL.note = "Could not load stored returns.";
  }
  RETL.loading = false;
  returnsListRender();
}

function returnsListSort(k){
  if(RETL.sort === k) RETL.desc = !RETL.desc;
  else { RETL.sort = k; RETL.desc = true; }
  returnsListRender();
}

function returnsListStatus(s){ RETL.status = (RETL.status === s) ? "" : s;
                               returnsListRender(); }
function returnsListSearch(v){ RETL.q = v || ""; returnsListRender(); }

function _rlVisible(){
  const q = RETL.q.trim().toLowerCase();
  return (RETL.rows || []).filter(function(r){
    if(RETL.status && String(r.status || "") !== RETL.status) return false;
    if(!q) return true;
    // The things you actually have in your hand: an order number off an email,
    // an ASIN off Seller Central, a SKU off a label, or the product's name.
    return ["order_id", "asin", "sku", "name", "reason", "resolution"]
      .some(function(f){ return String(r[f] || "").toLowerCase().indexOf(q) >= 0; });
  });
}

const _RETL_COLS = [
  {k: "date",         t: "Returned",  kind: "text"},
  {k: "name",         t: "Product",   kind: "product"},
  {k: "qty",          t: "Qty",       kind: "count"},
  {k: "reason",       t: "Reason",    kind: "text"},
  {k: "status",       t: "Status",    kind: "status"},
  {k: "resolution",   t: "Resolution", kind: "text"},
  {k: "order_amount", t: "Order",     kind: "money"},
  {k: "refunded",     t: "Refunded",  kind: "money"},
];

function returnsListRender(){
  const host = document.getElementById("returns_list");
  if(!host) return;

  const cov = RETL.coverage || {};
  let h = '<div style="display:flex;align-items:center;gap:10px;margin:2px 0 10px;flex-wrap:wrap">'
    + '<div style="font-size:12.5px;font-weight:600">All returns</div>';

  // WHAT IS HELD, said before anything is read off the table. A list of 40
  // returns over a period the reports only covered half of is not wrong, but it
  // is misleading unless it says which half.
  if(cov.held){
    h += '<span class="cc" style="font-size:11px">'
      + (cov.n || 0) + ' kept · ' + _rlEsc(cov.first_date || "") + ' to '
      + _rlEsc(cov.last_date || "")
      + (cov.fba ? ' · ' + cov.fba + ' FBA' : '')
      + (cov.mfn ? ' · ' + cov.mfn + ' seller-fulfilled' : '')
      + '</span>';
  }
  h += '<span style="margin-left:auto;display:flex;gap:8px;align-items:center">'
    + '<input class="ed" style="width:210px" placeholder="Order, ASIN, SKU or name…" '
    + 'value="' + _rlEsc(RETL.q) + '" oninput="returnsListSearch(this.value)">'
    + '<button class="mktbtn" onclick="returnsListLoad()" '
    + 'title="Re-read what has been stored. To fetch NEW returns from Amazon, '
    + 'use Pull from Amazon above — this reads what is already kept.">'
    + '<i class="ti ti-refresh"></i> Reload</button></span></div>';

  if(RETL.note){
    h += '<div class="cc" style="padding:12px;border:1px dashed var(--line2);'
      + 'border-radius:6px;font-size:12px;margin-bottom:10px">'
      + _rlEsc(RETL.note) + '</div>';
  }

  // The status chips double as the filter, so the count you read is the count
  // you get when you click it.
  const st = RETL.statuses || {};
  const keys = Object.keys(st).sort(function(a, b){ return st[b] - st[a]; });
  if(keys.length){
    h += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">';
    keys.forEach(function(k){
      // jsArg, NOT JSON.stringify. JSON.stringify emits a bare double quote,
      // which closes the onclick attribute -- the handler then renders
      // perfectly and does nothing at all. That exact bug shipped twice before
      // (the Users screen and "Use as main" in the image library), so
      // test_useredit.js now scans the whole static/js tree for the shape.
      // jsArg (users.js) escapes for the JS string AND for the attribute.
      h += '<button class="db-chip' + (RETL.status === k ? ' on' : '') + '" '
        + 'onclick="returnsListStatus(' + jsArg(k) + ')">'
        + _rlEsc(k) + ' <b>' + st[k] + '</b></button>';
    });
    h += '</div>';
  }

  const rows = _rlVisible();
  if(!rows.length){
    h += '<div class="cc" style="padding:14px;border:1px dashed var(--line2);'
      + 'border-radius:6px;font-size:12px">'
      + (RETL.rows.length ? 'No returns match that filter.'
                          : 'Nothing stored yet.') + '</div>';
    host.innerHTML = h; return;
  }

  const dir = RETL.desc ? -1 : 1;
  const sorted = rows.slice().sort(function(a, b){
    let x = a[RETL.sort], y = b[RETL.sort];
    if(x === null || x === undefined || x === "") return 1;
    if(y === null || y === undefined || y === "") return -1;
    if(typeof x === "string") return dir * (x < y ? 1 : x > y ? -1 : 0);
    return dir * (x - y);
  });

  h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:900px">'
    + '<thead><tr>';
  _RETL_COLS.forEach(function(c){
    const right = (c.kind === "money" || c.kind === "count");
    h += '<th style="text-align:' + (right ? "right" : "left") + ';font-size:11px;'
      + 'cursor:pointer;white-space:nowrap;padding:6px 8px" '
      + 'onclick="returnsListSort(' + jsArg(c.k) + ')">'
      + _rlEsc(c.t) + (RETL.sort === c.k ? (RETL.desc ? " ▾" : " ▴") : "") + '</th>';
  });
  h += '<th></th></tr></thead><tbody>';

  sorted.forEach(function(r){
    h += '<tr>';
    _RETL_COLS.forEach(function(c){
      const v = r[c.k];
      let cell, right = (c.kind === "money" || c.kind === "count");
      if(c.kind === "money") cell = _rlMoney(v);
      else if(c.kind === "status"){
        const tone = _rlStatusTone(v);
        cell = v ? '<span style="font-size:10.5px' +
                   (tone === "ok" ? ";color:var(--ok)" :
                    tone === "warn" ? ";color:var(--warn)" : "") + '">'
                   + _rlEsc(v) + '</span>'
                 : '<span class="cc">—</span>';
      }
      else if(c.kind === "product"){
        cell = '<span style="display:block;overflow:hidden;text-overflow:ellipsis;'
             + 'white-space:nowrap;max-width:300px" title="' + _rlEsc(v) + '">'
             + _rlEsc(v || "—") + '</span>'
             + '<span class="cc" style="font-size:10px">' + _rlEsc(r.asin || "")
             + (r.sku ? ' · ' + _rlEsc(r.sku) : '') + '</span>';
      }
      else if(v === null || v === undefined || v === "") cell = '<span class="cc">—</span>';
      else cell = _rlEsc(String(v));
      h += '<td style="text-align:' + (right ? "right" : "left")
        + ';padding:5px 8px;font-size:11.5px;vertical-align:top">' + cell + '</td>';
    });
    h += '<td style="text-align:right;padding:5px 8px"><button class="ib" '
      + 'title="Open this return" onclick="returnsListOpen('
      + jsArg(r.identity) + ')">'
      + '<i class="ti ti-chevron-right"></i></button></td></tr>';
  });
  h += '</tbody></table></div>';

  host.innerHTML = h + '<div id="returns_detail"></div>';
  if(RETL.open) returnsListRenderDetail();
}

async function returnsListOpen(identity){
  RETL.open = identity;
  RETL.detail = null;
  returnsListRenderDetail();
  try{
    const qs = ["identity=" + encodeURIComponent(identity)];
    const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
              ? CUR_ACCOUNT.id : "";
    const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
    if(a) qs.push("id=" + encodeURIComponent(a));
    if(m && m !== "__all__") qs.push("marketplace=" + encodeURIComponent(m));
    const r = await fetch("/returns/detail?" + qs.join("&"));
    RETL.detail = await r.json();
  }catch(e){
    RETL.detail = {ok: false, error: "Could not open that return."};
  }
  returnsListRenderDetail();
}

function returnsListClose(){ RETL.open = null; RETL.detail = null;
                             returnsListRenderDetail(); }

function returnsListRenderDetail(){
  const host = document.getElementById("returns_detail");
  if(!host) return;
  if(!RETL.open){ host.innerHTML = ""; return; }
  const j = RETL.detail;
  if(!j){
    host.innerHTML = '<div class="cc" style="padding:14px"><span class="genspin"></span> '
      + 'Opening…</div>';
    return;
  }
  if(!j.ok){
    host.innerHTML = '<div style="padding:12px;color:var(--red)">'
      + _rlEsc(j.error || "Could not open that return.") + '</div>';
    return;
  }
  const r = j["return"] || {};
  const row = function(k, v){
    return '<tr><td class="k" style="white-space:nowrap">' + _rlEsc(k)
         + '</td><td class="v">' + v + '</td></tr>';
  };

  let h = '<div class="salespanel" style="margin-top:14px">'
    + '<div class="panelhead"><div>'
    + '<p class="paneltitle">' + _rlEsc(r.name || r.asin || "Return") + '</p>'
    + '<p class="panelsub">Order ' + _rlEsc(r.order_id || "—")
    + ' · returned ' + _rlEsc(r.date || "—") + '</p></div>'
    + '<button class="ib" onclick="returnsListClose()" title="Close">'
    + '<i class="ti ti-x"></i></button></div>';

  h += '<table class="kv" style="width:100%">'
    + row("Status", _rlEsc(r.status || "—"))
    + row("Reason", _rlEsc(r.reason || "—")
          + (r.reason_raw && r.reason_raw !== r.reason
             ? ' <span class="cc" style="font-size:10.5px">(Amazon wrote: '
               + _rlEsc(r.reason_raw) + ')</span>' : ''))
    + row("Resolution", _rlEsc(r.resolution || "—"))
    + row("Quantity", _rlEsc(String(r.qty == null ? "—" : r.qty)))
    + row("Order amount", _rlMoney(r.order_amount))
    + row("Refunded", _rlMoney(r.refunded))
    + row("ASIN / SKU", _rlEsc(r.asin || "—") + ' · ' + _rlEsc(r.sku || "—"))
    + row("Kind", r.kind === "fba" ? "Fulfilled by Amazon"
                                   : "Seller-fulfilled");

  // FBA-ONLY, AND ABSENT RATHER THAN BLANK. Amazon grades a return and records
  // the buyer's comment only when it receives one itself. A seller-fulfilled
  // return goes straight back to you, so Amazon never sees it and has no
  // column for either -- which is a different fact from "undamaged, nothing
  // said", and the screen must not let them look the same.
  if(r.kind === "fba"){
    h += row("Condition", _rlEsc(r.disposition || "—"))
      +  row("Buyer's comment", _rlEsc(r.comment || "—"));
  }else{
    h += '<tr><td class="k">Condition</td><td class="v cc" style="font-size:11px">'
      + 'Not reported. Amazon grades a return only when it receives one itself; '
      + 'this came straight back to you, so Amazon never saw it.</td></tr>';
  }
  h += '</table>';

  if((j.same_order || []).length){
    h += '<div style="margin-top:10px;font-size:11.5px">'
      + '<b>Also returned on this order:</b><ul style="margin:4px 0 0 16px">';
    j.same_order.forEach(function(s){
      h += '<li style="font-size:11px">' + _rlEsc(s.name || s.asin || "")
        + ' — ' + _rlEsc(s.reason || "") + '</li>';
    });
    h += '</ul></div>';
  }

  // WHAT AMAZON WOULD LET US SEND. Asked per order, because the answer really
  // does differ between orders, and each action carries Amazon's OWN schema --
  // so the form below is drawn from what Amazon says it wants, never from a
  // shape assumed here.
  h += '<div style="margin-top:12px;padding:10px;border:1px solid var(--line2);'
    + 'border-radius:6px">'
    + '<div style="font-size:11.5px;font-weight:600;margin-bottom:6px">'
    + 'Contacting the customer</div>';

  const acts = j.actions || [];
  if(acts.length){
    h += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">';
    acts.forEach(function(a){
      const on = (RETL.action === a.name);
      // An action Amazon has disabled, or one this app has no verified
      // endpoint for, is shown and NOT offered -- with the reason on hover.
      // Hiding it would leave somebody wondering why Seller Central offers
      // something this screen does not.
      h += '<button class="db-chip' + (on ? ' on' : '') + '"'
        + (a.sendable ? ' onclick="returnsPick(' + jsArg(a.name) + ')"'
                      : ' disabled style="opacity:.5;cursor:not-allowed"')
        + ' title="' + _rlEsc(a.sendable ? (a.description || a.title)
                                         : a.why_not) + '">'
        + _rlEsc(a.title || a.name) + '</button>';
    });
    h += '</div>';

    const picked = acts.filter(function(a){ return a.name === RETL.action
                                                   && a.sendable; })[0];
    if(picked){
      h += '<div style="border-top:1px solid var(--line2);padding-top:8px">'
        + '<div class="cc" style="font-size:11px;margin-bottom:6px">'
        + _rlEsc(picked.description || "") + '</div>';
      (picked.fields || []).forEach(function(f){
        h += '<div style="margin-bottom:6px">'
          + '<div style="font-size:11px;margin-bottom:3px">' + _rlEsc(f.title)
          + (f.required ? ' <span style="color:var(--red)">*</span>' : '')
          + (f.max_length ? ' <span class="cc">(up to ' + f.max_length
                            + ' characters)</span>' : '')
          + '</div>'
          + '<textarea id="retmsg_' + _rlEsc(f.name) + '" class="ed" rows="4" '
          + 'style="width:100%;font-size:12px"'
          + (f.max_length ? ' maxlength="' + f.max_length + '"' : '')
          + '></textarea></div>';
      });
      if(!(picked.fields || []).length){
        h += '<div class="cc" style="font-size:11px;margin-bottom:6px">'
          + 'This message has no text — Amazon sends its own wording.</div>';
      }
      h += '<button class="mktbtn on" onclick="returnsSend()">'
        + '<i class="ti ti-send"></i> Send to the customer</button>'
        + '<span id="retmsg_status" class="cc" style="margin-left:8px;'
        + 'font-size:11px"></span>'
        // SAID BEFORE THE BUTTON IS PRESSED, not after. A message to a buyer
        // cannot be recalled, and Amazon does not give it back afterwards.
        + '<div class="cc" style="font-size:10.5px;margin-top:6px">'
        + 'This goes to the buyer through Amazon and cannot be unsent. Amazon '
        + 'does not return it afterwards, so this app\'s own record is the '
        + 'only copy.</div></div>';
    }
  }

  h += '<div class="cc" style="font-size:11px;line-height:1.5;margin-top:6px">'
    + _rlEsc(j.actions_note || "")
    + (j.actions_error ? ' <span style="color:var(--red)">'
                         + _rlEsc(j.actions_error) + '</span>' : '')
    + '</div>';

  // WHAT WAS ALREADY SENT ABOUT THIS ORDER. Amazon publishes no sent-message
  // history at all, so without this there is no way to answer "have we already
  // replied to them?" -- and the answer decides whether to write again.
  if((j.sent || []).length){
    h += '<div style="margin-top:10px;border-top:1px solid var(--line2);'
      + 'padding-top:8px"><div style="font-size:11.5px;font-weight:600">'
      + 'Already sent about this order</div>';
    j.sent.forEach(function(s){
      let body = "";
      try{ const o = JSON.parse(s.body || "{}");
           body = Object.keys(o).map(function(k){ return o[k]; }).join(" "); }
      catch(e){ body = s.body || ""; }
      h += '<div style="margin-top:6px;font-size:11px">'
        + '<span style="' + (s.ok ? '' : 'color:var(--red)') + '">'
        + _rlEsc(s.action) + '</span> <span class="cc">'
        + _rlEsc(s.sent_at || "") + (s.sent_by ? ' · ' + _rlEsc(s.sent_by) : '')
        + (s.ok ? '' : ' · refused') + '</span>'
        + (body ? '<div class="cc" style="font-size:10.5px;white-space:pre-wrap">'
                  + _rlEsc(body.slice(0, 400)) + '</div>' : '')
        + (s.error ? '<div style="color:var(--red);font-size:10.5px">'
                     + _rlEsc(s.error) + '</div>' : '')
        + '</div>';
    });
    h += '</div>';
  }
  h += '</div>';

  h += '</div>';
  host.innerHTML = h;
}

function returnsPick(action){
  RETL.action = (RETL.action === action) ? "" : action;
  returnsListRenderDetail();
}

async function returnsSend(){
  const j = RETL.detail;
  if(!j || !j.ok || !RETL.action) return;
  const act = (j.actions || []).filter(function(a){
    return a.name === RETL.action; })[0];
  if(!act || !act.sendable) return;

  const values = {};
  let missing = "";
  (act.fields || []).forEach(function(f){
    const el = document.getElementById("retmsg_" + f.name);
    const v = el ? String(el.value || "").trim() : "";
    if(f.required && !v) missing = f.title;
    if(v) values[f.name] = v;
  });
  if(missing){
    const st = document.getElementById("retmsg_status");
    if(st) st.innerHTML = '<span style="color:var(--red)">' + _rlEsc(missing)
      + ' is required.</span>';
    return;
  }

  // ASKED BEFORE IT GOES. This is the one action in the returns screen that
  // reaches another person and cannot be undone, so it is never one click.
  const preview = Object.keys(values).map(function(k){ return values[k]; })
                        .join("\n\n");
  const ok = await uiConfirm(
    "Send this to the customer?\n\n" + (act.title || RETL.action)
    + "\nOrder " + ((j["return"] || {}).order_id || "")
    + (preview ? "\n\n" + preview : "")
    + "\n\nIt goes through Amazon and cannot be unsent.");
  if(!ok) return;

  const st = document.getElementById("retmsg_status");
  if(st) st.innerHTML = '<span class="genspin"></span> Sending…';
  try{
    const qs = [];
    const a = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
              ? CUR_ACCOUNT.id : "";
    const m = (typeof WS_MARKET !== "undefined" && WS_MARKET) ? WS_MARKET : "";
    if(a) qs.push("id=" + encodeURIComponent(a));
    if(m && m !== "__all__") qs.push("marketplace=" + encodeURIComponent(m));
    const r = await fetch("/returns/message?" + qs.join("&"), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({order_id: (j["return"] || {}).order_id,
                            action: RETL.action, values: values})});
    const res = await r.json();
    if(!res || !res.ok){
      if(st) st.innerHTML = '<span style="color:var(--red)">'
        + _rlEsc((res && res.error) || "Amazon refused it.") + '</span>';
      return;
    }
    if(typeof toast === "function") toast("Message sent");
    RETL.action = "";
    // Re-open so the sent-message record below is the server's, not ours.
    returnsListOpen(RETL.open);
  }catch(e){
    if(st) st.innerHTML = '<span style="color:var(--red)">Could not send.</span>';
  }
}
