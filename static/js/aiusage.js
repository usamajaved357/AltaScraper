// ===================== WHAT THE AI COST =====================
// "how many credits are used in which account of the AI and for which feature"
//
// Both halves of that question get an answer here, and the second one is the
// one that changes decisions. A total tells you the bill; the cross of account
// against feature tells you that one account's image generation is most of it,
// which is the only version you can act on.
//
// Drawn as a chart AND written out. The chart answers "is it going up"; the
// tables answer "which account, doing what". Neither replaces the other, and
// the request was explicit about wanting both.
//
// THREE THINGS THIS SCREEN REFUSES TO SMOOTH OVER, because each of them makes
// the number smaller and a too-small number is the one nobody questions:
//   * a call on a model with no known price is counted as UNKNOWN, never as
//     free, and the total is labelled a minimum
//   * a failed call still spent its input tokens, so it is counted
//   * a call made outside any account is its own row, never folded into
//     whichever account happened to be open
//
// The line chart is salesChart() from salescharts.js -- the same one the Sales
// screen uses, with its hover and its refusal to draw a zero where there is no
// data. A second chart implementation here would drift from that one on the
// first fix made to either.

let AIU = {data: null, days: 30, busy: false, calls: null, callsFor: ""};

function _aiEsc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// Money, at the precision the number deserves. AI calls cost fractions of a
// cent, so a flat 2 decimal places would print "$0.00" beside a real spend and
// make the screen look broken -- or worse, free.
function _aiMoney(v){
  if(v === null || v === undefined) return "unknown";
  const n = Number(v);
  if(!isFinite(n)) return "unknown";
  if(n === 0) return "$0";
  if(n >= 1) return "$" + n.toFixed(2);
  if(n >= 0.01) return "$" + n.toFixed(3);
  return "$" + n.toFixed(5);
}

function _aiNum(v){
  const n = Number(v || 0);
  return n >= 1000 ? n.toLocaleString() : String(n);
}

// Tokens read better in thousands once there are a lot of them.
function _aiTok(v){
  const n = Number(v || 0);
  if(n >= 1000000) return (n / 1000000).toFixed(2) + "M";
  if(n >= 1000) return Math.round(n / 1000) + "k";
  return String(n);
}

// A stable colour per name, so an account keeps its colour between loads.
function _aiColour(name){
  const palette = ["#6ac7e8", "#8fd694", "#e8c66a", "#c79ae8", "#7fb2f0",
                   "#ef8f8f", "#7fd6c8", "#d9a06a"];
  let h = 0;
  const s = String(name || "");
  for(let i = 0; i < s.length; i++){ h = (h * 31 + s.charCodeAt(i)) | 0; }
  return palette[Math.abs(h) % palette.length];
}

function aiUsageOnOpen(){ if(!AIU.data) aiUsageLoad(); else aiUsageRender(); }
function aiUsageSetDays(d){ AIU.days = d; aiUsageLoad(); }

async function aiUsageLoad(){
  const body = document.getElementById("aiu_body");
  if(!body || AIU.busy) return;
  AIU.busy = true;
  body.innerHTML = '<div class="cc" style="padding:18px"><span class="genspin"></span> '
    + 'Reading what the AI has cost…</div>';
  try{
    const j = await (await fetch("/aiusage/summary?days=" + AIU.days)).json();
    if(!j || !j.ok){
      body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
        + _aiEsc((j && j.error) || "Could not read the usage record") + '</div>';
      return;
    }
    AIU.data = j;
    aiUsageRender();
  }catch(e){
    body.innerHTML = '<div class="cc" style="padding:18px;color:var(--red)">'
      + 'Could not read the usage record: ' + _aiEsc(String(e)) + '</div>';
  }finally{
    AIU.busy = false;
  }
}

// ---- the pieces of the page ------------------------------------------------

function _aiEmpty(d){
  // Nothing recorded is a legitimate state, and it must not look like a
  // failure. It is also worth saying WHY it can be empty, because recording
  // started on a particular day and older spend is genuinely not in here.
  return '<div style="padding:20px;border:1px dashed #2a3446;border-radius:10px">'
    + '<div style="font-size:14px;margin-bottom:6px">No AI calls recorded between '
    + _aiEsc(d.start) + ' and ' + _aiEsc(d.end) + '.</div>'
    + '<div class="cc" style="font-size:12px;line-height:1.6">'
    + 'Every call the app makes is recorded from the moment it is made — but only '
    + 'from then on. Spend from before this screen existed was never written down '
    + 'and cannot be recovered. Generate a listing or an image and it will appear '
    + 'here.</div></div>';
}

