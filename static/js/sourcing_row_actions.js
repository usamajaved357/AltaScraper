// static/js/sourcing_row_actions.js -- per-row price, direction, buffer, check now, the source picker, enrol/unenrol. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* Which way a NEWLY tracked SKU may move. Global; changes nothing existing. */
async function sourcingDefaultDirection(){
  let cur = "up_only";
  try{
    const g = await (await fetch("/sourcing/default_direction"
                                 + _srcUrl(""))).json();
    if(g && g.ok) cur = g.direction;
  }catch(e){ /* the shown default stands */ }
  const row = function(v, label, why){
    return '<label class="rp-mi" style="cursor:pointer;align-items:flex-start">'
      + '<input type="radio" name="src_ddir" value="' + v + '"'
      + (cur === v ? ' checked' : '') + ' style="margin-top:3px">'
      + '<span><b>' + label + '</b><br><span class="cc" '
      + 'style="font-size:11px;line-height:1.5">' + why + '</span></span></label>';
  };
  _srcModal("Which way a newly tracked SKU may move",
    '<div style="font-size:12.5px">'
    + '<p>Applies to SKUs enrolled <b>from now on</b>. Nothing already tracked '
    + 'changes -- each keeps whatever its own Direction pill says.</p>'
    + row('up_only', 'Up only',
          'Never lowered. A cheaper supplier becomes margin instead of a '
          + 'discount. This is the default, and it is the reason a 0% profit '
          + 'target is safe: the floor can only ever push a price up.')
    + row('up_and_down', 'Up and down',
          'Follows the supplier both ways.')
    + row('match_floor', 'Match the floor exactly',
          'Always on the calculated floor, ignoring any held price.')
    + '</div>',
    async function(){
      const sel = document.querySelector('input[name="src_ddir"]:checked');
      if(!sel) return false;
      const jr = await (await fetch("/sourcing/default_direction",
        {method: "POST", headers: {"Content-Type": "application/json"},
         body: _srcBody({direction: sel.value})})).json();
      if(!jr.ok){ toast(jr.error || "Could not save"); return false; }
      toast(jr.note || "Saved");
      await sourcingLoad(true);
      return true;
    });
}

/* A PRICE SET BY HAND, pushed to Amazon now.
 *
 *     "This lets the user adjust prices without leaving the app or going to
 *      Seller Central. The repricer respects the manual change and only acts
 *      again if costs force it."
 *
 * THE ONE CONTROL ON THIS SCREEN THAT CHANGES A LIVE PRICE ON DEMAND, so it
 * says so before it is used rather than afterwards: the hint under the box
 * names Amazon and says it is immediate. Everything else here decides and
 * waits for the four-hourly run.
 *
 * The FLOOR is enforced on the server, not here -- a check that only exists in
 * the browser is a check anybody can skip. This copy is so the answer arrives
 * before the round trip, not instead of it.
 */
async function sourcingManualPrice(sku, btn){
  const row = (SRC_ROWS || []).filter(function(r){ return r.sku === sku; })[0];
  const now = ((row || {}).current || {}).price;
  const floor = (SRC_ROW_RULES[sku] || (row || {}).rule || {}).min_price;
  await uiInline(btn, {
    title: "Set the price on Amazon",
    prefix: _srcSym(),
    type: "number", min: 0, step: "0.01",
    value: (now == null ? "" : now),
    hint: "Sent to Amazon straight away, without waiting for the next check. "
        + (floor != null
            ? "It cannot go below the " + _smoney(floor) + " floor you set. "
            : "")
        + "The repricer then treats this as the current price.",
    onSave: async function(v){
      const t = String(v).trim();
      const n = parseFloat(t);
      if(!(n > 0)) return "That needs to be an amount above zero, e.g. 18.47";
      if(floor != null && n < +floor - 0.001)
        return "That is below the " + _smoney(floor) + " floor you set for "
             + "this SKU. Change the floor first if you mean it.";
      if(now != null && Math.abs(n - now) < 0.005)
        return "That is what it already sells for.";
      try{
        const j = await (await fetch("/sourcing/manual_price", {method: "POST",
          headers: {"Content-Type": "application/json"},
          body: _srcBody({sku: sku, price: t})})).json();
        if(!j.ok) return j.error || "Amazon refused that price.";
        toast(j.note || ("Set to " + _smoney(n)));
        await sourcingLoad(true);
        return "";
      }catch(e){ return String((e && e.message) || e); }
    }
  });
}

