/* static/js/orders_panel.js -- one order, opened, in about a third of the room.
 *
 *     "The expanded order detail takes ~600px+ of vertical height with separate
 *      'WHAT WAS ORDERED', 'WHERE TO BUY IT', 'WHAT IT EARNED' and 'DELIVERY'
 *      sections stacked vertically. The new layout fits all of that into ~300px
 *      using the same visual language as the Sourcing page."
 *
 * ═══ NOTHING NEW IS FETCHED AND NOTHING NEW IS WORKED OUT ═══════════════════
 *
 * Every figure below comes out of the SAME `d` the old panel was built from --
 * d.order, d.items, d.sources, d.breakdown -- fetched by the same call, from
 * the same route. This file rearranges; it does not compute. In particular the
 * profit, the fee, the margin and the ROI are the server's, because the row
 * above the panel shows those same four and a panel that worked them out again
 * would be able to disagree with the row it is attached to (CLAUDE.md Rule 12).
 *
 * ═══ WHAT WAS DROPPED, AND WHY EACH ONE IS SAFE ════════════════════════════
 *
 * "WHAT WAS ORDERED" as a section: the row above already carries the picture,
 * the title and the SKU, and it is two inches away. The parts of it that are
 * NOT on the row -- the ASIN link, and the cancellation explanation for the two
 * statuses that cost money to misread -- are kept, on one line.
 *
 * The five-column "WHAT IT EARNED" table becomes one flow line, because on a
 * single-item order (which is nearly all of them) a table with headers is five
 * headings over five numbers. A MULTI-ITEM order still gets the table: the flow
 * line can only show one sum, and hiding a second product's numbers to save
 * space would be losing data rather than compressing it.
 *
 * "DELIVERY" as three labelled rows becomes one line. Same three facts.
 *
 * ═══ WHAT IS NOT HERE THAT THE BRIEF ASKS FOR ══════════════════════════════
 *
 * "Ship now", "Print label" and "Invoice". This app has no shipping flow, no
 * label endpoint and no invoice generator -- there is no route for any of the
 * three. Three buttons that did nothing would be worse than their absence, and
 * on an order screen "Ship now" that silently fails is the worst of them
 * (Rule 4). The two actions that DO exist are here.
 */

/* The stacked bar: what the stock cost, what Amazon took, what is left.
 *
 * PROPORTIONAL, so it is read at a glance -- and it is drawn ONLY when all
 * three parts are known. A bar with a missing segment silently redistributes
 * the width across the others, which makes an order with no recorded cost look
 * like the most profitable one on the screen. */
function _opBar(t, cur){
  const cost = _opNum(t.cogs), fee = _opNum(t.fees), profit = _opNum(t.profit);
  if(cost === null || fee === null || profit === null) return "";
  if(!(cost + fee + Math.abs(profit) > 0)) return "";
  const seg = function(cls, v, label){
    if(v <= 0) return "";
    return '<div class="' + cls + '" style="flex:' + v + '" title="' + _oEsc(label)
         + '">' + _oEsc(_oMoney(v, cur)) + '</div>';
  };
  return '<div class="o-bar">'
    + seg("bar-cost", cost, "What the stock cost you")
    + seg("bar-fee", fee, "What Amazon took")
    + (profit >= 0
        ? seg("bar-profit", profit, "What is left")
        : '<div class="bar-loss" style="flex:' + Math.abs(profit)
          + '" title="This order lost money">' + _oEsc(_oMoney(profit, cur))
          + '</div>')
    + '</div>';
}

