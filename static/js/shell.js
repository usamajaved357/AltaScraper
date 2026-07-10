// ---- shell navigation ----
// ===================== SHELL NAVIGATION (new layout) =====================
// Drives home <-> workspace screens and the in-workspace section switching.
// All existing functions (card, render, loadRows, runMode, switchView, the
// brand panel, AI image gen, chat) are preserved and called from here.

let VIEWS = [];        // [{key,label,brand,marketplace,sheet,tab}]
let ACTIVE_WS = null;  // currently-open workspace member (a view)
let CUR_GROUP = null;  // currently-open workspace group (brand across marketplaces)
let CUR_SEC = "listings";

// Which spreadsheet + tab the OPEN workspace actually reads and writes.
// {out_id,out_gid,out_tab,in_id,in_gid,missing:[]} -- or null for Dropshipping.
// Seeded from /accounts/select, then corrected by /rows, which reports the tab it
// really opened. Shown in the header so the user can always see (and click through
// to) the sheet the app is using, instead of trusting that it picked the right one.
let WS_SOURCE = null;

function _srcLink(id, gid){
  if(!id) return "";
  return "https://docs.google.com/spreadsheets/d/" + id + "/edit" + (gid ? ("#gid=" + gid) : "");
}
function _srcChip(label, id, gid, tab){
  if(!id) return `<span><b>${esc(label)}:</b> <span class="missing">not set</span></span>`;
  const shortId = id.length > 18 ? (id.slice(0, 10) + "…" + id.slice(-4)) : id;
  const where = tab ? esc(tab) : (gid ? ("gid " + esc(String(gid))) : "no tab set");
  const cls = (!tab && !gid) ? ' class="missing"' : "";
  return `<span><b>${esc(label)}:</b> `
       + `<a href="${_srcLink(id, gid)}" target="_blank" rel="noopener" title="${esc(id)}">${esc(shortId)}</a>`
       + ` <code${cls}>· ${where}</code></span>`;
}
function renderDataSource(){
  const el = document.getElementById("ws_datasrc");
  if(!el) return;
  const s = WS_SOURCE;
  if(!s){ el.innerHTML = ""; return; }
  let html = `<span style="opacity:.7"><i class="ti ti-database"></i> Data source</span>`
           + _srcChip("Output", s.out_id, s.out_gid, s.out_tab)
           + _srcChip("Input",  s.in_id,  s.in_gid,  "");
  if(s.missing && s.missing.length){
    html += `<span class="missing"><i class="ti ti-alert-triangle"></i> `
          + `${esc(s.missing.join(" and "))} not configured</span>`
          + ` <button class="linkbtn" onclick="openCurrentAccountSettings()">Fix in Account &amp; sheets</button>`;
  }
  el.innerHTML = html;
}

function _wsColor(v){
  // deterministic accent per workspace
  if(!v || !v.brand) return {bg:"rgba(76,141,255,.16)", fg:"#9cc1ff"};
  const palette=[["#E1F5EE","#0F6E56"],["#EEEDFE","#3C3489"],["#FAECE7","#993C1D"],
                 ["#E6F1FB","#185FA5"],["#FBEAF0","#993556"],["#FAEEDA","#854F0B"]];
  let h=0; for(const c of v.key) h=(h*31+c.charCodeAt(0))>>>0;
  const p=palette[h%palette.length];
  return {bg:p[0], fg:p[1]};
}
function _initials(name){
  const w=(name||"").trim().split(/\s+/);
  return ((w[0]||"")[0]||"?").toUpperCase()+((w[1]||"")[0]||"").toUpperCase();
}

function _baseName(v){
  if(!v.brand) return "__dropshipping__";
  return String(v.brand).replace(/\s+(USA?|UK|EU|CA|AU|DE|FR|IT|ES)\b\s*$/i,"").trim() || v.brand;
}
function _mktOf(v){
  const m=(v.marketplace||"").toUpperCase();
  if(m) return m;
  const t=(v.brand||"").toUpperCase();
  if(/\bUSA?\b/.test(t)) return "US";
  if(/\bUK\b/.test(t)) return "UK";
  return "";
}
function workspaceGroups(){
  const groups={};
  VIEWS.forEach(v=>{
    const base=_baseName(v);
    if(!groups[base]) groups[base]={base, members:[], isDrop:!v.brand};
    groups[base].members.push(v);
  });
  return Object.values(groups).map(g=>{ g.label=g.isDrop?"Dropshipping":g.base; return g; });
}

