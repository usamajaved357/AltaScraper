// ===================== SOURCE REPRICER =====================
// What the app WOULD do to each enrolled listing, and why.
//
// The screen's whole job is to make a decision arguable before it is armed.
// So every row shows the reasoning, not just the outcome: which supplier was
// chosen, what the others were rejected for, how old the readings were, and the
// arithmetic behind the price. A number with no explanation is exactly what
// nobody should be trusting with their prices.
//
// Nothing here writes to Amazon. The buttons re-read suppliers and re-decide;
// arming the repricer is Phase D and is deliberately not reachable from here.

let SRC_ROWS = [];
let SRC_RULE = null;
let SRC_MASTER = false;     // the master switch, as the SERVER reports it

// Every /sourcing call says WHICH account and marketplace it means.
//
// It used to rely on the server's active_marketplace, which this screen never
// sets -- opening the Repricer directly left it empty, so it looked up
// jack_uk::"" , found nothing, and reported "no live listings cached" for an
// account with 55 of them. The browser already knows both; sending them removes
// the guess entirely.
function _srcScope(){
  const p = [];
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
    p.push("id=" + encodeURIComponent(CUR_ACCOUNT.id));
  if(typeof WS_MARKET !== "undefined" && WS_MARKET)
    p.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return p.join("&");
}
function _srcUrl(path, extra){
  const q = [_srcScope(), extra || ""].filter(Boolean).join("&");
  return path + (q ? (path.indexOf("?") >= 0 ? "&" : "?") + q : "");
}
function _srcBody(o){
  const b = Object.assign({}, o || {});
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id) b.id = CUR_ACCOUNT.id;
  if(typeof WS_MARKET !== "undefined" && WS_MARKET) b.marketplace = WS_MARKET;
  return JSON.stringify(b);
}

