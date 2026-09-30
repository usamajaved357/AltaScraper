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

// WHICH DAY A WEEK STARTS ON. 0 = Sunday, 1 = Monday.
//
// Sunday, because that is what this card is read beside: "on orbit there is
// sales data displayed, and it starts from sunday and ends at saturday". Amazon's
// own reports run Sunday to Saturday as well. An earlier instruction said Monday,
// and this is the number to change back if that is wanted -- everything that
// needs to know reads it from here rather than working it out again, so there is
// no second place for the two to disagree.
const SALES_WEEK_START = 0;
const SALES_DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday",
                         "Friday","Saturday"];

// ONE _sEsc (Milestone 4). There were two; the second, below, was the one
// every caller got (a later declaration replaces an earlier one), so it is
// the one kept, here with the other helpers.
function _sEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
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
           + 'onclick="salesSet(\'preset\',' + jsArg(x[0]) + ')">'+x[1]+'</button>';}).join("");
  }
  const g=document.getElementById("sales_gran");
  if(g){
    g.className = "seg";
    g.innerHTML = SALES_GRAN.map(function(x){
      return '<button class="'+(SALES.gran===x[0]?"on":"")+'" '
           + 'onclick="salesSet(\'gran\',' + jsArg(x[0]) + ')">'+x[1]+'</button>';}).join("");
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
           +  'onclick="salesSetMonth(' + jsArg(start) + ',' + jsArg(end) + ')" '
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
  // PICKING A PERIOD ENDS A ZOOM. The "Zoomed to … / Back to the full range"
  // bar stayed up after a preset was chosen, and pressing it threw the chosen
  // period away for the one from before the zoom.
  if(what==="preset"){ SALES.preset=val; SALES._zoomBack = null; }
  else SALES.gran=val;
  salesDrawFilters();
  if(SALES.preset==="custom" && !(SALES.start && SALES.end)) return;
  salesReload();
}

function salesSetDates(){
  const s=document.getElementById("sales_start"), e=document.getElementById("sales_end");
  SALES.start = s ? s.value : "";
  SALES.end   = e ? e.value : "";
  // Typed dates are a new period too, so they end a zoom (see salesSet).
  SALES._zoomBack = null;
  if(SALES.start && SALES.end) salesReload();
}

/* DRAG ACROSS A CHART TO ZOOM INTO THOSE DAYS.
   Called by salescharts.js with two COLUMN positions; the dates that go with
   them are whatever the last draw used, which is why the columns are kept.

   A custom range already existed in the date boxes, but reading a shape off a
   chart and then translating it into two dates typed into two fields is the
   step nobody takes -- so the interesting week never got looked at closely.
   The previous range is remembered so there is a way back out. */
/* A column key's real first and last day. On Day the key IS the day; on Week
   it is the Monday the bucket starts (domain/sales_data.bucket) and the bucket
   runs to the Sunday; on Month it is "YYYY-MM". Zooming used to send these keys
   straight through as dates, so a dragged pair of weeks ended on the second
   week's MONDAY and "2026-08" went to the server as a date. */
function _sBucketSpan(key, gran){
  const k = String(key || "");
  const iso = function(d){ return d.toISOString().slice(0, 10); };
  if(gran === "month" && /^\d{4}-\d{2}$/.test(k)){
    const y = +k.slice(0, 4), m = +k.slice(5, 7) - 1;
    return [iso(new Date(Date.UTC(y, m, 1))), iso(new Date(Date.UTC(y, m + 1, 0)))];
  }
  const d = new Date(k + "T00:00:00Z");
  if(isNaN(d)) return null;
  if(gran === "week") return [iso(d), iso(new Date(d.getTime() + 6 * 86400000))];
  return [k, k];
}

/* The column key, `offDays` earlier, in the SAME granularity: the bucket's
   first day moved back and snapped to the bucket it lands in. */
function _sBackKey(key, offDays, gran){
  const span = _sBucketSpan(key, gran);
  if(!span) return null;
  const d = new Date(new Date(span[0] + "T00:00:00Z").getTime() - (offDays || 0) * 86400000);
  if(isNaN(d)) return null;
  if(gran === "month") return d.toISOString().slice(0, 7);
  if(gran === "week"){
    const back = (d.getUTCDay() + 6) % 7;          // days since Monday
    return new Date(d.getTime() - back * 86400000).toISOString().slice(0, 10);
  }
  return d.toISOString().slice(0, 10);
}

