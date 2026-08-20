// ---- where listings actually live -----------------------------------------
// The app moved to a local database; the input sheet is imported on demand and
// is no longer the store. Every screen that still said "the sheet" was sending
// people to a spreadsheet to fix something that is not in it any more.
//
// ONE helper, so the wording cannot be right on one screen and wrong on the
// next. window.DATA_BACKEND is what /users/me reports the app is ACTUALLY using,
// not what the config asks for, so this follows reality rather than intent.
function storeName(){
  return (window.DATA_BACKEND === "db") ? "this app" : "your sheet";
}
function storeNameCap(){
  return (window.DATA_BACKEND === "db") ? "This app" : "Your sheet";
}
// "…from the sheet" / "…from this app" — the phrase most of the buttons need.
function storeFrom(){
  return (window.DATA_BACKEND === "db") ? "from this app" : "from your sheet";
}

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

  // WHERE THE DATA ACTUALLY IS.
  //
  // This header advertised the Output SHEET as the data source. On the database
  // nothing is written there at all -- generated listings go into the app's own
  // store -- so the one line whose whole job is to say where your data lives was
  // pointing at a spreadsheet that had not been touched in weeks. It is the
  // single most misleading thing on the screen, and it is why the app still
  // looks like it runs on Sheets.
  //
  // On the database: name the database, and keep the INPUT sheet only as what it
  // now is -- an optional place to import products from.
  // ON THE DATABASE, THERE IS NOTHING TO SAY HERE.
  //
  // This still printed "Data source · This app's database · Import from:
  // 1XcH6Ldb…HBvM · gid 0 · optional". Every part of that is either obvious or
  // about a spreadsheet: naming the database as the data source is telling
  // someone their app stores its data in itself, and the rest advertises a
  // sheet id and a gid across the top of the listings screen for a feature that
  // is one button inside the queue.
  //
  // Reported as: "i still see the import from and tab sections in the app in
  // the header, if we are not using sheets make sure to delete them from there".
  // Importing from a sheet still WORKS -- it is "Import from sheet" in the input
  // queue, where the import is -- it just stops being a permanent caption.
  if(window.DATA_BACKEND === "db"){
    el.innerHTML = "";
    return;
  }

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
  if(!v || !v.brand) return {bg:"var(--accent-bg)", fg:"var(--accent2)"};
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

