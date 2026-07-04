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

