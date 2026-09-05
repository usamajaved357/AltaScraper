/* static/js/ppcterms.js -- the Search Terms screen.
 *
 * One row per thing somebody actually typed into Amazon, with what it cost and
 * what it returned.
 *
 * THE TABLE AND THE CARDS ANSWER FOR DIFFERENT WINDOWS, AND IT SAYS SO.
 * The KPI cards come from the daily tables and move with the date buttons. The
 * table comes from the stored Search Term Report, which covers ONE fixed window
 * chosen when it was pulled. Those are not the same period and cannot be made
 * to be -- so rather than quietly letting somebody compare them, the page
 * prints the report's own dates above the table. A screen where half the
 * numbers move and half do not, with nothing to say why, is the kind of thing
 * that gets noticed once and distrusted afterwards.
 *
 * NOTHING HERE WRITES (CLAUDE.md Rule 8).
 */

const PPCT = {data: null, loading: false, sort: "spend", desc: true, q: "",
              match: "all", brand: "all", zeroOnly: false,
              minSpend: "", maxAcos: ""};

async function ppctLoad(){
  const host = document.getElementById("ppct_body");
  if(!host || PPCT.loading) return;
  PPCT.loading = true;
  host.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Reading the search terms…</div>';
  try{
    const qs = ppcQS(PPCWIN.start
      ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
    const j = await (await fetch("/ppc/analytics/terms?" + qs)).json();
    PPCT.loading = false;
    if(!j || !j.ok){
      host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _pEsc((j && j.error) || "Could not read the search terms.") + '</div>';
      return;
    }
    PPCT.data = j;
    ppctRender();
  }catch(e){
    PPCT.loading = false;
    host.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + 'Could not read the search terms.</div>';
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
function ppctExport(){
  const qs = ppcQS(PPCWIN.start
    ? {start: PPCWIN.start, end: PPCWIN.end} : {days: PPCWIN.days});
  window.location = "/ppc/analytics/terms.csv?" + qs;
}

/* Which rows survive the filter bar. Kept apart from drawing so the count under
 * the table ("showing X of Y") is the same arithmetic the table used, rather
 * than a second opinion about it. */
function ppctRows(){
  const j = PPCT.data;
  let rows = (j && j.terms) || [];
  if(PPCT.q){
    rows = rows.filter(function(r){
      return (String(r.search_term || "") + " " + String(r.campaign || ""))
        .toLowerCase().indexOf(PPCT.q) >= 0;
    });
  }
  if(PPCT.match !== "all"){
    rows = rows.filter(function(r){
      const m = String(r.match_type || "").toUpperCase();
      if(PPCT.match === "PT") return m.indexOf("TARGETING_EXPRESSION") === 0;
      return m === PPCT.match;
    });
  }
  if(PPCT.brand !== "all"){
    // `branded` is TRUE, FALSE or NULL, and null means "no brand terms are set
    // up" rather than "not branded" -- see domain/ppc_view.is_branded. A row
    // whose branding is unknown must not answer either filter, because both
    // answers would be a claim.
    rows = rows.filter(function(r){
      return PPCT.brand === "branded" ? r.branded === true : r.branded === false;
    });
  }
  if(PPCT.zeroOnly){
    rows = rows.filter(function(r){ return !r.orders && r.clicks; });
  }
  const min = parseFloat(PPCT.minSpend);
  if(!isNaN(min)) rows = rows.filter(function(r){ return (r.spend || 0) >= min; });
  const ma = parseFloat(PPCT.maxAcos);
  if(!isNaN(ma)){
    rows = rows.filter(function(r){
      // A term with no sales has an UNDEFINED ACOS, not an infinite one. It is
      // kept when filtering by a ceiling, because hiding the terms that sold
      // nothing is the opposite of what somebody filtering on ACOS wants.
      return r.acos_pct === null || r.acos_pct === undefined || r.acos_pct <= ma;
    });
  }
  return ppcSortRows(rows, PPCT.sort, PPCT.desc);
}

function ppctRender(){
  const host = document.getElementById("ppct_body");
  const j = PPCT.data;
  if(!host || !j) return;
  const cur = "GBP";
  const t = j.totals || {}, ch = j.change || {}, av = j.availability || {};

  let h = ppcWindowBar("ppctLoad");

  if(!(j.terms || []).length){
    host.innerHTML = h + ppcUnavailable(
      "No search terms stored",
      (av.search_terms && av.search_terms.why)
        || "No Search Term Report is stored for this account.");
    return;
  }

  h += ppcProductNote(av);
  h += ppcRatesNote(j.rates);

  h += ppcCards([
    ppcCard({label: "Spend", value: ppcMoney(t.spend, cur),
             change: ppcChange(ch.spend, "down")}),
    ppcCard({label: "Sales", value: ppcMoney(t.sales, cur),
             change: ppcChange(ch.sales, "up")}),
    ppcCard({label: "ACOS", value: ppcPct(t.acos_pct),
             change: ppcChange(ch.acos_pct, "down")}),
    ppcCard({label: "Wasted spend",
             value: ppcMoney((j.wasted || {}).spend, cur, (j.wasted || {}).why),
             note: ((j.wasted || {}).terms
                    ? j.wasted.terms + " terms clicked, none ordered" : ""),
             help: "Spend on search terms that took a click and produced no "
                 + "order."}),
  ]);
  h += ppcCards([
    ppcCard({label: "ROAS", value: ppcX(t.roas), change: ppcChange(ch.roas, "up")}),
    ppcCard({label: "CTR", value: ppcPct(t.ctr_pct, "", 2),
             change: ppcChange(ch.ctr_pct, "up")}),
    ppcCard({label: "CVR", value: ppcPct(t.cvr_pct, "", 2),
             change: ppcChange(ch.cvr_pct, "up")}),
    ppcCard({label: "Avg CPC", value: ppcMoney(t.cpc, cur),
             change: ppcChange(ch.cpc, "down")}),
  ]);

  // Branded against the rest -- or an honest refusal when no brand words exist.
  h += ppctBranded(j, cur);
  h += ppctMatchTypes(j, cur);

  // ---- the table ------------------------------------------------------
  const rows = ppctRows();
  h += '<div class="panelcard" style="padding:0;border-radius:8px;overflow:hidden">'
    + '<div style="padding:12px 14px">'
    + '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
    + '<b style="font-size:13px">Search terms</b>'
    + '<input placeholder="Filter search terms…" oninput="ppctFilter(this.value)" '
    +   'style="font-size:12px;padding:5px 9px;min-width:190px;margin-left:auto">'
    + '</div>';

  if(j.report_note){
    h += '<div class="cc" style="font-size:11.5px;margin-top:8px;line-height:1.55">'
      + '<i class="ti ti-info-circle"></i> ' + _pEsc(j.report_note) + '</div>';
  }

  // Filters. Match type first because it is the one that changes the answer
  // most: an exact-match term and a product-targeting placement are different
  // kinds of thing and averaging them together hides both.
  const pill = function(field, val, label){
    return '<button class="db-chip' + (PPCT[field] === val ? " on" : "") + '" '
      + 'onclick="ppctSet(' + jsArg(field) + ',' + jsArg(val)
      + ')">' + _pEsc(label) + '</button>';
  };
  h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
    + 'margin-top:9px">'
    + '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +   'letter-spacing:.7px">Match type</span>'
    + pill("match", "all", "All") + pill("match", "EXACT", "Exact")
    + pill("match", "PHRASE", "Phrase") + pill("match", "BROAD", "Broad")
    + pill("match", "PT", "Product targeting")
    + '</div>';

  const brandable = (j.branded && j.branded.branded_terms !== null);
  h += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
    + 'margin-top:6px">'
    + '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +   'letter-spacing:.7px">Brand</span>'
    + (brandable
        ? (pill("brand", "all", "All") + pill("brand", "branded", "Branded")
           + pill("brand", "non_branded", "Non-branded"))
        : '<span class="cc" style="font-size:11.5px">No brand words are set for '
          + 'this account, so terms cannot be split into branded and not. Add '
          + 'them on the PPC screen.</span>')
    + '</div>';

  h += '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;'
    + 'margin-top:6px">'
    + '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +   'letter-spacing:.7px">Min spend</span>'
    + '<input value="' + _pEsc(PPCT.minSpend) + '" placeholder="0" '
    +   'oninput="ppctSet(\'minSpend\', this.value)" '
    +   'style="font-size:12px;padding:4px 7px;width:70px">'
    + '<span class="cc" style="font-size:10.5px;text-transform:uppercase;'
    +   'letter-spacing:.7px">Max ACOS %</span>'
    + '<input value="' + _pEsc(PPCT.maxAcos) + '" placeholder="any" '
    +   'oninput="ppctSet(\'maxAcos\', this.value)" '
    +   'style="font-size:12px;padding:4px 7px;width:70px">'
    + '<label class="cc" style="font-size:11.5px;display:flex;gap:5px;'
    +   'align-items:center;cursor:pointer">'
    + '<input type="checkbox"' + (PPCT.zeroOnly ? " checked" : "")
    +   ' onchange="ppctToggleZero()"> clicked but never ordered</label>'
    + '</div></div>';

  h += ppctTable(rows, cur);
  h += '<div class="cc" style="padding:9px 14px;font-size:11.5px">Showing '
    + rows.length + ' of ' + (j.terms || []).length + ' terms.</div>';
  h += '</div>';

  host.innerHTML = h;
}

/* Match type colours, as the spec asks: transparent tints rather than solid
 * fills, so a long product-targeting name stays readable as plain text. */
function ppctMatchBadge(m){
  const s = String(m || "").toUpperCase();
  const tone = {BROAD: ["rgba(210,153,34,0.18)", "#d29922"],
                PHRASE: ["rgba(63,185,80,0.18)", "#3fb950"],
                EXACT: ["rgba(57,210,192,0.18)", "#39d2c0"]};
  if(tone[s]){
    return '<span style="background:' + tone[s][0] + ';color:' + tone[s][1]
      + ';font-size:10.5px;font-weight:700;padding:2px 10px;border-radius:4px">'
      + s + '</span>';
  }
  // TARGETING_EXPRESSION* is long and is not a match type anybody chose -- it
  // is a placement. Plain dim text, not a badge, so it does not shout.
  return '<span class="cc" style="font-size:10.5px">' + _pEsc(s) + '</span>';
}

function ppctTable(rows, cur){
  if(!rows.length){
    return '<div class="cc" style="padding:16px">No terms match those filters.</div>';
  }
  let h = '<div style="overflow-x:auto"><table class="kv ordtable" '
    + 'style="width:100%;min-width:1080px"><thead><tr>'
    + ppcTh("Opp", "opportunity", PPCT, "ppctSort", "left",
            "How much there is to gain by acting on this term.")
    + ppcTh("Search term", "search_term", PPCT, "ppctSort", "left",
            "What the shopper actually typed. An ASIN here is a product-"
            + "targeting placement, not something anybody typed.")
    + ppcTh("Match type", "match_type", PPCT, "ppctSort", "left")
    + ppcTh("Profit", "profit", PPCT, "ppctSort", "right",
            "Estimated from this account's measured fee and stock cost.")
    + ppcTh("Clicks", "clicks", PPCT, "ppctSort", "right")
    + ppcTh("CTR", "ctr_pct", PPCT, "ppctSort", "right")
    + ppcTh("CPC", "cpc", PPCT, "ppctSort", "right")
    + ppcTh("CPA", "cpa", PPCT, "ppctSort", "right")
    + ppcTh("Spend", "spend", PPCT, "ppctSort", "right")
    + ppcTh("Sales", "sales", PPCT, "ppctSort", "right")
    + ppcTh("ACOS", "acos_pct", PPCT, "ppctSort", "right")
    + ppcTh("ROAS", "roas", PPCT, "ppctSort", "right")
    + '</tr></thead><tbody>';
  rows.slice(0, 400).forEach(function(r){
    h += '<tr title="' + _pEsc("Campaign: " + (r.campaign || "—")
                               + "   Keyword: " + (r.keyword || "—")) + '">'
      + '<td>' + ppcOpp(r.opportunity) + '</td>'
      + '<td style="font-size:12px;max-width:280px;overflow-wrap:anywhere">'
      +   _pEsc(r.search_term)
      +   (r.product_target ? ' <span style="background:rgba(57,210,192,0.2);'
            + 'color:var(--accent);font-size:9px;font-weight:700;padding:1px 5px;'
            + 'border-radius:3px" title="Product targeting: this is an ASIN, '
            + 'not a typed search">PT</span>' : '')
      +   '<div class="cc" style="font-size:10px;overflow:hidden;'
      +     'text-overflow:ellipsis;white-space:nowrap">'
      +     _pEsc(r.campaign || "") + '</div>'
      + '</td>'
      + '<td>' + ppctMatchBadge(r.match_type) + '</td>'
      + '<td style="text-align:right">' + ppcProfit(r.profit, cur) + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.clicks) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.ctr_pct, "", 2) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.cpc, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.cpa, cur,
          "No orders from this term, so there is no cost per order.") + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.spend, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.sales, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.acos_pct,
          "No sales from this term, so ACOS is undefined — not 0%.") + '</td>'
      + '<td style="text-align:right">' + ppcX(r.roas) + '</td>'
      + '</tr>';
  });
  h += '</tbody></table></div>';
  if(rows.length > 400){
    h += '<div class="cc" style="padding:9px 14px;font-size:11.5px">Drawing the '
      + 'first 400 of ' + rows.length + '. Export gives you all of them.</div>';
  }
  return h;
}

