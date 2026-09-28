// static/js/sourcing_bulk.js -- selecting rows and the bulk actions. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* ---- selecting several SKUs ------------------------------------------------
 *
 *     "also allow to select multiple skus at once and unroll them from tracking"
 *
 * The selection is kept by SKU rather than by row index, so it survives a
 * re-render after a check or an arm -- indices shift when the list re-sorts and
 * would silently move the tick onto a different product.
 */
let SRC_SEL = new Set();

function sourcingSelect(sku, on){
  if(on) SRC_SEL.add(String(sku)); else SRC_SEL.delete(String(sku));
  _srcSelBar();
}

/* Tick or untick everything CURRENTLY SHOWN.
 *
 * Shown, not tracked. Under a filter the header box has to mean the rows under
 * it -- ticking "all" while looking at four out-of-stock SKUs and quietly
 * selecting the other sixty-three is how a bulk action hits the wrong things.
 */
function sourcingSelectAll(on){
  const shown = _srcVisible().map(function(r){ return String(r.sku); });
  if(on) shown.forEach(function(s){ SRC_SEL.add(s); });
  else shown.forEach(function(s){ SRC_SEL.delete(s); });
  document.querySelectorAll(".srcsel").forEach(function(b){ b.checked = !!on; });
  const all = document.getElementById("rp_all");
  if(all) all.checked = !!on;
  _srcSelBar();
}

/* THE BULK BAR.
 *
 *     "When checkboxes are ticked, a sticky bar appears above the table:
 *      X selected | Set min price | Set ROI | Set margin | Arm all |
 *      Disarm all | Stop tracking"
 *
 * STICKY, because the rows it acts on are the reason to scroll. Selecting
 * thirty SKUs down a sixty-seven row table used to leave the bar somewhere
 * above the fold, so the last thing you did was scroll back up to find the
 * button for the thing you had just finished choosing.
 *
 * Every action here is the SAME call the single-row version makes -- see
 * _srcBulkRule, which loops the one-SKU save. Nothing has a bulk endpoint of
 * its own, so a rule set for forty SKUs cannot be validated differently from
 * one set for one (CLAUDE.md Rule 12).
 */
function _srcSelBar(){
  const el = document.getElementById("srcselbar");
  if(!el) return;
  // Only SKUs still on screen count. A filter change can leave a tick on a row
  // nobody can see, and acting on forty when four are visible is the kind of
  // surprise this bar exists to prevent.
  const shown = new Set(_srcVisible().map(function(r){ return String(r.sku); }));
  const picked = [...SRC_SEL].filter(function(s){ return shown.has(s); });
  if(!picked.length){ el.innerHTML = ""; return; }
  const rows = SRC_ROWS.filter(function(r){
    return picked.indexOf(String(r.sku)) >= 0; });
  const armed = rows.filter(function(r){ return r.mode === "live"; }).length;
  // ARMING NEEDS A FLOOR. Said before the button is pressed rather than as
  // forty identical refusals afterwards.
  const noFloor = rows.filter(function(r){
    return (r.rule || {}).min_price == null; }).length;

  el.innerHTML =
      '<div class="rp-bulk">'
    + '<b>' + picked.length + ' selected</b>'
    + (armed ? '<span class="rp-g">' + armed + ' armed</span>' : '')
    + (noFloor ? '<span class="rp-y" title="A SKU cannot be armed until it has '
                 + 'a price it will never sell below.">' + noFloor
                 + ' with no floor</span>' : '')
    + '<span style="flex:1"></span>'
    + '<button class="db-chip" onclick="sourcingSelectAll(false)">Clear</button>'
    // THE FLOOR THAT ARMING REQUIRES, settable for everything at once. Without
    // this it is one row at a time, which is why nothing was armed.
    + '<button class="db-chip" onclick="sourcingMinPriceBulk(this)" title="'
    + 'Give each selected listing a price it will never sell below. A SKU '
    + 'cannot be armed without one.">'
    + '<i class="ti ti-arrow-down-circle"></i> Set min price</button>'
    + '<button class="db-chip" onclick="sourcingBulkTarget(\'roi\',this)" title="'
    + 'The return you want on the cash you put in, for every selected SKU. The '
    + 'price becomes the least that meets it.">Set ROI</button>'
    + '<button class="db-chip" onclick="sourcingBulkTarget(\'margin\',this)" '
    + 'title="The share of the selling price you want to keep, for every '
    + 'selected SKU.">Set margin</button>'
    + '<button class="db-chip" onclick="sourcingBulkDirection()" title="'
    + 'Whether these SKUs may have their price lowered as well as raised.">'
    + 'Set direction</button>'
    // THE ANSWER TO "it should not reduce my selling price", made reachable.
    // The held price did this all along; typing it into 67 SKUs by hand did not.
    + '<button class="db-chip" onclick="sourcingHoldAtCurrent()" title="'
    + "Write today's Amazon price in as the floor for each selected listing. "
    // Each claim kept whole rather than split across a concatenation. These
    // three phrases are what the button PROMISES, and a promise broken over
    // two string literals cannot be found -- by a reader grepping for it, or
    // by the test that guards the wording.
    + 'The repricer then never prices below it — a cheaper supplier means '
    + 'more margin, not a lower price — '
    + 'but a dearer one can still push the price UP, '
    + 'so it can never hold you at a loss.">'
    + '<i class="ti ti-lock-dollar"></i> Hold at today’s price</button>'
    + '<button class="db-chip go" onclick="sourcingBulkArm(true)" title="'
    + 'Let these SKUs change their own price on Amazon, without anyone '
    + 'watching. Each one still needs a floor first.">'
    + '<i class="ti ti-bolt"></i> Arm all</button>'
    + '<button class="db-chip" onclick="sourcingBulkArm(false)" title="'
    + 'Back to watching only. Costs are still tracked and decisions still '
    + 'recorded; nothing reaches Amazon.">Disarm all</button>'
    + '<button class="db-chip risk" onclick="sourcingUnenrolSelected()">'
    + '<i class="ti ti-eye-off"></i> Stop tracking</button>'
    + '</div>';
}

