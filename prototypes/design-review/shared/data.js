/* FAKE DATA for the design prototypes. Every name, SKU, order and figure here is
 * invented. None of it comes from the real database or config, and nothing in
 * these prototypes talks to a server. The SHAPES follow the real app (SKU as
 * price_days_ASIN, two ASINs per row, VAT per account, costs that can be
 * missing) so the designs are tested against realistic cases. */

const P_ACCOUNTS = [
  {id: "northfield_uk", name: "Northfield Home", seller: "Seller …4Q2Z",
   mkts: ["UK", "DE"], cur: "£", vat: 0.20, colour: "#2dd4a8"},
  {id: "brightleaf_us", name: "Brightleaf Goods", seller: "Seller …7BR1",
   mkts: ["US"], cur: "$", vat: 0, colour: "#8b9cff"},
  {id: "oakline_uk", name: "Oakline Supplies", seller: "Seller …2KX9",
   mkts: ["UK"], cur: "£", vat: 0, colour: "#f0b429", empty: true},
];

/* status: draft | review | blocked | ready | submitted | live | refused */
const P_LISTINGS = [
  {acct:"northfield_uk", sku:"12.99_3Days_B0FAKE0001", title:"Bamboo Bath Mat, Non-Slip, 50x80cm",
   brand:"Northfield", status:"live", price:24.99, cost:9.40, stock:38, images:7, barcode:"5012345000017",
   sold30:61, own:"B0NF000101", ref:"B0FAKE0001", issues:[], compliance:null},
  {acct:"northfield_uk", sku:"8.50_2Days_B0FAKE0002", title:"Stainless Steel Soap Dispenser 400ml",
   brand:"Northfield", status:"live", price:16.49, cost:null, stock:12, images:6, barcode:"5012345000024",
   sold30:44, own:"B0NF000102", ref:"B0FAKE0002", issues:[], compliance:null},
  {acct:"northfield_uk", sku:"15.10_3Days_B0FAKE0003", title:"Cast Iron Grill Pan, Large, Pre-Seasoned",
   brand:"Northfield", status:"refused", price:32.99, cost:15.10, stock:0, images:5, barcode:"5012345000031",
   sold30:0, own:null, ref:"B0FAKE0003",
   issues:[{kind:"amazon", field:"item_weight",
            msg:"The attribute 'item_weight' is required but was not provided."},
           {kind:"amazon", field:"country_of_origin",
            msg:"'Pakistan (PK)' is not a valid value for country_of_origin. Use a 2-letter code."}],
   compliance:null},
  {acct:"northfield_uk", sku:"6.20_3Days_B0FAKE0004", title:"Silicone Kitchen Utensil Set (6 pieces)",
   brand:"Northfield", status:"ready", price:18.99, cost:6.20, stock:25, images:7, barcode:"5012345000048",
   sold30:0, own:null, ref:"B0FAKE0004", issues:[], compliance:null},
  {acct:"northfield_uk", sku:"4.75_5Days_B0FAKE0005", title:"Lavender Scented Candle Trio",
   brand:"Northfield", status:"blocked", price:14.99, cost:4.75, stock:30, images:4, barcode:"",
   sold30:0, own:null, ref:"B0FAKE0005",
   issues:[{kind:"identifier", field:"barcode",
            msg:"No barcode, and the GTIN exemption is not ticked. Amazon needs one or the other."}],
   compliance:{level:"gated", note:"Candles: fire-safety documents may be requested."}},
  {acct:"northfield_uk", sku:"22.00_3Days_B0FAKE0006", title:"Heated Throw Blanket, Electric, Double",
   brand:"Northfield", status:"blocked", price:49.99, cost:22.00, stock:10, images:6, barcode:"5012345000062",
   sold30:0, own:null, ref:"B0FAKE0006", issues:[],
   compliance:{level:"prohibited", note:"Electrical heated textiles: this category is restricted for this account."}},
  {acct:"northfield_uk", sku:"3.10_2Days_B0FAKE0007", title:"Microfibre Cleaning Cloths, 12 Pack",
   brand:"Northfield", status:"review", price:9.99, cost:3.10, stock:80, images:3, barcode:"5012345000079",
   sold30:0, own:null, ref:"B0FAKE0007", issues:[], compliance:null},
  {acct:"northfield_uk", sku:"5.40_3Days_B0FAKE0008", title:"Bamboo Drawer Organiser, Expandable",
   brand:"Northfield", status:"review", price:17.49, cost:5.40, stock:22, images:6, barcode:"5012345000086",
   sold30:0, own:null, ref:"B0FAKE0008", issues:[], compliance:null},
  {acct:"northfield_uk", sku:"9.99_3Days_B0FAKE0009", title:"Glass Food Storage Containers, 5 Set",
   brand:"Northfield", status:"submitted", price:27.99, cost:9.99, stock:15, images:7, barcode:"5012345000093",
   sold30:0, own:null, ref:"B0FAKE0009", issues:[], compliance:null},
  {acct:"northfield_uk", sku:"2.80_2Days_B0FAKE0010", title:"Cotton Tea Towels, Striped, 4 Pack",
   brand:"Northfield", status:"draft", price:null, cost:2.80, stock:null, images:1, barcode:"",
   sold30:0, own:null, ref:"B0FAKE0010", issues:[], compliance:null},
  {acct:"northfield_uk", sku:"11.25_3Days_B0FAKE0011", title:"Wall-Mounted Key Holder, Oak",
   brand:"Northfield", status:"live", price:21.99, cost:11.25, stock:3, images:6, barcode:"5012345000116",
   sold30:18, own:"B0NF000111", ref:"B0FAKE0011", issues:[], compliance:null},

  {acct:"brightleaf_us", sku:"7.00_3Days_B0FAKE0101", title:"Collapsible Silicone Water Bottle 20oz",
   brand:"Brightleaf", status:"live", price:19.99, cost:7.00, stock:54, images:7, barcode:"012345000101",
   sold30:73, own:"B0BL000101", ref:"B0FAKE0101", issues:[], compliance:null},
  {acct:"brightleaf_us", sku:"3.30_2Days_B0FAKE0102", title:"Reusable Beeswax Food Wraps, 6 Pack",
   brand:"Brightleaf", status:"live", price:14.99, cost:null, stock:40, images:5, barcode:"012345000102",
   sold30:29, own:"B0BL000102", ref:"B0FAKE0102", issues:[], compliance:null},
  {acct:"brightleaf_us", sku:"12.40_4Days_B0FAKE0103", title:"Bamboo Laptop Stand, Adjustable",
   brand:"Brightleaf", status:"review", price:34.99, cost:12.40, stock:14, images:6, barcode:"012345000103",
   sold30:0, own:null, ref:"B0FAKE0103", issues:[], compliance:null},
  {acct:"brightleaf_us", sku:"5.10_3Days_B0FAKE0104", title:"Stainless Steel Straws with Brush, 8 Pack",
   brand:"Brightleaf", status:"refused", price:11.99, cost:5.10, stock:0, images:4, barcode:"012345000104",
   sold30:0, own:null, ref:"B0FAKE0104",
   issues:[{kind:"amazon", field:"barcode",
            msg:"This barcode already belongs to another product (ASIN B0XXXXOTHER). Amazon matched it instead of creating yours."}],
   compliance:null},
];

