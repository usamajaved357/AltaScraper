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
// Which marketplace the rows are from, so the money editors show the right
// currency symbol. Read off the server's answer rather than a global set by
// whichever screen was opened last.
let SRC_MKT = "";
// What a NEWLY enrolled SKU should start with. Set by the owner in the ⋯ menu;
// it does NOT touch SKUs that are already tracked.
let SRC_DEFAULT_TARGET = {};
// Which stat card is filtering the table: "" | armed | update | out_of_stock.
let SRC_FILTER = "";
// The last /sourcing/list answer, so a filter can redraw without refetching.
let SRC_LAST_J = null;

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
/* An amount, WITH the currency it is in.
 *
 * It used to return a bare "10.06". On a UK-only screen that is merely terse;
 * across accounts it is wrong -- sheelady_us and miles_lubricants sell in
 * dollars, and a bare number beside a pound-denominated cost is a figure the
 * reader has no way to place. Every money figure on this screen goes through
 * here, so this is the one place that has to know (CLAUDE.md Rule 12).
 *
 * The symbol comes from _srcSym(), which reads the marketplace the ROWS came
 * from rather than whichever screen happened to be opened last.
 *
 * The dash for an unknown amount was mojibake -- three bytes that render as a
 * capital A with a circumflex followed by two more -- from a cp1252 round
 * trip. It is a real em dash now.
 */
function _smoney(v){
  if(v == null || v === "") return "\u2014";
  const n = Number(v);
  if(!isFinite(n)) return "\u2014";
  return _srcSym() + n.toFixed(2);
}

// LOUD, and it is the one place that should be. Opening the screen from
// nothing has no stale table to keep, so a spinner is honest about the wait;
// a blank panel with no explanation is what it would be without one.
function sourcingOnOpen(){ sourcingLoad(); }

/* Load the screen. `quiet` refreshes it WITHOUT blanking it.
 *
 *     "keep everything on screen. The expanded row stays open, the table stays
 *      visible."
 *
 * The blank was this function's own first line: it replaced the table with a
 * spinner, then spent a second fetching sixty-seven decisions before it had
 * anything to draw. Every save went through here, so setting one number on one
 * row emptied the page, lost every open panel and jumped the scroll to the top.
 *
 * Quiet mode leaves the old table up while the new data is fetched, then puts
 * back exactly what was open and where you were. Nothing flickers because
 * nothing is removed until the replacement is ready.
 *
 * The loud version is still right for the FIRST load and for the buttons that
 * change what the list contains -- there, a spinner is honest about the wait.
 */
