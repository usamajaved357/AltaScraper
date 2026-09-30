"""Bug round, 30 Sep 2026 -- ASIN Studio, Upload history, Image library, Image
refs, Image Studio, Variations and Seller import.

    "look for bugs in all screens one by one and fix them all across the app"

Each check below fails on the code as it was before the round. Functional where
the code can be run without a network or the owner's data (a throwaway database
is built for the draft test); source text where the behaviour lives in the
browser.
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

# A THROWAWAY DATABASE AND CONFIG before anything imports the store, so the
# draft test can never write into a real account.
_TMP = tempfile.mkdtemp(prefix="alta_imgbug_")
_CFG = os.path.join(_TMP, "config.json")
with open(_CFG, "w", encoding="utf-8") as fh:
    json.dump({"accounts": []}, fh)
os.environ["ALTASCRAPER_DB"] = os.path.join(_TMP, "altascraper.db")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-70s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


def read(*p):
    return open(os.path.join(HERE, *p), encoding="utf-8").read()


def js_function(src, name):
    """The full text of `function name(...) {...}` from a JS source."""
    i = src.index("function " + name + "(")
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError(name)


def node(script):
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                       timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


# ------------------------------------------------------------ ASIN Studio
print("== ASIN Studio: create-draft ==")
from flask import Flask
from routes import asin_studio_routes as _asr

_state = {"active_account_id": "acct_t"}
app = Flask("t_asin")
_asr.register(app, CONFIG_PATH=_CFG, _cfg=lambda: {}, _state=_state,
              _active_account=lambda: {"id": "acct_t"})
c = app.test_client()
body = {"id": "acct_t", "copy": {"title": "T", "bullets": ["b1"],
                                 "description": "d", "search_terms": "garden hose"},
        "brand": "Selvora", "source_asin": "B0TESTTEST", "price": "12.5",
        "handling_days": "3", "product_type": "HOSE"}
r = c.post("/asin-studio/create-draft", json=body)
check("first draft is created", r.status_code, 200)
sku = (r.get_json() or {}).get("sku")
check("  price normalised into the SKU", sku, "12.50_3Days_B0TESTTEST")
from data.store import ListingStore
row = ListingStore("acct_t", _CFG).get_row_by_sku(sku) or {}
check("  search terms are saved (real column)", row.get("Search Terms / KW"), "garden hose")
check("  product type is saved", row.get("Product Type"), "HOSE")
r2 = c.post("/asin-studio/create-draft", json=dict(body, copy=dict(body["copy"], title="OTHER")))
check("the same SKU again is refused", r2.status_code, 409)
row2 = ListingStore("acct_t", _CFG).get_row_by_sku(sku) or {}
check("  and the existing listing is untouched", row2.get("Title"), "T")
r3 = c.post("/asin-studio/create-draft", json=dict(body, price="abc"))
check("a price that is not a number is refused", r3.status_code, 400)
R = read("routes", "asin_studio_routes.py")
truthy("generate returns its findings", '"findings": findings' in R)
J = read("static", "js", "asinstudio.js")
truthy("Image Studio waits for the draft's SKU", "Create the draft first" in J)
truthy("the product type is sent", "product_type: (ASTUDIO.source || {}).product_type" in J)

# ------------------------------------------------------------ Uploads
print("\n== Upload history ==")
from routes import upload_log_routes as _ulr
app2 = Flask("t_up")
_ulr.register(app2, CONFIG_PATH=_CFG, _state={"active_account_id": "open_one"})
c2 = app2.test_client()
for path in ("/uploads/list", "/uploads/detail/1", "/uploads/file/1", "/uploads/report/1"):
    check("no account named -> refused: " + path, c2.get(path).status_code, 400)
U = read("static", "js", "uploadhistory.js")
truthy("a failed detail load is not cached as 'no rows'", "d.error" in U and "uploadsRetryDetail" in U)
truthy("replies are checked against the account asked for", "screenStillIn" in U)

# ------------------------------------------------------------ Image library
print("\n== Image library ==")
L = read("static", "js", "listingimages.js")
push = js_function(L, "ilPushLive")
truthy("push asks first, naming the SKU and the image",
       "uiConfirm" in push and "Image: " in push
       and push.index("await uiConfirm") < push.rindex("confirmed:true"))
truthy("'Use as main' refuses secondary/A+ images", "_ilBlockedMain(madeAs)" in js_function(L, "ilSetMain"))
truthy("a push to MAIN does not push a second time", "noAmazonFallback:true" in L
       and "if(opts.noAmazonFallback) return false;" in L)
truthy("_ilLoad drops a reply for a SKU no longer selected", "_stillAsked()" in js_function(L, "_ilLoad"))
LR = read("routes", "listing_routes.py")
_pi = LR.split('@app.route("/listing/push_image"')[1][:6000]
truthy("/listing/push_image applies refuse_slot", "refuse_slot(_img_slot.MAIN" in _pi)
# The inference the route uses when the page sends no made_as, run for real.
_m = re.search(r're\.search\(r"([^"]+)"', _pi)
rx = _m.group(1) if _m else ""
m1 = re.search(rx, "/media/_acct/jack_uk/SKU1/secondary/generated_1.jpg")
check("  infers 'secondary' from an account path", m1 and m1.group(1), "secondary")
m2 = re.search(rx, "/media/SKU1/aplus/premium/mobile/x.jpg")
check("  infers A+ from a legacy path", m2 and m2.group(1), "aplus/premium/mobile")
check("  a root image is not inferred as anything",
      bool(re.search(rx, "/media/_acct/jack_uk/SKU1/generated_1.jpg")), False)
from listing import images as _limg
truthy("  and refuse_slot refuses what it infers", _limg.refuse_slot(_limg.MAIN, "secondary"))
# Payload review (30 Sep 2026): the page's made_as no longer REPLACES the path
# check -- a stale "unsorted" on an aplus file must still be refused.
truthy("  the path is checked even when the page sends made_as",
       "refuse_slot(_img_slot.MAIN, _path_made)" in _pi and "if not _made:" not in _pi)
M = read("routes", "media_routes.py")
truthy("another account's media folder is checked", "_foreign_account_refusal(relpath)" in M
       and "can_access_workspace" in M)
truthy("thumbnail root check uses commonpath", "os.path.commonpath([src, root])" in M)
IL = read("static", "js", "imagelibrary.js")
truthy("the library waits for an in-flight product list", "_imgpWaitForPicker" in IL)

# ------------------------------------------------------------ Image refs
print("\n== Image refs ==")
S = read("static", "js", "settings.js")
save = js_function(S, "saveImageRef")
truthy("no save over a profile that could not be read", "_IREF_LOAD_ERR" in save)
truthy("helper fields (_...) and error are not saved back", 'k.charAt(0)==="_"' in save)
truthy("the save reply is read", "j.ok===false" in save)
truthy("the delete reply is read", "j.ok" in js_function(S, "delMedia"))
truthy("the media library checks its reply's account", "screenStillIn" in js_function(S, "loadMediaLibrary"))

# ------------------------------------------------------------ Image Studio
print("\n== Image Studio ==")
from domain import image_jobs as _ij
_ij._IMG_JOBS["t1"] = {"status": "running", "results": [], "error": "", "cancel": True}
_ij._job_finish("t1", error="stopped by user")
_ij._job_finish("t1")                          # the dispatcher's own finish
check("a stopped batch stays stopped", (_ij._IMG_JOBS["t1"]["status"],
                                         _ij._IMG_JOBS["t1"]["error"]),
      ("error", "stopped by user"))
_ij._IMG_JOBS["t2"] = {"status": "running", "results": [], "error": "", "cancel": False}
_ij._job_finish("t2")
check("  an ordinary batch still ends 'done'", _ij._IMG_JOBS["t2"]["status"], "done")
IJ = read("domain", "image_jobs.py")
truthy("auto-save files through media_kinds.folder_for", "_mk.folder_for(_kind, _tier, _variant)" in IJ)
from domain import media_kinds as _mk
check("  a phone premium module goes to its own folder",
      _mk.folder_for("aplus", "premium", "mobile"), "aplus/premium/mobile")

G = read("static", "js", "genimage.js")
H = read("static", "js", "howworks.js")
ek = js_function(G, "_studioEffectiveKind")
done = js_function(G, "_studioDoneLine")
out = node(
    "function esc(s){return String(s);}\n" + ek + "\n" + done + "\n"
    "const r={};\n"
    "r.sec=_studioEffectiveKind('concept','secondary');\n"
    "r.ap=_studioEffectiveKind('concept','aplus');\n"
    "r.src=_studioEffectiveKind('source','');\n"
    "r.stop=_studioDoneLine({status:'error',error:'stopped by user',total:4,"
    "results:[{ok:true,saved_url:'/m/x'}]});\n"
    "r.err=_studioDoneLine({status:'done',total:2,results:[{ok:true,saved_url:'/m/a'},"
    "{ok:true,save_error:'disk full'}]});\n"
    "console.log(JSON.stringify(r));")
o = json.loads(out)
check("a strategist secondary is filed as secondary", o["sec"], "secondary")
check("  a strategist A+ as aplus", o["ap"], "aplus")
check("  a cleaned source photo as main (not 'reference')", o["src"], "main")
truthy("'Done' says Stopped for a stopped batch", "Stopped" in o["stop"])
truthy("'Done' reports a save failure", "NOT saved" in o["err"] and "disk full" in o["err"])
truthy("results go to the run's own pane", "_studioEffectiveKind(kind, \"\")" in G)
truthy("_itemForSku also looks in STUDIO.items", "STUDIO.items" in js_function(G, "_itemForSku"))
truthy("Redo keeps the SKU", "const _sku = r.sku" in js_function(H, "studioReroll"))
truthy("savedUrl comes from saved_url", "savedUrl:(j.saved_url||\"\")" in H)
truthy("  and Save does not duplicate it", "if(r.savedUrl)" in js_function(H, "studioSave"))

# ------------------------------------------------------------ Variations
print("\n== Variations ==")
from listing import variations as _var
truthy("Rule 1: the GTIN exemption is never copied to a parent",
       "supplier_declared_has_product_identifier_exemption" in _var._NEVER_ON_PARENT)
kids = [{"sku": "A", "raw": {"supplier_declared_has_product_identifier_exemption":
                             [{"value": True}]}},
        {"sku": "B", "raw": {"supplier_declared_has_product_identifier_exemption":
                             [{"value": True}]}}]
pa = _var.parent_attributes(kids, "SIZE", title="X", marketplace_id="A1F83G8C2ARO7P",
                            required=["supplier_declared_has_product_identifier_exemption"])
check("  even when both children agree on it",
      "supplier_declared_has_product_identifier_exemption" in pa["attributes"], False)
VR = read("routes", "variations_routes.py")
truthy("the child's parent SKU is read from its own key", '"parent_sku": _parent_of(a)' in VR)
V = read("static", "js", "variations.js")
ap = js_function(V, "variationsApply")
truthy("a refused apply shows the server's error", "Nothing was created" in ap)
truthy("the preview sends the parent title", "parent_title:((document.getElementById(\"var_title\")" in V)

# ------------------------------------------------------------ Seller import
print("\n== Seller import ==")
SR = read("routes", "seller_routes.py")
truthy("the request's named account (routes/scope.for_request)", "_scope_mod.for_request(" in SR)
SI = read("static", "js", "sellerimport.js")
truthy("partial success is reported and the list reloaded",
       "Number(j.drafted) > 0" in SI)
truthy("a new search clears the last summary", "SIMP.screenSummary = null" in SI)
truthy("the blocked warning says the whole batch is refused",
       "refused as " in SI and "a whole" in SI)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
