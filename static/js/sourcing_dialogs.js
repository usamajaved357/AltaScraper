// static/js/sourcing_dialogs.js -- the Repricer's dialogs, track-all, clearing suppliers and uploads. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

// A small modal with an OK that can refuse to close. prompt() cannot show two
// boxes at once, which is the whole reason this exists.
/* `onCancel` matters when the caller is AWAITING an answer.
 *
 * Without it, dismissing the box resolved nothing and the promise behind it
 * never settled -- so cancelling the min-price upload left the whole flow
 * hanging, with the file already chosen and no way back except a reload.
 * Called for the Cancel button, a click on the surround, and Escape, because
 * all three mean the same thing. */
function _srcModal(title, bodyHtml, onOk, onCancel){
  const old = document.getElementById("srcmodal");
  if(old) old.remove();
  const wrap = document.createElement("div");
  wrap.id = "srcmodal";
  wrap.className = "modalwrap";
  wrap.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.55);"
    + "display:flex;align-items:center;justify-content:center;z-index:9000";
  wrap.innerHTML = '<div class="panelcard roomy" style="max-width:560px;width:92%">'
    + '<div style="font-size:14px;font-weight:600;margin-bottom:10px">'
    + _sesc(title) + '</div>'
    + bodyHtml
    + '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">'
    + '<button class="db-chip" id="srcmodal_cancel">Cancel</button>'
    + '<button class="db-chip" id="srcmodal_ok" style="background:var(--accent);'
    + 'color:var(--paper);border-color:var(--accent)">Save</button></div></div>';
  document.body.appendChild(wrap);
  let settled = false;
  const close = function(cancelled){
    if(settled) return;
    settled = true;
    document.removeEventListener("keydown", key, true);
    wrap.remove();
    if(cancelled && typeof onCancel === "function") onCancel();
  };
  const key = function(e){
    if(e.key === "Escape"){ e.preventDefault(); close(true); }
  };
  document.addEventListener("keydown", key, true);
  wrap.querySelector("#srcmodal_cancel").onclick = function(){ close(true); };
  wrap.onclick = function(e){ if(e.target === wrap) close(true); };
  // ONE SAVE AT A TIME, AND A FAILED ONE SAYS SO (repricer bug hunt, 30 Sep
  // 2026). The button stayed live, so a double click saved twice; and a network
  // error or a non-JSON reply threw out of onOk, leaving the dialog open with
  // no message at all. Every dialog on this screen goes through here.
  const okBtn = wrap.querySelector("#srcmodal_ok");
  // The account the dialog was OPENED in. Its saves read the account at Save
  // time, so a switch while it was open would have written this dialog's
  // values (another account's floor, say) into the new one.
  const openScope = _srcScopeNow();
  okBtn.onclick = async function(){
    if(okBtn.disabled) return;
    if(!_srcStillIn(openScope)){
      if(typeof toast === "function")
        toast("The account or marketplace changed while this was open, so nothing was saved.");
      close(true);
      return;
    }
    const label = okBtn.innerHTML;
    okBtn.disabled = true;
    okBtn.innerHTML = '<span class="genspin"></span> Saving…';
    let ok = false;
    try{ ok = await onOk(); }
    catch(e){
      ok = false;
      if(typeof toast === "function")
        toast("Not saved: " + String((e && e.message) || e || "the server did not answer"));
    }
    if(ok !== false){ close(false); return; }   // a refusal keeps the boxes and their values
    okBtn.disabled = false;
    okBtn.innerHTML = label;
  };
  const first = wrap.querySelector("input");
  if(first) first.focus();
}

/* A confirmation in the app's own skin, awaited like confirm() but not white.
 *
 *     "i dont like this white appearing messages over the window. modern apps
 *      do not behave like this."
 *
 * confirm() cannot be styled, appears attached to the browser rather than to the
 * page, and on a dark app reads as an error from somewhere else. This is the
 * same shape -- resolves true or false, blocks nothing -- so a call site only
 * has to gain an `await`.
 *
 * The body is plain text, wrapped here, because every caller is writing a
 * sentence rather than markup and one of them writing a tag by accident should
 * not be able to put it on the page.
 */
