/* static/js/ppclive.js -- the Live Tracker.
 *
 * Built to LIVE-TRACKER-BUILD-PROMPT.md, with its central premise corrected
 * against what Amazon will actually supply rather than drawn anyway.
 *
 * THE MOCKUP IS AN HOURLY PAGE. "Last 24 Hours" and "Last 7 Days" both plot one
 * point per hour. There is no hourly advertising data and there is no way to get
 * any: asked of Amazon directly, spCampaigns, spAdvertisedProduct and the
 * placement report all refuse timeUnit HOURLY with "configuration timeUnit is
 * not supported for this report type".
 *
 * Drawing twenty-four points across a day Amazon reported once would be a lie
 * told in pictures, and it is the exact thing this app has been asked more than
 * once not to do -- "i still see the organic vs ppc sales graph as a
 * placeholder". So the ranges are days, the limitation is stated at the top in
 * plain words, and the page delivers the part of the mockup that IS real.
 *
 * WHAT IS REAL, AND IS NEW HERE: the placement breakdown. Top of search, product
 * pages, the rest of Amazon. Two campaigns spending the same amount are not
 * making the same buy if one sits at the top of search and the other on a
 * competitor's product page, and until now nothing here could tell them apart.
 *
 * THE CHARTS ARE THE APP'S OWN. salesCombo carries the hover card, the
 * drag-to-zoom and the clickable key the Sales page has had all along, so these
 * behave identically and stay identical as that one changes (Rule 12). The
 * mockup's bespoke SVG would have been a picture.
 *
 * Colours live in static/css/ppc.css -- static/js may not name one.
 */

const PPCL = {data: null, loading: false, days: 7, cumulative: false,
              openAsin: null, asinData: {}, metric: "spend"};

async function ppclLoad(force){
  const host = document.getElementById("ppcl_body");
  if(!host || PPCL.loading) return;
  PPCL.loading = true;
  ppcBusy("ppcl_body", true);
  if(!PPCL.data){
    host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
      + 'color:var(--ppc-muted)"><span class="genspin"></span> '
      + 'Reading the advertising figures…</div></div>';
  }
  try{
    const j = await (await fetch("/ppc/live?" + ppcQS({
      days: PPCL.days, cumulative: PPCL.cumulative ? 1 : 0}))).json();
    PPCL.loading = false;
    if(!j || !j.ok){
      host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
        + 'color:var(--ppc-red)">'
        + _pEsc((j && j.error) || "Could not read the tracker.") + '</div></div>';
      ppcBusy("ppcl_body", false);
      return;
    }
    PPCL.data = j;
    ppclRender();
  }catch(e){
    PPCL.loading = false;
    ppcBusy("ppcl_body", false);
    if(!PPCL.data){
      host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
        + 'color:var(--ppc-red)">Could not read the tracker.</div></div>';
    }
  }
}

function ppclSetDays(d){ PPCL.days = d; PPCL.asinData = {}; ppclLoad(true); }
function ppclToggleCum(){ PPCL.cumulative = !PPCL.cumulative; ppclLoad(true); }

function ppclRender(){
  const j = PPCL.data;
  const host = document.getElementById("ppcl_body");
  if(!host || !j) return;
  const cur = (j.kpis && j.kpis.currency) || (typeof WS_MARKET !== "undefined"
    && WS_MARKET === "US" ? "USD" : "GBP");
  const k = j.kpis || {};

  let h = '<div class="ppc-page wide">'
    + '<h1>Live Tracker</h1>'
    + '<p class="ppc-sub">' + _pEsc(j.account_label || "")
    + ' · advertising as Amazon has reported it, to the latest complete day.</p>';

  // THE LIMITATION FIRST, not buried at the bottom. Somebody opening a page
  // called "Live Tracker" expecting hourly figures should learn in one sentence
  // why the buttons say days.
  h += '<div class="ppc-note warn"><b>This page is daily, not hourly.</b> '
    + _pEsc((j.hourly && j.hourly.why) || "") + '</div>';

  if(j.connection && j.connection.ok === false){
    h += ppcNoData({connection: j.connection},
                   "Nothing below can be drawn without it.");
    host.innerHTML = h + '</div>';
    ppcBusy("ppcl_body", false);
    return;
  }
  if(!k.has_data){
    h += ppcNoData({connection: j.connection, campaigns: {ok: false}},
                   "No advertising rows are stored for this window.");
    host.innerHTML = h + '</div>';
    ppcBusy("ppcl_body", false);
    return;
  }

  // ---- controls ----------------------------------------------------------
  h += '<div class="ppc-filters" style="align-items:flex-end">'
    + '<div><div class="ppc-flabel">Range</div><div class="ppc-seg">'
    + (j.ranges || []).map(function(r){
        return '<button class="' + (PPCL.days === r.days ? "on" : "") + '" '
          + 'onclick="ppclSetDays(' + r.days + ')">' + _pEsc(r.label)
          + '</button>'; }).join("")
    + '</div></div>'
    + '<div style="margin-left:auto;display:flex;align-items:center;gap:9px">'
    +   '<span style="font-size:13px;font-weight:600">Cumulative</span>'
    +   '<button class="ppcl-sw' + (PPCL.cumulative ? " on" : "") + '" '
    +   'onclick="ppclToggleCum()" title="Show the running total from the start '
    +   'of the range instead of each day on its own."></button>'
    + '</div></div>';

  // ---- the six cards ------------------------------------------------------
  const card = function(label, value, note){
    return '<div class="ppcl-kpi"><div class="k">' + _pEsc(label) + '</div>'
      + '<div class="v">' + value + '</div>'
      + (note ? '<div class="n">' + note + '</div>' : "") + '</div>';
  };
  h += '<div class="ppcl-kpis">'
    + card("Total ad spend", ppcMoney0(k.spend, cur))
    + card("Total sales", ppcMoney0(k.total_sales, cur))
    + card("TACOS", ppcPct(k.tacos_pct,
        "Needs total sales as well as ad spend; one of them is missing."))
    + card("ACOS", ppcPct(k.acos_pct,
        "No advertised sales in this window, so there is nothing to divide the "
        + "spend by. That is not an ACOS of nought."))
    + card("Ad orders", ppcNum(k.orders))
    + card("Units", ppcDash(k.units_why),
           '<span title="' + _pEsc(k.units_why || "") + '">not stored</span>')
    + '</div>';

  // ---- the main chart, through the app's own engine ------------------------
  h += ppclMainChart(j, cur);

  // ---- placements ---------------------------------------------------------
  h += ppclPlacements(j, cur);

  // ---- per product --------------------------------------------------------
  h += ppclProducts(j, cur);

  host.innerHTML = h + '</div>';
  PPCL.loading = false;
  ppcBusy("ppcl_body", false);
  ppcArm("ppcl_body");
}