/* WHICH WAY A SKU'S PRICE MAY MOVE.
 *
 *     "Clicking the pill cycles through options (or opens a small dropdown)"
 *
 * A DROPDOWN, not a cycle. Cycling is fine for two states; with three, getting
 * from "up only" to "match floor" means passing THROUGH "up and down" -- and
 * each step here is a saved setting that changes what the repricer will do to
 * a live price. Passing through a state you did not want, on a control that
 * writes as it goes, is not a thing to build on a screen that sets prices.
 *
 * The three are spelled out with what each one DOES, because the names alone
 * do not say which of them can lose you money.
 */
async function sourcingDirection(sku, btn){
  const cur = String((SRC_ROW_RULES[sku] || {}).direction || 'up_only');
  const row = function(v, label, why){
    return '<label class="rp-mi" style="cursor:pointer;align-items:flex-start">'
      + '<input type="radio" name="src_dir" value="' + v + '"'
      + (cur === v ? ' checked' : '') + ' style="margin-top:3px">'
      + '<span><b>' + label + '</b><br>'
      + '<span class="cc" style="font-size:11px;line-height:1.5">' + why
      + '</span></span></label>';
  };
  _srcModal("Which way may this price move?",
    '<div style="font-size:12.5px">'
    + row('up_only', 'Up only',
          'Never lowered. If the rules work out a floor below what it sells '
          + 'for today, nothing is changed -- a cheaper supplier becomes '
          + 'margin instead of a discount. This is the default.')
    + row('up_and_down', 'Up and down',
          'Follows the supplier both ways. A cheaper supplier means a cheaper '
          + 'price, which wins the buy box more often and earns less on each '
          + 'sale.')
    + row('match_floor', 'Match the floor exactly',
          'Always sits on the calculated floor. This also ignores any held '
          + 'price you have set, because a hold is a floor ABOVE the computed '
          + 'one and both cannot be honoured at once.')
    + '<div class="cc" style="font-size:11px;margin-top:8px;line-height:1.5">'
    + 'The minimum price still applies whichever you pick: nothing is ever '
    + 'priced below it.</div></div>',
    async function(){
      const sel = document.querySelector('input[name="src_dir"]:checked');
      if(!sel) return false;
      const err = await sourcingSaveRule(sku, {direction: sel.value},
        {up_only: 'This SKU will only ever be priced UP',
         up_and_down: 'This SKU will follow its supplier both ways',
         match_floor: 'This SKU will sit exactly on its floor'}[sel.value]);
      if(err){ toast(err); return false; }
      return true;
    });
}

/* EXTRA HANDLING DAYS -- for one SKU, for the account, or for every ticked SKU.
 *
 *     "Label it 'Extra handling days' with a tooltip: 'Added on top of the
 *      calculated handling time. Use for slow suppliers.'"
 *     "I can add +1, +2, or +3 of my own choice by bulk-selecting them"
 *     "I should be able to override the default setting by selecting and
 *      changing things in it" (owner, 27 Oct 2026)
 *
 * ONE DIALOG FOR ALL THREE, so the pill, the ⋯ menu and the selection bar
 * offer the same choices and save the same way. A SKU's "Default" is a NULL
 * on its own row -- it then follows the account's number (sku '' in
 * sourcing_rules), which the server lays underneath it (source_repo.rule_for).
 *
 * This is the only setting that makes a promise LONGER than the supplier's
 * own: each day is a day later delivery date on the listing.
 */
/* THE TWO FACTS EVERY Extra handling control needs, read in ONE place each
 * (Rule 12): the account's number (its sku '' row, SRC_RULE) and whether a
 * row's number is its own -- true / false, or null when the server could not
 * say (own_rule null), which every caller must show without claiming either. */
function _srcAcctBuffer(){
  return (typeof SRC_RULE !== "undefined" && SRC_RULE)
       ? (+SRC_RULE.handling_buffer_days || 0) : 0;
}

