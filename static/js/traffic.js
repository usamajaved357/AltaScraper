// ===================== TRAFFIC & CONVERSIONS =====================
//
// Built to Orbit's page, scanned panel by panel on 15 Aug 2026, and drawn with
// the SAME chart functions the Sales screen uses -- salesChart and salesCombo
// from salescharts.js. A second chart implementation here would drift from that
// one on the first fix made to either, and the two screens would stop looking
// like the same app within a week.
//
// ORBIT'S PANELS, in its order and its words:
//
//   8 KPI tiles        SESSIONS, PAGE VIEWS, PAGES / SESSION, UNITS ORDERED,
//                      REVENUE, CONVERSION RATE, BUY BOX %, ACTIVE ASINS
//   Traffic Overview   "Sessions & Page Views"
//   Performance Metrics "Conversion Rate & Buy Box %"
//   Channel Breakdown  a donut of Browser vs Mobile, and the same split daily
//   Top ASINs Trend    "Daily sessions"
//   ASIN Performance   "Top 10 by Conversion Rate"
//   Top ASINs by Sessions, with a "Group by parent ASIN" toggle
//
// EVERY FIGURE COMES FROM ONE REQUEST, made in domain/traffic_view.py, so the
// tiles, the charts and the table cannot disagree about a number they all
// describe. That is the failure the Sales screen had to be rescued from twice.

let TRAF = {preset: "30d", group: "asin", data: null, busy: false, sort: "sessions"};

const TRAF_PRESETS = [["7d", "7d"], ["14d", "14d"], ["30d", "30d"],
                      ["60d", "60d"], ["90d", "90d"]];

function _tEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* Numbers, formatted the way the rest of the app formats them. _sNum lives in
   sales.js and is loaded before this file; if it is not there for any reason
   the page still draws, with plainer numbers, rather than throwing. */
function _tNum(v, kind, cur){
  if(typeof _sNum === "function") return _sNum(v, kind, cur);
  if(v === null || v === undefined) return "—";
  if(kind === "pct") return Number(v).toFixed(1) + "%";
  if(kind === "ratio") return Number(v).toFixed(2);
  return String(v);
}

function trafficOnOpen(){ if(!TRAF.data) trafficLoad(); else trafficRender(); }

function trafficSetPreset(p){ TRAF.preset = p; trafficLoad(); }
function trafficSetGroup(g){ TRAF.group = g; trafficLoad(); }
function trafficSort(k){
  TRAF.sort = (TRAF.sort === k) ? ("-" + k) : k;
  trafficRender();
}

function _tQuery(){
  const q = ["preset=" + encodeURIComponent(TRAF.preset),
             "group=" + encodeURIComponent(TRAF.group)];
  if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
    q.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return q.join("&");
}

async function trafficLoad(){
  if(TRAF.busy) return;
  TRAF.busy = true;
  const host = document.getElementById("trafbody");
  // The previous render is held at reduced opacity rather than replaced with a
  // spinner: no layout jump, and the figures being read stay readable.
  if(host && host.innerHTML.trim()) host.style.opacity = ".45";
  else if(host) host.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Loading traffic…</div>';
  try{
    const j = await (await fetch("/traffic/summary?" + _tQuery())).json();
    TRAF.data = j;
    trafficRender();
  }catch(e){
    if(host) host.innerHTML = '<div class="empty">Could not load traffic: '
      + _tEsc(String(e)) + '</div>';
  }finally{
    TRAF.busy = false;
    if(host) host.style.opacity = "";
  }
}

/* The date pills, in the same shape the Sales screen's are. */
function _tPills(){
  return '<span class="gpills">' + TRAF_PRESETS.map(function(p){
    return '<button class="gpill' + (p[0] === TRAF.preset ? " on" : "") + '"'
      + ' onclick="trafficSetPreset(' + jsArg(p[0]) + ')">' + _tEsc(p[1]) + '</button>';
  }).join("") + '</span>';
}