async function sourcingLoad(quiet){
  const body = document.getElementById("srcbody");
  if(!body) return;
  // What is open, and where we are, so it can be put back.
  const open = quiet
    ? Array.prototype.filter.call(
        document.querySelectorAll('#srcbody tr[id^="srcrow_"]'),
        function(tr){ return tr.style.display === "table-row"; })
        .map(function(tr){ return tr.id; })
    : [];
  const scrollY = quiet ? window.scrollY : 0;

  if(!quiet){
    body.innerHTML = '<div class="cc" style="padding:16px">'
      + '<span class="genspin"></span> Loading…</div>';
  }
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/list"))).json(); }
  catch(e){
    // A quiet refresh that fails leaves what is on screen alone and says so in
    // a toast. Replacing a working table with an error because a background
    // refresh timed out would be worse than the stale table.
    if(quiet){ toast("Could not refresh: " + String(e)); return; }
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
      + 'Could not load: ' + _sesc(String(e)) + '</div>';
    return;
  }
  if(!j || !j.ok){
    if(quiet){ toast((j && j.error) || "Could not refresh"); return; }
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
      + _sesc((j && j.error) || "Could not load") + '</div>';
    return;
  }
  SRC_ROWS = j.rows || [];
  SRC_RULE = j.rule || j.defaults || {};
  SRC_MKT = j.marketplace || SRC_MKT || "";
  SRC_DEFAULT_TARGET = j.default_target || {};
  // Read from the server, never remembered from the last click: whether the app
  // is currently allowed to change prices is not something to guess at.
  try{ SRC_MASTER = !!(await (await fetch(_srcUrl("/sourcing/master"))).json()).enabled; }
  catch(e){ SRC_MASTER = false; }
  sourcingRender(j);
  if(quiet){
    open.forEach(function(id){
      const tr = document.getElementById(id);
      if(tr){
        tr.style.display = "table-row";
        const row = document.getElementById(id + "_r");
        if(row) row.classList.add("rp-sel");
      }
    });
    // After the rows are back, or the page is shorter than it was and the
    // scroll gets clamped to the wrong place.
    window.scrollTo(0, scrollY);
  }
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
  // NOTHING ABOVE THE TOOLBAR ANY MORE.
  //
  //     "one compact alert ... Nothing else between the stat cards and the
  //      table."
  //
  // This drew two full-width banners here, above everything, each naming its
  // SKUs in three columns -- thirteen of them, then six more, then a green
  // paragraph. That is roughly 400 pixels of page before the first price, and
  // it is a TABLE pretending to be a warning: every SKU it listed has a row
  // twelve inches below with a red dot in its state column and, once opened,
  // the reason it cannot be bought from.
  //
  // The counts still appear, in the one alert bar under the toolbar
  // (_alertBar), which is drawn from the same decisions. What is NOT repeated
  // is the list of names.
  //
  // The panel is folded, and only exists at all because the two lists are not
  // quite the same question: "nowhere left to buy from" is a fact, and "could
  // not be read" is an absence of one, and the second is the list you would
  // want to see before pressing Check now. Open it and it is exactly what it
  // always was.
  if(!bad.length && !dunno.length){ host.innerHTML = ''; return; }
  let h = '<details class="foldgroup" style="margin:0 0 10px"><summary>'
    + '<i class="ti ti-list-search"></i> Which SKUs '
    + (bad.length ? bad.length + ' cannot be bought from' : '')
    + (bad.length && dunno.length ? ', ' : '')
    + (dunno.length ? dunno.length + ' could not be read' : '')
    + '</summary>';
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
  host.innerHTML = h + '</details>';
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
    sourcingLoad(true);
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
    + 'color:#fff;border-color:var(--accent)">Save</button></div></div>';
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
  wrap.querySelector("#srcmodal_ok").onclick = async function(){
    const ok = await onOk();
    if(ok !== false) close(false);   // a refusal keeps the boxes and their values
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
    if(!j.ok){ toast(j.error||"Could not enroll"); return; }
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

/* ======================================================================
 * THE TABLE.
 *
 * Built from repricer_dashboard_reference.html. What changed and why:
 *
 * It was sixty-seven bordered <div> cards stacked down the page, each one
 * repeating its own labels -- "cheapest source", "selling price", "profit /
 * unit" -- against a single figure. Sixty-seven copies of six labels is four
 * hundred words of furniture, and the one thing a list of prices is for, which
 * is running your eye down a column and seeing which number is out of line,
 * was impossible: nothing lined up with anything.
 *
 * A table says each label ONCE, in a header, and puts the numbers underneath
 * each other. That is the whole reason the reference is a table.
 *
 * Every figure that was on a card is still here. The ones you scan (cost,
 * postage, price, profit, ROI, trend, state) are columns; the ones you read
 * when a row looks wrong (the sum, the suppliers, the rules, the reason) are
 * in the panel that opens underneath it.
 * ====================================================================== */

/* A price history as a line, not bars.
 *
 *     "7d trend = SVG LINE GRAPH sparkline, NOT bar ticks"
 *
 * A supplier's cost is a continuous thing that moves; bars imply separate
 * measurements of separate quantities. The line also makes the shape of a
 * change legible at 70x24 pixels, which is the entire point of drawing it that
 * small.
 *
 * `hist` is [{at, landed, status, in_stock}] NEWEST FIRST -- that is what
 * source_drift.price_history returns, because source_repo.history reads
 * ORDER BY id DESC. It is REVERSED here, and it has to be: a line drawn
 * straight from that order runs backwards in time, so a supplier who has put
 * their price up appears to have dropped it. Measured on jack_uk, every trend
 * on the screen was mirrored.
 *
 * Readings that could not be read are skipped rather than drawn as zero -- a
 * failed fetch is not a free supplier, and a line diving to the floor says
 * exactly that.
 */
function _spark(hist, opts){
  const o = opts || {};
  const W = o.w || 70, H = o.h || 24, PAD = 3;
  // OLDEST FIRST, so left-to-right is earlier-to-later. See the note above.
  const all = (hist || []).slice().reverse().filter(function(p){
    return p && p.landed != null && isFinite(p.landed);
  });
  // ONE READING IS NOT A HISTORY. A single point drawn in a trend column reads
  // as a flat line, which is a claim about how the price has BEHAVED made from
  // one measurement. Nothing is better than that.
  if(all.length < 2) return '';
  // Newest last, and at most the last 12 readings -- older than that is a
  // different question, answered by the full chart this opens into.
  const pts = all.slice(-12);
  const vals = pts.map(function(p){ return +p.landed; });
  const lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  const span = (hi - lo) || 1;
  // A FLAT LINE IS DRAWN FLAT, down the middle. Scaling a run of identical
  // readings to fill the box turns rounding noise into a mountain range.
  const flat = (hi - lo) < 0.005;
  const x = function(i){
    return pts.length < 2 ? W / 2
         : PAD + i * (W - PAD * 2) / (pts.length - 1);
  };
  const y = function(v){
    return flat ? H / 2
         : (H - PAD) - ((v - lo) / span) * (H - PAD * 2);
  };
  // Which way it has gone decides the colour: cheaper is good for us.
  const first = vals[0], last = vals[vals.length - 1];
  const move = first ? ((last - first) / first) * 100 : 0;
  const col = o.color || (move < -1 ? 'var(--ok)'
                        : move > 1  ? 'var(--gold)'
                        : 'var(--ink3)');
  const poly = pts.map(function(p, i){
    return x(i).toFixed(1) + ',' + y(+p.landed).toFixed(1);
  }).join(' ');
  const lastP = pts[pts.length - 1];
  // The supplier has ENDED: the run to the last point is dashed and red, so a
  // dead source is visible without reading the row.
  const dead = String((lastP || {}).status || '') === 'gone';
  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true">'
    + '<polyline fill="none" stroke="' + col + '" stroke-width="1.5" '
    + 'stroke-linecap="round" stroke-linejoin="round" points="' + poly + '"/>'
    + '<circle cx="' + x(pts.length - 1).toFixed(1) + '" cy="'
    + y(+lastP.landed).toFixed(1) + '" r="2" fill="'
    + (dead ? 'var(--red)' : col) + '"/></svg>';
  if(o.bare) return '<div class="rp-supspk">' + svg + '</div>';
  const tip = _smoney(last)
    + (flat ? ' &middot; steady'
            : ' &middot; ' + (move < 0 ? '&darr;' : '&uarr;')
              + Math.abs(move).toFixed(0) + '% over ' + pts.length + ' readings');
  // `this` is passed so the chart can open BESIDE the sparkline rather than in
  // the middle of the page -- the row it belongs to is the context, and a
  // centred modal takes that away exactly when you are comparing this SKU's
  // line with the ones above and below it.
  return '<div class="rp-spk" title="Click for the full history" '
    + 'onclick="event.stopPropagation();srcChart(' + _sarg(o.title || '')
    + ',' + _sarg(JSON.stringify(pts)) + ',this)">' + svg
    + '<div class="rp-stip">' + tip + '</div></div>';
}

/* "08:12" out of a stored "2026-08-17 08:12:46", or "" if there is no time.
 * Read straight off the string rather than through Date: the value is already
 * local time as the app recorded it, and parsing it into a Date would shift it
 * by the browser's offset. */
function _srcClock(iso){
  const m = /[ T](\d{2}):(\d{2})/.exec(String(iso || ''));
  return m ? (m[1] + ':' + m[2]) : '';
}

/* THE SPARKLINE, OPENED UP -- a real chart, not a bar log.
 *
 *     "show a proper line chart like Orbit's -- smooth curves with area fill,
 *      not flat bars. This replaces the current flat grey bar log entirely."
 *
 * WHY A CURVE AND NOT A POLYLINE. A supplier's cost is a continuous thing, and
 * the readings are samples of it four hours apart. Straight segments say "it
 * jumped here", which is a claim about a moment nobody measured; a curve says
 * "it moved between these two points", which is all that is actually known.
 *
 * MONOTONE cubic, specifically -- Fritsch-Carlson tangents -- not a plain
 * Catmull-Rom. An ordinary spline OVERSHOOTS: three readings of 10, 10, 12
 * would be drawn dipping below 10 before the rise, and a chart that shows a
 * price the supplier never charged is worse than one drawn with rulers.
 * Monotone interpolation cannot overshoot by construction.
 *
 * NEAR THE SPARKLINE, not centre-screen: the row it belongs to is the context,
 * and a modal in the middle of the page takes that away at the moment you are
 * comparing this SKU's line with the ones above and below it.
 */
function srcChart(title, json, anchor){
  let pts = [];
  try { pts = JSON.parse(json) || []; } catch(e){ pts = []; }
  // Oldest first -- _spark has already reversed the server's newest-first
  // order, and a chart read left to right must run forwards in time.
  //
  // A READING THAT COULD NOT BE READ IS NOT A PRICE OF ZERO, so the curve is
  // drawn only through the ones that have an amount. But it is not silently
  // dropped either: a run of failures is exactly why a price can look
  // unchanged for a week, and a chart that hides them turns "we could not see"
  // into "it did not move". They are counted under the header and marked on
  // the axis where they happened.
  const usable = pts.filter(function(p){
    return p && p.landed != null && isFinite(p.landed);
  });
  const unread = pts.length - usable.length;
  if(usable.length < 2) return;

  const W = 360, H = 180;
  // A little more room at the bottom than the spec's 26: the axis can carry a
  // second line naming the DATE when the labels above it are clock times.
  const PAD = {t: 14, r: 12, b: 34, l: 52};
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const vals = usable.map(function(p){ return +p.landed; });
  const lo0 = Math.min.apply(null, vals), hi0 = Math.max.apply(null, vals);
  // A FLAT LINE MUST LOOK FLAT. With lo === hi the scale is degenerate, so a
  // band is invented around the value -- and the line sits in the middle of it
  // rather than filling the box and turning rounding noise into a mountain.
  const flat = (hi0 - lo0) < 0.005;
  const pad = flat ? Math.max(0.5, lo0 * 0.05) : (hi0 - lo0) * 0.18;
  const lo = lo0 - pad, hi = hi0 + pad;
  const span = (hi - lo) || 1;

  const X = function(i){ return PAD.l + (i * iw / (usable.length - 1)); };
  const Y = function(v){ return PAD.t + ih - ((v - lo) / span) * ih; };

  // Which way it has gone decides the colour: cheaper is good for us.
  const first = vals[0], last = vals[vals.length - 1];
  const move = first ? ((last - first) / first) * 100 : 0;
  const col = flat || Math.abs(move) < 1 ? '#22c55e'
            : (move < 0 ? '#22c55e' : '#f0b429');
  const gid = 'rpg_' + Math.random().toString(36).slice(2, 8);

  // ---- monotone cubic tangents (Fritsch-Carlson) ----------------------
  const n = usable.length;
  const xs = [], ys = [];
  for(let i = 0; i < n; i++){ xs.push(X(i)); ys.push(Y(vals[i])); }
  const dx = [], dy = [], slope = [];
  for(let i = 0; i < n - 1; i++){
    dx.push(xs[i + 1] - xs[i]);
    dy.push(ys[i + 1] - ys[i]);
    slope.push(dy[i] / (dx[i] || 1));
  }
  const m = [slope[0]];
  for(let i = 1; i < n - 1; i++){
    // A LOCAL EXTREME GETS A FLAT TANGENT. This is the line that makes
    // overshoot impossible: where the data turns, the curve turns with it
    // instead of carrying on past the point and coming back.
    if(slope[i - 1] * slope[i] <= 0){ m.push(0); }
    else {
      const w1 = 2 * dx[i] + dx[i - 1], w2 = dx[i] + 2 * dx[i - 1];
      m.push((w1 + w2) / (w1 / slope[i - 1] + w2 / slope[i]));
    }
  }
  m.push(slope[n - 2]);

  let d = 'M' + xs[0].toFixed(1) + ',' + ys[0].toFixed(1);
  for(let i = 0; i < n - 1; i++){
    const c1x = xs[i] + dx[i] / 3, c1y = ys[i] + m[i] * dx[i] / 3;
    const c2x = xs[i + 1] - dx[i] / 3, c2y = ys[i + 1] - m[i + 1] * dx[i] / 3;
    d += 'C' + c1x.toFixed(1) + ',' + c1y.toFixed(1)
       + ' ' + c2x.toFixed(1) + ',' + c2y.toFixed(1)
       + ' ' + xs[i + 1].toFixed(1) + ',' + ys[i + 1].toFixed(1);
  }
  const area = d + 'L' + xs[n - 1].toFixed(1) + ',' + (PAD.t + ih)
             + 'L' + xs[0].toFixed(1) + ',' + (PAD.t + ih) + 'Z';

  // ---- the axes --------------------------------------------------------
  // THREE GRID LINES, at amounts that are actually in range. A grid drawn at
  // round numbers outside the data would imply the price had been there.
  let grid = '', yl = '';
  for(let k = 0; k <= 2; k++){
    const v = lo0 + (hi0 - lo0) * (k / 2);
    const y = Y(v).toFixed(1);
    grid += '<line x1="' + PAD.l + '" y1="' + y + '" x2="' + (W - PAD.r)
         +  '" y2="' + y + '" stroke="rgba(255,255,255,.06)" stroke-width="1"/>';
    yl += '<text x="' + (PAD.l - 6) + '" y="' + (+y + 3.5)
       +  '" text-anchor="end" class="rp-ax">' + _sesc(_smoney(v)) + '</text>';
  }
  // At most four labels, or they collide.
  //
  // THE DAY, OR THE TIME OF DAY. Suppliers are read every four hours, so a
  // short run of readings is often all on one or two dates -- and "Mon 17 Aug"
  // three times over is a label that distinguishes nothing. When the whole
  // series spans two days or fewer the axis switches to clock times, which is
  // what actually separates those points.
  const days = {};
  usable.forEach(function(p){ days[String(p.at || '').slice(0, 10)] = 1; });
  const sameDay = Object.keys(days).length <= 2;
  let xl = '';
  const step = Math.max(1, Math.round((n - 1) / 3));
  for(let i = 0; i < n; i += step){
    const lab = sameDay ? _srcClock(usable[i].at)
                        : (_srcDay(usable[i].at) || '');
    xl += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 17)
       +  '" text-anchor="middle" class="rp-ax">' + _sesc(lab) + '</text>';
  }
  // ...and then the DATE is said once, under the axis, so "14:20" is not a
  // time on an unknown day.
  if(sameDay){
    const d0 = _srcDay(usable[0].at) || '';
    const d1 = _srcDay(usable[n - 1].at) || '';
    xl += '<text x="' + (PAD.l + iw / 2) + '" y="' + (H - 5)
       +  '" text-anchor="middle" class="rp-ax">'
       +  _sesc(d0 === d1 ? d0 : d0 + ' – ' + d1) + '</text>';
  }

  // ---- the dots, hidden until hovered ---------------------------------
  let dots = '';
  for(let i = 0; i < n; i++){
    const dead = String(usable[i].status || '') === 'gone';
    dots += '<g class="rp-pt" data-i="' + i + '">'
         +  '<circle cx="' + xs[i].toFixed(1) + '" cy="' + ys[i].toFixed(1)
         +  '" r="4" fill="' + (dead ? '#ef4444' : col) + '"/>'
         +  '<circle cx="' + xs[i].toFixed(1) + '" cy="' + ys[i].toFixed(1)
         +  '" r="2" fill="#fff"/></g>';
  }

  const svg =
      '<svg class="rp-chart" viewBox="0 0 ' + W + ' ' + H + '" width="' + W
    + '" height="' + H + '">'
    + '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0" stop-color="' + col + '" stop-opacity=".20"/>'
    + '<stop offset="1" stop-color="' + col + '" stop-opacity="0"/>'
    + '</linearGradient></defs>'
    + grid
    + '<path d="' + area + '" fill="url(#' + gid + ')"/>'
    + '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="2" '
    + 'stroke-linecap="round" stroke-linejoin="round"/>'
    + '<line class="rp-cross" x1="0" y1="' + PAD.t + '" x2="0" y2="'
    + (PAD.t + ih) + '" stroke="rgba(255,255,255,.22)" stroke-width="1" '
    + 'style="display:none"/>'
    + dots + yl + xl
    + '<rect class="rp-hit" x="' + PAD.l + '" y="' + PAD.t + '" width="' + iw
    + '" height="' + ih + '" fill="transparent"/>'
    + '</svg>';

  const arrow = flat || Math.abs(move) < 1 ? '&middot; steady'
              : (move < 0 ? '&darr; ' : '&uarr; ')
                + (move > 0 ? '+' : '') + move.toFixed(1) + '%';

  let ov = document.getElementById('rp_ov');
  if(!ov){
    ov = document.createElement('div');
    ov.id = 'rp_ov';
    ov.className = 'rp-ov';
    document.body.appendChild(ov);
  }
  ov.innerHTML =
      '<div class="rp-box">'
    + '<button class="rp-x" aria-label="Close">&times;</button>'
    + '<h4>' + _sesc(title || 'Supplier cost') + '</h4>'
    + '<div class="rp-sub">'
    + '<b>' + _smoney(first) + '</b> &rarr; <b>' + _smoney(last) + '</b> '
    + '<span style="color:' + col + '">' + arrow + '</span>'
    + '<span class="cc"> &middot; last ' + n + ' checks</span>'
    // SAID, NOT HIDDEN. Without this line a week of failed reads and a week of
    // a genuinely steady price are the same picture.
    + (unread
        ? '<span class="rp-unread" title="Those readings have no amount, so '
          + 'the line cannot pass through them. A run of them is why a price '
          + 'can look unchanged for days."> &middot; ' + unread
          + ' could not be read</span>'
        : '')
    + '</div>'
    + svg
    + '<div class="rp-tip" style="display:none"></div>'
    + '</div>';

  // ---- position it near the sparkline ---------------------------------
  const box = ov.querySelector('.rp-box');
  ov.classList.add('rp-show');
  if(anchor && anchor.getBoundingClientRect){
    const r = anchor.getBoundingClientRect();
    const bw = box.offsetWidth, bh = box.offsetHeight;
    let left = r.left + window.scrollX - bw / 2 + r.width / 2;
    let top = r.bottom + window.scrollY + 8;
    // Flipped above when there is no room below, and pulled inside the window
    // on both axes -- a popup half off the screen is a popup you cannot read.
    if(r.bottom + bh + 16 > window.innerHeight)
      top = r.top + window.scrollY - bh - 8;
    left = Math.max(8, Math.min(left, window.innerWidth - bw - 8));
    top = Math.max(8, top);
    box.style.left = left + 'px';
    box.style.top = top + 'px';
  } else {
    box.style.left = Math.round(window.innerWidth / 2 - 190) + 'px';
    box.style.top = (window.scrollY + 90) + 'px';
  }

  // ---- hover: crosshair, dot, tooltip ---------------------------------
  const svgEl = box.querySelector('svg');
  const cross = box.querySelector('.rp-cross');
  const tip = box.querySelector('.rp-tip');
  const hit = box.querySelector('.rp-hit');
  const show = function(ev){
    // SNAPPED TO THE NEAREST READING, never interpolated. A tooltip reading
    // "£10.43" for a moment between two checks would be a price nobody was
    // ever charged.
    const r = svgEl.getBoundingClientRect();
    const px = (ev.clientX - r.left) * (W / r.width);
    let best = 0, bd = 1e9;
    for(let i = 0; i < n; i++){
      const dd = Math.abs(xs[i] - px);
      if(dd < bd){ bd = dd; best = i; }
    }
    cross.setAttribute('x1', xs[best]);
    cross.setAttribute('x2', xs[best]);
    cross.style.display = '';
    box.querySelectorAll('.rp-pt').forEach(function(g){
      g.classList.toggle('rp-on', +g.dataset.i === best);
    });
    const p = usable[best];
    tip.innerHTML = '<b>' + _smoney(p.landed) + '</b><br>'
      + _sesc((_srcDay(p.at) || '') + ' ' + _srcClock(p.at)).trim()
      + (String(p.status || '') === 'gone'
          ? '<br><span style="color:#ef4444">supplier ended</span>'
          : (p.in_stock === false
              ? '<br><span style="color:#ef4444">out of stock</span>' : ''));
    tip.style.display = 'block';
    const tx = (xs[best] / W) * r.width + (r.left - box.getBoundingClientRect().left);
    tip.style.left = Math.round(tx) + 'px';
    tip.style.top = Math.round((ys[best] / H) * r.height
                    + (r.top - box.getBoundingClientRect().top) - 12) + 'px';
  };
  hit.addEventListener('mousemove', show);
  hit.addEventListener('mouseleave', function(){
    cross.style.display = 'none';
    tip.style.display = 'none';
    box.querySelectorAll('.rp-pt').forEach(function(g){
      g.classList.remove('rp-on');
    });
  });

  const close = function(){
    ov.classList.remove('rp-show');
    document.removeEventListener('keydown', onKey, true);
  };
  const onKey = function(e){ if(e.key === 'Escape'){ e.preventDefault(); close(); } };
  document.addEventListener('keydown', onKey, true);
  box.querySelector('.rp-x').onclick = close;
  ov.onclick = function(e){ if(e.target === ov) close(); };
}

/* WHERE THE SELLING PRICE GOES, as one bar.
 *
 * The sum is already written out line by line in the panel below this. The bar
 * is for the question the list answers badly: what SHARE of the price is left
 * after everyone has been paid. A profit of 5.51 means nothing until you can
 * see it is a fifth of the bar and the supplier is two thirds of it.
 *
 * Segments are flexed by their own amounts, so widths are true to the money.
 */
function _stackBar(b){
  if(!b || b.price == null) return '';
  const cost = +(b.cost || 0);
  const fees = (b.fees && b.fees.lines) || null;
  let ref = +(b.fee || 0), close = 0;
  if(fees){
    // Prefer Amazon's own split when it has been quoted, so the bar and the
    // "All Amazon fees" panel above cannot show different shares.
    const f = function(k){
      const l = fees.filter(function(x){ return x.key === k; })[0];
      return l ? +(l.amount || 0) : 0;
    };
    ref = f('referral'); close = f('closing');
  }
  const other = +(b.postage_label || 0) + +(b.ads || 0);
  const profit = +(b.profit || 0);
  const tot = cost + ref + close + other + Math.max(0, profit);
  if(!(tot > 0)) return '';
  let h = '<div class="rp-sbar">'
    + '<div class="rp-sb-cost" style="flex:' + cost + '" title="What one unit '
    + 'costs you delivered from the supplier">' + _smoney(cost) + '</div>'
    + '<div class="rp-sb-ref" style="flex:' + ref + '" title="Amazon\'s '
    + 'referral fee on this price">' + _smoney(ref) + '</div>';
  if(close > 0)
    h += '<div class="rp-sb-close" title="Amazon\'s variable closing fee">'
      +  _smoney(close) + '</div>';
  if(other > 0)
    h += '<div style="flex:' + other + ';background:var(--line2);'
      +  'color:var(--ink2)" title="Your postage label and the amount set aside '
      +  'for ads">' + _smoney(other) + '</div>';
  h += (profit > 0
        ? '<div class="rp-sb-profit" style="flex:' + profit + '" title="What '
          + 'you keep per unit">' + _smoney(profit) + '</div>'
        : '<div class="rp-sb-loss" style="flex:' + Math.max(1, cost * 0.25)
          + '" title="This price does not cover what the unit costs">'
          + _smoney(profit) + '</div>');
  h += '</div><div class="rp-sbleg">'
    + '<span><span class="rp-sq" style="background:#5b8fb9"></span>Supplier</span>'
    + '<span><span class="rp-sq" style="background:#e25c5c"></span>Referral</span>'
    + (close > 0
        ? '<span><span class="rp-sq" style="background:#d4846f"></span>Closing</span>'
        : '')
    + (other > 0
        ? '<span><span class="rp-sq" style="background:var(--line2)"></span>'
          + 'Postage &amp; ads</span>'
        : '')
    + '<span><span class="rp-sq" style="background:#4ebb82"></span>'
    + (profit > 0 ? 'Profit' : 'Shortfall') + '</span>'
    + '</div>';
  return h;
}

/* The figures that decide whether a SKU is worth keeping.
 *
 * AT THE PRICE THE BAR ABOVE IT SHOWS, not at today's. The strip sits directly
 * under the stacked bar, which is a picture of the PROPOSED price broken into
 * its parts -- so reading today's ROI there put two different questions side by
 * side with nothing to tell them apart. Measured on a real jack_uk SKU: the bar
 * showed 10.06 + 2.56 + 2.02 = 14.64 and the cards read "69% ROI", which is the
 * return at the 19.97 it sells for now. Both true, neither wrong, and together
 * unreadable.
 *
 * Today's figures are the ROW's job -- the Profit and ROI columns, which is
 * where you scan for a SKU that is currently underwater. This is the panel, and
 * the panel is about the decision.
 *
 * It falls back to the glance only when there is no decision to describe, so a
 * blocked SKU still shows what it is earning rather than four dashes.
 */
function _metStrip(r){
  const g = r.glance || {}, d = r.decision || {}, b = d.breakdown || {};
  const priced = (b.price != null && b.profit != null);
  const roi = priced ? (b.cost ? (b.profit / b.cost) * 100 : null)
            : (g.roi_pct != null ? g.roi_pct : null);
  const mgn = priced ? (b.price ? (b.profit / b.price) * 100 : null)
            : (g.margin_pct != null ? g.margin_pct : null);
  const tgt = ((r.rule || {}).target_roi_pct != null)
            ? +r.rule.target_roi_pct : null;
  // Green only when it CLEARS the target you set. Amber when it is short --
  // the number itself is the same either way, and the colour is the only thing
  // that says whether it is the number you asked for.
  const roiTone = (roi == null) ? 'rp-m2b'
                : (tgt != null && roi < tgt) ? 'rp-m2y' : 'rp-m2g';
  const cell = function(cls, val, label, why){
    return '<div class="rp-m2 ' + cls + '" title="' + _sesc(why || '') + '">'
      + '<div class="rp-n">' + val + '</div>'
      + '<div class="rp-l">' + label + '</div></div>';
  };
  const lead = (d.lead_days != null) ? d.lead_days
             : ((r.current || {}).lead_days);
  const pol = (b.shipping_policy_days != null) ? b.shipping_policy_days : 2;
  // NO HEADING ABOVE THE TILES. The bar sits directly above them and is drawn
  // from the same three numbers, so the strip belongs to it visually; a line of
  // uppercase text between the two broke that and cost a row of height on every
  // open panel. WHICH price they are about is on each tile's own tooltip.
  const at = priced ? _smoney(b.price) : ((r.current || {}).price != null
                                          ? _smoney(r.current.price) : null);
  const when = (priced ? 'At the price the repricer would set'
                       : 'At the price it sells for now')
             + (at ? ' (' + at + '). ' : '. ');
  // Green for the money, blue for the days -- the mockup's two tile colours.
  // The ROI tile is NOT recoloured when it misses your target: the table's own
  // ROI column already goes amber for that, and the miss has a notice of its
  // own with the price that would clear it. Three greens and a blue is the
  // pattern being matched; a tile that changes colour breaks the set.
  let h = '<div class="rp-met2">'
    + cell('rp-m2g', priced ? _smoney(b.profit)
           : (g.profit != null ? _smoney(g.profit) : '&mdash;'), 'Profit / unit',
           when + 'What is left per unit after what the stock cost and '
           + 'Amazon\'s fee'
           + (priced ? ' of ' + _smoney(b.fee)
              : (g.fee == null ? '' : ' of ' + _smoney(g.fee))))
    + cell('rp-m2g', roi == null ? '&mdash;' : roi.toFixed(0) + '%', 'ROI',
           when + 'What you keep, as a share of the cash you put in'
           + (tgt != null ? '. You asked for ' + tgt + '%.' : '.'))
    + cell('rp-m2g', mgn == null ? '&mdash;' : mgn.toFixed(0) + '%', 'Margin',
           when + 'What you keep, as a share of what the buyer paid.')
    + cell('rp-m2b', lead == null ? '&mdash;' : lead + 'd', 'Handling',
           'Days Amazon is told to allow before this posts. The '
           + pol + ' days the postage takes are counted by Amazon separately, '
           + 'so they are not in this number.')
    + '</div>';

  // THE SAME FIGURES AGAIN, WITH THE COUPON ON.
  //
  //     "show profit per unit when no promotion like coupon or discounts etc
  //      are applied and also show the profit when some coupons or promotions
  //      etc are applied ... also show roi and margin in both cases"
  //
  // ONLY when a discount was actually MEASURED off settled orders. A second
  // identical strip on every row would be four more numbers to read past on the
  // SKUs that have no coupon, and worse, it would imply the app had checked and
  // found none -- it cannot check. Amazon does not expose a seller's running
  // coupons to this app; see domain/promotions.py.
  const p = g.promo;
  if(p){
    const why = 'After the discount this SKU has actually been selling under: '
              + _smoney(p.amount_per_unit) + ' a unit'
              + (p.pct == null ? '' : ' (about ' + p.pct.toFixed(0) + '% off)')
              + '. ' + (g.promo_note || '');
    h += '<div class="cc" style="font-size:10px;text-transform:uppercase;'
      +  'letter-spacing:.05em;margin:2px 0 4px">With the coupon on</div>'
      +  '<div class="rp-met2">'
      +  cell('rp-m2y', _smoney(g.sell_price_promo), 'After coupon', why)
      +  cell('rp-m2y', _smoney(g.profit_promo), 'Profit / unit', why)
      +  cell('rp-m2y', g.roi_pct_promo == null ? '&mdash;'
              : g.roi_pct_promo.toFixed(0) + '%', 'ROI', why)
      +  cell('rp-m2y', g.margin_pct_promo == null ? '&mdash;'
              : g.margin_pct_promo.toFixed(0) + '%', 'Margin', why)
      +  '</div>';
  }
  return h;
}

/* Suppliers as rows, so several can be compared rather than read one by one.
 *
 * The keys are domain/order_sources.options_for's -- source_id, state, profit
 * -- which is the SAME payload the order screen's supplier list draws from.
 * The ranking, the landed cost and the "you keep" figure are all worked out
 * there, once, for both screens (CLAUDE.md Rule 12).
 *
 * The seven-day cost line comes from r.sources, which is where the readings
 * are, matched on source_id.
 */
function _supTable(r){
  const opts = r.options || [];
  if(!opts.length)
    return '<div class="cc" style="font-size:11px;padding:4px 0">'
      + 'No supplier link on this SKU yet, so there is nothing to price from.'
      + '</div>';
  const used = (r.decision || {}).source_id;
  // source_id -> its readings, for the sparkline.
  const hist = {};
  (r.sources || []).forEach(function(s){ hist[s.id] = s.history || []; });
  // Why each one was passed over, in the words decide() used.
  const why = {};
  ((r.decision || {}).rejections || []).forEach(function(x){
    why[x.source_id] = x.reason;
  });
  let rows = '';
  opts.forEach(function(s){
    const dead = (s.state === 'dead');
    const unknown = (s.state === 'unknown');
    const isUsed = (used != null && s.source_id === used);
    const tag = isUsed
        ? '<span class="rp-tag rp-tgu">USING</span>'
        : String(s.status || '') === 'gone'
        ? '<span class="rp-tag rp-tgo">ENDED</span>'
        : dead ? '<span class="rp-tag rp-tgo">OOS</span>'
        : unknown ? '<span class="rp-d" style="font-size:8px">?</span>'
        : '<span class="rp-d" style="font-size:9px">&mdash;</span>';
    rows += '<tr' + (dead ? ' class="rp-oos"' : '') + '>'
      + '<td>' + tag + '</td>'
      + '<td><a class="rp-snm" href="' + _sesc(s.url || '#') + '" target="_blank" '
      + 'rel="noopener" onclick="event.stopPropagation()" title="'
      + _sesc(why[s.source_id] || s.url || '') + '">'
      + _sesc(s.label || _srcShort(s.url) || '') + '</a>'
      // Two numbers, apart: "show item cost and shipping separately". A landed
      // figure hides which half moved, and a supplier who holds their price and
      // doubles their postage looks identical to one who put the item up.
      + '</td>'
      + '<td style="font-weight:600">'
      + (s.price != null ? _smoney(s.price) : '&mdash;') + '</td>'
      + '<td class="rp-d">'
      + (s.shipping == null ? '?' : (s.shipping > 0 ? _smoney(s.shipping) : 'free'))
      + '</td>'
      + '<td style="font-weight:600">'
      + (s.landed != null ? _smoney(s.landed) : '&mdash;') + '</td>'
      + '<td' + (s.available_qty === 0 ? ' style="color:var(--red)"' : '') + '>'
      + (s.available_qty != null ? s.available_qty : '&mdash;') + '</td>'
      + '<td>' + (s.dispatch_days != null ? s.dispatch_days + 'd' : '&mdash;') + '</td>'
      + '<td>' + _spark(hist[s.source_id], {bare: true, w: 50, h: 16}) + '</td>'
      + '<td style="font-weight:600;color:'
      + (dead || s.profit == null ? 'var(--ink3)' : 'var(--ok)') + '">'
      + (!dead && s.profit != null ? _smoney(s.profit) : '&mdash;') + '</td>'
      // Its OWN class, not the rules pills'. It sits above them in the panel
      // and it DELETES a supplier and its price history, where every .rp-rl
      // opens an editor -- sharing a class made "the first pill in the panel"
      // mean the × button, which is how a probe for the Floor editor ended up
      // opening a delete confirmation instead.
      + '<td style="width:18px"><button class="rp-xrm" '
      + 'onclick="event.stopPropagation();sourcingRemoveSource(' + s.source_id
      + ')" title="Remove this supplier link">&times;</button></td>'
      + '</tr>';
    // WHEN EBAY SAYS IT WILL ARRIVE, and why it was passed over -- both under
    // the row they belong to rather than in a column. A date is a sentence, not
    // a figure, and putting it in a cell would either truncate it or make every
    // other column narrower to fit it.
    const line = _srcDeliveryLine({carrier: s.carrier, postage_text: s.postage_text,
                                   delivery_text: s.delivery_text,
                                   delivery_postcode: s.delivery_postcode});
    const rej = why[s.source_id];
    if(line || rej){
      rows += '<tr><td></td><td colspan="9" style="padding:0 3px 4px 3px;'
        + 'border-bottom:1px solid var(--line)">'
        + (rej ? '<span style="font-size:10px;color:var(--gold)">'
                 + _sesc(rej) + '</span> ' : '')
        + (line || '') + '</td></tr>';
    }
  });
  return '<table class="rp-sup"><thead><tr>'
    + '<th></th><th>Supplier</th>'
    + '<th title="What the supplier charges for the item">Item</th>'
    + '<th title="Their postage to you">Post</th>'
    + '<th title="Item plus postage -- what one unit really costs you">Landed</th>'
    + '<th title="How many they say they have">Stock</th>'
    + '<th title="Days they say they take to dispatch">Disp</th>'
    + '<th title="What this supplier has been charging">Trend</th>'
    + '<th title="What is left of the selling price after Amazon and this '
    + 'supplier">You keep</th><th></th>'
    + '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/* The rules, as pills that open the box that changes them.
 *
 * They were a column of labelled inputs, which is a form -- something you fill
 * in. These are settings that are already set, and mostly correct; what you
 * want is to SEE them at a glance and change the one that is wrong. A pill
 * shows the current value and is the button that edits it.
 */
function _rulePills(r){
  const rule = r.rule || {}, d = r.decision || {}, b = d.breakdown || {};
  const sku = r.sku;
  // `this` IS PASSED TO EVERY HANDLER, and it has to be.
  //
  // The editors these open are INLINE -- a small panel anchored under the
  // control that opened it, so the row it is about stays visible behind. With
  // no button to measure, uiInline has nowhere to put itself and returns
  // without drawing anything: the pill would look dead. Measured in a browser
  // before this was added, clicking Floor did nothing at all.
  const pill = function(k, v, fn, why, cls){
    return '<button class="rp-rl" title="' + _sesc(why) + '" '
      + 'onclick="event.stopPropagation();' + fn + '">'
      + '<span class="rp-k">' + k + '</span>'
      + '<span class="rp-v ' + (cls || '') + '">' + v + '</span></button>';
  };
  const S = _sarg(sku);
  let h = '<div class="rp-rules">';
  h += pill('Floor', rule.min_price != null ? _smoney(rule.min_price) : 'not set',
            'sourcingMinPrice(' + S + ',this)',
            'The price this SKU will never sell below. It is the one guard that '
            + 'still works if a supplier page is misread, and a SKU cannot be '
            + 'armed without it.',
            rule.min_price == null ? 'rp-off' : '');
  h += pill('ROI', rule.target_roi_pct != null ? rule.target_roi_pct + '%' : 'none',
            'sourcingTarget(' + S + ')',
            'The return you want on the cash you put in. The price is set to '
            + 'the least that meets it.',
            rule.target_roi_pct != null ? 'rp-g' : 'rp-off');
  h += pill('Margin',
            rule.target_margin_pct != null ? rule.target_margin_pct + '%' : 'none',
            'sourcingTarget(' + S + ')',
            'The share of the selling price you want to keep.',
            rule.target_margin_pct != null ? 'rp-g' : 'rp-off');
  // "tell me above this", NOT "hold above this" -- the change goes through and
  // the notification is what a big move produces.
  h += pill('Tell me over',
            (rule.max_change_pct != null ? rule.max_change_pct : 25) + '%',
            'sourcingTarget(' + S + ')',
            'A price move bigger than this still happens -- it just sends you a '
            + 'notification as well.');
  // WHICH WAY THIS SKU MAY MOVE. First among the pills after the floor,
  // because it decides whether any of the others can ever LOWER a price.
  const DIRW = {up_only: ['&uarr; up only', 'rp-g'],
                up_and_down: ['&udarr; both ways', ''],
                match_floor: ['= the floor', 'rp-y']};
  const dcur = String(rule.direction || 'up_only');
  h += pill('Direction', (DIRW[dcur] || DIRW.up_only)[0],
            'sourcingDirection(' + S + ',this)',
            {up_only: 'The price can only ever go UP. A floor below what it '
                      + 'sells for today is not acted on, so a cheaper '
                      + 'supplier becomes margin rather than a discount.',
             up_and_down: 'The price follows the supplier both ways -- a '
                      + 'cheaper supplier means a cheaper price.',
             match_floor: 'The price sits exactly on the calculated floor, '
                      + 'always. This also ignores any held price, because a '
                      + 'hold is a floor ABOVE the computed one.'}[dcur]
            || '',
            (DIRW[dcur] || DIRW.up_only)[1]);
  h += pill('Extra handling',
            '+' + (rule.handling_buffer_days || 0) + 'd',
            'sourcingBuffer(' + S + ',this)',
            'Added on top of the calculated handling time. Use it for a '
            + 'supplier that does not dispatch when it says it will.',
            (rule.handling_buffer_days ? '' : 'rp-off'));
  // WHOSE FEE FIGURE THIS IS, and it has to be legible without hovering.
  //
  // A rate is just a number until you know whether Amazon quoted it for THIS
  // product or it is an average of your own settled orders. The panel used to
  // print "15%" for both. Two decimals, because 17.5% and 15.4% were rounding
  // to the same whole number, and a word after it saying which kind it is.
  const fr = (b.fee_rate != null) ? (b.fee_rate * 100).toFixed(2)
             .replace(/\.00$/, '').replace(/(\.\d)0$/, '$1') + '%' : '?';
  const quoted = (d.fee_basis === 'quoted');
  h += pill('Amazon fee',
            fr + ' <span style="font-weight:400;opacity:.7">'
               + (quoted ? 'quoted' : 'measured') + '</span>',
            'sourcingGetFees(' + S + ')',
            (d.fee_detail
              || 'Amazon has not been asked about this product yet.')
            + (quoted
                ? " -- Amazon's own figure for this product."
                : ' -- your measured rate, not Amazon\'s quote. Click to ask '
                  + 'Amazon.'),
            quoted ? 'rp-g' : '');
  h += '</div>';
  return h;
}

/* FOUR counts, each with a bar showing it as a share of everything tracked.
 *
 *     "4 cards max in a row ... Remove the 5th card (Held for review)"
 *
 * There were five, and the fifth was the odd one out in a way the layout was
 * hiding. The other four are STATES a SKU is in -- tracked, armed, about to
 * change, out of stock -- and every SKU is in exactly one of them. "Held for
 * review" is not a state, it is a reason a decision did not happen, and it
 * overlaps the others: a held SKU is also a tracked one.
 *
 * So the held count moved into the alert bar, which is where "something needs
 * you" belongs, and it now says WHY they are held rather than only how many --
 * which is the thing a card could never do.
 *
 * The bar along the bottom is the count as a SHARE. "5 held" means one thing
 * out of 8 and something else out of 80, and a bare number cannot tell you
 * which.
 */
function _statCards(j){
  const c = j.counts || {};
  const rows = SRC_ROWS || [];
  const total = rows.length || 0;
  const armed = rows.filter(function(r){ return r.mode === 'live'; }).length;
  const pct = function(n){ return total ? Math.round(n / total * 100) : 0; };
  // THE CARDS ARE THE FILTER.
  //
  //     "Clicking 'Armed' shows only armed SKUs ... Clicking the active filter
  //      again clears it."
  //
  // A count and a filter are the same thing asked twice. "13 out of stock" is
  // only useful if the next thing you do is look at those thirteen, and on a
  // 67-row table that meant scrolling and reading dots. The number IS the way
  // in now, which is also why no separate row of filter buttons was added:
  // that would be two controls for one idea.
  const card = function(key, n, label, tone, bar, why){
    const on = (SRC_FILTER === key);
    return '<button class="rp-mc' + (on ? ' rp-on' : '') + '" type="button" '
      + 'onclick="sourcingFilter(' + _sarg(key) + ')" '
      + 'aria-pressed="' + (on ? 'true' : 'false') + '" title="'
      + _sesc(why || '') + (n ? (on ? ' — click to show all again.'
                                    : ' Click to show only these.') : '') + '">'
      + '<div class="rp-mc-n ' + (tone || '') + '">' + n + '</div>'
      + '<div class="rp-mc-l">' + label + '</div>'
      + '<div class="rp-mc-bar" style="width:' + pct(bar) + '%;background:'
      + (tone === 'rp-g' ? '#22c55e' : tone === 'rp-y' ? '#f0b429'
         : tone === 'rp-r' ? '#ef4444' : 'var(--line2)') + '"></div></button>';
  };
  return '<div class="rp-met">'
    // "Tracked" is the whole set, so it is the way OFF a filter rather than a
    // filter of its own -- clicking it always shows everything.
    + card('', total, 'Tracked', '', total,
           'SKUs whose supplier costs are being read every four hours.')
    + card('armed', armed, 'Armed', armed ? 'rp-g' : 'rp-d', armed,
           'SKUs that can have their price changed on Amazon without anyone '
           + 'watching. Each one was armed on its own.')
    + card('update', c.update || 0, 'Would change', (c.update ? 'rp-y' : 'rp-d'),
           c.update || 0,
           'SKUs whose price, stock or handling time is not what the rules say '
           + 'it should be.')
    + card('out_of_stock', c.out_of_stock || 0, 'Out of stock',
           (c.out_of_stock ? 'rp-r' : 'rp-d'), c.out_of_stock || 0,
           'Every supplier confirmed unable to supply. These go to zero stock '
           + 'on Amazon, and you are told.')
    + '</div>';
}

/* Turn a filter on, or off if it is already on.
 *
 * Re-renders from the rows already held -- no fetch, because the answer is
 * already on the page and a filter that waits on the network feels broken.
 * Open panels close, deliberately: a panel belonging to a row that is no longer
 * shown would be a detail floating under nothing.
 */
function sourcingFilter(key){
  SRC_FILTER = (SRC_FILTER === key) ? "" : String(key || "");
  // A selection made under one filter would act on rows you can no longer see.
  // Cleared with the filter, so "12 selected" always means twelve visible rows.
  SRC_SEL = new Set();
  sourcingRender(SRC_LAST_J || {});
  const host = document.getElementById("srcbody");
  if(host) host.scrollIntoView({block: "start", behavior: "auto"});
}

/* Which rows a filter admits. One place, so the table and the count that
 * labels it can never disagree about what "armed" means. */
function _srcVisible(){
  const rows = SRC_ROWS || [];
  if(!SRC_FILTER) return rows;
  return rows.filter(function(r){
    const d = r.decision || {};
    if(SRC_FILTER === "armed") return r.mode === "live";
    if(SRC_FILTER === "update") return d.action === "update";
    if(SRC_FILTER === "out_of_stock") return d.action === "out_of_stock";
    return true;
  });
}

/* ONE line, only when there is something to act on.
 *
 * It replaces two full-width banners that listed the affected SKUs by name --
 * thirteen of them in three columns, then six more. Naming thirteen SKUs in a
 * banner is a table pretending to be a warning, and the table underneath
 * already has a row for each with a red dot in the state column.
 *
 * So this says HOW MANY and WHAT IT MEANS, in the order you would act: things
 * that are already wrong on Amazon first, then things that are stopping the
 * app working, then things you have not set up yet. A screen with nothing
 * wrong shows no banner at all.
 */
function _alertBar(j){
  const c = j.counts || {};
  const rows = SRC_ROWS || [];
  const noFloor = rows.filter(function(r){
    return r.mode !== 'live' && (r.rule || {}).min_price == null;
  }).length;
  // Held is not the same as "would go out of stock": a held SKU is one the app
  // COULD NOT decide about, so it is sitting at whatever price it had.
  const held = c.blocked || 0;

  // WHAT NO TARGET ACTUALLY MEANS FOR THE PRICE.
  //
  // The repricer does not price TOWARDS a floor, it prices AT it -- the price
  // IS the floor, because the price follows the supplier and nothing pulls it
  // up. So a SKU with no target is priced at break-even: cost plus Amazon's
  // cut, and nothing else.
  //
  // That is exactly what a 0% default asks for, and it is a correct absolute
  // limit. But it is not obvious from the words "Target: none", and the
  // consequence is large: measured on jack_uk the moment the default changed,
  // 22 SKUs would have been cut, the deepest by 71.5% (16.99 to 4.84), giving
  // up about £160 a unit of margin in total.
  //
  // Nothing can happen without a floor and an arming, so this is a warning
  // rather than a fault -- but it has to be said BEFORE somebody arms them,
  // not afterwards in a notification about a price that has already dropped.
  const cuts = rows.filter(function(r){
    const d = r.decision || {}, ru = r.rule || {}, cu = r.current || {};
    return d.action === 'update' && d.price != null && cu.price != null
        && d.price < cu.price - 0.01
        && ru.target_roi_pct == null && ru.target_margin_pct == null;
  });
  // HOW MANY CUTS THE UP-ONLY SETTING IS CURRENTLY PREVENTING.
  //
  // This is the good-news half of the same fact, and it belongs on screen for
  // the same reason: without it, "nothing would change" reads as "there is
  // nothing to think about", when what is really happening is that a setting
  // is holding 22 prices up that the rules would otherwise cut. If somebody
  // switches those SKUs to "up and down" they should know what it costs
  // before they do it, not after.
  const helds = rows.filter(function(r){
    return (r.decision || {}).direction_held;
  });
  let saved = 0;
  helds.forEach(function(r){
    const d = r.decision, cu = r.current || {};
    if(d.direction_floor != null && cu.price != null)
      saved += (cu.price - d.direction_floor);
  });

  const bits = [];
  if(c.out_of_stock)
    bits.push('<b>' + c.out_of_stock + '</b> would go out of stock');
  if(held)
    bits.push('<b>' + held + '</b> held &mdash; open one to see what stopped it');
  if(noFloor)
    bits.push('<b>' + noFloor + '</b> cannot be armed without a minimum price');

  let h = '';
  if(bits.length){
    h += '<div class="rp-alert" style="margin-bottom:' + (cuts.length ? '6' : '10')
      +  'px"><i class="ti ti-alert-triangle"></i>'
      +  bits.join(' &middot; ')
      // THE FIX FOR THE MISSING FLOORS, ON THE LINE THAT REPORTS THEM.
      //
      //     "where is that set a minimum price in bulk template?"
      //
      // It was only in the ⋯ menu, and the ⋯ menu is a 36px icon at the far
      // right of the toolbar that nobody looks at. This sentence is where the
      // problem is stated, so it is where the way out of it belongs -- 66 of
      // 67 SKUs have no floor, and the floor is the one thing stopping the
      // whole account being armed.
      +  (noFloor
          ? ' <a class="db-chip" href="/sourcing/minprice_template.csv'
            + _srcUrl("") + '" style="text-decoration:none" title="'
            + 'A sheet of every tracked SKU with what it sells for, what it '
            + 'costs and the floor it has now, and one empty column to fill '
            + 'in. Fill it in Excel and upload it back.">'
            + '<i class="ti ti-file-download"></i> Get the sheet</a>'
            + '<label class="db-chip" for="src_minup" style="cursor:pointer" '
            + 'title="Reads the filled-in sheet and sets each floor. Rows left '
            + 'blank are skipped. Asks before it arms anything.">'
            + '<i class="ti ti-table-import"></i> Upload it back</label>'
          : '')
      +  '</div>';
  }
  if(cuts.length){
    // Worst case named, because "22 would be cut" and "one of them by 71%" are
    // different sizes of problem and only the second makes anyone look.
    let worst = null, worstPct = 0;
    cuts.forEach(function(r){
      const p = (r.current.price - r.decision.price) / r.current.price * 100;
      if(p > worstPct){ worstPct = p; worst = r; }
    });
    h += '<div class="rp-alert rp-alert-bad" style="margin-bottom:10px">'
      +  '<i class="ti ti-arrow-big-down-lines"></i>'
      +  '<b>' + cuts.length + '</b> SKU' + (cuts.length === 1 ? '' : 's')
      +  ' would be priced DOWN to break-even because no profit target is set'
      +  (worst ? ' &mdash; the biggest cut is <b>' + worstPct.toFixed(0)
                  + '%</b> (' + _smoney(worst.current.price) + ' &rarr; '
                  + _smoney(worst.decision.price) + ')' : '')
      +  '. <button class="db-chip" onclick="sourcingTarget(\'\')">'
      +  'Set a target</button>'
      +  '<span class="infodot" title="The repricer does not price TOWARDS a '
      +  'floor, it prices AT it: the price follows the supplier and nothing '
      +  'pulls it up. With no target, the floor is cost plus Amazon&#39;s cut '
      +  '-- break-even -- so the sale earns nothing. Set an ROI or margin '
      +  'target, or set these SKUs to move UP ONLY, which refuses a cut '
      +  'outright. Nothing is pushed until a SKU is armed and auto-pricing '
      +  'is on, so no price has moved.">i</span>'
      +  '</div>';
  }
  // Only when nothing is actually being cut -- otherwise the red line above
  // is the news and this would soften it.
  if(!cuts.length && helds.length){
    h += '<div class="rp-alert" style="background:var(--ok-bg);'
      +  'border-color:var(--ok-line);color:var(--ok);margin-bottom:10px">'
      +  '<i class="ti ti-arrow-up"></i>'
      +  '<b>' + helds.length + '</b> SKU' + (helds.length === 1 ? '' : 's')
      +  ' would have been priced down, and ' + (helds.length === 1 ? 'was' : 'were')
      +  ' not &mdash; they are set to move <b>up only</b>'
      +  (saved > 0.01 ? ', keeping <b>' + _smoney(saved)
                         + '</b> a unit in total' : '')
      +  '<span class="infodot" title="The repricer prices AT its floor, not '
      +  'towards it, so a SKU whose floor falls below what it sells for today '
      +  'would be cut. Up only refuses that: a cheaper supplier becomes '
      +  'margin instead of a discount. Change it per SKU on the Direction '
      +  'pill, or for everything selected from the bulk bar.">i</span></div>';
  }
  return h;
}

/* The eight controls that are not everyday controls.
 *
 * Each one is something you do when SETTING AN ACCOUNT UP -- import a sheet of
 * suppliers, fetch Amazon's fee rates, clear every link and start again -- or
 * something you read once. On the toolbar they had equal weight with "check
 * now", which is pressed daily, and with the switch that decides whether the
 * app touches Amazon at all.
 *
 * THE TARGET IS IN HERE TOO, and it is not a button.
 *
 *     "Target: 20% ROI is a setting, not a button"
 *
 * Right -- and it read as a button that DID something, when what it does is
 * show you a setting's current value. It is a labelled row in this menu now,
 * with its value on the right like every other setting, next to the postage
 * policy which is the same kind of thing.
 *
 * The file input has to stay in the DOM whether the menu is open or not -- a
 * <label for> pointing at an input that does not exist yet opens nothing -- so
 * it lives outside the panel and only its label is in the list.
 */
function _srcMoreMenu(j){
  // `danger` marks the one row that DESTROYS something. On the toolbar it was
  // the red .srcwipe button; in a list of plain rows it would look exactly like
  // "Get the template", which is the difference between fetching a file and
  // deleting every supplier link on the account.
  const row = function(icon, label, onclick, why, value, danger){
    return '<button class="rp-mi' + (danger ? ' rp-danger' : '') + '" '
      + 'onclick="_srcMoreClose();' + onclick + '" '
      + 'title="' + _sesc(why) + '">'
      + '<i class="ti ' + icon + '"></i><span>' + label + '</span>'
      + (value ? '<b>' + value + '</b>' : '') + '</button>';
  };
  return '<div class="rp-more">'
    + '<input type="file" id="src_upload" accept=".csv,.tsv,.xlsx,.xlsm,.xls" '
    + 'class="visually-hidden" onchange="sourcingUpload(this)">'
    // IT SAYS "MORE".
    //
    //     "where is that set a minimum price in bulk template?"
    //
    // It was a 36px unlabelled ⋯ at the far right of the toolbar, and the
    // answer was "behind it" -- which is no answer, because nobody looks
    // there. Three dots at the edge of a screen read as decoration, not as a
    // door. Verified in a browser at 1440, 1366, 1200 and 900: the button was
    // present and on screen every time and still could not be found.
    //
    // A word beside the dots turns it into a control. This is the cheap half
    // of the fix; the other half is that the sheet is now offered where the
    // need for it arises -- see _alertBar and _srcSelBar.
    + '<button class="db-chip" onclick="_srcMoreToggle(event)" '
    + 'title="Templates, Amazon fees, settings and help">'
    + '<i class="ti ti-dots"></i> More</button>'
    + '<div class="rp-menu" id="rp_more">'

    + '<div class="rp-mh">Suppliers</div>'
    + row('ti-eye', 'Track everything', 'sourcingTrackAll(this)',
          'Starts watching every live listing that is not already tracked, and '
          + 'attaches the supplier link the app recorded when it built each '
          + 'one. Changes no prices.')
    + '<label class="rp-mi" for="src_upload" onclick="_srcMoreClose()" '
    + 'title="A sheet of supplier links. One column of SKUs or ASINs, one '
    + 'column of links -- the app matches each link to the right listing and '
    + 'starts tracking it. Nothing is priced.">'
    + '<i class="ti ti-table-import"></i><span>Suppliers from a sheet</span></label>'
    + '<a class="rp-mi" href="/sourcing/template.csv" onclick="_srcMoreClose()" '
    + 'title="A sheet already listing every SKU you are tracking, with its '
    + 'ASIN, product name and its suppliers across ten columns headed '
    + '&quot;supplier 1&quot; to &quot;supplier 10&quot;. Need more than ten? '
    + 'Add a column headed &quot;supplier 11&quot;, then &quot;supplier 12&quot; '
    + '-- there is no limit, the app reads every numbered column it finds. '
    + 'Fill in the blanks and upload it back. '
    // One string, not two: this phrase is what promises the sheet is SAFE to
    // upload half-filled, and split across a concatenation it could not be
    // found -- by a reader grepping for it, or by the test that guards it.
    + 'Columns you leave blank are not changed, and a link that is already '
    + 'attached is left alone.">'
    + '<i class="ti ti-file-download"></i><span>Get the template</span></a>'
    + row('ti-eraser', 'Clear all suppliers', 'sourcingClearSuppliers()',
          'Deletes every supplier link on this account and marketplace so you '
          + 'can upload a fresh set. The SKUs stay tracked and their targets '
          + 'stay set. Asks first, and says how many links and readings will go.',
          '', true)

    // ---- floors by the sheetful --------------------------------------
    //
    //     "This is the fastest path to going live: download -> fill prices in
    //      Excel -> upload -> all armed in 2 minutes."
    //
    // Its own group because it is a WORKFLOW, not two unrelated buttons: the
    // second one only makes sense after the first, and they read as a pair.
    + '<div class="rp-mh">Minimum prices</div>'
    + '<a class="rp-mi" href="/sourcing/minprice_template.csv' + _srcUrl("")
    + '" onclick="_srcMoreClose()" title="'
    + 'A sheet of every tracked SKU with what it sells for, what it costs and '
    + 'the floor it has now — and one empty column to fill in. The floor is '
    + 'what gates arming, so this is the quickest way to make a whole account '
    + 'ready to go live.">'
    + '<i class="ti ti-file-download"></i><span>Download template</span></a>'
    + '<input type="file" id="src_minup" accept=".csv,.tsv,.xlsx,.xlsm,.xls" '
    + 'class="visually-hidden" onchange="sourcingMinPriceUpload(this)">'
    + '<label class="rp-mi" for="src_minup" onclick="_srcMoreClose()" title="'
    + 'Reads the filled-in sheet and sets each floor. Rows left blank are '
    + 'skipped, not cleared. Asks before it arms anything.">'
    + '<i class="ti ti-table-import"></i><span>Upload min prices</span></label>'

    + '<div class="rp-mh">Amazon</div>'
    + row('ti-receipt-tax', "Get Amazon's fees", 'sourcingGetFees(this)',
          'Asks Amazon what its referral fee actually is on each tracked '
          + 'product, and remembers it for a week. Prices are then worked out '
          + "from Amazon's own figure instead of your measured average. "
          + 'Changes no price by itself.')
    + row('ti-list-check', 'Check they still exist', 'sourcingCheckListings()',
          'Asks Amazon whether it still has each tracked SKU. Any it no longer '
          + 'has is marked and its auto-pricing switched off -- its suppliers '
          + 'and history are kept in case you relist it.')

    // SETTINGS, not actions. Same list, but a heading and a value on the right
    // so they read as "this is set to X" rather than as things to press.
    + '<div class="rp-mh">Settings</div>'
    + row('ti-target', 'Profit target', "sourcingTarget('')",
          'The least profit you will accept, as a margin % or an ROI % or '
          + 'both. This is the DEFAULT for every enrolled SKU -- a SKU with its '
          + 'own target, set from its Rules pills, wins over this one.',
          _sesc(_srcTargetLabel(j.rule || {}).replace(/^Target: /, '')))
    + row('ti-truck-delivery', 'Postage takes', 'sourcingShippingPolicy()',
          'How long your postage service takes once it has left. Amazon counts '
          + 'this separately from the handling time, so the repricer takes it '
          + 'OFF the handling time rather than promising it twice.',
          ((j.shipping_policy_days != null ? j.shipping_policy_days : 2) + 'd'))
    // WHAT A NEW SKU STARTS WITH -- and only a new one.
    //
    //     "This applies only to NEW enrollments. Existing SKUs keep their
    //      current rules."
    //
    // Which is why it is a separate setting from the target above rather than
    // the same one. That one is the account's fallback, read live; this one is
    // written onto a SKU once, at the moment it is enrolled. Change it and
    // nothing already tracked moves.
    + row('ti-file-plus', 'New SKUs start at', 'sourcingDefaultTarget()',
          'The target a newly tracked SKU is given. It is written onto that '
          + 'SKU when it is enrolled, so changing this never re-prices '
          + 'anything you are already tracking.',
          _srcDefaultTargetLabel())
    + row('ti-arrows-up-down', 'New SKUs may move',
          'sourcingDefaultDirection()',
          'Whether a newly tracked SKU may have its price lowered as well as '
          + 'raised. Written onto the SKU when it is enrolled, so changing '
          + 'this never affects anything already tracked.',
          {up_only: '&uarr; up only', up_and_down: 'both ways',
           match_floor: 'the floor'}[String(j.default_direction || 'up_only')]
          || '&uarr; up only')

    + '<div class="rp-mh">Help</div>'
    + row('ti-book', 'How this page works', "openGuide('repricer')",
          'What this page does, what each figure means, and what it will and '
          + 'will not change on Amazon.')
    + '</div></div>';
}

function _srcMoreToggle(e){
  if(e) e.stopPropagation();
  const m = document.getElementById("rp_more");
  if(!m) return;
  const open = !m.classList.contains("rp-open");
  m.classList.toggle("rp-open", open);
  // Click anywhere else and it shuts. Registered once per open rather than on
  // every render, so re-drawing the list sixty-seven times leaves no listeners.
  if(open){
    const off = function(ev){
      if(m.contains(ev.target)) return;
      m.classList.remove("rp-open");
      document.removeEventListener("click", off);
    };
    setTimeout(function(){ document.addEventListener("click", off); }, 0);
  }
}

function _srcMoreClose(){
  const m = document.getElementById("rp_more");
  if(m) m.classList.remove("rp-open");
}

/* What the "New SKUs start at" row shows on its right. */
function _srcDefaultTargetLabel(){
  const d = SRC_DEFAULT_TARGET || {};
  const kind = String(d.kind || "none").toLowerCase();
  if(kind === "roi" && d.pct != null) return d.pct + "% ROI";
  if(kind === "margin" && d.pct != null) return d.pct + "% margin";
  return "break-even";
}

/* THE TARGET A NEWLY TRACKED SKU IS GIVEN.
 *
 *     "Add a setting in the ⋯ menu: 'Default target for new enrollments'"
 *
 * Three choices, and the third is the honest default: nothing. A repricer with
 * no target prices no lower than break-even and no higher — which is the
 * absolute floor and nobody's commercial decision. Picking a number here is
 * saying "and start every new one at this", which is a decision, so it is
 * asked rather than assumed.
 */
async function sourcingDefaultTarget(){
  let cur = {kind: "none", pct: null};
  try{
    const g = await (await fetch("/sourcing/default_target" + _srcUrl(""))).json();
    if(g && g.ok) cur = g;
  }catch(e){ /* the shown default stands */ }
  const k = String(cur.kind || "none").toLowerCase();
  _srcModal("What a newly tracked SKU starts at",
    '<div style="font-size:12.5px;line-height:1.6">'
    + '<p>Applies to SKUs enrolled <b>from now on</b>. Nothing you are already '
    + 'tracking changes — each of those keeps whatever its own Rules pills '
    + 'say.</p>'
    + '<label class="rp-mi" style="cursor:pointer">'
    + '<input type="radio" name="src_dt" value="none"'
    + (k === "none" ? " checked" : "") + '><span>None — break-even</span></label>'
    + '<div class="cc" style="font-size:11px;margin:0 0 8px 30px">Priced no '
    + 'lower than cost plus Amazon\'s fee, and no higher until you set a '
    + 'target.</div>'
    + '<label class="rp-mi" style="cursor:pointer">'
    + '<input type="radio" name="src_dt" value="roi"'
    + (k === "roi" ? " checked" : "") + '><span>ROI</span>'
    + '<input id="src_dt_roi" type="number" min="0" max="500" step="0.5" '
    + 'style="width:74px" value="'
    + (k === "roi" && cur.pct != null ? cur.pct : "") + '" placeholder="25">'
    + '<span class="cc">%</span></label>'
    + '<div class="cc" style="font-size:11px;margin:0 0 8px 30px">What you keep '
    + 'as a share of the cash you put in.</div>'
    + '<label class="rp-mi" style="cursor:pointer">'
    + '<input type="radio" name="src_dt" value="margin"'
    + (k === "margin" ? " checked" : "") + '><span>Margin</span>'
    + '<input id="src_dt_margin" type="number" min="0" max="99" step="0.5" '
    + 'style="width:74px" value="'
    + (k === "margin" && cur.pct != null ? cur.pct : "") + '" placeholder="20">'
    + '<span class="cc">%</span></label>'
    + '<div class="cc" style="font-size:11px;margin:0 0 0 30px">What you keep '
    + 'as a share of what the buyer pays. Amazon\'s fee comes out of the same '
    + 'price, so much over 60% cannot be met.</div>'
    + '</div>',
    async function(){
      const sel = document.querySelector('input[name="src_dt"]:checked');
      const kind = sel ? sel.value : "none";
      let pct = null;
      if(kind !== "none"){
        const el = document.getElementById("src_dt_" + kind);
        pct = el ? el.value : "";
        if(String(pct).trim() === ""){
          toast("Type the percentage, or choose None");
          return false;
        }
      }
      const jr = await (await fetch("/sourcing/default_target", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({kind: kind, pct: pct})})).json();
      if(!jr.ok){ toast(jr.error || "Could not save"); return false; }
      SRC_DEFAULT_TARGET = {kind: jr.kind, pct: jr.pct};
      toast(jr.note || "Saved");
      return true;
    });
}

/* ======================================================================
 * FLOORS BY THE SHEETFUL.
 *
 * The floor is the gate -- nothing can be armed without one, and on this
 * account 66 of 67 SKUs have none. Setting them one at a time is 66 popovers,
 * and each asks a question you can only answer by comparing three numbers:
 * what it sells for, what it costs, and what you would accept. A spreadsheet
 * puts those in columns and lets you fill the fourth down the page.
 *
 * The BROWSER parses the file, using the same reader the supplier sheet uses,
 * so there is one answer to "what does this column mean" rather than a second
 * parser on the server that would eventually disagree with it (Rule 12).
 * ====================================================================== */
async function sourcingMinPriceUpload(input){
  const f = input && input.files && input.files[0];
  if(!f) return;
  input.value = "";                       // so the same file can be re-picked
  let rows;
  try{ rows = await _srcReadSheet(f); }
  catch(e){
    await uiAlert(String((e && e.message) || e),
                  {title: "That file could not be read"});
    return;
  }
  const filled = rows.filter(function(r){ return r.min_price !== ""; });
  if(!filled.length){
    await uiAlert(
      "The sheet was read (" + rows.length + " row"
      + (rows.length === 1 ? "" : "s") + "), but the “New Min Price” "
      + "column was empty on every one of them.\n\n"
      + "Fill that column in Excel and upload it again. The other columns are "
      + "there for context and are not read back.",
      {title: "Nothing to set"});
    return;
  }
  // ARMING IS OPT-IN, ALWAYS, and it is the same tick the spec asked for. A
  // sheet that armed by default would be a file turning on live pricing for a
  // whole account, which is not a thing a file should be able to do quietly.
  const arm = await _srcAskArm(filled.length);
  if(arm === null) return;

  let j;
  try{
    j = await (await fetch("/sourcing/minprice_upload", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: _srcBody({rows: filled, arm: !!arm})})).json();
  }catch(e){
    await uiAlert(String((e && e.message) || e), {title: "Upload failed"});
    return;
  }
  if(!j.ok){
    await uiAlert(j.error || "Could not set those floors.",
                  {title: "Upload refused"});
    return;
  }
  toast(j.note || (j.updated + " min prices updated"));
  // WHICH ROWS DID NOT GO IN, and why -- a summary saying "1 error" with no
  // way to find out which row is a summary you cannot act on.
  if((j.errors || []).length){
    await uiAlert(
      j.errors.slice(0, 20).map(function(e){
        return e.row + " — " + e.why; }).join("\n")
      + ((j.errors.length > 20)
          ? "\n\n…and " + (j.errors.length - 20) + " more." : ""),
      {title: j.errors.length + " row"
              + (j.errors.length === 1 ? "" : "s") + " could not be read"});
  }
  // Inline, keeping the table and any open panel exactly as they were.
  await sourcingLoad(true);
}

