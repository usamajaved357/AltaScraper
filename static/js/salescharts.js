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

/* HOW WIDE THIS CHART SHOULD BE DRAWN -- the container's own width, measured.
 *
 * THE BUG THIS EXISTS FOR: "in the mobile view the graphs do not look as
 * original they are too short", and on desktop "the size of the graphs is not
 * the same as orbit" and "the graphs looks uneven".
 *
 * All three are the same fault. The charts were drawn at a fixed viewBox with
 * `width:100%; height:auto`, which scales the picture UNIFORMLY: halve the
 * width and the height halves with it.
 *
 * MEASURED on Orbit at 1600px and at 390px:
 *
 *                        desktop        phone
 *   Live Sales           665 x 200      340 x 200
 *   Week to Date         665 x 200      340 x 200
 *   Sales Report        1365 x 320      340 x 320
 *   Organic vs PPC      1365 x 380      332 x 380
 *
 * Its charts KEEP THEIR HEIGHT and only lose width -- the plot re-lays-out
 * narrower, it does not shrink. Ours at 340 wide became 340 x 102, which is the
 * "too short" exactly. On desktop the same scaling made every chart taller than
 * Orbit's on a wide screen, and made two side-by-side cards disagree in height
 * whenever their widths differed by a pixel, which is the "uneven".
 *
 * So the width comes from the element the chart is going into, and the height is
 * whatever the caller asked for. Falls back to Orbit's own width when the host
 * cannot be measured (it is hidden, or this is a test with no layout).
 */
function scChartWidth(hostId, fallback){
  try{
    const el = document.getElementById(hostId);
    const w = el && (el.clientWidth || el.getBoundingClientRect().width);
    // Under about 240 there is no room for a y-axis and 30 dates; below that the
    // fallback reads better than a squashed picture.
    if(w && w >= 240) return Math.round(w);
  }catch(e){}
  return fallback;
}

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

/* WHICH SCREEN A DRAG ON THIS CHART ZOOMS.
 *
 * salesChart() is shared -- Sales, Traffic and AI spend all draw with it -- so
 * every one of those charts got the drag hit-targets, and _scDragEnd sent all
 * of them to salesZoomTo(). Dragging across the Traffic chart therefore read
 * ITS column numbers as offsets into the SALES screen's dates and quietly
 * reloaded a screen you were not looking at. The AI spend page even advertises
 * "drag across to zoom into those days" under a chart where the gesture did
 * nothing visible at all.
 *
 * A chart now names its own handler. The registry is by chart id, so two charts
 * on one page zoom independently, and a chart that names none still falls back
 * to salesZoomTo -- which is what the Sales screen has always relied on.
 */
const _SC_ZOOM = {};

