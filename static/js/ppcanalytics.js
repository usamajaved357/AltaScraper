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
 * Marketing Stream, a separate push integration this app does not have.
 *
 * So the trail keeps its seven cards and its curve, drawn at the finest grain
 * that exists, and its caption says which. The heatmap keeps its panel and its
 * legend and says what it needs. Neither is filled with invented hours -- that
 * is the one thing these screens have been told off for twice.
 *
 * NOTHING HERE WRITES. No bid, no budget, no campaign state (Rule 8).
 */

const PPCA = {data: null, loading: false, sort: "spend", desc: true,
              tab: "campaigns", q: ""};

async function ppcaLoad(){
  const host = document.getElementById("ppca_body");
  if(!host || PPCA.loading) return;
  PPCA.loading = true;
  host.innerHTML = '<div class="ppc-page"><div style="padding:18px;'
    + 'color:var(--ppc-muted)"><span class="genspin"></span> '
    + 'Reading the advertising figures…</div></div>';
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
    host.innerHTML = '<div class="ppc-page"><div style="padding:18px;'
      + 'color:var(--ppc-red)">Could not read the advertising figures.</div></div>';
  }
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
    h += ppcUnavailable("No advertising figures for this window",
      (av.campaigns && av.campaigns.why)
        || "Nothing is stored for this account and marketplace in this window.");
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
}