/* Ask whether to arm, and be honest about what that means. */
function _srcAskArm(n){
  return new Promise(function(resolve){
    _srcModal("Set " + n + " minimum price" + (n === 1 ? "" : "s"),
      '<div style="font-size:12.5px;line-height:1.6">'
      + '<p>Each row with a value in <b>New Min Price</b> gets that floor. '
      + 'Rows left blank are skipped, never cleared.</p>'
      + '<label class="rp-mi" style="cursor:pointer;margin-top:6px">'
      + '<input type="checkbox" id="src_autoarm">'
      + '<span>Also arm each SKU that gets a floor</span></label>'
      + '<div class="cc" style="font-size:11.5px;margin:2px 0 0 30px">'
      + 'Armed SKUs can have their price, stock and handling time changed on '
      + 'Amazon without anyone watching — at most one change each every four '
      + 'hours, and never below the floor this sheet is setting. '
      + (SRC_MASTER ? '' : 'Auto-pricing is currently OFF, so nothing would be '
                          + 'pushed until you switch it on.')
      + '</div></div>',
      function(){
        const el = document.getElementById("src_autoarm");
        resolve(!!(el && el.checked));
        return true;
      },
      function(){ resolve(null); });        // cancelled
  });
}

/* Read a .csv/.tsv/.xlsx into [{sku, asin, min_price}].
 *
 * Header matching is by MEANING, not by position: a person who reorders the
 * columns in Excel, or deletes the ones they did not need, has done nothing
 * wrong and the file should still work. Only the SKU/ASIN and the new floor
 * are read -- the price and cost columns are context for the reader.
 */
