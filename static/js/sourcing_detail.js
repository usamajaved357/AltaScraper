// static/js/sourcing_detail.js -- the expanded row: cost split bar, metric strip, supplier table, rule pills; the stat cards. Moved word for word out of sourcing.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* IS A PRICE CHANGE BEING PROPOSED, and to what.
 *
 * ONE PLACE ANSWERS THIS. The row's price cell and the stacked bar's caption
 * both hang on it, and the two must never disagree: a bar captioned "at
 * proposed price 20.16" while the cell shows no move is the same fact told two
 * ways. The test is not "is there a decision" -- an 'update' whose price is a
 * penny off today's is a rounding artefact, not a move, so it is held to the
 * same 0.01 the cell has always used.
 *
 * Returns null when nothing is proposed, or {price, from, up}.
 */
function _proposedPrice(r){
  const d = (r || {}).decision || {}, cur = (r || {}).current || {};
  if(d.action !== 'update' || d.price == null || cur.price == null) return null;
  if(Math.abs(d.price - cur.price) < 0.01) return null;
  return {price: d.price, from: cur.price, up: d.price > cur.price};
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
function _stackBar(b, r){
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
  const prop = _proposedPrice(r);
  const other = +(b.postage_label || 0) + +(b.ads || 0);
  const profit = +(b.profit || 0);
  // THE VAT INSIDE THE PRICE, on a VAT-registered account. It is part of what
  // the price pays for, so without its own segment the bar no longer added up
  // to the price once profit started taking it out.
  const vat = +(b.vat || 0);
  const tot = cost + ref + close + other + vat + Math.max(0, profit);
  if(!(tot > 0)) return '';
  let h = '<div class="rp-sbar">'
    + '<div class="rp-sb-cost" style="flex:' + cost + '" title="What one unit '
    + 'costs you delivered from the supplier">' + _smoney(cost) + '</div>'
    + '<div class="rp-sb-ref" style="flex:' + ref + '" title="Amazon\'s '
    + 'referral fee on this price">' + _smoney(ref) + '</div>'
    + (vat > 0
        ? '<div style="flex:' + vat + ';background:var(--line2);color:var(--ink2)" '
          + 'title="VAT inside this price, at this account\'s rate — collected '
          + 'for HMRC">' + _smoney(vat) + '</div>'
        : '');
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
  // THE KEY MUST BE THE BAR'S OWN COLOURS. These were the *-bg TINTS -- the dark
  // backgrounds, not the segments -- so the legend square beside "Supplier" was
  // a nearly-black teal while the segment it named was blue. A key that does not
  // match the thing it explains is worse than no key.
  h += '</div><div class="rp-sbleg">'
    + '<span><span class="rp-sq" style="background:var(--bar-cost)"></span>Supplier</span>'
    + '<span><span class="rp-sq" style="background:var(--bar-fee)"></span>Referral</span>'
    + (close > 0
        ? '<span><span class="rp-sq" style="background:var(--bar-fee2)"></span>Closing</span>'
        : '')
    + (vat > 0
        ? '<span><span class="rp-sq" style="background:var(--line2)"></span>VAT</span>'
        : '')
    + (other > 0
        ? '<span><span class="rp-sq" style="background:var(--line2)"></span>'
          + 'Postage &amp; ads</span>'
        : '')
    + '<span><span class="rp-sq" style="background:'
    + (profit > 0 ? 'var(--bar-profit)' : 'var(--red)') + '"></span>'
    + (profit > 0 ? 'Profit' : 'Shortfall') + '</span>'
    // WHICH PRICE THIS BAR IS DRAWN AT.
    //
    // The bar is a picture of the PROPOSED price, not today's, and nothing on
    // it said so. When the repricer is holding still the two are the same
    // number and the question never comes up -- but the moment a move is
    // proposed, a reader has the row's price in their eye and a bar of
    // different figures under it, with no line joining them. The caption is
    // that line, and it only exists when there is something to join.
    + (prop
        ? '<span class="rp-sbprop">' + (prop.up ? '&#8599;' : '&#8600;')
          + ' at proposed price <b>' + _smoney(prop.price) + '</b></span>'
        : '')
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
  // Margin over the price AFTER VAT (b.vat, at the account's setting) -- the
  // definition target_status and every profit screen use, so a 20% target
  // that is met does not read 16.7% here.
  const _net = priced ? (+b.price - +(b.vat || 0)) : 0;
  const mgn = priced ? (_net > 0 ? (b.profit / _net) * 100 : null)
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
  // open panel.
  //
  // BUT THE PRICE HAS TO BE ON THE TILES THEMSELVES.
  //
  //     "the profit in the colors say something else and profit under it at the
  //      front of the supplier says something else and the profit on the
  //      product card is something else"
  //     "the cost price is same but profit numbers differ why"
  //
  // Three numbers, all called profit, all correct, about TWO DIFFERENT SELLING
  // PRICES -- and nothing on screen said so. On his SDS cutter the row read
  // -2.26 and this strip read 7.21 with the same 24.00 cost: the row is what it
  // earns TODAY at the 24.99 that is live, the strip is what it would earn at
  // the 35.87 his 30% target asks for and which is not on Amazon yet.
  //
  // It was in the TOOLTIP, which is the one place a number cannot be compared
  // with the number beside it. The label carries it now -- "Profit at £35.87"
  // against the table's "Profit now" -- so the two stop looking like a
  // contradiction and start looking like the before and after they are. That is
  // the heading's information without the heading, which he had removed.
  const at = priced ? _smoney(b.price) : ((r.current || {}).price != null
                                          ? _smoney(r.current.price) : null);
  // Every price-dependent tile takes this, so they cannot drift apart.
  const atLbl = at ? (priced ? ' at ' + at : ' now') : '';
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
           : (g.profit != null ? _smoney(g.profit) : '&mdash;'),
           'Profit' + atLbl,
           when + 'What is left per unit after what the stock cost and '
           + 'Amazon\'s fee'
           + (priced ? ' of ' + _smoney(b.fee)
              : (g.fee == null ? '' : ' of ' + _smoney(g.fee))))
    // THE TARGET IS SAID, NOT ONLY IMPLIED.
    //
    //     "the roi target when i set on a listing at bulk, i donot see on the
    //      listings that how much target is currently set for it"
    //
    // It was in the tooltip and nowhere else, so a target set in bulk across
    // sixty SKUs left no visible trace on any of them -- and a bare "34%" does
    // not say whether that is the number you asked for or the number you got.
    // The label carries it now, so the two sit one above the other.
    //
    // THE TILE KEEPS ITS GREEN, deliberately -- see the note above the strip.
    // An earlier pass here swapped in roiTone on the reasoning that a computed
    // tone was being discarded by accident. It was not: the table's own ROI
    // column already goes amber against the target, and a miss has its own red
    // notice carrying the price that would clear it. Three greens and a blue is
    // the pattern; a tile that changes colour breaks the set.
    + cell('rp-m2g', roi == null ? '&mdash;' : roi.toFixed(0) + '%',
           'ROI' + atLbl + (tgt != null ? ' &middot; want ' + tgt + '%' : ''),
           when + 'What you keep, as a share of the cash you put in'
           + (tgt != null ? '. You asked for ' + tgt + '%.' : '.'))
    + cell('rp-m2g', mgn == null ? '&mdash;' : mgn.toFixed(0) + '%',
           'Margin' + atLbl,
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
  // The price every "you keep" in this table is worked out at -- the same one
  // the tiles and the bar above use, so the whole panel speaks about one price.
  const _at = ((r.decision || {}).price != null)
            ? r.decision.price : ((r.current || {}).price);
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
      // A LOSS IS NOT GREEN. This coloured every readable figure with --ok,
      // so a supplier that would cost you £3.85 a sale was drawn in the same
      // green as one that earns you £6, in a column headed "You keep".
      // Measured on jack_uk: three suppliers were being shown that way.
      + '<td style="font-weight:600;color:'
      + (dead || s.profit == null ? 'var(--ink3)'
         : s.profit < 0 ? 'var(--red)' : 'var(--ok)') + '">'
      + (!dead && s.profit != null ? _smoney(s.profit) : '&mdash;') + '</td>'
      // Its OWN class, not the rules pills'. It sits above them in the panel
      // and it DELETES a supplier and its price history, where every .rp-rl
      // opens an editor -- sharing a class made "the first pill in the panel"
      // mean the × button, which is how a probe for the Floor editor ended up
      // opening a delete confirmation instead.
      + '<td style="width:18px"><button class="rp-xrm" '
      + 'onclick="event.stopPropagation();sourcingRemoveSource(' + Number(s.source_id)
      + ')" title="Remove this supplier link">&times;</button></td>'
      + '</tr>';
    // WHEN EBAY SAYS IT WILL ARRIVE, and why it was passed over -- both under
    // the row they belong to rather than in a column. A date is a sentence, not
    // a figure, and putting it in a cell would either truncate it or make every
    // other column narrower to fit it.
    // delivery_min/max, which _srcDeliveryLine reads -- it was handed
    // delivery_text, which it never looks at, so the window never showed
    // (repricer review, 30 Sep 2026).
    const line = _srcDeliveryLine({carrier: s.carrier, postage_text: s.postage_text,
                                   delivery_min: s.delivery_min,
                                   delivery_max: s.delivery_max,
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
    // NAMED WITH THE PRICE IT IS ABOUT. Every other figure in this panel is at
    // the decided price; this column is too, and saying so is what stops it
    // being read as a second, contradictory profit.
    + '<th title="What is left after Amazon and this supplier, at the price '
    + 'this panel is about' + (_at != null ? ' (' + _sesc(_smoney(_at)) + ')' : '')
    + '. The same price for every row, so the suppliers can be compared.">'
    + 'You keep' + (_at != null ? '<br><span style="font-weight:400;'
                                  + 'text-transform:none;letter-spacing:0">at '
                                  + _smoney(_at) + '</span>' : '')
    + '</th><th></th>'
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
  // A THIRD KIND OF FIGURE, AND IT OUTRANKS THE OTHER TWO. 'settled' is what
  // Amazon really took on THIS product, measured off its own orders -- not a
  // quote about what it would take, and not an average across everything the
  // account sells. It is the same number the Orders page reports, which is the
  // point: the two screens were disagreeing about one product.
  const settled = (d.fee_basis === 'actual');
  h += pill('Amazon fee',
            fr + ' <span style="font-weight:400;opacity:.7">'
               + (settled ? 'from your sales'
                          : (quoted ? 'quoted' : 'measured')) + '</span>',
            'sourcingGetFees(' + S + ')',
            (d.fee_detail
              || 'Amazon has not been asked about this product yet.')
            + (settled
                ? ' -- what Amazon actually took on this product, so it is the '
                  + 'same fee the Orders page reports.'
                : (quoted
                    ? " -- Amazon's own figure for this product."
                    : ' -- your measured rate, not Amazon\'s quote. Click to ask '
                      + 'Amazon.')),
            settled ? 'rp-g' : (quoted ? 'rp-g' : ''));
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
      + (tone === 'rp-g' ? 'var(--as-lit-22c55e-bg)' : tone === 'rp-y' ? 'var(--as-lit-f0b429-bg)'
         : tone === 'rp-r' ? 'var(--as-lit-ef4444-bg)' : 'var(--line2)') + '"></div></button>';
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