function trafficRender(){
  const host = document.getElementById("trafbody");
  if(!host) return;
  const d = TRAF.data;
  if(!d || !d.ok){
    host.innerHTML = '<div class="empty">' + _tEsc((d && d.error) || "No traffic data")
      + '</div>';
    return;
  }
  const cur = d.currency || "";

  let h = '<div class="gtools" style="margin:0 0 14px">'
    + '<span class="glbl">Period</span>' + _tPills()
    + '<span class="glast">' + _tEsc(d.start || "") + ' to ' + _tEsc(d.end || "") + '</span>'
    + '<span class="gspacer"></span>'
    + '<span class="glbl">Group</span>'
    + '<span class="gpills">'
    + '<button class="gpill' + (TRAF.group === "asin" ? " on" : "") + '"'
    + ' onclick="trafficSetGroup(\'asin\')">By ASIN</button>'
    + '<button class="gpill' + (TRAF.group === "parent" ? " on" : "") + '"'
    + ' onclick="trafficSetGroup(\'parent\')">By parent</button>'
    + '</span></div>';

  if(d.empty){
    host.innerHTML = h + '<div class="empty">' + _tEsc(d.note || "Nothing yet.") + '</div>';
    return;
  }

  // ---- the eight tiles -------------------------------------------------
  h += '<div class="stat-row" id="traf_kpis">' + (d.kpis || []).map(function(k){
    const missing = (k.value === null || k.value === undefined);
    return '<div class="stat-card' + (missing ? " is-empty" : "") + '">'
      + '<p class="stat-label">' + _tEsc(k.label) + '</p>'
      + '<p class="stat-number">' + _tEsc(_tNum(k.value, k.kind, cur)) + '</p>'
      + (k.delta_pct === null || k.delta_pct === undefined
          ? '<p class="stat-delta">no earlier period</p>'
          : '<p class="stat-delta">'
            + (typeof _sBadge === "function" ? _sBadge(k.delta_pct, {sign: true})
                                             : (k.delta_pct + "%"))
            + '</p>')
      + '</div>';
  }).join("") + '</div>';

  const dates = d.dates || [];
  const S = d.series || {};
  const pts = function(arr){
    return dates.map(function(x, i){ return {label: x, value: (arr || [])[i]}; });
  };

  // ---- Traffic Overview -------------------------------------------------
  h += '<div class="salespanel" style="margin:16px 0">'
    + '<div class="panelhead" style="margin:0 0 10px;padding:0"><div>'
    + '<p class="paneltitle">Traffic Overview</p>'
    + '<p class="panelsub">Sessions &amp; Page Views</p></div></div>'
    + (typeof salesCombo === "function"
        // kind:"count" -- these are sessions and page views, and the axis would
        // otherwise be labelled in pounds.
        ? salesCombo({id: "traf_overview", columns: dates, bars: null, currency: cur,
                      kind: "count",
                      width: scChartWidth("trafbody", 1365), height: 240,
                      lines: [{key: "sessions", values: S.sessions},
                              {key: "page_views", values: S.page_views}]})
        : "")
    + '</div>';

  // ---- Performance Metrics ---------------------------------------------
  h += '<div class="salespanel" style="margin:16px 0">'
    + '<div class="panelhead" style="margin:0 0 10px;padding:0"><div>'
    + '<p class="paneltitle">Performance Metrics</p>'
    + '<p class="panelsub">Conversion Rate &amp; Buy Box %</p></div></div>'
    + (typeof salesCombo === "function"
        ? salesCombo({id: "traf_perf", columns: dates, bars: null, currency: cur,
                      kind: "pct",
                      width: scChartWidth("trafbody", 1365), height: 240,
                      lines: [{key: "conversion", values: S.conversion},
                              {key: "buy_box", values: S.buy_box}]})
        : "")
    + '</div>';

  // ---- Channel Breakdown ------------------------------------------------
  const ch = d.channel || {};
  h += '<div class="salespanel" style="margin:16px 0">'
    + '<div class="panelhead" style="margin:0 0 10px;padding:0"><div>'
    + '<p class="paneltitle">Channel Breakdown</p>'
    + '<p class="panelsub">Sessions</p></div>'
    + '<div class="cc" style="font-size:20px;font-weight:600;color:var(--ink)">'
    + _tEsc(_tNum(ch.browser + ch.mobile, "count", cur)) + '</div></div>'
    + '<div class="trafsplit">'
    + _tDonut(ch)
    + '<div style="flex:1;min-width:0">'
    + (typeof salesCombo === "function"
        ? salesCombo({id: "traf_channel", columns: dates, bars: null, currency: cur,
                      kind: "count",
                      width: scChartWidth("trafbody", 1000), height: 240,
                      lines: [{key: "browser", values: S.browser},
                              {key: "mobile", values: S.mobile}]})
        : "")
    + '</div></div></div>';

  // ---- Top ASINs Trend --------------------------------------------------
  const trend = d.top_trend || [];
  if(trend.length){
    h += '<div class="salespanel" style="margin:16px 0">'
      + '<div class="panelhead" style="margin:0 0 10px;padding:0"><div>'
      + '<p class="paneltitle">Top ASINs Trend</p>'
      + '<p class="panelsub">Daily sessions</p></div></div>'
      + (typeof salesCombo === "function"
          ? salesCombo({id: "traf_trend", columns: dates, bars: null, currency: cur,
                        kind: "count",
                        width: scChartWidth("trafbody", 1365), height: 240,
                        lines: trend.map(function(t, i){
                          return {key: "top" + (i + 1), values: t.daily};
                        })})
          : "")
      + '<div class="traflegend">' + trend.map(function(t, i){
          return '<span class="ri-leg"><span class="ri-dot" style="background:'
            + (TRAF_COLOURS[i] || "#8fd694") + '"></span>'
            + '<span class="ri-leg-label" title="' + _tEsc(t.title || t.asin) + '">'
            + _tEsc((t.title || t.asin).slice(0, 34))
            + ((t.title || "").length > 34 ? "â€¦" : "") + '</span>'
            + '<span class="ri-leg-val">' + _tEsc(_tNum(t.sessions, "count", cur))
            + '</span></span>';
        }).join("") + '</div></div>';
  }

  // ---- ASIN Performance -------------------------------------------------
  const cvr = d.top_cvr || [];
  h += '<div class="salespanel" style="margin:16px 0">'
    + '<div class="panelhead" style="margin:0 0 10px;padding:0"><div>'
    + '<p class="paneltitle">ASIN Performance</p>'
    + '<p class="panelsub">Top 10 by Conversion Rate</p></div></div>'
    + (cvr.length
        ? _tBars(cvr, cur)
        : '<div class="cc" style="font-size:12px;padding:10px 0">No product has '
          + 'had ' + (d.cvr_min_sessions || 30) + ' sessions in this period yet, '
          + 'and a conversion rate from fewer than that is noise â€” one session '
          + 'that converted reads as 100%.</div>')
    + '</div>';

  // ---- the table --------------------------------------------------------
  h += '<div class="salespanel" style="margin:16px 0">'
    + '<div class="panelhead" style="margin:0 0 10px;padding:0"><div>'
    + '<p class="paneltitle">Top ASINs by Sessions</p>'
    + '<p class="panelsub">' + (TRAF.group === "parent"
        ? "Grouped by parent ASIN" : "One row per ASIN") + '</p></div>'
    + '<div class="cc" style="font-size:11px">' + (d.rows || []).length
    + ' products</div></div>'
    + _tTable(d, cur) + '</div>';

  host.innerHTML = h;
  if(typeof altaChartsInView === "function") altaChartsInView(host);
}

