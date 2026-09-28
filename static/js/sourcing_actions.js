// static/js/sourcing_actions.js -- the master switch, arming, rules, minimum/hold prices, fees and targets. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

async function sourcingMaster(on){
  if(on && !await srcConfirm({
      title: "Turn auto-pricing on?",
      body: "Armed SKUs will then have their price, stock and handling time "
          + "changed on Amazon automatically, without anyone watching. SKUs "
          + "still in dry run are unaffected.",
      confirm: "Turn it on", risk: true})) return;
  try{
    const j = await (await fetch("/sourcing/master",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({enabled:!!on})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast(j.enabled ? "Master switch ON" : "Master switch off — nothing will be pushed");
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}

async function sourcingArm(sku, live){
  // Fixed BEFORE either question: the answer agrees to this SKU in this account.
  const scope = _srcScopeNow();
  if(live && !await srcConfirm({
      title: "Arm " + sku + "?",
      body: "From then on the app may change this listing's price, stock and "
          + "handling time on Amazon by itself, without anyone watching.",
      confirm: "Arm it", risk: true})) return;
  // DISARMING ASKS TOO (design package 01/07: "Armed -- disarm" is a dangerous
  // toggle). It is the safer direction for prices, but it STOPS automatic
  // pricing: from then on nothing keeps the price, stock or handling time in
  // step with the source, and an out-of-stock source can oversell.
  if(!live && !await srcConfirm({
      title: "Disarm repricing for " + sku + "?",
      body: "Automatic pricing stops for this SKU: its price, stock and handling "
          + "time will no longer follow the source. Nothing already sent to "
          + "Amazon is undone, and you can arm it again at any time.",
      confirm: "Disarm", risk: true})) return;
  if(!_srcStillIn(scope)){ toast("The account changed while that was open, so nothing was sent."); return; }
  try{
    const j = await (await fetch("/sourcing/arm",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, live:!!live}, scope)})).json();
    if(!j.ok){ toast(j.error||"Could not arm"); return; }
    toast(j.note || (j.mode==="live" ? "Armed" : "Back to dry run"));
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}

/* SAVE ONE RULE WITHOUT LOSING THE SCREEN.
 *
 *     "Saving a minimum price clears the entire screen and shows 'Minimum
 *      price saved' on a blank page while it reloads. This is terrible UX."
 *
 * It was: every save called sourcingLoad(), which blanks #srcbody to a spinner,
 * re-fetches sixty-seven decisions, and redraws from nothing. Every open panel
 * shut, the scroll jumped to the top, and for a second there was a message on
 * an empty page.
 *
 * This is the one place a rule is saved from now (Rule 12). It posts, updates
 * the row's rule in the model we already hold, and refreshes quietly -- see
 * sourcingLoad(quiet), which keeps what is on screen until the new HTML is
 * ready and then puts the open panels and the scroll position back.
 *
 * Returns "" on success or the error to show, which is the contract uiInline
 * wants: a string keeps the editor open with the message under it.
 */
async function sourcingSaveRule(sku, rule, okMsg){
  try{
    const j = await (await fetch("/sourcing/rules", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: _srcBody({sku: sku, rule: rule})})).json();
    if(!j.ok) return j.error || "Could not save that.";
    // The model we are already holding, so the row is right even before the
    // quiet refresh lands.
    const row = (SRC_ROWS || []).filter(function(r){ return r.sku === sku; })[0];
    if(row){ row.rule = Object.assign({}, row.rule || {}, rule); }
    if(SRC_ROW_RULES[sku]) Object.assign(SRC_ROW_RULES[sku], rule);
    if(okMsg) toast(okMsg);
    sourcingLoad(true);
    return "";
  }catch(e){ return String((e && e.message) || e); }
}

/* THE FLOOR, EDITED WHERE THE BUTTON IS.
 *
 * An amount, so the box is a number field with a currency symbol beside it --
 * neither of which prompt() could draw. Cancelling is Escape or a click
 * anywhere else; turning it off is its own button, because an empty box saved
 * is ambiguous and this is the one setting that gates arming.
 */