function _srcReadSheet(file){
  return new Promise(function(resolve, reject){
    const done = function(rowsRaw){
      if(!rowsRaw || !rowsRaw.length) return reject(new Error("It had no rows."));
      const head = rowsRaw[0].map(function(c){
        return String(c == null ? "" : c).trim().toLowerCase(); });
      const find = function(names){
        for(let i = 0; i < head.length; i++)
          if(names.indexOf(head[i]) >= 0) return i;
        return -1;
      };
      const iSku = find(["sku", "seller sku", "seller-sku"]);
      const iAsin = find(["asin", "asin1"]);
      const iNew = find(["new min price", "new min", "min price", "minimum price",
                         "new minimum price", "floor"]);
      if(iNew < 0)
        return reject(new Error(
          'There is no "New Min Price" column. Download the template again '
          + 'and fill in that column without renaming it.'));
      if(iSku < 0 && iAsin < 0)
        return reject(new Error(
          "There is no SKU or ASIN column, so the app cannot tell which "
          + "listing each row is about."));
      const out = [];
      for(let r = 1; r < rowsRaw.length; r++){
        const row = rowsRaw[r] || [];
        const cell = function(i){
          return i < 0 ? "" : String(row[i] == null ? "" : row[i]).trim(); };
        const sku = cell(iSku), asin = cell(iAsin), v = cell(iNew);
        if(!sku && !asin) continue;                 // a blank line in the sheet
        out.push({sku: sku, asin: asin, min_price: v});
      }
      resolve(out);
    };

    const name = String(file.name || "").toLowerCase();
    if(/\.xlsx?$|\.xlsm$/.test(name)){
      if(typeof XLSX === "undefined")
        return reject(new Error(
          "The spreadsheet reader did not load. Save the sheet as CSV and "
          + "upload that instead."));
      const fr = new FileReader();
      fr.onerror = function(){ reject(new Error("The file could not be read.")); };
      fr.onload = function(e){
        try{
          const wb = XLSX.read(new Uint8Array(e.target.result), {type: "array"});
          const sh = wb.Sheets[wb.SheetNames[0]];
          done(XLSX.utils.sheet_to_json(sh, {header: 1, raw: false, defval: ""}));
        }catch(err){ reject(err); }
      };
      fr.readAsArrayBuffer(file);
      return;
    }
    const fr = new FileReader();
    fr.onerror = function(){ reject(new Error("The file could not be read.")); };
    fr.onload = function(e){
      const text = String(e.target.result || "");
      // Tab if the first line has more tabs than commas -- a title with a comma
      // in it is common and must not be read as a column break.
      const first = text.split(/\r?\n/)[0] || "";
      const sep = ((first.match(/\t/g) || []).length
                   > (first.match(/,/g) || []).length) ? "\t" : ",";
      done(text.split(/\r?\n/).filter(function(l){ return l.trim() !== ""; })
               .map(function(l){ return _srcCsvLine(l, sep); }));
    };
    fr.readAsText(file);
  });
}

