/* static/js/brandview.js -- one account, every marketplace, side by side.
 *
 * WHY THIS EXISTS
 * The sidebar has offered "All marketplaces" all along, and every screen threw
 * it away. scopeq.js drops the parameter; the routes that do receive it turn it
 * into the account's default. Measured 21 Aug 2026 in a browser: with "All
 * marketplaces" showing in the sidebar, the Sales screen said "United Kingdom
 * Time", drew a week-to-date chart in pounds, and made no new request at all
 * after the switch. Jack Reacherd sells in ten marketplaces; the screen showed
 * one of them under a heading that said all.
 *
 * NO TOTAL ACROSS CURRENCIES
 *     "keep grouping by currency, don't sum across them"   -- the owner, 20 Aug
 * A subtotal per currency, and nothing that adds pounds to euros. That needs a
 * rate and a date, and a single number hiding both is worse than none: it is
 * one nobody can check.
 *
 * QUIET MARKETPLACES ARE FOLDED AWAY, NOT DROPPED
 * Ten rows of zeros is not a report. They collapse into one line that says how
 * many and opens on a click -- "are we selling in Poland yet" is a real
 * question, and a missing row would answer it wrongly.
 */

let BRANDV = {rows: [], meta: null, showQuiet: false, loading: false};

function _bvEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function _bvMoney(v, cur){
  if(v === null || v === undefined) return '<span class="cc">—</span>';
  if(typeof curMoney === "function") return _bvEsc(curMoney(v, cur || ""));
  return _bvEsc((cur ? cur + " " : "") + Number(v).toFixed(2));
}

function _bvNum(v){
  if(v === null || v === undefined) return '<span class="cc">—</span>';
  return _bvEsc(Number(v).toLocaleString());
}

/* The change against the same window immediately before. Shown only when there
 * IS a previous figure: "+100%" against nothing is not a rise, it is a first
 * sale, and the two read very differently. */
function _bvDelta(now, was){
  if(now === null || now === undefined) return "";
  if(was === null || was === undefined || !Number(was)) return "";
  const pct = ((Number(now) - Number(was)) / Math.abs(Number(was))) * 100;
  if(!isFinite(pct)) return "";
  const up = pct >= 0;
  return '<span class="bvdelta ' + (up ? "up" : "down") + '">'
       + (up ? "▲" : "▼") + " " + Math.abs(pct).toFixed(0) + "%</span>";
}

function _bvQuiet(r){
  return !Number(r.ordered_sales) && !Number(r.units) && !Number(r.orders);
}

async function brandviewLoad(){
  const host = document.getElementById("brandview");
  if(!host) return;
  if(BRANDV.loading) return;
  BRANDV.loading = true;
  host.innerHTML = '<div class="cc" style="padding:16px">'
    + '<span class="genspin"></span> Reading every marketplace…</div>';
  try{
    const qs = (typeof scopeQs === "function") ? scopeQs({days: 30})
      : ("?days=30" + (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT
          ? "&id=" + encodeURIComponent(CUR_ACCOUNT.id) : ""));
    const j = await (await fetch("/brand/marketplaces" + qs)).json();
    if(!j || !j.ok){
      host.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
        + _bvEsc((j && j.error) || "Could not load") + '</div>';
      return;
    }
    BRANDV.rows = j.rows || [];
    BRANDV.meta = j;
    brandviewDraw();
  }catch(e){
    host.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
      + _bvEsc(String(e)) + '</div>';
  }finally{
    BRANDV.loading = false;
  }
}

function brandviewToggleQuiet(){
  BRANDV.showQuiet = !BRANDV.showQuiet;
  brandviewDraw();
}