function _srcBufOwn(r){
  const o = (r || {}).own_rule;
  if(o == null) return null;
  return o.handling_buffer_days != null;
}

let SRC_BUF_ITEMS = [];
// Whether anything was chosen since the dialog opened. See `blank` below.
let SRC_BUF_TOUCHED = false;

function _srcBufferModal(title, cur, dflt, onSave, blank, note){
  // dflt is the account's number, or null when this IS the account's number
  // (it has nothing under it to fall back to).
  //
  // `blank`: the selection bar's dialog opens with NOTHING chosen and will not
  // save until something is. Opened on "Default", Save-without-looking would
  // put thirty SKUs that each had their own number back on the account's.
  SRC_BUF_ITEMS = (dflt == null ? [] : [{v: "d", label: "Default +" + dflt}])
    .concat([0, 1, 2, 3].map(function(n){ return {v: String(n), label: "+" + n}; }));
  SRC_BUF_TOUCHED = false;
  _srcModal(title,
    '<div style="font-size:12.5px;line-height:1.6">'
    + (note ? '<div class="cc" style="font-size:11.5px;margin:-4px 0 8px">'
              + note + '</div>' : '')
    + '<div id="src_bufseg">'
    + uiSeg(SRC_BUF_ITEMS, blank ? "" : (cur == null ? "d" : String(cur)), "_srcBufPick")
    + '</div>'
    + '<label for="src_buf" class="cc" style="font-size:11.5px;display:block;'
    + 'margin-top:10px">Or any number of days, 0 to 30</label>'
    + '<input id="src_buf" type="number" min="0" max="30" step="1" value="'
    + (cur == null ? '' : (+cur)) + '" placeholder="' + (dflt == null ? '0' : 'default')
    + '" oninput="_srcBufMark(this.value)" style="width:110px;margin-top:4px">'
    + '<p class="cc" style="font-size:11.5px;margin:10px 0 0">Added to the '
    + 'handling time worked out from the supplier. Each day is a day later '
    + 'delivery date on the listing.</p>'
    + '</div>',
    async function(){
      if(blank && !SRC_BUF_TOUCHED){
        toast("Choose Default, +0 to +3, or type a number of days");
        return false;
      }
      const el = document.getElementById("src_buf");
      const v = el ? String(el.value).trim() : "";
      // CHECKED ONCE, HERE, before anything is sent: a box the browser cannot
      // read reports "" -- which would mean "Default" -- and 31 would be
      // refused by the server once per selected SKU.
      if((el && el.validity && el.validity.badInput)
         || (v !== "" && !(/^\d+$/.test(v) && +v <= 30))){
        toast("Extra handling is a whole number of days, 0 to 30");
        return false;
      }
      return onSave(v === "" ? null : +v);
    });
}

function _srcBufPick(v){
  const el = document.getElementById("src_buf");
  if(el) el.value = (v === "d") ? "" : v;
  _srcBufMark(el ? el.value : "");
}

/* The chosen segment is lit IN PLACE: rebuilding the buttons destroyed the one
 * just pressed and dropped the keyboard focus out of the dialog. */
function _srcBufMark(v){
  SRC_BUF_TOUCHED = true;
  const key = String(v).trim() === "" ? "d" : String(parseInt(v, 10));
  document.querySelectorAll("#src_bufseg .seg > button").forEach(function(b, i){
    b.classList.toggle("on", !!SRC_BUF_ITEMS[i] && SRC_BUF_ITEMS[i].v === key);
  });
}

