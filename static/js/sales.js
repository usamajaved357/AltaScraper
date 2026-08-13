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
    salesDrawCards(sum, av);
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
    return '<div class="stat-card'+(missing?" is-empty":"")+'">'
      + '<p class="stat-number">'+_sEsc(_sShort(c.value, c.kind, sum.currency))+'</p>'
      + '<p class="stat-label">'+_sEsc(c.label)+'</p>'
      + (adsOff
          ? '<p class="stat-delta cc" title="'+_sEsc(sum.ads_note||"")+'">not connected</p>'
          : _sDelta(c))
      + '</div>';
  }).join("");

  if(note){
    note.innerHTML = sum.ads_connected ? "" :
      '<div class="cc salesnote"><i class="ti ti-info-circle"></i> '
      + _sEsc(sum.ads_note||"") + '</div>';
  }
}

/* Change against the previous period of the SAME LENGTH. Carries an arrow and a
   word as well as a colour — a green number alone is unreadable to a good number
   of people, and meaningless in print. */
function _sDelta(c){
  if(c.delta_pct===null || c.delta_pct===undefined){
    return '<p class="stat-delta cc">no earlier period</p>';
  }
  const up = c.delta_pct >= 0;
  // Ad spend rising is not a win, so direction and goodness are separate things.
  const good = (c.key==="spend") ? !up : up;
  const cls = c.delta_pct===0 ? "flat" : (good?"good":"bad");
  const arrow = c.delta_pct===0 ? "→" : (up?"↑":"↓");
  return '<p class="stat-delta '+cls+'">'+arrow+' '
       + Math.abs(c.delta_pct).toFixed(1)+'% <span class="cc">vs previous</span></p>';
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
