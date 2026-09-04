/* static/js/drawer_attributes.js -- Amazon's live values, beside our own.
 *
 * THE PROBLEM THIS EXISTS FOR
 *
 *     "For listings that were created as me too or outside the app, the
 *      attributes are empty even though Amazon has the data."
 *
 * They were empty because nothing ever asked Amazon. The drawer's attribute
 * grid has always shown the row's OWN Attributes JSON -- what this app wrote
 * when it generated the listing -- so a listing this app did not generate has
 * nothing to show. Every other part of the grid already worked: the required
 * stars, the schema dropdowns, the nested sub-field boxes, the save-on-blur.
 * The single missing ingredient was the data.
 *
 * WHAT THIS FILE DOES AND DOES NOT DO
 *
 * It fetches (once per drawer open), caches, and decorates. It does NOT draw a
 * second attribute grid -- autofix.js's grid is the only one, and it now takes
 * these values as an extra source (CLAUDE.md Rule 12). It does NOT write to
 * Amazon: "Use this" copies Amazon's value into the local row through the same
 * /edit the boxes already use, and nothing reaches Amazon until Submit.
 *
 * NOTHING IS COPIED WITHOUT BEING ASKED. It would have been easy to pour every
 * live value into the row on open and call it "merging". That would rewrite a
 * listing's stored data from a source the user never looked at, and there is no
 * undo. Every copy here is a button someone presses.
 */

/* sku -> {state, values, multi, content, issues, error, product_type,
 *         amazon_status, on_amazon, reason}
 * state: "loading" | "ok" | "gone" | "error" */
const LIVE_ATTRS = {};

/* WHICH LISTINGS ARE WORTH ASKING ABOUT.
 *
 * A QUEUED or GENERATED listing has never been sent, so there is nothing on
 * Amazon to fetch and the call would spend a rate-limited request to be told
 * 404. Those rows show their local values and the schema dropdowns exactly as
 * before -- which is what the brief asks for, and what already happened. */
function lvWants(r){
  if(!r) return false;
  const st = String(r.status||"").toUpperCase();
  if(st === "LIVE" || st === "SUBMITTED") return true;
  try{ return typeof isAmazonLive === "function" && isAmazonLive(r); }
  catch(e){ return false; }
}

function lvGet(sku){ return LIVE_ATTRS[String(sku)] || null; }
function lvKeys(sku){
  const L = lvGet(sku);
  return (L && L.state === "ok") ? Object.keys(L.values||{}) : [];
}

/* Fetch once. Re-entrant: a second call while one is in flight does nothing. */
function lvEnsure(r){
  if(!lvWants(r)) return;
  const sku = String(r.sku);
  if(LIVE_ATTRS[sku]) return;                 // cached, including a past failure
  LIVE_ATTRS[sku] = {state:"loading", values:{}, multi:{}, content:{}, issues:[]};
  const url = acctUrl("/listing/live_attributes?sku=" + encodeURIComponent(sku)
                      + "&mkt=" + encodeURIComponent(typeof rowMkt==="function" ? rowMkt(r) : ""));
  fetch(url).then(res => res.json()).then(j => {
    if(!j || !j.ok){
      LIVE_ATTRS[sku] = {state:"error", values:{}, multi:{}, content:{}, issues:[],
                         error: (j && j.error) || "Amazon did not answer"};
    } else if(j.on_amazon === false){
      LIVE_ATTRS[sku] = {state:"gone", values:{}, multi:{}, content:{}, issues:[],
                         reason: j.reason || ""};
    } else {
      LIVE_ATTRS[sku] = {state:"ok", values:j.values||{}, multi:j.multi||{},
                         content:j.content||{}, issues:j.issues||[],
                         skipped:j.skipped||[], product_type:j.product_type||"",
                         // THE CATALOGUE RECORD, kept apart from `values`.
                         // `values` is what THIS seller submitted, read back.
                         // `summary` is what Amazon actually shows shoppers,
                         // which on a shared ASIN can be another seller's
                         // contribution. Two different facts, so two fields.
                         summary:j.summary||{},
                         amazon_status:j.amazon_status||""};
    }
  }).catch(e => {
    LIVE_ATTRS[sku] = {state:"error", values:{}, multi:{}, content:{}, issues:[],
                       error: String((e && e.message) || e)};
  }).then(() => {
    // Only redraw if this SKU is still the one on screen -- in EITHER view.
    // Redrawing one the user has already left would put one listing's values
    // under another listing's name.
    const onDrawer = (typeof DRAWER_SKU !== "undefined") && String(DRAWER_SKU) === sku;
    const onPdp    = (typeof PDP_SKU !== "undefined") && String(PDP_SKU) === sku;
    if(onDrawer && typeof _rebuildDrawerData === "function") _rebuildDrawerData(sku);
    else if(onPdp && typeof pdpRebuild === "function") pdpRebuild(sku);
  });
}

