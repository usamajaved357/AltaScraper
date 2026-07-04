// ============================================================
// "HOW IT WORKS" LOGIC FRAMEWORK (admin-visible transparency layer)
// One central registry + one helper. To document any feature anywhere in the
// app, add an entry to LOGIC_REGISTRY and drop ${howWorks('key')} after its button.
// Visibility is gated: admin sees panels when LOGIC_VISIBLE is true; a non-admin
// (or admin in "preview as user" mode) sees nothing.
// ============================================================
window.LOGIC_VISIBLE = true;      // set from /ai/settings admin flags on load
function _mdl(){
  var f=((document.getElementById("studio_fidelity")||{}).value||"high");
  return { C:(window.AI_IMAGE||"your image model"), T:(window.AI_TEXT||"your prompt model"),
    fid:f, strn:(f==="high"?"0.2":(f==="medium"?"0.35":"0.55")) };
}
function LOGIC_REGISTRY(){
  const {C,T,strn} = _mdl();
  return {
    strategist: { title:"How the AI strategist works", steps:[
      `<b>Reads your real product.</b> Your product image goes to the prompt AI (<code>${esc(T)}</code>) for a forensic read — shape, proportions, material, exact colours/gradient, every line of label text, the logo — producing a written spec.`,
      `<b>Thinks like a strategist + customer.</b> That spec + your title go to <code>strategize_images</code>, prompted to reason as an Amazon conversion expert and as your buyer. It invents 3 concepts: <i>customer insight</i>, <i>concept</i>, <i>art direction</i>.`,
      `<b>You pick.</b> Nothing is generated yet — you choose one idea or "Generate all".`,
      `<b>Generates faithfully.</b> The art direction runs through <code>run_pipeline</code> → <code>from_concept</code>: your product image attached as reference, image AI (<code>${esc(C)}</code>) renders at <b>strength ${strn}</b> (low = stay close), <b>4K, pure white</b>.`,
      `<b>Auto-saves</b> each finished image to this product's media library immediately.` ]},
    ready3: { title:"How the 3 ready-made variations work", steps:[
      `<b>No idea-invention step</b> — uses 3 fixed treatments: straight-on hero, flattering angle, creative "personality" shot.`,
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec, folded into each brief so the product can't drift.`,
      `<b>Writes the prompt.</b> <code>enhance_prompt</code> turns each treatment + spec into a detailed prompt with strict pure-white-background rules.`,
      `<b>Generates with your product as reference.</b> Image AI (<code>${esc(C)}</code>) renders each at <b>strength ${strn}, 4K, 1:1 pure white</b>.`,
      `<b>Background + auto-save.</b> All 3 run in the background; each saves as it finishes. Use <i>Redo this</i> on any that drifts.` ]},
    secAI: { title:"How the AI-designed secondary set works", steps:[
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec.`,
      `<b>Invents secondary concepts</b> — which benefit to lead with, what objection to kill, which lifestyle moment sells it (text/graphics allowed on secondary images).`,
      `<b>You pick which to generate.</b>`,
      `<b>Generates faithfully</b> via <code>run_pipeline</code> with your product attached at <b>strength ${strn}, 4K</b> (image AI: <code>${esc(C)}</code>).`,
      `<b>Auto-saves</b> every result.` ]},
    secManual: { title:"How your hand-built secondary set works", steps:[
      `<b>You define the set</b> — roles ticked, benefits per image, specific benefits, competitor inspiration.`,
      `<b>Competitor inspiration handled safely.</b> "Describe style" → vision AI extracts only the <i>technique</i> (lighting, angle, effects) and reapplies it to your product (no copying). "Direct" → feeds their image to the model.`,
      `<b>Reads your product</b> (<code>${esc(T)}</code>) for an exact spec.`,
      `<b>Generates each role</b> with your product attached at <b>strength 0.35, 4K</b> (image AI: <code>${esc(C)}</code>), one clear message per image.`,
      `<b>Auto-saves</b> every result.` ]},
    source: { title:"How the Main image (clean white bg) works", steps:[
      `<b>Pick the reference photo.</b> The product's source images (eBay first) are shown as thumbnails — tap the cleanest one that best shows the product. If you don't pick, the first is auto-selected.`,
      `<b>Reads the source photo</b> (eBay/Amazon scrape or brand upload) with the prompt AI (<code>${esc(T)}</code>) for a product spec.`,
      `<b>Applies the logo rule by source.</b> Competitor/eBay → remove a brand logo if present, blend to surface (no replacement); no logo → leave as-is. Brand CSV → keep product <i>and</i> logo (unless you uncheck "preserve logo").`,
      `<b>Keeps the product identical</b> — only the logo and your optional edits change.`,
      `<b>Generates clean</b> with your chosen reference attached at your fidelity strength, target <b>2500px, pure white</b> (image AI: <code>${esc(C)}</code>).`,
      `<b>Auto-saves</b> the result, and shows its real <b>pixel size and file size</b> under the image.` ]},
    drive: { title:"How Drive image storage works", steps:[
      `<b>Set a master folder per account.</b> In Account &amp; sheets, paste a Google Drive folder URL. That folder becomes the home for this account's generated images.`,
      `<b>Share it with the service account.</b> Just like a Google Sheet, the folder must be shared (Editor) with the service-account email shown in the Drive panel — otherwise uploads are denied.`,
      `<b>Per-product subfolders.</b> Each image is uploaded into a subfolder named <code>{SKU}_{ProductName}</code>, created automatically if it doesn't exist.`,
      `<b>Your own Drive.</b> Images live in your Drive, organised by product, safe and separate from the app.` ]},
    content_index: { title:"How the content fields & indexing work", steps:[
      `<b>Title</b> — fill close to the 75-char cap (the hard cap lands 27 Jul 2026). Front-load the first ~70 chars; mobile truncates there. Fully indexed, highest A10 weight.`,
      `<b>Item Highlights</b> — a structured 125-char field shown with the title in search and on the PDP; carries its own weight.`,
      `<b>Bullets</b> — 500 chars each, but Amazon indexes only the first ~1,000 <i>bytes</i> across ALL five combined. The meter above the bullets shows how much of that budget is used; overflow still shows to shoppers but isn't indexed.`,
      `<b>Description</b> — up to 2,000 chars incl. HTML; indexed but lowest weight.`,
      `<b>Backend search terms</b> — 249 <i>bytes</i> (not chars). One byte over silently de-indexes the whole field, so the counter is in bytes and warns near the limit.` ]},
    required_fields: { title:"How required fields are shown", steps:[
      `<b>The red ★</b> marks a field Amazon requires, read straight from the live schema's <code>required</code> list for this product type.`,
      `<b>Before Preview</b> we show every <i>static</i> required field. Some are <i>conditional</i> (e.g. the lithium-battery group) and Amazon only reveals them after a Preview.`,
      `<b>After Preview</b> every field Amazon flags gets a visible box — including nested sub-fields — so nothing the validator wants is hidden from you.`,
      `<b>Product type</b> defaults to the type Amazon assigned in the catalogue ("Amazon-assigned"); changing it warns you, because a wrong type causes rejection.` ]},
    // ---------- OPTIMIZE: the red-dot fixer ----------
    opt_fetch: { title:"How 'Optimize live listing' loads the data", steps:[
      `<b>Reads the LIVE listing from Amazon.</b> Calls SP-API <code>getListingsItem</code> with <code>includedData="attributes,summaries,issues"</code> on the connected seller account — so the title, status and fields are the real current ones, not a cached report.`,
      `<b>Shows Amazon's own issues verbatim.</b> The warnings/errors come straight from Amazon's <code>issues</code> array (e.g. "invalid condition type", "missing item_dimensions") and are parsed to name the exact attributes at fault. This text is Amazon's, not the app's guess.`,
      `<b>Nothing is changed.</b> This step only reads. You draft edits against it, and only approved fields are pushed later.` ]},
    opt_diagnose: { title:"How 'Suggest fixes with AI' works", steps:[
      `<b>Re-reads the live listing</b> (<code>getListingsItem</code>) and collects ONLY the attributes Amazon flagged as missing or invalid.`,
      `<b>Asks the AI for values for just those fields.</b> The prompt AI (<code>${esc(T)}</code>) proposes values <i>only</i> for the flagged attributes. These are clearly labeled <b>AI estimates</b> — inferred, not from Amazon.`,
      `<b>You review and tick.</b> Nothing is pushed here. You edit/correct each suggestion and tick only the ones you want.`,
      `<b>Honest limit:</b> dimensions with units are safest finished in Seller Central, which structures the nested fields correctly.` ]},
    opt_push: { title:"How approved changes reach Amazon", steps:[
      `<b>Gated by your approval.</b> The push only runs with a <code>confirmed</code> flag, and only the fields you ticked are sent — nothing else.`,
      `<b>Builds a minimal patch.</b> <code>_build_patches</code> turns your approved fields into JSON-Patch operations, applied via SP-API <code>patchListingsItem</code> (a targeted edit, not a full re-submit).`,
      `<b>Only approved fields change</b> on the live listing; everything you didn't tick is left untouched.` ]},
    opt_rewrite: { title:"How 'Custom AI rewrite' works", steps:[
      `<b>Uses your instruction as the driver.</b> You tell the AI what you want (e.g. "no brand in title, emphasise durability"). A product link is optional extra context.`,
      `<b>Pulls source context if given.</b> Any eBay/Amazon link you paste is fetched and fed in so the AI knows the real product.`,
      `<b>Brand is optional context only.</b> The account's brand is passed as context but never forced into copy — and the app never falls back to the account label as a brand (this fixed the "label leaked into title" bug).`,
      `<b>Applies your compliance & IP rules.</b> The rewrite still runs under <code>compliance_rules.json</code> and <code>ip_rules.json</code> (forbidden phrases / safe words), so the new copy stays Amazon-safe.`,
      `<b>Returns a draft</b> (title/bullets/description) for your review — nothing is pushed automatically.` ]},
    // ---------- GENERATION PIPELINE ----------
    gen_pipeline: { title:"How 'Generate' builds a listing (the full pipeline)", steps:[
      `<b>1 · Scrapes the product.</b> For each source row it pulls real data: the eBay item (Browse API via <code>fetch_ebay_supplement</code> — specifics + images) and the competitor Amazon ASIN (<code>get_competitor_asin_data</code>, plus a crawl4ai PDP scrape as fallback). It also pulls pricing/fees and computes financials.`,
      `<b>2 · Writes the prompt.</b> <code>build_prompt</code> folds the scraped specifics, pricing, keywords (autocomplete) and your rules into a structured brief.`,
      `<b>3 · Generates the listing</b> with the Claude API (<code>generate_listing</code>) — title, bullets, description, and the product-type attributes Amazon's schema requires.`,
      `<b>4 · Runs the compliance + IP gates</b> (see the next two panels) — these can downgrade the status.`,
      `<b>5 · Builds the SKU</b> as <code>{source_price}_{N}Days_{COMP_ASIN}</code> (e.g. <code>7.99_3Days_B0XYZ12345</code>); duplicates get <code>_2</code>, <code>_3</code> appended.`,
      `<b>6 · Maps the flat-file route</b> (<code>detect_route</code> → FILE1 or FILE2) for the right Amazon template, and writes everything to your Google Sheet with a Status for review. <b>Nothing is submitted to Amazon here</b> — generation only fills the sheet.` ]},
    gen_compliance: { title:"How the compliance gate works", steps:[
      `<b>Checks the listing against your rules.</b> <code>check_compliance</code> screens the generated copy using <code>compliance_rules.json</code> (your 17 UK regulatory categories) for risky claims and category risk level.`,
      `<b>Can downgrade the status.</b> If the product falls in a HIGH-risk category, a <code>NEEDS_REVIEW</code> row is downgraded to <code>COMPLIANCE_HOLD</code> so you must review it before it can go live.`,
      `<b>Safety-net defaults</b> are applied where required fields are missing, so the listing isn't left in a non-compliant state silently.` ]},
    gen_ip: { title:"How the IP / trademark gate works", steps:[
      `<b>Screens for brand/trademark risk.</b> <code>check_ip_violations</code> matches the copy against <code>ip_rules.json</code> — your list of forbidden phrases (e.g. "compatible with X", "replacement for X") and ~470 safe words.`,
      `<b>IP_HOLD supersedes other holds.</b> If a forbidden phrase is found, the status is set to <code>IP_HOLD</code> — which overrides <code>NEEDS_REVIEW</code> and <code>COMPLIANCE_HOLD</code> (a hard ERROR stays an error).`,
      `<b>You review every hold.</b> The full status flow is: <code>NEEDS_REVIEW → COMPLIANCE_HOLD / IP_HOLD → APPROVED → export</code>. Only APPROVED rows are exported to the flat file.` ]},
    // ---------- LISTINGS GRID / SYNC ----------
    grid_load: { title:"How the listings grid loads", steps:[
      `<b>Pulls your live listings from Amazon.</b> <code>/live/catalog</code> requests a Reports-API report (<code>GET_MERCHANT_LISTINGS_ALL_DATA</code>) for the connected account + marketplace, then parses each row.`,
      `<b>Reads real fields per listing.</b> From the report it captures SKU, ASIN, title, price, quantity, status, brand, and — importantly — <code>fulfillment-channel</code> (FBA/FBM) and <code>merchant-shipping-group</code>.`,
      `<b>Caches briefly</b> so re-opening is instant. A normal load reuses a recent report/cache; it does <i>not</i> hit Amazon every time.`,
      `<b>Drafts vs Live vs All</b> just filters what's shown — Drafts are from your sheet, Live are pulled from Amazon, All merges both.` ]},
    grid_enrich: { title:"How each card gets its image, title, FBA/FBM & shipping", steps:[
      `<b>Enriches in batches.</b> <code>/live/images</code> calls <code>getListingsItem</code> with <code>includedData="summaries,issues,fulfillmentAvailability,attributes"</code> for the visible SKUs.`,
      `<b>Pulls the real main image and live title</b> (from <code>summaries</code>) — so the title reflects any edit you made immediately, not the cached report.`,
      `<b>Shows fulfillment + handling.</b> FBA/FBM comes from the fulfillment data; FBM handling time is the real <code>lead_time_to_ship_max_days</code>.`,
      `<b>Honest caveat on dates.</b> "Ships by / delivery ~" dates are <i>estimates</i> the app computes (FBM ≈ your handling + ~5d transit; FBA ≈ ~2d) — they are not Amazon's exact promised dates.` ]},
    grid_sync: { title:"How 'Sync' forces fresh data", steps:[
      `<b>Forces a brand-new report.</b> Sync sends <code>force=true</code>, which <i>skips</i> the report/cache reuse and generates a FRESH Reports-API report (this fixed the bug where Sync reused stale data).`,
      `<b>Clears the per-listing cache.</b> It drops the cached images/status/title/fulfillment for this account+marketplace, so everything re-pulls from Amazon.`,
      `<b>Use it after edits or going live.</b> Amazon can take a little time to reflect changes; if a fresh report isn't ready yet, Sync again in a minute and it loads.` ]},
    // ---------- ACCOUNTS / CONNECTION ----------
    acct_connect: { title:"How connecting an account to Amazon works", steps:[
      `<b>You provide SP-API credentials.</b> Seller/merchant ID, LWA client ID, LWA client secret, and a refresh token — the four things Amazon's Selling Partner API needs (<code>account_creds</code>).`,
      `<b>"Connected" = a real refresh token.</b> An account counts as connected only when its refresh token is real (not a <code>PUT_</code>/<code>ROTATE</code> placeholder). Until then it's <b>draft-only</b>: you can build and generate listings, but live features (pulling listings, optimize, submit) are disabled.`,
      `<b>Secrets stay local.</b> The client secret and refresh token are stored in your local <code>config.json</code> and shown as masked dots — the app never displays the saved values, and you can leave them blank to keep the existing ones.`,
      `<b>Each account is a workspace.</b> Account → Marketplace → Listings. Brands are data attached to an account, not a separate level.` ]},
    acct_marketplaces: { title:"How 'Detect marketplaces' works", steps:[
      `<b>Asks Amazon which marketplaces this account sells in.</b> Calls SP-API <code>getMarketplaceParticipations</code> (Sellers API) with the account's credentials.`,
      `<b>Maps IDs to codes</b> using the built-in marketplace table (e.g. <code>A1F83G8C2ARO7P</code> → UK, <code>ATVPDKIKX0DER</code> → US) and saves the detected codes onto the account.`,
      `<b>This is why the workspace shows real marketplaces</b> — the US/UK/DE tabs reflect where the account is actually live, pulled from Amazon, not typed in by hand.` ]},
    acct_brands: { title:"How 'Detect brands' works (and its honest limit)", steps:[
      `<b>Reads the brand field from live listings.</b> It derives the brands actually used on the account from the <code>brand</code> field in the listings report, merged with any brands you typed.`,
      `<b>Honest limit:</b> Amazon has no clean "list my Brand Registry brands" API — so this is what's <i>seen on live listings</i>, not a Brand Registry pull. Add or correct brands manually if needed.` ]},
    // ---------- COGS ----------
    cogs: { title:"How COGS & the profit estimate work", steps:[
      `<b>Two ways to know your cost.</b> <code>_resolve_cogs</code> uses a priority: a <b>manual override</b> you set per SKU wins; otherwise it reads the cost <b>embedded in the dropshipping SKU</b> (the <code>{source_price}_…</code> prefix).`,
      `<b>Bulk upload.</b> The COGS CSV (<code>/cogs/upload</code>) accepts SKU + cost rows and stores them as per-account overrides, so you can set many at once.`,
      `<b>Profit is an estimate.</b> <code>_estimate_profit</code> = price − COGS − a <b>15% referral fee</b> (default). It's a quick margin guide, not Amazon's exact fee — real fees vary by category and include other charges.`,
      `<b>Stored locally</b> in your COGS overrides file, keyed by account+SKU.` ]},
    // ---------- SUBMIT LIVE ----------
    submit_live: { title:"How 'Submit · go live' publishes to Amazon", steps:[
      `<b>Double-confirms the destination.</b> First it calls <code>/submit/target</code> to find the <b>active account</b> and marketplace, then shows you a confirm dialog <b>naming that exact account</b> — so you can't publish to the wrong store.`,
      `<b>Checks credentials exist.</b> If the view's marketplace has no SP-API credentials, it stops and tells you — nothing is sent.`,
      `<b>Publishes only APPROVED rows.</b> It runs <code>api_submit</code>, which creates or replaces live listings for every <b>APPROVED / API_READY</b> row in this view — rows still in NEEDS_REVIEW / holds are skipped.`,
      `<b>This is the only step that writes to Amazon.</b> Generation, optimize drafts, and image generation never publish — only this button does, and only after your confirmation.` ]},
    // ---------- RECIPES / MEDIA / A+ ----------
    recipes: { title:"How image recipes work", steps:[
      `<b>A recipe is a saved, reusable treatment.</b> It stores a template image + the instructions/changes you want (e.g. "droplets on the bottle, soft top light"), so you can apply the same look to any product without retyping it.`,
      `<b>Recipes are per-brand.</b> They're saved against the active brand, but the studio also exposes recipes from your <i>other</i> brands (clearly labelled) so you can reuse across.`,
      `<b>Applying a recipe</b> runs the normal pipeline: your product image is attached as reference and the recipe's instructions become the brief — the product itself stays identical, only the treatment is applied.`,
      `<b>Stored locally</b> in <code>image_recipes.json</code>.` ]},
    media: { title:"How the media library & auto-save work", steps:[
      `<b>Per-SKU folders.</b> Every product has its own media folder; <code>/media/list</code> shows the stored images grouped by SKU, and <code>/media/<sku>/<file></code> serves them.`,
      `<b>Auto-save on generation.</b> Every image the studio generates is written to that product's folder immediately (<code>generated_*.png</code>) — so results are never lost even if you close the window.`,
      `<b>Manual save & upload.</b> "Save to media" stores a chosen image; you can also upload your own images into a SKU's folder. Delete removes a file from the folder.`,
      `<b>These are local files</b> on your machine — separate from Amazon. You choose which to use when building a listing.` ]},
    aplus: { title:"How A+ Content generation works (and what Amazon requires)", steps:[
      `<b>Generates module images at Amazon's EXACT pixel dimensions.</b> The catalog (<code>_APLUS_MODULES</code>) holds each Basic and Premium module with its precise size (e.g. image+text 970×600, four-quadrant 220×220), so the output fits Amazon's A+ builder.`,
      `<b>Drafts the copy separately.</b> It writes the module text (≈70% visual / 30% text) and blocks prohibited claims — the text is drafted by the prompt AI for reliability, not baked into the image.`,
      `<b>Keeps your product faithful.</b> Your product image is always attached as the reference.`,
      `<b>Honest gating:</b> A+ requires <b>Amazon Brand Registry</b>; <b>Premium A+</b> additionally needs a Brand Story on all ASINs + 15 approved submissions in the last 12 months. The app builds the assets — <b>you upload them in Seller Central's A+ builder</b>.` ]}
  };
}
function howWorks(which){
  if(!window.LOGIC_VISIBLE) return "";
  const reg = LOGIC_REGISTRY();
  const b = reg[which]; if(!b) return "";
  return `<details class="howbox"><summary><span class="chev">▶</span> How this works — the actual steps behind the button</summary>
    <div class="howbody"><div style="font-weight:600;color:var(--text);margin-bottom:2px">${esc(b.title)}</div>
      <ol>${b.steps.map(s=>`<li>${s}</li>`).join("")}</ol>
      <div style="margin-top:6px;opacity:.8">Models shown reflect your current dropdown selections. Nothing is sent to Amazon — generated images only go to this product's media library for review.</div>
    </div></details>`;
}
// Inject disclosures that live in STATIC page HTML (not JS template literals).
// Called on boot and whenever the admin toggles logic visibility.
function refreshStaticHowPanels(){
  const map = {
    "genhow":  ['gen_pipeline','gen_compliance','gen_ip','submit_live'],
    "gridhow": ['grid_load','grid_enrich','grid_sync','cogs']
  };
  Object.keys(map).forEach(function(id){
    const el=document.getElementById(id);
    if(el){ el.innerHTML = (typeof howWorks==="function") ? map[id].map(function(k){return howWorks(k);}).join("") : ""; }
  });
}

