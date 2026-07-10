let ROWS = [], FILTER = "all", SHIP = "", SCHEMAS = {}, PTYPES = [];
let SELECTED = new Set();      // SKUs ticked for batch actions
let CUR_SYMBOL = "\u00a3";     // £ default; flips to $ for US workspaces
let WS_MARKET = "";           // active marketplace within the workspace
let DRAWER_SKU = null;        // SKU currently open in the side drawer

// Resolve a listing's OWN marketplace (US/UK/…): the row's marketplace first,
// then its attributes, then the active workspace marketplace, then UK. Used so
// the schema/value lists are fetched for the listing's real marketplace+creds.
function rowMkt(r){
  r=r||{};
  return String(r._marketplace || (r.attributes||{}).marketplace || WS_MARKET || "UK").toUpperCase();
}

function toggleSelect(sku, on){
  if(on) SELECTED.add(String(sku)); else SELECTED.delete(String(sku));
  const c=document.querySelector('.lcard[data-sku="'+CSS.escape(String(sku))+'"]');
  if(c) c.classList.toggle('sel', on);
  updateSelBar();
}
function selectAllVisible(on){
  ROWS.filter(passFilter).filter(r=>!isEmptyRow(r)).forEach(r=>{
    if(on) SELECTED.add(String(r.sku)); else SELECTED.delete(String(r.sku));
  });
  render(); updateSelBar();
}
function clearSelection(){ SELECTED.clear(); render(); updateSelBar(); }
function updateSelBar(){
  const bar=document.getElementById('selbar'); if(!bar) return;
  const n=SELECTED.size;
  bar.style.display = n? 'flex':'none';
  const cnt=document.getElementById('selcount'); if(cnt) cnt.textContent=n+' selected';
}
function selectedSkus(){ return Array.from(SELECTED); }

async function batchGenerate(kind){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  // Batch COPY regeneration runs through the generator with a --skus filter.
  // If your generator build doesn't have --skus yet, it will report that.
  if(!confirm("Regenerate listing copy for "+skus.length+" selected SKU(s)?\nThis reruns the generator scoped to just these SKUs.")) return;
  navTo("generate");
  const log=document.getElementById("log"); if(log){ log.style.display="block"; log.textContent="Starting regeneration for "+skus.length+" SKU(s)…\n"; }
  try{
    const es=new EventSource("/run/regen?skus="+encodeURIComponent(skus.join(",")));
    es.onmessage=e=>{ if(log){ log.textContent+=e.data+"\n"; log.scrollTop=log.scrollHeight; } };
    es.addEventListener("end",()=>{ es.close(); showStop(false); loadRows(); toast("Regeneration finished"); });
    showStop(true);
  }catch(e){ toast("Could not start: "+e); }
}