/* The five trend colours, and the two channel ones. Orbit's own, measured:
   gold, blue, red, green, purple for the ASIN lines; blue and orange for
   browser and mobile. */
const TRAF_COLOURS = ["#fbbf24", "#3b82f6", "#ef4444", "#22c55e", "#8b5cf6"];

/* A donut, drawn rather than pulled in: two numbers do not justify a charting
   library, and the app already refuses anything from a CDN it does not own. */
function _tDonut(ch){
  const b = Number(ch.browser || 0), m = Number(ch.mobile || 0);
  const tot = b + m;
  if(!tot) return '<div class="cc" style="font-size:12px">No sessions yet.</div>';
  const R = 54, C = 2 * Math.PI * R;
  const bLen = C * (b / tot);
  return '<div class="trafdonut">'
    + '<svg viewBox="0 0 140 140" width="140" height="140">'
    // Mobile fills the ring; browser is drawn over it for its share, so the two
    // always add to the whole and can never leave a gap from rounding.
    + '<circle cx="70" cy="70" r="' + R + '" fill="none" stroke="#f97316" stroke-width="18"/>'
    + '<circle cx="70" cy="70" r="' + R + '" fill="none" stroke="#3b82f6" stroke-width="18"'
    + ' stroke-dasharray="' + bLen.toFixed(1) + ' ' + (C - bLen).toFixed(1) + '"'
    + ' transform="rotate(-90 70 70)"/>'
    + '</svg>'
    + '<div class="ri-legend" style="margin-top:8px">'
    + '<div class="ri-leg"><span class="ri-dot" style="background:#3b82f6"></span>'
    + '<span class="ri-leg-label">Browser</span>'
    + '<span class="ri-leg-pct">' + (ch.browser_pct == null ? "â€”" : ch.browser_pct + "%")
    + '</span></div>'
    + '<div class="ri-leg"><span class="ri-dot" style="background:#f97316"></span>'
    + '<span class="ri-leg-label">Mobile</span>'
    + '<span class="ri-leg-pct">' + (ch.mobile_pct == null ? "â€”" : ch.mobile_pct + "%")
    + '</span></div></div></div>';
}