function _studioAddResult(job, j, grid){
  grid=grid||document.getElementById("studio_results");
  const cardId="sres_"+Math.random().toString(36).slice(2);
  const label=esc(job.sku)+(job.strategy?(' · '+job.strategy.replace('_',' ')):'');
  let inner;
  if(j&&j.ok&&j.data_url){
    // stash the originating kind+payload so we can regenerate JUST this one
    STUDIO._reroll=STUDIO._reroll||{};
    if(j._kind&&j._payload){ STUDIO._reroll[cardId]={kind:j._kind, payload:j._payload, label:(job.strategy||job.sku)}; }
    const canReroll = !!(j._kind&&j._payload);
    const _driveLine = j.drive_direct_url
      ? `<div class="cc" style="color:#86d0a8;font-size:10.5px;padding:0 8px 4px">\u2713 saved to Drive</div>`
      : (j.drive_error
          ? `<div class="cc" style="color:#e3b768;font-size:10.5px;padding:0 8px 4px">Drive: ${esc(j.drive_error)}</div>`
          : (j.save_error
              ? `<div class="cc" style="color:#e0696b;font-size:10.5px;padding:0 8px 4px">Save: ${esc(j.save_error)}</div>`
              : ""));
    inner=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
      <div class="srescap">${label}</div>
      ${_driveLine}
      <div class="sresacts">
        <button class="ib" onclick="studioSave('${cardId}','${esc(job.sku)}')"><i class="ti ti-device-floppy"></i> Save to media</button>
        <button class="ib" onclick="studioDownload('${cardId}','${esc(job.sku)}')"><i class="ti ti-download"></i></button>
        <button class="ib" onclick="studioToDrive('${cardId}','${esc(job.sku)}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
        ${canReroll?`<button class="ib" onclick="studioReroll('${cardId}')" title="Generate this one again (e.g. if a detail came out wrong)"><i class="ti ti-refresh"></i> Redo this</button>`:''}
        ${canReroll?`<button class="ib" onclick="studioRefine('${cardId}')" title="Tell the AI a small change to make to THIS image"><i class="ti ti-wand"></i> Refine…</button>`:''}
      </div>`;
    STUDIO.results[cardId]={data_url:j.data_url, sku:job.sku};
  } else {
    inner=`<div class="sresfail">✗ ${esc((j&&j.error)||'failed')}</div><div class="srescap">${label}</div>`;
  }
  const div=document.createElement("div");
  div.className="srescard"; div.id=cardId; div.innerHTML=inner;
  grid.appendChild(div);
}
async function studioReroll(cardId){
  const r=(STUDIO._reroll||{})[cardId]; if(!r){ toast("Can't redo this one."); return; }
  const card=document.getElementById(cardId);
  if(card){ card.innerHTML='<div class="srescap"><span class="genspin"></span> regenerating…</div>'; }
  const ep = r.kind==="concept" ? "/genimage/from_concept"
           : r.kind==="source" ? "/genimage/process_source"
           : r.kind==="secondary" ? "/genimage/secondary_v2"
           : r.kind==="aplus" ? "/genimage/generate"
           : "/genimage/recipe";
  try{
    const j=await (await fetch(ep,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(r.payload)})).json();
    if(j&&j.ok&&j.data_url){
      // auto-save the redo too
      try{ await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:r.payload.sku||r.payload.title||"", data_url:j.data_url})}); }catch(e){}
      if(card){
        STUDIO.results[cardId]={data_url:j.data_url, sku:(r.payload.title||"")};
        card.innerHTML=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
          <div class="srescap">${esc(r.label)} · redone</div>
          <div class="sresacts">
            <button class="ib" onclick="studioSave('${cardId}','')"><i class="ti ti-device-floppy"></i> Save to media</button>
            <button class="ib" onclick="studioDownload('${cardId}','')"><i class="ti ti-download"></i></button>
            <button class="ib" onclick="studioToDrive('${cardId}','')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
            <button class="ib" onclick="studioReroll('${cardId}')"><i class="ti ti-refresh"></i> Redo this</button>
          </div>`;
      }
    } else {
      if(card){ card.innerHTML='<div class="sresfail">✗ '+esc((j&&j.error)||'failed')+'</div>'; }
    }
  }catch(e){ if(card){ card.innerHTML='<div class="sresfail">✗ '+esc(String(e))+'</div>'; } }
}
async function studioRefine(cardId){
  const cur=(STUDIO.results||{})[cardId];
  const r=(STUDIO._reroll||{})[cardId];
  if(!cur||!cur.data_url){ toast("Nothing to refine here."); return; }
  const instruction=prompt("What small change should I make to this image?\n(e.g. \"make the background warmer\", \"remove the water droplets\", \"move the product slightly left\", \"make the text bigger\")");
  if(!instruction||!instruction.trim()) return;
  // figure out the kind from the original payload (main / secondary / aplus)
  let kind="main";
  if(r&&r.kind){ kind = (r.kind==="concept")?"main":(r.kind==="aplus"?"aplus":(r.kind==="secondary"?"secondary":"main")); }
  const card=document.getElementById(cardId);
  if(card){ card.innerHTML='<div class="srescap"><span class="genspin"></span> refining…</div>'; }
  // attach the ORIGINAL product reference so the edit can't drift the real product
  let origRef="";
  try{
    const sku=cur.sku||"";
    const it=_itemForSku(sku) || (STUDIO.items&&STUDIO.items[0]);
    origRef=_refImgForItem(it)||"";
  }catch(e){}
  const payload={
    image:cur.data_url, original_reference:origRef, instruction:instruction.trim(), kind:kind,
    title:(cur.sku||""), text_provider:(window.AI_TEXT||null), image_provider:(window.AI_IMAGE||null)
  };
  try{
    const j=await (await fetch("/genimage/refine",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload)})).json();
    if(j&&j.ok&&j.data_url){
      try{ await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:cur.sku||"", data_url:j.data_url})}); }catch(e){}
      STUDIO.results[cardId]={data_url:j.data_url, sku:cur.sku};
      // keep refine available so you can iterate (refine the refined image)
      if(j._kind&&j._payload){ STUDIO._reroll[cardId]={kind:j._kind, payload:j._payload, label:(STUDIO._reroll[cardId]?STUDIO._reroll[cardId].label:cur.sku)}; }
      if(card){
        card.innerHTML=`<img src="${j.data_url}" class="sresimg" onload="imgMetaLabel(this,'${j.data_url}')">
          <div class="srescap">refined: ${esc(instruction.trim()).slice(0,40)}</div>
          <div class="sresacts">
            <button class="ib" onclick="studioSave('${cardId}','${esc(cur.sku||'')}')"><i class="ti ti-device-floppy"></i> Save to media</button>
            <button class="ib" onclick="studioDownload('${cardId}','${esc(cur.sku||'')}')"><i class="ti ti-download"></i></button>
            <button class="ib" onclick="studioToDrive('${cardId}','${esc(cur.sku||'')}')" title="Upload to this account's Drive folder"><i class="ti ti-brand-google-drive"></i> Drive</button>
            <button class="ib" onclick="studioRefine('${cardId}')" title="Make another small change"><i class="ti ti-wand"></i> Refine…</button>
          </div>`;
      }
    } else {
      if(card){ card.innerHTML='<div class="sresfail">✗ '+esc((j&&j.error)||'failed')+'</div>'; }
      toast("Refine failed: "+((j&&j.error)||""));
    }
  }catch(e){ if(card){ card.innerHTML='<div class="sresfail">✗ '+esc(String(e))+'</div>'; } }
}
async function studioSave(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  try{
    const j=await (await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, data_url:r.data_url})})).json();
    if(j.ok){ r.savedUrl=j.url; toast("Saved to "+sku+" media library"); }
    else toast("Save failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
async function studioToDrive(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  // confirm a Drive folder is configured for this account
  let ds=null; try{ ds=await (await fetch("/drive/status")).json(); }catch(e){}
  if(!ds||!ds.ok||!ds.configured){
    toast("No Drive folder set for this account — add one in Account & sheets");
    return;
  }
  // ensure it's saved locally first (Drive upload reads the local file)
  if(!r.savedUrl){
    try{
      const sj=await (await fetch("/genimage/save_to_media",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({sku:sku, data_url:r.data_url})})).json();
      if(sj.ok) r.savedUrl=sj.url; else { toast("Save failed: "+(sj.error||"")); return; }
    }catch(e){ toast("Error: "+e); return; }
  }
  const it=_itemForSku(sku);
  const pname=(it&&it.title)||(r.sku||"");
  toast("Uploading to Drive…");
  try{
    const j=await (await fetch("/drive/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku:sku, product_name:pname, relpath:r.savedUrl})})).json();
    if(j.ok) toast("Uploaded to Drive ✓");
    else toast("Drive upload failed: "+(j.error||""));
  }catch(e){ toast("Error: "+e); }
}
function _extFromDataUrl(durl){
  // Determine the TRUE image extension from the bytes, not the mime label (which
  // can be wrong -- e.g. JPEG bytes tagged image/png, which Amazon then rejects).
  try{
    if(!durl) return "jpg";
    if(/^https?:/i.test(durl)){
      const m=durl.split("?")[0].match(/\.(png|jpe?g|webp|gif)$/i);
      return m ? (m[1].toLowerCase()==="jpeg"?"jpg":m[1].toLowerCase()) : "jpg";
    }
    const comma=durl.indexOf(","); if(comma<0) return "jpg";
    const bin=atob(durl.slice(comma+1, comma+24));  // first few bytes are enough
    const b=[]; for(let i=0;i<bin.length;i++) b.push(bin.charCodeAt(i)&0xff);
    if(b[0]===0xff&&b[1]===0xd8&&b[2]===0xff) return "jpg";
    if(b[0]===0x89&&b[1]===0x50&&b[2]===0x4e&&b[3]===0x47) return "png";
    if(b[0]===0x52&&b[1]===0x49&&b[2]===0x46&&b[3]===0x46&&b[8]===0x57&&b[9]===0x45) return "webp";
    if(b[0]===0x47&&b[1]===0x49&&b[2]===0x46) return "gif";
  }catch(e){}
  return "jpg";
}
function studioDownload(cardId, sku){
  const r=STUDIO.results[cardId]; if(!r) return;
  // Prefer the full-resolution image URL if we have it; fall back to the inline
  // data. Convert to JPEG on download (Amazon-preferred, smaller files).
  const src = r.url || r.data_url;
  _downloadAsJpeg(src, (sku||"image"));
}
function _downloadAsJpeg(src, baseName){
  // Draw the image to a canvas and export JPEG, so downloads are always .jpg
  // regardless of the source format. Transparency is flattened onto white.
  try{
    const img=new Image();
    img.crossOrigin="anonymous";
    img.onload=function(){
      try{
        const c=document.createElement("canvas");
        c.width=img.naturalWidth||img.width; c.height=img.naturalHeight||img.height;
        const ctx=c.getContext("2d");
        ctx.fillStyle="#ffffff"; ctx.fillRect(0,0,c.width,c.height);
        ctx.drawImage(img,0,0);
        const jpeg=c.toDataURL("image/jpeg",0.9);
        const a=document.createElement("a"); a.href=jpeg; a.download=baseName+".jpg"; a.click();
      }catch(e){
        // tainted canvas (cross-origin) -> fall back to direct download of source
        const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click();
      }
    };
    img.onerror=function(){ const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click(); };
    img.src=src;
  }catch(e){
    const a=document.createElement("a"); a.href=src; a.download=baseName+".jpg"; a.click();
  }
}
async function loadSchemas(pts, force, mkt){
  const mp = (mkt||"").toString().toUpperCase();
  const q = (force?"?refresh=1":"") + (mp?((force?"&":"?")+"mkt="+encodeURIComponent(mp)):"");
  await Promise.all(pts.map(async pt=>{
    if(SCHEMAS[pt] && (SCHEMAS[pt].attrs||[]).length && !force)return;  // only skip if genuinely loaded
    try{const r=await fetch("/schema/"+encodeURIComponent(pt)+q);const j=await r.json();
        SCHEMAS[pt]=j.ok?{opts:(j.enums||{}),req:(j.required||[]),attrs:(j.attrs||[]),subs:(j.subfields||{}),titles:(j.titles||{}),_mkt:(j.marketplace||mp)}:{opts:{},req:[],attrs:[],subs:{},titles:{}};}catch(e){SCHEMAS[pt]={opts:{},req:[],attrs:[],subs:{},titles:{}};}
  }));
}
async function refreshSchemaFor(sku){
  const r=ROWS.find(x=>String(x.sku)===String(sku)); if(!r)return;
  const pt=r.product_type; if(!pt){toast("No product type on this row");return;}
  delete SCHEMAS[pt];
  toast("Refreshing Amazon allowed values…");
  await loadSchemas([pt], true, rowMkt(r));
  if(DRAWER_SKU===sku){ openDrawer(sku); }
  else render();
  toast("Amazon values refreshed — dropdowns updated");
}

async function setStatus(sku,status,btn){
  if(!sku){toast("This row has no SKU yet");return;}
  btn.disabled=true; const old=btn.textContent; btn.textContent="…";
  try{
    const res=await fetch("/approve",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku,status})});
    const j=await res.json();
    if(j.ok){const r=ROWS.find(x=>x.sku===sku); if(r)r.status=status; render(); toast(status==="APPROVED"?"Approved":"Set to needs-review");}
    else {toast("Failed: "+j.error); btn.disabled=false; btn.textContent=old;}
  }catch(e){toast("Failed: "+e); btn.disabled=false; btn.textContent=old;}
}

