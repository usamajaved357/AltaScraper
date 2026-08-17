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
             data:null, series:null, busy:false,
             // What the dashed line and every "was:" figure compare against.
             // Remembered on this browser, because it is a way of reading the
             // business rather than a one-off question.
             compareKind:(function(){
               try{ return localStorage.getItem("alta_sales_compare") || "period"; }
               catch(e){ return "period"; }
             })(),
             compare:null, compareOffsetDays:0, compareRange:"",
             // ---- the P&L heatmap's OWN period and granularity ----------------
             // Measured on Orbit: the heatmap carries its own Day/Week/Month and
             // 7d/14d/30d/60d/90d controls, separate from the Sales Report's
             // above it. That is a real feature and not a duplicate: the shape
             // of the month is a chart question, and "which week was expensive"
             // is a grid one, and they want different buckets.
             //
             // EMPTY MEANS FOLLOW THE SCREEN. Until one of these is touched the
             // grid draws from the series the rest of the page already fetched,
             // so the common case costs no extra request and the two cannot
             // disagree. Touching one makes the grid fetch its own.
             gridGran:"", gridPreset:"", gridSeries:null, gridBusy:false,
             // Which metric rows are hidden, remembered per browser. Thirty-
             // eight rows is a lot to scroll past when the question is about
             // four of them.
             gridHidden:(function(){
               try{ return JSON.parse(localStorage.getItem("alta_grid_hidden") || "[]"); }
               catch(e){ return []; }
             })()};

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
  // SEGMENTED, as Orbit has them: one tray at rgb(45,50,66) with the chosen one
  // filled gold. Measured -- tray radius 8 with 2px padding and 2px gaps, each
  // button 28 high, radius 6, padding 4/12, 10px text.
  const p=document.getElementById("sales_presets");
  if(p){
    p.className = "seg";
    p.innerHTML = SALES_PRESETS.map(function(x){
      return '<button class="'+(SALES.preset===x[0]?"on":"")+'" '
           + 'onclick="salesSet(\'preset\',\''+x[0]+'\')">'+x[1]+'</button>';}).join("");
  }
  const g=document.getElementById("sales_gran");
  if(g){
    g.className = "seg";
    g.innerHTML = SALES_GRAN.map(function(x){
      return '<button class="'+(SALES.gran===x[0]?"on":"")+'" '
           + 'onclick="salesSet(\'gran\',\''+x[0]+'\')">'+x[1]+'</button>';}).join("");
  }
  // THE LAST THREE WHOLE MONTHS. Orbit puts Aug / Jul / Jun beside the presets,
  // and a month is the unit a business reports in -- picking one out of two date
  // boxes is the step nobody takes.
  const mo = document.getElementById("sales_months");
  if(mo){
    mo.className = "seg";
    const now = new Date();
    let html = "";
    for(let back = 1; back <= 3; back++){
      const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - back, 1));
      const start = d.toISOString().slice(0, 10);
      const end = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0))
                    .toISOString().slice(0, 10);
      const name = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()];
      const on = (SALES.preset === "custom" && SALES.start === start && SALES.end === end);
      html += '<button class="' + (on ? "on" : "") + '" '
           +  'onclick="salesSetMonth(\'' + start + '\',\'' + end + '\')" '
           +  'title="' + start + ' to ' + end + '">' + name + '</button>';
    }
    mo.innerHTML = html;
  }
  const cmp = document.getElementById("sales_compare");
  if(cmp && cmp.value !== (SALES.compareKind || "period")) cmp.value = SALES.compareKind || "period";
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
/* The account this screen is displaying, named on every request.
 *
 * The server holds ONE active-account variable for the whole process, so a
 * reply could come back describing whichever account the global had drifted to
 * by the time the request was handled -- which is what changed Nestwell Goods'
 * figures after switching away and back. Naming it here means the answer always
 * describes the screen that asked. See domain/request_account.py. */