async function sourcingMinPrice(sku, btn){
  const cur = (SRC_ROW_RULES[sku] || {}).min_price;
  await uiInline(btn || (window.event && window.event.target), {
    title: "Never sell " + sku + " below",
    prefix: _srcSym(),
    type: "number",
    min: 0,
    step: "0.01",
    value: (cur == null ? "" : cur),
    placeholder: "e.g. 14.99",
    hint: "The one guard that still works if a supplier's page is misread. A "
        + "SKU cannot be armed without it.",
    clearable: cur != null,
    clearLabel: "Remove the floor",
    onSave: function(v){
      const t = String(v).trim();
      if(t !== "" && !(parseFloat(t) > 0))
        return "That needs to be an amount above zero, e.g. 14.99";
      return sourcingSaveRule(sku, {min_price: t === "" ? null : parseFloat(t)},
                              t === "" ? "Floor removed"
                                       : "Never below " + _smoney(parseFloat(t)));
    }
  });
}

/* Which currency this account sells in. One place, because three of these
 * editors want the symbol and a wrong one is a wrong number on screen. */
/* Which Amazon domain this account's listings live on.
 *
 * A UK ASIN opened on amazon.com is either a different product or a 404, and
 * the link was hardcoded to .co.uk for every account -- including sheelady_us
 * and miles_lubricants, which sell in dollars. One place, so the row link and
 * anything added later cannot disagree (CLAUDE.md Rule 12).
 */
function _srcAmzHost(){
  const m = String((typeof SRC_MKT === "string" && SRC_MKT)
                   || window.ACTIVE_MARKETPLACE || "UK").toUpperCase();
  return {UK: "co.uk", US: "com", DE: "de", FR: "fr", IT: "it", ES: "es",
          NL: "nl", SE: "se", PL: "pl", BE: "com.be", IE: "ie", CA: "ca",
          MX: "com.mx", BR: "com.br", AU: "com.au", JP: "co.jp",
          IN: "in", AE: "ae", SA: "sa", TR: "com.tr",
          SG: "sg"}[m] || "co.uk";
}

function _srcSym(){
  const m = (typeof SRC_MKT === "string" && SRC_MKT)
          || (window.ACTIVE_MARKETPLACE || "");
  if(typeof currencySymbol === "function"){
    try{ return currencySymbol(m) || "£"; }catch(e){ /* fall through */ }
  }
  return String(m).toUpperCase() === "US" ? "$" : "£";
}

/* HOLD THE PRICE AT WHAT THE MARKET PAYS.
 *
 * "i want the repricer to not to change my price if the margin or roi target set is
 *  less than my selling price ... but if source price suddenly goes upto 35 pounds
 *  and i am selling at 40 pounds, so then it should increase my selling price but
 *  when the source again came back to 12 or 20 pounds my selling price should be
 *  set to 40 again"
 *
 * The prompt spells the whole behaviour out, because the difference between this
 * and "never sell below" is exactly the thing that would get them confused, and
 * confusing the two is expensive in both directions.
 */
async function sourcingHoldPrice(sku, btn){
  const cur = (SRC_ROW_RULES[sku] || {}).hold_price;
  await uiInline(btn || (window.event && window.event.target), {
    title: "Hold " + sku + " at",
    prefix: _srcSym(),
    type: "number",
    min: 0,
    step: "0.01",
    value: (cur == null ? "" : cur),
    placeholder: "e.g. 40.00",
    // THE DIFFERENCE FROM THE FLOOR, in one line rather than four paragraphs.
    // The old prompt spelled the whole behaviour out because a native dialog
    // has nowhere else to put it; here the rest is on the button's own tooltip
    // and in the notice the panel draws when a hold is actually in force.
    hint: "Never priced below this even when your target would take less. It "
        + "is a floor, not a fixed price: if the supplier gets dearer the "
        + "price still goes up, and comes back to this when they get cheaper.",
    clearable: cur != null,
    clearLabel: "Stop holding the price",
    onSave: function(v){
      const t = String(v).trim();
      if(t !== "" && !(parseFloat(t) > 0))
        return "That needs to be an amount above zero, e.g. 40.00";
      return sourcingSaveRule(sku, {hold_price: t === "" ? null : t},
                              t === "" ? "No longer holding the price"
                                       : "Held at " + _smoney(parseFloat(t)));
    }
  });
}

/* ASK AMAZON WHAT IT CHARGES ON EACH PRODUCT.
 *
 * Fills the fee cache. Pricing reads that cache and never calls Amazon itself,
 * because pricing runs for every enrolled SKU on every page load.
 *
 * IT SAYS WHAT IT COULD NOT ANSWER. On an account whose SP-API roles are not
 * granted Amazon refuses every one of these, and a button that reported "done"
 * would leave the owner believing his prices were built on Amazon's figures
 * when they are still built on an average.
 */