/* The SKUs the bulk bar is about: ticked AND on screen. */
function _srcPicked(){
  const shown = new Set(_srcVisible().map(function(r){ return String(r.sku); }));
  return [...SRC_SEL].filter(function(s){ return shown.has(s); });
}

/* Save one rule across every selected SKU, one call each.
 *
 * One at a time on purpose. Each save goes through /sourcing/rules, which is
 * the route that validates a percentage and refuses an impossible margin -- a
 * bulk endpoint would need that logic again and would eventually disagree with
 * it. Sixty-seven small posts is a second; a second validator is a bug.
 */
async function _srcBulkRule(rule, verb){
  const skus = _srcPicked();
  if(!skus.length) return;
  const scope = _srcScopeNow();
  let ok = 0, stopped = 0;
  const bad = [];
  for(const sku of skus){
    if(!_srcStillIn(scope)){ stopped = skus.length - ok - bad.length; break; }
    const err = await sourcingSaveRuleQuiet(sku, rule, scope);
    if(err) bad.push(sku + ": " + err); else ok++;
  }
  toast(verb + " on " + ok + " SKU" + (ok === 1 ? "" : "s")
        + (bad.length ? " · " + bad.length + " refused" : ""));
  if(bad.length || stopped) await uiAlert(bad.slice(0, 12).join("\n") + _srcStopNote(stopped),
      {title: bad.length ? (bad.length + " could not be saved") : ("Stopped after " + ok)});
  await sourcingLoad(true);
}

/* sourcingSaveRule without the toast and without a refresh per SKU. */
async function sourcingSaveRuleQuiet(sku, rule, scope){
  try{
    const j = await (await fetch("/sourcing/rules", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: _srcBody({sku: sku, rule: rule}, scope)})).json();
    if(!j.ok) return j.error || "refused";
    const row = (SRC_ROWS || []).filter(function(r){ return r.sku === sku; })[0];
    if(row) row.rule = Object.assign({}, row.rule || {}, rule);
    return "";
  }catch(e){ return String((e && e.message) || e); }
}

/* Which way the selected SKUs may move. A modal, not an inline box, because
 * the three choices need a sentence each -- their names do not say which one
 * can lose you money. */
async function sourcingBulkDirection(){
  const n = _srcPicked().length;
  if(!n) return;
  const row = function(v, label, why){
    return '<label class="rp-mi" style="cursor:pointer;align-items:flex-start">'
      + '<input type="radio" name="src_bdir" value="' + v + '"'
      + (v === 'up_only' ? ' checked' : '') + ' style="margin-top:3px">'
      + '<span><b>' + label + '</b><br><span class="cc" '
      + 'style="font-size:11px;line-height:1.5">' + why + '</span></span></label>';
  };
  _srcModal("Direction for " + n + " SKU" + (n === 1 ? "" : "s"),
    '<div style="font-size:12.5px">'
    + row('up_only', 'Up only',
          'Never lowered. A cheaper supplier becomes margin instead of a '
          + 'discount. This is the default.')
    + row('up_and_down', 'Up and down',
          'Follows the supplier both ways -- cheaper cost, cheaper price.')
    + row('match_floor', 'Match the floor exactly',
          'Always on the calculated floor, ignoring any held price.')
    + '</div>',
    async function(){
      const sel = document.querySelector('input[name="src_bdir"]:checked');
      if(!sel) return false;
      await _srcBulkRule({direction: sel.value},
        {up_only: 'Up only', up_and_down: 'Up and down',
         match_floor: 'Matching the floor'}[sel.value]);
      return true;
    });
}