function _sesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
// An argument for an inline onclick. Single-quoted for JS, then escaped for the
// attribute -- see the same helper in users.js and the bug that made it
// necessary: JSON.stringify closes the attribute it is pasted into.
function _sarg(s){
  const js = String(s==null?"":s).replace(/\\/g,"\\\\").replace(/'/g,"\\'");
  return "'" + js.replace(/&/g,"&amp;").replace(/"/g,"&quot;")
                 .replace(/</g,"&lt;").replace(/>/g,"&gt;") + "'";
}
function _smoney(v){
  return (v==null || v==="") ? "—" : Number(v).toFixed(2);
}

function sourcingOnOpen(){ sourcingLoad(); }

async function sourcingLoad(){
  const body = document.getElementById("srcbody");
  if(!body) return;
  body.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading…</div>';
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/list"))).json(); }
  catch(e){ body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">Could not load: '+_sesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>';
    return;
  }
  SRC_ROWS = j.rows || [];
  SRC_RULE = j.rule || j.defaults || {};
  // Read from the server, never remembered from the last click: whether the app
  // is currently allowed to change prices is not something to guess at.
  try{ SRC_MASTER = !!(await (await fetch(_srcUrl("/sourcing/master"))).json()).enabled; }
  catch(e){ SRC_MASTER = false; }
  sourcingRender(j);
}

async function sourcingMaster(on){
  if(on && !confirm("Turn the master switch ON?\n\nArmed SKUs will then have their "
                  + "price, stock and handling time changed on Amazon automatically. "
                  + "SKUs still in dry run are unaffected.")) return;
  try{
    const j = await (await fetch("/sourcing/master",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({enabled:!!on})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast(j.enabled ? "Master switch ON" : "Master switch off — nothing will be pushed");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingArm(sku, live){
  if(live && !confirm("Arm "+sku+"?\n\nFrom then on the app may change this listing's "
                    + "price, stock and handling time on Amazon by itself.")) return;
  try{
    const j = await (await fetch("/sourcing/arm",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, live:!!live})})).json();
    if(!j.ok){ toast(j.error||"Could not arm"); return; }
    toast(j.note || (j.mode==="live" ? "Armed" : "Back to dry run"));
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingMinPrice(sku){
  const v = prompt("Lowest price you will ever sell "+sku+" at.\n\nThis is the one "
                 + "guard that still works if a supplier's page is misread, so the "
                 + "app will not arm a SKU without it.");
  if(v===null) return;
  try{
    const j = await (await fetch("/sourcing/rules",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, rule:{min_price: v===""? null : parseFloat(v)}})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast("Minimum price saved"); sourcingLoad();
  }catch(e){ toast(String(e)); }
}

// A PERCENTAGE PROFIT FLOOR, on top of the flat one.
//
// "i want an option in which i can enroll an option to maintain atleast 20
//  percent margin or roi, a user should be able to set. and if some items are
//  less than that flag it"
//
// Margin and ROI are asked for in the same breath and are not the same number:
// on an 11.95 unit a 20% target is 26.08 as margin and 22.76 as ROI. So the
// choice is made explicitly rather than picked for you, and the difference is
// spelled out where the choice is made.
async function sourcingTarget(sku){
  const scope = sku ? ('"' + sku + '"') : "every enrolled SKU";
  const kind = prompt(
    "Least profit you will accept on " + scope + ".\n\n"
  + "Type  margin  — profit as a share of what the CUSTOMER pays.\n"
  + "      Strict: Amazon's 15% comes out of the same price, so a margin\n"
  + "      target above about 84% cannot be met at any price.\n\n"
  + "Type  roi     — profit as a share of what YOU paid for the unit.\n"
  + "      On a £11.95 unit, 20% ROI wants £22.76 and 20% margin wants £26.08.\n\n"
  + "Leave blank to remove the target and go back to the flat minimum profit.",
    "roi");
  if(kind === null) return;
  const k = String(kind).trim().toLowerCase();
  let pct = null;
  if(k){
    const v = prompt("What percentage? e.g. 20", "20");
    if(v === null) return;
    pct = parseFloat(String(v).replace("%", "").trim());
    if(!(pct > 0)){ toast("That is not a percentage."); return; }
  }
  try{
    const j = await (await fetch("/sourcing/rules",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku||"", rule:{profit_target_kind: k||null,
                                        profit_target_pct: k?pct:null}})})).json();
    // The server refuses an unreachable or mistyped target and says why. Shown
    // as-is: a target that silently did nothing would leave you believing a
    // floor was in force while the app priced to the flat £1.
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast(k ? ("Target set: " + pct + "% " + k) : "Profit target removed");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

// The chip on a row that is not earning what it is supposed to. Deliberately
// says how far short, not just that it is short -- 0.4% under is a rounding
// argument and 12% under is a supplier you should stop buying from.
function _targetChip(t){
  if(!t) return '';                       // no target set on this SKU
  if(t.meets === null) return '';          // not enough to tell; not a failure
  if(t.meets){
    return '<span class="db-chip" style="background:#12321f;color:#7fd18b" title="'
      +  'Earning ' + t.actual_pct + '% against a ' + t.target_pct + '% '
      +  t.kind + ' target.">' + t.kind + ' ' + t.actual_pct + '%</span>';
  }
  return '<span class="db-chip" style="background:#3a1b1b;color:#e88a8a" title="'
    +  'This listing is earning ' + t.actual_pct + '% ' + t.kind + ' at its '
    +  'current price, against your ' + t.target_pct + '% target — '
    +  t.short_by + ' points short'
    +  (t.profit != null ? ' (' + _smoney(t.profit) + ' a unit).' : '.')
    +  '">below target &middot; ' + t.actual_pct + '%</span>';
}

// Start tracking everything that is not tracked yet.
//
// The supplier link is not asked for: the app recorded where each listing came
// from when it built it, so it can attach them itself. What it CANNOT do is
// invent one for a listing whose source was an Amazon page -- that is the
// competitor the listing was modelled on, not where the stock is bought -- so
// those are enrolled and reported rather than quietly skipped.
async function sourcingTrackAll(btn){
  const old = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled = true; btn.innerHTML = '<span class="genspin"></span> reading your listings…'; }
  try{
    const cand = await (await fetch("/sourcing/candidates")).json();
    const items = (cand && cand.items) || [];
    const todo = items.filter(function(x){ return !x.enrolled; }).map(function(x){ return x.sku; });
    if(!items.length){
      toast((cand && cand.note) || "No live listings to track — press Sync on Listings first.");
      return;
    }
    if(!todo.length){ toast("Every live listing is already being tracked."); return; }
    if(!confirm("Start tracking " + todo.length + " listing" + (todo.length===1?"":"s") + "?\n\n"
              + "This records what each one costs at its supplier, every 4 hours.\n"
              + "It does NOT change any price — auto-pricing stays "
              + (SRC_MASTER ? "as it is" : "off") + ", and each SKU still has to be "
              + "armed separately before anything can reach Amazon.")) return;
    if(btn) btn.innerHTML = '<span class="genspin"></span> tracking ' + todo.length + '…';
    const j = await (await fetch("/sourcing/enrol_bulk",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({skus: todo})})).json();
    if(!j.ok){ toast(j.error||"Could not enrol"); return; }
    // Say what did NOT work as loudly as what did. A bulk action that reports
    // only its successes is how you end up with SKUs quietly tracking nothing.
    let msg = "Now tracking " + j.enrolled + " listing" + (j.enrolled===1?"":"s")
            + " — " + j.linked + " with the supplier the app already had on file";
    if(j.no_link) msg += ", " + j.no_link + " still need a supplier link";
    toast(msg + ".");
    SRC_LASTBULK = j.rows || [];
    sourcingLoad();
  }catch(e){ toast(String(e)); }
  finally{ if(btn){ btn.disabled = false; btn.innerHTML = old; } }
}
let SRC_LASTBULK = null;

// SUPPLIERS FROM A SHEET.
//
// "the repricer tool give me an option to upload a sheet containing the sku's or
//  original asins of the item, to add their suppliers through a sheet upload"
//
// The report is shown ROW BY ROW, not as a total. A bulk import that says "38
// attached" and nothing else is how twelve silently-skipped rows become "the
// repricer is not working" a fortnight later.
async function sourcingUpload(inp){
  const f = inp && inp.files && inp.files[0];
  if(!f) return;
  const host = document.getElementById("srcbody");
  const fd = new FormData();
  fd.append("file", f);
  toast("Reading " + f.name + "…");
  let j;
  try{
    j = await (await fetch("/sourcing/sources/upload", {method: "POST", body: fd})).json();
  }catch(e){ toast(String(e)); return; }
  finally{ inp.value = ""; }

  if(!j.ok){ toast(j.error || "Could not read that sheet"); return; }
  SRC_LASTBULK = j;
  toast(j.attached + " supplier" + (j.attached === 1 ? "" : "s") + " attached"
        + (j.already ? (", " + j.already + " already had one") : "")
        + (j.skipped ? (", " + j.skipped + " skipped") : "") + ".");
  sourcingLoad();
}

// What the last upload did to each row, offered rather than forced: it is long,
// and it is only interesting until you have read it.
function sourcingUploadReport(){
  const j = SRC_LASTBULK;
  if(!j) return '';
  const bad = (j.rows || []).filter(function(r){ return r.status !== "attached"; });
  return '<details class="foldgroup" style="margin-bottom:12px"><summary>'
    + '<i class="ti ti-table-import"></i> Last sheet upload &mdash; '
    + j.attached + ' attached'
    + (j.already ? (', ' + j.already + ' already had one') : '')
    + (j.skipped ? ('<b style="color:#e8c66a">, ' + j.skipped + ' skipped</b>') : '')
    + '<span class="cc"> — matched on "' + _sesc((j.columns||{}).sku || (j.columns||{}).asin || '?')
    + '" and "' + _sesc((j.columns||{}).url || '?') + '"</span></summary>'
    + (bad.length
        ? bad.map(function(r){
            return '<div class="cc" style="font-size:11.5px;padding:3px 0;'
              + 'border-top:1px solid #1c2531">line ' + r.line + ' &middot; '
              + _sesc(r.sku || r.asin || '(no key)') + ' &mdash; ' + _sesc(r.note) + '</div>';
          }).join("")
        : '<div class="cc" style="font-size:11.5px;padding:4px 0">Every row went in.</div>')
    + '</details>';
}

function sourcingRender(j){
  const body = document.getElementById("srcbody");
  const c = j.counts || {};
  let h = "";

  // The standing statement of what the app is doing to real listings right now.
  // It sits at the top rather than in a footnote because "is this live?" is the
  // only question that really matters, and the answer must never be a guess.
  const live = SRC_ROWS.filter(function(r){ return r.mode==="live"; }).length;
  if(SRC_MASTER && live){
    h += '<div style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
      +  'border:1px solid #4a2323;background:#2a1212;border-radius:6px">'
      +  '<b style="color:#e88a8a">Live.</b> '+live+' SKU'+(live===1?" is":"s are")
      +  ' armed and can have their price, stock and handling time changed on '
      +  'Amazon without anyone watching. At most one change each per 4 hours, '
      +  'and never below the minimum price you set. '
      +  '<button class="db-chip" onclick="sourcingMaster(false)" '
      +  'style="margin-left:6px">Stop everything</button></div>';
  } else {
    // TRACKING IS NOT PRICING, and the screen has to say so.
    //
    // "uploading or selecting the skus in the repricer means to track their true
    //  costs from the sources" -- which is what enrolling has always done, but
    //  the screen called itself the repricer and implied that adding a SKU
    //  handed it your prices. It does not, and that is the reason it is safe to
    //  add all of them.
    // Short line, detail on the dot -- the pattern asked for on the notices
    // ("i think this is the right way to write notices"). This was five lines of
    // prose across the top of the screen, which is a paragraph nobody finishes.
    h += '<div class="cc" style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
      +  'border:1px solid #26403a;background:#10231f;border-radius:6px">'
      +  '<b>Tracking costs. Auto-pricing is off.</b> '
      +  'Suppliers are read every 4 hours and what each unit really costs is '
      +  'written down. Nothing changes a live listing.'
      +  '<span class="infodot" title="'
      +  'It also works out what it WOULD price at, so the decisions can be read '
      +  'before they are trusted - if one looks wrong here, it would have been '
      +  'wrong on Amazon. Adding a SKU is safe: it starts the cost history and '
      +  'nothing more, and each SKU still has to be armed separately. A supplier '
      +  'price on a day nobody was watching cannot be recovered later, which is '
      +  'the reason to add them before you need them.">i</span>'
      +  (SRC_MASTER ? ' <b>Auto-pricing is on</b>, but no SKU is armed for it yet.'
                     : '')
      +  '</div>';
  }

  h += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">'
    +  '<button class="db-chip" onclick="sourcingCheckNow(this)">'
    +  '<i class="ti ti-refresh"></i> Re-read suppliers now</button>'
    +  '<button class="db-chip" onclick="sourcingAddPrompt()">'
    +  '<i class="ti ti-plus"></i> Track a SKU</button>'
    +  '<button class="db-chip go" onclick="sourcingTrackAll(this)" title="'
    +  'Starts watching every live listing that is not already tracked, and '
    +  'attaches the supplier link the app recorded when it built each one. '
    +  'Changes no prices.">'
    +  '<i class="ti ti-eye"></i> Track everything</button>'
    // Suppliers from a sheet. A file input the browser draws itself arrives as
    // the one light-grey control on a dark panel, so it is off-screen behind a
    // label -- the same fix the image library needed.
    +  '<input type="file" id="src_upload" accept=".csv,.tsv,.xlsx,.xlsm,.xls" '
    +  'class="visually-hidden" onchange="sourcingUpload(this)">'
    +  '<label class="db-chip" for="src_upload" style="cursor:pointer" title="'
    +  'A sheet of supplier links. One column of SKUs or ASINs, one column of '
    +  'links — the app matches each link to the right listing and starts '
    +  'tracking it. Nothing is priced.">'
    +  '<i class="ti ti-table-import"></i> Suppliers from a sheet</label>'
    // The switch that actually matters, named for what it does rather than for
    // where it lives. "Master switch: off" did not say off from WHAT.
    +  '<button class="db-chip'+(SRC_MASTER?' risk':'')+'" '
    +  'onclick="sourcingMaster('+(SRC_MASTER?"false":"true")+')" title="'
    +  (SRC_MASTER ? 'Auto-pricing is ON. Armed SKUs can have their price, stock '
                   + 'and handling time changed on Amazon without anyone watching.'
                   : 'Auto-pricing is OFF. Costs are still tracked and decisions '
                   + 'still recorded; nothing reaches Amazon.')+'">'
    +  (SRC_MASTER ? '<i class="ti ti-lock-open"></i> Auto-pricing: ON'
                   : '<i class="ti ti-lock"></i> Auto-pricing: off')+'</button>'
    +  '<button class="db-chip" onclick="sourcingTarget(\'\')" title="'
    +  'The least profit you will accept, as a percentage. Applies to every '
    +  'enrolled SKU unless one has its own.">'
    +  '<i class="ti ti-target"></i> '
    +  (((j.rule||{}).profit_target_kind && (j.rule||{}).profit_target_pct)
        ? ('Target: '+(j.rule).profit_target_pct+'% '+(j.rule).profit_target_kind)
        : 'Profit target: none')
    +  '</button>'
    +  '</div>';
  // The numbers get cards of their own, under the controls rather than crammed
  // into them.
  if(SRC_ROWS.length) h += _srcCounts(c);
  h += sourcingUploadReport();

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:10px;border:1px dashed #2a3446;border-radius:6px">'
      +  _sesc(j.note)+' Enrol a SKU above to start watching its suppliers.</div>';
    body.innerHTML = h; return;
  }

  SRC_ROWS.forEach(function(r, i){ h += sourcingRow(r, i); });
  body.innerHTML = h;
}

// A SUPPLIER LINK IS NOT DATA TO READ.
//
// The reason lines printed the whole URL, and an eBay link carries its search
// terms with it: "...itm/235976183512?_skw=ct3123+Universal+Security+Coupling+
// Hitch+Lock+for+Trailers+Caravan+Horse+Box+Tow+Ball+Fittings%2C+Yellow&itmmeta=
// 01KX041JXHMKKKAPC9ZYBA58YW&hash=item36f146ced8..." -- two hundred characters
// of machine noise per row, wrapping to three lines and burying the sentence
// that actually mattered. The item number is the part a person can use.
function _srcShort(url){
  const u = String(url || "");
  const m = u.match(/\/itm\/(\d{9,15})/);
  if(m) return "eBay item " + m[1];
  try{ return (u.split("/")[2] || u).replace(/^www\./, ""); }
  catch(e){ return u.slice(0, 40); }
}

// The same shortening, applied to a sentence that has URLs embedded in it. The
// reason strings are written server-side as the permanent audit record and are
// deliberately not changed -- this is only how they are drawn.
// Split on the RAW url, then escape each piece. Escaping first and matching
// afterwards does not work: _sesc turns & into &amp;, and an eBay link is mostly
// ampersands, so a pattern that stops at ";" stops inside the first entity and
// leaves the rest of the query string sitting there as text. That is exactly
// what it did, which is why half of each link was still on screen.
function _srcTidy(text){
  const s = String(text || "");
  const re = /https?:\/\/\S+/g;
  let out = "", last = 0, m;
  while((m = re.exec(s)) !== null){
    let url = m[0];
    // Trailing punctuation belongs to the sentence, not to the link.
    const tail = url.match(/[),.;:]+$/);
    if(tail){ url = url.slice(0, -tail[0].length); }
    out += _sesc(s.slice(last, m.index))
        +  '<a href="' + _sesc(url) + '" target="_blank" rel="noopener" title="'
        +  _sesc(url) + '">' + _sesc(_srcShort(url)) + '</a>'
        +  (tail ? _sesc(tail[0]) : "");
    last = m.index + m[0].length;
  }
  return out + _sesc(s.slice(last));
}

