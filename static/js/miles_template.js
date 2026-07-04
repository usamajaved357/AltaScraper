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