async function batchAutoGenerate(kind){
  // Bulk one-click: strategize + generate in the BACKGROUND. Does NOT open the
  // studio — the floating status bar shows progress, results auto-save to each
  // product's media library, and it keeps running on any page. kind defaults to
  // 'secondary'; pass 'aplus' for the A+ button.
  kind=kind||"secondary";
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  const per=(kind==="aplus")?7:7; // 7 secondary or up to 7 A+ modules
  const n=skus.length;
  if(!confirm("Auto-generate "+(kind==="aplus"?"A+ modules":"secondary images")+" for "+n+
              " product"+(n>1?"s":"")+" (~"+(n*per)+" images). The strategist proposes ideas and "+
              "generates them all in the background. You can keep working. Continue?")) return;

  const liveSel = (LIST_SOURCE==='live' || LIST_SOURCE==='all');
  toast("Designing concepts for each product…");
  // Strategize SEPARATELY for EACH product using its own reference image, so
  // every product gets concepts tailored to ITSELF — no shared/mixed set.
  let jobs=[];
  let skipped=[];
  for(let si=0; si<skus.length; si++){
    const sku=skus[si];
    const it=_itemForSku(sku);
    const ref=_refImgForItem(it);
    if(!ref){ skipped.push(sku); continue; }
    let concepts=[];
    try{
      const sj=await (await fetch("/genimage/strategize",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({product_image:ref, title:(it&&it.title)||"", kind:kind,
          n:per, text_provider:(window.AI_TEXT||null)})})).json();
      if(!sj.ok){ toast("Strategist failed for "+sku+": "+(sj.error||"unknown")); continue; }
      concepts=sj.concepts||[];
    }catch(e){ toast("Strategist error for "+sku+": "+e); continue; }
    if(!concepts.length){ continue; }
    const asin=liveSel?_asinForSku(sku):"";
    concepts.forEach((c,ci)=>{
      const code=(kind==="aplus")
        ? ("APLUS"+String(ci+1).padStart(2,"0"))
        : ("PT"+String(ci+1).padStart(2,"0"));
      jobs.push({sku:sku, ref:ref, label:sku+" · "+(c.title||code),
        asin:asin, img_code:code,
        payload:{ product_image:ref, title:(it&&it.title)||"", kind:kind,
          concept:c.concept||"", art_direction:c.art_direction||"",
          fidelity:"high", tier:"basic",
          text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null) }});
    });
  }
  if(skipped.length){ toast(skipped.length+" product(s) skipped — no reference image: "+skipped.join(", ")); }
  if(!jobs.length){ toast("Nothing to generate — no products had reference images or concepts."); return; }

  // 3) submit as a background batch — no studio window, status bar tracks it
  try{
    const r=await (await fetch("/genimage/start_batch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:"concept", jobs:jobs, label:(kind==="aplus"?"A+ ":"Secondary ")+"× "+n+" product"+(n>1?"s":"")})})).json();
    if(!r.ok){ toast("Could not start: "+(r.error||"unknown")); return; }
    GEN_ACTIVE_JOB=r.job;
    toast("Started "+jobs.length+" image(s) in the background.");
    openGenPanel();
    startGenStatusPoll();
  }catch(e){ toast("Error: "+e); }
}
function _asinForSku(sku){
  // find the ASIN for a SKU from live items or rows
  const s=String(sku);
  let it=(LIVE_ITEMS||[]).find(x=>String(x.sku)===s);
  if(it && it.asin) return String(it.asin);
  it=(ROWS||[]).find(x=>String(x.sku)===s);
  return (it && it.asin) ? String(it.asin) : "";
}
async function batchSecondaryImages(){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some listings first"); return; }
  // Detect whether the selected SKUs are LIVE Amazon listings (not in the draft
  // sheet). Live listings aren't rows in our sheet, so we generate the images
  // and hand them back for download (upload via Amazon Manage Images), using
  // each live listing's own Amazon photo as the visual reference.
  const liveSel = (LIST_SOURCE==='live' || LIST_SOURCE==='all');
  const liveRefs = {};
  if(liveSel){
    (LIVE_ITEMS||[]).forEach(it=>{ if(it.sku && skus.includes(String(it.sku)) && it.img) liveRefs[it.sku]=it.img; });
  }
  const brief=prompt("Describe the secondary images to generate (one shared set applied to all "+skus.length+" selected SKUs).\nSeparate each image idea with a comma or new line — e.g. 'lifestyle shot in a modern bathroom, infographic of key ingredients, clean packaging shot, how-to-use steps'.\n\nTip: keep text minimal and premium.");
  if(brief===null) return;
  toast("Generating secondary images for "+skus.length+" SKU(s)…");
  try{
    const res=await fetch("/genimage/secondary",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({skus:skus, brief:brief, live:liveSel, live_refs:liveRefs})});
    const j=await res.json();
    if(!j.ok){ toast("Failed: "+(j.error||"unknown")); return; }
    if(j.images && j.images.length){
      // show the generated set in a panel so the user can download each one
      showSecondaryResults(j.images, skus, liveSel);
    }
    toast(liveSel ? ("Generated "+ (j.images? j.images.length:0) +" image(s) — download below")
                  : ("Secondary images applied to "+skus.length+" SKU(s)"));
    if(!liveSel) loadRows();
  }catch(e){ toast("Error: "+e); }
}
function showSecondaryResults(images, skus, live){
  let host=document.getElementById("secresults");
  if(!host){
    host=document.createElement("div"); host.id="secresults";
    host.style.cssText="position:fixed;right:18px;bottom:18px;width:340px;max-height:70vh;overflow:auto;background:var(--card,#0f1722);border:1px solid var(--line,#22304a);border-radius:12px;padding:14px;z-index:9999;box-shadow:0 10px 40px rgba(0,0,0,.5)";
    document.body.appendChild(host);
  }
  const note = live
    ? "These are generated as a shared set. Download each, then upload to your live listings via Amazon → Manage Images (live listings can't be image-updated automatically)."
    : "Applied to the selected draft SKUs and saved to the sheet.";
  host.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
    + '<b style="font-size:13px">Secondary images ('+images.length+')</b>'
    + '<button onclick="document.getElementById(\'secresults\').remove()" style="background:none;border:none;color:#9cc1ff;cursor:pointer;font-size:16px">✕</button></div>'
    + '<div style="font-size:11px;color:#9fb2cc;margin-bottom:10px">'+note+'</div>'
    + images.map((u,i)=>'<div style="margin-bottom:10px"><img src="'+u+'" style="width:100%;border-radius:8px;border:1px solid var(--line,#22304a)"><a href="#" onclick="_downloadAsJpeg(\''+u+'\',\'secondary_'+(i+1)+'\');return false;" style="display:inline-block;margin-top:4px;font-size:12px;color:#9cc1ff">⬇ Download image '+(i+1)+'</a></div>').join("");
}
async function loadBrandPanel(){
  const host=document.getElementById('brandpanel');
  if(!host.dataset.loaded){
    host.innerHTML = await (await fetch('/brand/panel')).text();
    host.dataset.loaded='1';
    host.querySelectorAll('script').forEach(old=>{const s=document.createElement('script'); s.textContent=old.textContent; document.body.appendChild(s);});
    if(window.brandInit) window.brandInit();
  } else if(window.brandRefresh){
    window.brandRefresh();   // re-lock to the current workspace's brand
  }
}
function iBtnEntry(p){
  if(!p) return '';
  const verified = p.verified ? 'code-verified' : 'AI-reported';
  const tip = ((p.source||'') + (p.note? ' \u2014 '+p.note : '') + ' ('+verified+')');
  const warn = (String(p.source||'').startsWith('INFERRED') && !p.verified);
  return '<i class="ibtn '+(warn?'iwarn':'iok')+'" title="'+tip.replace(/"/g,'&quot;')+'">i</i>';
}
function iBtn(prov, key){ return (prov&&prov[key])?iBtnEntry(prov[key]):''; }
// Small source badge for an attribute value: where the data came from.
function srcBadge(src){
  if(!src) return '';
  const s=String(src).toLowerCase();
  let cls='', label='';
  if(s==='ebay'){ cls='src-ebay'; label='eBay'; }
  else if(s==='amazon'){ cls='src-amazon'; label='Amazon'; }
  else if(s==='ai'){ cls='src-ai'; label='AI'; }
  else return '';
  const tip = (s==='ebay') ? 'Value sourced from the eBay listing'
            : (s==='amazon') ? 'Value sourced from Amazon catalogue data'
            : 'Value written by AI from product knowledge — please verify';
  return '<span class="srcbadge '+cls+'" title="'+tip+'">'+label+'</span>';
}
function rowProvenance(r){ try{ return (JSON.parse(r.attrs||'{}')._provenance)||null; }catch(e){ return null; } }
function locateFlags(sku, btn){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r) return;
  const out=document.getElementById('loc_'+sid(sku)); if(!out) return;
  // pull flagged terms from notes: "phrases: a, b" and "suspected brand words: c, d"
  const notes=String(r.notes||'')+' '+String(r.comp_notes||'');
  let terms=[];
  let m=notes.match(/phrases?:\s*([^|]+)/i); if(m) terms=terms.concat(m[1].split(',').map(s=>s.trim()));
  m=notes.match(/suspected brand words?:\s*([^|]+)/i); if(m) terms=terms.concat(m[1].split(',').map(s=>s.trim()));
  terms=terms.filter(t=>t&&t.length>1);
  if(!terms.length){ out.innerHTML='<div class="cc" style="margin-top:6px">No specific terms parsed from the note — the flag may be a category/compliance signal, not a word match.</div>'; return; }
  // search each content field for each term
  const fields={'Title':r.title,'Bullet 1':(r.bullets||[])[0],'Bullet 2':(r.bullets||[])[1],
    'Bullet 3':(r.bullets||[])[2],'Bullet 4':(r.bullets||[])[3],'Bullet 5':(r.bullets||[])[4],
    'Description':r.description,'Search terms':r.search_terms};
  let html='<div style="margin-top:8px;border-top:1px solid var(--line);padding-top:6px">';
  let any=false;
  terms.forEach(t=>{
    const re=new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig');
    Object.keys(fields).forEach(fn=>{
      const v=String(fields[fn]||'');
      if(v && re.test(v)){
        any=true;
        const hl=esc(v).replace(re,'<mark style="background:#5c4a16;color:#ffe9a8">$1</mark>');
        html+='<div style="margin:4px 0"><b style="color:#e3b768">'+esc(t)+'</b> in <b>'+fn+'</b>: <span style="color:#cbd3e1">'+hl+'</span></div>';
      }
    });
  });
  if(!any) html+='<div class="cc">None of the flagged terms were found in the current copy — they may have already been edited out. Safe to re-check.</div>';
  html+='</div>';
  out.innerHTML=html;
}
(function(){
  document.querySelectorAll('header .pill[data-f]').forEach(p=>{
    p.addEventListener('click',()=>{
      document.getElementById('brandpanel').style.display='none';
      document.getElementById('grid').style.display='';
      document.getElementById('summary').style.display='';
    });
  });
})();

