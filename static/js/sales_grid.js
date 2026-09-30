// static/js/sales_grid.js -- the metrics-by-date product grid and its tools. Moved word for word out of sales.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* ---- the metrics × dates grid ------------------------------------------ */
function salesDrawGrid(ser){
  const host=document.getElementById("sales_grid");
  if(!host) return;
  if(!ser || !ser.ok){
    host.innerHTML=(ser&&ser.error)
      ? uiError("The sales grid could not be loaded", ser.error, "salesReload", "sales")
      : '<div class="empty">No data</div>';
    return;
  }
  if(ser.empty || !(ser.metrics||[]).length){
    host.innerHTML='<div class="empty">No sales data for this period yet.'
      + '<div class="cc" style="margin-top:6px;font-size:11.5px">Amazon delivers sales '
      + 'a day or two behind, and never for today. Press Sync to pull what it has.</div></div>';
    return;
  }
  const cols=ser.columns||[];
  // ORBIT'S TITLE FOR THIS TABLE, and its description. The grid had neither, so
  // the most information-dense thing on the page arrived unannounced -- and the
  // colour in it needs saying, because a heatmap whose scale is not explained
  // is just decoration.
  let h='<div class="panelhead" style="margin:0 0 12px;padding:0"><div>'
      + '<p class="paneltitle">P&amp;L Heatmap</p>'
      // Orbit's own line, word for word and at its own 10px rather than the
      // 12px the other panel subtitles use -- measured: its P&L Heatmap
      // subtitle is smaller than its Live Sales one. "coloring" is Orbit's
      // spelling and this is a match to Orbit, not to the rest of the app.
      + '<p class="panelsub" style="font-size:10px">Performance metrics with '
      + 'heatmap coloring across '
      // The colour's meaning belongs HERE, on the hover, not as prose on the
      // page. Orbit does the same: a short line, an i, and the explanation only
      // if you ask for it.
      + 'time periods<span class="infodot" title="Colour = effect on PROFIT, '
      + 'against the previous column.&#10;&#10;'
      + 'Green is always good, red is always bad. Sales, orders and units going '
      + 'up is green. Fees, refunds, ad spend and cost of goods going up is RED '
      + '— the number rose but the profit fell.&#10;&#10;'
      + 'Depth = size of the change: under 1% is left plain, 20% or more is '
      + 'solid. It is a percentage, so it is per row — a dark red in fees is not '
      + 'the same pounds as a dark red in sales.&#10;&#10;'
      + 'A loss is red whatever the change was. Hover any cell for its figure '
      + 'and the change behind the colour.">i</span></p>'
      + '</div></div>'
      + _sGridTools(ser)
      + '<div class="salesgridwrap"><table class="salesgrid"><thead><tr>'
      + '<th class="mcol">Metric</th>'
      + cols.map(function(c){ return '<th>'+_sEsc(_sColLabel(c, ser.granularity))+'</th>'; }).join("")
      + '</tr></thead><tbody>';

  // ONE ROW, drawn the same way wherever it appears.
  const byKey = {};
  (ser.metrics||[]).forEach(function(m){ byKey[m.key] = m; });

  // A DAY WITH NO SALE SHOWS ZERO, NOT A DASH.
  //
  // "the zeros written also indicates no sales was made so it is right thing."
  //
  // An em-dash means "not known" everywhere in this grid, and for most rows
  // that is exactly right -- Amazon settles fees days later, so a blank fee
  // cell genuinely means "not told yet". But for what was ORDERED, absence is
  // an answer: the order feed is read continuously, so a day it holds no order
  // for is a day that took no orders. Printing a dash there asks the reader to
  // wonder whether the app failed to load it.
  //
  // Only these four, and only inside the period Amazon has actually reported
  // on. Outside it nothing has been checked, and a zero there would be the app
  // asserting something it has not looked at -- which is the fault that put
  // fifteen months of invented zeros in the store in the first place.
  const ORDERED = ["ordered_sales", "orders", "units", "order_items"];
  const _avail = (SALES.avail && SALES.avail.sales) || {};
  const knownFrom = _avail.first_date || "";
  const knownTo = _avail.last_date || "";
  const zeroable = function(key, i){
    if(ORDERED.indexOf(key) < 0) return false;
    const d = cols[i];
    if(!d || !knownFrom || !knownTo) return false;
    return d >= knownFrom && d <= knownTo;
  };

  const drawRow = function(m){
    // The value each cell is compared against: the previous column. Worked out
    // once for the row, so a cell whose own neighbour is blank still compares
    // against the last figure there actually was rather than against nothing.
    const shownAt = m.cells.map(function(v, i){
      const blank = (v === null || v === undefined);
      return (blank && zeroable(m.key, i)) ? 0 : v;
    });
    return '<tr><th class="mcol" title="'+_sEsc(m.label)+'">'+_sEsc(m.label)+'</th>'
       + shownAt.map(function(shown, i){
           const blank = (m.cells[i] === null || m.cells[i] === undefined);
           const prev = (i > 0) ? shownAt[i - 1] : null;
           const t = _sTint(shown, prev, m.key, m.good);
           const txt = _sNum(shown, m.kind, ser.currency);
           // WHAT DROVE THE COLOUR, on hover. A shade you cannot interrogate is
           // a shade you end up ignoring.
           const d = _sDeltaPct(shown, prev);
           let tip = m.label + ": " + txt;
           if(blank && shown === 0) tip += " — no orders that day";
           if(d !== null && prev !== null && prev !== undefined){
             const sign = d > 0 ? "+" : "";
             tip += "\n" + sign + d.toFixed(1) + "% vs "
                  + _sColLabel(cols[i - 1], ser.granularity)
                  + " (" + _sNum(prev, m.kind, ser.currency) + ")";
             if(Math.abs(d) < 1) tip += " — flat";
             else tip += (t.indexOf("45,212,168") >= 0)
                       ? " — better for profit" : " — worse for profit";
           }
           return '<td'+(t?' style="background:'+t+'"':'')
                + ' title="'+_sEsc(tip)+'">'+_sEsc(txt)+'</td>';
         }).join("")
       + '</tr>';
  };

  // BANDED INTO SECTIONS, as Orbit's is.
  //
  // "the p&l heatmap has spacing in it to separate data and make it easy to
  // understand visually". Measured on Orbit: its grid is six sections, each
  // introduced by a header row -- SALES & REVENUE, ORGANIC, PPC, COSTS &
  // DEDUCTIONS, TRAFFIC, DERIVED -- 24px tall on rgb(45,50,66) against 29px
  // transparent for a data row.
  //
  // That banding is the difference between a grid you can scan and a wall of
  // numbers: "is my advertising working" becomes four adjacent rows instead of
  // four rows scattered through thirty-eight.
  //
  // The sections come from the SERVER, next to where the metrics themselves are
  // defined, so the order cannot drift from the order the metrics are sent in.
  // An older answer with no `sections` still draws -- as one flat list, exactly
  // as before.
  // Rows the Metrics picker has switched off. A section whose every row is
  // hidden loses its heading too -- a band with nothing under it is furniture.
  const hidden = SALES.gridHidden || [];
  const visible = function(k){ return byKey[k] && hidden.indexOf(k) < 0; };
  const sections = (ser.sections || []).filter(function(s){
    return (s.keys || []).some(visible);
  });
  if(sections.length){
    sections.forEach(function(s){
      h += '<tr class="gsec"><th class="mcol">' + _sEsc(s.name) + '</th>'
         + '<td colspan="' + cols.length + '"></td></tr>';
      (s.keys || []).forEach(function(k){ if(visible(k)) h += drawRow(byKey[k]); });
    });
  } else {
    (ser.metrics||[]).forEach(function(m){ if(visible(m.key)) h += drawRow(m); });
  }
  // Every row switched off is not an empty grid with no explanation.
  if(!(ser.metrics||[]).some(function(m){ return visible(m.key); })){
    h += '<tr><th class="mcol">—</th><td colspan="' + cols.length + '" '
      + 'style="text-align:left;color:var(--muted)">Every row is switched off. '
      + 'Use <b>Metrics</b> above to bring some back.</td></tr>';
  }
  h+='</tbody></table></div>';
  host.innerHTML=h;
}

