/* static/js/pdp_imagegen.js -- the PDP Images tab's generator: four presets.
 *
 * THE OWNER'S CHOICE ("Idea 1: Presets", PDP_REDESIGN_SPEC.md, 26 Sep 2026):
 *
 *   [Main image] [3 variations] [Secondary set] [A+ content]
 *   ▸ Add instructions (optional)          -- collapsed until wanted
 *   <image model> · results fill empty slots above
 *
 * One click starts generating from the listing's current reference picture.
 * The full Image Studio form -- reference box, two model pickers, fidelity --
 * is NOT drawn here; it is still one sidebar click away, on its own page.
 *
 * NOTHING HERE IS A SECOND GENERATOR (Rule 12). Each button builds exactly the
 * jobs Image Studio's own buttons build (static/js/genimage.js) and hands them
 * to the same /genimage/start_batch, which saves every finished picture to the
 * listing's media library:
 *
 *   Main image      one "creative" job, the hero_straight strategy
 *   3 variations    the three creative strategies studioRun() runs
 *   Secondary set   the strategist (/genimage/strategize, kind secondary,
 *                   7 concepts), then its concept jobs -- _conceptJobs's shape
 *   A+ content      the strategist for A+ at the basic tier (5 modules)
 *
 * WHERE THE RESULTS GO. Into EMPTY slots only, never over a picture someone
 * chose: a new main picture into Main if it is empty, a secondary set into the
 * empty PT slots in order. Three variations are alternatives for one slot, so
 * they are not placed -- pick one from the Library tab. A+ modules are not
 * listing images at all and stay in the library. Everything is in the library
 * either way.
 *
 * EVERY RUN IS A PAID CALL, AND SAYS SO FIRST -- the count, before anything
 * starts, the way studioGenAllConcepts does.
 */

let PDPIG = {sku: "", running: false, job: "", model: "", modelAsked: false};

const PDPIG_PRESETS = [
  {key: "main",       icon: "ti-photo",       label: "Main image"},
  {key: "variations", icon: "ti-layout-grid", label: "3 variations"},
  {key: "secondary",  icon: "ti-photo-bolt",  label: "Secondary set"},
  {key: "aplus",      icon: "ti-sparkles",    label: "A+ content"},
];

/* The configured image model's name, for the status line. Read from
 * /ai/settings -- the call Image Studio fills its own picker from -- so this
 * never claims a model the app is not using. */
async function _pdpigLoadModel(){
  if(PDPIG.modelAsked) return;
  PDPIG.modelAsked = true;
  try{
    const s = await (await fetch("/ai/settings")).json();
    if(!s || !s.ok) return;
    const id = (s.select && s.select.image_generate) || "";
    const m = (s.image_models || []).find(function(x){ return x.id === id; });
    PDPIG.model = (m && (m.name || m.id)) || id || "";
    const el = document.getElementById("pdpig_model");
    if(el) el.textContent = PDPIG.model || "image model not set";
  }catch(e){}
}

function pdpImgGenSection(r){
  setTimeout(_pdpigLoadModel, 0);
  const busy = PDPIG.running && PDPIG.sku === String(r.sku);
  return '<div class="pdp-gen pdpig" id="pdpig">'
    + '<div class="pdpi-sechead"><span class="pdpi-sect">Image Studio</span>'
    +   '<span class="pdpi-secsub">one click generates</span></div>'
    + '<div class="pdpig-presets">' + PDPIG_PRESETS.map(function(p){
        return '<button class="pdpig-btn" onclick="pdpImgGenRun(\'' + p.key + '\')"'
             + (busy ? " disabled" : "") + '><i class="ti ' + p.icon + '"></i> '
             + esc(p.label) + '</button>';
      }).join("") + '</div>'
    + '<a class="pdpig-more" onclick="pdpImgGenToggle(this)"><i class="ti ti-chevron-right"></i>'
    +   ' Add instructions (optional)</a>'
    + '<div class="pdpig-instr" id="pdpig_instrbox" style="display:none">'
    +   '<textarea id="pdpig_instr" rows="2" placeholder="e.g. no people, close-up of texture, soft shadow, white background"></textarea>'
    +   '<div class="pdpig-sub">Instructions apply to whichever button you click next.</div>'
    + '</div>'
    + '<div class="pdpig-model"><i class="ti ti-check"></i> <span id="pdpig_model">'
    +   esc(PDPIG.model || "…") + '</span> · results fill empty slots above</div>'
    + '<div class="pdpig-status" id="pdpig_status"></div>'
    + '</div>';
}