function setFilter(el){
  document.querySelectorAll(".pill").forEach(p=>p.classList.remove("active"));
  el.classList.add("active"); FILTER=el.dataset.f; render();
}
function setFilterVal(v){
  FILTER=v||"all";
  // leaving brand settings panel if open
  var bp=document.getElementById('brandpanel'); if(bp&&bp.style.display!=='none'){ bp.style.display='none'; var g=document.getElementById('grid'); if(g) g.style.display=''; var sm=document.getElementById('summary'); if(sm) sm.style.display=''; }
  render();
}

let ES=null;
function showStop(on){ const b=document.getElementById("stopbtn"); if(b) b.disabled=!on; }
async function stopRun(){
  const b=document.getElementById("stopbtn"); if(b) b.disabled=true;
  try{ const r=await fetch("/stop",{method:"POST"}); const j=await r.json();
       toast(j.ok?"Stopping the run\u2026":("Stop: "+(j.error||"nothing running"))); }
  catch(e){ toast("Stop failed"); if(b) b.disabled=false; }
}
function genSelOnInput(){
  const v=(document.getElementById("gensel_value").value||"").toLowerCase();
  const dd=document.getElementById("gensel_type");
  const hint=document.getElementById("gensel_hint");
  const isUrl = v.includes("http://")||v.includes("https://")||v.includes("amazon.")||v.includes("ebay.");
  if(dd){ dd.disabled=isUrl; dd.style.opacity=isUrl?.45:1; }
  if(hint){ hint.textContent = isUrl
    ? "URL detected — the platform is read from the link, so the dropdown is ignored."
    : "Row numbers can be comma-separated (e.g. 2, 5, 7). For one product you can paste its URL — the dropdown is ignored then."; }
}
