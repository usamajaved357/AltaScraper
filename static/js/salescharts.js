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
// They also never invent a second axis. Two series on one chart share a scale
// only when they share a unit; revenue and units do not, so they get separate
// charts rather than a twin axis whose crossings mean nothing.

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

function _scHover(cid, i, px, py, label, shown){
  const out = document.getElementById(cid + "_read");
  if(out) out.innerHTML = '<b>' + label + '</b> · ' + shown;
  const vl = document.getElementById(cid + "_vl");
  if(vl){ vl.setAttribute("x1", px); vl.setAttribute("x2", px); vl.setAttribute("opacity", "0.55"); }
  const dot = document.getElementById(cid + "_dot");
  if(dot){
    if(py >= 0){ dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.setAttribute("opacity", "1"); }
    else { dot.setAttribute("opacity", "0"); }
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
  ["_vl", "_dot"].forEach(function(s){
    const el = document.getElementById(cid + s);
    if(el) el.setAttribute("opacity", "0");
  });
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
  const W = o.width || 720, H = o.height || 260;
  const padL = 56, padR = 12, padT = 14, padB = 30;
  const iw = W - padL - padR, ih = H - padT - padB;
  const vals = points.map(p => _scNum(p.value)).filter(v => v !== null);

  if(!vals.length){
    return '<div class="cc" style="padding:18px;border:1px dashed #2a3446;border-radius:8px;'
         + 'font-size:12px">' + _scEsc(o.title || "") + ' — nothing in this period yet.</div>';
  }

  const lo = Math.min(0, Math.min.apply(null, vals));
  const hi = _scNiceMax(Math.max.apply(null, vals));
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

  runs.forEach(function(r){
    if(r.length === 1){
      dots += `<circle cx="${x(r[0].i)}" cy="${y(r[0].v)}" r="2.6" fill="${o.color || '#6ac7e8'}"/>`;
      return;
    }
    const d = r.map((pt, k) => (k ? "L" : "M") + x(pt.i).toFixed(1) + " " + y(pt.v).toFixed(1)).join(" ");
    paths += `<path d="${d}" fill="none" stroke="${o.color || '#6ac7e8'}" stroke-width="2"
                    stroke-linejoin="round" stroke-linecap="round"/>`;
    // A soft fill under the line, clipped to this run only.
    const area = d + ` L ${x(r[r.length-1].i).toFixed(1)} ${y(lo).toFixed(1)}`
               + ` L ${x(r[0].i).toFixed(1)} ${y(lo).toFixed(1)} Z`;
    paths += `<path d="${area}" fill="${o.color || '#6ac7e8'}" opacity="0.10"/>`;
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
  // Now each column reports through one shared readout above the chart, with a
  // marker line and a dot on the point. It appears instantly, follows the
  // pointer, and says the date and the value.
  //
  // The handlers are inline attributes on purpose: this HTML is built as a
  // string and inserted with innerHTML, so there is no element to bind to until
  // after it is in the document, and a later querySelectorAll pass would have to
  // be re-run on every redraw.
  const cid = o.id || ("c" + Math.abs(_scHash(String(o.title || "") + points.length)));
  let hits = "";
  points.forEach(function(p, i){
    const half = points.length > 1 ? iw / (points.length - 1) / 2 : iw / 2;
    const v = _scNum(p.value);
    const shown = (v === null ? "no data yet" : _scFmt(v, o.kind));
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
  hits = `<line id="${cid}_vl" x1="0" y1="${padT}" x2="0" y2="${padT + ih}"
                stroke="#6ac7e8" stroke-width="1" opacity="0"/>`
       + `<circle id="${cid}_dot" cx="0" cy="0" r="3.5" fill="${o.color || '#6ac7e8'}"
                 opacity="0"/>`
       + `<rect id="${cid}_sel" x="0" y="${padT}" width="0" height="${ih}"
                fill="#6ac7e8" opacity="0.14" pointer-events="none"/>`
       + hits;

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
       + '<div class="cc" style="font-size:10px;margin:-2px 0 5px;opacity:.65">'
       + 'Hover for the day’s figure · drag across to zoom into those days</div>'
       // NOT preserveAspectRatio="none". That stretched the viewBox horizontally
       // to whatever the container was and left the vertical scale at 1, so every
       // axis label, date and tooltip was squashed or smeared by however wide the
       // panel happened to be -- and the line's stroke thickened in one direction
       // only. Scaling uniformly costs a taller chart on a wide screen and makes
       // the text legible at every width, including on a phone.
       + `<svg viewBox="0 0 ${W} ${H}" width="100%"
               style="display:block;height:auto;background:#0d1220;
                      border:1px solid #1e2733;border-radius:8px">`
       + grid + gaps + paths + dots + xl + hits + '</svg></div>';
}