function _sAcct(){
  try{ return (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
              ? String(CUR_ACCOUNT.id || "") : ""; }catch(e){ return ""; }
}

/* Every request this screen makes, with the account attached and late replies
 * dropped. ONE place, so neither guarantee can be forgotten at a call site --
 * three of the queries on this screen are hand-built rather than going through
 * _sQuery(), and those were the ones travelling with no account at all.
 *
 * Naming the account fixes WHICH data comes back. Dropping the late reply fixes
 * WHERE it is painted: a reply for the account you have just left must not be
 * written into the account you have just opened, however correct it is.
 *
 * Returns null when the workspace moved on -- callers stop rather than paint. */
/* THE THREE ENDPOINTS THAT GO TO AMAZON, not to our own database.
 *
 * /sales/today, /sales/hourly and /sales/recent each pull orders live from the
 * Orders API. Everything else on this screen reads the local store and answers
 * in tens of milliseconds; these take seconds, and Amazon rations them -- one
 * call a minute, and going over is the "QuotaExceeded" the Live Sales card
 * showed. They are the reason a period click took nine and a half seconds.
 */
const _S_LIVE = ["/sales/today", "/sales/hourly", "/sales/recent"];
const _S_LIVE_TTL = 60000;      // one minute: Amazon's own refill rate
const _sInflight = {};          // url -> the promise already asking
const _sRecent = {};            // url -> {at, value} for the live three only

function _sIsLive(u){
  return _S_LIVE.some(function(p){ return String(u).indexOf(p) === 0; });
}

async function _sFetch(url, opts){
  const acct = _sAcct();
  let u = String(url);
  if(acct && u.indexOf("account_id=") < 0){
    u += (u.indexOf("?") < 0 ? "?" : "&") + "account_id=" + encodeURIComponent(acct);
  }
  // THE ACCOUNT IS PART OF THE KEY, AND NOTHING IS SHARED WITHOUT ONE.
  //
  // Sharing and reuse are keyed by the account as well as the URL. The URL
  // normally carries account_id and would be enough -- but only normally: for
  // the moment during a switch when CUR_ACCOUNT is not yet set, _sAcct() is ""
  // and nothing is appended, so two accounts produce the SAME url. Keyed on
  // the url alone, one account's Live Sales would then be handed to the other
  // and held for a minute. That is the account-mixing fault this codebase has
  // been bitten by before, and a cache is the easiest place in the app to
  // reintroduce it.
  //
  // With no account known, neither share nor store: an unidentified request is
  // exactly the one that must not be reused.
  const key = acct ? (acct + "|" + u) : "";
  // ASKED ONCE, NOT ONCE PER CALLER. Two parts of the screen wanting the same
  // thing at the same moment is one question, and it was being sent twice --
  // measured on a single 90-day click, /sales/hourly went to Amazon at +2.4s
  // and again at +7.7s for the same day's orders.
  const shareable = !opts && !!key;
  if(shareable && _sInflight[key]) return _sInflight[key];
  // AND NOT RE-ASKED FOR A MINUTE. Only for the live three: their answer
  // describes a FIXED window -- today, today and yesterday, the last six days
  // -- which the period pills cannot change, so re-fetching on every click
  // spent seconds and quota to be told the same thing.
  if(shareable && _sIsLive(u)){
    const hit = _sRecent[key];
    if(hit && (Date.now() - hit.at) < _S_LIVE_TTL) return hit.value;
  }
  const run = (async function(){
    try{
      const r = await fetch(u, opts);
      const j = await r.json();
      if(shareable && _sIsLive(u) && j && j.ok) _sRecent[key] = {at: Date.now(), value: j};
      return (_sAcct() === acct) ? j : null;
    }finally{
      if(shareable) delete _sInflight[key];
    }
  })();
  if(shareable) _sInflight[key] = run;
  return run;
}

/* Everything remembered for an account, forgotten when you leave it.
 *
 * Belt and braces on the keying above: switching account drops that account's
 * held answers rather than trusting them to age out, so nothing from the
 * screen you have just left can be painted onto the one you have just opened. */
function _sForget(){
  [_sInflight, _sRecent].forEach(function(store){
    Object.keys(store).forEach(function(k){ delete store[k]; });
  });
  // AND THE FIGURES THEMSELVES, not just the held replies.
  //
  // screenForgetAll empties the panels, but these live in memory and were
  // left behind -- so after switching account the grid still HELD the previous
  // account's series. Anything reading SALES.series before the new load
  // finished got the account you had just left: measured, opening Nestwell
  // Goods straight after Jack Reacherd left Jack Reacherd's days in
  // SALES.gridSeries while the cards above them were blank.
  try{
    SALES.series = null;
    SALES.gridSeries = null;
    SALES.data = null;
    SALES._live = null;
    SALES.compare = null;
    SALES._chartBasis = "";
  }catch(e){}
}

/* WHO IS ASKING, and nothing about WHEN.
 *
 * The three live endpoints above were being sent _sQuery(), which carries the
 * period and the granularity. Their windows are fixed and set on the server, so
 * those parameters changed nothing about the answer -- but they changed the
 * URL, so every click on 7d / 30d / 90d sent all three to Amazon again for
 * figures it had just been given. Scope only: the account and the marketplace,
 * which are the two things that genuinely change the answer.
 */
function _sScope(){
  const q = [];
  const a = _sAcct();
  if(a) q.push("account_id=" + encodeURIComponent(a));
  if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
    q.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return q.join("&");
}

function _sQuery(){
  const q=["preset="+encodeURIComponent(SALES.preset),
           "granularity="+encodeURIComponent(SALES.gran)];
  const _a = _sAcct();
  if(_a) q.push("account_id="+encodeURIComponent(_a));
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
    const j = await _sFetch("/sales/breakdown?"+_sQuery()
                            +"&group="+encodeURIComponent(SALES_BD.group));
    if(j === null) return;
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
  // A PERIOD WITH NOTHING IN IT SAYS SO, rather than leaving the space where
  // three charts belong empty. Seen on a live account: the request succeeded and
  // returned no columns, and the top half of the screen was simply blank, which
  // reads as a screen that failed to draw. Charting nothing is right; saying
  // nothing about it is not.
  if(!dates.length){
    host.innerHTML = '<div class="cc" style="padding:18px;border:1px dashed '
      + 'var(--line);border-radius:8px;font-size:12px">'
      + 'Nothing to chart for this period yet — Amazon has sent no figures for '
      + 'these dates. Press <b>Sync</b> to pull what it has, or widen the range.'
      + '</div>';
    return;
  }

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

  // ---- ORBIT'S ONE CHART, BEFORE THE SEPARATE ONES --------------------
  //
  // Orbit's Sales Report is a single combined chart -- gold bars for orders
  // against a right-hand count axis, money lines against the left -- with the
  // key underneath. Five separate panels answer the same questions but cannot
  // be read in one glance, which is the whole reason its dashboard feels
  // different from ours.
  //
  // Built from the same series as the panels below and with the same rules: a
  // day Amazon has not delivered stays null and is drawn as a gap, and a series
  // that is entirely zero is not drawn at all.
  let comboHtml = "";
  if(typeof salesCombo === "function"){
    const cells = function(key){
      const m = byKey[key];
      return m ? dates.map(function(d, i){ return m.cells[i]; }) : null;
    };
    const anyReal = function(vals){
      return vals && vals.some(function(v){
        return v !== null && v !== undefined && Number(v) !== 0; });
    };
    // ONE DATE BASIS FOR THE WHOLE CHART. This is the bug behind "it shows
    // sales and profit but the orders are zero, it can not be possible to
    // generate sales without orders".
    //
    // It IS possible, and both figures were right. Amazon dates the two feeds
    // differently:
    //
    //   Sales & Traffic report   dated by ORDER date
    //   finance records          dated by when the MONEY MOVED (shipment)
    //
    // So an order placed on the 5th and shipped on the 7th is an order on the
    // 5th and a profit on the 7th. Measured on jack_uk: EIGHT days carried
    // profit against a delivered, genuine zero for orders. Drawing the two
    // together on one chart, unlabelled, states something impossible.
    //
    // Orbit does not have this problem because it commits to one basis and says
    // so on the card -- "Based on order dates". So does this chart now: the
    // order basis when the report has delivered, because that is the one that
    // carries orders at all, and the money basis otherwise. Whichever it picks,
    // every series on the chart comes from it, and the panel says which.
    // THE DAYS THE REPORT HAS NOT SENT YET, FILLED FROM THE ORDERS API.
    //
    // "but in amazn i am able to see the sales from yesterday accurately, why
    // not here" -- because Seller Central reads the Orders API and this chart
    // was reading the Sales & Traffic report, which runs a day or two behind.
    //
    // Both count an order on the day it was PLACED. They are the same
    // measurement, and the report is simply the settled version that arrives
    // later, which is what makes this safe -- unlike the finance feed below,
    // which is dated by when the money moved and belongs to different days.
    //
    // ONLY where the report has sent NOTHING (null). A figure Amazon has
    // actually delivered is never overwritten, so the chart cannot start
    // disagreeing with the grid under it on a settled day.
    const live = SALES._live || null;
    const _fill = function(vals, key){
      if(!live || !vals) return vals;
      return vals.map(function(v, i){
        if(v !== null && v !== undefined) return v;
        const day = live[dates[i]];
        return (day && day[key] !== undefined) ? day[key] : v;
      });
    };
    const liveOrders = _fill(cells("orders"), "orders");
    const liveSales  = _fill(cells("ordered_sales"), "revenue");

    // THE SERVER SAYS WHICH CALENDAR THIS IS. The chart does not decide.
    //
    // It used to: "order basis if any order or sale is non-zero, money basis
    // otherwise". That was a fourth opinion on a question the route, the grid
    // and the profit card were each already answering their own way, and four
    // answers to one question is why nothing on this screen agreed with
    // anything else on it. The route now decides once, in _basis(), and says
    // so in ser.basis -- and every part of the screen reads that one answer.
    //
    // The fallback is kept only for a reply that predates the field.
    const orderBasis = (ser && ser.basis)
      ? (ser.basis === "order")
      : (anyReal(liveOrders) || anyReal(liveSales));
    SALES._chartBasis = orderBasis ? "order" : "money";
    SALES._liveFilled = orderBasis && live
      ? dates.filter(function(d, i){
          const rep = (cells("orders") || [])[i];
          return live[d] && (rep === null || rep === undefined);
        })
      : [];
    const salesCells  = orderBasis ? liveSales : cells("net_revenue");
    const orderCells  = orderBasis ? liveOrders : cells("units_shipped");
    // PROFIT IS NOW DRAWN ON EITHER CALENDAR, because on the order basis it is
    // no longer on a different one. It used to be left off: profit came from
    // the finance feed, dated by when the money moved, so a profit line beside
    // order-dated bars put the two on different days -- eight days on jack_uk
    // carried profit against a genuine zero for orders.
    //
    // The route re-dates the settled money to each order's own day, so the
    // profit for a day and the orders for that day are now the same trade.
    // Drawn when it is there, left out when it is not -- which happens when a
    // product has no cost recorded, and the COGS strip under the grid says so.
    const profitCells = cells("profit");

    // The comparison, on the same axis as Sales, matched by date exactly as the
    // single-metric charts match it.
    let cmpCells = null;
    if(SALES.compare && SALES.compare.metrics && SALES.compareOffsetDays){
      const key = anyReal(cells("net_revenue")) ? "net_revenue" : "ordered_sales";
      const cm = SALES.compare.metrics.filter(function(m){ return m.key === key; })[0];
      if(cm && cm.cells){
        const was = {};
        (SALES.compare.columns || []).forEach(function(d, i){ was[d] = cm.cells[i]; });
        const off = SALES.compareOffsetDays * 86400000;
        cmpCells = dates.map(function(d){
          const dt = new Date(String(d) + "T00:00:00Z");
          if(isNaN(dt)) return null;
          const back = new Date(dt.getTime() - off).toISOString().slice(0, 10);
          return (back in was) ? was[back] : null;
        });
        if(!anyReal(cmpCells)) cmpCells = null;
      }
    }

    const comboLines = [];
    if(anyReal(salesCells))  comboLines.push({key: "sales",  values: salesCells});
    if(profitCells && anyReal(profitCells)) comboLines.push({key: "profit", values: profitCells});
    if(cmpCells) comboLines.push({
      key: (SALES.compareKind === "year") ? "prior_year" : "prior",
      values: cmpCells});

    if(comboLines.length || anyReal(orderCells)){
      comboHtml = salesCombo({
        // The currency, so the money axis reads "£28.0k" rather than a bare
        // number. Orbit's reads "$28.0k".
        currency: (ser && ser.currency),
        id: "sales_combo", columns: dates,
        // Orbit's Sales Report keeps a 320px height at every width -- measured
        // 1365x320 on desktop and 340x320 on a phone. See scChartWidth.
        width: scChartWidth("sales_charts", 1365), height: 320,
        // THE LABEL FOLLOWS THE DATA. This said "Orders" whatever was in the
        // bars, and on the money basis the bars hold UNITS SHIPPED -- dated by
        // when the money moved, not when the order was placed.
        //
        // Reported on jack_uk: "the graph shows i generated an order on 7 9 and
        // 12th aug but i did not a single in these days". Reproduced exactly --
        // on a 14-day range that account's report feed has delivered nothing, so
        // the chart fell back to the finance feed and drew a bar on each of
        // those three settlement days, under a key that read "Orders".
        //
        // The panel already carried a note saying which basis was in use, but
        // the key sits directly under the bars and is what gets read. A label
        // that contradicts the note is worse than no note.
        bars: anyReal(orderCells)
          ? {label: (orderBasis ? "Orders" : "Units shipped"), values: orderCells}
          : null,
        lines: comboLines,
      });
    }
  }

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
  // The combined chart FIRST and full width, as Orbit has it: orders, sales,
  // profit and the comparison in one picture. The per-metric panels follow for
  // the things it cannot carry -- margin and conversion are percentages and
  // would need a third scale.
  if(comboHtml){
    // A CHART WITH ONE COLUMN LOOKS BROKEN, and it is not -- it is one day of
    // figures, drawn correctly: a single bar with three dots stacked at the
    // same position, because there is nothing to draw a line between.
    // Reported as "3 lines and 1 pillar displaying at a single spot", which is
    // an exact description of it. So the chart says how many days it actually
    // has rather than leaving that to be worked out.
    const withData = dates.filter(function(d, i){
      return (rows || []).some(function(m){
        const v = (m.cells || [])[i];
        return v !== null && v !== undefined && Number(v) !== 0;
      });
    }).length;
    // WHICH BASIS, said on the panel exactly as Orbit says "Based on order
    // dates". Without it the same product appears to have sold on two
    // different days depending on which screen you are looking at, and there
    // is no way to tell that both are right.
    // WHY THE PROFIT LINE IS A DOT.
    //
    // Reported as "the profit lines do not appears on the graph it just show a
    // dot". It is drawn correctly: profit exists on ONE day out of twenty,
    // because profit is withheld for any day where a unit shipped has no cost
    // recorded, and 19 of Nestwell's 22 units have none. One point is a dot --
    // there is nothing to draw a line to.
    //
    // The reason was already on the screen, under the cards, as the COGS
    // coverage note. It is said HERE too because here is where the dot is, and
    // it is the same fact from the same place rather than a second opinion.
    const _pm = (rows || []).filter(function(m){ return m.key === "profit"; })[0];
    const _pdays = _pm ? (_pm.cells || []).filter(function(v){
      return v !== null && v !== undefined; }).length : 0;
    const _sparse = (_pm && _pdays > 0 && _pdays < Math.max(2, dates.length / 3))
      ? ' <b>Profit</b> is drawn on only ' + _pdays + ' of these ' + dates.length
        + ' days: a day is left out when any unit shipped that day has no cost '
        + 'recorded, so the line breaks rather than guessing. Enter costs on the '
        + 'Listings screen and the rest fill in.'
      : '';
    let note = (SALES._chartBasis === "order")
      ? '<div class="cc" style="font-size:11.5px;margin:0 0 8px">'
        + 'Based on <b>order dates</b> — counted when the order was placed, '
        + 'including Amazon’s fees, so every line describes the same trade.'
        + _sparse + '</div>'
      : '<div class="cc" style="font-size:11.5px;margin:0 0 8px">'
        + 'Based on <b>when the money moved</b> — the gold bars are <b>units '
        + 'shipped</b>, dated at settlement, <b>not orders</b>. A bar on a day '
        + 'means money settled that day for an order placed earlier. The Sales '
        + '&amp; Traffic report has delivered no order counts for this period, '
        + 'which is why the chart cannot show order dates.</div>';

    // THE DAYS AT THE END THAT AMAZON HAS NOT SENT YET.
    //
    // Reported: "i got orders 3 orders yesterday and those are not displayed in
    // the graph". They are real, and they are not in this chart because the
    // Sales & Traffic report runs a day or two behind -- yesterday's row simply
    // does not exist yet. The chart draws a gap rather than a zero, which is
    // right, but a gap at the right-hand edge is indistinguishable from a quiet
    // day unless it is named.
    //
    // The Live Sales card DOES have them: it reads the Orders API directly.
    // Those are two different measurements and merging them into one line is
    // exactly the mix this chart refuses to make, so the answer is to say where
    // the missing days are rather than to fill them in.
    const _tail = (function(){
      const undelivered = [];
      for(let i = dates.length - 1; i >= 0; i--){
        const any = (rows || []).some(function(m){
          const v = (m.cells || [])[i];
          return v !== null && v !== undefined;
        });
        if(any) break;
        undelivered.push(dates[i]);
      }
      return undelivered.reverse();
    })();
    const _filled = SALES._liveFilled || [];
    if(_filled.length){
      note += '<div class="cc" style="font-size:11.5px;margin:0 0 8px;padding:8px 11px;'
        + 'border:1px solid var(--line);border-radius:6px">'
        + '<i class="ti ti-bolt"></i> <b>' + _sEsc(_filled.join(", ")) + '</b> '
        + (_filled.length === 1 ? 'is' : 'are') + ' counted live from the Orders '
        + 'API, because Amazon\'s Sales &amp; Traffic report has not delivered '
        + (_filled.length === 1 ? 'that day' : 'those days') + ' yet — this is the '
        + 'same feed Seller Central shows you. The figures settle into the report '
        + 'within a day or two and the chart will switch to it automatically.</div>';
    } else if(_tail.length){
      note += '<div class="cc" style="font-size:11.5px;margin:0 0 8px;padding:8px 11px;'
        + 'border:1px solid var(--warn-line);background:var(--warn-bg);border-radius:6px">'
        + '<i class="ti ti-info-circle"></i> Amazon has sent nothing yet for '
        + '<b>' + _sEsc(_tail.join(", ")) + '</b>. The Sales &amp; Traffic report '
        + 'runs a day or two behind, so orders placed since then are not on this '
        + 'chart — they are counted on the <b>Live Sales</b> card above, which '
        + 'reads orders directly as they arrive.</div>';
    }
    if(withData <= 2){
      note += '<div class="cc" style="font-size:11.5px;margin:0 0 8px;padding:8px 11px;'
        + 'border:1px solid var(--warn-line);background:var(--warn-bg);border-radius:6px">'
        + '<i class="ti ti-info-circle"></i> Only <b>' + withData + ' day'
        + (withData === 1 ? '' : 's') + '</b> in this range has figures, so there '
        + 'is nothing to draw a line between — the marks sit at that one day. '
        + 'Press <b>Sync</b> to pull the rest, or widen the range.</div>';
    }
    // NOT a nested .salespanel. #sales_charts already sits inside one, so this
    // wrapper made a card inside a card and charged the chart TWO lots of
    // padding: measured on a 390px phone, Orbit's Sales Report chart is 340
    // wide and ours was 306, entirely because of this line.
    h += '<div style="margin:0 0 16px">' + note + comboHtml + '</div>';
  }
  // ONE CHART, NOT SIX.
  //
  // Orbit's Sales Dashboard has exactly three: Live Sales, Week to Date, and
  // this combined one. Ours drew five separate panels -- Revenue, Units,
  // Profit, Margin, Conversion -- and when the combined chart was added they
  // were left in place, so the screen had six. That is not "close to Orbit
  // with some extras"; it is a different screen.
  //
  // Everything the five panels showed is still reachable: revenue, orders and
  // profit are ON the combined chart, and every metric including margin and
  // conversion is in the grid below it, per day, in full. What is gone is five
  // charts nobody asked for competing with the one that matters.
  //
  // The feed-disagreement warning the panels carried moves here, because it is
  // about the data rather than about any one chart: if the report says zero for
  // a period the finance records have sales for, that is worth knowing and it
  // was the whole reason those panels named their source.
  const zeroed = [];
  [["Revenue", ["net_revenue", "ordered_sales"]],
   ["Units",   ["units_shipped", "units"]],
   ["Profit",  ["profit"]]].forEach(function(pair){
    const anyPresent = pair[1].some(function(k){ return pts(k); });
    const anyUsable  = pair[1].some(function(k){ return usable(pts(k)); });
    if(anyPresent && !anyUsable) zeroed.push(pair[0]);
  });
  if(zeroed.length){
    h += '<div class="cc" style="font-size:11.5px;margin-top:10px;padding:9px 11px;'
      +  'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
      +  '<i class="ti ti-info-circle"></i> ' + _sEsc(zeroed.join(", "))
      +  ': every value Amazon has sent for this period is zero. That is what a '
      +  'feed which has not arrived looks like, so it is left off the chart '
      +  'rather than drawn as no sales. Press <b>Sync</b> to keep '
      +  'backfilling.</div>';
  }
  host.innerHTML = (comboHtml || zeroed.length) ? h : "";
  // Any chart below the fold is held at the start of its sweep until it is
  // scrolled to, so there is still motion left when you reach it. See
  // altaChartsInView in motion.js.
  if(typeof altaChartsInView === "function") altaChartsInView(host);
}

/* THE WHOLE PAGE AT ONCE, then the numbers.
 *
 * "our app displays the content in the graphs in parts... in orbit when i click
 * on the sales dashboard all of the graphs etc is displayed... data takes a sec
 * to load, but our app displays the content in the graphs in parts".
 *
 * MEASURED, sampling every 250ms from the moment Sales is opened:
 *
 *   stat cards       250 ms
 *   Week to Date     250 ms
 *   Sales Report     250 ms
 *   Organic vs PPC   250 ms
 *   P&L Heatmap      250 ms
 *   Live Sales      5750 ms      <- a 5.5 SECOND spread
 *
 * Two separate causes, and both are fixed rather than papered over.
 *
 * The first is ordering: salesLoadToday() reads the Orders API, which is by far
 * the slowest call on the screen, and it was started LAST -- after five other
 * renders had already finished. It now starts before the awaits, so it is in
 * flight while the report requests are.
 *
 * The second is that an empty panel showed NOTHING. A panel with its frame and a
 * shimmer says "this is loading"; an empty box says the page is broken or the
 * feature is missing. Orbit draws every panel immediately and only the data
 * arrives late, which is why its screen never looks like it is assembling
 * itself.
 *
 * Only ever into an EMPTY panel -- altaSkeletonInto refuses to cover content
 * that is already there, so a reload keeps the figures you were reading instead
 * of replacing them with grey blocks.
 */
function _sFrameUp(){
  if(typeof altaSkeletonInto !== "function") return;
  [["sales_today", {cards: 0, rows: 2}],
   ["sales_week", {cards: 0, rows: 3}],
   ["sales_cards", {cards: 5, rows: 0}],
   ["sales_charts", {cards: 0, rows: 5}],
   ["sales_orgppc", {cards: 0, rows: 4}],
   ["sales_grid", {cards: 0, rows: 8}]].forEach(function(p){
    try{ altaSkeletonInto(p[0], p[1]); }catch(e){}
  });
}

async function salesReload(){
  // ASKED WHILE ALREADY LOADING? REMEMBER IT, do not throw it away.
  //
  // This used to return, so changing the date range while the screen was still
  // loading did nothing at all -- the click vanished and the old period stayed
  // on screen looking like the answer. Worse on a slow account, which is
  // exactly where somebody is most likely to click again.
  //
  // One pending re-run is enough: three impatient clicks want the LAST period
  // asked for, not three sequential loads of the first three.
  if(SALES.busy){ SALES._again = true; return; }
  SALES.busy=true;
  SALES._again = false;
  // Every panel gets its frame before anything is asked for, so the screen
  // arrives whole rather than assembling itself. See _sFrameUp.
  _sFrameUp();
  // THE SLOWEST CALL FIRST. Live Sales reads the Orders API and took 5.75s of
  // the 5.75s spread measured above, purely because it was started last.
  salesLoadToday();
  salesLoadWeek().catch(function(){});
  // Hold the previous render at reduced opacity rather than flashing a skeleton
  // — no layout jump, and the numbers you were reading stay readable.
  const grid=document.getElementById("sales_grid");
  if(grid && grid.innerHTML.trim()) grid.style.opacity=".45";
  try{
    // AVAILABILITY FIRST. Ask what dates exist before asking for numbers, so a
    // period Amazon has not delivered is reported as such instead of drawn as a
    // wall of zeros.
    const av = await _sFetch("/sales/availability?"+_sQuery());
    if(av === null) return;
    // Kept, so every part of the screen can say what it does and does not have.
    // The grid needs it as much as the cards do -- an empty column and a column
    // that is genuinely zero look identical, and they are not the same fact.
    SALES.avail = av;
    const [sum, ser] = await Promise.all([
      _sFetch("/sales/summary?"+_sQuery()),
      _sFetch("/sales/series?"+_sQuery())
    ]);
    if(sum === null || ser === null) return;
    SALES.data=sum; SALES.series=ser;
    // The period immediately before this one, for the comparison line. Fetched
    // separately and NOT awaited with the rest: the charts must not wait for
    // context to draw the thing the context is about. When it arrives the
    // charts redraw with it; if it fails they simply stay as they are.
    SALES.compare = null;
    // CLEARED BEFORE THE NEW ONE IS ASKED FOR. Without this, switching account
    // or marketplace leaves the previous one's live orders in place and they
    // are drawn onto the new account's chart -- one account's sales shown under
    // another's name, which this app has shipped three times and must not again.
    SALES._live = null;
    SALES._liveFilled = [];
    salesLoadCompare(sum).catch(function(){});
    // The last few days of orders, live. NOT awaited, for the same reason the
    // comparison is not: the chart must draw from the report the moment it has
    // it, and this only ever ADDS the days the report has not covered. If it is
    // slow the chart is already up; if it fails the chart is exactly what it was
    // before, with the note saying which days are missing.
    salesLoadRecent().catch(function(){});
    salesDrawCards(sum, av);
    // The stock-cost bar, right under the Profit card it explains. Fire and
    // forget: a missing costing setting must never hold up the figures.
    if(typeof cogsModeLoad === "function") cogsModeLoad().catch(function(){});
    salesDrawCharts(ser);
    salesDrawOrgPpc(ser);
    salesDrawGrid(ser);
    salesDrawRange(sum, av);
    // After the numbers, not before: the options depend on the range, and the
    // grid is what someone is waiting for.
    salesFillAsins();
    // salesLoadToday() and salesLoadWeek() are NOT called here any more. They
    // are started at the top of this function, before the awaits, because Live
    // Sales reads the Orders API and was the slowest thing on the screen by a
    // factor of twenty -- 5.75s against 250ms for everything else -- entirely
    // because it went last. Calling them again here would fetch both twice.
  }catch(e){
    const g=document.getElementById("sales_grid");
    if(g) g.innerHTML='<div class="empty">Could not load sales: '+_sEsc(String(e))+'</div>';
  }finally{
    if(grid) grid.style.opacity="";
    SALES.busy=false;
    // Whatever was asked for while this was running now happens, with the
    // period that was actually chosen. Deferred a tick so the flag is clear
    // before the next run reads it.
    if(SALES._again){
      SALES._again = false;
      setTimeout(function(){ salesReload(); }, 0);
    }
  }
}

/* ---- the days the report has not sent yet, read live --------------------
 *
 * "but in amazn i am able to see the sales from yesterday accurately, why not
 * here". Seller Central reads the Orders API; this screen read the Sales &
 * Traffic report, which runs a day or two behind. Measured on jack_uk: the
 * report had nothing at all for 14 August, and the Orders API had the three
 * orders placed that day, £102.21 — the exact figures the account holder could
 * see in Amazon and not here.
 *
 * Six days is enough: the report is rarely more than two behind, and asking for
 * a month of orders is a slow call that pages.
 */
async function salesLoadRecent(){
  if(!SALES.series || !((SALES.series.columns) || []).length) return;
  let j;
  try{
    // _sScope(), not _sQuery(): days=6 already says which window this is.
    j = await _sFetch("/sales/recent?days=6&" + _sScope());
    if(j === null) return;
  }catch(e){ return; }
  // A 502 here is normal and not worth reporting: an account whose Amazon app
  // is not authorised for Orders simply keeps the report-only chart it had.
  if(!j || !j.ok || !j.days || !Object.keys(j.days).length) return;
  SALES._live = j.days;
  // Redraw from the series already in hand -- no second request for anything.
  // THE CARDS TOO. They are built server-side from the report alone, so without
  // this the cards say "0 orders, £0" while the chart beside them shows
  // yesterday's three. Reported exactly that way: the totals and the graph
  // disagreeing on the same screen.
  if(SALES.series){
    salesDrawCharts(SALES.series);
    salesDrawGrid(SALES.series);
    if(SALES.data) salesDrawCards(SALES.data, null);
  }
}

/* What the live feed adds to a card, for the days the report has not sent.
 *
 * The cards come from /sales/summary, which reads the report and nothing else.
 * On a short window that is routinely every day but the last, so a week whose
 * only trade was yesterday reads as a week with no trade at all -- while the
 * chart beside it, which IS filled, shows the orders. Two numbers describing
 * the same week, disagreeing, is worse than either being late.
 *
 * ONLY the days the report has not delivered, matched against the same series
 * the chart draws, so the two cannot diverge. A day Amazon has reported -- even
 * as a genuine zero -- is never touched.
 */
function _sLiveAdd(key){
  const live = SALES._live;
  const ser = SALES.series;
  if(!live || !ser) return 0;
  const dates = ser.columns || [];
  const rep = ((ser.metrics || []).filter(function(m){ return m.key === key; })[0] || {}).cells || [];
  const field = (key === "orders") ? "orders"
              : (key === "units") ? "units"
              : (key === "ordered_sales") ? "revenue" : "";
  if(!field) return 0;
  let add = 0;
  dates.forEach(function(d, i){
    const v = rep[i];
    if(v !== null && v !== undefined) return;      // Amazon has spoken
    const day = live[d];
    if(day && day[field]) add += Number(day[field]) || 0;
  });
  return add;
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
/* WHAT THE DASHED LINE IS COMPARED AGAINST. Two answers that mean something --
   the period immediately before ("is this week better than last") and the same
   period a year ago ("is this Christmas better than last Christmas") -- plus
   the option of neither, because on a screen this dense a second line you are
   not using is just ink. */
/* One whole month, from its chip. Sets the same custom range the date boxes
   would, so everything downstream -- the comparison, the export, the zoom --
   behaves exactly as it does for any other range. */
function salesSetMonth(start, end){
  SALES.preset = "custom";
  SALES.start = start;
  SALES.end = end;
  const a = document.getElementById("sales_start");
  const b = document.getElementById("sales_end");
  if(a) a.value = start;
  if(b) b.value = end;
  SALES._zoomBack = null;
  salesDrawFilters();
  salesReload();
}

function salesSetCompare(v){
  SALES.compareKind = v || "period";
  SALES.compare = null;
  SALES.compareOffsetDays = 0;
  try{ localStorage.setItem("alta_sales_compare", SALES.compareKind); }catch(e){}
  // Redraw immediately so the old line goes at once, then fetch the new one.
  if(SALES.series) salesDrawCharts(SALES.series);
  if(SALES.data) salesDrawCards(SALES.data, null);
  if(SALES.compareKind !== "none" && SALES.data) salesLoadCompare(SALES.data).catch(function(){});
}

async function salesLoadCompare(sum){
  if(SALES.compareKind === "none") return;
  if(!sum || !sum.ok || !sum.start || !sum.end) return;
  const start = new Date(sum.start + "T00:00:00Z");
  const end   = new Date(sum.end   + "T00:00:00Z");
  if(isNaN(start) || isNaN(end)) return;
  const days = Math.round((end - start) / 86400000) + 1;
  if(days < 2 || days > 400) return;             // nothing to compare against

  // WHERE THE COMPARISON WINDOW SITS depends on what is being compared against.
  //
  //   prior period   the same number of days immediately before this range
  //   prior year     the SAME dates, 364 days back
  //
  // 364 and not 365: it is exactly 52 weeks, so Monday lines up with Monday.
  // Retail weeks are the thing that actually repeats -- comparing a Saturday
  // against a Friday would put a weekend against a weekday and call the
  // difference a trend.
  const year = (SALES.compareKind === "year");
  const offsetDays = year ? 364 : days;
  const prevEnd   = year ? new Date(end.getTime()   - 364 * 86400000)
                         : new Date(start.getTime() - 86400000);
  const prevStart = year ? new Date(start.getTime() - 364 * 86400000)
                         : new Date(prevEnd.getTime() - (days - 1) * 86400000);
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

  const j = await _sFetch("/sales/series?" + q.join("&"));
  if(!j || !j.ok || !(j.columns || []).length) return;
  SALES.compare = j;
  // The offset, in days, between a column here and the column it is compared
  // against. Kept because the two series are matched BY DATE, not by position:
  // measured on jack_uk, a 30-day request came back with 28 columns for this
  // period and 1 for the period before, because the reply carries only the
  // buckets that have figures. Pairing them by position would have compared
  // June 15th against July 15th; requiring equal lengths would have meant the
  // comparison never drew at all.
  SALES.compareOffsetDays = offsetDays;
  SALES.compareRange = iso(prevStart) + " to " + iso(prevEnd);
  salesDrawCharts(SALES.series);
}

/* ---- week to date ------------------------------------------------------
 * The second of Orbit's two "how is it going right now" cards: Monday to
 * today, drawn against the same days of the week before.
 *
 * Built from a request of its own rather than sliced out of the main range,
 * because the main range is whatever the user last picked -- on a 90-day view
 * there would be no "this week" in it to slice, and on a custom range there
 * might be no Monday at all.
 */
async function salesLoadWeek(){
  const host = document.getElementById("sales_week");
  const badge = document.getElementById("sales_week_delta");
  if(!host) return;
  const today = new Date();
  const dow = (today.getUTCDay() + 6) % 7;          // Monday = 0
  const mon = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(),
                                today.getUTCDate() - dow));
  const lastMon = new Date(mon.getTime() - 7 * 86400000);
  const lastEnd = new Date(mon.getTime() - 86400000);
  const iso = d => d.toISOString().slice(0, 10);
  const base = function(a, b){
    const q = ["preset=custom", "start=" + iso(a), "end=" + iso(b), "granularity=day"];
    if(SALES.asin) q.push("asin=" + encodeURIComponent(SALES.asin));
    if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
      q.push("marketplace=" + encodeURIComponent(WS_MARKET));
    return q.join("&");
  };
  host.innerHTML = '<div class="cc" style="padding:14px;font-size:12px">Loading…</div>';
  let now, before;
  try{
    now    = await _sFetch("/sales/series?" + base(mon, today));
    before = await _sFetch("/sales/series?" + base(lastMon, lastEnd));
    if(now === null || before === null) return;
  }catch(e){
    host.innerHTML = '<div class="cc" style="padding:14px;font-size:12px">'
      + 'Could not load this week.</div>';
    return;
  }
  if(!now || !now.ok){ host.innerHTML = ""; return; }

  const key = function(j){
    const has = function(k){
      const m = ((j.metrics)||[]).filter(function(x){ return x.key === k; })[0];
      return m && (m.cells||[]).some(function(v){ return v !== null && Number(v) !== 0; })
             ? m : null;
    };
    return has("net_revenue") || has("ordered_sales");
  };
  const mNow = key(now), mBefore = key(before);
  if(!mNow){
    host.innerHTML = '<div class="cc" style="padding:14px;font-size:12px">'
      + 'Nothing recorded for this week yet.</div>';
    if(badge) badge.innerHTML = "";
    return;
  }

  // Both weeks laid out Monday-first, so day 1 sits under day 1 whatever dates
  // they carry -- which is the whole point of a week-on-week picture.
  const cols = now.columns || [];
  const pts = cols.map(function(d, i){ return {label: d, value: mNow.cells[i]}; });
  let cmp = null;
  if(mBefore && (before.columns||[]).length){
    const byPos = (before.columns||[]).map(function(d, i){ return mBefore.cells[i]; });
    cmp = cols.map(function(d, i){
      return {label: (before.columns||[])[i] || "", value: (i < byPos.length ? byPos[i] : null)};
    });
    if(!cmp.some(function(p){ return p.value !== null && Number(p.value) !== 0; })) cmp = null;
  }

  // A WEEK IS SEVEN BUCKETS, NOT SEVEN INSTANTS, so the points sit at the middle
  // of each day's band and are captioned by day name -- Sun, Mon, Tue … -- which
  // is what Orbit's Week to Date x-axis reads (measured: seven labels at 106.4
  // through 603.6, one per band centre). Ours read "Aug 9 … Aug 15": the same
  // information in the form you would use to file it rather than to say it, and
  // on a chart of one week the date adds nothing the title has not said.
  const wkOpts = {
    title: "", kind: "money", color: "#3b82f6", id: "sales_week_chart",
    currency: (now && now.currency),
    // The card's own width, so the chart is drawn at 1:1 and keeps its 200px
    // height at every screen size -- which is what Orbit does. See
    // scChartWidth: with height:auto a 340px phone got a 102px-tall chart.
    width: scChartWidth("sales_week", 665),
    height: 200, compare: cmp, scale: "band", xLabel: "dow",
    compact: true, thisLabel: "This Week", compareLabel: "Last Week",
    // Named for the days actually DRAWN. Last week is fetched Monday to Sunday,
    // but the dashed line is aligned by position against this week's columns, so
    // on a partial week it stops where this week stops -- and saying it runs to
    // Sunday describes a line that is not on the chart.
    compareTitle: cmp
      ? ("the dashed line is " + (cmp[0] ? cmp[0].label : iso(lastMon)) + " to "
         + (cmp[cmp.length - 1] ? cmp[cmp.length - 1].label : iso(lastEnd)))
      : ""};
  // Remembered so a window resize can REDRAW at the new width without fetching
  // the week again. A chart drawn at a fixed pixel width has to be redrawn when
  // that width changes, or turning a phone sideways letterboxes it.
  SALES._weekDraw = function(){
    wkOpts.width = scChartWidth("sales_week", 665);
    host.innerHTML = salesChart(pts, wkOpts) + SALES._weekFoot;
  };
  host.innerHTML = salesChart(pts, wkOpts);

  // The key goes in the card's HEADER, which is where Orbit has it -- "This
  // Week", "Last Week", then the change badge, all on the title's own line.
  // It used to sit between the header and the chart, pushing the chart down and
  // giving the card a band of small print Orbit does not have.
  const wkey = document.getElementById("sales_week_key");
  if(wkey) wkey.innerHTML = salesChartKey(wkOpts);

  // The missing days still have to be explained -- the shaded block on the right
  // is the days Amazon has not delivered, and unexplained it reads as a fault.
  // It goes under the subtitle rather than over the chart.
  const wnote = document.getElementById("sales_week_note");
  if(wnote){
    const gaps = pts.filter(function(p){
      return p.value === null || p.value === undefined; }).length;
    wnote.className = "panelnote warn";
    wnote.textContent = gaps
      ? ("· " + gaps + " day" + (gaps === 1 ? "" : "s")
         + " not in from Amazon yet — shaded, not zero")
      : "";
  }

  // ORBIT'S WEEK CARD HAS AN AD FOOTER TOO -- measured: "Ad spend this week
  // $10,633 · TACOS 9.8%", the label at 10px and the figure at 12px. Ours had
  // one under Live Sales and nothing under this card, so the two halves of the
  // top row did not even end the same way. Neither figure is available on this
  // account, and the footer says which and why rather than leaving a gap that
  // looks like a design that forgot something.
  SALES._weekFoot = '<div class="adfooter">'
    + '<span class="lbl">Ad spend this week</span> <b>not connected</b>'
    + '<span class="lbl" style="margin-left:8px">Tacos</span> <b>not connected</b>'
    + '<span style="color:rgb(156,163,175)"> — both need the Advertising API.</span>'
    + '</div>';
  host.innerHTML += SALES._weekFoot;

  // THE SAME DAYS, WHICH IS WHAT THE CHIP SAYS IT IS COMPARING.
  //
  // This week runs Monday to TODAY; last week is fetched Monday to Sunday so the
  // dashed line has somewhere to come from. The chip summed both in full -- a
  // partial week against a whole one -- so on a Wednesday it reported roughly
  // -57% on trade that had not moved at all, and its own tooltip said "against
  // the same days last week" while doing it.
  //
  // Week to Date is a CALENDAR week, Monday to today. Its comparison has to be
  // the same slice of the week before, not the whole of it.
  if(badge){
    const cellsOf = function(m){ return (m ? (m.cells || []) : []); };
    const daysSoFar = cellsOf(mNow).length;
    const sum = function(cells){
      return cells.reduce(function(a, v){ return a + (Number(v) || 0); }, 0);
    };
    const a = sum(cellsOf(mNow));
    const b = sum(cellsOf(mBefore).slice(0, daysSoFar));
    if(!b){ badge.innerHTML = ""; }
    else badge.innerHTML = _sBadge(((a - b) / Math.abs(b)) * 100,
      {title: "against the same " + daysSoFar + " day"
              + (daysSoFar === 1 ? "" : "s") + " of last week"});
  }
}