let ACCOUNTS = [];
async function _fetchJSON(url, opts, ms){
  // fetch with a hard timeout so a slow/stalled route can't freeze the page
  ms = ms || 12000;
  const ctrl = new AbortController();
  const t = setTimeout(()=>ctrl.abort(), ms);
  try{
    const r = await fetch(url, Object.assign({signal:ctrl.signal}, opts||{}));
    clearTimeout(t);
    return await r.json();
  }catch(e){
    clearTimeout(t);
    return {ok:false, error:(e&&e.name==='AbortError')?('timed out after '+(ms/1000)+'s'):String(e), _failed:true};
  }
}
async function loadHome(){
  const grid=document.getElementById("wsgrid");
  grid.innerHTML='<div class="empty" style="grid-column:1/-1">Loading workspaces…</div>';
  let acctData=await _fetchJSON("/accounts/list");
  if(acctData && acctData.config_error){
    grid.innerHTML='<div class="empty" style="grid-column:1/-1;text-align:left">'
      +'<div style="color:#ef9a9a;font-weight:600;margin-bottom:8px">⚠ Your config.json has an error</div>'
      +'<div class="cc" style="white-space:pre-wrap">'+esc(acctData.error||"")+'</div>'
      +'<div class="cc" style="margin-top:10px">Fix the file, save it, then click Home to retry.</div></div>';
    return;
  }
  if(acctData && acctData._failed){
    grid.innerHTML='<div class="empty" style="grid-column:1/-1;text-align:left">'
      +'<div style="color:#ef9a9a;font-weight:600;margin-bottom:8px">⚠ Could not load accounts</div>'
      +'<div class="cc">'+esc(acctData.error||"")+'</div>'
      +'<div class="cc" style="margin-top:8px">Try clicking Home again. If this persists, check the terminal where the app runs for an error.</div></div>';
    return;
  }
  ACCOUNTS=(acctData&&acctData.accounts)||[];
  const vd=await _fetchJSON("/view/list", null, 8000);   // don't let this stall the page
  VIEWS=(vd&&vd.views)||[];
  let cards="";
  // inline SVGs so the home cards never depend on the icon-font CDN
  const SVG_CART='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="19" r="2"/><circle cx="17" cy="19" r="2"/><path d="M17 17H6V3H4"/><path d="M6 5l14 1-1 7H6"/></svg>';
  const SVG_PLUG='<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 12h10v3a5 5 0 0 1-10 0z"/><path d="M9 12V7M15 12V7M12 20v2"/></svg>';
  const SVG_PLUGX='<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 12h7v3a5 5 0 0 1-7 4.5"/><path d="M9 12V7M14 12V7"/><path d="M18 6l4 4M22 6l-4 4"/></svg>';
  const SVG_PLUS='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>';
  // Dropshipping workspace (not an Amazon account -- the eBay->Amazon arbitrage side)
  cards += `<div class="wscard" onclick='enterDropshipping()'>
      <button class="peek" title="Reveal" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
      <div style="display:flex;align-items:center;gap:11px">
        <div class="ic" style="background:rgba(76,141,255,.16);color:#9cc1ff">${SVG_CART}</div>
        <div style="flex:1"><div class="nm pii">Dropshipping</div><div class="sub pii">eBay → Amazon arbitrage</div></div>
        <button class="wsedit" title="Assign input &amp; output sheets" onclick='event.stopPropagation();openDropshippingSheets()'><i class="ti ti-settings"></i></button>
      </div>
      <div class="stats"><span class="cc">cross-account</span></div>
    </div>`;
  // each Amazon ACCOUNT is a workspace
  cards += ACCOUNTS.map(a=>{
    const col=_wsColorKey(a.id||a.label);
    const connected=a.has_creds;
    const mkts=(a.marketplaces&&a.marketplaces.length)?a.marketplaces.join(" · ")
      :(connected?'<span class="cc">marketplaces not detected</span>':'<span class="cc">draft-only · not connected</span>');
    const brandcount=(a.brands&&a.brands.length)?(a.brands.length+" trademark"+(a.brands.length>1?"s":"")):"";
    const stateBadge = connected
      ? '<span class="connpill on" title="SP-API credentials present">'+SVG_PLUG+' connected</span>'
      : '<span class="connpill off" title="No credentials yet — drafting works, live actions disabled">'+SVG_PLUGX+' draft-only</span>';
    return `<div class="wscard" onclick='enterAccount(${JSON.stringify(a.id)})'>
      <button class="peek" title="Reveal" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
      <div style="display:flex;align-items:center;gap:11px">
        <div class="ic" style="background:${col.bg};color:${col.fg}">${_initials(a.label)}</div>
        <div style="flex:1"><div class="nm pii">${esc(a.label)}</div><div class="sub pii">Amazon account${a.seller_id?(" · "+esc(a.seller_id)):""}</div></div>
        ${stateBadge}
        <button class="wsedit" title="Edit account &amp; sheet links" onclick='event.stopPropagation();openAccountEditor(${JSON.stringify(a.id)})'><i class="ti ti-settings"></i></button>
      </div>
      <div class="stats pii"><span>${mkts}</span>${brandcount?`<span>${esc(brandcount)}</span>`:""}</div>
    </div>`;
  }).join("");
  cards += `<div class="wscard add" onclick="openAccountEditor('')">${SVG_PLUS} Add account</div>`;
  grid.innerHTML = cards;
}
async function openDropshippingSheets(){
  // Reuse the account modal shell to edit the DEFAULT (Dropshipping) sheets.
  const m=document.getElementById("acctmodal"); if(!m) return; m.classList.add("open");
  const body=document.getElementById("acctmodalbody");
  body.innerHTML='<div class="cc" style="padding:12px"><span class="genspin"></span> Loading…</div>';
  let s; try{ s=await (await fetch("/settings/dropshipping_sheets")).json(); }catch(e){ s={ok:false}; }
  const S=(s&&s.ok)?s:{output_sheet_url:"",input_sheet_url:"",output_tab:""};
  body.innerHTML=`
    <div style="font-weight:600;font-size:14px;margin-bottom:2px"><i class="ti ti-table"></i> Dropshipping default sheets</div>
    <div class="cc" style="font-size:11.5px;margin-bottom:10px">The built-in Dropshipping workspace (eBay → Amazon) uses these sheets. Paste the <b>full Google Sheets link</b> with the tab open — the app reads the spreadsheet ID and the tab (gid) from the URL. Leave blank to fall back to the app's config defaults.</div>
    <table class="kv">
      <tr><td class="k">Output sheet URL <span class="cc">(generated listings)</span></td><td class="v"><input class="ed" id="ds_output_url" value="${esc(S.output_sheet_url||'')}" oninput="_showParsed('ds_output_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ds_output_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
      <tr><td class="k">Input sheet URL <span class="cc">(source rows)</span></td><td class="v"><input class="ed" id="ds_input_url" value="${esc(S.input_sheet_url||'')}" oninput="_showParsed('ds_input_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ds_input_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
    </table>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <button class="primary" onclick="saveDropshippingSheets()">Save sheets</button>
      <button onclick="closeAccountEditor()">Cancel</button>
      <span id="ds_status" class="cc"></span>
    </div>`;
}
async function saveDropshippingSheets(){
  const out=((document.getElementById("ds_output_url")||{}).value||"").trim();
  const inp=((document.getElementById("ds_input_url")||{}).value||"").trim();
  const st=document.getElementById("ds_status");
  if(st) st.textContent="Saving…";
  try{
    const j=await (await fetch("/settings/dropshipping_sheets",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({output_sheet_url:out, input_sheet_url:inp})})).json();
    if(j.ok){ toast("Dropshipping sheets saved"+(j.output_tab?(" · tab: "+j.output_tab):"")); closeAccountEditor(); loadHome(); }
    else { if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(String(e))+'</span>'; }
}
function _wsColorKey(key){
  const palette=[["#E1F5EE","#0F6E56"],["#EEEDFE","#3C3489"],["#FAECE7","#993C1D"],
                 ["#E6F1FB","#185FA5"],["#FBEAF0","#993556"],["#FAEEDA","#854F0B"]];
  let h=0; for(const c of String(key)) h=(h*31+c.charCodeAt(0))>>>0;
  const p=palette[h%palette.length]; return {bg:p[0], fg:p[1]};
}