/* ---- the heatmap's own toolbar -----------------------------------------
 *
 * MEASURED on Orbit's P&L Heatmap, control by control:
 *
 *   "33/33 Metrics"   10px/500, transparent, radius 6, padding 4px 12px
 *   PRODUCTS          11px/600 uppercase label, rgb(156,163,175)
 *   All Products (166)  13px/400 on rgb(45,50,66), radius 8, padding 7px 12px
 *   GRANULARITY       Day | Week | Month -- 10px, the active one 600 on
 *                     #fbbf24, radius 4, padding 4px 10px
 *   Last: 8/13
 *   PERIOD            7d | 14d | 30d | 60d | 90d | Custom, same pill styling
 *   Export            10px/500, radius 6
 *
 * and under them a COGS strip: "COGS  Actual · $22.36 avg/unit ·
 * 99.7% of shipped units covered  Change setting →".
 *
 * Ours says "of SKUs costed" rather than "of shipped units covered", because
 * that is what this app actually knows -- domain/cogs.py counts SKUs with a
 * cost against SKUs without one. Borrowing Orbit's wording for a different
 * measurement would be a wrong number with a right-sounding label.
 */
const _S_GRANS = [["day", "Day"], ["week", "Week"], ["month", "Month"]];
const _S_GRID_PERIODS = [["7d", "7d"], ["14d", "14d"], ["30d", "30d"],
                         ["60d", "60d"], ["90d", "90d"]];