/* ---- organic vs PPC -----------------------------------------------------
 * Orbit's split of what sold on its own against what advertising paid for:
 * two stacked areas in its own measured colours (#10b981 organic, #8b5cf6
 * PPC), a share bar above them, and the percentages named.
 *
 * THE ADVERTISING API IS NOT CONNECTED, and this is built anyway -- with the
 * shape drawn from a sample series and every figure marked as such, so the
 * panel exists and is judgeable now and fills with real numbers the moment
 * ads_daily has rows. The one thing it must never do is show a plausible
 * split as though it were measured: an organic/paid ratio drives what you
 * spend, and a made-up one is worse than a blank panel.
 */
function salesDrawOrgPpc(ser){
  const host = document.getElementById("sales_orgppc");
  if(!host || typeof salesCombo !== "function") return;
  const cols = (ser && ser.columns) || [];
  const by = {};
  ((ser && ser.metrics) || []).forEach(function(m){ by[m.key] = m.cells || []; });

  const total = by["ordered_sales"] || by["net_revenue"] || [];
  // ad_sales is what the Advertising API would give. Absent today.
  const adSales = by["ad_sales"] || [];
  const haveAds = adSales.some(function(v){
    return v !== null && v !== undefined && Number(v) !== 0; });

  let organic, ppc, sample = false, note = "";
  if(haveAds){
    ppc = adSales.slice();
    organic = total.map(function(t, i){
      const a = Number(adSales[i] || 0);
      if(t === null || t === undefined) return null;
      // Attributed sales cannot exceed the total; if they do, the two feeds
      // disagree and the honest answer is zero organic, not a negative.
      return Math.max(0, Number(t) - a);
    });
  } else {
    // The SHAPE, from this account's own real sales, split on a fixed ratio so
    // the panel is not a straight line. Marked, never presented as measured.
    sample = true;
    const base = total.length ? total : cols.map(function(){ return null; });
    organic = base.map(function(v){ return v === null || v === undefined ? null : Number(v) * 0.7; });
    ppc     = base.map(function(v){ return v === null || v === undefined ? null : Number(v) * 0.3; });
    note = '<div class="ri-samplebar" style="margin:0 0 12px">'
      + '<b>This split is a placeholder, not your data.</b> It divides your real '
      + 'sales 70/30 purely to show the shape. The real split needs the '
      + 'Advertising API, which this account is not connected to — until then '
      + 'nothing here is measured, and the app will not guess at a ratio that '
      + 'decides what you spend.</div>';
  }

  const sum = function(a){ return a.reduce(function(x, v){ return x + (Number(v) || 0); }, 0); };
  const o = sum(organic), p = sum(ppc), t = o + p;
  const oPct = t ? Math.round((o / t) * 100) : 0;
  const pPct = t ? (100 - oPct) : 0;

  // The share bar Orbit puts above the chart.
  const bar = '<div style="display:flex;height:8px;border-radius:4px;overflow:hidden;'
    + 'background:var(--panel2);margin:0 0 6px">'
    + '<div style="width:' + oPct + '%;background:#10b981"></div>'
    + '<div style="width:' + pPct + '%;background:#8b5cf6"></div></div>'
    + '<div style="display:flex;gap:16px;font-size:12px;margin:0 0 10px"'
    + (sample ? ' class="ri-sample"' : '') + '>'
    + '<span><span style="display:inline-block;width:9px;height:9px;border-radius:2px;'
    + 'background:#10b981;margin-right:6px"></span>Organic <b>' + oPct + '%</b>'
    + ' <span class="cc">' + _sShort(o, "money", ser && ser.currency) + '</span></span>'
    + '<span><span style="display:inline-block;width:9px;height:9px;border-radius:2px;'
    + 'background:#8b5cf6;margin-right:6px"></span>PPC <b>' + pPct + '%</b>'
    + ' <span class="cc">' + _sShort(p, "money", ser && ser.currency) + '</span></span>'
    + '</div>';

  if(!cols.length || !t){
    host.innerHTML = note
      + '<div class="cc" style="font-size:12px;padding:12px 0">'
      + 'No sales in this period to split.</div>';
    return;
  }

  // Measured: Orbit's Organic vs PPC panel is 1365 x 380, taller than its Sales
  // Report because the two areas overlap and need the room to stay readable.
  const chart = salesCombo({
    id: "orgppc", columns: cols, bars: null, currency: (ser && ser.currency),
    lines: [{key: "organic", values: organic}, {key: "ppc", values: ppc}],
    width: scChartWidth("sales_orgppc", 1365), height: 380,
  });
  host.innerHTML = note + bar
    + (sample ? '<div class="ri-sample">' + chart + '</div>' : chart);
  // This one is always below the fold, which is exactly what the hold is for.
  if(typeof altaChartsInView === "function") altaChartsInView(host);
}