function salesZoomTo(i, j){
  const dates = (SALES._chartDates || []);
  const gran = (SALES.series && SALES.series.granularity) || SALES.gran;
  const a0 = _sBucketSpan(dates[Math.max(0, Math.min(i, j))], gran);
  const b0 = _sBucketSpan(dates[Math.min(dates.length - 1, Math.max(i, j))], gran);
  if(!a0 || !b0) return;
  let from = a0[0], to = b0[1];
  // Kept inside the range on screen: the first and last week or month of a
  // range are usually part-buckets, and zooming must not widen the period.
  const cur = SALES.series || {};
  if(cur.start && from < cur.start) from = cur.start;
  if(cur.end && to > cur.end) to = cur.end;
  if(from > to) return;
  // Zooming inside a zoom keeps the FIRST way back, so "Back to the full
  // range" still means the range you started from.
  if(!SALES._zoomBack) SALES._zoomBack = {preset: SALES.preset, start: SALES.start, end: SALES.end};
  SALES.preset = "custom"; SALES.start = from; SALES.end = to;
  const a = document.getElementById("sales_start"), b = document.getElementById("sales_end");
  if(a) a.value = from;
  if(b) b.value = to;
  // The preset row and the date boxes follow the zoom (they were left showing
  // the old preset with the Custom boxes hidden).
  salesDrawFilters();
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
  salesDrawFilters();
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
  if(acct && u.indexOf("account=") < 0){
    u += (u.indexOf("?") < 0 ? "?" : "&") + "account=" + encodeURIComponent(acct);
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
  // THE MARKETPLACE AND THE SWITCH GENERATION TOO, not only the account.
  // Comparing CUR_ACCOUNT alone let a reply for UK be painted after the
  // sidebar moved to DE (same account), and an A -> B -> A switch pass as
  // "still A". screenScope()/screenStillIn() is the shared test (Rule 12).
  const _sc = (typeof screenScope === "function") ? screenScope() : null;
  const run = (async function(){
    try{
      const r = await fetch(u, opts);
      const j = await r.json();
      if(shareable && _sIsLive(u) && j && j.ok) _sRecent[key] = {at: Date.now(), value: j};
      if(_sc && typeof screenStillIn === "function" && !screenStillIn(_sc)) return null;
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
    // AND THE PRODUCT FILTER. It names the previous account's ASIN, and the
    // product picker keeps a chosen ASIN even with no sales in range -- so B's
    // picker offered A's product (seeded-marker browser check, 28 Sep 2026).
    SALES.asin = "";
    // The filter CONTROL back to its default -- emptied, it lost "All products"
    // until the next good load (review).
    const _sel = document.getElementById("sales_asin");
    if(_sel) _sel.innerHTML = '<option value="">All products</option>';
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
  if(a) q.push("account=" + encodeURIComponent(a));
  if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
    q.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return q.join("&");
}

function _sQuery(){
  const q=["preset="+encodeURIComponent(SALES.preset),
           "granularity="+encodeURIComponent(SALES.gran)];
  const _a = _sAcct();
  if(_a) q.push("account="+encodeURIComponent(_a));
  if(SALES.preset==="custom" && SALES.start && SALES.end){
    q.push("start="+encodeURIComponent(SALES.start));
    q.push("end="+encodeURIComponent(SALES.end));
  }
  if(SALES.asin) q.push("asin="+encodeURIComponent(SALES.asin));
  if(typeof WS_MARKET!=="undefined" && WS_MARKET && WS_MARKET!=="__all__")
    q.push("marketplace="+encodeURIComponent(WS_MARKET));
  // WHAT THE CARDS' "was"/"LY" FIGURE IS. /sales/summary summed the period
  // immediately before whatever the picker said, so "LY" printed last month's
  // figure. It now shifts 364 days when told the comparison is the prior year.
  if(SALES.compareKind === "year") q.push("compare_kind=year");
  return q.join("&");
}

// SALES_BD ... salesDrawBreakdown: moved to static/js/sales_breakdown.js (Milestone 4), loaded right after this file.
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
    // ANY VALUE AT ALL, zero included. A DIFFERENT QUESTION from anyReal, and
    // the difference is the bug behind "the dotted lines are not accurately
    // representing last week data in all graphs all over the app".
    //
    // The comparison line was dropped whenever anyReal said no -- which it says
    // for a period that traded NOTHING as readily as for a period nobody has
    // any figures for. So a quiet week produced no dashed line, and a dashed
    // line missing from a chart reads as the comparison being broken rather
    // than as last week having been quiet.
    //
    // Those are two different facts and they need two different pictures:
    //   nothing known   -> no line, because there is nothing to draw
    //   known, and zero -> a line along the bottom, which is the answer
    const anyKnown = function(vals){
      return vals && vals.some(function(v){
        return v !== null && v !== undefined; });
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
        // BY BUCKET, not by day. On Week and Month the columns are bucket keys
        // (a Monday, or "YYYY-MM"), and shifting a Monday by 30 days lands on
        // a Thursday -- which is no column at all -- while "2026-09" is not a
        // date, so the dashed line vanished on both. _sBackKey shifts the
        // bucket's first day and snaps to the bucket it falls in.
        cmpCells = dates.map(function(d){
          const back = _sBackKey(d, SALES.compareOffsetDays,
                                 (ser && ser.granularity) || SALES.gran);
          if(!back) return null;
          return (back in was) ? was[back] : null;
        });
        // anyKnown, not anyReal: a prior period of genuine zeros is drawn along
        // the bottom rather than left off the chart. Only a period with no
        // figures at all is dropped.
        if(!anyKnown(cmpCells)) cmpCells = null;
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
        // Its columns ARE SALES._chartDates, so a drag across it can be turned
        // back into two dates. The week and Today charts deliberately do not
        // name a handler -- their columns are a different set entirely.
        id: "sales_combo", onZoom: "salesZoomTo", columns: dates,
        // WHAT ONE BAR IS. The granularity picker switches these columns
        // between days, weeks and months, and the chart's hover line said
        // "the day's figures" for all three.
        unit: (SALES.gran === "week") ? "week"
            : (SALES.gran === "month") ? "month" : "day",
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
      +  'border:1px solid var(--warn-line);background:var(--warn-bg);border-radius:6px">'
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
  //
  // NEWEST LOAD WINS, NOT "FINISH THE OLD ONE FIRST". The re-run above still
  // painted the OLD period first (for seconds, on a slow account) and every
  // helper it had started -- compare, recent, campaigns -- could land after
  // the new one. Each load now takes a ticket (SALES.loadSeq); after every
  // await a load whose ticket is no longer current stops without painting.
  const my = SALES.loadSeq = (SALES.loadSeq || 0) + 1;
  const _sc = (typeof screenScope === "function") ? screenScope() : null;
  const stale = function(){
    return my !== SALES.loadSeq
        || (_sc && typeof screenStillIn === "function" && !screenStillIn(_sc));
  };
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
    if(av === null || stale()) return;
    // Kept, so every part of the screen can say what it does and does not have.
    // The grid needs it as much as the cards do -- an empty column and a column
    // that is genuinely zero look identical, and they are not the same fact.
    SALES.avail = av;
    const [sum, ser] = await Promise.all([
      _sFetch("/sales/summary?"+_sQuery()),
      _sFetch("/sales/series?"+_sQuery())
    ]);
    if(sum === null || ser === null || stale()) return;
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
    salesDrawPpcCards(sum);
    salesDrawOrgPpc(ser);
    // Below the split it breaks down. Fire and forget, like the product
    // breakdown: a slow campaign query must never hold up the charts.
    salesLoadCampaigns().catch(function(){});
    // The grid's own period if it has one (salesRedrawGrid, sales_grid.js).
    salesRedrawGrid();
    salesDrawRange(sum, av);
    // WHICH PRODUCTS SOLD. This was never called.
    //
    // salesLoadBreakdown had exactly one caller: salesBdGroup, the "Each ASIN /
    // Grouped by parent" toggle -- and those two buttons are drawn INSIDE the
    // block that only appears once the loader has run. Nothing could ever start
    // it, so the "By product" section of this screen has been empty since it
    // was written. Measured on jack_uk: the section 0 rows and 0 bytes on the
    // page, while /sales/breakdown answers with 47 products; calling it by hand
    // in the console filled it with all 47 immediately.
    //
    // Here rather than at the top with Live Sales: it reads _sQuery(), which
    // needs the range this function has just settled. Not awaited -- it has its
    // own fetch and the figures above must not wait for it.
    salesLoadBreakdown();
    // After the numbers, not before: the options depend on the range, and the
    // grid is what someone is waiting for.
    salesFillAsins();
    // salesLoadToday() and salesLoadWeek() are NOT called here any more. They
    // are started at the top of this function, before the awaits, because Live
    // Sales reads the Orders API and was the slowest thing on the screen by a
    // factor of twenty -- 5.75s against 250ms for everything else -- entirely
    // because it went last. Calling them again here would fetch both twice.
  }catch(e){
    if(stale()) return;
    const g=document.getElementById("sales_grid");
    if(g) g.innerHTML=uiError("Sales could not be loaded", String(e), "salesReload", "sales");
  }finally{
    // Only the CURRENT load clears the loading state; an overtaken one leaves
    // it to the load that replaced it.
    if(my === SALES.loadSeq){
      if(grid) grid.style.opacity="";
      SALES.busy=false;
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
  const tk = SALES.loadSeq;
  try{
    // _sScope(), not _sQuery(): days=6 already says which window this is.
    j = await _sFetch("/sales/recent?days=6&" + _sScope());
    if(j === null) return;
  }catch(e){ return; }
  // A newer load has cleared _live and asked again; this reply is for it only
  // if no load started since this one was asked for.
  if(tk !== SALES.loadSeq) return;
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
    salesRedrawGrid();
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
  // THE CARDS' EARLIER FIGURE COMES FROM THE SERVER, so a change between
  // "previous period" and "last year" needs a fresh summary (compare_kind in
  // _sQuery); the label follows the reply, never the picker, until it lands.
  if(SALES.data) _sReloadSummary().catch(function(){});
}

/* Only the stat cards' summary, re-asked with the current comparison. */
async function _sReloadSummary(){
  const tk = SALES.loadSeq;
  const sc = (typeof screenScope === "function") ? screenScope() : null;
  const sum = await _sFetch("/sales/summary?" + _sQuery());
  if(sum === null || tk !== SALES.loadSeq) return;
  if(sc && typeof screenStillIn === "function" && !screenStillIn(sc)) return;
  if(!sum || !sum.ok) return;
  SALES.data = sum;
  salesDrawCards(sum, null);
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

  const tk = SALES.loadSeq, kind = SALES.compareKind;
  const j = await _sFetch("/sales/series?" + q.join("&"));
  // A comparison for a period (or a picker setting) that is no longer on
  // screen is dropped rather than drawn behind the new one.
  if(tk !== SALES.loadSeq || kind !== SALES.compareKind) return;
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

// _sAdFooter ... salesLoadWeek: moved to static/js/sales_week.js (Milestone 4), loaded right after this file.
// SALES_CAMP ... salesDrawOrgPpc: moved to static/js/sales_campaigns.js (Milestone 4), loaded right after this file.
// salesDrawRange ... _sProfitTip: moved to static/js/sales_live.js (Milestone 4), loaded right after this file.
// salesDrawCards ... _sDelta: moved to static/js/sales_cards.js (Milestone 4), loaded right after this file.
// salesDrawGrid ... _sTint: moved to static/js/sales_grid.js (Milestone 4), loaded right after this file.
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
    // The fees-and-refunds half can fail while the sales half succeeds -- say
    // so, or an account whose finances stopped updating looks fine.
    if(j.finance && j.finance.ok === false) msg+=" · Fees and refunds NOT updated: "+(j.finance.error||"no reason given");
    else if(j.finance && j.finance.not_updated) msg+=" · "+j.finance.not_updated;
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
  const tk = SALES.loadSeq;
  try{
    const j=await _sFetch("/sales/products?"+_sQuery());
    if(j === null || tk !== SALES.loadSeq) return;
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

/* "ALL MARKETPLACES" NOW MEANS ALL MARKETPLACES.
 *
 * The sidebar has offered it all along and this screen threw it away:
 * static/js/scopeq.js drops the parameter, so every panel below asked about ONE
 * marketplace. Measured 21 Aug 2026 with "All marketplaces" showing: the screen
 * said "United Kingdom Time", drew a week-to-date chart in pounds, and the
 * Sales Report under it was jack_uk's UK figures. Ten marketplaces, one shown,
 * under a heading that said all.
 *
 * Every panel on this screen is built for one marketplace and one currency --
 * a chart cannot plot pounds and euros on one axis, and the owner's rule is
 * "keep grouping by currency, don't sum across them". So instead of pretending,
 * the single-marketplace panels are put away and a per-marketplace table takes
 * their place (static/js/brandview.js). Choosing a country brings them back.
 */
function salesIsAllMarkets(){
  return typeof WS_MARKET !== "undefined" && WS_MARKET === "__all__";
}

function salesOpen(){
  const all = salesIsAllMarkets();
  const body = document.getElementById("sales_body");
  const bv = document.getElementById("brandview");
  if(body) body.style.display = all ? "none" : "";
  if(bv) bv.style.display = all ? "" : "none";
  if(all){
    if(typeof brandviewLoad === "function") brandviewLoad();
    return;
  }
  const s=document.getElementById("sales_start"), e=document.getElementById("sales_end");
  if(s && !s.value) SALES.start="";
  if(e && !e.value) SALES.end="";
  salesDrawFilters();
  salesReload();
}
window.salesOpen = salesOpen;
window.salesSetAsin = salesSetAsin;
window.salesSetDates = salesSetDates;