// The counts, as cards. They were a run of text in the toolbar -- "17 would
// change · 7 would go out of stock · 31 unchanged · 19 held" -- which is the
// same information Sales gives five cards to, on a screen where those numbers
// are the whole point of looking.
function _srcCounts(c){
  const cards = [
    ["would change", c.update || 0, "var(--accent)"],
    ["would go out of stock", c.out_of_stock || 0, "var(--red)"],
    ["held for review", c.blocked || 0, "var(--warn)"],
    ["unchanged", c.none || 0, ""],
  ];
  if(c.below_target) cards.push(["below target", c.below_target, "var(--red)"]);
  return '<div style="display:grid;gap:10px;margin-bottom:14px;'
    +  'grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">'
    +  cards.map(function(k){
         return '<div class="panelcard" style="padding:12px 14px">'
           +  '<div style="font-size:24px;font-weight:600;line-height:1.15'
           +  (k[2] ? ';color:' + k[2] : '') + '">' + k[1] + '</div>'
           +  '<div class="cc" style="font-size:11.5px;margin-top:2px">' + k[0] + '</div>'
           +  '</div>';
       }).join("")
    +  '</div>';
}

function _actionChip(d){
  const a = d.action;
  if(d.blocked_by) return '<span class="db-chip" style="background:#3a2f12;color:#e8c66a">held</span>';
  if(a==="update") return '<span class="db-chip" style="background:#12303a;color:#6ac7e8">would change</span>';
  if(a==="out_of_stock") return '<span class="db-chip" style="background:#3a1b1b;color:#e88a8a">would go out of stock</span>';
  return '<span class="db-chip">no change</span>';
}