async function sourcingGetFees(btn){
  const was = btn ? btn.innerHTML : "";
  if(btn){ btn.disabled = true; btn.textContent = "Asking Amazon…"; }
  try{
    const j = await (await fetch(_srcUrl("/sourcing/fees"), {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: _srcBody({})})).json();
    if(!j || !j.ok){ toast((j && j.error) || "Could not ask Amazon"); return; }
    toast(j.note || (j.quoted + " quoted"));
    // The ones Amazon would not answer for are the point of the second dialog:
    // those SKUs keep pricing from your measured rate, and that is worth
    // knowing per SKU rather than as a count.
    const bad = (j.not_quoted || []).concat(j.left_alone || []);
    if(bad.length){
      await srcConfirm({
        title: bad.length + " could not be quoted",
        body: bad.slice(0, 10).map(function(r){
                return "  " + r.sku + "\n      " + (r.detail || r.why || "");
              }).join("\n")
            + (bad.length > 10 ? "\n…and " + (bad.length - 10) + " more" : "")
            + "\n\nThese keep pricing from your own measured rate instead of "
            + "Amazon's quote. Their rows say so.",
        confirm: "OK",
      });
    }
    sourcingLoad();
  }catch(e){ toast(String(e)); }
  finally{ if(btn){ btn.disabled = false; btn.innerHTML = was; } }
}

/* A MINIMUM PRICE ON MANY SKUS AT ONCE.
 *
 *     "i am not able to arm a sku"
 *
 * A SKU cannot be armed without one, and there was only ever one way to set it:
 * open the row, find the box, type a number. On an account with nine SKUs below
 * target and sixty-seven tracked, that is the same wall the held price hit --
 * the guard exists, and nobody can reach it often enough to use it.
 *
 * A SHARE OF TODAY'S SELLING PRICE, not of the cost. That is deliberate and it
 * is what this particular number is FOR: the minimum price is the guard that
 * still works when a supplier's page is misread, so deriving it from the
 * supplier's figure would tie the safety net to the thing it protects against.
 * Today's Amazon price is independent of that.
 *
 * It also works where a cost-based floor could not: 22 of the 67 tracked SKUs
 * have no readable supplier cost at all, and those are exactly the ones most in
 * need of a floor.
 */
