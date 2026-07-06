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