function _sPills(items, current, fn){
  return '<span class="gpills">' + items.map(function(p){
    const on = (p[0] === current);
    return '<button class="gpill' + (on ? " on" : "") + '"'
         + ' onclick="' + fn + '(' + jsArg(p[0]) + ')">' + _sEsc(p[1]) + '</button>';
  }).join("") + '</span>';
}

function _sGridTools(ser){
  const hidden = SALES.gridHidden || [];
  const all = (ser.metrics || []).length;
  const shown = (ser.metrics || []).filter(function(m){
    return hidden.indexOf(m.key) < 0; }).length;
  // Which period and granularity the GRID is on -- its own if it has been
  // touched, otherwise the screen's, which is what it is actually drawing.
  const gran = SALES.gridGran || SALES.gran || "day";
  const period = SALES.gridPreset || SALES.preset || "30d";
  const last = (ser.columns || []).length
    ? _sColLabel((ser.columns || [])[ser.columns.length - 1], gran) : "";

  let h = '<div class="gtools">'
    + '<button class="gbtn" onclick="salesMetricsOpen(event)" '
    + 'title="Choose which rows this grid shows">'
    + shown + '/' + all + ' Metrics</button>';

  // The product filter is the SAME one the rest of the screen uses -- a second
  // one that filtered only the grid would be two answers to one question.
  const asinLabel = SALES.asin ? SALES.asin : "All products";
  h += '<span class="glbl">Products</span>'
    + '<button class="gbtn wide" onclick="salesFocusProducts()" '
    + 'title="The product filter at the top of this screen">'
    + _sEsc(asinLabel) + '</button>';

  h += '<span class="glbl">Granularity</span>'
    + _sPills(_S_GRANS, gran, "salesGridGran");
  if(last) h += '<span class="glast">Last: ' + _sEsc(last) + '</span>';

  h += '<span class="glbl">Period</span>'
    + _sPills(_S_GRID_PERIODS, period, "salesGridPeriod");
  // Says when the grid has been taken off the screen's own range, and offers
  // the way back -- otherwise the numbers here and the chart above disagree
  // with nothing on screen explaining why.
  if(SALES.gridGran || SALES.gridPreset){
    h += '<button class="gbtn" onclick="salesGridFollow()" '
      + 'title="Show the same period as the charts above">'
      + '<i class="ti ti-arrow-back-up"></i> Match the charts</button>';
  }
  h += '<span class="gspacer"></span>'
    + '<button class="gbtn" onclick="salesExport()">'
    + '<i class="ti ti-download"></i> Export</button>'
    + '</div>';

  // ---- the COGS strip ----------------------------------------------------
  const cov = (SALES.data && SALES.data.cogs_coverage) || null;
  if(cov && cov.total){
    // Average cost per unit shipped, from this grid's own figures, so it can
    // never disagree with the Cost of goods row below it.
    const sum = function(key){
      const m = (ser.metrics || []).filter(function(x){ return x.key === key; })[0];
      if(!m) return null;
      let t = 0, any = false;
      (m.cells || []).forEach(function(v){
        if(v !== null && v !== undefined){ t += Number(v); any = true; } });
      return any ? t : null;
    };
    const c = sum("cogs"), u = sum("units_shipped");
    const per = (c && u) ? (c / u) : null;
    h += '<div class="gcogs">'
      + '<span class="glbl">COGS</span>'
      + (per !== null
          ? '<b>' + _sEsc(_sNum(per, "money", ser.currency)) + '</b> avg/unit'
          : '<span class="cc">no costed units in this period</span>')
      + '<span class="gsep">·</span>'
      + '<b>' + (cov.pct === null || cov.pct === undefined ? "—" : cov.pct + "%")
      + '</b> of SKUs costed'
      + (cov.unknown
          ? '<span class="cc"> (' + cov.unknown + ' of ' + cov.total + ' have no cost, '
            + 'so profit is withheld for any period containing them)</span>' : "")
      + '<button class="glink" onclick="navTo(\'listings\')">Change setting →</button>'
      + '</div>';
  }

  // ---- where Amazon's own two answers do not agree -----------------------
  //
  // A row is meant to read across: what the buyers paid, split into the part
  // that is yours and the VAT that is not. On a few days it cannot, because
  // Amazon's Finances feed and its Orders feed disagree about those particular
  // orders -- ones refunded in full, and cross-border ones where Amazon
  // collected the VAT itself and reported a different total for the same order.
  //
  // Neither figure is wrong and neither is adjusted to fit the other. What was
  // missing was saying so: the grid showed 601.08 + 15.80 under a sales row of
  // 605.77 and left it to be noticed, which reads as a fault in the app rather
  // than as a fact about the data.
  // ---- "there is nothing here, and that is not a fault" -------------------
  //
  // THE REPORT: "the sales report and p&l heatmap do not show data beyond 27th
  // july no matter if i select 30 day, 60d or 90d", and then: "when no data is
  // available its okay but the user should be able to see that there is no
  // data available".
  //
  // Nestwell Goods has nothing before 27 July — checked against Amazon, which
  // returns a genuine zero for 10 July, so the account simply was not selling.
  // 30, 60 and 90 days really are the same figures. But the screen said none of
  // that: it drew the extra weeks as blank columns, which reads as the app
  // having failed to load them.
  //
  // An em-dash means "not known" everywhere else in this grid and still does.
  // What was missing is anybody saying WHY a run of them is there.
  //
  // KEPT SHORT ON PURPOSE. This was a paragraph, and the owner's answer was
  // "i think the note in english wont be so good" -- fair: a wall of English
  // is not what someone scanning a grid of numbers wants, and this app is read
  // by someone who does not use English first. The zeros above now carry the
  // meaning; this only has to date the edge.
  const _av = (SALES.avail && SALES.avail.sales) || {};
  if(_av.first_date && ser.start && ser.start < _av.first_date){
    h += '<div class="gcogs gnodata">'
      + '<span class="glbl">Trading from</span>'
      + '<b>' + _sEsc(_sColLabel(_av.first_date, "day")) + '</b>'
      + '<span class="infodot" title="This account has nothing before '
      + _sEsc(_av.first_date) + '. The columns before it are empty because '
      + 'there was no trade to report, not because they failed to load — so a '
      + 'longer period shows the same figures as a shorter one.">i</span>'
      + '</div>';
  }

  const tie = ser.tie_out;
  if(tie && tie.days){
    const worst = (tie.worst || []).map(function(w){
      return _sColLabel(w[0], gran) + " " + _sNum(w[1], "money", ser.currency);
    }).join(", ");
    // Label, figure, and the explanation on the hover -- not a paragraph on the
    // page. Same shape as everything else here.
    h += '<div class="gcogs gtie">'
      + '<span class="glbl">Tie-out</span>'
      + '<b>' + _sEsc(_sNum(tie.amount, "money", ser.currency)) + '</b>'
      + ' over ' + tie.days + ' day' + (tie.days === 1 ? "" : "s")
      + '<span class="infodot" title="' + _sEsc(tie.note)
      + (worst ? "\n\nLargest: " + worst + "." : "")
      + '">i</span>'
      + '</div>';
  }
  return h;
}

