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

const GUIDES = {
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
    lead: "It watches what your suppliers charge and works out what each unit "
        + "would really earn. Nothing here changes a live Amazon listing unless "
        + "you turn two separate things on.",
    steps: [
      {n: "1", h: "Track a SKU",
       b: "Tracking means the app reads that SKU's supplier links every few "
        + "hours and writes down what the unit costs, delivered. <b>It changes "
        + "nothing on Amazon.</b> That is why it is safe to track everything: a "
        + "supplier price on a day nobody was watching cannot be recovered "
        + "later, so the history is worth starting before you need it.<br><br>"
        + "<b>Track everything</b> adds every live listing at once and attaches "
        + "the supplier link the app recorded when it built each one. "
        + "<b>Suppliers from a sheet</b> takes a spreadsheet — get the template "
        + "first, it arrives already filled in with your SKUs."},
      {n: "2", h: "Give each SKU its suppliers",
       b: "A SKU can have as many as you like. The app reads them all and prices "
        + "from the <b>cheapest one that can actually be bought</b> — in stock, "
        + "readable, and with a known postage cost. A supplier whose postage "
        + "cannot be read is skipped rather than counted as free.<br><br>"
        + "The template has ten columns, <i>supplier 1</i> to <i>supplier 10</i>. "
        + "Need more? Add a column headed <i>supplier 11</i>, then 12, and so on "
        + "— there is no limit."},
      {n: "3", h: "Set what you will accept",
       b: "<b>Margin</b> is profit as a share of what the customer pays. "
        + "<b>ROI</b> is profit as a share of what YOU paid. They are different "
        + "questions and give very different prices from the same cost, so there "
        + "are two boxes and both apply — the price takes whichever asks more, "
        + "so adding a target can raise a price and never lowers one.<br><br>"
        + "<b>Minimum price</b> is the backstop. It is the only guard that still "
        + "works if a supplier's page is misread, which is why no SKU can be "
        + "armed without one. <b>Hold price</b> is different: it means “this is "
        + "what the market pays”, and keeps a price there even when a target "
        + "would allow lower — but it can never hold a price below cost."},
      {n: "4", h: "Arm it, and only then turn auto-pricing on",
       b: "Two switches, deliberately. <b>Arm</b> is per SKU. <b>Auto-pricing</b> "
        + "is the master switch for the whole account. A price only moves when "
        + "both are on.<br><br>"
        + "Until then every decision is still worked out and written down, so "
        + "you can read what the app WOULD have done before trusting it. If one "
        + "looks wrong on this page, it would have been wrong on Amazon."},
    ],
    notes: [
      "<b>What the figures on each row mean.</b> <i>Cheapest source</i> is what "
      + "one unit costs you delivered — the supplier's price plus their postage. "
      + "<i>Selling price</i> is what Amazon is charging today. <i>Profit / unit</i> "
      + "is what is left after the stock and Amazon's fee. <i>Margin</i> is that "
      + "over the selling price; <i>ROI</i> is that over what you paid.",
      "<b>The “after coupon” figures</b> appear only on SKUs that have actually "
      + "been selling at a discount. Amazon does not tell this app which coupons "
      + "are running, so it is measured from what buyers were really charged on "
      + "settled orders — not read from a setting in Seller Central.",
      "<b>Nothing is added that you did not enter.</b> Postage out and an "
      + "advertising allowance are 0.00 unless you set them. The profit figures "
      + "are what the buyer paid, less the stock, less what Amazon actually took.",
      "<b>Handling time</b> is the supplier's own dispatch estimate plus a safety "
      + "buffer. That total is what would be promised to the buyer, never the "
      + "supplier's promise on its own.",
      "A price is never moved more than once every four hours, never by more than "
      + "the change cap in one step, and never below your minimum price.",
      "A SKU Amazon no longer has is marked and disarmed automatically. Its "
      + "suppliers and history are kept in case you relist it.",
      "Removing a SKU from tracking keeps its links and its price history — "
      + "enrol it again later and everything is still attached.",
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
