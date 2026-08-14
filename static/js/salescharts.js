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
  const W = o.width || 720, H = o.height || 170;
  const padL = 52, padR = 10, padT = 12, padB = 26;
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

  // Hover targets: one invisible column per point, carrying a native tooltip.
  let hits = "";
  points.forEach(function(p, i){
    const half = points.length > 1 ? iw / (points.length - 1) / 2 : iw / 2;
    const v = _scNum(p.value);
    hits += `<rect x="${Math.max(padL, x(i) - half)}" y="${padT}"
                   width="${Math.min(half * 2, iw)}" height="${ih}" fill="transparent">`
         +  `<title>${_scEsc(p.label)}: ${v === null ? "no data yet" : _scFmt(v, o.kind)}</title></rect>`;
  });

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
       + '</div>'
       // Every chart says where its numbers came from. Amazon has two feeds that
       // describe the same trade and they disagree for days at a time, so a
       // shape without its source is a shape you cannot act on.
       + (o.subtitle ? '<div class="cc" style="font-size:10.5px;margin:-1px 0 5px">'
                       + _scEsc(o.subtitle) + '</div>' : '')
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