async function sourcingBulkTarget(kind, btn){
  const n = _srcPicked().length;
  if(!n) return;
  const key = (kind === "roi") ? "target_roi_pct" : "target_margin_pct";
  await uiInline(btn, {
    title: (kind === "roi" ? "ROI" : "Margin") + " target on " + n + " SKU"
           + (n === 1 ? "" : "s"),
    type: "number", min: 0, step: "0.5", suffix: "%",
    placeholder: kind === "roi" ? "e.g. 25" : "e.g. 20",
    hint: kind === "roi"
      ? "What you keep as a share of the cash you put in. The price becomes "
        + "the least that meets it."
      : "What you keep as a share of what the buyer pays. Amazon's fee comes "
        + "out of the same price, so a margin much over 60% cannot be met.",
    clearable: true,
    clearLabel: "Turn this target off",
    onSave: async function(v){
      const t = String(v).trim();
      if(t !== "" && !(parseFloat(t) >= 0))
        return "That needs to be a number, e.g. 20";
      const patch = {};
      patch[key] = (t === "" ? null : parseFloat(t));
      await _srcBulkRule(patch, t === "" ? "Target cleared"
                                         : t + "% " + kind + " set");
      return "";
    }
  });
}

/* Arm or disarm everything selected.
 *
 * ARMING IS THE MOST CONSEQUENTIAL THING ON THIS SCREEN -- an armed SKU can
 * change a real price with nobody watching -- so it asks first, and says how
 * many and what that means. Disarming does not ask: stopping is always safe.
 */
async function sourcingBulkArm(on){
  const skus = _srcPicked();
  if(!skus.length) return;
  // Fixed BEFORE the question is asked: the confirm names these SKUs in this
  // account, and that is what the answer agrees to.
  const scope = _srcScopeNow();
  if(on){
    const ok = await uiConfirm(
      "Arm " + skus.length + " SKU" + (skus.length === 1 ? "" : "s") + "?\n\n"
      + "Armed SKUs can have their price, stock and handling time changed on "
      + "Amazon without anyone watching — at most one change each every "
      + "four hours, and never below the floor you set.\n\n"
      + (SRC_MASTER ? "" : "Auto-pricing is currently OFF, so nothing will be "
                           + "pushed until you switch it on."),
      {title: "Arm " + skus.length + " SKU" + (skus.length === 1 ? "" : "s"),
       ok: "Arm them", danger: true});
    if(!ok) return;
  }else{
    // Disarming asks as well -- see sourcingArm.
    const ok = await uiConfirm(
      "Disarm " + skus.length + " SKU" + (skus.length === 1 ? "" : "s") + "?\n\n"
      + "Automatic pricing stops for them: price, stock and handling time will "
      + "no longer follow their sources. Nothing already sent to Amazon is undone.",
      {title: "Disarm " + skus.length + " SKU" + (skus.length === 1 ? "" : "s"),
       ok: "Disarm", danger: true});
    if(!ok) return;
  }
  let done = 0, stopped = 0;
  const bad = [];
  for(const sku of skus){
    if(!_srcStillIn(scope)){ stopped = skus.length - done - bad.length; break; }
    try{
      const j = await (await fetch("/sourcing/arm", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({sku: sku, live: !!on}, scope)})).json();
      if(j.ok) done++; else bad.push(sku + ": " + (j.error || "refused"));
    }catch(e){ bad.push(sku + ": " + String((e && e.message) || e)); }
  }
  toast((on ? "Armed " : "Disarmed ") + done
        + (bad.length ? " · " + bad.length + " refused" : ""));
  // WHY EACH REFUSAL HAPPENED, not just how many. Almost always a missing
  // floor, and that is fixable in one more click from the same bar.
  if(bad.length || stopped) await uiAlert(bad.slice(0, 12).join("\n") + _srcStopNote(stopped),
      {title: bad.length ? (bad.length + " could not be armed") : ("Stopped after " + done)});
  await sourcingLoad(true);
}

async function sourcingUnenrolSelected(){
  const shown = new Set(SRC_ROWS.map(function(r){ return String(r.sku); }));
  const skus = [...SRC_SEL].filter(function(s){ return shown.has(s); });
  if(!skus.length) return;
  const armed = SRC_ROWS.filter(function(r){
    return skus.indexOf(String(r.sku)) >= 0 && r.mode === "live"; }).length;
  // NOTHING IS DELETED, and that is the point worth making before the click
  // rather than after it -- the links and the price history are the expensive
  // part, and a supplier price on a day nobody was watching cannot be recovered.
  const ok = await srcConfirm({
    title: "Stop tracking " + skus.length + " SKU" + (skus.length === 1 ? "" : "s") + "?",
    body: "Their supplier links and price history are KEPT — enroll one again "
        + "later and everything is still attached. Nothing is deleted and "
        + "nothing on Amazon changes."
        + (armed ? "\n\n" + armed + " of them are armed for auto-pricing. "
                 + "Stopping tracking takes them out of it." : ""),
    confirm: "Stop tracking",
    risk: true,
  });
  if(!ok) return;
  try{
    const j = await (await fetch("/sourcing/unenrol_bulk",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({skus: skus})})).json();
    if(!j || !j.ok){ toast((j&&j.error)||"Could not stop tracking those"); return; }
    SRC_SEL = new Set();
    toast(j.note || ("Stopped tracking " + (j.unenrolled || 0)));
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}
