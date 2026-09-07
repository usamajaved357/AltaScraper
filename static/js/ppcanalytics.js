/* static/js/ppcanalytics.js -- the PPC Analytics screen, to orbit-ppc-v3.jsx.
 *
 * The mockup's sections, in its order, with its spacing:
 *
 *     h1 + subtitle
 *     TODAY bar                  6 stats, evenly spread, change under each
 *     Day trail                  7 cards, mini cumulative curve, range buttons
 *     Filters                    labels ABOVE controls, COMPARE TO pushed right
 *     KPI row 1                  SPEND / SALES / ACOS / ROAS, with sparklines
 *     KPI row 2                  IMPRESSIONS / CLICKS / CTR / PURCHASES
 *     Branded vs Non-Branded     donut left, table right, 250px 1fr
 *     Profitability Analysis     flow line, then 3 + 3 cards
 *     Revenue, Ad Spend & Profit gold bars + red line + cyan line
 *     Profit/Click + Efficiency  two area charts with gradient shadows
 *     ACoS Heatmap + TACoS       3fr / 2fr
 *     Budget & Pacing            two stats, separator, bars + line
 *     ASIN Performance           grouped header table
 *
 * WHAT THE MOCKUP DRAWS THAT THE DATA CANNOT SUPPORT, AND WHAT IS DONE ABOUT IT
 * The Day trail's curve is "cumulative ad spend BY HOUR" and the heatmap is
 * day x hour. There are no hourly figures: Amazon refuses timeUnit HOURLY on
 * this report type -- measured, in its own words, "configuration timeUnit is
 * not supported for this report type". Hourly Amazon ad data comes from
 * Marketing Stream, which needs an AWS SQS queue.
 *
 * THAT IS NOT BEING BUILT, BY INSTRUCTION -- there is no AWS account:
 *
 *     "Skip Phase 4 entirely (AMS/AWS). Owner doesn't have an AWS account.
 *      Build the graceful degradation fallbacks instead"
 *
 * So these are not placeholders waiting on a queue; they are the screen. Each
 * is the same question asked at the grain that exists, and each says so in its
 * own caption rather than leaving the reader to assume hours:
 *
 *     TODAY bar    the latest COMPLETE day, labelled with its date and how far
 *                  behind Amazon is -- never "today" unless it really is
 *     Day trail    seven cards, each a curve of spend building across the
 *                  window. Briefly drawn as one bar per card and reverted at
 *                  the owner's request -- see ppcaTrail.
 *     Heatmap      ACoS by day of week, no hour axis
 *
 * Nothing is filled with invented hours -- that is the one thing these screens
 * have been told off for twice. domain/ams.py holds the on-ramp for the day an
 * AWS queue does appear; until then it reports absent and nothing calls it.
 *
 * NOTHING HERE WRITES. No bid, no budget, no campaign state (Rule 8).
 */

const PPCA = {data: null, loading: false, sort: "spend", desc: true,
              tab: "campaigns", q: ""};

