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

// Where you are, out of how many. Three named steps beat a screen that changes
// under you with no indication that it was ever going to.
const VAR_STEPS = ["Pick the products", "Say what differs", "Check and join"];

function _varSteps(now){
  let h = '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;'
        + 'margin:0 0 12px">';
  VAR_STEPS.forEach(function(t, i){
    const n = i + 1, on = n === now, done = n < now;
    h += '<span style="display:inline-flex;align-items:center;gap:5px;'
      +  'font-size:11.5px;padding:4px 9px;border-radius:20px;'
      +  (on ? 'background:var(--accent);color:#fff;font-weight:600'
            : done ? 'border:1px solid var(--ok,#8fd694);color:var(--ok,#8fd694)'
                   : 'border:1px solid #26303f;opacity:.6')
      +  '">' + (done ? '✓' : n) + ' ' + _vesc(t) + '</span>';
    if(n < VAR_STEPS.length) h += '<span class="cc" style="opacity:.4">→</span>';
  });
  return h + '</div>';
}

function variationsRender(q){
  const host = document.getElementById("varbody");

  // WHAT THIS SCREEN IS, before what to do on it.
  //
  // "Variation family", "parent", "theme" and "child" are Amazon's words, not
  // anybody's ordinary ones, and the screen used to open with all four and a
  // list of SKUs. Someone who has not met the concept cannot act on that. So:
  // one concrete example first, then numbered steps, then the list.
  h += '<div style="font-size:12.5px;margin:2px 0 12px;padding:11px 13px;'
    + 'border:1px solid #26303f;border-radius:8px;line-height:1.55">'
    + '<b>What this does.</b> If you sell the same product in several colours or '
    + 'sizes, each one is its own listing and they compete with each other — '
    + 'reviews and sales split between them. Joining them makes Amazon show '
    + '<i>one</i> product with a colour or size picker, and the reviews add up.'
    + '<div class="cc" style="margin-top:6px">'
    + 'Example: a ceiling fan in white and in black, listed separately, become one '
    + 'fan with a colour choice.</div>'
    + '<div class="cc" style="margin-top:6px">'
    + '<b>Nothing is sent to Amazon until you have seen exactly what would be.</b> '
    + 'Amazon accepts a half-finished family without complaining and the products '
    + 'then quietly stop showing up, so every check runs first.</div>'
    + '</div>';

  h += _varSteps(1);

  h += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">'
    + '<input id="varq" placeholder="Search your listings…" value="'+_vesc(q||"")+'" '
    + 'oninput="variationsFilter(this.value)" style="font-size:12px;padding:5px 8px;min-width:240px">'
    + '<span class="cc" style="font-size:11.5px">'+VARS.picked.length+' picked</span>'
    + (VARS.picked.length>=2
        ? '<button class="db-chip" style="background:var(--accent);color:#fff;'
          + 'border-color:var(--accent)" onclick="variationsStep2()">'
          + 'Next: say what makes them different →</button>'
        : '<span class="cc" style="font-size:11px">Tick at least two products that '
          + 'are the same thing in different colours or sizes.</span>')
    + '</div>';

  if(VARS.note){
    h += '<div class="cc" style="padding:14px;border:1px dashed #2a3446;border-radius:6px;font-size:12px">'
      + _vesc(VARS.note)+'</div>';
    host.innerHTML = h; return;
  }

  h += '<div style="max-height:360px;overflow:auto;border:1px solid #1c2531;border-radius:6px">';
  // ONCE ONE IS PICKED, ONLY ITS OWN KIND CAN JOIN IT.
  //
  // Amazon only groups products of the same type, and the screen let you tick a
  // ceiling light and a tow hitch and only objected three steps later, after
  // you had named the family and written a title. The rule is known up front,
  // so it belongs up front -- greyed out with the reason, not hidden, because
  // silently removing something you were looking for is its own confusion.
  const pickedType = (function(){
    if(!VARS.picked.length) return "";
    const first = (VARS.items||[]).filter(x => x.sku === VARS.picked[0])[0];
    return (first && first.product_type) || "";
  })();

  (VARS.items||[]).forEach(function(it){
    const on = VARS.picked.indexOf(it.sku) >= 0;
    const wrongType = !!(pickedType && it.product_type
                         && it.product_type !== pickedType && !on);
    const inFamily = !!it.parent_sku || wrongType;
    h += '<label style="display:flex;gap:9px;align-items:center;font-size:11.5px;'
      +  'padding:6px 8px;border-top:1px solid #1c2531;cursor:'+(inFamily?'not-allowed':'pointer')+';'
      +  (on?'background:#12222c':'')+'">'
      +  '<input type="checkbox" '+(on?'checked':'')+' '+(inFamily?'disabled':'')
      +  ' onchange="variationsPick('+jsArg(it.sku)+', this.checked)">'
      // Deciding two products are the same thing in different colours is a
      // VISUAL judgement. Doing it from SKUs like 10.06_3Days_B0081ZHHTS is
      // guesswork, and a wrong family does not fail loudly.
      +  (it.img
          ? '<img src="'+_vesc(it.img)+'" loading="lazy" alt="" '
            + 'style="width:40px;height:40px;object-fit:contain;background:#0d1220;'
            + 'border-radius:5px;flex:0 0 auto">'
          : '<span style="width:40px;height:40px;border-radius:5px;flex:0 0 auto;'
            + 'background:#0d1220;display:inline-block"></span>')
      +  '<span style="flex:1;min-width:0">'
      +  '<span style="display:block;overflow:hidden;text-overflow:ellipsis;'
      +  'white-space:nowrap" title="'+_vesc(it.title)+'">'
      +  _vesc(it.title||"(no title)")+'</span>'
      +  '<code class="cc" style="font-size:10px">'+_vesc(it.sku)+'</code></span>'
      +  (it.product_type ? '<span class="cc">'+_vesc(it.product_type)+'</span>' : '')
      +  (it.parent_sku
          ? '<span class="db-chip" style="opacity:.7" title="Amazon allows one parent per child">already in '+_vesc(it.parent_sku)+'</span>'
          : wrongType
            ? '<span class="db-chip" style="opacity:.7" title="Amazon only groups products of the same type, so this cannot join a '
              + _vesc(pickedType) + ' family">not a ' + _vesc(pickedType) + '</span>'
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

// Narrow the theme list as you type. Rebuilds the options rather than filtering
// the DOM, so the selected value survives and the counts stay honest.
function variationsThemeFilter(q){
  const sel = document.getElementById("var_theme");
  if(!sel) return;
  const want = String(q || "").trim().toUpperCase();
  const keep = want ? VARS.themes.filter(t => t.indexOf(want) >= 0) : VARS.themes;
  const cur = sel.value;
  sel.innerHTML = '<option value="">— choose —</option>'
    + keep.map(t => '<option value="'+_vesc(t)+'"'+(t===cur?' selected':'')+'>'
                    + _vesc(t)+'</option>').join("");
  if(want && !keep.length){
    sel.innerHTML = '<option value="">nothing matches “'+_vesc(q)+'”</option>';
  }
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

  // Ask by SKU as well as by type. The list this screen reads from does not
  // always carry a product type, and when it did not the request was simply
  // never made -- leaving an empty dropdown, no theme to pick, and no way
  // forward. The server can work the type out from the SKUs.
  let th = {themes: [], checked: false, note: ""};
  try{
    const qs = (pt ? "product_type=" + encodeURIComponent(pt) + "&" : "")
             + "skus=" + encodeURIComponent(VARS.picked.join(","));
    th = await (await fetch("/variations/themes?" + qs)).json();
    if(th && th.product_type && !pt) pt = th.product_type;
  }catch(e){}
  VARS.themes = th.themes || [];

  let h = _varSteps(2);
  h += '<div style="margin-bottom:10px"><button class="db-chip" onclick="variationsRender(\'\')">'
        + '← back to the list</button></div>';
  h += '<div style="border:1px solid #26303f;border-radius:8px;padding:12px;margin-bottom:12px">'
    + '<div style="font-weight:600;font-size:13px;margin-bottom:8px">'
    + VARS.picked.length+' products, '+_vesc(pt||"unknown type")+'</div>';

  if(th.note){
    h += '<div class="cc" style="font-size:12px;margin-bottom:10px;padding:8px 10px;'
      + 'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
      + '<i class="ti ti-alert-triangle"></i> '+_vesc(th.note)+'</div>';
  }

  h += '<div style="font-size:12px;font-weight:600;margin-bottom:2px">'
    + 'What is different between them?</div>'
    + '<div class="cc" style="font-size:11px;margin-bottom:5px">'
    + 'This is what shoppers will choose from — a colour picker, a size picker. '
    + 'Only the options Amazon allows for this kind of product are listed, because '
    + 'anything else is rejected or, worse, accepted and ignored.</div>';
  if(VARS.themes.length){
    // SEARCHABLE, because LIGHT_FIXTURE alone allows 774 of these. A dropdown
    // with 774 entries is a list you scroll past, not one you choose from —
    // and picking the wrong grouping is not a loud failure: Amazon accepts a
    // theme the products do not actually vary by and the family just does not
    // work.
    //
    // The common ones first: what most products actually differ by.
    const COMMON = ["COLOR", "SIZE", "COLOR/SIZE", "SIZE/COLOR", "STYLE",
                    "MATERIAL", "PATTERN", "COLOR/STYLE", "SIZE/STYLE"];
    const common = VARS.themes.filter(t => COMMON.indexOf(t) >= 0);
    h += '<input id="var_theme_q" placeholder="Type to narrow — colour, size…" '
      +  'oninput="variationsThemeFilter(this.value)" '
      +  'style="font-size:12px;padding:5px 8px;min-width:220px;margin-right:6px">'
      +  '<select id="var_theme" onchange="variationsPreview()" '
      +  'style="font-size:12px;padding:5px 8px;min-width:260px">'
      +  '<option value="">— choose —</option>'
      +  (common.length
          ? '<optgroup label="Most products differ by one of these">'
            + common.map(t => '<option value="'+_vesc(t)+'">'+_vesc(t)+'</option>').join("")
            + '</optgroup>'
          : '')
      +  '<optgroup label="Everything this product type allows ('
      +  VARS.themes.length + ')">'
      +  VARS.themes.map(t => '<option value="'+_vesc(t)+'">'+_vesc(t)+'</option>').join("")
      +  '</optgroup></select>';
  } else {
    h += '<input id="var_theme" placeholder="e.g. SIZE" onchange="variationsPreview()" '
      + 'style="font-size:12px;padding:5px 8px;min-width:220px">';
  }

  h += '<div style="font-size:12px;font-weight:600;margin:14px 0 2px">'
    + 'A code for the group itself</div>'
    + '<div class="cc" style="font-size:11px;margin-bottom:5px">'
    + 'Every family needs its own code, separate from the products in it. Nobody '
    + 'can buy this one — it exists to hold the others together. We suggest one; '
    + 'change it if you like. It is <b>permanent on Amazon</b> once created.</div>'
    + '<input id="var_parent" placeholder="parent SKU" style="font-size:12px;padding:5px 8px;min-width:260px">';

  h += '<div style="font-size:12px;font-weight:600;margin:14px 0 2px">'
    + 'The title shoppers see for the group</div>'
    + '<div class="cc" style="font-size:11px;margin-bottom:5px">'
    + 'Describe the product without the colour or size — those become the picker. '
    + '“Ceiling fan with light and remote”, not “…, white”.</div>'
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