// What we thought a unit cost, against what the supplier charges now. Shown on
// the collapsed row, because a cost that has drifted is not something you would
// know to go looking for -- it has to be in front of you.
function _driftChip(dr){
  if(!dr || dr.delta==null) return '';
  const worse = dr.delta > 0, flat = dr.delta === 0;
  const col = flat ? '' : (worse ? 'background:#3a2f12;color:#e8c66a'
                                 : 'background:#12321f;color:#7fd18b');
  const sign = dr.delta > 0 ? '+' : '';
  return '<span class="db-chip" style="'+col+'" title="'
    +  'This SKU was created when the source cost '+_smoney(dr.cogs)+'. '
    +  'The supplier now charges '+_smoney(dr.landed)+' delivered to you. '
    +  (worse ? 'Every profit figure for this SKU still subtracts the old, lower cost, '
             +  'so profit is overstated by '+_smoney(dr.delta)+' a unit.'
             : (flat ? 'Unchanged since the listing was created.'
                     : 'It is cheaper than when the listing was created.'))
    +  '">cost '+(flat ? 'unchanged' : (worse?'up':'down'))
    +  (flat ? '' : ' '+sign+dr.pct+'%')+'</span>';
}

// The sum, laid out. It exists because the one-sentence version of this was
// accurate and unreadable: "price 20.33 = 11.28 cost + 3.05 fee + 3.00 postage
// + 2.00 ads + 1.00 profit" is five numbers and a total run together, and the
// question it has to answer -- "where did my price come from" -- is answered
// much better by a list than by a sentence. The sentence is still what gets
// stored in the log, unchanged; this is only how it is drawn.
function _priceBreakdown(b, cur){
  if(!b || b.price==null) return '';
  const line = function(label, v, note){
    return '<div style="display:flex;gap:8px;font-size:11.5px;padding:1.5px 0">'
      +  '<span style="min-width:186px" class="cc">'+label+'</span>'
      +  '<span style="min-width:62px;text-align:right">'+_smoney(v)+'</span>'
      +  '<span class="cc">'+(note||'')+'</span></div>';
  };
  let h = '<div class="cc" style="font-size:11px;margin:9px 0 3px">'
        + 'How this price was worked out</div>';
  h += line('What the supplier charges', b.supplier_price, '');
  if(b.supplier_postage!=null && b.supplier_postage>0)
    h += line('Their postage to you', b.supplier_postage, '');
  h += line('So one unit costs you', b.cost, 'delivered to your door');
  h += line("Amazon's cut", b.fee,
            Math.round((b.fee_rate||0)*100)+'% of the selling price, not of the cost');
  h += line('Your postage to the buyer', b.postage_label, 'the shipping label');
  h += line('Set aside for ads', b.ads, '');
  h += line('Profit left over', b.profit, 'what you keep per unit');
  h += '<div style="display:flex;gap:8px;font-size:12px;font-weight:600;'
    +  'padding:5px 0 0;margin-top:3px;border-top:1px solid #26303f">'
    +  '<span style="min-width:186px">Price it should sell at</span>'
    +  '<span style="min-width:62px;text-align:right">'+_smoney(b.price)+'</span>'
    +  '<span class="cc" style="font-weight:400">'
    +  (cur && cur.price!=null ? 'it is '+_smoney(cur.price)+' now' : '')+'</span></div>';
  if(b.lead_days!=null){
    h += '<div class="cc" style="font-size:11.5px;margin-top:5px">'
      +  'Handling time '+b.lead_days+' days &mdash; the supplier says '
      +  b.supplier_dispatch_days+' to dispatch, plus '+b.buffer_days
      +  ' spare so a slow day does not make you late.</div>';
  }
  if(b.sources_total>1){
    h += '<div class="cc" style="font-size:11.5px;margin-top:3px">'
      +  'Cheapest of '+b.sources_usable+' usable supplier'
      +  (b.sources_usable===1?'':'s')+' out of '+b.sources_total+'.</div>';
  }
  return h;
}