function srcConfirm(o){
  const opt = o || {};
  // ONE implementation, in static/js/dialog.js. This keeps the shape eleven
  // call sites on this screen already use -- {title, body, confirm, risk} --
  // and hands it to the app-wide one, so there is a single answer to what
  // Escape does, what a click on the surround does, and which button is
  // focused (CLAUDE.md Rule 12).
  return uiConfirm(String(opt.body || ""), {
    title: opt.title || "Are you sure?",
    ok: opt.confirm || "Yes",
    danger: !!opt.risk
  });
}

// Start tracking everything that is not tracked yet.
//
// The supplier link is not asked for: the app recorded where each listing came
// from when it built it, so it can attach them itself. What it CANNOT do is
// invent one for a listing whose source was an Amazon page -- that is the
// competitor the listing was modelled on, not where the stock is bought -- so
// those are enrolled and reported rather than quietly skipped.
async function sourcingTrackAll(btn){
  const old = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled = true; btn.innerHTML = '<span class="genspin"></span> reading your listings…'; }
  try{
    const cand = await (await fetch(_srcUrl("/sourcing/candidates"))).json();
    const items = (cand && cand.items) || [];
    const todo = items.filter(function(x){ return !x.enrolled; }).map(function(x){ return x.sku; });
    if(!items.length){
      toast((cand && cand.note) || "No live listings to track — press Sync on Listings first.");
      return;
    }
    if(!todo.length){ toast("Every live listing is already being tracked."); return; }
    if(!await srcConfirm({
        title: "Start tracking " + todo.length + " listing"
             + (todo.length === 1 ? "" : "s") + "?",
        body: "This records what each one costs at its supplier, every 4 hours.\n\n"
            + "It does NOT change any price — auto-pricing stays "
            + (SRC_MASTER ? "as it is" : "off") + ", and each SKU still has to "
            + "be armed separately before anything can reach Amazon.",
        confirm: "Start tracking"})) return;
    if(btn) btn.innerHTML = '<span class="genspin"></span> tracking ' + todo.length + '…';
    const j = await (await fetch("/sourcing/enrol_bulk",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({skus: todo})})).json();
    if(!j.ok){ toast(j.error||"Could not enroll"); return; }
    // Say what did NOT work as loudly as what did. A bulk action that reports
    // only its successes is how you end up with SKUs quietly tracking nothing.
    let msg = "Now tracking " + j.enrolled + " listing" + (j.enrolled===1?"":"s")
            + " — " + j.linked + " with the supplier the app already had on file";
    if(j.no_link) msg += ", " + j.no_link + " still need a supplier link";
    toast(msg + ".");
    // NOT stored as the "last sheet upload": this is not one, and its bare
    // list of rows drew "undefined attached" there (repricer bug hunt).
    sourcingLoad();
  }catch(e){ toast(String(e)); }
  finally{ if(btn){ btn.disabled = false; btn.innerHTML = old; } }
}
let SRC_LASTBULK = null;

// SUPPLIERS FROM A SHEET.
//
// "the repricer tool give me an option to upload a sheet containing the sku's or
//  original asins of the item, to add their suppliers through a sheet upload"
//
/* ---- TAKING THEM ALL OFF AGAIN ---------------------------------------------
 *
 *     "I also want to delete all the suppliers from the repricer ... so i can
 *      add new suppliers"
 *
 * Suppliers could be added one at a time and by the sheetful, and removed only
 * one at a time from inside an expanded row -- so replacing a whole set meant
 * opening fifty-five rows and clicking fifty-five times.
 *
 * THE WARNING NAMES THREE NUMBERS, not one. "Delete 55 suppliers" understates
 * it: the price readings recorded against them go too, and those cannot be
 * fetched again -- a supplier's price on a day nobody was watching is gone. And
 * it says what SURVIVES, because that is the point of the request: the SKUs
 * stay tracked and their targets stay set, so a new sheet works immediately.
 */
