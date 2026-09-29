"""The product page's bug round of 30 Sep 2026 ("check for bugs in the pdp and fix").

Owner report: "pdp does not upload images to amazon". A UI review and a
listing-payload review found the causes and a set of other defects; each fix is
pinned here so it cannot quietly come undone.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILS = []


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILS.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def yes(label, got):
    check(label, bool(got), True)


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8-sig") as f:
        return f.read()


PDP = read("static", "js", "pdp.js")
IMG = read("static", "js", "pdp_images.js")
AF = read("static", "js", "autofix.js")
SUB = read("static", "js", "submit.js")
RQ = read("static", "js", "runqueue.js")
DA = read("static", "js", "drawer_attributes.js")
GEN = read("static", "js", "pdp_imagegen.js")
LR = read("routes", "listing_routes.py")
VR = read("routes", "variations_routes.py")
SR = read("routes", "submit_routes.py")
ICSS = read("static", "css", "pdp_images.css")
PCSS = read("static", "css", "pdp.css")

print("== images reach Amazon ==")
yes("a live listing's Images tab pushes EVERY changed slot, not only Main",
    "function pdpImgPushChanged(" in IMG and "/listing/image_push" in IMG and "_pdpiChanged()" in IMG)
yes("  through the route that checks each slot against the schema",
    'if slot not in allowed:' in VR)
yes("  and Amazon's problems are passed on, not dropped", '"issues": res.get("issues") or [],' in VR)
yes("  and shown on the tab", "Amazon reports a problem with this listing" in IMG)
yes("no Push is explained, not silently missing",
    "read-only workspace: nothing can be sent" in IMG and "so the pictures go with Submit" in IMG)
yes("Push main image no longer says 'Listing not found' for a catalogue listing",
    "toast('Listing not found')" not in AF and "pdpCatalogueRow(sku)" in AF)
yes("the main-image push never files an image under a guessed 'PRODUCT' type",
    'ptype or "PRODUCT"' not in LR and "Amazon did not say what product type" in LR)
yes("  and checks the address Amazon will fetch", "_img_chk.check_url(public_url)" in LR)
yes("  and reads the app's own https /media/ address as the local path it is",
    '_own = re.match(r"^https?://([^/]+)(/media/.+)$", img, re.I)' in LR)
yes("neither push route sends somebody else's photo as the main image",
    "_iu.is_ours(CONFIG_PATH, url)" in VR and "_iu_own.is_ours(CONFIG_PATH, img)" in LR)
yes("Push sends only the slots changed here, or empty on Amazon (not every re-hosted one)",
    "return !!touched[s.key] || !s.current;" in IMG)
yes("  and a slot Amazon refused stays on the list", "failedKeys.forEach" in IMG)
yes("the precheck keeps count = main-image problems; gallery ones apart",
    '"count": len(bad),' in SR and '"other_count": len(others)' in SR)
yes("Submit warns about every gallery picture it would leave out",
    '"other_image_rows": others' in SR and "other_image_rows" in SUB)

print("\n== a link on this computer is refused ==")
from listing import images as _img  # noqa: E402
yes("127.0.0.1", _img.check_url("https://127.0.0.1:5000/img/t/a.jpg"))
yes("localhost", _img.check_url("https://localhost/img/t/a.jpg"))
check("a real public address passes", _img.check_url("https://app.altascraper.com/img/t/a.jpg"), "")

print("\n== the right account ==")
yes("Submit pins the account and marketplace across its confirms",
    "const _pin = (typeof acctId" in SUB and "rqEnqueue(sku, \"api_submit\", MINIMAL_MODE_ON, _pin)" in SUB
    and "nothing was submitted" in SUB)
yes("  and the queue names the pinned account", "acctBodyFor({sku:sku, mode:mode, minimal:!!minimal}, account)" in RQ)
yes("Push main image pins them too", "var _pin=(typeof acctId" in AF and "id:_pin}, _pin)" in AF)
yes("Push changed slots pins them too", "const pin = (typeof acctId" in IMG and "acctBodyFor({confirmed: true, sku: sku, slot: s.key" in IMG)

print("\n== nothing lost while typing, nothing closed by accident ==")
yes("late redraws wait for the field to lose focus", "function pdpRenderWhenIdle(" in PDP
    and "pdpRenderWhenIdle(sku);\n    })" in PDP.replace("\r\n", "\n")
    and "if(PDP_SKU === sku) pdpRenderWhenIdle(sku)" in PDP)
yes("  including the rebuild when Amazon's copy lands",
    re.search(r"function pdpRebuild\(sku\)\{[\s\S]{0,300}pdpRenderWhenIdle\(sku\)", PDP))
yes("Escape on a dialog or a modal does not also close the page",
    "if(ev.defaultPrevented) return;" in PDP and ".modalwrap.open" in PDP)

print("\n== what the page shows is what it acts on ==")
yes("  and asks before replacing the draft's own bullets", "async function _bulletsMayReplace(" in AF and AF.count("await _bulletsMayReplace(sku, r, list)") >= 3)
yes("bullet up/down/delete/add act on the bullets on screen",
    "function _bulletsShown(" in AF and AF.count("_bulletsShown(sku, r)") >= 3)
yes("Fill from Amazon counts exactly what it copies", "function lvFillTodo(" in DA
    and "const todo = lvFillTodo(sku);" in DA and "_nFillFn(sku).length" in PDP)
yes("  and the one-field 'use Amazon's' refuses the same keys", "!lvFillable(key)" in DA)
yes("  and never copies the barcode or the GTIN-exemption declaration (Rule 1)",
    re.search(r"function lvFillable[\s\S]{0,200}product_identifier[\s\S]{0,40}gtin", DA))
yes("the hero barcode is locked where the Offer tab locks it",
    "function pdpBarcodeLocked(" in PDP and "pdpBarcodeLocked(r) ? 'readonly" in PDP)
yes("the Attributes filter starts fresh on another listing", 'PDP_ATTR_FILTER = "all";' in PDP)
yes("closing the page forgets the Images tab's reading",
    re.search(r"function pdpClose\(opts\)\{[\s\S]{0,400}pdpImagesForget\(\)", PDP))
yes("a catalogue listing's link reopens", "? pdpCatalogueRow(sku) : null);" in PDP)
yes("'Try again' works on a catalogue listing", "pdpCatalogueRow(sku) : null)" in DA)
yes("Sync this listing refreshes the checks and images",
    "pdpRender(); pdpAfterAction(sku);" in PDP)
yes("the image generator is busy per listing, from before the planning call",
    "PDPIG.busy[_key] = true;" in GEN and "if(!_started) delete PDPIG.busy[_key];" in GEN)

print("\n== keyboard and phone ==")
yes("every clickable panel gets a tab stop and a role", "function _pdpKeyable(" in PDP and "_pdpKeyable(host);" in PDP)
yes("  and Enter / Space press it", "_pdpKeyPress(ev)" in PDP)
yes("slot x and library delete show without hover (phones)", "@media (hover:none)" in ICSS)
yes("the page fits Safari's visible height", "100dvh" in PCSS)
yes("save and finish commits a contenteditable field too", "|| a.isContentEditable)) a.blur();" in PDP)


print("\n== behaviour: what 'Fill from Amazon' may copy ==")
import subprocess  # noqa: E402
_JS = r"""
const fs=require("fs"); const src=fs.readFileSync("static/js/drawer_attributes.js","utf8");
const i=src.indexOf("function lvFillable("); const f=new Function("return "+src.slice(i, src.indexOf("\n}",i)+2))();
const out={}; ["supplier_declared_has_product_identifier_exemption","externally_assigned_product_identifier",
 "main_product_image_locator","other_product_image_locator_3","merchant_suggested_asin","item_name","material"]
 .forEach(k=>out[k]=f(k)); console.log(JSON.stringify(out));
"""
import json as _json  # noqa: E402
_r = subprocess.run(["node", "-e", _JS], cwd=HERE, capture_output=True, text=True)
_v = _json.loads(_r.stdout or "{}")
check("the GTIN-exemption declaration is never copied (Rule 1)",
      _v.get("supplier_declared_has_product_identifier_exemption"), False)
check("  nor the barcode", _v.get("externally_assigned_product_identifier"), False)
check("  nor an image slot", _v.get("other_product_image_locator_3"), False)
check("  nor merchant_suggested_asin (Rule 1)", _v.get("merchant_suggested_asin"), False)
check("an ordinary field is", _v.get("material"), True)
print("\nFAILURES: %d" % len(FAILS) if FAILS else "\nFAILURES: 0")
sys.exit(1 if FAILS else 0)
