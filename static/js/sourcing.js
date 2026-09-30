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
// Bumped by every sourcingLoad; only the newest one's reply is drawn.
let SRC_LOAD_SEQ = 0;

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
    p.push("account=" + encodeURIComponent(CUR_ACCOUNT.id));
  if(typeof WS_MARKET !== "undefined" && WS_MARKET)
    p.push("marketplace=" + encodeURIComponent(WS_MARKET));
  return p.join("&");
}
function _srcUrl(path, extra){
  const q = [_srcScope(), extra || ""].filter(Boolean).join("&");
  return path + (q ? (path.indexOf("?") >= 0 ? "&" : "?") + q : "");
}
function _srcBody(o, scope){
  const b = Object.assign({}, o || {});
  const sc = scope || _srcScopeNow();
  if(sc.id) b.id = sc.id;
  if(sc.marketplace) b.marketplace = sc.marketplace;
  return JSON.stringify(b);
}
/* The account + marketplace on screen NOW, as a value that will not change.
 *
 * A BULK LOOP TAKES THIS ONCE, before its first write, and passes it to every
 * _srcBody call. Reading CUR_ACCOUNT afresh per SKU meant switching account
 * mid-loop armed -- or re-ruled -- the new account's same-SKU listings
 * (master audit S1, 28 Sep 2026). */
function _srcScopeNow(){
  // THE SHARED ANSWER when it is loaded (screenstate.js screenScope: account,
  // marketplace AND the switch generation, so A -> B -> A is caught too). The
  // fallback below is only for this file loaded on its own, as tests do.
  if(typeof screenScope === "function"){
    const sc = screenScope();
    return {id: sc.acct, marketplace: sc.mkt, gen: sc.gen, _shared: sc};
  }
  return {
    id: (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id)
        ? String(CUR_ACCOUNT.id) : "",
    marketplace: (typeof WS_MARKET !== "undefined" && WS_MARKET) ? String(WS_MARKET) : ""
  };
}
/* Is the screen still on the scope a loop started in? */
function _srcStillIn(scope){
  if(scope && scope._shared && typeof screenStillIn === "function")
    return screenStillIn(scope._shared);
  const now = _srcScopeNow();
  return now.id === scope.id && now.marketplace === scope.marketplace;
}
const _SRC_MOVED = "stopped — the account or marketplace was changed part-way";
/* What a bulk loop that STOPPED says -- counted, and apart from the refusals,
 * so "N refused" and "the rest were set" stay true (UI review, Milestone 6). */
function _srcStopNote(stopped){
  return stopped ? ("\n\nStopped: the account or marketplace was changed part-way, "
                    + "so " + stopped + " were not attempted. Open it again to finish.")
                 : "";
}

