// ============ ASIN MONITOR — tracking list (Stage 2) ============
// Standalone competitor/hijacker watch, separate from listing generation. This stage is
// the tracking list only: add/remove ASINs, each with a label and which EU marketplaces to
// check. The hourly checker + alerts + history come in Stage 3/4.

let MON_EU = ["UK","DE","FR","IT","ES","NL","PL","SE","BE","IE"];
let MON_LIST = [];

function monitorOnOpen(){ loadMonitorOverview(); loadMonitorAlerts(); monSchedLoad(); }

/* ============ WHEN THE MONITOR RUNS ============
 *
 *   "i dont want the asin monitor to be working always, give 2 options. option
 *    1 is to recheck the status of the buybox by clicking a button. option two
 *    is to setup a time of your choice. e.g. every 4 hours. 10 hours etc etc. a
 *    user should be able to choose time on his choice"
 *
 * Option 1 is the Check now button, which has always been there and works
 * whatever this says. Option 2 is here, and it is OFF by default: this is the
 * app's largest consumer of the Amazon quota and it used to run whether or not
 * anybody was looking at it.
 *
 * The hour buttons are SHORTCUTS, not the choice. Any whole number of hours can
 * be typed, because "a user should be able to choose time on his choice" -- the
 * server puts a silly number in range rather than refusing to save.
 */
const MON_SCHED = {mode: "off", hours: 4, suggested: [], min: 1, max: 168,
                   explains: "", loaded: false};

async function monSchedLoad(){
  try{
    const j = await (await fetch("/monitor/schedule")).json();
    if(!j || !j.ok) return;
    MON_SCHED.mode = j.mode; MON_SCHED.hours = j.hours;
    MON_SCHED.suggested = j.suggested_hours || [];
    MON_SCHED.min = j.min_hours; MON_SCHED.max = j.max_hours;
    MON_SCHED.explains = j.explains || "";
    MON_SCHED.loaded = true;
    monSchedRender();
  }catch(e){ /* the screen works without it; Check now is unaffected */ }
}

function monSchedRender(){
  const host = document.getElementById("mon_sched");
  if(!host || !MON_SCHED.loaded) return;
  const on = MON_SCHED.mode === "every";
  const chips = (MON_SCHED.suggested || []).map(function(h){
    return '<button class="monsched-h' + (on && h === MON_SCHED.hours ? " on" : "")
         + '" onclick="monSchedSet(\'every\',' + h + ')">'
         + (h === 24 ? "24h" : (h + "h")) + '</button>';
  }).join("");
  host.innerHTML =
      '<div class="monsched-row">'
    +   '<span class="monsched-lbl">Automatic checking</span>'
    +   '<button class="monsched-t' + (on ? "" : " on")
    +     '" onclick="monSchedSet(\'off\')">Off</button>'
    +   '<button class="monsched-t' + (on ? " on" : "")
    +     '" onclick="monSchedSet(\'every\',' + (MON_SCHED.hours || 4) + ')">'
    +     'Every&hellip;</button>'
    +   (on ? '<span class="monsched-chips">' + chips + '</span>'
              // Typed, not chosen from a list. The label says so, because a box
              // beside a row of buttons reads as "other" unless it is named.
            + '<span class="monsched-any">or every '
            + '<input id="mon_sched_h" class="monsched-in" type="number" '
            +   'min="' + MON_SCHED.min + '" max="' + MON_SCHED.max + '" '
            +   'value="' + MON_SCHED.hours + '" '
            +   'onchange="monSchedSet(\'every\', this.value)"> hours</span>'
          : '')
    + '</div>'
    + '<div class="monsched-why cc">' + _monEsc(MON_SCHED.explains) + '</div>';
}

async function monSchedSet(mode, hours){
  try{
    const j = await (await fetch("/monitor/schedule", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({mode: mode, hours: hours})
    })).json();
    if(!j || !j.ok){ toast("Could not save that: " + ((j && j.error) || "unknown")); return; }
    // Redrawn from what the SERVER stored, not from what was clicked -- it puts
    // an out-of-range number in range, and the screen must show what is really
    // set rather than what was asked for.
    MON_SCHED.mode = j.mode; MON_SCHED.hours = j.hours;
    MON_SCHED.explains = j.explains || "";
    monSchedRender();
    toast(j.mode === "off" ? "Automatic checking is off."
                           : "Checking every " + j.hours + " hours.");
  }catch(e){ toast("Could not save that: " + e); }
}