function esc(s){return (s==null?"":String(s)).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");
  clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove("show"),1800);}

function badgeClass(s){return ["APPROVED","NEEDS_REVIEW","IP_HOLD","COMPLIANCE_HOLD","ERROR","API_READY","API_ERROR","LIVE"].includes(s)?("b-"+s):"b-none";}
function isHold(s){return s==="IP_HOLD"||s==="COMPLIANCE_HOLD"||s==="ERROR"||s==="API_ERROR";}

function passFilter(r){
  if(FILTER==="all")return true;
  if(FILTER==="review")return r.status==="NEEDS_REVIEW";
  if(FILTER==="holds")return isHold(r.status);
  if(FILTER==="approved")return r.status==="APPROVED"||r.status==="API_READY";
  if(FILTER==="live")return r.status==="LIVE";
  return true;
}

// Is this row live ON AMAZON? Amazon's catalog is the ONLY authority whenever we
// have it. A "LIVE" in the sheet is a claim, not proof: the sheet is written by
// this app, it is never re-read from Amazon, and a misrouted tab once put another
// account's "LIVE" rows straight into the Live on Amazon group. So when the live
// catalog is loaded, a row counts as live only if Amazon returned its SKU or ASIN.
//
// Without the catalog (the Drafts view never fetches it) we fall back to the
// sheet's own claim -- and render() labels that group as unverified, rather than
// captioning it "Live on Amazon".
//
// Must return the SAME answer for render() (grouping) and summary() (counting),
// or the top bar disagrees with the grid.
function isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  const s=norm(r.sku), a=norm(r.asin);
  if(liveGroupShown) return !!((s && liveCatSkus.has(s)) || (a && liveCatAsins.has(a)));
  return norm(r.status)==="LIVE";
}

// The sheet SAYS this row is live, but Amazon's catalog does not list it.
// Only meaningful once the catalog is loaded.
function isClaimedLiveOnly(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  if(!liveGroupShown) return false;
  return norm(r.status)==="LIVE" && !isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown);
}

// Build the SKU/ASIN sets once per render -- reused by summary()
function _liveCatSetsForCurrentView(){
  const norm = v => String(v||"").trim().toUpperCase();
  return {
    skus:  new Set((LIVE_ITEMS||[]).map(it=>norm(it.sku)).filter(Boolean)),
    asins: new Set((LIVE_ITEMS||[]).map(it=>norm(it.asin)).filter(Boolean)),
    liveGroupShown: (LIST_SOURCE==="live" || LIST_SOURCE==="all"),
  };
}

