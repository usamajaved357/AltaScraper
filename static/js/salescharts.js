// ===================== SALES CHARTS =====================
// Inline SVG, no library. The app already refuses to load anything from a CDN it
// does not control, and a chart library would be 200KB to draw two shapes.
//
// WHAT THESE CHARTS WILL NOT DO
// They never draw a zero where there is no data. Amazon delivers sales a day or
// two late, so the last columns of any range are routinely "not in yet" -- and a
// line that dives to the axis is read as "sales collapsed", which is the single
// most misleading thing a sales chart can do. A missing day breaks the line and
// is shaded, so the gap looks like a gap.
//
// A SECOND AXIS IS ALLOWED IN EXACTLY ONE PLACE, and it is worth saying where
// the line is. Two series that are COMPARED to each other must share a scale --
// a twin axis makes their crossing point look meaningful when it is an artefact
// of how the two scales were chosen, and the eye reads the crossing first. So
// the single-metric charts refuse one.
//
// salesCombo() at the bottom of this file does use one, because its bars are a
// COUNT of orders and its lines are MONEY. Nobody reads "orders crossed above
// revenue"; they read the shape of each. The alternative is two charts that
// cannot be scanned in one glance. Both axes are labelled, so which is which is
// never a guess.

// Orbit's chart palette and line styles, MEASURED off its live Sales Dashboard
// on 15 Aug 2026 (tools/orbit_capture.py -> orbit_interactions.md), not copied
// from a screenshot. Every value here was read from the drawn SVG:
//
//   current period    #fbbf24, 2px, solid
//   period before     #6b7280, 2px, dashed 5,5
//   same period last  #6366f1, 1.5px, dashed 5,3   -- a different comparison,
//     year              so a different line, which is why it is not the same
//                       grey with a different dash
//   area gradient     the line's own colour, 0.30 at 5% fading to 0 at 95%
//                     (prior-year's is fainter, 0.15, because context should
//                      not compete with the subject)
const SC_GOLD      = "#fbbf24";
const SC_COMPARE   = "#6b7280";
const SC_PRIORYEAR = "#6366f1";
const SC_DASH      = "5 5";     // the period before
const SC_DASH_YEAR = "5 3";     // the same period a year earlier

