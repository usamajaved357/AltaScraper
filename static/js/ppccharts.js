/* static/js/ppccharts.js -- the charts on the three advertising screens.
 *
 * Drawn to the mockups rather than through salesCombo. The Sales page's chart
 * is a different drawing with different rules -- 1365x320, its own padding, its
 * own legend, its own hover card -- and bending it into Orbit's shape would have
 * meant changing it for the Sales page too. These are small, self-contained SVG
 * builders that take the mockup's numbers literally:
 *
 *     grid            strokeDasharray "3 3" in --ppc-border
 *     axis ticks      9-10px in --ppc-dim
 *     bars            --ppc-gold at 0.65 opacity, 24 wide, 2px top corners
 *     lines           2px, no dots
 *     area gradient   the line's colour, 0.25 at the top fading to 0
 *     reference line  dashed "6 4"
 *
 * A GAP IS A GAP. A day the server sent None for is not a day of zero spend,
 * and every path here breaks rather than drawing down to the floor and back.
 * That distinction is the whole reason these screens exist in the shape they do.
 */

let _PPCC_ID = 0;

function _ppcId(p){ return "ppcc" + p + (++_PPCC_ID); }

function _ppcNum(v){
  if(v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

/* A round-ish upper bound, so the axis reads 0 / 5k / 10k rather than 0 / 4,317.
 * Same intent as the Sales chart's _scNiceMax; kept local because these charts
 * do not otherwise depend on that file. */
function _ppcNice(max){
  if(!(max > 0)) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(max)));
  const n = max / mag;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * mag;
}

function _ppcMoneyTick(v, cur){
  const sym = (cur === "USD") ? "$" : (cur === "EUR") ? "€" : "£";
  const a = Math.abs(v);
  if(a >= 1000) return sym + (v / 1000).toFixed(a >= 10000 ? 0 : 1) + "k";
  if(a >= 1 || a === 0) return sym + Math.round(v);
  return sym + v.toFixed(2);
}

/* How many x labels fit, so 30 dates do not overprint each other. */
function _ppcEvery(n, room){
  const per = Math.max(1, Math.ceil(n / Math.max(1, Math.floor(room / 52))));
  return per;
}

/* ---- bars + lines, on one money axis --------------------------------------
 *
 * The mockup's "Revenue, Ad Spend & Profitability" and "Budget & Pacing": gold
 * bars behind, two or one 2px lines over, dashed grid, dollars on the left.
 */
function ppcComposed(o){
  const cols = o.columns || [];
  if(!cols.length) return "";
  const W = 1120, H = o.height || 300;
  const padL = 58, padR = 16, padT = 12, padB = 34;
  const iw = W - padL - padR, ih = H - padT - padB;
  const cur = o.currency || "GBP";

  const bars = (o.bars && o.bars.values) ? o.bars.values.map(_ppcNum) : null;
  const lines = (o.lines || []).map(function(l){
    return {colour: l.colour, values: (l.values || []).map(_ppcNum),
            label: l.label};
  });

  // ONE AXIS, from every visible series. The mockup puts revenue, spend and
  // profit on the same money axis, and so does this -- they are all money and
  // the comparison between them is the point.
  const all = [];
  if(bars) bars.forEach(function(v){ if(v !== null) all.push(v); });
  lines.forEach(function(l){
    l.values.forEach(function(v){ if(v !== null) all.push(v); });
  });
  if(!all.length) return "";
  let lo = Math.min(0, Math.min.apply(null, all));
  let hi = _ppcNice(Math.max.apply(null, all));
  if(hi === lo) hi = lo + 1;
  const span = hi - lo;
  const x = function(i){
    return padL + (cols.length === 1 ? iw / 2
                   : (i / (cols.length - 1)) * iw);
  };
  const y = function(v){ return padT + ih - ((v - lo) / span) * ih; };

  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" '
    + 'style="width:100%;height:auto" preserveAspectRatio="xMidYMid meet">';

  // grid + y labels
  for(let i = 0; i <= 4; i++){
    const v = lo + span * i / 4, yy = y(v);
    svg += '<line x1="' + padL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - padR)
      + '" y2="' + yy.toFixed(1) + '" stroke="var(--ppc-border)" '
      + 'stroke-width="1" stroke-dasharray="3 3"/>'
      + '<text x="' + (padL - 8) + '" y="' + (yy + 3.5).toFixed(1)
      + '" text-anchor="end" font-size="10" fill="var(--ppc-dim)">'
      + _ppcMoneyTick(v, cur) + '</text>';
  }

  // bars first, so the lines sit over them
  if(bars){
    const bw = Math.max(3, Math.min(24, (iw / Math.max(1, cols.length)) * 0.6));
    const zero = y(Math.max(lo, 0));
    bars.forEach(function(v, i){
      if(v === null) return;
      const top = y(v), h = Math.max(0, zero - top);
      if(h <= 0) return;
      svg += '<rect x="' + (x(i) - bw / 2).toFixed(1) + '" y="' + top.toFixed(1)
        + '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1)
        + '" rx="2" fill="' + (o.bars.colour || "var(--ppc-gold)")
        + '" opacity="0.65"/>';
    });
  }

  // reference lines, dashed 6 4, labelled at the edge
  (o.refLines || []).forEach(function(r){
    const v = _ppcNum(r.value);
    if(v === null || v < lo || v > hi) return;
    const yy = y(v);
    svg += '<line x1="' + padL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - padR)
      + '" y2="' + yy.toFixed(1) + '" stroke="' + r.colour
      + '" stroke-width="1" stroke-dasharray="6 4"/>'
      + '<text x="' + (r.side === "right" ? (W - padR - 4) : (padL + 4))
      + '" y="' + (yy - 5).toFixed(1) + '" text-anchor="'
      + (r.side === "right" ? "end" : "start")
      + '" font-size="10" fill="' + r.colour + '">' + r.label + '</text>';
  });

  // lines, broken across gaps
  lines.forEach(function(l){
    let d = "", pen = false;
    l.values.forEach(function(v, i){
      if(v === null){ pen = false; return; }
      d += (pen ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1) + " ";
      pen = true;
    });
    if(d) svg += '<path d="' + d.trim() + '" fill="none" stroke="' + l.colour
      + '" stroke-width="2" stroke-linejoin="round"/>';
  });

  // x labels, as many as fit
  const every = _ppcEvery(cols.length, iw);
  cols.forEach(function(c, i){
    if(i % every) return;
    svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 12)
      + '" text-anchor="middle" font-size="10" fill="var(--ppc-dim)">'
      + _pEsc(String(c).slice(5)) + '</text>';
  });

  return svg + '</svg>';
}

