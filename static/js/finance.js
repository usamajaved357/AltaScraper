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

let FIN = {rows: [], totals: {}, sort: "revenue", desc: true,
           preset: "30d", filter: "all"};

// The window, as periods people actually ask for. The date boxes stayed EMPTY
// while the screen quietly showed the last thirty days, so the one thing a
// money screen must be unambiguous about -- which days it is counting -- was
// the one thing it never said. Picking a preset fills the boxes, and typing in
// the boxes clears the preset, so the two can never disagree.
const FIN_PRESETS = [
  {k: "7d",  t: "7 days",       days: 7},
  {k: "30d", t: "30 days",      days: 30},
  {k: "90d", t: "90 days",      days: 90},
  {k: "mtd", t: "This month",   month: true},
  {k: "qtd", t: "This quarter", quarter: true},
];

const FIN_FILTERS = [
  {k: "all",    t: "All"},
  {k: "profit", t: "Profitable"},
  {k: "loss",   t: "Loss-making"},
  {k: "blank",  t: "No contribution"},
];

function _finIso(d){ return d.toISOString().slice(0, 10); }

function financePreset(k){
  FIN.preset = k || "";
  if(k){
    const p = FIN_PRESETS.filter(x => x.k === k)[0];
    if(p){
      const end = new Date(), start = new Date();
      if(p.month){ start.setDate(1); }
      else if(p.quarter){ start.setMonth(Math.floor(start.getMonth() / 3) * 3, 1); }
      else { start.setDate(start.getDate() - (p.days - 1)); }
      const a = document.getElementById("fin_start"), b = document.getElementById("fin_end");
      if(a) a.value = _finIso(start);
      if(b) b.value = _finIso(end);
    }
  }
  financeLoad();
}

function financeFilter(k){ FIN.filter = k; financeRender(); }

function _finChips(){
  const p = document.getElementById("fin_presets");
  if(p){
    p.innerHTML = FIN_PRESETS.map(function(x){
      return '<button class="db-chip'+(FIN.preset===x.k?" on":"")+'" '
           + 'onclick="financePreset('+jsArg(x.k)+')">'+_fesc(x.t)+'</button>';
    }).join("");
  }
  const f = document.getElementById("fin_filters");
  if(f){
    // Each filter carries its own count, so choosing one is never a guess about
    // whether it will show anything.
    f.innerHTML = FIN_FILTERS.map(function(x){
      const n = _finMatching(x.k).length;
      return '<button class="db-chip'+(FIN.filter===x.k?" on":"")+'"'
           + (n ? "" : ' style="opacity:.45"')
           + ' onclick="financeFilter('+jsArg(x.k)+')">'+_fesc(x.t)+' '+n+'</button>';
    }).join("");
  }
}

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

// Opens on the preset it was already silently using, with the dates FILLED IN
// rather than left blank for the reader to wonder about.
function financeOnOpen(){ financePreset(FIN.preset || "30d"); }

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

// A product with NO contribution is its own answer, not a loss and not a
// profit. Lumping it in with either would be the quiet lie on this screen:
// "loss-making" would fill up with products whose cost simply is not known.
function _finMatching(f){
  return FIN.rows.filter(function(r){
    const c = r.contribution;
    if(f === "profit") return c !== null && c !== undefined && c > 0;
    if(f === "loss")   return c !== null && c !== undefined && c <= 0;
    if(f === "blank")  return c === null || c === undefined;
    return true;
  });
}

// Children rolled into their parent. Money adds up; margin does NOT -- it is
// recomputed from the rolled-up parts, because averaging percentages weights a
// product that sold twice the same as one that sold two hundred times. And a
// parent containing ONE product whose contribution is unknown reports no
// contribution for the whole family, exactly as a single product does: a
// partial total only ever flatters.
function _finRollup(rows){
  const out = {}, order = [];
  rows.forEach(function(r){
    const key = r.parent_asin || r.asin;
    if(!out[key]){
      out[key] = {asin: key, title: r.title || "", parent_asin: "", _n: 0,
                  units: 0, revenue: 0, vat: 0, fees: 0, cogs: 0, refunds: 0,
                  ad_spend: null, uncosted_units: 0, contribution: 0,
                  _blank: false, _isGroup: false};
      order.push(key);
    }
    const g = out[key];
    g._n++;
    if(r.parent_asin) g._isGroup = true;
    ["units", "revenue", "vat", "fees", "cogs", "refunds", "uncosted_units"]
      .forEach(function(k){ g[k] += Number(r[k] || 0); });
    if(r.ad_spend !== null && r.ad_spend !== undefined){
      g.ad_spend = Number(g.ad_spend || 0) + Number(r.ad_spend);
    }
    if(r.contribution === null || r.contribution === undefined) g._blank = true;
    else g.contribution += Number(r.contribution);
    if(!g.title && r.title) g.title = r.title;
  });
  return order.map(function(k){
    const g = out[k];
    if(g._blank) g.contribution = null;
    g.margin_pct = (g.contribution !== null && g.revenue)
                 ? Number((g.contribution / g.revenue * 100).toFixed(2)) : null;
    if(g._isGroup) g.title = (g.title || "") + " (" + g._n + " children)";
    return g;
  });
}

