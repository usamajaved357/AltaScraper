// The "buy from" panel on an order, and the out-of-stock banner.
//
// "display the source links in the order details arranged by low to high price...
//  also show handling time and profit pounds if the user place order from each
//  link what will be the profit and when will my order will be delivered"
// "add an alert in the app that whenever all the links go out of stock"
//
// The renderers are RUN here against the exact shape the server sends, rather
// than the source being read for keywords. The failures worth catching are all in
// the output: a dead link drawn as if it could be bought from, a missing profit
// printed as 0.00, an all-gone warning that does not appear.
//
// The account this was built against has had no orders for 90 days, so there was
// no live order to open -- this is what stands in for that, plus
// test_order_sources.py for the arithmetic and /sourcing/alerts checked live
// (12 real alerts on jack_uk).

const fs = require("fs");
const path = require("path");
const vm = require("vm");

let fails = [];
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails.push(label);
  console.log("  " + label.padEnd(66) +
    (ok ? "OK" : "FAIL got=" + JSON.stringify(got) + " want=" + JSON.stringify(want)));
}
function truthy(label, got) { check(label, !!got, true); }
function falsy(label, got) { check(label, !!got, false); }

// ---- load orders.js far enough to call the renderer ----------------------
const src = fs.readFileSync(path.join("static", "js", "orders.js"), "utf8");
const sandbox = {
  console: console,
  document: {getElementById: () => null, querySelectorAll: () => []},
  window: {},
  fetch: () => Promise.reject(new Error("no network in this test")),
  setTimeout: () => 0,
  toast: () => {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
try {
  vm.runInContext(src, sandbox, {filename: "orders.js"});
} catch (e) {
  console.log("  could not load orders.js: " + e.message);
  process.exit(1);
}
const render = sandbox._ordSourcesHtml;
truthy("the renderer is defined", typeof render === "function");

// ---- the exact shape /orders/detail sends --------------------------------
// Copied from the live response of domain/order_sources.options_for: three links,
// cheapest first, one of them ended.
function opt(over) {
  return Object.assign({
    source_id: 1, url: "https://www.ebay.co.uk/itm/1", label: "itm/1",
    kind: "ebay", enabled: true, state: "buyable", status: "fetched",
    checked_at: "2026-08-17 09:00:00", error: "",
    price: 11.0, shipping: 1.5, landed: 12.5, currency: "GBP",
    in_stock: true, available_qty: 33,
    carrier: "Royal Mail Tracked 48",
    postage_text: "Free Royal Mail Tracked 48",
    delivery_min: "2026-08-19", delivery_max: "2026-08-20",
    delivery_text: "Wed 19 Aug to Thu 20 Aug", delivery_postcode: "B11AA",
    dispatch_days: 3, profit: 9.0, margin_pct: 30.0, roi_pct: 72.0,
    age_minutes: 180, stale: false, rank: 1, cheapest: true,
  }, over || {});
}

const block = {
  unit_price: 30.0,
  options: [
    opt({}),
    opt({source_id: 2, url: "https://www.ebay.co.uk/itm/2", label: "itm/2",
         landed: 19.0, price: 19.0, shipping: 0, profit: 2.5, roi_pct: 13.0,
         rank: 2, cheapest: false, carrier: "Evri Tracked",
         postage_text: "Free Evri Tracked",
         delivery_text: "Mon 24 Aug", delivery_max: "2026-08-24",
         dispatch_days: 7}),
    opt({source_id: 3, url: "https://www.ebay.co.uk/itm/3", label: "itm/3",
         state: "dead", status: "gone", price: null, shipping: null,
         landed: null, in_stock: null, available_qty: null, profit: null,
         roi_pct: null, margin_pct: null, carrier: "", postage_text: "",
         delivery_text: "", delivery_postcode: "", dispatch_days: null,
         error: "HTTP 404 Not Found", rank: 3, cheapest: false}),
  ],
  summary: {total: 3, buyable: 2, dead: 1, unknown: 0, all_dead: false,
            best_profit: 9.0, best_url: "https://www.ebay.co.uk/itm/1"},
};

console.log("\n=== the panel draws all three links, in order ===");
const h = render(block);
truthy("it renders something", h && h.length > 100);
// Cheapest first: itm/1 must appear before itm/2, and itm/3 last.
const i1 = h.indexOf("itm/1"), i2 = h.indexOf("itm/2"), i3 = h.indexOf("itm/3");
truthy("all three links are on the panel", i1 >= 0 && i2 >= 0 && i3 >= 0);
truthy("  cheapest before dearer", i1 < i2);
truthy("  and the ended one last", i2 < i3);
truthy("the cheapest is labelled as such", /cheapest/.test(h));
truthy("  and the ended one is labelled gone", /gone/.test(h));

console.log("\n=== profit in pounds, per link, as asked ===");
truthy("the profit on the cheapest is shown", h.includes("9.00"));
truthy("  and on the dearer one", h.includes("2.50"));
truthy("  with the ROI beside it", h.includes("72%"));
// A MISSING PROFIT MUST NOT PRINT AS ZERO. On the dead link there is no cost, so
// there is no profit -- and 0.00 would read as "this one breaks even", which is a
// completely different statement from "we cannot say".
//
// Rendered WITHOUT unit_price for this one check: with it, the panel legitimately
// prints "the 30.00 this buyer paid", and searching the whole panel for "0.00"
// caught that instead. The assertion has to look where the claim would be, not
// anywhere on the page.
const deadOnly = render({
  options: [block.options[2]],
  summary: {total: 1, buyable: 0, dead: 1, unknown: 0, all_dead: true},
});
falsy("a link with no cost does not claim 0.00 profit", /\d\.00/.test(deadOnly));
truthy("  it shows a dash instead", deadOnly.includes("—"));

console.log("\n=== how it gets to the buyer, and when ===");
truthy("the carrier / postage line is printed",
       h.includes("Free Royal Mail Tracked 48"));
truthy("  the delivery window", h.includes("Wed 19 Aug to Thu 20 Aug"));
truthy("  the postcode it was worked out for", h.includes("B11AA"));
truthy("  the handling time", /3 days handling/.test(h));
truthy("  and how many the supplier has left", /33 left/.test(h));
// Singular, because "1 days handling" is the sort of thing that makes a screen
// look unfinished.
const one = render({unit_price: 30, summary: block.summary,
                    options: [opt({dispatch_days: 1})]});
truthy("one day is not '1 days'", /1 day handling/.test(one));
falsy("  really not", /1 days handling/.test(one));

console.log("\n=== the profit is against what THIS buyer paid ===");
// Not the current listing price. A line sold under a coupon does not earn what
// the listing earns today, and the panel says which figure it used.
truthy("the panel says what the buyer paid", /this buyer paid/.test(h));
truthy("  and names the amount", h.includes("30.00"));

console.log("\n=== every link gone: the loudest thing on the panel ===");
const gone = render({
  unit_price: 30.0,
  options: block.options.map(function (o) {
    return Object.assign({}, o, {state: "dead", profit: null, landed: null,
                                 cheapest: false});
  }),
  summary: {total: 3, buyable: 0, dead: 3, unknown: 0, all_dead: true,
            best_profit: null, best_url: ""},
});
truthy("it says every supplier is out", /Every supplier for this SKU is/.test(gone));
truthy("  and that there is nowhere to buy it", /nowhere to buy/.test(gone));
// Red, not the same amber as every other note on the screen.
truthy("  in the red style, not the ordinary one", gone.includes("#2a1414"));
// The links are still listed even though they are all dead: three ended
// suppliers is a different situation from one, and hiding them makes them look
// the same.
truthy("  the dead links are still listed", gone.indexOf("itm/3") > 0);

console.log("\n=== nothing tracked, and nothing readable ===");
const none = render({options: [], summary: {total: 0}});
truthy("no links -> it says how to add one", /Add|Repricer/.test(none));
falsy("  and does not raise an out-of-stock alarm",
      /out of stock|nowhere to buy/i.test(none));
const err = render({error: "SomeError: boom"});
truthy("a lookup failure is reported, not swallowed", /Could not read/.test(err));
check("no block at all renders nothing", render(undefined), "");
check("  and neither does null", render(null), "");

console.log("\n=== a stale reading is called out ===");
const old = render({unit_price: 30, summary: block.summary,
                    options: [opt({stale: true})]});
truthy("it says the reading is out of date", /out of date/.test(old));
truthy("  and what to do about it", /Repricer/.test(old));

console.log("\n=== the repricer shows the same facts ===");
// "i want to see this information of the source in the repricer as well".
const sjs = fs.readFileSync(path.join("static", "js", "sourcing.js"), "utf8");
const sbox = {console: console, document: {getElementById: () => null},
              window: {}, fetch: () => Promise.reject(new Error("no network")),
              setTimeout: () => 0, toast: () => {}};
sbox.window = sbox;
vm.createContext(sbox);
vm.runInContext(sjs, sbox, {filename: "sourcing.js"});
truthy("the repricer has a delivery line too",
       typeof sbox._srcDeliveryLine === "function");
const line = sbox._srcDeliveryLine({
  postage_text: "Free Royal Mail Tracked 48", carrier: "Royal Mail Tracked 48",
  delivery_min: "2026-08-19", delivery_max: "2026-08-20",
  delivery_postcode: "B11AA"});
truthy("  it prints the postage line", line.includes("Free Royal Mail Tracked 48"));
truthy("  and the same window wording as the order screen",
       line.includes("Wed 19 Aug to Thu 20 Aug"));
truthy("  and the postcode", line.includes("B11AA"));
// A check with nothing to say draws nothing at all, rather than an empty row.
check("no delivery info -> no line", sbox._srcDeliveryLine({}), "");
check("  and no check at all -> no line", sbox._srcDeliveryLine(null), "");
// THE DAY NAMES ARE WRITTEN OUT, not taken from the browser's locale: the same
// order must not read differently on two machines.
//
// Asserted by CALLING it, not by searching the source. The comment inside _srcDay
// says "rather than using toLocaleDateString", so a substring search over the
// function text matches my own explanation and fails. Third time that has caught
// me in this session -- assert on behaviour, or strip the comments first.
check("a date renders as written-out English", sbox._srcDay("2026-08-19"),
      "Wed 19 Aug");
check("  and the same on any machine", sbox._srcDay("2026-12-25"), "Fri 25 Dec");
check("  a malformed date renders nothing", sbox._srcDay("not-a-date"), "");
check("  and so does an empty one", sbox._srcDay(""), "");
const _srcDayCode = sbox._srcDay.toString().replace(/\/\/[^\n]*/g, "");
falsy("no locale-dependent formatting in the code",
      /toLocale/.test(_srcDayCode));

console.log("\n" + (fails.length ? "FAILED: " + fails.join(", ") : "all checks passed"));
process.exit(fails.length ? 1 : 0);
