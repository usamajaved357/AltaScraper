// static/js/sales_breakdown.js -- the Sales breakdown table (by ASIN, SKU, ...). Moved word for word out of sales.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

// ---- per-product breakdown ------------------------------------------------
// Which products the period was actually made of. The dashboard could filter TO
// one product but never showed them side by side, so "how did we do" could be
// answered and "what did it" could not.
let SALES_BD = {group: "asin", rows: [], sort: "revenue", desc: true};

function salesBdGroup(g){ SALES_BD.group = g; salesLoadBreakdown(); }
function salesBdSort(k){
  if(SALES_BD.sort === k) SALES_BD.desc = !SALES_BD.desc;
  else { SALES_BD.sort = k; SALES_BD.desc = true; }
  salesDrawBreakdown();
}

async function salesLoadBreakdown(){
  const host = document.getElementById("sales_breakdown");
  if(!host) return;
  host.innerHTML = '<div class="cc" style="padding:14px"><span class="genspin"></span> Loading products…</div>';
  // NEWEST ASK WINS: a period change or a group toggle while a slow reply is
  // out must not be overwritten by that older reply.
  const tk = SALES_BD.seq = (SALES_BD.seq || 0) + 1;
  try{
    const j = await _sFetch("/sales/breakdown?"+_sQuery()
                            +"&group="+encodeURIComponent(SALES_BD.group));
    if(j === null || tk !== SALES_BD.seq) return;
    if(!j || !j.ok){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'
      + _sEsc((j&&j.error)||"Could not load") + '</div>'; return; }
    SALES_BD.rows = j.rows || [];
    SALES_BD.meta = j;
    salesDrawBreakdown();
  }catch(e){
    if(tk !== SALES_BD.seq) return;
    host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sEsc(String(e))+'</div>';
  }
}

const _BD_COLS = [
  {k:"k",          t:"Product",    kind:"text"},
  {k:"units",      t:"Units",      kind:"int"},
  {k:"revenue",    t:"Revenue",    kind:"money"},
  {k:"avg_price",  t:"Avg price",  kind:"money"},
  {k:"orders",     t:"Orders",     kind:"int"},
  {k:"sessions",   t:"Sessions",   kind:"int"},
  {k:"conversion", t:"Conversion", kind:"pct"},
];