/* The main chart. Spend, ad sales and total sales as lines; impressions is
 * deliberately NOT drawn on the same axes -- the mockup puts it on a second
 * y-axis as bars, and a bar scale of thousands beside a money scale of tens
 * makes both unreadable. It gets its own strip underneath instead. */
function ppclMainChart(j, cur){
  const pts = ((j.series || {}).points) || [];
  if(pts.length < 2){
    return ppcUnavailable("Not enough days to draw",
      "A line needs at least two days. This window has " + pts.length + ".");
  }
  const cols = pts.map(function(p){ return p.date; });
  const money = ppclChart({
    id: "ppcl_main", columns: cols, cur: cur,
    lines: [
      {key: "spend", values: pts.map(function(p){ return p.spend; })},
      {key: "ad_sales", values: pts.map(function(p){ return p.ad_sales; })},
      {key: "revenue", values: pts.map(function(p){ return p.total_sales; })},
    ]});
  const traffic = ppclChart({
    id: "ppcl_traffic", columns: cols, cur: cur,
    lines: [
      {key: "impressions", values: pts.map(function(p){ return p.impressions; })},
      {key: "clicks", values: pts.map(function(p){ return p.clicks; })},
    ]});

  return '<div class="ppc-panel ppc-mb16">'
    + '<div class="ppc-panel-title">Spend and sales'
    +   (PPCL.cumulative ? " — running total" : "") + '</div>'
    + '<div class="ppcl-chart">' + (money || "") + '</div>'
    + '</div>'
    + '<div class="ppc-panel ppc-mb16">'
    + '<div class="ppc-panel-title">Impressions and clicks'
    +   '<span class="ppc-i" title="On their own axes. Impressions run to '
    +   'thousands and spend to tens — drawn together, one of the two becomes a '
    +   'flat line along the bottom and neither can be read.">ⓘ</span></div>'
    + '<div class="ppcl-chart">' + (traffic || "") + '</div>'
    + '</div>';
}

/* salesCombo, called the SAME WAY PPC Analytics calls it -- columns and lines,
 * not labels and series. Written the other way first, which would have returned
 * an empty chart in silence: salesCombo reads o.columns, finds nothing, and
 * returns "" without complaining. Exactly the failure that once made this whole
 * set of screens look like flat pictures.
 *
 * Returns "" if the engine is absent rather than throwing -- a missing chart
 * must not take the page down with it. */
function ppclChart(o){
  if(typeof salesCombo !== "function") return "";
  const cols = o.columns || [];
  if(cols.length < 2) return "";
  try{
    return salesCombo({
      id: o.id, columns: cols, unit: "day", lines: o.lines || [],
      currency: o.cur, width: scChartWidth("ppcl_body", 1120),
      height: o.height || 280});
  }catch(e){ return ""; }
}