function _sesc(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
// An argument for an inline onclick. Single-quoted for JS, then escaped for the
// attribute -- see the same helper in users.js and the bug that made it
// necessary: JSON.stringify closes the attribute it is pasted into.
// ONE escaper for a value inside an inline handler: jsArg, in users.js (Rule 12,
// Milestone 2). This name is kept for its callers.
function _sarg(s){ return jsArg(s); }
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
  // The account and marketplace this reply is for: one that lands after a
  // switch is not painted (master audit S5). _srcScopeNow/_srcStillIn are this
  // screen's own copy of screenScope, kept for its bulk loops.
  const _sc = _srcScopeNow();
  // AND ONLY THE NEWEST LOAD PAINTS: two quick saves start two reloads, and
  // the older reply landing last redrew the older state (repricer bug hunt).
  const _seq = ++SRC_LOAD_SEQ;
  try{ j = await (await fetch(_srcUrl("/sourcing/list"))).json(); }
  catch(e){
    if(!_srcStillIn(_sc) || _seq !== SRC_LOAD_SEQ) return;
    // A quiet refresh that fails leaves what is on screen alone and says so in
    // a toast. Replacing a working table with an error because a background
    // refresh timed out would be worse than the stale table.
    if(quiet){ toast("Could not refresh: " + String(e)); return; }
    body.innerHTML = '<div class="cc" style="padding:16px;color:var(--red)">'
      + 'Could not load: ' + _sesc(String(e)) + '</div>';
    return;
  }
  if(!_srcStillIn(_sc) || _seq !== SRC_LOAD_SEQ) return;
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
  // Read into a local and checked BEFORE it is kept: assigned first, a late
  // reply put A's auto-pricing on/off into B until B's load finished.
  // FROM THIS SAME REPLY (master_enabled, the value /sourcing/master reads).
  // A second fetch that failed set it to false, so the toolbar said
  // "Auto-pricing: off" when the real state was simply not known (repricer
  // review, 30 Sep 2026); one reply cannot disagree with itself.
  SRC_MASTER = !!j.master_enabled;
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
  const _sc = _srcScopeNow();
  // A FAILED CHECK IS SAID, never an empty strip: empty reads as "no supplier
  // is out of stock", which is the one thing a failure cannot tell you
  // (repricer review, 30 Sep 2026).
  const _failNote = '<div class="cc" style="font-size:11.5px;color:var(--warn)">'
    + '<i class="ti ti-alert-triangle"></i> Could not check supplier alerts \u2014 refresh to try again.</div>';
  try{ j = await (await fetch(_srcUrl("/sourcing/alerts"))).json(); }
  catch(e){ if(_srcStillIn(_sc)) host.innerHTML = _failNote; return; }
  if(!_srcStillIn(_sc)) return;        // another account's alerts (audit S5)
  if(!j || !j.ok){ host.innerHTML = _failNote; return; }
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

// sourcingMaster ... _srcTargetBox: moved to static/js/sourcing_actions.js (Milestone 4), loaded right after this file.
// _srcModal ... sourcingUploadReport: moved to static/js/sourcing_dialogs.js (Milestone 4), loaded right after this file.
// _spark ... srcChart: moved to static/js/sourcing_chart.js (Milestone 4), loaded right after this file.
// _proposedPrice ... _statCards: moved to static/js/sourcing_detail.js (Milestone 4), loaded right after this file.
// sourcingFilter ... sourcingShippingPolicy: moved to static/js/sourcing_menu.js (Milestone 4), loaded right after this file.
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
    h += '<div class="cc" style="font-size:12px;padding:10px;border:1px dashed var(--line2);border-radius:6px">'
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
    // "NOW", because the panel underneath answers the other question.
    //
    //     "the cost price is same but profit numbers differ why"
    //
    // These two columns are today's sale, at the price that is live on Amazon.
    // The open panel's tiles are the sale that WOULD happen at the price the
    // rules ask for. Same cost, different price, so different profit -- and
    // with both called plain "Profit" the pair read as a contradiction rather
    // than as a before and an after.
    +  '<th title="What is left per unit after Amazon, postage and ads, at the '
    +  'price this SKU sells for TODAY. The tiles in the open panel answer the '
    +  'same question about the price the rules would set instead.">Profit now</th>'
    +  '<th title="Today&#39;s profit as a share of the cash you put in">ROI now</th>'
    +  '<th title="What this SKU&#39;s cheapest supplier has been charging">Trend</th>'
    +  '<th style="width:58px" title="Armed (bolt) or dry run, which way the price may move (up only / both ways / = floor), and the status dot">Rule</th>'
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

// SRC_SEL ... sourcingUnenrolSelected: moved to static/js/sourcing_bulk.js (Milestone 4), loaded right after this file.
// _srcShort ... sourcingToggleDetail: moved to static/js/sourcing_row.js (Milestone 4), loaded right after this file.
// sourcingDefaultDirection ... sourcingRemoveSource: moved to static/js/sourcing_row_actions.js (Milestone 4), loaded right after this file.