// A saved sheet VIEW with no brand on it. These are the old Google Sheets
// views, which are a different thing from the workspace card that has been
// removed -- but they used the same word, and the word is what made the
// arbitrage model look like part of the product. Grouped and labelled by what
// they actually are now: a sheet nobody has named.
function _baseName(v){
  if(!v.brand) return "__unnamed__";
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
  return Object.values(groups).map(g=>{ g.label=g.isDrop?"Unnamed sheet":g.base; return g; });
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
      +'<div style="color:var(--red);font-weight:600;margin-bottom:8px">⚠ Your config.json has an error</div>'
      +'<div class="cc" style="white-space:pre-wrap">'+esc(acctData.error||"")+'</div>'
      +'<div class="cc" style="margin-top:10px">Fix the file, save it, then click Home to retry.</div></div>';
    // Nothing can be reopened, so let the error be SEEN rather than sit behind
    // the routing veil until its timeout.
    _altaBootDone();
    return;
  }
  if(acctData && acctData._failed){
    grid.innerHTML='<div class="empty" style="grid-column:1/-1;text-align:left">'
      +'<div style="color:var(--red);font-weight:600;margin-bottom:8px">⚠ Could not load accounts</div>'
      +'<div class="cc">'+esc(acctData.error||"")+'</div>'
      +'<div class="cc" style="margin-top:8px">Try clicking Home again. If this persists, check the terminal where the app runs for an error.</div></div>';
    _altaBootDone();
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
  // THE DROPSHIPPING CARD IS GONE. It described itself as "eBay → Amazon
  // arbitrage", which is the one thing CLAUDE.md rule 1 says this app does not
  // do: it creates NEW listings under the owner's own brands, and the
  // competitor ASIN is a reference for product data and nothing else. A
  // workspace whose own subtitle contradicts the first rule in the file is a
  // place for work to go wrong, so it is no longer reachable from anywhere.
  //
  // Its 13 orphaned listing rows (workspace ids dropship_uk / dropship_us,
  // which were not in config.json and so could never be opened) were written to
  // _deleted_dropship_rows.json and removed.
  // each Amazon ACCOUNT is a workspace
  cards += ACCOUNTS.map(a=>{
    const col=_wsColorKey(a.id||a.label);
    const connected=a.has_creds;
    // MARKETPLACES AS FLAGS YOU CAN CLICK.
    //
    // This card is the only thing the home screen does -- it chooses an
    // account. Orbit chooses an account AND a marketplace, with the country
    // shown as a flag, and that is the better shape: nearly every one of these
    // accounts sells in more than one country, and picking the account only to
    // then hunt for the marketplace switcher is a step that need not exist.
    //
    // Clicking a flag opens the account already on that marketplace. Clicking
    // anywhere else on the card opens it on the account's own default, exactly
    // as before.
    const mktList = (a.marketplaces && a.marketplaces.length) ? a.marketplaces : [];
    const dfltM = a.default_marketplace || "";
    const mkts = mktList.length
      ? mktList.map(function(m){
          const on = (m === dfltM);
          return '<button class="mktflag' + (on ? " on" : "") + '" '
               + 'title="Open ' + esc(a.label) + ' on ' + esc(mktName(m))
               + (on ? " (its default)" : "") + '" '
               + "onclick='event.stopPropagation();enterAccountAt("
               + JSON.stringify(a.id) + "," + JSON.stringify(m) + ")'>"
               + mktFlag(m) + ' <span>' + esc(mktShort(m)) + '</span></button>';
        }).join("")
      : (connected ? '<span class="cc">marketplaces not detected</span>'
                   : '<span class="cc">draft-only · not connected</span>');
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
  // First paint only: now that ACCOUNTS and VIEWS are known, honour the address
  // the user actually arrived on. Deliberately at the END of loadHome -- opening
  // a workspace before we know which ones exist can only guess. The early error
  // returns above skip this, which is correct: if accounts could not be loaded
  // we cannot reopen anything, and the error on screen is the honest answer.
  if(!_ALTA_ROUTED){ _ALTA_ROUTED = true; altaRouteFromUrl(); }
}
// The two functions that opened and saved the Dropshipping default sheets were
// here. They edited the sheets that workspace read from, and it no longer
// exists -- see the note further down where the function that opened it used to
// be. Every account sets its own sheets from its own card, which is where this
// belonged anyway.

// ---- importing the input sheet ------------------------------------------
// The input sheet USED to be read live, every run. It is now imported: press
// this, the rows land in the app, and nothing reads Google again until you press
// it again. The sheet is unchanged -- it just stops being a dependency.
//
// ONE block, rendered by both sheet editors (the account one and the
// Dropshipping one). Two copies of a button that imports your product queue
// would be two places to fix when the wording or the endpoint changes.
function _importInputRow(){
  return `<tr><td class="k">Products in the app</td><td class="v">
      <button class="db-chip" id="in_importbtn" onclick="importInputSheet()">
        <i class="ti ti-download"></i> Import from this sheet</button>
      <span id="in_importstatus" class="cc" style="font-size:11px;margin-left:8px">…</span>
      <div class="cc" style="font-size:11px;margin-top:4px">
        Copies the rows above into the app. Nothing is read from Google again
        until you press this. Importing never deletes — rows removed from the
        sheet stay here until you clear them.</div></td></tr>`;
}

async function refreshInputStatus(){
  const el=document.getElementById("in_importstatus");
  if(!el) return;
  try{
    const j=await (await fetch("/input/status")).json();
    if(!j || !j.ok){ el.textContent=""; return; }
    // Always say WHEN. A count with no date on it is indistinguishable from a
    // fresh one, which is how you end up generating last month's list.
    el.textContent = j.count
      ? (j.count+" product"+(j.count===1?"":"s")+" imported"
         + (j.imported_at ? (" · "+j.imported_at) : ""))
      : "nothing imported yet";
  }catch(e){ el.textContent=""; }
}

async function importInputSheet(){
  const btn=document.getElementById("in_importbtn");
  const el=document.getElementById("in_importstatus");
  if(btn) btn.disabled=true;
  if(el) el.innerHTML='<span class="genspin"></span> reading the sheet…';
  try{
    const j=await (await fetch("/input/import",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:"{}"})).json();
    if(!j || !j.ok){
      if(el) el.innerHTML='<span style="color:var(--red)">'+esc((j&&j.error)||"failed")+'</span>';
      return;
    }
    // Say what changed, not just that something did: "read 40" with "added 0,
    // updated 40" is a re-import, and that is worth being able to tell.
    toast("Imported "+j.read+" row"+(j.read===1?"":"s")+" — "
          +j.added+" new, "+j.updated+" updated");
    refreshInputStatus();
  }catch(e){
    if(el) el.innerHTML='<span style="color:var(--red)">'+esc(String(e))+'</span>';
  }finally{ if(btn) btn.disabled=false; }
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
/* Show the percentage box only when the company actually charges VAT. The tick
 * and the box are two controls over ONE stored number: unticked is 0, ticked is
 * whatever is typed. A second stored "is registered" flag could contradict the
 * rate, so there isn't one. */
function _toggleVat(on){
  const w = document.getElementById("ac_vat_wrap");
  if(w) w.style.display = on ? "" : "none";
  if(on){
    const f = document.getElementById("ac_vat_pct");
    // Default to the standard UK rate rather than 0 -- ticking the box and
    // leaving a zero in it would silently mean "registered, but charges
    // nothing", which is not what ticking it says.
    if(f && !(parseFloat(f.value) > 0)) f.value = 20;
  }
}

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
  LIVE_ITEMS=[]; APLUS_BY_ASIN={}; AMZ_STATE={};   // never carry one account's data into another
  // AND THE DRAFTS. These were left behind when only the live-side caches were
  // cleared, so opening Jack Reacherd painted Green Haven's listings and held
  // them on screen for the whole of the new fetch -- up to a minute on a
  // multi-tab account. Reported as "it shows me listings from other accounts
  // for some seconds and then loads back".
  //
  // An empty grid for a moment is the correct thing to show: this account's
  // listings are not known yet, and the previous account's are not an
  // approximation of them.
  ROWS=[]; if(typeof TABS!=="undefined") TABS=[];
  if(typeof DUP_INDEX!=="undefined" && DUP_INDEX && DUP_INDEX.clear) DUP_INDEX.clear();
  var _g=document.getElementById("grid"); if(_g) _g.innerHTML="";
  var _sm=document.getElementById("summary"); if(_sm) _sm.innerHTML="";
  // EVERY OTHER SCREEN TOO -- Sales, Finance, Orders, Returns and the rest all
  // keep their rendered contents in their panels. Those panels are hidden, not
  // emptied, so without this the new account's Sales screen would open showing
  // the last account's figures until its own load finished.
  if(typeof screenForgetAll === "function") screenForgetAll();
  // The counting numbers remember what they last showed, so they animate only a
  // real change. Every one of those figures is about to describe something
  // else, so that memory goes with the rest.
  if(typeof altaCountReset === "function") altaCountReset();
  // Open on DRAFTS only -- loading the workspace must be fully local. A live Amazon
  // read (the Reports API call in /live/catalog) is slow and must never fire just from
  // opening the page; the user triggers it explicitly by clicking the Live/All source
  // button or Sync/Pull. (Previously defaulted to 'all' for connected accounts, which
  // auto-fired loadLiveCatalog on every workspace open.)
  LIST_SOURCE = 'drafts';
  // default marketplace: account's configured default, else first detected
  const dflt = a.default_marketplace && (a.marketplaces||[]).indexOf(a.default_marketplace)>=0 ? a.default_marketplace : null;
  WS_MARKET = dflt || ((a.marketplaces && a.marketplaces.length) ? a.marketplaces[0] : "");
  CUR_SYMBOL = mktSymbol(WS_MARKET) || "\u00a3";   // one table: static/js/marketplaces.js
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
  // Picking an account from the panel closes it. This used to hide a full-screen
  // home page; that element is gone, and calling .classList on the null it left
  // behind would have thrown here -- on the one path every account switch takes.
  closeAccounts();
  document.getElementById("workspace").classList.add("show");
  const col=_wsColorKey(a.id||a.label);
  const icEl=document.getElementById("ws_ic");
  icEl.style.background=col.bg; icEl.style.color=col.fg; icEl.innerHTML=_initials(a.label);
  document.getElementById("ws_nm").textContent=a.label;
  if(window.WS_READONLY){
    const _lender=(ACCOUNTS||[]).find(x=>x.id===window.WS_CREDS_SOURCE);
    document.getElementById("ws_sub").innerHTML =
      '<span style="color:var(--warn);font-weight:600"><i class="ti ti-lock"></i> Read-only</span>'
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
  // Bookmarks are per account: reload them rather than repaint the last
  // account\u2019s pins.
  if(typeof bmkRefresh==="function") bmkRefresh();
  // marketplace switcher from the account's (detected) marketplaces
  buildAccountMktSwitch(a);
  // The two sidebar rows say what is open. Updated here, where the account
  // actually changes, so they cannot disagree with the screen.
  if(typeof renderSwitchRows === "function") renderSwitchRows();
  // Remembered so the next visit opens here instead of a grid of cards.
  try{ localStorage.setItem("alta_last_account", String(a.id || "")); }catch(e){}
  navTo("listings");
  altaSyncUrl();
  // Start the background refresh as soon as a CONNECTED workspace is open, not
  // only once someone has visited the Live tab. That is what makes switching to
  // "Live on Amazon" find data already waiting instead of starting a wait --
  // previously the timer was only armed by a successful live load, so the very
  // first visit always paid the full report-build time.
  if(hasCreds && !window.WS_READONLY && typeof startAutoSync === "function"){
    try{ startAutoSync(); }catch(e){}
  }
  // THE DRAFTS VIEW NEEDS AMAZON'S CATALOGUE TOO -- see the note below.
  loadRows(); loadLiveCatalog(false);
}

/* WHY EVERY VIEW LOADS THE LIVE CATALOGUE NOW, not just Live and All.
 *
 *     "when i go to live on amazon section i see the asin B0HCVFW53Y and
 *      B0HCVTDFNW as live and when i go to drafts it showed me the both as
 *      drafts; ready to send. but when i refreshed the asin the ready to send
 *      section was zero"
 *
 * One listing, two answers, and the app was sure of both.
 *
 * MEASURED: on the Drafts view, LIVE_ITEMS was 0 and _liveCatalogLoaded() was
 * false -- the catalogue was never fetched there. isPublishedRow() decides
 * whether a row is a draft or something Amazon has already published, and with
 * no catalogue to consult it can only fall back to the row's stored status
 * word. A listing Amazon published, whose stored word still says APPROVED,
 * therefore stayed in "ready to send" indefinitely.
 *
 * Visiting "Live on Amazon" loads the catalogue (47 items, measured), and
 * coming back to Drafts then hides the same row and drops the count -- which is
 * exactly the "refreshed and it was zero" half of the report. The number was
 * never really changing; the view was simply the only place that had asked.
 *
 * force=false, so this costs NO Amazon call: it is served from the durable
 * snapshot, and when nothing is saved yet the route returns immediately and
 * lets the background refresh fill it in. The status word is left alone -- only
 * Sync writes it -- because Amazon's catalogue is the authority here and the
 * screen should read it rather than a copy of it that has gone stale. */
/* Open an account already on a chosen marketplace.
 *
 * enterAccount picks the account's own default; this picks the one that was
 * clicked. Done by setting WS_MARKET after the account is open rather than
 * before, because enterAccount RESETS it to the default -- setting it first
 * would be silently overwritten, which is the kind of thing that looks like
 * "the flag button does nothing". */
async function enterAccountAt(accountId, marketplace){
  await enterAccount(accountId);
  const m = String(marketplace || "");
  if(!m || m === WS_MARKET) return;
  await switchAccountMarket(m);
}

// The function that opened the Dropshipping workspace was here, and has been
// removed with the workspace itself.
// It set the header to "Dropshipping / eBay -> Amazon", cleared the
// account, and pointed the app at the config default sheet -- the app's
// original no-account mode, from before per-account workspaces existed.
//
// CLAUDE.md rule 1 says this app creates NEW listings under the owner's own
// brands and uses a competitor ASIN only to gather product data. A workspace
// subtitled "eBay -> Amazon arbitrage" is the business model the rule exists
// to rule out, so it is gone rather than renamed.

// WHICH MARKETPLACE IS OPEN, AND WHAT IT SPENDS.
//
// This used to draw the marketplace strip in the toolbar AS WELL as settle the
// state behind it. The strip is gone -- the sidebar row is the one control now
// -- but the state is not: WS_MARKET has to be valid for the account being
// opened, and CUR_SYMBOL follows from it. Deleting this along with the markup
// would have left every price on screen in the previous account's currency.
//
// The three things the strip drew are all still reachable: draft-only is on the
// account pill and in the account switcher, and detect / set-as-default moved
// into the sidebar's marketplace menu.
function buildAccountMktSwitch(a){
  if(!a || !a.has_creds) return;
  const mkts=a.marketplaces&&a.marketplaces.length?a.marketplaces:[];
  if(!mkts.length) return;
  // keep the current selection if it's valid for this account; else default to first
  if(!WS_MARKET || (WS_MARKET!=="__all__" && mkts.indexOf(WS_MARKET)<0)){ WS_MARKET=mkts[0]; }
  if(WS_MARKET!=="__all__"){
    // One table of what a marketplace code means, in static/js/marketplaces.js.
    // This was an inline ternary here AND another in switchAccountMarket, and
    // the two had already drifted apart on which countries use the euro.
    CUR_SYMBOL = mktSymbol(WS_MARKET) || "\u00a3";
  }
  // The sidebar row shows which marketplace is live, so it is repainted
  // whenever this settles on a different one than was showing.
  if(typeof renderSwitchRows === "function") renderSwitchRows();
}
async function detectMarketplaces(accountId){
  // Detection takes a few seconds and used to show a spinner in the toolbar
  // strip. With the strip gone this is started from a menu that closes on the
  // click, so the only place left to say anything is a toast.
  toast("Asking Amazon which marketplaces this account sells in…");
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
  CUR_SYMBOL = mktSymbol(m) || "\u00a3";   // one table, in static/js/marketplaces.js
  // A marketplace is as different as an account: UK sales are not US sales.
  // Remembered screens are keyed by both, so they will reload -- but what is
  // already painted has to go, or the UK figures sit under the US heading until
  // the reload lands.
  if(typeof screenForgetAll === "function") screenForgetAll();
  // The counting numbers remember what they last showed, so they animate only a
  // real change. Every one of those figures is about to describe something
  // else, so that memory goes with the rest.
  if(typeof altaCountReset === "function") altaCountReset();
  try{ await fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"",marketplace:m})}); }catch(e){}
  if(CUR_ACCOUNT) buildAccountMktSwitch(CUR_ACCOUNT);
  if(typeof renderSwitchRows === "function") renderSwitchRows();
  // Both, on every view: changing marketplace changes which listings Amazon has
  // live, and the Drafts view reads that to tell a draft from something already
  // published. See the note above enterAccount's loader.
  loadRows(); loadLiveCatalog(false);
}