function _ppcaRound1(v){ return Math.round(Number(v) * 10) / 10; }

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
  return '<div class="ppc-today">'
    + '<div class="ppc-today-label"><b>TODAY</b><span>'
    + _pEsc(d.date || "") + '</span></div>'
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
  const cum = rows.map(function(r){ return r.cumulative; });
  const MON = ["JAN","FEB","MAR","APR","MAY","JUN",
               "JUL","AUG","SEP","OCT","NOV","DEC"];
  const DOW = ["SUN","MON","TUE","WED","THU","FRI","SAT"];

  let h = '<div style="display:flex;align-items:center;justify-content:'
    + 'space-between;margin-bottom:4px;flex-wrap:wrap;gap:8px">'
    + '<div><div style="font-size:18px;font-weight:700">Day trail</div>'
    + '<div style="font-size:12px;color:var(--ppc-muted)">Cumulative ad spend '
    + 'by day · Amazon publishes no hourly figures for this report, so each '
    + 'curve is days rather than hours</div></div>'
    + ppcSeg(30, "ppcaLoad") + '</div>'
    + '<div class="ppc-trail">';

  rows.forEach(function(r, i){
    const day = new Date(r.date + "T00:00:00");
    const lbl = isNaN(day.getTime()) ? r.date
      : (DOW[day.getDay()] + " " + MON[day.getMonth()] + " " + day.getDate());
    h += '<div class="ppc-trail-card">'
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

  return '<div class="ppc-kpis">'
    + ppcKpi({label: "SPEND", value: ppcMoney0(t.spend, cur),
              change: ppcChangeBare(ch.spend, "down"),
              spark: ppcSparkline(col("spend"), "var(--ppc-red)"),
              help: "What Amazon charged for the ads in this window."})
    + ppcKpi({label: "SALES", value: ppcMoney0(t.sales, cur),
              change: ppcChangeBare(ch.sales, "up"),
              spark: ppcSparkline(col("ad_sales"), "var(--ppc-green)"),
              help: "Sales Amazon attributes to those ads. An organic sale is "
                  + "not in here."})
    + ppcKpi({label: "ACOS", value: ppcPct(t.acos_pct),
              change: ppcChangeBare(ch.acos_pct, "down"),
              spark: ppcSparkline(col("acos_pct"), "var(--ppc-orange)"),
              help: "Spend divided by AD sales. How much of the advertised "
                  + "revenue the advertising ate. Lower is better."})
    + ppcKpi({label: "ROAS", value: ppcX(t.roas),
              change: ppcChangeBare(ch.roas, "up"),
              spark: ppcSparkline(col("roas"), "var(--ppc-blue)"),
              help: "Ad sales for every pound of spend."})
    + '</div>'
    + '<div class="ppc-kpis last">'
    + ppcKpi({label: "IMPRESSIONS", value: ppcNum(t.impressions),
              change: ppcChangeBare(ch.impressions, "up"),
              spark: ppcSparkline(col("impressions"), "var(--ppc-blue)"),
              help: "How many times the ads were shown."})
    + ppcKpi({label: "CLICKS", value: ppcNum(t.clicks),
              change: ppcChangeBare(ch.clicks, "up"),
              spark: ppcSparkline(col("clicks"), "var(--ppc-green)"),
              help: "How many times somebody clicked one."})
    + ppcKpi({label: "CTR", value: ppcPct(t.ctr_pct, "", 2),
              change: ppcChangeBare(ch.ctr_pct, "up"),
              spark: ppcSparkline(col("ctr_pct"), "var(--ppc-magenta)"),
              help: "Clicks per impression."})
    + ppcKpi({label: "PURCHASES", value: ppcNum(t.orders),
              change: ppcChangeBare(ch.orders, "up"),
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

  return head
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

  // Wasted spend, and whether it moved. FALLING IS GOOD -- the mockup is
  // explicit, and it is the opposite of the default reading of a red arrow.
  let wchange = null;
  if(w.spend !== null && w.spend !== undefined
     && wp.spend !== null && wp.spend !== undefined && wp.spend){
    wchange = _ppcaRound1(100 * (w.spend - wp.spend) / Math.abs(wp.spend));
  }
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
                    change: ppcChangeText((j.change || {}).tacos_pct, "down"),
                    note: period,
                    help: "Spend divided by ALL sales, advertised and organic "
                        + "together. Rising is bad — advertising is taking a "
                        + "larger share of the whole business."})
    +   ppcSubCard({label: "WASTED SPEND",
                    value: ppcMoney0(w.spend, cur, w.why), why: w.why,
                    change: (wchange === null ? "" :
                             ppcChangeText(wchange, "down")),
                    note: (wpct === null ? period
                           : (wpct.toFixed(1) + "% of total spend")),
                    note2: (w.terms ? (w.terms + " terms clicked, none ordered")
                                    : ""),
                    help: "Spend on search terms that took at least one click "
                        + "and produced no order. Not 'ACOS above target' — "
                        + "that is a judgement about price. This is money that "
                        + "bought traffic which bought nothing."})
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
    +   ppcSubCard({label: "EFFICIENCY SCORE",
                    value: (eff === null ? null : eff.toFixed(2)),
                    why: "Needs a measured break-even ACOS and attributed sales.",
                    badge: effBadge,
                    note: "100 is break-even. Higher is better.",
                    help: "Our own measure, defined here rather than borrowed: "
                        + "100 × break-even ACOS ÷ actual ACOS. At 100 the "
                        + "advertising exactly breaks even; above it, it makes "
                        + "money."})
    +   ppcSubCard({label: "NET PROFIT",
                    value: (net === null ? null : ppcMoney0(net, cur)),
                    colour: (net === null ? "" : (net >= 0 ? "var(--ppc-green)"
                                                           : "var(--ppc-red)")),
                    why: "Needs both measured rates.",
                    note: period,
                    help: "Attributed sales, less the spend, less this "
                        + "account's measured Amazon fee and stock cost."})
    + '</div></div>';
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
  const lines = [{values: d.map(function(x){ return x.spend; }),
                  colour: "var(--ppc-red)"}];
  if(canProfit) lines.push({values: profit, colour: "var(--ppc-cyan)"});

  return '<div class="ppc-panel">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
    +   '<span class="ppc-panel-title" style="margin:0">Revenue, Ad Spend '
    +   '&amp; Profitability</span>'
    +   '<span class="ppc-i" title="Total sales as bars, with what the '
    +   'advertising cost and returned over them. A gap is a day with nothing '
    +   'stored, not a day of no spend.">ⓘ</span></div>'
    + ppcLegend([["Ad Spend", "var(--ppc-red)"]]
        .concat(canProfit ? [["Profit", "var(--ppc-cyan)"]] : [])
        .concat([["Total Revenue", "var(--ppc-gold)"]]))
    + ppcComposed({
        columns: d.map(function(x){ return x.date; }),
        bars: {values: d.map(function(x){ return x.total_sales; }),
               colour: "var(--ppc-gold)"},
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
    ? ppcArea({columns: cols, values: pc, colour: "var(--ppc-green)",
               height: 200, refLineY: 0,
               yFormat: function(v){ return sym + v.toFixed(2); }})
    : missing((j.rates || {}).why || "Profit per click needs a measured fee "
        + "rate and a measured stock cost. Without both there is no honest way "
        + "to say what a click earned.");

  const right = (eff && eff.some(function(v){ return v !== null; }))
    ? ppcArea({columns: cols, values: eff, colour: "var(--ppc-cyan)",
               height: 200, refLineY: 100,
               yFormat: function(v){ return String(Math.round(v)); }})
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
function ppcaHeatAndTacos(j, cur){
  const d = j.daily || [];
  const av = j.availability || {};
  const hourWhy = (av.hourly && av.hourly.why) || "";

  // The heatmap needs day x hour and there are no hours. The panel, its legend
  // and the reason stay; the grid is not invented.
  const heat = '<div class="ppc-panel ppc-panel-sm" style="margin-bottom:0">'
    + '<div class="ppc-panel-title-sm">ACoS Heatmap — Day × Hour'
    + '<span class="ppc-i" title="Which hours of which days the advertising '
    + 'converts.">ⓘ</span></div>'
    + '<div style="font-size:12px;color:var(--ppc-muted);line-height:1.6;'
    + 'margin-bottom:12px">' + _pEsc(hourWhy) + '</div>'
    + ppcHeatmap(null) + '</div>';

  const tacos = d.map(function(x){ return x.tacos_pct; });
  const hasT = tacos.some(function(v){ return v !== null; });
  const tp = '<div class="ppc-panel ppc-panel-sm" style="margin-bottom:0">'
    + '<div class="ppc-panel-title-sm">TACoS Over Time</div>'
    + (hasT
        ? ppcArea({columns: d.map(function(x){ return x.date; }),
                   values: tacos, colour: "var(--ppc-orange)", height: 220,
                   yFormat: function(v){ return v.toFixed(0) + "%"; }})
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
    + ppcLegend([["Ad Spend", "var(--ppc-red)"], ["Sales", "var(--ppc-gold)"]])
    + ppcComposed({
        columns: d.map(function(x){ return x.date; }),
        bars: {values: d.map(function(x){ return x.total_sales; }),
               colour: "var(--ppc-gold)"},
        lines: [{values: d.map(function(x){ return x.spend; }),
                 colour: "var(--ppc-red)"}],
        refLines: refs, currency: cur, height: 260})
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