function _monEsc(s){
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                                   .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ---- overview: per-ASIN seller detail + top summary (Feature 1) ----------------
async function loadMonitorOverview(){
  const host = document.getElementById("mon_list");
  if(host) host.innerHTML = '<div class="cc" style="padding:14px;opacity:.7"><span class="genspin"></span> Loading…</div>';
  try{
    const j = await (await fetch("/monitor/overview")).json();
    if(!j || !j.ok){ if(host) host.innerHTML='<div class="cc" style="color:var(--red);padding:14px">Could not load: '+esc((j&&j.error)||"unknown")+'</div>'; return; }
    MON_EU = j.eu_marketplaces || MON_EU;
    renderMonitorMarketPicker();
    renderMonitorOverview(j.rows||[], j.summary||{}, j.unknowns||[]);
  }catch(e){ if(host) host.innerHTML='<div class="cc" style="color:var(--red);padding:14px">Error: '+esc(String(e))+'</div>'; }
}

function monUnknownsSection(unknowns, s){
  if(!unknowns || !unknowns.length) return "";
  const na = s.new_accounts||0;
  const body = unknowns.map(u=>{
    const nameCell = u.storefront ? `<a href="${esc(u.storefront)}" target="_blank" rel="noopener">${esc(u.name||u.seller_id)}</a>` : esc(u.name||u.seller_id);
    const badges = (u.high_risk?' <span class="hirisk">HIGH RISK</span>':'')
                 + (u.new_account?' <span class="newacct">NEW</span>':'')
                 + ((u.multi_account||1)>1?` <span class="multiacct" title="Same name on ${u.multi_account} seller IDs — likely one bad actor">${u.multi_account} accounts</span>`:'');
    const fb = u.new_account ? '0 reviews' : ((u.feedback_pct!=null?u.feedback_pct+'%':'?')+' · '+(u.feedback_count||0));
    const price = (u.price!==null && u.price!==undefined) ? (esc(String(u.price))+' '+esc(u.currency||'')) : '—';
    return `<tr class="${u.high_risk?'hirow':(u.new_account?'newrow':'')}">
      <td class="monasin">${esc(u.asin)}</td><td>${esc(u.label||'')||'<span class="cc">—</span>'}</td>
      <td><span class="monchip">${esc(u.marketplace)}</span></td>
      <td>${nameCell}${badges} <span class="cc">(${esc(u.seller_id)})</span></td>
      <td>${u.buybox?'<span class="bbstar">★</span>':''}</td>
      <td>${price} <span class="cc">${u.fba?'FBA':'FBM'}</span></td>
      <td>${esc(fb)}</td>
      <td class="cc">${esc(u.first_seen||'—')}</td>
      <td><button class="monlabelbtn" title="Name / classify this seller (applies to this ID everywhere)" onclick="monLabelSeller('${esc(u.seller_id)}','${esc(u.marketplace)}')"><i class="ti ti-tag"></i> Name</button></td></tr>`;
  }).join("");
  const hr = s.high_risk||0;
  return `<div class="monunk">
    <div class="monunk-h"><i class="ti ti-alert-triangle"></i> Third parties on your listings — <b>${unknowns.length}</b>${hr?` · <span style="color:var(--red)">${hr} HIGH RISK</span>`:''}${na?` · <span style="color:var(--warn)">${na} new account${na!==1?'s':''}</span>`:''}</div>
    <div style="overflow-x:auto"><table class="montable"><thead><tr><th>ASIN</th><th>Label</th><th>Market</th><th>Seller</th><th>BB</th><th>Price</th><th>Feedback</th><th>First seen</th><th></th></tr></thead><tbody>${body}</tbody></table></div>
  </div>`;
}

// Name / classify a seller from the UI -> writes config.json known_sellers (no code edit).
// BUG 1/2/3 fix: the modal takes ONLY the seller id + marketplace (never a name — the name is
// fetched from the server so an ASIN can never be pre-filled). It shows the seller's CURRENT
// global classification and its FOOTPRINT (how many ASINs/marketplaces this label will touch),
// offers a REVERT-to-unknown option, and warns before marking a contradictory seller as safe.
function monLabelSeller(id, mkt){
  if(document.getElementById("lblwrap")) closeLabelModal();
  window._LBL_INFO = null;
  const dlg=document.createElement("div"); dlg.className="modalwrap open"; dlg.id="lblwrap"; dlg.style.zIndex="140";
  dlg.innerHTML=`<div class="modal" style="max-width:480px;position:relative">
    <button class="x" onclick="closeLabelModal()">×</button>
    <h3><i class="ti ti-tag"></i> Label seller</h3>
    <div class="cc" style="margin:2px 0 8px">Seller ID <b>${esc(id)}</b> — this label applies to this ID <b>everywhere</b> (all ASINs &amp; marketplaces), not just here.</div>
    <div id="lbl_footprint" class="cc" style="margin-bottom:10px;padding:7px 9px;border:1px solid var(--bd,var(--line2));border-radius:6px"><span class="genspin"></span> checking where this seller appears…</div>
    <input type="hidden" id="lbl_id" value="${esc(id)}"><input type="hidden" id="lbl_mkt" value="${esc(mkt||'')}">
    <label class="pl-lbl">Business name</label>
    <input id="lbl_name" class="pl-in" placeholder="e.g. Woux LLC" autocomplete="off">
    <label class="pl-lbl" style="margin-top:10px">Classify as <span id="lbl_prev" class="cc"></span></label>
    <select id="lbl_kind" class="pl-in">
      <option value="name">Named third party — still flagged (default)</option>
      <option value="authorised">Authorised reseller — trusted (neutral)</option>
      <option value="me">My own account — you (teal)</option>
      <option value="amazon">Amazon retail — neutral</option>
      <option value="unknown">↩ Revert to UNKNOWN — flag it again</option>
    </select>
    <div class="pl-actions">
      <button class="mktbtn" onclick="closeLabelModal()">Cancel</button>
      <button class="mktbtn on" id="lbl_save" onclick="monSaveSellerLabel()"><i class="ti ti-check"></i> Save</button>
    </div>
  </div>`;
  document.body.appendChild(dlg);
  // Pull the seller's real name + current classification + footprint from the server.
  fetch("/monitor/seller_info?seller_id="+encodeURIComponent(id))
    .then(r=>r.json()).then(j=>{
      if(!j||!j.ok) return;
      window._LBL_INFO=j;
      const nm=document.getElementById("lbl_name"); if(nm && j.name) nm.value=j.name;   // real name, NEVER the ASIN
      const kd=document.getElementById("lbl_kind"); if(kd && j.kind && j.kind!=="unknown") kd.value=j.kind;
      const pv=document.getElementById("lbl_prev"); if(pv) pv.textContent="· currently: "+(j.kind||"unknown");
      const fp=j.footprint||{}; const ev=j.evidence||{}; const fpEl=document.getElementById("lbl_footprint");
      if(fpEl){
        const mkts=(fp.marketplaces||[]);
        let html="This label will apply to <b>"+esc(String(fp.asin_count||0))+"</b> ASIN"+((fp.asin_count||0)!==1?'s':'')+
                 " across <b>"+esc(String(fp.marketplace_count||0))+"</b> marketplace"+((fp.marketplace_count||0)!==1?'s':'')+
                 (mkts.length?" ("+mkts.map(esc).join(", ")+")":"")+".";
        const fb=ev.feedback_count;
        if(fb===0) html+=' <span style="color:var(--gold)">⚠ 0 feedback</span>';
        else if(fb!=null) html+=" · "+esc(String(fb))+" feedback";
        if(ev.fba) html+=" · FBA";
        fpEl.innerHTML=html;
      }
    }).catch(()=>{});
  setTimeout(()=>{ const el=document.getElementById("lbl_name"); if(el){ el.focus(); el.select(); } }, 120);
}
function closeLabelModal(){ const w=document.getElementById("lblwrap"); if(w) w.remove(); }
async function monSaveSellerLabel(){
  const g=id=>(document.getElementById(id)||{}).value||"";
  const id=g("lbl_id"), name=g("lbl_name").trim(), kind=g("lbl_kind")||"name", mkt=g("lbl_mkt");
  if(!name && kind!=="me" && kind!=="unknown"){ toast("Enter a name"); const el=document.getElementById("lbl_name"); if(el) el.focus(); return; }
  // CONTRADICTION WARNING — don't silently mark a likely hijacker as safe. Confirm, never block.
  const info=window._LBL_INFO||{}; const ev=info.evidence||{};
  if(kind==="me" || kind==="amazon"){
    const reasons=[];
    if(ev.feedback_count===0) reasons.push("it has 0 feedback");
    if(kind==="amazon" && name && !/amazon/i.test(name)) reasons.push('its storefront name ("'+name+'") does not match Amazon');
    if(reasons.length){
      if(!await uiConfirm("Hold on — marking "+id+" as "+kind.toUpperCase()+" will STOP it being flagged, but "+reasons.join(" and ")+
                  ".\n\nThis looks like it could be a hijacker. Misclassifying a hijacker as safe is the most costly mistake this tool can make — it silences alerts on a real threat.\n\nMark it as "+kind.toUpperCase()+" anyway?")) return;
    }
  }
  const btn=document.getElementById("lbl_save"); if(btn) btn.disabled=true;
  try{
    const j=await (await fetch("/monitor/seller_label",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({seller_id:id, name, kind, marketplace:mkt})})).json();
    if(!j||!j.ok){ toast("Save failed: "+((j&&j.error)||"unknown")); if(btn) btn.disabled=false; return; }
    const prev=(j.previous&&j.previous.kind)||"unknown";
    const msg = kind==="unknown" ? "Reverted to unknown"
              : kind==="name"    ? ('Named "'+name+'"')
              :                    ('Classified as '+kind);
    toast(msg+" (was: "+prev+")");
    closeLabelModal(); loadMonitorOverview();   // cfg cache is dropped server-side -> rows re-render with the new label
  }catch(e){ toast("Save error: "+e); if(btn) btn.disabled=false; }
}

