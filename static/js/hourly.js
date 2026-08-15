// ===================== HOURLY SALES =====================
//
// Built to Orbit's page, whose own description says exactly what it is:
//
//   "Total ordered sales per ASIN by local hour of week (America/Los_Angeles),
//    trailing 30 days. Each row shows the ASIN's average sales by hour of day,
//    color-scaled to its own peak hour; click a row for the full Mon-Sun grid."
//
// COLOUR-SCALED TO ITS OWN PEAK is the important half, and it is the same rule
// the P&L heatmap uses: shade each row against ITSELF, never across rows. A
// product selling three a day and one selling three hundred both have a best
// hour, and that is what this screen is for. Scaled across rows, every row but
// the biggest would be a flat grey band.

let HRLY = {days: 30, metric: "units", data: null, busy: false, open: ""};

function _hEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function hourlyOnOpen(){ if(!HRLY.data) hourlyLoad(); else hourlyRender(); }
function hourlySetDays(d){ HRLY.days = d; hourlyLoad(); }
function hourlySetMetric(m){ HRLY.metric = m; hourlyLoad(); }
function hourlyToggle(asin){
  HRLY.open = (HRLY.open === asin) ? "" : asin;
  hourlyRender();
}

function _hQuery(){
  const q = ["days=" + HRLY.days, "metric=" + encodeURIComponent(HRLY.metric)];
  if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
    q.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return q.join("&");
}

async function hourlyLoad(){
  if(HRLY.busy) return;
  HRLY.busy = true;
  const host = document.getElementById("hrlybody");
  if(host && host.innerHTML.trim()) host.style.opacity = ".45";
  else if(host) host.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Reading order times…</div>';
  try{
    HRLY.data = await (await fetch("/hourly/summary?" + _hQuery())).json();
    hourlyRender();
  }catch(e){
    if(host) host.innerHTML = '<div class="empty">Could not load: '
      + _hEsc(String(e)) + '</div>';
  }finally{
    HRLY.busy = false;
    if(host) host.style.opacity = "";
  }
}

/* Pull orders the app has not seen. Slow on purpose -- it is one Amazon call per
   order -- so it says what it is doing and how far it got. */
async function hourlyFetch(btn){
  if(btn){ btn.disabled = true; btn.innerHTML = '<span class="genspin"></span> Pulling…'; }
  const st = document.getElementById("hrly_status");
  if(st) st.textContent = "Asking Amazon for orders, then for what was in each one…";
  try{
    const j = await (await fetch("/hourly/fetch?" + _hQuery(), {method: "POST"})).json();
    if(!j || !j.ok){
      if(st) st.innerHTML = '<span style="color:var(--red)">'
        + _hEsc((j && j.error) || "failed") + '</span>';
    } else {
      if(st) st.textContent = "Read " + j.fetched + " new order"
        + (j.fetched === 1 ? "" : "s") + " of " + j.orders_seen + " in the window."
        + (j.note ? " " + j.note : "");
      await hourlyLoad();
    }
  }catch(e){
    if(st) st.innerHTML = '<span style="color:var(--red)">' + _hEsc(String(e)) + '</span>';
  }finally{
    if(btn){ btn.disabled = false; btn.innerHTML = '<i class="ti ti-download"></i> Pull orders'; }
  }
}

const HRLY_DAYS = [[30, "30d"], [60, "60d"], [90, "90d"]];
const HRLY_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/* The hour labels Orbit shows across the top: 12AM, 6AM, 12PM, 6PM, 11PM. */
function _hHourLabel(h){
  if(h === 0) return "12AM";
  if(h === 12) return "12PM";
  return (h % 12 === 0 ? 12 : h % 12) + (h < 12 ? "AM" : "PM");
}

/* A cell's shade: gold, scaled against THIS row's own peak. Measured off
   Orbit's own cells -- rgba(251,191,36,a) over rgb(45,50,66) for a zero. */
function _hCell(v, peak){
  if(!v) return "rgb(45,50,66)";
  const a = 0.14 + 0.72 * Math.min(1, v / (peak || 1));
  return "rgba(251,191,36," + a.toFixed(2) + ")";
}

function _hNum(v, metric, cur){
  if(typeof _sNum === "function")
    return _sNum(v, metric === "revenue" ? "money" : "count", cur);
  return String(v);
}

