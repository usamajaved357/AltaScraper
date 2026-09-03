"""The Amazon-style detailed listings view, and the six things asked of it.

The renderer is EXECUTED with real row shapes, not just parsed: a view that
throws renders as an empty panel with nothing in the console to say why.

THE MOCKUP IS listings-amazon-style-mockup.html and its values are the design.
Where this departs from it, the owner asked for the departure and the test says
which:

  1  a light GREY ground, not the mockup's pure white
  2  handling days, which the mockup has no column for and the app has always
     shown
  3  a symbol each for restricted / compliance / claim risk
  4  what Amazon said about the last submit -- an API error or another kind
  5  an EAN already used on an existing listing, named
  6  the brand

AND ONE THING DELIBERATELY NOT BUILT: the mockup's favourite star. There is no
favourite anywhere in this app -- not on a row, not in the listings table, not
in a route -- so a star would light up and forget itself on the next render.
A control that lies about having saved something is worse than no control
(CLAUDE.md Rule 4).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-66s %s" % (label, "OK" if ok else "FAIL got=%r want=%r"
                                                 % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def falsy(label, got):
    check(label, bool(got), False)


JS = open(os.path.join(HERE, "static", "js", "listrow_detailed.js"),
          encoding="utf-8").read()
CSS = open(os.path.join(HERE, "static", "css", "listrow_detailed.css"),
           encoding="utf-8").read()

print("=== the file is clean UTF-8 ===")
# A PowerShell round-trip double-encoded this file's dashes and box rules once.
# It was repaired; this stops it shipping if it happens again.
truthy("no mojibake left in the renderer",
       not re.search(r"â€|Â·|â•", JS))
falsy("and no byte-order mark", JS.startswith("﻿"))

print("\n=== 1. a light grey ground, not white ===")
truthy("the table is grey, not #fff", "background:#fafafa" in CSS)
falsy("  no pure-white row background survives",
      re.search(r"\.inv-table\{[^}]*background:#fff\b", CSS) is not None)
truthy("  and the header is a step darker so it still reads as one",
       "background:#efefef" in CSS)
# The mockup's own accents are kept exactly -- they were chosen against a light
# ground and still work on one.
for hexv in ("#008296", "#067D62", "#B12704", "#C45500", "#e7e7e7", "#111"):
    truthy("keeps the mockup's %s" % hexv, hexv in CSS)

print("\n=== the mockup's structure ===")
truthy("a real table, as the mockup has", "inv-table" in JS and "<thead" in JS)
for col in ("col-cb", "col-status", "col-product", "col-perf", "col-inv",
            "col-price", "col-fees", "col-actions"):
    truthy("column %s" % col, col in JS and ("." + col) in CSS)
truthy("a sort bar with a count and a picker",
       "lr-sortbar" in CSS and "function lrSortBar(" in JS)
truthy("  which sorts a COPY, leaving the grid's own order alone",
       "rows || []).slice()" in JS)
falsy("no favourite star, because there is no favourite to save",
      re.search(r'class="[^"]*\bstar\b', JS) is not None)

print("\n=== 2..6: what was asked for on top of the mockup ===")
truthy("2. handling days are on the row", "function lrInv(" in JS
       and "_handCell" in JS)
truthy("   through listings.js's own cell, not a second copy",
       "_handCell(r)" in JS)
truthy("3. three risk symbols", "function lrRisks(" in JS)
truthy("   restricted, compliance and claims", "ti-ban" in JS
       and "ti-file-description" in JS and "ti-quote" in JS)
truthy("   coloured by the shared warnings reader",
       "lsWarnTypes" in JS and "lsCheckTone" in JS)
truthy("4. what Amazon said about the submit", "function lrAmazonSaid(" in JS)
truthy("   told apart by STATUS, not by reading the prose",
       'raw === "API_ERROR"' in JS and 'raw === "SUBMITTED"' in JS
       and 'raw === "API_READY"' in JS)
truthy("5. a clashing EAN is reported", "function lrEanClash(" in JS)
truthy("   from the warnings that already answer it",
       "barcode_live_on_amazon" in JS and "duplicate_barcode" in JS)
truthy("   naming the ASIN or SKU that owns it",
       "live_asin" in JS and "existing_sku" in JS)
truthy("6. the brand is shown", "Brand " in JS and "r.brand" in JS)

print("\n=== the renderer actually runs ===")
probe = r"""
const fs=require("fs"), vm=require("vm");
globalThis.window=globalThis;
globalThis.esc=s=>String(s==null?"":s).replace(/[&<>"']/g,
  c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
globalThis.CUR_SYMBOL="£";
globalThis.SELECTED=new Set();
globalThis.ROWS=[];
globalThis.rowSelectBox=()=>'<input type="checkbox">';
globalThis.rowActions=()=>'<i class="ti ti-dots"></i>';
globalThis.rowAsin=r=>({own:r.live_asin||"", source:r.competitor_asin||""});
globalThis._rowImages=r=>(r.img?[r.img]:[]);
globalThis._dwCost=r=>(r.cost?("£"+r.cost):"");
globalThis._dpUrl=a=>"https://amazon.co.uk/dp/"+a;
globalThis._handCell=r=>'<span class="tilefact">'+(r.handling_days||"?")+'d (ours)</span>';
globalThis.lsStatusOf=r=>String(r.status||"").toUpperCase();
globalThis.lsWasSentToAmazon=r=>!!r.live_asin;
globalThis.lsWarnings=r=>({n:(r.warnings||[]).length});
globalThis.lsWarnTypes=r=>{const o={};(r.warnings||[]).forEach(w=>{
  const t=w.type||"other";let s=(w.severity||"low");
  const e=o[t]||(o[t]={n:0,worst:""});e.n++;
  if(e.worst!=="high") e.worst=(s==="high")?"high":(e.worst==="medium"?"medium":s);});
  return o;};
globalThis.lsCheckTone=(types,keys)=>{let w="";(keys||[]).forEach(k=>{const e=(types||{})[k];
  if(!e)return; if(e.worst==="high")w="high"; else if(e.worst==="medium"&&w!=="high")w="medium";});
  return w==="high"?"bad":(w==="medium"?"warn":"ok");};
globalThis.lsCheckCount=(types,keys)=>{let n=0;(keys||[]).forEach(k=>{n+=(((types||{})[k])||{}).n||0;});return n;};
vm.runInThisContext(fs.readFileSync("static/js/listrow_detailed.js","utf8"),
                    {filename:"listrow_detailed.js"});

// A live listing with a HIGH compliance warning and an EAN Amazon already has.
const live={sku:"9.18_3Days_B0C6XTNXL8", title:"Floor Scrub Brush",
  status:"LIVE", brand:"Green Haven", barcode:"4553334465572",
  live_asin:"B0H8VHDX8B", price:"24.99", cost:"9.18", profit:"8.57",
  handling_days:3, img:"https://x/a.jpg",
  warnings:[{type:"compliance_risk",severity:"high",message:"needs docs"},
            {type:"barcode_live_on_amazon",severity:"medium",
             message:"already live", live_asin:"B0HZZZ1111"}]};
// A draft Amazon rejected, no brand, no barcode, no warnings at all.
const draft={sku:"8.00_3Days_B0G1K5B7QS", title:"Cutter", status:"API_ERROR",
  notes:"API SUBMIT REJECTED by Amazon (3 error(s)): brand is required",
  competitor_asin:"B0G1K5B7QS", price:"", handling_days:2};

const rowLive=detailedRow(live), rowDraft=detailedRow(draft);
const block=detailedBlock([live,draft]);
const head=detailedHead([live,draft]);
const n=(h,re)=>(String(h).match(re)||[]).length;
console.log(JSON.stringify({
  cells: n(rowLive,/<td/g),
  isTable: /<table class="inv-table">/.test(block) && /<tbody>/.test(block),
  // `<th ` with the space: /<th/ also matches the <thead> that wraps them.
  headCols: n(head,/<th /g),
  sortBar: /lr-sortbar/.test(block),
  // 2 handling
  handLive: /3d \(ours\)/.test(rowLive), handDraft: /2d \(ours\)/.test(rowDraft),
  // 3 three symbols on BOTH rows, red where the warning is high
  risksLive: n(rowLive,/class="lr-risk /g), risksDraft: n(rowDraft,/class="lr-risk /g),
  complianceRed: /lr-risk bad/.test(rowLive),
  allGreyOnDraft: n(rowDraft,/lr-risk none/g),
  // 4 Amazon's verdict
  amzBad: /Amazon rejected — 3 errors/.test(rowDraft),
  amzQuotes: /brand is required/.test(rowDraft),
  amzSilentWhenNothingSent: !/lr-amz/.test(rowLive),
  // 5 the EAN clash, naming the ASIN
  clash: /already on ASIN B0HZZZ1111/.test(rowLive),
  clashRed: /prod-ean clash/.test(rowLive),
  noClashOnDraft: !/lr-eanclash/.test(rowDraft),
  // 6 brand
  brandLive: /Brand <strong>Green Haven<\/strong>/.test(rowLive),
  brandMissing: /Brand <span class="prod-dim">not set/.test(rowDraft),
  // price box is editable and saves through the one save path
  priceBox: /class="price-input-wrap"/.test(rowLive) && /saveEdit\(this/.test(rowLive),
  // a draft has no performance to report and says so
  draftNotLive: /Not yet live/.test(rowDraft),
  // an unknown figure is a dash, never a zero
  dashes: n(rowDraft,/class="dash"/g) > 0
}));
"""
try:
    fd, path = tempfile.mkstemp(suffix=".js", dir=HERE)
    os.write(fd, probe.encode("utf-8"))
    os.close(fd)
    out = subprocess.run(["node", path], capture_output=True, text=True, cwd=HERE)
    os.unlink(path)
    if out.returncode != 0:
        FAILS.append("the renderer threw")
        print("  FAIL the renderer threw:", (out.stderr or "")[:400])
    else:
        g = json.loads(out.stdout.strip().splitlines()[-1])
        check("eight cells per row", g["cells"], 8)
        truthy("a real table with a body", g["isTable"])
        check("  eight columns in the header", g["headCols"], 8)
        truthy("  and a sort bar above it", g["sortBar"])
        truthy("2. handling on a live row", g["handLive"])
        truthy("   and on a draft", g["handDraft"])
        check("3. three symbols on a live row", g["risksLive"], 3)
        check("   three on a draft too, so a gap is never a missing icon",
              g["risksDraft"], 3)
        truthy("   a HIGH compliance warning turns one red", g["complianceRed"])
        check("   a row with no warnings shows three grey", g["allGreyOnDraft"], 3)
        truthy("4. a rejected draft says so, with the count", g["amzBad"])
        truthy("   and carries Amazon's own words", g["amzQuotes"])
        truthy("   a row that was never submitted says nothing",
               g["amzSilentWhenNothingSent"])
        truthy("5. the clashing EAN names the ASIN that owns it", g["clash"])
        truthy("   and the number itself is marked", g["clashRed"])
        truthy("   a row with no clash says nothing", g["noClashOnDraft"])
        truthy("6. the brand is shown", g["brandLive"])
        truthy("   and 'not set' when there is none", g["brandMissing"])
        truthy("the price is editable and saves the one way", g["priceBox"])
        truthy("a draft reports no performance rather than four dashes",
               g["draftNotLive"])
        truthy("an unknown figure is a dash", g["dashes"])
except FileNotFoundError:
    print("  (node not on this machine -- renderer not exercised)")
except Exception as e:
    FAILS.append("renderer probe")
    print("  FAIL renderer probe:", str(e)[:300])

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