// Every reading we hold for one supplier, newest first. Two readings that never
// move are how you tell a stable price from a stale one, so failures are listed
// rather than hidden.
function _sourceHistory(hist){
  if(!hist || hist.length<2) return '';
  let h = '<div class="cc" style="font-size:11px;margin:5px 0 2px">'
        + 'What this supplier has charged</div>';
  hist.forEach(function(c){
    h += '<div style="display:flex;gap:8px;font-size:11px;padding:1px 0">'
      +  '<span class="cc" style="min-width:132px">'+_sesc(c.at||'')+'</span>'
      +  '<span style="min-width:70px">'
      +  (c.landed!=null ? _smoney(c.landed) : '<span class="cc">could not read</span>')
      +  '</span>'
      +  '<span class="cc">'+(c.status!=='fetched' ? _sesc(c.status||'')
                              : (c.in_stock===false ? 'out of stock' : ''))+'</span>'
      +  '</div>';
  });
  return h;
}

// One line of facts under each SKU. Six small labelled figures rather than a
// sentence, because these are numbers you scan down a column, not read.
function _glanceRow(g){
  if(!g) return '';
  const cell = function(label, value, tone, title){
    if(value === null || value === undefined || value === "") return '';
    return '<span title="' + _sesc(title || '') + '" style="display:inline-flex;'
      + 'flex-direction:column;line-height:1.25;min-width:74px">'
      + '<span style="font-size:12.5px;font-weight:600'
      + (tone ? (';color:' + tone) : '') + '">' + value + '</span>'
      + '<span class="cc" style="font-size:10px">' + label + '</span></span>';
  };
  const pct = function(v){ return (v === null || v === undefined) ? null
                                  : (v.toFixed ? v.toFixed(1) : v) + '%'; };
  // Margin and ROI answer different questions, so they are coloured against
  // different thresholds rather than one shared rule of thumb.
  const mTone = (g.margin_pct === null || g.margin_pct === undefined) ? ''
              : (g.margin_pct >= 20 ? 'var(--ok)'
                 : g.margin_pct >= 8 ? 'var(--warn)' : 'var(--red)');
  const rTone = (g.roi_pct === null || g.roi_pct === undefined) ? ''
              : (g.roi_pct >= 30 ? 'var(--ok)'
                 : g.roi_pct >= 12 ? 'var(--warn)' : 'var(--red)');
  const stockTone = (g.units_available === null || g.units_available === undefined) ? ''
                  : (g.units_available <= 0 ? 'var(--red)'
                     : g.units_available <= 3 ? 'var(--warn)' : '');
  const bits = [
    cell('source price', _smoney(g.landed),
         '', 'What one unit costs you delivered: '
         + _smoney(g.source_price) + ' + ' + _smoney(g.source_postage) + ' postage'),
    cell('sells at', _smoney(g.sell_price), '',
         'What Amazon is charging for it right now'),
    cell('profit / unit', _smoney(g.profit), mTone,
         'At the current price, after Amazon’s cut, your postage label and the ads allowance'),
    cell('margin', pct(g.margin_pct), mTone, 'Profit as a share of the selling price'),
    cell('ROI', pct(g.roi_pct), rTone, 'Profit as a share of what you paid for the unit'),
    cell('units at source', g.units_available, stockTone,
         'How many the supplier says are left. eBay sometimes reports a floor rather than a count.'),
    cell('handling', (g.handling_days == null ? null : g.handling_days + 'd'), '',
         'Supplier dispatch ' + (g.dispatch_days == null ? '?' : g.dispatch_days)
         + 'd plus the safety buffer — what would be promised to the buyer'),
  ].filter(Boolean);
  if(!bits.length) return '';
  return '<div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;'
       + 'padding:8px 10px;background:var(--panel2);border-radius:6px">'
       + bits.join("") + '</div>';
}

