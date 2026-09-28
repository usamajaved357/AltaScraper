// static/js/sales_cards.js -- the Sales Report stat cards. Moved word for word out of sales.js (Milestone 4, 28 Sep 2026); loaded right after it, so every name resolves as before.

/* ---- stat cards -------------------------------------------------------- */
function salesDrawCards(sum, av){
  const host=document.getElementById("sales_cards");
  const note=document.getElementById("sales_note");
  if(!host) return;
  if(!sum || !sum.ok){
    host.innerHTML="";
    if(note) note.innerHTML=(sum&&sum.error)
      ? uiError("Sales could not be loaded", sum.error, "salesReload", "sales")
      : '<div class="empty">No sales data</div>';
    return;
  }
  // ORBIT'S FIVE, IN ITS ORDER AND ITS WORDS: Total Sales, Daily Average,
  // Total Orders, Total Units, Profit. Ours had ten in a different order with
  // different names, so the two screens did not even begin the same way.
  //
  // The rest are not thrown away -- they are every one of them a row in the
  // grid below, per day, in full. What changes is which five are given the top
  // of the screen.
  //
  // Daily Average is not a figure Amazon sends; it is revenue over the number
  // of days in the range, worked out here. It is on the same basis as the
  // revenue it comes from, so it cannot disagree with the card beside it.
  const _byKey = {};
  (sum.cards || []).forEach(function(c){ _byKey[c.key] = c; });
  // THE DAYS THE REPORT HAS NOT SENT, added from the live order feed -- the same
  // days, from the same source, that the chart below is already drawing. Without
  // this a week whose only trade was yesterday reads "0 orders, £0" on the cards
  // while the chart beside them shows three, which is worse than either being
  // late. See _sLiveAdd: a day Amazon HAS reported is never touched, even when
  // it reported a zero.
  ["ordered_sales", "orders", "units"].forEach(function(k){
    const add = _sLiveAdd(k);
    if(!add) return;
    const c = _byKey[k] || (_byKey[k] = {key: k, value: 0,
                                         kind: (k === "ordered_sales" ? "money" : "count")});
    c.value = (Number(c.value) || 0) + add;
    c.live_added = add;
  });
  const _days = (function(){
    try{
      const a = new Date(sum.start + "T00:00:00Z"), b = new Date(sum.end + "T00:00:00Z");
      const n = Math.round((b - a) / 86400000) + 1;
      return (n > 0 && n < 1000) ? n : 0;
    }catch(e){ return 0; }
  })();
  let _rev = _byKey["ordered_sales"] || _byKey["net_revenue"];

  // THE POSTAGE IS ALREADY IN THE STORED FIGURE, so it is NOT added here.
  //
  // It used to be: the report's ordered_sales is the goods alone, and the
  // postage was only known per order, so the browser added it on. Since
  // domain/live_reconcile.py started writing the live orders into sales_daily
  // -- postage included, because that is the owner's definition of revenue --
  // adding it again counted it twice. Measured on jack_uk: the card read 114
  // against a true 102.21, over by exactly the 12.24 of postage.
  //
  // One place decides what revenue means, and it is the store. The split is
  // still shown on hover, from order_profit, because the goods figure alone is
  // what reconciles against Seller Central.
  const _op = sum.order_profit;
  if(_op && _op.postage > 0 && _rev) {
    _rev = Object.assign({}, _rev, {goods: _op.goods, postage: _op.postage});
  }

  const ORBIT_CARDS = [
    Object.assign({}, _rev || {}, {label: "Total Sales"}),
    (_rev && _days && _rev.value !== null && _rev.value !== undefined)
      ? {key: "daily_avg", kind: "money", label: "Daily Average",
         value: Number(_rev.value) / _days,
         previous: (_rev.previous === null || _rev.previous === undefined)
                   ? null : Number(_rev.previous) / _days,
         delta_pct: _rev.delta_pct}
      : {key: "daily_avg", kind: "money", label: "Daily Average",
         value: null, previous: null, delta_pct: null},
    Object.assign({}, _byKey["orders"] || {key: "orders", kind: "count", value: null},
                  {label: "Total Orders"}),
    Object.assign({}, _byKey["units"] || {key: "units", kind: "count", value: null},
                  {label: "Total Units"}),
    _sProfitCard(sum, _byKey),
  ];

  host.innerHTML = ORBIT_CARDS.map(function(c){
    const missing = (c.value===null||c.value===undefined);
    const adsOff = (c.key==="spend" && !sum.ads_connected);
    // PROFIT AND MARGIN READ AT A GLANCE. They are the two numbers the business
    // runs on, and a loss has to be obvious without reading the minus sign.
    const isProfit = (c.key==="profit" || c.key==="margin_pct");
    const neg = isProfit && Number(c.value) < 0;
    const col = missing ? "" :
      (neg ? ";color:var(--red)" :
       isProfit ? ";color:var(--ok,var(--ok))" : "");
    // LABEL FIRST, then the number, then the comparison -- Orbit's order,
    // measured: the label sits above the figure, not under it. Ours had it the
    // other way round and centred, which is why the two never looked alike
    // however close the colours got.
    // WHAT THIS FIGURE IS, under the figure. A profit worked out from the
    // owner's own costs is not the same claim as one Amazon has settled, and a
    // profit with uncosted units in it is knowingly too high -- neither can be
    // left to be inferred from a number on its own.
    // THE SENTENCE GOES BEHIND A MARK, NOT INSIDE THE CARD.
    //
    // "the cards on the screen are too big, check orbit cards, the profit has a
    //  i button which explains and you have english written statements very long
    //  and it disturb the cards size. please hide them somewhere in a i button"
    //
    // Measured, ours against Orbit's on the same screen size:
    //     Orbit   216 x 104   padding 12   radius 8
    //     ours    229 x 163
    // and the extra 59px was this note, set to white-space:normal and allowed to
    // wrap to three or four lines inside the card. The Profit card carried 169
    // characters of it: "22 of 28 units have no cost recorded, so nothing was
    // subtracted for them and this profit is HIGHER than the truth…".
    //
    // Orbit does exactly this: its Profit card has a "More information" mark and
    // no prose. So the note becomes the mark's tooltip -- still one hover away,
    // never lost -- and the card keeps its height. A warning also keeps a small
    // coloured flag, because "this figure is too high" must be visible without
    // hovering anything.
    const noteMark = c.note
      ? '<span class="statinfo" title="' + _sEsc(c.note) + '">'
        + (c.warn ? '<i class="ti ti-alert-triangle" style="color:var(--warn)"></i>'
                  : '<i class="ti ti-info-circle"></i>')
        + '</span>'
      : '';
    const foot = c.note
      ? (adsOff
          ? '<p class="stat-delta" title="'+_sEsc(sum.ads_note||"")+'">not connected</p>'
          : _sDelta(c, (SALES.compareKind === "year" ? "LY" : "was"),
                    c.previous, c.kind, sum.currency))
      : (adsOff
          ? '<p class="stat-delta" title="'+_sEsc(sum.ads_note||"")+'">not connected</p>'
          // "LY :" is Orbit's own wording, with the space. `previous` is what
          // the server calls the earlier figure -- it was read as `prev_value`,
          // which does not exist, so every card said only a percentage with
          // nothing to compare it against.
          : _sDelta(c, (SALES.compareKind === "year" ? "LY" : "was"),
                    c.previous, c.kind, sum.currency));
    // Where postage has been folded into Total Sales, say so on hover -- the
    // goods figure alone is what reconciles against Seller Central, and someone
    // checking the two must be able to find it.
    const salesTip = (c.postage
      ? "goods " + _sNum(c.goods, "money", sum.currency)
        + " + postage the buyer paid " + _sNum(c.postage, "money", sum.currency)
        + "\nAmazon's own 'Ordered product sales' is the goods figure alone."
      : "");
    return '<div class="stat-card'+(missing?" is-empty":"")+'"'
      + (isProfit ? ' title="'+_sEsc(_sProfitTip(c))+'"'
                  : (salesTip ? ' title="'+_sEsc(salesTip)+'"' : ''))
      + '>'
      + '<p class="stat-label">'+_sEsc(c.label)+' '+noteMark+'</p>'
      + '<p class="stat-number" style="'+col.replace(/^;/,"")+'">'
      + _sEsc(_sShort(c.value, c.kind, sum.currency))+'</p>'
      + foot
      + '</div>';
  }).join("");

  if(note){
    let n = "";
    if(!sum.ads_connected)
      n += '<div class="cc salesnote"><i class="ti ti-info-circle"></i> '
         + _sEsc(sum.ads_note||"") + '</div>';
    // Why a Profit row may be blank. Without this the em-dash reads as a fault
    // rather than as "some of these products have never been costed".
    const cov = sum.cogs_coverage;
    if(cov && cov.note)
      n += '<div class="cc salesnote"><i class="ti ti-info-circle"></i> '
         + _sEsc(cov.note) + '</div>';
    note.innerHTML = n;
  }
}

