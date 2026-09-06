/* static/js/ppcterms.js -- Search Terms, to orbit-search-terms-v4.jsx.
 *
 * The mockup's order and its measurements:
 *
 *     header            title left, filters right, the first carrying a 2px
 *                       orange border
 *     KPI row 1         SPEND / SALES / ACOS / WASTED SPEND, gap 6
 *     KPI row 2         ROAS / CTR / CVR / AVG CPC, gap 6, then 24 clear
 *     panel             padding 20px 24px
 *       title row       "Search Terms" + filter box + Export
 *       MATCH TYPE      rounded pills, cyan when active
 *       BRAND           the same pills
 *       brand input     a box to add a brand word
 *       SPEND / ACOS    two small boxes, a 160px slider, a checkbox
 *       summary grid    5 x 2 cells, each its own bordered box, gap 4
 *       "Showing X of Y terms"
 *       the table       13 columns, profit cyan-tinted, rows expand
 *
 * THE TABLE AND THE CARDS ANSWER FOR DIFFERENT WINDOWS, AND IT SAYS SO.
 * The cards come from the daily tables and move with the dates. The table comes
 * from the stored Search Term Report, which covers ONE fixed window chosen when
 * it was pulled. Those cannot be made the same, so the report's own dates are
 * printed above the table -- a screen where half the numbers move and half do
 * not, with nothing to say why, gets noticed once and distrusted afterwards.
 *
 * NOTHING HERE WRITES (Rule 8).
 */

const PPCT = {data: null, loading: false, sort: "spend", desc: true, q: "",
              match: "All", brand: "All", zeroOnly: false, open: null,
              minSpend: "", maxSpend: "", maxAcos: 200};

