// ============ USER GUIDES ============
//
// "i am also not able to understand how the generate and submit works, there is
//  no user guide there ... please add a user guide button on that page
//  explaining the process"
//
// NOT the same thing as howWorks(). That is an admin transparency layer -- it
// explains which API each button calls, it is gated on LOGIC_VISIBLE, and a
// normal user never sees it. This is a guide: what the screen is for, in what
// order to press things, and what each step will and will not do to a live
// Amazon listing. Always visible, to everybody.
//
// Written from the flow as it actually runs, not from the button labels:
// /input/add queues a product, Generate turns the queue into drafts, Preview
// validates a draft against Amazon without creating anything, and Submit is the
// only step that reaches the live catalogue.

/* A LIST, NOT A PARAGRAPH.
 *
 *     "mention everything how it works and what are the rules in a format easy
 *      to understand and not in paragraphs but in words"
 *
 * A guide is read to find ONE rule, not from start to finish, and a rule buried
 * mid-sentence in a block of prose cannot be found by scanning. One style,
 * defined once, so every guide that uses it looks the same (CLAUDE.md Rule 12).
 * Styles are inline because these strings are injected as innerHTML and the
 * guide has no stylesheet of its own.
 */
function _gl(items){
  return '<ul style="margin:6px 0 0;padding-left:17px">'
    + (items || []).map(function(t){
        return '<li style="margin:3px 0;line-height:1.55">' + t + '</li>';
      }).join("")
    + '</ul>';
}

/* Two columns -- a thing and what it means. For "what this word on the row
   means", where a sentence per item reads as a wall and a table does not. */
function _gt(rows){
  return '<table style="margin:7px 0 0;border-collapse:collapse;width:100%">'
    + (rows || []).map(function(r){
        return '<tr>'
          + '<td style="padding:3px 10px 3px 0;vertical-align:top;white-space:nowrap">'
          + '<b>' + r[0] + '</b></td>'
          + '<td style="padding:3px 0;vertical-align:top;line-height:1.5">'
          + r[1] + '</td></tr>';
      }).join("")
    + '</table>';
}