/* The product filter lives in the toolbar at the top of the screen. Rather than
   build a second one here -- two controls for one setting is how they come to
   disagree -- this takes you to the one that exists and makes it obvious. */
function salesFocusProducts(){
  const el = document.getElementById("sales_asin");
  if(!el) return;
  try{ el.scrollIntoView({block: "center", behavior: "smooth"}); }catch(e){}
  try{ el.focus(); }catch(e){}
  el.classList.add("flashfocus");
  setTimeout(function(){ el.classList.remove("flashfocus"); }, 1400);
}

function salesGridGran(g){
  SALES.gridGran = (g === (SALES.gran || "day") && !SALES.gridPreset) ? "" : g;
  salesLoadGrid();
}
function salesGridPeriod(p){
  SALES.gridPreset = (p === (SALES.preset || "30d") && !SALES.gridGran) ? "" : p;
  salesLoadGrid();
}
function salesGridFollow(){
  SALES.gridGran = ""; SALES.gridPreset = ""; SALES.gridSeries = null;
  if(SALES.series) salesDrawGrid(SALES.series);
}

/* Fetch the grid's OWN series, when it has been taken off the screen's range.
   Same endpoint, same shape -- only the two parameters differ, so nothing about
   how a figure is produced can drift between the chart and the grid. */
