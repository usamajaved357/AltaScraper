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

// A row is "actually live" if its status is LIVE, OR its SKU/ASIN already
// exists in the Amazon live catalog. This must return the SAME answer whether
// called by render() (for grouping) or summary() (for counting) -- otherwise
// the two drift and the top-bar shows a HOLD count for rows that are actually
// live on Amazon (a leftover pre-submit status the sheet never updated).
function isActuallyLive(r, liveCatSkus, liveCatAsins, liveGroupShown){
  const norm = v => String(v||"").trim().toUpperCase();
  if(norm(r.status)==="LIVE") return true;
  if(!liveGroupShown) return false;   // don't reclassify in views without a Live group
  const s=norm(r.sku), a=norm(r.asin);
  if(s && liveCatSkus.has(s)) return true;
  if(a && liveCatAsins.has(a)) return true;
  return false;
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
        <button class="suggestbtn" onclick="refreshSchemaFor('${esc(r.sku)}')" title="Re-fetch Amazon's allowed values so dropdowns show the latest options"><i class="ti ti-refresh"></i> Refresh Amazon values</button>
        <label class="minlbl" title="Send only the fields Amazon strictly requires (plus price/title/etc.). Create the listing now, add the rest in Seller Central. Note: lithium-battery products still require their safety fields."><input type="checkbox" onchange="toggleMinimal(this)" ${MINIMAL_MODE_ON?'checked':''}> Minimal mode (required fields only)</label>
        <button class="genmain" onclick="openStudioSingle('${esc(r.sku)}')"><i class="ti ti-photo"></i> Image Studio</button>
        <button class="pushimg" onclick="pushImageLive('${esc(r.sku)}',this)" title="Send the current main image to the LIVE Amazon listing (updates just the image, no full resubmit)"><i class="ti ti-cloud-upload"></i> Push image to live</button>
        <label class="pushimg" style="cursor:pointer" title="Upload a clean main image from your computer. It's hosted publicly so Amazon can fetch it, then set as this listing's main image. Preview/Submit sends it."><i class="ti ti-photo-up"></i> Upload main image<input type="file" accept="image/*" style="display:none" onchange="uploadMainImage('${esc(r.sku)}',this)"></label>
        <button class="ok" onclick="setStatus('${esc(r.sku)}','APPROVED',this)">Approve</button>
        <button class="prev1" onclick="previewOne('${esc(r.sku)}')" title="Preview this listing against Amazon (no changes sent)"><i class="ti ti-eye"></i> Preview</button>
        <button class="prev1" style="background:#fff;color:#111;border-color:#fff" onclick="autoFixLoop('${esc(r.sku)}')" title="Auto-loop: Suggest → Apply → Preview. Repeats until zero errors, or stops if progress stalls (max 8 rounds)."><i class="ti ti-wand"></i> Auto-fix</button>
        <button class="submit1" onclick="submitOne('${esc(r.sku)}')" title="Publish ONLY this listing live"><i class="ti ti-upload"></i> Submit this</button>
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

// ---- AI sourced suggestions for missing fields ----
function _srcBadge(src){
  var map={
    'eBay':['#10301f','#74e0a3','eBay source'],
    'Amazon competitor (SP-API)':['#15233a','#9cc1ff','Amazon competitor'],
    'AI knowledge':['#2a2440','#c8b6ff','AI knowledge'],
    'AI inference':['#2e2510','#e3b768','AI inference'],
    'none':['#2e1414','#ef9a9a','no source']
  };
  var m=map[src]||map['AI inference'];
  return '<span class="srcbadge" style="background:'+m[0]+';color:'+m[1]+'">'+m[2]+'</span>';
}
function _confBadge(c){
  if(!c) return '';
  var col=c==='high'?'#7fd99a':(c==='medium'?'#e3b768':'#9aa3b2');
  return '<span class="confbadge" style="color:'+col+'">'+esc(c)+'</span>';
}
async function suggestFields(sku){
  var box=document.getElementById('suggestbox_'+sid(sku));
  if(!box) return;
  box.innerHTML='<div class="gendiag"><span class="genspin"></span> Checking eBay \u2192 Amazon competitor \u2192 search \u2192 AI for the missing fields\u2026</div>';
  try{
    var res=await fetch('/suggest',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku})});
    var j=await res.json();
    if(!j.ok){ box.innerHTML='<div class="gendiag bad">\u2717 '+esc(j.error||'failed')+'</div>'; return; }
    if(!j.suggestions || !j.suggestions.length){
      // The /suggest endpoint only knows fields Amazon flagged in a PRIOR Preview
      // (read from Notes). But the schema also has its own required list, and a
      // required field can be EMPTY while unflagged -- that's the field with a
      // star. Cross-check the schema so the message doesn't contradict the stars.
      var _emptyReq = [];
      try{
        var r=(ROWS||[]).find(function(x){return String(x.sku)===String(sku);});
        var pt=(r&&r.product_type)||"";
        var sc=SCHEMAS[pt]||{}; var reqL=sc.req||[];
        var a=(r&&r.attributes)||{};
        reqL.forEach(function(k){
          // consider the field "filled" if it has a value directly OR any of its
          // dotted sub-keys has a value (nested fields like dangerous goods).
          var direct=(k in a)&&String(a[k]).trim()!=="";
          var nested=Object.keys(a).some(function(kk){return kk.indexOf(k+".")===0 && String(a[kk]).trim()!=="";});
          if(!direct && !nested) _emptyReq.push(k);
        });
      }catch(e){}
      if(_emptyReq.length){
        box.innerHTML='<div class="gendiag" style="color:#e3b768">\u2605 '+_emptyReq.length+' required field'+(_emptyReq.length>1?'s':'')+' still need a value (marked with \u2605 below): <b>'+_emptyReq.map(function(x){return esc(x.replace(/_/g," "));}).join(", ")+'</b>.<br><span class="cc">Amazon hasn\u2019t flagged these yet \u2014 fill them now, or click Preview API to confirm exactly what\u2019s required.</span></div>';
      } else {
        box.innerHTML='<div class="gendiag ok">\u2713 No missing required fields detected. (If Amazon flagged some, click Preview API first so they\u2019re known.)</div>';
      }
      return;
    }
    var rows=j.suggestions.map(function(s){
      var sidv=sid(sku)+'__'+sid(s.field);
      if(s._code_owned){
        // Compliance field the app fills automatically on Preview -- show as an
        // info card with NO editable box and NO Apply button, so the user knows
        // it's handled and won't try to fill it by hand.
        return '<div class="sgrow applied" id="sg_'+sidv+'">'+
          '<div class="sghead"><span class="sgfield">'+esc(s.field)+'</span>'+
          '<span class="srcbadge" style="background:#13371f;border-color:#1f7a3a;color:#7fdca0">auto-filled on Preview</span></div>'+
          (s.note?'<div class="sgnote">'+esc(s.note)+'</div>':'')+
        '</div>';
      }
      return '<div class="sgrow" id="sg_'+sidv+'">'+
        '<div class="sghead"><span class="sgfield">'+esc(s.field)+'</span>'+_srcBadge(s.source)+_confBadge(s.confidence)+'</div>'+
        '<textarea class="ed sgval" id="sgval_'+sidv+'">'+esc(s.value||'')+'</textarea>'+
        (s.note?'<div class="sgnote">'+esc(s.note)+'</div>':'')+
        '<div class="sgacts"><button class="sgapply" onclick="applySuggestion(\''+esc(sku)+'\',\''+esc(s.field)+'\',\''+sidv+'\')">Apply this</button></div>'+
      '</div>';
    }).join('');
    box.innerHTML='<div class="sgtop"><b>Suggested values</b> <span class="cc">each tagged with where it came from</span>'+
      '<button class="sgall" onclick="applyAllSuggestions(\''+esc(sku)+'\')">Apply all</button></div>'+rows;
  }catch(e){ box.innerHTML='<div class="gendiag bad">\u2717 '+esc(String(e))+'</div>'; }
}
async function applySuggestion(sku, field, sidv){
  var ta=document.getElementById('sgval_'+sidv);
  var val=ta?ta.value:'';
  var btn=document.querySelector('#sg_'+sidv+' .sgapply');
  if(btn){ btn.disabled=true; btn.textContent='Applying…'; }
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:field,value:val})});
    var rowEl=document.getElementById('sg_'+sidv);
    if(rowEl){ rowEl.classList.add('applied'); }
    if(btn){ btn.textContent='\u2713 Applied'; }
    // reflect immediately in the open drawer so scrolling down shows the value
    // (single-apply previously only saved server-side and never refreshed UI).
    try{
      // 1) update the in-memory row so the value persists in the UI model
      var r=(ROWS||[]).find(function(x){return String(x.sku)===String(sku);});
      if(r){ r.attributes=r.attributes||{}; r.attributes[field]=val; }
      // 2) re-render the open drawer's full-data section so the filled value is
      //    visible when you scroll down (single-apply used to never refresh it).
      if(DRAWER_SKU && String(DRAWER_SKU)===String(sku) && typeof fullData==='function'){
        var fr=(ROWS||[]).find(function(x){return String(x.sku)===String(DRAWER_SKU);});
        var host=document.getElementById('fulldata_'+sid(DRAWER_SKU));
        if(host && fr){ host.innerHTML=fullData(fr); }
      }
    }catch(e){}
  }catch(e){ if(btn){ btn.disabled=false; btn.textContent='Apply this'; } toast('Could not apply: '+e); }
}
async function applyAllSuggestions(sku){
  var box=document.getElementById('suggestbox_'+sid(sku));
  if(!box) return;
  var rows=box.querySelectorAll('.sgrow:not(.applied)');
  for(var i=0;i<rows.length;i++){
    var id=rows[i].id.replace('sg_','');
    var field=rows[i].querySelector('.sgfield').textContent;
    await applySuggestion(sku, field, id);
  }
  toast('Applied all suggestions');
  loadRows();
}

// ============================================================================
// AUTO-FIX LOOP: Suggest → Apply → Preview → check errors → repeat until clean
// or progress stalls. Max 8 rounds. Reports back through a floating status box.
//
// TRACE CAPTURE: every round records the AI's suggestions (field + value +
// source + confidence), which values were actually applied to the sheet, the
// full Amazon error banner (verbatim [E] lines), and the changed error set.
// A "Copy trace" button dumps the whole diagnostic to the clipboard as a
// pasteable block for handing to Claude in this chat -- so you can share the
// exact sequence of what happened per round instead of reconstructing it.
// ============================================================================
window.AUTOFIX_STATE = null;

async function autoFixLoop(sku){
  if(!sku) return;
  if(window.AUTOFIX_STATE && window.AUTOFIX_STATE.sku === sku){
    toast('Auto-fix already running for this SKU'); return;
  }
  const MAX_ROUNDS = 8;
  const state = {sku:sku, round:0, prevErrors:null, stopped:false, cancelled:false,
                  trace: [], startedAt: new Date().toISOString()};
  window.AUTOFIX_STATE = state;
  window._AUTOFIX_LAST_STATE = state;   // set NOW so bulkAutoFix can read it back regardless of which panel path we take

  // If we're inside a bulk batch, DON'T create our own panel -- the batch panel
  // is already on screen and using the same DOM slot ('autofix_panel'). We
  // still capture the full trace in `state` so the batch panel can render it,
  // but skip the per-SKU floating box to avoid destroying the batch UI.
  const insideBulk = !!(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done);
  const panel = insideBulk ? _autoFixNullPanel() : _autoFixPanel(sku, state);
  if(!insideBulk){
    panel.show('Auto-fix started for '+sku);
  }

  try{
    while(state.round < MAX_ROUNDS && !state.cancelled){
      state.round++;
      const roundEntry = {
        round: state.round,
        started_at: new Date().toISOString(),
        suggestions: [],
        applied: [],
        skipped: [],
        preview_verdict: null,
        preview_error_fields: [],
        preview_raw_lines: [],
        diagnosis: '',
      };
      state.trace.push(roundEntry);
      panel.step('Round '+state.round+' of '+MAX_ROUNDS+' — asking AI for suggestions…');

      // --- 1. Get suggestions from AI ---
      let sugRes;
      try{
        sugRes = await fetch('/suggest',{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({sku:sku})});
        sugRes = await sugRes.json();
      }catch(e){
        roundEntry.diagnosis = '/suggest network error: '+String(e);
        panel.fail('Round '+state.round+': /suggest failed — see trace');
        panel.renderTrace();
        break;
      }
      if(!sugRes.ok){
        // If the error mentions "sku not found" it means the row isn't in the
        // current worksheet -- usually because the user switched account
        // workspaces (or the app was restarted) after ticking this SKU.
        // Explain that plainly so the trace tells the user what to fix.
        const errRaw = String(sugRes.error || 'no error field');
        const isMissing = /sku not found|not in.*view|not in.*sheet/i.test(errRaw);
        roundEntry.diagnosis = isMissing
          ? ('SKU not visible in current workspace. This usually means you switched '+
              'account workspaces (or the app restarted) after ticking this SKU. '+
              'Click into the correct account workspace first, then try again. '+
              '(Raw: '+errRaw+')')
          : ('/suggest returned ok=false: '+errRaw);
        panel.fail('Round '+state.round+': '+(isMissing ? 'SKU not in current workspace' : 'suggestion API error')+' — see trace');
        panel.renderTrace();
        break;
      }
      // Capture EVERY suggestion (both code_owned info cards and AI-fillable ones)
      // so the trace shows exactly what the system chose per field.
      roundEntry.suggestions = (sugRes.suggestions||[]).map(function(s){
        return {
          field: s.field, value: s.value || '', source: s.source || '',
          confidence: s.confidence || '', note: s.note || '',
          code_owned: !!s._code_owned,
        };
      });
      const suggestions = (sugRes.suggestions||[]).filter(function(s){ return !s._code_owned; });
      panel.step('Round '+state.round+': got '+suggestions.length+' AI suggestions ('+
                 (roundEntry.suggestions.length-suggestions.length)+' code-owned)');

      // --- 2. Apply each suggestion ---
      for(let i=0;i<suggestions.length;i++){
        const s = suggestions[i];
        if(!s.value){
          roundEntry.skipped.push({field:s.field, reason:'empty AI value'});
          continue;
        }
        try{
          const editRes = await fetch('/edit',{method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({sku:sku, target:'attr', key:s.field, value:s.value})});
          const editJson = await editRes.json();
          if(editJson.ok){
            roundEntry.applied.push({field:s.field, value:s.value, source:s.source});
          } else {
            const err = String(editJson.error || 'unknown');
            roundEntry.skipped.push({field:s.field, reason:'edit failed: '+err});
            // If the sheet says the SKU doesn't exist, all further edits in this
            // round WILL fail identically -- abort the loop immediately with a
            // clear diagnosis instead of grinding through every suggestion.
            if(/sku not found|not in.*sheet|not in.*view/i.test(err)){
              roundEntry.diagnosis = 'SKU not visible in current workspace at edit time. '+
                                      'The row was found by /suggest but had disappeared by /edit -- '+
                                      'this usually means you switched workspaces mid-run or a '+
                                      'concurrent submit moved the row. Click into the correct '+
                                      'account workspace and retry.';
              panel.fail('Round '+state.round+': SKU disappeared from workspace between /suggest and /edit — see trace');
              panel.renderTrace();
              // Break out of BOTH the inner apply loop and the outer round loop
              window._AUTOFIX_STOP = true;
              break;
            }
          }
        }catch(e){
          roundEntry.skipped.push({field:s.field, reason:'edit exception: '+String(e)});
        }
      }
      if(window._AUTOFIX_STOP){ window._AUTOFIX_STOP = false; break; }
      panel.step('Round '+state.round+': applied '+roundEntry.applied.length+
                 ' / skipped '+roundEntry.skipped.length);

      // Count code-owned suggestions: these DON'T get "applied" (nothing to
      // apply -- the generator fills them itself when Preview runs), but they
      // ARE progress. If the current round applied 0 AI values but flagged
      // code-owned fields exist, running Preview WILL fill them via the
      // generator's compliance block. So don't stop when the only work left
      // is code-owned -- Preview is what actually resolves those.
      const codeOwnedCount = roundEntry.suggestions.filter(function(s){ return s.code_owned; }).length;
      if(roundEntry.applied.length === 0 && codeOwnedCount === 0 && state.round > 1){
        roundEntry.diagnosis = 'Nothing new to apply after round 1 and no code-owned fields to fill. AI has no more suggestions.';
        panel.stop('Round '+state.round+': nothing new to apply. Stopping.');
        panel.renderTrace();
        break;
      }

      // --- 3. Run Preview and capture EVERY line ---
      panel.step('Round '+state.round+': running Preview…');
      const verdict = await _autoFixPreview(sku, panel, roundEntry);
      roundEntry.preview_verdict = verdict.kind;
      roundEntry.preview_error_fields = verdict.errorFields || [];
      roundEntry.preview_verdict_raw = verdict.raw || '';

      if(state.cancelled){ break; }

      // --- 4. Interpret verdict ---
      if(verdict.kind === 'ok_preview'){
        roundEntry.diagnosis = 'Amazon accepted the Preview. Ready to Submit.';
        panel.done('✓ Round '+state.round+': Amazon accepted Preview. Ready to Submit!');
        panel.renderTrace();
        loadRows();
        break;
      }

      if(verdict.kind === 'network' || verdict.kind === 'nocreds' ||
          verdict.kind === 'busy' || verdict.kind === 'timeout'){
        roundEntry.diagnosis = 'Environment issue ('+verdict.kind+') — not a listing problem.';
        panel.fail('Round '+state.round+': '+verdict.kind+' — see trace');
        panel.renderTrace();
        break;
      }

      if(verdict.kind === 'error'){
        const errKey = (verdict.errorFields||[]).slice().sort().join('|');
        roundEntry.diagnosis = 'Amazon flagged '+verdict.n+' error(s) on fields: '+
                                (verdict.errorFields||[]).join(', ');
        panel.step('Round '+state.round+': Amazon flagged '+verdict.n+' error(s) on: '+
                   (verdict.errorFields||[]).join(', '));
        if(state.prevErrors && state.prevErrors === errKey){
          roundEntry.diagnosis += ' — IDENTICAL to previous round, no progress.';
          panel.stop('Round '+state.round+': Same errors as last round. Auto-fix cannot resolve these. Stopped.');
          panel.renderTrace();
          break;
        }
        state.prevErrors = errKey;
        panel.renderTrace();   // incremental render so user sees progress
        continue;
      }

      roundEntry.diagnosis = 'Unclear outcome ('+verdict.kind+'). Stopped for safety.';
      panel.fail('Round '+state.round+': unclear outcome — see trace');
      panel.renderTrace();
      break;
    }
    if(state.round >= MAX_ROUNDS && !state.cancelled){
      panel.stop('Hit max rounds ('+MAX_ROUNDS+'). Stopped. Review trace to see the loop pattern.');
      panel.renderTrace();
    }
  } finally {
    window.AUTOFIX_STATE = null;
    // Skip the per-SKU sheet refresh when running inside a batch -- the batch
    // wrapper calls loadRows() once at the very end. Doing it per SKU would
    // hit /rows 20+ times in a bulk run.
    if(!(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done)){
      loadRows();
    }
  }
}

// Runs one Preview and returns a verdict object. Also appends every stream line
// to roundEntry.preview_raw_lines so the trace has the full Amazon response
// for that round.
function _autoFixPreview(sku, panel, roundEntry){
  return new Promise(function(resolve){
    const url = '/run/api?skus='+encodeURIComponent(sku)+_minParam();
    const es = new EventSource(url);
    let verdict = null;
    let errorFields = [];
    let sawStart = false;
    let done = false;
    function finish(v){
      if(done) return; done=true;
      try{ es.close(); }catch(e){}
      v.errorFields = errorFields;
      resolve(v);
    }
    es.onmessage = function(e){
      const d = e.data || '';
      if(panel) panel.log(d);
      if(roundEntry) roundEntry.preview_raw_lines.push(d);
      if(d.indexOf('[start]') === 0) sawStart = true;
      // parse [E] field markers -- track ALL, not just first-per-line, in case
      // multiple errors share one message
      const mm = d.match(/\[E\]\s*([a-z0-9_.]+)/g);
      if(mm){
        mm.forEach(function(x){
          const m2 = x.match(/\[E\]\s*([a-z0-9_.]+)/);
          if(m2 && errorFields.indexOf(m2[1]) < 0) errorFields.push(m2[1]);
        });
      }
      // detect final verdict lines
      if(d.indexOf(sku) >= 0){
        const low = d.toLowerCase();
        let m = d.match(/(\d+)\s+error\(s\)/i);
        if(m){ verdict = {kind:'error', n:parseInt(m[1]), raw:d}; }
        else if(low.indexOf('missing') >= 0 && low.indexOf('skip') >= 0){ verdict = {kind:'missing', raw:d}; }
        else if(low.indexOf('api_ready') >= 0 || low.indexOf('preview clean') >= 0){ verdict = {kind:'ok_preview', raw:d}; }
        else if(low.indexOf('api call failed') >= 0 || low.indexOf('api_error') >= 0){ verdict = {kind:'error', n:0, raw:d}; }
      }
      if(d.toLowerCase().indexOf('no seller_id') >= 0) verdict = {kind:'nocreds', raw:d};
      if(d.indexOf('[done]') === 0 || d.indexOf('[busy]') >= 0){
        if(d.indexOf('[busy]') >= 0 && !verdict) verdict = {kind:'busy', raw:d};
        finish(verdict || {kind:'unknown', raw:d});
      }
      if(/getaddrinfo failed|failed to resolve|nameresolutionerror/i.test(d)){
        verdict = {kind:'network', raw:d};
      }
    };
    es.onerror = function(){
      // EventSource fires onerror on server-side stream end too, so treat this
      // as "the stream is done"; use whatever verdict we've collected so far.
      if(!done) finish(verdict || {kind: sawStart ? 'unknown' : 'network', raw:'stream ended'});
    };
    setTimeout(function(){
      if(!done) finish(verdict || {kind:'timeout', raw:'exceeded 5 minutes'});
    }, 5*60*1000);
  });
}

// Build a plain-text trace of the whole loop, ready to paste to Claude.
function _autoFixTraceText(state){
  const lines = [];
  lines.push('=== AUTO-FIX TRACE ===');
  lines.push('SKU: '+state.sku);
  lines.push('Started: '+state.startedAt);
  lines.push('Rounds run: '+state.trace.length+' / '+8);
  lines.push('');
  state.trace.forEach(function(r){
    lines.push('---- ROUND '+r.round+' ('+r.started_at+') ----');
    lines.push('');
    lines.push('SUGGESTIONS FROM AI ('+r.suggestions.length+' total):');
    if(r.suggestions.length === 0){
      lines.push('  (none)');
    } else {
      r.suggestions.forEach(function(s){
        const tag = s.code_owned ? '[CODE-OWNED]' : '[AI]';
        lines.push('  '+tag+' '+s.field+' = '+JSON.stringify(s.value)+
                    '  (source: '+(s.source||'-')+', confidence: '+(s.confidence||'-')+')');
        if(s.note) lines.push('    note: '+s.note);
      });
    }
    lines.push('');
    lines.push('APPLIED TO SHEET ('+r.applied.length+'):');
    if(r.applied.length === 0){
      lines.push('  (none applied)');
    } else {
      r.applied.forEach(function(a){
        lines.push('  ✓ '+a.field+' = '+JSON.stringify(a.value)+'  (from: '+(a.source||'-')+')');
      });
    }
    if(r.skipped.length){
      lines.push('');
      lines.push('SKIPPED ('+r.skipped.length+'):');
      r.skipped.forEach(function(x){
        lines.push('  ✗ '+x.field+' — '+x.reason);
      });
    }
    lines.push('');
    lines.push('PREVIEW VERDICT: '+r.preview_verdict);
    if(r.preview_error_fields && r.preview_error_fields.length){
      lines.push('Amazon flagged ('+r.preview_error_fields.length+'): '+
                  r.preview_error_fields.join(', '));
    }
    lines.push('');
    lines.push('PREVIEW STREAM (full Amazon response, verbatim):');
    // Include EVERY raw line, not a filtered subset. Filtering was hiding
    // parser mismatches (e.g. verdict `unknown` with an empty filtered view
    // when the stream actually did contain success/error lines the parser
    // failed to recognise). The full stream lets us see what Amazon sent
    // vs what our parser did with it, without which "unknown outcome"
    // diagnoses are un-debuggable.
    const raw_all = r.preview_raw_lines || [];
    if(raw_all.length){
      raw_all.forEach(function(x){ lines.push('  | '+x); });
    } else {
      lines.push('  (no stream lines received)');
    }
    lines.push('');
    if(r.diagnosis){
      lines.push('DIAGNOSIS: '+r.diagnosis);
      lines.push('');
    }
  });
  lines.push('=== END TRACE ===');
  return lines.join('\n');
}

async function _autoFixCopyTrace(){
  const state = window._AUTOFIX_LAST_STATE || window.AUTOFIX_STATE;
  if(!state){ toast('No auto-fix trace to copy'); return; }
  const text = _autoFixTraceText(state);
  try{
    await navigator.clipboard.writeText(text);
    toast('Trace copied — paste into Claude chat');
  }catch(e){
    // Clipboard API can fail in non-secure contexts; fall back to a prompt
    const w = window.open('', '_blank', 'width=700,height=500');
    if(w){
      w.document.title = 'Auto-fix trace';
      w.document.body.innerHTML = '<pre style="font:12px ui-monospace,Consolas,monospace;padding:12px;white-space:pre-wrap">'+
        text.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</pre>';
    } else {
      prompt('Copy the trace below:', text);
    }
  }
}

// A no-op panel used when autoFixLoop runs inside a bulk batch. The batch has
// its own panel; we just need the API surface (show/step/log/etc.) so
// autoFixLoop's calls are harmless.
function _autoFixNullPanel(){
  const noop = function(){};
  return {show:noop, step:noop, log:noop, done:noop, stop:noop, fail:noop, renderTrace:noop};
}

// Floating progress panel with an in-panel trace view + Copy button
function _autoFixPanel(sku, state){
  let el = document.getElementById('autofix_panel');
  if(el){ el.remove(); }
  el = document.createElement('div');
  el.id = 'autofix_panel';
  el.style.cssText = 'position:fixed;bottom:20px;right:20px;width:560px;max-height:80vh;'+
    'background:#141b2b;border:1px solid #3b4d70;border-radius:10px;padding:12px;'+
    'box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:9999;font-size:12px;color:#e8eaed;'+
    'display:flex;flex-direction:column;gap:8px';
  el.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;font-weight:600">'+
      '<span>✦ Auto-fix: '+esc(sku)+'</span>'+
      '<div style="display:flex;gap:8px;align-items:center">'+
        '<button id="autofix_copy" onclick="_autoFixCopyTrace()" '+
          'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
          '📋 Copy trace</button>'+
        '<button onclick="if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;this.parentElement.parentElement.parentElement.remove()" '+
        'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px">✕</button>'+
      '</div>'+
    '</div>'+
    '<div id="autofix_status" style="color:#9cc1ff"></div>'+
    '<div style="display:flex;gap:6px;font-size:10px">'+
      '<button onclick="document.getElementById(\'autofix_traceview\').style.display=\'none\';document.getElementById(\'autofix_log\').style.display=\'block\'" '+
        'style="background:#0d1220;border:1px solid #263145;color:#e8eaed;padding:3px 8px;border-radius:4px;cursor:pointer">Live log</button>'+
      '<button onclick="document.getElementById(\'autofix_log\').style.display=\'none\';document.getElementById(\'autofix_traceview\').style.display=\'block\'" '+
        'style="background:#0d1220;border:1px solid #263145;color:#e8eaed;padding:3px 8px;border-radius:4px;cursor:pointer">Round-by-round trace</button>'+
    '</div>'+
    '<div id="autofix_log" style="background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:280px;overflow:auto;flex:1"></div>'+
    '<div id="autofix_traceview" style="display:none;background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:280px;overflow:auto;flex:1;white-space:pre-wrap"></div>';
  document.body.appendChild(el);
  window._AUTOFIX_LAST_STATE = state;   // keep after the loop ends so Copy still works
  return {
    show: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    step: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    log: function(line){
      const l = document.getElementById('autofix_log');
      if(l){ l.textContent += line+'\n'; l.scrollTop = l.scrollHeight; }
    },
    done: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#74e0a3">'+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#e3b768">⚠ '+esc(msg)+'</span>';
    },
    fail: function(msg){
      const s = document.getElementById('autofix_status');
      if(s) s.innerHTML = '<span style="color:#e0696b">✗ '+esc(msg)+'</span>';
    },
    renderTrace: function(){
      const t = document.getElementById('autofix_traceview');
      if(t) t.textContent = _autoFixTraceText(state);
    },
  };
}

// ============================================================================
// BULK AUTO-FIX: run autoFixLoop sequentially across every selected SKU.
// Sequential (not parallel) because each Preview call hits SP-API and Amazon
// rate-limits per-seller; running 20 in parallel would trip 429s and slow
// everything down. A shared trace records every SKU's rounds so one Copy
// button gives you the whole batch's diagnostic to paste to Claude.
// ============================================================================
window.BULK_AUTOFIX = null;

async function bulkAutoFix(){
  const skus = selectedSkus();
  if(!skus.length){ toast("Nothing selected — tick some listings first"); return; }
  if(window.BULK_AUTOFIX && !window.BULK_AUTOFIX.done){
    toast("A batch auto-fix is already running"); return;
  }

  // PRE-FLIGHT: verify every selected SKU is actually in the current workspace.
  // The batch UI persists SELECTED across page-loads and Flask restarts, so it's
  // possible to tick SKUs on Account A, switch to Account B (or restart Flask
  // which resets active_account to default), and end up asking Amazon about
  // rows that aren't visible to the current worksheet. Without this check the
  // /suggest and /edit endpoints just 404 with cryptic 'sku not found in
  // current view' messages -- the batch trace shows those but doesn't explain
  // WHY, which wastes the user's time.
  //
  // The current view rows are already loaded into ROWS as of the last
  // loadRows() call. Cross-check locally before hitting the network.
  const inView = new Set((ROWS || []).map(r => String(r.sku || "")));
  const missing = skus.filter(s => !inView.has(String(s)));
  if(missing.length){
    const inViewCount = skus.length - missing.length;
    const msg = "⚠ "+missing.length+" of "+skus.length+" selected SKU(s) are NOT in the current workspace view:\n\n" +
                 missing.slice(0, 10).join("\n") +
                 (missing.length > 10 ? "\n  ...and "+(missing.length-10)+" more" : "") +
                 "\n\nThis usually means you switched account workspaces (or the app restarted) after ticking them. " +
                 "The auto-fix loop can't Suggest/Apply/Preview rows it can't see.\n\n" +
                 (inViewCount > 0
                   ? "Continue anyway with the "+inViewCount+" SKU(s) still in view?"
                   : "None of the selected SKUs are in this view. Please click into the correct account workspace first and re-tick.");
    if(inViewCount === 0){ alert(msg); return; }
    if(!confirm(msg)) return;
    // Filter to just the SKUs actually visible
    for(let i = skus.length - 1; i >= 0; i--){
      if(!inView.has(String(skus[i]))) skus.splice(i, 1);
    }
  }

  if(!confirm("Run Auto-fix on "+skus.length+" selected listing(s)?\n\n"+
              "Each SKU will loop through Suggest→Apply→Preview until Amazon accepts "+
              "or the loop can\u2019t make progress. This is sequential (one at a time) "+
              "so it may take a few minutes.")) return;

  const batch = {
    skus: skus, done: false, cancelled: false, startedAt: new Date().toISOString(),
    per_sku_states: [],    // one autoFix state per SKU
    current_idx: -1,
    summary: {ok: 0, stuck: 0, failed: 0},
  };
  window.BULK_AUTOFIX = batch;

  const panel = _bulkAutoFixPanel(batch);
  panel.show("Batch auto-fix: "+skus.length+" listing(s)");

  try{
    for(let i=0; i<skus.length; i++){
      if(batch.cancelled){ break; }
      batch.current_idx = i;
      const sku = skus[i];
      panel.step("["+(i+1)+"/"+skus.length+"] "+sku+" — running…");

      // Run the single-SKU loop and capture its state into the batch trace.
      // The single-SKU loop already stores state on window.AUTOFIX_STATE and
      // window._AUTOFIX_LAST_STATE so we can read it back when it finishes.
      window.AUTOFIX_STATE = null;
      try{
        await autoFixLoop(sku);
      }catch(e){
        batch.summary.failed++;
        batch.per_sku_states.push({sku: sku, error: String(e)});
        panel.step("["+(i+1)+"/"+skus.length+"] "+sku+" — CRASHED: "+String(e));
        panel.renderTrace();
        continue;
      }
      // autoFixLoop finished — pull the final state
      const finalState = window._AUTOFIX_LAST_STATE;
      if(finalState && finalState.sku === sku){
        batch.per_sku_states.push(finalState);
        // Judge the outcome from the last round's verdict (trace may be empty
        // if the loop bailed before completing any round -- e.g. /suggest 500)
        const lastRound = (finalState.trace && finalState.trace.length)
                          ? finalState.trace[finalState.trace.length-1]
                          : null;
        if(lastRound && lastRound.preview_verdict === 'ok_preview'){
          batch.summary.ok++;
        } else if(lastRound && lastRound.preview_verdict === 'error'){
          batch.summary.stuck++;
        } else {
          batch.summary.failed++;
        }
      } else {
        batch.summary.failed++;
        batch.per_sku_states.push({sku: sku, error: "no state captured"});
      }
      panel.renderTrace();
    }
    batch.done = true;
    if(batch.cancelled){
      panel.stop("Cancelled after "+batch.current_idx+" of "+skus.length+" SKU(s). "+
                  "Cleared: "+batch.summary.ok+" · stuck: "+batch.summary.stuck+" · failed: "+batch.summary.failed);
    } else {
      panel.done("Batch complete. Cleared: "+batch.summary.ok+
                 " · stuck: "+batch.summary.stuck+" · failed: "+batch.summary.failed);
    }
    panel.renderTrace();
  } finally {
    loadRows();
  }
}

// Build one large trace text covering every SKU in the batch, ready to paste
// to Claude in one message.
function _bulkAutoFixTraceText(batch){
  const lines = [];
  lines.push('=== BULK AUTO-FIX BATCH TRACE ===');
  lines.push('Started: '+batch.startedAt);
  lines.push('SKUs: '+batch.skus.length);
  lines.push('Summary: cleared='+batch.summary.ok+
              ' · stuck='+batch.summary.stuck+
              ' · failed='+batch.summary.failed);
  lines.push('');
  batch.per_sku_states.forEach(function(s, idx){
    lines.push('################################################################');
    lines.push('# SKU '+(idx+1)+' of '+batch.skus.length+': '+(s.sku||'(unknown)'));
    lines.push('################################################################');
    if(s.error){
      lines.push('LOOP ERROR: '+s.error);
      lines.push('');
      return;
    }
    if(!s.trace){
      lines.push('(no trace captured)');
      lines.push('');
      return;
    }
    // Reuse the single-SKU trace formatter
    lines.push(_autoFixTraceText(s));
    lines.push('');
  });
  lines.push('=== END BATCH TRACE ===');
  return lines.join('\n');
}

async function _bulkAutoFixCopyTrace(){
  const batch = window.BULK_AUTOFIX;
  if(!batch){ toast('No batch trace to copy'); return; }
  const text = _bulkAutoFixTraceText(batch);
  try{
    await navigator.clipboard.writeText(text);
    toast('Batch trace copied — paste into Claude chat');
  }catch(e){
    const w = window.open('', '_blank', 'width=800,height=600');
    if(w){
      w.document.title = 'Bulk auto-fix trace';
      w.document.body.innerHTML = '<pre style="font:12px ui-monospace,Consolas,monospace;padding:12px;white-space:pre-wrap">'+
        text.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</pre>';
    } else {
      prompt('Copy the trace below:', text);
    }
  }
}

function _bulkAutoFixPanel(batch){
  // Reuse the same slot as single-SKU panel so we never have two on screen
  let el = document.getElementById('autofix_panel');
  if(el){ el.remove(); }
  el = document.createElement('div');
  el.id = 'autofix_panel';
  el.style.cssText = 'position:fixed;bottom:20px;right:20px;width:620px;max-height:80vh;'+
    'background:#141b2b;border:1px solid #3b4d70;border-radius:10px;padding:12px;'+
    'box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:9999;font-size:12px;color:#e8eaed;'+
    'display:flex;flex-direction:column;gap:8px';
  el.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:center;font-weight:600">'+
      '<span>✦ Batch Auto-fix ('+batch.skus.length+' SKU'+(batch.skus.length===1?'':'s')+')</span>'+
      '<div style="display:flex;gap:8px;align-items:center">'+
        '<button onclick="_bulkAutoFixCopyTrace()" '+
          'style="background:#5b3fb8;color:#fff;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px">'+
          '📋 Copy batch trace</button>'+
        '<button onclick="if(window.BULK_AUTOFIX)window.BULK_AUTOFIX.cancelled=true;if(window.AUTOFIX_STATE)window.AUTOFIX_STATE.cancelled=true;this.parentElement.parentElement.parentElement.remove()" '+
          'style="background:none;color:#e8eaed;border:none;cursor:pointer;font-size:16px" title="Cancel batch and close">✕</button>'+
      '</div>'+
    '</div>'+
    '<div id="bulk_autofix_status" style="color:#9cc1ff"></div>'+
    '<div id="bulk_autofix_summary" style="font-size:11px;color:#bfc7d5"></div>'+
    '<div id="bulk_autofix_traceview" style="background:#0d1220;border:1px solid #263145;border-radius:6px;'+
      'padding:6px 8px;font-family:ui-monospace,Consolas,monospace;font-size:10px;'+
      'max-height:400px;overflow:auto;flex:1;white-space:pre-wrap"></div>';
  document.body.appendChild(el);
  return {
    show: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
    },
    step: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span class="genspin"></span> '+esc(msg);
      const sm = document.getElementById('bulk_autofix_summary');
      if(sm) sm.textContent = 'Progress: '+batch.summary.ok+' cleared · '+
                              batch.summary.stuck+' stuck · '+batch.summary.failed+' failed';
    },
    done: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span style="color:#74e0a3">✓ '+esc(msg)+'</span>';
    },
    stop: function(msg){
      const s = document.getElementById('bulk_autofix_status');
      if(s) s.innerHTML = '<span style="color:#e3b768">⚠ '+esc(msg)+'</span>';
    },
    renderTrace: function(){
      const t = document.getElementById('bulk_autofix_traceview');
      if(t) t.textContent = _bulkAutoFixTraceText(batch);
    },
  };
}

function roCell(v){ return `<span class="ro">${esc(v==null?"":String(v))}</span>`; }
// Suggested Amazon browse-node IDs per product type (mirrors the generator's
// PT_DEFAULT_NODE). Used only to offer a sensible default; the field stays optional.
const PT_NODE_MAP = {
  "HEALTH_PERSONAL_CARE":"66280031", "BEAUTY":"18918424031", "KITCHEN":"3187111031",
  "HOME":"3579745031", "COOKWARE_SET":"11715891", "LAMP":"10709381",
  "HARDWARE":"1938668031", "SPORT_TARGET":"26971320031"
};
function PT_NODE_DEFAULT(){
  let pt="";
  try{ pt = (window.OPT_CURRENT&&OPT_CURRENT.product_type) || (window.OPT_EDIT_ROW&&OPT_EDIT_ROW.product_type) || ""; }catch(e){}
  return PT_NODE_MAP[(pt||"").toUpperCase()] || "";
}
// Product Type control: defaults to Amazon's catalogue-assigned type (the
// ground truth). The static list is still selectable, but choosing anything
// other than the Amazon-assigned type shows a clear warning, because that's
// what causes "product type not allowed" rejections.
function productTypeCell(sku, r){
  const amazonPT = String(r.product_type||"").trim();   // assigned by get_catalog_item
  // option list = the Amazon type first (always), then the static list
  const opts = [];
  if(amazonPT) opts.push(amazonPT);
  (PTYPES||[]).forEach(p=>{ if(p && opts.indexOf(p)<0) opts.push(p); });
  const wid="pt_"+sid(sku);
  let h=`<select id="${wid}" class="ed" onchange="onProductTypeChange(this,'${esc(sku)}','${esc(amazonPT)}')">`;
  if(!amazonPT) h+=`<option value="" selected>—</option>`;
  opts.forEach(o=>{
    const isAmz = (o===amazonPT);
    h+=`<option value="${esc(o)}"${o===amazonPT?" selected":""}>${esc(o)}${isAmz?" (Amazon-assigned)":""}</option>`;
  });
  h+=`</select>`;
  h+=`<div id="${wid}_warn" class="cwarn" style="display:none"></div>`;
  return h;
}
function onProductTypeChange(sel, sku, amazonPT){
  const warn=document.getElementById("pt_"+sid(sku)+"_warn");
  const chosen=sel.value;
  if(warn){
    if(amazonPT && chosen && chosen!==amazonPT){
      warn.style.display="block";
      warn.innerHTML="⚠ Amazon assigned this product the type <b>"+esc(amazonPT)+"</b>. "
        +"Listing it as <b>"+esc(chosen)+"</b> may be rejected. Only change this if you are certain.";
    } else { warn.style.display="none"; warn.innerHTML=""; }
  }
  // save via the normal column path
  saveEdit(sel, sku, "col", "Product Type");
  // refresh the schema for the newly chosen type so the fields update
  if(typeof loadSchemas==="function"){ var _r=ROWS.find(x=>String(x.sku)===String(sku)); loadSchemas([chosen], true, _r?rowMkt(_r):WS_MARKET).then(()=>{ if(DRAWER_SKU===sku) openDrawer(sku); }); }
}
function editCell(sku,target,key,value,opts,multiline){
  const cur=(value==null?"":String(value));
  // recommended_browse_nodes is a single Amazon category NODE ID (a number), not a
  // pick-list — Amazon never ships the full node tree as an enum. Force a free-text
  // input so users aren't stuck with an empty/irrelevant dropdown.
  const isBrowseNode = /(^|\.)recommended_browse_nodes$|(^|\.)browse_node/.test(key||"");
  if(isBrowseNode){
    const def=(typeof PT_NODE_DEFAULT==="function")?PT_NODE_DEFAULT():"";
    const ph = def?("e.g. "+def+" (suggested for this type) — optional"):"e.g. 66280031 — optional";
    return `<input class="ed" value="${esc(cur)}" placeholder="${esc(ph)}" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`
      + (def&&!cur?`<div class="cc" style="font-size:11px;margin-top:3px">Leave blank to let Amazon auto-assign the category, or use the suggested node <a href="#" onclick="(function(e){e.preventDefault();var i=e.target.closest('td').querySelector('input');i.value='${esc(def)}';i.dispatchEvent(new Event('change'));})(event)">${esc(def)}</a>.</div>`:"");
  }
  if(opts&&opts.length){
    let h=`<select class="ed" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`;
    h+=`<option value=""${cur===""?" selected":""}>—</option>`;
    if(cur&&!opts.includes(cur)) h+=`<option value="${esc(cur)}" selected>${esc(cur)} (current)</option>`;
    opts.forEach(o=>{h+=`<option value="${esc(o)}"${o===cur?" selected":""}>${esc(o)}</option>`;});
    return h+`</select>`;
  }
  if(multiline) return `<textarea class="ed" rows="3" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">${esc(cur)}</textarea>`;
  return `<input class="ed" value="${esc(cur)}" onchange="saveEdit(this,'${esc(sku)}','${target}','${esc(key)}')">`;
}
function edRow(label,ctrl,hint,prov,sub,req,softReq){ const provHtml = (typeof prov==='string') ? srcBadge(prov) : (prov?iBtnEntry(prov):""); const reqHtml = softReq ? '<span class="reqsoft" title="The schema lists this as required, but Amazon\u2019s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">\u2606 schema-listed</span>' : (req?'<span class="reqstar" title="Required by Amazon">\u2605</span>':""); return `<tr class="${hint?'flaggedrow':''}${sub?' subrow':''}"><td class="k">${sub?'<span class="subarrow">\u21b3</span> ':''}${esc(_cleanLabel(label))}${reqHtml}${provHtml}${hint?` <span class="fixhint">\u26a0 ${esc(hint)}</span>`:""}</td><td class="v">${ctrl}</td></tr>`; }
function _cleanLabel(s){ s=String(s==null?"":s); s=s.replace(/&nbsp;/g,"").replace(/\u21b3/g,"").replace(/[._]/g," ").trim(); return s.charAt(0).toUpperCase()+s.slice(1); }
function wideRow(label,ctrl){ return `<tr><td colspan="2" class="wcell"><div class="wlab">${esc(label)}</div>${ctrl}</td></tr>`; }
function ccount(el, cid, limit){
  const c=document.getElementById(cid); if(!c) return;
  const useBytes = el.getAttribute && el.getAttribute("data-bytes")==="1";
  const warnAt = parseInt((el.getAttribute&&el.getAttribute("data-warn"))||"0",10)||0;
  const n = useBytes ? (function(){try{return new Blob([el.value]).size;}catch(e){return el.value.length;}})() : el.value.length;
  const unit = useBytes ? " bytes" : " chars";
  c.textContent=n+(limit?(' / '+limit):'')+unit;
  const over = limit && n>limit;
  const warn = warnAt && n>warnAt && !over;
  c.classList.toggle('over', !!over);
  c.classList.toggle('warn', !!warn);
}
// Combined indexing meter: Amazon indexes only the FIRST ~1,000 BYTES across ALL
// 5 bullets COMBINED (not per bullet). Show how much of that budget is used.
function bulletMeter(){
  const meter=document.getElementById('bulletIdxMeter'); if(!meter) return;
  let total=0;
  for(let i=1;i<=5;i++){
    const ta=document.querySelector('textarea[data-bkt="bullet'+i+'"]');
    if(ta){ try{ total+=new Blob([ta.value]).size; }catch(e){ total+=ta.value.length; } }
  }
  const cap=1000;
  const pct=Math.min(100, Math.round(total/cap*100));
  const over=total>cap;
  meter.innerHTML='<div class="idxbar"><div class="idxfill'+(over?' over':'')+'" style="width:'+pct+'%"></div></div>'
    +'<span class="idxlbl'+(over?' over':'')+'">'+total+' / '+cap+' bytes indexed across all 5 bullets'
    +(over?' — content past 1,000 bytes is NOT indexed (still shown to shoppers)':'')+'</span>';
}
// byte length (UTF-8) — Amazon counts backend search terms + bullet indexing in BYTES, not chars
function byteLen(s){ try{ return new Blob([String(s==null?"":s)]).size; }catch(e){ return String(s==null?"":s).length; } }
// Approx file size of a data: URL (base64 -> bytes) as a human string.
function dataUrlSize(durl){
  try{
    const i=String(durl).indexOf(",");
    const b64=i>=0?String(durl).slice(i+1):String(durl);
    const bytes=Math.floor(b64.length*3/4);
    if(bytes>=1048576) return (bytes/1048576).toFixed(1)+" MB";
    if(bytes>=1024) return Math.round(bytes/1024)+" KB";
    return bytes+" B";
  }catch(e){ return ""; }
}
// Attach a small "WxH · size" label under a freshly generated image. Reads the
// image's real natural dimensions once it loads. Call from the img onload.
function imgMetaLabel(imgEl, durl){
  try{
    const w=imgEl.naturalWidth||0, h=imgEl.naturalHeight||0;
    const size=durl?dataUrlSize(durl):"";
    const txt=(w&&h)?(w+"\u00d7"+h+" px"+(size?(" \u00b7 "+size):"")):(size||"");
    let cap=imgEl.parentElement&&imgEl.parentElement.querySelector(".imgmeta");
    if(!cap){ cap=document.createElement("div"); cap.className="imgmeta"; imgEl.insertAdjacentElement("afterend",cap); }
    cap.textContent=txt;
  }catch(e){}
}
function contentRow(label, sku, colKey, value, limit, opts){
  opts = opts||{};
  const cur=(value==null?"":String(value));
  const cid="cc_"+Math.random().toString(36).slice(2,8);
  const lim=limit||0;
  const useBytes = !!opts.bytes;
  const n = useBytes ? byteLen(cur) : cur.length;
  // soft warn threshold (e.g. title 75-char hard cap inside a 200 system max)
  const warnAt = opts.warnAt||0;
  const over = lim && n>lim;
  const warn = warnAt && n>warnAt && !over;
  const unit = useBytes ? " bytes" : " chars";
  const counter=`<span class="cc${over?' over':(warn?' warn':'')}" id="${cid}">${n}${lim?' / '+lim:''}${unit}</span>`;
  const idx = opts.indexNote ? `<span class="idxnote" title="${esc(opts.indexTip||'')}">${esc(opts.indexNote)}</span>` : "";
  const warnmsg = opts.warnMsg && (warn||over) ? `<div class="cwarn">⚠ ${esc(opts.warnMsg)}</div>` : "";
  const rows = opts.rows||3;
  const tgt = opts.target||"col";
  const ta=`<textarea class="ed" rows="${rows}" data-bkt="${esc(opts.bucket||'')}" data-bytes="${useBytes?1:0}" data-warn="${warnAt}" data-lim="${lim}" oninput="ccount(this,'${cid}',${lim});bulletMeter()" onchange="saveEdit(this,'${esc(sku)}','${tgt}','${esc(colKey)}')">${esc(cur)}</textarea>`;
  return `<tr><td colspan="2" class="wcell"><div class="wlab">${esc(label)} ${counter} ${idx}</div>${warnmsg}${ta}</td></tr>`;
}
function edRowReq(label,ctrl,hint){ return `<tr class="reqrow"><td class="k"><span class="klabel">${esc(label)}<span class="reqstar" title="Required by Amazon">\u2605</span></span> <span class="reqtag">needs value</span>${hint?`<span class="fixhint">\u26a0 ${esc(hint)}</span>`:""}</td><td class="v">${ctrl}</td></tr>`; }
function sid(s){ return String(s).replace(/[^a-zA-Z0-9]/g,"_"); }
function parseMissing(notes){
  // pull field names Amazon's preview flagged as "required but missing" (ground truth)
  if(!notes) return [];
  const out=[];
  String(notes).split(";").forEach(p=>{
    const m=p.match(/\[E\]\s+(\S+)\s+.*required but missing/i);
    if(m && m[1]) out.push(m[1]);
  });
  return out;
}
const AXIS_FIELD={width:"item_width",depth:"item_depth",height:"item_height",length:"item_length"};
// Plain-English, value-specific guidance shown UNDER the flagged field so the
// user knows exactly what to enter. Keyed by Amazon attribute name. Generic
// errors fall through to the phrasing matchers below; only known fields get a
// precise instruction here. Sub-field errors (e.g. hazmat.aspect) inherit the
// parent's hint, and the hazmat parent also carries the full instruction.
const SPECIFIC_HINT={
  hazmat:"Lithium battery item. Aspect = united_nations_regulatory_id, Value = UN3481 (battery packed in equipment).",
  contains_battery_or_cell:"App fills this automatically on Preview (Yes / true to match Amazon's list). You don't need to type here.",
  batteries_included:"Pick Yes / No from the list (not the word True).",
  batteries_required:"Pick Yes / No from the list (not the word True).",
  battery_installation_device_type:"For a LITHIUM battery, Amazon requires not_installed (installed_in_equipment is rejected for lithium). Other valid values: installed_in_vehicle, installed_in_vessel. The word Flashlight is NOT accepted.",
  wattage:"Enter a number AND pick the Wattage Unit (e.g. watts) — or remove wattage entirely.",
  warranty_description:"Type the warranty text, e.g. 1 Year Manufacturer Warranty.",
  special_feature:"Enter each feature as its own value (this is the singular field Amazon wants, not Special features).",
  model_name:"Enter the model name / number for this product.",
  supplier_declared_dg_hz_regulation:"Is this product hazardous/dangerous to ship? For a normal non-chemical, non-battery item (e.g. a hand tool) choose \u201cnot_applicable\u201d. Only pick a regulation (e.g. for lithium batteries or chemicals) if the product actually contains one.",
  lithium_battery_packaging:"Battery is inside the device — choose batteries_contained_in_equipment."
};
// Per-sub-field guidance for nested compliance attributes (key = "parent.subpath").
const SUBFIELD_HINT={
  "hazmat.aspect":"Choose united_nations_regulatory_id.",
  "hazmat.value":"Type UN3481 (lithium-ion battery packed with equipment).",
  "hazmat.united_nations_regulatory_id":"Type UN3481."
};
function parseFlagged(notes){
  // {field: hint} for every fixable attribute issue Amazon flagged in the last preview.
  // Maps composite dimension errors (item_depth_width_height) to the editable axis field.
  const out={};
  if(!notes) return out;
  String(notes).split(";").forEach(seg=>{
    const m=seg.match(/\[[EW]\]\s+([a-z][a-z0-9_]+)\s+([\s\S]*)/i);   // skips non-attribute "fields" like a bare barcode number
    if(!m) return;
    const field=m[1].toLowerCase(), msg=m[2];
    if(/required but missing/i.test(msg)){ if(!out[field]) out[field]="required"; return; }
    let mm=msg.match(/at least '([^']+)'\s+(\w+)\s+for '([^']+)'/i);
    if(mm){ out[AXIS_FIELD[mm[3].toLowerCase()]||field]="must be at least "+mm[1]+" "+mm[2]; return; }
    mm=msg.match(/at most '([^']+)'\s+(\w+)\s+for '([^']+)'/i);
    if(mm){ out[AXIS_FIELD[mm[3].toLowerCase()]||field]="must be at most "+mm[1]+" "+mm[2]; return; }
    mm=msg.match(/must be at least '([^']+)'\s*(\w+)?/i);
    if(mm){ out[field]="must be at least "+mm[1]+(mm[2]?(" "+mm[2]):""); return; }
    // SPECIFIC, ACTIONABLE HINT for the common compliance offenders, so the box
    // tells the user exactly WHAT to enter (not just "choose a value"). Overrides
    // the generic phrasing below. Falls through to generic/catch-all if unknown.
    if(SPECIFIC_HINT[field]){ out[field]=SPECIFIC_HINT[field]; return; }
    if(/not a valid value|approved value|select an approved/i.test(msg)){ out[field]="choose an allowed value"; return; }
    if(/does not have the expected value|expected value|unexpected value|invalid value|not.*expected/i.test(msg)){ out[field]="choose an allowed value"; return; }
    if(/less than the minimum|greater than the maximum|out of range/i.test(msg)){ out[field]="value out of allowed range"; return; }
    // CATCH-ALL: any other error Amazon flagged on a real attribute still gets a
    // visible box, so a field is NEVER silently dropped from the editor just
    // because its error phrasing is new. (This is what hid `hazmat` before.)
    if(!out[field]) out[field]="Amazon flagged this — review the value";
    return;
  });
  return out;
}
function addField(sku, pt, sel){
  const k=sel.value; if(!k) return;
  const sc=SCHEMAS[pt]||{opts:{}}; const opts=(sc.opts||{}); const subs=(sc.subs||{});
  const tb=document.getElementById("added_"+sid(sku));
  if(!tb){ sel.value=""; return; }
  if(tb.querySelector('tr[data-fk="'+k+'"]')){ sel.value=""; return; }
  const sf=subs[k];
  if(sf&&sf.length){
    const head=document.createElement("tr");
    head.setAttribute("data-fk",k); head.className="subhead";
    head.innerHTML='<td class="k" colspan="2"><b>'+k.replace(/_/g," ")+'</b></td>';
    tb.appendChild(head);
    sf.forEach(s=>{
      const full=k+"."+s.path;
      const tr=document.createElement("tr");
      tr.className='subrow';
      tr.innerHTML='<td class="k"><span class="subarrow">\u21b3</span> '+esc(_cleanLabel(s.label))+'</td><td class="v">'+editCell(sku,"attr",full,"",(s.enum&&s.enum.length?s.enum:null))+'</td>';
      tb.appendChild(tr);
    });
  }else{
    const tr=document.createElement("tr");
    tr.setAttribute("data-fk",k);
    tr.innerHTML='<td class="k">'+k.replace(/_/g," ")+'</td><td class="v">'+editCell(sku,"attr",k,"",opts[k]||null)+'</td>';
    tb.appendChild(tr);
  }
  for(let i=sel.options.length-1;i>=0;i--){ if(sel.options[i].value===k) sel.remove(i); }
  sel.value="";
}
const COLMAP={"Title":"title","Description (HTML)":"description","Search Terms / KW":"search_terms",
  "Our Price (GBP)":"price","Brand":"brand","UPC":"barcode","Handling Days":"handling_days","Product Type":"product_type"};
function updateLocalCol(r,key,value){
  if(key in COLMAP){ r[COLMAP[key]]=value; return; }
  const m=key.match(/^Bullet (\d)$/); if(m){ r.bullets=r.bullets||[]; r.bullets[+m[1]-1]=value; }
}
async function saveEdit(el,sku,target,key){
  const value=el.value; el.classList.remove("saved","err"); el.classList.add("saving");
  try{
    const res=await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku,target,key,value})});
    const j=await res.json(); el.classList.remove("saving");
    if(j.ok){ el.classList.add("saved"); toast("Saved ✓"); setTimeout(()=>el.classList.remove("saved"),1000);
      const r=ROWS.find(x=>x.sku===sku);
      if(r){ if(target==="attr"){ r.attributes=r.attributes||{};
               if(String(value).trim()==="") delete r.attributes[key]; else r.attributes[key]=value; }
             else updateLocalCol(r,key,value); }
    } else { el.classList.add("err"); toast("Save failed: "+(j.error||"")); }
  }catch(e){ el.classList.remove("saving"); el.classList.add("err"); toast("Save failed: "+e); }
}
// Schema-state diagnostic strip. The #1 reason flagged boxes render without
// dropdowns (or look "empty/shrunk") is that the LIVE Amazon schema for this
// product type failed to load in the browser -- so enums is empty and every
// field falls back to a plain text box. This makes that state visible and gives
// a one-click reload, instead of silently looking broken.
function schemaDiag(pt, nEnum, nAttrs, nSubs, missing, flagged, a){
  if(!pt) return "";
  const loaded = !!(SCHEMAS[pt] && (SCHEMAS[pt].attrs||[]).length);
  const flaggedKeys=Object.keys(flagged||{});
  const SS=(SCHEMAS[pt]||{});
  const hasList=(k)=>{
    if(SS.opts && SS.opts[k] && SS.opts[k].length) return true;        // top-level dropdown
    const sf=(SS.subs||{})[k];                                          // nested: any sub-field with a list
    if(sf && sf.some(s=>s.enum && s.enum.length)) return true;
    return false;
  };
  const noDropdown=flaggedKeys.filter(k=>!hasList(k));
  if(loaded && nEnum>0){
    // healthy: schema loaded with enums. Tiny unobtrusive confirmation.
    let note="";
    if(flaggedKeys.length && noDropdown.length){
      note=`<div style="font-size:11px;color:#c9a227;margin-top:4px">${noDropdown.length} flagged field(s) have no preset list from Amazon (${noDropdown.map(esc).join(", ")}) — these are free-text: type the value Amazon expects.</div>`;
    }
    return `<div class="schemadiag ok">Amazon schema loaded for <b>${esc(pt)}</b> · ${nEnum} field(s) with dropdown values, ${nAttrs} total, ${nSubs} nested.${note}</div>`;
  }
  // unhealthy: schema not loaded / empty -> THIS is why boxes look broken
  return `<div class="schemadiag bad">
    <b>⚠ Amazon's value lists for “${esc(pt)}” haven't loaded in this view.</b>
    That's why flagged fields show as plain boxes without dropdowns. The listing data is still editable, but the allowed-value menus are missing.
    <div style="margin-top:6px">
      <button class="ghost" onclick="reloadSchemaNow('${esc(pt)}')"><i class="ti ti-refresh"></i> Reload Amazon values now</button>
      <button class="ghost" onclick="dumpSchemaState('${esc(pt)}')"><i class="ti ti-bug"></i> Show what loaded</button>
    </div>
    <div id="schemadump_${sid(pt)}" style="font-size:11px;color:#9bb;margin-top:6px;white-space:pre-wrap"></div>
  </div>`;
}
async function reloadSchemaNow(pt){
  toast("Reloading Amazon values for "+pt+"…");
  try{
    var _r = DRAWER_SKU ? ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)) : null;
    var _mkt = _r ? rowMkt(_r) : WS_MARKET;
    if(typeof loadSchemas==="function"){ await loadSchemas([pt], true, _mkt); }
    if(DRAWER_SKU){ const fr=ROWS.find(x=>String(x.product_type)===String(pt)&&String(x.sku)===String(DRAWER_SKU)) || ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)); const host=document.getElementById("fulldata_"+sid(DRAWER_SKU)); if(host&&fr){ host.innerHTML=fullData(fr); } }
    const s=SCHEMAS[pt]||{};
    const n=(s.opts?Object.keys(s.opts).length:0);
    toast(n>0?("Loaded "+n+" value lists ✓"):"Still empty — Amazon schema call returned nothing. Check the app's terminal for an SP-API error.");
  }catch(e){ toast("Reload failed: "+(e&&e.message||e)); }
}
async function dumpSchemaState(pt){
  const el=document.getElementById("schemadump_"+sid(pt));
  var _r = DRAWER_SKU ? ROWS.find(x=>String(x.sku)===String(DRAWER_SKU)) : null;
  var _mkt = _r ? rowMkt(_r) : WS_MARKET;
  let txt="listing marketplace: "+(_mkt||"(none)")+"\nclient SCHEMAS["+pt+"]: ";
  const s=SCHEMAS[pt];
  if(!s){ txt+="NOT LOADED\n"; } else {
    txt+= (s.attrs||[]).length+" attrs, "+(s.opts?Object.keys(s.opts).length:0)+" enums, "+(s.subs?Object.keys(s.subs).length:0)+" nested\n";
  }
  // also ask the server directly so we can compare
  try{
    const j=await (await fetch("/schema/"+encodeURIComponent(pt)+"?refresh=1"+(_mkt?("&mkt="+encodeURIComponent(_mkt)):""))).json();
    if(j.ok){ txt+="server /schema ("+(j.marketplace||"?")+"): "+(j.attrs||[]).length+" attrs, "+Object.keys(j.enums||{}).length+" enums, "+Object.keys(j.subfields||{}).length+" nested\n";
      txt+="enum fields: "+Object.keys(j.enums||{}).slice(0,30).join(", ");
    } else { txt+="server /schema ERROR: "+(j.error||"unknown")+"\n"; }
  }catch(e){ txt+="server /schema fetch failed: "+(e&&e.message||e); }
  if(el) el.textContent=txt;
}
function fullData(r){
  try{
    return _fullDataInner(r);
  }catch(err){
    // Never let a render error silently collapse the drawer into empty boxes.
    // Show what failed so it can be fixed instead of guessed at.
    return `<details open><summary>Full listing data</summary>
      <div style="background:#3a1212;border:1px solid #6b2222;border-radius:8px;padding:12px;margin:8px 0">
        <b style="color:#ff8a8a">This listing's detail view hit an error while rendering.</b>
        <div style="font-size:12px;color:#ffb3b3;margin-top:6px">${esc(String(err&&err.message||err))}</div>
        <div style="font-size:11px;color:#c98;margin-top:8px">The raw data is still below so you can read/edit it.</div>
        <pre class="raw" style="display:block;margin-top:8px">${esc(JSON.stringify(r,null,2))}</pre>
      </div></details>`;
  }
}
function _fullDataInner(r){
  const sku=r.sku;
  const sc=SCHEMAS[r.product_type]||{opts:{},req:[],attrs:[],subs:{},titles:{}};
  const enums=sc.opts||{}, reqList=sc.req||[], allAttrs=sc.attrs||[];
  const titles=sc.titles||{};
  // Amazon's REAL field label (matches Seller Central) -> falls back to prettified key
  const lbl=(k)=> titles[k] || _cleanLabel(String(k));
  const idRows=[
    edRow("Product type", productTypeCell(sku, r), "Amazon-assigned from the catalogue. Changing it can cause rejection."),
    edRow("SKU", roCell(r.sku)),
    edRow("Brand", editCell(sku,"col","Brand",r.brand), null, (rowProvenance(r)||{}).brand),
    edRow("Condition", roCell("New")),
    edRow("Category", roCell((r.category||r.amazon_category||"")+(r.subcategory?(" › "+r.subcategory):""))),
    edRow("Browse node(s)", roCell((r.attributes||{}).recommended_browse_nodes||(r.attributes||{}).browse_node||"—")),
    edRow("Barcode / GTIN", editCell(sku,"col","UPC",r.barcode)),
    (function(){
       // Currency follows the ACTIVE workspace marketplace (reliable), with a
       // per-row override if the row itself carries a marketplace.
       var rowMkt = String(r._marketplace||(r.attributes||{}).marketplace||"").toUpperCase();
       var mkt = rowMkt || String(WS_MARKET||"").toUpperCase() || "UK";
       var cur = (mkt==="US"||mkt==="CA"||mkt==="MX") ? "$"
               : (mkt==="EU"||["DE","FR","IT","ES","NL"].indexOf(mkt)>=0) ? "\u20ac" : "\u00a3";
       var raw=String(r.price==null?"":r.price);
       var num=raw.replace(/[^0-9.\-]/g,"");            // strip any currency -> number only
       return edRow("Price ("+cur+")", '<span class="curlbl">'+cur+'</span>'+editCell(sku,"col","Our Price (GBP)",num));
    })(),
    edRow("List price", roCell((function(){var lp=(r.attributes||{}).list_price; return lp?String(lp).replace(/[^0-9.\-]/g,"")||"—":"—";})())),
    edRow("Quantity — blank = default 10", editCell(sku,"attr","fulfillment_quantity",(r.attributes||{}).fulfillment_quantity||"")),
    (function(){
       var rowMkt = String(r._marketplace||(r.attributes||{}).marketplace||"").toUpperCase();
       var mkt = rowMkt || String(WS_MARKET||"").toUpperCase() || "UK";
       var cur = (mkt==="US"||mkt==="CA"||mkt==="MX") ? "$"
               : (mkt==="EU"||["DE","FR","IT","ES","NL"].indexOf(mkt)>=0) ? "\u20ac" : "\u00a3";
       var pnum=String(r.profit==null?"":r.profit).replace(/[^0-9.\-]/g,"");
       return edRow("Profit ("+cur+")", roCell(pnum?(cur+pnum):"—"));
    })(),
    edRow("Handling days", editCell(sku,"col","Handling Days",r.handling_days)),
    edRow("Shipping group", roCell(SHIP)),
  ].join("");
  const a=r.attributes||{};
  const IMGRE=/^(main_product_image_locator|other_product_image_locator_\d+)$/;
  const imgUrls=Object.keys(a).filter(k=>IMGRE.test(k)).sort().map(k=>a[k]).filter(Boolean);
  const HIDEKEYS=new Set([...Object.keys(a).filter(k=>IMGRE.test(k)),"fulfillment_quantity"]);
  const _AHIDE=new Set(["_provenance","provenance"]); const aKeys=Object.keys(a).filter(k=>!HIDEKEYS.has(k));
  // fields the script fills itself (structural / identity / dimensions) -- never shown as needs-value
  const EXCLUDE_REQ=new Set(["item_name","bullet_point","product_description","generic_keyword","purchasable_offer","fulfillment_availability","brand","condition_type","merchant_shipping_group","supplier_declared_has_product_identifier_exemption","externally_assigned_product_identifier","list_price","manufacturer","model_number","part_number","item_dimensions","item_package_dimensions","item_depth_width_height","item_length_width_height","website_shipping_weight","recommended_browse_nodes","browse_node","browse_nodes"]);
  // required-but-missing = schema top-level required UNION the fields Amazon's last preview flagged
  const flagged=parseFlagged(r.notes);   // {field: hint} from Amazon's last preview (required / min-max / invalid)
  const flaggedKeys=Object.keys(flagged);
  const reqUnion=new Set([...(reqList||[]), ...flaggedKeys]);
  // A field Amazon EXPLICITLY flagged must ALWAYS show a box, even if it's in
  // EXCLUDE_REQ (our "script fills it" assumption) -- Amazon is overriding us.
  // Only EXCLUDE_REQ filters the schema-required list, never the flagged list.
  const missing=[...reqUnion].filter(k=>{
    if(!k) return false;
    if(k in a) return false;                       // already has a value
    if(flagged[k]) return true;                    // Amazon flagged it -> ALWAYS show
    if(EXCLUDE_REQ.has(k)) return false;           // script fills it (and not flagged)
    if(k.endsWith("_image_locator")) return false; // images optional
    return true;
  }).sort();
  const _prov=rowProvenance(r);
  const subs=sc.subs||{};
  // FALLBACK nested structure: when the live schema didn't load, sc.subs is empty
  // and nested fields would collapse to flat boxes (losing the structure AND the
  // "filling this requires its sub-fields" note). Rebuild the nesting from (a) any
  // dotted keys already in the data (e.g. "battery.cell_composition") and (b) a
  // known map of common Amazon nested fields. This makes the structure + note show
  // ALL the time, regardless of whether Amazon's value lists loaded this view.
  const KNOWN_NESTED={
    battery:["cell_composition","average_life","weight","charge_time","capacity"],
    hazmat:["aspect","value"],
    wattage:["value","unit"],
    unit_count:["value","type"],
    item_length:["value","unit"],
    item_width:["value","unit"],
    item_height:["value","unit"],
    item_weight:["value","unit"],
    package_weight:["value","unit"],
    voltage:["value","unit"],
    item_dimensions:["length","width","height"],
    supplier_declared_dg_hz_regulation:["value"]
  };
  function _fallbackSubs(){
    const out={};
    // (a) from dotted keys in the data
    Object.keys(a).forEach(function(key){
      const dot=key.indexOf(".");
      if(dot>0){
        const parent=key.slice(0,dot), child=key.slice(dot+1);
        if(!out[parent]) out[parent]=[];
        if(!out[parent].some(s=>s.path===child)) out[parent].push({path:child,label:child.replace(/_/g," "),enum:null});
      }
    });
    // (b) from the known map -- only add a parent that the data/attrs actually reference
    Object.keys(KNOWN_NESTED).forEach(function(parent){
      const referenced = (parent in a) || aKeys.indexOf(parent)>=0 ||
                         Object.keys(a).some(k=>k.indexOf(parent+".")===0) ||
                         (reqList||[]).indexOf(parent)>=0;
      if(referenced && !out[parent]){
        out[parent]=KNOWN_NESTED[parent].map(c=>({path:c,label:c.replace(/_/g," "),enum:null}));
      }
    });
    return out;
  }
  const fbSubs=_fallbackSubs();
  // merged view: prefer the real schema subs; fall back to reconstructed ones
  const subsView=Object.assign({}, fbSubs, subs);
  // Render ONE attribute. If schema says it's a nested object (battery,
  // maximum_speed, item_dimensions, ...), expand into its real sub-field boxes;
  // each sub-field saves flat as "<field>.<path>".
  const renderAttr=(k,isMissing)=>{
    const sf=subsView[k];
    // A field is "required" for star purposes if the schema lists it OR Amazon's
    // preview flagged it (conditionally required, e.g. hazmat on a battery item).
    const _schemaReq = (reqList||[]).indexOf(k)>=0;
    const isReqParent = _schemaReq || !!isMissing;
    // HONESTY: the schema's static required list is broader than what Amazon's
    // live validation actually enforces. If a clean Preview already ran for this
    // listing (status API_READY / "PREVIEW clean") and did NOT flag this field,
    // then a hard red "Required" star is misleading -- Amazon accepted it without
    // it. Show a SOFTER marker in that case so the user isn't sent chasing a
    // field Amazon didn't ask for (e.g. dangerous goods on a manual tool).
    const _cleanPrev = (String(r.status||"").toUpperCase()==="API_READY")
                       || /PREVIEW clean/i.test(String(r.notes||""));
    const _amazonFlagged = !!isMissing || !!flagged[k];
    const _schemaOnly = _schemaReq && !_amazonFlagged && _cleanPrev;
    const reqMark = _amazonFlagged
      ? '<span class="reqstar" title="Amazon flagged this in Preview — it must be filled">\u2605</span>'
      : (_schemaOnly
          ? '<span class="reqsoft" title="The schema lists this as required, but Amazon\u2019s last Preview accepted the listing WITHOUT it. Fill it only if a later Preview flags it.">\u2606 schema-listed</span>'
          : (isReqParent ? '<span class="reqstar" title="Required by Amazon">\u2605</span>' : ''));
    if(sf&&sf.length){
      // Specific parent instruction (e.g. hazmat) shown right on the group header
      // so the user sees WHAT to enter at the field, not just in the top red box.
      const headHint = isMissing ? (SPECIFIC_HINT[k] || "fill the sub-fields below") : null;
      // ALWAYS-ON guidance for multi-level (nested) fields: a parent like this is
      // usually optional, BUT the moment you put a value in it, Amazon makes its
      // sub-fields required -- leaving any blank then throws an error. This note
      // prevents the "why did filling one box create new errors?" surprise.
      const nestNote = isReqParent
        ? ""   // already required -> the star + headHint already say to fill it
        : `<span class="nesthint" title="This field is optional. But if you enter a value here, Amazon will require ALL its sub-fields below to be filled too — otherwise it errors. Leave the whole group blank if you don't need it.">\u2139 optional — but filling this makes its sub-fields required</span>`;
      const head=`<tr class="subhead${isMissing?' flaggedrow':''}"><td class="k" colspan="2"><b>${esc(lbl(k))}</b>${reqMark}${headHint?` <span class="fixhint">\u26a0 ${esc(headHint)}</span>`:''}${nestNote}</td></tr>`;
      const rows=sf.map(s=>{
        const full=k+"."+s.path;                 // flat dot-key in Attributes JSON
        const val=(full in a)?a[full]:"";
        const sHasEnum=!!(s.enum&&s.enum.length);
        // Per-sub-field guidance for the known compliance fields.
        const subKey=(k+"."+s.path).toLowerCase();
        let sHint = isMissing ? (sHasEnum?"choose an allowed value":"type the value Amazon expects") : null;
        if(isMissing && SUBFIELD_HINT[subKey]) sHint = SUBFIELD_HINT[subKey];
        return edRow(titles[full]||s.label, editCell(sku,"attr",full,val,(sHasEnum?s.enum:null)), sHint, _prov&&_prov[full], true);
      }).join("");
      return head+rows;
    }
    const isReq = ((reqList||[]).indexOf(k)>=0) || !!isMissing;
    // same honesty rule as the nested head: a schema-required field that a clean
    // Preview didn't flag shows a soft marker, not a hard "required" star.
    const _flatAmazonFlagged = !!isMissing || !!flagged[k];
    const _flatSchemaOnly = ((reqList||[]).indexOf(k)>=0) && !_flatAmazonFlagged && _cleanPrev;
    // Accurate hint: if Amazon gives an allowed-value list -> dropdown ("choose
    // a value"); if not -> free text, so tell the user to type what Amazon wants
    // rather than showing the misleading "choose an allowed value".
    const hasEnum = !!(enums[k] && enums[k].length);
    const baseHint = flagged[k] || "";
    const missHint = hasEnum
      ? (baseHint || "choose an allowed value")
      : (/required/i.test(baseHint) ? "required — type the value Amazon expects"
                                    : "type the value Amazon expects (free text)");
    return isMissing
      ? edRowReq(lbl(k), editCell(sku,"attr",k,"",enums[k]||null), missHint)
      : edRow(lbl(k), editCell(sku,"attr",k,a[k],enums[k]||null), flagged[k], _prov&&_prov[k], false, isReq, _flatSchemaOnly);
  };
  // skip flat dot-keys that belong to a nested group (rendered under their head)
  const isSubKey=k=>k.includes(".")&&subsView[k.split(".")[0]];
  // parents whose sub-values are already filled (so head + sub-rows still show)
  const filledParents=[...new Set(aKeys.filter(isSubKey).map(k=>k.split(".")[0]))]
      .filter(p=>!aKeys.includes(p)&&!missing.includes(p));
  const presentTop=aKeys.filter(k=>!_AHIDE.has(k)&&!isSubKey(k));
  const attrRows=presentTop.map(k=>renderAttr(k,false)).join("")
    + filledParents.map(k=>renderAttr(k,false)).join("")
    + missing.map(k=>renderAttr(k,true)).join("");
  // every other schema field the user MAY fill (optional) -> add-on demand picker
  const addable=allAttrs.filter(k=>!(k in a) && !missing.includes(k) && !EXCLUDE_REQ.has(k) && !k.endsWith("_image_locator")).sort();
  const sidv=sid(sku);
  const addCtrl = addable.length ? `<div class="addfield">
      <select onchange="addField('${esc(sku)}','${esc(r.product_type)}',this)">
        <option value="">+ add another field (${addable.length} optional available)…</option>
        ${addable.map(k=>`<option value="${esc(k)}">${esc(lbl(k))}</option>`).join("")}
      </select>
      <table class="kv" id="added_${sidv}"></table>
      <div class="hint">Pick any field to add and fill — saves automatically.</div>
    </div>` : "";
  // ---- CONTENT FIELDS with 2026 limits + indexing depth indicators ----------
  // Title: 200 system max, but a 75-char HARD CAP lands Jul 27 2026 (all cats
  //        except media). Mobile truncates ~70. Fully indexed, highest weight.
  // Bullets: 500 each, but only the first ~1,000 BYTES across all 5 COMBINED are
  //          indexed -> a shared byte meter sits above the bullets.
  // Description: 2,000 incl HTML, indexed but LOWEST weight of visible fields.
  // Item Highlights: 125, new structured field, own A10 weight.
  // Backend search terms: 249 BYTES (not chars); one byte over de-indexes ALL.
  const titleOpts={ warnAt:75, warnMsg:"Amazon's 75-char hard cap applies from 27 Jul 2026 (all categories except media). Front-load the first ~70 chars — mobile truncates there.", indexNote:"fully indexed · highest weight", indexTip:"Title carries the most A10 search weight. Mobile shows ~70-80 chars, so put the most important words first." };
  const bulletOptsFor=(i)=>({ bucket:"bullet"+i, indexNote:(i===1?"first 1,000 bytes (all 5 combined) indexed":""), indexTip:"Amazon indexes only the first ~1,000 bytes across ALL five bullets combined — not per bullet. See the meter above." });
  const descOpts={ indexNote:"indexed · lowest weight", indexTip:"The description is indexed but weighted lowest of the visible fields. Won't save past 2,000 chars (HTML included)." };
  const highlightOpts={ target:"attr", indexNote:"indexed · own weight", indexTip:"Item Highlights is a structured field shown with the title in search and on the PDP. Carries its own A10 weight (2026)." };
  const backendOpts={ bytes:true, warnAt:249, warnMsg:"Backend search terms are measured in BYTES. One byte over 249 silently de-indexes the ENTIRE field — keep it at or under 249.", indexNote:"249-byte cap · de-index risk", indexTip:"Counted in bytes, not characters. Going one byte over 249 removes the whole field from search." };
  const bulletMeterRow = `<tr><td colspan="2" class="wcell"><div id="bulletIdxMeter" class="bulletmeter"></div></td></tr>`;
  const itemHi = (r.attributes||{}).item_type_keyword===undefined ? "" : "";
  const _highlightVal = (function(){ try{ return (r.attributes||{}).item_highlights || r.item_highlights || ""; }catch(e){ return ""; } })();
  const cRows=[
      contentRow("Backend search terms", sku, "Search Terms / KW", r.search_terms, 249, backendOpts),
      contentRow("Title", sku, "Title", r.title, 200, titleOpts),
      contentRow("Item Highlights", sku, "item_highlights", _highlightVal, 125, highlightOpts)
    ]
    .concat([bulletMeterRow])
    .concat((r.bullets||[]).map((b,i)=>contentRow("Bullet "+(i+1), sku, "Bullet "+(i+1), b, 500, bulletOptsFor(i+1))))
    .concat([contentRow("Description", sku, "Description (HTML)", r.description, 2000, descOpts)]).join("");
  const rid="raw_"+Math.random().toString(36).slice(2,8);
  const nEnum=Object.keys(enums).length;
  const hasAttrs=aKeys.length||missing.length;
  const nFix=missing.length + Object.keys(flagged).filter(k=>k in a).length;
  const attrHdr=nFix?` — ${nFix} field(s) flagged by Amazon — fix the highlighted ones`:(hasAttrs?'':' — none yet');
  const st=(r.status||"").toUpperCase();
  const reqNote = missing.length
    ? `<div class="reqnote">Amazon reveals required fields in <b>stages</b> — fill the highlighted box(es) above, then click <b>Preview (API)</b> again. More required fields may appear after each Preview; repeat until Preview reports no errors.</div>`
    : (["API_READY","API_ERROR","LIVE"].includes(st) ? ""
        : `<div class="reqnote">Required fields are revealed by Amazon's validation, not upfront. Click <b>Preview (API)</b> to check this row — any required fields will appear here as highlighted boxes.</div>`);
  const rememberBtn = (aKeys.length||missing.length)
    ? `<button class="rememberbtn" onclick="saveDefault('${esc(sku)}','${esc(r.product_type)}',this)">★ Remember these as defaults for all ${esc(r.product_type||"this type")} listings</button>`
    : "";
  const isBrandRow = !r.asin || (r.sku && /^[A-Za-z]/.test(String(r.sku)) && !/_\d+Days_/.test(String(r.sku)));
  const imgLabel = isBrandRow ? "Images — from brand catalogue" : "Images — from competitor (eBay priority)";
  const _mainIsLocal = imgUrls.length && !/^https?:\/\//i.test(String(imgUrls[0]||""));
  const _imgWarn = _mainIsLocal
    ? `<div class="hint" style="color:#e3b768;margin-top:4px">⚠ The main image is a LOCAL file Amazon can't fetch — it will block submission. Remove it (submit without an image) or set a public https URL.</div>`
    : "";
  const _imgActions = imgUrls.length
    ? `<div style="margin-top:6px;display:flex;gap:8px">
         <button class="suggestbtn" style="background:#2a1414;border-color:#5c2424;color:#ff8a8a" onclick="clearMainImage('${esc(sku)}')" title="Remove the main image URL so the listing can be created without an image (add one later in Seller Central)"><i class="ti ti-photo-off"></i> Remove main image</button>
       </div>`
    : "";
  const imgBlock = (imgUrls.length
    ? `<div class="kvsec">${imgLabel}</div><div class="imgrow">${imgUrls.map((u,i)=>`<div class="thumbwrap"><a href="${esc(u)}" target="_blank" title="${i===0?'MAIN image':'additional #'+i}"><img class="thumb" src="${esc(u)}" loading="lazy"><span class="thumbcap">${i===0?'main':'#'+i}</span></a><button class="thumbedit" title="Edit this image (AI changes only what you ask)" onclick="editListingImage('${esc(sku)}','${esc(u)}',${i})"><i class="ti ti-wand"></i></button></div>`).join("")}</div>${_imgWarn}${_imgActions}`
    : `<div class="kvsec">Images</div><div class="hint">No image captured for this row.</div>`)
    + `<div class="genimg" id="genimg_${sidv}">
        <div class="kvsec" style="color:#c8b6ff;margin-top:12px"><i class="ti ti-sparkles"></i> AI image generation</div>
        <div class="genpanel" id="genpanel_${sidv}" style="display:block">
          <div class="gendiag" id="gendiag_${sidv}">Checking OpenRouter connection…</div>
          <div class="genrow">
            <span class="cc">Reference image:</span>
            <input class="ed geninput" id="genraw_${sidv}" style="flex:1"
                   value="${esc(imgUrls[0]||'')}"
                   placeholder="${isBrandRow?'brand/product image URL':'eBay source image (auto)'}">
            <label class="uploadbtn" title="Upload a reference image from your computer">
              <i class="ti ti-upload"></i> Upload
              <input type="file" accept="image/*" style="display:none" onchange="uploadRef(this,'${esc(sku)}','${sidv}')">
            </label>
          </div>
          ${isBrandRow?`<label class="cc"><input type="checkbox" id="genusebrand_${sidv}"> use brand-saved reference image instead</label>`:''}
          <textarea class="ed geninput" id="genbrief_${sidv}" rows="2"
            placeholder="Your command: how should the image look? e.g. 'premium studio shot, soft shadow, blue mirror lens variant'"></textarea>
          <div class="genrow">
            <span class="cc">Prompt AI:</span>
            <select class="ed" id="gentai_${sidv}" style="width:auto"></select>
            <span class="cc">Image AI:</span>
            <select class="ed" id="geniai_${sidv}" style="width:auto"></select>
            <a class="browsemodels sm" href="https://openrouter.ai/models?output_modalities=image" target="_blank" rel="noopener" title="See all image models on OpenRouter"><i class="ti ti-external-link"></i> all image models</a>
          </div>
          <div class="genrow">
            <button class="genimgbtn" id="genbtn_${sidv}" onclick="doGen('${esc(sku)}','${sidv}')">Generate</button>
            <span class="cc" id="genstatus_${sidv}"></span>
          </div>
          <details id="genpromptwrap_${sidv}" style="display:none"><summary class="cc">view detailed prompt the AI wrote</summary><pre class="genprompt" id="genprompt_${sidv}"></pre></details>
          <div id="genresult_${sidv}"></div>
        </div>
      </div>`
      + ((window.WS_FEATURES&&window.WS_FEATURES.indexOf('harvest')>=0)
         ? milesTemplatePanel(sku, sidv) : "");
  // COMPLETE submission view: every attribute key, no exclusions, read-only,
  // so the user sees everything that will be sent to Amazon (browse nodes,
  // dimensions, compliance flags, image locators, prices -- the lot).
  const allSubKeys=Object.keys(a).filter(k=>k!=="_provenance"&&k!=="provenance").sort();
  const fmtVal=v=>{ if(v==null) return ""; if(typeof v==="object") return esc(JSON.stringify(v)); return esc(String(v)); };
  const fullSubRows=allSubKeys.map(k=>`<tr><td class="k">${esc(k.replace(/_/g," "))}</td><td class="v"><span class="ro">${fmtVal(a[k])}</span></td></tr>`).join("");
  const fullSubBlock=allSubKeys.length
    ? `<details class="suball"><summary class="kvsec" style="cursor:pointer">Complete submission data — everything sent to Amazon (${allSubKeys.length} fields, read-only)</summary>
        <table class="kv">${fullSubRows}</table></details>`
    : "";
  return `<details open><summary>Full listing data — click any value to edit; saves automatically${nEnum?'. Dropdowns = Amazon allowed values':''}</summary>
    ${imgBlock}
    <div class="kvsec">Identity &amp; offer</div><table class="kv">${idRows}</table>
    <div class="kvsec">Attributes${attrHdr}</div>${schemaDiag(r.product_type, nEnum, allAttrs.length, Object.keys(subs).length, missing, flagged, a)}${(typeof howWorks==="function")?howWorks('required_fields'):""}${hasAttrs?`<table class="kv">${attrRows}</table>`:''}${reqNote}${addCtrl}${rememberBtn}
    <div class="kvsec">Content</div>${(typeof howWorks==="function")?howWorks('content_index'):""}<table class="kv">${cRows}</table>
    ${fullSubBlock}
    <span class="rawtoggle" onclick="var e=document.getElementById('${rid}');e.style.display=(e.style.display==='block'?'none':'block')">show / hide raw JSON</span>
    <pre class="raw" id="${rid}">${esc(JSON.stringify(a,null,2))}</pre>
    ${ (window.SHOW_PAYLOAD_VIEWER===true && r.api_payload && String(r.api_payload).trim())
       ? `<details class="payloadbox"><summary class="kvsec" style="cursor:pointer">\ud83d\udce6 Exact payload sent to Amazon (literal API body from last Preview/Submit, read-only)</summary>
            <div class="payloadnote">This is the verbatim JSON the app sent to Amazon on the last Preview or Submit for this SKU — every word, exactly as transmitted. It does not affect anything; it is for visibility only. You can hide this section in Settings.</div>
            <pre class="raw payloadraw" id="pl_${sidv}">${esc(String(r.api_payload))}</pre>
            <button class="linkbtn" onclick="navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('pl_${sidv}').textContent);toast&&toast('Payload copied')">Copy payload</button>
          </details>`
       : "" }
  </details>`;
}
var AISET=null;
async function loadAISettings(){
  if(AISET) return AISET;
  try{ AISET=await (await fetch('/ai/settings')).json(); }catch(e){ AISET={ok:false}; }
  if(AISET&&AISET.admin){ window.LOGIC_VISIBLE = !!AISET.admin.show_logic && !AISET.admin.preview_as_user; }
  return AISET;
}
function fillModelSelect(sel, models, chosen){
  if(!sel) return;
  sel.innerHTML=(models||[]).map(function(m){
    return '<option value="'+esc(m.id)+'"'+(m.id===chosen?' selected':'')+'>'+esc(m.name||m.id)+'</option>';
  }).join('');
}
async function toggleGen(sidv){
  var p=document.getElementById('genpanel_'+sidv);
  if(p) p.style.display = (p.style.display==='none'?'block':'none');
  var s=await loadAISettings();
  if(!s || !s.ok || !(s.image_models && s.image_models.length)){
    try{ AISET=null; s=await (await fetch('/ai/settings?refresh=1')).json(); AISET=s; }catch(e){}
  }
  if(s&&s.ok){
    fillModelSelect(document.getElementById('gentai_'+sidv), s.text_models, s.select.prompt_enhance);
    fillModelSelect(document.getElementById('geniai_'+sidv), s.image_models, s.select.image_generate);
  }
  // quick connectivity check so the user knows BEFORE generating whether the key works
  var diag=document.getElementById('gendiag_'+sidv);
  if(diag && p && p.style.display!=='none'){
    await _orTestInto(diag);
  }
}
async function doGen(sku, sidv){
  var r=ROWS.find(x=>String(x.sku)===String(sku));
  var title=r?(r.title||''):'';
  var ref=(document.getElementById('genraw_'+sidv)||{}).value||'';
  var brief=(document.getElementById('genbrief_'+sidv)||{}).value||'';
  var tprov=(document.getElementById('gentai_'+sidv)||{}).value||'';
  var iprov=(document.getElementById('geniai_'+sidv)||{}).value||'';
  var useBrand=document.getElementById('genusebrand_'+sidv);
  if(useBrand&&useBrand.checked){ ref='__BRAND_REF__'; }
  var st=document.getElementById('genstatus_'+sidv);
  var btn=document.getElementById('genbtn_'+sidv);
  if(btn){ btn.disabled=true; btn.textContent='Generating…'; }
  if(st){ st.innerHTML='<span class="genspin"></span> Stage 1: writing prompt… then creating image. This can take 30\u201390s \u2014 please wait.'; }
  // elapsed-time ticker so the user sees it IS working
  var t0=Date.now();
  var ticker=setInterval(function(){
    if(st){ var s=Math.round((Date.now()-t0)/1000); var base=st.getAttribute('data-base')||'Working'; st.innerHTML='<span class="genspin"></span> '+base+' \u2014 '+s+'s elapsed'; }
  }, 1000);
  if(st) st.setAttribute('data-base','Generating image');
  try{
    var res=await fetch('/genimage',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brief:brief,reference_image:ref,title:title,text_provider:tprov,image_provider:iprov})});
    var j=await res.json();
    clearInterval(ticker);
    if(btn){ btn.disabled=false; btn.textContent='Generate'; }
    if(!j.ok){
      if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 Failed ('+(j.stage||'')+'): '+esc(j.error||'unknown')+'</span>';
      if(j.detailed_prompt){ var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv); if(pw&&pp){pw.style.display='block'; pp.textContent=j.detailed_prompt;} }
      return;
    }
    if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 Done ('+esc(j.text_provider||'')+' \u2192 '+esc(j.image_provider||'')+') \u2014 review below.</span>';
    var pw=document.getElementById('genpromptwrap_'+sidv); var pp=document.getElementById('genprompt_'+sidv);
    if(pw&&pp){ pw.style.display='block'; pp.textContent=j.detailed_prompt||''; }
    var out=document.getElementById('genresult_'+sidv);
    if(out){
      var _dimtxt=(j.width&&j.height)?(j.width+'×'+j.height+' px'):'';
      var _sztxt=(j.bytes)?_fmtBytes(j.bytes):'';
      var _meta=(_dimtxt||_sztxt)?('<div class="cc" style="margin:4px 0">'+esc([_dimtxt,_sztxt].filter(Boolean).join(' · '))+'</div>'):'';
      out.innerHTML='<div class="genpreview"><img src="'+j.data_url+'">'+_meta+
        '<div class="cc" id="gendrive_'+sidv+'" style="margin:2px 0;color:#86d0a8"></div>'+
        '<div class="genrow">'+
        '<button class="genimgbtn apply" onclick="applyGen(\''+esc(sku)+'\',\''+sidv+'\')">Use as main image</button>'+
        '<button class="genimgbtn" onclick="document.getElementById(\'genresult_'+sidv+'\').innerHTML=\'\'">Discard</button></div></div>';
      out.dataset.img=j.data_url;
    }
    // auto-save the generation into this SKU's media folder (builds the library)
    // AND auto-push to Drive (server does this for kind=generated), then show the link.
    try{
      var sv=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sku:sku,data:j.data_url,kind:'generated'})});
      var svj=await sv.json();
      if(svj.ok && out){
        out.dataset.savedurl=svj.url;
        var dr=document.getElementById('gendrive_'+sidv);
        if(dr){
          if(svj.drive_direct_url){
            dr.innerHTML='\u2713 Saved to Drive \u2014 <a href="'+esc(svj.drive_view_url||svj.drive_direct_url)+'" target="_blank">open</a> '+
              '<span class="cc" style="color:#8a93a6">(Amazon-ready link saved)</span>';
            out.dataset.driveurl=svj.drive_direct_url;
          } else {
            var _de = svj.drive_error ? (' Reason: '+esc(svj.drive_error)) : '';
            dr.innerHTML='<span class="cc" style="color:#e3b768">Saved locally, but NOT uploaded to Drive.'+_de+'</span>';
          }
        }
      }
    }catch(e){}
  }catch(e){
    clearInterval(ticker);
    if(btn){ btn.disabled=false; btn.textContent='Generate'; }
    if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 Error: '+esc(String(e))+'</span>';
  }
}
function uploadMainImage(sku, inp){
  // Upload a LOCAL image as this listing's main image. Chains two existing routes:
  //  1) /media/upload (kind:'main') -> saves + auto-pushes to Drive, returns a
  //     PUBLIC drive_direct_url Amazon can fetch.
  //  2) /edit -> writes that public URL onto the row's main_product_image_locator,
  //     so the next Preview/Submit sends YOUR clean image instead of the source one.
  const f = inp && inp.files && inp.files[0];
  if(!f){ return; }
  if(!/^image\//.test(f.type||"")){ toast("Please choose an image file"); inp.value=""; return; }
  const rd = new FileReader();
  rd.onload = async () => {
    toast("Uploading main image…");
    try{
      const up = await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, data:rd.result, name:f.name, kind:"main"})})).json();
      if(!up || !up.ok){ toast("Upload failed: "+((up&&up.error)||"unknown")); return; }
      const pub = up.drive_direct_url || "";
      if(!pub){ toast("Uploaded, but no public URL"+(up.drive_error?(" ("+up.drive_error+")"):"")+". Set the account's Drive folder so Amazon can fetch it."); return; }
      const sv = await (await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, target:"attr", key:"main_product_image_locator", value:pub})})).json();
      if(sv && sv.ok){ toast("Main image set ✓ — Preview/Submit to send it to Amazon"); loadRows(); }
      else { toast("Image hosted but couldn't save to the row: "+((sv&&sv.error)||"")); }
    }catch(e){ toast("Upload error: "+((e&&e.message)||e)); }
    finally { if(inp) inp.value=""; }
  };
  rd.readAsDataURL(f);
}
async function pushImageLive(sku, btn){
  var r=(ROWS||[]).find(x=>String(x.sku)===String(sku));
  if(!r){ toast('Listing not found'); return; }
  if(!confirm("Send the current main image to the LIVE Amazon listing for "+sku+"?\n\nThis updates ONLY the main image on Amazon (no full resubmit). Amazon must be able to fetch the image, so it will be uploaded to your Drive and made public if it isn't already.")) return;
  var old = btn?btn.textContent:'';
  if(btn){ btn.disabled=true; btn.textContent='Pushing…'; }
  try{
    var res=await fetch('/listing/push_image',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({confirmed:true, sku:sku,
        marketplace:(typeof WS_MARKET!=='undefined'?WS_MARKET:''),
        product_type:(r.product_type||''),
        id:(CUR_ACCOUNT&&CUR_ACCOUNT.id)||''})});
    var j=await res.json();
    if(j.ok){
      toast('✓ Image sent to Amazon ('+(j.status||'accepted')+'). Amazon takes a few minutes to show it.');
    } else {
      var extra = (j.issues&&j.issues.length)?(' — '+j.issues.map(function(i){return (i.message||i.code||'');}).join('; ')):'';
      toast('Could not push image: '+(j.error||'unknown')+extra);
    }
  }catch(e){ toast('Push failed: '+e); }
  finally{ if(btn){ btn.disabled=false; btn.textContent=old||'Push image to live'; } }
}
async function applyGen(sku, sidv){
  var out=document.getElementById('genresult_'+sidv);
  var dataUrl=out?out.dataset.img:'';
  if(!dataUrl){ toast('No generated image to apply'); return; }
  // prefer the saved file URL (real hosted path) over the inline data URL
  var savedUrl=out?out.dataset.savedurl:'';
  var useUrl=savedUrl||dataUrl;
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:'main_product_image_locator',value:useUrl})});
    toast(savedUrl?'Set as main image (saved to media)':'Set as main image');
    loadRows();
  }catch(e){ toast('Could not apply: '+e); }
}
// ===== Miles template main-image builder (overlay text on blank template) =====
let MILES_TPLS = null;
async function _loadMilesTpls(){
  if(MILES_TPLS) return MILES_TPLS;
  try{ var j=await (await fetch('/miles_template/list')).json(); MILES_TPLS=(j&&j.templates)||[]; }
  catch(e){ MILES_TPLS=[]; }
  return MILES_TPLS;
}
function milesTemplatePanel(sku, sidv){
  return `<div class="genimg" id="milestpl_${sidv}">
    <div class="kvsec" style="color:#7fd0ff;margin-top:14px"><i class="ti ti-stack"></i> Miles template main image</div>
    <div class="genpanel" style="display:block">
      <div class="cc" style="margin-bottom:6px">Overlay product text onto your blank Miles template — pixel-faithful, no AI. <a href="#" onclick="openMilesTplManager();return false" style="color:#9cc1ff">Manage templates</a></div>
      <div class="genrow">
        <span class="cc">Template:</span>
        <select class="ed" id="mtpl_${sidv}" style="flex:1" onfocus="refreshMilesDropdowns()"><option value="">— loading templates —</option></select>
      </div>
      <div class="genrow">
        <span class="cc">Title:</span>
        <input class="ed geninput" id="mtitle_${sidv}" style="flex:1" placeholder="VOLTAGE II">
      </div>
      <div class="cc" style="margin:6px 0 2px">Subtitle lines <button class="genimgbtn" style="padding:2px 8px" onclick="milesAddLine('${sidv}')">+ add line</button></div>
      <div id="msubs_${sidv}"></div>
      <div class="cc" style="margin:8px 0 2px;opacity:.7">CHOICE OF MECHANICS — fixed (always shown)</div>
      <div class="genrow">
        <span class="cc">Application:</span>
        <input class="ed geninput" id="mapp_${sidv}" style="flex:1" placeholder="HYDRAULIC FLUID">
        <label class="cc" style="white-space:nowrap"><input type="checkbox" id="mappL_${sidv}" checked> 2 lines</label>
      </div>
      <div class="genrow" style="margin-top:8px">
        <button class="genimgbtn apply" id="mbtn_${sidv}" onclick="milesRender('${esc(sku)}','${sidv}')">Generate template image</button>
        <button class="genimgbtn" id="maibtn_${sidv}" onclick="milesAiFill('${esc(sku)}','${sidv}')" title="Let AI fill the title, grade and application from the listing"><i class="ti ti-sparkles"></i> AI fill text</button>
        <span class="cc" id="mstatus_${sidv}"></span>
      </div>
      <div id="mresult_${sidv}"></div>
    </div>
  </div>`;
}
// populate the template dropdown + seed two subtitle lines when the drawer opens
async function initMilesPanel(sidv){
  var sel=document.getElementById('mtpl_'+sidv); if(!sel) return;
  var tpls=await _loadMilesTpls();
  sel.innerHTML = tpls.length
    ? tpls.map(t=>`<option value="${esc(t.id)}">${esc(t.label)} (${esc(t.container)})</option>`).join("")
    : '<option value="">no templates yet — click Manage templates to upload</option>';
  var box=document.getElementById('msubs_'+sidv);
  if(box && !box.children.length){ milesAddLine(sidv,'ELECTRICAL INSULATING'); milesAddLine(sidv,'OIL TYPE II INHIBITED'); }
}
function milesAddLine(sidv, val){
  var box=document.getElementById('msubs_'+sidv); if(!box) return;
  var i=box.children.length;
  var row=document.createElement('div'); row.className='genrow'; row.style.marginBottom='4px';
  row.innerHTML=`<input class="ed geninput msubin" style="flex:1" value="${esc(val||'')}" placeholder="subtitle line">
    <label class="cc" style="white-space:nowrap"><input type="checkbox" class="msub2" checked> 2 lines</label>
    <button class="genimgbtn" style="padding:2px 8px" onclick="this.parentNode.remove()">−</button>`;
  box.appendChild(row);
}
async function milesAiFill(sku, sidv){
  var r=ROWS.find(x=>String(x.sku)===String(sku));
  var st=document.getElementById('mstatus_'+sidv);
  var btn=document.getElementById('maibtn_'+sidv);
  if(btn) btn.disabled=true;
  if(st) st.innerHTML='<span class="genspin"></span> AI reading listing…';
  try{
    var body={ sku:sku,
      title:(r&&r.title)||'',
      bullets:(r&&(r.bullets||[]).join(' \u2022 '))||'',
      specs:(r&&(r.search_terms||''))||'' };
    var j=await (await fetch('/miles_template/ai_fill',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)})).json();
    if(btn) btn.disabled=false;
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 '+esc(j.error||'failed')+'</span>'; return; }
    var sp=j.spec||{};
    // fill title
    var t=document.getElementById('mtitle_'+sidv); if(t) t.value=(sp.title||'');
    // rebuild subtitle lines from the AI's grade
    var box=document.getElementById('msubs_'+sidv);
    if(box){ box.innerHTML=''; (sp.subtitles||[]).forEach(function(s){ milesAddLine(sidv, s.text); }); }
    // fill application
    var ap=document.getElementById('mapp_'+sidv); if(ap) ap.value=((sp.application||{}).text||'');
    var apL=document.getElementById('mappL_'+sidv); if(apL) apL.checked=(((sp.application||{}).lines||2)>=2);
    if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 AI filled — review &amp; Generate</span>';
  }catch(e){ if(btn) btn.disabled=false; if(st) st.innerHTML='<span style="color:#ef9a9a">\u2717 '+esc(String(e))+'</span>'; }
}
async function milesRender(sku, sidv){
  var tid=(document.getElementById('mtpl_'+sidv)||{}).value||'';
  if(!tid){ toast('Upload/select a Miles template first'); return; }
  var title=(document.getElementById('mtitle_'+sidv)||{}).value||'';
  var subs=[...document.querySelectorAll('#msubs_'+sidv+' .genrow')].map(function(rw){
    var t=rw.querySelector('.msubin'); var c=rw.querySelector('.msub2');
    return {text:(t&&t.value)||'', lines:(c&&c.checked)?2:1};
  }).filter(s=>s.text.trim());
  var app=(document.getElementById('mapp_'+sidv)||{}).value||'';
  var appL=(document.getElementById('mappL_'+sidv)||{}).checked?2:1;
  var st=document.getElementById('mstatus_'+sidv);
  var btn=document.getElementById('mbtn_'+sidv);
  if(btn){ btn.disabled=true; }
  if(st){ st.innerHTML='<span class="genspin"></span> rendering…'; }
  try{
    var j=await (await fetch('/miles_template/render',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({template_id:tid, sku:sku, spec:{title:title, subtitles:subs, application:{text:app, lines:appL}}})})).json();
    if(btn){ btn.disabled=false; }
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#ef9a9a">✗ '+esc(j.error||'failed')+'</span>'; return; }
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ rendered</span>';
    var out=document.getElementById('mresult_'+sidv);
    if(out){
      out.dataset.savedurl=j.url||'';
      out.dataset.dataurl=j.data_url||'';
      out.innerHTML='<div class="genpreview"><img src="'+(j.data_url||j.url)+'" style="max-width:320px">'+
        '<div class="genrow"><button class="genimgbtn apply" onclick="milesApply(\''+esc(sku)+'\',\''+sidv+'\')">Use as main image</button>'+
        '<button class="genimgbtn" onclick="milesDownload(\''+esc(sku)+'\',\''+sidv+'\')"><i class="ti ti-download"></i> Download</button>'+
        '<button class="genimgbtn" onclick="document.getElementById(\'mresult_'+sidv+'\').innerHTML=\'\'">Discard</button></div></div>';
    }
  }catch(e){ if(btn){btn.disabled=false;} if(st) st.innerHTML='<span style="color:#ef9a9a">✗ '+esc(String(e))+'</span>'; }
}
function milesDownload(sku, sidv){
  var out=document.getElementById('mresult_'+sidv);
  var url=out?out.dataset.savedurl:'';
  if(!url){ toast('Nothing to download'); return; }
  // download the full-resolution saved image, named by its REAL extension (the
  // saved file already has the correct format suffix) so Amazon accepts it.
  var _m=String(url).split("?")[0].match(/\.(png|jpe?g|webp|gif)$/i);
  var _ext=_m?(_m[1].toLowerCase()==="jpeg"?"jpg":_m[1].toLowerCase()):"jpg";
  var a=document.createElement('a');
  a.href=url; a.download=(sku||'miles')+'_main.'+_ext;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}
async function milesApply(sku, sidv){
  var out=document.getElementById('mresult_'+sidv);
  var url=out?out.dataset.savedurl:'';
  if(!url){ toast('Nothing to apply'); return; }
  try{
    await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:sku,target:'attr',key:'main_product_image_locator',value:url})});
    toast('Set as main image'); loadRows();
  }catch(e){ toast('Could not apply: '+e); }
}
// ===== Visual zone editor: drag boxes onto the template to place text =====
let ZE_STATE = null;
// ===== Advanced visual zone editor =====
// Zone object: {key, label, color, box:[x0,y0,x1,y1], align, bold, size, text, builtin}
function _defaultZones(){
  return [
    {key:'title',       label:'TITLE',          color:'#4c8dff', box:[0.07,0.33,0.40,0.42], align:'left',   bold:true,  size:1.0, builtin:true},
    {key:'grade',       label:'GRADE',          color:'#ffd479', box:[0.07,0.50,0.40,0.56], align:'center', bold:true,  size:1.0, builtin:true},
    {key:'choice',      label:'CHOICE (fixed)', color:'#9aa0aa', box:[0.07,0.565,0.40,0.60],align:'center', bold:false, size:1.0, builtin:true},
    {key:'application', label:'APPLICATION',    color:'#7fd99a', box:[0.07,0.78,0.40,0.88], align:'left',   bold:true,  size:1.0, builtin:true}
  ];
}
function _zonesToArray(saved){
  // accept either the new dict-of-objects or legacy dict-of-arrays
  var def=_defaultZones(); var byKey={}; def.forEach(z=>byKey[z.key]=z);
  if(!saved) return def;
  var out=[];
  Object.keys(saved).forEach(function(k){
    var v=saved[k]; var base=byKey[k]||{key:k,label:k.toUpperCase(),color:'#c792ea',builtin:false};
    if(Array.isArray(v)){ out.push(Object.assign({},base,{box:v,align:base.align||'left',bold:base.bold!==false,size:1.0,text:''})); }
    else { out.push(Object.assign({},base,{box:v.box,align:v.align||'left',bold:v.bold!==false,size:v.size||1.0,text:v.text||''})); }
  });
  // ensure builtins exist
  def.forEach(function(d){ if(!out.find(z=>z.key===d.key)) out.push(d); });
  return out;
}
function _zonesToSave(){
  var o={};
  ZE_STATE.zones.forEach(function(z){
    o[z.key]={box:z.box, align:z.align, bold:z.bold, size:z.size, text:z.text||''};
  });
  return o;
}
async function openZoneEditor(tid){
  var tpls=await (await fetch('/miles_template/list')).json().catch(()=>({templates:[]}));
  var t=(tpls.templates||[]).find(x=>x.id===tid);
  if(!t){ toast('Template not found'); return; }
  ZE_STATE={tid:tid, zones:_zonesToArray(t.zones), erase:(t.erase||[]), sel:null, tool:'move'};
  renderZoneEditor();
}
function renderZoneEditor(){
  var tid=ZE_STATE.tid;
  var html=`<div style="display:flex;gap:14px;flex-wrap:wrap">
    <div style="flex:1;min-width:300px">
      <div style="font-weight:600;margin-bottom:6px">Design the panel — drag boxes, edit each on the right</div>
      <div class="cc" style="margin-bottom:6px">Tools:
        <button class="genimgbtn ${ZE_STATE.tool==='move'?'apply':''}" onclick="zeTool('move')">Move/Resize</button>
        <button class="genimgbtn ${ZE_STATE.tool==='erase'?'apply':''}" onclick="zeTool('erase')">Eraser (drag to cover badge)</button>
      </div>
      <div id="zewrap" style="position:relative;display:inline-block;max-width:100%;user-select:none;border:1px solid #2a3344">
        <img id="zeimg" src="/miles_template/preview/${esc(tid)}" style="display:block;max-width:100%;max-height:56vh">
      </div>
      <div class="genrow" style="margin-top:10px">
        <button class="primary" onclick="saveZones()">Save</button>
        <span id="zesaved" style="display:none;color:#7fd99a;font-size:12px;margin-left:6px"></span>
        <button class="genimgbtn" onclick="zonePreview()">Preview with sample text</button>
        <button class="genimgbtn" onclick="zeAddZone()">+ Add text box</button>
        <button class="genimgbtn" onclick="openMilesTplManager()">Back</button>
      </div>
      <div id="zepreview" style="margin-top:10px"></div>
    </div>
    <div id="zeside" style="width:230px;flex-shrink:0"></div>
  </div>`;
  document.getElementById("acctmodalbody").innerHTML=html;
  document.getElementById("acctmodal").classList.add("open");
  setTimeout(function(){ zeDrawBoxes(); zeRenderSide(); }, 60);
}
function zeTool(t){ ZE_STATE.tool=t; renderZoneEditor(); }
function zeAddZone(){
  var n=ZE_STATE.zones.filter(z=>!z.builtin).length+1;
  ZE_STATE.zones.push({key:'custom'+Date.now(), label:'TEXT '+n, color:'#c792ea',
    box:[0.07,0.62,0.40,0.68], align:'center', bold:true, size:1.0, text:'TEXT', builtin:false});
  renderZoneEditor();
}
function zeDelZone(key){
  ZE_STATE.zones=ZE_STATE.zones.filter(z=>z.key!==key);
  if(ZE_STATE.sel===key) ZE_STATE.sel=null;
  renderZoneEditor();
}
function zeDrawBoxes(){
  var img=document.getElementById('zeimg'), wrap=document.getElementById('zewrap');
  if(!img||!wrap) return;
  function draw(){
    var iw=img.clientWidth, ih=img.clientHeight;
    // remove old
    wrap.querySelectorAll('.zebox,.zeerase').forEach(e=>e.remove());
    // erase rectangles
    (ZE_STATE.erase||[]).forEach(function(e,i){
      var d=document.createElement('div'); d.className='zeerase';
      d.style.left=(e[0]*iw)+'px'; d.style.top=(e[1]*ih)+'px';
      d.style.width=((e[2]-e[0])*iw)+'px'; d.style.height=((e[3]-e[1])*ih)+'px';
      d.innerHTML='<span class="zex" onclick="ZE_STATE.erase.splice('+i+',1);renderZoneEditor()">×</span>';
      wrap.appendChild(d);
    });
    // text zones with live text
    ZE_STATE.zones.forEach(function(z){
      var bx=document.createElement('div'); bx.className='zebox'+(ZE_STATE.sel===z.key?' sel':'');
      bx.dataset.zone=z.key; bx.style.borderColor=z.color;
      bx.style.left=(z.box[0]*iw)+'px'; bx.style.top=(z.box[1]*ih)+'px';
      bx.style.width=((z.box[2]-z.box[0])*iw)+'px'; bx.style.height=((z.box[3]-z.box[1])*ih)+'px';
      var shown = z.key==='choice'?'CHOICE OF MECHANICS':(z.builtin?z.label:(z.text||z.label));
      bx.style.justifyContent = 'flex-start';   // render is always left-aligned
      bx.innerHTML='<span class="zelbl" style="background:'+z.color+'">'+esc(z.label)+'</span>'+
        '<span class="zetext" style="font-weight:'+(z.bold?'700':'500')+'">'+esc(shown)+'</span>'+
        '<span class="zegrip"></span>';
      wrap.appendChild(bx);
    });
    zeBind();
  }
  if(!img.complete){ img.onload=draw; } else draw();
}
function zeBind(){
  var img=document.getElementById('zeimg'), wrap=document.getElementById('zewrap');
  var iw=img.clientWidth, ih=img.clientHeight;
  // eraser: drag a new rectangle
  if(ZE_STATE.tool==='erase'){
    wrap.onmousedown=function(e){
      if(e.target!==img && !e.target.classList.contains('zetext')) { /* allow */ }
      var r=img.getBoundingClientRect();
      var sx=(e.clientX-r.left)/iw, sy=(e.clientY-r.top)/ih;
      var box=[sx,sy,sx,sy];
      function mv(ev){ box[2]=(ev.clientX-r.left)/iw; box[3]=(ev.clientY-r.top)/ih; zeTempErase(box); }
      function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up);
        var x0=Math.min(box[0],box[2]),y0=Math.min(box[1],box[3]),x1=Math.max(box[0],box[2]),y1=Math.max(box[1],box[3]);
        if(x1-x0>0.01&&y1-y0>0.01){ ZE_STATE.erase.push([x0,y0,x1,y1]); }
        renderZoneEditor();
      }
      document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
    };
    return;
  }
  wrap.onmousedown=null;
  // move/resize boxes
  wrap.querySelectorAll('.zebox').forEach(function(bx){
    bx.addEventListener('mousedown', function(e){
      e.preventDefault(); e.stopPropagation();
      ZE_STATE.sel=bx.dataset.zone; zeRenderSide();
      var z=ZE_STATE.zones.find(zz=>zz.key===bx.dataset.zone); if(!z) return;
      var isGrip=e.target.classList.contains('zegrip');
      var sX=e.clientX, sY=e.clientY, ob=z.box.slice();
      function mv(ev){
        var dx=(ev.clientX-sX)/iw, dy=(ev.clientY-sY)/ih;
        if(isGrip){ z.box=[ob[0],ob[1],Math.min(1,ob[2]+dx),Math.min(1,ob[3]+dy)]; }
        else { var w=ob[2]-ob[0],h=ob[3]-ob[1];
          var nx=Math.max(0,Math.min(1-w,ob[0]+dx)), ny=Math.max(0,Math.min(1-h,ob[1]+dy));
          z.box=[nx,ny,nx+w,ny+h]; }
        bx.style.left=(z.box[0]*iw)+'px'; bx.style.top=(z.box[1]*ih)+'px';
        bx.style.width=((z.box[2]-z.box[0])*iw)+'px'; bx.style.height=((z.box[3]-z.box[1])*ih)+'px';
      }
      function up(){ document.removeEventListener('mousemove',mv); document.removeEventListener('mouseup',up); }
      document.addEventListener('mousemove',mv); document.addEventListener('mouseup',up);
    });
  });
}
function zeTempErase(box){
  var img=document.getElementById('zeimg'), wrap=document.getElementById('zewrap');
  var iw=img.clientWidth, ih=img.clientHeight;
  var t=wrap.querySelector('.zetmp'); if(!t){ t=document.createElement('div'); t.className='zeerase zetmp'; wrap.appendChild(t); }
  var x0=Math.min(box[0],box[2]),y0=Math.min(box[1],box[3]);
  t.style.left=(x0*iw)+'px'; t.style.top=(y0*ih)+'px';
  t.style.width=(Math.abs(box[2]-box[0])*iw)+'px'; t.style.height=(Math.abs(box[3]-box[1])*ih)+'px';
}
function zeRenderSide(){
  var side=document.getElementById('zeside'); if(!side) return;
  var z=ZE_STATE.zones.find(zz=>zz.key===ZE_STATE.sel);
  if(!z){ side.innerHTML='<div class="cc">Click a box to edit its style.</div>'; return; }
  side.innerHTML=`<div style="font-weight:600;margin-bottom:8px">${esc(z.label)}</div>
    ${z.builtin?'':`<div class="genrow"><span class="cc">Text:</span><input class="ed" style="flex:1" value="${esc(z.text||'')}" oninput="zeSet('text',this.value)"></div>`}
    <div class="genrow" style="margin-top:6px"><label class="cc"><input type="checkbox" ${z.bold?'checked':''} onchange="zeSet('bold',this.checked)"> Bold</label></div>
    <div class="genrow" style="margin-top:6px"><span class="cc">Max size:</span>
      <input type="range" min="0.3" max="1" step="0.05" value="${z.size||1}" oninput="zeSet('size',parseFloat(this.value))" style="flex:1">
    </div>
    ${z.builtin?'':`<button class="del" style="margin-top:8px" onclick="zeDelZone('${z.key}')">Remove this box</button>`}
    <div class="cc" style="margin-top:10px;font-size:11px">Tip: drag the box on the left to move; drag its corner to resize.</div>`;
}
function zeSet(prop,val){
  var z=ZE_STATE.zones.find(zz=>zz.key===ZE_STATE.sel); if(!z) return;
  z[prop]=val; zeDrawBoxes(); zeRenderSide();
}
async function saveZones(){
  if(!ZE_STATE){ alert('Open a template first'); return; }
  var btn=event&&event.target;
  if(btn){ btn.disabled=true; btn.textContent='Saving…'; }
  try{
    var j=await (await fetch('/miles_template/save_zones',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:ZE_STATE.tid, zones:_zonesToSave(), erase:ZE_STATE.erase})})).json();
    if(btn){ btn.disabled=false; btn.textContent='Save'; }
    if(j.ok){
      MILES_TPLS=null;
      var s=document.getElementById('zesaved');
      if(s){ s.textContent='✓ Saved — every product on this template now uses this layout'; s.style.display='inline'; }
      if(typeof toast==='function') toast('Zones saved');
    } else {
      alert('Save failed: '+(j.error||'unknown'));
    }
  }catch(e){ if(btn){btn.disabled=false; btn.textContent='Save';} alert('Save error: '+e); }
}
async function zonePreview(){
  if(!ZE_STATE) return;
  var box=document.getElementById('zepreview');
  if(box) box.innerHTML='<span class="genspin"></span> rendering…';
  var j=await (await fetch('/miles_template/render',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({template_id:ZE_STATE.tid, sku:'_zonetest',
      spec:{title:'INDUSTIAL GEAR OIL', subtitles:[{text:'80W-90',lines:1}],
        application:{text:'HYDRAULIC FLUID',lines:2}, zones:_zonesToSave(), erase:ZE_STATE.erase}})})).json();
  if(box) box.innerHTML = j.ok ? '<img src="'+(j.data_url||j.url)+'" style="max-width:300px;border:1px solid #2a3344">'
    : '<span style="color:#ef9a9a">'+esc(j.error||'failed')+'</span>';
}
async function openMilesTplManager(){
  var tpls=await (await fetch('/miles_template/list')).json().catch(()=>({templates:[]}));
  var list=(tpls.templates||[]).map(t=>`<tr><td><img src="/miles_template/preview/${esc(t.id)}" style="height:48px"></td>`+
    `<td>${esc(t.label)}</td><td>${esc(t.container)}</td>`+
    `<td>${t.zones?'<span style="color:#7fd99a">✓ zones set</span>':'<span class="cc">no zones</span>'}</td>`+
    `<td><button class="primary" style="padding:3px 8px" onclick="openZoneEditor('${esc(t.id)}')">Edit zones</button> `+
    `<button class="del" onclick="milesTplDelete('${esc(t.id)}')">Delete</button></td></tr>`).join("")
    || '<tr><td colspan="5" class="cc">No templates yet.</td></tr>';
  var html=`<div style="font-weight:600;margin-bottom:8px">Miles blank templates</div>
    <table class="kv"><tr><td class="k">Label</td><td class="v"><input class="ed" id="mtm_label" placeholder="e.g. Drum 55gal"></td></tr>
    <tr><td class="k">Container</td><td class="v"><select class="ed" id="mtm_cont"><option value="pail">Pail (5 gal)</option><option value="drum">Drum (55 gal)</option></select></td></tr>
    <tr><td class="k">Blank PNG</td><td class="v"><input type="file" id="mtm_file" accept="image/png,image/jpeg"></td></tr></table>
    <button class="primary" style="margin:8px 0" onclick="milesTplUpload()">Upload template</button>
    <table class="kv" style="margin-top:10px">${list}</table>`;
  var m=document.getElementById("acctmodal");
  document.getElementById("acctmodalbody").innerHTML=html; m.classList.add("open");
}
async function milesTplUpload(){
  var f=(document.getElementById('mtm_file')||{}).files;
  if(!f||!f.length){ toast('Choose a PNG'); return; }
  var label=(document.getElementById('mtm_label')||{}).value||'Template';
  var cont=(document.getElementById('mtm_cont')||{}).value||'drum';
  var rd=new FileReader();
  rd.onload=async function(){
    try{
      var j=await (await fetch('/miles_template/upload',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({label:label, container:cont, data:rd.result})})).json();
      if(j.ok){ toast('Template uploaded'); MILES_TPLS=null; await refreshMilesDropdowns(); openMilesTplManager(); }
      else toast('Upload failed: '+(j.error||''));
    }catch(e){ toast('Error: '+e); }
  };
  rd.readAsDataURL(f[0]);
}
// Re-populate every open Miles template dropdown in the drawer with the latest list.
async function refreshMilesDropdowns(){
  MILES_TPLS=null;
  var tpls=await _loadMilesTpls();
  document.querySelectorAll('select[id^="mtpl_"]').forEach(function(sel){
    var cur=sel.value;
    sel.innerHTML = tpls.length
      ? tpls.map(t=>`<option value="${esc(t.id)}">${esc(t.label)} (${esc(t.container)})</option>`).join("")
      : '<option value="">no templates yet — click Manage templates to upload</option>';
    if(cur) sel.value=cur;
  });
}
async function milesTplDelete(id){
  if(!confirm('Delete this template?')) return;
  await fetch('/miles_template/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
  MILES_TPLS=null; toast('Deleted'); await refreshMilesDropdowns(); openMilesTplManager();
}
function askAbout(sku){
  var w=document.getElementById("chatwrap"); if(!w) return;
  w.classList.add("open"); fillChatCtx();
  var sel=document.getElementById("chatctx"); if(sel) sel.value=sku;
  setTimeout(function(){var i=document.getElementById("chatinput"); if(i) i.focus();},60);
}
async function submitLive(){
  // PRECHECK: catch local /media images Amazon can't fetch, before submitting.
  try{
    const pc=await (await fetch('/submit/precheck')).json();
    if(pc && pc.ok && pc.count>0){
      const skus=pc.local_image_rows.map(x=>x.sku).join(", ");
      alert("⚠ "+pc.count+" listing(s) have a LOCAL image that Amazon cannot fetch:\n\n  "+skus+"\n\n"
        +"AI images saved to your media library live on your PC (127.0.0.1), so Amazon's servers can't reach them. "
        +"These rows will FAIL with 'Unable to Retrieve Media Content'.\n\n"
        +"Fix: use a publicly-hosted image URL for the main image (e.g. upload to a host, or use the source image URL), "
        +"then submit again. The other rows can still go through.");
      if(!confirm("Submit anyway? (the local-image rows above will error)")) return;
    }
  }catch(e){}
  // SAFETY: confirm WHICH Amazon account this will publish to, by name.
  let t;
  try{ t=await (await fetch('/submit/target')).json(); }catch(e){ t=null; }
  if(!t || !t.ok){
    if(!confirm("Could not determine the target account. Submit anyway to your live account?")) return;
  } else {
    if(t.block==='none'){
      alert("This view is set to the "+t.marketplace+" marketplace, but no credentials are configured for it. Nothing will be submitted. Add the account's SP-API credentials first.");
      return;
    }
    var _sel = selectedSkus();
    var _scope = _sel.length
      ? ("the "+_sel.length+" SELECTED listing(s):\n    "+_sel.join(", ")+"\n")
      : "every APPROVED / API_READY row in THIS view";
    var msg = "PUBLISH LIVE \u2014 confirm the destination account:\n\n"
      + "  Account:    "+t.account_label+"\n"
      + (t.seller_id?("  Seller ID:  "+t.seller_id+"\n"):"")
      + "  Marketplace: "+t.marketplace+"\n"
      + "  Workspace:  "+t.view+"\n\n"
      + "This will CREATE or REPLACE live listings for "+_scope+", on the account above.\n"
      + "(Already-live listings are skipped automatically.)\n\nIs this the correct account?";
    if(!confirm(msg)) return;
  }
  // Scope the submit to the user's SELECTION when there is one; otherwise fall back
  // to all approved/ready rows (the server's default).
  var _sel2 = selectedSkus();
  if(_sel2.length) runMode('api_submit', _sel2);
  else runMode('api_submit');
}
function isEmptyRow(r){
  const s=x=>String(x==null?"":x).trim();
  return !s(r.sku)&&!s(r.title)&&!s(r.asin)&&!s(r.product_type)&&!s(r.price);
}
function render(){
  const grid=document.getElementById("grid");
  const list=ROWS.filter(passFilter);
  const empties=list.filter(isEmptyRow);
  const realAll=list.filter(r=>!isEmptyRow(r));
  const _norm = v => String(v||"").trim().toUpperCase();
  // Use the shared isActuallyLive() so render() and summary() ALWAYS agree.
  // Before this fix, render() had inline logic while summary() did not, so a
  // row displayed under "Live on Amazon" was still counted as HOLD in the top
  // bar. Any future changes to the "is this live?" rule need only edit
  // isActuallyLive() -- both callers pick up the fix automatically.
  const sets = _liveCatSetsForCurrentView();
  const _liveCatSkus  = sets.skus;
  const _liveCatAsins = sets.asins;
  const _liveGroupShown = sets.liveGroupShown;
  const _isActuallyLive = r => isActuallyLive(r, _liveCatSkus, _liveCatAsins, _liveGroupShown);
  const real     = realAll.filter(r=>!_isActuallyLive(r));
  const liveRows = realAll.filter(r=> _isActuallyLive(r));
  const note = empties.length
    ? `<div class="emptynote">${empties.length} empty row${empties.length>1?'s':''} hidden — <button class="linkbtn" onclick="clearEmpty(this)">clear them from the sheet</button></div>`
    : "";
  // SOURCE: drafts (app rows) / live (Amazon catalog) / all (both)
  let draftHtml = real.length ? real.map(card).join("") : "";
  // DEDUPE: the same SKU can exist BOTH as an app row marked LIVE and as an
  // Amazon-catalog tile (fetched from Seller Central). Showing both makes one
  // real listing appear twice. Prefer the app row (it has the edit controls +
  // "Push image to live"), and drop any catalog tile whose SKU/ASIN already
  // appears as a LIVE app row.
  const liveAppSkus = new Set(liveRows.map(r=>_norm(r.sku)));
  const liveAppAsins = new Set(liveRows.map(r=>_norm(r.asin)).filter(Boolean));
  const liveCatalog = (LIVE_ITEMS||[]).filter(it=>{
    const s=_norm(it.sku), a=_norm(it.asin);
    if(s && liveAppSkus.has(s)) return false;   // same SKU already shown as app row
    if(a && liveAppAsins.has(a)) return false;  // or same ASIN
    return true;
  });
  // live group = app rows already submitted (status LIVE) + non-duplicate catalog tiles
  let liveHtml  = (liveRows.length ? liveRows.map(card).join("") : "")
                + (liveCatalog.length ? liveCatalog.map(liveTile).join("") : "");
  if(LIST_SOURCE==="live"){
    grid.innerHTML = liveHtml || `<div class="empty">No live listings loaded yet.${CUR_ACCOUNT?(WS_MARKET?` <button class="mktbtn on" style="margin-left:8px" onclick="loadLiveCatalog(true)">Fetch ${esc(WS_MARKET)} live listings now</button>`:' Select a marketplace first.'):' Open an Amazon account workspace.'}</div>`;
  } else if(LIST_SOURCE==="all"){
    grid.innerHTML = note
      + (draftHtml?('<div class="srcgroup">Drafts (in this app)</div>'+draftHtml):'')
      + (liveHtml?('<div class="srcgroup">Live on Amazon</div>'+liveHtml):'')
      + ((!draftHtml&&!liveHtml)?'<div class="empty">Nothing to show yet.</div>':'');
  } else {
    // default view: show drafts, then any already-live (submitted) app rows,
    // each under a clear heading, so a submitted listing is visible but not
    // mislabeled as a draft.
    const liveAppHtml = liveRows.length ? liveRows.map(card).join("") : "";
    grid.innerHTML = note
      + (draftHtml?('<div class="srcgroup">Drafts (in this app)</div>'+draftHtml):'')
      + (liveAppHtml?('<div class="srcgroup">Live on Amazon</div>'+liveAppHtml):'')
      + ((!draftHtml&&!liveAppHtml)?(empties.length ? "" : `<div class="empty">No listings in this view.${ROWS.length?'':' Run Generate to create some.'}</div>`):'');
  }
  summary();
  // fetch real product images for live tiles that don't have one yet
  if((LIST_SOURCE==="live"||LIST_SOURCE==="all") && LIVE_ITEMS.length){ fetchLiveImages(); }
  // keep an open drawer in sync with refreshed data -- BUT never while a per-
  // listing Preview/Submit run is streaming into the drawer panel, or the panel
  // (and its live log) would be wiped mid-run.
  if(DRAWER_SKU && !window.RUN_STREAMING){
    var dr=ROWS.find(x=>String(x.sku)===String(DRAWER_SKU));
    if(dr){ var b=document.getElementById("drawerbody"); if(b) b.innerHTML=drawerContent(dr); }
    else closeDrawer();
  }
}
async function delRow(sku, row, btn){
  if(!confirm("Delete this row from the sheet? This cannot be undone.")) return;
  btn.disabled=true;
  try{
    const res=await fetch("/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sku:sku,row:row})});
    const j=await res.json();
    if(j.ok){ toast("Row deleted"); loadRows(); }
    else{ toast("Delete failed: "+(j.error||"")); btn.disabled=false; }
  }catch(e){ toast("Delete failed"); btn.disabled=false; }
}
async function bulkStatus(status){
  const skus=selectedSkus();
  if(!skus.length){ toast("Nothing selected"); return; }
  // normalise: the sheet uses NEEDS_REVIEW for "hold"
  if(status==="HOLD") status="NEEDS_REVIEW";
  const label = status==="APPROVED" ? "Approve" : "Hold";
  if(!confirm(label+" "+skus.length+" selected listing(s)?")) return;
  let ok=0, fail=0;
  toast(label+"ing "+skus.length+"…");
  for(const sku of skus){
    try{
      const res=await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},
                  body:JSON.stringify({sku:sku, status:status})});
      const j=await res.json();
      if(j.ok) ok++; else fail++;
    }catch(e){ fail++; }
  }
  toast(label+"d "+ok+(fail?(" / "+fail+" failed"):""));
  clearSelection(); loadRows();
}
async function bulkDelete(){
  const skus=selectedSkus();
  if(!skus.length){ toast("Nothing selected"); return; }
  if(!confirm("Delete "+skus.length+" selected listing(s) from the sheet? This cannot be undone.")) return;
  let ok=0, fail=0;
  toast("Deleting "+skus.length+"…");
  // delete from the BOTTOM up so row numbers don't shift mid-loop
  const items=skus.map(s=>{const r=ROWS.find(x=>String(x.sku)===String(s)); return {sku:s, row:(r&&r.row)||null};})
                  .sort((a,b)=>(b.row||0)-(a.row||0));
  for(const it of items){
    try{
      const res=await fetch("/delete",{method:"POST",headers:{"Content-Type":"application/json"},
                  body:JSON.stringify({sku:it.sku, row:it.row})});
      const j=await res.json();
      if(j.ok) ok++; else fail++;
    }catch(e){ fail++; }
  }
  toast("Deleted "+ok+(fail?(" / "+fail+" failed"):""));
  clearSelection(); loadRows();
}
async function clearMainImage(sku){
  if(!sku) return;
  if(!confirm("Remove the main image from this listing?\n\nThe listing can then be created WITHOUT an image (add one later in Seller Central). This also clears any additional image URLs that are local files.")) return;
  try{
    // remove main + any local (non-http) additional image locators
    const r=ROWS.find(x=>String(x.sku)===String(sku));
    let a={}; try{a=JSON.parse((r&&r.attrs)||"{}");}catch(e){a={};}
    const toClear=["main_product_image_locator"];
    Object.keys(a).forEach(k=>{
      if(/^other_product_image_locator_\d+$/.test(k)){
        const v=String(a[k]||"");
        if(!/^https?:\/\//i.test(v)) toClear.push(k);   // only drop local ones
      }
    });
    for(const k of toClear){
      await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, target:"attr", key:k, value:""})});
    }
    toast("Main image removed — listing can be created without it");
    // refresh this row so the panel updates
    try{
      const j=await (await fetch("/row?sku="+encodeURIComponent(sku))).json();
      if(j&&j.ok&&j.row){ const i=ROWS.findIndex(x=>String(x.sku)===String(sku)); if(i>=0) ROWS[i]={...ROWS[i],...j.row}; }
    }catch(e){}
    if(DRAWER_SKU===sku) openDrawer(sku); else render();
  }catch(e){ toast("Could not remove image: "+e); }
}
async function clearEmpty(btn){
  if(!confirm("Remove all empty rows from the sheet?")) return;
  btn.disabled=true;
  try{
    const res=await fetch("/clear_empty",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    const j=await res.json();
    if(j.ok){ toast("Removed "+(j.deleted||0)+" empty row(s)"); loadRows(); }
    else{ toast("Failed: "+(j.error||"")); btn.disabled=false; }
  }catch(e){ toast("Failed"); btn.disabled=false; }
}

let LIST_SOURCE = "drafts";   // 'drafts' | 'live' | 'all'
let LIVE_ITEMS = [];          // fetched live Amazon catalog for current account+mkt
let LIVE_STORE = {};          // cache: "accountid::MKT" -> {items, ts}
let LIVE_SYNC_TIMER = null;   // auto-sync interval handle

function _liveKey(){ return (CUR_ACCOUNT?CUR_ACCOUNT.id:"")+"::"+(WS_MARKET||""); }

function setListSource(src){
  if((src==="live"||src==="all") && CUR_ACCOUNT && !CUR_ACCOUNT.has_creds){
    toast("Live listings need a connected account. Add SP-API credentials to this account first.");
    // keep on drafts
    document.querySelectorAll('#srcswitch .mktbtn').forEach(b=>b.classList.toggle('on', b.dataset.src==='drafts'));
    LIST_SOURCE='drafts'; render();
    return;
  }
  LIST_SOURCE=src;
  document.querySelectorAll('#srcswitch .mktbtn').forEach(b=>b.classList.toggle('on', b.dataset.src===src));
  if((src==="live"||src==="all") && CUR_ACCOUNT){
    if(!WS_MARKET){ toast("Select a marketplace (US, UK, etc.) first, then it will load."); render(); return; }
    loadLiveCatalog(false);   // uses cache if present; fetches only if not cached
  }
  else render();
}
async function loadLiveCatalog(force){
  if(!CUR_ACCOUNT){ toast("Live catalog is per Amazon account — open an account workspace"); return; }
  if(!WS_MARKET){ toast("Pick a marketplace first"); return; }
  // Never refresh the live catalog while a per-listing Preview/Submit is streaming
  // into the drawer panel -- rewriting grid.innerHTML below would destroy that
  // panel (and its live log) mid-run. Defer; the next manual Sync/refresh picks it up.
  if(window.RUN_STREAMING){ return; }
  // "All marketplaces": fetch each marketplace's catalog and merge
  if(WS_MARKET==="__all__"){ return loadAllMarketplaces(force); }
  const key=_liveKey();
  const reqAccount=CUR_ACCOUNT.id, reqMkt=WS_MARKET;   // remember what THIS request is for
  // use in-browser cache unless forced -> returning to the page is instant
  if(!force && LIVE_STORE[key]){
    LIVE_ITEMS=LIVE_STORE[key].items; render(); updateSyncLabel(); return;
  }
  const grid=document.getElementById("grid");
  if(grid) grid.innerHTML='<div class="empty"><span class="genspin"></span> Fetching live listings from Amazon…<div class="cc" style="margin-top:8px">The first fetch generates a report on Amazon\u2019s side and can take 1\u20134 minutes for larger accounts. After that it\u2019s cached for 30 minutes. Please leave this open.</div></div>';
  try{
    const j=await (await fetch("/live/catalog",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:reqAccount,marketplace:reqMkt,force:!!force})})).json();
    // GUARD: if the user switched account/marketplace while this was loading,
    // store the result in its own cache slot but do NOT render it into the
    // current (different) view. This prevents one account's listings leaking
    // into another.
    const stillHere = (CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET===reqMkt);
    if(!j.ok){
      if(stillHere && grid) grid.innerHTML='<div class="empty">Could not load live catalog: '+esc(j.error||"")+'</div>';
      return;
    }
    LIVE_STORE[reqAccount+"::"+reqMkt]={items:(j.items||[]), ts:Date.now()};
    if(stillHere){
      LIVE_ITEMS=j.items||[];
      // If a Preview/Submit started streaming while this fetch was in flight,
      // cache the result but don't render now -- rendering would wipe the panel.
      if(window.RUN_STREAMING){ updateSyncLabel(); startAutoSync(); return; }
      render(); updateSyncLabel(); startAutoSync();
    }
  }catch(e){ if(grid && CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET===reqMkt) grid.innerHTML='<div class="empty">Error: '+esc(String(e))+'</div>'; }
}
function updateSyncLabel(){
  const el=document.getElementById("synclabel"); if(!el) return;
  const key=_liveKey(); const c=LIVE_STORE[key];
  if(c){ const mins=Math.round((Date.now()-c.ts)/60000);
    el.textContent = mins<1?"synced just now":("synced "+mins+"m ago"); }
  else el.textContent="";
}
function startAutoSync(){
  // SP-API is free (no AI credits), so a periodic background sync is fine.
  if(LIVE_SYNC_TIMER) return;
  LIVE_SYNC_TIMER=setInterval(()=>{
    if(window.RUN_STREAMING) return;   // don't wipe a streaming drawer panel
    if((LIST_SOURCE==="live"||LIST_SOURCE==="all") && CUR_ACCOUNT && WS_MARKET){
      loadLiveCatalog(true);   // refresh quietly every 30 min
    }
  }, 30*60*1000);
}
async function syncLive(){
  toast("Syncing live listings from Amazon…");
  await loadLiveCatalog(true);
}
async function runSpDiagnose(){
  // Run the one-shot SP-API health check for THIS workspace's account +
  // marketplace, and show the raw per-layer report in a modal. Every layer
  // (DNS, TCP, TLS, LWA auth, each SP-API operation) prints PASS/FAIL and
  // exactly what to fix if it fails -- so we don't have to guess anymore.
  const mkt = WS_MARKET && WS_MARKET!=="__all__" ? WS_MARKET : "UK";
  const acct = (CUR_ACCOUNT && CUR_ACCOUNT.id) ? CUR_ACCOUNT.id : "";
  const dlg = document.createElement("div");
  dlg.className = "modalwrap open";
  dlg.style.zIndex = "130";
  dlg.innerHTML = `<div class="modal" style="max-width:820px;position:relative">
    <button class="x" onclick="this.closest('.modalwrap').remove()">×</button>
    <h3><i class="ti ti-stethoscope"></i> SP-API diagnostic — ${esc(mkt)}${acct?(' · '+esc(acct)):''}</h3>
    <div class="cc" style="margin:2px 0 10px">Testing DNS → TCP → TLS → LWA auth → every SP-API operation. This takes ~15–45 seconds. The output tells you exactly which layer is broken and how to fix it.</div>
    <pre id="spdiagout" style="background:#0d1220;border:1px solid var(--line);border-radius:8px;padding:12px;font-size:12px;max-height:65vh;overflow:auto;white-space:pre-wrap;color:#cfe0ff"><span class="genspin"></span> Running…</pre>
  </div>`;
  document.body.appendChild(dlg);
  try{
    const j = await (await fetch("/sp_diagnose",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({marketplace:mkt, account_id:acct})})).json();
    const box=document.getElementById("spdiagout");
    if(!box) return;
    if(!j.ok){ box.textContent = "Error: "+(j.error||"unknown"); return; }
    // colour-tint PASS/FAIL/WARN lines for scannability
    const lines=(j.output||"").split("\n").map(l=>{
      if(/\bPASS\b/.test(l))  return '<span style="color:#7fd99a">'+esc(l)+'</span>';
      if(/\bFAIL\b/.test(l))  return '<span style="color:#e0696b">'+esc(l)+'</span>';
      if(/\bWARN\b/.test(l))  return '<span style="color:#e3b768">'+esc(l)+'</span>';
      if(/^\[.\d+\]/.test(l)) return '<span style="color:#9cc1ff;font-weight:600">'+esc(l)+'</span>';
      return esc(l);
    }).join("\n");
    box.innerHTML = lines + '\n\n<span style="color:'+(j.exit_code===0?'#7fd99a':'#e3b768')+'">Exit code: '+j.exit_code+'</span>';
  }catch(e){
    const box=document.getElementById("spdiagout");
    if(box) box.textContent = "Diagnostic failed to start: "+e;
  }
}
async function loadAllMarketplaces(force){
  if(window.RUN_STREAMING){ return; }   // don't wipe a streaming drawer panel mid-run
  const mkts=(CUR_ACCOUNT.marketplaces||[]);
  if(!mkts.length){ toast("No marketplaces detected for this account."); return; }
  const grid=document.getElementById("grid");
  // serve from cache if every marketplace is already cached and not forcing
  const allCached = mkts.every(mm => LIVE_STORE[CUR_ACCOUNT.id+"::"+mm]);
  if(!force && allCached){
    LIVE_ITEMS = mkts.flatMap(mm => (LIVE_STORE[CUR_ACCOUNT.id+"::"+mm].items||[]).map(it=>({...it,_mkt:mm})));
    render(); updateSyncLabel(); return;
  }
  const reqAccount=CUR_ACCOUNT.id;
  let merged=[]; let done=0;
  for(const mm of mkts){
    if(!(CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET==="__all__")) return; // user moved on
    if(grid) grid.innerHTML='<div class="empty"><span class="genspin"></span> Fetching all marketplaces… '+(done)+'/'+mkts.length+' ('+esc(mm)+')<div class="cc" style="margin-top:8px">Each marketplace is a separate Amazon report; this can take a few minutes the first time.</div></div>';
    try{
      const j=await (await fetch("/live/catalog",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:reqAccount,marketplace:mm,force:!!force})})).json();
      if(j.ok){
        LIVE_STORE[reqAccount+"::"+mm]={items:(j.items||[]), ts:Date.now()};
        merged=merged.concat((j.items||[]).map(it=>({...it,_mkt:mm})));
      }
    }catch(e){}
    done++;
  }
  if(CUR_ACCOUNT && CUR_ACCOUNT.id===reqAccount && WS_MARKET==="__all__"){
    LIVE_ITEMS=merged; render(); updateSyncLabel(); startAutoSync();
  }
}
function liveTile(it){
  // real status from the report (Active/Inactive/Incomplete), not a hardcoded LIVE
  var st=(it.status||"Active").trim();
  var stl=st.toLowerCase();
  // check inactive/suppressed/incomplete BEFORE active ("inactive" contains "active")
  var col = (stl.indexOf("inactive")>=0||stl.indexOf("suppress")>=0)?"#ef9a9a"
          : stl.indexOf("incomplete")>=0?"#e3b768"
          : stl.indexOf("active")>=0?"#74e0a3"
          : "#9aa3b2";
  var price = it.price ? (CUR_SYMBOL+esc(String(it.price).replace(/^[A-Z]{3}\s?/,''))) : '';
  // image slot — filled from the real getListingsItem image (fetched in batch after render)
  var sidv = sid(it.sku||it.asin||'');
  var imgHtml = it.img
    ? `<img src="${esc(it.img)}" loading="lazy">`
    : (it._noImg
        ? `<div class="noimgmsg"><i class="ti ti-photo-off"></i><span>No image uploaded</span></div>`
        : `<i class="ti ti-cloud-check" id="liveimg_${sidv}"></i>`);
  // qty: show value, or FBA/— when the report omits it
  var qtyHtml = (it.qty!==undefined && it.qty!=='' && it.qty!==null) ? ('qty '+esc(it.qty)) : '<span class="cc">qty —</span>';
  // profit margin chip
  var profHtml = '';
  if(it.profit){
    var mcol = it.profit.margin>=25?'#74e0a3':(it.profit.margin>=10?'#e3b768':'#ef9a9a');
    profHtml = `<span class="profchip" style="color:${mcol};border-color:${mcol}55;background:${mcol}1a" title="Price ${CUR_SYMBOL}${it.profit.price} − COGS ${CUR_SYMBOL}${it.profit.cogs} − ~15% referral ${CUR_SYMBOL}${it.profit.referral} = ${CUR_SYMBOL}${it.profit.net}">${it.profit.margin}% · ${CUR_SYMBOL}${it.profit.net}</span>`;
  } else {
    profHtml = `<span class="profchip cc" style="cursor:pointer" title="Set cost to see margin" onclick="event.stopPropagation();setCogs('${esc(it.sku||'')}','${esc(String(it.price||''))}')">+ COGS</span>`;
  }
  // fulfillment (FBA/FBM) + handling time + delivery estimate
  var fch = it.fulfillment||"";
  var fmode = /FBA|AMAZON/i.test(fch) ? "FBA" : (fch ? "FBM" : "");
  var fcol = fmode==="FBA" ? "#9cc1ff" : "#c9b6e8";
  var shipHtml = "";
  if(fmode){
    var fmt = (d)=>d.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'});
    var hd, transit;
    if(it.handling!==undefined && it.handling!==null && it.handling!=="" && !isNaN(parseInt(it.handling))){
      hd = parseInt(it.handling);
      transit = fmode==="FBA" ? 2 : 5;
    } else if(fmode==="FBA"){
      hd = 0; transit = 2;   // FBA: typically same/next-day handling + ~2d transit
    } else {
      hd = null;             // FBM with unknown handling
    }
    if(hd!==null){
      var shipBy = new Date(Date.now()+hd*864e5);
      var delBy  = new Date(Date.now()+(hd+transit)*864e5);
      shipHtml = `<div class="cc shipline" style="margin-top:4px"><span class="fmode" style="color:${fcol};border-color:${fcol}55;background:${fcol}1a">${fmode}</span> `+
                 `<span title="When it leaves the warehouse if ordered today">📦 ships by ${fmt(shipBy)}</span> · `+
                 `<span title="Estimated arrival for the customer">🚚 delivery ~${fmt(delBy)}</span>`+
                 `${it.ship_group?(' · <span class="cc" title="Shipping template">'+esc(it.ship_group)+'</span>'):''}</div>`;
    } else {
      shipHtml = `<div class="cc shipline" style="margin-top:4px"><span class="fmode" style="color:${fcol};border-color:${fcol}55;background:${fcol}1a">${fmode}</span> <span class="cc">handling time not set</span>${it.ship_group?(' · '+esc(it.ship_group)):''}</div>`;
    }
  } else {
    shipHtml = `<div class="cc shipline" style="margin-top:4px"><span class="cc">fulfillment loading…</span></div>`;
  }
  return `<div class="tile live" title="On Amazon — status: ${esc(st)}">
    <input type="checkbox" class="tilesel" ${SELECTED.has(String(it.sku))?'checked':''} onclick="event.stopPropagation()" onchange="toggleSelect('${esc(it.sku||'')}',this.checked)" title="Select for batch image generation">
    <div class="tileimg ${it.asin?'':'noimg'}">${imgHtml}</div>
    <div class="tilebody">
      <div class="tiletitle">${esc(it.title)||'<span class="cc">(no title in report)</span>'}</div>
      <div class="tilemeta"><span class="tileprice">${price}</span><span class="tilesku">${esc(it.sku||'')}</span></div>
      <div class="cc" style="margin-top:4px"><span class="livestatus" style="background:${col}1f;color:${col};border:1px solid ${col}55">${esc(st)}</span> ${esc(it.asin||'')} · ${qtyHtml}</div>
      ${shipHtml}
      <div style="margin-top:5px">${profHtml}</div>
    </div>
    <div class="tileacts">
      <button class="ib" title="Optimize this live listing" onclick="optimizeLive('${esc(it.asin||'')}','${esc(it.sku||'')}')"><i class="ti ti-wand"></i> Optimize</button>
      <button class="ib" title="Generate images for this product" onclick="event.stopPropagation();openStudioSingle('${esc(it.sku||'')}')"><i class="ti ti-photo"></i> Images</button>
      <a class="ib" title="View on Amazon" href="https://www.amazon.${WS_MARKET==='UK'?'co.uk':(WS_MARKET==='US'?'com':'com')}/dp/${esc(it.asin||'')}" target="_blank" rel="noopener"><i class="ti ti-external-link"></i></a>
    </div>
  </div>`;
}
async function uploadCogsCsv(input){
  const file=input.files&&input.files[0]; if(!file) return;
  const text=await file.text();
  const lines=text.split(/\r?\n/).filter(l=>l.trim());
  if(!lines.length){ toast("Empty CSV."); return; }
  // detect columns from header
  const hdr=lines[0].split(",").map(h=>h.trim().toLowerCase());
  const skuI=hdr.findIndex(h=>h==="sku"||h==="seller-sku"||h==="seller_sku");
  const asinI=hdr.findIndex(h=>h==="asin"||h==="asin1");
  const costI=hdr.findIndex(h=>h==="cost"||h==="cogs"||h==="source price"||h==="source_price"||h==="price");
  if(costI<0||(skuI<0&&asinI<0)){ toast("CSV needs a cost column and a sku or asin column."); input.value=""; return; }
  // build sku->cost; for ASIN-only rows, map against loaded live items
  const asinToSku={}; (LIVE_ITEMS||[]).forEach(it=>{ if(it.asin) asinToSku[it.asin]=it.sku; });
  const rows=[];
  for(let i=1;i<lines.length;i++){
    const c=lines[i].split(",");
    const cost=(c[costI]||"").trim(); if(!cost) continue;
    let sku=skuI>=0?(c[skuI]||"").trim():"";
    if(!sku && asinI>=0){ const asin=(c[asinI]||"").trim(); sku=asinToSku[asin]||""; }
    if(sku) rows.push({sku:sku, cost:cost});
  }
  if(!rows.length){ toast("No matchable rows (check sku/asin values match your listings)."); input.value=""; return; }
  try{
    const j=await (await fetch("/cogs/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id,rows:rows})})).json();
    if(!j.ok){ toast("Upload failed: "+(j.error||"")); input.value=""; return; }
    toast("COGS set for "+j.count+" SKUs. Re-syncing to show margins…");
    input.value="";
    await loadLiveCatalog(true);   // refresh so margins recompute
  }catch(e){ toast("Error: "+e); input.value=""; }
}
let _imgFetchBusy=false;
async function fetchLiveImages(){
  if(_imgFetchBusy) return;
  const need=(LIVE_ITEMS||[]).filter(it=>!it.img && it.sku).map(it=>it.sku);
  if(!need.length) return;
  _imgFetchBusy=true;
  const reqAccount=CUR_ACCOUNT?CUR_ACCOUNT.id:"", reqMkt=WS_MARKET;
  try{
    // fetch in chunks so images appear progressively
    for(let i=0;i<need.length;i+=20){
      if(!CUR_ACCOUNT||CUR_ACCOUNT.id!==reqAccount||WS_MARKET!==reqMkt) break; // user moved on
      const chunk=need.slice(i,i+20);
      const j=await (await fetch("/live/images",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:reqAccount,marketplace:reqMkt,skus:chunk})})).json();
      if(j&&j.ok){
        let changed=false;
        Object.entries(j.images||{}).forEach(([sku,url])=>{
          if(!url) return;
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku); if(it){ it.img=url; }
          const slot=document.getElementById("liveimg_"+sid(sku));
          if(slot){ const box=slot.parentNode; box.classList.remove("noimg"); box.innerHTML='<img src="'+url+'" loading="lazy">'; }
        });
        // apply REAL status (from getListingsItem) which is more accurate than the report
        Object.entries(j.statuses||{}).forEach(([sku,st])=>{
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku);
          if(it && st && it.status!==st){ it.status=st; it._realStatus=true; changed=true; }
        });
        // apply fulfillment (FBA/FBM) + handling time + live title
        Object.entries(j.meta||{}).forEach(([sku,mm])=>{
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku);
          if(it && mm){
            if(mm.fulfillment && it.fulfillment!==mm.fulfillment){ it.fulfillment=mm.fulfillment; changed=true; }
            if(mm.handling!==undefined && mm.handling!==null && it.handling!==mm.handling){ it.handling=mm.handling; changed=true; }
            // live title from getListingsItem reflects Amazon edits immediately;
            // prefer it over the (possibly stale) report title
            if(mm.title && mm.title.trim() && it.title!==mm.title){ it.title=mm.title; changed=true; }
          }
        });
        // mark items we checked that have NO image, so we can show "no image" text
        chunk.forEach(sku=>{
          const it=(LIVE_ITEMS||[]).find(x=>x.sku===sku);
          if(it && !it.img){ it._noImg=true; }
        });
        const key=_liveKey(); if(LIVE_STORE[key]) LIVE_STORE[key].items=LIVE_ITEMS;
        if(changed) render();   // refresh so corrected statuses/colors show
      }
    }
  }catch(e){ /* silent — images are best-effort */ }
  _imgFetchBusy=false;
}
async function setCogs(sku, price){
  const cur=prompt("Enter your cost (COGS) for SKU "+sku+"\n\nThis is your total cost including shipping. Margin = (price − COGS − ~15% Amazon referral) / price.","");
  if(cur===null) return;
  try{
    const j=await (await fetch("/cogs/set",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id,sku:sku,cost:cur,price:price})})).json();
    if(!j.ok){ toast("Could not set COGS: "+(j.error||"")); return; }
    // update the cached item and re-render
    const key=_liveKey();
    (LIVE_ITEMS||[]).forEach(it=>{ if(it.sku===sku){ it.profit=j.profit; it.cogs=parseFloat(cur); } });
    if(LIVE_STORE[key]) LIVE_STORE[key].items=LIVE_ITEMS;
    render();
  }catch(e){ toast("Error: "+e); }
}
let OPT_CURRENT = null;   // {sku, asin, product_type, marketplace, marketplace_id, fields}
async function optimizeLive(asin, sku){
  if(!sku){ toast("This listing has no SKU in the report — can't optimize it directly."); return; }
  const mod=document.getElementById("optmodal"); mod.classList.add("open");
  document.getElementById("optbody").innerHTML='<div class="gendiag"><span class="genspin"></span> Fetching current live data from Amazon…</div>';
  try{
    const j=await (await fetch("/optimize/fetch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"",sku:sku,marketplace:WS_MARKET})})).json();
    if(!j.ok){ document.getElementById("optbody").innerHTML='<div class="gendiag bad">✗ '+esc(j.error||"failed")+'</div>'; return; }
    OPT_CURRENT=j;
    OPT_EDIT_STATE=null;   // fresh listing -> clear any prior edits
    OPT_BRAND_HINT = (CUR_ACCOUNT && CUR_ACCOUNT.brands && CUR_ACCOUNT.brands.length) ? CUR_ACCOUNT.brands[0] : (CUR_ACCOUNT?CUR_ACCOUNT.label:"");
    renderOptEditor(j);
  }catch(e){ document.getElementById("optbody").innerHTML='<div class="gendiag bad">✗ '+esc(String(e))+'</div>'; }
}
function _optAttrToText(v){
  // turn an SP-API attribute value (list of dicts) into an editable string
  if(Array.isArray(v)){
    return v.map(x=>{
      if(x && typeof x==='object'){
        return x.value!==undefined?x.value:(x.media_location!==undefined?x.media_location:JSON.stringify(x));
      }
      return String(x);
    }).join(" | ");
  }
  return v==null?"":String(v);
}
function optIssuesPanel(j){
  const issues=j.issues||[];
  const errs=issues.filter(i=>(i.severity||"").toUpperCase()==="ERROR");
  const warns=issues.filter(i=>(i.severity||"").toUpperCase()!=="ERROR");
  let statusLine = j.listing_status ? `<div class="cc" style="margin-bottom:6px">Amazon status: <b>${esc(j.listing_status)}</b></div>` : "";
  if(!issues.length){
    return statusLine+`<div class="issuesbox ok"><b>✓ No attribute issues reported by Amazon.</b> If you still see a red dot, it's usually a <i>recommended</i> (not required) field, a pricing/Buy-Box issue, or a category review — not a missing attribute. You can still run a full diagnosis below.
      <div style="margin-top:8px"><button class="suggestbtn" onclick="optDiagnose()"><i class="ti ti-stethoscope"></i> Diagnose with Amazon &amp; suggest fixes</button> <span id="opt_diagstatus" class="cc"></span></div></div>`;
  }
  const renderList=(arr,cls,label)=> arr.length?`
    <div class="issgrp">
      <div class="issgrp-h ${cls}">${label} (${arr.length})</div>
      ${arr.map(i=>`<div class="issrow"><div class="issmsg">${esc(i.message||i.code||"issue")}</div>
        ${(i.attributes&&i.attributes.length)?`<div class="issattr">fields: ${i.attributes.map(a=>'<code>'+esc(a)+'</code>').join(", ")}</div>`:""}</div>`).join("")}
    </div>`:"";
  return statusLine+`<div class="issuesbox warn">
    <b>⚠ Amazon is reporting issues on this listing</b> — the text below is <b>Amazon's own wording, pulled live from the SP-API</b> (not our guess). It's what causes the red status.
    ${typeof howWorks==="function"?howWorks('opt_fetch'):""}
    ${renderList(errs,"err","Errors (must fix)")}
    ${renderList(warns,"warn","Warnings / recommended")}
    <div style="margin-top:8px"><button class="suggestbtn" onclick="optDiagnose()"><i class="ti ti-stethoscope"></i> Suggest fixes with AI</button> <span id="opt_diagstatus" class="cc"></span></div>
    ${typeof howWorks==="function"?howWorks('opt_diagnose'):""}
    <div id="opt_diagresults"></div>
  </div>`;
}
async function optDiagnose(){
  const st=document.getElementById("opt_diagstatus");
  if(st) st.innerHTML='<span class="genspin"></span> Asking Amazon what\u2019s wrong and drafting fixes…';
  try{
    const j=await (await fetch("/optimize/diagnose_fill",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"", sku:OPT_CURRENT.sku, marketplace:WS_MARKET})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; return; }
    const box=document.getElementById("opt_diagresults");
    if(!j.flagged || !j.flagged.length){
      if(st) st.innerHTML='';
      if(box) box.innerHTML='<div class="cc" style="margin-top:8px">'+esc(j.note||"No attribute-level issues to fix.")+'</div>';
      return;
    }
    const sugg=j.suggestions||{};
    let rows=j.flagged.map(f=>{
      const s=sugg[f.attribute]||{};
      const val=(s.value!==undefined&&s.value!==null)?s.value:"";
      const note=s.note||"";
      const needs=(s.value===null||s.value===undefined)&&note;
      return `<tr>
        <td class="k"><code>${esc(f.attribute)}</code><div class="cc" style="font-size:10px">${esc(f.message||"")}</div></td>
        <td class="v">
          ${needs?`<div class="cc" style="color:#e3b768">⚠ ${esc(note)} (you'll need to provide this)</div>`:""}
          <input class="ed optfix" data-attr="${esc(f.attribute)}" value="${esc(String(val))}" placeholder="${esc(note||'value')}">
          <label class="cc" style="display:flex;align-items:center;gap:5px;margin-top:3px"><input type="checkbox" class="optfixchk" data-attr="${esc(f.attribute)}" ${val?'checked':''}> apply this fix</label>
        </td></tr>`;
    }).join("");
    if(box) box.innerHTML=`<div style="margin-top:10px"><div class="optsec">AI-suggested values — these are <b>estimates the AI inferred</b>, not from Amazon. Review &amp; correct each before applying.</div>
      <table class="kv">${rows}</table>
      <div class="cc" style="margin:6px 0">These get added to your approved changes. Simple fields push fine; <b>dimensions with units are safest filled in Seller Central</b> (the form structures them correctly). Tick only what you want.</div>
      <button class="primary" onclick="optApplyFixes()"><i class="ti ti-check"></i> Add ticked fixes to changes</button></div>${typeof howWorks==="function"?howWorks('opt_push'):""}`;
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ Drafted '+Object.keys(sugg).length+' suggestion(s)</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Error: '+esc(String(e))+'</span>'; }
}
function optApplyFixes(){
  _captureOptEditor();
  const st=OPT_EDIT_STATE||(OPT_EDIT_STATE={});
  st.attrs=st.attrs||{};
  let n=0;
  document.querySelectorAll(".optfixchk:checked").forEach(chk=>{
    const attr=chk.dataset.attr;
    const inp=document.querySelector('.optfix[data-attr="'+CSS.escape(attr)+'"]');
    if(inp && inp.value.trim()){ st.attrs[attr]=inp.value.trim(); n++; }
  });
  toast(n+" fix(es) added to your changes. Review changes to approve & push.");
}
function renderOptEditor(j){
  OPT_CURRENT=j;
  const f=j.fields||{};
  const attrs=j.raw_attributes||{};
  const s=OPT_EDIT_STATE||{};   // saved edits (incl. AI copy) take precedence over original
  const vTitle = (s.title!==undefined?s.title:(f.title||""));
  const vBullets = (s.bullets!==undefined?s.bullets:(f.bullets||[]));
  const vDesc = (s.description!==undefined?s.description:(f.description||""));
  const vPrice = (s.price!==undefined?s.price:(f.price||""));
  const vImg = (s.main_image!==undefined?s.main_image:(f.main_image||""));
  const bulletsText=(vBullets||[]).join("\n");
  const img=vImg;
  // core fields shown prominently
  let core=`
    <table class="kv">
      <tr><td class="k">Title</td><td class="v"><textarea class="ed" id="opt_title" rows="2">${esc(vTitle)}</textarea></td></tr>
      <tr><td class="k">Bullets <span class="cc">(one per line)</span></td><td class="v"><textarea class="ed" id="opt_bullets" rows="5">${esc(bulletsText)}</textarea></td></tr>
      <tr><td class="k">Description</td><td class="v"><textarea class="ed" id="opt_description" rows="4">${esc(vDesc)}</textarea></td></tr>
      <tr><td class="k">Price</td><td class="v"><input class="ed" id="opt_price" value="${esc(vPrice)}"></td></tr>
      <tr><td class="k">Main image</td><td class="v">
        ${img?`<img src="${esc(img)}" style="max-width:120px;border-radius:8px;border:1px solid var(--line);display:block;margin-bottom:6px">`:'<span class="cc">no image</span>'}
        <input class="ed" id="opt_main_image" value="${esc(img)}"></td></tr>
    </table>`;
  // ALL other attributes — full editable list, like Amazon's edit page
  const coreKeys=new Set(["item_name","bullet_point","product_description","purchasable_offer",
                          "main_product_image_locator"]);
  let allRows="";
  const savedAttrs=s.attrs||{};
  const keys=Object.keys(attrs).filter(k=>!coreKeys.has(k)).sort();
  for(const k of keys){
    const val=(savedAttrs[k]!==undefined?savedAttrs[k]:_optAttrToText(attrs[k]));
    const isImg=/image_locator/i.test(k);
    const long=val.length>60;
    allRows+=`<tr><td class="k">${esc(k)}</td><td class="v">`+
      (isImg&&val?`<img src="${esc(val.split(' | ')[0])}" style="max-width:70px;border-radius:6px;border:1px solid var(--line);display:block;margin-bottom:4px">`:"")+
      (long?`<textarea class="ed optattr" data-attr="${esc(k)}" rows="2">${esc(val)}</textarea>`
           :`<input class="ed optattr" data-attr="${esc(k)}" value="${esc(val)}">`)+
      `</td></tr>`;
  }
  document.getElementById("optbody").innerHTML=`
    <div class="cc" style="margin-bottom:10px">Editing a <b>LIVE</b> listing on <b>${esc(CUR_ACCOUNT?CUR_ACCOUNT.label:"")}</b> · ${esc(j.marketplace)} · ASIN ${esc(j.asin||"")} · SKU ${esc(j.sku)} · type <b>${esc(j.product_type||"")}</b>. <b>Nothing is sent to Amazon</b> until you review and approve each field.</div>
    ${optIssuesPanel(j)}
    <div class="srcbox">
      <div class="optsec" style="margin-bottom:6px"><i class="ti ti-robot"></i> Custom AI rewrite</div>
      <div class="cc" style="margin-bottom:8px">Tell the AI exactly what you want (e.g. <i>"don't put any brand in the title, focus on iPhone 17 Pro fit, make it sound premium"</i>). Optionally paste the real product's eBay/Amazon link so it knows the actual product. Compliance &amp; IP rules stay applied.</div>
      <textarea class="ed" id="opt_src_instruction" rows="2" placeholder="What do you want? e.g. rewrite without my brand name, emphasise durability, keep it under 150 chars…" style="margin-bottom:6px"></textarea>
      <input class="ed" id="opt_src_ebay" placeholder="eBay product URL (optional)" style="margin-bottom:6px">
      <input class="ed" id="opt_src_amazon" placeholder="Amazon product URL (optional)" style="margin-bottom:8px">
      <button class="suggestbtn" onclick="optRewriteFromSource()"><i class="ti ti-wand"></i> Rewrite with these instructions</button>
      <span id="opt_srcstatus" class="cc" style="margin-left:8px"></span>
      ${typeof howWorks==="function"?howWorks('opt_rewrite'):""}
    </div>
    <div class="optsec">Core listing fields</div>
    ${core}
    <details class="optall"><summary>All other attributes (${keys.length}) — required &amp; optional, exactly as Amazon has them</summary>
      <table class="kv">${allRows||'<tr><td class="cc">No additional attributes returned.</td></tr>'}</table>
    </details>
    <div style="margin-top:14px;display:flex;gap:8px">
      <button class="suggestbtn" onclick="optAISuggest()"><i class="ti ti-wand"></i> AI optimize copy</button>
      <button class="primary" onclick="optReview()"><i class="ti ti-eye"></i> Review changes before pushing</button>
      <button onclick="closeOpt()">Cancel</button>
    </div>
    <div id="opt_aistatus" class="cc" style="margin-top:6px"></div>`;
}
let OPT_BRAND_HINT = "";
async function optRewriteFromSource(){
  const eb=(document.getElementById("opt_src_ebay")||{}).value||"";
  const az=(document.getElementById("opt_src_amazon")||{}).value||"";
  const ins=(document.getElementById("opt_src_instruction")||{}).value||"";
  const st=document.getElementById("opt_srcstatus");
  if(!eb.trim() && !az.trim() && !ins.trim()){ if(st) st.textContent="Type an instruction and/or paste a product link first."; return; }
  _captureOptEditor();
  if(st) st.innerHTML='<span class="genspin"></span> AI is rewriting per your instructions (can take 20–40s)…';
  try{
    const j=await (await fetch("/optimize/from_source",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT.id, ebay_url:eb.trim(), amazon_url:az.trim(), instruction:ins.trim(),
        product_type:OPT_CURRENT.product_type,
        current:{title:(document.getElementById("opt_title")||{}).value,
                 bullets:(document.getElementById("opt_bullets")||{}).value,
                 description:(document.getElementById("opt_description")||{}).value}})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; return; }
    const s=j.suggestion||{};
    if(s.title) document.getElementById("opt_title").value=s.title;
    if(Array.isArray(s.bullets)&&s.bullets.length) document.getElementById("opt_bullets").value=s.bullets.join("\n");
    if(s.description) document.getElementById("opt_description").value=s.description;
    _captureOptEditor();
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ Rewritten per your instructions. Review &amp; edit, then Review changes to approve.</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Error: '+esc(String(e))+'</span>'; }
}
async function optAISuggest(){
  const st=document.getElementById("opt_aistatus");
  if(st) st.innerHTML='<span class="genspin"></span> AI optimizing title, bullets, description…';
  try{
    const j=await (await fetch("/ask",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({messages:[{role:"user",text:"Optimize this Amazon listing's title, bullets and description for conversions and SEO. Return ONLY JSON {\"title\":\"..\",\"bullets\":[\"..\"],\"description\":\"..\"} no preamble."}],
        context:{title:(document.getElementById("opt_title")||{}).value,bullets:(document.getElementById("opt_bullets")||{}).value,description:(document.getElementById("opt_description")||{}).value,product_type:OPT_CURRENT.product_type}})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">AI failed: '+esc(j.error||"")+'</span>'; return; }
    let txt=(j.reply||"").trim().replace(/^```json/i,'').replace(/```$/,'').trim();
    let s=JSON.parse(txt);
    if(s.title) document.getElementById("opt_title").value=s.title;
    if(Array.isArray(s.bullets)&&s.bullets.length) document.getElementById("opt_bullets").value=s.bullets.join("\n");
    if(s.description) document.getElementById("opt_description").value=s.description;
    _captureOptEditor();   // save AI copy into state so it survives Back-to-edit / Review
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ AI suggestions applied — they\u2019re saved. Click Review changes to approve.</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Could not parse AI: '+esc(String(e))+'</span>'; }
}
let OPT_EDIT_STATE = null;   // persists edited values across editor<->review
function _captureOptEditor(){
  // read the editor inputs WHILE they exist and save into OPT_EDIT_STATE
  const f=OPT_CURRENT.fields||{};
  const attrs=OPT_CURRENT.raw_attributes||{};
  const gv=(id)=>{ const el=document.getElementById(id); return el?(el.value||""):null; };
  const bv=gv("opt_bullets");
  const st={
    title:   gv("opt_title"),
    bullets: bv===null?null:bv.split("\n").map(s=>s.trim()).filter(Boolean),
    description: gv("opt_description"),
    price:   gv("opt_price"),
    main_image: gv("opt_main_image"),
    attrs:{}
  };
  document.querySelectorAll(".optattr").forEach(el=>{ st.attrs[el.dataset.attr]=(el.value||"").trim(); });
  // merge into existing state so values persist even if some inputs are absent
  OPT_EDIT_STATE = OPT_EDIT_STATE || {};
  if(st.title!==null) OPT_EDIT_STATE.title=st.title.trim();
  if(st.bullets!==null) OPT_EDIT_STATE.bullets=st.bullets;
  if(st.description!==null) OPT_EDIT_STATE.description=st.description.trim();
  if(st.price!==null) OPT_EDIT_STATE.price=st.price.trim();
  if(st.main_image!==null) OPT_EDIT_STATE.main_image=st.main_image.trim();
  OPT_EDIT_STATE.attrs = Object.assign(OPT_EDIT_STATE.attrs||{}, st.attrs);
  return OPT_EDIT_STATE;
}
function _optEdited(){
  const f=OPT_CURRENT.fields||{};
  const attrs=OPT_CURRENT.raw_attributes||{};
  // if the editor is on screen, refresh saved state from it first
  if(document.getElementById("opt_title")) _captureOptEditor();
  const s=OPT_EDIT_STATE||{};
  const ed={
    title:{old:f.title||"", new:(s.title!==undefined?s.title:(f.title||""))},
    bullets:{old:(f.bullets||[]), new:(s.bullets!==undefined?s.bullets:(f.bullets||[]))},
    description:{old:f.description||"", new:(s.description!==undefined?s.description:(f.description||""))},
    price:{old:String(f.price||""), new:(s.price!==undefined?s.price:String(f.price||""))},
    main_image:{old:f.main_image||"", new:(s.main_image!==undefined?s.main_image:(f.main_image||""))},
  };
  const savedAttrs=s.attrs||{};
  Object.keys(attrs).forEach(k=>{
    if(["item_name","bullet_point","product_description","purchasable_offer","main_product_image_locator"].includes(k)) return;
    const oldVal=_optAttrToText(attrs[k]);
    const newVal=(savedAttrs[k]!==undefined?savedAttrs[k]:oldVal);
    ed["attr:"+k]={old:oldVal, new:newVal, _isAttr:true};
  });
  return ed;
}
function optReview(){
  const ed=_optEdited();
  let rows="";
  const changed=[];
  for(const [field,val] of Object.entries(ed)){
    const oldS=Array.isArray(val.old)?val.old.join(" | "):String(val.old);
    const newS=Array.isArray(val.new)?val.new.join(" | "):String(val.new);
    const isChanged = oldS!==newS;
    if(isChanged) changed.push(field);
    rows+=`<div class="optdiff ${isChanged?'chg':'same'}">
      <label class="optcheck"><input type="checkbox" id="optapprove_${field}" ${isChanged?'':'disabled'} onchange="optCountApproved()"> <b>${esc(field)}</b> ${isChanged?'<span class="chgflag">changed</span>':'<span class="cc">unchanged</span>'}</label>
      <div class="optold"><span class="cc">Current (live):</span> ${esc(oldS)||'<span class="cc">(empty)</span>'}</div>
      <div class="optnew"><span class="cc">New:</span> ${esc(newS)||'<span class="cc">(empty)</span>'}</div>
    </div>`;
  }
  document.getElementById("optbody").innerHTML=`
    <div class="cc" style="margin-bottom:10px"><b>Review every change.</b> Only the fields you tick will be sent to Amazon. Unticked fields stay exactly as they are on the live listing.</div>
    ${rows}
    <div style="margin-top:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;position:sticky;bottom:0;background:var(--panel);padding:12px 0;border-top:1px solid var(--line)">
      <button id="optpushbtn" disabled onclick="optPush()" style="background:#3a1d1d;border:1px solid #5c2b2b;color:#e0a3a3;padding:9px 16px;border-radius:8px;cursor:pointer;font-weight:600">Push approved fields to LIVE Amazon</button>
      <span id="optapprovedcount" class="cc">0 fields approved</span>
      <button onclick="renderOptEditor(OPT_CURRENT)">← Back to edit</button>
      <button onclick="closeOpt()">Cancel</button>
    </div>`;
  optCountApproved();
}
function optCountApproved(){
  const ed=_optEdited();
  let n=0;
  for(const field of Object.keys(ed)){
    const cb=document.getElementById("optapprove_"+field);
    if(cb&&cb.checked) n++;
  }
  const lbl=document.getElementById("optapprovedcount"); if(lbl) lbl.textContent=n+" field"+(n===1?"":"s")+" approved";
  const btn=document.getElementById("optpushbtn"); if(btn) btn.disabled=(n===0);
  if(btn){ btn.style.opacity=(n===0)?".5":"1"; }
}
async function optPush(){
  const ed=_optEdited();
  const changes={};
  for(const [field,val] of Object.entries(ed)){
    const cb=document.getElementById("optapprove_"+field);
    if(cb&&cb.checked){ changes[field]=val.new; }
  }
  const fieldList=Object.keys(changes);
  if(!fieldList.length){ toast("Tick at least one changed field to push."); return; }
  if(!confirm("PUSH TO LIVE AMAZON\n\nAccount: "+(CUR_ACCOUNT?CUR_ACCOUNT.label:"")+"\nASIN: "+(OPT_CURRENT.asin||"")+"\nSKU: "+OPT_CURRENT.sku+"\nMarketplace: "+OPT_CURRENT.marketplace+"\n\nFields being changed: "+fieldList.join(", ")+"\n\nThis updates the LIVE listing customers see. Proceed?")) return;
  const btn=document.getElementById("optpushbtn"); if(btn){ btn.disabled=true; btn.textContent="Pushing…"; }
  try{
    const j=await (await fetch("/optimize/push",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id:CUR_ACCOUNT?CUR_ACCOUNT.id:"",sku:OPT_CURRENT.sku,marketplace:OPT_CURRENT.marketplace,
        product_type:OPT_CURRENT.product_type,changes:changes,confirmed:true})})).json();
    if(j.ok){
      document.getElementById("optbody").innerHTML='<div class="gendiag ok">✓ Submitted to Amazon ('+esc(j.status||"accepted")+'). Pushed: '+esc((j.pushed_fields||[]).join(", "))+'.<div class="cc" style="margin-top:6px">Amazon may take time to reflect changes. Use Sync to refresh.</div></div>';
    } else {
      let issues=(j.issues||[]).map(x=>(x.message||JSON.stringify(x))).join("; ");
      document.getElementById("optbody").innerHTML='<div class="gendiag bad">✗ Amazon rejected the change: '+esc(j.error||issues||j.status||"unknown")+'</div><button onclick="renderOptEditor(OPT_CURRENT)" style="margin-top:10px">← Back to edit</button>';
    }
  }catch(e){ if(btn){btn.disabled=false;btn.textContent="Push approved fields to LIVE Amazon";} toast("Push error: "+e); }
}
function closeOpt(){ document.getElementById("optmodal").classList.remove("open"); OPT_CURRENT=null; }

// ============ IMAGE STUDIO (main image generation: recipes + creative + batch) ============
let STUDIO = { skus: [], items: [], brand: "", recipes: [], results: {} };
function _itemForSku(sku){ return (LIVE_ITEMS||[]).find(x=>String(x.sku)===String(sku)) || (ROWS||[]).find(x=>String(x.sku)===String(sku)); }
function _refImgForItem(it){
  if(!it){ return (typeof STUDIO!=='undefined' && STUDIO.manualRef) || ""; }
  var direct = it.img || it.main_image || it.image || "";
  if(direct) return direct;
  // draft rows store images inside the attributes JSON (main_product_image_locator)
  try{
    var imgs=_rowImages(it);
    if(imgs && imgs.length) return imgs[0];
  }catch(e){}
  // brand/source image, then a manually-provided reference (upload/URL) as last resort
  return it.source_image || it.src_image || (typeof STUDIO!=='undefined' && STUDIO.manualRef) || "";
}
async function openStudioSingle(sku){
  const it=_itemForSku(sku);
  STUDIO={ skus:[String(sku)], items: it?[it]:[], brand: (CUR_ACCOUNT&&CUR_ACCOUNT.brands&&CUR_ACCOUNT.brands.length?CUR_ACCOUNT.brands[0]:(CUR_ACCOUNT?CUR_ACCOUNT.label:"")), recipes:[], results:{} };
  document.getElementById("imgstudio").classList.add("open");
  await loadRecipes();
  renderStudio();
  studioLoadModels();
  loadStudioInstructions();
}
async function openStudioBatch(){
  const skus=selectedSkus();
  if(!skus.length){ toast("Select some products first (tick the cards)."); return; }
  const items=skus.map(_itemForSku).filter(Boolean);
  STUDIO={ skus:skus.map(String), items:items, brand:(CUR_ACCOUNT&&CUR_ACCOUNT.brands&&CUR_ACCOUNT.brands.length?CUR_ACCOUNT.brands[0]:(CUR_ACCOUNT?CUR_ACCOUNT.label:"")), recipes:[], results:{} };
  document.getElementById("imgstudio").classList.add("open");
  await loadRecipes();
  renderStudio();
  studioLoadModels();
  loadStudioInstructions();
}
function closeStudio(){ document.getElementById("imgstudio").classList.remove("open"); }
async function loadRecipes(){
  try{
    const j=await (await fetch("/recipes/list",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({brand:STUDIO.brand})})).json();
    if(j.ok){ STUDIO.recipes=j.recipes||[]; STUDIO.all_recipes=j.all_recipes||[]; }
  }catch(e){}
}
// known strengths of popular image models (shown as guidance next to the picker)
const IMG_MODEL_NOTES=[
  {match:/seedream/i, note:"★ Best for product shots & packaging, native up to 4K, strong text — top pick for main images"},
  {match:/ideogram/i, note:"★ Best text rendering — ideal for secondary images & A+ with benefit text"},
  {match:/imagen.*ultra|imagen-4/i, note:"Most photorealistic — great for hero shots (pricier)"},
  {match:/flux.*2|flux\.2/i, note:"Strong photorealism & reference preservation (good for keeping your product)"},
  {match:/nano-banana-2|gemini-3.*image|nano banana 2/i, note:"Fast, native 2K, good all-round"},
  {match:/nano-banana|gemini-2.5-flash-image/i, note:"Fast & cheap, ~1024px (may need upscaling for Amazon)"},
  {match:/gpt-image|gpt-5-image/i, note:"Top-ranked quality, good text & editing"},
  {match:/recraft/i, note:"Design-first, good for clean e-commerce mockups & vectors"},
];
function _imgModelNote(id){
  for(const m of IMG_MODEL_NOTES){ if(m.match.test(id||"")) return m.note; }
  return "";
}
async function studioLoadModels(){
  let s=null;
  try{ s=await (await fetch('/ai/settings')).json(); }catch(e){}
  if(!s||!s.ok){ return; }
  // admin gate for the "how it works" panels
  if(s.admin){ window.LOGIC_VISIBLE = !!s.admin.show_logic && !s.admin.preview_as_user; }
  const tsel=document.getElementById("studio_text_model");
  const isel=document.getElementById("studio_image_model");
  if(tsel){
    tsel.innerHTML=(s.text_models||[]).map(m=>`<option value="${esc(m.id)}" ${m.id===s.select.prompt_enhance?'selected':''}>${esc(m.name||m.id)}</option>`).join("")||'<option value="">no text models</option>';
    window.AI_TEXT=tsel.value;
    tsel.onchange=()=>{ window.AI_TEXT=tsel.value; };
  }
  if(isel){
    isel.innerHTML=(s.image_models||[]).map(m=>`<option value="${esc(m.id)}" ${m.id===s.select.image_generate?'selected':''}>${esc(m.name||m.id)}</option>`).join("")||'<option value="">no image models</option>';
    window.AI_IMAGE=isel.value;
    isel.onchange=()=>{ window.AI_IMAGE=isel.value; studioModelHint(); };
  }
  // text hint: which models are good for the product-reading job
  const th=document.getElementById("studio_text_hint");
  if(th) th.innerHTML="Tip: a strong vision model (e.g. one that can read images well) reads your label text more accurately. This AI examines your product and writes the detailed prompt.";
  studioModelHint();
}
function studioModelHint(){
  const isel=document.getElementById("studio_image_model");
  const ih=document.getElementById("studio_image_hint");
  if(isel&&ih){ const note=_imgModelNote(isel.value); ih.innerHTML=note?('<span style="color:#7fd99a">'+esc(note)+'</span>'):'<span class="cc">Pick the image model. Models that support reference images keep your product faithful.</span>'; }
}
function renderStudio(){
  const body=document.getElementById("studiobody");
  const n=STUDIO.skus.length;
  const batch = n>1;
  const recipeOpts=(STUDIO.recipes||[]).map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join("");
  const otherRecipes=(STUDIO.all_recipes||[]).filter(r=>!(STUDIO.recipes||[]).some(x=>x.id===r.id));
  const otherOpts=otherRecipes.map(r=>`<option value="${esc(r.id)}">${esc(r.name)} — ${esc(r.brand)}</option>`).join("");
  body.innerHTML=`
    <div class="cc" style="margin-bottom:10px">${batch?('<b>Batch:</b> '+n+' products selected — the chosen treatment applies to each, using each product\u2019s own image.'):'Generating a main image for <b>'+esc(STUDIO.skus[0])+'</b>.'} Brand: <b>${esc(STUDIO.brand||'(none)')}</b></div>
    <div class="studiomodels">
      <div class="smodel">
        <label class="cc">Prompt AI (reads your product &amp; writes the prompt)</label>
        <select id="studio_text_model" class="ed"><option value="">Loading…</option></select>
        <div class="cc smodelhint" id="studio_text_hint"></div>
      </div>
      <div class="smodel">
        <label class="cc">Image AI (generates the image)</label>
        <select id="studio_image_model" class="ed" onchange="studioModelHint()"><option value="">Loading…</option></select>
        <div class="cc smodelhint" id="studio_image_hint"></div>
      </div>
      <div class="smodel">
        <label class="cc">Product fidelity (how closely to keep your exact product)</label>
        <select id="studio_fidelity" class="ed">
          <option value="high" selected>High — keep my product as exact as possible (recommended)</option>
          <option value="medium">Medium — balanced</option>
          <option value="creative">Creative — allow more artistic freedom</option>
        </select>
        <div class="cc smodelhint">Higher fidelity keeps the shape, colours and proportions closest to your real product. Note: how well this works depends heavily on the image model — reference-preserving models (Seedream, FLUX) keep the product far better than Gemini Flash.</div>
      </div>
      <div class="smodel" style="grid-column:1/-1">
        <label class="cc"><i class="ti ti-message-2-cog"></i> Your standing instructions (the AI remembers these for every image)</label>
        <textarea id="studio_custom_instructions" class="ed" rows="2" placeholder="e.g. Always use a pure white background. Keep our logo in the top-left. Never include people. Warm lighting."></textarea>
        <div style="display:flex;gap:8px;align-items:center;margin-top:5px;flex-wrap:wrap">
          <button class="ib" onclick="saveStudioInstructions()"><i class="ti ti-device-floppy"></i> Save instructions</button>
          <span class="cc" id="studio_ci_status" style="font-size:11px"></span>
        </div>
        <div class="cc smodelhint">These are added on top of the strategist's creative brief for every image you generate or edit — so your rules are always applied without retyping.</div>
      </div>
    </div>
    <div class="studiotabs">
      <button class="stab on" data-tab="recipe" onclick="studioTab('recipe')">Use a saved recipe (templated)</button>
      <button class="stab" data-tab="creative" onclick="studioTab('creative')">Creative (3 variations)</button>
      <button class="stab" data-tab="source" onclick="studioTab('source')">Main image (clean white bg)</button>
      <button class="stab" data-tab="secondary" onclick="studioTab('secondary')">Secondary images</button>
      <button class="stab" data-tab="aplus" onclick="studioTab('aplus')">A+ Content</button>
      <button class="stab" data-tab="recipes_manage" onclick="studioTab('recipes_manage')">Manage recipes</button>
    </div>
    <div id="studio_recipe" class="studiopane">
      ${recipeOpts||otherOpts ? `
        <label class="cc">Recipe</label>
        <select id="studio_recipe_sel" class="ed">${recipeOpts}${otherOpts?('<optgroup label="Other brands">'+otherOpts+'</optgroup>'):''}</select>
        <div class="cc" style="margin:8px 0">The recipe\u2019s saved instructions are applied to ${batch?'each selected product':'this product'}; the product itself stays identical.</div>
        <button class="primary" onclick="studioRun('recipe')"><i class="ti ti-sparkles"></i> ${batch?('Generate for all '+n+' products'):'Generate main image'}</button>
      ` : `<div class="cc">No recipes yet for <b>${esc(STUDIO.brand||'this brand')}</b>. Create one under <b>Manage recipes</b> — a recipe is a saved treatment (template image + the changes you want) that you can reuse on any product.</div>`}
      ${typeof howWorks==="function"?(howWorks('recipes')+howWorks('media')):""}
    </div>
    <div id="studio_creative" class="studiopane" style="display:none">
      <div class="ideabox">
        <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-bulb"></i> Option A — Let the AI strategist invent the ideas</div>
        <div class="cc" style="margin-bottom:8px">Instead of you supplying the idea, the AI thinks like a top Amazon conversion strategist <i>and</i> like your customer — what stops them scrolling, what makes them feel "this is the one" — then proposes concrete photo concepts for <b>this</b> product. You pick which to generate. (Main images stay pure white; creativity is in angle, lighting &amp; touches like droplets.)</div>
        <label class="cc" style="display:block;margin-bottom:3px">Instructions for the strategist (optional, not saved) — e.g. "don't show pets", "show the product in only some images, not all"</label>
        <textarea id="strat_instr_main" class="ed" rows="2" placeholder='e.g. no people; show one close-up of the texture; keep it minimal' style="margin-bottom:8px"></textarea>
        <button class="primary" onclick="studioStrategize('main')"><i class="ti ti-sparkles"></i> Suggest image ideas</button>
        <button class="primary" onclick="studioStrategize('main', true)" style="margin-left:6px" title="Ask the strategist for ideas AND generate them all automatically — no manual picking"><i class="ti ti-bolt"></i> Suggest &amp; auto-generate${batch?(' ('+n+' products)'):''}</button>
        <span id="studio_strat_status" class="cc" style="margin-left:8px"></span>
        ${howWorks('strategist')}
        <div id="studio_concepts" style="margin-top:10px"></div>
      </div>
      <div class="ordiv"><span>OR</span></div>
      <div class="buildbox">
        <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-adjustments"></i> Option B — Use the 3 ready-made variations</div>
        <div class="cc" style="margin-bottom:8px">Generates 3 fixed treatments — straight-on hero, flattering angle, and a creative "personality" shot — all on pure white, product kept identical.</div>
        <label class="cc">Optional inspiration (a link, image URL, or a few words)</label>
        <input id="studio_inspo" class="ed" placeholder="e.g. https://… or 'bright airy bathroom, marble surface'">
        <div style="margin-top:10px"><button class="primary" onclick="studioRun('creative')"><i class="ti ti-sparkles"></i> ${batch?('Generate 3 variations for each of '+n+' products'):'Generate 3 variations'}</button></div>
        ${howWorks('ready3')}
      </div>
    </div>
    <div id="studio_recipes_manage" class="studiopane" style="display:none">${recipesManageHTML()}</div>
    <div id="studio_secondary" class="studiopane" style="display:none">${secondaryPaneHTML(batch,n)}</div>
    <div id="studio_source" class="studiopane" style="display:none">${sourcePaneHTML(batch,n)}</div>
    <div id="studio_aplus" class="studiopane" style="display:none">${aplusPaneHTML(batch,n)}</div>
    <div id="studio_progress" style="margin-top:14px"></div>
    <div id="studio_results" class="studiogrid" style="margin-top:14px"></div>`;
}
function sourcePaneHTML(batch,n){
  // default: if this workspace has brand profiles/CSV products, assume 'brand' (keep logo);
  // otherwise assume 'competitor' (dropshipping/scrape -> remove logo)
  const looksBrand = !!(STUDIO.brand && STUDIO.brand.trim());
  return `
    <div class="cc" style="margin-bottom:8px">Turn the <b>source product photo</b> (from eBay/Amazon, or your brand's own upload) into a clean Amazon main image — <b>pure white background, product kept identical</b>. ${batch?('Applies to each of '+n+' selected products.'):''}</div>
    ${batch?'':refPickerHTML()}
    <div class="secrow">
      <label class="cc">Where is this image from?</label>
      <select id="src_source" class="ed" onchange="srcSourceChange()">
        <option value="competitor" ${looksBrand?'':'selected'}>Competitor / eBay / Amazon scrape — remove their logo</option>
        <option value="brand" ${looksBrand?'selected':''}>My brand's own product (CSV/upload) — keep my product &amp; logo</option>
      </select>
    </div>
    <div id="src_brandopts" style="margin-top:8px;${looksBrand?'':'display:none'}">
      <label class="seccheck"><input type="checkbox" id="src_preserve_logo" checked> Preserve product <b>and logo</b> (keep my branding exactly)</label>
    </div>
    <div id="src_competitornote" class="cc" style="margin-top:8px;font-size:11px;${looksBrand?'display:none':''}">
      Any brand logo found on the product will be cleanly removed (blended to match the surface — no replacement). If the photo has no logo, the product is kept as-is.
    </div>
    <label class="cc" style="margin-top:10px;display:block">Optional — any other edits you want</label>
    <textarea id="src_instruction" class="ed" rows="2" placeholder="e.g. straighten the bottle, brighten it, remove the reflection, centre it"></textarea>
    <div style="margin-top:10px"><button class="primary" onclick="studioRunSource()"><i class="ti ti-wand"></i> ${batch?('Clean source image for all '+n+' products'):'Clean &amp; generate from source'}</button></div>
    ${howWorks('source')}`;
}
// Reference-image picker: shows the product's source images (eBay first) so the
// user can choose which one to use as the AI reference. If none is picked, the
// first (auto-picked "cleanest") is used. Choice is stored in STUDIO.chosenRef.
function refPickerHTML(){
  const sku = (STUDIO.skus&&STUDIO.skus[0])||"";
  const it = _itemForSku(sku);
  let imgs=[];
  try{ imgs=_rowImages(it)||[]; }catch(e){ imgs=[]; }
  if(!imgs.length){
    const r=_refImgForItem(it); if(r) imgs=[r];
  }
  if(!imgs.length){
    // No auto-found source image -> let the user PROVIDE one (upload a file or
    // paste a URL) instead of falling back to text-only generation.
    const manual = STUDIO.manualRef || "";
    return `
      <div class="refpicker">
        <div class="cc" style="margin-bottom:6px;color:#e3b768">No source image was found for this product automatically. Add one below so the AI can keep your real product (otherwise it generates from the text description only).</div>
        <div class="secrow" style="gap:8px;align-items:center;flex-wrap:wrap">
          <button class="ib" onclick="document.getElementById('manual_ref_file').click()"><i class="ti ti-upload"></i> Upload product image</button>
          <span class="cc" style="font-size:11px">or paste an image URL:</span>
          <input id="manual_ref_url" class="ed" style="min-width:220px;flex:1" placeholder="https://…/product.jpg" value="${manual && /^https?:/i.test(manual)?esc(manual):''}" onchange="setManualRefUrl(this.value)">
        </div>
        <input type="file" id="manual_ref_file" accept="image/*" style="display:none" onchange="onManualRefFile(this)">
        ${manual?`<div class="refrow" style="margin-top:8px"><div class="refthumb on"><img src="${esc(manual)}" loading="lazy"><span class="refbadge">reference</span></div></div>`:''}
      </div>`;
  }
  // auto-pick the first as default reference if not chosen yet
  if(!STUDIO.chosenRef || imgs.indexOf(STUDIO.chosenRef)<0){ STUDIO.chosenRef = imgs[0]; }
  const thumbs = imgs.map((u,i)=>`
    <div class="refthumb${u===STUDIO.chosenRef?' on':''}" onclick="pickRef('${esc(u)}')" title="Use this image as the AI reference">
      <img src="${esc(u)}" loading="lazy">
      ${u===STUDIO.chosenRef?'<span class="refbadge">reference</span>':''}
    </div>`).join("");
  return `
    <div class="refpicker">
      <div class="cc" style="margin-bottom:6px"><b>Choose the reference image</b> — tap the eBay/source photo that best shows the product (cleanest, least text). The first is auto-selected.</div>
      <div class="refrow">${thumbs}</div>
    </div>`;
}
function pickRef(u){
  STUDIO.chosenRef = u;
  // re-render just the picker (cheap: re-render the whole source pane)
  const pane=document.getElementById("studio_source");
  if(pane){ const batch=(STUDIO.skus||[]).length>1; pane.innerHTML=sourcePaneHTML(batch,(STUDIO.skus||[]).length); }
}
function _rerenderSourcePane(){
  const pane=document.getElementById("studio_source");
  if(pane){ const batch=(STUDIO.skus||[]).length>1; pane.innerHTML=sourcePaneHTML(batch,(STUDIO.skus||[]).length); }
}
function setManualRefUrl(u){
  u=(u||"").trim();
  if(!u){ return; }
  STUDIO.manualRef=u; STUDIO.chosenRef=u;
  _rerenderSourcePane();
}
function onManualRefFile(input){
  const f=input && input.files && input.files[0];
  if(!f) return;
  if(!/^image\//.test(f.type)){ toast("Please choose an image file."); return; }
  const rd=new FileReader();
  rd.onload=function(){
    // store as a data URL — the generator accepts data URLs as the reference
    STUDIO.manualRef=rd.result; STUDIO.chosenRef=rd.result;
    _rerenderSourcePane();
    toast("Reference image added ✓");
  };
  rd.onerror=function(){ toast("Could not read that file."); };
  rd.readAsDataURL(f);
}
function srcSourceChange(){
  const v=(document.getElementById("src_source")||{}).value;
  const bo=document.getElementById("src_brandopts");
  const cn=document.getElementById("src_competitornote");
  if(bo) bo.style.display = v==="brand"?"block":"none";
  if(cn) cn.style.display = v==="competitor"?"block":"none";
}
async function studioRunSource(){
  const source=(document.getElementById("src_source")||{}).value||"competitor";
  const preserveLogo=(document.getElementById("src_preserve_logo")||{checked:true}).checked;
  const instr=(document.getElementById("src_instruction")||{}).value||"";
  const fid=(document.getElementById("studio_fidelity")||{}).value||"high";
  const single=(STUDIO.skus||[]).length===1;
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku);
    // single product: honour the reference the user picked (eBay picker) OR a
    // manually-provided upload/URL; batch: each product uses its own image.
    const ref=(single && (STUDIO.chosenRef||STUDIO.manualRef)) ? (STUDIO.chosenRef||STUDIO.manualRef) : _refImgForItem(it);
    jobs.push({sku:sku, ref:ref, label:(source==="brand"?"brand-clean":"logo-removed"), payload:{
      product_image:ref, title:(it&&it.title)||"", source:source, preserve_logo:preserveLogo,
      instruction:instr, fidelity:fid, text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)
    }});
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" image(s). Each is a paid call. Continue?")) return;
  studioRunBackground("source", jobs, total);
}

function secondaryPaneHTML(batch,n){
  const roles=[["benefit","Benefit infographic"],["feature","Feature / what's-in-box"],["lifestyle","Lifestyle in-use"],["dimensions","Size / dimensions"],["trust","Trust / quality"],["comparison","Why choose us"],["detail","Close-up detail / materials"],["usecase","Use-case / scenario"]];
  return `
    <div class="ideabox">
      <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-bulb"></i> Option A — Let the AI strategist design the set</div>
      <div class="cc" style="margin-bottom:8px">The AI thinks like a conversion strategist + your customer and proposes secondary-image concepts (which benefit to lead with, what objection to kill, what lifestyle moment sells it) for <b>this</b> product. Click below, then pick which ideas to generate.</div>
      <label class="cc" style="display:block;margin-bottom:3px">Instructions for the strategist (optional, not saved) — e.g. "don't show pets", "pour the medicine into the tub in one image", "show the product in only some images, not all"</label>
      <textarea id="strat_instr_secondary" class="ed" rows="2" placeholder='e.g. no pets; one image pouring liquid into a tub; show product in ~half the images so the buyer still knows what it is' style="margin-bottom:8px"></textarea>
      <button class="primary" onclick="studioStrategize('secondary')"><i class="ti ti-sparkles"></i> Suggest secondary ideas</button>
      <button class="primary" onclick="studioStrategize('secondary', true)" style="margin-left:6px" title="Ask the strategist for ideas AND generate them all automatically — no manual picking"><i class="ti ti-bolt"></i> Suggest &amp; auto-generate${batch?(' ('+n+' products)'):''}</button>
      <span id="sec_strat_status" class="cc" style="margin-left:8px"></span>
      ${howWorks('secAI')}
      <div id="sec_concepts" style="margin-top:10px"></div>
      <div class="cc" style="font-size:11px;margin-top:6px;opacity:.75">↑ The "Generate all ideas" button appears here <i>after</i> the AI suggests ideas — it generates the AI's concepts.</div>
    </div>

    <div class="ordiv"><span>OR</span></div>

    <div class="buildbox">
      <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-adjustments"></i> Option B — Build the set yourself</div>
      <div class="cc" style="margin-bottom:8px">You choose the roles and details. Secondary images each do <b>one job</b> — clean and premium, not cluttered. ${batch?('Applies to each of '+n+' selected products.'):''}</div>
      <div class="secrow">
        <label class="cc">Mode</label>
        <select id="sec_mode" class="ed" onchange="secModeChange()">
          <option value="planned">Planned roles (recommended)</option>
          <option value="free">Free-form (write my own)</option>
        </select>
      </div>
      <div id="sec_planned">
        <label class="cc" style="margin-top:8px;display:block">Choose the images to generate</label>
        <div class="secroles">
          ${roles.map(r=>`<label class="seccheck"><input type="checkbox" class="secrole" value="${r[0]}" ${r[0]==='benefit'?'checked':''}> ${r[1]}</label>`).join("")}
        </div>
      </div>
      <div id="sec_free" style="display:none">
        <label class="cc" style="margin-top:8px;display:block">Describe the secondary image(s) you want</label>
        <textarea id="sec_instruction" class="ed" rows="2" placeholder="e.g. an infographic showing the 2L capacity with a clean water splash, premium feel"></textarea>
        <div class="secrow" style="margin-top:8px;align-items:center;gap:8px">
          <label class="cc">How many images?</label>
          <input id="sec_free_count" type="number" min="1" max="10" value="1" class="ed" style="max-width:90px" title="How many secondary images to generate from your description (1–10).">
          <span class="cc" style="font-size:11px;opacity:.7">per product${batch?(' × '+n+' products'):''}</span>
        </div>
      </div>
      <div class="secrow" style="margin-top:10px">
        <label class="seccheck"><input type="radio" name="benc" value="1" checked> Highlight 1 benefit per image</label>
        <label class="seccheck"><input type="radio" name="benc" value="2"> Highlight 2 benefits per image</label>
      </div>
      <label class="cc" style="margin-top:8px;display:block">Specific benefit(s) to highlight (optional)</label>
      <input id="sec_benefit_text" class="ed" placeholder="e.g. dishwasher-safe; BPA-free">
      <div class="seccomp">
        <label class="cc" style="margin-top:10px;display:block">Competitor inspiration (optional, up to 3) — paste an image URL or upload</label>
        ${[0,1,2].map(i=>`
          <div class="seccomp8 row">
            <input id="sec_comp_${i}" class="ed" placeholder="competitor image URL" style="flex:1">
            <input type="file" id="sec_compf_${i}" accept="image/*" onchange="secCompPick(${i},this)" style="max-width:160px">
            <select id="sec_compm_${i}" class="ed" style="max-width:150px" title="How to use this reference">
              <option value="describe">Describe style (safe)</option>
              <option value="direct">Direct reference</option>
            </select>
          </div>`).join("")}
        <div class="cc" style="font-size:11px;margin-top:4px"><b>Describe style</b>: AI extracts the look (lighting, angle, effects like oil-drops) and reapplies it to your product — recommended, avoids copying. <b>Direct</b>: feeds the competitor image to the model directly.</div>
      </div>
      <div style="margin-top:12px"><button class="primary" onclick="studioRunSecondary()"><i class="ti ti-sparkles"></i> ${batch?('Generate my hand-built set for all '+n+' products'):'Generate my hand-built set'}</button></div>
      ${howWorks('secManual')}
    </div>`;
}
function secModeChange(){
  const m=(document.getElementById("sec_mode")||{}).value;
  document.getElementById("sec_planned").style.display = m==="planned"?"block":"none";
  document.getElementById("sec_free").style.display = m==="free"?"block":"none";
}
let SEC_COMP_DATA={};
function secCompPick(i, input){
  const f=input.files&&input.files[0]; if(!f) return;
  const r=new FileReader(); r.onload=()=>{ SEC_COMP_DATA[i]=r.result; toast("Competitor image "+(i+1)+" loaded"); };
  r.readAsDataURL(f);
}
function _collectCompRefs(){
  const refs=[];
  for(let i=0;i<3;i++){
    const url=(document.getElementById("sec_comp_"+i)||{}).value||"";
    const data=SEC_COMP_DATA[i]||"";
    const mode=(document.getElementById("sec_compm_"+i)||{}).value||"describe";
    const img=data||url.trim();
    if(img) refs.push({image:img, mode:mode});
  }
  return refs;
}
async function studioRunSecondary(){
  const mode=(document.getElementById("sec_mode")||{}).value;
  const benc=parseInt((document.querySelector('input[name="benc"]:checked')||{}).value||"1");
  const benefitText=(document.getElementById("sec_benefit_text")||{}).value||"";
  const compRefs=_collectCompRefs();
  let roles=[];
  if(mode==="planned"){
    roles=Array.from(document.querySelectorAll(".secrole:checked")).map(c=>c.value);
    if(!roles.length){ toast("Pick at least one image role."); return; }
  } else {
    const instr=(document.getElementById("sec_instruction")||{}).value||"";
    if(!instr.trim()){ toast("Describe the secondary image you want."); return; }
    // honor the "how many images?" count in free-form mode: make that many jobs,
    // each from the same description (the model varies them naturally).
    let cnt=parseInt((document.getElementById("sec_free_count")||{}).value||"1");
    if(isNaN(cnt)||cnt<1) cnt=1; if(cnt>10) cnt=10;
    roles=[]; for(let _i=0;_i<cnt;_i++) roles.push("__free__");
  }
  const freeInstr=(document.getElementById("sec_instruction")||{}).value||"";
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku); const ref=_refImgForItem(it);
    let _freeIdx=0;
    roles.forEach(role=>{
      // number multiple free-form images so results are distinguishable
      const roleLabel=role==="__free__"?("custom "+(++_freeIdx)):role;
      const body={ product_image:ref, title:(it&&it.title)||"", benefit_count:benc, benefit_text:benefitText,
        competitor_refs:compRefs, text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null),
        fidelity:((document.getElementById("studio_fidelity")||{}).value||"high") };
      if(role==="__free__") body.instruction=freeInstr; else body.role=role;
      jobs.push({sku:sku, ref:ref, label:roleLabel, payload:body});
    });
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" secondary image"+(total>1?"s":"")+" ("+STUDIO.skus.length+" product(s) × "+roles.length+" image(s)).\nEach is a paid OpenRouter call. Continue?")) return;
  studioRunBackground("secondary", jobs, total);
}

// ============ A+ CONTENT ============
let APLUS_MODULES={basic:[],premium:[]};
function aplusPaneHTML(batch,n){
  return `
    <div class="aplusnote">
      <b>A+ Content</b> requires <b>Amazon Brand Registry</b>. <b>Premium A+</b> additionally requires a Brand Story on all your ASINs and 15+ approved A+ submissions in the last 12 months. This tool generates module images at Amazon's <b>exact pixel dimensions</b> plus draft copy — you then upload them in Seller Central's A+ builder.
    </div>
    <div class="ideabox" style="margin-top:10px">
      <div style="font-weight:600;margin-bottom:4px"><i class="ti ti-bulb"></i> Option A — Let the AI strategist design your A+ story</div>
      <div class="cc" style="margin-bottom:8px">The AI thinks like a brand strategist + your customer and proposes a coherent A+ module sequence (hero banner, key benefits, how-to-use, ingredients, lifestyle, why-us, trust) for <b>this</b> product. Pick which modules to generate.</div>
      <div class="secrow" style="margin-bottom:8px;align-items:center;gap:8px">
        <label class="cc">Tier</label>
        <select id="ap_strat_tier" class="ed" style="max-width:280px">
          <option value="basic">Basic A+ (all Brand Registered sellers) — 5 modules</option>
          <option value="premium">Premium A+ (requires Premium access) — 7 modules</option>
        </select>
      </div>
      <button class="primary" onclick="studioStrategize('aplus')"><i class="ti ti-sparkles"></i> Suggest A+ modules</button>
      <button class="primary" onclick="studioStrategize('aplus', true)" style="margin-left:6px" title="Ask the strategist for A+ modules AND generate them all automatically — no manual picking"><i class="ti ti-bolt"></i> Suggest &amp; auto-generate${batch?(' ('+n+' products)'):''}</button>
      <span id="ap_strat_status" class="cc" style="margin-left:8px"></span>
      <label class="cc" style="display:block;margin:8px 0 3px">Instructions for the strategist (optional, not saved) — e.g. "don't show pets", "include a how-to-use module", "show the product in only some modules"</label>
      <textarea id="strat_instr_aplus" class="ed" rows="2" placeholder='e.g. no people or pets; one module showing it poured into a bath; keep palette blue/white'></textarea>
      <div id="ap_concepts" style="margin-top:10px"></div>
    </div>
    <div class="ordiv"><span>OR</span></div>
    <div class="buildbox">
    <div style="font-weight:600;margin-bottom:8px"><i class="ti ti-adjustments"></i> Option B — Pick the exact modules yourself</div>
    <div class="secrow" style="margin-top:10px">
      <label class="cc">Tier</label>
      <select id="ap_tier" class="ed" onchange="aplusRenderModules()">
        <option value="basic">Basic A+ (all Brand Registered sellers)</option>
        <option value="premium">Premium A+ (requires Premium access)</option>
      </select>
    </div>
    <label class="cc" style="margin-top:10px;display:block">Choose modules to generate (each shows Amazon's exact size)</label>
    <div id="ap_modules" class="apmods"><span class="cc">Loading modules…</span></div>
    <label class="cc" style="margin-top:10px;display:block">Benefit(s) / message to feature (optional)</label>
    <input id="ap_benefit" class="ed" placeholder="e.g. keeps drinks cold 24h; leak-proof lid">
    <label class="cc" style="margin-top:8px;display:block">Extra instruction (optional)</label>
    <textarea id="ap_instruction" class="ed" rows="2" placeholder="e.g. match our brand's clean blue palette, show the product on a marble surface"></textarea>
    <div style="margin-top:12px"><button class="primary" onclick="studioRunAplus()"><i class="ti ti-sparkles"></i> ${batch?('Generate A+ modules for all '+n+' products'):'Generate A+ module images'}</button></div>
    </div>${typeof howWorks==="function"?howWorks('aplus'):""}`;
}
async function aplusLoadModules(){
  if(APLUS_MODULES.basic.length) { aplusRenderModules(); return; }
  try{
    const j=await (await fetch("/aplus/modules")).json();
    if(j.ok){ APLUS_MODULES=j.modules; }
  }catch(e){}
  aplusRenderModules();
}
function aplusRenderModules(){
  const tier=(document.getElementById("ap_tier")||{}).value||"basic";
  const box=document.getElementById("ap_modules"); if(!box) return;
  const mods=APLUS_MODULES[tier]||[];
  if(!mods.length){ box.innerHTML='<span class="cc">No modules.</span>'; return; }
  box.innerHTML=mods.map(m=>`
    <label class="apmod">
      <input type="checkbox" class="apmodchk" value="${esc(m.id)}" ${m.id==='image_header_text'||m.id==='premium_full'?'checked':''}>
      <div>
        <div style="font-weight:600;font-size:13px">${esc(m.name)} <span class="apdim">${m.w}×${m.h}px</span></div>
        <div class="cc" style="font-size:11px">${esc(m.desc)}</div>
      </div>
    </label>`).join("");
}
async function studioRunAplus(){
  const tier=(document.getElementById("ap_tier")||{}).value||"basic";
  const benefit=(document.getElementById("ap_benefit")||{}).value||"";
  const instr=(document.getElementById("ap_instruction")||{}).value||"";
  const mods=Array.from(document.querySelectorAll(".apmodchk:checked")).map(c=>c.value);
  if(!mods.length){ toast("Pick at least one A+ module."); return; }
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku); const ref=_refImgForItem(it);
    mods.forEach(mid=>{
      const modName=((APLUS_MODULES[tier]||[]).find(m=>m.id===mid)||{}).name||mid;
      const body={ product_image:ref, title:(it&&it.title)||"", tier:tier, module_id:mid,
        benefit_text:benefit, instruction:instr, text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null),
        fidelity:((document.getElementById("studio_fidelity")||{}).value||"high") };
      jobs.push({sku:sku, ref:ref, label:modName, payload:body});
    });
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" A+ module image"+(total>1?"s":"")+" ("+STUDIO.skus.length+" product(s) × "+mods.length+" module(s)).\nEach is a paid OpenRouter call. Continue?")) return;
  studioRunBackground("aplus", jobs, total);
}
function _aplusAddResult(job, j, grid){
  grid=grid||document.getElementById("studio_results");
  const cardId="ares_"+Math.random().toString(36).slice(2);
  const dim=j&&j.module?(j.module.w+'×'+j.module.h+'px'):'';
  let copyHtml="";
  if(j&&j.copy){
    try{ const c=JSON.parse(j.copy); copyHtml=`<div class="apcopy"><b>${esc(c.headline||'')}</b><br>${esc(c.body||'')}</div>`; }
    catch(e){ copyHtml=`<div class="apcopy">${esc(j.copy)}</div>`; }
  }
  let inner;
  if(j&&j.ok&&j.data_url){
    inner=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
      <div class="srescap">${esc(job.sku)} · ${esc(job.modName)} <span class="apdim">${dim}</span></div>
      ${copyHtml}
      <div class="sresacts">
        <button class="ib" onclick="studioSave('${cardId}','${esc(job.sku)}')"><i class="ti ti-device-floppy"></i> Save</button>
        <button class="ib" onclick="studioDownload('${cardId}','${esc(job.sku)}')"><i class="ti ti-download"></i></button>
        <button class="ib" onclick="studioToDrive('${cardId}','${esc(job.sku)}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
      </div>`;
    STUDIO.results[cardId]={data_url:j.data_url, sku:job.sku};
  } else {
    inner=`<div class="sresfail">✗ ${esc((j&&j.error)||'failed')}</div><div class="srescap">${esc(job.sku)} · ${esc(job.modName)}</div>`;
  }
  const div=document.createElement("div");
  div.className="srescard"; div.id=cardId; div.innerHTML=inner;
  grid.appendChild(div);
}
function studioTab(t){
  document.querySelectorAll('#studiobody .stab').forEach(b=>b.classList.toggle('on', b.dataset.tab===t));
  ['recipe','creative','source','secondary','aplus','recipes_manage'].forEach(p=>{
    const el=document.getElementById('studio_'+p); if(el) el.style.display = (p===t)?'block':'none';
  });
  if(t==='aplus') aplusLoadModules();
}
function recipesManageHTML(){
  const list=(STUDIO.recipes||[]).map(r=>`
    <div class="recipecard">
      ${r.template_image?`<img src="${esc(r.template_image)}">`:'<div class="noimgmsg" style="height:60px"><span>no template image</span></div>'}
      <div style="flex:1">
        <div style="font-weight:600">${esc(r.name)}</div>
        <div class="cc" style="font-size:11px;max-height:38px;overflow:hidden">${esc(r.instructions)}</div>
      </div>
      <button class="ib" title="Delete recipe" onclick="deleteRecipe('${esc(r.id)}')"><i class="ti ti-trash"></i></button>
    </div>`).join("");
  return `
    <div class="cc" style="margin-bottom:8px">A recipe = a <b>template image</b> (a main image from one of your products) + the <b>changes you want</b>. Save it once and reuse it on any product. The AI improves your wording before generating, and always keeps each product faithful via its own reference image.</div>
    <label class="cc">Recipe name</label>
    <input id="rec_name" class="ed" placeholder="e.g. Shee'lady white hero">
    <label class="cc" style="margin-top:6px;display:block">Template image (optional — upload a main image to mimic)</label>
    <input type="file" id="rec_tpl" accept="image/*" onchange="recTplPick(this)">
    <div id="rec_tpl_prev"></div>
    <label class="cc" style="margin-top:6px;display:block">Changes / treatment you want</label>
    <textarea id="rec_instr" class="ed" rows="3" placeholder="e.g. pure white background, soft top-light, product centered at 85% with a subtle shadow, premium clean look"></textarea>
    <div style="margin-top:8px"><button class="primary" onclick="saveRecipe()"><i class="ti ti-device-floppy"></i> Save recipe</button> <span id="rec_status" class="cc"></span></div>
    <div style="margin-top:14px">${list||'<div class="cc">No recipes saved yet.</div>'}</div>`;
}
let REC_TPL_DATA="";
function recTplPick(input){
  const f=input.files&&input.files[0]; if(!f) return;
  const r=new FileReader(); r.onload=()=>{ REC_TPL_DATA=r.result; document.getElementById("rec_tpl_prev").innerHTML='<img src="'+REC_TPL_DATA+'" style="max-width:120px;border-radius:8px;margin-top:6px">'; };
  r.readAsDataURL(f);
}
async function saveRecipe(){
  const name=(document.getElementById("rec_name")||{}).value||"";
  const instr=(document.getElementById("rec_instr")||{}).value||"";
  const st=document.getElementById("rec_status");
  if(!name.trim()||!instr.trim()){ if(st) st.textContent="Name and changes are required."; return; }
  if(st) st.innerHTML='<span class="genspin"></span> saving…';
  try{
    const j=await (await fetch("/recipes/save",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({brand:STUDIO.brand, name:name.trim(), instructions:instr.trim(), template_image:REC_TPL_DATA})})).json();
    if(!j.ok){ if(st) st.textContent=j.error||"failed"; return; }
    REC_TPL_DATA=""; await loadRecipes();
    document.getElementById("studio_recipes_manage").innerHTML=recipesManageHTML();
    if(st) st.textContent="Saved ✓";
  }catch(e){ if(st) st.textContent="Error: "+e; }
}
async function deleteRecipe(id){
  if(!confirm("Delete this recipe?")) return;
  await fetch("/recipes/delete",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({brand:STUDIO.brand, id:id})});
  await loadRecipes();
  document.getElementById("studio_recipes_manage").innerHTML=recipesManageHTML();
  renderStudio();
}
// ---- shared background-job runner: submit jobs, poll, render as they complete ----
let STUDIO_POLL=null;
function _studioRenderResult(kind, r, grid){
  // r has .ok,.data_url,.label,.sku and (for aplus) .module,.copy
  if(kind==="aplus"){ _aplusAddResult({sku:r.sku, modName:(r.module&&r.module.name)||r.label||""}, r, grid); }
  else { _studioAddResult({sku:r.sku, strategy:r.label}, r, grid); }
}
async function studioRunBackground(kind, jobs, total){
  // Each section (main / secondary / aplus) has its OWN concept list but they
  // shared a single results container before -- so generating from the secondary
  // or A+ section wrote into (or failed to find) the MAIN container and looked
  // like "nothing happened". Resolve the right containers for the active section,
  // and create them on the fly if that section doesn't have them yet.
  const section = STUDIO.conceptKind || (kind==="concept" ? (STUDIO.conceptKind||"main") : "main");
  function _ensure(anchorId, id, cls){
    let el=document.getElementById(id);
    if(el) return el;
    const anchor=document.getElementById(anchorId);
    if(!anchor) return null;
    el=document.createElement("div");
    el.id=id; if(cls) el.className=cls; el.style.marginTop="14px";
    anchor.parentNode.insertBefore(el, anchor.nextSibling);
    return el;
  }
  let prog, grid;
  if(section==="secondary"){
    prog=_ensure("sec_concepts","sec_progress");
    grid=_ensure("sec_progress","sec_results","studiogrid");
  } else if(section==="aplus"){
    prog=_ensure("ap_concepts","ap_progress");
    grid=_ensure("ap_progress","ap_results","studiogrid");
  }
  // fall back to the main containers if section ones couldn't be made
  prog=prog||document.getElementById("studio_progress");
  grid=grid||document.getElementById("studio_results");
  if(!prog||!grid){ toast("Couldn't find a place to show results — try reopening Image Studio."); return; }
  grid.innerHTML=""; STUDIO.results={};
  if(STUDIO_POLL){ clearInterval(STUDIO_POLL); STUDIO_POLL=null; }
  prog.innerHTML='<span class="genspin"></span> Starting '+total+' generation'+(total>1?'s':'')+' in the background…';
  let resp;
  try{
    resp=await (await fetch("/genimage/start_batch",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind:kind, jobs:jobs})})).json();
  }catch(e){ prog.innerHTML='<span style="color:#e0696b">Could not start: '+esc(String(e))+'</span>'; return; }
  if(!resp.ok){ prog.innerHTML='<span style="color:#e0696b">'+esc(resp.error||"failed to start")+'</span>'; return; }
  const jobId=resp.job;
  STUDIO.currentJob=jobId;
  let shown=0;
  prog.innerHTML='<span class="genspin"></span> Generating in background… <span class="cc">you can keep using the app; results appear below as they finish.</span>';
  STUDIO_POLL=setInterval(async ()=>{
    try{
      const st=await (await fetch("/genimage/job_status?job="+encodeURIComponent(jobId))).json();
      if(!st.ok){ return; }
      // render any new results
      for(let i=shown;i<st.results.length;i++){ _studioRenderResult(kind, st.results[i], grid); }
      shown=st.results.length;
      if(st.status!=="running"){
        clearInterval(STUDIO_POLL); STUDIO_POLL=null;
        const okN=st.results.filter(r=>r.ok).length;
        prog.innerHTML='<span style="color:#7fd99a">✓ Done — '+okN+'/'+st.total+' succeeded. <b>All generated images were auto-saved to each product\u2019s media library</b> (Image refs), so they\u2019re safe even if you close this.</span>'
          + (st.error?(' <span style="color:#e0696b">'+esc(st.error)+'</span>'):'');
      } else {
        prog.innerHTML='<span class="genspin"></span> Generating '+st.done+'/'+st.total+' in background… <span class="cc">each finished image is auto-saved to its media library; safe to close or keep working.</span>';
      }
    }catch(e){}
  }, 2000);
}

// ---- STRATEGIST: AI invents conversion-focused image concepts ----
async function saveStudioInstructions(){
  const ta=document.getElementById("studio_custom_instructions");
  const st=document.getElementById("studio_ci_status");
  if(!ta) return;
  const txt=ta.value||"";
  if(st) st.innerHTML='<span class="genspin"></span> saving…';
  try{
    const j=await (await fetch("/genimage/instructions",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({instructions:txt, scope:"account", id:(CUR_ACCOUNT&&CUR_ACCOUNT.id)||""})})).json();
    window.IMG_INSTRUCTIONS = j.instructions||"";
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ saved — applied to every image</span>';
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">could not save</span>'; }
}
async function loadStudioInstructions(){
  try{
    const j=await (await fetch("/genimage/instructions?id="+encodeURIComponent((CUR_ACCOUNT&&CUR_ACCOUNT.id)||""))).json();
    window.IMG_INSTRUCTIONS = j.instructions||"";
    const ta=document.getElementById("studio_custom_instructions");
    if(ta && !ta.value) ta.value=window.IMG_INSTRUCTIONS;
  }catch(e){}
}
async function studioStrategize(kind, autoGen){
  const statusId = kind==="main" ? "studio_strat_status" : (kind==="aplus" ? "ap_strat_status" : "sec_strat_status");
  const boxId = kind==="main" ? "studio_concepts" : (kind==="aplus" ? "ap_concepts" : "sec_concepts");
  const st=document.getElementById(statusId);
  const box=document.getElementById(boxId);
  if(STUDIO.skus.length>1){
    // for batch, strategize on the first product as the template, applied to all
    if(st) st.innerHTML='<span class="cc">(using the first selected product to design concepts, then applies to all)</span>';
  }
  const sku=STUDIO.skus[0];
  const it=_itemForSku(sku); const ref=_refImgForItem(it);
  if(!ref){ if(st) st.innerHTML='<span style="color:#e0696b">first product has no reference image</span>'; return; }
  if(st) st.innerHTML='<span class="genspin"></span> The strategist is thinking like a customer & conversion expert…';
  if(box) box.innerHTML="";
  // How many ideas to ask for depends on the section:
  //  - secondary: Amazon allows up to 8 extra images, so propose 8
  //  - aplus: match the chosen tier's module count (basic 5 / premium 7)
  //  - main: 3 hero concepts
  let _n = 3;
  if(kind==="secondary") _n = 8;
  else if(kind==="aplus"){
    // read the tier selector that lives in Option A (the strategist's own), so
    // the user can pick Premium for the strategist directly. Fall back to Option
    // B's tier, then basic.
    const _tier = ((document.getElementById("ap_strat_tier")||{}).value
                   || (document.getElementById("ap_tier")||{}).value || "basic");
    _n = _tier==="premium" ? 7 : 5;
    STUDIO.aplusTier = _tier;   // remember so generated modules go to the right subfolder
  }
  try{
    // per-run instructions for the strategist (not saved) — keyed by section
    const _instrEl=document.getElementById("strat_instr_"+kind);
    const _customInstr=(_instrEl && _instrEl.value || "").trim();
    const j=await (await fetch("/genimage/strategize",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({product_image:ref, title:(it&&it.title)||"", kind:kind, n:_n, text_provider:(window.AI_TEXT||null), custom_instructions:_customInstr})})).json();
    if(!j.ok){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; return; }
    const concepts=j.concepts||[];
    if(!concepts.length){ if(st) st.innerHTML='<span class="cc">No concepts returned — try again.</span>'; return; }
    STUDIO.concepts=concepts; STUDIO.conceptKind=kind;
    if(st) st.innerHTML='<span style="color:#7fd99a">✓ '+concepts.length+' ideas'+(autoGen?' — generating all now…':' — pick to generate')+'</span>';
    if(box) box.innerHTML=concepts.map((c,i)=>`
      <div class="conceptcard">
        <div style="flex:1">
          <div style="font-weight:600;font-size:13px">${esc(c.title||('Idea '+(i+1)))}</div>
          <div class="cc" style="font-size:11px;margin:2px 0"><b>Customer insight:</b> ${esc(c.customer_insight||"")}</div>
          <div class="cc" style="font-size:11.5px;margin:2px 0">${esc(c.concept||"")}</div>
          <div class="cc" style="font-size:10.5px;opacity:.8"><b>Art direction:</b> ${esc(c.art_direction||"")}</div>
        </div>
        <button class="ib" onclick="studioGenConcept(${i})"><i class="ti ti-photo"></i> Generate${STUDIO.skus.length>1?(' ×'+STUDIO.skus.length):''}</button>
      </div>`).join("") +
      (concepts.length>1?`<div style="margin-top:8px"><button class="primary" onclick="studioGenAllConcepts()"><i class="ti ti-sparkles"></i> Generate all ${concepts.length} AI ideas${STUDIO.skus.length>1?(' for each of '+STUDIO.skus.length+' products'):''}</button></div>`:"");
    // AUTO-ACCEPT: if the user asked to auto-generate, skip the manual pick and
    // generate every suggested concept right away (across all selected products).
    if(autoGen){ studioGenAllConcepts(true); }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">Error: '+esc(String(e))+'</span>'; }
}
function _conceptJobs(concepts){
  const kind=STUDIO.conceptKind||"main";
  const fid=(document.getElementById("studio_fidelity")||{}).value||"high";
  const ci=((document.getElementById("studio_custom_instructions")||{}).value||window.IMG_INSTRUCTIONS||"");
  let jobs=[];
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku); const ref=_refImgForItem(it);
    concepts.forEach(c=>{
      jobs.push({sku:sku, ref:ref, label:(c.title||"idea"), payload:{
        product_image:ref, title:(it&&it.title)||"", kind:kind,
        concept:c.concept||"", art_direction:c.art_direction||"",
        fidelity:fid, custom_instructions:ci,
        tier:(STUDIO.aplusTier||"basic"),
        text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)
      }});
    });
  });
  return jobs;
}
function studioGenConcept(i){
  const c=(STUDIO.concepts||[])[i]; if(!c) return;
  const jobs=_conceptJobs([c]);
  studioRunBackgroundConcept(jobs, jobs.length);
}
function studioGenAllConcepts(auto){
  const concepts=STUDIO.concepts||[]; if(!concepts.length) return;
  const jobs=_conceptJobs(concepts);
  // when auto-invoked (user clicked "Suggest & auto-generate"), they've already
  // opted in, so skip the paid-call confirm; otherwise still confirm for >4.
  if(!auto && jobs.length>4 && !confirm("This will generate "+jobs.length+" image(s). Each is a paid call. Continue?")) return;
  studioRunBackgroundConcept(jobs, jobs.length);
}
function studioRunBackgroundConcept(jobs, total){
  studioRunBackground("concept", jobs, total);
}

async function studioRun(mode){
  let jobs=[];
  const strategies = mode==="creative" ? ["hero_straight","hero_angle","hero_personality"] : [null];
  const recipeId = mode==="recipe" ? ((document.getElementById("studio_recipe_sel")||{}).value||"") : "";
  const inspo = mode==="creative" ? ((document.getElementById("studio_inspo")||{}).value||"") : "";
  if(mode==="recipe" && !recipeId){ toast("Pick a recipe first."); return; }
  STUDIO.skus.forEach(sku=>{
    const it=_itemForSku(sku);
    const ref=_refImgForItem(it);
    strategies.forEach(strat=>{
      const body={ product_image:ref, title:(it&&it.title)||"", text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null), fidelity:((document.getElementById("studio_fidelity")||{}).value||"high") };
      if(mode==="recipe"){ body.mode="recipe"; body.recipe_id=recipeId; body.brand=STUDIO.brand; }
      else { body.mode="creative"; body.strategy=strat; body.inspiration=inspo; }
      jobs.push({sku:sku, ref:ref, label:(strat?strat.replace(/_/g,' '):'main'), payload:body});
    });
  });
  const total=jobs.length;
  if(total>4 && !confirm("This will generate "+total+" image"+(total>1?"s":"")+" ("+STUDIO.skus.length+" product(s)"+(mode==="creative"?" × 3 variations":"")+").\nEach is a paid OpenRouter call. Continue?")) return;
  studioRunBackground(mode==="creative"?"creative":"recipe", jobs, total);
}
// ============================================================
// "HOW IT WORKS" LOGIC FRAMEWORK (admin-visible transparency layer)
// One central registry + one helper. To document any feature anywhere in the
// app, add an entry to LOGIC_REGISTRY and drop ${howWorks('key')} after its button.
// Visibility is gated: admin sees panels when LOGIC_VISIBLE is true; a non-admin
// (or admin in "preview as user" mode) sees nothing.
// ============================================================
window.LOGIC_VISIBLE = true;      // set from /ai/settings admin flags on load
function _mdl(){
  var f=((document.getElementById("studio_fidelity")||{}).value||"high");
  return { C:(window.AI_IMAGE||"your image model"), T:(window.AI_TEXT||"your prompt model"),
    fid:f, strn:(f==="high"?"0.2":(f==="medium"?"0.35":"0.55")) };
}
function LOGIC_REGISTRY(){
  const {C,T,strn} = _mdl();
  return {
    strategist: { title:"How the AI strategist works", steps:[
      `<b>Reads your real product.</b> Your product image goes to the prompt AI (<code>${esc(T)}</code>) for a forensic read — shape, proportions, material, exact colours/gradient, every line of label text, the logo — producing a written spec.`,
      `<b>Thinks like a strategist + customer.</b> That spec + your title go to <code>strategize_images</code>, prompted to reason as an Amazon conversion expert and as your buyer. It invents 3 concepts: <i>customer insight</i>, <i>concept</i>, <i>art direction</i>.`,
      `<b>You pick.</b> Nothing is generated yet — you choose one idea or "Generate all".`,
      `<b>Generates faithfully.</b> The art direction runs through <code>run_pipeline</code> → <code>from_concept</code>: your product image attached as reference, image AI (<code>${esc(C)}</code>) renders at <b>strength ${strn}</b> (low = stay close), <b>4K, pure white</b>.`,
      `<b>Auto-saves</b> each finished image to this product's media library immediately.` ]},
    ready3: { title:"How the 3 ready-made variations work", steps:[
      `<b>No idea-invention step</b> — uses 3 fixed treatments: straight-on hero, flattering angle, creative "personality" shot.`,
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec, folded into each brief so the product can't drift.`,
      `<b>Writes the prompt.</b> <code>enhance_prompt</code> turns each treatment + spec into a detailed prompt with strict pure-white-background rules.`,
      `<b>Generates with your product as reference.</b> Image AI (<code>${esc(C)}</code>) renders each at <b>strength ${strn}, 4K, 1:1 pure white</b>.`,
      `<b>Background + auto-save.</b> All 3 run in the background; each saves as it finishes. Use <i>Redo this</i> on any that drifts.` ]},
    secAI: { title:"How the AI-designed secondary set works", steps:[
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec.`,
      `<b>Invents secondary concepts</b> — which benefit to lead with, what objection to kill, which lifestyle moment sells it (text/graphics allowed on secondary images).`,
      `<b>You pick which to generate.</b>`,
      `<b>Generates faithfully</b> via <code>run_pipeline</code> with your product attached at <b>strength ${strn}, 4K</b> (image AI: <code>${esc(C)}</code>).`,
      `<b>Auto-saves</b> every result.` ]},
    secManual: { title:"How your hand-built secondary set works", steps:[
      `<b>You define the set</b> — roles ticked, benefits per image, specific benefits, competitor inspiration.`,
      `<b>Competitor inspiration handled safely.</b> "Describe style" → vision AI extracts only the <i>technique</i> (lighting, angle, effects) and reapplies it to your product (no copying). "Direct" → feeds their image to the model.`,
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec.`,
      `<b>Generates each role</b> with your product attached at <b>strength 0.35, 4K</b> (image AI: <code>${esc(C)}</code>), one clear message per image.`,
      `<b>Auto-saves</b> every result.` ]},
    source: { title:"How the Main image (clean white bg) works", steps:[
      `<b>Pick the reference photo.</b> The product's source images (eBay first) are shown as thumbnails — tap the cleanest one that best shows the product. If you don't pick, the first is auto-selected.`,
      `<b>Reads the source photo</b> (eBay/Amazon scrape or brand upload) with the prompt AI (<code>${esc(T)}</code>) for a product spec.`,
      `<b>Applies the logo rule by source.</b> Competitor/eBay → remove a brand logo if present, blend to surface (no replacement); no logo → leave as-is. Brand CSV → keep product <i>and</i> logo (unless you uncheck "preserve logo").`,
      `<b>Keeps the product identical</b> — only the logo and your optional edits change.`,
      `<b>Generates clean</b> with your chosen reference attached at your fidelity strength, target <b>2500px, pure white</b> (image AI: <code>${esc(C)}</code>).`,
      `<b>Auto-saves</b> the result, and shows its real <b>pixel size and file size</b> under the image.` ]},
    drive: { title:"How Drive image storage works", steps:[
      `<b>Set a master folder per account.</b> In Account &amp; sheets, paste a Google Drive folder URL. That folder becomes the home for this account's generated images.`,
      `<b>Share it with the service account.</b> Just like a Google Sheet, the folder must be shared (Editor) with the service-account email shown in the Drive panel — otherwise uploads are denied.`,
      `<b>Per-product subfolders.</b> Each image is uploaded into a subfolder named <code>{SKU}_{ProductName}</code>, created automatically if it doesn't exist.`,
      `<b>Your own Drive.</b> Images live in your Drive, organised by product, safe and separate from the app.` ]},
    content_index: { title:"How the content fields & indexing work", steps:[
      `<b>Title</b> — fill close to the 75-char cap (the hard cap lands 27 Jul 2026). Front-load the first ~70 chars; mobile truncates there. Fully indexed, highest A10 weight.`,
      `<b>Item Highlights</b> — a structured 125-char field shown with the title in search and on the PDP; carries its own weight.`,
      `<b>Bullets</b> — 500 chars each, but Amazon indexes only the first ~1,000 <i>bytes</i> across ALL five combined. The meter above the bullets shows how much of that budget is used; overflow still shows to shoppers but isn't indexed.`,
      `<b>Description</b> — up to 2,000 chars incl. HTML; indexed but lowest weight.`,
      `<b>Backend search terms</b> — 249 <i>bytes</i> (not chars). One byte over silently de-indexes the whole field, so the counter is in bytes and warns near the limit.` ]},
    required_fields: { title:"How required fields are shown", steps:[
      `<b>The red ★</b> marks a field Amazon requires, read straight from the live schema's <code>required</code> list for this product type.`,
      `<b>Before Preview</b> we show every <i>static</i> required field. Some are <i>conditional</i> (e.g. the lithium-battery group) and Amazon only reveals them after a Preview.`,
      `<b>After Preview</b> every field Amazon flags gets a visible box — including nested sub-fields — so nothing the validator wants is hidden from you.`,
      `<b>Product type</b> defaults to the type Amazon assigned in the catalogue ("Amazon-assigned"); changing it warns you, because a wrong type causes rejection.` ]},
    // ---------- OPTIMIZE: the red-dot fixer ----------
    opt_fetch: { title:"How 'Optimize live listing' loads the data", steps:[
      `<b>Reads the LIVE listing from Amazon.</b> Calls SP-API <code>getListingsItem</code> with <code>includedData="attributes,summaries,issues"</code> on the connected seller account — so the title, status and fields are the real current ones, not a cached report.`,
      `<b>Shows Amazon's own issues verbatim.</b> The warnings/errors come straight from Amazon's <code>issues</code> array (e.g. "invalid condition type", "missing item_dimensions") and are parsed to name the exact attributes at fault. This text is Amazon's, not the app's guess.`,
      `<b>Nothing is changed.</b> This step only reads. You draft edits against it, and only approved fields are pushed later.` ]},
    opt_diagnose: { title:"How 'Suggest fixes with AI' works", steps:[
      `<b>Re-reads the live listing</b> (<code>getListingsItem</code>) and collects ONLY the attributes Amazon flagged as missing or invalid.`,
      `<b>Asks the AI for values for just those fields.</b> The prompt AI (<code>${esc(T)}</code>) proposes values <i>only</i> for the flagged attributes. These are clearly labeled <b>AI estimates</b> — inferred, not from Amazon.`,
      `<b>You review and tick.</b> Nothing is pushed here. You edit/correct each suggestion and tick only the ones you want.`,
      `<b>Honest limit:</b> dimensions with units are safest finished in Seller Central, which structures the nested fields correctly.` ]},
    opt_push: { title:"How approved changes reach Amazon", steps:[
      `<b>Gated by your approval.</b> The push only runs with a <code>confirmed</code> flag, and only the fields you ticked are sent — nothing else.`,
      `<b>Builds a minimal patch.</b> <code>_build_patches</code> turns your approved fields into JSON-Patch operations, applied via SP-API <code>patchListingsItem</code> (a targeted edit, not a full re-submit).`,
      `<b>Only approved fields change</b> on the live listing; everything you didn't tick is left untouched.` ]},
    opt_rewrite: { title:"How 'Custom AI rewrite' works", steps:[
      `<b>Uses your instruction as the driver.</b> You tell the AI what you want (e.g. "no brand in title, emphasise durability"). A product link is optional extra context.`,
      `<b>Pulls source context if given.</b> Any eBay/Amazon link you paste is fetched and fed in so the AI knows the real product.`,
      `<b>Brand is optional context only.</b> The account's brand is passed as context but never forced into copy — and the app never falls back to the account label as a brand (this fixed the "label leaked into title" bug).`,
      `<b>Applies your compliance & IP rules.</b> The rewrite still runs under <code>compliance_rules.json</code> and <code>ip_rules.json</code> (forbidden phrases / safe words), so the new copy stays Amazon-safe.`,
      `<b>Returns a draft</b> (title/bullets/description) for your review — nothing is pushed automatically.` ]},
    // ---------- GENERATION PIPELINE ----------
    gen_pipeline: { title:"How 'Generate' builds a listing (the full pipeline)", steps:[
      `<b>1 · Scrapes the product.</b> For each source row it pulls real data: the eBay item (Browse API via <code>fetch_ebay_supplement</code> — specifics + images) and the competitor Amazon ASIN (<code>get_competitor_asin_data</code>, plus a crawl4ai PDP scrape as fallback). It also pulls pricing/fees and computes financials.`,
      `<b>2 · Writes the prompt.</b> <code>build_prompt</code> folds the scraped specifics, pricing, keywords (autocomplete) and your rules into a structured brief.`,
      `<b>3 · Generates the listing</b> with the Claude API (<code>generate_listing</code>) — title, bullets, description, and the product-type attributes Amazon's schema requires.`,
      `<b>4 · Runs the compliance + IP gates</b> (see the next two panels) — these can downgrade the status.`,
      `<b>5 · Builds the SKU</b> as <code>{source_price}_{N}Days_{COMP_ASIN}</code> (e.g. <code>7.99_3Days_B0XYZ12345</code>); duplicates get <code>_2</code>, <code>_3</code> appended.`,
      `<b>6 · Maps the flat-file route</b> (<code>detect_route</code> → FILE1 or FILE2) for the right Amazon template, and writes everything to your Google Sheet with a Status for review. <b>Nothing is submitted to Amazon here</b> — generation only fills the sheet.` ]},
    gen_compliance: { title:"How the compliance gate works", steps:[
      `<b>Checks the listing against your rules.</b> <code>check_compliance</code> screens the generated copy using <code>compliance_rules.json</code> (your 17 UK regulatory categories) for risky claims and category risk level.`,
      `<b>Can downgrade the status.</b> If the product falls in a HIGH-risk category, a <code>NEEDS_REVIEW</code> row is downgraded to <code>COMPLIANCE_HOLD</code> so you must review it before it can go live.`,
      `<b>Safety-net defaults</b> are applied where required fields are missing, so the listing isn't left in a non-compliant state silently.` ]},
    gen_ip: { title:"How the IP / trademark gate works", steps:[
      `<b>Screens for brand/trademark risk.</b> <code>check_ip_violations</code> matches the copy against <code>ip_rules.json</code> — your list of forbidden phrases (e.g. "compatible with X", "replacement for X") and ~470 safe words.`,
      `<b>IP_HOLD supersedes other holds.</b> If a forbidden phrase is found, the status is set to <code>IP_HOLD</code> — which overrides <code>NEEDS_REVIEW</code> and <code>COMPLIANCE_HOLD</code> (a hard ERROR stays an error).`,
      `<b>You review every hold.</b> The full status flow is: <code>NEEDS_REVIEW → COMPLIANCE_HOLD / IP_HOLD → APPROVED → export</code>. Only APPROVED rows are exported to the flat file.` ]},
    // ---------- LISTINGS GRID / SYNC ----------
    grid_load: { title:"How the listings grid loads", steps:[
      `<b>Pulls your live listings from Amazon.</b> <code>/live/catalog</code> requests a Reports-API report (<code>GET_MERCHANT_LISTINGS_ALL_DATA</code>) for the connected account + marketplace, then parses each row.`,
      `<b>Reads real fields per listing.</b> From the report it captures SKU, ASIN, title, price, quantity, status, brand, and — importantly — <code>fulfillment-channel</code> (FBA/FBM) and <code>merchant-shipping-group</code>.`,
      `<b>Caches briefly</b> so re-opening is instant. A normal load reuses a recent report/cache; it does <i>not</i> hit Amazon every time.`,
      `<b>Drafts vs Live vs All</b> just filters what's shown — Drafts are from your sheet, Live are pulled from Amazon, All merges both.` ]},
    grid_enrich: { title:"How each card gets its image, title, FBA/FBM & shipping", steps:[
      `<b>Enriches in batches.</b> <code>/live/images</code> calls <code>getListingsItem</code> with <code>includedData="summaries,issues,fulfillmentAvailability,attributes"</code> for the visible SKUs.`,
      `<b>Pulls the real main image and live title</b> (from <code>summaries</code>) — so the title reflects any edit you made immediately, not the cached report.`,
      `<b>Shows fulfillment + handling.</b> FBA/FBM comes from the fulfillment data; FBM handling time is the real <code>lead_time_to_ship_max_days</code>.`,
      `<b>Honest caveat on dates.</b> "Ships by / delivery ~" dates are <i>estimates</i> the app computes (FBM ≈ your handling + ~5d transit; FBA ≈ ~2d) — they are not Amazon's exact promised dates.` ]},
    grid_sync: { title:"How 'Sync' forces fresh data", steps:[
      `<b>Forces a brand-new report.</b> Sync sends <code>force=true</code>, which <i>skips</i> the report/cache reuse and generates a FRESH Reports-API report (this fixed the bug where Sync reused stale data).`,
      `<b>Clears the per-listing cache.</b> It drops the cached images/status/title/fulfillment for this account+marketplace, so everything re-pulls from Amazon.`,
      `<b>Use it after edits or going live.</b> Amazon can take a little time to reflect changes; if a fresh report isn't ready yet, Sync again in a minute and it loads.` ]},
    // ---------- ACCOUNTS / CONNECTION ----------
    acct_connect: { title:"How connecting an account to Amazon works", steps:[
      `<b>You provide SP-API credentials.</b> Seller/merchant ID, LWA client ID, LWA client secret, and a refresh token — the four things Amazon's Selling Partner API needs (<code>account_creds</code>).`,
      `<b>"Connected" = a real refresh token.</b> An account counts as connected only when its refresh token is real (not a <code>PUT_</code>/<code>ROTATE</code> placeholder). Until then it's <b>draft-only</b>: you can build and generate listings, but live features (pulling listings, optimize, submit) are disabled.`,
      `<b>Secrets stay local.</b> The client secret and refresh token are stored in your local <code>config.json</code> and shown as masked dots — the app never displays the saved values, and you can leave them blank to keep the existing ones.`,
      `<b>Each account is a workspace.</b> Account → Marketplace → Listings. Brands are data attached to an account, not a separate level.` ]},
    acct_marketplaces: { title:"How 'Detect marketplaces' works", steps:[
      `<b>Asks Amazon which marketplaces this account sells in.</b> Calls SP-API <code>getMarketplaceParticipations</code> (Sellers API) with the account's credentials.`,
      `<b>Maps IDs to codes</b> using the built-in marketplace table (e.g. <code>A1F83G8C2ARO7P</code> → UK, <code>ATVPDKIKX0DER</code> → US) and saves the detected codes onto the account.`,
      `<b>This is why the workspace shows real marketplaces</b> — the US/UK/DE tabs reflect where the account is actually live, pulled from Amazon, not typed in by hand.` ]},
    acct_brands: { title:"How 'Detect brands' works (and its honest limit)", steps:[
      `<b>Reads the brand field from live listings.</b> It derives the brands actually used on the account from the <code>brand</code> field in the listings report, merged with any brands you typed.`,
      `<b>Honest limit:</b> Amazon has no clean "list my Brand Registry brands" API — so this is what's <i>seen on live listings</i>, not a Brand Registry pull. Add or correct brands manually if needed.` ]},
    // ---------- COGS ----------
    cogs: { title:"How COGS & the profit estimate work", steps:[
      `<b>Two ways to know your cost.</b> <code>_resolve_cogs</code> uses a priority: a <b>manual override</b> you set per SKU wins; otherwise it reads the cost <b>embedded in the dropshipping SKU</b> (the <code>{source_price}_…</code> prefix).`,
      `<b>Bulk upload.</b> The COGS CSV (<code>/cogs/upload</code>) accepts SKU + cost rows and stores them as per-account overrides, so you can set many at once.`,
      `<b>Profit is an estimate.</b> <code>_estimate_profit</code> = price − COGS − a <b>15% referral fee</b> (default). It's a quick margin guide, not Amazon's exact fee — real fees vary by category and include other charges.`,
      `<b>Stored locally</b> in your COGS overrides file, keyed by account+SKU.` ]},
    // ---------- SUBMIT LIVE ----------
    submit_live: { title:"How 'Submit · go live' publishes to Amazon", steps:[
      `<b>Double-confirms the destination.</b> First it calls <code>/submit/target</code> to find the <b>active account</b> and marketplace, then shows you a confirm dialog <b>naming that exact account</b> — so you can't publish to the wrong store.`,
      `<b>Checks credentials exist.</b> If the view's marketplace has no SP-API credentials, it stops and tells you — nothing is sent.`,
      `<b>Publishes only APPROVED rows.</b> It runs <code>api_submit</code>, which creates or replaces live listings for every <b>APPROVED / API_READY</b> row in this view — rows still in NEEDS_REVIEW / holds are skipped.`,
      `<b>This is the only step that writes to Amazon.</b> Generation, optimize drafts, and image generation never publish — only this button does, and only after your confirmation.` ]},
    // ---------- RECIPES / MEDIA / A+ ----------
    recipes: { title:"How image recipes work", steps:[
      `<b>A recipe is a saved, reusable treatment.</b> It stores a template image + the instructions/changes you want (e.g. "droplets on the bottle, soft top light"), so you can apply the same look to any product without retyping it.`,
      `<b>Recipes are per-brand.</b> They're saved against the active brand, but the studio also exposes recipes from your <i>other</i> brands (clearly labelled) so you can reuse across.`,
      `<b>Applying a recipe</b> runs the normal pipeline: your product image is attached as reference and the recipe's instructions become the brief — the product itself stays identical, only the treatment is applied.`,
      `<b>Stored locally</b> in <code>image_recipes.json</code>.` ]},
    media: { title:"How the media library & auto-save work", steps:[
      `<b>Per-SKU folders.</b> Every product has its own media folder; <code>/media/list</code> shows the stored images grouped by SKU, and <code>/media/<sku>/<file></code> serves them.`,
      `<b>Auto-save on generation.</b> Every image the studio generates is written to that product's folder immediately (<code>generated_*.png</code>) — so results are never lost even if you close the window.`,
      `<b>Manual save & upload.</b> "Save to media" stores a chosen image; you can also upload your own images into a SKU's folder. Delete removes a file from the folder.`,
      `<b>These are local files</b> on your machine — separate from Amazon. You choose which to use when building a listing.` ]},
    aplus: { title:"How A+ Content generation works (and what Amazon requires)", steps:[
      `<b>Generates module images at Amazon's EXACT pixel dimensions.</b> The catalog (<code>_APLUS_MODULES</code>) holds each Basic and Premium module with its precise size (e.g. image+text 970×600, four-quadrant 220×220), so the output fits Amazon's A+ builder.`,
      `<b>Drafts the copy separately.</b> It writes the module text (≈70% visual / 30% text) and blocks prohibited claims — the text is drafted by the prompt AI for reliability, not baked into the image.`,
      `<b>Keeps your product faithful.</b> Your product image is always attached as the reference.`,
      `<b>Honest gating:</b> A+ requires <b>Amazon Brand Registry</b>; <b>Premium A+</b> additionally needs a Brand Story on all ASINs + 15 approved submissions in the last 12 months. The app builds the assets — <b>you upload them in Seller Central's A+ builder</b>.` ]}
  };
}
function howWorks(which){
  if(!window.LOGIC_VISIBLE) return "";
  const reg = LOGIC_REGISTRY();
  const b = reg[which]; if(!b) return "";
  return `<details class="howbox"><summary><span class="chev">▶</span> How this works — the actual steps behind the button</summary>
    <div class="howbody"><div style="font-weight:600;color:var(--text);margin-bottom:2px">${esc(b.title)}</div>
      <ol>${b.steps.map(s=>`<li>${s}</li>`).join("")}</ol>
      <div style="margin-top:6px;opacity:.8">Models shown reflect your current dropdown selections. Nothing is sent to Amazon — generated images only go to this product's media library for review.</div>
    </div></details>`;
}
// Inject disclosures that live in STATIC page HTML (not JS template literals).
// Called on boot and whenever the admin toggles logic visibility.
function refreshStaticHowPanels(){
  const map = {
    "genhow":  ['gen_pipeline','gen_compliance','gen_ip','submit_live'],
    "gridhow": ['grid_load','grid_enrich','grid_sync','cogs']
  };
  Object.keys(map).forEach(function(id){
    const el=document.getElementById(id);
    if(el){ el.innerHTML = (typeof howWorks==="function") ? map[id].map(function(k){return howWorks(k);}).join("") : ""; }
  });
}

function _studioAddResult(job, j, grid){
  grid=grid||document.getElementById("studio_results");
  const cardId="sres_"+Math.random().toString(36).slice(2);
  const label=esc(job.sku)+(job.strategy?(' · '+job.strategy.replace('_',' ')):'');
  let inner;
  if(j&&j.ok&&j.data_url){
    // stash the originating kind+payload so we can regenerate JUST this one
    STUDIO._reroll=STUDIO._reroll||{};
    if(j._kind&&j._payload){ STUDIO._reroll[cardId]={kind:j._kind, payload:j._payload, label:(job.strategy||job.sku)}; }
    const canReroll = !!(j._kind&&j._payload);
    const _driveLine = j.drive_direct_url
      ? `<div class="cc" style="color:#86d0a8;font-size:10.5px;padding:0 8px 4px">\u2713 saved to Drive</div>`
      : (j.drive_error
          ? `<div class="cc" style="color:#e3b768;font-size:10.5px;padding:0 8px 4px">Drive: ${esc(j.drive_error)}</div>`
          : (j.save_error
              ? `<div class="cc" style="color:#e0696b;font-size:10.5px;padding:0 8px 4px">Save: ${esc(j.save_error)}</div>`
              : ""));
    inner=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
      <div class="srescap">${label}</div>
      ${_driveLine}
      <div class="sresacts">
        <button class="ib" onclick="studioSave('${cardId}','${esc(job.sku)}')"><i class="ti ti-device-floppy"></i> Save to media</button>
        <button class="ib" onclick="studioDownload('${cardId}','${esc(job.sku)}')"><i class="ti ti-download"></i></button>
        <button class="ib" onclick="studioToDrive('${cardId}','${esc(job.sku)}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
        ${canReroll?`<button class="ib" onclick="studioReroll('${cardId}')" title="Generate this one again (e.g. if a detail came out wrong)"><i class="ti ti-refresh"></i> Redo this</button>`:''}
        ${canReroll?`<button class="ib" onclick="studioRefine('${cardId}')" title="Tell the AI a small change to make to THIS image"><i class="ti ti-wand"></i> Refine…</button>`:''}
      </div>`;
    STUDIO.results[cardId]={data_url:j.data_url, sku:job.sku};
  } else {
    inner=`<div class="sresfail">✗ ${esc((j&&j.error)||'failed')}</div><div class="srescap">${label}</div>`;
  }
  const div=document.createElement("div");
  div.className="srescard"; div.id=cardId; div.innerHTML=inner;
  grid.appendChild(div);
}
async function studioReroll(cardId){
  const r=(STUDIO._reroll||{})[cardId]; if(!r){ toast("Can't redo this one."); return; }
  const card=document.getElementById(cardId);
  if(card){ card.innerHTML='<div class="srescap"><span class="genspin"></span> regenerating…</div>'; }
  const ep = r.kind==="concept" ? "/genimage/from_concept"
           : r.kind==="source" ? "/genimage/process_source"
           : r.kind==="secondary" ? "/genimage/secondary_v2"
           : r.kind==="aplus" ? "/genimage/generate"
           : "/genimage/recipe";
  try{
    const j=await (await fetch(ep,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(r.payload)})).json();
    if(j&&j.ok&&j.data_url){
      // auto-save the redo too
      try{ await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:r.payload.sku||r.payload.title||"", data_url:j.data_url})}); }catch(e){}
      if(card){
        STUDIO.results[cardId]={data_url:j.data_url, sku:(r.payload.title||"")};
        card.innerHTML=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
          <div class="srescap">${esc(r.label)} · redone</div>
          <div class="sresacts">
            <button class="ib" onclick="studioSave('${cardId}','')"><i class="ti ti-device-floppy"></i> Save to media</button>
            <button class="ib" onclick="studioDownload('${cardId}','')"><i class="ti ti-download"></i></button>
            <button class="ib" onclick="studioToDrive('${cardId}','')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
            <button class="ib" onclick="studioReroll('${cardId}')"><i class="ti ti-refresh"></i> Redo this</button>
          </div>`;
      }
    } else {
      if(card){ card.innerHTML='<div class="sresfail">✗ '+esc((j&&j.error)||'failed')+'</div>'; }
    }
  }catch(e){ if(card){ card.innerHTML='<div class="sresfail">✗ '+esc(String(e))+'</div>'; } }
}
async function studioRefine(cardId){
  const cur=(STUDIO.results||{})[cardId];
  const r=(STUDIO._reroll||{})[cardId];
  if(!cur||!cur.data_url){ toast("Nothing to refine here."); return; }
  const instruction=prompt("What small change should I make to this image?\n(e.g. \"make the background warmer\", \"remove the water droplets\", \"move the product slightly left\", \"make the text bigger\")");
  if(!instruction||!instruction.trim()) return;
  // figure out the kind from the original payload (main / secondary / aplus)
  let kind="main";
  if(r&&r.kind){ kind = (r.kind==="concept")?"main":(r.kind==="aplus"?"aplus":(r.kind==="secondary"?"secondary":"main")); }
  const card=document.getElementById(cardId);
  if(card){ card.innerHTML='<div class="srescap"><span class="genspin"></span> refining…</div>'; }
  // attach the ORIGINAL product reference so the edit can't drift the real product
  let origRef="";
  try{
    const sku=cur.sku||"";
    const it=_itemForSku(sku) || (STUDIO.items&&STUDIO.items[0]);
    origRef=_refImgForItem(it)||"";
  }catch(e){}
  const payload={
    image:cur.data_url, original_reference:origRef, instruction:instruction.trim(), kind:kind,
    title:(cur.sku||""), text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)
  };
  try{
    const j=await (await fetch("/genimage/refine",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload)})).json();
    if(j&&j.ok&&j.data_url){
      try{ await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:cur.sku||"", data_url:j.data_url})}); }catch(e){}
      STUDIO.results[cardId]={data_url:j.data_url, sku:cur.sku};
      // keep refine available so you can iterate (refine the refined image)
      if(j._kind&&j._payload){ STUDIO._reroll[cardId]={kind:j._kind, payload:j._payload, label:(STUDIO._reroll[cardId]?STUDIO._reroll[cardId].label:cur.sku)}; }
      if(card){
        card.innerHTML=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
          <div class="srescap">refined: ${esc(instruction.trim()).slice(0,40)}</div>
          <div class="sresacts">
            <button class="ib" onclick="studioSave('${cardId}','${esc(cur.sku||'')}')"><i class="ti ti-device-floppy"></i> Save to media</button>
            <button class="ib" onclick="studioDownload('${cardId}','${esc(cur.sku||'')}')"><i class="ti ti-download"></i></button>
            <button class="ib" onclick="studioToDrive('${cardId}','${esc(cur.sku||'')}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
            <button class="ib" onclick="studioRefine('${cardId}')" title="Make another small change"><i class="ti ti-wand"></i> Refine…</button>
          </div>`;
      }
    } else {
      if(card){ card.innerHTML='<div class="sresfail">✗ '+esc((j&&j.error)||'failed')+'</div>'; }
      toast("Refine failed: "+((j&&j.error)||""));
    }
  }catch(e){ if(card){ card.innerHTML='<div class="sresfail">✗ '+esc(String(e))+'</div>'; } }
}
async function studioSave(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  try{
    const j=await (await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, data_url:r.data_url})})).json();
    if(j.ok){ r.savedUrl=j.url; toast("Saved to "+sku+" media library"); }
    else toast("Save failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
async function studioToDrive(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  // confirm a Drive folder is configured for this account
  let ds=null; try{ ds=await (await fetch("/drive/status")).json(); }catch(e){}
  if(!ds||!ds.ok||!ds.configured){
    toast("No Drive folder set for this account — add one in Account & sheets");
    return;
  }
  // ensure it's saved locally first (Drive upload reads the local file)
  if(!r.savedUrl){
    try{
      const sj=await (await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, data_url:r.data_url})})).json();
      if(sj.ok) r.savedUrl=sj.url; else { toast("Save failed: "+(sj.error||"")); return; }
    }catch(e){ toast("Error: "+e); return; }
  }
  const it=_itemForSku(sku);
  const pname=(it&&it.title)||(r.sku||"");
  toast("Uploading to Drive…");
  try{
    const j=await (await fetch("/drive/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, product_name:pname, relpath:r.savedUrl})})).json();
    if(j.ok) toast("Uploaded to Drive ✓");
    else toast("Drive upload failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
function _extFromDataUrl(durl){
  // Determine the TRUE image extension from the bytes, not the mime label (which
  // can be wrong -- e.g. JPEG bytes tagged image/png, which Amazon then rejects).
  try{
    if(!durl) return "jpg";
    if(/^https?:/i.test(durl)){
      const m=durl.split("?")[0].match(/\.(png|jpe?g|webp|gif)$/i);
      return m ? (m[1].toLowerCase()==="jpeg"?"jpg":m[1].toLowerCase()) : "jpg";
    }
    const comma=durl.indexOf(","); if(comma<0) return "jpg";
    const bin=atob(durl.slice(comma+1, comma+24));  // first few bytes are enough
    const b=[]; for(let i=0;i<bin.length;i++) b.push(bin.charCodeAt(i)&0xff);
    if(b[0]===0xff&&b[1]===0xd8&&b[2]===0xff) return "jpg";
    if(b[0]===0x89&&b[1]===0x50&&b[2]===0x4e&&b[3]===0x47) return "png";
    if(b[0]===0x52&&b[1]===0x49&&b[2]===0x46&&b[3]===0x46&&b[8]===0x57&&b[9]===0x45) return "webp";
    if(b[0]===0x47&&b[1]===0x49&&b[2]===0x46) return "gif";
  }catch(e){}
  return "jpg";
}
function studioDownload(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  // Prefer the full-resolution image URL if we have it; fall back to the inline
  // data. Convert to JPEG on download (Amazon-preferred, smaller files).
  const src = r.url || r.data_url;
  _downloadAsJpeg(src, (sku||"image"));
}
function _downloadAsJpeg(src, baseName){
  // Draw the image to a canvas and export JPEG, so downloads are always .jpg
  // regardless of the source format. Transparency is flattened onto white.
  try{
    const img=new Image();
    img.crossOrigin="anonymous";
    img.onload=function(){
      try{
        const c=document.createElement("canvas");
        c.width=img.naturalWidth||img.width; c.height=img.naturalHeight||img.height;
        const ctx=c.getContext("2d");
        ctx.fillStyle="#ffffff"; ctx.fillRect(0,0,c.width,c.height);
        ctx.drawImage(img,0,0);
        const jpeg=c.toDataURL("image/jpeg",0.9);
        const a=document.createElement("a"); a.href=jpeg; a.download=baseName+".jpg"; a.click();
      }catch(e){
        // tainted canvas (cross-origin) -> fall back to direct download of source
        const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click();
      }
    };
    img.onerror=function(){ const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click(); };
    img.src=src;
  }catch(e){
    const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click();
  }
}
async function loadSchemas(pts, force, mkt){
  const mp = (mkt||"").toString().toUpperCase();
  const q = (force?"?refresh=1":"") + (mp?((force?"&":"?")+"mkt="+encodeURIComponent(mp)):"");
  await Promise.all(pts.map(async pt=>{
    if(SCHEMAS[pt] && (SCHEMAS[pt].attrs||[]).length && !force)return;  // only skip if genuinely loaded
    try{const r=await fetch("/schema/"+encodeURIComponent(pt)+q);const j=await r.json();
        SCHEMAS[pt]=j.ok?{opts:(j.enums||{}),req:(j.required||[]),attrs:(j.attrs||[]),subs:(j.subfields||{}),titles:(j.titles||{}),_mkt:(j.marketplace||mp)}:{opts:{},req:[],attrs:[],subs:{},titles:{}};}catch(e){SCHEMAS[pt]={opts:{},req:[],attrs:[],subs:{},titles:{}};}
  }));
}
async function refreshSchemaFor(sku){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r)return;
  const pt=r.product_type; if(!pt){toast("No product type on this row");return;}
  delete SCHEMAS[pt];
  toast("Refreshing Amazon allowed values…");
  await loadSchemas([pt], true, rowMkt(r));
  if(DRAWER_SKU===sku){ openDrawer(sku); }
  else render();
  toast("Amazon values refreshed — dropdowns updated");
}

async function setStatus(sku,status,btn){
  if(!sku){toast("This row has no SKU yet");return;}
  btn.disabled=true; const old=btn.textContent; btn.textContent="…";
  try{
    const res=await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku,status})});
    const j=await res.json();
    if(j.ok){const r=ROWS.find(x=>x.sku===sku); if(r)r.status=status; render(); toast(status==="APPROVED"?"Approved":"Set to needs-review");}
    else {toast("Failed: "+j.error); btn.disabled=false; btn.textContent=old;}
  }catch(e){toast("Failed: "+e); btn.disabled=false; btn.textContent=old;}
}

function setFilter(el){
  document.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));
  el.classList.add("active"); FILTER=el.dataset.f; render();
}
function setFilterVal(v){
  FILTER=v||"all";
  // leaving brand settings panel if open
  var bp=document.getElementById('brandpanel'); if(bp&&bp.style.display!=='none'){ bp.style.display='none'; var g=document.getElementById('grid'); if(g) g.style.display=''; var sm=document.getElementById('summary'); if(sm) sm.style.display=''; }
  render();
}

let ES=null;
function showStop(on){ const b=document.getElementById("stopbtn"); if(b) b.disabled=!on; }
async function stopRun(){
  const b=document.getElementById("stopbtn"); if(b) b.disabled=true;
  try{ const r=await fetch("/stop",{method:"POST"}); const j=await r.json();
       toast(j.ok?"Stopping the run\u2026":("Stop: "+(j.error||"nothing running"))); }
  catch(e){ toast("Stop failed"); if(b) b.disabled=false; }
}
function genSelOnInput(){
  const v=(document.getElementById("gensel_value").value||"").toLowerCase();
  const dd=document.getElementById("gensel_type");
  const hint=document.getElementById("gensel_hint");
  const isUrl = v.includes("http://")||v.includes("https://")||v.includes("amazon.")||v.includes("ebay.");
  if(dd){ dd.disabled=isUrl; dd.style.opacity=isUrl?.45:1; }
  if(hint){ hint.textContent = isUrl
    ? "URL detected — the platform is read from the link, so the dropdown is ignored."
    : "Row numbers can be comma-separated (e.g. 2, 5, 7). For one product you can paste its URL — the dropdown is ignored then."; }
}
// ---- Miles Lubricants import ----
let MILES_ITEMS=[];
function milesPickFile(input){
  const f=input.files&&input.files[0];
  if(!f) return;
  const status=document.getElementById("miles_filestatus");
  status.textContent="Reading "+f.name+"…";
  const name=f.name.toLowerCase();
  if(name.endsWith(".csv")){
    const reader=new FileReader();
    reader.onload=e=>milesParseCSV(e.target.result, f.name);
    reader.readAsText(f);
  } else {
    // XLSX: parse with SheetJS if available, else ask for CSV
    if(typeof XLSX==="undefined"){
      status.textContent="Excel parsing needs CSV here — please save as CSV and re-upload.";
      return;
    }
    const reader=new FileReader();
    reader.onload=e=>{
      try{
        const wb=XLSX.read(new Uint8Array(e.target.result),{type:"array"});
        const ws=wb.Sheets[wb.SheetNames[0]];
        const rows=XLSX.utils.sheet_to_json(ws,{header:1});
        milesParseRows(rows, f.name);
      }catch(err){ status.textContent="Could not read Excel: "+err; }
    };
    reader.readAsArrayBuffer(f);
  }
}
function milesParseCSV(text, fname){
  const rows=text.split(/\r?\n/).map(l=>l.split(","));
  milesParseRows(rows, fname);
}
function milesParseRows(rows, fname){
  // find the item-number column: header match, else column 0
  const nameKeys=["item number","item_number","item","sku","product number","product_number","number"];
  let col=0, start=0;
  if(rows.length){
    const hdr=rows[0].map(c=>String(c||"").trim().toLowerCase());
    const idx=hdr.findIndex(h=>nameKeys.includes(h));
    if(idx>=0){ col=idx; start=1; }
    else if(!/^[a-z]{1,4}\d{4,}$|^\d{6,}$/i.test(hdr[0]||"")){ start=1; } // looks like header, skip
  }
  const seen=new Set(); const items=[];
  for(let i=start;i<rows.length;i++){
    const v=String((rows[i]||[])[col]||"").trim();
    if(!v || nameKeys.includes(v.toLowerCase())) continue;
    if(!seen.has(v)){ seen.add(v); items.push(v); }
  }
  MILES_ITEMS=items;
  document.getElementById("miles_filestatus").textContent=fname+" — "+items.length+" item number(s)";
  document.getElementById("miles_items").textContent = items.length? ("Items: "+items.slice(0,30).join(", ")+(items.length>30?" …":"")) : "No item numbers found in the file.";
  // upload to server
  fetch("/miles/upload",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({items})}).then(r=>r.json()).then(j=>{
      const btn=document.getElementById("miles_runbtn");
      if(btn) btn.disabled = !(j.ok && j.count>0);
    }).catch(()=>{});
}
function milesRun(){
  if(ES){toast("A run is already streaming");return;}
  if(!MILES_ITEMS.length){toast("Upload an item-number file first");return;}
  const log=document.getElementById("miles_log");
  if(log){ log.style.display="block"; log.textContent=""; }
  const skipDone = document.getElementById("miles_skip_done");
  const url = "/miles/run" + (skipDone && skipDone.checked ? "?skip_done=1" : "?skip_done=0");
  ES=new EventSource(url);
  const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=true;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=false;
  ES.onmessage=e=>{
    if(!log) return;
    const div=document.createElement("div");
    if(e.data.startsWith("[error]")) div.style.color="#ff8585";
    else if(e.data.startsWith("[done]")) div.style.color="#7ee08a";
    else if(e.data.startsWith("[start]")) div.style.color="#9cc1ff";
    else if(e.data.indexOf("NOT_FOUND")>=0||e.data.indexOf("NEEDS_REVIEW")>=0) div.style.color="#e3b768";
    div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;
    const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    milesLoadResults(); toast("Harvest + generation finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;
    const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    if(log){const d=document.createElement("div");d.style.color="#ff8585";d.textContent="[error] stream interrupted — check the app terminal for a Python traceback";log.appendChild(d);}
  }};
}
function milesSavePref(){
  // Persist the output Sheet ID/tab so it survives reloads until changed.
  const sheet=(document.getElementById("miles_sheet")||{}).value||"";
  const tab=(document.getElementById("miles_tab")||{}).value||"";
  fetch("/miles/sheet_pref",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({sheet:sheet.trim(),tab:tab.trim()})}).catch(()=>{});
}
function milesLoadPref(){
  // Pre-fill the saved Sheet ID/tab on open. Only fills empty fields so we never
  // clobber something the user just typed.
  fetch("/miles/sheet_pref").then(r=>r.json()).then(d=>{
    if(!d) return;
    const s=document.getElementById("miles_sheet");
    const t=document.getElementById("miles_tab");
    if(s && !s.value && d.sheet) s.value=d.sheet;
    if(t && !t.value && d.tab)   t.value=d.tab;
  }).catch(()=>{});
}
function milesGenerate(){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("miles_log");
  if(log){ log.style.display="block"; log.textContent=""; }
  const sheet=(document.getElementById("miles_sheet")||{}).value||"";
  const tab=(document.getElementById("miles_tab")||{}).value||"";
  const lim=(document.getElementById("miles_limit")||{}).value||"";
  // Post params first, then open the SSE stream
  const params=new URLSearchParams();
  if(sheet.trim()) params.set("sheet", sheet.trim());
  if(tab.trim())   params.set("tab",   tab.trim());
  if(lim.trim() && parseInt(lim)>0) params.set("limit", parseInt(lim).toString());
  const useBA=(document.getElementById("miles_use_ba")||{}).checked;
  if(useBA) params.set("use_ba","1");
  // Store in sessionStorage so the SSE GET route can read them back
  sessionStorage.setItem("mg_sheet", sheet.trim());
  sessionStorage.setItem("mg_tab",   tab.trim());
  sessionStorage.setItem("mg_limit", (lim.trim() && parseInt(lim)>0) ? parseInt(lim).toString() : "");
  const qs=params.toString();
  ES=new EventSource("/miles/generate"+(qs?"?"+qs:""));
  const gb=document.getElementById("miles_genbtn"); if(gb) gb.disabled=true;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=false;
  ES.onmessage=e=>{
    if(!log) return;
    const div=document.createElement("div");
    if(e.data.startsWith("[error]")) div.style.color="#ff8585";
    else if(e.data.startsWith("[done]")) div.style.color="#7ee08a";
    else if(e.data.startsWith("[start]")) div.style.color="#9cc1ff";
    div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;
    const gb=document.getElementById("miles_genbtn"); if(gb) gb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    loadRows(); toast("Draft generation finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;
    const gb=document.getElementById("miles_genbtn"); if(gb) gb.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;}};
}
function milesOptimize(){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("miles_log");
  if(log){ log.style.display="block"; log.textContent=""; }
  const sheet=(document.getElementById("miles_sheet")||{}).value||"";
  const tab=(document.getElementById("miles_tab")||{}).value||"";
  const params=new URLSearchParams();
  if(sheet.trim()) params.set("sheet", sheet.trim());
  if(tab.trim())   params.set("tab",   tab.trim());
  const qs=params.toString();
  ES=new EventSource("/miles/optimize"+(qs?"?"+qs:""));
  const ob=document.getElementById("miles_optbtn"); if(ob) ob.disabled=true;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=false;
  ES.onmessage=e=>{
    if(!log) return;
    const div=document.createElement("div");
    if(e.data.startsWith("[error]")) div.style.color="#ff8585";
    else if(e.data.startsWith("[done]")) div.style.color="#7ee08a";
    else if(e.data.startsWith("[start]")) div.style.color="#9cc1ff";
    div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;
    const ob=document.getElementById("miles_optbtn"); if(ob) ob.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
    loadRows(); toast("SQP optimization finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;
    const ob=document.getElementById("miles_optbtn"); if(ob) ob.disabled=false;
    const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;}};
}
function milesStop(){
  // The Miles harvest is an SSE stream, not a subprocess. Cancel it server-side
  // (so the in-flight loop stops between items) and close the stream client-side.
  fetch("/miles/stop",{method:"POST"}).catch(()=>{});
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  const log=document.getElementById("miles_log");
  if(log){ const d=document.createElement("div"); d.style.color="#e3b768"; d.textContent="[stopped] harvest cancelled by user"; log.appendChild(d); log.scrollTop=log.scrollHeight; }
  const rb=document.getElementById("miles_runbtn"); if(rb) rb.disabled=false;
  const sb=document.getElementById("miles_stopbtn"); if(sb) sb.disabled=true;
  toast("Harvest stopped");
}
function milesClearHistory(){
  fetch("/miles/clear_history",{method:"POST"}).then(r=>r.json()).then(j=>{
    toast(j.ok ? ("Cleared "+(j.cleared||0)+" harvested item(s)") : "Could not clear history");
  }).catch(()=>toast("Could not clear history"));
}
function milesLoadResults(){
  fetch("/miles/results").then(r=>r.json()).then(j=>{
    const box=document.getElementById("miles_results");
    if(!box) return;
    if(!j.ok){ box.innerHTML=""; return; }
    const s=j.summary;
    let h='<div style="padding:12px;border:1px solid var(--line);border-radius:10px">';
    h+='<div style="font-weight:600;margin-bottom:8px">Harvest results</div>';
    h+='<div style="font-size:13px;margin-bottom:6px">✓ '+s.ok+' harvested · ⚠ '+s.needs_review.length+' need review · ✗ '+s.not_found.length+' not found · '+s.errors.length+' errors</div>';
    if(s.products.length){
      h+='<table style="width:100%;font-size:12px;border-collapse:collapse;margin-top:8px">';
      h+='<tr style="text-align:left;opacity:.7"><th style="padding:4px">Item</th><th style="padding:4px">Title</th><th style="padding:4px">PDFs</th><th style="padding:4px">SDS</th></tr>';
      s.products.forEach(p=>{ h+='<tr><td style="padding:4px">'+esc(p.item_number||"")+'</td><td style="padding:4px">'+esc((p.title||"").slice(0,50))+'</td><td style="padding:4px">'+p.pdf_count+'</td><td style="padding:4px">'+(p.has_sds?"✓":"—")+'</td></tr>'; });
      h+='</table>';
    }
    if(s.needs_review.length){
      h+='<div style="margin-top:10px;font-size:12px;color:#e3b768"><b>Manual review (multiple matches):</b> '+s.needs_review.map(x=>esc(x.item)).join(", ")+'</div>';
    }
    if(s.not_found.length){
      h+='<div style="margin-top:6px;font-size:12px;opacity:.7"><b>Not found:</b> '+s.not_found.map(x=>esc(x.item)).join(", ")+'</div>';
    }
    h+='</div>';
    box.innerHTML=h;
  }).catch(()=>{});
}

// ---------- PPC section ----------
function ppcOnOpen(){
  // set the context banner so the agent knows this is scoped per-workspace
  const el=document.getElementById("ppc_ctx");
  if(el){
    const acct=(CUR_ACCOUNT&&CUR_ACCOUNT.label)||"this workspace";
    const mkt=WS_MARKET||"UK";
    el.textContent=acct+" · "+mkt;
  }
}
function ppcAppendChat(who, text){
  const box=document.getElementById("ppc_chatlog"); if(!box) return;
  const div=document.createElement("div");
  div.style.margin="10px 0";
  div.style.fontSize="13px";
  div.style.lineHeight="1.5";
  const who_style = (who==="you") ? "color:#9cc1ff;font-weight:600" : "color:#7fdca0;font-weight:600";
  div.innerHTML='<div style="'+who_style+';font-size:11px;text-transform:uppercase;letter-spacing:.5px">'+esc(who)+'</div><div style="white-space:pre-wrap">'+esc(text)+'</div>';
  box.appendChild(div);
  box.scrollTop=box.scrollHeight;
}
async function ppcAgentSend(){
  const inp=document.getElementById("ppc_input"); if(!inp) return;
  const msg=(inp.value||"").trim(); if(!msg) return;
  inp.value=""; ppcAppendChat("you", msg);
  // spinner
  const box=document.getElementById("ppc_chatlog");
  const sp=document.createElement("div"); sp.className="cc"; sp.innerHTML='<span class="genspin"></span> thinking…';
  sp.style.margin="6px 0";
  box.appendChild(sp); box.scrollTop=box.scrollHeight;
  try{
    const acct=(CUR_ACCOUNT&&CUR_ACCOUNT.id)||"";
    const mkt=WS_MARKET||"UK";
    const j=await (await fetch("/ppc/agent",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({message:msg, account_id:acct, marketplace:mkt})})).json();
    sp.remove();
    if(!j.ok){ ppcAppendChat("agent", "Error: "+(j.error||"unknown")); return; }
    ppcAppendChat("agent", j.reply||"(empty response)");
    if(j.routed_skill){
      ppcAppendChat("agent", "Routed to skill: "+j.routed_skill+". "+(j.next_action||""));
    }
  }catch(e){
    sp.remove();
    ppcAppendChat("agent", "Request failed: "+String(e));
  }
}
function ppcOpenBuilder(){
  const m=document.getElementById("ppc_builder_modal");
  if(m){ m.classList.add("open"); }
}
function ppcCloseBuilder(){
  const m=document.getElementById("ppc_builder_modal");
  if(m){ m.classList.remove("open"); }
  const r=document.getElementById("pb_result"); if(r) r.innerHTML="";
}
async function ppcRunBuilder(){
  const asin=(document.getElementById("pb_asin").value||"").trim();
  const sku=(document.getElementById("pb_sku").value||"").trim();
  const name=(document.getElementById("pb_name").value||"").trim();
  const budget=parseFloat(document.getElementById("pb_budget").value||"8.0");
  const bid=parseFloat(document.getElementById("pb_bid").value||"0.30");
  const conquest=(document.getElementById("pb_conquest").value||"").split(",").map(s=>s.trim()).filter(Boolean);
  const compbrands=(document.getElementById("pb_compbrands").value||"").split(",").map(s=>s.trim()).filter(Boolean);
  const headterms=(document.getElementById("pb_headterms").value||"").split(",").map(s=>s.trim()).filter(Boolean);
  const fileEl=document.getElementById("pb_file");
  const resBox=document.getElementById("pb_result");
  if(!asin||!sku||!name){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">ASIN, SKU, and product short name are all required.</div>'; return; }
  if(asin===sku){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">SKU cannot equal ASIN. Use the seller SKU from Seller Central.</div>'; return; }
  if(!fileEl.files||!fileEl.files[0]){ resBox.innerHTML='<div style="color:#e3b768;font-size:12px;padding:8px;border:1px solid #4d3712;border-radius:6px;background:#241a10">Attach a keyword file (CSV from DataDive, Helium 10, or SQP).</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Bucketing keywords + building bulk file…</div>';
  const fd=new FormData();
  fd.append("file", fileEl.files[0]);
  fd.append("asin", asin);
  fd.append("sku", sku);
  fd.append("product_short_name", name);
  fd.append("daily_budget", String(budget));
  fd.append("default_bid", String(bid));
  fd.append("conquest_asins", JSON.stringify(conquest));
  fd.append("competitor_brands", JSON.stringify(compbrands));
  fd.append("category_heads", JSON.stringify(headterms));
  fd.append("marketplace", WS_MARKET||"UK");
  try{
    const j=await (await fetch("/ppc/build_campaigns",{method:"POST", body:fd})).json();
    if(!j.ok){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"build failed")+'</div>'; return; }
    const v=j.validation||{};
    let html='<div style="padding:10px;border:1px solid var(--line);border-radius:8px">';
    html+='<div style="font-weight:600;margin-bottom:6px;color:'+(v.ok?'#7fdca0':'#e3b768')+'">'+(v.ok?'✓ Built + validated':'⚠ Built but validation flagged issues')+'</div>';
    html+='<div style="font-size:12px;line-height:1.6">';
    html+='Rows: <b>'+(j.row_count||0)+'</b> · Unique keywords: <b>'+(j.unique_keywords||0)+'</b> · Campaigns: <b>'+(j.campaign_count||0)+'</b><br>';
    html+='Buckets: core '+(j.bucket_counts.core||0)+' · head '+(j.bucket_counts['category-head']||0)+' · comp '+(j.bucket_counts.competitor||0)+' · drop '+(j.bucket_counts.drop||0);
    html+='</div>';
    if(v.errors&&v.errors.length){
      html+='<div style="margin-top:8px;font-size:12px;color:#e0696b"><b>Errors (must fix before upload):</b><br>'+v.errors.map(esc).join("<br>")+'</div>';
    }
    if(v.warnings&&v.warnings.length){
      html+='<div style="margin-top:8px;font-size:12px;color:#e3b768"><b>Warnings:</b><br>'+v.warnings.map(esc).join("<br>")+'</div>';
    }
    html+='<div style="margin-top:10px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Download bulk CSV</a></div>';
    html+='</div>';
    resBox.innerHTML=html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

function ppcOpenHarvest(){
  const m=document.getElementById("ppc_harvest_modal");
  if(m){ m.classList.add("open"); }
}
function ppcCloseHarvest(){
  const m=document.getElementById("ppc_harvest_modal");
  if(m){ m.classList.remove("open"); }
  const r=document.getElementById("ph_result"); if(r) r.innerHTML="";
}
async function ppcRunHarvest(){
  const asin=(document.getElementById("ph_asin").value||"").trim();
  const sku=(document.getElementById("ph_sku").value||"").trim();
  const name=(document.getElementById("ph_name").value||"").trim();
  const be=parseFloat(document.getElementById("ph_be").value||"0.35");
  const bid=parseFloat(document.getElementById("ph_bid").value||"0.30");
  const budget=parseFloat(document.getElementById("ph_budget").value||"8.0");
  const fileEl=document.getElementById("ph_file");
  const tgtEl=document.getElementById("ph_targeted");
  const resBox=document.getElementById("ph_result");
  if(!asin||!sku||!name){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">ASIN, SKU, and product short name are all required.</div>'; return; }
  if(asin===sku){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">SKU cannot equal ASIN.</div>'; return; }
  if(!fileEl.files||!fileEl.files[0]){ resBox.innerHTML='<div style="color:#e3b768;font-size:12px;padding:8px;border:1px solid #4d3712;border-radius:6px;background:#241a10">Upload the SP Search Term Report CSV.</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Classifying every term, applying $10 rule + break-even ACOS…</div>';
  const fd=new FormData();
  fd.append("file", fileEl.files[0]);
  fd.append("asin", asin);
  fd.append("sku", sku);
  fd.append("product_short_name", name);
  fd.append("break_even_acos", String(be));
  fd.append("default_bid", String(bid));
  fd.append("daily_budget", String(budget));
  fd.append("marketplace", WS_MARKET||"UK");
  if(tgtEl&&tgtEl.files&&tgtEl.files[0]) fd.append("targeted_file", tgtEl.files[0]);
  try{
    const j=await (await fetch("/ppc/harvest",{method:"POST", body:fd})).json();
    if(!j.ok){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"harvest failed")+'</div>'; return; }
    const t=j.totals||{}, c=j.counts||{};
    let html='<div style="padding:10px;border:1px solid var(--line);border-radius:8px">';
    html+='<div style="font-weight:600;margin-bottom:6px;color:#7fdca0">✓ Harvest complete</div>';
    html+='<div style="font-size:12px;line-height:1.7">';
    html+='Terms: <b>'+(t.total_terms||0)+'</b> · Total spend: <b>'+(t.total_spend||0)+'</b> · Total sales: <b>'+(t.total_sales||0)+'</b> · Orders: <b>'+(t.total_orders||0)+'</b><br>';
    html+='Ready for harvest: <b style="color:#7fdca0">'+(t.harvest_ready||0)+'</b> new converting terms (excluded '+j.excluded_already_targeted+' already-targeted)<br>';
    html+='Ready for negation: <b style="color:#e0696b">'+(t.negatives_ready||0)+'</b> past-$10 zero-order terms';
    html+='</div>';
    html+='<div style="margin:10px 0;display:flex;flex-wrap:wrap;gap:6px;font-size:12px">';
    Object.keys(c).forEach(k=>{
      const col = k==='CONVERTING'?'#7fdca0': (k==='OVER-$10-CUT'||k==='CLICKS-NO-SALE')?'#e0696b': (k==='CONVERTS-BUT-HIGH-ACOS'||k==='HIGH-SPEND-WATCH')?'#e3b768':'#9cc1ff';
      html+='<span style="padding:3px 8px;border-radius:4px;background:'+col+'22;color:'+col+';border:1px solid '+col+'55">'+esc(k)+': '+c[k]+'</span>';
    });
    html+='</div>';
    html+='<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">';
    if(j.downloads.status_xlsx){
      html+='<a href="'+j.downloads.status_xlsx+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Status (coloured xlsx)</a>';
    }
    html+='<a href="'+j.downloads.status+'" class="mktbtn" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Status (CSV)</a>';
    html+='<a href="'+j.downloads.harvest+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Harvest bulk</a>';
    html+='<a href="'+j.downloads.negatives+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ Negatives bulk</a>';
    html+='</div>';
    html+='</div>';
    resBox.innerHTML=html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// Deliverable modal shared by audit / dashboard / forecast / weekly-deck
let PPC_DELIV_SKILL="";
function ppcOpenDeliverable(skill, title, desc){
  PPC_DELIV_SKILL = skill;
  document.getElementById("pd_title").innerHTML='<i class="ti ti-file"></i> '+esc(title);
  document.getElementById("pd_desc").textContent = desc;
  const m=document.getElementById("ppc_deliv_modal");
  if(m){ m.classList.add("open"); }
  const r=document.getElementById("pd_result"); if(r) r.innerHTML="";
}
function ppcCloseDeliv(){
  const m=document.getElementById("ppc_deliv_modal");
  if(m){ m.classList.remove("open"); }
  const r=document.getElementById("pd_result"); if(r) r.innerHTML="";
  PPC_DELIV_SKILL="";
}
async function ppcRunDeliv(){
  const filesEl=document.getElementById("pd_files");
  const ctxEl=document.getElementById("pd_context");
  const resBox=document.getElementById("pd_result");
  const skill = PPC_DELIV_SKILL;
  if(!skill){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">No capability selected — try again from a shortcut.</div>'; return; }
  const files = filesEl && filesEl.files ? Array.from(filesEl.files) : [];
  if(!files.length){ resBox.innerHTML='<div style="color:#e3b768;font-size:12px;padding:8px;border:1px solid #4d3712;border-radius:6px;background:#241a10">Attach at least one file so I can detect its family and act on real data.</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Detecting file families + building deliverable…</div>';
  const fd=new FormData();
  fd.append("skill", skill);
  fd.append("context", (ctxEl && ctxEl.value)||"");
  fd.append("account_id", (CUR_ACCOUNT&&CUR_ACCOUNT.id)||"");
  fd.append("marketplace", WS_MARKET||"UK");
  files.forEach((f,i)=>fd.append("files", f, f.name));
  try{
    const j=await (await fetch("/ppc/deliverable",{method:"POST", body:fd})).json();
    if(!j.ok){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"failed")+'</div>'; return; }
    let html='<div style="padding:10px;border:1px solid var(--line);border-radius:8px">';
    // Files detected
    html+='<div style="font-weight:600;margin-bottom:6px;color:#9cc1ff">Files detected</div>';
    html+='<ul style="font-size:12px;margin:0 0 8px 18px;line-height:1.6">';
    (j.file_summary||[]).forEach(f=>{
      const tag = f.family ? '<span style="color:#7fdca0">'+esc(f.family)+'</span>' : '<span style="color:#e3b768">unknown</span>';
      html+='<li>'+esc(f.filename)+' → '+tag+' ('+f.row_count+' rows)</li>';
    });
    html+='</ul>';
    // Missing inputs
    if(j.missing && j.missing.length){
      html+='<div style="margin-top:10px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:12px">';
      html+='<b>Still needed to build the deliverable:</b><ul style="margin:6px 0 0 18px">';
      j.missing.forEach(m=>html+='<li>'+esc(m)+'</li>');
      html+='</ul></div>';
    }
    // Downloads
    if(j.downloads && Object.keys(j.downloads).length){
      html+='<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">';
      Object.entries(j.downloads).forEach(([k,url])=>{
        const label = k==='audit_docx'?'Audit (docx)':
                      k==='dashboard_html'?'Dashboard (HTML)':
                      k==='forecast_xlsx'?'Forecast (xlsx)':
                      k==='weekly_deck_pptx'?'Weekly deck (pptx)': k;
        html+='<a href="'+url+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:6px 12px">⬇ '+esc(label)+'</a>';
      });
      html+='</div>';
    }
    // Analysis text
    if(j.reply){
      html+='<div style="font-weight:600;margin:12px 0 6px;color:#7fdca0">Executive note</div>';
      html+='<div style="white-space:pre-wrap;font-size:13px;line-height:1.5">'+esc(j.reply)+'</div>';
    }
    html+='</div>';
    resBox.innerHTML=html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}
// ---------- /PPC section ----------

// ---------- Inventory section ----------
async function invRunBuild(){
  const resBox = document.getElementById("inv_result");
  const pl3 = document.getElementById("inv_pl3");
  const sales = document.getElementById("inv_sales");
  const yoy = document.getElementById("inv_yoy");
  const pd = document.getElementById("inv_pd");
  if(!pl3.files || !pl3.files[0]){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">3PL stock CSV is required.</div>'; return; }
  if(!sales.files || !sales.files[0]){ resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">Daily sales CSV is required.</div>'; return; }
  resBox.innerHTML='<div class="cc"><span class="genspin"></span> Pulling FBA inventory from SP-API + computing replenishment for every SKU…</div>';
  const fd = new FormData();
  fd.append("pl3_file", pl3.files[0]);
  fd.append("sales_file", sales.files[0]);
  if(yoy.files && yoy.files[0]) fd.append("yoy_file", yoy.files[0]);
  if(pd.files && pd.files[0]) fd.append("pd_file", pd.files[0]);
  fd.append("target_normal_days", document.getElementById("inv_normal").value || "85");
  fd.append("reorder_cycle_days", document.getElementById("inv_reorder").value || "5");
  fd.append("target_long_days", document.getElementById("inv_long").value || "110");
  fd.append("marketplace", WS_MARKET || "UK");
  fd.append("cycle_label", document.getElementById("inv_cycle").value || "");
  try{
    const j = await (await fetch("/inventory/build",{method:"POST", body:fd})).json();
    if(!j.ok){
      resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"build failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    const c = j.sku_coverage || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:#7fdca0">✓ Replenishment sheet built</div>';
    html += '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-bottom:10px">';
    html += '<div><b>'+j.row_count+'</b> SKUs total</div>';
    html += '<div><b style="color:#ffd76b">'+(s.replenish_yes||0)+'</b> flagged for replenishment</div>';
    html += '<div><b style="color:#7fdca0">'+(s.units_flagged||0)+'</b> units to reorder</div>';
    if(s.stockout_risk_skus){
      html += '<div><b style="color:#e0696b">'+s.stockout_risk_skus+'</b> stockout-risk SKUs (DOS &lt; 14)</div>';
    }
    html += '</div>';
    html += '<div style="font-size:11px;opacity:.75;margin-bottom:10px">SKU coverage — FBA (SP-API): '+(c.in_fba||0)+' · 3PL upload: '+(c.in_3pl||0)+' · Sales upload: '+(c.in_sales||0);
    if(c.in_yoy) html += ' · YoY: '+c.in_yoy;
    if(c.in_pd) html += ' · PD: '+c.in_pd;
    html += ' · Union: <b>'+(c.union||0)+'</b></div>';
    if(j.warnings && j.warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>SP-API warnings:</b><br>' + j.warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download replenishment xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;
  }catch(e){
    resBox.innerHTML='<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// ---------- v2 inventory handler (SP-API auto-fetch, 4-bucket classification) ----------
async function inv2Run(){
  const resBox = document.getElementById("inv2_result");
  const acctId = (CUR_ACCOUNT && CUR_ACCOUNT.id) || "";
  if(!acctId){
    resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">No workspace/account selected. Pick one from the sidebar first.</div>';
    return;
  }
  resBox.innerHTML = '<div class="cc"><span class="genspin"></span> Running inventory model — fetching FBA + sales from SP-API (5-15 min if cache is stale, instant if cached)…</div>';

  const fd = new FormData();
  fd.append("account_id", acctId);
  fd.append("marketplace", WS_MARKET || "US");
  fd.append("target_normal_dos",       document.getElementById("inv2_normal").value  || "85");
  fd.append("reorder_cycle_days",      document.getElementById("inv2_reorder").value || "5");
  fd.append("target_long_horizon_dos", document.getElementById("inv2_long").value    || "110");
  fd.append("sales_window_days",       document.getElementById("inv2_window").value  || "30");
  fd.append("cache_hours",             document.getElementById("inv2_cache").value   || "6");
  fd.append("force_refresh",           document.getElementById("inv2_force").checked ? "true" : "false");
  const three_pl_file = document.getElementById("inv2_3pl");
  if(three_pl_file.files && three_pl_file.files[0]) fd.append("three_pl_file", three_pl_file.files[0]);

  try{
    const j = await (await fetch("/inventory/v2/run",{method:"POST", body:fd})).json();
    if(!j.ok){
      resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px;border:1px solid #4d1e1e;border-radius:6px;background:#241010">'+esc(j.error||"run failed")+'</div>';
      return;
    }
    const s = j.summary || {};
    let html = '<div style="padding:12px;border:1px solid var(--line);border-radius:8px">';
    html += '<div style="font-weight:600;margin-bottom:8px;color:#7fdca0">✓ Inventory model complete</div>';

    // Bucket counts
    html += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;font-size:12px">';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#1c3a1c;color:#8adca0;border:1px solid #2a7a2a">ACTIVE '+(s.active||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a3a1c;color:#ffe066;border:1px solid #7a7a2a">NEW_LAUNCH '+(s.new_launch||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a2f1a;color:#ffce7a;border:1px solid #7a5a2a">DORMANT '+(s.dormant||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#3a1f1f;color:#ff8a8a;border:1px solid #7a2a2a">DEAD '+(s.dead||0)+'</div>';
    html += '<div style="padding:4px 10px;border-radius:4px;background:#1c2a3a;color:#8ac0ff;border:1px solid #2a5a7a">Total '+(s.total_skus||0)+'</div>';
    html += '</div>';

    // Reorder summary
    html += '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin-bottom:10px">';
    html += '<div><b style="color:#ffd76b">'+(s.fba_reorder_count||0)+'</b> SKUs need FBA reorder</div>';
    html += '<div><b>'+Math.round(s.total_fba_units_needed||0).toLocaleString()+'</b> total FBA units</div>';
    if(s.three_pl_reorder_count) html += '<div><b>'+s.three_pl_reorder_count+'</b> SKUs need 3PL reorder</div>';
    html += '</div>';

    // Data sources
    html += '<div style="font-size:11px;opacity:.75;margin-bottom:10px;line-height:1.5">';
    html += '<b>FBA source:</b> '+esc(j.fba_source||"")+'<br>';
    html += '<b>Velocity source:</b> '+esc(j.velocity_source||"");
    html += '</div>';

    // Sample alerts
    if(j.alerts_sample && j.alerts_sample.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>Sample alerts (first 10):</b>';
      html += '<ul style="margin:6px 0 0 18px">';
      j.alerts_sample.forEach(a=>{
        html += '<li>'+esc(a.sku)+' — '+esc(a.alert)+'</li>';
      });
      html += '</ul></div>';
    }
    if(j.three_pl_warnings && j.three_pl_warnings.length){
      html += '<div style="margin-top:8px;padding:8px;border-radius:6px;background:#241a10;border:1px solid #4d3712;color:#e3b768;font-size:11px">';
      html += '<b>3PL CSV warnings:</b><br>'+j.three_pl_warnings.map(esc).join("<br>");
      html += '</div>';
    }
    html += '<div style="margin-top:12px"><a href="'+j.download_url+'" download="'+j.filename+'" class="mktbtn on" style="display:inline-block;text-decoration:none;padding:8px 14px">⬇ Download inventory xlsx</a></div>';
    html += '</div>';
    resBox.innerHTML = html;

    // Refresh the sidebar alert badge
    invBadgeRefresh();
  }catch(e){
    resBox.innerHTML = '<div style="color:#e0696b;font-size:12px;padding:8px">Request failed: '+esc(String(e))+'</div>';
  }
}

// Polls /inventory/v2/alerts and updates the sidebar red badge
async function invBadgeRefresh(){
  const badge = document.getElementById("inv_badge");
  if(!badge) return;
  const acctId = (CUR_ACCOUNT && CUR_ACCOUNT.id) || "";
  if(!acctId){ badge.style.display="none"; return; }
  try{
    const j = await (await fetch("/inventory/v2/alerts?account_id="+encodeURIComponent(acctId))).json();
    const n = j.count || 0;
    if(n > 0){
      badge.textContent = n;
      badge.style.display = "inline-block";
    } else {
      badge.style.display = "none";
    }
  }catch(e){ /* silent */ }
}
// ---------- /Inventory section ----------

function runMode(mode, skus){
  if(ES){toast("A run is already streaming");return;}
  const log=document.getElementById("log");
  log.style.display="block"; log.textContent="";
  let url="/run/"+mode;
  // Generate-only: pass the row selection (value + type). Empty -> generate all.
  if(mode==="generate"){
    const valEl=document.getElementById("gensel_value");
    const typeEl=document.getElementById("gensel_type");
    const val=(valEl&&valEl.value||"").trim();
    if(val){
      const params=new URLSearchParams();
      params.set("select", val);
      // when a URL is pasted the dropdown is disabled; send 'auto' so the server auto-detects
      params.set("select_type", (typeEl&&!typeEl.disabled)? typeEl.value : "auto");
      url += "?"+params.toString();
    }
  }
  // Preview/Submit: if specific SKUs are passed (the user's SELECTION), scope the
  // run to exactly those. Empty -> the server's default (all approved/ready rows).
  if((mode==="api"||mode==="api_submit") && skus && skus.length){
    url += (url.indexOf("?")>=0?"&":"?")+"skus="+encodeURIComponent(skus.join(","));
  }
  ES=new EventSource(url);
  showStop(true);
  ES.onmessage=e=>{
    const cls = e.data.startsWith("[start]")?"start":e.data.startsWith("[done]")?"done":"l";
    const div=document.createElement("div"); div.className=cls; div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;showStop(false);loadRows();toast("Run finished");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;showStop(false);loadRows();}};
}
// ---- Per-listing Preview / Submit ----
function _streamRun(url, doneMsg){
  if(ES){toast("A run is already streaming");return;}
  let log=document.getElementById("log");
  if(log){ log.style.display="block"; log.textContent=""; }
  ES=new EventSource(url);
  ES.onmessage=e=>{
    if(!log) return;
    const cls=e.data.startsWith("[start]")?"start":e.data.startsWith("[done]")?"done":"l";
    const div=document.createElement("div"); div.className=cls; div.textContent=e.data;
    log.appendChild(div); log.scrollTop=log.scrollHeight;
  };
  ES.addEventListener("end",()=>{ES.close();ES=null;loadRows();toast(doneMsg||"Done");});
  ES.onerror=()=>{if(ES){ES.close();ES=null;loadRows();}};
}
function _runPanel(sku){
  const p=document.getElementById("runpanel_"+sid(sku));
  if(!p) return null;
  return {
    box:p,
    title:p.querySelector(".runtitle"),
    verdict:p.querySelector(".runverdict"),
    log:p.querySelector(".runlog"),
    show(t){ p.style.display="block"; this.title.textContent=t; this.verdict.innerHTML=""; this.log.textContent=""; }
  };
}
// Stream a run INTO the listing's own panel, parsing Amazon's response into a
// clear verdict (accepted / needs fields / error).
function _streamRunPanel(url, sku, mode){
  // clear any stale stream first so a previous run can't block this one
  if(ES){ try{ES.close();}catch(e){} ES=null; }
  window.RUN_STREAMING=true;   // block render() from rebuilding the drawer mid-run
  const P=_runPanel(sku);
  if(P) P.show((mode==="submit"?"Submitting ":"Previewing ")+sku+" …");
  let sawStart=false, lines=[], verdict=null, warnings="", done=false;
  ES=new EventSource(url);
  ES.onmessage=e=>{
    const d=e.data||"";
    lines.push(d);
    if(P){ P.log.textContent+=d+"\n"; P.log.scrollTop=P.log.scrollHeight; }
    if(d.indexOf("[busy]")>=0){ verdict={kind:"busy", raw:d}; }
    if(d.startsWith("[start]")){ sawStart=true; if(P) P.verdict.innerHTML='<span class="rspin"></span> Request sent to Amazon… waiting for response.'; }
    // parse the per-row result line for THIS sku
    if(d.indexOf(sku)>=0){
      const low=d.toLowerCase();
      let m=d.match(/(\d+)\s+error\(s\)/i);
      if(m){ verdict={kind:"error", n:parseInt(m[1]), raw:d}; }
      else if(low.indexOf("missing")>=0 && low.indexOf("skip")>=0){ verdict={kind:"missing", raw:d}; }
      else if(low.indexOf("api_ready")>=0 || low.indexOf("preview clean")>=0){ verdict={kind:"ok_preview", raw:d}; }
      else if(low.indexOf("live")>=0 || low.indexOf("submitted")>=0){ verdict={kind:"ok_submit", raw:d}; }
      else if(low.indexOf("api call failed")>=0 || low.indexOf("api_error")>=0){ verdict={kind:"error", n:0, raw:d}; }
      const wm=d.match(/warnings?:\s*(.+)$/i); if(wm) warnings=wm[1];
    }
    if(d.toLowerCase().indexOf("none of the requested")>=0 && !verdict){ verdict={kind:"notfound", raw:d}; }
    if(d.toLowerCase().indexOf("no seller_id")>=0) verdict={kind:"nocreds", raw:d};
    // network / DNS failure (e.g. "getaddrinfo failed", "Failed to resolve",
    // "Max retries exceeded", "NameResolutionError") -> the script couldn't even
    // reach Google/Amazon, so this is a connectivity problem, not a listing one.
    {
      const dl=d.toLowerCase();
      if(/getaddrinfo failed|failed to resolve|nameresolutionerror|max retries exceeded|connectionerror|transporterror|errno 11002|temporary failure in name resolution|connection timed out|handshake operation timed out/.test(dl)){
        verdict={kind:"network", raw:d};
      }
    }
  };
  function finish(){
    if(done) return; done=true;
    if(ES){ ES.close(); ES=null; }
    // NOTE: keep window.RUN_STREAMING = true so render() won't rebuild the drawer
    // and wipe this panel. It's cleared when YOU close the panel (the ✕ button).
    // NOTE: deliberately do NOT call loadRows() here -- it rebuilds the grid and
    // the open drawer, which would wipe this panel. The status is written to the
    // sheet regardless; the panel stays so you can read the result + full log.
    if(!P) return;
    if(!sawStart){
      if(verdict && verdict.kind==="busy"){ P.verdict.innerHTML='<span class="rwarn">A previous Preview/Submit for this account is still finishing (it may be retrying a slow schema download). Wait ~10\u201320 seconds and click Preview again \u2014 the app clears the lock automatically once that run ends or its process exits, so you won\u2019t stay stuck.</span>'; return; }
      P.verdict.innerHTML='<span class="rbad">✗ The run didn\u2019t start. Check that the generator script is reachable.</span>'; return;
    }
    if(verdict && verdict.kind==="network"){
      // Distinguish the common case where ONLY the schema CDN host failed to
      // resolve (the API host worked) -- that points at DNS, not bandwidth.
      const _raw=String(verdict.raw||"");
      const _cdnOnly=/schema host DNS lookup failed|schema download failed[^]*getaddrinfo|no schema for/i.test(_raw)
                     && /seller:|marketplace:|fetching schema/i.test(_raw);
      if(_cdnOnly){
        P.verdict.innerHTML='<div class="rbad">✗ DNS couldn\u2019t resolve Amazon\u2019s schema host.</div>'
          +'<div class="rmsg">Your connection is fine and Amazon\u2019s main API resolved \u2014 but the separate <b>schema CDN host</b> failed a DNS lookup (Errno 11002). Fast internet doesn\u2019t fix this; it\u2019s name-resolution, not speed. This almost always means something is filtering DNS.</div>'
          +'<div class="rhint"><b>Most effective fixes, in order:</b><br>1) <b>Disable any VPN/proxy</b> (the #1 cause \u2014 they reroute DNS).<br>2) Change your DNS to <code>1.1.1.1</code> or <code>8.8.8.8</code> (Wi\u2011Fi \u2192 Properties \u2192 DNS). Public DNS resolves Amazon\u2019s CDN reliably.<br>3) Run <code>ipconfig /flushdns</code> then Preview again.<br>4) Check no firewall/antivirus or hosts\u2011file rule is blocking Amazon CDN domains.</div>';
        return;
      }
      P.verdict.innerHTML='<div class="rbad">✗ Network problem — couldn\u2019t reach Google/Amazon to run this.</div>'
        +'<div class="rmsg">Your computer failed a DNS lookup, so the app never got to validate the listing. This is a connection issue, not a problem with the listing.</div>'
        +'<div class="rhint"><b>Try this:</b> 1) Preview again (often transient). 2) If you\u2019re on a <b>VPN/proxy</b>, turn it off. 3) Open Command Prompt and run <code>ipconfig /flushdns</code>, then retry. 4) Switch your DNS to <code>1.1.1.1</code> or <code>8.8.8.8</code>. 5) Confirm your internet is up by opening any website.</div>';
      return;
    }
    if(!verdict){ P.verdict.innerHTML='<span class="rwarn">Finished, but no result line was found for this SKU. Open the log below to read exactly what happened.</span>'; return; }
    if(verdict.kind==="nocreds"){ P.verdict.innerHTML='<span class="rbad">✗ No SP-API credentials for this account/marketplace.</span> Add them in the account editor before publishing.'; return; }
    if(verdict.kind==="missing"){
      P.verdict.innerHTML='<div class="rbad">✗ This row is missing a SKU or Product Type in the sheet.</div>'
        +'<div class="ramz">'+esc(verdict.raw.trim())+'</div>'
        +'<div class="rhint">Open the listing in the sheet/editor and make sure both <b>SKU</b> and <b>Product Type</b> are filled, then Preview again.</div>';
      return;
    }
    if(verdict.kind==="notfound"){
      P.verdict.innerHTML='<div class="rwarn">This SKU wasn\u2019t found to validate in this account\u2019s sheet/tab.</div>'
        +'<div class="rhint">Make sure you\u2019re in the right account workspace and the listing is in this tab, with <b>SKU</b> and <b>Product Type</b> columns filled.</div>';
      return;
    }
    if(verdict.kind==="error"){
      // A timeout is NOT a rejection -- the call never completed validation. Show
      // it as a connection slowness so the user doesn't go hunting for fields.
      if(/timed out|timeout|read operation|TIMED OUT/i.test(String(verdict.raw||""))){
        P.verdict.innerHTML='<div class="rbad">\u2717 The validation call to Amazon timed out.</div>'
          +'<div class="rmsg">This is <b>not</b> a problem with your listing \u2014 the call to Amazon\u2019s UK/EU endpoint was too slow to finish. The app already retried automatically.</div>'
          +'<div class="rhint"><b>Try this:</b> 1) Preview again (often works on the next try). 2) If you\u2019re on a VPN/proxy, turn it off \u2014 it adds latency to the EU endpoint. 3) Switch DNS to <code>1.1.1.1</code>. 4) If it keeps timing out, your connection to Amazon EU is slow right now \u2014 wait a moment and retry.</div>';
        return;
      }
      const msg=esc(verdict.raw.replace(/^.*error\(s\)\)?/i,"").trim()||verdict.raw);
      P.verdict.innerHTML='<div class="rbad">✗ Amazon did NOT accept this listing — '+(verdict.n||"")+' issue(s).</div>'
        +'<div class="rmsg">Amazon is asking for fixes / extra fields:</div><div class="ramz">'+msg+'</div>'
        +'<div class="rhint">Click <b>Suggest missing fields</b> above to fill what Amazon flagged, then Preview again.</div>';
      return;
    }
    if(verdict.kind==="ok_preview"){
      P.verdict.innerHTML='<div class="rgood">\u2713 Amazon accepted this listing — no missing or invalid fields.</div>'
        +(warnings?('<div class="rwarn">Non-blocking warnings: '+esc(warnings)+'</div>'):'<div class="rmsg">No extra boxes need filling. It\u2019s ready to submit.</div>');
      return;
    }
    if(verdict.kind==="ok_submit"){
      P.verdict.innerHTML='<div class="rgood">\u2713 Published live to Amazon.</div>'
        +(warnings?('<div class="rwarn">Warnings: '+esc(warnings)+'</div>'):'<div class="rmsg">The listing is now live on your account.</div>');
      return;
    }
  }
  ES.addEventListener("end", finish);
  // After the run ends, quietly refresh THIS row's stored data (notes/status)
  // so when the panel is closed the drawer shows the fresh result, not the old
  // cached errors. Doesn't rebuild the grid (that would wipe the panel).
  ES.addEventListener("end", ()=>{
    setTimeout(async ()=>{
      try{
        const j = await (await fetch("/row?sku="+encodeURIComponent(sku))).json();
        if(j && j.ok && j.row){
          const idx = ROWS.findIndex(x=>String(x.sku)===String(sku));
          if(idx>=0){ ROWS[idx] = {...ROWS[idx], ...j.row}; }
          // If the drawer is still open for this SKU, re-render JUST the listing
          // data block so the fields Amazon just flagged (e.g. hazmat) appear as
          // editable boxes right away -- without rebuilding the run panel above.
          if(String(DRAWER_SKU)===String(sku)){
            const host=document.getElementById("fulldata_"+sid(sku));
            const fresh=ROWS.find(x=>String(x.sku)===String(sku));
            if(host && fresh){
              host.innerHTML=fullData(fresh);
              setTimeout(()=>{ if(typeof bulletMeter==='function') bulletMeter(); }, 40);
            }
          }
        }
      }catch(e){}
    }, 800);
  });
  // EventSource fires onerror on NORMAL stream close too. Only treat it as a real
  // error if we haven't already finished AND nothing has streamed yet.
  ES.onerror=()=>{
    if(done) return;
    // give the 'end' event a moment; if it never came and we got no data, it's a real failure
    setTimeout(()=>{
      if(done) return;
      if(ES){ try{ES.close();}catch(e){} ES=null; }
      if(lines.length>0){ finish(); }   // stream produced output then dropped -> show what we have
      else if(P){ done=true; P.verdict.innerHTML='<span class="rbad">✗ Couldn\u2019t reach the run stream. Is the app still running? Try again.</span>'; }
    }, 600);
  };
}
let MINIMAL_MODE_ON = false;
function toggleMinimal(cb){ MINIMAL_MODE_ON = !!cb.checked;
  toast(MINIMAL_MODE_ON ? "Minimal mode ON — only required fields will be sent" : "Minimal mode off"); }
// Exact-payload viewer: off by default (it's debug). Persisted in localStorage.
let SHOW_PAYLOAD_VIEWER = false;
try{ SHOW_PAYLOAD_VIEWER = (localStorage.getItem("show_payload_viewer")==="1"); }catch(e){}
window.SHOW_PAYLOAD_VIEWER = SHOW_PAYLOAD_VIEWER;
function togglePayloadViewer(cb){
  window.SHOW_PAYLOAD_VIEWER = !!cb.checked;
  try{ localStorage.setItem("show_payload_viewer", cb.checked?"1":"0"); }catch(e){}
  toast(cb.checked ? "Exact-payload viewer ON" : "Exact-payload viewer hidden");
  if(typeof render==="function"){ try{ render(); }catch(e){} }
}
function _minParam(){ return MINIMAL_MODE_ON ? "&minimal=1" : ""; }
function previewOne(sku){
  if(!sku) return;
  _streamRunPanel("/run/api?skus="+encodeURIComponent(sku)+_minParam(), sku, "preview");
}
async function submitOne(sku){
  if(!sku) return;
  // same safety as the global submit: precheck local images, then confirm the account
  try{
    const pc=await (await fetch("/submit/precheck")).json();
    if(pc&&pc.ok&&pc.count>0){
      const hit=(pc.local_image_rows||[]).some(x=>String(x.sku)===String(sku));
      if(hit){
        if(!confirm("⚠ This listing's main image is a LOCAL file Amazon can't fetch (it lives on your PC). "
          +"It will FAIL with 'Unable to Retrieve Media Content'.\n\nUse a publicly-hosted image URL first, "
          +"or submit anyway to see the error?")) return;
      }
    }
  }catch(e){}
  let t=null; try{ t=await (await fetch('/submit/target')).json(); }catch(e){}
  let who = (t&&t.ok)?(t.account_label+" · "+t.marketplace):"your live account";
  if(t&&t.ok&&t.block==='none'){ alert("No SP-API credentials for this marketplace. Add them first."); return; }
  // Amazon-side duplicate check: warn if this SKU already exists live on Amazon
  try{
    const dc=await (await fetch("/dup_check",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({skus:[sku]})})).json();
    if(dc&&dc.ok&&dc.exists&&dc.exists.length){
      const ex=dc.exists[0];
      if(!confirm("⚠ This SKU already exists on Amazon ("+who+")"
        +(ex.title?("\n  Live listing: "+ex.title):"")
        +"\n\nSubmitting will REPLACE the existing live listing. Continue?")) return;
    }
  }catch(e){}
  if(!confirm("PUBLISH THIS LISTING LIVE\n\n  SKU: "+sku+"\n  Account: "+who
      +(MINIMAL_MODE_ON?"\n  Mode: MINIMAL (required fields only)":"")
      +"\n\nThis creates/replaces ONLY this listing on the account above. Continue?")) return;
  toast("Submitting "+sku+"…");
  _streamRunPanel("/run/api_submit?skus="+encodeURIComponent(sku)+_minParam(), sku, "submit");
}

async function loadViews(){
  try{
    const j=await (await fetch('/view/list')).json();
    if(!j.ok) return;
    const sel=document.getElementById('viewsel'); if(!sel) return;
    sel.innerHTML=j.views.map(v=>`<option value="${v.key}" data-sheet="${v.sheet||''}" data-tab="${v.tab||''}">${v.label}</option>`).join('');
    sel.value=j.active||'';
  }catch(e){}
}
async function switchView(key){
  const sel=document.getElementById('viewsel');
  const opt=sel&&sel.selectedOptions&&sel.selectedOptions[0];
  const sheet=opt?opt.getAttribute('data-sheet'):'';
  const tab=opt?opt.getAttribute('data-tab'):'';
  try{
    await fetch('/view/set',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key:key,sheet:sheet,tab:tab})});
    const bp=document.getElementById('brandpanel'); if(bp) bp.style.display='none';
    document.getElementById('grid').style.display='';
    const sm=document.getElementById('summary'); if(sm) sm.style.display='';
    toast(key?('Showing: '+key):'Showing: all (default)');
    loadRows();
  }catch(e){ toast('Could not switch view'); }
}
loadViews();
async function loadRows(){
  try{
    const j=await _fetchJSON("/rows", null, 20000);
    if(!j || j._failed){ toast("Could not load listings: "+((j&&j.error)||"timeout")); return; }
    if(!j.ok){ toast("Sheet error: "+(j.error||"unknown")); return; }
    ROWS=j.rows||[]; SHIP=j.shipping_group||""; PTYPES=j.product_types||[];
    render();
    const pts=[...new Set(ROWS.map(r=>r.product_type).filter(Boolean))];
    try{ await loadSchemas(pts); }catch(e){}
    render();
  }catch(e){ toast("Could not load: "+e); }
}
loadRows();

/* ---------- floating Claude assistant ---------- */
let CHAT = [];
let CHATIMGS = [];
function toggleChat(){
  const w=document.getElementById("chatwrap");
  w.classList.toggle("open");
  if(w.classList.contains("open")){ fillChatCtx(); setTimeout(()=>document.getElementById("chatinput").focus(),50); }
}
function fillChatCtx(){
  const sel=document.getElementById("chatctx"); const cur=sel.value;
  const opts=['<option value="">\u2014 general \u2014</option>'].concat(
    (ROWS||[]).filter(r=>r.sku||r.title||r.product_type).map(r=>{
      const label=(r.product_type||"?")+" \u00b7 "+String(r.title||r.sku||"row").slice(0,42);
      return '<option value="'+esc(String(r.sku||r.row||""))+'">'+esc(label)+'</option>';
    }));
  sel.innerHTML=opts.join(""); sel.value=cur;
}
function chatKey(e){ if(e.key==="Enter"&&!e.shiftKey){ e.preventDefault(); sendChat(); } }
function onChatFile(e){
  const f=e.target.files&&e.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=()=>{ CHATIMGS.push({media_type:f.type||"image/jpeg",data:String(rd.result).split(",")[1],name:f.name||"image"}); renderChips(); };
  rd.readAsDataURL(f); e.target.value="";
}
function onChatPaste(e){
  const items=(e.clipboardData&&e.clipboardData.items)||[];
  for(const it of items){
    if(it.type&&it.type.indexOf("image/")===0){
      const f=it.getAsFile();
      if(f){ const rd=new FileReader(); rd.onload=()=>{ CHATIMGS.push({media_type:f.type,data:String(rd.result).split(",")[1],name:"pasted image"}); renderChips(); }; rd.readAsDataURL(f); }
    }
  }
}
function renderChips(){
  document.getElementById("chatchips").innerHTML =
    CHATIMGS.map((im,i)=>'<span class="chip">\ud83d\uddbc '+esc(im.name)+' <button onclick="CHATIMGS.splice('+i+',1);renderChips()">\u00d7</button></span>').join("");
}
function chatBubble(role,text,imgs){
  const em=document.getElementById("chatempty"); if(em) em.remove();
  const body=document.getElementById("chatbody");
  const div=document.createElement("div"); div.className="msg "+(role==="user"?"u":"a"); div.textContent=text;
  if(imgs&&imgs.length){ imgs.forEach(im=>{ const x=document.createElement("img"); x.src="data:"+im.media_type+";base64,"+im.data; div.appendChild(x); }); }
  body.appendChild(div); body.scrollTop=body.scrollHeight; return div;
}
async function sendChat(){
  const ta=document.getElementById("chatinput"); const text=ta.value.trim();
  if(!text && !CHATIMGS.length) return;
  const btn=document.getElementById("chatsend"); btn.disabled=true;
  const imgs=CHATIMGS.slice(); CHATIMGS=[]; renderChips();
  CHAT.push({role:"user", text: text || "(see attached image)"});
  chatBubble("user", text || "(image)", imgs); ta.value="";
  let ctx=null; const sv=document.getElementById("chatctx").value;
  if(sv){ const r=(ROWS||[]).find(x=>String(x.sku)===sv||String(x.row)===sv);
    if(r) ctx={product_type:r.product_type,title:r.title,bullets:r.bullets,attributes:r.attributes,competitor_asin:r.asin,source_url:r.source,price:r.price,status:r.status,amazon_flags:r.notes||"",flagged_fields:parseFlagged(r.notes)}; }
  const wait=chatBubble("assistant","\u2026",null);
  try{
    const res=await fetch("/ask",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({messages:CHAT,context:ctx,images:imgs})});
    const j=await res.json(); wait.remove();
    if(j.ok){ CHAT.push({role:"assistant", text:j.reply}); chatBubble("assistant", j.reply); }
    else{ chatBubble("assistant", "\u26a0 "+(j.error||"failed")); }
  }catch(e){ wait.remove(); chatBubble("assistant","\u26a0 request failed"); }
  btn.disabled=false; ta.focus();
}

async function saveDefault(sku, pt, btn){
  btn.disabled=true; const orig=btn.textContent; btn.textContent="Saving…";
  try{
    const res=await fetch("/save_default",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sku:sku})});
    const j=await res.json();
    if(j.ok){ btn.textContent="★ Saved "+j.count+" default(s) for "+(j.pt||pt); toast("Defaults saved for "+(j.pt||pt)+" — future "+(j.pt||pt)+" listings will prefill these"); setTimeout(()=>{btn.textContent=orig;btn.disabled=false;},2800); }
    else{ btn.textContent=orig; btn.disabled=false; toast("Save failed: "+(j.error||"")); }
  }catch(e){ btn.textContent=orig; btn.disabled=false; toast("Save failed"); }
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
  LIVE_ITEMS=[]; LIST_SOURCE = hasCreds ? 'all' : 'drafts';   // All = drafts + live for connected accounts
  // default marketplace: account's configured default, else first detected
  const dflt = a.default_marketplace && (a.marketplaces||[]).indexOf(a.default_marketplace)>=0 ? a.default_marketplace : null;
  WS_MARKET = dflt || ((a.marketplaces && a.marketplaces.length) ? a.marketplaces[0] : "");
  CUR_SYMBOL = (WS_MARKET==="US"||WS_MARKET==="CA"||WS_MARKET==="MX") ? "$" : ((WS_MARKET==="EU"||["DE","FR","IT","ES","NL"].includes(WS_MARKET)) ? "\u20ac" : "\u00a3");
  var sw=document.getElementById('srcswitch'); if(sw){ sw.style.display='flex'; sw.querySelectorAll('.mktbtn').forEach(b=>b.classList.toggle('on',b.dataset.src===LIST_SOURCE)); }
  // tell the backend this account is active (all submit/preview use ITS creds)
  try{ await fetch("/accounts/select",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:a.id})}); }catch(e){}
  // paint shell
  document.getElementById("home").classList.remove("show");
  document.getElementById("workspace").classList.add("show");
  const col=_wsColorKey(a.id||a.label);
  const icEl=document.getElementById("ws_ic");
  icEl.style.background=col.bg; icEl.style.color=col.fg; icEl.innerHTML=_initials(a.label);
  document.getElementById("ws_nm").textContent=a.label;
  document.getElementById("ws_sub").textContent="Amazon account"+(a.seller_id?(" · "+a.seller_id):"");
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
      <tr><td colspan="2" style="padding-top:10px"><div style="font-weight:600;font-size:13px"><i class="ti ti-shopping-cart"></i> eBay source credentials <span class="cc">(optional — per-account override)</span></div><div class="cc" style="font-size:11.5px">Used to scrape the source eBay listing for each row. Leave blank to use the app-wide eBay keys (set in <b>AI &amp; settings ▸ eBay</b>). <b>If you fill BOTH fields here, they override the global eBay credentials for THIS account.</b></div></td></tr>
      <tr><td class="k">eBay App ID <span class="cc">(client ID)</span></td><td class="v"><input class="ed" id="ac_ebay_app" value="${esc(a.ebay_app_id||'')}" placeholder="leave blank to use global"></td></tr>
      <tr><td class="k">eBay Cert ID <span class="cc">(secret)</span></td><td class="v"><input class="ed" id="ac_ebay_cert" type="password" placeholder="${a.has_ebay_cert?'•••••• (leave blank to keep)':'leave blank to use global'}"></td></tr>
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
async function saveAccount(){
  const inUrl=(document.getElementById("ac_input_url")||{}).value||"";
  const outUrl=(document.getElementById("ac_output_url")||{}).value||"";
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
    ebay_app_id:((document.getElementById("ac_ebay_app")||{}).value||"").trim(),
    ebay_cert_id:((document.getElementById("ac_ebay_cert")||{}).value||"").trim(),
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

// ---- Image refs section: shows this workspace's saved reference image ----
let _IREF_PROFILE = null;
async function loadImageRefs(){
  const box=document.getElementById("imagerefsbody");
  let html="";
  // brand reference card (brands only)
  if(ACTIVE_WS && ACTIVE_WS.brand){
    let prof={};
    try{ prof=await (await fetch("/brand/get/"+encodeURIComponent(ACTIVE_WS.brand))).json(); }catch(e){}
    _IREF_PROFILE = prof.profile || prof || {};
    const ref=_IREF_PROFILE.main_image_reference||"";
    html+=`
      <div class="card" style="max-width:560px">
        <div class="kvsec">Brand main-image reference</div>
        <p class="cc" style="margin:0">Offered as the reference when generating a main image for any product in this brand (still overridable per-listing).</p>
        ${ref?`<img class="thumb" style="width:160px;height:160px" src="${esc(ref)}">`:'<div class="hint cc">No reference saved yet.</div>'}
        <div style="display:flex;gap:6px;align-items:center">
          <input class="ed" id="iref_input" style="flex:1" placeholder="https://… or upload →" value="${esc(ref)}">
          <label class="uploadbtn"><i class="ti ti-upload"></i> Upload
            <input type="file" accept="image/*" style="display:none" onchange="uploadIRef(this)"></label>
        </div>
        <div><button class="primary" onclick="saveImageRef()">Save reference</button></div>
      </div>`;
  } else {
    html+=`<div class="reqnote">Dropshipping uses each listing's eBay source image as the AI reference automatically. The media library below holds every image you generate or upload, filed by SKU.</div>`;
  }
  // media library: folders per SKU
  html+=`<div class="kvsec" style="margin-top:18px"><i class="ti ti-folders"></i> Media library — by SKU</div>
         <div id="medialib"><div class="cc">Loading media…</div></div>`;
  box.innerHTML=html;
  loadMediaLibrary();
}
async function uploadIRef(input){
  var file=input.files&&input.files[0]; if(!file) return;
  try{
    var dataUrl=await _fileToDataURL(file);
    var brand=(ACTIVE_WS&&ACTIVE_WS.brand)||'brand';
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:'_brand_'+brand,data:dataUrl,name:file.name,kind:'brandref'})});
    var j=await res.json();
    if(j.ok){ document.getElementById('iref_input').value=j.url; toast('Uploaded — click Save reference'); loadMediaLibrary(); }
    else toast('Upload failed: '+(j.error||''));
  }catch(e){ toast('Error: '+e); }
}
function _fmtBytes(n){
  n=Number(n)||0;
  if(n<1024) return n+' B';
  if(n<1048576) return (n/1024).toFixed(0)+' KB';
  return (n/1048576).toFixed(2)+' MB';
}
async function loadMediaLibrary(){
  var host=document.getElementById('medialib'); if(!host) return;
  try{
    var j=await (await fetch('/media/list')).json();
    if(!j.ok){ host.innerHTML='<div class="cc">Could not load media: '+esc(j.error||'')+'</div>'; return; }
    if(!j.folders||!j.folders.length){ host.innerHTML='<div class="emptynote">No media yet. Generated and uploaded images will appear here, filed by SKU.</div>'; return; }
    host.innerHTML=j.folders.map(function(f){
      return '<details class="mediafolder"><summary><i class="ti ti-folder"></i> '+esc(f.sku)+' <span class="cc">('+f.count+')</span></summary>'+
        '<div class="mediagrid">'+f.files.map(function(im){
          var _dim=(im.width&&im.height)?(im.width+'×'+im.height+' px'):'';
          var _sz=(im.bytes)?_fmtBytes(im.bytes):'';
          var _grp=im.group?('<span class="medagroup">'+esc(im.group)+'</span>'):'';
          var _meta=(_dim||_sz)?('<div class="mediameta">'+esc([_dim,_sz].filter(Boolean).join(' · '))+'</div>'):'';
          return '<div class="mediacell"><img src="'+esc(im.url)+'" loading="lazy" onclick="window.open(\''+esc(im.url)+'\')">'+_grp+
            '<button class="mediadel" title="Delete" onclick="delMedia(\''+esc(im.url)+'\')"><i class="ti ti-x"></i></button>'+
            '<button class="mediaedit" title="Edit this image (AI changes only what you ask, keeps the rest)" onclick="editMediaImage(\''+esc(im.url)+'\',\''+esc(f.sku)+'\')"><i class="ti ti-wand"></i> Edit</button>'+
            _meta+'</div>';
        }).join('')+'</div></details>';
    }).join('');
  }catch(e){ host.innerHTML='<div class="cc">Error: '+esc(String(e))+'</div>'; }
}
async function editListingImage(sku, url, idx){
  const instruction = prompt("What should the AI change about this image?\n\nIt edits ONLY what you ask and keeps everything else the same.\n\nExamples: \"pure white background\", \"add a soft shadow\", \"brighten the product\".");
  if(instruction===null) return;
  if(!instruction.trim()){ toast("Tell me what to change."); return; }
  toast("Editing image…");
  try{
    var r=(ROWS||[]).find(x=>String(x.sku)===String(sku));
    var res=await (await fetch("/genimage/refine",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({image:url, instruction:instruction.trim(),
        title:(r&&r.title)||"", kind:"main",
        text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)})})).json();
    if(!res.ok){ toast("Edit failed: "+(res.error||"unknown")); return; }
    var sv=await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, data:res.data_url, kind:"generated"})})).json();
    if(!sv.ok){ toast("Edited, but could not save: "+(sv.error||"")); return; }
    // if this was the MAIN image, offer to set the edited version as the new main
    if(idx===0 && confirm("Edited image saved. Set it as the MAIN image for this listing?\n(This updates the app copy; use \"Push image to live\" to send it to Amazon.)")){
      var useUrl=sv.url||res.data_url;
      await fetch('/edit',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sku:sku,target:'attr',key:'main_product_image_locator',value:useUrl})});
      toast("✓ Set as main image (app copy). Use 'Push image to live' to send to Amazon.");
      loadRows();
    } else {
      toast("✓ Edited image saved to "+sku+"'s library.");
    }
  }catch(e){ toast("Edit error: "+e); }
}
async function editMediaImage(url, sku){
  const instruction = prompt("What should the AI change about this image?\n\nIt edits ONLY what you ask and keeps everything else the same (same product, same layout, same colours).\n\nExamples: \"make the background pure white\", \"add a soft shadow under the product\", \"remove the text in the corner\".");
  if(instruction===null) return;
  if(!instruction.trim()){ toast("Tell me what to change."); return; }
  toast("Editing image… this takes a moment.");
  try{
    // the refine endpoint accepts a URL or data-url as the base image
    var it=_itemForSku(sku);
    var res=await (await fetch("/genimage/refine",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({image:url, instruction:instruction.trim(),
        title:(it&&it.title)||"", kind:"main",
        text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)})})).json();
    if(!res.ok){ toast("Edit failed: "+(res.error||"unknown")); return; }
    // save the edited image back into the same SKU's media library
    var sv=await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, data:res.data_url, kind:"generated"})})).json();
    if(sv.ok){
      toast("✓ Edited image saved to "+sku+"'s library"+(sv.drive_direct_url?" (also on Drive)":""));
      loadMediaLibrary();
    } else {
      toast("Edited, but could not save: "+(sv.error||""));
    }
  }catch(e){ toast("Edit error: "+e); }
}
async function delMedia(url){
  if(!confirm('Delete this image?')) return;
  try{ await fetch('/media/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url})}); loadMediaLibrary(); }
  catch(e){ toast('Could not delete: '+e); }
}
async function saveImageRef(){
  if(!ACTIVE_WS||!ACTIVE_WS.brand) return;
  const val=(document.getElementById("iref_input")||{}).value||"";
  const prof=Object.assign({}, _IREF_PROFILE||{}, {brand_name:ACTIVE_WS.brand, main_image_reference:val});
  try{
    await fetch("/brand/save",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(prof)});
    toast("Reference image saved");
    loadImageRefs();
  }catch(e){ toast("Could not save: "+e); }
}

// ---- AI settings modal ----
async function openAISettings(){
  const m=document.getElementById("aimodal"); m.classList.add("open");
  // reflect current payload-viewer setting on the toggle
  try{ var _pv=document.getElementById("payloadViewerToggle"); if(_pv) _pv.checked=!!window.SHOW_PAYLOAD_VIEWER; }catch(e){}
  const body=document.getElementById("aimodalbody");
  body.innerHTML="Loading models from OpenRouter…";
  let s; try{ s=await (await fetch("/ai/settings")).json(); }catch(e){ s={ok:false}; }
  if(!s.ok){ body.innerHTML='<div class="reqnote">Could not load AI settings.</div>'; return; }
  // current GLOBAL eBay creds (App ID shown; Cert never returned, only a masked tail)
  let eb; try{ eb=await (await fetch("/settings/ebay")).json(); }catch(e){ eb={ok:false}; }
  const ebSafe=(eb&&eb.ok)?eb:{ebay_app_id:"",has_cert:false,cert_tail:""};
  const keyNote = s.has_key
    ? (s.discover_ok ? `<span class="cc" style="color:#7fd99a">\u2713 OpenRouter connected \u2014 ${ (s.text_models||[]).length } text models, ${ (s.image_models||[]).length } image models available</span>`
                     : `<span class="cc" style="color:#e3b768">Key present, but model discovery failed: ${esc(s.discover_error||'')} (showing fallback list)</span>`)
    : `<div class="reqnote">No <code>openrouter_api_key</code> in your config.json. Get one at <a href="https://openrouter.ai/keys" target="_blank">openrouter.ai/keys</a> and add it locally, then click Refresh.</div>`;
  const opt=(models,chosen)=>models.map(mm=>`<option value="${esc(mm.id)}"${mm.id===chosen?" selected":""}>${esc(mm.name||mm.id)}</option>`).join("");
  body.innerHTML=`
    ${keyNote}
    <table class="kv" style="margin-top:10px">
      <tr><td class="k">Prompt enhancement model<br><span class="cc">writes the detailed image prompt</span></td>
          <td class="v"><select class="ed" id="ai_text">${opt(s.text_models||[], s.select.prompt_enhance)}</select></td></tr>
      <tr><td class="k">Image generation model<br><span class="cc">Nano Banana, GPT Image, Seedream, etc.</span></td>
          <td class="v"><select class="ed" id="ai_image">${opt(s.image_models||[], s.select.image_generate)}</select></td></tr>
    </table>
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="primary" onclick="saveAISettings()">Save selection</button>
      <button onclick="refreshAIModels()"><i class="ti ti-refresh"></i> Refresh model list</button>
      <a class="browsemodels" href="https://openrouter.ai/models" target="_blank" rel="noopener"><i class="ti ti-external-link"></i> Browse all models</a>
      <button onclick="closeAISettings()">Cancel</button>
    </div>
    <div class="adminbox" style="margin-top:12px">
      <div style="font-weight:600;margin-bottom:6px"><i class="ti ti-shopping-cart"></i> eBay source credentials <span class="cc">(global default)</span></div>
      <div class="cc" style="font-size:11.5px;margin-bottom:8px">Used to scrape each row's source eBay listing (title, item specifics, images) via eBay's Browse API. These are the app-wide defaults; any single account can override them in its <b>Account &amp; sheets</b> editor. <b>No eBay Dev ID is required</b> — the Browse API authenticates with only App ID + Cert ID.</div>
      <table class="kv">
        <tr><td class="k">eBay App ID <span class="cc">(client ID)</span></td><td class="v"><input class="ed" id="ebay_app" value="${esc(ebSafe.ebay_app_id||'')}" placeholder="YourApp-xxxx-PRD-xxxx-xxxx"></td></tr>
        <tr><td class="k">eBay Cert ID <span class="cc">(secret)</span></td><td class="v"><input class="ed" id="ebay_cert" type="password" placeholder="${ebSafe.has_cert?('•••• '+esc(ebSafe.cert_tail||'')+' — leave blank to keep'):'paste Cert ID'}"></td></tr>
      </table>
      <div style="margin-top:8px"><button class="primary" onclick="saveEbaySettings()"><i class="ti ti-check"></i> Save eBay credentials</button> <span id="ebay_status" class="cc"></span></div>
    </div>
    <div class="adminbox">
      <div style="font-weight:600;margin-bottom:6px"><i class="ti ti-shield-lock"></i> Admin — transparency &amp; access</div>
      <label class="seccheck" style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px">
        <input type="checkbox" id="adm_show_logic" ${ (s.admin&&s.admin.show_logic)!==false ? 'checked':'' }>
        <span><b>Show "How this works" logic panels</b><br><span class="cc">The collapsible arrows under each button that explain the real backend workflow. Turn OFF to hide them from everyone.</span></span>
      </label>
      <label class="seccheck" style="display:flex;align-items:flex-start;gap:8px">
        <input type="checkbox" id="adm_preview_user" ${ (s.admin&&s.admin.preview_as_user) ? 'checked':'' }>
        <span><b>Preview as a regular user</b><br><span class="cc">See the app exactly as a non-admin signup would — the logic panels are hidden while this is on, even if the option above is enabled. Uncheck to return to admin view.</span></span>
      </label>
      <div style="margin-top:8px"><button class="primary" onclick="saveAdminSettings()"><i class="ti ti-check"></i> Save admin settings</button> <span id="adm_status" class="cc"></span></div>
    </div>
    <p class="cc" style="margin-top:12px">One OpenRouter key powers every model. Your key lives only in your local config.json \u2014 this app never displays or stores the key value.</p>`;
}
async function refreshAIModels(){
  const body=document.getElementById("aimodalbody"); body.innerHTML="Refreshing from OpenRouter…";
  try{ await fetch("/ai/settings?refresh=1"); }catch(e){}
  AISET=null; openAISettings();
}
async function saveAdminSettings(){
  const show=(document.getElementById("adm_show_logic")||{checked:true}).checked;
  const prev=(document.getElementById("adm_preview_user")||{checked:false}).checked;
  const st=document.getElementById("adm_status");
  if(st) st.textContent="Saving…";
  try{
    const j=await (await fetch("/admin/logic_settings",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({show_logic:show, preview_as_user:prev})})).json();
    if(j.ok){
      window.LOGIC_VISIBLE = !!j.show_logic && !j.preview_as_user;
      AISET=null;
      if(typeof refreshStaticHowPanels==="function") refreshStaticHowPanels();
      if(st) st.innerHTML='<span style="color:#7fd99a">\u2713 saved — '+(window.LOGIC_VISIBLE?'logic panels visible':'logic panels hidden')+'</span>';
      toast(window.LOGIC_VISIBLE?"Logic panels are now visible.":"Logic panels are now hidden (user view).");
    } else { if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(String(e))+'</span>'; }
}
function closeAISettings(){ document.getElementById("aimodal").classList.remove("open"); }
async function saveAISettings(){
  const t=(document.getElementById("ai_text")||{}).value;
  const i=(document.getElementById("ai_image")||{}).value;
  try{
    await fetch("/ai/settings",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({prompt_enhance:t,image_generate:i})});
    AISET=null; // force reload in image-gen panels
    toast("AI selection saved");
    closeAISettings();
  }catch(e){ toast("Could not save: "+e); }
}
async function saveEbaySettings(){
  const app=((document.getElementById("ebay_app")||{}).value||"").trim();
  const cert=((document.getElementById("ebay_cert")||{}).value||"").trim();
  const st=document.getElementById("ebay_status");
  if(st) st.textContent="Saving…";
  try{
    const j=await (await fetch("/settings/ebay",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ebay_app_id:app, ebay_cert_id:cert})})).json();
    if(j.ok){ if(st) st.innerHTML='<span style="color:#7fd99a">✓ saved</span>'; toast("eBay credentials saved"); }
    else { if(st) st.innerHTML='<span style="color:#e0696b">'+esc(j.error||"failed")+'</span>'; }
  }catch(e){ if(st) st.innerHTML='<span style="color:#e0696b">'+esc(String(e))+'</span>'; }
}

// ---- GLOBAL generation status bar + full-visibility panel (works everywhere) ----
// Image jobs run server-side, so they continue no matter what page you're on or
// even if you navigate away. The bottom bar shows overall progress on ANY page;
// the panel (View) shows EVERY planned image, its concept, live status, the
// finished thumbnail, and any error. Stop-all is always available.
let GEN_STATUS_POLL=null;
let GEN_ACTIVE_JOB="";      // the job whose detail the panel shows
let GEN_PANEL_OPEN=false;

async function pollGenStatus(){
  try{
    const j=await (await fetch("/genimage/jobs_active")).json();
    const bar=document.getElementById("genstatusbar");
    const txt=document.getElementById("genstatustext");
    if(bar&&txt){
      if(j.ok && j.jobs && j.jobs.length){
        let done=0,total=0;
        j.jobs.forEach(x=>{ done+=(x.done||0); total+=(x.total||0); });
        txt.textContent="Generating "+done+"/"+total+" image"+(total===1?"":"s")+"…";
        bar.style.display="flex";
        // adopt an active job for the panel if we don't have one yet
        if(!GEN_ACTIVE_JOB && j.jobs[0]) GEN_ACTIVE_JOB=j.jobs[0].job;
      } else {
        bar.style.display="none";
      }
    }
    // if the detail panel is open, refresh it
    if(GEN_PANEL_OPEN && GEN_ACTIVE_JOB){ refreshGenPanel(); }
  }catch(e){}
}
function startGenStatusPoll(){
  if(GEN_STATUS_POLL) return;
  pollGenStatus();
  GEN_STATUS_POLL=setInterval(pollGenStatus, 2000);
}
function openGenPanel(){
  const p=document.getElementById("genpanel"); if(!p) return;
  p.classList.add("open"); GEN_PANEL_OPEN=true;
  refreshGenPanel();
}
function closeGenPanel(){
  const p=document.getElementById("genpanel"); if(p) p.classList.remove("open");
  GEN_PANEL_OPEN=false;
}
async function refreshGenPanel(){
  if(!GEN_ACTIVE_JOB) return;
  let st;
  try{ st=await (await fetch("/genimage/job_status?job="+encodeURIComponent(GEN_ACTIVE_JOB))).json(); }
  catch(e){ return; }
  if(!st || !st.ok) return;
  const head=document.getElementById("genpanelhead");
  const grid=document.getElementById("genpanelgrid");
  const stopBtn=document.getElementById("genpanelstop");
  const okN=(st.results||[]).filter(r=>r.ok).length;
  const failN=(st.results||[]).filter(r=>r&&!r.ok).length;
  if(head){
    if(st.status==="running"){
      head.innerHTML='<span class="genspin"></span> Generating '+st.done+' of '+st.total+
        ' — <span style="color:#7fd99a">'+okN+' done</span>'+(failN?(' · <span style="color:#e0696b">'+failN+' failed</span>'):'');
    } else if(st.status==="error" && st.error==="stopped by user"){
      head.innerHTML='<span style="color:#e3b768">■ Stopped. '+okN+'/'+st.total+' finished before stopping.</span>';
    } else {
      head.innerHTML='<span style="color:#7fd99a">✓ Complete — '+okN+'/'+st.total+' generated'+
        (failN?(' · <span style="color:#e0696b">'+failN+' failed</span>'):'')+
        '. Saved to each product\u2019s library.</span>';
    }
  }
  if(stopBtn) stopBtn.style.display=(st.status==="running")?"":"none";
  if(grid){
    const plan=st.plan||[];
    const results=st.results||[];
    // build the card for each planned image; match results by index (jobs run in order)
    let html=plan.map((pl,i)=>{
      const r=results[i];
      let statusHtml, thumb="";
      if(!r){
        statusHtml = (i===results.length)
          ? '<span style="color:#9cc1ff"><span class="genspin"></span> generating…</span>'
          : '<span class="cc">queued</span>';
      } else if(r.ok && r.data_url){
        statusHtml='<span style="color:#7fd99a">✓ done'+(r.saved_url?' · saved':'')+'</span>';
        thumb='<img src="'+r.data_url+'" style="width:100%;border-radius:7px;margin-bottom:5px">';
      } else {
        statusHtml='<span style="color:#e0696b" title="'+esc(r.error||"failed")+'">✗ '+esc((r.error||"failed").slice(0,60))+'</span>';
      }
      return '<div style="border:1px solid var(--line);border-radius:9px;padding:8px;background:var(--panel2)">'
        + thumb
        + '<div style="font-size:11.5px;font-weight:600">'+esc(pl.img_code||("#"+(i+1)))+' · '+esc(pl.sku||"")+'</div>'
        + '<div class="cc" style="font-size:10.5px;margin:2px 0;max-height:52px;overflow:auto">'+esc((pl.concept||pl.label||"").slice(0,140))+'</div>'
        + '<div style="font-size:11px;margin-top:3px">'+statusHtml+'</div>'
        + '</div>';
    }).join("");
    grid.innerHTML=html || '<div class="cc">No jobs.</div>';
  }
}
async function stopAllGenerations(){
  if(!confirm("Stop ALL image generations currently running?")) return;
  try{
    const j=await (await fetch("/genimage/stop_all",{method:"POST"})).json();
    toast("Stopping "+(j.stopped||0)+" batch(es)… in-flight images finish, the rest are cancelled.");
    if(typeof STUDIO_POLL!=="undefined" && STUDIO_POLL){ clearInterval(STUDIO_POLL); STUDIO_POLL=null; }
    setTimeout(pollGenStatus, 800);
  }catch(e){ toast("Could not stop: "+e); }
}

// boot into the home screen
window.addEventListener("DOMContentLoaded", function(){ try{ if(localStorage.getItem("priv_on")==="1"){ togglePrivacy(); } }catch(e){} loadAISettings().then(function(){ if(typeof refreshStaticHowPanels==="function") refreshStaticHowPanels(); }); loadHome(); startGenStatusPoll(); });