function renderMonitorOverview(rows, s, unknowns){
  const host = document.getElementById("mon_list"); if(!host) return;
  const warnCls = n => (n>0 ? "monsum-warn" : "monsum-ok");
  const sumBar = `<div class="monsum">
    <span><b>${s.tracked||0}</b> ASIN${(s.tracked||0)!==1?'s':''} tracked</span>
    <span class="monsum-ok"><b>${s.clean||0}</b> clean</span>
    <span class="${warnCls(s.with_unknown||0)}"><b>${s.with_unknown||0}</b> with unknown seller${(s.with_unknown||0)!==1?'s':''}</span>
    <span class="${warnCls(s.total_unknown||0)}"><b>${s.total_unknown||0}</b> unknown seller${(s.total_unknown||0)!==1?'s':''} total</span>
    ${(s.high_risk||0)>0?`<span class="monsum-hi"><b>${s.high_risk}</b> HIGH RISK</span>`:''}
    ${(s.checked||0)<(s.tracked||0)?`<span class="cc">· ${(s.tracked||0)-(s.checked||0)} not checked yet</span>`:''}
  </div>`;
  const bm = s.by_marketplace||{};
  const bmMax = Math.max(0, ...Object.values(bm));
  // The by-market run of text is now the chart above (monChart) -- same numbers,
  // with the shape visible. Keeping both would be the same figure twice.
  const bmText = "";
  monChart(s);
  const c=document.getElementById("mon_count"); if(c) c.textContent=(s.tracked||0)+" ASIN"+((s.tracked||0)!==1?"s":"")+" tracked";
  if(!rows.length){ host.innerHTML = sumBar + bmText + '<div class="cc" style="padding:14px;opacity:.7">No ASINs tracked yet. Add one above (or upload a list) to start watching it.</div>'; return; }
  host.innerHTML = sumBar + bmText + monUnknownsSection(unknowns, s) + rows.map(monAsinBlock).join("");
}

/* ONE LINE PER ASIN, NOT TEN.
 *
 *   "each asin has a too long list of markets telling here is this hijacker
 *    here the hijacker or seller or offer was not found, summarize the info,
 *    what is this. this is too messy"
 *
 * Measured before this change: 111 ASINs x 10 marketplaces = 1,110 rows on one
 * page, and the page was 46,293 pixels tall -- about forty screens. Most of
 * those rows said "skipped — not listed here", which is the app reporting that
 * nothing happened, ten times per product.
 *
 * WHAT A SUMMARY HAS TO KEEP. The whole point of this screen is "is somebody
 * else on my listing", so the summary leads with that and with WHERE, and the
 * silent markets collapse into a count. Nothing is thrown away -- the ten rows
 * are still there behind Details, and an ASIN with an unknown seller opens
 * expanded, because that one you do want to read.
 */
function _monMarketSummary(r){
  const per = r.per_marketplace || [];
  const listed = [], quiet = [], failed = [], unchecked = [], hot = [];
  per.forEach(function(m){
    if(m.error){ failed.push(m.marketplace); return; }
    if(m.skipped){ quiet.push(m.marketplace); return; }
    if(!m.checked){ unchecked.push(m.marketplace); return; }
    if((m.seller_count||0) > 0){
      listed.push(m.marketplace);
      if((m.sellers||[]).some(function(s){ return s.kind === "unknown"; }))
        hot.push(m.marketplace);
    } else {
      quiet.push(m.marketplace);
    }
  });
  return {listed: listed, quiet: quiet, failed: failed, unchecked: unchecked,
          hot: hot, total: per.length};
}

/* ---- the one chart worth having on this page -----------------------------
 *
 * WHICH CHART. The question this screen exists to answer is "is somebody else
 * on my listings, and where" -- so the chart is unknown sellers BY MARKETPLACE,
 * biggest first. That was already on the page as a run of text
 * ("BE 11 · DE 3 · ES 2 · FR 6 …"), which is a chart drawn badly: the numbers
 * are there but the shape is not, and the shape is the whole point. Eleven in
 * Belgium against one in Sweden is obvious as bars and invisible as a list.
 *
 * NOT a time series, which is what a monitoring page usually reaches for. The
 * history holds one snapshot per marketplace per run, and runs are irregular
 * (this one is manual and had four days between the last two), so a line
 * against time would be mostly interpolation between two points -- a shape
 * invented by the drawing rather than measured.
 */
function monChart(s){
  const host = document.getElementById("mon_chart");
  if(!host) return;
  const bm = s.by_marketplace || {};
  const keys = Object.keys(bm).filter(function(k){ return (bm[k] || 0) > 0; })
                     .sort(function(a, b){ return bm[b] - bm[a]; });
  if(!keys.length){
    // A clean account gets a sentence, not an empty chart frame. An axis with
    // nothing under it reads as "failed to load".
    host.innerHTML = (s.checked || 0)
      ? '<div class="moncard moncard-clean"><i class="ti ti-shield-check"></i> '
        + 'No unknown sellers on any tracked ASIN, in any marketplace.</div>'
      : '';
    return;
  }
  const max = bm[keys[0]] || 1;
  const total = keys.reduce(function(a, k){ return a + bm[k]; }, 0);
  const bars = keys.map(function(k){
    const n = bm[k];
    const pct = Math.round(n / max * 100);
    return '<div class="monbar-row">'
      + '<span class="monbar-lbl">' + esc(k) + '</span>'
      + '<span class="monbar-track"><span class="monbar-fill" style="width:'
      + pct + '%"></span></span>'
      + '<span class="monbar-n">' + n + '</span></div>';
  }).join("");
  host.innerHTML = '<div class="moncard">'
    + '<div class="moncard-head"><b>Unknown sellers by marketplace</b>'
    + '<span class="cc">' + total + ' across ' + keys.length + ' market'
    + (keys.length !== 1 ? 's' : '') + ' · worst is ' + esc(keys[0]) + '</span></div>'
    + '<div class="monbars">' + bars + '</div>'
    + '<div class="cc moncard-foot">A seller this app has not been told about. '
    + 'Name one and it stops counting here — use <b>Import seller names</b> for '
    + 'a list of them.</div></div>';
}

