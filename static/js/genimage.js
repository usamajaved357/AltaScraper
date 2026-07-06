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
