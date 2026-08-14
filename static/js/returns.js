// ===================== WHY THINGS COME BACK =====================
// Built from the FBA Returns Intelligence report, with the sections this app's
// data can actually support — and honest, on screen, about the two it cannot.
//
// The classification is the point. Fifty reason codes are a list; four causes
// are a decision, and each one has a different answer:
//
//   Product Quality       talk to the supplier, or stop selling it
//   Listing Content       your listing set the wrong expectation — cheapest fix
//   Customer Preference   nothing went wrong; some of this is just trade
//   Shipping / Delivery   packaging, or the carrier
//
// One thing here is better than the report it came from: that page ESTIMATED
// lost revenue. The seller-fulfilled report carries the amount actually
// refunded, so this states the real figure and says which it is.

let RET = {data: null, days: 30, busy: false, sort: "returns"};

function _rEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _rMoney(v){
  return (v===null||v===undefined) ? "—" : Number(v).toFixed(2);
}
function _rPct(v){
  return (v===null||v===undefined) ? "—" : Number(v).toFixed(2)+"%";
}

const RET_NATURE_COLOUR = {
  "Product Quality":     "#ef5350",
  "Listing Content":     "#f5a623",
  "Customer Preference": "#4f8cff",
  "Shipping / Delivery": "#a78bfa",
  "Unclassified":        "#8b90a0",
};

function returnsOnOpen(){ if(!RET.data) returnsLoad(); else returnsRender(); }
function returnsSetDays(d){ RET.days = d; returnsLoad(); }

async function returnsLoad(){
  const body = document.getElementById("retbody");
  if(!body || RET.busy) return;
  RET.busy = true;
  body.innerHTML = '<div class="cc" style="padding:18px"><span class="genspin"></span> '
    + 'Asking Amazon for the returns report — they build these slowly, so this '
    + 'can take a minute…</div>';
  try{
    const j = await (await fetch("/returns/report?days=" + RET.days)).json();
    if(!j || !j.ok){
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _rEsc((j&&j.error)||"Could not load returns") + '</div>';
      return;
    }
    RET.data = j; returnsRender();
  }catch(e){
    body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + _rEsc(String(e)) + '</div>';
  }finally{ RET.busy = false; }
}

function returnsUploadOpen(){
  const i = document.getElementById("ret_file");
  if(i) i.click();
}

async function returnsUploadFile(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  const body = document.getElementById("retbody");
  if(body) body.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Reading ' + _rEsc(f.name) + '…</div>';
  try{
    const fd = new FormData();
    fd.append("file", f);
    const j = await (await fetch("/returns/upload", {method:"POST", body: fd})).json();
    if(!j || !j.ok){
      if(body) body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _rEsc((j&&j.error)||"Could not read that file") + '</div>';
      return;
    }
    RET.data = j; returnsRender();
  }catch(e){
    if(body) body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + _rEsc(String(e)) + '</div>';
  }finally{ input.value = ""; }
}

function _retBars(obj, colourFn, total){
  const keys = Object.keys(obj || {});
  if(!keys.length) return '<div class="cc" style="font-size:11.5px">nothing yet</div>';
  const max = Math.max.apply(null, keys.map(k => obj[k]));
  return keys.map(function(k){
    const n = obj[k], pct = total ? (n / total * 100) : 0;
    const col = colourFn ? colourFn(k) : "var(--accent)";
    return '<div style="margin-bottom:7px">'
      + '<div style="display:flex;justify-content:space-between;font-size:11.5px;'
      + 'margin-bottom:2px"><span>' + _rEsc(k.replace(/_/g, " ").toLowerCase())
      + '</span><span class="cc">' + n
      + (total ? ' · ' + pct.toFixed(0) + '%' : '') + '</span></div>'
      + '<div style="height:6px;background:#0d1220;border-radius:3px;overflow:hidden">'
      + '<div style="height:100%;width:' + (max ? (n / max * 100) : 0) + '%;'
      + 'background:' + col + '"></div></div></div>';
  }).join("");
}

function _retSpark(daily){
  const days = Object.keys(daily || {});
  if(!days.length) return "";
  const vals = days.map(d => daily[d]);
  const max = Math.max.apply(null, vals) || 1;
  const W = 720, H = 90, pad = 8;
  const x = i => pad + (days.length === 1 ? (W-2*pad)/2 : i*(W-2*pad)/(days.length-1));
  const y = v => H - pad - (v / max) * (H - 2*pad);
  const d = days.map((k,i) => (i?"L":"M") + x(i).toFixed(1) + " " + y(daily[k]).toFixed(1)).join(" ");
  return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" style="height:auto;display:block;'
    + 'background:#0d1220;border:1px solid #1e2733;border-radius:8px">'
    + '<path d="'+d+'" fill="none" stroke="#ef5350" stroke-width="2" stroke-linejoin="round"/>'
    + days.map(function(k,i){
        return '<rect x="'+(x(i)-6)+'" y="'+pad+'" width="12" height="'+(H-2*pad)+'" '
             + 'fill="transparent"><title>'+_rEsc(k)+': '+daily[k]+'</title></rect>'; }).join("")
    + '</svg>';
}