function openCurrentAccountSettings(){
  // Resolve the account currently in focus. CUR_ACCOUNT is set by enterAccount;
  // it's intentionally null in the built-in Dropshipping workspace.
  if(CUR_ACCOUNT && CUR_ACCOUNT.id){ openAccountEditor(CUR_ACCOUNT.id); return; }
  // Dropshipping (or no account selected): try the server's active account id.
  if(ACTIVE_WS && ACTIVE_WS.account && ACTIVE_WS.key){ openAccountEditor(ACTIVE_WS.key); return; }
  // Built-in Dropshipping workspace has no account object — explain + send to Home.
  if(ACTIVE_WS && !ACTIVE_WS.account){
    toast("No account is open, so this uses the app default sheet. Open an account to set its own sheet links.");
    return;
  }
  toast("Open an account from All workspaces first, then click Account & sheets.");
}
function openAccountEditor(id){
  const a = id ? (ACCOUNTS.find(x=>x.id===id)||{}) : {};
  // Which store the app is ACTUALLY on, not what the config asks for -- the
  // sheet fields below describe two different jobs depending on the answer.
  const onDb = (window.DATA_BACKEND === "db");
  const m=document.getElementById("acctmodal"); m.classList.add("open");
  document.getElementById("acctmodalbody").innerHTML=`
    <table class="kv">
      <tr><td class="k">Account name</td><td class="v"><input class="ed" id="ac_label" value="${esc(a.label||'')}" placeholder="e.g. Jack Reacherd (UK)"></td></tr>
      <tr><td class="k">Seller / merchant ID</td><td class="v"><input class="ed" id="ac_seller" value="${esc(a.seller_id||'')}" placeholder="A1B2C3..."></td></tr>
      <tr><td class="k">LWA client ID</td><td class="v"><input class="ed" id="ac_clientid" value="${esc(a.lwa_client_id||'')}" placeholder="amzn1.application-oa2-client..."></td></tr>
      <tr><td class="k">LWA client secret</td><td class="v"><input class="ed" id="ac_secret" type="password" placeholder="${a.has_secret?'•••••• (leave blank to keep)':'paste secret'}"></td></tr>
      <tr><td class="k">Refresh token</td><td class="v"><input class="ed" id="ac_refresh" type="password" placeholder="${a.has_creds?'•••••• (leave blank to keep)':'paste refresh token'}"></td></tr>
      <tr><td class="k">Primary marketplace</td><td class="v"><select class="ed" id="ac_marketplace"><option value="UK"${(a.default_marketplace||'UK')==='UK'?' selected':''}>UK — amazon.co.uk (GBP)</option><option value="US"${(a.default_marketplace||'')==='US'?' selected':''}>US — amazon.com (USD)</option></select><div class="cc" style="font-size:11px;margin-top:2px">Drives pricing, fees, SP-API and the flat-file route for this account's listings.</div></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-table"></i> Google Sheets for this account ${onDb?'<span class="cc" style="font-weight:400">— optional</span>':''}</div><div class="cc" style="font-size:11.5px">${onDb
          // ON THE DATABASE THESE ARE NOT WHERE ANYTHING LIVES, and the labels
          // said otherwise -- "(generated listings)" against a sheet nothing is
          // written to is why the app still looks like it runs on spreadsheets.
          // Kept, because importing an existing sheet is still useful and
          // switching back must stay possible; relabelled, because a field that
          // describes a job it no longer does is worse than no field.
          ? 'This app stores its listings in its own database, so <b>neither of these is required</b>. Keep an input sheet only if you want to keep pasting rows into a spreadsheet and press <b>Import from sheet</b>; the output sheet is <b>not written to at all</b> while the database is in use.'
          : 'Paste the <b>full Google Sheets link</b> (with the tab open). The app reads the spreadsheet ID and the tab (gid) from the URL — so each account\'s US/UK listings go to the right place.'}</div></td></tr>
      <tr><td class="k">Input sheet URL <span class="cc">${onDb?'(only for Import from sheet)':'(source rows)'}</span></td><td class="v"><input class="ed" id="ac_input_url" value="${esc(a.input_sheet_url||'')}" oninput="_showParsed('ac_input_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ac_input_parsed" class="cc" style="font-size:11px;margin-top:2px"></div>${_savedSheetLine('Currently saved', a.input_sheet_url, a.input_tab_gid)}${onDb?'<div class="cc" style="font-size:11px;margin-top:3px">You can skip this entirely — add products straight into the queue on the <b>Generate</b> screen.</div>':''}</td></tr>
      ${_importInputRow()}
      <tr><td class="k">Output sheet URL <span class="cc">${onDb?'(not in use)':'(generated listings)'}</span></td><td class="v"><input class="ed" id="ac_output_url" value="${esc(a.output_sheet_url||'')}" oninput="_showParsed('ac_output_parsed',this.value)" placeholder="https://docs.google.com/spreadsheets/d/…/edit?gid=…"><div id="ac_output_parsed" class="cc" style="font-size:11px;margin-top:2px"></div>${_savedSheetLine('Currently saved', a.output_sheet_url, a.output_tab_gid)}${onDb?'<div class="cc" style="font-size:11px;margin-top:3px">Generated listings go into this app\'s database, not here. This is kept only so nothing is lost if you switch back to spreadsheets.</div>':''}</td></tr>
      <tr><td class="k">Drive image folder URL <span class="cc">(image storage)</span></td><td class="v"><input class="ed" id="ac_drive_url" value="${esc(a.drive_folder_url||'')}" placeholder="https://drive.google.com/drive/folders/…"><div class="cc" id="ac_drive_share" style="font-size:11px;margin-top:3px">Generated images upload here into per-product <code>SKU_ProductName</code> subfolders. <b>Share this folder (Editor) with the service account</b> shown below, or uploads will be denied.</div></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-shield-check"></i> UK Responsible Person <span class="cc">(only needed for Amazon.co.uk listings)</span></div><div class="cc" style="font-size:11.5px">Selling on Amazon.co.uk from outside the UK legally requires a UK Responsible Person (name + real UK address + contact). Fill this once and every UK listing inherits it. Leave blank for US-only — US listings are unaffected.</div></td></tr>
      <tr><td class="k">RP legal name</td><td class="v"><input class="ed" id="ac_rp_name" value="${esc((a.uk_responsible_person||{}).name||'')}" placeholder="e.g. FLIPX LTD"></td></tr>
      <tr><td class="k">RP UK address</td><td class="v"><input class="ed" id="ac_rp_address" value="${esc((a.uk_responsible_person||{}).address||'')}" placeholder="Real UK address — no PO boxes"></td></tr>
      <tr><td class="k">RP email</td><td class="v"><input class="ed" id="ac_rp_email" value="${esc((a.uk_responsible_person||{}).email||'')}" placeholder="contact@…"></td></tr>
      <tr><td class="k">RP phone</td><td class="v"><input class="ed" id="ac_rp_phone" value="${esc((a.uk_responsible_person||{}).phone||'')}" placeholder="+44…"></td></tr>
      <tr><td class="k">Trademarks / brands <span class="cc">(comma-separated)</span><div class="cc" style="font-weight:400;font-size:11px;line-height:1.45;margin-top:3px">The brands this account may list under. A listing whose Brand is not on this list is sent under the first one instead, and the run says so. This is NOT the same as <b>Brand setup</b>, which holds a brand\u2019s copy voice.</div></td><td class="v"><input class="ed" id="ac_brands" value="${esc((a.brands||[]).join(', '))}" placeholder="Headbanger Lures, Leech Eyewear"></td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-receipt-tax"></i> VAT</div><div class="cc" style="font-size:11.5px">Amazon reports this account's order values with VAT <b>already inside them</b>. If this company is VAT registered, that portion belongs to HMRC and is not your revenue — so profit and margin are worked out after it is taken out. Leave unticked if this company is not registered. Each company is separate, so set it per account.</div></td></tr>
      <tr><td class="k">VAT registered</td><td class="v">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
          <input type="checkbox" id="ac_vat_on" ${(a.vat_percent||0) > 0 ? 'checked' : ''} onchange="_toggleVat(this.checked)">
          <span>This company charges VAT</span>
        </label>
        <div id="ac_vat_wrap" style="margin-top:6px;${(a.vat_percent||0) > 0 ? '' : 'display:none'}">
          <input class="ed" id="ac_vat_pct" type="number" min="0" max="100" step="0.01"
                 style="max-width:120px"
                 value="${a.vat_percent === null || a.vat_percent === undefined ? 20 : esc(String(a.vat_percent))}"> <span class="cc">%</span>
          <div class="cc" style="font-size:11px;margin-top:3px">20% is the standard UK rate. Change it if this company pays a different one.</div>
        </div>
        ${(a.vat_percent === null || a.vat_percent === undefined)
          ? '<div class="cc" style="font-size:11px;margin-top:4px;color:var(--warn)"><i class="ti ti-alert-triangle"></i> Not answered yet — profit is withheld for this account until you say.</div>'
          : ''}
      </td></tr>
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-lock"></i> No Amazon account of its own?</div><div class="cc" style="font-size:11.5px">If this workspace has no SP-API credentials above, it can borrow another account's Amazon app to look up <b>catalogue data only</b> — product types, item type keywords, valid values, fees. It can <b>never</b> read that account's listings or inventory, and it can <b>never</b> publish. Leave as "none" for a normal, connected account.</div></td></tr>
      <tr><td class="k">Borrow Amazon app from</td><td class="v">
        <select class="ed" id="ac_creds_source">
          <option value="">none — this account uses its own Amazon app</option>
          ${(ACCOUNTS||[]).filter(x=>x.id!==a.id && x.has_creds).map(x=>
            `<option value="${esc(x.id)}" ${a.credentials_source_account_id===x.id?'selected':''}>${esc(x.label)}</option>`).join("")}
        </select>
        <div class="cc" style="font-size:11px;margin-top:3px">${a.can_publish===false
          ? '<span style="color:var(--warn)"><i class="ti ti-lock"></i> This workspace is read-only: it can generate listings, but not preview, verify or publish them.</span>'
          : 'This account can publish to Amazon.'}</div>
      </td></tr>
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
  // How many products are already imported, and when. Runs after the modal is
  // drawn, so the row it writes into exists.
  refreshInputStatus();
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
// The exact link the app has on disk for this account, spelled out and clickable.
// Previously the only clue was whatever happened to be inside the text box, so an
// account with a spreadsheet id but no stored URL looked like it had nothing saved.
function _savedSheetLine(label, url, gid){
  const u = String(url||"").trim();
  if(!u) return `<div class="cc" style="font-size:11px;margin-top:3px"><span class="missing">Nothing saved yet</span></div>`;
  const tab = String(gid||"").trim();
  return `<div class="cc" style="font-size:11px;margin-top:3px;word-break:break-all">`
       + `${esc(label)}: <a href="${esc(u)}" target="_blank" rel="noopener" style="color:#7fd0ff">${esc(u)}</a>`
       + (tab ? ` <code style="opacity:.75">(tab gid ${esc(tab)})</code>`
              : ` <span class="missing">— no tab (#gid=…) in this link</span>`)
       + `</div>`;
}

function _showParsed(boxId, url){
  const p=parseSheetUrl(url); const el=document.getElementById(boxId);
  if(!el) return;
  if(!url.trim()){ el.innerHTML=""; return; }
  if(p.id){ el.innerHTML='<span style="color:var(--ok)">✓ sheet '+esc(p.id.slice(0,10))+'…'+(p.gid?(' · tab gid '+esc(p.gid)):' · first tab')+'</span>'; }
  else { el.innerHTML='<span style="color:var(--red)">✗ couldn\u2019t read a sheet ID from that link</span>'; }
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
    // "" = this account uses its own Amazon app (or has none at all)
    credentials_source_account_id:((document.getElementById("ac_creds_source")||{}).value||""),
    // per-account eBay override (blank = fall back to the global eBay creds)
    ebay_app_id: ebayGlobal ? "" : ((document.getElementById("ac_ebay_app")||{}).value||"").trim(),
    ebay_cert_id: ebayGlobal ? "" : ((document.getElementById("ac_ebay_cert")||{}).value||"").trim(),
    default_marketplace:(document.getElementById("ac_marketplace")||{}).value||"UK",
    // A PERCENTAGE, because "20" and "0.2" are the same rate written two ways
    // and only the sender knows which was meant. Unticked sends 0 -- "not
    // registered", which is a real answer -- rather than blank, which means
    // nobody has said and makes the app withhold the figure instead.
    vat_percent: ((document.getElementById("ac_vat_on")||{}).checked)
      ? (parseFloat((document.getElementById("ac_vat_pct")||{}).value) || 0)
      : 0,
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
    if(j.ok){ if(out) out.innerHTML='<span style="color:var(--ok)">\u2713 Detected: '+(j.marketplaces||[]).join(", ")+'</span>'; loadHome(); }
    else { if(out) out.innerHTML='<span style="color:var(--red)">\u2717 '+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(out) out.innerHTML='<span style="color:var(--red)">\u2717 '+esc(String(e))+'</span>'; }
}
async function detectBrandsFromEditor(id){
  var out=document.getElementById("ac_detectout");
  if(out) out.innerHTML='<span class="genspin"></span> Reading brands from your live listings…';
  try{
    var j=await (await fetch("/accounts/detect_brands",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})})).json();
    if(j.ok){
      // reflect into the brands field
      var bf=document.getElementById("ac_brands"); if(bf) bf.value=(j.brands||[]).join(", ");
      if(out) out.innerHTML='<span style="color:var(--ok)">\u2713 Brands ('+esc(j.source||"")+'): '+esc((j.brands||[]).join(", ")||"none found")+'</span>'
        +'<div class="cc" style="margin-top:4px">'+esc(j.note||"")+'</div>';
      loadHome();
    } else { if(out) out.innerHTML='<span style="color:var(--red)">\u2717 '+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(out) out.innerHTML='<span style="color:var(--red)">\u2717 '+esc(String(e))+'</span>'; }
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
/* THE ACCOUNTS PANEL, which used to be the home page.
 *
 * It no longer LEAVES the workspace: the account you are in stays open behind
 * it, so opening the list to check something and closing it again costs
 * nothing. Before, this cleared ACTIVE_WS and unloaded the screen, so glancing
 * at the list meant reloading everything on the way back.
 *
 * Kept under the old name because eight call sites and the switcher use it.
 */
