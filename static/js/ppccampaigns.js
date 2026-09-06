/* static/js/ppccampaigns.js -- Campaign Analytics, to
 * orbit-campaign-analytics-v2.jsx.
 *
 * The mockup's order and its measurements:
 *
 *     header                 title + subtitle left, filters right
 *     Campaign & Match Type  donut 220 left in a 260px column, stacked area
 *       Breakdown            right, then one table with a tint per column and
 *                            two labelled sections
 *     Campaign Profitability one dot per campaign on the page's own ground,
 *       Map                  seven ACOS bands, a dashed BREAKEVEN rule
 *     Performance Cohorts    a 22px stacked bar, then five cards, ALL ringed
 *                            in orange
 *     Top Campaigns          orange pills, a blue ACOS slider, a pill search
 *                            box, and rows that open onto their own search
 *                            terms behind a blue rule
 *
 * NOTHING HERE WRITES. No bid, no budget, no campaign state (Rule 8).
 */

const PPCC = {data: null, loading: false, sort: "spend", desc: true, q: "",
              type: "All", status: "All", open: null, minSpend: "",
              maxAcos: 200, highlight: null};

async function ppccLoad(){
  const host = document.getElementById("ppcc_body");
  if(!host || PPCC.loading) return;
  PPCC.loading = true;
  // The screen stays on and dims rather than going blank -- see ppcBusy.
  ppcBusy("ppcc_body", true);
  if(!PPCC.data){
    host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
      + 'color:var(--ppc-muted)"><span class="genspin"></span> '
      + 'Reading the campaigns…</div></div>';
  }
  try{
    const qs = ppcQS(PPCWIN.start
      ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
    const j = await (await fetch("/ppc/analytics/campaigns?" + qs)).json();
    PPCC.loading = false;
    if(!j || !j.ok){
      host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
        + 'color:var(--ppc-red)">'
        + _pEsc((j && j.error) || "Could not read the campaigns.")
        + '</div></div>';
      return;
    }
    PPCC.data = j;
    ppccRender();
  }catch(e){
    PPCC.loading = false;
    ppcBusy("ppcc_body", false);
    if(!PPCC.data){
      host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
        + 'color:var(--ppc-red)">Could not read the campaigns.</div></div>';
    }else if(typeof toast === "function"){
      toast("Could not refresh the campaigns — showing the last ones.");
    }
  }
}

/* Dragging across the spend chart narrows the window to those days, exactly as
 * it does on PPC Analytics and on the Sales page. */
function ppccZoomTo(from, to){
  if(!from || !to) return;
  PPCWIN.start = String(from).slice(0, 10);
  PPCWIN.end = String(to).slice(0, 10);
  ppccLoad();
}

function ppccSort(k){
  if(PPCC.sort === k) PPCC.desc = !PPCC.desc;
  else { PPCC.sort = k; PPCC.desc = true; }
  ppccRender();
}
function ppccSet(f, v){ PPCC[f] = v; ppccRender(); }
function ppccFilter(v){ PPCC.q = (v || "").toLowerCase(); ppccRender(); }
function ppccToggle(id){
  PPCC.open = (PPCC.open === id) ? null : id;
  ppccRender();
}
/* Clicking a bubble highlights its row, which is what the mockup's caption
 * promises: "Click to highlight in table below." */
function ppccHighlight(id){
  PPCC.highlight = (PPCC.highlight === id) ? null : id;
  PPCC.open = id;
  ppccRender();
  const el = document.getElementById("ppcc_row_" + id);
  if(el && el.scrollIntoView) el.scrollIntoView({block: "center"});
}

function ppccRows(){
  const j = PPCC.data;
  let rows = (j && j.campaigns) || [];
  if(PPCC.q){
    rows = rows.filter(function(r){
      return String(r.name || "").toLowerCase().indexOf(PPCC.q) >= 0;
    });
  }
  if(PPCC.type !== "All"){
    const want = {SP: "SPONSORED_PRODUCTS", SB: "SPONSORED_BRANDS",
                  SD: "SPONSORED_DISPLAY"}[PPCC.type];
    rows = rows.filter(function(r){
      return String(r.ad_product || "").toUpperCase() === want;
    });
  }
  if(PPCC.status !== "All"){
    rows = rows.filter(function(r){
      return String(r.status || "").toUpperCase() === PPCC.status.toUpperCase();
    });
  }
  const min = parseFloat(PPCC.minSpend);
  if(!isNaN(min)) rows = rows.filter(function(r){ return (r.spend || 0) >= min; });
  const ma = Number(PPCC.maxAcos);
  if(ma < 200){
    rows = rows.filter(function(r){
      return r.acos_pct === null || r.acos_pct === undefined || r.acos_pct <= ma;
    });
  }
  return ppcSortRows(rows, PPCC.sort, PPCC.desc);
}

function ppccRender(){
  const host = document.getElementById("ppcc_body");
  const j = PPCC.data;
  if(!host || !j) return;
  const cur = j.currency || "GBP";
  const av = j.availability || {}, w = j.window || {};

  let h = '<div class="ppc-page wide">'
    + '<div style="display:flex;justify-content:space-between;'
    + 'align-items:flex-start;margin-bottom:20px;flex-wrap:wrap;gap:14px">'
    + '<div><h1>Campaign Analytics</h1>'
    +   '<p class="ppc-sub" style="margin:4px 0 0">Campaign type breakdown, '
    +   'match type performance, and top campaigns</p></div>'
    + '<div style="display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap">'
    +   '<div><div class="ppc-flabel">Range</div>'
    +     ppcSeg(30, "ppccLoad") + '</div>'
    +   '<div class="ppc-fctl" style="border-radius:8px">'
    +     _pEsc((w.start || "") + " to " + (w.end || "")) + '</div>'
    + '</div></div>';

  if(!(j.campaigns || []).length){
    h += ppcUnavailable("No campaigns stored for this window",
      (av.campaigns && av.campaigns.why) || "Nothing is stored for this window.");
    host.innerHTML = h + '</div>';
    return;
  }

  h += ppcProductNote(av);
  h += ppcRatesNote(j.rates);
  h += ppccBreakdown(j, cur);
  h += ppccMap(j, cur);
  h += ppccCohorts(j, cur);
  h += ppccTable(j, cur);

  host.innerHTML = h + '</div>';
  PPCC.loading = false;
  ppcBusy("ppcc_body", false);
  ppcArm("ppcc_body");
}

/* ---- 1. the breakdown panel --------------------------------------------- */
function ppccBreakdown(j, cur){
  const prods = j.by_ad_product || [], matches = j.by_match_type || [];
  const dbp = j.daily_by_product || {};
  const NICE = {SPONSORED_PRODUCTS: "Sponsored Products (SP)",
                SPONSORED_BRANDS: "Sponsored Brands (SB)",
                SPONSORED_DISPLAY: "Sponsored Display (SD)"};
  const PCOL = {SPONSORED_PRODUCTS: "#f0c000", SPONSORED_BRANDS: "var(--ppc-blue)",
                SPONSORED_DISPLAY: "var(--ppc-purple)"};
  const MCOL = {BROAD: "var(--ppc-orange)", PHRASE: "var(--ppc-blue)",
                EXACT: "var(--ppc-green)",
                TARGETING_EXPRESSION: "var(--ppc-red)",
                TARGETING_EXPRESSION_PREDEFINED: "var(--ppc-muted)"};

  const totalSpend = prods.reduce(function(a, p){ return a + (p.spend || 0); }, 0);

  // The eleven columns and their tints, in the mockup's order.
  const TINTS = ["", "ppc-tint-blue", "ppc-tint-blue", "ppc-tint-blue",
                 "ppc-tint-blue", "ppc-tint-purple", "ppc-tint-purple",
                 "ppc-tint-blue", "ppc-tint-blue", "ppc-tint-green",
                 "ppc-tint-teal"];
  const HEADS = ["TYPE", "CLICKS", "CTR", "CPC", "CPA", "SPEND", "% SPEND",
                 "SALES", "ACOS", "PROFIT", "% PROFIT"];

  const row = function(r, colour, label){
    const cells = [
      ppcNum(r.clicks), ppcPct(r.ctr_pct, "", 1), ppcMoney(r.cpc, cur),
      ppcMoney(r.cpa, cur, "No orders, so there is no cost per order."),
      ppcMoney0(r.spend, cur), ppcPct(r.spend_share_pct),
      ppcMoney0(r.sales, cur), ppcPct(r.acos_pct,
        "No attributed sales, so ACOS is undefined — not 0%."),
      ppcProfit(r.profit, cur, "greenred"), ppcPct(r.profit_share_pct),
    ];
    return '<tr><td style="border-left:3px solid ' + colour + '">'
      + '<span class="ppc-dot" style="background:' + colour + '"></span>'
      + _pEsc(label) + '</td>'
      + cells.map(function(v, i){
          return '<td class="' + TINTS[i + 1] + '">' + v + '</td>';
        }).join("")
      + '</tr>';
  };

  let table = '<div style="overflow-x:auto"><table>'
    + '<thead><tr>'
    + HEADS.map(function(x, i){
        return '<th class="' + TINTS[i] + '">' + x + '</th>';
      }).join("")
    + '</tr></thead><tbody>';

  if(matches.length){
    table += '<tr class="sect"><td colspan="11">Match types</td></tr>';
    matches.forEach(function(m){
      table += row(m, MCOL[String(m.key).toUpperCase()] || "var(--ppc-muted)",
                   m.key);
    });
  }
  if(prods.length){
    table += '<tr class="sect"><td colspan="11">Campaign types</td></tr>';
    prods.forEach(function(p){
      const k = String(p.key).toUpperCase();
      table += row(p, PCOL[k] || "var(--ppc-muted)", NICE[k] || p.key);
    });
  }
  table += '</tbody></table></div>';

  // SPEND PER DAY, THROUGH THE APP'S OWN CHART so it hovers, zooms and lets
  // the key be clicked like every other chart in the app. Only products that
  // actually have rows become lines -- an empty "Sponsored Brands" band would
  // claim Brands ran and returned nothing, which is not the same as never
  // having been pulled.
  //
  // A LINE PER PRODUCT, NOT A STACK. The mockup stacks them, which reads well
  // with two comparable products; with one it is a filled blob, and salesCombo
  // draws lines. The colours and the legend are the mockup's either way, and a
  // line is the shape you can hover a single day on.
  const KEYMAP = {SPONSORED_PRODUCTS: "ad_spend", SPONSORED_BRANDS: "ad_sales",
                  SPONSORED_DISPLAY: "roas"};
  const lines = (dbp.series || [])
    .filter(function(s){
      return (s.values || []).some(function(v){
        return v !== null && v !== undefined; });
    })
    .map(function(s){
      const k = String(s.key).toUpperCase();
      return {key: KEYMAP[k] || "ad_spend", label: NICE[k] || s.key,
              values: s.values};
    });
  const chart = (lines.length && typeof salesCombo === "function")
    ? salesCombo({id: "ppcc_spend", onZoom: "ppccZoomTo",
                  columns: dbp.dates || [], bars: null, lines: lines,
                  currency: cur, unit: "day",
                  width: scChartWidth("ppcc_body", 820), height: 280})
    : "";

  return '<div class="ppc-panel ppc-break">'
    + '<div style="font-size:15px;font-weight:700;margin-bottom:2px">'
    +   'Campaign &amp; Match Type Breakdown'
    +   '<span style="font-weight:400;font-size:12px;color:var(--ppc-muted);'
    +   'margin-left:6px">spend by ad product, and how each match type '
    +   'performed</span></div>'
    + '<div style="display:grid;grid-template-columns:260px 1fr;gap:24px;'
    +   'margin-top:16px;align-items:center">'
    + '<div style="text-align:center">'
    +   ppcDonut(prods.map(function(p){
          const k = String(p.key).toUpperCase();
          return {label: NICE[k] || p.key, value: p.spend || 0,
                  colour: PCOL[k] || "var(--ppc-muted)"};
        }), 220)
    +   '<div style="font-size:12px;color:var(--ppc-muted)">Total Spend</div>'
    +   '<div style="font-size:26px;font-weight:700">'
    +   ppcMoney0(totalSpend, cur) + '</div>'
    + '</div>'
    + '<div>'
    +   (chart
          ? ('<div class="ppc-charthint">Spend per day by ad product · hover '
             + 'for the day · drag across to zoom · click a name to hide it'
             + '</div>' + chart)
          : '<div style="font-size:12px;color:var(--ppc-muted)">No daily '
            + 'campaign rows in this window.</div>')
    + '</div>'
    + '</div>'
    + table
    + ppcLegend(prods.map(function(p){
        const k = String(p.key).toUpperCase();
        return [(NICE[k] || p.key) + " (" + ppcMoney0(p.spend, cur) + ")",
                PCOL[k] || "var(--ppc-muted)"];
      }))
    + '</div>';
}

/* ---- 2. the profitability map -------------------------------------------
 *
 * One dot per campaign: spend across, estimated profit up, a dashed rule at
 * zero. Everything under it is losing money and the further right it sits the
 * more of it there is -- one glance instead of sorting a 254-row table twice.
 *
 * The mockup hides outliers rather than letting one campaign flatten the rest,
 * and says how many. So does this.
 */
function ppccMap(j, cur){
  const all = (j.campaigns || []).filter(function(r){
    return r.spend !== null && r.spend !== undefined
        && r.profit !== null && r.profit !== undefined;
  });
  if(!all.length){
    return ppcUnavailable("Campaign Profitability Map",
      "Profit cannot be worked out for this window, so there is nothing to plot "
      + "against it. " + ((j.rates || {}).why || "This account has no measured "
      + "fee rate or no costed orders."));
  }

  // OUTLIERS ARE HIDDEN AND COUNTED, never dropped silently. One campaign at
  // ten times everything else pushes the other 250 into a single row of pixels.
  const sorted = all.slice().sort(function(a, b){ return a.spend - b.spend; });
  const cap = sorted[Math.floor(sorted.length * 0.98)];
  const capSpend = (cap ? cap.spend : 0) * 1.15;
  const rows = all.filter(function(r){ return r.spend <= capSpend; });
  const hidden = all.length - rows.length;

  const W = 1220, H = 360;
  const X0 = 60, X1 = 1180, Y0 = 20, Y1 = 300;
  const sMax = Math.max.apply(null, rows.map(function(r){ return r.spend; })) || 1;
  let pMin = Math.min.apply(null, rows.map(function(r){ return r.profit; }));
  let pMax = Math.max.apply(null, rows.map(function(r){ return r.profit; }));
  if(pMin > 0) pMin = 0;
  if(pMax < 0) pMax = 0;
  const pSpan = (pMax - pMin) || 1;
  const mapX = function(v){ return X0 + (v / sMax) * (X1 - X0); };
  const mapY = function(v){ return Y1 - ((v - pMin) / pSpan) * (Y1 - Y0); };

  const band = function(a){
    if(a === null || a === undefined) return "var(--ppc-dim)";
    if(a < 15) return "var(--ppc-green)";
    if(a < 25) return "var(--ppc-heat2)";
    if(a < 40) return "var(--ppc-orange)";
    if(a < 60) return "var(--ppc-acos6)";
    if(a < 100) return "var(--ppc-red)";
    return "var(--ppc-acos7)";
  };

  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" '
    + 'style="width:100%;height:auto;display:block">';
  for(let i = 0; i <= 4; i++){
    const v = pMin + pSpan * i / 4, yy = mapY(v);
    svg += '<line x1="' + X0 + '" y1="' + yy.toFixed(1) + '" x2="' + X1
      + '" y2="' + yy.toFixed(1) + '" stroke="var(--ppc-border)" '
      + 'stroke-width="1" stroke-dasharray="4 4"/>'
      + '<text x="' + (X0 - 8) + '" y="' + (yy + 4).toFixed(1) + '" '
      + 'fill="var(--ppc-dim)" font-size="11" text-anchor="end">'
      + _pEsc(ppcMoney0(v, cur).replace(/<[^>]+>/g, "")) + '</text>';
    const xv = sMax * i / 4, xx = mapX(xv);
    svg += '<line x1="' + xx.toFixed(1) + '" y1="' + Y0 + '" x2="' + xx.toFixed(1)
      + '" y2="' + Y1 + '" stroke="var(--ppc-border)" stroke-width="1" '
      + 'stroke-dasharray="4 4"/>'
      + '<text x="' + xx.toFixed(1) + '" y="' + (Y1 + 18) + '" '
      + 'fill="var(--ppc-dim)" font-size="11" text-anchor="middle">'
      + _pEsc(ppcMoney0(xv, cur).replace(/<[^>]+>/g, "")) + '</text>';
  }
  const zero = mapY(0);
  svg += '<line x1="' + X0 + '" y1="' + zero.toFixed(1) + '" x2="' + X1
    + '" y2="' + zero.toFixed(1) + '" stroke="var(--ppc-muted)" '
    + 'stroke-width="1.5" stroke-dasharray="8 5"/>'
    + '<text x="' + (X1 + 6) + '" y="' + (zero + 4).toFixed(1) + '" '
    + 'fill="var(--ppc-muted)" font-size="10" font-weight="600" '
    + 'text-anchor="end">BREAKEVEN</text>'
    + '<text x="' + ((X0 + X1) / 2) + '" y="' + (Y1 + 42) + '" '
    + 'fill="var(--ppc-muted)" font-size="12" text-anchor="middle">'
    + 'Ad Spend</text>'
    + '<text x="14" y="' + ((Y0 + Y1) / 2) + '" fill="var(--ppc-muted)" '
    + 'font-size="12" text-anchor="middle" transform="rotate(-90 14 '
    + ((Y0 + Y1) / 2) + ')">Estimated Profit</text>';

  const salesMax = Math.max.apply(null,
    rows.map(function(r){ return r.sales || 0; })) || 1;
  rows.forEach(function(r){
    const rad = Math.max(4, Math.sqrt((r.sales || 0) / salesMax * 100) * 0.9);
    svg += '<circle cx="' + mapX(r.spend).toFixed(1) + '" cy="'
      + mapY(r.profit).toFixed(1) + '" r="' + rad.toFixed(1) + '" fill="'
      + band(r.acos_pct) + '" opacity="0.85" style="cursor:pointer" '
      + 'onclick="ppccHighlight(' + jsArg(String(r.campaign_id)) + ')">'
      + '<title>' + _pEsc(String(r.name || r.campaign_id))
      + "\nSpend: " + _pEsc(ppcMoney(r.spend, cur).replace(/<[^>]+>/g, ""))
      + "\nSales: " + _pEsc(ppcMoney(r.sales, cur).replace(/<[^>]+>/g, ""))
      + "\nProfit: " + _pEsc(ppcMoney(r.profit, cur).replace(/<[^>]+>/g, ""))
      + "\nACOS: " + (r.acos_pct === null || r.acos_pct === undefined
                      ? "no sales" : (r.acos_pct + "%"))
      + '</title></circle>';
  });
  svg += '</svg>';

  const legend = [["var(--ppc-green)", "< 15%"], ["var(--ppc-heat2)", "15–25%"],
                  ["var(--ppc-orange)", "25–40%"], ["var(--ppc-acos6)", "40–60%"],
                  ["var(--ppc-red)", "60–100%"], ["var(--ppc-acos7)", "> 100%"],
                  ["var(--ppc-dim)", "no sales"]].map(function(l){
    return '<span style="display:flex;align-items:center;gap:4px">'
      + '<span style="width:9px;height:9px;border-radius:50%;background:'
      + l[0] + '"></span>' + l[1] + '</span>';
  }).join("");

  return '<div class="ppc-panel">'
    + '<div style="display:flex;justify-content:space-between;'
    +   'align-items:flex-start;flex-wrap:wrap;gap:8px">'
    + '<div><div style="font-size:15px;font-weight:700">Campaign Profitability '
    +   'Map</div>'
    +   '<div style="font-size:12px;color:var(--ppc-muted);margin-top:2px">'
    +   'Each dot is a campaign. Size is sales volume, colour is the ACOS band, '
    +   'and the dashed rule is break even. Click one to open its row below.'
    +   '</div></div>'
    + (hidden ? '<span style="font-size:12px;color:var(--ppc-muted)" '
                + 'title="Campaigns spending far more than the rest are left '
                + 'out so the others are not squeezed into one row of pixels. '
                + 'They are still in the table.">' + hidden + ' outlier'
                + (hidden === 1 ? "" : "s") + ' hidden</span>' : '')
    + '</div>'
    + '<div style="display:flex;gap:14px;margin:10px 0 12px;font-size:11px;'
    +   'color:var(--ppc-muted);align-items:center;flex-wrap:wrap">'
    +   '<span style="font-weight:600">ACOS:</span>' + legend + '</div>'
    + '<div class="ppc-map">' + svg + '</div>'
    + '</div>';
}

/* ---- 3. the cohorts ------------------------------------------------------ */
function ppccCohorts(j, cur){
  const c = j.cohorts || {};
  if(!c.all || !c.all.n) return "";
  const ORDER = ["profitable", "marginal", "unprofitable", "no_sales",
                 "no_activity", "unclassified"];
  // The mockup's muted set -- a bar of six saturated colours is a barcode.
  const TONE = {profitable: "var(--ppc-cohort-ok)",
                marginal: "var(--ppc-cohort-mid)",
                unprofitable: "var(--ppc-cohort-bad)",
                no_sales: "var(--ppc-acos7)",
                no_activity: "var(--ppc-dim)",
                unclassified: "var(--ppc-muted)"};

  let bar = '<div class="ppc-cohortbar">';
  ORDER.forEach(function(k){
    const b = c[k];
    if(!b || !b.n) return;
    bar += '<div title="' + _pEsc((b.label || k) + ": " + b.n) + '" style="width:'
      + (100 * b.n / c.all.n).toFixed(2) + '%;background:' + TONE[k] + '"></div>';
  });
  bar += '</div>';

  let cards = '<div class="ppc-cohorts">'
    + '<div class="ppc-cohort all">'
    + '<div class="k" style="color:var(--ppc-orange)">ALL</div>'
    + '<div class="n">' + c.all.n + '</div>'
    + '<div class="s">' + ppcMoney0(c.all.spend, cur) + ' spend</div></div>';
  ORDER.forEach(function(k){
    const b = c[k];
    if(!b || !b.n) return;
    cards += '<div class="ppc-cohort">'
      + '<div class="k" style="color:var(--ppc-muted)">'
      +   '<span class="ppc-dot" style="background:' + TONE[k]
      +   ';margin-right:0"></span>'
      +   _pEsc((b.label || k).toUpperCase()) + '</div>'
      + '<div class="n">' + b.n + '</div>'
      + '<div class="s">' + ppcMoney0(b.spend, cur) + ' spend · '
      +   ppcMoney0(b.sales, cur) + ' sales</div></div>';
  });
  cards += '</div>';

  return '<div class="ppc-panel">'
    + '<div style="font-size:15px;font-weight:700;margin-bottom:2px">'
    +   'Performance Cohorts</div>'
    + '<div style="font-size:12px;color:var(--ppc-muted);margin-bottom:14px">'
    +   'Against this account\'s own break-even ACOS. <b>No sales</b> spent '
    +   'money and got nothing back; <b>no activity</b> did not run in this '
    +   'window — they are kept apart because only one of them is money lost.'
    + '</div>'
    + bar + cards + '</div>';
}

/* ---- 4. Top Campaigns ---------------------------------------------------- */
function ppccTable(j, cur){
  const rows = ppccRows();
  const pill = function(f, v){
    return '<button class="ppc-tpill' + (PPCC[f] === v ? " on" : "") + '" '
      + 'onclick="ppccSet(' + jsArg(f) + ',' + jsArg(v) + ')">'
      + _pEsc(v) + '</button>';
  };

  let h = '<div class="ppc-panel" style="margin-bottom:0">'
    + '<div style="display:flex;justify-content:space-between;'
    +   'align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px">'
    + '<span style="font-size:15px;font-weight:700">Top Campaigns</span>'
    + '<input class="ppc-input ppc-pill-input" style="width:200px" '
    +   'placeholder="Search campaigns…" oninput="ppccFilter(this.value)">'
    + '</div>'
    + '<div style="display:flex;align-items:center;gap:6px;margin-bottom:16px;'
    +   'flex-wrap:wrap">'
    + '<span class="ppc-filterlabel" style="font-size:11px;letter-spacing:.5px">'
    +   'TYPE</span>'
    + ["All", "SP", "SB", "SD"].map(function(v){ return pill("type", v); }).join("")
    + '<span class="ppc-filterlabel" style="font-size:11px;letter-spacing:.5px;'
    +   'margin-left:14px">STATUS</span>'
    + ["All", "Enabled", "Paused"].map(function(v){ return pill("status", v); }).join("")
    + '<span class="ppc-filterlabel" style="font-size:11px;letter-spacing:.5px;'
    +   'margin-left:14px">MIN SPEND</span>'
    + '<input class="ppc-input" style="width:60px;padding:3px 8px;font-size:12px" '
    +   'value="' + _pEsc(PPCC.minSpend) + '" placeholder="0" '
    +   'oninput="ppccSet(\'minSpend\', this.value)">'
    + '<span class="ppc-filterlabel" style="font-size:11px;letter-spacing:.5px;'
    +   'margin-left:14px">ACOS</span>'
    + '<div style="display:flex;flex-direction:column;align-items:center">'
    +   '<span style="font-size:10px;color:var(--ppc-muted);margin-bottom:2px">'
    +     'ACoS: 0% – ' + (Number(PPCC.maxAcos) >= 200 ? "200%+"
                           : (PPCC.maxAcos + "%")) + '</span>'
    +   '<div class="ppc-slider" style="width:180px;height:16px">'
    +     '<div class="track"></div>'
    +     '<div class="fill" style="width:' + (Number(PPCC.maxAcos) / 2)
    +       '%;background:var(--ppc-blue)"></div>'
    +     '<input type="range" min="0" max="200" step="5" value="'
    +       PPCC.maxAcos + '" style="accent-color:var(--ppc-blue)" '
    +       'oninput="ppccSet(\'maxAcos\', this.value)">'
    +   '</div></div>'
    + '</div>';

  if(!rows.length){
    return h + '<div style="color:var(--ppc-muted);padding:8px 0">'
      + 'No campaigns match those filters.</div></div>';
  }

  h += '<div style="overflow-x:auto"><table class="ppc-table camp" '
    + 'style="min-width:1150px"><thead><tr><th style="width:20px"></th>'
    + ppcTh("Opportunity", "opportunity", PPCC, "ppccSort", "left",
            "How much there is to gain by looking at this one.")
    + ppcTh("Campaign", "name", PPCC, "ppccSort", "left")
    + ppcTh("Type", "ad_product", PPCC, "ppccSort", "left")
    + ppcTh("Status", "status", PPCC, "ppccSort", "left")
    + '<th class="ppc-tint-profit ppc-sortable" style="text-align:right" '
    +   'onclick="ppccSort(' + jsArg("profit") + ')" title="Estimated from this '
    +   'account\'s measured fee and stock cost.">Profit'
    +   '<span class="ppc-q">?</span><span class="ppc-sortarrow'
    +   (PPCC.sort === "profit" ? " on" : "") + '">'
    +   (PPCC.sort === "profit" ? (PPCC.desc ? "↓" : "↑") : "↕") + '</span></th>'
    + ppcTh("Clicks", "clicks", PPCC, "ppccSort", "right")
    + ppcTh("CTR", "ctr_pct", PPCC, "ppccSort", "right")
    + ppcTh("CPC", "cpc", PPCC, "ppccSort", "right")
    + ppcTh("CPA", "cpa", PPCC, "ppccSort", "right")
    + ppcTh("Spend", "spend", PPCC, "ppccSort", "right")
    + ppcTh("Sales", "sales", PPCC, "ppccSort", "right")
    + ppcTh("ACoS", "acos_pct", PPCC, "ppccSort", "right")
    + ppcTh("RoAS", "roas", PPCC, "ppccSort", "right")
    + '</tr></thead><tbody>';

  const TYPE = {SPONSORED_PRODUCTS: ["sp", "SP"],
                SPONSORED_BRANDS: ["sb", "SB"],
                SPONSORED_DISPLAY: ["sd", "SD"]};
  rows.forEach(function(r){
    const id = String(r.campaign_id);
    const open = (PPCC.open === id);
    const tp = TYPE[String(r.ad_product || "").toUpperCase()];
    h += '<tr id="ppcc_row_' + _pEsc(id) + '" class="'
      + (open ? "open" : "") + '" style="cursor:pointer'
      + (PPCC.highlight === id
          ? ";outline:1px solid var(--ppc-blue);outline-offset:-1px" : "")
      + '" onclick="ppccToggle(' + jsArg(id) + ')">'
      + '<td style="text-align:center;color:var(--ppc-dim);font-size:11px">'
      +   (open ? "⌃" : "⌄") + '</td>'
      + '<td>' + ppcOpp(r.opportunity) + '</td>'
      + '<td style="font-size:13px;max-width:420px;overflow:hidden;'
      +   'text-overflow:ellipsis;white-space:nowrap" title="'
      +   _pEsc(r.name || id) + '">' + _pEsc(r.name || id) + '</td>'
      + '<td style="text-align:left">'
      +   (tp ? '<span class="ppc-badge ' + tp[0] + '">' + tp[1] + '</span>'
            : '<span class="ppc-badge plain">'
              + _pEsc(r.ad_product || "") + '</span>') + '</td>'
      + '<td style="text-align:left">'
      +   (String(r.status || "").toUpperCase() === "ENABLED"
            ? '<span class="ppc-badge enabled">ENABLED</span>'
            : '<span class="ppc-badge plain">' + _pEsc(r.status || "")
              + '</span>') + '</td>'
      + '<td class="ppc-tint-profit">' + ppcProfit(r.profit, cur, "greenred")
      +   '</td>'
      + '<td>' + ppcNum(r.clicks) + '</td>'
      + '<td>' + ppcPct(r.ctr_pct, "", 1) + '</td>'
      + '<td>' + ppcMoney(r.cpc, cur) + '</td>'
      + '<td>' + ppcMoney(r.cpa, cur,
          "No attributed orders, so there is no cost per order.") + '</td>'
      + '<td style="font-weight:500">' + ppcMoney0(r.spend, cur) + '</td>'
      + '<td>' + ppcMoney0(r.sales, cur) + '</td>'
      + '<td>' + ppcPct(r.acos_pct,
          "No attributed sales, so ACOS is undefined — not 0%.") + '</td>'
      + '<td>' + ppcX(r.roas) + '</td>'
      + '</tr>';
    if(open) h += ppccDetail(j, r, cur);
  });
  return h + '</tbody></table></div></div>';
}

/* What one campaign bought: six stat boxes, then its own search terms.
 *
 * The terms come from the Search Term Report, which covers its own fixed
 * window. When it has nothing for this campaign the panel says so, because an
 * empty sub-table reads as "this campaign got no searches" when the truth is
 * usually "the report does not cover it". */
function ppccDetail(j, r, cur){
  const terms = (j.terms_by_campaign || {})[r.name] || [];
  const box = function(label, val, isProfit){
    return '<div class="box' + (isProfit ? " profit" : "") + '">'
      + '<div class="k">' + label + '</div>'
      + '<div class="v">' + val + '</div></div>';
  };
  let h = '<tr><td colspan="14" style="padding:0"><div class="ppc-campexp">'
    + '<div class="boxes">'
    +   box("Spend", ppcMoney0(r.spend, cur))
    +   box("Sales", ppcMoney0(r.sales, cur))
    +   box("Clicks", ppcNum(r.clicks))
    +   box("CPC", ppcMoney(r.cpc, cur))
    +   box("Purchases", ppcNum(r.orders))
    +   box("Profit", ppcProfit(r.profit, cur, "greenred"), true)
    + '</div>';

  if(!terms.length){
    h += '<div style="font-size:13px;color:var(--ppc-muted)">The stored search '
      + 'term report has no rows for this campaign. That usually means the '
      + 'report covers a different window rather than that the campaign got no '
      + 'searches.</div>';
  }else{
    h += '<div style="font-size:13px;color:var(--ppc-muted);margin-bottom:10px">'
      + terms.length + ' search term' + (terms.length === 1 ? "" : "s")
      + ' in this campaign</div>'
      + '<div style="overflow-x:auto"><table><thead><tr>'
      + '<th>Search Term</th><th>Match Type</th>'
      + '<th class="ppc-tint-profit">Profit</th>'
      + '<th>Spend</th><th>Sales</th><th>ACOS</th><th>Clicks</th>'
      + '<th>CPC</th><th>Purchases</th></tr></thead><tbody>';
    terms.forEach(function(t){
      h += '<tr title="' + _pEsc(t.search_term) + '">'
        + '<td style="max-width:260px;overflow-wrap:anywhere">'
        +   _pEsc(t.search_term) + '</td>'
        // Plain white text, no coloured badge -- the mockup is explicit, and a
        // second set of badges inside an expanded row is noise.
        + '<td style="font-size:12px;color:var(--ppc-text)">'
        +   _pEsc(t.match_type) + '</td>'
        + '<td class="ppc-tint-profit">'
        +   ppcProfit(t.profit, cur, "greenred") + '</td>'
        + '<td>' + ppcMoney0(t.spend, cur) + '</td>'
        + '<td>' + ppcMoney0(t.sales, cur) + '</td>'
        + '<td>' + ppcPct(t.acos_pct,
            "No sales from this term, so ACOS is undefined — not 0%.") + '</td>'
        + '<td>' + ppcNum(t.clicks) + '</td>'
        + '<td>' + ppcMoney(t.cpc, cur) + '</td>'
        + '<td style="color:var(--ppc-blue)">' + ppcNum(t.orders) + '</td>'
        + '</tr>';
    });
    h += '</tbody></table></div>';
  }
  return h + '</div></td></tr>';
}
