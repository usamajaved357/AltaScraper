"""The product page: images tab, checks rail, button order and page width.

The renderer is EXECUTED, not just parsed. node --check proves the file is
valid JavaScript and nothing else -- the stray-token bug in orders.js parsed
fine and threw at runtime, and a tab that throws renders as an empty box with
no clue why.

WHAT IS BEING GUARDED

  the slots are Amazon's      /listing/image_slots reads the product type's own
                              schema (getDefinitionsProductType). A slot list
                              written into this app would be rejected on Submit
                              as an attribute nobody recognises, so when the
                              schema cannot be read the section says so and
                              offers nothing (CLAUDE.md Rule 4).

  no new endpoints            assigning, uploading, listing and deleting all go
                              through routes that already existed and are used
                              by other screens (Rule 12).

  the rail cannot lie         "The left sidebar shows Restricted, Compliance,
                              and Claim risks all as GREEN — but Compliance tab
                              shows 2 HIGH warnings." The rail read three row
                              fields and the tab read r.warnings. Both read
                              r.warnings now, through liststatus.js.
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


JS = open(os.path.join(HERE, "static", "js", "pdp_images.js"),
          encoding="utf-8").read()
PDP = open(os.path.join(HERE, "static", "js", "pdp.js"), encoding="utf-8").read()
LS = open(os.path.join(HERE, "static", "js", "liststatus.js"),
          encoding="utf-8").read()
CSS = open(os.path.join(HERE, "static", "css", "pdp.css"), encoding="utf-8").read()
HTML = open(os.path.join(HERE, "templates", "dashboard.html"),
            encoding="utf-8").read()

print("=== 1. the page fills the page ===")
# Three caps were leaving ~800px blank either side of a 720px column.
# THE FIRST MATCH IS NOT THE RULE. `.pdp-layout` is written twice -- the phone
# override (flex-direction:column, inside @media max-width:700px) comes FIRST in
# the file, so splitting on the name reads the one that does not apply on a
# desktop. The same trap test_layout_density.py's rules() helper exists for.
_layout = [b for b in re.findall(r"\.pdp-layout\{([^}]*)\}", CSS)
           if "overflow-y" in b or "max-width" in b or "display:flex" in b]
_layout = _layout[0] if _layout else ""
falsy("the layout is no longer capped at 1100px", "max-width:1100px" in _layout)
_content = CSS.split(".pdp-content{")[1].split("}")[0]
falsy("  nor the content at 720px", "max-width:720px" in _content)
# 24-32px was right for a full-bleed page. PDP_REDESIGN_TASK.md narrowed the
# panel to 680px and named the new padding itself ("Main content area: 12px
# 16px") -- at that width, 28px of padding either side is a tenth of the panel
# spent on nothing. The check that matters is unchanged: the content is not
# capped, and it is not flush against the edge.
truthy("  and the padding is the 12px 16px asked for",
       re.search(r"padding:12px 16px", _content) is not None)
_hero = CSS.split(".pdp-hero-in{")[1].split("}")[0]
falsy("  the hero is not centred in a narrower column either",
      "max-width:900px" in _hero)
truthy("the sidebar still sits directly against the content",
       "gap:0" in _layout)
# AND THE LAYOUT IS NOW THE ONE THING THAT SCROLLS. The top bar, the hero, the
# tabs and the footer are its flex siblings, so they cannot scroll away --
# "the top bar and tabs ... should stay pinned at the top of the PDP panel
# while the content below scrolls". min-height:0 is what lets a flex item
# shrink below its content and actually scroll.
truthy("  and it is the panel's scroller",
       "overflow-y:auto" in _layout and "min-height:0" in _layout)

print("\n=== 2. the checks rail reads the same warnings as the tab ===")
truthy("there is one warnings-by-type reader", "function lsWarnTypes(" in LS)
truthy("  and one place that turns a type into a colour",
       "function lsCheckTone(" in LS)
# The rail's four verdicts moved into liststatus.js as lsCheckStates on 26 Sep
# 2026 -- the Safety tab's badges read the same function -- and it is built on
# lsWarnTypes / lsCheckTone there.
truthy("the rail uses them", "lsCheckStates(r)" in PDP
       and "lsWarnTypes(r)" in LS and "lsCheckTone(wt," in LS)
truthy("  and a HIGH warning is red, not amber",
       'worst === "high" ? "bad"' in LS)
truthy("  a medium one is amber", '"medium" ? "warn"' in LS)
truthy("  and low or none stays green", 'return worst === "high"' in LS)
truthy("the red state exists in the stylesheet", ".pdp-ck.bad{" in CSS)
# The row's own verdicts are not all mirrored into warnings, so ignoring them
# would swap one lie for another.
# And COUNTED from the lists: `matched` is a boolean, so the old
# `matched.length` test never fired (lsRestrictedHits / lsViabilityHits).
truthy("a row verdict with no warning row still colours the light",
       "function lsRestrictedHits(" in LS and "function lsViabilityHits(" in LS
       and "(x.matches || []).length" in LS and "(x.risks || []).length" in LS)
falsy("  never by .matched.length, which a boolean does not have",
      ".matched.length" in LS or ".matched.length" in PDP)

print("\n=== 3. the buttons sit next to Back, the overflow menu on the right ===")
_top = PDP.split("const top = ")[1].split("// A BLOCKING PROBLEM")[0]
_order = [m for m in re.findall(r"pdp-back|previewOne|autoFixLoop|submitOne"
                                r"|pdp-spacer|drawerMore", _top)]
check("Back, Preview, Auto-fix, Submit, then the spacer, then the menu",
      _order, ["pdp-back", "previewOne", "autoFixLoop", "submitOne",
               "pdp-spacer", "drawerMore"])
truthy("they are still in the top bar, not under the title",
       'class="pdp-top"' in _top)

print("\n=== 4. the images tab ===")
truthy("it is its own file, not more of pdp.js",
       os.path.exists(os.path.join(HERE, "static", "js", "pdp_images.js")))
truthy("  and pdp.js only calls into it", "pdpImagesTab(r)" in PDP)
truthy("  loaded by the page", "pdp_images.js" in HTML and "pdp_images.css" in HTML)

# RULE 12: every call goes to a route that already existed.
for route in ("/listing/image_slots", "/edit", "/media/list", "/media/upload",
              "/media/delete"):
    truthy("uses the existing %s" % route, '"%s' % route in JS)
falsy("and invents no endpoint of its own",
      re.search(r'fetch\("/(?!listing/image_slots|edit|media/)', JS) is not None)
# ONE ROUTE WAS ADDED, on purpose (the owner's redesign, 26 Sep 2026): the
# competitor strip's eBay / Amazon pictures. It is read-only and fetches them
# through the two fetchers the app already had -- fetch_ebay_supplement and the
# /catalog/lookup view -- so it is a door, not a second implementation.
truthy("the competitor strip reads /listing/competitor_images",
       '"/listing/competitor_images?sku="' in JS)
_LR = open(os.path.join(HERE, "routes", "listing_routes.py"), encoding="utf-8").read()
_ci = _LR.split("def listing_competitor_images(")[1].split("@app.route")[0]
truthy("  which reuses fetch_ebay_supplement", "fetch_ebay_supplement(" in _ci)
truthy("  and the /catalog/lookup view", 'view_functions.get("catalog_lookup")' in _ci)
truthy("  and answers for the account the page names", "_store_for(" in _ci)

# RULE 4: the slots come from the schema, and their absence is said out loud.
truthy("the slot list comes from the schema route",
       "/listing/image_slots?" in JS)
falsy("  no slot names are written into this file",
      re.search(r'\["MAIN"|PT01.*PT02|"SWATCH"', JS) is not None)
truthy("  and an unreadable schema offers nothing rather than guessing",
       "Nothing is guessed at here" in JS)

# The draft is what Submit sends, so that is what assigning writes to.
truthy("assigning writes the draft attribute Submit reads",
       'target: "attr"' in JS)
truthy("  and says so rather than implying it reached Amazon",
       "does not push to Amazon" in JS or "what Submit will send" in JS)

# A generated picture is saved into this SKU's library, so the tab re-reads it
# then -- it used to appear only after a DIFFERENT listing had been opened.
_AF = open(os.path.join(HERE, "static", "js", "autofix.js"), encoding="utf-8").read()
_dogen = _AF[_AF.index("function doGen("):]
_dogen = _dogen[:_dogen.index("\nfunction ")]
truthy("the library can be re-read from outside the tab",
       "async function pdpImagesLibraryReload(sku)" in JS)
truthy("  and the generator does so once its result is saved",
       re.search(r"/media/upload[\s\S]*pdpImagesLibraryReload\(sku\)", _dogen) is not None)

print("\n=== the renderer actually runs ===")
probe = r"""
const fs=require("fs"), vm=require("vm");
globalThis.window=globalThis;
globalThis.esc=s=>String(s==null?"":s).replace(/[&<>"']/g,
  c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
globalThis.toast=function(){};
globalThis.document={getElementById:()=>null};
globalThis.fetch=()=>Promise.resolve({json:()=>Promise.resolve({ok:true})});
globalThis.ROWS=[];
// listings.js supplies this on the real page; the tab reads the row's pictures
// through it rather than parsing attributes a second way.
globalThis._rowImages=function(r){
  const a=(r&&r.attributes)||{};
  return Object.keys(a).filter(k=>/image_locator/.test(k)).sort().map(k=>a[k]);
};
vm.runInThisContext(fs.readFileSync("static/js/pdp_images.js","utf8"),
                    {filename:"pdp_images.js"});
globalThis.pdpRow=()=>ROW;

// A draft: two pictures in attributes, nothing live on Amazon.
const ROW={sku:"SKU-1", product_type:"SQUEEGEE", attributes:{
  main_product_image_locator:"https://x/one.jpg",
  other_product_image_locator_1:"https://x/two.jpg"}};

// First call: no state for this sku yet, so it returns the loading shell.
const first=pdpImagesTab(ROW);

// Now with slots loaded, as the route would answer for a draft.
PDPI={sku:"SKU-1", productType:"SQUEEGEE", live:false, checked:true, note:"",
      err:"", loading:false, dragUrl:"",
      // THE SHAPE /listing/image_slots REALLY SENDS: `label`, never `name`
      // (listing/images.py slots_from_schema). This fixture used `name`, which
      // is why the screen's raw-key slot names never showed up here.
      slots:[{key:"main_product_image_locator", label:"Main image", current:""},
             {key:"other_product_image_locator_1", label:"PT1", current:""},
             {key:"other_product_image_locator_2", label:"PT2", current:""},
             {key:"image_locator_eeuk", label:"UK Energy Label", current:""}],
      library:[{url:"/media/_acct/a/SKU-1/gen.png", name:"gen.png"}],
      // The strip on its Library tab, and a competitor answer beside it.
      comp:{ebay:["https://e/1.jpg"], amazon:[], ebay_error:"", amazon_error:"no ASIN"},
      compTab:"library", compLoading:false};
const full=_pdpiBody(ROW);
PDPI.compTab="ebay";
const ebay=_pdpiBody(ROW);
PDPI.compTab="amazon";
const amazon=_pdpiBody(ROW);
PDPI.compTab="library";

// And the honest refusal when the schema could not be read.
PDPI.checked=false; PDPI.slots=[];
const noSchema=_pdpiBody(ROW);

const count=(h,re)=>(String(h).match(re)||[]).length;
console.log(JSON.stringify({
  firstIsShell: /Reading this product type/.test(first),
  sections: count(full,/pdpi-sechead/g),
  slots: count(full,/pdpi-slot"/g)+count(full,/pdpi-slot filled"/g),
  filled: count(full,/pdpi-slot filled/g),
  // The Library tab shows the one library picture; eBay its one; Amazon says
  // why it has none rather than drawing nothing.
  thumbs: count(full,/class="pdpi-thumb"/g),
  ebayThumbs: count(ebay,/class="pdpi-thumb"/g),
  amazonSaysWhy: /no ASIN/.test(amazon),
  // Click fills the next empty slot -- no dropdown any more.
  clickFills: /onclick="pdpImgFillNext\(/.test(full),
  picks: count(full,/class="pdpi-pick"/g),
  fillAll: /pdpImgFillAll\(\)/.test(full),
  statusLine: /2 of 4 slots filled/.test(full),
  hasUpload: /onchange="pdpImgUpload\(this\)"/.test(full),
  saysNotLive: /go live when you submit/.test(full),
  // A slot holding a draft picture can be cleared; an empty one cannot.
  clears: count(full,/pdpImgClear/g),
  slotNames: (String(full).match(/pdpi-slotname">([^<]*)</g)||[])
               .map(s=>s.replace(/^pdpi-slotname">/,"").replace(/<$/,"")),
  rawKeyShown: />main_product_image_locator</.test(full)
               || />other_product_image_locator_\d/.test(full),
  noSchemaRefuses: /Nothing is guessed at here|schema could not be read/.test(noSchema)
                   && !/pdpi-slot"/.test(noSchema),
  // A quote in a URL must not break out of the onclick.
  quoted: (function(){
    PDPI.library=[{url:"/media/a'b.png", name:"x"}];
    PDPI.compTab="library";
    const h=_pdpiStripHtml();
    return h.indexOf("a\\'b.png")>=0;
  })()
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
        got = json.loads(out.stdout.strip().splitlines()[-1])
        truthy("the first draw is a loading shell, not a blank tab",
               got["firstIsShell"])
        # TWO SECTIONS since the owner's redesign (26 Sep 2026): slots, and the
        # one competitor strip. The generator is its own section outside this
        # repainted box (pdp_imagegen.js); upload is a button on the status line.
        check("two sections", got["sections"], 2)
        check("one square per slot the schema named", got["slots"], 4)
        check("  named the way Seller Central names them", got["slotNames"],
              ["Main", "PT01", "PT02", "UK Energy Label"])
        falsy("  never the raw attribute key", got["rawKeyShown"])
        check("  the two the draft has assigned are filled", got["filled"], 2)
        check("  and only those can be cleared", got["clears"], 2)
        truthy("  and the status line counts them", got["statusLine"])
        check("the Library tab shows the library", got["thumbs"], 1)
        check("the eBay tab shows eBay's pictures", got["ebayThumbs"], 1)
        truthy("  a source with none says why", got["amazonSaysWhy"])
        truthy("clicking a picture fills the next empty slot", got["clickFills"])
        check("  with no slot dropdown any more", got["picks"], 0)
        truthy("  and one button fills them all", got["fillAll"])
        truthy("there is an Upload image button", got["hasUpload"])
        truthy("a draft says its slots go live on Submit, not now",
               got["saysNotLive"])
        truthy("an unreadable schema draws no slots at all",
               got["noSchemaRefuses"])
        truthy("a quote in a filename cannot break out of the onclick",
               got["quoted"])
except FileNotFoundError:
    print("  (node not on this machine -- renderer not exercised)")
except Exception as e:
    FAILS.append("renderer probe")
    print("  FAIL renderer probe:", str(e)[:200])

print("\n=== the slots route answers for a draft, not just a live listing ===")
VR = open(os.path.join(HERE, "routes", "variations_routes.py"),
          encoding="utf-8").read()
_fn = VR.split("def listing_image_slots(")[1].split("\n    @app.route")[0]
truthy("it accepts a product type", 'request.args.get("product_type")' in _fn)
truthy("  and no longer refuses every unsubmitted listing",
       "and not asked_pt" in _fn)
truthy("  saying whether the live listing could be read",
       '"live": live is not None' in _fn)
truthy("  through the same slots_from_schema as before",
       "_img.slots_from_schema(sch)" in _fn)

print("\nFAILURES: %d" % len(FAILS))
for f in FAILS:
    print("  - " + f)
raise SystemExit(1 if FAILS else 0)