function salesDrawRange(sum, av){
  const el=document.getElementById("sales_range");
  if(!el) return;
  if(!sum || !sum.ok){ el.textContent=""; return; }
  const a=(av&&av.sales)||{};
  let t = sum.start+" to "+sum.end;
  if(a.last_date) t += " · Amazon has data to "+a.last_date;
  // AND WHERE IT STARTS, when you have asked for more than there is.
  //
  // Reported as "the sales report and p&l heatmap do not show data beyond 27th
  // july no matter if i select 30 day, 60d or 90d". Nestwell Goods has nothing
  // before 27 July -- checked against Amazon, which returns a genuine zero for
  // 10 July -- so 30, 60 and 90 days really are the same figures. The screen
  // said none of that: it drew the extra weeks as empty columns, which reads
  // as the app failing to load them rather than as an account that was not
  // trading yet.
  // Short, for the same reason as the grid's own note: the figures say it.
  if(a.first_date && sum.start && sum.start < a.first_date){
    t += " · trading from " + a.first_date;
  }
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
    // _sScope(), not _sQuery(): "today so far" is today whatever period is set.
    const j=await _sFetch("/sales/today?"+_sScope());
    if(j === null) return;   // the workspace moved on while this was in flight
    // NOT BLANKED. See _sCardError: measured on sheelady_us, this call answers
    // 502 because Amazon refuses the account's app the Orders data, and the
    // card simply disappeared -- which reads as "no sales today" rather than
    // "Amazon would not tell us".
    if(!j || !j.ok){ _sCardError(el, (j && j.error) || "", "Live Sales"); return; }
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
    el.innerHTML = '<div class="todaystrip">'
      + bit("revenue", t.revenue, "money", "revenue")
      + bit("orders", t.orders, "count", "orders")
      + bit("units", t.units, "count", "units")
      + '<span class="cc todaynote">live from orders'
      + (y ? ' · vs '+_sEsc(j.compared_to||"the same time yesterday") : "")
      + _sEsc(extra) + '</span></div>'
      + '<div id="sales_hourly"></div>';
    // The curve underneath, which is the shape Orbit's Live Sales card is.
    salesLoadHourly().catch(function(){});
  }catch(e){ _sCardError(el, String(e), "Live Sales"); }
}