async function sourcingClearSuppliers(){
  let c = null;
  try{
    // THE TAB'S ACCOUNT, like every other /sourcing call (_srcUrl). This used
    // to send none and get the server's open account -- once _where() began
    // reading ?account=, that meant counting and then DELETING another tab's
    // account's suppliers (batch 1 review).
    c = await (await fetch(_srcUrl("/sourcing/sources/count"))).json();
    if(!c || !c.ok){ toast((c && c.error) || "Could not read the suppliers."); return; }
  }catch(e){ toast(String(e)); return; }

  const n = Number(c.sources) || 0;
  if(!n){
    // A confirmation offering to delete nothing teaches people to dismiss
    // confirmations.
    toast("There are no supplier links on " + [c.account, c.marketplace].filter(Boolean).join(" · ")
          + " — nothing to clear. Add some with “Suppliers from a sheet”.");
    return;
  }

  // srcConfirm, not the browser's confirm(): this page deliberately has none
  // left, and a white system dialog in the middle of a dark screen is the one
  // thing on it that does not look like the app.
  if(!await srcConfirm({
      title: "Delete all " + n + " supplier link" + (n === 1 ? "" : "s") + "?",
      body: "For " + [c.account, c.marketplace].filter(Boolean).join(" · ")
          + ". They are attached to " + (c.skus || 0) + " SKU"
          + ((c.skus === 1) ? "" : "s") + ", and " + (c.checks || 0)
          + " recorded price reading" + ((c.checks === 1) ? "" : "s")
          + " will go with them — a supplier's price on a day nobody was "
          + "watching cannot be fetched again.\n\n"
          + "The SKUs stay tracked and their profit targets stay set, so a new "
          + "supplier sheet works straight away.\n\n"
          + "Other accounts and other marketplaces are not touched. Nothing on "
          + "Amazon changes.",
      confirm: "Delete them all", risk: true})){
    return;
  }

  try{
    const r = await fetch(_srcUrl("/sourcing/sources/clear"), {
      method: "POST", headers: {"Content-Type": "application/json"},
      // The number agreed to goes back with it: if a sweep finished while the
      // dialog was open, the server refuses rather than deleting a different
      // amount from the one shown.
      body: JSON.stringify({expect: n})});
    const j = await r.json();
    if(!j || !j.ok){ toast((j && j.error) || "Nothing was deleted."); return; }
    toast(j.note || (j.deleted + " supplier link(s) deleted"));
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

// The report is shown ROW BY ROW, not as a total. A bulk import that says "38
// attached" and nothing else is how twelve silently-skipped rows become "the
// repricer is not working" a fortnight later.
async function sourcingUpload(inp){
  const f = inp && inp.files && inp.files[0];
  if(!f) return;
  const host = document.getElementById("srcbody");
  const fd = new FormData();
  fd.append("file", f);
  toast("Reading " + f.name + "…");
  let j;
  try{
    j = await (await fetch(_srcUrl("/sourcing/sources/upload"), {method: "POST", body: fd})).json();
  }catch(e){ toast(String(e)); return; }
  finally{ inp.value = ""; }

  if(!j || !j.ok){ toast((j && j.error) || "Could not read that sheet"); return; }
  SRC_LASTBULK = j;
  toast(j.attached + " supplier" + (j.attached === 1 ? "" : "s") + " attached"
        + (j.already ? (", " + j.already + " already had one") : "")
        + (j.skipped ? (", " + j.skipped + " skipped") : "") + ".");
  sourcingLoad();
}

// What the last upload did to each row, offered rather than forced: it is long,
// and it is only interesting until you have read it.
function sourcingUploadReport(){
  const j = SRC_LASTBULK;
  // Only a sheet upload's reply is a report; anything else draws nothing.
  if(!j || Array.isArray(j) || j.attached == null) return '';
  const bad = (j.rows || []).filter(function(r){ return r.status !== "attached"; });
  return '<details class="foldgroup" style="margin-bottom:12px"><summary>'
    + '<i class="ti ti-table-import"></i> Last sheet upload &mdash; '
    + j.attached + ' attached'
    + (j.already ? (', ' + j.already + ' already had one') : '')
    + (j.skipped ? ('<b style="color:var(--gold)">, ' + j.skipped + ' skipped</b>') : '')
    + '<span class="cc"> — matched on "' + _sesc((j.columns||{}).sku || (j.columns||{}).asin || '?')
    + '" and "' + _sesc((j.columns||{}).url || '?') + '"</span></summary>'
    + (bad.length
        ? bad.map(function(r){
            return '<div class="cc" style="font-size:11.5px;padding:3px 0;'
              + 'border-top:1px solid var(--line2)">line ' + r.line + ' &middot; '
              + _sesc(r.sku || r.asin || '(no key)') + ' &mdash; ' + _sesc(r.note) + '</div>';
          }).join("")
        : '<div class="cc" style="font-size:11.5px;padding:4px 0">Every row went in.</div>')
    + '</details>';
}