function summary(){
  const c={APPROVED:0,API_READY:0,NEEDS_REVIEW:0,HOLD:0,ERROR:0,LIVE:0};
  const sets = _liveCatSetsForCurrentView();
  ROWS.forEach(r=>{
    // FIX: reclassify HOLD/NEEDS_REVIEW/etc. as LIVE if the row's SKU/ASIN
    // matches the Amazon catalog. Without this the top-bar shows a stale
    // "N on hold" count for rows that already went live on Amazon but never
    // had their stored status updated from a pre-submit HOLD.
    if(isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown)){
      c.LIVE++;
      return;
    }
    if(r.status==="APPROVED")c.APPROVED++;
    else if(r.status==="API_READY")c.API_READY++;
    else if(r.status==="LIVE")c.LIVE++;
    else if(r.status==="NEEDS_REVIEW")c.NEEDS_REVIEW++;
    else if(r.status==="IP_HOLD"||r.status==="COMPLIANCE_HOLD")c.HOLD++;
    else if(r.status==="ERROR"||r.status==="API_ERROR")c.ERROR++;
  });
  // include live Amazon listings in the counts when they're part of the view.
  // Deduplicate: a catalog tile whose SKU/ASIN already matched an app row above
  // has already been counted as LIVE -- don't count it twice.
  const norm = v => String(v||"").trim().toUpperCase();
  const alreadyCountedSkus  = new Set(ROWS.filter(r=>isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown))
                                          .map(r=>norm(r.sku)).filter(Boolean));
  const alreadyCountedAsins = new Set(ROWS.filter(r=>isActuallyLive(r, sets.skus, sets.asins, sets.liveGroupShown))
                                          .map(r=>norm(r.asin)).filter(Boolean));
  const liveCount = ((LIST_SOURCE==='live'||LIST_SOURCE==='all')
                     ? (LIVE_ITEMS||[]).filter(it=>{
                         const s=norm(it.sku), a=norm(it.asin);
                         if(s && alreadyCountedSkus.has(s))  return false;
                         if(a && alreadyCountedAsins.has(a)) return false;
                         return true;
                       }).length
                     : 0);
  c.LIVE += liveCount;
  // total reflects what's actually shown in the current view
  let total = ROWS.length;
  if(LIST_SOURCE==='live') total = liveCount;
  else if(LIST_SOURCE==='all') total = ROWS.length + liveCount;
  document.getElementById("summary").innerHTML =
    `<b style="color:#e8eaed">${total}</b> listings &nbsp;·&nbsp; `+
    `${c.NEEDS_REVIEW} needs review &nbsp;·&nbsp; `+
    `<span style="color:#ef9a9a">${c.HOLD} on hold</span> &nbsp;·&nbsp; `+
    `<span style="color:#ef9a9a">${c.ERROR} error</span> &nbsp;·&nbsp; `+
    `<span style="color:#7fd1a0">${c.APPROVED} approved</span> &nbsp;·&nbsp; `+
    `<span style="color:#9cc1ff">${c.API_READY} preview-ready</span> &nbsp;·&nbsp; `+
    `<span style="color:#74e0a3">${c.LIVE} live</span>`;
}

// Pull a LIVE listing's real data (every Amazon image: main + all secondary) into the row, so
// the product card, the drawer and Image Studio show the ACTUAL live photos instead of the
// eBay/competitor ones captured at generation time -- and so A+ finally has a reference image.
async function pullLiveRow(sku, btn){
  const _old = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled=true; btn.innerHTML='<span class="genspin"></span> Pulling from Amazon…'; }
  try{
    const j = await (await fetch("/live/pull_row",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku})})).json();
    if(!j || !j.ok){ toast("Couldn't pull from Amazon: "+((j&&j.error)||"unknown")); return; }
    toast("Pulled "+j.count+" live image(s) from Amazon");
    try{
      const r = await (await fetch("/row?sku="+encodeURIComponent(sku))).json();
      if(r && r.ok && r.row){
        const i = ROWS.findIndex(x=>String(x.sku)===String(sku));
        if(i>=0) ROWS[i] = Object.assign({}, ROWS[i], r.row);
      }
    }catch(e){}
    try{ render(); }catch(e){}
    if(typeof DRAWER_SKU!=="undefined" && String(DRAWER_SKU)===String(sku)){ try{ openDrawer(sku); }catch(e){} }
  }catch(e){
    toast("Pull failed: "+((e&&e.message)||e));
  }finally{
    if(btn){ btn.disabled=false; btn.innerHTML=_old; }
  }
}
function _rowImages(r){
  var a={};try{a=JSON.parse(r.attrs||'{}');}catch(e){a={};}
  var IMGRE=/^(main_product_image_locator|other_product_image_locator_\d+)$/;
  var urls=Object.keys(a).filter(k=>IMGRE.test(k)).sort().map(k=>a[k]).filter(Boolean);
  if(!urls.length) urls=Object.keys(a).filter(k=>/image_locator/i.test(k)).map(k=>a[k]).filter(Boolean);
  return urls;
}
function _statusDot(r){
  var s=r.status||"";
  var col = s==="LIVE"?"#74e0a3" : (isHold(s)||s==="API_ERROR"||s==="ERROR")?"#ef9a9a"
          : s==="NEEDS_REVIEW"?"#e3b768" : s==="APPROVED"?"#74e0a3" : "#9aa3b2";
  return col;
}
// ---- GALLERY TILE ----
// Is this row confirmed live by AMAZON right now? Used to gate the live-only
// actions (Optimize, Pull live data). These used to key off r.status === "LIVE",
// i.e. the sheet's own claim -- so they appeared on rows Amazon had never seen and
// were missing from rows Amazon HAD published but whose sheet status was stale
// (e.g. still "SUBMITTED"). Returns false in the Drafts view, where the catalog was
// never fetched and we genuinely do not know.
function isAmazonLive(r){
  const sets = _liveCatSetsForCurrentView();
  if(!sets.liveGroupShown) return false;
  return isActuallyLive(r, sets.skus, sets.asins, true);
}

