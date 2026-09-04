// ===================== WHY THINGS COME BACK =====================
// Built from the FBA Returns Intelligence report, with the sections this app's
// data can actually support — and honest, on screen, about the two it cannot.
//
// The classification is the point. Fifty reason codes are a list; four causes
// are a decision, and each one has a different answer:
//
//   Product Quality       talk to the supplier, or stop selling it
//   Listing Content       your listing set the wrong expectation — cheapest fix
//   Customer Preference   nothing went wrong; some of this is just trade
//   Shipping / Delivery   packaging, or the carrier
//
// One thing here is better than the report it came from: that page ESTIMATED
// lost revenue. The seller-fulfilled report carries the amount actually
// refunded, so this states the real figure and says which it is.

let RET = {data: null, days: 30, busy: false, sort: "returns", range: null};

/* THE LAST ANSWER WINS, and only the last one.
 *
 * Four things can put data on this screen -- the Amazon pull, a returns upload,
 * a Voice of the Customer upload, and a date range -- and they take wildly
 * different times. The Amazon pull is the slow one: it waits on a report and
 * can take a minute or more. Open the tab (pull starts), drop a file on it
 * while you wait, and the pull lands afterwards and REPLACES the file you just
 * uploaded with whatever the last 30 days held.
 *
 * Caught in a browser: after uploading four seller-fulfilled files and then an
 * FBA file, the page read "3 returns" -- jack_uk's last 30 days from the API --
 * while the server was correctly holding 13,091.
 *
 * Every request takes a ticket; a reply is only drawn if no newer request has
 * been issued since. Nothing is cancelled, so a slow reply is still allowed to
 * finish and simply loses. */
let _RET_SEQ = 0;
function _retTicket(){ return ++_RET_SEQ; }
function _retCurrent(t){ return t === _RET_SEQ; }

function _rEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
/* Money with thousands separators. "195899.96" in a headline card is a number
   nobody can read at a glance -- and misreading a refund total by a factor of
   ten is exactly the mistake the separators exist to prevent.

   NO CURRENCY SYMBOL. The returns report states the amount and not the
   currency, and these accounts span GBP, EUR and USD marketplaces; printing a
   "$" over a euro figure would be a confident lie. The marketplace is on the
   screen already. */
function _rMoney(v){
  if(v === null || v === undefined) return "—";
  const n = Number(v);
  if(!isFinite(n)) return "—";
  return n.toLocaleString(undefined, {minimumFractionDigits: 2,
                                      maximumFractionDigits: 2});
}
function _rPct(v){
  return (v===null||v===undefined) ? "—" : Number(v).toFixed(2)+"%";
}

const RET_NATURE_COLOUR = {
  // SIZING WAS MISSING HERE. domain/returns_view.py grew a "Sizing & Fit" cause
  // -- the biggest one on a footwear account, 63% of everything -- and with no
  // colour against its name every chart drew it in the grey reserved for
  // "Unclassified", which is the one thing it is not.
  "Sizing & Fit":        "#f0b429",
  "Product Quality":     "#ef5350",
  "Listing Content":     "#f5a623",
  "Customer Preference": "#4f8cff",
  "Shipping / Delivery": "#a78bfa",
  "Unclassified":        "#8b90a0",
};

function returnsOnOpen(){ if(!RET.data) returnsLoad(); else returnsRender(); }
function returnsSetDays(d){ RET.days = d; returnsLoad(); }

async function returnsLoad(){
  const body = document.getElementById("retbody");
  if(!body || RET.busy) return;
  RET.busy = true;
  const t = _retTicket();
  body.innerHTML = '<div class="cc" style="padding:18px"><span class="genspin"></span> '
    + 'Asking Amazon for the returns report — they build these slowly, so this '
    + 'can take a minute…</div>';
  try{
    const j = await (await fetch("/returns/report?days=" + RET.days)).json();
    // The slowest request on this screen, and the one most likely to land after
    // a file you uploaded while waiting for it. If anything newer has been
    // asked for, this answer is stale on arrival and is dropped.
    if(!_retCurrent(t)) return;
    if(!j || !j.ok){
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _rEsc((j&&j.error)||"Could not load returns") + '</div>';
      return;
    }
    RET.range = null;
    RET.data = j; returnsRender();
  }catch(e){
    if(!_retCurrent(t)) return;
    body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + _rEsc(String(e)) + '</div>';
  }finally{ RET.busy = false; }
}

/* WHICH REPORT, AND WHERE TO GET IT. Two reports fill different halves of this
   page, and "upload a report" said neither which nor where. Amazon's own naming
   is not guessable -- the FBA one lives under Customer Concessions, which is
   not a phrase anybody would search for. */
const RET_REPORTS = {
  fba: {
    name: "FBA Customer Returns",
    where: "Seller Central → Reports → Fulfilment → Customer Concessions → "
         + "FBA Customer Returns",
    gives: "Everything on this page, including the condition each return came "
         + "back in and the customers' own comments — two things Amazon's API "
         + "will not give a seller-fulfilled account at all.",
  },
  mfn: {
    name: "Seller-fulfilled returns",
    where: "Seller Central → Reports → Return Reports → Seller-fulfilled returns",
    gives: "Reasons, dates, quantities and the amount actually refunded. No "
         + "condition grading and no customer comments — Amazon never handles "
         + "these returns, so it has nothing to grade or record.",
  },
};

let RET_WANT = "";

function returnsUploadOpen(which){
  RET_WANT = which || "";
  const i = document.getElementById("ret_file");
  if(i) i.click();
}

/* SEVERAL FILES AT ONCE, AND THEY ADD UP.
 *
 * This used to send one file and replace everything on screen, which broke the
 * two cases it is most needed for: a year of seller-fulfilled returns is four
 * or five files because Amazon caps that report at 60 days, and an account with
 * both kinds needs one of each. Uploading the second file deleted the first --
 * adding data removed data.
 *
 * The server merges and de-duplicates on the returns themselves, so overlapping
 * windows are safe and re-uploading the same file changes nothing. */
async function returnsUploadFile(input){
  const files = input && input.files ? Array.from(input.files) : [];
  if(!files.length) return;
  const body = document.getElementById("retbody");
  const t = _retTicket();
  if(body) body.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Reading ' + files.length + ' file'
    + (files.length === 1 ? "" : "s") + ': '
    + _rEsc(files.map(f => f.name).join(", ")) + '…</div>';
  try{
    const fd = new FormData();
    files.forEach(f => fd.append("file", f));
    const j = await (await fetch("/returns/upload", {method:"POST", body: fd})).json();
    if(!_retCurrent(t)) return;
    if(!j || !j.ok){
      if(body) body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _rEsc((j&&j.error)||"Could not read that file") + '</div>';
      return;
    }
    // The files are identified by their COLUMNS, not by which button was
    // pressed -- so choosing the wrong one is corrected rather than punished.
    // Said out loud, because silently reading it as the other kind would leave
    // you wondering why half the page is still empty.
    const gotKinds = j.kinds || [];
    if(RET_WANT && gotKinds.length && gotKinds.indexOf(RET_WANT) < 0){
      const got = RET_REPORTS[gotKinds[0]];
      toast("That looks like the " + ((got && got.name) || gotKinds[0])
            + " report — read as that.");
    }
    // A file among several that could not be read must be NAMED. Four files in
    // and one silently missing is the kind of gap nobody notices for a month.
    (j.rejected || []).forEach(function(msg){ toast(msg); });
    RET.range = null;             // a new upload drops any zoom
    RET.data = j; returnsRender();
  }catch(e){
    if(body) body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + _rEsc(String(e)) + '</div>';
  }finally{ input.value = ""; }
}