function returnsRender(){
  const body = document.getElementById("retbody");
  const d = RET.data;
  if(!body || !d) return;
  let h = "";

  if(d.note){
    h += '<div class="cc" style="font-size:12px;margin:0 0 10px;padding:9px 11px;'
      +  'border:1px solid #26303f;border-radius:6px">'
      +  '<i class="ti ti-info-circle"></i> ' + _rEsc(d.note) + '</div>';
  }

  // ---- the KPI row ----------------------------------------------------
  const kpi = function(label, value, sub){
    return '<div style="background:var(--panel);border:1px solid var(--line);'
      + 'border-radius:10px;padding:14px 16px">'
      + '<div class="cc" style="font-size:10.5px;text-transform:uppercase;'
      + 'letter-spacing:.06em;margin-bottom:6px">' + _rEsc(label) + '</div>'
      + '<div style="font-size:23px;font-weight:700;line-height:1.1">' + value + '</div>'
      + (sub ? '<div class="cc" style="font-size:11px;margin-top:4px">' + sub + '</div>' : '')
      + '</div>';
  };
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));'
    +  'gap:12px;margin-bottom:18px">'
    +  kpi("Returns", d.total_returns, d.units_returned + " units")
    // A count says nothing on its own: twelve is excellent on four thousand
    // orders and a catastrophe on twenty. So the rate is the headline, and its
    // absence is stated rather than filled with a plausible denominator.
    +  kpi("Return rate", _rPct(d.return_rate),
           d.total_ordered ? ("of " + d.total_ordered + " sold")
                           : '<span style="color:var(--warn)">units sold not known — sync Sales</span>')
    +  kpi(d.refunded_is_actual ? "Refunded" : "Refunded (not reported)",
           _rMoney(d.refunded),
           d.refunded_is_actual ? "actually paid back, not an estimate" : "")
    +  kpi("Products affected", d.unique_skus, "")
    +  '</div>';

  // ---- what the returns are really about -------------------------------
  const totalNat = Object.values(d.natures || {}).reduce((a,b)=>a+b, 0);
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px">';
  h += '<div style="background:var(--panel);border:1px solid var(--line);'
    +  'border-radius:10px;padding:14px 16px">'
    +  '<div style="font-weight:600;font-size:13px;margin-bottom:3px">What is actually going wrong</div>'
    +  '<div class="cc" style="font-size:11px;margin-bottom:10px">'
    +  'Amazon gives fifty reason codes. These are the four things you can DO '
    +  'something about.</div>'
    +  _retBars(d.natures, k => RET_NATURE_COLOUR[k] || "var(--accent)", totalNat);
  // Each cause carries what to do about it, because a bar chart of categories
  // invites "so what" and this is the answer.
  Object.keys(d.natures || {}).forEach(function(k){
    const act = (d.nature_actions || {})[k];
    if(!act) return;
    h += '<div style="border-left:2px solid ' + (RET_NATURE_COLOUR[k]||"var(--line)")
      +  ';padding:5px 0 5px 9px;margin:8px 0;font-size:11.5px">'
      +  '<b>' + _rEsc(k) + '</b><div class="cc" style="margin-top:2px">'
      +  _rEsc(act) + '</div></div>';
  });
  h += '</div>';

  h += '<div style="background:var(--panel);border:1px solid var(--line);'
    +  'border-radius:10px;padding:14px 16px">'
    +  '<div style="font-weight:600;font-size:13px;margin-bottom:10px">Amazon\'s own reason codes</div>'
    +  _retBars(d.reasons, null, d.units_returned) + '</div>';
  h += '</div>';

  // ---- when ------------------------------------------------------------
  if(Object.keys(d.daily || {}).length){
    h += '<div style="background:var(--panel);border:1px solid var(--line);'
      +  'border-radius:10px;padding:14px 16px;margin-bottom:18px">'
      +  '<div style="font-weight:600;font-size:13px;margin-bottom:8px">Returns per day</div>'
      +  _retSpark(d.daily) + '</div>';
  }

  // ---- FBA-only sections, present or explained -------------------------
  if(d.has_disposition){
    h += '<div style="background:var(--panel);border:1px solid var(--line);'
      +  'border-radius:10px;padding:14px 16px;margin-bottom:18px">'
      +  '<div style="font-weight:600;font-size:13px;margin-bottom:10px">'
      +  'What condition they came back in</div>'
      +  _retBars(d.dispositions, null, d.units_returned) + '</div>';
  }
  if(d.has_comments){
    h += '<div style="background:var(--panel);border:1px solid var(--line);'
      +  'border-radius:10px;padding:14px 16px;margin-bottom:18px">'
      +  '<div style="font-weight:600;font-size:13px;margin-bottom:3px">'
      +  'What the customers said</div>'
      +  '<div class="cc" style="font-size:11px;margin-bottom:10px">'
      +  (d.comments||[]).length + ' comments, in their own words.</div>'
      +  '<div style="max-height:340px;overflow:auto">'
      +  (d.comments||[]).map(function(c){
           return '<div style="border-top:1px solid #1c2531;padding:7px 0;font-size:11.5px">'
                + '<div>' + _rEsc(c.text) + '</div>'
                + '<div class="cc" style="font-size:10px;margin-top:3px">'
                + _rEsc(c.sku || c.asin || "") + ' · '
                + _rEsc(String(c.reason||"").replace(/_/g," ").toLowerCase())
                + '</div></div>'; }).join("")
      +  '</div></div>';
  }
  // WHAT THIS DATA CANNOT ANSWER, and why. A section that is simply absent
  // reads as a fault; one that explains itself reads as a fact about Amazon.
  (d.unavailable || []).forEach(function(u){
    h += '<div class="cc" style="font-size:11.5px;margin-bottom:10px;padding:10px 12px;'
      +  'border:1px dashed #2a3446;border-radius:8px">'
      +  '<b>' + _rEsc(u.section) + '</b> — not available here. ' + _rEsc(u.why)
      +  '</div>';
  });

  // ---- per product ------------------------------------------------------
  const rows = (d.asins || []).slice().sort(function(a,b){
    const k = RET.sort;
    const av = a[k], bv = b[k];
    if(av === null || av === undefined) return 1;
    if(bv === null || bv === undefined) return -1;
    return (typeof av === "string") ? String(av).localeCompare(String(bv)) : (bv - av);
  });
  if(rows.length){
    h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:860px">'
      +  '<thead><tr>'
      +  [["name","Product"],["returns","Returns"],["ordered","Sold"],
          ["rate","Return rate"],["refunded","Refunded"],["natures","Mostly because"]]
         .map(function(c){
           return '<th style="text-align:left;font-size:10.5px;padding:6px 8px;'
                + 'cursor:pointer;white-space:nowrap" onclick="returnsSort('
                + jsArg(c[0]) + ')">' + _rEsc(c[1])
                + (RET.sort===c[0] ? ' ▾' : '') + '</th>'; }).join("")
      +  '</tr></thead><tbody>';
    rows.forEach(function(r){
      const top = Object.keys(r.natures||{}).sort((a,b)=>r.natures[b]-r.natures[a])[0];
      h += '<tr>'
        +  '<td style="padding:6px 8px;font-size:11.5px;max-width:320px">'
        +  '<div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '
        +  'title="'+_rEsc(r.name||"")+'">' + _rEsc(r.name || "(no title)") + '</div>'
        +  '<code class="cc" style="font-size:10px">' + _rEsc(r.asin||"")
        +  (r.sku ? ' · ' + _rEsc(r.sku) : '') + '</code></td>'
        +  '<td style="padding:6px 8px;font-size:11.5px">' + r.returns + '</td>'
        +  '<td style="padding:6px 8px;font-size:11.5px">'
        +  (r.ordered ? r.ordered : '<span class="cc">—</span>') + '</td>'
        // Red above 5%: the point at which a return rate stops being noise.
        +  '<td style="padding:6px 8px;font-size:11.5px'
        +  (r.rate !== null && r.rate > 5 ? ';color:var(--red);font-weight:600' : '')
        +  '">' + _rPct(r.rate) + '</td>'
        +  '<td style="padding:6px 8px;font-size:11.5px">' + _rMoney(r.refunded) + '</td>'
        +  '<td style="padding:6px 8px;font-size:11px">'
        +  (top ? '<span style="color:' + (RET_NATURE_COLOUR[top]||"inherit") + '">'
                  + _rEsc(top) + '</span>' : '<span class="cc">—</span>')
        +  '</td></tr>';
    });
    h += '</tbody></table></div>';
  }else{
    h += '<div class="cc" style="padding:20px;border:1px dashed #2a3446;border-radius:6px">'
      +  'No returns in this period. For a returns report that is the right answer.'
      +  '</div>';
  }

  h += '<div class="cc" style="font-size:11px;margin-top:12px">Read as <b>'
    +  _rEsc(d.source === "fba" ? "FBA" : "seller-fulfilled") + '</b> data'
    +  (d.skipped ? ' · ' + d.skipped + ' row(s) had no ASIN or SKU and were skipped' : '')
    +  (d.start ? ' · ' + _rEsc(d.start) + ' → ' + _rEsc(d.end) : '') + '</div>';
  body.innerHTML = h;
}

function returnsSort(k){ RET.sort = k; returnsRender(); }