/* stage: to_buy | to_ship | late | shipped | returned */
const P_ORDERS = [
  {acct:"northfield_uk", id:"206-1111111-0000001", date:"27 Sep", shipBy:"29 Sep", sku:"12.99_3Days_B0FAKE0001",
   title:"Bamboo Bath Mat, Non-Slip, 50x80cm", qty:1, total:24.99, stage:"to_buy", paid:null, tracking:"", buyer:"Customer in Leeds"},
  {acct:"northfield_uk", id:"206-1111111-0000002", date:"26 Sep", shipBy:"28 Sep", sku:"8.50_2Days_B0FAKE0002",
   title:"Stainless Steel Soap Dispenser 400ml", qty:2, total:32.98, stage:"to_ship", paid:17.00, tracking:"", buyer:"Customer in Bristol"},
  {acct:"northfield_uk", id:"206-1111111-0000003", date:"24 Sep", shipBy:"26 Sep", sku:"11.25_3Days_B0FAKE0011",
   title:"Wall-Mounted Key Holder, Oak", qty:1, total:21.99, stage:"late", paid:null, tracking:"", buyer:"Customer in Cardiff"},
  {acct:"northfield_uk", id:"206-1111111-0000004", date:"23 Sep", shipBy:"25 Sep", sku:"12.99_3Days_B0FAKE0001",
   title:"Bamboo Bath Mat, Non-Slip, 50x80cm", qty:1, total:24.99, stage:"shipped", paid:12.99, tracking:"RM 123 456 789 GB", buyer:"Customer in York"},
  {acct:"northfield_uk", id:"206-1111111-0000005", date:"20 Sep", shipBy:"22 Sep", sku:"8.50_2Days_B0FAKE0002",
   title:"Stainless Steel Soap Dispenser 400ml", qty:1, total:16.49, stage:"returned", paid:8.50, tracking:"RM 987 654 321 GB", buyer:"Customer in Hull"},
  {acct:"northfield_uk", id:"206-1111111-0000006", date:"27 Sep", shipBy:"30 Sep", sku:"12.99_3Days_B0FAKE0001",
   title:"Bamboo Bath Mat, Non-Slip, 50x80cm", qty:2, total:49.98, stage:"to_buy", paid:null, tracking:"", buyer:"Customer in Derby"},
  {acct:"brightleaf_us", id:"113-2222222-0000001", date:"27 Sep", shipBy:"30 Sep", sku:"7.00_3Days_B0FAKE0101",
   title:"Collapsible Silicone Water Bottle 20oz", qty:1, total:19.99, stage:"to_buy", paid:null, tracking:"", buyer:"Customer in Austin, TX"},
  {acct:"brightleaf_us", id:"113-2222222-0000002", date:"25 Sep", shipBy:"27 Sep", sku:"3.30_2Days_B0FAKE0102",
   title:"Reusable Beeswax Food Wraps, 6 Pack", qty:3, total:44.97, stage:"late", paid:9.90, tracking:"", buyer:"Customer in Denver, CO"},
  {acct:"brightleaf_us", id:"113-2222222-0000003", date:"22 Sep", shipBy:"24 Sep", sku:"7.00_3Days_B0FAKE0101",
   title:"Collapsible Silicone Water Bottle 20oz", qty:1, total:19.99, stage:"shipped", paid:7.00, tracking:"USPS 9400 1000 0000 0000", buyer:"Customer in Reno, NV"},
];