/* One CSV line into cells, honouring quotes -- product titles contain commas
 * and a naive split puts half a title in the ASIN column. */
function _srcCsvLine(line, sep){
  const out = [];
  let cur = "", q = false;
  for(let i = 0; i < line.length; i++){
    const ch = line[i];
    if(q){
      if(ch === '"'){
        if(line[i + 1] === '"'){ cur += '"'; i++; }   // "" is a literal quote
        else q = false;
      } else cur += ch;
    } else if(ch === '"'){ q = true; }
    else if(ch === sep){ out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}

/* HOW LONG YOUR POSTAGE TAKES. Global, not per SKU: it describes the courier,
 * not the product. It is the number the handling time is reduced BY, so if it
 * is wrong every promised delivery date is wrong with it. */
async function sourcingShippingPolicy(){
  let cur = 2;
  try{
    const g = await (await fetch("/sourcing/shipping_policy" + _srcUrl(""))).json();
    if(g && g.ok) cur = g.days;
  }catch(e){ /* the default stands */ }
  _srcModal("How long your postage takes",
    '<div style="font-size:12.5px;line-height:1.6">'
    + '<p>Amazon shows a buyer <b>two</b> numbers added together: the handling '
    + 'time you set, and how long the postage service on the listing takes. '
    + 'So the repricer takes these days OFF the handling time rather than '
    + 'promising them twice.</p>'
    + '<p class="cc" style="font-size:11.5px">With 2 days here, a supplier who '
    + 'dispatches in 3 gives 1 day of handling &mdash; and the buyer is still '
    + 'shown 3 days, which is what the supplier actually promised. Set it to '
    + 'match the service you really post with; if it is wrong, every delivery '
    + 'date on every listing is wrong with it.</p>'
    + '<label class="cc" style="font-size:11.5px;display:block;margin-top:8px">'
    + 'Days in transit (0 to 30)</label>'
    + '<input id="src_pol" type="number" min="0" max="30" step="1" value="'
    + (+cur) + '" style="width:110px;margin-top:4px">'
    + '</div>',
    async function(){
      const el = document.getElementById("src_pol");
      const jr = await (await fetch("/sourcing/shipping_policy", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({days: el ? el.value : ""})})).json();
      if(!jr.ok){ toast(jr.error || "Could not save"); return false; }
      toast(jr.note || "Saved");
      await sourcingLoad(true);
      return true;
    });
}

function sourcingRender(j){
  const body = document.getElementById("srcbody");
  const c = j.counts || {};
  let h = "";
  // Kept so a filter can redraw from what is already here rather than fetching
  // sixty-seven decisions again to show a subset of the ones on screen.
  SRC_LAST_J = j;

  // ---- the toolbar: three controls, and a menu -------------------------
  //
  //     "consolidate into a clean toolbar ... Keep ONLY these visible"
  //
  // There were eleven buttons wrapped across two rows. Eight of them are things
  // you do once when setting an account up -- import a sheet, fetch the fee
  // rates, clear every supplier -- and they were sharing a row, and equal
  // weight, with the two you press every day and the switch that decides
  // whether the app touches Amazon at all.
  //
  // Nothing was removed. The eight moved into a menu, which is one click and
  // costs nothing, and the three that are left are the ones that answer "check
  // now", "watch this SKU too" and "is it live?".
  const live = SRC_ROWS.filter(function(r){ return r.mode === "live"; }).length;
  h += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;'
    +  'margin:2px 0 10px">'
    // THE SWITCH THAT ACTUALLY MATTERS, first and coloured. It is the answer to
    // "can this thing change my prices right now", and that is the only
    // question on this screen worth being unable to miss.
    +  '<button class="db-chip' + (SRC_MASTER ? ' risk' : '') + '" '
    +  'onclick="sourcingMaster(' + (SRC_MASTER ? "false" : "true") + ')" title="'
    +  (SRC_MASTER
        ? 'Auto-pricing is ON. Armed SKUs can have their price, stock and '
          + 'handling time changed on Amazon without anyone watching. '
          + live + ' of ' + SRC_ROWS.length + ' are armed.'
        : 'Auto-pricing is OFF. Costs are still tracked and decisions still '
          + 'recorded; nothing reaches Amazon.') + '">'
    +  (SRC_MASTER ? '<i class="ti ti-lock-open"></i> Auto-pricing: ON'
                   : '<i class="ti ti-lock"></i> Auto-pricing: off') + '</button>'
    +  '<button class="db-chip" onclick="sourcingCheckNow(this)" title="'
    +  'Reads every tracked supplier now instead of waiting for the next '
    +  '4-hourly sweep. Changes no prices.">'
    +  '<i class="ti ti-refresh"></i> Check now</button>'
    +  '<button class="db-chip" onclick="sourcingAddPrompt()" title="'
    +  'Start tracking one more of this account&#39;s live listings. Enrolling '
    +  'watches its suppliers; it does not price it.">'
    +  '<i class="ti ti-plus"></i> Enroll</button>'
    +  '<span style="flex:1"></span>'
    +  _srcMoreMenu(j)
    +  '</div>';

  // ---- ONE alert, not three banners ------------------------------------
  //
  // Two full-width blocks used to list every affected SKU by name -- 13 of them
  // in three columns, then 6 more -- above a green paragraph explaining that
  // tracking is not pricing. Naming thirteen SKUs in a banner is a table
  // pretending to be a warning, and the table underneath already has a row for
  // each of them with a red dot.
  //
  // So the banner says HOW MANY and WHAT TO DO, and the SKUs stay where SKUs
  // belong. Drawn only when there is something to act on: a quiet screen with
  // nothing wrong shows no banner at all.
  h += _alertBar(j);

  // ---- the numbers ------------------------------------------------------
  if(SRC_ROWS.length) h += _statCards(j);
  h += sourcingUploadReport();

  if(j.note){
    h += '<div class="cc" style="font-size:12px;padding:10px;border:1px dashed #2a3446;border-radius:6px">'
      +  _sesc(j.note)+' Enroll a SKU above to start watching its suppliers.</div>';
    body.innerHTML = h; return;
  }

  // The selection bar sits directly above the rows it acts on, and only when
  // something is selected -- a permanent empty toolbar is one more thing to read
  // past on a screen that already has plenty.
  h += '<div id="srcselbar"></div>';

  // NOTHING BETWEEN THE CARDS AND THE TABLE.
  //
  //     "Remove the 'Click any row to open it...' explanation at the bottom --
  //      users figure this out by clicking"
  //
  // Quite so. A row that highlights on hover and has a cursor is already
  // telling you it can be clicked, and a sentence saying so is a sentence
  // everybody reads once and nobody needs twice. What that line ALSO carried --
  // what Item, Post and Profit each mean -- has gone onto the column headers as
  // tooltips, which is where a column's definition belongs: attached to the
  // column, available when you wonder, invisible when you do not.

  // THE TABLE.
  //
  //     "8. Click row = detail expands inline below"
  //
  // Nine columns, and the last is deliberately narrow: the status dot. It is
  // there so the state of a listing reads down a column rather than having to
  // be found in a chip somewhere along each row.
  h += '<div class="rp-card"><div class="rp-scroll">'
    +  '<table class="rp-tbl"><thead><tr>'
    +  '<th style="width:22px"><input type="checkbox" id="rp_all" '
    +  'onclick="sourcingSelectAll(this.checked)" title="Select every SKU shown" '
    +  'style="width:14px;height:14px;cursor:pointer;accent-color:var(--accent)">'
    +  '</th>'
    +  '<th style="width:44px"></th><th>Product</th>'
    +  '<th title="What the cheapest usable supplier charges for the item">Item</th>'
    +  '<th title="That supplier&#39;s postage to you">Post</th>'
    +  '<th title="What it sells for on Amazon now, and what the rules say it '
    +  'should be">Price</th>'
    +  '<th title="What is left per unit after Amazon, postage and ads">Profit</th>'
    +  '<th title="That profit as a share of the cash you put in">ROI</th>'
    +  '<th title="What this SKU&#39;s cheapest supplier has been charging">Trend</th>'
    +  '<th style="width:14px"></th>'
    +  '</tr></thead><tbody id="rp_body">';
  // Filtered, and the INDEX is the row's real position in SRC_ROWS -- the panel
  // ids are built from it, and renumbering them under a filter would make
  // "which row is open" mean two different things on two different views.
  const shown = _srcVisible();
  SRC_ROWS.forEach(function(r, i){
    if(shown.indexOf(r) >= 0) h += sourcingRow(r, i);
  });
  h += '</tbody></table></div></div>';
  // A filter that hides everything must say so, or it reads as a table that
  // failed to load.
  if(!shown.length && SRC_ROWS.length){
    h += '<div class="cc" style="font-size:12px;padding:14px 4px">'
      +  'No SKU is in that state right now. '
      +  '<button class="db-chip" onclick="sourcingFilter(\'\')">'
      +  'Show all ' + SRC_ROWS.length + '</button></div>';
  }
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
  let ok = 0;
  const bad = [];
  for(const sku of skus){
    const err = await sourcingSaveRuleQuiet(sku, rule);
    if(err) bad.push(sku + ": " + err); else ok++;
  }
  toast(verb + " on " + ok + " SKU" + (ok === 1 ? "" : "s")
        + (bad.length ? " · " + bad.length + " refused" : ""));
  if(bad.length) await uiAlert(bad.slice(0, 12).join("\n"),
                               {title: bad.length + " could not be saved"});
  await sourcingLoad(true);
}

/* sourcingSaveRule without the toast and without a refresh per SKU. */
async function sourcingSaveRuleQuiet(sku, rule){
  try{
    const j = await (await fetch("/sourcing/rules", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: _srcBody({sku: sku, rule: rule})})).json();
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
  }
  let done = 0;
  const bad = [];
  for(const sku of skus){
    try{
      const j = await (await fetch("/sourcing/arm", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({sku: sku, live: !!on})})).json();
      if(j.ok) done++; else bad.push(sku + ": " + (j.error || "refused"));
    }catch(e){ bad.push(sku + ": " + String((e && e.message) || e)); }
  }
  toast((on ? "Armed " : "Disarmed ") + done
        + (bad.length ? " · " + bad.length + " refused" : ""));
  // WHY EACH REFUSAL HAPPENED, not just how many. Almost always a missing
  // floor, and that is fixable in one more click from the same bar.
  if(bad.length) await uiAlert(bad.slice(0, 12).join("\n"),
                               {title: bad.length + " could not be armed"});
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

