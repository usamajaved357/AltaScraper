// static/js/sourcing_row.js -- drawing one Repricer row and its detail toggle. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

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
  // The same money-bar palette the stacked bar above this panel uses, so a fee
  // line and its segment are the same colour (dashboard.css --bar-*).
  const COL = {referral: 'var(--bar-fee)', closing: 'var(--bar-fee2)',
               fba: 'var(--ink3)'};
  let rows = '';
  (f.lines || []).forEach(function(l){
    const on = !!l.charged;
    rows += '<div style="display:flex;gap:8px;font-size:11.5px;padding:1.5px 0;'
         +  (on ? '' : 'opacity:.45') + '">'
         +  '<span style="min-width:178px;padding-left:8px;'
         +    (on ? 'border-left:2px solid ' + (COL[l.key] || 'var(--bar-cost)')
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

/* ARMED? WHICH WAY? -- readable down the table without opening a row.
 *
 *     "I WANT SOME SORT OF INDICATION AND SYMBOL WHICH TELLS ME WHAT IS THE
 *      RULE SET ON THE REPRICER DOWN ONLY, UP AND DOWN OR WHAT ... A SYMBOL
 *      ... THAT IF THE ITEM IS ARMED" (owner, 30 Sep 2026)
 *
 * Two marks beside the status dot:
 *   bolt       green = armed (live), dim bolt-off = dry run
 *   direction  up only / both ways / = the floor -- from the SKU's own rule,
 *              "up_only" when unset, exactly what domain/sourcing.py uses
 *              (rule.get("direction") or "up_only").
 */
const RP_DIR_MARK = {
  up_only:     ['ti-arrow-up',        'rp-g', 'Up only: the price can only ever go up'],
  up_and_down: ['ti-arrows-vertical', 'rp-b', 'Up and down: the price follows the supplier both ways'],
  match_floor: ['ti-equal',           'rp-y', 'Matches the floor: the price sits exactly on the calculated floor'],
};
function _rpRuleMarks(r){
  const live = (r.mode === "live");
  const dir = String((r.rule || {}).direction || "up_only");
  const dm = RP_DIR_MARK[dir] || RP_DIR_MARK.up_only;
  return '<i class="ti ' + (live ? 'ti-bolt rp-g' : 'ti-bolt-off rp-d') + ' rp-mark" role="img" '
    + 'aria-label="' + (live ? 'Armed' : 'Dry run') + '" title="'
    + (live ? 'Armed: auto-pricing can change this SKU on Amazon'
            : 'Dry run: not armed, nothing reaches Amazon') + '"></i>'
    + '<i class="ti ' + dm[0] + ' ' + dm[1] + ' rp-mark" role="img" aria-label="'
    + _sesc(dm[2]) + '" title="' + _sesc(dm[2]) + '"></i>';
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
  // OUR ASIN, OR NONE -- never the draft's.
  //
  // This used to fall back to it.asin when Amazon had no record of the SKU,
  // and that is the COMPETITOR. The catalogue is asked with include_drafts so
  // a never-sent SKU still gets a PICTURE; a draft's asin is the product the
  // listing was researched from, which CLAUDE.md Rule 1 is explicit about --
  // "the ASIN in the SKU format is a COMPETITOR REFERENCE ... It is not the
  // target listing."
  //
  // Measured on jack_uk: six rows were showing somebody else's ASIN as the
  // seller's own, each one a link straight to that competitor's page, on a
  // row headed with the seller's product name. That is the app telling you
  // you own something you do not.
  //
  // So only what Amazon actually answered with is shown. Where there is none,
  // the row says so -- see the mark below, which is more useful than a wrong
  // ASIN in any case: it means Amazon has no such SKU, and nothing on that
  // row can be pushed.
  const asin = String(cur.asin || "");
  const draftAsin = (!asin && it.asin) ? String(it.asin) : "";
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
  // UNKNOWN IS NOT UNAVAILABLE. A link eBay did not describe this time is
  // counted apart from one that is out of stock or ended, because the
  // repricer holds on the first and acts on the second (repricer review,
  // 30 Sep 2026).
  const nUnk = (r.options || []).filter(function(o){
    return o.state === 'unknown';
  }).length;
  const nDead = nOpt - nUse - nUnk;
  if(nOpt && nUse < nOpt)
    flags += '<span class="rp-tag" style="background:var(--warn-bg);'
          +  'color:var(--warn)" title="'
          +  (nDead ? nDead + ' of this SKU\'s supplier links cannot be bought '
                    + 'from right now (out of stock or ended). ' : '')
          +  (nUnk ? nUnk + ' could not be read this time -- unknown, not out '
                   + 'of stock. ' : '')
          +  'Open the row to see which, and why.">' + nUse + '/' + nOpt + '</span> ';

  // THE SKU IS IN THE TOOLTIP, NOT THE COLUMN. It is the identifier everything
  // else uses -- the upload template, the arm call, the log -- so it cannot go
  // away; but 10.39_3Days_B0F6LQ1S93 tells nobody WHICH PRODUCT this is, and
  // that is what a column three inches wide has to answer. So the name is
  // shown, the SKU is one hover away, and the panel prints it in full.
  h += '<td><div class="rp-nm" title="' + _sesc((it.title || "") + "\n" + r.sku) + '">'
    + _sesc(it.title || r.sku) + '</div>'
    + '<div style="display:flex;gap:3px;align-items:center;margin-top:1px">'
    // THE DOMAIN FOLLOWS THE MARKETPLACE. A UK ASIN opened on amazon.com is
    // either a different product or a 404, and the link was hardcoded to .co.uk
    // for every account -- including the two that sell in dollars.
    + (asin
        ? '<a class="rp-asin" href="https://www.amazon.' + _srcAmzHost()
          + '/dp/' + _sesc(asin)
          + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" '
          + 'title="Open this listing on Amazon">' + _sesc(asin) + '</a>'
        : '<span class="rp-d" style="font-size:9px" title="'
          + (draftAsin
              ? 'Amazon has no record of this SKU. It was researched from '
                + _sesc(draftAsin) + ', which is a COMPETITOR’s product '
                + 'and not yours -- so it is not shown as an ASIN here.'
              : 'Amazon has no ASIN for this SKU.')
          + '">' + _sesc(r.sku) + '</span>')
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
  const prop = _proposedPrice(r);
  if(prop){
    h += '<span class="rp-was">' + _smoney(prop.from) + '</span> '
      +  '<span class="rp-p ' + (prop.up ? 'rp-g' : 'rp-y') + '">'
      +  _smoney(prop.price) + '</span>';
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
    + '<td class="rp-marks">' + _rpRuleMarks(r)
    + '<span class="rp-dot ' + dot[0] + '" title="' + _sesc(dot[1])
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
    // WHAT WAS RESEARCHED, NAMED AS SUCH. When Amazon has no ASIN for this SKU
    // the draft still carries the competitor it was modelled on, and that is
    // worth knowing -- but only if it is labelled as someone else's product.
    // Shown as plain text, never as a link: a link here reads as "your
    // listing", which is exactly the mistake this replaced.
    +  (draftAsin
        ? ' &middot; <span style="color:var(--warn)">Amazon has no ASIN for '
          + 'this SKU</span> &middot; researched from ' + _sesc(draftAsin)
          + ' (a competitor)'
        : '')
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
  h += _stackBar(b, r) + _metStrip(r);

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