function sourcingRow(r, i){
  const d = r.decision || {}, cur = r.current || {};
  const id = "srcrow_"+i;
  let h = '<div style="border:1px solid #26303f;border-radius:7px;padding:10px 12px;margin-bottom:9px">';

  h += '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">'
    +  '<code style="font-size:12px">'+_sesc(r.sku)+'</code>'
    +  _actionChip(d)
    +  _driftChip(r.drift)
    +  _targetChip(d.target)
    +  '<span style="flex:1"></span>'
    +  '<span class="cc" style="font-size:11.5px">now '+_smoney(cur.price)
    +  (cur.lead_days!=null ? ' &middot; '+cur.lead_days+'d handling' : '')
    +  '</span>';
  if(d.action==="update"){
    h += '<span style="font-size:12px;font-weight:600">&rarr; '+_smoney(d.price)
      +  (d.lead_days!=null ? ' &middot; '+d.lead_days+'d' : '')+'</span>';
  }
  h += '<button class="db-chip" onclick="sourcingToggleDetail('+_sarg(id)+')">Why?</button>'
    +  (r.mode==="live"
        ? '<button class="db-chip" style="background:#3a1b1b;color:#e88a8a" '
          + 'onclick="sourcingArm('+_sarg(r.sku)+',false)">Armed &mdash; disarm</button>'
        : '<button class="db-chip" onclick="sourcingArm('+_sarg(r.sku)+',true)">Arm</button>')
    +  '<button class="db-chip" onclick="sourcingUnenrol('+_sarg(r.sku)+')">Remove</button>'
    +  '</div>';

  // THE ROW AT A GLANCE.
  //
  // "i want to add some additional info which give me a glance view to be
  //  displayed on each sku, current source price, current my selling price on
  //  which the item will be sold if i receive an order and the profit margin and
  //  the roi i will generate on the sale. source units available, the shipping
  //  days of the supplier"
  //
  // Every figure is about the sale that would happen NOW -- what Amazon is
  // charging today against what the supplier charges today -- which is a
  // different question from the price the repricer would LIKE it to be. That one
  // is already on the line above.
  //
  // Blank where unknown. A margin shown as 0% because nothing could be read is a
  // number somebody would act on.
  h += _glanceRow(r.glance);

  // The reason line is the point of the whole screen.
  h += '<div class="cc" style="font-size:11.5px;margin-top:5px;line-height:1.5">'
    +  (d.blocked_by ? '<b style="color:#e8c66a">'+_sesc(d.blocked_by)+'</b> &mdash; ' : '')
    +  _srcTidy(d.reason||"")+'</div>';

  h += '<div id="'+id+'" style="display:none;margin-top:9px">';

  h += _priceBreakdown(d.breakdown, cur);

  // What the target is doing to THIS listing, under the sum it changes. The
  // chip above is the flag; this says what it would take to clear it, which is
  // the number you need to decide whether the supplier is still worth buying
  // from at all.
  const tg = d.target, bd = d.breakdown || {};
  if(tg && tg.meets === false){
    h += '<div class="cc" style="font-size:11.5px;margin-top:7px;padding:6px 8px;'
      +  'border:1px solid #4a2323;background:#2a1212;border-radius:6px">'
      +  'At its current price this earns <b>'+tg.actual_pct+'%</b> '+tg.kind
      +  (tg.profit!=null ? ' &mdash; '+_smoney(tg.profit)+' a unit' : '')
      +  ', against your <b>'+tg.target_pct+'%</b> target. '
      +  (bd.target_floor!=null
          ? 'It would need <b>'+_smoney(bd.target_floor)+'</b> to clear it.'
          : '')
      +  '</div>';
  }

  // The cost comparison in words, under the sum it affects. The chip in the
  // header is the flag; this is the sentence that says what it means, because
  // "cost up 9%" does not on its own tell you that a profit figure is wrong.
  const dr = r.drift || {};
  if(dr.delta!=null && dr.delta!==0){
    h += '<div class="cc" style="font-size:11.5px;margin-top:7px;padding:6px 8px;'
      +  'border:1px solid #2a3446;border-radius:6px">'
      +  'This SKU was created when a unit cost <b>'+_smoney(dr.cogs)+'</b>'
      +  (dr.cogs_source==='manual' ? ' (you set that by hand)' : ' (from the SKU name)')
      +  '. The supplier now charges <b>'+_smoney(dr.landed)+'</b> delivered. '
      +  (dr.delta>0
          ? 'Profit figures for this SKU still subtract the old '+_smoney(dr.cogs)
            + ', so they are overstated by about '+_smoney(dr.delta)+' on every unit sold.'
          : 'It is cheaper than it was, so profit figures are understating it by about '
            + _smoney(Math.abs(dr.delta))+' a unit.')
      +  '</div>';
  }

  h += '<div class="cc" style="font-size:11px;margin:9px 0 4px">Suppliers</div>';
  (r.sources||[]).forEach(function(s){
    const k = s.check || {};
    const rej = (d.rejections||[]).find(function(x){ return x.source_id===s.id; });
    const chosen = d.source_id===s.id;
    h += '<div style="display:flex;gap:8px;align-items:center;font-size:11.5px;'
      +  'padding:4px 0;border-top:1px solid #1c2531">'
      +  (chosen ? '<span class="db-chip" style="background:#12303a;color:#6ac7e8">using</span>'
                 : '<span class="db-chip" style="opacity:.55">—</span>')
      +  '<a href="'+_sesc(s.url)+'" target="_blank" rel="noopener" title="'+_sesc(s.url)+'" '
      +  'style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
      +  _sesc(_srcShort(s.url))+'</a>'
      +  '<span class="cc">'+_sesc(s.kind)+'</span>'
      +  '<span style="flex:1"></span>'
      +  '<span>'+_smoney(k.price)+' + '+(k.shipping==null?'<b style="color:#e8c66a">postage unknown</b>':_smoney(k.shipping))+'</span>'
      +  '<span class="cc">'+(k.in_stock===true?'in stock':k.in_stock===false?'out of stock':'stock unknown')+'</span>'
      +  '<span class="cc">'+(k.dispatch_days==null?'':k.dispatch_days+'d')+'</span>'
      +  (rej ? '<span class="cc" style="color:#e8c66a">'+_sesc(rej.reason)+'</span>' : '')
      +  '<button class="db-chip" onclick="sourcingRemoveSource('+s.id+')">×</button>'
      +  '</div>';
    h += _sourceHistory(s.history);
  });
  if(!(r.sources||[]).length){
    h += '<div class="cc" style="font-size:11.5px;padding:4px 0">'
      +  'No suppliers yet &mdash; nothing can be decided until one is added.</div>';
  }
  h += '<div style="margin-top:7px"><button class="db-chip" '
    +  'onclick="sourcingAddSourcePrompt('+_sarg(r.sku)+')">'
    +  '<i class="ti ti-plus"></i> Add a supplier link</button></div>';
  // The minimum price is shown whether or not it is set, because its ABSENCE is
  // the reason a SKU cannot be armed, and that has to be visible at the point of
  // trying rather than only in the error message afterwards.
  const mp = (r.rule||{}).min_price;
  h += '<div class="cc" style="font-size:11.5px;margin-top:7px">Never sell below: '
    +  (mp==null
        ? '<b style="color:#e8c66a">not set</b> — required before this SKU can be armed'
        : '<b>'+_smoney(mp)+'</b>')
    +  ' <button class="db-chip" onclick="sourcingMinPrice('+_sarg(r.sku)+')">'
    +  (mp==null?'Set':'Change')+'</button></div>';
  // The target, per SKU. A cheap fast-moving line and an expensive slow one do
  // not want the same percentage, so the account-wide setting is a default
  // rather than a rule.
  const tk = (r.rule||{}).profit_target_kind, tp = (r.rule||{}).profit_target_pct;
  h += '<div class="cc" style="font-size:11.5px;margin-top:5px">Least profit accepted: '
    +  ((tk && tp!=null) ? '<b>'+tp+'% '+_sesc(tk)+'</b>'
                         : '<span class="cc">the flat minimum only</span>')
    +  ' <button class="db-chip" onclick="sourcingTarget('+_sarg(r.sku)+')">'
    +  ((tk && tp!=null)?'Change':'Set')+'</button></div>';
  if(d.inputs_age_mins!=null){
    h += '<div class="cc" style="font-size:11px;margin-top:6px">Decided on a reading '
      +  Math.round(d.inputs_age_mins)+' minutes old.</div>';
  }
  h += '</div></div>';
  return h;
}