function monAsinBlock(r){
  const dp = _dpUrl(r.asin, r.marketplace || r.mkt);   // per-row market, not always UK
  const sm = _monMarketSummary(r);
  const badge = r.has_unknown ? '<span class="monchip warn">⚠ unknown seller</span>'
              : (r.checked ? '<span class="monchip ok">clean</span>' : '<span class="cc">not checked yet</span>');
  const id = "monx_" + String(r.asin || "").replace(/[^A-Za-z0-9]/g, "");
  // An ASIN with somebody else on it opens READ, not folded away.
  const open = !!r.has_unknown;
  const head = `<div class="monasin-head">
    <a href="${dp}" target="_blank" rel="noopener" class="monasin">${esc(r.asin)}</a>
    ${r.label?`<span class="cc monasin-label">${esc(r.label)}</span>`:''} ${badge}
    <span style="flex:1"></span>
    <button class="db-chip monx" onclick="monToggle('${id}',this)" aria-expanded="${open}">
      <i class="ti ti-chevron-${open?'up':'down'}"></i> ${sm.total} market${sm.total!==1?'s':''}</button>
    <button class="db-chip" title="Offer history" onclick="openMonHistory('${esc(r.asin)}','${esc((r.label||'').replace(/'/g,''))}')"><i class="ti ti-history"></i></button>
    <button class="db-chip" title="Stop tracking" onclick="removeMonitorAsin('','${esc(r.asin)}')"><i class="ti ti-trash"></i></button>
  </div>`;

  // The one line that replaces ten. Ordered by what you would look for first.
  const bits = [];
  if(sm.hot.length)
    bits.push('<span class="monsm-hot"><i class="ti ti-alert-triangle"></i> other sellers in '
              + sm.hot.map(esc).join(", ") + '</span>');
  if(sm.listed.length){
    // DON'T SAY THE SAME MARKETS TWICE. When every market carrying offers also
    // has an unknown seller, the line above has already named them and this
    // repeated the list word for word: "other sellers in IT, ES, BE · on sale
    // in 3 of 10 — IT, ES, BE".
    const same = sm.hot.length === sm.listed.length
                 && sm.listed.every(function(m){ return sm.hot.indexOf(m) >= 0; });
    bits.push('<span class="monsm-on">on sale in ' + sm.listed.length + ' of ' + sm.total
              + (same ? '' : ' — ' + sm.listed.map(esc).join(", ")) + '</span>');
  }
  // The silent markets are a COUNT, not a list of "not listed here" rows. That
  // is the noise this whole change exists to remove.
  if(sm.quiet.length)
    bits.push('<span class="cc">' + sm.quiet.length + ' with no offers</span>');
  if(sm.unchecked.length)
    bits.push('<span class="cc">' + sm.unchecked.length + ' not checked yet</span>');
  if(sm.failed.length)
    bits.push('<span class="monsm-fail">' + sm.failed.length + ' could not be checked</span>');
  const summary = '<div class="monasin-sum">' + (bits.join('<span class="monsm-dot">·</span>')
                  || '<span class="cc">nothing checked yet</span>') + '</div>';

  const mkts = (r.per_marketplace||[]).map(m=>{
    const mk = `<span class="monchip">${esc(m.marketplace)}</span>`;
    if(m.skipped) return `<div class="monmkt-row skipped">${mk} <span class="cc">no offers here${m.last_checked?(' · checked '+esc(m.last_checked)):''}</span></div>`;
    if(m.error) return `<div class="monmkt-row">${mk} <span class="monsm-fail">could not be checked — ${esc(m.error)}</span></div>`;
    if(!m.checked) return `<div class="monmkt-row">${mk} <span class="cc">not checked yet</span></div>`;
    const n = m.seller_count||0;
    const chips = (m.sellers||[]).map(monSellerChip).join(" ");
    const body = n>0 ? `<b>${n}</b> seller${n!==1?'s':''} ${chips}` : `<span class="cc">no offers found</span>`;
    return `<div class="monmkt-row">${mk} ${body}<span class="cc monmkt-ts"> · ${esc(m.ts||'')}</span></div>`;
  }).join("");
  return `<div class="monasin-block ${r.has_unknown?'warn':''}">${head}${summary}`
       + `<div class="monmkt-list" id="${id}"${open?'':' hidden'}>${mkts}</div></div>`;
}

function monToggle(id, btn){
  const el = document.getElementById(id);
  if(!el) return;
  const now = el.hasAttribute("hidden");
  if(now) el.removeAttribute("hidden"); else el.setAttribute("hidden", "");
  if(btn){
    btn.setAttribute("aria-expanded", String(now));
    const i = btn.querySelector("i");
    if(i) i.className = "ti ti-chevron-" + (now ? "up" : "down");
  }
}

function monSellerChip(s){
  const cls = s.kind==="me"?"me":(s.kind==="amazon"?"amz":(s.kind==="authorised"?"auth":"unk"));
  const star = s.buybox ? '<span class="bbstar" title="Buy Box holder">★</span>' : '';
  const fb = (s.feedback_pct!==null && s.feedback_pct!==undefined) ? (" · "+s.feedback_pct+"% ("+(s.feedback_count||0)+")") : "";
  const name = esc(s.label || s.id || "unknown seller");
  const inner = (s.kind==="unknown" && s.storefront)
    ? `<a href="${esc(s.storefront)}" target="_blank" rel="noopener">${name}</a>` : name;
  // For UNKNOWN third parties, surface feedback prominently: brand-new (0 feedback) = NEW badge
  // (classic hijacker signature); otherwise show the % + review count inline, not just on hover.
  let extra = "";
  if(s.kind==="unknown"){
    const fc = s.feedback_count;
    if(fc===0 || fc===null || fc===undefined)
      extra = ' <span class="newacct" title="Brand-new account — 0 feedback (classic hijacker signature)">NEW</span>';
    else
      extra = ` <span class="fbnote">${esc(String(s.feedback_pct!=null?s.feedback_pct:'?'))}%·${esc(String(fc))}</span>`;
  }
  return `<span class="sellerchip ${cls}" title="${esc(s.id||"")}${esc(fb)}">${star}${inner}${extra}</span>`;
}

// ---- alerts / status / manual check ----------------------------------------
const MON_ALERT_META = {
  new_seller:    {icon:"ti-user-plus",   cls:"na", label:"New seller"},
  seller_removed:{icon:"ti-user-minus",  cls:"sr", label:"Seller left"},
  price_change:  {icon:"ti-tag",         cls:"pc", label:"Price change"},
  buybox_change: {icon:"ti-award",       cls:"bb", label:"Buy Box changed"},
};

async function loadMonitorAlerts(){
  const host = document.getElementById("mon_alerts");
  try{
    const j = await (await fetch("/monitor/alerts")).json();
    if(!j || !j.ok){ return; }
    updateMonBadge(j.unread||0);
    renderMonStatus(j.status||{});
    if(!host) return;
    const al = j.alerts || [];
    if(!al.length){
      host.innerHTML = '<div class="cc" style="padding:10px 2px;opacity:.7">No alerts yet. When a new seller appears on a tracked ASIN, it shows here.</div>';
      return;
    }
    host.innerHTML = al.map(monAlertCard).join("");
  }catch(e){ /* alerts are additive */ }
}

