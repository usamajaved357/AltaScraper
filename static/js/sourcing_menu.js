// static/js/sourcing_menu.js -- filters, the alert bar, the more menu, defaults, sheet uploads and push now. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

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
    // Same "is a move proposed" test as the row and the bar -- _proposedPrice
    // -- narrowed to the downward ones. The threshold stays > 0.01 rather than
    // the helper's >= : a penny is not a cut worth warning about, and this
    // count is the one that gets read as "22 SKUs would be cut".
    const p = _proposedPrice(r), ru = r.rule || {};
    return p && (p.from - p.price) > 0.01
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
    + '<a class="rp-mi" href="' + esc(_srcUrl("/sourcing/template.csv")) + '" onclick="_srcMoreClose()" '
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
    // THE ONLY BUTTON IN THE APP THAT CHANGES A LIVE PRICE.
    //
    //     "the set roi should be able to do the job for the prices"
    //
    // Before this, nothing did. The engine decided correctly and the decision
    // went nowhere: /sourcing/apply existed and no button called it, and the
    // four-hourly job that was meant to was registered in a module the running
    // app never loads. So a target could be set, the screen could show the
    // price it wanted, and Amazon would never hear about it.
    //
    // It takes no shortcut around the gates -- master switch on, SKU armed,
    // minimum price set, four hours since that SKU last moved -- it just runs
    // them now instead of waiting. Same call the timer makes.
    + row('ti-cloud-upload', 'Push changes now', 'sourcingPushNow(this)',
          'Sends every armed SKU whose price, stock or handling time is wrong '
          + 'to Amazon, right now, instead of waiting for the next four-hourly '
          + 'run. Nothing that is already correct is touched, and nothing that '
          + 'is not armed is sent.')
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
    // STOCK, kept apart from the two "new SKUs start at" rows below on purpose.
    //
    //     "there should be a separate default stock setting which is activated
    //      along with the auto pricing being on"
    //
    // Those two are written onto a SKU at enrolment and never move again,
    // because they are pricing decisions. This is not a pricing decision, it is
    // one number saying how much stock you hold, so it is read live and applies
    // to everything tracked -- except a SKU given its own figure. It sits with
    // "Postage takes" because both describe how you actually operate, rather
    // than what a new row should inherit.
    + row('ti-package', 'Keep stock at', 'sourcingDefaultStock()',
          'How many units every tracked SKU is set to on Amazon. Applies to '
          + 'everything you track, not just new SKUs -- a SKU given its own '
          + 'figure keeps it. It only reaches Amazon while auto-pricing is on.',
          ((j.default_stock != null ? j.default_stock : 3) + ' units'))
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
  // The account AND marketplace this was opened for, noted before the dialog;
  // the write names them and is refused if the screen moved (confirm-then-write).
  const _sc0 = _srcScopeNow();
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
    // The file itself goes too, so the Upload history keeps the original.
    const _file = (typeof uphFileForUpload === "function") ? await uphFileForUpload(f) : null;
    if(!_srcStillIn(_sc0)){
      if(typeof toast === "function") toast("The account or marketplace changed while this was open, so nothing was done.");
      return;
    }
    j = await (await fetch("/sourcing/minprice_upload", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: _srcBody({rows: filled, arm: !!arm, file: _file}, _sc0)})).json();
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
/* Send every armed SKU's changes to Amazon now.
 *
 * ASKS FIRST, and names the number. This is the one action on the page that
 * edits live listings, and "Push changes now" in a menu does not convey how
 * many prices are about to move. The count comes from the same "would change"
 * figure the stat cards show, so the question and the screen cannot disagree.
 */