function pdpImgGenToggle(a){
  const box = document.getElementById("pdpig_instrbox");
  if(!box) return;
  const open = box.style.display === "none";
  box.style.display = open ? "" : "none";
  const i = a && a.querySelector(".ti");
  if(i) i.style.transform = open ? "rotate(90deg)" : "";
}

function _pdpigSay(html){
  const el = document.getElementById("pdpig_status");
  if(el) el.innerHTML = html;
}

/* The instructions for THIS click, then cleared -- they are for the next
 * button, not every button after it. */
function _pdpigTakeInstructions(){
  const ta = document.getElementById("pdpig_instr");
  const v = ta ? String(ta.value || "").trim() : "";
  if(ta) ta.value = "";
  return v;
}

/* The two creative jobs' shape, exactly studioRun's. */
function _pdpigCreativeJobs(r, ref, strategies, instr){
  return strategies.map(function(strat){
    return {sku: r.sku, ref: ref, label: strat.replace(/_/g, " "),
            payload: {product_image: ref, title: r.title || "",
                      text_provider: (window.AI_TEXT || null),
                      image_provider: (window.AI_IMAGE || null),
                      fidelity: "high", mode: "creative", strategy: strat,
                      inspiration: instr}};
  });
}

/* The strategist's concepts turned into jobs -- _conceptJobs's shape, for one
 * SKU. */
function _pdpigConceptJobs(r, ref, concepts, kind, instr){
  return concepts.map(function(c){
    const slot = c.slot || c.n || 0;
    return {sku: r.sku, ref: ref, label: (slot ? slot + ". " : "") + (c.title || "idea"),
            slot: slot, why: (c.why_here || c.why || ""), role: (c.role || ""),
            payload: {product_image: ref, title: r.title || "", kind: kind,
                      concept: c.concept || "", art_direction: c.art_direction || "",
                      fidelity: "high", custom_instructions: instr,
                      tier: "basic",
                      text_provider: (window.AI_TEXT || null),
                      image_provider: (window.AI_IMAGE || null)}};
  });
}