// The sum, laid out. It exists because the one-sentence version of this was
// accurate and unreadable: "price 20.33 = 11.28 cost + 3.05 fee + 3.00 postage
// + 2.00 ads + 1.00 profit" is five numbers and a total run together, and the
// question it has to answer -- "where did my price come from" -- is answered
// much better by a list than by a sentence. The sentence is still what gets
// stored in the log, unchanged; this is only how it is drawn.
// EVERY AMAZON CHARGE, INCLUDING THE ONES YOU ARE NOT PAYING.
//
// The line above says "Amazon's cut 3.60". This says what that 3.60 is made
// of, and -- deliberately -- lists the charges that came to nothing. A fee
// showing 0.00 next to "not charged -- you post this yourself" answers the
// question "is the app forgetting FBA?" before it gets asked. Charged lines
// carry the mockup's fee colours; uncharged ones are dimmed, not hidden.
//
// It is folded shut by default. The sum above is the answer most of the time;
// this is for the times it is not.
function _allFees(d, cur){
  const f = (d || {}).fees;
  if(!f || !(f.lines || []).length) return '';
  const id = 'fee_' + Math.random().toString(36).slice(2, 9);
  const COL = {referral: '#e25c5c', closing: '#d4846f', fba: '#8b95a5'};
  let rows = '';
  (f.lines || []).forEach(function(l){
    const on = !!l.charged;
    rows += '<div style="display:flex;gap:8px;font-size:11.5px;padding:1.5px 0;'
         +  (on ? '' : 'opacity:.45') + '">'
         +  '<span style="min-width:178px;padding-left:8px;'
         +    (on ? 'border-left:2px solid ' + (COL[l.key] || '#5b8fb9')
                  : 'border-left:2px solid transparent') + '" class="cc">'
         +    _sesc(l.label) + '</span>'
         +  '<span style="min-width:62px;text-align:right">'
         +    _smoney(l.amount) + '</span>'
         +  '<span class="cc">' + _sesc(l.note || '') + '</span></div>';
  });
  // No left indent any more. It used to be inset 194px so the link lined up
  // under the label column of the price list above it; that list is gone, so
  // the indent would now be 194px of nothing.
  return '<div style="margin:2px 0 4px">'
    +  '<a href="#" class="cc" style="font-size:11px;text-decoration:none;'
    +    'border-bottom:1px dotted currentColor" '
    +    'onclick="event.stopPropagation();'
    +    'var e=document.getElementById(\'' + id + '\');'
    +    'var s=e.style.display===\'none\';e.style.display=s?\'\':\'none\';'
    +    'this.textContent=(s?\'Hide\':\'All\')+\' Amazon fees\';'
    +    'return false">All Amazon fees</a></div>'
    +  '<div id="' + id + '" style="display:none;margin:2px 0 7px">'
    +    rows
    +    '<div class="cc" style="font-size:10.5px;padding:4px 0 0 8px">'
    +      _sesc(f.detail || '') + '</div></div>';
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
  // A DATE **OR** A TIMESTAMP. Readings are stored as "2026-08-17 08:12:46",
  // and the old pattern anchored to the end of a bare date -- so every supplier
  // reading failed to match and the chart fell back to printing the raw
  // "2026-08-17 08:12:46" in a column an inch wide.
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T]|$)/.exec(String(iso || ''));
  if(!m) return '';
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  if(isNaN(d)) return '';
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return days[d.getUTCDay()] + ' ' + d.getUTCDate() + ' ' + mon[d.getUTCMonth()];
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