function _opNum(v){
  if(v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

/* The four cards. Every one of them is a figure the ROW also shows, so they
 * cannot disagree with it -- they are here because the row's version is 11px in
 * a 9% column and this is the reading you came in for. */
function _opCards(r, t, cur, o){
  const card = function(value, label, tone, title){
    return '<div class="o-card' + (tone ? " " + tone : "") + '" title="'
      + _oEsc(title || "") + '">'
      + '<div class="o-card-v">' + value + '</div>'
      + '<div class="o-card-l">' + _oEsc(label) + '</div></div>';
  };
  const dash = '<span class="cc">—</span>';
  const profit = _opNum(t.profit);
  const paid = _opNum(t.revenue);
  const pct = function(v){
    const n = _opNum(v);
    return n === null ? dash : _oEsc(n.toFixed(1) + "%");
  };
  // THE FOURTH CARD IS NOT "HANDLING", and that is a correction to the brief
  // rather than an omission. An ORDER carries no handling time: handling_days
  // is a setting on the LISTING, and nothing on an order row or in the order
  // detail holds one. MEASURED in a browser -- the card rendered a dash on
  // every order, which is a card that can never say anything.
  //
  // What the order DOES carry is Amazon's post-by date, and days-left is the
  // one number on this screen that costs money if it is ignored: dispatch after
  // it and the order is late, which is a metric hit on the account. Same
  // territory the brief wanted the card for, from data that exists.
  const post = _opDaysLeft(o.ship_by);
  return '<div class="o-cards">'
    + card(profit === null ? dash : _oEsc(_oMoney(profit, cur)),
           paid === null ? "Profit" : ("Profit at " + _oMoney(paid, cur)),
           profit === null ? "" : (profit < 0 ? "bad" : "good"),
           profit === null
             ? "No cost is recorded for part of this order, so there is no profit figure — it is left blank rather than counting the missing cost as nothing."
             : "What the buyer paid, less Amazon's cut, less what the stock cost.")
    + card(pct(r.roi_pct), "ROI", "",
           "Profit as a share of what the stock cost — whether the stock was worth buying.")
    + card(pct(r.margin_pct), "Margin", "",
           "Profit as a share of what the buyer paid — whether the price is any good.")
    + card(post.text === "" ? dash : _oEsc(post.text), post.label, post.tone,
           post.title)
    + '</div>';
}

/* How long is left to post this, from Amazon's ship-by date.
 *
 * Returns {text, label, tone, title}. Absent rather than guessed when Amazon
 * gave no date -- an order with no deadline shown is better than one with an
 * invented deadline, and "overdue" is the single most expensive thing this
 * panel could get wrong. */
function _opDaysLeft(shipBy){
  const out = {text: "", label: "Post by", tone: "",
               title: "Amazon did not give a dispatch deadline for this order."};
  if(!shipBy) return out;
  let due;
  try{ due = new Date(shipBy); }catch(e){ return out; }
  if(!due || isNaN(due.getTime())) return out;
  // WHOLE DAYS, from midnight to midnight -- "1.4 days" is not how a deadline
  // is read, and rounding the hours would make a deadline this afternoon and
  // one tomorrow morning both say "1".
  const d0 = new Date(); d0.setHours(0, 0, 0, 0);
  const d1 = new Date(due.getFullYear(), due.getMonth(), due.getDate());
  const days = Math.round((d1 - d0) / 86400000);
  const when = (typeof _oWhen === "function") ? _oWhen(shipBy) : String(shipBy);
  out.title = "Amazon counts this order late if it is not dispatched by "
            + when + ".";
  if(days < 0){ out.text = "overdue"; out.tone = "bad"; out.label = "Post by"; }
  else if(days === 0){ out.text = "today"; out.tone = "bad"; }
  else if(days === 1){ out.text = "1 day"; out.tone = "good"; }
  else { out.text = days + " days"; out.tone = "good"; }
  return out;
}

/* The two actions that actually exist. See the note at the top of this file for
 * the three the brief asks for that do not. */
function _opActions(r, d, items){
  const btns = [];
  // AMAZON'S OWN ORDER PAGE. Seller Central's order detail lives at a fixed
  // path per marketplace; the domain table is listings.js's, borrowed rather
  // than copied (Rule 12), and the button is simply omitted if that file has
  // not loaded rather than pointing somewhere plausible and wrong.
  const sc = _opSellerCentral(r.order_id, r.marketplace);
  if(sc){
    btns.push('<a class="o-btn primary" href="' + _oEsc(sc) + '" target="_blank"'
      + ' rel="noopener" onclick="event.stopPropagation()"'
      + ' title="Open this order in Seller Central">'
      + '<i class="ti ti-external-link"></i> Amazon order</a>');
  }
  // THE PRODUCT, on Amazon. One button per item would be a row of buttons on a
  // multi-item order, so it is only offered when there is one thing to open.
  if(items.length === 1 && items[0].asin && typeof _ordDp === "function"){
    btns.push('<a class="o-btn" href="' + _oEsc(_ordDp(items[0].asin, r.marketplace))
      + '" target="_blank" rel="noopener" onclick="event.stopPropagation()"'
      + ' title="Open the product on Amazon">'
      + '<i class="ti ti-package"></i> Product page</a>');
  }
  // BUY IT FROM THE SUPPLIER. The link is the one the sources block already
  // marked cheapest -- not re-sorted here, or this button and the table under
  // it could name different suppliers.
  const best = _opBestSource(d, items);
  if(best && best.url){
    btns.push('<a class="o-btn" href="' + _oEsc(best.url) + '" target="_blank"'
      + ' rel="noopener" onclick="event.stopPropagation()"'
      + ' title="Buy this from ' + _oEsc(best.label || "the cheapest supplier")
      + '"><i class="ti ti-shopping-cart"></i> Buy from supplier</a>');
  }
  return btns.length ? '<div class="o-acts">' + btns.join("") + '</div>' : "";
}

function _opSellerCentral(orderId, market){
  if(!orderId) return "";
  let tld = "co.uk";
  try{ if(typeof _amzTld === "function") tld = _amzTld(market); }
  catch(e){ return ""; }
  return "https://sellercentral.amazon." + tld
       + "/orders-v3/order/" + encodeURIComponent(orderId);
}

/* The cheapest supplier across the order's items, as the sources block already
 * flagged it. Never re-derived by comparing prices here. */
function _opBestSource(d, items){
  const src = d.sources || {};
  let best = null;
  items.forEach(function(it){
    const opts = ((src[it.sku] || {}).options) || [];
    const c = opts.filter(function(o){ return o.cheapest; })[0];
    if(c && !best) best = c;
  });
  return best;
}

/* Buyer paid -> Amazon fee -> cost = profit, on one line.
 *
 * REPLACES A FIVE-COLUMN TABLE, and only where a table was overkill: a
 * single-line order. The multi-item case keeps the table -- see the note at the
 * top of this file. */
function _opFlow(t, cur){
  const step = function(v, label, cls){
    const n = _opNum(v);
    return '<div class="o-step' + (cls ? " " + cls : "") + '">'
      + '<div class="o-step-v">' + (n === null ? '<span class="cc">—</span>'
                                               : _oEsc(_oMoney(v, cur))) + '</div>'
      + '<div class="o-step-l">' + _oEsc(label) + '</div></div>';
  };
  const arrow = '<div class="o-arrow">→</div>';
  const eq = '<div class="o-arrow">=</div>';
  return '<div class="o-flow">'
    + step(t.revenue, "Buyer paid")
    + arrow
    + step(t.fees === null || t.fees === undefined ? null : -Math.abs(_opNum(t.fees) || 0),
           "Amazon fee", "neg")
    + arrow
    + step(t.cogs_complete === false ? null
           : (t.cogs === null || t.cogs === undefined
              ? null : -Math.abs(_opNum(t.cogs) || 0)),
           "Cost", "neg")
    + eq
    + step(t.profit, "Profit",
           (_opNum(t.profit) !== null && _opNum(t.profit) < 0) ? "bad" : "good")
    + '</div>';
}

/* Post by / arrive by / going to, on one line. Three facts, one row, and each
 * one absent rather than blank when Amazon did not say. */
function _opDelivery(o){
  const bits = [];
  if(o.ship_by) bits.push("Post by " + _oWhen(o.ship_by));
  if(o.deliver_by) bits.push("Must arrive by " + _oWhen(o.deliver_by));
  if(o.region) bits.push("Going to " + o.region);
  if(!bits.length) return "";
  return '<div class="o-deliv" title="Amazon counts a dispatch late after the '
    + 'post-by date, and the arrive-by date is what the buyer was promised.">'
    + '<i class="ti ti-truck-delivery"></i> ' + _oEsc(bits.join(" · ")) + '</div>';
}

/* The pills along the bottom: what this panel is assuming, in three words each.
 *
 * THEY EXIST BECAUSE THE FIGURES ABOVE ARE NOT ALL THE SAME KIND OF FACT. An
 * estimated fee and a settled one are both printed as "£5.59", and only this
 * says which you are looking at. */
function _opBadges(t, d, items, cur){
  const out = [];
  const settled = (t.fees_basis === "actual");
  out.push('<span class="o-badge ' + (settled ? "ok" : "warn") + '" title="'
    + (settled
        ? "Amazon has settled this order, so the fee above is what it actually took."
        : "Amazon has not settled this order yet, so its fee is worked out at this "
          + "account's own measured rate and will be replaced when it settles.")
    + '">' + (settled ? "Fee settled by Amazon"
                      : "Fee estimated at "
                        + Math.round((t.fee_rate || 0.15) * 100) + "%") + '</span>');
  if(t.uncosted_lines){
    out.push('<span class="o-badge bad" title="Lines with no recorded cost are '
      + 'not counted as free — the order total is left blank instead.">'
      + t.uncosted_lines + ' line' + (t.uncosted_lines === 1 ? "" : "s")
      + ' with no cost</span>');
  }
  const best = _opBestSource(d, items);
  if(best && best.landed !== null && best.landed !== undefined){
    out.push('<span class="o-badge" title="The cheapest supplier this app is '
      + 'tracking for the item in this order.">Best supplier: '
      + _oEsc(String(best.label || "").slice(0, 24)) + " "
      + _oEsc(_oMoney(best.landed, best.currency || cur)) + '</span>');
  }
  // THE BUYER PAID MORE THAN THE LINES ADD UP TO. Postage, gift wrap or a
  // coupon -- a real gap, and one that makes the flow line above look wrong
  // unless it is named.
  if(t.order_total !== null && t.order_total !== undefined
     && Math.abs((t.revenue || 0) - t.order_total) > 0.02){
    out.push('<span class="o-badge warn" title="The difference from the lines '
      + 'above is postage, gift wrap or a coupon.">Buyer charged '
      + _oEsc(_oMoney(t.order_total, cur)) + ' in total</span>');
  }
  return out.length ? '<div class="o-badges">' + out.join("") + '</div>' : "";
}

/* The whole panel. Called by _ordDetailHtml, which keeps the error and
 * still-loading states -- this draws the case where there is something to
 * draw. */
function ordPanelHtml(r, d){
  const o = d.order || {};
  const items = d.items || [];
  const bd = d.breakdown || {};
  const t = bd.totals || {};
  const cur = o.currency || r.currency || "";
  let h = '<div class="opanel">';

  h += _opBar(t, cur);
  h += _opCards(r, t, cur, o);
  h += _opActions(r, d, items);

  // THE ITEM LINE. Not the old "What was ordered" block: the row above carries
  // the picture, the title and the SKU. What it does NOT carry is the ASIN and
  // the cancellation explanation, and those are the two parts kept.
  items.forEach(function(it){
    const why = (typeof _ordWhyText === "function")
      ? _ordWhyText(o.status || r.status, it.cancel_requested, it.cancel_reason) : "";
    const bits = [];
    if(items.length > 1) bits.push('<b>' + _oEsc(it.title || "(no title)") + '</b>');
    if(it.qty > 1) bits.push(it.qty + ' units');
    if(it.asin && typeof _ordDp === "function"){
      bits.push('<a class="link" target="_blank" rel="noopener" href="'
        + _oEsc(_ordDp(it.asin, r.marketplace)) + '" onclick="event.stopPropagation()"'
        + ' title="Open this product on Amazon">' + _oEsc(it.asin)
        + ' <i class="ti ti-external-link"></i></a>');
    }
    if(typeof _ordStateChip === "function"){
      const chip = _ordStateChip(o.status || r.status, it.cancel_requested);
      if(chip) bits.push(chip);
    }
    if(bits.length) h += '<div class="o-item">' + bits.join(' <span class="o-dot">·</span> ') + '</div>';
    // The cancellation sentence is never folded into a chip: it is the one
    // state where acting on a misreading costs real money.
    if(why) h += '<div class="o-why">' + why + '</div>';
  });

  // ---- where to buy it, compact ---------------------------------------
  // The sources block's OWN compact view, which already exists and already
  // decides which supplier is best. Not a second summary written here.
  items.forEach(function(it){
    const block = (d.sources || {})[it.sku];
    if(!block || typeof _ordSourcesHtml !== "function") return;
    const body = _ordSourcesHtml(block, items.length > 1 ? it.title : "",
                                 {compact: true});
    if(body) h += body;
  });

  // ---- what it earned --------------------------------------------------
  // ONE LINE FOR ONE ITEM, THE TABLE FOR MORE. The flow line can show a single
  // sum; on a two-item order it would have to hide one product's numbers, which
  // is losing data rather than compressing it.
  if((bd.lines || []).length > 1){
    h += (typeof _ordBreakdownHtml === "function")
      ? _ordBreakdownHtml(bd, cur, r.order_id, r.account_id, r.marketplace) : "";
  }else{
    h += _opFlow(t, cur);
    h += _opCostBox(bd, r);
  }

  h += _opDelivery(o);
  h += _opBadges(t, d, items, cur);
  return h + '</div>';
}

/* Correct THIS order's cost, inline on the flow line.
 *
 * The endpoint and the rules are ordSetOrderCogs's, unchanged: per unit, per
 * order, blank clears it back to "not known". Only the layout moved -- it was a
 * paragraph and a box at the foot of the panel. */
function _opCostBox(bd, r){
  const lines = bd.lines || [];
  if(!r.order_id || lines.length !== 1) return "";
  const l = lines[0];
  if(!l.sku && lines.length > 1) return "";
  const unit = (l.unit_cost !== null && l.unit_cost !== undefined)
    ? l.unit_cost
    : ((l.cogs !== null && l.cogs !== undefined && l.qty)
        ? (Number(l.cogs) / Number(l.qty)) : null);
  const id = "ordcogs_0";
  return '<div class="o-costfix" onclick="event.stopPropagation()">'
    + '<label for="' + id + '" title="Per unit, and for this order only — no '
    + 'other order changes, and the product\'s own cost is left alone. Empty it '
    + 'and Save to put this line back to &quot;not known&quot;.">Cost per unit</label>'
    + '<input id="' + id + '" class="ed" placeholder="'
    + (unit === null ? "e.g. 15.10" : _oEsc(Number(unit).toFixed(2))) + '">'
    + '<button class="ghost" onclick="ordSetOrderCogs('
    + jsArg(r.order_id) + ',' + jsArg(l.sku || "") + ',' + jsArg(id) + ','
    + jsArg(r.account_id || "") + ',' + jsArg(r.marketplace || "") + ')">Save</button>'
    + (l.qty > 1 ? '<span class="cc">× ' + l.qty + ' units</span>' : "")
    + '</div>';
}