async function sourcingBuffer(sku, btn){
  const acct = _srcAcctBuffer();
  // Through sourcingSaveRule, the screen's one single-SKU save (it also keeps
  // the row's own values right until the quiet reload lands).
  const save = async function(v){
    const err = await sourcingSaveRule(sku, {handling_buffer_days: v},
      sku ? ("Extra handling: " + (v == null ? "default (+" + acct + ")" : "+" + v))
          : ("Default extra handling: +" + (v == null ? 0 : v)));
    if(err){ toast(err); return false; }
    return true;
  };
  if(!sku){
    // HOW FAR IT REACHES, said before Save: every SKU without a number of its
    // own. A typo here moves every one of them at the next push.
    const rows = SRC_ROWS || [];
    const follow = rows.filter(function(r){ return _srcBufOwn(r) === false; });
    const armed = follow.filter(function(r){ return r.mode === "live"; }).length;
    _srcBufferModal("Extra handling — account default", acct, null, save, false,
      'Followed by <b>' + follow.length + '</b> of ' + rows.length
      + ' tracked SKUs (' + armed + ' armed); the rest have their own.');
    return;
  }
  const row = (SRC_ROWS || []).filter(function(r){ return r.sku === sku; })[0] || {};
  // Unknown (null): open on the number in force rather than on "Default", so a
  // Save without touching anything cannot wipe an own number it did not know of.
  const own = _srcBufOwn(row);
  const cur = (own === null) ? (+((row.rule || {}).handling_buffer_days) || 0)
            : own ? row.own_rule.handling_buffer_days : null;
  _srcBufferModal("Extra handling days", cur, acct, save);
}

async function sourcingCheckNow(btn){
  if(btn){ btn.disabled=true; btn.innerHTML='<span class="genspin"></span> reading…'; }
  try{
    const j = await (await fetch("/sourcing/check",{method:"POST",
      headers:{"Content-Type":"application/json"}, body:_srcBody({})})).json();
    if(!j.ok){ toast(j.error||"Could not read the suppliers"); return; }
    const f = j.fetch || {};
    let msg = "Read "+(f.checked||0)+" supplier"+((f.checked===1)?"":"s");
    if(f.unreadable) msg += " · "+f.unreadable+" unreadable";
    if(f.ended) msg += " · "+f.ended+" ended";
    toast(f.note || msg);
    await sourcingLoad();
  }catch(e){ toast("Failed: "+((e&&e.message)||e)); }
  finally{ if(btn){ btn.disabled=false; btn.innerHTML='<i class="ti ti-refresh"></i> Re-read suppliers now'; } }
}

// Pick from what is actually on Amazon, rather than typing a SKU from memory.
// A typed SKU with a typo in it enrolls a product that does not exist: the sweep
// finds no sources, the screen shows a row that never decides anything, and
// nothing anywhere says the SKU was wrong.
async function sourcingAddPrompt(){
  const host = document.getElementById("srcpick");
  if(!host) return;
  host.style.display = "block";
  host.innerHTML = '<div class="cc" style="padding:14px"><span class="genspin"></span> Loading this account\'s live listings…</div>';
  await sourcingPickerLoad("");
}