const GUIDES = {
  // PPC ANALYTICS. The thing worth leading with is where the figures come from:
  // this app has no Advertising API connection, so everything is read from a
  // report the seller downloads. Somebody who does not know that will wonder
  // why the screen is empty and conclude it is broken.
  ppc: {
    title: "PPC — how this page works",
    lead: "What your advertising is doing, and what it is wasting. Every figure "
        + "comes from your own Search Term Report. Nothing here changes a bid, "
        + "a budget or a campaign.",
    steps: [
      {n: "1", h: "Get the report",
       b: "In Seller Central: <b>Advertising → Measurement &amp; Reporting → "
        + "Sponsored Products → Search Term Report</b>. Pick a date range, "
        + "download the CSV, and upload it with the button at the top of this "
        + "page.<br><br>"
        + "<b>Why a file and not a live connection.</b> Amazon's Advertising "
        + "API is a completely separate login from the one this app uses for "
        + "listings and orders — its own client id, secret and refresh token — "
        + "and it is not connected. The report carries everything except the "
        + "hour-by-hour view, so nothing waits on it."},
      {n: "2", h: "Start with what bought nothing",
       b: "The headline is the spend that produced no orders. It is the only "
        + "figure on the page that names an action rather than scoring you.<br><br>"
        + "A term needs at least ten clicks before it is counted — below that, "
        + "no orders is evidence of nothing, and negating on it would throw "
        + "away a term that was never given a chance."},
      {n: "3", h: "Tell it your brand name",
       b: "Amazon does not report which searches were for your brand. Type your "
        + "brand words into the box and every term containing one is counted "
        + "as branded.<br><br>"
        + "It matters more than it sounds: paying to appear on your own name is "
        + "defensive, not growth. Mixed together they make a healthy-looking "
        + "ACOS out of money that never won a new customer. Split apart, the "
        + "non-branded ACOS is the number that tells you whether the "
        + "advertising is actually working."},
      {n: "4", h: "Act on it in the harvester, not here",
       b: "This page reports. The <b>campaign builder and harvester</b> below "
        + "turn what you have found into a Seller Central bulk file — new "
        + "keywords in all three match types, and negatives for the terms that "
        + "wasted money.<br><br>"
        + "You review that file and upload it yourself. Nothing in this app "
        + "ever changes a bid or a budget on its own."},
    ],
    notes: [
      "<b>ACOS</b> is spend over the sales the ads made — does the advertising "
      + "pay for itself. <b>TACOS</b> is spend over ALL your sales, ad and "
      + "organic — what advertising costs the business. A brand can have a "
      + "healthy ACOS and a TACOS that is eating it, and only the second "
      + "answers whether you should be spending this at all.",
      "<b>CPC</b> is cost per click. <b>CPA</b> is cost per <i>acquisition</i>. "
      + "A term with a cheap CPC and a terrible CPA is the expensive kind of "
      + "cheap.",
      "<b>CTR</b> asks whether the AD is worth clicking. <b>CVR</b> asks "
      + "whether the LISTING converts the traffic the ad bought. A bad ACOS "
      + "with a good CTR and a poor CVR is a listing problem, not an ads one.",
      "<b>Match types.</b> Broad discovers, exact converts. The % of spend "
      + "against % of profit columns are the point — a match type taking 40% "
      + "of the spend and returning 12% of the profit is the one to look at.",
      "A blank figure means it could not be worked out, never zero. A term with "
      + "no clicks has no CTR; printing 0% would invite acting on a number "
      + "nobody measured.",
      "TACOS needs total sales, which come from your orders rather than the ad "
      + "report — so it appears once the report carries its date range.",
    ],
  },
  // THE STOCK COCKPIT. Written around the one thing that is genuinely different
  // here from every other inventory tool: these listings are merchant-fulfilled,
  // so "units" is a promise rather than a warehouse count, and the number that
  // decides whether a low one matters is how fast the SUPPLIER can send more.
  stock: {
    title: "Inventory — how this page works",
    lead: "What you have, how fast it is going, and whether you can get more "
        + "before it runs out. It reads what the app already knows and changes "
        + "nothing on Amazon.",
    steps: [
      {n: "1", h: "Read the headline first",
       b: "It names the product that runs out soonest and the date it happens. "
        + "That is the one thing on this screen worth acting on today.<br><br>"
        + "The three cards beside it are the money: what you stand to lose if "
        + "nothing is ordered, what the stock you hold cost you, and how many "
        + "days of cover you have on average."},
      {n: "2", h: "Know what “units” means here",
       b: "It is the quantity on your Amazon listing — <b>what you have "
        + "promised</b>, not what is in a warehouse. Every listing on these "
        + "accounts is merchant-fulfilled: there is no FBA stock, and the item "
        + "is bought from the supplier when an order arrives.<br><br>"
        + "So a listing showing 4 units is a promise to supply four, and the "
        + "question is whether four can be sourced in time."},
      {n: "3", h: "Cover against restock is the whole judgement",
       b: "<b>Cover</b> is how many days the listed quantity lasts at the rate "
        + "it has been selling. <b>Restock</b> is how long your fastest usable "
        + "supplier takes to dispatch, plus the safety buffer.<br><br>"
        + "A product is flagged when cover is shorter than restock — it will "
        + "run out before more can arrive. That is why 6 days of cover can be "
        + "fine on one product and urgent on another."},
      {n: "4", h: "Fill the gaps the review queue names",
       b: "A row with no cost cannot be valued. A row with no supplier gets an "
        + "assumed restock time and says so with a “?”. A row with no sales in "
        + "the window has no rate, so it has no cover — that is honest rather "
        + "than a zero.<br><br>"
        + "Costs go on the Costs sheet on the Listings screen. Suppliers go in "
        + "the Repricer. Both feed straight back into this page."},
    ],
    notes: [
      "<b>Sold / day</b> is units sold over the last 30 days divided by 30 — "
      + "Orbit's own definition. A product whose entire history falls inside "
      + "that window is marked <i>new</i>, because two sales in three days is "
      + "not two thirds of a sale a day sustained.",
      "<b>Cover</b> is Orbit's DOS: units divided by the daily rate. No sales "
      + "means no cover at all, never infinite cover.",
      "<b>Revenue at risk</b> is a forecast and is the only figure here that "
      + "is: for each product that runs out before more can arrive, the sales "
      + "it would have made during the gap. It is not the value of the product.",
      "<b>The five states</b> — safe, watch, order soon, order now, stockout "
      + "likely — are Orbit's names in Orbit's order, healthiest to most "
      + "urgent. The thresholds are ours: multiples of the restock time rather "
      + "than a fixed number of days, because a supplier who ships next day "
      + "needs far less warning than one who takes ten.",
      "Nothing on this page writes anything or contacts Amazon. It is a view.",
    ],
  },
  // "give a button on the top of the page which explains how do this page works
  //  and what the information means etc etc."
  //
  // Written around the one thing that actually confuses people here: TRACKING IS
  // NOT PRICING. Adding a SKU starts a cost history and nothing else, and every
  // SKU still has to be armed separately on top of a master switch. Somebody who
  // does not know that either refuses to add anything, or adds everything
  // expecting prices to move and concludes the app is broken when they do not.
  repricer: {
    title: "The repricer — how this page works",
    lead: "It reads what your suppliers charge and works out what each unit "
        + "really earns. It changes nothing on Amazon until THREE separate "
        + "things are on.",
    steps: [
      {n: "1", h: "Track a SKU — changes nothing on Amazon",
       b: "Tracking = the app reads that SKU's supplier links every 4 hours and "
        + "writes down what a unit costs, delivered."
        + _gl([
            "Safe to track everything — it only starts a cost history",
            "<b>Track everything</b> — adds every live listing and attaches the "
            + "supplier link recorded when it was built",
            "<b>Suppliers from a sheet</b> — get the template first; it arrives "
            + "filled in with your SKUs",
            "A supplier price on a day nobody was watching cannot be recovered "
            + "later — start it before you need it",
          ])},
      {n: "2", h: "Give each SKU its suppliers",
       b: "As many as you like. It prices from the <b>cheapest one that can "
        + "actually be bought</b>."
        + _gl([
            "Must be in stock, readable, and with a known postage cost",
            "Postage that cannot be read = skipped, never counted as free",
            "Template has <i>supplier 1</i> … <i>supplier 10</i>; add "
            + "<i>supplier 11</i>, 12 … for more — no limit",
          ])},
      {n: "3", h: "How the price is worked out",
       b: "Forwards from the supplier, never backwards from what you sell at:"
        + _gl([
            "what the supplier charges <b>+ their postage to you</b> = your cost",
            "<b>+ Amazon's fee</b> — your referral %, 15% unless you change it",
            "<b>+ your postage to the buyer</b> — 0.00 unless you set it",
            "<b>+ ads allowance</b> — 0.00 unless you set it",
            "<b>+ profit</b> — the largest of: your flat minimum, the 20% "
            + "safety floor, your margin target, your ROI target",
          ])
        + "<div style=\"margin-top:7px\">The price is the <b>highest</b> of "
        + "those floors. No readable supplier = no cost = <b>no price, and "
        + "nothing changes</b>.</div>"},
      {n: "4", h: "The four numbers you can set",
       b: _gt([
            ["Margin target",
             "profit as a share of what the CUSTOMER pays. Cannot go much above "
             + "84% — Amazon's cut comes out of the same price."],
            ["ROI target",
             "profit as a share of what YOU paid. No ceiling."],
            ["Never sell below",
             "the backstop. The only guard that still works if a supplier's page "
             + "is misread — <b>no SKU can be armed without it</b>."],
            ["Hold the price at",
             "“this is what the market pays”. Never priced below it."],
          ])
        + "<div style=\"margin-top:7px\">Both targets apply at once; the price "
        + "takes whichever asks for more. Each can be set for the whole account "
        + "or for one SKU — the SKU's own wins.</div>"},
      {n: "5", h: "A target is a FLOOR, so it can lower a price",
       b: "This surprises people, so it is worth reading twice."
        + _gl([
            "The target sets the <b>least</b> price that still earns it",
            "Selling ABOVE that? It will come <b>down</b> to the floor",
            "Selling BELOW it? It goes <b>up</b>",
            "To stop it coming down: <b>Hold the price at</b>",
          ])
        + "<div style=\"margin-top:7px\"><b>Hold at today's price</b> — tick the "
        + "SKUs, press it once, and today's Amazon price becomes the floor for "
        + "each. Then a cheaper supplier means more margin, not a lower price; a "
        + "dearer one can still push the price UP, so a hold can never hold you "
        + "at a loss.</div>"},
      {n: "6", h: "Three switches before anything moves",
       b: _gl([
            "<b>Minimum price</b> set on that SKU — without it, Arm refuses",
            "<b>Arm</b> — per SKU",
            "<b>Auto-pricing</b> — the master switch for the account",
          ])
        + "<div style=\"margin-top:7px\">All three, or the price stays put. "
        + "Until then every decision is still worked out and written down, so "
        + "you can read what it WOULD have done. If it looks wrong here, it "
        + "would have been wrong on Amazon.</div>"},
      {n: "7", h: "Why a SKU is not being repriced",
       b: "In the order it is usually one of these — press <b>Why?</b> on the "
        + "row for that SKU's own answer:"
        + _gl([
            "no suppliers set up for it",
            "no supplier could be read, or all of them are out of stock or ended",
            "no minimum price, so it could never be armed",
            "not armed, or auto-pricing is off",
            "its price is held where it is",
            "it moved within the last 4 hours",
            "the change is bigger than the one-step cap",
          ])},
    ],
    notes: [
      "<b>What each figure on a row means.</b>"
      + _gt([
          ["Cheapest source", "what one unit costs you delivered — supplier's "
           + "price + their postage"],
          ["Selling price", "what Amazon is charging today"],
          ["Profit / unit", "what is left after the stock and Amazon's fee"],
          ["Margin", "that profit over the SELLING PRICE"],
          ["ROI", "that profit over WHAT YOU PAID"],
          ["Units at source", "how many the supplier has"],
          ["Handling", "supplier's dispatch estimate + your safety buffer"],
        ]),
      "<b>What the chips mean.</b>"
      + _gt([
          ["would change", "it wants to move this price — the new one is shown "
           + "beside it"],
          ["cost up / down %", "your supplier's price against the cost on record "
           + "for that SKU"],
          ["roi %", "what you would make if an order came in RIGHT NOW"],
          ["held", "the price is held where it is"],
          ["would go out of stock", "nothing can be bought to fulfil it"],
          ["N of M usable", "how many suppliers could actually be read"],
        ]),
      "<b>The 15% is a setting, not Amazon's quote.</b> It is applied flat to "
      + "every SKU. Amazon's real referral fee varies by category — often 15%, "
      + "sometimes 8%, usually with a minimum per item. Nothing checks it "
      + "against Amazon for your product, so if it is wrong for a product every "
      + "price for that product is wrong.",
      "<b>The 20% safety floor is not a target.</b> It is the line below which "
      + "the app will not price at all, so a repricer can never sell at "
      + "break-even. Setting a target of your own is separate.",
      "<b>Nothing is added that you did not enter.</b> Postage out and the ads "
      + "allowance are 0.00 unless you set them.",
      "<b>The “after coupon” figures</b> appear only on SKUs that have really "
      + "been selling at a discount — measured from what buyers were charged on "
      + "settled orders, not read from Seller Central.",
      "A price is never moved more than once every 4 hours, never by more than "
      + "the change cap in one step, and never below your minimum price.",
      "A SKU Amazon no longer has is marked and disarmed automatically; its "
      + "suppliers and history are kept in case you relist it.",
      "Removing a SKU from tracking keeps its links and its price history.",
    ],
  },
  generate: {
    title: "Generate &amp; submit — how it works",
    lead: "This screen turns a product you found somewhere else into a live "
        + "Amazon listing under your own brand. It runs in four steps, and only "
        + "the last one touches Amazon.",
    steps: [
      {n: "1", h: "Put the product in the queue",
       b: "The queue is the list at the bottom of this page — it is what "
        + "Generate works from. Two ways to fill it:<br><br>"
        + "<b>Add a product</b> (the form above the list) — paste the "
        + "<b>source link</b>, which is the page you would actually BUY from, "
        + "normally an eBay item. Then the <b>Amazon / ASIN</b> of a competitor "
        + "selling something similar: the app reads that listing for its product "
        + "type, its category and the exact Amazon fees, and for nothing else. "
        + "Cost is what you pay the supplier. Leave <b>Sell at</b> empty and the "
        + "app prices it from your cost and Amazon's fees.<br><br>"
        + "<b>Import from sheet</b> — reads a spreadsheet once and adds its rows "
        + "to the queue. It never deletes from the queue, and nothing is read "
        + "from that sheet again afterwards."},
      {n: "2", h: "Generate the drafts",
       b: "<b>Generate</b> creates a listing for every queued product that is not "
        + "in the app yet — title, five bullets, description, search terms and "
        + "the attributes the product type requires. To do only some of them, "
        + "name them in the <b>Which listings</b> box by ASIN, or paste a "
        + "single product's URL.<br><br>"
        + "The words come from the SOURCE listing, not the competitor: the "
        + "competitor is a different seller's version of a similar product and is "
        + "used for price, fees and product type only. Nothing here reaches "
        + "Amazon — the drafts land on the <b>Listings</b> screen."},
      {n: "3", h: "Check each draft, then ask Amazon",
       b: "Open a draft on the Listings screen and read it. The compliance panel "
        + "tells you which documents Amazon can ask for later; it never blocks "
        + "publishing.<br><br>"
        + "<b>Preview (API)</b> sends the draft to Amazon's validator and brings "
        + "back the real errors — a missing attribute, a value the product type "
        + "will not accept. It creates NOTHING. Fix what it reports and preview "
        + "again until it comes back clean. <b>Retry holds</b> re-runs the ones "
        + "that got stuck.<br><br>"
        + "Images: use <b>Image Studio</b> to generate them and the image library "
        + "to put each one in its slot."},
      {n: "4", h: "Publish",
       b: "<b>Submit · go live</b> is the only button on this page that changes "
        + "anything on Amazon. It creates the listing under your own brand — a "
        + "new product, not an offer on somebody else's. Amazon usually takes a "
        + "few minutes, and the Listings screen shows it as live once Amazon "
        + "confirms it.<br><br>"
        + "<b>Export .xlsm</b> is the alternative: it fills Amazon's flat-file "
        + "template so you can upload it in Seller Central by hand instead."},
    ],
    notes: [
      "<b>Stop</b> ends the current run. Anything already generated is kept.",
      "Everything on this page is scoped to the account and marketplace shown in "
      + "the sidebar. Switching either changes what Generate will touch.",
      "A run works through the queue one product at a time and streams its "
      + "progress into the page, so you can leave it and come back.",
    ],
  },

  // "you said the variations tab is working correctly but i am not able to
  //  understand how to create variations using it. give me a how this page
  //  works button on the variations page"
  //
  // Written from what the tool actually does, having merged a real family with
  // it: listing/variations.py decides, routes/variations_routes.py sends, and
  // the parent is created before any child is touched.
  variations: {
    title: "Variations — how to join products into one listing",
    lead: "A variation family is several products shown on ONE Amazon page with "
        + "a picker — Black or Green, Small or Large. This screen builds one out "
        + "of listings you already have live. Nothing is sent until the last "
        + "step, and every check happens before it.",
    steps: [
      {n: "1", h: "Pick the products that belong together",
       b: "The list is this account's LIVE listings — a family is built out of "
        + "products Amazon already has, so a draft cannot be in one until it has "
        + "been published.<br><br>"
        + "Tick two or more. They must be the same product type, the same brand, "
        + "and genuinely differ in one respect: two listings both in “Large” "
        + "under a SIZE grouping are not a family, they are two listings that "
        + "compete with each other.<br><br>"
        + "Deciding which products are the same thing in different colours is a "
        + "judgement you make by looking, which is why the pictures are there."},
      {n: "2", h: "Choose what makes them different",
       b: "The dropdown lists only the groupings <b>this product type actually "
        + "allows</b>, read from Amazon's own schema. Deprecated ones are left "
        + "out, and so are the ones that name an attribute the type does not "
        + "have — those are shown greyed with the reason, because a grouping "
        + "vanishing from a list looks like the app lost it.<br><br>"
        + "COLOR groups by colour, SIZE by size, and a grouping written with a "
        + "slash like SIZE/PATTERN needs BOTH set on every product."},
      {n: "3", h: "Name the parent",
       b: "The parent is a listing with its own SKU that <b>nobody can buy</b>. "
        + "It carries the title and the pictures the family shows in search; the "
        + "children keep the prices and the stock.<br><br>"
        + "A SKU is permanent on Amazon, so the suggested one is only a "
        + "suggestion — give it a name you will recognise in a year."},
      {n: "4", h: "Read the preview, then create it",
       b: "The preview <b>is</b> the payload: the same code builds what you see "
        + "and what gets sent, so they cannot drift apart. It lists every reason "
        + "the merge would be refused, in plain words, and the button stays "
        + "disabled until there are none.<br><br>"
        + "It also says which details the parent <b>inherits</b> — everything the "
        + "children agree on, like brand and country of origin — and which it "
        + "<b>borrows</b> from one child, because two products written separately "
        + "never share a description. That is a real choice about what shoppers "
        + "read, so it names the product it took them from.<br><br>"
        + "<b>Create the family on Amazon</b> makes the parent first and only "
        + "joins the children once Amazon has accepted it. If the parent is "
        + "refused, nothing else is sent."},
    ],
    notes: [
      "Amazon accepts a half-formed family WITHOUT COMPLAINING and the products "
      + "then quietly stop appearing in search. That is why everything is "
      + "checked before anything is sent, and why the parent goes up first.",
      "A product can belong to one family only. One that already has a parent is "
      + "refused, and says which family it is in.",
      "Amazon publishes variations in its own time — a few minutes is normal "
      + "before the picker appears on the product page.",
      "Splitting a family up again afterwards is fiddly, so it is worth being "
      + "sure before you press the last button.",
    ],
  },
};