function _aiTotals(d){
  const cards = [
    ["Total spend", _aiMoney(d.cost_usd),
     d.unpriced_calls ? "at least — some calls are unpriced" : "in this period"],
    ["Calls", _aiNum(d.calls), "requests made"],
    ["Tokens", _aiTok((d.input_tokens || 0) + (d.output_tokens || 0)),
     _aiTok(d.input_tokens) + " in / " + _aiTok(d.output_tokens) + " out"],
    ["Images", _aiNum(d.images), "generated"],
  ];
  return '<div style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px">'
    + cards.map(function(c){
        return '<div style="flex:1;min-width:150px;border:1px solid #2a3446;'
          + 'border-radius:10px;padding:10px 12px">'
          + '<div class="cc" style="font-size:11px;text-transform:uppercase;'
          + 'letter-spacing:.04em">' + _aiEsc(c[0]) + '</div>'
          + '<div style="font-size:22px;font-weight:600;margin:2px 0">'
          + _aiEsc(c[1]) + '</div>'
          + '<div class="cc" style="font-size:11px">' + _aiEsc(c[2]) + '</div></div>';
      }).join("")
    + '</div>';
}

function _aiNotes(d){
  const notes = d.notes || [];
  if(!notes.length) return "";
  return '<div style="border:1px solid #3d3520;background:#221d10;border-radius:10px;'
    + 'padding:10px 12px;margin:0 0 14px;font-size:12px;line-height:1.7">'
    + notes.map(function(n){ return '<div>• ' + _aiEsc(n) + '</div>'; }).join("")
    + '</div>';
}

function _aiChart(d){
  const daily = d.daily || [];
  if(!daily.length || typeof salesChart !== "function") return "";
  // Every day in the window, not only the days with calls: a week of nothing is
  // a real fact about the spend and it should be visible as a flat stretch.
  // Zero here means "recorded, and it was nothing", which is different from the
  // nulls salesChart draws as gaps — and on this screen a day with no calls
  // genuinely did cost nothing.
  const by = {};
  daily.forEach(function(r){ by[r.day] = r; });
  const pts = [];
  let cur = new Date(d.start + "T00:00:00Z");
  const end = new Date(d.end + "T00:00:00Z");
  let guard = 0;
  while(cur <= end && guard++ < 400){
    const iso = cur.toISOString().slice(0, 10);
    const r = by[iso];
    pts.push({label: iso, value: r ? Number(r.cost || 0) : 0});
    cur = new Date(cur.getTime() + 86400000);
  }
  return '<div style="margin:0 0 16px">'
    + salesChart(pts, {title: "Spend per day", kind: "money", color: "#6ac7e8",
                       id: "aiu_daily", width: 980, height: 240,
                       subtitle: "US dollars. Hover any day for the figure."})
    + '</div>';
}

// A bar per row, drawn in plain HTML. Proportion is the whole point of this
// picture — "which account is most of the bill" — and a bar answers it faster
// than a column of numbers, without a second chart engine.
function _aiBars(title, rows, labelKey, note){
  if(!rows || !rows.length) return "";
  const max = rows.reduce(function(m, r){
    return Math.max(m, Number(r.cost || 0));
  }, 0) || 1;
  const bars = rows.slice(0, 12).map(function(r){
    const label = String(r[labelKey] || "") || "not attributed";
    const cost = Number(r.cost || 0);
    const pct = Math.max(1.5, (cost / max) * 100);
    const col = _aiColour(label);
    return '<div style="display:flex;align-items:center;gap:10px;margin:5px 0">'
      + '<div style="width:190px;font-size:12px;overflow:hidden;'
      + 'text-overflow:ellipsis;white-space:nowrap" title="' + _aiEsc(label) + '">'
      + _aiEsc(label) + '</div>'
      + '<div style="flex:1;background:#161d28;border-radius:5px;height:16px;'
      + 'position:relative;overflow:hidden">'
      + '<div style="width:' + pct.toFixed(1) + '%;height:100%;background:'
      + col + ';opacity:.75"></div></div>'
      + '<div style="width:96px;text-align:right;font-size:12px">'
      + _aiEsc(_aiMoney(r.cost)) + '</div>'
      + '<div class="cc" style="width:74px;text-align:right;font-size:11px">'
      + _aiEsc(_aiNum(r.calls)) + ' calls</div></div>';
  }).join("");
  return '<div style="flex:1;min-width:420px;border:1px solid #2a3446;'
    + 'border-radius:10px;padding:12px 14px">'
    + '<div style="font-size:13px;font-weight:600;margin-bottom:2px">'
    + _aiEsc(title) + '</div>'
    + (note ? '<div class="cc" style="font-size:11px;margin-bottom:8px">'
              + _aiEsc(note) + '</div>' : '')
    + bars
    + (rows.length > 12 ? '<div class="cc" style="font-size:11px;margin-top:6px">'
        + 'Showing the 12 largest of ' + rows.length + '.</div>' : '')
    + '</div>';
}