async function ppctLoad(){
  const host = document.getElementById("ppct_body");
  if(!host || PPCT.loading) return;
  PPCT.loading = true;
  // The screen stays on and dims rather than going blank -- see ppcBusy.
  ppcBusy("ppct_body", true);
  if(!PPCT.data){
    host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
      + 'color:var(--ppc-muted)"><span class="genspin"></span> '
      + 'Reading the search terms…</div></div>';
  }
  try{
    const qs = ppcQS(PPCWIN.start
      ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
    const j = await (await fetch("/ppc/analytics/terms?" + qs)).json();
    PPCT.loading = false;
    if(!j || !j.ok){
      host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
        + 'color:var(--ppc-red)">'
        + _pEsc((j && j.error) || "Could not read the search terms.")
        + '</div></div>';
      return;
    }
    PPCT.data = j;
    ppctRender();
  }catch(e){
    PPCT.loading = false;
    ppcBusy("ppct_body", false);
    if(!PPCT.data){
      host.innerHTML = '<div class="ppc-page wide"><div style="padding:18px;'
        + 'color:var(--ppc-red)">Could not read the search terms.</div></div>';
    }else if(typeof toast === "function"){
      toast("Could not refresh the search terms — showing the last ones.");
    }
  }
}

function ppctSort(k){
  if(PPCT.sort === k) PPCT.desc = !PPCT.desc;
  else { PPCT.sort = k; PPCT.desc = true; }
  ppctRender();
}
function ppctSet(field, v){ PPCT[field] = v; ppctRender(); }
function ppctFilter(v){ PPCT.q = (v || "").toLowerCase(); ppctRender(); }
function ppctToggleZero(){ PPCT.zeroOnly = !PPCT.zeroOnly; ppctRender(); }
function ppctToggleRow(i){
  PPCT.open = (PPCT.open === i) ? null : i;
  ppctRender();
}
function ppctExport(){
  const qs = ppcQS(PPCWIN.start
    ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
  window.location = "/ppc/analytics/terms.csv?" + qs;
}

/* Which rows survive the filter bar. Kept apart from drawing so "showing X of
 * Y" is the same arithmetic the table used rather than a second opinion. */
function ppctRows(){
  const j = PPCT.data;
  let rows = (j && j.terms) || [];
  if(PPCT.q){
    rows = rows.filter(function(r){
      return (String(r.search_term || "") + " " + String(r.campaign || ""))
        .toLowerCase().indexOf(PPCT.q) >= 0;
    });
  }
  if(PPCT.match !== "All"){
    const want = PPCT.match.toUpperCase();
    rows = rows.filter(function(r){
      const m = String(r.match_type || "").toUpperCase();
      if(want === "PRODUCT TARGETING") return m.indexOf("TARGETING_EXPRESSION") === 0;
      return m === want;
    });
  }
  if(PPCT.brand !== "All"){
    // `branded` is TRUE, FALSE or NULL, and null means "no brand words are set
    // up" rather than "not branded" -- see domain/ppc_view.is_branded. A row
    // whose branding is unknown answers neither filter, because both answers
    // would be a claim nobody measured.
    rows = rows.filter(function(r){
      return PPCT.brand === "Branded" ? r.branded === true : r.branded === false;
    });
  }
  if(PPCT.zeroOnly){
    rows = rows.filter(function(r){ return !r.orders && r.clicks; });
  }
  const lo = parseFloat(PPCT.minSpend), hi = parseFloat(PPCT.maxSpend);
  if(!isNaN(lo)) rows = rows.filter(function(r){ return (r.spend || 0) >= lo; });
  if(!isNaN(hi)) rows = rows.filter(function(r){ return (r.spend || 0) <= hi; });
  const ma = Number(PPCT.maxAcos);
  if(ma < 200){
    rows = rows.filter(function(r){
      // A term with no sales has an UNDEFINED ACOS, not an infinite one. It is
      // kept under a ceiling, because hiding the terms that sold nothing is the
      // opposite of what somebody filtering on ACOS is looking for.
      return r.acos_pct === null || r.acos_pct === undefined || r.acos_pct <= ma;
    });
  }
  return ppcSortRows(rows, PPCT.sort, PPCT.desc);
}

function ppctRender(){
  const host = document.getElementById("ppct_body");
  const j = PPCT.data;
  if(!host || !j) return;
  const cur = j.currency || "GBP";
  const t = j.totals || {}, ch = j.change || {}, av = j.availability || {};
  const w = j.window || {};

  // ---- header: title left, the filters right ---------------------------
  let h = '<div class="ppc-page wide">'
    + '<div style="display:flex;justify-content:space-between;'
    + 'align-items:flex-start;margin-bottom:20px;flex-wrap:wrap;gap:14px">'
    + '<div><h1>Search Terms</h1>'
    +   '<p class="ppc-sub" style="max-width:340px;margin:4px 0 0">'
    +   'Search term performance across all campaigns and keywords</p></div>'
    + '<div style="display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap">'
    +   '<div><div class="ppc-flabel">Terms</div>'
    +     '<div class="ppc-fctl" style="border:2px solid var(--ppc-orange);'
    +     'border-radius:8px;min-width:180px">'
    +     ((j.terms || []).length) + ' stored</div></div>'
    +   '<div><div class="ppc-flabel">Range</div>'
    +     ppcSeg(30, "ppctLoad") + '</div>'
    +   '<div class="ppc-fctl" style="border-radius:8px">'
    +     _pEsc((w.start || "") + " to " + (w.end || "")) + '</div>'
    + '</div></div>';

  if(!(j.terms || []).length){
    h += ppcUnavailable("No search terms stored",
      (av.search_terms && av.search_terms.why)
        || "No Search Term Report is stored for this account.");
    host.innerHTML = h + '</div>';
    return;
  }

  // ---- the eight KPI cards ---------------------------------------------
  const wsp = j.wasted || {};
  const card = function(label, value, chg, good, help, why){
    return '<div class="ppc-kpi st">'
      + '<div class="k">' + label
      +   '<span class="ppc-q" title="' + _pEsc(help || "") + '">?</span></div>'
      + '<div class="row"><span class="v">'
      +   (value === null || value === undefined ? ppcDash(why) : value)
      + '</span>' + ppcChangeText(chg, good) + '</div></div>';
  };
  h += '<div class="ppc-kpis tight">'
    + card("SPEND", ppcMoney0(t.spend, cur), ch.spend, "down",
           "What Amazon charged for the ads in this window.")
    + card("SALES", ppcMoney0(t.sales, cur), ch.sales, "up",
           "Sales Amazon attributes to those ads.")
    + card("ACOS", ppcPct(t.acos_pct), ch.acos_pct, "down",
           "Spend divided by ad sales. Lower is better.")
    + card("WASTED SPEND", ppcMoney0(wsp.spend, cur, wsp.why), null, "down",
           "Spend on search terms that took a click and produced no order.",
           wsp.why)
    + '</div>'
    + '<div class="ppc-kpis tight last">'
    + card("ROAS", ppcX(t.roas), ch.roas, "up",
           "Ad sales for every pound of spend.")
    + card("CTR", ppcPct(t.ctr_pct, "", 2), ch.ctr_pct, "up",
           "Clicks per impression.")
    + card("CVR", ppcPct(t.cvr_pct, "", 2), ch.cvr_pct, "up",
           "Orders per click.")
    + card("AVG CPC", ppcMoney(t.cpc, cur), ch.cpc, "down",
           "What each click cost on average.")
    + '</div>';

  h += ppcProductNote(av);
  h += ppcRatesNote(j.rates);

  // ---- the panel --------------------------------------------------------
  const rows = ppctRows();
  h += '<div class="ppc-panel" style="padding:20px 24px;margin-bottom:0">'
    + '<div style="display:flex;justify-content:space-between;'
    +   'align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px">'
    + '<span style="font-size:16px;font-weight:700">Search Terms</span>'
    + '<div style="display:flex;gap:12px;align-items:center">'
    +   '<input class="ppc-input" placeholder="Filter search terms…" '
    +     'style="width:200px" oninput="ppctFilter(this.value)">'
    +   '<button class="ppc-btn" style="background:transparent;'
    +     'color:var(--ppc-muted)" onclick="ppctExport()">⬇ Export</button>'
    + '</div></div>';

  if(j.report_note){
    h += '<div class="ppc-note" style="margin-bottom:14px">'
      + _pEsc(j.report_note) + '</div>';
  }

  // MATCH TYPE and BRAND pills
  const pill = function(field, val){
    return '<button class="ppc-rpill' + (PPCT[field] === val ? " on" : "")
      + '" onclick="ppctSet(' + jsArg(field) + ',' + jsArg(val) + ')">'
      + _pEsc(val) + '</button>';
  };
  h += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:14px;'
    + 'flex-wrap:wrap">'
    + '<span class="ppc-filterlabel" style="margin-right:4px">MATCH TYPE</span>'
    + ["All", "Exact", "Phrase", "Broad", "Product Targeting"]
        .map(function(v){ return pill("match", v); }).join("");

  const brandable = (j.branded && j.branded.branded_terms !== null
                     && j.branded.branded_terms !== undefined);
  h += '<span class="ppc-filterlabel" style="margin-left:20px;margin-right:4px">'
    + 'BRAND</span>'
    + (brandable
        ? ["All", "Branded", "Non-Branded"]
            .map(function(v){ return pill("brand", v); }).join("")
        : '<span style="font-size:11.5px;color:var(--ppc-muted)">no brand '
          + 'words set, so terms cannot be split</span>')
    + '</div>';

  // The brand word box. Adding one is what turns the split on, so it sits on
  // the screen that shows the split rather than buried in settings.
  h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">'
    + '<span style="color:var(--ppc-dim)">🏷</span>'
    + '<input class="ppc-input" id="ppct_brand" style="flex:1;max-width:400px" '
    +   'placeholder="Add a brand word to enable the branded split…" '
    +   'onkeydown="if(event.key===\'Enter\')ppctAddBrand()">'
    + '<button class="ppc-btn" onclick="ppctAddBrand()">Add</button>'
    + '</div>';

  // SPEND range, ACOS slider, zero-conversions checkbox
  h += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;'
    + 'flex-wrap:wrap">'
    + '<span class="ppc-filterlabel">SPEND</span>'
    + '<input class="ppc-input" style="width:65px;padding:5px 8px;font-size:12px" '
    +   'placeholder="Min" value="' + _pEsc(PPCT.minSpend) + '" '
    +   'oninput="ppctSet(\'minSpend\', this.value)">'
    + '<span style="color:var(--ppc-dim)">–</span>'
    + '<input class="ppc-input" style="width:65px;padding:5px 8px;font-size:12px" '
    +   'placeholder="Max" value="' + _pEsc(PPCT.maxSpend) + '" '
    +   'oninput="ppctSet(\'maxSpend\', this.value)">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-left:16px">'
    +   '<span class="ppc-filterlabel">ACOS</span>'
    +   '<div class="ppc-slider">'
    +     '<div class="track"></div>'
    +     '<div class="fill" style="width:' + (Number(PPCT.maxAcos) / 2) + '%"></div>'
    +     '<input type="range" min="0" max="200" step="5" value="'
    +       PPCT.maxAcos + '" oninput="ppctSet(\'maxAcos\', this.value)">'
    +   '</div>'
    +   '<span style="font-size:11px;color:var(--ppc-muted);white-space:nowrap">'
    +     'ACoS: 0% – ' + (Number(PPCT.maxAcos) >= 200 ? "200%+"
                           : (PPCT.maxAcos + "%")) + '</span>'
    + '</div>'
    + '<label style="display:flex;align-items:center;gap:4px;font-size:12px;'
    +   'color:var(--ppc-muted);cursor:pointer;margin-left:16px">'
    +   '<input type="checkbox"' + (PPCT.zeroOnly ? " checked" : "")
    +   ' onchange="ppctToggleZero()" style="accent-color:var(--ppc-cyan)"> '
    +   'Zero conversions only</label>'
    + '</div>';

  // ---- the ten summary cells, over the FILTERED rows -------------------
  h += ppctSummary(rows, cur, ch);
  h += '<div style="font-size:12px;color:var(--ppc-muted);margin-bottom:14px">'
    + 'Showing ' + rows.length + ' of ' + (j.terms || []).length
    + ' terms</div>';

  h += ppctTable(rows, cur);
  host.innerHTML = h + '</div></div>';
  PPCT.loading = false;
  ppcBusy("ppct_body", false);
  ppcArm("ppct_body");
}

/* The summary bar. Its figures are the FILTERED rows -- the mockup calls them
 * "the filtered totals", which is the whole reason they sit under the filter
 * bar rather than above it.
 *
 * The change figures beside them belong to the WINDOW and cannot follow a
 * filter, so they are shown only on the unfiltered view. A "+8.0%" that does
 * not move when the filter does is worse than no percentage at all. */
function ppctSummary(rows, cur, ch){
  let spend = 0, sales = 0, clicks = 0, impr = 0, orders = 0;
  let profit = 0, profitKnown = true, n = 0;
  rows.forEach(function(r){
    spend += r.spend || 0; sales += r.sales || 0;
    clicks += r.clicks || 0; impr += r.impressions || 0;
    orders += r.orders || 0;
    if(r.profit === null || r.profit === undefined) profitKnown = false;
    else profit += r.profit;
    n++;
  });
  const rate = function(a, b, nd){
    return b ? (100 * a / b).toFixed(nd === undefined ? 1 : nd) + "%" : null;
  };
  const filtered = !!(PPCT.q || PPCT.match !== "All" || PPCT.brand !== "All"
                      || PPCT.zeroOnly || PPCT.minSpend || PPCT.maxSpend
                      || Number(PPCT.maxAcos) < 200);
  const cell = function(label, value, chg, help){
    return '<div class="ppc-sumcell">'
      + '<div class="k">' + label
      +   '<span class="ppc-q" title="' + _pEsc(help || "") + '">?</span></div>'
      + '<span class="v">' + (value === null || value === undefined
                              ? ppcDash("Nothing to work this out from.")
                              : value) + '</span>'
      + ((filtered || chg === null || chg === undefined) ? ""
         : ('<span class="c" style="color:' + (chg >= 0 ? "var(--ppc-green)"
             : "var(--ppc-red)") + '">' + (chg >= 0 ? "+" : "")
            + Number(chg).toFixed(1) + '%</span>'))
      + '</div>';
  };
  return '<div class="ppc-sumgrid">'
    + cell("TOTAL SPEND", ppcMoney0(spend, cur), ch.spend)
    + cell("TOTAL SALES", ppcMoney0(sales, cur), ch.sales)
    + cell("AVG ACOS", rate(spend, sales), ch.acos_pct,
           "Spend over sales, across the rows shown.")
    + cell("AVG CPC", clicks ? ppcMoney(spend / clicks, cur) : null, ch.cpc)
    + cell("TOTAL CLICKS", ppcNum(clicks), ch.clicks)
    + '</div><div class="ppc-sumgrid last">'
    + cell("TOTAL IMPRESSIONS", ppcNum(impr), ch.impressions)
    + cell("AVG CTR", rate(clicks, impr, 2), ch.ctr_pct)
    + cell("AVG CVR", rate(orders, clicks, 2), ch.cvr_pct)
    + cell("TOTAL PURCHASES", ppcNum(orders), ch.orders)
    + cell("TOTAL PROFIT",
           ((profitKnown && n) ? ppcMoney0(profit, cur) : null), null,
           "Estimated from this account's measured fee and stock cost. Blank "
           + "when any row shown could not be costed.")
    + '</div>';
}

/* Match type, exactly as the mockup colours it: transparent tints for the three
 * real match types, plain dim text for the long targeting names, and a small PT
 * pill when the term is an ASIN rather than something anybody typed. */
function ppctMatchBadge(m, isPt){
  const s = String(m || "").toUpperCase();
  const pt = isPt ? '<span class="ppc-badge pt">PT</span>' : "";
  if(s.indexOf("TARGETING_EXPRESSION") === 0){
    // No badge: it is a placement, not a match type anybody chose, and the name
    // is long enough that a filled pill would dominate the row.
    return '<span class="ppc-badge plain">' + _pEsc(s) + '</span>' + pt;
  }
  const cls = (s === "BROAD") ? "broad" : (s === "PHRASE") ? "phrase"
            : (s === "EXACT") ? "exact" : "plain";
  return '<span class="ppc-badge ' + cls + '">' + _pEsc(s) + '</span>' + pt;
}

function ppctTable(rows, cur){
  if(!rows.length){
    return '<div style="color:var(--ppc-muted);padding:8px 0">'
      + 'No terms match those filters.</div>';
  }
  let h = '<div style="overflow-x:auto"><table class="ppc-table terms" '
    + 'style="min-width:1150px"><thead><tr>'
    + ppcTh("Opp", "opportunity", PPCT, "ppctSort", "left",
            "How much there is to gain by acting on this term.")
    + '<th style="width:20px"></th>'
    + ppcTh("Search Term", "search_term", PPCT, "ppctSort", "left",
            "What the shopper actually typed. An ASIN here is a "
            + "product-targeting placement, not something anybody typed.")
    + ppcTh("Match Type", "match_type", PPCT, "ppctSort", "left")
    + ppcTh("Profit", "profit", PPCT, "ppctSort", "right",
            "Estimated from this account's measured fee and stock cost.")
    + ppcTh("Clicks", "clicks", PPCT, "ppctSort", "right")
    + ppcTh("CTR", "ctr_pct", PPCT, "ppctSort", "right")
    + ppcTh("CPC", "cpc", PPCT, "ppctSort", "right")
    + ppcTh("CPA", "cpa", PPCT, "ppctSort", "right",
            "What each order from this term cost in advertising.")
    + ppcTh("Spend", "spend", PPCT, "ppctSort", "right")
    + ppcTh("Sales", "sales", PPCT, "ppctSort", "right")
    + ppcTh("ACoS", "acos_pct", PPCT, "ppctSort", "right")
    + ppcTh("RoAS", "roas", PPCT, "ppctSort", "right")
    + '</tr></thead><tbody>';

  rows.slice(0, 400).forEach(function(r, i){
    const open = (PPCT.open === i);
    h += '<tr class="' + (open ? "open" : "") + '" style="cursor:pointer" '
      + 'onclick="ppctToggleRow(' + i + ')">'
      + '<td>' + ppcOpp(r.opportunity) + '</td>'
      + '<td style="text-align:center;color:var(--ppc-dim);font-size:10px">'
      +   (open ? "▾" : "▸") + '</td>'
      + '<td style="font-size:14px;max-width:280px;overflow-wrap:anywhere">'
      +   _pEsc(r.search_term) + '</td>'
      + '<td style="text-align:left">'
      +   ppctMatchBadge(r.match_type, r.product_target) + '</td>'
      + '<td class="ppc-col-profit-cy">' + ppcProfit(r.profit, cur) + '</td>'
      + '<td>' + ppcNum(r.clicks) + '</td>'
      + '<td>' + ppcPct(r.ctr_pct, "", 1) + '</td>'
      + '<td>' + ppcMoney(r.cpc, cur) + '</td>'
      + '<td>' + ppcMoney(r.cpa, cur,
          "No orders from this term, so there is no cost per order.") + '</td>'
      + '<td style="font-weight:500">' + ppcMoney0(r.spend, cur) + '</td>'
      + '<td>' + ppcMoney0(r.sales, cur) + '</td>'
      + '<td>' + ppcPct(r.acos_pct,
          "No sales from this term, so ACOS is undefined — not 0%.") + '</td>'
      + '<td>' + ppcX(r.roas) + '</td>'
      + '</tr>';
    if(open){
      h += '<tr class="ppc-termexp"><td colspan="13">'
        + '<span style="color:var(--ppc-dim)">Campaign: </span>'
        + '<span style="color:var(--ppc-muted)">'
        +   _pEsc(r.campaign || "—") + '</span>'
        + '<span style="color:var(--ppc-dim);margin-left:28px">Keyword: </span>'
        + '<span style="color:var(--ppc-text);font-weight:600">'
        +   _pEsc(r.keyword || r.search_term) + '</span>'
        + '</td></tr>';
    }
  });
  h += '</tbody></table></div>';
  if(rows.length > 400){
    h += '<div style="font-size:12px;color:var(--ppc-muted);margin-top:9px">'
      + 'Drawing the first 400 of ' + rows.length
      + '. Export gives you all of them.</div>';
  }
  return h;
}

/* Adding a brand word is what turns the branded split on, so it lives on the
 * screen that shows the split. Posts to /ppc/brand_terms, which the older PPC
 * screen already owns -- one brand list, not two (Rule 12). */
async function ppctAddBrand(){
  const el = document.getElementById("ppct_brand");
  const v = ((el && el.value) || "").trim();
  if(!v) return;
  try{
    const j = await (await fetch("/ppc/brand_terms?" + ppcQS(), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({add: v})})).json();
    if(!j || !j.ok){
      if(typeof toast === "function")
        toast("Could not add that: " + ((j && j.error) || "unknown"));
      return;
    }
    if(typeof toast === "function") toast('Brand word "' + v + '" added.');
    ppctLoad();
  }catch(e){
    if(typeof toast === "function") toast("Could not add that brand word.");
  }
}