/* The grid, redrawn for WHATEVER PERIOD IT IS ON. The screen's reload and the
   late live-orders fill both called salesDrawGrid(SALES.series) -- the screen's
   range -- even when the grid had been given its own period, so the toolbar
   said "7d · Week" over thirty days of daily columns. When the grid has its own
   period it is re-fetched for it instead. */
function salesRedrawGrid(){
  if(SALES.gridGran || SALES.gridPreset) return salesLoadGrid();
  if(SALES.series) salesDrawGrid(SALES.series);
}

async function salesLoadGrid(){
  if(!SALES.gridGran && !SALES.gridPreset){
    SALES.gridSeries = null;
    if(SALES.series) salesDrawGrid(SALES.series);
    return;
  }
  // NEWEST CLICK WINS. A click while a load was out used to be dropped
  // (gridBusy) -- the pill lit up for the new period and the grid kept the old
  // one. Each load takes a ticket; only the latest may draw.
  const tk = SALES.gridSeq = (SALES.gridSeq || 0) + 1;
  SALES.gridBusy = true;
  const host = document.getElementById("sales_grid");
  if(host) host.style.opacity = ".45";
  try{
    const preset = SALES.gridPreset || SALES.preset || "30d";
    const q = ["preset=" + encodeURIComponent(preset),
               "granularity=" + encodeURIComponent(SALES.gridGran || SALES.gran || "day")];
    // A CUSTOM PERIOD CARRIES ITS DATES. With the grid following a custom
    // screen range (only its granularity changed), "preset=custom" went alone
    // and the server fell back to its default window.
    if(preset === "custom"){
      if(!(SALES.start && SALES.end)){ return; }
      q.push("start=" + encodeURIComponent(SALES.start));
      q.push("end=" + encodeURIComponent(SALES.end));
    }
    if(SALES.asin) q.push("asin=" + encodeURIComponent(SALES.asin));
    if(typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__")
      q.push("marketplace=" + encodeURIComponent(WS_MARKET));
    // NO basis HERE. The route decides it, once, for the whole screen.
    //
    // This line used to say basis=order -- and it only ran when the grid had
    // been given its OWN period, which is not the normal case. So the grid the
    // owner actually looks at borrowed SALES.series instead (see the top of
    // this function), and that was fetched without a basis and defaulted to
    // money. Hence a heatmap showing 18.32 of revenue on a day with no orders
    // and no revenue on the day that took three: the grid was on the settlement
    // calendar the whole time while claiming the order one.
    const j = await _sFetch("/sales/series?" + q.join("&"));
    if(tk !== SALES.gridSeq) return;
    if(j && j.ok){ SALES.gridSeries = j; salesDrawGrid(j); }
  }catch(e){
    // Left as it was rather than blanked: the previous grid is still true of
    // the period it was drawn for, and the toolbar says which that is.
  }finally{
    if(tk === SALES.gridSeq){
      SALES.gridBusy = false;
      if(host) host.style.opacity = "";
    }
  }
}

/* Which rows to show. Thirty-eight is a lot to scroll past when the question is
   about four of them, and Orbit puts the same control in the same place. */
function salesMetricsOpen(ev){
  if(ev) ev.stopPropagation();
  const ser = SALES.gridSeries || SALES.series;
  if(!ser || !(ser.metrics || []).length) return;
  const hidden = SALES.gridHidden || [];
  const secs = (ser.sections || []).length
    ? ser.sections
    : [{name: "Metrics", keys: (ser.metrics || []).map(function(m){ return m.key; })}];
  const by = {};
  (ser.metrics || []).forEach(function(m){ by[m.key] = m; });

  let h = '<div class="metricpick-head">Rows to show'
        + '<button class="glink" onclick="salesMetricsAll(1)">all</button>'
        + '<button class="glink" onclick="salesMetricsAll(0)">none</button></div>';
  secs.forEach(function(s){
    const keys = (s.keys || []).filter(function(k){ return by[k]; });
    if(!keys.length) return;
    h += '<div class="metricpick-sec">' + _sEsc(s.name) + '</div>';
    keys.forEach(function(k){
      h += '<label class="metricpick-row"><input type="checkbox"'
        + (hidden.indexOf(k) < 0 ? " checked" : "")
        + ' onchange="salesMetricToggle(' + jsArg(k) + ', this.checked)"> '
        + _sEsc(by[k].label) + '</label>';
    });
  });
  let box = document.getElementById("metricpick");
  if(!box){
    box = document.createElement("div");
    box.id = "metricpick";
    box.className = "metricpick";
    document.body.appendChild(box);
    document.addEventListener("click", function(e){
      if(box && !box.contains(e.target)) box.classList.remove("open");
    });
  }
  box.innerHTML = h;
  const btn = ev && ev.target && ev.target.closest ? ev.target.closest("button") : null;
  const r = btn ? btn.getBoundingClientRect() : {left: 40, bottom: 90};
  box.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 280)) + "px";
  box.style.top = (r.bottom + window.scrollY + 6) + "px";
  box.classList.add("open");
}

