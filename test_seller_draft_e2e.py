"""/seller/draft end to end: does the family path actually RUN?

The existing tests assert what the route's SOURCE says. That proves the code was
written; it does not prove it executes. This calls the real endpoint with eBay
stubbed and a throwaway database, and then looks at what landed.
"""
import json, os, sys, tempfile, shutil
sys.path.insert(0, r"D:\AltaScraper")

TMP = tempfile.mkdtemp()
CFG = os.path.join(TMP, "config.json")
real = json.load(open(r"D:\AltaScraper\config.json", encoding="utf-8"))
json.dump({"accounts": real.get("accounts", [])[:1],
           "db_path": os.path.join(TMP, "e2e.db"),
           "storage": "DB",
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
    check("three were enrolled -- the parent is not a product", j.get("enrolled"), 3)
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

    check("every enrollment is DRY RUN",
          sorted({e["mode"] for e in enr}), ["dry_run"])
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