function sourcingToggleDetail(id){
  const el = document.getElementById(id);
  if(el) el.style.display = (el.style.display==="none") ? "block" : "none";
}

async function sourcingCheckNow(btn){
  if(btn){ btn.disabled=true; btn.innerHTML='<span class="genspin"></span> reading…'; }
  try{
    const j = await (await fetch("/sourcing/check",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:_srcBody({})})).json();
    if(!j.ok){ toast(j.error||"Could not read the suppliers"); return; }
    const f = j.fetch || {};
    let msg = "Read "+(f.checked||0)+" supplier"+((f.checked===1)?"":"s");
    if(f.unreadable) msg += " · "+f.unreadable+" unreadable";
    if(f.ended) msg += " · "+f.ended+" ended";
    toast(f.note || msg);
    await sourcingLoad();
  }catch(e){ toast("Failed: "+((e&&e.message)||e)); }
  finally{ if(btn){ btn.disabled=false; btn.innerHTML='<i class="ti ti-refresh"></i> Re-read suppliers now'; } }
}

// Pick from what is actually on Amazon, rather than typing a SKU from memory.
// A typed SKU with a typo in it enrols a product that does not exist: the sweep
// finds no sources, the screen shows a row that never decides anything, and
// nothing anywhere says the SKU was wrong.
async function sourcingAddPrompt(){
  const host = document.getElementById("srcpick");
  if(!host) return;
  host.style.display = "block";
  host.innerHTML = '<div class="cc" style="padding:14px"><span class="genspin"></span> Loading this account\'s live listings…</div>';
  await sourcingPickerLoad("");
}

