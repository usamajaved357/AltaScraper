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
// Render one raw log line, colour-coded by kind so the error + its reason stand out
// in the otherwise dense stream: red = Amazon error, amber = ignorable warning,
// grey = plumbing/progress, green = success.
function _logLineEl(d){
  const s=String(d==null?"":d);
  const div=document.createElement("div");
  div.textContent=s;
  div.style.whiteSpace="pre-wrap"; div.style.padding="1px 0";
  if(/\[E\]|NOT live|invalid attribute value|does not match any ASIN|not in the catalog|cannot be added|\b\d+\s+(?:error|issue)\(s\)/i.test(s)){
    div.style.color="#ff6b6b"; div.style.fontWeight="700"; div.style.borderLeft="3px solid #ff6b6b";
    div.style.paddingLeft="8px"; div.style.margin="6px 0"; div.style.background="rgba(255,107,107,.07)";
  } else if(/\[W\]|We are ignoring|warning/i.test(s)){
    div.style.color="#e3b768";
  } else if(/\[start\]|\[done\]|API mode:|seller:|fetching schema|MODE:|Listing Generator|complete --/i.test(s)){
    div.style.color="#7f8ea3";
  } else if(/LIVE \(|Amazon accepted|no missing|accepted this listing|Published live/i.test(s)){
    div.style.color="#5fd08a"; div.style.fontWeight="600";
  } else {
    div.style.color="#cfe0ff";
  }
  return div;
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
    if(P){ P.log.appendChild(_logLineEl(d)); P.log.scrollTop=P.log.scrollHeight; }
    if(d.indexOf("[busy]")>=0){ verdict={kind:"busy", raw:d}; }
    if(d.startsWith("[start]")){ sawStart=true; if(P) P.verdict.innerHTML='<span class="rspin"></span> Request sent to Amazon… waiting for response.'; }
    // parse the per-row result line for THIS sku
    if(d.indexOf(sku)>=0){
      const low=d.toLowerCase();
      // count "N error(s)" OR "N issue(s)" -- submit prints "NOT live -- 2 issue(s)"
      let m=d.match(/(\d+)\s+(?:error|issue)\(s\)/i);
      if(m){ verdict={kind:"error", n:parseInt(m[1]), raw:d}; }
      // "NOT live" CONTAINS the word "live" -- it must be caught as an ERROR *before*
      // the "live" success check below, or a failed submit falsely reads "Published live".
      else if(low.indexOf("not live")>=0 || low.indexOf("api call failed")>=0 || low.indexOf("api_error")>=0){ verdict={kind:"error", n:0, raw:d}; }
      else if(low.indexOf("missing")>=0 && low.indexOf("skip")>=0){ verdict={kind:"missing", raw:d}; }
      else if(low.indexOf("api_ready")>=0 || low.indexOf("preview clean")>=0){ verdict={kind:"ok_preview", raw:d}; }
      else if(low.indexOf("live")>=0 || low.indexOf("submitted")>=0){ verdict={kind:"ok_submit", raw:d}; }
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
      // Pull Amazon's ACTUAL error detail lines (the [E] lines) straight from the
      // stream, so we show Amazon's OWN words verbatim -- not our paraphrase. This is
      // how you can be sure it's Amazon rejecting, not the app claiming it is.
      const _eLines=lines.filter(x=>/\[E\]/.test(x))
                         .map(x=>x.replace(/^[^[]*\[E\]\s*/,"").replace(/\s+/g," ").trim())
                         .filter(Boolean);
      const _eText=_eLines.join("  •  ");
      const _allText=lines.join(" ");
      // Amazon rejected the product barcode / identifier for creating a new ASIN.
      // "Suggest missing fields" CANNOT fix this -- the barcode itself is invalid, so
      // tell the truth and offer the two real options (replace it, or use exemption).
      if(/standard_product_id|externally_assigned_product_identifier|does not match any ASIN|not in the catalog/i.test(_allText)){
        P.verdict.innerHTML='<div class="rbad">✗ Amazon REJECTED your barcode (GTIN / EAN).</div>'
          +'<div class="rmsg"><b>This is Amazon’s response, word for word:</b></div>'
          +'<div class="ramz">'+esc(_eText||verdict.raw)+'</div>'
          +'<div class="rmsg"><b>Why:</b> Amazon won’t accept this barcode to create a new listing. Purchased / reseller EANs aren’t GS1-registered to your brand, so Amazon’s GS1 check rejects them.</div>'
          +'<div class="rhint"><b>Two ways forward:</b><br>'
          +'&nbsp;&nbsp;<b>1) Replace it</b> — put a different purchased EAN in the <b>Barcode / GTIN</b> box above, then Preview again.<br>'
          +'&nbsp;&nbsp;<b>2) Use the GTIN exemption</b> — <b>empty</b> the Barcode / GTIN box and Preview; the app claims the exemption instead (needs GTIN-exemption approval for this brand + category in Seller Central).</div>';
        return;
      }
      const msg=esc(_eText||verdict.raw.replace(/^.*error\(s\)\)?/i,"").trim()||verdict.raw);
      P.verdict.innerHTML='<div class="rbad">✗ Amazon did NOT accept this listing — '+(verdict.n||"")+' issue(s).</div>'
        +'<div class="rmsg"><b>Amazon’s response, word for word:</b></div><div class="ramz">'+msg+'</div>'
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
// loadViews() is invoked at DOMContentLoaded (in settings.js) so every file's helpers
// (e.g. _fetchJSON in shell.js) are already defined -- calling it here at script-load
// time ran before shell.js loaded and threw "ReferenceError: _fetchJSON is not defined".
async function loadRows(){
  try{
    const j=await _fetchJSON("/rows", null, 20000);
    if(!j || j._failed){ toast("Could not load listings: "+((j&&j.error)||"timeout")); return; }
    if(!j.ok){
      // This workspace has no sheet/tab configured. The app deliberately refuses to
      // fall back to the shared default tab (it holds another account's listings), so
      // say so plainly and send the user to the one place that fixes it.
      if(j.sheet_scope_error){
        ROWS=[];
        const g=document.getElementById("grid");
        if(g) g.innerHTML=`<div class="empty" style="border:1px solid #5c2424;border-radius:10px;background:rgba(255,80,80,.05)">
          <div style="color:#ff8a8a;font-weight:600;margin-bottom:8px"><i class="ti ti-alert-triangle"></i> This workspace has no sheet configured</div>
          <div class="cc" style="max-width:620px;margin:0 auto 12px;line-height:1.5">${esc(j.error||"")}</div>
          <button class="mktbtn on" onclick="openCurrentAccountSettings()">Open Account &amp; sheets</button></div>`;
        const s=document.getElementById("summary"); if(s) s.innerHTML="";
        return;
      }
      toast("Sheet error: "+(j.error||"unknown")); return;
    }
    ROWS=j.rows||[]; SHIP=j.shipping_group||""; PTYPES=j.product_types||[];
    // /rows reports the tab it ACTUALLY opened -- trust that over what config claims.
    if(j.source && j.source.sheet_id && typeof WS_SOURCE!=="undefined" && WS_SOURCE){
      WS_SOURCE.out_id=j.source.sheet_id;
      WS_SOURCE.out_gid=j.source.tab_gid||"";
      WS_SOURCE.out_tab=j.source.tab||"";
      if(typeof renderDataSource==="function") renderDataSource();
    }
    render();
    const pts=[...new Set(ROWS.map(r=>r.product_type).filter(Boolean))];
    try{ await loadSchemas(pts); }catch(e){}
    render();
  }catch(e){ toast("Could not load: "+e); }
}
// loadRows() is invoked at DOMContentLoaded (in settings.js) -- see note above.

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