/* ---- an area with a gradient shadow ---------------------------------------
 *
 * The mockup's TrendWithShadow: a 2px line, the area beneath fading from 0.25
 * to nothing, a dashed reference line, its own y format. Used for Profit per
 * Click, Efficiency Score and TACoS Over Time.
 */
function ppcArea(o){
  const cols = o.columns || [];
  const vals = (o.values || []).map(_ppcNum);
  const known = vals.filter(function(v){ return v !== null; });
  if(!cols.length || known.length < 1) return "";
  const W = 700, H = o.height || 200;
  const padL = 52, padR = 14, padT = 10, padB = 30;
  const iw = W - padL - padR, ih = H - padT - padB;
  const id = _ppcId("grad");

  let lo, hi;
  if(o.yDomain){ lo = o.yDomain[0]; hi = o.yDomain[1]; }
  else{
    lo = Math.min.apply(null, known);
    hi = Math.max.apply(null, known);
    if(lo > 0) lo = 0;
    hi = _ppcNice(hi || 1);
  }
  if(hi === lo) hi = lo + 1;
  const span = hi - lo;
  const x = function(i){
    return padL + (cols.length === 1 ? iw / 2 : (i / (cols.length - 1)) * iw);
  };
  const y = function(v){
    return padT + ih - ((Math.max(lo, Math.min(hi, v)) - lo) / span) * ih;
  };
  const fmt = o.yFormat || function(v){ return String(Math.round(v)); };

  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" '
    + 'style="width:100%;height:auto" preserveAspectRatio="xMidYMid meet">'
    + '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0%" stop-color="' + o.colour + '" stop-opacity="0.25"/>'
    + '<stop offset="100%" stop-color="' + o.colour + '" stop-opacity="0"/>'
    + '</linearGradient></defs>';

  for(let i = 0; i <= 4; i++){
    const v = lo + span * i / 4, yy = y(v);
    svg += '<line x1="' + padL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - padR)
      + '" y2="' + yy.toFixed(1) + '" stroke="var(--ppc-border)" '
      + 'stroke-width="1" stroke-dasharray="3 3"/>'
      + '<text x="' + (padL - 8) + '" y="' + (yy + 3.5).toFixed(1)
      + '" text-anchor="end" font-size="10" fill="var(--ppc-dim)">'
      + _pEsc(fmt(v)) + '</text>';
  }

  if(o.refLineY !== undefined && o.refLineY >= lo && o.refLineY <= hi){
    const yy = y(o.refLineY);
    svg += '<line x1="' + padL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - padR)
      + '" y2="' + yy.toFixed(1) + '" stroke="var(--ppc-green)" '
      + 'stroke-width="1" stroke-dasharray="6 4"/>';
  }

  // The filled area is drawn only across RUNS of real values, so a gap leaves
  // a gap rather than a wedge down to the axis.
  let run = [];
  const flush = function(){
    if(run.length < 2){ run = []; return; }
    let d = "";
    run.forEach(function(p, i){
      d += (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1) + " ";
    });
    const base = y(Math.max(lo, 0));
    svg += '<path d="' + d + "L" + run[run.length - 1][0].toFixed(1) + ","
      + base.toFixed(1) + " L" + run[0][0].toFixed(1) + "," + base.toFixed(1)
      + ' Z" fill="url(#' + id + ')"/>'
      + '<path d="' + d.trim() + '" fill="none" stroke="' + o.colour
      + '" stroke-width="2" stroke-linejoin="round"/>';
    run = [];
  };
  vals.forEach(function(v, i){
    if(v === null){ flush(); return; }
    run.push([x(i), y(v)]);
  });
  flush();

  const every = _ppcEvery(cols.length, iw);
  cols.forEach(function(c, i){
    if(i % every) return;
    svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10)
      + '" text-anchor="middle" font-size="9" fill="var(--ppc-dim)">'
      + _pEsc(String(c).slice(5)) + '</text>';
  });
  return svg + '</svg>';
}