// The written breakdown. Asked for explicitly — "show in a dashboard in graph
// and also the other way written" — and it carries what a bar cannot: tokens,
// images, and which calls had no price.
function _aiTable(title, rows, cols, note){
  if(!rows || !rows.length) return "";
  const head = cols.map(function(c){
    return '<th style="text-align:' + (c.right ? "right" : "left")
      + ';padding:5px 8px;font-size:11px;font-weight:600;border-bottom:1px solid #2a3446">'
      + _aiEsc(c.title) + '</th>';
  }).join("");
  const body = rows.map(function(r){
    return '<tr>' + cols.map(function(c){
      return '<td style="text-align:' + (c.right ? "right" : "left")
        + ';padding:5px 8px;font-size:12px;border-bottom:1px solid #1b2330">'
        + c.cell(r) + '</td>';
    }).join("") + '</tr>';
  }).join("");
  return '<div style="margin:0 0 16px">'
    + '<div style="font-size:13px;font-weight:600;margin-bottom:2px">'
    + _aiEsc(title) + '</div>'
    + (note ? '<div class="cc" style="font-size:11px;margin-bottom:6px">'
              + _aiEsc(note) + '</div>' : '')
    + '<table style="width:100%;border-collapse:collapse">'
    + '<thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
}

function aiUsageRender(){
  const body = document.getElementById("aiu_body");
  const d = AIU.data;
  if(!body || !d) return;

  if(!d.calls){ body.innerHTML = _aiEmpty(d); return; }

  const period = '<div class="cc" style="font-size:11.5px;margin:0 0 10px">'
    + 'Between ' + _aiEsc(d.start) + ' and ' + _aiEsc(d.end)
    + (d.scoped_to ? ' — this account only.'
                   : ' — every account, so they can be compared.') + '</div>';

  const bars = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin:0 0 16px">'
    + _aiBars("Spend by account", d.by_account || [], "name",
              "Which account ran up the bill.")
    + _aiBars("Spend by feature", d.by_feature || [], "feature",
              "What the app was doing when it spent it.")
    + '</div>';

  const byAccount = _aiTable("Every account, written out", d.by_account || [], [
    {title: "Account", cell: function(r){ return _aiEsc(r.name || r.workspace_id || "not attributed"); }},
    {title: "Calls", right: true, cell: function(r){ return _aiEsc(_aiNum(r.calls)); }},
    {title: "Tokens", right: true, cell: function(r){ return _aiEsc(_aiTok(r.tokens)); }},
    {title: "Images", right: true, cell: function(r){ return _aiEsc(_aiNum(r.images)); }},
    {title: "Cost", right: true, cell: function(r){ return _aiEsc(_aiMoney(r.cost)); }},
  ]);

  const byFeature = _aiTable("Every feature, written out", d.by_feature || [], [
    {title: "Feature", cell: function(r){ return _aiEsc(r.feature || "unknown"); }},
    {title: "Calls", right: true, cell: function(r){ return _aiEsc(_aiNum(r.calls)); }},
    {title: "Tokens", right: true, cell: function(r){ return _aiEsc(_aiTok(r.tokens)); }},
    {title: "Images", right: true, cell: function(r){ return _aiEsc(_aiNum(r.images)); }},
    {title: "Cost", right: true, cell: function(r){ return _aiEsc(_aiMoney(r.cost)); }},
  ], "One generated listing is several calls — reading the product, writing the "
   + "copy, and each image is four of its own. They are listed separately "
   + "because that is what a bill is made of.");

  // The cross-tab: the actual question, answered.
  const cross = _aiTable("Which account, doing what", d.by_account_feature || [], [
    {title: "Account", cell: function(r){ return _aiEsc(r.name || r.workspace_id || "not attributed"); }},
    {title: "Feature", cell: function(r){ return _aiEsc(r.feature || "unknown"); }},
    {title: "Calls", right: true, cell: function(r){ return _aiEsc(_aiNum(r.calls)); }},
    {title: "Cost", right: true, cell: function(r){ return _aiEsc(_aiMoney(r.cost)); }},
  ], "Sorted by cost. This is the line that tells you where to look first.");

  const byModel = _aiTable("By model", d.by_model || [], [
    {title: "Model", cell: function(r){ return _aiEsc(r.model || "unknown"); }},
    {title: "Provider", cell: function(r){ return _aiEsc(r.provider || ""); }},
    {title: "Calls", right: true, cell: function(r){ return _aiEsc(_aiNum(r.calls)); }},
    {title: "Unpriced", right: true, cell: function(r){
      // Named plainly: these are the calls the total below cannot include.
      const u = Number(r.unpriced || 0);
      return u ? '<span style="color:var(--amber,#f5a623)">' + _aiEsc(_aiNum(u))
                 + '</span>' : '—';
    }},
    {title: "Cost", right: true, cell: function(r){ return _aiEsc(_aiMoney(r.cost)); }},
  ], "A model with no price in the table shows its calls under Unpriced and "
   + "contributes nothing to the cost column. That is deliberate: pricing it at "
   + "zero would be a wrong number that looks right.");

  body.innerHTML = period + _aiNotes(d) + _aiTotals(d) + _aiChart(d)
    + bars + cross + byAccount + byFeature + byModel;
}
