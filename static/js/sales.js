/* sales.js — the Sales dashboard.
 *
 * FOUR STAT CARDS, then a metrics × dates grid.
 *
 * TWO RULES THIS SCREEN IS BUILT ON
 *
 * 1. No data is not zero. Amazon delivers sales with a lag and never has today,
 *    so a day it has not sent shows an em-dash, not a 0. A zero is a claim that
 *    you sold nothing, and making that claim wrongly is worse than saying
 *    nothing at all. The same applies to Ad Spend: the Advertising API is not
 *    connected, so that card says so rather than showing £0.
 *
 * 2. Colour never carries a value on its own. Every cell in the grid prints its
 *    number; the tint only shades it against that metric's own range. So the
 *    grid IS the accessible table view — there is no second view to keep in
 *    step, and nothing is lost to colour blindness or a black-and-white print.
 *
 * The shading is ONE hue (the app's teal), light→dark, per row. A rainbow would
 * imply categories where there is only magnitude, and shading across rows would
 * compare sessions against revenue, which means nothing.
 */

let SALES = {preset:"30d", gran:"day", asin:"", start:"", end:"",
             data:null, series:null, busy:false};

const SALES_PRESETS = [["7d","7d"],["14d","14d"],["30d","30d"],
                       ["60d","60d"],["90d","90d"],["ytd","YTD"],["custom","Custom"]];
const SALES_GRAN = [["day","Day"],["week","Week"],["month","Month"]];