/* 30 days of money per account, generated the same way every time. */
function pSales(acctId){
  const a = P_ACCOUNTS.find(x => x.id === acctId) || P_ACCOUNTS[0];
  if(a.empty) return {days: [], rows: [], totals: null};
  let seed = acctId.length * 97;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const base = acctId === "northfield_uk" ? 140 : 95;
  const days = [];
  for(let i = 29; i >= 0; i--){
    const rev = Math.round((base + rnd() * base * 0.9 + (i < 7 ? 25 : 0)) * 100) / 100;
    days.push({d: i, revenue: rev, units: Math.max(1, Math.round(rev / 19))});
  }
  const revenue = days.reduce((s, x) => s + x.revenue, 0);
  const units = days.reduce((s, x) => s + x.units, 0);
  const vat = revenue - revenue / (1 + a.vat);
  const fees = revenue * 0.153;
  const ads = acctId === "northfield_uk" ? 212.40 : null;   // null = not connected
  const refunds = revenue * 0.021;
  const cogsKnown = revenue * 0.34;
  const unitsNoCost = acctId === "northfield_uk" ? 44 : 29;
  const overhead = acctId === "northfield_uk" ? 39.00 : 25.00;
  const profit = revenue - vat - fees - (ads || 0) - refunds - cogsKnown - overhead;
  return {days, totals: {revenue, units, vat, fees, ads, refunds, cogsKnown,
                         unitsNoCost, overhead, profit,
                         prevProfit: profit * 0.86}};
}

function pAcct(id){ return P_ACCOUNTS.find(a => a.id === id) || P_ACCOUNTS[0]; }
function pListings(id){ return P_LISTINGS.filter(l => l.acct === id); }
function pOrders(id){ return P_ORDERS.filter(o => o.acct === id); }

/* Profit per unit at the listing price, or null when it cannot be known.
 * UNKNOWN IS NEVER ZERO: no cost, or no price, means no profit figure. */
function pUnitProfit(l){
  if(l.price == null || l.cost == null) return null;
  const a = pAcct(l.acct);
  const net = l.price / (1 + a.vat);
  return Math.round((net - l.price * 0.153 - l.cost) * 100) / 100;
}