function goHome(){
  const m = document.getElementById("wsmodal");
  if(m) m.classList.add("open");
  loadHome();
}

function closeAccounts(){
  const m = document.getElementById("wsmodal");
  if(m) m.classList.remove("open");
}

async function enterWorkspace(key){
  const v=VIEWS.find(x=>String(x.key)===String(key)) || {key:key,label:key};
  ACTIVE_WS=v;
  // switch the backend view so all existing routes read this workspace's sheet
  try{ await fetch("/view/set",{method:"POST",headers:{"Content-Type":"application/json"},
       body:JSON.stringify({key:v.key, sheet:v.sheet||"", tab:v.tab||""})}); }catch(e){}
  // paint shell
  // Picking an account from the panel closes it. This used to hide a full-screen
  // home page; that element is gone, and calling .classList on the null it left
  // behind would have thrown here -- on the one path every account switch takes.
  closeAccounts();
  document.getElementById("workspace").classList.add("show");
  const col=_wsColor(v), isDrop=!v.brand;
  const icEl=document.getElementById("ws_ic");
  icEl.style.background=col.bg; icEl.style.color=col.fg;
  icEl.innerHTML = isDrop ? '<i class="ti ti-shopping-cart"></i>' : _initials(v.brand||v.label);
  document.getElementById("ws_nm").textContent=v.label||v.brand||"Unnamed sheet";
  document.getElementById("ws_sub").textContent=v.marketplace||"";
  document.getElementById("ws_title").textContent=(v.label||"Listings");
  document.getElementById("crumbs").innerHTML=
    `<span class="sep">/</span><span class="here">${esc(v.label||v.brand||"Unnamed sheet")}</span>`;
  // brand-only sections
  document.getElementById("nav_setup").style.display = isDrop ? "none" : "flex";
  window.WS_BRAND = isDrop ? "" : (v.brand||"");
  // currency + marketplace for this workspace
  WS_MARKET = _mktOf(v) || (isDrop ? "" : "");
  // This one only knew about dollars and pounds, so a German or Irish
  // marketplace showed euro amounts with a pound sign in front of them.
  CUR_SYMBOL = mktSymbol(WS_MARKET) || "\u00a3";   // one table: static/js/marketplaces.js
  SELECTED.clear(); updateSelBar();
  document.getElementById("gen_scope").textContent =
    (v.label? "\u201c"+v.label+"\u201d" : "this workspace\u2019s");
  navTo("listings");
  altaSyncUrl();
  loadRows();
  loadViews();   // keep legacy view <select> in sync if present
}