/* ---- stacked areas ---------------------------------------------------------
 *
 * The campaign screen's SP-over-SB chart: each series filled at 0.25 of its own
 * colour with a 2px line on top, stacked, and NO vertical grid lines -- the
 * mockup turns those off and it is why the shape reads as one mass rather than
 * a grid with something in it.
 *
 * A day missing from EVERY series is a gap. A day missing from one series but
 * present in another is a real zero for that series: the stack is only
 * meaningful if every layer has a floor to sit on, and a hole in the middle of
 * a stack cannot be drawn honestly at all.
 */
function ppcStackedArea(o){
  const cols = o.columns || [];
  const series = (o.series || []).map(function(s){
    return {colour: s.colour, label: s.label,
            values: (s.values || []).map(_ppcNum)};
  });
  if(!cols.length || !series.length) return "";

  // Which columns have anything at all. Everything else is left blank.
  const live = cols.map(function(_c, i){
    return series.some(function(s){ return s.values[i] !== null; });
  });
  if(!live.some(Boolean)) return "";

  const W = 1120, H = o.height || 280;
  const padL = 52, padR = 14, padT = 12, padB = 30;
  const iw = W - padL - padR, ih = H - padT - padB;
  const cur = o.currency || "GBP";

  // Cumulative tops, per column.
  const tops = cols.map(function(_c, i){
    if(!live[i]) return null;
    let run = 0;
    return series.map(function(s){
      run += (s.values[i] || 0);
      return run;
    });
  });
  const maxes = tops.filter(Boolean).map(function(t){ return t[t.length - 1]; });
  const hi = _ppcNice(maxes.length ? Math.max.apply(null, maxes) : 1) || 1;
  const x = function(i){
    return padL + (cols.length === 1 ? iw / 2 : (i / (cols.length - 1)) * iw);
  };
  const y = function(v){ return padT + ih - (v / hi) * ih; };

  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" '
    + 'style="width:100%;height:auto" preserveAspectRatio="xMidYMid meet">';

  // HORIZONTAL GRID ONLY. The mockup sets vertical={false}.
  for(let i = 0; i <= 4; i++){
    const v = hi * i / 4, yy = y(v);
    svg += '<line x1="' + padL + '" y1="' + yy.toFixed(1) + '" x2="' + (W - padR)
      + '" y2="' + yy.toFixed(1) + '" stroke="var(--ppc-border)" '
      + 'stroke-width="1" stroke-dasharray="3 3"/>'
      + '<text x="' + (padL - 8) + '" y="' + (yy + 3.5).toFixed(1)
      + '" text-anchor="end" font-size="10" fill="var(--ppc-dim)">'
      + _ppcMoneyTick(v, cur) + '</text>';
  }

  // Painted from the top layer down, so a lower band is not hidden by the one
  // above it.
  for(let si = series.length - 1; si >= 0; si--){
    let d = "", pen = false, first = -1, last = -1;
    cols.forEach(function(_c, i){
      if(!live[i]){ pen = false; return; }
      if(first < 0) first = i;
      last = i;
      d += (pen ? "L" : "M") + x(i).toFixed(1) + ","
         + y(tops[i][si]).toFixed(1) + " ";
      pen = true;
    });
    if(first < 0) continue;
    const floor = y(0);
    svg += '<path d="' + d + "L" + x(last).toFixed(1) + "," + floor.toFixed(1)
      + " L" + x(first).toFixed(1) + "," + floor.toFixed(1) + ' Z" fill="'
      + series[si].colour + '" fill-opacity="0.25"/>'
      + '<path d="' + d.trim() + '" fill="none" stroke="' + series[si].colour
      + '" stroke-width="2" stroke-linejoin="round"/>';
  }

  const every = _ppcEvery(cols.length, iw);
  cols.forEach(function(c, i){
    if(i % every) return;
    svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10)
      + '" text-anchor="middle" font-size="10" fill="var(--ppc-dim)">'
      + _pEsc(String(c).slice(5)) + '</text>';
  });
  return svg + '</svg>';
}