// THE LATEST PICKER LOAD, and the account it was for. A reply from a switched-
// away account, or an older search that lands after a newer one, is dropped
// rather than painted -- its Enroll buttons would otherwise post A's SKUs under
// B (repricer bug hunt, 30 Sep 2026). screenstate.js bumps the number on a switch.
let SRC_PICK_SEQ = 0;
let SRC_PICK_SCOPE = null;
async function sourcingPickerLoad(q){
  const host = document.getElementById("srcpick");
  if(!host) return;
  const seq = ++SRC_PICK_SEQ;
  const sc = _srcScopeNow();
  const stale = function(){ return seq !== SRC_PICK_SEQ || !_srcStillIn(sc); };
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/candidates","q="+encodeURIComponent(q||"")))).json(); }
  catch(e){ if(stale()) return; host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc(String(e))+'</div>'; return; }
  if(stale()) return;
  SRC_PICK_SCOPE = sc;
  if(!j || !j.ok){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>'; return; }

  // ONLY THE ONES YOU CAN ACTUALLY ENROLL.
  //
  //     "Clicking '+ Enroll' shows ALL items including ones that are already
  //      enrolled (showing 'enrolled · 3 sources'). Only show items that are
  //      NOT yet enrolled."
  //
  // Right: this is a list you pick FROM, and an entry you cannot pick is not a
  // choice, it is something to read past. On this account 67 of the live
  // listings are already tracked, so the picker was mostly rows with a disabled
  // chip where the button should be.
  //
  // The count still says how many were left out, because "3 listings" with no
  // explanation on an account with seventy of them looks like a broken filter.
  const all = j.items || [];
  const items = all.filter(function(it){ return !it.enrolled; });
  const already = all.length - items.length;

  let h = '<div style="border:1px solid var(--line2);border-radius:8px;padding:12px;margin-bottom:12px">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
    + '<b style="font-size:13px">Enroll a listing</b>'
    + '<span class="cc" style="font-size:11px">'
    + items.length + ' not yet tracked'
    + (already ? ' &middot; ' + already + ' already are' : '')
    + '</span>'
    + '<span style="flex:1"></span>'
    + '<input id="srcpickq" placeholder="filter by SKU or title" value="'+_sesc(q||"")+'" '
    + 'oninput="sourcingPickerFilter(this.value)" style="font-size:12px;padding:4px 8px;min-width:200px">'
    + '<button class="db-chip" onclick="sourcingPickerClose()">Close</button></div>';

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:8px">'+_sesc(j.note)+'</div></div>';
    host.innerHTML = h; return;
  }
  // EVERYTHING IS ALREADY TRACKED is a good answer, and it has to be said. An
  // empty list reads as a filter that matched nothing or a page that failed.
  if(!items.length){
    h += '<div class="cc" style="font-size:12px;padding:10px 8px;line-height:1.5">'
      + (already
          ? '<i class="ti ti-check"></i> Every live listing that matches is '
            + 'already tracked' + (q ? ' (' + already + ' of them)' : '') + '.'
          : 'Nothing matched. Clear the filter to see the full list.')
      + '</div></div>';
    host.innerHTML = h; return;
  }

  h += '<div style="max-height:340px;overflow:auto">';
  items.forEach(function(it){
    h += '<div style="display:flex;gap:9px;align-items:center;font-size:11.5px;'
      +  'padding:6px 4px;border-top:1px solid var(--line2)">'
      // The product, at a glance. A SKU is "10.06_3Days_B0081ZHHTS" and a title
      // is forty words of keywords; neither says what the thing is, and
      // enrolling the wrong one reprices it against somebody else's supplier.
      +  (it.img
          ? '<img src="'+_sesc(thumbUrl(it.img, 38))+'" loading="lazy" decoding="async" alt="" '
            + 'style="width:38px;height:38px;object-fit:contain;background:var(--sidebar);'
            + 'border-radius:5px;flex:0 0 auto">'
          : '<span style="width:38px;height:38px;border-radius:5px;flex:0 0 auto;'
            + 'background:var(--sidebar);display:inline-block"></span>')
      +  '<code style="min-width:150px">'+_sesc(it.sku)+'</code>'
      +  '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '
      +  'title="'+_sesc(it.title)+'">'+_sesc(it.title||"(no title)")+'</span>'
      +  (/AFN|AMAZON|FBA/i.test(it.fulfillment||"")
          ? '<span class="db-chip" style="opacity:.6" title="Amazon holds this stock, so the repricer leaves it alone">FBA</span>'
          : '')
      +  '<span class="cc">'+_smoney(it.price)+'</span>'
      +  '<button class="db-chip" onclick="sourcingEnrolPicked('
      +  _sarg(it.sku) + ')">Enroll</button>'
      +  '</div>';
  });
  h += '</div></div>';
  host.innerHTML = h;
}

let _srcPickTimer = null;
function sourcingPickerFilter(v){
  clearTimeout(_srcPickTimer);
  _srcPickTimer = setTimeout(function(){ sourcingPickerLoad(v); }, 200);
}
function sourcingPickerClose(){
  const host = document.getElementById("srcpick");
  if(host){ host.style.display = "none"; host.innerHTML = ""; }
}

async function sourcingEnrolPicked(sku){
  // The list was drawn for one account; enrol there or nowhere.
  const sc = SRC_PICK_SCOPE || _srcScopeNow();
  if(!_srcStillIn(sc)){
    toast("The account or marketplace changed, so nothing was enrolled.");
    sourcingPickerClose(); return;
  }
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku}, sc)})).json();
    if(!j.ok){ toast(j.error||"Could not enroll"); return; }
    toast("Enrolled in dry run — add a supplier link next");
    await sourcingPickerLoad((document.getElementById("srcpickq")||{}).value||"");
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}