function _scEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
// For a value going inside a single-quoted inline handler, where an apostrophe
// would end the string and a backslash would be eaten by the HTML parser.
function _scAttr(s){
  return _scEsc(s).replace(/'/g, "&#39;");
}
function _scHash(s){
  let h = 0;
  for(let i = 0; i < s.length; i++){ h = (h * 31 + s.charCodeAt(i)) | 0; }
  return h;
}

// ---- hover readout and drag-to-zoom -------------------------------------
// One readout per chart, updated in place. See the note beside the hit targets
// for why the handlers are inline.
const _SC_DRAG = {};

// A ROW ON THE HOVER CARD. Encoded into one attribute because these handlers
// are inline (see the note beside the hit targets): name, colour, value,
// and the y position of that series' dot, joined by characters that cannot
// appear in a formatted number or a series name.
const _SC_ROW = "";     // between fields
const _SC_SEP = "";     // between rows

function _scRows(rows){
  return rows.map(function(r){
    return [r.name, r.color, r.value, (r.y === null || r.y === undefined) ? "" : r.y]
      .join(_SC_ROW);
  }).join(_SC_SEP);
}

function _scHover(cid, i, px, py, label, rowsEnc){
  // THE FLOATING CARD, measured off Orbit: rgb(45,50,66) on a rgb(75,85,99)
  // border, radius 6, padding 8/12, min-width 160, and a gold-tinted shadow.
  // Its wrapper carries `transition: transform .4s`, so it GLIDES to each new
  // column rather than jumping -- which is the movement that makes the chart
  // feel alive, and the thing a corner readout cannot do.
  const tip = document.getElementById(cid + "_tip");
  const svg = document.getElementById(cid + "_svg");
  const rows = String(rowsEnc || "").split(_SC_SEP).filter(Boolean)
    .map(function(s){
      const p = s.split(_SC_ROW);
      return {name: p[0], color: p[1], value: p[2], y: p[3]};
    });

  if(tip && svg){
    tip.innerHTML =
      '<p class="charttip-time">' + label + '</p>'
      + rows.map(function(r){
          return '<div class="charttip-row">'
               + '<span class="charttip-name" style="color:' + r.color + '">'
               + r.name + ':</span>'
               + '<span class="charttip-val">' + r.value + '</span></div>';
        }).join("");
    // The SVG is drawn in viewBox units and displayed at whatever width the
    // panel is, so a position inside it has to be scaled before it can place an
    // HTML element on top.
    let scale = 1;
    try{
      const vb = svg.viewBox.baseVal;
      if(vb && vb.width) scale = (svg.clientWidth || vb.width) / vb.width;
    }catch(e){}
    const w = tip.offsetWidth || 160;
    const host = svg.parentElement;
    const hostW = (host && host.clientWidth) || (svg.clientWidth || 0);
    // Flip to the left of the crosshair when the card would run off the panel,
    // which on the right-hand third of any chart it otherwise does.
    let left = px * scale + 14;
    if(left + w > hostW) left = Math.max(0, px * scale - w - 14);
    tip.style.transform = "translate(" + Math.round(left) + "px, 12px)";
    tip.style.opacity = "1";
  }

  const vl = document.getElementById(cid + "_vl");
  if(vl){ vl.setAttribute("x1", px); vl.setAttribute("x2", px); vl.setAttribute("opacity", "1"); }

  // A DOT ON EVERY SERIES at the hovered column, not just the first: gold and
  // grey circles with a white ring, radius 5 and 2px stroke, as measured.
  const dots = document.getElementById(cid + "_dots");
  if(dots){
    dots.innerHTML = rows.filter(function(r){ return r.y !== "" && r.y !== undefined; })
      .map(function(r){
        return '<circle cx="' + px + '" cy="' + r.y + '" r="5" fill="' + r.color
             + '" stroke="#ffffff" stroke-width="2"/>';
      }).join("");
  }
  // Mid-drag: shade from where the press began to here, so the range being
  // chosen is visible while choosing it.
  const d = _SC_DRAG[cid];
  if(d && d.active){
    d.toIndex = i; d.toX = Number(px);
    const sel = document.getElementById(cid + "_sel");
    if(sel){
      const a = Math.min(d.fromX, d.toX), b = Math.max(d.fromX, d.toX);
      sel.setAttribute("x", a); sel.setAttribute("width", Math.max(0, b - a));
    }
  }
}

function _scLeave(cid){
  const vl = document.getElementById(cid + "_vl");
  if(vl) vl.setAttribute("opacity", "0");
  const dots = document.getElementById(cid + "_dots");
  if(dots) dots.innerHTML = "";
  const tip = document.getElementById(cid + "_tip");
  // Faded rather than emptied: the card keeps its size while it goes, so
  // nothing reflows behind it on the way out.
  if(tip) tip.style.opacity = "0";
  const out = document.getElementById(cid + "_read");
  if(out) out.innerHTML = "";
}

function _scDragStart(cid, i, ev){
  if(ev && ev.preventDefault) ev.preventDefault();   // no text selection
  _SC_DRAG[cid] = {active: true, fromIndex: i, toIndex: i,
                   fromX: Number(ev && ev.target && ev.target.getAttribute("x")) || 0,
                   toX: 0};
  const sel = document.getElementById(cid + "_sel");
  if(sel) sel.setAttribute("width", 0);
}

// DRAG ACROSS A CHART TO ZOOM INTO THOSE DAYS -- the Keepa gesture. A date-range
// picker exists above the charts, but reading a shape and then translating it
// into two dates in two boxes is the step nobody takes, so the interesting week
// never gets looked at closely.
function _scDragEnd(cid, i){
  const d = _SC_DRAG[cid];
  const sel = document.getElementById(cid + "_sel");
  if(sel) sel.setAttribute("width", 0);
  if(!d || !d.active){ return; }
  d.active = false;
  const a = Math.min(d.fromIndex, i), b = Math.max(d.fromIndex, i);
  // A click is not a drag. Two points is the smallest range worth zooming to.
  if(b - a < 1) return;
  if(typeof salesZoomTo === "function") salesZoomTo(a, b);
}
// ---- THE CURVE ----------------------------------------------------------
//
// Orbit's lines are SMOOTH. Measured off its live chart: every path is made of
// `C` commands -- cubic beziers -- and contains not one `L`. Ours joined the
// points with straight segments, and that is the difference that survived
// every colour, size and spacing fix: the same numbers drawn as a polyline
// simply do not read like the same chart.
//
// This is the monotone cubic that Recharts draws with (d3's curveMonotoneX,
// Fritsch-Carlson tangents). MONOTONE is the important word, not just smooth:
// an ordinary spline overshoots between points, so a run of small values
// followed by a large one would bulge BELOW the axis on the way up and draw
// negative sales that never happened. A monotone curve cannot leave the range
// of the points it joins.
function _scCurve(pts){
  const n = pts.length;
  if(n === 0) return "";
  const f = v => v.toFixed(2);
  if(n === 1) return "M" + f(pts[0].x) + "," + f(pts[0].y);
  if(n === 2){
    return "M" + f(pts[0].x) + "," + f(pts[0].y)
         + "L" + f(pts[1].x) + "," + f(pts[1].y);
  }

  const dx = [], dy = [], s = [];
  for(let i = 0; i < n - 1; i++){
    dx[i] = pts[i + 1].x - pts[i].x;
    dy[i] = pts[i + 1].y - pts[i].y;
    s[i]  = dx[i] ? dy[i] / dx[i] : 0;
  }

  // Tangent at each point. Zero wherever the slope changes sign -- that is
  // what pins the curve to a local peak or trough instead of sailing past it.
  const m = new Array(n);
  m[0] = s[0];
  m[n - 1] = s[n - 2];
  for(let i = 1; i < n - 1; i++){
    if(s[i - 1] * s[i] <= 0){
      m[i] = 0;
    } else {
      const w1 = 2 * dx[i] + dx[i - 1];
      const w2 = dx[i] + 2 * dx[i - 1];
      m[i] = (w1 + w2) / (w1 / s[i - 1] + w2 / s[i]);
    }
  }

  let d = "M" + f(pts[0].x) + "," + f(pts[0].y);
  for(let i = 0; i < n - 1; i++){
    const h = dx[i] / 3;
    d += "C" + f(pts[i].x + h) + "," + f(pts[i].y + m[i] * h)
       + "," + f(pts[i + 1].x - h) + "," + f(pts[i + 1].y - m[i + 1] * h)
       + "," + f(pts[i + 1].x) + "," + f(pts[i + 1].y);
  }
  return d;
}

function _scNum(v){
  if(v===null || v===undefined || v==="") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}
function _scFmt(v, kind){
  if(v===null) return "—";
  if(kind === "money") return Number(v).toFixed(2);
  if(kind === "pct")   return Number(v).toFixed(1) + "%";
  return String(Math.round(v));
}

// A "nice" top-of-axis, so the labels are round numbers rather than 3847.219.
function _scNiceMax(v){
  if(!v || v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

// One chart. `points` is [{label, value}] with value === null meaning NO DATA --
// which is drawn as a break, never as zero.
function salesChart(points, opts){
  const o = opts || {};
  // BIGGER, and taller relative to its width. At 720x170 in a three-across grid
  // a chart was a couple of centimetres of squiggle -- too small to read a shape
  // off, which is the only reason to draw one. Fewer, larger charts beat more,
  // smaller ones.
  // ORBIT'S GEOMETRY, MEASURED (orbit_sales_spec.md, scanned at 1600px):
  //
  //   svg        597 x 200   -- a 2.98 ratio. Ours was 720 x 260 (2.77), which
  //                             is why the same data read as a different shape
  //                             however closely the colours matched.
  //   plot area  512 x 160
  //   padding    left 65, top 5, right 20, bottom 35
  //
  // The left padding is what the money labels need and the bottom is what the
  // dates need; the top is deliberately almost nothing, so the line uses the
  // full height of the panel.
  const W = o.width || 597, H = o.height || 200;
  const padL = 65, padR = 20, padT = 5, padB = 35;
  const iw = W - padL - padR, ih = H - padT - padB;
  const vals = points.map(p => _scNum(p.value)).filter(v => v !== null);

  if(!vals.length){
    return '<div class="cc" style="padding:18px;border:1px dashed #2a3446;border-radius:8px;'
         + 'font-size:12px">' + _scEsc(o.title || "") + ' — nothing in this period yet.</div>';
  }

  // THE COMPARISON LINE -- what Orbit's charts have that these did not.
  //
  // A single line answers "what happened". It cannot answer "is that good",
  // which is the question actually being asked of a sales chart, and answering
  // it meant changing the dates and remembering the old shape. The same period
  // immediately before is drawn behind it in grey dashes: current in gold,
  // previous in grey, exactly as the Orbit audit describes (4.11).
  //
  // Same length as `points` and same order. Nulls are gaps here too -- a
  // previous period that has no figure for a day must not be drawn as zero any
  // more than the current one.
  const cmp = (o.compare && o.compare.length === points.length) ? o.compare : null;
  // Declared HERE, once, because the hover rows, the dashes and the legend all
  // ask it -- and a `const` used before its declaration is a dead-zone crash,
  // not a hoisted undefined. It was declared beside the legend, which is after
  // the hover code that reads it.
  const _cIsYear = (o.compareKind === "year");
  const cmpVals = cmp ? cmp.map(p => _scNum(p && p.value)).filter(v => v !== null) : [];

  // BOTH SERIES SHARE ONE SCALE. They have to: two lines on separate scales
  // that cross each other say something that is not true, and the crossing is
  // the exact thing the eye reads first.
  const allVals = vals.concat(cmpVals);
  const lo = Math.min(0, Math.min.apply(null, allVals));
  const hi = _scNiceMax(Math.max.apply(null, allVals));
  const span = (hi - lo) || 1;
  const x = i => padL + (points.length === 1 ? iw / 2 : (i * iw) / (points.length - 1));
  const y = v => padT + ih - ((v - lo) / span) * ih;

  // Gridlines and their labels, at nice fractions of the top value.
  let grid = "";
  [0, 0.25, 0.5, 0.75, 1].forEach(function(f){
    const v = lo + span * f, yy = y(v);
    grid += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="#1e2733" stroke-width="1"/>`
         +  `<text x="${padL - 6}" y="${yy + 3.5}" text-anchor="end" font-size="9.5"
                fill="#7b8794">${_scEsc(_scFmt(v, o.kind))}</text>`;
  });

  // The line, BROKEN wherever a day has no data. Each run of real values is its
  // own path, so nothing is drawn across the gap and nothing implies a zero.
  let paths = "", dots = "", runs = [], run = [];
  points.forEach(function(p, i){
    const v = _scNum(p.value);
    if(v === null){ if(run.length) runs.push(run); run = []; }
    else run.push({i: i, v: v});
  });
  if(run.length) runs.push(run);

  const LINE = o.color || SC_GOLD;
  const cid0 = o.id || ("c" + Math.abs(_scHash(String(o.title || "") + points.length)));

  // THE PREVIOUS PERIOD, FIRST, so the current one is drawn over it. Grey and
  // dashed, thinner, and with no fill: it is context, and context that competes
  // with the subject is just noise.
  if(cmp){
    let cruns = [], crun = [];
    cmp.forEach(function(p, i){
      const v = _scNum(p && p.value);
      if(v === null){ if(crun.length) cruns.push(crun); crun = []; }
      else crun.push({i: i, v: v});
    });
    if(crun.length) cruns.push(crun);
    // Measured off Orbit: 2px and a 5,5 dash for the period before, 1.5px and
    // 5,3 in indigo for the same period a year earlier. A year-ago line is a
    // different question from a period-ago line, so it does not get the same
    // grey with a slightly different dash -- at a glance that reads as noise.
    const cIsYear = (o.compareKind === "year");
    const cCol  = cIsYear ? SC_PRIORYEAR : SC_COMPARE;
    const cW    = cIsYear ? "1.5" : "2";
    const cDash = cIsYear ? SC_DASH_YEAR : SC_DASH;
    cruns.forEach(function(r){
      if(r.length < 2) return;               // one point is not a trend
      const d = _scCurve(r.map(pt => ({x: x(pt.i), y: y(pt.v)})));
      paths += `<path d="${d}" fill="none" stroke="${cCol}" stroke-width="${cW}"
                      stroke-dasharray="${cDash}" stroke-linejoin="round"
                      stroke-linecap="round"/>`;
    });
  }

  runs.forEach(function(r){
    if(r.length === 1){
      dots += `<circle cx="${x(r[0].i)}" cy="${y(r[0].v)}" r="2.6" fill="${LINE}"/>`;
      return;
    }
    const d = _scCurve(r.map(pt => ({x: x(pt.i), y: y(pt.v)})));
    // A GRADIENT under the line rather than a flat wash -- the area fades to
    // nothing at the axis, so the line stays the thing being read and the fill
    // only gives it weight. The class is what the stylesheet animates the sweep
    // on, so the line appears to draw itself.
    //
    // The fill follows the SAME curve and then drops to the axis, so its top
    // edge is the line itself rather than a polyline sitting slightly off it.
    const area = d + ` L ${x(r[r.length-1].i).toFixed(1)} ${y(lo).toFixed(1)}`
               + ` L ${x(r[0].i).toFixed(1)} ${y(lo).toFixed(1)} Z`;
    // The fill carries the same class as the line so the two sweep in TOGETHER.
    // Without it the shading appeared complete while the line was still drawing
    // across it, which reads as a rendering fault rather than an animation.
    paths += `<path class="series" d="${area}" fill="url(#${cid0}_grad)"/>`;
    paths += `<path class="series" d="${d}" fill="none" stroke="${LINE}" stroke-width="2"
                    stroke-linejoin="round" stroke-linecap="round"/>`;
  });

  // Shade the days with no data, so a gap reads as "not in yet" rather than as
  // a chart that failed to draw.
  let gaps = "";
  points.forEach(function(p, i){
    if(_scNum(p.value) !== null) return;
    const half = points.length > 1 ? iw / (points.length - 1) / 2 : iw / 2;
    gaps += `<rect x="${Math.max(padL, x(i) - half)}" y="${padT}"
                   width="${Math.min(half * 2, iw)}" height="${ih}"
                   fill="#7b8794" opacity="0.07"/>`;
  });

  // HOVER, PROPERLY.
  //
  // These carried a <title>, which is the browser's own tooltip: it takes about
  // a second to appear, vanishes if the pointer moves, cannot be styled, and on
  // a touch screen does not exist at all. Reported as "nothing comes up when I
  // hover", which was accurate.
  //
  // Now each column raises a floating CARD beside the pointer -- the time at
  // the top, then a row per series in that series' own colour, with a dot on
  // each line and a crosshair down the column. Measured off Orbit, including
  // the 0.4s transform transition that makes the card glide from column to
  // column instead of jumping.
  //
  // The handlers are inline attributes on purpose: this HTML is built as a
  // string and inserted with innerHTML, so there is no element to bind to until
  // after it is in the document, and a later querySelectorAll pass would have to
  // be re-run on every redraw.
  const cid = cid0;
  let hits = "";
  points.forEach(function(p, i){
    const half = points.length > 1 ? iw / (points.length - 1) / 2 : iw / 2;
    const v = _scNum(p.value);
    // One row per series on the floating card, each named in its own colour --
    // Orbit's layout, measured. The comparison gets a row too: a second line
    // you cannot read a number off is decoration.
    const rows = [{name: (o.seriesName || "This period"), color: LINE,
                   value: (v === null ? "no data yet" : _scFmt(v, o.kind)),
                   y: (v === null ? null : y(v).toFixed(1))}];
    if(cmp){
      const cv = _scNum(cmp[i] && cmp[i].value);
      let cvText = (cv === null ? "—" : _scFmt(cv, o.kind));
      if(v !== null && cv !== null && cv !== 0){
        const pct = ((v - cv) / Math.abs(cv)) * 100;
        cvText += "  (" + (pct >= 0 ? "+" : "") + pct.toFixed(0) + "%)";
      }
      rows.push({name: (_cIsYear ? "Last year" : "Before"),
                 color: (_cIsYear ? SC_PRIORYEAR : SC_COMPARE),
                 value: cvText,
                 y: (cv === null ? null : y(cv).toFixed(1))});
    }
    const shown = _scRows(rows);
    hits += `<rect x="${Math.max(padL, x(i) - half)}" y="${padT}"
                   width="${Math.min(half * 2, iw)}" height="${ih}" fill="transparent"
                   style="cursor:crosshair"
                   onmousemove="_scHover('${cid}',${i},${x(i).toFixed(1)},${
                       v === null ? -1 : y(v).toFixed(1)},'${_scAttr(p.label)}','${_scAttr(shown)}')"
                   onmouseleave="_scLeave('${cid}')"
                   onmousedown="_scDragStart('${cid}',${i},event)"
                   onmouseup="_scDragEnd('${cid}',${i})"></rect>`;
  });
  // The marker: a vertical line and a dot, moved by the handler rather than
  // redrawn, so hovering costs nothing.
  // The crosshair is GOLD and solid at full opacity -- measured off Orbit's,
  // which is rgb(251,191,36) at 1px. Ours was the series colour at 0.55.
  hits = `<line id="${cid}_vl" x1="0" y1="${padT}" x2="0" y2="${padT + ih}"
                stroke="${SC_GOLD}" stroke-width="1" opacity="0"/>`
       + `<g id="${cid}_dots"></g>`
       + `<rect id="${cid}_sel" x="0" y="${padT}" width="0" height="${ih}"
                fill="${LINE}" opacity="0.14" pointer-events="none"/>`
       + hits;

  // The gradient the area is painted with. Defined per chart because the colour
  // is per chart, and referenced by id -- two charts on one page must not share
  // one definition and therefore one colour.
  // Stops measured off Orbit's own gradients (goldGradient, blueGradient,
  // salesGradient): 0.30 at 5%, fading to 0 at 95%.
  const defs = `<defs><linearGradient id="${cid}_grad" x1="0" y1="0" x2="0" y2="1">`
             + `<stop offset="5%" stop-color="${LINE}" stop-opacity="0.30"/>`
             + `<stop offset="95%" stop-color="${LINE}" stop-opacity="0"/>`
             + `</linearGradient></defs>`;

  // A legend, only when there are two things to tell apart. One line needs no
  // key, and a key for one line is furniture.
  const legend = cmp
    ? '<span style="font-size:10.5px;display:inline-flex;align-items:center;gap:10px">'
      + '<span style="display:inline-flex;align-items:center;gap:4px">'
      + '<svg width="16" height="6"><line x1="0" y1="3" x2="16" y2="3" stroke="' + LINE
      + '" stroke-width="2"/></svg>this period</span>'
      + '<span style="display:inline-flex;align-items:center;gap:4px" class="cc">'
      + '<svg width="16" height="6"><line x1="0" y1="3" x2="16" y2="3" stroke="'
      + (_cIsYear ? SC_PRIORYEAR : SC_COMPARE)
      + '" stroke-width="' + (_cIsYear ? "1.5" : "2") + '" stroke-dasharray="'
      + (_cIsYear ? SC_DASH_YEAR : SC_DASH) + '"/></svg>'
      + (_cIsYear ? "the same period last year" : "the period before") + '</span></span>'
    : "";

  // Only a few x labels, or they collide and none of them can be read.
  let xl = "";
  const step = Math.max(1, Math.ceil(points.length / 7));
  points.forEach(function(p, i){
    if(i % step && i !== points.length - 1) return;
    xl += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="9.5"
                 fill="#7b8794">${_scEsc(String(p.label).slice(5))}</text>`;
  });

  const missing = points.filter(p => _scNum(p.value) === null).length;
  return '<div style="margin-bottom:14px">'
       + '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:2px;flex-wrap:wrap">'
       + '<div style="font-size:12.5px;font-weight:600">' + _scEsc(o.title || "") + '</div>'
       + (missing ? '<span class="cc" style="font-size:10.5px">' + missing
                    + ' day' + (missing===1?'':'s') + ' not in from Amazon yet — shaded, not zero</span>' : '')
       // Where the hover answer lands. Beside the title, so the eye does not
       // have to leave the chart to read it.
       + '<span id="' + cid + '_read" style="font-size:11.5px;margin-left:auto;'
       + 'font-variant-numeric:tabular-nums"></span>'
       + '</div>'
       // Every chart says where its numbers came from. Amazon has two feeds that
       // describe the same trade and they disagree for days at a time, so a
       // shape without its source is a shape you cannot act on.
       + (o.subtitle ? '<div class="cc" style="font-size:10.5px;margin:-1px 0 5px">'
                       + _scEsc(o.subtitle) + '</div>' : '')
       + (legend ? '<div style="margin:-1px 0 5px">' + legend + '</div>' : '')
       + '<div class="cc" style="font-size:10px;margin:-2px 0 5px;opacity:.65">'
       + 'Hover for the day’s figure · drag across to zoom into those days</div>'
       // NOT preserveAspectRatio="none". That stretched the viewBox horizontally
       // to whatever the container was and left the vertical scale at 1, so every
       // axis label, date and tooltip was squashed or smeared by however wide the
       // panel happened to be -- and the line's stroke thickened in one direction
       // only. Scaling uniformly costs a taller chart on a wide screen and makes
       // the text legible at every width, including on a phone.
       // position:relative so the floating hover card can be placed over the
       // chart in page pixels while the chart itself is drawn in viewBox units.
       + '<div style="position:relative">'
       + `<svg id="${cid}_svg" class="chartbox" viewBox="0 0 ${W} ${H}" width="100%"
               style="display:block;height:auto;background:#0d1220;
                      border:1px solid #1e2733;border-radius:8px">`
       + defs + grid + gaps + paths + dots + xl + hits + '</svg>'
       + `<div id="${cid}_tip" class="charttip"></div>`
       + '</div></div>';
}


// ===================== THE COMBO CHART =====================
// Orbit's main Sales Report chart, rebuilt from measurements rather than from
// the look of it: gold bars for orders against a right-hand count axis, and
// money lines against the left-hand axis, with the key underneath.
//
// EVERY VALUE HERE WAS MEASURED off the live dashboard (orbit_interactions.md):
//   bars           #fbbf24 at 0.3 opacity, 28px wide
//   grid lines     rgb(55,65,81), 1px
//   axis labels    11px, rgb(156,163,175)
//   legend text    12px
//   sales line     #10b981 2px      profit line  #38bdf8 2px
//   prior year     #6366f1 1.5px dashed 5,3
//   prior period   #6b7280 2px dashed 5,5
//
// WHY TWO AXES, when the single-metric charts deliberately refuse one.
// A twin axis is dishonest when the two series are compared to each other --
// the crossing point is meaningless and the eye reads it anyway. Here the bars
// are a COUNT and the lines are MONEY, they are never read against each other,
// and the alternative is two charts that cannot be scanned in one glance. Orbit
// makes the same call. The axes are labelled so which is which is never a
// guess.
const SC_SERIES = {
  sales:      {label: "Sales",            color: "#10b981", width: 2,   dash: ""},
  profit:     {label: "Profit",           color: "#38bdf8", width: 2,   dash: ""},
  prior_year: {label: "Prior Year Sales", color: "#6366f1", width: 1.5, dash: "5 3"},
  prior:      {label: "Prior period",     color: "#6b7280", width: 2,   dash: "5 5"},
  // Orbit's own organic/paid colours, from its gradientOrganic and gradientPpc.
  organic:    {label: "Organic",          color: "#10b981", width: 2,   dash: ""},
  ppc:        {label: "PPC",              color: "#8b5cf6", width: 2,   dash: ""},
};

function salesCombo(o){
  const cols  = o.columns || [];
  const bars  = o.bars || null;              // {key,label,values[]}
  const lines = (o.lines || []).filter(function(l){
    return (l.values || []).some(function(v){ return _scNum(v) !== null; });
  });
  if(!cols.length) return "";

  // Measured: the Sales Report panel is 1261 wide with 16px padding, so the
  // chart has 1229 to work in, and the panel's height leaves it about 330 once
  // the header and the row of stat cards are taken out.
  //
  // The left and top padding match the small charts exactly; the right is wider
  // because a SECOND axis lives there. Without space reserved for it the last
  // bar sat under the labels, which was most of why the first attempt looked
  // wrong.
  const W = o.width || 1229, H = o.height || 330;
  const padL = 65, padR = 56, padT = 5, padB = 46;
  const iw = W - padL - padR, ih = H - padT - padB;

  const moneyVals = [];
  lines.forEach(function(l){
    (l.values || []).forEach(function(v){
      const n = _scNum(v); if(n !== null) moneyVals.push(n);
    });
  });
  const barVals = (bars && bars.values || []).map(_scNum).filter(function(v){ return v !== null; });

  const cid0 = o.id || "combo";
  const mLo = Math.min(0, moneyVals.length ? Math.min.apply(null, moneyVals) : 0);
  const mHi = _scNiceMax(moneyVals.length ? Math.max.apply(null, moneyVals) : 1);
  const mSpan = (mHi - mLo) || 1;
  const bHi = _scNiceMax(barVals.length ? Math.max.apply(null, barVals) : 1);

  const x  = i => padL + (cols.length === 1 ? iw / 2 : (i * iw) / (cols.length - 1));
  const yM = v => padT + ih - ((v - mLo) / mSpan) * ih;
  const yB = v => padT + ih - (v / (bHi || 1)) * ih;

  // Gridlines and both sets of tick labels, at the same five heights so the
  // two scales line up visually instead of drawing two sets of rules.
  let grid = "";
  [0, 0.25, 0.5, 0.75, 1].forEach(function(f){
    const yy = padT + ih - f * ih;
    grid += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"
                   stroke="rgb(55,65,81)" stroke-width="1"/>`
         +  `<text x="${padL - 8}" y="${yy + 4}" text-anchor="end" font-size="11"
                  fill="rgb(156,163,175)">${_scEsc(_scFmt(mLo + mSpan * f, "money"))}</text>`
         +  `<text x="${W - padR + 8}" y="${yy + 4}" text-anchor="start" font-size="11"
                  fill="rgb(156,163,175)">${_scEsc(String(Math.round(bHi * f)))}</text>`;
  });

  // BARS FIRST, so the lines sit over them. 28px measured, but never wider than
  // the space one column actually has -- a 90-day range at 28px would overlap
  // into a solid block.
  let barsSvg = "";
  if(bars){
    const slot = cols.length > 1 ? iw / (cols.length - 1) : iw;
    const bw = Math.max(2, Math.min(28, slot * 0.62));
    (bars.values || []).forEach(function(v, i){
      const n = _scNum(v);
      if(n === null || n <= 0) return;
      const top = yB(n), h = (padT + ih) - top;
      barsSvg += `<rect class="bar" x="${(x(i) - bw / 2).toFixed(1)}" y="${top.toFixed(1)}"
                        width="${bw.toFixed(1)}" height="${Math.max(0, h).toFixed(1)}"
                        fill="#fbbf24" fill-opacity="0.3" rx="2"/>`;
    });
  }

  // Lines, each broken wherever a day has no figure -- the same refusal to draw
  // through a gap that the single-metric charts make.
  let linesSvg = "";
  lines.forEach(function(l){
    const spec = SC_SERIES[l.key] || {color: "#8fd694", width: 2, dash: ""};
    let run = [], runs = [];
    (l.values || []).forEach(function(v, i){
      const n = _scNum(v);
      if(n === null){ if(run.length) runs.push(run); run = []; }
      else run.push({i: i, v: n});
    });
    if(run.length) runs.push(run);
    runs.forEach(function(r){
      if(r.length === 1){
        linesSvg += `<circle cx="${x(r[0].i)}" cy="${yM(r[0].v)}" r="2.6" fill="${spec.color}"/>`;
        return;
      }
      const d = _scCurve(r.map(p => ({x: x(p.i), y: yM(p.v)})));
      // THE SHADOW UNDER THE LINE. Orbit fills beneath every one of its money
      // lines with a gradient of that line's own colour -- 0.30 at the top
      // fading to nothing at the axis (measured: goldGradient, blueGradient,
      // salesGradient). This chart had no fill at all, which is why it read as
      // flat beside Orbit's however well the line itself matched.
      //
      // Drawn BEFORE the line, so the stroke sits on top of its own shading,
      // and only for solid series: a comparison line is context and filling
      // under it would give the past the same visual weight as the present.
      if(!spec.dash){
        const area = d + ` L ${x(r[r.length-1].i).toFixed(1)} ${yM(mLo).toFixed(1)}`
                       + ` L ${x(r[0].i).toFixed(1)} ${yM(mLo).toFixed(1)} Z`;
        linesSvg += `<path class="series" d="${area}"
                           fill="url(#${cid0}_g_${l.key})"/>`;
      }
      linesSvg += `<path class="series" d="${d}" fill="none" stroke="${spec.color}"
                         stroke-width="${spec.width}"
                         ${spec.dash ? `stroke-dasharray="${spec.dash}"` : ""}
                         stroke-linejoin="round" stroke-linecap="round"/>`;
    });
  });

  // x labels, thinned so they can be read
  let xl = "";
  const step = Math.max(1, Math.ceil(cols.length / 16));
  cols.forEach(function(c, i){
    if(i % step && i !== cols.length - 1) return;
    xl += `<text x="${x(i)}" y="${H - 34}" text-anchor="middle" font-size="11"
                 fill="rgb(156,163,175)">${_scEsc(String(c).slice(5))}</text>`;
  });

  // Hover: one readout for every series at that column, which is the whole
  // reason to put them on one chart.
  // One gradient per series, since each fills in its own colour. Stops measured
  // off Orbit's: 0.30 at 5%, fading to 0 at 95%.
  const defs = "<defs>" + lines.map(function(l){
    const spec = SC_SERIES[l.key] || {color: "#8fd694"};
    return `<linearGradient id="${cid0}_g_${l.key}" x1="0" y1="0" x2="0" y2="1">`
         + `<stop offset="5%" stop-color="${spec.color}" stop-opacity="0.30"/>`
         + `<stop offset="95%" stop-color="${spec.color}" stop-opacity="0"/>`
         + `</linearGradient>`;
  }).join("") + "</defs>";

  const cid = cid0;
  // Gold crosshair, as measured on Orbit -- rgb(251,191,36) at 1px, solid.
  let hits = `<line id="${cid}_vl" x1="0" y1="${padT}" x2="0" y2="${padT + ih}"
                    stroke="${SC_GOLD}" stroke-width="1" opacity="0"/>`
           + `<g id="${cid}_dots"></g>`;
  cols.forEach(function(c, i){
    const half = cols.length > 1 ? iw / (cols.length - 1) / 2 : iw / 2;
    // A ROW PER SERIES on the floating card, each in its own colour, with the
    // dot placed on that series' own line. Bars get a row too but no dot --
    // a dot on a bar has nothing to sit on.
    const rows = [];
    if(bars){
      const bv = _scNum((bars.values || [])[i]);
      rows.push({name: (bars.label || "Orders"), color: SC_GOLD,
                 value: (bv === null ? "—" : String(Math.round(bv))), y: null});
    }
    lines.forEach(function(l){
      const spec = SC_SERIES[l.key] || {label: l.key, color: "#8fd694"};
      const v = _scNum((l.values || [])[i]);
      rows.push({name: (spec.label || l.key), color: spec.color,
                 value: (v === null ? "—" : _scFmt(v, "money")),
                 y: (v === null ? null : yM(v).toFixed(1))});
    });
    // DRAG TO ZOOM, on this chart too. The per-metric panels had it and this
    // one replaced them, so without it the gesture simply disappeared from the
    // screen -- and it is the only way anyone actually looks closely at an
    // interesting week.
    hits += `<rect x="${Math.max(padL, x(i) - half)}" y="${padT}"
                   width="${Math.min(half * 2, iw)}" height="${ih}" fill="transparent"
                   style="cursor:crosshair"
                   onmousemove="_scHover('${cid}',${i},${x(i).toFixed(1)},-1,
                       '${_scAttr(c)}','${_scAttr(_scRows(rows))}')"
                   onmouseleave="_scLeave('${cid}')"
                   onmousedown="_scDragStart('${cid}',${i},event)"
                   onmouseup="_scDragEnd('${cid}',${i})"></rect>`;
  });
  // The shaded band that shows the range while it is being chosen, and the
  // readout the drag writes into.
  hits = `<rect id="${cid}_sel" x="0" y="${padT}" width="0" height="${ih}"
                fill="${SC_GOLD}" opacity="0.14" pointer-events="none"/>` + hits;

  // The key, underneath and centred, with the coloured marks Orbit uses: a
  // filled square for the bars, a line for each line.
  let key = '<div style="display:flex;gap:18px;justify-content:center;'
          + 'flex-wrap:wrap;margin-top:6px;font-size:12px">';
  if(bars){
    key += '<span style="display:inline-flex;align-items:center;gap:6px">'
        +  '<span style="width:11px;height:11px;border-radius:2px;background:#fbbf24;'
        +  'opacity:.55;display:inline-block"></span>' + _scEsc(bars.label || "Orders")
        +  '</span>';
  }
  lines.forEach(function(l){
    const spec = SC_SERIES[l.key] || {color: "#8fd694", width: 2, dash: ""};
    key += '<span style="display:inline-flex;align-items:center;gap:6px">'
        +  '<svg width="16" height="8"><line x1="0" y1="4" x2="16" y2="4" stroke="'
        +  spec.color + '" stroke-width="' + spec.width + '"'
        +  (spec.dash ? ' stroke-dasharray="' + spec.dash + '"' : "") + '/></svg>'
        +  _scEsc(spec.label) + '</span>';
  });
  key += '</div>';

  return '<div style="margin:4px 0 0">'
       // Says the gesture exists. Nobody discovers drag-to-zoom by accident.
       + '<div class="cc" style="font-size:10px;margin:0 0 4px;opacity:.65">'
       + 'Hover for the day’s figures · drag across to zoom into those days'
       + '<span id="' + cid + '_read" style="margin-left:auto"></span></div>'
       + '<div style="position:relative">'
       + `<svg id="${cid}_svg" class="chartbox" viewBox="0 0 ${W} ${H}" width="100%"
               style="display:block;height:auto;background:transparent;border:0">`
       + defs + grid + barsSvg + linesSvg + xl + hits + '</svg>'
       + `<div id="${cid}_tip" class="charttip"></div>`
       + '</div>'
       + key + '</div>';
}