function _sGridSave(){
  try{ localStorage.setItem("alta_grid_hidden", JSON.stringify(SALES.gridHidden || [])); }
  catch(e){}
  const ser = SALES.gridSeries || SALES.series;
  if(ser) salesDrawGrid(ser);
}
function salesMetricToggle(key, on){
  const h = SALES.gridHidden || (SALES.gridHidden = []);
  const i = h.indexOf(key);
  if(on && i >= 0) h.splice(i, 1);
  if(!on && i < 0) h.push(key);
  _sGridSave();
}
function salesMetricsAll(on){
  const ser = SALES.gridSeries || SALES.series;
  SALES.gridHidden = on ? [] : (ser.metrics || []).map(function(m){ return m.key; });
  _sGridSave();
  // Redrawing the grid does not redraw the open picker, so it is rebuilt with
  // the boxes in their new state.
  const box = document.getElementById("metricpick");
  if(box && box.classList.contains("open")){
    const btn = document.querySelector(".gtools .gbtn");
    salesMetricsOpen({target: btn, stopPropagation: function(){}});
  }
}

function _sColLabel(c, gran){
  if(gran==="month") return c;                 // 2026-08
  const p=String(c).split("-");
  return p.length===3 ? (p[1].replace(/^0/,"")+"/"+p[2]) : c;
}

/* ONE hue, light→dark, five steps. Five rather than a continuous ramp because
   past about seven classes adjacent shades blur; and the number is printed in
   every cell regardless, so the tint is an aid, never the reading. */