function navTo(sec){
  // THE DOOR, NOT JUST THE SIGNPOST.
  //
  //     "the user with permissions should only be able to view the page for
  //      which the permission is aloted to him"
  //
  // Permissions used to hide the nav ITEM, which is not the only way in: every
  // screen has a real address (/w/<workspace>/<section>), and there is also the
  // bookmark bar, the Back button, and any link somebody was sent. All of those
  // arrive here. The server already refuses the data (auth/guard.py), so this
  // is not what keeps the numbers safe -- it is what makes the answer legible
  // instead of letting the screen open and then fail, which reads as a broken
  // app rather than as "no".
  //
  // Guarded on the function existing because users.js is a separate file, and
  // navigation must not break if it has not loaded.
  if(typeof maySeeSection === "function" && !maySeeSection(sec)){
    if(typeof toast === "function"){
      toast("You do not have access to that page. Ask the account owner if you need it.");
    }
    return;
  }
  // LEAVING THE IMAGE LIBRARY PAGE HANDS THE LIBRARY BACK TO ITS MODAL.
  // Without this, pressing the images button on a Listings row would draw into
  // a container on a page nobody is looking at, and the modal would open empty.
  if(CUR_SEC === "imagelib" && sec !== "imagelib"
     && typeof imagelibOnLeave === "function") imagelibOnLeave();
  CUR_SEC=sec;
  document.querySelectorAll(".navitem").forEach(n=>n.classList.toggle("active", n.dataset.sec===sec));
  // OPEN THE GROUP THIS SCREEN LIVES IN. The sidebar's master items collapse,
  // so without this the highlight would sit inside a shut drawer and the app
  // would look like it had lost its place -- most visibly on a deep link into a
  // group the user last left closed. Guarded because navgroups.js is a separate
  // file and nav must not break if it fails to load.
  if(typeof navGroupSyncActive === "function") navGroupSyncActive(sec);
  // The nav items are real links now, and half of each address is the
  // workspace -- which moves. Re-point them whenever the section changes.
  if(typeof navSyncHrefs === "function") navSyncHrefs();
  // listings uses #sec_listings (always block); others are .wspanel
  document.getElementById("sec_listings").style.display = (sec==="listings")?"block":"none";
  // THIS LIST IS WHAT MAKES A SCREEN VISIBLE, and it is a second list of the
  // same screens as ALTA_SECTIONS below. "permissions" was added to that one --
  // so it got an address, a nav link and an onOpen that ran and drew the page --
  // and left out of this one, so the panel it drew into never had .show put on
  // it. Every part of the screen worked except being seen.
  //
  // Found by opening every section in a real browser and photographing it:
  // Permissions came back as an empty page with no error, which is exactly what
  // a missing entry here looks like.
  ["imagerefs","setup","generate","miles","sales","traffic","hourly","ppc","inventory","sync","monitor","sourcing","orders","returns","daily","weekly","imagestudio","aiusage","finance","variations","sellerimport","trackers","alerts","leading","notify","sqp","catalog","compliance","overview","categories","drppc","imagelib","permissions","reimbursements","brief"].forEach(s=>{
    const el=document.getElementById("sec_"+s);
    if(el) el.classList.toggle("show", s===sec);
  });
  // LOAD ONLY IF THERE IS SOMETHING TO LOAD.
  //
  // Every one of these used to run on every visit, so going Sales -> Orders ->
  // Sales made you wait for Sales twice. The rendered content was never gone:
  // its panel is hidden, not emptied. Skipping the loader shows it again
  // instantly, which is what every other app does and what was asked for.
  //
  // screenNeedsLoad() is true the first time, true again once the content is
  // old, and true immediately after an account or marketplace change -- see
  // static/js/screenstate.js for why that last one is the important part.
  const _fresh = (typeof screenNeedsLoad === "function") ? screenNeedsLoad(sec) : true;
  const _mark  = function(){ if(typeof screenLoaded === "function") screenLoaded(sec); };
  if(_fresh){
    if(sec==="setup")     loadBrandPanel();
    if(sec==="imagerefs") loadImageRefs();
    if(sec==="generate"){ loadTargetAccount(); loadInputSheet();
      // What a run WOULD do, before it does it. Costs nothing -- it asks
      // the generator's own duplicate rule and reports the answer.
      if(typeof genplanLoad==="function") genplanLoad(); }
    if(sec==="miles"){    milesLoadResults(); milesLoadPref(); }
    if(sec==="sales"){    if(typeof salesOpen==="function") salesOpen(); }
    if(sec==="traffic"){  if(typeof trafficOnOpen==="function") trafficOnOpen(); }
    if(sec==="hourly"){   if(typeof hourlyOnOpen==="function")  hourlyOnOpen(); }
    if(sec==="ppc")       ppcOnOpen();
    if(sec==="sync"){     if(typeof syncOnOpen==="function") syncOnOpen(); }
    if(sec==="monitor"){  if(typeof monitorOnOpen==="function") monitorOnOpen(); }
    if(sec==="sourcing"){ if(typeof sourcingOnOpen==="function") sourcingOnOpen(); }
    if(sec==="orders"){   if(typeof ordersOnOpen==="function")   ordersOnOpen(); }
    if(sec==="returns"){  if(typeof returnsOnOpen==="function")  returnsOnOpen(); }
  if(sec==="daily"){    if(typeof dailyOnOpen==="function")    dailyOnOpen(); }
  if(sec==="weekly"){   if(typeof weeklyOnOpen==="function")   weeklyOnOpen(); }
  // The trackers and their alerts. Both read STORED readings only -- opening
  // either never calls Amazon. A check costs an API call per ASIN and happens
  // when the button is pressed, which is the lesson the ASIN Monitor was rebuilt
  // around ("i dont want the asin monitor to be working always").
  if(sec==="trackers"){ if(typeof trkLoad==="function")    trkLoad(); }
  if(sec==="alerts"){   if(typeof alertsLoad==="function") alertsLoad(); }
  // Reads sales_daily, which the app already syncs -- no Amazon call.
  if(sec==="leading"){  if(typeof leadLoad==="function")   leadLoad(); }
  // Reads the channel list and the delivery log. Opening this screen NEVER
  // sends anything -- that is a button, deliberately.
  if(sec==="notify"){   if(typeof ntfLoad==="function")    ntfLoad(); }
  // Amazon BUILDS this report on request, roughly one a minute, so opening the
  // screen does not fetch it -- "Get the report" does.
  if(sec==="sqp"){      if(typeof sqpRender==="function")  sqpRender(); }
  // Reads the app's own sales table and catalogue snapshot -- no Amazon call.
  if(sec==="catalog"){  if(typeof catpLoad==="function")   catpLoad(); }
  // Loads the scan HISTORY only. A scan is an Amazon call and a button press.
  if(sec==="compliance"){ if(typeof cmpLoad==="function") cmpLoad(); }
  // Reads EVERY account, so it is the one screen the account switcher does not
  // narrow. Nothing is fetched from Amazon -- it reads what is already stored.
  if(sec==="overview"){ if(typeof ovwLoad==="function")   ovwLoad(); }
  // Draws the STORED map. Reading from Amazon is one call per product and is
  // therefore a button, never something that happens on open.
  if(sec==="categories"){ if(typeof catsLoad==="function") catsLoad(); }
  // Checks the CONNECTION on open, never the reports -- those are two Amazon
  // report builds and belong behind the button.
  if(sec==="drppc"){ if(typeof drpOnOpen==="function")   drpOnOpen(); }
  if(sec==="imagelib"){ if(typeof imagelibOnOpen==="function") imagelibOnOpen(); }
  if(sec==="permissions"){ if(typeof permissionsOnOpen==="function") permissionsOnOpen(); }
  // studioPickerOnOpen draws the product picker and then calls
  // imagestudioOnOpen itself, so the Studio works with nothing chosen -- it no
  // longer has to be entered from Listings.
  if(sec==="imagestudio"){ if(typeof studioPickerOnOpen==="function") studioPickerOnOpen();
                           else if(typeof imagestudioOnOpen==="function") imagestudioOnOpen(); }
    if(sec==="aiusage"){  if(typeof aiUsageOnOpen==="function")  aiUsageOnOpen(); }
    if(sec==="finance"){  if(typeof financeOnOpen==="function")  financeOnOpen(); }
    if(sec==="variations"){ if(typeof variationsOnOpen==="function") variationsOnOpen(); }
    if(sec==="sellerimport"){ if(typeof sellerImportOnOpen==="function") sellerImportOnOpen(); }
    if(sec==="inventory"){ if(typeof stockOnOpen==="function") stockOnOpen(); }
    if(sec==="reimbursements"){ if(typeof reimbursementsOnOpen==="function") reimbursementsOnOpen(); }
  if(sec==="brief"){ if(typeof briefOnOpen==="function") briefOnOpen(); }
  // The bookmark bar marks the page you are on and its star reflects
  // whether THIS page is pinned, so both follow every navigation.
  if(typeof bmkRender==="function") bmkRender();
    _mark();
  }
  altaSyncUrl();
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

// loadInputSheet and filterInputSheet MOVED to static/js/inputqueue.js.
//
// They rendered the Google input sheet read-only, from /input_sheet. The screen
// now edits the queue itself, so keeping these here would have been two
// functions of the same name in two files, with whichever script loaded last
// deciding what the button did -- and shell.js loads late, so the old read-only
// pair would have quietly won.

function navToBrandCreate(){
  // open a blank brand setup so the user can create a new brand profile
  enterWorkspaceBlank();
}
function enterWorkspaceBlank(){
  ACTIVE_WS={key:"",label:"New brand",brand:"new"};
  // Picking an account from the panel closes it. This used to hide a full-screen
  // home page; that element is gone, and calling .classList on the null it left
  // behind would have thrown here -- on the one path every account switch takes.
  closeAccounts();
  document.getElementById("workspace").classList.add("show");
  document.getElementById("ws_nm").textContent="New brand";
  document.getElementById("ws_sub").textContent="";
  document.getElementById("nav_setup").style.display="flex";
  document.getElementById("crumbs").innerHTML='<span class="sep">/</span><span class="here">New brand</span>';
  navTo("setup");
}

// ===================== URL ROUTING (addressable screens) =====================
// Plain English: the app used to keep every screen behind the single address
// "/", so refreshing threw you back to the workspace list, nothing could be
// bookmarked, and Back left the app altogether. Every screen now has a real
// address -- /w/<workspace>/<section> -- and the browser bar follows you as you
// move. Nothing is reloaded and nothing is re-fetched: this only RECORDS where
// you are, so the page can put you back there.
//
// Everything below is defensive. Every history call is wrapped, and if any of it
// throws, the app behaves exactly as it did before -- the sections still switch.
// Routing can fail to update an address; it can never stop you navigating.

// Sections that get their own address, so /w/<account>/<section> opens them.
// "weekly" is here because a client KPI pack is a thing you send somebody a
// link to, which is the whole reason this list exists.
// EVERY screen, not thirteen of them.
//
// This list decides which sections have an address. It had thirteen entries
// while the app had twenty-eight screens, so most of them could not be linked
// to, bookmarked, restored after a refresh, or opened in a second tab -- and
// the ones added most recently were exactly the ones missing.
//
// It is also what makes right-click "open in a new tab" work: a nav item can
// only be a real link if there is an address for it to point at.
const ALTA_SECTIONS = ["listings","imagerefs","setup","generate",
                       "sales","traffic","hourly","ppc","inventory","sync","monitor","miles",
                       "weekly","daily","orders","returns","variations","sellerimport",
                       "sourcing","finance","aiusage","imagestudio","imagelib",
                       "trackers","alerts","leading","notify","sqp","catalog",
                       "compliance","overview","categories","drppc","permissions",
                       "reimbursements","brief"];

// THE ADDRESS FOR ONE SECTION, so a nav item can be a real <a href>.
//
//     "i see that when i right click on them i dont get an option to open them
//      to the new tab"
//
// They were <div onclick=...>. A browser offers "open in new tab" for LINKS --
// it has no idea a div is navigation. So the nav items are anchors now, and
// this builds what they point at. Single click is still handled in JavaScript
// and never reloads the page; the href is there for the right-click menu,
// ctrl-click, middle-click and for showing the address on hover.
function altaPathFor(sec){
  if(!ACTIVE_WS || ACTIVE_WS.brand === "new") return "";
  if(ALTA_SECTIONS.indexOf(sec) < 0) return "";
  const slug = String(ACTIVE_WS.key || "") || "default";
  return "/w/" + encodeURIComponent(slug) + "/" + sec;
}

// Point every nav link at the CURRENT workspace. Called when one is opened and
// whenever the section changes, because the workspace is half of the address
// and it moves.
function navSyncHrefs(){
  try{
    document.querySelectorAll(".navitem[data-sec]").forEach(function(el){
      const p = altaPathFor(el.dataset.sec);
      if(p && el.tagName === "A") el.setAttribute("href", p);
    });
  }catch(e){}
}

// A nav click. Returns false for an ORDINARY click so the page never reloads,
// and true for a modified one so the browser does what it always does --
// ctrl/cmd-click and middle-click open a new tab, and taking that away would
// be replacing one missing behaviour with another.
function navGo(ev, sec){
  try{
    if(ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1)) return true;
    if(ev && ev.preventDefault) ev.preventDefault();
  }catch(e){}
  navTo(sec);
  return false;
}