/* Change against the previous period of the SAME LENGTH. Carries an arrow and a
   word as well as a colour — a green number alone is unreadable to a good number
   of people, and meaningless in print. */
/* The comparison line under each figure, laid out as Orbit lays it out:
   the earlier figure in grey, then the percentage as a coloured chip.
   Measured from its live dashboard -- "LY: $551,866.01 +5.2%".

   Ours says "was" rather than "LY" because the comparison is the previous
   PERIOD by default, and calling a 30-day-ago figure "last year" would be a
   plain lie. When the comparison is set to a year earlier it says LY, because
   then it is one. */
function _sDelta(c, prevLabel, prevValue, kind, currency){
  if(c.delta_pct===null || c.delta_pct===undefined){
    // Said, not left as a dash. A blank here reads as a fault, and showing
    // "0.0%" for a period with nothing to compare against would be a fiction.
    //
    // BUT THERE ARE TWO REASONS FOR NO PERCENTAGE, and they are not the same
    // fact. Reported as "no earlier period" on every card of a week that had a
    // perfectly ordinary week before it:
    //
    //   the period before had NOTHING     -- a real figure, and a rise from
    //                                        zero has no percentage
    //   there IS no period before         -- the account has no data that far
    //                                        back at all
    //
    // A rise from zero is the more common of the two and the more interesting,
    // and calling it "no earlier period" says the app cannot see history when
    // it can.
    const had = (prevValue !== null && prevValue !== undefined);
    return '<p class="stat-delta">'
         + (had ? (_sEsc(prevLabel || "was") + " : "
                   + _sEsc(_sShort(prevValue, kind, currency))
                   + " — no % from zero")
                : "no earlier period")
         + '</p>';
  }
  const up = c.delta_pct >= 0;
  // AD SPEND RISING IS NOT A WIN, so direction and goodness are separate things:
  // the arrow still points up, the colour goes the other way. _sBadge draws the
  // arrow from the number, so the colour is corrected here afterwards -- the one
  // case on the screen where the two disagree.
  const good = (c.key === "spend") ? !up : up;
  // "LY : $551,866.01" -- Orbit's spacing, measured off its own cards.
  const was = (prevValue===null || prevValue===undefined)
    ? "" : (prevLabel||"was") + " : " + _sShort(prevValue, kind, currency) + " ";
  let badge = _sBadge(c.delta_pct, {sign: true,
    title: (up ? "up" : "down") + " versus "
         + (prevLabel === "LY" ? "the same period last year" : "the period before")});
  if(c.delta_pct !== 0 && good !== up){
    badge = badge.replace('pct-badge ' + (up ? "up" : "down"),
                          'pct-badge ' + (good ? "up" : "down"));
  }
  return '<p class="stat-delta">' + _sEsc(was) + badge + '</p>';
}