function card(r){
  const findings = [];
  if(r.notes && r.notes.trim()) findings.push(r.notes);
  if(r.comp_notes && r.comp_notes.trim()) findings.push(r.comp_notes);
  const issues = isHold(r.status) || r.ip_risk==="HIGH" || r.comp_risk==="HIGH" || r.comp_risk==="MEDIUM" || findings.length>0;
  const urls=_rowImages(r);
  const thumb = (urls&&urls.length)
    ? `<img src="${esc(urls[0])}" loading="lazy" onerror="this.style.display='none';this.parentNode.classList.add('noimg');this.parentNode.innerHTML='<i class=\\'ti ti-photo\\'></i>'">`
    : `<i class="ti ti-photo"></i>`;
  const selected = SELECTED.has(String(r.sku));
  const priceStr = r.price?`${CUR_SYMBOL}${esc(String(r.price).replace(/^[A-Z]{3}/,''))}`:'';
  const skuId=sid(r.sku);
  return `<div class="tile ${selected?'sel':''} ${issues?'flag':''}" data-sku="${esc(r.sku)}">
    <div class="tileimg pii-img ${(urls&&urls.length)?'':'noimg'}" onclick="openDrawer('${esc(r.sku)}')">
      ${thumb}
      <span class="tiledot" style="background:${_statusDot(r)}" title="${esc(r.status||'')}"></span>
      <input type="checkbox" class="tilesel" ${selected?'checked':''} onclick="event.stopPropagation()" onchange="toggleSelect('${esc(r.sku)}',this.checked)" title="Select">
      ${issues?'<span class="tileflag" title="Needs review"><i class="ti ti-alert-triangle"></i></span>':''}
      <button class="peek" title="Reveal this listing" onclick="event.stopPropagation();peekTile(this)"><i class="ti ti-eye"></i></button>
    </div>
    <div class="tilebody" onclick="openDrawer('${esc(r.sku)}')">
      <div class="tiletitle pii">${esc(r.title)||'<span class="cc">(no title)</span>'}</div>
      <div class="tilemeta">
        ${priceStr?`<span class="tileprice pii">${priceStr}</span>`:'<span></span>'}
        <span class="tilesku pii">${esc(r.sku)||''}</span>
      </div>
    </div>
    <div class="tileacts">
      <button class="ib" title="Approve" onclick="setStatus('${esc(r.sku)}','APPROVED',this)"><i class="ti ti-check"></i></button>
      <button class="ib gen" title="Image Studio (creative ideas, prompt &amp; image AI)" onclick="event.stopPropagation();openStudioSingle('${esc(r.sku)}')"><i class="ti ti-photo"></i></button>
      <button class="ib" title="Edit / details" onclick="openDrawer('${esc(r.sku)}')"><i class="ti ti-edit"></i></button>
      <button class="ib" title="✦ Auto-fix: Suggest → Apply → Preview loop until zero errors" style="color:#93c5fd" onclick="event.stopPropagation();autoFixLoop('${esc(r.sku)}')"><i class="ti ti-wand"></i></button>
      ${isAmazonLive(r) ? `<button class="ib" title="Optimize this live listing's copy — pulls it live from Amazon so you can rewrite &amp; push" style="color:#c8b6ff" onclick="event.stopPropagation();optimizeLive('${esc(r.asin||'')}','${esc(r.sku)}')"><i class="ti ti-sparkles"></i></button>` : ""}
      ${isAmazonLive(r) ? `<button class="ib" title="Pull this listing's REAL images from Amazon (main + every secondary image) into this row, replacing the generation-time ones" style="color:#9fe6bd" onclick="event.stopPropagation();pullLiveRow('${esc(r.sku)}',this)"><i class="ti ti-cloud-download"></i></button>` : ""}
      <button class="ib more" title="More" onclick="tileMenu(event,'${esc(r.sku)}',${r.row||0})"><i class="ti ti-dots"></i></button>
    </div>
  </div>`;
}

