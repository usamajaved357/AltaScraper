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

