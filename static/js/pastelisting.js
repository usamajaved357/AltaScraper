// ---- Paste a listing -> Image Studio -----------------------------------------
// Enter a listing's copy (title, bullet points, description) by hand and give a main
// image (paste a URL or upload a file), then hand it straight to Image Studio to
// generate secondary images and A+ content. No sheet row is created — this is a
// scratch item, exactly like the ASIN-research handoff. Reuses /media/upload to host
// an uploaded image and the existing STUDIO object the studio already understands.

let _PL_IMG = "";   // resolved main-image URL (pasted or uploaded)

function openPasteListing(){
  if(document.getElementById("pastelistingwrap")) return;
  _PL_IMG = "";
  const dlg = document.createElement("div");
  dlg.className = "modalwrap open"; dlg.id = "pastelistingwrap"; dlg.style.zIndex = "130";
  dlg.innerHTML = `<div class="modal" style="max-width:660px;position:relative">
    <button class="x" onclick="closePasteListing()">×</button>
    <h3><i class="ti ti-clipboard-text"></i> Paste a listing → Image Studio</h3>
    <div class="cc" style="margin:2px 0 12px">Paste the copy and give a main image, then open Image Studio to generate secondary images and A+ content. This does not create a sheet row — it's a one-off item just for the studio.</div>
    <div class="pl-grid">
      <label class="pl-lbl">Product name / SKU <span class="cc">(optional — used to file the generated images)</span></label>
      <input id="pl_sku" class="pl-in" placeholder="e.g. my-product-01" autocomplete="off">
      <label class="pl-lbl">Title</label>
      <input id="pl_title" class="pl-in" placeholder="Full product title" autocomplete="off">
      <label class="pl-lbl">Bullet points <span class="cc">(one per line)</span></label>
      <textarea id="pl_bullets" class="pl-in" rows="5" placeholder="First bullet&#10;Second bullet&#10;Third bullet…"></textarea>
      <label class="pl-lbl">Description <span class="cc">(optional)</span></label>
      <textarea id="pl_desc" class="pl-in" rows="4" placeholder="Product description"></textarea>
      <label class="pl-lbl">Main image <span class="cc">(Image Studio uses this as the reference)</span></label>
      <div class="pl-img">
        <input id="pl_imgurl" class="pl-in" placeholder="Paste an image URL, or upload →" oninput="_plPreview(this.value)" autocomplete="off">
        <button type="button" class="mktbtn" onclick="document.getElementById('pl_imgfile').click()"><i class="ti ti-upload"></i> Upload</button>
        <input type="file" id="pl_imgfile" accept="image/*" style="display:none" onchange="_plFile(this)">
      </div>
      <div id="pl_preview" class="pl-preview"></div>
    </div>
    <div class="pl-actions">
      <button type="button" class="mktbtn" onclick="closePasteListing()">Cancel</button>
      <button type="button" class="mktbtn on" id="pl_go" onclick="pasteToStudio()"><i class="ti ti-photo"></i> Open in Image Studio</button>
    </div>
  </div>`;
  document.body.appendChild(dlg);
  setTimeout(()=>{ const t=document.getElementById("pl_title"); if(t) t.focus(); }, 50);
}

function closePasteListing(){ const w=document.getElementById("pastelistingwrap"); if(w) w.remove(); }

function _plPreview(url){
  _PL_IMG = String(url||"").trim();
  const p = document.getElementById("pl_preview");
  if(p) p.innerHTML = _PL_IMG ? `<img src="${esc(_PL_IMG)}" onerror="this.style.display='none';this.parentNode.innerHTML='<span class=\\'cc\\'>Could not load that image URL.</span>'">` : "";
}

function _plFile(inp){
  const f = inp && inp.files && inp.files[0];
  if(!f) return;
  if(!/^image\//.test(f.type||"")){ toast("Please choose an image file"); inp.value=""; return; }
  const rd = new FileReader();
  rd.onload = async () => {
    const p = document.getElementById("pl_preview");
    if(p) p.innerHTML = '<div class="cc"><span class="genspin"></span> Uploading…</div>';
    try{
      const sku = ((document.getElementById("pl_sku")||{}).value || "pasted-item").trim() || "pasted-item";
      const up = await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, data:rd.result, name:f.name, kind:"main"})})).json();
      if(!up || !up.ok){ toast("Upload failed: "+((up&&up.error)||"unknown")); if(p) p.innerHTML=""; return; }
      const pub = up.drive_direct_url || up.url || "";
      if(!pub){ toast("Uploaded, but no public URL — set the account's Drive folder, or paste an image URL instead."); if(p) p.innerHTML=""; return; }
      const urlbox = document.getElementById("pl_imgurl"); if(urlbox) urlbox.value = pub;
      _plPreview(pub);
      toast("Image uploaded ✓");
    }catch(e){ toast("Upload error: "+((e&&e.message)||e)); }
    finally{ if(inp) inp.value=""; }
  };
  rd.readAsDataURL(f);
}

function pasteToStudio(){
  const g = id => (document.getElementById(id)||{}).value || "";
  const title = g("pl_title").trim();
  const bullets = g("pl_bullets").split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  const desc = g("pl_desc").trim();
  let sku = g("pl_sku").trim();
  const img = _PL_IMG || g("pl_imgurl").trim();
  if(!title){ toast("Add a title first"); const t=document.getElementById("pl_title"); if(t) t.focus(); return; }
  if(!img){ toast("Add a main image (paste a URL or upload) — Image Studio needs it as the reference"); return; }
  if(!sku){
    sku = "paste-" + (title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,32) || "item");
  }
  if(typeof STUDIO==="undefined" || typeof renderStudio!=="function"){ toast("Image Studio isn't available on this screen."); return; }
  // Seed the studio exactly like the ASIN-research handoff: one item carrying the copy +
  // the main image as the reference (source_image/img/manualRef all point at it).
  STUDIO = {
    skus: [sku],
    items: [{ sku:sku, title:title, bullets:bullets, description:desc,
              source_image:img, images:[img], img:img }],
    brand: (typeof CUR_ACCOUNT!=="undefined" && CUR_ACCOUNT && CUR_ACCOUNT.brands && CUR_ACCOUNT.brands.length
            ? CUR_ACCOUNT.brands[0]
            : (typeof CUR_ACCOUNT!=="undefined" && CUR_ACCOUNT ? CUR_ACCOUNT.label : "")),
    manualRef: img, recipes: [], results: {}
  };
  closePasteListing();
  _studioShow();   // its own screen now, not a modal over Listings
  if(typeof loadRecipes==="function"){ loadRecipes().then(()=>{ try{ renderStudio(); }catch(e){} }); }
  else { try{ renderStudio(); }catch(e){} }
  if(typeof studioLoadModels==="function") studioLoadModels();
  if(typeof loadStudioInstructions==="function") loadStudioInstructions();
  toast("Opened Image Studio — pick a model and generate secondary images / A+.");
}