/* Horizontal bars for the top converters. Orbit draws these as a bar chart with
   the product names down the side; a bar per row with the figure printed on it
   says the same thing and stays readable when a title is long. */
function _tBars(rows, cur){
  const max = Math.max.apply(null, rows.map(function(r){ return r.conversion || 0; })) || 1;
  return '<div class="trafbars">' + rows.map(function(r){
    const pct = ((r.conversion || 0) / max) * 100;
    return '<div class="trafbar">'
      + '<span class="trafbar-name" title="' + _tEsc(r.title || r.asin) + '">'
      + _tEsc((r.title || r.asin).slice(0, 46)) + '</span>'
      + '<span class="trafbar-track"><span class="trafbar-fill" style="width:'
      + pct.toFixed(1) + '%"></span></span>'
      + '<span class="trafbar-val">' + _tEsc(_tNum(r.conversion, "pct", cur)) + '</span>'
      + '<span class="trafbar-sub cc">' + _tEsc(_tNum(r.sessions, "count", cur))
      + ' sessions</span></div>';
  }).join("") + '</div>';
}

const TRAF_COLS = [
  ["asin",       "ASIN",       "text"],
  ["sessions",   "Sessions",   "count"],
  ["page_views", "Page Views", "count"],
  ["units",      "Units",      "count"],
  ["revenue",    "Revenue",    "money"],
  ["conversion", "CVR%",       "pct"],
  ["buy_box",    "Buy Box%",   "pct"],
];

function _tTable(d, cur){
  const key = TRAF.sort.replace(/^-/, "");
  const asc = TRAF.sort.charAt(0) === "-";
  const rows = (d.rows || []).slice().sort(function(a, b){
    const x = a[key], y = b[key];
    if(key === "asin"){
      const r = String(a.title || a.asin).localeCompare(String(b.title || b.asin));
      return asc ? -r : r;
    }
    const r = (Number(y) || 0) - (Number(x) || 0);
    return asc ? -r : r;
  });
  let h = '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
        + '<thead><tr>';
  TRAF_COLS.forEach(function(c){
    h += '<th style="cursor:pointer;white-space:nowrap;text-align:'
      + (c[2] === "text" ? "left" : "right") + '" onclick="trafficSort('
      + jsArg(c[0]) + ')">' + _tEsc(c[1])
      + (key === c[0] ? (asc ? " â–´" : " â–¾") : "") + '</th>';
  });
  h += '</tr></thead><tbody>';
  rows.forEach(function(r){
    // ONE LINE PER PRODUCT. These titles are long -- "Bayonet Ceiling Fan with
    // Light and Remote, B22 Bayonet Fitting & E27 Screw-In, No Wiring Needed,
    // Dimmable LED 6-Blade 52cm..." -- and left to wrap they made rows 182px
    // tall and the table 4,587px long, which is a table nobody scans.
    //
    // Orbit truncates: "Flux Footwear Adapt Runners Barefoot Sho...
    // (B0D8JZWSNH)". The whole title is on the hover, and the ASIN is never
    // truncated, because it is the part you would copy.
    h += '<tr><td class="trafname">'
      + '<span class="trafname-t pii" title="' + _tEsc(r.title || "") + '">'
      + _tEsc(r.title || "(no title recorded)") + '</span>'
      + '<code class="cc trafname-a">' + _tEsc(r.asin) + '</code>'
      + (r.children > 1 ? '<span class="cc trafname-a">· ' + r.children
                          + ' variations</span>' : "")
      + '</td>';
    TRAF_COLS.slice(1).forEach(function(c){
      h += '<td style="padding:6px 8px;text-align:right;white-space:nowrap">'
        + _tEsc(_tNum(r[c[0]], c[2], cur)) + '</td>';
    });
    h += '</tr>';
  });
  return h + '</tbody></table></div>';
}