let _ALTA_ROUTED    = false;  // has the one-time restore-from-address already run?
let _ALTA_RESTORING = false;  // true while replaying an address: replace, never push

// The address for whatever is on screen right now, or null when there is nothing
// worth recording.
function altaCurrentPath(){
  if(!ACTIVE_WS) return "/";
  // The blank "New brand" screen is a form being filled in, not a place. Giving
  // it an address would produce a bookmark that reopens an empty form.
  if(ACTIVE_WS.brand === "new") return null;
  const slug = String(ACTIVE_WS.key || "") || "default";
  const sec  = (ALTA_SECTIONS.indexOf(CUR_SEC) >= 0) ? CUR_SEC : "listings";
  let p = "/w/" + encodeURIComponent(slug) + "/" + sec;
  // Drafts is the default so it stays out of the address; Live and All are worth
  // recording, because landing back on Drafts after a refresh is the annoyance.
  if(sec === "listings" && (LIST_SOURCE === "live" || LIST_SOURCE === "all")){
    p += "?src=" + LIST_SOURCE;
  }
  return p;
}

function altaSyncUrl(){
  try{
    const p = altaCurrentPath();
    if(!p) return;
    if(p === (location.pathname + location.search)) return;   // nothing moved
    history[_ALTA_RESTORING ? "replaceState" : "pushState"]({alta:1}, "", p);
  }catch(e){}
}

