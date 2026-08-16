"""The app runs without Google. That is what "independent of the sheets" means.

"if we are not using sheets make sure to delete them from there and make the app
 independent of the sheets"

Independence is not "the word Sheets does not appear anywhere" -- importing from
a spreadsheet is still a useful button, and deleting it would remove a feature
nobody asked to lose. It is that NOTHING NORMAL REQUIRES GOOGLE: the app starts,
serves, stores and publishes without gspread installed, without credentials, and
without a spreadsheet configured.

The test imports the app with gspread and google.oauth2 forced to fail, which is
the state a deployment is in when those packages are not installed.
"""
import builtins, importlib, os, sys, types

sys.path.insert(0, r"D:\AltaScraper")

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-66s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)


print("=== the app imports with Google missing ===")
_real_import = builtins.__import__
BLOCKED = ("gspread", "google.oauth2", "google.oauth2.service_account",
           "google_auth_oauthlib", "googleapiclient")

def _blocking_import(name, *a, **kw):
    if name in BLOCKED or name.startswith("gspread."):
        raise ImportError("blocked for this test: " + name)
    return _real_import(name, *a, **kw)

for m in list(sys.modules):
    if m.startswith(("gspread", "google", "dashboard")):
        sys.modules.pop(m, None)

builtins.__import__ = _blocking_import
try:
    import dashboard as D
    ok_import = True
    err = ""
except Exception as e:
    D = None
    ok_import = False
    err = "%s: %s" % (type(e).__name__, e)
finally:
    builtins.__import__ = _real_import

check("dashboard imports", ok_import, True)
if not ok_import:
    print("     %s" % err[:200])
else:
    check("  and knows Google is unavailable", getattr(D, "GOOGLE_AVAILABLE", None), False)
    check("  without pretending it has a client", D.gspread, None)
    truthy("  the app object exists", getattr(D, "app", None) is not None)

print("\n=== and it serves ===")
if ok_import:
    try:
        c = D.app.test_client()
        r = c.get("/healthz")
        if r.status_code == 404:
            r = c.get("/")
        truthy("a request is answered (%s)" % r.status_code, r.status_code < 500)
    except Exception as e:
        check("a request is answered", "raised: %s" % str(e)[:90], "no exception")

print("\n=== the store in use is the database, not a spreadsheet ===")
from data import choice as _choice
import json
CFG = r"D:\AltaScraper\config.json"
cfg = json.load(open(CFG, encoding="utf-8"))
check("backend", _choice.decide(cfg, CFG)["backend"], "db")

print("\n=== every publish path resolves the store the same way ===")
# regen opened a Google Sheet directly while everything else used output_ws, so
# a regenerated listing landed where the app never looks.
regen = open(r"D:\AltaScraper\listing\regen.py", encoding="utf-8").read()
truthy("regen uses the shared resolver", "G.output_ws(config, gc, spreadsheet_id, output_tab)" in regen)
truthy("  and no longer opens a spreadsheet itself",
       "_open_sheet_retry" not in regen and "sh.worksheet(" not in regen)
gen = open(r"D:\AltaScraper\amazon_listing_generator.py", encoding="utf-8").read()
truthy("output_ws returns the database store on this backend",
       "SheetLikeStore(ListingStore(" in gen)

print("\n=== the header does not advertise a spreadsheet ===")
shell = open(r"D:\AltaScraper\static\js\shell.js", encoding="utf-8").read()
truthy("nothing is drawn on the database backend",
       'if(window.DATA_BACKEND === "db"){\n    el.innerHTML = "";' in shell)
truthy("  no Import-from chip", "_srcChip(\"Import from\"" not in shell)
truthy("  no gid caption", "only read when you press Import" not in shell)
# The FEATURE stays -- it just lives where the importing happens.
tpl = open(r"D:\AltaScraper\templates\dashboard.html", encoding="utf-8").read()
truthy("importing from a sheet is still offered in the queue",
       "inputQueueImport(" in tpl)

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
