// ===================== VARIATION FAMILIES =====================
// Merge separate listings into one parent, so a shirt in six sizes reads as one
// product instead of six weak ones.
//
// The screen is built around one fact: Amazon accepts a HALF-FORMED family
// without complaint, and the products then quietly stop appearing in search.
// There is no error to react to. So nothing can be applied until every check has
// passed, the problems are listed in plain words rather than counted, and the
// preview shown IS the payload sent — the same builder produces both.

let VARS = {picked: [], theme: "", parentSku: "", themes: [], preview: null};

function _vesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function variationsOnOpen(){ VARS.picked = []; variationsLoad(""); }

async function variationsLoad(q){
  const host = document.getElementById("varbody");
  if(!host) return;
  host.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading listings…</div>';
  try{
    const j = await (await fetch("/variations/candidates?q="+encodeURIComponent(q||""))).json();
    if(!j || !j.ok){ host.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
      + _vesc((j&&j.error)||"Could not load")+'</div>'; return; }
    VARS.items = j.items || [];
    VARS.note = j.note || "";
    variationsRender(q||"");
  }catch(e){
    host.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_vesc(String(e))+'</div>';
  }
}

function variationsRender(q){
  const host = document.getElementById("varbody");
  let h = '<div class="cc" style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
    + 'border:1px solid #26303f;border-radius:6px">'
    + 'Pick the listings that are the same product in different sizes, colours or '
    + 'styles, say what makes them different, and they become one product on Amazon '
    + 'with a picker. <b>Nothing is sent until you have seen exactly what would be.</b>'
    + '</div>';

  h += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">'
    + '<input id="varq" placeholder="filter by SKU or title" value="'+_vesc(q||"")+'" '
    + 'oninput="variationsFilter(this.value)" style="font-size:12px;padding:5px 8px;min-width:240px">'
    + '<span class="cc" style="font-size:11.5px">'+VARS.picked.length+' selected</span>'
    + (VARS.picked.length>=2
        ? '<button class="db-chip" onclick="variationsStep2()">Next — describe the family</button>'
        : '<span class="cc" style="font-size:11px">pick at least two</span>')
    + '</div>';

  if(VARS.note){
    h += '<div class="cc" style="padding:14px;border:1px dashed #2a3446;border-radius:6px;font-size:12px">'
      + _vesc(VARS.note)+'</div>';
    host.innerHTML = h; return;
  }

  h += '<div style="max-height:360px;overflow:auto;border:1px solid #1c2531;border-radius:6px">';
  (VARS.items||[]).forEach(function(it){
    const on = VARS.picked.indexOf(it.sku) >= 0;
    const inFamily = !!it.parent_sku;
    h += '<label style="display:flex;gap:9px;align-items:center;font-size:11.5px;'
      +  'padding:6px 8px;border-top:1px solid #1c2531;cursor:'+(inFamily?'not-allowed':'pointer')+';'
      +  (on?'background:#12222c':'')+'">'
      +  '<input type="checkbox" '+(on?'checked':'')+' '+(inFamily?'disabled':'')
      +  ' onchange="variationsPick('+jsArg(it.sku)+', this.checked)">'
      +  '<code style="min-width:150px">'+_vesc(it.sku)+'</code>'
      +  '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '
      +  'title="'+_vesc(it.title)+'">'+_vesc(it.title||"(no title)")+'</span>'
      +  (it.product_type ? '<span class="cc">'+_vesc(it.product_type)+'</span>' : '')
      +  (inFamily
          ? '<span class="db-chip" style="opacity:.7" title="Amazon allows one parent per child">already in '+_vesc(it.parent_sku)+'</span>'
          : '')
      +  '</label>';
  });
  h += '</div>';
  host.innerHTML = h;
}

let _varTimer=null;
function variationsFilter(v){
  clearTimeout(_varTimer);
  _varTimer = setTimeout(function(){ variationsLoad(v); }, 200);
}

function variationsPick(sku, on){
  const i = VARS.picked.indexOf(sku);
  if(on && i < 0) VARS.picked.push(sku);
  if(!on && i >= 0) VARS.picked.splice(i, 1);
  variationsRender((document.getElementById("varq")||{}).value||"");
}

async function variationsStep2(){
  const host = document.getElementById("varbody");
  const first = (VARS.items||[]).find(x => x.sku === VARS.picked[0]) || {};
  const pt = first.product_type || "";
  host.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Reading what this product type allows…</div>';

  let th = {themes: [], checked: false, note: ""};
  if(pt){
    try{ th = await (await fetch("/variations/themes?product_type="+encodeURIComponent(pt))).json(); }
    catch(e){}
  }
  VARS.themes = th.themes || [];

  let h = '<div style="margin-bottom:10px"><button class="db-chip" onclick="variationsRender(\'\')">'
        + '← back to the list</button></div>';
  h += '<div style="border:1px solid #26303f;border-radius:8px;padding:12px;margin-bottom:12px">'
    + '<div style="font-weight:600;font-size:13px;margin-bottom:8px">'
    + VARS.picked.length+' products, '+_vesc(pt||"unknown type")+'</div>';

  if(th.note){
    h += '<div class="cc" style="font-size:12px;margin-bottom:10px;padding:8px 10px;'
      + 'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
      + '<i class="ti ti-alert-triangle"></i> '+_vesc(th.note)+'</div>';
  }

  h += '<div class="cc" style="font-size:11.5px;margin-bottom:4px">What makes them different?</div>';
  if(VARS.themes.length){
    h += '<select id="var_theme" style="font-size:12px;padding:5px 8px;min-width:220px">'
      + '<option value="">— pick one —</option>'
      + VARS.themes.map(t => '<option value="'+_vesc(t)+'">'+_vesc(t)+'</option>').join("")
      + '</select>';
  } else {
    h += '<input id="var_theme" placeholder="e.g. SIZE" style="font-size:12px;padding:5px 8px;min-width:220px">';
  }

  h += '<div class="cc" style="font-size:11.5px;margin:12px 0 4px">'
    + 'A code for the family itself — nobody buys this one</div>'
    + '<input id="var_parent" placeholder="parent SKU" style="font-size:12px;padding:5px 8px;min-width:260px">'
    + '<div class="cc" style="font-size:10.5px;margin-top:3px">Permanent on Amazon once created, so it is worth reading.</div>';

  h += '<div class="cc" style="font-size:11.5px;margin:12px 0 4px">'
    + 'The title shoppers see for the group</div>'
    + '<input id="var_title" placeholder="parent title" style="font-size:12px;padding:5px 8px;width:100%;max-width:560px">';

  h += '<div style="margin-top:14px"><button class="db-chip" onclick="variationsPreview()">'
    + 'Check it</button></div></div>';
  h += '<div id="varpreview"></div>';
  host.innerHTML = h;
  variationsPreview();          // fill the suggested parent SKU straight away
}