// Read the address bar and reopen that screen. Runs once, from the end of
// loadHome(), because opening a workspace before ACCOUNTS and VIEWS are known
// could only guess at which one was meant.
async function altaRouteFromUrl(){
  const m = /^\/w\/([^\/]+)(?:\/([^\/]+))?\/?$/.exec(location.pathname || "");
  if(!m){
    // NO ADDRESS -- so land on the account that was open last, not on a grid of
    // cards. Orbit has no landing page at all: you arrive on a working screen
    // and switch from the sidebar, and a session that begins on a screen with
    // no work on it is a click everyone pays every time.
    //
    // The grid still exists and is one click away ("Manage accounts…"), because
    // it is where accounts are added and edited. It is just no longer the door.
    let last = "";
    try{ last = localStorage.getItem("alta_last_account") || ""; }catch(e){}
    const known = (ACCOUNTS || []).some(a => String(a.id) === last);
    if(last && known){
      enterAccount(last).then(_altaBootDone).catch(_altaBootDone);
      return;
    }
    // Nothing remembered: the first CONNECTED account, since a draft-only one
    // opens onto half a working screen. Failing that, the grid, which is the
    // right answer for a fresh install with nothing set up.
    const first = (ACCOUNTS || []).filter(a => a.has_creds)[0] || (ACCOUNTS || [])[0];
    if(first){
      enterAccount(first.id).then(_altaBootDone).catch(_altaBootDone);
      return;
    }
    _altaBootDone();
    return;
  }
  const ws  = decodeURIComponent(m[1] || "");
  let   sec = m[2] || "listings";
  if(ALTA_SECTIONS.indexOf(sec) < 0) sec = "listings";
  let src = "";
  try{ src = new URLSearchParams(location.search).get("src") || ""; }catch(e){}

  _ALTA_RESTORING = true;
  try{
    // A bookmark to the old Dropshipping workspace falls through to the
    // "no longer exists" branch below, which is exactly right -- it does not.
    if((ACCOUNTS||[]).some(a => String(a.id) === ws)){
      await enterAccount(ws);
    } else if((VIEWS||[]).some(v => String(v.key) === ws)){
      await enterWorkspace(ws);
    } else {
      // The link names a workspace that has since been renamed or removed. Say
      // so, rather than silently opening whichever one happens to be first.
      toast("That workspace no longer exists — showing all workspaces.");
      try{ history.replaceState({alta:1}, "", "/"); }catch(e){}
      return;
    }
    if(sec !== CUR_SEC) navTo(sec);
    if(sec === "listings" && (src === "live" || src === "all")
       && typeof setListSource === "function"){
      setListSource(src);
    }
  }catch(e){
    // Reopening failed. Leave the user on whatever did load rather than
    // trapping them on a half-drawn screen.
  }finally{
    _ALTA_RESTORING = false;
    altaSyncUrl();   // settle the address on where we actually ended up
    _altaBootDone();
  }
}