/* A CARD THAT COULD NOT LOAD SAYS SO.
 *
 * Found by driving the live app: /sales/today answers 502 on sheelady_us,
 * because Amazon refuses it -- "Unauthorized: Access to requested resource is
 * denied", which is an SP-API role the app registration has not been granted.
 * The three UK accounts answer 200 on the same call, so it is that account's
 * authorisation and not this code.
 *
 * What the screen did with that was blank the card. An empty region reads as a
 * design that forgot something, or as "no sales", and neither is true -- the
 * figure was refused, which is a different fact and the only one that tells you
 * what to go and fix.
 *
 * Amazon's own words are shown, because the fix is in Seller Central and the
 * message is what identifies which permission is missing.
 */
function _sCardError(el, err, what){
  if(!el) return;
  const raw = String(err || "").trim();
  const denied = /unauthor|forbidden|access to requested resource/i.test(raw);
  // A QUOTA REFUSAL IS NOT A FAULT, and showing Amazon's raw dict for it --
  // "[{'code': 'QuotaExceeded', ...}]" -- reads as something broken. Amazon
  // limits how often it will answer; the figures are fine and the next attempt
  // will get them. Said in those words, because "the request failed" beside a
  // machine error is the most alarming way to describe waiting.
  const throttled = /quotaexceeded|throttl|too many requests|429/i.test(raw);
  el.innerHTML = '<div class="ri-samplebar" style="margin:0">'
    + '<b>' + _sEsc(what) + (throttled ? ' is waiting on Amazon.' : ' could not be loaded.') + '</b> '
    + (throttled
        ? 'Amazon limits how often it will answer this, and that limit has been '
          + 'reached for the moment. Nothing is wrong with your figures — this '
          + 'card fills itself in as soon as Amazon allows, usually within a '
          + 'minute or two.'
        : denied
        ? 'Amazon refused the request: this account\'s Amazon app is not '
          + 'authorised for the data this card needs. Re-authorise it in Seller '
          + 'Central with the role that covers it, then reload.'
        : 'The request failed.')
    // Amazon's own words are kept for the cases where they help someone act.
    // On a quota refusal they do not: the message is machine noise and the
    // advice above is the whole of what can be done.
    + ((raw && !throttled)
        ? '<div class="cc" style="margin-top:6px;font-size:11px;'
          + 'font-family:ui-monospace,monospace">' + _sEsc(raw.slice(0, 220))
          + '</div>' : "")
    + '</div>';
}

/* THE CHANGE BADGE -- "↑ 16.9 %" -- built in ONE place.
 *
 * Rule 12: this was written out three times, on the Live Sales card, on the Week
 * to Date card and on every stat card, and the three had already drifted -- two
 * of them put no space before the % and the third added a sign the others did
 * not. Orbit's is one component and reads the same everywhere.
 *
 * MEASURED off Orbit's own badges: "↑ 16.9 %" and "↓ 0.4 %" -- a space after the
 * arrow AND a space before the per-cent sign, at 12px weight 500.
 *
 * `sign` is for the stat cards, which show "↑ +5.2 %" against a named previous
 * figure; the two top cards show the arrow alone. `zero` is the flat case, which
 * gets an arrow that means neither up nor down rather than an up-arrow on a
 * change of nothing.
 */
function _sBadge(pct, opts){
  const o = opts || {};
  if(pct === null || pct === undefined || !isFinite(Number(pct))) return "";
  const n = Number(pct);
  const flat = (n === 0);
  const up = n > 0;
  const cls = flat ? "flat" : (up ? "up" : "down");
  const arrow = flat ? "→" : (up ? "↑" : "↓");
  const sign = (!o.sign || flat) ? "" : (up ? "+" : "−");
  return '<span class="pct-badge ' + cls + '"'
       + (o.title ? ' title="' + _sEsc(o.title) + '"' : "")
       + '>' + arrow + " " + sign + Math.abs(n).toFixed(1) + " %</span>";
}

/* "Pacific Time (PDT) · 7:20 PM" -- the marketplace's zone in words and its own
 * current time, which is what Orbit shows on the Live Sales header.
 *
 * Both come from Intl, so the zone name is whatever the browser calls it rather
 * than a table this app would have to keep. If the zone is one Intl does not
 * know, the identifier itself is shown: a name that is merely unfriendly beats
 * a card that silently drops which day it is talking about. */
function _sClock(tz){
  if(!tz) return "";
  const now = new Date();
  // en-US for the ZONE NAME, because that is the only locale that gives the
  // abbreviation Orbit shows: en-GB renders America/Los_Angeles as "GMT-7" where
  // en-US renders it "PDT". The TIME below stays on the app's own locale.
  const zone = function(style){
    try{
      const p = new Intl.DateTimeFormat("en-US", {timeZone: tz, timeZoneName: style})
        .formatToParts(now).filter(function(x){ return x.type === "timeZoneName"; });
      return p.length ? p[0].value : "";
    }catch(e){ return ""; }
  };
  // ORBIT'S EXACT FORM, read off its live header: "Pacific Time (PDT) • 7:20 PM"
  // -- the generic name, the current abbreviation in brackets, a middle dot, the
  // time. Ours was "Pacific Time: 5:17 PM", which is the same fact punctuated
  // differently.
  //
  // The brackets are dropped when they would only repeat the name, and the whole
  // thing falls back to the abbreviation when the generic name is long: "United
  // Kingdom Time (GMT+1)" is 27 characters and pushes the change badge onto a
  // second line, and a header that reflows is worse than an abbreviation.
  const generic = zone("longGeneric");
  const shortz = zone("short");
  let name = generic;
  if(name && shortz && shortz !== name && !/^GMT/.test(shortz)) name += " (" + shortz + ")";
  if(!name || name.length > 20) name = shortz || generic || tz;
  let time = "";
  try{
    time = new Intl.DateTimeFormat("en-GB", {timeZone: tz, hour: "numeric",
      minute: "2-digit", hour12: true}).format(now).toUpperCase();
  }catch(e){ return _sEsc(name); }
  return '<span class="cc">' + _sEsc(name) + ' &middot; </span>' + _sEsc(time);
}

/* ---- the hourly curve --------------------------------------------------
 * Orbit's Live Sales card: today climbing across the day in gold, yesterday
 * running the full 24 hours behind it in grey dashes, so "am I ahead of
 * yesterday" is answered by which line is higher at the same hour.
 *
 * Built from order timestamps, which the app already pulls -- see
 * domain/hourly_sales.py for why this is a different measurement from
 * everything on the settled report below, and why the card says so.
 */
async function salesLoadHourly(){
  const el = document.getElementById("sales_hourly");
  const badge = document.getElementById("sales_today_delta");
  if(!el) return;
  let j;
  try{
    // _sScope(), not _sQuery(): the curve is always today against yesterday.
    j = await _sFetch("/sales/hourly?" + _sScope());
    if(j === null) return;
  }catch(e){ return; }
  if(!j || !j.ok || !(j.hours || []).length) return;

  // Midnight, 3am, 6am … as Orbit labels them, rather than 00:00..23:00.
  const label = function(h){
    const n = Number(String(h).slice(0, 2));
    const ampm = n < 12 ? "AM" : "PM";
    const hh = (n % 12) === 0 ? 12 : (n % 12);
    return hh + " " + ampm;
  };
  const pts = (j.hours || []).map(function(h, i){
    return {label: label(h), value: (j.today || [])[i]};
  });
  const cmp = (j.yesterday || []).map(function(v, i){
    return {label: label((j.hours || [])[i]), value: v};
  });

  // The strip along the bottom of Orbit's card is AD SPEND TODAY and TACOS.
  // Both come from the Advertising API, which is not connected -- ads_daily is
  // empty. Said out loud, in the place the figures would sit, rather than
  // leaving a gap that looks like a design that forgot something.
  // Measured: 10px uppercase label with 0.4px tracking, the value beside it at
  // 12px, 4px between, 8px above with a 4px lead-in. Orbit puts figures here;
  // we say what is missing and why, in the same shape.
  const adsFoot = '<div class="adfooter">'
    + '<span class="lbl">Ad spend today</span> <b>not connected</b>'
    + '<span class="lbl" style="margin-left:8px">Tacos</span> <b>not connected</b>'
    + '<span style="color:rgb(156,163,175)"> — both need the Advertising API, '
    + 'which this account is not connected to.</span></div>';

  // A POINT SCALE here, not a band: these are readings across a continuous day,
  // and midnight IS the start of the axis. Measured on Orbit's Live Sales: 24
  // hourly points from x=65 (on the y-axis) to x=645 (the right edge), labelled
  // every third hour.
  const hrOpts = {
    title: "", kind: "money", color: "#fbbf24", id: "sales_hourly_chart",
    currency: (j && j.currency),
    width: scChartWidth("sales_hourly", 665),
    height: 200, compare: cmp, scale: "point",
    compact: true, thisLabel: "Today", compareLabel: "Yesterday"};
  SALES._hourlyDraw = function(){
    hrOpts.width = scChartWidth("sales_hourly", 665);
    el.innerHTML = salesChart(pts, hrOpts) + adsFoot;
  };
  el.innerHTML = salesChart(pts, hrOpts) + adsFoot;

  const hkey = document.getElementById("sales_today_key");
  if(hkey) hkey.innerHTML = salesChartKey(hrOpts);

  // WHICH CLOCK "today" IS ON, in the header where Orbit puts it -- measured:
  // "Pacific Time (PDT): 5:14 PM", the zone named in words and the marketplace's
  // own current time beside it. Ours had the IANA identifier in a subtitle under
  // the chart, which is the same fact written for a machine.
  //
  // It matters more here than it does for Orbit: this app is run from Pakistan
  // against UK and US stores, so "today so far" is three different days
  // depending on which account is open.
  const clock = document.getElementById("sales_today_clock");
  if(clock) clock.innerHTML = _sClock(j.timezone);
  const hnote = document.getElementById("sales_today_note");
  if(hnote) hnote.textContent = "";

  // Against the SAME HOUR yesterday, never yesterday's full day -- otherwise
  // every morning shows a collapse and every evening a recovery.
  if(badge){
    const a = Number(j.today_total || 0), b = Number(j.yesterday_so_far || 0);
    if(!b){ badge.innerHTML = ""; }
    else badge.innerHTML = _sBadge(((a - b) / Math.abs(b)) * 100,
      {title: "against the same time yesterday"});
  }
}

/* ---- redraw when the window changes size --------------------------------
 *
 * A chart drawn at the container's pixel width has to be redrawn when that width
 * changes. Without this, turning a phone sideways or dragging a window wider
 * letterboxes every chart -- the viewBox is honest about its aspect ratio, so it
 * centres itself in the new box rather than filling it.
 *
 * Nothing is re-fetched. Each renderer left behind a closure over the data it
 * already had, so this is a redraw and not a reload: no request, no spinner, and
 * the figures on screen cannot change just because the window did.
 *
 * Debounced, because a drag fires resize continuously and redrawing four charts
 * per frame is how a resize comes to feel like the app has locked up. 150ms is
 * after the drag stops, not during it.
 */