/* Metrics that can legitimately go NEGATIVE, and where the sign is the whole
   point. A loss is not a small profit. */
const _S_SIGNED = ["profit", "margin_pct", "net_proceeds", "roi_pct"];

/* THE SHADING BEHIND A CELL.
 *
 * HUE IS THE DIRECTION OF IMPACT ON PROFIT, NOT WHETHER A NUMBER WENT UP.
 *
 * Stated by the owner, and it is the right model:
 *
 *   income lines   revenue, profit, units, orders   up   = green
 *   cost lines     fees, COGS, ad spend, refunds    down = green
 *
 * so RED ALWAYS MEANS BAD FOR PROFIT and GREEN ALWAYS MEANS GOOD, whichever
 * row you are looking at. This is what the grid did not do: it shaded every row
 * on one green scale by SIZE, so a month of record Amazon fees was the darkest
 * green on the sheet. The direction each metric wants is not guessed here -- it
 * is `good` on the metric itself, set beside the metric's own definition in
 * domain/sales_data.py, so the two cannot drift apart.
 *
 * INTENSITY IS THE SIZE OF THE CHANGE AGAINST THE PRIOR COLUMN.
 *
 *   under 1%   flat -- left unshaded, because a rounding wobble is not news
 *   1 to 5%    faint
 *   5 to 10%   light
 *   10 to 20%  strong
 *   over 20%   solid
 *
 * Percentages, so it is scaled per ROW by construction: a dark red in Referral
 * Fees is not the same number of pounds as a dark red in Revenue -- it is dark
 * because it is a big move FOR THAT LINE.
 *
 * A LOSS IS STILL RED, whatever the change was.
 *
 * The one thing kept from the previous rule. A profit row that goes -80 then
 * -50 has improved, and by change alone the -50 would be green -- a green cell
 * on a day that lost fifty pounds. On the rows where the sign is the whole
 * point (see _S_SIGNED) a negative value is red regardless, because it IS bad
 * for profit, which is the rule this whole scheme exists to express.
 *
 * Colour is never the only carrier: every cell prints its number and its hover
 * gives the exact figure and the change that drove the shade, so the grid reads
 * correctly in black and white and to anyone who cannot separate red from green.
 */
const _S_GREEN = ["rgba(45,212,168,.10)", "rgba(45,212,168,.20)",
                  "rgba(45,212,168,.32)", "rgba(45,212,168,.46)"];
const _S_RED = ["rgba(239,68,68,.10)", "rgba(239,68,68,.20)",
                "rgba(239,68,68,.32)", "rgba(239,68,68,.46)"];

/* The change from the previous column, as a percentage.
 *
 * null when it cannot be one: the first column has nothing before it, and a
 * cell whose neighbour is missing is not a change of anything. Going from zero
 * to something is a real move and is treated as a big one rather than as
 * infinity. */
function _sDeltaPct(v, prev){
  if(v === null || v === undefined || prev === null || prev === undefined) return null;
  const a = Number(v), b = Number(prev);
  if(!isFinite(a) || !isFinite(b)) return null;
  if(b === 0) return (a === 0) ? 0 : (a > 0 ? 100 : -100);
  return ((a - b) / Math.abs(b)) * 100;
}

function _sTint(v, prev, key, good){
  if(v === null || v === undefined) return "";
  const n = Number(v);
  if(!isFinite(n)) return "";

  const signed = _S_SIGNED.indexOf(String(key || "")) >= 0;
  const d = _sDeltaPct(v, prev);

  // A loss is bad however it got there -- and shown at full strength, because
  // "we lost money" is not a shade of grey.
  if(signed && n < 0) return _S_RED[3];

  if(d === null) return "";                 // nothing to compare against
  const mag = Math.abs(d);
  if(mag < 1) return "";                    // flat
  const step = mag >= 20 ? 3 : mag >= 10 ? 2 : mag >= 5 ? 1 : 0;

  // Which way is good for THIS row. Anything unlabelled is treated as an
  // income line, which is what all but the cost rows are.
  const wantUp = String(good || "up") !== "down";
  const helps = wantUp ? (d > 0) : (d < 0);
  return (helps ? _S_GREEN : _S_RED)[step];
}