// ---- DRAWER: full editor for one listing ----
function _marketIsUS(){
  try{ return String((typeof WS_MARKET!=="undefined"&&WS_MARKET)||(CUR_ACCOUNT&&CUR_ACCOUNT.marketplace)||"").toUpperCase()==="US"; }
  catch(e){ return false; }
}
function _stripUKforUS(s){
  // Old rows were generated before compliance became marketplace-aware, so their
  // saved notes can carry UK wording (UKCA, BS 1363, UK/EU dangerous goods) even
  // on a US listing. When the active marketplace is US, rewrite those phrases at
  // DISPLAY time so the flag isn't misleading. (Does not change stored data.)
  if(!_marketIsUS()) return s;
  return String(s)
    .replace(/UK\/EU dangerous goods shipping regulations/gi, "US/international dangerous goods shipping regulations")
    .replace(/\bUKCA\b[^.;|]*/gi, "")
    .replace(/BS\s?1363[^.;|]*/gi, "")
    .replace(/UK Batteries Regulations[^.;|]*/gi, "")
    .replace(/\bWEEE\b[^.;|]*/gi, "")
    .replace(/for (the )?UK market/gi, "for the US market")
    .replace(/\s{2,}/g," ").trim();
}
function formatFindings(findings){
  if(!findings || !findings.length) return "A note is set, but no specific detail was recorded.";
  // Notes may already contain HTML entities (e.g. &#39; for apostrophes) if a
  // previous run stored them escaped. Decode first so splitting + display work.
  const deEntity = (s)=> String(s)
    .replace(/&#39;/g,"'").replace(/&apos;/g,"'").replace(/&quot;/g,'"')
    .replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">");
  findings = findings.map(f=>_stripUKforUS(deEntity(f)));
  const joined = findings.join(" ");
  // If this looks like an API preview error list, split into individual rows so
  // each missing/invalid field is its own line item instead of a wall of text.
  if(/required but missing|\[E\]|\[W\]|API (PREVIEW|SUBMIT)/i.test(joined)){
    // strip the "API PREVIEW - N error(s):" prefix, then split on "; "
    const body = joined.replace(/API (PREVIEW|SUBMIT)[^:]*:\s*/i, "");
    const items = body.split(/;\s*/).map(s=>s.trim()).filter(Boolean);
    if(items.length){
      return '<div class="errlist">' + items.map(it=>{
        const isErr = /^\[E\]/.test(it) || /required|invalid|missing/i.test(it);
        const txt = it.replace(/^\[[EW]\]\s*/,"");
        // pull the field name (first token) to bold it
        const m = txt.match(/^(\S+)\s+(.*)$/);
        const field = m? m[1] : "";
        const rest  = m? m[2] : txt;
        return '<div class="erritem '+(isErr?'e':'w')+'"><span class="errfield">'+esc(field)+'</span> '+esc(rest)+'</div>';
      }).join("") + '</div>';
    }
  }
  // not an API error list -> show as-is (compliance/IP notes), escaped + newlines
  return findings.map(f=>esc(f)).join("\n");
}
function drawerContent(r){
  const findings = [];
  if(r.notes && r.notes.trim()) findings.push(r.notes);
  if(r.comp_notes && r.comp_notes.trim()) findings.push(r.comp_notes);
  const issues = isHold(r.status) || r.ip_risk==="HIGH" || r.comp_risk==="HIGH" || r.comp_risk==="MEDIUM" || findings.length>0;
  const risks = [];
  if(r.ip_risk==="HIGH") risks.push('<span class="risk hi">IP: HIGH</span>');
  if(r.comp_risk==="HIGH") risks.push('<span class="risk hi">Compliance: HIGH</span>');
  else if(r.comp_risk==="MEDIUM") risks.push('<span class="risk med">Compliance: MED</span>');
  let reason = "";
  if(issues){
    if(r.comp_risk==="HIGH") reason="Compliance flag";
    else if(r.ip_risk&&r.ip_risk!=="") reason="IP review";
    else if(r.comp_risk==="MEDIUM") reason="Minor compliance note";
    else reason="Review note";
  }
  // Is this an ACTUAL blocking problem, or just an informational compliance note
  // (e.g. "lithium battery -> these docs may be requested")? A real problem = an
  // API error/hold or an IP risk. A compliance note on an already-submitted/live
  // listing is informational, so show it ORANGE, not alarming red.
  const _allNotes = String((r.notes||"")+" "+(r.comp_notes||""));
  const _hasApiError = /\[E\]|required but missing|API (PREVIEW|SUBMIT)[^:]*:\s*\d+\s*error|invalid/i.test(_allNotes);
  const _isHoldOrErr = (typeof isHold==="function" && isHold(r.status)) ||
                       String(r.status||"").toUpperCase().indexOf("ERROR")>=0;
  const _ipProblem = r.ip_risk==="HIGH";
  const _informational = issues && !_hasApiError && !_isHoldOrErr && !_ipProblem;
  if(_informational){
    reason = "Compliance info — documents Amazon may request";
  }
  const _sumClass = _informational ? "findsum info" : "findsum bad";
  const _findClass = _informational ? "findings info" : "findings";
  const statusBlock = issues
    ? `<details class="findingsbox" open><summary class="${_sumClass}">\u2139 ${esc(reason)}</summary>
        <div class="${_findClass}">${formatFindings(findings)}</div>
        <button class="linkbtn" style="margin-top:6px" onclick="locateFlags('${esc(r.sku)}',this)">\ud83d\udd0d Locate flagged terms</button>
        <div class="locout" id="loc_${sid(r.sku)}"></div></details>`
    : `<div class="findsum good">\u2713 No issues detected</div>`;
  const urls=_rowImages(r);
  const priceStr = r.price?`${CUR_SYMBOL}${esc(String(r.price).replace(/^[A-Z]{3}/,''))}`:'';
  const hero = (urls&&urls.length)?`<div class="heroimg"><img src="${esc(urls[0])}" loading="lazy" onerror="this.parentNode.style.display='none'"></div>`:'';
  return `
    <div class="dwhead">
      <div class="dwtop">
        <span class="badge ${badgeClass(r.status)}">${esc(r.status||'\u2014')}</span>
        ${risks.join("")}
        <span class="spacer"></span>
        <button class="ib" onclick="closeDrawer()" title="Close"><i class="ti ti-x"></i></button>
      </div>
      <div class="dwtitle">${esc(r.title)||'<span class="cc">(no title)</span>'}</div>
      ${r.item_highlights?`<div class="dwhl"><span class="dwhl-lbl">Highlights</span> ${esc(r.item_highlights)}</div>`:''}
      <div class="lmeta">
        <span class="lsku">${esc(r.sku)||'\u2014'}</span>
        ${priceStr?`<span class="lprice">${priceStr}</span>`:''}
        ${r.profit?`<span class="cc">profit ${CUR_SYMBOL}${esc(String(r.profit).replace(/^[A-Z]{3}/,''))}</span>`:''}
      </div>
      <div class="dwactions">
        <button class="suggestbtn" onclick="suggestFields('${esc(r.sku)}')"><i class="ti ti-wand"></i> Suggest missing fields</button>
        <button class="suggestbtn" onclick="refreshSchemaFor('${esc(r.sku)}')" title="Re-fetch Amazon's allowed values so the dropdowns show the latest options. This does NOT pull your listing's data — use 'Pull live data from Amazon' for that."><i class="ti ti-refresh"></i> Refresh dropdown options</button>
        ${isAmazonLive(r) ? `<button class="suggestbtn" style="background:#123021;border-color:#2c5c3f;color:#9fe6bd" onclick="pullLiveRow('${esc(r.sku)}',this)" title="Fetch this listing's real IMAGES from Amazon — the main image and every secondary image — and replace the generation-time ones on this row. Does not pull A+ content, title, bullets or price."><i class="ti ti-cloud-download"></i> Pull live images from Amazon</button>` : ""}
        <label class="minlbl" title="Send only the fields Amazon strictly requires (plus price/title/etc.). Create the listing now, add the rest in Seller Central. Note: lithium-battery products still require their safety fields."><input type="checkbox" onchange="toggleMinimal(this)" ${MINIMAL_MODE_ON?'checked':''}> Minimal mode (required fields only)</label>
        <button class="genmain" onclick="openStudioSingle('${esc(r.sku)}')"><i class="ti ti-photo"></i> Image Studio</button>
        <button class="pushimg" onclick="pushImageLive('${esc(r.sku)}',this)" title="Send the current main image to the LIVE Amazon listing (updates just the image, no full resubmit)"><i class="ti ti-cloud-upload"></i> Push image to live</button>
        <label class="pushimg" style="cursor:pointer" title="Upload a clean main image from your computer. It's hosted publicly so Amazon can fetch it, then set as this listing's main image. Preview/Submit sends it."><i class="ti ti-photo-up"></i> Upload main image<input type="file" accept="image/*" style="display:none" onchange="uploadMainImage('${esc(r.sku)}',this)"></label>
        <button class="ok" onclick="setStatus('${esc(r.sku)}','APPROVED',this)">Approve</button>
        <button class="prev1" onclick="previewOne('${esc(r.sku)}')" title="Preview this listing against Amazon (no changes sent)"><i class="ti ti-eye"></i> Preview</button>
        <button class="prev1" style="background:#fff;color:#111;border-color:#fff" onclick="autoFixLoop('${esc(r.sku)}')" title="Auto-loop: Suggest → Apply → Preview. Repeats until zero errors, or stops if progress stalls (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>
        ${window.WS_READONLY ? `<span class="cc" style="font-size:11.5px;align-self:center"><i class="ti ti-lock"></i> Read-only workspace — cannot publish</span>` : `<button class="submit1" onclick="submitOne('${esc(r.sku)}')" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit this</button>`}
        ${isAmazonLive(r) ? `<button class="prev1" style="background:#3a2f5c;color:#e9ddff;border-color:#6b5b9a" onclick="optimizeLive('${esc(r.asin||'')}','${esc(r.sku)}')" title="Optimize this LIVE listing's copy — pulls it from Amazon so you can rewrite &amp; push the update"><i class="ti ti-sparkles"></i> Optimize copy</button>` : ""}
        <button class="hold" onclick="setStatus('${esc(r.sku)}','NEEDS_REVIEW',this)">Hold</button>
        <button class="askthis" onclick="askAbout('${esc(r.sku)}')">\u2726 Ask Claude</button>
        ${r.source?`<a class="srcbtn" href="${esc(r.source)}" target="_blank" rel="noopener">source \u2197</a>`:''}
        <button class="del" onclick="delRow('${esc(r.sku)}',${r.row||0},this)">Delete</button>
      </div>
      <div id="suggestbox_${sid(r.sku)}" class="suggestbox"></div>
      <div id="runpanel_${sid(r.sku)}" class="runpanel" style="display:none">
        <div class="runhead"><span class="runtitle"></span><button class="runclose" onclick="window.RUN_STREAMING=false;this.closest('.runpanel').style.display='none'">✕</button></div>
        <div class="runverdict"></div>
        <details class="runlogwrap"><summary>Show the full Amazon response log</summary><pre class="runlog"></pre></details>
      </div>
    </div>
    ${hero}
    ${statusBlock}
    <div id="fulldata_${sid(r.sku)}">${fullData(r)}</div>`;
}