function monAlertCard(a){
  const m = MON_ALERT_META[a.type] || {icon:"ti-bell", cls:"", label:a.type};
  const seller = a.seller_name
    ? `${esc(a.seller_name)} <span class="cc">(${esc(a.seller_id||"")})</span>`
    : `<span class="cc">${esc(a.seller_id||"unknown seller")}</span>`;
  const fb = (a.feedback_pct!==null && a.feedback_pct!==undefined)
    ? ` · ${esc(String(a.feedback_pct))}% (${esc(String(a.feedback_count||0))})` : "";
  const price = (a.price!==null && a.price!==undefined)
    ? ` · ${esc(String(a.price))} ${esc(a.currency||"")} ${a.fba?"(FBA)":"(FBM)"}` : "";
  const store = a.storefront ? ` · <a href="${esc(a.storefront)}" target="_blank" rel="noopener">storefront ↗</a>` : "";
  return `<div class="monalert ${m.cls} ${a.read?'read':''}">
    <div class="ma-ic"><i class="ti ${m.icon}"></i></div>
    <div class="ma-body">
      <div class="ma-top"><b>${esc(m.label)}</b> · <span class="ma-asin">${esc(a.asin||"")}</span>
        <span class="monchip">${esc(a.marketplace||"")}</span>
        ${a.label?`<span class="cc">${esc(a.label)}</span>`:''}
        <span class="spacer"></span><span class="cc ma-ts">${esc(a.ts||"")}</span></div>
      <div class="ma-mid">Seller: ${seller}${fb}${price}${store}</div>
      ${a.detail?`<div class="cc ma-det">${esc(a.detail)}</div>`:''}
    </div></div>`;
}

function renderMonStatus(st){
  const el = document.getElementById("mon_status"); if(!el) return;
  if(st.running){
    // WHAT IT IS ACTUALLY DOING. This said "checking…" and nothing else for
    // the entire run -- nine minutes of a word, with no way to tell a working
    // check from a hung one. Reported as: pressed Check now, waited ten
    // minutes, nothing changed, reloaded the page, still nothing.
    const done = Number(st.done || 0), total = Number(st.total || 0);
    const pct = total ? Math.round(done / total * 100) : 0;
    let line = '<span class="genspin"></span> Checking ' + done.toLocaleString()
             + ' of ' + total.toLocaleString() + ' marketplace checks';
    if(total) line += ' (' + pct + '%)';
    if(st.started_ts){
      const el4 = Math.round((Date.now() / 1000 - st.started_ts));
      line += ' · ' + (el4 < 90 ? el4 + 's' : Math.round(el4 / 60) + 'm') + ' so far';
      // An estimate from the rate ACHIEVED, not from a guess about the API.
      if(done > 0 && total > done){
        const rem = Math.round(el4 / done * (total - done));
        line += ' · about ' + (rem < 90 ? rem + 's' : Math.round(rem / 60) + 'm')
              + ' left';
      }
    }
    if(st.run_alerts) line += ' · <b>' + st.run_alerts + '</b> alert'
                            + (st.run_alerts !== 1 ? 's' : '') + ' so far';
    if(st.run_fails) line += ' · <span style="color:var(--warn)">' + st.run_fails
                           + ' failed</span>';
    if(total) line += '<div class="monprog"><div class="monprog-fill" style="width:'
                    + pct + '%"></div></div>';
    // The results below fill in as it goes now, so say so -- otherwise a
    // half-filled page during a run looks like a half-broken one.
    line += '<div class="cc" style="font-size:10.5px;margin-top:3px">'
          + 'Results below update as each batch finishes — you can leave this '
          + 'page and come back.</div>';
    el.innerHTML = line;
    return;
  }
  if(st.phase === "failed" && st.error){
    el.innerHTML = '<span style="color:var(--red)">' + esc(st.error)
                 + '</span> <span class="cc">Everything checked before it '
                 + 'stopped has been saved.</span>';
    return;
  }
  if(!st.last_run){ el.textContent = "Not run yet — runs hourly while the app is open."; return; }
  const bits = ["Last check: "+esc(st.last_run)];
  if(st.api_calls!=null) bits.push(st.api_calls+" API call"+(st.api_calls!==1?"s":""));
  if(st.duration!=null) bits.push(st.duration+"s");
  if(st.skipped) bits.push(st.skipped+" market"+(st.skipped!==1?"s":"")+" skipped");
  if(st.next_run_ts){ const m=Math.max(0,Math.round((st.next_run_ts*1000-Date.now())/60000)); bits.push("next in "+m+"m"); }
  let html = bits.join(" · ");
  if(st.last_run_ok===false) html += ' <span style="color:var(--warn)">(some checks failed — see terminal)</span>';
  if(st.overload) html += ' <span style="color:var(--red)">⚠ cycle nearly exceeds the hour — reduce scope (drop dead markets / inactive ASINs)</span>';
  el.innerHTML = html;
}

function updateMonBadge(n){
  const b = document.getElementById("mon_badge"); if(!b) return;
  if(n>0){ b.textContent = n>99?"99+":String(n); b.style.display=""; }
  else { b.style.display="none"; b.textContent=""; }
}

function _monPoll(btn){
  let n=0; const iv=setInterval(async ()=>{
    await loadMonitorAlerts();
    const s = await (await fetch("/monitor/status")).json();
    if((!s.status || !s.status.running) || ++n>60){ clearInterval(iv); if(btn) btn.disabled=false; loadMonitorOverview(); }
  }, 3000);
}
async function monCheckNow(){
  const btn = document.getElementById("mon_checkbtn");
  if(btn){ btn.disabled = true; }
  try{
    const j = await (await fetch("/monitor/check_now",{method:"POST"})).json();
    if(!j || !j.ok){ toast("Could not start: "+((j&&j.error)||"unknown")); if(btn) btn.disabled=false; return; }
    toast("Checking tracked ASINs now…");
    _monPoll(btn);
  }catch(e){ toast("Check error: "+e); if(btn) btn.disabled=false; }
}
async function monRescanAll(){
  const btn = document.getElementById("mon_rescanbtn");
  if(btn){ btn.disabled = true; }
  try{
    const j = await (await fetch("/monitor/check_now",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({rescan:true})})).json();
    if(!j || !j.ok){ toast("Could not start: "+((j&&j.error)||"unknown")); if(btn) btn.disabled=false; return; }
    toast("Re-scanning every marketplace (including skipped)…");
    _monPoll(btn);
  }catch(e){ toast("Re-scan error: "+e); if(btn) btn.disabled=false; }
}

function monDownloadExcel(){
  // simple GET download -> the route streams the .xlsx with a Content-Disposition attachment
  window.location.href = "/monitor/export";
  toast("Preparing Excel…");
}