async function sourcingUnenrol(sku){
  if(!await srcConfirm({
      title: "Stop tracking " + sku + "?",
      body: "Its supplier links and price history are kept — enroll it again "
          + "later and everything is still attached. Nothing on Amazon changes.",
      confirm: "Stop tracking", risk: true})) return;
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, enrolled:false})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}

async function sourcingAddSourcePrompt(sku){
  // The account AND marketplace this was opened for, noted before the dialog;
  // the write names them and is refused if the screen moved (confirm-then-write).
  const _sc0 = _srcScopeNow();
  const url = await uiPrompt("Paste the supplier's link for "+sku+".\n\neBay links are read "
                   + "through eBay's own API. Other sites are read only if they "
                   + "publish structured product data — the app will tell you if "
                   + "it cannot read one rather than guess a price.");
  if(!url) return;
  try{
    if(!_srcStillIn(_sc0)){
      if(typeof toast === "function") toast("The account or marketplace changed while this was open, so nothing was done.");
      return;
    }
    let j = await (await fetch("/sourcing/source/add",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, url:url.trim()}, _sc0)})).json();
    // A VARIATION LISTING WHOSE LINK DOES NOT SAY WHICH ONE: the server lists
    // them; the owner picks, and the pick is sent as its own ?var= link.
    // (Only one in stock is linked by the server itself and said in the note.)
    if(j && j.choose && (j.variations || []).length){
      const chosen = await _srcPickVariation(sku, j.error, j.variations);
      if(!chosen) return;
      if(!_srcStillIn(_sc0)){ toast("The account or marketplace changed, so nothing was added."); return; }
      j = await (await fetch("/sourcing/source/add",{method:"POST",
        headers:{"Content-Type":"application/json"},
        body:_srcBody({sku:sku, url:chosen}, _sc0)})).json();
    }
    if(!j.ok){ toast(j.error||"Could not add"); return; }
    if(j.note) toast(j.note);
    toast("Supplier added — press “Re-read suppliers now” to check it");
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}

/* Pick one variation of an eBay listing -> its ?var= link, or null.
 * In the repricer's own dialog (_srcModal), one row per variation: what tells
 * it apart, its price, and whether eBay says it is in stock. */
function _srcPickVariation(sku, why, vars){
  return new Promise(function(resolve){
    let done = false;
    const fin = function(v){ if(!done){ done = true; resolve(v); } };
    const rows = vars.map(function(v, i){
      const st = v.in_stock === true ? '<span style="color:var(--ok)">in stock</span>'
               : v.in_stock === false ? '<span style="color:var(--red)">out of stock</span>'
               : '<span class="cc">stock unknown</span>';
      return '<label style="display:flex;gap:8px;align-items:center;padding:6px 0;'
        + 'border-top:1px solid var(--line2);cursor:pointer">'
        + '<input type="radio" name="srcvar" value="' + i + '"'
        + (v.in_stock === true ? '' : '') + '>'
        + '<span style="flex:1">' + _sesc(v.label || ("variation " + v.var_id)) + '</span>'
        + '<span style="font-variant-numeric:tabular-nums">'
        + (v.price !== null && v.price !== undefined ? _sesc((v.currency ? v.currency + " " : "") + Number(v.price).toFixed(2)) : "")
        + '</span><span style="font-size:11px;min-width:80px;text-align:right">' + st + '</span></label>';
    }).join("");
    _srcModal("Which variation do you buy for " + sku + "?",
      '<div class="cc" style="font-size:12px;margin-bottom:8px">' + _sesc(why || "") + '</div>' + rows,
      function(){
        const on = document.querySelector('#srcmodal input[name="srcvar"]:checked');
        if(!on){ toast("Pick one variation first."); return false; }
        fin(vars[Number(on.value)].url);
        return true;
      },
      function(){ fin(null); });
  });
}

async function sourcingRemoveSource(sid){
  if(!await srcConfirm({
      title: "Remove this supplier?",
      body: "The repricer will stop reading its price. The other suppliers on "
          + "this SKU are not affected.",
      confirm: "Remove it", risk: true})) return;
  try{
    const j = await (await fetch("/sourcing/source/remove",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({source_id:sid})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}