function openGuide(key){
  const g = GUIDES[key];
  if(!g) return;
  let host = document.getElementById("guidewrap");
  if(!host){
    host = document.createElement("div");
    host.id = "guidewrap";
    host.className = "modalwrap";
    host.style.zIndex = "180";
    host.addEventListener("click", function(ev){
      if(ev.target === host) closeGuide();
    });
    document.body.appendChild(host);
  }
  host.innerHTML =
      '<div class="modal" style="max-width:760px">'
    + '<button class="x" onclick="closeGuide()">×</button>'
    + '<p class="paneltitle"><i class="ti ti-book"></i> ' + g.title + '</p>'
    + '<p class="panelsub" style="margin-bottom:14px">' + g.lead + '</p>'
    + g.steps.map(function(s){
        return '<div class="panelcard" style="padding:12px 14px;margin-bottom:10px">'
          + '<div style="display:flex;gap:11px;align-items:flex-start">'
          + '<div style="flex:0 0 26px;height:26px;border-radius:50%;'
          + 'background:var(--accent-bg);color:var(--accent);display:flex;'
          + 'align-items:center;justify-content:center;font-weight:700;'
          + 'font-size:12.5px">' + s.n + '</div>'
          + '<div><div style="font-weight:600;font-size:13px;margin-bottom:4px">'
          + s.h + '</div>'
          + '<div class="cc" style="font-size:12px;line-height:1.62">' + s.b + '</div>'
          + '</div></div></div>';
      }).join("")
    + '<div class="cc" style="font-size:11.5px;line-height:1.6;margin-top:4px">'
    + g.notes.map(function(n){ return '· ' + n; }).join("<br>")
    + '</div></div>';
  host.classList.add("open");
  document.addEventListener("keydown", _guideKey);
}

function _guideKey(ev){
  if(ev.key === "Escape") closeGuide();
}

function closeGuide(){
  document.removeEventListener("keydown", _guideKey);
  const host = document.getElementById("guidewrap");
  if(host) host.classList.remove("open");
}