let _sResizeTimer = null;
let _sLastW = 0;
function salesOnResize(){
  clearTimeout(_sResizeTimer);
  _sResizeTimer = setTimeout(function(){
    const w = window.innerWidth || 0;
    // Only when the width ACTUALLY changed. Mobile browsers fire resize when the
    // address bar hides, which changes the height and nothing else -- redrawing
    // there would make the page flicker as you scroll.
    if(w === _sLastW) return;
    _sLastW = w;
    try{ if(SALES._hourlyDraw) SALES._hourlyDraw(); }catch(e){}
    try{ if(SALES._weekDraw) SALES._weekDraw(); }catch(e){}
    try{ if(SALES.series){ salesDrawCharts(SALES.series); salesDrawOrgPpc(SALES.series); } }catch(e){}
  }, 150);
}
if(typeof window !== "undefined" && window.addEventListener){
  _sLastW = window.innerWidth || 0;
  window.addEventListener("resize", salesOnResize);
}

/* The Profit card, on the SAME basis as the sales beside it.
 *
 * This is the card that read "£80" next to "Total Sales £0". Both were right and
 * they were about different trades: Amazon dates sales by when the order was
 * PLACED and profit by when the MONEY MOVED, so a window whose orders have not
 * settled showed this week's sales beside last month's profit.
 *
 * The order-dated figure is preferred, worked out from the owner's own cost
 * prices -- revenue, less VAT where the company is registered, less Amazon's fee
 * at the rate this account actually pays, less what the stock cost and what was
 * spent getting it out. Amazon has no answer on this basis; the owner does.
 *
 * It is never shown as if it were Amazon's own figure. Where costs are missing
 * the number is knowingly too high, and the card says so rather than hiding it.
 */
function _sProfitCard(sum, byKey){
  const est = sum && sum.order_profit;
  const settled = byKey["profit"] || {key: "profit", kind: "money", value: null};

  if(!est || est.profit === null || est.profit === undefined){
    // Nothing costed at all -- fall back to the settled figure, but say which
    // days it is really about so it cannot be read as this week's.
    return Object.assign({}, settled, {
      label: "Profit",
      note: (est && est.error) ? "" : "on settled orders — a different set of days",
    });
  }

  // TWO DIFFERENT WAYS THIS FIGURE CAN BE INCOMPLETE, and they are not the same
  // thing: some UNITS have no cost (the figure is too high), or some ORDERS of
  // the period have not been fetched at all (the figure is about less than the
  // period). Both are warnings and both are shown; neither is left to be
  // guessed at from a number on its own.
  const warns = [];
  if(est.coverage_note) warns.push(est.coverage_note);
  if(est.warning) warns.push(est.warning);
  return {
    key: "profit", kind: "money", label: "Profit",
    value: est.profit,
    previous: null, delta_pct: null,
    note: warns.length ? warns.join(" ") : (est.note || ""),
    warn: warns.length > 0,
    detail: est,
  };
}

/* The full working, on hover. Every number that went into the profit, so a
 * figure nobody expected can be taken apart rather than argued with. */