async function variationsPreview(){
  const out = document.getElementById("varpreview");
  if(!out) return;
  const theme = (document.getElementById("var_theme")||{}).value || "";
  const parent = (document.getElementById("var_parent")||{}).value || "";
  out.innerHTML = '<div class="cc" style="padding:10px"><span class="genspin"></span> Checking…</div>';
  let j;
  try{
    j = await (await fetch("/variations/preview",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({skus:VARS.picked, theme:theme, parent_sku:parent})})).json();
  }catch(e){ out.innerHTML='<div class="cc" style="color:var(--red)">'+_vesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){ out.innerHTML='<div class="cc" style="color:var(--red)">'+_vesc((j&&j.error)||"failed")+'</div>'; return; }
  VARS.preview = j;

  const pf = document.getElementById("var_parent");
  if(pf && !pf.value && j.parent_sku) pf.value = j.parent_sku;   // the suggestion

  let h = "";
  if(j.problems && j.problems.length){
    h += '<div style="border:1px solid #4a2323;background:#2a1212;border-radius:6px;padding:10px 12px;margin-bottom:10px">'
      + '<div style="font-weight:600;font-size:12.5px;color:#e88a8a;margin-bottom:5px">'
      + 'Not ready yet</div><ul style="margin:0;padding-left:18px;font-size:12px">'
      + j.problems.map(p => '<li style="margin:3px 0">'+_vesc(p)+'</li>').join("")
      + '</ul></div>';
  }

  if(j.payload && j.can_apply){
    const p = j.payload;
    h += '<div style="border:1px solid #26403a;background:#10231f;border-radius:6px;padding:10px 12px;margin-bottom:10px">'
      + '<div style="font-weight:600;font-size:12.5px;margin-bottom:6px">This is exactly what would be sent</div>'
      + '<div style="font-size:11.5px;margin-bottom:4px"><b>Parent</b> <code>'+_vesc(p.parent.sku)+'</code> '
      + '— created as the group. No price, no stock: those stay on the children.</div>'
      + '<div style="font-size:11.5px">'+p.children.length+' children join it, each grouped by <b>'
      + _vesc(p.theme)+'</b>:</div>'
      + '<div style="font-size:11.5px;margin-top:4px">'
      + p.children.map(c => '<code style="margin-right:8px">'+_vesc(c.sku)+'</code>').join("")
      + '</div></div>';
    h += '<button class="db-chip" style="background:var(--accent);color:#fff;border-color:var(--accent)" '
      + 'onclick="variationsApply()">Create the family on Amazon</button>'
      + '<span id="var_applystatus" class="cc" style="margin-left:8px;font-size:11.5px"></span>';
  }
  out.innerHTML = h;
}

async function variationsApply(){
  const st = document.getElementById("var_applystatus");
  const theme = (document.getElementById("var_theme")||{}).value || "";
  const parent = (document.getElementById("var_parent")||{}).value || "";
  const title = (document.getElementById("var_title")||{}).value || "";
  if(!confirm("Create this family on Amazon?\n\nThe parent listing is created "
            + "first, then each product is joined to it. Splitting a family up "
            + "again afterwards is fiddly, so it is worth being sure.\n\n"
            + "Amazon publishes variations asynchronously — it usually shows "
            + "within a few minutes.")) return;
  if(st) st.innerHTML = '<span class="genspin"></span> creating the parent…';
  try{
    const j = await (await fetch("/variations/apply",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirmed:true, skus:VARS.picked, theme:theme,
                           parent_sku:parent, parent_title:title})})).json();
    if(!j.ok && j.stage === "parent"){
      if(st) st.innerHTML = '<span style="color:var(--red)">The parent was rejected, '
                          + 'so nothing else was sent: '+_vesc(j.error)+'</span>';
      return;
    }
    if(j.failed && j.failed.length){
      if(st) st.innerHTML = '<span style="color:var(--warn)">Parent created, '
        + (j.joined||[]).length+' joined, '+j.failed.length+' rejected: '
        + _vesc(j.failed.map(f => f.sku+" ("+f.error+")").join("; "))+'</span>';
      return;
    }
    if(st) st.innerHTML = '<span style="color:var(--ok)">✓ family created — '
      + (j.joined||[]).length+' products joined. '+_vesc(j.note||"")+'</span>';
  }catch(e){
    if(st) st.innerHTML = '<span style="color:var(--red)">'+_vesc(String(e))+'</span>';
  }
}