async function monMarkAllRead(){
  try{
    await fetch("/monitor/alerts/read",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    loadMonitorAlerts();
  }catch(e){}
}

// ---- offer history viewer (Stage 4) ----------------------------------------
let MON_NAMES = {};
function _monSellerLabel(sid, mkt){
  if(!sid) return '<span class="cc">—</span>';
  const nm = MON_NAMES[sid+"::"+mkt];
  const link = `https://www.amazon.${_monTld(mkt)}/sp?seller=${encodeURIComponent(sid)}`;
  const inner = nm ? `${esc(nm)} <span class="cc">(${esc(sid)})</span>` : esc(sid);
  return `<a href="${link}" target="_blank" rel="noopener">${inner}</a>`;
}
function _monTld(mkt){
  const m={UK:"co.uk",GB:"co.uk",DE:"de",FR:"fr",IT:"it",ES:"es",NL:"nl",PL:"pl",SE:"se",BE:"com.be",IE:"ie"};
  return m[String(mkt||"").toUpperCase()]||"co.uk";
}
function _lowestLanded(offers){
  const vals=(offers||[]).map(o=>o.landed).filter(v=>v!==null&&v!==undefined);
  return vals.length?Math.min.apply(null,vals):null;
}

async function openMonHistory(asin, label){
  if(document.getElementById("monhistwrap")) closeMonHistory();
  const dlg=document.createElement("div");
  dlg.className="modalwrap open"; dlg.id="monhistwrap"; dlg.style.zIndex="130";
  dlg.innerHTML=`<div class="modal" style="max-width:900px;position:relative">
    <button class="x" onclick="closeMonHistory()">×</button>
    <h3><i class="ti ti-history"></i> Offer history — <span class="ma-asin">${esc(asin)}</span>${label?` <span class="cc">${esc(label)}</span>`:''}</h3>
    <div id="monhist_body"><div class="cc" style="padding:14px"><span class="genspin"></span> Loading…</div></div>
  </div>`;
  document.body.appendChild(dlg);
  try{
    const j=await (await fetch("/monitor/history?asin="+encodeURIComponent(asin))).json();
    const body=document.getElementById("monhist_body"); if(!body) return;
    if(!j || !j.ok){ body.innerHTML='<div class="cc" style="color:var(--red);padding:14px">'+esc((j&&j.error)||"could not load")+'</div>'; return; }
    MON_NAMES = j.names || {};
    const hist = j.history || {};
    const keys = Object.keys(hist).sort();
    if(!keys.length){ body.innerHTML='<div class="cc" style="padding:14px;opacity:.75">No checks recorded yet for this ASIN. Hit “Check now”, then open this again.</div>'; return; }
    body.innerHTML = keys.map(k=>{
      const mkt = k.split("::")[1]||"";
      const snaps = (hist[k]||[]).slice().reverse();   // newest first
      let rows = snaps.map(s=>{
        const bb = _monSellerLabel(s.buybox_seller, mkt);
        const low = _lowestLanded(s.offers);
        const sellerCount = (s.seller_count!=null?s.seller_count:(s.sellers||[]).length);
        const cur = ((s.offers||[])[0]||{}).currency||"";
        return `<tr>
          <td class="cc">${esc(s.ts||"")}</td>
          <td style="text-align:center">${esc(String(sellerCount))}${s.total_offer_count&&s.total_offer_count>sellerCount?` <span class="cc">/${esc(String(s.total_offer_count))}</span>`:''}</td>
          <td>${low!=null?esc(String(low))+" "+esc(cur):'<span class="cc">—</span>'}</td>
          <td>${bb}</td>
          <td>${_monSnapSellers(s, mkt)}</td>
        </tr>`;
      }).join("");
      return `<div class="monhist-mkt"><div class="monhist-h"><span class="monchip">${esc(mkt)}</span> ${snaps.length} check(s)</div>
        <div style="overflow-x:auto"><table class="monhisttable">
          <thead><tr><th>When</th><th>Sellers</th><th>Lowest</th><th>Buy Box</th><th>Who was present</th></tr></thead>
          <tbody>${rows}</tbody></table></div></div>`;
    }).join("");
  }catch(e){ const body=document.getElementById("monhist_body"); if(body) body.innerHTML='<div class="cc" style="color:var(--red);padding:14px">Error: '+esc(String(e))+'</div>'; }
}
function _monSnapSellers(s, mkt){
  const ids = (s.sellers||[]);
  if(!ids.length) return '<span class="cc">—</span>';
  const bb = s.buybox_seller;
  return ids.slice(0,12).map(id=>{
    const nm = MON_NAMES[id+"::"+mkt];
    const cls = (id===bb)?'monhs bb':'monhs';
    return `<span class="${cls}" title="${esc(nm||id)}">${esc(nm? nm.slice(0,14) : id)}</span>`;
  }).join(" ") + (ids.length>12?` <span class="cc">+${ids.length-12}</span>`:"");
}
function closeMonHistory(){ const w=document.getElementById("monhistwrap"); if(w) w.remove(); }

// Global badge poll so the nav count stays fresh even when not on the section.
async function refreshMonBadge(){
  try{
    const j = await (await fetch("/monitor/status")).json();
    if(j && j.ok) updateMonBadge(j.unread||0);
  }catch(e){}
}
setInterval(refreshMonBadge, 120000);
setTimeout(refreshMonBadge, 8000);

async function loadMonitorList(){
  const host = document.getElementById("mon_list");
  if(host) host.innerHTML = '<div class="cc" style="padding:14px;opacity:.7"><span class="genspin"></span> Loading tracked ASINs…</div>';
  try{
    const j = await (await fetch("/monitor/list")).json();
    if(!j || !j.ok){ if(host) host.innerHTML = '<div class="cc" style="color:var(--red);padding:14px">Could not load: '+esc((j&&j.error)||"unknown")+'</div>'; return; }
    MON_EU = j.eu_marketplaces || MON_EU;
    MON_LIST = j.asins || [];
    renderMonitorMarketPicker();
    renderMonitorList();
  }catch(e){ if(host) host.innerHTML = '<div class="cc" style="color:var(--red);padding:14px">Error: '+esc(String(e))+'</div>'; }
}

/* ---- naming sellers from a file, instead of one at a time ----------------
 *
 *   "i have the names of the sellers which i can put in a csv file to tell the
 *    asin monitor that this seller id's person name is this. whether it is
 *    amazon, myself, or a third party. right now i have the ability to do it
 *    manually one by one"
 *
 * WHY THIS IS WORSE THAN IT SOUNDS TODAY. The auto-scraped cache is keyed
 * "sellerId::marketplace", so one seller trading in eight countries is eight
 * separate unnamed entries and naming them by hand is eight trips through the
 * modal. A seller's name is the same everywhere, so one row here settles it for
 * every marketplace and every ASIN, past snapshots included.
 *
 * SHOWN BEFORE IT IS APPLIED, because this writes into config.json -- which is
 * not somewhere to discover afterwards that a column was in the wrong place.
 */
let MON_SELLER_ROWS = [];

function monSellersPick(){
  const i = document.getElementById("mon_sellerfile");
  if(i) i.click();
}

async function monSellersUpload(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  try{
    const data = await new Promise(function(res, rej){
      const r = new FileReader();
      r.onload = function(){ res(r.result); };
      r.onerror = rej;
      r.readAsDataURL(f);
    });
    const j = await (await fetch("/monitor/sellers_preview", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({data: data, filename: f.name})})).json();
    if(!j || !j.ok){ toast((j && j.error) || "Could not read that file"); return; }
    MON_SELLER_ROWS = j.rows || [];
    monSellersPreview(j, f.name);
  }catch(e){ toast(String(e)); }
  finally{ input.value = ""; }
}

const _MON_KIND_WORD = {
  me: "Mine", amazon: "Amazon", authorised: "Authorised reseller",
  name: "Third party (named)", unknown: "Unknown — stays flagged",
};

