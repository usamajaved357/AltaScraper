/* static/js/ppccharts.js -- the one advertising drawing that is not a chart.
 *
 * THIS FILE USED TO HOLD A SECOND CHART ENGINE, and that was the bug.
 *
 * It shipped ppcComposed, ppcArea, ppcStackedArea and ppcHeatmap: bespoke SVG
 * builders written to the mockups, with their own axes, their own gaps and their
 * own everything. They drew pictures -- no hover card, no drag-to-zoom, no
 * clickable key -- which is exactly what "PPC Analytics page seems to be just an
 * image not a full interactive page" was describing.
 *
 * When those screens moved onto salesCombo, the app's own engine, all four were
 * left behind. NOTHING HAS CALLED THEM SINCE. Measured across every .js and every
 * template: of the ten functions this file defined, nine had no caller anywhere,
 * and ppcHeatmap was a second implementation of a heatmap ppcanalytics.js
 * already draws as an HTML table.
 *
 * Seventeen kilobytes of dead code is the small half of the problem. The large
 * half is that a working, importable, NON-INTERACTIVE chart builder sitting
 * beside the shared one is an invitation: the next person to add a panel finds
 * ppcComposed, uses it, and quietly reintroduces the flat picture. Deleting it
 * removes the invitation (Rule 12 -- one way to draw a chart, not two).
 *
 * WHAT SURVIVES is the donut, which is genuinely not a chart in the salesCombo
 * sense: no axes, no time, nothing to hover along. It is a proportion drawn as a
 * ring, and the engine has no equivalent.
 *
 * Everything else on these screens goes through salesCombo (see ppcanalytics.js
 * ppcaChart and ppclive.js ppclChart), so hover, zoom and the key behave the same
 * here as on the Sales page and keep behaving the same as that page changes.
 */

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