/* ---- the donut ------------------------------------------------------------
 *
 * 170x170, inner 48, outer 75, no stroke -- the mockup's branded/non-branded
 * ring. Refuses to draw on a total of zero rather than showing a full circle of
 * the first colour, which would read as "all of it is branded".
 */
function ppcDonut(segments, size){
  const segs = (segments || []).filter(function(s){ return Number(s.value) > 0; });
  const total = segs.reduce(function(a, s){ return a + Number(s.value); }, 0);
  if(!total) return "";
  const S = size || 170, cx = S / 2, cy = S / 2;
  const rOut = S * 0.441, rIn = S * 0.282;   // 75 and 48 at S=170
  let a0 = -Math.PI / 2, svg = '<svg viewBox="0 0 ' + S + ' ' + S
    + '" style="width:' + S + 'px;height:' + S + 'px;max-width:100%">';
  segs.forEach(function(s){
    const frac = Number(s.value) / total;
    const a1 = a0 + frac * Math.PI * 2;
    const big = (a1 - a0) > Math.PI ? 1 : 0;
    const p = function(r, a){
      return [(cx + r * Math.cos(a)).toFixed(2),
              (cy + r * Math.sin(a)).toFixed(2)];
    };
    // A single segment of the whole is a ring, and an arc cannot draw one --
    // the start and end points coincide and the path collapses.
    if(frac > 0.9999){
      svg += '<circle cx="' + cx + '" cy="' + cy + '" r="'
        + ((rOut + rIn) / 2).toFixed(2) + '" fill="none" stroke="' + s.colour
        + '" stroke-width="' + (rOut - rIn).toFixed(2) + '"/>';
    }else{
      const o0 = p(rOut, a0), o1 = p(rOut, a1);
      const i1 = p(rIn, a1), i0 = p(rIn, a0);
      svg += '<path d="M' + o0[0] + ',' + o0[1]
        + ' A' + rOut.toFixed(2) + ',' + rOut.toFixed(2) + ' 0 ' + big + ' 1 '
        + o1[0] + ',' + o1[1]
        + ' L' + i1[0] + ',' + i1[1]
        + ' A' + rIn.toFixed(2) + ',' + rIn.toFixed(2) + ' 0 ' + big + ' 0 '
        + i0[0] + ',' + i0[1] + ' Z" fill="' + s.colour + '">'
        + '<title>' + _pEsc(s.label + ": " + Math.round(frac * 100) + "%")
        + '</title></path>';
    }
    a0 = a1;
  });
  return svg + '</svg>';
}

/* ---- the heatmap ----------------------------------------------------------
 *
 * Day x hour, one 22px cell per hour, coloured by ACoS band. `grid` is
 * [7][24] of a colour or null; null draws nothing, which is how "no data for
 * that hour" is shown -- an empty cell rather than a green one.
 */
const PPC_HEAT_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const PPC_HEAT_HOURS = ["12a","1a","2a","3a","4a","5a","6a","7a","8a","9a","10a",
                        "11a","12p","1p","2p","3p","4p","5p","6p","7p","8p","9p",
                        "10p","11p"];

function ppcHeatmap(grid){
  let h = '<div style="overflow-x:auto"><table class="ppc-heat"><thead><tr>'
    + '<th style="width:36px"></th>';
  PPC_HEAT_HOURS.forEach(function(x){ h += '<th>' + x + '</th>'; });
  h += '</tr></thead><tbody>';
  PPC_HEAT_DAYS.forEach(function(day, di){
    h += '<tr><td class="day">' + day + '</td>';
    for(let hi = 0; hi < 24; hi++){
      const c = (grid && grid[di] && grid[di][hi]) || null;
      h += '<td><div class="cell" style="background:'
        + (c || "transparent") + '"></div></td>';
    }
    h += '</tr>';
  });
  h += '</tbody></table></div>'
    + '<div style="display:flex;gap:14px;margin-top:10px;font-size:11px;'
    + 'color:var(--ppc-muted)">'
    + [["var(--ppc-heat1)", "<26%"], ["var(--ppc-heat2)", "<35%"],
       ["var(--ppc-heat3)", "<43%"], ["var(--ppc-heat4)", ">43%"]]
      .map(function(l){
        return '<span style="display:flex;align-items:center;gap:4px">'
          + '<span style="width:12px;height:12px;border-radius:2px;background:'
          + l[0] + ';display:inline-block"></span>' + l[1] + '</span>';
      }).join("")
    + '</div>';
  return h;
}