/* WHICH DOT, and what each one is telling you.
 *
 * Five states, and they answer five different questions, which is why they are
 * separate colours rather than shades of one:
 *   red    the supplier has ended or Amazon has lost the listing -- act
 *   amber  something is stopping a decision -- decide
 *   green  armed, and it can change a live price on its own -- watch
 *   teal   tracked and deciding, but nothing reaches Amazon -- safe
 *   grey   nothing has been read yet -- wait
 */
function _rpDot(r){
  const d = r.decision || {};
  if(String(d.listing_state || "") === "gone")
    return ['rp-dr', 'Amazon no longer has this SKU. There is no offer to price.'];
  if(d.action === "out_of_stock")
    return ['rp-dr', 'Every supplier confirmed unable to supply. This would go '
                   + 'to zero stock on Amazon.'];
  if(d.blocked_by)
    return ['rp-dy', 'Held: ' + d.blocked_by];
  if(r.mode === "live")
    return ['rp-dg', 'Armed. This SKU can have its price, stock and handling '
                   + 'time changed on Amazon without anyone watching.'];
  if(d.action === "update" || d.action === "none")
    return ['rp-db', 'Tracked and deciding. Nothing reaches Amazon until it is '
                   + 'armed.'];
  return ['rp-dd', 'Nothing has been read for this SKU yet.'];
}

/* The cheapest usable supplier's history, for the row's sparkline.
 * One line per SKU, not one per supplier -- the row is about the SKU, and the
 * supplier it would actually buy from is the one whose cost decides its price.
 */
function _rpRowHist(r){
  const used = (r.decision || {}).source_id;
  const srcs = r.sources || [];
  let pick = srcs.filter(function(s){ return used != null && s.id === used; })[0];
  if(!pick) pick = srcs.filter(function(s){ return (s.history || []).length > 1; })[0];
  return (pick || {}).history || [];
}

function sourcingRow(r, i){
  const d = r.decision || {}, cur = r.current || {}, g = r.glance || {};
  const b = d.breakdown || {};
  const id = "srcrow_"+i;
  const it = r.item || {};
  const dot = _rpDot(r);
  const asin = (cur.asin || it.asin || "");
  // Held rows get a tint so the ones needing a decision are findable without
  // reading every reason line.
  const rowCls = 'rp-row' + (d.blocked_by ? ' rp-held' : '');

  // ---- the nine columns ------------------------------------------------
  //
  // The whole row is the button that opens the detail. Anything inside it that
  // is itself clickable -- the tick, the ASIN link, the sparkline -- stops the
  // event, so selecting a SKU or following a link does not also toggle a panel.
  let h = '<tr class="' + rowCls + '" id="' + id + '_r" '
    + 'onclick="sourcingToggleDetail(' + _sarg(id) + ')">';

  // 1. select
  h += '<td onclick="event.stopPropagation()">'
    + '<input type="checkbox" class="srcsel" data-sku="' + _sesc(r.sku) + '"'
    + (SRC_SEL.has(r.sku) ? ' checked' : '')
    + ' onclick="sourcingSelect(' + _sarg(r.sku) + ',this.checked)" '
    + 'title="Select this SKU" '
    + 'style="width:14px;height:14px;cursor:pointer;accent-color:var(--accent)">'
    + '</td>';

  // 2. the picture. WHOSE it is still matters: a supplier photograph shown as
  // though it were the live listing's would be the app telling you what is on
  // your Amazon page when it is nothing of the kind.
  const fromSup = (it.img_source === "supplier");
  h += '<td><div class="rp-thumb" title="'
    + _sesc(fromSup
        ? "The SUPPLIER's photograph, from the source listing. Amazon has no "
          + "image for this SKU."
        : (it.img ? "The image on the live Amazon listing."
                  : "No picture -- Amazon has none for this SKU."))
    + '">'
    + (it.img
        ? '<img src="' + _sesc(thumbUrl(it.img, 72)) + '" loading="lazy" '
          + 'decoding="async" alt="">'
          // A CORNER MARK, not just a tooltip. Showing a supplier's photograph
          // as though it were the live listing's would be the app telling you
          // what is on your Amazon page when it is nothing of the kind, and a
          // tooltip is invisible on a phone.
          + (fromSup
              ? '<span style="position:absolute;right:0;bottom:0;'
                + 'background:var(--warn-bg);color:var(--warn);font-size:7px;'
                + 'font-weight:700;padding:0 2px;line-height:10px;'
                + 'border-radius:2px 0 0 0">SRC</span>'
              : '')
        : '<i class="ti ti-photo"></i>')
    + '</div></td>';

  // 3. name + ASIN. The ASIN links to Amazon, because when a row looks wrong
  // the next thing anyone does is go and look at the listing.
  // THREE THINGS THE COLUMNS CANNOT SAY, kept beside the name because each one
  // means "the numbers on this row are not what they look like":
  //   gone      Amazon no longer has the listing, so nothing here is a price
  //   cost up   the profit figures still subtract a cost the supplier left
  //             behind, so they are overstated by that much on every sale
  //   2 of 3    one of this SKU's suppliers cannot be bought from right now,
  //             which is why the cheapest price on the row is not the one used
  // They were chips across the old card. As chips they were the loudest thing
  // on the row; here they are 8px marks that only appear when they are true.
  const dft = r.drift || {};
  const nOpt = (r.options || []).length;
  const nUse = (r.options || []).filter(function(o){
    return o.state === 'buyable';
  }).length;
  let flags = '';
  if(String(d.listing_state || "") === "gone")
    flags += '<span class="rp-tag rp-tgo" title="Amazon no longer has this SKU, '
          +  'so there is no offer to price. Auto-pricing was switched off for '
          +  'it. Its suppliers and history are kept in case you relist.">GONE</span> ';
  if(dft.delta != null && dft.delta !== 0)
    flags += '<span class="rp-tag" style="background:var(--warn-bg);'
          +  'color:var(--warn)" title="This SKU was created when a unit cost '
          +  _sesc(_smoney(dft.cogs)) + '. The supplier now charges '
          +  _sesc(_smoney(dft.landed)) + ' delivered, so profit figures are out '
          +  'by about ' + _sesc(_smoney(Math.abs(dft.delta))) + ' a unit.">cost '
          +  (dft.delta > 0 ? '&uarr;' : '&darr;')
          +  (dft.cogs ? Math.abs(dft.delta / dft.cogs * 100).toFixed(0) + '%' : '')
          +  '</span> ';
  if(nOpt && nUse < nOpt)
    flags += '<span class="rp-tag" style="background:var(--warn-bg);'
          +  'color:var(--warn)" title="' + (nOpt - nUse) + ' of this SKU\'s '
          +  'supplier links cannot be bought from right now. Open the row to '
          +  'see which, and why.">' + nUse + '/' + nOpt + '</span> ';

  // THE SKU IS IN THE TOOLTIP, NOT THE COLUMN. It is the identifier everything
  // else uses -- the upload template, the arm call, the log -- so it cannot go
  // away; but 10.39_3Days_B0F6LQ1S93 tells nobody WHICH PRODUCT this is, and
  // that is what a column three inches wide has to answer. So the name is
  // shown, the SKU is one hover away, and the panel prints it in full.
  h += '<td><div class="rp-nm" title="' + _sesc((it.title || "") + "\n" + r.sku) + '">'
    + _sesc(it.title || r.sku) + '</div>'
    + '<div style="display:flex;gap:3px;align-items:center;margin-top:1px">'
    + (asin
        ? '<a class="rp-asin" href="https://www.amazon.co.uk/dp/' + _sesc(asin)
          + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" '
          + 'title="Open this listing on Amazon">' + _sesc(asin) + '</a>'
        : '<span class="rp-d" style="font-size:9px">' + _sesc(r.sku) + '</span>')
    + (flags ? '<span style="margin-left:2px">' + flags + '</span>' : '')
    + '</div></td>';

  // 4+5. the supplier's two numbers, apart.
  //
  //     "show item cost and shipping separately"
  //
  // They were one landed figure, and a landed figure hides which half moved. A
  // supplier who holds their price and doubles their postage looks identical to
  // one who put the item up.
  const sp = (g.source_price != null) ? g.source_price : b.supplier_price;
  const sh = (g.source_postage != null) ? g.source_postage : b.supplier_postage;
  h += '<td class="rp-p">' + (sp != null ? _smoney(sp) : '<span class="rp-d">&mdash;</span>') + '</td>'
    + '<td class="rp-d" style="font-size:10.5px">'
    + (sh == null ? '&mdash;' : (sh > 0 ? _smoney(sh) : 'free')) + '</td>';

  // 6. price now, and where it is going.
  h += '<td>';
  if(d.action === "update" && d.price != null && cur.price != null
     && Math.abs(d.price - cur.price) >= 0.01){
    const up = d.price > cur.price;
    h += '<span class="rp-was">' + _smoney(cur.price) + '</span> '
      +  '<span class="rp-p ' + (up ? 'rp-g' : 'rp-y') + '">'
      +  _smoney(d.price) + '</span>';
  } else {
    h += '<span class="rp-p">'
      +  (cur.price != null ? _smoney(cur.price) : '<span class="rp-d">&mdash;</span>')
      +  '</span>';
  }
  // SET IT BY HAND, from the row.
  //
  //     "add this to the table row -- a small pencil icon next to the PRICE
  //      column that opens the same inline editor."
  //
  // Quiet until the row is hovered: sixty-seven pencils down a column is a
  // column of pencils. It opens the same editor the panel's button does, so
  // there is one place a price is typed (CLAUDE.md Rule 12).
  if(cur.price != null){
    h += ' <button class="rp-pen" onclick="event.stopPropagation();'
      +  'sourcingManualPrice(' + _sarg(r.sku) + ',this)" '
      +  'title="Set this price on Amazon by hand">'
      +  '<i class="ti ti-pencil"></i></button>';
  }

  // A COUPON IS RUNNING ON THIS SKU, so the price in this column is not what
  // buyers have been paying. Marked rather than substituted: the listed price
  // is what the rules act on, and the discounted one is what the profit really
  // was. Both are in the panel; this says "there are two".
  if(g.promo && g.sell_price_promo != null){
    h += ' <span class="rp-tag" style="background:var(--warn-bg);'
      +  'color:var(--warn)" title="A discount has been measured on this SKU '
      +  'from settled orders: buyers have been paying about '
      +  _sesc(_smoney(g.sell_price_promo)) + '. Open the row for the profit at '
      +  'that price.">' + _sesc(_smoney(g.sell_price_promo)) + '</span>';
  }
  h += '</td>';

  // 7+8. profit and ROI, from the sale that would happen NOW.
  const pf = (g.profit != null) ? g.profit : b.profit;
  const roi = (g.roi_pct != null) ? g.roi_pct
            : (b.profit != null && b.cost ? (b.profit / b.cost) * 100 : null);
  const tgt = (r.rule || {}).target_roi_pct;
  const roiTone = (roi == null) ? 'rp-d'
                : (roi < 0) ? 'rp-r'
                : (tgt != null && roi < +tgt) ? 'rp-y' : 'rp-g';
  h += '<td class="rp-p ' + (pf == null ? 'rp-d' : pf < 0 ? 'rp-r' : 'rp-g') + '">'
    + (pf != null ? _smoney(pf) : '&mdash;') + '</td>'
    + '<td class="' + roiTone + '" style="font-size:10.5px;font-weight:500" title="'
    + (tgt != null ? 'You asked for ' + tgt + '% on this SKU' : 'No ROI target set')
    + '">' + (roi != null ? roi.toFixed(0) + '%' : '&mdash;') + '</td>';

  // 9. the trend, and 10 the dot.
  h += '<td>' + (_spark(_rpRowHist(r), {title: it.title || r.sku})
                 || '<span class="rp-d" style="font-size:9px">no history</span>')
    + '</td>'
    + '<td><span class="rp-dot ' + dot[0] + '" title="' + _sesc(dot[1])
    + '"></span></td></tr>';

  // ---- the panel, in a row of its own ----------------------------------
  //
  //     "the detail panel must be FLUSH with the table edges ... The detail
  //      <td colspan> should have padding:0"
  //
  // Hidden rather than absent, so opening one costs nothing and the browser
  // keeps the scroll position -- inserting rows on click made the page jump.
  h += '<tr id="' + id + '" style="display:none"><td colspan="10" class="rp-detcell">'
    + '<div class="rp-det">';

  // THE SKU IN FULL, once the row is open. It is the code every other part of
  // the app is keyed on -- the supplier template, the log, the arm call -- so
  // it has to be copyable from here even though the column shows the name.
  h += '<div class="cc" style="font-size:10px;margin-bottom:6px">'
    +  '<code>' + _sesc(r.sku) + '</code>'
    +  (asin ? ' &middot; ASIN ' + _sesc(asin) : '')
    +  '</div>';

  // WHY NOTHING IS HAPPENING -- and ONLY that.
  //
  //     "no paragraphs"
  //
  // The full reason sentence used to be drawn here: "Buying from eBay item
  // 235976183512 at 10.06 delivered. Selling at 14.64 leaves 2.02 a unit after
  // Amazon's 2.56 fee. That is 20% back on what you paid and 14% of the sale
  // price. Handling 1 day -- ..." Every number in it is now a shape or a tile
  // an inch above: the supplier's 10.06 is the blue segment, the 2.56 the red
  // one, the 2.02 the green one, and the 20%, 14% and 1 day are three of the
  // four tiles. Reading the same figures twice, once as prose, is what made the
  // panel long enough to need scrolling.
  //
  // It is still written in full to the decision log, which is where a permanent
  // record belongs. Nothing was lost, only stopped being said twice.
  //
  // blocked_by STAYS, because it is the one thing no shape can carry: a bar
  // cannot draw the absence of a decision. It is a phrase, not a paragraph, and
  // without it a held SKU shows four dashes and no explanation.
  if(d.blocked_by){
    h += '<div class="rp-alert" style="margin-bottom:9px">'
      +  '<i class="ti ti-player-pause"></i>' + _sesc(d.blocked_by) + '</div>';
  }

  // A big move happens and TELLS you, rather than waiting for a human who is
  // not there at 3am.
  if(d.large_move && d.large_move_note){
    h += '<div class="rp-alert" style="margin-bottom:9px">'
      +  '<i class="ti ti-bell"></i>' + _sesc(d.large_move_note)
      +  ' &mdash; the change still goes through, and you are told.</div>';
  }

  // Where the price goes, then the three figures, then the actions.
  h += _stackBar(b) + _metStrip(r);

  h += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:9px">'
    +  (r.mode === "live"
        ? '<button class="db-chip" style="background:var(--red-bg);'
          + 'color:var(--red);border-color:var(--red-line)" '
          + 'onclick="event.stopPropagation();sourcingArm(' + _sarg(r.sku)
          + ',false)">Armed &mdash; disarm</button>'
        : ((r.rule || {}).min_price == null
            ? '<button class="db-chip" style="border-color:var(--warn);'
              + 'color:var(--warn)" onclick="event.stopPropagation();'
              + 'sourcingMinPrice(' + _sarg(r.sku) + ',this)" '
              + 'title="A SKU cannot be armed until it has a price it will never '
              + 'sell below. That floor is the one guard that still works if a '
              + "supplier's page is misread. Click to set it.\">"
              + 'Set a minimum price to arm</button>'
            : '<button class="db-chip" onclick="event.stopPropagation();'
              + 'sourcingArm(' + _sarg(r.sku) + ',true)">Arm</button>'))
    // SET THE PRICE BY HAND. Beside the arm button because it is the other
    // way a price changes -- one of them lets the app do it, the other does it
    // yourself. It pushes to Amazon immediately; the tooltip says so, because
    // "Edit price" on a screen full of proposals could be read as editing a
    // proposal.
    +  (cur.price != null
        ? '<button class="db-chip" onclick="event.stopPropagation();'
          + 'sourcingManualPrice(' + _sarg(r.sku) + ',this)" title="'
          + 'Sets this price on Amazon NOW, without waiting for the next '
          + 'check. It must be at or above your minimum price. The repricer '
          + 'then treats it as the current price and only acts again if costs '
          + 'force it.">'
          + '<i class="ti ti-pencil"></i> Edit price</button>'
        : '')
    +  '<button class="db-chip" onclick="event.stopPropagation();'
    +  'sourcingAddSourcePrompt(' + _sarg(r.sku) + ')">'
    +  '<i class="ti ti-plus"></i> Add a supplier</button>'
    +  '<button class="db-chip" onclick="event.stopPropagation();'
    +  'sourcingHoldPrice(' + _sarg(r.sku) + ',this)" title="'
    +  'Use this when you know what a product sells for. The repricer will never '
    +  'price BELOW it, even if your target would be met by less. It is a floor, '
    +  'not a fixed price: if the supplier gets dearer the price still goes UP.">'
    +  'Hold at ' + ((r.rule || {}).hold_price != null
                     ? _smoney(r.rule.hold_price) : '&hellip;') + '</button>'
    +  '<button class="db-chip" onclick="event.stopPropagation();'
    +  'sourcingUnenrol(' + _sarg(r.sku) + ')">Stop tracking</button>'
    +  '</div>';

  // Remembered so the target boxes open showing what THIS SKU has rather than
  // the account default -- opening them pre-filled with someone else's numbers
  // and pressing Save would silently overwrite the override.
  SRC_ROW_RULES[r.sku] = r.rule || {};


  // THE FEE BREAKDOWN, AND NOTHING ELSE FROM THE OLD SUM.
  //
  // _priceBreakdown drew the whole thing as a labelled list -- supplier price,
  // landed cost, Amazon's cut, postage, ads, profit, total, then a handling
  // sentence and a supplier count. Every one of those is now a segment of the
  // stacked bar, a tile, or a row in the supplier table, so the list was the
  // same figures a second time in words.
  //
  // What it carried that nothing else does is the "All Amazon fees" panel: the
  // split between referral and closing, and the FBA line that reads 0.00 with
  // the reason, which is what answers "is the app forgetting FBA?". That is
  // kept, on its own, folded shut.
  h += _allFees(d, cur);

  // THE FOUR NOTICES, EACH ONE LINE.
  //
  // These were four paragraphs of two or three sentences apiece. Every one of
  // them exists to carry a NUMBER you would act on -- the price that would
  // clear your target, how much a profit figure is out by, what a hold is
  // holding at -- and the sentences around those numbers were explaining
  // mechanics that belong in a tooltip, not on the panel of every SKU.
  //
  // So each is now one line: the number, and the shortest phrase that says what
  // it is. The explanation is on hover, where somebody who needs it can get it
  // and nobody else has to read past it.
  const note = function(tone, icon, text, why){
    return '<div class="rp-alert" style="margin:0 0 5px;'
      + (tone === 'ok'
          ? 'background:var(--ok-bg);border-color:var(--ok-line);color:var(--ok)'
          : tone === 'bad'
          ? 'background:var(--red-bg);border-color:var(--red-line);color:var(--red)'
          : '') + '" title="' + _sesc(why || '') + '">'
      + '<i class="ti ' + icon + '"></i>' + text + '</div>';
  };

  const tg = d.target, bd = d.breakdown || {};
  if(tg && tg.meets === false){
    // EVERY target it misses, not just the worst. With two on, naming one and
    // quoting a floor set by the other is a sum that does not add up on screen.
    const miss = (tg.parts && tg.parts.length ? tg.parts : [tg])
      .filter(function(x){ return x.meets === false; });
    h += note('bad', 'ti-target-off',
      miss.map(function(x){
        return '<b>' + x.actual_pct + '%</b> ' + x.kind
             + ' vs <b>' + x.target_pct + '%</b>'; }).join(' &middot; ')
      + (bd.target_floor != null
          ? ' &middot; needs <b>' + _smoney(bd.target_floor) + '</b>' : ''),
      'At the price it sells for now this is under the target you set. '
      + (bd.target_floor != null
          ? 'It would have to sell at ' + _smoney(bd.target_floor) + ' to clear '
            + (miss.length > 1 ? 'both targets' : 'it') + '.' : ''));
  }

  // THE COST DRIFT. Kept, because it is the one warning that says a number
  // elsewhere on the screen is WRONG -- profit figures still subtract the cost
  // baked into the SKU name, and the supplier has moved since.
  const dr = r.drift || {};
  if(dr.delta != null && dr.delta !== 0){
    h += note('', 'ti-arrows-diff',
      'Cost was <b>' + _smoney(dr.cogs) + '</b>, now <b>' + _smoney(dr.landed)
      + '</b> &middot; profit '
      + (dr.delta > 0 ? 'overstated' : 'understated') + ' by <b>'
      + _smoney(Math.abs(dr.delta)) + '</b> a unit',
      'This SKU was created when a unit cost ' + _smoney(dr.cogs)
      + (dr.cogs_source === 'manual' ? ' (you set that by hand)'
                                     : ' (from the SKU name)')
      + '. The supplier now charges ' + _smoney(dr.landed) + ' delivered, and '
      + 'profit figures still subtract the old one.');
  }

  // UP-ONLY STOPPED A CUT. Worth its own line: "unchanged" and "the rules
  // wanted less and this SKU may not go down" look identical on a screen, and
  // only the second tells you how much margin the setting is protecting.
  if(d.direction_held && d.direction_floor != null){
    const cp = (r.current || {}).price;
    h += note('ok', 'ti-arrow-up',
      'Up only &middot; the rules would ask <b>' + _smoney(d.direction_floor)
      + '</b>, so nothing changed'
      + (cp != null ? ' &middot; keeping <b>'
                      + _smoney(cp - d.direction_floor) + '</b> a unit' : ''),
      'This SKU is set to move up only, so a floor below what it sells for '
      + 'today is not acted on. A cheaper supplier becomes margin rather than '
      + 'a discount. Change it on the Direction pill below.');
  }

  if(d.held){
    h += note('ok', 'ti-lock',
      'Held at <b>' + _smoney(d.held_at) + '</b> &middot; rules said '
      + _smoney(d.held_over),
      'Your rules and targets would have priced this at '
      + _smoney(d.held_over) + ' -- lower than the price you hold it at, so it '
      + 'was not used.');
  }else if(d.hold_exceeded != null){
    h += note('', 'ti-arrow-up',
      'Above your <b>' + _smoney(d.hold_exceeded) + '</b> hold',
      'The supplier has risen, so ' + _smoney(d.price) + ' is now above the '
      + _smoney(d.hold_exceeded) + ' you hold this at. A held price is a floor, '
      + 'not a fixed price, so it goes up rather than selling at a loss.');
  }else if(d.hold_capped){
    h += note('bad', 'ti-alert-triangle',
      'Hold <b>' + _smoney(d.hold_capped.hold) + '</b> vs ceiling <b>'
      + _smoney(d.hold_capped.ceiling) + '</b> &middot; ceiling won',
      'You hold this at ' + _smoney(d.hold_capped.hold) + ' but the maximum '
      + 'price is ' + _smoney(d.hold_capped.ceiling) + '. One of the two needs '
      + 'changing.');
  }
  h += '<div class="cc" style="font-size:10px;text-transform:uppercase;'
    +  'letter-spacing:.05em;margin:11px 0 4px">Suppliers</div>'
    +  _supTable(r);

  h += '<div class="cc" style="font-size:10px;text-transform:uppercase;'
    +  'letter-spacing:.05em;margin:11px 0 4px">Rules in force</div>'
    +  _rulePills(r);

  // HOW OLD THE READING BEHIND ALL OF THIS IS -- in the footer, where a
  // timestamp belongs.
  //
  // It was a sentence in the middle of the panel: "Decided on a reading 25
  // minutes old." It is not a finding, it is the provenance of every other
  // number above it, and provenance goes at the bottom in small type. It has to
  // stay somewhere, though: every figure on this panel is only as true as the
  // moment the supplier was last read, and readings go stale after 24 hours --
  // measured, every one of them was nine days old at one point today, which is
  // exactly the condition this line exists to make visible.
  if(d.inputs_age_mins != null){
    const mins = Math.round(d.inputs_age_mins);
    const old = mins > 1440;
    h += '<div style="font-size:9.5px;margin-top:9px;padding-top:6px;'
      +  'border-top:1px solid var(--line);color:'
      +  (old ? 'var(--warn)' : 'var(--ink4)') + '" title="'
      +  'Every figure here is worked out from the last successful reading of '
      +  'this SKU\'s suppliers. Readings older than a day are not used to '
      +  'price -- the SKU is held instead.">'
      +  '<i class="ti ti-clock" style="font-size:10px"></i> '
      +  (mins < 60 ? mins + ' min'
         : mins < 1440 ? Math.round(mins / 60) + ' hr'
         : Math.round(mins / 1440) + ' day') + ' old'
      +  (old ? ' &mdash; too old to price from' : '') + '</div>';
  }

  h += '</div></div>';
  return h;
}