function openDrawer(sku, jumpGen){
  const r=ROWS.find(x=>String(x.sku)===String(sku));
  if(!r) return;
  DRAWER_SKU=sku;
  const dw=document.getElementById("drawer");
  const body=document.getElementById("drawerbody");
  body.innerHTML=drawerContent(r);
  dw.classList.add("open");
  document.getElementById("drawerscrim").classList.add("open");
  dw.scrollTop=0;
  // If this product type's schema (allowed values + nested sub-fields like ghs /
  // battery) isn't loaded yet, fetch it then re-render -- otherwise required
  // nested fields render as flat boxes (or not at all) and you can't see the
  // dropdowns Amazon needs. This is what made flagged fields invisible.
  if(r.product_type && typeof loadSchemas==="function" && !(SCHEMAS[r.product_type] && (SCHEMAS[r.product_type].attrs||[]).length)){
    loadSchemas([r.product_type], false, rowMkt(r)).then(()=>{
      if(DRAWER_SKU===sku){ body.innerHTML=drawerContent(r); var sv=sid(sku);
        setTimeout(function(){ if(typeof bulletMeter==='function') bulletMeter(); }, 60); }
    }).catch(()=>{});
  }
  // populate the (always-visible) image panel's model dropdowns + run the
  // connection check, once the drawer is in place
  var sidv=sid(sku);
  setTimeout(function(){ initGenPanel(sidv); if(typeof initMilesPanel==='function') initMilesPanel(sidv); if(typeof bulletMeter==='function') bulletMeter(); }, 120);
  if(jumpGen){
    setTimeout(function(){
      var anchor=document.getElementById('genimg_'+sidv);
      if(anchor && dw){ dw.scrollTo({top: anchor.offsetTop - 12, behavior:'smooth'}); }
    }, 280);
  }
}
// Shared OpenRouter connection tester: NEVER hangs (12s timeout) and writes a
// clear, specific status into the given diag element so the user knows exactly
// what's wrong (missing key / bad key / discovery / network / app unreachable).
async function _orTestInto(diag){
  if(!diag) return null;
  diag.className='gendiag'; diag.textContent='Checking OpenRouter connection…';
  let t=null;
  try{
    const ctrl=new AbortController();
    const timer=setTimeout(()=>ctrl.abort(), 12000);   // 12s hard cap, no infinite hang
    let resp;
    try{ resp=await fetch('/ai/test',{signal:ctrl.signal}); }
    finally{ clearTimeout(timer); }
    t=await resp.json();
  }catch(e){
    diag.className='gendiag bad';
    diag.textContent = (e&&e.name==='AbortError')
      ? '\u2717 OpenRouter check timed out (12s). Likely a slow or blocked connection to openrouter.ai — check your internet/VPN, then reopen this panel.'
      : '\u2717 Could not reach the app to test OpenRouter (is the app still running?).';
    return null;
  }
  if(t&&t.ok){
    diag.className='gendiag ok';
    diag.textContent='\u2713 OpenRouter ready \u2014 image model: '+(t.image_model||'?')+' ('+(t.image_count||0)+' image models available)';
  } else {
    diag.className='gendiag bad';
    const stage=(t&&t.stage)||'';
    const base='\u2717 '+((t&&t.error)||'OpenRouter not ready');
    const tip = stage==='key'     ? ' \u2014 add your real openrouter_api_key to config.json and restart the app.'
              : stage==='discover'? ' \u2014 the key was found but OpenRouter rejected it or returned no models. Check the key is valid/active at openrouter.ai/keys.'
              :                     ' \u2014 reopen this panel to retry.';
    diag.textContent=base+tip;
  }
  return t;
}
async function initGenPanel(sidv){
  var s=await loadAISettings();
  // If the cached settings have no image models yet (discovery hadn't finished
  // on first page load), force a fresh discovery so the dropdowns populate.
  if(!s || !s.ok || !(s.image_models && s.image_models.length)){
    try{
      AISET=null;
      s=await (await fetch('/ai/settings?refresh=1')).json();
      AISET=s;
    }catch(e){}
  }
  if(s&&s.ok){
    fillModelSelect(document.getElementById('gentai_'+sidv), s.text_models, s.select.prompt_enhance);
    fillModelSelect(document.getElementById('geniai_'+sidv), s.image_models, s.select.image_generate);
  }
  var diag=document.getElementById('gendiag_'+sidv);
  await _orTestInto(diag);
}
function closeDrawer(){
  DRAWER_SKU=null;
  window.RUN_STREAMING=false;
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  document.getElementById("drawer").classList.remove("open");
  document.getElementById("drawerscrim").classList.remove("open");
}
function tileMenu(ev, sku, row){
  ev.stopPropagation();
  // simple context menu
  closeTileMenu();
  const m=document.createElement("div"); m.className="tilemenu"; m.id="tilemenu";
  m.innerHTML=`
    <button onclick="setStatus('${esc(sku)}','NEEDS_REVIEW',this);closeTileMenu()"><i class="ti ti-player-pause"></i> Hold</button>
    <button onclick="askAbout('${esc(sku)}');closeTileMenu()"><i class="ti ti-message-circle"></i> Ask Claude</button>
    <button onclick="openDrawer('${esc(sku)}');closeTileMenu()"><i class="ti ti-edit"></i> Edit details</button>
    <button class="danger" onclick="delRow('${esc(sku)}',${row},this);closeTileMenu()"><i class="ti ti-trash"></i> Delete</button>`;
  document.body.appendChild(m);
  const rect=ev.target.closest("button").getBoundingClientRect();
  m.style.top=(rect.bottom+4)+"px";
  m.style.left=Math.min(rect.left, window.innerWidth-180)+"px";
  setTimeout(()=>document.addEventListener("click",closeTileMenu,{once:true}),0);
}
function closeTileMenu(){ const m=document.getElementById("tilemenu"); if(m) m.remove(); }
function openGenPanelInDrawer(sku){
  try{
    var sidv=sid(sku);
    var dw=document.getElementById("drawer");
    var anchor=document.getElementById('genimg_'+sidv);
    if(!anchor){ toast("Image panel not found \u2014 try reopening the drawer"); return; }
    if(dw){ dw.scrollTo({top: anchor.offsetTop - 12, behavior:'smooth'}); }
    initGenPanel(sidv);
  }catch(e){ toast("Could not open image panel: "+e); }
}
function openGenFromHead(sku){ openStudioSingle(sku); }

function _fileToDataURL(file){
  return new Promise(function(res,rej){
    var fr=new FileReader(); fr.onload=function(){res(fr.result);}; fr.onerror=rej; fr.readAsDataURL(file);
  });
}
async function uploadRef(input, sku, sidv){
  var file=input.files&&input.files[0]; if(!file) return;
  var st=document.getElementById('genstatus_'+sidv); if(st) st.textContent='Uploading reference…';
  try{
    var dataUrl=await _fileToDataURL(file);
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,data:dataUrl,name:file.name,kind:'ref'})});
    var j=await res.json();
    if(!j.ok){ if(st) st.textContent='Upload failed: '+(j.error||''); return; }
    var fld=document.getElementById('genraw_'+sidv); if(fld) fld.value=j.url;
    if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 Reference uploaded \u2014 saved to this SKU\u2019s media folder.</span>';
  }catch(e){ if(st) st.textContent='Upload error: '+e; }
}

