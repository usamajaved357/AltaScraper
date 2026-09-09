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
              maxAcos: 200, highlight: null,
              // The plotted dots, kept so the map's hover can find the campaign
              // under the pointer without re-deriving the geometry.
              dots: [], mapCur: "GBP"};

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
 * it does on PPC Analytics and on the Sales page. Through the shared resolver,
 * because salescharts hands back column INDICES rather than dates -- see
 * ppcZoomTo, and the "Invalid isoformat string: '23'" it fixes. */
function ppccZoomTo(from, to, cid){
  ppcZoomTo(from, to, cid, "ppccLoad");
}

function ppccSort(k){
  if(PPCC.sort === k) PPCC.desc = !PPCC.desc;
  else { PPCC.sort = k; PPCC.desc = true; }
  ppccRender();
}
function ppccSet(f, v){ PPCC[f] = v; ppccRender(); }
/* THE SEARCH BOX. Three separate faults, measured on the running screen with
 * this account's 254 campaigns:
 *
 *     "THE SEARCH CAMPAIGNS BAR IS NOT WORKING"
 *
 *   only the first letter ever landed -- this calls ppccRender(), which rebuilds
 *     the whole of #ppcc_body. The input it drew carried no value= and was a NEW
 *     element, so what you had typed was gone and the FOCUS went with it. Typing
 *     "auto" left PPCC.q === "a" and the box empty: the u, t and o were sent to
 *     the page, not to a box.
 *   "  auto  " found 0 of 254 -- lowercased, never trimmed, so the spaces were
 *     part of what it looked for. Trailing spaces arrive by pasting, which is
 *     when you are least likely to suspect the search box.
 *   "auto ceiling" found nothing -- a bare indexOf on the whole name, and these
 *     names are underscore-joined segments (SP_AUTO_CeilingFan_DISC), so two
 *     words can never be a single run of characters in one.
 *
 * The RAW text is kept now, not the lowercased copy: it is what goes back into
 * the box, and altaSearchMatch lowercases both sides itself.
 */
function ppccFilter(v){
  PPCC.q = (v == null ? "" : String(v));
  // Remembered BEFORE the redraw destroys the element, and read back by
  // ppccKeepFocus after it. `_focus` is what stops a filter pill or a column
  // sort -- which also re-render -- from pulling the cursor into this box.
  const el = document.getElementById("ppcc_q");
  PPCC._focus = !!el && document.activeElement === el;
  PPCC._caret = el ? el.selectionStart : null;
  ppccRender();
}

/* Does one campaign match what is typed? Through the shared matcher in
 * static/js/textsearch.js, which is also what the listings search uses -- so
 * "every word somewhere, in any order" means the same thing on both screens
 * and cannot drift (CLAUDE.md Rule 12).
 *
 * The FIELDS are this screen's business and stay here. Name first because it is
 * what people search by; the type and state are included so "paused" or "SP"
 * narrows the list the way the pills do, without having to reach for them. */
