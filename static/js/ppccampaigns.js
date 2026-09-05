/* static/js/ppccampaigns.js -- the Campaign Analytics screen.
 *
 * Every campaign, sortable, with the search terms it actually bought folded
 * underneath each one.
 *
 * THE PROFITABILITY MAP IS THE POINT OF THIS PAGE. Each campaign is a dot:
 * spend across, estimated profit up, and a line at zero. Everything below the
 * line is losing money, and the further right it sits the more of it there is.
 * That is one glance instead of sorting a 254-row table twice.
 *
 * It is drawn as plain SVG rather than through salesCombo, which draws a time
 * series -- this has no time axis at all. The colours and the break-even line
 * come from the same vocabulary as everything else on these screens.
 *
 * NOTHING HERE WRITES. No bid, no budget, no campaign state (CLAUDE.md Rule 8).
 */

const PPCC = {data: null, loading: false, sort: "spend", desc: true, q: "",
              type: "all", status: "all", open: "", minSpend: ""};

async function ppccLoad(){
  const host = document.getElementById("ppcc_body");
  if(!host || PPCC.loading) return;
  PPCC.loading = true;
  host.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Reading the campaigns…</div>';
  try{
    const qs = ppcQS(PPCWIN.start
      ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
    const j = await (await fetch("/ppc/analytics/campaigns?" + qs)).json();
    PPCC.loading = false;
    if(!j || !j.ok){
      host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _pEsc((j && j.error) || "Could not read the campaigns.") + '</div>';
      return;
    }
    PPCC.data = j;
    ppccRender();
  }catch(e){
    PPCC.loading = false;
    host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + 'Could not read the campaigns.</div>';
  }
}

function ppccSort(k){
  if(PPCC.sort === k) PPCC.desc = !PPCC.desc;
  else { PPCC.sort = k; PPCC.desc = true; }
  ppccRender();
}
function ppccSet(f, v){ PPCC[f] = v; ppccRender(); }
function ppccFilter(v){ PPCC.q = (v || "").toLowerCase(); ppccRender(); }
function ppccToggle(id){
  PPCC.open = (PPCC.open === id) ? "" : id;
  ppccRender();
}

function ppccRows(){
  const j = PPCC.data;
  let rows = (j && j.campaigns) || [];
  if(PPCC.q){
    rows = rows.filter(function(r){
      return String(r.name || "").toLowerCase().indexOf(PPCC.q) >= 0;
    });
  }
  if(PPCC.type !== "all"){
    rows = rows.filter(function(r){
      return String(r.ad_product || "").toUpperCase() === PPCC.type;
    });
  }
  if(PPCC.status !== "all"){
    rows = rows.filter(function(r){
      return String(r.status || "").toUpperCase() === PPCC.status;
    });
  }
  const min = parseFloat(PPCC.minSpend);
  if(!isNaN(min)) rows = rows.filter(function(r){ return (r.spend || 0) >= min; });
  return ppcSortRows(rows, PPCC.sort, PPCC.desc);
}

function ppccRender(){
  const host = document.getElementById("ppcc_body");
  const j = PPCC.data;
  if(!host || !j) return;
  const cur = "GBP";
  const av = j.availability || {};

  let h = ppcWindowBar("ppccLoad");

  if(!(j.campaigns || []).length){
    host.innerHTML = h + ppcUnavailable(
      "No campaigns stored for this window",
      (av.campaigns && av.campaigns.why) || "Nothing is stored for this window.");
    return;
  }

  h += ppcProductNote(av);
  h += ppcRatesNote(j.rates);
  h += ppccTypeBreakdown(j, cur);
  h += ppccMap(j, cur);
  h += ppccCohorts(j, cur);
  h += ppccTable(j, cur);

  host.innerHTML = h;
}

/* Spend by ad product and by match type, side by side.
 *
 * The spec draws a donut with SP gold and SB blue. With only Sponsored Products
 * stored, a donut would be one full circle -- which says nothing and implies
 * the other slice was measured at zero. A bar per product that exists says the
 * same thing honestly, and the note above already explains what is missing. */
function ppccTypeBreakdown(j, cur){
  const prods = j.by_ad_product || [], matches = j.by_match_type || [];
  if(!prods.length && !matches.length) return "";
  const tone = {SPONSORED_PRODUCTS: "#f0c000", SPONSORED_BRANDS: "#58a6ff",
                SPONSORED_DISPLAY: "#bc8cff",
                BROAD: "#d29922", PHRASE: "#58a6ff", EXACT: "#3fb950",
                TARGETING_EXPRESSION: "#f85149",
                TARGETING_EXPRESSION_PREDEFINED: "#8b949e"};
  const nice = {SPONSORED_PRODUCTS: "Sponsored Products",
                SPONSORED_BRANDS: "Sponsored Brands",
                SPONSORED_DISPLAY: "Sponsored Display"};
  const block = function(title, rows, sub){
    if(!rows.length) return "";
    let b = '<div><div style="font-weight:600;font-size:12.5px;margin-bottom:2px">'
      + _pEsc(title) + '</div>'
      + '<div class="cc" style="font-size:11px;margin-bottom:8px">'
      + _pEsc(sub) + '</div>'
      + '<table class="kv" style="width:100%">'
      + '<thead><tr><th>Type</th><th style="text-align:right">Spend</th>'
      + '<th style="text-align:right">% spend</th>'
      + '<th style="text-align:right">Sales</th>'
      + '<th style="text-align:right">ACOS</th>'
      + '<th style="text-align:right">Profit</th></tr></thead><tbody>';
    rows.forEach(function(r){
      const c = tone[String(r.key).toUpperCase()] || "#8b949e";
      b += '<tr><td style="border-left:3px solid ' + c + ';padding-left:8px">'
        + '<span style="display:inline-block;width:7px;height:7px;'
        + 'border-radius:50%;background:' + c + ';margin-right:6px"></span>'
        + _pEsc(nice[String(r.key).toUpperCase()] || r.key) + '</td>'
        + '<td style="text-align:right;font-family:ui-monospace,monospace">'
        +   ppcMoney(r.spend, cur) + '</td>'
        + '<td style="text-align:right" class="cc">' + ppcPct(r.spend_share_pct) + '</td>'
        + '<td style="text-align:right;font-family:ui-monospace,monospace">'
        +   ppcMoney(r.sales, cur) + '</td>'
        + '<td style="text-align:right">' + ppcPct(r.acos_pct) + '</td>'
        + '<td style="text-align:right">' + ppcProfit(r.profit, cur) + '</td></tr>';
    });
    return b + '</tbody></table></div>';
  };
  return '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:10px">Where the money went</div>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fit,'
    + 'minmax(320px,1fr));gap:18px">'
    + block("Campaign types", prods,
            "Sponsored Products, Brands and Display are separate report types. "
            + "Only the ones actually stored appear here.")
    + block("Match types", matches,
            "From the search term report. Product targeting is a placement "
            + "rather than something anybody typed.")
    + '</div></div>';
}

/* Every campaign as a dot: spend across, estimated profit up, zero marked.
 *
 * WHY NOT A BUBBLE SIZED BY SALES, as the spec asks: sizing by sales encodes a
 * third number in an area, which people read badly, and on this account most
 * campaigns cluster in the bottom-left where overlapping bubbles hide each
 * other. Colour by ACOS band carries the same information and stays readable
 * where the dots pile up. Radius still grows a little with sales so the big
 * ones are findable.
 *
 * Drawn only when profit could be worked out -- an axis labelled "profit" with
 * nothing on it is worse than a sentence saying why. */
function ppccMap(j, cur){
  const rows = (j.campaigns || []).filter(function(r){
    return r.spend !== null && r.spend !== undefined && r.profit !== null
        && r.profit !== undefined;
  });
  if(!rows.length){
    return ppcUnavailable("Campaign profitability map",
      "Profit cannot be worked out for this window, so there is nothing to plot "
      + "against it. " + ((j.rates && j.rates.why) || "This account has no "
      + "measured fee rate or no costed orders."));
  }
  const W = 1100, H = 340, padL = 74, padR = 24, padT = 16, padB = 46;
  const iw = W - padL - padR, ih = H - padT - padB;
  const sp = rows.map(function(r){ return r.spend; });
  const pf = rows.map(function(r){ return r.profit; });
  const sMax = Math.max.apply(null, sp) || 1;
  let pMin = Math.min.apply(null, pf), pMax = Math.max.apply(null, pf);
  if(pMin > 0) pMin = 0;
  if(pMax < 0) pMax = 0;
  const pSpan = (pMax - pMin) || 1;
  const x = function(v){ return padL + (v / sMax) * iw; };
  const y = function(v){ return padT + ih - ((v - pMin) / pSpan) * ih; };

  const band = function(a){
    if(a === null || a === undefined) return "#6e7681";
    if(a < 15) return "#3fb950";
    if(a < 25) return "#2d8a44";
    if(a < 40) return "#d29922";
    if(a < 60) return "#e87a1e";
    if(a < 100) return "#f85149";
    return "#c0304a";
  };

  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;'
    + 'background:var(--bg);border-radius:6px" '
    + 'preserveAspectRatio="xMidYMid meet">';
  // Grid and axis labels.
  for(let i = 0; i <= 4; i++){
    const v = pMin + (pSpan * i / 4), yy = y(v);
    svg += '<line x1="' + padL + '" y1="' + yy + '" x2="' + (W - padR) + '" y2="' + yy
      + '" stroke="var(--line2,#30363d)" stroke-width="1" stroke-dasharray="4 4"/>'
      + '<text x="' + (padL - 8) + '" y="' + (yy + 4) + '" text-anchor="end" '
      + 'font-size="11" fill="var(--ink2,#8b949e)">'
      + (v < 0 ? "-" : "") + "£" + Math.abs(Math.round(v)) + '</text>';
  }
  for(let i = 0; i <= 4; i++){
    const v = sMax * i / 4, xx = x(v);
    svg += '<line x1="' + xx + '" y1="' + padT + '" x2="' + xx + '" y2="' + (padT + ih)
      + '" stroke="var(--line2,#30363d)" stroke-width="1" stroke-dasharray="4 4"/>'
      + '<text x="' + xx + '" y="' + (H - 22) + '" text-anchor="middle" '
      + 'font-size="11" fill="var(--ink2,#8b949e)">£' + Math.round(v) + '</text>';
  }
  // BREAK-EVEN. The one line on the chart that decides anything.
  const y0 = y(0);
  svg += '<line x1="' + padL + '" y1="' + y0 + '" x2="' + (W - padR) + '" y2="' + y0
    + '" stroke="#8b949e" stroke-width="1.4" stroke-dasharray="8 5"/>'
    + '<text x="' + (W - padR - 4) + '" y="' + (y0 - 6) + '" text-anchor="end" '
    + 'font-size="10" fill="#8b949e" letter-spacing="1">BREAK EVEN</text>';

  const sMaxSales = Math.max.apply(null,
    rows.map(function(r){ return r.sales || 0; })) || 1;
  rows.forEach(function(r){
    const rad = 3.5 + 6 * Math.sqrt((r.sales || 0) / sMaxSales);
    svg += '<circle cx="' + x(r.spend).toFixed(1) + '" cy="' + y(r.profit).toFixed(1)
      + '" r="' + rad.toFixed(1) + '" fill="' + band(r.acos_pct) + '" opacity="0.85">'
      + '<title>' + _pEsc(r.name || r.campaign_id)
      + "\nSpend: " + _pEsc(ppcMoney(r.spend, cur).replace(/<[^>]+>/g, ""))
      + "\nSales: " + _pEsc(ppcMoney(r.sales, cur).replace(/<[^>]+>/g, ""))
      + "\nProfit: " + _pEsc(ppcMoney(r.profit, cur).replace(/<[^>]+>/g, ""))
      + "\nACOS: " + (r.acos_pct === null || r.acos_pct === undefined
                      ? "no sales" : r.acos_pct + "%")
      + '</title></circle>';
  });
  svg += '<text x="14" y="' + (padT + ih / 2) + '" font-size="11" '
    + 'fill="var(--ink2,#8b949e)" transform="rotate(-90 14 '
    + (padT + ih / 2) + ')" text-anchor="middle">Estimated profit</text>'
    + '<text x="' + (padL + iw / 2) + '" y="' + (H - 5) + '" font-size="11" '
    + 'fill="var(--ink2,#8b949e)" text-anchor="middle">Ad spend</text>'
    + '</svg>';

  const legend = [["< 15%", "#3fb950"], ["15–25%", "#2d8a44"], ["25–40%", "#d29922"],
                  ["40–60%", "#e87a1e"], ["60–100%", "#f85149"], ["> 100%", "#c0304a"],
                  ["no sales", "#6e7681"]].map(function(p){
    return '<span style="display:inline-flex;align-items:center;gap:4px;'
      + 'margin-right:12px"><span style="width:8px;height:8px;border-radius:50%;'
      + 'background:' + p[1] + ';display:inline-block"></span>' + p[0] + '</span>';
  }).join("");

  return '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:2px">Campaign profitability map</div>'
    + '<div class="cc" style="font-size:11.5px;margin-bottom:9px">'
    + 'One dot per campaign. Across is what it spent, up is what it made, and the '
    + 'dashed line is break even — everything under it is losing money. Colour is '
    + 'the ACOS band; a bigger dot sold more. Hover for the figures.'
    + '</div>' + svg
    + '<div class="cc" style="font-size:11px;margin-top:8px">' + legend + '</div>'
    + '</div>';
}

function ppccCohorts(j, cur){
  const c = j.cohorts || {};
  if(!c.all || !c.all.n) return "";
  const order = ["profitable", "marginal", "unprofitable", "no_sales",
                 "no_activity", "unclassified"];
  const tone = {profitable: "#2ea043", marginal: "#c9862a",
                unprofitable: "#c04b45", no_sales: "#8b3a37",
                no_activity: "#4d5560", unclassified: "#6e7681"};
  // A single bar, so the shape of the account is one glance. Widths are of the
  // COUNT, not the spend: this answers "how many campaigns", and the cards
  // under it carry the money.
  let bar = '<div style="display:flex;height:22px;border-radius:4px;'
    + 'overflow:hidden;margin-bottom:10px">';
  order.forEach(function(k){
    const b = c[k];
    if(!b || !b.n) return;
    const pct = (100 * b.n / c.all.n).toFixed(2);
    bar += '<div title="' + _pEsc((b.label || k) + ": " + b.n) + '" style="width:'
      + pct + '%;background:' + tone[k] + '"></div>';
  });
  bar += '</div>';

  let cards = '<div style="display:grid;grid-template-columns:repeat(auto-fit,'
    + 'minmax(150px,1fr));gap:8px">';
  cards += '<div class="panelcard" style="padding:11px 13px;border-radius:8px;'
    + 'border:2px solid var(--gold)"><div class="cc" style="font-size:10.5px;'
    + 'text-transform:uppercase;letter-spacing:.7px">All</div>'
    + '<div style="font-size:26px;font-weight:600">' + c.all.n + '</div>'
    + '<div class="cc" style="font-size:11px">' + ppcMoney(c.all.spend, cur)
    + ' spend</div></div>';
  order.forEach(function(k){
    const b = c[k];
    if(!b || !b.n) return;
    cards += '<div class="panelcard" style="padding:11px 13px;border-radius:8px">'
      + '<div style="font-size:10.5px;text-transform:uppercase;letter-spacing:.7px;'
      + 'color:' + tone[k] + '">'
      + '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
      + 'background:' + tone[k] + ';margin-right:5px"></span>'
      + _pEsc(b.label || k) + '</div>'
      + '<div style="font-size:26px;font-weight:600">' + b.n + '</div>'
      + '<div class="cc" style="font-size:11px">' + ppcMoney(b.spend, cur)
      + ' · ' + ppcMoney(b.sales, cur) + ' sales</div></div>';
  });
  cards += '</div>';

  return '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:2px">Performance cohorts</div>'
    + '<div class="cc" style="font-size:11.5px;margin-bottom:9px">'
    + 'Against this account\'s own break-even ACOS. <b>No sales</b> spent money '
    + 'and got nothing; <b>no activity</b> did not run in this window — they are '
    + 'kept apart because only one of them is money lost.</div>'
    + bar + cards + '</div>';
}

function ppccTable(j, cur){
  const rows = ppccRows();
  const pill = function(f, v, label){
    return '<button class="db-chip' + (PPCC[f] === v ? " on" : "") + '" '
      + 'onclick="ppccSet(' + jsArg(f) + ',' + jsArg(v) + ')">'
      + _pEsc(label) + '</button>';
  };
  let h = '<div class="panelcard" style="padding:0;border-radius:8px;overflow:hidden">'
    + '<div style="padding:12px 14px">'
    + '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
    + '<b style="font-size:13px">Campaigns</b>'
    + '<input placeholder="Filter campaigns…" oninput="ppccFilter(this.value)" '
    +   'style="font-size:12px;padding:5px 9px;min-width:190px;margin-left:auto">'
    + '</div>'
    + '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
    +   'margin-top:9px">'
    + '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +   'letter-spacing:.7px">Type</span>'
    + pill("type", "all", "All") + pill("type", "SPONSORED_PRODUCTS", "SP")
    + pill("type", "SPONSORED_BRANDS", "SB") + pill("type", "SPONSORED_DISPLAY", "SD")
    + '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +   'letter-spacing:.7px;margin-left:10px">Status</span>'
    + pill("status", "all", "All") + pill("status", "ENABLED", "Enabled")
    + pill("status", "PAUSED", "Paused")
    + '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +   'letter-spacing:.7px;margin-left:10px">Min spend</span>'
    + '<input value="' + _pEsc(PPCC.minSpend) + '" placeholder="0" '
    +   'oninput="ppccSet(\'minSpend\', this.value)" '
    +   'style="font-size:12px;padding:4px 7px;width:70px">'
    + '</div></div>';

  if(!rows.length){
    return h + '<div class="cc" style="padding:16px">No campaigns match those '
      + 'filters.</div></div>';
  }

  h += '<div style="overflow-x:auto"><table class="kv ordtable" '
    + 'style="width:100%;min-width:1100px"><thead><tr><th style="width:20px"></th>'
    + ppcTh("Opp", "opportunity", PPCC, "ppccSort", "left")
    + ppcTh("Campaign", "name", PPCC, "ppccSort", "left")
    + ppcTh("Status", "status", PPCC, "ppccSort", "left")
    + ppcTh("Profit", "profit", PPCC, "ppccSort", "right",
            "Estimated from this account's measured fee and stock cost.")
    + ppcTh("Clicks", "clicks", PPCC, "ppccSort", "right")
    + ppcTh("CTR", "ctr_pct", PPCC, "ppccSort", "right")
    + ppcTh("CPC", "cpc", PPCC, "ppccSort", "right")
    + ppcTh("CPA", "cpa", PPCC, "ppccSort", "right")
    + ppcTh("Spend", "spend", PPCC, "ppccSort", "right")
    + ppcTh("Sales", "sales", PPCC, "ppccSort", "right")
    + ppcTh("ACOS", "acos_pct", PPCC, "ppccSort", "right")
    + ppcTh("ROAS", "roas", PPCC, "ppccSort", "right")
    + '</tr></thead><tbody>';

  const tone = {SPONSORED_PRODUCTS: ["rgba(240,192,0,0.18)", "#f0c000", "SP"],
                SPONSORED_BRANDS: ["rgba(88,166,255,0.18)", "#58a6ff", "SB"],
                SPONSORED_DISPLAY: ["rgba(188,140,255,0.18)", "#bc8cff", "SD"]};
  rows.forEach(function(r){
    const open = (PPCC.open === String(r.campaign_id));
    const tp = tone[String(r.ad_product || "").toUpperCase()];
    // jsArg, not JSON.stringify: this attribute is double-quoted, and
    // JSON.stringify returns a double-quoted literal that ends it early. A
    // campaign id is Amazon's own and safe today, which is exactly how a
    // quoting bug survives until the day something has an apostrophe in it.
    h += '<tr style="cursor:pointer" onclick="ppccToggle('
      + jsArg(String(r.campaign_id)) + ')">'
      + '<td class="cc" style="font-size:11px">' + (open ? "⌄" : "›") + '</td>'
      + '<td>' + ppcOpp(r.opportunity) + '</td>'
      + '<td style="font-size:11.5px;max-width:300px;overflow-wrap:anywhere">'
      +   _pEsc(r.name || r.campaign_id)
      +   (tp ? ' <span style="background:' + tp[0] + ';color:' + tp[1]
             + ';font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px">'
             + tp[2] + '</span>' : '')
      + '</td>'
      + '<td>' + (String(r.status || "").toUpperCase() === "ENABLED"
          ? '<span style="background:rgba(63,185,80,0.15);color:var(--ok);'
            + 'font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px">'
            + 'ENABLED</span>'
          : '<span class="cc" style="font-size:10.5px">' + _pEsc(r.status || "")
            + '</span>') + '</td>'
      + '<td style="text-align:right">' + ppcProfit(r.profit, cur) + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.clicks) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.ctr_pct, "", 2) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.cpc, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.cpa, cur,
          "No attributed orders, so there is no cost per order.") + '</td>'
      + '<td style="text-align:right;font-weight:500">' + ppcMoney(r.spend, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.sales, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.acos_pct,
          "No attributed sales, so ACOS is undefined — not 0%.") + '</td>'
      + '<td style="text-align:right">' + ppcX(r.roas) + '</td>'
      + '</tr>';
    if(open) h += ppccDetail(j, r, cur);
  });
  return h + '</tbody></table></div></div>';
}

