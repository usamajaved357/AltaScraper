// ===================== FINANCE: CONTRIBUTION PER PRODUCT =====================
// What each product actually left behind, after Amazon's fees, refunds and what
// the stock cost.
//
// Two things on this screen are deliberately NOT numbers:
//   * Ad spend reads "not connected" rather than 0.00. Nothing writes to
//     ads_daily yet, and a zero would inflate every advertised product's
//     contribution by exactly what you are spending on it — convincingly.
//   * A product with any uncosted unit shows no contribution at all, because a
//     partial cost only ever makes a product look better than it is.
// Both are stated on screen rather than left for the reader to notice.

let FIN = {rows: [], totals: {}, sort: "revenue", desc: true};

function _fesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _fmoney(v, cur){
  if(v===null || v===undefined || v==="") return '<span class="cc">—</span>';
  const n = Number(v);
  return (n<0 ? "−" : "") + (cur ? cur+" " : "") + Math.abs(n).toFixed(2);
}
function _fpct(v){
  return (v===null||v===undefined||v==="") ? '<span class="cc">—</span>'
                                           : Number(v).toFixed(1)+"%";
}

function financeOnOpen(){ financeLoad(); }

async function financeLoad(){
  const body = document.getElementById("finbody");
  if(!body) return;
  body.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading…</div>';
  const qs = [];
  const s = (document.getElementById("fin_start")||{}).value;
  const e = (document.getElementById("fin_end")||{}).value;
  if(s && e){ qs.push("start="+encodeURIComponent(s), "end="+encodeURIComponent(e)); }
  let j;
  try{ j = await (await fetch("/finance/contribution"+(qs.length?"?"+qs.join("&"):""))).json(); }
  catch(err){ body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">Could not load: '+_fesc(String(err))+'</div>'; return; }
  if(!j || !j.ok){
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_fesc((j&&j.error)||"Could not load")+'</div>';
    return;
  }
  FIN.rows = j.rows || [];
  FIN.totals = j.totals || {};
  FIN.meta = j;
  financeRender();
}

function financeSort(key){
  if(FIN.sort === key){ FIN.desc = !FIN.desc; } else { FIN.sort = key; FIN.desc = true; }
  financeRender();
}

function _finSorted(){
  const k = FIN.sort, dir = FIN.desc ? -1 : 1;
  return FIN.rows.slice().sort(function(a, b){
    let x = a[k], y = b[k];
    // Blanks sort to the bottom whichever way the column is pointing: a withheld
    // contribution is not "the smallest", it is "not known".
    if(x===null||x===undefined) return 1;
    if(y===null||y===undefined) return -1;
    if(typeof x === "string") return dir * (x < y ? 1 : x > y ? -1 : 0);
    return dir * (x - y);
  });
}

const FIN_COLS = [
  {k:"asin",         t:"Product",       kind:"text"},
  {k:"units",        t:"Units",         kind:"int",   tip:"Units SHIPPED — the same basis as the fees and refunds beside them"},
  {k:"revenue",      t:"Revenue",       kind:"money", tip:"Charged to buyers, from Amazon's finance records"},
  {k:"vat",          t:"VAT",           kind:"money", tip:"Collected from the buyer and owed onward — never yours"},
  {k:"ad_spend",     t:"Ad spend",      kind:"money", tip:"Not connected yet"},
  {k:"fees",         t:"Amazon fees",   kind:"money", tip:"Referral + FBA + other"},
  {k:"cogs",         t:"COGS",          kind:"money", tip:"What the units cost, from the cost written into each SKU"},
  {k:"refunds",      t:"Refunds",       kind:"money"},
  {k:"contribution", t:"Contribution",  kind:"money", tip:"Revenue − fees − refunds + reimbursements − COGS. Before advertising."},
  {k:"margin_pct",   t:"Margin",        kind:"pct"},
];

function financeRender(){
  const body = document.getElementById("finbody");
  const t = FIN.totals || {}, cur = (FIN.meta && FIN.meta.currency) || "";
  let h = "";

  ((FIN.meta && FIN.meta.notes) || []).forEach(function(n){
    h += '<div class="cc" style="font-size:12px;margin:2px 0 10px;padding:9px 11px;'
      +  'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
      +  '<i class="ti ti-info-circle"></i> '+_fesc(n)+'</div>';
  });

  if(!FIN.rows.length){
    h += '<div class="cc" style="padding:20px;border:1px dashed #2a3446;border-radius:6px">'
      +  'Nothing in this period yet. Finance data is pulled per day — press '
      +  '<b>Sync</b> on the Sales screen and come back.</div>';
    body.innerHTML = h; return;
  }

  h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:820px">'
    +  '<thead><tr>';
  FIN_COLS.forEach(function(c){
    const on = (FIN.sort === c.k);
    h += '<th style="text-align:'+(c.kind==="text"?"left":"right")+';font-size:11px;'
      +  'cursor:pointer;white-space:nowrap;padding:6px 8px"'
      +  (c.tip ? ' title="'+_fesc(c.tip)+'"' : '')
      +  ' onclick="financeSort('+jsArg(c.k)+')">'
      +  _fesc(c.t) + (on ? (FIN.desc ? " ▾" : " ▴") : "") + '</th>';
  });
  h += '</tr></thead><tbody>';

  _finSorted().forEach(function(r){
    h += '<tr>';
    FIN_COLS.forEach(function(c){
      const v = r[c.k];
      let cell;
      if(c.kind === "text"){
        cell = '<code style="font-size:11.5px">'+_fesc(v)+'</code>';
        if(r.uncosted_units){
          cell += '<span class="cc" style="font-size:10px;color:var(--warn);margin-left:6px" '
                + 'title="These units have no cost recorded, so no contribution is shown">'
                + r.uncosted_units+' uncosted</span>';
        }
      } else if(c.kind === "int"){
        cell = (v===null||v===undefined) ? '<span class="cc">—</span>' : String(v);
      } else if(c.kind === "pct"){
        cell = _fpct(v);
      } else {
        cell = _fmoney(v, "");
        if(c.k === "ad_spend" && (v===null||v===undefined)){
          cell = '<span class="cc" title="No ad data in the app yet">not connected</span>';
        }
      }
      const strong = (c.k === "contribution") ? "font-weight:600;" : "";
      h += '<td style="text-align:'+(c.kind==="text"?"left":"right")+';'+strong
        +  'white-space:nowrap;padding:5px 8px">'+cell+'</td>';
    });
    h += '</tr>';
  });

  h += '</tbody><tfoot><tr style="border-top:2px solid #26303f;font-weight:600">';
  FIN_COLS.forEach(function(c){
    let cell;
    if(c.kind === "text") cell = t.products + " product" + (t.products===1?"":"s");
    else if(c.kind === "int") cell = String(t[c.k] || 0);
    else if(c.kind === "pct") cell = _fpct(t[c.k]);
    else if(c.k === "ad_spend" && t.ad_spend===null) cell = '<span class="cc">—</span>';
    else cell = _fmoney(t[c.k], "");
    h += '<td style="text-align:'+(c.kind==="text"?"left":"right")+';padding:7px 8px">'
      +  cell+'</td>';
  });
  h += '</tr></tfoot></table></div>';

  h += '<div class="cc" style="font-size:11px;margin-top:10px">'
    +  'Totals are recomputed from the parts, not summed from the column above — '
    +  'summing would quietly drop every product whose contribution is withheld '
    +  'and present the remainder as the whole.'
    +  (cur ? ' Amounts in '+_fesc(cur)+'.' : '')
    +  '</div>';

  body.innerHTML = h;
}
