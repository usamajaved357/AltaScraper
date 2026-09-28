
// Self-contained "how it works" for the standalone brand panel (it can't reach
// the main page's helper). Respects the same admin flag from /ai/settings.
var BRAND_LOGIC_VISIBLE = true;
function _bEsc(s){ return String(s==null?"":s).replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); }
function brandHow(which){
  if(!BRAND_LOGIC_VISIBLE) return "";
  var reg = {
    brand_import: { title:"How importing a brand's Shopify export works", steps:[
      "<b>Parses your Shopify CSV/TSV</b> (<code>load_shopify_products</code>) — detecting the delimiter and reading each product: title, type, primary variant SKU, price (and price range for variants), cleaned EAN/UPC barcode, variant option axes, and all images (parent + continuation rows, de-duped).",
      "<b>Pulls description metafields</b> and strips their HTML to clean text.",
      "<b>Detects the catalogue language</b> so non-English source copy is handled (and never output verbatim).",
      "<b>Preview</b> just shows the product count and a sample — nothing is generated or written until you run." ]},
    brand_run: { title:"How generating a brand's listings works (vs dropshipping)", steps:[
      "<b>This is YOUR brand's own product</b> — so identity is preserved, not invented. <code>extract_identity</code> takes the MPN/model, GTIN/barcode and SKU <i>verbatim</i> from the export, each tagged with a code-verified <i>provenance</i> source.",
      "<b>Writes the listing with the brand's voice.</b> <code>build_brand_prompt</code> keeps the brand's strong phrasing and positioning but restructures it for Amazon and outputs English.",
      "<b>Claims are gated to evidence.</b> Any performance/health claim must be backed by your claim documents (pulled from the shared Drive folder); unsupported claims are dropped.",
      "<b>Brand pricing</b> (<code>compute_brand_price</code>): source price \u00d7 FX rate \u00d7 your markup, optionally rounded to .99 — or a fixed price if you set one.",
      "<b>Writes to your chosen Sheet/tab</b> (e.g. a US brand to your US sheet) with a status for review. Test run does a limited few; Generate ALL does the whole catalogue and uses full credits." ]}
  };
  var b = reg[which]; if(!b) return "";
  return '<details class="howbox"><summary><span class="chev">\u25b6</span> How this works \u2014 the actual steps behind the button</summary>'
    + '<div class="howbody"><div style="font-weight:600;color:var(--text);margin-bottom:2px">'+_bEsc(b.title)+'</div><ol>'
    + b.steps.map(function(s){return "<li>"+s+"</li>";}).join("")
    + '</ol><div style="margin-top:6px;opacity:.8">Nothing is sent to Amazon here \u2014 a brand run only fills your Google Sheet for review.</div></div></details>';
}
function brandRefreshHow(){
  var map={ "brandhow_import":"brand_import", "brandhow_run":"brand_run" };
  Object.keys(map).forEach(function(id){
    var el=document.getElementById(id);
    if(el) el.innerHTML = brandHow(map[id]);
  });
}
async function brandLoadLogicFlag(){
  try{ var s=await (await fetch("/ai/settings")).json();
    if(s&&s.admin){ BRAND_LOGIC_VISIBLE = !!s.admin.show_logic && !s.admin.preview_as_user; }
  }catch(e){}
  brandRefreshHow();
}
function brandTab(t){
  document.getElementById('pane-brand').style.display = t==='brand'?'block':'none';
  document.getElementById('pane-conn').style.display  = t==='conn'?'block':'none';
  document.getElementById('tab-brand').classList.toggle('active', t==='brand');
  document.getElementById('tab-conn').classList.toggle('active', t==='conn');
  if(t==='conn') connLoad();
}
function setTone(opts, current){
  const sel=document.getElementById('b_tone'); sel.innerHTML='';
  (opts||[{code:'en',label:'English',default:true}]).forEach(o=>{
    const op=document.createElement('option'); op.value=o.code; op.textContent=o.label; sel.appendChild(op);
  });
  sel.value = current || 'en';
}
async function brandRefresh(){
  const r=await (await fetch('/brand/list')).json();
  const sel=document.getElementById('b_select'); sel.innerHTML='<option value="">(new brand)</option>';
  const cards=document.getElementById('brand_cards'); if(cards) cards.innerHTML='';
  (r.brands||[]).forEach(b=>{
    const o=document.createElement('option');o.value=b.brand_name;o.textContent=b.brand_name;sel.appendChild(o);
    if(cards){
      const c=document.createElement('div');
      c.style.cssText='border:1px solid var(--line);border-radius:9px;padding:8px 11px;background:var(--panel2);cursor:pointer;min-width:150px;position:relative';
      c.innerHTML='<div style="font-weight:600;padding-right:18px">'+b.brand_name+'</div><div class="cc">'+(b.vendor_mode||'')+' \u00b7 '+(b.marketplace||'')+' \u00b7 '+(b.source_language||'en')+'</div>'
        +'<span title="Remove this trademark from this account" style="position:absolute;top:5px;right:7px;color:var(--red);font-weight:700;cursor:pointer" onclick="event.stopPropagation();brandRemoveFromAccount('+jsArg(b.brand_name)+')">\u00d7</span>';
      c.onclick=()=>{document.getElementById('b_select').value=b.brand_name; brandLoad(b.brand_name);};
      cards.appendChild(c);
    }
  });
  if(cards && !(r.brands||[]).length){ cards.innerHTML='<div class="cc">No brands saved yet. Fill the form below and click Save brand.</div>'; }
  // WORKSPACE LOCK: if opened inside a workspace, hide the multi-brand chooser
  // and auto-load only that brand.
  var locked = window.WS_BRAND || "";
  var chooserRow = document.getElementById('b_select') ? document.getElementById('b_select').closest('tr') : null;
  if(locked){
    if(cards) cards.style.display='none';
    if(chooserRow) chooserRow.style.display='none';
    var has=(r.brands||[]).some(function(b){return b.brand_name===locked;});
    if(has){ document.getElementById('b_select').value=locked; brandLoad(locked); }
    else { var nm=document.getElementById('b_name'); if(nm) nm.value=locked; }
  } else {
    if(cards) cards.style.display='flex';
    if(chooserRow) chooserRow.style.display='';
  }
}
async function brandLoad(name){
  if(!name){return;}
  const p=await (await fetch('/brand/get/'+encodeURIComponent(name))).json();
  b_name.value=p.brand_name||''; b_vendor_mode.value=p.vendor_mode||'single_brand';
  b_voice_mode.value=p.voice_mode||'regenerate'; b_marketplace.value=p.marketplace||'UK';
  b_coo.value=p.country_of_origin||''; b_lead.value=String(p.lead_with_brand!==false);
  b_prefix_on.value=String(!!p.sku_prefix_enabled); b_prefix.value=p.sku_prefix||'';
  b_csv.value=p.shopify_export_path||''; b_drive.value=p.claims_docs_drive_url||'';
  b_comp.value=(p.competitor_asins||[]).join(', '); b_forbidden.value=(p.forbidden_brands||[]).join(', ');
  b_voicenotes.value=p.voice_notes||'';
  document.getElementById('b_srccur').value=p.source_currency||'';
  document.getElementById('b_fx').value=p.fx_rate||'';
  document.getElementById('b_markup').value=p.price_markup||'';
  document.getElementById('b_round99').checked=!!p.price_round_99;
  document.getElementById('b_fixed').value=p.price_fixed||'';
  document.getElementById('b_outsheet').value=p.output_spreadsheet_id||'';
  document.getElementById('b_outtab').value=p.output_tab||'';
  document.getElementById('b_mainimgref').value=p.main_image_reference||'';
  setTone(p._tone_options, p.tone_language);
}
async function brandSave(){
  const body={brand_name:b_name.value, vendor_mode:b_vendor_mode.value, voice_mode:b_voice_mode.value,
    tone_language:b_tone.value, marketplace:b_marketplace.value, country_of_origin:b_coo.value,
    lead_with_brand:b_lead.value==='true', sku_prefix_enabled:b_prefix_on.value==='true',
    sku_prefix:b_prefix.value, shopify_export_path:b_csv.value, claims_docs_drive_url:b_drive.value,
    competitor_asins:b_comp.value, forbidden_brands:b_forbidden.value, voice_notes:b_voicenotes.value,
    source_currency:document.getElementById('b_srccur').value,
    fx_rate:document.getElementById('b_fx').value,
    price_markup:document.getElementById('b_markup').value,
    price_round_99:document.getElementById('b_round99').checked,
    price_fixed:document.getElementById('b_fixed').value,
    output_spreadsheet_id:document.getElementById('b_outsheet').value,
    output_tab:document.getElementById('b_outtab').value,
    main_image_reference:document.getElementById('b_mainimgref').value};
  const r=await (await fetch('/brand/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)})).json();
  await uiAlert(r.ok?'Brand saved.':'Error: '+(r.error||'?')); brandRefresh();
}
async function brandUpload(input){
  const f = input.files && input.files[0]; if(!f) return;
  const st=document.getElementById('b_uploadstatus'); st.textContent='Uploading '+f.name+'…';
  const fd=new FormData(); fd.append('file', f);
  try{
    const r=await (await fetch('/brand/upload',{method:'POST',body:fd})).json();
    if(!r.ok){ st.textContent='Upload failed: '+(r.error||'?'); return; }
    document.getElementById('b_csv').value = r.path;
    st.textContent='Uploaded ('+(r.bytes/1024|0)+' KB) → '+r.path;
    brandPreview();   // auto-preview so they see product count + language immediately
  }catch(e){ st.textContent='Upload error: '+e; }
}
async function brandPreview(){
  const out=document.getElementById('b_preview'); out.textContent='Parsing...';
  const r=await (await fetch('/brand/preview',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({csv_path:b_csv.value})})).json();
  if(!r.ok){out.textContent='Error: '+r.error;return;}
  setTone(r.tone_options, b_tone.value);
  out.innerHTML = `<b>${r.count}</b> products | source language: <b>${r.language.name}</b>`
    + ` | statuses: ${JSON.stringify(r.statuses)}`
    + `<br>top vendors: ` + r.vendors.map(v=>`${v.name} (${v.count})`).join(', ');
}
async function brandRun(testMode){
  if(!b_name.value){await uiAlert('Save the brand first.');return;}
  let limit=0;
  if(testMode){ limit=parseInt((document.getElementById('b_testlimit')||{}).value||'2',10)||2; }
  const log=document.getElementById('brandlog'); log.style.display='block';
  log.textContent=testMode?('TEST RUN \u2014 first '+limit+' listing(s)\n'):'GENERATING ALL listings\n';
  const stop=document.getElementById('b_stopbtn'); if(stop) stop.style.display='inline-block';
  const es=new EventSource('/brand/run/'+encodeURIComponent(b_name.value)+'?limit='+limit);
  window._brandES = es;
  es.onmessage=e=>{log.textContent+=e.data+'\n'; log.scrollTop=log.scrollHeight;};
  es.addEventListener('end',()=>{es.close(); if(stop) stop.style.display='none';});
}
async function brandStop(){
  try{ await fetch('/stop',{method:'POST'}); }catch(e){}
  if(window._brandES){ window._brandES.close(); }
  const log=document.getElementById('brandlog'); if(log) log.textContent+='\n[stopped by user]\n';
  const stop=document.getElementById('b_stopbtn'); if(stop) stop.style.display='none';
}
async function connLoad(){
  const c=await (await fetch('/brand/connection')).json();
  c_auth.value=c.auth_method||'service_account'; c_sa.value=c.service_account_json||'service_account.json';
  c_drive.value=c.claims_docs_drive_url||''; c_label.value=c.label||'Owner (default)';
}
async function connSave(){
  const body={auth_method:c_auth.value, service_account_json:c_sa.value,
    claims_docs_drive_url:c_drive.value, label:c_label.value};
  const r=await (await fetch('/brand/connection',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)})).json();
  await uiAlert(r.ok?'Connection saved.':'Error: '+(r.error||'?'));
}
function brandInit(){ brandRefresh(); setTone(null,'en'); brandLoadLogicFlag(); }
window.brandInit = brandInit;
window.brandRefresh = brandRefresh;
async function brandRemoveFromAccount(name){
  if(!await uiConfirm('Remove "'+name+'" from this account?\n\nThis unassigns the trademark from this workspace. (The brand profile itself is kept and can be re-added later.)')) return;
  try{
    const r=await (await fetch('/accounts/remove_brand',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brand:name})})).json();
    if(!r.ok){ await uiAlert('Could not remove: '+(r.error||'?')); return; }
    if(window.ACCOUNTS && window.CUR_ACCOUNT){ /* refresh local copy */ }
    brandRefresh();
  }catch(e){ await uiAlert('Error: '+e); }
}
window.brandRemoveFromAccount = brandRemoveFromAccount;
function _bfileToDataURL(file){return new Promise(function(res,rej){var fr=new FileReader();fr.onload=function(){res(fr.result);};fr.onerror=rej;fr.readAsDataURL(file);});}
async function uploadBrandRef(input){
  var file=input.files&&input.files[0]; if(!file) return;
  var brand=(document.getElementById('b_name')||{}).value||(window.WS_BRAND||'brand');
  var prev=document.getElementById('b_mainimgref_prev');
  if(prev) prev.innerHTML='<span class="cc">Uploading…</span>';
  try{
    var dataUrl=await _bfileToDataURL(file);
    var res=await fetch('/media/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({sku:'_brand_'+brand,data:dataUrl,name:file.name,kind:'brandref'})});
    var j=await res.json();
    if(!j.ok){ if(prev) prev.innerHTML='<span class="cc" style="color:var(--red)">Upload failed: '+(j.error||'')+'</span>'; return; }
    document.getElementById('b_mainimgref').value=j.url;
    if(prev) prev.innerHTML='<img src="'+j.url+'" style="max-width:120px;border-radius:8px;border:1px solid var(--line);margin-top:6px"><div class="cc">\u2713 uploaded \u2014 remember to Save brand</div>';
  }catch(e){ if(prev) prev.innerHTML='<span class="cc" style="color:var(--red)">Error: '+e+'</span>'; }
}
window.uploadBrandRef = uploadBrandRef;