/* Paying to appear on your own name, against everything else.
 *
 * The most useful cut on the page, and the one most easily faked: with no brand
 * words set up, ppc_view.is_branded answers NULL rather than "not branded", and
 * this refuses to draw a confident 0% branded rather than turning that null
 * into a measurement. */
function ppctBranded(j, cur){
  const b = j.branded || {};
  if(b.why){
    return '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
      + 'margin:0 0 10px"><div style="font-weight:600;margin-bottom:4px">'
      + 'Branded vs non-branded</div>'
      + '<div class="cc" style="font-size:12px;line-height:1.6">'
      + '<i class="ti ti-info-circle"></i> ' + _pEsc(b.why) + '</div></div>';
  }
  if(!b.branded && !b.non_branded) return "";
  const row = function(label, x, colour){
    if(!x) return "";
    return '<tr><td style="color:' + colour + ';font-weight:600">' + label + '</td>'
      + '<td style="text-align:right">' + ppcMoney(x.spend, cur) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(x.sales, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(x.acos_pct) + '</td>'
      + '<td style="text-align:right">' + ppcX(x.roas) + '</td>'
      + '<td style="text-align:right">' + ppcPct(x.cvr_pct, "", 2) + '</td>'
      + '<td style="text-align:right">' + ppcPct(x.spend_share_pct) + '</td></tr>';
  };
  return '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:2px">Branded vs non-branded</div>'
    + '<div class="cc" style="font-size:11.5px;margin-bottom:9px">'
    + 'Paying to appear on your own name is defensive. Mixed in with the rest it '
    + 'makes a healthy-looking ACOS out of money that never won a new customer. '
    + _pEsc((b.branded_terms || 0) + " branded terms, "
            + (b.non_branded_terms || 0) + " not")
    + (b.unclassified_terms ? _pEsc(", " + b.unclassified_terms + " unknown") : "")
    + '.</div>'
    + '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
    + '<thead><tr><th></th><th style="text-align:right">Spend</th>'
    + '<th style="text-align:right">Sales</th><th style="text-align:right">ACOS</th>'
    + '<th style="text-align:right">ROAS</th><th style="text-align:right">CVR</th>'
    + '<th style="text-align:right">% of spend</th></tr></thead><tbody>'
    + row("Branded", b.branded, "#58a6ff")
    + row("Non-branded", b.non_branded, "#d29922")
    + '</tbody></table></div></div>';
}

function ppctMatchTypes(j, cur){
  const rows = j.by_match_type || [];
  if(!rows.length) return "";
  let h = '<div class="panelcard" style="padding:14px 16px;border-radius:8px;'
    + 'margin:0 0 10px">'
    + '<div style="font-weight:600;margin-bottom:9px">By match type</div>'
    + '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
    + '<thead><tr><th>Type</th><th style="text-align:right">Terms</th>'
    + '<th style="text-align:right">Spend</th><th style="text-align:right">% spend</th>'
    + '<th style="text-align:right">Sales</th><th style="text-align:right">ACOS</th>'
    + '<th style="text-align:right">CPC</th><th style="text-align:right">CVR</th>'
    + '<th style="text-align:right">Profit</th></tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr><td>' + ppctMatchBadge(r.key) + '</td>'
      + '<td style="text-align:right">' + ppcNum(r.n) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.spend, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.spend_share_pct) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.sales, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.acos_pct) + '</td>'
      + '<td style="text-align:right">' + ppcMoney(r.cpc, cur) + '</td>'
      + '<td style="text-align:right">' + ppcPct(r.cvr_pct, "", 2) + '</td>'
      + '<td style="text-align:right">' + ppcProfit(r.profit, cur) + '</td></tr>';
  });
  return h + '</tbody></table></div></div>';
}
