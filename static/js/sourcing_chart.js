// static/js/sourcing_chart.js -- the sparkline and the price chart. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* ======================================================================
 * THE TABLE.
 *
 * Built from repricer_dashboard_reference.html. What changed and why:
 *
 * It was sixty-seven bordered <div> cards stacked down the page, each one
 * repeating its own labels -- "cheapest source", "selling price", "profit /
 * unit" -- against a single figure. Sixty-seven copies of six labels is four
 * hundred words of furniture, and the one thing a list of prices is for, which
 * is running your eye down a column and seeing which number is out of line,
 * was impossible: nothing lined up with anything.
 *
 * A table says each label ONCE, in a header, and puts the numbers underneath
 * each other. That is the whole reason the reference is a table.
 *
 * Every figure that was on a card is still here. The ones you scan (cost,
 * postage, price, profit, ROI, trend, state) are columns; the ones you read
 * when a row looks wrong (the sum, the suppliers, the rules, the reason) are
 * in the panel that opens underneath it.
 * ====================================================================== */

/* A price history as a line, not bars.
 *
 *     "7d trend = SVG LINE GRAPH sparkline, NOT bar ticks"
 *
 * A supplier's cost is a continuous thing that moves; bars imply separate
 * measurements of separate quantities. The line also makes the shape of a
 * change legible at 70x24 pixels, which is the entire point of drawing it that
 * small.
 *
 * `hist` is [{at, landed, status, in_stock}] NEWEST FIRST -- that is what
 * source_drift.price_history returns, because source_repo.history reads
 * ORDER BY id DESC. It is REVERSED here, and it has to be: a line drawn
 * straight from that order runs backwards in time, so a supplier who has put
 * their price up appears to have dropped it. Measured on jack_uk, every trend
 * on the screen was mirrored.
 *
 * Readings that could not be read are skipped rather than drawn as zero -- a
 * failed fetch is not a free supplier, and a line diving to the floor says
 * exactly that.
 */
function _spark(hist, opts){
  const o = opts || {};
  const W = o.w || 70, H = o.h || 24, PAD = 3;
  // OLDEST FIRST, so left-to-right is earlier-to-later. See the note above.
  const all = (hist || []).slice().reverse().filter(function(p){
    return p && p.landed != null && isFinite(p.landed);
  });
  // ONE READING IS NOT A HISTORY. A single point drawn in a trend column reads
  // as a flat line, which is a claim about how the price has BEHAVED made from
  // one measurement. Nothing is better than that.
  if(all.length < 2) return '';
  // Newest last, and at most the last 12 readings -- older than that is a
  // different question, answered by the full chart this opens into.
  const pts = all.slice(-12);
  const vals = pts.map(function(p){ return +p.landed; });
  const lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  const span = (hi - lo) || 1;
  // A FLAT LINE IS DRAWN FLAT, down the middle. Scaling a run of identical
  // readings to fill the box turns rounding noise into a mountain range.
  const flat = (hi - lo) < 0.005;
  const x = function(i){
    return pts.length < 2 ? W / 2
         : PAD + i * (W - PAD * 2) / (pts.length - 1);
  };
  const y = function(v){
    return flat ? H / 2
         : (H - PAD) - ((v - lo) / span) * (H - PAD * 2);
  };
  // Which way it has gone decides the colour: cheaper is good for us.
  const first = vals[0], last = vals[vals.length - 1];
  const move = first ? ((last - first) / first) * 100 : 0;
  const col = o.color || (move < -1 ? 'var(--ok)'
                        : move > 1  ? 'var(--gold)'
                        : 'var(--ink3)');
  const poly = pts.map(function(p, i){
    return x(i).toFixed(1) + ',' + y(+p.landed).toFixed(1);
  }).join(' ');
  const lastP = pts[pts.length - 1];
  // The supplier has ENDED: the run to the last point is dashed and red, so a
  // dead source is visible without reading the row.
  const dead = String((lastP || {}).status || '') === 'gone';
  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true">'
    + '<polyline fill="none" stroke="' + col + '" stroke-width="1.5" '
    + 'stroke-linecap="round" stroke-linejoin="round" points="' + poly + '"/>'
    + '<circle cx="' + x(pts.length - 1).toFixed(1) + '" cy="'
    + y(+lastP.landed).toFixed(1) + '" r="2" fill="'
    + (dead ? 'var(--red)' : col) + '"/></svg>';
  if(o.bare) return '<div class="rp-supspk">' + svg + '</div>';
  const tip = _smoney(last)
    + (flat ? ' &middot; steady'
            : ' &middot; ' + (move < 0 ? '&darr;' : '&uarr;')
              + Math.abs(move).toFixed(0) + '% over ' + pts.length + ' readings');
  // `this` is passed so the chart can open BESIDE the sparkline rather than in
  // the middle of the page -- the row it belongs to is the context, and a
  // centred modal takes that away exactly when you are comparing this SKU's
  // line with the ones above and below it.
  return '<div class="rp-spk" title="Click for the full history" '
    + 'onclick="event.stopPropagation();srcChart(' + _sarg(o.title || '')
    + ',' + _sarg(JSON.stringify(pts)) + ',this)">' + svg
    + '<div class="rp-stip">' + tip + '</div></div>';
}