async function sourcingMinPriceBulk(){
  const shown = new Set(SRC_ROWS.map(function(r){ return String(r.sku); }));
  const picked = [...SRC_SEL].filter(function(s){ return shown.has(s); });
  if(!picked.length){ toast("Select some listings first"); return; }

  const rows = SRC_ROWS.filter(function(r){
    return picked.indexOf(String(r.sku)) >= 0
        && (r.current || {}).price != null && Number(r.current.price) > 0;
  });
  const noPrice = picked.length - rows.length;
  if(!rows.length){
    toast("None of the " + picked.length + " selected listing(s) has a price "
        + "read from Amazon, so there is no figure to work a floor out from.");
    return;
  }

  _srcModal(
    "Never sell below — for " + rows.length + " listing(s)",
    '<p class="cc" style="font-size:12px;margin:0 0 12px">Set each one\'s floor '
    + 'as a share of what it sells for on Amazon today. A SKU cannot be armed '
    + 'until it has one.</p>'
    + _srcTargetBox('minpct', 'Percent of today\'s price', 80,
        'Worked out from your Amazon price, NOT from the supplier — this is the '
      + 'guard that still works when a supplier\'s page is misread, so it must '
      + 'not depend on one.',
        'A listing at 19.97 with 80% gets a floor of 15.98')
    + (noPrice
        ? '<p class="cc" style="font-size:11.5px;margin:10px 0 0">' + noPrice
          + ' selected listing(s) have no price read from Amazon and will be '
          + 'left alone.</p>'
        : ''),
    async function(){
      const el = document.getElementById('minpct');
      const pct = Number(String((el && el.value) || "").replace("%", "").trim());
      if(!isFinite(pct) || pct <= 0 || pct > 100){
        toast("Enter a percentage between 1 and 100");
        return false;                       // keep the box open
      }
      const plan = rows.map(function(r){
        return {sku: r.sku, now: Number(r.current.price),
                floor: Math.round(Number(r.current.price) * pct) / 100,
                was: (r.rule || {}).min_price};
      });
      const already = plan.filter(function(p){ return p.was != null; });
      const sample = plan.slice(0, 12).map(function(p){
        return "  " + p.sku + "\n      never below " + _smoney(p.floor)
             + "   (sells at " + _smoney(p.now) + ")"
             + (p.was != null ? "   was " + _smoney(p.was) : "");
      }).join("\n");

    // The account these were chosen in, fixed BEFORE the question (master audit S1).
      const scope = _srcScopeNow();
      const go = await srcConfirm({
        title: "Set a floor on " + plan.length + " listing(s)?",
        body: sample
          + (plan.length > 12 ? "\n  …and " + (plan.length - 12) + " more" : "")
          + "\n\nThe repricer will never price them below these figures, "
          + "whatever a supplier's page says. Each one can then be armed."
          + (already.length
              ? "\n\n" + already.length + " already have a minimum price, and it "
                + "will be REPLACED."
              : "")
          + "\n\nNothing on Amazon changes now.",
        confirm: "Set the floors",
      });
      if(!go) return false;

      let ok = 0, stopped = 0;
      const failed = [];
      toast("Setting " + plan.length + " floor(s)…");
      for(const p of plan){
        if(!_srcStillIn(scope)){ stopped = plan.length - ok - failed.length; break; }
        try{
          const j = await (await fetch("/sourcing/rules", {method: "POST",
            headers: {"Content-Type": "application/json"},
            body: _srcBody({sku: p.sku,
                            rule: {min_price: String(p.floor)}}, scope)})).json();
          if(j && j.ok) ok++;
          else failed.push(p.sku + ": " + ((j && j.error) || "refused"));
        }catch(e){ failed.push(p.sku + ": " + String(e)); }
      }
      let msg = "Minimum price set on " + ok + " listing(s).";
      if(noPrice) msg += " " + noPrice + " left alone (no price read from Amazon).";
      toast(msg);
      if(failed.length || stopped){
        await srcConfirm({
          title: failed.length ? (failed.length + " could not be set")
                               : ("Stopped after " + ok),
          body: failed.slice(0, 10).join("\n")
              + (failed.length > 10 ? "\n…and " + (failed.length - 10) + " more" : "")
              + (stopped ? _srcStopNote(stopped)
                         : "\n\nThe rest were set.") + " Nothing on Amazon has changed.",
          confirm: "OK",
        });
      }
      sourcingLoad(true);
      return true;
    });
}

/* HOLD WHAT I SELL AT TODAY, ON MANY SKUS AT ONCE.
 *
 *     "why do the repricer wants to reduce my selling price to achieve the
 *      target, it should not happen"
 *     "If your supplier drops from 15.34 to 9 i want to stay where it is and
 *      take the extra margin"
 *
 * The behaviour he is asking for already existed and already worked -- MEASURED
 * on his own row, with a 20% target and a hold at 21.99:
 *
 *     supplier 15.34 -> 9.00   target alone would allow 12.71, it holds 21.99
 *     supplier 15.34 -> 24.00  target needs 33.89, it RISES to 33.89
 *     supplier 24.00 -> 15.34  it comes back to 21.99, not to 21.66
 *
 * What did not exist was any way to set it without typing a number into each of
 * 67 SKUs one at a time. A feature nobody can reach at their own scale is not a
 * feature, which is why the repricer went on cutting prices while the answer sat
 * there unused.
 *
 * TODAY'S AMAZON PRICE IS THE NUMBER. It needs to be a written-down number
 * rather than a "don't go down" flag, and that reasoning is not mine -- it is in
 * test_hold_price.py: a flag has no memory, so once a cost spike carries the
 * price to 46 there is nothing to come back TO, and every spike becomes
 * permanent. The current price is the one number that means "where I am now".
 *
 * SAFE ON A LISTING THAT IS UNDER WATER, which I wrongly warned it would not be.
 * A hold is a FLOOR, so it never blocks a rise: measured at 24.99 selling
 * against a 24.00 cost, the price still goes UP to 33.89. Holding cannot freeze
 * a loss in place.
 */
