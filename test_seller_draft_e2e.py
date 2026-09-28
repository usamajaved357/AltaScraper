"""/seller/draft end to end: does the family path actually RUN?

The existing tests assert what the route's SOURCE says. That proves the code was
written; it does not prove it executes. This calls the real endpoint with eBay
stubbed and a throwaway database, and then looks at what landed.
"""
# THE TREE THIS TEST LIVES IN. It used to name the main checkout outright, so
# run from any other checkout it silently tested THAT checkout's code
# (Milestone 1, 28 Sep 2026: 141 files did this).
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import json, os, sys, tempfile, shutil
sys.path.insert(0, _REPO)

TMP = tempfile.mkdtemp()
CFG = os.path.join(TMP, "config.json")
# A MADE-UP ACCOUNT, NOT THE OWNER'S. This copied the first account out of the
# real config.json -- credentials and all -- into a temp file on every run, and
# in any other checkout it simply crashed. eBay is stubbed below and nothing
# here talks to Amazon, so an account with no credentials is all it needs
# (Milestone 10, 28 Sep 2026).
_E2E_ACCOUNT = {"id": "e2e_account", "name": "E2E test account",
                "label": "E2E test account", "default_marketplace": "UK",
                "marketplaces": ["UK"], "brand_name": "E2E Test Brand",
                "brands": ["E2E Test Brand"]}
real = {"accounts": [_E2E_ACCOUNT]}
json.dump({"accounts": [_E2E_ACCOUNT],
           "db_path": os.path.join(TMP, "e2e.db"),
           "storage": "DB",
           # visible placeholders, like run_tests.TEST_CONFIG -- not credentials
           "anthropic_api_key": "test-placeholder-not-a-real-key",
           "google_spreadsheet_id": "test-placeholder-sheet",
           "google_service_account_json": "test-placeholder-service-account.json",
           "ebay_app_id": "x", "ebay_cert_id": "y"},
          open(CFG, "w", encoding="utf-8"))

os.environ["ALTA_CONFIG"] = CFG
import dashboard as D
D.CONFIG_PATH = CFG

from api import ebay as E

def _kid(var, colour, size, price):
    return {"itemId": "v1|223778867020|%s" % var, "legacyItemId": "223778867020",
            "title": "Fruit of The Loom Tee",
            "image": {"imageUrl": "https://i.ebayimg.com/%s.jpg" % colour},
            "price": {"value": price, "currency": "GBP"},
            "itemWebUrl": "https://www.ebay.co.uk/itm/223778867020?var=%s" % var,
            "shippingOptions": [{"shippingCost": {"value": "0.00", "currency": "GBP"}}],
            "localizedAspects": [{"name": "Colour", "value": colour},
                                 {"name": "Size", "value": size},
                                 {"name": "Brand", "value": "FOTL"}]}

GROUP = {"items": [_kid("111", "Black", "S", "14.49"),
                   _kid("222", "Black", "M", "14.49"),
                   _kid("333", "Grey",  "L", "23.49")]}

E.item_group = lambda gid, a, c, **kw: {"status": E.OK, "data": GROUP, "error": ""}

app = D.build_app(); app.config["TESTING"] = True
fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-62s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))

acc = (real.get("accounts") or [{}])[0]
WS, MKT = acc.get("id"), (acc.get("default_marketplace") or "UK")

with app.test_client() as c:
    with c.session_transaction() as s:
        s["user"] = "owner"; s["role"] = "owner"; s["is_owner"] = True
    c.post("/accounts/select", json={"id": WS, "marketplace": MKT})

    row = {"item_id": "223778867020", "title": "Fruit of The Loom Tee",
           "url": "https://www.ebay.co.uk/itm/223778867020",
           "image": "https://i.ebayimg.com/x.jpg", "price": 14.49, "shipping": 0.0,
           "is_group": True,
           "group_href": ("https://api.ebay.com/buy/browse/v1/item/"
                          "get_items_by_item_group?item_group_id=223778867020"),
           "selected": True, "screen": {"verdict": "clear", "notes": []}}

    r = c.post("/seller/draft", json={"confirmed": True, "rows": [row]})
    j = r.get_json() or {}
    print("\nHTTP %s  ok=%s" % (r.status_code, j.get("ok")))
    print("  error: %s" % str(j.get("error"))[:200] if j.get("error") else "")
    print("  drafted=%s enrolled=%s errors=%s"
          % (j.get("drafted"), j.get("enrolled"), j.get("errors")))
    for n in (j.get("families") or []):
        print("  family: %s" % n)

    print("\n=== what actually landed ===")
    check("the request succeeded", j.get("ok"), True)
    check("one parent plus three children were written", j.get("drafted"), 4)
    # RE-PINNED (Milestone 10): drafts are NEVER enrolled. The owner's 7 Sep
    # 2026 rule -- the repricer takes a listing "when the listing goes live,
    # not on draft" -- is what routes/seller_routes.py does; this still
    # expected 3 because it had not been able to run since (it needed the
    # real config.json).
    check("none were enrolled -- drafts wait for go-live", j.get("enrolled"), 0)
    check("no errors", j.get("errors"), [])
    skus = j.get("skus") or []
    check("four DISTINCT skus", len(set(skus)), 4)
    check("  the parent is named for the listing",
          "PARENT_223778867020" in skus, True)

    from data import db as _db
    conn = _db.get_db(CFG)
    enr = [dict(x) for x in conn.execute(
        "SELECT sku, mode, enrolled FROM sourcing_enrolment")]
    src = [dict(x) for x in conn.execute(
        "SELECT sku, url, kind FROM sourcing_sources ORDER BY sku")]
    print("\n  enrollment rows: %d" % len(enr))
    for e in enr: print("     %-40s mode=%s enrolled=%s" % (e["sku"], e["mode"], e["enrolled"]))
    print("  source rows: %d" % len(src))
    for s2 in src: print("     %-40s %s" % (s2["sku"], s2["url"]))

    check("nothing is in the repricer yet (the supplier is recorded, not enrolled)",
          len(enr), 0)
    check("the parent was never enrolled",
          any("PARENT" in e["sku"] for e in enr), False)
    check("each child got a source", len(src), 3)
    check("  each pointing at its OWN variation",
          sorted(u["url"].split("var=")[1] for u in src), ["111", "222", "333"])

    print("\n=== importing the same seller twice ===")
    r2 = c.post("/seller/draft", json={"confirmed": True, "rows": [row]})
    j2 = r2.get_json() or {}
    src2 = conn.execute("SELECT COUNT(*) c FROM sourcing_sources").fetchone()["c"]
    check("it succeeds again", j2.get("ok"), True)
    check("  the drafts are updated, not duplicated",
          conn.execute("SELECT COUNT(*) c FROM listings WHERE workspace_id=?",
                       (WS,)).fetchone()["c"], 4)
    check("  and NO duplicate sources are added", src2, 3)

print("\nFAILURES: %d" % len(fails))
for f in fails: print("   -", f)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fails else 0)
