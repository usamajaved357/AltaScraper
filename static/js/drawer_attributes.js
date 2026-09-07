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
/* IS THIS YOUR PRODUCT, OR YOUR OFFER ON SOMEBODY ELSE'S?
 *
 *     "the items i listed were same in both, but i did mee too on nestwell
 *      goods so they were not used using the app"
 *
 * The drawer showed both identically, and that is how twenty-six me-too offers
 * were once diagnosed as "misfiled under the wrong account" and nearly moved --
 * which would have taken the other account's own listings away.
 *
 * The distinction matters every time somebody edits: on an offer, the title,
 * the images and the description belong to the ASIN and cannot be changed from
 * here however many times Save is pressed. Price, stock and handling are yours.
 * Saying so up front is the difference between a screen that refuses and one
 * that explains. */
function lvShapeBar(L){
  const s = L && L.shape;
  if(!s || s.kind === "unknown") return "";
  if(s.kind !== "offer") return "";          // your own product: nothing to warn
  return '<div class="lv-issues" style="border-left:3px solid var(--warn)">'
    + '<b>This is a me-too offer, not your own product listing.</b>'
    + (s.asin ? ' <code>' + esc(s.asin) + '</code>' : "")
    + '<div class="lv-issue" style="opacity:.85">' + esc(s.why || "") + '</div>'
    + '</div>';
}

/* One of Amazon's errors, with the two values named.
 *
 *     "Row 38 -> ASIN B0H8TFYNB9 -> 'number_of_items' (Merchant 1 / Amazon 2)
 *      Catalogue ASIN is a 2-PACK; we submit a 1-pack."
 *
 * Amazon's message says the values differ and leaves you to work out which is
 * whose. The one that matters is that the FIRST is yours and the second is the
 * ASIN's -- and the correct response is usually NOT to copy the ASIN's, because
 * a mismatch on pack size normally means the barcode matched the wrong product
 * entirely. Copying it would build a piggyback listing on somebody else's ASIN,
 * which Rule 1 forbids.
 *
 * THE ATTRIBUTE NAME COMES FROM THE STRUCTURED FIELD, never the prose. Reading
 * it out of the message text is exactly the "The"/"Your" phantom-field bug the
 * parsing rule in CLAUDE.md was written for; the numbers below are read from
 * the text only after the name has come from `attributes`. */
function lvIssueHtml(i){
  const names = (i.attributes || []).filter(Boolean);
  let extra = "";
  // Amazon writes these as "... Merchant: 1 ... Amazon: 2" or "(1 / 2)". Only
  // read them when Amazon named an attribute in its structured field -- prose
  // alone is never enough to label a value.
  if(names.length){
    const m = String(i.message || "")
      .match(/merchant[^0-9a-z]{0,4}([\w.\-]+)[\s\S]{0,40}?amazon[^0-9a-z]{0,4}([\w.\-]+)/i);
    if(m){
      extra = '<div class="lv-issue" style="opacity:.85">'
        + '<b>Yours:</b> ' + esc(m[1])
        + ' &nbsp;·&nbsp; <b>The ASIN\'s:</b> ' + esc(m[2])
        + '<div style="margin-top:3px">A mismatch here usually means the '
        + 'barcode matched a DIFFERENT product, not that your value is wrong. '
        + 'Copying the ASIN\'s value would join somebody else\'s product rather '
        + 'than fix yours.</div></div>';
    }
  }
  return '<div class="lv-issue">' + esc(i.message || "")
    + (names.length ? ' <span class="lv-issf">(' + esc(names.join(", "))
                      + ')</span>' : "")
    + '</div>' + extra;
}

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
                         // Whether this is your own product or an offer on
                         // somebody else's ASIN. The two were indistinguishable
                         // here, which is how a set of me-too offers was once
                         // diagnosed as "misfiled" and nearly moved.
                         shape:j.shape||null,
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

/* THE OTHER DIRECTION: send what this app holds TO Amazon.
 *
 *     "also see other buttons which seems like calling amazon but donot call
 *      amazon for a change"
 *
 * Measured across the whole app: of 264 routes the browser posts to, ELEVEN
 * change anything on Amazon. Everything else is local, and the one that misled
 * hardest was the ordinary field edit -- typing a Country of Origin or a
 * Dangerous Goods value on a LIVE listing saved it here and left Amazon
 * untouched. Price and handling had push buttons; nothing else did, so the same
 * gesture reached Amazon for two fields and stopped at the app for the rest.
 *
 * lvVerdict already knows which fields differ -- the bar has been counting them
 * as "N differ" all along -- so the information was on screen and there was
 * nothing to do with it. This is that count, made actionable.
 *
 * IT PUSHES ONLY WHAT DIFFERS, and names every field before it sends. A patch
 * is not reversible by sending it again; it is reversible only by knowing what
 * the old value was, so the confirmation lists both.
 *
 * /optimize/push is the existing gated patch path (Rule 12): it takes a map of
 * approved fields, builds the JSON Patch, and reports Amazon's own verdict
 * rather than assuming success. Nothing new talks to Amazon here.
 */
function lvDiffFields(sku){
  const L = lvGet(sku);
  const r = (typeof ROWS !== "undefined" && ROWS.find)
    ? ROWS.find(x => String(x.sku) === String(sku)) : null;
  if(!L || L.state !== "ok" || !r) return [];
  const a = r.attributes || {};
  // Only what THIS app has a value for. A field that is empty here and set on
  // Amazon is "only on Amazon" and belongs to the Fill button above -- pushing
  // an empty over Amazon's value would delete content nobody asked to remove.
  return Object.keys(a).filter(k => {
    if((L.multi||{})[String(k).split(".")[0]]) return false;   // never the multis
    if(String(a[k] == null ? "" : a[k]).trim() === "") return false;
    return lvVerdict(sku, k, a[k]) === "differs";
  });
}