async function sourcingHoldAtCurrent(){
  const shown = new Set(SRC_ROWS.map(function(r){ return String(r.sku); }));
  const picked = [...SRC_SEL].filter(function(s){ return shown.has(s); });
  if(!picked.length){ toast("Select some listings first"); return; }

  // Only rows Amazon gave a price for. A hold is a price, and there is no
  // honest number to write for a listing whose price could not be read --
  // guessing one would be inventing the very figure the hold exists to fix.
  const rows = SRC_ROWS.filter(function(r){
    return picked.indexOf(String(r.sku)) >= 0
        && (r.current || {}).price != null && Number(r.current.price) > 0;
  });
  const noPrice = picked.length - rows.length;
  if(!rows.length){
    toast("None of the " + picked.length + " selected listing(s) has a price "
        + "read from Amazon, so there is nothing to hold them at.");
    return;
  }

  // What it will actually do, per SKU, before it does it.
  const already = rows.filter(function(r){ return (r.rule||{}).hold_price != null; });
  const sample = rows.slice(0, 12).map(function(r){
    const was = (r.rule||{}).hold_price;
    return "  " + r.sku + "\n      hold at " + _smoney(r.current.price)
         + (was != null ? "   (was " + _smoney(was) + ")" : "");
  }).join("\n");

  let ask = sample
    + (rows.length > 12 ? "\n  …and " + (rows.length - 12) + " more" : "")
    + "\n\nThe repricer will never price them BELOW these figures. If a supplier "
    + "gets cheaper the price stays where it is and you keep the extra margin. "
    + "If a supplier gets dearer and the price stops covering your target, it "
    + "still goes UP — a hold is a floor, so it can never hold you at a loss.";
  if(already.length){
    ask += "\n\n" + already.length + " of them already have a held price, and it "
         + "will be REPLACED with today's.";
  }
  if(noPrice){
    ask += "\n\n" + noPrice + " selected listing(s) have no price read from "
         + "Amazon and will be left alone.";
  }
  ask += "\n\nNothing on Amazon changes now — this only sets the floor the "
       + "repricer works to.";
  // srcConfirm, not the browser's confirm(): this page deliberately has none.
  // The account these were chosen in, fixed BEFORE the question (master audit S1).
  const scope = _srcScopeNow();
  const go = await srcConfirm({
    title: "Hold " + rows.length + " listing(s) at today's price?",
    body: ask,
    confirm: "Hold at today's price",
  });
  if(!go) return;

  // THROUGH THE ROUTE THAT ALREADY VALIDATES A HELD PRICE, one SKU at a time,
  // rather than a second endpoint with a second copy of that validation
  // (CLAUDE.md Rule 12).
  let ok = 0;
  const failed = [];
  let stopped = 0;
  toast("Holding " + rows.length + " listing(s)…");
  for(const r of rows){
    if(!_srcStillIn(scope)){ stopped = rows.length - ok - failed.length; break; }
    try{
      const j = await (await fetch("/sourcing/rules", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({sku: r.sku,
                        rule: {hold_price: String(r.current.price)}}, scope)})).json();
      if(j && j.ok) ok++; else failed.push(r.sku + ": " + ((j && j.error) || "refused"));
    }catch(e){ failed.push(r.sku + ": " + String(e)); }
  }

  // WHAT HAPPENED, PER SKU WHEN IT WENT WRONG. A count on its own turns a
  // handful of quietly-refused SKUs into "the hold does not work" a fortnight
  // later -- the same reason the supplier upload reports row by row.
  let msg = "Held " + ok + " listing(s) at today's price.";
  if(noPrice) msg += " " + noPrice + " left alone (no price read from Amazon).";
  toast(msg);
  if(failed.length || stopped){
    await srcConfirm({
      title: failed.length ? (failed.length + " could not be held")
                           : ("Stopped after " + ok),
      body: failed.slice(0, 10).join("\n")
          + (failed.length > 10 ? "\n…and " + (failed.length - 10) + " more" : "")
          + (stopped ? _srcStopNote(stopped)
                     : "\n\nThe rest were held.") + " Nothing on Amazon has changed.",
      confirm: "OK",
    });
  }
  sourcingLoad(true);
}