function brandviewDraw(){
  const host = document.getElementById("brandview");
  const m = BRANDV.meta;
  if(!host || !m) return;
  const live = BRANDV.rows.filter(function(r){ return !r.error && !_bvQuiet(r); });
  const quiet = BRANDV.rows.filter(function(r){ return !r.error && _bvQuiet(r); });
  const bad = BRANDV.rows.filter(function(r){ return !!r.error; });

  let h = '<div class="bvhead">'
    + '<div><h3 style="margin:0;font-size:15px">' + _bvEsc(m.account_label)
    + ' — every marketplace</h3>'
    + '<div class="cc" style="font-size:11.5px;margin-top:2px">'
    + _bvEsc(m.start) + ' to ' + _bvEsc(m.end)
    + ' · compared with ' + _bvEsc(m.prev_start) + ' to ' + _bvEsc(m.prev_end)
    + '</div></div></div>';

  // The subtotals, one per currency, and nothing that adds them together.
  if((m.by_currency || []).length){
    h += '<div class="bvcurs">';
    (m.by_currency || []).forEach(function(b){
      h += '<div class="bvcur">'
        + '<div class="bvcurhd">' + _bvEsc(b.currency)
        + '<span class="cc"> · ' + b.marketplaces + ' marketplace'
        + (b.marketplaces === 1 ? '' : 's') + '</span></div>'
        + '<div class="bvcurbig">' + _bvMoney(b.ordered_sales, b.currency)
        + ' ' + _bvDelta(b.ordered_sales, b.prev_ordered_sales) + '</div>'
        + '<div class="cc bvcursub">' + _bvNum(b.units) + ' units · '
        + _bvNum(b.orders) + ' orders · profit '
        + (b.profit_complete ? _bvMoney(b.profit, b.currency)
            : '<span class="cc" title="One of these marketplaces has a product '
              + 'with no cost recorded, so a subtotal would understate what it '
              + 'cost and overstate what was made.">not all costed</span>')
        + '</div></div>';
    });
    h += '</div>';
  }

  h += '<div class="cc bvnote">' + _bvEsc(m.note) + '</div>';

  if(live.length){
    h += '<div style="overflow-x:auto"><table class="kv bvtable">'
      + '<thead><tr>'
      + '<th style="text-align:left">Marketplace</th>'
      + '<th>Revenue</th><th>Units</th><th>Orders</th>'
      + '<th>Amazon fees</th><th>Stock cost</th><th>Profit</th><th>Margin</th>'
      + '</tr></thead><tbody>';
    live.forEach(function(r){
      const nm = (typeof mktName === "function") ? mktName(r.marketplace) : r.marketplace;
      const fl = (typeof mktFlag === "function") ? mktFlag(r.marketplace) : "";
      h += '<tr>'
        + '<td style="text-align:left"><span class="bvflag">' + fl + '</span> '
        + _bvEsc(nm) + ' <span class="cc">' + _bvEsc(r.currency || "") + '</span></td>'
        + '<td>' + _bvMoney(r.ordered_sales, r.currency) + ' '
        + _bvDelta(r.ordered_sales, r.prev_ordered_sales) + '</td>'
        + '<td>' + _bvNum(r.units) + '</td>'
        + '<td>' + _bvNum(r.orders) + '</td>'
        + '<td>' + _bvMoney(r.total_fees, r.currency) + '</td>'
        + '<td>' + _bvMoney(r.cogs, r.currency) + '</td>'
        + '<td>' + _bvMoney(r.profit, r.currency) + '</td>'
        + '<td>' + (r.margin_pct === null || r.margin_pct === undefined
            ? '<span class="cc">—</span>'
            : _bvEsc(Number(r.margin_pct).toFixed(1)) + '%') + '</td>'
        + '</tr>';
    });
    h += '</tbody></table></div>';
  }else{
    h += '<div class="cc bvempty">No marketplace has any sales in this period.'
      + ' Nothing here is missing — there is nothing to show.</div>';
  }

  // Quiet ones, folded. "Are we selling in Poland yet" is a real question and a
  // missing row would answer it wrongly.
  if(quiet.length){
    h += '<button class="bvmore" onclick="brandviewToggleQuiet()">'
      + '<i class="ti ti-chevron-' + (BRANDV.showQuiet ? "down" : "right") + '"></i> '
      + quiet.length + ' marketplace' + (quiet.length === 1 ? '' : 's')
      + ' with no sales in this period</button>';
    if(BRANDV.showQuiet){
      h += '<div class="bvquiet">' + quiet.map(function(r){
        const nm = (typeof mktName === "function") ? mktName(r.marketplace) : r.marketplace;
        const fl = (typeof mktFlag === "function") ? mktFlag(r.marketplace) : "";
        return '<span class="bvchip">' + fl + ' ' + _bvEsc(nm) + '</span>';
      }).join("") + '</div>';
    }
  }
  if(bad.length){
    h += '<div class="cc bvnote" style="color:var(--warn)">'
      + bad.length + ' marketplace' + (bad.length === 1 ? '' : 's')
      + ' could not be read: '
      + bad.map(function(r){ return _bvEsc(r.marketplace); }).join(", ")
      + '</div>';
  }
  h += '<div class="cc bvnote">' + _bvEsc(m.source) + '</div>';
  host.innerHTML = h;
}