function _sProfitTip(c){
  const d = c && c.detail;
  if(!d) return "Revenue after Amazon's fees and what the stock cost.";
  const L = [];
  L.push("revenue " + _sNum(d.revenue, "money"));
  if(d.goods !== undefined)
    L.push("  = goods " + _sNum(d.goods, "money")
           + " + postage the buyer paid " + _sNum(d.postage, "money"));
  if(d.vat) L.push("less VAT " + _sNum(d.vat, "money") + " (HMRC's, not yours)");
  L.push("less Amazon fees " + _sNum(d.fees, "money") + " — " + (d.rate_detail || ""));
  L.push("less stock cost " + _sNum(d.cogs, "money")
         + " (" + d.costed_units + " of " + d.units + " units costed)");
  if(d.charges)
    L.push("less your charges " + _sNum(d.charges, "money")
           + (d.charge_parts && d.charge_parts.length
              ? " — " + d.charge_parts.map(function(p){
                  return p.label + " " + _sNum(p.amount, "money"); }).join(", ")
              : ""));
  L.push(d.ads_connected
         ? "less ad spend " + _sNum(d.ad_spend, "money")
         : "ad spend NOT subtracted — Advertising is not connected");
  L.push("= " + _sNum(d.profit, "money")
         + (d.margin_pct !== null && d.margin_pct !== undefined
            ? "  (" + d.margin_pct + "% margin)" : ""));
  return L.join("\n");
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
  // ORBIT'S FIVE, IN ITS ORDER AND ITS WORDS: Total Sales, Daily Average,
  // Total Orders, Total Units, Profit. Ours had ten in a different order with
  // different names, so the two screens did not even begin the same way.
  //
  // The rest are not thrown away -- they are every one of them a row in the
  // grid below, per day, in full. What changes is which five are given the top
  // of the screen.
  //
  // Daily Average is not a figure Amazon sends; it is revenue over the number
  // of days in the range, worked out here. It is on the same basis as the
  // revenue it comes from, so it cannot disagree with the card beside it.
  const _byKey = {};
  (sum.cards || []).forEach(function(c){ _byKey[c.key] = c; });
  // THE DAYS THE REPORT HAS NOT SENT, added from the live order feed -- the same
  // days, from the same source, that the chart below is already drawing. Without
  // this a week whose only trade was yesterday reads "0 orders, £0" on the cards
  // while the chart beside them shows three, which is worse than either being
  // late. See _sLiveAdd: a day Amazon HAS reported is never touched, even when
  // it reported a zero.
  ["ordered_sales", "orders", "units"].forEach(function(k){
    const add = _sLiveAdd(k);
    if(!add) return;
    const c = _byKey[k] || (_byKey[k] = {key: k, value: 0,
                                         kind: (k === "ordered_sales" ? "money" : "count")});
    c.value = (Number(c.value) || 0) + add;
    c.live_added = add;
  });
  const _days = (function(){
    try{
      const a = new Date(sum.start + "T00:00:00Z"), b = new Date(sum.end + "T00:00:00Z");
      const n = Math.round((b - a) / 86400000) + 1;
      return (n > 0 && n < 1000) ? n : 0;
    }catch(e){ return 0; }
  })();
  let _rev = _byKey["ordered_sales"] || _byKey["net_revenue"];

  // THE POSTAGE IS ALREADY IN THE STORED FIGURE, so it is NOT added here.
  //
  // It used to be: the report's ordered_sales is the goods alone, and the
  // postage was only known per order, so the browser added it on. Since
  // domain/live_reconcile.py started writing the live orders into sales_daily
  // -- postage included, because that is the owner's definition of revenue --
  // adding it again counted it twice. Measured on jack_uk: the card read 114
  // against a true 102.21, over by exactly the 12.24 of postage.
  //
  // One place decides what revenue means, and it is the store. The split is
  // still shown on hover, from order_profit, because the goods figure alone is
  // what reconciles against Seller Central.
  const _op = sum.order_profit;
  if(_op && _op.postage > 0 && _rev) {
    _rev = Object.assign({}, _rev, {goods: _op.goods, postage: _op.postage});
  }

  const ORBIT_CARDS = [
    Object.assign({}, _rev || {}, {label: "Total Sales"}),
    (_rev && _days && _rev.value !== null && _rev.value !== undefined)
      ? {key: "daily_avg", kind: "money", label: "Daily Average",
         value: Number(_rev.value) / _days,
         previous: (_rev.previous === null || _rev.previous === undefined)
                   ? null : Number(_rev.previous) / _days,
         delta_pct: _rev.delta_pct}
      : {key: "daily_avg", kind: "money", label: "Daily Average",
         value: null, previous: null, delta_pct: null},
    Object.assign({}, _byKey["orders"] || {key: "orders", kind: "count", value: null},
                  {label: "Total Orders"}),
    Object.assign({}, _byKey["units"] || {key: "units", kind: "count", value: null},
                  {label: "Total Units"}),
    _sProfitCard(sum, _byKey),
  ];

  host.innerHTML = ORBIT_CARDS.map(function(c){
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
    // WHAT THIS FIGURE IS, under the figure. A profit worked out from the
    // owner's own costs is not the same claim as one Amazon has settled, and a
    // profit with uncosted units in it is knowingly too high -- neither can be
    // left to be inferred from a number on its own.
    const foot = c.note
      ? '<p class="stat-delta" style="white-space:normal;line-height:1.35'
        + (c.warn ? ';color:var(--warn)' : '') + '">'
        + (c.warn ? '<i class="ti ti-alert-triangle"></i> ' : '')
        + _sEsc(c.note) + '</p>'
      : (adsOff
          ? '<p class="stat-delta" title="'+_sEsc(sum.ads_note||"")+'">not connected</p>'
          // "LY :" is Orbit's own wording, with the space. `previous` is what
          // the server calls the earlier figure -- it was read as `prev_value`,
          // which does not exist, so every card said only a percentage with
          // nothing to compare it against.
          : _sDelta(c, (SALES.compareKind === "year" ? "LY" : "was"),
                    c.previous, c.kind, sum.currency));
    // Where postage has been folded into Total Sales, say so on hover -- the
    // goods figure alone is what reconciles against Seller Central, and someone
    // checking the two must be able to find it.
    const salesTip = (c.postage
      ? "goods " + _sNum(c.goods, "money", sum.currency)
        + " + postage the buyer paid " + _sNum(c.postage, "money", sum.currency)
        + "\nAmazon's own 'Ordered product sales' is the goods figure alone."
      : "");
    return '<div class="stat-card'+(missing?" is-empty":"")+'"'
      + (isProfit ? ' title="'+_sEsc(_sProfitTip(c))+'"'
                  : (salesTip ? ' title="'+_sEsc(salesTip)+'"' : ''))
      + '>'
      + '<p class="stat-label">'+_sEsc(c.label)+'</p>'
      + '<p class="stat-number" style="'+col.replace(/^;/,"")+'">'
      + _sEsc(_sShort(c.value, c.kind, sum.currency))+'</p>'
      + foot
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
    //
    // BUT THERE ARE TWO REASONS FOR NO PERCENTAGE, and they are not the same
    // fact. Reported as "no earlier period" on every card of a week that had a
    // perfectly ordinary week before it:
    //
    //   the period before had NOTHING     -- a real figure, and a rise from
    //                                        zero has no percentage
    //   there IS no period before         -- the account has no data that far
    //                                        back at all
    //
    // A rise from zero is the more common of the two and the more interesting,
    // and calling it "no earlier period" says the app cannot see history when
    // it can.
    const had = (prevValue !== null && prevValue !== undefined);
    return '<p class="stat-delta">'
         + (had ? (_sEsc(prevLabel || "was") + " : "
                   + _sEsc(_sShort(prevValue, kind, currency))
                   + " — no % from zero")
                : "no earlier period")
         + '</p>';
  }
  const up = c.delta_pct >= 0;
  // AD SPEND RISING IS NOT A WIN, so direction and goodness are separate things:
  // the arrow still points up, the colour goes the other way. _sBadge draws the
  // arrow from the number, so the colour is corrected here afterwards -- the one
  // case on the screen where the two disagree.
  const good = (c.key === "spend") ? !up : up;
  // "LY : $551,866.01" -- Orbit's spacing, measured off its own cards.
  const was = (prevValue===null || prevValue===undefined)
    ? "" : (prevLabel||"was") + " : " + _sShort(prevValue, kind, currency) + " ";
  let badge = _sBadge(c.delta_pct, {sign: true,
    title: (up ? "up" : "down") + " versus "
         + (prevLabel === "LY" ? "the same period last year" : "the period before")});
  if(c.delta_pct !== 0 && good !== up){
    badge = badge.replace('pct-badge ' + (up ? "up" : "down"),
                          'pct-badge ' + (good ? "up" : "down"));
  }
  return '<p class="stat-delta">' + _sEsc(was) + badge + '</p>';
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
  // ORBIT'S TITLE FOR THIS TABLE, and its description. The grid had neither, so
  // the most information-dense thing on the page arrived unannounced -- and the
  // colour in it needs saying, because a heatmap whose scale is not explained
  // is just decoration.
  let h='<div class="panelhead" style="margin:0 0 12px;padding:0"><div>'
      + '<p class="paneltitle">P&amp;L Heatmap</p>'
      // Orbit's own line, word for word and at its own 10px rather than the
      // 12px the other panel subtitles use -- measured: its P&L Heatmap
      // subtitle is smaller than its Live Sales one. "coloring" is Orbit's
      // spelling and this is a match to Orbit, not to the rest of the app.
      + '<p class="panelsub" style="font-size:10px">Performance metrics with '
      + 'heatmap coloring across '
      // The colour's meaning belongs HERE, on the hover, not as prose on the
      // page. Orbit does the same: a short line, an i, and the explanation only
      // if you ask for it.
      + 'time periods<span class="infodot" title="Colour = effect on PROFIT, '
      + 'against the previous column.&#10;&#10;'
      + 'Green is always good, red is always bad. Sales, orders and units going '
      + 'up is green. Fees, refunds, ad spend and cost of goods going up is RED '
      + '— the number rose but the profit fell.&#10;&#10;'
      + 'Depth = size of the change: under 1% is left plain, 20% or more is '
      + 'solid. It is a percentage, so it is per row — a dark red in fees is not '
      + 'the same pounds as a dark red in sales.&#10;&#10;'
      + 'A loss is red whatever the change was. Hover any cell for its figure '
      + 'and the change behind the colour.">i</span></p>'
      + '</div></div>'
      + _sGridTools(ser)
      + '<div class="salesgridwrap"><table class="salesgrid"><thead><tr>'
      + '<th class="mcol">Metric</th>'
      + cols.map(function(c){ return '<th>'+_sEsc(_sColLabel(c, ser.granularity))+'</th>'; }).join("")
      + '</tr></thead><tbody>';

  // ONE ROW, drawn the same way wherever it appears.
  const byKey = {};
  (ser.metrics||[]).forEach(function(m){ byKey[m.key] = m; });

  // A DAY WITH NO SALE SHOWS ZERO, NOT A DASH.
  //
  // "the zeros written also indicates no sales was made so it is right thing."
  //
  // An em-dash means "not known" everywhere in this grid, and for most rows
  // that is exactly right -- Amazon settles fees days later, so a blank fee
  // cell genuinely means "not told yet". But for what was ORDERED, absence is
  // an answer: the order feed is read continuously, so a day it holds no order
  // for is a day that took no orders. Printing a dash there asks the reader to
  // wonder whether the app failed to load it.
  //
  // Only these four, and only inside the period Amazon has actually reported
  // on. Outside it nothing has been checked, and a zero there would be the app
  // asserting something it has not looked at -- which is the fault that put
  // fifteen months of invented zeros in the store in the first place.
  const ORDERED = ["ordered_sales", "orders", "units", "order_items"];
  const _avail = (SALES.avail && SALES.avail.sales) || {};
  const knownFrom = _avail.first_date || "";
  const knownTo = _avail.last_date || "";
  const zeroable = function(key, i){
    if(ORDERED.indexOf(key) < 0) return false;
    const d = cols[i];
    if(!d || !knownFrom || !knownTo) return false;
    return d >= knownFrom && d <= knownTo;
  };

  const drawRow = function(m){
    // The value each cell is compared against: the previous column. Worked out
    // once for the row, so a cell whose own neighbour is blank still compares
    // against the last figure there actually was rather than against nothing.
    const shownAt = m.cells.map(function(v, i){
      const blank = (v === null || v === undefined);
      return (blank && zeroable(m.key, i)) ? 0 : v;
    });
    return '<tr><th class="mcol" title="'+_sEsc(m.label)+'">'+_sEsc(m.label)+'</th>'
       + shownAt.map(function(shown, i){
           const blank = (m.cells[i] === null || m.cells[i] === undefined);
           const prev = (i > 0) ? shownAt[i - 1] : null;
           const t = _sTint(shown, prev, m.key, m.good);
           const txt = _sNum(shown, m.kind, ser.currency);
           // WHAT DROVE THE COLOUR, on hover. A shade you cannot interrogate is
           // a shade you end up ignoring.
           const d = _sDeltaPct(shown, prev);
           let tip = m.label + ": " + txt;
           if(blank && shown === 0) tip += " — no orders that day";
           if(d !== null && prev !== null && prev !== undefined){
             const sign = d > 0 ? "+" : "";
             tip += "\n" + sign + d.toFixed(1) + "% vs "
                  + _sColLabel(cols[i - 1], ser.granularity)
                  + " (" + _sNum(prev, m.kind, ser.currency) + ")";
             if(Math.abs(d) < 1) tip += " — flat";
             else tip += (t.indexOf("45,212,168") >= 0)
                       ? " — better for profit" : " — worse for profit";
           }
           return '<td'+(t?' style="background:'+t+'"':'')
                + ' title="'+_sEsc(tip)+'">'+_sEsc(txt)+'</td>';
         }).join("")
       + '</tr>';
  };

  // BANDED INTO SECTIONS, as Orbit's is.
  //
  // "the p&l heatmap has spacing in it to separate data and make it easy to
  // understand visually". Measured on Orbit: its grid is six sections, each
  // introduced by a header row -- SALES & REVENUE, ORGANIC, PPC, COSTS &
  // DEDUCTIONS, TRAFFIC, DERIVED -- 24px tall on rgb(45,50,66) against 29px
  // transparent for a data row.
  //
  // That banding is the difference between a grid you can scan and a wall of
  // numbers: "is my advertising working" becomes four adjacent rows instead of
  // four rows scattered through thirty-eight.
  //
  // The sections come from the SERVER, next to where the metrics themselves are
  // defined, so the order cannot drift from the order the metrics are sent in.
  // An older answer with no `sections` still draws -- as one flat list, exactly
  // as before.
  // Rows the Metrics picker has switched off. A section whose every row is
  // hidden loses its heading too -- a band with nothing under it is furniture.
  const hidden = SALES.gridHidden || [];
  const visible = function(k){ return byKey[k] && hidden.indexOf(k) < 0; };
  const sections = (ser.sections || []).filter(function(s){
    return (s.keys || []).some(visible);
  });
  if(sections.length){
    sections.forEach(function(s){
      h += '<tr class="gsec"><th class="mcol">' + _sEsc(s.name) + '</th>'
         + '<td colspan="' + cols.length + '"></td></tr>';
      (s.keys || []).forEach(function(k){ if(visible(k)) h += drawRow(byKey[k]); });
    });
  } else {
    (ser.metrics||[]).forEach(function(m){ if(visible(m.key)) h += drawRow(m); });
  }
  // Every row switched off is not an empty grid with no explanation.
  if(!(ser.metrics||[]).some(function(m){ return visible(m.key); })){
    h += '<tr><th class="mcol">—</th><td colspan="' + cols.length + '" '
      + 'style="text-align:left;color:var(--muted)">Every row is switched off. '
      + 'Use <b>Metrics</b> above to bring some back.</td></tr>';
  }
  h+='</tbody></table></div>';
  host.innerHTML=h;
}

/* ---- the heatmap's own toolbar -----------------------------------------
 *
 * MEASURED on Orbit's P&L Heatmap, control by control:
 *
 *   "33/33 Metrics"   10px/500, transparent, radius 6, padding 4px 12px
 *   PRODUCTS          11px/600 uppercase label, rgb(156,163,175)
 *   All Products (166)  13px/400 on rgb(45,50,66), radius 8, padding 7px 12px
 *   GRANULARITY       Day | Week | Month -- 10px, the active one 600 on
 *                     #fbbf24, radius 4, padding 4px 10px
 *   Last: 8/13
 *   PERIOD            7d | 14d | 30d | 60d | 90d | Custom, same pill styling
 *   Export            10px/500, radius 6
 *
 * and under them a COGS strip: "COGS  Actual · $22.36 avg/unit ·
 * 99.7% of shipped units covered  Change setting →".
 *
 * Ours says "of SKUs costed" rather than "of shipped units covered", because
 * that is what this app actually knows -- domain/cogs.py counts SKUs with a
 * cost against SKUs without one. Borrowing Orbit's wording for a different
 * measurement would be a wrong number with a right-sounding label.
 */
const _S_GRANS = [["day", "Day"], ["week", "Week"], ["month", "Month"]];
const _S_GRID_PERIODS = [["7d", "7d"], ["14d", "14d"], ["30d", "30d"],
                         ["60d", "60d"], ["90d", "90d"]];

function _sPills(items, current, fn){
  return '<span class="gpills">' + items.map(function(p){
    const on = (p[0] === current);
    return '<button class="gpill' + (on ? " on" : "") + '"'
         + ' onclick="' + fn + '(' + jsArg(p[0]) + ')">' + _sEsc(p[1]) + '</button>';
  }).join("") + '</span>';
}

function _sGridTools(ser){
  const hidden = SALES.gridHidden || [];
  const all = (ser.metrics || []).length;
  const shown = (ser.metrics || []).filter(function(m){
    return hidden.indexOf(m.key) < 0; }).length;
  // Which period and granularity the GRID is on -- its own if it has been
  // touched, otherwise the screen's, which is what it is actually drawing.
  const gran = SALES.gridGran || SALES.gran || "day";
  const period = SALES.gridPreset || SALES.preset || "30d";
  const last = (ser.columns || []).length
    ? _sColLabel((ser.columns || [])[ser.columns.length - 1], gran) : "";

  let h = '<div class="gtools">'
    + '<button class="gbtn" onclick="salesMetricsOpen(event)" '
    + 'title="Choose which rows this grid shows">'
    + shown + '/' + all + ' Metrics</button>';

  // The product filter is the SAME one the rest of the screen uses -- a second
  // one that filtered only the grid would be two answers to one question.
  const asinLabel = SALES.asin ? SALES.asin : "All products";
  h += '<span class="glbl">Products</span>'
    + '<button class="gbtn wide" onclick="salesFocusProducts()" '
    + 'title="The product filter at the top of this screen">'
    + _sEsc(asinLabel) + '</button>';

  h += '<span class="glbl">Granularity</span>'
    + _sPills(_S_GRANS, gran, "salesGridGran");
  if(last) h += '<span class="glast">Last: ' + _sEsc(last) + '</span>';

  h += '<span class="glbl">Period</span>'
    + _sPills(_S_GRID_PERIODS, period, "salesGridPeriod");
  // Says when the grid has been taken off the screen's own range, and offers
  // the way back -- otherwise the numbers here and the chart above disagree
  // with nothing on screen explaining why.
  if(SALES.gridGran || SALES.gridPreset){
    h += '<button class="gbtn" onclick="salesGridFollow()" '
      + 'title="Show the same period as the charts above">'
      + '<i class="ti ti-arrow-back-up"></i> Match the charts</button>';
  }
  h += '<span class="gspacer"></span>'
    + '<button class="gbtn" onclick="salesExport()">'
    + '<i class="ti ti-download"></i> Export</button>'
    + '</div>';

  // ---- the COGS strip ----------------------------------------------------
  const cov = (SALES.data && SALES.data.cogs_coverage) || null;
  if(cov && cov.total){
    // Average cost per unit shipped, from this grid's own figures, so it can
    // never disagree with the Cost of goods row below it.
    const sum = function(key){
      const m = (ser.metrics || []).filter(function(x){ return x.key === key; })[0];
      if(!m) return null;
      let t = 0, any = false;
      (m.cells || []).forEach(function(v){
        if(v !== null && v !== undefined){ t += Number(v); any = true; } });
      return any ? t : null;
    };
    const c = sum("cogs"), u = sum("units_shipped");
    const per = (c && u) ? (c / u) : null;
    h += '<div class="gcogs">'
      + '<span class="glbl">COGS</span>'
      + (per !== null
          ? '<b>' + _sEsc(_sNum(per, "money", ser.currency)) + '</b> avg/unit'
          : '<span class="cc">no costed units in this period</span>')
      + '<span class="gsep">·</span>'
      + '<b>' + (cov.pct === null || cov.pct === undefined ? "—" : cov.pct + "%")
      + '</b> of SKUs costed'
      + (cov.unknown
          ? '<span class="cc"> (' + cov.unknown + ' of ' + cov.total + ' have no cost, '
            + 'so profit is withheld for any period containing them)</span>' : "")
      + '<button class="glink" onclick="navTo(\'listings\')">Change setting →</button>'
      + '</div>';
  }

  // ---- where Amazon's own two answers do not agree -----------------------
  //
  // A row is meant to read across: what the buyers paid, split into the part
  // that is yours and the VAT that is not. On a few days it cannot, because
  // Amazon's Finances feed and its Orders feed disagree about those particular
  // orders -- ones refunded in full, and cross-border ones where Amazon
  // collected the VAT itself and reported a different total for the same order.
  //
  // Neither figure is wrong and neither is adjusted to fit the other. What was
  // missing was saying so: the grid showed 601.08 + 15.80 under a sales row of
  // 605.77 and left it to be noticed, which reads as a fault in the app rather
  // than as a fact about the data.
  // ---- "there is nothing here, and that is not a fault" -------------------
  //
  // THE REPORT: "the sales report and p&l heatmap do not show data beyond 27th
  // july no matter if i select 30 day, 60d or 90d", and then: "when no data is
  // available its okay but the user should be able to see that there is no
  // data available".
  //
  // Nestwell Goods has nothing before 27 July — checked against Amazon, which
  // returns a genuine zero for 10 July, so the account simply was not selling.
  // 30, 60 and 90 days really are the same figures. But the screen said none of
  // that: it drew the extra weeks as blank columns, which reads as the app
  // having failed to load them.
  //
  // An em-dash means "not known" everywhere else in this grid and still does.
  // What was missing is anybody saying WHY a run of them is there.
  //
  // KEPT SHORT ON PURPOSE. This was a paragraph, and the owner's answer was
  // "i think the note in english wont be so good" -- fair: a wall of English
  // is not what someone scanning a grid of numbers wants, and this app is read
  // by someone who does not use English first. The zeros above now carry the
  // meaning; this only has to date the edge.
  const _av = (SALES.avail && SALES.avail.sales) || {};
  if(_av.first_date && ser.start && ser.start < _av.first_date){
    h += '<div class="gcogs gnodata">'
      + '<span class="glbl">Trading from</span>'
      + '<b>' + _sEsc(_sColLabel(_av.first_date, "day")) + '</b>'
      + '<span class="infodot" title="This account has nothing before '
      + _sEsc(_av.first_date) + '. The columns before it are empty because '
      + 'there was no trade to report, not because they failed to load — so a '
      + 'longer period shows the same figures as a shorter one.">i</span>'
      + '</div>';
  }

  const tie = ser.tie_out;
  if(tie && tie.days){
    const worst = (tie.worst || []).map(function(w){
      return _sColLabel(w[0], gran) + " " + _sNum(w[1], "money", ser.currency);
    }).join(", ");
    // Label, figure, and the explanation on the hover -- not a paragraph on the
    // page. Same shape as everything else here.
    h += '<div class="gcogs gtie">'
      + '<span class="glbl">Tie-out</span>'
      + '<b>' + _sEsc(_sNum(tie.amount, "money", ser.currency)) + '</b>'
      + ' over ' + tie.days + ' day' + (tie.days === 1 ? "" : "s")
      + '<span class="infodot" title="' + _sEsc(tie.note)
      + (worst ? "\n\nLargest: " + worst + "." : "")
      + '">i</span>'
      + '</div>';
  }
  return h;
}

/* The product filter lives in the toolbar at the top of the screen. Rather than
   build a second one here -- two controls for one setting is how they come to
   disagree -- this takes you to the one that exists and makes it obvious. */
function salesFocusProducts(){
  const el = document.getElementById("sales_asin");
  if(!el) return;
  try{ el.scrollIntoView({block: "center", behavior: "smooth"}); }catch(e){}
  try{ el.focus(); }catch(e){}
  el.classList.add("flashfocus");
  setTimeout(function(){ el.classList.remove("flashfocus"); }, 1400);
}

function salesGridGran(g){
  SALES.gridGran = (g === (SALES.gran || "day") && !SALES.gridPreset) ? "" : g;
  salesLoadGrid();
}
function salesGridPeriod(p){
  SALES.gridPreset = (p === (SALES.preset || "30d") && !SALES.gridGran) ? "" : p;
  salesLoadGrid();
}
function salesGridFollow(){
  SALES.gridGran = ""; SALES.gridPreset = ""; SALES.gridSeries = null;
  if(SALES.series) salesDrawGrid(SALES.series);
}

/* Fetch the grid's OWN series, when it has been taken off the screen's range.
   Same endpoint, same shape -- only the two parameters differ, so nothing about
   how a figure is produced can drift between the chart and the grid. */
async function salesLoadGrid(){
  if(!SALES.gridGran && !SALES.gridPreset){
    SALES.gridSeries = null;
    if(SALES.series) salesDrawGrid(SALES.series);
    return;
  }
  if(SALES.gridBusy) return;
  SALES.gridBusy = true;
  const host = document.getElementById("sales_grid");
  if(host) host.style.opacity = ".45";
  try{
    const q = ["preset=" + encodeURIComponent(SALES.gridPreset || SALES.preset || "30d"),
               "granularity=" + encodeURIComponent(SALES.gridGran || SALES.gran || "day")];
    if(SALES.asin) q.push("asin=" + encodeURIComponent(SALES.asin));
    if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
      q.push("marketplace=" + encodeURIComponent(WS_MARKET));
    // NO basis HERE. The route decides it, once, for the whole screen.
    //
    // This line used to say basis=order -- and it only ran when the grid had
    // been given its OWN period, which is not the normal case. So the grid the
    // owner actually looks at borrowed SALES.series instead (see the top of
    // this function), and that was fetched without a basis and defaulted to
    // money. Hence a heatmap showing 18.32 of revenue on a day with no orders
    // and no revenue on the day that took three: the grid was on the settlement
    // calendar the whole time while claiming the order one.
    const j = await _sFetch("/sales/series?" + q.join("&"));
    if(j && j.ok){ SALES.gridSeries = j; salesDrawGrid(j); }
  }catch(e){
    // Left as it was rather than blanked: the previous grid is still true of
    // the period it was drawn for, and the toolbar says which that is.
  }finally{
    SALES.gridBusy = false;
    if(host) host.style.opacity = "";
  }
}

/* Which rows to show. Thirty-eight is a lot to scroll past when the question is
   about four of them, and Orbit puts the same control in the same place. */
function salesMetricsOpen(ev){
  if(ev) ev.stopPropagation();
  const ser = SALES.gridSeries || SALES.series;
  if(!ser || !(ser.metrics || []).length) return;
  const hidden = SALES.gridHidden || [];
  const secs = (ser.sections || []).length
    ? ser.sections
    : [{name: "Metrics", keys: (ser.metrics || []).map(function(m){ return m.key; })}];
  const by = {};
  (ser.metrics || []).forEach(function(m){ by[m.key] = m; });

  let h = '<div class="metricpick-head">Rows to show'
        + '<button class="glink" onclick="salesMetricsAll(1)">all</button>'
        + '<button class="glink" onclick="salesMetricsAll(0)">none</button></div>';
  secs.forEach(function(s){
    const keys = (s.keys || []).filter(function(k){ return by[k]; });
    if(!keys.length) return;
    h += '<div class="metricpick-sec">' + _sEsc(s.name) + '</div>';
    keys.forEach(function(k){
      h += '<label class="metricpick-row"><input type="checkbox"'
        + (hidden.indexOf(k) < 0 ? " checked" : "")
        + ' onchange="salesMetricToggle(' + jsArg(k) + ', this.checked)"> '
        + _sEsc(by[k].label) + '</label>';
    });
  });
  let box = document.getElementById("metricpick");
  if(!box){
    box = document.createElement("div");
    box.id = "metricpick";
    box.className = "metricpick";
    document.body.appendChild(box);
    document.addEventListener("click", function(e){
      if(box && !box.contains(e.target)) box.classList.remove("open");
    });
  }
  box.innerHTML = h;
  const btn = ev && ev.target && ev.target.closest ? ev.target.closest("button") : null;
  const r = btn ? btn.getBoundingClientRect() : {left: 40, bottom: 90};
  box.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 280)) + "px";
  box.style.top = (r.bottom + window.scrollY + 6) + "px";
  box.classList.add("open");
}