function salesDrawBreakdown(){
  const host = document.getElementById("sales_breakdown");
  const m = SALES_BD.meta || {};
  let h = '<div style="display:flex;align-items:center;gap:8px;margin:6px 0 8px">'
    + '<div style="font-size:12.5px;font-weight:600">By product</div>'
    + '<div class="mktswitch">'
    + '<button class="mktbtn'+(SALES_BD.group==="asin"?" on":"")+'" onclick="salesBdGroup(\'asin\')">Each ASIN</button>'
    + '<button class="mktbtn'+(SALES_BD.group==="parent"?" on":"")+'" onclick="salesBdGroup(\'parent\')">Grouped by parent</button>'
    + '</div>'
    + '<span class="cc" style="font-size:11px">'+(SALES_BD.rows.length)+' product'
    + (SALES_BD.rows.length===1?'':'s')
    + (SALES_BD.group==="parent" ? ' — variations of one product counted together' : '')
    + '</span></div>';

  if(!SALES_BD.rows.length){
    h += '<div class="cc" style="padding:14px;border:1px dashed var(--line2);border-radius:6px;font-size:12px">'
      + _sEsc(m.note || "Nothing yet.") + '</div>';
    host.innerHTML = h; return;
  }

  // HOW MUCH OF THE PERIOD THIS TABLE IS ACTUALLY SHOWING.
  //
  // Measured 21 Aug 2026 over thirty days: Nestwell's headline was £946.67 and
  // these rows came to £149.95 -- a sixth of the business -- and Selvora's
  // headline was £4,145.60 against no rows at all. Not a fault: two feeds fill
  // sales_daily. The ORDER feed writes a day's total as soon as the orders are
  // known; Amazon's Sales & Traffic REPORT is what carries the per-ASIN block,
  // and it has to be asked for one day at a time against a quota of roughly one
  // report a minute across six accounts and eleven marketplaces. So a day can
  // have a true total and no product detail yet.
  //
  // The defect was that the screen did not SAY so. A table headed "By product"
  // that silently omits most of the money answers "which products sold" with a
  // number nobody can act on.
  const cov = m.coverage || {};
  if(cov.uncovered > 0.01){
    const mny = function(v){
      return (typeof curMoney === "function")
        ? curMoney(v, m.currency || cov.currency || "")
        : String(v);
    };
    const d = cov.days_without_products || 0;
    h += '<div class="cc" style="padding:8px 10px;margin-bottom:8px;'
      +  'border:1px solid var(--warn-line);background:var(--warn-bg);border-radius:6px;'
      +  'font-size:11.5px;line-height:1.5">'
      +  '<i class="ti ti-alert-triangle" style="color:var(--gold)"></i> '
      +  'These products account for <b>' + _sEsc(mny(cov.covered)) + '</b> of the '
      +  '<b>' + _sEsc(mny(cov.total)) + '</b> sold in this period'
      +  (cov.pct !== null && cov.pct !== undefined
          ? ' (' + _sEsc(String(cov.pct)) + '%)' : '') + '. '
      +  'The other <b>' + _sEsc(mny(cov.uncovered)) + '</b> is on '
      +  d + ' day' + (d === 1 ? '' : 's')
      +  ' Amazon has not yet sent a product-level report for, so it cannot be '
      +  'put against a product. The totals at the top of the screen include it. '
      +  'Sync fetches those days one at a time, against Amazon’s report quota.'
      +  '</div>';
  }

  const dir = SALES_BD.desc ? -1 : 1;
  const rows = SALES_BD.rows.slice().sort(function(a,b){
    let x=a[SALES_BD.sort], y=b[SALES_BD.sort];
    if(x===null||x===undefined) return 1;      // unknown is not "smallest"
    if(y===null||y===undefined) return -1;
    // Same direction as the numbers (the campaign table's fix, 30 Sep): the
    // Product column read Z-A under "▴" and A-Z under "▾".
    if(typeof x==="string") return dir*(x<y?-1:x>y?1:0);
    return dir*(x-y);
  });

  h += '<div style="overflow-x:auto"><table class="kv" style="width:100%;min-width:640px"><thead><tr>';
  _BD_COLS.forEach(function(c){
    h += '<th style="text-align:'+(c.kind==="text"?"left":"right")+';font-size:11px;'
      +  'cursor:pointer;white-space:nowrap;padding:6px 8px" onclick="salesBdSort('+jsArg(c.k)+')">'
      +  _sEsc(c.t) + (SALES_BD.sort===c.k ? (SALES_BD.desc?" ▾":" ▴") : "") + '</th>';
  });
  h += '</tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr>';
    _BD_COLS.forEach(function(c){
      const v = r[c.k];
      let cell;
      if(c.kind==="text"){
        // THE PRODUCT, not just its code. This column was a bare ASIN, and
        // B0F9NQ6WZK tells nobody which product had the good month. The picture
        // and the name come with the row, from the same catalogue the Listings
        // cards and the Orders screen use.
        const pic = r.img
          ? '<img src="'+_sEsc(thumbUrl(r.img, 30))+'" loading="lazy" decoding="async" alt="" style="width:30px;'
            + 'height:30px;object-fit:contain;background:var(--sidebar);border-radius:5px;'
            + 'flex:0 0 30px">'
          : '<span style="width:30px;height:30px;border-radius:5px;background:var(--sidebar);'
            + 'display:inline-flex;align-items:center;justify-content:center;'
            + 'flex:0 0 30px"><i class="ti ti-photo" style="opacity:.4"></i></span>';
        cell = '<div style="display:flex;gap:8px;align-items:center">' + pic
             + '<span style="min-width:0">'
             + (r.title
                 ? '<span style="display:block;font-size:11.5px;overflow:hidden;'
                   + 'text-overflow:ellipsis;white-space:nowrap;max-width:280px" '
                   + 'title="'+_sEsc(r.title)+'">'+_sEsc(r.title)+'</span>'
                 : '')
             + '<a href="'+_sEsc(_dpUrl(r.k))+'" target="_blank" rel="noopener" '
             + 'onclick="event.stopPropagation()" '
             + 'style="font-size:'+(r.title?'10px':'11.5px')+'" '
             + 'title="Open on Amazon">'+_sEsc(r.k)+'</a>'
             + (SALES_BD.group==="parent" && (r.children||0) > 1
                 ? '<span class="cc" style="font-size:10px;margin-left:6px">'
                   + r.children+' variations</span>' : '')
             + '</span></div>';
      } else if(v===null||v===undefined){ cell = '<span class="cc">—</span>'; }
      else if(c.kind==="money") cell = Number(v).toFixed(2);
      else if(c.kind==="pct")   cell = Number(v).toFixed(2)+"%";
      else cell = String(Math.round(v));
      h += '<td style="text-align:'+(c.kind==="text"?"left":"right")+';white-space:nowrap;'
        +  'padding:5px 8px">'+cell+'</td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  host.innerHTML = h;
}