async function sourcingPickerLoad(q){
  const host = document.getElementById("srcpick");
  if(!host) return;
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/candidates","q="+encodeURIComponent(q||"")))).json(); }
  catch(e){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>'; return; }

  let h = '<div style="border:1px solid #26303f;border-radius:8px;padding:12px;margin-bottom:12px">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
    + '<b style="font-size:13px">Enrol a listing</b>'
    + '<span class="cc" style="font-size:11px">'+j.count+' live on this account</span>'
    + '<span style="flex:1"></span>'
    + '<input id="srcpickq" placeholder="filter by SKU or title" value="'+_sesc(q||"")+'" '
    + 'oninput="sourcingPickerFilter(this.value)" style="font-size:12px;padding:4px 8px;min-width:200px">'
    + '<button class="db-chip" onclick="sourcingPickerClose()">Close</button></div>';

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:8px">'+_sesc(j.note)+'</div></div>';
    host.innerHTML = h; return;
  }

  h += '<div style="max-height:340px;overflow:auto">';
  (j.items||[]).forEach(function(it){
    h += '<div style="display:flex;gap:9px;align-items:center;font-size:11.5px;'
      +  'padding:6px 4px;border-top:1px solid #1c2531">'
      // The product, at a glance. A SKU is "10.06_3Days_B0081ZHHTS" and a title
      // is forty words of keywords; neither says what the thing is, and
      // enrolling the wrong one reprices it against somebody else's supplier.
      +  (it.img
          ? '<img src="'+_sesc(it.img)+'" loading="lazy" alt="" '
            + 'style="width:38px;height:38px;object-fit:contain;background:#0d1220;'
            + 'border-radius:5px;flex:0 0 auto">'
          : '<span style="width:38px;height:38px;border-radius:5px;flex:0 0 auto;'
            + 'background:#0d1220;display:inline-block"></span>')
      +  '<code style="min-width:150px">'+_sesc(it.sku)+'</code>'
      +  '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '
      +  'title="'+_sesc(it.title)+'">'+_sesc(it.title||"(no title)")+'</span>'
      +  (/AFN|AMAZON|FBA/i.test(it.fulfillment||"")
          ? '<span class="db-chip" style="opacity:.6" title="Amazon holds this stock, so the repricer leaves it alone">FBA</span>'
          : '')
      +  '<span class="cc">'+_smoney(it.price)+'</span>'
      +  (it.enrolled
          ? '<span class="db-chip" style="background:#12303a;color:#6ac7e8">enrolled'
            + (it.sources? ' · '+it.sources+' source'+(it.sources===1?'':'s') : ' · no sources yet')+'</span>'
          : '<button class="db-chip" onclick="sourcingEnrolPicked('+_sarg(it.sku)+')">Enrol</button>')
      +  '</div>';
  });
  h += '</div></div>';
  host.innerHTML = h;
}

let _srcPickTimer = null;
function sourcingPickerFilter(v){
  clearTimeout(_srcPickTimer);
  _srcPickTimer = setTimeout(function(){ sourcingPickerLoad(v); }, 200);
}
function sourcingPickerClose(){
  const host = document.getElementById("srcpick");
  if(host){ host.style.display = "none"; host.innerHTML = ""; }
}

async function sourcingEnrolPicked(sku){
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku})})).json();
    if(!j.ok){ toast(j.error||"Could not enrol"); return; }
    toast("Enrolled in dry run — add a supplier link next");
    await sourcingPickerLoad((document.getElementById("srcpickq")||{}).value||"");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingUnenrol(sku){
  if(!confirm("Stop watching "+sku+"? Its suppliers and history are kept.")) return;
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, enrolled:false})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingAddSourcePrompt(sku){
  const url = prompt("Paste the supplier's link for "+sku+".\n\neBay links are read "
                   + "through eBay's own API. Other sites are read only if they "
                   + "publish structured product data — the app will tell you if "
                   + "it cannot read one rather than guess a price.");
  if(!url) return;
  try{
    const j = await (await fetch("/sourcing/source/add",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, url:url.trim()})})).json();
    if(!j.ok){ toast(j.error||"Could not add"); return; }
    toast("Supplier added — press “Re-read suppliers now” to check it");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingRemoveSource(sid){
  if(!confirm("Remove this supplier?")) return;
  try{
    const j = await (await fetch("/sourcing/source/remove",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({source_id:sid})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}