/* Throw the cached answer away and ask again. */
function lvRefresh(sku){
  sku = String(sku);
  delete LIVE_ATTRS[sku];
  const r = (typeof ROWS !== "undefined") ? ROWS.find(x => String(x.sku) === sku) : null;
  if(!r) return;
  lvEnsure(r);
  if(typeof _rebuildDrawerData === "function") _rebuildDrawerData(sku);   // show "checking"
}

/* SAME VALUE, WRITTEN TWO WAYS, IS STILL THE SAME VALUE.
 *
 * Amazon sends 20 for a dimension the generator stored as "20.0". Comparing
 * those as text marks every dimension on every listing as "differs", which
 * would make the whole feature noise. Numbers compare as numbers; everything
 * else compares exactly, because Amazon's enums ARE case-sensitive and
 * "Grams" vs "grams" is a real difference it will reject. */
function lvSame(a, b){
  const x = String(a == null ? "" : a).trim();
  const y = String(b == null ? "" : b).trim();
  if(x === y) return true;
  if(x === "" || y === "") return false;
  const nx = Number(x), ny = Number(y);
  return Number.isFinite(nx) && Number.isFinite(ny) && nx === ny;
}

/* "" (nothing to say) | "same" | "differs" | "live_only" | "app_only" */
function lvVerdict(sku, key, localVal){
  const L = lvGet(sku);
  if(!L || L.state !== "ok") return "";
  const has = Object.prototype.hasOwnProperty.call(L.values||{}, key);
  const lv  = has ? L.values[key] : "";
  const app = String(localVal == null ? "" : localVal).trim();
  if(!has && !app) return "";
  if(!has) return "app_only";
  if(!app) return "live_only";
  return lvSame(app, lv) ? "same" : "differs";
}

/* The tag that sits on the cell's label line. Ready-made HTML, handed to
 * dwCell the same way dwNestCell already takes reqMark -- so the wording lives
 * here rather than being rebuilt from a flag at the far end. */
function lvTag(sku, key, localVal){
  const v = lvVerdict(sku, key, localVal);
  if(!v) return "";
  const L = lvGet(sku);
  const multi = (L.multi||{})[String(key).split(".")[0]] || 0;
  if(multi){
    return '<span class="lv-tag lv-multi" title="Amazon holds ' + multi
         + ' values for this attribute. Only the first is shown, and it is not '
         + 'editable here — saving one value would drop the rest on the next '
         + 'submit. Edit it in Seller Central.">' + multi + ' values on Amazon</span>';
  }
  if(v === "same")
    return '<span class="lv-tag lv-ok" title="This app and Amazon hold the same value.">matches Amazon</span>';
  if(v === "differs")
    return '<span class="lv-tag lv-diff" title="This app and Amazon disagree. The app’s value is in the box; Amazon’s is shown underneath.">differs from Amazon</span>';
  if(v === "live_only")
    return '<span class="lv-tag lv-live" title="Amazon has a value for this field and this app does not.">only on Amazon</span>';
  return '<span class="lv-tag lv-app" title="This app has a value for this field and Amazon does not. It will be sent on the next submit.">not on Amazon</span>';
}

/* The line UNDER the control: Amazon's own value, and the button that takes it. */
function lvBelow(sku, key, localVal){
  const v = lvVerdict(sku, key, localVal);
  if(v !== "differs" && v !== "live_only") return "";
  const L = lvGet(sku);
  const lv = String(L.values[key]);
  const multi = (L.multi||{})[String(key).split(".")[0]] || 0;
  const shown = lv.length > 120 ? (lv.slice(0,120) + "…") : lv;
  return '<div class="lv-below">'
       + '<span class="lv-dot" title="Live on Amazon"></span>'
       + '<span class="lv-val" title="' + esc(lv) + '">' + esc(shown) + '</span>'
       + (multi ? '' :
          '<button class="lv-use" title="Copy Amazon’s value into this listing. '
          + 'Saves to the app only — nothing is sent to Amazon until you press Submit."'
          + ' onclick="lvUse(\'' + esc(sku) + '\',\'' + esc(key) + '\')">use this</button>')
       + '</div>';
}

/* Copy ONE live value into the row, through the same /edit every box uses. */
async function lvUse(sku, key){
  const L = lvGet(sku);
  if(!L || L.state !== "ok") return;
  const val = L.values[key];
  if(val == null) return;
  try{
    const j = await (await fetch("/edit", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify(acctBody({sku, target:"attr", key, value: val}))})).json();
    if(!j.ok){ toast("Save failed: " + (j.error||"")); return; }
    const r = ROWS.find(x => String(x.sku) === String(sku));
    if(r){ r.attributes = r.attributes || {}; r.attributes[key] = val; }
    toast("Saved ✓");
    if(typeof _rebuildDrawerData === "function") _rebuildDrawerData(sku);
  }catch(e){ toast("Save failed: " + e); }
}