// A PERCENTAGE PROFIT FLOOR, on top of the flat one.
//
// "i want an option in which i can enroll an option to maintain atleast 20
//  percent margin or roi, a user should be able to set. and if some items are
//  less than that flag it"
//
// Margin and ROI are asked for in the same breath and are not the same number:
// on an 11.95 unit a 20% target is 26.08 as margin and 22.76 as ROI. So the
// choice is made explicitly rather than picked for you, and the difference is
// spelled out where the choice is made.
// TWO BOXES, because they are two settings and not a choice between them.
//
// "give me 2 different boxes for setting the roi or margin target on repricer"
//
// It was one prompt asking which KIND you wanted and then the number, so
// choosing margin threw away whatever ROI you had. "At least 20% margin AND at
// least 30% back on the cash" is an ordinary thing to want, and on an £11.95
// unit those ask for £26.08 and £20.73 -- neither implies the other. Both apply
// now, and the price takes the higher of the two floors.
function sourcingTarget(sku){
  // The boxes open showing what is ALREADY set -- for this SKU if it has its
  // own, otherwise the account default. Opening them blank would make "Save"
  // read as "clear both", and opening a SKU's dialog pre-filled with the
  // account's numbers would overwrite its override with someone else's.
  const acct = SRC_RULE || {};
  const cur = (sku && SRC_ROW_RULES[sku]) ? SRC_ROW_RULES[sku] : acct;
  const m = cur.target_margin_pct, o = cur.target_roi_pct;
  const scope = sku ? ('<code>' + _sesc(sku) + '</code>')
                    : 'every enrolled SKU';
  _srcModal(
    'Least profit you will accept',
    '<p class="cc" style="font-size:12px;margin:0 0 12px">Applies to ' + scope
    + '. Fill in either box, or both — the price is set to whichever asks for '
    + 'more. Leave a box empty to switch that target off.</p>'
    + '<div style="display:flex;gap:14px;flex-wrap:wrap">'
    + _srcTargetBox('tgt_margin', 'Margin target', m,
        'Profit as a share of what the CUSTOMER pays. Amazon’s cut comes '
      + 'out of the same price, so this cannot go much above 84%.',
        'On an £11.95 unit, 20% margin wants £26.08')
    + _srcTargetBox('tgt_roi', 'ROI target', o,
        'Profit as a share of what YOU paid for the unit. Measured against the '
      + 'cost, so Amazon’s cut does not cap it.',
        'On an £11.95 unit, 20% ROI wants £20.73')
    + '</div>',
    async function(){
      const gv = function(id){
        const el = document.getElementById(id);
        const v = el ? String(el.value).replace("%", "").trim() : "";
        return v === "" ? null : v;
      };
      const rule = {target_margin_pct: gv('tgt_margin'),
                    target_roi_pct: gv('tgt_roi')};
      try{
        const j = await (await fetch("/sourcing/rules",{method:"POST",
          headers:{"Content-Type":"application/json"},
          body:_srcBody({sku:sku||"", rule:rule})})).json();
        // The server refuses an unreachable or mistyped target and says why.
        // Shown as-is: a target that silently did nothing would leave you
        // believing a floor was in force while the app priced to the flat £1.
        if(!j.ok){ toast(j.error||"failed"); return false; }
        const on = [];
        if(rule.target_margin_pct) on.push(rule.target_margin_pct + "% margin");
        if(rule.target_roi_pct) on.push(rule.target_roi_pct + "% ROI");
        toast(on.length ? ("Target: " + on.join(" and ")) : "Profit targets off");
        sourcingLoad(true);
        return true;
      }catch(e){ toast(String(e)); return false; }
    });
}

// "Target: 20% margin · 30% ROI", or one, or none. Both are shown because both
// apply; showing only one would misdescribe the floor the app is pricing to.
function _srcTargetLabel(rule){
  const on = [];
  if(rule.target_margin_pct) on.push(rule.target_margin_pct + '% margin');
  if(rule.target_roi_pct) on.push(rule.target_roi_pct + '% ROI');
  // "Profit target: none" named neither of the two things this sets, so the
  // toolbar -- the only mention of targets visible without expanding a row --
  // gave a reader looking for "margin" or "ROI" nothing to find. See the note
  // beside the per-SKU line in sourcingRow.
  return on.length ? ('Target: ' + on.join(' · '))
                   : 'Margin / ROI target: none';
}

function _srcTargetBox(id, label, value, why, example){
  return '<label style="flex:1 1 220px;min-width:200px">'
    + '<span style="display:block;font-size:12px;font-weight:600;margin-bottom:3px">'
    + _sesc(label) + '</span>'
    + '<span style="display:flex;align-items:center;gap:6px">'
    + '<input id="' + id + '" type="number" min="0" step="0.5" '
    + 'placeholder="off" value="' + (value == null ? '' : _sesc(String(value)))
    + '" style="width:90px;font-size:13px;padding:6px 8px">'
    + '<span class="cc" style="font-size:13px">%</span></span>'
    + '<span class="cc" style="display:block;font-size:11px;margin-top:5px;'
    + 'line-height:1.45">' + why + '</span>'
    + '<span class="cc" style="display:block;font-size:10.5px;margin-top:3px;'
    + 'opacity:.75">' + example + '</span>'
    + '</label>';
}