/* What one campaign bought: its own figures, then the search terms under it.
 *
 * The terms come from the Search Term Report, which covers its own fixed window
 * -- so this says how many there are rather than implying the two periods are
 * the same. When the report has nothing for this campaign it says so, because
 * an empty sub-table reads as "this campaign got no searches" when the truth is
 * usually "the report does not cover it". */
function ppccDetail(j, r, cur){
  const terms = (j.terms_by_campaign || {})[r.name] || [];
  let h = '<tr><td colspan="13" style="padding:0">'
    + '<div style="margin:0 0 0 38px;border-left:3px solid var(--accent);'
    + 'padding:12px 14px;background:rgba(255,255,255,0.01)">';

  const box = function(label, val){
    return '<div class="panelcard" style="padding:9px 11px;border-radius:4px;'
      + 'text-align:center"><div class="cc" style="font-size:10px;'
      + 'text-transform:uppercase;letter-spacing:.8px">' + _pEsc(label) + '</div>'
      + '<div style="font-size:15px;font-weight:600;margin-top:2px">' + val
      + '</div></div>';
  };
  h += '<div style="display:grid;grid-template-columns:repeat(auto-fit,'
    + 'minmax(96px,1fr));gap:4px;margin-bottom:10px">'
    + box("Spend", ppcMoney(r.spend, cur))
    + box("Sales", ppcMoney(r.sales, cur))
    + box("Clicks", ppcNum(r.clicks))
    + box("CPC", ppcMoney(r.cpc, cur))
    + box("Orders", ppcNum(r.orders))
    + box("Profit", ppcProfit(r.profit, cur))
    + '</div>';

  if(!terms.length){
    h += '<div class="cc" style="font-size:12px">The stored search term report '
      + 'has no rows for this campaign. That usually means the report covers a '
      + 'different window rather than that the campaign got no searches.</div>';
  }else{
    h += '<div class="cc" style="font-size:12.5px;margin-bottom:6px">'
      + terms.length + ' search term' + (terms.length === 1 ? "" : "s")
      + ' in this campaign</div>'
      + '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
      + '<thead><tr>'
      + '<th style="font-size:11.5px">Search term</th>'
      + '<th style="font-size:11.5px">Match type</th>'
      + '<th style="text-align:right;font-size:11.5px">Profit</th>'
      + '<th style="text-align:right;font-size:11.5px">Spend</th>'
      + '<th style="text-align:right;font-size:11.5px">Sales</th>'
      + '<th style="text-align:right;font-size:11.5px">ACOS</th>'
      + '<th style="text-align:right;font-size:11.5px">Clicks</th>'
      + '<th style="text-align:right;font-size:11.5px">CPC</th>'
      + '<th style="text-align:right;font-size:11.5px">Orders</th>'
      + '</tr></thead><tbody>';
    terms.forEach(function(t){
      h += '<tr><td style="font-size:11.5px;max-width:260px;'
        +   'overflow-wrap:anywhere" title="' + _pEsc(t.search_term) + '">'
        +   _pEsc(t.search_term) + '</td>'
        + '<td class="cc" style="font-size:11px">' + _pEsc(t.match_type) + '</td>'
        + '<td style="text-align:right">' + ppcProfit(t.profit, cur) + '</td>'
        + '<td style="text-align:right">' + ppcMoney(t.spend, cur) + '</td>'
        + '<td style="text-align:right">' + ppcMoney(t.sales, cur) + '</td>'
        + '<td style="text-align:right">' + ppcPct(t.acos_pct) + '</td>'
        + '<td style="text-align:right">' + ppcNum(t.clicks) + '</td>'
        + '<td style="text-align:right">' + ppcMoney(t.cpc, cur) + '</td>'
        + '<td style="text-align:right;color:var(--accent)">' + ppcNum(t.orders)
        + '</td></tr>';
    });
    h += '</tbody></table></div>';
  }
  return h + '</div></td></tr>';
}