function ppccMatch(r){
  if(typeof altaSearchMatch !== "function"){
    // textsearch.js not loaded: fall back to what this did before rather than
    // filtering everything out and showing an empty screen.
    const q = String(PPCC.q || "").trim().toLowerCase();
    return !q || String(r.name || "").toLowerCase().indexOf(q) >= 0;
  }
  return altaSearchMatch(PPCC.q, [r.name, r.campaignType, r.type, r.state,
                                  r.status, r.targetingType]);
}
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
  if(String(PPCC.q || "").trim()){
    rows = rows.filter(ppccMatch);
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
    // A PICKER, NOT A LABEL. This printed the window as read-only text beside
    // the day buttons, so the only reachable windows were 7, 14, 30 and 90 --
    // the same complaint as PPC Analytics, and all three pages share PPCWIN, so
    // a date set on any one of them holds when you move between them.
    +   ppcDateRange(j, "ppccLoad")
    + '</div></div>';

  if(!(j.campaigns || []).length){
    h += ppcNoData(av, "The campaign table, the profitability map and the "
                     + "cohorts all read the same rows, so none is drawn.");
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
  ppccKeepFocus();
  PPCC.loading = false;
  ppcBusy("ppcc_body", false);
  ppcArm("ppcc_body");
}

/* PUT THE CURSOR BACK IN THE SEARCH BOX.
 *
 * This is the half of "the search bar is not working" that value= alone does
 * not fix. Every keystroke calls ppccRender(), which replaces the whole of
 * #ppcc_body -- so the element being typed into stops existing. The browser has
 * nothing to return focus to, and the next letter goes to the page instead of
 * the box. Measured: typing "auto" left PPCC.q === "a".
 *
 * So the box is refocused after the redraw, with the caret where it was rather
 * than at the start -- a caret that jumps to position 0 makes a search box type
 * backwards, which is a worse bug than the one being fixed.
 *
 * Only when it was ALREADY focused: pressing a filter pill or sorting a column
 * also re-renders, and stealing the cursor into the search box then would be
 * its own small madness. */
function ppccKeepFocus(){
  const el = document.getElementById("ppcc_q");
  if(!el || !PPCC._focus) return;
  try{
    el.focus();
    const n = (PPCC._caret == null) ? el.value.length : PPCC._caret;
    el.setSelectionRange(n, n);
  }catch(e){}                 // a browser that refuses is not worth failing over
}

/* ---- 1. the breakdown panel --------------------------------------------- */
/* WHAT THE RING SHOULD DIVIDE.
 *
 *     "the circular graph should show up movement with a particular number of
 *      stats"
 *
 * The mockup's ring splits spend between Sponsored Products and Sponsored
 * Brands, and shows two segments because that account runs both. This one runs
 * only Sponsored Products -- measured: by_ad_product has exactly one entry --
 * so the same ring is one complete circle of one colour, which tells nobody
 * anything and looks broken.
 *
 * Inventing a second product would be a lie. But the panel is called "Campaign
 * & Match Type Breakdown", and the match types ARE a real division of the same
 * spend, from Amazon, with five live categories on this account. So when there
 * is only one ad product the ring divides by match type instead, and the caption
 * underneath says which of the two it is dividing.
 *
 * Neither is a default: the ring always divides something real and always names
 * it.
 */
function _ppccRing(prods, matches, NICE, PCOL, MCOL){
  const useProducts = (prods || []).filter(function(p){
    return (p.spend || 0) > 0; }).length > 1;
  if(useProducts){
    return {
      caption: "Total spend, split by ad product",
      segments: prods.map(function(p){
        const k = String(p.key).toUpperCase();
        return {label: NICE[k] || p.key, value: p.spend || 0,
                colour: PCOL[k] || "var(--ppc-muted)"};
      }),
    };
  }
  const live = (matches || []).filter(function(m){ return (m.spend || 0) > 0; });
  if(live.length > 1){
    return {
      caption: "Total spend, split by match type — this account runs only one "
               + "ad product, so the product split would be one whole circle",
      segments: live.map(function(m){
        const k = String(m.key).toUpperCase();
        // THE SERVER'S LABEL, when it sends one. The match types now come from
        // the targeting report, which carries Amazon's literal enum -- so the
        // auto slice arrives as TARGETING_EXPRESSION_PREDEFINED and read
        // "TARGETING EXPRESSION PREDEFINED" on the chart key. The server knows
        // it means "Auto"; underscores-to-spaces stays as the fallback for a
        // value it has no name for, so a new Amazon enum still shows up as
        // itself rather than vanishing into an Other slice.
        return {label: m.label || String(m.key).replace(/_/g, " "),
                value: m.spend || 0,
                colour: MCOL[k] || "var(--ppc-muted)"};
      }),
    };
  }
  return {
    caption: "Total spend",
    segments: (prods || []).map(function(p){
      const k = String(p.key).toUpperCase();
      return {label: NICE[k] || p.key, value: p.spend || 0,
              colour: PCOL[k] || "var(--ppc-muted)"};
    }),
  };
}

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
  // EVERY COLUMN SAYS HOW IT WAS WORKED OUT.
  //
  //     "in the tables there i see the circular i marks that should display the
  //      logic when the user hower over it"
  //
  // The ⓘ was on some headings and not others, and where it was present it
  // named the metric rather than the arithmetic. A column called PROFIT on an
  // advertising screen is the one people most need the method for: Amazon
  // attributes SALES to a campaign and attributes neither the fee nor the stock
  // cost, so the profit here is this account's own measured rates applied to
  // those sales. Saying that on hover is the difference between a number
  // somebody can act on and one they have to trust.
  const HEADS = [
    ["TYPE", "The match type Amazon reported for the search term, or the ad "
             + "product for the campaign rows below."],
    ["CLICKS", "Clicks Amazon attributed to this group in the window."],
    ["CTR", "Clicks ÷ impressions. Recomputed over the whole group, not "
            + "averaged across its rows — averaging lets one quiet row weigh as "
            + "much as a busy one."],
    ["CPC", "Spend ÷ clicks. Blank when there were no clicks, which is not a "
            + "cost per click of nothing."],
    ["CPA", "Spend ÷ ad orders — what one order cost to buy. Blank when there "
            + "were no orders."],
    ["SPEND", "What Amazon charged for these ads. Its figure, not an estimate."],
    ["% SPEND", "This group's share of the window's total ad spend."],
    ["SALES", "Sales Amazon ATTRIBUTED to these ads within its own attribution "
              + "window. Not the same as total sales, and not everything these "
              + "ads influenced."],
    ["ACOS", "Spend ÷ attributed ad sales. Blank when the ads made no "
             + "attributed sales — that is not an ACOS of nought, it is spend "
             + "that bought none."],
    ["PROFIT", "ESTIMATED. Amazon attributes sales to a campaign but not the "
               + "referral fee or the stock cost, so this is attributed sales "
               + "minus spend, minus this account's own MEASURED fee rate and "
               + "cost rate applied to those sales. Blank when either rate "
               + "could not be measured — a profit built on a guessed margin is "
               + "how a working campaign gets switched off."],
    ["% PROFIT", "This group's share of the window's total estimated profit."],
  ];

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
        return '<th class="' + TINTS[i] + '">' + _pEsc(x[0])
          + '<span class="ppc-i" title="' + _pEsc(x[1]) + '">ⓘ</span></th>';
      }).join("")
    + '</tr></thead><tbody>';

  if(matches.length){
    table += '<tr class="sect"><td colspan="11">Match types</td></tr>';
    matches.forEach(function(m){
      // The server's readable name, falling back to Amazon's own string. See
      // the note in _ppccRing: an enum this app has no name for is shown as
      // itself rather than swept into an "Other" row, because spend that
      // disappears from a table while staying in the total beside it reads as
      // an arithmetic error in the page.
      table += row(m, MCOL[String(m.key).toUpperCase()] || "var(--ppc-muted)",
                   m.label || m.key);
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
  let lines = (dbp.series || [])
    .filter(function(s){
      return (s.values || []).some(function(v){
        return v !== null && v !== undefined; });
    })
    .map(function(s){
      const k = String(s.key).toUpperCase();
      return {key: KEYMAP[k] || "ad_spend", label: NICE[k] || s.key,
              values: s.values};
    });
  let cols = dbp.dates || [];
  let chartNote = "Spend per day by ad product";

  // ONE BAND IS NOT A BREAKDOWN.
  //
  //     "the line graph should also have more data than there is"
  //
  // With a single ad product this chart is one line, and a chart with one line
  // needs no key and shows no composition.
  //
  // MATCH TYPE IS WHAT THE SPEC ASKS FOR HERE, and it is what the panel is
  // named after: "Stacked Area Chart -- Daily spend by match type over the date
  // range. Layers = match types (Exact, Phrase, Broad, PAT). Same
  // targeting-level data source as donut."
  //
  // It could not be drawn before today. Match type lived only in the search
  // term report, which was stored as one batch per window with no dates -- so
  // there was no per-day figure to layer. The targeting report supplies one,
  // and the donut beside this chart is now drawn from the same rows, so the
  // ring and the layers cannot disagree.
  //
  // Placement stays as the LAST resort, for an account with no targeting report
  // yet. Nothing is invented at any step; each is a real cut of the same spend
  // and the caption says which one is on screen.
  const PKEY = ["ad_spend", "ad_sales", "roas", "clicks"];
  const mtd = j.match_type_daily || {};
  if(lines.length < 2 && (mtd.lines || []).length > 1){
    lines = mtd.lines.map(function(s, i){
      return {key: PKEY[i % PKEY.length], label: s.name || s.key,
              values: s.values};
    });
    cols = mtd.columns || [];
    chartNote = "Spend per day by match type — this account runs one ad "
              + "product, so a split by product would be a single line";
  }

  const pd = j.placement_daily || {};
  if(lines.length < 2 && (pd.series || []).length > 1){
    lines = pd.series.map(function(s, i){
      return {key: PKEY[i % PKEY.length], label: s.label, values: s.values};
    });
    cols = pd.dates || [];
    chartNote = "Spend per day by placement — this account runs one ad product, "
              + "and no targeting report is stored yet, so neither a product "
              + "nor a match-type split can be drawn";
  }

  const chart = (lines.length && typeof salesCombo === "function")
    ? salesCombo({id: "ppcc_spend", onZoom: "ppccZoomTo",
                  columns: cols, bars: null, lines: lines,
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
    +   ppcDonut(_ppccRing(prods, matches, NICE, PCOL, MCOL).segments, 220)
    +   '<div style="font-size:12px;color:var(--ppc-muted)">'
    +   _pEsc(_ppccRing(prods, matches, NICE, PCOL, MCOL).caption) + '</div>'
    +   '<div style="font-size:26px;font-weight:700">'
    +   ppcMoney0(totalSpend, cur) + '</div>'
    + '</div>'
    + '<div>'
    +   (chart
          // The caption stays -- it says WHICH cut of the spend is on screen,
          // which is not an instruction and cannot be guessed from the chart.
          // The gesture advertisement is gone, app-wide, by request.
          ? ('<div class="ppc-charthint">' + _pEsc(chartNote) + '</div>' + chart)
          : '<div style="font-size:12px;color:var(--ppc-muted)">No daily '
            + 'campaign rows in this window.</div>')
    + '</div>'
    + '</div>'
    + table
    // The legend names whatever the RING divided, not always the products --
    // a key that lists two products beside a ring split five ways is worse than
    // no key at all.
    + ppcLegend(_ppccRing(prods, matches, NICE, PCOL, MCOL).segments
        .map(function(sg){
          return [sg.label + " (" + ppcMoney0(sg.value, cur) + ")", sg.colour];
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

  // THE CROSSHAIR, drawn once and moved on hover rather than one per dot.
  //
  //     "the campaign profitablity map displays two lines intersecting over a
  //      point when somebody hower over it and displays specific information"
  //
  // Right, and it did not: every dot carried a native <title>, which is the
  // browser's own yellow box -- it appears after a pause, cannot be styled, and
  // gives no sense of WHERE on the two axes the campaign sits. The point of this
  // chart is the position, so the hover has to show the position.
  const salesMax = Math.max.apply(null,
    rows.map(function(r){ return r.sales || 0; })) || 1;
  svg += '<line id="ppcc_ch_x" x1="0" y1="0" x2="0" y2="0" '
    + 'stroke="var(--ppc-cyan)" stroke-width="1" stroke-dasharray="4 3" '
    + 'opacity="0" pointer-events="none"/>'
    + '<line id="ppcc_ch_y" x1="0" y1="0" x2="0" y2="0" '
    + 'stroke="var(--ppc-cyan)" stroke-width="1" stroke-dasharray="4 3" '
    + 'opacity="0" pointer-events="none"/>';

  PPCC.dots = [];
  rows.forEach(function(r, i){
    const cx = mapX(r.spend), cy = mapY(r.profit);
    const rad = Math.max(4, Math.sqrt((r.sales || 0) / salesMax * 100) * 0.9);
    PPCC.dots.push({x: cx, y: cy, r: r});
    svg += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1)
      + '" r="' + rad.toFixed(1) + '" fill="' + band(r.acos_pct)
      + '" opacity="0.85" style="cursor:pointer" '
      + 'onmouseenter="ppccDot(' + i + ',evt)" onmouseleave="ppccDotOut()" '
      + 'onclick="ppccHighlight(' + jsArg(String(r.campaign_id)) + ')"/>';
  });
  // The plot bounds, so the crosshair can be drawn to the axes.
  svg += '<rect id="ppcc_plot" x="' + X0 + '" y="' + Y0 + '" width="'
    + (X1 - X0) + '" height="' + (Y1 - Y0) + '" fill="none" '
    + 'pointer-events="none" data-x0="' + X0 + '" data-x1="' + X1
    + '" data-y0="' + Y0 + '" data-y1="' + Y1 + '"/>';
  svg += '</svg>';
  PPCC.mapCur = cur;

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
    + '<div class="ppc-map" style="position:relative">' + svg
    +   '<div id="ppcc_tip" class="ppc-maptip" style="display:none"></div>'
    + '</div>'
    + '</div>';
}

/* The hover: move the two rules onto the point, and say what sits there.
 *
 * The figures are the ones the dot is POSITIONED by -- spend across, profit up,
 * with the sales that set its size and the ACOS that set its colour -- so the
 * card explains the picture rather than repeating the table. */
function ppccDot(i, evt){
  const d = (PPCC.dots || [])[i];
  const tip = document.getElementById("ppcc_tip");
  const plot = document.getElementById("ppcc_plot");
  const lx = document.getElementById("ppcc_ch_x");
  const ly = document.getElementById("ppcc_ch_y");
  if(!d || !tip || !plot) return;
  const X0 = +plot.getAttribute("data-x0"), X1 = +plot.getAttribute("data-x1");
  const Y0 = +plot.getAttribute("data-y0"), Y1 = +plot.getAttribute("data-y1");
  if(lx){
    lx.setAttribute("x1", d.x); lx.setAttribute("x2", d.x);
    lx.setAttribute("y1", Y0);  lx.setAttribute("y2", Y1);
    lx.setAttribute("opacity", "1");
  }
  if(ly){
    ly.setAttribute("x1", X0);  ly.setAttribute("x2", X1);
    ly.setAttribute("y1", d.y); ly.setAttribute("y2", d.y);
    ly.setAttribute("opacity", "1");
  }
  const r = d.r, cur = PPCC.mapCur || "GBP";
  const line = function(k, v){
    return '<div class="l"><span>' + k + '</span><b>' + v + '</b></div>';
  };
  tip.innerHTML = '<div class="t">' + _pEsc(String(r.name || r.campaign_id))
    + '</div>'
    + line("Ad spend", ppcMoney(r.spend, cur))
    + line("Ad sales", ppcMoney(r.sales, cur))
    + line("Estimated profit", ppcProfit(r.profit, cur, "greenred"))
    + line("ACOS", ppcPct(r.acos_pct, "No attributed sales, so there is nothing "
                                      + "to divide the spend by."))
    + line("Orders", ppcNum(r.orders))
    + '<div class="n">Across: spend · Up: profit · Size: sales · Colour: ACOS'
    + '</div>';
  // Positioned against the chart box, so it follows the dot rather than the
  // pointer -- the pointer is already on the dot.
  try{
    const box = plot.ownerSVGElement.getBoundingClientRect();
    const vb = plot.ownerSVGElement.viewBox.baseVal;
    const sx = box.width / (vb.width || 1);
    tip.style.left = Math.min(box.width - 230, Math.max(0, d.x * sx + 14)) + "px";
    tip.style.top = Math.max(0, d.y * (box.height / (vb.height || 1)) - 10) + "px";
  }catch(e){
    tip.style.left = "20px";
    tip.style.top = "20px";
  }
  tip.style.display = "block";
}

function ppccDotOut(){
  const tip = document.getElementById("ppcc_tip");
  if(tip) tip.style.display = "none";
  ["ppcc_ch_x", "ppcc_ch_y"].forEach(function(id){
    const el = document.getElementById(id);
    if(el) el.setAttribute("opacity", "0");
  });
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
    // value= AND an id. The value so the box still holds what was typed after
    // ppccRender() replaces it; the id so the focus and the caret can be put
    // back afterwards -- see ppccKeepFocus. Without both, this box accepted
    // exactly one character.
    + '<input class="ppc-input ppc-pill-input" style="width:200px" '
    +   'id="ppcc_q" placeholder="Search campaigns…" '
    +   'value="' + _pEsc(PPCC.q) + '" oninput="ppccFilter(this.value)">'
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