async function ppcaLoad(){
  const host = document.getElementById("ppca_body");
  if(!host || PPCA.loading) return;
  PPCA.loading = true;
  // THE SCREEN DOES NOT GO BLANK WHILE A FILTER RELOADS.
  //
  //     "when i change the range the whole screen dissappears and then
  //      reappear after loading"
  //
  // It did, because this wiped innerHTML and put a spinner in its place. What
  // is on screen is still true until the new figures arrive -- it is simply
  // for a different window -- so it stays, dimmed slightly, with a small bar
  // saying what is happening. Only a FIRST load, with nothing to keep, draws
  // the spinner on its own.
  ppcaBusy(true);
  if(!PPCA.data){
    host.innerHTML = '<div class="ppc-page"><div style="padding:18px;'
      + 'color:var(--ppc-muted)"><span class="genspin"></span> '
      + 'Reading the advertising figures…</div></div>';
  }
  try{
    const qs = ppcQS(PPCWIN.start
      ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
    const j = await (await fetch("/ppc/analytics/overview?" + qs)).json();
    PPCA.loading = false;
    if(!j || !j.ok){
      host.innerHTML = '<div class="ppc-page"><div style="padding:18px;'
        + 'color:var(--ppc-red)">'
        + _pEsc((j && j.error) || "Could not read the advertising figures.")
        + '</div></div>';
      return;
    }
    PPCA.data = j;
    ppcaRender();
  }catch(e){
    PPCA.loading = false;
    ppcaBusy(false);
    if(!PPCA.data){
      host.innerHTML = '<div class="ppc-page"><div style="padding:18px;'
        + 'color:var(--ppc-red)">Could not read the advertising figures.'
        + '</div></div>';
    }else if(typeof toast === "function"){
      // The figures already on screen are still true, for the window they were
      // fetched for. Replacing them with an error would throw away something
      // correct to report something transient.
      toast("Could not refresh the advertising figures — showing the last ones.");
    }
  }
}

/* The dim-and-say-so state a filter change uses instead of a blank screen.
 *
 * WHOLLY DEFENSIVE. This is decoration around the real work, and a missing
 * element or an older browser must never be able to stop a render that would
 * otherwise have succeeded -- the figures matter, the dimming does not. */
function ppcaBusy(on){
  try{
    const host = document.getElementById("ppca_body");
    if(!host || typeof host.querySelector !== "function") return;
    const page = host.querySelector(".ppc-page");
    if(page && page.style) page.style.opacity = on ? "0.55" : "";
    let bar = document.getElementById("ppca_busy");
    if(on && !bar && page && typeof document.createElement === "function"){
      bar = document.createElement("div");
      bar.id = "ppca_busy";
      bar.className = "ppc-busy";
      bar.innerHTML = '<span class="genspin"></span> Updating…';
      if(typeof page.prepend === "function") page.prepend(bar);
      else if(typeof page.insertBefore === "function")
        page.insertBefore(bar, page.firstChild);
    }else if(!on && bar && typeof bar.remove === "function"){
      bar.remove();
    }
  }catch(e){ /* never let the busy state break the page */ }
}

function ppcaSort(key){
  if(PPCA.sort === key) PPCA.desc = !PPCA.desc;
  else { PPCA.sort = key; PPCA.desc = true; }
  ppcaRender();
}
function ppcaTab(t){ PPCA.tab = t; ppcaRender(); }
function ppcaFilter(v){ PPCA.q = (v || "").toLowerCase(); ppcaRender(); }

function ppcaRender(){
  const host = document.getElementById("ppca_body");
  const j = PPCA.data;
  if(!host || !j) return;
  const cur = j.currency || "GBP";
  const t = j.totals || {}, ch = j.change || {}, av = j.availability || {};

  let h = '<div class="ppc-page">'
    + '<h1>PPC Analytics</h1>'
    + '<p class="ppc-sub">Advertising spend, sales, efficiency, and campaign '
    + 'performance</p>';

  if(!t.has_data){
    // Which of the three reasons it is -- see ppcNoData. Saying "no data" to an
    // account that has no advertising login is how this page came to look
    // broken rather than empty.
    h += ppcNoData(av, "Every panel below this point needs advertising rows, so "
                     + "none of them is drawn. Nothing is missing from the page.");
    host.innerHTML = h + '</div>';
    return;
  }

  h += ppcaToday(j, cur);
  h += ppcaTrail(j, cur);
  h += ppcFilterRow(j, "ppcaLoad");
  h += ppcaKpis(j, cur, t, ch);
  h += ppcProductNote(av);
  h += ppcaBranded(j, cur);
  h += ppcaProfitability(j, cur);
  h += ppcaRevenueChart(j, cur);
  h += ppcaTrends(j, cur);
  h += ppcaHeatAndTacos(j, cur);
  h += ppcaBudget(j, cur);
  h += ppcaAsinTable(j, cur);

  host.innerHTML = h + '</div>';
  PPCA.loading = false;
  ppcaBusy(false);
  // Arm the draw-in animation on every chart just inserted, the same call the
  // Sales page makes. The hover and drag handlers are inline on the SVG that
  // salesCombo returns, so they need nothing.
  if(typeof altaChartsInView === "function"){
    try{ altaChartsInView(host); }catch(e){}
  }
}

function _ppcaRound1(v){ return Math.round(Number(v) * 10) / 10; }

/* Every chart on this page goes through the app's OWN engine.
 *
 *     "i can not interact with graphs when hover over or other features which i
 *      have in my other graphs, i.e. sales graph"
 *
 * Right: the first build drew bare SVG, which is a picture. salesCombo carries
 * the hover card, the drag-to-zoom and the clickable key that the Sales page
 * has had all along, and reusing it is also the only way these charts stay
 * identical to that one as it changes (Rule 12).
 *
 * The series KEYS matter: salescharts.js looks each one up in SC_SERIES for its
 * colour, its label and whether it is filled, so a chart here and a chart there
 * cannot end up drawing "Ad spend" in two different reds.
 */
/* A CHART IS DRAWN AT THE WIDTH OF THE BOX IT LANDS IN, not the page's.
 *
 *     "see how orbit renders graphs and how you, you have fucked the view"
 *
 * Every chart on this page measured `ppca_body` -- the whole page, about 1120px
 * -- including the ones that sit two-up in half-width panels. salesCombo then
 * writes viewBox="0 0 1120 210" with no preserveAspectRatio, so the browser
 * defaults to "xMidYMid meet": it scales the whole drawing down to fit the
 * ~500px panel, which is 45%, and CENTRES it vertically in the 210px box the
 * style height reserves.
 *
 * That is the entire fault, and it explains every part of what it looked like:
 *   a ~95px sliver of chart floating in the middle of a tall empty card;
 *   axis labels shrunk to 45% and unreadable;
 *   dates crushed together, because 30 labels were laid out for 1120px of room
 *   and then squeezed into 500.
 *
 * `frac` is the share of the page width the chart's panel actually occupies, so
 * the drawing is made the size it will be displayed at. At 1:1 there is no
 * scaling: the plot fills its card and the type comes out at its real size.
 */
function ppcaChart(o){
  if(typeof salesCombo !== "function") return "";
  const cols = o.columns || [];
  if(!cols.length) return "";
  // A series Amazon has sent nothing for is DROPPED, not drawn flat along the
  // floor -- salesCombo already does that for lines; this keeps a bars series
  // from claiming a row of zeros.
  const bars = (o.bars && (o.bars.values || []).some(function(v){
    return v !== null && v !== undefined; })) ? o.bars : null;
  const page = scChartWidth(o.host || "ppca_body", 1120);
  const frac = o.frac || 1;
  // The panel's own padding and the grid gap, which are inside the share but
  // outside the chart. Measured off ppc.css: 20px of panel padding each side,
  // 16px of grid gap.
  const chrome = (frac < 1) ? 56 : 40;
  const W = Math.max(240, Math.round(page * frac) - chrome);
  return salesCombo({
    id: o.id, onZoom: "ppcaZoomTo", columns: cols, unit: "day",
    bars: bars, lines: o.lines || [], currency: o.currency,
    width: W,
    height: o.height || 300,
  });
}

/* Dragging across any chart on this page narrows the window to those days.
 *
 * IT IS CALLED WITH TWO DIFFERENT KINDS OF ARGUMENT, which is what broke it:
 * salescharts hands a drag back as two COLUMN INDICES, while the day-trail
 * cards call it with two real dates. This treated both as dates, so a drag sent
 * start=23 and the server answered "Invalid isoformat string: '23'".
 * ppcZoomTo resolves either against the columns that chart was drawn with. */
function ppcaZoomTo(from, to, cid){
  ppcZoomTo(from, to, cid, "ppcaLoad");
}

/* ---- 1. the TODAY strip -------------------------------------------------- */
function ppcaToday(j, cur){
  const d = j.today || {};
  const n = d.now || {}, c = d.change || {};
  // Amazon's advertising figures for today are partial all day and arrive late,
  // so an empty strip before lunchtime is normal rather than a fault.
  const why = "Amazon has sent no advertising figures for today yet. They "
            + "arrive through the day and are complete only after it ends.";
  const stat = function(label, value, chg, good){
    const v = (chg === null || chg === undefined) ? null : Number(chg);
    const col = (v === null || v === 0) ? "var(--ppc-muted)"
      : (((good === "up") ? v > 0 : v < 0) ? "var(--ppc-green)" : "var(--ppc-red)");
    return '<div class="ppc-today-stat">'
      + '<div class="k">' + label + '</div>'
      + '<div class="v">' + value + '</div>'
      + '<div class="c" style="color:' + col + '">'
      +   (v === null
            ? '<span class="ppc-dash" title="Nothing stored for yesterday to '
              + 'compare against.">—</span>'
            : ((v > 0 ? "+" : "") + v.toFixed(1) + "%"))
      + '</div></div>';
  };
  // IT IS ONLY "TODAY" WHEN IT IS.
  //
  //     "the top banner of today ad spend adsales etc that is returning no
  //      data, that behavior is inaccurate"
  //
  // It was asking for today, and Amazon's advertising reports lag -- measured
  // on 6 Sep, the newest stored day was the 4th. Six dashes on an account with
  // plenty of data reads as "the advertising did nothing", which is false. The
  // strip now reports the latest day Amazon HAS sent, and says which day that
  // is and how far behind it is, so nobody reads it as this morning's.
  const lag = d.lag_days;
  const heading = d.is_today ? "TODAY"
    : (lag === 1 ? "YESTERDAY" : "LATEST DAY");
  const sub = !d.date ? "no advertising data"
    : (d.is_today ? _pEsc(d.date)
       : (_pEsc(d.date) + " · Amazon is " + lag + " day"
          + (lag === 1 ? "" : "s") + " behind"));
  return '<div class="ppc-today">'
    + '<div class="ppc-today-label"><b>' + heading + '</b><span title="'
    + 'Amazon publishes advertising figures a day or two in arrears, so the '
    + 'newest complete day is not usually today.">' + sub + '</span></div>'
    + stat("AD SPEND", ppcMoney0(n.spend, cur, why), c.spend, "down")
    + stat("AD SALES", ppcMoney0(n.sales, cur, why), c.sales, "up")
    + stat("TOTAL SALES", ppcMoney0(n.total_sales, cur, why), c.total_sales, "up")
    + stat("ACOS", ppcPct(n.acos_pct, why), c.acos_pct, "down")
    + stat("TACOS", ppcPct(n.tacos_pct, why), c.tacos_pct, "down")
    + stat("ROAS", ppcX(n.roas, why), c.roas, "up")
    + '</div>';
}

/* ---- 2. the day trail ---------------------------------------------------- */
function ppcaTrail(j, cur){
  const rows = j.trail || [];
  if(!rows.length) return "";
  // THE CURVE IS BACK, BY REQUEST.
  //
  //     "see day trail graphs that were real graphs earlier but in the recent
  //      edits you made the thick candles, please revert the day trails graph
  //      style"
  //
  // These were briefly one bar per card, scaled across the trail. The reasoning
  // was that a running total can only climb, so the last card always stands
  // tallest -- but a bar per card reads as a chunk rather than a graph, and the
  // owner has now seen both and prefers the curve. It is his screen.
  //
  // The tooltip still names the running total for what it is, so the shape is
  // not mistaken for the day's own spend, and the caption still says these are
  // days rather than the hours the mockup drew.
  const cum = rows.map(function(r){ return r.cumulative; });
  const MON = ["JAN","FEB","MAR","APR","MAY","JUN",
               "JUL","AUG","SEP","OCT","NOV","DEC"];
  const DOW = ["SUN","MON","TUE","WED","THU","FRI","SAT"];

  let h = '<div style="display:flex;align-items:center;justify-content:'
    + 'space-between;margin-bottom:4px;flex-wrap:wrap;gap:8px">'
    + '<div><div style="font-size:18px;font-weight:700">Day trail</div>'
    + '<div style="font-size:12px;color:var(--ppc-muted)">Ad spend building up '
    + 'across the window · Amazon publishes no hourly figures for this report, '
    + 'so each curve is days rather than hours</div></div>'
    + ppcSeg(30, "ppcaLoad") + '</div>'
    + '<div class="ppc-trail">';

  rows.forEach(function(r, i){
    const day = new Date(r.date + "T00:00:00");
    const lbl = isNaN(day.getTime()) ? r.date
      : (DOW[day.getDay()] + " " + MON[day.getMonth()] + " " + day.getDate());
    // EVERY CARD ANSWERS ON HOVER AND OPENS ON CLICK.
    //
    //     "day trail graph also dont interact like other graphs"
    //
    // These are 120px wide, so a full hover card would be bigger than the
    // thing it describes -- but a card that reports nothing at all is the
    // complaint. So each carries its own figures as a native tooltip, and
    // clicking one narrows the whole page to that day, which is what the
    // drag-zoom does on the big charts.
    const tip = [
      r.date,
      "Spend: " + (r.spend === null || r.spend === undefined
                   ? "no row stored" : ppcMoney(r.spend, cur)),
      "Orders: " + (r.orders === null || r.orders === undefined
                    ? "—" : Math.round(r.orders)),
      // The running total is still worth having -- it is just not what the bar
      // draws any more, so it is named for what it is rather than implied by a
      // climbing line.
      "Spent so far this window: " + ppcMoney(r.cumulative, cur),
      "", "Click to show this day only.",
    ].join("\n");
    h += '<div class="ppc-trail-card" title="' + _pEsc(tip) + '" '
      + 'onclick="ppcaZoomTo(' + jsArg(r.date) + ',' + jsArg(r.date) + ')">'
      + '<div class="ppc-trail-head"><span class="d">' + _pEsc(lbl) + '</span>'
      +   (r.today ? '<span class="t">Today</span>' : '') + '</div>'
      + '<div class="ppc-trail-chart">'
      +   ppcMiniLine(cum.slice(0, i + 1), "var(--ppc-cyan)") + '</div>'
      + '<div class="ppc-trail-spend">'
      +   ppcMoney(r.spend, cur, "No advertising row stored for this day. That "
          + "is not the same as having spent nothing.") + '</div>'
      + '<div class="ppc-trail-units">'
      +   (r.orders === null || r.orders === undefined ? "—"
           : (Math.round(r.orders) + " order"
              + (Math.round(r.orders) === 1 ? "" : "s")))
      + '</div></div>';
  });
  return h + '</div>';
}

/* ---- 3. the two KPI rows ------------------------------------------------- */
function ppcaKpis(j, cur, t, ch){
  const d = j.daily || [];
  const col = function(k){ return d.map(function(r){ return r[k]; }); };
  // WHICH UNIT EACH ARROW IS IN, decided by the server so every screen agrees.
  // ACOS and CTR are already percentages and move in POINTS; spend, sales,
  // clicks and impressions move in per cent. 24.3% to 28.4% is +4.1pts, and
  // calling it +16.9% answers a question nobody asked.
  const cu = j.change_units || {};

  return '<div class="ppc-kpis">'
    + ppcKpi({label: "SPEND", value: ppcMoney0(t.spend, cur),
              change: ppcChangeBare(ch.spend, "down", "", cu.spend),
              spark: ppcSparkline(col("spend"), "var(--ppc-red)"),
              help: "What Amazon charged for the ads in this window."})
    + ppcKpi({label: "SALES", value: ppcMoney0(t.sales, cur),
              change: ppcChangeBare(ch.sales, "up", "", cu.sales),
              spark: ppcSparkline(col("ad_sales"), "var(--ppc-green)"),
              help: "Sales Amazon attributes to those ads. An organic sale is "
                  + "not in here."})
    + ppcKpi({label: "ACOS", value: ppcPct(t.acos_pct),
              change: ppcChangeBare(ch.acos_pct, "down", "", cu.acos_pct),
              spark: ppcSparkline(col("acos_pct"), "var(--ppc-orange)"),
              help: "Spend divided by AD sales. How much of the advertised "
                  + "revenue the advertising ate. Lower is better."})
    + ppcKpi({label: "ROAS", value: ppcX(t.roas),
              change: ppcChangeBare(ch.roas, "up", "", cu.roas),
              spark: ppcSparkline(col("roas"), "var(--ppc-blue)"),
              help: "Ad sales for every pound of spend."})
    + '</div>'
    + '<div class="ppc-kpis last">'
    + ppcKpi({label: "IMPRESSIONS", value: ppcNum(t.impressions),
              change: ppcChangeBare(ch.impressions, "up", "", cu.impressions),
              spark: ppcSparkline(col("impressions"), "var(--ppc-blue)"),
              help: "How many times the ads were shown."})
    + ppcKpi({label: "CLICKS", value: ppcNum(t.clicks),
              change: ppcChangeBare(ch.clicks, "up", "", cu.clicks),
              spark: ppcSparkline(col("clicks"), "var(--ppc-green)"),
              help: "How many times somebody clicked one."})
    + ppcKpi({label: "CTR", value: ppcPct(t.ctr_pct, "", 2),
              change: ppcChangeBare(ch.ctr_pct, "up", "", cu.ctr_pct),
              spark: ppcSparkline(col("ctr_pct"), "var(--ppc-magenta)"),
              help: "Clicks per impression."})
    + ppcKpi({label: "PURCHASES", value: ppcNum(t.orders),
              change: ppcChangeBare(ch.orders, "up", "", cu.orders),
              spark: ppcSparkline(col("orders"), "var(--ppc-green)"),
              help: "Orders Amazon attributes to the ads."})
    + '</div>';
}

/* ---- 4. branded vs non-branded ------------------------------------------ */
function ppcaBranded(j, cur){
  const b = j.branded || {};
  const head = '<div class="ppc-panel">'
    + '<div class="ppc-panel-title">Branded vs Non-Branded Analysis</div>';

  if(b.why || (!b.branded && !b.non_branded)){
    // ppc_view.is_branded answers NULL, not False, when no brand words are set
    // -- "not set up: not 'no', which is a claim". A donut here would show a
    // confident 0% branded for an account that never typed its brand in.
    return head + '<div style="font-size:12px;color:var(--ppc-muted);'
      + 'line-height:1.6">' + _pEsc(b.why || "Nothing to split yet.")
      + '</div></div>';
  }

  const br = b.branded || {}, nb = b.non_branded || {};
  const totSpend = (br.spend || 0) + (nb.spend || 0);
  const totSales = (br.sales || 0) + (nb.sales || 0);
  const share = function(v, tot){
    if(v === null || v === undefined || !tot) return "";
    return ' <span style="color:var(--ppc-muted);font-size:12px">('
      + Math.round(100 * v / tot) + '%)</span>';
  };
  const row = function(metric, x, y, fmt){
    return '<tr style="border-top:1px solid var(--ppc-border)">'
      + '<td style="padding:10px 0;color:var(--ppc-muted);text-align:left">'
      +   metric + '</td>'
      + '<td style="padding:10px 0;text-align:center">' + fmt(x) + '</td>'
      + '<td style="padding:10px 0;text-align:right;color:var(--ppc-orange)">'
      +   fmt(y) + '</td></tr>';
  };

  // WHAT IT MATCHED ON, PRINTED. "it is not showing me which keyword is it
  // assuming as branded" -- a split into two lanes with no statement of the
  // rule cannot be checked, and a wrong brand list looks exactly like a wrong
  // sum. The words, the share they caught, and the biggest terms they caught,
  // so the list can be judged at a glance.
  let rule = "";
  if(b.rule){
    const chips = (b.brand_words || []).map(function(w){
      return '<code style="background:var(--ppc-surface);border:1px solid '
        + 'var(--ppc-border);border-radius:4px;padding:1px 5px;margin-right:4px">'
        + _pEsc(w) + '</code>';
    }).join("");
    const eg = (b.matched_examples || []).slice(0, 5).map(function(x){
      return _pEsc(x.term);
    }).join(" · ");
    rule = '<div class="ppc-note' + (b.warning ? " warn" : "") + '" '
      + 'style="margin:0 0 14px">'
      + '<b>Brand words:</b> ' + (chips || '<i>none</i>')
      + '<div style="margin-top:5px">' + _pEsc(b.rule) + '</div>'
      + (eg ? '<div style="margin-top:5px;color:var(--ppc-muted)">Caught, '
              + 'biggest spend first: ' + eg + '</div>' : "")
      + (b.warning ? '<div style="margin-top:5px;color:var(--ppc-orange)">'
                     + _pEsc(b.warning) + '</div>' : "")
      + '</div>';
  }

  return head + rule
    + '<div style="display:grid;grid-template-columns:250px 1fr;gap:24px;'
    + 'align-items:start">'
    + '<div style="display:flex;justify-content:center;padding-top:10px">'
    +   ppcDonut([{label: "Branded", value: br.spend || 0,
                   colour: "var(--ppc-blue)"},
                  {label: "Non-Branded", value: nb.spend || 0,
                   colour: "var(--ppc-orange)"}], 170)
    + '</div>'
    + '<table style="width:100%;border-collapse:collapse">'
    + '<thead><tr>'
    + '<th style="text-align:left;font-size:12px;color:var(--ppc-muted);'
    +   'padding:8px 0;font-weight:600;text-transform:uppercase;width:30%">'
    +   'Metric</th>'
    + '<th style="text-align:center;font-size:12px;color:var(--ppc-blue);'
    +   'padding:8px 0;font-weight:600;text-transform:uppercase;width:35%">'
    +   'Branded</th>'
    + '<th style="text-align:right;font-size:12px;color:var(--ppc-orange);'
    +   'padding:8px 0;font-weight:600;text-transform:uppercase;width:35%">'
    +   'Non-Branded</th>'
    + '</tr></thead><tbody>'
    + row("Spend", br.spend, nb.spend, function(v){
        return ppcMoney(v, cur) + share(v, totSpend); })
    + row("Sales", br.sales, nb.sales, function(v){
        return ppcMoney(v, cur) + share(v, totSales); })
    + row("ACoS", br.acos_pct, nb.acos_pct, function(v){ return ppcPct(v); })
    + row("RoAS", br.roas, nb.roas, function(v){ return ppcX(v); })
    + row("CVR", br.cvr_pct, nb.cvr_pct, function(v){ return ppcPct(v, "", 2); })
    + '</tbody></table></div>'
    + '<div style="display:flex;justify-content:space-between;align-items:center;'
    + 'margin-top:14px;flex-wrap:wrap;gap:8px">'
    + '<div style="display:flex;gap:20px;font-size:12px;color:var(--ppc-muted)">'
    +   '<span><span style="color:var(--ppc-blue)">●</span> Branded</span>'
    +   '<span><span style="color:var(--ppc-orange)">●</span> Non-Branded</span>'
    + '</div>'
    + '<div style="font-size:11px;color:var(--ppc-muted)">'
    +   (b.branded_terms || 0) + ' branded terms · '
    +   (b.non_branded_terms || 0) + ' non-branded terms</div>'
    + '</div></div>';
}

/* ---- 5. profitability --------------------------------------------------- */
function ppcaProfitability(j, cur){
  const r = j.rates || {}, t = j.totals || {}, w = j.wasted || {};
  const wp = j.wasted_previous || {};
  const win = j.window || {};
  const be = r.breakeven_acos_pct, acos = t.acos_pct;
  const period = _pEsc((win.start || "") + " – " + (win.end || ""));

  // The mockup's flow line: stock → fees → break-even | verdict.
  let flow = '<div style="font-size:13px;color:var(--ppc-muted);'
    + 'margin-bottom:20px;display:flex;gap:10px;flex-wrap:wrap;'
    + 'align-items:center">'
    + '<span>Stock cost: <strong style="color:var(--ppc-text)">'
    +   ppcPct(r.cogs_rate === null || r.cogs_rate === undefined
               ? null : r.cogs_rate * 100) + '</strong></span>'
    + '<span style="color:var(--ppc-dim)">→</span>'
    + '<span style="color:var(--ppc-orange)">Amazon fees: <strong>'
    +   ppcPct(r.fee_rate === null || r.fee_rate === undefined
               ? null : r.fee_rate * 100) + '</strong> (measured)</span>'
    + '<span style="color:var(--ppc-dim)">→</span>'
    + '<span>Break-even ACOS: <strong style="color:var(--ppc-text)">'
    +   ppcPct(be) + '</strong><span class="ppc-i" title="What is left of a '
    +   'pound of revenue after Amazon\'s fee and the stock. Spend more than '
    +   'this on an ad and the sale loses money.">ⓘ</span></span>';
  if(be !== null && be !== undefined && acos !== null && acos !== undefined){
    const ok = acos < be;
    flow += '<span style="color:var(--ppc-dim)">|</span>'
      + '<span style="color:' + (ok ? "var(--ppc-green)" : "var(--ppc-red)")
      + ';font-weight:600">ACOS: ' + ppcPct(acos) + ' — '
      + (ok ? "Profitable" : "Losing money") + '</span>';
  }
  flow += '</div>';

  // WASTED SPEND SHOWS NO CHANGE, AND THAT IS THE HONEST ANSWER.
  //
  // The mockup puts a falling-is-good arrow here, and this used to draw one by
  // comparing wasted spend against "the previous period". Both calls read the
  // stored Search Term Report, which is ONE fixed window with no day-by-day
  // breakdown -- so both returned the identical figure and the arrow read zero
  // for ever. Measured across 7, 14, 30 and 90 days: 251.56 every time.
  //
  // An arrow that cannot move is not information. The card states the window the
  // figure really covers instead, which is the thing somebody actually needs to
  // know about it.
  const wchange = (w.comparable === false) ? null : null;
  const wpct = (w.spend !== null && w.spend !== undefined && t.spend)
    ? _ppcaRound1(100 * w.spend / t.spend) : null;

  let net = null;
  if(r.fee_rate !== null && r.fee_rate !== undefined
     && r.cogs_rate !== null && r.cogs_rate !== undefined
     && t.sales !== null && t.sales !== undefined
     && t.spend !== null && t.spend !== undefined){
    net = Math.round((t.sales - t.spend - t.sales * r.fee_rate
                      - t.sales * r.cogs_rate) * 100) / 100;
  }
  // PROFIT AFTER ADVERTISING, from the server. See the NET PROFIT card below.
  const np = j.net_profit || {};
  const npv = (np.net_profit === undefined) ? null : np.net_profit;

  // PROFIT PER CLICK STAYS AD-ONLY, DELIBERATELY. A click buys an advertised
  // sale, not the organic ones, so dividing the whole account's contribution by
  // the clicks would credit advertising with revenue it did not bring. `net`
  // above is the ad-only figure and remains the right numerator for this one.
  const perClick = (net !== null && t.clicks)
    ? Math.round((net / t.clicks) * 1000) / 1000 : null;
  const eff = (be && acos) ? _ppcaRound1(100 * be / acos) : null;
  const effBadge = (eff === null) ? "" :
    '<span class="ppc-verdict '
    + (eff >= 100 ? "good" : eff >= 70 ? "watch" : "poor") + '">'
    + (eff >= 100 ? "Good" : eff >= 70 ? "Watch" : "Poor") + '</span>';

  return '<div class="ppc-panel">'
    + '<div class="ppc-panel-title-lg">Profitability Analysis</div>'
    + flow
    + '<div class="ppc-grid3 ppc-mb12">'
    +   ppcSubCard({label: "TACOS", value: ppcPct(t.tacos_pct),
                    change: ppcChangeText((j.change || {}).tacos_pct, "down", "", (j.change_units||{}).tacos_pct),
                    note: period,
                    // The divisor is stated, because it is NOT simply the
                    // window's sales: Amazon's advertising feed runs about two
                    // days behind its sales feed, so the ratio is taken over
                    // the days that have both. Dividing by days the spend
                    // cannot cover reports a TACOS that is too low.
                    note2: (t.tacos_note
                            ? '<span style="color:var(--ppc-orange)">'
                              + _pEsc(t.tacos_note) + '</span>' : ""),
                    help: "Spend divided by ALL sales, advertised and organic "
                        + "together, over the days that have advertising "
                        + "figures. Rising is bad — advertising is taking a "
                        + "larger share of the whole business."})
    +   ppcSubCard({label: "WASTED SPEND",
                    value: ppcMoney0(w.spend, cur, w.why), why: w.why,
                    change: (wchange === null ? "" :
                             ppcChangeText(wchange, "down")),
                    note: (wpct === null ? period
                           : (wpct.toFixed(1) + "% of total spend")),
                    note2: (w.terms ? (w.terms + " terms clicked, none ordered"
                             + (w.report_start ? (" · from the search-term "
                                + "report covering " + _pEsc(w.report_start)
                                + " to " + _pEsc(w.report_end)) : ""))
                                    : ""),
                    help: "Spend on search terms that took at least one click "
                        + "and produced no order. Not 'ACOS above target' — "
                        + "that is a judgement about price. This is money that "
                        + "bought traffic which bought nothing. "
                        + (w.comparable_why || "")})
    +   ppcSubCard({label: "BREAK-EVEN ACOS", value: ppcPct(be),
                    note: ((be !== null && be !== undefined
                            && acos !== null && acos !== undefined)
                      ? ('<span style="color:' + (acos < be ? "var(--ppc-green)"
                          : "var(--ppc-red)") + '">Current ACOS: '
                         + ppcPct(acos) + ' — '
                         + (acos < be ? "Profitable" : "Losing money") + '</span>')
                      : _pEsc(r.cogs_basis || "")),
                    help: "Measured from this account's own fee and stock "
                        + "rates, not a rule of thumb. A 60%-margin product "
                        + "and a 15%-margin one do not stop being worth "
                        + "advertising at the same ACOS."})
    + '</div>'
    + '<div class="ppc-grid3">'
    +   ppcSubCard({label: "PROFIT / CLICK",
                    value: (perClick === null ? null : ppcMoney(perClick, cur)),
                    why: "Needs both a measured fee rate and a measured stock "
                       + "cost, and clicks in the window.",
                    note: period,
                    help: "Estimated profit for the window, divided by the "
                        + "clicks that were paid for."})
    +   _ppcaEfficiencyCard(j, eff, effBadge)
    // NET PROFIT IS THE SALES PAGE'S OWN PROFIT, LESS AD SPEND.
    //
    //     "when i go to sales report i see i made 102 pounds in profit in the
    //      last 30 days and when i go to ppc analytics it shows profit in minus"
    //
    // It used to be attributed sales less spend less rates -- PPC-only, ignoring
    // organic revenue completely. The Sales page counts all revenue and takes
    // nothing off for ads. Two different questions, both labelled "profit", one
    // click apart, and easily on opposite sides of zero.
    //
    // The spec settles it (section 5): net profit is the TOTAL account
    // contribution, ad and organic, minus ad spend. Worked out server-side by
    // asking the Sales page's own function, so the two cannot drift again.
    +   ppcSubCard({label: "NET PROFIT",
                    value: (npv === null ? null : ppcMoney0(npv, cur)),
                    colour: (npv === null ? "" : (npv >= 0 ? "var(--ppc-green)"
                                                           : "var(--ppc-red)")),
                    // The server names the reason -- usually uncosted units --
                    // because a dash on a profit card reads as a broken screen
                    // rather than as a deliberate refusal.
                    why: (np.why || "Needs the account's measured rates."),
                    // A MONTHLY CHARGE LANDING IN A SHORT WINDOW IS NOT A BAD
                    // WEEK. Amazon sends the subscription fee with no date, so
                    // it is filed on whichever day the figures were last
                    // pulled. Over two days it IS the figure -- measured on
                    // nestwell_goods, £30.00 on a day that sold nothing, giving
                    // a confident -£30.00 for an account that traded fine.
                    // The total is right; this says which part of it is a
                    // calendar artefact rather than trading.
                    note2: (np.note
                            ? ('<span style="color:var(--ppc-orange)">'
                               + _pEsc(np.note) + ' Without it: '
                               + ppcMoney0(np.net_profit_excl_undated, cur)
                               + '.</span>')
                            : ""),
                    note: period,
                    help: "Everything the account sold in this window, "
                        + "advertised AND organic, less Amazon's fees, less "
                        + "what the stock cost, less the advertising spend. "
                        + "This is the Sales page's profit with the ad spend "
                        + "taken off, so the two screens agree."
                        + (np.sales_profit !== null && np.sales_profit !== undefined
                           ? " Sales page profit " + ppcMoney0(np.sales_profit, cur)
                             + " − ad spend " + ppcMoney0(np.ad_spend, cur) + "."
                           : "")})
    + '</div></div>';
}

/* THE HEADLINE EFFICIENCY SCORE, WITH ITS WORKING SHOWN.
 *
 * Three parts, weighted 0.50 / 0.30 / 0.20 -- how far ACOS sits under
 * break-even, how normal the conversion rate is against its own history, and
 * how little of the spend bought clicks and no orders. Bands: under 50 poor,
 * 50-75 average, over 75 good.
 *
 * A single 0-100 number is the kind of thing people act on without asking how it
 * was made, so every part, its weight and its reasoning are on the hover. And
 * when one part cannot be measured the score is NOT shown: two legs out of three
 * looks exactly like a real score and is not one.
 *
 * The older ratio -- break-even over actual ACOS -- is still the DAILY trend
 * below, which answers a narrower question and is a shape rather than a verdict.
 */
function _ppcaEfficiencyCard(j, eff, effBadge){
  const s = j.efficiency_score || {};
  if(s.score === null || s.score === undefined){
    return ppcSubCard({
      label: "EFFICIENCY SCORE", value: null,
      why: s.why || "One of its three parts could not be measured.",
      note: _pEsc(s.why || ""),
      help: "Three parts, weighted: 50% how far ACOS sits under break-even, "
          + "30% how normal the conversion rate is against its own history, "
          + "20% how little of the spend bought clicks and no orders. Not shown "
          + "unless all three can be measured — a score built on two of them "
          + "looks identical to a real one."});
  }
  const p = s.parts || {};
  const line = function(k, label){
    const x = p[k];
    if(!x) return "";
    return label + " " + Number(x.value).toFixed(0) + " × "
      + Number(x.weight).toFixed(2) + " — " + x.why;
  };
  return ppcSubCard({
    label: "EFFICIENCY SCORE",
    value: Number(s.score).toFixed(2),
    badge: '<span class="ppc-opp ' + (s.band === "Good" ? "hi" : "lo")
         + '">' + _pEsc(s.band) + '</span>',
    note: _pEsc("under 50 poor · 50-75 average · over 75 good"),
    note2: _pEsc((p.wasted || {}).why || ""),
    help: "Our own measure, and here is all of it:\n"
        + line("acos", "· ACOS part") + "\n"
        + line("cvr", "· conversion part") + "\n"
        + line("wasted", "· waste part") + "\n"
        + "Weighted 0.50 / 0.30 / 0.20 and added. Every input is Amazon's own "
        + "figure; the weighting is ours."});
}

/* ---- 6. revenue, ad spend and profit ------------------------------------ */
function ppcaRevenueChart(j, cur){
  const d = j.daily || [];
  if(!d.length) return "";
  const r = j.rates || {};
  const canProfit = (r.fee_rate !== null && r.fee_rate !== undefined
                     && r.cogs_rate !== null && r.cogs_rate !== undefined);
  const profit = d.map(function(x){
    if(!canProfit || x.ad_sales === null || x.spend === null) return null;
    return Math.round((x.ad_sales - x.spend - x.ad_sales * r.fee_rate
                       - x.ad_sales * r.cogs_rate) * 100) / 100;
  });
  const lines = [{key: "ad_spend",
                  values: d.map(function(x){ return x.spend; })}];
  if(canProfit) lines.push({key: "ad_profit", values: profit});

  return '<div class="ppc-panel">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
    +   '<span class="ppc-panel-title" style="margin:0">Revenue, Ad Spend '
    +   '&amp; Profitability</span>'
    +   '<span class="ppc-i" title="Total sales as bars, with what the '
    +   'advertising cost and returned over them. A gap is a day with nothing '
    +   'stored, not a day of no spend.">ⓘ</span></div>'
    // NO INSTRUCTION LINE. Removed by request across the app -- the gestures
    // are unchanged, only the sentence advertising them is gone. The reference
    // screen has none of these either.
    + ppcaChart({id: "ppca_rev", columns: d.map(function(x){ return x.date; }),
                 bars: {key: "total_sales", label: "Total revenue",
                        values: d.map(function(x){ return x.total_sales; })},
                 lines: lines, currency: cur, height: 300})
    + '</div>';
}

/* ---- 7. the two trend charts -------------------------------------------- */
function ppcaTrends(j, cur){
  const d = j.daily || [];
  const cols = d.map(function(x){ return x.date; });
  const pc = j.per_click, eff = j.efficiency;
  const sym = (cur === "USD") ? "$" : (cur === "EUR") ? "€" : "£";

  const panel = function(title, help, body){
    return '<div class="ppc-panel ppc-panel-sm" style="margin-bottom:0">'
      + '<div class="ppc-panel-title-sm">' + title
      + '<span class="ppc-i" title="' + _pEsc(help) + '">ⓘ</span></div>'
      + body + '</div>';
  };
  const missing = function(text){
    return '<div style="font-size:12px;color:var(--ppc-muted);line-height:1.6">'
      + _pEsc(text) + '</div>';
  };

  const left = (pc && pc.some(function(v){ return v !== null; }))
    // HALF THE PAGE: these two sit side by side in .ppc-grid2. Drawn at the
    // page's full width they were scaled to 45% and floated in a half-empty
    // card -- see the note on ppcaChart.
    ? ppcaChart({id: "ppca_pc", columns: cols, currency: cur, height: 250,
                 frac: 0.5,
                 lines: [{key: "cpc", label: "Profit per click", values: pc}]})
    : missing((j.rates || {}).why || "Profit per click needs a measured fee "
        + "rate and a measured stock cost. Without both there is no honest way "
        + "to say what a click earned.");

  const right = (eff && eff.some(function(v){ return v !== null; }))
    ? ppcaChart({id: "ppca_eff", columns: cols, height: 250, frac: 0.5,
                 lines: [{key: "roas", label: "Efficiency score", values: eff}]})
    : missing("The efficiency score is the day's ACOS against this account's "
        + "break-even ACOS, and neither can be measured for this window.");

  return '<div class="ppc-grid2 ppc-mb16">'
    + panel("Profit per Click Trend",
            "Estimated profit for the day, divided by the clicks paid for. The "
            + "dashed line is zero: below it, each click cost more than it "
            + "brought in.", left)
    + panel("Spend Efficiency Score Trend",
            "100 × break-even ACOS ÷ the day's ACOS. The dashed line is 100 — "
            + "break-even. Our own measure, so it is defined rather than "
            + "borrowed.", right)
    + '</div>';
}

/* ---- 8. heatmap + TACoS -------------------------------------------------- */
/* ACoS BY DAY OF WEEK, WHICH IS A HEATMAP THIS DATA CAN ACTUALLY FILL.
 *
 * The mockup's grid is day x HOUR, and there are no hourly figures -- Amazon
 * refuses timeUnit HOURLY on this report. The first build therefore drew an
 * empty grid and a paragraph, which is honest and useless.
 *
 * Every stored day HAS a day of the week, so the same question -- when does the
 * advertising convert -- is answerable one step coarser. Rows are Mon..Sun,
 * columns are the weeks of the window, and each cell is that day's ACOS.
 *
 * SHADED BY BAND, NOT BY RANK. The hourly sales heatmap scales each row against
 * its own peak, which is right for volume: a product selling three a day still
 * has a best hour. ACOS is not volume -- 25% is good and 80% is bad whatever
 * the rest of the grid looks like -- so the mockup's four bands are used as
 * absolutes, and the legend under it means what it says.
 */
function ppcaHeatmap(daily){
  const rows = (daily || []).filter(function(x){
    return x.acos_pct !== null && x.acos_pct !== undefined;
  });
  if(rows.length < 3) return null;

  const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const weeks = [];            // [{label, cells: [7]}]
  const byKey = {};
  (daily || []).forEach(function(x){
    const dt = new Date(x.date + "T00:00:00");
    if(isNaN(dt.getTime())) return;
    const dow = (dt.getDay() + 6) % 7;                 // Monday = 0
    const monday = new Date(dt);
    monday.setDate(dt.getDate() - dow);
    const wk = monday.toISOString().slice(0, 10);
    if(!byKey[wk]){
      byKey[wk] = {label: wk, cells: new Array(7).fill(null)};
      weeks.push(byKey[wk]);
    }
    byKey[wk].cells[dow] = x;
  });
  weeks.sort(function(a, b){ return a.label < b.label ? -1 : 1; });

  const band = function(a){
    if(a === null || a === undefined) return null;
    if(a < 26) return "var(--ppc-heat1)";
    if(a < 35) return "var(--ppc-heat2)";
    if(a < 43) return "var(--ppc-heat3)";
    return "var(--ppc-heat4)";
  };
  const MON = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"];

  let h = '<div style="overflow-x:auto"><table class="ppc-heat"><thead><tr>'
    + '<th style="width:40px"></th>';
  weeks.forEach(function(w){
    const d = new Date(w.label + "T00:00:00");
    h += '<th>' + (isNaN(d.getTime()) ? _pEsc(w.label)
                   : (MON[d.getMonth()] + " " + d.getDate())) + '</th>';
  });
  h += '</tr></thead><tbody>';
  DOW.forEach(function(name, i){
    h += '<tr><td class="day">' + name + '</td>';
    weeks.forEach(function(w){
      const x = w.cells[i];
      const c = x ? band(x.acos_pct) : null;
      // A day with no advertising row draws an EMPTY cell, not a green one.
      // Green would say the advertising did well that day.
      const tip = x
        ? (x.date + " — ACOS " + Number(x.acos_pct).toFixed(1) + "%"
           + (x.spend !== null && x.spend !== undefined
              ? ", spent " + Number(x.spend).toFixed(2) : ""))
        : "no advertising figures stored for this day";
      h += '<td><div class="cell" title="' + _pEsc(tip) + '" style="background:'
        + (c || "transparent") + '"></div></td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table></div>'
    + '<div style="display:flex;gap:14px;margin-top:10px;font-size:11px;'
    + 'color:var(--ppc-muted);flex-wrap:wrap">'
    + [["var(--ppc-heat1)", "<26%"], ["var(--ppc-heat2)", "<35%"],
       ["var(--ppc-heat3)", "<43%"], ["var(--ppc-heat4)", ">43%"]]
      .map(function(l){
        return '<span style="display:flex;align-items:center;gap:4px">'
          + '<span style="width:12px;height:12px;border-radius:2px;background:'
          + l[0] + ';display:inline-block"></span>' + l[1] + '</span>';
      }).join("")
    + '</div>';
  return h;
}

function ppcaHeatAndTacos(j, cur){
  const d = j.daily || [];
  const av = j.availability || {};
  const grid = ppcaHeatmap(d);

  const heat = '<div class="ppc-panel ppc-panel-sm" style="margin-bottom:0">'
    + '<div class="ppc-panel-title-sm">ACoS heatmap — day of week'
    + '<span class="ppc-i" title="Which days the advertising converts. Hover a '
    + 'cell for that day\'s ACOS and spend.">ⓘ</span></div>'
    + '<div style="font-size:11.5px;color:var(--ppc-muted);line-height:1.6;'
    + 'margin-bottom:10px">'
    + (grid
        ? 'One cell per day, shaded by its ACOS band. The mockup asks for day × '
          + 'hour; Amazon publishes no hourly figures for this report, so this '
          + 'is the same question one step coarser — and every cell is measured.'
        : _pEsc((av.hourly && av.hourly.why) || ""))
    + '</div>'
    + (grid || '<div style="font-size:12px;color:var(--ppc-muted)">Not enough '
               + 'days with an ACOS in this window to draw one.</div>')
    + '</div>';

  const tacos = d.map(function(x){ return x.tacos_pct; });
  const hasT = tacos.some(function(v){ return v !== null; });
  const tp = '<div class="ppc-panel ppc-panel-sm" style="margin-bottom:0">'
    + '<div class="ppc-panel-title-sm">TACoS over time</div>'
    + (hasT
        // TWO FIFTHS: the heatmap and this share a 3fr / 2fr row.
        ? ppcaChart({id: "ppca_tacos", height: 250, frac: 0.4,
                     columns: d.map(function(x){ return x.date; }),
                     lines: [{key: "tacos", values: tacos}]})
        : '<div style="font-size:12px;color:var(--ppc-muted)">No total sales '
          + 'are stored for these days, so advertising cannot be compared '
          + 'against them.</div>')
    + '</div>';

  return '<div class="ppc-grid-3-2 ppc-mb16">' + heat + tp + '</div>';
}

/* ---- 9. budget and pacing ------------------------------------------------ */
function ppcaBudget(j, cur){
  const d = j.daily || [];
  const t = j.totals || {};
  if(!d.length) return "";
  const days = t.days || d.length || 1;
  const avgSpend = (t.spend === null || t.spend === undefined)
    ? null : t.spend / days;
  const avgSales = (t.total_sales === null || t.total_sales === undefined)
    ? null : t.total_sales / days;

  const refs = [];
  if(avgSales !== null) refs.push({value: avgSales, colour: "var(--ppc-green)",
                                   label: "Avg Sales", side: "left"});
  if(avgSpend !== null) refs.push({value: avgSpend, colour: "var(--ppc-red)",
                                   label: "Avg Spend", side: "right"});

  return '<div class="ppc-panel">'
    + '<div class="ppc-panel-title">Budget &amp; Pacing'
    + '<span class="ppc-i" title="What was spent against what came in, day by '
    + 'day, with each one\'s average marked.">ⓘ</span></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:32px">'
    + '<div><div style="font-size:11px;color:var(--ppc-green);'
    +   'text-transform:uppercase;font-weight:600">Total spend</div>'
    +   '<div style="font-size:28px;font-weight:700">'
    +   ppcMoney0(t.spend, cur) + '</div>'
    +   '<div style="font-size:12px;color:var(--ppc-muted)">'
    +   (avgSpend === null ? "—" : ppcMoney(avgSpend, cur) + "/day avg")
    +   '</div></div>'
    + '<div><div style="font-size:11px;color:var(--ppc-muted);'
    +   'text-transform:uppercase;font-weight:600">Total sales</div>'
    +   '<div style="font-size:28px;font-weight:700">'
    +   ppcMoney0(t.total_sales, cur) + '</div>'
    +   '<div style="font-size:12px;color:var(--ppc-muted)">'
    +   (avgSales === null ? "—" : ppcMoney(avgSales, cur) + "/day avg")
    +   '</div></div></div>'
    + '<div style="height:1px;background:var(--ppc-border);margin:16px 0"></div>'
    // The one thing this line said that was not an instruction -- what the
    // reference lines mean -- moves onto the chart's own ⓘ, where it belongs.
    + ''
    + ppcaChart({id: "ppca_budget", height: 260, currency: cur,
                 columns: d.map(function(x){ return x.date; }),
                 bars: {key: "total_sales", label: "Sales",
                        values: d.map(function(x){ return x.total_sales; })},
                 lines: [{key: "ad_spend",
                          values: d.map(function(x){ return x.spend; })}]})
    + '</div>';
}

/* ---- 10. ASIN performance ------------------------------------------------
 *
 * The mockup's grouped header: a thin row above the columns reading
 * (blank) | PROFIT | TRAFFIC across five | PAID across four.
 *
 * The two halves are different reports and mean different things -- CVR here is
 * the LISTING's units per session from the Business Report, not the ad's orders
 * per click. Two conversion rates in one column would be meaningless, so the
 * column says which.
 */
function ppcaAsinTable(j, cur){
  let rows = (j.asins || []);
  if(PPCA.q){
    rows = rows.filter(function(r){
      return (String(r.asin || "") + " " + String(r.title || ""))
        .toLowerCase().indexOf(PPCA.q) >= 0;
    });
  }
  rows = ppcSortRows(rows, PPCA.sort === "name" ? "asin" : PPCA.sort, PPCA.desc);

  let h = '<div class="ppc-panel" style="margin-bottom:0">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;'
    + 'margin-bottom:16px;flex-wrap:wrap;gap:10px">'
    + '<div class="ppc-panel-title" style="margin:0">ASIN Performance'
    +   '<span class="ppc-i" title="Every advertised product, with what the '
    +   'listing did beside what the advertising did.">ⓘ</span></div>'
    + '<input class="ppc-input" placeholder="Search by ASIN or title…" '
    +   'style="width:220px" oninput="ppcaFilter(this.value)">'
    + '</div>';

  if(!rows.length){
    return h + '<div style="color:var(--ppc-muted);padding:8px 0">'
      + 'No products match.</div></div>';
  }

  h += '<div style="overflow-x:auto"><table class="ppc-table" '
    + 'style="min-width:950px"><thead>'
    + '<tr class="grouphead"><th></th><th>PROFIT</th>'
    +   '<th colspan="4">TRAFFIC</th><th colspan="5">PAID</th></tr>'
    + '<tr>'
    + ppcTh("ASIN", "asin", PPCA, "ppcaSort", "left")
    + ppcTh("Profit", "profit", PPCA, "ppcaSort", "right",
            "Estimated from this account's measured fee and stock cost.")
    + ppcTh("Sessions", "sessions", PPCA, "ppcaSort", "right",
            "Visits to the listing, from the Business Report — all traffic, "
            + "not just advertising.")
    + ppcTh("Page Views", "page_views", PPCA, "ppcaSort", "right")
    + ppcTh("CVR", "cvr_pct", PPCA, "ppcaSort", "right",
            "The LISTING's conversion: units per session. Not the ad's orders "
            + "per click.")
    + ppcTh("Buy Box", "buy_box_pct", PPCA, "ppcaSort", "right")
    + ppcTh("Impr", "impressions", PPCA, "ppcaSort", "right")
    + ppcTh("Clicks", "clicks", PPCA, "ppcaSort", "right")
    + ppcTh("Spend", "spend", PPCA, "ppcaSort", "right")
    + ppcTh("Orders", "orders", PPCA, "ppcaSort", "right")
    + ppcTh("Sales", "sales", PPCA, "ppcaSort", "right")
    + '</tr></thead><tbody>';

  rows.forEach(function(r){
    h += '<tr>'
      + '<td style="min-width:230px"><div style="display:flex;gap:8px;'
      +   'align-items:center">'
      +   (r.img ? '<img src="' + _pEsc(r.img) + '" style="width:32px;height:32px;'
                   + 'object-fit:contain;border-radius:4px;border:1px solid '
                   + 'var(--ppc-border)" loading="lazy">'
               : '<span style="width:32px;height:32px;border-radius:4px;'
                 + 'border:1px solid var(--ppc-border);display:inline-block">'
                 + '</span>')
      +   '<div style="min-width:0">'
      +     '<div style="font-size:12px;font-weight:600;color:var(--ppc-cyan)">'
      +       _pEsc(r.asin) + '</div>'
      +     '<div style="font-size:11px;color:var(--ppc-muted);overflow:hidden;'
      +       'text-overflow:ellipsis;white-space:nowrap;max-width:230px">'
      +       _pEsc(r.title || "") + '</div></div></div></td>'
      + '<td>' + ppcProfit(r.profit, cur, "greenred") + '</td>'
      + '<td>' + ppcNum(r.sessions, "No Business Report data stored for this "
                        + "product in this window.") + '</td>'
      + '<td>' + ppcNum(r.page_views) + '</td>'
      + '<td>' + ppcPct(r.cvr_pct, "", 1) + '</td>'
      + '<td>' + ppcPct(r.buy_box_pct) + '</td>'
      + '<td>' + ppcNum(r.impressions) + '</td>'
      + '<td>' + ppcNum(r.clicks) + '</td>'
      + '<td>' + ppcMoney0(r.spend, cur) + '</td>'
      + '<td>' + ppcNum(r.orders) + '</td>'
      + '<td>' + ppcMoney0(r.sales, cur) + '</td>'
      + '</tr>';
  });
  return h + '</tbody></table></div></div>';
}