async function returnsClear(){
  if(!await uiConfirm("Forget every returns file loaded for this account?\n\n"
              + "Nothing on Amazon changes — this only clears what this screen "
              + "is holding, so you can start again with different files."))
    return;
  try{
    const j = await (await fetch("/returns/clear", {method:"POST"})).json();
    RET.data = null; RET.range = null;
    const body = document.getElementById("retbody");
    if(body) body.innerHTML = "";
    toast((j && j.note) || "Cleared.");
    returnsLoad();
  }catch(e){ toast(String(e)); }
}

/* Re-ask the server for a date range. The filtering happens THERE, through the
   same summarise()/build() a fresh upload goes through, so the zoomed figures
   are computed by the one implementation rather than a second copy in JS. */
async function returnsSetRange(from, to){
  const body = document.getElementById("retbody");
  const prev = body ? body.innerHTML : "";
  const t = _retTicket();
  try{
    const q = "?from=" + encodeURIComponent(from || "")
            + "&to=" + encodeURIComponent(to || "");
    const j = await (await fetch("/returns/view" + q)).json();
    if(!_retCurrent(t)) return;
    if(!j || !j.ok){ toast((j && j.error) || "Could not apply that range."); return; }
    RET.range = j.zoomed ? {from: j.start, to: j.end,
                            fullFrom: j.full_start, fullTo: j.full_end} : null;
    RET.data = j; returnsRender();
  }catch(e){
    toast(String(e));
    if(body && prev) body.innerHTML = prev;
  }
}

function returnsResetRange(){ returnsSetRange("", ""); }

/* ---- Amazon's own verdict, and the workbook -----------------------------
 *
 * The Voice of the Customer export is the ONLY place three columns on this page
 * can come from: whether the "frequently returned item" badge is showing on a
 * listing, Amazon's CX Health grade, and the reason Amazon itself puts at the
 * top. None of it is in either returns report, and none of it is in any API
 * this app has. So it is a third upload rather than something inferred.
 */
function returnsQualityOpen(){
  const i = document.getElementById("ret_quality");
  if(i) i.click();
}

async function returnsQualityFile(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  const t = _retTicket();
  try{
    const fd = new FormData();
    fd.append("file", f);
    const j = await (await fetch("/returns/quality", {method:"POST", body: fd})).json();
    if(!_retCurrent(t)) return;
    if(!j || !j.ok){
      toast((j && j.error) || "Could not read that file");
      return;
    }
    toast("Read " + j.rows + " listings — " + j.badge_showing + " already badged, "
          + j.at_risk_count + " at risk.");
    // THE REPLY IS THE WHOLE ANSWER, rebuilt server-side with the quality file
    // folded in. It is NOT patched together here -- the at-risk list and the
    // SKU table's three Amazon columns come from the same analysis the rest of
    // the page does, so there is one place that decides what "at risk" means.
    //
    // AND IT IS NOT returnsLoad(). That pulls from Amazon, which on an account
    // whose returns were UPLOADED threw the uploaded file away: adding a file
    // emptied the page.
    if(j.total_returns !== undefined){ RET.data = j; returnsRender(); }
  }catch(e){
    toast(String(e));
  }finally{ input.value = ""; }
}

/* The workbook is built from what the screen was LAST GIVEN, server-side, so it
   cannot disagree with what is on the page. A plain navigation rather than a
   fetch, so the browser's own download handles it -- and an error comes back as
   JSON, which is why the reply is sniffed first. */
async function returnsExport(){
  try{
    const r = await fetch("/returns/export.xlsx");
    const type = r.headers.get("content-type") || "";
    if(!r.ok || type.indexOf("json") >= 0){
      const j = await r.json().catch(function(){ return null; });
      toast((j && j.error) || "Could not build the workbook");
      return;
    }
    const blob = await r.blob();
    const name = (r.headers.get("content-disposition") || "")
      .replace(/.*filename="?([^"]+)"?.*/, "$1") || "returns-analysis.xlsx";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(a.href); }, 4000);
  }catch(e){ toast(String(e)); }
}

function _retBars(obj, colourFn, total){
  const keys = Object.keys(obj || {});
  if(!keys.length) return '<div class="cc" style="font-size:11.5px">nothing yet</div>';
  const max = Math.max.apply(null, keys.map(k => obj[k]));
  return keys.map(function(k){
    const n = obj[k], pct = total ? (n / total * 100) : 0;
    const col = colourFn ? colourFn(k) : "var(--accent)";
    return '<div style="margin-bottom:7px">'
      + '<div style="display:flex;justify-content:space-between;font-size:11.5px;'
      + 'margin-bottom:2px"><span>' + _rEsc(k.replace(/_/g, " ").toLowerCase())
      + '</span><span class="cc">' + n
      + (total ? ' · ' + pct.toFixed(0) + '%' : '') + '</span></div>'
      + '<div style="height:6px;background:var(--sidebar);border-radius:3px;overflow:hidden">'
      + '<div style="height:100%;width:' + (max ? (n / max * 100) : 0) + '%;'
      + 'background:' + col + '"></div></div></div>';
  }).join("");
}

function _retSpark(daily){
  const days = Object.keys(daily || {});
  if(!days.length) return "";
  const vals = days.map(d => daily[d]);
  const max = Math.max.apply(null, vals) || 1;
  const W = 720, H = 90, pad = 8;
  const x = i => pad + (days.length === 1 ? (W-2*pad)/2 : i*(W-2*pad)/(days.length-1));
  const y = v => H - pad - (v / max) * (H - 2*pad);
  const d = days.map((k,i) => (i?"L":"M") + x(i).toFixed(1) + " " + y(daily[k]).toFixed(1)).join(" ");
  return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" style="height:auto;display:block;'
    + 'background:var(--sidebar);border:1px solid var(--line2);border-radius:8px">'
    + '<path d="'+d+'" fill="none" stroke="#ef5350" stroke-width="2" stroke-linejoin="round"/>'
    + days.map(function(k,i){
        return '<rect x="'+(x(i)-6)+'" y="'+pad+'" width="12" height="'+(H-2*pad)+'" '
             + 'fill="transparent"><title>'+_rEsc(k)+': '+daily[k]+'</title></rect>'; }).join("")
    + '</svg>';
}

/* ---- the page, laid out as the Returns Intelligence report ------------
 *
 * Same six figures across the top, same nine panels, same order, same type
 * scale -- taken from Promixx-USA-FBA-Returns-Intelligence-May2026.html and
 * mapped onto the app's own colours so it belongs here rather than looking
 * like a document that was pasted in.
 *
 * WHERE THE APP HAS NO DATA YET, the panel is still drawn, with a sample
 * figure so the format can be judged. Every one of those is dimmed, in
 * italics, and labelled -- a plausible-looking sample number is the single
 * worst thing this page could produce, because it would be acted on.
 */
function _riSample(v){
  return '<span class="ri-sample" title="Sample figure — no data for this '
       + 'period yet">' + v + '</span>';
}

function _riKpi(label, value, sub, sample){
  return '<div class="ri-kpi"><div class="lbl">' + _rEsc(label) + '</div>'
    + '<div class="val">' + (sample ? _riSample(value) : value) + '</div>'
    + (sub ? '<div class="sub">' + sub + '</div>' : '') + '</div>';
}