/* "08:12" out of a stored "2026-08-17 08:12:46", or "" if there is no time.
 * Read straight off the string rather than through Date: the value is already
 * local time as the app recorded it, and parsing it into a Date would shift it
 * by the browser's offset. */
function _srcClock(iso){
  const m = /[ T](\d{2}):(\d{2})/.exec(String(iso || ''));
  return m ? (m[1] + ':' + m[2]) : '';
}

/* THE SPARKLINE, OPENED UP -- a real chart, not a bar log.
 *
 *     "show a proper line chart like Orbit's -- smooth curves with area fill,
 *      not flat bars. This replaces the current flat grey bar log entirely."
 *
 * WHY A CURVE AND NOT A POLYLINE. A supplier's cost is a continuous thing, and
 * the readings are samples of it four hours apart. Straight segments say "it
 * jumped here", which is a claim about a moment nobody measured; a curve says
 * "it moved between these two points", which is all that is actually known.
 *
 * MONOTONE cubic, specifically -- Fritsch-Carlson tangents -- not a plain
 * Catmull-Rom. An ordinary spline OVERSHOOTS: three readings of 10, 10, 12
 * would be drawn dipping below 10 before the rise, and a chart that shows a
 * price the supplier never charged is worse than one drawn with rulers.
 * Monotone interpolation cannot overshoot by construction.
 *
 * NEAR THE SPARKLINE, not centre-screen: the row it belongs to is the context,
 * and a modal in the middle of the page takes that away at the moment you are
 * comparing this SKU's line with the ones above and below it.
 */
