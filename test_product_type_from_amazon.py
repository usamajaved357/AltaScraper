# -*- coding: utf-8 -*-
"""Product types come from Amazon: the drawer's search, and fixing drafts.

    "why am i seeing that error on almost all of my listings"
    "i see a very limited products type to select from the pdp in the app"
    "fix the product types from amazon, and build the search"

Amazon's replies were MEASURED before any of this was written (see the notes in
api/amazon_catalog.py). These checks feed those exact reply shapes and error
kinds through the real functions and the real routes -- nothing reaches Amazon,
and the database is a throwaway one in a temp directory.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

FAILS = []


def check(name, got, want):
    if got == want:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s   got=%r want=%r" % (name, got, want))
        FAILS.append(name)


# ============================================================ Amazon's replies
print("== api/amazon_catalog reads Amazon's reply as measured ==")
from api import amazon_catalog as C
import sp_api.api as SP


class _Res:
    def __init__(self, payload):
        self.payload = payload


class _Err(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class SellingApiForbiddenException(_Err):
    pass


class SellingApiNotFoundException(_Err):
    pass


def fake_catalog(reply):
    class _Cl:
        def __init__(self, **kw):
            pass

        def get_catalog_item(self, asin, **kw):
            if isinstance(reply, Exception):
                raise reply
            return _Res(reply)
    return _Cl


def fake_ptd(reply, seen):
    class _Cl:
        def __init__(self, **kw):
            pass

        def search_definitions_product_types(self, **kw):
            seen.update(kw)
            if isinstance(reply, Exception):
                raise reply
            return _Res(reply)
    return _Cl


MID = "A1F83G8C2ARO7P"
real_cat, real_ptd = SP.CatalogItemsV20220401, SP.ProductTypeDefinitions
try:
    SP.CatalogItemsV20220401 = fake_catalog(
        {"asin": "B0DNYVCK4J",
         "productTypes": [{"marketplaceId": MID, "productType": "TABLE"}]})
    got = C.product_type_of({}, "UK", MID, "b0dnyvck4j")
    check("the camping table is TABLE", (got["status"], got["product_type"]), ("ok", "TABLE"))

    SP.CatalogItemsV20220401 = fake_catalog(
        {"productTypes": [{"marketplaceId": "A13V1IB3VIYZZH", "productType": "CHAIR"},
                          {"marketplaceId": MID, "productType": "STOOL_SEATING"}]})
    check("  the entry for THIS marketplace is the one read",
          C.product_type_of({}, "UK", MID, "B00TKIAZWG")["product_type"], "STOOL_SEATING")

    SP.CatalogItemsV20220401 = fake_catalog(SellingApiNotFoundException(
        404, "Requested item, B000000000, not found in marketplace(s)"))
    check("a missing ASIN is not_found, not a crash",
          C.product_type_of({}, "UK", MID, "B000000000")["status"], "not_found")

    SP.CatalogItemsV20220401 = fake_catalog(SellingApiForbiddenException(
        403, "Access to requested resource is denied."))
    check("a refused account is denied", C.product_type_of({}, "UK", MID, "B0DNYVCK4J")["status"], "denied")
    check("  and a denied answer never carries a type",
          C.product_type_of({}, "UK", MID, "B0DNYVCK4J")["product_type"], "")

    seen = {}
    SP.ProductTypeDefinitions = fake_ptd(
        {"productTypes": [{"name": "TABLE", "displayName": "Table", "marketplaceIds": [MID]}],
         "productTypeVersion": "x"}, seen)
    got = C.search_product_types({}, "UK", MID, item_name="Folding Camping Table")
    check("search by title", (got["status"], got["types"]),
          ("ok", [{"name": "TABLE", "display_name": "Table"}]))
    check("  sent as Amazon's itemName", seen.get("itemName"), "Folding Camping Table")

    seen.clear()
    C.search_product_types({}, "UK", MID, keywords="camping  table")
    check("words are sent comma-separated", seen.get("keywords"), "camping,table")

    SP.ProductTypeDefinitions = fake_ptd(SellingApiForbiddenException(403, "denied"), {})
    check("a refused search is denied",
          C.search_product_types({}, "UK", MID, item_name="x")["status"], "denied")
    check("nothing to search for is refused before asking",
          C.search_product_types({}, "UK", MID)["status"], "failed")
finally:
    SP.CatalogItemsV20220401, SP.ProductTypeDefinitions = real_cat, real_ptd


# ================================================================ the verdicts
print("\n== listing/product_type.compare says what would change ==")
from listing import product_type as PT

drafts = [
    {"sku": "8.59_2Days_B0DNYVCK4J", "title": "Folding Camping Table", "asin": "B0DNYVCK4J", "product_type": "HOME"},
    {"sku": "15.80_3Days_B00TKIAZWG", "title": "Bar Stool", "asin": "B00TKIAZWG", "product_type": "CHAIR"},
    {"sku": "9.39_2Days_B0FGCXYCP3", "title": "Battle Rope", "asin": "B0FGCXYCP3", "product_type": "JUMP_ROPE"},
]
answers = {"B0DNYVCK4J": {"status": "ok", "product_type": "TABLE"},
           "B00TKIAZWG": {"status": "denied", "product_type": "", "error": "refused"},
           "B0FGCXYCP3": {"status": "ok", "product_type": "JUMP_ROPE"}}
v = {r["sku"]: r for r in PT.compare(drafts, answers)}
check("HOME -> TABLE is a change", (v["8.59_2Days_B0DNYVCK4J"]["verdict"],
                                    v["8.59_2Days_B0DNYVCK4J"]["amazon"]), ("change", "TABLE"))
check("a refused lookup changes nothing", v["15.80_3Days_B00TKIAZWG"]["verdict"], "not_checked")
check("  and says why", v["15.80_3Days_B00TKIAZWG"]["why"], "refused")
check("an already-right type is left alone", v["9.39_2Days_B0FGCXYCP3"]["verdict"], "same")


# ============================================================ the routes, run
print("\n== the routes, on a throwaway database ==")
tmp = tempfile.mkdtemp(prefix="pt_routes_")
cfg_path = os.path.join(tmp, "config.json")
with open(cfg_path, "w") as fh:
    json.dump({"accounts": [{"id": "nestwell_goods", "label": "Nestwell",
                             "default_marketplace": "UK"}]}, fh)
os.environ["ALTASCRAPER_DB"] = os.path.join(tmp, "altascraper.db")

from data import db as DB
conn = DB.get_db(cfg_path)
ROWS = [("nestwell_goods", "8.59_2Days_B0DNYVCK4J", "B0DNYVCK4J", "HOME", "API_READY", "Folding Camping Table"),
        ("nestwell_goods", "7.99_3Days_B07GDBY3YS", "B07GDBY3YS", "HOME", "LIVE", "Weed Puller"),
        ("nestwell_goods", "6.00_3Days_B0SUBMITTD", "B0SUBMITTD", "HOME", "SUBMITTED", "Sent one"),
        ("nestwell_goods", "0.00_3Days_336636956670", "", "HOME", "GENERATED", "No ASIN"),
        ("jack_uk", "8.59_2Days_B0DNYVCK4J", "B0DNYVCK4J", "HOME", "GENERATED", "Other account")]
for r in ROWS:
    conn.execute("INSERT INTO listings (workspace_id, sku, competitor_asin, product_type, status, title) "
                 "VALUES (?,?,?,?,?,?)", r)
conn.commit()

got = PT.drafts_to_check(cfg_path, "nestwell_goods")
check("only the unsent draft with an ASIN, in this account",
      [d["sku"] for d in got], ["8.59_2Days_B0DNYVCK4J"])

from flask import Flask
import accounts as ACC
from routes import product_type_routes as R

app = Flask(__name__)
state = {"active_account_id": "nestwell_goods"}
R.register(app, CONFIG_PATH=cfg_path, _cfg=lambda: json.load(open(cfg_path)), _state=state)
cli = app.test_client()

calls = []
real_resolve, real_of, real_search = ACC.resolve_catalog_creds, C.product_type_of, C.search_product_types
try:
    ACC.resolve_catalog_creds = lambda cfg, acc, path=None: ({"refresh_token": "x"}, None)
    C.product_type_of = lambda creds, mkt, mid, asin, timeout=30: (
        calls.append((mkt, mid, asin)) or {"status": "ok", "product_type": "TABLE", "error": ""})

    j = cli.get("/product_types/drafts?account=nestwell_goods").get_json()
    # The draft with no competitor ASIN is now checked by its title
    # (test_product_type_fix_scope.py covers that and the reasons).
    check("GET drafts", [(d["sku"], d["method"]) for d in j["drafts"]],
          [("8.59_2Days_B0DNYVCK4J", "asin"), ("0.00_3Days_336636956670", "title")])

    j = cli.post("/product_types/lookup", json={
        "account": "nestwell_goods", "marketplace": "UK",
        "skus": ["8.59_2Days_B0DNYVCK4J", "7.99_3Days_B07GDBY3YS"]}).get_json()
    check("lookup returns the decided verdict",
          [(r["sku"], r["current"], r["amazon"], r["verdict"]) for r in j["rows"]],
          [("8.59_2Days_B0DNYVCK4J", "HOME", "TABLE", "change")])
    check("  a LIVE listing named by the browser is not looked up",
          [c[2] for c in calls], ["B0DNYVCK4J"])
    check("  in the UK marketplace", calls[0][:2], ("UK", MID))
    after = conn.execute("SELECT product_type FROM listings WHERE workspace_id='nestwell_goods' "
                         "AND sku='8.59_2Days_B0DNYVCK4J'").fetchone()[0]
    check("  and nothing was written by the lookup", after, "HOME")

    C.search_product_types = lambda creds, mkt, mid, item_name="", keywords="", timeout=30: {
        "status": "ok", "types": [{"name": "TABLE", "display_name": "Table"}], "error": ""}
    j = cli.get("/product_types/search?account=nestwell_goods&title=Folding%20Camping%20Table").get_json()
    check("search route", (j["ok"], [t["name"] for t in j["types"]]), (True, ["TABLE"]))

    def _refuse(cfg, acc, path=None):
        raise LookupError("Nestwell has no Amazon developer app")
    ACC.resolve_catalog_creds = _refuse
    j = cli.get("/product_types/search?account=nestwell_goods&q=table").get_json()
    check("an account with no access says so", (j["ok"], j.get("denied")), (False, True))

    j = cli.post("/product_types/recheck", json={"account": "nestwell_goods"}).get_json()
    check("recheck works the warnings out", j.get("ok"), True)
finally:
    ACC.resolve_catalog_creds, C.product_type_of, C.search_product_types = real_resolve, real_of, real_search


# ======================================================== the screen's wiring
print("\n== the screen ==")
AF = open(os.path.join(HERE, "static", "js", "autofix.js"), encoding="utf-8").read()
PJ = open(os.path.join(HERE, "static", "js", "product_type.js"), encoding="utf-8").read()
TP = open(os.path.join(HERE, "templates", "dashboard.html"), encoding="utf-8").read()
check("the box no longer claims Amazon assigned the type", '" (Amazon-assigned)"' in AF, False)
check("the search sits under the product-type box", "ptSearchBox(sku, r)" in AF, True)
check("a picked type is saved through the dropdown's own change", 'dispatchEvent(new Event("change"))' in PJ, True)
check("applied changes go through editField", 'editField(r.sku, "col", "Product Type", r.amazon)' in PJ, True)
check("the browser does not decide the verdict itself", 'amazon === current ? "same"' in PJ, False)
check("the script is loaded after autofix.js",
      TP.find("/static/js/autofix.js") < TP.find("/static/js/product_type.js"), True)
check("the toolbar button exists", 'onclick="ptFixDrafts()"' in TP, True)

print()
if FAILS:
    print("FAILED: %d" % len(FAILS))
    sys.exit(1)
print("all passed")