function _riCard(title, meta, inner, cls){
  return '<div class="ri-card ' + (cls || "") + '">'
    + '<div class="ri-card-head"><div class="ri-card-title">' + _rEsc(title)
    + '</div>' + (meta ? '<div class="ri-card-meta">' + meta + '</div>' : '')
    + '</div>' + inner + '</div>';
}

/* Horizontal bars, biggest first, each showing its share. */
function _riHbars(rows, colourFor, total){
  if(!rows || !rows.length){
    return '<div class="cc" style="font-size:12px;padding:10px 0">'
         + 'Nothing recorded for this period.</div>';
  }
  const max = rows.reduce(function(m, r){ return Math.max(m, r.n || 0); }, 0) || 1;
  return rows.slice(0, 10).map(function(r){
    const pct = total ? Math.round((r.n / total) * 100) : 0;
    return '<div class="ri-hbar">'
      + '<div class="ri-hbar-head"><span class="ri-hbar-name">' + _rEsc(r.name)
      + '</span><span class="ri-hbar-val">' + r.n
      + (total ? ' <span class="cc" style="font-weight:400">' + pct + '%</span>' : '')
      + '</span></div>'
      + '<div class="ri-hbar-track"><div class="ri-hbar-fill" style="width:'
      + Math.round((r.n / max) * 100) + '%;background:'
      + (colourFor ? colourFor(r.name) : "var(--accent2)") + '"></div></div></div>';
  }).join("");
}

/* ---- the daily chart -------------------------------------------------------
 *
 * WHAT IT WAS: bare bars, no axis, no dates, no counts. You could see that some
 * days were worse than others and nothing else -- not which days, not how many,
 * and there was no way to look at a period. A tooltip on hover was the only
 * access to any actual number, one day at a time.
 *
 * WHAT IT IS NOW: dated ticks along the bottom, a labelled scale up the left,
 * and drag across it to select a period. Releasing the drag re-asks the SERVER
 * for that range, so every figure on the page follows the selection rather than
 * the chart alone -- see returnsSetRange.
 *
 * Drawn as one SVG with real coordinates rather than percentage-height divs,
 * because a drag needs to map a pixel back to a date and flexed divs cannot.
 */
function _riDailyChart(days, daily, dmax){
  const W = 1000, H = 220, L = 46, R = 10, T = 12, B = 30;
  const iw = W - L - R, ih = H - T - B;
  const n = days.length;
  const bw = Math.max(1, iw / n);
  const x = i => L + i * bw;
  const y = v => T + ih - (v / dmax) * ih;

  // A GRID YOU CAN READ A NUMBER OFF. Four lines, each labelled, rounded to
  // something a person would say out loud rather than dmax/4 to two decimals.
  const step = (function(m){
    const raw = m / 4;
    const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    return Math.max(1, Math.ceil(raw / mag) * mag);
  })(dmax);
  let grid = "";
  for(let v = 0; v <= dmax + step * 0.01; v += step){
    const yy = y(v);
    grid += '<line x1="' + L + '" y1="' + yy.toFixed(1) + '" x2="' + (W-R)
         + '" y2="' + yy.toFixed(1) + '" stroke="var(--line)" stroke-width="1"'
         + (v ? ' stroke-dasharray="2 4"' : '') + '/>'
         + '<text x="' + (L-6) + '" y="' + (yy+3.5).toFixed(1) + '" text-anchor="end"'
         + ' font-size="10" fill="var(--ink3)">' + Number(v).toLocaleString()
         + '</text>';
  }

  // DATE TICKS. About eight, evenly spaced, always including the first and last
  // day -- the two anybody looks for first.
  const every = Math.max(1, Math.round(n / 8));
  const want = [];
  days.forEach(function(k, i){
    if(i === 0 || i === n - 1 || i % every === 0) want.push(i);
  });
  // A REGULAR TICK NEXT TO THE LAST DAY OVERLAPS IT. On 226 days the spacing
  // put a label at 08-18 and the final one at 08-20, and they printed on top of
  // each other. The last day always wins -- it is the one people look for.
  const minGap = iw / 12;
  for(let a = want.length - 2; a >= 0; a--){
    if(x(want[a + 1]) - x(want[a]) < minGap) want.splice(a, 1);
  }
  let ticks = "";
  want.forEach(function(i){
    const xx = x(i) + bw / 2;
    ticks += '<text x="' + xx.toFixed(1) + '" y="' + (H - 10)
          + '" text-anchor="middle" font-size="10" fill="var(--ink3)">'
          + _rEsc(days[i].slice(5)) + '</text>';
  });

  const bars = days.map(function(k, i){
    const v = daily[k];
    const hgt = Math.max(1, (v / dmax) * ih);
    return '<rect class="ri-dbar" x="' + x(i).toFixed(2) + '" y="' + y(v).toFixed(2)
      + '" width="' + Math.max(0.6, bw - 0.6).toFixed(2) + '" height="' + hgt.toFixed(2)
      + '" fill="#ef5350"><title>' + _rEsc(k) + ' — ' + v + ' unit'
      + (v === 1 ? "" : "s") + '</title></rect>';
  }).join("");

  const first = days[0], last = days[n-1];
  const zoom = RET.range;
  return '<div class="ri-chartwrap">'
    + '<svg id="ri_daily_svg" viewBox="0 0 ' + W + ' ' + H + '" width="100%"'
    + ' style="height:auto;display:block;touch-action:none;cursor:crosshair"'
    + ' data-l="' + L + '" data-r="' + R + '" data-w="' + W + '"'
    + ' data-days="' + _rEsc(days.join(",")) + '">'
    + '<rect x="' + L + '" y="' + T + '" width="' + iw + '" height="' + ih
    + '" fill="#0d1220" stroke="#1e2733"/>'
    + grid + bars + ticks
    + '<rect id="ri_drag" x="0" y="' + T + '" width="0" height="' + ih
    + '" fill="rgba(79,140,255,.22)" stroke="#4f8cff" stroke-width="1"'
    + ' style="display:none;pointer-events:none"/>'
    + '</svg>'
    + '<div class="ri-charthint">'
    + '<span class="cc">' + _rEsc(first) + ' → ' + _rEsc(last) + ' · '
    + n + ' day' + (n === 1 ? "" : "s")
    + ' · peak ' + Number(dmax).toLocaleString() + '</span>'
    + '<span class="cc">drag across to select a period</span>'
    + (zoom ? '<button class="db-chip" onclick="returnsResetRange()">'
              + '<i class="ti ti-zoom-reset"></i> Show all ('
              + _rEsc(zoom.fullFrom || "") + ' → ' + _rEsc(zoom.fullTo || "")
              + ')</button>' : '')
    + '</div></div>';
}

/* Drag handling, attached AFTER the markup is in the DOM. Bound once per render
   to the SVG itself, so nothing leaks when the card is redrawn. */