/* Open or close one row's panel.
 *
 * "table-row", not "block". The panel is a <tr> now, and a <tr> set to display
 * block is lifted out of the table's layout: its single cell stops spanning the
 * columns and the panel collapses to the width of whatever is inside it. This
 * is the one line that has to know the panel is a table row.
 *
 * The row above it is marked open too, so it keeps the highlight while its
 * panel is showing -- otherwise an open panel appears to belong to nothing.
 */
function sourcingToggleDetail(id){
  const el = document.getElementById(id);
  if(!el) return;
  const open = (el.style.display === "none");
  el.style.display = open ? "table-row" : "none";
  const row = document.getElementById(id + "_r");
  if(row) row.classList.toggle("rp-sel", open);
}

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

/* EXTRA HANDLING DAYS, PER SKU.
 *
 *     "Label it 'Extra handling days' with a tooltip: 'Added on top of the
 *      calculated handling time. Use for slow suppliers.'"
 *
 * Zero by default. This is the only setting that makes a promise LONGER than
 * the supplier's own, so it says what it will cost you before you set it: a
 * longer handling time is a later delivery date on the listing.
 */
async function sourcingBuffer(sku, btn){
  const cur = (SRC_ROW_RULES[sku] || {}).handling_buffer_days || 0;
  _srcModal("Extra handling days",
    '<div style="font-size:12.5px;line-height:1.6">'
    + '<p>Added <b>on top of</b> the handling time the app works out. Use it for '
    + 'a supplier that does not dispatch when it says it will.</p>'
    + '<p class="cc" style="font-size:11.5px">The handling time already takes '
    + 'off the days your postage takes, because Amazon counts those separately. '
    + 'A supplier that dispatches in 3 days gives 1 day of handling; adding 2 '
    + 'here makes it 3, and the buyer is shown a date 2 days later than the '
    + 'supplier promised. That is a real cost to the listing, so leave it at 0 '
    + 'unless a supplier has actually let you down.</p>'
    + '<label class="cc" style="font-size:11.5px;display:block;margin-top:8px">'
    + 'Extra days (0 to 30)</label>'
    + '<input id="src_buf" type="number" min="0" max="30" step="1" value="'
    + (+cur) + '" style="width:110px;margin-top:4px">'
    + '</div>',
    async function(){
      const el = document.getElementById("src_buf");
      const v = el ? String(el.value).trim() : "";
      const j = await (await fetch("/sourcing/rules", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({sku: sku,
                        rule: {handling_buffer_days: v === "" ? 0 : v}})})).json();
      if(!j.ok){ toast(j.error || "Could not save"); return false; }
      toast("Extra handling: +" + (v === "" ? 0 : v) + " day(s)");
      await sourcingLoad(true);
      return true;
    });
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

async function sourcingPickerLoad(q){
  const host = document.getElementById("srcpick");
  if(!host) return;
  let j;
  try{ j = await (await fetch(_srcUrl("/sourcing/candidates","q="+encodeURIComponent(q||"")))).json(); }
  catch(e){ host.innerHTML = '<div class="cc" style="padding:14px;color:var(--red)">'+_sesc(String(e))+'</div>'; return; }
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

  let h = '<div style="border:1px solid #26303f;border-radius:8px;padding:12px;margin-bottom:12px">'
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
  try{
    const j = await (await fetch("/sourcing/enrol",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:_srcBody({sku:sku})})).json();
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
  const url = await uiPrompt("Paste the supplier's link for "+sku+".\n\neBay links are read "
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
    sourcingLoad(true);
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
    sourcingLoad(true);
  }catch(e){ toast(String(e)); }
}