/* Copy every field Amazon has that this listing does not.
 *
 * ONLY THE EMPTY ONES. A value already in the row is left exactly as it is,
 * even when Amazon disagrees with it -- overwriting those is the destructive
 * direction and is left as a per-field decision. */
async function lvFillEmpty(sku){
  const L = lvGet(sku);
  const r = ROWS.find(x => String(x.sku) === String(sku));
  if(!L || L.state !== "ok" || !r) return;
  const a = r.attributes || {};
  const todo = Object.keys(L.values).filter(k => {
    if((L.multi||{})[String(k).split(".")[0]]) return false;   // never the multis
    const cur = a[k];
    return cur == null || String(cur).trim() === "";
  });
  if(!todo.length){ toast("Nothing to fill — every field Amazon has is already set."); return; }
  const ok = await uiConfirm("Copy " + todo.length + " value(s) from Amazon into this "
    + "listing?\n\nOnly fields that are currently EMPTY are filled. Nothing is sent to "
    + "Amazon — this writes to the app, and takes effect on the next submit.");
  if(!ok) return;
  let done = 0, failed = 0;
  for(const k of todo){
    try{
      const j = await (await fetch("/edit", {method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify(acctBody({sku, target:"attr", key:k, value:L.values[k]}))})).json();
      if(j.ok){ r.attributes = r.attributes || {}; r.attributes[k] = L.values[k]; done++; }
      else failed++;
    }catch(e){ failed++; }
  }
  toast("Filled " + done + " field(s)" + (failed ? (", " + failed + " failed") : ""));
  if(typeof _rebuildDrawerData === "function") _rebuildDrawerData(sku);
}

/* The strip above the attribute grid: where these values came from, how they
 * compare, and the two things you can do about it. */
function lvBanner(r){
  if(!lvWants(r)) return "";
  const sku = String(r.sku);
  const L = lvGet(sku);
  if(!L) return "";
  if(L.state === "loading")
    return '<div class="lv-bar loading"><span class="lv-spin"></span>'
         + 'Reading this listing from Amazon…</div>';
  if(L.state === "gone")
    return '<div class="lv-bar gone">Amazon has no listing with this SKU on this account, '
         + 'so there is nothing live to compare. The values below are this app’s own.'
         + '<button class="lv-refresh" onclick="lvRefresh(\'' + esc(sku) + '\')">check again</button></div>';
  if(L.state === "error")
    return '<div class="lv-bar err">Could not read this listing from Amazon: '
         + esc(L.error||"") + '. The values below are this app’s own — they are '
         + 'not wrong, they are just not confirmed against Amazon.'
         + '<button class="lv-refresh" onclick="lvRefresh(\'' + esc(sku) + '\')">try again</button></div>';

  const a = r.attributes || {};
  const vals = L.values || {};
  let same = 0, diff = 0, only = 0;
  Object.keys(vals).forEach(k => {
    const v = lvVerdict(sku, k, a[k]);
    if(v === "same") same++; else if(v === "differs") diff++; else if(v === "live_only") only++;
  });
  const bits = [];
  if(same) bits.push('<span class="lv-cnt ok">' + same + ' match</span>');
  if(diff) bits.push('<span class="lv-cnt diff">' + diff + ' differ</span>');
  if(only) bits.push('<span class="lv-cnt live">' + only + ' only on Amazon</span>');
  if(!bits.length) bits.push('<span class="lv-cnt">Amazon returned no attributes for this SKU</span>');

  const issues = (L.issues||[]).filter(i => String(i.severity||"").toUpperCase() === "ERROR");
  return '<div class="lv-bar ok">'
    + '<span class="lv-dot"></span><b>Live on Amazon</b>'
    + (L.amazon_status ? '<span class="lv-status">' + esc(L.amazon_status) + '</span>' : "")
    + bits.join("")
    + (only ? '<button class="lv-fill" onclick="lvFillEmpty(\'' + esc(sku) + '\')">'
              + 'Fill ' + only + ' empty field(s) from Amazon</button>' : "")
    + '<button class="lv-refresh" onclick="lvRefresh(\'' + esc(sku) + '\')">refresh</button>'
    + '</div>'
    + (issues.length
        ? '<div class="lv-issues"><b>Amazon reports ' + issues.length + ' error(s) on this listing:</b>'
          + issues.slice(0,6).map(i => '<div class="lv-issue">' + esc(i.message||"")
              + (i.attributes && i.attributes.length
                  ? ' <span class="lv-issf">(' + esc(i.attributes.join(", ")) + ')</span>' : "")
              + '</div>').join("")
          + '</div>'
        : "")
    + ((L.skipped||[]).length
        ? '<div class="lv-note">Price and stock are not listed as attributes here — they '
          + 'have their own rows above (' + esc((L.skipped||[]).join(", ")) + ').</div>'
        : "");
}