function monSellersPreview(j, filename){
  const rows = j.rows || [];
  const changing = rows.filter(function(r){ return r.changes; });
  const same = rows.length - changing.length;
  let h = '<div class="modal" style="max-width:760px">'
    + '<button class="x" onclick="monSellersClose()">×</button>'
    + '<h3 style="margin:0 0 4px">Import seller names</h3>'
    + '<div class="cc" style="font-size:11.5px;margin-bottom:10px">'
    + esc(filename) + ' — <b>' + rows.length + '</b> seller'
    + (rows.length !== 1 ? 's' : '') + ' read'
    + (same ? ', ' + same + ' already set the same way' : '')
    + (j.invalid && j.invalid.length
        ? ', <span style="color:var(--warn)">' + j.invalid.length
          + ' line' + (j.invalid.length !== 1 ? 's' : '') + ' skipped</span>' : '')
    + '. Nothing has been saved yet.</div>';
  if(!rows.length){
    h += '<div class="db-warn-red">Nothing usable in that file.</div>';
  } else {
    h += '<div class="ri-scroll" style="max-height:380px">'
      + '<table class="kv" style="width:100%">'
      + '<thead><tr><th>Seller ID</th><th>Name</th><th>Treated as</th>'
      + '<th>Was</th></tr></thead><tbody>'
      + rows.map(function(r){
          return '<tr' + (r.changes ? '' : ' style="opacity:.5"') + '>'
            + '<td style="padding:5px 7px"><code style="font-size:11px">' + esc(r.seller_id) + '</code></td>'
            + '<td style="padding:5px 7px">' + esc(r.name || '—') + '</td>'
            + '<td style="padding:5px 7px">' + esc(_MON_KIND_WORD[r.kind] || r.kind) + '</td>'
            + '<td style="padding:5px 7px" class="cc">' + esc(r.previous_label || r.previous_kind || '') + '</td>'
            + '</tr>';
        }).join("")
      + '</tbody></table></div>';
    // The lines it could not use are NAMED. A file of two hundred with three
    // silently dropped is three sellers you go on believing are named.
    if(j.invalid && j.invalid.length){
      h += '<div class="cc" style="font-size:11px;margin-top:8px">Skipped: '
         + j.invalid.slice(0, 8).map(function(v){
             return 'line ' + v.row + ' (' + esc(v.why) + ')'; }).join(", ")
         + (j.invalid.length > 8 ? ' and ' + (j.invalid.length - 8) + ' more' : '')
         + '</div>';
    }
    h += '<div style="display:flex;gap:8px;margin-top:14px;align-items:center">'
      + '<button class="db-chip btn-primary" onclick="monSellersApply()">'
      + 'Apply ' + rows.length + ' seller' + (rows.length !== 1 ? 's' : '') + '</button>'
      + '<button class="db-chip" onclick="monSellersClose()">Cancel</button>'
      + '<span class="cc" style="font-size:11px">Applies to every marketplace '
      + 'and every ASIN, including past results.</span></div>';
  }
  h += '</div>';
  let w = document.getElementById("mon_sellerwrap");
  if(!w){
    w = document.createElement("div");
    w.id = "mon_sellerwrap";
    w.className = "modalwrap";
    document.body.appendChild(w);
  }
  w.innerHTML = h;
  w.classList.add("show");
}

function monSellersClose(){
  const w = document.getElementById("mon_sellerwrap");
  if(w) w.classList.remove("show");
  MON_SELLER_ROWS = [];
}

async function monSellersApply(){
  if(!MON_SELLER_ROWS.length){ monSellersClose(); return; }
  try{
    const j = await (await fetch("/monitor/sellers_import", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({rows: MON_SELLER_ROWS})})).json();
    if(!j || !j.ok){ toast((j && j.error) || "Could not apply"); return; }
    toast("Named " + j.applied + " seller" + (j.applied !== 1 ? "s" : "")
          + " everywhere.");
    monSellersClose();
    loadMonitorOverview();     // the flags recompute from the new names
  }catch(e){ toast(String(e)); }
}

// The EU marketplace checkboxes on the add form (default: all ticked).
function renderMonitorMarketPicker(){
  const box = document.getElementById("mon_markets");
  if(!box) return;
  box.innerHTML = MON_EU.map(m =>
    `<label class="monmkt"><input type="checkbox" value="${esc(m)}" checked> ${esc(m)}</label>`
  ).join("");
}
function _monSelectedMarkets(){
  const box = document.getElementById("mon_markets");
  if(!box) return [];
  return Array.prototype.slice.call(box.querySelectorAll("input:checked")).map(i=>i.value);
}
function monMarketsAll(on){
  const box = document.getElementById("mon_markets"); if(!box) return;
  box.querySelectorAll("input[type=checkbox]").forEach(i=>{ i.checked = !!on; });
}

function renderMonitorList(){
  const host = document.getElementById("mon_list");
  if(!host) return;
  if(!MON_LIST.length){
    host.innerHTML = '<div class="cc" style="padding:16px;opacity:.7">No ASINs tracked yet. Add one above to start watching it for new sellers.</div>';
    return;
  }
  let html = '<table class="montable"><thead><tr>'
    + '<th>ASIN</th><th>Label</th><th>Marketplaces</th><th>Condition</th><th>Added</th><th></th>'
    + '</tr></thead><tbody>';
  MON_LIST.forEach(r=>{
    const mkts = (r.marketplaces||[]);
    const mkChips = mkts.length===MON_EU.length
      ? '<span class="monchip all">all EU</span>'
      : mkts.map(m=>`<span class="monchip">${esc(m)}</span>`).join(" ");
    html += '<tr>'
      + `<td><a href="${esc(_dpUrl(r.asin, r.marketplace || r.mkt))}" target="_blank" rel="noopener" class="monasin">${esc(r.asin)}</a></td>`
      + `<td>${esc(r.label||"")||'<span class="cc">—</span>'}</td>`
      + `<td>${mkChips}</td>`
      + `<td>${esc(r.condition||"New")}</td>`
      + `<td class="cc">${esc(r.added_at||"")}</td>`
      + `<td style="white-space:nowrap">`
      +   `<button class="monhist" title="View offer history for this ASIN" onclick="openMonHistory('${esc(r.asin)}','${esc((r.label||'').replace(/'/g,""))}')"><i class="ti ti-history"></i></button> `
      +   `<button class="monrm" title="Stop tracking this ASIN" onclick="removeMonitorAsin('${esc(String(r.id))}','${esc(r.asin)}')"><i class="ti ti-trash"></i></button>`
      + `</td>`
      + '</tr>';
  });
  html += '</tbody></table>';
  host.innerHTML = html;
  const c = document.getElementById("mon_count");
  if(c) c.textContent = MON_LIST.length + " ASIN" + (MON_LIST.length!==1?"s":"") + " tracked";
}

async function addMonitorAsin(){
  const asinEl = document.getElementById("mon_asin");
  const labelEl = document.getElementById("mon_label");
  const asin = (asinEl&&asinEl.value||"").trim().toUpperCase();
  const label = (labelEl&&labelEl.value||"").trim();
  const markets = _monSelectedMarkets();
  if(!asin){ toast("Enter an ASIN"); if(asinEl) asinEl.focus(); return; }
  if(!/^[A-Z0-9]{10}$/.test(asin)){ toast("ASIN must be 10 letters/digits, e.g. B0XXXXXXXX"); return; }
  if(!markets.length){ toast("Pick at least one marketplace"); return; }
  const btn = document.getElementById("mon_addbtn");
  if(btn){ btn.disabled = true; }
  try{
    const j = await (await fetch("/monitor/add",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({asin, label, marketplaces:markets, condition:"New"})})).json();
    if(!j || !j.ok){ toast("Add failed: "+((j&&j.error)||"unknown")); return; }
    toast(j.updated ? ("Updated "+asin) : ("Now tracking "+asin));
    if(asinEl) asinEl.value = "";
    if(labelEl) labelEl.value = "";
    monMarketsAll(true);
    loadMonitorOverview();
  }catch(e){ toast("Add error: "+e); }
  finally{ if(btn) btn.disabled = false; }
}