function enterGroup(base){
  const groups=workspaceGroups();
  const g=groups.find(x=>x.base===base) || groups[0];
  CUR_GROUP=g;
  enterWorkspace(g.members[0].key);
  buildMktSwitch(g);
}

let CUR_ACCOUNT = null;
async function enterAccount(accountId){
  const a=ACCOUNTS.find(x=>x.id===accountId) || ACCOUNTS[0];
  if(!a){ toast("Account not found"); return; }
  CUR_ACCOUNT=a;
  // Refresh inventory alert badge when workspace changes (fire-and-forget)
  if(typeof invBadgeRefresh === 'function') invBadgeRefresh();
  const hasCreds = !!(a.has_creds || (a.refresh_token && !String(a.refresh_token).startsWith("PUT_")));
  // A read-only workspace owns no Amazon app. It may borrow another account's app to
  // look up catalogue data while generating, but it has no listings of its own to show
  // and may never publish. can_publish comes from the backend, which is what actually
  // enforces it -- this only keeps the UI from offering actions that will be refused.
  window.WS_READONLY = (a.can_publish === false);
  window.WS_CREDS_SOURCE = a.credentials_source_account_id || "";
  LIVE_ITEMS=[]; APLUS_BY_ASIN={};   // never carry one account's catalog or A+ into another
  LIST_SOURCE = hasCreds ? 'all' : 'drafts';   // All = drafts + live for connected accounts
  // default marketplace: account's configured default, else first detected
  const dflt = a.default_marketplace && (a.marketplaces||[]).indexOf(a.default_marketplace)>=0 ? a.default_marketplace : null;
  WS_MARKET = dflt || ((a.marketplaces && a.marketplaces.length) ? a.marketplaces[0] : "");
  CUR_SYMBOL = (WS_MARKET==="US"||WS_MARKET==="CA"||WS_MARKET==="MX") ? "$" : ((WS_MARKET==="EU"||["DE","FR","IT","ES","NL"].includes(WS_MARKET)) ? "\u20ac" : "\u00a3");
  // A read-only workspace has no live catalog at all -- /live/catalog refuses it --
  // so don't offer the Live / All / Sync controls that can only fail.
  var sw=document.getElementById('srcswitch');
  if(sw){ sw.style.display = (hasCreds && !window.WS_READONLY) ? 'flex' : 'none';
          sw.querySelectorAll('.mktbtn').forEach(b=>b.classList.toggle('on',b.dataset.src===LIST_SOURCE)); }
  // tell the backend this account is active (all submit/preview use ITS creds).
  // The reply names the exact spreadsheet + tab this workspace is bound to, and
  // lists anything unset -- shown in the header so the data source is never a guess.
  try{
    const _sel=await (await fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:a.id})})).json();
    WS_SOURCE = _sel && _sel.ok ? {out_id:_sel.sheet||"", out_gid:_sel.tab_gid||"", out_tab:_sel.tab||"",
                                   in_id:_sel.input_sheet||"", in_gid:_sel.input_tab_gid||"",
                                   missing:_sel.missing||[]} : null;
  }catch(e){ WS_SOURCE=null; }
  renderDataSource();
  // paint shell
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  const col=_wsColorKey(a.id||a.label);
  const icEl=document.getElementById("ws_ic");
  icEl.style.background=col.bg; icEl.style.color=col.fg; icEl.innerHTML=_initials(a.label);
  document.getElementById("ws_nm").textContent=a.label;
  if(window.WS_READONLY){
    const _lender=(ACCOUNTS||[]).find(x=>x.id===window.WS_CREDS_SOURCE);
    document.getElementById("ws_sub").innerHTML =
      '<span style="color:#e3b768;font-weight:600"><i class="ti ti-lock"></i> Read-only</span>'
      + (_lender ? ' · generating with '+esc(_lender.label)+"'s Amazon app" : ' · no Amazon app')
      + ' · cannot publish';
  } else {
    document.getElementById("ws_sub").textContent="Amazon account"+(a.seller_id?(" · "+a.seller_id):"");
  }
  document.getElementById("ws_title").textContent="Listings";
  document.getElementById("crumbs").innerHTML=`<span class="sep">/</span><span class="here">${esc(a.label)}</span>`;
  document.getElementById("nav_setup").style.display="flex"; // brand/account setup
  // Per-workspace features: show the Supplier Import (harvest) nav only if the
  // account has the "harvest" feature enabled in its settings.
  const _feats = a.features || [];
  const _hv = document.getElementById("nav_harvest");
  if(_hv) _hv.style.display = _feats.includes("harvest") ? "flex" : "none";
  window.WS_FEATURES = _feats;
  window.WS_BRAND="";
  ACTIVE_WS={key:a.id, label:a.label, account:true};
  // marketplace switcher from the account's (detected) marketplaces
  buildAccountMktSwitch(a);
  navTo("listings");
  if(LIST_SOURCE==='all' || LIST_SOURCE==='live'){ loadRows(); loadLiveCatalog(false); }
  else loadRows();
}
function enterDropshipping(){
  CUR_ACCOUNT=null;
  WS_SOURCE=null; renderDataSource();   // dropshipping uses the config default sheet
  try{ fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:""})}); }catch(e){}
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  const icEl=document.getElementById("ws_ic");
  icEl.style.background="rgba(76,141,255,.16)"; icEl.style.color="#9cc1ff";
  icEl.innerHTML='<i class="ti ti-shopping-cart"></i>';
  document.getElementById("ws_nm").textContent="Dropshipping";
  document.getElementById("ws_sub").textContent="eBay → Amazon";
  document.getElementById("ws_title").textContent="Listings";
  document.getElementById("crumbs").innerHTML='<span class="sep">/</span><span class="here">Dropshipping</span>';
  document.getElementById("nav_setup").style.display="none";
  var _hv=document.getElementById("nav_harvest"); if(_hv) _hv.style.display="none";
  window.WS_FEATURES=[];
  window.WS_BRAND="";
  ACTIVE_WS={key:"", label:"Dropshipping"};
  document.getElementById("mktswitch").innerHTML="";
  var sw=document.getElementById('srcswitch'); if(sw) sw.style.display='none';
  LIST_SOURCE='drafts'; LIVE_ITEMS=[];
  navTo("listings");
  loadRows();
}
function buildAccountMktSwitch(a){
  const host=document.getElementById("mktswitch"); if(!host) return;
  if(!a.has_creds){
    host.innerHTML='<span class="mktlabel" title="Add SP-API credentials to enable live features">draft-only · <a href="#" onclick="openAccountEditor(\''+esc(a.id)+'\');return false" style="color:#9cc1ff">connect account</a></span>';
    return;
  }
  const mkts=a.marketplaces&&a.marketplaces.length?a.marketplaces:[];
  if(!mkts.length){
    host.innerHTML='<button class="mktbtn" onclick="detectMarketplaces(\''+esc(a.id)+'\')"><i class="ti ti-radar"></i> Detect marketplaces</button>';
    return;
  }
  // keep the current selection if it's valid for this account; else default to first
  if(!WS_MARKET || (WS_MARKET!=="__all__" && mkts.indexOf(WS_MARKET)<0)){ WS_MARKET=mkts[0]; }
  if(WS_MARKET!=="__all__"){
    CUR_SYMBOL=(WS_MARKET==="US"||WS_MARKET==="CA"||WS_MARKET==="MX")?"$":((WS_MARKET==="EU"||["DE","FR","IT","ES","NL"].includes(WS_MARKET))?"\u20ac":"\u00a3");
  }
  host.innerHTML =
    `<button class="mktbtn ${WS_MARKET==='__all__'?'on':''}" title="Show listings across every marketplace (fetches each — can be slow)" onclick="switchAccountMarket('__all__')">All</button>`
    + mkts.map(m=>{
        const isDflt = a.default_marketplace===m;
        return `<button class="mktbtn ${m===WS_MARKET?'on':''}" onclick="switchAccountMarket('${esc(m)}')">${esc(m)}${isDflt?' <span title="default" style="color:#e3b768">\u2605</span>':''}</button>`;
      }).join("")
    + `<button class="mktbtn" title="Set current marketplace (${esc(WS_MARKET||'')}) as this account\u2019s default" onclick="setDefaultMarketplace()">\u2606 default</button>`
    + '<button class="mktbtn" title="Re-detect" onclick="detectMarketplaces(\''+esc(a.id)+'\')"><i class="ti ti-refresh"></i></button>';
}
async function detectMarketplaces(accountId){
  var host=document.getElementById("mktswitch");
  if(host) host.innerHTML='<span class="mktlabel"><span class="genspin"></span> detecting…</span>';
  try{
    var j=await (await fetch("/accounts/detect_marketplaces",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:accountId})})).json();
    if(!j.ok){ toast("Detect failed: "+(j.error||"")); 
      // refresh the account object so the button comes back
      try{ var al=await (await fetch("/accounts/list")).json(); ACCOUNTS=al.accounts||[]; }catch(e){}
      var a=ACCOUNTS.find(x=>x.id===accountId); if(a) buildAccountMktSwitch(a);
      return;
    }
    toast("Detected: "+(j.marketplaces||[]).join(", "));
    // update local account + rebuild switcher
    try{ var al=await (await fetch("/accounts/list")).json(); ACCOUNTS=al.accounts||[]; }catch(e){}
    var a2=ACCOUNTS.find(x=>x.id===accountId);
    if(a2){ CUR_ACCOUNT=a2; buildAccountMktSwitch(a2); }
  }catch(e){ toast("Error: "+e); }
}
async function setDefaultMarketplace(){
  if(!CUR_ACCOUNT || !WS_MARKET || WS_MARKET==="__all__"){ toast("Pick a specific marketplace first."); return; }
  try{
    const j=await (await fetch("/accounts/set_default_marketplace",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id,marketplace:WS_MARKET})})).json();
    if(!j.ok){ toast("Could not set default: "+(j.error||"")); return; }
    CUR_ACCOUNT.default_marketplace=WS_MARKET;
    const acc=ACCOUNTS.find(x=>x.id===CUR_ACCOUNT.id); if(acc) acc.default_marketplace=WS_MARKET;
    buildAccountMktSwitch(CUR_ACCOUNT);
    toast(WS_MARKET+" is now the default marketplace for "+CUR_ACCOUNT.label);
  }catch(e){ toast("Error: "+e); }
}
async function switchAccountMarket(m){
  WS_MARKET=m;
  CUR_SYMBOL=(m==="US"||m==="CA"||m==="MX")?"$":(m==="UK"?"\u00a3":(m==="EU"||["DE","FR","IT","ES","NL"].includes(m))?"\u20ac":"\u00a3");
  try{ await fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"",marketplace:m})}); }catch(e){}
  if(CUR_ACCOUNT) buildAccountMktSwitch(CUR_ACCOUNT);
  if(LIST_SOURCE==='live'||LIST_SOURCE==='all'){ loadLiveCatalog(false); } else { loadRows(); }
}

