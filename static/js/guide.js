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
        + "name them in the <b>Which listings</b> box by row number, or paste a "
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