async function sourcingPushNow(btn){
  // The account AND marketplace this was opened for, noted before the dialog;
  // the write names them and is refused if the screen moved (confirm-then-write).
  const _sc0 = _srcScopeNow();
  if(!SRC_MASTER){
    await uiAlert(
      "Nothing is sent to Amazon while auto-pricing is off. Turn it on with "
      + "the switch at the top of this page, then push again.",
      {title: "Auto-pricing is off"});
    return;
  }
  // r.mode, which is what every other armed-count on this page reads
  // (sourcingFilter, the stat cards). r.enrollment.mode is not a field.
  const armed = (SRC_ROWS || []).filter(function(r){
    return r.mode === "live";
  }).length;
  if(!armed){
    await uiAlert(
      "Every tracked SKU is still in dry run, so there is nothing to send. "
      + "Arm a SKU from its panel once you are happy with the price it would "
      + "set — it needs a minimum price first.",
      {title: "Nothing is armed"});
    return;
  }
  const ok = await uiConfirm(
    armed + (armed === 1 ? " SKU is armed" : " SKUs are armed") + ". Any of "
    + "them whose price, stock or handling time is wrong will be corrected on "
    + "Amazon now. Anything already correct is left alone, and a SKU changed "
    + "in the last four hours is skipped.",
    {title: "Send changes to Amazon?", ok: "Push now"});
  if(!ok) return;
  if(btn){ btn.disabled = true; }
  try{
    if(!_srcStillIn(_sc0)){
      if(typeof toast === "function") toast("The account or marketplace changed while this was open, so nothing was done.");
      return;
    }
    const j = await (await fetch("/sourcing/apply", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: _srcBody({}, _sc0)})).json();
    if(!j.ok){ toast(j.error || "Could not push"); return; }
    // SAY WHAT HAPPENED TO ALL OF THEM, not just the ones that worked. A push
    // that sends two and is refused on three has to read as that, or the three
    // are never looked into.
    const bits = [];
    bits.push((j.pushed || 0) + " sent");
    if(j.rejected) bits.push(j.rejected + " refused by Amazon");
    if(j.note) bits.push(j.note);
    toast(bits.join(" · "));
    await sourcingLoad(true);
  }catch(e){ toast("Failed: " + ((e && e.message) || e)); }
  finally{ if(btn){ btn.disabled = false; } }
}

/* How many units every tracked SKU is kept at.
 *
 *     "there should be a separate default stock setting which is activated
 *      along with the auto pricing being on"
 *
 * SEPARATE FROM THE PRICE, and that is the point of it. A run whose only real
 * change is putting stock back to three no longer touches the price at all
 * (domain/source_apply.build_patches), so this setting can do its job on a day
 * when nothing about the price needs to move.
 *
 * The floor of 1 is enforced on the server too, and for a reason worth saying
 * out loud rather than only validating: 0 is not a stock level, it is a
 * different decision. Sending 0 tells Amazon the product is unavailable, which
 * is what the out-of-stock rule does -- having first checked the supplier.
 * Reaching the same end by typing 0 into a settings box would take every armed
 * listing down at once, from a control that does not look like it could.
 */
async function sourcingDefaultStock(){
  let cur = 3;
  try{
    const g = await (await fetch("/sourcing/default_stock" + _srcUrl(""))).json();
    if(g && g.ok && g.quantity != null) cur = g.quantity;
  }catch(e){ /* the default stands */ }
  _srcModal("Keep stock at",
    '<div style="font-size:12.5px;line-height:1.6">'
    + '<p>Every tracked SKU is set to this many units on Amazon, so a listing '
    + 'that has quietly gone to zero comes back up on the next run.</p>'
    + '<p class="cc" style="font-size:11.5px">Unlike the two &ldquo;new SKUs '
    + 'start at&rdquo; settings, this one applies to <b>everything you already '
    + 'track</b> &mdash; change it and every SKU follows. A SKU you have given '
    + 'its own figure keeps that figure.</p>'
    + '<p class="cc" style="font-size:11.5px">It reaches Amazon only while '
    + 'auto-pricing is on, and only for SKUs you have armed. To take a listing '
    + 'down, leave that to the out-of-stock rule &mdash; it checks the supplier '
    + 'first, which is why 1 is the lowest this can be set to.</p>'
    + '<label class="cc" style="font-size:11.5px;display:block;margin-top:8px">'
    + 'Units to keep (1 to 999)</label>'
    + '<input id="src_stk" type="number" min="1" max="999" step="1" value="'
    + (+cur) + '" style="width:110px;margin-top:4px">'
    + '</div>',
    async function(){
      const el = document.getElementById("src_stk");
      const jr = await (await fetch("/sourcing/default_stock", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: _srcBody({quantity: el ? el.value : ""})})).json();
      if(!jr.ok){ toast(jr.error || "Could not save"); return false; }
      toast(jr.note || "Saved");
      await sourcingLoad(true);
      return true;
    });
}

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