function openCurrentAccountSettings(){
  // Resolve the account currently in focus. CUR_ACCOUNT is set by enterAccount;
  // it's intentionally null in the built-in Dropshipping workspace.
  if(CUR_ACCOUNT && CUR_ACCOUNT.id){ openAccountEditor(CUR_ACCOUNT.id); return; }
  // Dropshipping (or no account selected): try the server's active account id.
  if(ACTIVE_WS && ACTIVE_WS.account && ACTIVE_WS.key){ openAccountEditor(ACTIVE_WS.key); return; }
  // Built-in Dropshipping workspace has no account object — explain + send to Home.
  if(ACTIVE_WS && !ACTIVE_WS.account){
    toast("Dropshipping uses the default sheet. To set per-account sheet links, open a real account from All workspaces.");
    return;
  }
  toast("Open an account from All workspaces first, then click Account & sheets.");
}
function openAccountEditor(id){
  const a = id ? (ACCOUNTS.find(x=>x.id===id)||{}) : {};
  const m=document.getElementById("acctmodal"); m.classList.add("open");
  document.getElementById("acctmodalbody").innerHTML=`
    <table class="kv">
      <tr><td class="k">Account name</td><td class="v"><input class="ed" id="ac_label" value="${esc(a.label||'')}" placeholder="e.g. Jack Reacherd (UK)"></td></tr>
      <tr><td class="k">Seller / merchant ID</td><td class="v"><input class="ed" id="ac_seller" value="${esc(a.seller_id||'')}" placeholder="A1B2C3..."></td></tr>
      <tr><td class="k">LWA client ID</td><td class="v"><input class="ed" id="ac_clientid" value="${esc(a.lwa_client_id||'')}" placeholder="amzn1.application-oa2-client..."></td></tr>
      <tr><td class="k">LWA client secret</td><td class="v"><input class="ed" id="ac_secret" type="password" placeholder="${a.has_secret?'•••••• (leave blank to keep)':'paste secret'}"></td></tr>
      <tr><td class="k">Refresh token</td><td class="v"><input class="ed" id="ac_refresh" type="password" placeholder="${a.has_creds?'•••••• (leave blank to keep)':'paste refresh token'}"></td></tr>
      <tr><td class="k">Primary marketplace</td><td class="v"><select class="ed" id="ac_marketplace"><option value="UK"${(a.default_marketplace||'UK')==='UK'?' selected':''}>UK — amazon.co.uk (GBP)</option><option value="US"${(a.default_marketplace||'')==='US'?' selected':''}>US — amazon.com (USD)</option></select><div class="cc" style="font-size:11px;margin-top:2px">Drives pricing, fees, SP-API and the flat-file route for this account's listings.</div></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-table"></i> Google Sheets for this account</div><div class="cc" style="font-size:11.5px">Paste the <b>full Google Sheets link</b> (with the tab open). The app reads the spreadsheet ID and the tab (gid) from the URL — so each account's US/UK listings go to the right place.</div></td></tr>
      <tr><td class="k">Input sheet URL <span class="cc">(source rows)</span></td><td class="v"><input class="ed" id="ac_input_url" value="${esc(a.input_sheet_url||'')}" oninput="_showParsed('ac_input_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ac_input_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
      <tr><td class="k">Output sheet URL <span class="cc">(generated listings)</span></td><td class="v"><input class="ed" id="ac_output_url" value="${esc(a.output_sheet_url||'')}" oninput="_showParsed('ac_output_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ac_output_parsed" class="cc" style="font-size:11px;margin-top:2px"></div></td></tr>
      <tr><td class="k">Drive image folder URL <span class="cc">(image storage)</span></td><td class="v"><input class="ed" id="ac_drive_url" value="${esc(a.drive_folder_url||'')}" placeholder="https://drive.google.com/drive/folders/…"><div class="cc" id="ac_drive_share" style="font-size:11px;margin-top:3px">Generated images upload here into per-product <code>SKU_ProductName</code> subfolders. <b>Share this folder (Editor) with the service account</b> shown below, or uploads will be denied.</div></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-shield-check"></i> UK Responsible Person <span class="cc">(only needed for Amazon.co.uk listings)</span></div><div class="cc" style="font-size:11.5px">Selling on Amazon.co.uk from outside the UK legally requires a UK Responsible Person (name + real UK address + contact). Fill this once and every UK listing inherits it. Leave blank for US-only — US listings are unaffected.</div></td></tr>
      <tr><td class="k">RP legal name</td><td class="v"><input class="ed" id="ac_rp_name" value="${esc((a.uk_responsible_person||{}).name||'')}" placeholder="e.g. FLIPX LTD"></td></tr>
      <tr><td class="k">RP UK address</td><td class="v"><input class="ed" id="ac_rp_address" value="${esc((a.uk_responsible_person||{}).address||'')}" placeholder="Real UK address — no PO boxes"></td></tr>
      <tr><td class="k">RP email</td><td class="v"><input class="ed" id="ac_rp_email" value="${esc((a.uk_responsible_person||{}).email||'')}" placeholder="contact@…"></td></tr>
      <tr><td class="k">RP phone</td><td class="v"><input class="ed" id="ac_rp_phone" value="${esc((a.uk_responsible_person||{}).phone||'')}" placeholder="+44…"></td></tr>
      <tr><td class="k">Trademarks / brands <span class="cc">(comma-separated)</span></td><td class="v"><input class="ed" id="ac_brands" value="${esc((a.brands||[]).join(', '))}" placeholder="Headbanger Lures, Leech Eyewear"></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-shopping-cart"></i> eBay source credentials</div><div class="cc" style="font-size:11.5px">Used to scrape the source eBay listing for each row.</div></td></tr>
      <tr><td class="k">eBay account</td><td class="v">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
          <input type="checkbox" id="ac_ebay_global" ${(a.ebay_app_id && a.has_ebay_cert)?'':'checked'} onchange="_toggleEbayGlobal(this.checked)">
          <span>Use my global eBay credentials</span>
        </label>
        <div class="cc" style="font-size:11.5px;margin-top:3px">Your one eBay developer app, shared by every account (set in <b>AI &amp; settings ▸ eBay</b>). Untick only when this account has its own developer app.</div>
      </td></tr>
      <tr id="ac_ebay_row_app" style="display:${(a.ebay_app_id && a.has_ebay_cert)?'':'none'}"><td class="k">eBay App ID <span class="cc">(client ID)</span></td><td class="v"><input class="ed" id="ac_ebay_app" value="${esc(a.ebay_app_id||'')}" placeholder="this account's own eBay App ID"></td></tr>
      <tr id="ac_ebay_row_cert" style="display:${(a.ebay_app_id && a.has_ebay_cert)?'':'none'}"><td class="k">eBay Cert ID <span class="cc">(secret)</span></td><td class="v"><input class="ed" id="ac_ebay_cert" type="password" placeholder="${a.has_ebay_cert?'•••••• (leave blank to keep)':"this account's own eBay Cert ID"}"><div class="cc" style="font-size:11px;margin-top:3px">Both boxes must be filled, or the app falls back to the global keys rather than send a half-filled pair.</div></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-plug"></i> Workspace features</div><div class="cc" style="font-size:11.5px">Turn on extra capabilities for this account. Enabling a feature reveals its section inside the workspace; uploads there build listings for THIS account (its sheet, its credentials).</div></td></tr>
      <tr><td class="k">Supplier harvest</td><td class="v">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
          <input type="checkbox" id="ac_feat_harvest" ${(a.features||[]).includes('harvest')?'checked':''} style="width:16px;height:16px">
          Enable supplier-site harvesting (scrape product pages + PDFs, e.g. Miles Lubricants)
        </label></td></tr>
      <tr><td class="k">Auto main image</td><td class="v">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
          <input type="checkbox" id="ac_feat_imgtpl" ${(a.features||[]).includes('image_template')?'checked':''} style="width:16px;height:16px">
          Generate a templated main image for each listing in this workspace
        </label></td></tr>
    </table>
    <input type="hidden" id="ac_id" value="${esc(a.id||'')}">
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="primary" onclick="saveAccount()">Save account</button>
      ${id?`<button onclick="detectFromEditor('${esc(id)}')"><i class="ti ti-radar"></i> Detect marketplaces</button>`:''}
      ${id?`<button onclick="detectBrandsFromEditor('${esc(id)}')"><i class="ti ti-tags"></i> Detect brands</button>`:''}
      ${id?`<button class="del" onclick="deleteAccount('${esc(id)}')">Delete</button>`:''}
      <button onclick="closeAccountEditor()">Cancel</button>
    </div>
    ${typeof howWorks==="function"?(howWorks('acct_connect')+howWorks('acct_marketplaces')+howWorks('acct_brands')):""}
    <div id="ac_detectout" class="cc" style="margin-top:8px"></div>
    <p class="cc" style="margin-top:10px">Secrets are stored only in your local config.json. Leave secret/refresh blank when editing to keep the existing values. Marketplaces are auto-detected (next step) once credentials are valid.</p>`;
  // populate the service-account email for the Drive folder share hint
  (async function(){
    try{
      const ds=await (await fetch("/drive/status")).json();
      const el=document.getElementById("ac_drive_share");
      if(el && ds && ds.ok && ds.service_account_email){
        el.innerHTML='Generated images upload here into per-product <code>SKU_ProductName</code> subfolders. '
          +'<b>Share this folder (Editor) with:</b><br><code style="user-select:all;background:#11203a;padding:2px 6px;border-radius:4px;display:inline-block;margin-top:3px">'
          +esc(ds.service_account_email)+'</code><br>or uploads will be denied.';
      }
    }catch(e){}
  })();
}
function closeAccountEditor(){ document.getElementById("acctmodal").classList.remove("open"); }
// Parse a full Google Sheets URL into {id, gid}. Accepts a bare ID too.
function parseSheetUrl(u){
  u=(u||"").trim();
  if(!u) return {id:"", gid:""};
  let id="", gid="";
  let m=u.match(/\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/);
  if(m){ id=m[1]; }
  else if(/^[a-zA-Z0-9_-]{20,}$/.test(u)){ id=u; }   // looks like a bare ID
  let g=u.match(/[#&?]gid=([0-9]+)/);
  if(g){ gid=g[1]; }
  return {id:id, gid:gid};
}
function _showParsed(boxId, url){
  const p=parseSheetUrl(url); const el=document.getElementById(boxId);
  if(!el) return;
  if(!url.trim()){ el.innerHTML=""; return; }
  if(p.id){ el.innerHTML='<span style="color:#7fd99a">✓ sheet '+esc(p.id.slice(0,10))+'…'+(p.gid?(' · tab gid '+esc(p.gid)):' · first tab')+'</span>'; }
  else { el.innerHTML='<span style="color:#e0696b">✗ couldn\u2019t read a sheet ID from that link</span>'; }
}
// Show/hide the per-account eBay boxes. Ticked = use the app-wide eBay keys, which
// is what the backend already does whenever an account has no eBay App ID of its own
// (dashboard.py _ebay_creds). This only makes that visible; it changes no logic.
function _toggleEbayGlobal(useGlobal){
  ["ac_ebay_row_app","ac_ebay_row_cert"].forEach(id=>{
    const el=document.getElementById(id);
    if(el) el.style.display = useGlobal ? "none" : "";
  });
}

async function saveAccount(){
  const inUrl=(document.getElementById("ac_input_url")||{}).value||"";
  const outUrl=(document.getElementById("ac_output_url")||{}).value||"";
  // Ticked "use global" -> clear this account's eBay App ID. _ebay_creds() needs BOTH
  // halves to use a per-account pair, so blanking the App ID is enough to fall back
  // to the global keys (and we never have to touch the stored secret).
  const ebayGlobal = !!(document.getElementById("ac_ebay_global")||{}).checked;
  const inP=parseSheetUrl(inUrl), outP=parseSheetUrl(outUrl);
  const body={
    id:(document.getElementById("ac_id")||{}).value||"",
    label:(document.getElementById("ac_label")||{}).value||"",
    seller_id:(document.getElementById("ac_seller")||{}).value||"",
    lwa_client_id:(document.getElementById("ac_clientid")||{}).value||"",
    lwa_client_secret:(document.getElementById("ac_secret")||{}).value||"",
    refresh_token:(document.getElementById("ac_refresh")||{}).value||"",
    // store the raw URLs (so the field shows them again) AND the parsed pieces
    input_sheet_url:inUrl, output_sheet_url:outUrl,
    drive_folder_url:((document.getElementById("ac_drive_url")||{}).value||"").trim(),
    uk_responsible_person:{
      name:((document.getElementById("ac_rp_name")||{}).value||"").trim(),
      address:((document.getElementById("ac_rp_address")||{}).value||"").trim(),
      email:((document.getElementById("ac_rp_email")||{}).value||"").trim(),
      phone:((document.getElementById("ac_rp_phone")||{}).value||"").trim()
    },
    input_spreadsheet_id:inP.id, input_tab_gid:inP.gid,
    output_spreadsheet_id:outP.id, output_tab_gid:outP.gid,
    // per-account eBay override (blank = fall back to the global eBay creds)
    ebay_app_id: ebayGlobal ? "" : ((document.getElementById("ac_ebay_app")||{}).value||"").trim(),
    ebay_cert_id: ebayGlobal ? "" : ((document.getElementById("ac_ebay_cert")||{}).value||"").trim(),
    default_marketplace:(document.getElementById("ac_marketplace")||{}).value||"UK",
    brands:((document.getElementById("ac_brands")||{}).value||"").split(",").map(s=>s.trim()).filter(Boolean),
    features:[
      ...(((document.getElementById("ac_feat_harvest")||{}).checked)?["harvest"]:[]),
      ...(((document.getElementById("ac_feat_imgtpl")||{}).checked)?["image_template"]:[])
    ]
  };
  if(!body.label){ toast("Account name required"); return; }
  if(outUrl.trim() && !outP.id){ toast("Output sheet link looks wrong — couldn't read a sheet ID"); return; }
  try{
    const j=await (await fetch("/accounts/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
    if(j.ok){ toast("Account saved"); closeAccountEditor(); loadHome(); }
    else toast("Save failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
async function deleteAccount(id){
  if(!confirm("Delete this account from the app? (Your Amazon account is unaffected; this only removes it from the tool.)")) return;
  try{ await fetch("/accounts/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})});
    toast("Account removed"); closeAccountEditor(); loadHome(); }
  catch(e){ toast("Error: "+e); }
}
async function detectFromEditor(id){
  var out=document.getElementById("ac_detectout");
  if(out) out.innerHTML='<span class="genspin"></span> Calling Amazon (getMarketplaceParticipations)…';
  try{
    var j=await (await fetch("/accounts/detect_marketplaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})})).json();
    if(j.ok){ if(out) out.innerHTML='<span style="color:#7fd99a">\u2713 Detected: '+(j.marketplaces||[]).join(", ")+'</span>'; loadHome(); }
    else { if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(String(e))+'</span>'; }
}
async function detectBrandsFromEditor(id){
  var out=document.getElementById("ac_detectout");
  if(out) out.innerHTML='<span class="genspin"></span> Reading brands from your live listings…';
  try{
    var j=await (await fetch("/accounts/detect_brands",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})})).json();
    if(j.ok){
      // reflect into the brands field
      var bf=document.getElementById("ac_brands"); if(bf) bf.value=(j.brands||[]).join(", ");
      if(out) out.innerHTML='<span style="color:#7fd99a">\u2713 Brands ('+esc(j.source||"")+'): '+esc((j.brands||[]).join(", ")||"none found")+'</span>'
        +'<div class="cc" style="margin-top:4px">'+esc(j.note||"")+'</div>';
      loadHome();
    } else { if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(out) out.innerHTML='<span style="color:#e0696b">\u2717 '+esc(String(e))+'</span>'; }
}
function buildMktSwitch(g){
  const host=document.getElementById("mktswitch"); if(!host) return;
  if(!g || g.members.length<2 && !g.isDrop){
    // single-marketplace brand: show its marketplace as a static label (or nothing)
    const m=g&&g.members[0]?_mktOf(g.members[0]):"";
    host.innerHTML = m? `<span class="mktlabel">${esc(m)}</span>`:"";
    return;
  }
  host.innerHTML = g.members.map(v=>{
    const m=_mktOf(v)||v.label;
    const on = ACTIVE_WS && ACTIVE_WS.key===v.key;
    return `<button class="mktbtn ${on?'on':''}" onclick='switchMarket(${JSON.stringify(v.key)})'>${esc(m)}</button>`;
  }).join("");
}
async function switchMarket(key){
  await enterWorkspace(key);
  if(CUR_GROUP) buildMktSwitch(CUR_GROUP);
}

let PRIVACY_ON = false;
function togglePrivacy(){
  PRIVACY_ON = !PRIVACY_ON;
  document.body.classList.toggle("privacy-on", PRIVACY_ON);
  const btn=document.getElementById("privbtn");
  if(btn){
    btn.classList.toggle("privon", PRIVACY_ON);
    btn.innerHTML = PRIVACY_ON
      ? '<i class="ti ti-eye-off"></i> Privacy ON'
      : '<i class="ti ti-eye-off"></i> Privacy';
  }
  // When turning privacy back OFF, clear any per-card reveals so next time
  // privacy is enabled everything starts blurred again.
  if(!PRIVACY_ON){
    document.querySelectorAll(".unblurred").forEach(el=>el.classList.remove("unblurred"));
  }
  try{ localStorage.setItem("priv_on", PRIVACY_ON?"1":"0"); }catch(e){}
}
// Reveal (or re-hide) a single tile/card. The eye button lives inside the
// tile image or card; walk up to the nearest .tile or .wscard and toggle.
function peekTile(btn){
  const host = btn.closest(".tile, .wscard");
  if(!host) return;
  const now = host.classList.toggle("unblurred");
  const ic = btn.querySelector("i");
  if(ic) ic.className = now ? "ti ti-eye-off" : "ti ti-eye";
  btn.title = now ? "Hide again" : "Reveal this listing";
}
function goHome(){
  ACTIVE_WS=null;
  document.getElementById("workspace").classList.remove("show");
  document.getElementById("home").classList.add("show");
  document.getElementById("crumbs").innerHTML="";
  loadHome();
}

async function enterWorkspace(key){
  const v=VIEWS.find(x=>String(x.key)===String(key)) || {key:key,label:key};
  ACTIVE_WS=v;
  // switch the backend view so all existing routes read this workspace's sheet
  try{ await fetch("/view/set",{method:"POST",headers:{"Content-Type":"application/json"},
       body:JSON.stringify({key:v.key, sheet:v.sheet||"", tab:v.tab||""})}); }catch(e){}
  // paint shell
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  const col=_wsColor(v), isDrop=!v.brand;
  const icEl=document.getElementById("ws_ic");
  icEl.style.background=col.bg; icEl.style.color=col.fg;
  icEl.innerHTML = isDrop ? '<i class="ti ti-shopping-cart"></i>' : _initials(v.brand||v.label);
  document.getElementById("ws_nm").textContent=v.label||v.brand||"Dropshipping";
  document.getElementById("ws_sub").textContent=v.marketplace||"";
  document.getElementById("ws_title").textContent=(v.label||"Listings");
  document.getElementById("crumbs").innerHTML=
    `<span class="sep">/</span><span class="here">${esc(v.label||v.brand||"Dropshipping")}</span>`;
  // brand-only sections
  document.getElementById("nav_setup").style.display = isDrop ? "none" : "flex";
  window.WS_BRAND = isDrop ? "" : (v.brand||"");
  // currency + marketplace for this workspace
  WS_MARKET = _mktOf(v) || (isDrop ? "" : "");
  CUR_SYMBOL = (WS_MARKET==="US") ? "$" : "\u00a3";
  SELECTED.clear(); updateSelBar();
  document.getElementById("gen_scope").textContent =
    (v.label? "\u201c"+v.label+"\u201d" : "this workspace\u2019s");
  navTo("listings");
  loadRows();
  loadViews();   // keep legacy view <select> in sync if present
}

function navTo(sec){
  CUR_SEC=sec;
  document.querySelectorAll(".navitem").forEach(n=>n.classList.toggle("active", n.dataset.sec===sec));
  // listings uses #sec_listings (always block); others are .wspanel
  document.getElementById("sec_listings").style.display = (sec==="listings")?"block":"none";
  ["imagerefs","setup","generate","miles","ppc","inventory"].forEach(s=>{
    const el=document.getElementById("sec_"+s);
    if(el) el.classList.toggle("show", s===sec);
  });
  if(sec==="setup")     loadBrandPanel();
  if(sec==="imagerefs") loadImageRefs();
  if(sec==="generate"){ loadTargetAccount(); loadInputSheet(); }
  if(sec==="miles"){    milesLoadResults(); milesLoadPref(); }
  if(sec==="ppc")       ppcOnOpen();
}
async function loadTargetAccount(){
  var el=document.getElementById("targetacct"); if(!el) return;
  el.className="acctbanner"; el.textContent="Resolving destination account…";
  try{
    var t=await (await fetch('/submit/target')).json();
    if(t&&t.ok){
      if(t.block==='none'){ el.className="acctbanner bad"; el.innerHTML='\u26a0 '+esc(t.marketplace)+' marketplace selected, but NO credentials configured \u2014 submit will do nothing.'; }
      else { el.className="acctbanner ok"; el.innerHTML='<i class="ti ti-shield-check"></i> Submits here publish to: <b>'+esc(t.account_label)+'</b>'+(t.seller_id?' <span class="cc">('+esc(t.seller_id)+')</span>':'')+' \u2014 marketplace <b>'+esc(t.marketplace)+'</b>'; }
    } else { el.className="acctbanner bad"; el.textContent="Could not resolve destination account."; }
  }catch(e){ el.className="acctbanner bad"; el.textContent="Could not resolve destination account."; }
}

async function loadInputSheet(){
  var body=document.getElementById("inputsheet_body"); if(!body) return;
  var meta=document.getElementById("inputsheet_meta");
  body.innerHTML='<div class="cc" style="padding:16px;opacity:.7"><span class="genspin"></span> Loading input sheet\u2026</div>';
  if(meta) meta.textContent="";
  try{
    var j=await (await fetch('/input_sheet')).json();
    if(!j.ok){ body.innerHTML='<div class="cc" style="padding:16px;color:#e3b768">'+esc(j.error||'could not load')+'</div>'; return; }
    var openA=document.getElementById("inputsheet_open");
    if(openA && j.view_url){ openA.href=j.view_url; openA.style.display="inline-flex"; }
    if(meta) meta.textContent='\u201c'+(j.title||'')+'\u201d \u00b7 '+j.row_count+' rows \u00d7 '+j.col_count+' cols';
    var H=j.headers||[], R=j.rows||[];
    if(!H.length && !R.length){ body.innerHTML='<div class="cc" style="padding:16px;opacity:.6">This sheet is empty.</div>'; return; }
    var html='<table class="ishtable"><thead><tr><th class="isgut">#</th>';
    H.forEach(function(h){ html+='<th>'+esc(h||'')+'</th>'; });
    html+='</tr></thead><tbody id="ishbody">';
    R.forEach(function(row,ri){
      html+='<tr><td class="isgut">'+(ri+2)+'</td>';
      for(var c=0;c<H.length;c++){ html+='<td>'+esc(row[c]!=null?row[c]:'')+'</td>'; }
      html+='</tr>';
    });
    html+='</tbody></table>';
    body.innerHTML=html;
  }catch(e){ body.innerHTML='<div class="cc" style="padding:16px;color:#e0696b">Error: '+esc(String(e))+'</div>'; }
}
function filterInputSheet(){
  var q=((document.getElementById("inputsheet_filter")||{}).value||"").toLowerCase().trim();
  var body=document.getElementById("ishbody"); if(!body) return;
  Array.prototype.forEach.call(body.querySelectorAll("tr"), function(tr){
    if(!q){ tr.style.display=""; return; }
    tr.style.display = (tr.textContent.toLowerCase().indexOf(q)>=0) ? "" : "none";
  });
}

function navToBrandCreate(){
  // open a blank brand setup so the user can create a new brand profile
  enterWorkspaceBlank();
}
function enterWorkspaceBlank(){
  ACTIVE_WS={key:"",label:"New brand",brand:"new"};
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  document.getElementById("ws_nm").textContent="New brand";
  document.getElementById("ws_sub").textContent="";
  document.getElementById("nav_setup").style.display="flex";
  document.getElementById("crumbs").innerHTML='<span class="sep">/</span><span class="here">New brand</span>';
  navTo("setup");
}