// The hand-off is over: let the home screen exist again and take the veil down.
// Called from every path out of routing, including the ones that gave up --
// a home screen that stays hidden is a worse bug than the flash it replaced.
function _altaBootDone(){
  try{
    document.documentElement.classList.remove("alta-routing");
    const b = document.getElementById("alta-booting");
    if(b) b.style.display = "none";
  }catch(e){}
}

// Back / Forward. altaRouteFromUrl owns the restoring flag for its own run, so
// it is NOT set here -- that function is async, and setting the flag around a
// call that returns at its first await would clear it far too early.
window.addEventListener("popstate", function(){
  // ONE BRANCH, because "/" is no longer a different kind of address. It used
  // to mean "leave the workspace and show the grid of cards", so Back unloaded
  // everything you had open; there is no home page to leave it for now, and
  // altaRouteFromUrl already knows that "/" means the account you were last in.
  try{ altaRouteFromUrl(); }catch(e){}
});

// Record the Drafts / Live / All switch in the address too. Wrapped here rather
// than edited into miles_template.js so that every line of routing lives in one
// file: the source switch has no business knowing about the address bar. Load
// order makes this safe -- miles_template.js is loaded before shell.js, so the
// original function already exists by the time this runs.
(function(){
  if(typeof window.setListSource !== "function") return;
  const _inner = window.setListSource;
  window.setListSource = function(){
    const r = _inner.apply(this, arguments);
    altaSyncUrl();
    return r;
  };
})();

