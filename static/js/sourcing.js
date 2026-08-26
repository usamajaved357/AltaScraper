// ===================== SOURCE REPRICER =====================
// What the app WOULD do to each enrolled listing, and why.
//
// The screen's whole job is to make a decision arguable before it is armed.
// So every row shows the reasoning, not just the outcome: which supplier was
// chosen, what the others were rejected for, how old the readings were, and the
// arithmetic behind the price. A number with no explanation is exactly what
// nobody should be trusting with their prices.
//
// Nothing here writes to Amazon. The buttons re-read suppliers and re-decide;
// arming the repricer is Phase D and is deliberately not reachable from here.

let SRC_ROWS = [];
let SRC_RULE = null;
// Each SKU's own rule, kept as the rows draw, so the target dialog opens on
// THIS SKU's numbers rather than the account's.
let SRC_ROW_RULES = {};
let SRC_MASTER = false;     // the master switch, as the SERVER reports it

// Every /sourcing call says WHICH account and marketplace it means.
//
// It used to rely on the server's active_marketplace, which this screen never
// sets -- opening the Repricer directly left it empty, so it looked up
// jack_uk::"" , found nothing, and reported "no live listings cached" for an
// account with 55 of them. The browser already knows both; sending them removes
// the guess entirely.
function _srcScope(){
  const p = [];
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
    p.push("id=" + encodeURIComponent(CUR_ACCOUNT.id));
  if(typeof WS_MARKET !== "undefined" && WS_MARKET)
    p.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return p.join("&");
}
function _srcUrl(path, extra){
  const q = [_srcScope(), extra || ""].filter(Boolean).join("&");
  return path + (q ? (path.indexOf("?") >= 0 ? "&" : "?") + q : "");
}
function _srcBody(o){
  const b = Object.assign({}, o || {});
  if(typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id) b.id = CUR_ACCOUNT.id;
  if(typeof WS_MARKET !== "undefined" && WS_MARKET) b.marketplace = WS_MARKET;
  return JSON.stringify(b);
}