function _sEsc(s){
  return String(s==null?"":s).replace(/[&<>"]/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});
}

/* ---- formatting -------------------------------------------------------- */
/* An em-dash for "we do not know", never 0. */
function _sNum(v, kind, cur){
  if(v===null || v===undefined || v==="") return "—";
  const n = Number(v);
  if(!isFinite(n)) return "—";
  if(kind==="money"){
    const sym = _sCur(cur);
    return sym + n.toLocaleString(undefined,{minimumFractionDigits:2, maximumFractionDigits:2});
  }
  if(kind==="pct") return n.toFixed(2) + "%";
  return n.toLocaleString();
}
function _sCur(c){
  return ({GBP:"£", USD:"$", EUR:"€", CAD:"$", AUD:"$", JPY:"¥"})[String(c||"").toUpperCase()] || "";
}
/* Compact form for the big card figures: 12.4k reads faster than 12,431 and the
   exact number is one hover away in the grid below. */
function _sShort(v, kind, cur){
  if(v===null||v===undefined) return "—";
  const n=Number(v); if(!isFinite(n)) return "—";
  const sym = kind==="money" ? _sCur(cur) : "";
  // A margin is a percentage and belongs to one decimal: rounding 20.4% to
  // "20" throws away the difference between a healthy month and a thin one,
  // and shortening it to "20k" would be nonsense.
  if(kind==="pct") return n.toFixed(1)+"%";
  const a=Math.abs(n);
  if(a>=1e6) return sym+(n/1e6).toFixed(1)+"m";
  if(a>=1e4) return sym+(n/1e3).toFixed(1)+"k";
  if(kind==="money") return sym+n.toLocaleString(undefined,{maximumFractionDigits:0});
  return sym+n.toLocaleString();
}

/* ---- the filter row (one row, above everything it scopes) -------------- */
function salesDrawFilters(){
  const p=document.getElementById("sales_presets");
  if(p) p.innerHTML = SALES_PRESETS.map(function(x){
    return '<button class="mktbtn'+(SALES.preset===x[0]?" on":"")+'" '
         + 'onclick="salesSet(\'preset\',\''+x[0]+'\')">'+x[1]+'</button>';}).join("");
  const g=document.getElementById("sales_gran");
  if(g) g.innerHTML = SALES_GRAN.map(function(x){
    return '<button class="mktbtn'+(SALES.gran===x[0]?" on":"")+'" '
         + 'onclick="salesSet(\'gran\',\''+x[0]+'\')">'+x[1]+'</button>';}).join("");
  const c=document.getElementById("sales_custom");
  // inline-flex, not "": the element carries gap/align-items, which need a flex
  // container, and a bare span is not one.
  if(c) c.style.display = (SALES.preset==="custom") ? "inline-flex" : "none";
}
/* Custom shows two date boxes; it does not reload until both are filled, because
   half a range is not a range and asking for one would blank the screen. */
function salesSet(what, val){
  if(what==="preset") SALES.preset=val; else SALES.gran=val;
  salesDrawFilters();
  if(SALES.preset==="custom" && !(SALES.start && SALES.end)) return;
  salesReload();
}

function salesSetDates(){
  const s=document.getElementById("sales_start"), e=document.getElementById("sales_end");
  SALES.start = s ? s.value : "";
  SALES.end   = e ? e.value : "";
  if(SALES.start && SALES.end) salesReload();
}

/* DRAG ACROSS A CHART TO ZOOM INTO THOSE DAYS.
   Called by salescharts.js with two COLUMN positions; the dates that go with
   them are whatever the last draw used, which is why the columns are kept.

   A custom range already existed in the date boxes, but reading a shape off a
   chart and then translating it into two dates typed into two fields is the
   step nobody takes -- so the interesting week never got looked at closely.
   The previous range is remembered so there is a way back out. */
function salesZoomTo(i, j){
  const dates = (SALES._chartDates || []);
  const from = dates[Math.max(0, Math.min(i, j))];
  const to   = dates[Math.min(dates.length - 1, Math.max(i, j))];
  if(!from || !to) return;
  SALES._zoomBack = {preset: SALES.preset, start: SALES.start, end: SALES.end};
  SALES.preset = "custom"; SALES.start = from; SALES.end = to;
  const a = document.getElementById("sales_start"), b = document.getElementById("sales_end");
  if(a) a.value = from;
  if(b) b.value = to;
  salesReload();
}

function salesZoomOut(){
  const z = SALES._zoomBack;
  if(!z) return;
  SALES.preset = z.preset || "30d";
  SALES.start = z.start || ""; SALES.end = z.end || "";
  SALES._zoomBack = null;
  const a = document.getElementById("sales_start"), b = document.getElementById("sales_end");
  if(a) a.value = SALES.start;
  if(b) b.value = SALES.end;
  salesReload();
}

/* The product filter. Its own handler, because the select has to write its value
   into the state the query is built from -- an onchange that only calls reload
   re-requests the range it already had and the filter appears to do nothing. */
function salesSetAsin(v){
  SALES.asin = v || "";
  salesReload();
}

/* ---- loading ----------------------------------------------------------- */
function _sQuery(){
  const q=["preset="+encodeURIComponent(SALES.preset),
           "granularity="+encodeURIComponent(SALES.gran)];
  if(SALES.preset==="custom" && SALES.start && SALES.end){
    q.push("start="+encodeURIComponent(SALES.start));
    q.push("end="+encodeURIComponent(SALES.end));
  }
  if(SALES.asin) q.push("asin="+encodeURIComponent(SALES.asin));
  if(typeof WS_MARKET!=="undefined" && WS_MARKET && WS_MARKET!=="__all__")
    q.push("marketplace="+encodeURIComponent(WS_MARKET));
  return q.join("&");
}

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
  try{
    const j = await (await fetch("/sales/breakdown?"+_sQuery()
                                 +"&group="+encodeURIComponent(SALES_BD.group))).json();
    if(!j || !j.ok){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'
      + _sEsc((j&&j.error)||"Could not load") + '</div>'; return; }
    SALES_BD.rows = j.rows || [];
    SALES_BD.meta = j;
    salesDrawBreakdown();
  }catch(e){
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
    h += '<div class="cc" style="padding:14px;border:1px dashed #2a3446;border-radius:6px;font-size:12px">'
      + _sEsc(m.note || "Nothing yet.") + '</div>';
    host.innerHTML = h; return;
  }

  const dir = SALES_BD.desc ? -1 : 1;
  const rows = SALES_BD.rows.slice().sort(function(a,b){
    let x=a[SALES_BD.sort], y=b[SALES_BD.sort];
    if(x===null||x===undefined) return 1;      // unknown is not "smallest"
    if(y===null||y===undefined) return -1;
    if(typeof x==="string") return dir*(x<y?1:x>y?-1:0);
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
        cell = '<a href="'+_sEsc(_dpUrl(r.k))+'" target="_blank" rel="noopener" '
             + 'title="Open on Amazon">'+_sEsc(r.k)+'</a>';
        if(SALES_BD.group==="parent" && (r.children||0) > 1){
          cell += '<span class="cc" style="font-size:10px;margin-left:6px">'
                + r.children+' variations</span>';
        }
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

// The shape of the period, before the table of numbers.
//
// Four charts rather than one with four lines: they do not share a unit, and two
// series on one scale means the crossings look meaningful when they are an
// artefact of the axis. Each is drawn from the SAME series the grid below shows,
// so a shape and a number can never disagree.
function salesDrawCharts(ser){
  const host = document.getElementById("sales_charts");
  if(!host || typeof salesChart !== "function") return;
  // `columns` is the response's name for the buckets -- day, week or month
  // depending on the granularity picked, so the charts follow it automatically.
  const dates = (ser && ser.columns) || [];
  const rows  = (ser && ser.metrics) || [];
  if(!dates.length){ host.innerHTML = ""; return; }

  // Remembered so a drag on any chart can turn two column positions back into
  // two dates. The charts all share one set of columns, so any of them can zoom.
  SALES._chartDates = dates;

  const byKey = {};
  rows.forEach(function(m){ byKey[m.key] = m; });
  const pts = function(key){
    const m = byKey[key];
    if(!m) return null;
    // A cell Amazon has not delivered arrives as null and STAYS null all the way
    // to the chart, which draws a gap. Coercing it to 0 here is exactly how a
    // chart comes to say "sales collapsed" about a day that has not landed.
    return dates.map(function(d, i){ return {label: d, value: m.cells[i]}; });
  };

  // WHY EACH CHART HAS MORE THAN ONE SOURCE
  // Two different Amazon feeds describe the same trade. The Sales & Traffic
  // REPORT gives ordered_sales / units / conversion; the FINANCE records give
  // net_revenue / units_shipped / profit. They arrive separately and one can be
  // days behind the other -- measured on jack_uk: the finance records held nine
  // days of real sales (13.33 to 116.64) while the report had three days, all of
  // them zeroes, because the rest had not been backfilled past Amazon's
  // one-report-a-minute quota.
  //
  // The charts were pinned to the report columns, so three of the four drew a
  // confident flat line along the axis for an account that was selling. A flat
  // zero is not a neutral thing to draw: it reads as "sales collapsed", which is
  // worse than drawing nothing. So each chart names the series it would rather
  // have and falls back to the other feed, a series is only drawn if it has a
  // number that is not zero, and the chart says which feed it came from.
  const want = [
    {title: "Revenue", kind: "money", color: "#6ac7e8",
     keys: [["net_revenue", "finance records"], ["ordered_sales", "Sales & Traffic report"]]},
    {title: "Units", kind: "count", color: "#8fd694",
     keys: [["units_shipped", "finance records"], ["units", "Sales & Traffic report"]]},
    {title: "Profit", kind: "money", color: "#e8c66a",
     keys: [["profit", "finance records"]]},
    {title: "Margin", kind: "pct", color: "#c79ae8",
     keys: [["margin_pct", "finance records"]]},
    {title: "Conversion", kind: "pct", color: "#7fb2f0",
     keys: [["unit_session_pct", "Sales & Traffic report"]]},
  ];

  // Usable means: at least one real number, and not every one of them zero.
  // All-zero is what a feed that has not arrived looks like, and it is the one
  // shape a chart must never present as a fact.
  const usable = function(p){
    if(!p) return false;
    const real = p.filter(function(x){ return x.value !== null && x.value !== undefined; });
    return real.length > 0 && real.some(function(x){ return Number(x.value) !== 0; });
  };

  // A way OUT of a zoom, beside the charts rather than in a date box. Without
  // it the only route back is remembering what the range used to be.
  let h = "";
  if(SALES._zoomBack){
    h += '<div style="display:flex;align-items:center;gap:9px;margin:0 0 10px;'
      +  'padding:8px 11px;border:1px solid var(--accent);border-radius:7px;font-size:12px">'
      +  '<i class="ti ti-zoom-in"></i> Zoomed to <b>' + _sEsc(SALES.start)
      +  '</b> → <b>' + _sEsc(SALES.end) + '</b>'
      +  '<button class="db-chip" style="margin-left:auto" onclick="salesZoomOut()">'
      +  'Back to the full range</button></div>';
  }
  // TWO ACROSS, not three or four. At a third of the width a chart was a couple
  // of centimetres of squiggle -- too small to read a shape off, which is the
  // only reason to draw one.
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:16px">';
  let drew = 0;
  const skipped = [];
  want.forEach(function(w){
    let chosen = null, source = "", chosenAt = -1;
    for(let i = 0; i < w.keys.length; i++){
      const p = pts(w.keys[i][0]);
      if(usable(p)){ chosen = p; source = w.keys[i][1]; chosenAt = i; break; }
    }
    if(!chosen){
      // Present but empty is a different thing from absent, and only the first
      // is worth telling someone about.
      if(w.keys.some(function(k){ return pts(k[0]); })) skipped.push(w.title);
      return;
    }
    // EVERY other feed is checked, not just the ones ahead of the winner. The
    // disagreement is the point: if the finance records show sales for a period
    // and the report shows zero for the same period, that is worth knowing, and
    // stopping at the first usable series would never surface it.
    const disagrees = w.keys.filter(function(k, i){
      const p = pts(k[0]);
      return i !== chosenAt && p && !usable(p);
    }).map(function(k){ return k[1]; });
    drew++;
    // The same metric over the period before, if it arrived. Matched by KEY, so
    // a chart that fell back to the finance feed is compared against the
    // finance feed and not against a different measurement of the same trade.
    // MATCHED BY DATE, one entry per column of the chart being drawn.
    //
    // Not by position: the reply carries only the buckets that have figures, so
    // the two periods routinely come back with different numbers of columns.
    // Each column here looks up its own date minus the offset; a date the
    // earlier period has no figure for becomes null, which the chart draws as a
    // gap rather than as zero.
    let cmp = null;
    if(SALES.compare && SALES.compare.metrics && SALES.compareOffsetDays){
      const key = w.keys[chosenAt][0];
      const cm = SALES.compare.metrics.filter(function(m){ return m.key === key; })[0];
      if(cm && cm.cells){
        const was = {};
        (SALES.compare.columns || []).forEach(function(d, i){ was[d] = cm.cells[i]; });
        const off = SALES.compareOffsetDays * 86400000;
        cmp = chosen.map(function(pt){
          const d = new Date(String(pt.label) + "T00:00:00Z");
          if(isNaN(d)) return {label: "", value: null};
          const back = new Date(d.getTime() - off).toISOString().slice(0, 10);
          return {label: back,
                  value: (back in was) ? was[back] : null};
        });
        // Nothing lined up at all -- weekly or monthly buckets that the offset
        // does not land on. Better no second line than a line made of gaps.
        if(!cmp.some(function(p){ return p.value !== null && p.value !== undefined; })) cmp = null;
      }
    }
    h += salesChart(chosen, {
      title: w.title, kind: w.kind, color: w.color, compare: cmp,
      // Said on every chart, not only when it falls back: which of Amazon's two
      // feeds a number came from decides what it means, and the two disagree.
      subtitle: "from the " + source
        + (cmp && SALES.compareRange
             ? " · dashed line is " + SALES.compareRange : "")
        + (disagrees.length ? " — the " + _sEsc(disagrees.join(" and "))
                            + " shows zero for the same period, so it is not "
                            + "drawn" : "")});
  });
  h += '</div>';

  if(skipped.length){
    h += '<div class="cc" style="font-size:11.5px;margin-top:2px;padding:9px 11px;'
      +  'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
      +  '<i class="ti ti-info-circle"></i> Not drawn: ' + _sEsc(skipped.join(", "))
      +  ' — every value Amazon has sent for this period is zero. That is what a '
      +  'feed which has not arrived looks like, so it is left blank rather than '
      +  'charted as no sales. Press <b>Sync</b> to keep backfilling.</div>';
  }
  host.innerHTML = drew ? h : (skipped.length ? h : "");
}

async function salesReload(){
  if(SALES.busy) return;
  SALES.busy=true;
  // Hold the previous render at reduced opacity rather than flashing a skeleton
  // — no layout jump, and the numbers you were reading stay readable.
  const grid=document.getElementById("sales_grid");
  if(grid && grid.innerHTML.trim()) grid.style.opacity=".45";
  try{
    // AVAILABILITY FIRST. Ask what dates exist before asking for numbers, so a
    // period Amazon has not delivered is reported as such instead of drawn as a
    // wall of zeros.
    const av = await (await fetch("/sales/availability?"+_sQuery())).json();
    const [sum, ser] = await Promise.all([
      (await fetch("/sales/summary?"+_sQuery())).json(),
      (await fetch("/sales/series?"+_sQuery())).json()
    ]);
    SALES.data=sum; SALES.series=ser;
    // The period immediately before this one, for the comparison line. Fetched
    // separately and NOT awaited with the rest: the charts must not wait for
    // context to draw the thing the context is about. When it arrives the
    // charts redraw with it; if it fails they simply stay as they are.
    SALES.compare = null;
    salesLoadCompare(sum).catch(function(){});
    salesDrawCards(sum, av);
    salesDrawCharts(ser);
    salesDrawGrid(ser);
    salesDrawRange(sum, av);
    // After the numbers, not before: the options depend on the range, and the
    // grid is what someone is waiting for.
    salesFillAsins();
    salesLoadToday();
  }catch(e){
    const g=document.getElementById("sales_grid");
    if(g) g.innerHTML='<div class="empty">Could not load sales: '+_sEsc(String(e))+'</div>';
  }finally{
    if(grid) grid.style.opacity="";
    SALES.busy=false;
  }
}

/* ---- the period before this one ----------------------------------------
 * A line on its own says what happened. It cannot say whether that is good,
 * which is the question actually being asked -- and answering it meant
 * changing the dates and trying to remember the old shape. So the same span
 * immediately before is fetched and drawn behind, in grey dashes.
 *
 * Deliberately a SEPARATE request, not part of the load above: it is context.
 * If it is slow the charts are already up; if it fails there is simply no
 * second line, and nothing on the screen is wrong.
 */
async function salesLoadCompare(sum){
  if(!sum || !sum.ok || !sum.start || !sum.end) return;
  const start = new Date(sum.start + "T00:00:00Z");
  const end   = new Date(sum.end   + "T00:00:00Z");
  if(isNaN(start) || isNaN(end)) return;
  const days = Math.round((end - start) / 86400000) + 1;
  if(days < 2 || days > 400) return;             // nothing to compare against
  const prevEnd   = new Date(start.getTime() - 86400000);
  const prevStart = new Date(prevEnd.getTime() - (days - 1) * 86400000);
  const iso = d => d.toISOString().slice(0, 10);

  // The same query as the main series, with the dates replaced -- so the
  // product filter, the marketplace and the granularity all carry over. A
  // comparison drawn from a different filter would be a different product.
  const q = ["preset=custom",
             "start=" + iso(prevStart), "end=" + iso(prevEnd),
             "granularity=" + encodeURIComponent(SALES.gran)];
  if(SALES.asin) q.push("asin=" + encodeURIComponent(SALES.asin));
  if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
    q.push("marketplace=" + encodeURIComponent(WS_MARKET));

  const j = await (await fetch("/sales/series?" + q.join("&"))).json();
  if(!j || !j.ok || !(j.columns || []).length) return;
  SALES.compare = j;
  // The offset, in days, between a column here and the column it is compared
  // against. Kept because the two series are matched BY DATE, not by position:
  // measured on jack_uk, a 30-day request came back with 28 columns for this
  // period and 1 for the period before, because the reply carries only the
  // buckets that have figures. Pairing them by position would have compared
  // June 15th against July 15th; requiring equal lengths would have meant the
  // comparison never drew at all.
  SALES.compareOffsetDays = days;
  SALES.compareRange = iso(prevStart) + " to " + iso(prevEnd);
  salesDrawCharts(SALES.series);
}

function salesDrawRange(sum, av){
  const el=document.getElementById("sales_range");
  if(!el) return;
  if(!sum || !sum.ok){ el.textContent=""; return; }
  const a=(av&&av.sales)||{};
  let t = sum.start+" to "+sum.end;
  if(a.last_date) t += " · Amazon has data to "+a.last_date;
  el.textContent=t;
}

/* ---- today so far ------------------------------------------------------
 * Kept visually apart from the grid, because it is a DIFFERENT measurement:
 * orders counted as they are placed, not as Amazon finally settled them. It will
 * not tie out to the grid and is not meant to, so it says where it came from and
 * what it is being compared against.
 */
async function salesLoadToday(){
  const el=document.getElementById("sales_today");
  if(!el) return;
  try{
    const j=await (await fetch("/sales/today?"+_sQuery())).json();
    if(!j || !j.ok){ el.innerHTML=""; return; }
    const t=j.today||{}, y=j.yesterday||null, d=j.delta_pct||{};
    const cur=t.currency||"";
    function bit(label, v, kind, key){
      const dp=d[key];
      const arrow = (dp===null||dp===undefined) ? "" :
        ' <span class="'+(dp>=0?"good":"bad")+'">'+(dp>=0?"↑":"↓")+Math.abs(dp).toFixed(1)+'%</span>';
      return '<span class="todaybit"><b>'+_sEsc(_sNum(v,kind,cur))+'</b>'+arrow
           + ' <span class="cc">'+_sEsc(label)+'</span></span>';
    }
    let extra="";
    if(t.pending) extra += ' · '+t.pending+' pending (no value yet)';
    if(j.truncated) extra += ' · partial — very busy day';
    el.innerHTML = '<div class="todaystrip"><span class="todaylead">Today so far</span>'
      + bit("revenue", t.revenue, "money", "revenue")
      + bit("orders", t.orders, "count", "orders")
      + bit("units", t.units, "count", "units")
      + '<span class="cc todaynote">live from orders'
      + (y ? ' · vs '+_sEsc(j.compared_to||"the same time yesterday") : "")
      + _sEsc(extra) + '</span></div>';
  }catch(e){ el.innerHTML=""; }
}

/* ---- stat cards -------------------------------------------------------- */
function salesDrawCards(sum, av){
  const host=document.getElementById("sales_cards");
  const note=document.getElementById("sales_note");
  if(!host) return;
  if(!sum || !sum.ok){
    host.innerHTML="";
    if(note) note.innerHTML='<div class="empty">'+_sEsc((sum&&sum.error)||"No sales data")+'</div>';
    return;
  }
  host.innerHTML = (sum.cards||[]).map(function(c){
    const missing = (c.value===null||c.value===undefined);
    const adsOff = (c.key==="spend" && !sum.ads_connected);
    // PROFIT AND MARGIN READ AT A GLANCE. They are the two numbers the business
    // runs on, and a loss has to be obvious without reading the minus sign.
    const isProfit = (c.key==="profit" || c.key==="margin_pct");
    const neg = isProfit && Number(c.value) < 0;
    const col = missing ? "" :
      (neg ? ";color:var(--red)" :
       isProfit ? ";color:var(--ok,#8fd694)" : "");
    // LABEL FIRST, then the number, then the comparison -- Orbit's order,
    // measured: the label sits above the figure, not under it. Ours had it the
    // other way round and centred, which is why the two never looked alike
    // however close the colours got.
    return '<div class="stat-card'+(missing?" is-empty":"")+'"'
      + (isProfit ? ' title="Revenue after Amazon\'s fees, refunds and what the '
                    + 'stock cost. Withheld entirely when any unit shipped has no '
                    + 'recorded cost — a partial cost only ever flatters."' : '')
      + '>'
      + '<p class="stat-label">'+_sEsc(c.label)+'</p>'
      + '<p class="stat-number" style="'+col.replace(/^;/,"")+'">'
      + _sEsc(_sShort(c.value, c.kind, sum.currency))+'</p>'
      + (adsOff
          ? '<p class="stat-delta" title="'+_sEsc(sum.ads_note||"")+'">not connected</p>'
          : _sDelta(c, (SALES.compareKind === "year" ? "LY" : "was"),
                    c.prev_value, c.kind, sum.currency))
      + '</div>';
  }).join("");

  if(note){
    let n = "";
    if(!sum.ads_connected)
      n += '<div class="cc salesnote"><i class="ti ti-info-circle"></i> '
         + _sEsc(sum.ads_note||"") + '</div>';
    // Why a Profit row may be blank. Without this the em-dash reads as a fault
    // rather than as "some of these products have never been costed".
    const cov = sum.cogs_coverage;
    if(cov && cov.note)
      n += '<div class="cc salesnote"><i class="ti ti-info-circle"></i> '
         + _sEsc(cov.note) + '</div>';
    note.innerHTML = n;
  }
}

/* Change against the previous period of the SAME LENGTH. Carries an arrow and a
   word as well as a colour — a green number alone is unreadable to a good number
   of people, and meaningless in print. */
/* The comparison line under each figure, laid out as Orbit lays it out:
   the earlier figure in grey, then the percentage as a coloured chip.
   Measured from its live dashboard -- "LY: $551,866.01 +5.2%".

   Ours says "was" rather than "LY" because the comparison is the previous
   PERIOD by default, and calling a 30-day-ago figure "last year" would be a
   plain lie. When the comparison is set to a year earlier it says LY, because
   then it is one. */
function _sDelta(c, prevLabel, prevValue, kind, currency){
  if(c.delta_pct===null || c.delta_pct===undefined){
    // Said, not left as a dash. A blank here reads as a fault, and showing
    // "0.0%" for a period with nothing to compare against would be a fiction.
    return '<p class="stat-delta">no earlier period</p>';
  }
  const up = c.delta_pct >= 0;
  // Ad spend rising is not a win, so direction and goodness are separate things.
  const good = (c.key==="spend") ? !up : up;
  const cls = c.delta_pct===0 ? "flat" : (good?"up":"down");
  // ARROW AND SIGN, not colour alone. Orbit uses "↑ 21.1%" on its chart headers
  // and "+5.2%" on its cards; the arrow is kept on both because a green number
  // with no other cue is unreadable to a good number of people and means
  // nothing in print.
  const arrow = c.delta_pct===0 ? "→" : (up?"↑":"↓");
  const sign = c.delta_pct===0 ? "" : (up?"+":"−");
  const was = (prevValue===null || prevValue===undefined)
    ? "" : (prevLabel||"was") + ": " + _sShort(prevValue, kind, currency) + " ";
  return '<p class="stat-delta">' + _sEsc(was)
       + '<span class="pct-badge ' + cls + '" title="' + (up?"up":"down")
       + ' versus ' + _sEsc(prevLabel === "LY" ? "the same period last year"
                                               : "the period before") + '">'
       + arrow + ' ' + sign
       + Math.abs(c.delta_pct).toFixed(1) + '%</span></p>';
}

/* ---- the metrics × dates grid ------------------------------------------ */
function salesDrawGrid(ser){
  const host=document.getElementById("sales_grid");
  if(!host) return;
  if(!ser || !ser.ok){
    host.innerHTML='<div class="empty">'+_sEsc((ser&&ser.error)||"No data")+'</div>';
    return;
  }
  if(ser.empty || !(ser.metrics||[]).length){
    host.innerHTML='<div class="empty">No sales data for this period yet.'
      + '<div class="cc" style="margin-top:6px;font-size:11.5px">Amazon delivers sales '
      + 'a day or two behind, and never for today. Press Sync to pull what it has.</div></div>';
    return;
  }
  const cols=ser.columns||[];
  let h='<div class="salesgridwrap"><table class="salesgrid"><thead><tr>'
      + '<th class="mcol">Metric</th>'
      + cols.map(function(c){ return '<th>'+_sEsc(_sColLabel(c, ser.granularity))+'</th>'; }).join("")
      + '</tr></thead><tbody>';

  (ser.metrics||[]).forEach(function(m){
    // Shade against THIS metric's own range. Shading across rows would compare
    // sessions with revenue, which means nothing.
    const nums=m.cells.filter(function(v){ return v!==null && v!==undefined; }).map(Number);
    const lo=Math.min.apply(null, nums.length?nums:[0]);
    const hi=Math.max.apply(null, nums.length?nums:[0]);
    h += '<tr><th class="mcol" title="'+_sEsc(m.label)+'">'+_sEsc(m.label)+'</th>'
       + m.cells.map(function(v){
           const t=_sTint(v, lo, hi);
           const txt=_sNum(v, m.kind, ser.currency);
           return '<td'+(t?' style="background:'+t+'"':'')
                + ' title="'+_sEsc(m.label+": "+txt)+'">'+_sEsc(txt)+'</td>';
         }).join("")
       + '</tr>';
  });
  h+='</tbody></table></div>';
  host.innerHTML=h;
}

function _sColLabel(c, gran){
  if(gran==="month") return c;                 // 2026-08
  const p=String(c).split("-");
  return p.length===3 ? (p[1].replace(/^0/,"")+"/"+p[2]) : c;
}

/* ONE hue, light→dark, five steps. Five rather than a continuous ramp because
   past about seven classes adjacent shades blur; and the number is printed in
   every cell regardless, so the tint is an aid, never the reading. */
function _sTint(v, lo, hi){
  if(v===null||v===undefined) return "";
  if(!(hi>lo)) return "";
  const f=(Number(v)-lo)/(hi-lo);
  const step=Math.min(4, Math.max(0, Math.floor(f*5)));
  return ["rgba(45,212,168,.05)","rgba(45,212,168,.10)","rgba(45,212,168,.17)",
          "rgba(45,212,168,.25)","rgba(45,212,168,.34)"][step];
}

/* ---- actions ----------------------------------------------------------- */
async function salesSync(btn){
  const old = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled=true; btn.innerHTML='<span class="genspin"></span> pulling…'; }
  try{
    const j=await (await fetch("/sales/sync",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({marketplace:(typeof WS_MARKET!=="undefined"?WS_MARKET:"")})})).json();
    if(!j.ok){ toast(j.error||"Could not pull sales"); return; }
    // Say what is LEFT as well as what arrived: a backfill runs in passes, and
    // "7 days pulled" alone looks like it finished when it has not.
    let msg="Pulled "+(j.fetched||0)+" day"+((j.fetched===1)?"":"s");
    if(j.still_missing) msg+=" · "+j.still_missing+" still to fetch — press Sync again";
    if((j.failed||[]).length) msg+=" · "+j.failed.length+" Amazon would not return";
    toast(msg);
    salesReload();
  }catch(e){ toast("Sync failed: "+((e&&e.message)||e)); }
  finally{ if(btn){ btn.disabled=false; btn.innerHTML=old; } }
}

function salesExport(){
  // A plain navigation, so the browser saves it with the server's filename.
  window.location = "/sales/export?" + _sQuery();
}

/* Populate the product filter from what actually SOLD in the current range.
 *
 * It used to read the live-catalogue array this page never loads, so the filter
 * was empty unless you had visited the catalogue screen first — and once filled,
 * it offered ASINs with no sales in the period, every one of which selects an
 * empty screen. Sales are the right source for a sales filter.
 *
 * Ordered biggest-revenue first: the product someone wants is nearly always one
 * of the top few, and alphabetical order buries it.
 */
async function salesFillAsins(){
  const sel=document.getElementById("sales_asin");
  if(!sel) return;
  let items=[];
  try{
    const j=await (await fetch("/sales/products?"+_sQuery())).json();
    if(j && j.ok) items=j.products||[];
  }catch(e){ /* the filter is an aid; losing it must not take the screen down */ }

  const opts=items.map(function(it){
    const a=String(it.asin||"").trim();
    if(!a) return "";
    const rev=(it.revenue!==null&&it.revenue!==undefined)
      ? (" — "+_sNum(it.revenue,"money",(SALES.data&&SALES.data.currency)||"")) : "";
    return '<option value="'+_sEsc(a)+'">'+_sEsc(a+rev)+'</option>';
  }).filter(Boolean);

  sel.innerHTML='<option value="">All products'+(opts.length?(" ("+opts.length+")"):"")+'</option>'
              + opts.join("");
  // Keep the current selection even if it has dropped out of the new range, so
  // changing the dates does not silently reset the filter under you.
  if(SALES.asin && !items.some(function(i){return i.asin===SALES.asin;})){
    sel.insertAdjacentHTML("beforeend",
      '<option value="'+_sEsc(SALES.asin)+'">'+_sEsc(SALES.asin+" — no sales in range")+'</option>');
  }
  sel.value=SALES.asin||"";
}

function salesOpen(){
  const s=document.getElementById("sales_start"), e=document.getElementById("sales_end");
  if(s && !s.value) SALES.start="";
  if(e && !e.value) SALES.end="";
  salesDrawFilters();
  salesReload();
}
window.salesOpen = salesOpen;
window.salesSetAsin = salesSetAsin;
window.salesSetDates = salesSetDates;