function _riBindDrag(){
  const svg = document.getElementById("ri_daily_svg");
  if(!svg) return;
  const days = (svg.getAttribute("data-days") || "").split(",").filter(Boolean);
  if(days.length < 2) return;
  const L = Number(svg.getAttribute("data-l")), R = Number(svg.getAttribute("data-r"));
  const W = Number(svg.getAttribute("data-w"));
  const band = document.getElementById("ri_drag");
  let from = null;

  // Pixel -> day. The SVG scales to its box, so a client x has to be converted
  // through the rendered width rather than assumed to be viewBox units.
  function dayAt(clientX){
    const box = svg.getBoundingClientRect();
    const vx = ((clientX - box.left) / box.width) * W;
    const t = (vx - L) / (W - L - R);
    const i = Math.round(t * (days.length - 1));
    return Math.max(0, Math.min(days.length - 1, i));
  }
  function vxOf(i){
    return L + (i / (days.length - 1)) * (W - L - R);
  }
  svg.addEventListener("pointerdown", function(ev){
    from = dayAt(ev.clientX);
    try{ svg.setPointerCapture(ev.pointerId); }catch(e){}
    if(band){ band.style.display = ""; band.setAttribute("width", "0"); }
  });
  svg.addEventListener("pointermove", function(ev){
    if(from === null || !band) return;
    const to = dayAt(ev.clientX);
    const a = vxOf(Math.min(from, to)), b = vxOf(Math.max(from, to));
    band.setAttribute("x", a.toFixed(1));
    band.setAttribute("width", Math.max(1, b - a).toFixed(1));
  });
  svg.addEventListener("pointerup", function(ev){
    if(from === null) return;
    const to = dayAt(ev.clientX);
    const lo = days[Math.min(from, to)], hi = days[Math.max(from, to)];
    from = null;
    if(band) band.style.display = "none";
    // A CLICK IS NOT A DRAG. Selecting a single day out of eight months is
    // almost always a misclick, and it would replace the whole page with one
    // day's returns.
    if(lo === hi){ return; }
    returnsSetRange(lo, hi);
  });
  svg.addEventListener("pointercancel", function(){
    from = null; if(band) band.style.display = "none";
  });
}