function srcChart(title, json, anchor){
  let pts = [];
  try { pts = JSON.parse(json) || []; } catch(e){ pts = []; }
  // Oldest first -- _spark has already reversed the server's newest-first
  // order, and a chart read left to right must run forwards in time.
  //
  // A READING THAT COULD NOT BE READ IS NOT A PRICE OF ZERO, so the curve is
  // drawn only through the ones that have an amount. But it is not silently
  // dropped either: a run of failures is exactly why a price can look
  // unchanged for a week, and a chart that hides them turns "we could not see"
  // into "it did not move". They are counted under the header and marked on
  // the axis where they happened.
  const usable = pts.filter(function(p){
    return p && p.landed != null && isFinite(p.landed);
  });
  const unread = pts.length - usable.length;
  if(usable.length < 2) return;

  const W = 360, H = 180;
  // A little more room at the bottom than the spec's 26: the axis can carry a
  // second line naming the DATE when the labels above it are clock times.
  const PAD = {t: 14, r: 12, b: 34, l: 52};
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const vals = usable.map(function(p){ return +p.landed; });
  const lo0 = Math.min.apply(null, vals), hi0 = Math.max.apply(null, vals);
  // A FLAT LINE MUST LOOK FLAT. With lo === hi the scale is degenerate, so a
  // band is invented around the value -- and the line sits in the middle of it
  // rather than filling the box and turning rounding noise into a mountain.
  const flat = (hi0 - lo0) < 0.005;
  const pad = flat ? Math.max(0.5, lo0 * 0.05) : (hi0 - lo0) * 0.18;
  const lo = lo0 - pad, hi = hi0 + pad;
  const span = (hi - lo) || 1;

  const X = function(i){ return PAD.l + (i * iw / (usable.length - 1)); };
  const Y = function(v){ return PAD.t + ih - ((v - lo) / span) * ih; };

  // Which way it has gone decides the colour: cheaper is good for us.
  const first = vals[0], last = vals[vals.length - 1];
  const move = first ? ((last - first) / first) * 100 : 0;
  // Tokens, as the row sparkline above uses (graph audit, 30 Sep 2026). They
  // go through style="" below: an SVG presentation attribute does not reliably
  // take var().
  const col = flat || Math.abs(move) < 1 ? 'var(--ok)'
            : (move < 0 ? 'var(--ok)' : 'var(--gold)');
  const gid = 'rpg_' + Math.random().toString(36).slice(2, 8);

  // ---- monotone cubic tangents (Fritsch-Carlson) ----------------------
  const n = usable.length;
  const xs = [], ys = [];
  for(let i = 0; i < n; i++){ xs.push(X(i)); ys.push(Y(vals[i])); }
  const dx = [], dy = [], slope = [];
  for(let i = 0; i < n - 1; i++){
    dx.push(xs[i + 1] - xs[i]);
    dy.push(ys[i + 1] - ys[i]);
    slope.push(dy[i] / (dx[i] || 1));
  }
  const m = [slope[0]];
  for(let i = 1; i < n - 1; i++){
    // A LOCAL EXTREME GETS A FLAT TANGENT. This is the line that makes
    // overshoot impossible: where the data turns, the curve turns with it
    // instead of carrying on past the point and coming back.
    if(slope[i - 1] * slope[i] <= 0){ m.push(0); }
    else {
      const w1 = 2 * dx[i] + dx[i - 1], w2 = dx[i] + 2 * dx[i - 1];
      m.push((w1 + w2) / (w1 / slope[i - 1] + w2 / slope[i]));
    }
  }
  m.push(slope[n - 2]);

  let d = 'M' + xs[0].toFixed(1) + ',' + ys[0].toFixed(1);
  for(let i = 0; i < n - 1; i++){
    const c1x = xs[i] + dx[i] / 3, c1y = ys[i] + m[i] * dx[i] / 3;
    const c2x = xs[i + 1] - dx[i] / 3, c2y = ys[i + 1] - m[i + 1] * dx[i] / 3;
    d += 'C' + c1x.toFixed(1) + ',' + c1y.toFixed(1)
       + ' ' + c2x.toFixed(1) + ',' + c2y.toFixed(1)
       + ' ' + xs[i + 1].toFixed(1) + ',' + ys[i + 1].toFixed(1);
  }
  const area = d + 'L' + xs[n - 1].toFixed(1) + ',' + (PAD.t + ih)
             + 'L' + xs[0].toFixed(1) + ',' + (PAD.t + ih) + 'Z';

  // ---- the axes --------------------------------------------------------
  // THREE GRID LINES, at amounts that are actually in range. A grid drawn at
  // round numbers outside the data would imply the price had been there.
  // Dashed and classed as salesCombo's (.sc-grid), one chart language.
  let grid = '', yl = '';
  for(let k = 0; k <= 2; k++){
    const v = lo0 + (hi0 - lo0) * (k / 2);
    const y = Y(v).toFixed(1);
    grid += '<line x1="' + PAD.l + '" y1="' + y + '" x2="' + (W - PAD.r)
         +  '" y2="' + y + '" class="sc-grid" stroke-width="1" stroke-dasharray="3 3"/>';
    yl += '<text x="' + (PAD.l - 6) + '" y="' + (+y + 3.5)
       +  '" text-anchor="end" class="rp-ax">' + _sesc(_smoney(v)) + '</text>';
  }
  // At most four labels, or they collide.
  //
  // THE DAY, OR THE TIME OF DAY. Suppliers are read every four hours, so a
  // short run of readings is often all on one or two dates -- and "Mon 17 Aug"
  // three times over is a label that distinguishes nothing. When the whole
  // series spans two days or fewer the axis switches to clock times, which is
  // what actually separates those points.
  const days = {};
  usable.forEach(function(p){ days[String(p.at || '').slice(0, 10)] = 1; });
  const sameDay = Object.keys(days).length <= 2;
  let xl = '';
  const step = Math.max(1, Math.round((n - 1) / 3));
  for(let i = 0; i < n; i += step){
    const lab = sameDay ? _srcClock(usable[i].at)
                        : (_srcDay(usable[i].at) || '');
    xl += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 17)
       +  '" text-anchor="middle" class="rp-ax">' + _sesc(lab) + '</text>';
  }
  // ...and then the DATE is said once, under the axis, so "14:20" is not a
  // time on an unknown day.
  if(sameDay){
    const d0 = _srcDay(usable[0].at) || '';
    const d1 = _srcDay(usable[n - 1].at) || '';
    xl += '<text x="' + (PAD.l + iw / 2) + '" y="' + (H - 5)
       +  '" text-anchor="middle" class="rp-ax">'
       +  _sesc(d0 === d1 ? d0 : d0 + ' – ' + d1) + '</text>';
  }

  // ---- the dots, hidden until hovered ---------------------------------
  let dots = '';
  for(let i = 0; i < n; i++){
    const dead = String(usable[i].status || '') === 'gone';
    dots += '<g class="rp-pt" data-i="' + i + '">'
         +  '<circle cx="' + xs[i].toFixed(1) + '" cy="' + ys[i].toFixed(1)
         +  '" r="4" style="fill:' + (dead ? 'var(--red)' : col) + '"/>'
         +  '<circle cx="' + xs[i].toFixed(1) + '" cy="' + ys[i].toFixed(1)
         +  '" r="2" style="fill:var(--as-lit-ffffff-bg)"/></g>';
  }

  const svg =
      '<svg class="rp-chart" viewBox="0 0 ' + W + ' ' + H + '" width="' + W
    + '" height="' + H + '">'
    + '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0" style="stop-color:' + col + ';stop-opacity:.20"/>'
    + '<stop offset="1" style="stop-color:' + col + ';stop-opacity:0"/>'
    + '</linearGradient></defs>'
    + grid
    + '<path d="' + area + '" fill="url(#' + gid + ')"/>'
    + '<path d="' + d + '" fill="none" style="stroke:' + col + '" stroke-width="2" '
    + 'stroke-linecap="round" stroke-linejoin="round"/>'
    + '<line class="rp-cross spc-axis" x1="0" y1="' + PAD.t + '" x2="0" y2="'
    + (PAD.t + ih) + '" stroke-width="1" '
    + 'style="display:none"/>'
    + dots + yl + xl
    + '<rect class="rp-hit" x="' + PAD.l + '" y="' + PAD.t + '" width="' + iw
    + '" height="' + ih + '" fill="transparent"/>'
    + '</svg>';

  const arrow = flat || Math.abs(move) < 1 ? '&middot; steady'
              : (move < 0 ? '&darr; ' : '&uarr; ')
                + (move > 0 ? '+' : '') + move.toFixed(1) + '%';

  let ov = document.getElementById('rp_ov');
  if(!ov){
    ov = document.createElement('div');
    ov.id = 'rp_ov';
    ov.className = 'rp-ov';
    document.body.appendChild(ov);
  }
  ov.innerHTML =
      '<div class="rp-box">'
    + '<button class="rp-x" aria-label="Close">&times;</button>'
    + '<h4>' + _sesc(title || 'Supplier cost') + '</h4>'
    + '<div class="rp-sub">'
    + '<b>' + _smoney(first) + '</b> &rarr; <b>' + _smoney(last) + '</b> '
    + '<span style="color:' + col + '">' + arrow + '</span>'
    + '<span class="cc"> &middot; last ' + n + ' checks</span>'
    // SAID, NOT HIDDEN. Without this line a week of failed reads and a week of
    // a genuinely steady price are the same picture.
    + (unread
        ? '<span class="rp-unread" title="Those readings have no amount, so '
          + 'the line cannot pass through them. A run of them is why a price '
          + 'can look unchanged for days."> &middot; ' + unread
          + ' could not be read</span>'
        : '')
    + '</div>'
    + svg
    + '<div class="rp-tip" style="display:none"></div>'
    + '</div>';

  // ---- position it near the sparkline ---------------------------------
  const box = ov.querySelector('.rp-box');
  ov.classList.add('rp-show');
  if(anchor && anchor.getBoundingClientRect){
    const r = anchor.getBoundingClientRect();
    const bw = box.offsetWidth, bh = box.offsetHeight;
    let left = r.left + window.scrollX - bw / 2 + r.width / 2;
    let top = r.bottom + window.scrollY + 8;
    // Flipped above when there is no room below, and pulled inside the window
    // on both axes -- a popup half off the screen is a popup you cannot read.
    if(r.bottom + bh + 16 > window.innerHeight)
      top = r.top + window.scrollY - bh - 8;
    left = Math.max(8, Math.min(left, window.innerWidth - bw - 8));
    top = Math.max(8, top);
    box.style.left = left + 'px';
    box.style.top = top + 'px';
  } else {
    box.style.left = Math.round(window.innerWidth / 2 - 190) + 'px';
    box.style.top = (window.scrollY + 90) + 'px';
  }

  // ---- hover: crosshair, dot, tooltip ---------------------------------
  const svgEl = box.querySelector('svg');
  const cross = box.querySelector('.rp-cross');
  const tip = box.querySelector('.rp-tip');
  const hit = box.querySelector('.rp-hit');
  const show = function(ev){
    // SNAPPED TO THE NEAREST READING, never interpolated. A tooltip reading
    // "£10.43" for a moment between two checks would be a price nobody was
    // ever charged.
    const r = svgEl.getBoundingClientRect();
    const px = (ev.clientX - r.left) * (W / r.width);
    let best = 0, bd = 1e9;
    for(let i = 0; i < n; i++){
      const dd = Math.abs(xs[i] - px);
      if(dd < bd){ bd = dd; best = i; }
    }
    cross.setAttribute('x1', xs[best]);
    cross.setAttribute('x2', xs[best]);
    cross.style.display = '';
    box.querySelectorAll('.rp-pt').forEach(function(g){
      g.classList.toggle('rp-on', +g.dataset.i === best);
    });
    const p = usable[best];
    tip.innerHTML = '<b>' + _smoney(p.landed) + '</b><br>'
      + _sesc((_srcDay(p.at) || '') + ' ' + _srcClock(p.at)).trim()
      + (String(p.status || '') === 'gone'
          ? '<br><span style="color:var(--red)">supplier ended</span>'
          : (p.in_stock === false
              ? '<br><span style="color:var(--red)">out of stock</span>' : ''));
    tip.style.display = 'block';
    const tx = (xs[best] / W) * r.width + (r.left - box.getBoundingClientRect().left);
    tip.style.left = Math.round(tx) + 'px';
    tip.style.top = Math.round((ys[best] / H) * r.height
                    + (r.top - box.getBoundingClientRect().top) - 12) + 'px';
  };
  hit.addEventListener('mousemove', show);
  hit.addEventListener('mouseleave', function(){
    cross.style.display = 'none';
    tip.style.display = 'none';
    box.querySelectorAll('.rp-pt').forEach(function(g){
      g.classList.remove('rp-on');
    });
  });

  const close = function(){
    ov.classList.remove('rp-show');
    document.removeEventListener('keydown', onKey, true);
  };
  const onKey = function(e){ if(e.key === 'Escape'){ e.preventDefault(); close(); } };
  document.addEventListener('keydown', onKey, true);
  box.querySelector('.rp-x').onclick = close;
  ov.onclick = function(e){ if(e.target === ov) close(); };
}