function _sesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
// An argument for an inline onclick. Single-quoted for JS, then escaped for the
// attribute -- see the same helper in users.js and the bug that made it
// necessary: JSON.stringify closes the attribute it is pasted into.
function _sarg(s){
  const js = String(s==null?"":s).replace(/\\/g,"\\\\").replace(/'/g,"\\'");
  return "'" + js.replace(/&/g,"&amp;").replace(/"/g,"&quot;")
                 .replace(/</g,"&lt;").replace(/>/g,"&gt;") + "'";
}
function _smoney(v){
  return (v==null || v==="") ? "—" : Number(v).toFixed(2);
}

function sourcingOnOpen(){ sourcingLoad(); }

async function sourcingLoad(){
  const body = document.getElementById("srcbody");
  if(!body) return;
  body.innerHTML = '<div class="cc" style="padding:16px"><span class="genspin"></span> Loading…</div>';
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/list"))).json(); }
  catch(e){ body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">Could not load: '+_sesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>';
    return;
  }
  SRC_ROWS = j.rows || [];
  SRC_RULE = j.rule || j.defaults || {};
  // Read from the server, never remembered from the last click: whether the app
  // is currently allowed to change prices is not something to guess at.
  try{ SRC_MASTER = !!(await (await fetch(_srcUrl("/sourcing/master"))).json()).enabled; }
  catch(e){ SRC_MASTER = false; }
  sourcingRender(j);
  // WHICH SKUS HAVE NOWHERE LEFT TO BUY FROM. Fetched after the table is drawn
  // rather than before it: the alert is important but the table is what the
  // screen is FOR, and one should not wait on the other.
  sourcingAlerts();
}

/* THE OUT-OF-STOCK ALERT.
 *
 * "add an alert in the app that whenever all the links go out of stock i should
 *  receive a notification"
 *
 * The wording comes from the server (domain/stock_alerts.sentence) so this banner
 * and anything else that reports it later cannot say different things.
 *
 * Two groups, deliberately not merged. "Every supplier has ended" is a fact and
 * needs action; "we could not read any of them" is not knowing, and calling that
 * an emergency is how an alert stops being believed.
 */
async function sourcingAlerts(){
  const host = document.getElementById("srcalerts");
  if(!host) return;
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/alerts"))).json(); }
  catch(e){ host.innerHTML = ''; return; }
  if(!j || !j.ok){ host.innerHTML = ''; return; }
  const bad = j.alerts || [], dunno = j.unreadable || [];
  if(!bad.length && !dunno.length){
    // Say the good news too, quietly. A blank space cannot be told apart from a
    // check that never ran.
    host.innerHTML = '<div class="cc" style="font-size:11px;padding:6px 2px">'
      + '<i class="ti ti-check"></i> Every enrolled SKU has at least one supplier '
      + 'that can be bought from.</div>';
    return;
  }
  let h = '';
  if(bad.length){
    h += '<div class="srcalert bad">'
      +  '<div class="srcalert-h">'
      +  '<i class="ti ti-alert-triangle"></i> '
      +  bad.length + ' SKU' + (bad.length===1?' has':'s have')
      +  ' nowhere left to buy from</div>'
      +  _srcAlertBody(bad, j.alerts_shared, 12);
  }
  if(dunno.length){
    h += '<div class="srcalert dunno">'
      +  '<div class="srcalert-h">'
      +  '<i class="ti ti-info-circle"></i> '
      +  dunno.length + ' SKU' + (dunno.length===1?'':'s')
      +  ' could not be read — not known whether they can still be bought</div>'
      +  _srcAlertBody(dunno, j.unreadable_shared, 8);
  }
  host.innerHTML = h;
}

/* The explanation once, then the SKUs.
 *
 * Every alert used to print its own self-contained sentence, which is right for
 * a webhook posting ONE of them into a channel and wrong for a list: twelve
 * alerts came out as twelve copies of the same twenty words. Measured on a
 * phone, that was a full screen of duplicated prose above the page itself.
 *
 *     "all the text all over the app should be arranged and should not be
 *      floating freely"
 *
 * The shared half comes from the server (domain/stock_alerts.group_sentence)
 * beside the sentence it was split out of, so the two cannot drift. When the
 * alerts genuinely have nothing in common the server sends "" and every row
 * falls back to its own full sentence -- correct and repetitive beats tidy and
 * wrong about half the list.
 */
function _srcAlertBody(list, shared, cap){
  let h = shared
    ? '<div class="srcalert-why">' + _sesc(shared) + '</div>'
    : '';
  h += '<div class="srcalert-skus">';
  list.slice(0, cap).forEach(function(a){
    h += '<div>' + _sesc(shared ? (a.row || a.sku) : (a.sentence || a.sku))
      +  '</div>';
  });
  h += '</div>';
  if(list.length > cap){
    h += '<div class="cc" style="padding:3px 0 0">…and ' + (list.length - cap)
      +  ' more.</div>';
  }
  return h + '</div>';
}

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
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingArm(sku, live){
  if(live && !await srcConfirm({
      title: "Arm " + sku + "?",
      body: "From then on the app may change this listing's price, stock and "
          + "handling time on Amazon by itself, without anyone watching.",
      confirm: "Arm it", risk: true})) return;
  try{
    const j = await (await fetch("/sourcing/arm",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, live:!!live})})).json();
    if(!j.ok){ toast(j.error||"Could not arm"); return; }
    toast(j.note || (j.mode==="live" ? "Armed" : "Back to dry run"));
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingMinPrice(sku){
  const v = prompt("Lowest price you will ever sell "+sku+" at.\n\nThis is the one "
                 + "guard that still works if a supplier's page is misread, so the "
                 + "app will not arm a SKU without it.");
  if(v===null) return;
  try{
    const j = await (await fetch("/sourcing/rules",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, rule:{min_price: v===""? null : parseFloat(v)}})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast("Minimum price saved"); sourcingLoad();
  }catch(e){ toast(String(e)); }
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
async function sourcingHoldPrice(sku){
  const cur = (SRC_ROW_RULES[sku]||{}).hold_price;
  const v = prompt(
    "Hold " + sku + " at this price.\n\n"
    + "The repricer will never price BELOW it, even when your ROI or margin target "
    + "would be happy with less. Use it for products where you know what the market "
    + "pays.\n\n"
    + "If the supplier gets dearer and this price stops covering your target, the "
    + "price still goes UP — it is a floor, not a fixed price, so it can never make "
    + "you sell at a loss. When the supplier gets cheaper again the price comes "
    + "straight back to this number.\n\n"
    + "This is NOT the same as 'never sell below', which is there to stop a misread "
    + "supplier page pricing you into a loss. Leave empty to stop holding the price.",
    (cur==null ? "" : String(cur)));
  if(v===null) return;
  try{
    const j = await (await fetch("/sourcing/rules",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, rule:{hold_price: v.trim()==="" ? null : v.trim()}})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    toast(v.trim()==="" ? "No longer holding the price" : "Price held at "+v.trim());
    sourcingLoad();
  }catch(e){ toast(String(e)); }
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

      let ok = 0;
      const failed = [];
      toast("Setting " + plan.length + " floor(s)…");
      for(const p of plan){
        try{
          const j = await (await fetch("/sourcing/rules", {method: "POST",
            headers: {"Content-Type": "application/json"},
            body: _srcBody({sku: p.sku,
                            rule: {min_price: String(p.floor)}})})).json();
          if(j && j.ok) ok++;
          else failed.push(p.sku + ": " + ((j && j.error) || "refused"));
        }catch(e){ failed.push(p.sku + ": " + String(e)); }
      }
      let msg = "Minimum price set on " + ok + " listing(s).";
      if(noPrice) msg += " " + noPrice + " left alone (no price read from Amazon).";
      toast(msg);
      if(failed.length){
        await srcConfirm({
          title: failed.length + " could not be set",
          body: failed.slice(0, 10).join("\n")
              + (failed.length > 10 ? "\n…and " + (failed.length - 10) + " more" : "")
              + "\n\nThe rest were set. Nothing on Amazon has changed.",
          confirm: "OK",
        });
      }
      sourcingLoad();
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
  toast("Holding " + rows.length + " listing(s)…");
  for(const r of rows){
    try{
      const j = await (await fetch("/sourcing/rules", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({sku: r.sku,
                        rule: {hold_price: String(r.current.price)}})})).json();
      if(j && j.ok) ok++; else failed.push(r.sku + ": " + ((j && j.error) || "refused"));
    }catch(e){ failed.push(r.sku + ": " + String(e)); }
  }

  // WHAT HAPPENED, PER SKU WHEN IT WENT WRONG. A count on its own turns a
  // handful of quietly-refused SKUs into "the hold does not work" a fortnight
  // later -- the same reason the supplier upload reports row by row.
  let msg = "Held " + ok + " listing(s) at today's price.";
  if(noPrice) msg += " " + noPrice + " left alone (no price read from Amazon).";
  toast(msg);
  if(failed.length){
    await srcConfirm({
      title: failed.length + " could not be held",
      body: failed.slice(0, 10).join("\n")
          + (failed.length > 10 ? "\n…and " + (failed.length - 10) + " more" : "")
          + "\n\nThe rest were held. Nothing on Amazon has changed.",
      confirm: "OK",
    });
  }
  sourcingLoad();
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
        sourcingLoad();
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

// A small modal with an OK that can refuse to close. prompt() cannot show two
// boxes at once, which is the whole reason this exists.
function _srcModal(title, bodyHtml, onOk){
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
    + 'color:#fff;border-color:var(--accent)">Save</button></div></div>';
  document.body.appendChild(wrap);
  const close = function(){ wrap.remove(); };
  wrap.querySelector("#srcmodal_cancel").onclick = close;
  wrap.onclick = function(e){ if(e.target === wrap) close(); };
  wrap.querySelector("#srcmodal_ok").onclick = async function(){
    const ok = await onOk();
    if(ok !== false) close();     // a refusal keeps the boxes and their values
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
  return new Promise(function(resolve){
    const old = document.getElementById("srcconfirm");
    if(old) old.remove();
    const wrap = document.createElement("div");
    wrap.id = "srcconfirm";
    wrap.className = "modalwrap open";
    wrap.style.zIndex = "9100";
    const para = String(opt.body || "").split("\n\n").map(function(p){
      return '<p style="margin:0 0 9px;font-size:12.5px;line-height:1.6">'
           + _sesc(p) + '</p>';
    }).join("");
    wrap.innerHTML = '<div class="modal" style="max-width:480px">'
      + '<h3>' + _sesc(opt.title || "Are you sure?") + '</h3>'
      + '<div class="cc" style="margin:8px 0 0">' + para + '</div>'
      + '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">'
      + '<button class="db-chip" id="srcconfirm_no">Cancel</button>'
      + '<button class="db-chip ' + (opt.risk ? 'risk' : 'go') + '" '
      + 'id="srcconfirm_yes">' + _sesc(opt.confirm || "Yes") + '</button>'
      + '</div></div>';
    document.body.appendChild(wrap);
    const done = function(v){
      wrap.remove();
      document.removeEventListener("keydown", key);
      resolve(v);
    };
    const key = function(ev){
      if(ev.key === "Escape"){ ev.preventDefault(); done(false); }
    };
    document.addEventListener("keydown", key);
    wrap.onclick = function(e){ if(e.target === wrap) done(false); };
    wrap.querySelector("#srcconfirm_no").onclick = function(){ done(false); };
    wrap.querySelector("#srcconfirm_yes").onclick = function(){ done(true); };
    wrap.querySelector("#srcconfirm_yes").focus();
  });
}

// The chip on a row that is not earning what it is supposed to. Deliberately
// says how far short, not just that it is short -- 0.4% under is a rounding
// argument and 12% under is a supplier you should stop buying from.
function _targetChip(t){
  if(!t) return '';                       // no target set on this SKU
  if(t.meets === null) return '';          // not enough to tell; not a failure
  // WITH BOTH TARGETS ON, the tooltip names them both -- "22% ROI against 30%"
  // alone does not say whether the margin one passed, and someone reading a red
  // chip needs to know which of their two floors this SKU is under.
  const all = (t.parts && t.parts.length ? t.parts : [t])
    .filter(function(x){ return x.meets !== null; })
    .map(function(x){
      return x.kind + ' ' + x.actual_pct + '% against ' + x.target_pct + '%'
           + (x.meets ? '' : ' — ' + x.short_by + ' short'); })
    .join('; ');
  if(t.meets){
    return '<span class="db-chip" style="background:#12321f;color:#7fd18b" title="'
      +  _sesc(all) + '">' + t.kind + ' ' + t.actual_pct + '%</span>';
  }
  return '<span class="db-chip" style="background:#3a1b1b;color:#e88a8a" title="'
    +  _sesc(all)
    +  (t.profit != null ? ' (' + _smoney(t.profit) + ' a unit).' : '.')
    +  '">below ' + t.kind + ' &middot; ' + t.actual_pct + '%</span>';
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
    const cand = await (await fetch("/sourcing/candidates")).json();
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
    if(!j.ok){ toast(j.error||"Could not enrol"); return; }
    // Say what did NOT work as loudly as what did. A bulk action that reports
    // only its successes is how you end up with SKUs quietly tracking nothing.
    let msg = "Now tracking " + j.enrolled + " listing" + (j.enrolled===1?"":"s")
            + " — " + j.linked + " with the supplier the app already had on file";
    if(j.no_link) msg += ", " + j.no_link + " still need a supplier link";
    toast(msg + ".");
    SRC_LASTBULK = j.rows || [];
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
    // No query string, like every other /sourcing call on this page: the
    // server's _where() resolves the open account and marketplace, and adding a
    // second way to say it here is how the two come to disagree.
    c = await (await fetch("/sourcing/sources/count")).json();
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
    const r = await fetch("/sourcing/sources/clear", {
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
    j = await (await fetch("/sourcing/sources/upload", {method: "POST", body: fd})).json();
  }catch(e){ toast(String(e)); return; }
  finally{ inp.value = ""; }

  if(!j.ok){ toast(j.error || "Could not read that sheet"); return; }
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
  if(!j) return '';
  const bad = (j.rows || []).filter(function(r){ return r.status !== "attached"; });
  return '<details class="foldgroup" style="margin-bottom:12px"><summary>'
    + '<i class="ti ti-table-import"></i> Last sheet upload &mdash; '
    + j.attached + ' attached'
    + (j.already ? (', ' + j.already + ' already had one') : '')
    + (j.skipped ? ('<b style="color:#e8c66a">, ' + j.skipped + ' skipped</b>') : '')
    + '<span class="cc"> — matched on "' + _sesc((j.columns||{}).sku || (j.columns||{}).asin || '?')
    + '" and "' + _sesc((j.columns||{}).url || '?') + '"</span></summary>'
    + (bad.length
        ? bad.map(function(r){
            return '<div class="cc" style="font-size:11.5px;padding:3px 0;'
              + 'border-top:1px solid #1c2531">line ' + r.line + ' &middot; '
              + _sesc(r.sku || r.asin || '(no key)') + ' &mdash; ' + _sesc(r.note) + '</div>';
          }).join("")
        : '<div class="cc" style="font-size:11.5px;padding:4px 0">Every row went in.</div>')
    + '</details>';
}

function sourcingRender(j){
  const body = document.getElementById("srcbody");
  const c = j.counts || {};
  let h = "";

  // The standing statement of what the app is doing to real listings right now.
  // It sits at the top rather than in a footnote because "is this live?" is the
  // only question that really matters, and the answer must never be a guess.
  const live = SRC_ROWS.filter(function(r){ return r.mode==="live"; }).length;
  if(SRC_MASTER && live){
    h += '<div style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
      +  'border:1px solid #4a2323;background:#2a1212;border-radius:6px">'
      +  '<b style="color:#e88a8a">Live.</b> '+live+' SKU'+(live===1?" is":"s are")
      +  ' armed and can have their price, stock and handling time changed on '
      +  'Amazon without anyone watching. At most one change each per 4 hours, '
      +  'and never below the minimum price you set. '
      +  '<button class="db-chip" onclick="sourcingMaster(false)" '
      +  'style="margin-left:6px">Stop everything</button></div>';
  } else {
    // TRACKING IS NOT PRICING, and the screen has to say so.
    //
    // "uploading or selecting the skus in the repricer means to track their true
    //  costs from the sources" -- which is what enrolling has always done, but
    //  the screen called itself the repricer and implied that adding a SKU
    //  handed it your prices. It does not, and that is the reason it is safe to
    //  add all of them.
    // Short line, detail on the dot -- the pattern asked for on the notices
    // ("i think this is the right way to write notices"). This was five lines of
    // prose across the top of the screen, which is a paragraph nobody finishes.
    h += '<div class="cc" style="font-size:12px;margin:2px 0 12px;padding:9px 11px;'
      +  'border:1px solid #26403a;background:#10231f;border-radius:6px">'
      +  '<b>Tracking costs. Auto-pricing is off.</b> '
      +  'Suppliers are read every 4 hours and what each unit really costs is '
      +  'written down. Nothing changes a live listing.'
      +  '<span class="infodot" title="'
      +  'It also works out what it WOULD price at, so the decisions can be read '
      +  'before they are trusted - if one looks wrong here, it would have been '
      +  'wrong on Amazon. Adding a SKU is safe: it starts the cost history and '
      +  'nothing more, and each SKU still has to be armed separately. A supplier '
      +  'price on a day nobody was watching cannot be recovered later, which is '
      +  'the reason to add them before you need them.">i</span>'
      +  (SRC_MASTER ? ' <b>Auto-pricing is on</b>, but no SKU is armed for it yet.'
                     : '')
      +  '</div>';
  }

  h += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">'
    // "give a button on the top of the page which explains how do this page
    //  works and what the information means etc etc." First in the row, because
    //  the answer to "what does any of this mean" should not be the seventh
    //  button along.
    +  '<button class="db-chip" onclick="openGuide(\'repricer\')" title="'
    +  'What this page does, what each figure means, and what it will and will '
    +  'not change on Amazon.">'
    +  '<i class="ti ti-book"></i> How this page works</button>'
    +  '<button class="db-chip" onclick="sourcingCheckNow(this)">'
    +  '<i class="ti ti-refresh"></i> Re-read suppliers now</button>'
    +  '<button class="db-chip" onclick="sourcingAddPrompt()">'
    +  '<i class="ti ti-plus"></i> Track a SKU</button>'
    +  '<button class="db-chip go" onclick="sourcingTrackAll(this)" title="'
    +  'Starts watching every live listing that is not already tracked, and '
    +  'attaches the supplier link the app recorded when it built each one. '
    +  'Changes no prices.">'
    +  '<i class="ti ti-eye"></i> Track everything</button>'
    // Suppliers from a sheet. A file input the browser draws itself arrives as
    // the one light-grey control on a dark panel, so it is off-screen behind a
    // label -- the same fix the image library needed.
    +  '<input type="file" id="src_upload" accept=".csv,.tsv,.xlsx,.xlsm,.xls" '
    +  'class="visually-hidden" onchange="sourcingUpload(this)">'
    +  '<label class="db-chip" for="src_upload" style="cursor:pointer" title="'
    +  'A sheet of supplier links. One column of SKUs or ASINs, one column of '
    +  'links — the app matches each link to the right listing and starts '
    +  'tracking it. Nothing is priced.">'
    +  '<i class="ti ti-table-import"></i> Suppliers from a sheet</label>'
    // THE SHEET TO FILL IN, HANDED OVER READY. "give the user the template
    // first filled by the asins enrolled for tracking in the repricer, the user
    // will fill that template and upload it back". A blank sheet means typing
    // forty SKUs by hand, and a hand-typed SKU is the one that silently matches
    // nothing.
    //
    // TEN SUPPLIER COLUMNS, AND MORE IF YOU WANT THEM. It used to be one link
    // column and one row per supplier, because the reader could only see a
    // single link column and extra ones would have been silently ignored. It
    // reads every numbered column now:
    //
    //   "give the option in the template in the repricer page to add multiple
    //    supplier links ... supplier 1, supplier 2 ... upto 10 and the user
    //    should be told that he can add more suplliers by adding more columns
    //    after 10 and giving the heading of 11th count, 12 count and so on"
    +  '<a class="db-chip" href="/sourcing/template.csv" '
    +  'style="text-decoration:none" title="'
    +  'Downloads a sheet already listing every SKU you are tracking, with its '
    +  'ASIN, product name, and its suppliers spread across ten columns headed '
    +  '“supplier 1” to “supplier 10”. One row per SKU. '
    +  'NEED MORE THAN TEN? Add another column and head it “supplier 11”, then '
    +  '“supplier 12”, and so on — there is no limit, the app reads every '
    +  'numbered column it finds. '
    +  'Fill in the blanks and upload it back with the button on the left. '
    +  'Columns you leave blank are not changed, and a link that is already '
    +  'attached is left alone.">'
    +  '<i class="ti ti-file-download"></i> Get the template</a>'
    // THE WAY BACK OUT, beside the two controls that put suppliers IN.
    //
    //     "I also want to delete all the suppliers from the repricer ... so i
    //      can add new suppliers"
    //
    // Suppliers could be added one at a time and by the sheetful, and removed
    // only one at a time from inside a row -- so replacing a whole set meant
    // fifty-five clicks through fifty-five expanded rows.
    +  '<button class="db-chip srcwipe" onclick="sourcingClearSuppliers()" title="'
    +  'Delete every supplier link on this account and marketplace so you can '
    +  'upload a fresh set. The SKUs stay tracked and their targets stay set. '
    +  'Asks first, and says how many links and price readings will go.">'
    +  '<i class="ti ti-eraser"></i> Clear all suppliers</button>'
    +  '<button class="db-chip" onclick="sourcingCheckListings()" title="'
    +  'Asks Amazon whether it still has each tracked SKU. Any it no longer has '
    +  'is marked "deleted on Amazon" and its auto-pricing switched off — its '
    +  'suppliers and history are kept in case you relist it. One Amazon call per '
    +  'SKU, so it takes a moment.">'
    +  '<i class="ti ti-plug-connected-x"></i> Check they still exist</button>'
    // ASK AMAZON WHAT IT ACTUALLY CHARGES, per product.
    //
    //     "the fees of amazon reflecting in the details should be accurate and
    //      not estimate of 15 percent like i see right now in the app"
    //
    // Its own button rather than part of the supplier re-read, because it is a
    // different question asked of a different API, it is rate-limited, and the
    // answer keeps for a week. Pricing never calls Amazon itself -- it reads
    // what this fills.
    +  '<button class="db-chip" onclick="sourcingGetFees(this)" title="'
    +  'Asks Amazon what its referral fee actually is on each tracked product, '
    +  'and remembers it. Prices are then worked out from Amazon&#39;s own '
    +  'figure instead of an assumed 15%. Changes no price by itself.">'
    +  '<i class="ti ti-receipt-tax"></i> Get Amazon&#39;s fees</button>'
    // The switch that actually matters, named for what it does rather than for
    // where it lives. "Master switch: off" did not say off from WHAT.
    +  '<button class="db-chip'+(SRC_MASTER?' risk':'')+'" '
    +  'onclick="sourcingMaster('+(SRC_MASTER?"false":"true")+')" title="'
    +  (SRC_MASTER ? 'Auto-pricing is ON. Armed SKUs can have their price, stock '
                   + 'and handling time changed on Amazon without anyone watching.'
                   : 'Auto-pricing is OFF. Costs are still tracked and decisions '
                   + 'still recorded; nothing reaches Amazon.')+'">'
    +  (SRC_MASTER ? '<i class="ti ti-lock-open"></i> Auto-pricing: ON'
                   : '<i class="ti ti-lock"></i> Auto-pricing: off')+'</button>'
    +  '<button class="db-chip" onclick="sourcingTarget(\'\')" title="'
    +  'The least profit you will accept, as a margin % or an ROI % or both. '
    +  'This is the DEFAULT for every enrolled SKU. To set one for a single '
    +  'product instead, open that row and use &quot;Set for this SKU&quot; -- '
    +  'its own target wins over this one.">'
    +  '<i class="ti ti-target"></i> ' + _srcTargetLabel(j.rule || {})
    +  '</button>'
    +  '</div>';
  // The numbers get cards of their own, under the controls rather than crammed
  // into them.
  if(SRC_ROWS.length) h += _srcCounts(c);
  h += sourcingUploadReport();

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:10px;border:1px dashed #2a3446;border-radius:6px">'
      +  _sesc(j.note)+' Enrol a SKU above to start watching its suppliers.</div>';
    body.innerHTML = h; return;
  }

  // The selection bar sits directly above the rows it acts on, and only when
  // something is selected -- a permanent empty toolbar is one more thing to read
  // past on a screen that already has plenty.
  h += '<div id="srcselbar"></div>';

  // WHAT THE TWO SUPPLIER COLUMNS MEAN, said ONCE.
  //
  // It was printed under every supplier block -- the same sentence 55 times on
  // this account, which is a paragraph of page spent saying one thing. It is
  // still true and still needed the first time, so it moves here rather than
  // going away.
  h += '<div class="cc" style="font-size:11px;margin:2px 0 8px;line-height:1.5">'
    +  '<i class="ti ti-info-circle"></i> Open any supplier line to see them all. '
    +  'Cheapest first, and it re-sorts itself when a supplier changes their '
    +  'price. <b>You pay</b> is their price plus their postage; <b>you keep</b> '
    +  'is what is left of the selling price after Amazon&rsquo;s fee and that '
    +  'supplier.</div>';

  SRC_ROWS.forEach(function(r, i){ h += sourcingRow(r, i); });
  body.innerHTML = h;
  _srcSelBar();
}

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

function sourcingSelectAll(on){
  SRC_SEL = on ? new Set(SRC_ROWS.map(function(r){ return String(r.sku); }))
               : new Set();
  document.querySelectorAll(".srcsel").forEach(function(b){ b.checked = !!on; });
  _srcSelBar();
}

function _srcSelBar(){
  const el = document.getElementById("srcselbar");
  if(!el) return;
  // Only SKUs still on screen count. A filter change can leave a tick on a row
  // nobody can see, and acting on forty when four are visible is the kind of
  // surprise this bar exists to prevent.
  const shown = new Set(SRC_ROWS.map(function(r){ return String(r.sku); }));
  const picked = [...SRC_SEL].filter(function(s){ return shown.has(s); });
  if(!picked.length){ el.innerHTML = ""; return; }
  const armed = SRC_ROWS.filter(function(r){
    return picked.indexOf(String(r.sku)) >= 0 && r.mode === "live"; }).length;
  el.innerHTML =
      '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;'
    + 'padding:9px 11px;margin-bottom:10px;border:1px solid var(--accent-line);'
    + 'background:var(--accent-bg);border-radius:7px;font-size:12.5px">'
    + '<b>' + picked.length + ' selected</b>'
    + (armed ? '<span style="color:var(--warn)">' + armed + ' of them armed</span>' : '')
    + '<span style="flex:1"></span>'
    + '<button class="db-chip" onclick="sourcingSelectAll(true)">Select all '
    + SRC_ROWS.length + '</button>'
    + '<button class="db-chip" onclick="sourcingSelectAll(false)">Clear</button>'
    // THE FLOOR THAT ARMING REQUIRES, settable for everything at once. Without
    // this it is one row at a time, which is why nothing was armed.
    + '<button class="db-chip" onclick="sourcingMinPriceBulk()" title="'
    + 'Give each selected listing a price it will never sell below, worked out '
    + 'as a share of what it sells for today. A SKU cannot be armed without '
    + 'one.">'
    + '<i class="ti ti-arrow-down-circle"></i> Set minimum price</button>'
    // THE ANSWER TO "it should not reduce my selling price", made reachable.
    // The held price did this all along; typing it into 67 SKUs by hand did not.
    + '<button class="db-chip" onclick="sourcingHoldAtCurrent()" title="'
    + 'Write today\'s Amazon price in as the floor for each selected listing. '
    + 'The repricer then never prices below it — a cheaper supplier means more '
    + 'margin, not a lower price — but a dearer one can still push the price UP, '
    + 'so it can never hold you at a loss.">'
    + '<i class="ti ti-lock-dollar"></i> Hold at today\'s price</button>'
    + '<button class="db-chip risk" onclick="sourcingUnenrolSelected()">'
    + '<i class="ti ti-eye-off"></i> Stop tracking ' + picked.length + '</button>'
    + '</div>';
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
    body: "Their supplier links and price history are KEPT — enrol one again "
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
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

// A SUPPLIER LINK IS NOT DATA TO READ.
//
// The reason lines printed the whole URL, and an eBay link carries its search
// terms with it: "...itm/235976183512?_skw=ct3123+Universal+Security+Coupling+
// Hitch+Lock+for+Trailers+Caravan+Horse+Box+Tow+Ball+Fittings%2C+Yellow&itmmeta=
// 01KX041JXHMKKKAPC9ZYBA58YW&hash=item36f146ced8..." -- two hundred characters
// of machine noise per row, wrapping to three lines and burying the sentence
// that actually mattered. The item number is the part a person can use.
function _srcShort(url){
  const u = String(url || "");
  const m = u.match(/\/itm\/(\d{9,15})/);
  if(m) return "eBay item " + m[1];
  try{ return (u.split("/")[2] || u).replace(/^www\./, ""); }
  catch(e){ return u.slice(0, 40); }
}

// The same shortening, applied to a sentence that has URLs embedded in it. The
// reason strings are written server-side as the permanent audit record and are
// deliberately not changed -- this is only how they are drawn.
// Split on the RAW url, then escape each piece. Escaping first and matching
// afterwards does not work: _sesc turns & into &amp;, and an eBay link is mostly
// ampersands, so a pattern that stops at ";" stops inside the first entity and
// leaves the rest of the query string sitting there as text. That is exactly
// what it did, which is why half of each link was still on screen.
function _srcTidy(text){
  const s = String(text || "");
  const re = /https?:\/\/\S+/g;
  let out = "", last = 0, m;
  while((m = re.exec(s)) !== null){
    let url = m[0];
    // Trailing punctuation belongs to the sentence, not to the link.
    const tail = url.match(/[),.;:]+$/);
    if(tail){ url = url.slice(0, -tail[0].length); }
    out += _sesc(s.slice(last, m.index))
        +  '<a href="' + _sesc(url) + '" target="_blank" rel="noopener" title="'
        +  _sesc(url) + '">' + _sesc(_srcShort(url)) + '</a>'
        +  (tail ? _sesc(tail[0]) : "");
    last = m.index + m[0].length;
  }
  return out + _sesc(s.slice(last));
}

// The counts, as cards. They were a run of text in the toolbar -- "17 would
// change · 7 would go out of stock · 31 unchanged · 19 held" -- which is the
// same information Sales gives five cards to, on a screen where those numbers
// are the whole point of looking.
function _srcCounts(c){
  const cards = [
    ["would change", c.update || 0, "var(--accent)"],
    ["would go out of stock", c.out_of_stock || 0, "var(--red)"],
    ["held for review", c.blocked || 0, "var(--warn)"],
    ["unchanged", c.none || 0, ""],
  ];
  if(c.below_target) cards.push(["below target", c.below_target, "var(--red)"]);
  return '<div style="display:grid;gap:10px;margin-bottom:14px;'
    +  'grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">'
    +  cards.map(function(k){
         return '<div class="panelcard" style="padding:12px 14px">'
           +  '<div style="font-size:24px;font-weight:600;line-height:1.15'
           +  (k[2] ? ';color:' + k[2] : '') + '">' + k[1] + '</div>'
           +  '<div class="cc" style="font-size:11.5px;margin-top:2px">' + k[0] + '</div>'
           +  '</div>';
       }).join("")
    +  '</div>';
}

function _actionChip(d){
  const a = d.action;
  if(d.blocked_by) return '<span class="db-chip" style="background:#3a2f12;color:#e8c66a">held</span>';
  if(a==="update") return '<span class="db-chip" style="background:#12303a;color:#6ac7e8">would change</span>';
  if(a==="out_of_stock") return '<span class="db-chip" style="background:#3a1b1b;color:#e88a8a">would go out of stock</span>';
  return '<span class="db-chip">no change</span>';
}

// What we thought a unit cost, against what the supplier charges now. Shown on
// the collapsed row, because a cost that has drifted is not something you would
// know to go looking for -- it has to be in front of you.
function _driftChip(dr){
  if(!dr || dr.delta==null) return '';
  const worse = dr.delta > 0, flat = dr.delta === 0;
  const col = flat ? '' : (worse ? 'background:#3a2f12;color:#e8c66a'
                                 : 'background:#12321f;color:#7fd18b');
  const sign = dr.delta > 0 ? '+' : '';
  return '<span class="db-chip" style="'+col+'" title="'
    +  'This SKU was created when the source cost '+_smoney(dr.cogs)+'. '
    +  'The supplier now charges '+_smoney(dr.landed)+' delivered to you. '
    +  (worse ? 'Every profit figure for this SKU still subtracts the old, lower cost, '
             +  'so profit is overstated by '+_smoney(dr.delta)+' a unit.'
             : (flat ? 'Unchanged since the listing was created.'
                     : 'It is cheaper than when the listing was created.'))
    +  '">cost '+(flat ? 'unchanged' : (worse?'up':'down'))
    +  (flat ? '' : ' '+sign+dr.pct+'%')+'</span>';
}

// The sum, laid out. It exists because the one-sentence version of this was
// accurate and unreadable: "price 20.33 = 11.28 cost + 3.05 fee + 3.00 postage
// + 2.00 ads + 1.00 profit" is five numbers and a total run together, and the
// question it has to answer -- "where did my price come from" -- is answered
// much better by a list than by a sentence. The sentence is still what gets
// stored in the log, unchanged; this is only how it is drawn.
function _priceBreakdown(b, cur){
  if(!b || b.price==null) return '';
  const line = function(label, v, note){
    return '<div style="display:flex;gap:8px;font-size:11.5px;padding:1.5px 0">'
      +  '<span style="min-width:186px" class="cc">'+label+'</span>'
      +  '<span style="min-width:62px;text-align:right">'+_smoney(v)+'</span>'
      +  '<span class="cc">'+(note||'')+'</span></div>';
  };
  let h = '<div class="cc" style="font-size:11px;margin:9px 0 3px">'
        + 'How this price was worked out</div>';
  h += line('What the supplier charges', b.supplier_price, '');
  if(b.supplier_postage!=null && b.supplier_postage>0)
    h += line('Their postage to you', b.supplier_postage, '');
  h += line('So one unit costs you', b.cost, 'delivered to your door');
  // WHOSE FIGURE THIS IS. A rate is just a number; whether Amazon quoted it for
  // this product or it is an average of your own settled orders is the
  // difference between a figure and a guess, and the panel used to say "15%" in
  // both cases. `fee_basis` comes from domain/source_run.decide_one.
  const _fb = (b.fee_basis || "");
  const _rate = ((b.fee_rate || 0) * 100).toFixed(2).replace(/\.00$/, "");
  h += line("Amazon's cut", b.fee,
            _rate + '% of the selling price, not of the cost'
            + (_fb === "quoted"
                ? ' &mdash; <b>Amazon\'s own figure for this product</b>'
                : _fb === "estimated"
                ? ' &mdash; your measured rate, not Amazon\'s quote'
                : ''));
  h += line('Your postage to the buyer', b.postage_label, 'the shipping label');
  h += line('Set aside for ads', b.ads, '');
  // THE NUMBER YOU SET A TARGET AGAINST, said beside the profit it comes from.
  // "profit left over 0.00" was both wrong and unanswerable -- there was no way
  // to tell from this panel whether the price met the 20% you asked for. It now
  // shows the return that profit represents, worked out from the same figures
  // above rather than fetched from anywhere else.
  const _roi = (b.profit != null && b.cost) ? (b.profit / b.cost) * 100 : null;
  h += line('Profit left over', b.profit,
            'what you keep per unit'
            + (_roi == null ? ''
               : ' &mdash; ' + _roi.toFixed(1) + '% of the ' + _smoney(b.cost)
                 + ' you paid'));
  if(b.min_profit != null && b.min_profit > 0){
    h += '<div class="cc" style="font-size:11px;padding:0 0 2px 194px">'
      +  'you asked for at least ' + _smoney(b.min_profit) + ' per unit</div>';
  }
  h += '<div style="display:flex;gap:8px;font-size:12px;font-weight:600;'
    +  'padding:5px 0 0;margin-top:3px;border-top:1px solid #26303f">'
    +  '<span style="min-width:186px">Price it should sell at</span>'
    +  '<span style="min-width:62px;text-align:right">'+_smoney(b.price)+'</span>'
    +  '<span class="cc" style="font-weight:400">'
    +  (cur && cur.price!=null ? 'it is '+_smoney(cur.price)+' now' : '')+'</span></div>';
  if(b.lead_days!=null){
    h += '<div class="cc" style="font-size:11.5px;margin-top:5px">'
      +  'Handling time '+b.lead_days+' days &mdash; the supplier says '
      +  b.supplier_dispatch_days+' to dispatch, plus '+b.buffer_days
      +  ' spare so a slow day does not make you late.</div>';
  }
  if(b.sources_total>1){
    h += '<div class="cc" style="font-size:11.5px;margin-top:3px">'
      +  'Cheapest of '+b.sources_usable+' usable supplier'
      +  (b.sources_usable===1?'':'s')+' out of '+b.sources_total+'.</div>';
  }
  return h;
}

// Every reading we hold for one supplier, newest first. Two readings that never
// move are how you tell a stable price from a stale one, so failures are listed
// rather than hidden.
/* THE DELIVERY LINE, shared with the order details screen.
 *
 * "i want to see this information of the source in the repricer as well" -- the
 * carrier if eBay named one ("Royal Mail Tracked 48"), otherwise the postage as
 * written, then the estimated delivery window and the postcode it was worked out
 * for. All of it is stored on the check by domain/source_fetch.py.
 *
 * The dates are formatted BY THE SERVER for the order screen (delivery_text from
 * domain/order_sources.py) but this screen is handed the raw check row, so it
 * formats them here. Kept to the same shape -- "Tue 18 Aug to Wed 19 Aug" -- so
 * the two screens read alike.
 */
function _srcDeliveryLine(k){
  if(!k) return '';
  const bits = [];
  if(k.postage_text) bits.push(_sesc(k.postage_text));
  else if(k.carrier) bits.push(_sesc(k.carrier));
  const win = _srcWindow(k.delivery_min, k.delivery_max);
  if(win){
    bits.push('arrives ' + win
      + (k.delivery_postcode ? ' to ' + _sesc(k.delivery_postcode) : ''));
  }
  if(!bits.length) return '';
  return '<div class="cc" style="font-size:10.5px;padding:0 0 4px 34px">'
       + bits.join(' · ') + '</div>';
}

function _srcWindow(lo, hi){
  const a = _srcDay(lo), b = _srcDay(hi);
  if(a && b && a !== b) return a + ' to ' + b;
  return b || a || '';
}

function _srcDay(iso){
  // Written out rather than using toLocaleDateString: that follows the browser's
  // locale, so the same date would read differently on two machines looking at
  // the same order.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  if(!m) return '';
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  if(isNaN(d)) return '';
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return days[d.getUTCDay()] + ' ' + d.getUTCDate() + ' ' + mon[d.getUTCMonth()];
}

function _sourceHistory(hist){
  if(!hist || hist.length<2) return '';
  let h = '<div class="cc" style="font-size:11px;margin:5px 0 2px">'
        + 'What this supplier has charged</div>';
  hist.forEach(function(c){
    h += '<div style="display:flex;gap:8px;font-size:11px;padding:1px 0">'
      +  '<span class="cc" style="min-width:132px">'+_sesc(c.at||'')+'</span>'
      +  '<span style="min-width:70px">'
      +  (c.landed!=null ? _smoney(c.landed) : '<span class="cc">could not read</span>')
      +  '</span>'
      +  '<span class="cc">'+(c.status!=='fetched' ? _sesc(c.status||'')
                              : (c.in_stock===false ? 'out of stock' : ''))+'</span>'
      +  '</div>';
  });
  return h;
}

// One line of facts under each SKU. Six small labelled figures rather than a
// sentence, because these are numbers you scan down a column, not read.
function _glanceRow(g){
  if(!g) return '';
  const cell = function(label, value, tone, title){
    if(value === null || value === undefined || value === "") return '';
    return '<span title="' + _sesc(title || '') + '" style="display:inline-flex;'
      + 'flex-direction:column;line-height:1.25;min-width:74px">'
      + '<span style="font-size:12.5px;font-weight:600'
      + (tone ? (';color:' + tone) : '') + '">' + value + '</span>'
      + '<span class="cc" style="font-size:10px">' + label + '</span></span>';
  };
  const pct = function(v){ return (v === null || v === undefined) ? null
                                  : (v.toFixed ? v.toFixed(1) : v) + '%'; };
  // Margin and ROI answer different questions, so they are coloured against
  // different thresholds rather than one shared rule of thumb.
  const mTone = (g.margin_pct === null || g.margin_pct === undefined) ? ''
              : (g.margin_pct >= 20 ? 'var(--ok)'
                 : g.margin_pct >= 8 ? 'var(--warn)' : 'var(--red)');
  const rTone = (g.roi_pct === null || g.roi_pct === undefined) ? ''
              : (g.roi_pct >= 30 ? 'var(--ok)'
                 : g.roi_pct >= 12 ? 'var(--warn)' : 'var(--red)');
  const stockTone = (g.units_available === null || g.units_available === undefined) ? ''
                  : (g.units_available <= 0 ? 'var(--red)'
                     : g.units_available <= 3 ? 'var(--warn)' : '');
  const p = g.promo;
  const pTone = function(v, hi, mid){
    return (v === null || v === undefined) ? ''
         : (v >= hi ? 'var(--ok)' : v >= mid ? 'var(--warn)' : 'var(--red)');
  };
  const bits = [
    cell('cheapest source', _smoney(g.landed),
         '', 'What one unit costs you delivered from the cheapest usable '
         + 'supplier: ' + _smoney(g.source_price) + ' + '
         + _smoney(g.source_postage) + ' postage'),
    cell('selling price', _smoney(g.sell_price), '',
         'What Amazon is charging for it right now, before any coupon'),
    cell('profit / unit', _smoney(g.profit), mTone,
         'At the full selling price, after what the stock cost and Amazon’s fee'
         + (g.fee == null ? '' : ' of ' + _smoney(g.fee))),
    cell('margin', pct(g.margin_pct), mTone, 'Profit as a share of the selling price'),
    cell('ROI', pct(g.roi_pct), rTone, 'Profit as a share of what you paid for the unit'),
  ];

  // THE SAME THREE AGAIN, WITH THE COUPON ON.
  //
  //     "show profit per unit when no promotion like coupon or discounts etc
  //      are applied and also show the profit when some coupons or promotions
  //      etc are applied ... also show roi and margin in both cases"
  //
  // Only when a discount was actually measured. Showing an identical pair of
  // columns on every row would be four more numbers to read past on the SKUs
  // that have no coupon at all, and would imply the app had checked and found
  // nothing when in fact it cannot check -- see domain/promotions.py.
  if(p){
    const why = 'After the discount this SKU has actually been selling under: '
              + _smoney(p.amount_per_unit) + ' a unit'
              + (p.pct == null ? '' : ' (about ' + p.pct.toFixed(0) + '% off)')
              + '. ' + (g.promo_note || '');
    bits.push(cell('after coupon', _smoney(g.sell_price_promo), 'var(--warn)', why));
    bits.push(cell('profit / unit', _smoney(g.profit_promo),
                   pTone(g.margin_pct_promo, 20, 8), why));
    bits.push(cell('margin', pct(g.margin_pct_promo),
                   pTone(g.margin_pct_promo, 20, 8), why));
    bits.push(cell('ROI', pct(g.roi_pct_promo),
                   pTone(g.roi_pct_promo, 30, 12), why));
  }

  bits.push(cell('units at source', g.units_available, stockTone,
       'How many the supplier says are left. eBay sometimes reports a floor rather than a count.'));
  // HANDLING TIME AS IT STANDS NOW. "also show ... the handling time set for
  // each item at that time" -- what is promised to the buyer today, and what it
  // is built from, rather than only the one the repricer would propose.
  bits.push(cell('handling', (g.handling_days == null ? null : g.handling_days + 'd'), '',
       'Supplier dispatch ' + (g.dispatch_days == null ? '?' : g.dispatch_days)
       + 'd plus the safety buffer — what would be promised to the buyer'));

  const kept = bits.filter(Boolean);
  if(!kept.length) return '';
  // The coupon pair is separated by a divider rather than run together with the
  // full-price figures, because two "profit / unit" labels side by side with
  // nothing between them is the free-flowing text problem all over again.
  let h = '<div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;'
        + 'padding:8px 10px;background:var(--panel2);border-radius:6px;'
        + 'align-items:flex-start">' + kept.join("");
  if(p){
    h += '<span class="cc" style="width:100%;font-size:10px;margin-top:2px">'
      +  '<i class="ti ti-tag"></i> The four figures after “after coupon” are '
      +  'the same sale with the discount applied. ' + _sesc(g.promo_note || '')
      +  '</span>';
  }
  return h + '</div>';
}

// The picture and the name, with the SKU underneath it as the small print it
// always should have been. The picture comes from the same catalogue the
// Listings cards and the Orders rows use, so one product looks the same
// wherever it appears. An icon rather than a broken image when there is none.
function _srcItemCell(item, sku){
  const it = item || {};
  // WHOSE PICTURE THIS IS. An Amazon one is what is live on the listing; a
  // supplier one is the source listing's photograph, used because the SKU is a
  // draft Amazon has never seen. Showing the second as though it were the first
  // would be the app telling you what is on your listing when it is nothing of
  // the kind, so it carries a corner mark and says so on hover.
  const fromSupplier = (it.img_source === "supplier");
  const why = fromSupplier
    ? "This is the SUPPLIER’s photograph, from the source listing. Amazon has no "
      + "image for this SKU — either it is still a draft, or Amazon returned none."
    : "The image on the live Amazon listing.";
  const pic = it.img
    ? '<span style="position:relative;flex:0 0 38px;line-height:0" title="'
      + _sesc(why) + '">'
      + '<img src="' + _sesc(thumbUrl(it.img, 38)) + '" loading="lazy" decoding="async" alt="" style="width:38px;'
      + 'height:38px;object-fit:contain;background:#0d1220;border-radius:6px">'
      + (fromSupplier
          ? '<span style="position:absolute;right:-2px;bottom:-2px;'
            + 'background:#3a2f14;color:#e8c66a;border-radius:3px;font-size:8px;'
            + 'padding:0 2px;line-height:11px;font-weight:600">SRC</span>'
          : '')
      + '</span>'
    : '<span style="width:38px;height:38px;border-radius:6px;background:#0d1220;'
      + 'display:inline-flex;align-items:center;justify-content:center;'
      + 'flex:0 0 38px" title="No picture — Amazon has none for this SKU and the '
      + 'draft carries none either."><i class="ti ti-photo" style="opacity:.4"></i></span>';
  return '<span style="display:flex;gap:9px;align-items:center;min-width:0;'
    + 'max-width:420px">' + pic + '<span style="min-width:0">'
    + (it.title
        ? '<span style="display:block;font-size:12px;line-height:1.3;'
          + 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'
          + _sesc(it.title) + '">' + _sesc(it.title) + '</span>'
        : '')
    + '<code style="font-size:' + (it.title ? '10px' : '12px') + ';opacity:'
    + (it.title ? '.7' : '1') + '">' + _sesc(sku) + '</code>'
    + '</span></span>';
}

// THIS OFFER IS GONE FROM AMAZON. Loud, because nothing else on the row can
// matter: there is no listing to price.
//
// "the template and the repricer is saving the skus which i have deleted
//  already, turn off the auto repricing for that sku and give warning to tell
//  that this offer is deleted"
//
// Auto-pricing is already off by the time this draws -- set_listing_state
// disarms in the same statement that marks it -- so this says what happened
// rather than warning about what might.
function _goneChip(d){
  if(!d || String(d.listing_state || "") !== "gone") return "";
  return '<span class="db-chip" style="background:#3a1b1b;color:#e88a8a;'
    + 'border-color:#5a2a2a" title="Amazon no longer has this SKU, so there is '
    + 'no offer to price. Auto-pricing has been switched off for it. Its '
    + 'suppliers and history are kept in case you relist it.">'
    + '<i class="ti ti-trash-x"></i> deleted on Amazon</span>';
}

// Ask Amazon which enrolled SKUs it still has. One call per SKU, so it is a
// button rather than something that runs on every draw.
async function sourcingCheckListings(){
  if(!await srcConfirm({
      title: "Check every tracked SKU against Amazon?",
      body: "This asks Amazon once per SKU, so it takes a moment on a long "
          + "list. Any SKU Amazon no longer has is marked and its auto-pricing "
          + "switched off — nothing is deleted.",
      confirm: "Check them"})) return;
  toast("Asking Amazon about each tracked SKU…");
  try{
    const j = await (await fetch("/sourcing/check_listings", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({})})).json();
    if(!j.ok){ toast(j.error || "failed"); return; }
    toast(j.note || ("checked " + j.checked));
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

/* HOW MANY SUPPLIER LINKS THIS SKU HAS, and how many can be bought from.
 *
 * Clicking it opens the same panel the "Why?" button does, so the count is both
 * the answer and the way to see the detail behind it.
 *
 * "no supplier" is drawn in amber rather than as a plain zero: a tracked SKU with
 * nothing attached can never be priced, and that is a job to do rather than a
 * neutral fact.
 */
function _srcCountChip(r, id){
  const list = r.sources || [];
  const n = list.length;
  const live = list.filter(function(s){
    const k = s.check || {};
    return k.status === "fetched" && k.in_stock !== false;
  }).length;
  if(!n){
    return '<button class="db-chip" style="background:#3a3320;color:#e8c66a" '
         + 'onclick="sourcingToggleDetail(' + _sarg(id) + ')" '
         + 'title="Nothing to buy this from, so no price can be worked out. '
         + 'Add a supplier link.">no supplier</button>';
  }
  // "2 of 3 usable" only when they differ -- saying "1 of 1" on every row is
  // noise that makes the rows that DO differ harder to spot.
  const label = (live === n)
    ? (n + ' supplier' + (n === 1 ? '' : 's'))
    : (live + ' of ' + n + ' usable');
  return '<button class="db-chip"'
       + (live < n ? ' style="background:#3a3320;color:#e8c66a"' : '')
       + ' onclick="sourcingToggleDetail(' + _sarg(id) + ')"'
       + ' title="' + (live < n
            ? (n - live) + ' of this SKU\'s links cannot be bought from right now. '
            : '')
       + 'Click to see the links, their prices and their delivery.">'
       + label + '</button>';
}

/* The same shape domain/order_sources.summary() returns, worked out in the
 * browser from the options the row already carries. Only the two fields the
 * renderer reads are needed; asking the server for the rest would be a second
 * round trip for something already on the page. */
function _srcOptSummary(opts){
  const o = opts || [];
  const buyable = o.filter(function(x){ return x.state === "buyable"; });
  return {total: o.length, buyable: buyable.length,
          dead: o.filter(function(x){ return x.state === "dead"; }).length,
          all_dead: !!(o.length && !buyable.length
                       && !o.filter(function(x){ return x.state === "unknown"; }).length)};
}

function sourcingRow(r, i){
  const d = r.decision || {}, cur = r.current || {};
  const id = "srcrow_"+i;
  let h = '<div style="border:1px solid #26303f;border-radius:7px;padding:10px 12px;margin-bottom:9px">';

  // THE PRODUCT, not just its code. "i want to see the images of the items in
  // the repricer so it is easy to understand for which product are we talking
  // about" -- 10.39_3Days_B0F6LQ1S93 is unreadable, and this screen is where
  // you decide whether to keep selling something.
  h += '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">'
    // PICK SEVERAL AND ACT ON THEM ONCE. "also allow to select multiple skus at
    // once and unroll them from tracking" -- removing forty one at a time is
    // forty confirmations, and forty is the normal case after a bulk import
    // that pulled in more than was wanted.
    +  '<input type="checkbox" class="srcsel" data-sku="' + _sesc(r.sku) + '"'
    +  (SRC_SEL.has(r.sku) ? ' checked' : '')
    +  ' onclick="event.stopPropagation();sourcingSelect(' + _sarg(r.sku)
    +  ',this.checked)" title="Select this SKU" '
    +  'style="width:15px;height:15px;cursor:pointer;accent-color:var(--accent);flex:none">'
    +  _srcItemCell(r.item, r.sku)
    +  _goneChip(d)
    +  _actionChip(d)
    +  _driftChip(r.drift)
    +  _targetChip(d.target)
    +  '<span style="flex:1"></span>'
    +  '<span class="cc" style="font-size:11.5px">now '+_smoney(cur.price)
    +  (cur.lead_days!=null ? ' &middot; '+cur.lead_days+'d handling' : '')
    +  '</span>';
  if(d.action==="update"){
    h += '<span style="font-size:12px;font-weight:600">&rarr; '+_smoney(d.price)
      +  (d.lead_days!=null ? ' &middot; '+d.lead_days+'d' : '')+'</span>';
  }
  // HOW MANY SUPPLIERS THIS SKU HAS, on the row itself.
  //
  // "i am not able to see all the source links in the repricer" -- they were all
  // there, but only inside a panel opened by a button labelled "Why?", which
  // sounds like it explains the price rather than lists the suppliers. So the
  // count was invisible: with one link on every SKU there was no way to tell
  // whether that was all of them or all the screen was showing.
  //
  // The chip is the same button, so clicking the count opens the list.
  h += _srcCountChip(r, id)
    +  '<button class="db-chip" onclick="sourcingToggleDetail('+_sarg(id)+')">Why?</button>'
    // WHY IT CANNOT BE ARMED, ON THE BUTTON.
    //
    //     "i am not able to arm a sku"
    //
    // It could not be, and the reason was real: no minimum price. But the only
    // place that was said was the button's TOOLTIP, which you have to hover to
    // read and which never appears on a phone. So the button looked ordinary,
    // did nothing anybody could see, and the answer was invisible.
    //
    // Now the button names the missing thing and OPENS it, so the fix is one
    // click from the problem instead of a hunt through the row's detail panel.
    +  (r.mode==="live"
        ? '<button class="db-chip" style="background:#3a1b1b;color:#e88a8a" '
          + 'onclick="sourcingArm('+_sarg(r.sku)+',false)">Armed &mdash; disarm</button>'
        : ((r.rule||{}).min_price == null
            ? '<button class="db-chip" style="border-color:var(--warn);'
              + 'color:var(--warn)" onclick="sourcingMinPrice('+_sarg(r.sku)+')" '
              + 'title="A SKU cannot be armed until it has a price it will never '
              + 'sell below. That floor is the one guard that still works if a '
              + 'supplier&#39;s page is misread. Click to set it.">'
              + 'Set a minimum price to arm</button>'
            : '<button class="db-chip" onclick="sourcingArm('+_sarg(r.sku)+',true)">Arm</button>'))
    +  '<button class="db-chip" onclick="sourcingUnenrol('+_sarg(r.sku)+')">Remove</button>'
    +  '</div>';

  // THE ROW AT A GLANCE.
  //
  // "i want to add some additional info which give me a glance view to be
  //  displayed on each sku, current source price, current my selling price on
  //  which the item will be sold if i receive an order and the profit margin and
  //  the roi i will generate on the sale. source units available, the shipping
  //  days of the supplier"
  //
  // Every figure is about the sale that would happen NOW -- what Amazon is
  // charging today against what the supplier charges today -- which is a
  // different question from the price the repricer would LIKE it to be. That one
  // is already on the line above.
  //
  // Blank where unknown. A margin shown as 0% because nothing could be read is a
  // number somebody would act on.
  h += _glanceRow(r.glance);

  // EVERY SUPPLIER LINK, ON THE ROW.
  //
  //     "i want to be shown all the available supplier/ source links and
  //      highlight the cheapest of all of them ... and under it where the
  //      source links are mentioned show the delivery time of the suppliers"
  //
  // They were only ever behind a button labelled "Why?", which sounds like it
  // explains the price rather than lists the suppliers -- so with one link on
  // every SKU there was no way to tell whether that was all of them or all the
  // screen was showing.
  //
  // Drawn by _ordSourcesHtml, which is the ORDER panel's renderer, from the same
  // options_for data. One list, one ranking, one delivery sentence, on both
  // screens (Rule 12). If orders.js has not loaded the row simply keeps the
  // count chip it always had rather than breaking.
  // FOLDED, because there are sixty-four of these on this screen and one on an
  // order. Measured on jack_uk: the supplier blocks were 8,888px of a 19,201px
  // page. The summary line carries the answer -- how many suppliers, the
  // cheapest landed cost, what you keep, what is wrong -- and opens to exactly
  // the same table.
  if((r.options || []).length && typeof _ordSourcesHtml === "function"){
    h += _ordSourcesHtml({options: r.options,
                          summary: _srcOptSummary(r.options),
                          unit_price: (r.current || {}).price},
                         "", {compact: true});
  }

  // The reason line is the point of the whole screen.
  h += '<div class="cc" style="font-size:11.5px;margin-top:5px;line-height:1.5">'
    +  (d.blocked_by ? '<b style="color:#e8c66a">'+_sesc(d.blocked_by)+'</b> &mdash; ' : '')
    +  _srcTidy(d.reason||"")+'</div>';

  h += '<div id="'+id+'" style="display:none;margin-top:9px">';

  h += _priceBreakdown(d.breakdown, cur);

  // What the target is doing to THIS listing, under the sum it changes. The
  // chip above is the flag; this says what it would take to clear it, which is
  // the number you need to decide whether the supplier is still worth buying
  // from at all.
  const tg = d.target, bd = d.breakdown || {};
  if(tg && tg.meets === false){
    // EVERY target it misses, not just the worst. With two on, "it earns 22%
    // ROI against 30%" leaves the margin one unaccounted for, and the price
    // needed clears BOTH -- so naming one and quoting a floor set by the other
    // is a sum that does not add up on screen.
    const miss = (tg.parts && tg.parts.length ? tg.parts : [tg])
      .filter(function(x){ return x.meets === false; });
    h += '<div class="cc" style="font-size:11.5px;margin-top:7px;padding:6px 8px;'
      +  'border:1px solid #4a2323;background:#2a1212;border-radius:6px">'
      +  'At its current price this earns '
      +  miss.map(function(x){
           return '<b>'+x.actual_pct+'%</b> '+x.kind+' against your <b>'
                + x.target_pct+'%</b>'; }).join(', and ')
      +  (tg.profit!=null ? ' &mdash; '+_smoney(tg.profit)+' a unit' : '')
      +  '. '
      +  (bd.target_floor!=null
          ? 'It would need <b>'+_smoney(bd.target_floor)+'</b> to clear '
            + (miss.length > 1 ? 'both' : 'it') + '.'
          : '')
      +  '</div>';
  }

  // The cost comparison in words, under the sum it affects. The chip in the
  // header is the flag; this is the sentence that says what it means, because
  // "cost up 9%" does not on its own tell you that a profit figure is wrong.
  const dr = r.drift || {};
  if(dr.delta!=null && dr.delta!==0){
    h += '<div class="cc" style="font-size:11.5px;margin-top:7px;padding:6px 8px;'
      +  'border:1px solid #2a3446;border-radius:6px">'
      +  'This SKU was created when a unit cost <b>'+_smoney(dr.cogs)+'</b>'
      +  (dr.cogs_source==='manual' ? ' (you set that by hand)' : ' (from the SKU name)')
      +  '. The supplier now charges <b>'+_smoney(dr.landed)+'</b> delivered. '
      +  (dr.delta>0
          ? 'Profit figures for this SKU still subtract the old '+_smoney(dr.cogs)
            + ', so they are overstated by about '+_smoney(dr.delta)+' on every unit sold.'
          : 'It is cheaper than it was, so profit figures are understating it by about '
            + _smoney(Math.abs(dr.delta))+' a unit.')
      +  '</div>';
  }

  h += '<div class="cc" style="font-size:11px;margin:9px 0 4px">Suppliers</div>';
  (r.sources||[]).forEach(function(s){
    const k = s.check || {};
    const rej = (d.rejections||[]).find(function(x){ return x.source_id===s.id; });
    const chosen = d.source_id===s.id;
    h += '<div style="display:flex;gap:8px;align-items:center;font-size:11.5px;'
      +  'padding:4px 0;border-top:1px solid #1c2531">'
      +  (chosen ? '<span class="db-chip" style="background:#12303a;color:#6ac7e8">using</span>'
                 : '<span class="db-chip" style="opacity:.55">—</span>')
      // The name comes from the server (domain/source_link.display_name), which
      // knows the seller eBay published and any label typed in the template.
      // _srcShort is the fallback for an older payload that has no name on it.
      +  '<a href="'+_sesc(s.url)+'" target="_blank" rel="noopener" title="'+_sesc(s.url)+'" '
      +  'style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
      +  _sesc(s.name || _srcShort(s.url))+'</a>'
      +  '<span class="cc">'+_sesc(s.kind)+'</span>'
      +  '<span style="flex:1"></span>'
      +  '<span>'+_smoney(k.price)+' + '+(k.shipping==null?'<b style="color:#e8c66a">postage unknown</b>':_smoney(k.shipping))+'</span>'
      +  '<span class="cc">'+(k.in_stock===true?'in stock':k.in_stock===false?'out of stock':'stock unknown')+'</span>'
      +  '<span class="cc">'+(k.dispatch_days==null?'':k.dispatch_days+'d')+'</span>'
      +  (rej ? '<span class="cc" style="color:#e8c66a">'+_sesc(rej.reason)+'</span>' : '')
      +  '<button class="db-chip" onclick="sourcingRemoveSource('+s.id+')">×</button>'
      +  '</div>';
    // HOW IT GETS HERE AND WHEN. "i want to see this information of the source in
    // the repricer as well" -- the same facts, and the same wording, as the order
    // details screen. The line is only drawn when eBay actually said something.
    h += _srcDeliveryLine(k);
    h += _sourceHistory(s.history);
  });
  if(!(r.sources||[]).length){
    h += '<div class="cc" style="font-size:11.5px;padding:4px 0">'
      +  'No suppliers yet &mdash; nothing can be decided until one is added.</div>';
  }
  h += '<div style="margin-top:7px"><button class="db-chip" '
    +  'onclick="sourcingAddSourcePrompt('+_sarg(r.sku)+')">'
    +  '<i class="ti ti-plus"></i> Add a supplier link</button></div>';
  // The minimum price is shown whether or not it is set, because its ABSENCE is
  // the reason a SKU cannot be armed, and that has to be visible at the point of
  // trying rather than only in the error message afterwards.
  const mp = (r.rule||{}).min_price;
  h += '<div class="cc" style="font-size:11.5px;margin-top:7px">Never sell below: '
    +  (mp==null
        ? '<b style="color:#e8c66a">not set</b> — required before this SKU can be armed'
        : '<b>'+_smoney(mp)+'</b>')
    +  ' <button class="db-chip" onclick="sourcingMinPrice('+_sarg(r.sku)+')">'
    +  (mp==null?'Set':'Change')+'</button></div>';
  // The target, per SKU. A cheap fast-moving line and an expensive slow one do
  // not want the same percentage, so the account-wide setting is a default
  // rather than a rule.
  const rr = r.rule || {};
  // Remembered so the two boxes open showing what THIS SKU has, rather than the
  // account default -- opening them pre-filled with someone else's numbers and
  // pressing Save would silently overwrite the override.
  SRC_ROW_RULES[r.sku] = rr;
  const anyT = (rr.target_margin_pct != null || rr.target_roi_pct != null);
  // IT NAMES THE TWO THINGS IT SETS, EVEN WHEN NEITHER IS SET.
  //
  //     "i am looking at repricer, i dont have an option to set the margin and
  //      roi target per item"
  //
  // It was there and it worked -- measured on this account, 67 per-SKU buttons,
  // one for every enrolled SKU, each wired to its own rule row. What it never
  // did was SAY SO. Unset, the line read "Least profit accepted: the flat
  // minimum only [Set]" and the toolbar read "Profit target: none", so the words
  // "margin" and "ROI" appeared nowhere on the screen until after a target
  // existed. Anyone scanning for them concluded the feature was missing, which
  // is what happened.
  //
  // The plain-English phrase is kept -- it is what the setting MEANS, and Rule 5
  // asks for that first -- with the two names it is known by beside it.
  h += '<div class="cc" style="font-size:11.5px;margin-top:5px">'
    +  'Least profit accepted <span class="cc">(margin / ROI target)</span>: '
    +  (anyT ? '<b>' + _sesc(_srcTargetLabel(rr).replace(/^Target: /, '')) + '</b>'
             : '<span class="cc">not set — the flat minimum only</span>')
    +  ' <button class="db-chip" onclick="sourcingTarget('+_sarg(r.sku)+')">'
    +  (anyT?'Change this SKU':'Set for this SKU')+'</button></div>';

  /* THE MARKET PRICE, HELD.
   *
   * "i want the repricer to not to change my price if the margin or roi target set
   *  is less than my selling price ... this rule is for the items where i am sure
   *  that this is the market price and this product sells on this price point no
   *  matter the roi or margin"
   *
   * Deliberately its OWN box and not the "never sell below" one above. That one is
   * loss protection; this one is a commercial decision. Sharing a field would mean
   * dropping the floor for a clearance also let the repricer undercut the market
   * price -- see hold_price in domain/sourcing.DEFAULT_RULE.
   */
  const hp = rr.hold_price;
  h += '<div class="cc" style="font-size:11.5px;margin-top:5px">Hold the price at: '
    +  (hp==null
        ? '<span class="cc">not held — the price follows the supplier and the target</span>'
        : '<b>'+_smoney(hp)+'</b>')
    +  ' <button class="db-chip" onclick="sourcingHoldPrice('+_sarg(r.sku)+')">'
    +  (hp==null?'Set':'Change')+'</button>'
    +  '<span class="infodot" title="Use this when you know what a product sells '
    +  'for. The repricer will never price BELOW this, even if your ROI or margin '
    +  'target would be satisfied by less — so a 40.00 line stays at 40.00 on a '
    +  '12.00 cost. If the supplier gets dearer and 40.00 no longer covers your '
    +  'target, the price still goes UP; when they get cheaper again it comes back '
    +  'to 40.00. It can never hold a price below what the unit costs to sell.">i</span>'
    +  '</div>';
  // WHAT IT IS DOING RIGHT NOW, said on the row rather than left in the log. A
  // held price with no explanation beside it looks like a repricer that has
  // stopped working.
  if(d.held){
    h += '<div style="font-size:11.5px;margin-top:4px;padding:6px 8px;'
      +  'border:1px solid #1d3a2a;background:#0f2318;border-radius:6px">'
      +  '<b>Held at '+_smoney(d.held_at)+'.</b> Your rules and targets would have '
      +  'priced this at '+_smoney(d.held_over)+' — lower, so it was not used.</div>';
  }else if(d.hold_exceeded!=null){
    h += '<div style="font-size:11.5px;margin-top:4px;padding:6px 8px;'
      +  'border:1px solid #3a3320;background:#241f10;border-radius:6px">'
      +  'The supplier has risen, so '+_smoney(d.price)+' is now ABOVE the '
      +  _smoney(d.hold_exceeded)+' you hold this at. The held price is a floor, '
      +  'not a fixed price, so it goes up rather than selling at a loss.</div>';
  }else if(d.hold_capped){
    h += '<div style="font-size:11.5px;margin-top:4px;padding:6px 8px;'
      +  'border:1px solid #5c2b2b;background:#2a1414;color:#ffb4b4;border-radius:6px">'
      +  'You hold this at '+_smoney(d.hold_capped.hold)+' but the maximum price is '
      +  _smoney(d.hold_capped.ceiling)+', so the ceiling won. One of the two needs '
      +  'changing.</div>';
  }
  if(d.inputs_age_mins!=null){
    h += '<div class="cc" style="font-size:11px;margin-top:6px">Decided on a reading '
      +  Math.round(d.inputs_age_mins)+' minutes old.</div>';
  }
  h += '</div></div>';
  return h;
}

function sourcingToggleDetail(id){
  const el = document.getElementById(id);
  if(el) el.style.display = (el.style.display==="none") ? "block" : "none";
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
// A typed SKU with a typo in it enrols a product that does not exist: the sweep
// finds no sources, the screen shows a row that never decides anything, and
// nothing anywhere says the SKU was wrong.
async function sourcingAddPrompt(){
  const host = document.getElementById("srcpick");
  if(!host) return;
  host.style.display = "block";
  host.innerHTML = '<div class="cc" style="padding:14px"><span class="genspin"></span> Loading this account\'s live listings…</div>';
  await sourcingPickerLoad("");
}

async function sourcingPickerLoad(q){
  const host = document.getElementById("srcpick");
  if(!host) return;
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/candidates","q="+encodeURIComponent(q||"")))).json(); }
  catch(e){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc(String(e))+'</div>'; return; }
  if(!j || !j.ok){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc((j&&j.error)||"Could not load")+'</div>'; return; }

  let h = '<div style="border:1px solid #26303f;border-radius:8px;padding:12px;margin-bottom:12px">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
    + '<b style="font-size:13px">Enrol a listing</b>'
    + '<span class="cc" style="font-size:11px">'+j.count+' live on this account</span>'
    + '<span style="flex:1"></span>'
    + '<input id="srcpickq" placeholder="filter by SKU or title" value="'+_sesc(q||"")+'" '
    + 'oninput="sourcingPickerFilter(this.value)" style="font-size:12px;padding:4px 8px;min-width:200px">'
    + '<button class="db-chip" onclick="sourcingPickerClose()">Close</button></div>';

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:8px">'+_sesc(j.note)+'</div></div>';
    host.innerHTML = h; return;
  }

  h += '<div style="max-height:340px;overflow:auto">';
  (j.items||[]).forEach(function(it){
    h += '<div style="display:flex;gap:9px;align-items:center;font-size:11.5px;'
      +  'padding:6px 4px;border-top:1px solid #1c2531">'
      // The product, at a glance. A SKU is "10.06_3Days_B0081ZHHTS" and a title
      // is forty words of keywords; neither says what the thing is, and
      // enrolling the wrong one reprices it against somebody else's supplier.
      +  (it.img
          ? '<img src="'+_sesc(thumbUrl(it.img, 38))+'" loading="lazy" decoding="async" alt="" '
            + 'style="width:38px;height:38px;object-fit:contain;background:#0d1220;'
            + 'border-radius:5px;flex:0 0 auto">'
          : '<span style="width:38px;height:38px;border-radius:5px;flex:0 0 auto;'
            + 'background:#0d1220;display:inline-block"></span>')
      +  '<code style="min-width:150px">'+_sesc(it.sku)+'</code>'
      +  '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" '
      +  'title="'+_sesc(it.title)+'">'+_sesc(it.title||"(no title)")+'</span>'
      +  (/AFN|AMAZON|FBA/i.test(it.fulfillment||"")
          ? '<span class="db-chip" style="opacity:.6" title="Amazon holds this stock, so the repricer leaves it alone">FBA</span>'
          : '')
      +  '<span class="cc">'+_smoney(it.price)+'</span>'
      +  (it.enrolled
          ? '<span class="db-chip" style="background:#12303a;color:#6ac7e8">enrolled'
            + (it.sources? ' · '+it.sources+' source'+(it.sources===1?'':'s') : ' · no sources yet')+'</span>'
          : '<button class="db-chip" onclick="sourcingEnrolPicked('+_sarg(it.sku)+')">Enrol</button>')
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
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku})})).json();
    if(!j.ok){ toast(j.error||"Could not enrol"); return; }
    toast("Enrolled in dry run — add a supplier link next");
    await sourcingPickerLoad((document.getElementById("srcpickq")||{}).value||"");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingUnenrol(sku){
  if(!await srcConfirm({
      title: "Stop tracking " + sku + "?",
      body: "Its supplier links and price history are kept — enrol it again "
          + "later and everything is still attached. Nothing on Amazon changes.",
      confirm: "Stop tracking", risk: true})) return;
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, enrolled:false})})).json();
    if(!j.ok){ toast(j.error||"failed"); return; }
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}

async function sourcingAddSourcePrompt(sku){
  const url = prompt("Paste the supplier's link for "+sku+".\n\neBay links are read "
                   + "through eBay's own API. Other sites are read only if they "
                   + "publish structured product data — the app will tell you if "
                   + "it cannot read one rather than guess a price.");
  if(!url) return;
  try{
    const j = await (await fetch("/sourcing/source/add",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku, url:url.trim()})})).json();
    if(!j.ok){ toast(j.error||"Could not add"); return; }
    toast("Supplier added — press “Re-read suppliers now” to check it");
    sourcingLoad();
  }catch(e){ toast(String(e)); }
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
    sourcingLoad();
  }catch(e){ toast(String(e)); }
}