async function pdpImgGenRun(preset){
  const r = (typeof pdpRow === "function") ? pdpRow() : null;
  if(!r) return;
  if(PDPIG.running){ toast("A generation is already running for this listing."); return; }
  // The reference picture, found the way Image Studio finds it.
  const ref = (typeof _refImgForItem === "function") ? _refImgForItem(r) : "";
  if(!ref){
    toast("No reference picture — put one in the Main slot first.");
    return;
  }
  const instr = _pdpigTakeInstructions();
  const sku = String(r.sku);

  let kind = "creative", jobs = [];
  if(preset === "main"){
    jobs = _pdpigCreativeJobs(r, ref, ["hero_straight"], instr);
  } else if(preset === "variations"){
    jobs = _pdpigCreativeJobs(r, ref, ["hero_straight", "hero_angle", "hero_personality"], instr);
  } else {
    // The strategist first: it reads the listing and designs the set.
    const sKind = (preset === "aplus") ? "aplus" : "secondary";
    _pdpigSay('<span class="genspin"></span> Designing the ' + (sKind === "aplus" ? "A+ modules" : "secondary set") + '…');
    try{
      const j = await (await fetch("/genimage/strategize", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({product_image: ref,
          product_images: (typeof _refCandidates === "function") ? _refCandidates(r) : [ref],
          title: r.title || "", sku: sku, listing: r, kind: sKind,
          n: (sKind === "aplus" ? 5 : 7), text_provider: (window.AI_TEXT || null),
          custom_instructions: instr})})).json();
      if(!j || !j.ok || !(j.concepts || []).length){
        _pdpigSay('<span class="bad">' + esc((j && j.error) || "No ideas came back — try again.") + '</span>');
        return;
      }
      kind = "concept";
      jobs = _pdpigConceptJobs(r, ref, j.concepts, sKind, instr);
    }catch(e){ _pdpigSay('<span class="bad">' + esc(String(e)) + '</span>'); return; }
  }

  // THE COUNT, BEFORE ANY MONEY IS SPENT.
  const what = {main: "main image", variations: "main-image variation",
                secondary: "secondary image", aplus: "A+ module"}[preset] || "image";
  if(!await uiConfirm("Generate " + jobs.length + " " + what + (jobs.length === 1 ? "" : "s")
        + " for this listing?\n\nEach one is a paid call.")){ _pdpigSay(""); return; }
  if(typeof confirmIfExisting === "function" && !await confirmIfExisting([sku], "images")){
    _pdpigSay(""); return;
  }

  // What was in the library before, so the new pictures can be told apart.
  const before = {};
  ((typeof PDPI !== "undefined" && PDPI.library) || []).forEach(function(f){ before[f.url] = 1; });

  let resp;
  try{
    resp = await (await fetch("/genimage/start_batch", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({kind: kind, jobs: jobs, label: "PDP " + what})})).json();
  }catch(e){ _pdpigSay('<span class="bad">Could not start: ' + esc(String(e)) + '</span>'); return; }
  if(!resp || !resp.ok){ _pdpigSay('<span class="bad">' + esc((resp && resp.error) || "failed to start") + '</span>'); return; }

  PDPIG.running = true; PDPIG.sku = sku; PDPIG.job = resp.job;
  _pdpigSetBusy(true);
  _pdpigSay('<span class="genspin"></span> Generating 0/' + jobs.length + '…');
  let polling = false;
  const t = setInterval(async function(){
    if(polling) return;
    polling = true;
    try{
      const st = await (await fetch("/genimage/job_status?job=" + encodeURIComponent(resp.job))).json();
      if(!st || !st.ok) return;
      if(st.status === "running"){
        _pdpigSay('<span class="genspin"></span> Generating ' + st.done + '/' + st.total + '…');
        return;
      }
      clearInterval(t);
      PDPIG.running = false;
      _pdpigSetBusy(false);
      const okN = (st.results || []).filter(function(x){ return x.ok; }).length;
      const placed = await _pdpigPlace(sku, preset, before);
      _pdpigSay('<span class="ok"><i class="ti ti-check"></i> ' + okN + '/' + st.total + ' made'
        + (placed ? " · " + placed + " put into empty slots" : "")
        + ' · all saved to Library.</span>'
        + (st.error ? ' <span class="bad">' + esc(st.error) + '</span>' : ""));
    }catch(e){}
    finally{ polling = false; }
  }, 2000);
}

function _pdpigSetBusy(on){
  document.querySelectorAll("#pdpig .pdpig-btn").forEach(function(b){ b.disabled = !!on; });
}

/* Re-read the library and put the NEW pictures into empty slots -- the rule at
 * the top of this file. Returns how many were placed. */
async function _pdpigPlace(sku, preset, before){
  if(typeof PDPI === "undefined" || PDPI.sku !== sku) return 0;
  if(typeof _pdpiLoadLibrary === "function") await _pdpiLoadLibrary();
  const fresh = (PDPI.library || []).map(function(f){ return f.url; })
                  .filter(function(u){ return !before[u]; });
  let placed = 0;
  if(preset === "main" || preset === "secondary"){
    const free = (typeof _pdpiEmptySlots === "function") ? _pdpiEmptySlots() : [];
    const targets = free.filter(function(s){
      const isMain = s.key === "main_product_image_locator";
      return preset === "main" ? isMain : !isMain;
    });
    for(let i = 0; i < targets.length && i < fresh.length; i++){
      if(await pdpImgAssign(targets[i].key, fresh[i], {quiet: true})) placed++;
    }
  }
  PDPI.compTab = "library";
  if(placed && typeof pdpRender === "function") pdpRender();
  else if(typeof _pdpiPaint === "function") _pdpiPaint();
  return placed;
}