function _sGridSave(){
  try{ localStorage.setItem("alta_grid_hidden", JSON.stringify(SALES.gridHidden || [])); }
  catch(e){}
  const ser = SALES.gridSeries || SALES.series;
  if(ser) salesDrawGrid(ser);
}
function salesMetricToggle(key, on){
  const h = SALES.gridHidden || (SALES.gridHidden = []);
  const i = h.indexOf(key);
  if(on && i >= 0) h.splice(i, 1);
  if(!on && i < 0) h.push(key);
  _sGridSave();
}
function salesMetricsAll(on){
  const ser = SALES.gridSeries || SALES.series;
  SALES.gridHidden = on ? [] : (ser.metrics || []).map(function(m){ return m.key; });
  _sGridSave();
  // Redrawing the grid does not redraw the open picker, so it is rebuilt with
  // the boxes in their new state.
  const box = document.getElementById("metricpick");
  if(box && box.classList.contains("open")){
    const btn = document.querySelector(".gtools .gbtn");
    salesMetricsOpen({target: btn, stopPropagation: function(){}});
  }
}

function _sColLabel(c, gran){
  if(gran==="month") return c;                 // 2026-08
  const p=String(c).split("-");
  return p.length===3 ? (p[1].replace(/^0/,"")+"/"+p[2]) : c;
}

/* ONE hue, light→dark, five steps. Five rather than a continuous ramp because
   past about seven classes adjacent shades blur; and the number is printed in
   every cell regardless, so the tint is an aid, never the reading. */
/* Metrics that can legitimately go NEGATIVE, and where the sign is the whole
   point. A loss is not a small profit. */
const _S_SIGNED = ["profit", "margin_pct", "net_proceeds", "roi_pct"];

/* THE SHADING BEHIND A CELL.
 *
 * HUE IS THE DIRECTION OF IMPACT ON PROFIT, NOT WHETHER A NUMBER WENT UP.
 *
 * Stated by the owner, and it is the right model:
 *
 *   income lines   revenue, profit, units, orders   up   = green
 *   cost lines     fees, COGS, ad spend, refunds    down = green
 *
 * so RED ALWAYS MEANS BAD FOR PROFIT and GREEN ALWAYS MEANS GOOD, whichever
 * row you are looking at. This is what the grid did not do: it shaded every row
 * on one green scale by SIZE, so a month of record Amazon fees was the darkest
 * green on the sheet. The direction each metric wants is not guessed here -- it
 * is `good` on the metric itself, set beside the metric's own definition in
 * domain/sales_data.py, so the two cannot drift apart.
 *
 * INTENSITY IS THE SIZE OF THE CHANGE AGAINST THE PRIOR COLUMN.
 *
 *   under 1%   flat -- left unshaded, because a rounding wobble is not news
 *   1 to 5%    faint
 *   5 to 10%   light
 *   10 to 20%  strong
 *   over 20%   solid
 *
 * Percentages, so it is scaled per ROW by construction: a dark red in Referral
 * Fees is not the same number of pounds as a dark red in Revenue -- it is dark
 * because it is a big move FOR THAT LINE.
 *
 * A LOSS IS STILL RED, whatever the change was.
 *
 * The one thing kept from the previous rule. A profit row that goes -80 then
 * -50 has improved, and by change alone the -50 would be green -- a green cell
 * on a day that lost fifty pounds. On the rows where the sign is the whole
 * point (see _S_SIGNED) a negative value is red regardless, because it IS bad
 * for profit, which is the rule this whole scheme exists to express.
 *
 * Colour is never the only carrier: every cell prints its number and its hover
 * gives the exact figure and the change that drove the shade, so the grid reads
 * correctly in black and white and to anyone who cannot separate red from green.
 */
const _S_GREEN = ["rgba(45,212,168,.10)", "rgba(45,212,168,.20)",
                  "rgba(45,212,168,.32)", "rgba(45,212,168,.46)"];
const _S_RED = ["rgba(239,68,68,.10)", "rgba(239,68,68,.20)",
                "rgba(239,68,68,.32)", "rgba(239,68,68,.46)"];

/* The change from the previous column, as a percentage.
 *
 * null when it cannot be one: the first column has nothing before it, and a
 * cell whose neighbour is missing is not a change of anything. Going from zero
 * to something is a real move and is treated as a big one rather than as
 * infinity. */
function _sDeltaPct(v, prev){
  if(v === null || v === undefined || prev === null || prev === undefined) return null;
  const a = Number(v), b = Number(prev);
  if(!isFinite(a) || !isFinite(b)) return null;
  if(b === 0) return (a === 0) ? 0 : (a > 0 ? 100 : -100);
  return ((a - b) / Math.abs(b)) * 100;
}

function _sTint(v, prev, key, good){
  if(v === null || v === undefined) return "";
  const n = Number(v);
  if(!isFinite(n)) return "";

  const signed = _S_SIGNED.indexOf(String(key || "")) >= 0;
  const d = _sDeltaPct(v, prev);

  // A loss is bad however it got there -- and shown at full strength, because
  // "we lost money" is not a shade of grey.
  if(signed && n < 0) return _S_RED[3];

  if(d === null) return "";                 // nothing to compare against
  const mag = Math.abs(d);
  if(mag < 1) return "";                    // flat
  const step = mag >= 20 ? 3 : mag >= 10 ? 2 : mag >= 5 ? 1 : 0;

  // Which way is good for THIS row. Anything unlabelled is treated as an
  // income line, which is what all but the cost rows are.
  const wantUp = String(good || "up") !== "down";
  const helps = wantUp ? (d > 0) : (d < 0);
  return (helps ? _S_GREEN : _S_RED)[step];
}

/* ---- actions ----------------------------------------------------------- */
async function salesSync(btn){
  const old = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled=true; btn.innerHTML='<span class="genspin"></span> pulling…'; }
  try{
    // A sync WRITES days into this account's store, so it names the account in
    // the body as well -- _sFetch puts it on the query string, and the server
    // reads either. A pull that landed under the wrong account would take a
    // re-sync of both to undo.
    const j=await _sFetch("/sales/sync",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({marketplace:(typeof WS_MARKET!=="undefined"?WS_MARKET:""),
                           account_id:_sAcct()})});
    if(j === null) return;
    if(!j || !j.ok){ toast((j&&j.error)||"Could not pull sales"); return; }
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
    const j=await _sFetch("/sales/products?"+_sQuery());
    if(j === null) return;
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
