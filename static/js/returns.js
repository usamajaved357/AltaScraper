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

let RET = {data: null, days: 30, busy: false, sort: "returns"};

function _rEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function _rMoney(v){
  return (v===null||v===undefined) ? "—" : Number(v).toFixed(2);
}
function _rPct(v){
  return (v===null||v===undefined) ? "—" : Number(v).toFixed(2)+"%";
}

const RET_NATURE_COLOUR = {
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
  body.innerHTML = '<div class="cc" style="padding:18px"><span class="genspin"></span> '
    + 'Asking Amazon for the returns report — they build these slowly, so this '
    + 'can take a minute…</div>';
  try{
    const j = await (await fetch("/returns/report?days=" + RET.days)).json();
    if(!j || !j.ok){
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _rEsc((j&&j.error)||"Could not load returns") + '</div>';
      return;
    }
    RET.data = j; returnsRender();
  }catch(e){
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

async function returnsUploadFile(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  const body = document.getElementById("retbody");
  if(body) body.innerHTML = '<div class="cc" style="padding:18px">'
    + '<span class="genspin"></span> Reading ' + _rEsc(f.name) + '…</div>';
  try{
    const fd = new FormData();
    fd.append("file", f);
    const j = await (await fetch("/returns/upload", {method:"POST", body: fd})).json();
    // The file is identified by its COLUMNS, not by which button was pressed --
    // so choosing the wrong one is corrected rather than punished. Said out
    // loud, because silently reading it as the other kind would leave you
    // wondering why half the page is still empty.
    if(j && j.ok && RET_WANT && j.source && j.source !== RET_WANT){
      const got = RET_REPORTS[j.source];
      toast("That looks like the " + ((got && got.name) || j.source)
            + " report — read as that.");
    }
    if(!j || !j.ok){
      if(body) body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _rEsc((j&&j.error)||"Could not read that file") + '</div>';
      return;
    }
    RET.data = j; returnsRender();
  }catch(e){
    if(body) body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + _rEsc(String(e)) + '</div>';
  }finally{ input.value = ""; }
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
      + '<div style="height:6px;background:#0d1220;border-radius:3px;overflow:hidden">'
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
    + 'background:#0d1220;border:1px solid #1e2733;border-radius:8px">'
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

  // ---- the six figures across the top --------------------------------
  const rate = (d.return_rate === null || d.return_rate === undefined)
             ? null : Number(d.return_rate);
  const rateBadge = (rate === null) ? ""
    : '<span class="ri-badge ' + (rate > 10 ? "red" : rate > 5 ? "amber" : "teal")
      + '">' + (rate > 10 ? "Above avg" : rate > 5 ? "Watch" : "Below avg")
      + '</span>';
  const sellable = (function(){
    // "Sellable" is a DISPOSITION, and only an FBA file carries it. Said as
    // unavailable rather than guessed from the reason codes.
    const s = (d.dispositions || {});
    const good = Object.keys(s).filter(function(k){
      return /sellable|good/i.test(k) && !/un/i.test(k);
    }).reduce(function(a, k){ return a + s[k]; }, 0);
    const all = Object.keys(s).reduce(function(a, k){ return a + s[k]; }, 0);
    return all ? Math.round((good / all) * 100) : null;
  })();

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
    dailyHtml = '<div class="ri-daily">' + days.map(function(k){
      return '<div class="ri-daily-bar" style="height:'
        + Math.max(3, Math.round((daily[k] / dmax) * 100)) + '%">'
        + '<span class="tip">' + _rEsc(k) + ' — ' + daily[k] + ' unit'
        + (daily[k] === 1 ? "" : "s") + '</span></div>';
    }).join("") + '</div>';
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
  const asins = d.asins || [];
  let table;
  if(asins.length){
    const cols = [["title", "Product"], ["asin", "ASIN"], ["returns", "Returns"],
                  ["units_sold", "Sold"], ["rate", "Rate"],
                  ["refunded", "Refunded"], ["top_reason", "Top reason"]];
    const sorted = asins.slice().sort(function(a, b){
      const k = RET.sort || "returns";
      return (Number(b[k]) || 0) - (Number(a[k]) || 0);
    });
    table = '<div style="overflow-x:auto"><table class="kv" style="width:100%">'
      + '<thead><tr>' + cols.map(function(c){
          return '<th style="text-align:left;font-size:10.5px;padding:6px 8px;'
            + 'cursor:pointer;white-space:nowrap" onclick="returnsSort('
            + jsArg(c[0]) + ')">' + _rEsc(c[1])
            + (RET.sort === c[0] ? ' ▾' : '') + '</th>'; }).join("")
      + '</tr></thead><tbody>'
      + sorted.map(function(r){
          return '<tr>'
            + '<td style="padding:6px 8px;max-width:260px">' + _rEsc(r.title || "") + '</td>'
            + '<td style="padding:6px 8px"><code style="font-size:11px;color:var(--accent2)">'
            + _rEsc(r.asin || "") + '</code></td>'
            + '<td style="padding:6px 8px">' + (r.returns || 0) + '</td>'
            + '<td style="padding:6px 8px">' + (r.units_sold || "—") + '</td>'
            + '<td style="padding:6px 8px">' + _rPct(r.rate) + '</td>'
            + '<td style="padding:6px 8px">' + _rMoney(r.refunded) + '</td>'
            + '<td style="padding:6px 8px">' + _rEsc(r.top_reason || "") + '</td>'
            + '</tr>'; }).join("")
      + '</tbody></table></div>';
  } else {
    table = '<div class="cc ri-sample" style="font-size:12px;padding:14px 0">'
      + 'Each returned product appears here with its return rate, what was '
      + 'refunded, and the reason given most often.</div>';
  }
  h += '<div style="margin-bottom:24px">'
    + _riCard("SKU-Level Returns Detail",
              asins.length ? (asins.length + " products") : "sample", table)
    + '</div>';

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
  const insights = [];
  if(natureTotal){
    natureRows.slice(0, 3).forEach(function(r){
      const pct = Math.round((r.n / natureSum) * 100);
      const action = (d.nature_actions || {})[r.name];
      if(pct >= 15 && action){
        insights.push({sev: pct >= 40 ? "high" : pct >= 25 ? "medium" : "low",
                       title: r.name + " — " + pct + "% of returns",
                       body: r.n + " of " + natureSum + " returned units fall here.",
                       action: action});
      }
    });
  }
  const insightHtml = insights.length
    ? insights.map(function(i){
        return '<div class="ri-insight"><div class="ri-insight-head">'
          + '<span class="ri-sev ' + i.sev + '"></span>'
          + '<span class="ri-insight-title">' + _rEsc(i.title) + '</span></div>'
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

  h += '</div>';
  body.innerHTML = h;
}

function returnsSort(k){ RET.sort = k; returnsRender(); }