function returnsRender(){
  const body = document.getElementById("retbody");
  const d = RET.data;
  if(!body || !d) return;

  const pairs = function(obj){
    return Object.keys(obj || {}).map(function(k){ return {name: k, n: obj[k]}; })
      .sort(function(a, b){ return b.n - a.n; });
  };
  const natures = pairs(d.natures);
  const reasons = pairs(d.reasons);
  const disps   = pairs(d.dispositions);
  const statuses = pairs(d.statuses);
  const totalRet = Number(d.total_returns || 0);
  const noData = !totalRet;

  let h = '<div class="ri-main">';

  if(noData){
    // WHY there is nothing, first -- "Amazon is still building the report" and
    // "this account is seller-fulfilled so there is no FBA report" are
    // completely different problems and only one of them is worth waiting on.
    if(d.no_report){
      h += '<div class="ri-samplebar"><b>No report yet.</b> ' + _rEsc(d.no_report)
        +  '<div style="margin-top:6px">You can upload one instead — the two '
        +  'Amazon reports this page reads are listed below.</div></div>';
    } else {
      h += '<div class="ri-samplebar"><b>No returns recorded for this period.</b> '
        +  'For a returns page that is good news rather than a fault.</div>';
    }
    h += '<div class="ri-samplebar" style="border-color:var(--line);'
      +  'background:var(--panel2)"><b>The figures below are placeholders, not '
      +  'your data.</b> Every one of them is dimmed and in italics so the '
      +  'layout can be judged now. They are not stored, they are never mixed '
      +  'in with real ones, and they disappear entirely the moment a report '
      +  'lands.</div>';

    // WHICH REPORTS, named, with where to find each and what each one can
    // actually fill in. Amazon's own naming is not guessable: the FBA one
    // lives under "Customer Concessions".
    h += '<div class="ri-2" style="margin-bottom:24px">'
      + Object.keys(RET_REPORTS).map(function(k){
          const r = RET_REPORTS[k];
          return '<div class="ri-card"><div class="ri-card-head">'
            + '<div class="ri-card-title">' + _rEsc(r.name) + '</div>'
            + '<button class="db-chip" onclick="returnsUploadOpen(\'' + k + '\')">'
            + '<i class="ti ti-file-upload"></i> Upload this one</button></div>'
            + '<div class="cc" style="font-size:11.5px;line-height:1.6">'
            + '<b>Where:</b> ' + _rEsc(r.where) + '</div>'
            + '<div class="cc" style="font-size:11.5px;line-height:1.6;margin-top:6px">'
            + '<b>Fills in:</b> ' + _rEsc(r.gives) + '</div></div>';
        }).join("")
      + '</div>';
  }
  if(d.note){
    h += '<div class="cc" style="font-size:12px;margin:0 0 14px;padding:9px 11px;'
      +  'border:1px solid var(--line);border-radius:6px">'
      +  '<i class="ti ti-info-circle"></i> ' + _rEsc(d.note) + '</div>';
  }
  // WHEN A PERIOD IS SELECTED, SAY SO AT THE TOP. Every figure below is for
  // that period, and a page of numbers that quietly means something narrower
  // than it did a moment ago is the worst kind of wrong.
  if(RET.range){
    h += '<div class="ri-samplebar" style="border-color:var(--accent2);'
      +  'display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
      +  '<b>Showing ' + _rEsc(RET.range.from) + ' to ' + _rEsc(RET.range.to)
      +  '.</b> <span class="cc">Every figure on this page is for that period.</span>'
      +  '<button class="db-chip" onclick="returnsResetRange()" '
      +  'style="margin-left:auto"><i class="ti ti-zoom-reset"></i> Show all</button>'
      +  '</div>';
  }

  // ---- the six figures across the top --------------------------------
  const rate = (d.return_rate === null || d.return_rate === undefined)
             ? null : Number(d.return_rate);
  const rateBadge = (rate === null) ? ""
    : '<span class="ri-badge ' + (rate > 10 ? "red" : rate > 5 ? "amber" : "teal")
      + '">' + (rate > 10 ? "Above avg" : rate > 5 ? "Watch" : "Below avg")
      + '</span>';
  // "Sellable" is a DISPOSITION, and only an FBA file carries it. Said as
  // unavailable rather than guessed from the reason codes.
  //
  // FROM THE SERVER, not worked out here. This used to run its own regex over
  // the disposition names — a third place deciding what "sellable" means, after
  // domain/returns_view.is_sellable and the per-product split. One definition,
  // one figure (rule 12).
  const sellable = (d.sellable_pct === null || d.sellable_pct === undefined)
                 ? null : Math.round(Number(d.sellable_pct));

  h += '<div class="ri-kpis">'
    + _riKpi("Total returns", noData ? "212" : totalRet,
             noData ? _riSample("2,438 units ordered")
                    : (d.total_ordered ? (Number(d.total_ordered).toLocaleString()
                                          + " units ordered")
                                       : '<span class="cc">units ordered not known</span>'),
             noData)
    + _riKpi("Return rate", noData ? "8.7%" : (rate === null ? "—" : rate.toFixed(1) + "%"),
             noData ? _riSample("Amazon avg ~8-10%")
                    : (rate === null
                        ? '<span class="cc">no sales figures to compare against</span>'
                        : 'Amazon avg ~8-10% ' + rateBadge),
             noData)
    + _riKpi("Refunded", noData ? "$4,182" : _rMoney(d.refunded),
             noData ? _riSample("of total sales")
                    : (d.refunded_is_actual
                        ? "the amount actually refunded"
                        : '<span class="cc">estimated — the report carried no refund column</span>'),
             noData)
    + _riKpi("Sellable returns", noData ? "46%" : (sellable === null ? "—" : sellable + "%"),
             noData ? _riSample("98 of 212 units recoverable")
                    : (sellable === null
                        ? '<span class="cc">needs an FBA returns file</span>'
                        : "of the units Amazon graded"),
             noData)
    + _riKpi("Avg daily returns",
             noData ? "6.8" : (function(){
               const days = Object.keys(d.daily || {}).length;
               return days ? (totalRet / days).toFixed(1) : "—";
             })(),
             noData ? _riSample("Peak: May 15 (18 units)") : (function(){
               const ds = d.daily || {};
               let top = null;
               Object.keys(ds).forEach(function(k){
                 if(!top || ds[k] > ds[top]) top = k; });
               return top ? ("Peak: " + top + " (" + ds[top] + ")") : "";
             })(),
             noData)
    + _riKpi("Unique SKUs", noData ? "54" : (d.unique_skus || (d.asins || []).length),
             noData ? _riSample("across 7 product lines")
                    : "returned at least once",
             noData)
    + '</div>';

  // ---- daily volume, and the nature mix beside it ---------------------
  const daily = d.daily || {};
  const days = Object.keys(daily).sort();
  const dmax = days.reduce(function(m, k){ return Math.max(m, daily[k]); }, 0) || 1;
  let dailyHtml;
  if(days.length){
    dailyHtml = _riDailyChart(days, daily, dmax);
  } else {
    // The shape, with a sample series, so the panel is not an empty box.
    dailyHtml = '<div class="ri-daily">' + [4,7,3,9,5,12,6,8,4,11,7,5,9,6,3,8]
      .map(function(v){
        return '<div class="ri-daily-bar ri-sample" style="height:'
          + Math.round((v / 12) * 100) + '%"></div>'; }).join("")
      + '</div><div class="cc" style="font-size:11px;margin-top:6px">'
      + 'Sample shape — your own days appear here.</div>';
  }

  const natureTotal = natures.reduce(function(a, r){ return a + r.n; }, 0);
  const natureRows = natures.length ? natures : [
    {name: "Product Quality", n: 84}, {name: "Listing Content", n: 52},
    {name: "Customer Preference", n: 46}, {name: "Shipping / Delivery", n: 30}];
  const natureSum = natureRows.reduce(function(a, r){ return a + r.n; }, 0) || 1;
  const natureHtml =
    '<div class="ri-mini">' + natureRows.map(function(r){
      return '<div class="ri-mini-seg" style="width:' + ((r.n / natureSum) * 100)
        + '%;background:' + (RET_NATURE_COLOUR[r.name] || "#8b90a0") + '"></div>';
    }).join("") + '</div>'
    + '<div class="ri-legend" style="margin-top:12px">'
    + natureRows.map(function(r){
        const pct = Math.round((r.n / natureSum) * 100);
        return '<div class="ri-leg">'
          + '<span class="ri-dot" style="background:'
          + (RET_NATURE_COLOUR[r.name] || "#8b90a0") + '"></span>'
          + '<span class="ri-leg-label">' + _rEsc(r.name) + '</span>'
          + '<span class="ri-leg-val' + (natureTotal ? "" : " ri-sample") + '">'
          + r.n + '</span>'
          + '<span class="ri-leg-pct">' + pct + '%</span></div>';
      }).join("")
    + '</div>'
    + '<div class="cc" style="font-size:11px;margin-top:10px;line-height:1.5">'
    + 'Fifty reason codes grouped into the four things you can actually do '
    + 'something about.</div>';

  h += '<div class="ri-2-1">'
    + _riCard("Daily Returns Volume",
              days.length ? (days.length + " days") : "sample", dailyHtml)
    + _riCard("Issue Nature Classification",
              natureTotal ? (natureTotal + " units") : "sample", natureHtml)
    + '</div>';

  // ---- reasons, disposition, status ----------------------------------
  const reasonRows = reasons.length ? reasons : [
    {name: "Item defective or doesn't work", n: 48},
    {name: "Not as described on the site", n: 37},
    {name: "Ordered wrong item", n: 29},
    {name: "Arrived too late", n: 18},
    {name: "Damaged during shipping", n: 12}];
  const dispRows = disps.length ? disps : [
    {name: "Sellable", n: 98}, {name: "Customer damaged", n: 54},
    {name: "Defective", n: 38}, {name: "Carrier damaged", n: 22}];
  const statusRows = statuses.length ? statuses : [
    {name: "Completed", n: 176}, {name: "Reimbursed", n: 24},
    {name: "Pending", n: 12}];

  const dim = function(html, isSample){
    return isSample ? '<div class="ri-sample">' + html + '</div>' : html;
  };
  h += '<div class="ri-3">'
    + _riCard("Return Reasons Breakdown", reasons.length ? "" : "sample",
              dim(_riHbars(reasonRows, function(){ return "var(--red)"; },
                           reasonRows.reduce(function(a, r){ return a + r.n; }, 0)),
                  !reasons.length))
    + _riCard("Disposition & Recovery", disps.length ? "" :
              (d.has_disposition === false ? "needs an FBA file" : "sample"),
              dim(_riHbars(dispRows, function(n){
                    return /sellable|good/i.test(n) ? "var(--ok)" : "var(--warn)"; },
                    dispRows.reduce(function(a, r){ return a + r.n; }, 0)),
                  !disps.length))
    + _riCard("Return Status", statuses.length ? "" : "sample",
              dim(_riHbars(statusRows, function(){ return "var(--accent2)"; },
                           statusRows.reduce(function(a, r){ return a + r.n; }, 0)),
                  !statuses.length))
    + '</div>';

  // ---- the per-product table -----------------------------------------
  // THREE OF THESE COLUMNS WERE ALWAYS BLANK. The table asked each row for
  // `title`, `units_sold` and `top_reason`; the server has never sent any of
  // those three. It sends `name`, `ordered`, and a `reasons` object. So the
  // Product column, the Sold column and the Top reason column were empty on
  // every row of every account, and sorting by two of them did nothing --
  // silently, because a blank cell in a table of real numbers reads as "no
  // value" rather than as a fault. Found by comparing the keys this file reads
  // against the keys domain/returns_view.py's summarise() actually writes.
  const asins = d.asins || [];
  const topReason = function(r){
    const rs = r.reasons || {};
    let best = "", n = 0;
    Object.keys(rs).forEach(function(k){ if(rs[k] > n){ n = rs[k]; best = k; } });
    return best ? (best.replace(/_/g, " ").toLowerCase() + " (" + n + ")") : "";
  };
  let table;
  if(asins.length){
    const cols = [["name", "Product"], ["asin", "ASIN"], ["returns", "Returns"],
                  ["ordered", "Sold"], ["rate", "Rate"],
                  ["sellable", "Sellable"], ["refunded", "Refunded"],
                  ["", "Top reason"]];
    const sorted = asins.slice().sort(function(a, b){
      const k = RET.sort || "returns";
      // TEXT SORTS AS TEXT. Number("Flux Footwear…") is NaN, so sorting by
      // Product used to compare NaN with NaN and leave the order untouched.
      if(k === "name" || k === "asin"){
        return String(a[k] || "").localeCompare(String(b[k] || ""));
      }
      return (Number(b[k]) || 0) - (Number(a[k]) || 0);
    });
    table = '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
      + '<thead><tr>' + cols.map(function(c){
          if(!c[0]){
            return '<th style="text-align:left;font-size:10.5px;padding:6px 8px;'
              + 'white-space:nowrap">' + _rEsc(c[1]) + '</th>';
          }
          return '<th style="text-align:left;font-size:10.5px;padding:6px 8px;'
            + 'cursor:pointer;white-space:nowrap" onclick="returnsSort('
            + jsArg(c[0]) + ')">' + _rEsc(c[1])
            + (RET.sort === c[0] ? ' ▾' : '') + '</th>'; }).join("")
      + '</tr></thead><tbody>'
      + sorted.map(function(r){
          return '<tr>'
            + '<td class="ri-namecell" style="padding:6px 8px"><div class="ri-name" title="'
            + _rEsc(r.name || "") + '">' + _rEsc(r.name || "") + '</div></td>'
            + '<td style="padding:6px 8px"><code style="font-size:11px;color:var(--accent2)">'
            + _rEsc(r.asin || "") + '</code></td>'
            + '<td style="padding:6px 8px">' + (r.returns || 0) + '</td>'
            + '<td style="padding:6px 8px">'
            + (r.ordered ? Number(r.ordered).toLocaleString() : "—") + '</td>'
            + '<td style="padding:6px 8px">' + _rPct(r.rate) + '</td>'
            // Blank, not zero, where nothing was graded: an ungraded return and
            // a return graded unsellable are different facts.
            + '<td style="padding:6px 8px">'
            + ((r.sellable || r.unsellable)
                ? (r.sellable + ' / ' + (r.sellable + r.unsellable)) : "—") + '</td>'
            + '<td style="padding:6px 8px">' + _rMoney(r.refunded) + '</td>'
            + '<td style="padding:6px 8px">' + _rEsc(topReason(r)) + '</td>'
            + '</tr>'; }).join("")
      + '</tbody></table></div>';
  } else {
    table = '<div class="cc ri-sample" style="font-size:12px;padding:14px 0">'
      + 'Each returned product appears here with its return rate, what was '
      + 'refunded, and the reason given most often.</div>';
  }
  // ---- PRODUCT LINE PERFORMANCE ---------------------------------------
  //
  // The section the report has and this screen did not, and it answers the one
  // question the per-SKU table below cannot: is it THIS COLOUR that comes back,
  // or is the whole family bad? A 12.6% rate across every Pro Electric is a
  // product problem; one colour at 12% among nine at 3% is a listing problem,
  // and they need opposite fixes.
  //
  // Amazon sends no product line, so it is derived from the product name -- see
  // line_of() in domain/returns_view.py -- and the card says so rather than
  // presenting a guess as a fact.
  // PLACEHOLDER ROWS ONLY WHEN THERE IS NO DATA AT ALL. `noData` is the same
  // flag every other panel on this screen uses. Keying off `lines.length` alone
  // would have drawn invented product lines beside real returns whenever the
  // server answer predated this section -- sample figures sitting in a table of
  // true ones, which is the one thing a placeholder must never do.
  const lines = d.lines || [];
  const lineRows = lines.length ? lines : (noData ? [
    {line: "Pursuit PE (Plastic)", returns: 72, ordered: 2356, rate: 3.06,
     sales: 38484, lost: 954, skus: 12,
     natures: {"Product Quality": 30, "Listing Content": 18,
               "Customer Preference": 16, "FBA / Shipping": 8}},
    {line: "Pro Electric", returns: 52, ordered: 414, rate: 12.56,
     sales: 14066, lost: 1767, skus: 2,
     natures: {"Product Quality": 28, "Listing Content": 14,
               "Customer Preference": 6, "FBA / Shipping": 4}},
    {line: "Pursuit SWSS (Stainless)", returns: 45, ordered: 651, rate: 6.91,
     sales: 15767, lost: 1102, skus: 13,
     natures: {"Product Quality": 15, "Listing Content": 15,
               "Customer Preference": 12, "FBA / Shipping": 3}}] : []);
  const lineMix = function(nat){
    const tot = Object.keys(nat || {}).reduce(function(a, k){ return a + nat[k]; }, 0) || 1;
    return '<div class="ri-mini" style="min-width:96px">'
      + Object.keys(nat || {}).map(function(k){
          return '<div class="ri-mini-seg" style="width:' + ((nat[k] / tot) * 100)
            + '%;background:' + (RET_NATURE_COLOUR[k] || "#8b90a0") + '"'
            + ' title="' + _rEsc(k) + ': ' + nat[k] + '"></div>';
        }).join("") + '</div>';
  };
  // The SAME table class the SKU table below uses. A second table style here
  // would be two things that have to be kept looking alike by hand.
  const lineTable = '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
    + '<thead><tr><th>Product Line</th><th>Returns</th><th>Ordered</th>'
    + '<th>Return Rate</th><th>Revenue</th><th>Est. Lost Rev</th>'
    + '<th>Issue Mix</th><th>SKUs</th></tr></thead><tbody>'
    + lineRows.map(function(L){
        // The rate carries the colour, because it is the number being scanned
        // for: anything over 10% is the reason to open the row. Reuses the
        // existing .ri-badge, which already has the three colours.
        const rateCls = (L.rate === null || L.rate === undefined) ? ""
          : (L.rate >= 10 ? "red" : L.rate >= 6 ? "amber" : "teal");
        return '<tr' + (lines.length ? "" : ' class="ri-sample"') + '>'
          + '<td class="ri-namecell" style="padding:6px 8px">'
          + '<div class="ri-name" title="' + _rEsc(L.line) + '">'
          + _rEsc(L.line) + '</div></td>'
          + '<td style="padding:6px 8px">' + (L.returns || 0) + '</td>'
          + '<td style="padding:6px 8px">' + (L.ordered ? Number(L.ordered).toLocaleString() : "—") + '</td>'
          + '<td style="padding:6px 8px">'
          + (rateCls ? '<span class="ri-badge ' + rateCls + '">' + _rPct(L.rate) + '</span>'
                     : _rPct(L.rate)) + '</td>'
          + '<td style="padding:6px 8px">' + (L.sales ? _rMoney(L.sales) : "—") + '</td>'
          + '<td style="padding:6px 8px">' + (L.lost ? _rMoney(L.lost) : "—")
          + (L.estimated ? '<span class="cc" title="estimated from this line\'s own '
                           + 'average selling price, because the report carried no '
                           + 'refunded column"> est</span>' : "") + '</td>'
          + '<td style="padding:6px 8px">' + lineMix(L.natures) + '</td>'
          + '<td style="padding:6px 8px">' + (L.skus || 0) + '</td>'
          + '</tr>'; }).join("")
    + '</tbody></table></div>'
    + '<div class="cc" style="font-size:11px;margin-top:8px">'
    + (lines.length
        ? 'Lines are worked out from ' + _rEsc(d.lines_from || "the product names")
          + ' — Amazon sends no product line of its own. The SKUs in each are in '
          + 'the table below.'
        : (noData
            ? 'Sample shape — your own product lines appear here.'
            : 'Your returns are loaded but this app has not grouped them into '
              + 'product lines yet. Press Refresh; if it stays empty the returns '
              + 'file carried no product names to group by.'))
    + '</div>';

  h += '<div style="margin-bottom:24px">'
    + _riCard("Product Line Performance",
              lines.length ? "Return rate and revenue impact by product family"
                           : (noData ? "sample" : "nothing to group"), lineTable)
    + '</div>';

  // ---- BY PARENT: the same returns, one row per product ----------------
  //
  // The Product Line table above answers "which family", and this answers "and
  // in which DIRECTION". They are the same grouping -- domain/returns_intel.py
  // keys on the identical line_of() call, so the totals cannot drift -- and
  // this one carries the three things the other has no room for: how many child
  // ASINs are inside, how the sizing splits, and whether it is getting worse.
  const intel = d.intel || {};
  const parents = intel.parents || [];
  const months = intel.months || [];
  const trendChip = function(t){
    if(t === "increasing") return '<span class="ri-badge red">rising</span>';
    if(t === "decreasing") return '<span class="ri-badge teal">falling</span>';
    if(t === "stable")     return '<span class="ri-badge">steady</span>';
    return '<span class="cc" style="font-size:10.5px">too few months</span>';
  };
  if(parents.length){
    const pTable = '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
      + '<thead><tr><th>Product</th><th>Returns</th><th>Ordered</th><th>Rate</th>'
      + '<th>Share</th><th>Children</th><th>Sellable</th><th>Too small</th>'
      + '<th>Too large</th><th>Ratio</th><th>Trend</th></tr></thead><tbody>'
      + parents.map(function(p){
          const rs = p.reasons || {};
          const small = rs.APPAREL_TOO_SMALL || 0, large = rs.APPAREL_TOO_LARGE || 0;
          const rateCls = (p.return_rate === null || p.return_rate === undefined) ? ""
            : (p.return_rate >= 25 ? "red" : p.return_rate >= 15 ? "amber" : "teal");
          return '<tr>'
            + '<td class="ri-namecell" style="padding:6px 8px"><div class="ri-name" title="'
            + _rEsc(p.label) + '">' + _rEsc(p.label) + '</div></td>'
            + '<td style="padding:6px 8px">' + (p.returns || 0) + '</td>'
            + '<td style="padding:6px 8px">'
            + (p.ordered ? Number(p.ordered).toLocaleString() : "—") + '</td>'
            + '<td style="padding:6px 8px">'
            + (rateCls ? '<span class="ri-badge ' + rateCls + '">' + _rPct(p.return_rate)
                         + '</span>' : _rPct(p.return_rate)) + '</td>'
            + '<td style="padding:6px 8px">' + _rPct(p.share) + '</td>'
            + '<td style="padding:6px 8px">' + (p.child_count || 0) + '</td>'
            + '<td style="padding:6px 8px">' + _rPct(p.sellable_pct) + '</td>'
            + '<td style="padding:6px 8px">' + (small || "—") + '</td>'
            + '<td style="padding:6px 8px">' + (large || "—") + '</td>'
            + '<td style="padding:6px 8px">'
            + (large ? (small / large).toFixed(1) + ":1" : "—") + '</td>'
            + '<td style="padding:6px 8px">' + trendChip(p.trend) + '</td>'
            + '</tr>'; }).join("")
      + '</tbody></table></div>'
      + '<div class="cc" style="font-size:11px;margin-top:8px;line-height:1.5">'
      + 'Grouped by ' + _rEsc((parents[0] || {}).grouped_by || "the product name")
      + '. Trend compares the last three complete months with the first three, '
      + 'so a quarter either way is noise and anything past that is a direction.'
      + '</div>';
    h += '<div style="margin-bottom:24px">'
      + _riCard("By Parent Product",
                parents.length + " product line" + (parents.length === 1 ? "" : "s"),
                pTable)
      + '</div>';

    // ---- the same rows, month by month ---------------------------------
    if(months.length > 1){
      const part = intel.partial_last_month;
      const mTable = '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
        + '<thead><tr><th>Product</th>'
        + months.map(function(m, i){
            const last = (i === months.length - 1);
            return '<th' + ((last && part)
              ? ' title="This month is not finished, so it is left out of the trend"'
              : '') + '>' + _rEsc(m.slice(2)) + ((last && part) ? "*" : "") + '</th>';
          }).join("")
        + '<th>Total</th><th>Trend</th></tr></thead><tbody>'
        + parents.map(function(p){
            const mm = p.monthly || {};
            const peak = months.reduce(function(a, m){
              return Math.max(a, mm[m] || 0); }, 0) || 1;
            return '<tr><td class="ri-namecell" style="padding:6px 8px">'
              + '<div class="ri-name" title="' + _rEsc(p.label) + '">'
              + _rEsc(p.label) + '</div></td>'
              // Shaded by size, so the shape of a year is readable without
              // reading eight numbers per row.
              + months.map(function(m){
                  const v = mm[m] || 0;
                  return '<td style="padding:6px 8px;background:rgba(239,83,80,'
                    + (v / peak * 0.28).toFixed(3) + ')">' + (v || "") + '</td>';
                }).join("")
              + '<td style="padding:6px 8px"><b>' + (p.returns || 0) + '</b></td>'
              + '<td style="padding:6px 8px">' + trendChip(p.trend) + '</td>'
              + '</tr>'; }).join("")
        + '</tbody></table></div>'
        + (part ? '<div class="cc" style="font-size:11px;margin-top:8px">'
                  + '* the last month is not finished — it is shown, and left '
                  + 'out of the trend, because three weeks against a full month '
                  + 'reads as a collapse that has not happened.</div>' : "");
      h += '<div style="margin-bottom:24px">'
        + _riCard("Month by Month", months.length + " months", mTable)
        + '</div>';
    }
  }

  h += '<div style="margin-bottom:24px">'
    + _riCard("SKU-Level Returns Detail",
              asins.length ? "Every child ASIN that came back, biggest first"
                           : "sample", table)
    + '</div>';

  // ---- what Amazon itself has flagged ---------------------------------
  //
  // NOT OUR THRESHOLD. This is the "frequently returned item" badge -- Amazon's
  // own warning, shown to shoppers on the listing page. An earlier version
  // flagged anything over 15% and produced 470 rows out of 552 on a real
  // account, including ASINs with one order at "100%". A list nobody can act on
  // is the same as no list.
  const risky = intel.at_risk || [];
  if(intel.has_amazon_quality){
    const showing = risky.filter(function(a){ return a.state === "badge showing"; });
    const soon = risky.filter(function(a){ return a.state === "at risk"; });
    const rTable = risky.length
      ? '<div class="ri-scroll" style="max-height:420px"><table class="kv" style="width:100%">'
        + '<thead><tr><th>State</th><th>ASIN</th><th>Product</th><th>Rate</th>'
        + '<th>Orders</th><th>Amazon\'s top reason</th><th>CX health</th>'
        + '</tr></thead><tbody>'
        + risky.map(function(a){
            return '<tr><td style="padding:6px 8px"><span class="ri-badge '
              + (a.state === "badge showing" ? "red" : "amber") + '">'
              + (a.state === "badge showing" ? "badged" : "at risk") + '</span></td>'
              + '<td style="padding:6px 8px"><code style="font-size:11px;'
              + 'color:var(--accent2)">' + _rEsc(a.asin) + '</code></td>'
              + '<td class="ri-namecell" style="padding:6px 8px"><div class="ri-name" title="'
              + _rEsc(a.name || "") + '">' + _rEsc(a.name || "") + '</div></td>'
              + '<td style="padding:6px 8px">' + _rPct(a.return_rate) + '</td>'
              + '<td style="padding:6px 8px">' + (a.orders || "—")
              // Amazon lists a listing once per SKU. The rows are folded into
              // one, and how many there were is said rather than hidden --
              // otherwise the totals here and in Amazon's own file disagree
              // with nothing to explain why.
              + (a.sku_rows > 1 ? ' <span class="cc" style="font-size:10px" '
                 + 'title="Amazon listed this ASIN under ' + a.sku_rows
                 + ' SKUs; this is the one with the most orders. Nothing is '
                 + 'added up across them.">· ' + a.sku_rows + ' SKUs</span>'
                 : '') + '</td>'
              + '<td style="padding:6px 8px">' + _rEsc(a.top_reason || "—") + '</td>'
              + '<td style="padding:6px 8px">' + _rEsc(a.cx_health || "—") + '</td>'
              + '</tr>'; }).join("")
        + '</tbody></table></div>'
      : '<div class="cc" style="font-size:12px;padding:12px 0">Amazon has '
        + 'flagged none of your listings. That is the good answer.</div>';
    h += '<div style="margin-bottom:24px">'
      + _riCard("Amazon's Returns Badge",
                showing.length + ' already badged · ' + soon.length + ' at risk',
                '<div class="cc" style="font-size:11.5px;line-height:1.6;'
                + 'margin-bottom:10px">A badged listing shows shoppers a '
                + '"frequently returned item" warning, and it costs conversion '
                + 'on every visit from then on. "At risk" means it is not '
                + 'showing yet — the cheaper half of the list.</div>' + rTable)
      + '</div>';
  } else {
    h += '<div style="margin-bottom:24px">'
      + _riCard("Amazon's Returns Badge", "needs one more file",
                '<div class="cc" style="font-size:11.5px;line-height:1.7">'
                + 'Whether Amazon is showing the "frequently returned item" '
                + 'badge on a listing is not in either returns report and is in '
                + 'no API this app has. It is only in the Voice of the Customer '
                + 'export: <b>Seller Central → Brands → Customer Experience → '
                + 'Voice of the Customer → Download</b>. Press '
                + '<b>Upload listing quality</b> above and this fills in, along '
                + 'with three columns of the SKU table.</div>')
      + '</div>';
  }

  // ---- what customers said, and what to do about it -------------------
  const comments = d.comments || [];
  const natureCls = function(n){
    return /quality/i.test(n) ? "quality" : /listing/i.test(n) ? "listing"
         : /shipping|delivery/i.test(n) ? "shipping" : "customer";
  };
  let commentHtml;
  if(comments.length){
    commentHtml = '<div class="ri-scroll">' + comments.slice(0, 40).map(function(c){
      return '<div class="ri-comment ' + natureCls(c.nature || c.reason || "") + '">'
        + _rEsc(c.text || "")
        + '<div class="ri-comment-meta">' + _rEsc(c.sku || c.asin || "")
        + (c.reason ? " · " + _rEsc(c.reason) : "") + '</div></div>';
    }).join("") + '</div>';
  } else {
    commentHtml = '<div class="ri-sample">'
      + '<div class="ri-comment quality">Stopped charging after two weeks. '
        + 'Disappointing for the price.<div class="ri-comment-meta">sample · '
        + 'Item defective</div></div>'
      + '<div class="ri-comment listing">Much smaller than the photos suggest.'
        + '<div class="ri-comment-meta">sample · Not as described</div></div>'
      + '</div>'
      + '<div class="cc" style="font-size:11px;margin-top:8px;line-height:1.5">'
      + (d.has_comments === false
          ? 'The seller-fulfilled report carries no customer comments. Upload an '
            + 'FBA Customer Returns file and the real ones appear here.'
          : 'Customers’ own words appear here when the report carries them.')
      + '</div>';
  }

  // The insights are DERIVED, never invented: each one names the figure it
  // came from, so it can be checked rather than believed.
  //
  // THEY COME FROM THE SERVER NOW. This used to build its own three from the
  // nature mix, which meant the screen and the Excel export would have derived
  // their findings separately and could have said different things about the
  // same account (rule 12). domain/returns_intel.insights() is the one place
  // that turns figures into findings; the workbook's Action Plan sheet is the
  // same list with a priority and a timeline against each row.
  const insights = (intel.insights || []).map(function(i){
    return {sev: i.severity === "high" ? "high"
               : i.severity === "medium" ? "medium" : "low",
            title: i.title, body: i.body, action: i.action, scope: i.scope};
  });
  const insightHtml = insights.length
    ? insights.map(function(i){
        return '<div class="ri-insight"><div class="ri-insight-head">'
          + '<span class="ri-sev ' + i.sev + '"></span>'
          + '<span class="ri-insight-title">' + _rEsc(i.title) + '</span>'
          + (i.scope && i.scope !== "Whole account"
              ? '<span class="cc" style="font-size:10.5px;margin-left:auto">'
                + _rEsc(i.scope.slice(0, 34)) + '</span>' : '')
          + '</div>'
          + '<div class="ri-insight-body">' + _rEsc(i.body) + '</div>'
          + '<div class="ri-insight-action">→ ' + _rEsc(i.action) + '</div></div>';
      }).join("")
    : '<div class="ri-sample">'
      + '<div class="ri-insight"><div class="ri-insight-head">'
      + '<span class="ri-sev high"></span>'
      + '<span class="ri-insight-title">Product Quality — 40% of returns</span></div>'
      + '<div class="ri-insight-body">Sample. Real insights name the figure they '
      + 'came from, so each one can be checked rather than believed.</div>'
      + '<div class="ri-insight-action">→ talk to the supplier, or stop selling it'
      + '</div></div></div>';

  h += '<div class="ri-2">'
    + _riCard("Customer Voice Analysis",
              comments.length ? (comments.length + " comments") : "sample", commentHtml)
    + _riCard("Actionable Insights",
              insights.length ? "" : "sample", insightHtml)
    + '</div>';

  // ---- the comments, grouped by what they actually SAY ------------------
  //
  // Four thousand comments are unreadable. Seven themes with real quotes under
  // them are a morning's work. The themes come from the WORDS, not the reason
  // code, because the two disagree often enough to matter: a return Amazon
  // filed as UNWANTED_ITEM whose comment says "half a size too short" is a
  // sizing return, and only the comment says so.
  const th = intel.themes || {};
  const themes = th.themes || [];
  if(themes.length){
    const tmax = themes[0].count || 1;
    const themeHtml = themes.map(function(t){
      return '<div class="ri-theme">'
        + '<div class="ri-hbar-head"><span class="ri-hbar-name">'
        + _rEsc(t.theme) + ' <span class="cc" style="font-weight:400">'
        + _rEsc(t.nature) + '</span></span>'
        + '<span class="ri-hbar-val">' + t.count
        + ' <span class="cc" style="font-weight:400">' + _rPct(t.share)
        + '</span></span></div>'
        + '<div class="ri-hbar-track"><div class="ri-hbar-fill" style="width:'
        + Math.round(t.count / tmax * 100) + '%;background:'
        + (RET_NATURE_COLOUR[t.nature] || "var(--accent2)") + '"></div></div>'
        + '<div class="ri-quotes">' + (t.quotes || []).map(function(q){
            return '<div class="ri-quote">“' + _rEsc(q) + '”</div>';
          }).join("") + '</div></div>';
    }).join("");
    h += '<div style="margin-bottom:24px">'
      + _riCard("What Customers Actually Wrote",
                th.placed + " of " + th.comments_read + " comments grouped",
                themeHtml
                // SAID OUT LOUD. A theme list covering half the comments and
                // not saying so reads as the whole picture.
                + '<div class="cc" style="font-size:11px;margin-top:12px;'
                + 'line-height:1.6">' + th.unplaced + ' comment'
                + (th.unplaced === 1 ? " says" : "s say")
                + ' something this app has no rule for, and are not counted '
                + 'above. They are worth reading raw in the panel above — that '
                + 'is where a theme nobody has thought of yet shows up.</div>')
      + '</div>';
  }

  h += '</div>';
  body.innerHTML = h;
  // AFTER the markup exists. The chart is redrawn on every render, so the
  // handlers are attached to the fresh SVG each time rather than kept alive.
  try{ _riBindDrag(); }catch(e){}
}

function returnsSort(k){ RET.sort = k; returnsRender(); }