function _finVisible(){
  let rows = _finMatching(FIN.filter);
  const box = document.getElementById("fin_by_parent");
  if(box && box.checked) rows = _finRollup(rows);
  return rows;
}

function _finSorted(){
  const k = FIN.sort, dir = FIN.desc ? -1 : 1;
  return _finVisible().slice().sort(function(a, b){
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

// Totals for whatever is on screen. NOT the server's whole-period totals: with
// a filter on, showing those under a filtered table invites reading the two as
// the same thing, and "Loss-making" with a healthy total underneath it is the
// most misleading arrangement this screen could produce. Contribution is
// withheld if ANY visible row withholds it -- the same rule one product follows.
function _finTotals(rows){
  const t = {products: rows.length, units: 0, revenue: 0, vat: 0, fees: 0,
             cogs: 0, refunds: 0, ad_spend: null, contribution: 0};
  let blank = false, anyAds = false;
  rows.forEach(function(r){
    ["units", "revenue", "vat", "fees", "cogs", "refunds"].forEach(function(k){
      t[k] += Number(r[k] || 0);
    });
    if(r.ad_spend !== null && r.ad_spend !== undefined){
      anyAds = true; t.ad_spend = Number(t.ad_spend || 0) + Number(r.ad_spend);
    }
    if(r.contribution === null || r.contribution === undefined) blank = true;
    else t.contribution += Number(r.contribution);
  });
  if(!anyAds) t.ad_spend = null;
  if(blank) t.contribution = null;
  t.margin_pct = (t.contribution !== null && t.revenue)
               ? Number((t.contribution / t.revenue * 100).toFixed(2)) : null;
  ["revenue", "vat", "fees", "cogs", "refunds"].forEach(function(k){
    t[k] = Number(t[k].toFixed(2));
  });
  if(t.contribution !== null) t.contribution = Number(t.contribution.toFixed(2));
  return t;
}

function financeRender(){
  const body = document.getElementById("finbody");
  _finChips();
  const visible = _finVisible();
  const t = _finTotals(visible), cur = (FIN.meta && FIN.meta.currency) || "";
  let h = "";

  // Which days this screen is counting, said out loud. It defaulted to the last
  // thirty while the date boxes sat empty, so the number on screen belonged to a
  // period nobody had been told about.
  if(FIN.meta && FIN.meta.start){
    h += '<div class="cc" style="font-size:11.5px;margin:0 0 8px">'
      +  'Money that moved between <b>'+_fesc(FIN.meta.start)+'</b> and <b>'
      +  _fesc(FIN.meta.end)+'</b>'
      +  (FIN.filter !== "all"
          ? ' — showing <b>'+_fesc((FIN_FILTERS.filter(x=>x.k===FIN.filter)[0]||{}).t)
            +'</b> only, and the totals below are for those '+visible.length
            +' row'+(visible.length===1?'':'s')+', not the whole period.'
          : '.')
      +  '</div>';
  }

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
  if(!visible.length){
    // The period HAS products; this filter has none. Two different facts, and
    // the empty-period wording above would have said the wrong one.
    h += '<div class="cc" style="padding:20px;border:1px dashed #2a3446;border-radius:6px">'
      +  'None of the '+FIN.rows.length+' products in this period are '
      +  _fesc(((FIN_FILTERS.filter(x=>x.k===FIN.filter)[0])||{}).t||"").toLowerCase()
      +  '. Pick <b>All</b> to see them.</div>';
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
        // The product, not just its code. An ASIN alone is unreadable, and a
        // table of unreadable identifiers is one nobody checks.
        cell = r.title
          ? '<div style="max-width:290px"><div style="font-size:11.5px;'
            + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'
            + _fesc(r.title)+'">'+_fesc(r.title)+'</div>'
            + '<code class="cc" style="font-size:10px">'+_fesc(v)+'</code></div>'
          : '<code style="font-size:11.5px">'+_fesc(v)+'</code>';
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