function hourlyRender(){
  const host = document.getElementById("hrlybody");
  if(!host) return;
  const d = HRLY.data;
  if(!d || !d.ok){
    host.innerHTML = '<div class="empty">' + _hEsc((d && d.error) || "No data") + '</div>';
    return;
  }
  const cur = d.currency || "";

  let h = '<div class="gtools" style="margin:0 0 6px">'
    + '<span class="glbl">Window</span><span class="gpills">'
    + HRLY_DAYS.map(function(p){
        return '<button class="gpill' + (p[0] === HRLY.days ? " on" : "") + '"'
          + ' onclick="hourlySetDays(' + p[0] + ')">' + p[1] + '</button>';
      }).join("") + '</span>'
    + '<span class="glbl">Show</span><span class="gpills">'
    + [["units", "Units"], ["revenue", "Revenue"]].map(function(p){
        return '<button class="gpill' + (p[0] === HRLY.metric ? " on" : "") + '"'
          + ' onclick="hourlySetMetric(' + jsArg(p[0]) + ')">' + p[1] + '</button>';
      }).join("") + '</span>'
    + '<span class="gspacer"></span>'
    + '<button class="gbtn" onclick="hourlyFetch(this)">'
    + '<i class="ti ti-download"></i> Pull orders</button>'
    + '</div>'
    + '<div class="cc" id="hrly_status" style="font-size:11.5px;margin:0 0 12px;'
    + 'min-height:16px"></div>';

  if(d.empty){
    host.innerHTML = h + '<div class="empty" style="text-align:left">'
      + _hEsc(d.note || "Nothing yet.") + '</div>';
    return;
  }

  // The header: the hour labels Orbit shows, spread across the 24 columns.
  h += '<div class="hrlywrap"><div class="hrlyhead">'
    + '<span class="hrlyname">ASIN / PRODUCT</span>'
    + '<span class="hrlystrip">'
    + [0, 6, 12, 18, 23].map(function(hr){
        return '<span style="grid-column:' + (hr + 1) + '">' + _hHourLabel(hr) + '</span>';
      }).join("")
    + '</span>'
    + '<span class="hrlytot">WINDOW TOTALS</span></div>';

  (d.asins || []).forEach(function(a){
    const open = (HRLY.open === a.asin);
    h += '<div class="hrlyrow' + (open ? " open" : "") + '"'
      + ' onclick="hourlyToggle(' + jsArg(a.asin) + ')"'
      + ' title="Click for the full Mon-Sun grid">'
      + '<span class="hrlyname">'
      + '<code class="cc">' + _hEsc(a.asin) + '</code>'
      + '<span class="hrlytitle pii" title="' + _hEsc(a.title) + '">'
      + _hEsc(a.title || "(no title)") + '</span></span>'
      + '<span class="hrlystrip">'
      + a.hours.map(function(v, hr){
          return '<span class="hrlycell" style="background:' + _hCell(v, a.peak) + '"'
            + ' title="' + _hHourLabel(hr) + ' — '
            + _hEsc(_hNum(v, d.metric, cur)) + '"></span>';
        }).join("")
      + '</span>'
      + '<span class="hrlytot"><b>' + _hEsc(_hNum(a.units, "units", cur))
      + '</b> units<br>' + _hEsc(_hNum(a.revenue, "revenue", cur)) + '</span>'
      + '</div>';

    if(open){
      // THE FULL MON-SUN GRID, which is what Orbit opens on a click. The strip
      // above is the average day; this is where a Saturday-morning product
      // stops looking like a mid-week one.
      h += '<div class="hrlygrid">'
        + '<div class="hrlygridhead"><span></span>'
        + [0, 6, 12, 18, 23].map(function(hr){
            return '<span style="grid-column:' + (hr + 2) + '">'
              + _hHourLabel(hr) + '</span>'; }).join("")
        + '</div>'
        + a.grid.map(function(row, dow){
            const rowPeak = Math.max.apply(null, row.concat([0]));
            return '<div class="hrlygridrow"><span class="hrlydow">'
              + HRLY_DOW[dow] + '</span>'
              + row.map(function(v, hr){
                  // Scaled against the WHOLE PRODUCT's peak, not the row's, so
                  // Tuesday and Saturday can be compared to each other. Scaling
                  // each day to itself would make every day look equally busy.
                  return '<span class="hrlycell" style="background:'
                    + _hCell(v, a.peak) + '" title="' + HRLY_DOW[dow] + ' '
                    + _hHourLabel(hr) + ' — ' + _hEsc(_hNum(v, d.metric, cur))
                    + '"></span>';
                }).join("") + '</div>';
          }).join("")
        + '<div class="cc" style="font-size:11px;margin-top:8px">'
        + (a.peak_hour === null || a.peak_hour === undefined
            ? 'No peak hour yet.'
            : 'Best hour: <b>' + _hHourLabel(a.peak_hour) + '</b> '
              + '(' + _hEsc(_hNum(a.peak, d.metric, cur)) + ' in the window). '
              + 'Shaded against this product\'s own peak, so a slow seller and a '
              + 'fast one can both be read.')
        + '</div></div>';
    }
  });
  h += '</div>';

  h += '<div class="cc" style="font-size:11px;margin-top:12px">'
    + 'Order times in <b>' + _hEsc(d.timezone || "the marketplace's timezone")
    + '</b>, trailing ' + d.days + ' days, from ' + d.lines + ' order line'
    + (d.lines === 1 ? "" : "s") + '. Cancelled orders are not counted.</div>';

  host.innerHTML = h;
}