async function lvPushChanges(sku){
  sku = String(sku);
  const L = lvGet(sku);
  const r = (typeof ROWS !== "undefined" && ROWS.find)
    ? ROWS.find(x => String(x.sku) === String(sku)) : null;
  if(!L || !r) return;
  const todo = lvDiffFields(sku);
  if(!todo.length){ toast("Nothing to send — Amazon already has these values."); return; }

  const a = r.attributes || {};
  const lines = todo.slice(0, 12).map(k =>
    "  • " + k + ":  " + String((L.values||{})[k] == null ? "—" : (L.values||{})[k])
    + "  →  " + String(a[k]));
  const more = todo.length > 12 ? ("\n  …and " + (todo.length - 12) + " more") : "";
  if(!await uiConfirm(
      "Send " + todo.length + " change(s) to Amazon for " + sku + "?\n\n"
      + "Amazon's value → yours:\n" + lines.join("\n") + more
      + "\n\nThis changes the LIVE listing. Amazon publishes in its own time, "
      + "usually within 5–30 minutes.")) return;

  const changes = {};
  todo.forEach(k => { changes[k] = a[k]; });
  try{
    const body = (typeof acctBody === "function")
      ? acctBody({sku: sku, changes: changes, confirmed: true,
                  product_type: L.product_type || r.product_type || "",
                  marketplace: (typeof rowMkt === "function") ? rowMkt(r) : ""})
      : {sku: sku, changes: changes, confirmed: true};
    // /optimize/push reads the account from `id`, not `account`.
    if(body.account && !body.id) body.id = body.account;
    const j = await (await fetch("/optimize/push", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)})).json();
    if(j && j.ok){
      toast("Amazon accepted " + todo.length + " change(s)");
      // WHAT AMAZON HOLDS HAS CHANGED, so the comparison this bar is built on
      // is now stale. Re-read rather than assuming it took: ACCEPTED means
      // Amazon received the patch, not that it has published it.
      lvRefresh(sku);
    }else if(j && j.unknown){
      await uiAlert("Amazon replied, but not with a verdict this app could read.\n\n"
        + "Nothing here claims it worked. Press Sync in a few minutes — that "
        + "reads the listing back from Amazon and is the only thing that settles it.");
    }else{
      const iss = ((j && j.issues) || []).slice(0, 5)
        .map(i => "  – " + (i.message || i.code || "")).join("\n");
      await uiAlert("Amazon refused the change:\n\n"
        + ((j && j.error) || "no reason given") + (iss ? ("\n\n" + iss) : ""));
    }
  }catch(e){ toast("Could not send: " + e); }
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
  // NOT SIMPLY "differ" ANY MORE. A difference on a LIVE listing means a value
  // saved here that Amazon has never been told about -- which is the thing that
  // was invisible: "buttons which seems like calling amazon but donot call
  // amazon for a change". Naming it that way is the whole point; a neutral
  // "differ" reads like a curiosity rather than unsent work.
  const _unsent = lvDiffFields(sku).length;
  const bits = [];
  if(same) bits.push('<span class="lv-cnt ok">' + same + ' match</span>');
  if(diff) bits.push('<span class="lv-cnt diff" title="Saved in this app and not '
      + 'the same on Amazon. Editing a field here does not send it — use the '
      + 'button beside this to push them.">' + diff + ' differ</span>');
  if(only) bits.push('<span class="lv-cnt live">' + only + ' only on Amazon</span>');
  if(!bits.length) bits.push('<span class="lv-cnt">Amazon returned no attributes for this SKU</span>');

  const issues = (L.issues||[]).filter(i => String(i.severity||"").toUpperCase() === "ERROR");
  return '<div class="lv-bar ok">'
    + '<span class="lv-dot"></span><b>Live on Amazon</b>'
    + (L.amazon_status ? '<span class="lv-status">' + esc(L.amazon_status) + '</span>' : "")
    + bits.join("")
    + (only ? '<button class="lv-fill" onclick="lvFillEmpty(\'' + esc(sku) + '\')">'
              + 'Fill ' + only + ' empty field(s) from Amazon</button>' : "")
    // THE REVERSE, which never existed. "Fill from Amazon" has always been here;
    // there was no way to send the other way, so an edit to a live listing sat
    // in this app indefinitely with nothing saying so.
    + (_unsent ? '<button class="lv-push" onclick="lvPushChanges(\'' + esc(sku) + '\')"'
              + ' title="Patch these fields on the live Amazon listing. Only the '
              + 'ones that differ are sent, and you see each one before it goes.">'
              + 'Send ' + _unsent + ' change(s) to Amazon</button>' : "")
    + '<button class="lv-refresh" onclick="lvRefresh(\'' + esc(sku) + '\')">refresh</button>'
    + '</div>'
    + lvShapeBar(L)
    + (issues.length
        ? '<div class="lv-issues"><b>Amazon reports ' + issues.length + ' error(s) on this listing:</b>'
          + issues.map(lvIssueHtml).slice(0,6).join("")
          + '</div>'
        : "")
    + ((L.skipped||[]).length
        ? '<div class="lv-note">Price and stock are not listed as attributes here — they '
          + 'have their own rows above (' + esc((L.skipped||[]).join(", ")) + ').</div>'
        : "");
}