function scZoomTarget(cid, fnName){
  // Cleared, not left stale: a chart id reused by another screen must not
  // inherit the previous screen's zoom.
  if(fnName) _SC_ZOOM[cid] = fnName;
  else delete _SC_ZOOM[cid];
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
  // OPT IN, NEVER A FALLBACK. A chart zooms only if it named a handler, because
  // "zoom whatever the Sales screen is showing" is wrong for every chart whose
  // columns are not those dates -- and two of them are not: the week card draws
  // seven days of its own, and Today draws twenty-four HOURS. Dragging 9am-2pm
  // across the hourly chart used to zoom the whole screen to the 9th-14th day
  // of the range, which looks like a feature doing something and is nonsense.
  const named = _SC_ZOOM[cid];
  const fn = named ? window[named] : null;
  if(typeof fn === "function") fn(a, b, cid);
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
/* ACROSS A GAP, A DASHED CONNECTOR -- so a sparse line reads as one line.
 *
 * "the lines dont join for profit on the salesreport graph", and before that
 * "the profit lines do not appears on the graph it just show a dot".
 *
 * Profit is known only on days where every unit shipped has a cost recorded, so
 * on these accounts it is eight days out of ninety. Eight separate one-point
 * runs draw as eight unconnected dots, which reads as a broken chart rather
 * than as a sparse measurement.
 *
 * Drawing a SOLID line across would say the profit passed through those days at
 * those values, and it is not known that it did. So the gap is bridged dashed,
 * thin and faded: the eye follows one series, and the stretch that was never
 * measured is visibly not the same as the stretch that was. The grey "no data"
 * shading behind it still marks those days.
 *
 * ONE implementation. Both charts on this screen build runs the same way and
 * both had their own copy of the break-at-gaps rule; the join belongs in one
 * place or only one of them will ever have it -- which is exactly what happened
 * the first time this was fixed.
 */
function _scGapJoin(runs, x, y, colour){
  let out = "";
  for(let g = 1; g < (runs || []).length; g++){
    const a = runs[g - 1][runs[g - 1].length - 1];
    const b = runs[g][0];
    if(!a || !b) continue;
    out += `<path class="series" d="M ${x(a.i).toFixed(1)} ${y(a.v).toFixed(1)}`
         + ` L ${x(b.i).toFixed(1)} ${y(b.v).toFixed(1)}" fill="none"`
         + ` stroke="${colour}" stroke-width="1.2" stroke-dasharray="3,4"`
         + ` opacity="0.55" stroke-linecap="round"/>`;
  }
  return out;
}

/* A DAY THAT IS THE WHOLE MEASUREMENT, drawn as one.
 *
 * "check the profit lines on the graph of daily sales, that is not how the
 *  lines are drawn in other places"
 *
 * Profit is known only on days where every unit shipped has a cost recorded --
 * on jack_uk that is five days out of thirty, none of them next to each other.
 * So EVERY run is a single point, no solid stroke is ever drawn, and the only
 * blue on the chart is the dashed bridge between them. Measured in the browser:
 * four #38bdf8 paths, all 1.2px, dash 3,4, opacity 0.55, and not one solid
 * segment. Beside Sales -- a confident 2px line with a gradient under it -- the
 * profit series read as something faint and provisional, when those five points
 * are as measured as any point on the green line.
 *
 * The dashes are RIGHT and stay: the app does not know what the profit was on
 * the days in between, and a solid line would claim it did. What was wrong is
 * that the measured days looked like nothing. A 2.6px dot in the series colour
 * sits on a grid of 1px lines and reads as grid.
 *
 * So a lone point gets a ring in its own colour. No background colour is
 * involved -- a halo painted in the panel's grey would be wrong the moment this
 * chart sat on anything else.
 */
function _scLonePoint(px, py, colour){
  const cx = px.toFixed(1), cy = py.toFixed(1);
  return `<circle cx="${cx}" cy="${cy}" r="6" fill="${colour}" opacity="0.18"/>`
       + `<circle cx="${cx}" cy="${cy}" r="3.2" fill="${colour}"/>`;
}

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
/* THE BAND AROUND ONE POINT, KEPT INSIDE THE PLOT.
   Three places drew this band -- the missing-data shading and two hover strips
   -- and all three clamped the LEFT edge and the WIDTH but never the RIGHT one.
   For the last point on a chart that means x + width lands past the plot area,
   and MEASURED in a browser it overshot the SVG by 6px at 1920 and 3px at 1536:
   a sliver of chart drawn outside its own frame and clipped away.
   Small, but it is exactly the class of thing reported as "the page cutting my
   visuals", and three copies of a clamp that was wrong in the same way is what
   Rule 12 is about. Returns {x, w}. */
function _scBand(centre, half, padL, iw){
  const left  = Math.max(padL, centre - half);
  const right = Math.min(padL + iw, centre + half);
  return { x: left, w: Math.max(0, right - left) };
}
/* A value as it appears in the READOUT -- the hover card, where the exact
   figure is what is wanted. */
function _scFmt(v, kind){
  if(v===null) return "—";
  if(kind === "money") return Number(v).toFixed(2);
  if(kind === "pct")   return Number(v).toFixed(1) + "%";
  return String(Math.round(v));
}

/* A value as it appears on an AXIS, which is a different job.
 *
 * Orbit's y-axis reads "$28.0k", "$21.0k", "$0" -- measured. Ours read
 * "28000.00", so five gridline labels took three times the width and the eye
 * had to parse a decimal on every one. An axis is scanned, not read: it wants
 * the magnitude and nothing else.
 *
 * The exact figure is never lost -- it is in the hover card and in the grid
 * below, both to the penny. */
// Was a private copy of the currency map that rendered CAD and AUD both as
// "$". One map now, in static/js/money.js (CLAUDE.md Rule 12). Read through a
// getter rather than captured at load, so the order of the script tags cannot
// silently empty it -- which is exactly what happened to weekly.js.
function _scCur(code){
  return (typeof curSymbol === "function") ? curSymbol(code) : "";
}

/* `span` is the height of the whole axis, and it is what decides the number of
 * decimals -- NOT the individual value. Deciding per value gave one axis reading
 * "£0, £5.0, £10, £15, £20": five ticks in three different formats, because 5
 * fell under the "small, so show a decimal" rule and 10 did not. An axis is one
 * scale and has to be written one way. Two ticks that round to the same string
 * are the same failure the count axis had, so a short span keeps its decimals. */
function _scAxis(v, kind, currency, span){
  if(v === null || v === undefined) return "";
  const n = Number(v);
  if(!isFinite(n)) return "";
  if(kind === "pct") return n.toFixed(0) + "%";
  const sym = (kind === "money") ? (_scCur(currency) || "£") : "";
  if(n === 0) return sym + "0";               // "£0", never "£0.0k"
  const sc = Math.abs(Number(span)) || Math.abs(n);
  if(sc >= 1e6) return sym + (n / 1e6).toFixed(1) + "m";
  // Thousands only once the whole axis is comfortably in them. At a span of
  // 2,500 the shortened form reads "£0.6k" for 625 -- one significant figure,
  // which throws away the number the axis exists to give.
  if(sc >= 1e4) return sym + (n / 1000).toFixed(1) + "k";
  const dp = sc >= 20 ? 0 : sc >= 2 ? 1 : 2;
  return sym + n.toFixed(dp).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/* "Jul 15", not "07-15". Orbit labels its x-axis the way a person says a date,
   and a hyphenated pair reads as a code rather than a day. */
const SC_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"];

function _scDay(label){
  const s = String(label || "");
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if(!m) return s;                        // already a word, or an hour
  return SC_MONTHS[Number(m[2]) - 1] + " " + Number(m[3]);
}

/* THE WEEK CHART NAMES ITS DAYS. Measured off Orbit's Week to Date: its x-axis
 * reads Sun, Mon, Tue, Wed, Thu, Fri, Sat -- seven labels, one per day. Ours
 * read "Aug 9 … Aug 15", which is the same information in the form you would
 * use to file it rather than the form you would say it. On a chart of ONE week
 * the date adds nothing: the week is already established by the panel title,
 * and what is being looked for is which DAY was strong. */
const SC_DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

function _scDow(label){
  const s = String(label || "");
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if(!m) return s;
  // Built in UTC because the labels are UTC dates. A local-time Date would
  // shift the day backwards for anyone east of Greenwich, so Monday's column
  // would be captioned Sunday -- which is worse than a bare date.
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return isNaN(d) ? s : SC_DOW[d.getUTCDay()];
}

function _scXLabel(label, mode){
  return (mode === "dow") ? _scDow(label) : _scDay(label);
}

// A "nice" top-of-axis, so the labels are round numbers rather than 3847.219.
function _scNiceMax(v){
  if(!v || v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

/* A COUNT AXIS IS NOT A MONEY AXIS, and treating it as one is the bug behind
 * "where i have 1 order the pillar rise upto 50".
 *
 * The bars are scaled against their own top value. _scNiceMax(1) is 1, so a day
 * with ONE order drew a bar the full height of the chart -- and if every day had
 * one order, every bar was full height and identical, which is exactly what a
 * hard-coded picture looks like. The right-hand axis was worse: the five ticks
 * came out 0, 0, 1, 1, 1, because quarters of 1 were being rounded for display.
 *
 * A count has no halves. So the STEP is what gets rounded, not the labels: pick
 * a whole-number step of at least 1 and put the top of the axis four steps up.
 * One order against a 0-1-2-3-4 axis is a quarter-height bar, and the axis says
 * so.
 *
 * The ladder includes 4 because Orbit's does. Measured on its Sales Report: a
 * peak of ~106 orders gives ticks 0, 40, 80, 120, 160 -- a step of 40, which
 * only comes out of a ladder with 4 in it (106/4 = 26.5 -> 40). A ladder of
 * 1/2/2.5/5/10 would have chosen 50 and a top of 200.
 */
function _scNiceStep(v){
  if(!v || v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / mag;
  const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 4 ? 4 : n <= 5 ? 5 : 10) * mag;
  return step;
}

function _scNiceCount(v){
  const top = Math.max(1, Math.ceil(Number(v) || 0));
  const step = Math.max(1, Math.round(_scNiceStep(top / 4)));
  return step * 4;
}

/* WHERE COLUMN i SITS. Two answers, and Orbit uses both -- measured:
 *
 *   point   Live Sales. 24 hourly points, the first ON the y-axis at x=65 and
 *           the last on the right edge at x=645. Correct for a continuous run of
 *           readings: midnight IS the start of the axis.
 *
 *   band    Week to Date, and every chart with bars. Each column occupies a
 *           slice of the axis and is drawn at the middle of its slice (measured
 *           on the Sales Report: 30 days across a plot from 70 to 1274.9, so
 *           bands of 40.17, and bar centre, line point and date label all meet
 *           at 90.08).
 *
 * A day is a bucket and a bucket wants a band. It is also what stops the last
 * bar hanging half its width into the right-hand axis labels.
 *
 * ONE definition, used by both charts. It was the same arithmetic written out
 * twice, which is how the two came to disagree about where a column is in the
 * first place. */
function _scScale(band, padL, iw, n){
  const count = Math.max(1, n);
  const slot = band ? (iw / count) : (count > 1 ? iw / (count - 1) : iw);
  return {
    slot: slot,
    x: band ? (i => padL + (i + 0.5) * slot)
            : (i => padL + (count === 1 ? iw / 2 : i * slot)),
  };
}

/* A BAR WITH ROUNDED TOP CORNERS ONLY, which is what Orbit draws: measured
 * `radius=4,4,0,0` on every rectangle of its Sales Report. A plain rect with
 * rx rounds all four, and the two at the bottom get clipped by the axis into a
 * shape that reads as a rendering fault. */
function _scBarPath(x, y, w, h, r){
  const f = v => (Math.round(v * 100) / 100);
  const rr = Math.max(0, Math.min(r, w / 2, h));
  if(h <= 0) return "";
  return "M" + f(x) + "," + f(y + rr)
       + "A" + f(rr) + "," + f(rr) + ",0,0,1," + f(x + rr) + "," + f(y)
       + "L" + f(x + w - rr) + "," + f(y)
       + "A" + f(rr) + "," + f(rr) + ",0,0,1," + f(x + w) + "," + f(y + rr)
       + "L" + f(x + w) + "," + f(y + h)
       + "L" + f(x) + "," + f(y + h) + "Z";
}

// One chart. `points` is [{label, value}] with value === null meaning NO DATA --
// which is drawn as a break, never as zero.
function salesChart(points, opts){
  const o = opts || {};
  // BIGGER, and taller relative to its width. At 720x170 in a three-across grid
  // a chart was a couple of centimetres of squiggle -- too small to read a shape
  // off, which is the only reason to draw one. Fewer, larger charts beat more,
  // smaller ones.
  // ORBIT'S GEOMETRY, RE-MEASURED off the live Live Sales and Week to Date
  // cards on 15 Aug 2026 (tools captured in the job scratch as orbit_bars4):
  //
  //   svg        665 x 200   -- the earlier note said 597, taken from a narrower
  //                             scan. At 1600px both top cards report a 665-wide
  //                             viewBox, and the ratio is what decides whether
  //                             the same numbers read as the same shape.
  //   plot area  580 x 160   -- gridlines at y = 165, 125, 85, 45, 5, so the
  //                             top is 5 and the bottom 165
  //   padding    left 65, top 5, right 20, bottom 35
  //
  // The left padding is what the money labels need and the bottom is what the
  // dates need; the top is deliberately almost nothing, so the line uses the
  // full height of the panel.
  const W = o.width || 665, H = o.height || 200;
  const padL = 65, padR = 20, padT = 5, padB = 35;
  const iw = W - padL - padR, ih = H - padT - padB;
  const vals = points.map(p => _scNum(p.value)).filter(v => v !== null);

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

  // A CHART IS STILL DRAWN WHEN ONLY THE COMPARISON IS KNOWN.
  //
  // This gave up on `!vals.length` alone, before the comparison had even been
  // read -- so a period whose own days are not in yet lost its whole card, even
  // with last week sitting there fully measured and ready to draw. That is the
  // fault the Week to Date card was already reported for, twice:
  //
  //     "week to date graph is shown as empty to me on jack reacherd"
  //     "even i dont have any sales the graph should be displayed"
  //
  // and it came back the moment un-fetched days stopped being drawn as zero
  // (see _drop_padding in domain/sales_data.py). Both series share one scale
  // already, and the main line is drawn as separate runs between the gaps -- so
  // with every current value null there is simply no gold line, the dashed
  // comparison draws, and the axis comes from it. Nothing extra is needed below.
  //
  // AND THE SENTENCE DOES NOT SAY "NOTHING" ABOUT DAYS NOBODY MEASURED. There
  // are two ways to have no line and they are different facts: no days at all
  // in the range, and days whose figures have not arrived. Saying "nothing in
  // this period yet" for the second is the same claim as plotting a zero.
  if(!vals.length && !cmpVals.length){
    const unknown = points.length > 0;
    return '<div class="cc" style="padding:18px;border:1px dashed var(--line2);border-radius:8px;'
         + 'font-size:12px">' + _scEsc(o.title || "")
         + (unknown
             ? ' — no figures for these ' + _scEsc((o.units || (o.unit || "day") + "s"))
               + ' yet. That is not the same as none.'
             : ' — nothing in this period yet.')
         + '</div>';
  }

  // BOTH SERIES SHARE ONE SCALE. They have to: two lines on separate scales
  // that cross each other say something that is not true, and the crossing is
  // the exact thing the eye reads first.
  const allVals = vals.concat(cmpVals);
  const lo = Math.min(0, Math.min.apply(null, allVals));
  const hi = _scNiceMax(Math.max.apply(null, allVals));
  const span = (hi - lo) || 1;

  // Band for the week (Sun … Sat measured at band centres, 82.86 apart), point
  // for the hourly card. See _scScale.
  const _sc = _scScale(o.scale === "band", padL, iw, points.length);
  const slot = _sc.slot, x = _sc.x;
  const y = v => padT + ih - ((v - lo) / span) * ih;

  // Gridlines and their labels, at nice fractions of the top value.
  // MEASURED: Orbit's gridlines are rgb(55,65,81) at 1px with a 3,3 dash, not a
  // solid rule, and there is an axis line along the bottom in the same colour.
  // Its tick text is 11px in rgb(156,163,175) at x = padL - 8; ours was 9.5px in
  // a darker grey, which is why the axis read as fainter and more cramped than
  // Orbit's at the same size.
  let grid = "";
  [0, 0.25, 0.5, 0.75, 1].forEach(function(f){
    const v = lo + span * f, yy = y(v);
    grid += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"
                   stroke="rgb(55,65,81)" stroke-width="1" stroke-dasharray="3 3"/>`
         +  `<text x="${padL - 8}" y="${yy + 4}" text-anchor="end" font-size="11"
                fill="rgb(156,163,175)">${_scEsc(_scAxis(v, o.kind, o.currency, span))}</text>`;
  });
  grid += `<line x1="${padL}" y1="${padT + ih}" x2="${W - padR}" y2="${padT + ih}"
                 stroke="rgb(55,65,81)" stroke-width="1"/>`;

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
  // Whose dates a drag across THIS chart narrows. Registered at draw time so it
  // travels with the chart rather than being decided inside the drag handler.
  scZoomTarget(cid0, o.onZoom);

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

  paths += _scGapJoin(runs, x, y, LINE);

  runs.forEach(function(r){
    if(r.length === 1){
      // ONE point is the whole measurement for that day -- see _scLonePoint.
      dots += _scLonePoint(x(r[0].i), y(r[0].v), LINE);
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
    const half = slot / 2;
    const _b = _scBand(x(i), half, padL, iw);
    gaps += `<rect x="${_b.x}" y="${padT}"
                   width="${_b.w}" height="${ih}"
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
    const half = slot / 2;
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
    const _hb = _scBand(x(i), half, padL, iw);
    hits += `<rect x="${_hb.x}" y="${padT}"
                   width="${_hb.w}" height="${ih}" fill="transparent"
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

  // X LABELS, as many as fit rather than a fixed seven.
  //
  // MEASURED on Orbit's two top cards: the week is labelled in full -- all seven
  // days, Sun to Sat -- and the hourly card every third hour, 75.65px apart, so
  // eight labels across 24 points. Both come out of one rule if the rule is a
  // minimum SPACING rather than a count: at 70px, seven days pass (82.9 apart)
  // and 24 hours thin to every third (75.7 apart). A fixed count either crowds a
  // long range or throws away labels a short one had room for.
  //
  // Nothing forces the last point to be labelled. Orbit's hourly axis stops at
  // 9 PM and leaves the last two hours unlabelled rather than squeezing one in
  // beside it, and a label that breaks the spacing is the one that collides.
  //
  // Its tick text is 11px in rgb(156,163,175), baseline at y = 173 on a 200-high
  // chart, which is 8px under the axis.
  let xl = "";
  const room = Math.max(1, Math.floor(iw / 70));
  const step = Math.max(1, Math.ceil(points.length / room));
  points.forEach(function(p, i){
    if(i % step) return;
    xl += `<text x="${x(i)}" y="${padT + ih + 8}" text-anchor="middle" font-size="11"
                 fill="rgb(156,163,175)">${_scEsc(_scXLabel(p.label, o.xLabel))}</text>`;
  });

  const missing = points.filter(p => _scNum(p.value) === null).length;

  // COMPACT is what the two top cards ask for, and it is a measured shape, not
  // a preference. Orbit's Week to Date card contains three things and nothing
  // else: the header row, the chart, the ad-spend footer. Between the header and
  // the chart there is NO subtitle, NO key, NO hint and NO inner panel -- the
  // chart is drawn straight onto the card.
  //
  // Ours stacked a missing-days note, a key and a hover hint in that gap and
  // then drew the chart inside its own bordered dark box, so the card was a box
  // inside a box with three lines of small print between them. That is most of
  // "week to date looks nothing like orbit", and none of it is about the line.
  //
  // Nothing is lost: the key and the note move up into the card's own header
  // beside the title (see salesChartKey, which the caller places), and the hover
  // gesture is announced once on the big chart below rather than on all three.
  const compact = !!o.compact;

  // WHAT ONE POINT IS CALLED, and why this is a parameter rather than the word
  // "day". This chart is drawn over day, week and month buckets -- the Sales
  // page switches between all three with its granularity picker, and the weekly
  // KPI trend is twelve weeks -- but the header said "day" in every case. So a
  // chart of twelve weeks announced "7 days not in from Amazon yet" and offered
  // "the day's figure" for a point that is a week.
  const unit = o.unit || "day";
  const units = o.units || (unit + "s");

  // WHY A POINT IS MISSING is also the caller's to say. "Not in from Amazon
  // yet" is true of a sales day near the end of a range, and false of a weekly
  // pack nobody uploaded -- that one is not late, it does not exist. Naming the
  // wrong reason is worse than naming none, because it tells the reader to wait
  // for something that is never coming.
  const why = o.missingNote || "not in from Amazon yet — shaded, not zero";
  const head = compact ? "" :
    ('<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:2px;flex-wrap:wrap">'
     + '<div style="font-size:12.5px;font-weight:600">' + _scEsc(o.title || "") + '</div>'
     + (missing ? '<span class="cc" style="font-size:10.5px">' + missing
                  + ' ' + _scEsc(missing === 1 ? unit : units) + ' '
                  + _scEsc(why) + '</span>' : '')
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
     // ONLY PROMISE THE GESTURE WHERE IT EXISTS. This line was printed under
     // every chart salesChart draws, including the ones that cannot zoom -- so
     // the AI spend page told you to drag across a chart where dragging moved
     // nothing you could see.
     + '<div class="cc" style="font-size:10px;margin:-2px 0 5px;opacity:.65">'
     + 'Hover for the ' + _scEsc(unit) + '’s figure'
     + (o.onZoom ? ' · drag across to zoom into those ' + _scEsc(units) : '')
     + '</div>');

  return '<div style="margin-bottom:' + (compact ? "0" : "14px") + '">'
       + head
       // NOT preserveAspectRatio="none". That stretched the viewBox horizontally
       // to whatever the container was and left the vertical scale at 1, so every
       // axis label, date and tooltip was squashed or smeared by however wide the
       // panel happened to be -- and the line's stroke thickened in one direction
       // only. Scaling uniformly costs a taller chart on a wide screen and makes
       // the text legible at every width, including on a phone.
       // position:relative so the floating hover card can be placed over the
       // chart in page pixels while the chart itself is drawn in viewBox units.
       + '<div style="position:relative">'
       // THE HEIGHT IS FIXED IN PIXELS and the viewBox is drawn at the width the
       // container actually has, so the scale is 1:1 and nothing is shrunk. With
       // `height:auto` this scaled uniformly and a 340px phone got a 102px-tall
       // chart -- see scChartWidth for the measurements.
       + `<svg id="${cid}_svg" class="chartbox" viewBox="0 0 ${W} ${H}" width="100%"
               style="display:block;height:${H}px;${compact
                 ? "background:transparent;border:0"
                 : "background:var(--sidebar);border:1px solid var(--line2);border-radius:8px"}">`
       + defs + grid + gaps + paths + dots + xl + hits + '</svg>'
       + `<div id="${cid}_tip" class="charttip"></div>`
       + '</div></div>';
}

/* THE KEY, ON ITS OWN, so a card can put it where Orbit puts it: in the header
 * row, right-aligned, beside the change badge. Measured on Orbit's Week to Date:
 * "This Week" and "Last Week" at 12px, then the percentage badge, all three on
 * the title's own line.
 *
 * Same arguments as salesChart, so the two cannot describe different lines. */
function salesChartKey(o){
  const opt = o || {};
  const isYear = (opt.compareKind === "year");
  const LINE = opt.color || SC_GOLD;
  const cCol = isYear ? SC_PRIORYEAR : SC_COMPARE;
  const mark = function(col, w, dash){
    return '<svg width="16" height="6" style="flex:none"><line x1="0" y1="3" x2="16" y2="3"'
         + ' stroke="' + col + '" stroke-width="' + w + '"'
         + (dash ? ' stroke-dasharray="' + dash + '"' : "") + '/></svg>';
  };
  const item = function(col, w, dash, text, dim, tip){
    return '<span style="display:inline-flex;align-items:center;gap:5px;font-size:12px'
         + (dim ? ';color:rgb(156,163,175)' : '') + '"'
         + (tip ? ' title="' + _scEsc(tip) + '"' : "") + '>'
         + mark(col, w, dash) + _scEsc(text) + '</span>';
  };
  let out = item(LINE, 2, "", opt.thisLabel || "This period", false, opt.thisTitle);
  if(opt.compare){
    // WHICH DAYS THE DASHED LINE ACTUALLY COVERS. "Last Week" is Orbit's caption
    // and it is what the card shows, but a comparison whose dates cannot be
    // recovered is a comparison you cannot check -- so they are on the hover.
    out += item(cCol, isYear ? 1.5 : 2, isYear ? SC_DASH_YEAR : SC_DASH,
                opt.compareLabel || (isYear ? "Last year" : "Before"), true,
                opt.compareTitle);
  }
  return '<span style="display:inline-flex;align-items:center;gap:12px">' + out + '</span>';
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
//
// WHICH LINES ARE FILLED is a per-series fact, not something to infer from the
// dash. Ours filled under anything solid, which gave Profit a shading Orbit
// does not draw and left Prior Year flat when Orbit does shade it. Measured on
// the live chart, by the element recharts used for each:
//
//   Sales        recharts-area-curve   fill salesGradient      0.30 -> 0
//   Prior Year   recharts-area-curve   fill priorYearGradient  0.15 -> 0
//   Profit       recharts-line-curve   NO fill
//
// Prior Year is dashed AND filled, at half the opacity -- context that is
// present without competing. `fill: 0` means draw the stroke only.
//
// (Profit reported a stroke-dasharray of "1329.78px 0px" when measured. That is
// not a dash, it is recharts' line-draw animation holding the full path length;
// the series is solid.)
const SC_SERIES = {
  sales:      {label: "Sales",            color: "#10b981", width: 2,   dash: "",    fill: 0.30},
  profit:     {label: "Profit",           color: "#38bdf8", width: 2,   dash: "",    fill: 0},
  prior_year: {label: "Prior Year Sales", color: "#6366f1", width: 1.5, dash: "5 3", fill: 0.15},
  prior:      {label: "Prior period",     color: "#6b7280", width: 2,   dash: "5 5", fill: 0},
  // Orbit's own organic/paid colours and gradients, from gradientOrganic and
  // gradientPpc -- both of which fade to 0.05 rather than to nothing, so the
  // two areas stay distinguishable where they overlap low down.
  organic:    {label: "Organic",          color: "#10b981", width: 2,   dash: "",
               fill: 0.30, fillEnd: 0.05},
  ppc:        {label: "PPC",              color: "#8b5cf6", width: 2,   dash: "",
               fill: 0.30, fillEnd: 0.05},

  // ---- Traffic & Conversions -------------------------------------------
  // MEASURED off Orbit's own lines on that page:
  //   Sessions & Page Views       gold #fbbf24 + blue #3b82f6, both filled
  //   Conversion & Buy Box        green #22c55e + purple #8b5cf6, no fill
  //   Browser & Mobile            blue #3b82f6 + orange #f97316, both filled
  //   Top ASINs                   gold, blue, red, green, purple
  //
  // The rate lines are deliberately UNFILLED. A filled area says "this much of
  // something", and a percentage is not a quantity you can stack or add up --
  // shading under a conversion rate invites reading the area as volume.
  sessions:   {label: "Sessions",         color: "#fbbf24", width: 2, dash: "", fill: 0.30},
  page_views: {label: "Page views",       color: "#3b82f6", width: 2, dash: "", fill: 0.30},
  conversion: {label: "Conversion rate",  color: "#22c55e", width: 2, dash: "", fill: 0},
  buy_box:    {label: "Buy box",          color: "#8b5cf6", width: 2, dash: "", fill: 0},
  browser:    {label: "Browser",          color: "#3b82f6", width: 2, dash: "", fill: 0.30},
  mobile:     {label: "Mobile",           color: "#f97316", width: 2, dash: "", fill: 0.30},
  top1:       {label: "1st",              color: "#fbbf24", width: 2, dash: "", fill: 0},
  top2:       {label: "2nd",              color: "#3b82f6", width: 2, dash: "", fill: 0},
  top3:       {label: "3rd",              color: "#ef4444", width: 2, dash: "", fill: 0},
  top4:       {label: "4th",              color: "#22c55e", width: 2, dash: "", fill: 0},
  top5:       {label: "5th",              color: "#8b5cf6", width: 2, dash: "", fill: 0},
};

/* ---- CLICKING THE KEY TO HIDE A LINE ----------------------------------------
 * Asked for directly: "the graph shows orders prior year sales profit and sales
 * under the graph and user is able to click them to enable those options, they
 * are enabled by default and user can hide the lines by again clicking on them".
 *
 * WHY THIS IS WORTH HAVING and not just decoration: the money lines share one
 * axis, so a big series flattens a small one. Sales in the thousands against
 * profit in the tens draws profit as a line along the floor. Hiding Sales
 * rescales the axis and profit becomes readable -- the axis is recomputed from
 * the VISIBLE series for exactly that reason.
 *
 * HELD IN MEMORY ONLY, deliberately. It survives a filter change or a date
 * change (those redraw, they do not reload) but a page load starts with
 * everything shown. Remembering it across reloads would mean opening the app to
 * a chart with a line silently missing and no memory of having hidden it --
 * which reads as lost data. Orbit resets on reload too.
 */
const SC_OFF = {};          // {"sales_combo": {"profit": true}}
const SC_LAST = {};         // {"sales_combo": <the options it was drawn with>}

function scSeriesHidden(cid, key){
  return !!(SC_OFF[cid] && SC_OFF[cid][key]);
}

function scToggleSeries(cid, key){
  SC_OFF[cid] = SC_OFF[cid] || {};
  if(SC_OFF[cid][key]) delete SC_OFF[cid][key];
  else SC_OFF[cid][key] = true;
  // Redraw from the options the chart was built with, so the toggle never has to
  // know where the figures came from or which screen it is on -- the Sales combo
  // and the four Traffic combos all get this for free.
  const opts = SC_LAST[cid];
  const wrap = document.getElementById(cid + "_wrap");
  if(!opts || !wrap) return;
  // NOT innerHTML on the wrapper: the wrapper IS what salesCombo returns, so
  // replacing its contents would nest a second copy inside the first.
  wrap.outerHTML = salesCombo(opts);
  scRearm(cid);
}

/* ---- THE SCROLL ANIMATION IS NOT REBUILT HERE -------------------------------
 * A chart redrawn by a legend click is a NEW <svg>, so whatever armed the
 * original one has nothing left to hold. The animation itself already exists and
 * is not duplicated here: altaChartsInView() in static/js/motion.js holds any
 * chart below the fold at the start of its animation and releases it when it is
 * scrolled to, and the keyframes live beside .chartbox in dashboard.css.
 *
 * I started writing a second one and deleted it. Two systems animating the same
 * element is how you get a chart that plays twice, or one that pauses itself
 * after the other has released it.
 */
function scRearm(cid){
  if(typeof altaChartsInView !== "function") return;
  const wrap = document.getElementById(cid + "_wrap");
  if(!wrap) return;
  altaChartsInView(wrap);
}

function salesCombo(o){
  const cols  = o.columns || [];
  const bars  = o.bars || null;              // {key,label,values[]}
  const cidKey = o.id || "combo";
  // Remembered so clicking the key can redraw this exact chart. Stored before
  // the early return, so a chart that had nothing to draw still redraws once
  // there is something.
  SC_LAST[cidKey] = o;

  // TWO LISTS, and the difference matters.
  //
  //   drawable  the series Amazon has actually sent a figure for
  //   lines     of those, the ones not switched off in the key
  //
  // The key is built from `drawable` so a hidden series stays listed (dimmed)
  // and can be clicked back on -- removing it from the key would hide the only
  // control that brings it back. Everything else works off `lines`, including
  // the axis, so hiding a series really does rescale the chart.
  const drawable = (o.lines || []).filter(function(l){
    return (l.values || []).some(function(v){ return _scNum(v) !== null; });
  });
  const lines = drawable.filter(function(l){ return !scSeriesHidden(cidKey, l.key); });
  const barsOn = bars && !scSeriesHidden(cidKey, "__bars");
  if(!cols.length) return "";

  // MEASURED off Orbit's live Sales Report, from the drawn SVG rather than from
  // the panel it sits in:
  //
  //   viewBox            1365 x 320
  //   plot area          x 70 -> 1274.9, y 10 -> 254
  //   left tick text     x = 62,   anchor end     (so the axis is at 70)
  //   right tick text    x = 1283, anchor start   (8px clear of the plot)
  //   legend             below the chart, at y 284
  //
  // Ours was 1229 x 330 with padR 56 -- a squatter chart with too little room
  // reserved on the right, which is why the count labels landed ON the last
  // pillar. Half of a 32-wide bar centred on the right-hand plot edge sticks
  // 16px into exactly the strip the labels are drawn in.
  //
  // The right padding is 90 only when there IS a count axis to write there.
  // Orbit's Organic vs PPC chart, which has no bars, runs its plot from 60 to
  // 1355 -- ten clear on the right, not ninety. Reserving the strip on a chart
  // with nothing to put in it just makes the plot narrower than Orbit's.
  const W = o.width || 1365, H = o.height || 320;
  const padL = 70, padR = (barsOn ? 90 : 20), padT = 10, padB = 66;
  const iw = W - padL - padR, ih = H - padT - padB;

  const moneyVals = [];
  lines.forEach(function(l){
    (l.values || []).forEach(function(v){
      const n = _scNum(v); if(n !== null) moneyVals.push(n);
    });
  });
  const barVals = (barsOn && bars.values || []).map(_scNum).filter(function(v){ return v !== null; });

  const cid0 = o.id || "combo";
  scZoomTarget(cid0, o.onZoom);         // same rule as salesChart above
  const mLo = Math.min(0, moneyVals.length ? Math.min.apply(null, moneyVals) : 0);
  const mHi = _scNiceMax(moneyVals.length ? Math.max.apply(null, moneyVals) : 1);
  const mSpan = (mHi - mLo) || 1;
  // The bar axis counts ORDERS, so its ticks have to be whole numbers and its
  // top has to be four whole steps up. See _scNiceCount: this is what stops one
  // order drawing a full-height pillar against an axis reading 0, 0, 1, 1, 1.
  const bHi = _scNiceCount(barVals.length ? Math.max.apply(null, barVals) : 1);

  // BARS NEED BANDS; two areas do not. Ours spread the points edge to edge,
  // which puts the LAST one exactly on the right-hand plot edge -- and a 32-wide
  // bar centred there hangs half its width into the strip the orders axis is
  // written in. That is the "numbers written on the last one orange pillar".
  //
  // Without bars it is a point scale, as Orbit's own Organic vs PPC chart is
  // (measured: 31 points from x=60 to x=1355, first ON the axis, last on the
  // right edge). Same helper as the small charts -- see _scScale.
  const _sc = _scScale(!!barsOn, padL, iw, cols.length);
  const slot = _sc.slot, x = _sc.x;
  const yM = v => padT + ih - ((v - mLo) / mSpan) * ih;
  const yB = v => padT + ih - (v / (bHi || 1)) * ih;

  // Gridlines and both sets of tick labels, at the same five heights so the
  // two scales line up visually instead of drawing two sets of rules.
  // Measured: rgb(55,65,81) at 1px with a 3,3 dash.
  let grid = "";
  [0, 0.25, 0.5, 0.75, 1].forEach(function(f){
    const yy = padT + ih - f * ih;
    grid += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"
                   stroke="rgb(55,65,81)" stroke-width="1" stroke-dasharray="3 3"/>`
         // The left axis is not always money. The Traffic screen puts sessions
         // and page views on it, and conversion and buy box as percentages --
         // labelling a session count "£522" is a plain lie, and it is the kind
         // that goes unnoticed because the shape of the line still looks right.
         +  `<text x="${padL - 8}" y="${yy + 4}" text-anchor="end" font-size="11"
                  fill="rgb(156,163,175)">${_scEsc(_scAxis(mLo + mSpan * f, o.kind || "money", o.currency, mSpan))}</text>`;
    // The right-hand count axis is only drawn when something is counted on it.
    // An axis labelled 0-1-2-3-4 beside a chart with no bars is furniture.
    if(barsOn){
      grid += `<text x="${W - padR + 8}" y="${yy + 4}" text-anchor="start" font-size="11"
                  fill="rgb(156,163,175)">${_scEsc(String(Math.round(bHi * f)))}</text>`;
    }
  });

  // BARS FIRST, so the lines sit over them. Measured: 32 wide in a 40.17 band
  // (0.8 of it), #fbbf24 at opacity 0.3, corners rounded 4 at the TOP only.
  // Never wider than the band, or a long range overlaps into a solid block.
  let barsSvg = "";
  if(barsOn){
    const bw = Math.max(2, Math.min(32, slot * 0.8));
    (bars.values || []).forEach(function(v, i){
      const n = _scNum(v);
      if(n === null || n <= 0) return;
      const top = yB(n), h = (padT + ih) - top;
      barsSvg += `<path class="bar" d="${_scBarPath(x(i) - bw / 2, top, bw, Math.max(0, h), 4)}"
                        fill="#fbbf24" opacity="0.3"/>`;
    });
  }

  // Lines, each broken wherever a day has no figure -- the same refusal to draw
  // through a gap that the single-metric charts make.
  let linesSvg = "";
  // WHAT EACH SERIES ACTUALLY LOOKED LIKE, so the key below can say it rather
  // than promise a solid line the chart never draws. See the note over the
  // legend swatch.
  const shape = {};
  lines.forEach(function(l){
    const spec = SC_SERIES[l.key] || {color: "#8fd694", width: 2, dash: ""};
    let run = [], runs = [];
    (l.values || []).forEach(function(v, i){
      const n = _scNum(v);
      if(n === null){ if(run.length) runs.push(run); run = []; }
      else run.push({i: i, v: n});
    });
    if(run.length) runs.push(run);
    shape[l.key] = {
      points: runs.reduce(function(a, r){ return a + r.length; }, 0),
      days: (l.values || []).length,
      solid: runs.some(function(r){ return r.length > 1; }),
    };
    // The same dashed bridge the single-metric charts use. Profit is the series
    // this is for: it is known only on days where every unit shipped has a cost,
    // so without it the line is a scatter of unconnected dots.
    linesSvg += _scGapJoin(runs, x, yM, spec.color);
    runs.forEach(function(r){
      if(r.length === 1){
        linesSvg += _scLonePoint(x(r[0].i), yM(r[0].v), spec.color);
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
      // and only for the series Orbit actually fills under -- which is a fact
      // about each series, not something the dash can be asked. Profit is solid
      // and unfilled; Prior Year is dashed and filled at half strength.
      if(spec.fill){
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

  // X LABELS, as many as fit. Measured: Orbit labels every one of its 30 days --
  // "Jul 15", "Jul 16", … -- at 40.17px apart, which is as tight as an 11px
  // "Jul 15" goes. Ours thinned to sixteen and dropped half of them for no
  // reason but a fixed count. Same spacing rule as the small charts, with the
  // tighter minimum this chart's own measurement gives: a 30-day range keeps all
  // thirty, and a 90-day range thins itself.
  let xl = "";
  const room = Math.max(1, Math.floor(iw / 40));
  const step = Math.max(1, Math.ceil(cols.length / room));
  cols.forEach(function(c, i){
    if(i % step) return;
    xl += `<text x="${x(i)}" y="${padT + ih + 16}" text-anchor="middle" font-size="11"
                 fill="rgb(156,163,175)">${_scEsc(_scXLabel(c, o.xLabel))}</text>`;
  });

  // Hover: one readout for every series at that column, which is the whole
  // reason to put them on one chart.
  // One gradient per series, since each fills in its own colour. Stops measured
  // off Orbit's: 0.30 at 5%, fading to 0 at 95%.
  const defs = "<defs>" + lines.map(function(l){
    const spec = SC_SERIES[l.key] || {color: "#8fd694", fill: 0.30};
    return `<linearGradient id="${cid0}_g_${l.key}" x1="0" y1="0" x2="0" y2="1">`
         + `<stop offset="5%" stop-color="${spec.color}" stop-opacity="${spec.fill}"/>`
         + `<stop offset="95%" stop-color="${spec.color}" stop-opacity="${
              spec.fillEnd === undefined ? 0 : spec.fillEnd}"/>`
         + `</linearGradient>`;
  }).join("") + "</defs>";

  const cid = cid0;
  // Gold crosshair, as measured on Orbit -- rgb(251,191,36) at 1px, solid.
  let hits = `<line id="${cid}_vl" x1="0" y1="${padT}" x2="0" y2="${padT + ih}"
                    stroke="${SC_GOLD}" stroke-width="1" opacity="0"/>`
           + `<g id="${cid}_dots"></g>`;
  cols.forEach(function(c, i){
    const half = slot / 2;
    // A ROW PER SERIES on the floating card, each in its own colour, with the
    // dot placed on that series' own line. Bars get a row too but no dot --
    // a dot on a bar has nothing to sit on.
    const rows = [];
    // A hidden series is left off the hover card too. A readout for a line that
    // is not on the chart is the sort of thing that makes someone doubt the
    // chart rather than doubt the readout.
    if(barsOn){
      const bv = _scNum((bars.values || [])[i]);
      rows.push({name: (bars.label || "Orders"), color: SC_GOLD,
                 value: (bv === null ? "—" : String(Math.round(bv))), y: null});
    }
    lines.forEach(function(l){
      const spec = SC_SERIES[l.key] || {label: l.key, color: "#8fd694"};
      const v = _scNum((l.values || [])[i]);
      rows.push({name: (spec.label || l.key), color: spec.color,
                 value: (v === null ? "—" : _scFmt(v, o.kind || "money")),
                 y: (v === null ? null : yM(v).toFixed(1))});
    });
    // DRAG TO ZOOM, on this chart too. The per-metric panels had it and this
    // one replaced them, so without it the gesture simply disappeared from the
    // screen -- and it is the only way anyone actually looks closely at an
    // interesting week.
    const _hb = _scBand(x(i), half, padL, iw);
    hits += `<rect x="${_hb.x}" y="${padT}"
                   width="${_hb.w}" height="${ih}" fill="transparent"
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
  //
  // EVERY ITEM IS A BUTTON. Built from `drawable`, not `lines`, so a series that
  // has been switched off is still listed and can be switched back on -- see the
  // two-list note at the top of this function.
  //
  // A real <button>, not a span with a click handler: it is reachable by keyboard
  // and announces itself as a control. aria-pressed carries the on/off state,
  // because "this one is dimmed" is not information a screen reader has.
  const item = function(mark, label, k, on){
    return '<button type="button" class="sc-key' + (on ? '' : ' off') + '"'
         + ' onclick="scToggleSeries(\'' + cid + '\',\'' + k + '\')"'
         + ' aria-pressed="' + (on ? 'true' : 'false') + '"'
         + ' title="' + (on ? 'Hide ' : 'Show ') + _scAttr(label) + ' on the chart">'
         + mark + '<span>' + _scEsc(label) + '</span></button>';
  };
  let key = '<div class="sc-keys">';
  if(bars){
    key += item('<span class="sc-key-sq" style="background:var(--warn-bg)"></span>',
                bars.label || "Orders", "__bars", !!barsOn);
  }
  // THE SWATCH SHOWS WHAT WAS DRAWN, not what the series is supposed to look
  // like.
  //
  //     "check the profit lines on the graph of daily sales, that is not how
  //      the lines are drawn in other places"
  //
  // Profit is known only on days where every unit shipped has a cost, so on
  // these accounts every run is ONE day and no solid stroke is ever drawn --
  // measured in the browser: four #38bdf8 paths, all 1.2px dashed at 0.55
  // opacity, not one solid segment. The key meanwhile drew a confident solid
  // 2px line, exactly like Sales's. So the key and the chart disagreed, and the
  // key was the one that was wrong.
  //
  // Where a series has no continuous stretch, its swatch is the bridge and a
  // point -- which is what is on the chart -- and the label says on how many
  // days it was actually known. That number is the useful one: "Profit, 5 of
  // 30 days" answers the question the faint line raises.
  drawable.forEach(function(l){
    const spec = SC_SERIES[l.key] || {label: l.key, color: "#8fd694", width: 2, dash: ""};
    const sh = (shape || {})[l.key] || {};
    const sparse = sh.points > 0 && !sh.solid;
    const mark = sparse
      ? '<svg width="16" height="8" aria-hidden="true">'
        + '<line x1="0" y1="4" x2="16" y2="4" stroke="' + spec.color
        + '" stroke-width="1.2" stroke-dasharray="3,4" opacity="0.55"/>'
        + '<circle cx="8" cy="4" r="2.6" fill="' + spec.color + '"/></svg>'
      : '<svg width="16" height="8" aria-hidden="true">'
        + '<line x1="0" y1="4" x2="16" y2="4" stroke="' + spec.color
        + '" stroke-width="' + spec.width + '"'
        + (spec.dash ? ' stroke-dasharray="' + spec.dash + '"' : "") + '/></svg>';
    // PLAIN TEXT. item() escapes the label -- markup here would be shown as
    // markup, which is how a "helpful" span becomes &lt;span&gt; on screen.
    const label = (spec.label || l.key)
      + (sparse && sh.days ? ' · ' + sh.points + ' of ' + sh.days + ' days' : '');
    key += item(mark, label, l.key, !scSeriesHidden(cid, l.key));
  });
  key += '</div>';

  // EVERY SERIES SWITCHED OFF is not the same as a chart with no data, and the
  // empty plot that results looks exactly like one. Say which it is.
  const allOff = !barsOn && !lines.length && (drawable.length || bars);
  const note = allOff
    ? '<div class="cc" style="font-size:11px;padding:6px 0;text-align:center;opacity:.8">'
      + 'Everything is hidden — click a name below to bring it back.</div>'
    : '';

  return '<div id="' + cid + '_wrap" style="margin:4px 0 0">'
       // Says the gesture exists. Nobody discovers drag-to-zoom by accident --
       // and it is only claimed on a chart that named a zoom handler.
       + '<div class="cc" style="font-size:10px;margin:0 0 4px;opacity:.65">'
       // The bucket's name, not always "day" -- the Sales Report is drawn over
       // days, weeks or months depending on the granularity picked, and this
       // line said "day" for all three. See the same note in salesChart.
       + 'Hover for the ' + _scEsc(o.unit || "day") + '’s figures'
       + (o.onZoom ? ' · drag across to zoom' : '')
       + ' · click a name below to hide that line'
       + '<span id="' + cid + '_read" style="margin-left:auto"></span></div>'
       + '<div style="position:relative">'
       // Fixed height, width taken from the container -- the same rule as the
       // small charts. See scChartWidth.
       + `<svg id="${cid}_svg" class="chartbox" viewBox="0 0 ${W} ${H}" width="100%"
               style="display:block;height:${H}px;background:transparent;border:0">`
       + defs + grid + barsSvg + linesSvg + xl + hits + '</svg>'
       + `<div id="${cid}_tip" class="charttip"></div>`
       + '</div>'
       + note + key + '</div>';
}