function ppclPlacements(j, cur){
  const p = j.placements || {};
  if(!p.has_data){
    return '<div class="ppc-panel ppc-mb16">'
      + '<div class="ppc-panel-title">Where the ads appeared</div>'
      + '<div class="ppc-note">' + _pEsc(p.why || "") + '</div></div>';
  }
  let h = '<div class="ppc-panel ppc-mb16">'
    + '<div class="ppc-panel-title">Where the ads appeared'
    + '<span class="ppc-i" title="' + _pEsc(p.why || "") + '">ⓘ</span></div>'
    + '<table class="ppc-table"><thead><tr>'
    + '<th>Placement</th><th>Spend</th><th>Share</th><th>Impressions</th>'
    + '<th>Clicks</th><th>CPC</th><th>Ad sales</th><th>ACOS</th><th>Orders</th>'
    + '</tr></thead><tbody>';
  (p.rows || []).forEach(function(r){
    h += '<tr><td title="Amazon calls this ' + _pEsc(r.placement) + '">'
      + _pEsc(r.label) + '</td>'
      + '<td>' + ppcMoney(r.spend, cur) + '</td>'
      + '<td>' + ppcPct(r.share_pct) + '</td>'
      + '<td>' + ppcNum(r.impressions) + '</td>'
      + '<td>' + ppcNum(r.clicks) + '</td>'
      + '<td>' + ppcMoney(r.cpc, cur) + '</td>'
      + '<td>' + ppcMoney(r.sales, cur) + '</td>'
      + '<td>' + ppcPct(r.acos_pct, "No sales attributed to this placement, so "
                                    + "it has no ACOS — not an ACOS of nought.")
      + '</td>'
      + '<td>' + ppcNum(r.orders) + '</td></tr>';
  });
  h += '</tbody></table>'
    + '<div class="ppc-note">' + _pEsc(p.asin_why || "") + '</div></div>';
  return h;
}

function ppclProducts(j, cur){
  const pr = j.products || {};
  const rows = pr.rows || [];
  if(!rows.length){
    return ppcUnavailable("No advertised products in this window",
      "Nothing was advertised, or the per-product rows have not been synced.");
  }
  let h = '<div class="ppc-panel">'
    + '<div class="ppc-panel-title">By product'
    + '<span class="ppc-i" title="' + _pEsc(pr.why || "") + '">ⓘ</span></div>'
    + '<table class="ppc-table"><thead><tr>'
    + '<th>Product</th><th>Spend</th><th>Share</th><th>Impressions</th>'
    + '<th>Clicks</th><th>Orders</th><th>Ad sales</th><th>ACOS</th><th>CVR</th>'
    + '</tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr class="ppcl-prow" onclick="ppclOpenAsin(' + jsArg(r.asin) + ')">'
      + '<td><div class="ppcl-prod">'
      +   (r.img ? '<img src="' + _pEsc(r.img) + '" alt="" loading="lazy">'
                 : '<span class="ppcl-noimg" title="No catalogue picture stored '
                   + 'for this ASIN."></span>')
      +   '<div><div class="t">' + _pEsc((r.title || "").slice(0, 64))
      +   '</div><div class="a">' + _pEsc(r.asin) + '</div></div></div></td>'
      + '<td>' + ppcMoney(r.spend, cur) + '</td>'
      + '<td>' + ppcPct(r.share_pct) + '</td>'
      + '<td>' + ppcNum(r.impressions) + '</td>'
      + '<td>' + ppcNum(r.clicks) + '</td>'
      + '<td>' + ppcNum(r.orders) + '</td>'
      + '<td>' + ppcMoney(r.sales, cur) + '</td>'
      + '<td>' + ppcPct(r.acos_pct, "This product's ads made no attributed "
                                    + "sales in the window.") + '</td>'
      + '<td>' + ppcPct(r.cvr_pct, "No clicks, so no conversion rate.")
      + '</td></tr>';
    if(PPCL.openAsin === r.asin){
      h += '<tr><td colspan="9" style="padding:0"><div id="ppcl_asin">'
        + ppclAsinPanel(r.asin, cur) + '</div></td></tr>';
    }
  });
  return h + '</tbody></table></div>';
}

function ppclAsinPanel(asin, cur){
  const d = PPCL.asinData[asin];
  if(!d){
    return '<div class="ppcl-detail"><span class="genspin"></span> '
      + 'Reading this product…</div>';
  }
  const pts = d.points || [];
  const chart = ppclChart({
    id: "ppcl_a_" + asin, cur: cur, height: 220,
    columns: pts.map(function(p){ return p.date; }),
    lines: [
      {key: "spend", values: pts.map(function(p){ return p.spend; })},
      {key: "ad_sales", values: pts.map(function(p){ return p.sales; })},
      {key: "clicks", values: pts.map(function(p){ return p.clicks; })},
    ]});
  return '<div class="ppcl-detail">'
    + (chart || '<div style="color:var(--ppc-muted);font-size:12px">'
                + 'Not enough days to draw a line.</div>')
    + '</div>';
}

async function ppclOpenAsin(asin){
  PPCL.openAsin = (PPCL.openAsin === asin) ? null : asin;
  ppclRender();
  if(!PPCL.openAsin || PPCL.asinData[asin]) return;
  try{
    const j = await (await fetch("/ppc/live/asin?"
      + ppcQS({asin: asin, days: PPCL.days}))).json();
    if(j && j.ok){
      PPCL.asinData[asin] = j;
      if(PPCL.openAsin === asin) ppclRender();
    }
  }catch(e){ /* the row stays open with its notice */ }
}