// ---- bulk upload (Feature 2) ------------------------------------------------
function monPickFile(){ const el=document.getElementById("mon_file"); if(el) el.click(); }

async function monBulkUpload(inp){
  const f = inp && inp.files && inp.files[0];
  if(!f) return;
  const rd = new FileReader();
  rd.onload = async () => {
    try{
      const j = await (await fetch("/monitor/bulk_preview",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({filename:f.name, data:String(rd.result)})})).json();
      if(!j || !j.ok){ toast("Could not read file: "+((j&&j.error)||"unknown")); return; }
      showBulkPreview(j);
    }catch(e){ toast("Upload error: "+e); }
    finally{ if(inp) inp.value=""; }
  };
  rd.readAsDataURL(f);
}

function showBulkPreview(j){
  if(document.getElementById("bulkwrap")) closeBulk();
  window._BULK_ALL = j.rows||[];
  window._BULK_STATUS_COUNTS = j.status_counts||{};
  window._BULK_FILTER = "active";                 // default = Active only
  const invalid = j.invalid||[];
  const invalidHtml = invalid.length
    ? `<details style="margin-top:8px"><summary class="cc" style="color:var(--warn);cursor:pointer">${invalid.length} invalid row(s) — skipped</summary>
        <div class="cc" style="max-height:150px;overflow:auto;margin-top:6px;line-height:1.6">${invalid.slice(0,60).map(x=>`row ${x.row}: “${esc(String(x.value))}” — ${esc(x.reason)}`).join("<br>")}</div></details>`
    : "";
  const sc = window._BULK_STATUS_COUNTS;
  const hasStatus = Object.keys(sc).length>0;
  const scText = hasStatus ? " — " + Object.keys(sc).map(k=>`<b>${sc[k]}</b> ${esc(k)}`).join(", ") : "";
  const filterRow = hasStatus ? `<div class="bulkfilter">Import:
      <button class="tabpill" data-f="active" onclick="monBulkSetFilter('active')">Active only</button>
      <button class="tabpill" data-f="active_inactive" onclick="monBulkSetFilter('active_inactive')">Active + Inactive</button>
      <button class="tabpill" data-f="all" onclick="monBulkSetFilter('all')">All</button></div>` : "";
  const dlg=document.createElement("div"); dlg.className="modalwrap open"; dlg.id="bulkwrap"; dlg.style.zIndex="130";
  dlg.innerHTML=`<div class="modal" style="max-width:800px;position:relative">
    <button class="x" onclick="closeBulk()">×</button>
    <h3><i class="ti ti-upload"></i> Import ASINs</h3>
    <div class="cc" style="margin:2px 0 8px"><b style="color:var(--ink)">Found ${j.found||0}</b> ASIN(s)${scText}${invalid.length?`, <b style="color:var(--warn)">${invalid.length}</b> invalid`:''}.</div>
    ${filterRow}
    ${invalidHtml}
    <div id="bulk_table" style="max-height:330px;overflow:auto;margin-top:10px"></div>
    <div class="pl-actions">
      <button class="mktbtn" onclick="closeBulk()">Cancel</button>
      <button class="mktbtn on" id="bulk_go" onclick="monBulkImport()"></button>
    </div>
  </div>`;
  document.body.appendChild(dlg);
  monBulkSetFilter(hasStatus ? "active" : "all");
}
function _bulkStatusMatch(r, f){
  const st = String(r.status||"");
  if(f==="all") return true;
  if(f==="active") return st==="Active";
  if(f==="active_inactive") return st==="Active" || st==="Inactive";
  return true;
}
function monBulkFiltered(){
  const rows = window._BULK_ALL||[];
  const hasStatus = Object.keys(window._BULK_STATUS_COUNTS||{}).length>0;
  if(!hasStatus) return rows;                     // non-report file -> import all
  return rows.filter(r=>_bulkStatusMatch(r, window._BULK_FILTER||"active"));
}
function monBulkSetFilter(f){
  window._BULK_FILTER = f;
  document.querySelectorAll("#bulkwrap .bulkfilter .tabpill").forEach(b=>b.classList.toggle("active", b.dataset.f===f));
  const rows = monBulkFiltered();
  const tbl = document.getElementById("bulk_table");
  if(tbl){
    const body = rows.slice(0,300).map(r=>{
      const mk=(r.marketplaces||[]); const mkc = mk.length>=10?'<span class="monchip all">all EU</span>':mk.map(m=>`<span class="monchip">${esc(m)}</span>`).join(" ");
      return `<tr><td class="monasin">${esc(r.asin)}</td><td>${esc(r.label||"")||'<span class="cc">—</span>'}</td><td>${r.status?esc(r.status):'<span class="cc">—</span>'}</td><td>${mkc}</td><td>${r.existing?'<span class="cc">update</span>':'<span class="monchip ok">new</span>'}</td></tr>`;
    }).join("");
    tbl.innerHTML = `<table class="montable"><thead><tr><th>ASIN</th><th>Label</th><th>Status</th><th>Marketplaces</th><th></th></tr></thead><tbody>${body||'<tr><td colspan="5" class="cc">Nothing matches this filter.</td></tr>'}</tbody></table>`;
  }
  const btn=document.getElementById("bulk_go");
  if(btn){ btn.disabled = !rows.length; btn.innerHTML = `<i class="ti ti-check"></i> Import ${rows.length} ASIN(s)`; }
}
function closeBulk(){ const w=document.getElementById("bulkwrap"); if(w) w.remove(); window._BULK_ALL=null; }

async function monBulkImport(){
  const rows = monBulkFiltered();
  if(!rows.length){ closeBulk(); return; }
  const btn=document.getElementById("bulk_go"); if(btn){ btn.disabled=true; btn.textContent="Importing…"; }
  try{
    const j = await (await fetch("/monitor/bulk_import",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({rows})})).json();
    if(!j || !j.ok){ toast("Import failed: "+((j&&j.error)||"unknown")); if(btn) btn.disabled=false; return; }
    toast("Imported: "+j.added+" new, "+j.updated+" updated"+(j.failed?(", "+j.failed+" failed"):""));
    closeBulk(); loadMonitorOverview();
  }catch(e){ toast("Import error: "+e); if(btn) btn.disabled=false; }
}

async function removeMonitorAsin(id, asin){
  if(!await uiConfirm("Stop tracking "+(asin||"this ASIN")+"?")) return;
  try{
    const j = await (await fetch("/monitor/remove",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id, asin})})).json();
    if(!j || !j.ok){ toast("Remove failed: "+((j&&j.error)||"unknown")); return; }
    toast("Stopped tracking "+(asin||""));
    loadMonitorOverview();
  }catch(e){ toast("Remove error: "+e); }
}
