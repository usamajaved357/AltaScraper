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
truthy("the rail uses them", "lsWarnTypes(r)" in PDP and "lsCheckTone" in PDP)
truthy("  and a HIGH warning is red, not amber",
       'worst === "high" ? "bad"' in LS)
truthy("  a medium one is amber", '"medium" ? "warn"' in LS)
truthy("  and low or none stays green", 'return worst === "high"' in LS)
truthy("the red state exists in the stylesheet", ".pdp-ck.bad{" in CSS)
# The row's own verdicts are not all mirrored into warnings, so ignoring them
# would swap one lie for another.
truthy("a row verdict with no warning row still colours the light",
       "restrictedHit" in PDP and "viabilityHit" in PDP)

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
      slots:[{key:"main_product_image_locator", name:"MAIN", current:""},
             {key:"other_product_image_locator_1", name:"PT01", current:""},
             {key:"other_product_image_locator_2", name:"PT02", current:""}],
      library:[{url:"/media/_acct/a/SKU-1/gen.png", name:"gen.png"}]};
const full=_pdpiBody(ROW);

// And the honest refusal when the schema could not be read.
PDPI.checked=false; PDPI.slots=[];
const noSchema=_pdpiBody(ROW);

const count=(h,re)=>(String(h).match(re)||[]).length;
console.log(JSON.stringify({
  firstIsShell: /Reading this product type/.test(first),
  sections: count(full,/pdpi-sechead/g),
  slots: count(full,/pdpi-slot"/g)+count(full,/pdpi-slot filled"/g),
  filled: count(full,/pdpi-slot filled/g),
  // One caption per tile: the row's two pictures plus the one in the library.
  thumbs: count(full,/pdpi-thumbcap/g),
  // Every tile offers the slots, and every slot the schema named is offered.
  picks: count(full,/class="pdpi-pick"/g),
  optionsPerPick: count(full,/value="other_product_image_locator_2"/g),
  hasUpload: /pdpi-drop/.test(full),
  saysNotLive: /not on Amazon yet/.test(full),
  // A slot holding a draft picture can be cleared; an empty one cannot.
  clears: count(full,/pdpImgClear/g),
  noSchemaRefuses: /Nothing is guessed at here|schema could not be read/.test(noSchema)
                   && !/pdpi-slot"/.test(noSchema),
  // A quote in a URL must not break out of the onclick.
  quoted: (function(){
    PDPI.library=[{url:"/media/a'b.png", name:"x"}];
    const h=_pdpiLibraryHtml();
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
        check("four sections", got["sections"], 4)
        check("one square per slot the schema named", got["slots"], 3)
        check("  the two the draft has assigned are filled", got["filled"], 2)
        check("  and only those can be cleared", got["clears"], 2)
        check("the row's pictures and the library are offered", got["thumbs"], 3)
        check("  each with a slot picker", got["picks"], 3)
        check("  listing every slot the type has", got["optionsPerPick"], 3)
        truthy("there is somewhere to drop a file", got["hasUpload"])
        truthy("a draft says its slots are not what Amazon holds",
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
